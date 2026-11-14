/**
 * AI圆桌 — 前端实时工作台主控脚本
 * 模块化覆盖：
 * 1. 全链路专业术语规范与旧会话平滑兼容（deep_deliberation / adversarial_review / divergent_convergent / code_review / rapid_consensus + auto_preview_exec）
 * 2. 可配置运行与时限策略（深度推理不限时 / 标准均衡 / 自定义阈值）+ 实时中间状态流 + 15s 非阻塞「跳过本轮」+ 异常卡片三级恢复
 * 3. 三区结构化「会议白板」（已确认共识与约束 / 待决争议与风险项 / 待执行任务清单 + 勾选范围联动执行 + 乐观锁版本保护）
 * 4. 极简开局引导舱（5 大场景预设）+ 一体化席位配置浮层 + 60fps 合成器级微动效
 */

const STORAGE_KEYS = {
  theme: "ai_rt_theme",
  palette: "ai_rt_palette",
  fontsize: "ai_rt_fontsize",
  leftExpanded: "ai_rt_left_rail_expanded",
  rightHidden: "ai_rt_right_hidden",
};

const AGENT_ORDER = ["carbon", "grok", "astra"];

// AI_ROUNDTABLE_V2_UPGRADE_20261114
const AGENT_NAMES = {
  carbon: "架构师",
  grok: "审计官",
  astra: "工程师",
  chair: "主持人",
  system: "系统",
};

const AUTHOR_BADGE_META = {
  chair: { short: "主", name: "主持约束", cls: "badge-seat-chair" },
  carbon: { short: "架", name: "架构师", cls: "badge-seat-carbon" },
  grok: { short: "审", name: "审计官", cls: "badge-seat-grok" },
  astra: { short: "工", name: "工程师", cls: "badge-seat-astra" },
  system: { short: "系", name: "决议归档", cls: "badge-seat-system" },
};

const ROSTER_NAME_PRESETS = {
  role_experts: { label: "专业职能称呼", names: { carbon: "架构师", grok: "审计官", astra: "工程师" } },
  council_alpha: { label: "中立席位代号", names: { carbon: "Alpha", grok: "Beta", astra: "Gamma" } },
  product_studio: { label: "产品研发委员会", names: { carbon: "产品总监", grok: "红队审计", astra: "研发主程" } },
  auto_driver: { label: "跟随底层引擎", names: {} },
  classic: { label: "经典默认代号", names: { carbon: "Carbon", grok: "Grok", astra: "Astra" } },
};
const DEFAULT_ROSTER_PRESETS = ROSTER_NAME_PRESETS;

const DRIVER_LABELS = {
  agy: "Antigravity CLI",
  grok: "Grok CLI",
  codex: "Codex CLI",
  auto: "自动匹配 CLI",
};

const DRIVER_DEFAULTS = {
  agy: { model: "gemini-4-carbon", discussEffort: "high", execEffort: "high", listId: "agyModelPresets" },
  grok: { model: "grok-4.7", discussEffort: "xhigh", execEffort: "xhigh", listId: "grokModelPresets" },
  codex: { model: "gpt-6-astra", discussEffort: "max", execEffort: "max", listId: "codexModelPresets" },
  auto: { model: "", discussEffort: "high", execEffort: "high", listId: "" },
};

// 模块一：7 项规范角色职责预设
const PERSONA_ORDER = [
  "planner",
  "red_team",
  "implementer",
  "fullstack_solo",
  "product_ux",
  "perf_sre",
  "qa_audit",
];

const DEFAULT_PERSONA_PRESETS = {
  planner: {
    key: "planner",
    label: "架构规划",
    short_tag: "规划",
    wb_kind: "decision",
    cue_btn: "请 {name} 收敛方案",
    cue_prompt: "请整合各方分歧，收敛出清晰的阶段边界、架构取舍与优先级结论",
    desc: "拆解系统边界、权衡方案取舍并收敛实施优先级",
  },
  red_team: {
    key: "red_team",
    label: "风险审计",
    short_tag: "审计",
    wb_kind: "risk",
    cue_btn: "请 {name} 审计风险",
    cue_prompt: "请针对当前方案开展反向压力审计，指出隐性假设漏洞、并发竞态与极端边界反例",
    desc: "反向假设检验、排查并发竞态与失效边界反例",
  },
  implementer: {
    key: "implementer",
    label: "工程实现",
    short_tag: "工程",
    wb_kind: "action",
    cue_btn: "请 {name} 评估实现",
    cue_prompt: "请评估具体改动文件与函数范围、接口契约及最小验证步骤",
    desc: "定位改动文件范围、接口契约与可执行落地步骤",
  },
  fullstack_solo: {
    key: "fullstack_solo",
    label: "全栈架构",
    short_tag: "全栈",
    wb_kind: "decision",
    cue_btn: "请 {name} 深化设计",
    cue_prompt: "请统筹深化端到端架构设计、异常边界防线与文件级实施清单",
    desc: "统筹顶层架构设计、边界自检与端到端工程闭环",
  },
  product_ux: {
    key: "product_ux",
    label: "产品交互",
    short_tag: "交互",
    wb_kind: "action",
    cue_btn: "请 {name} 评估交互",
    cue_prompt: "请从用户高频路径、信息层级降噪与状态反馈维度给出交互改进方案",
    desc: "审视操作路径、信息密度降噪与状态反馈体验",
  },
  perf_sre: {
    key: "perf_sre",
    label: "性能与稳定性",
    short_tag: "性能",
    wb_kind: "risk",
    cue_btn: "请 {name} 评估性能",
    cue_prompt: "请排查延迟瓶颈、资源回收、并发锁竞争与超时熔断隐患",
    desc: "聚焦吞吐延迟、进程资源回收与超时容错护栏",
  },
  qa_audit: {
    key: "qa_audit",
    label: "测试与验证",
    short_tag: "验证",
    wb_kind: "action",
    cue_btn: "请 {name} 制定验证",
    cue_prompt: "请梳理正常流与异常边界验证矩阵、回归检查点及自动化测试命令",
    desc: "拆解极端输入、回归验证矩阵与自动化自检方案",
  },
};

const DEFAULT_SEAT_PERSONAS = {
  carbon: "planner",
  grok: "red_team",
  astra: "implementer",
};

// 模块一：5 项正式讨论策略 + 历史旧 key 映射
const COLLAB_MODES = {
  deep_deliberation: {
    label: "深度研讨",
    hint: "独立立论 → 交叉质询 → 定向答辩 → 架构裁定",
  },
  adversarial_review: {
    label: "正反辩证",
    hint: "主方案立论 → 反向压力审计 → 防御修正 → 综合裁定",
  },
  divergent_convergent: {
    label: "发散收敛",
    hint: "多维方案发散 → 可行性与成本评估 → 优选方案收敛",
  },
  code_review: {
    label: "代码审查",
    hint: "源码证据定位 → 调用链交叉核验 → 文件级修改方案",
  },
  rapid_consensus: {
    label: "快速合议",
    hint: "单轮要点直出 → 核心风险核对 → 生成执行清单",
  },
};

const LEGACY_COLLAB_MODE_MAP = {
  standard_roundtable: "deep_deliberation",
  red_blue_debate: "adversarial_review",
  fast_align: "rapid_consensus",
};

// 模块五：5 大开局引导舱场景预设
const SCENARIO_PRESETS = {
  arch_review: {
    key: "arch_review",
    label: "架构评审",
    collab_mode: "deep_deliberation",
    enabled_agents: ["carbon", "grok", "astra"],
    seat_personas: { carbon: "planner", grok: "red_team", astra: "implementer" },
    executor_agent: "astra",
  },
  proposal_debate: {
    key: "proposal_debate",
    label: "方案论证",
    collab_mode: "adversarial_review",
    enabled_agents: ["carbon", "grok", "astra"],
    seat_personas: { carbon: "planner", grok: "red_team", astra: "implementer" },
    executor_agent: "astra",
  },
  product_design: {
    key: "product_design",
    label: "产品设计",
    collab_mode: "divergent_convergent",
    enabled_agents: ["carbon", "grok", "astra"],
    seat_personas: { carbon: "product_ux", grok: "red_team", astra: "fullstack_solo" },
    executor_agent: "astra",
  },
  code_diagnosis: {
    key: "code_diagnosis",
    label: "源码诊断",
    collab_mode: "code_review",
    enabled_agents: ["carbon", "grok", "astra"],
    seat_personas: { carbon: "perf_sre", grok: "qa_audit", astra: "implementer" },
    executor_agent: "astra",
  },
  solo_focus: {
    key: "solo_focus",
    label: "单席专注",
    collab_mode: "rapid_consensus",
    solo: true,
  },
};

const PACING_PRESETS = {
  unrestricted: {
    idle_timeout_sec: 900,
    turn_timeout_sec: 0,
    max_ref_chars: 120000,
    desc: "空闲等待 900s · 单轮不限总时长 · 源码预算 120,000 字符",
  },
  standard: {
    idle_timeout_sec: 300,
    turn_timeout_sec: 600,
    max_ref_chars: 120000,
    desc: "空闲等待 300s · 单轮上限 600s · 源码预算 120,000 字符",
  },
};

const FALLBACK_MODEL_EFFORT_CATALOG = {
  agy: {
    "gemini-4-carbon": { allowed: ["low", "medium", "high"], default: "high", supports_effort: true },
    "gemini-4-argon": { allowed: ["low", "medium", "high"], default: "high", supports_effort: true },
    "gemini-4-hydrogen": { allowed: ["low", "medium", "high", "xhigh"], default: "xhigh", supports_effort: true },
    "orchestrator (carbon)": { allowed: [], default: "", supports_effort: false },
    "orchestrator (argon)": { allowed: [], default: "", supports_effort: false },
    "*": { allowed: ["low", "medium", "high"], default: "high", supports_effort: true },
  },
  grok: {
    "grok-4.7": { allowed: ["low", "medium", "high", "xhigh"], default: "xhigh", supports_effort: true },
    "*": { allowed: ["low", "medium", "high", "xhigh"], default: "xhigh", supports_effort: true },
  },
  codex: {
    "gpt-6-astra": { allowed: ["low", "medium", "high", "xhigh", "max"], default: "max", supports_effort: true },
    "gpt-6.1-sol": { allowed: ["low", "medium", "high", "xhigh"], default: "xhigh", supports_effort: true },
    "*": { allowed: ["low", "medium", "high", "xhigh", "max"], default: "max", supports_effort: true },
  },
};

const STAGE_LABELS = {
  idle: "待命",
  opening_parallel: "独立立论",
  cross_talk: "交叉质询",
  chair_interrupt: "定向回应",
  awaiting_chair: "待主持推进",
  concluded: "已形成决议",
  executing: "执行交付中",
};

const AT_TOKEN_GLOBAL_RE = /@([A-Za-z0-9_\u4e00-\u9fa5./-]+\.[A-Za-z0-9]{1,10})(?::[Ll]?(\d+)(?:-[Ll]?(\d+))?)?/g;

const state = {
  system: null,
  sessions: [],
  currentSessionId: null,
  sessionSearchQuery: "",
  stage: "idle",
  isBusy: false,
  topic: "",
  collabMode: "deep_deliberation",
  autoPreviewExec: false,
  enabledAgents: ["carbon", "grok", "astra"],
  seatPersonas: { ...DEFAULT_SEAT_PERSONAS },
  seatEfforts: {},
  executorAgent: "astra",
  sessionWorkspaceDir: "",
  workspaceBound: null,
  workspaceIsGit: false,
  seatStates: {},
  messages: new Map(),
  sendingSessions: new Set(),
  whiteboard: null,
  wbKnownItemIds: new Set(),
  lastWbTotalCount: 0,
  sse: null,
  sseReconnectTimer: null,
  userScrolledUp: false,
  activeTab: "whiteboard",
  cliTestResults: {},
  pingLatencyBySeat: {},
  expandedCliCard: null,
  personaPopoverSeat: null,
  execStartTs: 0,
  rosterPreset: "role_experts",
  singleCliConcurrency: 3,
  pacingMode: "unrestricted",
  idleTimeoutSec: 900,
  turnTimeoutSec: 0,
  maxRefChars: 120000,
  atMenu: {
    open: false,
    items: [],
    activeIndex: 0,
    tokenStart: -1,
    tokenEnd: -1,
    query: "",
    fetchTimer: null,
  },
  attachedFilesCache: new Map(),
};

const el = (id) => document.getElementById(id);

function escapeHtml(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function showToast(message, kind = "info", durationMs = 3000) {
  const box = el("toastContainer");
  if (!box) return;
  const item = document.createElement("div");
  const cls =
    kind === "ok"
      ? "toast-ok"
      : kind === "err"
      ? "toast-err"
      : kind === "warn"
      ? "toast-warn"
      : "";
  item.className = `toast-item ${cls}`.trim();
  item.textContent = message;
  box.appendChild(item);
  setTimeout(() => {
    item.style.opacity = "0";
    item.style.transform = "translateY(-4px)";
    item.style.transition = "opacity 160ms ease, transform 160ms ease";
    setTimeout(() => item.remove(), 180);
  }, durationMs);
}

async function apiFetch(path, options = {}) {
  const opts = {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  };
  const res = await fetch(path, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.error || `请求失败 (${res.status})`);
  }
  return data;
}

function getPersonaMap() {
  const serverPresets = state.system?.persona_presets;
  if (serverPresets && typeof serverPresets === "object") {
    const merged = {};
    for (const k of PERSONA_ORDER) {
      merged[k] = {
        ...(DEFAULT_PERSONA_PRESETS[k] || {}),
        ...(serverPresets[k] || {}),
      };
    }
    return merged;
  }
  return DEFAULT_PERSONA_PRESETS;
}

function getPersonaSpec(personaKey, fallbackSeat = "carbon") {
  const map = getPersonaMap();
  if (personaKey && map[personaKey]) return map[personaKey];
  const defKey = DEFAULT_SEAT_PERSONAS[fallbackSeat] || "planner";
  return map[defKey] || DEFAULT_PERSONA_PRESETS.planner;
}

function normalizeCollabModeAndAutoExec(rawMode, rawAutoExec) {
  let m = String(rawMode || "").trim();
  let autoExec = typeof rawAutoExec === "boolean" ? rawAutoExec : state.autoPreviewExec;
  if (m === "arch_to_exec") {
    m = "rapid_consensus";
    autoExec = true;
  } else if (LEGACY_COLLAB_MODE_MAP[m]) {
    m = LEGACY_COLLAB_MODE_MAP[m];
  }
  if (!COLLAB_MODES[m]) {
    m = "deep_deliberation";
  }
  return { mode: m, autoPreviewExec: Boolean(autoExec) };
}

function effectiveWorkspacePath() {
  if ((state.workspaceBound ?? state.system?.workspace_bound) === false) return "";
  return (state.sessionWorkspaceDir || state.system?.workspace_dir || "").trim();
}

function pickPreferredSoloSeat() {
  const agents = state.system?.agents || {};
  for (const cand of ["astra", "carbon", "grok"]) {
    if (agents[cand]?.binary_detected || state.seatStates[cand]?.binary_ready) {
      return cand;
    }
  }
  return "carbon";
}

/* ==================== 外观、侧栏与工作台布局控制 ==================== */

function applyTheme(theme) {
  const next = theme === "dark" ? "dark" : "light";
  document.documentElement.setAttribute("data-theme", next);
  localStorage.setItem(STORAGE_KEYS.theme, next);
  document.querySelectorAll("[data-theme-opt]").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.themeOpt === next);
  });
  const paletteSec = el("paletteSection");
  if (paletteSec) {
    paletteSec.style.opacity = next === "dark" ? "0.45" : "1";
    paletteSec.style.pointerEvents = next === "dark" ? "none" : "auto";
  }
}

function applyPalette(palette) {
  const valid = ["pearl", "alabaster", "glacier", "sage"];
  const next = valid.includes(palette) ? palette : "pearl";
  document.documentElement.setAttribute("data-palette", next);
  localStorage.setItem(STORAGE_KEYS.palette, next);
  document.querySelectorAll("[data-palette-opt]").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.paletteOpt === next);
  });
}

function applyFontSize(scale) {
  const valid = ["standard", "comfort", "large"];
  const next = valid.includes(scale) ? scale : "comfort";
  document.documentElement.setAttribute("data-fontsize", next);
  localStorage.setItem(STORAGE_KEYS.fontsize, next);
  document.querySelectorAll("[data-font-opt]").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.fontOpt === next);
  });
}

function toggleAppearanceMenu(forceOpen) {
  const pop = el("appearancePopover");
  const btn = el("appearanceBtn");
  if (!pop || !btn) return;
  const shouldOpen = typeof forceOpen === "boolean" ? forceOpen : pop.classList.contains("hidden");
  pop.classList.toggle("hidden", !shouldOpen);
  btn.setAttribute("aria-expanded", shouldOpen ? "true" : "false");
}

function setLeftCollapsed(collapsed) {
  const shell = el("appShell");
  if (!shell) return;
  shell.classList.toggle("left-collapsed", Boolean(collapsed));
  localStorage.setItem(STORAGE_KEYS.leftExpanded, collapsed ? "0" : "1");
}

function setRightCollapsed(collapsed) {
  const shell = el("appShell");
  const btn = el("toggleRightBtn");
  if (!shell) return;
  shell.classList.toggle("right-collapsed", Boolean(collapsed));
  localStorage.setItem(STORAGE_KEYS.rightHidden, collapsed ? "1" : "0");
  if (btn) {
    btn.classList.toggle("active-pane", !collapsed);
  }
}

function switchWorkbenchTab(tabName) {
  const next = tabName === "terminal" ? "terminal" : "whiteboard";
  state.activeTab = next;
  const tabsWrap = el("workbenchTabs");
  if (tabsWrap) {
    tabsWrap.setAttribute("data-active-tab", next);
  }
  document.querySelectorAll(".wb-tab[data-tab]").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.tab === next);
  });
  el("pane-whiteboard")?.classList.toggle("active", next === "whiteboard");
  el("pane-terminal")?.classList.toggle("active", next === "terminal");

  const toggleBtnSpan = el("toggleRightBtn")?.querySelector("span");
  if (toggleBtnSpan) {
    toggleBtnSpan.textContent = next === "terminal" ? "执行终端" : "会议白板";
  }
  if (next === "terminal") {
    el("execDot")?.classList.add("hidden");
  }
}

/* ==================== 讨论策略、自动执行预演与场景预设同步 ==================== */

function syncCollabModeUI(modeKey, autoExec = state.autoPreviewExec) {
  const normalized = normalizeCollabModeAndAutoExec(modeKey, autoExec);
  state.collabMode = normalized.mode;
  state.autoPreviewExec = normalized.autoPreviewExec;

  const spec = COLLAB_MODES[state.collabMode] || COLLAB_MODES.deep_deliberation;
  const sel = el("collabModeSelect");
  if (sel && sel.value !== state.collabMode) {
    sel.value = state.collabMode;
  }
  const hint = el("collabModeHint");
  if (hint) hint.textContent = spec.hint;
  const compDesc = el("composerModeDesc");
  if (compDesc) compDesc.textContent = spec.hint;

  document.querySelectorAll("[data-collab-opt]").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.collabOpt === state.collabMode);
  });

  syncAutoPreviewUI(state.autoPreviewExec);
  syncScenarioPresetHighlight();
}

function syncAutoPreviewUI(on) {
  state.autoPreviewExec = Boolean(on);
  ["emptyAutoPreviewBtn", "composerAutoPreviewBtn"].forEach((id) => {
    const btn = el(id);
    if (btn) {
      btn.classList.toggle("active", state.autoPreviewExec);
      btn.setAttribute("aria-pressed", state.autoPreviewExec ? "true" : "false");
    }
  });
}

function detectActiveScenarioKey() {
  if (state.enabledAgents.length === 1) {
    const only = state.enabledAgents[0];
    if (state.collabMode === "rapid_consensus" && state.seatPersonas[only] === "fullstack_solo") {
      return "solo_focus";
    }
    return "";
  }
  if (state.enabledAgents.length === 3) {
    for (const [key, sp] of Object.entries(SCENARIO_PRESETS)) {
      if (sp.solo) continue;
      if (sp.collab_mode !== state.collabMode) continue;
      const matchPersonas = AGENT_ORDER.every((aid) => state.seatPersonas[aid] === sp.seat_personas[aid]);
      if (matchPersonas) return key;
    }
  }
  return "";
}

