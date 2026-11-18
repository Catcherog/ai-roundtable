#!/usr/bin/env python3
"""Verify the installed v4 macOS bundle against the assembled app and current sources."""
import argparse
import hashlib
import json
import os
import plistlib
import re
import secrets
import select
import socket
import struct
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def inventory(folder):
    return {p.relative_to(folder).as_posix(): digest(p) for p in folder.rglob("*")
            if p.is_file() and p.name != ".DS_Store" and "__pycache__" not in p.parts and p.suffix != ".pyc"}

def verify_listener_handoff(app):
    """A desktop child must serve the already reserved port without a second bind."""
    with tempfile.TemporaryDirectory(prefix="roundtable-startup-") as data, socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        _, port = listener.getsockname()
        fd = listener.fileno()
        token, boot_id = secrets.token_hex(32), secrets.token_hex(16)
        env = dict(os.environ, AI_ROUNDTABLE_HOME=data, AI_ROUNDTABLE_BOOT_TOKEN=token,
                   AI_ROUNDTABLE_BOOT_ID=boot_id, PYTHONDONTWRITEBYTECODE="1")
        server = app / "Contents/Resources/app/backend/server.py"
        cmd = [sys.executable, str(server), "--port", str(port), "--listen-fd", str(fd), "--notify-parent"]
        with subprocess.Popen(cmd, env=env, pass_fds=(fd,), stdout=subprocess.PIPE) as child:
            try:
                listener.close()
                assert select.select([child.stdout], [], [], 30)[0], "Backend readiness timed out"
                assert child.stdout.readline().strip() == f"ROUNDTABLE_PORT={port}".encode()
                request = urllib.request.Request(f"http://127.0.0.1:{port}/api/status",
                                                 headers={"X-Roundtable-Token": token})
                with urllib.request.urlopen(request, timeout=5) as response:
                    assert json.load(response)["boot_id"] == boot_id
            finally:
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()

def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installed", type=Path, default=Path.home() / "Desktop" / "AI圆桌.app")
    built, installed = root / "AI圆桌.app", parser.parse_args().installed.resolve()
    src = (root / "macos_app/main.m").read_text()
    build_script = (root / "scripts/build_macos_app.sh").read_text()
    version_match = re.search(r"<key>CFBundleShortVersionString</key>\s*<string>([^<]+)</string>", build_script)
    assert version_match, "Build script does not declare a macOS bundle version"
    expected_version = version_match.group(1)
    assert "runOpenPanelWithParameters:" in src and "panel.canChooseFiles = YES" in src
    assert ".UIDelegate = self" in src or "setUIDelegate:self" in src
    records = []
    for app in (built, installed):
        subprocess.run(["codesign", "--verify", "--deep", "--strict", str(app)], check=True)
        contents = app / "Contents"
        info = plistlib.loads((contents / "Info.plist").read_bytes())
        assert info["CFBundleShortVersionString"] == expected_version
        binary = contents / "MacOS" / info["CFBundleExecutable"]
        assert b"webView:runOpenPanelWithParameters:initiatedByFrame:completionHandler:" in binary.read_bytes()
        assert b"saveMinutes" in binary.read_bytes()
        ico = contents / "Resources/AppIcon.icns"
        data = ico.read_bytes()
        assert data[:4] == b"icns" and struct.unpack(">I", data[4:8])[0] == len(data)
        with tempfile.TemporaryDirectory(prefix="roundtable-icon-") as td:
            target = Path(td) / "App.iconset"
            subprocess.run(["iconutil", "-c", "iconset", str(ico), "-o", str(target)], check=True)
            assert any(struct.unpack(">II", f.read_bytes()[16:24]) == (1024, 1024) for f in target.glob("*.png"))
        embedded = contents / "Resources/app"
        for name in ("backend", "frontend"):
            assert inventory(root / name) == inventory(embedded / name), name + " differs in " + str(app)
        records.append({"path":str(app),"version":info["CFBundleShortVersionString"],"build":info["CFBundleVersion"],
                        "strict_signature":True,"icon_bytes":len(data),"icon_1024_decoded":True,
                        "native_picker":True,"embedded_source_match":True,"binary_sha256":digest(binary)})
    assert inventory(built) == inventory(installed), "Installed and built bundles differ"
    verify_listener_handoff(installed)
    print(json.dumps({"identical_bundles":True,"bundles":records},ensure_ascii=False,indent=2))

if __name__ == "__main__":
    main()
