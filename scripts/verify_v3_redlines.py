#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI圆桌 v3 — 全链路架构裁定红线与交互能力自动化验收套件 (verify_v3_redlines.py)

覆盖验证矩阵：
1. 控制面协议前置防线（414 超长请求行 / 431 超多请求头 / 413 >1MiB / 403 非法 Host 与跨源 Origin / 零 CORS）
2. 双模式凭据闭环（无令牌 401 / URL Query 令牌 401 / #bootstrap 一次性核销与重放拦截 401）
3. 高危旁路清零（pick-folder 禁传 direct_path 400 / workspace 禁指 ~/.ai-roundtable 400 / export 禁写盘 400 & 内存流下载 200 / allow_workspace_write 严格布尔 400）
4. 无 Git 纯标准库 CAS 字节清单（含已跟踪 + .gitignore 忽略文件 + 嵌套子目录 100% 字节级还原 / 越界软链写前 409 零副作用）
5. 单飞预约与跨会话非阻塞 flock(LOCK_NB) 互斥 + 事后手动编辑冲突 409 全量 conflict_paths 原子拒绝 + 崩溃中断 recovery_required 哈希确认恢复
6. Pipe-EOF 孤儿进程组自毁围栏（父管道断开后子孙进程组立即消亡）
7. 超时残稿清零（>=80 字符输出后超时绝不吞异常、白板零污染）+ 八项合取门禁 + 软链同源二进制禁升 decision
8. SSE 单调 rev 断线重连与多字节 UTF-8 中文流无损拼接
9. SQLite 单写线程持久化与旧 sessions.json 幂等迁移 + 6 席单 CLI 独立 TMPDIR 真并行加速比 + 执行后自动验证钩子
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import textwrap
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


async def raw_http_request(
    port: int,
    method: str,
    target: str,
    *,
    headers: Optional[Dict[str, str]] = None,
    body: bytes = b"",
    raw_override: Optional[bytes] = None,
) -> Tuple[int, Dict[str, str], bytes]:
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    try:
        if raw_override is not None:
            writer.write(raw_override)
        else:
            hdrs = {"Host": f"127.0.0.1:{port}", **(headers or {})}
            if body and "Content-Length" not in hdrs and "content-length" not in hdrs:
                hdrs["Content-Length"] = str(len(body))
            lines = [f"{method} {target} HTTP/1.1"]
            for k, v in hdrs.items():
                lines.append(f"{k}: {v}")
            head_bytes = ("\r\n".join(lines) + "\r\n\r\n").encode("latin-1")
            writer.write(head_bytes + body)
        await writer.drain()

        status_line = await asyncio.wait_for(reader.readline(), timeout=10.0)
        if not status_line:
            raise RuntimeError("Empty HTTP response")
        parts = status_line.decode("latin-1").strip().split(" ", 2)
        status_code = int(parts[1])
        resp_headers: Dict[str, str] = {}
        while True:
            hl = await asyncio.wait_for(reader.readline(), timeout=10.0)
            if not hl or hl in (b"\r\n", b"\n"):
                break
            k, v = hl.decode("latin-1").rstrip("\r\n").split(":", 1)
            resp_headers[k.strip().lower()] = v.strip()
        cl = int(resp_headers.get("content-length", "0"))
        resp_body = await asyncio.wait_for(reader.readexactly(cl), timeout=10.0) if cl > 0 else b""
        return status_code, resp_headers, resp_body
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass


def make_executable(path: Path, content: str) -> Path:
    path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


