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
import threading
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple


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
        conn.execute("PRAGMA busy_timeout = 15000;")
        force_delete = os.environ.get("AI_ROUNDTABLE_FORCE_DELETE_JOURNAL", "").strip() == "1"
        mode = "DELETE"
        if not force_delete:
            for attempt in range(3):
                try:
                    row = conn.execute("PRAGMA journal_mode = WAL;").fetchone()
                    cand = str(row[0] if row else "").strip().upper()
                    if cand == "WAL":
                        mode = "WAL"
                        conn.execute("PRAGMA synchronous = NORMAL;")
                    break
                except sqlite3.OperationalError:
                    if attempt < 2:
                        time.sleep(0.15 * (attempt + 1))
                    else:
                        mode = "DELETE"
        if mode != "WAL":
            try:
                conn.execute("PRAGMA journal_mode = DELETE;")
                conn.execute("PRAGMA synchronous = FULL;")
            except sqlite3.OperationalError:
                pass
        return mode

    def _begin_immediate_with_retry(self, conn: sqlite3.Connection) -> None:
        last_err: Optional[BaseException] = None
        for attempt in range(4):
            try:
                conn.execute("BEGIN IMMEDIATE;")
                return
            except sqlite3.OperationalError as exc:
                last_err = exc
                if "locked" in str(exc).lower() and attempt < 3:
                    time.sleep(0.2 * (attempt + 1))
                    continue
                raise
        if last_err is not None:
            raise last_err

    def _init_schema(self, conn: sqlite3.Connection) -> None:
        self._begin_immediate_with_retry(conn)
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
                    whiteboard_json TEXT NOT NULL
                );
                """
            )
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
            if conn.in_transaction:
                try:
                    conn.execute("ROLLBACK;")
                except Exception:
                    pass
            raise

    def _writer_loop(self) -> None:
        conn: Optional[sqlite3.Connection] = None
        try:
            conn = sqlite3.connect(str(self.db_path), timeout=15.0, check_same_thread=False)
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
            done_ev.wait(timeout=15.0)
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

    def _read_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=5.0)
        conn.row_factory = sqlite3.Row
        return conn

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
            for item in raw_list[-50:]:
                if not isinstance(item, dict):
                    continue
                sid = str(item.get("session_id") or "").strip()
                if not sid:
                    continue
                msgs = list(item.get("messages") or [])[-500:]
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

    def load_all_sessions(self, limit: int = 50) -> List[dict]:
        """读取持久化会话（按 updated_ts 升序还原，供编排器启动加载）。"""
        with self._read_conn() as rconn:
            rows = rconn.execute(
                """
                SELECT session_id, updated_ts, rev, header_json, whiteboard_json
                FROM sessions
                ORDER BY updated_ts DESC
                LIMIT ?
                """,
                (max(1, int(limit)),),
            ).fetchall()
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
        """O(1) 增量写入会话元数据、白板与单条完成消息；必要时支持全量重写单会话消息并裁剪超过 50 个的旧会话。"""
        sid = str(persisted_dict.get("session_id") or "").strip()
        if not sid:
            return
        upd_ts = float(persisted_dict.get("updated_ts") or time.time())
        rev = int(persisted_dict.get("rev") or 0)
        wb = dict(persisted_dict.get("whiteboard") or {})
        msgs = list(persisted_dict.get("messages") or [])[-500:]
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
            conn.execute(
                """
                INSERT INTO sessions(session_id, updated_ts, rev, header_json, whiteboard_json)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    updated_ts = excluded.updated_ts,
                    rev = excluded.rev,
                    header_json = excluded.header_json,
                    whiteboard_json = excluded.whiteboard_json
                """,
                (sid, upd_ts, rev, header_str, wb_str),
            )
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
            conn.execute(
                """
                DELETE FROM sessions
                WHERE session_id NOT IN (
                    SELECT session_id FROM sessions ORDER BY updated_ts DESC LIMIT 50
                )
                """
            )

        self.submit_write(_tx, wait=wait)

    def delete_session(self, session_id: str, *, wait: bool = True) -> None:
        def _tx(conn: sqlite3.Connection) -> None:
            conn.execute("DELETE FROM session_messages WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))

        self.submit_write(_tx, wait=wait)

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