function escapeRegExp(str) {
  return String(str || "").replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function computeAvatarShortChar(nameStr, fallbackAid = "carbon") {
  const clean = String(nameStr || "").trim();
  if (!clean) return fallbackAid[0].toUpperCase();
  const ch = Array.from(clean)[0];
  return /[a-z]/i.test(ch) ? ch.toUpperCase() : ch;
}

function syncDynamicRosterNames() {
  const sysAgents = state.system?.agents || {};
  if (state.system?.roster_preset) {
    state.rosterPreset = state.system.roster_preset;
  }
  if (typeof state.system?.single_cli_concurrency === "number") {
    state.singleCliConcurrency = state.system.single_cli_concurrency;
  }
  const serverRosterPresets = state.system?.roster_presets;
  const presetObj =
    serverRosterPresets?.[state.rosterPreset] ||
    ROSTER_NAME_PRESETS[state.rosterPreset] ||
    ROSTER_NAME_PRESETS.role_experts;

  for (const aid of AGENT_ORDER) {
    const stName = state.seatStates?.[aid]?.name;
    const sysName = sysAgents?.[aid]?.name;
    const resolved = String(sysName || stName || presetObj.names?.[aid] || AGENT_NAMES[aid] || aid).trim();
    AGENT_NAMES[aid] = resolved;
    AUTHOR_BADGE_META[aid].name = resolved;
    AUTHOR_BADGE_META[aid].short = computeAvatarShortChar(resolved, aid);

    const seatCard = el(`seat-${aid}`);
    if (seatCard) {
      const nameSpan = seatCard.querySelector(".seat-name");
      if (nameSpan) nameSpan.textContent = resolved;
      const av = seatCard.querySelector(".seat-avatar");
      if (av) av.textContent = AUTHOR_BADGE_META[aid].short;
      seatCard.title = `点击胶囊点名 @${resolved}；点击职责标签配置角色、名称与推理档位`;
      const roleBtn = el(`seat-role-${aid}`);
      if (roleBtn) roleBtn.title = `配置 ${resolved} 角色职责、显示名称、推理档位与参会状态`;
    }

    const execSegBtn = document.querySelector(`#executorSegmented [data-exec-agent="${aid}"]`);
    if (execSegBtn) {
      execSegBtn.textContent = resolved;
      execSegBtn.title = `由 ${resolved} 承接执行交付`;
    }

    document.querySelectorAll(`.msg-card.speaker-${aid} [data-msg-act="mention"]`).forEach((btn) => {
      btn.textContent = `@${resolved}`;
    });
  }

  const slotLabels = { carbon: "席位一", grok: "席位二", astra: "席位三" };
  for (const [aid, cap] of [
    ["carbon", "Carbon"],
    ["grok", "Grok"],
    ["astra", "Astra"],
  ]) {
    const h4 = el(`cfgHead${cap}`);
    if (h4) h4.textContent = `${AGENT_NAMES[aid]}（${slotLabels[aid]}）`;
  }

  // 动态刷新开局引导舱与侧栏的 5 大场景预设描述文案
  const cN = AGENT_NAMES.carbon;
  const gN = AGENT_NAMES.grok;
  const aN = AGENT_NAMES.astra;
  const scenarioDescMap = {
    arch_review: `${cN} 架构规划 · ${gN} 风险审计 · ${aN} 工程实现`,
    proposal_debate: `${aN} 立论 · ${gN} 压力审计 · ${cN} 架构裁定`,
    product_design: `${cN} 产品交互 · ${gN} 风险审计 · ${aN} 全栈架构`,
    code_diagnosis: `${cN} 性能与稳定性 · ${gN} 测试与验证 · ${aN} 工程实现`,
    solo_focus: `启用单席「全栈架构」独立完成方案设计与自检交付`,
  };
  document.querySelectorAll("[data-scenario-preset]").forEach((node) => {
    const pk = node.dataset.scenarioPreset;
    if (!pk || !scenarioDescMap[pk]) return;
    const descDiv = node.querySelector(".scenario-desc");
    if (descDiv) descDiv.textContent = scenarioDescMap[pk];
    if (node.classList.contains("lineup-pill")) {
      node.title = scenarioDescMap[pk];
    }
  });
}

function syncScenarioPresetHighlight() {
  const activeKey = detectActiveScenarioKey();
  document.documentElement.setAttribute("data-active-scenario", activeKey || "custom");
  document.querySelectorAll("[data-scenario-preset]").forEach((btn) => {
    btn.classList.toggle("active", Boolean(activeKey) && btn.dataset.scenarioPreset === activeKey);
  });
}

async function persistSessionSeatsPatch(patch) {
  if (!state.currentSessionId) return null;
  const res = await apiFetch(`/api/sessions/${state.currentSessionId}/seats`, {
    method: "POST",
    body: JSON.stringify(patch),
  });
  if (Array.isArray(res.enabled_agents)) state.enabledAgents = res.enabled_agents;
  if (res.seat_personas) state.seatPersonas = { ...state.seatPersonas, ...res.seat_personas };
  if (res.seat_efforts) state.seatEfforts = { ...res.seatEfforts };
  if (res.executor_agent) state.executorAgent = res.executor_agent;
  if (res.collab_mode) {
    syncCollabModeUI(res.collab_mode, res.auto_preview_exec);
  } else if (typeof res.auto_preview_exec === "boolean") {
    syncAutoPreviewUI(res.auto_preview_exec);
  }
  if (res.seat_states) {
    state.seatStates = res.seat_states;
  }
  renderAllSeats();
  renderQuickCueButtons();
  renderExecutorControls();
  syncScenarioPresetHighlight();
  return res;
}

async function applyScenarioPreset(presetKey) {
  const spec = SCENARIO_PRESETS[presetKey];
  if (!spec) return;

  let nextEnabled = [];
  let nextPersonas = { ...state.seatPersonas };
  let nextExec = state.executorAgent;

  if (spec.solo) {
    const soloAid = pickPreferredSoloSeat();
    nextEnabled = [soloAid];
    nextPersonas[soloAid] = "fullstack_solo";
    nextExec = soloAid;
  } else {
    nextEnabled = [...spec.enabled_agents];
    nextPersonas = { ...spec.seat_personas };
    nextExec = spec.executor_agent || "astra";
  }

  syncCollabModeUI(spec.collab_mode, state.autoPreviewExec);
  state.enabledAgents = nextEnabled;
  state.seatPersonas = nextPersonas;
  state.executorAgent = nextExec;
  renderAllSeats();
  renderQuickCueButtons();
  renderExecutorControls();
  syncScenarioPresetHighlight();

  if (state.currentSessionId) {
    try {
      await persistSessionSeatsPatch({
        collab_mode: spec.collab_mode,
        enabled_agents: nextEnabled,
        seat_personas: nextPersonas,
        executor_agent: nextExec,
      });
      showToast(`已切换场景预设：${spec.label}（${COLLAB_MODES[spec.collab_mode].label}）`, "ok", 2200);
    } catch (err) {
      showToast(err.message || "更新场景预设失败", "err");
    }
  }
}

/* ==================== 模型推理档位能力与全局时限策略 ==================== */

function getEffortSpecForModel(driverKey, modelName, seatId = "") {
  const effDrv =
    driverKey === "auto"
      ? state.system?.agents?.[seatId]?.effective_driver || "agy"
      : driverKey || "agy";
  const rawCatalog = state.system?.model_effort_catalog;
  const drvMap =
    rawCatalog?.drivers?.[effDrv]?.models ||
    rawCatalog?.[effDrv] ||
    FALLBACK_MODEL_EFFORT_CATALOG[effDrv] ||
    FALLBACK_MODEL_EFFORT_CATALOG.agy;
  const cleanModel =
    String(modelName || "").trim().toLowerCase() || (DRIVER_DEFAULTS[effDrv]?.model || "").toLowerCase();

  if (cleanModel && drvMap[cleanModel]) {
    return drvMap[cleanModel];
  }
  if (cleanModel.includes("orchestrator")) {
    return { allowed: [], default: "", supports_effort: false };
  }
  for (const [pattern, spec] of Object.entries(drvMap)) {
    if (pattern.endsWith("*") && pattern !== "*") {
      const prefix = pattern.slice(0, -1).toLowerCase();
      if (cleanModel.startsWith(prefix)) return spec;
    }
  }
  return drvMap["*"] || { allowed: ["low", "medium", "high"], default: "high", supports_effort: true };
}

function populateEffortSelectElement(selectEl, allowedList, preferredVal, supportsEffort = true) {
  if (!selectEl) return;
  selectEl.innerHTML = "";
  if (!supportsEffort || !allowedList || allowedList.length === 0) {
    const opt = document.createElement("option");
    opt.value = "";
    opt.textContent = "自动省略";
    selectEl.appendChild(opt);
    selectEl.disabled = true;
    return;
  }
  selectEl.disabled = false;
  let chosen = allowedList.includes(preferredVal)
    ? preferredVal
    : allowedList[allowedList.length - 1];
  for (const lv of allowedList) {
    const opt = document.createElement("option");
    opt.value = lv;
    opt.textContent = lv;
    if (lv === chosen) opt.selected = true;
    selectEl.appendChild(opt);
  }
}

function refreshSeatEffortSelectInModal(seatCap, autoResetModelOnDriverChange = false) {
  const aid = seatCap.toLowerCase();
  const drvSel = el(`cfg${seatCap}Driver`);
  const modelInp = el(`cfg${seatCap}Model`);
  const discSel = el(`cfg${seatCap}Effort`);
  const execSel = el(`cfg${seatCap}ExecEffort`);
  const hintEl = el(`cfg${seatCap}EffortHint`);
  if (!drvSel || !modelInp || !discSel || !execSel) return;

  const drv = drvSel.value || "auto";
  const dSpec = DRIVER_DEFAULTS[drv] || DRIVER_DEFAULTS.auto;
  if (dSpec.listId) {
    modelInp.setAttribute("list", dSpec.listId);
  } else {
    modelInp.removeAttribute("list");
  }

  if (autoResetModelOnDriverChange && dSpec.model) {
    const curM = modelInp.value.trim().toLowerCase();
    const exclusiveMismatch =
      (drv === "agy" && (curM.startsWith("grok") || curM.startsWith("gpt-"))) ||
      (drv === "grok" && (curM.startsWith("gemini") || curM.startsWith("gpt-") || curM.includes("orchestrator"))) ||
      (drv === "codex" && (curM.startsWith("gemini") || curM.startsWith("grok") || curM.includes("orchestrator")));
    if (!curM || exclusiveMismatch) {
      modelInp.value = dSpec.model;
    }
  }

  const spec = getEffortSpecForModel(drv, modelInp.value, aid);
  const prevDisc = discSel.value || spec.default || dSpec.discussEffort;
  const prevExec = execSel.value || spec.default || dSpec.execEffort;

  populateEffortSelectElement(discSel, spec.allowed, prevDisc, spec.supports_effort);
  const execAllowed = (spec.allowed || []).filter((x) => x !== "low");
  populateEffortSelectElement(
    execSel,
    execAllowed.length ? execAllowed : spec.allowed,
    prevExec,
    spec.supports_effort
  );

  if (hintEl) {
    hintEl.textContent = spec.supports_effort
      ? `(最高 ${spec.allowed[spec.allowed.length - 1]})`
      : "(无需档位)";
  }
}

function syncPacingControlsInModal(mode, idleSec, turnSec, refChars) {
  const nextMode = ["unrestricted", "standard", "custom"].includes(mode) ? mode : "unrestricted";
  state.pacingMode = nextMode;

  document.querySelectorAll("#cfgPacingGroup [data-pacing-mode]").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.pacingMode === nextMode);
  });

  const customBox = el("cfgCustomPacingBox");
  if (customBox) {
    customBox.classList.toggle("hidden", nextMode !== "custom");
  }

  const preset = PACING_PRESETS[nextMode];
  const effIdle = preset ? preset.idle_timeout_sec : Number(idleSec ?? state.idleTimeoutSec ?? 900);
  const effTurn = preset ? preset.turn_timeout_sec : Number(turnSec ?? state.turnTimeoutSec ?? 0);
  const effRef = preset ? preset.max_ref_chars : Number(refChars ?? state.maxRefChars ?? 120000);

  if (el("cfgIdleTimeout")) el("cfgIdleTimeout").value = String(effIdle);
  if (el("cfgTurnTimeout")) el("cfgTurnTimeout").value = String(effTurn);
  if (el("cfgMaxRefChars")) el("cfgMaxRefChars").value = String(effRef);

  const descEl = el("cfgPacingDesc");
  if (descEl) {
    if (preset) {
      descEl.textContent = preset.desc;
    } else {
      const idleLabel = effIdle <= 0 ? "子进程存活不限空闲" : `空闲等待 ${effIdle}s`;
      const turnLabel = effTurn <= 0 ? "单轮不限总时长" : `单轮上限 ${effTurn}s`;
      descEl.textContent = `${idleLabel} · ${turnLabel} · 源码预算 ${effRef.toLocaleString()} 字符`;
    }
  }
}

/* ==================== 轻量安全 Markdown 与 Diff 渲染器 ==================== */

function stripInternalStatusLines(rawText) {
  if (!rawText) return "";
  return String(rawText)
    .replace(/\[(?:状态|徽章|白板|白板要点)[:：][^\]]*\]/g, "")
    .trim();
}

function formatInlineMarkdown(escapedLine) {
  let s = escapedLine;
  s = s.replace(/`([^`]+)`/g, "<code>$1</code>");
  s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  s = s.replace(/\*([^*\n]+)\*/g, "<em>$1</em>");
  const mentionNames = Array.from(
    new Set(["Carbon", "Grok", "Astra", "主持人", AGENT_NAMES.carbon, AGENT_NAMES.grok, AGENT_NAMES.astra].filter(Boolean))
  ).map(escapeRegExp);
  if (mentionNames.length) {
    const mRe = new RegExp(`@(${mentionNames.join("|")})(?![A-Za-z0-9_])`, "gi");
    s = s.replace(mRe, '<span class="mention-tag">@$1</span>');
  }
  s = s.replace(
    /@([A-Za-z0-9_\u4e00-\u9fa5./-]+\.[A-Za-z0-9]{1,10}(?::[Ll]?\d+(?:-[Ll]?\d+)?)?)/g,
    '<span class="file-mention-tag">@$1</span>'
  );
  return s;
}

function renderMarkdown(raw) {
  const cleaned = stripInternalStatusLines(raw);
  if (!cleaned) return "";

  const codeBlocks = [];
  const withPlaceholders = cleaned.replace(/```([a-zA-Z0-9_+-]*)\n?([\s\S]*?)```/g, (_, lang, code) => {
    const idx = codeBlocks.length;
    const safeLang = escapeHtml((lang || "code").trim());
    const safeCode = escapeHtml(code.replace(/\n$/, ""));
    codeBlocks.push(
      `<div class="md-code-block">` +
        `<div class="md-code-head"><span>${safeLang}</span>` +
        `<button type="button" class="md-copy-code" data-copy-code="${idx}">复制代码</button></div>` +
        `<pre><code>${safeCode}</code></pre>` +
      `</div>`
    );
    return `\n@@CODEBLOCK_${idx}@@\n`;
  });

  const lines = withPlaceholders.split("\n");
  const out = [];
  let inUl = false;
  let inOl = false;
  let tableBuf = [];

  const flushList = () => {
    if (inUl) {
      out.push("</ul>");
      inUl = false;
    }
    if (inOl) {
      out.push("</ol>");
      inOl = false;
    }
  };

  const flushTable = () => {
    if (!tableBuf.length) return;
    if (tableBuf.length >= 2 && /^\|?[\s:-]+\|/.test(tableBuf[1])) {
      const parseRow = (r) =>
        r
          .trim()
          .replace(/^\||\|$/g, "")
          .split("|")
          .map((c) => formatInlineMarkdown(escapeHtml(c.trim())));
      const headers = parseRow(tableBuf[0]);
      const bodyRows = tableBuf.slice(2).map(parseRow);
      let html = '<div class="md-table-wrap"><table class="md-table"><thead><tr>';
      headers.forEach((h) => {
        html += `<th>${h}</th>`;
      });
      html += "</tr></thead><tbody>";
      bodyRows.forEach((row) => {
        html += "<tr>" + row.map((c) => `<td>${c}</td>`).join("") + "</tr>";
      });
      html += "</tbody></table></div>";
      out.push(html);
    } else {
      tableBuf.forEach((r) => out.push(`<p>${formatInlineMarkdown(escapeHtml(r))}</p>`));
    }
    tableBuf = [];
  };

  for (const rawLn of lines) {
    const trimLn = rawLn.trim();
    const codeMatch = trimLn.match(/^@@CODEBLOCK_(\d+)@@$/);
    if (codeMatch) {
      flushList();
      flushTable();
      out.push(codeBlocks[Number(codeMatch[1])] || "");
      continue;
    }

    if (trimLn.startsWith("|") && trimLn.endsWith("|") && trimLn.length > 2) {
      flushList();
      tableBuf.push(trimLn);
      continue;
    } else if (tableBuf.length) {
      flushTable();
    }

    if (!trimLn) {
      flushList();
      continue;
    }

    if (/^---+$/.test(trimLn)) {
      flushList();
      out.push('<hr class="md-hr" />');
      continue;
    }

    const hMatch = trimLn.match(/^(#{1,4})\s+(.+)$/);
    if (hMatch) {
      flushList();
      const level = hMatch[1].length <= 2 ? "h3" : "h4";
      out.push(`<${level}>${formatInlineMarkdown(escapeHtml(hMatch[2]))}</${level}>`);
      continue;
    }

    const bqMatch = trimLn.match(/^>\s?(.*)$/);
    if (bqMatch) {
      flushList();
      out.push(`<blockquote>${formatInlineMarkdown(escapeHtml(bqMatch[1]))}</blockquote>`);
      continue;
    }

    const ulMatch = trimLn.match(/^[-*•]\s+(.+)$/);
    if (ulMatch) {
      if (inOl) {
        out.push("</ol>");
        inOl = false;
      }
      if (!inUl) {
        out.push("<ul>");
        inUl = true;
      }
      out.push(`<li>${formatInlineMarkdown(escapeHtml(ulMatch[1]))}</li>`);
      continue;
    }

    const olMatch = trimLn.match(/^\d+[.)、]\s+(.+)$/);
    if (olMatch) {
      if (inUl) {
        out.push("</ul>");
        inUl = false;
      }
      if (!inOl) {
        out.push("<ol>");
        inOl = true;
      }
      out.push(`<li>${formatInlineMarkdown(escapeHtml(olMatch[1]))}</li>`);
      continue;
    }

    flushList();
    out.push(`<p>${formatInlineMarkdown(escapeHtml(trimLn))}</p>`);
  }

  flushList();
  flushTable();
  return out.join("");
}

function renderDiffHtml(diffText) {
  const raw = String(diffText || "").trim();
  if (!raw) {
    if (el("diffStatBadge")) el("diffStatBadge").textContent = "";
    return "暂无变更输出";
  }
  let addCount = 0;
  let delCount = 0;
  const htmlLines = raw.split("\n").map((ln) => {
    const safe = escapeHtml(ln);
    if (ln.startsWith("+++") || ln.startsWith("---")) {
      return `<span class="diff-hunk">${safe}</span>`;
    }
    if (ln.startsWith("+")) {
      addCount += 1;
      return `<span class="diff-add">${safe}</span>`;
    }
    if (ln.startsWith("-")) {
      delCount += 1;
      return `<span class="diff-del">${safe}</span>`;
    }
    if (ln.startsWith("@@") || ln.startsWith("diff --git")) {
      return `<span class="diff-hunk">${safe}</span>`;
    }
    return safe;
  });
  if (el("diffStatBadge")) {
    el("diffStatBadge").textContent = addCount || delCount ? `+${addCount} / -${delCount}` : "";
  }
  return htmlLines.join("\n");
}

/* ==================== 发言卡片、实时思考条、15s 跳过与三级恢复 ==================== */

function getMessageContainer() {
  return el("chatStreamInner") || el("chatStream");
}

function clearChatMessages() {
  const container = getMessageContainer();
  if (container) {
    container.querySelectorAll(".msg-card").forEach((node) => node.remove());
  }
  state.messages.clear();
}

function updateEmptyGuideVisibility() {
  const guide = el("emptyGuide");
  if (!guide) return;
  const hasMsgs = state.messages.size > 0 || state.isBusy;
  guide.classList.toggle("hidden", hasMsgs);
}

function resolveSemanticBadgeClass(msg) {
  const phase = String(msg.phase_label || "");
  const badge = String(msg.badge || "");
  if (msg.skipped || badge.includes("跳过") || badge.includes("停止") || badge.includes("中断")) {
    return "sem-badge-muted";
  }
  if (msg.error || badge.includes("异常") || badge.includes("失败") || badge.includes("超时") || badge.includes("风险") || phase.includes("反向审计")) {
    return "sem-badge-audit";
  }
  if (
    phase.includes("决议") ||
    phase.includes("执行交付") ||
    badge.includes("交付完成") ||
    badge.includes("已写入") ||
    badge.includes("达成共识") ||
    badge.includes("已形成决议")
  ) {
    return "sem-badge-done";
  }
  if (phase.includes("答辩") || phase.includes("裁定") || phase.includes("收敛") || phase.includes("修正") || phase.includes("方案")) {
    return "sem-badge-rebuttal";
  }
  if (phase.includes("质询") || phase.includes("辩证") || phase.includes("核验") || phase.includes("评估")) {
    return "sem-badge-debate";
  }
  return "";
}

function formatThinkingModelTag(msg) {
  const seatInfo = state.seatStates[msg.speaker] || {};
  const model = msg.model || seatInfo.effective_model || msg.driver || seatInfo.effective_driver || "";
  const effort = msg.effort || state.seatEfforts[msg.speaker] || seatInfo.effective_effort || "";
  if (model && effort) return `${model} · ${effort}`;
  if (model) return model;
  return AGENT_NAMES[msg.speaker] || "CLI";
}

function buildThinkingPlaceholderHtml(msg) {
  const startTs = Number(msg.started_ts || Date.now());
  const elapsedSec = Math.max(0, Math.floor((Date.now() - startTs) / 1000));
  const modelTag = escapeHtml(formatThinkingModelTag(msg));
  const activity = escapeHtml(msg.activity || "正在深度推演…");
  const canSkip = AGENT_ORDER.includes(msg.speaker);
  const skipVisible = elapsedSec >= 15 ? " is-visible" : "";
  return (
    `<div class="thinking-placeholder" data-thinking-for="${escapeHtml(msg.id)}">` +
      `<span class="thinking-spinner" aria-hidden="true"></span>` +
      `<span class="thinking-status-wrap">` +
        `<span class="thinking-model-tag">${modelTag}</span>` +
        `<span class="thinking-sep">·</span>` +
        `<span class="thinking-activity-text">${activity}</span>` +
        `<span class="thinking-sep">·</span>` +
        `<span class="thinking-timer">${elapsedSec}s</span>` +
      `</span>` +
      (canSkip
        ? `<button type="button" class="skip-turn-btn${skipVisible}" data-msg-act="skip-turn" title="仅跳过本席当前回合，不中断其余席位">跳过本轮</button>`
        : "") +
    `</div>`
  );
}

function extractBestPointForWhiteboard(msg) {
  const cleaned = stripInternalStatusLines(msg.content || "");
  if (!cleaned) return "";
  const lines = cleaned
    .split("\n")
    .map((l) => l.replace(/^(?:[#>*•\-]+|\d+[.)、])\s*/, "").trim())
    .filter((l) => l.length >= 6 && !l.startsWith("```") && !l.startsWith("|"));
  const chosen = lines[0] || cleaned.slice(0, 140);
  return chosen.length > 165 ? chosen.slice(0, 164) + "…" : chosen;
}

