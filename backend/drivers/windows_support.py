"""Win32 jobs, safe file reads and executable resolution for the portable desktop app."""
import ctypes
from ctypes import wintypes
import errno
import json
import msvcrt
import os
from pathlib import Path
import shutil
import stat

kernel = ctypes.WinDLL("kernel32", use_last_error=True)
H, D, P = wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p


def _api(name, result, *args):
    fn = getattr(kernel, name)
    fn.restype, fn.argtypes = result, args
    return fn


_create_job = _api("CreateJobObjectW", H, P, wintypes.LPCWSTR)
_set_job = _api("SetInformationJobObject", wintypes.BOOL, H, ctypes.c_int, P, D)
_query_job = _api("QueryInformationJobObject", wintypes.BOOL, H, ctypes.c_int, P, D, P)
_assign = _api("AssignProcessToJobObject", wintypes.BOOL, H, H)
_end_job = _api("TerminateJobObject", wintypes.BOOL, H, wintypes.UINT)
_close = _api("CloseHandle", wintypes.BOOL, H)
_open_process = _api("OpenProcess", H, D, wintypes.BOOL, D)
_create_file = _api("CreateFileW", H, wintypes.LPCWSTR, D, D, P, D, D, H)
_get_file_info = _api("GetFileInformationByHandleEx", wintypes.BOOL, H, ctypes.c_int, P, D)
_jobs = {}


class BasicLimits(ctypes.Structure):
    _fields_ = [("process_time", ctypes.c_int64), ("job_time", ctypes.c_int64), ("flags", D),
                ("min_ws", ctypes.c_size_t), ("max_ws", ctypes.c_size_t), ("process_limit", D),
                ("affinity", ctypes.c_size_t), ("priority", D), ("scheduling", D)]


class ExtendedLimits(ctypes.Structure):
    _fields_ = [("basic", BasicLimits), ("io", ctypes.c_uint64 * 6),
                ("memory", ctypes.c_size_t * 4)]


class Accounting(ctypes.Structure):
    _fields_ = [("times", ctypes.c_int64 * 4), ("page_faults", D), ("total", D),
                ("active", D), ("terminated", D)]


def attach_job(pid):
    """The helper is blocked on its gate until it belongs to this kill-on-close job."""
    job = _create_job(None, None)
    if not job:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        limits = ExtendedLimits()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not _set_job(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            raise ctypes.WinError(ctypes.get_last_error())
        proc = _open_process(0x0101, False, pid)  # PROCESS_SET_QUOTA | PROCESS_TERMINATE
        if not proc:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            if not _assign(job, proc):
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            _close(proc)
        _jobs[pid] = job
    except BaseException:
        _close(job)
        raise


def job_alive(pid):
    job = _jobs.get(pid)
    if not job:
        return False
    info = Accounting()
    if not _query_job(job, 1, ctypes.byref(info), ctypes.sizeof(info), None):
        raise ctypes.WinError(ctypes.get_last_error())
    return info.active > 0


def stop_job(pid):
    job = _jobs.get(pid)
    if job and not _end_job(job, 1):
        raise ctypes.WinError(ctypes.get_last_error())


def close_job(pid):
    job = _jobs.pop(pid, None)
    if job:
        _close(job)


def open_regular_file(path):
    # FILE_FLAG_OPEN_REPARSE_POINT opens the link itself rather than its target.
    handle = _create_file(str(path), 0x80000000, 7, None, 3, 0x00200000, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        attrs = (D * 2)()
        if not _get_file_info(handle, 9, ctypes.byref(attrs), ctypes.sizeof(attrs)):
            raise ctypes.WinError(ctypes.get_last_error())
        if attrs[0] & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise OSError(errno.ELOOP, "reparse point", str(path))
        return msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
    except BaseException:
        _close(handle)
        raise


def native_command(argv, env):
    """Call native CLIs directly, or resolve an npm shim's declared JS entry without cmd.exe."""
    program = shutil.which(argv[0], path=env.get("PATH")) or argv[0]
    path = Path(program)
    if path.suffix.lower() not in {".cmd", ".bat", ".ps1"}:
        return [program, *argv[1:]]
    # Never interpolate a model prompt into a shell command line. npm records its bin in package.json.
    modules = path.parent / "node_modules"
    node = path.parent / "node.exe"
    runtime = str(node) if node.is_file() else shutil.which("node.exe", path=env.get("PATH"))
    if runtime and modules.is_dir():
        for manifest in (*modules.glob("*/package.json"), *modules.glob("@*/*/package.json")):
            try:
                meta = json.loads(manifest.read_text(encoding="utf-8"))
                entries = meta.get("bin", {})
                if isinstance(entries, str):
                    entries = {meta.get("name", "").split("/")[-1]: entries}
                entry = entries.get(path.stem) if isinstance(entries, dict) else None
                if isinstance(entry, str):
                    target = (manifest.parent / entry).resolve()
                    if target.is_relative_to(manifest.parent.resolve()) and target.is_file():
                        return [runtime, str(target), *argv[1:]]
            except (OSError, ValueError, AttributeError):
                continue
    raise OSError(f"请选择原生 .exe，或使用包含 Node.js 和 package.json 的 npm 安装：{path.name}")


def split_command(text):
    shell = ctypes.WinDLL("shell32", use_last_error=True)
    shell.CommandLineToArgvW.argtypes = (wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_int))
    shell.CommandLineToArgvW.restype = ctypes.POINTER(wintypes.LPWSTR)
    count = ctypes.c_int()
    args = shell.CommandLineToArgvW(text, ctypes.byref(count))
    if not args:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return list(args[:count.value])
    finally:
        _api("LocalFree", H, H)(ctypes.cast(args, H))
