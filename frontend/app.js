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

const AGENT_ORDER = ["carbon", "grok", "astra", "vega", "titan", "prism"];
const CORE_TRIAD_SEATS = ["carbon", "grok", "astra"];
const SEAT_CAP_PAIRS = [
  ["carbon", "Carbon", "席位一"],
  ["grok", "Grok", "席位二"],
  ["astra", "Astra", "席位三"],
  ["vega", "Vega", "席位四"],
  ["titan", "Titan", "席位五"],
  ["prism", "Prism", "席位六"],
];

// AI_ROUNDTABLE_V3_UPGRADE_20261114 — 内存态控制面鉴权凭据（严禁落 localStorage / Cookie / URL Query）
const authState = {
  token: "",
  bootId: "",
  ready: false,
};

const AGENT_NAMES = {
  carbon: "架构师",
  grok: "审计官",
  astra: "工程师",
  vega: "交互设计",
  titan: "性能专家",
  prism: "质量验证",
  chair: "主持人",
  system: "系统",
};

const AUTHOR_BADGE_META = {
  chair: { short: "主", name: "主持约束", cls: "badge-seat-chair" },
  carbon: { short: "架", name: "架构师", cls: "badge-seat-carbon" },
  grok: { short: "审", name: "审计官", cls: "badge-seat-grok" },
  astra: { short: "工", name: "工程师", cls: "badge-seat-astra" },
  vega: { short: "交", name: "交互设计", cls: "badge-seat-vega" },
  titan: { short: "性", name: "性能专家", cls: "badge-seat-titan" },
  prism: { short: "验", name: "质量验证", cls: "badge-seat-prism" },
  system: { short: "系", name: "决议归档", cls: "badge-seat-system" },
};

