# -*- coding: utf-8 -*-
"""
AI圆桌 — 领域模型包：1~6 席弹性阵容目录、白板八项合取准入门禁与多席异构驱动族共识门禁
"""

from __future__ import annotations

import os
from typing import Dict, Iterable, List, Optional, Set, Tuple


ALL_SEAT_IDS: Tuple[str, ...] = ("carbon", "grok", "astra", "vega", "titan", "prism")
CLASSIC_SEAT_IDS: Tuple[str, ...] = ("carbon", "grok", "astra")

IMMUTABLE_SEAT_CATALOG: Dict[str, dict] = {
    "carbon": {
        "agent_id": "carbon",
        "default_name": "架构师",
        "title": "规划",
        "default_persona": "planner",
        "default_driver": "agy",
        "default_cli": "Antigravity CLI",
        "color_token": "carbon",
        "accent_hex": "#3b63f6",
    },
    "grok": {
        "agent_id": "grok",
        "default_name": "审计官",
        "title": "审计",
        "default_persona": "red_team",
        "default_driver": "grok",
        "default_cli": "Grok CLI",
        "color_token": "grok",
        "accent_hex": "#d97706",
    },
    "astra": {
        "agent_id": "astra",
        "default_name": "工程师",
        "title": "工程",
        "default_persona": "implementer",
        "default_driver": "codex",
        "default_cli": "Codex CLI",
        "color_token": "astra",
        "accent_hex": "#0d9470",
    },
    "vega": {
        "agent_id": "vega",
        "default_name": "交互设计",
        "title": "交互",
        "default_persona": "product_ux",
        "default_driver": "auto",
        "default_cli": "Auto CLI",
        "color_token": "vega",
        "accent_hex": "#e11d48",
    },
    "titan": {
        "agent_id": "titan",
        "default_name": "性能专家",
        "title": "性能",
        "default_persona": "perf_sre",
        "default_driver": "auto",
        "default_cli": "Auto CLI",
        "color_token": "titan",
        "accent_hex": "#0284c7",
    },
    "prism": {
        "agent_id": "prism",
        "default_name": "质量验证",
        "title": "验证",
        "default_persona": "qa_audit",
        "default_driver": "auto",
        "default_cli": "Auto CLI",
        "color_token": "prism",
        "accent_hex": "#7c3aed",
    },
}

SCENARIO_LINEUP_TEMPLATES: Dict[str, dict] = {
    "solo_focus": {
        "key": "solo_focus",
        "label": "单席专注（1席）",
        "seat_count": 1,
        "enabled_agents": ["carbon"],
        "seat_personas": {"carbon": "fullstack_solo"},
        "collab_mode": "deep_deliberation",
        "desc": "单席全栈架构推演与自我边界审查，零跨席等待，适合独立方案设计与快速编码",
    },
    "duel_review": {
        "key": "duel_review",
        "label": "双席辩证（2席）",
        "seat_count": 2,
        "enabled_agents": ["carbon", "grok"],
        "seat_personas": {"carbon": "fullstack_solo", "grok": "red_team"},
        "collab_mode": "adversarial_review",
        "desc": "主方案立论与反向风险审计双席博弈，兼顾低配额开销与深度边界验证",
    },
    "classic_triad": {
        "key": "classic_triad",
        "label": "标准三席合议（3席）",
        "seat_count": 3,
        "enabled_agents": ["carbon", "grok", "astra"],
        "seat_personas": {"carbon": "planner", "grok": "red_team", "astra": "implementer"},
        "collab_mode": "deep_deliberation",
        "desc": "架构规划、风险审计与工程实现三席协同（默认推荐配置）",
    },
    "product_quad": {
        "key": "product_quad",
        "label": "四席产品全栈评审（4席）",
        "seat_count": 4,
        "enabled_agents": ["carbon", "vega", "grok", "astra"],
        "seat_personas": {
            "carbon": "planner",
            "vega": "product_ux",
            "grok": "red_team",
            "astra": "implementer",
        },
        "collab_mode": "divergent_convergent",
        "desc": "引入产品交互席位，统筹系统架构、信息层级、安全边界与代码落地",
    },
    "sre_council_5": {
        "key": "sre_council_5",
        "label": "五席高可靠架构委员会（5席）",
        "seat_count": 5,
        "enabled_agents": ["carbon", "vega", "grok", "titan", "astra"],
        "seat_personas": {
            "carbon": "planner",
            "vega": "product_ux",
            "grok": "red_team",
            "titan": "perf_sre",
            "astra": "implementer",
        },
        "collab_mode": "deep_deliberation",
        "desc": "增设性能与稳定性席位，针对并发锁、存储事务与低延迟链路展开专项评审",
    },
    "full_jury_6": {
        "key": "full_jury_6",
        "label": "六席全景工程评审（6席）",
        "seat_count": 6,
        "enabled_agents": ["carbon", "vega", "grok", "titan", "astra", "prism"],
        "seat_personas": {
            "carbon": "planner",
            "vega": "product_ux",
            "grok": "red_team",
            "titan": "perf_sre",
            "astra": "implementer",
            "prism": "qa_audit",
        },
        "collab_mode": "deep_deliberation",
        "desc": "六席全量并发评审（含测试与验证席位），同步产出架构裁定、实施路径与回归验证矩阵",
    },
}


