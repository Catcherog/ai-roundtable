#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI圆桌 — 异步 HTTP + 流式 SSE 安全控制面服务端（v3 P0 全链路加固版）

核心安全防线：
1. 协议前置限额：请求行 <= 4 KiB，Header 行数 <= 64、单行 <= 8 KiB；Content-Length 严格非负十进制整数且 <= 1 MiB（超限前置 413）。
2. 同源与 Host 强校验：Host 头与监听 `host:port` 字节级精确匹配，非同源 Origin 一律 403，彻底移除全部 CORS 响应头与 500 堆栈回显。
3. 全链路 `X-Roundtable-Token` 内存鉴权：单点拦截全部 `/api/*`（含流式 SSE 与原生忙态探针），配合 Web 端 `#bootstrap` 单次兑换码核销。
4. 高危旁路收口：`pick-folder` 禁传 `direct_path` 且仅更新默认新建目录；会话切目录统一收口至 `/api/sessions/{sid}/workspace`；
   `export` 纯内存生成字节流响应不落服务端磁盘；`allow_workspace_write` 严格校验 JSON 布尔类型。
"""

from __future__ import annotations

import argparse
import asyncio
import hmac
import json
import mimetypes
import os
import secrets
import subprocess
import sys
import time
import traceback
import urllib.parse
from pathlib import Path
from typing import Dict, Optional, Tuple

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.orchestrator import (  # noqa: E402
    ExecutionAdmissionConflictError,
    RoundtableOrchestrator,
)

FRONTEND_DIR = (ROOT_DIR / "frontend").resolve()

MAX_REQUEST_LINE_BYTES = 4 * 1024       # 4 KiB
MAX_HEADER_LINE_BYTES = 8 * 1024        # 8 KiB
MAX_HEADER_COUNT = 64
MAX_BODY_BYTES = 1 * 1024 * 1024        # 1 MiB

HTTP_STATUS_TEXT = {
    200: "OK",
    201: "Created",
    202: "Accepted",
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    409: "Conflict",
    413: "Payload Too Large",
    414: "URI Too Long",
    431: "Request Header Fields Too Large",
    500: "Internal Server Error",
}


class _LineTooLongError(ValueError):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code


async def _read_bounded_line_fast(
    reader: asyncio.StreamReader,
    *,
    max_bytes: int,
    timeout: float,
    err_status: int,
) -> bytes:
    """高性能有界行读取：利用 readuntil('\\n') 并在 LimitOverrunError 时立即拒绝，绝不读入无限内存。"""
    try:
        line = await asyncio.wait_for(reader.readuntil(b"\n"), timeout=timeout)
    except asyncio.IncompleteReadError as inc:
        if len(inc.partial) > max_bytes:
            raise _LineTooLongError(err_status, "HTTP line exceeds limit") from inc
        return inc.partial
    except asyncio.LimitOverrunError as ovr:
        raise _LineTooLongError(err_status, "HTTP line exceeds stream limit") from ovr
    if len(line) > max_bytes:
        raise _LineTooLongError(err_status, "HTTP line exceeds limit")
    return line


class AsyncHTTPServer:
    def __init__(
        self,
        host: str,
        port: int,
        workspace_dir: str,
        *,
        boot_token: Optional[str] = None,
        boot_id: Optional[str] = None,
        bootstrap_code: Optional[str] = None,
    ) -> None:
        self.host = host
        self.port = int(port)
        self.expected_host_header = f"{self.host}:{self.port}"
        self.expected_origin = f"http://{self.host}:{self.port}"
        self.boot_id = (boot_id or os.environ.get("AI_ROUNDTABLE_BOOT_ID") or "").strip() or secrets.token_hex(16)
        self.boot_token = (boot_token or os.environ.get("AI_ROUNDTABLE_BOOT_TOKEN") or "").strip() or secrets.token_hex(32)
        self._bootstrap_code = (
            bootstrap_code if bootstrap_code is not None else os.environ.get("AI_ROUNDTABLE_BOOTSTRAP_CODE", "")
        ).strip()
        self._bootstrap_redeemed = False
        self.orchestrator = RoundtableOrchestrator(
            workspace_dir=workspace_dir,
            boot_id=self.boot_id,
            runtime_code_root=str(ROOT_DIR),
        )

    def _verify_token(self, headers: Dict[str, str]) -> bool:
        provided = headers.get("x-roundtable-token", "")
        if not provided or not self.boot_token:
            return False
        return hmac.compare_digest(provided.encode("utf-8"), self.boot_token.encode("utf-8"))

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            req_line = await _read_bounded_line_fast(
                reader,
                max_bytes=MAX_REQUEST_LINE_BYTES,
                timeout=15.0,
                err_status=414,
            )
            if not req_line:
                return
            req_str = req_line.decode("latin-1").rstrip("\r\n")
            parts = req_str.split(" ")
            if len(parts) != 3 or not parts[2].startswith("HTTP/1."):
                await self._send_json(writer, 400, {"error": "非法的 HTTP 请求行"})
                return
            method, raw_target = parts[0].upper(), parts[1]
            parsed = urllib.parse.urlparse(raw_target)
            path = urllib.parse.unquote(parsed.path)
            query_params = urllib.parse.parse_qs(parsed.query)

            headers: Dict[str, str] = {}
            header_count = 0
            duplicate_cl = False
            while True:
                hline = await _read_bounded_line_fast(
                    reader,
                    max_bytes=MAX_HEADER_LINE_BYTES,
                    timeout=10.0,
                    err_status=431,
                )
                if not hline or hline in (b"\r\n", b"\n"):
                    break
                header_count += 1
                if header_count > MAX_HEADER_COUNT:
                    await self._send_json(writer, 431, {"error": "请求头数量超出安全上限"})
                    return
                hstr = hline.decode("latin-1").rstrip("\r\n")
                if ":" not in hstr:
                    await self._send_json(writer, 400, {"error": "请求头格式非法"})
                    return
                k, v = hstr.split(":", 1)
                k_low = k.strip().lower()
                v_clean = v.strip()
                if k_low == "content-length" and "content-length" in headers and headers["content-length"] != v_clean:
                    duplicate_cl = True
                headers[k_low] = v_clean

            if duplicate_cl or "transfer-encoding" in headers:
                await self._send_json(writer, 400, {"error": "不支持冲突的 Content-Length 或分块传输编码"})
                return

            # 1. Host 请求头字节级精确匹配防 DNS Rebinding
            raw_host = headers.get("host", "")
            if raw_host != self.expected_host_header:
                await self._send_json(writer, 403, {"error": "非法的 Host 请求头"})
                return

            # 2. 跨源 Origin 防护（拒绝任何跨源预检或跨源请求）
            origin_hdr = headers.get("origin", "")
            if origin_hdr and origin_hdr != self.expected_origin:
                await self._send_json(writer, 403, {"error": "禁止跨源访问本地控制面"})
                return

            if method == "OPTIONS":
                await self._send_json(writer, 405, {"error": "已禁用 CORS 预检方法"})
                return

            # 3. Content-Length 仅接受非负十进制整数且 <= 1 MiB（在 readexactly 前直接返回 413）
            raw_cl = headers.get("content-length")
            content_len = 0
            if raw_cl is not None:
                if not raw_cl or not raw_cl.isascii() or not raw_cl.isdigit():
                    await self._send_json(writer, 400, {"error": "Content-Length 必须为非负十进制整数"})
                    return
                content_len = int(raw_cl)
                if content_len > MAX_BODY_BYTES:
                    await self._send_json(writer, 413, {"error": "请求体超过 1 MiB 上限"})
                    return

            body_bytes = b""
            if content_len > 0:
                body_bytes = await asyncio.wait_for(reader.readexactly(content_len), timeout=15.0)

            if path.startswith("/api/"):
                await self._route_api(method, path, query_params, headers, body_bytes, writer)
            else:
                if method not in ("GET", "HEAD"):
                    await self._send_json(writer, 405, {"error": "静态资源仅支持 GET/HEAD"})
                    return
                await self._serve_static(path, writer, head_only=(method == "HEAD"))
        except _LineTooLongError as line_err:
            try:
                await self._send_json(writer, line_err.status_code, {"error": "请求行或请求头超出长度限制"})
            except Exception:
                pass
        except (asyncio.TimeoutError, asyncio.IncompleteReadError, ConnectionResetError, BrokenPipeError):
            pass
        except Exception:
            traceback.print_exc(file=sys.stderr)
            try:
                await self._send_json(writer, 500, {"error": "内部服务处理异常"})
            except Exception:
                pass
        finally:
            try:
                if not writer.is_closing():
                    writer.close()
                    await writer.wait_closed()
            except Exception:
                pass

    @staticmethod
    def _parse_json_strict(body_bytes: bytes) -> Tuple[Optional[dict], Optional[str]]:
        if not body_bytes:
            return {}, None
        try:
            obj = json.loads(body_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None, "请求体不是合法的 UTF-8 JSON 对象"
        if not isinstance(obj, dict):
            return None, "请求体顶层必须为 JSON 对象"
        return obj, None

    async def _send_json(self, writer: asyncio.StreamWriter, status: int, payload: dict) -> None:
        status_text = HTTP_STATUS_TEXT.get(status, "OK")
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        head = (
            f"HTTP/1.1 {status} {status_text}\r\n"
            f"Content-Type: application/json; charset=utf-8\r\n"
            f"Content-Length: {len(body)}\r\n"
            f"Cache-Control: no-store\r\n"
            f"X-Content-Type-Options: nosniff\r\n"
            f"Connection: close\r\n\r\n"
        ).encode("utf-8")
        writer.write(head + body)
        await writer.drain()

    async def _send_bytes(
        self,
        writer: asyncio.StreamWriter,
        status: int,
        data: bytes,
        *,
        content_type: str,
        extra_headers: Optional[Dict[str, str]] = None,
        head_only: bool = False,
    ) -> None:
        status_text = HTTP_STATUS_TEXT.get(status, "OK")
        hdr_lines = [
            f"HTTP/1.1 {status} {status_text}",
            f"Content-Type: {content_type}",
            f"Content-Length: {len(data)}",
            "Cache-Control: no-cache",
            "X-Content-Type-Options: nosniff",
            "Connection: close",
        ]
        if extra_headers:
            for hk, hv in extra_headers.items():
                safe_v = str(hv).replace("\r", "").replace("\n", "")
                hdr_lines.append(f"{hk}: {safe_v}")
        head_bytes = ("\r\n".join(hdr_lines) + "\r\n\r\n").encode("utf-8")
        writer.write(head_bytes if head_only else (head_bytes + data))
        await writer.drain()

    async def _serve_static(self, path: str, writer: asyncio.StreamWriter, *, head_only: bool = False) -> None:
        if path in ("/ui_preview.html", "/ui-preview"):
            preview_file = (ROOT_DIR / "ui_preview.html").resolve()
            if preview_file.is_relative_to(ROOT_DIR.resolve()) and preview_file.is_file():
                await self._send_bytes(
                    writer,
                    200,
                    preview_file.read_bytes(),
                    content_type="text/html; charset=utf-8",
                    head_only=head_only,
                )
                return

        rel = "index.html" if path in ("", "/") else path.lstrip("/")
        target = (FRONTEND_DIR / rel).resolve()
        if not target.is_relative_to(FRONTEND_DIR) or not target.is_file():
            await self._send_json(writer, 404, {"error": "静态资源不存在"})
            return
        mime, _ = mimetypes.guess_type(str(target))
        ctype = mime or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json", "image/svg+xml"):
            ctype += "; charset=utf-8"
        await self._send_bytes(writer, 200, target.read_bytes(), content_type=ctype, head_only=head_only)

    @staticmethod
    def _pick_macos_folder_sync() -> str:
        if sys.platform != "darwin":
            return ""
        script = 'POSIX path of (choose folder with prompt "请选择 AI圆桌 新建会议默认绑定的项目工作区目录：")'
        try:
            res = subprocess.run(
                ["osascript", "-e", script],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=60.0,
            )
            if res.returncode == 0:
                chosen = res.stdout.decode("utf-8", errors="replace").strip()
                return chosen.rstrip("/") if chosen != "/" else chosen
            return ""
        except Exception:
            return ""

    async def _route_api(
        self,
        method: str,
        path: str,
        query_params: Dict[str, list],
        headers: Dict[str, str],
        body_bytes: bytes,
        writer: asyncio.StreamWriter,
    ) -> None:
        if method == "POST" and path == "/api/auth/bootstrap":
            data, jerr = self._parse_json_strict(body_bytes)
            if jerr is not None or data is None:
                await self._send_json(writer, 400, {"error": jerr or "参数错误"})
                return
            code = str(data.get("code") or "").strip()
            if (
                not code
                or not self._bootstrap_code
                or self._bootstrap_redeemed
                or not hmac.compare_digest(code.encode("utf-8"), self._bootstrap_code.encode("utf-8"))
            ):
                await self._send_json(writer, 401, {"error": "引导兑换码无效或已被单次核销"})
                return
            self._bootstrap_redeemed = True
            self._bootstrap_code = ""
            await self._send_json(
                writer,
                200,
                {
                    "ok": True,
                    "token": self.boot_token,
                    "boot_id": self.boot_id,
                },
            )
            return

        if "token" in query_params or "access_token" in query_params:
            await self._send_json(writer, 401, {"error": "禁止通过 URL 查询串传递鉴权令牌"})
            return
        if not self._verify_token(headers):
            await self._send_json(writer, 401, {"error": "缺少或无效的 X-Roundtable-Token 凭据"})
            return

        if method == "GET" and path == "/api/status":
            sys_status = self.orchestrator.get_system_status()
            await self._send_json(
                writer,
                200,
                {
                    "boot_id": self.boot_id,
                    "system": sys_status,
                    "sessions": self.orchestrator.list_sessions(),
                    "default_session_id": self.orchestrator.default_session_id,
                },
            )
            return

        if method == "GET" and path == "/api/workspace/files":
            sid = (query_params.get("session_id") or [""])[0]
            q = (query_params.get("q") or [""])[0]
            try:
                limit = int((query_params.get("limit") or ["120"])[0])
            except ValueError:
                limit = 120
            res = await self.orchestrator.search_workspace_files_async(session_id=sid, query=q, limit=limit)
            await self._send_json(writer, 200, res)
            return

        if method == "POST" and path == "/api/config":
            data, jerr = self._parse_json_strict(body_bytes)
            if jerr is not None or data is None:
                await self._send_json(writer, 400, {"error": jerr or "参数错误"})
                return
            if "workspace_dir" in data and data["workspace_dir"]:
                ok_ws, ws_err = self.orchestrator.validate_safe_workspace_path(str(data["workspace_dir"]))
                if not ok_ws:
                    await self._send_json(writer, 400, {"error": ws_err})
                    return
            active_sid = str(data.get("active_session_id", "")).strip()
            updated = self.orchestrator.update_runtime_config(data, active_session_id=active_sid)
            for sess in self.orchestrator.sessions.values():
                for st in sess.seat_states.values():
                    await self.orchestrator.broadcast(sess, "seat_update", st)
                await self.orchestrator._broadcast_meta(sess)
            await self._send_json(writer, 200, {"ok": True, "boot_id": self.boot_id, "system": updated})
            return

        if method == "POST" and path == "/api/system/pick-folder":
            data, jerr = self._parse_json_strict(body_bytes)
            if jerr is not None or data is None:
                await self._send_json(writer, 400, {"error": jerr or "参数错误"})
                return
            if "direct_path" in data:
                await self._send_json(
                    writer,
                    400,
                    {"error": "pick-folder 禁止接收 direct_path 参数；切换会话目录请调用 POST /api/sessions/{sid}/workspace"},
                )
                return
            loop = asyncio.get_running_loop()
            selected = await loop.run_in_executor(None, self._pick_macos_folder_sync)
            if not selected:
                await self._send_json(writer, 200, {"ok": False, "cancelled": True})
                return
            ok_ws, ws_err = self.orchestrator.validate_safe_workspace_path(selected)
            if not ok_ws:
                await self._send_json(writer, 400, {"error": ws_err})
                return
            updated = self.orchestrator.update_default_workspace_only(selected)
            await self._send_json(writer, 200, {"ok": True, "path": selected, "system": updated})
            return

        if method == "POST" and path == "/api/cli/test":
            data, jerr = self._parse_json_strict(body_bytes)
            if jerr is not None or data is None:
                await self._send_json(writer, 400, {"error": jerr or "参数错误"})
                return
            override_agents = data.get("agents") if isinstance(data.get("agents"), dict) else None
            target_aid = str(data.get("agent_id", "")).strip().lower()
            results = await self.orchestrator.run_cli_connectivity_test(
                override_agents=override_agents,
                target_agent_id=target_aid,
            )
            await self._send_json(
                writer,
                200,
                {
                    "ok": True,
                    "results": results,
                    "system": self.orchestrator.get_system_status(),
                },
            )
            return

        if method == "GET" and path == "/api/sessions":
            await self._send_json(writer, 200, {"sessions": self.orchestrator.list_sessions()})
            return

        if method == "POST" and path == "/api/sessions":
            data, jerr = self._parse_json_strict(body_bytes)
            if jerr is not None or data is None:
                await self._send_json(writer, 400, {"error": jerr or "参数错误"})
                return
            raw_auto = data.get("auto_preview_exec")
            sess = self.orchestrator.create_session(
                title=str(data.get("title", "新会议")),
                collab_mode=str(data.get("collab_mode", "deep_deliberation")),
                auto_preview_exec=bool(raw_auto) if raw_auto is not None else None,
            )
            await self._send_json(
                writer,
                201,
                {"session": sess.to_snapshot(), "sessions": self.orchestrator.list_sessions()},
            )
            return

        segs = [s for s in path.split("/") if s]
        if len(segs) >= 3 and segs[0] == "api" and segs[1] == "sessions":
            sid = segs[2]
            action = segs[3] if len(segs) >= 4 else ""
            sub_action = segs[4] if len(segs) >= 5 else ""

            if method == "DELETE" and action == "":
                next_sid = await self.orchestrator.delete_session(sid)
                if not next_sid:
                    await self._send_json(writer, 404, {"error": f"未找到会议会话 {sid}"})
                    return
                await self._send_json(
                    writer,
                    200,
                    {
                        "ok": True,
                        "active_session_id": next_sid,
                        "sessions": self.orchestrator.list_sessions(),
                    },
                )
                return

            sess = self.orchestrator.get_session(sid)
            if not sess:
                await self._send_json(writer, 404, {"error": f"未找到会议会话 {sid}"})
                return

            if method == "GET" and action == "":
                await self._send_json(writer, 200, {"boot_id": self.boot_id, "session": sess.to_snapshot()})
                return

            if method == "GET" and action == "stream":
                since_raw = (query_params.get("since_rev") or [headers.get("last-event-id", "0")])[0]
                try:
                    since_rev = max(0, int(str(since_raw or "0").strip()))
                except ValueError:
                    since_rev = 0
                client_boot = str((query_params.get("boot_id") or [""])[0]).strip()
                await self._handle_sse(sess, writer, since_rev=since_rev, client_boot_id=client_boot)
                return

            if method in ("GET", "POST") and action == "export":
                if body_bytes:
                    parsed_exp, jerr = self._parse_json_strict(body_bytes)
                    if jerr is not None or parsed_exp is None:
                        await self._send_json(writer, 400, {"error": jerr or "参数错误"})
                        return
                    if "markdown" in parsed_exp or "save_path" in parsed_exp or "workspace_dir" in parsed_exp:
                        await self._send_json(
                            writer,
                            400,
                            {"error": "export 接口已收口为服务端内存生成下载流，禁止客户端直传 markdown 写盘"},
                        )
                        return
                md_bytes, filename = self.orchestrator.build_session_export_bytes(sess)
                encoded_fn = urllib.parse.quote(filename)
                await self._send_bytes(
                    writer,
                    200,
                    md_bytes,
                    content_type="text/markdown; charset=utf-8",
                    extra_headers={
                        "Content-Disposition": f"attachment; filename=\"roundtable-minutes.md\"; filename*=UTF-8''{encoded_fn}",
                        "X-Roundtable-Filename": encoded_fn,
                    },
                )
                return

            if method == "GET" and action == "recovery":
                plan = await self.orchestrator.get_session_recovery_plan(sess)
                await self._send_json(writer, 200, {"ok": True, "recovery": plan})
                return

            payload, jerr = self._parse_json_strict(body_bytes)
            if jerr is not None or payload is None:
                await self._send_json(writer, 400, {"error": jerr or "请求体 JSON 格式错误"})
                return

            if method == "POST" and action == "workspace":
                target_ws = str(payload.get("workspace_dir") or "").strip()
                status_code, resp_dict = await self.orchestrator.switch_session_workspace(sess, target_ws)
                await self._send_json(writer, status_code, resp_dict)
                return

            if method == "POST" and action == "start":
                topic = str(payload.get("topic", "")).strip() or sess.topic
                if not topic:
                    await self._send_json(writer, 400, {"error": "议题内容不能为空"})
                    return
                collab_mode = payload.get("collab_mode")
                raw_auto_exec = payload.get("auto_preview_exec")
                enabled_agents = payload.get("enabled_agents")
                seat_personas = payload.get("seat_personas")
                seat_efforts = payload.get("seat_efforts")
                executor_agent = str(payload.get("executor_agent", "")).strip().lower() or None
                reset_history = bool(payload.get("reset_history", False))
                await self.orchestrator.start_topic_meeting(
                    sess,
                    topic=topic,
                    collab_mode=collab_mode,
                    auto_preview_exec=bool(raw_auto_exec) if raw_auto_exec is not None else None,
                    enabled_agents=enabled_agents if isinstance(enabled_agents, list) else None,
                    seat_personas=seat_personas if isinstance(seat_personas, dict) else None,
                    seat_efforts=seat_efforts if isinstance(seat_efforts, dict) else None,
                    executor_agent=executor_agent,
                    reset_history=reset_history,
                )
                await self._send_json(writer, 200, {"ok": True, "session": sess.to_snapshot()})
                return

            if method == "POST" and action in ("interrupt", "followup"):
                msg = str(payload.get("message", "")).strip()
                if not msg:
                    await self._send_json(writer, 400, {"error": "发言内容不能为空"})
                    return
                await self.orchestrator.chair_interrupt(sess, message=msg)
                await self._send_json(writer, 200, {"ok": True})
                return

            if method == "POST" and action == "stop":
                res = await self.orchestrator.stop_session_flow(sess)
                await self._send_json(writer, 200, res if isinstance(res, dict) else {"ok": True})
                return

            if method == "POST" and action == "skip":
                agent_id = str(payload.get("agent_id", "")).strip().lower()
                if not agent_id:
                    await self._send_json(writer, 400, {"error": "缺少跳过席位标识 agent_id"})
                    return
                try:
                    res = await self.orchestrator.skip_agent_turn(sess, agent_id=agent_id)
                except ValueError as ve:
                    await self._send_json(writer, 400, {"error": str(ve)})
                    return
                await self._send_json(writer, 200, res)
                return

            if method == "POST" and action == "seats":
                enabled = payload.get("enabled_agents")
                seat_personas = payload.get("seat_personas")
                seat_efforts = payload.get("seat_efforts")
                collab_mode = payload.get("collab_mode")
                raw_auto_exec = payload.get("auto_preview_exec")
                executor_agent = str(payload.get("executor_agent", "")).strip().lower() or None
                if enabled is not None and not isinstance(enabled, list):
                    await self._send_json(writer, 400, {"error": "参会席位列表格式无效"})
                    return
                try:
                    updated_seats = await self.orchestrator.update_session_seats(
                        sess,
                        enabled_agents=enabled,
                        seat_personas=seat_personas if isinstance(seat_personas, dict) else None,
                        executor_agent=executor_agent,
                        seat_efforts=seat_efforts if isinstance(seat_efforts, dict) else None,
                        collab_mode=str(collab_mode) if collab_mode is not None else None,
                        auto_preview_exec=bool(raw_auto_exec) if raw_auto_exec is not None else None,
                    )
                except ValueError as ve:
                    await self._send_json(writer, 400, {"error": str(ve)})
                    return
                await self._send_json(writer, 200, {"ok": True, **updated_seats})
                return

            if method in ("POST", "PATCH") and action == "whiteboard":
                wb = await self.orchestrator.update_whiteboard_manual(sess, payload)
                await self._send_json(writer, 200, {"ok": True, "whiteboard": wb})
                return

            if method == "POST" and action == "cue":
                agent_id = str(payload.get("agent_id", "")).strip().lower()
                instruction = str(payload.get("instruction", "")).strip()
                await self.orchestrator.cue_agent(sess, agent_id=agent_id, instruction=instruction)
                await self._send_json(writer, 200, {"ok": True})
                return

            if method == "POST" and action == "retry":
                agent_id = str(payload.get("agent_id", "")).strip().lower()
                message_id = str(payload.get("message_id", "")).strip()
                retry_mode = str(payload.get("mode", "unlimited")).strip().lower() or "unlimited"
                if not agent_id:
                    await self._send_json(writer, 400, {"error": "缺少重试席位标识 agent_id"})
                    return
                try:
                    retry_res = await self.orchestrator.retry_agent_turn(
                        sess,
                        agent_id=agent_id,
                        message_id=message_id,
                        mode=retry_mode,
                    )
                except ValueError as ve:
                    await self._send_json(writer, 400, {"error": str(ve)})
                    return
                await self._send_json(writer, 200, retry_res)
                return

            if method == "POST" and action == "conclude":
                await self.orchestrator.conclude_meeting(sess)
                await self._send_json(writer, 200, {"ok": True})
                return

            if method == "POST" and action == "execute":
                if "allow_workspace_write" not in payload or type(payload["allow_workspace_write"]) is not bool:
                    await self._send_json(
                        writer,
                        400,
                        {"error": "allow_workspace_write 必须为严格的 JSON 布尔值（true 或 false）"},
                    )
                    return
                allow_write = payload["allow_workspace_write"]
                executor_id = str(payload.get("executor_id", "")).strip().lower() or None
                verify_cmd = str(payload.get("verify_command", "")).strip() or None
                try:
                    admitted = await self.orchestrator.admit_and_start_execution(
                        sess,
                        allow_workspace_write=allow_write,
                        executor_id=executor_id,
                        verify_command=verify_cmd,
                    )
                except ExecutionAdmissionConflictError as conf_exc:
                    await self._send_json(writer, conf_exc.status_code, conf_exc.to_dict())
                    return
                await self._send_json(writer, 202, admitted)
                return

            if method == "POST" and action == "snapshot" and sub_action == "ack":
                ack_res = await self.orchestrator.acknowledge_previous_snapshot(sess)
                await self._send_json(writer, 200, ack_res)
                return

            if method == "POST" and action == "rollback":
                status_code, rb_payload = await self.orchestrator.rollback_session_execution_detailed(sess)
                await self._send_json(writer, status_code, rb_payload)
                return

            if method == "POST" and action == "recover":
                expected_hashes = payload.get("expected_hashes")
                delete_new = payload.get("delete_confirmed_new_files", True)
                if type(delete_new) is not bool:
                    await self._send_json(writer, 400, {"error": "delete_confirmed_new_files 必须为 JSON 布尔值"})
                    return
                status_code, rec_payload = await self.orchestrator.recover_session_workspace(
                    sess,
                    expected_hashes=expected_hashes,
                    delete_confirmed_new_files=delete_new,
                )
                await self._send_json(writer, status_code, rec_payload)
                return

        await self._send_json(writer, 404, {"error": f"未知接口路径: {path}"})

    async def _handle_sse(
        self,
        sess,
        writer: asyncio.StreamWriter,
        *,
        since_rev: int = 0,
        client_boot_id: str = "",
    ) -> None:
        head = (
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: text/event-stream; charset=utf-8\r\n"
            "Cache-Control: no-cache, no-store\r\n"
            "Connection: keep-alive\r\n"
            "X-Content-Type-Options: nosniff\r\n"
            "X-Accel-Buffering: no\r\n\r\n"
        ).encode("utf-8")
        writer.write(head)
        await writer.drain()

        queue, initial_packets = self.orchestrator.subscribe_session_sse(
            sess,
            since_rev=since_rev if (not client_boot_id or client_boot_id == self.boot_id) else 0,
        )
        try:
            for pkt in initial_packets:
                writer.write(pkt)
            await writer.drain()

            while True:
                try:
                    pkt = await asyncio.wait_for(queue.get(), timeout=15.0)
                    if pkt is None:
                        break
                    writer.write(pkt)
                    await writer.drain()
                except asyncio.TimeoutError:
                    writer.write(b": ping\n\n")
                    await writer.drain()
        except (ConnectionResetError, BrokenPipeError, asyncio.CancelledError):
            pass
        finally:
            self.orchestrator.unsubscribe_session_sse(sess, queue)


async def run_async_server(host: str, port: int, workspace_dir: str, *, notify_parent: bool = False) -> None:
    import socket
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        listener.bind((host, port))
        port = listener.getsockname()[1]
        app = AsyncHTTPServer(host=host, port=port, workspace_dir=workspace_dir)
        server = await asyncio.start_server(
            app.handle_client, sock=listener, limit=max(MAX_REQUEST_LINE_BYTES, MAX_HEADER_LINE_BYTES) + 256,
        )
    except BaseException:
        listener.close()
        raise
    if notify_parent:
        print(f"ROUNDTABLE_PORT={port}", flush=True)
    asyncio.create_task(app.orchestrator.runner.prewarm())
    status = app.orchestrator.get_system_status()
    print("=" * 68, flush=True)
    print(f"AI圆桌服务已启动: http://{host}:{port} (boot_id={app.boot_id[:8]})", flush=True)
    print(f"运行源码根路径: {status.get('runtime_code_root', '')}", flush=True)
    print(f"默认工作目录: {status['workspace_dir']}", flush=True)
    for aid, info in status["agents"].items():
        if info["binary_detected"]:
            print(
                f" [已就绪] {info['name']:6s} ({info['title']}) -> {info['cli_name']} | {info['binary_path']}",
                flush=True,
            )
        elif aid in ("carbon", "grok", "astra"):
            print(
                f" [未检测] {info['name']:6s} ({info['title']}) -> 未找到 {'/'.join(info['binary_candidates'])}",
                flush=True,
            )
    print("=" * 68, flush=True)
    try:
        async with server:
            await server.serve_forever()
    finally:
        await app.orchestrator.shutdown()


def main() -> None:
    parser = argparse.ArgumentParser(description="AI圆桌 本地多 CLI 实时会议安全服务")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址 (默认 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="监听端口 (默认 8765)")
    parser.add_argument("--workspace", default=str(ROOT_DIR), help="新建会话默认工作目录")
    parser.add_argument("--notify-parent", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--wait-for-parent", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.wait_for_parent and sys.stdin.buffer.readline(16).strip() != b"START":
        return
    try:
        asyncio.run(run_async_server(args.host, args.port, args.workspace, notify_parent=args.notify_parent))
    except KeyboardInterrupt:
        print("\n服务已关闭。")


if __name__ == "__main__":
    main()
