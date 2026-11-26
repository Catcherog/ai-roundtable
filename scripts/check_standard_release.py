#!/usr/bin/env python3
"""Verify the standard desktop payload before copying it into a public release."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRO_PATHS = ("backend/audit_pro", "frontend/audit-studio.js", "frontend/audit-studio.css")
PRO_HOOKS = {
    "backend/server.py": "/api/pro/audit/",
    "frontend/app.js": "./audit-studio.js",
    "frontend/index.html": "audit-pro-launch",
}


def check(root):
    hits = [p for p in PRO_PATHS if (root / p).exists() or (root / p).is_symlink()]
    for name, marker in PRO_HOOKS.items():
        if marker in (root / name).read_text(encoding="utf-8"):
            hits.append(name)
    if hits:
        raise SystemExit("Paid desktop payload found in the standard build: " + ", ".join(hits))


if __name__ == "__main__":
    check(Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT)
