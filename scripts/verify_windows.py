"""Release check: run with the Python executable inside the extracted x64 bundle."""
import asyncio
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

bundle = Path(sys.argv[1]).resolve()
assert sys.platform == "win32" and Path(sys.executable).resolve() == bundle / "runtime" / "python.exe"
from backend.drivers.process_watchdog import spawn_supervised_cli, terminate_and_reap_process_group
from backend.drivers.windows_support import native_command, split_command
from backend.workspace_backup import WorkspaceBackup, WorkspaceWriteLock, WorkspaceAdmissionError
from backend.server import AsyncHTTPServer

def running(pid):
    kernel = ctypes.windll.kernel32
    kernel.OpenProcess.restype = ctypes.c_void_p
    h = kernel.OpenProcess(0x100000, False, pid)
    if not h:
        return False
    try:
        return kernel.WaitForSingleObject(ctypes.c_void_p(h), 0) == 258
    finally:
        kernel.CloseHandle(ctypes.c_void_p(h))


async def check(root):
    project = root / "目录 with spaces"
    project.mkdir()
    data = root / "state"
    os.environ["AI_ROUNDTABLE_HOME"] = str(data)
    assert split_command(r'"C:\some path\tool.exe" "含 空格"') == [r"C:\some path\tool.exe", "含 空格"]
    raw = project / "bytes.bin"
    before = bytes(range(256)) + b"\r\n\0\x1a"
    raw.write_bytes(before)
    snap = WorkspaceBackup.capture(str(project), runtime_home=data)
    raw.write_bytes(b"after")
    assert snap.finish()
    raw.write_bytes(b"user edit")
    ok, _, detail = snap.restore_with_report()
    assert not ok and detail["status_code"] == 409 and raw.read_bytes() == b"user edit"
    raw.write_bytes(b"after")
    assert snap.restore_with_report()[0] and raw.read_bytes() == before
    with WorkspaceWriteLock(str(project), runtime_home=data):
        code = (
            "import sys;from pathlib import Path;from backend.workspace_backup import WorkspaceWriteLock,WorkspaceLockBusyError\n"
            "try: WorkspaceWriteLock(sys.argv[1],runtime_home=Path(sys.argv[2])).try_acquire()\n"
            "except WorkspaceLockBusyError: sys.exit(0)\n"
            "sys.exit(3)"
        )
        assert subprocess.run([sys.executable, "-c", code, str(project).upper(), str(data)], timeout=8).returncode == 0
    with WorkspaceWriteLock(str(project), runtime_home=data):
        pass
    external = root / "outside"; external.mkdir()
    link = project / "junction"
    subprocess.run(["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(external)], check=True, capture_output=True)
    try:
        WorkspaceBackup.capture(str(project), runtime_home=data)
        raise AssertionError("junction admitted for write")
    except WorkspaceAdmissionError as exc:
        assert exc.reason == "windows_reparse_point"
    finally:
        link.rmdir()
    print("PASS workspace locking across processes, junction rejection, binary rollback and manual-edit conflict", flush=True)

    argv = [sys.executable, "-c", "import json,sys;print(json.dumps([sys.argv[1],sys.stdin.buffer.read().hex()]))", 'spaces & | %NAME% "引号"']
    h = await spawn_supervised_cli(argv, cwd=str(project), env=os.environ.copy(), stdin=asyncio.subprocess.PIPE)
    try:
        out, err = await asyncio.wait_for(h.proc.communicate(b"hello\n"), 15)
        assert h.proc.returncode == 0, err
        assert json.loads(out) == [argv[-1], b"hello\n".hex()]
    finally:
        await terminate_and_reap_process_group(h)
    fixture = project / "node_modules" / "@test" / "tool"
    fixture.mkdir(parents=True);(fixture/"package.json").write_text('{"bin":{"rt":"main.js"}}')
    (fixture/"main.js").write_text(
        "const a=process.argv.slice(2); if(a.includes('--version'))console.log('fixture 1.0');"
        "else if(a.includes('--help'))console.log('usage: fixture -p');"
        "else if(a.includes('-p'))console.log('WINDOWS_ADAPTER_OK'); else process.exit(4);"
    )
    (project/"rt.cmd").write_text("@exit /b 9")
    resolved = native_command([str(project/"rt.cmd"), argv[-1]], os.environ.copy())
    assert len(resolved) == 3 and Path(resolved[1]).samefile(fixture/"main.js") and resolved[2] == argv[-1], resolved
    marker = project / "tree.json"
    code = ("import json,os,subprocess,sys,time;from pathlib import Path;"
            "child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(120)']);"
            "Path(sys.argv[1]).write_text(json.dumps([os.getpid(),child.pid]));time.sleep(120)")
    for trial in range(12):
        marker.unlink(missing_ok=True)
        h = await spawn_supervised_cli([sys.executable,"-c",code,str(marker)],cwd=str(project),env=os.environ.copy(),wait_release=True)
        await asyncio.sleep(.15);assert not marker.exists(); h.release_gate()
        try:
            for _ in range(100):
                if marker.exists() and marker.stat().st_size:break
                await asyncio.sleep(.05)
            children = json.loads(marker.read_text());assert all(running(p) for p in children)
        finally:
            await terminate_and_reap_process_group(h)
        assert not any(running(p) for p in children)
    print("PASS stdin, Unicode argv, shell metacharacters, npm shim, release gate and descendant cleanup",flush=True)
    # Kill the manager itself while its real child and grandchild are alive.
    marker.unlink()
    owner = ("import asyncio,os,sys;from backend.drivers.process_watchdog import spawn_supervised_cli\n"
             "async def run():\n"
             " h=await spawn_supervised_cli([sys.executable,'-c',sys.argv[1],sys.argv[2]],cwd=os.getcwd(),env=os.environ.copy())\n"
             " await asyncio.sleep(60)\n"
             "asyncio.run(run())")
    manager = subprocess.Popen([sys.executable,"-c",owner,code,str(marker)],cwd=project)
    try:
        for _ in range(150):
            if marker.exists() and marker.stat().st_size: break
            await asyncio.sleep(.05)
        tree = json.loads(marker.read_text())
        assert all(running(pid) for pid in tree)
    finally:
        manager.kill()
        manager.wait(timeout=8)
    for _ in range(150):
        if not any(running(pid) for pid in tree): break
        await asyncio.sleep(.03)
    assert not any(running(pid) for pid in tree)
    print("PASS closing the manager's last Job handle on a crash removed the real process tree",flush=True)


    # Probe the packaged API without credentials for a hosted model.
    import socket
    sock=socket.socket();sock.bind(("127.0.0.1",0));sock.setblocking(False)
    port=sock.getsockname()[1];app=AsyncHTTPServer("127.0.0.1",port,str(project))
    server=await asyncio.start_server(app.handle_client,sock=sock)
    def request(path,token=None,payload=None,method=None):
        req=urllib.request.Request(f"http://127.0.0.1:{port}"+path,data=json.dumps(payload).encode() if payload is not None else None,
            headers={"Content-Type":"application/json",**({"X-Roundtable-Token":token} if token else {})},method=method)
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(req,timeout=15) as r:return r.status,json.loads(r.read())
        except urllib.error.HTTPError as exc:return exc.code,{}
    try:
        assert (await asyncio.to_thread(request,"/api/status"))[0]==401
        rc,s=await asyncio.to_thread(request,"/api/status",app.boot_token);assert rc==200 and len(s["system"]["agents"])==6
        rc,s=await asyncio.to_thread(request,"/api/config",app.boot_token,{"agents":{"carbon":{"model":"gemini-4-argon","discussion_effort":"medium"}}})
        assert rc==200 and s["system"]["agents"]["carbon"]["model"]=="gemini-4-argon"
        assert json.loads((data/"config.json").read_text(encoding="utf8"))["agents"]["carbon"]["model"]=="gemini-4-argon"
        rc,s=await asyncio.to_thread(request,"/api/cli/test",app.boot_token,{"agent_id":"carbon","agents":{"carbon":{"driver":"agy","custom_binary":str(project/"rt.cmd")}}})
        ping=s["results"]["carbon"]
        assert rc == 200 and ping["ok"] and "WINDOWS_ADAPTER_OK" in ping["reply"], ping
        async def api(path, payload=None, method=None, expected=200):
            code, body = await asyncio.to_thread(request, path, app.boot_token, payload, method)
            assert code == expected, (path, code, expected)
            return body
        created = await api("/api/sessions", {"title":"Windows 历史核验"}, expected=201)
        sid = created["session"]["session_id"]
        meeting = "/api/sessions/" + sid
        await api(meeting + "/attachments", {"filename":"会议证据.txt","data_base64":"cHJvb2Y="}, expected=201)
        await api(meeting, method="DELETE")
        await api(meeting + "/restore", {})
        assert len((await api(meeting + "/attachments"))["attachments"]) == 1
        await api(meeting, method="DELETE")
        row = next(r for r in (await api("/api/sessions/trash"))["sessions"] if r["session_id"] == sid)
        confirm = {"confirm_session_id":sid,"confirm_title":row["title"],"deleted_at":row["deleted_at"]}
        await api(meeting + "/purge", {**confirm, "confirm_title":"错误标题"}, expected=409)
        folder = data / "attachments" / sid
        busy_file = folder / "open-test.txt"
        with busy_file.open("wb") as held:
            held.write(b"Windows sharing violation fixture"); held.flush()
            await api(meeting + "/purge", confirm, expected=409)
        await api(meeting + "/purge", confirm)
        assert not folder.exists()
        assert not any(r["session_id"] == sid for r in (await api("/api/sessions/trash"))["sessions"])
        print("PASS Windows trash/restore, title confirmation and retry after closing a locked file", flush=True)
    finally:
        server.close();await server.wait_closed();await app.orchestrator.shutdown()
    print("PASS extracted release API authentication, six seats, saved model and SQLite startup",flush=True)

with tempfile.TemporaryDirectory(prefix="roundtable-win-") as tmp:
    asyncio.run(check(Path(tmp)))
