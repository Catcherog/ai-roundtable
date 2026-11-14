# -*- coding: utf-8 -*-
"""
AI圆桌 — 执行后置自动化只读验证门禁（P2.1 核心交付）
在主刀 CLI 写入工作区完成、进入最终 `completed` 态前，支持执行用户配置的只读自检命令（如 `python3 -m unittest` / `py_compile`），
若验证未通过则阻断无警报完结并在白板与执行终端高亮一键原子回滚入口。
"""

from __future__ import annotations

import asyncio
import os
import shlex
import time
from typing import Dict, Optional

from ..drivers.process_watchdog import spawn_supervised_cli, terminate_and_reap_process_group


async def run_post_execution_verification(
    verify_cmd: str,
    *,
    workspace_realpath: str,
    env: Dict[str, str],
    timeout_sec: float = 60.0,
) -> dict:
    """在独立受监管进程组中执行只读后置验证命令并返回结构化核验报告。"""
    cleaned = str(verify_cmd or "").strip()
    if not cleaned:
        return {
            "enabled": False,
            "passed": True,
            "exit_code": 0,
            "elapsed_ms": 0,
            "output": "",
            "command": "",
        }

    try:
        argv = shlex.split(cleaned)
    except ValueError as exc:
        return {
            "enabled": True,
            "passed": False,
            "exit_code": 2,
            "elapsed_ms": 0,
            "output": f"验证命令语法解析失败: {exc}",
            "command": cleaned,
        }

    if not argv:
        return {"enabled": False, "passed": True, "exit_code": 0, "elapsed_ms": 0, "output": "", "command": ""}

    t0 = time.perf_counter()
    handle = None
    try:
        handle = await spawn_supervised_cli(
            argv,
            cwd=workspace_realpath,
            env=env,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            wait_release=False,
        )
        out_bytes, _ = await asyncio.wait_for(handle.proc.communicate(), timeout=max(5.0, float(timeout_sec)))
        rc = int(handle.proc.returncode if handle.proc.returncode is not None else 1)
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        text = (out_bytes or b"").decode("utf-8", errors="replace")[-12000:]
        return {
            "enabled": True,
            "passed": rc == 0,
            "exit_code": rc,
            "elapsed_ms": elapsed_ms,
            "output": text.strip(),
            "command": cleaned,
        }
    except asyncio.TimeoutError:
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        return {
            "enabled": True,
            "passed": False,
            "exit_code": 124,
            "elapsed_ms": elapsed_ms,
            "output": f"后置验证命令执行超时（>{int(timeout_sec)}s）：{cleaned}",
            "command": cleaned,
        }
    except Exception as exc:
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        return {
            "enabled": True,
            "passed": False,
            "exit_code": 127,
            "elapsed_ms": elapsed_ms,
            "output": f"后置验证命令启动异常：{exc}",
            "command": cleaned,
        }
    finally:
        if handle is not None:
            await terminate_and_reap_process_group(handle)


__all__ = ["run_post_execution_verification"]
