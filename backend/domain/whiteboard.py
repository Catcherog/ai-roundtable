# -*- coding: utf-8 -*-
"""
AI圆桌 — 结构化白板领域子模块（Phase 2 解耦）

职责范围：
1. 三区结构化白板（decision / risk / action）与 v3 旧四数组（chair_constraints / carbon_plan / grok_risks / astra_actions）双向无损同步；
2. 确定性白板条目 ID（wb_{prefix}_{ordinal}_{sha1_8}）与全 6 席 + 主持人发言卡片溯源映射（_infer_source_msg_id）；
3. 独立软上限配额池（未置顶 risk 60 条、未置顶且未勾选 action 60 条独立核算，checked=True 与 pinned=True 硬豁免保护）；
4. 过程性工具独白过滤（is_whiteboard_noise）、议题短标题提炼与最终决议正负面清单物理隔离提取。
"""

from __future__ import annotations

import hashlib
import re
import time
from typing import Dict, List, Optional, Set, Tuple

from . import ALL_SEAT_IDS, VALID_ORIGIN_TIERS


WHITEBOARD_LIST_KEYS = ("chair_constraints", "carbon_plan", "grok_risks", "astra_actions")
VALID_WB_KINDS = ("decision", "risk", "action")
VALID_WB_AUTHORS = ("chair", "carbon", "grok", "astra", "vega", "titan", "prism", "system")
UNPINNED_WB_SOFT_LIMIT = 60
DISAGREEMENT_KEYWORDS = ("存疑", "分歧", "反对", "漏洞", "阻塞", "不同意", "待定", "需修", "质疑", "未决")

DEFAULT_SEAT_WB_KINDS: Dict[str, str] = {
    "chair": "decision",
    "carbon": "decision",
    "grok": "risk",
    "astra": "action",
    "vega": "action",
    "titan": "risk",
    "prism": "action",
}

STALE_STREAMING_BADGES = frozenset(
    {"思考中", "发言中", "调用中", "重试中", "排队等待发言…", "汇总决议中", "正在深度推演…"}
)

_CONVERSATIONAL_NOISE_PREFIX = re.compile(
    r"^(?:我只查公开资料|先核实|同意|完全赞同|赞同|收到|好的|没问题|说得好|整体可行|补充一点|针对\s*@|工程侧赞同|综合\s*@|以下是|作为)",
    re.IGNORECASE,
)

_TOOL_MONOLOGUE_NOISE_RE = re.compile(
    r"^(?:"
    r"我(?:先|这就|来|去|将|准备|需要|正在|只)?\s*(?:只读|核对|查看|读取|检查|检索|扫描|查阅|浏览|打开|看下|看一下|查一下|只查|核实|定位)"
    r"|先\s*(?:只读|核对|查看|读取|检查|检索|看下|看一下|看源码|核实|对一下|浏览|扫描)"
    r"|让我(?:先)?\s*(?:只读|核对|查看|读取|检查|看下|浏览)"
    r"|正在\s*(?:只读|读取|核对|查看|检索|扫描|浏览)"
    r"|接下来我(?:先)?\s*(?:只读|核对|查看|读取|检查)"
    r"|只读(?:查看|读取|浏览|核对|扫描|检查)"
    r"|不(?:改|修改|改动|写入)任何(?:本地)?(?:文件|代码|源码)"
    r"|Finishing\s+session"
    r")",
    re.IGNORECASE,
)

_PROCEDURAL_INLINE_BLACKLIST_RE = re.compile(
    r"(?:"
    r"我(?:先|只|正在)\s*(?:只读|核对|查看|读取|检查|检索|扫描|浏览)"
    r"|先(?:查看|只读|核对|读取|看下|看一下)"
    r"|不(?:改|修改|改动|写入)任何(?:本地)?(?:文件|代码|源码)"
    r"|只读[^。；\n]{0,20}不改任何文件"
    r")",
    re.IGNORECASE,
)


def now_hhmmss() -> str:
    return time.strftime("%H:%M:%S", time.localtime())


def now_display_time() -> str:
    return time.strftime("%m-%d %H:%M", time.localtime())


_MD_LINK_URL_RE = re.compile(r"\[([^\[\]]+)\]\((?:file://|https?://|/)[^)\s]*\)", re.IGNORECASE)


