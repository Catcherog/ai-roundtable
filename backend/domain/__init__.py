# -*- coding: utf-8 -*-
"""
AI圆桌 — 领域模型包：1~6 席弹性阵容目录、四大场景意图包、白板八项合取准入门禁、三级来源准入与认知防伪门禁
"""

from __future__ import annotations

import os
from typing import Dict, Iterable, List, Optional, Set, Tuple


ALL_SEAT_IDS: Tuple[str, ...] = ("carbon", "grok", "astra", "vega", "titan", "prism")
CLASSIC_SEAT_IDS: Tuple[str, ...] = ("carbon", "grok", "astra")

VALID_ARTIFACT_TYPES: Tuple[str, ...] = (
    "code_patch",
    "decision_matrix",
    "ux_checklist",
    "doc_export",
)

VALID_ORIGIN_TIERS: Tuple[str, ...] = (
    "multi_seat_consensus",
    "chair_directive",
    "provisional_suggestion",
)

DRIVER_PROVIDER_LABELS: Dict[str, Tuple[str, str]] = {
    "agy": ("Google", "Antigravity CLI"),
    "antigravity": ("Google", "Antigravity CLI"),
    "codex": ("OpenAI", "Codex CLI"),
    "grok": ("xAI", "Grok CLI"),
}

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