function createOrUpdateMessageCard(msgInput, options = {}) {
  const { skipEnterAnim = false } = options;
  const container = getMessageContainer();
  if (!container || !msgInput || !msgInput.id) return;

  const prev = state.messages.get(msgInput.id) || {};
  const msg = {
    ...prev,
    ...msgInput,
    started_ts: msgInput.started_ts || prev.started_ts || Date.now(),
  };
  state.messages.set(msg.id, msg);
  updateEmptyGuideVisibility();

  let card = document.getElementById(`msg-${msg.id}`);
  const isNewCard = !card;
  if (isNewCard) {
    card = document.createElement("article");
    card.id = `msg-${msg.id}`;
    if (!skipEnterAnim) {
      card.classList.add("msg-enter");
      card.addEventListener(
        "animationend",
        () => {
          card.classList.remove("msg-enter");
        },
        { once: true }
      );
    }
    container.appendChild(card);
  }

  const staleBadges = ["思考中", "发言中", "调用中", "重试中", "排队等待发言…", "汇总决议中", "正在深度推演…"];
  const rawBadgeStr = String(msg.badge || "").trim();
  if (!msg.streaming && (staleBadges.includes(rawBadgeStr) || rawBadgeStr.startsWith("正在"))) {
    msg.badge = "已中断";
  }

  const speakerKey = msg.speaker || "system";
  const isResolution = msg.phase_label === "最终决议";
  const isSkipped = Boolean(msg.skipped) || msg.badge === "已跳过本轮" || (!msg.streaming && msg.badge === "已中断" && !(msg.content || "").trim());
  const isError = Boolean(msg.error) && !isSkipped;
  const wasCollapsed = card.classList.contains("is-collapsed");

  card.className = [
    "msg-card",
    `speaker-${speakerKey}`,
    isResolution ? "msg-resolution-card" : "",
    isSkipped ? "msg-skipped" : "",
    isError ? "msg-error" : "",
    wasCollapsed ? "is-collapsed" : "",
    card.classList.contains("msg-enter") ? "msg-enter" : "",
    card.classList.contains("msg-spotlight") ? "msg-spotlight" : "",
  ]
    .filter(Boolean)
    .join(" ");

  const avatarChar =
    speakerKey === "chair"
      ? "主"
      : speakerKey === "system"
      ? "系"
      : computeAvatarShortChar(msg.speaker_name || AGENT_NAMES[speakerKey] || speakerKey, speakerKey);

  const targetHtml = msg.target
    ? `<span class="msg-target-chip">→ @${escapeHtml(AGENT_NAMES[msg.target] || msg.target)}</span>`
    : "";

  const badgeSemCls = resolveSemanticBadgeClass(msg);
  const badgeHtml = msg.badge
    ? `<span class="msg-badge-chip ${badgeSemCls}">${escapeHtml(msg.badge)}</span>`
    : "";

  const timingStr =
    !msg.streaming && msg.elapsed_ms > 0
      ? `<span class="msg-timing">${(msg.elapsed_ms / 1000).toFixed(1)}s</span>`
      : "";

  const isAgentMsg = AGENT_ORDER.includes(speakerKey);
  const canIngestWb = !msg.streaming && !isError && !isSkipped && (isAgentMsg || isResolution) && (msg.content || "").trim();

  const hoverBtns = [];
  if (isResolution && !msg.streaming && (msg.content || "").trim()) {
    hoverBtns.push(
      `<button type="button" class="msg-sync-wb-btn" data-msg-act="sync-resolution" title="提取最终决议中的共识、风险与任务项同步至右侧会议白板">同步决议至白板</button>`
    );
  }
  if (canIngestWb && !isResolution) {
    hoverBtns.push(`<button type="button" class="msg-act-btn" data-msg-act="add-wb">收入白板</button>`);
  }
  if (isAgentMsg && !msg.streaming) {
    hoverBtns.push(
      `<button type="button" class="msg-act-btn" data-msg-act="mention">@${escapeHtml(AGENT_NAMES[speakerKey])}</button>`
    );
  }
  if (!msg.streaming && (msg.content || "").trim()) {
    hoverBtns.push(`<button type="button" class="msg-act-btn" data-msg-act="copy">复制</button>`);
    if ((msg.content || "").length > 360) {
      hoverBtns.push(
        `<button type="button" class="msg-act-btn msg-fold-toggle" data-msg-act="toggle-fold">${wasCollapsed ? "展开" : "收起"}</button>`
      );
    }
  }

  const hasContent = Boolean((msg.content || "").trim());
  const isThinkingOnly = Boolean(msg.streaming) && !hasContent;

  let bodyInnerHtml = "";
  if (isThinkingOnly) {
    bodyInnerHtml = buildThinkingPlaceholderHtml(msg);
  } else if (!hasContent && !isError) {
    bodyInnerHtml = renderMarkdown("*(该轮发言未生成内容或已中断)*");
  } else {
    bodyInnerHtml = renderMarkdown(msg.content || "");
  }

  let errorPanelHtml = "";
  if (isError && isAgentMsg) {
    const rawDiag = msg.error_detail
      ? `<details class="msg-error-details"><summary>查看底层 CLI 诊断输出</summary><div class="msg-error-raw">${escapeHtml(
          msg.error_detail
        )}</div></details>`
      : "";
    errorPanelHtml =
      `<div class="msg-error-panel">` +
        `<div class="msg-error-actions">` +
          `<button type="button" class="msg-retry-unlimited-btn" data-msg-act="retry-mode" data-retry-mode="unlimited">原配置重试（不限时）</button>` +
          `<button type="button" class="msg-downgrade-retry-btn" data-msg-act="retry-mode" data-retry-mode="downgrade">降级档位重试</button>` +
          `<button type="button" class="msg-borrow-retry-btn" data-msg-act="retry-mode" data-retry-mode="borrow">切换备用引擎代答</button>` +
          `<button type="button" class="msg-open-cfg-btn" data-msg-act="open-settings">修改配置</button>` +
        `</div>` +
        rawDiag +
      `</div>`;
  }

  card.innerHTML =
    (isResolution ? `<div class="msg-resolution-crown" aria-hidden="true"></div>` : "") +
    `<div class="msg-header">` +
      `<div class="msg-author-group">` +
        `<span class="msg-avatar-mini">${escapeHtml(avatarChar)}</span>` +
        `<span class="msg-speaker">${escapeHtml(msg.speaker_name || AGENT_NAMES[speakerKey] || "成员")}</span>` +
        (msg.role_title ? `<span class="msg-role">${escapeHtml(msg.role_title)}</span>` : "") +
        (isResolution
          ? `<span class="resolution-crown-badge">会议最终决议</span>`
          : msg.phase_label
          ? `<span class="msg-phase">${escapeHtml(msg.phase_label)}</span>`
          : "") +
        targetHtml +
      `</div>` +
      `<div class="msg-meta-right">` +
        (isResolution && !msg.streaming && hasContent
          ? hoverBtns.shift() || ""
          : "") +
        `<div class="msg-hover-actions">${hoverBtns.join("")}</div>` +
        badgeHtml +
        timingStr +
        (msg.timestamp ? `<span>${escapeHtml(msg.timestamp)}</span>` : "") +
      `</div>` +
    `</div>` +
    `<div class="msg-body${msg.streaming && hasContent ? " streaming" : ""}${isThinkingOnly ? " thinking-only" : ""}">` +
      bodyInnerHtml +
    `</div>` +
    errorPanelHtml;

  bindCardInteractiveEvents(card, msg);
  if (!state.userScrolledUp && !skipEnterAnim) {
    scrollToBottom(false);
  }
}

function appendMessageDelta(msgId, deltaText) {
  const msg = state.messages.get(msgId);
  if (!msg) return;
  msg.content = (msg.content || "") + (deltaText || "");
  msg.activity = "";
  const card = document.getElementById(`msg-${msgId}`);
  const bodyEl = card?.querySelector(".msg-body");
  if (!bodyEl) {
    createOrUpdateMessageCard(msg, { skipEnterAnim: true });
    return;
  }
  bodyEl.classList.remove("thinking-only");
  bodyEl.classList.add("streaming");
  bodyEl.innerHTML = renderMarkdown(msg.content);
  bindCodeCopyButtons(bodyEl, msg.content);
  if (!state.userScrolledUp) {
    scrollToBottom(false);
  }
}

function updateMessageStreamingStatus(pkt) {
  if (!pkt || !pkt.id) return;
  const msg = state.messages.get(pkt.id);
  if (!msg || !msg.streaming) return;
  if (pkt.driver) msg.driver = pkt.driver;
  if (pkt.model) msg.model = pkt.model;
  if (pkt.effort) msg.effort = pkt.effort;
  if (pkt.detail || pkt.activity) {
    msg.activity = pkt.detail || pkt.activity;
  }
  const card = document.getElementById(`msg-${pkt.id}`);
  const ph = card?.querySelector(".thinking-placeholder");
  if (!ph) return;
  const tagEl = ph.querySelector(".thinking-model-tag");
  const actEl = ph.querySelector(".thinking-activity-text");
  if (tagEl) tagEl.textContent = formatThinkingModelTag(msg);
  if (actEl && msg.activity) actEl.textContent = msg.activity;
}

function bindCodeCopyButtons(containerEl, rawMarkdown) {
  const codeBlocksRaw = [];
  String(rawMarkdown || "").replace(/```(?:[a-zA-Z0-9_+-]*)\n?([\s\S]*?)```/g, (_, code) => {
    codeBlocksRaw.push(code.replace(/\n$/, ""));
    return "";
  });
  containerEl.querySelectorAll("[data-copy-code]").forEach((btn) => {
    btn.onclick = async (e) => {
      e.stopPropagation();
      const idx = Number(btn.dataset.copyCode || "0");
      const text = codeBlocksRaw[idx] || btn.closest(".md-code-block")?.querySelector("code")?.textContent || "";
      await copyTextToClipboard(text, "代码片段已复制");
    };
  });
}

function bindCardInteractiveEvents(card, msg) {
  bindCodeCopyButtons(card, msg.content || "");

  card.querySelectorAll("[data-msg-act]").forEach((btn) => {
    btn.onclick = async (e) => {
      e.stopPropagation();
      const act = btn.dataset.msgAct;
      if (act === "skip-turn") {
        btn.disabled = true;
        btn.textContent = "跳过中…";
        await skipSeatTurn(msg.speaker);
      } else if (act === "retry-mode") {
        const mode = btn.dataset.retryMode || "unlimited";
        card.querySelectorAll("[data-msg-act='retry-mode']").forEach((b) => {
          b.disabled = true;
        });
        await retrySeatTurn(msg.speaker, msg.id, mode);
      } else if (act === "open-settings") {
        openSettingsModal();
      } else if (act === "sync-resolution") {
        btn.disabled = true;
        await syncResolutionToWhiteboard(msg.id);
        btn.disabled = false;
      } else if (act === "add-wb") {
        const point = extractBestPointForWhiteboard(msg);
        if (!point) return;
        const pSpec = getPersonaSpec(state.seatPersonas[msg.speaker], msg.speaker);
        await postWhiteboardMutation({
          op: "add",
          kind: pSpec.wb_kind || "decision",
          author: AGENT_ORDER.includes(msg.speaker) ? msg.speaker : "chair",
          source_msg_id: msg.id,
          text: point,
        });
        showToast("已收入会议白板", "ok", 1800);
      } else if (act === "mention") {
        insertMentionIntoComposer(`@${AGENT_NAMES[msg.speaker] || msg.speaker} `);
      } else if (act === "copy") {
        await copyTextToClipboard(stripInternalStatusLines(msg.content || ""), "发言内容已复制");
      } else if (act === "toggle-fold") {
        const nowCollapsed = card.classList.toggle("is-collapsed");
        btn.textContent = nowCollapsed ? "展开" : "收起";
      }
    };
  });
}

async function skipSeatTurn(agentId) {
  if (!state.currentSessionId || !agentId) return;
  try {
    await apiFetch(`/api/sessions/${state.currentSessionId}/skip`, {
      method: "POST",
      body: JSON.stringify({ agent_id: agentId }),
    });
    showToast(`已跳过 ${AGENT_NAMES[agentId] || agentId} 本轮发言，会议继续推进`, "info", 2200);
  } catch (err) {
    showToast(err.message || "跳过本轮失败", "err");
  }
}

async function retrySeatTurn(agentId, messageId, mode = "unlimited") {
  if (!state.currentSessionId || !agentId) return;
  try {
    const res = await apiFetch(`/api/sessions/${state.currentSessionId}/retry`, {
      method: "POST",
      body: JSON.stringify({
        agent_id: agentId,
        message_id: messageId,
        mode,
      }),
    });
    showToast(`已启动 ${AGENT_NAMES[agentId]}：${res.description || "恢复重试"}`, "ok", 2400);
  } catch (err) {
    showToast(err.message || "重试请求失败", "err", 3600);
    const existing = state.messages.get(messageId);
    if (existing) {
      createOrUpdateMessageCard(existing, { skipEnterAnim: true });
    }
  }
}

async function syncResolutionToWhiteboard(messageId) {
  const wb = await postWhiteboardMutation({
    op: "import_resolution",
    message_id: messageId || "",
  });
  if (wb) {
    switchWorkbenchTab("whiteboard");
    setRightCollapsed(false);
    showToast("已将最终决议同步至会议白板三区", "ok", 2400);
  }
}

function tickThinkingTimers() {
  const now = Date.now();
  for (const msg of state.messages.values()) {
    if (!msg.streaming) continue;
    const startTs = Number(msg.started_ts || now);
    const elapsedSec = Math.max(0, Math.floor((now - startTs) / 1000));
    const card = document.getElementById(`msg-${msg.id}`);
    if (card) {
      const ph = card.querySelector(".thinking-placeholder");
      if (ph) {
        const timerEl = ph.querySelector(".thinking-timer");
        if (timerEl) timerEl.textContent = `${elapsedSec}s`;
        const skipBtn = ph.querySelector(".skip-turn-btn");
        if (skipBtn && elapsedSec >= 15 && !skipBtn.classList.contains("is-visible")) {
          skipBtn.classList.add("is-visible");
        }
      }
    }
    if (AGENT_ORDER.includes(msg.speaker)) {
      const st = state.seatStates[msg.speaker];
      if (st && st.status === "thinking") {
        const badgeEl = el(`seat-badge-${msg.speaker}`);
        if (badgeEl) {
          const baseStatus = msg.activity ? msg.activity.slice(0, 10) : "思考中";
          badgeEl.textContent = `${baseStatus} ${elapsedSec}s`;
        }
      }
    }
  }

  const execTimer = el("execLiveTimer");
  if (execTimer) {
    if (state.stage === "executing" && state.execStartTs > 0) {
      const sec = Math.max(0, Math.floor((now - state.execStartTs) / 1000));
      execTimer.textContent = `${sec}s`;
      execTimer.classList.remove("hidden");
    } else {
      execTimer.classList.add("hidden");
    }
  }
}

function scrollToBottom(smooth = true) {
  const stream = el("chatStream");
  if (!stream) return;
  stream.scrollTo({
    top: stream.scrollHeight,
    behavior: smooth ? "smooth" : "auto",
  });
  state.userScrolledUp = false;
  el("scrollBottomBtn")?.classList.add("hidden");
}

function scrollToSourceMessage(sourceMsgId) {
  if (!sourceMsgId) {
    showToast("该白板条目由人工录入，无关联讨论卡片", "info", 1800);
    return;
  }
  const targetCard = document.getElementById(`msg-${sourceMsgId}`);
  if (!targetCard) {
    showToast("未在当前讨论流中找到对应发言卡片", "warn", 2000);
    return;
  }
  targetCard.classList.remove("is-collapsed");
  targetCard.scrollIntoView({ behavior: "smooth", block: "center" });
  targetCard.classList.remove("msg-spotlight");
  void targetCard.offsetWidth;
  targetCard.classList.add("msg-spotlight");
  setTimeout(() => {
    targetCard.classList.remove("msg-spotlight");
  }, 1450);
}

/* ==================== 模块四：三区结构化「会议白板」与乐观锁同步 ==================== */

function normalizeClientWhiteboard(rawWb) {
  const wb = rawWb && typeof rawWb === "object" ? { ...rawWb } : {};
  const rawItems = Array.isArray(wb.items) ? wb.items : null;
  let items = [];

  if (rawItems) {
    items = rawItems
      .filter((it) => it && typeof it === "object" && String(it.text || "").trim())
      .map((it, idx) => {
        const rawKind = String(it.kind || "").toLowerCase();
        const kind = ["decision", "risk", "action"].includes(rawKind)
          ? rawKind
          : it.adopted
          ? "decision"
          : it.bucket === "grok_risks"
          ? "risk"
          : it.bucket === "astra_actions"
          ? "action"
          : "decision";
        const rawAuthor = String(it.author || it.source_seat || "chair").toLowerCase();
        const author = AUTHOR_BADGE_META[rawAuthor] ? rawAuthor : "chair";
        return {
          id: String(it.id || `wb_cli_${idx}`),
          kind,
          text: String(it.text || "").trim(),
          author,
          source_msg_id: String(it.source_msg_id || ""),
          pinned: Boolean(it.pinned),
          checked: it.checked !== undefined ? Boolean(it.checked) : true,
          ver: Math.max(1, Number(it.ver || it.version || 1)),
        };
      });
  } else {
    const legacyBuckets = [
      ["chair_constraints", "decision", "chair", true],
      ["carbon_plan", "decision", "carbon", false],
      ["grok_risks", "risk", "grok", false],
      ["astra_actions", "action", "astra", false],
    ];
    let seq = 0;
    for (const [bKey, kind, author, pinned] of legacyBuckets) {
      const arr = Array.isArray(wb[bKey]) ? wb[bKey] : [];
      for (const txt of arr) {
        const clean = String(txt || "").trim();
        if (!clean) continue;
        seq += 1;
        items.push({
          id: `wb_legacy_${bKey}_${seq}`,
          kind,
          text: clean,
          author,
          source_msg_id: "",
          pinned,
          checked: true,
          ver: 1,
        });
      }
    }
  }

  wb.items = items;
  wb.exec_logs = Array.isArray(wb.exec_logs) ? wb.exec_logs : [];
  wb.exec_diff = String(wb.exec_diff || "");
  wb.can_rollback = Boolean(wb.can_rollback);
  return wb;
}

