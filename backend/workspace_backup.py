# -*- coding: utf-8 -*-
"""
AI圆桌 — 纯 Python 无 Git 依赖 CAS 写前字节清单与跨进程排他锁（P0.2 & P0.4 核心防线）

裁定落地契约：
1. 零子进程派生、零 Git 依赖：通过 `os.lstat` + `O_NOFOLLOW` + `sha256` 遍历工作区全部普通文件与合法内部符号链接
   （完整覆盖已跟踪文件、`.gitignore` 忽略文件及子模块普通文件，仅跳过 `.git` 内部元数据目录）。
2. 写前准入红线（任何违规立即抛 `WorkspaceAdmissionError(status_code=409)`，保证工作区字节零改动）：
   - 指向 `workspace_realpath` 之外的越界符号链接；
   - Socket / FIFO / 块设备 / 字符设备等特殊文件；
   - 无读权限文件；
   - 普通文件累计大小 `> 128 MiB`（`MAX_BACKUP_WORKSPACE_BYTES = 134_217_728`）。
3. 落盘可靠性：CAS 对象与 `manifest.json` 均采用同目录临时文件写入 -> `os.fsync(fd)` -> `os.replace` -> 父目录 `fsync_dir`，
   持久化至 `~/.ai-roundtable/backups/<session_id>/<run_id>/`。
4. 跨进程排他锁：`~/.ai-roundtable/locks/<sha256(workspace_realpath)>.lock` 使用 `fcntl.flock(LOCK_EX | LOCK_NB)` + `O_CLOEXEC`，
   冲突立即返回 `409` 及当前持锁方 `{session_id, run_id, pid}`。
5. 事后编辑冲突回滚：原子校验所有受影响路径在 `after` 之后是否被再次修改；若存在任何冲突，整批拒绝（`409` 返回全量 `conflict_paths`）
   并保留 `rollbackable` 状态，绝不局部跳过。
6. 崩溃中断恢复（无 `after` 清单）：标记 `recovery_required`，禁止后台静默删除新增文件，必须校验用户确认的 `(path -> sha256)` 字典后恢复。
"""

from __future__ import annotations

import difflib
import errno
import hashlib
import json
import os
import stat
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

if os.name == "nt":
    import msvcrt
else:
    import fcntl


MAX_BACKUP_WORKSPACE_BYTES = 128 * 1024 * 1024  # 128 MiB 写前准入红线
DEFAULT_RUNTIME_HOME = Path(os.path.expanduser("~/.ai-roundtable"))


class WorkspaceAdmissionError(ValueError):
    """写前字节清单准入拦截异常（对应 HTTP 409 Conflict）。"""

    def __init__(self, message: str, *, reason: str = "admission_rejected", offending_path: str = "") -> None:
        super().__init__(message)
        self.status_code = 409
        self.reason = reason
        self.offending_path = offending_path


class WorkspaceLockBusyError(RuntimeError):
    """跨进程工作区排他锁占用冲突异常（对应 HTTP 409 Conflict）。"""

    def __init__(self, message: str, *, holder: Optional[dict] = None) -> None:
        super().__init__(message)
        self.status_code = 409
        self.holder = holder or {}


def fsync_directory(dir_path: Path) -> None:
    """对目录项执行 fsync 确保 rename/unlink 元数据落盘。"""
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    try:
        dfd = os.open(str(dir_path), flags)
    except OSError:
        return
    try:
        os.fsync(dfd)
    except OSError:
        pass
    finally:
        try:
            os.close(dfd)
        except OSError:
            pass


def atomic_write_bytes_fsync(target_path: Path, data: bytes, mode: int = 0o600) -> None:
    """同目录临时文件写入 -> fsync(fd) -> chmod -> os.replace -> 父目录 fsync。"""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_name = f".{target_path.name}.tmp.{os.getpid()}.{uuid.uuid4().hex[:8]}"
    tmp_path = target_path.parent / tmp_name
    fd = os.open(str(tmp_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0), mode)
    try:
        view = memoryview(data)
        written = 0
        while written < len(data):
            n = os.write(fd, view[written:])
            written += n
        os.fsync(fd)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            tmp_path.unlink()
        except OSError:
            pass
        raise
    os.close(fd)
    try:
        os.chmod(str(tmp_path), mode)
    except OSError:
        pass
    os.replace(str(tmp_path), str(target_path))
    fsync_directory(target_path.parent)


