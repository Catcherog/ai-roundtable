#!/usr/bin/env python3
"""Regressions for concurrent uploads, capacity and per-turn attachment isolation."""
import base64
import concurrent.futures
import io
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.attachments import MAX_SESSION_ATTACHMENTS, SessionAttachmentManager


def verify_binary_attachment_prompts(manager, turn_dir):
    session_id = "attachment_prompt"
    archive_bytes = io.BytesIO()
    with zipfile.ZipFile(archive_bytes, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("notes.txt", b"A" * 50000)
    raw_archive = archive_bytes.getvalue()
    workbook = manager.save_raw_attachment(session_id, filename="table.xlsx", raw_bytes=raw_archive)
    bundle = manager.save_raw_attachment(session_id, filename="bundle.zip", raw_bytes=raw_archive)
    assert all(item["line_count"] == 0 and not item["excerpt"] for item in (workbook, bundle))
    session_dir = manager._session_dir(session_id)
    records = manager._load_index(session_dir)
    records[0].update(excerpt=raw_archive[:600].decode("utf-8", errors="replace"), line_count=4)
    manager._save_index(session_dir, records)
    legacy = manager.resolve_attachments(session_id, [workbook["id"]])[0]
    assert legacy["line_count"] == 0 and not legacy["excerpt"]

    raw_note = ("中文前段\x00后段" + "尾" * 100).encode("utf-8")
    note = manager.save_raw_attachment(session_id, filename="note.txt", raw_bytes=raw_note)
    raw_utf16 = "UTF16\x00尾部".encode("utf-16")
    utf16 = manager.save_raw_attachment(session_id, filename="unicode.txt", raw_bytes=raw_utf16)
    turn_dir.mkdir()
    prompt, images = manager.stage_for_cli_turn(session_id, [legacy, bundle, note, utf16], str(turn_dir))
    assert not images and "\x00" not in prompt and "A" * 50 not in prompt
    assert "Excel 工作簿" in prompt and "ZIP 压缩包" in prompt
    assert r"中文前段\x00后段" in prompt and r"UTF16\x00尾部" in prompt
    staged_dir = turn_dir / "rt_attachments"
    assert (staged_dir / "01_table.xlsx").read_bytes() == raw_archive
    assert (staged_dir / "02_bundle.zip").read_bytes() == raw_archive
    assert (staged_dir / "03_note.txt").read_bytes() == raw_note
    assert (staged_dir / "04_unicode.txt").read_bytes() == raw_utf16
    subprocess.run([sys.executable, "-c", "import sys; assert '01_table.xlsx' in sys.argv[1]", prompt], check=True)
    print("PASS legacy and new ZIP/Excel attachments preserve bytes without leaking binary into CLI arguments")


def main():
    with tempfile.TemporaryDirectory(prefix="roundtable-v4-edges-") as td:
        tmp=Path(td); mgr=SessionAttachmentManager(str(tmp / "state")); sid="edge_session"
        def save(name, data):
            return mgr.save_base64_attachment(sid,filename=name,data_base64=base64.b64encode(data).decode())
        def reject(fn):
            try: fn()
            except (ValueError,OSError): return
            raise AssertionError("unsafe input was accepted")
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            dup=list(pool.map(lambda _:save("draft.log",b"one\n"),range(8)))
            unique=list(pool.map(lambda i:save(f"{i}.txt",str(i).encode()),range(8)))
        assert len({a["id"] for a in dup})==1 and len(mgr.list_attachments(sid))==9
        reject(lambda: save("image.png",b"\x7fELF"+b"A"*128))
        reject(lambda: save("notes.txt",b"\x7fELF"+b"A"*128))
        for i in range(9,MAX_SESSION_ATTACHMENTS): save(f"{i}.txt",str(i).encode())
        reject(lambda: save("overflow.txt",b"too many"))
        assert len(mgr.resolve_attachments(sid,[dup[0]["id"],unique[0]["id"]]))==2
        t=tmp/"turn"; t.mkdir()
        note=unique[0]
        prompt,_=mgr.stage_for_cli_turn(sid,[note],str(t))
        dst=next((t/"rt_attachments").iterdir())
        assert str(dst) in prompt and str(mgr.root_dir) not in prompt
        if os.name!="nt":
            assert dst.stat().st_mode & 0o777 == 0o400
            target=tmp/"unrelated.txt";target.write_text("keep")
            dst.unlink();dst.symlink_to(target)
            mgr.stage_for_cli_turn(sid,[note],str(t))
            assert target.read_text()=="keep" and not dst.is_symlink()
            (t/"rt_attachments").rename(t/"old");(t/"rt_attachments").symlink_to(tmp)
            reject(lambda: mgr.stage_for_cli_turn(sid,[note],str(t)))
        reject(lambda: mgr.stage_for_cli_turn(sid,[note],""))
        mgr.delete_session_attachments(sid)
        assert not (mgr.root_dir/sid).exists()
        print("PASS concurrent dedup and unique uploads; disguised ELF with no MIME; capacity preserves history; private staging and cascade cleanup")
        verify_binary_attachment_prompts(mgr, tmp / "file_turn")
if __name__=="__main__":
    main()
