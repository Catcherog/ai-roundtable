#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI圆桌 — 全链路架构收敛、安全闭环与故障注入自动化回归验收套件
(scripts/verify_full_convergence.py)

覆盖 Phase 0 (P0-1 ~ P0-4)、Phase 1 (P1-1 ~ P1-2)、Phase 2 (P2-1) 全部接口契约、
四大架构基线与 7 条禁止退化负面清单（支持无网络沙箱内存态 HTTP/SSE 驱动及实机回环双模验证）。
"""

from __future__ import annotations

import ast
import asyncio
import hashlib
import json
import os
import stat
import struct
import subprocess
import sys
import tempfile
import textwrap
import urllib.parse
import zlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import patch

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


class _MemoryWriter:
    """支持无 socket 内存态完整驱动 AsyncHTTPServer.handle_client 的轻量 StreamWriter 替身。"""

    def __init__(self) -> None:
        self.buf = bytearray()
        self._closing = False

    def write(self, data: bytes) -> None:
        self.buf.extend(data)

    async def drain(self) -> None:
        await asyncio.sleep(0)

    def is_closing(self) -> bool:
        return self._closing

    def close(self) -> None:
        self._closing = True

    async def wait_closed(self) -> None:
        return


async def mem_http_request(
    app: Any,
    method: str,
    target: str,
    *,
    headers: Optional[Dict[str, str]] = None,
    body: bytes = b"",
) -> Tuple[int, Dict[str, str], bytes]:
    hdrs = {"Host": f"{app.host}:{app.port}", **(headers or {})}
    if body and "Content-Length" not in hdrs and "content-length" not in hdrs:
        hdrs["Content-Length"] = str(len(body))
    head_lines = [f"{method} {target} HTTP/1.1"] + [f"{k}: {v}" for k, v in hdrs.items()]
    raw_req = ("\r\n".join(head_lines) + "\r\n\r\n").encode("latin-1") + body

    reader = asyncio.StreamReader(limit=32768)
    reader.feed_data(raw_req)
    reader.feed_eof()
    writer = _MemoryWriter()
    await app.handle_client(reader, writer)

    raw_resp = bytes(writer.buf)
    sep = raw_resp.find(b"\r\n\r\n")
    assert sep > 0, f"Invalid HTTP response: {raw_resp!r}"
    head_part = raw_resp[:sep].decode("latin-1")
    resp_body = raw_resp[sep + 4 :]
    lines = head_part.split("\r\n")
    status_code = int(lines[0].split(" ", 2)[1])
    resp_headers: Dict[str, str] = {}
    for hl in lines[1:]:
        if ":" in hl:
            k, v = hl.split(":", 1)
            resp_headers[k.strip().lower()] = v.strip()
    return status_code, resp_headers, resp_body


async def mem_json(
    app: Any,
    token: str,
    method: str,
    target: str,
    payload: Optional[Dict[str, Any]] = None,
) -> Tuple[int, Dict[str, str], Dict[str, Any]]:
    hdrs = {"Content-Type": "application/json"}
    if token:
        hdrs["X-Roundtable-Token"] = token
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else b""
    st, rh, rb = await mem_http_request(app, method, target, headers=hdrs, body=body)
    data = json.loads(rb.decode("utf-8")) if rb else {}
    return st, rh, data


def build_valid_png(width: int = 32, height: int = 24) -> bytes:
    def _chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    raw_rows = (b"\x00" + b"\x3b\x63\xf6" * width) * height
    return b"".join(
        [
            b"\x89PNG\r\n\x1a\n",
            _chunk(b"IHDR", ihdr),
            _chunk(b"IDAT", zlib.compress(raw_rows)),
            _chunk(b"IEND", b""),
        ]
    )


def make_executable(path: Path, content: str) -> Path:
    path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def verify_static_negative_list() -> None:
    # 1. 仓库根目录无异常空文件 `=` 且 domain/whiteboard.py 已独立解耦
    assert not (ROOT_DIR / "=").exists(), "仓库根目录仍残留异常文件 `=`"
    assert (ROOT_DIR / "backend" / "domain" / "whiteboard.py").is_file(), "缺少解耦后的 backend/domain/whiteboard.py"

    # 2. Python 纯标准库零第三方运行时依赖 AST 扫描（兼容 Python 3.9+）
    import importlib.util
    optional_platform_stdlib = {"__future__", "msvcrt", "fcntl", "termios", "pty", "resource", "grp", "pwd", "winreg", "_winapi"}
    internal_pkgs = {"backend", "cli_adapters", "orchestrator", "server", "storage", "attachments", "workspace_backup", "domain", "drivers", "engine", "context"}
    for py_file in (ROOT_DIR / "backend").rglob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            imported_tops: List[str] = []
            if isinstance(node, ast.Import):
                imported_tops.extend(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                imported_tops.append(node.module.split(".")[0])
            for top in imported_tops:
                if top in internal_pkgs or top in optional_platform_stdlib:
                    continue
                spec = importlib.util.find_spec(top)
                assert spec is not None, f"未知导入模块: {py_file} -> {top}"
                origin = str(spec.origin or "")
                assert "site-packages" not in origin and "dist-packages" not in origin, (
                    f"发现第三方运行时依赖导入: {py_file} -> {top} ({origin})"
                )

    # 3. 前端禁止退化红线与全量 DOM ID 闭合校验
    import re
    index_html = (ROOT_DIR / "frontend" / "index.html").read_text(encoding="utf-8")
    v4_js = (ROOT_DIR / "frontend" / "v4_ui.js").read_text(encoding="utf-8")
    app_js = (ROOT_DIR / "frontend" / "app.js").read_text(encoding="utf-8")
    html_ids = re.findall(r'\sid="([^"]+)"', index_html)
    known_ids = set(html_ids)
    assert len(html_ids) == len(known_ids), "frontend/index.html 存在重复 ID"
    for req_id in ("cfgWsBindScopeSeg", "ackSnapshotBtn", "v4AttachmentTray", "wbCardAbsent", "roundtableRing"):
        assert req_id in known_ids, f"frontend/index.html 缺少 #{req_id}"

    seats_cap = ("Carbon", "Grok", "Astra", "Vega", "Titan", "Prism")
    for fn_name, content in (("v4_ui.js", v4_js), ("app.js", app_js)):
        assert "window.fetch =" not in content and "window.fetch=" not in content, f"{fn_name} 仍存在 window.fetch 全局拦截"
        assert "new MutationObserver" not in content and "MutationObserver(" not in content, f"{fn_name} 仍存在 MutationObserver"
        assert "MODEL_CHIPS_BY_DRIVER" not in content, f"{fn_name} 仍残留硬编码 MODEL_CHIPS_BY_DRIVER"
        assert "document.cookie" not in content, f"{fn_name} 禁止访问 Cookie 存储凭据"
        for ls_line in [ln for ln in content.splitlines() if "localStorage.setItem" in ln]:
            assert "token" not in ls_line.lower() and "auth" not in ls_line.lower(), (
                f"{fn_name} 严禁将鉴权令牌写入 localStorage: {ls_line}"
            )
        for m in re.finditer(r"""(?:\bel|\$id|\bgetElementById)\(\s*["']([^"']+)["']\s*\)""", content):
            if m.group(1) != "wbTopicEditInput":
                assert m.group(1) in known_ids, f"{fn_name} 引用了缺失的静态 DOM ID: #{m.group(1)}"
        for m in re.finditer(r"""(?:\bel|\$id|\bgetElementById)\(\s*`([^`]+)`\)""", content):
            pat = m.group(1)
            if pat.startswith("msg-") or pat.startswith("wb-editor-"):
                continue
            for cap in seats_cap:
                exp = re.sub(r"\$\{(?:cap|seatCap)\}", cap, pat)
                exp = re.sub(r"\$\{(?:agentId|aid|msg\.speaker)\}", cap.lower(), exp)
                if exp == "settings-pane-${k}":
                    for tab in ("seats", "concurrency", "diagnostics"):
                        assert f"settings-pane-{tab}" in known_ids
                else:
                    assert exp in known_ids, f"{fn_name} 模板引用了缺失的 DOM ID: #{exp}"

    # 4. server.py 默认监听 127.0.0.1 且默认 --workspace 为空字符串（纯研讨模式，非 ROOT_DIR）
    srv_src = (ROOT_DIR / "backend" / "server.py").read_text(encoding="utf-8")
    assert 'default="127.0.0.1"' in srv_src
    assert "0.0.0.0" not in srv_src
    assert '"--workspace", default=""' in srv_src, "server.py 未移除将 ROOT_DIR 设为默认 --workspace 的自举风险"


async def run_convergence_suite() -> None:
    passed: List[str] = []

    def ok(label: str, detail: str = "") -> None:
        suf = f" ({detail})" if detail else ""
        print(f"  [PASS] {label}{suf}", flush=True)
        passed.append(label)

    verify_static_negative_list()
    ok("1. 静态负面清单与纯标准库零第三方依赖 AST 审计", "零 fetch 劫持 / 零 MutationObserver / 零硬编码模型表 / 零 = 残留")

    with tempfile.TemporaryDirectory(prefix="ai_rt_conv_verify_") as tmp_str:
        tmp_root = Path(tmp_str).resolve()
        rt_home = tmp_root / "rt_home"
        rt_home.mkdir(parents=True, exist_ok=True)
        os.environ["AI_ROUNDTABLE_HOME"] = str(rt_home)
        os.environ["AI_ROUNDTABLE_FAST_TEST"] = "1"

        # 注入引导期敏感环境变量，严格验证不会泄漏至 CLI 子进程或验证命令子进程
        os.environ["AI_ROUNDTABLE_BOOT_TOKEN"] = "SENSITIVE_BOOT_TOKEN_DO_NOT_LEAK_999"
        os.environ["AI_ROUNDTABLE_BOOTSTRAP_CODE"] = "SENSITIVE_BOOTSTRAP_CODE_DO_NOT_LEAK_888"
        os.environ["AI_ROUNDTABLE_BOOT_ID"] = "boot_env_leak_probe"
        os.environ["AI_ROUNDTABLE_BOOT_EXTRA"] = "SENSITIVE_EXTRA_777"

        from backend.cli_adapters import build_host_env, list_workspace_files
        from backend.domain.whiteboard import _infer_source_msg_id, _normalize_and_sync_whiteboard
        from backend.drivers import sanitize_subprocess_env, windows_support
        from backend.engine import run_post_execution_verification
        from backend.server import AsyncHTTPServer
        from backend.project_edits import apply_edit_reply
        from backend.workspace_backup import (
            HONEST_ROLLBACK_DISCLOSURE,
            MAX_BACKUP_WORKSPACE_BYTES,
            WorkspaceBackup,
            precheck_workspace_capacity,
        )

        # ---------------- 2. 子进程凭据隔离与验证钩子安全执行 ----------------
        for env_cand in (build_host_env(), sanitize_subprocess_env(dict(os.environ))):
            leaked_keys = [k for k in env_cand if k.startswith("AI_ROUNDTABLE_BOOT")]
            assert not leaked_keys, f"子进程环境变量发生敏感引导凭据泄漏: {leaked_keys}"

        ws_a = tmp_root / "proj_ws_a"
        ws_b = tmp_root / "proj_ws_b"
        ws_a.mkdir(parents=True)
        ws_b.mkdir(parents=True)
        (ws_a / "core.py").write_text("VALUE = 1\n", encoding="utf-8")
        (ws_b / "other.py").write_text("OTHER = 2\n", encoding="utf-8")

        env_dump_file = ws_a / "verify_env_probe.json"
        v_cmd = (
            f'"{sys.executable}" -c "import json,os,pathlib; '
            f"pathlib.Path('verify_env_probe.json').write_text(json.dumps({{'cwd':os.getcwd(),"
            f"'leaked':[k for k in os.environ if k.startswith('AI_ROUNDTABLE_BOOT')]}}))\""
        )
        v_rep = await run_post_execution_verification(
            v_cmd, workspace_realpath=str(ws_a), env=dict(os.environ)
        )
        assert v_rep["passed"], f"验证钩子执行失败: {v_rep}"
        probe_obj = json.loads(env_dump_file.read_text("utf-8"))
        assert os.path.realpath(probe_obj["cwd"]) == os.path.realpath(str(ws_a))
        assert probe_obj["leaked"] == [], f"验证命令泄漏了敏感环境变量: {probe_obj['leaked']}"
        env_dump_file.unlink()

        # 验证 shell=False：分号拼接参数绝不会被 Shell 拆分为第二条子命令执行
        marker_probe = ws_a / "extra_arg_probe.txt"
        await run_post_execution_verification(
            f'"{sys.executable}" -c "import sys; sys.exit(0)" ; touch "{marker_probe}"',
            workspace_realpath=str(ws_a),
            env=dict(os.environ),
        )
        assert not marker_probe.exists(), "严重漏洞：post_exec_verify_cmd 仍在启用 shell=True 解析分号！"
        ok("2. CLI 与验证子进程凭据剥离（AI_ROUNDTABLE_BOOT_* 清零）及 shell=False 锁定 cwd")

        # ---------------- 3. 工作区爆炸半径前置硬拦截、output/ 归档忽略与 128 MiB 预检 ----------------
        mock_cli = make_executable(
            tmp_root / "mock_exec_cli",
            """\
            #!/usr/bin/env python3
            import os, sys
            from pathlib import Path
            args = sys.argv[1:]
            if "--version" in args:
                print("mock-cli 6.0.0")
                sys.exit(0)
            prompt = " ".join(args)
            if "仅回复 OK" in prompt or "Reply with OK only" in prompt:
                print("OK")
                sys.exit(0)
            leaked = [k for k in os.environ if k.startswith("AI_ROUNDTABLE_BOOT")]
            if leaked:
                sys.stderr.write(f"LEAKED_ENV:{leaked}\\n")
                sys.exit(9)
            if "写入本地项目工作区" in prompt or os.environ.get("MOCK_DO_WRITE") == "1":
                cwd = Path.cwd()
                (cwd / "core.py").write_text("VALUE = 2\\n", encoding="utf-8")
                (cwd / "added_by_ai.py").write_text("ADDED = True\\n", encoding="utf-8")
                print("已完成安全写入。")
                sys.exit(0)
            print("已完成只读实施方案预演。\\n\\n[白板要点]\\n- 任务：核对只读预演输出")
            """,
        )

        app = AsyncHTTPServer(
            host="127.0.0.1",
            port=18765,
            workspace_dir="",
            boot_token="conv_test_token_abcdef0123456789",
            boot_id="boot_conv_01",
            bootstrap_code="init_code_123456",
        )

        try:
            # 3.1 验证绑定拦截：磁盘根 `/`、家目录 `$HOME`、`~/.ai-roundtable`、`.app` 包、凭证目录 `~/.ssh`
            fake_home = tmp_root / "fake_user_home"
            fake_ssh = fake_home / ".ssh"
            fake_keychain = fake_home / "Library" / "Keychains"
            fake_app_bundle = tmp_root / "DemoApp.app" / "Contents" / "Resources"
            for d in (fake_ssh, fake_keychain, fake_app_bundle):
                d.mkdir(parents=True, exist_ok=True)

            with patch.dict(os.environ, {"HOME": str(fake_home)}):
                for bad_p, exp_reason in (
                    ("/", "filesystem_root_forbidden"),
                    (str(fake_home), "home_dir_forbidden"),
                    (str(rt_home), "runtime_state_dir_forbidden"),
                    (str(fake_app_bundle), "app_bundle_forbidden"),
                    (str(fake_ssh), "sensitive_credentials_dir_forbidden"),
                    (str(fake_keychain), "sensitive_credentials_dir_forbidden"),
                ):
                    is_ok, _, det = app.orchestrator.validate_safe_workspace_path_detailed(bad_p)
                    assert not is_ok and det.get("reason") == exp_reason, f"路径 {bad_p} 未按预期拦截 ({exp_reason}): {det}"

            # 3.2 未跟踪的归档照常跳过；大项目仍能绑定并按文件跨目录执行。
            untracked_out = ws_a / "output" / "archives"
            untracked_out.mkdir(parents=True, exist_ok=True)
            with open(untracked_out / "release_bundle.zip", "wb") as f_out:
                f_out.seek(MAX_BACKUP_WORKSPACE_BYTES + 1024 * 1024)
                f_out.write(b"\x00")
            # 因为未跟踪的 output/ 默认被快照与 @ 检索忽略，ws_a 准入预检应顺利通过且 @ 检索不包含 output/
            cap_ok_with_out, total_b_out, _, _ = precheck_workspace_capacity(str(ws_a))
            assert cap_ok_with_out and total_b_out < 1024 * 1024, "未纳入版本控制的 output/ 归档目录未被快照扫描忽略！"
            at_files = list_workspace_files(str(ws_a), query="", limit=50).get("files", [])
            assert all(not f["path"].startswith("output/") for f in at_files), f"@检索泄露了未跟踪 output/: {at_files}"

            # 大文件不得进入逐文件快照，即使回滚时它已被其他进程修改。
            oversize_ws = tmp_root / "oversize_ws"
            (oversize_ws / "heavy_assets").mkdir(parents=True)
            with open(oversize_ws / "heavy_assets" / "weights.bin", "wb") as f_big:
                f_big.seek(MAX_BACKUP_WORKSPACE_BYTES + 2 * 1024 * 1024)
                f_big.write(b"\x01")

            sid_default = app.orchestrator.default_session_id
            tok = app.boot_token
            st_over, _, d_over = await mem_json(
                app,
                tok,
                "POST",
                f"/api/sessions/{sid_default}/workspace",
                {"workspace_dir": str(oversize_ws)},
            )
            assert st_over == 200 and d_over["workspace_dir"] == str(oversize_ws)
            src = oversize_ws / "src" / "中文.py"
            src.parent.mkdir()
            src.write_bytes(b"value = 1\r\n")
            new_file = oversize_ws / "tests" / "nested" / "value.txt"
            snap = WorkspaceBackup.capture_for_execution(str(oversize_ws), runtime_home=rt_home)
            assert snap.target_paths == []
            edit = {"path": "src/中文.py", "replacements": [{"old": "value = 1\n", "new": "value = 2\n"}]}
            for bad_edit in ({"path": "../outside.py", "create": "x"}, {"path": "missing.py", "replacements": [{"old": "x", "new": "y"}]}):
                try:
                    apply_edit_reply(snap, json.dumps({"summary": "test", "files": [edit, bad_edit]}))
                except ValueError:
                    pass
                else:
                    raise AssertionError("invalid batch accepted")
                assert src.read_bytes() == b"value = 1\r\n"
            apply_edit_reply(snap, json.dumps({"summary": "test", "files": [edit, {"path": "tests/nested/value.txt", "create": "2\n"}]}))
            assert src.read_bytes() == b"value = 2\r\n" and new_file.read_text() == "2\n"
            assert snap.finish() and set(snap.changed_paths) == {"src/中文.py", "tests/nested/value.txt"}
            restored = WorkspaceBackup.load_from_manifest(snap.manifest_path)
            src.write_text("manual\n")
            assert not restored.restore_with_report()[0] and new_file.exists()
            src.write_bytes(b"value = 2\r\n")
            unrelated = oversize_ws / "other.txt"
            unrelated.write_text("concurrent")
            assert restored.restore_with_report()[0]
            assert src.read_bytes() == b"value = 1\r\n" and not new_file.exists() and unrelated.read_text() == "concurrent"
            ok("3. 敏感目录防护、未跟踪归档忽略、大项目绑定、跨目录写入、冲突检测与重载后回滚")

            # ---------------- 4. 启动鉴权兑换、X-Roundtable-Boot-Id 与 reissue-bootstrap + driver_catalog ----------------
            st_b1, h_b1, d_b1 = await mem_json(app, "", "POST", "/api/auth/bootstrap", {"code": "init_code_123456"})
            assert st_b1 == 200 and d_b1["token"] == tok and h_b1.get("x-roundtable-boot-id") == "boot_conv_01"
            st_b2, _, _ = await mem_json(app, "", "POST", "/api/auth/bootstrap", {"code": "init_code_123456"})
            assert st_b2 == 401

            st_reissue, _, d_reissue = await mem_json(app, tok, "POST", "/api/auth/reissue-bootstrap", {})
            assert st_reissue == 200 and d_reissue.get("bootstrap_code")
            fresh_code = d_reissue["bootstrap_code"]
            st_b3, _, d_b3 = await mem_json(app, "", "POST", "/api/auth/bootstrap", {"code": fresh_code})
            assert st_b3 == 200 and d_b3["token"] == tok

            st_stat, h_stat, d_stat = await mem_json(app, tok, "GET", "/api/status")
            assert st_stat == 200 and h_stat.get("x-roundtable-boot-id") == "boot_conv_01"
            assert "drivers" in (d_stat.get("driver_catalog") or {}), "/api/status 未下发单源 driver_catalog"
            ok("4. 启动兑换码单次核销、WebView 崩溃重签发 reissue-bootstrap 与 driver_catalog 单源下发")

            # ---------------- 5. 配置保存退出会话工作区状态机、unrestricted 超时对齐与在途热改驱动 409 ----------------
            st_bind_a, _, _ = await mem_json(
                app, tok, "POST", f"/api/sessions/{sid_default}/workspace", {"workspace_dir": str(ws_a)}
            )
            assert st_bind_a == 200

            # POST /api/config 传入 ws_b 仅更新新建会话默认目录，绝不篡改已存在会话 sid_default 的 workspace_dir！
            agents_cfg = {
                aid: {"driver": "agy", "custom_binary": str(mock_cli), "model": "gemini-4-carbon", "discussion_effort": "high"}
                for aid in ("carbon", "grok", "astra", "vega", "titan", "prism")
            }
            st_cfg, _, d_cfg = await mem_json(
                app,
                tok,
                "POST",
                "/api/config",
                {
                    "active_session_id": sid_default,
                    "workspace_dir": str(ws_b),
                    "pacing_mode": "unrestricted",
                    "post_exec_verify_cmd": f'"{sys.executable}" -c "import sys; sys.exit(0)"',
                    "agents": agents_cfg,
                },
            )
            assert st_cfg == 200
            sys_after = d_cfg["system"]
            assert os.path.realpath(sys_after["workspace_dir"]) == os.path.realpath(str(ws_b))
            sess_def = app.orchestrator.get_session(sid_default)
            assert os.path.realpath(sess_def.workspace_dir) == os.path.realpath(str(ws_a)), (
                "严重退化：POST /api/config 顺带篡改了活跃会话的绑定工作区！"
            )
            # 验证 pacing_mode=unrestricted 精确等于 600s / 1800s（未被二次串改为 900s）
            assert sys_after["idle_timeout_sec"] == 600 and sys_after["turn_timeout_sec"] == 1800, (
                f"unrestricted 节奏档位阈值失准: idle={sys_after['idle_timeout_sec']}, turn={sys_after['turn_timeout_sec']}"
            )
            # 验证验证命令按工作区隔离绑定
            assert app.orchestrator.get_verify_cmd_for_workspace(str(ws_a)) != ""
            assert app.orchestrator.get_verify_cmd_for_workspace(str(ws_b)) == ""

            # 模拟会话处于运行忙态时，POST /api/config 热修改参会席位 driver 必须返回 409！
            sess_def.exec_state = "running"
            try:
                st_hot, _, d_hot = await mem_json(
                    app,
                    tok,
                    "POST",
                    "/api/config",
                    {"agents": {"astra": {"driver": "codex"}}},
                )
                assert st_hot == 409 and d_hot.get("reason") == "in_flight_driver_change_forbidden", (
                    f"运行态热改驱动未返回 409: {st_hot} {d_hot}"
                )
                # 尝试在忙态切换工作区也必须返回 409
                st_sw_busy, _, d_sw_busy = await mem_json(
                    app,
                    tok,
                    "POST",
                    f"/api/sessions/{sid_default}/workspace",
                    {"workspace_dir": str(ws_b)},
                )
                assert st_sw_busy == 409 and d_sw_busy.get("reason") == "session_busy"
            finally:
                sess_def.exec_state = "idle"
            ok("5. POST /api/config 剥离会话工作区状态机、unrestricted 600s/1800s 精确对齐与在途热改驱动 409 拦截")

            # ---------------- 6. 四项执行一致性契约漂移 409、逐席缺席确认与 runtime_code_root 热写 403 拦截 ----------------
            sess_def.topic = "验证执行一致性契约与源码自举写保护"
            _, _, d_w1 = await mem_json(
                app,
                tok,
                "POST",
                f"/api/sessions/{sid_default}/whiteboard",
                {"op": "add", "kind": "action", "author": "chair", "text": "更新 core.py 常量并补充新模块"},
            )
            act_id = [it["id"] for it in d_w1["whiteboard"]["items"] if it["kind"] == "action"][0]
            _, _, d_w2 = await mem_json(
                app,
                tok,
                "POST",
                f"/api/sessions/{sid_default}/whiteboard",
                {"op": "toggle_check", "item_id": act_id, "checked": True},
            )
            cur_ver = d_w2["whiteboard"]["wb_version"]

            # 注入 2 个异常缺席席位（grok 与 titan），测试未确认 / 仅确认 1 席 / 全量逐席确认
            sess_def.enabled_agents = ["carbon", "grok", "astra", "titan"]
            app.orchestrator._record_absent_seat(sess_def, "grok", reason="响应超时", error_kind="timeout", abnormal=True)
            app.orchestrator._record_absent_seat(sess_def, "titan", reason="配额限流", error_kind="quota_rate_limit", abnormal=True)

            # 仅传 ["grok"] 时必须 409 拦截（titan 尚未勾选确认）
            st_abs_partial, _, d_abs_partial = await mem_json(
                app,
                tok,
                "POST",
                f"/api/sessions/{sid_default}/execute",
                {
                    "allow_workspace_write": False,
                    "executor_id": "astra",
                    "expected_wb_version": cur_ver,
                    "checked_action_ids": [act_id],
                    "expected_workspace_dir": str(ws_a),
                    "acknowledged_absent_agents": ["grok"],
                },
            )
            assert st_abs_partial == 409 and d_abs_partial.get("reason") == "unacknowledged_absent_seats"

            # 缺省四项契约字段 -> 409 missing_execution_contract + 携带最新快照
            st_miss_c, _, d_miss_c = await mem_json(
                app,
                tok,
                "POST",
                f"/api/sessions/{sid_default}/execute",
                {"allow_workspace_write": False, "acknowledged_absent_agents": ["grok", "titan"]},
            )
            assert st_miss_c == 409 and d_miss_c.get("reason") == "missing_execution_contract"
            assert "session" in d_miss_c and "whiteboard" in d_miss_c

            # wb_version 漂移 -> 409 wb_version_mismatch
            st_ver_drift, _, d_ver_drift = await mem_json(
                app,
                tok,
                "POST",
                f"/api/sessions/{sid_default}/execute",
                {
                    "allow_workspace_write": False,
                    "executor_id": "astra",
                    "expected_wb_version": cur_ver - 1,
                    "checked_action_ids": [act_id],
                    "expected_workspace_dir": str(ws_a),
                    "acknowledged_absent_agents": ["grok", "titan"],
                },
            )
            assert st_ver_drift == 409 and d_ver_drift.get("reason") == "wb_version_mismatch"

            # checked_action_ids 漂移 -> 409 checked_actions_mismatch
            st_chk_drift, _, d_chk_drift = await mem_json(
                app,
                tok,
                "POST",
                f"/api/sessions/{sid_default}/execute",
                {
                    "allow_workspace_write": False,
                    "executor_id": "astra",
                    "expected_wb_version": cur_ver,
                    "checked_action_ids": ["wb_fake_nonexistent"],
                    "expected_workspace_dir": str(ws_a),
                    "acknowledged_absent_agents": ["grok", "titan"],
                },
            )
            assert st_chk_drift == 409 and d_chk_drift.get("reason") == "checked_actions_mismatch"

            # expected_workspace_dir 漂移 -> 409 workspace_dir_mismatch
            st_ws_drift, _, d_ws_drift = await mem_json(
                app,
                tok,
                "POST",
                f"/api/sessions/{sid_default}/execute",
                {
                    "allow_workspace_write": False,
                    "executor_id": "astra",
                    "expected_wb_version": cur_ver,
                    "checked_action_ids": [act_id],
                    "expected_workspace_dir": str(ws_b),
                    "acknowledged_absent_agents": ["grok", "titan"],
                },
            )
            assert st_ws_drift == 409 and d_ws_drift.get("reason") == "workspace_dir_mismatch"

            # runtime_code_root 自举保护：允许只读绑定与只读预演 (202)，硬拦截 allow_workspace_write=True (403)
            _, d_self_sess = (await mem_json(app, tok, "POST", "/api/sessions", {"title": "源码自举只读保护会话"}))[2], None
            st_new_self, _, d_new_self = await mem_json(app, tok, "POST", "/api/sessions", {"title": "源码自举测试会话"})
            sid_self = d_new_self["session"]["session_id"]
            st_bind_self, _, d_bind_self = await mem_json(
                app, tok, "POST", f"/api/sessions/{sid_self}/workspace", {"workspace_dir": str(ROOT_DIR)}
            )
            assert st_bind_self == 200 and d_bind_self.get("is_runtime_code_root") is True
            sess_self = app.orchestrator.get_session(sid_self)
            sess_self.topic = "自举保护验证"
            _, _, d_sw1 = await mem_json(
                app, tok, "POST", f"/api/sessions/{sid_self}/whiteboard",
                {"op": "add", "kind": "action", "author": "chair", "text": "只读预演架构改造"},
            )
            self_act_id = [it["id"] for it in d_sw1["whiteboard"]["items"] if it["kind"] == "action"][0]
            _, _, d_sw2 = await mem_json(
                app, tok, "POST", f"/api/sessions/{sid_self}/whiteboard",
                {"op": "toggle_check", "item_id": self_act_id, "checked": True},
            )
            self_contract = {
                "expected_wb_version": d_sw2["whiteboard"]["wb_version"],
                "checked_action_ids": [self_act_id],
                "expected_workspace_dir": str(ROOT_DIR),
                "acknowledged_absent_agents": [],
            }
            st_self_write, _, d_self_write = await mem_json(
                app, tok, "POST", f"/api/sessions/{sid_self}/execute",
                {"allow_workspace_write": True, "executor_id": "astra", **self_contract},
            )
            assert st_self_write == 403 and d_self_write.get("reason") == "runtime_code_root_write_blocked", (
                f"runtime_code_root 原地热写入未被 403 硬拦截: {st_self_write} {d_self_write}"
            )
            st_self_ro, _, _ = await mem_json(
                app, tok, "POST", f"/api/sessions/{sid_self}/execute",
                {"allow_workspace_write": False, "executor_id": "astra", **self_contract},
            )
            assert st_self_ro == 202
            for _ in range(40):
                await asyncio.sleep(0.05)
                if not sess_self.is_busy:
                    break
            ok("6. 四项执行契约漂移 409 返回快照、逐席勾选缺席确认与 runtime_code_root 热写 403 / 只读 202")

            # ---------------- 7. 验证命令失败状态保持未完成、换绑防孤儿快照与四阶段先写后删幂等可重入回滚 ----------------
            # 设置非零退出码验证钩子，执行真实写入后交付状态必须保持「验证未通过」，严禁标为已完成！
            app.orchestrator.set_verify_cmd_for_workspace(
                str(ws_a), f'"{sys.executable}" -c "import sys; sys.stderr.write(\'unit test failed\\n\'); sys.exit(1)"'
            )
            os.environ["MOCK_DO_WRITE"] = "1"
            cur_ver_now = sess_def.whiteboard["wb_version"]
            st_exec_w, _, d_exec_w = await mem_json(
                app,
                tok,
                "POST",
                f"/api/sessions/{sid_default}/execute",
                {
                    "allow_workspace_write": True,
                    "executor_id": "astra",
                    "expected_wb_version": cur_ver_now,
                    "checked_action_ids": [act_id],
                    "expected_workspace_dir": str(ws_a),
                    "acknowledged_absent_agents": ["grok", "titan"],
                },
            )
            assert st_exec_w == 202, f"真实写入准入失败: {st_exec_w} {d_exec_w}"
            for _ in range(50):
                await asyncio.sleep(0.06)
                if not sess_def.is_busy and sess_def.exec_state == "idle":
                    break
            os.environ.pop("MOCK_DO_WRITE", None)

            assert sess_def.whiteboard.get("verification_failed") is True
            assert "验证未通过" in str(sess_def.whiteboard.get("consensus_status") or "")
            assert sess_def.last_backup is not None and sess_def.last_backup.is_rollbackable

            # 7.1 持有未归档可回滚快照时换绑目录：未传 confirm_abandon_rollback=True 必须返回 409！
            manifest_path_1 = sess_def.last_backup.manifest_path
            st_sw_no_conf, _, d_sw_no_conf = await mem_json(
                app,
                tok,
                "POST",
                f"/api/sessions/{sid_default}/workspace",
                {"workspace_dir": str(ws_b)},
            )
            assert st_sw_no_conf == 409 and d_sw_no_conf.get("reason") == "confirm_abandon_rollback_required"
            assert sess_def.last_backup is not None and json.loads(manifest_path_1.read_text("utf-8"))["state"] == "rollbackable"

            # 7.2 区分仅权限位冲突（permission_only_conflicts）与内容冲突（content_conflicts）
            added_f = ws_a / "added_by_ai.py"
            orig_mode = stat.S_IMODE(added_f.stat().st_mode)
            added_f.chmod(0o755 if orig_mode != 0o755 else 0o600)
            st_rb_perm, _, d_rb_perm = await mem_json(app, tok, "POST", f"/api/sessions/{sid_default}/rollback", {})
            assert st_rb_perm == 409 and d_rb_perm.get("conflict_kind") == "permission_only", f"未识别仅权限冲突: {d_rb_perm}"
            assert "added_by_ai.py" in d_rb_perm.get("permission_only_conflicts", [])
            added_f.chmod(orig_mode)

            # 7.3 故障注入：模拟回滚中途进程崩溃（已切入 rolling_back 并完成阶段2覆盖 before_entries，但尚未删除 added_files）
            bk_obj = sess_def.last_backup
            bk_obj.state = "rolling_back"
            bk_obj._persist_manifest()
            (ws_a / "core.py").write_text("VALUE = 1\n", encoding="utf-8")  # 阶段2已恢复部分受管文件，但 added_by_ai.py 仍在！

            # 从磁盘重新加载 rolling_back 清单，验证 is_rollbackable 为 True 且二次重入回滚 100% 幂等成功！
            reloaded_bk = WorkspaceBackup.load_from_manifest(manifest_path_1)
            assert reloaded_bk.state == "rolling_back" and reloaded_bk.is_rollbackable is True
            sess_def.last_backup = reloaded_bk

            # 在 rolling_back 重入前若用户修改了 added_by_ai.py，阶段3删除前二次哈希复核必须拦截误删！
            added_f.write_text("USER_EDITED_DURING_CRASH = True\n", encoding="utf-8")
            st_rb_guard, _, d_rb_guard = await mem_json(app, tok, "POST", f"/api/sessions/{sid_default}/rollback", {})
            assert st_rb_guard == 409 and added_f.exists(), f"删除前二次哈希复核未能拦截用户编辑的新增文件: {d_rb_guard}"

            # 还原新增文件内容后重入回滚 -> 成功完成先写后删并落盘 rolled_back + 诚实披露边界文案
            added_f.write_text("ADDED = True\n", encoding="utf-8")
            st_rb_ok, _, d_rb_ok = await mem_json(app, tok, "POST", f"/api/sessions/{sid_default}/rollback", {})
            assert st_rb_ok == 200, f"rolling_back 幂等重入回滚失败: {d_rb_ok}"
            assert HONEST_ROLLBACK_DISCLOSURE in d_rb_ok.get("message", "")
            assert (ws_a / "core.py").read_text("utf-8") == "VALUE = 1\n"
            assert not added_f.exists()
            assert json.loads(manifest_path_1.read_text("utf-8"))["state"] == "rolled_back"

            # 7.4 验证显式 confirm_abandon_rollback=True 时先落盘 archived 再清空 last_backup（零孤儿清单）
            bk_2 = WorkspaceBackup.capture(str(ws_a), session_id=sid_default, run_id="run_abandon_chk", runtime_home=rt_home)
            (ws_a / "core.py").write_text("VALUE = 3\n", encoding="utf-8")
            bk_2.finish()
            sess_def.last_backup = bk_2
            st_sw_yes, _, _ = await mem_json(
                app,
                tok,
                "POST",
                f"/api/sessions/{sid_default}/workspace",
                {"workspace_dir": str(ws_b), "confirm_abandon_rollback": True},
            )
            assert st_sw_yes == 200
            assert sess_def.last_backup is None
            assert json.loads(bk_2.manifest_path.read_text("utf-8"))["state"] == "archived", (
                "换绑放弃快照时未先将磁盘 manifest 落盘为 archived（产生孤儿清单）！"
            )
            ok("7. 验证失败保持未完成、换绑二次确认防孤儿快照与四阶段先写后删 rolling_back 崩溃重入回滚")

            # ---------------- 8. 全 6 席白板归属映射与独立 60/60 配额池（checked=True 淘汰豁免） ----------------
            six_msgs = [
                {"id": f"m_{seat}_01", "speaker": seat, "content": f"{seat} 核心技术要点锚点文本"}
                for seat in ("carbon", "grok", "astra", "vega", "titan", "prism", "chair")
            ]
            for seat in ("carbon", "grok", "astra", "vega", "titan", "prism", "chair"):
                assert _infer_source_msg_id(seat, f"{seat} 核心技术要点", six_msgs) == f"m_{seat}_01", (
                    f"席位 {seat} 未能关联发言卡片 ID"
                )

            quota_wb: Dict[str, Any] = {"wb_version": 1, "topic": "配额池压测", "items": []}
            # 先插入 5 条已勾选待执行任务（checked=True, pinned=False）
            for i in range(5):
                quota_wb["items"].append(
                    {
                        "id": f"wb_checked_act_{i}",
                        "kind": "action",
                        "text": f"必须受豁免保护的已勾选待执行任务 #{i}",
                        "author": "vega" if i % 2 == 0 else "prism",
                        "pinned": False,
                        "checked": True,
                        "ver": 1,
                    }
                )
            # 再灌入 65 条未置顶 risk 与 65 条未置顶且未勾选 action
            for i in range(65):
                quota_wb["items"].append(
                    {
                        "id": f"wb_flood_risk_{i}",
                        "kind": "risk",
                        "text": f"高频性能风险条目填充样本编号 {i:03d}",
                        "author": "titan",
                        "pinned": False,
                        "checked": True,
                        "ver": 1,
                    }
                )
                quota_wb["items"].append(
                    {
                        "id": f"wb_flood_uncheck_act_{i}",
                        "kind": "action",
                        "text": f"未勾选候选行动项填充样本编号 {i:03d}",
                        "author": "astra",
                        "pinned": False,
                        "checked": False,
                        "ver": 1,
                    }
                )
            _normalize_and_sync_whiteboard(quota_wb, topic="配额池压测", messages=six_msgs)
            surviving_checked = [
                it for it in quota_wb["items"] if it["kind"] == "action" and it.get("checked") is True
            ]
            surviving_unchecked = [
                it for it in quota_wb["items"] if it["kind"] == "action" and not it.get("checked")
            ]
            surviving_risks = [it for it in quota_wb["items"] if it["kind"] == "risk"]
            assert len(surviving_checked) == 5, f"严重缺陷：checked=True 待执行任务被淘汰挤出！剩余={len(surviving_checked)}"
            assert len(surviving_risks) == 60, f"未置顶 risk 配额池应精确保留 60 条，实际={len(surviving_risks)}"
            assert len(surviving_unchecked) == 60, f"未勾选 action 独立配额池应精确保留 60 条，实际={len(surviving_unchecked)}"
            ok("8. 全 6 席（含 vega/titan/prism）发言溯源映射、60/60 独立配额池与 checked=True 淘汰豁免")

            # ---------------- 9. 二进制流异步附件上传、加锁落库广播删除与跨端选目录取消/异常区分 ----------------
            png_bytes = build_valid_png(48, 36)
            st_oct, _, b_oct = await mem_http_request(
                app,
                "POST",
                f"/api/sessions/{sid_default}/attachments",
                headers={
                    "X-Roundtable-Token": tok,
                    "Content-Type": "application/octet-stream",
                    "X-Attachment-Filename": urllib.parse.quote("架构走查图.png"),
                    "X-Attachment-Mime": "image/png",
                },
                body=png_bytes,
            )
            assert st_oct == 201, b_oct.decode("utf-8", errors="replace")
            att_meta = json.loads(b_oct.decode("utf-8"))["attachment"]
            assert att_meta["width"] == 48 and att_meta["height"] == 36
            sess_def.whiteboard["session_attachments"] = [att_meta]
            rev_before_del = sess_def.rev

            st_del_a, _, d_del_a = await mem_json(
                app, tok, "DELETE", f"/api/sessions/{sid_default}/attachments/{att_meta['id']}"
            )
            assert st_del_a == 200 and sess_def.rev > rev_before_del
            assert sess_def.whiteboard.get("session_attachments") == []
            assert any(b"event: attachment_deleted" in pkt for _, pkt in sess_def.event_ring)

            # 验证 pick-folder 区分用户取消 (200 cancelled=True) 与平台异常 (500 cancelled=False) 及绑定作用域分离
            with patch.object(AsyncHTTPServer, "_pick_system_folder_sync", return_value=("", True, "")):
                st_p_cancel, _, d_p_cancel = await mem_json(
                    app, tok, "POST", "/api/system/pick-folder", {"bind_scope": "default_only"}
                )
                assert st_p_cancel == 200 and d_p_cancel.get("cancelled") is True

            with patch.object(AsyncHTTPServer, "_pick_system_folder_sync", return_value=("", False, "STA PowerShell dialog failed")):
                st_p_err, _, d_p_err = await mem_json(
                    app, tok, "POST", "/api/system/pick-folder", {"bind_scope": "default_only"}
                )
                assert st_p_err == 500 and d_p_err.get("cancelled") is False and "STA PowerShell" in d_p_err.get("error", "")

            with patch.object(AsyncHTTPServer, "_pick_system_folder_sync", return_value=(str(ws_a), False, "")):
                # default_only 仅改默认工作区，不改当前绑定在 ws_b 的 sid_default
                st_p_def, _, d_p_def = await mem_json(
                    app, tok, "POST", "/api/system/pick-folder", {"bind_scope": "default_only"}
                )
                assert st_p_def == 200 and d_p_def.get("bind_scope") == "default_only"
                assert os.path.realpath(sess_def.workspace_dir) == os.path.realpath(str(ws_b))

                # session 作用域精准切换目标会话工作区
                st_p_sess, _, d_p_sess = await mem_json(
                    app, tok, "POST", "/api/system/pick-folder", {"bind_scope": "session", "session_id": sid_default}
                )
                assert st_p_sess == 200 and os.path.realpath(sess_def.workspace_dir) == os.path.realpath(str(ws_a))

            # 单元测试 windows_support.pick_folder_sta 的取消与异常区分逻辑
            with patch("shutil.which", return_value="powershell.exe"):
                with patch("subprocess.run", return_value=subprocess.CompletedProcess(["powershell.exe"], 0, b"CANCELLED\r\n", b"")):
                    p_sel, p_can, p_err = windows_support.pick_folder_sta("测试取消")
                    assert p_sel == "" and p_can is True and p_err == ""
                with patch("subprocess.run", return_value=subprocess.CompletedProcess(["powershell.exe"], 1, b"", b"ApartmentState error")):
                    p_sel2, p_can2, p_err2 = windows_support.pick_folder_sta("测试失败")
                    assert p_sel2 == "" and p_can2 is False and "ApartmentState" in p_err2
                with patch("subprocess.run", return_value=subprocess.CompletedProcess(["powershell.exe"], 0, b"SELECTED:D:\\Projects\\Demo\\\r\n", b"")):
                    p_sel3, p_can3, p_err3 = windows_support.pick_folder_sta("测试成功")
                    assert p_sel3 == "D:\\Projects\\Demo" and p_can3 is False and p_err3 == ""

            ok("9. application/octet-stream 异步附件上传、加锁广播删除与 Windows/macOS 选目录取消 vs 异常分离")
        finally:
            await app.orchestrator.shutdown()

    print("\n" + "=" * 76, flush=True)
    print(f"✔ AI圆桌 全链路架构收敛与故障注入验收套件全部 {len(passed)}/9 大项 100% 通过！", flush=True)
    print("=" * 76, flush=True)


if __name__ == "__main__":
    asyncio.run(run_convergence_suite())