function pulseWbTabBadge() {
  const badge = el("wbCountBadge");
  if (!badge) return;
  badge.classList.remove("badge-pulse");
  void badge.offsetWidth;
  badge.classList.add("badge-pulse");
}

function showWbConflictBanner(message, draftText, retryForceFn) {
  const banner = el("wbConflictBanner");
  if (!banner) return;
  banner.innerHTML =
    `<div>${escapeHtml(message || "该白板条目刚被并发更新，请确认后再保存")}</div>` +
    `<div class="wb-conflict-actions">` +
      (draftText
        ? `<button type="button" class="wb-conflict-btn" data-wb-conflict="copy">复制草稿</button>`
        : "") +
      (retryForceFn
        ? `<button type="button" class="wb-conflict-btn primary" data-wb-conflict="force">覆盖保存</button>`
        : "") +
      `<button type="button" class="wb-conflict-btn" data-wb-conflict="dismiss">刷新最新</button>` +
    `</div>`;
  banner.classList.remove("hidden");

  banner.querySelector("[data-wb-conflict='copy']")?.addEventListener("click", () => {
    copyTextToClipboard(draftText, "冲突草稿已复制");
  });
  banner.querySelector("[data-wb-conflict='force']")?.addEventListener("click", async () => {
    banner.classList.add("hidden");
    await retryForceFn();
  });
  banner.querySelector("[data-wb-conflict='dismiss']")?.addEventListener("click", () => {
    banner.classList.add("hidden");
    if (state.whiteboard) {
      renderWhiteboard(state.whiteboard, true, false);
    }
  });
}

async function postWhiteboardMutation(payload, draftTextForConflict = "") {
  if (!state.currentSessionId) return null;
  try {
    const res = await apiFetch(`/api/sessions/${state.currentSessionId}/whiteboard`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    const wb = res.whiteboard;
    if (wb?.conflict) {
      showWbConflictBanner(wb.conflict_message, draftTextForConflict, async () => {
        const retryPayload = { ...payload };
        delete retryPayload.ver;
        delete retryPayload.expected_version;
        await postWhiteboardMutation(retryPayload);
      });
      state.whiteboard = normalizeClientWhiteboard(wb);
      return null;
    }
    el("wbConflictBanner")?.classList.add("hidden");
    if (wb) {
      renderWhiteboard(wb, true, false);
    }
    return wb;
  } catch (err) {
    showToast(err.message || "更新会议白板失败", "err");
    return null;
  }
}

async function discussRiskItem(item) {
  if (!item || !item.text || !state.currentSessionId) return;
  const prompt = `请围绕以下待决争议与风险项展开定向讨论，对比可行方案的工程代价并给出明确裁决结论：${item.text}`;
  try {
    if (!state.topic) {
      await startOrInterruptWithText(prompt);
    } else {
      await apiFetch(`/api/sessions/${state.currentSessionId}/followup`, {
        method: "POST",
        body: JSON.stringify({ message: prompt }),
      });
      showToast("已围绕该争议项发起圆桌定向讨论", "ok", 2200);
    }
  } catch (err) {
    showToast(err.message || "发起定向讨论失败", "err");
  }
}

function buildWbPoolItemElement(item, zoneKind, animateEnter) {
  const li = document.createElement("li");
  const isAction = zoneKind === "action";
  const isRisk = zoneKind === "risk";
  const isDecision = zoneKind === "decision";
  const isChecked = item.checked !== false;

  li.className = [
    "wb-pool-item",
    item.pinned ? "is-pinned" : "",
    isAction ? "has-checkbox" : "",
    isAction && !isChecked ? "is-unchecked" : "",
    animateEnter ? "wb-card-enter" : "",
  ]
    .filter(Boolean)
    .join(" ");
  li.dataset.itemId = item.id;

  const authorMeta = AUTHOR_BADGE_META[item.author] || AUTHOR_BADGE_META.chair;
  const srcTip = item.source_msg_id
    ? `来自 ${authorMeta.name} · 点击滚回左侧原发言并聚光高亮`
    : `来源：${authorMeta.name}`;

  let actionsHtml = "";
  if (isDecision) {
    actionsHtml =
      `<button type="button" class="wb-card-act pin-btn${item.pinned ? " active" : ""}" data-wb-act="pin" title="${
        item.pinned ? "取消置顶" : "置顶锁定该共识"
      }">${item.pinned ? "已置顶" : "置顶"}</button>` +
      `<button type="button" class="wb-card-act" data-wb-act="edit" title="行内编辑">编辑</button>` +
      `<button type="button" class="wb-card-act del-btn" data-wb-act="del" title="移除条目">✕</button>`;
  } else if (isRisk) {
    actionsHtml =
      `<button type="button" class="wb-act-pill discuss-btn" data-wb-act="discuss" title="围绕该争议项发起圆桌定向讨论裁决">定向讨论</button>` +
      `<button type="button" class="wb-act-pill adopt-btn" data-wb-act="adopt" title="将该条目采纳移入第一区「已确认共识与约束」">采纳为共识</button>` +
      `<button type="button" class="wb-card-act" data-wb-act="edit" title="行内编辑">编辑</button>` +
      `<button type="button" class="wb-card-act del-btn" data-wb-act="del" title="移除条目">✕</button>`;
  } else {
    actionsHtml =
      `<button type="button" class="wb-card-act" data-wb-act="edit" title="行内编辑">编辑</button>` +
      `<button type="button" class="wb-card-act del-btn" data-wb-act="del" title="移除条目">✕</button>`;
  }

  li.innerHTML =
    `<div class="wb-pool-main">` +
      (isAction
        ? `<button type="button" class="wb-task-check${isChecked ? " checked" : ""}" data-wb-act="check" aria-pressed="${
            isChecked ? "true" : "false"
          }" title="${isChecked ? "已纳入本轮执行范围（点击取消勾选排除）" : "已排除在本次执行范围之外（点击重新纳入）"}">${
            isChecked ? "✓" : ""
          }</button>`
        : "") +
      `<div class="wb-pool-text" title="单击直接编辑内容">${escapeHtml(item.text)}</div>` +
    `</div>` +
    `<div class="wb-pool-meta">` +
      `<button type="button" class="wb-seat-mini-badge ${authorMeta.cls}" data-wb-act="source" title="${escapeHtml(srcTip)}">` +
        `<span class="mini-seat-dot">${escapeHtml(authorMeta.short)}</span>` +
        `<span>${escapeHtml(authorMeta.name)}</span>` +
      `</button>` +
      `<div class="wb-pool-actions">${actionsHtml}</div>` +
    `</div>`;

  const textDiv = li.querySelector(".wb-pool-text");
  if (textDiv) {
    textDiv.onclick = (e) => {
      e.stopPropagation();
      startInlineWbItemEdit(li, item);
    };
  }

  li.querySelectorAll("[data-wb-act]").forEach((btn) => {
    btn.onclick = async (e) => {
      e.stopPropagation();
      const act = btn.dataset.wbAct;
      if (act === "source") {
        scrollToSourceMessage(item.source_msg_id);
      } else if (act === "pin") {
        await postWhiteboardMutation({ op: "toggle_pin", item_id: item.id });
      } else if (act === "check") {
        await postWhiteboardMutation({
          op: "toggle_check",
          item_id: item.id,
          checked: !isChecked,
        });
      } else if (act === "adopt") {
        state.wbKnownItemIds.delete(`${item.id}:decision`);
        const updated = await postWhiteboardMutation({
          op: "adopt_decision",
          item_id: item.id,
        });
        if (updated) {
          pulseWbTabBadge();
          showToast("已采纳至「已确认共识与约束」", "ok", 1800);
        }
      } else if (act === "discuss") {
        await discussRiskItem(item);
      } else if (act === "edit") {
        startInlineWbItemEdit(li, item);
      } else if (act === "del") {
        await postWhiteboardMutation({
          op: "remove",
          item_id: item.id,
          ver: item.ver,
        });
      }
    };
  });

  return li;
}

function startInlineWbItemEdit(liEl, item) {
  if (!liEl || liEl.classList.contains("editing")) return;
  liEl.classList.add("editing");
  liEl.innerHTML =
    `<div class="wb-edit-box">` +
      `<textarea class="wb-edit-input" rows="2">${escapeHtml(item.text)}</textarea>` +
      `<div class="wb-edit-toolbar">` +
        `<span class="wb-edit-ver">v${item.ver} · Enter 保存 / Esc 取消</span>` +
        `<div class="wb-edit-btns">` +
          `<button type="button" class="wb-edit-cancel-btn">取消</button>` +
          `<button type="button" class="wb-edit-save-btn">保存</button>` +
        `</div>` +
      `</div>` +
    `</div>`;

  const input = liEl.querySelector(".wb-edit-input");
  const saveBtn = liEl.querySelector(".wb-edit-save-btn");
  const cancelBtn = liEl.querySelector(".wb-edit-cancel-btn");

  const commit = async () => {
    const nextVal = (input?.value || "").trim();
    if (nextVal === item.text) {
      if (state.whiteboard) renderWhiteboard(state.whiteboard, true, false);
      return;
    }
    await postWhiteboardMutation(
      {
        op: nextVal ? "update" : "remove",
        item_id: item.id,
        text: nextVal,
        ver: item.ver,
      },
      nextVal
    );
  };

  const cancel = () => {
    if (state.whiteboard) renderWhiteboard(state.whiteboard, true, false);
  };

  saveBtn?.addEventListener("click", (e) => {
    e.stopPropagation();
    commit();
  });
  cancelBtn?.addEventListener("click", (e) => {
    e.stopPropagation();
    cancel();
  });
  input?.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing && e.keyCode !== 229) {
      e.preventDefault();
      commit();
    } else if (e.key === "Escape") {
      e.preventDefault();
      cancel();
    }
  });
  if (input) {
    input.focus();
    input.setSelectionRange(input.value.length, input.value.length);
  }
}

function startInlineTopicEdit() {
  const topicBox = el("wbTopicText");
  if (!topicBox || topicBox.querySelector("#wbTopicEditInput")) return;
  const currentFullTopic = state.whiteboard?.topic || state.topic || "";
  topicBox.innerHTML =
    `<div class="wb-edit-box">` +
      `<textarea id="wbTopicEditInput" class="wb-edit-input" rows="2" placeholder="输入或修订当前会议完整议题…">${escapeHtml(
        currentFullTopic
      )}</textarea>` +
      `<div class="wb-edit-toolbar">` +
        `<span class="wb-edit-ver">Enter 保存议题 · Esc 取消</span>` +
        `<div class="wb-edit-btns">` +
          `<button type="button" class="wb-edit-cancel-btn">取消</button>` +
          `<button type="button" class="wb-edit-save-btn">保存</button>` +
        `</div>` +
      `</div>` +
    `</div>`;

  const inp = el("wbTopicEditInput");
  const save = async () => {
    const val = (inp?.value || "").trim();
    if (!val || val === currentFullTopic) {
      if (state.whiteboard) renderWhiteboard(state.whiteboard, true, false);
      return;
    }
    await postWhiteboardMutation({ topic: val }, val);
  };
  const cancel = () => {
    if (state.whiteboard) renderWhiteboard(state.whiteboard, true, false);
  };

  topicBox.querySelector(".wb-edit-save-btn")?.addEventListener("click", (e) => {
    e.stopPropagation();
    save();
  });
  topicBox.querySelector(".wb-edit-cancel-btn")?.addEventListener("click", (e) => {
    e.stopPropagation();
    cancel();
  });
  inp?.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing && e.keyCode !== 229) {
      e.preventDefault();
      save();
    } else if (e.key === "Escape") {
      e.preventDefault();
      cancel();
    }
  });
  if (inp) {
    inp.focus();
    inp.setSelectionRange(inp.value.length, inp.value.length);
  }
}

function renderWhiteboard(rawWb, forceRender = false, isInitialSnapshot = false) {
  const wb = normalizeClientWhiteboard(rawWb);
  state.whiteboard = wb;

  if (wb.consensus_status && el("wbConsensusTag")) {
    el("wbConsensusTag").textContent = wb.consensus_status;
  }

  const allItems = wb.items || [];
  const decisionItems = [
    ...allItems.filter((it) => it.kind === "decision" && it.pinned),
    ...allItems.filter((it) => it.kind === "decision" && !it.pinned),
  ];
  const riskItems = allItems.filter((it) => it.kind === "risk");
  const actionItems = allItems.filter((it) => it.kind === "action");
  const checkedActionCount = actionItems.filter((it) => it.checked !== false).length;

  const totalCount = allItems.length;
  if (el("wbCountBadge")) {
    el("wbCountBadge").textContent = String(totalCount);
  }
  if (!isInitialSnapshot && totalCount > state.lastWbTotalCount) {
    pulseWbTabBadge();
  }
  state.lastWbTotalCount = totalCount;

  // 同步执行终端日志、Diff 与回滚按钮
  if (Array.isArray(wb.exec_logs) && wb.exec_logs.length > 0 && el("astraTermLogs")) {
    el("astraTermLogs").textContent = wb.exec_logs.join("\n");
    el("astraTermLogs").scrollTop = el("astraTermLogs").scrollHeight;
  } else if (!state.isBusy && el("astraTermLogs") && (!wb.exec_logs || !wb.exec_logs.length) && !wb.exec_summary) {
    el("astraTermLogs").textContent = "尚未触发执行任务";
  }
  if (el("astraDiffView")) {
    el("astraDiffView").innerHTML = renderDiffHtml(wb.exec_diff || "");
  }
  el("rollbackExecBtn")?.classList.toggle("hidden", !wb.can_rollback);

  // 当存在聚焦中的 .wb-edit-input 时，豁免后台 SSE 全量重绘覆盖用户正在输入的草稿
  const activeEl = document.activeElement;
  if (
    !forceRender &&
    activeEl &&
    (activeEl.classList.contains("wb-edit-input") || activeEl.id === "wbTopicEditInput")
  ) {
    return;
  }

  const topicEl = el("wbTopicText");
  if (topicEl) {
    const fullTopic = wb.topic || state.topic || "";
    topicEl.textContent = fullTopic || "未设置议题（发起研讨后自动锁定，单击可编辑）";
    topicEl.classList.toggle("editable", true);
    topicEl.title = fullTopic ? "单击内联编辑完整议题" : "单击设置议题";
  }

  if (el("wbDecisionCount")) el("wbDecisionCount").textContent = String(decisionItems.length);
  if (el("wbRiskCount")) el("wbRiskCount").textContent = String(riskItems.length);
  if (el("wbActionCount")) {
    el("wbActionCount").textContent = `${checkedActionCount}/${actionItems.length} 项待执行`;
  }

  const renderZoneList = (listId, zoneItems, zoneKind, emptyText) => {
    const ul = el(listId);
    if (!ul) return;
    ul.innerHTML = "";
    if (!zoneItems.length) {
      ul.classList.add("empty-hint");
      const tip = document.createElement("li");
      tip.className = "wb-empty-tip";
      tip.textContent = emptyText;
      ul.appendChild(tip);
      return;
    }
    ul.classList.remove("empty-hint");
    for (const it of zoneItems) {
      const animKey = `${it.id}:${zoneKind}`;
      const shouldAnimate = !isInitialSnapshot && !state.wbKnownItemIds.has(animKey);
      state.wbKnownItemIds.add(animKey);
      ul.appendChild(buildWbPoolItemElement(it, zoneKind, shouldAnimate));
    }
  };

  if (isInitialSnapshot) {
    state.wbKnownItemIds.clear();
    for (const it of allItems) {
      state.wbKnownItemIds.add(`${it.id}:${it.kind}`);
    }
  }

  renderZoneList(
    "wbDecisionList",
    decisionItems,
    "decision",
    "主持约束与各方确认的架构共识将在此置顶锁定，后续轮次严格遵循"
  );
  renderZoneList(
    "wbRiskList",
    riskItems,
    "risk",
    "悬浮条目可发起「定向讨论」聚焦裁决，或点击「采纳为共识」移入第一区"
  );
  renderZoneList(
    "wbActionList",
    actionItems,
    "action",
    "勾选需在本轮交付的任务项（取消勾选将排除在本次代码修改范围之外）"
  );

  const jumpBtn = el("wbToExecBtn");
  if (jumpBtn) {
    const execName = AGENT_NAMES[state.executorAgent] || "工程师";
    jumpBtn.textContent =
      actionItems.length > 0
        ? `前往执行终端由 ${execName} 交付已选任务 (${checkedActionCount}/${actionItems.length}) →`
        : `前往执行终端交由 ${execName} 交付 →`;
  }
}

/* ==================== 会议纪要 Markdown 规范四节排版导出 ==================== */

function buildMinutesMarkdown() {
  const wb = normalizeClientWhiteboard(state.whiteboard || {});
  const items = wb.items || [];
  const decisions = items.filter((i) => i.kind === "decision");
  const risks = items.filter((i) => i.kind === "risk");
  const actions = items.filter((i) => i.kind === "action");
  const title = wb.topic_title || state.topic || "AI圆桌会议纪要";
  const modeSpec = COLLAB_MODES[state.collabMode] || COLLAB_MODES.deep_deliberation;
  const ws = effectiveWorkspacePath() || "未绑定本地目录";

  const lines = [
    `# ${title}`,
    "",
    `- **讨论策略**：${modeSpec.label}（${modeSpec.hint}）`,
    `- **项目工作区**：\`${ws}\``,
    `- **会议状态**：${wb.consensus_status || STAGE_LABELS[state.stage] || "待命"}`,
    wb.topic && wb.topic !== title ? `- **完整议题**：${wb.topic}` : "",
    "",
    "## 一、已确认共识与约束",
    ...(decisions.length
      ? decisions.map(
          (it) =>
            `- ${it.pinned ? "**[置顶约束]** " : ""}${it.text} *(${
              AUTHOR_BADGE_META[it.author]?.name || it.author
            })*`
        )
      : ["- 暂无已确认共识记录"]),
    "",
    "## 二、风险审计与边界防线",
    ...(risks.length
      ? risks.map((it) => `- ${it.text} *(${AUTHOR_BADGE_META[it.author]?.name || it.author})*`)
      : ["- 暂无待决争议或风险项"]),
    "",
    "## 三、执行任务清单",
    ...(actions.length
      ? actions.map(
          (it) =>
            `- [${it.checked !== false ? "x" : " "}] ${it.text} *(${
              AUTHOR_BADGE_META[it.author]?.name || it.author
            })*`
        )
      : ["- [ ] 暂无待执行任务项"]),
    "",
    "## 四、完整研讨记录",
    "",
  ].filter((x) => x !== null);

  for (const msg of state.messages.values()) {
    if (!msg.content || msg.skipped) continue;
    const rolePart = msg.role_title ? ` · ${msg.role_title}` : "";
    const phasePart = msg.phase_label ? ` [${msg.phase_label}]` : "";
    lines.push(`### ${msg.speaker_name || AGENT_NAMES[msg.speaker] || "发言"}${rolePart}${phasePart}`);
    lines.push("");
    lines.push(stripInternalStatusLines(msg.content));
    lines.push("");
  }

  return lines.join("\n").trim() + "\n";
}

async function copyTextToClipboard(text, okMsg = "已复制到剪贴板") {
  if (!text) {
    showToast("暂无可复制内容", "warn", 1800);
    return;
  }
  try {
    await navigator.clipboard.writeText(text);
    showToast(okMsg, "ok", 2000);
  } catch {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    ta.remove();
    showToast(okMsg, "ok", 2000);
  }
}