def strip_markdown_links(text: str) -> str:
    """将 Markdown 文件或网页链接 [label](file:///...) 收敛为纯可读标签 label，避免冗长本地绝对 URI 污染白板。"""
    if not text:
        return ""
    return _MD_LINK_URL_RE.sub(r"\1", str(text))


def _norm_dedupe_key(text: str) -> str:
    return re.sub(r"[^\w\u4e00-\u9fa5]+", "", strip_markdown_links(text or "").strip().lower())


def smart_clip(text: str, limit: int = 165) -> str:
    s = strip_markdown_links(text or "").strip()
    if len(s) <= limit:
        return s
    cut = s[:limit]
    for sep in ("；", "，", "。", "、", " "):
        idx = cut.rfind(sep)
        if idx >= int(limit * 0.65):
            return cut[:idx] + "…"
    return cut + "…"


def _empty_session_draft(topic: str, messages: list, board: dict) -> bool:
    has_entries = isinstance(board, dict) and any(board.get(key) for key in ("items", *WHITEBOARD_LIST_KEYS))
    return not str(topic or "").strip() and not messages and not has_entries


def is_whiteboard_noise(text: str) -> bool:
    """拦截模型工具读取独白、纯冒号结构小标题、过程性铺垫与空泛寒暄，严禁进入结构化白板。"""
    cleaned = strip_markdown_links(text or "").strip()
    s = re.sub(r"^(?:[-*•]+|\d+[.)、]|[①②③④⑤⑥⑦⑧⑨⑩])\s*(?:\[[xX✓✔ ]\]\s*)?", "", cleaned).strip()
    s = re.sub(r"\*\*([^*]+)\*\*", r"\1", s).strip()
    s = re.sub(r"`([^`]+)`", r"\1", s).strip()
    if len(s) < 4:
        return True
    if s in ("无", "暂无", "待补充", "发言完成", "略", "暂无记录"):
        return True
    if re.match(r"^[^。！？!?\n]{1,32}[:：]$", s):
        return True
    if _CONVERSATIONAL_NOISE_PREFIX.match(s):
        return True
    if _TOOL_MONOLOGUE_NOISE_RE.match(s):
        return True
    if _PROCEDURAL_INLINE_BLACKLIST_RE.search(s):
        return True
    return False


def make_deterministic_wb_id(seat_or_bucket: str, ordinal: int, text: str) -> str:
    """按「桶名/来源标识 + 序号 + 归一化内容短哈希」生成跨重启稳定的确定性白板条目 ID。"""
    prefix = re.sub(r"[^a-z0-9_]", "", (seat_or_bucket or "wb").lower())[:12] or "wb"
    norm = _norm_dedupe_key(text) or (text or "").strip()
    digest = hashlib.sha1(f"{prefix}:{ordinal}:{norm}".encode("utf-8")).hexdigest()[:8]
    return f"wb_{prefix}_{ordinal}_{digest}"


def _infer_source_msg_id(seat: str, point_text: str, messages: List[dict]) -> str:
    """为白板及历史迁移条目关联对应 6 席或主持人发言卡片 ID，支持前端一键定位高亮。"""
    if not messages or seat not in (*ALL_SEAT_IDS, "chair"):
        return ""
    norm_pt = _norm_dedupe_key(point_text)[:12]
    candidates = [m for m in messages if isinstance(m, dict) and m.get("speaker") == seat and m.get("id")]
    if not candidates:
        return ""
    if norm_pt and len(norm_pt) >= 4:
        for m in reversed(candidates):
            if norm_pt in _norm_dedupe_key(str(m.get("content") or "")):
                return str(m["id"])
    return str(candidates[-1]["id"])


