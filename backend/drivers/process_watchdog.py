# -*- coding: utf-8 -*-
"""
AI圆桌 — Pipe-EOF 子进程组自毁监管器与进程组消亡围栏（P0.2 孤儿进程防线）

核心契约：
1. 父进程创建匿名生命线管道 `(r_fd, w_fd)`，以 `start_new_session=True` 拉起监管包装器（此时 `pgid == proc.pid`）。
2. 若启用 `wait_release=True`，监管包装器在拉起真实 CLI 前先阻塞读取 1 字节放行信号 `b"\\x01"`：
   父进程可先把 `pgid` 通过 `fsync` 落盘记入恢复清单，再写入 `b"\\x01"` 放行真实 CLI；若父进程在放行前崩溃，管道 EOF 立即触发退出，工作区零改动。
3. 真实 CLI 运行期间，监管包装器屏蔽 `SIGTERM`（并在 Linux 上启用 `PR_SET_CHILD_SUBREAPER` 收割孤儿孙进程），守护线程持续阻塞读取 `r_fd`：
   一旦父进程退出或主动关闭 `w_fd` 产生 Pipe-EOF，监管包装器先向 `-pgid` 发送 `SIGTERM`，宽限后发送 `SIGKILL` 并收割全部子孙僵尸进程。
"""

from __future__ import annotations

import asyncio
import errno
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

if os.name == "nt":
    import msvcrt
    from . import windows_support


_WINDOWS_GATE = """
import msvcrt, os, subprocess, sys
fd = msvcrt.open_osfhandle(int(sys.argv[1]), os.O_RDONLY | os.O_BINARY)
try:
    allowed = os.read(fd, 1) == bytes([1])
finally:
    os.close(fd)
if not allowed:
    sys.exit(125)
sys.exit(subprocess.call(sys.argv[2:], stdin=sys.stdin.buffer, stdout=sys.stdout.buffer,
                         stderr=sys.stderr.buffer, close_fds=True))
"""


_WATCHDOG_INLINE_CODE = r"""
import ctypes, os, signal, subprocess, sys, threading, time

def _enable_subreaper_best_effort():
    if sys.platform.startswith("linux"):
        try:
            libc = ctypes.CDLL("libc.so.6", use_errno=True)
            libc.prctl(36, 1, 0, 0, 0)  # PR_SET_CHILD_SUBREAPER = 36
        except Exception:
            pass

def _reap_all_children():
    while True:
        try:
            pid, _ = os.waitpid(-1, os.WNOHANG)
            if pid <= 0:
                break
        except ChildProcessError:
            break
        except OSError:
            break

def _restore_child_signals():
    signal.signal(signal.SIGTERM, signal.SIG_DFL)
    signal.signal(signal.SIGINT, signal.SIG_DFL)

def _kill_descendants_without_self(pgid, self_pid, sig):
    # 在支持 /proc 的系统上精准向同组非自身进程发 SIGKILL，使监管器存活完成 waitpid 收割孙进程
    proc_root = "/proc"
    if os.path.isdir(proc_root) and sig == signal.SIGKILL:
        killed_any = False
        for name in os.listdir(proc_root):
            if not name.isdigit():
                continue
            pid = int(name)
            if pid == self_pid:
                continue
            try:
                if os.getpgid(pid) == pgid:
                    os.kill(pid, signal.SIGKILL)
                    killed_any = True
            except OSError:
                pass
        return killed_any
    try:
        os.killpg(pgid, sig)
        return True
    except OSError:
        return False

def _kill_group_thoroughly(pgid, self_pid, child_proc=None):
    try:
        os.killpg(pgid, signal.SIGTERM)
    except Exception:
        pass
    deadline = time.monotonic() + 0.14
    while time.monotonic() < deadline:
        _reap_all_children()
        if child_proc is not None and child_proc.poll() is not None:
            break
        time.sleep(0.02)
    _kill_descendants_without_self(pgid, self_pid, signal.SIGKILL)
    for _ in range(8):
        _reap_all_children()
        time.sleep(0.015)

def main():
    _enable_subreaper_best_effort()
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    self_pid = os.getpid()
    life_fd = int(sys.argv[1])
    wait_gate = sys.argv[2] == "1"
    cmd = sys.argv[3:]
    pgid = os.getpgrp()

    if wait_gate:
        try:
            gate = os.read(life_fd, 1)
        except OSError:
            gate = b""
        if gate != b"\x01":
            _kill_group_thoroughly(pgid, self_pid, None)
            os._exit(125)

    child_holder = []
    eof_triggered = threading.Event()
    cleanup_done = threading.Event()

    def _watch_eof():
        while True:
            try:
                buf = os.read(life_fd, 64)
                if not buf:
                    break
            except OSError:
                break
        eof_triggered.set()
        proc_ref = child_holder[0] if child_holder else None
        _kill_group_thoroughly(pgid, self_pid, proc_ref)
        cleanup_done.set()

    t = threading.Thread(target=_watch_eof, daemon=True)
    t.start()

    try:
        proc = subprocess.Popen(cmd, close_fds=True, preexec_fn=_restore_child_signals)
        child_holder.append(proc)
        rc = proc.wait()
    except Exception as exc:
        sys.stderr.write(f"watchdog spawn error: {exc}\n")
        sys.stderr.flush()
        rc = 127
    finally:
        if eof_triggered.is_set():
            cleanup_done.wait(timeout=0.6)
        _reap_all_children()
    os._exit(rc if rc >= 0 else 128 + abs(rc))

if __name__ == "__main__":
    main()
"""


