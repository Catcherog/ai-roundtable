# -*- coding: utf-8 -*-
"""
AI圆桌 v4 — 多模态图片与本地文件附件安全暂存与 CLI 注入子系统 (attachments.py)

核心设计契约：
1. 工作区零污染（CAS 安全隔离）：所有上传图片、截图与外部参考文档统一加密权限 (0o600) 存储于
   `~/.ai-roundtable/attachments/<session_id>/`，绝不写入用户绑定的本地项目目录，100% 兼容无 Git CAS 快照与回滚。
2. 纯 Python 标准库魔数与尺寸解析：无需第三方 Pillow 依赖，原生校验 PNG / JPEG / GIF / WebP 文件头魔数并提取宽高像素，
   自动拦截伪造扩展名与非法二进制可执行文件。
3. 沙箱友好的多模态 CLI 挂载：每轮调用 CLI（agy / codex / grok）前，按需将当前会话附件只读硬链/拷贝至该席位独立的
   `TMPDIR/rt_attachments/` 隔离目录，既保证 `--sandbox read-only` 下视觉/文件工具可直接读取，又在进程退出后自动清理。
"""

from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import os
import re
import shutil
import struct
import threading
import time
import uuid
import zlib
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .workspace_backup import atomic_write_bytes_fsync, atomic_write_json_fsync

MAX_SINGLE_ATTACHMENT_BYTES = 12 * 1024 * 1024  # 单文件原始字节上限 12 MiB
MAX_SESSION_ATTACHMENTS = 24
MAX_PROMPT_ATTACHMENT_CHARS = 48000

RASTER_IMAGE_MIMES: Dict[str, str] = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
}

CODE_EXTENSIONS = {
    ".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".vue", ".svelte",
    ".html", ".htm", ".css", ".scss", ".less", ".m", ".mm", ".swift", ".c",
    ".cc", ".cpp", ".h", ".hpp", ".rs", ".go", ".java", ".kt", ".rb", ".php",
    ".sh", ".bash", ".zsh", ".sql", ".graphql", ".proto", ".toml", ".yaml",
    ".yml", ".json", ".xml", ".svg", ".ini", ".cfg", ".conf", ".dockerfile",
}

DOC_TEXT_EXTENSIONS = {
    ".md", ".markdown", ".txt", ".log", ".csv", ".tsv", ".rst", ".env", ".gitignore",
}

_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{2,64}$")
_SAFE_NAME_CLEAN_RE = re.compile(r"[^A-Za-z0-9_\u4e00-\u9fa5.-]+")


def sanitize_attachment_filename(raw_name: str, fallback_ext: str = ".bin") -> str:
    base = os.path.basename(str(raw_name or "").strip().replace("\\", "/"))
    if not base or base in (".", ".."):
        base = f"attachment{fallback_ext}"
    stem, ext = os.path.splitext(base)
    clean_stem = _SAFE_NAME_CLEAN_RE.sub("_", stem).strip("._")[:48] or "file"
    clean_ext = re.sub(r"[^.A-Za-z0-9]", "", ext.lower())[:12] or fallback_ext
    if not clean_ext.startswith("."):
        clean_ext = f".{clean_ext}"
    return f"{clean_stem}{clean_ext}"


