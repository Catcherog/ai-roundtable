# -*- coding: utf-8 -*-
"""
AI圆桌 — 多 CLI 协同研讨与工程交付编排器
核心能力：
1. 五大差异化研讨拓扑（深度研讨 / 正反辩证 / 发散收敛 / 代码审查 / 快速合议）与单席专注自检闭环
2. 内置 7 项专业角色职责预设，支持实时切换并联动提示词、收敛路由与白板默认归类
3. 三区结构化会议白板（已确认共识与约束 / 待决争议与风险项 / 待执行任务清单）与勾选任务精准执行联动
4. 可配置运行与时限策略、实时中间状态透传、单席非阻塞跳过与异常三级就地恢复
5. 会话级本地项目目录绑定、@源码行号检索、执行前 Git 快照与一键回滚
"""

from __future__ import annotations

import asyncio
import copy
import glob
import hashlib
import json
import os
import re
import time
import uuid
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# AI_ROUNDTABLE_V2_UPGRADE_20261114
from .cli_adapters import (
    DEFAULT_SEAT_PERSONAS,
    DRIVER_SPECS,
    MAX_ROUND_SOURCE_CHARS,
    PERSONA_PRESETS,
    ROSTER_NAME_PRESETS,
    VALID_DRIVERS,
    VALID_EFFORT_LEVELS,
    VALID_PERSONAS,
    VALID_ROSTER_PRESETS,
    CLIInvocationError,
    RuntimeSettings,
    UnifiedAgentRunner,
    detect_driver_binary,
    export_model_effort_catalog,
    get_persona_spec,
    is_git_workspace,
    is_real_bound_workspace,
    DEFAULT_IDLE_TIMEOUT_SEC,
    DEFAULT_TURN_TIMEOUT_SEC,
    build_host_env,
    list_workspace_files,
    list_workspace_files_async,
    normalize_model_effort,
    parse_structured_tail_with_kinds,
    resolve_effective_model_for_driver,
    step_down_model_effort,
    validate_referenced_files_snapshot,
)
from collections import deque
from .context import invalidate_workspace_index
from .domain import (
    ALL_SEAT_IDS,
    CLASSIC_SEAT_IDS,
    DRIVER_PROVIDER_LABELS,
    IMMUTABLE_SEAT_CATALOG,
    SCENARIO_INTENT_PACKS,
    SCENARIO_LINEUP_TEMPLATES,
    VALID_ARTIFACT_TYPES,
    VALID_ORIGIN_TIERS,
    can_auto_promote_consensus_decision,
    check_whiteboard_admission_gate,
    compute_effective_driver_families,
    compute_epistemic_status,
    normalize_driver_family_key,
    normalize_scenario_pack_and_artifact,
)
from .drivers import is_process_group_alive
from .engine import run_post_execution_verification
from .attachments import SessionAttachmentManager
from .storage import RoundtableSQLiteStore
from .workspace_backup import (
    WorkspaceAdmissionError,
    WorkspaceBackup,
    WorkspaceLockBusyError,
    WorkspaceWriteLock,
)


class ExecutionAdmissionConflictError(RuntimeError):
    def __init__(self, message: str, *, status_code: int = 409, details: Optional[dict] = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.details = details or {}

    def to_dict(self) -> dict:
        out = {"ok": False, "error": str(self)}
        out.update(self.details)
        return out


# 只读静态席位元数据（P0.1：严禁在任何会话逻辑中原地修改此全局字典，彻底杜绝跨会话席位名写污染）
AGENT_META = {
    aid: {
        "name": spec["default_name"],
        "title": spec["title"],
        "cli": spec["default_cli"],
        "color_token": spec["color_token"],
        "accent_hex": spec["accent_hex"],
    }
    for aid, spec in IMMUTABLE_SEAT_CATALOG.items()
}

DEFAULT_ENABLED_AGENTS = CLASSIC_SEAT_IDS
AGENT_ORDER = ALL_SEAT_IDS

COLLAB_MODES = {
    "deep_deliberation": {
        "label": "深度研讨",
        "rounds": 2,
        "desc": "独立立论 → 交叉质询 → 定向答辩 → 架构裁定",
    },
    "adversarial_review": {
        "label": "正反辩证",
        "rounds": 2,
        "desc": "主方案立论 → 反向压力审计 → 防御修正 → 综合裁定",
    },
    "divergent_convergent": {
        "label": "发散收敛",
        "rounds": 2,
        "desc": "多维方案发散 → 可行性与成本评估 → 优选方案收敛",
    },
    "code_review": {
        "label": "代码审查",
        "rounds": 2,
        "desc": "源码证据定位 → 调用链交叉核验 → 文件级修改方案",
    },
    "rapid_consensus": {
        "label": "快速合议",
        "rounds": 1,
        "desc": "单轮要点直出 → 核心风险核对 → 生成执行清单",
    },
}

LEGACY_COLLAB_MODE_MAP = {
    "standard_roundtable": "deep_deliberation",
    "red_blue_debate": "adversarial_review",
    "fast_align": "rapid_consensus",
    "arch_to_exec": "rapid_consensus",
}


def normalize_collab_mode(
    raw_mode: Optional[str],
    auto_preview_exec: Optional[bool] = None,
) -> Tuple[str, bool]:
    """归一化讨论策略 key 并兼容历史持久化的旧模式（如 arch_to_exec 解耦为 rapid_consensus + auto_preview_exec=True）。"""
    cleaned = str(raw_mode or "").strip()
    if cleaned == "arch_to_exec":
        return "rapid_consensus", (True if auto_preview_exec is None else bool(auto_preview_exec))
    mapped = LEGACY_COLLAB_MODE_MAP.get(cleaned, cleaned)
    if mapped not in COLLAB_MODES:
        mapped = "deep_deliberation"
    return mapped, bool(auto_preview_exec) if auto_preview_exec is not None else False


WHITEBOARD_LIST_KEYS = ("chair_constraints", "carbon_plan", "grok_risks", "astra_actions")
VALID_WB_KINDS = ("decision", "risk", "action")
VALID_WB_AUTHORS = ("chair", "carbon", "grok", "astra", "vega", "titan", "prism", "system")
UNPINNED_WB_SOFT_LIMIT = 60
DISAGREEMENT_KEYWORDS = ("存疑", "分歧", "反对", "漏洞", "阻塞", "不同意", "待定", "需修", "质疑", "未决")

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


def _empty_session_draft(topic: str, messages: list, board: dict) -> bool:
    has_entries = isinstance(board, dict) and any(board.get(key) for key in ("items", *WHITEBOARD_LIST_KEYS))
    return not str(topic or "").strip() and not messages and not has_entries


def is_whiteboard_noise(text: str) -> bool:
    """拦截模型工具读取独白、过程性铺垫与空泛寒暄，严禁进入结构化白板。"""
    s = re.sub(r"^(?:[-*•]+|\d+[.)、]|[①②③④⑤])\s*", "", (text or "").strip()).strip()
    if len(s) < 4:
        return True
    if s in ("无", "暂无", "待补充", "发言完成", "略"):
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
    """为历史迁移条目尽力关联左侧对应席位发言卡片 ID，支持一键定位高亮。"""
    if not messages or seat not in ("carbon", "grok", "astra", "chair"):
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


def sync_whiteboard_legacy_arrays_and_caps(wb: dict) -> None:
    """
    对未置顶的 risk/action 条目施加软上限（decision 共识约束与置顶条目永不淘汰），
    并每次修改后同步回写 chair_constraints / carbon_plan / grok_risks / astra_actions 四个兼容字段。
    """
    items = wb.get("items")
    if not isinstance(items, list):
        items = []
        wb["items"] = items

    unpinned_indices = [
        idx
        for idx, it in enumerate(items)
        if isinstance(it, dict) and not it.get("pinned") and it.get("kind") != "decision"
    ]
    if len(unpinned_indices) > UNPINNED_WB_SOFT_LIMIT:
        drop_count = len(unpinned_indices) - UNPINNED_WB_SOFT_LIMIT
        drop_set = set(unpinned_indices[:drop_count])
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
) -> dict:
    """
    归一化并双向同步三区结构化白板：
    - 每条结构：{"id": "wb_...", "kind": "decision"|"risk"|"action", "text": "...",
      "author": "chair"|"carbon"|"grok"|"astra"|"system", "source_msg_id": "m_xxx",
      "pinned": bool, "checked": bool, "ver": int}
    - 加载旧会话（仅有 chair_constraints / carbon_plan / grok_risks / astra_actions）时，
      按“桶名+序号+内容短哈希”稳定迁移生成 items；
    - 同步回写四个旧数组字段，确保旧逻辑与测试脚本 100% 兼容。
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

        # 若为旧过渡版 items（不含 kind 字段且 chair_constraints 独立存在），先吸收主持约束为 decision
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
            txt = str(raw_it.get("text") or "").strip()
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
                kind = {"chair": "decision", "carbon": "decision", "grok": "risk", "astra": "action"}.get(
                    raw_author, "decision"
                )

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
        # 旧会话（仅有四个字符串数组字段）按“桶名+序号+内容短哈希”确定性迁移
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
                        "origin_tier": "chair_directive" if mapped_author == "chair" else ("multi_seat_consensus" if mapped_kind == "decision" else "provisional_suggestion"),
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
    if not isinstance(wb.get("round_summaries"), list):
        wb["round_summaries"] = []
    if not isinstance(wb.get("resolution_meta"), dict):
        wb["resolution_meta"] = {}

    sync_whiteboard_legacy_arrays_and_caps(wb)
    return wb


normalize_whiteboard_structure = _normalize_and_sync_whiteboard

STALE_STREAMING_BADGES = frozenset(
    {"思考中", "发言中", "调用中", "重试中", "排队等待发言…", "汇总决议中", "正在深度推演…"}
)


def sanitize_persisted_message(mc: dict, fallback_badge: str = "已中断") -> dict:
    """
    清理非流式消息中残留的「思考中」徽章与空白僵尸消息体：
    根治历史会话重开或异常中断后页面出现大块空白「思考中」卡片的问题。
    """
    mc.pop("activity", None)
    mc.pop("_start_seq", None)
    mc.pop("_done_seq", None)
    was_streaming = bool(mc.get("streaming"))
    if was_streaming:
        mc["streaming"] = False
    cur_badge = str(mc.get("badge") or "").strip()
    if was_streaming or cur_badge in STALE_STREAMING_BADGES or cur_badge.startswith("正在"):
        mc["badge"] = fallback_badge if (was_streaming or not cur_badge or cur_badge in STALE_STREAMING_BADGES or cur_badge.startswith("正在")) else cur_badge

    body_txt = str(mc.get("content") or "").strip()
    if not mc.get("streaming") and not body_txt and not mc.get("error") and not mc.get("skipped"):
        mc["skipped"] = True
        mc["badge"] = fallback_badge
        mc["content"] = f"*（该轮发言未完成：{fallback_badge}）*"
    return mc


def now_hhmmss() -> str:
    return time.strftime("%H:%M:%S", time.localtime())


def now_display_time() -> str:
    return time.strftime("%m-%d %H:%M", time.localtime())


def _norm_dedupe_key(text: str) -> str:
    return re.sub(r"[^\w\u4e00-\u9fa5]+", "", (text or "").strip().lower())


def summarize_topic_and_constraints(raw_topic: str) -> Tuple[str, List[str]]:
    """
    将用户输入议题提炼为：
    1) 精炼短标题 topic_title（<= 28 字，避免白板粗体标题与顶栏重复铺满整段长文）；
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
        # 若某条约束与整段长议题高度重合（前缀相同且长度占议题 85% 以上），视为整段重复予以剔除
        if topic_norm and len(topic_norm) >= 24 and len(kn) >= int(len(topic_norm) * 0.85):
            if kn.startswith(topic_norm[:24]) or topic_norm.startswith(kn[:24]):
                continue
        if kn not in seen:
            seen.add(kn)
            out.append(txt)
    return out[:16]


@dataclass
class MeetingSession:
    session_id: str
    title: str
    topic: str = ""
    workspace_dir: str = ""
    collab_mode: str = "deep_deliberation"
    scenario_pack: str = "arch_code"
    artifact_type: str = "code_patch"
    auto_preview_exec: bool = False
    stage: str = "idle"
    created_at: str = field(default_factory=now_display_time)
    updated_ts: float = field(default_factory=time.time)
    enabled_agents: List[str] = field(default_factory=lambda: list(DEFAULT_ENABLED_AGENTS))
    seat_personas: Dict[str, str] = field(default_factory=dict)
    seat_efforts: Dict[str, str] = field(default_factory=dict)
    executor_agent: str = "astra"
    seat_states: Dict[str, dict] = field(default_factory=dict)
    messages: List[dict] = field(default_factory=list)
    whiteboard: dict = field(default_factory=dict)
    rev: int = 0
    exec_state: str = "idle"  # "idle" | "preparing" | "running"
    active_operation_id: str = ""
    active_run_id: str = ""
    execution_started_at: float = 0.0
    recovery_required: bool = False
    pending_recovery_backup: Optional[WorkspaceBackup] = field(default=None, repr=False)
    last_backup: Optional[WorkspaceBackup] = field(default=None, repr=False)
    subscribers: List[asyncio.Queue] = field(default_factory=list, repr=False)
    event_ring: deque = field(default_factory=lambda: deque(maxlen=1024), repr=False)
    session_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)
    cancelled_operations: set = field(default_factory=set, repr=False)
    round_driver_records: List[dict] = field(default_factory=list, repr=False)
    active_task: Optional[asyncio.Task] = field(default=None, repr=False)
    active_seat_tasks: Dict[str, asyncio.Task] = field(default_factory=dict, repr=False)
    active_seat_msgs: Dict[str, dict] = field(default_factory=dict, repr=False)
    skipped_seat_flags: set = field(default_factory=set, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.subscribers, list):
            self.subscribers = []
        if not isinstance(self.active_seat_tasks, dict):
            self.active_seat_tasks = {}
        if not isinstance(self.active_seat_msgs, dict):
            self.active_seat_msgs = {}
        if not isinstance(self.skipped_seat_flags, set):
            self.skipped_seat_flags = set()

        norm_mode, norm_auto_exec = normalize_collab_mode(
            self.collab_mode,
            auto_preview_exec=self.auto_preview_exec if self.collab_mode != "arch_to_exec" else None,
        )
        self.collab_mode = norm_mode
        self.auto_preview_exec = bool(self.auto_preview_exec or norm_auto_exec)

        wb_pack = str((self.whiteboard or {}).get("scenario_pack") or "") if isinstance(self.whiteboard, dict) else ""
        wb_art = str((self.whiteboard or {}).get("artifact_type") or "") if isinstance(self.whiteboard, dict) else ""
        self.scenario_pack, self.artifact_type = normalize_scenario_pack_and_artifact(
            self.scenario_pack or wb_pack,
            self.artifact_type or wb_art,
        )

        if not isinstance(self.session_lock, asyncio.Lock):
            self.session_lock = asyncio.Lock()
        if not isinstance(self.event_ring, deque):
            self.event_ring = deque(maxlen=1024)
        if not isinstance(self.cancelled_operations, set):
            self.cancelled_operations = set()
        if not isinstance(self.round_driver_records, list):
            self.round_driver_records = []

        if not self.enabled_agents:
            self.enabled_agents = list(DEFAULT_ENABLED_AGENTS)
        else:
            self.enabled_agents = [a for a in AGENT_ORDER if a in self.enabled_agents] or list(DEFAULT_ENABLED_AGENTS)

        normalized_personas: Dict[str, str] = {}
        for aid in AGENT_ORDER:
            raw_p = (self.seat_personas or {}).get(aid, "")
            normalized_personas[aid] = raw_p if raw_p in PERSONA_PRESETS else DEFAULT_SEAT_PERSONAS[aid]
        self.seat_personas = normalized_personas

        normalized_efforts: Dict[str, str] = {}
        if isinstance(self.seat_efforts, dict):
            for aid, raw_eff in self.seat_efforts.items():
                eff_s = str(raw_eff or "").strip().lower()
                if aid in AGENT_ORDER and eff_s in VALID_EFFORT_LEVELS:
                    normalized_efforts[aid] = eff_s
        self.seat_efforts = normalized_efforts

        if self.executor_agent not in AGENT_ORDER:
            self.executor_agent = "astra"

        if isinstance(self.messages, list) and self.messages:
            healed_msgs: List[dict] = []
            for raw_m in self.messages:
                if not isinstance(raw_m, dict):
                    continue
                mc = dict(raw_m)
                sanitize_persisted_message(mc, fallback_badge="已中断")
                healed_msgs.append(mc)
            self.messages = healed_msgs

        if not self.seat_states:
            self.seat_states = {}
        for aid, meta in AGENT_META.items():
            pspec = get_persona_spec(self.seat_personas[aid], fallback_agent_id=aid)
            st = self.seat_states.setdefault(
                aid,
                {
                    "agent_id": aid,
                    "name": meta["name"],
                    "title": pspec["short_tag"],
                    "persona": pspec["key"],
                    "persona_label": pspec["label"],
                    "wb_kind": pspec["wb_kind"],
                    "wb_title": pspec["wb_title"],
                    "cue_btn": pspec["cue_btn"].format(name=meta["name"]),
                    "cue_prompt": pspec["cue_prompt"],
                    "status": "idle",
                    "badge": "未开始",
                    "binary_ready": False,
                    "shared_fallback": False,
                    "cli_label": meta["cli"],
                    "enabled": aid in self.enabled_agents,
                    "ttft_ms": 0,
                    "elapsed_ms": 0,
                },
            )
            st["enabled"] = aid in self.enabled_agents
            st["persona"] = pspec["key"]
            st["persona_label"] = pspec["label"]
            st["title"] = pspec["short_tag"]
            st["wb_kind"] = pspec["wb_kind"]
            st["wb_title"] = pspec["wb_title"]
            st["cue_btn"] = pspec["cue_btn"].format(name=meta["name"])
            st["cue_prompt"] = pspec["cue_prompt"]

        short_topic_title, _ = summarize_topic_and_constraints(self.topic)
        default_wb = {
            "wb_version": 1,
            "topic": self.topic,
            "topic_title": short_topic_title,
            "consensus_status": "待输入议题",
            "scenario_pack": self.scenario_pack,
            "artifact_type": self.artifact_type,
            "epistemic_mode": "solo_draft" if len(self.enabled_agents) <= 1 else "homogeneous_warning",
            "epistemic_badge": "[单席推演草稿]" if len(self.enabled_agents) <= 1 else "[同源模型多视角推演 · 误差相关]",
            "chair_constraints": [],
            "items": [],
            "absent_seats": [],
            "disagreements": [],
            "abandoned_proposals": [],
            "round_summaries": [],
            "resolution_meta": {},
            "carbon_plan": [],
            "grok_risks": [],
            "astra_actions": [],
            "exec_logs": [],
            "exec_diff": "",
            "exec_summary": "",
            "executor_agent": self.effective_executor_agent(),
            "can_rollback": False,
        }
        if not self.whiteboard:
            self.whiteboard = default_wb
            _normalize_and_sync_whiteboard(self.whiteboard, topic=self.topic, messages=self.messages)
        else:
            for k, v in default_wb.items():
                if k == "items":
                    continue
                self.whiteboard.setdefault(k, v)
            self.whiteboard["scenario_pack"] = self.scenario_pack
            self.whiteboard["artifact_type"] = self.artifact_type
            if self.topic and (
                not self.whiteboard.get("topic_title")
                or _norm_dedupe_key(self.whiteboard.get("topic_title", "")) == _norm_dedupe_key(self.topic)
                and len(self.topic) > 28
            ):
                self.whiteboard["topic_title"] = short_topic_title
            _normalize_and_sync_whiteboard(self.whiteboard, topic=self.topic, messages=self.messages)
            self.whiteboard["executor_agent"] = self.effective_executor_agent()

    @property
    def is_busy(self) -> bool:
        return bool((self.active_task and not self.active_task.done()) or self.exec_state in ("preparing", "running"))

    @property
    def topic_locked(self) -> bool:
        return bool(self.stage != "idle" or len(self.messages) > 0)

    def has_exportable_content(self) -> bool:
        has_substantive_msg = any(
            isinstance(m, dict)
            and m.get("speaker") != "system"
            and not m.get("skipped")
            and not m.get("error")
            and str(m.get("content") or "").strip()
            for m in (self.messages or [])
        )
        if has_substantive_msg:
            return True
        wb_items = (self.whiteboard or {}).get("items") or []
        if any(isinstance(it, dict) and str(it.get("text") or "").strip() for it in wb_items):
            return True
        ab_items = (self.whiteboard or {}).get("abandoned_proposals") or []
        return any((isinstance(x, dict) and str(x.get("text") or "").strip()) or (isinstance(x, str) and x.strip()) for x in ab_items)

    def has_unacked_rollbackable(self) -> bool:
        return bool(self.last_backup is not None and self.last_backup.is_rollbackable)

    @property
    def is_solo(self) -> bool:
        return len(self.enabled_agents) == 1

    def effective_executor_agent(self) -> str:
        """
        动态解析执行席位：
        - 单席专注模式时，自动由该启用席位直接承接执行交付；
        - 多席参会时，优先使用显式选定的执行席位，否则优先选挂载「工程实现/全栈架构」职责的参会席位。
        """
        if len(self.enabled_agents) == 1:
            return self.enabled_agents[0]
        if self.executor_agent in self.enabled_agents:
            return self.executor_agent
        for aid in self.enabled_agents:
            if self.seat_personas.get(aid) in ("implementer", "fullstack_solo"):
                return aid
        if "astra" in self.enabled_agents:
            return "astra"
        return self.enabled_agents[0] if self.enabled_agents else "astra"

    def to_snapshot(self) -> dict:
        eff_exec = self.effective_executor_agent()
        self.whiteboard["executor_agent"] = eff_exec
        self.whiteboard["scenario_pack"] = self.scenario_pack
        self.whiteboard["artifact_type"] = self.artifact_type
        self.whiteboard["topic_locked"] = self.topic_locked
        self.whiteboard["can_rollback"] = self.has_unacked_rollbackable()
        self.whiteboard["recovery_required"] = bool(self.recovery_required)
        return {
            "session_id": self.session_id,
            "rev": int(self.rev),
            "exec_state": self.exec_state,
            "active_operation_id": self.active_operation_id,
            "active_run_id": self.active_run_id,
            "execution_started_at": self.execution_started_at,
            "recovery_required": bool(self.recovery_required),
            "title": self.title,
            "topic": self.topic,
            "topic_locked": self.topic_locked,
            "workspace_dir": self.workspace_dir,
            "workspace_bound": is_real_bound_workspace(self.workspace_dir)[0],
            "workspace_is_git": is_git_workspace(self.workspace_dir),
            "collab_mode": self.collab_mode,
            "collab_mode_label": COLLAB_MODES.get(self.collab_mode, {}).get("label", "深度研讨"),
            "scenario_pack": self.scenario_pack,
            "artifact_type": self.artifact_type,
            "auto_preview_exec": bool(self.auto_preview_exec),
            "stage": self.stage,
            "created_at": self.created_at,
            "is_busy": self.is_busy,
            "enabled_agents": list(self.enabled_agents),
            "seat_personas": dict(self.seat_personas),
            "seat_efforts": dict(self.seat_efforts),
            "executor_agent": eff_exec,
            "seat_states": self.seat_states,
            "messages": self.messages,
            "whiteboard": self.whiteboard,
        }

    def to_persisted_dict(self) -> dict:
        clean_msgs = []
        for m in self.messages[-500:]:
            mc = dict(m)
            sanitize_persisted_message(mc, fallback_badge="已中断")
            clean_msgs.append(mc)
        wb_copy = dict(self.whiteboard)
        wb_copy.pop("conflict", None)
        wb_copy.pop("conflict_message", None)
        wb_copy.pop("conflict_item", None)
        wb_copy.pop("_synthesis_dossier_block", None)
        wb_copy["can_rollback"] = False
        wb_copy["scenario_pack"] = self.scenario_pack
        wb_copy["artifact_type"] = self.artifact_type
        wb_copy["executor_agent"] = self.effective_executor_agent()
        if isinstance(wb_copy.get("exec_logs"), list) and len(wb_copy["exec_logs"]) > 300:
            wb_copy["exec_logs"] = wb_copy["exec_logs"][-300:]
        return {
            "session_id": self.session_id,
            "rev": int(self.rev),
            "title": self.title,
            "topic": self.topic,
            "workspace_dir": self.workspace_dir,
            "collab_mode": self.collab_mode,
            "scenario_pack": self.scenario_pack,
            "artifact_type": self.artifact_type,
            "auto_preview_exec": bool(self.auto_preview_exec),
            "stage": "awaiting_chair"
            if self.stage in ("opening_parallel", "cross_talk", "chair_interrupt", "executing")
            else self.stage,
            "created_at": self.created_at,
            "updated_ts": self.updated_ts,
            "enabled_agents": list(self.enabled_agents),
            "seat_personas": dict(self.seat_personas),
            "seat_efforts": dict(self.seat_efforts),
            "executor_agent": self.executor_agent,
            "messages": clean_msgs,
            "whiteboard": wb_copy,
        }