SCENARIO_INTENT_PACKS: Dict[str, dict] = {
    "arch_code": {
        "key": "arch_code",
        "label": "工程研发与代码审查包",
        "short_label": "工程研发与代码审查",
        "artifact_type": "code_patch",
        "artifact_label": "代码预演与安全写盘",
        "seat_count": 3,
        "enabled_agents": ["carbon", "grok", "astra"],
        "seat_personas": {
            "carbon": "planner",
            "grok": "red_team",
            "astra": "implementer",
        },
        "collab_mode": "deep_deliberation",
        "prefer_unbound_workspace": False,
        "desc": "3 席（规划立论 + 反向审计 + 工程实现）· 深度研讨，开启工作区 @源码切片引用与预演/写盘终端出口",
        "starter_prompt": (
            "请针对目标模块开展架构设计与代码级协同审查：\n"
            "1. 核心改造诉求与预期目标：\n"
            "2. 涉及文件范围（可通过 @路径:起始行-结束行 引用源码）：\n"
            "3. 兼容性边界与回归验收标准："
        ),
    },
    "tradeoff_debate": {
        "key": "tradeoff_debate",
        "label": "方案利弊红蓝辩证包",
        "short_label": "方案利弊红蓝辩证",
        "artifact_type": "decision_matrix",
        "artifact_label": "对比决策纪要",
        "seat_count": 3,
        "enabled_agents": ["carbon", "grok", "astra"],
        "seat_personas": {
            "carbon": "planner",
            "grok": "red_team",
            "astra": "implementer",
        },
        "collab_mode": "adversarial_review",
        "prefer_unbound_workspace": True,
        "desc": "2–3 席（正方建构 + 反方证伪 + 综合裁定）· 正反辩证，默认纯研讨免绑目录，主出口为对比决策纪要",
        "starter_prompt": (
            "请围绕以下关键技术/产品取舍开展红蓝正反辩证与综合裁定：\n"
            "1. 待决核心议题与备选路线（方案 A vs 方案 B）：\n"
            "2. 现实约束边界（时延 / 成本 / 复杂度 / 演进周期）：\n"
            "3. 关键评判维度与不可突破底线："
        ),
    },
    "ux_multimodal": {
        "key": "ux_multimodal",
        "label": "产品体验与多模态走查包",
        "short_label": "产品体验与多模态走查",
        "artifact_type": "ux_checklist",
        "artifact_label": "体验走查清单",
        "seat_count": 4,
        "enabled_agents": ["vega", "carbon", "grok", "astra"],
        "seat_personas": {
            "vega": "product_ux",
            "carbon": "planner",
            "grok": "red_team",
            "astra": "implementer",
        },
        "collab_mode": "divergent_convergent",
        "prefer_unbound_workspace": False,
        "desc": "3–4 席（交互体感 + 架构边界 + 风险审计）· 发散收敛，支持粘贴/拖拽截图对比与走查清单交付",
        "starter_prompt": (
            "请结合界面交互链路或参考截图（支持直接粘贴或拖拽图片至附件托盘）开展多维走查：\n"
            "1. 目标用户核心使用动线与首屏心智预期：\n"
            "2. 当前视觉层级、信息过载或交互状态痛点：\n"
            "3. 期望输出的分级体验优化与验收走查清单："
        ),
    },
    "incident_doc": {
        "key": "incident_doc",
        "label": "故障排查与文稿打磨包",
        "short_label": "故障排查与文稿打磨",
        "artifact_type": "doc_export",
        "artifact_label": "排查清单与结构化定稿",
        "seat_count": 2,
        "enabled_agents": ["grok", "astra"],
        "seat_personas": {
            "grok": "red_team",
            "astra": "implementer",
        },
        "collab_mode": "rapid_consensus",
        "prefer_unbound_workspace": True,
        "desc": "自适应排查/定稿立场 · 快速合议，单轮收敛根因验证路径或结构化定稿并支持一键复制/导出",
        "starter_prompt": (
            "请针对以下故障现象或待打磨文稿开展快速合议与定稿收敛：\n"
            "1. 异常现象/报错日志（或待打磨文稿草稿与受众目标）：\n"
            "2. 已观测上下文与排除条件：\n"
            "3. 期望交付的根因排查清单或结构化定稿规范："
        ),
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
        "artifact_type": "code_patch",
        "desc": "单席全栈架构推演与自我边界审查，零跨席等待，适合独立方案设计与快速编码",
    },
    "duel_review": {
        "key": "duel_review",
        "label": "双席辩证（2席）",
        "seat_count": 2,
        "enabled_agents": ["carbon", "grok"],
        "seat_personas": {"carbon": "fullstack_solo", "grok": "red_team"},
        "collab_mode": "adversarial_review",
        "artifact_type": "decision_matrix",
        "desc": "主方案立论与反向风险审计双席博弈，兼顾低配额开销与深度边界验证",
    },
    "classic_triad": {
        "key": "classic_triad",
        "label": "标准三席合议（3席）",
        "seat_count": 3,
        "enabled_agents": ["carbon", "grok", "astra"],
        "seat_personas": {"carbon": "planner", "grok": "red_team", "astra": "implementer"},
        "collab_mode": "deep_deliberation",
        "artifact_type": "code_patch",
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
        "artifact_type": "ux_checklist",
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
        "artifact_type": "code_patch",
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
            "prism": "qa_audit",
            "astra": "implementer",
        },
        "collab_mode": "deep_deliberation",
        "artifact_type": "code_patch",
        "desc": "六席全量并发评审（含测试与验证席位），同步产出架构裁定、实施路径与回归验证矩阵",
    },
}


def normalize_scenario_pack_and_artifact(
    scenario_pack: Optional[str] = None,
    artifact_type: Optional[str] = None,
) -> Tuple[str, str]:
    """规范化场景意图包标识与交付物出口类型，缺省兼容旧工程会话（arch_code / code_patch）。"""
    sp = str(scenario_pack or "").strip().lower()
    if sp not in SCENARIO_INTENT_PACKS:
        sp = "arch_code"
    at = str(artifact_type or "").strip().lower()
    if at not in VALID_ARTIFACT_TYPES:
        at = SCENARIO_INTENT_PACKS[sp]["artifact_type"]
    return sp, at


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


