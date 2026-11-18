# -*- coding: utf-8 -*-
"""
AI圆桌 — 异步项目源码索引与 (mtime_ns, size) 元数据缓存包（P1.2 事件循环零阻塞优化）
"""

from __future__ import annotations

import asyncio
import os
import stat
import threading
import time
from typing import Dict, List, Optional, Tuple


_LINE_COUNT_CACHE_LOCK = threading.Lock()
# key: real_file_path -> (st_mtime_ns, st_size, line_count)
_LINE_COUNT_CACHE: Dict[str, Tuple[int, int, int]] = {}

# Store names only. Compute sizes and line counts for the displayed results.
_WS_SCAN_LOCK = threading.Lock()
_WS_DIR_INDEX_CACHE: Dict[tuple, Tuple[float, Tuple[str, ...]]] = {}
_WS_INDEX_TTL_SEC = 8.0


def count_file_lines_cached(full_path: str, st: Optional[os.stat_result] = None) -> Optional[int]:
    """按 (st_mtime_ns, st_size) 缓存文件行数，命中缓存时零磁盘读取。"""
    try:
        stat_res = st or os.stat(full_path)
    except OSError:
        return None
    sz = stat_res.st_size
    if sz <= 0 or sz > 524_288:
        return 0 if sz == 0 else None
    sig_m = stat_res.st_mtime_ns
    with _LINE_COUNT_CACHE_LOCK:
        cached = _LINE_COUNT_CACHE.get(full_path)
        if cached and cached[0] == sig_m and cached[1] == sz:
            return cached[2]

    try:
        with open(full_path, "rb") as bf:
            raw = bf.read()
        lines = raw.count(b"\n") + (1 if raw and not raw.endswith(b"\n") else 0)
    except OSError:
        return None

    with _LINE_COUNT_CACHE_LOCK:
        if len(_LINE_COUNT_CACHE) > 8000:
            _LINE_COUNT_CACHE.clear()
        _LINE_COUNT_CACHE[full_path] = (sig_m, sz, lines)
    return lines


def _read_git_index_bytes(real_ws: str) -> bytes:
    """纯标准库读取 .git/index 原始字节（支持 worktree/submodule gitdir 文件），零子进程开销。"""
    dot_git = os.path.join(real_ws, ".git")
    git_dir = ""
    try:
        if os.path.isdir(dot_git):
            git_dir = dot_git
        elif os.path.isfile(dot_git):
            raw_ptr = open(dot_git, "r", encoding="utf-8", errors="ignore").read(1024).strip()
            if raw_ptr.startswith("gitdir:"):
                cand = raw_ptr.split(":", 1)[1].strip()
                git_dir = cand if os.path.isabs(cand) else os.path.normpath(os.path.join(real_ws, cand))
        if not git_dir:
            return b""
        idx_path = os.path.join(git_dir, "index")
        if os.path.isfile(idx_path) and os.path.getsize(idx_path) <= 32 * 1024 * 1024:
            with open(idx_path, "rb") as f:
                return f.read()
    except OSError:
        return b""
    return b""


def is_untracked_output_dir(real_ws: str, rel_dir_posix: str, git_index_bytes: Optional[bytes] = None) -> bool:
    """判断 output/ 构建归档目录是否未纳入 Git 版本控制（未跟踪时默认忽略）。"""
    clean_rel = rel_dir_posix.strip("/")
    if not clean_rel:
        return False
    base_name = clean_rel.rsplit("/", 1)[-1]
    if base_name != "output":
        return False
    idx_buf = _read_git_index_bytes(real_ws) if git_index_bytes is None else git_index_bytes
    if not idx_buf:
        return True
    needle = (clean_rel + "/").encode("utf-8")
    return needle not in idx_buf