const ROSTER_NAME_PRESETS = {
  role_experts: {
    label: "专业职能称呼",
    names: { carbon: "架构师", grok: "审计官", astra: "工程师", vega: "交互设计", titan: "性能专家", prism: "质量验证" },
  },
  council_alpha: {
    label: "中立席位代号",
    names: { carbon: "Alpha", grok: "Beta", astra: "Gamma", vega: "Delta", titan: "Epsilon", prism: "Zeta" },
  },
  product_studio: {
    label: "产品研发委员会",
    names: { carbon: "产品总监", grok: "红队审计", astra: "研发主程", vega: "体验设计", titan: "稳定性架构", prism: "测试主管" },
  },
  auto_driver: { label: "跟随底层引擎", names: {} },
  classic: {
    label: "经典工程代号",
    names: { carbon: "Carbon", grok: "Grok", astra: "Astra", vega: "Vega", titan: "Titan", prism: "Prism" },
  },
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
  vega: "product_ux",
  titan: "perf_sre",
  prism: "qa_audit",
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

// 模块五：1–6 席全场景阵容预设
const SCENARIO_PRESETS = {
  solo_focus: {
    key: "solo_focus",
    label: "单席专注（1席）",
    collab_mode: "rapid_consensus",
    solo: true,
  },
  duel_review: {
    key: "duel_review",
    label: "双席辩证（2席）",
    collab_mode: "adversarial_review",
    enabled_agents: ["carbon", "grok"],
    seat_personas: { carbon: "fullstack_solo", grok: "red_team" },
    executor_agent: "carbon",
  },
  arch_review: {
    key: "arch_review",
    label: "标准三席评审（3席）",
    collab_mode: "deep_deliberation",
    enabled_agents: ["carbon", "grok", "astra"],
    seat_personas: { carbon: "planner", grok: "red_team", astra: "implementer" },
    executor_agent: "astra",
  },
  classic_triad: {
    key: "classic_triad",
    label: "标准三席合议（3席）",
    collab_mode: "deep_deliberation",
    enabled_agents: ["carbon", "grok", "astra"],
    seat_personas: { carbon: "planner", grok: "red_team", astra: "implementer" },
    executor_agent: "astra",
  },
  proposal_debate: {
    key: "proposal_debate",
    label: "方案论证（3席）",
    collab_mode: "adversarial_review",
    enabled_agents: ["carbon", "grok", "astra"],
    seat_personas: { carbon: "planner", grok: "red_team", astra: "implementer" },
    executor_agent: "astra",
  },
  product_design: {
    key: "product_design",
    label: "产品设计（3席）",
    collab_mode: "divergent_convergent",
    enabled_agents: ["carbon", "grok", "astra"],
    seat_personas: { carbon: "product_ux", grok: "red_team", astra: "fullstack_solo" },
    executor_agent: "astra",
  },
  code_diagnosis: {
    key: "code_diagnosis",
    label: "源码诊断（3席）",
    collab_mode: "code_review",
    enabled_agents: ["carbon", "grok", "astra"],
    seat_personas: { carbon: "perf_sre", grok: "qa_audit", astra: "implementer" },
    executor_agent: "astra",
  },
  product_quad: {
    key: "product_quad",
    label: "四席产品全栈（4席）",
    collab_mode: "divergent_convergent",
    enabled_agents: ["carbon", "vega", "grok", "astra"],
    seat_personas: { carbon: "planner", vega: "product_ux", grok: "red_team", astra: "implementer" },
    executor_agent: "astra",
  },
  sre_council_5: {
    key: "sre_council_5",
    label: "五席高可靠委员会（5席）",
    collab_mode: "deep_deliberation",
    enabled_agents: ["carbon", "vega", "grok", "titan", "astra"],
    seat_personas: { carbon: "planner", vega: "product_ux", grok: "red_team", titan: "perf_sre", astra: "implementer" },
    executor_agent: "astra",
  },
  full_jury_6: {
    key: "full_jury_6",
    label: "六席全景评审（6席）",
    collab_mode: "deep_deliberation",
    enabled_agents: ["carbon", "vega", "grok", "titan", "astra", "prism"],
    seat_personas: {
      carbon: "planner",
      vega: "product_ux",
      grok: "red_team",
      titan: "perf_sre",
      astra: "implementer",
      prism: "qa_audit",
    },
    executor_agent: "astra",
  },
};

// P0.3 强制有限默认时限（废除 turn_timeout_sec=0 无限挂死分支）
const PACING_PRESETS = {
  standard: {
    idle_timeout_sec: 300,
    turn_timeout_sec: 600,
    max_ref_chars: 120000,
    desc: "空闲等待 300s · 单轮上限 600s · 源码预算 120,000 字符（推荐默认）",
  },
  unrestricted: {
    idle_timeout_sec: 600,
    turn_timeout_sec: 1800,
    max_ref_chars: 120000,
    desc: "空闲等待 600s · 单轮长考上限 1800s · 源码预算 120,000 字符",
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
  sseAbortController: null,
  sseReconnectTimer: null,
  sseConnectedSessionId: "",
  sseLastRev: 0,
  seatConfigRev: 0,
  userScrolledUp: false,
  activeTab: "whiteboard",
  activeSettingsTab: "seats",
  showAllSeatsInRing: false,
  cliTestResults: {},
  pingLatencyBySeat: {},
  expandedCliCard: null,
  personaPopoverSeat: null,
  execStartTs: 0,
  execState: "idle",
  recoveryRequired: false,
  recoveryPlan: null,
  rollbackConflicts: [],
  postExecVerifyFailed: false,
  postExecVerifyCmd: "",
  rosterPreset: "role_experts",
  singleCliConcurrency: 3,
  pacingMode: "standard",
  idleTimeoutSec: 300,
  turnTimeoutSec: 600,
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
  topicLocked: false,
  scenarioPack: "arch_code",
  artifactType: "code_patch",
  presetSwitching: false,
  userToggledRightPane: false,
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

async function initControlPlaneAuth() {
  // 1. 先检查 URL Fragment (#bootstrap=...)，第一时间抹除浏览器地址栏，杜绝泄露
  const rawHash = window.location.hash || "";
  let bootstrapCode = "";
  if (rawHash.startsWith("#")) {
    const hashParams = new URLSearchParams(rawHash.slice(1));
    bootstrapCode = (hashParams.get("bootstrap") || "").trim();
    if (bootstrapCode) {
      window.history.replaceState(null, "", window.location.pathname + window.location.search);
    }
  }

  // 2. macOS 原生 WKWebView 主框架受信任源凭据桥
  const nativeBridge = window.webkit?.messageHandlers?.roundtableNative || window.roundtableDesktop;
  if (nativeBridge && typeof nativeBridge.postMessage === "function") {
    try {
      const nativeAuth = await nativeBridge.postMessage({ action: "getBootAuth" });
      if (nativeAuth && nativeAuth.token) {
        authState.token = String(nativeAuth.token);
        authState.bootId = String(nativeAuth.bootId || "");
        authState.ready = true;
        return;
      }
    } catch {
      // 回退至 Web 引导码核销流程
    }
  }

  // 3. 纯浏览器开发模式：单次核销 #bootstrap 兑换码换取内存态 X-Roundtable-Token
  if (bootstrapCode) {
    const res = await fetch("/api/auth/bootstrap", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code: bootstrapCode }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data.token) {
      throw new Error(data.error || "引导兑换码已失效，请从终端输出重新打开一次性引导链接");
    }
    authState.token = String(data.token);
    authState.bootId = String(data.boot_id || "");
    authState.ready = true;
  }
}

async function apiFetch(path, options = {}) {
  const mergedHeaders = {
    "Content-Type": "application/json",
    ...(authState.token ? { "X-Roundtable-Token": authState.token } : {}),
    ...(options.headers || {}),
  };
  const opts = {
    ...options,
    headers: mergedHeaders,
  };
  const res = await fetch(path, opts);
  const data = await res.json().catch(() => ({}));
  if (data && typeof data.boot_id === "string" && data.boot_id) {
    authState.bootId = data.boot_id;
  }
  if (!res.ok) {
    const err = new Error(data.error || `请求失败 (${res.status})`);
    err.status = res.status;
    err.payload = data;
    throw err;
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

const CLIENT_SCENARIO_PACKS = {
  arch_code: {
    key: "arch_code",
    label: "工程研发与代码审查包",
    preset: "arch_review",
    collab_mode: "deep_deliberation",
    artifact_type: "code_patch",
    enabled_agents: ["carbon", "grok", "astra"],
    seat_personas: { carbon: "planner", grok: "red_team", astra: "implementer" },
    executor_agent: "astra",
    requires_workspace: true,
    prefer_unbound_workspace: false,
  },
  tradeoff_debate: {
    key: "tradeoff_debate",
    label: "方案利弊红蓝辩证包",
    preset: "arch_review",
    collab_mode: "adversarial_review",
    artifact_type: "decision_matrix",
    enabled_agents: ["carbon", "grok", "astra"],
    seat_personas: { carbon: "planner", grok: "red_team", astra: "fullstack_solo" },
    executor_agent: "astra",
    requires_workspace: false,
    prefer_unbound_workspace: true,
  },
  ux_multimodal: {
    key: "ux_multimodal",
    label: "产品体验与多模态走查包",
    preset: "product_quad",
    collab_mode: "divergent_convergent",
    artifact_type: "ux_checklist",
    enabled_agents: ["vega", "carbon", "grok", "astra"],
    seat_personas: { vega: "product_ux", carbon: "planner", grok: "red_team", astra: "implementer" },
    executor_agent: "astra",
    requires_workspace: false,
    prefer_unbound_workspace: false,
  },
  incident_doc: {
    key: "incident_doc",
    label: "故障排查与文稿打磨包",
    preset: "duel_review",
    collab_mode: "rapid_consensus",
    artifact_type: "doc_export",
    enabled_agents: ["grok", "astra"],
    seat_personas: { grok: "perf_sre", astra: "qa_audit" },
    executor_agent: "astra",
    requires_workspace: false,
    prefer_unbound_workspace: false,
  },
};

function getCheckedActionCount() {
  const items = state.whiteboard?.items;
  if (!Array.isArray(items)) return 0;
  return items.filter((it) => it && it.kind === "action" && it.checked === true).length;
}

function hasExportableSessionContent() {
  const hasMsgs = Boolean(
    state.messages &&
      Array.from(state.messages.values()).some((m) => m && !m.skipped && String(m.content || "").trim())
  );
  const hasItems = Boolean(state.whiteboard?.items?.length);
  const hasAbandoned = Boolean(state.whiteboard?.abandoned_proposals?.length);
  return Boolean(hasMsgs || hasItems || hasAbandoned);
}

function setRightCollapsed(collapsed, manualByUser = false) {
  const shell = el("appShell");
  const btn = el("toggleRightBtn");
  if (!shell) return;
  const nextCollapsed = Boolean(collapsed);
  if (manualByUser) {
    state.userToggledRightPane = true;
    localStorage.setItem(STORAGE_KEYS.rightHidden, nextCollapsed ? "1" : "0");
  }
  shell.classList.toggle("right-collapsed", nextCollapsed);
  if (btn) {
    btn.classList.toggle("active-pane", !nextCollapsed);
  }
}

function syncAdaptiveRightCollapse() {
  if (state.userToggledRightPane) return;
  const isIdleBlank =
    (state.stage || "idle") === "idle" &&
    !String(state.topic || state.whiteboard?.topic || "").trim() &&
    (!state.messages || state.messages.size === 0) &&
    !(state.whiteboard?.items?.length) &&
    !(state.whiteboard?.abandoned_proposals?.length);
  setRightCollapsed(isIdleBlank, false);
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

/* ==================== 讨论策略、自动执行预演与场景预设事务同步 ==================== */

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
    if (state.seatPersonas[only] === "fullstack_solo") {
      return "solo_focus";
    }
    return "";
  }
  const curSet = state.enabledAgents.join(",");
  for (const [key, sp] of Object.entries(SCENARIO_PRESETS)) {
    if (sp.solo || key === "classic_triad") continue;
    if (!Array.isArray(sp.enabled_agents) || sp.enabled_agents.join(",") !== curSet) continue;
    if (sp.collab_mode !== state.collabMode) continue;
    const matchPersonas = sp.enabled_agents.every((aid) => state.seatPersonas[aid] === sp.seat_personas[aid]);
    if (matchPersonas) return key;
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

  for (const [aid, cap, slotLabel] of SEAT_CAP_PAIRS) {
    const stName = state.seatStates?.[aid]?.name;
    const sysName = sysAgents?.[aid]?.name;
    const resolved = String(sysName || stName || presetObj.names?.[aid] || AGENT_NAMES[aid] || aid).trim();
    AGENT_NAMES[aid] = resolved;
    if (!AUTHOR_BADGE_META[aid]) {
      AUTHOR_BADGE_META[aid] = { short: computeAvatarShortChar(resolved, aid), name: resolved, cls: `badge-seat-${aid}` };
    } else {
      AUTHOR_BADGE_META[aid].name = resolved;
      AUTHOR_BADGE_META[aid].short = computeAvatarShortChar(resolved, aid);
    }

    const seatCard = el(`seat-${aid}`);
    if (seatCard) {
      const nameSpan = seatCard.querySelector(".seat-name");
      if (nameSpan) nameSpan.textContent = resolved;
      const av = seatCard.querySelector(".seat-avatar");
      if (av && !av.querySelector("svg")) av.textContent = AUTHOR_BADGE_META[aid].short;
      seatCard.title = `点击胶囊点名 @${resolved}；点击职责标签配置角色、名称与推理档位`;
      const roleBtn = el(`seat-role-${aid}`);
      if (roleBtn) roleBtn.title = `配置 ${resolved} 角色职责、显示名称、推理档位与参会状态`;
    }

    const h4 = el(`cfgHead${cap}`);
    if (h4) h4.textContent = `${resolved}（${slotLabel}）`;

    document.querySelectorAll(`[data-seat-slot-name="${aid}"]`).forEach((b) => {
      b.textContent = resolved;
    });

    document.querySelectorAll(`.msg-card.speaker-${aid} [data-msg-act="mention"]`).forEach((btn) => {
      btn.textContent = `@${resolved}`;
    });
  }

  const cN = AGENT_NAMES.carbon;
  const gN = AGENT_NAMES.grok;
  const aN = AGENT_NAMES.astra;
  const vN = AGENT_NAMES.vega;
  const tN = AGENT_NAMES.titan;
  const pN = AGENT_NAMES.prism;
  const scenarioDescMap = {
    solo_focus: `1席 · 启用首席「全栈架构」独立完成推演与交付`,
    duel_review: `2席 · ${cN} 全栈立论 + ${gN} 反向压力质询`,
    arch_review: `3席 · ${cN} 架构规划 · ${gN} 风险审计 · ${aN} 工程实现`,
    product_quad: `4席 · ${cN} / ${vN} / ${gN} / ${aN} 产品与全栈合议`,
    sre_council_5: `5席 · 增设 ${tN} 专项评审并发锁、存储事务与低延迟`,
    full_jury_6: `6席 · ${cN}·${vN}·${gN}·${tN}·${aN}·${pN} 全景评审`,
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
  document.querySelectorAll("[data-scenario-pack]").forEach((card) => {
    const pk = card.dataset.scenarioPack;
    const isAct = Boolean(state.scenarioPack) && pk === state.scenarioPack;
    card.classList.toggle("active", isAct);
    card.setAttribute("aria-pressed", isAct ? "true" : "false");
  });
}

function captureLineupSnapshot() {
  return {
    collabMode: state.collabMode,
    autoPreviewExec: state.autoPreviewExec,
    enabledAgents: [...state.enabledAgents],
    seatPersonas: { ...state.seatPersonas },
    seatEfforts: { ...state.seatEfforts },
    executorAgent: state.executorAgent,
    scenarioPack: state.scenarioPack,
    artifactType: state.artifactType,
  };
}

function restoreLineupSnapshot(snap) {
  if (!snap) return;
  state.collabMode = snap.collabMode;
  state.autoPreviewExec = snap.autoPreviewExec;
  state.enabledAgents = [...snap.enabledAgents];
  state.seatPersonas = { ...snap.seatPersonas };
  state.seatEfforts = { ...snap.seatEfforts };
  state.executorAgent = snap.executorAgent;
  state.scenarioPack = snap.scenarioPack;
  state.artifactType = snap.artifactType;
  syncCollabModeUI(state.collabMode, state.autoPreviewExec);
  renderAllSeats();
  renderQuickCueButtons();
  renderExecutorControls();
  syncScenarioPresetHighlight();
  if (state.whiteboard) renderWhiteboard(state.whiteboard, true, false);
}

async function persistSessionSeatsPatch(patch) {
  const sessionId = state.currentSessionId;
  if (!sessionId) return null;
  const res = await apiFetch(`/api/sessions/${sessionId}/seats`, {
    method: "POST",
    body: JSON.stringify(patch),
  });
  if (sessionId !== state.currentSessionId || (res.rev && res.rev < state.seatConfigRev)) return res;
  state.seatConfigRev = Math.max(state.seatConfigRev, res.rev || 0);
  if (Array.isArray(res.enabled_agents)) state.enabledAgents = res.enabled_agents;
  if (res.seat_personas) state.seatPersonas = { ...state.seatPersonas, ...res.seat_personas };
  if (res.seat_efforts) state.seatEfforts = { ...res.seatEfforts };
  if (res.executor_agent) state.executorAgent = res.executor_agent;
  if (typeof res.scenario_pack === "string" && res.scenario_pack) state.scenarioPack = res.scenario_pack;
  if (typeof res.artifact_type === "string" && res.artifact_type) state.artifactType = res.artifact_type;
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
  if (state.whiteboard) renderWhiteboard(state.whiteboard, true, false);
  return res;
}

async function applyScenarioPack(packKey) {
  const srvPacks = state.system?.scenario_packs || {};
  const pack = {
    ...(CLIENT_SCENARIO_PACKS[packKey] || {}),
    ...(srvPacks[packKey] || {}),
  };
  if (!pack || !pack.collab_mode) return false;
  if (state.presetSwitching) return false;
  if (state.isBusy || ["opening_parallel", "cross_talk", "chair_interrupt", "executing"].includes(state.stage)) {
    showToast("当前回合正在运行中，请待本轮收敛或停止后再切换场景意图包", "warn", 2400);
    return false;
  }

  const prevSnap = captureLineupSnapshot();
  state.presetSwitching = true;
  try {
    const nextEnabled = Array.isArray(pack.enabled_agents) && pack.enabled_agents.length
      ? [...pack.enabled_agents]
      : ["carbon", "grok", "astra"];
    const nextPersonas = { ...state.seatPersonas, ...(pack.seat_personas || {}) };
    const nextExec = pack.executor_agent || (nextEnabled.includes("astra") ? "astra" : nextEnabled[0]);
    const nextArt = pack.artifact_type || "code_patch";

    if (state.currentSessionId) {
      await persistSessionSeatsPatch({
        scenario_pack: packKey,
        artifact_type: nextArt,
        collab_mode: pack.collab_mode,
        enabled_agents: nextEnabled,
        seat_personas: nextPersonas,
        executor_agent: nextExec,
      });
    } else {
      state.scenarioPack = packKey;
      state.artifactType = nextArt;
      state.enabledAgents = nextEnabled;
      state.seatPersonas = nextPersonas;
      state.executorAgent = nextExec;
      syncCollabModeUI(pack.collab_mode, state.autoPreviewExec);
      renderAllSeats();
      renderQuickCueButtons();
      renderExecutorControls();
      syncScenarioPresetHighlight();
    }

    state.scenarioPack = packKey;
    state.artifactType = state.artifactType || nextArt;
    syncScenarioPresetHighlight();

    const isIdleUnstarted =
      (state.stage || "idle") === "idle" &&
      (!state.messages || state.messages.size === 0) &&
      !String(state.topic || "").trim();
    if ((pack.prefer_unbound_workspace || packKey === "tradeoff_debate") && isIdleUnstarted && effectiveWorkspacePath()) {
      await switchCurrentSessionWorkspace("");
    }
    if (state.whiteboard) renderWhiteboard(state.whiteboard, true, false);
    showToast(`已切换场景意图包：${pack.label || packKey}`, "ok", 2200);
    return true;
  } catch (err) {
    restoreLineupSnapshot(prevSnap);
    showToast(err.message || "切换场景意图包失败，已回滚原阵容", "err", 2800);
    return false;
  } finally {
    state.presetSwitching = false;
  }
}

async function applyScenarioPreset(presetKey) {
  const spec = SCENARIO_PRESETS[presetKey];
  if (!spec) return false;
  if (state.presetSwitching) return false;
  if (state.isBusy || ["opening_parallel", "cross_talk", "chair_interrupt", "executing"].includes(state.stage)) {
    showToast("当前研讨或执行正在运行中，请待收敛后再切换预设阵容", "warn", 2400);
    return false;
  }

  const prevSnap = captureLineupSnapshot();
  state.presetSwitching = true;

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
    nextPersonas = { ...state.seatPersonas, ...spec.seat_personas };
    nextExec = spec.executor_agent || "astra";
  }

  try {
    if (state.currentSessionId) {
      await persistSessionSeatsPatch({
        collab_mode: spec.collab_mode,
        enabled_agents: nextEnabled,
        seat_personas: nextPersonas,
        executor_agent: nextExec,
      });
    } else {
      syncCollabModeUI(spec.collab_mode, state.autoPreviewExec);
      state.enabledAgents = nextEnabled;
      state.seatPersonas = nextPersonas;
      state.executorAgent = nextExec;
      renderAllSeats();
      renderQuickCueButtons();
      renderExecutorControls();
      syncScenarioPresetHighlight();
    }
    showToast(`已切换场景预设：${spec.label}（${COLLAB_MODES[spec.collab_mode]?.label || spec.collab_mode}）`, "ok", 2200);
    return true;
  } catch (err) {
    restoreLineupSnapshot(prevSnap);
    showToast(err.message || "更新场景预设失败，已回滚原阵容", "err", 2800);
    return false;
  } finally {
    state.presetSwitching = false;
  }
}

async function applyHeterogeneousRecommendation() {
  if (state.presetSwitching) return false;
  if (state.isBusy || ["opening_parallel", "cross_talk", "chair_interrupt", "executing"].includes(state.stage)) {
    showToast("当前研讨正在运行中，请待收敛后再切换异构混编阵容", "warn", 2400);
    return false;
  }

  const prevSnap = captureLineupSnapshot();
  state.presetSwitching = true;

  try {
    if (state.currentSessionId) {
      await persistSessionSeatsPatch({
        recommend_heterogeneous: true,
      });
    } else {
      const rec = state.system?.heterogeneous_recommendation;
      const sysAgents = state.system?.agents || {};
      let nextEnabled = [];
      let nextPersonas = { ...state.seatPersonas };

      if (rec && Array.isArray(rec.enabled_agents) && rec.enabled_agents.length >= 2) {
        nextEnabled = [...rec.enabled_agents];
        if (rec.seat_personas) nextPersonas = { ...nextPersonas, ...rec.seat_personas };
      } else {
        const seenFamilies = new Set();
        for (const aid of AGENT_ORDER) {
          const info = sysAgents[aid] || {};
          if (!info.binary_detected) continue;
          const fam = String(info.binary_realpath || info.binary_path || info.effective_driver || aid);
          if (!seenFamilies.has(fam)) {
            seenFamilies.add(fam);
            nextEnabled.push(aid);
          }
          if (nextEnabled.length >= 3) break;
        }
        if (nextEnabled.length < 2) {
          nextEnabled = ["carbon", "grok", "astra"];
        }
      }
      state.enabledAgents = nextEnabled;
      state.seatPersonas = nextPersonas;
      state.executorAgent = nextEnabled.includes("astra") ? "astra" : nextEnabled[0];
      renderAllSeats();
      renderQuickCueButtons();
      renderExecutorControls();
      syncScenarioPresetHighlight();
    }
    showToast(
      `已启用异构混编推荐阵容（${state.enabledAgents.map((a) => AGENT_NAMES[a] || a).join(" · ")}）`,
      "ok",
      2400
    );
    return true;
  } catch (err) {
    restoreLineupSnapshot(prevSnap);
    showToast(err.message || "应用异构混编阵容失败，已回滚原阵容", "err", 2800);
    return false;
  } finally {
    state.presetSwitching = false;
  }
}

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
  const nextMode = ["standard", "unrestricted", "custom"].includes(mode) ? mode : "standard";
  state.pacingMode = nextMode;

  document.querySelectorAll("#cfgPacingGroup [data-pacing-mode]").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.pacingMode === nextMode);
  });

  const customBox = el("cfgCustomPacingBox");
  if (customBox) {
    customBox.classList.toggle("hidden", nextMode !== "custom");
  }

  const preset = PACING_PRESETS[nextMode];
  const effIdle = Math.max(15, preset ? preset.idle_timeout_sec : Number(idleSec || state.idleTimeoutSec || 300));
  const effTurn = Math.max(30, preset ? preset.turn_timeout_sec : Number(turnSec || state.turnTimeoutSec || 600));
  const effRef = Math.max(10000, preset ? preset.max_ref_chars : Number(refChars || state.maxRefChars || 120000));

  if (el("cfgIdleTimeout")) el("cfgIdleTimeout").value = String(effIdle);
  if (el("cfgTurnTimeout")) el("cfgTurnTimeout").value = String(effTurn);
  if (el("cfgMaxRefChars")) el("cfgMaxRefChars").value = String(effRef);

  const descEl = el("cfgPacingDesc");
  if (descEl) {
    descEl.textContent = preset
      ? preset.desc
      : `空闲上限 ${effIdle}s · 单轮上限 ${effTurn}s · 源码预算 ${effRef.toLocaleString()} 字符`;
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
    new Set(
      [
        "Carbon",
        "Grok",
        "Astra",
        "Vega",
        "Titan",
        "Prism",
        "主持人",
        ...AGENT_ORDER.map((aid) => AGENT_NAMES[aid]),
      ].filter(Boolean)
    )
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

function resolveKineticVisualSpec(activityRaw, phaseRaw) {
  const txt = `${activityRaw || ""} ${phaseRaw || ""}`;
  if (/源码|检索|扫描|读取|索引|上下文|注入/.test(txt)) {
    return {
      mode: "scanning",
      phaseTag: "上下文检索",
      html: `<span class="kinetic-stage" data-kinetic-mode="scanning" aria-hidden="true"><span class="k-scan-bars"><i></i><i></i><i></i><i></i></span></span>`,
    };
  }
  if (/决议|收敛|汇总|归档|快照|回滚|验证/.test(txt)) {
    return {
      mode: "synthesizing",
      phaseTag: "共识收敛",
      html: `<span class="kinetic-stage" data-kinetic-mode="synthesizing" aria-hidden="true"><span class="k-synth-wrap"><span class="k-synth-halo"></span><span class="k-synth-inner-ring"></span></span></span>`,
    };
  }
  return {
    mode: "thinking",
    phaseTag: /质询|答辩|辩证/.test(txt) ? "交叉核验" : "深度推演",
    html:
      `<span class="kinetic-stage" data-kinetic-mode="thinking" aria-hidden="true">` +
      `<svg class="k-linear-trefoil" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round">` +
      `<circle class="k-ring r1" cx="12" cy="8.9" r="5.1"></circle>` +
      `<circle class="k-ring r2" cx="9.4" cy="13.5" r="5.1"></circle>` +
      `<circle class="k-ring r3" cx="14.6" cy="13.5" r="5.1"></circle>` +
      `</svg>` +
      `</span>`,
  };
}

function buildThinkingPlaceholderHtml(msg) {
  const startTs = Number(msg.started_ts || Date.now());
  const elapsedSec = Math.max(0, Math.floor((Date.now() - startTs) / 1000));
  const modelTag = escapeHtml(formatThinkingModelTag(msg));
  const rawAct = msg.activity || "正在组织核心论据与代码锚点…";
  const activity = escapeHtml(rawAct);
  const kSpec = resolveKineticVisualSpec(rawAct, msg.phase_label);
  const canSkip = AGENT_ORDER.includes(msg.speaker);
  const skipVisible = elapsedSec >= 15 ? " is-visible" : "";
  return (
    `<div class="thinking-placeholder" data-thinking-for="${escapeHtml(msg.id)}" data-kinetic-state="${kSpec.mode}">` +
      kSpec.html +
      `<span class="thinking-status-wrap">` +
        `<span class="thinking-model-tag">${modelTag}</span>` +
        `<span class="thinking-phase-pill">${escapeHtml(kSpec.phaseTag)}</span>` +
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
    msg.streaming ? "is-streaming" : "",
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

  const hasContent = Boolean((msg.content || "").trim());
  const isThinkingOnly = Boolean(msg.streaming) && !hasContent;

  const badgeSemCls = resolveSemanticBadgeClass(msg);
  const suppressRedundantThinkingBadge = isThinkingOnly && msg.badge === "思考中";
  const badgeHtml = msg.badge && !suppressRedundantThinkingBadge
    ? `<span class="msg-badge-chip ${badgeSemCls}">${escapeHtml(msg.badge)}</span>`
    : "";

  const timingStr =
    !msg.streaming && msg.elapsed_ms > 0
      ? `<span class="msg-timing">${(msg.elapsed_ms / 1000).toFixed(1)}s</span>`
      : "";

  const isAgentMsg = AGENT_ORDER.includes(speakerKey);
  const canIngestWb = !msg.streaming && !isError && !isSkipped && (isAgentMsg || isResolution) && hasContent;

  const hoverBtns = [];
  if (isResolution && !msg.streaming && hasContent) {
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
  if (!msg.streaming && hasContent) {
    hoverBtns.push(`<button type="button" class="msg-act-btn" data-msg-act="copy">复制</button>`);
    if ((msg.content || "").length > 360) {
      hoverBtns.push(
        `<button type="button" class="msg-act-btn msg-fold-toggle" data-msg-act="toggle-fold">${wasCollapsed ? "展开" : "收起"}</button>`
      );
    }
  }

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

  let resolutionAuditHtml = "";
  if (isResolution && !msg.streaming && hasContent) {
    const rMeta = msg.resolution_meta || state.whiteboard?.resolution_meta || {};
    const epBadge =
      rMeta.epistemic_badge ||
      state.whiteboard?.epistemic_badge ||
      (state.enabledAgents.length <= 1 ? "[单席推演草稿]" : "");
    const roundsArr = Array.isArray(rMeta.covered_rounds)
      ? rMeta.covered_rounds
      : rMeta.covered_rounds
      ? [String(rMeta.covered_rounds)]
      : [];
    const wbItemsNow = state.whiteboard?.items || [];
    const retainedCnt =
      rMeta.retained_count ??
      rMeta.adopted_count ??
      wbItemsNow.filter((it) => it.kind === "decision").length;
    const abandonedCnt =
      rMeta.abandoned_count ?? (state.whiteboard?.abandoned_proposals?.length || 0);
    const actionCnt =
      rMeta.action_count ?? wbItemsNow.filter((it) => it.kind === "action").length;

    resolutionAuditHtml =
      `<div class="resolution-audit-strip">` +
        (epBadge ? `<span class="audit-metric-pill">${escapeHtml(epBadge)}</span>` : "") +
        (roundsArr.length
          ? `<span class="audit-metric-pill">覆盖阶段：${escapeHtml(roundsArr.join(" · "))}</span>`
          : "") +
        `<span class="audit-metric-pill is-retained">采纳成果 ${Number(retainedCnt)}</span>` +
        `<span class="audit-metric-pill is-abandoned">隔离弃案 ${Number(abandonedCnt)}</span>` +
        `<span class="audit-metric-pill">交付清单 ${Number(actionCnt)}</span>` +
      `</div>`;
  }

  let roundSummaryBarHtml = "";
  const roundSummaries = state.whiteboard?.round_summaries;
  if (Array.isArray(roundSummaries) && msg.id) {
    const matchedRs = roundSummaries.find((rs) => rs && rs.after_msg_id === msg.id);
    if (matchedRs) {
      const rsLabel = matchedRs.round_label || matchedRs.phase_label || "回合演进摘要";
      const rsText =
        matchedRs.summary ||
        matchedRs.text ||
        (Array.isArray(matchedRs.highlights) ? matchedRs.highlights.join("；") : "");
      const openDisCnt = Number(
        matchedRs.open_disagreements ?? matchedRs.disagreement_count ?? 0
      );
      const shiftCnt = Number(
        matchedRs.revised_count ??
          (Array.isArray(matchedRs.stance_shifts) ? matchedRs.stance_shifts.length : 0)
      );
      roundSummaryBarHtml =
        `<div class="round-disagreement-bar">` +
          `<span class="round-bar-tag">${escapeHtml(rsLabel)}</span>` +
          `<span class="round-bar-summary">${escapeHtml(
            rsText || `待决分歧 ${openDisCnt} 项 · 立场演进 ${shiftCnt} 项`
          )}</span>` +
        `</div>`;
    }
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
    resolutionAuditHtml +
    `<div class="msg-body${msg.streaming && hasContent ? " streaming" : ""}${isThinkingOnly ? " thinking-only" : ""}">` +
      bodyInnerHtml +
    `</div>` +
    roundSummaryBarHtml +
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
  const phaseEl = ph.querySelector(".thinking-phase-pill");
  const kSpec = resolveKineticVisualSpec(msg.activity, msg.phase_label);
  if (ph.dataset.kineticState !== kSpec.mode) {
    ph.dataset.kineticState = kSpec.mode;
    const oldStage = ph.querySelector(".kinetic-stage");
    if (oldStage) {
      oldStage.outerHTML = kSpec.html;
    }
  }
  if (phaseEl) phaseEl.textContent = kSpec.phaseTag;
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
        const defaultTier =
          author === "chair"
            ? "chair_directive"
            : kind === "decision"
            ? "multi_seat_consensus"
            : "provisional_suggestion";
        return {
          id: String(it.id || `wb_cli_${idx}`),
          kind,
          text: String(it.text || "").trim(),
          author,
          source_msg_id: String(it.source_msg_id || ""),
          pinned: Boolean(it.pinned),
          checked: kind === "action" ? Boolean(it.checked === true) : it.checked !== undefined ? Boolean(it.checked) : true,
          ver: Math.max(1, Number(it.ver || it.version || 1)),
          origin_tier: String(it.origin_tier || defaultTier),
          provisional_decision: Boolean(it.provisional_decision),
          adopted_by: String(it.adopted_by || ""),
          adopted_at: String(it.adopted_at || ""),
          disagreement_id: String(it.disagreement_id || ""),
          rebutted: Boolean(it.rebutted),
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
          checked: kind === "action" ? false : true,
          ver: 1,
          origin_tier: author === "chair" ? "chair_directive" : "provisional_suggestion",
          provisional_decision: false,
          adopted_by: "",
          adopted_at: "",
          disagreement_id: "",
          rebutted: false,
        });
      }
    }
  }

  wb.items = items;
  wb.absent_seats = Array.isArray(wb.absent_seats) ? wb.absent_seats : [];
  wb.absent_acknowledged = Boolean(wb.absent_acknowledged);
  wb.disagreements = Array.isArray(wb.disagreements) ? wb.disagreements : [];
  wb.abandoned_proposals = Array.isArray(wb.abandoned_proposals) ? wb.abandoned_proposals : [];
  wb.round_summaries = Array.isArray(wb.round_summaries) ? wb.round_summaries : [];
  wb.resolution_meta = wb.resolution_meta && typeof wb.resolution_meta === "object" ? wb.resolution_meta : null;
  wb.epistemic_badge = String(wb.epistemic_badge || "");
  wb.driver_family_count = Number(wb.driver_family_count ?? 0);
  wb.topic_locked = Boolean(wb.topic_locked);
  if (wb.artifact_type) {
    wb.artifact_type = String(wb.artifact_type);
  }
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

async function postWhiteboardMutation(payload, draftTextForConflict = "", options = {}) {
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
    if (options.rethrow) throw err;
    showToast(err.message || "更新会议白板失败", "err");
    return null;
  }
}

async function triggerRiskRedebate(item) {
  if (!item || !state.currentSessionId) return;
  if (state.isBusy) {
    showToast("当前研讨正在运行中，请待收敛后再发起双席再辩", "warn", 2200);
    return;
  }
  const activeSeats = Array.isArray(state.enabledAgents) && state.enabledAgents.length
    ? state.enabledAgents
    : ["carbon", "grok"];
  const challenger =
    item.author && item.author !== "chair" && activeSeats.includes(item.author)
      ? item.author
      : activeSeats.includes("grok")
      ? "grok"
      : activeSeats[0] || "grok";
  const defender =
    activeSeats.find((aid) => aid !== challenger) ||
    (challenger === "carbon" ? "grok" : "carbon");
  try {
    await apiFetch(`/api/sessions/${state.currentSessionId}/redebate`, {
      method: "POST",
      body: JSON.stringify({
        item_id: item.id,
        disagreement_id: item.disagreement_id || "",
        claim: item.text,
        challenger,
        defender,
      }),
    });
    showToast(`已启动双席 1 轮定向再辩（${AGENT_NAMES[challenger] || challenger} vs ${AGENT_NAMES[defender] || defender}）`, "ok", 2400);
  } catch (err) {
    showToast(err.message || "启动双席再辩失败", "err");
  }
}

async function adoptRiskWithGovernance(item) {
  if (!item || !state.currentSessionId) return;
  state.wbKnownItemIds.delete(`${item.id}:decision`);
  const wbNow = state.whiteboard || {};
  const heteroReady =
    Boolean(item.rebutted) &&
    (Number(wbNow.driver_family_count || 0) >= 2 || item.origin_tier === "multi_seat_consensus");

  try {
    const wb = await postWhiteboardMutation(
      {
        op: "adopt_decision",
        item_id: item.id,
        ...(heteroReady ? {} : { as_chair_directive: true, adopted_by: "chair" }),
      },
      "",
      { rethrow: true }
    );
    if (wb) {
      pulseWbTabBadge();
      showToast(
        heteroReady ? "已核验采纳至多席共识池" : "已按 [主持指定约束] 署名锁定至第一区",
        "ok",
        2000
      );
    }
  } catch (err) {
    const errReason =
      err?.payload?.reason || err?.payload?.code || err?.payload?.error_code || "";
    if (err?.status === 409 || errReason === "unverified_consensus_adoption") {
      const wb = await postWhiteboardMutation({
        op: "adopt_decision",
        item_id: item.id,
        as_chair_directive: true,
        adopted_by: "chair",
      });
      if (wb) {
        pulseWbTabBadge();
        showToast("未满足异构反驳闭环，已转为 [主持指定约束] 锁定", "ok", 2400);
      }
      return;
    }
    showToast(err.message || "采纳条目失败", "err");
  }
}

function resolveOriginPillMeta(item) {
  const tier = String(item.origin_tier || "").toLowerCase();
  if (tier === "chair_directive" || item.author === "chair") {
    const sig =
      item.adopted_by && item.adopted_by !== "chair" ? ` · ${item.adopted_by}` : "";
    return { label: `[主持指定约束]${sig}`, cls: "tier-chair" };
  }
  if (
    tier === "multi_seat_consensus" ||
    tier === "verified_heterogeneous" ||
    tier === "heterogeneous_consensus"
  ) {
    return { label: "异构交叉共识", cls: "tier-hetero" };
  }
  return { label: "初评待核验", cls: "tier-draft" };
}

function buildWbPoolItemElement(item, zoneKind, animateEnter) {
  const li = document.createElement("li");
  const isAction = zoneKind === "action";
  const isRisk = zoneKind === "risk";
  const isDecision = zoneKind === "decision";
  const isChecked = item.checked === true;

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
  const originMeta = resolveOriginPillMeta(item);
  const srcTip = item.source_msg_id
    ? `来自 ${authorMeta.name} · 点击滚回左侧原发言并聚光高亮`
    : `来源：${authorMeta.name}${item.adopted_at ? ` · ${item.adopted_at}` : ""}`;

  const heteroVerified =
    Boolean(item.rebutted) &&
    (Number(state.whiteboard?.driver_family_count || 0) >= 2 || item.origin_tier === "multi_seat_consensus");

  let actionsHtml = "";
  if (isDecision) {
    actionsHtml =
      `<button type="button" class="wb-card-act pin-btn${item.pinned ? " active" : ""}" data-wb-act="pin" title="${
        item.pinned ? "取消置顶" : "置顶锁定该约束"
      }">${item.pinned ? "已置顶" : "置顶"}</button>` +
      `<button type="button" class="wb-card-act" data-wb-act="edit" title="行内编辑">编辑</button>` +
      `<button type="button" class="wb-card-act del-btn" data-wb-act="del" title="移除条目">移除</button>`;
  } else if (isRisk) {
    actionsHtml =
      `<button type="button" class="wb-act-pill discuss-btn" data-wb-act="redebate" title="召集正反双席围绕该分歧点定向再辩 1 轮">双席再辩 1 轮</button>` +
      `<button type="button" class="wb-act-pill adopt-btn" data-wb-act="adopt" title="${
        heteroVerified ? "已完成异构核验，采纳移入多席共识池" : "未完成异构反驳闭环，以 [主持指定约束] 署名锁定至第一区"
      }">${heteroVerified ? "采纳为共识" : "主持拍板锁定"}</button>` +
      `<button type="button" class="wb-card-act" data-wb-act="abandon" title="标记为已证伪弃案并移入负面清单">弃案</button>` +
      `<button type="button" class="wb-card-act" data-wb-act="edit" title="行内编辑">编辑</button>` +
      `<button type="button" class="wb-card-act del-btn" data-wb-act="del" title="移除条目">移除</button>`;
  } else {
    actionsHtml =
      `<button type="button" class="wb-card-act" data-wb-act="edit" title="行内编辑">编辑</button>` +
      `<button type="button" class="wb-card-act" data-wb-act="abandon" title="移入弃案负面清单">弃案</button>` +
      `<button type="button" class="wb-card-act del-btn" data-wb-act="del" title="移除条目">移除</button>`;
  }

  li.innerHTML =
    `<div class="wb-pool-main">` +
      (isAction
        ? `<button type="button" class="wb-task-check${isChecked ? " checked" : ""}" data-wb-act="check" aria-pressed="${
            isChecked ? "true" : "false"
          }" title="${isChecked ? "已勾选纳入本轮执行交付范围（点击取消勾选）" : "默认未勾选（点击勾选纳入本次执行范围）"}">${
            isChecked ? '<svg viewBox="0 0 16 16" width="11" height="11" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="3.2 8.4 6.6 11.8 12.8 4.6"></polyline></svg>' : ""
          }</button>`
        : "") +
      `<div class="wb-pool-text" title="单击直接编辑内容">${escapeHtml(item.text)}</div>` +
    `</div>` +
    `<div class="wb-pool-meta">` +
      `<div class="wb-meta-left" style="display:inline-flex;align-items:center;gap:5px;flex-wrap:wrap;">` +
        `<button type="button" class="wb-seat-mini-badge ${authorMeta.cls}" data-wb-act="source" title="${escapeHtml(srcTip)}">` +
          `<span class="mini-seat-dot">${escapeHtml(authorMeta.short)}</span>` +
          `<span>${escapeHtml(authorMeta.name)}</span>` +
        `</button>` +
        `<span class="wb-origin-pill ${originMeta.cls}">${escapeHtml(originMeta.label)}</span>` +
      `</div>` +
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
        await adoptRiskWithGovernance(item);
      } else if (act === "redebate") {
        await triggerRiskRedebate(item);
      } else if (act === "abandon") {
        const wb = await postWhiteboardMutation({
          op: "abandon_item",
          item_id: item.id,
          reason: "会议白板人工证伪归档",
        });
        if (wb) showToast("已隔离至「弃案与证伪方案」负面清单", "info", 2000);
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
      `<textarea id="wb-editor-${escapeHtml(item.id)}" class="wb-edit-input" rows="2">${escapeHtml(item.text)}</textarea>` +
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
  if (state.topicLocked || state.stage !== "idle" || state.messages.size > 0) {
    showToast("议题在开局后已锁定不可篡改，请通过底部追问或插话补充新约束", "warn", 2400);
    return;
  }
  const topicBox = el("wbTopicText");
  if (!topicBox || topicBox.querySelector("#wbTopicEditInput")) return;
  const currentFullTopic = state.whiteboard?.topic || state.topic || "";
  topicBox.innerHTML =
    `<div class="wb-edit-box">` +
      `<textarea id="wbTopicEditInput" class="wb-edit-input wb-topic-edit-input" rows="2" placeholder="输入开局前的会议完整议题…">${escapeHtml(
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

function computeActiveDriverFamilyCount() {
  const wbCount = Number(state.whiteboard?.driver_family_count || 0);
  if (wbCount > 0) return wbCount;
  const sysAgents = state.system?.agents || {};
  const families = new Set();
  for (const aid of state.enabledAgents || []) {
    const st = state.seatStates?.[aid] || {};
    const info = sysAgents[aid] || {};
    if (st.binary_ready || info.binary_detected) {
      const fk = st.driver_family_key || info.driver_family_key || info.binary_realpath || info.binary_path || st.effective_driver || info.effective_driver || aid;
      families.add(String(fk));
    }
  }
  return families.size;
}

function renderWhiteboard(rawWb, forceRender = false, isInitialSnapshot = false) {
  const wb = normalizeClientWhiteboard(rawWb);
  state.whiteboard = wb;
  state.topicLocked = Boolean(wb.topic_locked || state.stage !== "idle" || state.messages.size > 0);
  if (wb.artifact_type) {
    state.artifactType = wb.artifact_type;
  }

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
  const checkedActionCount = actionItems.filter((it) => it.checked === true).length;
  const abandonedItems = Array.isArray(wb.abandoned_proposals) ? wb.abandoned_proposals : [];
  const absentSeats = Array.isArray(wb.absent_seats) ? wb.absent_seats : [];

  const totalCount = allItems.length;
  if (el("wbCountBadge")) {
    el("wbCountBadge").textContent = String(totalCount);
  }
  if (!isInitialSnapshot && totalCount > state.lastWbTotalCount) {
    pulseWbTabBadge();
  }
  state.lastWbTotalCount = totalCount;

  // 1. 认知防伪横幅 (#wbEpistemicBanner)
  const enabledCnt = (state.enabledAgents || []).length;
  const familyCnt = computeActiveDriverFamilyCount();
  const epistemicBadge =
    wb.epistemic_badge ||
    (enabledCnt <= 1
      ? "[单席推演草稿]"
      : familyCnt < 2
      ? "[同源模型多视角推演 · 误差相关]"
      : "[异构多引擎独立推演]");
  const epBanner = el("wbEpistemicBanner");
  if (epBanner) {
    const hasMeetingContext = Boolean(state.topic || wb.topic || allItems.length || state.messages.size > 0);
    epBanner.classList.toggle("hidden", !hasMeetingContext);
    epBanner.classList.toggle("is-warn", enabledCnt <= 1 || familyCnt < 2);
    epBanner.classList.toggle("is-verified", enabledCnt >= 2 && familyCnt >= 2);
    epBanner.textContent =
      enabledCnt <= 1
        ? `${epistemicBadge} 当前仅单席推演，白板结论仅作草稿或主持指定约束`
        : familyCnt < 2
        ? `${epistemicBadge} 参会席位共享同一底层驱动，未交叉核验项需主持拍板锁定`
        : `${epistemicBadge} 跨驱动族首轮盲评隔离与交叉反驳已启用`;
  }

  // 2. 未参评/缺席席位披露卡 (#wbCardAbsent / #wbAbsentCount / #wbAbsentList / #wbAckAbsentBtn)
  const absentCard = el("wbCardAbsent");
  const absentCountEl = el("wbAbsentCount");
  const absentListEl = el("wbAbsentList");
  const ackAbsentBtn = el("wbAckAbsentBtn");
  if (absentCard) {
    absentCard.classList.toggle("hidden", absentSeats.length === 0);
  }
  if (absentCountEl) {
    absentCountEl.textContent = String(absentSeats.length);
  }
  if (absentListEl) {
    absentListEl.innerHTML = "";
    for (const ab of absentSeats) {
      const aid = typeof ab === "string" ? ab : ab?.agent_id || ab?.seat || "";
      const seatName = (typeof ab === "object" && ab?.name) || AGENT_NAMES[aid] || aid || "席位";
      const reason =
        (typeof ab === "object" && (ab?.reason || ab?.error)) || "本轮异常中断或超时缺席";
      const li = document.createElement("li");
      li.className = "wb-absent-item";
      li.innerHTML =
        `<span><strong>${escapeHtml(seatName)}</strong> · ${escapeHtml(reason)}</span>` +
        `<span>${wb.absent_acknowledged || ab?.acknowledged ? "已确认" : "待确认"}</span>`;
      absentListEl.appendChild(li);
    }
  }
  if (ackAbsentBtn) {
    const allAcked = Boolean(
      wb.absent_acknowledged ||
        (absentSeats.length > 0 && absentSeats.every((x) => typeof x === "object" && x?.acknowledged))
    );
    ackAbsentBtn.classList.toggle("hidden", absentSeats.length === 0 || allAcked);
  }

  // 3. 同步执行终端日志、Diff 与回滚按钮
  if (Array.isArray(wb.exec_logs) && wb.exec_logs.length > 0 && el("astraTermLogs")) {
    el("astraTermLogs").textContent = wb.exec_logs.join("\n");
    el("astraTermLogs").scrollTop = el("astraTermLogs").scrollHeight;
  } else if (!state.isBusy && el("astraTermLogs") && (!wb.exec_logs || !wb.exec_logs.length) && !wb.exec_summary) {
    el("astraTermLogs").textContent = "尚未触发执行任务";
  }
  if (el("astraDiffView")) {
    el("astraDiffView").innerHTML = renderDiffHtml(wb.exec_diff || "");
  }
  state.recoveryRequired = Boolean(wb.recovery_required || state.recoveryRequired);
  const verifyFailed = Boolean(
    wb.exec_summary && (String(wb.exec_summary).includes("验证未通过") || String(wb.exec_summary).includes("验证失败"))
  );
  state.postExecVerifyFailed = verifyFailed;
  const rbBtn = el("rollbackExecBtn");
  if (rbBtn) {
    rbBtn.classList.toggle("hidden", !wb.can_rollback);
    rbBtn.classList.toggle("highlight-urgent", Boolean(wb.can_rollback && (verifyFailed || state.rollbackConflicts.length)));
  }
  el("ackSnapshotBtn")?.classList.toggle("hidden", !wb.can_rollback);
  renderExecGuardBanner();

  // 当存在聚焦中的 .wb-edit-input 时，豁免后台 SSE 全量重绘覆盖用户正在输入的草稿
  const activeEl = document.activeElement;
  if (
    !forceRender &&
    activeEl &&
    (activeEl.classList.contains("wb-edit-input") || activeEl.id === "wbTopicEditInput")
  ) {
    return;
  }

  // 4. 议题与锁定徽章 (#wbTopicLockBadge)
  const lockBadge = el("wbTopicLockBadge");
  if (lockBadge) {
    lockBadge.classList.toggle("hidden", !state.topicLocked);
  }
  const topicEl = el("wbTopicText");
  if (topicEl) {
    const fullTopic = wb.topic || state.topic || "";
    topicEl.textContent = fullTopic || "未设置议题（开局前单击可预设，发起研讨后自动锁定）";
    topicEl.classList.toggle("editable", !state.topicLocked);
    topicEl.title = state.topicLocked
      ? "会议已开局锁定议题，请通过追问或插话补充新约束"
      : fullTopic
      ? "单击内联编辑开局议题"
      : "单击设置初始议题";
  }

  // 5. 动态分区标题 (#wbDecisionZoneTitle / #wbActionZoneTitle)
  const decTitleEl = el("wbDecisionZoneTitle");
  if (decTitleEl) {
    decTitleEl.textContent =
      enabledCnt <= 1
        ? "主持指定约束"
        : familyCnt < 2
        ? "已锁定结论与主持约束"
        : "已确认共识与约束";
  }
  const actTitleEl = el("wbActionZoneTitle");
  if (actTitleEl) {
    const artTitleMap = {
      code_patch: "待勾选执行任务清单",
      decision_matrix: "方案对比与决策行动项",
      ux_checklist: "体验走查整改清单",
      doc_export: "排查核验与文稿定稿项",
    };
    actTitleEl.textContent = artTitleMap[state.artifactType] || "待勾选执行任务清单";
  }

  if (el("wbDecisionCount")) el("wbDecisionCount").textContent = String(decisionItems.length);
  if (el("wbRiskCount")) el("wbRiskCount").textContent = String(riskItems.length);
  if (el("wbActionCount")) {
    el("wbActionCount").textContent = `${checkedActionCount}/${actionItems.length} 已勾选`;
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
    "主持硬约束与经核验锁定的结论将在此置顶，后续轮次严格遵循"
  );
  renderZoneList(
    "wbRiskList",
    riskItems,
    "risk",
    "可对分歧项发起「双席再辩 1 轮」、「主持拍板锁定」或移入「弃案」"
  );
  renderZoneList(
    "wbActionList",
    actionItems,
    "action",
    "新增任务默认不勾选；请显式勾选需在本轮交付的任务项后再触发执行"
  );

  // 6. 弃案与证伪淘汰方案负面清单 (#wbCardAbandoned / #wbAbandonedCount / #wbAbandonedList)
  const abCard = el("wbCardAbandoned");
  const abCount = el("wbAbandonedCount");
  const abList = el("wbAbandonedList");
  if (abCard) {
    abCard.classList.toggle("hidden", abandonedItems.length === 0);
  }
  if (abCount) {
    abCount.textContent = String(abandonedItems.length);
  }
  if (abList) {
    abList.innerHTML = "";
    abandonedItems.forEach((ab, idx) => {
      const abId = (typeof ab === "object" && ab?.id) || `ab_${idx}`;
      const abText =
        typeof ab === "string"
          ? ab
          : ab?.text || ab?.proposal || ab?.summary || "";
      const abReason = typeof ab === "object" ? ab?.reason || "" : "";
      const abReplaced = typeof ab === "object" ? ab?.replaced_by || "" : "";
      const li = document.createElement("li");
      li.className = "wb-abandoned-item";
      li.innerHTML =
        `<div>` +
          `<span class="wb-abandoned-title">${escapeHtml(abText)}</span>` +
          (abReason || abReplaced
            ? `<span class="wb-abandoned-reason">${escapeHtml(
                [abReason ? `原因：${abReason}` : "", abReplaced ? `替代终态：${abReplaced}` : ""]
                  .filter(Boolean)
                  .join(" · ")
              )}</span>`
            : "") +
        `</div>` +
        `<button type="button" class="wb-card-act del-btn" title="从负面清单移除">移除</button>`;
      li.querySelector("button")?.addEventListener("click", async (e) => {
        e.stopPropagation();
        await postWhiteboardMutation({
          op: "remove_abandoned",
          abandoned_id: abId,
          item_id: abId,
        });
      });
      abList.appendChild(li);
    });
  }

  // 7. 按 state.artifactType 自适应切换执行终端与文稿导出栏，并落实零勾选/空纪要门禁
  const isDocArtifact = Boolean(state.artifactType && state.artifactType !== "code_patch");
  const adaptBar = el("wbAdaptiveExportBar");
  if (adaptBar) {
    adaptBar.classList.toggle("hidden", !isDocArtifact);
  }

  const jumpBtn = el("wbToExecBtn");
  if (jumpBtn) {
    const execName = AGENT_NAMES[state.executorAgent] || "工程师";
    jumpBtn.classList.toggle("hidden", isDocArtifact);
    jumpBtn.disabled = checkedActionCount < 1;
    jumpBtn.textContent =
      checkedActionCount < 1
        ? `请先勾选至少 1 项待执行任务 (0/${actionItems.length})`
        : `前往执行终端由 ${execName} 交付已选任务 (${checkedActionCount}/${actionItems.length})`;
  }

  const canExport = hasExportableSessionContent();
  ["copyMdBtn", "exportMdBtn", "dedupeWbBtn", "wbQuickCopyArtifactBtn", "wbQuickExportArtifactBtn"].forEach((btnId) => {
    const b = el(btnId);
    if (b) b.disabled = !canExport;
  });

  renderExecutorControls();
  syncAdaptiveRightCollapse();
}

/* ==================== 会议纪要 Markdown 规范排版导出（含防伪标记、缺席账本与弃案负面清单） ==================== */

function buildMinutesMarkdown() {
  const wb = normalizeClientWhiteboard(state.whiteboard || {});
  const items = wb.items || [];
  const decisions = items.filter((i) => i.kind === "decision");
  const risks = items.filter((i) => i.kind === "risk");
  const actions = items.filter((i) => i.kind === "action");
  const abandoned = Array.isArray(wb.abandoned_proposals) ? wb.abandoned_proposals : [];
  const absentSeats = Array.isArray(wb.absent_seats) ? wb.absent_seats : [];
  const title = wb.topic_title || state.topic || "AI圆桌会议纪要";
  const modeSpec = COLLAB_MODES[state.collabMode] || COLLAB_MODES.deep_deliberation;
  const ws = effectiveWorkspacePath() || "不绑定项目 · 纯研讨";
  const enabledCnt = (state.enabledAgents || []).length;
  const familyCnt = computeActiveDriverFamilyCount();
  const epBadge =
    wb.epistemic_badge ||
    (enabledCnt <= 1
      ? "[单席推演草稿]"
      : familyCnt < 2
      ? "[同源模型多视角推演 · 误差相关]"
      : "[异构多引擎独立推演]");

  const absentSection = absentSeats.length
    ? [
        "",
        "## 未参评/缺席席位",
        ...absentSeats.map((ab) => {
          const aid = typeof ab === "string" ? ab : ab?.agent_id || ab?.seat || "";
          const nm = (typeof ab === "object" && ab?.name) || AGENT_NAMES[aid] || aid;
          const rs = (typeof ab === "object" && (ab?.reason || ab?.error)) || "异常缺席";
          return `- **${nm}**：${rs}`;
        }),
      ]
    : [];

  const lines = [
    `# ${title}`,
    "",
    `- **认知防伪标记**：${epBadge}`,
    `- **讨论策略**：${modeSpec.label}（${modeSpec.hint}）`,
    `- **项目工作区**：\`${ws}\``,
    `- **会议状态**：${wb.consensus_status || STAGE_LABELS[state.stage] || "待命"}`,
    wb.topic && wb.topic !== title ? `- **完整议题**：${wb.topic}` : "",
    ...absentSection,
    "",
    "## 一、已确认共识与主持约束",
    ...(decisions.length
      ? decisions.map((it) => {
          const isChairDir = it.origin_tier === "chair_directive" || it.author === "chair";
          const prefix = isChairDir
            ? "**[主持指定约束]** "
            : it.pinned
            ? "**[置顶共识]** "
            : "";
          return `- ${prefix}${it.text} *(${AUTHOR_BADGE_META[it.author]?.name || it.author})*`;
        })
      : ["- 暂无已确认共识记录"]),
    "",
    "## 二、待决分歧与风险边界",
    ...(risks.length
      ? risks.map((it) => `- ${it.text} *(${AUTHOR_BADGE_META[it.author]?.name || it.author})*`)
      : ["- 暂无待决争议或风险项"]),
    "",
    "## 三、待执行交付任务清单",
    ...(actions.length
      ? actions.map(
          (it) =>
            `- [${it.checked === true ? "x" : " "}] ${it.text} *(${
              AUTHOR_BADGE_META[it.author]?.name || it.author
            })*`
        )
      : ["- [ ] 暂无待执行任务项"]),
    "",
    "## 四、已确认放弃与证伪淘汰方案",
    ...(abandoned.length
      ? abandoned.map((ab) => {
          const txt = typeof ab === "string" ? ab : ab?.text || ab?.proposal || ab?.summary || "";
          const rsn = typeof ab === "object" && ab?.reason ? ` —— 弃用原因：${ab.reason}` : "";
          const rep = typeof ab === "object" && ab?.replaced_by ? `（替代终态：${ab.replaced_by}）` : "";
          return `- ~~${txt}~~${rsn}${rep}`;
        })
      : ["- 无已证伪或放弃的历史方案"]),
    "",
    "## 五、完整研讨记录",
    "",
  ].filter((x) => x !== "");

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
  if (!state.currentSessionId) return;
  if (!hasExportableSessionContent()) {
    showToast("当前为空白新会议，暂无可导出的会议纪要", "warn", 2200);
    return;
  }
  try {
    const res = await fetch(`/api/sessions/${state.currentSessionId}/export`, {
      method: "GET",
      headers: authState.token ? { "X-Roundtable-Token": authState.token } : {},
    });
    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      throw new Error(errData.error || `导出失败 (${res.status})`);
    }
    const blob = await res.blob();
    const encodedFn = res.headers.get("X-Roundtable-Filename") || "";
    const decodedFn = encodedFn ? decodeURIComponent(encodedFn) : "";
    const fallbackName =
      (state.whiteboard?.topic_title || state.topic || "AI圆桌纪要")
        .replace(/[\\/:*?"<>|\s]+/g, "_")
        .slice(0, 36) + ".md";
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = decodedFn || fallbackName;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1200);
    showToast("已从服务端内存生成并下载 .md 会议纪要", "ok", 2400);
  } catch (err) {
    showToast(err.message || "导出会议纪要失败", "err");
  }
}