def compute_epistemic_status(
    *,
    enabled_seat_count: int,
    active_driver_families: Set[str],
    configured_driver_families: Optional[Set[str]] = None,
) -> dict:
    """
    计算会话认知独立性防伪状态（Section 1.2 & 2.1）：
    - 1 席参会：mode="solo_draft", badge="[单席推演草稿]"
    - >=2 席且实际生效（或就绪配置）独立驱动族 >= 2：mode="heterogeneous", badge="[异构多源交叉验证]"
    - >=2 席但独立驱动族 < 2：mode="homogeneous_warning", badge="[同源模型多视角推演 · 误差相关]"
    """
    if enabled_seat_count <= 1:
        return {
            "mode": "solo_draft",
            "badge": "[单席推演草稿]",
            "short_badge": "单席推演草稿",
            "driver_family_count": len(active_driver_families or configured_driver_families or set()),
            "is_heterogeneous": False,
        }
    eff_fams = active_driver_families if active_driver_families else (configured_driver_families or set())
    fam_cnt = len(eff_fams)
    if fam_cnt >= 2:
        return {
            "mode": "heterogeneous",
            "badge": "[异构独立引擎交叉核验]",
            "short_badge": f"异构独立 · {fam_cnt} 引擎",
            "driver_family_count": fam_cnt,
            "is_heterogeneous": True,
        }
    return {
        "mode": "homogeneous_warning",
        "badge": "[同源模型多视角推演 · 误差相关]",
        "short_badge": "同源模型多视角推演 · 误差相关",
        "driver_family_count": max(1, fam_cnt) if eff_fams else 0,
        "is_heterogeneous": False,
    }


from .whiteboard import (  # noqa: E402
    DEFAULT_SEAT_WB_KINDS,
    DISAGREEMENT_KEYWORDS,
    STALE_STREAMING_BADGES,
    UNPINNED_WB_SOFT_LIMIT,
    VALID_WB_AUTHORS,
    VALID_WB_KINDS,
    WHITEBOARD_LIST_KEYS,
    _empty_session_draft,
    _infer_source_msg_id,
    _norm_dedupe_key,
    _normalize_and_sync_whiteboard,
    dedupe_chair_constraints,
    extract_key_points_from_markdown,
    is_whiteboard_noise,
    make_deterministic_wb_id,
    normalize_whiteboard_structure,
    now_display_time,
    now_hhmmss,
    sanitize_persisted_message,
    smart_clip,
    summarize_topic_and_constraints,
    sync_whiteboard_legacy_arrays_and_caps,
)

__all__ = [
    "ALL_SEAT_IDS",
    "CLASSIC_SEAT_IDS",
    "DEFAULT_SEAT_WB_KINDS",
    "DISAGREEMENT_KEYWORDS",
    "DRIVER_PROVIDER_LABELS",
    "IMMUTABLE_SEAT_CATALOG",
    "SCENARIO_INTENT_PACKS",
    "SCENARIO_LINEUP_TEMPLATES",
    "STALE_STREAMING_BADGES",
    "UNPINNED_WB_SOFT_LIMIT",
    "VALID_ARTIFACT_TYPES",
    "VALID_ORIGIN_TIERS",
    "VALID_WB_AUTHORS",
    "VALID_WB_KINDS",
    "WHITEBOARD_LIST_KEYS",
    "_empty_session_draft",
    "_infer_source_msg_id",
    "_norm_dedupe_key",
    "_normalize_and_sync_whiteboard",
    "can_auto_promote_consensus_decision",
    "check_whiteboard_admission_gate",
    "compute_effective_driver_families",
    "compute_epistemic_status",
    "dedupe_chair_constraints",
    "extract_key_points_from_markdown",
    "is_whiteboard_noise",
    "make_deterministic_wb_id",
    "normalize_driver_family_key",
    "normalize_scenario_pack_and_artifact",
    "normalize_whiteboard_structure",
    "now_display_time",
    "now_hhmmss",
    "sanitize_persisted_message",
    "smart_clip",
    "summarize_topic_and_constraints",
    "sync_whiteboard_legacy_arrays_and_caps",
]