@dataclass
class SupervisedProcessHandle:
    proc: asyncio.subprocess.Process
    pgid: int
    lifeline_write_fd: int
    wait_release: bool = False
    _released: bool = False
    _closed: bool = False

    def release_gate(self) -> None:
        """父进程完成 pgid 落盘 fsync 后写入单字节放行真实 CLI。"""
        if not self.wait_release or self._released or self._closed:
            return
        try:
            os.write(self.lifeline_write_fd, b"\x01")
            self._released = True
        except OSError:
            self.close_lifeline()

    def close_lifeline(self) -> None:
        """关闭父进程持有的生命线写端，立即在子监管器侧触发 Pipe-EOF 自毁。"""
        if self._closed:
            return
        self._closed = True
        try:
            os.close(self.lifeline_write_fd)
        except OSError:
            pass


async def spawn_supervised_cli(
    cmd: List[str],
    *,
    cwd: str,
    env: Dict[str, str],
    stdin: int = asyncio.subprocess.DEVNULL,
    stdout: int = asyncio.subprocess.PIPE,
    stderr: int = asyncio.subprocess.PIPE,
    limit: int = 4 * 1024 * 1024,
    wait_release: bool = False,
) -> SupervisedProcessHandle:
    """拉起带 Pipe-EOF 生命线与独立进程组围栏的受监管 CLI 子进程。"""
    r_fd, w_fd = os.pipe()
    if os.name == "nt":
        proc = None
        try:
            argv = windows_support.native_command(cmd, env)
            read_handle = msvcrt.get_osfhandle(r_fd)
            os.set_handle_inheritable(read_handle, True)
            startup = subprocess.STARTUPINFO()
            startup.lpAttributeList = {"handle_list": [read_handle]}
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-I", "-u", "-c", _WINDOWS_GATE, str(read_handle), *argv,
                stdin=stdin, stdout=stdout, stderr=stderr, cwd=cwd, env=env, limit=limit,
                startupinfo=startup, creationflags=subprocess.CREATE_NO_WINDOW,
            )
            windows_support.attach_job(proc.pid)
            handle = SupervisedProcessHandle(proc, proc.pid, w_fd, wait_release=True)
            if not wait_release:
                handle.release_gate()
            return handle
        except BaseException:
            os.close(w_fd)
            if proc is not None:
                windows_support.close_job(proc.pid)
                if proc.returncode is None:
                    proc.kill()
                await proc.wait()
            raise
        finally:
            os.close(r_fd)
    os.set_inheritable(r_fd, True)
    os.set_inheritable(w_fd, False)
    wrapped_cmd = [
        sys.executable,
        "-u",
        "-c",
        _WATCHDOG_INLINE_CODE,
        str(r_fd),
        "1" if wait_release else "0",
        *cmd,
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *wrapped_cmd,
            stdin=stdin,
            stdout=stdout,
            stderr=stderr,
            cwd=cwd,
            env=env,
            limit=limit,
            start_new_session=True,
            pass_fds=(r_fd,),
        )
    except Exception:
        try:
            os.close(r_fd)
        except OSError:
            pass
        try:
            os.close(w_fd)
        except OSError:
            pass
        raise
    finally:
        try:
            os.close(r_fd)
        except OSError:
            pass

    return SupervisedProcessHandle(
        proc=proc,
        pgid=int(proc.pid),
        lifeline_write_fd=w_fd,
        wait_release=wait_release,
    )