def atomic_write_json_fsync(target_path: Path, payload: dict) -> None:
    raw = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
    atomic_write_bytes_fsync(target_path, raw, mode=0o600)


class WorkspaceWriteLock:
    """跨进程非阻塞排他文件锁（~/.ai-roundtable/locks/<sha256(workspace_realpath)>.lock）。"""

    def __init__(
        self,
        workspace_realpath: str,
        *,
        session_id: str = "",
        run_id: str = "",
        operation_id: str = "",
        runtime_home: Optional[Path] = None,
    ) -> None:
        self.workspace_realpath = os.path.realpath(workspace_realpath)
        self.session_id = session_id
        self.run_id = run_id
        self.operation_id = operation_id
        base = runtime_home or Path(os.environ.get("AI_ROUNDTABLE_HOME") or str(DEFAULT_RUNTIME_HOME))
        locks_dir = base / "locks"
        locks_dir.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(os.path.normcase(self.workspace_realpath).encode("utf-8")).hexdigest()
        self.lock_path = locks_dir / f"{digest}.lock"
        self._fd: Optional[int] = None

    @property
    def acquired(self) -> bool:
        return self._fd is not None

    def try_acquire(self) -> None:
        if self._fd is not None:
            return
        flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_CLOEXEC", 0)
        fd = os.open(str(self.lock_path), flags, 0o600)
        try:
            if os.name == "nt":
                # Lock a byte beyond the metadata so contenders can still read the holder.
                os.lseek(fd, 1 << 30, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            holder = self._read_holder_from_fd(fd)
            try:
                os.close(fd)
            except OSError:
                pass
            if exc.errno in (errno.EACCES, errno.EAGAIN, errno.EWOULDBLOCK):
                h_sid = holder.get("session_id") or "unknown"
                h_run = holder.get("run_id") or "unknown"
                raise WorkspaceLockBusyError(
                    f"工作区正被其他执行或回滚任务排他占用（session={h_sid}, run={h_run}）",
                    holder=holder,
                ) from exc
            raise

        self._fd = fd
        self.update_holder_metadata(session_id=self.session_id, run_id=self.run_id, operation_id=self.operation_id)

    def update_holder_metadata(self, *, session_id: str, run_id: str, operation_id: str = "") -> None:
        if self._fd is None:
            return
        self.session_id = session_id
        self.run_id = run_id
        self.operation_id = operation_id
        payload = json.dumps(
            {
                "workspace_realpath": self.workspace_realpath,
                "session_id": session_id,
                "run_id": run_id,
                "operation_id": operation_id,
                "pid": os.getpid(),
                "started_at": time.time(),
            },
            ensure_ascii=False,
        ).encode("utf-8")
        try:
            os.lseek(self._fd, 0, os.SEEK_SET)
            os.ftruncate(self._fd, 0)
            os.write(self._fd, payload)
            os.fsync(self._fd)
        except OSError:
            pass

    @staticmethod
    def _read_holder_from_fd(fd: int) -> dict:
        try:
            os.lseek(fd, 0, os.SEEK_SET)
            raw = os.read(fd, 8192)
            if raw:
                parsed = json.loads(raw.decode("utf-8", errors="replace"))
                if isinstance(parsed, dict):
                    return parsed
        except Exception:
            pass
        return {}

    def release(self) -> None:
        if self._fd is None:
            return
        fd = self._fd
        self._fd = None
        try:
            os.lseek(fd, 0, os.SEEK_SET)
            os.ftruncate(fd, 0)
            os.fsync(fd)
        except OSError:
            pass
        try:
            if os.name == "nt":
                os.lseek(fd, 1 << 30, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pass
        try:
            os.close(fd)
        except OSError:
            pass

    def __enter__(self) -> "WorkspaceWriteLock":
        self.try_acquire()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()


def _is_within_realpath(candidate: Path, root_real: Path) -> bool:
    try:
        return candidate.is_relative_to(root_real)
    except ValueError:
        return False


def _resolve_symlink_without_escaping(link_full_path: Path, raw_target: str, root_real: Path) -> bool:
    """逐级核验符号链接目标及其父路径绝不越出 workspace_realpath。"""
    if os.path.isabs(raw_target):
        norm_abs = Path(os.path.normpath(raw_target))
        return _is_within_realpath(norm_abs, root_real)
    joined = Path(os.path.normpath(os.path.join(str(link_full_path.parent), raw_target)))
    if not _is_within_realpath(joined, root_real):
        return False
    # 若目标已存在，二次核验其 realpath 亦在 root_real 内部（防止多跳链逃逸）
    if os.path.lexists(str(joined)):
        real_target = Path(os.path.realpath(str(joined)))
        if not _is_within_realpath(real_target, root_real):
            return False
    return True


def _read_file_nofollow_bytes(full_path: Path) -> Tuple[bytes, os.stat_result]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        if os.name == "nt":
            from .drivers.windows_support import open_regular_file
            fd = open_regular_file(full_path)
        else:
            fd = os.open(str(full_path), flags)
    except PermissionError as exc:
        raise WorkspaceAdmissionError(
            f"工作区包含无读取权限的文件：{full_path.name}",
            reason="unreadable_file",
            offending_path=str(full_path),
        ) from exc
    except OSError as exc:
        if exc.errno in (errno.ELOOP, errno.EACCES, errno.EPERM):
            raise WorkspaceAdmissionError(
                f"工作区文件访问被安全策略拦截：{full_path.name}",
                reason="nofollow_or_perm_blocked",
                offending_path=str(full_path),
            ) from exc
        raise WorkspaceAdmissionError(
            f"无法读取工作区文件：{full_path.name} ({exc})",
            reason="io_error",
            offending_path=str(full_path),
        ) from exc

    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise WorkspaceAdmissionError(
                f"非常规文件禁止纳入写快照：{full_path.name}",
                reason="special_file",
                offending_path=str(full_path),
            )
        chunks: List[bytes] = []
        while True:
            buf = os.read(fd, 131072)
            if not buf:
                break
            chunks.append(buf)
        return b"".join(chunks), st
    finally:
        try:
            os.close(fd)
        except OSError:
            pass


def _entry_equal(a: Optional[dict], b: Optional[dict]) -> bool:
    if a is None or b is None:
        return a is b
    if a.get("type") != b.get("type"):
        return False
    if a.get("type") == "symlink":
        return a.get("link_target") == b.get("link_target")
    return a.get("sha256") == b.get("sha256") and int(a.get("mode", 0o644)) == int(b.get("mode", 0o644))


@dataclass
class WorkspaceBackup:
    """纯 Python 标准库 CAS 写前字节清单与原子回滚引擎。"""

    cwd: str
    session_id: str = "s_default"
    run_id: str = field(default_factory=lambda: f"run_{uuid.uuid4().hex[:12]}")
    operation_id: str = ""
    max_workspace_bytes: int = MAX_BACKUP_WORKSPACE_BYTES
    runtime_home: Optional[Path] = None

    def __post_init__(self) -> None:
        self.cwd = os.path.realpath(os.path.expanduser(str(self.cwd)))
        self.root = self.cwd
        base = self.runtime_home or Path(os.environ.get("AI_ROUNDTABLE_HOME") or str(DEFAULT_RUNTIME_HOME))
        self.backup_id = f"{self.session_id}/{self.run_id}"
        self.backup_dir = base / "backups" / self.session_id / self.run_id
        self.blobs_dir = self.backup_dir / "blobs"
        self.manifest_path = self.backup_dir / "manifest.json"
        self.state = "initializing"
        self.pgid: int = 0
        self.before_entries: Dict[str, dict] = {}
        self.after_entries: Optional[Dict[str, dict]] = None
        self.before_total_bytes: int = 0
        self.after_total_bytes: int = 0
        self._diff_text: str = ""
        self.changed_paths: List[str] = []

    @classmethod
    def capture(
        cls,
        cwd: str,
        *,
        session_id: str = "s_default",
        run_id: str = "",
        operation_id: str = "",
        max_workspace_bytes: int = MAX_BACKUP_WORKSPACE_BYTES,
        runtime_home: Optional[Path] = None,
    ) -> "WorkspaceBackup":
        """构建并落盘写前 `prepared` CAS 字节清单（兼容旧版 capture 调用，且无需 Git 仓库）。"""
        inst = cls(
            cwd=cwd,
            session_id=session_id or "s_default",
            run_id=run_id or f"run_{uuid.uuid4().hex[:12]}",
            operation_id=operation_id,
            max_workspace_bytes=max_workspace_bytes,
            runtime_home=runtime_home,
        )
        inst.prepare()
        return inst

    @classmethod
    def load_from_manifest(cls, manifest_file: Path) -> "WorkspaceBackup":
        raw = json.loads(manifest_file.read_text(encoding="utf-8"))
        inst = cls(
            cwd=raw["workspace_realpath"],
            session_id=raw.get("session_id", "s_default"),
            run_id=raw["run_id"],
            operation_id=raw.get("operation_id", ""),
            runtime_home=manifest_file.parent.parent.parent.parent,
        )
        inst.backup_dir = manifest_file.parent
        inst.blobs_dir = inst.backup_dir / "blobs"
        inst.manifest_path = manifest_file
        inst.state = str(raw.get("state") or "prepared")
        inst.pgid = int(raw.get("pgid") or 0)
        inst.before_entries = dict(raw.get("before") or {})
        inst.after_entries = dict(raw["after"]) if isinstance(raw.get("after"), dict) else None
        inst.before_total_bytes = int(raw.get("before_total_bytes") or 0)
        inst.after_total_bytes = int(raw.get("after_total_bytes") or 0)
        inst._diff_text = str(raw.get("diff_text") or "")
        inst.changed_paths = list(raw.get("changed_paths") or [])
        return inst

    def _blob_path(self, sha256_hex: str) -> Path:
        return self.blobs_dir / sha256_hex[:2] / sha256_hex

    def _store_blob_if_needed(self, sha256_hex: str, data: bytes) -> None:
        bp = self._blob_path(sha256_hex)
        if bp.is_file():
            return
        atomic_write_bytes_fsync(bp, data, mode=0o600)

    def _scan_workspace(self, *, store_blobs: bool, enforce_cap: bool) -> Tuple[Dict[str, dict], int]:
        root_path = Path(self.cwd)
        if not root_path.is_dir():
            raise WorkspaceAdmissionError(f"工作区目录不存在：{self.cwd}", reason="missing_workspace")

        entries: Dict[str, dict] = {}
        total_bytes = 0
        stack: List[Path] = [root_path]

        while stack:
            cur_dir = stack.pop()
            try:
                scandir_it = os.scandir(str(cur_dir))
            except PermissionError as exc:
                raise WorkspaceAdmissionError(
                    f"工作区子目录无访问权限：{cur_dir}",
                    reason="unreadable_dir",
                    offending_path=str(cur_dir),
                ) from exc
            except OSError as exc:
                raise WorkspaceAdmissionError(
                    f"扫描工作区目录失败：{cur_dir} ({exc})",
                    reason="scan_error",
                    offending_path=str(cur_dir),
                ) from exc

            with scandir_it:
                sorted_items = sorted(scandir_it, key=lambda e: e.name)
                for item in sorted_items:
                    full_p = Path(item.path)
                    rel_posix = full_p.relative_to(root_path).as_posix()
                    try:
                        lst = os.lstat(item.path)
                    except OSError as exc:
                        raise WorkspaceAdmissionError(
                            f"无法获取工作区文件状态：{rel_posix}",
                            reason="lstat_failed",
                            offending_path=rel_posix,
                        ) from exc

                    mode = lst.st_mode
                    if os.name == "nt" and lst.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                        raise WorkspaceAdmissionError(
                            f"Windows 工作区包含重解析点：{rel_posix}。请选择普通本地目录后再执行写入。",
                            reason="windows_reparse_point", offending_path=rel_posix,
                        )
                    # 仅跳过 .git 元数据目录本身（保留子模块工作树普通文件与所有 .gitignore 忽略文件）
                    if item.name == ".git" and stat.S_ISDIR(mode):
                        continue

                    if stat.S_ISLNK(mode):
                        try:
                            raw_target = os.readlink(item.path)
                        except OSError as exc:
                            raise WorkspaceAdmissionError(
                                f"无法读取符号链接：{rel_posix}",
                                reason="unreadable_symlink",
                                offending_path=rel_posix,
                            ) from exc
                        if not _resolve_symlink_without_escaping(full_p, raw_target, root_path):
                            raise WorkspaceAdmissionError(
                                f"检测到指向工作区外部的越界符号链接：{rel_posix} -> {raw_target}",
                                reason="escaping_symlink",
                                offending_path=rel_posix,
                            )
                        entries[rel_posix] = {
                            "type": "symlink",
                            "link_target": raw_target,
                            "mode": stat.S_IMODE(mode),
                        }
                    elif stat.S_ISDIR(mode):
                        stack.append(full_p)
                    elif stat.S_ISREG(mode):
                        if enforce_cap and (total_bytes + lst.st_size) > self.max_workspace_bytes:
                            mb_cap = self.max_workspace_bytes // (1024 * 1024)
                            raise WorkspaceAdmissionError(
                                f"工作区普通文件总大小超过安全上限（>{mb_cap} MiB），已拦截写前快照",
                                reason="workspace_too_large",
                                offending_path=rel_posix,
                            )
                        raw_bytes, fst = _read_file_nofollow_bytes(full_p)
                        total_bytes += len(raw_bytes)
                        if enforce_cap and total_bytes > self.max_workspace_bytes:
                            mb_cap = self.max_workspace_bytes // (1024 * 1024)
                            raise WorkspaceAdmissionError(
                                f"工作区普通文件总大小超过安全上限（>{mb_cap} MiB），已拦截写前快照",
                                reason="workspace_too_large",
                                offending_path=rel_posix,
                            )
                        digest = hashlib.sha256(raw_bytes).hexdigest()
                        if store_blobs:
                            self._store_blob_if_needed(digest, raw_bytes)
                        entries[rel_posix] = {
                            "type": "file",
                            "sha256": digest,
                            "size": len(raw_bytes),
                            "mode": stat.S_IMODE(fst.st_mode) or 0o644,
                        }
                    else:
                        # Socket / FIFO / 字符设备 / 块设备一律 409 拦截
                        raise WorkspaceAdmissionError(
                            f"工作区包含不支持快照的特殊节点（Socket/FIFO/设备）：{rel_posix}",
                            reason="special_file",
                            offending_path=rel_posix,
                        )

        return entries, total_bytes

    def _persist_manifest(self) -> None:
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 1,
            "session_id": self.session_id,
            "run_id": self.run_id,
            "operation_id": self.operation_id,
            "workspace_realpath": self.cwd,
            "state": self.state,
            "pgid": self.pgid,
            "updated_at": time.time(),
            "before_total_bytes": self.before_total_bytes,
            "after_total_bytes": self.after_total_bytes,
            "before": self.before_entries,
            "after": self.after_entries,
            "changed_paths": self.changed_paths,
            "diff_text": self._diff_text,
        }
        atomic_write_json_fsync(self.manifest_path, payload)
        fsync_directory(self.backup_dir.parent)

    def prepare(self) -> None:
        """执行写前扫描并将 CAS 字节与 `manifest.json(state="prepared")` fsync 落盘。"""
        before_map, total_b = self._scan_workspace(store_blobs=True, enforce_cap=True)
        self.before_entries = before_map
        self.before_total_bytes = total_b
        self.state = "prepared"
        self._persist_manifest()

    def record_running_pgid(self, pgid: int) -> None:
        """在拉起受监管子进程组后、放行 CLI 写入前，先将 pgid fsync 记入清单。"""
        self.pgid = int(pgid)
        self.state = "running"
        self._persist_manifest()

    def discard_prepared_unused(self) -> None:
        """当在放行前被 stop 取消或准入回退时标记作废。"""
        self.state = "aborted_clean"
        if self.manifest_path.is_file():
            self._persist_manifest()

    def _load_blob_bytes(self, sha256_hex: str) -> bytes:
        bp = self._blob_path(sha256_hex)
        if not bp.is_file():
            raise ValueError(f"CAS 快照对象缺失：{sha256_hex[:12]}")
        data = bp.read_bytes()
        if hashlib.sha256(data).hexdigest() != sha256_hex:
            raise ValueError(f"CAS 快照对象哈希校验失败：{sha256_hex[:12]}")
        return data

    def _build_unified_diff(self, before_map: Dict[str, dict], after_map: Dict[str, dict], changed: List[str]) -> str:
        chunks: List[str] = []
        total_chars = 0
        for rel in changed:
            b_ent = before_map.get(rel)
            a_ent = after_map.get(rel)
            if b_ent and b_ent.get("type") == "symlink" or (a_ent and a_ent.get("type") == "symlink"):
                b_desc = f"symlink -> {b_ent.get('link_target')}" if b_ent else "/dev/null"
                a_desc = f"symlink -> {a_ent.get('link_target')}" if a_ent else "/dev/null"
                chunks.append(f"diff --cas a/{rel} b/{rel}\n--- a/{rel}\n+++ b/{rel}\n@@ symlink @@\n-{b_desc}\n+{a_desc}\n")
                continue

            b_bytes = self._load_blob_bytes(b_ent["sha256"]) if (b_ent and b_ent.get("type") == "file") else b""
            a_bytes = self._load_blob_bytes(a_ent["sha256"]) if (a_ent and a_ent.get("type") == "file") else b""
            if b"\x00" in b_bytes[:4096] or b"\x00" in a_bytes[:4096]:
                chunks.append(f"Binary files a/{rel} and b/{rel} differ\n")
                continue

            b_lines = b_bytes.decode("utf-8", errors="replace").splitlines(keepends=True)
            a_lines = a_bytes.decode("utf-8", errors="replace").splitlines(keepends=True)
            from_lbl = f"a/{rel}" if b_ent else "/dev/null"
            to_lbl = f"b/{rel}" if a_ent else "/dev/null"
            udiff = "".join(difflib.unified_diff(b_lines, a_lines, fromfile=from_lbl, tofile=to_lbl, n=3))
            if udiff:
                chunks.append(udiff if udiff.endswith("\n") else udiff + "\n")
                total_chars += len(udiff)
            elif b_ent != a_ent:
                # 仅权限位 mode 变化
                chunks.append(
                    f"diff --cas a/{rel} b/{rel}\nold mode {oct(b_ent.get('mode', 0o644)) if b_ent else 'none'}\n"
                    f"new mode {oct(a_ent.get('mode', 0o644)) if a_ent else 'none'}\n"
                )
            if total_chars >= 180_000:
                chunks.append("\n... (Diff 预览已达上限，底层字节清单已完整归档)\n")
                break
        return "".join(chunks)

    def finish(self) -> bool:
        """扫描执行后的 `after` 清单并落盘；返回本次执行是否产生了任何工作区变更。"""
        after_map, total_a = self._scan_workspace(store_blobs=True, enforce_cap=False)
        self.after_entries = after_map
        self.after_total_bytes = total_a
        all_paths = sorted(set(self.before_entries.keys()) | set(after_map.keys()))
        changed = [p for p in all_paths if not _entry_equal(self.before_entries.get(p), after_map.get(p))]
        self.changed_paths = changed
        self._diff_text = self._build_unified_diff(self.before_entries, after_map, changed) if changed else ""
        self.state = "rollbackable" if changed else "completed_noop"
        self._persist_manifest()
        return bool(changed)

    @property
    def worktree_diff(self) -> str:
        return self._diff_text

    @property
    def is_rollbackable(self) -> bool:
        return self.state == "rollbackable" and self.after_entries is not None and bool(self.changed_paths)

    def mark_acknowledged(self) -> None:
        """用户显式确认保留当前执行变更、归档上一轮可回滚状态以开启新一轮写入。"""
        if self.state == "rollbackable":
            self.state = "archived"
            self._persist_manifest()

    def restore_with_report(self) -> Tuple[bool, str, dict]:
        """执行整批原子冲突检测与字节级还原；发现事后编辑冲突时返回 409 + 全量 conflict_paths 并保留 rollbackable。"""
        if self.after_entries is None or self.state not in ("rollbackable",):
            return False, "当前没有可回滚的已完成执行快照", {"status_code": 409, "conflict_paths": []}

        try:
            current_map, _ = self._scan_workspace(store_blobs=False, enforce_cap=False)
        except WorkspaceAdmissionError as adm_exc:
            offending = [adm_exc.offending_path] if adm_exc.offending_path else []
            return (
                False,
                f"回滚前工作区校验受阻：{adm_exc}",
                {"status_code": 409, "conflict_paths": offending, "rollbackable": True},
            )

        all_affected = sorted(
            p
            for p in (set(self.before_entries.keys()) | set(self.after_entries.keys()))
            if not _entry_equal(self.before_entries.get(p), self.after_entries.get(p))
        )
        if not all_affected:
            return False, "本次执行未产生任何文件变更，无需回滚", {"status_code": 400, "conflict_paths": []}

        conflict_paths: List[str] = []
        for rel in all_affected:
            after_ent = self.after_entries.get(rel)
            now_ent = current_map.get(rel)
            if not _entry_equal(after_ent, now_ent):
                conflict_paths.append(rel)

        if conflict_paths:
            preview = "、".join(conflict_paths[:5])
            suffix = f" 等共 {len(conflict_paths)} 个文件" if len(conflict_paths) > 5 else ""
            msg = f"检测到以下文件在执行结束后又被修改，已整批拒绝回滚并保留当前内容：{preview}{suffix}"
            return (
                False,
                msg,
                {
                    "status_code": 409,
                    "conflict_paths": conflict_paths,
                    "rollbackable": True,
                },
            )

        # 第一阶段：全量预检并加载所有需要还原的 CAS 字节（保证写盘中途绝不因缺失 blob 半途而废）
        staged_blobs: Dict[str, bytes] = {}
        for rel in all_affected:
            b_ent = self.before_entries.get(rel)
            if b_ent and b_ent.get("type") == "file":
                sha = b_ent["sha256"]
                if sha not in staged_blobs:
                    staged_blobs[sha] = self._load_blob_bytes(sha)

        root_path = Path(self.cwd)
        touched_dirs: Set[Path] = set()

        # 第二阶段：先删除本次执行新增的文件/链接（已证明与 after 字节完全一致）
        added_only = [p for p in all_affected if p not in self.before_entries and p in self.after_entries]
        for rel in sorted(added_only, key=lambda x: x.count("/"), reverse=True):
            target_p = root_path / rel
            if os.path.lexists(str(target_p)):
                if os.path.isdir(str(target_p)) and not os.path.islink(str(target_p)):
                    continue
                os.unlink(str(target_p))
                touched_dirs.add(target_p.parent)

        # 清理因本次新增文件产生的空子目录
        for d in sorted(touched_dirs, key=lambda p: len(p.parts), reverse=True):
            cur = d
            while cur != root_path and _is_within_realpath(cur, root_path):
                try:
                    os.rmdir(str(cur))
                    touched_dirs.add(cur.parent)
                    cur = cur.parent
                except OSError:
                    break

        # 第三阶段：还原所有修改或被删的文件与符号链接
        for rel in all_affected:
            b_ent = self.before_entries.get(rel)
            if b_ent is None:
                continue
            target_p = root_path / rel
            target_p.parent.mkdir(parents=True, exist_ok=True)
            if os.path.lexists(str(target_p)) and os.path.isdir(str(target_p)) and not os.path.islink(str(target_p)):
                # 若目录占据了原文件路径，安全移空目录
                os.rmdir(str(target_p))
            if b_ent.get("type") == "symlink":
                tmp_lnk = target_p.parent / f".{target_p.name}.lnk.{uuid.uuid4().hex[:8]}"
                os.symlink(b_ent["link_target"], str(tmp_lnk))
                os.replace(str(tmp_lnk), str(target_p))
                touched_dirs.add(target_p.parent)
            else:
                raw_data = staged_blobs[b_ent["sha256"]]
                fmode = int(b_ent.get("mode") or 0o644)
                atomic_write_bytes_fsync(target_p, raw_data, mode=fmode)
                touched_dirs.add(target_p.parent)

        for d in touched_dirs:
            if d.is_dir():
                fsync_directory(d)
        fsync_directory(root_path)

        self.state = "rolled_back"
        self._persist_manifest()
        return (
            True,
            f"已按字节清单完整回滚本次执行的 {len(all_affected)} 个文件",
            {
                "status_code": 200,
                "restored_count": len(all_affected),
                "conflict_paths": [],
                "rollbackable": False,
            },
        )

    def restore(self) -> Tuple[bool, str]:
        """兼容旧版 `(ok, message)` 二元组调用签名。"""
        ok, msg, _ = self.restore_with_report()
        return ok, msg

    def inspect_crash_recovery_plan(self) -> dict:
        """针对崩溃中断（无 after 清单）扫描与 before 的差异，生成供用户显式确认哈希的恢复计划。"""
        current_map, _ = self._scan_workspace(store_blobs=False, enforce_cap=False)
        modified_or_deleted: List[dict] = []
        untracked_new_files: List[dict] = []

        for rel, b_ent in sorted(self.before_entries.items()):
            c_ent = current_map.get(rel)
            if not _entry_equal(b_ent, c_ent):
                modified_or_deleted.append(
                    {
                        "path": rel,
                        "before_sha256": b_ent.get("sha256", f"symlink:{b_ent.get('link_target', '')}"),
                        "current_sha256": (
                            c_ent.get("sha256", f"symlink:{c_ent.get('link_target', '')}") if c_ent else "__DELETED__"
                        ),
                    }
                )

        for rel, c_ent in sorted(current_map.items()):
            if rel not in self.before_entries:
                untracked_new_files.append(
                    {
                        "path": rel,
                        "current_sha256": c_ent.get("sha256", f"symlink:{c_ent.get('link_target', '')}"),
                        "size": int(c_ent.get("size") or 0),
                    }
                )

        expected_hashes: Dict[str, str] = {}
        for item in modified_or_deleted:
            expected_hashes[item["path"]] = item["current_sha256"]
        for item in untracked_new_files:
            expected_hashes[item["path"]] = item["current_sha256"]

        return {
            "session_id": self.session_id,
            "run_id": self.run_id,
            "workspace_realpath": self.cwd,
            "state": "recovery_required",
            "modified_or_deleted": modified_or_deleted,
            "untracked_new_files": untracked_new_files,
            "expected_hashes": expected_hashes,
        }

    def recover_from_crash(
        self,
        expected_hashes: Dict[str, str],
        *,
        delete_confirmed_new_files: bool = True,
    ) -> Tuple[bool, str, dict]:
        """校验用户显式确认的 expected_hashes 与当前工作区哈希完全一致后，将崩溃现场恢复至 before 清单。"""
        if not isinstance(expected_hashes, dict):
            return False, "缺少用户确认的文件哈希映射 expected_hashes", {"status_code": 400, "conflict_paths": []}

        plan = self.inspect_crash_recovery_plan()
        live_hashes = plan["expected_hashes"]
        mismatched = sorted(
            p for p, cur_h in live_hashes.items() if expected_hashes.get(p) != cur_h
        )
        if mismatched:
            return (
                False,
                "工作区文件哈希已发生变化，请刷新恢复清单重新确认后再执行恢复",
                {"status_code": 409, "conflict_paths": mismatched, "recovery_plan": plan},
            )

        staged_blobs: Dict[str, bytes] = {}
        for item in plan["modified_or_deleted"]:
            rel = item["path"]
            b_ent = self.before_entries[rel]
            if b_ent.get("type") == "file":
                sha = b_ent["sha256"]
                if sha not in staged_blobs:
                    staged_blobs[sha] = self._load_blob_bytes(sha)

        root_path = Path(self.cwd)
        touched_dirs: Set[Path] = set()

        if delete_confirmed_new_files:
            for item in sorted(plan["untracked_new_files"], key=lambda x: x["path"].count("/"), reverse=True):
                tp = root_path / item["path"]
                if os.path.lexists(str(tp)) and not (os.path.isdir(str(tp)) and not os.path.islink(str(tp))):
                    os.unlink(str(tp))
                    touched_dirs.add(tp.parent)

        for item in plan["modified_or_deleted"]:
            rel = item["path"]
            b_ent = self.before_entries[rel]
            tp = root_path / rel
            tp.parent.mkdir(parents=True, exist_ok=True)
            if b_ent.get("type") == "symlink":
                tmp_lnk = tp.parent / f".{tp.name}.lnk.{uuid.uuid4().hex[:8]}"
                os.symlink(b_ent["link_target"], str(tmp_lnk))
                os.replace(str(tmp_lnk), str(tp))
            else:
                atomic_write_bytes_fsync(tp, staged_blobs[b_ent["sha256"]], mode=int(b_ent.get("mode") or 0o644))
            touched_dirs.add(tp.parent)

        for d in sorted(touched_dirs, key=lambda p: len(p.parts), reverse=True):
            cur = d
            while cur != root_path and _is_within_realpath(cur, root_path):
                try:
                    os.rmdir(str(cur))
                    cur = cur.parent
                except OSError:
                    break
            if d.is_dir():
                fsync_directory(d)
        fsync_directory(root_path)

        self.state = "recovered"
        self._persist_manifest()
        total_fixed = len(plan["modified_or_deleted"]) + (len(plan["untracked_new_files"]) if delete_confirmed_new_files else 0)
        return (
            True,
            f"已完成崩溃恢复，还原并清理共 {total_fixed} 个确认项",
            {"status_code": 200, "restored_count": total_fixed},
        )
