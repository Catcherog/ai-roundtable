# -*- coding: utf-8 -*-
"""
AI圆桌 — 真实多 CLI 会议编排器
升级特性：
1. 支持任选席位一键独奏（Solo）与动态指定主刀执行官（独奏时自动由该席位包揽设计与执行）
2. 内置 7 种预设身份（架构规划/红队挑刺/工程落地/全栈主程/产品交互/性能稳定/测试验收），支持实时切换并联动 Prompt、收敛路由与白板标题
3. 满档上下文记忆（80 轮完整消息注入 / 500 条会话持久化）+ 独立 synthesis 长文决议通道
4. 会话级独立本地项目目录绑定 + 真实 Git 仓库检测 + @文件源码检索与增量补齐
5. 执行阶段同步推送实时流式消息卡片与终端流（exec_delta），写入前自动保存 Git 工作区快照支持一键回滚
"""

from __future__ import annotations

import asyncio
import glob
import json
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .cli_adapters import (
    DEFAULT_SEAT_PERSONAS,
    DRIVER_SPECS,
    PERSONA_PRESETS,
    VALID_DRIVERS,
    VALID_EFFORT_LEVELS,
    VALID_PERSONAS,
    CLIInvocationError,
    RuntimeSettings,
    UnifiedAgentRunner,
    export_model_effort_catalog,
    get_persona_spec,
    is_git_workspace,
    list_workspace_files,
    normalize_model_effort,
    resolve_effective_model_for_driver,
)


AGENT_META = {
    "carbon": {"name": "Carbon", "title": "规划", "cli": "Antigravity CLI"},
    "grok": {"name": "Grok", "title": "挑刺", "cli": "Grok CLI"},
    "astra": {"name": "Astra", "title": "落地", "cli": "Codex CLI"},
}

AGENT_ORDER = ("carbon", "grok", "astra")

COLLAB_MODES = {
    "standard_roundtable": {
        "label": "标准讨论",
        "rounds": 2,
        "desc": "多方并发初评 → 并发质询+主控收敛（单席位独奏自动直达方案沉淀）",
    },
    "fast_align": {
        "label": "快速决议",
        "rounds": 1,
        "desc": "并发初评 → 1轮快速质询与收敛 → 待主持决议",
    },
    "red_blue_debate": {
        "label": "方案质询",
        "rounds": 2,
        "desc": "并发立论 → 2轮深度挑刺与边界风险审视",
    },
    "arch_to_exec": {
        "label": "讨论并执行",
        "rounds": 1,
        "desc": "方案初评收敛 → 自动汇总决议并交由主刀席位预演执行",
    },
}

WHITEBOARD_LIST_KEYS = ("chair_constraints", "carbon_plan", "grok_risks", "astra_actions")
DISAGREEMENT_KEYWORDS = ("存疑", "分歧", "反对", "漏洞", "阻塞", "不同意", "待定", "需修", "质疑", "未决")

