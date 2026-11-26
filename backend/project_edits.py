"""Apply a read-only agent's text edits to a large project under the existing workspace lock."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

from .workspace_backup import WorkspaceBackup, atomic_write_bytes_fsync, fsync_directory

_MACOS_SANDBOX_PROBE: bool | None = None


def can_apply_macos_sandbox() -> bool:
    """Return True only when macOS Seatbelt sandbox-exec is present and permitted in this process."""
    global _MACOS_SANDBOX_PROBE
    if _MACOS_SANDBOX_PROBE is not None:
        return _MACOS_SANDBOX_PROBE
    if sys.platform != "darwin" or not os.access("/usr/bin/sandbox-exec", os.X_OK):
        _MACOS_SANDBOX_PROBE = False
        return False
    try:
        proc = subprocess.run(
            ["/usr/bin/sandbox-exec", "-p", "(version 1)(allow default)", "/usr/bin/true"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3,
            check=False,
        )
        _MACOS_SANDBOX_PROBE = proc.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        _MACOS_SANDBOX_PROBE = False
    return _MACOS_SANDBOX_PROBE


EDIT_INSTRUCTION = """本项目使用逐文件写入。你可以只读检索整个工作区。请读取目标源码，勿自己写文件或运行会写文件的命令。
圆桌会在你返回后把编辑直接写入原目录。最终回答只给一个标记为 roundtable-edits 的 JSON 代码块。
格式为 {"summary":"用中文简述本轮改动","files":[{"path":"dir/a.py","replacements":[{"old":"原文件中唯一的原文","new":"替换后的原文"}]},{"path":"other/new.py","create":"完整新文件内容，含必要换行"}]}。
每个项目相对路径只列一次，可跨目录。old 必须精确匹配，必要时带上下文；同一文件的多处替换按顺序应用。
如需删除整个文件，请使用 {"path":"dir/old.py","delete_sha256":"所读文件的完整 SHA-256"}。
仅处理勾选的任务。如果不需要更改，files 用空数组并在 summary 说明原因。"""


def protect_project_command(argv, root):
    """Enforce a read-only project for the CLI or verification process and its descendants."""
    if not can_apply_macos_sandbox():
        raise ValueError("当前系统未提供大项目逐文件写入所需的只读进程保护")
    return [
        "/usr/bin/sandbox-exec", "-D", "PROJECT=" + os.path.realpath(root),
        "-p", '(version 1)(allow default)(deny file-write* (subpath (param "PROJECT")))', *argv,
    ]


def _result_bytes(edit, original, path):
    """Return the new bytes; None represents deletion. All edit preconditions are checked before publication."""
    modes = set(edit) - {"path"}
    if modes == {"create"} and isinstance(edit["create"], str):
        if original is not None:
            raise ValueError(f"新增目标已存在：{path}")
        data = edit["create"].encode("utf-8")
    elif modes == {"delete_sha256"} and isinstance(edit["delete_sha256"], str):
        if original is None or hashlib.sha256(original).hexdigest() != edit["delete_sha256"].lower():
            raise ValueError(f"删除前文件哈希不匹配：{path}")
        return None
    elif modes == {"replacements"} and isinstance(edit["replacements"], list) and edit["replacements"]:
        if original is None:
            raise ValueError(f"待修改文件不存在：{path}")
        content = original.decode("utf-8")
        crlf = "\r\n" in content and "\n" not in content.replace("\r\n", "")
        for item in edit["replacements"]:
            if not isinstance(item, dict) or set(item) != {"old", "new"} or not all(isinstance(s, str) for s in item.values()):
                raise ValueError(f"替换项缺少 old 或 new 原文：{path}")
            old, new = item["old"], item["new"]
            if crlf:
                old = old.replace("\r\n", "\n").replace("\n", "\r\n")
                new = new.replace("\r\n", "\n").replace("\n", "\r\n")
            if content.count(old) != 1:
                raise ValueError(f"原文已变化或匹配了多个位置：{path}")
            content = content.replace(old, new, 1)
        data = content.encode("utf-8")
    else:
        raise ValueError(f"无法识别文件编辑：{path}")
    if b"\x00" in data:
        raise ValueError(f"仅支持文本源码编辑：{path}")
    return data


def _publish(backup, rel, previous, entry):
    path = backup.target_file(rel)
    live, _ = backup.scan_target_files([rel], store_blobs=False)
    if live.get(rel) != previous:
        raise ValueError(f"文件在准备期间已被修改：{rel}")
    if entry is None:
        path.unlink()
        fsync_directory(path.parent)
    else:
        data = backup._load_blob_bytes(entry["sha256"])
        atomic_write_bytes_fsync(path, data, entry["mode"], create_only=previous is None)


def _extract_edit_plan(reply: str):
    """Extract a JSON edit plan cleanly even with inner code fences in JSON strings or trailing prose."""
    text = (reply or "").strip()
    if not text:
        raise ValueError("empty edit reply")
    decoder = json.JSONDecoder()
    for fence_pat in (r"^\x60{3}roundtable-edits[ \t]*\r?\n", r"^\x60{3}json[ \t]*\r?\n"):
        matches = list(re.finditer(fence_pat, text, re.M))
        for match in reversed(matches):
            body_start = match.end()
            while body_start < len(text) and text[body_start] in " \t\r\n":
                body_start += 1
            try:
                obj, end_idx = decoder.raw_decode(text, body_start)
            except ValueError:
                continue
            tail = text[end_idx:]
            if re.match(r"^[ \t]*(?:\r?\n)[ \t]*\x60{3}(?:[ \t]*(?:\r?\n|\Z))", tail):
                return obj
    return json.loads(text)


def apply_edit_reply(backup: WorkspaceBackup, reply: str):
    """Journal the whole batch before publishing; compensate a partially applied batch on an I/O error."""
    if backup.target_paths != []:
        raise ValueError("本次写入已经处理，请先核对当前文件")
    try:
        plan = _extract_edit_plan(reply)
    except (TypeError, ValueError) as exc:
        raise ValueError("执行席位未返回有效的文件编辑清单，本次没有写入") from exc
    if not isinstance(plan, dict) or not isinstance(plan.get("files"), list) or not isinstance(plan.get("summary"), str):
        raise ValueError("执行结果缺少 files 或 summary")
    summary = plan["summary"].strip()
    edits = plan["files"]
    paths = []
    keys = set()
    for edit in edits:
        if not isinstance(edit, dict) or not isinstance(edit.get("path"), str):
            raise ValueError("编辑清单缺少文件路径")
        rel = edit["path"]
        backup.target_file(rel)
        key = unicodedata.normalize("NFC", rel).casefold() if sys.platform in ("darwin", "win32") else rel
        if key in keys:
            raise ValueError(f"编辑清单包含重复的文件路径：{rel}")
        keys.add(key)
        paths.append(rel)
    if any(parent.as_posix() in keys for key in keys for parent in Path(key).parents):
        raise ValueError("同一路径不能既是文件又是其他目标的父目录")

    before, _ = backup.scan_target_files(paths, store_blobs=True)
    next_entries = {}
    total_after = 0
    for rel, edit in zip(paths, edits):
        entry = before.get(rel)
        old = backup._load_blob_bytes(entry["sha256"]) if entry else None
        if old is not None:
            old.decode("utf-8")
            if b"\x00" in old:
                raise ValueError(f"仅支持文本源码编辑：{rel}")
        new = _result_bytes(edit, old, rel)
        after = None
        if new is not None:
            total_after += len(new)
            if total_after > backup.max_workspace_bytes:
                raise ValueError("本轮编辑后的目标文件合计超过 128 MiB")
            digest = hashlib.sha256(new).hexdigest()
            backup._store_blob_if_needed(digest, new)
            after = {"type": "file", "sha256": digest, "size": len(new), "mode": entry["mode"] if entry else 0o644}
        if entry != after:
            next_entries[rel] = after

    backup.target_paths = list(next_entries)
    backup.before_entries = {p: before[p] for p in next_entries if p in before}
    backup.before_total_bytes = sum(e["size"] for e in backup.before_entries.values())
    root = Path(backup.cwd)
    for rel in next_entries:
        parent = (root / rel).parent
        while parent != root and not parent.exists():
            backup.new_parent_dirs.add(parent.relative_to(root).as_posix())
            parent = parent.parent
    backup._persist_manifest()

    try:
        for rel, after in next_entries.items():
            _publish(backup, rel, before.get(rel), after)
            backup.applied_entries[rel] = after
    except Exception as error:
        conflicts = []
        for rel in reversed(list(backup.applied_entries)):
            try:
                _publish(backup, rel, backup.applied_entries[rel], before.get(rel))
                del backup.applied_entries[rel]
            except (OSError, ValueError):
                conflicts.append(rel)
        for directory in sorted(backup.new_parent_dirs, key=lambda name: name.count("/"), reverse=True):
            try:
                candidate = root / directory
                if candidate.resolve() == candidate:
                    candidate.rmdir()
            except OSError:
                pass
        if conflicts:
            raise ValueError(f"写入中断，以下已改文件需核对回滚：{'、'.join(conflicts)}；{error}") from error
        raise

    return summary, list(next_entries)