def summarize_topic_and_constraints(raw_topic: str) -> Tuple[str, List[str]]:
    """
    将用户输入议题提炼为：
    1) 精炼短标题 topic_title（<= 28 字）；
    2) 独立约束列表 extracted_constraints（仅当多行输入包含明确分点/附加条款时提取，绝不重复首句或整段原话）。
    """
    cleaned = (raw_topic or "").strip()
    if not cleaned:
        return "", []

    lines = [ln.strip() for ln in cleaned.splitlines() if ln.strip()]
    first_line = re.sub(r"^(?:[#>*•\-]+|\d+[.)、])\s*", "", lines[0]).strip()
    first_clause = re.split(r"[。！？!?；;\n]", first_line)[0].strip()
    candidate = first_clause or first_line
    if len(candidate) > 28:
        sub_clauses = [seg.strip() for seg in re.split(r"[，,：:——]+", candidate) if seg.strip()]
        if sub_clauses and 4 <= len(sub_clauses[0]) <= 28:
            candidate = sub_clauses[0]
        else:
            candidate = candidate[:27].rstrip("，,、：:；; ") + "…"

    full_norm = _norm_dedupe_key(cleaned)
    title_norm = _norm_dedupe_key(candidate)

    extracted: List[str] = []
    if len(lines) > 1:
        for ln in lines[1:]:
            item = re.sub(r"^(?:[-*•]+|\d+[.)、]|[①②③④⑤⑥⑦⑧⑨⑩])\s*", "", ln).strip()
            if not item or len(item) < 3:
                continue
            item_norm = _norm_dedupe_key(item)
            if not item_norm or item_norm == full_norm or item_norm == title_norm:
                continue
            clipped = item[:150] + ("…" if len(item) > 150 else "")
            if all(_norm_dedupe_key(ex) != _norm_dedupe_key(clipped) for ex in extracted):
                extracted.append(clipped)
            if len(extracted) >= 8:
                break

    return candidate, extracted


def dedupe_chair_constraints(topic: str, topic_title: str, constraints: List[str]) -> List[str]:
    """清理白板主持约束中与完整议题或短标题重复的条目，保留真正的独立约束项。"""
    if not isinstance(constraints, list):
        return []
    topic_norm = _norm_dedupe_key(topic)
    title_norm = _norm_dedupe_key(topic_title)
    out: List[str] = []
    seen: set = set()
    for raw in constraints:
        txt = str(raw or "").strip()
        if not txt:
            continue
        kn = _norm_dedupe_key(txt)
        if not kn:
            continue
        if kn == topic_norm or kn == title_norm:
            continue
        if topic_norm and len(topic_norm) >= 24 and len(kn) >= int(len(topic_norm) * 0.85):
            if kn.startswith(topic_norm[:24]) or topic_norm.startswith(kn[:24]):
                continue
        if kn not in seen:
            seen.add(kn)
            out.append(txt)
    return out[:16]


def sync_whiteboard_legacy_arrays_and_caps(wb: dict) -> None:
    """
    独立配额池裁剪与旧数组双向同步：
    - decision 共识约束、pinned=True 置顶条目、以及 checked=True 待执行 action 条目享受淘汰豁免硬保护；
    - 未置顶 risk 与未置顶且未勾选 action 各自独立享有 60 条软上限配额池，互不挤占；
    - 每次修改后同步回写 chair_constraints / carbon_plan / grok_risks / astra_actions 四个兼容字段。
    """
    items = wb.get("items")
    if not isinstance(items, list):
        items = []
        wb["items"] = items

    unpinned_risk_indices = [
        idx
        for idx, it in enumerate(items)
        if isinstance(it, dict) and not it.get("pinned") and it.get("kind") == "risk"
    ]
    unpinned_unchecked_action_indices = [
        idx
        for idx, it in enumerate(items)
        if isinstance(it, dict)
        and not it.get("pinned")
        and it.get("kind") == "action"
        and not bool(it.get("checked", False))
    ]
    drop_set: Set[int] = set()
    if len(unpinned_risk_indices) > UNPINNED_WB_SOFT_LIMIT:
        drop_set.update(unpinned_risk_indices[: len(unpinned_risk_indices) - UNPINNED_WB_SOFT_LIMIT])
    if len(unpinned_unchecked_action_indices) > UNPINNED_WB_SOFT_LIMIT:
        drop_set.update(
            unpinned_unchecked_action_indices[: len(unpinned_unchecked_action_indices) - UNPINNED_WB_SOFT_LIMIT]
        )
    if drop_set:
        wb["items"] = [it for idx, it in enumerate(items) if idx not in drop_set]
        items = wb["items"]

    ordered = [
        it for it in items if isinstance(it, dict) and (it.get("pinned") or it.get("kind") == "decision")
    ] + [
        it for it in items if isinstance(it, dict) and not (it.get("pinned") or it.get("kind") == "decision")
    ]

    chair_arr: List[str] = []
    plan_arr: List[str] = []
    risk_arr: List[str] = []
    action_arr: List[str] = []

    for it in ordered:
        txt = str(it.get("text") or "").strip()
        if not txt:
            continue
        kind = str(it.get("kind") or "decision")
        author = str(it.get("author") or "chair")
        if kind == "decision":
            if author == "chair":
                if txt not in chair_arr:
                    chair_arr.append(txt)
            else:
                if txt not in plan_arr:
                    plan_arr.append(txt)
        elif kind == "risk":
            if txt not in risk_arr:
                risk_arr.append(txt)
        elif kind == "action":
            if bool(it.get("checked", True)) and txt not in action_arr:
                action_arr.append(txt)

    wb["chair_constraints"] = chair_arr[:24]
    wb["carbon_plan"] = plan_arr[:24]
    wb["grok_risks"] = risk_arr[:24]
    wb["astra_actions"] = action_arr[:24]