_CONVERSATIONAL_NOISE_PREFIX = re.compile(
    r"^(?:我只查公开资料|先核实|同意|完全赞同|赞同|收到|好的|补充一点|针对\s*@|工程侧赞同|综合\s*@|以下是|作为)",
    re.IGNORECASE,
)


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
    collab_mode: str = "standard_roundtable"
    stage: str = "idle"
    created_at: str = field(default_factory=now_display_time)
    updated_ts: float = field(default_factory=time.time)
    enabled_agents: List[str] = field(default_factory=lambda: list(AGENT_ORDER))
    seat_personas: Dict[str, str] = field(default_factory=dict)
    executor_agent: str = "astra"
    seat_states: Dict[str, dict] = field(default_factory=dict)
    messages: List[dict] = field(default_factory=list)
    whiteboard: dict = field(default_factory=dict)
    last_backup: Optional[dict] = field(default=None, repr=False)
    subscribers: List[asyncio.Queue] = field(default=list, repr=False)
    active_task: Optional[asyncio.Task] = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.subscribers, list):
            self.subscribers = []
        if not self.enabled_agents:
            self.enabled_agents = list(AGENT_ORDER)
        else:
            self.enabled_agents = [a for a in AGENT_ORDER if a in self.enabled_agents] or list(AGENT_ORDER)

        normalized_personas: Dict[str, str] = {}
        for aid in AGENT_ORDER:
            raw_p = (self.seat_personas or {}).get(aid, "")
            normalized_personas[aid] = raw_p if raw_p in PERSONA_PRESETS else DEFAULT_SEAT_PERSONAS[aid]
        self.seat_personas = normalized_personas

        if self.executor_agent not in AGENT_ORDER:
            self.executor_agent = "astra"

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
            st["wb_title"] = pspec["wb_title"]
            st["cue_btn"] = pspec["cue_btn"].format(name=meta["name"])
            st["cue_prompt"] = pspec["cue_prompt"]

        short_topic_title, _ = summarize_topic_and_constraints(self.topic)
        default_wb = {
            "topic": self.topic,
            "topic_title": short_topic_title,
            "consensus_status": "待输入议题",
            "chair_constraints": [],
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
        else:
            for k, v in default_wb.items():
                self.whiteboard.setdefault(k, v)
            if self.topic and (
                not self.whiteboard.get("topic_title")
                or _norm_dedupe_key(self.whiteboard.get("topic_title", "")) == _norm_dedupe_key(self.topic)
                and len(self.topic) > 28
            ):
                self.whiteboard["topic_title"] = short_topic_title
            self.whiteboard["chair_constraints"] = dedupe_chair_constraints(
                self.topic,
                self.whiteboard.get("topic_title", ""),
                self.whiteboard.get("chair_constraints", []),
            )
            self.whiteboard["executor_agent"] = self.effective_executor_agent()

    @property
    def is_busy(self) -> bool:
        return bool(self.active_task and not self.active_task.done())

    @property
    def is_solo(self) -> bool:
        return len(self.enabled_agents) == 1

    def effective_executor_agent(self) -> str:
        """
        动态解析主刀执行席位：
        - 单席位独奏时，自动由该独奏席位直接承接落地执行；
        - 多席位参会时，优先使用显式选定的参会主刀人，否则优先选挂载「工程落地/全栈主程」身份的参会席位。
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
        return {
            "session_id": self.session_id,
            "title": self.title,
            "topic": self.topic,
            "workspace_dir": self.workspace_dir,
            "workspace_is_git": is_git_workspace(self.workspace_dir),
            "collab_mode": self.collab_mode,
            "collab_mode_label": COLLAB_MODES.get(self.collab_mode, {}).get("label", "标准讨论"),
            "stage": self.stage,
            "created_at": self.created_at,
            "is_busy": self.is_busy,
            "enabled_agents": list(self.enabled_agents),
            "seat_personas": dict(self.seat_personas),
            "executor_agent": eff_exec,
            "seat_states": self.seat_states,
            "messages": self.messages,
            "whiteboard": self.whiteboard,
        }

    def to_persisted_dict(self) -> dict:
        clean_msgs = []
        for m in self.messages[-500:]:
            mc = dict(m)
            if mc.get("streaming"):
                mc["streaming"] = False
                mc["badge"] = mc.get("badge") or "已中断"
            clean_msgs.append(mc)
        wb_copy = dict(self.whiteboard)
        wb_copy["can_rollback"] = False
        wb_copy["executor_agent"] = self.effective_executor_agent()
        if isinstance(wb_copy.get("exec_logs"), list) and len(wb_copy["exec_logs"]) > 300:
            wb_copy["exec_logs"] = wb_copy["exec_logs"][-300:]
        return {
            "session_id": self.session_id,
            "title": self.title,
            "topic": self.topic,
            "workspace_dir": self.workspace_dir,
            "collab_mode": self.collab_mode,
            "stage": "awaiting_chair"
            if self.stage in ("opening_parallel", "cross_talk", "chair_interrupt", "executing")
            else self.stage,
            "created_at": self.created_at,
            "updated_ts": self.updated_ts,
            "enabled_agents": list(self.enabled_agents),
            "seat_personas": dict(self.seat_personas),
            "executor_agent": self.executor_agent,
            "messages": clean_msgs,
            "whiteboard": wb_copy,
        }


class RoundtableOrchestrator:
    SINGLE_CLI_SERIAL_BUFFER_SEC = 0.4

    def __init__(self, workspace_dir: str):
        self.data_dir = os.path.expanduser("~/.ai-roundtable")
        self.config_file = os.path.join(self.data_dir, "config.json")
        self.sessions_file = os.path.join(self.data_dir, "sessions.json")
        self._persist_handle: Optional[asyncio.TimerHandle] = None
        self._last_driver_finish_ts: Dict[str, float] = {}
        self._cleanup_stale_runtime_files()
        self.settings = RuntimeSettings.create_default(workspace_dir=workspace_dir)
        self._load_persisted_config()
        self.runner = UnifiedAgentRunner(self.settings)
        self.sessions: Dict[str, MeetingSession] = {}
        self._load_persisted_sessions()
        if not self.sessions:
            default_session = self.create_session(title="新会议", collab_mode="standard_roundtable")
            self.default_session_id = default_session.session_id
        else:
            self.default_session_id = list(self.sessions.keys())[-1]

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
                agents_cfg = data.get("agents", {})
                if isinstance(agents_cfg, dict):
                    for aid, acfg in agents_cfg.items():
                        if aid in self.settings.agents and isinstance(acfg, dict):
                            t = self.settings.agents[aid]
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
                normalized_changed = self._normalize_agent_efforts()
                if schema_ver < 6 or normalized_changed:
                    self._save_persisted_config()
        except Exception:
            pass

    def _save_persisted_config(self) -> None:
        try:
            os.makedirs(self.data_dir, exist_ok=True)
            payload = {
                "config_schema_version": 6,
                "workspace_dir": self.settings.workspace_dir,
                "allow_single_cli_fallback": self.settings.allow_single_cli_fallback,
                "agents": {
                    aid: {
                        "driver": cfg.driver,
                        "persona": cfg.persona,
                        "custom_binary": cfg.custom_binary,
                        "model": cfg.model,
                        "discussion_effort": cfg.discussion_effort,
                        "execution_effort": cfg.execution_effort,
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
            if not os.path.isfile(self.sessions_file):
                return
            with open(self.sessions_file, "r", encoding="utf-8") as f:
                raw_list = json.load(f)
            if not isinstance(raw_list, list):
                return
            inspected = self.settings.inspect_status()
            expire_cutoff = time.time() - 30 * 86400
            for item in raw_list[-50:]:
                if not isinstance(item, dict) or not item.get("session_id"):
                    continue
                msgs = item.get("messages") if isinstance(item.get("messages"), list) else []
                upd_ts = float(item.get("updated_ts") or time.time())
                if not msgs and not item.get("topic") and upd_ts < expire_cutoff:
                    continue
                sid = str(item["session_id"])
                mode = str(item.get("collab_mode", "standard_roundtable"))
                if mode not in COLLAB_MODES:
                    mode = "standard_roundtable"
                sess_ws = str(item.get("workspace_dir") or "").strip()
                if sess_ws and not os.path.isdir(sess_ws):
                    sess_ws = ""
                raw_personas = item.get("seat_personas")
                personas = (
                    dict(raw_personas)
                    if isinstance(raw_personas, dict)
                    else self._default_personas_from_settings()
                )
                exec_ag = str(item.get("executor_agent") or "astra").strip().lower()
                sess = MeetingSession(
                    session_id=sid,
                    title=str(item.get("title") or "新会议"),
                    topic=str(item.get("topic") or ""),
                    workspace_dir=sess_ws or self.settings.workspace_dir,
                    collab_mode=mode,
                    stage=str(item.get("stage") or "idle"),
                    created_at=str(item.get("created_at") or now_display_time()),
                    updated_ts=upd_ts,
                    enabled_agents=item.get("enabled_agents") or list(AGENT_ORDER),
                    seat_personas=personas,
                    executor_agent=exec_ag if exec_ag in AGENT_ORDER else "astra",
                    messages=msgs,
                    whiteboard=item.get("whiteboard") if isinstance(item.get("whiteboard"), dict) else {},
                )
                if sess.topic and sess.whiteboard.get("topic_title"):
                    sess.title = sess.whiteboard["topic_title"]
                if sess.stage == "awaiting_chair" and sess.whiteboard.get("consensus_status", "").startswith("第 "):
                    sess.whiteboard["consensus_status"] = "待主持人继续推进"
                self._sync_seat_readiness(sess, inspected=inspected)
                self.sessions[sid] = sess
        except Exception:
            pass

    def _flush_persisted_sessions_sync(self) -> None:
        try:
            os.makedirs(self.data_dir, exist_ok=True)
            items = [s.to_persisted_dict() for s in list(self.sessions.values())[-50:]]
            tmp_path = f"{self.sessions_file}.tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(items, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self.sessions_file)
        except Exception:
            pass

    def _save_persisted_sessions(self, immediate: bool = False) -> None:
        if immediate:
            if self._persist_handle:
                self._persist_handle.cancel()
                self._persist_handle = None
            self._flush_persisted_sessions_sync()
            return
        try:
            loop = asyncio.get_running_loop()
            if self._persist_handle:
                self._persist_handle.cancel()
            self._persist_handle = loop.call_later(
                0.18,
                lambda: loop.run_in_executor(None, self._flush_persisted_sessions_sync),
            )
        except RuntimeError:
            self._flush_persisted_sessions_sync()

    def create_session(self, title: str = "新会议", collab_mode: str = "standard_roundtable") -> MeetingSession:
        sid = f"s_{uuid.uuid4().hex[:8]}"
        mode = collab_mode if collab_mode in COLLAB_MODES else "standard_roundtable"
        prev_sess = self.sessions.get(self.default_session_id) if getattr(self, "default_session_id", None) else None
        init_enabled = list(prev_sess.enabled_agents) if prev_sess else list(AGENT_ORDER)
        init_personas = dict(prev_sess.seat_personas) if prev_sess else self._default_personas_from_settings()
        init_exec = prev_sess.executor_agent if prev_sess else "astra"

        sess = MeetingSession(
            session_id=sid,
            title=title.strip() or "新会议",
            workspace_dir=self.settings.workspace_dir,
            collab_mode=mode,
            enabled_agents=init_enabled,
            seat_personas=init_personas,
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
        if not self.sessions:
            fresh = self.create_session(title="新会议", collab_mode="standard_roundtable")
            self.default_session_id = fresh.session_id
        elif self.default_session_id == session_id:
            self.default_session_id = list(self.sessions.keys())[-1]
        self._save_persisted_sessions(immediate=True)
        return self.default_session_id

    def _sync_seat_readiness(self, sess: MeetingSession, inspected: Optional[Dict[str, dict]] = None) -> None:
        status_map = inspected if inspected is not None else self.settings.inspect_status()
        for aid, st in sess.seat_states.items():
            info = status_map.get(aid)
            enabled = aid in sess.enabled_agents
            p_key = sess.seat_personas.get(aid) or DEFAULT_SEAT_PERSONAS[aid]
            pspec = get_persona_spec(p_key, fallback_agent_id=aid)
            st["enabled"] = enabled
            st["persona"] = pspec["key"]
            st["persona_label"] = pspec["label"]
            st["title"] = pspec["short_tag"]
            st["wb_title"] = pspec["wb_title"]
            st["cue_btn"] = pspec["cue_btn"].format(name=AGENT_META[aid]["name"])
            st["cue_prompt"] = pspec["cue_prompt"]
            if info:
                st["binary_ready"] = bool(info.get("binary_detected"))
                st["shared_fallback"] = bool(info.get("shared_fallback"))
                st["shared_cli_group"] = bool(info.get("shared_cli_group"))
                st["effective_driver"] = info.get("effective_driver", "")
                st["effective_model"] = info.get("effective_model", "")
                st["effective_effort"] = info.get("effective_discussion_effort", "")
                if info.get("cli_name"):
                    st["cli_label"] = info["cli_name"]
                if st["status"] == "idle":
                    if not enabled:
                        st["badge"] = "已暂停参会"
                    elif info.get("binary_detected"):
                        st["badge"] = (
                            "单CLI多角" if info.get("shared_cli_group") and len(sess.enabled_agents) > 1 else "已就绪"
                        )
                    else:
                        st["badge"] = "未检测到 CLI"
        sess.whiteboard["executor_agent"] = sess.effective_executor_agent()

    def list_sessions(self) -> List[dict]:
        return [
            {
                "session_id": s.session_id,
                "title": s.title,
                "topic": s.topic,
                "workspace_dir": s.workspace_dir,
                "workspace_is_git": is_git_workspace(s.workspace_dir),
                "collab_mode": s.collab_mode,
                "collab_mode_label": COLLAB_MODES.get(s.collab_mode, {}).get("label", "标准讨论"),
                "stage": s.stage,
                "is_busy": s.is_busy,
                "enabled_agents": list(s.enabled_agents),
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

    def update_runtime_config(self, payload: dict, active_session_id: str = "") -> dict:
        if "workspace_dir" in payload and isinstance(payload["workspace_dir"], str):
            wdir = os.path.expanduser(payload["workspace_dir"].strip())
            if wdir:
                self.settings.workspace_dir = wdir
                for sid, s in self.sessions.items():
                    if sid == active_session_id or not s.topic:
                        s.workspace_dir = wdir
        if "allow_single_cli_fallback" in payload:
            self.settings.allow_single_cli_fallback = bool(payload["allow_single_cli_fallback"])
        updated_personas: Dict[str, str] = {}
        if "agents" in payload and isinstance(payload["agents"], dict):
            for aid, acfg in payload["agents"].items():
                if aid in self.settings.agents and isinstance(acfg, dict):
                    target = self.settings.agents[aid]
                    if "driver" in acfg and acfg["driver"] in VALID_DRIVERS:
                        target.driver = acfg["driver"]
                        target._cached_probe_path = ""
                    if "persona" in acfg and acfg["persona"] in VALID_PERSONAS:
                        target.persona = acfg["persona"]
                        target.title = PERSONA_PRESETS[target.persona]["short_tag"]
                        updated_personas[aid] = target.persona
                    if "custom_binary" in acfg:
                        target.custom_binary = str(acfg["custom_binary"]).strip()
                        target._cached_probe_path = ""
                    if "model" in acfg:
                        target.model = str(acfg["model"]).strip()
                    if "discussion_effort" in acfg:
                        raw_de = str(acfg.get("discussion_effort") or "").strip().lower()
                        if raw_de in VALID_EFFORT_LEVELS:
                            target.discussion_effort = raw_de
                    if "execution_effort" in acfg:
                        raw_ee = str(acfg.get("execution_effort") or "").strip().lower()
                        if raw_ee in VALID_EFFORT_LEVELS:
                            target.execution_effort = raw_ee
        self._normalize_agent_efforts()
        self._save_persisted_config()
        inspected = self.settings.inspect_status()
        for sid, sess in self.sessions.items():
            if updated_personas and (sid == active_session_id or not sess.topic):
                for aid, p_key in updated_personas.items():
                    sess.seat_personas[aid] = p_key
            self._sync_seat_readiness(sess, inspected=inspected)
        self._save_persisted_sessions()
        return {
            "workspace_dir": self.settings.workspace_dir,
            "workspace_is_git": is_git_workspace(self.settings.workspace_dir),
            "allow_single_cli_fallback": self.settings.allow_single_cli_fallback,
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
    ) -> dict:
        if enabled_agents is not None:
            valid = [aid for aid in AGENT_ORDER if aid in enabled_agents]
            if not valid:
                raise ValueError("至少需要保留一位参会席位")
            sess.enabled_agents = valid
            if len(valid) == 1:
                sess.executor_agent = valid[0]
            elif sess.executor_agent not in valid:
                sess.executor_agent = "astra" if "astra" in valid else valid[0]

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

        if executor_agent and executor_agent in AGENT_ORDER:
            sess.executor_agent = executor_agent
            if len(sess.enabled_agents) == 1 and executor_agent != sess.enabled_agents[0]:
                # 单席位独奏下若主动切换主刀人，自动将该主刀人加入参会避免矛盾
                sess.enabled_agents = [a for a in AGENT_ORDER if a in (sess.enabled_agents[0], executor_agent)]

        sess.updated_ts = time.time()
        self._sync_seat_readiness(sess)
        for st in sess.seat_states.values():
            await self.broadcast(sess, "seat_update", st)
        await self.broadcast(sess, "whiteboard_update", sess.whiteboard)
        await self._broadcast_meta(sess)
        self._save_persisted_sessions()
        return {
            "enabled_agents": list(sess.enabled_agents),
            "seat_personas": dict(sess.seat_personas),
            "executor_agent": sess.effective_executor_agent(),
            "seat_states": sess.seat_states,
        }

    async def update_whiteboard_manual(self, sess: MeetingSession, payload: dict) -> dict:
        wb = sess.whiteboard
        sess.updated_ts = time.time()
        if "topic" in payload and isinstance(payload["topic"], str):
            clean_t = payload["topic"].strip()
            if clean_t:
                short_t, _ = summarize_topic_and_constraints(clean_t)
                sess.topic = clean_t
                sess.title = short_t or (clean_t[:24] + ("…" if len(clean_t) > 24 else ""))
                wb["topic"] = clean_t
                wb["topic_title"] = short_t

        for key in WHITEBOARD_LIST_KEYS:
            if key in payload and isinstance(payload[key], list):
                wb[key] = [str(x).strip() for x in payload[key] if str(x).strip()][:16]

        op = payload.get("op")
        bucket_key = payload.get("bucket")
        if bucket_key in WHITEBOARD_LIST_KEYS:
            bucket: List[str] = wb.setdefault(bucket_key, [])
            if op == "add":
                txt = str(payload.get("text", "")).strip()
                if txt and txt not in bucket:
                    bucket.append(txt)
            elif op == "remove":
                idx = payload.get("index")
                if isinstance(idx, int) and 0 <= idx < len(bucket):
                    bucket.pop(idx)
            elif op == "update":
                idx = payload.get("index")
                txt = str(payload.get("text", "")).strip()
                if isinstance(idx, int) and 0 <= idx < len(bucket):
                    if txt:
                        bucket[idx] = txt
                    else:
                        bucket.pop(idx)

        wb["chair_constraints"] = dedupe_chair_constraints(
            sess.topic,
            wb.get("topic_title", ""),
            wb.get("chair_constraints", []),
        )
        await self.broadcast(sess, "whiteboard_update", wb)
        await self._broadcast_meta(sess)
        self._save_persisted_sessions()
        return wb

    def get_system_status(self) -> dict:
        return {
            "workspace_dir": self.settings.workspace_dir,
            "workspace_is_git": is_git_workspace(self.settings.workspace_dir),
            "allow_single_cli_fallback": self.settings.allow_single_cli_fallback,
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
        candidates = (
            [target_agent_id]
            if target_agent_id in AGENT_ORDER
            else list(AGENT_ORDER)
        )
        # 按底层驱动分组：不同 CLI 并发探活，同 CLI 串行留出 0.4s 缓冲避免并发抢占与限流误判
        groups: Dict[str, List[str]] = {}
        for aid in candidates:
            ov = overrides.get(aid) if isinstance(overrides.get(aid), dict) else None
            try:
                _, bpath, _, eff_drv, _ = self.runner._require_binary(aid, override=ov)
                gkey = bpath or eff_drv
            except Exception:
                gkey = f"missing_{aid}"
            groups.setdefault(gkey, []).append(aid)

        results_map: Dict[str, dict] = {}

        async def _run_ping_group(gkey: str, group_aids: List[str]) -> None:
            for idx, aid in enumerate(group_aids):
                if idx > 0 and not gkey.startswith("missing_"):
                    await asyncio.sleep(self.SINGLE_CLI_SERIAL_BUFFER_SEC)
                ov = overrides.get(aid) if isinstance(overrides.get(aid), dict) else None
                results_map[aid] = await self.runner.ping_agent(aid, override=ov)

        await asyncio.gather(*(_run_ping_group(gk, gaids) for gk, gaids in groups.items()))
        return {aid: results_map[aid] for aid in candidates if aid in results_map}

    async def broadcast(self, sess: MeetingSession, event_type: str, data: dict) -> None:
        packet = {"event": event_type, "data": data}
        dead: List[asyncio.Queue] = []
        for q in sess.subscribers:
            try:
                q.put_nowait(packet)
            except asyncio.QueueFull:
                dead.append(q)
        for q in dead:
            if q in sess.subscribers:
                sess.subscribers.remove(q)

    async def _broadcast_meta(self, sess: MeetingSession) -> None:
        eff_exec = sess.effective_executor_agent()
        sess.whiteboard["executor_agent"] = eff_exec
        eff_ws = sess.workspace_dir or self.settings.workspace_dir
        await self.broadcast(
            sess,
            "session_meta",
            {
                "stage": sess.stage,
                "title": sess.title,
                "topic": sess.topic,
                "workspace_dir": sess.workspace_dir,
                "workspace_is_git": is_git_workspace(eff_ws),
                "collab_mode": sess.collab_mode,
                "collab_mode_label": COLLAB_MODES.get(sess.collab_mode, {}).get("label", "标准讨论"),
                "is_busy": sess.is_busy,
                "enabled_agents": list(sess.enabled_agents),
                "seat_personas": dict(sess.seat_personas),
                "executor_agent": eff_exec,
                "consensus_status": sess.whiteboard.get("consensus_status", ""),
            },
        )

    async def cancel_active_flow(
        self,
        sess: MeetingSession,
        reason_tag: str = "已中断",
        persist: bool = True,
    ) -> None:
        if sess.active_task and not sess.active_task.done():
            sess.active_task.cancel()
            try:
                await sess.active_task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass
        sess.active_task = None
        for msg in sess.messages:
            if msg.get("streaming"):
                msg["streaming"] = False
                msg["badge"] = reason_tag
                await self.broadcast(sess, "msg_done", msg)
        self._sync_seat_readiness(sess)
        for aid, st in sess.seat_states.items():
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
    ) -> None:
        """
        统一收口流式任务结束状态：
        确保在广播最终 session_meta 前清理 active_task 与残留的非 idle 席位/流式消息，
        彻底消除单席报错或正常结束后状态栏卡在“讨论进行中”的矛盾。
        """
        if owner_task is None or sess.active_task is owner_task:
            sess.active_task = None
        for msg in sess.messages:
            if msg.get("streaming"):
                msg["streaming"] = False
                msg["badge"] = msg.get("badge") or "已结束"
                await self.broadcast(sess, "msg_done", msg)
        for _, st in sess.seat_states.items():
            if st["status"] in ("thinking", "speaking", "queued", "executing"):
                st["status"] = "idle"
                if st.get("badge") in ("思考中", "发言中", "调用中", "排队等待发言…", "汇总决议中"):
                    st["badge"] = "已就绪" if st.get("binary_ready") else "未检测到 CLI"
                await self.broadcast(sess, "seat_update", st)

    async def stop_session_flow(self, sess: MeetingSession) -> None:
        was_busy = sess.is_busy
        was_exec = sess.stage == "executing"
        await self.cancel_active_flow(sess, reason_tag="手动停止")
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
                    "已中止当前执行任务。您可以调整白板约束或重新触发执行。"
                    if was_exec
                    else "已停止当前发言生成。您可以补充要求继续追问、切换席位身份发言，或直接形成决议。"
                ),
                badge="已停止",
            )

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
        """根据参会席位所选预设身份动态选出收敛人（优先架构规划/全栈主程，其次 Carbon 或顺位首席）。"""
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

    def _resolve_driver_groups(
        self,
        sess: MeetingSession,
        agent_ids: List[str],
    ) -> Tuple[Dict[str, List[str]], Dict[str, bool], str]:
        """
        按底层生效 CLI 驱动对本批参会席位分组：
        - 不同底层 CLI 驱动返回独立分组以保持高吞吐并发；
        - 绑定到同一底层 CLI 驱动的多个席位自动归入同一串行组，标记无状态调用（stateless=True）并生成角色阵容说明。
        """
        inspected = self.settings.inspect_status()
        # 统计整场已启用且就绪席位是否共享底层驱动（即便当前子步仅单人收敛也保持无状态防串台）
        session_drv_counts: Dict[str, int] = {}
        for en_aid in sess.enabled_agents:
            info = inspected.get(en_aid) or {}
            if info.get("binary_detected"):
                gk = info.get("binary_path") or info.get("effective_driver") or en_aid
                session_drv_counts[gk] = session_drv_counts.get(gk, 0) + 1

        batch_groups: Dict[str, List[str]] = {}
        stateless_map: Dict[str, bool] = {}
        shared_seats: List[str] = []

        for en_aid in sess.enabled_agents:
            info = inspected.get(en_aid) or {}
            gk = (info.get("binary_path") or info.get("effective_driver") or en_aid) if info.get("binary_detected") else en_aid
            if session_drv_counts.get(gk, 0) > 1:
                p_label = get_persona_spec(sess.seat_personas.get(en_aid, ""), en_aid)["label"]
                shared_seats.append(f"{AGENT_META[en_aid]['name']}（{p_label}）")

        for aid in agent_ids:
            info = inspected.get(aid) or {}
            gk = (info.get("binary_path") or info.get("effective_driver") or aid) if info.get("binary_detected") else f"solo_{aid}"
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
    ) -> List[Tuple[bool, Optional[str], str, Optional[bool]]]:
        """
        混合并发/串行批次调度器：
        - 不同 CLI 驱动之间并发运行；
        - 共用同一 CLI 驱动的多个席位自动切换为无状态串行分次调用，未轮到席位显示「排队等待发言…」，席位间留 0.4s 缓冲。
        """
        if not agent_ids:
            return []
        batch_groups, stateless_map, roster_desc = self._resolve_driver_groups(sess, agent_ids)
        outcomes_by_agent: Dict[str, Tuple[bool, Optional[str], str, Optional[bool]]] = {}

        for _, gaids in batch_groups.items():
            if len(gaids) > 1:
                for waiting_aid in gaids[1:]:
                    await self._set_seat(sess, waiting_aid, "queued", "排队等待发言…")

        async def _run_group(gkey: str, gaids: List[str]) -> None:
            is_shared = any(stateless_map.get(a, False) for a in gaids)
            for idx, aid in enumerate(gaids):
                if is_shared or idx > 0:
                    await self._await_driver_buffer(gkey)
                res = await self._run_single_agent_turn(
                    sess,
                    aid,
                    stage_key,
                    phase_label,
                    is_solo_mode=is_solo_mode,
                    stateless=stateless_map.get(aid, False),
                    shared_cli_roster=roster_desc if stateless_map.get(aid, False) else "",
                )
                if is_shared or len(gaids) > 1:
                    self._last_driver_finish_ts[gkey] = time.monotonic()
                outcomes_by_agent[aid] = res

        await asyncio.gather(*(_run_group(gk, gaids) for gk, gaids in batch_groups.items()))
        return [outcomes_by_agent[aid] for aid in agent_ids]

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
    ) -> Tuple[bool, Optional[str], str, Optional[bool]]:
        meta = AGENT_META[agent_id]
        p_key = sess.seat_personas.get(agent_id) or DEFAULT_SEAT_PERSONAS[agent_id]
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

        await self._set_seat(sess, agent_id, "thinking", "汇总决议中" if stage_key == "synthesis" else "思考中")

        completed_msgs = [
            {"speaker": m["speaker_name"], "content": m["content"]}
            for m in sess.messages
            if m is not existing_msg_obj
            and not m.get("streaming")
            and not m.get("error")
            and m.get("content")
            and m.get("speaker") != "system"
        ]
        recent_snapshot = completed_msgs[-80:]

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
                    "streaming": True,
                    "error": False,
                    "error_kind": "",
                    "error_detail": "",
                    "timestamp": now_hhmmss(),
                }
            )
        else:
            msg_id = f"m_{uuid.uuid4().hex[:8]}"
            msg_obj = {
                "id": msg_id,
                "speaker": agent_id,
                "speaker_name": meta["name"],
                "role_title": pspec["label"],
                "phase_label": phase_label,
                "content": "",
                "badge": "调用中",
                "target": None,
                "ttft_ms": 0,
                "elapsed_ms": 0,
                "streaming": True,
                "error": False,
                "error_kind": "",
                "error_detail": "",
                "retry_stage": stage_key,
                "retry_phase": phase_label,
                "retry_cue": cue_instruction,
                "timestamp": now_hhmmss(),
            }
            sess.messages.append(msg_obj)
        await self.broadcast(sess, "msg_start", msg_obj)

        first_chunk = True
        called_target: Optional[str] = None
        final_badge = ""
        consensus_flag: Optional[bool] = None
        try:
            turn_kwargs = dict(
                session_id=sess.session_id,
                agent_id=agent_id,
                stage=stage_key,
                topic=sess.topic,
                collab_mode=COLLAB_MODES.get(sess.collab_mode, {}).get("label", "标准讨论"),
                whiteboard=sess.whiteboard,
                recent_messages=recent_snapshot,
                cue_instruction=cue_instruction,
                all_completed_count=len(completed_msgs),
                session_workspace=sess.workspace_dir or self.settings.workspace_dir,
                persona_key=p_key,
                is_solo_mode=is_solo_mode,
                stateless=use_stateless,
                shared_cli_roster=use_roster,
            )
            try:
                stream_gen = self.runner.stream_discussion_turn(**turn_kwargs)
            except TypeError:
                turn_kwargs.pop("stateless", None)
                turn_kwargs.pop("shared_cli_roster", None)
                stream_gen = self.runner.stream_discussion_turn(**turn_kwargs)

            async for ev in stream_gen:
                etype = ev.get("type")
                if etype == "delta":
                    if first_chunk:
                        first_chunk = False
                        await self._set_seat(sess, agent_id, "speaking", "发言中")
                    msg_obj["content"] += ev["text"]
                    await self.broadcast(sess, "msg_delta", {"id": msg_id, "delta": ev["text"]})
                elif etype == "done":
                    called_target = ev.get("target")
                    final_badge = ev.get("badge", "")
                    consensus_flag = ev.get("consensus")
                    structured_pts = ev.get("wb_points") or []
                    msg_obj["content"] = ev["full_text"]
                    msg_obj["badge"] = final_badge
                    msg_obj["target"] = called_target
                    msg_obj["ttft_ms"] = ev["ttft_ms"]
                    msg_obj["elapsed_ms"] = ev["elapsed_ms"]
                    msg_obj["streaming"] = False
                    msg_obj["error"] = False
                    msg_obj["error_kind"] = ""
                    msg_obj["error_detail"] = ""
                    sess.updated_ts = time.time()
                    await self.broadcast(sess, "msg_done", msg_obj)
                    await self._set_seat(
                        sess,
                        agent_id,
                        "idle",
                        final_badge,
                        ttft_ms=ev["ttft_ms"],
                        elapsed_ms=ev["elapsed_ms"],
                    )
                    if ingest_whiteboard:
                        self._ingest_into_whiteboard(
                            sess,
                            agent_id,
                            ev["full_text"],
                            structured_pts=structured_pts,
                        )
                        await self.broadcast(sess, "whiteboard_update", sess.whiteboard)
                    self._save_persisted_sessions()
            if use_stateless and batch_groups:
                for gk in batch_groups:
                    self._last_driver_finish_ts[gk] = time.monotonic()
            return True, called_target, final_badge, consensus_flag
        except asyncio.CancelledError:
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
            msg_obj["streaming"] = False
            msg_obj["error"] = True
            msg_obj["error_kind"] = exc.error_kind
            msg_obj["error_detail"] = "\n".join(diag_lines).strip()
            msg_obj["retry_stage"] = stage_key
            msg_obj["retry_phase"] = phase_label
            msg_obj["retry_cue"] = cue_instruction
            msg_obj["content"] = str(exc)
            msg_obj["badge"] = err_badge
            await self.broadcast(sess, "msg_done", msg_obj)
            await self._set_seat(sess, agent_id, "idle", err_badge)
            self._save_persisted_sessions()
            return False, None, err_badge, None
        except Exception as exc:
            msg_obj["streaming"] = False
            msg_obj["error"] = True
            msg_obj["error_kind"] = "process_error"
            msg_obj["error_detail"] = str(exc)[:1600]
            msg_obj["retry_stage"] = stage_key
            msg_obj["retry_phase"] = phase_label
            msg_obj["retry_cue"] = cue_instruction
            msg_obj["content"] = str(exc)
            msg_obj["badge"] = "调用异常"
            await self.broadcast(sess, "msg_done", msg_obj)
            await self._set_seat(sess, agent_id, "idle", "调用异常")
            self._save_persisted_sessions()
            return False, None, "调用异常", None

    async def retry_agent_turn(
        self,
        sess: MeetingSession,
        agent_id: str,
        message_id: str = "",
    ) -> None:
        """针对报错席位执行单席就地重试，无需重跑整轮会议。"""
        if agent_id not in AGENT_META:
            return
        await self.cancel_active_flow(sess, reason_tag=f"单席重试 {AGENT_META[agent_id]['name']}")
        target_msg: Optional[dict] = None
        if message_id:
            for m in reversed(sess.messages):
                if m.get("id") == message_id and m.get("speaker") == agent_id:
                    target_msg = m
                    break
        if target_msg is None:
            for m in reversed(sess.messages):
                if m.get("speaker") == agent_id and m.get("error"):
                    target_msg = m
                    break
        sess.active_task = asyncio.create_task(self._run_retry_flow(sess, agent_id, target_msg))
        await self._broadcast_meta(sess)

    async def _run_retry_flow(
        self,
        sess: MeetingSession,
        agent_id: str,
        target_msg: Optional[dict],
    ) -> None:
        owner_task = asyncio.current_task()
        try:
            stage_key = str((target_msg or {}).get("retry_stage") or "opening")
            phase_label = str((target_msg or {}).get("retry_phase") or "单席重试")
            cue_ins = str((target_msg or {}).get("retry_cue") or "")
            await self._set_stage(sess, "chair_interrupt", f"{AGENT_META[agent_id]['name']} 单席重试中…")
            ok, _, err_badge, _ = await self._run_single_agent_turn(
                sess,
                agent_id,
                stage_key,
                phase_label,
                cue_instruction=cue_ins,
                is_solo_mode=len(sess.enabled_agents) == 1,
                existing_msg_obj=target_msg,
            )
            await self._finalize_task_idle_state(sess, owner_task)
            if ok:
                await self._set_stage(sess, "awaiting_chair", f"{AGENT_META[agent_id]['name']} 重试已完成，待主持人推进")
            else:
                await self._set_stage(
                    sess,
                    "awaiting_chair",
                    f"{AGENT_META[agent_id]['name']} 重试未通过（{err_badge or '异常'}），可查看报错详情或调整配置",
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
                if len(candidate) >= 6 and not _CONVERSATIONAL_NOISE_PREFIX.match(candidate):
                    points.append(cls._smart_clip(candidate))

        if points:
            return points[:max_items]

        numbered = re.findall(r"(?:[1-4①②③④]\s*[\)）、.]|[一二三四]是)\s*([^；;。！!\n]{6,160})", cleaned)
        valid_num = [
            cls._smart_clip(s)
            for s in numbered
            if not _CONVERSATIONAL_NOISE_PREFIX.match(s.strip())
        ]
        if valid_num:
            return valid_num[:max_items]

        sentences = [
            cls._smart_clip(s)
            for s in re.split(r"[。！？!\n；;]+", cleaned)
            if len(s.strip()) >= 10 and not _CONVERSATIONAL_NOISE_PREFIX.match(s.strip())
        ]
        return sentences[:max_items]

    def _ingest_into_whiteboard(
        self,
        sess: MeetingSession,
        agent_id: str,
        text: str,
        structured_pts: Optional[List[str]] = None,
    ) -> None:
        pts = list(structured_pts) if structured_pts else self._extract_key_points(text, max_items=2)
        if not pts:
            return
        key_map = {"carbon": "carbon_plan", "grok": "grok_risks", "astra": "astra_actions"}
        bucket: List[str] = sess.whiteboard[key_map[agent_id]]
        for p in pts:
            norm_prefix = re.sub(r"[^\w\u4e00-\u9fa5]", "", p)[:14]
            replaced = False
            if len(norm_prefix) >= 8:
                for i, existing in enumerate(bucket):
                    ex_prefix = re.sub(r"[^\w\u4e00-\u9fa5]", "", existing)[:14]
                    if ex_prefix == norm_prefix:
                        bucket[i] = p
                        replaced = True
                        break
            if not replaced and p not in bucket:
                bucket.append(p)
        if len(bucket) > 12:
            del bucket[:-12]

    async def start_topic_meeting(
        self,
        sess: MeetingSession,
        topic: str,
        collab_mode: Optional[str] = None,
        enabled_agents: Optional[List[str]] = None,
        seat_personas: Optional[Dict[str, str]] = None,
        executor_agent: Optional[str] = None,
        reset_history: bool = False,
    ) -> None:
        await self.cancel_active_flow(sess, reason_tag="切换新议题")
        await self.runner.reset_session_context(sess.session_id)
        if reset_history:
            sess.messages = []
            await self.broadcast(sess, "session_cleared", {"session_id": sess.session_id})
        if enabled_agents:
            valid = [aid for aid in AGENT_ORDER if aid in enabled_agents]
            if valid:
                sess.enabled_agents = valid
        if isinstance(seat_personas, dict):
            for aid, p_key in seat_personas.items():
                if aid in AGENT_ORDER and p_key in VALID_PERSONAS:
                    sess.seat_personas[aid] = p_key
        if executor_agent and executor_agent in AGENT_ORDER:
            sess.executor_agent = executor_agent
        if not sess.workspace_dir:
            sess.workspace_dir = self.settings.workspace_dir
        self._sync_seat_readiness(sess)
        sess.topic = topic.strip()
        short_title, initial_constraints = summarize_topic_and_constraints(sess.topic)
        sess.title = short_title or (sess.topic[:24] + ("…" if len(sess.topic) > 24 else ""))
        if collab_mode and collab_mode in COLLAB_MODES:
            sess.collab_mode = collab_mode
        sess.whiteboard = {
            "topic": sess.topic,
            "topic_title": sess.title,
            "consensus_status": "会议进行中",
            "chair_constraints": dedupe_chair_constraints(sess.topic, sess.title, initial_constraints),
            "carbon_plan": [],
            "grok_risks": [],
            "astra_actions": [],
            "exec_logs": [],
            "exec_diff": "",
            "exec_summary": "",
            "executor_agent": sess.effective_executor_agent(),
            "can_rollback": bool(sess.last_backup),
        }
        await self.broadcast(sess, "whiteboard_update", sess.whiteboard)

        await self._append_non_agent_message(
            sess,
            speaker="chair",
            speaker_name="主持人",
            role_title="发起议题",
            phase_label="议题",
            content=sess.topic,
            badge=COLLAB_MODES[sess.collab_mode]["label"],
        )

        sess.active_task = asyncio.create_task(self._orchestrate_full_meeting(sess))
        await self._broadcast_meta(sess)

    @staticmethod
    def _is_round_converged(
        round_outcomes: List[Tuple[bool, Optional[str], str, Optional[bool]]],
        collab_mode: str,
    ) -> bool:
        if collab_mode == "red_blue_debate" or not round_outcomes:
            return False
        for ok, tgt, badge, cons_flag in round_outcomes:
            if not ok or tgt is not None:
                return False
            if cons_flag is False:
                return False
            if cons_flag is None and any(kw in (badge or "") for kw in DISAGREEMENT_KEYWORDS):
                return False
        return True

    async def _orchestrate_full_meeting(self, sess: MeetingSession) -> None:
        owner_task = asyncio.current_task()
        try:
            ready_agents, missing_agents = self._get_ready_enabled_agents(sess)
            if not ready_agents:
                missing_names = "、".join(
                    f"{AGENT_META[a]['name']} ({AGENT_META[a]['cli']})" for a in (missing_agents or sess.enabled_agents)
                )
                await self._append_non_agent_message(
                    sess,
                    speaker="system",
                    speaker_name="环境提示",
                    role_title="CLI 检测",
                    phase_label="未就绪",
                    content=(
                        f"当前参会席位均未检测到可用的本地 CLI：{missing_names}。\n"
                        f"请点击左侧栏 **「配置」** 指定可执行文件路径（或一键启用「单 CLI 分饰三席」），完成后点击 **「实测连通」**。"
                    ),
                    badge="需配置 CLI",
                    error=True,
                )
                await self._finalize_task_idle_state(sess, owner_task)
                await self._set_stage(sess, "idle", "CLI 未就绪，请检查配置")
                return

            if missing_agents:
                skipped_str = "、".join(f"{AGENT_META[a]['name']}" for a in missing_agents)
                for ma in missing_agents:
                    await self._set_seat(sess, ma, "idle", "未安装 · 已跳过")
                await self._append_non_agent_message(
                    sess,
                    speaker="system",
                    speaker_name="系统",
                    role_title="席位调度",
                    phase_label="自动跳过",
                    content=f"已自动跳过未检测到本地 CLI 的席位（{skipped_str}），由其余已就绪成员继续推进讨论。",
                    badge="弹性参会",
                )

            solo_mode = len(ready_agents) == 1
            if solo_mode:
                solo_name = AGENT_META[ready_agents[0]]["name"]
                await self._set_stage(sess, "opening_parallel", f"第 1 阶段：{solo_name} 独奏方案设计")
                opening_outcomes = [
                    await self._run_single_agent_turn(
                        sess,
                        ready_agents[0],
                        "opening",
                        "独奏设计",
                        is_solo_mode=True,
                    )
                ]
            else:
                drv_groups, _, _ = self._resolve_driver_groups(sess, ready_agents)
                is_single_cli_multi = len(drv_groups) == 1 and len(ready_agents) > 1
                stage_banner = (
                    f"第 1 阶段：单 CLI 分饰 {len(ready_agents)} 席轮流初评"
                    if is_single_cli_multi
                    else f"第 1 阶段：{len(ready_agents)} 方初评"
                )
                phase_lbl = "首轮初评" if is_single_cli_multi else "并发初评"
                await self._set_stage(sess, "opening_parallel", stage_banner)
                opening_outcomes = await self._run_agent_batch(
                    sess,
                    ready_agents,
                    "opening",
                    phase_lbl,
                    is_solo_mode=False,
                )

            active_agents = [aid for aid, (ok, _, _, _) in zip(ready_agents, opening_outcomes) if ok]
            failed_agents = [aid for aid, (ok, _, _, _) in zip(ready_agents, opening_outcomes) if not ok]
            if not active_agents:
                await self._finalize_task_idle_state(sess, owner_task)
                await self._set_stage(sess, "awaiting_chair", "初评未完成，请查看卡片报错详情或点击单席重试")
                return

            priority_target: Optional[str] = None
            for _, tgt, _, _ in opening_outcomes:
                if tgt in active_agents:
                    priority_target = tgt
                    break

            total_rounds = COLLAB_MODES.get(sess.collab_mode, {}).get("rounds", 2)
            if len(active_agents) > 1:
                lead_agent = self._pick_lead_synthesizer(sess, active_agents)
                for r in range(1, total_rounds + 1):
                    await self._set_stage(sess, "cross_talk", f"第 2 阶段：交叉讨论（{r}/{total_rounds}）")
                    round_outcomes: List[Tuple[bool, Optional[str], str, Optional[bool]]] = []

                    others = [a for a in active_agents if a != lead_agent] if lead_agent else list(active_agents)

                    if lead_agent and others and priority_target == lead_agent:
                        res_lead = await self._run_single_agent_turn(sess, lead_agent, "cross_talk", f"第{r}轮回应")
                        round_outcomes.append(res_lead)
                        res_others = await self._run_agent_batch(sess, others, "cross_talk", f"第{r}轮讨论")
                        round_outcomes.extend(res_others)
                    elif lead_agent and others:
                        res_others = await self._run_agent_batch(sess, others, "cross_talk", f"第{r}轮质询")
                        round_outcomes.extend(res_others)
                        res_lead = await self._run_single_agent_turn(sess, lead_agent, "cross_talk", f"第{r}轮收敛")
                        round_outcomes.append(res_lead)
                    else:
                        order = list(active_agents)
                        if priority_target in order:
                            order.remove(priority_target)
                            order.insert(0, priority_target)
                        res_all = await self._run_agent_batch(sess, order, "cross_talk", f"第{r}轮讨论")
                        round_outcomes.extend(res_all)

                    priority_target = None
                    for ok, nxt, _, _ in reversed(round_outcomes):
                        if ok and nxt in active_agents:
                            priority_target = nxt
                            break

                    if r < total_rounds and self._is_round_converged(round_outcomes, sess.collab_mode):
                        break

            if sess.collab_mode == "arch_to_exec" and active_agents:
                exec_aid = sess.effective_executor_agent()
                if exec_aid not in active_agents:
                    exec_aid = active_agents[-1]
                await self._finalize_consensus_internal(sess, clear_task_on_exit=False)
                await self._execute_agent_internal(
                    sess,
                    allow_workspace_write=False,
                    executor_id=exec_aid,
                    clear_task_on_exit=True,
                )
            else:
                await self._finalize_task_idle_state(sess, owner_task)
                exec_name = AGENT_META[sess.effective_executor_agent()]["name"]
                if failed_agents:
                    failed_names = "、".join(AGENT_META[a]["name"] for a in failed_agents)
                    status_hint = f"本轮已结束（{failed_names} 可单席重试），待主持人推进"
                elif len(active_agents) == 1 and solo_mode:
                    status_hint = f"独奏方案就绪，可追问打磨或交由 {exec_name} 执行"
                else:
                    status_hint = "讨论完成，待主持人决议或追问"
                await self._set_stage(sess, "awaiting_chair", status_hint)
        except asyncio.CancelledError:
            raise
        finally:
            await self._finalize_task_idle_state(sess, owner_task)
            self._save_persisted_sessions(immediate=True)
            await self._broadcast_meta(sess)

    async def chair_interrupt(self, sess: MeetingSession, message: str) -> None:
        clean_msg = message.strip()
        if not clean_msg:
            return
        was_busy = sess.is_busy
        await self.cancel_active_flow(sess, reason_tag="主持人插话" if was_busy else "补充追问")
        if not sess.topic:
            await self.start_topic_meeting(sess, clean_msg)
            return

        sess.whiteboard["chair_constraints"] = dedupe_chair_constraints(
            sess.topic,
            sess.whiteboard.get("topic_title", ""),
            list(sess.whiteboard.get("chair_constraints", [])) + [clean_msg],
        )
        await self.broadcast(sess, "whiteboard_update", sess.whiteboard)

        await self._append_non_agent_message(
            sess,
            speaker="chair",
            speaker_name="主持人",
            role_title="插话控场" if was_busy else "补充追问",
            phase_label="插话" if was_busy else "追问",
            content=clean_msg,
            badge="新约束" if was_busy else "继续讨论",
        )

        mentioned = [aid for aid in AGENT_ORDER if f"@{aid}" in clean_msg.lower()]
        sess.active_task = asyncio.create_task(self._handle_interrupt_alignment(sess, mentioned))
        await self._broadcast_meta(sess)

    async def _handle_interrupt_alignment(self, sess: MeetingSession, mentioned: List[str]) -> None:
        owner_task = asyncio.current_task()
        try:
            await self._set_stage(sess, "chair_interrupt", "响应主持人指示中")
            ready_agents, _ = self._get_ready_enabled_agents(sess)
            targets = mentioned if mentioned else ready_agents
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
        await self.cancel_active_flow(sess, reason_tag=f"点名 {AGENT_META[agent_id]['name']}")
        if not sess.topic:
            sess.topic = instruction.strip() or "专项讨论"
            short_t, _ = summarize_topic_and_constraints(sess.topic)
            sess.title = short_t or (sess.topic[:24] + ("…" if len(sess.topic) > 24 else ""))
            sess.whiteboard["topic"] = sess.topic
            sess.whiteboard["topic_title"] = sess.title
            await self.broadcast(sess, "whiteboard_update", sess.whiteboard)
        await self._append_non_agent_message(
            sess,
            speaker="chair",
            speaker_name="主持人",
            role_title="点名提问",
            phase_label="点名",
            content=f"@{AGENT_META[agent_id]['name']} {instruction}",
        )
        sess.active_task = asyncio.create_task(self._run_cue_flow(sess, agent_id, instruction))
        await self._broadcast_meta(sess)

    async def _run_cue_flow(self, sess: MeetingSession, agent_id: str, instruction: str) -> None:
        owner_task = asyncio.current_task()
        try:
            await self._set_stage(sess, "chair_interrupt", f"{AGENT_META[agent_id]['name']} 专项回应中")
            await self._run_single_agent_turn(
                sess,
                agent_id,
                "cue",
                "点名回应",
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
            await self._set_stage(sess, "concluded", "正在汇总会议决议…")
            ready_agents, _ = self._get_ready_enabled_agents(sess)
            synthesizer = self._pick_lead_synthesizer(sess, ready_agents) or (ready_agents[0] if ready_agents else None)

            synthesized_ok = False
            if synthesizer and sess.messages:
                synth_cue = (
                    "请基于以上完整会议讨论记录、白板要点与主持约束，输出一份完整详尽的《会议最终决议》：\n"
                    "1) 核心架构结论与明确取舍；\n"
                    "2) 分阶段、文件级的具体实施方案与关键代码/接口改动清单；\n"
                    "3) 边界风险防线与验收验证标准。"
                )
                ok, _, _, _ = await self._run_single_agent_turn(
                    sess,
                    synthesizer,
                    "synthesis",
                    "最终决议",
                    cue_instruction=synth_cue,
                    ingest_whiteboard=True,
                    is_solo_mode=len(ready_agents) == 1,
                )
                synthesized_ok = ok

            if not synthesized_ok:
                c_title = get_persona_spec(sess.seat_personas.get("carbon", ""), "carbon")["wb_title"]
                g_title = get_persona_spec(sess.seat_personas.get("grok", ""), "grok")["wb_title"]
                a_title = get_persona_spec(sess.seat_personas.get("astra", ""), "astra")["wb_title"]
                plan_lines = "\n".join(f"  - {x}" for x in sess.whiteboard["carbon_plan"][:8]) or "  - 暂无记录"
                risk_lines = "\n".join(f"  - {x}" for x in sess.whiteboard["grok_risks"][:8]) or "  - 暂无记录"
                act_lines = "\n".join(f"  - {x}" for x in sess.whiteboard["astra_actions"][:8]) or "  - 暂无记录"
                summary_md = (
                    f"**会议决议归档：{sess.title or sess.topic}**\n\n"
                    f"**Carbon · {c_title}**\n{plan_lines}\n\n"
                    f"**Grok · {g_title}**\n{risk_lines}\n\n"
                    f"**Astra · {a_title}**\n{act_lines}"
                )
                await self._append_non_agent_message(
                    sess,
                    speaker="system",
                    speaker_name="会议纪要",
                    role_title="决议归档",
                    phase_label="决议",
                    content=summary_md,
                    badge="已锁定",
                )

            if clear_task_on_exit:
                await self._finalize_task_idle_state(sess, owner_task)
            exec_name = AGENT_META[sess.effective_executor_agent()]["name"]
            await self._set_stage(sess, "concluded", f"已形成决议 · 可导出或交由 {exec_name} 执行")
            await self.broadcast(sess, "whiteboard_update", sess.whiteboard)
        except asyncio.CancelledError:
            raise
        finally:
            if clear_task_on_exit:
                await self._finalize_task_idle_state(sess, owner_task)
                self._save_persisted_sessions(immediate=True)
                await self._broadcast_meta(sess)

    async def trigger_astra_execution(
        self,
        sess: MeetingSession,
        allow_workspace_write: bool = False,
        executor_id: Optional[str] = None,
    ) -> None:
        await self.cancel_active_flow(sess, reason_tag="切换执行阶段")
        target_exec = executor_id if executor_id in AGENT_ORDER else sess.effective_executor_agent()
        sess.executor_agent = target_exec
        sess.active_task = asyncio.create_task(
            self._execute_agent_internal(
                sess,
                allow_workspace_write=allow_workspace_write,
                executor_id=target_exec,
                clear_task_on_exit=True,
            )
        )
        await self._broadcast_meta(sess)

    async def rollback_session_execution(self, sess: MeetingSession) -> Tuple[bool, str]:
        if not sess.last_backup:
            return False, "当前会话暂无可回滚的写入快照"
        ok, msg = await self.runner.rollback_workspace_backup(sess.last_backup)
        if ok:
            sess.last_backup = None
            sess.whiteboard["can_rollback"] = False
            sess.whiteboard["exec_logs"].append(f"↺ {msg}")
            sess.whiteboard["exec_diff"] = ""
            await self.broadcast(sess, "term_log", {"line": f"↺ {msg}"})
            await self.broadcast(sess, "whiteboard_update", sess.whiteboard)
            await self._append_non_agent_message(
                sess,
                speaker="system",
                speaker_name="Git 护栏",
                role_title="工作区回滚",
                phase_label="已回滚",
                content=msg,
                badge="已恢复",
            )
            self._save_persisted_sessions()
        return ok, msg

    async def _execute_agent_internal(
        self,
        sess: MeetingSession,
        allow_workspace_write: bool,
        executor_id: Optional[str] = None,
        clear_task_on_exit: bool = True,
    ) -> None:
        owner_task = asyncio.current_task()
        exec_aid = executor_id if executor_id in AGENT_ORDER else sess.effective_executor_agent()
        exec_name = AGENT_META[exec_aid]["name"]
        p_key = sess.seat_personas.get(exec_aid) or DEFAULT_SEAT_PERSONAS[exec_aid]
        pspec = get_persona_spec(p_key, fallback_agent_id=exec_aid)
        eff_ws = sess.workspace_dir or self.settings.workspace_dir
        mode_tag = "写入本地项目" if allow_workspace_write else "只读预演/方案交付"

        sess.executor_agent = exec_aid
        sess.whiteboard["executor_agent"] = exec_aid
        await self._set_stage(sess, "executing", f"{exec_name} 执行中（{mode_tag}）")
        await self._set_seat(sess, exec_aid, "executing", f"执行中·{mode_tag}")
        sess.whiteboard["exec_logs"] = []
        sess.whiteboard["exec_diff"] = ""

        if allow_workspace_write:
            backup = await self.runner.capture_workspace_backup(
                self.runner._effective_workspace_cwd(eff_ws)
            )
            sess.last_backup = backup
            sess.whiteboard["can_rollback"] = bool(backup)
            if backup:
                snap_line = "🛡 已建立本地 Git 执行前安全快照（支持一键回滚）"
            else:
                snap_line = "⚠ 当前目录未初始化 Git 仓库，写入将直接作用于磁盘文件（不支持一键 Git 回滚）"
            sess.whiteboard["exec_logs"].append(snap_line)
            await self.broadcast(sess, "term_log", {"line": snap_line})
        await self.broadcast(sess, "whiteboard_update", sess.whiteboard)

        exec_start_ts = time.perf_counter()
        exec_ttft_ms: Optional[int] = None
        msg_id = f"m_{uuid.uuid4().hex[:8]}"
        msg_obj = {
            "id": msg_id,
            "speaker": exec_aid,
            "speaker_name": exec_name,
            "role_title": f"{pspec['label']}·主刀执行",
            "phase_label": "执行交付",
            "content": "",
            "badge": mode_tag,
            "target": None,
            "ttft_ms": 0,
            "elapsed_ms": 0,
            "streaming": True,
            "error": False,
            "error_kind": "",
            "error_detail": "",
            "timestamp": now_hhmmss(),
        }
        sess.messages.append(msg_obj)
        await self.broadcast(sess, "msg_start", msg_obj)

        try:
            async for ev in self.runner.stream_agent_execution(
                topic=sess.topic or sess.title,
                whiteboard=sess.whiteboard,
                allow_workspace_write=allow_workspace_write,
                session_workspace=eff_ws,
                agent_id=exec_aid,
                persona_key=p_key,
            ):
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
                    elapsed_ms = int((time.perf_counter() - exec_start_ts) * 1000)
                    sess.whiteboard["exec_summary"] = ev["summary"]
                    sess.whiteboard["exec_diff"] = ev["diff"]
                    sess.whiteboard["can_rollback"] = bool(sess.last_backup and allow_workspace_write)
                    msg_obj["content"] = ev["summary"]
                    msg_obj["streaming"] = False
                    msg_obj["ttft_ms"] = exec_ttft_ms or elapsed_ms
                    msg_obj["elapsed_ms"] = elapsed_ms
                    msg_obj["badge"] = "已写入本地项目" if allow_workspace_write else "交付完成"
                    await self.broadcast(sess, "msg_done", msg_obj)
                    await self.broadcast(sess, "exec_artifact", ev)
                    await self.broadcast(sess, "whiteboard_update", sess.whiteboard)

            if msg_obj.get("streaming"):
                msg_obj["streaming"] = False
                msg_obj["elapsed_ms"] = int((time.perf_counter() - exec_start_ts) * 1000)
                msg_obj["badge"] = "交付完成"
                await self.broadcast(sess, "msg_done", msg_obj)

            await self._set_seat(sess, exec_aid, "idle", "执行完成", elapsed_ms=msg_obj["elapsed_ms"])
            if clear_task_on_exit:
                await self._finalize_task_idle_state(sess, owner_task)
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
            msg_obj["content"] = msg_obj["content"] + (f"\n\n{err_line}" if msg_obj["content"] else err_line)
            msg_obj["badge"] = err_badge
            await self.broadcast(sess, "msg_done", msg_obj)
            await self._set_seat(sess, exec_aid, "idle", err_badge)
            if clear_task_on_exit:
                await self._finalize_task_idle_state(sess, owner_task)
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
            if clear_task_on_exit:
                await self._finalize_task_idle_state(sess, owner_task)
            await self._set_stage(sess, "awaiting_chair", f"{exec_name} 执行未完成，请查看报错详情")
        finally:
            if clear_task_on_exit:
                await self._finalize_task_idle_state(sess, owner_task)
            self._save_persisted_sessions(immediate=True)
            await self._broadcast_meta(sess)