function resolveClientEpistemicMeta() {
  const wbMode = state.whiteboard?.epistemic_mode || "";
  const wbBadge = state.whiteboard?.epistemic_badge || "";
  const enabledCount = state.enabledAgents.length || 1;
  if (enabledCount <= 1 || wbMode === "solo_draft") {
    return {
      mode: "solo_draft",
      badge: "[单席推演草稿]",
      headerText: "[单席推演草稿]",
      bannerText: "[单席推演草稿] 当前仅启用 1 席独立推演，未经异席反向审计，所有结论须由主持人审阅确认。",
    };
  }
  const agents = state.system?.agents || {};
  const fams = new Set();
  state.enabledAgents.forEach((aid) => {
    const st = state.seatStates[aid] || {};
    const inf = agents[aid] || {};
    if (st.binary_ready || inf.binary_detected) {
      const fk = st.driver_family_key || inf.driver_family_key || st.effective_driver || inf.effective_driver;
      if (fk) fams.add(fk);
    }
  });
  if (wbMode === "heterogeneous" || fams.size >= 2) {
    return {
      mode: "heterogeneous",
      badge: wbBadge || `多源异构独立交叉核验（${Math.max(2, fams.size)} 独立引擎）`,
      headerText: `异构独立 · ${Math.max(2, fams.size)} 引擎`,
      bannerText: `多源异构独立交叉核验（${Math.max(2, fams.size)} 个独立驱动族）：首轮盲评隔离 + 交叉质询闭环准入已启用。`,
    };
  }
  return {
    mode: "homogeneous_warning",
    badge: "[同源模型多视角推演 · 误差相关]",
    headerText: "[同源模型多视角推演 · 误差相关]",
    bannerText: "[同源模型多视角推演 · 误差相关] 当前参会席位共用同一底层引擎，视角分化受同源盲区制约，禁止自动升格为多源共识。",
  };
}