def is_process_group_alive(pgid: int) -> bool:
    """检测进程组是否仍有非僵尸态存活成员进程。"""
    if pgid <= 1:
        return False
    if os.name == "nt":
        return windows_support.job_alive(pgid)
    try:
        os.kill(-pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError as exc:
        if exc.errno == errno.ESRCH:
            return False

    proc_dir = Path("/proc")
    if proc_dir.is_dir():
        for entry in proc_dir.iterdir():
            if not entry.name.isdigit():
                continue
            pid = int(entry.name)
            try:
                if os.getpgid(pid) != pgid:
                    continue
                stat_txt = (entry / "stat").read_text(encoding="latin-1")
                rparen = stat_txt.rfind(")")
                if rparen > 0:
                    fields = stat_txt[rparen + 2 :].split()
                    if fields and fields[0] != "Z":
                        return True
            except OSError:
                continue
        return False
    return True


async def terminate_and_reap_process_group(
    handle: Optional[SupervisedProcessHandle],
    proc: Optional[asyncio.subprocess.Process] = None,
    *,
    grace_sec: float = 0.25,
    max_wait_sec: float = 5.0,
) -> None:
    """优雅终止并强杀整个进程组，确保 pgid 内所有派生的孙进程完全消亡后再返回。"""
    target_proc = handle.proc if handle is not None else proc
    pgid = handle.pgid if handle is not None else (int(target_proc.pid) if target_proc and target_proc.pid else 0)

    if handle is not None:
        handle.close_lifeline()

    if os.name == "nt":
        members = windows_support.observe_job_members(pgid)
        try:
            windows_support.stop_job(pgid)
            if target_proc is not None:
                await asyncio.wait_for(target_proc.wait(), max_wait_sec)
            deadline = time.monotonic() + max_wait_sec
            while is_process_group_alive(pgid) or not windows_support.members_exited(members):
                if time.monotonic() >= deadline:
                    raise TimeoutError("Windows CLI processes did not finish exiting")
                await asyncio.sleep(0.02)
        finally:
            windows_support.release_members(members)
            windows_support.close_job(pgid)
        return

    if pgid > 1 and is_process_group_alive(pgid):
        try:
            os.killpg(pgid, signal.SIGTERM)
        except OSError:
            pass
        deadline_term = time.monotonic() + max(0.05, grace_sec)
        while time.monotonic() < deadline_term and is_process_group_alive(pgid):
            await asyncio.sleep(0.03)
        if is_process_group_alive(pgid):
            try:
                os.killpg(pgid, signal.SIGKILL)
            except OSError:
                pass

    if target_proc is not None and target_proc.returncode is None:
        try:
            target_proc.kill()
        except Exception:
            pass
        try:
            await asyncio.wait_for(target_proc.wait(), timeout=1.5)
        except Exception:
            pass

    if pgid > 1:
        deadline_gone = time.monotonic() + max(0.5, max_wait_sec)
        while time.monotonic() < deadline_gone and is_process_group_alive(pgid):
            try:
                os.killpg(pgid, signal.SIGKILL)
            except OSError:
                pass
            await asyncio.sleep(0.04)
