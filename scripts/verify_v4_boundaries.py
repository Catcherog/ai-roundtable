#!/usr/bin/env python3
"""Regressions for concurrent uploads, capacity and per-turn attachment isolation."""
import base64
import concurrent.futures
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.attachments import MAX_SESSION_ATTACHMENTS, SessionAttachmentManager

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
if __name__=="__main__":
    main()