function renderStageAndHeader() {
  const stage = state.stage || "idle";
  const hasTopic = Boolean(state.topic);
  const isIdleEmpty = stage === "idle" && !hasTopic && state.messages.size === 0 && !state.isBusy;

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

  const epiEl = el("headerEpistemicBadge");
  if (epiEl) {
    const epi = resolveClientEpistemicMeta();
    epiEl.classList.remove("hidden", "epistemic-warn", "epistemic-solo", "epistemic-hetero");
    epiEl.textContent = epi.headerText;
    epiEl.title = epi.bannerText;
    if (epi.mode === "heterogeneous") epiEl.classList.add("epistemic-hetero");
    else if (epi.mode === "solo_draft") epiEl.classList.add("epistemic-solo");
    else epiEl.classList.add("epistemic-warn");
  }

  // 首屏空态收起顶栏装饰性四阶段条，进入会议后恢复展示
  const stepperEl = el("stageStepper");
  if (stepperEl) {
    stepperEl.classList.toggle("hidden", isIdleEmpty);
  }

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
  document.querySelectorAll("#stageStepper .step-line").forEach((line) => {
    const beforeKey = line.dataset.lineBefore;
    const targetIdx = stepOrder.indexOf(beforeKey);
    line.classList.toggle("is-done", activeStepIdx >= targetIdx && targetIdx > 0);
    line.classList.toggle("is-flowing", state.isBusy && activeStepIdx >= 0 && targetIdx === activeStepIdx);
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
      const ws = effectiveWorkspacePath();
      topicInp.placeholder = ws
        ? "输入议题开启研讨，支持 @文件:起始-结束行 切片引用或拖拽截图/文档"
        : "输入议题开启纯研讨（如需引用本地源码或写盘预演，可点击顶栏绑定项目）";
    }
  }

  renderWorkspaceBadges();
  renderQuickCueButtons();
  renderExecutorControls();
}