async def run_all_tests() -> None:
    passed: List[str] = []

    def record_ok(name: str, detail: str = "") -> None:
        suffix = f" ({detail})" if detail else ""
        print(f"  [PASS] {name}{suffix}", flush=True)
        passed.append(name)

    with tempfile.TemporaryDirectory(prefix="ai_rt_v3_verify_") as tmp_root_str:
        tmp_root = Path(tmp_root_str).resolve()
        rt_home = tmp_root / "rt_home"
        rt_home.mkdir(parents=True, exist_ok=True)
        os.environ["AI_ROUNDTABLE_HOME"] = str(rt_home)
        os.environ["AI_ROUNDTABLE_FAST_TEST"] = "1"

        # 预置旧版 sessions.json 测试 SQLite 首次启动幂等迁移
        legacy_data_dir = rt_home / "data"
        legacy_data_dir.mkdir(parents=True, exist_ok=True)
        legacy_ws = tmp_root / "proj_alpha"
        legacy_ws.mkdir(parents=True, exist_ok=True)
        (legacy_ws / "app.py").write_text("print('v1')\n", encoding="utf-8")
        (legacy_ws / ".gitignore").write_text(".env.local\n", encoding="utf-8")
        (legacy_ws / ".env.local").write_text("SECRET_KEY=alpha_123\n", encoding="utf-8")
        sub_dir = legacy_ws / "vendor_sub"
        sub_dir.mkdir()
        (sub_dir / "lib.py").write_text("VAL = 42\n", encoding="utf-8")

        legacy_sessions_file = legacy_data_dir / "sessions.json"
        legacy_sessions_file.write_text(
            json.dumps(
                {
                    "sessions": [
                        {
                            "session_id": "legacy01",
                            "title": "历史迁移议题",
                            "created_at": "10:00:00",
                            "stage": "awaiting_chair",
                            "topic": "验证 SQLite 幂等迁移",
                            "collab_mode": "deep_deliberation",
                            "workspace_dir": str(legacy_ws),
                            "workspace_bound": True,
                            "enabled_agents": ["carbon", "grok", "astra"],
                            "messages": [
                                {
                                    "id": "m_leg_1",
                                    "speaker": "chair",
                                    "speaker_name": "主持人",
                                    "role_title": "会议主席",
                                    "content": "验证旧会话迁移完整性",
                                    "phase_label": "议题发起",
                                    "timestamp": "10:00:01",
                                    "streaming": False,
                                }
                            ],
                            "whiteboard": {"topic": "验证 SQLite 幂等迁移", "items": []},
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        # 构造多模式模拟 CLI 可执行脚本（支持连通探活、并发 TMPDIR 回显、慢速超时残稿、工作区写盘）
        mock_cli = make_executable(
            tmp_root / "mock_agy",
            """\
            #!/usr/bin/env python3
            import os, sys, time
            from pathlib import Path

            args = sys.argv[1:]
            if "--version" in args:
                print("mock-agy 3.0.0")
                sys.exit(0)
            prompt = " ".join(args)
            if "仅回复 OK" in prompt or "连通性探针" in prompt or prompt.strip() == "Reply with OK only.":
                print("OK")
                sys.exit(0)

            mode = os.environ.get("MOCK_CLI_MODE", "normal")
            if mode == "timeout_after_90_chars":
                # 先输出超过 80 字符的正文 + 伪造白板尾注，随后挂起触发空闲超时
                sys.stdout.write("这是一段超过八十个字符的残缺推演输出，用于严格验证超时后绝不会吞掉异常也不会把截断尾注写入会议白板！" * 2 + "\\n")
                sys.stdout.write("[白板要点]\\n- 共识：这条伪造共识绝不允许进入白板\\n")
                sys.stdout.flush()
                time.sleep(10.0)
                sys.exit(0)

            if mode == "parallel_bench":
                td = os.environ.get("TMPDIR", "")
                Path(td).mkdir(parents=True, exist_ok=True)
                marker = Path(td) / "slot.lock"
                marker.write_text(str(os.getpid()), encoding="utf-8")
                time.sleep(0.32)
                print(f"并行通道完成 TMPDIR={td}\\n\\n[白板要点]\\n- 风险：需关注锁粒度边界\\n- 行动：补充并发压测用例")
                sys.exit(0)

            if mode == "exec_write":
                hold_sec = float(os.environ.get("MOCK_EXEC_HOLD_SEC", "0.05"))
                cwd = Path.cwd()
                (cwd / "app.py").write_text("print('v2_modified_by_exec')\\n", encoding="utf-8")
                if (cwd / ".env.local").exists():
                    (cwd / ".env.local").unlink()
                (cwd / "generated_feature.py").write_text("FEATURE = True\\n", encoding="utf-8")
                print("正在应用工作区修改…", flush=True)
                time.sleep(hold_sec)
                print("已完成代码修改与自检。", flush=True)
                sys.exit(0)

            if mode == "stream_utf8":
                chunks = [
                    "第一段中文流式推演：验证跨分片 UTF-8 编码完整性与 ",
                    "since_rev 断线无损续传能力，包含复杂符号 🚀✨ 与架构锚点。",
                    "\\n\\n[白板要点]\\n- 共识：统一采用 fetch 流式鉴权通道\\n- 风险：单驱动场景不得自动升格共识\\n- 行动：核验断线重连零丢字",
                ]
                for c in chunks:
                    sys.stdout.write(c)
                    sys.stdout.flush()
                    time.sleep(0.12)
                sys.exit(0)

            print("常规模拟发言输出。\\n\\n[白板要点]\\n- 风险：常规边界提示")
            """,
        )

        # 创建同源软链接验证 realpath 驱动族去重
        mock_cli_symlink = tmp_root / "mock_grok_symlink"
        mock_cli_symlink.symlink_to(mock_cli)

        from backend.server import AsyncHTTPServer
        from backend.drivers.process_watchdog import is_process_group_alive, spawn_supervised_cli

        port = find_free_port()
        boot_code = "once_bootstrap_secret_998877"
        app = AsyncHTTPServer(
            host="127.0.0.1",
            port=port,
            workspace_dir=str(legacy_ws),
            boot_token="unit_test_boot_token_64hex_abcdef1234567890",
            boot_id="boot_v3_verify",
            bootstrap_code=boot_code,
        )
        srv = await asyncio.start_server(app.handle_client, "127.0.0.1", port, limit=16384)

        try:
            # ---------------- 1. 协议与鉴权防线测试 ----------------
            st, hdrs, _ = await raw_http_request(
                port, "GET", "/api/status", headers={"Host": f"evil.attacker.com:{port}"}
            )
            assert st == 403, f"Expected 403 on bad Host, got {st}"
            assert "access-control-allow-origin" not in hdrs
            record_ok("1.1 Host 端口精确校验与零 CORS 响应头", "伪造 Host 返回 403 且无 CORS 头")

            st, _, _ = await raw_http_request(
                port, "GET", "/api/status", headers={"Origin": "http://127.0.0.1:9999"}
            )
            assert st == 403, f"Expected 403 on cross-origin, got {st}"
            st_opt, _, _ = await raw_http_request(port, "OPTIONS", "/api/status")
            assert st_opt == 405
            record_ok("1.2 跨源 Origin 拦截与 OPTIONS 禁用", "跨源 403 / OPTIONS 405")

            long_uri = "/api/" + ("a" * 4500)
            st_414, _, _ = await raw_http_request(port, "GET", long_uri)
            assert st_414 == 414, f"Expected 414, got {st_414}"

            many_hdrs = {f"X-Pad-{i}": "1" for i in range(66)}
            st_431, _, _ = await raw_http_request(port, "GET", "/api/status", headers=many_hdrs)
            assert st_431 == 431, f"Expected 431, got {st_431}"

            st_413, _, _ = await raw_http_request(
                port,
                "POST",
                "/api/config",
                headers={"Content-Length": str(2 * 1024 * 1024), "X-Roundtable-Token": app.boot_token},
                raw_override=(
                    f"POST /api/config HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n"
                    f"Content-Length: {2 * 1024 * 1024}\r\n\r\n"
                ).encode("latin-1"),
            )
            assert st_413 == 413, f"Expected 413 before body read, got {st_413}"
            record_ok("1.3 协议前置限额防线", "414 超长请求行 / 431 超多请求头 / 413 超 1MiB 载荷前置拒绝")

            st_trav, _, _ = await raw_http_request(port, "GET", "/../backend/server.py")
            assert st_trav == 404
            st_no_tok, _, _ = await raw_http_request(port, "GET", "/api/status")
            assert st_no_tok == 401
            st_q_tok, _, _ = await raw_http_request(port, "GET", f"/api/status?token={app.boot_token}")
            assert st_q_tok == 401
            record_ok("1.4 静态路径越界防护与无令牌/URL查询串令牌拦截", "越界 404 / 缺头或带 ?token 均 401")

            st_boot1, _, b_boot1 = await raw_http_request(
                port,
                "POST",
                "/api/auth/bootstrap",
                headers={"Content-Type": "application/json"},
                body=json.dumps({"code": boot_code}).encode("utf-8"),
            )
            assert st_boot1 == 200
            redeemed = json.loads(b_boot1.decode("utf-8"))
            assert redeemed["token"] == app.boot_token and redeemed["boot_id"] == "boot_v3_verify"

            st_boot2, _, _ = await raw_http_request(
                port,
                "POST",
                "/api/auth/bootstrap",
                headers={"Content-Type": "application/json"},
                body=json.dumps({"code": boot_code}).encode("utf-8"),
            )
            assert st_boot2 == 401, f"Bootstrap replay must return 401, got {st_boot2}"
            record_ok("1.5 #bootstrap 引导码单次核销与重放拒绝", "首次 200 换取内存令牌，二次重放 401")

            auth_hdr = {"X-Roundtable-Token": app.boot_token, "Content-Type": "application/json"}

            # 验证 SQLite 历史迁移
            st_st, _, b_st = await raw_http_request(port, "GET", "/api/status", headers=auth_hdr)
            assert st_st == 200
            status_json = json.loads(b_st.decode("utf-8"))
            migrated_ids = [s["session_id"] for s in status_json["sessions"]]
            assert "legacy01" in migrated_ids
            assert (rt_home / "state.sqlite3").is_file()
            record_ok("2.1 SQLite 单写线程存储引擎与旧 sessions.json 幂等迁移", "state.sqlite3 已就绪且历史会话完整保留")

            # ---------------- 2. 高危旁路收口测试 ----------------
            st_pf, _, _ = await raw_http_request(
                port,
                "POST",
                "/api/system/pick-folder",
                headers=auth_hdr,
                body=json.dumps({"direct_path": str(legacy_ws)}).encode("utf-8"),
            )
            assert st_pf == 400
            st_ws_bad, _, _ = await raw_http_request(
                port,
                "POST",
                "/api/sessions/legacy01/workspace",
                headers=auth_hdr,
                body=json.dumps({"workspace_dir": str(rt_home)}).encode("utf-8"),
            )
            assert st_ws_bad == 400
            st_exp_bad, _, _ = await raw_http_request(
                port,
                "POST",
                "/api/sessions/legacy01/export",
                headers=auth_hdr,
                body=json.dumps({"markdown": "# Arbitrary write attempt"}).encode("utf-8"),
            )
            assert st_exp_bad == 400
            st_exp_ok, exp_hdrs, exp_bytes = await raw_http_request(
                port, "GET", "/api/sessions/legacy01/export", headers=auth_hdr
            )
            assert st_exp_ok == 200 and "验证旧会话迁移完整性" in exp_bytes.decode("utf-8")
            assert "content-disposition" in exp_hdrs
            st_bool_bad, _, _ = await raw_http_request(
                port,
                "POST",
                "/api/sessions/legacy01/execute",
                headers=auth_hdr,
                body=json.dumps({"allow_workspace_write": "true"}).encode("utf-8"),
            )
            assert st_bool_bad == 400
            record_ok("2.2 高危旁路清零核验", "pick-folder 禁 direct_path / 禁绑私有目录 / export 纯内存流下载 / allow_workspace_write 强布尔校验")

            # 配置 6 席全部绑定模拟 CLI（其中 grok 指向同源软链以测试驱动族归一化）
            agents_patch = {
                aid: {
                    "driver": "agy",
                    "custom_binary": str(mock_cli_symlink if aid == "grok" else mock_cli),
                    "model": "gemini-4-carbon",
                    "discussion_effort": "high",
                    "execution_effort": "high",
                }
                for aid in ("carbon", "grok", "astra", "vega", "titan", "prism")
            }
            st_cfg, _, _ = await raw_http_request(
                port,
                "POST",
                "/api/config",
                headers=auth_hdr,
                body=json.dumps(
                    {
                        "single_cli_concurrency": 6,
                        "pacing_mode": "custom",
                        "idle_timeout_sec": 1,
                        "turn_timeout_sec": 15,
                        "agents": agents_patch,
                    }
                ).encode("utf-8"),
            )
            assert st_cfg == 200

            # ---------------- 3. Pipe-EOF 孤儿进程组自毁围栏测试 ----------------
            sup_handle = await spawn_supervised_cli(
                [
                    sys.executable,
                    "-c",
                    "import subprocess, sys, time; subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']); time.sleep(60)",
                ],
                cwd=str(tmp_root),
                env=dict(os.environ),
                wait_release=True,
            )
            recorded_pgid = sup_handle.pgid
            assert recorded_pgid > 0
            sup_handle.release_gate()
            await asyncio.sleep(0.12)
            # 模拟父进程崩溃直接关闭生命线写端，不主动发送任何信号
            t_eof0 = time.monotonic()
            sup_handle.close_lifeline()
            await asyncio.wait_for(sup_handle.proc.wait(), timeout=2.0)
            for _ in range(30):
                if not is_process_group_alive(recorded_pgid):
                    break
                await asyncio.sleep(0.03)
            eof_ms = (time.monotonic() - t_eof0) * 1000
            assert not is_process_group_alive(recorded_pgid), f"Process group {recorded_pgid} survived Pipe-EOF!"
            record_ok("3.1 Pipe-EOF 孤儿进程组自毁围栏", f"父管道断开后进程组 pgid={recorded_pgid} 及其孙进程在 {eof_ms:.0f}ms 内消亡")

            # ---------------- 4. 越界符号链接写前 409 拦截（零字节与阶段污染） ----------------
            escape_link = legacy_ws / "escape_etc_hosts"
            escape_link.symlink_to("/etc/hosts")
            before_app_bytes = (legacy_ws / "app.py").read_bytes()
            st_sym, _, b_sym = await raw_http_request(
                port,
                "POST",
                "/api/sessions/legacy01/execute",
                headers=auth_hdr,
                body=json.dumps({"allow_workspace_write": True, "executor_id": "astra"}).encode("utf-8"),
            )
            assert st_sym == 409, f"Escaping symlink must fail with 409, got {st_sym}: {b_sym}"
            assert (legacy_ws / "app.py").read_bytes() == before_app_bytes
            sess_after_sym = app.orchestrator.get_session("legacy01")
            assert sess_after_sym.stage == "awaiting_chair" and sess_after_sym.exec_state == "idle"
            escape_link.unlink()
            record_ok("4.1 越界符号链接写前 409 原子拦截", "写前遍历检出越界软链立即返回 409，工作区字节与业务 stage 零变化")

            # ---------------- 5. 无 Git 纯标准库 CAS 快照、跨会话单飞 flock 互斥与 100% 字节级回滚 ----------------
            # 新建第二个会话绑定同一目录测试跨会话非阻塞 flock(LOCK_NB)
            _, _, b_s2 = await raw_http_request(
                port, "POST", "/api/sessions", headers=auth_hdr, body=json.dumps({"title": "并发写锁测试会话"}).encode("utf-8")
            )
            sid2 = json.loads(b_s2.decode("utf-8"))["session"]["session_id"]
            await raw_http_request(
                port,
                "POST",
                f"/api/sessions/{sid2}/workspace",
                headers=auth_hdr,
                body=json.dumps({"workspace_dir": str(legacy_ws)}).encode("utf-8"),
            )
            # 给会话 2 注入议题以便可执行
            app.orchestrator.get_session(sid2).topic = "并发冲突执行测试"

            orig_hashes = {
                "app.py": hashlib.sha256((legacy_ws / "app.py").read_bytes()).hexdigest(),
                ".env.local": hashlib.sha256((legacy_ws / ".env.local").read_bytes()).hexdigest(),
                "vendor_sub/lib.py": hashlib.sha256((legacy_ws / "vendor_sub" / "lib.py").read_bytes()).hexdigest(),
            }

            os.environ["MOCK_CLI_MODE"] = "exec_write"
            os.environ["MOCK_EXEC_HOLD_SEC"] = "0.55"
            st_ex1, _, b_ex1 = await raw_http_request(
                port,
                "POST",
                "/api/sessions/legacy01/execute",
                headers=auth_hdr,
                body=json.dumps({"allow_workspace_write": True, "executor_id": "astra"}).encode("utf-8"),
            )
            assert st_ex1 == 202, f"Expected 202 Accepted, got {st_ex1}: {b_ex1}"

            # 在 legacy01 持有工作区 flock 期间，sid2 并发请求写同一工作区必须非阻塞立即返回 409！
            t_lock0 = time.monotonic()
            st_ex2, _, b_ex2 = await raw_http_request(
                port,
                "POST",
                f"/api/sessions/{sid2}/execute",
                headers=auth_hdr,
                body=json.dumps({"allow_workspace_write": True, "executor_id": "astra"}).encode("utf-8"),
            )
            lock_reject_ms = (time.monotonic() - t_lock0) * 1000
            assert st_ex2 == 409 and lock_reject_ms < 450, f"Expected 409, got {st_ex2} in {lock_reject_ms:.1f}ms | ex1_logs={app.orchestrator.get_session('legacy01').whiteboard.get('exec_logs')} | ex1_msgs={app.orchestrator.get_session('legacy01').messages[-1:]}"
            record_ok("4.2 跨会话非阻塞 flock(LOCK_NB) 写互斥", f"并发写同一目录在 {lock_reject_ms:.1f}ms 内立即返回 409，峰值写者严格为 1")

            # 等待 legacy01 执行完成进入 rollbackable
            for _ in range(40):
                await asyncio.sleep(0.1)
                if not app.orchestrator.get_session("legacy01").is_busy:
                    break
            sess1 = app.orchestrator.get_session("legacy01")
            assert sess1.whiteboard["can_rollback"] is True, f"logs={sess1.whiteboard.get('exec_logs')}, rec={sess1.recovery_required}, busy={sess1.is_busy}, bkp={sess1.last_backup}"
            assert (legacy_ws / "generated_feature.py").exists()
            assert not (legacy_ws / ".env.local").exists()

            # 未确认上次快照前，再次发起写入执行必须返回 409
            st_unack, _, _ = await raw_http_request(
                port,
                "POST",
                "/api/sessions/legacy01/execute",
                headers=auth_hdr,
                body=json.dumps({"allow_workspace_write": True, "executor_id": "astra"}).encode("utf-8"),
            )
            assert st_unack == 409

            # 模拟用户在执行后手动修改了 generated_feature.py -> 回滚必须 409 原子拒绝并返回全量 conflict_paths
            (legacy_ws / "generated_feature.py").write_text("FEATURE = 'user_manual_edit'\n", encoding="utf-8")
            st_rb_conf, _, b_rb_conf = await raw_http_request(
                port, "POST", "/api/sessions/legacy01/rollback", headers=auth_hdr, body=b"{}"
            )
            rb_conf_json = json.loads(b_rb_conf.decode("utf-8"))
            assert st_rb_conf == 409
            assert "generated_feature.py" in rb_conf_json.get("conflict_paths", [])
            assert sess1.whiteboard["can_rollback"] is True, f"logs={sess1.whiteboard.get('exec_logs')}, rec={sess1.recovery_required}, busy={sess1.is_busy}, bkp={sess1.last_backup}"
            assert (legacy_ws / "generated_feature.py").read_text("utf-8") == "FEATURE = 'user_manual_edit'\n"
            record_ok("4.3 事后编辑冲突 409 全量原子拒绝", "检出手动修改文件返回 conflict_paths，零局部覆写且保留 rollbackable")

            # 用户还原手动编辑后执行原子回滚 -> 验证已跟踪文件、.gitignore 忽略文件 (.env.local) 与子目录 100% 字节级复原！
            (legacy_ws / "generated_feature.py").write_text("FEATURE = True\n", encoding="utf-8")
            st_rb_ok, _, _ = await raw_http_request(
                port, "POST", "/api/sessions/legacy01/rollback", headers=auth_hdr, body=b"{}"
            )
            assert st_rb_ok == 200
            assert not (legacy_ws / "generated_feature.py").exists()
            assert hashlib.sha256((legacy_ws / "app.py").read_bytes()).hexdigest() == orig_hashes["app.py"]
            assert hashlib.sha256((legacy_ws / ".env.local").read_bytes()).hexdigest() == orig_hashes[".env.local"]
            assert hashlib.sha256((legacy_ws / "vendor_sub" / "lib.py").read_bytes()).hexdigest() == orig_hashes["vendor_sub/lib.py"]
            record_ok("4.4 无 Git 纯标准库 CAS 字节级完整回滚", "已跟踪文件 + .gitignore 忽略文件 (.env.local) + 子目录 SHA-256 100% 复原")

            # ---------------- 6. 超时残稿清零（>=80 字符绝不吞异常、白板零污染） ----------------
            os.environ["MOCK_CLI_MODE"] = "timeout_after_90_chars"
            _, _, b_st_to = await raw_http_request(
                port, "POST", "/api/sessions", headers=auth_hdr, body=json.dumps({"title": "超时残稿门禁验证"}).encode("utf-8")
            )
            sid_to = json.loads(b_st_to.decode("utf-8"))["session"]["session_id"]
            await raw_http_request(
                port,
                "POST",
                f"/api/sessions/{sid_to}/start",
                headers=auth_hdr,
                body=json.dumps(
                    {
                        "topic": "测试超时后 >=80 字符残稿拦截",
                        "collab_mode": "rapid_consensus",
                        "enabled_agents": ["carbon"],
                    }
                ).encode("utf-8"),
            )
            for _ in range(60):
                await asyncio.sleep(0.15)
                s_to = app.orchestrator.get_session(sid_to)
                if not s_to.is_busy:
                    break
            s_to = app.orchestrator.get_session(sid_to)
            agent_msgs = [m for m in s_to.messages if m["speaker"] == "carbon"]
            assert agent_msgs and agent_msgs[-1].get("error") is True, "Timeout after >=80 chars MUST set error=True!"
            assert len(s_to.whiteboard.get("items", [])) == 0, f"Whiteboard polluted by timed-out turn: {s_to.whiteboard['items']}"
            record_ok("5.1 删除 80 字符吞超时分支与白板八项合取门禁", "输出 >120 字符后超时严格判败，截断尾注写入白板条目数为 0")

            # ---------------- 7. SSE 单调 rev 断线重连与软链同源驱动禁升 decision ----------------
            os.environ["MOCK_CLI_MODE"] = "stream_utf8"
            _, _, b_sse_sess = await raw_http_request(
                port, "POST", "/api/sessions", headers=auth_hdr, body=json.dumps({"title": "SSE 断线续传测试"}).encode("utf-8")
            )
            sid_sse = json.loads(b_sse_sess.decode("utf-8"))["session"]["session_id"]

            # 建立第一条 SSE 流，收到首帧 msg_delta 后主动模拟网络断线关闭 socket
            r1, w1 = await asyncio.open_connection("127.0.0.1", port)
            w1.write(
                (
                    f"GET /api/sessions/{sid_sse}/stream?since_rev=0&boot_id={app.boot_id} HTTP/1.1\r\n"
                    f"Host: 127.0.0.1:{port}\r\n"
                    f"X-Roundtable-Token: {app.boot_token}\r\n\r\n"
                ).encode("latin-1")
            )
            await w1.drain()
            # 读掉响应头
            while True:
                hl = await r1.readline()
                if hl in (b"\r\n", b"\n", b""):
                    break

            await raw_http_request(
                port,
                "POST",
                f"/api/sessions/{sid_sse}/start",
                headers=auth_hdr,
                body=json.dumps(
                    {
                        "topic": "测试 SSE 断线重连与软链同源驱动共识门禁",
                        "collab_mode": "rapid_consensus",
                        "enabled_agents": ["carbon", "grok"],  # grok 是指向 mock_cli 的软链，实际驱动族数 == 1！
                    }
                ).encode("utf-8"),
            )

            seen_rev = 0
            reconstructed: Dict[str, str] = {}
            cur_ev, cur_id, cur_data = "", "", []
            while True:
                ln = (await asyncio.wait_for(r1.readline(), timeout=5.0)).decode("utf-8").rstrip("\r\n")
                if ln == "":
                    if cur_data:
                        payload_obj = json.loads("\n".join(cur_data))
                        if cur_id:
                            seen_rev = max(seen_rev, int(cur_id))
                        if cur_ev == "msg_start":
                            reconstructed[payload_obj["id"]] = payload_obj.get("content", "")
                        elif cur_ev == "msg_delta":
                            reconstructed[payload_obj["id"]] = reconstructed.get(payload_obj["id"], "") + payload_obj.get("delta", "")
                            # 收到首个 delta 后立即强制断开第一条 SSE 连接！
                            break
                    cur_ev, cur_id, cur_data = "", "", []
                elif ln.startswith("event:"):
                    cur_ev = ln[6:].strip()
                elif ln.startswith("id:"):
                    cur_id = ln[3:].strip()
                elif ln.startswith("data:"):
                    cur_data.append(ln[5:].lstrip(" "))
            w1.close()

            # 等待服务端完成整轮流式生成
            for _ in range(50):
                await asyncio.sleep(0.1)
                if not app.orchestrator.get_session(sid_sse).is_busy:
                    break

            # 使用 since_rev 重连并回放遗漏帧
            r2, w2 = await asyncio.open_connection("127.0.0.1", port)
            w2.write(
                (
                    f"GET /api/sessions/{sid_sse}/stream?since_rev={seen_rev}&boot_id={app.boot_id} HTTP/1.1\r\n"
                    f"Host: 127.0.0.1:{port}\r\n"
                    f"X-Roundtable-Token: {app.boot_token}\r\n\r\n"
                ).encode("latin-1")
            )
            await w2.drain()
            while True:
                hl = await r2.readline()
                if hl in (b"\r\n", b"\n", b""):
                    break

            s_sse = app.orchestrator.get_session(sid_sse)
            target_rev = s_sse.rev
            cur_ev, cur_id, cur_data = "", "", []
            while seen_rev < target_rev:
                ln = (await asyncio.wait_for(r2.readline(), timeout=5.0)).decode("utf-8").rstrip("\r\n")
                if ln == "":
                    if cur_data:
                        payload_obj = json.loads("\n".join(cur_data))
                        num_id = int(cur_id or "0")
                        if num_id > seen_rev:
                            seen_rev = num_id
                            if cur_ev == "msg_start":
                                reconstructed[payload_obj["id"]] = payload_obj.get("content", "")
                            elif cur_ev == "msg_delta":
                                reconstructed[payload_obj["id"]] = reconstructed.get(payload_obj["id"], "") + payload_obj.get("delta", "")
                            elif cur_ev == "msg_done":
                                reconstructed[payload_obj["id"]] = payload_obj.get("content", "")
                    cur_ev, cur_id, cur_data = "", "", []
                elif ln.startswith("event:"):
                    cur_ev = ln[6:].strip()
                elif ln.startswith("id:"):
                    cur_id = ln[3:].strip()
                elif ln.startswith("data:"):
                    cur_data.append(ln[5:].lstrip(" "))
            w2.close()

            for m in s_sse.messages:
                if m["speaker"] in ("carbon", "grok"):
                    assert reconstructed.get(m["id"]) == m["content"], f"UTF-8 mismatch after SSE reconnect for {m['id']}"

            # 验证同源软链二进制 (realpath 相同 -> 实际驱动族 == 1 < 2) 严禁自动升格 decision！
            wb_decisions = [it for it in s_sse.whiteboard.get("items", []) if it.get("kind") == "decision"]
            assert len(wb_decisions) == 0, f"Single realpath driver family must NOT auto-promote decisions: {wb_decisions}"
            record_ok("5.2 SSE since_rev 断线无损续传与软链同源驱动禁升共识", "跨断线 UTF-8 字节 100% 一致，单驱动族自动升格 decision 数为 0")

            # ---------------- 8. 6 席单 CLI 独立 TMPDIR 真并行调用加速比验证 ----------------
            os.environ["MOCK_CLI_MODE"] = "parallel_bench"
            _, _, b_p6 = await raw_http_request(
                port, "POST", "/api/sessions", headers=auth_hdr, body=json.dumps({"title": "六席真并行验证"}).encode("utf-8")
            )
            sid_p6 = json.loads(b_p6.decode("utf-8"))["session"]["session_id"]
            t_p0 = time.monotonic()
            await raw_http_request(
                port,
                "POST",
                f"/api/sessions/{sid_p6}/start",
                headers=auth_hdr,
                body=json.dumps(
                    {
                        "topic": "验证 6 席独立 TMPDIR 真并行吞吐",
                        "collab_mode": "rapid_consensus",
                        "enabled_agents": ["carbon", "vega", "grok", "titan", "astra", "prism"],
                    }
                ).encode("utf-8"),
            )
            for _ in range(60):
                await asyncio.sleep(0.08)
                if not app.orchestrator.get_session(sid_p6).is_busy:
                    break
            wall_sec = time.monotonic() - t_p0
            s_p6 = app.orchestrator.get_session(sid_p6)
            p6_replies = [m["content"] for m in s_p6.messages if m["speaker"] in ("carbon", "vega", "grok", "titan", "astra", "prism")]
            tmpdirs = {
                ln.split("TMPDIR=", 1)[1].strip()
                for txt in p6_replies
                for ln in txt.splitlines()
                if "TMPDIR=" in ln
            }
            assert len(p6_replies) >= 6 and len(tmpdirs) == len(p6_replies), f"Expected 100% unique TMPDIRs per invocation, got {len(tmpdirs)} for {len(p6_replies)} replies"
            assert wall_sec < 1.65, f"Expected parallel wall time < 1.65s (serial would be >=1.92s+), got {wall_sec:.2f}s"
            record_ok("6.1 六席弹性阵容与单 CLI 6 路独立 TMPDIR 真并行", f"6 席全部完成，6 个独立隔离 TMPDIR，总耗时 {wall_sec:.2f}s")

            # ---------------- 9. 崩溃中断 (无 after 清单) 转 recovery_required 与哈希确认恢复 ----------------
            from backend.workspace_backup import WorkspaceBackup
            from backend.orchestrator import RoundtableOrchestrator

            crash_snap = WorkspaceBackup.capture(str(legacy_ws), session_id="legacy01", run_id="crashed_run_99", runtime_home=rt_home)
            # 模拟执行中途进程崩溃：修改了 app.py，同时用户在重启前手动新建了 user_notes.md，且未生成 after 清单
            (legacy_ws / "app.py").write_text("BROKEN_PARTIAL_WRITE\n", encoding="utf-8")
            user_precious = legacy_ws / "user_manual_note.md"
            user_precious.write_text("用户在重启前手动记录的重要笔记\n", encoding="utf-8")
            app.orchestrator.store.record_exec_recovery(
                session_id="legacy01",
                run_id="crashed_run_99",
                workspace_realpath=str(legacy_ws.resolve()),
                backup_dir=str(crash_snap.backup_dir),
                pgid=0,
                state="running",
                meta={"operation_id": "op_crash_99"},
            )

            # 模拟重启构建新 Orchestrator：严禁后台静默删除 user_manual_note.md！
            restarted_orch = RoundtableOrchestrator(
                workspace_dir=str(legacy_ws),
                boot_id="boot_after_crash",
                runtime_code_root=str(ROOT_DIR),
            )
            rec_sess = restarted_orch.get_session("legacy01")
            assert rec_sess.recovery_required is True
            assert user_precious.exists(), "Restart scan MUST NOT silently delete untracked user files!"

            plan = await restarted_orch.get_session_recovery_plan(rec_sess)
            assert any(it["path"] == "user_manual_note.md" for it in plan.get("untracked_new_files", []))

            # 哈希不匹配时拒绝恢复 (409)
            bad_code, _ = await restarted_orch.recover_session_workspace(
                rec_sess,
                expected_hashes={"user_manual_note.md": "0000_wrong_hash"},
                delete_confirmed_new_files=True,
            )
            assert bad_code == 409 and user_precious.exists()

            # 选择保留新增文件并恢复已跟踪破损文件 (200)
            ok_code, _ = await restarted_orch.recover_session_workspace(
                rec_sess,
                expected_hashes=plan["expected_hashes"],
                delete_confirmed_new_files=False,
            )
            assert ok_code == 200
            assert user_precious.exists()
            assert (legacy_ws / "app.py").read_text("utf-8") == "print('v1')\n"
            assert rec_sess.recovery_required is False
            await restarted_orch.shutdown()
            record_ok("6.2 崩溃中断 recovery_required 与显式哈希确认恢复", "重启零静默删文件，错哈希 409 拦截，确认后精准还原已跟踪文件并保留用户新增笔记")

        finally:
            srv.close()
            await srv.wait_closed()
            await app.orchestrator.shutdown()

    print("\n" + "=" * 72)
    print(f"ALL {len(passed)} V3 ARCHITECTURE REDLINE & UX SUITES PASSED!")
    print("=" * 72)


if __name__ == "__main__":
    asyncio.run(run_all_tests())
