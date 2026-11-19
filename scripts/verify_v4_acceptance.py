#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI圆桌 v4 — 多模态附件管线、灵动输入舱、配置降噪与 CLI 隔离挂载自动化验收套件 (verify_v4_acceptance.py)

覆盖 10 大实机验收项：
1. 前端 v4 静态资源与关键 DOM 契约（index.html / v4_ui.css / v4_ui.js 全部 HTTP 200，保留全部兼容 ID 并挂载胶囊输入舱与三分导航）
2. 附件控制面鉴权红线（未携带 X-Roundtable-Token 前置 401，URL Query 传 token 拦截 401）
3. 分级请求体限额红线（POST /api/config >1MiB 依然前置拦截 413；已鉴权 POST /attachments 放行 1.3MiB 高清图并拦截 >16MiB 载荷 413）
4. 纯标准库 PNG 魔数与像素尺寸解析 + 工作区零污染（640x360 PNG 解析精确、0o600 落盘于 ~/.ai-roundtable/attachments/<sid>/，绑定项目目录零新增文件）
5. 伪造扩展名恶意二进制拦截（将 ELF 二进制伪装成 .png 上传立即 400 拒绝）
6. 代码/日志附件行号解析、SHA-256 同内容幂等去重与安全二进制流读取（CSP 沙箱响应头校验）
7. 多模态圆桌开局与 CLI 沙箱挂载闭环（纯附件免填字开局 -> 席位 TMPDIR/rt_attachments/ 真实可读 + Codex --image 注入）
8. 研讨中途追问补充附件（POST /followup 携带新 Markdown 附件并自动合入会话上下文）
9. 单个附件删除与会话级联清理（DELETE 附件与 DELETE 会话均彻底清理磁盘文件，零残留）
10. CAS 写盘快照零干扰验证（挂载多模态附件后执行写入工作区与一键原子回滚 100% 字节级还原）
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import socket
import stat
import struct
import sys
import tempfile
import textwrap
import zlib
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def build_valid_png(width: int, height: int, pad_bytes: int = 0) -> bytes:
    """用纯标准库构造合法的指定宽高 PNG 图像字节流。"""
    def _chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    # 每行均有完整 RGB 像素，确实可解码为 IHDR 声明的尺寸。
    raw_rows = (b"\x00" + b"\x4f\x46\xe5" * width) * height
    idat_payload = zlib.compress(raw_rows)
    chunks = [b"\x89PNG\r\n\x1a\n", _chunk(b"IHDR", ihdr)]
    if pad_bytes > 0:
        # 附加私有辅助注释块模拟大图体积（完全符合 PNG 规范且保持 IHDR 真实尺寸）
        chunks.append(_chunk(b"tEXt", b"Comment\x00" + (b"A" * pad_bytes)))
    chunks.append(_chunk(b"IDAT", idat_payload))
    chunks.append(_chunk(b"IEND", b""))
    return b"".join(chunks)


async def raw_http_request(
    port: int,
    method: str,
    target: str,
    *,
    headers: Optional[Dict[str, str]] = None,
    body: bytes = b"",
) -> Tuple[int, Dict[str, str], bytes]:
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    try:
        hdrs = {"Host": f"127.0.0.1:{port}", **(headers or {})}
        if body and "Content-Length" not in hdrs and "content-length" not in hdrs:
            hdrs["Content-Length"] = str(len(body))
        lines = [f"{method} {target} HTTP/1.1"]
        for k, v in hdrs.items():
            lines.append(f"{k}: {v}")
        head_bytes = ("\r\n".join(lines) + "\r\n\r\n").encode("latin-1")
        writer.write(head_bytes + body)
        await writer.drain()

        status_line = await asyncio.wait_for(reader.readline(), timeout=15.0)
        if not status_line:
            raise RuntimeError("Empty HTTP response")
        status_code = int(status_line.decode("latin-1").strip().split(" ", 2)[1])
        resp_headers: Dict[str, str] = {}
        while True:
            hl = await asyncio.wait_for(reader.readline(), timeout=15.0)
            if not hl or hl in (b"\r\n", b"\n"):
                break
            k, v = hl.decode("latin-1").rstrip("\r\n").split(":", 1)
            resp_headers[k.strip().lower()] = v.strip()
        cl = int(resp_headers.get("content-length", "0"))
        resp_body = await asyncio.wait_for(reader.readexactly(cl), timeout=15.0) if cl > 0 else b""
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