function renderWorkspaceBadges() {
  const ws = effectiveWorkspacePath();
  const folderName = ws ? ws.split(/[\\/]/).filter(Boolean).pop() || ws : "";

  const headerChip = el("headerWsChip");
  const headerName = el("headerWsName");
  const unbindBtn = el("headerUnbindWsBtn");
  if (headerChip && headerName) {
    headerChip.classList.toggle("ws-bound", Boolean(ws));
    headerChip.classList.toggle("ws-unbound", !ws);
    headerName.textContent = folderName ? `项目：${folderName}` : "不绑定项目 · 纯研讨";
    headerChip.title = ws ? `当前绑定本地工作区：${ws}（点击切换目录）` : "当前为纯研讨免绑仓模式，点击绑定本地项目工作区";
  }
  if (unbindBtn) {
    unbindBtn.classList.toggle("hidden", !ws || state.isBusy || state.stage === "executing");
  }

  const wsName = el("workspaceName");
  const wsBadge = el("workspaceBadge");
  if (wsName) wsName.textContent = folderName || "不绑定项目 · 纯研讨";
  if (wsBadge) {
    wsBadge.textContent = ws || "未绑定本地目录（纯研讨模式）";
    wsBadge.title = ws;
  }
}

function renderSeatCard(agentId) {
  const seatEl = el(`seat-${agentId}`);
  if (!seatEl) return;

  const st = state.seatStates[agentId] || {};
  const status = st.status || "idle";
  const sysInfo = state.system?.agents?.[agentId] || {};
  const enabled = state.enabledAgents.includes(agentId);
  const isSolo = state.enabledAgents.length === 1 && state.enabledAgents[0] === agentId;
  const isExtraSeat = !CORE_TRIAD_SEATS.includes(agentId);
  const unmounted = isExtraSeat && !enabled && !state.showAllSeatsInRing && status === "idle";
  const personaKey = state.seatPersonas[agentId] || DEFAULT_SEAT_PERSONAS[agentId];
  const pSpec = getPersonaSpec(personaKey, agentId);
  const ready = Boolean(st.binary_ready ?? sysInfo.binary_detected);

  seatEl.className = [
    "seat-card",
    `seat-${agentId}`,
    `status-${status}`,
    !enabled ? "seat-disabled" : "",
    isSolo ? "seat-is-solo" : "",
    unmounted ? "seat-unmounted" : "",
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
    let badgeText = st.badge || (ready ? "已就绪" : "未检测到 CLI");
    if (!enabled && status === "idle") {
      badgeText = "暂停参会";
    } else if (status === "idle" && st.elapsed_ms > 0 && badgeText && !badgeText.includes("s")) {
      badgeText = `${badgeText} · ${(st.elapsed_ms / 1000).toFixed(1)}s`;
    }
    badgeEl.textContent = badgeText;
  }

  // 中层协议透出：对抗立场标签 · 真实模型名 · 提供方 · [异构独立 / 同源复用]
  const teleEl = el(`seat-tele-${agentId}`);
  if (teleEl) {
    const model = st.effective_model || sysInfo.effective_model || "";
    const provider = st.provider_name || sysInfo.provider_name || "";
    let indep = st.independence_label || sysInfo.independence_label || "";
    if (!indep && ready) {
      if (isSolo) indep = "单席专注";
      else indep = st.shared_cli_group || sysInfo.shared_fallback ? "同源复用" : "异构独立";
    }
    if (ready) {
      const segs = [pSpec.label, model || DRIVER_LABELS[sysInfo.effective_driver] || "CLI", provider, indep ? `[${indep}]` : ""].filter(Boolean);
      teleEl.textContent = segs.join(" · ");
      teleEl.classList.toggle("tele-homog", indep === "同源复用");
      teleEl.classList.toggle("tele-hetero", indep === "异构独立");
    } else {
      teleEl.textContent = `${pSpec.label} · 未检测到本地驱动`;
      teleEl.classList.remove("tele-homog", "tele-hetero");
    }
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
  const countLbl = el("ringSeatCountLabel");
  if (countLbl) {
    countLbl.textContent = `${state.enabledAgents.length} 席参会`;
  }
  // 同步底部 @点名胶囊（仅展示已启用席位，界面清爽不拥挤）
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
      const mentionTargets = state.enabledAgents.length ? state.enabledAgents : CORE_TRIAD_SEATS;
      label.textContent = "定向点名：";
      wrap.innerHTML = mentionTargets
        .map(
          (aid) =>
            `<button type="button" class="mention-btn" data-mention-seat="${aid}" data-mention="@${AGENT_NAMES[aid]} " title="点名 ${AGENT_NAMES[aid]} 回应">@${AGENT_NAMES[aid]}</button>`
        )
        .join("");
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
  const checkedCnt = getCheckedActionCount();
  const isCodePatch = (state.artifactType || "code_patch") === "code_patch";

  const termTabBtn = document.querySelector('.wb-tab[data-tab="terminal"]');
  if (termTabBtn) {
    termTabBtn.classList.toggle("hidden", !isCodePatch && state.stage !== "executing");
  }
  if (!isCodePatch && state.activeTab === "terminal" && state.stage !== "executing") {
    switchWorkbenchTab("whiteboard");
  }

  const segWrap = el("executorSegmented");
  if (segWrap) {
    const segSeats = Array.from(new Set([...(state.enabledAgents.length ? state.enabledAgents : CORE_TRIAD_SEATS), execAid]));
    segWrap.innerHTML = segSeats
      .map(
        (aid) =>
          `<button type="button" class="seg-btn${aid === execAid ? " active" : ""}" data-exec-agent="${aid}" title="由 ${escapeHtml(
            AGENT_NAMES[aid] || aid
          )} 承接执行交付">${escapeHtml(AGENT_NAMES[aid] || aid)}</button>`
      )
      .join("");
    segWrap.querySelectorAll("[data-exec-agent]").forEach((btn) => {
      btn.onclick = async () => {
        const aid = btn.dataset.execAgent;
        if (!AGENT_ORDER.includes(aid)) return;
        state.executorAgent = aid;
        renderExecutorControls();
        renderWhiteboard(state.whiteboard || {}, true, true);
        if (state.currentSessionId) {
          await persistSessionSeatsPatch({ executor_agent: aid });
        }
      };
    });
  }

  document.querySelectorAll("#sandboxSegmented [data-write-mode]").forEach((btn) => {
    const isWriteBtn = btn.dataset.writeMode === "write";
    btn.classList.toggle("active", isWriteBtn === allowWrite);
  });

  el("execWriteSafetyBanner")?.classList.toggle("hidden", !(allowWrite && ws));

  const execCueBtn = el("executeBtn");
  if (execCueBtn) {
    execCueBtn.classList.toggle("hidden", !isCodePatch);
    execCueBtn.disabled = checkedCnt < 1 || state.stage === "executing" || state.recoveryRequired;
    execCueBtn.textContent = checkedCnt < 1 ? `请先勾选白板任务` : `交由 ${execName} 执行 (${checkedCnt}) →`;
  }
  if (el("runExecFromTabBtn")) {
    el("runExecFromTabBtn").textContent =
      state.stage === "executing"
        ? `${execName} 执行中…`
        : checkedCnt < 1
        ? "尚无已勾选任务（请回白板勾选）"
        : `启动 ${execName} 执行 (${checkedCnt} 项)`;
    el("runExecFromTabBtn").disabled = checkedCnt < 1 || state.stage === "executing" || state.recoveryRequired;
  }
  el("stopExecFromTabBtn")?.classList.toggle("hidden", state.stage !== "executing");
  if (el("termTargetTitle")) {
    el("termTargetTitle").textContent = `${execName} · 执行终端`;
  }

  const descEl = el("execModeDesc");
  if (descEl) {
    if (!ws) {
      descEl.classList.remove("warn");
      descEl.textContent = "当前未绑定本地项目：点击执行将依据白板已锁定约束与已勾选任务输出《工程实施方案报告》。";
    } else if (allowWrite) {
      descEl.classList.add("warn");
      descEl.textContent =
        `写入模式（${ws}）：写前将获取跨进程排他锁并建立写前字节快照，验证异常支持一键回滚。`;
    } else {
      descEl.classList.remove("warn");
      descEl.textContent = `只读预演模式（${ws}）：依据白板已锁定约束与已勾选任务生成代码补丁预览，不改动本地文件。`;
    }
  }
}

/* ==================== 本地 CLI 引擎状态与连通实测 ==================== */

function renderSystemStatus(sys) {
  if (!sys) return;
  state.system = sys;
  state.pacingMode = sys.pacing_mode || "standard";
  state.idleTimeoutSec = Number(sys.idle_timeout_sec ?? 300);
  state.turnTimeoutSec = Number(sys.turn_timeout_sec ?? 600);
  state.maxRefChars = Number(sys.max_ref_chars ?? 120000);
  state.postExecVerifyCmd = String(sys.post_exec_verify_cmd || "");
  if (sys.boot_id) authState.bootId = sys.boot_id;
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

  if (el("diagRuntimeCodeRoot")) {
    el("diagRuntimeCodeRoot").textContent = sys.runtime_code_root || "未知";
  }
  if (el("diagBootId")) {
    el("diagBootId").textContent = authState.bootId || sys.boot_id || "未知";
  }
  if (el("diagSqliteBadge")) {
    const jMode = String(sys.sqlite_journal_mode || "wal").toUpperCase();
    el("diagSqliteBadge").textContent = `SQLite ${jMode}`;
  }
  if (el("diagIsolationSpec")) {
    const conc = state.singleCliConcurrency || 3;
    el("diagIsolationSpec").textContent = `独立 TMPDIR 隔离 · ${conc} 路并发通道 · 进程组围栏收割`;
  }

  const agents = sys.agents || {};
  const activeSeatScope = state.enabledAgents.length ? state.enabledAgents : CORE_TRIAD_SEATS;
  let readyCount = 0;
  const distinctFamilies = new Set();
  activeSeatScope.forEach((aid) => {
    if (agents[aid]?.binary_detected) {
      readyCount += 1;
      const fk = state.seatStates[aid]?.driver_family_key || agents[aid]?.driver_family_key || agents[aid]?.effective_driver;
      if (fk) distinctFamilies.add(fk);
    }
  });
  const isHomogeneousMulti = activeSeatScope.length > 1 && distinctFamilies.size < 2;

  const heteroBtn = el("ringHeterogeneousBtn");
  if (heteroBtn) {
    const canRec = Boolean(sys.can_recommend_heterogeneous) && activeSeatScope.length > 1 && isHomogeneousMulti && !state.isBusy;
    heteroBtn.classList.toggle("hidden", !canRec);
  }

  const summaryBar = el("readySummaryBar");
  if (summaryBar) {
    summaryBar.classList.remove("all-ready", "warn-ready");
    if (readyCount === activeSeatScope.length && !isHomogeneousMulti && activeSeatScope.length > 1) {
      summaryBar.classList.add("all-ready");
      summaryBar.textContent = `${readyCount} 席异构独立模型已就绪 · 支持真多源独立立论与交叉证伪`;
    } else if (readyCount >= 1) {
      summaryBar.classList.add("all-ready");
      summaryBar.textContent =
        activeSeatScope.length === 1
          ? `单席专注模式已就绪 · 独立推演与边界自检`
          : `本地模型已就绪（当前启用 ${activeSeatScope.length} 席 · 同源多视角推演）`;
    } else {
      summaryBar.classList.add("warn-ready");
      summaryBar.textContent = "未检测到可用本地 CLI · 请打开左下角「设置中心」配置驱动路径";
    }
  }

  const cardsBox = el("cliEngineCards");
  if (cardsBox) {
    cardsBox.innerHTML = "";
    for (const aid of AGENT_ORDER) {
      const info = agents[aid] || {};
      const ready = Boolean(info.binary_detected);
      const pingRes = state.cliTestResults[aid];
      const latMs = state.pingLatencyBySeat[aid];
      const isExpanded = state.expandedCliCard === aid;
      const isSeatEnabled = state.enabledAgents.includes(aid);

      let pillCls = ready ? "driver-pill live" : "driver-pill missing";
      let pillTxt = ready ? (info.independence_label || (info.shared_fallback ? "同源复用" : "已就绪")) : "未安装";
      if (latMs > 0 && pingRes?.ok) {
        pillCls =
          latMs < 2800
            ? "driver-pill latency-fast"
            : latMs < 7500
            ? "driver-pill latency-normal"
            : "driver-pill latency-slow";
        pillTxt = `${(latMs / 1000).toFixed(1)}s`;
      }

      if (isSeatEnabled || CORE_TRIAD_SEATS.includes(aid)) {
        const card = document.createElement("div");
        card.className = `cli-card${isExpanded ? " expanded" : ""}`;
        const provPart = info.provider_name ? `${info.provider_name} · ` : "";
        const drvText = `${provPart}${DRIVER_LABELS[info.effective_driver] || info.effective_driver || "CLI"} · ${
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
      }

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

async function switchCurrentSessionWorkspace(targetPath) {
  const clean = String(targetPath ?? "").trim();
  if (!clean) {
    if (state.currentSessionId) {
      const wsRes = await apiFetch(`/api/sessions/${state.currentSessionId}/workspace`, {
        method: "POST",
        body: JSON.stringify({ workspace_dir: "" }),
      });
      state.sessionWorkspaceDir = "";
      state.workspaceBound = wsRes.workspace_bound ?? false;
      state.workspaceIsGit = false;
    } else {
      state.sessionWorkspaceDir = "";
      state.workspaceBound = false;
      state.workspaceIsGit = false;
    }
    if (el("cfgWorkspaceDir")) el("cfgWorkspaceDir").value = "";
    state.attachedFilesCache.clear();
    refreshAttachedFilesBar();
    renderWorkspaceBadges();
    renderStageAndHeader();
    if (state.whiteboard) renderWhiteboard(state.whiteboard, true, false);
    return true;
  }
  if (state.currentSessionId) {
    const wsRes = await apiFetch(`/api/sessions/${state.currentSessionId}/workspace`, {
      method: "POST",
      body: JSON.stringify({ workspace_dir: clean }),
    });
    state.sessionWorkspaceDir = wsRes.workspace_dir || clean;
    state.workspaceBound = wsRes.workspace_bound ?? true;
    state.workspaceIsGit = Boolean(wsRes.workspace_is_git);
  }
  const cfgRes = await apiFetch("/api/config", {
    method: "POST",
    body: JSON.stringify({ workspace_dir: clean }),
  });
  if (cfgRes.system) renderSystemStatus(cfgRes.system);
  if (el("cfgWorkspaceDir")) el("cfgWorkspaceDir").value = clean;
  state.attachedFilesCache.clear();
  refreshAttachedFilesBar();
  renderWorkspaceBadges();
  renderStageAndHeader();
  if (state.whiteboard) renderWhiteboard(state.whiteboard, true, false);
  return true;
}

async function pickWorkspaceFolder() {
  const sessionId = state.currentSessionId;
  try {
    const native = window.webkit?.messageHandlers?.roundtableNative || window.roundtableDesktop;
    if (native) {
      const chosenPath = await native.postMessage({ action: "pickFolder" });
      if (!chosenPath || sessionId !== state.currentSessionId) return;
      await switchCurrentSessionWorkspace(chosenPath);
      showToast(`已绑定本地工作区：${chosenPath}`, "ok", 2200);
      return;
    }

    // 浏览器开发模式：调用系统目录弹窗（严禁传 direct_path），随后绑定至当前空闲会话
    const res = await apiFetch("/api/system/pick-folder", {
      method: "POST",
      body: JSON.stringify({}),
    });
    if (res.cancelled || !res.ok || !res.path || sessionId !== state.currentSessionId) return;
    if (res.system) renderSystemStatus(res.system);
    if (state.currentSessionId && !state.isBusy && state.stage !== "executing") {
      await switchCurrentSessionWorkspace(res.path);
    }
    showToast(`已绑定本地工作区：${res.path}`, "ok", 2200);
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

async function fetchRecoveryPlanIfNeeded() {
  if (!state.currentSessionId || !state.recoveryRequired) {
    state.recoveryPlan = null;
    renderExecGuardBanner();
    return;
  }
  try {
    const res = await apiFetch(`/api/sessions/${state.currentSessionId}/recovery`);
    state.recoveryPlan = res.recovery || null;
  } catch {
    state.recoveryPlan = null;
  }
  renderExecGuardBanner();
}

function renderExecGuardBanner() {
  const banner = el("execGuardBanner");
  if (!banner) return;

  if (state.recoveryRequired) {
    const plan = state.recoveryPlan || {};
    const modList = Array.isArray(plan.modified_or_deleted) ? plan.modified_or_deleted : [];
    const newFiles = Array.isArray(plan.untracked_new_files) ? plan.untracked_new_files : [];
    const lines = [
      ...modList.map((it) => `[待还原修改] ${escapeHtml(it.path)}  (现态: ${escapeHtml(String(it.current_sha256 || "").slice(0, 12))}…)`),
      ...newFiles.map((it) => `[待确认清理新增] ${escapeHtml(it.path)}  (sha256: ${escapeHtml(String(it.current_sha256 || "").slice(0, 12))}…)`),
    ];
    banner.className = "exec-guard-banner";
    banner.innerHTML =
      `<div class="exec-guard-title"><span>检测到上次执行异常中断（需人工确认哈希后恢复）</span></div>` +
      `<div>为防止误删您在重启前手动创建的文件，系统未静默清理工作区。请核对以下变更列表与哈希后选择恢复策略：</div>` +
      (lines.length ? `<div class="exec-guard-files">${lines.map((l) => `<div>${l}</div>`).join("")}</div>` : "") +
      `<div class="exec-guard-actions">` +
        `<button type="button" class="mini-primary-btn" id="confirmRecoverDeleteBtn">确认哈希并完整恢复写前状态</button>` +
        `<button type="button" class="mini-outline-btn" id="confirmRecoverKeepNewBtn">仅还原已跟踪文件（保留新增文件）</button>` +
      `</div>`;
    banner.querySelector("#confirmRecoverDeleteBtn")?.addEventListener("click", () => executeCrashRecovery(true));
    banner.querySelector("#confirmRecoverKeepNewBtn")?.addEventListener("click", () => executeCrashRecovery(false));
    return;
  }

  if (state.rollbackConflicts && state.rollbackConflicts.length > 0) {
    banner.className = "exec-guard-banner";
    banner.innerHTML =
      `<div class="exec-guard-title"><span>原子回滚已拦截：检测到事后手动修改冲突 (${state.rollbackConflicts.length} 个文件)</span></div>` +
      `<div>为杜绝半旧半新破坏代码树，系统已整批拒绝回滚并保留快照。请先备份或还原以下冲突文件后再点击「↺ 回滚写入」，或点击「✓ 确认保留上次改动」归档快照：</div>` +
      `<div class="exec-guard-files">${state.rollbackConflicts.map((p) => `<div>• ${escapeHtml(p)}</div>`).join("")}</div>`;
    return;
  }

  if (state.postExecVerifyFailed && state.whiteboard?.can_rollback) {
    banner.className = "exec-guard-banner is-warn";
    banner.innerHTML =
      `<div class="exec-guard-title"><span>执行后自动验证命令未通过</span></div>` +
      `<div>工作区写入已完成，但验证钩子返回非零退出码。建议检查终端日志或立即点击下方「↺ 回滚写入」一键还原至写前字节状态。</div>`;
    return;
  }

  banner.className = "exec-guard-banner hidden";
  banner.innerHTML = "";
}

async function executeCrashRecovery(deleteConfirmedNew) {
  if (!state.currentSessionId) return;
  const expectedHashes = state.recoveryPlan?.expected_hashes || {};
  try {
    const res = await apiFetch(`/api/sessions/${state.currentSessionId}/recover`, {
      method: "POST",
      body: JSON.stringify({
        expected_hashes: expectedHashes,
        delete_confirmed_new_files: Boolean(deleteConfirmedNew),
      }),
    });
    state.recoveryRequired = false;
    state.recoveryPlan = null;
    state.rollbackConflicts = [];
    renderExecGuardBanner();
    renderExecutorControls();
    showToast(res.message || "已完成中断恢复", "ok", 2800);
  } catch (err) {
    showToast(err.message || "中断恢复失败，请刷新哈希列表后重试", "err", 3600);
    await fetchRecoveryPlanIfNeeded();
  }
}

async function acknowledgeCurrentSnapshot() {
  if (!state.currentSessionId) return;
  try {
    const res = await apiFetch(`/api/sessions/${state.currentSessionId}/snapshot/ack`, {
      method: "POST",
      body: JSON.stringify({}),
    });
    state.rollbackConflicts = [];
    state.postExecVerifyFailed = false;
    if (state.whiteboard) {
      state.whiteboard.can_rollback = false;
      renderWhiteboard(state.whiteboard, true, false);
    }
    renderExecGuardBanner();
    showToast(res.message || "已确认保留上一轮工作区改动", "ok", 2200);
  } catch (err) {
    showToast(err.message || "确认快照失败", "err");
  }
}

function applySessionSnapshot(snap, options = {}) {
  if (!snap) return;
  const preserveNewerSeats = snap.session_id === state.currentSessionId &&
    snap.boot_id === authState.bootId && Number(snap.rev || 0) < state.seatConfigRev;
  const isSameSessionReconnect = Boolean(options.isReconnect && snap.session_id === state.currentSessionId);
  const streamEl = el("chatStream");
  const prevScrollTop = streamEl ? streamEl.scrollTop : 0;
  const prevScrolledUp = state.userScrolledUp;

  const isDifferentSession = snap.session_id !== state.currentSessionId;
  if (isDifferentSession) {
    state.userToggledRightPane = false;
  }

  state.currentSessionId = snap.session_id;
  state.stage = snap.stage || "idle";
  state.execState = snap.exec_state || "idle";
  state.isBusy = Boolean(snap.is_busy);
  state.topic = snap.topic || "";
  state.topicLocked = Boolean(snap.topic_locked || state.stage !== "idle" || (snap.messages || []).length > 0);
  state.scenarioPack = snap.scenario_pack || snap.whiteboard?.scenario_pack || "arch_code";
  state.artifactType = snap.artifact_type || snap.whiteboard?.artifact_type || "code_patch";
  state.sessionWorkspaceDir = snap.workspace_dir || "";
  state.workspaceBound = snap.workspace_bound ?? null;
  state.workspaceIsGit = Boolean(snap.workspace_is_git);
  state.recoveryRequired = Boolean(snap.recovery_required || snap.whiteboard?.recovery_required);
  if (typeof snap.rev === "number" && snap.rev > state.sseLastRev) {
    state.sseLastRev = snap.rev;
  }

  if (!preserveNewerSeats) {
    state.seatConfigRev = Number(snap.rev) || 0;
    const norm = normalizeCollabModeAndAutoExec(snap.collab_mode, snap.auto_preview_exec);
    state.collabMode = norm.mode;
    state.autoPreviewExec = norm.autoPreviewExec;
    state.enabledAgents = Array.isArray(snap.enabled_agents) && snap.enabled_agents.length
      ? snap.enabled_agents
      : CORE_TRIAD_SEATS.slice();
    state.seatPersonas = { ...DEFAULT_SEAT_PERSONAS, ...(snap.seat_personas || {}) };
    state.seatEfforts = { ...(snap.seat_efforts || {}) };
    state.executorAgent = snap.executor_agent || "astra";
    state.seatStates = snap.seat_states || {};
  }

  if (state.stage === "executing") {
    const serverStartSec = Number(snap.execution_started_at || 0);
    state.execStartTs = serverStartSec > 0 ? Math.floor(serverStartSec * 1000) : (state.execStartTs || Date.now());
  } else {
    state.execStartTs = 0;
  }

  syncCollabModeUI(state.collabMode, state.autoPreviewExec);

  const msgs = Array.isArray(snap.messages) ? snap.messages : [];
  if (isSameSessionReconnect) {
    const incomingIds = new Set(msgs.map((m) => m.id));
    for (const oldId of Array.from(state.messages.keys())) {
      if (!incomingIds.has(oldId)) {
        document.getElementById(`msg-${oldId}`)?.remove();
        state.messages.delete(oldId);
      }
    }
    for (const m of msgs) {
      createOrUpdateMessageCard(m, { skipEnterAnim: true });
    }
    updateEmptyGuideVisibility();
    renderAllSeats();
    renderWhiteboard(snap.whiteboard || {}, false, false);
    renderStageAndHeader();
    syncAdaptiveRightCollapse();
    if (streamEl && prevScrolledUp) {
      streamEl.scrollTop = prevScrollTop;
      state.userScrolledUp = true;
    }
  } else {
    state.rollbackConflicts = [];
    state.postExecVerifyFailed = false;
    clearChatMessages();
    for (const m of msgs) {
      createOrUpdateMessageCard(m, { skipEnterAnim: true });
    }
    updateEmptyGuideVisibility();
    renderAllSeats();
    renderWhiteboard(snap.whiteboard || {}, true, true);
    renderStageAndHeader();
    syncAdaptiveRightCollapse();
    scrollToBottom(false);
  }

  if (state.recoveryRequired) {
    fetchRecoveryPlanIfNeeded();
  } else {
    state.recoveryPlan = null;
    renderExecGuardBanner();
  }
}

function dispatchSseEventFrame(eventName, rawData, rawId, sessionId) {
  if (sessionId !== state.currentSessionId) return;
  const numericId = Number(rawId || 0);
  if (numericId > 0) {
    if (eventName !== "snapshot" && numericId <= state.sseLastRev) {
      return;
    }
    state.sseLastRev = Math.max(state.sseLastRev, numericId);
  }
  if (!rawData) return;
  let pkt;
  try {
    pkt = JSON.parse(rawData);
  } catch {
    return;
  }

  if (eventName === "snapshot") {
    const isReconnect = state.sseConnectedSessionId === sessionId && state.messages.size > 0;
    state.sseConnectedSessionId = sessionId;
    if (numericId > 0) state.sseLastRev = numericId;
    applySessionSnapshot(pkt, { isReconnect });
    return;
  }

  if (eventName === "session_cleared") {
    clearChatMessages();
    updateEmptyGuideVisibility();
    syncAdaptiveRightCollapse();
    return;
  }

  if (eventName === "session_meta") {
    const prevStage = state.stage;
    state.stage = pkt.stage || state.stage;
    state.execState = pkt.exec_state || state.execState;
    state.isBusy = Boolean(pkt.is_busy);
    if (typeof pkt.topic === "string") state.topic = pkt.topic;
    if (typeof pkt.topic_locked === "boolean") state.topicLocked = pkt.topic_locked;
    if (typeof pkt.scenario_pack === "string" && pkt.scenario_pack) state.scenarioPack = pkt.scenario_pack;
    if (typeof pkt.artifact_type === "string" && pkt.artifact_type) state.artifactType = pkt.artifact_type;
    if (typeof pkt.workspace_dir === "string") state.sessionWorkspaceDir = pkt.workspace_dir;
    if (typeof pkt.workspace_bound === "boolean") state.workspaceBound = pkt.workspace_bound;
    if (typeof pkt.workspace_is_git === "boolean") state.workspaceIsGit = pkt.workspace_is_git;
    if (typeof pkt.recovery_required === "boolean") {
      state.recoveryRequired = pkt.recovery_required;
      if (state.recoveryRequired) fetchRecoveryPlanIfNeeded();
      else renderExecGuardBanner();
    }
    if (numericId >= state.seatConfigRev) {
      state.seatConfigRev = numericId;
      if (Array.isArray(pkt.enabled_agents)) state.enabledAgents = pkt.enabled_agents;
      if (pkt.seat_personas) state.seatPersonas = { ...state.seatPersonas, ...pkt.seat_personas };
      if (pkt.seat_efforts) state.seatEfforts = { ...pkt.seat_efforts };
      if (pkt.executor_agent) state.executorAgent = pkt.executor_agent;
      if (pkt.collab_mode || typeof pkt.auto_preview_exec === "boolean") {
        syncCollabModeUI(pkt.collab_mode || state.collabMode, pkt.auto_preview_exec);
      }
    }
    if (state.whiteboard) {
      if (pkt.epistemic_mode) state.whiteboard.epistemic_mode = pkt.epistemic_mode;
      if (pkt.epistemic_badge) state.whiteboard.epistemic_badge = pkt.epistemic_badge;
    }
    if (pkt.consensus_status && el("wbConsensusTag")) {
      el("wbConsensusTag").textContent = pkt.consensus_status;
    }

    if (state.stage === "executing") {
      const srvStart = Number(pkt.execution_started_at || 0);
      if (srvStart > 0) {
        state.execStartTs = Math.floor(srvStart * 1000);
      } else if (prevStage !== "executing") {
        state.execStartTs = Date.now();
      }
      if (prevStage !== "executing" && state.activeTab !== "terminal") {
        el("execDot")?.classList.remove("hidden");
      }
    } else {
      state.execStartTs = 0;
    }

    updateEmptyGuideVisibility();
    renderAllSeats();
    renderStageAndHeader();
    syncAdaptiveRightCollapse();
    refreshSessionsListOnly();
    return;
  }

  if (eventName === "seat_update") {
    if (pkt?.agent_id) {
      state.seatStates[pkt.agent_id] = pkt;
      renderSeatCard(pkt.agent_id);
    }
    return;
  }

  if (eventName === "msg_start") {
    createOrUpdateMessageCard(pkt, { skipEnterAnim: false });
    return;
  }

  if (eventName === "msg_status" || eventName === "msg_activity") {
    updateMessageStreamingStatus(pkt);
    return;
  }

  if (eventName === "msg_delta") {
    appendMessageDelta(pkt.id, pkt.delta);
    return;
  }

  if (eventName === "msg_done") {
    createOrUpdateMessageCard(pkt, { skipEnterAnim: true });
    refreshSessionsListOnly();
    return;
  }

  if (eventName === "whiteboard_update") {
    renderWhiteboard(pkt, false, false);
    return;
  }

  if (eventName === "term_log") {
    const term = el("astraTermLogs");
    if (term && pkt?.line) {
      if (term.textContent === "尚未触发执行任务") term.textContent = "";
      term.textContent += (term.textContent ? "\n" : "") + pkt.line;
      term.scrollTop = term.scrollHeight;
    }
    return;
  }

  if (eventName === "exec_delta") {
    const term = el("astraTermLogs");
    if (term && pkt?.delta) {
      if (term.textContent === "尚未触发执行任务") term.textContent = "";
      term.textContent += pkt.delta;
      term.scrollTop = term.scrollHeight;
    }
    return;
  }

  if (eventName === "exec_artifact") {
    if (el("astraDiffView")) {
      el("astraDiffView").innerHTML = renderDiffHtml(pkt.diff || "");
    }
    if (state.activeTab !== "terminal") {
      el("execDot")?.classList.remove("hidden");
    }
  }
}

function disconnectSessionStream() {
  if (state.sseAbortController) {
    state.sseAbortController.abort();
    state.sseAbortController = null;
  }
  if (state.sseReconnectTimer) {
    clearTimeout(state.sseReconnectTimer);
    state.sseReconnectTimer = null;
  }
}

function connectSessionStream(sessionId) {
  disconnectSessionStream();
  if (!sessionId) return;

  if (state.sseConnectedSessionId !== sessionId) {
    state.sseLastRev = 0;
    state.seatConfigRev = 0;
  }

  const controller = new AbortController();
  state.sseAbortController = controller;

  const setConnOnline = (online) => {
    const dot = el("sseConnDot");
    if (!dot) return;
    dot.classList.toggle("online", online);
    dot.textContent = online ? "" : "重连中";
    dot.title = online ? "本地实时服务已连接（fetch 流式鉴权通道）" : "SSE 实时流中断，正在带 since_rev 无损重连…";
  };

  (async () => {
    const qs = new URLSearchParams({
      since_rev: String(state.sseLastRev || 0),
      boot_id: String(authState.bootId || ""),
    });
    try {
      const res = await fetch(`/api/sessions/${sessionId}/stream?${qs.toString()}`, {
        method: "GET",
        headers: {
          Accept: "text/event-stream",
          ...(authState.token ? { "X-Roundtable-Token": authState.token } : {}),
        },
        signal: controller.signal,
        cache: "no-store",
      });
      if (!res.ok || !res.body) {
        throw new Error(`SSE stream HTTP ${res.status}`);
      }
      setConnOnline(true);
      const reader = res.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let lineBuf = "";
      let curEvent = "message";
      let curId = "";
      let curDataLines = [];

      const flushFrame = () => {
        if (curDataLines.length > 0) {
          dispatchSseEventFrame(curEvent, curDataLines.join("\n"), curId, sessionId);
        }
        curEvent = "message";
        curId = "";
        curDataLines = [];
      };

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        lineBuf += decoder.decode(value, { stream: true });
        let nlIdx;
        while ((nlIdx = lineBuf.indexOf("\n")) >= 0) {
          let line = lineBuf.slice(0, nlIdx);
          lineBuf = lineBuf.slice(nlIdx + 1);
          if (line.endsWith("\r")) line = line.slice(0, -1);

          if (line === "") {
            flushFrame();
          } else if (line.startsWith(":")) {
            // 心跳注释帧 : ping
          } else if (line.startsWith("event:")) {
            curEvent = line.slice(6).trim() || "message";
          } else if (line.startsWith("id:")) {
            curId = line.slice(3).trim();
          } else if (line.startsWith("data:")) {
            const dPart = line.slice(5);
            curDataLines.push(dPart.startsWith(" ") ? dPart.slice(1) : dPart);
          }
        }
      }
      lineBuf += decoder.decode();
      if (lineBuf.trim()) {
        if (lineBuf.startsWith("data:")) {
          const dPart = lineBuf.slice(5).trim();
          curDataLines.push(dPart);
        }
      }
      flushFrame();
      throw new Error("SSE EOF");
    } catch (err) {
      if (controller.signal.aborted) return;
      setConnOnline(false);
      if (state.sseAbortController === controller) {
        state.sseAbortController = null;
        state.sseReconnectTimer = setTimeout(() => {
          if (state.currentSessionId === sessionId) {
            connectSessionStream(sessionId);
          }
        }, 1200);
      }
    }
  })();
}

async function switchToSession(sessionId) {
  closePersonaPopover();
  closeAtSuggestMenu();
  state.currentSessionId = sessionId;
  renderSessionList();
  connectSessionStream(sessionId);
}

async function createNewSession() {
  if (el("allowWriteCheckbox")) {
    el("allowWriteCheckbox").checked = false;
  }
  state.userToggledRightPane = false;
  if (!state.topic && !state.whiteboard?.items?.length && state.messages.size === 0 && !state.isBusy && state.currentSessionId) {
    renderExecutorControls();
    syncAdaptiveRightCollapse();
    el("topicInput")?.focus();
    showToast("当前已是空白新会议，可直接选择场景意图包或输入议题开启研讨", "info", 2000);
    return;
  }
  try {
    const res = await apiFetch("/api/sessions", {
      method: "POST",
      body: JSON.stringify({
        title: "新会议",
        collab_mode: state.collabMode || "deep_deliberation",
        scenario_pack: state.scenarioPack || "arch_code",
        artifact_type: state.artifactType || "code_patch",
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
          scenario_pack: state.scenarioPack,
          artifact_type: state.artifactType,
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
    showToast(err.message || "发送指令失败", "err", 3600);
  } finally {
    state.sendingSessions.delete(sessionId);
  }
}

async function triggerExecutionNow() {
  if (!state.currentSessionId) return;
  const checkedCnt = getCheckedActionCount();
  if (checkedCnt < 1) {
    setRightCollapsed(false, true);
    switchWorkbenchTab("whiteboard");
    el("wbCardAction")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    showToast("尚无已勾选任务（checked_action_count = 0），请先在会议白板核对并勾选至少 1 项待执行任务", "warn", 3000);
    return;
  }
  const allowWrite = Boolean(effectiveWorkspacePath() && el("allowWriteCheckbox")?.checked) === true;
  const execAid = state.executorAgent || "astra";
  setRightCollapsed(false, true);
  switchWorkbenchTab("terminal");
  state.rollbackConflicts = [];
  state.postExecVerifyFailed = false;
  renderExecGuardBanner();
  if (el("astraTermLogs")) {
    el("astraTermLogs").textContent = `正在核验任务勾选门禁与执行锁预约（${AGENT_NAMES[execAid] || execAid} · 已勾选 ${checkedCnt} 项任务）…`;
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
    if (el("astraTermLogs")) {
      el("astraTermLogs").textContent = `准入拦截 (${err.status || 409})：${err.message}`;
    }
    if (err.payload?.reason === "unacknowledged_absent_seats") {
      switchWorkbenchTab("whiteboard");
      el("wbCardAbsent")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
    if (err.payload?.recovery_required) {
      state.recoveryRequired = true;
      await fetchRecoveryPlanIfNeeded();
    }
    showToast(err.message || "触发执行失败", "err", 3800);
  }
}

/* ==================== 渐进披露式「系统与模型设置弹窗」与单引擎串行模式 ==================== */

function switchSettingsTab(tabKey) {
  const validTabs = ["seats", "concurrency", "diagnostics"];
  const requested = tabKey === "workspace" ? "concurrency" : tabKey;
  const next = validTabs.includes(requested) ? requested : "seats";
  state.activeSettingsTab = next;
  document.querySelectorAll("#settingsNav [data-settings-tab]").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.settingsTab === next);
  });
  validTabs.forEach((k) => {
    el(`settings-pane-${k}`)?.classList.toggle("active", k === next);
  });
}

function syncModalSeatMatrixSummary() {
  const checked = [];
  document.querySelectorAll("[data-cfg-seat-enable]").forEach((chk) => {
    if (chk.checked) checked.push(chk.dataset.cfgSeatEnable);
  });
  const sumEl = el("cfgEnabledSeatSummary");
  if (sumEl) {
    sumEl.textContent = `已勾选 ${checked.length} 席：${checked.map((a) => AGENT_NAMES[a] || a).join(" · ") || "请至少保留 1 席"}`;
  }
  const showAll = el("cfgShowAllSixSeats") ? el("cfgShowAllSixSeats").checked : true;
  document.querySelectorAll("[data-cfg-seat-card]").forEach((card) => {
    const aid = card.dataset.cfgSeatCard;
    card.classList.toggle("hidden", !showAll && !checked.includes(aid));
  });
}

function openSettingsModal(initialTab = "") {
  const modal = el("settingsModal");
  if (!modal) return;
  switchSettingsTab(initialTab || "seats");
  const sys = state.system || {};
  const agents = sys.agents || {};

  if (el("cfgWorkspaceDir")) {
    el("cfgWorkspaceDir").value = effectiveWorkspacePath();
  }
  if (el("cfgPostExecVerifyCmd")) {
    el("cfgPostExecVerifyCmd").value = sys.post_exec_verify_cmd || state.postExecVerifyCmd || "";
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
    for (const [aid, cap] of SEAT_CAP_PAIRS) {
      const inp = el(`cfg${cap}Name`);
      if (inp) {
        inp.placeholder = preset?.names?.[aid] ? `留空默认：${preset.names[aid]}` : "留空跟随引擎生成";
      }
    }
  }

  document.querySelectorAll("[data-cfg-seat-enable]").forEach((chk) => {
    const aid = chk.dataset.cfgSeatEnable;
    chk.checked = state.enabledAgents.includes(aid);
  });

  syncPacingControlsInModal(
    sys.pacing_mode || state.pacingMode || "standard",
    sys.idle_timeout_sec ?? state.idleTimeoutSec ?? 300,
    sys.turn_timeout_sec ?? state.turnTimeoutSec ?? 600,
    sys.max_ref_chars ?? state.maxRefChars ?? 120000
  );

  for (const [aid, cap] of SEAT_CAP_PAIRS) {
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
          statusPill.textContent = info.shared_cli_group ? "并行池就绪" : "已就绪";
          statusPill.className = "driver-pill live";
        }
      } else {
        statusPill.textContent = "未安装";
        statusPill.className = "driver-pill missing";
      }
    }
  }

  syncDynamicRosterNames();
  syncModalSeatMatrixSummary();
  modal.classList.remove("hidden");
  modal.dispatchEvent(new Event("roundtable:settings-open"));
}

function closeSettingsModal() {
  el("settingsModal")?.classList.add("hidden");
}

function collectDraftAgentConfigsFromModal() {
  const out = {};
  for (const [aid, cap] of SEAT_CAP_PAIRS) {
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
  const singleFb = el("cfgSingleCliFallback");
  if (singleFb) singleFb.checked = true;
  const concSel = el("cfgSingleCliConcurrency");
  if (concSel && !concSel.value) {
    concSel.value = String(state.singleCliConcurrency || 3);
  }
  state.singleCliConcurrency = Number(concSel?.value || state.singleCliConcurrency || 3);

  for (const [aid, cap] of SEAT_CAP_PAIRS) {
    const drvEl = el(`cfg${cap}Driver`);
    const perEl = el(`cfg${cap}Persona`);
    const modEl = el(`cfg${cap}Model`);
    const discEl = el(`cfg${cap}Effort`);
    const execEl = el(`cfg${cap}ExecEffort`);
    if (drvEl) drvEl.value = chosenDrv;
    if (perEl && !perEl.value) perEl.value = DEFAULT_SEAT_PERSONAS[aid];
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
  const concNote = state.singleCliConcurrency > 1 ? `${state.singleCliConcurrency} 路真并行` : "串行防限流";
  showToast(
    `已将全部 6 席对齐至「${DRIVER_LABELS[chosenDrv] || chosenDrv}」无状态真并行池（${concNote}），点击「保存配置」生效`,
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
    const selectedSeats = [];
    document.querySelectorAll("[data-cfg-seat-enable]").forEach((chk) => {
      if (chk.checked) selectedSeats.push(chk.dataset.cfgSeatEnable);
    });
    if (selectedSeats.length === 0) {
      showToast("请至少启用 1 个参会席位", "warn", 2400);
      switchSettingsTab("lineup");
      return;
    }

    const activePacingBtn = document.querySelector("#cfgPacingGroup .pacing-seg-btn.active");
    const pacingMode = activePacingBtn?.dataset.pacingMode || state.pacingMode || "standard";
    const preset = PACING_PRESETS[pacingMode];
    const idleSec = preset
      ? preset.idle_timeout_sec
      : Math.max(15, Number(el("cfgIdleTimeout")?.value || 300));
    const turnSec = preset
      ? preset.turn_timeout_sec
      : Math.max(30, Number(el("cfgTurnTimeout")?.value || 600));
    const maxRef = preset
      ? preset.max_ref_chars
      : Math.max(10000, Number(el("cfgMaxRefChars")?.value || 120000));

    const wsVal = (el("cfgWorkspaceDir")?.value || "").trim();
    const verifyCmdVal = (el("cfgPostExecVerifyCmd")?.value || "").trim();
    const singleFallback = Boolean(el("cfgSingleCliFallback")?.checked);
    const singleConc = Math.min(6, Math.max(1, Number(el("cfgSingleCliConcurrency")?.value || 3)));
    const rosterPreset = el("cfgRosterPresetSelect")?.value || "role_experts";

    const draftAgents = collectDraftAgentConfigsFromModal();
    for (const aid of AGENT_ORDER) {
      if (!draftAgents[aid].execution_effort && draftAgents[aid].discussion_effort) {
        draftAgents[aid].execution_effort = draftAgents[aid].discussion_effort;
      }
    }

    const prevEffectiveWs = effectiveWorkspacePath();
    if (wsVal && wsVal !== prevEffectiveWs && state.currentSessionId && !state.isBusy) {
      await apiFetch(`/api/sessions/${state.currentSessionId}/workspace`, {
        method: "POST",
        body: JSON.stringify({ workspace_dir: wsVal }),
      });
      state.sessionWorkspaceDir = wsVal;
      state.workspaceBound = true;
    }

    const res = await apiFetch("/api/config", {
      method: "POST",
      body: JSON.stringify({
        active_session_id: state.currentSessionId || "",
        workspace_dir: wsVal,
        post_exec_verify_cmd: verifyCmdVal,
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

    const nextPersonas = {};
    const resetSeatEfforts = {};
    for (const aid of AGENT_ORDER) {
      nextPersonas[aid] = draftAgents[aid].persona;
      resetSeatEfforts[aid] = "";
    }

    state.enabledAgents = selectedSeats;
    if (!selectedSeats.includes(state.executorAgent)) {
      state.executorAgent = selectedSeats.includes("astra") ? "astra" : selectedSeats[0];
    }
    state.seatPersonas = { ...state.seatPersonas, ...nextPersonas };
    state.seatEfforts = {};
    state.postExecVerifyCmd = verifyCmdVal;
    state.rosterPreset = res.system?.roster_preset || rosterPreset;
    state.singleCliConcurrency = res.system?.single_cli_concurrency || singleConc;

    if (res.system) {
      renderSystemStatus(res.system);
    } else {
      syncDynamicRosterNames();
      renderAllSeats();
    }

    if (state.currentSessionId) {
      await persistSessionSeatsPatch({
        enabled_agents: selectedSeats,
        executor_agent: state.executorAgent,
        seat_personas: nextPersonas,
        seat_efforts: resetSeatEfforts,
      });
    }

    renderStageAndHeader();
    if (state.whiteboard) renderWhiteboard(state.whiteboard, true, false);
    closeSettingsModal();
    showToast("1–6 席阵容、并发通道与系统安全策略已保存", "ok", 2200);
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
  el("headerUnbindWsBtn")?.addEventListener("click", async (e) => {
    e.stopPropagation();
    await switchCurrentSessionWorkspace("");
  });

  // 历史会话搜索
  el("sessionSearchInput")?.addEventListener("input", (e) => {
    state.sessionSearchQuery = e.target.value || "";
    renderSessionList();
  });

  // 右侧白板/执行终端面板显隐与页签滑块切换
  el("toggleRightBtn")?.addEventListener("click", () => {
    const isHidden = el("appShell")?.classList.contains("right-collapsed");
    setRightCollapsed(!isHidden, true);
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
        ? "已开启「自动执行预演」：讨论收敛并勾选任务后将进入只读预演"
        : "已关闭「自动执行预演」",
      "info",
      2200
    );
  };
  el("emptyAutoPreviewBtn")?.addEventListener("click", toggleAutoPreview);
  el("composerAutoPreviewBtn")?.addEventListener("click", toggleAutoPreview);

  // 首屏四大场景意图包 Facade 事务切换
  document.querySelectorAll("[data-scenario-pack]").forEach((card) => {
    card.addEventListener("click", () => applyScenarioPack(card.dataset.scenarioPack));
  });

  // 高级抽屉与侧栏 1–6 席预设联动
  document.querySelectorAll("[data-scenario-preset]").forEach((btn) => {
    btn.addEventListener("click", () => applyScenarioPreset(btn.dataset.scenarioPreset));
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
          scenario_pack: state.scenarioPack,
          artifact_type: state.artifactType,
          auto_preview_exec: state.autoPreviewExec,
          enabled_agents: state.enabledAgents,
          seat_personas: state.seatPersonas,
          seat_efforts: state.seatEfforts,
          executor_agent: state.executorAgent,
          reset_history: true,
        }),
      });
      showToast("已按当前场景意图包与席位分工重开本议题", "ok", 2000);
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

  // 会议白板操作：单击议题编辑（运行前）、+添加条目、缺席确认、整理去重、复制纪要、导出 .md、自适应交付出口
  el("wbTopicText")?.addEventListener("click", () => startInlineTopicEdit());
  el("wbAckAbsentBtn")?.addEventListener("click", async () => {
    const wb = await postWhiteboardMutation({ op: "acknowledge_absent" });
    if (wb) showToast("已确认知悉缺席席位影响，执行准入已解锁", "ok", 2200);
  });

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
        const isAction = editorKey === "action";
        const wb = await postWhiteboardMutation({
          op: "add",
          bucket: isConstraint ? "chair_constraints" : editorKey,
          kind: isConstraint ? "decision" : editorKey,
          author: "chair",
          pinned: isConstraint,
          checked: !isAction,
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
    if (!hasExportableSessionContent()) return;
    const wb = await postWhiteboardMutation({ op: "dedupe_clean" });
    if (wb) showToast("已完成白板整理去重与过程性噪音清理", "ok", 2000);
  });
  el("copyMdBtn")?.addEventListener("click", () => {
    if (!hasExportableSessionContent()) {
      showToast("当前会话尚无发言或白板条目，不可复制空纪要", "warn", 2000);
      return;
    }
    copyTextToClipboard(buildMinutesMarkdown(), "会议纪要 Markdown 已复制");
  });
  el("exportMdBtn")?.addEventListener("click", () => exportMinutesMarkdownFile());
  el("wbQuickCopyArtifactBtn")?.addEventListener("click", () => {
    if (!hasExportableSessionContent()) return;
    copyTextToClipboard(buildMinutesMarkdown(), "结构化交付纪要已复制");
  });
  el("wbQuickExportArtifactBtn")?.addEventListener("click", () => exportMinutesMarkdownFile());
  el("wbToExecBtn")?.addEventListener("click", () => {
    const checkedCnt = getCheckedActionCount();
    if (checkedCnt < 1) {
      showToast("尚无已勾选任务，请先在待执行清单勾选至少 1 项任务", "warn", 2200);
      return;
    }
    setRightCollapsed(false, true);
    switchWorkbenchTab("terminal");
  });

  // 执行终端：执行席位分段器、沙箱权限分段器、日志与补丁操作、CAS 快照回滚
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
  el("ackSnapshotBtn")?.addEventListener("click", () => acknowledgeCurrentSnapshot());

  el("rollbackExecBtn")?.addEventListener("click", async () => {
    if (!state.currentSessionId) return;
    try {
      const res = await apiFetch(`/api/sessions/${state.currentSessionId}/rollback`, {
        method: "POST",
        body: JSON.stringify({}),
      });
      state.rollbackConflicts = [];
      state.postExecVerifyFailed = false;
      renderExecGuardBanner();
      showToast(res.message || "已按写前 CAS 字节清单原子回滚工作区", "ok", 2800);
    } catch (err) {
      if (err.status === 409 && Array.isArray(err.payload?.conflict_paths)) {
        state.rollbackConflicts = err.payload.conflict_paths;
        renderExecGuardBanner();
      }
      showToast(err.message || "原子回滚已拦截", "err", 4200);
    }
  });

  // 顶栏圆桌席位快速编排按钮、一键异构混编推荐 & 分导航系统设置中心
  el("ringHeterogeneousBtn")?.addEventListener("click", () => applyHeterogeneousRecommendation());
  el("ringLineupQuickBtn")?.addEventListener("click", () => openSettingsModal("lineup"));
  el("railSettingsBtn")?.addEventListener("click", () => openSettingsModal());
  el("openSettingsBtn")?.addEventListener("click", () => openSettingsModal());
  el("closeSettingsBtn")?.addEventListener("click", () => closeSettingsModal());
  el("cancelSettingsBtn")?.addEventListener("click", () => closeSettingsModal());
  el("settingsModal")?.addEventListener("click", (e) => {
    if (e.target === el("settingsModal")) closeSettingsModal();
  });
  document.querySelectorAll("#settingsNav [data-settings-tab]").forEach((btn) => {
    btn.addEventListener("click", () => switchSettingsTab(btn.dataset.settingsTab));
  });
  document.querySelectorAll("[data-cfg-seat-enable]").forEach((chk) => {
    chk.addEventListener("change", () => syncModalSeatMatrixSummary());
  });
  el("cfgShowAllSixSeats")?.addEventListener("change", () => syncModalSeatMatrixSummary());
  document.querySelectorAll("[data-modal-lineup]").forEach((chip) => {
    chip.addEventListener("click", () => {
      const key = chip.dataset.modalLineup;
      const spec = SCENARIO_PRESETS[key];
      if (!spec) return;
      const targetEnabled = spec.solo ? [pickPreferredSoloSeat()] : (spec.enabled_agents || CORE_TRIAD_SEATS);
      const targetPersonas = spec.solo
        ? { [targetEnabled[0]]: "fullstack_solo" }
        : (spec.seat_personas || DEFAULT_SEAT_PERSONAS);
      document.querySelectorAll("[data-cfg-seat-enable]").forEach((chk) => {
        chk.checked = targetEnabled.includes(chk.dataset.cfgSeatEnable);
      });
      for (const [aid, cap] of SEAT_CAP_PAIRS) {
        const pSel = el(`cfg${cap}Persona`);
        if (pSel && targetPersonas[aid]) pSel.value = targetPersonas[aid];
      }
      syncCollabModeUI(spec.collab_mode, state.autoPreviewExec);
      syncModalSeatMatrixSummary();
      showToast(`已在设置中心预选「${spec.label}」，点击右下角「保存配置」生效`, "info", 2200);
    });
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

  for (const [, cap] of SEAT_CAP_PAIRS) {
    el(`cfg${cap}Driver`)?.addEventListener("change", () => refreshSeatEffortSelectInModal(cap, true));
    el(`cfg${cap}Model`)?.addEventListener("input", () => refreshSeatEffortSelectInModal(cap, false));
  }

  el("cfgRosterPresetSelect")?.addEventListener("change", (e) => {
    const val = e.target.value || "role_experts";
    const preset = ROSTER_NAME_PRESETS[val];
    for (const [aid, cap] of SEAT_CAP_PAIRS) {
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
  if (/Win/.test(navigator.platform)) {
    document.querySelectorAll('[title*="⌘"]').forEach(node => { node.title = node.title.replaceAll("⌘", "Ctrl+"); });
  }
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
    await initControlPlaneAuth();
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