async function exportMinutesMarkdownFile() {
  const md = buildMinutesMarkdown();
  if (window.webkit?.messageHandlers?.roundtableNative) {
    try {
      const result = await apiFetch(`/api/sessions/${state.currentSessionId}/export`, {
        method: "POST",
        body: JSON.stringify({ markdown: md }),
      });
      showToast(`会议纪要已保存到 ${result.saved_path}`, "ok", 4000);
    } catch (err) {
      showToast(err.message || "导出会议纪要失败", "err");
    }
    return;
  }
  const safeName = (state.whiteboard?.topic_title || state.topic || "AI圆桌纪要")
    .replace(/[\\/:*?"<>|\s]+/g, "_")
    .slice(0, 36);
  const blob = new Blob([md], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${safeName || "AI圆桌纪要"}.md`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  showToast("已导出规范四节排版的 .md 会议纪要", "ok", 2200);
}

/* ==================== 顶栏四阶段进度、精简席位条与一体化席位配置浮层 ==================== */

function renderStageAndHeader() {
  const stage = state.stage || "idle";
  const hasTopic = Boolean(state.topic);

  const heading = el("currentTopicTitle");
  if (heading) {
    const dispTitle = state.whiteboard?.topic_title || state.topic || "新圆桌会议";
    heading.textContent = dispTitle;
    heading.title = state.topic || dispTitle;
  }

  const pill = el("stageStatusPill");
  if (pill) {
    if (stage === "idle" && !hasTopic) {
      pill.classList.add("hidden");
    } else {
      pill.classList.remove("hidden");
      pill.textContent = STAGE_LABELS[stage] || "研讨中";
      pill.classList.toggle("pill-done", stage === "concluded");
    }
  }

  // 四阶段进度胶囊：① 独立初评 → ② 交叉质询 → ③ 形成决议 → ④ 执行交付
  const stepOrder = ["opening", "discussion", "consensus", "execution"];
  let activeStepIdx = -1;
  if (stage === "opening_parallel") activeStepIdx = 0;
  else if (stage === "cross_talk" || stage === "chair_interrupt" || stage === "awaiting_chair") activeStepIdx = 1;
  else if (stage === "concluded") activeStepIdx = 2;
  else if (stage === "executing") activeStepIdx = 3;

  document.querySelectorAll("#stageStepper .step-item").forEach((node) => {
    const key = node.dataset.step;
    const idx = stepOrder.indexOf(key);
    node.classList.toggle("active", idx === activeStepIdx && (hasTopic || state.isBusy));
    node.classList.toggle("done", activeStepIdx > idx);
  });

  // 底部控场栏与输入框模式联动
  const preBar = el("preMeetingModeBar");
  const mentionBar = el("activeMentionBar");
  const quickBar = el("quickCueBar");
  const stopBtn = el("stopFlowBtn");
  const busyBanner = el("cueBusyBanner");
  const decisionGroup = el("cueDecisionGroup");
  const primaryBtn = el("primaryActionBtn");
  const composerBox = el("composerBox");
  const topicInp = el("topicInput");

  const inMeeting = state.messages.size > 0 || state.isBusy;
  preBar?.classList.toggle("hidden", inMeeting);
  mentionBar?.classList.toggle("hidden", !inMeeting);
  quickBar?.classList.toggle("hidden", !inMeeting);

  if (inMeeting) {
    stopBtn?.classList.toggle("hidden", !state.isBusy);
    busyBanner?.classList.toggle("hidden", !state.isBusy);
    el("cueGroupLeft")?.classList.toggle("hidden", state.isBusy);
    decisionGroup?.classList.toggle("hidden", state.isBusy);
  }

  if (composerBox) {
    composerBox.classList.toggle("interrupt-mode", state.isBusy);
  }
  if (primaryBtn) {
    if (state.isBusy) {
      primaryBtn.textContent = "插话控场";
      primaryBtn.classList.add("btn-interrupt");
    } else if (inMeeting) {
      primaryBtn.textContent = "发送追问";
      primaryBtn.classList.remove("btn-interrupt");
    } else {
      primaryBtn.textContent = "开始研讨";
      primaryBtn.classList.remove("btn-interrupt");
    }
  }
  if (topicInp) {
    if (state.isBusy) {
      topicInp.placeholder = "研讨进行中，随时输入新约束插话控场，或使用 @席位名 定向提问";
    } else if (inMeeting) {
      topicInp.placeholder = "输入补充追问、使用 @席位名 点名深挖，或输入 @文件路径 注入源码";
    } else {
      topicInp.placeholder = "输入技术议题开启研讨，输入 @ 引用项目源码或 @文件:起始行-结束行 切片";
    }
  }

  renderWorkspaceBadges();
  renderQuickCueButtons();
  renderExecutorControls();
}

function renderWorkspaceBadges() {
  const ws = effectiveWorkspacePath();
  const folderName = ws ? ws.split("/").filter(Boolean).pop() || ws : "";

  const headerChip = el("headerWsChip");
  const headerName = el("headerWsName");
  if (headerChip && headerName) {
    headerChip.classList.toggle("ws-bound", Boolean(ws));
    headerChip.classList.toggle("ws-unbound", !ws);
    headerName.textContent = folderName || "选择本地项目";
    headerChip.title = ws ? `当前绑定本地工作区：${ws}（点击切换）` : "尚未绑定本地项目，点击选择本地项目目录";
  }

  const wsName = el("workspaceName");
  const wsBadge = el("workspaceBadge");
  if (wsName) wsName.textContent = folderName || "选择本地项目";
  if (wsBadge) {
    wsBadge.textContent = ws || "尚未绑定本地项目目录";
    wsBadge.title = ws;
  }

  const emptyBtn = el("emptyBindWsBtn");
  const emptyName = el("emptyWsName");
  if (emptyBtn && emptyName) {
    emptyBtn.classList.toggle("ws-bound", Boolean(ws));
    emptyName.textContent = ws ? `已绑定：${folderName}` : "点击绑定本地项目目录";
    emptyBtn.title = ws ? `${ws}（点击切换项目目录）` : "点击选择或切换本地项目工作区";
  }
}

function renderSeatCard(agentId) {
  const seatEl = el(`seat-${agentId}`);
  if (!seatEl) return;

  const st = state.seatStates[agentId] || {};
  const sysInfo = state.system?.agents?.[agentId] || {};
  const enabled = state.enabledAgents.includes(agentId);
  const isSolo = state.enabledAgents.length === 1 && state.enabledAgents[0] === agentId;
  const personaKey = state.seatPersonas[agentId] || DEFAULT_SEAT_PERSONAS[agentId];
  const pSpec = getPersonaSpec(personaKey, agentId);
  const status = st.status || "idle";

  seatEl.className = [
    "seat-card",
    `seat-${agentId}`,
    `status-${status}`,
    !enabled ? "seat-disabled" : "",
    isSolo ? "seat-is-solo" : "",
  ]
    .filter(Boolean)
    .join(" ");

  const roleTextEl = el(`seat-role-text-${agentId}`);
  if (roleTextEl) {
    roleTextEl.textContent = pSpec.short_tag || pSpec.label;
  }

  const cornerEl = el(`seat-corner-${agentId}`);
  if (cornerEl) {
    if (isSolo) {
      cornerEl.textContent = "专注";
      cornerEl.classList.remove("hidden", "is-paused");
    } else if (!enabled) {
      cornerEl.textContent = "已暂停";
      cornerEl.classList.remove("hidden");
      cornerEl.classList.add("is-paused");
    } else {
      cornerEl.textContent = "";
      cornerEl.classList.add("hidden");
      cornerEl.classList.remove("is-paused");
    }
  }

  const badgeEl = el(`seat-badge-${agentId}`);
  if (badgeEl) {
    let badgeText = st.badge || (sysInfo.binary_detected ? "已就绪" : "未检测到 CLI");
    if (!enabled && status === "idle") {
      badgeText = "暂停参会";
    } else if (status === "idle" && st.elapsed_ms > 0 && badgeText && !badgeText.includes("s")) {
      badgeText = `${badgeText} · ${(st.elapsed_ms / 1000).toFixed(1)}s`;
    }
    badgeEl.textContent = badgeText;
  }

  const teleEl = el(`seat-tele-${agentId}`);
  if (teleEl) {
    const model = st.effective_model || sysInfo.effective_model || "";
    const effort = state.seatEfforts[agentId] || st.effective_effort || sysInfo.effective_discussion_effort || "";
    teleEl.textContent = [model, effort].filter(Boolean).join(" · ") || DRIVER_LABELS[sysInfo.effective_driver] || "";
  }
}

function syncMentionChipActiveStates() {
  const val = el("topicInput")?.value || "";
  document.querySelectorAll("#mentionChipsWrap [data-mention-seat]").forEach((btn) => {
    const aid = btn.dataset.mentionSeat;
    const token = `@${AGENT_NAMES[aid] || aid}`;
    const escaped = escapeRegExp(token);
    const tokenRe = new RegExp(`(^|\\s)${escaped}(?=\\s|$)`, "i");
    btn.classList.toggle("is-mentioned", tokenRe.test(val));
  });
}

function renderAllSeats() {
  syncDynamicRosterNames();
  AGENT_ORDER.forEach((aid) => renderSeatCard(aid));
  // 同步底部 @点名胶囊可见状态
  const isSolo = state.enabledAgents.length === 1;
  const wrap = el("mentionChipsWrap");
  const label = el("mentionBarLabel");
  if (wrap && label) {
    if (isSolo) {
      const soloAid = state.enabledAgents[0];
      const pSpec = getPersonaSpec(state.seatPersonas[soloAid], soloAid);
      label.textContent = "当前模式：";
      wrap.innerHTML = `<span class="solo-mention-pill">${escapeHtml(AGENT_NAMES[soloAid])} · ${escapeHtml(
        pSpec.label
      )}（单席专注）</span>`;
    } else {
      label.textContent = "定向点名：";
      wrap.innerHTML = AGENT_ORDER.map(
        (aid) =>
          `<button type="button" class="mention-btn" data-mention-seat="${aid}" data-mention="@${AGENT_NAMES[aid]} " title="点名 ${AGENT_NAMES[aid]} 回应">@${AGENT_NAMES[aid]}</button>`
      ).join("");
      wrap.querySelectorAll("[data-mention]").forEach((btn) => {
        btn.onclick = () => insertMentionIntoComposer(btn.dataset.mention);
      });
      syncMentionChipActiveStates();
    }
  }
}

function openPersonaPopover(agentId, anchorEl) {
  const pop = el("personaPopover");
  if (!pop || !anchorEl) return;

  if (!pop.classList.contains("hidden") && state.personaPopoverSeat === agentId) {
    closePersonaPopover();
    return;
  }
  state.personaPopoverSeat = agentId;
  renderPersonaPopoverContents(agentId);
  pop.classList.remove("hidden");

  const rect = anchorEl.getBoundingClientRect();
  const popWidth = 298;
  const left = Math.min(Math.max(12, rect.left - 8), window.innerWidth - popWidth - 12);
  const top = Math.min(rect.bottom + 8, window.innerHeight - 400);
  pop.style.left = `${left}px`;
  pop.style.top = `${Math.max(12, top)}px`;
}

function closePersonaPopover() {
  const pop = el("personaPopover");
  if (pop) pop.classList.add("hidden");
  state.personaPopoverSeat = null;
}

function renderPersonaPopoverContents(agentId) {
  const titleEl = el("personaPopoverTitle");
  const listEl = el("personaOptionList");
  const effortBox = el("seatPopoverEffortBox");
  const actionsBox = el("seatPopoverQuickActions");
  if (!titleEl || !listEl || !effortBox || !actionsBox) return;

  const sysAgent = state.system?.agents?.[agentId] || {};
  const st = state.seatStates[agentId] || {};
  const effDrv = st.effective_driver || sysAgent.effective_driver || sysAgent.driver || "agy";
  const effModel = st.effective_model || sysAgent.effective_model || sysAgent.model || "";
  const curPersona = state.seatPersonas[agentId] || DEFAULT_SEAT_PERSONAS[agentId];
  const curCustomName = sysAgent.custom_name || "";
  const personaMap = getPersonaMap();

  titleEl.innerHTML =
    `<span>${escapeHtml(AGENT_NAMES[agentId])} 席位快捷配置</span>` +
    `<span class="persona-pop-model">${escapeHtml(effModel || DRIVER_LABELS[effDrv] || effDrv)}</span>`;

  listEl.innerHTML = "";
  const renameRow = document.createElement("div");
  renameRow.className = "seat-pop-rename-box";
  renameRow.innerHTML =
    `<input type="text" class="seat-pop-rename-inp" maxlength="20" value="${escapeHtml(
      curCustomName
    )}" placeholder="自定义名称（当前：${escapeHtml(AGENT_NAMES[agentId])}）" />` +
    `<button type="button" class="seat-pop-rename-btn">改名</button>`;
  const renameInp = renameRow.querySelector(".seat-pop-rename-inp");
  const renameBtn = renameRow.querySelector(".seat-pop-rename-btn");
  const saveQuickSeatName = async () => {
    const nextName = (renameInp?.value || "").trim();
    try {
      const cfgRes = await apiFetch("/api/config", {
        method: "POST",
        body: JSON.stringify({
          active_session_id: state.currentSessionId || "",
          agents: { [agentId]: { custom_name: nextName } },
        }),
      });
      if (cfgRes.system) {
        renderSystemStatus(cfgRes.system);
      } else {
        syncDynamicRosterNames();
        renderAllSeats();
      }
      renderQuickCueButtons();
      renderExecutorControls();
      if (state.whiteboard) renderWhiteboard(state.whiteboard, true, false);
      renderPersonaPopoverContents(agentId);
      showToast(nextName ? `席位名称已设为「${nextName}」` : `已恢复预设名称「${AGENT_NAMES[agentId]}」`, "ok", 1800);
    } catch (err) {
      showToast(err.message || "修改名称失败", "err");
    }
  };
  renameBtn?.addEventListener("click", (ev) => {
    ev.stopPropagation();
    saveQuickSeatName();
  });
  renameInp?.addEventListener("click", (ev) => ev.stopPropagation());
  renameInp?.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter" && !ev.isComposing) {
      ev.preventDefault();
      saveQuickSeatName();
    }
  });
  listEl.appendChild(renameRow);

  for (const pKey of PERSONA_ORDER) {
    const spec = personaMap[pKey] || DEFAULT_PERSONA_PRESETS[pKey];
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = `persona-opt-btn${curPersona === pKey ? " active" : ""}`;
    btn.innerHTML =
      `<div class="persona-opt-top">` +
        `<span>${escapeHtml(spec.label)}（${escapeHtml(spec.short_tag)}）</span>` +
        `<span>${curPersona === pKey ? "✓" : ""}</span>` +
      `</div>` +
      `<div class="persona-opt-desc">${escapeHtml(spec.desc || DEFAULT_PERSONA_PRESETS[pKey]?.desc || "")}</div>`;
    btn.onclick = async (e) => {
      e.stopPropagation();
      state.seatPersonas[agentId] = pKey;
      renderPersonaPopoverContents(agentId);
      await persistSessionSeatsPatch({ seat_personas: { [agentId]: pKey } });
      showToast(`${AGENT_NAMES[agentId]} 已切换为「${spec.label}」`, "ok", 1800);
    };
    listEl.appendChild(btn);
  }

  // 动态合法讨论推理档位胶囊
  const effortSpec = getEffortSpecForModel(effDrv, effModel, agentId);
  const curEffort =
    state.seatEfforts[agentId] ||
    st.effective_effort ||
    sysAgent.effective_discussion_effort ||
    effortSpec.default ||
    "";

  if (!effortSpec.supports_effort || !effortSpec.allowed?.length) {
    effortBox.innerHTML =
      `<div class="seat-pop-effort-head"><span>本场讨论推理档位</span><span class="seat-pop-effort-note">当前模型自动省略档位参数</span></div>`;
  } else {
    effortBox.innerHTML =
      `<div class="seat-pop-effort-head"><span>本场讨论推理档位</span><span class="seat-pop-effort-note">严格按所选档位调用</span></div>` +
      `<div class="seat-effort-pills">` +
        effortSpec.allowed
          .map(
            (lv) =>
              `<button type="button" class="seat-effort-pill${curEffort === lv ? " active" : ""}" data-seat-pop-effort="${escapeHtml(
                lv
              )}">${escapeHtml(lv)}</button>`
          )
          .join("") +
      `</div>`;

    effortBox.querySelectorAll("[data-seat-pop-effort]").forEach((pill) => {
      pill.onclick = async (e) => {
        e.stopPropagation();
        const chosenLv = pill.dataset.seatPopEffort;
        state.seatEfforts[agentId] = chosenLv;
        renderPersonaPopoverContents(agentId);
        try {
          await persistSessionSeatsPatch({ seat_efforts: { [agentId]: chosenLv } });
          await apiFetch("/api/config", {
            method: "POST",
            body: JSON.stringify({
              active_session_id: state.currentSessionId || "",
              agents: {
                [agentId]: { discussion_effort: chosenLv },
              },
            }),
          });
          showToast(`${AGENT_NAMES[agentId]} 讨论档位已设为 ${chosenLv}`, "ok", 1800);
        } catch (err) {
          showToast(err.message || "切换推理档位失败", "err");
        }
      };
    });
  }

  // 单席专注模式与本场参会启用开关
  const isSolo = state.enabledAgents.length === 1 && state.enabledAgents[0] === agentId;
  const seatOn = state.enabledAgents.includes(agentId);

  actionsBox.innerHTML =
    `<button type="button" class="seat-pop-toggle-row${isSolo ? " is-active" : ""}" data-seat-pop-act="solo">` +
      `<span>仅此席专注模式（单席包揽设计与执行）</span>` +
      `<span class="mini-toggle-track${isSolo ? " on" : ""}"><span class="mini-toggle-thumb"></span></span>` +
    `</button>` +
    `<button type="button" class="seat-pop-toggle-row${seatOn ? " is-active" : ""}" data-seat-pop-act="toggle-enable">` +
      `<span>本场参会启用状态</span>` +
      `<span class="mini-toggle-track${seatOn ? " on" : ""}"><span class="mini-toggle-thumb"></span></span>` +
    `</button>`;

  actionsBox.querySelector("[data-seat-pop-act='solo']")?.addEventListener("click", async (e) => {
    e.stopPropagation();
    const nextEnabled = isSolo ? ["carbon", "grok", "astra"] : [agentId];
    const nextExec = isSolo ? "astra" : agentId;
    try {
      await persistSessionSeatsPatch({
        enabled_agents: nextEnabled,
        executor_agent: nextExec,
      });
      renderPersonaPopoverContents(agentId);
      showToast(
        isSolo ? "已恢复三席协同研讨模式" : `已开启 ${AGENT_NAMES[agentId]} 单席专注模式`,
        "ok",
        2000
      );
    } catch (err) {
      showToast(err.message || "切换专注模式失败", "err");
    }
  });

  actionsBox.querySelector("[data-seat-pop-act='toggle-enable']")?.addEventListener("click", async (e) => {
    e.stopPropagation();
    let nextEnabled;
    if (seatOn) {
      if (state.enabledAgents.length <= 1) {
        showToast("至少需保留一个启用中的参会席位", "warn", 2000);
        return;
      }
      nextEnabled = state.enabledAgents.filter((a) => a !== agentId);
    } else {
      nextEnabled = AGENT_ORDER.filter((a) => a === agentId || state.enabledAgents.includes(a));
    }
    try {
      await persistSessionSeatsPatch({ enabled_agents: nextEnabled });
      renderPersonaPopoverContents(agentId);
    } catch (err) {
      showToast(err.message || "更新席位状态失败", "err");
    }
  });
}

function renderQuickCueButtons() {
  const leftBox = el("cueGroupLeft");
  if (!leftBox) return;
  leftBox.innerHTML = "";
  for (const aid of state.enabledAgents) {
    const pKey = state.seatPersonas[aid] || DEFAULT_SEAT_PERSONAS[aid];
    const pSpec = getPersonaSpec(pKey, aid);
    const label = (pSpec.cue_btn || "请 {name} 发言").replace("{name}", AGENT_NAMES[aid]);
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "cue-btn";
    btn.textContent = label;
    btn.onclick = async () => {
      if (!state.currentSessionId) return;
      try {
        await apiFetch(`/api/sessions/${state.currentSessionId}/cue`, {
          method: "POST",
          body: JSON.stringify({
            agent_id: aid,
            instruction: pSpec.cue_prompt || "请针对当前分歧给出深入判断与收敛建议",
          }),
        });
      } catch (err) {
        showToast(err.message || "定向追问失败", "err");
      }
    };
    leftBox.appendChild(btn);
  }
}

