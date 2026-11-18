#!/usr/bin/env python3
"""Exercise durable meeting history, recovery and explicit permanent deletion using temporary data."""
import asyncio
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.verify_full_convergence import mem_http_request, mem_json


async def check(root):
    from backend.server import AsyncHTTPServer

    project = root / "project"
    project.mkdir()
    user_file = project / "keep.txt"
    user_file.write_text("keep project and independently exported files")
    sid = "legacy_long_meeting"
    messages = [{"id": f"m_{i}", "speaker": "chair", "content": f"发言 {i}"} for i in range(550)]
    record = {"session_id": sid, "title": "跨窗口记录", "topic": "跨窗口记录", "stage": "awaiting_chair",
              "workspace_dir": str(project), "messages": messages, "updated_ts": 1, "rev": 1,
              "whiteboard": {"topic_title": "跨窗口记录", "exec_logs": [f"log {i}" for i in range(340)]}}
    legacy = [record] + [{"session_id": f"legacy_{i}", "title": f"会议 {i}", "topic": f"议题 {i}",
                          "updated_ts": 2+i} for i in range(59)]
    (root / "sessions.json").write_text(json.dumps(legacy))
    # Re-use an actual previous-version table with no deleted_at column.
    with sqlite3.connect(root / "state.sqlite3") as con:
        con.execute("CREATE TABLE sessions(session_id TEXT PRIMARY KEY,updated_ts REAL NOT NULL,rev INTEGER NOT NULL "
                    "DEFAULT 0,header_json TEXT NOT NULL,whiteboard_json TEXT NOT NULL)")

    def open_app():
        return AsyncHTTPServer("127.0.0.1", 18765, "")
    app = open_app()
    async def call(method, path, payload=None, expected=200):
        status, _, data = await mem_json(app, app.boot_token, method, path, payload)
        assert status == expected, (method, path, status, expected, data.get("error"))
        return data
    async def trash():
        rows = (await call("GET", "/api/sessions/trash"))["sessions"]
        return next(row for row in rows if row["session_id"] == sid)
    def confirmation(row):
        return {"confirm_session_id":sid, "confirm_title":row["title"], "deleted_at":row["deleted_at"]}

    path = "/api/sessions/" + sid
    try:
        assert len((await call("GET", "/api/sessions"))["sessions"]) == 60
        session = app.orchestrator.sessions[sid]
        assert len(session.messages) == 550 and session.messages[0]["content"] == "发言 0"
        app.orchestrator._save_persisted_sessions(immediate=True, session=session)
        att = app.attachments.save_raw_attachment(sid, filename="evidence.txt", raw_bytes=b"evidence", declared_mime="text/plain")
        backup = root / "backups" / sid / "finished"
        backup.mkdir(parents=True); (backup / "data").write_text("fixture")
        other = root / "backups" / "other_session"
        other.mkdir(); (other / "keep").write_text("keep")
        session.exec_state = "running"
        await call("DELETE", path, expected=409)
        session.exec_state = "idle"; session.recovery_required = True
        await call("DELETE", path, expected=409)
        session.recovery_required = False
        await call("POST", path+"/purge", {"confirm_session_id":sid, "confirm_title":session.title, "deleted_at":1}, 409)
        await call("DELETE", path); await call("DELETE", path)
        original = await trash()
        await call("GET", path, expected=404)
        await app.orchestrator.shutdown(); app = open_app()
        assert (await trash()) == original
        await call("POST", path+"/restore", {}); await call("POST", path+"/restore", {})
        restored = (await call("GET", path))["session"]
        assert [m["id"] for m in restored["messages"]] == [m["id"] for m in messages]
        assert restored["workspace_dir"] == str(project) and len(restored["whiteboard"]["exec_logs"]) == 340
        code, _, export = await mem_http_request(app, "GET", path+"/export", headers={"X-Roundtable-Token":app.boot_token})
        minutes = export.decode()
        assert code == 200 and all(m["content"]+"\n" in minutes for m in messages)
        assert app.attachments.get_attachment_bytes(sid, att["id"])[1] == b"evidence"
        print("PASS migration, 60 meetings / 550 messages, whole transcript, 340 log entries, restart and restore")
        await call("DELETE", path)
        row = await trash(); confirm = confirmation(row)
        for invalid in ({}, {**confirm,"confirm_title":"错标题"}, {**confirm,"confirm_session_id":"other"},
                        confirmation(original)):
            await call("POST", path+"/purge", invalid, 409)
        assert app.attachments.get_attachment_bytes(sid, att["id"])[1] == b"evidence"
        assert backup.is_dir()
        # Simulate a file still in use, then verify crash-safe completion on restart.
        with patch("backend.orchestrator.shutil.rmtree", side_effect=OSError("in use")):
            await call("POST", path+"/purge", confirm, 409)
        assert (await trash())["purge_pending"]
        await call("POST", path+"/restore", {}, 409)
        await app.orchestrator.shutdown(); app = open_app()
        await call("POST", path+"/purge", confirm)
        assert not (root/"attachments"/sid).exists() and not (root/"backups"/sid).exists()
        assert user_file.is_file() and (other/"keep").is_file()
        remaining = json.loads((root/"sessions.json").read_text())
        assert len(remaining) == 59 and all(r["session_id"] != sid for r in remaining)
        app.orchestrator.store.upsert_session_incremental(record, rewrite_all_messages=True, wait=True)
        with sqlite3.connect(root/"state.sqlite3") as con:
            for table in ("sessions","session_messages","exec_recovery"):
                assert not con.execute(f"SELECT 1 FROM {table} WHERE session_id=?", (sid,)).fetchone()
        assert not (await call("GET","/api/sessions/trash"))["sessions"]
        assert len((await call("GET","/api/sessions"))["sessions"]) == 59
        print("PASS busy/recovery protection, stale and wrong confirmations, cleanup retry, scope and stale-write suppression")
    finally:
        await app.orchestrator.shutdown()


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="roundtable-history-") as temp:
        os.environ["AI_ROUNDTABLE_HOME"] = temp
        asyncio.run(check(Path(temp)))