def check_whiteboard_admission_gate(
    *,
    run_id: str,
    expected_run_id: str,
    attempt_id: str,
    expected_attempt_id: str,
    status: str,
    terminal_received: bool,
    error_kind: str,
    partial_output: bool,
    skipped: bool,
    cancelled: bool,
    clean_body: str,
) -> bool:
    """
    白板准入八项合取门禁（Section 二.3）：
    仅当 `run_id/attempt_id 匹配 ∧ status == "success" ∧ terminal_received == True ∧ error_kind == "" ∧
    partial_output == False ∧ not skipped ∧ not cancelled ∧ 非空正文` 全部满足时返回 True。
    """
    if not run_id or run_id != expected_run_id:
        return False
    if not attempt_id or attempt_id != expected_attempt_id:
        return False
    if status != "success":
        return False
    if terminal_received is not True:
        return False
    if str(error_kind or "").strip() != "":
        return False
    if partial_output is True:
        return False
    if skipped is True:
        return False
    if cancelled is True:
        return False
    if not str(clean_body or "").strip():
        return False
    return True


def normalize_driver_family_key(effective_driver: str, binary_path: str = "") -> str:
    """
    计算防软链接双路径绕过的规范化驱动族标识：
    - 若存在真实二进制文件路径（非 mock://），优先按 os.path.realpath(binary_path) 归并同源可执行文件
      （即使两个席位分别通过不同软链接或不同 driver 别名指向同一个二进制文件，也只计为 1 个驱动族！）；
    - 对于 mock:// 或纯驱动标识场景，按规范化驱动协议族归并。
    """
    drv = str(effective_driver or "").strip().lower()
    bpath = str(binary_path or "").strip()
    if bpath and "://" not in bpath and os.path.lexists(bpath):
        real_bin = os.path.realpath(bpath)
        return f"realpath:{real_bin}"
    if drv in ("agy", "antigravity"):
        return "driver:agy"
    if drv == "grok":
        return "driver:grok"
    if drv == "codex":
        return "driver:codex"
    if bpath:
        return f"mockbin:{bpath}"
    if drv and drv != "auto":
        return f"driver:{drv}"
    return "driver:unknown"


def compute_effective_driver_families(records: Iterable[dict]) -> Set[str]:
    """统计本轮完整成功席位的独立底层驱动族集合。"""
    families: Set[str] = set()
    for rec in records:
        if not isinstance(rec, dict):
            continue
        if rec.get("status") != "success":
            continue
        fam = normalize_driver_family_key(
            str(rec.get("driver") or rec.get("effective_driver") or ""),
            str(rec.get("binary_path") or ""),
        )
        if fam and fam != "driver:unknown":
            families.add(fam)
    return families


def can_auto_promote_consensus_decision(
    *,
    enabled_seat_count: int,
    successful_driver_families: Set[str],
) -> bool:
    """实际成功驱动族 < 2 时禁止自动升格为已确认共识 decision。"""
    _ = enabled_seat_count
    return len(successful_driver_families) >= 2


__all__ = [
    "ALL_SEAT_IDS",
    "CLASSIC_SEAT_IDS",
    "IMMUTABLE_SEAT_CATALOG",
    "SCENARIO_LINEUP_TEMPLATES",
    "can_auto_promote_consensus_decision",
    "check_whiteboard_admission_gate",
    "compute_effective_driver_families",
    "normalize_driver_family_key",
]