function renderExecutorControls() {
  const execAid = AGENT_ORDER.includes(state.executorAgent) ? state.executorAgent : "astra";
  const execName = AGENT_NAMES[execAid] || "工程师";
  const allowWrite = Boolean(el("allowWriteCheckbox")?.checked);
  const ws = effectiveWorkspacePath();

  document.querySelectorAll("#executorSegmented [data-exec-agent]").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.execAgent === execAid);
  });

  document.querySelectorAll("#sandboxSegmented [data-write-mode]").forEach((btn) => {
    const isWriteBtn = btn.dataset.writeMode === "write";
    btn.classList.toggle("active", isWriteBtn === allowWrite);
  });

  if (el("executeBtn")) {
    el("executeBtn").textContent = `交由 ${execName} 执行 →`;
  }
  if (el("runExecFromTabBtn")) {
    el("runExecFromTabBtn").textContent = state.stage === "executing" ? `${execName} 执行中…` : `启动 ${execName} 执行`;
    el("runExecFromTabBtn").disabled = state.stage === "executing";
  }
  el("stopExecFromTabBtn")?.classList.toggle("hidden", state.stage !== "executing");
  if (el("termTargetTitle")) {
    el("termTargetTitle").textContent = `${execName} · 执行终端`;
  }

  const descEl = el("execModeDesc");
  if (descEl) {
    if (!ws) {
      descEl.classList.remove("warn");
      descEl.textContent = "当前未绑定本地项目：点击执行将依据白板已确认共识与已勾选任务输出《工程实施方案报告》。";
    } else if (allowWrite) {
      descEl.classList.add("warn");
      descEl.textContent = state.workspaceIsGit
        ? `将直接写入本地仓库（${ws}），仅实施白板已勾选任务；执行前自动创建 Git 快照支持一键回滚。`
        : `注意：当前目录（${ws}）非 Git 仓库，写入将直接作用于磁盘文件，请谨慎确认已勾选任务范围。`;
    } else {
      descEl.classList.remove("warn");
      descEl.textContent = `只读预演模式（${ws}）：依据白板已锁定共识与已勾选任务生成代码补丁预览，不修改本地文件。`;
    }
  }
}

/* ==================== 本地 CLI 引擎状态与连通实测 ==================== */

function renderSystemStatus(sys) {
  if (!sys) return;
  state.system = sys;
  state.pacingMode = sys.pacing_mode || "unrestricted";
  state.idleTimeoutSec = Number(sys.idle_timeout_sec ?? 900);
  state.turnTimeoutSec = Number(sys.turn_timeout_sec ?? 0);
  state.maxRefChars = Number(sys.max_ref_chars ?? 120000);
  if (sys.roster_preset) {
    state.rosterPreset = sys.roster_preset;
  }
  if (typeof sys.single_cli_concurrency === "number") {
    state.singleCliConcurrency = sys.single_cli_concurrency;
  }
  if (!state.sessionWorkspaceDir) {
    state.workspaceIsGit = Boolean(sys.workspace_is_git);
  }
  syncDynamicRosterNames();

  const agents = sys.agents || {};
  let readyCount = 0;
  let sharedCount = 0;
  AGENT_ORDER.forEach((aid) => {
    if (agents[aid]?.binary_detected) readyCount += 1;
    if (agents[aid]?.shared_fallback) sharedCount += 1;
  });

  const summaryBar = el("readySummaryBar");
  if (summaryBar) {
    summaryBar.classList.remove("all-ready", "warn-ready");
    if (readyCount === 3 && sharedCount === 0) {
      summaryBar.classList.add("all-ready");
      summaryBar.textContent = "3 席本地 CLI 引擎全部就绪 · 支持多模型并行深度交锋";
    } else if (readyCount >= 1) {
      summaryBar.classList.add("all-ready");
      const concModeLabel = (state.singleCliConcurrency || 3) > 1 ? `${state.singleCliConcurrency || 3} 席并发` : "串行";
      summaryBar.textContent =
        sharedCount > 0
          ? `已启用单引擎多角色无状态模式（${concModeLabel}） · ${readyCount} 席全部就绪`
          : `${readyCount} 席本地 CLI 引擎已就绪 · 支持弹性研讨与交付`;
    } else {
      summaryBar.classList.add("warn-ready");
      summaryBar.textContent = "未检测到可用本地 CLI · 请在左下角设置中指定路径";
    }
  }

  // 渲染侧栏折叠区 CLI 引擎卡片与设置弹窗状态胶囊
  const cardsBox = el("cliEngineCards");
  if (cardsBox) {
    cardsBox.innerHTML = "";
    for (const aid of AGENT_ORDER) {
      const info = agents[aid] || {};
      const ready = Boolean(info.binary_detected);
      const pingRes = state.cliTestResults[aid];
      const latMs = state.pingLatencyBySeat[aid];
      const isExpanded = state.expandedCliCard === aid;

      let pillCls = ready ? "driver-pill live" : "driver-pill missing";
      let pillTxt = ready ? (info.shared_fallback ? "串行复用" : "已就绪") : "未安装";
      if (latMs > 0 && pingRes?.ok) {
        pillCls =
          latMs < 2800
            ? "driver-pill latency-fast"
            : latMs < 7500
            ? "driver-pill latency-normal"
            : "driver-pill latency-slow";
        pillTxt = `${(latMs / 1000).toFixed(1)}s`;
      }

      const card = document.createElement("div");
      card.className = `cli-card${isExpanded ? " expanded" : ""}`;
      const drvText = `${DRIVER_LABELS[info.effective_driver] || info.effective_driver || "CLI"} · ${
        info.effective_model || "默认模型"
      }${info.effective_discussion_effort ? ` (${info.effective_discussion_effort})` : ""}`;

      card.innerHTML =
        `<div class="cli-card-top">` +
          `<div class="cli-name-wrap">` +
            `<span class="cli-role-dot dot-${aid}"></span>` +
            `<span class="cli-card-name">${escapeHtml(AGENT_NAMES[aid])}</span>` +
          `</div>` +
          `<span class="${pillCls}">${escapeHtml(pillTxt)}</span>` +
        `</div>` +
        `<div class="cli-card-cli">${escapeHtml(drvText)}</div>` +
        (pingRes
          ? `<div class="cli-test-note${pingRes.ok ? "" : " err"}">${escapeHtml(
              pingRes.ok ? `连通正常 · ${pingRes.reply || "OK"}` : pingRes.error || "探活失败"
            )}</div>`
          : "") +
        `<div class="cli-card-details">路径：${escapeHtml(info.binary_path || "未探测到可执行文件")}<br/>版本：${escapeHtml(
          info.version || "未知"
        )}</div>`;

      card.onclick = () => {
        state.expandedCliCard = state.expandedCliCard === aid ? null : aid;
        renderSystemStatus(state.system);
      };
      cardsBox.appendChild(card);

      // 同步设置弹窗头部状态胶丸
      const cap = aid.charAt(0).toUpperCase() + aid.slice(1);
      const modalPill = el(`cfgStatus${cap}`);
      if (modalPill) {
        modalPill.className = pillCls;
        modalPill.textContent = pillTxt;
      }
    }
  }

  renderWorkspaceBadges();
  renderAllSeats();
}

async function pickWorkspaceFolder() {
  const sessionId = state.currentSessionId;
  try {
    const native = window.webkit?.messageHandlers?.roundtableNative;
    const path = native ? await native.postMessage({ action: "pickFolder" }) : "";
    if (native && !path) return;
    const res = await apiFetch("/api/system/pick-folder", {
      method: "POST",
      body: JSON.stringify({ active_session_id: sessionId || "", direct_path: path }),
    });
    if (res.cancelled || sessionId !== state.currentSessionId) return;
    if (res.ok && res.path) {
      state.sessionWorkspaceDir = res.path;
      state.workspaceBound = res.system?.workspace_bound ?? true;
      if (res.system) renderSystemStatus(res.system);
      if (el("cfgWorkspaceDir")) el("cfgWorkspaceDir").value = res.path;
      state.attachedFilesCache.clear();
      refreshAttachedFilesBar();
      renderStageAndHeader();
      showToast(`已绑定工作区：${res.path}`, "ok", 2200);
    }
  } catch (err) {
    showToast(err.message || "选择目录失败", "err");
  }
}

/* ==================== @源码检索补全菜单与已附加文件栏 ==================== */

function insertMentionIntoComposer(mentionText) {
  const inp = el("topicInput");
  if (!inp) return;
  const cleanToken = String(mentionText || "").trim();
  if (!cleanToken) return;

  // 若是「+ @引用源码」按钮插入单个 "@" 触发补全，则在光标处插入且不追加尾随空格
  if (cleanToken === "@") {
    const start = inp.selectionStart ?? inp.value.length;
    const end = inp.selectionEnd ?? inp.value.length;
    const before = inp.value.slice(0, start);
    const after = inp.value.slice(end);
    const needSpace = before.length > 0 && !/\s$/.test(before) ? " " : "";
    const inserted = `${needSpace}@`;
    inp.value = before + inserted + after;
    const caret = before.length + inserted.length;
    inp.focus();
    inp.setSelectionRange(caret, caret);
    autoGrowComposer();
    refreshAttachedFilesBar();
    syncMentionChipActiveStates();
    return;
  }

  // 定向点名幂等切换：已存在则移除，避免重复堆叠 @架构师 @架构师 或 @Carbon @Grok
  const curVal = inp.value || "";
  const escaped = escapeRegExp(cleanToken);
  const tokenRe = new RegExp(`(^|\\s)${escaped}(?=\\s|$)`, "i");
  if (tokenRe.test(curVal)) {
    inp.value = curVal.replace(tokenRe, " ").replace(/^\s+/, "").replace(/\s{2,}/g, " ");
  } else {
    const prefix = curVal && !curVal.endsWith(" ") && !curVal.endsWith("\n") ? " " : "";
    inp.value = `${curVal}${prefix}${cleanToken} `;
  }
  const endCaret = inp.value.length;
  inp.focus();
  inp.setSelectionRange(endCaret, endCaret);
  autoGrowComposer();
  refreshAttachedFilesBar();
  syncMentionChipActiveStates();
}

function autoGrowComposer() {
  const inp = el("topicInput");
  if (!inp) return;
  inp.style.height = "auto";
  const nextH = Math.min(160, Math.max(24, inp.scrollHeight));
  inp.style.height = `${nextH}px`;
  inp.style.overflowY = inp.scrollHeight > 160 ? "auto" : "hidden";
}

function closeAtSuggestMenu() {
  clearTimeout(state.atMenu.fetchTimer);
  state.atMenu.fetchTimer = null;
  state.atMenu.open = false;
  state.atMenu.items = [];
  el("atSuggestMenu")?.classList.add("hidden");
}

function findActiveAtToken(text, caretPos) {
  const left = text.slice(0, caretPos);
  const match = left.match(/(?:^|\s)@([A-Za-z0-9_\u4e00-\u9fa5./:-]*)$/);
  if (!match) return null;
  const query = match[1] || "";
  const atIdx = left.lastIndexOf("@" + query);
  if (atIdx < 0) return null;
  return { start: atIdx, end: caretPos, query };
}

async function openOrUpdateAtSuggestMenu(query, tokenStart, tokenEnd) {
  const menu = el("atSuggestMenu");
  if (!menu) return;
  const rawFileQuery = query.split(":")[0];
  const lineRange = query.slice(rawFileQuery.length);
  const sessionId = state.currentSessionId;

  const seatCandidates = AGENT_ORDER.filter((aid) => state.enabledAgents.includes(aid))
    .map((aid) => ({
      kind: "seat",
      insert: `@${AGENT_NAMES[aid]} `,
      label: `@${AGENT_NAMES[aid]}`,
      meta: `${getPersonaSpec(state.seatPersonas[aid], aid).label} · 定向点名`,
    }))
    .filter((item) => !rawFileQuery || item.label.toLowerCase().includes(rawFileQuery.toLowerCase()));

  let fileItems = [];
  if (effectiveWorkspacePath()) {
    try {
      const qs = new URLSearchParams({
        session_id: state.currentSessionId || "",
        q: rawFileQuery,
        limit: "24",
      });
      const res = await apiFetch(`/api/workspace/files?${qs.toString()}`);
      fileItems = (res.files || []).map((f) => ({
        kind: "file",
        insert: `@${f.path}${lineRange} `,
        path: f.path,
        label: `@${f.path}`,
        meta: `${f.lines ? f.lines + " 行 · " : ""}${f.size_kb ?? "?"} KB · 支持 :起始-结束行`,
      }));
      (res.files || []).forEach((f) => state.attachedFilesCache.set(f.path, true));
    } catch {
      fileItems = [];
    }
  }

  const input = el("topicInput");
  const token = input && findActiveAtToken(input.value, input.selectionStart);
  if (sessionId !== state.currentSessionId || document.activeElement !== input ||
      !token || token.start !== tokenStart || token.end !== tokenEnd || token.query !== query) return;
  const combined = [...seatCandidates, ...fileItems].slice(0, 20);
  if (!combined.length) {
    if (!effectiveWorkspacePath()) {
      menu.innerHTML = `<div class="at-menu-head"><span>尚未绑定本地项目工作区</span><span>点击顶栏「选择本地项目」即可检索源码</span></div>`;
      menu.classList.remove("hidden");
      state.atMenu = { ...state.atMenu, open: true, items: [], activeIndex: 0, tokenStart, tokenEnd, query };
      return;
    }
    closeAtSuggestMenu();
    return;
  }

  state.atMenu.open = true;
  state.atMenu.items = combined;
  state.atMenu.activeIndex = 0;
  state.atMenu.tokenStart = tokenStart;
  state.atMenu.tokenEnd = tokenEnd;
  state.atMenu.query = query;

  renderAtSuggestMenuDOM();
}

function renderAtSuggestMenuDOM() {
  const menu = el("atSuggestMenu");
  if (!menu || !state.atMenu.open) return;
  const items = state.atMenu.items;
  const wsHint = effectiveWorkspacePath() ? "↑↓ 选择 · Enter 插入 · 支持 :行号区间" : "席位点名";

  menu.innerHTML =
    `<div class="at-menu-head"><span>引用源码或定向点名</span><span>${escapeHtml(wsHint)}</span></div>` +
    items
      .map(
        (it, idx) =>
          `<div class="at-menu-item${idx === state.atMenu.activeIndex ? " active" : ""}" data-at-idx="${idx}">` +
            `<span class="at-file-path">${escapeHtml(it.label)}</span>` +
            `<span class="at-file-meta">${escapeHtml(it.meta)}</span>` +
          `</div>`
      )
      .join("");
  menu.classList.remove("hidden");

  menu.querySelectorAll("[data-at-idx]").forEach((row) => {
    row.onmousedown = (e) => {
      e.preventDefault();
      applyAtSuggestSelection(Number(row.dataset.atIdx));
    };
  });
}

function applyAtSuggestSelection(index) {
  const item = state.atMenu.items[index];
  const inp = el("topicInput");
  if (!item || !inp) {
    closeAtSuggestMenu();
    return;
  }
  const before = inp.value.slice(0, state.atMenu.tokenStart);
  const after = inp.value.slice(state.atMenu.tokenEnd);
  inp.value = before + item.insert + after;
  const pos = before.length + item.insert.length;
  inp.focus();
  inp.setSelectionRange(pos, pos);
  closeAtSuggestMenu();
  autoGrowComposer();
  refreshAttachedFilesBar();
  syncMentionChipActiveStates();
}

function refreshAttachedFilesBar() {
  const bar = el("attachedFilesBar");
  const inp = el("topicInput");
  if (!bar || !inp) return;

  const text = inp.value || "";
  const matches = [];
  const seen = new Set();
  AT_TOKEN_GLOBAL_RE.lastIndex = 0;
  let m;
  while ((m = AT_TOKEN_GLOBAL_RE.exec(text)) !== null) {
    const fullToken = m[0];
    if (!seen.has(fullToken)) {
      seen.add(fullToken);
      matches.push({
        raw: fullToken,
        path: m[1],
        range: m[2] ? (m[3] ? `${m[2]}-${m[3]}` : `${m[2]}`) : "",
      });
    }
  }

  if (!matches.length) {
    bar.classList.add("hidden");
    bar.innerHTML = "";
    return;
  }

  const hasWs = Boolean(effectiveWorkspacePath());
  bar.classList.remove("hidden");
  bar.innerHTML =
    `<span class="attached-bar-label">已注入源码引用：</span>` +
    matches
      .map((item) => {
        const cls = hasWs ? "file-chip-valid" : "file-chip-warn";
        const statusText = hasWs ? (item.range ? `L${item.range}` : "全文/索引") : "需先绑定项目";
        return (
          `<span class="attached-file-chip ${cls}" data-raw-token="${escapeHtml(item.raw)}">` +
            `<span class="chip-file-name">${escapeHtml(item.path)}</span>` +
            `<em class="chip-file-status">${escapeHtml(statusText)}</em>` +
            `<button type="button" class="chip-file-remove" title="移除引用">✕</button>` +
          `</span>`
        );
      })
      .join("");

  bar.querySelectorAll(".attached-file-chip").forEach((chip) => {
    const rawTok = chip.dataset.rawToken;
    chip.querySelector(".chip-file-remove")?.addEventListener("click", (e) => {
      e.stopPropagation();
      inp.value = inp.value.replace(rawTok, "").replace(/\s{2,}/g, " ").trimStart();
      autoGrowComposer();
      refreshAttachedFilesBar();
    });
    if (!hasWs) {
      chip.onclick = () => pickWorkspaceFolder();
    }
  });
}

/* ==================== 会话生命周期、发起研讨、控场与 SSE 实时流 ==================== */

function renderSessionList() {
  const listEl = el("sessionList");
  const countTag = el("sessionCountTag");
  const railCount = el("railSessionCount");
  if (!listEl) return;

  const total = state.sessions.length;
  if (countTag) countTag.textContent = String(total);
  if (railCount) railCount.textContent = String(total);

  const q = state.sessionSearchQuery.trim().toLowerCase();
  const filtered = q
    ? state.sessions.filter(
        (s) =>
          String(s.title || "").toLowerCase().includes(q) ||
          String(s.topic || "").toLowerCase().includes(q)
      )
    : state.sessions;

  listEl.innerHTML = "";
  for (const s of filtered) {
    const div = document.createElement("div");
    div.className = `session-item${s.session_id === state.currentSessionId ? " active" : ""}`;
    const normMode = normalizeCollabModeAndAutoExec(s.collab_mode, s.auto_preview_exec).mode;
    const modeLabel = COLLAB_MODES[normMode]?.label || "深度研讨";

    div.innerHTML =
      `<div class="session-item-top">` +
        `<span class="session-item-title">${escapeHtml(s.title || "新圆桌会议")}</span>` +
        (s.is_busy ? `<span class="session-busy-dot" title="研讨运行中"></span>` : "") +
        `<button type="button" class="session-del-btn" title="删除会话">✕</button>` +
      `</div>` +
      `<div class="session-item-meta">` +
        `<span>${escapeHtml(modeLabel)} · ${s.message_count || 0} 条发言</span>` +
        `<span>${escapeHtml(s.created_at || "")}</span>` +
      `</div>`;

    div.onclick = () => {
      if (s.session_id !== state.currentSessionId) {
        switchToSession(s.session_id);
      }
    };
    div.querySelector(".session-del-btn")?.addEventListener("click", async (e) => {
      e.stopPropagation();
      await deleteSessionById(s.session_id);
    });
    listEl.appendChild(div);
  }
}

async function refreshSessionsListOnly() {
  try {
    const res = await apiFetch("/api/sessions");
    state.sessions = res.sessions || [];
    renderSessionList();
  } catch {
    // 静默忽略非关键列表刷新异常
  }
}

function applySessionSnapshot(snap) {
  if (!snap) return;
  state.currentSessionId = snap.session_id;
  state.stage = snap.stage || "idle";
  state.isBusy = Boolean(snap.is_busy);
  state.topic = snap.topic || "";
  state.sessionWorkspaceDir = snap.workspace_dir || "";
  state.workspaceBound = snap.workspace_bound ?? null;
  state.workspaceIsGit = Boolean(snap.workspace_is_git);

  const norm = normalizeCollabModeAndAutoExec(snap.collab_mode, snap.auto_preview_exec);
  state.collabMode = norm.mode;
  state.autoPreviewExec = norm.autoPreviewExec;

  state.enabledAgents = Array.isArray(snap.enabled_agents) && snap.enabled_agents.length
    ? snap.enabled_agents
    : ["carbon", "grok", "astra"];
  state.seatPersonas = { ...DEFAULT_SEAT_PERSONAS, ...(snap.seat_personas || {}) };
  state.seatEfforts = { ...(snap.seat_efforts || {}) };
  state.executorAgent = snap.executor_agent || "astra";
  state.seatStates = snap.seat_states || {};
  state.execStartTs = state.stage === "executing" ? Date.now() : 0;

  syncCollabModeUI(state.collabMode, state.autoPreviewExec);
  clearChatMessages();
  const msgs = Array.isArray(snap.messages) ? snap.messages : [];
  for (const m of msgs) {
    createOrUpdateMessageCard(m, { skipEnterAnim: true });
  }
  updateEmptyGuideVisibility();
  renderAllSeats();
  renderWhiteboard(snap.whiteboard || {}, true, true);
  renderStageAndHeader();
  scrollToBottom(false);
}