def _normalize_and_sync_whiteboard(
    wb: dict,
    topic: str = "",
    messages: Optional[List[dict]] = None,
    seat_states: Optional[Dict[str, dict]] = None,
) -> dict:
    """
    归一化并双向同步三区结构化白板：
    - 支持全 6 席（carbon/grok/astra/vega/titan/prism）及 chair/system 归属与动态 wb_kind；
    - 加载旧会话（仅有 chair_constraints / carbon_plan / grok_risks / astra_actions）时稳定迁移生成 items；
    - 同步回写四个旧数组字段，确保 v3/v4 SQLite 存储与历史测试 100% 双向兼容。
    """
    if not isinstance(wb, dict):
        wb = {}
    wb["wb_version"] = max(1, int(wb.get("wb_version") or 1))
    if topic and not wb.get("topic"):
        wb["topic"] = topic
    short_title, _ = summarize_topic_and_constraints(wb.get("topic") or topic)
    if short_title and not wb.get("topic_title"):
        wb["topic_title"] = short_title

    msg_list = messages if isinstance(messages, list) else []
    raw_items = wb.get("items")

    if isinstance(raw_items, list):
        normalized_items: List[dict] = []
        seen_ids: set = set()
        seen_norm_decisions: set = set()

        has_chair_item = any(
            isinstance(x, dict) and (x.get("author") == "chair" or x.get("source_seat") == "chair")
            for x in raw_items
        )
        raw_chair_list = wb.get("chair_constraints")
        if not has_chair_item and isinstance(raw_chair_list, list) and raw_chair_list:
            clean_chair = dedupe_chair_constraints(
                wb.get("topic") or topic,
                wb.get("topic_title", ""),
                raw_chair_list,
            )
            for c_idx, c_txt in enumerate(clean_chair):
                nk = _norm_dedupe_key(c_txt)
                if not nk or nk in seen_norm_decisions:
                    continue
                seen_norm_decisions.add(nk)
                cid = make_deterministic_wb_id("chair_constraints", c_idx, c_txt)
                seen_ids.add(cid)
                normalized_items.append(
                    {
                        "id": cid,
                        "kind": "decision",
                        "text": c_txt,
                        "author": "chair",
                        "origin_tier": "chair_directive",
                        "source_msg_id": _infer_source_msg_id("chair", c_txt, msg_list),
                        "pinned": True,
                        "checked": True,
                        "ver": 1,
                    }
                )

        for idx, raw_it in enumerate(raw_items):
            if not isinstance(raw_it, dict):
                continue
            txt = strip_markdown_links(str(raw_it.get("text") or "")).strip()
            if not txt:
                continue
            raw_kind = str(raw_it.get("kind") or "").strip().lower()
            raw_bucket = str(raw_it.get("bucket") or "").strip().lower()
            raw_author = str(raw_it.get("author") or raw_it.get("source_seat") or "").strip().lower()
            pinned = bool(raw_it.get("pinned", False))
            adopted = bool(raw_it.get("adopted", False))

            if raw_kind in VALID_WB_KINDS:
                kind = raw_kind
            elif adopted:
                kind = "decision"
            elif raw_bucket in ("chair_constraints", "carbon_plan", "consensus"):
                kind = "decision"
            elif raw_bucket == "grok_risks":
                kind = "risk"
            elif raw_bucket == "astra_actions":
                kind = "action"
            else:
                dyn_kind = (
                    str((seat_states.get(raw_author) or {}).get("wb_kind") or "").strip().lower()
                    if isinstance(seat_states, dict)
                    else ""
                )
                if dyn_kind in VALID_WB_KINDS:
                    kind = dyn_kind
                else:
                    kind = DEFAULT_SEAT_WB_KINDS.get(raw_author, "decision")

            if raw_author not in VALID_WB_AUTHORS:
                raw_author = {
                    "chair_constraints": "chair",
                    "carbon_plan": "carbon",
                    "grok_risks": "grok",
                    "astra_actions": "astra",
                }.get(raw_bucket, "chair" if kind == "decision" else "system")

            if not pinned and kind != "decision" and is_whiteboard_noise(txt):
                continue
            if raw_author != "chair" and is_whiteboard_noise(txt) and not pinned and not adopted:
                continue

            nk = _norm_dedupe_key(txt)
            if kind == "decision" and nk in seen_norm_decisions:
                continue
            if kind == "decision" and nk:
                seen_norm_decisions.add(nk)

            det_id = str(raw_it.get("id") or "").strip() or make_deterministic_wb_id(f"{kind}_{raw_author}", idx, txt)
            if det_id in seen_ids:
                det_id = make_deterministic_wb_id(f"{kind}_{raw_author}", idx + 1000, txt)
            seen_ids.add(det_id)

            src_msg_id = str(raw_it.get("source_msg_id") or "").strip()
            if not src_msg_id and raw_author in (*ALL_SEAT_IDS, "chair"):
                src_msg_id = _infer_source_msg_id(raw_author, txt, msg_list)

            raw_origin = str(raw_it.get("origin_tier") or "").strip()
            if raw_origin in VALID_ORIGIN_TIERS:
                origin_tier = raw_origin
            elif raw_author == "chair":
                origin_tier = "chair_directive"
            elif kind == "decision":
                origin_tier = "multi_seat_consensus"
            else:
                origin_tier = "provisional_suggestion"

            checked = bool(raw_it.get("checked", True))
            ver = max(1, int(raw_it.get("ver") or raw_it.get("version") or 1))
            norm_entry: dict = {
                "id": det_id,
                "kind": kind,
                "text": txt,
                "author": raw_author,
                "origin_tier": origin_tier,
                "source_msg_id": src_msg_id,
                "pinned": pinned,
                "checked": checked,
                "ver": ver,
            }
            if raw_it.get("provisional_decision"):
                norm_entry["provisional_decision"] = True
            if raw_it.get("adopted_by"):
                norm_entry["adopted_by"] = str(raw_it["adopted_by"])
            if raw_it.get("adopted_at"):
                norm_entry["adopted_at"] = str(raw_it["adopted_at"])
            if raw_it.get("disagreement_id"):
                norm_entry["disagreement_id"] = str(raw_it["disagreement_id"])
            if raw_it.get("rebutted"):
                norm_entry["rebutted"] = True
            normalized_items.append(norm_entry)
        wb["items"] = normalized_items
    else:
        migrated: List[dict] = []
        seen_norm: set = set()
        legacy_mapping = (
            ("chair_constraints", "decision", "chair", True),
            ("carbon_plan", "decision", "carbon", False),
            ("grok_risks", "risk", "grok", False),
            ("astra_actions", "action", "astra", False),
        )
        for bkey, mapped_kind, mapped_author, default_pinned in legacy_mapping:
            raw_arr = wb.get(bkey)
            if not isinstance(raw_arr, list):
                continue
            if bkey == "chair_constraints":
                raw_arr = dedupe_chair_constraints(wb.get("topic") or topic, wb.get("topic_title", ""), raw_arr)
            for local_idx, raw_txt in enumerate(raw_arr):
                txt = str(raw_txt or "").strip()
                if not txt:
                    continue
                if bkey != "chair_constraints" and is_whiteboard_noise(txt):
                    continue
                nk = _norm_dedupe_key(txt)
                if not nk or nk in seen_norm:
                    continue
                seen_norm.add(nk)
                migrated.append(
                    {
                        "id": make_deterministic_wb_id(bkey, local_idx, txt),
                        "kind": mapped_kind,
                        "text": txt,
                        "author": mapped_author,
                        "origin_tier": "chair_directive"
                        if mapped_author == "chair"
                        else ("multi_seat_consensus" if mapped_kind == "decision" else "provisional_suggestion"),
                        "source_msg_id": _infer_source_msg_id(mapped_author, txt, msg_list),
                        "pinned": default_pinned,
                        "checked": True,
                        "ver": 1,
                    }
                )
        wb["items"] = migrated

    if not isinstance(wb.get("absent_seats"), list):
        wb["absent_seats"] = []
    if not isinstance(wb.get("disagreements"), list):
        wb["disagreements"] = []
    if not isinstance(wb.get("abandoned_proposals"), list):
        wb["abandoned_proposals"] = []
    if not isinstance(wb.get("absorbed_highlights"), list):
        wb["absorbed_highlights"] = []
    if not isinstance(wb.get("round_summaries"), list):
        wb["round_summaries"] = []
    if not isinstance(wb.get("resolution_meta"), dict):
        wb["resolution_meta"] = {}

    sync_whiteboard_legacy_arrays_and_caps(wb)
    return wb