def inspect_raster_image_bytes(data: bytes) -> Optional[Tuple[str, str, int, int]]:
    """纯标准库校验光栅图片魔数并解析真实像素尺寸 (mime_type, ext, width, height)。"""
    n = len(data)
    if n < 16:
        return None

    # 1. PNG
    if data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR" and n >= 24:
        w, h = struct.unpack(">II", data[16:24])
        if w > 0 and h > 0:
            return "image/png", ".png", int(w), int(h)
        return None

    # 2. GIF87a / GIF89a
    if data[:6] in (b"GIF87a", b"GIF89a"):
        w, h = struct.unpack("<HH", data[6:10])
        if w > 0 and h > 0:
            return "image/gif", ".gif", int(w), int(h)
        return None

    # 3. WebP (RIFF....WEBP)
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP" and n >= 30:
        chunk_type = data[12:16]
        w, h = 0, 0
        if chunk_type == b"VP8X" and n >= 30:
            w = 1 + int.from_bytes(data[24:27], "little")
            h = 1 + int.from_bytes(data[27:30], "little")
        elif chunk_type == b"VP8 " and n >= 30:
            w = struct.unpack("<H", data[26:28])[0] & 0x3FFF
            h = struct.unpack("<H", data[28:30])[0] & 0x3FFF
        elif chunk_type == b"VP8L" and n >= 25 and data[20] == 0x2F:
            bits = struct.unpack("<I", data[21:25])[0]
            w = (bits & 0x3FFF) + 1
            h = ((bits >> 14) & 0x3FFF) + 1
        return "image/webp", ".webp", max(1, int(w)), max(1, int(h))

    # 4. JPEG
    if data[:3] == b"\xff\xd8\xff":
        idx = 2
        sof_markers = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
        while idx + 4 < n:
            if data[idx] != 0xFF:
                idx += 1
                continue
            while idx < n and data[idx] == 0xFF:
                idx += 1
            if idx >= n:
                break
            marker = data[idx]
            idx += 1
            if marker in (0xD8, 0xD9) or (0xD0 <= marker <= 0xD7) or marker == 0x01:
                continue
            if idx + 2 > n:
                break
            seg_len = struct.unpack(">H", data[idx : idx + 2])[0]
            if seg_len < 2 or idx + seg_len > n:
                break
            if marker in sof_markers and idx + 7 <= n:
                h, w = struct.unpack(">HH", data[idx + 3 : idx + 7])
                if w > 0 and h > 0:
                    return "image/jpeg", ".jpg", int(w), int(h)
            idx += seg_len
        return "image/jpeg", ".jpg", 0, 0

    return None


def _extract_pdf_text_fallback(data: bytes, max_chars: int = 24000) -> str:
    """纯标准库轻量提取 PDF 流内可读文本片段（配合原文件挂载供 CLI 深度读取）。"""
    pieces: List[str] = []
    # 解压常见 FlateDecode 内容流并抽取括号文本操作数
    for m in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", data, flags=re.DOTALL):
        raw_stream = m.group(1)
        candidates = [raw_stream]
        try:
            # A small PDF may contain a highly compressed stream. Only inflate a bounded excerpt.
            candidates.insert(0, zlib.decompressobj().decompress(raw_stream, max(65536, max_chars * 8)))
        except Exception:
            pass
        for buf in candidates[:1]:
            for txt_m in re.finditer(rb"\(([^()\\]{2,240})\)\s*Tj", buf):
                seg = txt_m.group(1).decode("utf-8", errors="ignore").strip()
                if seg and any(ch.isalnum() for ch in seg):
                    pieces.append(seg)
            if sum(len(x) for x in pieces) >= max_chars:
                break
        if sum(len(x) for x in pieces) >= max_chars:
            break
    joined = "\n".join(pieces).strip()
    return joined[:max_chars]


def _decode_safe_text_bytes(data: bytes) -> Tuple[bool, str]:
    if not data:
        return True, ""
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            return True, data.decode("utf-16")
        except Exception:
            return False, ""
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    null_count = data.count(b"\x00")
    if null_count > 0 and (null_count / max(1, len(data))) > 0.01:
        return False, ""
    return True, data.decode("utf-8", errors="replace")


def format_byte_size(num_bytes: int) -> str:
    b = max(0, int(num_bytes or 0))
    if b < 1024:
        return f"{b} B"
    if b < 1024 * 1024:
        return f"{b / 1024:.1f} KB"
    return f"{b / (1024 * 1024):.2f} MB"