function connectSessionStream(sessionId) {
  if (state.sse) {
    state.sse.close();
    state.sse = null;
  }
  if (state.sseReconnectTimer) {
    clearTimeout(state.sseReconnectTimer);
    state.sseReconnectTimer = null;
  }
  if (!sessionId) return;

  const es = new EventSource(`/api/sessions/${sessionId}/stream`);
  state.sse = es;

  const setConnOnline = (online) => {
    const dot = el("sseConnDot");
    if (!dot) return;
    dot.classList.toggle("online", online);
    dot.textContent = online ? "" : "重连中";
    dot.title = online ? "本地实时服务已连接" : "SSE 实时连接中断，正在自动重连…";
  };

  es.onopen = () => setConnOnline(true);

  es.addEventListener("snapshot", (ev) => {
    setConnOnline(true);
    const snap = JSON.parse(ev.data);
    applySessionSnapshot(snap);
  });

  es.addEventListener("session_cleared", () => {
    clearChatMessages();
    updateEmptyGuideVisibility();
  });

  es.addEventListener("session_meta", (ev) => {
    const meta = JSON.parse(ev.data);
    const prevStage = state.stage;
    state.stage = meta.stage || state.stage;
    state.isBusy = Boolean(meta.is_busy);
    if (typeof meta.topic === "string") state.topic = meta.topic;
    if (typeof meta.workspace_dir === "string") state.sessionWorkspaceDir = meta.workspace_dir;
    if (typeof meta.workspace_bound === "boolean") state.workspaceBound = meta.workspace_bound;
    if (typeof meta.workspace_is_git === "boolean") state.workspaceIsGit = meta.workspace_is_git;
    if (Array.isArray(meta.enabled_agents)) state.enabledAgents = meta.enabled_agents;
    if (meta.seat_personas) state.seatPersonas = { ...state.seatPersonas, ...meta.seat_personas };
    if (meta.seat_efforts) state.seatEfforts = { ...meta.seat_efforts };
    if (meta.executor_agent) state.executorAgent = meta.executor_agent;

    if (meta.collab_mode || typeof meta.auto_preview_exec === "boolean") {
      syncCollabModeUI(meta.collab_mode || state.collabMode, meta.auto_preview_exec);
    }
    if (meta.consensus_status && el("wbConsensusTag")) {
      el("wbConsensusTag").textContent = meta.consensus_status;
    }

    if (state.stage === "executing" && prevStage !== "executing") {
      state.execStartTs = Date.now();
      if (state.activeTab !== "terminal") {
        el("execDot")?.classList.remove("hidden");
      }
    } else if (state.stage !== "executing") {
      state.execStartTs = 0;
    }

    updateEmptyGuideVisibility();
    renderAllSeats();
    renderStageAndHeader();
    refreshSessionsListOnly();
  });

  es.addEventListener("seat_update", (ev) => {
    const st = JSON.parse(ev.data);
    if (st?.agent_id) {
      state.seatStates[st.agent_id] = st;
      renderSeatCard(st.agent_id);
    }
  });

  es.addEventListener("msg_start", (ev) => {
    const msg = JSON.parse(ev.data);
    createOrUpdateMessageCard(msg, { skipEnterAnim: false });
  });

  es.addEventListener("msg_status", (ev) => {
    updateMessageStreamingStatus(JSON.parse(ev.data));
  });

  es.addEventListener("msg_activity", (ev) => {
    updateMessageStreamingStatus(JSON.parse(ev.data));
  });

  es.addEventListener("msg_delta", (ev) => {
    const pkt = JSON.parse(ev.data);
    appendMessageDelta(pkt.id, pkt.delta);
  });

  es.addEventListener("msg_done", (ev) => {
    const msg = JSON.parse(ev.data);
    createOrUpdateMessageCard(msg, { skipEnterAnim: true });
    refreshSessionsListOnly();
  });

  es.addEventListener("whiteboard_update", (ev) => {
    const wb = JSON.parse(ev.data);
    renderWhiteboard(wb, false, false);
  });

  es.addEventListener("term_log", (ev) => {
    const pkt = JSON.parse(ev.data);
    const term = el("astraTermLogs");
    if (term && pkt?.line) {
      if (term.textContent === "尚未触发执行任务") term.textContent = "";
      term.textContent += (term.textContent ? "\n" : "") + pkt.line;
      term.scrollTop = term.scrollHeight;
    }
  });

  es.addEventListener("exec_delta", (ev) => {
    const pkt = JSON.parse(ev.data);
    const term = el("astraTermLogs");
    if (term && pkt?.delta) {
      if (term.textContent === "尚未触发执行任务") term.textContent = "";
      term.textContent += pkt.delta;
      term.scrollTop = term.scrollHeight;
    }
  });

  es.addEventListener("exec_artifact", (ev) => {
    const art = JSON.parse(ev.data);
    if (el("astraDiffView")) {
      el("astraDiffView").innerHTML = renderDiffHtml(art.diff || "");
    }
    if (state.activeTab !== "terminal") {
      el("execDot")?.classList.remove("hidden");
    }
  });

  es.onerror = () => {
    setConnOnline(false);
    es.close();
    if (state.sse === es) {
      state.sse = null;
      state.sseReconnectTimer = setTimeout(() => {
        if (state.currentSessionId === sessionId) {
          connectSessionStream(sessionId);
        }
      }, 1800);
    }
  };
}

async function switchToSession(sessionId) {
  closePersonaPopover();
  closeAtSuggestMenu();
  state.currentSessionId = sessionId;
  renderSessionList();
  connectSessionStream(sessionId);
}

async function createNewSession() {
  if (!state.topic && !state.whiteboard?.items?.length && state.messages.size === 0 && !state.isBusy && state.currentSessionId) {
    el("topicInput")?.focus();
    showToast("当前已是空白新会议，可直接输入议题开启研讨", "info", 2000);
    return;
  }
  try {
    const res = await apiFetch("/api/sessions", {
      method: "POST",
      body: JSON.stringify({
        title: "新会议",
        collab_mode: state.collabMode || "deep_deliberation",
        auto_preview_exec: state.autoPreviewExec,
      }),
    });
    if (Array.isArray(res.sessions)) {
      state.sessions = res.sessions;
      renderSessionList();
    }
    if (res.session?.session_id) {
      applySessionSnapshot(res.session);
      connectSessionStream(res.session.session_id);
    }
    el("topicInput")?.focus();
  } catch (err) {
    showToast(err.message || "新建圆桌会议失败", "err");
  }
}

async function deleteSessionById(sessionId) {
  try {
    const res = await apiFetch(`/api/sessions/${sessionId}`, { method: "DELETE" });
    state.sessions = res.sessions || [];
    renderSessionList();
    if (state.currentSessionId === sessionId && res.active_session_id) {
      await switchToSession(res.active_session_id);
    }
    showToast("已删除历史会话", "info", 1800);
  } catch (err) {
    showToast(err.message || "删除会话失败", "err");
  }
}

async function startOrInterruptWithText(overrideText = "") {
  const inp = el("topicInput");
  const draft = inp?.value || "";
  const inMeeting = state.messages.size > 0 || state.isBusy;
  const text = (overrideText || draft.trim() || (!inMeeting && state.topic) || "").trim();
  if (!text) {
    inp?.focus();
    return;
  }
  const sessionId = state.currentSessionId;
  if (!sessionId || state.sendingSessions.has(sessionId)) return;
  state.sendingSessions.add(sessionId);
  closeAtSuggestMenu();

  try {
    if (!inMeeting) {
      await apiFetch(`/api/sessions/${sessionId}/start`, {
        method: "POST",
        body: JSON.stringify({
          topic: text,
          collab_mode: state.collabMode,
          auto_preview_exec: state.autoPreviewExec,
          enabled_agents: state.enabledAgents,
          seat_personas: state.seatPersonas,
          seat_efforts: state.seatEfforts,
          executor_agent: state.executorAgent,
        }),
      });
    } else {
      const endpoint = state.isBusy ? "interrupt" : "followup";
      await apiFetch(`/api/sessions/${sessionId}/${endpoint}`, {
        method: "POST",
        body: JSON.stringify({ message: text }),
      });
    }
    if (sessionId === state.currentSessionId) {
      if (!overrideText && inp?.value === draft) {
        inp.value = "";
        autoGrowComposer();
        refreshAttachedFilesBar();
        syncMentionChipActiveStates();
      }
      scrollToBottom(true);
    }
  } catch (err) {
    showToast(err.message || "发送指令失败", "err");
  } finally {
    state.sendingSessions.delete(sessionId);
  }
}

async function triggerExecutionNow() {
  if (!state.currentSessionId) return;
  if (!state.topic && !state.whiteboard?.items?.some(it => it.kind === "action" && it.checked !== false) && state.messages.size === 0) {
    showToast("请先输入议题完成研讨或添加白板任务", "warn", 2200);
    return;
  }
  const allowWrite = Boolean(effectiveWorkspacePath() && el("allowWriteCheckbox")?.checked);
  const execAid = state.executorAgent || "astra";
  setRightCollapsed(false);
  switchWorkbenchTab("terminal");
  if (el("astraTermLogs")) {
    el("astraTermLogs").textContent = `正在启动 ${AGENT_NAMES[execAid]} 执行流水线…`;
  }
  try {
    await apiFetch(`/api/sessions/${state.currentSessionId}/execute`, {
      method: "POST",
      body: JSON.stringify({
        allow_workspace_write: allowWrite,
        executor_id: execAid,
      }),
    });
  } catch (err) {
    showToast(err.message || "触发执行失败", "err");
  }
}

/* ==================== 渐进披露式「系统与模型设置弹窗」与单引擎串行模式 ==================== */

function openSettingsModal() {
  const modal = el("settingsModal");
  if (!modal) return;
  const sys = state.system || {};
  const agents = sys.agents || {};

  if (el("cfgWorkspaceDir")) {
    el("cfgWorkspaceDir").value = effectiveWorkspacePath();
  }
  if (el("cfgSingleCliFallback")) {
    el("cfgSingleCliFallback").checked = sys.allow_single_cli_fallback !== false;
  }
  if (el("cfgSingleCliConcurrency")) {
    el("cfgSingleCliConcurrency").value = String(sys.single_cli_concurrency || state.singleCliConcurrency || 3);
  }
  if (el("cfgRosterPresetSelect")) {
    const curRp = sys.roster_preset || state.rosterPreset || "role_experts";
    el("cfgRosterPresetSelect").value = curRp;
    const preset = ROSTER_NAME_PRESETS[curRp];
    if (preset && preset.names) {
      for (const [aid, cap] of [
        ["carbon", "Carbon"],
        ["grok", "Grok"],
        ["astra", "Astra"],
      ]) {
        const inp = el(`cfg${cap}Name`);
        if (inp && preset.names[aid]) {
          inp.placeholder = `留空默认：${preset.names[aid]}`;
        }
      }
    }
  }

  syncPacingControlsInModal(
    sys.pacing_mode || state.pacingMode || "unrestricted",
    sys.idle_timeout_sec ?? state.idleTimeoutSec ?? 900,
    sys.turn_timeout_sec ?? state.turnTimeoutSec ?? 0,
    sys.max_ref_chars ?? state.maxRefChars ?? 120000
  );

  for (const [aid, cap] of [
    ["carbon", "Carbon"],
    ["grok", "Grok"],
    ["astra", "Astra"],
  ]) {
    const info = agents[aid] || {};
    const drvSel = el(`cfg${cap}Driver`);
    const personaSel = el(`cfg${cap}Persona`);
    const modelInp = el(`cfg${cap}Model`);
    const nameInp = el(`cfg${cap}Name`);
    const binInp = el(`cfg${cap}Bin`);
    const statusPill = el(`cfgStatus${cap}`);

    if (drvSel) drvSel.value = info.driver || "auto";
    if (personaSel) personaSel.value = state.seatPersonas[aid] || info.persona || DEFAULT_SEAT_PERSONAS[aid];
    if (modelInp) modelInp.value = info.model || info.effective_model || "";
    if (nameInp) nameInp.value = info.custom_name || "";
    if (binInp) binInp.value = info.custom_binary || "";

    refreshSeatEffortSelectInModal(cap, false);

    const discSel = el(`cfg${cap}Effort`);
    const execSel = el(`cfg${cap}ExecEffort`);
    const spec = getEffortSpecForModel(drvSel?.value || "auto", modelInp?.value || "", aid);
    const prefDisc = state.seatEfforts[aid] || info.discussion_effort || info.effective_discussion_effort || spec.default;
    const prefExec = info.execution_effort || info.effective_execution_effort || spec.default;
    populateEffortSelectElement(discSel, spec.allowed, prefDisc, spec.supports_effort);
    const execAllowed = (spec.allowed || []).filter((x) => x !== "low");
    populateEffortSelectElement(execSel, execAllowed.length ? execAllowed : spec.allowed, prefExec, spec.supports_effort);

    if (statusPill) {
      const latency = state.pingLatencyBySeat?.[aid];
      if (info.binary_detected) {
        if (latency > 0) {
          statusPill.textContent = `已就绪 · ${latency}ms`;
          statusPill.className = `driver-pill ${latency < 2800 ? "latency-fast" : latency < 7500 ? "latency-normal" : "latency-slow"}`;
        } else {
          statusPill.textContent = info.shared_cli_group ? "单引擎多角色" : "已就绪";
          statusPill.className = "driver-pill live";
        }
      } else {
        statusPill.textContent = "未安装";
        statusPill.className = "driver-pill missing";
      }
    }
  }

  syncDynamicRosterNames();
  modal.classList.remove("hidden");
}

function closeSettingsModal() {
  el("settingsModal")?.classList.add("hidden");
}

function collectDraftAgentConfigsFromModal() {
  const out = {};
  for (const [aid, cap] of [
    ["carbon", "Carbon"],
    ["grok", "Grok"],
    ["astra", "Astra"],
  ]) {
    const discSel = el(`cfg${cap}Effort`);
    const execSel = el(`cfg${cap}ExecEffort`);
    out[aid] = {
      driver: el(`cfg${cap}Driver`)?.value || "auto",
      persona: el(`cfg${cap}Persona`)?.value || DEFAULT_SEAT_PERSONAS[aid],
      custom_name: (el(`cfg${cap}Name`)?.value || "").trim(),
      model: (el(`cfg${cap}Model`)?.value || "").trim(),
      discussion_effort: discSel?.disabled ? "" : discSel?.value || "",
      execution_effort: execSel?.disabled ? "" : execSel?.value || "",
      custom_binary: (el(`cfg${cap}Bin`)?.value || "").trim(),
    };
  }
  return out;
}

function applyQuickSingleCliTriad() {
  const triadSel = el("singleCliTriadDriver");
  let chosenDrv = triadSel?.value || "auto";
  if (chosenDrv === "auto") {
    const agents = state.system?.agents || {};
    chosenDrv =
      ["agy", "codex", "grok"].find((d) =>
        Object.values(agents).some((info) => info?.binary_detected && info?.effective_driver === d)
      ) || "agy";
  }

  const dSpec = DRIVER_DEFAULTS[chosenDrv] || DRIVER_DEFAULTS.agy;
  const triadPersonas = { carbon: "planner", grok: "red_team", astra: "implementer" };
  const singleFb = el("cfgSingleCliFallback");
  if (singleFb) singleFb.checked = true;
  const concSel = el("cfgSingleCliConcurrency");
  if (concSel && !concSel.value) {
    concSel.value = String(state.singleCliConcurrency || 3);
  }
  state.singleCliConcurrency = Number(concSel?.value || state.singleCliConcurrency || 3);

  for (const [aid, cap] of [
    ["carbon", "Carbon"],
    ["grok", "Grok"],
    ["astra", "Astra"],
  ]) {
    const drvEl = el(`cfg${cap}Driver`);
    const perEl = el(`cfg${cap}Persona`);
    const modEl = el(`cfg${cap}Model`);
    const discEl = el(`cfg${cap}Effort`);
    const execEl = el(`cfg${cap}ExecEffort`);
    if (drvEl) drvEl.value = chosenDrv;
    if (perEl) perEl.value = triadPersonas[aid];
    if (modEl) modEl.value = dSpec.model;
    if (discEl) discEl.value = dSpec.discussEffort;
    if (execEl) execEl.value = dSpec.execEffort;
    refreshSeatEffortSelectInModal(cap, true);
    const spec = getEffortSpecForModel(chosenDrv, dSpec.model, aid);
    populateEffortSelectElement(discEl, spec.allowed, spec.default || dSpec.discussEffort, spec.supports_effort);
    const execAllowed = (spec.allowed || []).filter((x) => x !== "low");
    populateEffortSelectElement(
      execEl,
      execAllowed.length ? execAllowed : spec.allowed,
      spec.default || dSpec.execEffort,
      spec.supports_effort
    );
  }
  state.seatEfforts = {};
  const concNote = state.singleCliConcurrency > 1 ? `${state.singleCliConcurrency} 席并发` : "串行防限流";
  showToast(
    `已填入「${DRIVER_LABELS[chosenDrv] || chosenDrv}」单引擎三角色推荐配置（${concNote}），点击「保存配置」生效`,
    "ok",
    2800
  );
}

async function runCliTest(fromModal = false, targetAgentId = "") {
  const btn = el(fromModal ? "modalTestCliBtn" : "testCliBtn");
  const origTxt = btn?.textContent || "实测连通";
  if (btn) {
    btn.disabled = true;
    btn.textContent = "实测中…";
  }
  try {
    let overrideAgents = null;
    if (fromModal) {
      overrideAgents = collectDraftAgentConfigsFromModal();
    }
    const res = await apiFetch("/api/cli/test", {
      method: "POST",
      body: JSON.stringify({
        agents: overrideAgents,
        agent_id: targetAgentId || "",
      }),
    });
    const results = res.results || {};
    state.cliTestResults = { ...state.cliTestResults, ...results };
    let okCount = 0;
    let totalCount = 0;
    for (const [aid, r] of Object.entries(results)) {
      totalCount += 1;
      const ms = Number(r?.elapsed_ms ?? r?.latency_ms ?? 0);
      if (r?.ok) {
        okCount += 1;
        if (ms > 0) state.pingLatencyBySeat[aid] = ms;
      }
      const cap = aid.charAt(0).toUpperCase() + aid.slice(1);
      const pill = el(`cfgStatus${cap}`);
      if (pill && fromModal) {
        if (r?.ok) {
          pill.textContent = `连通 ${ms}ms`;
          pill.className = `driver-pill ${ms < 2500 ? "latency-fast" : ms < 6000 ? "latency-normal" : "latency-slow"}`;
        } else {
          pill.textContent = "未通过";
          pill.className = "driver-pill missing";
        }
      }
    }
    if (res.system) {
      renderSystemStatus(res.system);
    } else {
      renderAllSeats();
    }
    if (okCount === totalCount && totalCount > 0) {
      const summary = Object.entries(results)
        .map(([aid, r]) => `${AGENT_NAMES[aid] || aid} ${r.elapsed_ms ?? r.latency_ms ?? 0}ms`)
        .join(" / ");
      showToast(`连通实测全部通过：${summary}`, "ok", 3200);
    } else {
      const firstErr = Object.values(results).find((r) => !r?.ok)?.error || "部分席位未通过实测，请查看卡片诊断提示";
      showToast(firstErr, "warn", 4200);
    }
  } catch (err) {
    showToast(err.message || "连通性实测失败", "err");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = origTxt;
    }
  }
}