class RoundtableOrchestrator:
    SINGLE_CLI_SERIAL_BUFFER_SEC = 0.12
    SINGLE_CLI_PARALLEL_STAGGER_SEC = 0.08

    def _sync_agent_meta_names(self, inspected: Optional[Dict[str, dict]] = None) -> Dict[str, str]:
        """返回全局默认席位显示名映射（纯函数式返回，绝不覆写全局 AGENT_META 避免跨会话写污染）。"""
        status_map = inspected if inspected is not None else self.settings.inspect_status()
        resolved: Dict[str, str] = {}
        for aid in AGENT_ORDER:
            info = status_map.get(aid) or {}
            disp = str(info.get("name") or self.settings.resolve_seat_name(aid)).strip()
            resolved[aid] = disp
        return resolved

    def _seat_name(self, sess: Optional[MeetingSession], aid: str) -> str:
        """严格读取目标会话私有的席位显示名，彻底隔离并发多会话的角色与命名配置。"""
        if sess is not None:
            st = sess.seat_states.get(aid)
            if isinstance(st, dict) and str(st.get("name") or "").strip():
                return str(st["name"]).strip()
            p_key = sess.seat_personas.get(aid) or DEFAULT_SEAT_PERSONAS.get(aid, "planner")
            return self.settings.resolve_seat_name(aid, persona_key=p_key)
        return self.settings.resolve_seat_name(aid)

    def __init__(self, workspace_dir: str, *, boot_id: str = "", runtime_code_root: str = ""):
        self.data_dir = os.path.expanduser(os.environ.get("AI_ROUNDTABLE_HOME") or "~/.ai-roundtable")
        os.makedirs(self.data_dir, exist_ok=True)
        self.boot_id = boot_id or f"boot_{uuid.uuid4().hex[:12]}"
        self.runtime_code_root = os.path.realpath(runtime_code_root or str(Path(__file__).resolve().parent.parent))
        self.config_ver: int = 1
        self.config_file = os.path.join(self.data_dir, "config.json")
        self.sessions_file = os.path.join(self.data_dir, "sessions.json")
        self._persist_handle: Optional[asyncio.TimerHandle] = None
        self._last_driver_finish_ts: Dict[str, float] = {}
        self._workspace_write_locks: Dict[Path, asyncio.Lock] = {}
        self._turn_seq_counter: int = 0
        self._cleanup_stale_runtime_files()
        self.store = RoundtableSQLiteStore(os.path.join(self.data_dir, "state.sqlite3"))
        self.settings = RuntimeSettings.create_default(workspace_dir=workspace_dir)
        self._load_persisted_config()
        self.attachments = SessionAttachmentManager(self.data_dir)
        self.runner = UnifiedAgentRunner(self.settings)
        self.runner.attachments = self.attachments
        self.sessions: Dict[str, MeetingSession] = {}
        self._load_persisted_sessions()
        if not self.sessions:
            default_session = self.create_session(title="新会议", collab_mode="deep_deliberation")
            self.default_session_id = default_session.session_id
        else:
            self.default_session_id = list(self.sessions.keys())[-1]
        self._scan_crash_interrupted_backups()

    async def shutdown(self) -> None:
        try:
            await self.runner.shutdown()
        finally:
            self.store.close()

    def _scan_crash_interrupted_backups(self) -> None:
        """启动时扫描 ~/.ai-roundtable/backups/：凡处于 prepared/running 无 after 清单的快照转入 recovery_required，严禁静默删文件。"""
        backups_root = Path(self.data_dir) / "backups"
        if not backups_root.is_dir():
            return
        for manifest_p in sorted(backups_root.glob("*/*/manifest.json")):
            try:
                bk = WorkspaceBackup.load_from_manifest(manifest_p)
            except Exception:
                continue
            sess = self.sessions.get(bk.session_id)
            if not sess:
                continue
            if bk.state in ("prepared", "running") and bk.after_entries is None:
                sess.recovery_required = True
                sess.pending_recovery_backup = bk
                sess.whiteboard["recovery_required"] = True
                sess.whiteboard["consensus_status"] = "检测到上次执行异常中断，请核对文件哈希后恢复"
            elif bk.state == "rollbackable" and bk.is_rollbackable:
                if os.path.realpath(sess.workspace_dir or self.settings.workspace_dir) == bk.cwd:
                    sess.last_backup = bk
                    sess.whiteboard["can_rollback"] = True
                    sess.whiteboard["exec_diff"] = bk.worktree_diff

    def _normalize_agent_efforts(self) -> bool:
        changed = False
        for _, cfg in self.settings.agents.items():
            bpath, _, help_text, eff_drv, is_fb = cfg.get_probe_info(
                persist_cache=False,
                allow_single_cli_fallback=self.settings.allow_single_cli_fallback,
            )
            target_drv = eff_drv if bpath else cfg.preferred_driver_key()
            eff_model = resolve_effective_model_for_driver(
                target_drv,
                cfg.model,
                is_shared_fb=is_fb if bpath else False,
            )
            norm_disc = normalize_model_effort(
                target_drv,
                model=eff_model,
                effort=cfg.discussion_effort,
                help_text=help_text,
            )
            norm_exec = normalize_model_effort(
                target_drv,
                model=eff_model,
                effort=cfg.execution_effort or cfg.discussion_effort,
                help_text=help_text,
            )
            if cfg.discussion_effort != norm_disc:
                cfg.discussion_effort = norm_disc
                changed = True
            if cfg.execution_effort != norm_exec:
                cfg.execution_effort = norm_exec
                changed = True
        return changed

    def _cleanup_stale_runtime_files(self) -> None:
        try:
            if not os.path.isdir(self.data_dir):
                return
            now_ts = time.time()
            for tmp_f in glob.glob(os.path.join(self.data_dir, "*.tmp")):
                try:
                    if now_ts - os.path.getmtime(tmp_f) > 300:
                        os.remove(tmp_f)
                except Exception:
                    pass
        except Exception:
            pass

    def _load_persisted_config(self) -> None:
        try:
            if os.path.isfile(self.config_file):
                with open(self.config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                schema_ver = int(data.get("config_schema_version", 1) or 1)
                wdir = str(data.get("workspace_dir", "")).strip()
                if wdir:
                    exp_wdir = os.path.expanduser(wdir)
                    home_real = os.path.realpath(os.path.expanduser("~"))
                    if os.path.isdir(exp_wdir) and os.path.realpath(exp_wdir) != home_real:
                        self.settings.workspace_dir = exp_wdir
                if "allow_single_cli_fallback" in data:
                    self.settings.allow_single_cli_fallback = bool(data["allow_single_cli_fallback"])
                rp = str(data.get("roster_preset") or "").strip()
                if rp in VALID_ROSTER_PRESETS:
                    self.settings.roster_preset = rp
                if "single_cli_concurrency" in data:
                    try:
                        self.settings.single_cli_concurrency = max(1, min(4, int(data["single_cli_concurrency"])))
                    except Exception:
                        pass

                if schema_ver >= 8:
                    raw_pm = str(data.get("pacing_mode", "unrestricted") or "unrestricted").strip().lower()
                    self.settings.pacing_mode = (
                        raw_pm if raw_pm in ("unrestricted", "standard", "custom") else "unrestricted"
                    )
                    if "idle_timeout_sec" in data:
                        try:
                            raw_idle = int(data["idle_timeout_sec"])
                            min_idle = 1 if os.environ.get("AI_ROUNDTABLE_FAST_TEST") == "1" else 15
                            self.settings.idle_timeout_sec = DEFAULT_IDLE_TIMEOUT_SEC if raw_idle <= 0 else max(min_idle, min(7200, raw_idle))
                        except Exception:
                            pass
                    if "turn_timeout_sec" in data:
                        try:
                            raw_turn = int(data["turn_timeout_sec"])
                            self.settings.turn_timeout_sec = (
                                DEFAULT_TURN_TIMEOUT_SEC if raw_turn <= 0 else max(30, min(3600, raw_turn))
                            )
                        except Exception:
                            pass
                    if self.settings.idle_timeout_sec <= 0:
                        self.settings.idle_timeout_sec = DEFAULT_IDLE_TIMEOUT_SEC
                    if self.settings.turn_timeout_sec <= 0:
                        self.settings.turn_timeout_sec = DEFAULT_TURN_TIMEOUT_SEC
                    if "max_ref_chars" in data:
                        try:
                            self.settings.max_ref_chars = max(10000, min(500000, int(data["max_ref_chars"])))
                        except Exception:
                            pass
                else:
                    self.settings.pacing_mode = "standard"
                    self.settings.idle_timeout_sec = DEFAULT_IDLE_TIMEOUT_SEC
                    self.settings.turn_timeout_sec = DEFAULT_TURN_TIMEOUT_SEC
                    self.settings.max_ref_chars = MAX_ROUND_SOURCE_CHARS
                if "post_exec_verify_cmd" in data and isinstance(data["post_exec_verify_cmd"], str):
                    self.settings.post_exec_verify_cmd = data["post_exec_verify_cmd"].strip()[:500]
                if "single_cli_concurrency" in data:
                    try:
                        self.settings.single_cli_concurrency = max(1, min(6, int(data["single_cli_concurrency"])))
                    except Exception:
                        pass

                agents_cfg = data.get("agents", {})
                if isinstance(agents_cfg, dict):
                    for aid, acfg in agents_cfg.items():
                        if aid in self.settings.agents and isinstance(acfg, dict):
                            t = self.settings.agents[aid]
                            t.custom_name = str(acfg.get("custom_name", "")).strip()[:20]
                            t.custom_binary = str(acfg.get("custom_binary", "")).strip()
                            drv = str(acfg.get("driver", "")).strip()
                            if drv in VALID_DRIVERS:
                                t.driver = drv
                            p_key = str(acfg.get("persona", "")).strip()
                            if p_key in VALID_PERSONAS:
                                t.persona = p_key
                                t.title = PERSONA_PRESETS[p_key]["short_tag"]
                            if schema_ver >= 2:
                                t.model = str(acfg.get("model", "")).strip()
                                if "discussion_effort" in acfg:
                                    eff = str(acfg.get("discussion_effort", "")).strip().lower()
                                    if eff in VALID_EFFORT_LEVELS:
                                        t.discussion_effort = eff
                                if "execution_effort" in acfg:
                                    ex_eff = str(acfg.get("execution_effort", "")).strip().lower()
                                    if ex_eff in VALID_EFFORT_LEVELS:
                                        t.execution_effort = ex_eff
                                if "lock_discussion_effort" in acfg:
                                    t.lock_discussion_effort = bool(acfg.get("lock_discussion_effort"))
                normalized_changed = self._normalize_agent_efforts()
                self.settings.invalidate_status_cache()
                self._sync_agent_meta_names()
                if schema_ver < 9 or normalized_changed:
                    self._save_persisted_config()
        except Exception:
            pass

    def _save_persisted_config(self) -> None:
        try:
            os.makedirs(self.data_dir, exist_ok=True)
            payload = {
                "config_schema_version": 10,
                "workspace_dir": self.settings.workspace_dir,
                "allow_single_cli_fallback": self.settings.allow_single_cli_fallback,
                "roster_preset": self.settings.roster_preset,
                "single_cli_concurrency": self.settings.single_cli_concurrency,
                "pacing_mode": self.settings.pacing_mode,
                "idle_timeout_sec": self.settings.idle_timeout_sec,
                "turn_timeout_sec": self.settings.turn_timeout_sec,
                "max_ref_chars": self.settings.max_ref_chars,
                "post_exec_verify_cmd": self.settings.post_exec_verify_cmd,
                "agents": {
                    aid: {
                        "driver": cfg.driver,
                        "persona": cfg.persona,
                        "custom_name": cfg.custom_name,
                        "custom_binary": cfg.custom_binary,
                        "model": cfg.model,
                        "discussion_effort": cfg.discussion_effort,
                        "execution_effort": cfg.execution_effort,
                        "lock_discussion_effort": bool(cfg.lock_discussion_effort),
                    }
                    for aid, cfg in self.settings.agents.items()
                },
            }
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _default_personas_from_settings(self) -> Dict[str, str]:
        return {
            aid: (
                self.settings.agents[aid].persona
                if aid in self.settings.agents and self.settings.agents[aid].persona in PERSONA_PRESETS
                else DEFAULT_SEAT_PERSONAS[aid]
            )
            for aid in AGENT_ORDER
        }

    def _load_persisted_sessions(self) -> None:
        try:
            self.store.migrate_legacy_sessions_json_if_needed(Path(self.sessions_file))
            self.store.migrate_legacy_sessions_json_if_needed(Path(self.data_dir) / "data" / "sessions.json")
            raw_list = self.store.load_all_sessions(limit=50)
            if not raw_list and os.path.isfile(self.sessions_file):
                with open(self.sessions_file, "r", encoding="utf-8") as f:
                    raw_list = json.load(f)
            if not isinstance(raw_list, list) or not raw_list:
                return
            inspected = self.settings.inspect_status()
            self._sync_agent_meta_names(inspected=inspected)
            kept_empty_draft = False
            dirty_healed = False
            candidates_slice = [x for x in raw_list[-50:] if isinstance(x, dict) and x.get("session_id")]
            # 倒序检查空白会话：仅保留最新 1 个空白草稿，消除重复空白「新会议」导致的历史计数虚高
            allowed_empty_sid: Optional[str] = None
            for rev_it in reversed(candidates_slice):
                r_msgs = rev_it.get("messages") if isinstance(rev_it.get("messages"), list) else []
                if _empty_session_draft(rev_it.get("topic"), r_msgs, rev_it.get("whiteboard")):
                    if allowed_empty_sid is None:
                        allowed_empty_sid = str(rev_it["session_id"])
                    else:
                        dirty_healed = True

            for item in candidates_slice:
                try:
                    msgs = item.get("messages") if isinstance(item.get("messages"), list) else []
                    upd_ts = float(item.get("updated_ts") or time.time())
                    sid = str(item["session_id"])
                    if _empty_session_draft(item.get("topic"), msgs, item.get("whiteboard")):
                        if sid != allowed_empty_sid or kept_empty_draft:
                            dirty_healed = True
                            continue
                        kept_empty_draft = True

                    for m_chk in msgs:
                        if isinstance(m_chk, dict) and (
                            m_chk.get("streaming")
                            or str(m_chk.get("badge") or "") in STALE_STREAMING_BADGES
                        ):
                            dirty_healed = True

                    raw_mode = str(item.get("collab_mode", "deep_deliberation"))
                    raw_auto_exec = item.get("auto_preview_exec")
                    norm_mode, norm_auto_exec = normalize_collab_mode(
                        raw_mode,
                        auto_preview_exec=bool(raw_auto_exec) if raw_auto_exec is not None else None,
                    )
                    sess_ws = str(item.get("workspace_dir") or "").strip()
                    if sess_ws and not os.path.isdir(sess_ws):
                        sess_ws = ""
                    raw_personas = item.get("seat_personas")
                    personas = (
                        dict(raw_personas)
                        if isinstance(raw_personas, dict)
                        else self._default_personas_from_settings()
                    )
                    raw_efforts = item.get("seat_efforts")
                    seat_efforts = dict(raw_efforts) if isinstance(raw_efforts, dict) else {}
                    exec_ag = str(item.get("executor_agent") or "astra").strip().lower()
                    raw_wb_dict = item.get("whiteboard") if isinstance(item.get("whiteboard"), dict) else {}
                    raw_pack = str(item.get("scenario_pack") or raw_wb_dict.get("scenario_pack") or "")
                    raw_art = str(item.get("artifact_type") or raw_wb_dict.get("artifact_type") or "")
                    sess = MeetingSession(
                        session_id=sid,
                        title=str(item.get("title") or "新会议"),
                        topic=str(item.get("topic") or ""),
                        workspace_dir=sess_ws if "workspace_dir" in item else self.settings.workspace_dir,
                        collab_mode=norm_mode,
                        scenario_pack=raw_pack,
                        artifact_type=raw_art,
                        auto_preview_exec=norm_auto_exec,
                        stage=str(item.get("stage") or "idle"),
                        created_at=str(item.get("created_at") or now_display_time()),
                        updated_ts=upd_ts,
                        enabled_agents=item.get("enabled_agents") or list(DEFAULT_ENABLED_AGENTS),
                        rev=int(item.get("rev") or 0),
                        seat_personas=personas,
                        seat_efforts=seat_efforts,
                        executor_agent=exec_ag if exec_ag in AGENT_ORDER else "astra",
                        messages=msgs,
                        whiteboard=raw_wb_dict,
                    )
                    if sess.topic and sess.whiteboard.get("topic_title"):
                        sess.title = sess.whiteboard["topic_title"]
                    if sess.stage == "awaiting_chair" and sess.whiteboard.get("consensus_status", "").startswith("第 "):
                        sess.whiteboard["consensus_status"] = "待主持人继续推进"
                    self._sync_seat_readiness(sess, inspected=inspected)
                    self.sessions[sid] = sess
                except Exception:
                    dirty_healed = True
                    continue
            if dirty_healed:
                self._flush_persisted_sessions_sync()
        except Exception:
            pass

    def _persist_single_session(
        self,
        sess: MeetingSession,
        *,
        single_msg_idx: Optional[int] = None,
        rewrite_all_messages: bool = False,
        immediate: bool = False,
    ) -> None:
        pdict = sess.to_persisted_dict()
        single_pair: Optional[Tuple[int, dict]] = None
        if single_msg_idx is not None and 0 <= single_msg_idx < len(pdict["messages"]):
            single_pair = (single_msg_idx, pdict["messages"][single_msg_idx])
        self.store.upsert_session_incremental(
            pdict,
            single_msg_seq_and_obj=single_pair,
            rewrite_all_messages=rewrite_all_messages,
            wait=immediate,
        )

    def _flush_persisted_sessions_sync(self, wait: bool = False) -> None:
        try:
            for s in list(self.sessions.values())[-50:]:
                self.store.upsert_session_incremental(s.to_persisted_dict(), rewrite_all_messages=True, wait=False)
            if wait:
                self.store.flush()
        except Exception:
            pass

    def _save_persisted_sessions(self, immediate: bool = False) -> None:
        if immediate:
            if self._persist_handle:
                self._persist_handle.cancel()
                self._persist_handle = None
            self._flush_persisted_sessions_sync(wait=True)
            return
        try:
            loop = asyncio.get_running_loop()
            if self._persist_handle is None:
                def _checkpoint():
                    self._persist_handle = None
                    self._flush_persisted_sessions_sync(wait=False)
                # P1.1：常规状态抖动按检查点合并落库，msg_done 与阶段切换直接触发增量单写线程事务
                self._persist_handle = loop.call_later(0.5, _checkpoint)
        except RuntimeError:
            self._flush_persisted_sessions_sync(wait=False)

    def create_session(
        self,
        title: str = "新会议",
        collab_mode: str = "deep_deliberation",
        auto_preview_exec: Optional[bool] = None,
        scenario_pack: Optional[str] = None,
        artifact_type: Optional[str] = None,
    ) -> MeetingSession:
        norm_title = title.strip() or "新会议"
        pack_spec = SCENARIO_INTENT_PACKS.get(str(scenario_pack or "").strip().lower()) if scenario_pack else None
        eff_mode_arg = pack_spec["collab_mode"] if pack_spec and not collab_mode else collab_mode
        norm_mode, norm_auto_exec = normalize_collab_mode(eff_mode_arg, auto_preview_exec=auto_preview_exec)
        prev_sess = self.sessions.get(self.default_session_id) if getattr(self, "default_session_id", None) else None
        norm_pack, norm_art = normalize_scenario_pack_and_artifact(
            scenario_pack or (prev_sess.scenario_pack if prev_sess else "arch_code"),
            artifact_type or (pack_spec["artifact_type"] if pack_spec else (prev_sess.artifact_type if prev_sess else "code_patch")),
        )
        if norm_title == "新会议":
            for ex_s in reversed(list(self.sessions.values())):
                if (
                    ex_s.title == "新会议" and not ex_s.is_busy
                    and _empty_session_draft(ex_s.topic, ex_s.messages, ex_s.whiteboard)
                ):
                    ex_s.collab_mode = norm_mode
                    ex_s.auto_preview_exec = norm_auto_exec
                    ex_s.scenario_pack = norm_pack
                    ex_s.artifact_type = norm_art
                    ex_s.whiteboard["scenario_pack"] = norm_pack
                    ex_s.whiteboard["artifact_type"] = norm_art
                    if pack_spec:
                        ex_s.enabled_agents = [a for a in AGENT_ORDER if a in pack_spec["enabled_agents"]]
                        for a_k, p_v in pack_spec["seat_personas"].items():
                            if a_k in AGENT_ORDER and p_v in VALID_PERSONAS:
                                ex_s.seat_personas[a_k] = p_v
                    ex_s.updated_ts = time.time()
                    self._sync_seat_readiness(ex_s)
                    self.default_session_id = ex_s.session_id
                    self._save_persisted_sessions()
                    return ex_s
        sid = f"s_{uuid.uuid4().hex[:8]}"
        init_enabled = (
            [a for a in AGENT_ORDER if a in pack_spec["enabled_agents"]]
            if pack_spec
            else (list(prev_sess.enabled_agents) if prev_sess else list(DEFAULT_ENABLED_AGENTS))
        )
        init_personas = dict(prev_sess.seat_personas) if prev_sess else self._default_personas_from_settings()
        if pack_spec:
            for a_k, p_v in pack_spec["seat_personas"].items():
                if a_k in AGENT_ORDER and p_v in VALID_PERSONAS:
                    init_personas[a_k] = p_v
        init_efforts = dict(prev_sess.seat_efforts) if prev_sess else {}
        init_exec = prev_sess.executor_agent if prev_sess else "astra"
        init_ws = "" if (pack_spec and pack_spec.get("prefer_unbound_workspace")) else self.settings.workspace_dir

        sess = MeetingSession(
            session_id=sid,
            title=title.strip() or "新会议",
            workspace_dir=init_ws,
            collab_mode=norm_mode,
            scenario_pack=norm_pack,
            artifact_type=norm_art,
            auto_preview_exec=norm_auto_exec,
            enabled_agents=init_enabled,
            seat_personas=init_personas,
            seat_efforts=init_efforts,
            executor_agent=init_exec,
        )
        self._sync_seat_readiness(sess)
        self.sessions[sid] = sess
        self.default_session_id = sid
        self._save_persisted_sessions()
        return sess

    async def delete_session(self, session_id: str) -> Optional[str]:
        sess = self.sessions.get(session_id)
        if not sess:
            return None
        await self.cancel_active_flow(sess, reason_tag="会话已删除", persist=False)
        await self.runner.reset_session_context(session_id)
        del self.sessions[session_id]
        self.attachments.delete_session_attachments(session_id)
        self.store.delete_session(session_id, wait=True)
        if not self.sessions:
            fresh = self.create_session(title="新会议", collab_mode="deep_deliberation")
            self.default_session_id = fresh.session_id
        elif self.default_session_id == session_id:
            self.default_session_id = list(self.sessions.keys())[-1]
        self._save_persisted_sessions(immediate=True)
        return self.default_session_id

    def _refresh_epistemic_status(self, sess: MeetingSession, status_map: Optional[Dict[str, dict]] = None) -> dict:
        smap = status_map if status_map is not None else self.settings.inspect_status()
        active_fams = compute_effective_driver_families(sess.round_driver_records)
        cfg_fams: Set[str] = set()
        for aid in sess.enabled_agents:
            inf = smap.get(aid) or {}
            if inf.get("binary_detected"):
                fk = normalize_driver_family_key(str(inf.get("effective_driver") or ""), str(inf.get("binary_path") or ""))
                if fk and fk != "driver:unknown":
                    cfg_fams.add(fk)
        epi = compute_epistemic_status(
            enabled_seat_count=len(sess.enabled_agents),
            active_driver_families=active_fams,
            configured_driver_families=cfg_fams,
        )
        sess.whiteboard["epistemic_mode"] = epi["mode"]
        sess.whiteboard["epistemic_badge"] = epi["badge"]
        sess.whiteboard["epistemic_short_badge"] = epi["short_badge"]
        sess.whiteboard["driver_family_count"] = epi["driver_family_count"]
        return epi

    def _sync_seat_readiness(self, sess: MeetingSession, inspected: Optional[Dict[str, dict]] = None) -> None:
        status_map = inspected if inspected is not None else self.settings.inspect_status()
        self._sync_agent_meta_names(inspected=status_map)

        enabled_fam_counts: Dict[str, int] = {}
        for en_aid in sess.enabled_agents:
            en_info = status_map.get(en_aid) or {}
            if en_info.get("binary_detected"):
                efk = normalize_driver_family_key(
                    str(en_info.get("effective_driver") or ""),
                    str(en_info.get("binary_path") or ""),
                )
                enabled_fam_counts[efk] = enabled_fam_counts.get(efk, 0) + 1

        for aid, st in sess.seat_states.items():
            info = status_map.get(aid)
            enabled = aid in sess.enabled_agents
            p_key = sess.seat_personas.get(aid) or DEFAULT_SEAT_PERSONAS[aid]
            pspec = get_persona_spec(p_key, fallback_agent_id=aid)
            disp_name = self.settings.resolve_seat_name(
                aid,
                eff_drv=(info or {}).get("effective_driver", ""),
                eff_model=(info or {}).get("effective_model", ""),
                persona_key=pspec["key"],
            )
            st["name"] = disp_name
            st["enabled"] = enabled
            st["persona"] = pspec["key"]
            st["persona_label"] = pspec["label"]
            st["title"] = pspec["short_tag"]
            st["wb_kind"] = pspec["wb_kind"]
            st["wb_title"] = pspec["wb_title"]
            st["cue_btn"] = pspec["cue_btn"].format(name=disp_name)
            st["cue_prompt"] = pspec["cue_prompt"]
            if info:
                b_ready = bool(info.get("binary_detected"))
                eff_drv = str(info.get("effective_driver") or "")
                b_path = str(info.get("binary_path") or "")
                fam_key = normalize_driver_family_key(eff_drv, b_path) if b_ready else normalize_driver_family_key(eff_drv, "")
                is_shared_in_session = bool(info.get("shared_fallback")) or (
                    b_ready and enabled and len(sess.enabled_agents) > 1 and enabled_fam_counts.get(fam_key, 0) > 1
                )
                prov_name = str(info.get("provider_name") or DRIVER_PROVIDER_LABELS.get(eff_drv, ("Custom", ""))[0])
                is_het_seat = b_ready and enabled and len(sess.enabled_agents) > 1 and not is_shared_in_session
                if not b_ready:
                    indep_lbl = "未就绪"
                elif len(sess.enabled_agents) <= 1 and enabled:
                    indep_lbl = "单席专注"
                elif is_shared_in_session:
                    indep_lbl = "同源复用"
                else:
                    indep_lbl = "异构独立"

                st["binary_ready"] = b_ready
                st["shared_fallback"] = bool(info.get("shared_fallback"))
                st["shared_cli_group"] = is_shared_in_session
                st["effective_driver"] = eff_drv
                st["provider_name"] = prov_name
                st["driver_family_key"] = fam_key
                st["is_heterogeneous"] = is_het_seat
                st["independence_label"] = indep_lbl
                st["effective_model"] = info.get("effective_model", "")
                sess_eff_override = sess.seat_efforts.get(aid, "")
                if sess_eff_override:
                    cfg_obj = self.settings.agents.get(aid)
                    help_t = ""
                    if cfg_obj:
                        _, _, help_t, _, _ = cfg_obj.get_probe_info(
                            persist_cache=False,
                            allow_single_cli_fallback=self.settings.allow_single_cli_fallback,
                        )
                    st["effective_effort"] = normalize_model_effort(
                        eff_drv or "agy",
                        model=info.get("effective_model") or "",
                        effort=sess_eff_override,
                        help_text=help_t,
                        strict=True,
                    )
                else:
                    st["effective_effort"] = info.get("effective_discussion_effort", "")
                if info.get("cli_name"):
                    st["cli_label"] = info["cli_name"]
                if st["status"] == "idle":
                    if not enabled:
                        st["badge"] = "已暂停参会"
                    elif b_ready:
                        st["badge"] = "已就绪"
                    else:
                        st["badge"] = "未检测到 CLI"
        sess.whiteboard["executor_agent"] = sess.effective_executor_agent()
        sess.whiteboard["scenario_pack"] = sess.scenario_pack
        sess.whiteboard["artifact_type"] = sess.artifact_type
        self._refresh_epistemic_status(sess, status_map=status_map)

    def list_sessions(self) -> List[dict]:
        return [
            {
                "session_id": s.session_id,
                "title": s.title,
                "topic": s.topic,
                "topic_locked": s.topic_locked,
                "workspace_dir": s.workspace_dir,
                "workspace_is_git": is_git_workspace(s.workspace_dir),
                "collab_mode": s.collab_mode,
                "collab_mode_label": COLLAB_MODES.get(s.collab_mode, {}).get("label", "深度研讨"),
                "scenario_pack": s.scenario_pack,
                "artifact_type": s.artifact_type,
                "auto_preview_exec": bool(s.auto_preview_exec),
                "stage": s.stage,
                "is_busy": s.is_busy,
                "enabled_agents": list(s.enabled_agents),
                "seat_personas": dict(s.seat_personas),
                "executor_agent": s.effective_executor_agent(),
                "consensus_status": s.whiteboard.get("consensus_status", "待输入议题"),
                "created_at": s.created_at,
                "message_count": len(s.messages),
            }
            for s in reversed(list(self.sessions.values()))
        ]

    def get_session(self, session_id: str) -> Optional[MeetingSession]:
        return self.sessions.get(session_id)

    def has_any_busy_session(self) -> bool:
        return any(s.is_busy for s in self.sessions.values())

    def search_workspace_files(self, session_id: str = "", query: str = "", limit: int = 200) -> dict:
        sess = self.sessions.get(session_id) if session_id else None
        raw_ws = (sess.workspace_dir if sess and sess.workspace_dir else self.settings.workspace_dir) or ""
        return list_workspace_files(raw_ws, query=query, limit=limit)

    async def search_workspace_files_async(self, session_id: str = "", query: str = "", limit: int = 200) -> dict:
        sess = self.sessions.get(session_id) if session_id else None
        raw_ws = (sess.workspace_dir if sess and sess.workspace_dir else self.settings.workspace_dir) or ""
        return await list_workspace_files_async(raw_ws, query=query, limit=limit)

    def validate_safe_workspace_path(self, raw_path: str, *, allow_default_sandbox: bool = False) -> Tuple[bool, str]:
        """校验目标工作区路径存在且绝不落入 ~/.ai-roundtable 私有状态目录或任何 .app 包资源目录。"""
        cleaned = str(raw_path or "").strip()
        if not cleaned:
            return False, "工作区路径不能为空"
        expanded = os.path.expanduser(cleaned)
        if not os.path.isdir(expanded):
            return False, f"目标目录不存在：{expanded}"
        real_target = Path(os.path.realpath(expanded))
        data_root = Path(os.path.realpath(self.data_dir))
        default_sb = (data_root / "workspace").resolve()
        if allow_default_sandbox and real_target == default_sb:
            return True, str(real_target)
        if real_target == data_root or real_target.is_relative_to(data_root):
            return False, "禁止将 ~/.ai-roundtable 内部状态目录绑定为项目工作区"
        for part in real_target.parts:
            if part.endswith(".app"):
                return False, "禁止将 macOS .app 应用包内部资源目录绑定为项目工作区"
        return True, str(real_target)

    def update_default_workspace_only(self, new_default_ws: str) -> dict:
        """pick-folder 弹窗专用：仅更新新建会话默认目录（及尚未发起议题的空闲草稿），绝不篡改已有会话。"""
        real_ws = os.path.realpath(os.path.expanduser(new_default_ws.strip()))
        self.settings.workspace_dir = real_ws
        self.config_ver += 1
        for s in self.sessions.values():
            if not s.is_busy and s.stage == "idle" and _empty_session_draft(s.topic, s.messages, s.whiteboard):
                s.workspace_dir = real_ws
        self._save_persisted_config()
        return self.get_system_status()

    async def switch_session_workspace(self, sess: MeetingSession, target_ws: str) -> Tuple[int, dict]:
        """POST /api/sessions/{sid}/workspace 唯一入口：支持绑定安全本地目录或切回纯研讨（target_ws=""）。"""
        cleaned_target = str(target_ws or "").strip()
        if cleaned_target == "":
            real_ws = ""
        else:
            ok_p, res_or_err = self.validate_safe_workspace_path(cleaned_target, allow_default_sandbox=False)
            if not ok_p:
                return 400, {"ok": False, "error": res_or_err}
            real_ws = res_or_err
        async with sess.session_lock:
            if sess.is_busy or sess.exec_state != "idle" or sess.stage in (
                "opening_parallel",
                "cross_talk",
                "chair_interrupt",
                "executing",
            ):
                return 409, {"ok": False, "error": "会话当前正在运行中，请待空闲后再切换绑定工作区"}
            if sess.recovery_required:
                return 409, {"ok": False, "error": "当前会话存在待确认恢复的崩溃快照，请先处理恢复后再切换工作区"}
            old_real = os.path.realpath(sess.workspace_dir) if sess.workspace_dir else ""
            if old_real != real_ws:
                if sess.last_backup and sess.last_backup.is_rollbackable:
                    sess.last_backup.mark_acknowledged()
                sess.last_backup = None
                sess.whiteboard["can_rollback"] = False
                sess.whiteboard["exec_diff"] = ""
            sess.workspace_dir = real_ws
            sess.updated_ts = time.time()
        if real_ws:
            invalidate_workspace_index(real_ws)
        await self._broadcast_meta(sess)
        await self.broadcast(sess, "whiteboard_update", sess.whiteboard)
        self._persist_single_session(sess, immediate=True)
        return 200, {
            "ok": True,
            "workspace_dir": real_ws,
            "workspace_bound": is_real_bound_workspace(real_ws)[0],
            "workspace_is_git": is_git_workspace(real_ws),
            "session": sess.to_snapshot(),
        }

    def update_runtime_config(self, payload: dict, active_session_id: str = "") -> dict:
        self.config_ver += 1
        if "workspace_dir" in payload and isinstance(payload["workspace_dir"], str):
            wdir = os.path.expanduser(payload["workspace_dir"].strip())
            if wdir:
                self.settings.workspace_dir = wdir
                for sid, s in self.sessions.items():
                    if sid == active_session_id or not s.topic:
                        if os.path.realpath(s.workspace_dir) != os.path.realpath(wdir):
                            s.last_backup = None
                            s.whiteboard["can_rollback"] = False
                        s.workspace_dir = wdir
        if "allow_single_cli_fallback" in payload:
            self.settings.allow_single_cli_fallback = bool(payload["allow_single_cli_fallback"])
        if "roster_preset" in payload:
            rp = str(payload.get("roster_preset") or "").strip()
            if rp in VALID_ROSTER_PRESETS:
                self.settings.roster_preset = rp
        if "single_cli_concurrency" in payload:
            try:
                self.settings.single_cli_concurrency = max(1, min(6, int(payload["single_cli_concurrency"])))
            except Exception:
                pass
        if "post_exec_verify_cmd" in payload and isinstance(payload["post_exec_verify_cmd"], str):
            self.settings.post_exec_verify_cmd = payload["post_exec_verify_cmd"].strip()[:500]

        pm = str(payload.get("pacing_mode") or "").strip().lower()
        if pm in ("unrestricted", "extended", "standard", "custom"):
            self.settings.pacing_mode = "extended" if pm == "unrestricted" else pm
            if pm in ("unrestricted", "extended") and "idle_timeout_sec" not in payload and "turn_timeout_sec" not in payload:
                self.settings.idle_timeout_sec = 600
                self.settings.turn_timeout_sec = 1200
            elif pm == "standard" and "idle_timeout_sec" not in payload and "turn_timeout_sec" not in payload:
                self.settings.idle_timeout_sec = 300
                self.settings.turn_timeout_sec = 600

        if "idle_timeout_sec" in payload:
            try:
                raw_idle = int(payload["idle_timeout_sec"])
                min_idle = 1 if os.environ.get("AI_ROUNDTABLE_FAST_TEST") == "1" else 15
                self.settings.idle_timeout_sec = DEFAULT_IDLE_TIMEOUT_SEC if raw_idle <= 0 else max(min_idle, min(7200, raw_idle))
            except Exception:
                pass
        if "turn_timeout_sec" in payload:
            try:
                raw_turn = int(payload["turn_timeout_sec"])
                min_turn = 2 if os.environ.get("AI_ROUNDTABLE_FAST_TEST") == "1" else 30
                self.settings.turn_timeout_sec = DEFAULT_TURN_TIMEOUT_SEC if raw_turn <= 0 else max(min_turn, min(14400, raw_turn))
            except Exception:
                pass
        if pm == "unrestricted" and payload.get("pacing_mode") == "unrestricted":
            if payload.get("idle_timeout_sec") is None:
                self.settings.idle_timeout_sec = 900
            if payload.get("turn_timeout_sec") is None:
                self.settings.turn_timeout_sec = DEFAULT_TURN_TIMEOUT_SEC
        elif pm == "standard" and payload.get("pacing_mode") == "standard":
            if payload.get("idle_timeout_sec") is None:
                self.settings.idle_timeout_sec = 300
            if payload.get("turn_timeout_sec") is None:
                self.settings.turn_timeout_sec = 600

        if "max_ref_chars" in payload:
            try:
                self.settings.max_ref_chars = max(10000, min(500000, int(payload["max_ref_chars"])))
            except Exception:
                pass

        updated_personas: Dict[str, str] = {}
        updated_efforts: set = set()
        if "agents" in payload and isinstance(payload["agents"], dict):
            for aid, acfg in payload["agents"].items():
                if aid in self.settings.agents and isinstance(acfg, dict):
                    target = self.settings.agents[aid]
                    if "driver" in acfg and acfg["driver"] in VALID_DRIVERS:
                        target.driver = acfg["driver"]
                        target._cached_probe_path = ""
                        updated_efforts.add(aid)
                    if "persona" in acfg and acfg["persona"] in VALID_PERSONAS:
                        target.persona = acfg["persona"]
                        target.title = PERSONA_PRESETS[target.persona]["short_tag"]
                        updated_personas[aid] = target.persona
                    if "custom_name" in acfg:
                        target.custom_name = str(acfg.get("custom_name") or "").strip()[:20]
                    if "custom_binary" in acfg:
                        target.custom_binary = str(acfg["custom_binary"]).strip()
                        target._cached_probe_path = ""
                    if "model" in acfg:
                        target.model = str(acfg["model"]).strip()
                        updated_efforts.add(aid)
                    if "discussion_effort" in acfg:
                        raw_de = str(acfg.get("discussion_effort") or "").strip().lower()
                        if raw_de in VALID_EFFORT_LEVELS:
                            target.discussion_effort = raw_de
                            updated_efforts.add(aid)
                    if "execution_effort" in acfg:
                        raw_ee = str(acfg.get("execution_effort") or "").strip().lower()
                        if raw_ee in VALID_EFFORT_LEVELS:
                            target.execution_effort = raw_ee
                    if "lock_discussion_effort" in acfg:
                        target.lock_discussion_effort = bool(acfg.get("lock_discussion_effort"))
        self.settings.invalidate_status_cache()
        self._normalize_agent_efforts()
        self.settings.invalidate_status_cache()
        self._save_persisted_config()
        inspected = self.settings.inspect_status(force_refresh=True)
        for sid, sess in self.sessions.items():
            if updated_personas and (sid == active_session_id or not sess.topic):
                for aid, p_key in updated_personas.items():
                    sess.seat_personas[aid] = p_key
            if updated_efforts and (sid == active_session_id or not sess.topic):
                for aid in updated_efforts:
                    sess.seat_efforts.pop(aid, None)
            self._sync_seat_readiness(sess, inspected=inspected)
        self._save_persisted_sessions()
        return {
            "workspace_dir": self.settings.workspace_dir,
            "workspace_bound": is_real_bound_workspace(self.settings.workspace_dir)[0],
            "workspace_is_git": is_git_workspace(self.settings.workspace_dir),
            "allow_single_cli_fallback": self.settings.allow_single_cli_fallback,
            "roster_preset": self.settings.roster_preset,
            "roster_presets": ROSTER_NAME_PRESETS,
            "single_cli_concurrency": self.settings.single_cli_concurrency,
            "pacing_mode": self.settings.pacing_mode,
            "idle_timeout_sec": self.settings.idle_timeout_sec,
            "turn_timeout_sec": self.settings.turn_timeout_sec,
            "max_ref_chars": self.settings.max_ref_chars,
            "has_busy_session": self.has_any_busy_session(),
            "collab_modes": COLLAB_MODES,
            "persona_presets": PERSONA_PRESETS,
            "model_effort_catalog": export_model_effort_catalog(),
            "agents": inspected,
        }

    async def update_session_seats(
        self,
        sess: MeetingSession,
        enabled_agents: Optional[List[str]] = None,
        seat_personas: Optional[Dict[str, str]] = None,
        executor_agent: Optional[str] = None,
        seat_efforts: Optional[Dict[str, str]] = None,
        collab_mode: Optional[str] = None,
        auto_preview_exec: Optional[bool] = None,
        scenario_pack: Optional[str] = None,
        artifact_type: Optional[str] = None,
        recommend_heterogeneous: bool = False,
    ) -> dict:
        if sess.is_busy or sess.exec_state != "idle" or sess.stage in ("opening_parallel", "cross_talk", "chair_interrupt", "executing"):
            raise ExecutionAdmissionConflictError(
                "会议正在运行或执行中，禁止中途切换场景预设或参会席位阵容",
                status_code=409,
                details={"reason": "session_busy"},
            )

        pack_spec = SCENARIO_INTENT_PACKS.get(str(scenario_pack or "").strip().lower()) if scenario_pack else None
        if pack_spec is not None:
            if enabled_agents is None:
                enabled_agents = list(pack_spec["enabled_agents"])
            if seat_personas is None:
                seat_personas = dict(pack_spec["seat_personas"])
            if collab_mode is None:
                collab_mode = pack_spec["collab_mode"]
            if artifact_type is None:
                artifact_type = pack_spec["artifact_type"]

        if scenario_pack is not None or artifact_type is not None:
            sess.scenario_pack, sess.artifact_type = normalize_scenario_pack_and_artifact(
                scenario_pack if scenario_pack is not None else sess.scenario_pack,
                artifact_type if artifact_type is not None else sess.artifact_type,
            )
            sess.whiteboard["scenario_pack"] = sess.scenario_pack
            sess.whiteboard["artifact_type"] = sess.artifact_type

        if enabled_agents is not None:
            valid = [aid for aid in AGENT_ORDER if aid in enabled_agents]
            if not valid:
                raise ValueError("至少需要保留一位参会席位")
            sess.enabled_agents = valid
            if len(valid) == 1:
                sess.executor_agent = valid[0]
            elif sess.executor_agent not in valid:
                sess.executor_agent = "astra" if "astra" in valid else valid[0]

        if recommend_heterogeneous:
            avail = self.settings.detect_available_drivers()
            if len(avail) >= 2:
                for idx_h, aid_h in enumerate(sess.enabled_agents):
                    chosen_drv = avail[idx_h % len(avail)]["driver"]
                    if aid_h in self.settings.agents:
                        self.settings.agents[aid_h].driver = chosen_drv
                        self.settings.agents[aid_h].model = DRIVER_SPECS[chosen_drv]["default_model"]
                        self.settings.agents[aid_h].discussion_effort = normalize_model_effort(
                            chosen_drv,
                            model=self.settings.agents[aid_h].model,
                            effort=self.settings.agents[aid_h].discussion_effort,
                        )
                self.settings.invalidate_status_cache()
                self._save_persisted_config()

        if isinstance(seat_personas, dict):
            config_changed = False
            for aid, p_key in seat_personas.items():
                if aid in AGENT_ORDER and p_key in VALID_PERSONAS:
                    sess.seat_personas[aid] = p_key
                    if aid in self.settings.agents and self.settings.agents[aid].persona != p_key:
                        self.settings.agents[aid].persona = p_key
                        self.settings.agents[aid].title = PERSONA_PRESETS[p_key]["short_tag"]
                        config_changed = True
            if config_changed:
                self._save_persisted_config()

        if isinstance(seat_efforts, dict):
            for aid, eff_val in seat_efforts.items():
                if aid not in AGENT_ORDER:
                    continue
                eff_clean = str(eff_val or "").strip().lower()
                if not eff_clean:
                    sess.seat_efforts.pop(aid, None)
                elif eff_clean in VALID_EFFORT_LEVELS:
                    sess.seat_efforts[aid] = eff_clean

        if collab_mode is not None:
            norm_m, inferred_auto = normalize_collab_mode(collab_mode, auto_preview_exec=auto_preview_exec)
            sess.collab_mode = norm_m
            if collab_mode == "arch_to_exec" and auto_preview_exec is None:
                sess.auto_preview_exec = inferred_auto

        if auto_preview_exec is not None:
            sess.auto_preview_exec = bool(auto_preview_exec)

        if executor_agent and executor_agent in AGENT_ORDER:
            sess.executor_agent = executor_agent
            if len(sess.enabled_agents) == 1 and executor_agent != sess.enabled_agents[0] and enabled_agents is None:
                sess.enabled_agents = [a for a in AGENT_ORDER if a in (sess.enabled_agents[0], executor_agent)]

        sess.updated_ts = time.time()
        self._sync_seat_readiness(sess)
        for st in sess.seat_states.values():
            await self.broadcast(sess, "seat_update", st)
        await self.broadcast(sess, "whiteboard_update", sess.whiteboard)
        await self._broadcast_meta(sess)
        self._save_persisted_sessions()
        return {
            "rev": sess.rev,
            "enabled_agents": list(sess.enabled_agents),
            "seat_personas": dict(sess.seat_personas),
            "seat_efforts": dict(sess.seat_efforts),
            "collab_mode": sess.collab_mode,
            "collab_mode_label": COLLAB_MODES.get(sess.collab_mode, {}).get("label", "深度研讨"),
            "scenario_pack": sess.scenario_pack,
            "artifact_type": sess.artifact_type,
            "epistemic_mode": sess.whiteboard.get("epistemic_mode", ""),
            "epistemic_badge": sess.whiteboard.get("epistemic_badge", ""),
            "auto_preview_exec": bool(sess.auto_preview_exec),
            "executor_agent": sess.effective_executor_agent(),
            "seat_states": sess.seat_states,
        }

    @classmethod
    def _extract_resolution_bundle(cls, markdown_text: str) -> Tuple[List[dict], List[dict]]:
        """
        从《会议最终决议》正文中精准分离两类产物：
        1) active_entries: 已确认采纳成果（decision）、边界风险（risk）、待执行交付任务（action），上限放宽至 60 条防长文截断遗漏；
        2) abandoned_entries: 第二节『已确认放弃与证伪淘汰方案』及 [白板: 弃案=...] 中的负面清单，100% 物理隔离防回流！
        """
        if not markdown_text:
            return [], []
        active_entries: List[dict] = []
        abandoned_entries: List[dict] = []
        seen_active_norms: Set[str] = set()
        seen_abandoned_norms: Set[str] = set()

        def _push_abandoned(raw_t: str, reason_s: str = "决议确认淘汰") -> None:
            t_clean = cls._smart_clip(raw_t.strip(), limit=220)
            nk = _norm_dedupe_key(t_clean)
            if not nk or len(t_clean) < 4 or nk in seen_abandoned_norms:
                return
            seen_abandoned_norms.add(nk)
            abandoned_entries.append({"text": t_clean, "reason": reason_s})

        def _push_active(k_str: str, raw_t: str) -> None:
            t_clean = cls._smart_clip(raw_t.strip(), limit=220)
            nk = _norm_dedupe_key(t_clean)
            if not nk or len(t_clean) < 5 or is_whiteboard_noise(t_clean):
                return
            if nk in seen_abandoned_norms or nk in seen_active_norms:
                return
            seen_active_norms.add(nk)
            active_entries.append({"kind": k_str if k_str in VALID_WB_KINDS else "decision", "text": t_clean})

        _, tail_items = parse_structured_tail_with_kinds(markdown_text)
        for ti in tail_items:
            tk = str(ti.get("kind") or "decision").strip().lower()
            tt = str(ti.get("text") or "").strip()
            if not tt:
                continue
            if tk == "abandoned":
                _push_abandoned(tt, "决议结构化弃案标记")
            else:
                _push_active(tk, tt)

        cleaned = re.sub(r"\[(?:状态|徽章|白板|白板要点)[:：][^\]]*\]", "", markdown_text)
        cleaned = re.sub(r"```[\s\S]*?```", "", cleaned)

        cur_kind = "decision"
        for raw_ln in cleaned.splitlines():
            ln = raw_ln.strip()
            if not ln:
                continue
            m_head = re.match(r"^(?:#{1,4}\s*|\*\*|[一二三四五六1-6][、.)）]\s*)(.+?)(?:\*\*)?[:：]?\s*$", ln)
            if m_head and len(ln) <= 68 and not re.match(r"^[-*•]\s+", ln):
                htxt = m_head.group(1)
                if any(k in htxt for k in ("放弃", "弃案", "淘汰", "证伪", "废案", "负面清单", "不采用", "否决", "剔除")):
                    cur_kind = "abandoned"
                elif any(k in htxt for k in ("风险", "防线", "边界", "回滚", "异常", "隐患", "审计", "未决争议", "缺席")):
                    cur_kind = "risk"
                elif any(k in htxt for k in ("实施", "任务", "清单", "执行", "改动", "步骤", "文件", "落地", "走查", "矩阵", "排查", "定稿")):
                    cur_kind = "action"
                elif any(k in htxt for k in ("共识", "结论", "裁定", "取舍", "约束", "架构", "决议", "采纳", "成果")):
                    cur_kind = "decision"
                continue

            m_b = re.match(r"^(?:[-*•]+|\d+[.)、]|[①②③④⑤⑥⑦⑧⑨⑩])\s*(?:\[[xX ]\]\s*)?(.+)$", ln)
            if not m_b:
                continue
            item_txt = re.sub(r"\*\*([^*]+)\*\*", r"\1", m_b.group(1)).strip()
            item_txt = re.sub(r"`([^`]+)`", r"\1", item_txt).strip()
            if len(item_txt) < 5 or is_whiteboard_noise(item_txt):
                continue
            if item_txt in ("暂无记录", "暂无", "无", "（无）", "（暂无已确认放弃方案）"):
                continue
            inferred_kind = cur_kind
            if any(item_txt.startswith(pfx) for pfx in ("[已淘汰]", "[放弃]", "[弃案]", "弃案：", "淘汰：", "放弃方案：", "不采用：")):
                inferred_kind = "abandoned"
            elif inferred_kind != "abandoned":
                if any(item_txt.startswith(pfx) for pfx in ("风险：", "风险:", "隐患：", "防线：", "边界：")):
                    inferred_kind = "risk"
                elif any(item_txt.startswith(pfx) for pfx in ("任务：", "任务:", "修改 ", "新增 ", "重构 ", "走查：", "排查：")):
                    inferred_kind = "action"

            if inferred_kind == "abandoned":
                clean_ab = re.sub(r"^(?:\[已淘汰\]|\[放弃\]|\[弃案\]|弃案[:：]|淘汰[:：]|放弃方案[:：]|不采用[:：])\s*", "", item_txt).strip()
                _push_abandoned(clean_ab or item_txt, "决议确认放弃与证伪淘汰")
            else:
                _push_active(inferred_kind, item_txt)
            if len(active_entries) >= 60:
                break

        if seen_abandoned_norms:
            active_entries = [e for e in active_entries if _norm_dedupe_key(e["text"]) not in seen_abandoned_norms]
        return active_entries, abandoned_entries

    @classmethod
    def _extract_items_from_resolution(cls, markdown_text: str) -> List[dict]:
        """向后兼容提取入口：返回已剥离全部弃案后的有效白板条目列表。"""
        active_entries, _ = cls._extract_resolution_bundle(markdown_text)
        return active_entries

    def _has_heterogeneous_rebuttal_closure(self, sess: MeetingSession, item: Optional[dict] = None) -> bool:
        """
        核验是否满足『异构多引擎质询闭环』（Section 1.2 三级来源准入）：
        1) 会话实际成功驱动族 >= 2；
        2) 已至少完成过 1 轮交叉质询 / 定向答辩 / 反向压力审计 / 综合裁定 / 焦点再辩（或条目自身已标记 rebutted=True）。
        """
        if not self._can_session_auto_promote_decision(sess):
            return False
        if isinstance(item, dict) and item.get("rebutted"):
            return True
        closure_phases = {
            "交叉质询", "定向答辩", "反向审计", "防御修正", "综合裁定",
            "架构裁定", "矩阵评估", "优选收敛", "调用链核验", "修改方案", "焦点再辩",
        }
        return any(
            isinstance(m, dict)
            and not m.get("error")
            and not m.get("skipped")
            and str(m.get("phase_label") or "") in closure_phases
            and str(m.get("content") or "").strip()
            for m in sess.messages
        )

    def _record_abandoned_proposal(
        self,
        sess: MeetingSession,
        text: str,
        *,
        author: str = "system",
        reason: str = "讨论中证伪淘汰",
        round_phase: str = "",
        source_msg_id: str = "",
    ) -> bool:
        """记录已确认放弃或证伪淘汰的差方案，并自动清理白板中同内容的未置顶临时建议，防止回流。"""
        clean_t = self._smart_clip(re.sub(r"^[-*•\s]+", "", str(text or "").strip()), limit=220)
        nk = _norm_dedupe_key(clean_t)
        if not nk or len(clean_t) < 4:
            return False
        ab_list: List[dict] = sess.whiteboard.setdefault("abandoned_proposals", [])
        for ex in ab_list:
            if isinstance(ex, dict) and _norm_dedupe_key(str(ex.get("text") or "")) == nk:
                if source_msg_id and not ex.get("source_msg_id"):
                    ex["source_msg_id"] = source_msg_id
                return False
        seat_disp = "主持人" if author == "chair" else (self._seat_name(sess, author) if author in AGENT_META else "会议决议")
        ab_list.append(
            {
                "id": f"ab_{hashlib.sha1(nk.encode('utf-8')).hexdigest()[:8]}",
                "text": clean_t,
                "author": author,
                "seat_name": seat_disp,
                "reason": reason,
                "round_phase": round_phase,
                "source_msg_id": source_msg_id,
                "timestamp": now_hhmmss(),
            }
        )
        wb_items = sess.whiteboard.get("items")
        if isinstance(wb_items, list):
            sess.whiteboard["items"] = [
                it for it in wb_items
                if not (
                    isinstance(it, dict)
                    and not it.get("pinned")
                    and it.get("author") != "chair"
                    and it.get("origin_tier") != "chair_directive"
                    and _norm_dedupe_key(str(it.get("text") or "")) == nk
                )
            ]
        return True

    async def update_whiteboard_manual(self, sess: MeetingSession, payload: dict) -> dict:
        wb = _normalize_and_sync_whiteboard(sess.whiteboard, topic=sess.topic, messages=sess.messages)
        wb.pop("conflict", None)
        wb.pop("conflict_message", None)
        wb.pop("conflict_item", None)
        sess.updated_ts = time.time()

        mutated = False
        if "topic" in payload and isinstance(payload["topic"], str):
            clean_t = payload["topic"].strip()
            if clean_t and clean_t != sess.topic:
                if sess.topic_locked:
                    raise ExecutionAdmissionConflictError(
                        "会议启动后原始议题已锁定只读，严禁中途篡改；请通过底部追问或新增『主持指定约束』补充诉求",
                        status_code=409,
                        details={"reason": "topic_locked", "topic": sess.topic},
                    )
                short_t, _ = summarize_topic_and_constraints(clean_t)
                sess.topic = clean_t
                sess.title = short_t or (clean_t[:24] + ("…" if len(clean_t) > 24 else ""))
                wb["topic"] = clean_t
                wb["topic_title"] = short_t
                mutated = True

        items: List[dict] = wb.setdefault("items", [])

        if "chair_constraints" in payload and isinstance(payload["chair_constraints"], list):
            new_constraints = dedupe_chair_constraints(
                sess.topic,
                wb.get("topic_title", ""),
                [str(x).strip() for x in payload["chair_constraints"] if str(x).strip()],
            )
            kept_others = [
                it for it in items if not (isinstance(it, dict) and it.get("kind") == "decision" and it.get("author") == "chair")
            ]
            rebuilt_chair = [
                {
                    "id": make_deterministic_wb_id("chair_constraints", idx_c, c_txt),
                    "kind": "decision",
                    "text": c_txt,
                    "author": "chair",
                    "origin_tier": "chair_directive",
                    "source_msg_id": "",
                    "pinned": True,
                    "checked": True,
                    "ver": 1,
                }
                for idx_c, c_txt in enumerate(new_constraints)
            ]
            wb["items"] = rebuilt_chair + kept_others
            items = wb["items"]
            mutated = True

        op = str(payload.get("op") or "").strip()
        bucket_key = str(payload.get("bucket") or "").strip()
        raw_kind_param = str(payload.get("kind") or "").strip().lower()
        item_id = str(payload.get("item_id") or payload.get("id") or "").strip()
        expected_version = payload.get("ver", payload.get("expected_version"))

        def _find_item_idx(target_id: str) -> int:
            for idx_i, it_i in enumerate(items):
                if isinstance(it_i, dict) and it_i.get("id") == target_id:
                    return idx_i
            return -1

        def _resolve_target_kind(default_kind: str = "decision") -> str:
            if raw_kind_param in VALID_WB_KINDS:
                return raw_kind_param
            return {
                "chair_constraints": "decision",
                "consensus": "decision",
                "decision": "decision",
                "carbon_plan": "decision",
                "grok_risks": "risk",
                "risk": "risk",
                "astra_actions": "action",
                "action": "action",
            }.get(bucket_key, default_kind)

        if op == "acknowledge_absent":
            for ab_s in wb.get("absent_seats") or []:
                if isinstance(ab_s, dict) and not ab_s.get("acknowledged"):
                    ab_s["acknowledged"] = True
                    mutated = True

        elif op == "remove_abandoned":
            ab_id = str(payload.get("abandoned_id") or item_id or "").strip()
            before_len = len(wb.get("abandoned_proposals") or [])
            wb["abandoned_proposals"] = [
                x for x in (wb.get("abandoned_proposals") or [])
                if not (isinstance(x, dict) and x.get("id") == ab_id)
            ]
            if len(wb["abandoned_proposals"]) != before_len:
                mutated = True

        elif item_id and op in (
            "toggle_pin",
            "toggle_check",
            "adopt_decision",
            "promote_decision",
            "toggle_adopt",
            "abandon_item",
            "update",
            "remove",
        ):
            found_idx = _find_item_idx(item_id)
            if found_idx < 0:
                return {
                    **wb,
                    "conflict": True,
                    "conflict_message": "该白板条目已被并发更新或移除，草稿已为您保留",
                }
            target_item = items[found_idx]
            cur_ver = int(target_item.get("ver") or 1)
            if op in ("update", "remove") and expected_version is not None:
                try:
                    if int(expected_version) != cur_ver:
                        return {
                            **wb,
                            "conflict": True,
                            "conflict_item": dict(target_item),
                            "conflict_message": "该条目刚刚被并发修改，请核对最新内容后再保存",
                        }
                except (TypeError, ValueError):
                    pass

            if op == "toggle_pin":
                target_item["pinned"] = (
                    bool(payload["pinned"]) if "pinned" in payload else (not bool(target_item.get("pinned")))
                )
                target_item["ver"] = cur_ver + 1
                mutated = True
            elif op == "toggle_check":
                target_item["checked"] = (
                    bool(payload["checked"]) if "checked" in payload else (not bool(target_item.get("checked", False)))
                )
                target_item["ver"] = cur_ver + 1
                mutated = True
            elif op == "abandon_item":
                popped = items.pop(found_idx)
                self._record_abandoned_proposal(
                    sess,
                    str(popped.get("text") or ""),
                    author="chair",
                    reason=str(payload.get("reason") or "主持人显式标记放弃"),
                    round_phase="人工控场",
                    source_msg_id=str(popped.get("source_msg_id") or ""),
                )
                mutated = True
            elif op in ("adopt_decision", "promote_decision", "toggle_adopt"):
                if op == "toggle_adopt" and payload.get("adopted") is False:
                    target_item["kind"] = "risk"
                    target_item["origin_tier"] = "provisional_suggestion"
                    target_item.pop("adopted_by", None)
                    target_item.pop("adopted_at", None)
                else:
                    as_chair_dir = bool(payload.get("as_chair_directive") or payload.get("origin_tier") == "chair_directive")
                    verified_closure = self._has_heterogeneous_rebuttal_closure(sess, target_item)
                    if verified_closure and not as_chair_dir:
                        target_item["kind"] = "decision"
                        target_item["origin_tier"] = "multi_seat_consensus"
                        target_item.pop("provisional_decision", None)
                    elif as_chair_dir:
                        target_item["kind"] = "decision"
                        target_item["origin_tier"] = "chair_directive"
                        target_item["adopted_by"] = "chair"
                        target_item["adopted_at"] = now_display_time()
                        target_item["pinned"] = bool(payload.get("pinned", True))
                        target_item.pop("provisional_decision", None)
                    else:
                        raise ExecutionAdmissionConflictError(
                            "该条目尚未完成异构多引擎质询闭环，禁止直接升格为『多源交叉共识』；若需由主持人直接拍板锁定，请以『[主持指定约束]（chair_directive）』方式采纳",
                            status_code=409,
                            details={
                                "reason": "unverified_consensus_adoption",
                                "item_id": item_id,
                                "epistemic_badge": wb.get("epistemic_badge", ""),
                            },
                        )
                    if "pinned" in payload:
                        target_item["pinned"] = bool(payload["pinned"])
                target_item["ver"] = cur_ver + 1
                mutated = True
            elif op == "update":
                txt = str(payload.get("text") or "").strip()
                if txt:
                    target_item["text"] = txt
                    if raw_kind_param in VALID_WB_KINDS:
                        if raw_kind_param == "decision" and target_item.get("kind") != "decision":
                            if self._has_heterogeneous_rebuttal_closure(sess, target_item):
                                target_item["origin_tier"] = "multi_seat_consensus"
                            else:
                                target_item["origin_tier"] = "chair_directive"
                                target_item["adopted_by"] = "chair"
                                target_item["adopted_at"] = now_display_time()
                        target_item["kind"] = raw_kind_param
                    target_item["ver"] = cur_ver + 1
                else:
                    items.pop(found_idx)
                mutated = True
            elif op == "remove":
                items.pop(found_idx)
                mutated = True

        elif op == "add":
            txt = str(payload.get("text") or "").strip()
            if txt:
                src_author = str(payload.get("author") or payload.get("source_seat") or "").strip().lower()
                if src_author not in VALID_WB_AUTHORS:
                    src_author = {
                        "chair_constraints": "chair",
                        "carbon_plan": "carbon",
                        "grok_risks": "grok",
                        "astra_actions": "astra",
                    }.get(bucket_key, "chair")
                default_k = (
                    get_persona_spec(sess.seat_personas.get(src_author, ""), src_author)["wb_kind"]
                    if src_author in AGENT_ORDER
                    else "decision"
                )
                eff_kind = _resolve_target_kind(default_kind=default_k)
                src_msg_id = str(payload.get("source_msg_id") or "").strip()
                default_pin = bucket_key in ("chair_constraints", "consensus") or (
                    src_author == "chair" and eff_kind == "decision"
                )
                is_pinned = bool(payload.get("pinned", default_pin))
                if "checked" in payload:
                    is_checked = bool(payload["checked"])
                else:
                    is_checked = False if eff_kind == "action" else True

                if eff_kind == "decision":
                    if src_author == "chair" or not self._has_heterogeneous_rebuttal_closure(sess):
                        origin_tier = "chair_directive"
                    else:
                        origin_tier = "multi_seat_consensus"
                else:
                    origin_tier = "chair_directive" if src_author == "chair" else "provisional_suggestion"

                norm_new = _norm_dedupe_key(txt)
                matched_existing: Optional[dict] = None
                for ex in items:
                    if isinstance(ex, dict) and _norm_dedupe_key(str(ex.get("text") or "")) == norm_new:
                        matched_existing = ex
                        break
                if matched_existing is not None:
                    if eff_kind == "decision" and matched_existing.get("kind") != "decision":
                        matched_existing["kind"] = "decision"
                        matched_existing["origin_tier"] = origin_tier
                        if origin_tier == "chair_directive":
                            matched_existing["adopted_by"] = "chair"
                            matched_existing["adopted_at"] = now_display_time()
                    if is_pinned:
                        matched_existing["pinned"] = True
                    if src_msg_id and not matched_existing.get("source_msg_id"):
                        matched_existing["source_msg_id"] = src_msg_id
                    matched_existing["ver"] = int(matched_existing.get("ver") or 1) + 1
                    mutated = True
                else:
                    ordinal = int(wb.get("wb_version") or 1) + len(items) + 1
                    new_id = make_deterministic_wb_id(f"{eff_kind}_{src_author}", ordinal, txt)
                    new_obj: dict = {
                        "id": new_id,
                        "kind": eff_kind,
                        "text": txt,
                        "author": src_author,
                        "origin_tier": origin_tier,
                        "source_msg_id": src_msg_id,
                        "pinned": is_pinned,
                        "checked": is_checked,
                        "ver": 1,
                    }
                    if origin_tier == "chair_directive":
                        new_obj["adopted_by"] = "chair"
                        new_obj["adopted_at"] = now_display_time()
                    items.append(new_obj)
                    mutated = True

        elif op == "import_resolution":
            req_msg_id = str(payload.get("message_id") or "").strip()
            res_msg: Optional[dict] = None
            if req_msg_id:
                for m in reversed(sess.messages):
                    if m.get("id") == req_msg_id:
                        res_msg = m
                        break
            if res_msg is None:
                for m in reversed(sess.messages):
                    if m.get("phase_label") in ("最终决议", "决议", "架构裁定", "综合裁定", "优选收敛", "修改方案", "合议清单") and m.get("content"):
                        res_msg = m
                        break
            if res_msg and res_msg.get("content"):
                res_author = str(res_msg.get("speaker") or "system").lower()
                if res_author not in VALID_WB_AUTHORS:
                    res_author = "system"
                res_mid = str(res_msg.get("id") or "")
                parsed_entries, abandoned_entries = self._extract_resolution_bundle(str(res_msg.get("content") or ""))
                for ab_e in abandoned_entries:
                    if self._record_abandoned_proposal(
                        sess,
                        ab_e["text"],
                        author=res_author,
                        reason=ab_e.get("reason", "决议确认淘汰"),
                        round_phase=str(res_msg.get("phase_label") or "最终决议"),
                        source_msg_id=res_mid,
                    ):
                        mutated = True
                items = wb.setdefault("items", [])
                abandoned_norms = {
                    _norm_dedupe_key(str(x.get("text") or ""))
                    for x in (wb.get("abandoned_proposals") or [])
                    if isinstance(x, dict)
                }
                existing_norms = {
                    _norm_dedupe_key(str(it.get("text") or "")): it
                    for it in items
                    if isinstance(it, dict)
                }
                allow_auto_dec = self._has_heterogeneous_rebuttal_closure(sess)
                for entry in parsed_entries:
                    etxt = entry["text"]
                    ekind = entry["kind"]
                    enk = _norm_dedupe_key(etxt)
                    if not enk or enk in abandoned_norms:
                        continue
                    was_prov = False
                    if ekind == "decision" and not allow_auto_dec:
                        ekind = "risk"
                        was_prov = True
                    if enk in existing_norms:
                        ex_it = existing_norms[enk]
                        if ekind == "decision" and ex_it.get("kind") != "decision":
                            ex_it["kind"] = "decision"
                            ex_it["origin_tier"] = "multi_seat_consensus"
                            ex_it.pop("provisional_decision", None)
                            ex_it["ver"] = int(ex_it.get("ver") or 1) + 1
                            mutated = True
                        if res_mid and not ex_it.get("source_msg_id"):
                            ex_it["source_msg_id"] = res_mid
                            mutated = True
                        continue
                    ordinal = int(wb.get("wb_version") or 1) + len(items) + 1
                    new_it: dict = {
                        "id": make_deterministic_wb_id(f"{ekind}_{res_author}", ordinal, etxt),
                        "kind": ekind,
                        "text": etxt,
                        "author": res_author,
                        "origin_tier": "multi_seat_consensus" if ekind == "decision" else "provisional_suggestion",
                        "source_msg_id": res_mid,
                        "pinned": False,
                        "checked": False if ekind == "action" else True,
                        "ver": 1,
                    }
                    if was_prov:
                        new_it["provisional_decision"] = True
                    items.append(new_it)
                    existing_norms[enk] = new_it
                    mutated = True

        elif op == "dedupe_clean":
            cleaned_list: List[dict] = []
            for it in items:
                if not isinstance(it, dict):
                    continue
                txt = str(it.get("text") or "").strip()
                if not txt:
                    continue
                if not it.get("pinned") and it.get("author") != "chair" and is_whiteboard_noise(txt):
                    mutated = True
                    continue
                nk = _norm_dedupe_key(txt)
                if not nk:
                    mutated = True
                    continue
                merged = False
                for prev in cleaned_list:
                    pk = _norm_dedupe_key(str(prev.get("text") or ""))
                    same_or_overlap = nk == pk or (
                        prev.get("kind") == it.get("kind")
                        and min(len(nk), len(pk)) >= 14
                        and (nk in pk or pk in nk)
                    )
                    if same_or_overlap:
                        if it.get("pinned") and not prev.get("pinned"):
                            prev["pinned"] = True
                        if it.get("kind") == "decision" and prev.get("kind") != "decision":
                            prev["kind"] = "decision"
                            if it.get("origin_tier") in VALID_ORIGIN_TIERS:
                                prev["origin_tier"] = it["origin_tier"]
                        if len(txt) > len(str(prev.get("text") or "")) and not prev.get("pinned"):
                            prev["text"] = txt
                        if it.get("source_msg_id") and not prev.get("source_msg_id"):
                            prev["source_msg_id"] = it["source_msg_id"]
                        prev["ver"] = int(prev.get("ver") or 1) + 1
                        merged = True
                        mutated = True
                        break
                if not merged:
                    cleaned_list.append(it)
            wb["items"] = cleaned_list
            items = wb["items"]

        elif bucket_key in WHITEBOARD_LIST_KEYS and op in ("remove", "update"):
            idx = payload.get("index")
            expected_txt = payload.get("expected_text")
            if bucket_key == "chair_constraints":
                bucket_items = [
                    it for it in items if isinstance(it, dict) and it.get("kind") == "decision" and it.get("author") == "chair"
                ]
            elif bucket_key == "carbon_plan":
                bucket_items = [
                    it for it in items if isinstance(it, dict) and it.get("kind") == "decision" and it.get("author") != "chair"
                ]
            elif bucket_key == "grok_risks":
                bucket_items = [it for it in items if isinstance(it, dict) and it.get("kind") == "risk"]
            else:
                bucket_items = [it for it in items if isinstance(it, dict) and it.get("kind") == "action"]

            if isinstance(idx, int) and 0 <= idx < len(bucket_items):
                target_it = bucket_items[idx]
                if expected_txt is not None and str(expected_txt).strip() != str(target_it.get("text") or "").strip():
                    return {
                        **wb,
                        "conflict": True,
                        "conflict_message": "白板列表刚刚发生变化，请确认位置后重试",
                    }
                real_idx = _find_item_idx(target_it["id"])
                if real_idx >= 0:
                    if op == "remove":
                        items.pop(real_idx)
                    else:
                        txt = str(payload.get("text") or "").strip()
                        if txt:
                            items[real_idx]["text"] = txt
                            items[real_idx]["ver"] = int(items[real_idx].get("ver") or 1) + 1
                        else:
                            items.pop(real_idx)
                    mutated = True

        sync_whiteboard_legacy_arrays_and_caps(wb)
        if mutated:
            wb["wb_version"] = int(wb.get("wb_version") or 1) + 1
        await self.broadcast(sess, "whiteboard_update", wb)
        await self._broadcast_meta(sess)
        self._save_persisted_sessions()
        return wb

    def get_system_status(self) -> dict:
        avail_drvs = self.settings.detect_available_drivers()
        return {
            "boot_id": self.boot_id,
            "runtime_code_root": self.runtime_code_root,
            "sqlite_journal_mode": self.store.journal_mode_active,
            "workspace_dir": self.settings.workspace_dir,
            "workspace_bound": is_real_bound_workspace(self.settings.workspace_dir)[0],
            "workspace_is_git": is_git_workspace(self.settings.workspace_dir),
            "allow_single_cli_fallback": self.settings.allow_single_cli_fallback,
            "roster_preset": self.settings.roster_preset,
            "roster_presets": ROSTER_NAME_PRESETS,
            "scenario_packs": SCENARIO_INTENT_PACKS,
            "artifact_types": list(VALID_ARTIFACT_TYPES),
            "scenario_lineups": SCENARIO_LINEUP_TEMPLATES,
            "seat_catalog": IMMUTABLE_SEAT_CATALOG,
            "all_seat_ids": list(ALL_SEAT_IDS),
            "available_drivers": avail_drvs,
            "can_recommend_heterogeneous": len(avail_drvs) >= 2,
            "single_cli_concurrency": self.settings.single_cli_concurrency,
            "pacing_mode": self.settings.pacing_mode,
            "idle_timeout_sec": self.settings.idle_timeout_sec,
            "turn_timeout_sec": self.settings.turn_timeout_sec,
            "max_ref_chars": self.settings.max_ref_chars,
            "post_exec_verify_cmd": self.settings.post_exec_verify_cmd,
            "has_busy_session": self.has_any_busy_session(),
            "collab_modes": COLLAB_MODES,
            "persona_presets": PERSONA_PRESETS,
            "model_effort_catalog": export_model_effort_catalog(),
            "agents": self.settings.inspect_status(),
        }

    async def run_cli_connectivity_test(
        self,
        override_agents: Optional[Dict[str, dict]] = None,
        target_agent_id: str = "",
    ) -> Dict[str, dict]:
        overrides = override_agents if isinstance(override_agents, dict) else {}
        if target_agent_id in AGENT_ORDER:
            candidates = [target_agent_id]
        elif overrides:
            candidates = [a for a in AGENT_ORDER if a in overrides] or list(DEFAULT_ENABLED_AGENTS)
        else:
            active_union = set(DEFAULT_ENABLED_AGENTS)
            for s in self.sessions.values():
                active_union.update(s.enabled_agents)
            candidates = [a for a in AGENT_ORDER if a in active_union]

        cli_conc = max(1, min(6, int(getattr(self.settings, "single_cli_concurrency", 3) or 3)))
        groups: Dict[str, List[str]] = {}
        for aid in candidates:
            ov = overrides.get(aid) if isinstance(overrides.get(aid), dict) else None
            try:
                _, bpath, _, eff_drv, _ = self.runner._require_binary(aid, override=ov)
                gkey = os.path.realpath(bpath) if bpath and os.path.lexists(bpath) else (bpath or eff_drv)
            except Exception:
                gkey = f"missing_{aid}"
            groups.setdefault(gkey, []).append(aid)

        results_map: Dict[str, dict] = {}

        async def _run_ping_group(gkey: str, group_aids: List[str]) -> None:
            if gkey.startswith("missing_") or cli_conc > 1:
                sem = asyncio.Semaphore(cli_conc)
                async def _ping_one(idx_p: int, a_id: str) -> None:
                    if idx_p > 0 and not gkey.startswith("missing_"):
                        await asyncio.sleep(0.06 * idx_p)
                    async with sem:
                        ov = overrides.get(a_id) if isinstance(overrides.get(a_id), dict) else None
                        results_map[a_id] = await self.runner.ping_agent(a_id, override=ov)
                await asyncio.gather(*(_ping_one(i, a) for i, a in enumerate(group_aids)))
            else:
                for idx, aid in enumerate(group_aids):
                    if idx > 0:
                        await asyncio.sleep(self.SINGLE_CLI_SERIAL_BUFFER_SEC)
                    ov = overrides.get(aid) if isinstance(overrides.get(aid), dict) else None
                    results_map[aid] = await self.runner.ping_agent(aid, override=ov)

        await asyncio.gather(*(_run_ping_group(gk, gaids) for gk, gaids in groups.items()))
        return {aid: results_map[aid] for aid in candidates if aid in results_map}

    def _commit_sse_event_sync(self, sess: MeetingSession, event_type: str, data: dict) -> bytes:
        """原子同步提交器（Section 二.3）：单调递增 rev、挂载 boot_id 与环形增量缓冲并向所有订阅队列投递。"""
        sess.rev = int(sess.rev or 0) + 1
        cur_rev = sess.rev
        enriched = dict(data) if isinstance(data, dict) else {"value": data}
        enriched["rev"] = cur_rev
        enriched["boot_id"] = self.boot_id
        enriched["session_id"] = sess.session_id
        payload = json.dumps(enriched, ensure_ascii=False)
        packet = f"id: {cur_rev}\nevent: {event_type}\ndata: {payload}\n\n".encode("utf-8")
        sess.event_ring.append((cur_rev, packet))
        for q in list(sess.subscribers):
            try:
                q.put_nowait(packet)
            except asyncio.QueueFull:
                if q in sess.subscribers:
                    sess.subscribers.remove(q)
                while not q.empty():
                    try:
                        q.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                try:
                    q.put_nowait(None)
                except asyncio.QueueFull:
                    pass
        return packet

    def subscribe_session_sse(self, sess: MeetingSession, *, since_rev: int = 0) -> Tuple[asyncio.Queue, List[bytes]]:
        """注册 SSE 订阅：若客户端携带的 since_rev 在环形缓冲内则原地补发全部缺失增量包，否则下发带当前 rev 的快照。"""
        q: asyncio.Queue = asyncio.Queue(maxsize=1024)
        initial: List[bytes] = []
        if since_rev > 0 and since_rev == sess.rev:
            # 客户端已完全对齐最新 rev，发送轻量 sync_ack 保持原地 DOM 状态
            ack = json.dumps(
                {
                    "rev": sess.rev,
                    "boot_id": self.boot_id,
                    "session_id": sess.session_id,
                    "execution_started_at": sess.execution_started_at,
                    "exec_state": sess.exec_state,
                    "is_busy": sess.is_busy,
                },
                ensure_ascii=False,
            )
            initial.append(f"id: {sess.rev}\nevent: sync_ack\ndata: {ack}\n\n".encode("utf-8"))
        elif since_rev > 0 and sess.event_ring and sess.event_ring[0][0] <= (since_rev + 1) and since_rev < sess.rev:
            for ev_rev, pkt in sess.event_ring:
                if ev_rev > since_rev:
                    initial.append(pkt)
        else:
            snap = sess.to_snapshot()
            snap["boot_id"] = self.boot_id
            snap["rev"] = sess.rev
            snap_json = json.dumps(snap, ensure_ascii=False)
            initial.append(f"id: {sess.rev}\nevent: snapshot\ndata: {snap_json}\n\n".encode("utf-8"))
        sess.subscribers.append(q)
        return q, initial

    def unsubscribe_session_sse(self, sess: MeetingSession, q: asyncio.Queue) -> None:
        if q in sess.subscribers:
            sess.subscribers.remove(q)

    async def broadcast(self, sess: MeetingSession, event_type: str, data: dict) -> None:
        self._commit_sse_event_sync(sess, event_type, data)

    async def _broadcast_meta(self, sess: MeetingSession) -> None:
        eff_exec = sess.effective_executor_agent()
        sess.whiteboard["executor_agent"] = eff_exec
        sess.whiteboard["scenario_pack"] = sess.scenario_pack
        sess.whiteboard["artifact_type"] = sess.artifact_type
        sess.whiteboard["topic_locked"] = sess.topic_locked
        self._refresh_epistemic_status(sess)
        eff_ws = sess.workspace_dir if sess.workspace_dir != "" else ""
        await self.broadcast(
            sess,
            "session_meta",
            {
                "stage": sess.stage,
                "exec_state": sess.exec_state,
                "active_operation_id": sess.active_operation_id,
                "active_run_id": sess.active_run_id,
                "execution_started_at": sess.execution_started_at,
                "recovery_required": bool(sess.recovery_required),
                "title": sess.title,
                "topic": sess.topic,
                "topic_locked": sess.topic_locked,
                "workspace_dir": sess.workspace_dir,
                "workspace_bound": is_real_bound_workspace(eff_ws)[0],
                "workspace_is_git": is_git_workspace(eff_ws),
                "collab_mode": sess.collab_mode,
                "collab_mode_label": COLLAB_MODES.get(sess.collab_mode, {}).get("label", "深度研讨"),
                "scenario_pack": sess.scenario_pack,
                "artifact_type": sess.artifact_type,
                "epistemic_mode": sess.whiteboard.get("epistemic_mode", ""),
                "epistemic_badge": sess.whiteboard.get("epistemic_badge", ""),
                "auto_preview_exec": bool(sess.auto_preview_exec),
                "is_busy": sess.is_busy,
                "enabled_agents": list(sess.enabled_agents),
                "seat_personas": dict(sess.seat_personas),
                "seat_efforts": dict(sess.seat_efforts),
                "executor_agent": eff_exec,
                "consensus_status": sess.whiteboard.get("consensus_status", ""),
            },
        )

    def validate_message_file_references(self, sess: MeetingSession, text: str) -> List[str]:
        eff_ws = sess.workspace_dir if sess.workspace_dir != "" else ""
        return validate_referenced_files_snapshot(eff_ws, text)

    def _record_absent_seat(
        self,
        sess: MeetingSession,
        agent_id: str,
        *,
        reason: str,
        error_kind: str = "",
        phase: str = "",
        abnormal: bool = True,
    ) -> None:
        """记录未参评或异常中断的启用席位至显式缺席账本（Section 1.2 缺席留痕硬约束）。"""
        if agent_id not in sess.enabled_agents:
            return
        ab_list: List[dict] = sess.whiteboard.setdefault("absent_seats", [])
        sname = self._seat_name(sess, agent_id)
        entry = {
            "agent_id": agent_id,
            "seat_name": sname,
            "reason": reason,
            "error_kind": error_kind,
            "phase": phase or sess.stage,
            "abnormal": bool(abnormal),
            "acknowledged": False,
            "timestamp": now_hhmmss(),
        }
        for idx_a, ex in enumerate(ab_list):
            if isinstance(ex, dict) and ex.get("agent_id") == agent_id:
                ab_list[idx_a] = entry
                return
        ab_list.append(entry)

    def _clear_absent_seat(self, sess: MeetingSession, agent_id: str) -> None:
        ab_list = sess.whiteboard.get("absent_seats")
        if isinstance(ab_list, list):
            sess.whiteboard["absent_seats"] = [
                x for x in ab_list if not (isinstance(x, dict) and x.get("agent_id") == agent_id)
            ]

    async def skip_agent_turn(self, sess: MeetingSession, agent_id: str) -> dict:
        """非阻塞跳过单席当前思考回合，不中断同批次其余席位，并记入显式缺席账本。"""
        aid = str(agent_id or "").strip().lower()
        if aid not in AGENT_META:
            raise ValueError(f"未知席位标识: {agent_id}")
        seat_task = sess.active_seat_tasks.get(aid)
        sess.skipped_seat_flags.add(aid)
        self._record_absent_seat(
            sess,
            aid,
            reason="主持人手动跳过发言",
            error_kind="skipped",
            phase=sess.stage,
            abnormal=False,
        )
        try:
            await self.runner.cancel_seat_active_stream(sess.session_id, aid)
        except Exception:
            pass
        if seat_task and not seat_task.done():
            seat_task.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(seat_task), timeout=1.5)
            except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
                pass
        else:
            sess.skipped_seat_flags.discard(aid)
            msg_obj = sess.active_seat_msgs.pop(aid, None)
            if msg_obj and msg_obj.get("streaming"):
                msg_obj["streaming"] = False
                msg_obj["error"] = False
                msg_obj["skipped"] = True
                msg_obj["activity"] = ""
                msg_obj["badge"] = "已跳过本轮"
                if not str(msg_obj.get("content") or "").strip():
                    msg_obj["content"] = "*（已跳过本席本轮发言，会议继续推进）*"
                await self.broadcast(sess, "msg_done", msg_obj)
            if sess.seat_states.get(aid, {}).get("status") in ("thinking", "speaking", "queued"):
                await self._set_seat(sess, aid, "idle", "已跳过本轮")
            await self.broadcast(sess, "whiteboard_update", sess.whiteboard)
            self._save_persisted_sessions()
        return {"ok": True, "agent_id": aid, "badge": "已跳过本轮"}

    async def cancel_active_flow(
        self,
        sess: MeetingSession,
        reason_tag: str = "已中断",
        persist: bool = True,
        wait_task: bool = False,
    ) -> None:
        """会话短锁内零等待标记世代取消（Zero-Await CAS），锁外非阻塞发送进程取消信号，彻底根除重入死锁与 stop 饥饿。"""
        async with sess.session_lock:
            if sess.active_operation_id:
                sess.cancelled_operations.add(sess.active_operation_id)
            old_task = sess.active_task
            old_seat_tasks = list(sess.active_seat_tasks.items())
            sess.active_task = None
            sess.active_seat_tasks.clear()
            sess.active_seat_msgs.clear()
            sess.skipped_seat_flags.clear()
            if sess.exec_state == "preparing":
                sess.exec_state = "idle"

        for aid in AGENT_ORDER:
            try:
                await self.runner.cancel_seat_active_stream(sess.session_id, aid)
            except Exception:
                pass
            try:
                await self.runner.cancel_seat_active_stream("exec", aid)
            except Exception:
                pass
        for _, stask in old_seat_tasks:
            if stask and not stask.done():
                stask.cancel()
        if old_task and not old_task.done():
            old_task.cancel()
            if wait_task:
                try:
                    await asyncio.wait_for(asyncio.shield(old_task), timeout=1.5)
                except Exception:
                    pass

        for idx_m, msg in enumerate(sess.messages):
            if msg.get("streaming"):
                sanitize_persisted_message(msg, fallback_badge=reason_tag)
                await self.broadcast(sess, "msg_done", msg)
                self._persist_single_session(sess, single_msg_idx=idx_m)
        self._sync_seat_readiness(sess)
        for _, st in sess.seat_states.items():
            if st["status"] in ("thinking", "speaking", "queued", "executing"):
                st["status"] = "idle"
                if not st.get("enabled", True):
                    st["badge"] = "已暂停参会"
                else:
                    st["badge"] = "已就绪" if st["binary_ready"] else "未检测到 CLI"
            await self.broadcast(sess, "seat_update", st)
        if persist:
            self._save_persisted_sessions()

    async def _finalize_task_idle_state(
        self,
        sess: MeetingSession,
        owner_task: Optional[asyncio.Task],
        operation_id: str = "",
    ) -> None:
        """世代隔离收口：若当前会话已切入新一代任务，旧任务的延迟 finally 绝不覆写新任务状态，且锁内零 await。"""
        is_current_owner = False
        async with sess.session_lock:
            if owner_task is None or sess.active_task is owner_task or (
                operation_id and sess.active_operation_id == operation_id and sess.active_task is None
            ):
                sess.active_task = None
                is_current_owner = True
            if operation_id and sess.active_operation_id == operation_id:
                sess.exec_state = "idle"
                sess.execution_started_at = 0.0
        if not is_current_owner:
            return
        sess.active_seat_tasks.clear()
        sess.active_seat_msgs.clear()
        for idx_m, msg in enumerate(sess.messages):
            if msg.get("streaming") or str(msg.get("badge") or "") in STALE_STREAMING_BADGES:
                sanitize_persisted_message(msg, fallback_badge="已结束")
                await self.broadcast(sess, "msg_done", msg)
                self._persist_single_session(sess, single_msg_idx=idx_m)
        for _, st in sess.seat_states.items():
            if st["status"] in ("thinking", "speaking", "queued", "executing"):
                st["status"] = "idle"
                if st.get("badge") in STALE_STREAMING_BADGES or str(st.get("badge") or "").startswith("执行中"):
                    st["badge"] = (
                        ("已就绪" if st.get("binary_ready") else "未检测到 CLI")
                        if st.get("enabled", True)
                        else "已暂停参会"
                    )
                await self.broadcast(sess, "seat_update", st)

    async def stop_session_flow(self, sess: MeetingSession) -> dict:
        was_busy = sess.is_busy
        was_exec = sess.stage == "executing" or sess.exec_state in ("preparing", "running")
        cancelled_op = sess.active_operation_id
        await self.cancel_active_flow(sess, reason_tag="手动停止", wait_task=False)
        if sess.topic:
            await self._set_stage(sess, "awaiting_chair", "已暂停，待主持人指令")
        else:
            await self._set_stage(sess, "idle", "待输入议题")
        if was_busy:
            await self._append_non_agent_message(
                sess,
                speaker="system",
                speaker_name="系统",
                role_title="流程控制",
                phase_label="已暂停",
                content=(
                    "已发出停止指令并终止当前执行进程组。待工作区锁与状态收口后即可重新触发执行。"
                    if was_exec
                    else "已停止当前发言生成。您可以补充要求继续追问、切换席位职责发言，或直接形成决议。"
                ),
                badge="已停止",
            )
        return {"ok": True, "cancelled_operation_id": cancelled_op}

    async def _set_stage(self, sess: MeetingSession, stage: str, consensus_status: str) -> None:
        sess.stage = stage
        sess.updated_ts = time.time()
        sess.whiteboard["consensus_status"] = consensus_status
        await self._broadcast_meta(sess)
        self._save_persisted_sessions()

    async def _set_seat(
        self,
        sess: MeetingSession,
        agent_id: str,
        status: str,
        badge: str,
        ttft_ms: Optional[int] = None,
        elapsed_ms: Optional[int] = None,
    ) -> None:
        seat = sess.seat_states[agent_id]
        seat["status"] = status
        seat["badge"] = badge
        if ttft_ms is not None:
            seat["ttft_ms"] = ttft_ms
        if elapsed_ms is not None:
            seat["elapsed_ms"] = elapsed_ms
        await self.broadcast(sess, "seat_update", seat)

    async def _append_non_agent_message(
        self,
        sess: MeetingSession,
        speaker: str,
        speaker_name: str,
        role_title: str,
        phase_label: str,
        content: str,
        badge: str = "",
        error: bool = False,
        attachments: Optional[List[dict]] = None,
    ) -> dict:
        sess.updated_ts = time.time()
        msg = {
            "id": f"m_{uuid.uuid4().hex[:8]}",
            "speaker": speaker,
            "speaker_name": speaker_name,
            "role_title": role_title,
            "phase_label": phase_label,
            "content": content,
            "badge": badge,
            "attachments": list(attachments) if attachments else [],
            "target": None,
            "ttft_ms": 0,
            "elapsed_ms": 0,
            "streaming": False,
            "error": error,
            "timestamp": now_hhmmss(),
        }
        sess.messages.append(msg)
        await self.broadcast(sess, "msg_start", msg)
        await self.broadcast(sess, "msg_done", msg)
        self._save_persisted_sessions()
        return msg

    def _get_ready_enabled_agents(self, sess: MeetingSession) -> Tuple[List[str], List[str]]:
        self._sync_seat_readiness(sess)
        ready: List[str] = []
        missing: List[str] = []
        for aid in sess.enabled_agents:
            if sess.seat_states[aid].get("binary_ready"):
                ready.append(aid)
            else:
                missing.append(aid)
        return ready, missing

    def _pick_lead_synthesizer(self, sess: MeetingSession, candidates: List[str]) -> Optional[str]:
        """根据参会席位角色职责动态选出收敛人（优先架构规划/全栈架构，其次 Carbon 或顺位首席）。"""
        if not candidates:
            return None
        synth_cands = [
            aid
            for aid in candidates
            if get_persona_spec(sess.seat_personas.get(aid, ""), aid).get("is_synthesizer")
        ]
        if synth_cands:
            return "carbon" if "carbon" in synth_cands else synth_cands[0]
        return None

    def _pick_adversarial_roles(self, sess: MeetingSession, ready_agents: List[str]) -> Tuple[str, str, str]:
        """为正反辩证模式选定：正方立论席（proposer）、反向审计席（auditor）、综合裁定席（arbiter）。"""
        proposer = ""
        for aid in ready_agents:
            if sess.seat_personas.get(aid) in ("implementer", "fullstack_solo"):
                proposer = aid
                break
        if not proposer:
            proposer = "astra" if "astra" in ready_agents else ready_agents[0]

        remaining_after_prop = [a for a in ready_agents if a != proposer]
        auditor = ""
        for aid in remaining_after_prop:
            if sess.seat_personas.get(aid) in ("red_team", "perf_sre", "qa_audit"):
                auditor = aid
                break
        if not auditor:
            auditor = "grok" if "grok" in remaining_after_prop else remaining_after_prop[0]

        remaining_third = [a for a in remaining_after_prop if a != auditor]
        if remaining_third:
            arbiter = ""
            for aid in remaining_third:
                if sess.seat_personas.get(aid) == "planner":
                    arbiter = aid
                    break
            if not arbiter:
                arbiter = "carbon" if "carbon" in remaining_third else remaining_third[0]
        else:
            # 仅 2 席参会时由主方案席完成最终收敛
            arbiter = proposer
        return proposer, auditor, arbiter

    def _resolve_driver_groups(
        self,
        sess: MeetingSession,
        agent_ids: List[str],
    ) -> Tuple[Dict[str, List[str]], Dict[str, bool], str]:
        """
        按底层生效 CLI 驱动对本批参会席位分组：
        - 不同底层 CLI 驱动返回独立分组以保持高吞吐并发；
        - 绑定到同一底层 CLI 驱动的多个席位自动归入同一串行组，标记无状态调用（stateless=True）。
        """
        inspected = self.settings.inspect_status()
        session_drv_counts: Dict[str, int] = {}

        def _group_key_for_info(info_d: dict, fallback_id: str) -> str:
            if info_d.get("binary_detected"):
                return normalize_driver_family_key(
                    str(info_d.get("effective_driver") or ""),
                    str(info_d.get("binary_path") or ""),
                )
            return fallback_id

        for en_aid in sess.enabled_agents:
            info = inspected.get(en_aid) or {}
            if info.get("binary_detected"):
                gk = _group_key_for_info(info, en_aid)
                session_drv_counts[gk] = session_drv_counts.get(gk, 0) + 1

        batch_groups: Dict[str, List[str]] = {}
        stateless_map: Dict[str, bool] = {}
        shared_seats: List[str] = []

        for en_aid in sess.enabled_agents:
            info = inspected.get(en_aid) or {}
            gk = _group_key_for_info(info, en_aid)
            if session_drv_counts.get(gk, 0) > 1:
                p_label = get_persona_spec(sess.seat_personas.get(en_aid, ""), en_aid)["label"]
                shared_seats.append(f"{self._seat_name(sess, en_aid)}（{p_label}）")

        for aid in agent_ids:
            info = inspected.get(aid) or {}
            gk = _group_key_for_info(info, f"solo_{aid}")
            batch_groups.setdefault(gk, []).append(aid)
            stateless_map[aid] = session_drv_counts.get(gk, 0) > 1

        roster_desc = "、".join(shared_seats) if len(shared_seats) > 1 else ""
        return batch_groups, stateless_map, roster_desc

    async def _await_driver_buffer(self, group_key: str) -> None:
        last_ts = self._last_driver_finish_ts.get(group_key, 0.0)
        if last_ts > 0:
            gap = time.monotonic() - last_ts
            if gap < self.SINGLE_CLI_SERIAL_BUFFER_SEC:
                await asyncio.sleep(self.SINGLE_CLI_SERIAL_BUFFER_SEC - gap)

    async def _run_agent_batch(
        self,
        sess: MeetingSession,
        agent_ids: List[str],
        stage_key: str,
        phase_label: str,
        is_solo_mode: bool = False,
        cue_by_agent: Optional[Dict[str, str]] = None,
    ) -> List[Tuple[bool, Optional[str], str, Optional[bool]]]:
        """
        混合并发/串行批次调度器（含严格首轮盲评快照隔离 Section 1.1.2）：
        - 批次启动前冻结历史消息快照 frozen_history 与白板快照 frozen_whiteboard，
          即使在单 CLI 串行回退模式下，后序席位也绝不会读取到同批次前序席位的输出或新入板要点，确保 100% 盲评独立；
        - 不同 CLI 驱动之间并发运行；单席跳过仅终止该席位当前回合，不阻断同批次其余席位。
        """
        if not agent_ids:
            return []
        batch_groups, stateless_map, roster_desc = self._resolve_driver_groups(sess, agent_ids)
        outcomes_by_agent: Dict[str, Tuple[bool, Optional[str], str, Optional[bool]]] = {}
        cues = cue_by_agent or {}

        # 批次级输入快照冻结：杜绝串行回退或延迟调度下的同轮次串味污染
        frozen_history: List[dict] = [
            {"speaker": m["speaker_name"], "content": m["content"]}
            for m in sess.messages
            if not m.get("streaming")
            and not m.get("error")
            and not m.get("skipped")
            and m.get("content")
            and m.get("speaker") != "system"
        ]
        frozen_wb: dict = copy.deepcopy(sess.whiteboard)

        cli_conc = max(1, min(6, int(getattr(self.settings, "single_cli_concurrency", 3) or 3)))
        for _, gaids in batch_groups.items():
            if len(gaids) > cli_conc:
                for waiting_aid in gaids[cli_conc:]:
                    await self._set_seat(sess, waiting_aid, "queued", f"排队等待并发通道 (上限 {cli_conc})…")

        async def _run_group(gkey: str, gaids: List[str]) -> None:
            is_shared = any(stateless_map.get(a, False) for a in gaids)
            if len(gaids) > 1 and cli_conc > 1:
                group_sem = asyncio.Semaphore(cli_conc)
                slot_counter = 0

                async def _run_staggered(idx_s: int, aid_s: str) -> None:
                    nonlocal slot_counter
                    if idx_s > 0:
                        await asyncio.sleep(self.SINGLE_CLI_PARALLEL_STAGGER_SEC * min(idx_s, cli_conc))
                    async with group_sem:
                        slot_counter += 1
                        res_s = await self._run_single_agent_turn(
                            sess,
                            aid_s,
                            stage_key,
                            phase_label,
                            cue_instruction=cues.get(aid_s, ""),
                            is_solo_mode=is_solo_mode,
                            stateless=stateless_map.get(aid_s, False),
                            shared_cli_roster=roster_desc if stateless_map.get(aid_s, False) else "",
                            frozen_history=frozen_history,
                            frozen_whiteboard=frozen_wb,
                        )
                        self._last_driver_finish_ts[gkey] = time.monotonic()
                        outcomes_by_agent[aid_s] = res_s

                await asyncio.gather(*(_run_staggered(i, a) for i, a in enumerate(gaids)))
                return

            for idx, aid in enumerate(gaids):
                if is_shared or idx > 0:
                    await self._await_driver_buffer(gkey)
                res = await self._run_single_agent_turn(
                    sess,
                    aid,
                    stage_key,
                    phase_label,
                    cue_instruction=cues.get(aid, ""),
                    is_solo_mode=is_solo_mode,
                    stateless=stateless_map.get(aid, False),
                    shared_cli_roster=roster_desc if stateless_map.get(aid, False) else "",
                    frozen_history=frozen_history,
                    frozen_whiteboard=frozen_wb,
                )
                if is_shared or len(gaids) > 1:
                    self._last_driver_finish_ts[gkey] = time.monotonic()
                outcomes_by_agent[aid] = res

        await asyncio.gather(*(_run_group(gk, gaids) for gk, gaids in batch_groups.items()))
        return [outcomes_by_agent.get(aid, (False, None, "未完成", None)) for aid in agent_ids]

    @staticmethod
    def _badge_for_error_kind(error_kind: str) -> str:
        return {
            "unsupported_effort_or_model": "档位不兼容",
            "quota_rate_limit": "配额限流",
            "auth_expired": "鉴权失效",
            "timeout": "响应超时",
            "binary_missing": "缺少 CLI",
        }.get(error_kind, "调用异常")

    async def _run_single_agent_turn(
        self,
        sess: MeetingSession,
        agent_id: str,
        stage_key: str,
        phase_label: str,
        cue_instruction: str = "",
        ingest_whiteboard: bool = True,
        is_solo_mode: bool = False,
        stateless: Optional[bool] = None,
        shared_cli_roster: Optional[str] = None,
        existing_msg_obj: Optional[dict] = None,
        turn_override: Optional[dict] = None,
        frozen_history: Optional[List[dict]] = None,
        frozen_whiteboard: Optional[dict] = None,
    ) -> Tuple[bool, Optional[str], str, Optional[bool]]:
        seat_disp_name = self._seat_name(sess, agent_id)
        p_key = sess.seat_personas.get(agent_id) or DEFAULT_SEAT_PERSONAS.get(agent_id, "planner")
        pspec = get_persona_spec(p_key, fallback_agent_id=agent_id)

        if stateless is None or shared_cli_roster is None:
            batch_groups, stateless_map, roster_desc = self._resolve_driver_groups(sess, [agent_id])
            use_stateless = stateless if stateless is not None else stateless_map.get(agent_id, False)
            use_roster = (
                shared_cli_roster
                if shared_cli_roster is not None
                else (roster_desc if use_stateless else "")
            )
            if use_stateless:
                for gk in batch_groups:
                    await self._await_driver_buffer(gk)
        else:
            use_stateless = stateless
            use_roster = shared_cli_roster
            batch_groups = {}

        effective_override: dict = {}
        if sess.seat_efforts.get(agent_id):
            effective_override["effort"] = sess.seat_efforts[agent_id]
            effective_override["strict_effort"] = True
        if isinstance(turn_override, dict) and turn_override:
            effective_override.update(turn_override)

        seat_info = sess.seat_states.get(agent_id) or {}
        disp_driver = str(effective_override.get("driver") or seat_info.get("effective_driver") or "")
        disp_model = str(effective_override.get("model") or seat_info.get("effective_model") or "")
        disp_effort = str(effective_override.get("effort") or seat_info.get("effective_effort") or "")

        await self._set_seat(sess, agent_id, "thinking", "汇总决议中" if stage_key == "synthesis" else "思考中")

        if frozen_history is not None:
            completed_msgs = list(frozen_history)
        else:
            completed_msgs = [
                {"speaker": m["speaker_name"], "content": m["content"]}
                for m in sess.messages
                if m is not existing_msg_obj
                and not m.get("streaming")
                and not m.get("error")
                and not m.get("skipped")
                and m.get("content")
                and m.get("speaker") != "system"
            ]
        recent_snapshot = completed_msgs[-240:] if stage_key == "synthesis" else completed_msgs[-80:]
        prompt_whiteboard = frozen_whiteboard if frozen_whiteboard is not None else sess.whiteboard

        self._turn_seq_counter += 1
        turn_start_seq = self._turn_seq_counter
        started_epoch_ms = int(time.time() * 1000)

        if existing_msg_obj is not None:
            msg_obj = existing_msg_obj
            msg_id = msg_obj["id"]
            msg_obj.update(
                {
                    "role_title": pspec["label"],
                    "phase_label": phase_label,
                    "content": "",
                    "badge": "重试中",
                    "target": None,
                    "ttft_ms": 0,
                    "elapsed_ms": 0,
                    "started_ts": started_epoch_ms,
                    "streaming": True,
                    "skipped": False,
                    "error": False,
                    "error_kind": "",
                    "error_detail": "",
                    "failed_driver": "",
                    "failed_model": "",
                    "failed_effort": "",
                    "driver": disp_driver,
                    "model": disp_model,
                    "effort": disp_effort,
                    "activity": "准备推理上下文…",
                    "_start_seq": turn_start_seq,
                    "_done_seq": 0,
                    "timestamp": now_hhmmss(),
                }
            )
        else:
            msg_id = f"m_{uuid.uuid4().hex[:8]}"
            msg_obj = {
                "id": msg_id,
                "speaker": agent_id,
                "speaker_name": seat_disp_name,
                "role_title": pspec["label"],
                "phase_label": phase_label,
                "content": "",
                "badge": "思考中",
                "target": None,
                "ttft_ms": 0,
                "elapsed_ms": 0,
                "started_ts": started_epoch_ms,
                "streaming": True,
                "skipped": False,
                "error": False,
                "error_kind": "",
                "error_detail": "",
                "failed_driver": "",
                "failed_model": "",
                "failed_effort": "",
                "driver": disp_driver,
                "model": disp_model,
                "effort": disp_effort,
                "activity": "准备推理上下文…",
                "retry_stage": stage_key,
                "retry_phase": phase_label,
                "retry_cue": cue_instruction,
                "_start_seq": turn_start_seq,
                "_done_seq": 0,
                "timestamp": now_hhmmss(),
            }
            sess.messages.append(msg_obj)

        sess.skipped_seat_flags.discard(agent_id)
        sess.active_seat_msgs[agent_id] = msg_obj
        await self.broadcast(sess, "msg_start", msg_obj)

        expected_turn_run_id = sess.active_run_id or sess.active_operation_id or f"turn_{turn_start_seq}"
        expected_attempt_id = f"att_{msg_id}_{turn_start_seq}"

        async def _consume_seat_stream() -> Tuple[bool, Optional[str], str, Optional[bool]]:
            first_chunk = True
            called_target: Optional[str] = None
            final_badge = ""
            consensus_flag: Optional[bool] = None
            received_done_event = False

            turn_kwargs = dict(
                session_id=sess.session_id,
                agent_id=agent_id,
                stage=stage_key,
                topic=sess.topic,
                collab_mode=COLLAB_MODES.get(sess.collab_mode, {}).get("label", "深度研讨"),
                whiteboard=prompt_whiteboard,
                recent_messages=recent_snapshot,
                cue_instruction=cue_instruction,
                all_completed_count=len(completed_msgs),
                session_workspace=sess.workspace_dir or self.settings.workspace_dir,
                persona_key=p_key,
                is_solo_mode=is_solo_mode,
                stateless=use_stateless,
                shared_cli_roster=use_roster,
                collab_mode_key=sess.collab_mode,
                turn_override=effective_override if effective_override else None,
            )
            try:
                stream_gen = self.runner.stream_discussion_turn(**turn_kwargs)
            except TypeError:
                for opt_k in ("collab_mode_key", "turn_override"):
                    turn_kwargs.pop(opt_k, None)
                try:
                    stream_gen = self.runner.stream_discussion_turn(**turn_kwargs)
                except TypeError:
                    turn_kwargs.pop("stateless", None)
                    turn_kwargs.pop("shared_cli_roster", None)
                    stream_gen = self.runner.stream_discussion_turn(**turn_kwargs)

            async for ev in stream_gen:
                etype = ev.get("type")
                if etype in ("status", "activity"):
                    detail_txt = str(ev.get("detail") or ev.get("text") or "").strip()
                    if ev.get("driver"):
                        msg_obj["driver"] = str(ev["driver"])
                    if ev.get("model"):
                        msg_obj["model"] = str(ev["model"])
                    if ev.get("effort") is not None and str(ev.get("effort")) != "":
                        msg_obj["effort"] = str(ev["effort"])
                    if detail_txt and first_chunk:
                        msg_obj["activity"] = detail_txt
                        status_pkt = {
                            "id": msg_id,
                            "agent_id": agent_id,
                            "detail": detail_txt,
                            "activity": detail_txt,
                            "driver": msg_obj.get("driver", ""),
                            "model": msg_obj.get("model", ""),
                            "effort": msg_obj.get("effort", ""),
                        }
                        await self.broadcast(sess, "msg_status", status_pkt)
                        await self.broadcast(sess, "msg_activity", status_pkt)
                        short_badge = detail_txt[:16] + ("…" if len(detail_txt) > 16 else "")
                        await self._set_seat(sess, agent_id, "thinking", short_badge)
                elif etype == "delta":
                    if first_chunk:
                        first_chunk = False
                        msg_obj["activity"] = ""
                        await self._set_seat(sess, agent_id, "speaking", "发言中")
                    msg_obj["content"] += ev["text"]
                    await self.broadcast(sess, "msg_delta", {"id": msg_id, "delta": ev["text"]})
                elif etype == "done":
                    received_done_event = True
                    called_target = ev.get("target")
                    final_badge = ev.get("badge", "")
                    consensus_flag = ev.get("consensus")
                    structured_items = ev.get("wb_items") or []
                    structured_pts = ev.get("wb_points") or []
                    ev_status = str(ev.get("status") or "success")
                    ev_terminal = bool(ev.get("terminal_received", True))
                    ev_partial = bool(ev.get("partial_output", False))
                    ev_err_kind = str(ev.get("error_kind") or "")
                    ev_driver = str(ev.get("driver") or msg_obj.get("driver") or seat_info.get("effective_driver") or "")
                    ev_bpath = str(ev.get("binary_path") or (self.settings.inspect_status().get(agent_id) or {}).get("binary_path") or "")
                    is_op_cancelled = bool(sess.active_operation_id and sess.active_operation_id in sess.cancelled_operations)
                    is_seat_skipped = bool(agent_id in sess.skipped_seat_flags or msg_obj.get("skipped"))

                    self._turn_seq_counter += 1
                    msg_obj["_done_seq"] = self._turn_seq_counter
                    msg_obj["activity"] = ""
                    msg_obj["content"] = ev["full_text"]
                    msg_obj["badge"] = final_badge
                    msg_obj["target"] = called_target
                    msg_obj["ttft_ms"] = ev["ttft_ms"]
                    msg_obj["elapsed_ms"] = ev["elapsed_ms"]
                    msg_obj["streaming"] = False
                    msg_obj["skipped"] = is_seat_skipped
                    msg_obj["error"] = bool(ev_err_kind)
                    msg_obj["error_kind"] = ev_err_kind
                    msg_obj["error_detail"] = ""
                    sess.updated_ts = time.time()

                    admitted_wb = check_whiteboard_admission_gate(
                        run_id=str(ev.get("run_id") or expected_turn_run_id),
                        expected_run_id=expected_turn_run_id,
                        attempt_id=str(ev.get("attempt_id") or expected_attempt_id),
                        expected_attempt_id=expected_attempt_id,
                        status=ev_status,
                        terminal_received=ev_terminal,
                        error_kind=ev_err_kind,
                        partial_output=ev_partial,
                        skipped=is_seat_skipped,
                        cancelled=is_op_cancelled,
                        clean_body=ev["full_text"],
                    )
                    if admitted_wb:
                        self._clear_absent_seat(sess, agent_id)
                        sess.round_driver_records.append(
                            {
                                "agent_id": agent_id,
                                "status": "success",
                                "driver": ev_driver,
                                "binary_path": ev_bpath,
                            }
                        )
                        self._refresh_epistemic_status(sess)
                    elif is_seat_skipped:
                        self._record_absent_seat(
                            sess,
                            agent_id,
                            reason="主持人手动跳过发言",
                            error_kind="skipped",
                            phase=phase_label,
                            abnormal=False,
                        )
                    elif ev_err_kind:
                        self._record_absent_seat(
                            sess,
                            agent_id,
                            reason=self._badge_for_error_kind(ev_err_kind),
                            error_kind=ev_err_kind,
                            phase=phase_label,
                            abnormal=True,
                        )

                    await self.broadcast(sess, "msg_done", msg_obj)
                    await self._set_seat(
                        sess,
                        agent_id,
                        "idle",
                        final_badge,
                        ttft_ms=ev["ttft_ms"],
                        elapsed_ms=ev["elapsed_ms"],
                    )
                    if ingest_whiteboard and admitted_wb:
                        self._ingest_into_whiteboard(
                            sess,
                            agent_id,
                            ev["full_text"],
                            structured_pts=structured_pts,
                            structured_items=structured_items,
                            source_msg_id=msg_id,
                        )
                    await self.broadcast(sess, "whiteboard_update", sess.whiteboard)
                    try:
                        msg_idx = sess.messages.index(msg_obj)
                    except ValueError:
                        msg_idx = None
                    self._persist_single_session(sess, single_msg_idx=msg_idx)

            if use_stateless and batch_groups:
                for gk in batch_groups:
                    self._last_driver_finish_ts[gk] = time.monotonic()
            if not received_done_event:
                self._record_absent_seat(
                    sess,
                    agent_id,
                    reason="流式响应未正常结束",
                    error_kind="incomplete_stream",
                    phase=phase_label,
                    abnormal=True,
                )
                await self.broadcast(sess, "whiteboard_update", sess.whiteboard)
                return False, None, "未完成", None
            return True, called_target, final_badge, consensus_flag

        seat_task = asyncio.create_task(_consume_seat_stream())
        sess.active_seat_tasks[agent_id] = seat_task
        try:
            return await seat_task
        except asyncio.CancelledError:
            if agent_id in sess.skipped_seat_flags:
                sess.skipped_seat_flags.discard(agent_id)
                elapsed_skip = max(0, int(time.time() * 1000) - started_epoch_ms)
                msg_obj["activity"] = ""
                msg_obj["streaming"] = False
                msg_obj["error"] = False
                msg_obj["skipped"] = True
                msg_obj["elapsed_ms"] = elapsed_skip
                msg_obj["badge"] = "已跳过本轮"
                if not str(msg_obj.get("content") or "").strip():
                    msg_obj["content"] = "*（已跳过本席本轮发言，会议继续推进）*"
                self._record_absent_seat(
                    sess,
                    agent_id,
                    reason="主持人手动跳过发言",
                    error_kind="skipped",
                    phase=phase_label,
                    abnormal=False,
                )
                await self.broadcast(sess, "msg_done", msg_obj)
                await self._set_seat(sess, agent_id, "idle", "已跳过本轮", elapsed_ms=elapsed_skip)
                await self.broadcast(sess, "whiteboard_update", sess.whiteboard)
                self._save_persisted_sessions()
                return False, None, "已跳过本轮", None
            if not seat_task.done():
                seat_task.cancel()
                try:
                    await seat_task
                except Exception:
                    pass
            raise
        except CLIInvocationError as exc:
            err_badge = self._badge_for_error_kind(exc.error_kind)
            diag_lines = []
            if exc.driver or exc.model or exc.effort or exc.exit_code is not None:
                diag_lines.append(
                    f"driver={exc.driver or 'auto'} | model={exc.model or 'default'} | "
                    f"effort={exc.effort or 'none'} | exit_code={exc.exit_code if exc.exit_code is not None else 'N/A'}"
                )
            if exc.stderr:
                diag_lines.append(exc.stderr[:1600])
            msg_obj["activity"] = ""
            msg_obj["streaming"] = False
            msg_obj["skipped"] = False
            msg_obj["error"] = True
            msg_obj["error_kind"] = exc.error_kind
            msg_obj["error_detail"] = "\n".join(diag_lines).strip()
            msg_obj["failed_driver"] = exc.driver or disp_driver
            msg_obj["failed_model"] = exc.model or disp_model
            msg_obj["failed_effort"] = exc.effort or disp_effort
            msg_obj["retry_stage"] = stage_key
            msg_obj["retry_phase"] = phase_label
            msg_obj["retry_cue"] = cue_instruction
            msg_obj["content"] = str(exc)
            msg_obj["badge"] = err_badge
            self._record_absent_seat(
                sess,
                agent_id,
                reason=f"{err_badge}（{str(exc)[:60]}）",
                error_kind=exc.error_kind,
                phase=phase_label,
                abnormal=True,
            )
            await self.broadcast(sess, "msg_done", msg_obj)
            await self._set_seat(sess, agent_id, "idle", err_badge)
            await self.broadcast(sess, "whiteboard_update", sess.whiteboard)
            self._save_persisted_sessions()
            return False, None, err_badge, None
        except Exception as exc:
            msg_obj["activity"] = ""
            msg_obj["streaming"] = False
            msg_obj["skipped"] = False
            msg_obj["error"] = True
            msg_obj["error_kind"] = "process_error"
            msg_obj["error_detail"] = str(exc)[:1600]
            msg_obj["failed_driver"] = disp_driver
            msg_obj["failed_model"] = disp_model
            msg_obj["failed_effort"] = disp_effort
            msg_obj["retry_stage"] = stage_key
            msg_obj["retry_phase"] = phase_label
            msg_obj["retry_cue"] = cue_instruction
            msg_obj["content"] = str(exc)
            msg_obj["badge"] = "调用异常"
            self._record_absent_seat(
                sess,
                agent_id,
                reason=f"调用异常（{str(exc)[:60]}）",
                error_kind="process_error",
                phase=phase_label,
                abnormal=True,
            )
            await self.broadcast(sess, "msg_done", msg_obj)
            await self._set_seat(sess, agent_id, "idle", "调用异常")
            await self.broadcast(sess, "whiteboard_update", sess.whiteboard)
            self._save_persisted_sessions()
            return False, None, "调用异常", None
        finally:
            if sess.active_seat_tasks.get(agent_id) is seat_task:
                sess.active_seat_tasks.pop(agent_id, None)
            if sess.active_seat_msgs.get(agent_id) is msg_obj:
                sess.active_seat_msgs.pop(agent_id, None)

    def _build_retry_turn_override(
        self,
        sess: MeetingSession,
        agent_id: str,
        target_msg: Optional[dict],
        mode: str,
    ) -> Tuple[dict, str]:
        """
        构建单席三级就地恢复参数（仅作用于当前重试轮，绝不篡改全局保存配置）：
        - unlimited: 原驱动、原模型、原档位，本轮不设超时重试
        - downgrade: 仅本轮将该席位推理档位下调一档重试
        - borrow: 仅本轮自动借用本机任一已就绪的其他 CLI 驱动按当前角色职责代答
        """
        norm_mode = str(mode or "unlimited").strip().lower()
        if norm_mode not in ("unlimited", "downgrade", "borrow"):
            norm_mode = "unlimited"

        cfg = self.settings.agents[agent_id]
        bpath, _, help_text, eff_drv, is_fb = cfg.get_probe_info(
            persist_cache=False,
            allow_single_cli_fallback=self.settings.allow_single_cli_fallback,
        )
        cur_drv = str((target_msg or {}).get("failed_driver") or eff_drv or cfg.preferred_driver_key())
        cur_model = str(
            (target_msg or {}).get("failed_model")
            or resolve_effective_model_for_driver(cur_drv, cfg.model, is_shared_fb=is_fb if bpath else False)
        )
        cur_effort = str(
            (target_msg or {}).get("failed_effort")
            or sess.seat_efforts.get(agent_id)
            or cfg.discussion_effort
        )

        if norm_mode == "unlimited":
            return {"unlimited_timeout": True}, "原配置重试（不限时）"

        if norm_mode == "downgrade":
            lower_eff = step_down_model_effort(
                cur_drv,
                model=cur_model,
                current_effort=cur_effort,
                help_text=help_text,
            )
            label_eff = lower_eff or "默认档位"
            return (
                {
                    "effort": lower_eff,
                    "strict_effort": True,
                    "unlimited_timeout": True,
                },
                f"降级档位重试（{label_eff}）",
            )

        # norm_mode == "borrow": 查找本机其他已就绪的备用 CLI 驱动
        inspected = self.settings.inspect_status()
        for other_aid in AGENT_ORDER:
            if other_aid == agent_id:
                continue
            oinfo = inspected.get(other_aid) or {}
            odrv = str(oinfo.get("effective_driver") or "")
            if oinfo.get("binary_detected") and odrv and odrv != cur_drv:
                ocfg = self.settings.agents[other_aid]
                omodel = str(oinfo.get("effective_model") or "")
                oeff = str(oinfo.get("effective_discussion_effort") or "")
                drv_label = DRIVER_SPECS.get(odrv, {}).get("cli_name", odrv)
                return (
                    {
                        "driver": odrv,
                        "custom_binary": ocfg.custom_binary if ocfg.driver == odrv else "",
                        "model": omodel,
                        "effort": oeff,
                        "strict_effort": True,
                        "stateless": True,
                        "unlimited_timeout": True,
                    },
                    f"备用引擎代答（{drv_label}）",
                )

        for cand_drv in VALID_DRIVERS:
            if cand_drv == cur_drv:
                continue
            cand_bin = detect_driver_binary(cand_drv)
            if cand_bin:
                cand_model = resolve_effective_model_for_driver(cand_drv, "", is_shared_fb=True)
                cand_eff = normalize_model_effort(cand_drv, model=cand_model, effort="high")
                drv_label = DRIVER_SPECS.get(cand_drv, {}).get("cli_name", cand_drv)
                return (
                    {
                        "driver": cand_drv,
                        "custom_binary": "",
                        "model": cand_model,
                        "effort": cand_eff,
                        "strict_effort": True,
                        "stateless": True,
                        "unlimited_timeout": True,
                    },
                    f"备用引擎代答（{drv_label}）",
                )

        raise ValueError("本机未检测到其他已就绪的备用 CLI 引擎，请使用「原配置重试（不限时）」或「降级档位重试」")

    async def retry_agent_turn(
        self,
        sess: MeetingSession,
        agent_id: str,
        message_id: str = "",
        mode: str = "unlimited",
    ) -> dict:
        """针对异常或跳过席位执行三级就地恢复重试，不中断历史成果、不篡改全局保存配置。"""
        if agent_id not in AGENT_META:
            raise ValueError(f"未知席位标识: {agent_id}")
        target_msg: Optional[dict] = None
        if message_id:
            for m in reversed(sess.messages):
                if m.get("id") == message_id and m.get("speaker") == agent_id:
                    target_msg = m
                    break
        if target_msg is None:
            for m in reversed(sess.messages):
                if m.get("speaker") == agent_id and (m.get("error") or m.get("skipped")):
                    target_msg = m
                    break

        retry_override, mode_desc = self._build_retry_turn_override(sess, agent_id, target_msg, mode)
        await self.cancel_active_flow(sess, reason_tag=f"单席重试 {self._seat_name(sess, agent_id)}")
        sess.active_task = asyncio.create_task(
            self._run_retry_flow(sess, agent_id, target_msg, retry_override, mode_desc)
        )
        await self._broadcast_meta(sess)
        return {"ok": True, "mode": mode, "description": mode_desc}

    async def _run_retry_flow(
        self,
        sess: MeetingSession,
        agent_id: str,
        target_msg: Optional[dict],
        retry_override: dict,
        mode_desc: str,
    ) -> None:
        owner_task = asyncio.current_task()
        try:
            stage_key = str((target_msg or {}).get("retry_stage") or "opening")
            phase_label = str((target_msg or {}).get("retry_phase") or "单席重试")
            cue_ins = str((target_msg or {}).get("retry_cue") or "")
            await self._set_stage(sess, "chair_interrupt", f"{self._seat_name(sess, agent_id)} {mode_desc}…")
            ok, _, err_badge, _ = await self._run_single_agent_turn(
                sess,
                agent_id,
                stage_key,
                phase_label,
                cue_instruction=cue_ins,
                is_solo_mode=len(sess.enabled_agents) == 1,
                existing_msg_obj=target_msg,
                turn_override=retry_override,
            )
            await self._finalize_task_idle_state(sess, owner_task)
            if ok:
                await self._set_stage(sess, "awaiting_chair", f"{self._seat_name(sess, agent_id)} 恢复完成，待主持人推进")
            else:
                await self._set_stage(
                    sess,
                    "awaiting_chair",
                    f"{self._seat_name(sess, agent_id)} 重试未通过（{err_badge or '异常'}），可尝试其他恢复策略或调整配置",
                )
        except asyncio.CancelledError:
            raise
        finally:
            await self._finalize_task_idle_state(sess, owner_task)
            self._save_persisted_sessions(immediate=True)
            await self._broadcast_meta(sess)

    @staticmethod
    def _smart_clip(text: str, limit: int = 165) -> str:
        s = text.strip()
        if len(s) <= limit:
            return s
        cut = s[:limit]
        for sep in ("；", "，", "。", "、", " "):
            idx = cut.rfind(sep)
            if idx >= int(limit * 0.65):
                return cut[:idx] + "…"
        return cut + "…"

    @classmethod
    def _extract_key_points(cls, text: str, max_items: int = 2) -> List[str]:
        if not text:
            return []
        cleaned = re.sub(r"\[(?:状态|徽章|白板|白板要点)[:：][^\]]*\]", "", text)
        cleaned = re.sub(r"```[\s\S]*?```", "", cleaned)
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
                    points.append(cls._smart_clip(candidate))

        if points:
            return points[:max_items]

        numbered = re.findall(r"(?:[1-4①②③④]\s*[\)）、.]|[一二三四]是)\s*([^；;。！!\n]{6,160})", cleaned)
        valid_num = [
            cls._smart_clip(s)
            for s in numbered
            if not is_whiteboard_noise(s.strip())
        ]
        if valid_num:
            return valid_num[:max_items]

        sentences = [
            cls._smart_clip(s)
            for s in re.split(r"[。！？!\n；;]+", cleaned)
            if len(s.strip()) >= 10 and not is_whiteboard_noise(s.strip())
        ]
        return sentences[:max_items]

    def _can_session_auto_promote_decision(self, sess: MeetingSession) -> bool:
        """Section 一.5：统计实际成功驱动族（基于 realpath 防软链接绕过），< 2 时严禁自动升格 decision。"""
        fams = compute_effective_driver_families(sess.round_driver_records)
        if not fams:
            # 尚未积累到跨席异构成功记录时，预检当前启用且就绪席位的潜在异构驱动族；若配置本身同源则立即阻断，若仅 1 席成功亦阻断
            return False
        return can_auto_promote_consensus_decision(
            enabled_seat_count=len(sess.enabled_agents),
            successful_driver_families=fams,
        )

    def _ingest_into_whiteboard(
        self,
        sess: MeetingSession,
        agent_id: str,
        text: str,
        structured_pts: Optional[List[str]] = None,
        structured_items: Optional[List[dict]] = None,
        source_msg_id: str = "",
    ) -> None:
        p_key = sess.seat_personas.get(agent_id) or DEFAULT_SEAT_PERSONAS.get(agent_id, "planner")
        default_kind = get_persona_spec(p_key, fallback_agent_id=agent_id).get("wb_kind", "decision")
        if default_kind not in VALID_WB_KINDS:
            default_kind = "decision"

        # 实时识别正文中 [放弃原方案：...] 与 [修正原方案：旧 -> 新] 标记，立即归入弃案清单防污染白板
        seat_disp = self._seat_name(sess, agent_id)
        for ab_m in re.finditer(r"\[(?:放弃原方案|淘汰方案|废弃方案|弃案)[:：]\s*([^\]]+)\]", text or ""):
            self._record_abandoned_proposal(
                sess,
                ab_m.group(1),
                author=agent_id,
                reason=f"{seat_disp} 显式放弃/证伪淘汰",
                round_phase=sess.stage,
                source_msg_id=source_msg_id,
            )
        for rv_m in re.finditer(r"\[修正原方案[:：]\s*([^\]]+)\]", text or ""):
            rv_txt = rv_m.group(1).strip()
            if "->" in rv_txt or "→" in rv_txt:
                old_p = re.split(r"->|→", rv_txt, maxsplit=1)[0].strip()
                if len(old_p) >= 4:
                    self._record_abandoned_proposal(
                        sess,
                        old_p,
                        author=agent_id,
                        reason=f"{seat_disp} 经质询修正后淘汰初版草案",
                        round_phase=sess.stage,
                        source_msg_id=source_msg_id,
                    )

        candidate_entries: List[Tuple[str, str]] = []
        if structured_items:
            for sit in structured_items:
                if not isinstance(sit, dict):
                    continue
                stxt = str(sit.get("text") or "").strip()
                skind = str(sit.get("kind") or "").strip().lower()
                if not stxt:
                    continue
                if skind == "abandoned":
                    self._record_abandoned_proposal(
                        sess,
                        stxt,
                        author=agent_id,
                        reason=f"{seat_disp} 结构化标记弃案",
                        round_phase=sess.stage,
                        source_msg_id=source_msg_id,
                    )
                    continue
                if is_whiteboard_noise(stxt):
                    continue
                eff_k = skind if skind in VALID_WB_KINDS else default_kind
                candidate_entries.append((eff_k, self._smart_clip(stxt, limit=180)))
        elif structured_pts:
            for p in structured_pts:
                ptxt = str(p or "").strip()
                if ptxt and not is_whiteboard_noise(ptxt):
                    candidate_entries.append((default_kind, self._smart_clip(ptxt, limit=180)))

        if not candidate_entries:
            _, parsed_tail = parse_structured_tail_with_kinds(text)
            for pt in parsed_tail:
                ptxt = str(pt.get("text") or "").strip()
                pkind = str(pt.get("kind") or "").strip().lower()
                if not ptxt:
                    continue
                if pkind == "abandoned":
                    self._record_abandoned_proposal(
                        sess,
                        ptxt,
                        author=agent_id,
                        reason=f"{seat_disp} 结构化标记弃案",
                        round_phase=sess.stage,
                        source_msg_id=source_msg_id,
                    )
                    continue
                if not is_whiteboard_noise(ptxt):
                    candidate_entries.append(
                        (pkind if pkind in VALID_WB_KINDS else default_kind, self._smart_clip(ptxt, limit=180))
                    )

        if not candidate_entries:
            for ext_p in self._extract_key_points(text, max_items=2):
                if ext_p and not is_whiteboard_noise(ext_p):
                    candidate_entries.append((default_kind, ext_p))

        self._refresh_epistemic_status(sess)
        if not candidate_entries:
            return

        wb = _normalize_and_sync_whiteboard(sess.whiteboard, topic=sess.topic, messages=sess.messages)
        items: List[dict] = wb.setdefault("items", [])
        abandoned_norms = {
            _norm_dedupe_key(str(x.get("text") or ""))
            for x in (wb.get("abandoned_proposals") or [])
            if isinstance(x, dict)
        }
        changed = False

        # 三级来源准入：仅当满足异构驱动族 >= 2 且已完成反驳/交叉质询闭环时才自动升格 multi_seat_consensus
        rebuttal_closure_ready = self._has_heterogeneous_rebuttal_closure(sess)
        if rebuttal_closure_ready:
            for ex_it in items:
                if isinstance(ex_it, dict) and ex_it.get("provisional_decision") and ex_it.get("kind") != "decision":
                    ex_it["kind"] = "decision"
                    ex_it["origin_tier"] = "multi_seat_consensus"
                    ex_it.pop("provisional_decision", None)
                    ex_it["ver"] = int(ex_it.get("ver") or 1) + 1
                    changed = True

        for item_kind, p in candidate_entries:
            if is_whiteboard_noise(p):
                continue
            norm_full = _norm_dedupe_key(p)
            if not norm_full or norm_full in abandoned_norms:
                continue
            was_provisional_dec = False
            if item_kind == "decision" and not rebuttal_closure_ready:
                item_kind = "risk"
                was_provisional_dec = True
            norm_prefix = norm_full[:14]

            exact_dup = False
            for existing in items:
                if not isinstance(existing, dict):
                    continue
                if _norm_dedupe_key(str(existing.get("text") or "")) == norm_full:
                    if source_msg_id and not existing.get("source_msg_id"):
                        existing["source_msg_id"] = source_msg_id
                        changed = True
                    exact_dup = True
                    break
            if exact_dup:
                continue

            replaced = False
            if len(norm_prefix) >= 8:
                for existing in items:
                    if (
                        isinstance(existing, dict)
                        and existing.get("author") == agent_id
                        and existing.get("kind") == item_kind
                        and not existing.get("pinned")
                    ):
                        ex_prefix = _norm_dedupe_key(str(existing.get("text") or ""))[:14]
                        if ex_prefix == norm_prefix:
                            existing["text"] = p
                            if source_msg_id:
                                existing["source_msg_id"] = source_msg_id
                            existing["ver"] = int(existing.get("ver") or 1) + 1
                            replaced = True
                            changed = True
                            break

            if not replaced:
                ordinal = int(wb.get("wb_version") or 1) + len(items) + 1
                new_wb_entry: dict = {
                    "id": make_deterministic_wb_id(f"{item_kind}_{agent_id}", ordinal, p),
                    "kind": item_kind,
                    "text": p,
                    "author": agent_id,
                    "origin_tier": "multi_seat_consensus" if item_kind == "decision" else "provisional_suggestion",
                    "source_msg_id": source_msg_id,
                    "pinned": False,
                    # P0 硬闸门：所有 AI 新增任务项（action）缺省 checked=False，须经主持核对勾选！
                    "checked": False if item_kind == "action" else True,
                    "ver": 1,
                }
                if was_provisional_dec:
                    new_wb_entry["provisional_decision"] = True
                items.append(new_wb_entry)
                changed = True

        if changed:
            sync_whiteboard_legacy_arrays_and_caps(wb)
            wb["wb_version"] = int(wb.get("wb_version") or 1) + 1

    async def start_topic_meeting(
        self,
        sess: MeetingSession,
        topic: str,
        collab_mode: Optional[str] = None,
        auto_preview_exec: Optional[bool] = None,
        enabled_agents: Optional[List[str]] = None,
        seat_personas: Optional[Dict[str, str]] = None,
        seat_efforts: Optional[Dict[str, str]] = None,
        executor_agent: Optional[str] = None,
        scenario_pack: Optional[str] = None,
        artifact_type: Optional[str] = None,
        reset_history: bool = False,
        attachments: Optional[List[dict]] = None,
    ) -> None:
        await self.cancel_active_flow(sess, reason_tag="切换新议题")
        sess.round_driver_records.clear()
        await self.runner.reset_session_context(sess.session_id)
        draft_items = list(sess.whiteboard.get("items") or []) if not sess.messages and not reset_history else []
        prev_atts = list(sess.whiteboard.get("session_attachments") or []) if not reset_history else []
        merged_atts: List[dict] = []
        seen_att_ids: set = set()
        for att_it in prev_atts + list(attachments or []):
            if isinstance(att_it, dict) and att_it.get("id") and att_it["id"] not in seen_att_ids:
                seen_att_ids.add(att_it["id"])
                merged_atts.append(att_it)
        if reset_history:
            sess.messages = []
            await self.broadcast(sess, "session_cleared", {"session_id": sess.session_id})

        if scenario_pack is not None or artifact_type is not None:
            sess.scenario_pack, sess.artifact_type = normalize_scenario_pack_and_artifact(
                scenario_pack if scenario_pack is not None else sess.scenario_pack,
                artifact_type if artifact_type is not None else sess.artifact_type,
            )

        if enabled_agents:
            valid = [aid for aid in AGENT_ORDER if aid in enabled_agents]
            if valid:
                sess.enabled_agents = valid
        if isinstance(seat_personas, dict):
            for aid, p_key in seat_personas.items():
                if aid in AGENT_ORDER and p_key in VALID_PERSONAS:
                    sess.seat_personas[aid] = p_key
        if isinstance(seat_efforts, dict):
            for aid, eff_v in seat_efforts.items():
                eff_c = str(eff_v or "").strip().lower()
                if aid in AGENT_ORDER and eff_c in VALID_EFFORT_LEVELS:
                    sess.seat_efforts[aid] = eff_c
        if executor_agent and executor_agent in AGENT_ORDER:
            sess.executor_agent = executor_agent

        if collab_mode is not None:
            norm_m, inferred_auto = normalize_collab_mode(collab_mode, auto_preview_exec=auto_preview_exec)
            sess.collab_mode = norm_m
            if collab_mode == "arch_to_exec" and auto_preview_exec is None:
                sess.auto_preview_exec = inferred_auto
        if auto_preview_exec is not None:
            sess.auto_preview_exec = bool(auto_preview_exec)

        self._sync_seat_readiness(sess)
        sess.topic = topic.strip()
        short_title, initial_constraints = summarize_topic_and_constraints(sess.topic)
        sess.title = short_title or (sess.topic[:24] + ("…" if len(sess.topic) > 24 else ""))
        deduped_initial = dedupe_chair_constraints(sess.topic, sess.title, initial_constraints)

        chair_msg = await self._append_non_agent_message(
            sess,
            speaker="chair",
            speaker_name="主持人",
            role_title="发起议题",
            phase_label="议题",
            content=sess.topic,
            badge=COLLAB_MODES[sess.collab_mode]["label"],
            attachments=attachments,
        )

        initial_items = [
            {
                "id": make_deterministic_wb_id("chair_constraints", idx_c, c_txt),
                "kind": "decision",
                "text": c_txt,
                "author": "chair",
                "origin_tier": "chair_directive",
                "source_msg_id": chair_msg["id"],
                "pinned": True,
                "checked": True,
                "ver": 1,
            }
            for idx_c, c_txt in enumerate(deduped_initial)
        ]
        sess.whiteboard = {
            "wb_version": int(sess.whiteboard.get("wb_version") or 1) + 1,
            "topic": sess.topic,
            "topic_title": sess.title,
            "consensus_status": "会议进行中",
            "scenario_pack": sess.scenario_pack,
            "artifact_type": sess.artifact_type,
            "epistemic_mode": sess.whiteboard.get("epistemic_mode", ""),
            "epistemic_badge": sess.whiteboard.get("epistemic_badge", ""),
            "chair_constraints": deduped_initial,
            "items": draft_items + initial_items,
            "absent_seats": [],
            "disagreements": [],
            "abandoned_proposals": [],
            "round_summaries": [],
            "resolution_meta": {},
            "carbon_plan": [],
            "grok_risks": [],
            "astra_actions": [],
            "exec_logs": [],
            "exec_diff": "",
            "exec_summary": "",
            "executor_agent": sess.effective_executor_agent(),
            "can_rollback": bool(sess.last_backup),
            "session_attachments": merged_atts,
        }
        _normalize_and_sync_whiteboard(sess.whiteboard, topic=sess.topic, messages=sess.messages)
        self._refresh_epistemic_status(sess)
        await self.broadcast(sess, "whiteboard_update", sess.whiteboard)

        sess.active_task = asyncio.create_task(self._orchestrate_full_meeting(sess))
        await self._broadcast_meta(sess)

    def _analyze_round_disagreements_and_abandonments(
        self,
        sess: MeetingSession,
        round_msgs: List[dict],
        active_agents: List[str],
        round_label: str,
    ) -> List[dict]:
        """
        解析交叉质询/答辩回合中的结构化分歧对象（disagreement_id）与立场变化（stance_delta），
        生成回合分歧摘要供前端聊天流与白板渲染。
        """
        dis_list: List[dict] = sess.whiteboard.setdefault("disagreements", [])
        name_to_aid: Dict[str, str] = {}
        for aid_k in AGENT_ORDER:
            name_to_aid[aid_k] = aid_k
            sn = self._seat_name(sess, aid_k)
            if sn:
                name_to_aid[sn.strip().lower()] = aid_k

        rebut_re = re.compile(r"\[反驳\s*@?([^：:\]\s]+)\s*[：:]\s*([^\]]+)\]")
        created_in_round: List[dict] = []
        revised_count = 0
        abandoned_count = 0
        no_obj_seats: List[str] = []

        for m in round_msgs:
            if not isinstance(m, dict) or m.get("error") or m.get("skipped"):
                continue
            sp = str(m.get("speaker") or "").lower()
            if sp not in AGENT_META:
                continue
            sp_name = self._seat_name(sess, sp)
            mid = str(m.get("id") or "")
            body = str(m.get("content") or "")

            if "[无异议]" in body:
                no_obj_seats.append(sp_name)

            if "[修正原方案" in body:
                revised_count += 1
                for d_ex in dis_list:
                    if isinstance(d_ex, dict) and d_ex.get("target") == sp and not d_ex.get("resolved"):
                        d_ex["rebuttal_msg_id"] = mid
                        d_ex["stance_delta"] = "revised"
                        d_ex["resolved"] = True

            if "[放弃原方案" in body:
                abandoned_count += 1
                for d_ex in dis_list:
                    if isinstance(d_ex, dict) and d_ex.get("target") == sp and not d_ex.get("resolved"):
                        d_ex["rebuttal_msg_id"] = mid
                        d_ex["stance_delta"] = "abandoned"
                        d_ex["resolved"] = True

            matched_explicit = list(rebut_re.finditer(body))
            if matched_explicit:
                for rm in matched_explicit:
                    raw_tgt = rm.group(1).strip().lower()
                    tgt_aid = name_to_aid.get(raw_tgt) or str(m.get("target") or "")
                    if tgt_aid not in AGENT_META or tgt_aid == sp:
                        tgt_aid = next((a for a in active_agents if a != sp), "")
                    claim_s = self._smart_clip(rm.group(2).strip(), limit=160)
                    d_obj = {
                        "disagreement_id": f"d_{uuid.uuid4().hex[:8]}",
                        "round_label": round_label,
                        "challenger": sp,
                        "challenger_name": sp_name,
                        "target": tgt_aid,
                        "target_name": self._seat_name(sess, tgt_aid) if tgt_aid in AGENT_META else raw_tgt,
                        "claim": claim_s,
                        "source_msg_id": mid,
                        "rebuttal_msg_id": "",
                        "stance_delta": "challenged",
                        "resolved": False,
                    }
                    dis_list.append(d_obj)
                    created_in_round.append(d_obj)
            elif m.get("target") in active_agents and m.get("target") != sp and m.get("consensus") is False:
                tgt_aid = str(m["target"])
                pts = self._extract_key_points(body, max_items=1)
                claim_s = pts[0] if pts else f"{sp_name} 对 {self._seat_name(sess, tgt_aid)} 提出边界质疑"
                d_obj = {
                    "disagreement_id": f"d_{uuid.uuid4().hex[:8]}",
                    "round_label": round_label,
                    "challenger": sp,
                    "challenger_name": sp_name,
                    "target": tgt_aid,
                    "target_name": self._seat_name(sess, tgt_aid),
                    "claim": claim_s,
                    "source_msg_id": mid,
                    "rebuttal_msg_id": "",
                    "stance_delta": "challenged",
                    "resolved": False,
                }
                dis_list.append(d_obj)
                created_in_round.append(d_obj)

        if created_in_round or revised_count or abandoned_count or no_obj_seats:
            summary_entry = {
                "id": f"rs_{uuid.uuid4().hex[:6]}",
                "round_label": round_label,
                "after_msg_id": str(round_msgs[-1].get("id") or "") if round_msgs else "",
                "new_disagreements": len(created_in_round),
                "revised_count": revised_count,
                "abandoned_count": abandoned_count,
                "no_objection_seats": no_obj_seats,
                "claims": [f"{d['challenger_name']} → {d['target_name']}：{d['claim']}" for d in created_in_round[:3]],
            }
            sess.whiteboard.setdefault("round_summaries", []).append(summary_entry)
        return created_in_round

    def _collect_unanswered_rebuttal_targets(
        self,
        cross_msgs: List[dict],
        active_agents: List[str],
        sess: Optional[MeetingSession] = None,
    ) -> Dict[str, List[str]]:
        """
        检查本轮质询输出中的被点名席位（target 及正文 @席位名）：
        若某启用席位被其他席位点名质询，且未在该条质询完成后启动后续发言予以回应，
        返回 {被点名席位ID: [发起质询的席位名称列表]}。
        """
        pending: Dict[str, List[str]] = {}
        name_to_aid = {
            "carbon": "carbon",
            "grok": "grok",
            "astra": "astra",
        }
        for aid_k in AGENT_ORDER:
            name_to_aid[aid_k] = aid_k
            sname = self._seat_name(sess, aid_k)
            if sname:
                name_to_aid[sname.strip().lower()] = aid_k

        for cm in cross_msgs:
            if not isinstance(cm, dict) or cm.get("error") or cm.get("skipped"):
                continue
            challenger_aid = str(cm.get("speaker") or "").lower()
            if challenger_aid not in AGENT_META:
                continue
            challenger_name = self._seat_name(sess, challenger_aid)
            cm_done_seq = int(cm.get("_done_seq") or 0)

            mentioned_aids: List[str] = []
            primary_tgt = str(cm.get("target") or "").strip().lower()
            if primary_tgt in active_agents and primary_tgt != challenger_aid:
                mentioned_aids.append(primary_tgt)
            body_txt = str(cm.get("content") or "")
            alias_keys = sorted((k for k in name_to_aid.keys() if len(k) >= 2), key=len, reverse=True)
            if alias_keys:
                alias_pat = "|".join(re.escape(k) for k in alias_keys)
                for raw_m in re.findall(rf"@({alias_pat})(?![A-Za-z0-9_])", body_txt, flags=re.IGNORECASE):
                    m_aid = name_to_aid.get(raw_m.lower())
                    if m_aid in active_agents and m_aid != challenger_aid and m_aid not in mentioned_aids:
                        mentioned_aids.append(m_aid)

            for tgt_aid in mentioned_aids:
                # 若被点名席位在该质询完成后已经开启过新一轮发言，则视为已在后半段回应
                already_replied = any(
                    isinstance(later_m, dict)
                    and later_m.get("speaker") == tgt_aid
                    and not later_m.get("error")
                    and not later_m.get("skipped")
                    and cm_done_seq > 0
                    and int(later_m.get("_start_seq") or 0) > cm_done_seq
                    for later_m in cross_msgs
                )
                if not already_replied:
                    challengers_for_tgt = pending.setdefault(tgt_aid, [])
                    if challenger_name not in challengers_for_tgt:
                        challengers_for_tgt.append(challenger_name)
        return pending

    async def _orchestrate_full_meeting(self, sess: MeetingSession) -> None:
        owner_task = asyncio.current_task()
        try:
            ready_agents, missing_agents = self._get_ready_enabled_agents(sess)
            if not ready_agents:
                missing_names = "、".join(
                    f"{self._seat_name(sess, a)} ({AGENT_META[a]['cli']})" for a in (missing_agents or sess.enabled_agents)
                )
                await self._append_non_agent_message(
                    sess,
                    speaker="system",
                    speaker_name="环境提示",
                    role_title="CLI 检测",
                    phase_label="未就绪",
                    content=(
                        f"当前参会席位均未检测到可用的本地 CLI：{missing_names}。\n"
                        f"请点击左侧栏设置图标指定可执行文件路径（或启用「单引擎多角色串行模式」），完成后点击 **「连通性实测」**。"
                    ),
                    badge="需配置 CLI",
                    error=True,
                )
                await self._finalize_task_idle_state(sess, owner_task)
                await self._set_stage(sess, "idle", "CLI 未就绪，请检查配置")
                return

            if missing_agents:
                skipped_str = "、".join(f"{self._seat_name(sess, a)}" for a in missing_agents)
                for ma in missing_agents:
                    self._record_absent_seat(
                        sess,
                        ma,
                        reason="未检测到本地 CLI 可执行文件",
                        error_kind="binary_missing",
                        phase="开局检测",
                        abnormal=True,
                    )
                    await self._set_seat(sess, ma, "idle", "未安装 · 记入缺席")
                await self.broadcast(sess, "whiteboard_update", sess.whiteboard)
                await self._append_non_agent_message(
                    sess,
                    speaker="system",
                    speaker_name="系统",
                    role_title="席位调度",
                    phase_label="缺席披露",
                    content=f"已将未检测到本地 CLI 的启用席位（{skipped_str}）记入白板「未参评/缺席席位」账本，由其余已就绪成员继续推进研讨。",
                    badge="缺席留痕",
                )

            mode_key = sess.collab_mode if sess.collab_mode in COLLAB_MODES else "deep_deliberation"
            solo_mode = len(ready_agents) == 1
            active_agents: List[str] = []
            failed_agents: List[str] = []

            if solo_mode:
                solo_aid = ready_agents[0]
                solo_name = self._seat_name(sess, solo_aid)
                await self._set_stage(sess, "opening_parallel", f"第 1 阶段：{solo_name} 单席深度方案设计")
                ok_solo, _, solo_badge, _ = await self._run_single_agent_turn(
                    sess,
                    solo_aid,
                    "opening",
                    "深度设计",
                    is_solo_mode=True,
                )
                if ok_solo:
                    active_agents = [solo_aid]
                    if mode_key != "rapid_consensus":
                        await self._set_stage(sess, "cross_talk", f"第 2 阶段：{solo_name} 边界自检与收敛")
                        await self._run_single_agent_turn(
                            sess,
                            solo_aid,
                            "solo_audit",
                            "边界自检",
                            is_solo_mode=True,
                        )
                elif solo_badge != "已跳过本轮":
                    failed_agents = [solo_aid]

            elif mode_key == "adversarial_review":
                # 正反辩证（非对称 4 步拓扑）：正方立论 -> 反向审计 -> 防御修正 -> 综合裁定
                proposer, auditor, arbiter = self._pick_adversarial_roles(sess, ready_agents)
                prop_name = self._seat_name(sess, proposer)
                aud_name = self._seat_name(sess, auditor)
                arb_name = self._seat_name(sess, arbiter)

                await self._set_stage(sess, "opening_parallel", f"正反辩证 ①：{prop_name} 主方案立论")
                ok_prop, _, prop_badge, _ = await self._run_single_agent_turn(
                    sess,
                    proposer,
                    "adv_propose",
                    "正方立论",
                )
                if ok_prop:
                    active_agents.append(proposer)
                elif prop_badge != "已跳过本轮":
                    failed_agents.append(proposer)

                # 若首选正方失败，尝试由其余席位递补或中止
                if not ok_prop:
                    backup_props = [a for a in ready_agents if a not in (proposer, auditor)]
                    if backup_props:
                        proposer = backup_props[0]
                        prop_name = self._seat_name(sess, proposer)
                        ok_prop, _, _, _ = await self._run_single_agent_turn(
                            sess,
                            proposer,
                            "adv_propose",
                            "正方立论",
                        )
                        if ok_prop:
                            active_agents.append(proposer)

                if ok_prop:
                    await self._set_stage(sess, "cross_talk", f"正反辩证 ②：{aud_name} 反向压力审计")
                    ok_aud, _, aud_badge, _ = await self._run_single_agent_turn(
                        sess,
                        auditor,
                        "adv_attack",
                        "反向审计",
                    )
                    if ok_aud:
                        if auditor not in active_agents:
                            active_agents.append(auditor)
                        await self._set_stage(sess, "cross_talk", f"正反辩证 ③：{prop_name} 防御修正")
                        await self._run_single_agent_turn(
                            sess,
                            proposer,
                            "adv_defend",
                            "防御修正",
                        )
                    elif aud_badge != "已跳过本轮":
                        failed_agents.append(auditor)

                    eff_arbiter = arbiter if (arbiter in ready_agents and arbiter not in failed_agents) else proposer
                    await self._set_stage(sess, "cross_talk", f"正反辩证 ④：{self._seat_name(sess, eff_arbiter)} 综合裁定")
                    ok_arb, _, arb_badge, _ = await self._run_single_agent_turn(
                        sess,
                        eff_arbiter,
                        "adv_verdict",
                        "综合裁定",
                    )
                    if ok_arb and eff_arbiter not in active_agents:
                        active_agents.append(eff_arbiter)
                    elif not ok_arb and arb_badge != "已跳过本轮" and eff_arbiter not in failed_agents:
                        failed_agents.append(eff_arbiter)

            elif mode_key == "divergent_convergent":
                # 发散收敛：第 1 轮三维度互斥正交发散 -> 第 2 轮三维矩阵评估与优选方案收敛
                orthogonal_dims = [
                    "请聚焦维度一【架构/体验突破性方案】：跳出局部修补惯性，提出上限最高的结构性重塑或交互创新路径。",
                    "请聚焦维度二【最小改动渐进方案】：严格控制改动半径与回归面，提出最快可落地、低侵入的渐进实施路径。",
                    "请聚焦维度三【高复用模块化方案】：聚焦抽象解耦、契约边界与长期可维护性，提出高内聚可扩展方案。",
                ]
                div_cues = {
                    aid: orthogonal_dims[idx % len(orthogonal_dims)]
                    for idx, aid in enumerate(ready_agents)
                }
                await self._set_stage(sess, "opening_parallel", "第 1 轮：多维正交方案发散")
                opening_outcomes = await self._run_agent_batch(
                    sess,
                    ready_agents,
                    "div_expand",
                    "正交发散",
                    cue_by_agent=div_cues,
                )
                active_agents = [aid for aid, (ok, _, _, _) in zip(ready_agents, opening_outcomes) if ok]
                failed_agents = [
                    aid for aid, (ok, _, bdg, _) in zip(ready_agents, opening_outcomes) if not ok and bdg != "已跳过本轮"
                ]
                if len(active_agents) >= 2:
                    lead_agent = self._pick_lead_synthesizer(sess, active_agents) or active_agents[0]
                    evaluators = [a for a in active_agents if a != lead_agent]
                    if evaluators:
                        await self._set_stage(sess, "cross_talk", "第 2 轮：可行性与三维矩阵评估")
                        await self._run_agent_batch(sess, evaluators, "div_evaluate", "矩阵评估")
                    await self._set_stage(
                        sess,
                        "cross_talk",
                        f"第 2 轮：{self._seat_name(sess, lead_agent)} 优选方案收敛",
                    )
                    await self._run_single_agent_turn(sess, lead_agent, "div_converge", "优选收敛")

            elif mode_key == "code_review":
                # 代码审查：第 1 轮源码证据定位 -> 第 2 轮调用链交叉核验 -> 文件级修改方案
                await self._set_stage(sess, "opening_parallel", "第 1 轮：源码证据与耦合根因定位")
                opening_outcomes = await self._run_agent_batch(
                    sess,
                    ready_agents,
                    "cr_locate",
                    "源码定位",
                )
                active_agents = [aid for aid, (ok, _, _, _) in zip(ready_agents, opening_outcomes) if ok]
                failed_agents = [
                    aid for aid, (ok, _, bdg, _) in zip(ready_agents, opening_outcomes) if not ok and bdg != "已跳过本轮"
                ]
                if len(active_agents) >= 2:
                    lead_agent = self._pick_lead_synthesizer(sess, active_agents)
                    if not lead_agent:
                        lead_agent = "astra" if "astra" in active_agents else active_agents[0]
                    verifiers = [a for a in active_agents if a != lead_agent]
                    if verifiers:
                        await self._set_stage(sess, "cross_talk", "第 2 轮：调用链影响面与回归交叉核验")
                        await self._run_agent_batch(sess, verifiers, "cr_verify", "调用链核验")
                    await self._set_stage(
                        sess,
                        "cross_talk",
                        f"第 2 轮：{self._seat_name(sess, lead_agent)} 文件级修改方案",
                    )
                    await self._run_single_agent_turn(sess, lead_agent, "cr_plan", "修改方案")

            elif mode_key == "rapid_consensus":
                # 快速合议：1 轮并行直出改造要点与核心风险 -> 仅在存在分歧或缺少任务项且未开启自动决议时追加整合
                await self._set_stage(sess, "opening_parallel", "快速合议：单轮要点与风险直出")
                opening_outcomes = await self._run_agent_batch(
                    sess,
                    ready_agents,
                    "rapid_open",
                    "要点直出",
                )
                active_agents = [aid for aid, (ok, _, _, _) in zip(ready_agents, opening_outcomes) if ok]
                failed_agents = [
                    aid for aid, (ok, _, bdg, _) in zip(ready_agents, opening_outcomes) if not ok and bdg != "已跳过本轮"
                ]
                has_disagreement = any(cons is False for (_, _, _, cons) in opening_outcomes)
                wb_items_now = sess.whiteboard.get("items") or []
                has_action_items = any(isinstance(it, dict) and it.get("kind") == "action" for it in wb_items_now)
                need_align_turn = len(active_agents) >= 2 and not sess.auto_preview_exec and (
                    has_disagreement or not has_action_items
                )
                if need_align_turn:
                    lead_agent = self._pick_lead_synthesizer(sess, active_agents) or active_agents[0]
                    await self._set_stage(
                        sess,
                        "cross_talk",
                        f"快速合议：{self._seat_name(sess, lead_agent)} 生成执行清单",
                    )
                    await self._run_single_agent_turn(sess, lead_agent, "rapid_align", "执行清单")

            else:
                # 默认：深度研讨（deep_deliberation）
                # 阶段 1：独立立论 -> 阶段 2：交叉质询（证伪审计协议）-> 定向答辩（最多 1 批次）-> 主控架构裁定
                drv_groups, _, _ = self._resolve_driver_groups(sess, ready_agents)
                is_single_cli_multi = len(drv_groups) == 1 and len(ready_agents) > 1
                stage_banner = (
                    f"第 1 阶段：单引擎多角色串行立论（{len(ready_agents)} 席）"
                    if is_single_cli_multi
                    else f"第 1 阶段：{len(ready_agents)} 席独立立论"
                )
                await self._set_stage(sess, "opening_parallel", stage_banner)
                opening_outcomes = await self._run_agent_batch(
                    sess,
                    ready_agents,
                    "opening",
                    "独立立论",
                    is_solo_mode=False,
                )
                active_agents = [aid for aid, (ok, _, _, _) in zip(ready_agents, opening_outcomes) if ok]
                failed_agents = [
                    aid for aid, (ok, _, bdg, _) in zip(ready_agents, opening_outcomes) if not ok and bdg != "已跳过本轮"
                ]

                if len(active_agents) >= 2:
                    lead_agent = self._pick_lead_synthesizer(sess, active_agents) or active_agents[0]
                    cross_start_idx = len(sess.messages)
                    await self._set_stage(sess, "cross_talk", "第 2 阶段：交叉质询与边界证伪审计")
                    await self._run_agent_batch(
                        sess,
                        active_agents,
                        "cross_talk",
                        "交叉质询",
                    )

                    cross_msgs = sess.messages[cross_start_idx:]
                    new_disagreements = self._analyze_round_disagreements_and_abandonments(
                        sess,
                        cross_msgs,
                        active_agents,
                        "第 2 阶段 · 交叉质询",
                    )
                    unanswered_map = self._collect_unanswered_rebuttal_targets(cross_msgs, active_agents, sess=sess)
                    all_no_objection = bool(cross_msgs) and not unanswered_map and not new_disagreements and all(
                        ("[无异议]" in str(m.get("content") or "")) or (m.get("consensus") is True)
                        for m in cross_msgs
                        if isinstance(m, dict) and not m.get("error") and not m.get("skipped")
                    )
                    if unanswered_map:
                        rebuttal_order = [a for a in active_agents if a in unanswered_map]
                        rebuttal_cues = {
                            tgt_aid: (
                                f"本轮交叉质询中，{'、'.join(challengers)} 对你提出了定向质询。"
                                f"请正面回应其指出的漏洞、前提失效点或代价权衡，给出具体修正方案（标注 `[修正原方案：...]` / `[放弃原方案：...]`）或量化反证。"
                            )
                            for tgt_aid, challengers in unanswered_map.items()
                        }
                        rebuttal_names = "、".join(self._seat_name(sess, a) for a in rebuttal_order)
                        reb_start_idx = len(sess.messages)
                        await self._set_stage(sess, "cross_talk", f"第 2 阶段：{rebuttal_names} 定向答辩")
                        await self._run_agent_batch(
                            sess,
                            rebuttal_order,
                            "rebuttal",
                            "定向答辩",
                            cue_by_agent=rebuttal_cues,
                        )
                        self._analyze_round_disagreements_and_abandonments(
                            sess,
                            sess.messages[reb_start_idx:],
                            rebuttal_order,
                            "第 2 阶段 · 定向答辩",
                        )

                    if not all_no_objection:
                        await self._set_stage(
                            sess,
                            "cross_talk",
                            f"第 2 阶段：{self._seat_name(sess, lead_agent)} 分歧裁定与推进方案",
                        )
                        await self._run_single_agent_turn(
                            sess,
                            lead_agent,
                            "lead_synthesis",
                            "架构裁定",
                        )

            if not active_agents:
                await self._finalize_task_idle_state(sess, owner_task)
                await self._set_stage(sess, "awaiting_chair", "本轮未生成有效发言，请查看卡片详情或选择恢复重试")
                return

            if sess.auto_preview_exec and active_agents:
                exec_aid = sess.effective_executor_agent()
                if exec_aid not in active_agents:
                    exec_aid = active_agents[-1]
                last_valid_msg = next(
                    (m for m in reversed(sess.messages) if not m.get("error") and not m.get("skipped") and m.get("content")),
                    None,
                )
                already_converged = bool(
                    last_valid_msg
                    and last_valid_msg.get("phase_label") in ("架构裁定", "综合裁定", "优选收敛", "修改方案", "执行清单", "边界自检")
                )
                if already_converged:
                    await self.update_whiteboard_manual(sess, {"op": "import_resolution", "message_id": last_valid_msg["id"]})
                else:
                    await self._finalize_consensus_internal(sess, clear_task_on_exit=False)

                checked_cnt = sum(
                    1
                    for it in (sess.whiteboard.get("items") or [])
                    if isinstance(it, dict) and it.get("kind") == "action" and bool(it.get("checked", False))
                )
                if checked_cnt >= 1 and sess.artifact_type == "code_patch":
                    await self._execute_agent_internal(
                        sess,
                        allow_workspace_write=False,
                        executor_id=exec_aid,
                        clear_task_on_exit=True,
                    )
                else:
                    await self._finalize_task_idle_state(sess, owner_task)
                    await self._set_stage(sess, "concluded", "已收敛决议清单 · 请在白板核对并勾选待执行任务后启动预演")
            else:
                await self._finalize_task_idle_state(sess, owner_task)
                exec_name = self._seat_name(sess, sess.effective_executor_agent())
                if failed_agents:
                    failed_names = "、".join(self._seat_name(sess, a) for a in failed_agents)
                    status_hint = f"本轮已结束（{failed_names} 未完成发言已记入缺席账本，支持就地重试），待主持人推进"
                elif len(active_agents) == 1 and solo_mode:
                    status_hint = f"单席推演草稿已就绪，可继续追问或勾选任务后交由 {exec_name} 执行"
                else:
                    status_hint = "研讨完成，待主持人形成决议或定向追问"
                await self._set_stage(sess, "awaiting_chair", status_hint)
        except asyncio.CancelledError:
            raise
        finally:
            await self._finalize_task_idle_state(sess, owner_task)
            self._save_persisted_sessions(immediate=True)
            await self._broadcast_meta(sess)

    async def chair_interrupt(
        self,
        sess: MeetingSession,
        message: str,
        attachments: Optional[List[dict]] = None,
    ) -> None:
        clean_msg = message.strip()
        if not clean_msg:
            return
        was_busy = sess.is_busy
        await self.cancel_active_flow(sess, reason_tag="主持人插话" if was_busy else "补充追问")
        if not sess.topic:
            await self.start_topic_meeting(sess, clean_msg, attachments=attachments)
            return

        if attachments:
            cur_atts = list(sess.whiteboard.get("session_attachments") or [])
            seen_ids = {x.get("id") for x in cur_atts if isinstance(x, dict)}
            for att in attachments:
                if isinstance(att, dict) and att.get("id") and att["id"] not in seen_ids:
                    seen_ids.add(att["id"])
                    cur_atts.append(att)
            sess.whiteboard["session_attachments"] = cur_atts

        chair_msg = await self._append_non_agent_message(
            sess,
            speaker="chair",
            speaker_name="主持人",
            role_title="插话控场" if was_busy else "补充追问",
            phase_label="插话" if was_busy else "追问",
            content=clean_msg,
            badge="新约束" if was_busy else "继续讨论",
            attachments=attachments,
        )

        wb = _normalize_and_sync_whiteboard(sess.whiteboard, topic=sess.topic, messages=sess.messages)
        deduped_c = dedupe_chair_constraints(
            sess.topic,
            wb.get("topic_title", ""),
            list(wb.get("chair_constraints", [])) + [self._smart_clip(clean_msg, limit=180)],
        )
        items = wb.setdefault("items", [])
        existing_norms = {_norm_dedupe_key(str(it.get("text") or "")) for it in items if isinstance(it, dict)}
        wb_mutated = False
        for c_txt in deduped_c:
            cnk = _norm_dedupe_key(c_txt)
            if cnk and cnk not in existing_norms:
                ordinal = int(wb.get("wb_version") or 1) + len(items) + 1
                items.insert(
                    0,
                    {
                        "id": make_deterministic_wb_id("chair_constraints", ordinal, c_txt),
                        "kind": "decision",
                        "text": c_txt,
                        "author": "chair",
                        "source_msg_id": chair_msg["id"],
                        "pinned": True,
                        "checked": True,
                        "ver": 1,
                    },
                )
                existing_norms.add(cnk)
                wb_mutated = True
        if wb_mutated:
            sync_whiteboard_legacy_arrays_and_caps(wb)
            wb["wb_version"] = int(wb.get("wb_version") or 1) + 1
        await self.broadcast(sess, "whiteboard_update", sess.whiteboard)

        msg_low = clean_msg.lower()
        mentioned = [
            aid
            for aid in AGENT_ORDER
            if f"@{aid}" in msg_low
            or (self._seat_name(sess, aid) and f"@{self._seat_name(sess, aid).lower()}" in msg_low)
        ]
        sess.active_task = asyncio.create_task(self._handle_interrupt_alignment(sess, mentioned))
        await self._broadcast_meta(sess)

    async def _handle_interrupt_alignment(self, sess: MeetingSession, mentioned: List[str]) -> None:
        owner_task = asyncio.current_task()
        try:
            await self._set_stage(sess, "chair_interrupt", "响应主持人指示中")
            ready_agents, _ = self._get_ready_enabled_agents(sess)
            targets = [a for a in mentioned if a in ready_agents] if mentioned else ready_agents
            if not targets and mentioned:
                # 若显式点名的席位处于暂停态但本地 CLI 就绪，也允许单轮点名响应
                targets = [a for a in mentioned if sess.seat_states.get(a, {}).get("binary_ready")]
            if not targets:
                await self._finalize_task_idle_state(sess, owner_task)
                await self._set_stage(sess, "awaiting_chair", "无可用 CLI 响应，请检查配置")
                return

            lead_agent = self._pick_lead_synthesizer(sess, targets) if not mentioned and len(targets) >= 2 else None
            if lead_agent and len(targets) >= 2:
                ok_c, _, _, _ = await self._run_single_agent_turn(sess, lead_agent, "interrupt_reply", "方案调整")
                others = [a for a in targets if a != lead_agent]
                if ok_c and others:
                    await self._run_agent_batch(sess, others, "interrupt_reply", "协同回应")
            elif len(targets) > 1:
                await self._run_agent_batch(sess, targets, "interrupt_reply", "定向回应")
            else:
                await self._run_single_agent_turn(
                    sess,
                    targets[0],
                    "interrupt_reply",
                    "定向回应",
                    is_solo_mode=len(ready_agents) == 1,
                )
            await self._finalize_task_idle_state(sess, owner_task)
            await self._set_stage(sess, "awaiting_chair", "已完成回应，待主持人决议")
        except asyncio.CancelledError:
            raise
        finally:
            await self._finalize_task_idle_state(sess, owner_task)
            self._save_persisted_sessions(immediate=True)
            await self._broadcast_meta(sess)

    async def cue_agent(self, sess: MeetingSession, agent_id: str, instruction: str) -> None:
        if agent_id not in AGENT_META:
            return
        await self.cancel_active_flow(sess, reason_tag=f"定向追问 {self._seat_name(sess, agent_id)}")
        if not sess.topic:
            sess.topic = instruction.strip() or "专项研讨"
            short_t, _ = summarize_topic_and_constraints(sess.topic)
            sess.title = short_t or (sess.topic[:24] + ("…" if len(sess.topic) > 24 else ""))
            sess.whiteboard["topic"] = sess.topic
            sess.whiteboard["topic_title"] = sess.title
            await self.broadcast(sess, "whiteboard_update", sess.whiteboard)
        await self._append_non_agent_message(
            sess,
            speaker="chair",
            speaker_name="主持人",
            role_title="定向提问",
            phase_label="点名",
            content=f"@{self._seat_name(sess, agent_id)} {instruction}",
        )
        sess.active_task = asyncio.create_task(self._run_cue_flow(sess, agent_id, instruction))
        await self._broadcast_meta(sess)

    async def _run_cue_flow(self, sess: MeetingSession, agent_id: str, instruction: str) -> None:
        owner_task = asyncio.current_task()
        try:
            await self._set_stage(sess, "chair_interrupt", f"{self._seat_name(sess, agent_id)} 专项回应中")
            await self._run_single_agent_turn(
                sess,
                agent_id,
                "cue",
                "专项回应",
                cue_instruction=instruction,
                is_solo_mode=len(sess.enabled_agents) == 1,
            )
            await self._finalize_task_idle_state(sess, owner_task)
            await self._set_stage(sess, "awaiting_chair", "待主持人下一步指令")
        except asyncio.CancelledError:
            raise
        finally:
            await self._finalize_task_idle_state(sess, owner_task)
            self._save_persisted_sessions(immediate=True)
            await self._broadcast_meta(sess)

    async def redebate_disagreement(self, sess: MeetingSession, payload: dict) -> dict:
        """
        围绕指定分歧项（disagreement_id 或白板 risk item_id）发起双席 1 轮定向再辩（P2 T7）：
        仅调度争议关联的两个就绪席位正面交锋 1 轮，自动更新分歧账本与弃案清单。
        """
        if sess.is_busy or sess.exec_state != "idle":
            raise ExecutionAdmissionConflictError(
                "当前会话正在运行中，请待本轮发言结束后再发起双席定向再辩",
                status_code=409,
                details={"reason": "session_busy"},
            )
        ready_agents, _ = self._get_ready_enabled_agents(sess)
        if len(ready_agents) < 2:
            raise ExecutionAdmissionConflictError(
                "双席定向再辩至少需要 2 位已就绪的启用席位",
                status_code=409,
                details={"reason": "insufficient_ready_seats"},
            )

        dis_id = str(payload.get("disagreement_id") or "").strip()
        item_id = str(payload.get("item_id") or "").strip()
        claim_txt = str(payload.get("claim") or "").strip()
        challenger = str(payload.get("challenger") or "").strip().lower()
        defender = str(payload.get("defender") or "").strip().lower()

        dis_obj: Optional[dict] = None
        for d in sess.whiteboard.get("disagreements") or []:
            if isinstance(d, dict) and dis_id and d.get("disagreement_id") == dis_id:
                dis_obj = d
                break
        target_wb_item: Optional[dict] = None
        for it in sess.whiteboard.get("items") or []:
            if isinstance(it, dict) and item_id and it.get("id") == item_id:
                target_wb_item = it
                break

        if dis_obj:
            claim_txt = claim_txt or str(dis_obj.get("claim") or "")
            challenger = challenger or str(dis_obj.get("challenger") or "")
            defender = defender or str(dis_obj.get("target") or "")
        elif target_wb_item:
            claim_txt = claim_txt or str(target_wb_item.get("text") or "")
            item_author = str(target_wb_item.get("author") or "")
            if item_author in ready_agents:
                challenger = challenger or item_author

        if not claim_txt:
            raise ValueError("缺少再辩争议焦点内容（claim / item_id / disagreement_id）")

        if challenger not in ready_agents:
            challenger = next((a for a in ready_agents if sess.seat_personas.get(a) == "red_team"), ready_agents[0])
        if defender not in ready_agents or defender == challenger:
            defender = next((a for a in ready_agents if a != challenger), ready_agents[-1])

        async def _run_redebate_flow() -> None:
            owner_task = asyncio.current_task()
            try:
                c_name = self._seat_name(sess, challenger)
                d_name = self._seat_name(sess, defender)
                await self._set_stage(sess, "cross_talk", f"焦点再辩：{c_name} ⇄ {d_name}（1 轮定向交锋）")
                start_idx = len(sess.messages)
                ok1, _, _, _ = await self._run_single_agent_turn(
                    sess,
                    challenger,
                    "redebate",
                    "焦点再辩",
                    cue_instruction=f"争议焦点：「{claim_txt}」。请向 @{d_name} 给出最核心的证伪判据、边界条件或量化取舍要求。",
                )
                if ok1:
                    await self._run_single_agent_turn(
                        sess,
                        defender,
                        "redebate",
                        "焦点再辩",
                        cue_instruction=f"争议焦点：「{claim_txt}」。请正面回应 @{c_name} 的判据，直接给出最终修正契约（`[修正原方案：...]` / `[放弃原方案：...]`）或反证结论。",
                    )
                new_msgs = sess.messages[start_idx:]
                self._analyze_round_disagreements_and_abandonments(sess, new_msgs, [challenger, defender], "双席再辩")
                if dis_obj is not None:
                    dis_obj["resolved"] = True
                    dis_obj["stance_delta"] = "redebated"
                if target_wb_item is not None:
                    target_wb_item["rebutted"] = True
                    target_wb_item["ver"] = int(target_wb_item.get("ver") or 1) + 1
                await self.broadcast(sess, "whiteboard_update", sess.whiteboard)
                await self._finalize_task_idle_state(sess, owner_task)
                await self._set_stage(sess, "awaiting_chair", f"已完成 {c_name} ⇄ {d_name} 焦点再辩，待主持人形成决议")
            except asyncio.CancelledError:
                raise
            finally:
                await self._finalize_task_idle_state(sess, owner_task)
                self._save_persisted_sessions(immediate=True)
                await self._broadcast_meta(sess)

        sess.active_task = asyncio.create_task(_run_redebate_flow())
        await self._broadcast_meta(sess)
        return {
            "ok": True,
            "challenger": challenger,
            "defender": defender,
            "claim": claim_txt,
        }

    def _build_resolution_synthesis_dossier(self, sess: MeetingSession) -> Tuple[str, dict]:
        """
        全轮次讨论成果防遗漏 & 确认放弃差方案显式隔离编译器：
        扫描会话全部历史消息（零窗口截断）与结构化白板：
        1. 提取主持初始诉求、历次插话追问与 [主持指定约束]（100% 强制保留账本）；
        2. 识别所有经 [放弃原方案]、[修正原方案] 旧前缀、[白板: 弃案=...] 及主持明确否决淘汰的差方案，写入 abandoned_proposals；
        3. 按轮次与席位汇总经质询存活/修正演进后的有效技术结论、风险护栏与具体行动项，剔除已被弃案覆盖的旧提议；
        4. 返回可供 synthesis 模型精准收敛的结构化档案文本与统计元数据 resolution_meta。
        """
        wb = _normalize_and_sync_whiteboard(sess.whiteboard, topic=sess.topic, messages=sess.messages)
        self._refresh_epistemic_status(sess)

        chair_hard_list: List[str] = []
        seen_chair: Set[str] = set()

        def _add_chair(txt_c: str) -> None:
            s_c = self._smart_clip(str(txt_c or "").strip(), limit=220)
            nk_c = _norm_dedupe_key(s_c)
            if s_c and nk_c and nk_c not in seen_chair:
                seen_chair.add(nk_c)
                chair_hard_list.append(s_c)

        for c0 in wb.get("chair_constraints") or []:
            _add_chair(c0)
        for it0 in wb.get("items") or []:
            if isinstance(it0, dict) and (it0.get("author") == "chair" or it0.get("origin_tier") == "chair_directive"):
                _add_chair(it0.get("text", ""))

        # 扫描全量发言：收集主持追问、弃案声明、修正演进链与各席分阶段核心产出
        abandon_tag_re = re.compile(r"\[(?:放弃原方案|淘汰方案|废弃方案|弃案)[:：]\s*([^\]]+)\]")
        revise_tag_re = re.compile(r"\[修正原方案[:：]\s*([^\]]+)\]")
        chair_veto_re = re.compile(r"(?:明确放弃|确认放弃|不要采用|禁止采用|否决|砍掉|剔除方案)[:：]?\s*([^。；\n]{4,100})")

        covered_rounds: List[str] = []
        covered_seats: List[str] = []
        round_outcomes_by_seat: List[str] = []
        revised_highlights: List[str] = []

        for m in sess.messages:
            if not isinstance(m, dict) or m.get("error") or m.get("skipped"):
                continue
            sp = str(m.get("speaker") or "")
            sp_name = str(m.get("speaker_name") or sp)
            ph = str(m.get("phase_label") or "")
            body = str(m.get("content") or "").strip()
            mid = str(m.get("id") or "")
            if not body or sp == "system" or ph == "最终决议":
                continue

            if ph and ph not in covered_rounds:
                covered_rounds.append(ph)

            if sp == "chair":
                if ph in ("插话", "追问"):
                    _add_chair(f"[{ph}] {body}")
                for vm in chair_veto_re.finditer(body):
                    self._record_abandoned_proposal(
                        sess,
                        vm.group(1),
                        author="chair",
                        reason="主持人明确否决/剔除",
                        round_phase=ph or "主持控场",
                        source_msg_id=mid,
                    )
                continue

            if sp in AGENT_META and sp_name not in covered_seats:
                covered_seats.append(sp_name)

            for am in abandon_tag_re.finditer(body):
                self._record_abandoned_proposal(
                    sess,
                    am.group(1),
                    author=sp,
                    reason=f"{sp_name} 在「{ph}」阶段确认放弃/证伪淘汰",
                    round_phase=ph,
                    source_msg_id=mid,
                )

            for rm in revise_tag_re.finditer(body):
                rev_raw = rm.group(1).strip()
                if "->" in rev_raw or "→" in rev_raw:
                    parts = re.split(r"->|→", rev_raw, maxsplit=1)
                    old_part, new_part = parts[0].strip(), parts[1].strip()
                    if len(old_part) >= 4:
                        self._record_abandoned_proposal(
                            sess,
                            old_part,
                            author=sp,
                            reason=f"已被 {sp_name} 修正后终态方案（「{self._smart_clip(new_part, 60)}」）替代",
                            round_phase=ph,
                            source_msg_id=mid,
                        )
                    if new_part:
                        revised_highlights.append(f"  · [{sp_name} · {ph} · 修正终态] {self._smart_clip(new_part, 200)}")
                else:
                    revised_highlights.append(f"  · [{sp_name} · {ph} · 修正终态] {self._smart_clip(rev_raw, 200)}")

            clean_b, tail_typed = parse_structured_tail_with_kinds(body)
            pts_for_msg: List[str] = []
            for ti in tail_typed:
                tk = str(ti.get("kind") or "")
                tt = str(ti.get("text") or "").strip()
                if not tt:
                    continue
                if tk == "abandoned":
                    self._record_abandoned_proposal(
                        sess,
                        tt,
                        author=sp,
                        reason=f"{sp_name} 结构化标记淘汰",
                        round_phase=ph,
                        source_msg_id=mid,
                    )
                else:
                    pts_for_msg.append(f"({tk}) {tt}")
            if not pts_for_msg:
                for kp in self._extract_key_points(clean_b, max_items=3):
                    pts_for_msg.append(kp)
            if pts_for_msg:
                round_outcomes_by_seat.append(
                    f"  · [{ph} · {sp_name}] " + "；".join(self._smart_clip(x, 150) for x in pts_for_msg[:4])
                )

        abandoned_list = [x for x in (wb.get("abandoned_proposals") or []) if isinstance(x, dict) and str(x.get("text") or "").strip()]
        abandoned_norm_set = {_norm_dedupe_key(str(x.get("text") or "")) for x in abandoned_list}

        # 过滤掉任何命中弃案哈希的旧轮次摘录，确保只向决议模型喂入存活成果 + 显式负面清单
        surviving_outcomes: List[str] = []
        for line_o in round_outcomes_by_seat:
            if any(ab_k and len(ab_k) >= 8 and ab_k in _norm_dedupe_key(line_o) for ab_k in abandoned_norm_set):
                continue
            surviving_outcomes.append(line_o)

        absent_list = [x for x in (wb.get("absent_seats") or []) if isinstance(x, dict)]
        epi_badge = str(wb.get("epistemic_badge") or "[同源模型多视角推演 · 误差相关]")

        dossier_parts: List[str] = [
            "【全轮次会议成果与废案隔离审计档案（系统自动汇编 · 严禁遗漏存活项、严禁回流弃案）】：",
            f"- 认知独立性标记：{epi_badge}",
            f"- 覆盖研讨阶段：{' → '.join(covered_rounds) if covered_rounds else '直接汇总'}",
            f"- 实际参评席位：{'、'.join(covered_seats) if covered_seats else '暂无席位发言'}",
        ]
        if absent_list:
            absent_desc = "；".join(f"{a.get('seat_name')}（{a.get('reason')}）" for a in absent_list)
            dossier_parts.append(f"- 未参评/缺席席位（须在第三节如实披露）：{absent_desc}")
        if chair_hard_list:
            dossier_parts.append("1) 主持人硬约束与历次追问诉求（100% 强制保留）：\n" + "\n".join(f"  · {c}" for c in chair_hard_list[:24]))
        if revised_highlights:
            dossier_parts.append("2) 经质询答辩演进后的终态修正方案（优先采纳终态，勿回退初版草案）：\n" + "\n".join(revised_highlights[:20]))
        if surviving_outcomes:
            dossier_parts.append("3) 各轮次存活核心结论与行动建议索引（须全量核对吸纳）：\n" + "\n".join(surviving_outcomes[:36]))
        if abandoned_list:
            dossier_parts.append(
                "4) 已确认放弃 / 证伪淘汰差方案负面清单（严禁混入采纳结论或执行任务，须单独列入第二节）：\n"
                + "\n".join(
                    f"  · [淘汰] {ab['text']}（来源：{ab.get('seat_name', '')} · 原因：{ab.get('reason', '证伪淘汰')}）"
                    for ab in abandoned_list[:24]
                )
            )
        else:
            dossier_parts.append("4) 已确认放弃 / 证伪淘汰差方案负面清单：当前无显式声明弃案（若讨论记录中存在被推翻的次优方案，请主动归纳至第二节）。")

        meta = {
            "epistemic_badge": epi_badge,
            "covered_rounds": covered_rounds,
            "covered_seats": covered_seats,
            "chair_constraint_count": len(chair_hard_list),
            "surviving_outcome_count": len(surviving_outcomes) + len(revised_highlights),
            "abandoned_count": len(abandoned_list),
            "absent_count": len(absent_list),
        }
        return "\n".join(dossier_parts), meta

    async def conclude_meeting(self, sess: MeetingSession) -> None:
        await self.cancel_active_flow(sess, reason_tag="形成决议")
        sess.active_task = asyncio.create_task(self._finalize_consensus_internal(sess, clear_task_on_exit=True))
        await self._broadcast_meta(sess)

    async def _finalize_consensus_internal(
        self,
        sess: MeetingSession,
        clear_task_on_exit: bool = True,
    ) -> None:
        owner_task = asyncio.current_task()
        try:
            await self._set_stage(sess, "concluded", "正在全量盘点各轮成果并剥离淘汰方案，合成《会议最终决议》…")
            dossier_block, dossier_meta = self._build_resolution_synthesis_dossier(sess)
            sess.whiteboard["_synthesis_dossier_block"] = dossier_block

            ready_agents, _ = self._get_ready_enabled_agents(sess)
            synthesizer = self._pick_lead_synthesizer(sess, ready_agents) or (ready_agents[0] if ready_agents else None)

            sec4_title = {
                "code_patch": "四、文件级待执行任务清单（模块路径 · 改动职责 · 回归验证）",
                "decision_matrix": "四、方案对比决策矩阵与落地行动清单",
                "ux_checklist": "四、产品体验分级走查与验收打磨清单",
                "doc_export": "四、根因排查闭环与结构化定稿交付清单",
            }.get(sess.artifact_type, "四、待执行交付任务清单")

            synthesized_ok = False
            res_msg_id = ""
            if synthesizer and sess.messages:
                synth_cue = (
                    "请严格依据【全轮次会议成果与废案隔离审计档案】及完整讨论记录，输出一份零遗漏、零废案回流的旗舰级《会议最终决议》：\n"
                    "## 一、已确认共识与全量采纳成果（完整保留主持约束、历次追问定论与各席经答辩修正后的终态方案）\n"
                    "## 二、已确认放弃与证伪淘汰方案（防回流负面清单：逐条列出被放弃/证伪/被替代的旧方案及淘汰理由，严禁混入任务区）\n"
                    "## 三、边界风险防线、未决争议与参会披露（含异常回退护栏、未决分歧及缺席/同源认知标记）\n"
                    f"## {sec4_title}"
                )
                ok, _, _, _ = await self._run_single_agent_turn(
                    sess,
                    synthesizer,
                    "synthesis",
                    "最终决议",
                    cue_instruction=synth_cue,
                    ingest_whiteboard=False,
                    is_solo_mode=len(ready_agents) == 1,
                )
                synthesized_ok = ok
                if ok and sess.messages:
                    res_msg_id = str(sess.messages[-1].get("id") or "")

            sess.whiteboard.pop("_synthesis_dossier_block", None)

            if synthesized_ok and res_msg_id:
                await self.update_whiteboard_manual(sess, {"op": "import_resolution", "message_id": res_msg_id})
            else:
                wb = _normalize_and_sync_whiteboard(sess.whiteboard, topic=sess.topic, messages=sess.messages)
                items = wb.get("items") or []
                ab_items = wb.get("abandoned_proposals") or []
                ab_norms = {_norm_dedupe_key(str(x.get("text") or "")) for x in ab_items if isinstance(x, dict)}
                epi_badge = str(wb.get("epistemic_badge") or "[同源模型多视角推演 · 误差相关]")
                absent_seats = [x for x in (wb.get("absent_seats") or []) if isinstance(x, dict)]

                dec_items = [
                    it for it in items
                    if isinstance(it, dict) and it.get("kind") == "decision" and _norm_dedupe_key(str(it.get("text") or "")) not in ab_norms
                ]
                prov_dec_items = [
                    it for it in items
                    if isinstance(it, dict) and it.get("provisional_decision") and _norm_dedupe_key(str(it.get("text") or "")) not in ab_norms
                ]
                risk_items = [
                    it for it in items
                    if isinstance(it, dict) and it.get("kind") == "risk" and not it.get("provisional_decision") and _norm_dedupe_key(str(it.get("text") or "")) not in ab_norms
                ]
                act_items = [
                    it for it in items
                    if isinstance(it, dict) and it.get("kind") == "action" and _norm_dedupe_key(str(it.get("text") or "")) not in ab_norms
                ]

                dec_lines = "\n".join(
                    f"- {'[主持指定约束] ' if it.get('origin_tier') == 'chair_directive' else ''}{it['text']}"
                    for it in (dec_items + prov_dec_items)
                ) or "- 暂无已锁定记录"
                ab_lines = "\n".join(
                    f"- [已淘汰] {ab['text']}（原因：{ab.get('reason', '讨论证伪淘汰')}）"
                    for ab in ab_items
                ) or "- 本场讨论无显式淘汰废案"
                disclosure_lines: List[str] = [f"- 认知独立性声明：`{epi_badge}`"]
                if absent_seats:
                    disclosure_lines.append(
                        "- 未参评/缺席席位：" + "；".join(f"{a.get('seat_name')}（{a.get('reason')}）" for a in absent_seats)
                    )
                for r_it in risk_items:
                    disclosure_lines.append(f"- {r_it['text']}")
                act_lines = "\n".join(
                    f"- [{'x' if it.get('checked', False) else ' '}] {it['text']}"
                    for it in act_items
                ) or "- 暂无待执行交付项"

                summary_md = (
                    f"# 《会议最终决议》 — {sess.title or sess.topic}\n\n"
                    f"> 认知防伪标识：`{epi_badge}` · 覆盖阶段：{' → '.join(dossier_meta['covered_rounds']) or '归档汇总'}\n\n"
                    f"## 一、已确认共识与全量采纳成果\n{dec_lines}\n\n"
                    f"## 二、已确认放弃与证伪淘汰方案（防回流负面清单）\n{ab_lines}\n\n"
                    f"## 三、边界风险防线、未决争议与参会披露\n" + "\n".join(disclosure_lines) + "\n\n"
                    f"## {sec4_title}\n{act_lines}"
                )
                fallback_msg = await self._append_non_agent_message(
                    sess,
                    speaker="system",
                    speaker_name="会议纪要",
                    role_title="决议归档",
                    phase_label="最终决议",
                    content=summary_md,
                    badge="已形成决议",
                )
                res_msg_id = str(fallback_msg.get("id") or "")

            # 更新决议全量覆盖审计元数据，供前端高密度决议卡展示
            wb_final = sess.whiteboard
            final_items = [it for it in (wb_final.get("items") or []) if isinstance(it, dict)]
            wb_final["resolution_meta"] = {
                **dossier_meta,
                "message_id": res_msg_id,
                "adopted_count": sum(1 for it in final_items if it.get("kind") == "decision" or it.get("provisional_decision")),
                "abandoned_count": len(wb_final.get("abandoned_proposals") or []),
                "risk_count": sum(1 for it in final_items if it.get("kind") == "risk" and not it.get("provisional_decision")),
                "action_count": sum(1 for it in final_items if it.get("kind") == "action"),
                "checked_action_count": sum(1 for it in final_items if it.get("kind") == "action" and it.get("checked", False)),
                "synthesized_at": now_display_time(),
            }

            if clear_task_on_exit:
                await self._finalize_task_idle_state(sess, owner_task)
            if sess.artifact_type == "code_patch":
                exec_name = self._seat_name(sess, sess.effective_executor_agent())
                await self._set_stage(sess, "concluded", f"已形成决议 · 请在白板核对勾选待执行任务后交由 {exec_name} 执行")
            else:
                art_label = SCENARIO_INTENT_PACKS.get(sess.scenario_pack, {}).get("artifact_label", "结构化纪要")
                await self._set_stage(sess, "concluded", f"已形成决议 · 可一键复制或导出《{art_label}》")
            await self.broadcast(sess, "whiteboard_update", sess.whiteboard)
        except asyncio.CancelledError:
            sess.whiteboard.pop("_synthesis_dossier_block", None)
            raise
        finally:
            sess.whiteboard.pop("_synthesis_dossier_block", None)
            if clear_task_on_exit:
                await self._finalize_task_idle_state(sess, owner_task)
                self._save_persisted_sessions(immediate=True)
                await self._broadcast_meta(sess)

    def build_session_export_bytes(self, sess: MeetingSession) -> Tuple[bytes, str]:
        """从服务端会话内存快照安全生成 Markdown 会议纪要字节流（含认知防伪徽章、缺席账本与弃案负面清单）。"""
        self._refresh_epistemic_status(sess)
        wb = sess.whiteboard or {}
        epi_mode = str(wb.get("epistemic_mode") or "homogeneous_warning")
        epi_badge = str(wb.get("epistemic_badge") or "[同源模型多视角推演 · 误差相关]")
        pack_label = SCENARIO_INTENT_PACKS.get(sess.scenario_pack, {}).get("label", "工程研发与代码审查包")

        lines: List[str] = [
            f"# 《AI圆桌》会议纪要 — {sess.title or '未命名议题'}",
            "",
            f"- **会话 ID**：`{sess.session_id}`",
            f"- **认知独立性防伪标记**：**`{epi_badge}`**",
            f"- **场景意图包**：{pack_label}（{COLLAB_MODES.get(sess.collab_mode, {}).get('label', sess.collab_mode)}）",
            f"- **启用参会席位**：{'、'.join(self._seat_name(sess, a) for a in sess.enabled_agents)}",
            f"- **导出时间**：{now_display_time()}",
            "",
        ]

        absent_seats = [x for x in (wb.get("absent_seats") or []) if isinstance(x, dict)]
        lines.extend(["## 一、未参评 / 缺席席位披露", ""])
        if absent_seats:
            for ab in absent_seats:
                lines.append(
                    f"- **{ab.get('seat_name') or ab.get('agent_id')}**：{ab.get('reason', '未完成有效发言')}（阶段：{ab.get('phase') or '会议期间'}）"
                )
        else:
            lines.append("- 全部已启用参会席位均正常完成发言，无缺席记录。")

        lines.extend([
            "",
            "## 二、研讨议题与主持约束",
            "",
            sess.topic or "（未填写议题）",
            "",
        ])
        for c in wb.get("chair_constraints") or []:
            lines.append(f"- [主持约束] {c}")
        for att in wb.get("session_attachments") or []:
            if isinstance(att, dict) and att.get("name"):
                lines.append(f"- [参考附件] {att['name']} ({att.get('size_human') or att.get('mime_type') or ''})")

        items = [it for it in (wb.get("items") or []) if isinstance(it, dict) and str(it.get("text") or "").strip()]
        decisions = [it for it in items if it.get("kind") == "decision"]
        risks = [it for it in items if it.get("kind") == "risk"]
        actions = [it for it in items if it.get("kind") == "action"]
        abandoned = [x for x in (wb.get("abandoned_proposals") or []) if isinstance(x, dict) and str(x.get("text") or "").strip()]

        sec3_heading = (
            "## 三、已确认共识与主持约束（异构独立交叉核验）"
            if epi_mode == "heterogeneous"
            else f"## 三、已锁定结论与主持约束 {epi_badge}"
        )
        lines.extend(["", sec3_heading, ""])
        if decisions:
            for it in decisions:
                tier = str(it.get("origin_tier") or "")
                prefix = "[主持指定约束] " if (tier == "chair_directive" or it.get("author") == "chair") else ""
                lines.append(f"- {prefix}{it['text']}")
        else:
            lines.append("- （暂无已锁定结论或主持约束）")

        lines.extend(["", "## 四、已确认放弃与证伪淘汰方案（防回流负面清单）", ""])
        if abandoned:
            for ab in abandoned:
                lines.append(f"- [已淘汰] {ab['text']}（来源：{ab.get('seat_name', '圆桌')} · 原因：{ab.get('reason', '证伪淘汰')}）")
        else:
            lines.append("- （本场讨论无已归档淘汰方案）")

        lines.extend(["", "## 五、待决争议与风险项", ""])
        if risks:
            for it in risks:
                tag = " [单源初评待核验]" if it.get("provisional_decision") else ""
                lines.append(f"- {it['text']}{tag}")
        else:
            lines.append("- （暂无未决风险项）")

        lines.extend(["", "## 六、交付与执行任务清单", ""])
        if actions:
            for it in actions:
                mark = "x" if it.get("checked", False) else " "
                lines.append(f"- [{mark}] {it['text']}")
        else:
            lines.append("- （暂无待执行任务）")

        lines.extend(["", "## 七、完整发言记录", ""])
        for m in sess.messages:
            if not isinstance(m, dict) or not str(m.get("content") or "").strip():
                continue
            sp = m.get("speaker_name") or m.get("speaker") or "成员"
            rl = m.get("role_title") or ""
            ph = m.get("phase_label") or ""
            ts = m.get("timestamp") or ""
            lines.append(f"### {sp}（{rl} · {ph}） {ts}".strip())
            lines.append("")
            lines.append(str(m.get("content") or "").strip())
            lines.append("")

        safe_title = "".join(c for c in (sess.title or "会议纪要") if c.isalnum() or c in ("-", "_"))[:24] or "纪要"
        ts_str = time.strftime("%Y%m%d_%H%M%S", time.localtime())
        filename = f"AI圆桌_{safe_title}_{ts_str}.md"
        return ("\n".join(lines) + "\n").encode("utf-8"), filename

    async def acknowledge_previous_snapshot(self, sess: MeetingSession) -> dict:
        """显式确认并归档上一轮可回滚快照，解锁新一轮工作区写入准入。"""
        async with sess.session_lock:
            if sess.last_backup is not None:
                sess.last_backup.mark_acknowledged()
                sess.last_backup = None
            sess.whiteboard["can_rollback"] = False
            sess.whiteboard["verification_failed"] = False
        await self.broadcast(sess, "whiteboard_update", sess.whiteboard)
        await self._broadcast_meta(sess)
        return {"ok": True, "can_rollback": False}

    async def get_session_recovery_plan(self, sess: MeetingSession) -> dict:
        bk = sess.pending_recovery_backup
        if not sess.recovery_required or bk is None:
            return {"recovery_required": False}
        plan = await asyncio.to_thread(bk.inspect_crash_recovery_plan)
        plan["recovery_required"] = True
        return plan

    async def recover_session_workspace(
        self,
        sess: MeetingSession,
        *,
        expected_hashes: Optional[dict],
        delete_confirmed_new_files: bool = True,
    ) -> Tuple[int, dict]:
        """校验用户确认的文件哈希映射后执行崩溃恢复（Section 一.4）。"""
        bk = sess.pending_recovery_backup
        if not sess.recovery_required or bk is None:
            return 400, {"ok": False, "error": "当前会话无待恢复的崩溃中断快照"}
        if sess.is_busy or sess.exec_state != "idle":
            return 409, {"ok": False, "error": "会话正在运行中，无法执行恢复"}

        ws_lock = WorkspaceWriteLock(
            bk.cwd,
            session_id=sess.session_id,
            run_id=bk.run_id,
            runtime_home=Path(self.data_dir),
        )
        try:
            ws_lock.try_acquire()
        except WorkspaceLockBusyError as busy_exc:
            return 409, {"ok": False, "error": str(busy_exc), "holder": busy_exc.holder}

        try:
            ok, msg, report = await asyncio.to_thread(
                bk.recover_from_crash,
                expected_hashes,
                delete_confirmed_new_files=delete_confirmed_new_files,
            )
            if not ok:
                return int(report.get("status_code", 409)), {"ok": False, "error": msg, **report}
            async with sess.session_lock:
                sess.recovery_required = False
                sess.pending_recovery_backup = None
                sess.whiteboard["recovery_required"] = False
                sess.whiteboard["consensus_status"] = "已完成崩溃现场字节恢复"
            self.store.record_exec_recovery(
                run_id=bk.run_id,
                session_id=sess.session_id,
                workspace_realpath=bk.cwd,
                backup_dir=str(bk.backup_dir),
                state="recovered",
            )
            await self.broadcast(sess, "whiteboard_update", sess.whiteboard)
            await self._broadcast_meta(sess)
            self._persist_single_session(sess, immediate=True)
            return 200, {"ok": True, "message": msg, **report}
        finally:
            ws_lock.release()

    async def admit_and_start_execution(
        self,
        sess: MeetingSession,
        *,
        allow_workspace_write: bool = False,
        executor_id: Optional[str] = None,
        verify_command: Optional[str] = None,
        acknowledge_absent: bool = False,
    ) -> dict:
        """
        单飞预约、零勾选任务硬拦截、缺席席位知悉门禁、写前字节证明与孤儿进程围栏同步准入契约：
        1. 会话短锁内零等待校验 idle、无未决 rollbackable/recovery_required、已勾选待执行任务数 >= 1 且无未确认异常缺席席位；
        2. 锁外获取非阻塞跨进程 flock(LOCK_EX | LOCK_NB)，完成 lstat + O_NOFOLLOW + <=128MiB 写前 CAS 清单 fsync 落盘；
           任何违规立即回退状态至 idle、释放 flock 并抛 409（保证工作区字节与业务 stage 零变化）；
        3. 短锁内二次核验未被 stop 取消后绑定 run_id 转入 running，返回 202 Accepted（含 operation_id, run_id, backup_id）。
        """
        raw_ws = sess.workspace_dir or self.settings.workspace_dir
        bound_ok, real_ws = is_real_bound_workspace(raw_ws)
        do_real_write = bool(allow_workspace_write and bound_ok)
        if allow_workspace_write and not bound_ok:
            raise ExecutionAdmissionConflictError(
                "尚未绑定真实的本地项目目录，无法开启写入工作区模式",
                status_code=409,
                details={"reason": "unbound_workspace"},
            )

        # 步骤 1：会话短锁内零等待预约与前置治理闸门
        async with sess.session_lock:
            if sess.exec_state != "idle" or sess.is_busy:
                raise ExecutionAdmissionConflictError(
                    "当前会话已有正在准备或运行中的任务，请勿重复并发提交",
                    status_code=409,
                    details={
                        "reason": "session_busy",
                        "operation_id": sess.active_operation_id,
                        "run_id": sess.active_run_id,
                    },
                )
            if sess.recovery_required:
                raise ExecutionAdmissionConflictError(
                    "当前会话存在上次崩溃中断未恢复的写快照，请先确认哈希完成恢复",
                    status_code=409,
                    details={"reason": "recovery_required"},
                )
            if do_real_write and sess.has_unacked_rollbackable():
                raise ExecutionAdmissionConflictError(
                    "存在上一轮未决的可回滚写入快照（rollbackable），请先回滚或确认归档后再发起新一轮写入",
                    status_code=409,
                    details={"reason": "pending_rollbackable_snapshot"},
                )

            wb_items_now = sess.whiteboard.get("items") or []
            checked_actions = [
                it for it in wb_items_now
                if isinstance(it, dict)
                and it.get("kind") == "action"
                and bool(it.get("checked", False))
                and str(it.get("text") or "").strip()
            ]
            if len(checked_actions) < 1:
                raise ExecutionAdmissionConflictError(
                    "尚无已勾选待执行任务（checked_action_count = 0），请先在会议白板核对并勾选至少 1 项任务后再启动执行",
                    status_code=409,
                    details={"reason": "no_checked_tasks", "checked_action_count": 0},
                )

            absent_list = sess.whiteboard.get("absent_seats") or []
            unacked_abnormal = [
                ab for ab in absent_list
                if isinstance(ab, dict) and ab.get("abnormal", True) and not ab.get("acknowledged", False)
            ]
            if unacked_abnormal:
                if acknowledge_absent:
                    for ab in unacked_abnormal:
                        ab["acknowledged"] = True
                else:
                    ab_names = "、".join(str(ab.get("seat_name") or ab.get("agent_id")) for ab in unacked_abnormal)
                    raise ExecutionAdmissionConflictError(
                        f"存在未完成发言的异常缺席席位（{ab_names}），请先就地恢复重试，或显式确认已知悉缺席风险后再执行交付",
                        status_code=409,
                        details={"reason": "unacknowledged_absent_seats", "absent_seats": unacked_abnormal},
                    )

            target_exec = executor_id if executor_id in AGENT_ORDER else sess.effective_executor_agent()
            operation_id = f"op_{uuid.uuid4().hex[:12]}"
            run_id = f"run_{uuid.uuid4().hex[:12]}"
            frozen_ws = os.path.realpath(real_ws) if bound_ok else self.runner._effective_workspace_cwd(raw_ws)
            frozen_cfg_ver = self.config_ver
            sess.active_operation_id = operation_id
            sess.active_run_id = ""
            sess.exec_state = "preparing"
            sess.cancelled_operations.discard(operation_id)

        # 步骤 2：锁外获取跨进程非阻塞排他锁 + 写前 CAS 字节清单 fsync 落盘
        ws_lock: Optional[WorkspaceWriteLock] = None
        backup: Optional[WorkspaceBackup] = None
        backup_id = ""
        if do_real_write:
            ws_lock = WorkspaceWriteLock(
                frozen_ws,
                session_id=sess.session_id,
                run_id=run_id,
                operation_id=operation_id,
                runtime_home=Path(self.data_dir),
            )
            try:
                ws_lock.try_acquire()
                backup = await asyncio.to_thread(
                    WorkspaceBackup.capture,
                    frozen_ws,
                    session_id=sess.session_id,
                    run_id=run_id,
                    operation_id=operation_id,
                    runtime_home=Path(self.data_dir),
                )
                backup_id = backup.backup_id
                self.store.record_exec_recovery(
                    run_id=run_id,
                    session_id=sess.session_id,
                    workspace_realpath=frozen_ws,
                    backup_dir=str(backup.backup_dir),
                    state="prepared",
                    meta={"operation_id": operation_id, "executor_id": target_exec, "config_ver": frozen_cfg_ver},
                )
            except WorkspaceLockBusyError as lock_exc:
                async with sess.session_lock:
                    if sess.active_operation_id == operation_id:
                        sess.exec_state = "idle"
                        sess.active_operation_id = ""
                raise ExecutionAdmissionConflictError(
                    str(lock_exc),
                    status_code=409,
                    details={"reason": "workspace_locked", "holder": lock_exc.holder},
                ) from lock_exc
            except WorkspaceAdmissionError as adm_exc:
                if ws_lock is not None:
                    ws_lock.release()
                async with sess.session_lock:
                    if sess.active_operation_id == operation_id:
                        sess.exec_state = "idle"
                        sess.active_operation_id = ""
                raise ExecutionAdmissionConflictError(
                    str(adm_exc),
                    status_code=409,
                    details={"reason": adm_exc.reason, "offending_path": adm_exc.offending_path},
                ) from adm_exc
            except Exception as unexpected_exc:
                if ws_lock is not None:
                    ws_lock.release()
                async with sess.session_lock:
                    if sess.active_operation_id == operation_id:
                        sess.exec_state = "idle"
                        sess.active_operation_id = ""
                raise ExecutionAdmissionConflictError(
                    f"写前快照准备失败：{unexpected_exc}",
                    status_code=409,
                    details={"reason": "prepare_failed"},
                ) from unexpected_exc

        # 步骤 3：短锁内二次核验准备期间未被 stop 取消，绑定 run_id 转入 running 并启动受护栏异步执行协程
        async with sess.session_lock:
            if operation_id in sess.cancelled_operations or sess.exec_state != "preparing" or sess.active_operation_id != operation_id:
                if backup is not None:
                    await asyncio.to_thread(backup.discard_prepared_unused)
                    self.store.record_exec_recovery(
                        run_id=run_id,
                        session_id=sess.session_id,
                        workspace_realpath=frozen_ws,
                        backup_dir=str(backup.backup_dir),
                        state="aborted_clean",
                    )
                if ws_lock is not None:
                    ws_lock.release()
                if sess.active_operation_id == operation_id:
                    sess.exec_state = "idle"
                    sess.active_operation_id = ""
                raise ExecutionAdmissionConflictError(
                    "执行任务在准备阶段已被取消",
                    status_code=409,
                    details={"reason": "cancelled_during_prepare", "operation_id": operation_id},
                )

            sess.executor_agent = target_exec
            sess.active_run_id = run_id
            sess.exec_state = "running"
            sess.execution_started_at = time.time()
            eff_verify_cmd = (
                verify_command
                if verify_command is not None
                else getattr(self.settings, "post_exec_verify_cmd", "")
            )
            sess.active_task = asyncio.create_task(
                self._run_guarded_execution(
                    sess=sess,
                    frozen_ws=frozen_ws,
                    allow_workspace_write=do_real_write,
                    executor_id=target_exec,
                    operation_id=operation_id,
                    run_id=run_id,
                    backup=backup,
                    ws_lock=ws_lock,
                    verify_cmd=eff_verify_cmd,
                    clear_task_on_exit=True,
                )
            )

        await self._broadcast_meta(sess)
        return {
            "ok": True,
            "status": "accepted",
            "operation_id": operation_id,
            "run_id": run_id,
            "backup_id": backup_id,
            "execution_started_at": sess.execution_started_at,
        }

    async def trigger_astra_execution(
        self,
        sess: MeetingSession,
        allow_workspace_write: bool = False,
        executor_id: Optional[str] = None,
    ) -> dict:
        """兼容内部调用入口：委托至单飞同步准入状态机。"""
        if sess.is_busy and not allow_workspace_write:
            await self.cancel_active_flow(sess, reason_tag="切换执行阶段", wait_task=True)
        return await self.admit_and_start_execution(
            sess,
            allow_workspace_write=allow_workspace_write,
            executor_id=executor_id,
        )

    async def _execute_agent_internal(
        self,
        sess: MeetingSession,
        allow_workspace_write: bool,
        executor_id: Optional[str] = None,
        clear_task_on_exit: bool = True,
    ) -> None:
        """内部 auto_preview_exec 只读预演入口。"""
        raw_ws = sess.workspace_dir or self.settings.workspace_dir
        bound_ok, real_ws = is_real_bound_workspace(raw_ws)
        frozen_ws = os.path.realpath(real_ws) if bound_ok else self.runner._effective_workspace_cwd(raw_ws)
        op_id = sess.active_operation_id or f"op_{uuid.uuid4().hex[:12]}"
        run_id = f"run_{uuid.uuid4().hex[:12]}"
        await self._run_guarded_execution(
            sess=sess,
            frozen_ws=frozen_ws,
            allow_workspace_write=False,
            executor_id=executor_id,
            operation_id=op_id,
            run_id=run_id,
            backup=None,
            ws_lock=None,
            verify_cmd="",
            clear_task_on_exit=clear_task_on_exit,
        )

    async def rollback_session_execution_detailed(self, sess: MeetingSession) -> Tuple[int, dict]:
        """原子冲突检测回滚接口：返回 (HTTP状态码, 响应JSON)，冲突返回 409 + 全量 conflict_paths 并保留 rollbackable。"""
        async with sess.session_lock:
            backup = sess.last_backup
            if not backup or not backup.is_rollbackable:
                return 409, {"ok": False, "error": "当前会话暂无可回滚的写入快照", "conflict_paths": [], "rollbackable": False}
            if sess.is_busy or sess.exec_state != "idle":
                return 409, {"ok": False, "error": "请在当前执行任务完全收口后再执行回滚", "conflict_paths": [], "rollbackable": True}
            sess.exec_state = "preparing"

        ws_lock = WorkspaceWriteLock(
            backup.cwd,
            session_id=sess.session_id,
            run_id=f"rb_{backup.run_id}",
            runtime_home=Path(self.data_dir),
        )
        try:
            try:
                ws_lock.try_acquire()
            except WorkspaceLockBusyError as busy_exc:
                return 409, {
                    "ok": False,
                    "error": str(busy_exc),
                    "holder": busy_exc.holder,
                    "conflict_paths": [],
                    "rollbackable": True,
                }

            try:
                ok, msg, report = await asyncio.to_thread(backup.restore_with_report)
            finally:
                ws_lock.release()

            if not ok:
                status_code = int(report.get("status_code", 409))
                # 保留 last_backup 与 can_rollback = True
                sess.whiteboard["can_rollback"] = backup.is_rollbackable
                return status_code, {
                    "ok": False,
                    "error": msg,
                    "conflict_paths": list(report.get("conflict_paths") or []),
                    "rollbackable": backup.is_rollbackable,
                }

            sess.last_backup = None
            sess.whiteboard["can_rollback"] = False
            sess.whiteboard["verification_failed"] = False
            sess.whiteboard["exec_logs"].append(f"↺ {msg}")
            sess.whiteboard["exec_diff"] = ""
            self.store.record_exec_recovery(
                run_id=backup.run_id,
                session_id=sess.session_id,
                workspace_realpath=backup.cwd,
                backup_dir=str(backup.backup_dir),
                state="rolled_back",
            )
            invalidate_workspace_index(backup.cwd)
        finally:
            async with sess.session_lock:
                if sess.exec_state == "preparing":
                    sess.exec_state = "idle"

        await self.broadcast(sess, "term_log", {"line": f"↺ {msg}"})
        await self.broadcast(sess, "whiteboard_update", sess.whiteboard)
        await self._append_non_agent_message(
            sess,
            speaker="system",
            speaker_name="安全快照护栏",
            role_title="原子字节回滚",
            phase_label="已回滚",
            content=msg,
            badge="已恢复",
        )
        self._persist_single_session(sess, immediate=True)
        return 200, {"ok": True, "message": msg, "conflict_paths": [], "rollbackable": False}

    async def rollback_session_execution(self, sess: MeetingSession) -> Tuple[bool, str]:
        code, payload = await self.rollback_session_execution_detailed(sess)
        return code == 200, str(payload.get("message") or payload.get("error") or "")

    async def _run_guarded_execution(
        self,
        *,
        sess: MeetingSession,
        frozen_ws: str,
        allow_workspace_write: bool,
        executor_id: Optional[str],
        operation_id: str,
        run_id: str,
        backup: Optional[WorkspaceBackup],
        ws_lock: Optional[WorkspaceWriteLock],
        verify_cmd: str = "",
        clear_task_on_exit: bool = True,
    ) -> None:
        owner_task = asyncio.current_task()
        exec_aid = executor_id if executor_id in AGENT_ORDER else sess.effective_executor_agent()
        exec_name = self._seat_name(sess, exec_aid)
        p_key = sess.seat_personas.get(exec_aid) or DEFAULT_SEAT_PERSONAS.get(exec_aid, "implementer")
        pspec = get_persona_spec(p_key, fallback_agent_id=exec_aid)
        mode_tag = "写入本地项目" if allow_workspace_write else "只读预演/方案交付"

        sess.executor_agent = exec_aid
        sess.whiteboard["executor_agent"] = exec_aid
        sess.whiteboard["verification_failed"] = False
        _normalize_and_sync_whiteboard(sess.whiteboard, topic=sess.topic, messages=sess.messages)
        await self._set_stage(sess, "executing", f"{exec_name} 执行中（{mode_tag}）")
        await self._set_seat(sess, exec_aid, "executing", f"执行中·{mode_tag}")
        sess.whiteboard["exec_logs"] = []
        sess.whiteboard["exec_diff"] = ""
        sess.whiteboard["can_rollback"] = False
        await self.broadcast(sess, "whiteboard_update", sess.whiteboard)

        exec_start_ts = time.perf_counter()
        exec_ttft_ms: Optional[int] = None
        spawned_pgid_holder: List[int] = [0]
        received_substantive_artifact = False
        msg_id = f"m_{uuid.uuid4().hex[:8]}"
        msg_obj = {
            "id": msg_id,
            "speaker": exec_aid,
            "speaker_name": exec_name,
            "role_title": f"{pspec['label']}·执行席位",
            "phase_label": "执行交付",
            "content": "",
            "badge": mode_tag,
            "target": None,
            "ttft_ms": 0,
            "elapsed_ms": 0,
            "started_ts": int((sess.execution_started_at or time.time()) * 1000),
            "streaming": True,
            "error": False,
            "error_kind": "",
            "error_detail": "",
            "timestamp": now_hhmmss(),
        }
        sess.messages.append(msg_obj)
        await self.broadcast(sess, "msg_start", msg_obj)

        async def _on_pgid_spawned(pgid: int) -> None:
            spawned_pgid_holder[0] = int(pgid)
            if backup is not None:
                await asyncio.to_thread(backup.record_running_pgid, int(pgid))
                self.store.record_exec_recovery(
                    run_id=run_id,
                    session_id=sess.session_id,
                    workspace_realpath=frozen_ws,
                    backup_dir=str(backup.backup_dir),
                    state="running",
                    pgid=int(pgid),
                )

        try:
            if backup is not None:
                snap_line = f"[CAS Snapshot] 已完成写前无 Git 依赖字节清单与 fsync 落盘 (run={run_id})"
                sess.whiteboard["exec_logs"].append(snap_line)
                await self.broadcast(sess, "term_log", {"line": snap_line})

            exec_kwargs = dict(
                topic=sess.topic or sess.title,
                whiteboard=sess.whiteboard,
                allow_workspace_write=allow_workspace_write,
                session_workspace=frozen_ws,
                agent_id=exec_aid,
                persona_key=p_key,
                session_id=sess.session_id,
                on_pgid_spawned=_on_pgid_spawned,
            )
            try:
                exec_gen = self.runner.stream_agent_execution(**exec_kwargs)
            except TypeError:
                exec_kwargs.pop("session_id", None)
                exec_kwargs.pop("on_pgid_spawned", None)
                exec_gen = self.runner.stream_agent_execution(**exec_kwargs)

            async for ev in exec_gen:
                etype = ev.get("type")
                if etype == "term_log":
                    sess.whiteboard["exec_logs"].append(ev["line"])
                    await self.broadcast(sess, "term_log", {"line": ev["line"]})
                elif etype == "exec_delta":
                    delta_txt = ev.get("text", "")
                    if delta_txt:
                        if exec_ttft_ms is None:
                            exec_ttft_ms = int((time.perf_counter() - exec_start_ts) * 1000)
                            msg_obj["ttft_ms"] = exec_ttft_ms
                        msg_obj["content"] += delta_txt
                        await self.broadcast(sess, "msg_delta", {"id": msg_id, "delta": delta_txt})
                        await self.broadcast(sess, "exec_delta", {"delta": delta_txt})
                elif etype == "exec_artifact":
                    summary_txt = str(ev.get("summary") or "").strip()
                    diff_txt = str(ev.get("diff") or "").strip()
                    if summary_txt or diff_txt:
                        received_substantive_artifact = True
                        elapsed_ms = int((time.perf_counter() - exec_start_ts) * 1000)
                        sess.whiteboard["exec_summary"] = summary_txt
                        if diff_txt:
                            sess.whiteboard["exec_diff"] = diff_txt
                        msg_obj["content"] = summary_txt or msg_obj["content"]
                        msg_obj["streaming"] = False
                        msg_obj["ttft_ms"] = exec_ttft_ms or elapsed_ms
                        msg_obj["elapsed_ms"] = elapsed_ms
                        msg_obj["badge"] = "已写入本地项目" if allow_workspace_write else "交付完成"
                        await self.broadcast(sess, "msg_done", msg_obj)
                        await self.broadcast(sess, "exec_artifact", ev)
                        await self.broadcast(sess, "whiteboard_update", sess.whiteboard)

            # Section 二.3 红线：执行流无实质产出时严禁兜底伪造“交付完成”！
            if not received_substantive_artifact:
                elapsed_ms = int((time.perf_counter() - exec_start_ts) * 1000)
                msg_obj["streaming"] = False
                msg_obj["error"] = True
                msg_obj["error_kind"] = "empty_execution_output"
                msg_obj["elapsed_ms"] = elapsed_ms
                msg_obj["badge"] = "无有效产出"
                if not str(msg_obj.get("content") or "").strip():
                    msg_obj["content"] = "✖ 执行流结束但未收到有效交付产物（已阻断完成态标记）。"
                await self.broadcast(sess, "msg_done", msg_obj)
                await self._set_seat(sess, exec_aid, "idle", "无有效产出", elapsed_ms=elapsed_ms)
                await self._set_stage(sess, "awaiting_chair", f"{exec_name} 执行未产生有效交付，请核查日志")
            else:
                # P2.1：进入最终 completed 态前执行可选只读自动化验证门禁
                verify_failed = False
                if allow_workspace_write and str(verify_cmd or "").strip():
                    v_start_line = f"▶ [验证门禁] 正在执行只读校验命令: {verify_cmd}"
                    sess.whiteboard["exec_logs"].append(v_start_line)
                    await self.broadcast(sess, "term_log", {"line": v_start_line})
                    v_rep = await run_post_execution_verification(
                        verify_cmd,
                        workspace_realpath=frozen_ws,
                        env=build_host_env(),
                    )
                    sess.whiteboard["last_verification"] = v_rep
                    if v_rep["passed"]:
                        ok_line = f"✔ [验证门禁通过] ({v_rep['elapsed_ms']}ms) {verify_cmd}"
                        sess.whiteboard["exec_logs"].append(ok_line)
                        await self.broadcast(sess, "term_log", {"line": ok_line})
                    else:
                        verify_failed = True
                        sess.whiteboard["verification_failed"] = True
                        fail_line = f"✖ [验证门禁未通过] (exit={v_rep['exit_code']}) 建议立即点击白板「一键回滚」还原！\n{v_rep['output'][:1200]}"
                        sess.whiteboard["exec_logs"].append(fail_line)
                        await self.broadcast(sess, "term_log", {"line": fail_line})
                        msg_obj["badge"] = "验证未通过·待回滚"
                        await self.broadcast(sess, "msg_done", msg_obj)

                if verify_failed:
                    await self._set_seat(sess, exec_aid, "idle", "验证未通过", elapsed_ms=msg_obj["elapsed_ms"])
                    await self._set_stage(sess, "awaiting_chair", f"{exec_name} 写入已完成但自动化验证未通过，建议一键回滚")
                else:
                    await self._set_seat(sess, exec_aid, "idle", "执行完成", elapsed_ms=msg_obj["elapsed_ms"])
                    await self._set_stage(sess, "concluded", f"{exec_name} 执行已完成")
        except asyncio.CancelledError:
            raise
        except CLIInvocationError as exc:
            err_badge = self._badge_for_error_kind(exc.error_kind)
            err_line = f"✖ {exec_name} 执行异常: {exc}"
            sess.whiteboard["exec_logs"].append(err_line)
            await self.broadcast(sess, "term_log", {"line": err_line})
            msg_obj["streaming"] = False
            msg_obj["error"] = True
            msg_obj["error_kind"] = exc.error_kind
            msg_obj["error_detail"] = exc.stderr[:1600]
            msg_obj["failed_driver"] = exc.driver or ""
            msg_obj["failed_model"] = exc.model or ""
            msg_obj["failed_effort"] = exc.effort or ""
            msg_obj["content"] = msg_obj["content"] + (f"\n\n{err_line}" if msg_obj["content"] else err_line)
            msg_obj["badge"] = err_badge
            await self.broadcast(sess, "msg_done", msg_obj)
            await self._set_seat(sess, exec_aid, "idle", err_badge)
            await self._set_stage(sess, "awaiting_chair", f"{exec_name} 执行未完成（{err_badge}），请查看详情")
        except Exception as exc:
            err_line = f"✖ {exec_name} 执行失败: {exc}"
            sess.whiteboard["exec_logs"].append(err_line)
            await self.broadcast(sess, "term_log", {"line": err_line})
            msg_obj["streaming"] = False
            msg_obj["error"] = True
            msg_obj["error_kind"] = "process_error"
            msg_obj["error_detail"] = str(exc)[:1600]
            msg_obj["content"] = msg_obj["content"] + (f"\n\n{err_line}" if msg_obj["content"] else err_line)
            msg_obj["badge"] = "执行失败"
            await self.broadcast(sess, "msg_done", msg_obj)
            await self._set_seat(sess, exec_aid, "idle", "执行失败")
            await self._set_stage(sess, "awaiting_chair", f"{exec_name} 执行未完成，请查看报错详情")
        finally:
            try:
                # 严守围栏：确认受监管 pgid 进程组已彻底消亡后，再启动 after CAS 清单扫描，最后才释放跨进程 flock！
                pgid_val = spawned_pgid_holder[0]
                if pgid_val > 1:
                    wait_deadline = time.monotonic() + 5.0
                    while time.monotonic() < wait_deadline and is_process_group_alive(pgid_val):
                        try:
                            if os.name == "nt":
                                from .drivers.windows_support import stop_job
                                stop_job(pgid_val)
                            else:
                                os.killpg(pgid_val, 9)
                        except OSError:
                            pass
                        await asyncio.sleep(0.03)

                if backup is not None:
                    try:
                        changed = await asyncio.to_thread(backup.finish)
                        if os.path.realpath(sess.workspace_dir or frozen_ws) == os.path.realpath(backup.cwd):
                            if changed:
                                sess.last_backup = backup
                                sess.whiteboard["exec_diff"] = backup.worktree_diff
                            else:
                                sess.last_backup = None
                        self.store.record_exec_recovery(
                            run_id=run_id,
                            session_id=sess.session_id,
                            workspace_realpath=frozen_ws,
                            backup_dir=str(backup.backup_dir),
                            state="rollbackable" if changed else "completed_noop",
                        )
                        invalidate_workspace_index(frozen_ws)
                    except Exception as exc:
                        sess.last_backup = None
                        sess.recovery_required = True
                        sess.pending_recovery_backup = backup
                        sess.whiteboard["recovery_required"] = True
                        sess.whiteboard["exec_logs"].append(f"未能记录执行后的文件状态，已转入显式恢复保护态：{exc}")
            finally:
                if ws_lock is not None:
                    ws_lock.release()

            sess.whiteboard["can_rollback"] = sess.has_unacked_rollbackable()
            await self.broadcast(sess, "whiteboard_update", sess.whiteboard)
            if clear_task_on_exit:
                await self._finalize_task_idle_state(sess, owner_task, operation_id=operation_id)
            else:
                async with sess.session_lock:
                    if sess.active_operation_id == operation_id:
                        sess.exec_state = "idle"
                        sess.execution_started_at = 0.0
            self._persist_single_session(sess, rewrite_all_messages=True, immediate=True)
            await self._broadcast_meta(sess)
