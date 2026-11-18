# -*- coding: utf-8 -*-
"""
AI圆桌 — 单库 SQLite 事务存储与执行崩溃恢复账本（P0 执行恢复落盘 + P1.1 单写线程事务底座）

架构特性：
1. 纯 Python 标准库 `sqlite3`，零第三方依赖，位于 `~/.ai-roundtable/state.sqlite3`。
2. 专属单写线程 + `BEGIN IMMEDIATE` 事务串行提交：杜绝 `database is locked` 竞态，彻底避免事件循环同步磁盘阻塞。
3. WAL 优先 + 网络盘/不支持场景显式自动回退 `journal_mode=DELETE` 且 `synchronous=FULL`。
4. 将会话消息拆分为 `(session_id, seq)` 独立表，单条 `msg_done` 落盘从全库 $O(N)$ 重写降至单条 $O(1)$ UPSERT。
5. 幂等兼容迁移旧版 `~/.ai-roundtable/sessions.json`。
"""

from __future__ import annotations

import json
import os
import queue
import sqlite3
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Dict, Iterator, List, Optional, Tuple


class RoundtableSQLiteStore:
    def __init__(self, db_path: Optional[str] = None) -> None:
        base_dir = Path(os.path.expanduser(os.environ.get("AI_ROUNDTABLE_HOME") or "~/.ai-roundtable"))
        base_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = Path(db_path) if db_path else (base_dir / "state.sqlite3")
        self.journal_mode_active = "DELETE"
        self._write_queue: "queue.Queue[Optional[Tuple[Callable[[sqlite3.Connection], object], Optional[threading.Event], List[object], List[BaseException]]]]" = queue.Queue()
        self._closed = False
        self._ready_event = threading.Event()
        self._init_error: Optional[BaseException] = None
        self._writer_thread = threading.Thread(
            target=self._writer_loop,
            name="ai-roundtable-sqlite-writer",
            daemon=True,
        )
        self._writer_thread.start()
        self._ready_event.wait(timeout=10.0)
        if self._init_error is not None:
            raise RuntimeError(f"SQLite 存储初始化失败: {self._init_error}") from self._init_error

    def _configure_connection(self, conn: sqlite3.Connection) -> str:
        conn.isolation_level = None  # 手动显式控制 BEGIN IMMEDIATE / COMMIT
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA busy_timeout = 5000;")
        force_delete = os.environ.get("AI_ROUNDTABLE_FORCE_DELETE_JOURNAL", "").strip() == "1"
        mode = "DELETE"
        if not force_delete:
            try:
                row = conn.execute("PRAGMA journal_mode = WAL;").fetchone()
                cand = str(row[0] if row else "").strip().upper()
                if cand == "WAL":
                    mode = "WAL"
                    conn.execute("PRAGMA synchronous = NORMAL;")
            except sqlite3.OperationalError:
                mode = "DELETE"
        if mode != "WAL":
            conn.execute("PRAGMA journal_mode = DELETE;")
            conn.execute("PRAGMA synchronous = FULL;")
        return mode

    def _init_schema(self, conn: sqlite3.Connection) -> None:
        conn.execute("BEGIN IMMEDIATE;")
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    updated_ts REAL NOT NULL,
                    rev INTEGER NOT NULL DEFAULT 0,
                    header_json TEXT NOT NULL,
                    whiteboard_json TEXT NOT NULL,
                    deleted_at REAL
                );
                """
            )
            if "deleted_at" not in {row[1] for row in conn.execute("PRAGMA table_info(sessions)")}:
                conn.execute("ALTER TABLE sessions ADD COLUMN deleted_at REAL")
            conn.execute("CREATE TABLE IF NOT EXISTS meeting_purges "
                         "(session_id TEXT PRIMARY KEY, pending INTEGER NOT NULL)")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS session_messages (
                    session_id TEXT NOT NULL,
                    seq INTEGER NOT NULL,
                    msg_id TEXT NOT NULL,
                    msg_json TEXT NOT NULL,
                    PRIMARY KEY (session_id, seq),
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
                );
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_sessions_updated
                ON sessions(updated_ts DESC);
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS exec_recovery (
                    run_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    workspace_realpath TEXT NOT NULL,
                    backup_dir TEXT NOT NULL,
                    state TEXT NOT NULL,
                    pgid INTEGER NOT NULL DEFAULT 0,
                    updated_ts REAL NOT NULL,
                    meta_json TEXT NOT NULL
                );
                """
            )
            conn.execute("COMMIT;")
        except Exception:
            conn.execute("ROLLBACK;")
            raise

    def _writer_loop(self) -> None:
        conn: Optional[sqlite3.Connection] = None
        try:
            conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self.journal_mode_active = self._configure_connection(conn)
            self._init_schema(conn)
        except BaseException as exc:
            self._init_error = exc
            self._ready_event.set()
            return
        self._ready_event.set()

        while True:
            item = self._write_queue.get()
            if item is None:
                break
            fn, done_ev, res_box, err_box = item
            try:
                conn.execute("BEGIN IMMEDIATE;")
                try:
                    out = fn(conn)
                    conn.execute("COMMIT;")
                    res_box.append(out)
                except BaseException as tx_exc:
                    try:
                        conn.execute("ROLLBACK;")
                    except Exception:
                        pass
                    err_box.append(tx_exc)
            except BaseException as outer_exc:
                err_box.append(outer_exc)
            finally:
                if done_ev is not None:
                    done_ev.set()

        if conn is not None:
            try:
                if self.journal_mode_active == "WAL":
                    conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
            except Exception:
                pass
            try:
                conn.close()
            except Exception:
                pass

    def submit_write(self, fn: Callable[[sqlite3.Connection], object], *, wait: bool = False) -> object:
        """提交事务写操作；wait=False 异步入队零阻塞，wait=True 同步等待事务提交落盘。"""
        if self._closed:
            return None
        done_ev = threading.Event() if wait else None
        res_box: List[object] = []
        err_box: List[BaseException] = []
        self._write_queue.put((fn, done_ev, res_box, err_box))
        if done_ev is not None:
            done_ev.wait()
            if err_box:
                raise err_box[0]
            return res_box[0] if res_box else None
        return None

    def flush(self) -> None:
        """屏障式等待队列中所有前序写事务全部落盘完成。"""
        if self._closed:
            return
        self.submit_write(lambda _c: True, wait=True)

    def close(self) -> None:
        if self._closed:
            return
        self.flush()
        self._closed = True
        self._write_queue.put(None)
        self._writer_thread.join(timeout=3.0)

    @contextmanager
    def _read_conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.db_path), timeout=5.0)
        try:
            conn.row_factory = sqlite3.Row
            yield conn
        finally:
            conn.close()

    def migrate_legacy_sessions_json_if_needed(self, legacy_json_path: Path) -> bool:
        """幂等迁移旧版 sessions.json 至单库 SQLite（仅在未迁移且库为空时执行一次）。"""
        if not legacy_json_path.is_file():
            return False
        with self._read_conn() as rconn:
            mig_row = rconn.execute("SELECT value FROM meta WHERE key = 'migrated_sessions_json'").fetchone()
            cnt_row = rconn.execute("SELECT COUNT(1) AS cnt FROM sessions").fetchone()
            if mig_row or (cnt_row and int(cnt_row["cnt"]) > 0):
                return False
        try:
            raw_list = json.loads(legacy_json_path.read_text(encoding="utf-8"))
        except Exception:
            return False
        if isinstance(raw_list, dict) and isinstance(raw_list.get("sessions"), list):
            raw_list = raw_list["sessions"]
        if not isinstance(raw_list, list):
            return False

        def _tx(conn: sqlite3.Connection) -> int:
            imported = 0
            for item in raw_list:
                if not isinstance(item, dict):
                    continue
                sid = str(item.get("session_id") or "").strip()
                if not sid:
                    continue
                if conn.execute("SELECT 1 FROM meeting_purges WHERE session_id=?", (sid,)).fetchone():
                    continue
                msgs = list(item.get("messages") or [])
                wb = dict(item.get("whiteboard") or {})
                header = {k: v for k, v in item.items() if k not in ("messages", "whiteboard")}
                upd_ts = float(item.get("updated_ts") or time.time())
                rev = int(item.get("rev") or 0)
                conn.execute(
                    """
                    INSERT OR REPLACE INTO sessions(session_id, updated_ts, rev, header_json, whiteboard_json)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        sid,
                        upd_ts,
                        rev,
                        json.dumps(header, ensure_ascii=False),
                        json.dumps(wb, ensure_ascii=False),
                    ),
                )
                conn.execute("DELETE FROM session_messages WHERE session_id = ?", (sid,))
                for idx, m in enumerate(msgs):
                    mid = str(m.get("id") or f"m_{idx}")
                    conn.execute(
                        """
                        INSERT INTO session_messages(session_id, seq, msg_id, msg_json)
                        VALUES (?, ?, ?, ?)
                        """,
                        (sid, idx, mid, json.dumps(m, ensure_ascii=False)),
                    )
                imported += 1
            conn.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES ('migrated_sessions_json', ?)",
                (str(int(time.time())),),
            )
            return imported

        count = self.submit_write(_tx, wait=True)
        return bool(count)

    def load_all_sessions(self, limit: Optional[int] = None, *, trashed_id: str = "") -> List[dict]:
        """读取持久化会话（按 updated_ts 升序还原，供编排器启动加载）。"""
        with self._read_conn() as rconn:
            sql = """
                SELECT session_id, updated_ts, rev, header_json, whiteboard_json
                FROM sessions
            """
            if trashed_id:
                sql += " WHERE deleted_at IS NOT NULL AND session_id = ?"
                params = [trashed_id]
            else:
                sql += " WHERE deleted_at IS NULL"
                params = []
            sql += " ORDER BY updated_ts DESC, session_id DESC"
            if limit is not None:
                sql += " LIMIT ?"
                params.append(max(1, int(limit)))
            rows = rconn.execute(sql, params).fetchall()
            result: List[dict] = []
            for row in reversed(rows):
                sid = str(row["session_id"])
                try:
                    header = json.loads(row["header_json"])
                except Exception:
                    header = {"session_id": sid}
                try:
                    wb = json.loads(row["whiteboard_json"])
                except Exception:
                    wb = {}
                mrows = rconn.execute(
                    """
                    SELECT msg_json FROM session_messages
                    WHERE session_id = ?
                    ORDER BY seq ASC
                    """,
                    (sid,),
                ).fetchall()
                msgs: List[dict] = []
                for mr in mrows:
                    try:
                        msgs.append(json.loads(mr["msg_json"]))
                    except Exception:
                        continue
                header["session_id"] = sid
                header["updated_ts"] = float(row["updated_ts"])
                header["rev"] = int(row["rev"] or header.get("rev") or 0)
                header["messages"] = msgs
                header["whiteboard"] = wb
                result.append(header)
            return result

    def upsert_session_incremental(
        self,
        persisted_dict: dict,
        *,
        single_msg_seq_and_obj: Optional[Tuple[int, dict]] = None,
        rewrite_all_messages: bool = False,
        wait: bool = False,
    ) -> None:
        """Write a completed message or a full checkpoint for one active meeting."""
        sid = str(persisted_dict.get("session_id") or "").strip()
        if not sid:
            return
        upd_ts = float(persisted_dict.get("updated_ts") or time.time())
        rev = int(persisted_dict.get("rev") or 0)
        wb = dict(persisted_dict.get("whiteboard") or {})
        msgs = persisted_dict.get("messages") or []
        header = {k: v for k, v in persisted_dict.items() if k not in ("messages", "whiteboard")}
        header_str = json.dumps(header, ensure_ascii=False)
        wb_str = json.dumps(wb, ensure_ascii=False)

        single_payload: Optional[Tuple[int, str, str]] = None
        if single_msg_seq_and_obj is not None:
            seq_idx, mobj = single_msg_seq_and_obj
            single_payload = (
                int(seq_idx),
                str(mobj.get("id") or f"m_{seq_idx}"),
                json.dumps(mobj, ensure_ascii=False),
            )
        all_msgs_payload: Optional[List[Tuple[int, str, str]]] = None
        if rewrite_all_messages or single_payload is None:
            all_msgs_payload = [
                (idx, str(m.get("id") or f"m_{idx}"), json.dumps(m, ensure_ascii=False))
                for idx, m in enumerate(msgs)
            ]

        def _tx(conn: sqlite3.Connection) -> None:
            if conn.execute("SELECT 1 FROM meeting_purges WHERE session_id=?", (sid,)).fetchone():
                return
            written = conn.execute(
                """
                INSERT INTO sessions(session_id, updated_ts, rev, header_json, whiteboard_json)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    updated_ts = excluded.updated_ts,
                    rev = excluded.rev,
                    header_json = excluded.header_json,
                    whiteboard_json = excluded.whiteboard_json
                WHERE sessions.deleted_at IS NULL AND sessions.rev <= excluded.rev
                """,
                (sid, upd_ts, rev, header_str, wb_str),
            )
            if not written.rowcount:
                return
            if single_payload is not None and not rewrite_all_messages:
                sq, mid, mjson = single_payload
                conn.execute(
                    """
                    INSERT INTO session_messages(session_id, seq, msg_id, msg_json)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(session_id, seq) DO UPDATE SET
                        msg_id = excluded.msg_id,
                        msg_json = excluded.msg_json
                    """,
                    (sid, sq, mid, mjson),
                )
            elif all_msgs_payload is not None:
                conn.execute("DELETE FROM session_messages WHERE session_id = ?", (sid,))
                conn.executemany(
                    """
                    INSERT INTO session_messages(session_id, seq, msg_id, msg_json)
                    VALUES (?, ?, ?, ?)
                    """,
                    [(sid, sq, mid, mjson) for sq, mid, mjson in all_msgs_payload],
                )
        self.submit_write(_tx, wait=wait)

    def list_trashed_sessions(self) -> List[dict]:
        with self._read_conn() as conn:
            rows = conn.execute(
                "SELECT s.session_id, s.header_json, s.deleted_at, p.pending FROM sessions s "
                "LEFT JOIN meeting_purges p ON p.session_id=s.session_id "
                "WHERE s.deleted_at IS NOT NULL ORDER BY s.deleted_at DESC, s.session_id"
            )
            return [{"session_id": r["session_id"], "title": json.loads(r["header_json"]).get("title") or "新会议",
                     "deleted_at": r["deleted_at"], "purge_pending": bool(r["pending"])} for r in rows]

    def is_trashed(self, session_id: str) -> bool:
        with self._read_conn() as conn:
            return conn.execute("SELECT 1 FROM sessions WHERE session_id = ? AND deleted_at IS NOT NULL",
                                (session_id,)).fetchone() is not None

    def set_trashed(self, session_id: str, trashed: bool) -> bool:
        def update(conn):
            if trashed:
                return conn.execute(
                    "UPDATE sessions SET deleted_at = ? WHERE session_id = ? AND deleted_at IS NULL AND NOT EXISTS "
                    "(SELECT 1 FROM exec_recovery WHERE session_id = ? AND state IN "
                    "('prepared','running','rolling_back','recovery_required'))",
                    (time.time(), session_id, session_id)).rowcount
            return conn.execute("UPDATE sessions SET deleted_at = NULL WHERE session_id = ? AND deleted_at IS NOT NULL "
                                "AND NOT EXISTS (SELECT 1 FROM meeting_purges WHERE session_id=?)",
                                (session_id, session_id)).rowcount
        return bool(self.submit_write(update, wait=True))

    def begin_purge(self, sid: str, title: str, deleted_at: float) -> str:
        """Commit the confirmation before removing any files. The timestamp identifies this specific trash operation."""
        def begin(conn):
            marker = conn.execute("SELECT pending FROM meeting_purges WHERE session_id=?", (sid,)).fetchone()
            if marker and not marker[0]:
                return "done"
            row = conn.execute("SELECT deleted_at, header_json FROM sessions WHERE session_id=?", (sid,)).fetchone()
            if not row or row[0] is None:
                return "not_trashed"
            if row[0] != deleted_at or title != (json.loads(row[1]).get("title") or "新会议"):
                return "confirmation_mismatch"
            if conn.execute("SELECT 1 FROM exec_recovery WHERE session_id=? AND state IN "
                            "('prepared','running','rolling_back','recovery_required')", (sid,)).fetchone():
                return "pending_workspace_recovery"
            conn.execute("INSERT OR IGNORE INTO meeting_purges(session_id,pending) VALUES (?,1)", (sid,))
            return "pending"
        return self.submit_write(begin, wait=True)

    def pending_purges(self) -> List[str]:
        with self._read_conn() as conn:
            return [r[0] for r in conn.execute("SELECT session_id FROM meeting_purges WHERE pending=1")]

    def finish_purge(self, sid: str) -> None:
        def finish(conn):
            if not conn.execute("SELECT 1 FROM meeting_purges WHERE session_id=? AND pending=1", (sid,)).fetchone():
                return
            # The database writer also serializes edits to any old import file shared by multiple instances.
            for old in (self.db_path.parent / "sessions.json", self.db_path.parent / "data" / "sessions.json"):
                if not old.is_file():
                    continue
                if old.is_symlink() or old.parent.is_symlink():
                    raise OSError("旧版历史文件指向外部位置")
                with old.open(encoding="utf-8") as stream:
                    source = json.load(stream)
                rows = source.get("sessions") if isinstance(source, dict) else source
                if not isinstance(rows, list):
                    raise ValueError("旧版历史文件格式无法识别")
                kept = [r for r in rows if not isinstance(r, dict) or r.get("session_id") != sid]
                if len(kept) == len(rows):
                    continue
                if isinstance(source, dict):
                    source["sessions"] = kept
                else:
                    source = kept
                with tempfile.NamedTemporaryFile("w", prefix="meeting-purge-", suffix=".tmp",
                                                 dir=old.parent, encoding="utf-8", delete=False) as tmp:
                    try:
                        json.dump(source, tmp, ensure_ascii=False)
                        tmp.flush()
                        os.fsync(tmp.fileno())
                    except BaseException:
                        tmp.close()
                        Path(tmp.name).unlink(missing_ok=True)
                        raise
                try:
                    os.replace(tmp.name, old)
                finally:
                    Path(tmp.name).unlink(missing_ok=True)
            conn.execute("DELETE FROM sessions WHERE session_id=? AND deleted_at IS NOT NULL", (sid,))
            conn.execute("DELETE FROM exec_recovery WHERE session_id=?", (sid,))
            conn.execute("UPDATE meeting_purges SET pending=0 WHERE session_id=?", (sid,))
        self.submit_write(finish, wait=True)

    def record_exec_recovery(
        self,
        *,
        run_id: str,
        session_id: str,
        workspace_realpath: str,
        backup_dir: str,
        state: str,
        pgid: int = 0,
        meta: Optional[dict] = None,
        wait: bool = True,
    ) -> None:
        meta_str = json.dumps(meta or {}, ensure_ascii=False)
        now = time.time()

        def _tx(conn: sqlite3.Connection) -> None:
            if conn.execute("SELECT 1 FROM meeting_purges WHERE session_id=?", (session_id,)).fetchone():
                return
            conn.execute(
                """
                INSERT INTO exec_recovery(run_id, session_id, workspace_realpath, backup_dir, state, pgid, updated_ts, meta_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    state = excluded.state,
                    pgid = excluded.pgid,
                    updated_ts = excluded.updated_ts,
                    meta_json = excluded.meta_json
                """,
                (run_id, session_id, workspace_realpath, backup_dir, state, int(pgid), now, meta_str),
            )

        self.submit_write(_tx, wait=wait)

    def list_incomplete_exec_recoveries(self) -> List[dict]:
        with self._read_conn() as rconn:
            rows = rconn.execute(
                """
                SELECT run_id, session_id, workspace_realpath, backup_dir, state, pgid, updated_ts, meta_json
                FROM exec_recovery
                WHERE state IN ('prepared', 'running', 'recovery_required')
                ORDER BY updated_ts DESC
                """
            ).fetchall()
            out: List[dict] = []
            for r in rows:
                try:
                    meta = json.loads(r["meta_json"])
                except Exception:
                    meta = {}
                out.append(
                    {
                        "run_id": str(r["run_id"]),
                        "session_id": str(r["session_id"]),
                        "workspace_realpath": str(r["workspace_realpath"]),
                        "backup_dir": str(r["backup_dir"]),
                        "state": str(r["state"]),
                        "pgid": int(r["pgid"] or 0),
                        "updated_ts": float(r["updated_ts"]),
                        "meta": meta,
                    }
                )
            return out
