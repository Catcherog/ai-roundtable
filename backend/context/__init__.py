# -*- coding: utf-8 -*-
"""
AI圆桌 — 异步项目源码索引与 (mtime_ns, size) 元数据缓存包（P1.2 事件循环零阻塞优化）
"""

from __future__ import annotations

import asyncio
import os
import threading
import time
from typing import Dict, List, Optional, Tuple


_LINE_COUNT_CACHE_LOCK = threading.Lock()
# key: real_file_path -> (st_mtime_ns, st_size, line_count)
_LINE_COUNT_CACHE: Dict[str, Tuple[int, int, int]] = {}

# key: real_ws -> (monotonic_ts, scanned_entries_list)
_WS_DIR_INDEX_CACHE: Dict[str, Tuple[float, List[dict]]] = {}
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


def scan_workspace_index_cached(
    real_ws: str,
    ignored_dirs: set,
    binary_exts: set,
    *,
    force: bool = False,
    max_depth: int = 5,
    max_scan: int = 2500,
) -> List[dict]:
    """扫描工作区文件清单并复用目录缓存与单文件 (mtime_ns, size) 行数缓存。"""
    now = time.monotonic()
    with _LINE_COUNT_CACHE_LOCK:
        hit = _WS_DIR_INDEX_CACHE.get(real_ws)
        if not force and hit and (now - hit[0]) < _WS_INDEX_TTL_SEC:
            return list(hit[1])

    collected: List[dict] = []
    for root_d, dirs, files in os.walk(real_ws):
        rel_dir = os.path.relpath(root_d, real_ws)
        depth = 0 if rel_dir == "." else rel_dir.count(os.sep) + 1
        if depth > max_depth:
            dirs[:] = []
            continue
        dirs[:] = sorted(
            d
            for d in dirs
            if not d.startswith(".")
            and not d.endswith(".app")
            and d not in ignored_dirs
        )
        for fname in sorted(files):
            if fname.startswith("."):
                continue
            _, ext = os.path.splitext(fname)
            if ext.lower() in binary_exts:
                continue
            full_p = os.path.join(root_d, fname)
            if os.path.islink(full_p):
                continue
            try:
                st = os.stat(full_p)
            except OSError:
                continue
            rel_p = os.path.relpath(full_p, real_ws).replace(os.sep, "/")
            entry: dict = {
                "path": rel_p,
                "size_kb": round(st.st_size / 1024.0, 1),
            }
            ln = count_file_lines_cached(full_p, st)
            if ln is not None:
                entry["lines"] = ln
            collected.append(entry)
            if len(collected) >= max_scan:
                break
        if len(collected) >= max_scan:
            break

    with _LINE_COUNT_CACHE_LOCK:
        _WS_DIR_INDEX_CACHE[real_ws] = (time.monotonic(), collected)
    return list(collected)


def invalidate_workspace_index(real_ws: str = "") -> None:
    with _LINE_COUNT_CACHE_LOCK:
        if real_ws:
            _WS_DIR_INDEX_CACHE.pop(os.path.realpath(real_ws), None)
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
]