async def run_v4_suite() -> None:
    passed: List[str] = []

    def ok(label: str, detail: str = "") -> None:
        suf = f" ({detail})" if detail else ""
        print(f"  [PASS] {label}{suf}", flush=True)
        passed.append(label)

    with tempfile.TemporaryDirectory(prefix="ai_rt_v4_verify_") as tmp_str:
        tmp_root = Path(tmp_str).resolve()
        rt_home = tmp_root / "rt_home"
        rt_home.mkdir(parents=True, exist_ok=True)
        os.environ["AI_ROUNDTABLE_HOME"] = str(rt_home)
        os.environ["AI_ROUNDTABLE_FAST_TEST"] = "1"

        proj_dir = tmp_root / "bound_project"
        proj_dir.mkdir(parents=True, exist_ok=True)
        (proj_dir / "main.py").write_text("APP_VERSION = '3.0'\n", encoding="utf-8")

        # 构造可检验 TMPDIR/rt_attachments 隔离挂载与 Codex --image 参数的 Mock CLI
        mock_bin_dir = tmp_root / "mock_bins"
        mock_bin_dir.mkdir(parents=True, exist_ok=True)
        mock_codex = make_executable(
            mock_bin_dir / "mock_codex_v4",
            """
            #!/usr/bin/env python3
            import json, os, sys
            args = sys.argv[1:]
            if "--version" in args:
                print("codex-mock 4.0.0")
                sys.exit(0)
            if "--help" in args:
                print("Usage: codex exec --json --sandbox --image <FILE> -m <MODEL>")
                sys.exit(0)
            prompt = sys.stdin.read()
            tmpdir = os.environ.get("TMPDIR", "")
            stage_dir = os.path.join(tmpdir, "rt_attachments")
            staged_files = sorted(os.listdir(stage_dir)) if os.path.isdir(stage_dir) else []
            has_img_flag = "--image" in args
            if "写入本地项目工作区" in prompt:
                target_py = os.path.join(os.getcwd(), "main.py")
                if os.path.isfile(target_py):
                    with open(target_py, "w", encoding="utf-8") as wf:
                        wf.write("APP_VERSION = '4.0'\\n")
                msg = f"已完成工作区写入更新 (staged={','.join(staged_files)})"
                print(json.dumps({"type": "turn.started"}))
                print(json.dumps({"type": "item.completed", "item": {"id": "m1", "type": "agent_message", "text": msg}}))
                print(json.dumps({"type": "turn.completed"}))
                sys.exit(0)
            body = (
                f"已核验多模态附件：staged={staged_files} | img_flag={has_img_flag} | "
                f"has_dim={'640×360' in prompt}\\n"
                "[白板: 共识=多模态沙箱隔离挂载校验通过 | 任务=升级 main.py 版本号]\\n"
                "[状态: 审阅完成 | 共识: 已达成 | 点名: 无]"
            )
            print(json.dumps({"type": "thread.started", "thread_id": "tid_v4_1"}))
            print(json.dumps({"type": "item.completed", "item": {"id": "m1", "type": "agent_message", "text": body}}))
            print(json.dumps({"type": "turn.completed"}))
            """,
        )

        from backend.server import AsyncHTTPServer, MAX_HEADER_LINE_BYTES, MAX_REQUEST_LINE_BYTES

        port = find_free_port()
        token = "v4_secret_token_99887766"
        app = AsyncHTTPServer(
            host="127.0.0.1",
            port=port,
            workspace_dir=str(proj_dir),
            boot_token=token,
            boot_id="boot_v4_test",
        )
        server = await asyncio.start_server(
            app.handle_client,
            host="127.0.0.1",
            port=port,
            limit=max(MAX_REQUEST_LINE_BYTES, MAX_HEADER_LINE_BYTES) + 256,
        )
        auth_hdr = {"X-Roundtable-Token": token, "Content-Type": "application/json"}

        try:
            # 1. 静态资源与 v4 DOM 契约校验
            st_idx, _, idx_bytes = await raw_http_request(port, "GET", "/")
            st_css, _, css_bytes = await raw_http_request(port, "GET", "/v4_ui.css")
            st_js, _, js_bytes = await raw_http_request(port, "GET", "/v4_ui.js")
            assert st_idx == 200 and st_css == 200 and st_js == 200
            idx_html = idx_bytes.decode("utf-8")
            for must_id in (
                'id="v4AttachmentTray"',
                'id="v4PlusAttachBtn"',
                'id="v4ModeTriggerPill"',
                'id="v4LightboxModal"',
                'id="v4ModelChipsCarbon"',
                'id="v4EffortSegCarbon"',
                'id="settings-pane-seats"',
                'id="settings-pane-lineup"',
                'id="inlineModeSelect"',
                'src="/v4_ui.js"',
            ):
                assert must_id in idx_html, f"Missing DOM marker: {must_id}"
            assert len(css_bytes) > 5000 and len(js_bytes) > 8000
            ok("1. 前端 v4 胶囊输入舱、三分导航与专属图标静态资源校验")

            # 配置席位指向 Mock Codex CLI（单席快速验证）
            cfg_body = json.dumps(
                {
                    "workspace_dir": str(proj_dir),
                    "agents": {
                        "carbon": {"driver": "codex", "custom_binary": str(mock_codex), "model": "gpt-6-astra", "discussion_effort": "high"},
                        "grok": {"driver": "codex", "custom_binary": str(mock_codex), "model": "gpt-6-astra", "discussion_effort": "high"},
                        "astra": {"driver": "codex", "custom_binary": str(mock_codex), "model": "gpt-6-astra", "discussion_effort": "high"},
                    },
                }
            ).encode("utf-8")
            st_cfg, _, _ = await raw_http_request(port, "POST", "/api/config", headers=auth_hdr, body=cfg_body)
            assert st_cfg == 200

            # 新建测试会话
            st_new, _, new_b = await raw_http_request(
                port,
                "POST",
                "/api/sessions",
                headers=auth_hdr,
                body=json.dumps({"title": "v4多模态验收", "collab_mode": "rapid_consensus"}).encode("utf-8"),
            )
            assert st_new == 201
            sid = json.loads(new_b.decode("utf-8"))["session"]["session_id"]

            # 2. 鉴权红线校验
            st_unauth, _, _ = await raw_http_request(
                port,
                "POST",
                f"/api/sessions/{sid}/attachments",
                headers={"Content-Type": "application/json"},
                body=b'{"filename":"a.txt","data_base64":"YWJj"}',
            )
            assert st_unauth == 401
            ok("2. 附件上传端点无令牌前置 401 拦截")

            # 3. 分级请求体上限校验（/api/config >1MiB -> 413；/attachments 1.3MiB PNG -> 201；>16MiB -> 413）
            mib = 1024 * 1024
            st_limit_cfg, _, _ = await raw_http_request(
                port, "POST", "/api/config", headers=auth_hdr, body=b"{}".ljust(mib),
            )
            assert st_limit_cfg == 200
            st_413_cfg, _, _ = await raw_http_request(
                port,
                "POST",
                "/api/config",
                headers={**auth_hdr, "Content-Length": str(mib + 1)},
                body=b"",
            )
            assert st_413_cfg == 413

            big_png = build_valid_png(640, 360, pad_bytes=1_100_000)
            big_payload = json.dumps(
                {
                    "filename": "产品界面走查截图.png",
                    "mime_type": "image/png",
                    "data_base64": base64.b64encode(big_png).decode("ascii"),
                }
            ).encode("utf-8")
            assert len(big_payload) > 1 * 1024 * 1024
            st_up_img, _, up_img_b = await raw_http_request(
                port,
                "POST",
                f"/api/sessions/{sid}/attachments",
                headers=auth_hdr,
                body=big_payload,
            )
            assert st_up_img == 201, up_img_b.decode("utf-8", errors="replace")

            st_limit_att, _, at_limit = await raw_http_request(
                port, "POST", f"/api/sessions/{sid}/attachments", headers=auth_hdr,
                body=big_payload.ljust(16 * mib),
            )
            assert st_limit_att == 201 and json.loads(at_limit)["attachment"]["id"] == json.loads(up_img_b)["attachment"]["id"]
            st_413_att, _, _ = await raw_http_request(
                port,
                "POST",
                f"/api/sessions/{sid}/attachments",
                headers={**auth_hdr, "Content-Length": str(16 * mib + 1)},
                body=b"",
            )
            assert st_413_att == 413
            ok("3. 常规 1 MiB 与附件 16 MiB 请求体在上限放行、多一字节返回 413；实际上传 >1 MiB PNG")

            # 4. PNG 宽高像素解析、0o600 权限与工作区零污染校验
            saved_img = json.loads(up_img_b.decode("utf-8"))["attachment"]
            img_id = saved_img["id"]
            assert saved_img["kind"] == "image"
            assert saved_img["mime_type"] == "image/png"
            assert saved_img["width"] == 640 and saved_img["height"] == 360
            att_dir = rt_home / "attachments" / sid
            stored_files = [p for p in att_dir.iterdir() if p.name != "index.json"]
            assert len(stored_files) == 1
            file_mode = stat.S_IMODE(stored_files[0].stat().st_mode)
            assert file_mode == 0o600, f"Expected 0o600, got {oct(file_mode)}"
            assert [p.name for p in proj_dir.iterdir()] == ["main.py"]
            ok("4. 完整 640x360 PNG 尺寸解析、0o600 文件权限与项目工作区零污染")

            # 5. 伪造图片魔数的恶意 ELF 二进制拦截
            spoof_payload = json.dumps(
                {
                    "filename": "fake_screenshot.png",
                    "mime_type": "image/png",
                    "data_base64": base64.b64encode(b"\x7fELF\x02\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x02\x00").decode("ascii"),
                }
            ).encode("utf-8")
            st_spoof, _, _ = await raw_http_request(
                port,
                "POST",
                f"/api/sessions/{sid}/attachments",
                headers=auth_hdr,
                body=spoof_payload,
            )
            assert st_spoof == 400
            ok("5. 伪造扩展名二进制可执行载荷魔数拦截 (400)")

            # 6. 代码文件上传、SHA-256 去重与安全字节流下载（拒绝 URL ?token=）
            code_src = "def compute_delta(a: int, b: int) -> int:\n    return a - b\n"
            code_req = json.dumps(
                {
                    "filename": "delta_helper.py",
                    "mime_type": "text/x-python",
                    "data_base64": base64.b64encode(code_src.encode("utf-8")).decode("ascii"),
                }
            ).encode("utf-8")
            st_c1, _, c1_b = await raw_http_request(port, "POST", f"/api/sessions/{sid}/attachments", headers=auth_hdr, body=code_req)
            st_c2, _, c2_b = await raw_http_request(port, "POST", f"/api/sessions/{sid}/attachments", headers=auth_hdr, body=code_req)
            assert st_c1 == 201 and st_c2 == 201
            code_att = json.loads(c1_b.decode("utf-8"))["attachment"]
            code_att_dup = json.loads(c2_b.decode("utf-8"))["attachment"]
            assert code_att["id"] == code_att_dup["id"]
            assert code_att["kind"] == "code" and code_att["line_count"] == 2

            st_qtok, _, _ = await raw_http_request(
                port,
                "GET",
                f"/api/sessions/{sid}/attachments/{img_id}/raw?token={token}",
            )
            assert st_qtok == 401
            st_raw, raw_hdrs, raw_img_out = await raw_http_request(
                port,
                "GET",
                f"/api/sessions/{sid}/attachments/{img_id}/raw",
                headers={"X-Roundtable-Token": token},
            )
            assert st_raw == 200 and raw_img_out == big_png
            assert "sandbox" in raw_hdrs.get("content-security-policy", "")
            ok("6. 代码附件行号解析、SHA-256 幂等去重与安全流读取（拦截 Query Token）")

            # 7. 纯附件免填字启动研讨 + 席位隔离 TMPDIR/rt_attachments 挂载与 --image 参数验证
            start_req = json.dumps(
                {
                    "topic": "",
                    "collab_mode": "rapid_consensus",
                    "enabled_agents": ["astra"],
                    "attachment_ids": [img_id, code_att["id"]],
                }
            ).encode("utf-8")
            st_start, _, _ = await raw_http_request(
                port,
                "POST",
                f"/api/sessions/{sid}/start",
                headers=auth_hdr,
                body=start_req,
            )
            assert st_start == 200

            # 等待单席快速合议完成
            sess_snap = None
            for _ in range(60):
                await asyncio.sleep(0.1)
                _, _, sb = await raw_http_request(port, "GET", f"/api/sessions/{sid}", headers=auth_hdr)
                sess_snap = json.loads(sb.decode("utf-8"))["session"]
                if not sess_snap["is_busy"] and sess_snap["stage"] == "awaiting_chair":
                    break
            assert sess_snap is not None and not sess_snap["is_busy"]
            chair_msgs = [m for m in sess_snap["messages"] if m["speaker"] == "chair"]
            agent_msgs = [m for m in sess_snap["messages"] if m["speaker"] == "astra"]
            assert len(chair_msgs) == 1 and len(chair_msgs[0].get("attachments") or []) == 2
            assert len(agent_msgs) >= 1
            agent_reply = agent_msgs[-1]["content"]
            assert "img_flag=True" in agent_reply and "has_dim=True" in agent_reply and "delta_helper.py" in agent_reply, agent_reply
            ok("7. 多模态圆桌开局闭环（Chair 消息持久化附件 + 沙箱 rt_attachments 隔离挂载 + Codex --image）")

            # 8. 追问补充新附件合并校验
            doc_req = json.dumps(
                {
                    "filename": "release_notes.md",
                    "mime_type": "text/markdown",
                    "data_base64": base64.b64encode("# V4 Release\n- Multimodal ready\n".encode("utf-8")).decode("ascii"),
                }
            ).encode("utf-8")
            st_doc, _, doc_b = await raw_http_request(port, "POST", f"/api/sessions/{sid}/attachments", headers=auth_hdr, body=doc_req)
            assert st_doc == 201
            doc_id = json.loads(doc_b.decode("utf-8"))["attachment"]["id"]

            st_fu, _, _ = await raw_http_request(
                port,
                "POST",
                f"/api/sessions/{sid}/followup",
                headers=auth_hdr,
                body=json.dumps({"message": "", "attachment_ids": [doc_id]}).encode("utf-8"),
            )
            assert st_fu == 200
            for _ in range(60):
                await asyncio.sleep(0.1)
                _, _, sb = await raw_http_request(port, "GET", f"/api/sessions/{sid}", headers=auth_hdr)
                sess_snap = json.loads(sb.decode("utf-8"))["session"]
                if not sess_snap["is_busy"] and sess_snap["stage"] == "awaiting_chair":
                    break
            assert "release_notes.md" in sess_snap["messages"][-1]["content"]
            ok("8. 研讨中途追问补充附件自动合入会话上下文")

            # 9. CAS 写盘执行与一键原子回滚零干扰验证（v5 门禁适配：先断言零勾选 409，再勾选任务执行）
            st_ex_zero, _, b_ex_zero = await raw_http_request(
                port,
                "POST",
                f"/api/sessions/{sid}/execute",
                headers=auth_hdr,
                body=json.dumps({"allow_workspace_write": True, "executor_id": "astra"}).encode("utf-8"),
            )
            assert st_ex_zero == 409 and "no_checked_tasks" in b_ex_zero.decode("utf-8", errors="replace"), (
                f"Expected 409 no_checked_tasks, got {st_ex_zero}: {b_ex_zero}"
            )
            cur_actions = [it for it in sess_snap["whiteboard"].get("items", []) if it.get("kind") == "action"]
            if not cur_actions:
                _, _, b_add_v4 = await raw_http_request(
                    port,
                    "POST",
                    f"/api/sessions/{sid}/whiteboard",
                    headers=auth_hdr,
                    body=json.dumps({"op": "add", "kind": "action", "author": "chair", "text": "升级 main.py 版本号"}).encode("utf-8"),
                )
                cur_actions = [it for it in json.loads(b_add_v4.decode("utf-8"))["whiteboard"]["items"] if it.get("kind") == "action"]
            _, _, b_chk_v4 = await raw_http_request(
                port,
                "POST",
                f"/api/sessions/{sid}/whiteboard",
                headers=auth_hdr,
                body=json.dumps({"op": "toggle_check", "item_id": cur_actions[0]["id"], "checked": True}).encode("utf-8"),
            )
            wb_chk_v4 = json.loads(b_chk_v4.decode("utf-8"))["whiteboard"]
            st_ex, _, _ = await raw_http_request(
                port,
                "POST",
                f"/api/sessions/{sid}/execute",
                headers=auth_hdr,
                body=json.dumps(
                    {
                        "allow_workspace_write": True,
                        "executor_id": "astra",
                        "expected_wb_version": wb_chk_v4["wb_version"],
                        "checked_action_ids": [cur_actions[0]["id"]],
                        "expected_workspace_dir": str(proj_dir),
                        "acknowledged_absent_agents": [],
                    }
                ).encode("utf-8"),
            )
            assert st_ex == 202
            for _ in range(60):
                await asyncio.sleep(0.1)
                _, _, sb = await raw_http_request(port, "GET", f"/api/sessions/{sid}", headers=auth_hdr)
                sess_snap = json.loads(sb.decode("utf-8"))["session"]
                if not sess_snap["is_busy"] and sess_snap["exec_state"] == "idle":
                    break
            assert (proj_dir / "main.py").read_text(encoding="utf-8") == "APP_VERSION = '4.0'\n"
            assert sess_snap["whiteboard"]["can_rollback"] is True

            st_rb, _, _ = await raw_http_request(
                port,
                "POST",
                f"/api/sessions/{sid}/rollback",
                headers=auth_hdr,
                body=b"{}",
            )
            assert st_rb == 200
            assert (proj_dir / "main.py").read_text(encoding="utf-8") == "APP_VERSION = '3.0'\n"
            ok("9. 多模态附件与无 Git CAS 写前快照及一键原子回滚 100% 兼容")

            # 10. 单个附件删除与会话删除级联清理磁盘目录
            st_del_att, _, _ = await raw_http_request(
                port,
                "DELETE",
                f"/api/sessions/{sid}/attachments/{doc_id}",
                headers={"X-Roundtable-Token": token},
            )
            assert st_del_att == 200
            st_del_sess, _, _ = await raw_http_request(
                port,
                "DELETE",
                f"/api/sessions/{sid}",
                headers={"X-Roundtable-Token": token},
            )
            assert st_del_sess == 200
            assert not att_dir.exists()
            ok("10. 附件删除与会话级联清理（磁盘零残留）")

        finally:
            server.close()
            await server.wait_closed()
            await app.orchestrator.shutdown()

    print(f"\n✔ AI圆桌 v4 全部 {len(passed)}/10 项多模态与交互升级自动化验收 100% 通过！", flush=True)


if __name__ == "__main__":
    asyncio.run(run_v4_suite())