def scan_workspace_paths_cached(
    real_ws: str, ignored_dirs: set, binary_exts: set, *,
    force: bool = False, max_depth: Optional[int] = 5, max_scan: Optional[int] = 2500,
) -> Tuple[str, ...]:
    key = (real_ws, max_depth, max_scan, frozenset(ignored_dirs), frozenset(binary_exts))
    # Overlapping autocomplete requests share a scan. A long scan never holds the line-count lock.
    with _WS_SCAN_LOCK:
        hit = _WS_DIR_INDEX_CACHE.get(key)
        ttl = 60.0 if max_scan is None else _WS_INDEX_TTL_SEC
        if not force and hit and time.monotonic() - hit[0] < ttl:
            return hit[1]
        git_index = _read_git_index_bytes(real_ws)
        paths = []
        pending = [("", 0)]
        while pending and (max_scan is None or len(paths) < max_scan):
            directory, depth = pending.pop()
            try:
                with os.scandir(os.path.join(real_ws, directory)) as entries:
                    children = sorted(entries, key=lambda e: e.name)
            except OSError:
                continue
            dirs = []
            for entry in children:
                name = entry.name
                if name.startswith("."):
                    continue
                rel = directory + "/" + name if directory else name
                try:
                    if entry.is_dir(follow_symlinks=False):
                        if max_depth is not None and depth >= max_depth:
                            continue
                        if name in ignored_dirs or name.endswith(".app"):
                            continue
                        if name == "output" and is_untracked_output_dir(real_ws, rel, git_index):
                            continue
                        dirs.append((rel, depth + 1))
                    elif os.path.splitext(name)[1].lower() not in binary_exts and entry.is_file(follow_symlinks=False):
                        paths.append(rel)
                        if max_scan is not None and len(paths) >= max_scan:
                            break
                except OSError:
                    continue
            pending.extend(reversed(dirs))
        result = tuple(paths)
        # A meeting may switch among many large projects. Bound the retained indexes.
        _WS_DIR_INDEX_CACHE.pop(key, None)
        while len(_WS_DIR_INDEX_CACHE) >= 4:
            del _WS_DIR_INDEX_CACHE[next(iter(_WS_DIR_INDEX_CACHE))]
        _WS_DIR_INDEX_CACHE[key] = (time.monotonic(), result)
        return result


def describe_workspace_file(real_ws: str, rel: str) -> Optional[dict]:
    full = os.path.normpath(os.path.join(real_ws, rel))
    try:
        if os.path.normcase(os.path.realpath(full)) != os.path.normcase(full):
            return None
        st = os.stat(full, follow_symlinks=False)
        if not stat.S_ISREG(st.st_mode):
            return None
    except OSError:
        return None
    entry = {"path": rel, "size_kb": round(st.st_size / 1024.0, 1)}
    lines = count_file_lines_cached(full, st)
    if lines is not None:
        entry["lines"] = lines
    return entry


def scan_workspace_index_cached(real_ws: str, ignored_dirs: set, binary_exts: set, **options) -> List[dict]:
    paths = scan_workspace_paths_cached(real_ws, ignored_dirs, binary_exts, **options)
    return [entry for rel in paths if (entry := describe_workspace_file(real_ws, rel)) is not None]


def invalidate_workspace_index(real_ws: str = "") -> None:
    with _WS_SCAN_LOCK:
        if real_ws:
            real = os.path.realpath(real_ws)
            for key in list(_WS_DIR_INDEX_CACHE):
                if key[0] == real:
                    del _WS_DIR_INDEX_CACHE[key]
        else:
            _WS_DIR_INDEX_CACHE.clear()


async def run_index_in_thread(fn, *args, **kwargs):
    """统一将同步磁盘索引读取卸载至后台工作线程。"""
    return await asyncio.to_thread(fn, *args, **kwargs)


__all__ = [
    "count_file_lines_cached",
    "invalidate_workspace_index",
    "run_index_in_thread",
    "scan_workspace_index_cached",
    "scan_workspace_paths_cached",
    "describe_workspace_file",
]