async function saveSettingsFromModal() {
  const btn = el("saveSettingsBtn");
  if (btn) btn.disabled = true;

  try {
    const activePacingBtn = document.querySelector("#cfgPacingGroup .pacing-seg-btn.active");
    const pacingMode = activePacingBtn?.dataset.pacingMode || state.pacingMode || "unrestricted";
    const preset = PACING_PRESETS[pacingMode];
    const idleSec = preset
      ? preset.idle_timeout_sec
      : Math.max(0, Number(el("cfgIdleTimeout")?.value ?? 900));
    const turnSec = preset
      ? preset.turn_timeout_sec
      : Math.max(0, Number(el("cfgTurnTimeout")?.value ?? 0));
    const maxRef = preset
      ? preset.max_ref_chars
      : Math.max(10000, Number(el("cfgMaxRefChars")?.value ?? 120000));

    const wsVal = (el("cfgWorkspaceDir")?.value || "").trim();
    const singleFallback = Boolean(el("cfgSingleCliFallback")?.checked);
    const singleConc = Number(el("cfgSingleCliConcurrency")?.value || 3);
    const rosterPreset = el("cfgRosterPresetSelect")?.value || "role_experts";

    const draftAgents = collectDraftAgentConfigsFromModal();
    for (const aid of AGENT_ORDER) {
      if (!draftAgents[aid].execution_effort && draftAgents[aid].discussion_effort) {
        draftAgents[aid].execution_effort = draftAgents[aid].discussion_effort;
      }
    }

    const res = await apiFetch("/api/config", {
      method: "POST",
      body: JSON.stringify({
        active_session_id: state.currentSessionId || "",
        workspace_dir: wsVal,
        allow_single_cli_fallback: singleFallback,
        roster_preset: rosterPreset,
        single_cli_concurrency: singleConc,
        pacing_mode: pacingMode,
        idle_timeout_sec: idleSec,
        turn_timeout_sec: turnSec,
        max_ref_chars: maxRef,
        agents: draftAgents,
      }),
    });

    const nextPersonas = {
      carbon: draftAgents.carbon.persona,
      grok: draftAgents.grok.persona,
      astra: draftAgents.astra.persona,
    };
    const resetSeatEfforts = { carbon: "", grok: "", astra: "" };

    state.seatPersonas = { ...state.seatPersonas, ...nextPersonas };
    state.seatEfforts = {};
    state.rosterPreset = res.system?.roster_preset || rosterPreset;
    state.singleCliConcurrency = res.system?.single_cli_concurrency || singleConc;
    if (wsVal) {
      state.sessionWorkspaceDir = wsVal;
      state.workspaceBound = res.system?.workspace_bound ?? null;
    }

    if (res.system) {
      renderSystemStatus(res.system);
    } else {
      syncDynamicRosterNames();
      renderAllSeats();
    }

    if (state.currentSessionId) {
      await persistSessionSeatsPatch({
        seat_personas: nextPersonas,
        seat_efforts: resetSeatEfforts,
      });
    }

    renderStageAndHeader();
    if (state.whiteboard) renderWhiteboard(state.whiteboard, true, false);
    closeSettingsModal();
    showToast("系统运行策略、成员称呼与模型配置已保存", "ok", 2200);
  } catch (err) {
    showToast(err.message || "保存系统配置失败", "err", 3800);
  } finally {
    if (btn) btn.disabled = false;
  }
}

/* ==================== 全局事件绑定与启动初始化 ==================== */

function bindEvents() {
  // 左侧紧凑图标轨与展开侧栏切换
  el("brandToggleRailBtn")?.addEventListener("click", () => {
    const isCollapsed = el("appShell")?.classList.contains("left-collapsed");
    setLeftCollapsed(!isCollapsed);
  });
  el("collapseLeftBtn")?.addEventListener("click", (e) => {
    e.stopPropagation();
    setLeftCollapsed(true);
  });
  el("expandLeftBtn")?.addEventListener("click", () => setLeftCollapsed(false));
  el("railSessionsBtn")?.addEventListener("click", () => {
    setLeftCollapsed(false);
    el("sessionSearchInput")?.focus();
  });
  el("railNewSessionBtn")?.addEventListener("click", () => createNewSession());
  el("newSessionBtn")?.addEventListener("click", () => createNewSession());
  el("railPickFolderBtn")?.addEventListener("click", () => pickWorkspaceFolder());
  el("pickFolderQuickBtn")?.addEventListener("click", () => pickWorkspaceFolder());
  el("headerWsChip")?.addEventListener("click", () => pickWorkspaceFolder());
  el("emptyBindWsBtn")?.addEventListener("click", () => pickWorkspaceFolder());

  // 历史会话搜索
  el("sessionSearchInput")?.addEventListener("input", (e) => {
    state.sessionSearchQuery = e.target.value || "";
    renderSessionList();
  });

  // 右侧白板/执行终端面板显隐与页签滑块切换
  el("toggleRightBtn")?.addEventListener("click", () => {
    const isHidden = el("appShell")?.classList.contains("right-collapsed");
    setRightCollapsed(!isHidden);
  });
  document.querySelectorAll(".wb-tab[data-tab]").forEach((btn) => {
    btn.addEventListener("click", () => switchWorkbenchTab(btn.dataset.tab));
  });

  // 外观浮层（主题 / 色系 / 字号）
  el("appearanceBtn")?.addEventListener("click", (e) => {
    e.stopPropagation();
    closePersonaPopover();
    toggleAppearanceMenu();
  });
  document.querySelectorAll("[data-theme-opt]").forEach((btn) => {
    btn.addEventListener("click", () => applyTheme(btn.dataset.themeOpt));
  });
  document.querySelectorAll("[data-palette-opt]").forEach((btn) => {
    btn.addEventListener("click", () => applyPalette(btn.dataset.paletteOpt));
  });
  document.querySelectorAll("[data-font-opt]").forEach((btn) => {
    btn.addEventListener("click", () => applyFontSize(btn.dataset.fontOpt));
  });

  // 次顶栏席位胶囊：点击 [职责标签 ▾] 弹出配置浮层；点击胶囊主体插入 @点名
  document.querySelectorAll("[data-persona-trigger]").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      toggleAppearanceMenu(false);
      openPersonaPopover(btn.dataset.personaTrigger, btn);
    });
  });
  document.querySelectorAll(".seat-card[data-agent-seat]").forEach((card) => {
    card.addEventListener("click", (e) => {
      if (e.target.closest("[data-persona-trigger]")) return;
      const aid = card.dataset.agentSeat;
      if (aid && AGENT_NAMES[aid]) {
        insertMentionIntoComposer(`@${AGENT_NAMES[aid]} `);
      }
    });
  });

  // 讨论策略选择与自动执行预演开关
  el("collabModeSelect")?.addEventListener("change", async (e) => {
    syncCollabModeUI(e.target.value, state.autoPreviewExec);
    if (state.currentSessionId) {
      await persistSessionSeatsPatch({ collab_mode: state.collabMode });
    }
  });
  document.querySelectorAll("[data-collab-opt]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      syncCollabModeUI(btn.dataset.collabOpt, state.autoPreviewExec);
      if (state.currentSessionId) {
        await persistSessionSeatsPatch({ collab_mode: state.collabMode });
      }
    });
  });

  const toggleAutoPreview = async () => {
    const next = !state.autoPreviewExec;
    syncAutoPreviewUI(next);
    if (state.currentSessionId) {
      await persistSessionSeatsPatch({ auto_preview_exec: next });
    }
    showToast(
      next
        ? "已开启「自动执行预演」：讨论收敛后将自动生成决议并输出只读代码补丁预览"
        : "已关闭「自动执行预演」",
      "info",
      2200
    );
  };
  el("emptyAutoPreviewBtn")?.addEventListener("click", toggleAutoPreview);
  el("composerAutoPreviewBtn")?.addEventListener("click", toggleAutoPreview);

  // Launchpad 与侧栏 5 大场景预设联动
  document.querySelectorAll("[data-scenario-preset]").forEach((btn) => {
    btn.addEventListener("click", () => applyScenarioPreset(btn.dataset.scenarioPreset));
  });

  // Launchpad 工程开局议题模板
  document.querySelectorAll("[data-starter-topic]").forEach((card) => {
    card.addEventListener("click", () => {
      const inp = el("topicInput");
      if (!inp) return;
      inp.value = card.dataset.starterTopic || "";
      inp.focus();
      autoGrowComposer();
      refreshAttachedFilesBar();
    });
  });

  // 讨论流滚动监听与「↓ 查看最新发言」
  const stream = el("chatStream");
  stream?.addEventListener("scroll", () => {
    const dist = stream.scrollHeight - stream.scrollTop - stream.clientHeight;
    state.userScrolledUp = dist > 96;
    el("scrollBottomBtn")?.classList.toggle("hidden", !state.userScrolledUp);
  });
  el("scrollBottomBtn")?.addEventListener("click", () => scrollToBottom(true));

  // 输入框发送、快捷键与 @源码检索补全
  const topicInp = el("topicInput");
  topicInp?.addEventListener("input", () => {
    autoGrowComposer();
    refreshAttachedFilesBar();
    syncMentionChipActiveStates();
    const caret = topicInp.selectionStart ?? topicInp.value.length;
    const tok = findActiveAtToken(topicInp.value, caret);
    if (state.atMenu.fetchTimer) clearTimeout(state.atMenu.fetchTimer);
    if (!tok) {
      closeAtSuggestMenu();
      return;
    }
    state.atMenu.fetchTimer = setTimeout(() => {
      openOrUpdateAtSuggestMenu(tok.query, tok.start, tok.end);
    }, 90);
  });

  topicInp?.addEventListener("keydown", (e) => {
    if (e.isComposing || e.keyCode === 229) return;
    if (state.atMenu.open && state.atMenu.items.length > 0) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        state.atMenu.activeIndex = (state.atMenu.activeIndex + 1) % state.atMenu.items.length;
        renderAtSuggestMenuDOM();
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        state.atMenu.activeIndex =
          (state.atMenu.activeIndex - 1 + state.atMenu.items.length) % state.atMenu.items.length;
        renderAtSuggestMenuDOM();
        return;
      }
      if (e.key === "Enter" || e.key === "Tab") {
        e.preventDefault();
        applyAtSuggestSelection(state.atMenu.activeIndex);
        return;
      }
      if (e.key === "Escape") {
        e.preventDefault();
        closeAtSuggestMenu();
        return;
      }
    }
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      startOrInterruptWithText();
    }
  });

  el("primaryActionBtn")?.addEventListener("click", () => startOrInterruptWithText());
  el("insertFileRefBtn")?.addEventListener("click", async () => {
    if (!effectiveWorkspacePath()) {
      await pickWorkspaceFolder();
      if (!effectiveWorkspacePath()) return;
    }
    insertMentionIntoComposer("@");
    const inp = el("topicInput");
    if (inp) {
      const pos = inp.selectionStart ?? inp.value.length;
      const tok = findActiveAtToken(inp.value, pos);
      if (tok) openOrUpdateAtSuggestMenu(tok.query, tok.start, tok.end);
    }
  });

  document.querySelectorAll("#mentionChipsWrap [data-mention]").forEach((btn) => {
    btn.addEventListener("click", () => insertMentionIntoComposer(btn.dataset.mention));
  });

  // 底部控场栏：停止运行 / 重开本议题 / 形成决议 / 交由执行席位执行
  const stopFlowHandler = async () => {
    if (!state.currentSessionId) return;
    try {
      await apiFetch(`/api/sessions/${state.currentSessionId}/stop`, { method: "POST" });
      showToast("已中止当前运行任务", "info", 1800);
    } catch (err) {
      showToast(err.message || "停止失败", "err");
    }
  };
  el("stopFlowBtn")?.addEventListener("click", stopFlowHandler);
  el("stopExecFromTabBtn")?.addEventListener("click", stopFlowHandler);

  el("restartTopicBtn")?.addEventListener("click", async () => {
    if (!state.currentSessionId || !state.topic) return;
    try {
      await apiFetch(`/api/sessions/${state.currentSessionId}/start`, {
        method: "POST",
        body: JSON.stringify({
          topic: state.topic,
          collab_mode: state.collabMode,
          auto_preview_exec: state.autoPreviewExec,
          enabled_agents: state.enabledAgents,
          seat_personas: state.seatPersonas,
          seat_efforts: state.seatEfforts,
          executor_agent: state.executorAgent,
          reset_history: true,
        }),
      });
      showToast("已按当前策略与席位分工重开本议题", "ok", 2000);
    } catch (err) {
      showToast(err.message || "重开议题失败", "err");
    }
  });

  el("concludeBtn")?.addEventListener("click", async () => {
    if (!state.currentSessionId) return;
    try {
      await apiFetch(`/api/sessions/${state.currentSessionId}/conclude`, { method: "POST" });
    } catch (err) {
      showToast(err.message || "生成决议失败", "err");
    }
  });

  el("executeBtn")?.addEventListener("click", () => triggerExecutionNow());
  el("runExecFromTabBtn")?.addEventListener("click", () => triggerExecutionNow());

  // 会议白板操作：单击议题编辑、+添加条目、整理去重、复制纪要、导出 .md、跳转执行终端
  el("wbTopicText")?.addEventListener("click", () => startInlineTopicEdit());

  document.querySelectorAll("[data-wb-add]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const key = btn.dataset.wbAdd;
      const box = el(`wb-editor-${key}`);
      if (!box) return;
      const nowHidden = box.classList.toggle("hidden");
      if (!nowHidden) {
        const inp = box.querySelector("input");
        inp?.focus();
      }
    });
  });

  ["chair_constraints", "decision", "risk", "action"].forEach((editorKey) => {
    const box = el(`wb-editor-${editorKey}`);
    const inp = box?.querySelector("input");
    inp?.addEventListener("keydown", async (e) => {
      if (e.key === "Enter" && !e.isComposing) {
        e.preventDefault();
        const txt = inp.value.trim();
        if (!txt) return;
        const isConstraint = editorKey === "chair_constraints";
        const wb = await postWhiteboardMutation({
          op: "add",
          bucket: isConstraint ? "chair_constraints" : editorKey,
          kind: isConstraint ? "decision" : editorKey,
          author: "chair",
          pinned: isConstraint,
          checked: true,
          text: txt,
        });
        if (wb && inp.value.trim() === txt) {
          inp.value = "";
          box.classList.add("hidden");
        }
      } else if (e.key === "Escape") {
        box.classList.add("hidden");
      }
    });
  });

  el("dedupeWbBtn")?.addEventListener("click", async () => {
    const wb = await postWhiteboardMutation({ op: "dedupe_clean" });
    if (wb) showToast("已完成白板整理去重与过程性噪音清理", "ok", 2000);
  });
  el("copyMdBtn")?.addEventListener("click", () => copyTextToClipboard(buildMinutesMarkdown(), "会议纪要 Markdown 已复制"));
  el("exportMdBtn")?.addEventListener("click", () => exportMinutesMarkdownFile());
  el("wbToExecBtn")?.addEventListener("click", () => {
    setRightCollapsed(false);
    switchWorkbenchTab("terminal");
  });

  // 执行终端：执行席位分段器、沙箱权限分段器、日志与补丁操作、Git 回滚
  document.querySelectorAll("#executorSegmented [data-exec-agent]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const aid = btn.dataset.execAgent;
      if (!AGENT_ORDER.includes(aid)) return;
      state.executorAgent = aid;
      renderExecutorControls();
      renderWhiteboard(state.whiteboard || {}, true, true);
      if (state.currentSessionId) {
        await persistSessionSeatsPatch({ executor_agent: aid });
      }
    });
  });

  document.querySelectorAll("#sandboxSegmented [data-write-mode]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const writeOn = btn.dataset.writeMode === "write";
      if (el("allowWriteCheckbox")) el("allowWriteCheckbox").checked = writeOn;
      renderExecutorControls();
    });
  });

  el("copyTermBtn")?.addEventListener("click", () =>
    copyTextToClipboard(el("astraTermLogs")?.textContent || "", "执行日志已复制")
  );
  el("clearTermBtn")?.addEventListener("click", () => {
    if (el("astraTermLogs")) el("astraTermLogs").textContent = "尚未触发执行任务";
  });
  el("copyDiffBtn")?.addEventListener("click", () =>
    copyTextToClipboard(state.whiteboard?.exec_diff || "", "变更补丁 Diff 已复制")
  );
  el("rollbackExecBtn")?.addEventListener("click", async () => {
    if (!state.currentSessionId) return;
    try {
      const res = await apiFetch(`/api/sessions/${state.currentSessionId}/rollback`, { method: "POST" });
      showToast(res.message || "已回滚执行前工作区快照", "ok", 2600);
    } catch (err) {
      showToast(err.message || "回滚失败", "err");
    }
  });

  // 系统设置弹窗与连通实测
  el("railSettingsBtn")?.addEventListener("click", () => openSettingsModal());
  el("openSettingsBtn")?.addEventListener("click", () => openSettingsModal());
  el("closeSettingsBtn")?.addEventListener("click", () => closeSettingsModal());
  el("cancelSettingsBtn")?.addEventListener("click", () => closeSettingsModal());
  el("settingsModal")?.addEventListener("click", (e) => {
    if (e.target === el("settingsModal")) closeSettingsModal();
  });

  document.querySelectorAll("#cfgPacingGroup [data-pacing-mode]").forEach((btn) => {
    btn.addEventListener("click", () => {
      syncPacingControlsInModal(
        btn.dataset.pacingMode,
        el("cfgIdleTimeout")?.value,
        el("cfgTurnTimeout")?.value,
        el("cfgMaxRefChars")?.value
      );
    });
  });
  ["cfgIdleTimeout", "cfgTurnTimeout", "cfgMaxRefChars"].forEach((id) => {
    el(id)?.addEventListener("input", () => {
      syncPacingControlsInModal(
        "custom",
        el("cfgIdleTimeout")?.value,
        el("cfgTurnTimeout")?.value,
        el("cfgMaxRefChars")?.value
      );
    });
  });

  el("browseWorkspaceBtn")?.addEventListener("click", () => pickWorkspaceFolder());
  el("quickSingleCliTriadBtn")?.addEventListener("click", () => applyQuickSingleCliTriad());
  el("testCliBtn")?.addEventListener("click", () => runCliTest(false));
  el("modalTestCliBtn")?.addEventListener("click", () => runCliTest(true));
  el("saveSettingsBtn")?.addEventListener("click", () => saveSettingsFromModal());

  for (const cap of ["Carbon", "Grok", "Astra"]) {
    el(`cfg${cap}Driver`)?.addEventListener("change", () => refreshSeatEffortSelectInModal(cap, true));
    el(`cfg${cap}Model`)?.addEventListener("input", () => refreshSeatEffortSelectInModal(cap, false));
  }

  el("cfgRosterPresetSelect")?.addEventListener("change", (e) => {
    const val = e.target.value || "role_experts";
    const preset = ROSTER_NAME_PRESETS[val];
    for (const [aid, cap] of [
      ["carbon", "Carbon"],
      ["grok", "Grok"],
      ["astra", "Astra"],
    ]) {
      const inp = el(`cfg${cap}Name`);
      if (inp) {
        inp.placeholder = preset?.names?.[aid]
          ? `留空默认：${preset.names[aid]}`
          : "留空跟随底层引擎自动生成";
      }
    }
  });

  // 点击空白处收起浮层与全局快捷键
  document.addEventListener("click", (e) => {
    if (!e.target.closest("#appearanceMenuWrap")) {
      toggleAppearanceMenu(false);
    }
    if (!e.target.closest("#personaPopover") && !e.target.closest("[data-persona-trigger]")) {
      closePersonaPopover();
    }
    if (!e.target.closest("#atSuggestMenu") && !e.target.closest("#topicInput") && !e.target.closest("#insertFileRefBtn")) {
      closeAtSuggestMenu();
    }
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      toggleAppearanceMenu(false);
      closePersonaPopover();
      closeAtSuggestMenu();
      closeSettingsModal();
      return;
    }
    if (e.metaKey || e.ctrlKey) {
      const k = e.key.toLowerCase();
      if (k === "b") {
        e.preventDefault();
        const isCollapsed = el("appShell")?.classList.contains("left-collapsed");
        setLeftCollapsed(!isCollapsed);
      } else if (k === "j") {
        e.preventDefault();
        const isHidden = el("appShell")?.classList.contains("right-collapsed");
        setRightCollapsed(!isHidden);
      } else if (k === "n") {
        e.preventDefault();
        createNewSession();
      } else if (k === ",") {
        e.preventDefault();
        openSettingsModal();
      }
    }
  });
}

window.__roundtableMenu = (action) => {
  switch (action) {
    case "settings": openSettingsModal(); break;
    case "newSession": createNewSession(); break;
    case "pickFolder": pickWorkspaceFolder(); break;
    case "toggleLeft": el("brandToggleRailBtn")?.click(); break;
    case "toggleRight": el("toggleRightBtn")?.click(); break;
  }
};

async function bootstrap() {
  applyTheme(localStorage.getItem(STORAGE_KEYS.theme) || "light");
  applyPalette(localStorage.getItem(STORAGE_KEYS.palette) || "pearl");
  applyFontSize(localStorage.getItem(STORAGE_KEYS.fontsize) || "comfort");

  const savedLeftExpanded = localStorage.getItem(STORAGE_KEYS.leftExpanded) === "1";
  setLeftCollapsed(!savedLeftExpanded);
  const savedRightHidden = localStorage.getItem(STORAGE_KEYS.rightHidden) === "1";
  setRightCollapsed(savedRightHidden);

  bindEvents();
  setInterval(tickThinkingTimers, 1000);

  try {
    const statusRes = await apiFetch("/api/status");
    renderSystemStatus(statusRes.system);
    state.sessions = statusRes.sessions || [];
    const targetSid =
      statusRes.default_session_id || (state.sessions[0] && state.sessions[0].session_id) || "";
    state.currentSessionId = targetSid;
    renderSessionList();
    if (targetSid) {
      connectSessionStream(targetSid);
    }
  } catch (err) {
    showToast(`连接本地服务失败：${err.message}`, "err", 4500);
  }
}

bootstrap();