normalize_whiteboard_structure = _normalize_and_sync_whiteboard


def sanitize_persisted_message(mc: dict, fallback_badge: str = "已中断") -> dict:
    """清理非流式消息中残留的「思考中」徽章与空白僵尸消息体。"""
    mc.pop("activity", None)
    mc.pop("_start_seq", None)
    mc.pop("_done_seq", None)
    was_streaming = bool(mc.get("streaming"))
    if was_streaming:
        mc["streaming"] = False
    cur_badge = str(mc.get("badge") or "").strip()
    if was_streaming or cur_badge in STALE_STREAMING_BADGES or cur_badge.startswith("正在"):
        mc["badge"] = (
            fallback_badge
            if (was_streaming or not cur_badge or cur_badge in STALE_STREAMING_BADGES or cur_badge.startswith("正在"))
            else cur_badge
        )

    body_txt = str(mc.get("content") or "").strip()
    if not mc.get("streaming") and not body_txt and not mc.get("error") and not mc.get("skipped"):
        mc["skipped"] = True
        mc["badge"] = fallback_badge
        mc["content"] = f"*（该轮发言未完成：{fallback_badge}）*"
    return mc


def extract_key_points_from_markdown(text: str, max_items: int = 2) -> List[str]:
    if not text:
        return []
    cleaned = re.sub(r"\[(?:状态|徽章|白板|白板要点)[:：][^\]]*\]", "", text)
    cleaned = re.sub(r"```[\s\S]*?```", "", cleaned)
    cleaned = strip_markdown_links(cleaned)
    cleaned = re.sub(r"\*\*([^*]+)\*\*", r"\1", cleaned)
    cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)

    points: List[str] = []
    for raw_line in cleaned.splitlines():
        ln = raw_line.strip()
        if not ln or ln.startswith("#"):
            continue
        m_bullet = re.match(r"^(?:[-*•]|\d+[.)、]|[①②③④⑤])\s*(.+)$", ln)
        if m_bullet:
            candidate = m_bullet.group(1).strip()
            if len(candidate) >= 6 and not is_whiteboard_noise(candidate):
                points.append(smart_clip(candidate))

    if points:
        return points[:max_items]

    numbered = re.findall(r"(?:[1-4①②③④]\s*[\)）、.]|[一二三四]是)\s*([^；;。！!\n]{6,160})", cleaned)
    valid_num = [smart_clip(s) for s in numbered if not is_whiteboard_noise(s.strip())]
    if valid_num:
        return valid_num[:max_items]

    sentences = [
        smart_clip(s)
        for s in re.split(r"[。！？!\n；;]+", cleaned)
        if len(s.strip()) >= 10 and not is_whiteboard_noise(s.strip())
    ]
    return sentences[:max_items]


__all__ = [
    "DEFAULT_SEAT_WB_KINDS",
    "DISAGREEMENT_KEYWORDS",
    "STALE_STREAMING_BADGES",
    "UNPINNED_WB_SOFT_LIMIT",
    "VALID_WB_AUTHORS",
    "VALID_WB_KINDS",
    "WHITEBOARD_LIST_KEYS",
    "_empty_session_draft",
    "_infer_source_msg_id",
    "_norm_dedupe_key",
    "_normalize_and_sync_whiteboard",
    "dedupe_chair_constraints",
    "extract_key_points_from_markdown",
    "is_whiteboard_noise",
    "make_deterministic_wb_id",
    "normalize_whiteboard_structure",
    "now_display_time",
    "now_hhmmss",
    "sanitize_persisted_message",
    "smart_clip",
    "strip_markdown_links",
    "summarize_topic_and_constraints",
    "sync_whiteboard_legacy_arrays_and_caps",
]