class SessionAttachmentManager:
    """会话级多模态附件安全管理器（存储于 ~/.ai-roundtable/attachments/<session_id>/）。"""

    def __init__(self, runtime_home: Optional[str] = None) -> None:
        base = runtime_home or os.path.expanduser(os.environ.get("AI_ROUNDTABLE_HOME") or "~/.ai-roundtable")
        self.root_dir = Path(base).resolve() / "attachments"
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self._index_lock = threading.Lock()

    def _session_dir(self, session_id: str) -> Path:
        sid = str(session_id or "").strip()
        if not _SAFE_ID_RE.match(sid):
            raise ValueError("非法的会话标识")
        d = (self.root_dir / sid).resolve()
        if not d.is_relative_to(self.root_dir):
            raise ValueError("非法的会话附件目录")
        return d

    def _load_index(self, sdir: Path) -> List[dict]:
        idx_file = sdir / "index.json"
        if not idx_file.is_file():
            return []
        try:
            raw = json.loads(idx_file.read_text(encoding="utf-8"))
            if isinstance(raw, dict) and isinstance(raw.get("attachments"), list):
                return [x for x in raw["attachments"] if isinstance(x, dict) and x.get("id")]
        except Exception:
            pass
        return []

    def _save_index(self, sdir: Path, items: List[dict]) -> None:
        sdir.mkdir(parents=True, exist_ok=True)
        atomic_write_json_fsync(sdir / "index.json", {"attachments": items, "updated_ts": time.time()})

    @staticmethod
    def public_meta(entry: dict) -> dict:
        return {
            "id": str(entry.get("id") or ""),
            "name": str(entry.get("name") or ""),
            "kind": str(entry.get("kind") or "doc"),
            "mime_type": str(entry.get("mime_type") or "application/octet-stream"),
            "ext": str(entry.get("ext") or ""),
            "size_bytes": int(entry.get("size_bytes") or 0),
            "size_human": format_byte_size(int(entry.get("size_bytes") or 0)),
            "sha256": str(entry.get("sha256") or ""),
            "width": int(entry.get("width") or 0),
            "height": int(entry.get("height") or 0),
            "line_count": int(entry.get("line_count") or 0),
            "excerpt": str(entry.get("excerpt") or ""),
            "created_at": str(entry.get("created_at") or ""),
        }

    def list_attachments(self, session_id: str) -> List[dict]:
        sdir = self._session_dir(session_id)
        return [self.public_meta(it) for it in self._load_index(sdir)]

    def save_base64_attachment(
        self, session_id: str, *, filename: str, data_base64: str, declared_mime: str = "",
    ) -> dict:
        with self._index_lock:
            return self._save_base64_attachment(session_id, filename=filename, data_base64=data_base64, declared_mime=declared_mime)

    def _save_base64_attachment(
        self,
        session_id: str,
        *,
        filename: str,
        data_base64: str,
        declared_mime: str = "",
    ) -> dict:
        sdir = self._session_dir(session_id)
        b64_str = str(data_base64 or "").strip()
        if not b64_str:
            raise ValueError("附件内容为空")
        if b64_str.startswith("data:") and "," in b64_str:
            header_part, b64_str = b64_str.split(",", 1)
            if not declared_mime and ";" in header_part:
                declared_mime = header_part[5:].split(";", 1)[0].strip()

        try:
            raw_bytes = base64.b64decode(b64_str, validate=False)
        except Exception as exc:
            raise ValueError("附件 Base64 编码格式无效") from exc

        size_b = len(raw_bytes)
        if size_b <= 0:
            raise ValueError("禁止上传 0 字节空文件")
        if size_b > MAX_SINGLE_ATTACHMENT_BYTES:
            raise ValueError(f"单个附件大小超出 12 MiB 上限（当前 {format_byte_size(size_b)}）")

        digest = hashlib.sha256(raw_bytes).hexdigest()
        existing = self._load_index(sdir)

        img_info = inspect_raster_image_bytes(raw_bytes)
        orig_ext = os.path.splitext(str(filename or "").strip())[1].lower()
        dec_mime_low = str(declared_mime or "").strip().lower()

        width = 0
        height = 0
        line_count = 0
        excerpt = ""

        if img_info is not None:
            real_mime, real_ext, width, height = img_info
            safe_name = sanitize_attachment_filename(filename, fallback_ext=real_ext)
            if os.path.splitext(safe_name)[1].lower() not in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
                safe_name = os.path.splitext(safe_name)[0] + real_ext
            kind = "image"
            mime_type = real_mime
            ext = os.path.splitext(safe_name)[1].lower()
        elif raw_bytes.startswith((b"\x7fELF", b"MZ\x90\x00", b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf")):
            raise ValueError("不支持上传二进制可执行文件")
        elif orig_ext in (".png", ".jpg", ".jpeg", ".webp", ".gif") or (dec_mime_low.startswith("image/") and orig_ext != ".svg"):
            raise ValueError("图片文件头魔数校验未通过（仅支持真实的 PNG / JPEG / WebP / GIF / SVG 图像）")
        elif raw_bytes[:5] == b"%PDF-" or orig_ext == ".pdf":
            if raw_bytes[:5] != b"%PDF-":
                raise ValueError("PDF 文件头校验未通过")
            safe_name = sanitize_attachment_filename(filename, fallback_ext=".pdf")
            kind = "doc"
            mime_type = "application/pdf"
            ext = ".pdf"
            pdf_txt = _extract_pdf_text_fallback(raw_bytes, max_chars=2400)
            excerpt = pdf_txt[:600]
            line_count = len(pdf_txt.splitlines()) if pdf_txt else 0
        else:
            ok_txt, decoded_txt = _decode_safe_text_bytes(raw_bytes)
            if not ok_txt:
                raise ValueError("不支持上传未知二进制或可执行文件；请上传图片截图、源码、配置、日志、CSV/JSON、Markdown 或 PDF")
            fallback_e = orig_ext if (orig_ext in CODE_EXTENSIONS or orig_ext in DOC_TEXT_EXTENSIONS) else ".txt"
            safe_name = sanitize_attachment_filename(filename, fallback_ext=fallback_e)
            ext = os.path.splitext(safe_name)[1].lower()
            kind = "code" if ext in CODE_EXTENSIONS else "doc"
            guessed_mime, _ = mimetypes.guess_type(safe_name)
            mime_type = guessed_mime or "text/plain"
            lines = decoded_txt.splitlines()
            line_count = len(lines)
            excerpt = "\n".join(lines[:18])[:600]

        # 同会话内同内容同文件名幂等复用
        for it in existing:
            if it.get("sha256") == digest and it.get("name") == safe_name:
                disk_p = sdir / str(it.get("stored_name") or "")
                if disk_p.is_file():
                    return self.public_meta(it)

        if len(existing) >= MAX_SESSION_ATTACHMENTS:
            raise ValueError(f"本会话最多保存 {MAX_SESSION_ATTACHMENTS} 个附件，请先移除不再需要的附件")

        att_id = f"att_{uuid.uuid4().hex[:10]}"
        stored_name = f"{att_id}_{safe_name}"
        target_path = (sdir / stored_name).resolve()
        if not target_path.is_relative_to(sdir):
            raise ValueError("附件存储路径越界")

        atomic_write_bytes_fsync(target_path, raw_bytes, mode=0o600)
        entry = {
            "id": att_id,
            "name": safe_name,
            "stored_name": stored_name,
            "kind": kind,
            "mime_type": mime_type,
            "ext": ext,
            "size_bytes": size_b,
            "sha256": digest,
            "width": width,
            "height": height,
            "line_count": line_count,
            "excerpt": excerpt,
            "created_at": time.strftime("%H:%M:%S", time.localtime()),
        }
        existing.append(entry)
        self._save_index(sdir, existing)
        return self.public_meta(entry)

    def get_attachment_bytes(self, session_id: str, att_id: str) -> Tuple[Optional[dict], Optional[bytes]]:
        if not _SAFE_ID_RE.match(str(att_id or "")):
            return None, None
        sdir = self._session_dir(session_id)
        for it in self._load_index(sdir):
            if it.get("id") == att_id:
                fpath = (sdir / str(it.get("stored_name") or "")).resolve()
                if fpath.is_relative_to(sdir) and fpath.is_file():
                    return self.public_meta(it), fpath.read_bytes()
        return None, None

    def delete_attachment(self, session_id: str, att_id: str) -> bool:
        with self._index_lock:
            return self._delete_attachment(session_id, att_id)

    def _delete_attachment(self, session_id: str, att_id: str) -> bool:
        if not _SAFE_ID_RE.match(str(att_id or "")):
            return False
        sdir = self._session_dir(session_id)
        items = self._load_index(sdir)
        kept: List[dict] = []
        removed: Optional[dict] = None
        for it in items:
            if it.get("id") == att_id:
                removed = it
            else:
                kept.append(it)
        if removed is None:
            return False
        fpath = (sdir / str(removed.get("stored_name") or "")).resolve()
        try:
            if fpath.is_relative_to(sdir) and fpath.is_file():
                fpath.unlink()
        except OSError:
            pass
        self._save_index(sdir, kept)
        return True

    def delete_session_attachments(self, session_id: str) -> None:
        with self._index_lock:
            sdir = self._session_dir(session_id)
            if sdir.is_dir():
                shutil.rmtree(sdir)

    def resolve_attachments(self, session_id: str, attachment_ids: Optional[List[str]]) -> List[dict]:
        if not attachment_ids or not isinstance(attachment_ids, list):
            return []
        sdir = self._session_dir(session_id)
        by_id = {str(it.get("id")): it for it in self._load_index(sdir)}
        resolved: List[dict] = []
        seen: set = set()
        for raw_id in attachment_ids:
            aid = str(raw_id or "").strip()
            if not aid or aid in seen or aid not in by_id:
                continue
            it = by_id[aid]
            fpath = (sdir / str(it.get("stored_name") or "")).resolve()
            if fpath.is_relative_to(sdir) and fpath.is_file():
                seen.add(aid)
                resolved.append(self.public_meta(it))
        return resolved

    def stage_for_cli_turn(
        self,
        session_id: str,
        attachments_meta: Optional[List[dict]],
        call_tmp_dir: str,
        *,
        max_text_budget: int = MAX_PROMPT_ATTACHMENT_CHARS,
    ) -> Tuple[str, List[str]]:
        """
        将当前会话关联的图片与文件附件挂载到席位隔离的 `call_tmp_dir/rt_attachments/` 目录，
        返回 `(prompt_attachment_block, staged_raster_image_paths)`。
        """
        if not attachments_meta or not isinstance(attachments_meta, list) or not session_id:
            return "", []
        try:
            sdir = self._session_dir(session_id)
        except ValueError:
            return "", []

        by_id = {str(it.get("id")): it for it in self._load_index(sdir)}
        if not by_id:
            return "", []

        if not call_tmp_dir or not Path(call_tmp_dir).is_dir() or Path(call_tmp_dir).is_symlink():
            raise ValueError("缺少隔离的席位临时目录")
        stage_root = Path(call_tmp_dir).resolve() / "rt_attachments"
        if stage_root.is_symlink():
            raise ValueError("附件挂载目录不能是符号链接")
        stage_root.mkdir(mode=0o700, exist_ok=True)

        blocks: List[str] = []
        staged_images: List[str] = []
        used_chars = 0

        for idx, meta in enumerate(attachments_meta, start=1):
            if not isinstance(meta, dict):
                continue
            aid = str(meta.get("id") or "").strip()
            rec = by_id.get(aid)
            if not rec:
                continue
            src_path = (sdir / str(rec.get("stored_name") or "")).resolve()
            if not src_path.is_relative_to(sdir) or not src_path.is_file():
                continue

            safe_name = sanitize_attachment_filename(rec.get("name") or src_path.name)
            dst_path = stage_root / f"{idx:02d}_{safe_name}"
            # Always replace a private copy; never follow a pre-existing link or pass the archive path to a CLI.
            raw_data = src_path.read_bytes()
            atomic_write_bytes_fsync(dst_path, raw_data, mode=0o600 if os.name == "nt" else 0o400)

            kind = str(rec.get("kind") or "doc")
            size_h = format_byte_size(int(rec.get("size_bytes") or 0))
            ext = str(rec.get("ext") or "").lstrip(".") or "txt"

            if kind == "image":
                w = int(rec.get("width") or 0)
                h = int(rec.get("height") or 0)
                dim_str = f"{w}×{h} px, " if (w > 0 and h > 0) else ""
                staged_images.append(str(dst_path))
                blocks.append(
                    f"【多模态图像附件 #{idx}：{safe_name}（{dim_str}{size_h}）】\n"
                    f"- 本地可读图片路径：`{dst_path}`\n"
                    f"- 视觉审阅提示：可直接调用图片/文件查看工具读取上述路径图像，结合画面布局、文案、报错细节开展分析。"
                )
                continue

            if rec.get("mime_type") == "application/pdf" or ext == "pdf":
                pdf_text = _extract_pdf_text_fallback(raw_data, max_chars=min(12000, max(2000, max_text_budget - used_chars)))
                snippet_note = (
                    f"```text\n{pdf_text}\n```"
                    if pdf_text
                    else "（PDF 内嵌扫描图或压缩流，必要时可直接按本地只读路径检查文件）"
                )
                blk = (
                    f"【文档附件 #{idx}：{safe_name}（PDF, {size_h}）】\n"
                    f"- 本地只读路径：`{dst_path}`\n"
                    f"{snippet_note}"
                )
                blocks.append(blk)
                used_chars += len(blk)
                continue

            _, txt_content = _decode_safe_text_bytes(raw_data)
            lines = txt_content.splitlines()
            numbered = "\n".join(f"L{ln_no}: {ln}" for ln_no, ln in enumerate(lines[:800], start=1))
            rem = max(1200, max_text_budget - used_chars)
            if len(numbered) > rem:
                numbered = numbered[:rem] + f"\n... [附件全文共 {len(lines)} 行，完整文件位于 {dst_path}]"
            blk = (
                f"【{'代码/配置' if kind == 'code' else '文本/数据'}附件 #{idx}：{safe_name}（共 {len(lines)} 行, {size_h}）】\n"
                f"- 本地只读路径：`{dst_path}`\n"
                f"```{ext}\n{numbered}\n```"
            )
            blocks.append(blk)
            used_chars += len(blk)

        if not blocks:
            return "", staged_images

        header = "【用户随议题上传的多模态图片与参考文件附件（已隔离挂载，不影响工作区文件状态）】：\n"
        return header + "\n\n".join(blocks), staged_images
