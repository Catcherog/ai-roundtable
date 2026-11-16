"""Win32 jobs, safe file reads and executable resolution for the portable desktop app."""
import ctypes
import errno
import json
import os
from pathlib import Path
import shutil
import stat
import sys

_jobs = {}

if os.name == "nt" or sys.platform == "win32":
    from ctypes import wintypes
    import msvcrt

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
    _wait = _api("WaitForSingleObject", D, H, D)
    _close = _api("CloseHandle", wintypes.BOOL, H)
    _open_process = _api("OpenProcess", H, D, wintypes.BOOL, D)
    _create_file = _api("CreateFileW", H, wintypes.LPCWSTR, D, D, P, D, D, H)
    _get_file_info = _api("GetFileInformationByHandleEx", wintypes.BOOL, H, ctypes.c_int, P, D)

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


def observe_job_members(pid):
    """Retain waitable handles before terminating the job. Its accounting may reach zero first."""
    job = _jobs.get(pid)
    if not job:
        return []
    capacity = 32
    while True:
        class Members(ctypes.Structure):
            _fields_ = [("assigned", D), ("count", D), ("pids", ctypes.c_size_t * capacity)]
        info = Members()
        if _query_job(job, 3, ctypes.byref(info), ctypes.sizeof(info), None):
            break
        error = ctypes.get_last_error()
        if error != 234:  # ERROR_MORE_DATA
            raise ctypes.WinError(error)
        capacity = max(capacity * 2, info.assigned)
    handles = []
    for member in info.pids[:info.count]:
        handle = _open_process(0x00100000, False, member)  # SYNCHRONIZE
        if handle:
            handles.append(handle)
    return handles


def members_exited(handles):
    for handle in handles:
        result = _wait(handle, 0)
        if result == 258:  # WAIT_TIMEOUT
            return False
        if result != 0:
            raise ctypes.WinError(ctypes.get_last_error())
    return True


def release_members(handles):
    for handle in handles:
        _close(handle)


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


def pick_folder_sta(prompt: str = "请选择 AI圆桌 绑定的本地项目工作区目录："):
    """
    PowerShell STA 模式 System.Windows.Forms.FolderBrowserDialog 选目录兜底实现：
    返回 (selected_path, cancelled, error_message)，严格区分用户取消与平台调用异常。
    """
    import subprocess

    ps_exe = shutil.which("powershell.exe") or shutil.which("pwsh.exe") or "powershell.exe"
    safe_prompt = str(prompt or "请选择项目工作区目录").replace("'", "''")
    ps_script = (
        "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
        "Add-Type -AssemblyName System.Windows.Forms; "
        "Add-Type -AssemblyName System.Drawing; "
        "$owner = New-Object System.Windows.Forms.Form; "
        "$owner.TopMost = $true; $owner.ShowInTaskbar = $false; "
        "$owner.Width = 1; $owner.Height = 1; $owner.Opacity = 0; "
        "$owner.StartPosition = 'CenterScreen'; $owner.Show(); $owner.Activate(); "
        "$dlg = New-Object System.Windows.Forms.FolderBrowserDialog; "
        f"$dlg.Description = '{safe_prompt}'; "
        "$dlg.ShowNewFolderButton = $true; "
        "try { "
        "  $res = $dlg.ShowDialog($owner); "
        "  if ($res -eq [System.Windows.Forms.DialogResult]::OK -and $dlg.SelectedPath) { "
        "    [Console]::Out.WriteLine('SELECTED:' + $dlg.SelectedPath) "
        "  } else { "
        "    [Console]::Out.WriteLine('CANCELLED') "
        "  } "
        "} finally { $dlg.Dispose(); $owner.Close(); $owner.Dispose() }"
    )
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.run(
            [ps_exe, "-NoProfile", "-NonInteractive", "-Sta", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=90.0,
            creationflags=creation_flags,
        )
    except FileNotFoundError as exc:
        return "", False, f"未检测到 PowerShell 可执行程序，无法唤起 Windows 系统目录对话框 ({exc})"
    except subprocess.TimeoutExpired:
        return "", False, "Windows 目录选择对话框响应超时"
    except Exception as exc:
        return "", False, f"唤起 Windows 目录选择对话框异常：{exc}"

    out_txt = (proc.stdout or b"").decode("utf-8", errors="replace").strip()
    err_txt = (proc.stderr or b"").decode("utf-8", errors="replace").strip()
    if proc.returncode != 0:
        detail = err_txt or out_txt or f"exit={proc.returncode}"
        return "", False, f"Windows 目录选择组件调用失败：{detail[:240]}"
    for line in reversed(out_txt.splitlines()):
        clean = line.strip()
        if clean.startswith("SELECTED:"):
            chosen = clean[len("SELECTED:") :].strip()
            if len(chosen) > 3 and chosen[-1] in ("\\", "/"):
                chosen = chosen.rstrip("\\/")
            if chosen:
                return chosen, False, ""
        if clean in ("CANCELLED", "CANCEL"):
            return "", True, ""
    return "", False, f"Windows 目录选择器返回了无法解析的响应：{out_txt[:160] or err_txt[:160] or 'empty'}"
