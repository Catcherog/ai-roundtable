#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI圆桌 — 异步 HTTP + SSE 服务端
支持会话生命周期管理、停止生成、席位动态开关与预设身份切换、任选主刀执行、工作区文件检索、白板修订与安全回滚
"""

from __future__ import annotations

import argparse
import asyncio
import json
import itertools
import mimetypes
import os
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Dict

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.orchestrator import RoundtableOrchestrator  # noqa: E402

FRONTEND_DIR = ROOT_DIR / "frontend"


class AsyncHTTPServer:
    def __init__(self, host: str, port: int, workspace_dir: str):
        self.host = host
        self.port = port
        self.orchestrator = RoundtableOrchestrator(workspace_dir=workspace_dir)

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            req_line = await asyncio.wait_for(reader.readline(), timeout=15.0)
            if not req_line:
                writer.close()
                return
            parts = req_line.decode("utf-8", errors="replace").strip().split(" ")
            if len(parts) < 2:
                writer.close()
                return
            method, raw_target = parts[0].upper(), parts[1]
            parsed = urllib.parse.urlparse(raw_target)
            path = urllib.parse.unquote(parsed.path)
            query_params = urllib.parse.parse_qs(parsed.query)

            headers: Dict[str, str] = {}
            while True:
                hline = await asyncio.wait_for(reader.readline(), timeout=10.0)
                if not hline or hline in (b"\r\n", b"\n"):
                    break
                hstr = hline.decode("utf-8", errors="replace").strip()
                if ":" in hstr:
                    k, v = hstr.split(":", 1)
                    headers[k.strip().lower()] = v.strip()

            if method == "OPTIONS":
                await self._send_json(writer, 200, {"ok": True})
                return

            content_len = int(headers.get("content-length", "0") or "0")
            body_bytes = b""
            if content_len > 0:
                body_bytes = await asyncio.wait_for(reader.readexactly(content_len), timeout=15.0)

            if path.startswith("/api/"):
                await self._route_api(method, path, query_params, body_bytes, writer)
            else:
                await self._serve_static(path, writer)
        except (asyncio.TimeoutError, asyncio.IncompleteReadError, ConnectionResetError, BrokenPipeError):
            pass
        except Exception as exc:
            try:
                await self._send_json(writer, 500, {"error": str(exc)})
            except Exception:
                pass
        finally:
            try:
                if not writer.is_closing():
                    writer.close()
            except Exception:
                pass

    @staticmethod
    def _parse_json(body_bytes: bytes) -> dict:
        if not body_bytes:
            return {}
        try:
            return json.loads(body_bytes.decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            return {}

    async def _send_json(self, writer: asyncio.StreamWriter, status: int, payload: dict) -> None:
        status_text = {
            200: "OK",
            201: "Created",
            400: "Bad Request",
            404: "Not Found",
            500: "Internal Server Error",
        }.get(status, "OK")
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        head = (
            f"HTTP/1.1 {status} {status_text}\r\n"
            f"Content-Type: application/json; charset=utf-8\r\n"
            f"Content-Length: {len(body)}\r\n"
            f"Cache-Control: no-cache\r\n"
            f"Access-Control-Allow-Origin: *\r\n"
            f"Access-Control-Allow-Methods: GET, POST, DELETE, PATCH, OPTIONS\r\n"
            f"Access-Control-Allow-Headers: Content-Type\r\n"
            f"Connection: close\r\n\r\n"
        ).encode("utf-8")
        writer.write(head + body)
        await writer.drain()

    async def _serve_static(self, path: str, writer: asyncio.StreamWriter) -> None:
        if path in ("/ui_preview.html", "/ui-preview"):
            preview_file = (ROOT_DIR / "ui_preview.html").resolve()
            if preview_file.is_file():
                data = preview_file.read_bytes()
                head = (
                    f"HTTP/1.1 200 OK\r\n"
                    f"Content-Type: text/html; charset=utf-8\r\n"
                    f"Content-Length: {len(data)}\r\n"
                    f"Cache-Control: no-cache\r\n"
                    f"Connection: close\r\n\r\n"
                ).encode("utf-8")
                writer.write(head + data)
                await writer.drain()
                return

        rel = "index.html" if path in ("", "/") else path.lstrip("/")
        target = (FRONTEND_DIR / rel).resolve()
        if not str(target).startswith(str(FRONTEND_DIR.resolve())) or not target.is_file():
            await self._send_json(writer, 404, {"error": "资源不存在"})
            return
        mime, _ = mimetypes.guess_type(str(target))
        ctype = mime or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        data = target.read_bytes()
        head = (
            f"HTTP/1.1 200 OK\r\n"
            f"Content-Type: {ctype}\r\n"
            f"Content-Length: {len(data)}\r\n"
            f"Cache-Control: no-cache\r\n"
            f"Connection: close\r\n\r\n"
        ).encode("utf-8")
        writer.write(head + data)
        await writer.drain()

    @staticmethod
    def _pick_macos_folder_sync() -> str:
        if sys.platform != "darwin":
            return ""
        script = 'POSIX path of (choose folder with prompt "请选择 AI圆桌 绑定的本地项目工作区目录：")'
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
        body_bytes: bytes,
        writer: asyncio.StreamWriter,
    ) -> None:
        if method == "GET" and path == "/api/status":
            await self._send_json(
                writer,
                200,
                {
                    "system": self.orchestrator.get_system_status(),
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
            res = self.orchestrator.search_workspace_files(session_id=sid, query=q, limit=limit)
            await self._send_json(writer, 200, res)
            return

        if method == "POST" and path == "/api/config":
            data = self._parse_json(body_bytes)
            if "workspace_dir" in data and data["workspace_dir"]:
                exp = os.path.expanduser(str(data["workspace_dir"]).strip())
                if not os.path.isdir(exp):
                    await self._send_json(writer, 400, {"error": f"目录不存在：{exp}"})
                    return
            active_sid = str(data.get("active_session_id", "")).strip()
            updated = self.orchestrator.update_runtime_config(data, active_session_id=active_sid)
            for sess in self.orchestrator.sessions.values():
                for st in sess.seat_states.values():
                    await self.orchestrator.broadcast(sess, "seat_update", st)
                await self.orchestrator._broadcast_meta(sess)
            await self._send_json(writer, 200, {"ok": True, "system": updated})
            return

        if method == "POST" and path == "/api/system/pick-folder":
            data = self._parse_json(body_bytes)
            active_sid = str(data.get("active_session_id", "")).strip()
            direct_path = str(data.get("direct_path", "")).strip()
            if direct_path:
                exp = os.path.expanduser(direct_path)
                if not os.path.isdir(exp):
                    await self._send_json(writer, 400, {"error": f"目录不存在：{exp}"})
                    return
                selected = exp.rstrip("/") if exp != "/" else exp
            else:
                loop = asyncio.get_running_loop()
                selected = await loop.run_in_executor(None, self._pick_macos_folder_sync)
            if not selected:
                await self._send_json(writer, 200, {"ok": False, "cancelled": True})
                return
            updated = self.orchestrator.update_runtime_config(
                {"workspace_dir": selected},
                active_session_id=active_sid,
            )
            for sess in self.orchestrator.sessions.values():
                await self.orchestrator._broadcast_meta(sess)
            await self._send_json(writer, 200, {"ok": True, "path": selected, "system": updated})
            return

        if method == "POST" and path == "/api/cli/test":
            data = self._parse_json(body_bytes)
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
            data = self._parse_json(body_bytes)
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
                await self._send_json(writer, 200, {"session": sess.to_snapshot()})
                return

            if method == "GET" and action == "stream":
                await self._handle_sse(sess, writer)
                return

            payload = self._parse_json(body_bytes)
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
                await self.orchestrator.stop_session_flow(sess)
                await self._send_json(writer, 200, {"ok": True})
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
                allow_write = bool(payload.get("allow_workspace_write", False))
                executor_id = str(payload.get("executor_id", "")).strip().lower() or None
                await self.orchestrator.trigger_astra_execution(
                    sess,
                    allow_workspace_write=allow_write,
                    executor_id=executor_id,
                )
                await self._send_json(writer, 200, {"ok": True})
                return

            if method == "POST" and action == "rollback":
                ok, msg = await self.orchestrator.rollback_session_execution(sess)
                if not ok:
                    await self._send_json(writer, 400, {"error": msg})
                    return
                await self._send_json(writer, 200, {"ok": True, "message": msg})
                return

            if method == "POST" and action == "export":
                md_content = str(payload.get("markdown", ""))
                dl_dir = Path.home() / "Downloads"
                save_dir = dl_dir if dl_dir.is_dir() else Path(self.orchestrator.settings.workspace_dir)
                safe_title = "".join(c for c in (sess.title or "会议纪要") if c.isalnum() or c in ("-", "_"))[:20]
                ts_str = time.strftime("%Y%m%d_%H%M%S", time.localtime())
                stem = f"AI圆桌_{safe_title or '纪要'}_{ts_str}"
                for number in itertools.count(1):
                    suffix = "" if number == 1 else f"_{number}"
                    out_file = save_dir / f"{stem}{suffix}.md"
                    try:
                        with out_file.open("x", encoding="utf-8") as out:
                            out.write(md_content)
                        break
                    except FileExistsError:
                        continue
                await self._send_json(writer, 200, {"ok": True, "saved_path": str(out_file)})
                return

        await self._send_json(writer, 404, {"error": f"未知接口路径: {path}"})

    async def _handle_sse(self, sess, writer: asyncio.StreamWriter) -> None:
        head = (
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: text/event-stream; charset=utf-8\r\n"
            "Cache-Control: no-cache\r\n"
            "Connection: keep-alive\r\n"
            "Access-Control-Allow-Origin: *\r\n"
            "X-Accel-Buffering: no\r\n\r\n"
        ).encode("utf-8")
        writer.write(head)
        await writer.drain()

        queue: asyncio.Queue = asyncio.Queue(maxsize=512)
        sess.subscribers.append(queue)
        try:
            snap_payload = json.dumps(sess.to_snapshot(), ensure_ascii=False)
            writer.write(f"event: snapshot\ndata: {snap_payload}\n\n".encode("utf-8"))
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
            if queue in sess.subscribers:
                sess.subscribers.remove(queue)


async def run_async_server(host: str, port: int, workspace_dir: str) -> None:
    app = AsyncHTTPServer(host=host, port=port, workspace_dir=workspace_dir)
    server = await asyncio.start_server(app.handle_client, host=host, port=port)
    asyncio.create_task(app.orchestrator.runner.prewarm())
    status = app.orchestrator.get_system_status()
    print("=" * 64, flush=True)
    print(f"AI圆桌服务已启动: http://{host}:{port}", flush=True)
    print(f"工作目录: {status['workspace_dir']}", flush=True)
    for aid, info in status["agents"].items():
        if info["binary_detected"]:
            print(f"  [已就绪] {info['name']:6s} ({info['title']}) -> {info['cli_name']} | {info['binary_path']}", flush=True)
        else:
            print(f"  [未检测] {info['name']:6s} ({info['title']}) -> 未找到 {'/'.join(info['binary_candidates'])}", flush=True)
    print("=" * 64, flush=True)
    try:
        async with server:
            await server.serve_forever()
    finally:
        await app.orchestrator.runner.shutdown()


def main() -> None:
    parser = argparse.ArgumentParser(description="AI圆桌 本地多 CLI 实时会议服务")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址 (默认 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="监听端口 (默认 8765)")
    parser.add_argument("--workspace", default=str(ROOT_DIR), help="CLI 默认工作目录")
    args = parser.parse_args()
    try:
        asyncio.run(run_async_server(args.host, args.port, args.workspace))
    except KeyboardInterrupt:
        print("\n服务已关闭。")


if __name__ == "__main__":
    main()
