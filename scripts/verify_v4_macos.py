#!/usr/bin/env python3
"""Verify the installed v4 macOS bundle against the assembled app and current sources."""
import hashlib
import json
import plistlib
import struct
import subprocess
import tempfile
from pathlib import Path

def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def inventory(folder):
    return {p.relative_to(folder).as_posix(): digest(p) for p in folder.rglob("*")
            if p.is_file() and p.name != ".DS_Store" and "__pycache__" not in p.parts and p.suffix != ".pyc"}

def main():
    root = Path(__file__).resolve().parents[1]
    built, installed = root / "AI圆桌.app", Path.home() / "Desktop" / "AI圆桌.app"
    src = (root / "macos_app/main.m").read_text()
    assert "runOpenPanelWithParameters:" in src and "panel.canChooseFiles = YES" in src
    assert ".UIDelegate = self" in src or "setUIDelegate:self" in src
    records = []
    for app in (built, installed):
        subprocess.run(["codesign", "--verify", "--deep", "--strict", str(app)], check=True)
        contents = app / "Contents"
        info = plistlib.loads((contents / "Info.plist").read_bytes())
        assert info["CFBundleShortVersionString"] == "4.0.0"
        binary = contents / "MacOS" / info["CFBundleExecutable"]
        assert b"webView:runOpenPanelWithParameters:initiatedByFrame:completionHandler:" in binary.read_bytes()
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
    assert inventory(built) == inventory(installed), "Desktop and project bundles differ"
    print(json.dumps({"identical_bundles":True,"bundles":records},ensure_ascii=False,indent=2))

if __name__ == "__main__":
    main()
