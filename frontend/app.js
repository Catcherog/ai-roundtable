// AI圆桌 — 珍珠极昼流线工作台前端交互逻辑（集成 7 大预设身份、一键独奏、动态主刀、@源码自动补全、实时流式终端与 Git 护栏）

const AGENT_NAMES = {
  carbon: "Carbon",
  grok: "Grok",
  astra: "Astra",
};

const AGENT_ORDER = ["carbon", "grok", "astra"];

const FALLBACK_PERSONA_PRESETS = {
  planner: {
    key: "planner",
    label: "架构规划",
    short_tag: "规划",
    wb_title: "阶段规划共识",
    cue_btn: "请 {name} 收敛",
    cue_prompt: "请整合各方分歧，收敛出清晰的阶段优先级与取舍结论",
    prompt: "自顶向下拆解目标边界、明确取舍优先级并收敛各方分歧。",
  },
  fullstack_solo: {
    key: "fullstack_solo",
    label: "全栈主程",
    short_tag: "主程",
    wb_title: "全栈设计与执行清单",
    cue_btn: "请 {name} 深化方案",
    cue_prompt: "请深化核心架构设计、关键边界防线与可直接编码的文件级实施清单",
    prompt: "统筹系统架构拆解、关键异常边界自检与文件级可执行实施步骤。",
  },
  red_team: {
    key: "red_team",
    label: "红队挑刺",
    short_tag: "挑刺",
    wb_title: "风险防线与补充",
    cue_btn: "请 {name} 挑刺",
    cue_prompt: "请指出当前方案遗漏的边界条件、潜在风险与反例",
    prompt: "专门寻找盲区、并发边界与反例，给出实质风险防线。",
  },
  implementer: {
    key: "implementer",
    label: "工程落地",
    short_tag: "落地",
    wb_title: "工程落地清单",
    cue_btn: "请 {name} 评落地",
    cue_prompt: "请评估具体改动文件范围、实施步骤与验证方式",
    prompt: "务实评估技术选型、改动文件范围与最小验证步骤。",
  },
  product_ux: {
    key: "product_ux",
    label: "产品交互",
    short_tag: "交互",
    wb_title: "体验与交互建议",
    cue_btn: "请 {name} 审交互",
    cue_prompt: "请从用户操作路径、信息降噪与异常状态反馈维度提出体验优化建议",
    prompt: "审视界面层级、信息降噪、边界反馈与交互手感。",
  },
  perf_sre: {
    key: "perf_sre",
    label: "性能稳定",
    short_tag: "性能",
    wb_title: "性能与稳定护栏",
    cue_btn: "请 {name} 审性能",
    cue_prompt: "请排查响应延迟瓶颈、并发竞争、资源泄漏与超时降级隐患",
    prompt: "聚焦响应延迟、并发竞争、超时熔断与故障自愈护栏。",
  },
  qa_audit: {
    key: "qa_audit",
    label: "测试验收",
    short_tag: "测试",
    wb_title: "测试与验收矩阵",
    cue_btn: "请 {name} 列验收",
    cue_prompt: "请梳理极端边界输入、回归检查矩阵与自动化验证方案",
    prompt: "拆解正常流、异常流与边界用例矩阵，输出回归自检命令。",
  },
};

const MODE_HINTS = {
  standard_roundtable: "并发初评 → 并发质询+主控收敛（单席位独奏自动直达方案沉淀）",
  fast_align: "并发初评 → 1轮并发质询+收敛 → 待主持决议",
  red_blue_debate: "并发立论 → 2轮深度挑刺与边界风险审视",
  arch_to_exec: "并发初评 → 1轮快速收敛 → 自动汇总并交由主刀席位预演",
};

const SHORT_MODE_HINTS = {
  standard_roundtable: "并发初评 → 2轮交叉收敛",
  fast_align: "并发初评 → 1轮快速对齐",
  red_blue_debate: "并发立论 → 2轮深度挑刺",
  arch_to_exec: "快速收敛后自动触发预演",
};

const PALETTES = [
  { key: "pearl", label: "珍珠极昼" },
  { key: "alabaster", label: "暖砂羊皮纸" },
  { key: "glacier", label: "晨雾冰川" },
  { key: "sage", label: "鼠尾草微风" },
];

const FONT_SCALES = [
  { key: "comfort", label: "舒适" },
  { key: "large", label: "大字" },
  { key: "standard", label: "标准" },
];

const SPEAKER_AMBIENT_GLOW = {
  carbon: ["rgba(96, 165, 250, 0.42)", "rgba(165, 243, 252, 0.38)"],
  grok: ["rgba(253, 186, 116, 0.44)", "rgba(253, 230, 138, 0.38)"],
  astra: ["rgba(110, 231, 183, 0.44)", "rgba(153, 246, 228, 0.38)"],
  chair: ["rgba(196, 181, 253, 0.44)", "rgba(251, 207, 232, 0.36)"],
};

const AT_REF_REGEX = /@([A-Za-z0-9_\u4e00-\u9fa5./-]+\.[A-Za-z0-9]{1,10})(?::L?(\d+)(?:-L?(\d+))?)?/gi;
const NOISE_PIN_PREFIX = /^(?:我只查公开资料|先核实|同意|完全赞同|赞同|收到|好的|补充一点|针对\s*@|工程侧赞同|综合\s*@|以下是|作为)/i;
const TOOL_MONOLOGUE_NOISE_RE = /^(?:我(?:先|这就|来|去|将|准备|需要|正在|只)?\s*(?:只读|核对|查看|读取|检查|检索|扫描|查阅|浏览|打开|看下|看一下|查一下|只查|核实)|先\s*(?:只读|核对|查看|读取|检查|检索|看下|看一下|看源码|核实|对一下)|让我(?:先)?\s*(?:只读|核对|查看|读取|检查|看下)|正在\s*(?:只读|读取|核对|查看|检索|扫描)|接下来我(?:先)?\s*(?:只读|核对|查看|读取)|Finishing\s+session)/i;
const PURE_PROCEDURAL_TAIL_RE = /(?:我先(?:只读|核对|查看|检查)[^。；\n]{0,40}$|只读[^。；\n]{0,20}不改任何文件[。.]?$)/i;

const WB_EXCERPT_COMPACT_LIMIT = 12;
const WB_EXCERPT_SOFT_CAP = 60;

function isClientWhiteboardNoise(rawText) {
  const s = String(rawText || "")
    .replace(/^(?:[-*•]+|\d+[.)、]|[①②③④⑤])\s*/, "")
    .trim();
  if (s.length < 4) return true;
  if (["无", "暂无", "待补充", "发言完成"].includes(s)) return true;
  if (NOISE_PIN_PREFIX.test(s)) return true;
  if (TOOL_MONOLOGUE_NOISE_RE.test(s)) return true;
  if (s.length <= 64 && PURE_PROCEDURAL_TAIL_RE.test(s)) return true;
  return false;
}

const pendingDeltaIds = new Set();
let deltaRafId = 0;
let refreshSessionsTimer = 0;
let thinkingTimerId = 0;
let atSearchTimer = 0;
let composingLock = false;
let composingUnlockTimer = 0;
let sourceHighlightTimer = 0;

const state = {
  currentSessionId: null,
  sessionWorkspaceDir: "",
  workspaceIsGit: false,
  workspaceFiles: [],
  workspaceFileSet: new Set(),
  atMenuOpen: false,
  atCandidates: [],
  atActiveIdx: 0,
  atTokenRange: null,
  execStartTs: 0,
  execStreamingBuffer: "",
  eventSource: null,
  systemStatus: null,
  pingResults: {},
  expandedCliCards: new Set(),
  sessions: [],
  sessionFilter: "",
  messagesById: new Map(),
  msgCollapseState: new Map(),
  thinkingStartById: new Map(),
  seatThinkingStart: new Map(),
  whiteboard: null,
  wbFilterSeat: "all",
  wbExcerptsExpanded: false,
  wbEditingDraft: null,
  wbConflictState: null,
  knownWbIds: new Set(),
  wbInitialSeeded: false,
  lastWbTotalCount: 0,
  currentTopic: "",
  stage: "idle",
  isBusy: false,
  enabledAgents: ["carbon", "grok", "astra"],
  seatPersonas: { carbon: "planner", grok: "red_team", astra: "implementer" },
  seatStates: {},
  executorAgent: "astra",
  activePersonaSeat: null,
  activePopoverAnchor: null,
  rawDiffText: "",
  stickToBottom: true,
  pendingNativeFolderModal: false,
};

const el = (id) => document.getElementById(id);

function on(id, eventName, handler) {
  const node = el(id);
  if (node) {
    node.addEventListener(eventName, handler);
  }
}

function getPersonaMap() {
  return state.systemStatus?.persona_presets || FALLBACK_PERSONA_PRESETS;
}

function getPersonaSpec(personaKey, fallbackAid = "carbon") {
  const map = getPersonaMap();
  if (personaKey && map[personaKey]) return map[personaKey];
  const defKey = { carbon: "planner", grok: "red_team", astra: "implementer" }[fallbackAid] || "planner";
  return map[defKey] || FALLBACK_PERSONA_PRESETS[defKey];
}

function showToast(message, type = "info", durationMs = 2800) {
  const box = el("toastContainer");
  if (!box) return;
  const item = document.createElement("div");
  item.className = `toast-item toast-${type}`;
  item.textContent = message;
  box.appendChild(item);
  setTimeout(() => {
    item.style.opacity = "0";
    item.style.transform = "translateY(-6px)";
    item.style.transition = "all 0.18s ease";
    setTimeout(() => item.remove(), 200);
  }, durationMs);
}

function escapeHtml(raw) {
  return String(raw || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function stripTrailingStatusTag(raw) {
  if (!raw) return "";
  return String(raw)
    .replace(/(?:\n?\s*\[(?:状态|徽章|白板|白板要点)[:：][^\]]*\]?\s*)+$/u, "")
    .trimEnd();
}

function formatInlineMarkdown(escapedLine) {
  return escapedLine
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/@(Carbon|Grok|Astra)\b/gi, '<span class="mention-tag">@$1</span>')
    .replace(
      /@([A-Za-z0-9_\u4e00-\u9fa5./-]+\.[A-Za-z0-9]{1,10}(?::L?\d+(?:-L?\d+)?)?)/gi,
      '<span class="file-mention-tag">@$1</span>'
    );
}

function splitMarkdownTableRow(rawRow) {
  let s = String(rawRow || "").trim();
  if (s.startsWith("|")) s = s.slice(1);
  if (s.endsWith("|") && !s.endsWith("\\|")) s = s.slice(0, -1);
  const cells = [];
  let cur = "";
  let inCode = false;
  for (let i = 0; i < s.length; i += 1) {
    const ch = s[i];
    if (ch === "`") {
      inCode = !inCode;
      cur += ch;
    } else if (ch === "\\" && i + 1 < s.length && s[i + 1] === "|") {
      cur += "|";
      i += 1;
    } else if (ch === "|" && !inCode) {
      cells.push(cur.trim());
      cur = "";
    } else {
      cur += ch;
    }
  }
  cells.push(cur.trim());
  return cells;
}

function isMarkdownTableSeparator(line) {
  const t = String(line || "").trim();
  if (!t.includes("|") || !t.includes("-")) return false;
  return /^\|?\s*:?-{1,}:?(?:\s*\|\s*:?-{1,}:?)+\s*\|?$/.test(t);
}

function formatTableCellHtml(rawCell) {
  return formatInlineMarkdown(escapeHtml(rawCell)).replace(/&lt;br\s*\/?&gt;/gi, "<br>");
}

function renderMarkdownSafe(rawContent) {
  const cleanRaw = stripTrailingStatusTag(rawContent || "");
  if (!cleanRaw) return "";

  const codeBlocks = [];
  const withPlaceholders = cleanRaw.replace(/```([a-zA-Z0-9_+-]*)\n?([\s\S]*?)```/g, (_, lang, code) => {
    const idx = codeBlocks.length;
    const safeLang = escapeHtml(lang || "text");
    const safeCode = escapeHtml(code.replace(/\n$/, ""));
    codeBlocks.push(
      `<div class="md-code-block">` +
        `<div class="md-code-head"><span>${safeLang}</span><button type="button" class="md-copy-code">复制代码</button></div>` +
        `<pre><code>${safeCode}</code></pre>` +
      `</div>`
    );
    return `\n@@CODEBLOCK_${idx}@@\n`;
  });

  const lines = withPlaceholders.split("\n");
  const out = [];
  let listType = null;

  const closeList = () => {
    if (listType) {
      out.push(`</${listType}>`);
      listType = null;
    }
  };

  for (let i = 0; i < lines.length; i += 1) {
    const rawLine = lines[i];
    const trimmed = rawLine.trim();
    const codeMatch = trimmed.match(/^@@CODEBLOCK_(\d+)@@$/);
    if (codeMatch) {
      closeList();
      out.push(codeBlocks[Number(codeMatch[1])] || "");
      continue;
    }

    if (!trimmed) {
      closeList();
      continue;
    }

    if (/^(?:-{3,}|\*{3,}|_{3,})$/.test(trimmed)) {
      closeList();
      out.push('<hr class="md-hr" />');
      continue;
    }

    if (
      trimmed.includes("|") &&
      !trimmed.startsWith(">") &&
      i + 1 < lines.length &&
      isMarkdownTableSeparator(lines[i + 1])
    ) {
      const headerCells = splitMarkdownTableRow(rawLine);
      const sepCells = splitMarkdownTableRow(lines[i + 1]);
      if (headerCells.length >= 2 && sepCells.length >= 2) {
        closeList();
        const colCount = Math.max(headerCells.length, sepCells.length);
        const aligns = Array.from({ length: colCount }, (_, cIdx) => {
          const sc = (sepCells[cIdx] || "").trim();
          if (sc.startsWith(":") && sc.endsWith(":")) return "center";
          if (sc.endsWith(":")) return "right";
          return "left";
        });

        let tableHtml = `<div class="md-table-wrap"><table class="md-table"><thead><tr>`;
        for (let c = 0; c < headerCells.length; c += 1) {
          tableHtml += `<th style="text-align:${aligns[c] || "left"}">${formatTableCellHtml(headerCells[c])}</th>`;
        }
        tableHtml += `</tr></thead><tbody>`;

        i += 2;
        while (i < lines.length) {
          const rowTrim = lines[i].trim();
          if (
            !rowTrim ||
            /^@@CODEBLOCK_\d+@@$/.test(rowTrim) ||
            /^#{1,4}\s+/.test(rowTrim) ||
            !rowTrim.includes("|")
          ) {
            break;
          }
          const rowCells = splitMarkdownTableRow(lines[i]);
          tableHtml += "<tr>";
          for (let c = 0; c < headerCells.length; c += 1) {
            tableHtml += `<td style="text-align:${aligns[c] || "left"}">${formatTableCellHtml(rowCells[c] || "")}</td>`;
          }
          tableHtml += "</tr>";
          i += 1;
        }
        i -= 1;
        tableHtml += "</tbody></table></div>";
        out.push(tableHtml);
        continue;
      }
    }

    const escaped = escapeHtml(rawLine);
    const hMatch = trimmed.match(/^(#{1,4})\s+(.+)$/);
    if (hMatch) {
      closeList();
      const tag = hMatch[1].length <= 2 ? "h3" : "h4";
      out.push(`<${tag}>${formatInlineMarkdown(escapeHtml(hMatch[2]))}</${tag}>`);
      continue;
    }

    const bqMatch = trimmed.match(/^>\s?(.*)$/);
    if (bqMatch) {
      closeList();
      out.push(`<blockquote>${formatInlineMarkdown(escapeHtml(bqMatch[1]))}</blockquote>`);
      continue;
    }

    const ulMatch = trimmed.match(/^[-*•]\s+(.+)$/);
    if (ulMatch) {
      if (listType !== "ul") {
        closeList();
        listType = "ul";
        out.push("<ul>");
      }
      out.push(`<li>${formatInlineMarkdown(escapeHtml(ulMatch[1]))}</li>`);
      continue;
    }

    const olMatch = trimmed.match(/^\d+[.)、]\s+(.+)$/);
    if (olMatch) {
      if (listType !== "ol") {
        closeList();
        listType = "ol";
        out.push("<ol>");
      }
      out.push(`<li>${formatInlineMarkdown(escapeHtml(olMatch[1]))}</li>`);
      continue;
    }

    closeList();
    out.push(`<p>${formatInlineMarkdown(escaped)}</p>`);
  }

  closeList();
  return out.join("");
}

async function copyText(text, okHint = "已复制到剪贴板") {
  try {
    await navigator.clipboard.writeText(text);
    showToast(okHint, "ok", 1800);
  } catch (_) {
    const ta = document.createElement("textarea");
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    ta.remove();
    showToast(okHint, "ok", 1800);
  }
}

async function apiFetch(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.error || `请求失败 (${res.status})`);
  }
  return data;
}

function autoResizeComposer() {
  const input = el("topicInput");
  if (!input) return;
  input.style.height = "auto";
  const maxH = 160;
  const nextH = Math.min(input.scrollHeight, maxH);
  input.style.height = `${nextH}px`;
  input.style.overflowY = input.scrollHeight > maxH ? "auto" : "hidden";
}

function normalizeCompareText(raw) {
  return String(raw || "")
    .trim()
    .replace(/^\[主持人插话\]\s*/i, "")
    .replace(/^议题[:：]\s*/i, "")
    .replace(/[\s`*_#>•\-—，。！？；：,.!?;:()（）【】[\]"'“”‘’]+/g, "")
    .toLowerCase();
}

function summarizeTopicClient(rawTopic) {
  const raw = String(rawTopic || "").trim();
  if (!raw) return "";
  const lines = raw
    .split(/\r?\n/)
    .map((ln) => ln.trim())
    .filter(Boolean);
  let first = lines[0] || raw;
  first = first
    .replace(/^(?:[#>*\-•]+|\d+[.)、])\s*/, "")
    .replace(/^(?:议题|问题|任务|需求|目标|背景)[:：]\s*/, "")
    .replace(/(?:^|\s)@[A-Za-z0-9_\u4e00-\u9fa5./:-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  if (!first) first = raw.replace(/\s+/g, " ").trim();
  const clause = first.split(/[。！？!?；;\n]/)[0].trim() || first;
  return clause.length > 28 ? `${clause.slice(0, 28).trimEnd()}…` : clause;
}

function resolveConciseTopicTitle(rawTopic, preferredTitle = "") {
  const pref = String(preferredTitle || "").trim();
  if (pref && pref !== "新会议" && pref !== "未命名会议" && pref.length <= 32) {
    return pref;
  }
  return summarizeTopicClient(rawTopic) || pref.slice(0, 28) || "新圆桌会议";
}

function dedupeChairConstraintsClient(topic, topicTitle, chairConstraints) {
  if (!Array.isArray(chairConstraints) || chairConstraints.length === 0) return [];
  const topicNorm = normalizeCompareText(topic);
  const titleNorm = normalizeCompareText(topicTitle);
  const seen = new Set();
  const result = [];
  chairConstraints.forEach((item, origIndex) => {
    const text = String(item || "").trim();
    if (!text) return;
    const norm = normalizeCompareText(text);
    if (!norm) return;
    if (topicNorm && (norm === topicNorm || (norm.length >= 18 && topicNorm.includes(norm)) || (topicNorm.length >= 18 && norm.includes(topicNorm)))) {
      return;
    }
    if (titleNorm && norm === titleNorm) {
      return;
    }
    if (seen.has(norm)) return;
    seen.add(norm);
    result.push({ text, origIndex });
  });
  return result;
}

function formatLatencyBadge(elapsedMs) {
  const ms = Math.max(0, Number(elapsedMs || 0));
  const text = ms < 1000 ? `${Math.round(ms)}ms` : `${(ms / 1000).toFixed(1)}s`;
  if (ms < 10000) {
    return { text, tierClass: "latency-fast", tierHint: "响应迅速 (< 10s)" };
  }
  if (ms <= 25000) {
    return { text, tierClass: "latency-normal", tierHint: "常规耗时 (10~25s)" };
  }
  return { text, tierClass: "latency-slow", tierHint: "耗时偏高 (> 25s)" };
}

function detectFirstReadyDriver() {
  const agents = state.systemStatus?.agents || {};
  for (const aid of AGENT_ORDER) {
    const info = agents[aid];
    if (info && info.binary_detected && info.effective_driver) {
      return info.effective_driver;
    }
  }
  return "agy";
}

function resolveFrontendEffortSpec(driver, model, seatId = "carbon") {
  let drv = String(driver || "").trim().toLowerCase();
  if (!drv || drv === "auto") {
    drv =
      state.systemStatus?.agents?.[seatId]?.effective_driver ||
      detectFirstReadyDriver() ||
      { carbon: "agy", grok: "grok", astra: "codex" }[seatId] ||
      "agy";
  }
  const m = String(model || "").trim();
  const mLow = m.toLowerCase();

  if (drv === "agy") {
    if (mLow.includes("orchestrator")) {
      return {
        driver: "agy",
        supportsEffort: false,
        allowed: [],
        defaultEffort: "",
        hint: "Orchestrator 不传 --effort",
        listId: "agyModelPresets",
        placeholder: "如 gemini-4-carbon",
      };
    }
    if (mLow.includes("hydrogen")) {
      return {
        driver: "agy",
        supportsEffort: true,
        allowed: ["low", "medium", "high", "xhigh"],
        defaultEffort: "xhigh",
        hint: "Hydrogen 开放至 xhigh",
        listId: "agyModelPresets",
        placeholder: "如 gemini-4-hydrogen",
      };
    }
    return {
      driver: "agy",
      supportsEffort: true,
      allowed: ["low", "medium", "high"],
      defaultEffort: "high",
      hint: "仅支持 low / medium / high",
      listId: "agyModelPresets",
      placeholder: "如 gemini-4-carbon",
    };
  }

  if (drv === "grok") {
    return {
      driver: "grok",
      supportsEffort: true,
      allowed: ["low", "medium", "high", "xhigh"],
      defaultEffort: "xhigh",
      hint: "grok-4.7 开放至 xhigh",
      listId: "grokModelPresets",
      placeholder: "如 grok-4.7",
    };
  }

  if (mLow.includes("sol")) {
    return {
      driver: "codex",
      supportsEffort: true,
      allowed: ["low", "medium", "high", "xhigh"],
      defaultEffort: "xhigh",
      hint: "Sol 开放至 xhigh",
      listId: "codexModelPresets",
      placeholder: "如 gpt-6.1-sol",
    };
  }

  return {
    driver: "codex",
    supportsEffort: true,
    allowed: ["low", "medium", "high", "xhigh", "max"],
    defaultEffort: "max",
    hint: "gpt-6-astra 开放至 max",
    listId: "codexModelPresets",
    placeholder: "如 gpt-6-astra",
  };
}

function clampEffortBySpec(rawEffort, spec, isExec = false) {
  if (!spec || !spec.supportsEffort || !Array.isArray(spec.allowed) || spec.allowed.length === 0) {
    return "";
  }
  const pool = isExec && spec.allowed.length > 1 ? spec.allowed.filter((x) => x !== "low") : spec.allowed;
  const eff = String(rawEffort || "").trim().toLowerCase();
  if (pool.includes(eff)) return eff;
  if (["xhigh", "max", "ultra"].includes(eff)) {
    return pool[pool.length - 1];
  }
  if (spec.defaultEffort && pool.includes(spec.defaultEffort)) {
    return spec.defaultEffort;
  }
  return pool[pool.length - 1];
}

function syncModalEffortOptionsForSeat(aid, preferredDiscuss = undefined, preferredExec = undefined) {
  const cap = aid.charAt(0).toUpperCase() + aid.slice(1);
  const driverEl = el(`cfg${cap}Driver`);
  const modelEl = el(`cfg${cap}Model`);
  const discussEl = el(`cfg${cap}Effort`);
  const execEl = el(`cfg${cap}ExecEffort`);
  const hintEl = el(`cfg${cap}EffortHint`);
  if (!driverEl || !discussEl || !execEl) return;

  const spec = resolveFrontendEffortSpec(driverEl.value, modelEl?.value || "", aid);
  if (modelEl) {
    modelEl.setAttribute("list", spec.listId);
    modelEl.placeholder = spec.placeholder;
  }
  if (hintEl) {
    hintEl.textContent = spec.hint ? `(${spec.hint})` : "";
  }

  const labelForOpt = (val, isTop, isDefault) => {
    if (val === "max" && isTop) return "max（满档）";
    if (isDefault && isTop) return `${val}（最高 / 默认）`;
    if (isDefault) return `${val}（默认）`;
    if (isTop) return `${val}（最高）`;
    return val;
  };

  const rebuildSelect = (selectNode, rawPreferred, isExec) => {
    const prevVal = rawPreferred !== undefined ? rawPreferred : selectNode.value;
    if (!spec.supportsEffort) {
      selectNode.innerHTML = `<option value="" selected>无需档位（自动省略 --effort）</option>`;
      selectNode.value = "";
      selectNode.disabled = true;
      return;
    }
    const pool = isExec && spec.allowed.length > 1 ? spec.allowed.filter((x) => x !== "low") : spec.allowed;
    const chosen = clampEffortBySpec(prevVal, spec, isExec);
    const topVal = pool[pool.length - 1];
    selectNode.disabled = false;
    selectNode.innerHTML = pool
      .map((opt) => {
        const txt = labelForOpt(opt, opt === topVal, opt === spec.defaultEffort);
        return `<option value="${escapeHtml(opt)}"${opt === chosen ? " selected" : ""}>${escapeHtml(txt)}</option>`;
      })
      .join("");
    selectNode.value = chosen;
  };

  rebuildSelect(discussEl, preferredDiscuss, false);
  rebuildSelect(execEl, preferredExec, true);
}

function resetClientBusyTimersIfIdle() {
  if (state.isBusy) return;
  state.thinkingStartById.clear();
  state.seatThinkingStart.clear();
  state.execStartTs = 0;
  stopThinkingTickerIfIdle();
  el("execLiveTimer")?.classList.add("hidden");
  AGENT_ORDER.forEach((aid) => {
    const st = state.seatStates[aid];
    if (st && (st.status === "thinking" || st.status === "queued" || st.status === "executing")) {
      st.status = "idle";
      if (!st.badge || st.badge.includes("思考") || st.badge.includes("排队") || st.badge.includes("执行")) {
        st.badge = "待命";
      }
      updateSeatUI(st);
    }
  });
}

function normalizeFileEntry(f) {
  if (typeof f === "string") return { path: f, size_kb: 0 };
  return { path: String(f.path || ""), size_kb: Number(f.size_kb || 0) };
}

// ==================== 工作区源码检索与 @文件路径 自动补全 ====================

async function refreshWorkspaceFilesIndex(query = "") {
  const wsDir = state.sessionWorkspaceDir || state.systemStatus?.workspace_dir || "";
  if (isUnboundWorkspace(wsDir)) {
    state.workspaceFiles = [];
    state.workspaceFileSet.clear();
    renderAttachedFileChips();
    return [];
  }
  try {
    const sid = encodeURIComponent(state.currentSessionId || "");
    const q = encodeURIComponent(query || "");
    const res = await apiFetch(`/api/workspace/files?session_id=${sid}&q=${q}&limit=200`);
    if (res && Array.isArray(res.files)) {
      const normalized = res.files.map(normalizeFileEntry).filter((x) => x.path);
      if (!query) {
        state.workspaceFiles = normalized;
        state.workspaceFileSet = new Set(normalized.map((f) => f.path));
      }
      if (typeof res.is_git === "boolean") {
        state.workspaceIsGit = res.is_git;
        syncExecModeUI();
      }
      renderAttachedFileChips();
      return normalized;
    }
  } catch (_) {}
  return [];
}

function closeAtSuggestMenu() {
  state.atMenuOpen = false;
  state.atCandidates = [];
  state.atActiveIdx = 0;
  state.atTokenRange = null;
  el("atSuggestMenu")?.classList.add("hidden");
}

function renderAtSuggestMenu(candidates, unbound = false) {
  const menu = el("atSuggestMenu");
  if (!menu) return;

  if (unbound) {
    state.atMenuOpen = true;
    state.atCandidates = [{ isBindAction: true }];
    state.atActiveIdx = 0;
    menu.innerHTML = `
      <div class="at-menu-head">尚未绑定本地项目目录</div>
      <div class="at-menu-item active" data-at-bind="1">
        <span class="at-file-path">📂 点击选择本地项目文件夹后即可 @引用源码…</span>
      </div>
    `;
    menu.classList.remove("hidden");
    return;
  }

  if (!candidates || candidates.length === 0) {
    closeAtSuggestMenu();
    return;
  }

  state.atMenuOpen = true;
  state.atCandidates = candidates.slice(0, 9);
  if (state.atActiveIdx >= state.atCandidates.length) {
    state.atActiveIdx = 0;
  }

  menu.innerHTML =
    `<div class="at-menu-head"><span>引用项目源码（>350行自动提炼大纲骨架 · 支持 @路径:起始行-结束行 切片）</span><span>↑↓ · Enter</span></div>` +
    state.atCandidates
      .map(
        (item, idx) => `
        <div class="at-menu-item ${idx === state.atActiveIdx ? "active" : ""}" data-at-idx="${idx}">
          <span class="at-file-path">${escapeHtml(item.label || `@${item.path}`)}</span>
          <span class="at-file-meta">${escapeHtml(item.meta || (item.size_kb ? `${item.size_kb} KB` : ""))}</span>
        </div>
      `
      )
      .join("");
  menu.classList.remove("hidden");
}

function applyAtSuggestion(idx) {
  const item = state.atCandidates[idx];
  const input = el("topicInput");
  if (!item || !input) {
    closeAtSuggestMenu();
    return;
  }
  if (item.isBindAction) {
    closeAtSuggestMenu();
    pickWorkspaceFolder(false);
    return;
  }
  const range = state.atTokenRange;
  if (!range) {
    closeAtSuggestMenu();
    return;
  }
  const insertStr = item.insertText || `@${item.path} `;
  const before = input.value.slice(0, range.start);
  const after = input.value.slice(range.end);
  input.value = `${before}${insertStr}${after}`;
  const caret = before.length + insertStr.length;
  closeAtSuggestMenu();
  autoResizeComposer();
  renderAttachedFileChips();
  input.focus();
  input.setSelectionRange(caret, caret);
}

function handleComposerAtTrigger() {
  const input = el("topicInput");
  if (!input) return;
  renderAttachedFileChips();

  const caret = input.selectionStart || 0;
  const beforeCaret = input.value.slice(0, caret);
  const m = beforeCaret.match(/(?:^|\s)@([A-Za-z0-9_\u4e00-\u9fa5./-]*)$/);
  if (!m) {
    closeAtSuggestMenu();
    return;
  }

  const query = m[1] || "";
  const tokenStart = caret - query.length - 1;
  state.atTokenRange = { start: tokenStart, end: caret };

  const wsDir = state.sessionWorkspaceDir || state.systemStatus?.workspace_dir || "";
  const unbound = isUnboundWorkspace(wsDir);
  const qLow = query.toLowerCase();

  const seatItems = state.currentTopic
    ? state.enabledAgents
        .map((aid) => {
          const pspec = getPersonaSpec(state.seatPersonas[aid], aid);
          return {
            path: AGENT_NAMES[aid],
            label: `@${AGENT_NAMES[aid]}`,
            insertText: `@${AGENT_NAMES[aid]} `,
            meta: `${pspec.label}席位`,
          };
        })
        .filter((s) => !qLow || s.path.toLowerCase().startsWith(qLow))
    : [];

  if (unbound) {
    if (seatItems.length > 0 && qLow) {
      renderAtSuggestMenu(seatItems, false);
    } else if (!query) {
      renderAtSuggestMenu([], true);
    } else {
      closeAtSuggestMenu();
    }
    return;
  }

  const filterLocal = (files) => {
    const matchedFiles = files
      .filter((f) => {
        if (!qLow) return true;
        return f.path.toLowerCase().includes(qLow);
      })
      .slice(0, 8)
      .map((f) => ({
        path: f.path,
        label: `@${f.path}`,
        insertText: `@${f.path} `,
        meta: f.size_kb ? `${f.size_kb} KB` : "源码",
      }));
    renderAtSuggestMenu([...seatItems, ...matchedFiles], false);
  };

  if (state.workspaceFiles.length > 0 && query.length <= 2) {
    filterLocal(state.workspaceFiles);
  } else {
    if (atSearchTimer) clearTimeout(atSearchTimer);
    atSearchTimer = setTimeout(async () => {
      const files = await refreshWorkspaceFilesIndex(query);
      filterLocal(files.length ? files : state.workspaceFiles);
    }, 60);
  }
}

function renderAttachedFileChips() {
  const bar = el("attachedFilesBar");
  const input = el("topicInput");
  if (!bar || !input) return;

  const text = input.value || "";
  const matches = [...text.matchAll(AT_REF_REGEX)];
  if (matches.length === 0) {
    bar.classList.add("hidden");
    bar.innerHTML = "";
    return;
  }

  const wsDir = state.sessionWorkspaceDir || state.systemStatus?.workspace_dir || "";
  const unbound = isUnboundWorkspace(wsDir);
  const seen = new Set();
  const chips = [];

  matches.forEach((m) => {
    const fullToken = m[0];
    const relPath = (m[1] || "").replace(/^\/+/, "");
    const rangeTxt = m[2] ? `:${m[2]}${m[3] ? `-${m[3]}` : ""}` : "";
    if (seen.has(fullToken)) return;
    seen.add(fullToken);

    let cls = "file-chip-valid";
    let statusHint = rangeTxt
      ? "已就绪 · 发送时按行号区间精准切片注入"
      : "已就绪 · ≤350行注入源码，>350行自动提取头说明+行号大纲骨架";
    let badgeTxt = rangeTxt ? "行切片" : "";
    if (unbound) {
      cls = "file-chip-warn";
      statusHint = "尚未绑定本地项目目录，点击绑定后生效";
      badgeTxt = "未绑目录";
    } else if (state.workspaceFileSet.size > 0 && !state.workspaceFileSet.has(relPath)) {
      cls = "file-chip-warn";
      statusHint = `当前绑定项目中未找到 ${relPath}，请检查路径拼写`;
      badgeTxt = "路径未找到";
    }

    chips.push(`
      <span class="attached-file-chip ${cls}" title="${escapeHtml(statusHint)}" data-raw-token="${escapeHtml(fullToken)}">
        <span class="chip-file-icon">${cls === "file-chip-valid" ? "📄" : "⚠️"}</span>
        <span class="chip-file-name">@${escapeHtml(relPath)}${escapeHtml(rangeTxt)}</span>
        ${badgeTxt ? `<em class="chip-file-status">${escapeHtml(badgeTxt)}</em>` : ""}
        <button type="button" class="chip-file-remove" data-remove-ref="${escapeHtml(fullToken)}" title="移除该引用">✕</button>
      </span>
    `);
  });

  bar.innerHTML = `<span class="attached-bar-label">已挂载源码：</span>` + chips.join("");
  bar.classList.remove("hidden");
}

// ==================== 顶栏席位轻量配置浮层 & 参会阵容预设 ====================

function closePersonaPopover() {
  state.activePersonaSeat = null;
  state.activePopoverAnchor = null;
  el("personaPopover")?.classList.add("hidden");
}

function renderSeatPopoverContents(agentId) {
  const titleEl = el("personaPopoverTitle");
  const quickEl = el("seatPopoverQuickActions");
  const effortEl = el("seatPopoverEffortBox");
  const listEl = el("personaOptionList");
  if (!listEl || !agentId) return;

  const seatName = AGENT_NAMES[agentId] || agentId;
  const isSolo = state.enabledAgents.length === 1 && state.enabledAgents[0] === agentId;
  const seatOn = state.enabledAgents.includes(agentId);
  const info = state.systemStatus?.agents?.[agentId] || {};
  const shownModel = info.effective_model || info.model || "";

  if (titleEl) {
    titleEl.textContent = `${seatName} · 席位快捷控制${shownModel ? ` (${shownModel})` : ""}`;
  }

  if (quickEl) {
    quickEl.innerHTML = `
      <button type="button" class="seat-pop-btn primary-act" data-seat-pop-act="mention" title="在底部输入框插入 @${escapeHtml(seatName)} 点名回应">
        <span>@${escapeHtml(seatName)} 点名</span>
      </button>
      <button type="button" class="seat-pop-btn ${isSolo ? "active" : ""}" data-seat-pop-act="solo" title="${isSolo ? "恢复三席多视角圆桌" : `仅由 ${escapeHtml(seatName)} 单人包揽设计与落地执行`}">
        <span>${isSolo ? "✓ 独奏中（点此恢复三席）" : "🎯 仅该席独奏"}</span>
      </button>
      <button type="button" class="seat-pop-btn ${seatOn ? "" : "warn-act"}" data-seat-pop-act="toggle-enable" title="${seatOn ? `暂停 ${escapeHtml(seatName)} 参会` : `恢复 ${escapeHtml(seatName)} 参会`}">
        <span>${seatOn ? "⏸ 暂停参会" : "▶ 恢复参会"}</span>
      </button>
    `;
  }

  if (effortEl) {
    const spec = resolveFrontendEffortSpec(info.driver || info.effective_driver, shownModel, agentId);
    if (!spec.supportsEffort || !spec.allowed.length) {
      effortEl.innerHTML = `<div class="seat-pop-effort-note">当前模型自动省略 <code>--effort</code> 参数</div>`;
    } else {
      const curEffort = clampEffortBySpec(
        info.effective_discussion_effort || info.discussion_effort || spec.defaultEffort,
        spec,
        false
      );
      const isLocked = Boolean(info.lock_discussion_effort);
      const hasHighTier = spec.allowed.includes("xhigh") || spec.allowed.includes("max");
      effortEl.innerHTML = `
        <div class="seat-pop-effort-head">
          <span>讨论推理档位</span>
          ${
            hasHighTier
              ? `<button type="button" class="seat-lock-pill ${isLocked ? "locked" : ""}" data-seat-pop-lock="1" title="默认第 1–2 轮自动将 xhigh/max 降为 high 提速；开启强锁后全程保持所选最高档">
                  ${isLocked ? "🔒 已强锁高档" : "⚡ 首2轮自动降high提速"}
                 </button>`
              : ""
          }
        </div>
        <div class="seat-effort-pills">
          ${spec.allowed
            .map(
              (lv) =>
                `<button type="button" class="seat-effort-pill ${lv === curEffort ? "active" : ""}" data-seat-pop-effort="${escapeHtml(lv)}">${escapeHtml(lv)}</button>`
            )
            .join("")}
        </div>
      `;
    }
  }

  const curKey = state.seatPersonas[agentId] || "planner";
  const presets = getPersonaMap();
  const order = [
    "planner",
    "fullstack_solo",
    "red_team",
    "implementer",
    "product_ux",
    "perf_sre",
    "qa_audit",
  ];

  listEl.innerHTML = order
    .filter((k) => presets[k])
    .map((k) => {
      const p = presets[k];
      const active = k === curKey;
      const shortDesc = String(p.prompt || "")
        .replace(/^思维模型[:：]\s*/, "")
        .slice(0, 44);
      return `
        <button type="button" class="persona-opt-btn ${active ? "active" : ""}" data-pick-persona="${escapeHtml(k)}">
          <div class="persona-opt-top">
            <span>${escapeHtml(p.label)}（${escapeHtml(p.short_tag)}）</span>
            ${active ? "<span>✓</span>" : ""}
          </div>
          <div class="persona-opt-desc">${escapeHtml(shortDesc)}</div>
        </button>
      `;
    })
    .join("");
}

function openPersonaPopover(agentId, anchorBtn) {
  const pop = el("personaPopover");
  if (!pop || !anchorBtn) return;

  if (state.activePersonaSeat === agentId && !pop.classList.contains("hidden")) {
    closePersonaPopover();
    return;
  }

  state.activePersonaSeat = agentId;
  state.activePopoverAnchor = anchorBtn;
  renderSeatPopoverContents(agentId);

  pop.classList.remove("hidden");
  const rect = anchorBtn.getBoundingClientRect();
  const popWidth = Math.max(304, pop.offsetWidth || 312);
  const popHeight = Math.min(480, pop.offsetHeight || 420);
  const left = Math.max(12, Math.min(rect.left, window.innerWidth - popWidth - 12));
  const top = Math.max(12, Math.min(rect.bottom + 8, window.innerHeight - popHeight - 12));
  pop.style.left = `${left}px`;
  pop.style.top = `${top}px`;
}

async function toggleSoloSeat(agentId) {
  if (!state.currentSessionId || !AGENT_NAMES[agentId]) return;
  const isAlreadySolo = state.enabledAgents.length === 1 && state.enabledAgents[0] === agentId;
  const nextEnabled = isAlreadySolo ? [...AGENT_ORDER] : [agentId];
  const nextExec = isAlreadySolo ? "astra" : agentId;
  try {
    const res = await apiFetch(`/api/sessions/${state.currentSessionId}/seats`, {
      method: "POST",
      body: JSON.stringify({
        enabled_agents: nextEnabled,
        executor_agent: nextExec,
      }),
    });
    applySeatsResponse(res);
    if (state.activePersonaSeat === agentId) {
      renderSeatPopoverContents(agentId);
    }
    showToast(
      isAlreadySolo
        ? "已恢复三席多视角圆桌模式"
        : `已切换为 ${AGENT_NAMES[agentId]} 独奏模式（单人包揽设计与执行）`,
      "ok",
      2000
    );
  } catch (err) {
    showToast(err.message, "err");
  }
}

async function toggleSeatParticipation(agentId) {
  if (!state.currentSessionId || !AGENT_NAMES[agentId]) return;
  const isCurrentlyOn = state.enabledAgents.includes(agentId);
  const nextList = isCurrentlyOn
    ? state.enabledAgents.filter((x) => x !== agentId)
    : AGENT_ORDER.filter((x) => x === agentId || state.enabledAgents.includes(x));
  if (nextList.length === 0) {
    showToast("至少需要保留一位参会成员", "warn");
    return;
  }
  try {
    const res = await apiFetch(`/api/sessions/${state.currentSessionId}/seats`, {
      method: "POST",
      body: JSON.stringify({ enabled_agents: nextList }),
    });
    applySeatsResponse(res);
    if (state.activePersonaSeat === agentId) {
      renderSeatPopoverContents(agentId);
    }
    showToast(
      `${AGENT_NAMES[agentId]} 已${isCurrentlyOn ? "暂停参会" : "加入参会"}`,
      "info",
      1600
    );
  } catch (err) {
    showToast(err.message, "err");
  }
}

async function updateSeatEffortQuickly(agentId, patch) {
  if (!AGENT_NAMES[agentId]) return;
  try {
    const res = await apiFetch("/api/config", {
      method: "POST",
      body: JSON.stringify({
        active_session_id: state.currentSessionId || "",
        agents: { [agentId]: patch },
      }),
    });
    if (res.system) {
      renderSystemStatus(res.system);
    }
    if (state.activePersonaSeat === agentId) {
      renderSeatPopoverContents(agentId);
    }
    const updated = res.system?.agents?.[agentId];
    if (patch.discussion_effort) {
      showToast(`${AGENT_NAMES[agentId]} 讨论推理档位已设为 ${updated?.effective_discussion_effort || patch.discussion_effort}`, "ok", 1800);
    } else if (patch.lock_discussion_effort !== undefined) {
      showToast(
        patch.lock_discussion_effort
          ? `已强锁 ${AGENT_NAMES[agentId]} 在第 1–2 轮保持最高推理档`
          : `已恢复 ${AGENT_NAMES[agentId]} 第 1–2 轮自动降为 high 提速`,
        "info",
        2000
      );
    }
  } catch (err) {
    showToast(`更新档位失败：${err.message}`, "err");
  }
}

async function applySeatPersonaChange(agentId, personaKey) {
  closePersonaPopover();
  if (!state.currentSessionId || !agentId || !personaKey) return;
  try {
    const res = await apiFetch(`/api/sessions/${state.currentSessionId}/seats`, {
      method: "POST",
      body: JSON.stringify({ seat_personas: { [agentId]: personaKey } }),
    });
    applySeatsResponse(res);
    const pspec = getPersonaSpec(personaKey, agentId);
    showToast(`${AGENT_NAMES[agentId]} 已切换为「${pspec.label}」身份`, "ok", 1800);
  } catch (err) {
    showToast(`切换身份失败：${err.message}`, "err");
  }
}

function detectActiveLineupPreset() {
  const agentsSys = state.systemStatus?.agents || {};
  const drivers = AGENT_ORDER.map((a) => agentsSys[a]?.effective_driver || agentsSys[a]?.driver || "");
  const allSameDriver =
    state.enabledAgents.length === 3 &&
    drivers[0] &&
    drivers.every((d) => d === drivers[0]) &&
    agentsSys.carbon?.driver === agentsSys.grok?.driver &&
    agentsSys.grok?.driver === agentsSys.astra?.driver;
  if (state.enabledAgents.length === 1) {
    return "solo_lead";
  }
  if (allSameDriver) {
    return "single_cli";
  }
  if (
    state.seatPersonas.grok === "red_team" &&
    state.seatPersonas.astra === "qa_audit"
  ) {
    return "red_blue";
  }
  return "triad";
}

function syncLineupPresetUI() {
  const activeKey = detectActiveLineupPreset();
  document.querySelectorAll("[data-lineup-preset]").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.lineupPreset === activeKey);
  });
}

async function applyLineupPreset(presetKey) {
  if (!state.currentSessionId) return;
  try {
    if (presetKey === "single_cli") {
      const chosenDriver = detectFirstReadyDriver();
      const defaultModelMap = {
        agy: "gemini-4-carbon",
        grok: "grok-4.7",
        codex: "gpt-6-astra",
      };
      const triadPersonas = { carbon: "planner", grok: "red_team", astra: "implementer" };
      const agentsPayload = {};
      AGENT_ORDER.forEach((aid) => {
        const spec = resolveFrontendEffortSpec(chosenDriver, defaultModelMap[chosenDriver] || "", aid);
        agentsPayload[aid] = {
          driver: chosenDriver,
          persona: triadPersonas[aid],
          model: defaultModelMap[chosenDriver] || "",
          discussion_effort: spec.defaultEffort,
          execution_effort: spec.defaultEffort,
        };
      });
      const cfgRes = await apiFetch("/api/config", {
        method: "POST",
        body: JSON.stringify({
          active_session_id: state.currentSessionId,
          allow_single_cli_fallback: true,
          agents: agentsPayload,
        }),
      });
      if (cfgRes.system) renderSystemStatus(cfgRes.system);
      const seatRes = await apiFetch(`/api/sessions/${state.currentSessionId}/seats`, {
        method: "POST",
        body: JSON.stringify({
          enabled_agents: ["carbon", "grok", "astra"],
          seat_personas: triadPersonas,
          executor_agent: "astra",
        }),
      });
      applySeatsResponse(seatRes);
      showToast(`已切换为「单 CLI 分饰三席」（使用 ${chosenDriver} 串行无状态发言）`, "ok", 2400);
      return;
    }

    // 若之前处于「单 CLI 分饰三席」锁定同源驱动状态，切回多席预设时自动恢复三席默认异构驱动
    const curSysAgents = state.systemStatus?.agents || {};
    if (
      curSysAgents.carbon?.driver &&
      curSysAgents.carbon?.driver === curSysAgents.grok?.driver &&
      curSysAgents.grok?.driver === curSysAgents.astra?.driver
    ) {
      const resetRes = await apiFetch("/api/config", {
        method: "POST",
        body: JSON.stringify({
          active_session_id: state.currentSessionId,
          allow_single_cli_fallback: true,
          agents: {
            carbon: { driver: "agy", model: "" },
            grok: { driver: "grok", model: "" },
            astra: { driver: "codex", model: "" },
          },
        }),
      });
      if (resetRes.system) renderSystemStatus(resetRes.system);
    }

    if (presetKey === "solo_lead") {
      const readySeat =
        AGENT_ORDER.find((a) => state.systemStatus?.agents?.[a]?.binary_detected && a === "astra") ||
        AGENT_ORDER.find((a) => state.systemStatus?.agents?.[a]?.binary_detected) ||
        "carbon";
      const seatRes = await apiFetch(`/api/sessions/${state.currentSessionId}/seats`, {
        method: "POST",
        body: JSON.stringify({
          enabled_agents: [readySeat],
          seat_personas: { [readySeat]: "fullstack_solo" },
          executor_agent: readySeat,
        }),
      });
      applySeatsResponse(seatRes);
      showToast(`已切换为「单席主程」模式：由 ${AGENT_NAMES[readySeat]} 独立完成方案与执行`, "ok", 2200);
      return;
    }

    if (presetKey === "red_blue") {
      syncCollabModeUI("red_blue_debate");
      const seatRes = await apiFetch(`/api/sessions/${state.currentSessionId}/seats`, {
        method: "POST",
        body: JSON.stringify({
          enabled_agents: ["carbon", "grok", "astra"],
          seat_personas: { carbon: "planner", grok: "red_team", astra: "qa_audit" },
          executor_agent: "carbon",
        }),
      });
      applySeatsResponse(seatRes);
      showToast("已切换为「红蓝质询」阵容（规划立论 + 红队挑刺 + 测试验收）", "ok", 2200);
      return;
    }

    // 默认 triad 三席圆桌
    const seatRes = await apiFetch(`/api/sessions/${state.currentSessionId}/seats`, {
      method: "POST",
      body: JSON.stringify({
        enabled_agents: ["carbon", "grok", "astra"],
        seat_personas: { carbon: "planner", grok: "red_team", astra: "implementer" },
        executor_agent: "astra",
      }),
    });
    applySeatsResponse(seatRes);
    showToast("已切换为「三席圆桌」标准阵容（规划 + 挑刺 + 落地）", "ok", 2000);
  } catch (err) {
    showToast(`切换阵容失败：${err.message}`, "err");
  }
}

function applySeatsResponse(res) {
  if (!res) return;
  if (Array.isArray(res.enabled_agents)) {
    state.enabledAgents = res.enabled_agents;
  }
  if (res.seat_personas && typeof res.seat_personas === "object") {
    state.seatPersonas = { ...state.seatPersonas, ...res.seat_personas };
  }
  if (res.executor_agent) {
    state.executorAgent = res.executor_agent;
  }
  if (res.seat_states && typeof res.seat_states === "object") {
    Object.values(res.seat_states).forEach((st) => {
      state.seatStates[st.agent_id] = st;
      updateSeatUI(st);
    });
  }
  syncPersonasAndExecutorUI();
  syncComposerAndControls();
}

function syncPersonasAndExecutorUI() {
  const isSolo = state.enabledAgents.length === 1;
  const soloAid = isSolo ? state.enabledAgents[0] : "";
  const execAid = AGENT_NAMES[state.executorAgent] ? state.executorAgent : "astra";
  const execName = AGENT_NAMES[execAid] || "Astra";

  // 1. 席位胶囊头衔与独奏/暂停状态同步
  AGENT_ORDER.forEach((aid) => {
    const pKey = state.seatPersonas[aid] || "planner";
    const pspec = getPersonaSpec(pKey, aid);
    const thisSolo = isSolo && soloAid === aid;
    const seatOn = state.enabledAgents.includes(aid);
    const roleTxt = el(`seat-role-text-${aid}`);
    if (roleTxt) {
      roleTxt.textContent = thisSolo ? `${pspec.short_tag} · 独奏` : pspec.short_tag;
    }

    const card = el(`seat-${aid}`);
    if (card) {
      card.classList.toggle("seat-is-solo", thisSolo);
      card.classList.toggle("seat-disabled", !seatOn);
    }
  });

  syncLineupPresetUI();

  // 2. 动态生成底部快捷点名追问按钮组 (#cueGroupLeft)
  const cueLeft = el("cueGroupLeft");
  if (cueLeft) {
    cueLeft.innerHTML = state.enabledAgents
      .map((aid) => {
        const st = state.seatStates[aid];
        const pspec = getPersonaSpec(state.seatPersonas[aid], aid);
        const btnLabel = st?.cue_btn || (pspec.cue_btn || "请 {name} 分析").replace("{name}", AGENT_NAMES[aid]);
        const cuePrompt = st?.cue_prompt || pspec.cue_prompt || "请补充深化当前方案要点";
        return `<button type="button" class="cue-btn" data-cue-agent="${escapeHtml(aid)}" data-cue-text="${escapeHtml(cuePrompt)}">${escapeHtml(btnLabel)}</button>`;
      })
      .join("");
  }

  // 3. 同步底部点名芯片栏（独奏模式展示专属提示）
  const mentionLabel = el("mentionBarLabel");
  const mentionWrap = el("mentionChipsWrap");
  if (mentionWrap) {
    if (isSolo && soloAid) {
      const soloSpec = getPersonaSpec(state.seatPersonas[soloAid], soloAid);
      if (mentionLabel) mentionLabel.textContent = "当前模式：";
      mentionWrap.innerHTML = `<span class="solo-mention-pill">🎯 ${escapeHtml(AGENT_NAMES[soloAid])}（${escapeHtml(soloSpec.label)}）独奏中 · 直接输入即可追问或交由其执行</span>`;
    } else {
      if (mentionLabel) mentionLabel.textContent = "点名回应：";
      mentionWrap.innerHTML = state.enabledAgents
        .map(
          (aid) =>
            `<button type="button" class="mention-btn" data-mention-seat="${escapeHtml(aid)}" data-mention="@${escapeHtml(AGENT_NAMES[aid])} " title="点名 ${escapeHtml(AGENT_NAMES[aid])} 回应">@${escapeHtml(AGENT_NAMES[aid])}</button>`
        )
        .join("");
    }
  }

  // 4. 同步主刀执行席位切换器与按钮文案
  document.querySelectorAll("#executorSegmented .seg-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.execAgent === execAid);
  });
  const quickExecBtn = el("executeBtn");
  if (quickExecBtn) {
    quickExecBtn.textContent = `交由 ${execName} 执行 →`;
  }
  syncExecModeUI();
}

// ==================== 外观与工作区状态同步 ====================

function updateThemeUI(theme) {
  const safeTheme = theme === "dark" ? "dark" : "light";
  document.documentElement.dataset.theme = safeTheme;
  localStorage.setItem("ai_roundtable_theme_v2", safeTheme);
  document.querySelectorAll("[data-theme-opt]").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.themeOpt === safeTheme);
  });
  const curPalette = document.documentElement.dataset.palette || "pearl";
  document.querySelectorAll("[data-palette-opt]").forEach((btn) => {
    btn.classList.toggle("active", safeTheme === "light" && btn.dataset.paletteOpt === curPalette);
  });
}

function updatePaletteUI(paletteKey) {
  const found = PALETTES.find((p) => p.key === paletteKey) || PALETTES[0];
  document.documentElement.dataset.palette = found.key;
  localStorage.setItem("ai_roundtable_palette", found.key);
  const isLight = (document.documentElement.dataset.theme || "light") !== "dark";
  document.querySelectorAll("[data-palette-opt]").forEach((btn) => {
    btn.classList.toggle("active", isLight && btn.dataset.paletteOpt === found.key);
  });
  const o1 = el("ambientOrb1");
  const o2 = el("ambientOrb2");
  if (o1) o1.style.background = "";
  if (o2) o2.style.background = "";
}

function updateFontScaleUI(scaleKey) {
  const found = FONT_SCALES.find((f) => f.key === scaleKey) || FONT_SCALES[0];
  document.documentElement.dataset.fontsize = found.key;
  localStorage.setItem("ai_roundtable_fontsize", found.key);
  document.querySelectorAll("[data-font-opt]").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.fontOpt === found.key);
  });
}

function closeAppearancePopover() {
  const pop = el("appearancePopover");
  const btn = el("appearanceBtn");
  if (pop) pop.classList.add("hidden");
  if (btn) {
    btn.classList.remove("active-pane");
    btn.setAttribute("aria-expanded", "false");
  }
}

function shiftAmbientGlowForSpeaker(agentId) {
  if (document.documentElement.dataset.theme === "dark") return;
  const pair = SPEAKER_AMBIENT_GLOW[agentId];
  if (!pair) return;
  const o1 = el("ambientOrb1");
  const o2 = el("ambientOrb2");
  if (o1) o1.style.background = pair[0];
  if (o2) o2.style.background = pair[1];
}

function isUnboundWorkspace(wsDir) {
  if (!wsDir) return true;
  const norm = String(wsDir).trim().replace(/\/+$/, "");
  if (!norm || norm === "workspace") return true;
  if (norm.endsWith("/.ai-roundtable/workspace") || norm.endsWith("/.ai-roundtable")) {
    return true;
  }
  return false;
}

function syncExecModeUI() {
  const wsDir = state.sessionWorkspaceDir || state.systemStatus?.workspace_dir || "";
  const unbound = isUnboundWorkspace(wsDir);
  const parts = wsDir.split("/").filter(Boolean);
  const folderName = !unbound && parts.length ? parts[parts.length - 1] : wsDir;
  const isWrite = Boolean(el("allowWriteCheckbox")?.checked);
  const isExecRunning = state.isBusy && state.stage === "executing";
  const execAid = AGENT_NAMES[state.executorAgent] ? state.executorAgent : "astra";
  const execName = AGENT_NAMES[execAid] || "Astra";

  const runBtn = el("runExecFromTabBtn");
  const stopExecBtn = el("stopExecFromTabBtn");
  if (runBtn) {
    runBtn.disabled = isExecRunning;
    runBtn.textContent = isExecRunning ? `${execName} 正在执行中…` : `启动 ${execName} 执行`;
  }
  if (stopExecBtn) {
    stopExecBtn.classList.toggle("hidden", !isExecRunning);
  }

  const termTitle = el("termTargetTitle");
  if (termTitle) {
    termTitle.textContent = unbound
      ? `${execAid} · 方案交付终端（未绑定项目）`
      : `${execAid} · ${folderName}${state.workspaceIsGit ? " (Git)" : ""}`;
  }

  const desc = el("execModeDesc");
  if (!desc) return;
  if (unbound) {
    if (isWrite) {
      desc.textContent =
        "当前尚未绑定本地项目：建议先点击左上「选择本地项目」绑定代码仓库，否则仅在默认沙箱输出完整落地方案报告。";
      desc.classList.add("warn");
    } else {
      desc.textContent = `当前尚未绑定本地项目：点击执行将由 ${execName} 基于白板共识输出完整的《工程落地方案与实施报告》。`;
      desc.classList.remove("warn");
    }
  } else if (isWrite) {
    if (state.workspaceIsGit) {
      desc.textContent = `已绑定「${folderName}」(Git 仓库) · 写入模式：授权 ${execName} 直接修改本地文件，执行前自动保存 Git 快照并支持一键回滚。`;
    } else {
      desc.textContent = `⚠ 已绑定「${folderName}」（未检测到 Git 仓库）· 写入模式：${execName} 修改将直接覆写磁盘文件，不支持一键 Git 回滚！`;
    }
    desc.classList.add("warn");
  } else {
    desc.textContent = `已绑定「${folderName}」· 只读预演：${execName} 不改动磁盘文件，实时流式输出实施方案与 Unified Diff 补丁预览。`;
    desc.classList.remove("warn");
  }
}

function updateWorkspaceCardDisplay(dirPath, isGitOverride = undefined) {
  const prevDir = state.sessionWorkspaceDir;
  const wsDir = dirPath || state.systemStatus?.workspace_dir || "";
  if (typeof isGitOverride === "boolean") {
    state.workspaceIsGit = isGitOverride;
  }
  const unbound = isUnboundWorkspace(wsDir);
  const parts = wsDir.split("/").filter(Boolean);
  const folderName = parts.length ? parts[parts.length - 1] : wsDir;

  const wsNameEl = el("workspaceName");
  const wsBadgeEl = el("workspaceBadge");
  if (wsNameEl) {
    wsNameEl.textContent = unbound ? "选择本地项目" : folderName;
  }
  if (wsBadgeEl) {
    wsBadgeEl.textContent = unbound ? "尚未绑定本地项目目录" : wsDir;
    wsBadgeEl.title = unbound ? "" : wsDir;
  }

  const pickQuickBtn = el("pickFolderQuickBtn");
  if (pickQuickBtn) {
    pickQuickBtn.textContent = unbound ? "选择目录" : "切换目录";
  }

  const emptyWsNameEl = el("emptyWsName");
  const emptyBindBtn = el("emptyBindWsBtn");
  if (emptyWsNameEl) {
    emptyWsNameEl.textContent = unbound
      ? "点击绑定本地项目目录"
      : `${folderName}${state.workspaceIsGit ? " · Git" : ""}`;
  }
  if (emptyBindBtn) {
    emptyBindBtn.classList.toggle("ws-bound", !unbound);
    emptyBindBtn.title = unbound ? "点击选择本地项目文件夹" : `当前已绑定：${wsDir}（点击切换）`;
  }

  const headerName = el("headerWsName");
  const headerChip = el("headerWsChip");
  if (headerName && headerChip) {
    headerName.textContent = unbound ? "选择本地项目" : folderName;
    headerChip.classList.toggle("ws-unbound", unbound);
    headerChip.classList.toggle("ws-bound", !unbound);
    headerChip.title = unbound
      ? "尚未绑定本地项目，点击绑定本地代码仓库"
      : `当前绑定项目：${wsDir}${state.workspaceIsGit ? "（已启用 Git 护栏）" : "（非 Git 目录）"} — 点击切换`;
  }

  syncExecModeUI();
  if (!unbound && (wsDir !== prevDir || state.workspaceFiles.length === 0)) {
    refreshWorkspaceFilesIndex("");
  } else if (unbound) {
    state.workspaceFiles = [];
    state.workspaceFileSet.clear();
    renderAttachedFileChips();
  }
}

function formatConciseTopStatus(rawStatus) {
  const s = String(rawStatus || "").trim();
  if (!s || s === "待输入议题") return "";
  if (s.includes("独奏方案设计")) return "独奏设计中";
  if (s.includes("独奏方案就绪")) return "独奏就绪";
  if (s.includes("分饰") && s.includes("初评")) return "串行初评";
  if (s.includes("并发初评") || s.includes("正在初评")) return "并发初评";
  const roundMatch = s.match(/交叉讨论[（(](\d+\/\d+)[)）]/);
  if (roundMatch) return `交叉讨论 ${roundMatch[1]}`;
  if (s.includes("单席重试") || s.includes("正在重试")) return "单席重试";
  if (s.includes("未完成") || s.includes("异常") || s.includes("失败")) return "待重试";
  if (s.includes("讨论完成")) return "待决议";
  if (s.includes("汇总") && s.includes("决议")) return "汇总决议中";
  if (s.includes("已形成决议")) return "已形成决议";
  if (s.includes("已完成回应") || s.includes("待主持人下一步")) return "待追问";
  if (s.includes("已暂停") || s.includes("已停止")) return "已暂停";
  if (s.includes("执行中")) return "执行中";
  if (s.includes("执行已完成")) return "已交付";
  return s.length > 10 ? `${s.slice(0, 10)}…` : s;
}

function syncStageStatusPill(rawStatus) {
  const pill = el("stageStatusPill");
  if (!pill) return;
  const hasTopic = Boolean(state.currentTopic && state.currentTopic.trim());
  const concise = !hasTopic && state.stage === "idle" ? "" : formatConciseTopStatus(rawStatus);
  pill.textContent = concise;
  pill.classList.toggle("hidden", !concise);
  pill.classList.toggle("pill-busy", state.isBusy);
  pill.classList.toggle("pill-done", state.stage === "concluded" && !state.isBusy);
}

function syncCollabModeUI(modeKey) {
  const safeMode = MODE_HINTS[modeKey] ? modeKey : "standard_roundtable";
  const sel = el("collabModeSelect");
  if (sel) sel.value = safeMode;
  const hint = el("collabModeHint");
  if (hint) hint.textContent = MODE_HINTS[safeMode] || "";
  document.querySelectorAll("[data-collab-opt]").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.collabOpt === safeMode);
  });
  const inlineDesc = el("composerModeDesc");
  if (inlineDesc) inlineDesc.textContent = SHORT_MODE_HINTS[safeMode] || "";
}

function updateStageStepper(stage) {
  const order = ["opening", "discussion", "consensus", "execution"];
  let activeIdx = -1;
  let completedUpTo = -1;

  if (stage === "opening_parallel") {
    activeIdx = 0;
  } else if (stage === "cross_talk" || stage === "chair_interrupt") {
    completedUpTo = 0;
    activeIdx = 1;
  } else if (stage === "awaiting_chair") {
    completedUpTo = 1;
    activeIdx = 2;
  } else if (stage === "concluded") {
    completedUpTo = 2;
    activeIdx = -1;
  } else if (stage === "executing") {
    completedUpTo = 2;
    activeIdx = 3;
  }

  document.querySelectorAll("#stageStepper .step-item").forEach((node) => {
    const idx = order.indexOf(node.dataset.step);
    node.classList.toggle("done", idx <= completedUpTo);
    node.classList.toggle("active", idx === activeIdx);
  });
}

function syncComposerAndControls() {
  const hasTopic = Boolean(state.currentTopic && state.currentTopic.trim());
  const execName = AGENT_NAMES[state.executorAgent] || "Astra";
  const primaryBtn = el("primaryActionBtn");
  const stopBtn = el("stopFlowBtn");
  const quickCueBar = el("quickCueBar");
  const cueGroupLeft = el("cueGroupLeft");
  const cueBusyBanner = el("cueBusyBanner");
  const cueBusyText = el("cueBusyText");
  const cueDecisionGroup = el("cueDecisionGroup");
  const composerToolbar = el("composerToolbar");
  const preModeBar = el("preMeetingModeBar");
  const activeMentionBar = el("activeMentionBar");
  const input = el("topicInput");
  const box = el("composerBox");
  const chairHint = el("chairActionHint");

  syncStageStatusPill(state.whiteboard?.consensus_status || "");
  syncExecModeUI();

  if (state.isBusy && state.stage === "executing") {
    if (!state.execStartTs) {
      state.execStartTs = Date.now();
      ensureThinkingTicker();
    }
    el("execLiveTimer")?.classList.remove("hidden");
  } else {
    state.execStartTs = 0;
    el("execLiveTimer")?.classList.add("hidden");
    stopThinkingTickerIfIdle();
  }

  if (!state.isBusy) {
    resetClientBusyTimersIfIdle();
  }

  if (!hasTopic) {
    if (quickCueBar) quickCueBar.classList.add("hidden");
    if (cueBusyBanner) cueBusyBanner.classList.add("hidden");
    if (stopBtn) stopBtn.classList.add("hidden");
    if (composerToolbar) composerToolbar.classList.remove("hidden");
    if (preModeBar) preModeBar.classList.remove("hidden");
    if (activeMentionBar) activeMentionBar.classList.add("hidden");

    if (primaryBtn) {
      primaryBtn.textContent = state.enabledAgents.length === 1 ? "开始独奏" : "开始讨论";
      primaryBtn.className = "primary-send-btn";
    }
    if (box) box.classList.remove("interrupt-mode");
    if (input) input.placeholder = "输入议题开启圆桌或独奏（敲 @ 引用项目源码，Shift+Enter 换行 · Enter 发送）";
    if (chairHint) chairHint.textContent = "随时插话 / @点名";
  } else if (state.isBusy) {
    const isExec = state.stage === "executing";
    if (quickCueBar) quickCueBar.classList.remove("hidden");
    if (cueGroupLeft) cueGroupLeft.classList.add("hidden");
    if (cueDecisionGroup) cueDecisionGroup.classList.add("hidden");
    if (cueBusyBanner) cueBusyBanner.classList.remove("hidden");
    if (cueBusyText) {
      cueBusyText.textContent = isExec
        ? `${execName} 正在实时执行落地，可在右侧终端查看进展或点击停止`
        : "讨论进行中，可直接输入插话或点击右侧停止";
    }
    if (stopBtn) {
      stopBtn.classList.remove("hidden");
      stopBtn.textContent = isExec ? "■ 停止执行" : "■ 停止发言";
    }

    if (composerToolbar) composerToolbar.classList.add("hidden");
    if (preModeBar) preModeBar.classList.add("hidden");
    if (activeMentionBar) activeMentionBar.classList.add("hidden");

    if (primaryBtn) {
      primaryBtn.textContent = "插话转向";
      primaryBtn.className = "primary-send-btn btn-interrupt";
    }
    if (box) box.classList.add("interrupt-mode");
    if (input) input.placeholder = "输入补充要求随时插话转向（支持 @源码文件，Shift+Enter 换行 · Enter 发送）";
    if (chairHint) chairHint.textContent = isExec ? "执行中 · 可中止" : "讨论中 · 可插话";
  } else {
    if (quickCueBar) quickCueBar.classList.remove("hidden");
    if (cueGroupLeft) cueGroupLeft.classList.remove("hidden");
    if (cueDecisionGroup) cueDecisionGroup.classList.remove("hidden");
    if (cueBusyBanner) cueBusyBanner.classList.add("hidden");
    if (stopBtn) stopBtn.classList.add("hidden");

    if (composerToolbar) composerToolbar.classList.remove("hidden");
    if (preModeBar) preModeBar.classList.add("hidden");
    if (activeMentionBar) activeMentionBar.classList.remove("hidden");

    if (primaryBtn) {
      primaryBtn.textContent = "发送追问";
      primaryBtn.className = "primary-send-btn";
    }
    if (box) box.classList.remove("interrupt-mode");
    if (input) input.placeholder = "继续追问、补充约束或敲 @ 引用源码 / 点名回应（Shift+Enter 换行 · Enter 发送）";
    if (chairHint) chairHint.textContent = state.stage === "concluded" ? "已形成决议" : "待追问或决议";
  }

  updateStageStepper(state.stage);
}

function renderSystemStatus(sys) {
  state.systemStatus = sys;
  if (typeof sys.workspace_is_git === "boolean" && !state.sessionWorkspaceDir) {
    state.workspaceIsGit = sys.workspace_is_git;
  }
  updateWorkspaceCardDisplay(state.sessionWorkspaceDir || sys.workspace_dir);

  if (el("quickIdleTimeoutInput") && sys.idle_timeout_sec) {
    el("quickIdleTimeoutInput").value = String(sys.idle_timeout_sec);
  }
  if (el("quickTurnTimeoutInput") && sys.turn_timeout_sec) {
    el("quickTurnTimeoutInput").value = String(sys.turn_timeout_sec);
  }
  syncLineupPresetUI();

  const container = el("cliEngineCards");
  if (!container) return;
  container.innerHTML = "";
  let readyCount = 0;
  let sharedCount = 0;

  AGENT_ORDER.forEach((aid) => {
    const info = sys.agents[aid];
    if (!info) return;
    const detected = Boolean(info.binary_detected);
    const isShared = Boolean(info.shared_fallback);
    if (detected) readyCount += 1;
    if (isShared) sharedCount += 1;

    const cfgPill = el(`cfgStatus${aid.charAt(0).toUpperCase() + aid.slice(1)}`);
    if (cfgPill) {
      cfgPill.textContent = !detected ? "未找到" : isShared ? "同源复用" : "已检测到";
      cfgPill.className = `driver-pill ${detected ? "live" : "missing"}`;
    }

    const shownModel = info.effective_model || info.model || "";
    const supportsEffort = info.supports_effort !== false;
    const effDiscuss = supportsEffort
      ? info.effective_discussion_effort || info.discussion_effort || ""
      : "";
    const effExec = supportsEffort
      ? info.effective_execution_effort || info.execution_effort || effDiscuss
      : "";
    const seatCard = el(`seat-${aid}`);
    if (seatCard) {
      const autoFastNote =
        supportsEffort && ["xhigh", "max"].includes(effDiscuss) && !info.lock_discussion_effort
          ? "（首2轮自动降high提速）"
          : "";
      const effortTip = supportsEffort && effDiscuss ? ` · 档位 ${effDiscuss}${autoFastNote}` : " · 自动省略档位";
      seatCard.title = `${info.name} (${info.persona_label || info.title}) · ${info.cli_name}${shownModel ? ` · ${shownModel}` : ""}${effortTip} — 点击打开席位快捷控制`;
    }

    const ping = state.pingResults[aid];
    const seatSt = state.seatStates[aid];
    const card = document.createElement("div");
    card.className = `cli-card${state.expandedCliCards.has(aid) ? " expanded" : ""}`;

    let statusPillText = !detected ? "未安装" : isShared ? "同源就绪" : "已就绪";
    let statusPillCls = detected ? "live" : "missing";
    let statusPillTitle = "";
    let pingHtml = "";
    if (ping) {
      if (ping.ok) {
        const lat = formatLatencyBadge(ping.elapsed_ms);
        statusPillText = lat.text;
        statusPillCls = lat.tierClass;
        statusPillTitle = `${lat.tierHint}（实测耗时 ${ping.elapsed_ms}ms）`;
        const testedTag = ping.model
          ? `${ping.model}${ping.supports_effort !== false && ping.effort ? `/${ping.effort}` : ""}`
          : "";
        pingHtml = `<div class="cli-test-note">✔ 连通正常${testedTag ? ` [${escapeHtml(testedTag)}]` : ""}：${escapeHtml(ping.reply)}</div>`;
      } else {
        const errKindLabel =
          {
            unsupported_effort_or_model: "档位不兼容",
            quota_rate_limit: "配额限流",
            auth_expired: "鉴权失效",
            timeout: "探活超时",
            missing_binary: "未装 CLI",
          }[ping.error_kind] || "探活异常";
        statusPillText = errKindLabel;
        statusPillCls = "missing";
        const rawErr = String(ping.stderr || "").trim();
        const rawDetails = rawErr
          ? `<details class="cli-ping-raw-details"><summary>展开原始报错摘要</summary><pre class="msg-error-raw">${escapeHtml(rawErr)}</pre></details>`
          : "";
        pingHtml = `<div class="cli-test-note err">✖ ${escapeHtml(ping.error || "连通异常")}${rawDetails}</div>`;
      }
      if (cfgPill) {
        cfgPill.textContent = statusPillText;
        cfgPill.className = `driver-pill ${statusPillCls}`;
      }
    } else if (detected && seatSt && seatSt.elapsed_ms > 0) {
      const lat = formatLatencyBadge(seatSt.elapsed_ms);
      statusPillText = lat.text;
      statusPillCls = lat.tierClass;
      statusPillTitle = `${lat.tierHint}（最近一轮发言耗时 ${(seatSt.elapsed_ms / 1000).toFixed(1)}s）`;
    }

    const effortNote = !supportsEffort
      ? "无 --effort"
      : effExec && effExec !== effDiscuss
      ? `${effDiscuss}/${effExec}`
      : effDiscuss;

    card.innerHTML = `
      <div class="cli-card-top">
        <div class="cli-name-wrap">
          <span class="cli-role-dot dot-${aid}"></span>
          <span class="cli-card-name">${escapeHtml(info.name)} · ${escapeHtml(info.title)}</span>
        </div>
        <span class="driver-pill ${statusPillCls}"${statusPillTitle ? ` title="${escapeHtml(statusPillTitle)}"` : ""}>${escapeHtml(statusPillText)}</span>
      </div>
      <div class="cli-card-cli">${escapeHtml(info.cli_name)}${shownModel ? ` · ${escapeHtml(shownModel)}` : ""}${effortNote ? ` (${escapeHtml(effortNote)})` : ""}</div>
      <div class="cli-card-details">
        <div>${detected ? escapeHtml(info.binary_path) : `需安装: ${(info.binary_candidates || []).join(" / ")}`}</div>
        ${info.version ? `<div>版本: ${escapeHtml(info.version)}</div>` : ""}
      </div>
      ${pingHtml}
    `;

    card.addEventListener("click", (ev) => {
      if (ev.target.closest("details") || ev.target.closest("summary") || ev.target.closest("pre")) {
        ev.stopPropagation();
        return;
      }
      if (!detected) {
        openSettingsModal();
        return;
      }
      if (state.expandedCliCards.has(aid)) {
        state.expandedCliCards.delete(aid);
      } else {
        state.expandedCliCards.add(aid);
      }
      card.classList.toggle("expanded");
    });

    container.appendChild(card);
  });

  const readyBar = el("readySummaryBar");
  if (readyBar) {
    if (readyCount === 3 && sharedCount > 0) {
      readyBar.textContent = `● 3/3 席位就绪（单 CLI 分饰多席 · 自动无状态串行发言防冲突）`;
      readyBar.className = "empty-hero-badge all-ready";
    } else if (readyCount === 3) {
      readyBar.textContent = "● 3/3 本地 CLI 席位已就绪 · 模型合法档位已精准对齐";
      readyBar.className = "empty-hero-badge all-ready";
    } else if (readyCount > 0) {
      readyBar.textContent = `● ${readyCount}/3 席位已就绪（可在设置点「单 CLI 分饰三席」开启三视角圆桌）`;
      readyBar.className = "empty-hero-badge warn-ready";
    } else {
      readyBar.textContent = "⚠ 尚未检测到可用 CLI，请点击左侧齿轮配置可执行路径";
      readyBar.className = "empty-hero-badge warn-ready";
    }
  }
}

function renderSessionList(sessions) {
  state.sessions = sessions || [];
  const cntTag = el("sessionCountTag");
  if (cntTag) cntTag.textContent = String(state.sessions.length);
  const railCnt = el("railSessionCount");
  if (railCnt) {
    railCnt.textContent = String(state.sessions.length);
    railCnt.classList.toggle("hidden", state.sessions.length === 0);
  }

  const box = el("sessionList");
  if (!box) return;
  box.innerHTML = "";
  const kw = state.sessionFilter.trim().toLowerCase();

  const filtered = kw
    ? state.sessions.filter(
        (s) =>
          String(s.title || "").toLowerCase().includes(kw) ||
          String(s.topic || "").toLowerCase().includes(kw)
      )
    : state.sessions;

  filtered.forEach((s) => {
    const item = document.createElement("div");
    item.className = `session-item ${s.session_id === state.currentSessionId ? "active" : ""}`;
    item.innerHTML = `
      <div class="session-item-top">
        ${s.is_busy ? '<span class="session-busy-dot" title="进行中"></span>' : ""}
        <div class="session-item-title">${escapeHtml(s.title || "新会议")}</div>
        <button class="session-del-btn" data-del-sid="${escapeHtml(s.session_id)}" title="删除该会议记录">✕</button>
      </div>
      <div class="session-item-meta">
        <span>${escapeHtml(s.created_at || "")}</span>
        <span>${s.message_count || 0} 条发言</span>
      </div>
    `;

    item.addEventListener("click", (ev) => {
      const delBtn = ev.target.closest("[data-del-sid]");
      if (delBtn) {
        ev.stopPropagation();
        handleDeleteSession(s);
        return;
      }
      if (s.session_id !== state.currentSessionId) {
        connectToSession(s.session_id);
      }
    });
    box.appendChild(item);
  });
}

async function handleDeleteSession(sessMeta) {
  const sid = typeof sessMeta === "string" ? sessMeta : sessMeta.session_id;
  const hasContent =
    typeof sessMeta === "object" && ((sessMeta.message_count || 0) > 0 || Boolean(sessMeta.topic));
  if (hasContent) {
    const ok = window.confirm(`确定要删除会议记录「${sessMeta.title || "新会议"}」吗？删除后不可恢复。`);
    if (!ok) return;
  }
  try {
    const res = await apiFetch(`/api/sessions/${sid}`, { method: "DELETE" });
    renderSessionList(res.sessions);
    if (sid === state.currentSessionId && res.active_session_id) {
      connectToSession(res.active_session_id);
    }
    showToast("已删除会议记录", "info", 1800);
  } catch (err) {
    showToast(`删除失败：${err.message}`, "err");
  }
}

function formatThinkingSec(startTs) {
  const sec = Math.max(0, Math.floor((Date.now() - startTs) / 1000));
  return `${sec}s`;
}

function stopThinkingTickerIfIdle() {
  if (
    state.thinkingStartById.size === 0 &&
    state.seatThinkingStart.size === 0 &&
    !state.execStartTs &&
    thinkingTimerId
  ) {
    clearInterval(thinkingTimerId);
    thinkingTimerId = 0;
  }
}

function tickThinkingTimers() {
  if (
    state.thinkingStartById.size === 0 &&
    state.seatThinkingStart.size === 0 &&
    !state.execStartTs
  ) {
    stopThinkingTickerIfIdle();
    return;
  }

  if (state.execStartTs > 0) {
    const timerBadge = el("execLiveTimer");
    if (timerBadge) {
      timerBadge.textContent = `耗时 ${formatThinkingSec(state.execStartTs)}`;
    }
  }

  state.seatThinkingStart.forEach((info, aid) => {
    const badgeEl = el(`seat-badge-${aid}`);
    if (badgeEl) {
      badgeEl.textContent = `${info.prefix} ${formatThinkingSec(info.startTs)}`;
    }
  });

  state.thinkingStartById.forEach((startTs, msgId) => {
    const card = document.getElementById(`msg-${msgId}`);
    if (!card) {
      state.thinkingStartById.delete(msgId);
      return;
    }
    const secText = formatThinkingSec(startTs);
    const timerNode = card.querySelector(".thinking-timer");
    if (timerNode) timerNode.textContent = secText;
    const timingEl = card.querySelector(".msg-timing");
    if (timingEl) timingEl.textContent = `思考 ${secText}`;
  });

  stopThinkingTickerIfIdle();
}

function ensureThinkingTicker() {
  if (!thinkingTimerId) {
    thinkingTimerId = setInterval(tickThinkingTimers, 1000);
  }
}

function updateSeatUI(seat) {
  const aid = seat.agent_id;
  state.seatStates[aid] = seat;
  if (seat.persona) {
    state.seatPersonas[aid] = seat.persona;
  }
  const card = el(`seat-${aid}`);
  if (!card) return;
  const enabled = seat.enabled !== false && state.enabledAgents.includes(aid);
  const isSolo = state.enabledAgents.length === 1 && state.enabledAgents[0] === aid;
  card.className = `seat-card seat-${aid} status-${seat.status || "idle"}${enabled ? "" : " seat-disabled"}${isSolo ? " seat-is-solo" : ""}`;

  if (seat.title && el(`seat-role-text-${aid}`)) {
    el(`seat-role-text-${aid}`).textContent = isSolo ? `${seat.title} · 独奏` : seat.title;
  }

  if (seat.status === "speaking" || seat.status === "executing") {
    shiftAmbientGlowForSpeaker(aid);
  }

  const badgeEl = el(`seat-badge-${aid}`);
  if (enabled && (seat.status === "thinking" || seat.status === "executing")) {
    const cleanPrefix = String(seat.badge || "思考中").replace(/[….\s]+$/, "") || "思考中";
    if (!state.seatThinkingStart.has(aid)) {
      state.seatThinkingStart.set(aid, { startTs: Date.now(), prefix: cleanPrefix });
      ensureThinkingTicker();
    } else {
      state.seatThinkingStart.get(aid).prefix = cleanPrefix;
    }
    if (badgeEl) {
      badgeEl.textContent = `${cleanPrefix} ${formatThinkingSec(state.seatThinkingStart.get(aid).startTs)}`;
    }
  } else {
    if (state.seatThinkingStart.delete(aid)) {
      stopThinkingTickerIfIdle();
    }
    if (badgeEl) {
      badgeEl.textContent = !enabled
        ? "已暂停"
        : seat.status === "queued"
        ? seat.badge || "排队等待发言…"
        : seat.badge || "待命";
    }
  }

  if (seat.ttft_ms > 0 || seat.elapsed_ms > 0) {
    if (seat.ttft_ms > 0) {
      card.title = `${AGENT_NAMES[aid]} (${seat.persona_label || seat.title || ""}) · 首字 ${seat.ttft_ms}ms / 总计 ${(seat.elapsed_ms / 1000).toFixed(1)}s（点击打开席位控制）`;
    }
    if (seat.elapsed_ms > 0 && state.systemStatus && !state.pingResults[aid]) {
      renderSystemStatus(state.systemStatus);
    }
  }
}

function avatarCharForSpeaker(speaker) {
  return { carbon: "C", grok: "G", astra: "A", chair: "主", system: "纪" }[speaker] || "•";
}

function isStreamNearBottom() {
  const box = el("chatStream");
  if (!box) return true;
  return box.scrollHeight - box.scrollTop - box.clientHeight < 90;
}

function scrollToBottom(force = false) {
  const box = el("chatStream");
  const btn = el("scrollBottomBtn");
  if (!box) return;
  if (force || state.stickToBottom) {
    box.scrollTop = box.scrollHeight;
    if (btn) btn.classList.add("hidden");
  } else if (btn) {
    btn.classList.remove("hidden");
  }
}

function extractSmartPinSnippet(msg, cardEl) {
  const sel = window.getSelection ? window.getSelection() : null;
  if (sel && sel.rangeCount > 0 && cardEl) {
    const selectedText = sel.toString().trim();
    if (selectedText.length >= 4 && cardEl.contains(sel.anchorNode)) {
      return selectedText.length > 165 ? `${selectedText.slice(0, 165)}…` : selectedText;
    }
  }

  const raw = stripTrailingStatusTag(msg.content || "").replace(/```[\s\S]*?```/g, "");
  const lines = raw
    .split(/\n+/)
    .map((s) => s.trim())
    .filter((s) => s && !s.startsWith("#"));

  for (const ln of lines) {
    const bulletMatch = ln.match(/^(?:[-*•]|\d+[.)、]|[①②③④⑤])\s*(.+)$/);
    if (bulletMatch) {
      const cleanItem = bulletMatch[1].replace(/[*`]/g, "").trim();
      if (cleanItem.length >= 6 && !isClientWhiteboardNoise(cleanItem)) {
        return cleanItem.length > 165 ? `${cleanItem.slice(0, 165)}…` : cleanItem;
      }
    }
  }

  const sentences = raw
    .replace(/[#>*`]/g, "")
    .split(/[。！？!\n；;]+/)
    .map((s) => s.replace(/^[-•\d.)、\s]+/, "").trim())
    .filter((s) => s.length >= 8 && !isClientWhiteboardNoise(s));

  const best = sentences[0] || lines.find((x) => !isClientWhiteboardNoise(x)) || "";
  if (!best) return "";
  return best.length > 165 ? `${best.slice(0, 165)}…` : best;
}

function computeStepDownEffort(msg) {
  const aid = msg.speaker;
  if (!AGENT_NAMES[aid]) return null;
  const sysInfo = state.systemStatus?.agents?.[aid] || {};
  const errDetail = String(msg.error_detail || "");
  const parsedFromDetail = (errDetail.match(/effort=([a-z]+)/i)?.[1] || "").toLowerCase();
  const curEff = String(
    msg.failed_effort ||
      (parsedFromDetail && parsedFromDetail !== "none" ? parsedFromDetail : "") ||
      sysInfo.effective_discussion_effort ||
      sysInfo.discussion_effort ||
      ""
  )
    .trim()
    .toLowerCase();

  const drv = msg.failed_driver || sysInfo.effective_driver || sysInfo.driver || "";
  const mdl = msg.failed_model || sysInfo.effective_model || sysInfo.model || "";
  const spec = resolveFrontendEffortSpec(drv, mdl, aid);
  if (!spec.supportsEffort || !Array.isArray(spec.allowed) || spec.allowed.length === 0) {
    return null;
  }

  let target = "";
  if (curEff === "max" || curEff === "xhigh") {
    target = spec.allowed.includes("high") ? "high" : spec.allowed.includes("medium") ? "medium" : spec.allowed[0];
  } else if (curEff === "high") {
    target = spec.allowed.includes("medium") ? "medium" : spec.allowed.includes("low") ? "low" : "";
  } else if (curEff === "medium") {
    target = spec.allowed.includes("low") ? "low" : "";
  } else if (msg.error_kind === "unsupported_effort_or_model" || msg.error_kind === "timeout") {
    target = spec.allowed.includes("high") ? "high" : spec.allowed[0];
  }

  if (!target || target === curEff) return null;
  return { currentEffort: curEff, nextEffort: target };
}

async function downgradeAndRetrySeat(msg, nextEffort, btnEl) {
  if (!msg || !AGENT_NAMES[msg.speaker] || !state.currentSessionId || !nextEffort) return;
  const origLabel = btnEl ? btnEl.textContent : "";
  if (btnEl) {
    btnEl.disabled = true;
    btnEl.textContent = `正在降为 ${nextEffort} 并重试…`;
  }
  state.stickToBottom = true;
  try {
    const cfgRes = await apiFetch("/api/config", {
      method: "POST",
      body: JSON.stringify({
        active_session_id: state.currentSessionId,
        agents: {
          [msg.speaker]: {
            discussion_effort: nextEffort,
            lock_discussion_effort: false,
          },
        },
      }),
    });
    if (cfgRes.system) {
      renderSystemStatus(cfgRes.system);
    }
    await apiFetch(`/api/sessions/${state.currentSessionId}/retry`, {
      method: "POST",
      body: JSON.stringify({
        agent_id: msg.speaker,
        message_id: msg.id,
      }),
    });
    showToast(`${AGENT_NAMES[msg.speaker]} 已自动降为 ${nextEffort} 档并启动单席重试`, "ok", 2400);
  } catch (err) {
    if (btnEl) {
      btnEl.disabled = false;
      btnEl.textContent = origLabel;
    }
    showToast(`降档重试失败：${err.message}`, "err");
  }
}

function createOrUpdateMessageCard(msg) {
  const empty = el("emptyGuide");
  if (empty) empty.classList.add("hidden");

  const streamBox = el("chatStream");
  if (!streamBox) return;
  let card = document.getElementById(`msg-${msg.id}`);
  if (!card) {
    card = document.createElement("article");
    card.id = `msg-${msg.id}`;
    card.dataset.msgId = msg.id;
    streamBox.appendChild(card);
    card.innerHTML = `
      <div class="msg-header">
        <div class="msg-author-group">
          <span class="msg-avatar-mini"></span>
          <span class="msg-speaker"></span>
          <span class="msg-role"></span>
          <span class="msg-phase"></span>
          <span class="msg-target-chip hidden"></span>
        </div>
        <div class="msg-meta-right">
          <div class="msg-hover-actions">
            <button type="button" class="msg-act-btn" data-msg-act="copy" title="复制整条发言">复制</button>
            <button type="button" class="msg-act-btn" data-msg-act="pin" title="提取核心要点（或选中任意文字）加入右侧白板">收入白板</button>
            <button type="button" class="msg-act-btn" data-msg-act="reply" title="针对此发言点名追问">追问</button>
          </div>
          <button type="button" class="msg-act-btn msg-fold-toggle hidden" data-msg-act="toggle-fold">收起</button>
          <span class="msg-badge-chip hidden"></span>
          <span class="msg-timing"></span>
        </div>
      </div>
      <div class="msg-body"></div>
    `;
  }

  const isChair = msg.speaker === "chair";
  const rawTrimmed = (msg.content || "").trim();
  const cleanContent = stripTrailingStatusTag(msg.content || "");
  const isWaitingFirstToken = Boolean(msg.streaming && !rawTrimmed);
  const preserveFlash = card.classList.contains("msg-source-flash");

  card.className = `msg-card speaker-${msg.speaker}${msg.error ? " msg-error" : ""}${preserveFlash ? " msg-source-flash" : ""}`;
  card.querySelector(".msg-avatar-mini").textContent = avatarCharForSpeaker(msg.speaker);
  card.querySelector(".msg-speaker").textContent = msg.speaker_name || msg.speaker;

  const rawRole = (msg.role_title || "").trim();
  const shownRole = isChair ? rawRole.replace(/^主持人/, "").trim() : rawRole;
  const roleEl = card.querySelector(".msg-role");
  roleEl.textContent = shownRole;
  roleEl.classList.toggle("hidden", !shownRole || shownRole === (msg.speaker_name || ""));

  const phaseLabel = (msg.phase_label || "").trim();
  const semanticOverlap = Boolean(
    shownRole &&
      phaseLabel &&
      (shownRole === phaseLabel || shownRole.includes(phaseLabel) || phaseLabel.includes(shownRole))
  );
  const phaseEl = card.querySelector(".msg-phase");
  const hidePhase = Boolean(isChair || !phaseLabel || semanticOverlap);
  phaseEl.textContent = phaseLabel;
  phaseEl.classList.toggle("hidden", hidePhase);

  const targetChip = card.querySelector(".msg-target-chip");
  if (msg.target && AGENT_NAMES[msg.target]) {
    targetChip.textContent = `→ 点名 @${AGENT_NAMES[msg.target]}`;
    targetChip.classList.remove("hidden");
  } else {
    targetChip.classList.add("hidden");
  }

  const replyBtn = card.querySelector('[data-msg-act="reply"]');
  if (replyBtn) {
    replyBtn.classList.toggle("hidden", !AGENT_NAMES[msg.speaker]);
  }

  const badgeChip = card.querySelector(".msg-badge-chip");
  const hideBadge = Boolean(
    isChair ||
      isWaitingFirstToken ||
      !msg.badge ||
      msg.badge === phaseLabel ||
      msg.badge === shownRole
  );
  if (!hideBadge) {
    badgeChip.textContent = msg.badge;
    badgeChip.classList.remove("hidden");
  } else {
    badgeChip.classList.add("hidden");
  }

  const timingEl = card.querySelector(".msg-timing");
  const bodyEl = card.querySelector(".msg-body");

  if (isWaitingFirstToken) {
    if (!msg.clientStartTs) {
      msg.clientStartTs = state.seatThinkingStart.get(msg.speaker)?.startTs || Date.now();
    }
    if (!state.thinkingStartById.has(msg.id)) {
      state.thinkingStartById.set(msg.id, msg.clientStartTs);
      ensureThinkingTicker();
    }
    const elapsedText = formatThinkingSec(state.thinkingStartById.get(msg.id));
    timingEl.textContent = `思考 ${elapsedText}`;
    bodyEl.classList.remove("streaming");
    bodyEl.classList.add("thinking-only");
    const liveAct = String(msg.activity || "").trim();
    const waitHint = liveAct
      ? `🔍 ${escapeHtml(liveAct)}`
      : msg.phase_label === "最终决议"
      ? "正在通盘梳理全量记录并撰写完整决议书…"
      : msg.phase_label === "执行交付"
      ? "正在读取工作区并实时执行决议任务…"
      : "正在深度思考并组织观点…";
    bodyEl.innerHTML =
      `<div class="thinking-placeholder${liveAct ? " has-live-act" : ""}">` +
      `<span class="thinking-spinner" aria-hidden="true"></span>` +
      `<span class="thinking-status-wrap"><span class="thinking-activity-text">${waitHint}</span> <span class="thinking-timer">${elapsedText}</span></span>` +
      `</div>`;
  } else {
    if (state.thinkingStartById.delete(msg.id)) {
      stopThinkingTickerIfIdle();
    }
    bodyEl.classList.remove("thinking-only");
    bodyEl.classList.toggle("streaming", Boolean(msg.streaming));
    let bodyHtml = renderMarkdownSafe(msg.content || "");
    if (msg.error && !msg.streaming) {
      const canRetrySeat = Boolean(AGENT_NAMES[msg.speaker]);
      const rawErrDetail = String(msg.error_detail || "").trim();
      const downgradeInfo = canRetrySeat ? computeStepDownEffort(msg) : null;
      const downgradeBtnHtml = downgradeInfo
        ? `<button type="button" class="msg-downgrade-retry-btn" data-msg-act="downgrade-retry" data-next-effort="${escapeHtml(downgradeInfo.nextEffort)}" title="将 ${escapeHtml(AGENT_NAMES[msg.speaker])} 讨论档位从 ${escapeHtml(downgradeInfo.currentEffort || "高档")} 调降至 ${escapeHtml(downgradeInfo.nextEffort)} 并立即补发">⚡ 降为 ${escapeHtml(downgradeInfo.nextEffort)} 并单席重试</button>`
        : "";
      const actionBtns = canRetrySeat
        ? `<div class="msg-error-actions">` +
          downgradeBtnHtml +
          `<button type="button" class="msg-retry-seat-btn" data-msg-act="retry-seat" title="保持当前档位单独重新调用 ${escapeHtml(AGENT_NAMES[msg.speaker])} 补发本轮发言">↻ 原档重试</button>` +
          `<button type="button" class="msg-open-cfg-btn" data-msg-act="open-settings">检查配置</button>` +
          `</div>`
        : "";
      const detailBlock = rawErrDetail
        ? `<details class="msg-error-details"><summary>展开原始报错摘要</summary><pre class="msg-error-raw">${escapeHtml(rawErrDetail)}</pre></details>`
        : "";
      if (actionBtns || detailBlock) {
        bodyHtml += `<div class="msg-error-panel">${actionBtns}${detailBlock}</div>`;
      }
    }
    bodyEl.innerHTML = bodyHtml;

    if (msg.streaming) {
      timingEl.textContent = msg.ttft_ms > 0 ? `首字 ${(msg.ttft_ms / 1000).toFixed(1)}s · 输出中` : "输出中…";
    } else if (msg.ttft_ms > 0) {
      const totalSec = msg.elapsed_ms > 0 ? ` / ${(msg.elapsed_ms / 1000).toFixed(1)}s` : "";
      timingEl.textContent = `首字 ${(msg.ttft_ms / 1000).toFixed(1)}s${totalSec}`;
    } else {
      timingEl.textContent = msg.timestamp || "";
    }
  }

  const foldBtn = card.querySelector(".msg-fold-toggle");
  const isCompletedLong =
    !msg.streaming &&
    !msg.error &&
    !isWaitingFirstToken &&
    msg.phase_label !== "最终决议" &&
    cleanContent.trim().length > 380;
  if (!isCompletedLong) {
    card.classList.remove("is-collapsed");
    if (foldBtn) foldBtn.classList.add("hidden");
  } else {
    const collapsed = Boolean(state.msgCollapseState.get(msg.id));
    card.classList.toggle("is-collapsed", collapsed);
    if (foldBtn) {
      foldBtn.classList.remove("hidden");
      foldBtn.textContent = collapsed ? "展开" : "收起";
      foldBtn.title = collapsed ? `展开全文（共 ${cleanContent.trim().length} 字）` : "收起为 3 行高";
    }
  }

  scrollToBottom(false);
}

function bindAutoGrowTextarea(ta) {
  const resize = () => {
    ta.style.height = "auto";
    ta.style.height = `${Math.min(ta.scrollHeight, 140)}px`;
  };
  ta.addEventListener("input", resize);
  requestAnimationFrame(resize);
}

function hashShortClient(str) {
  let h = 2166136261;
  const s = String(str || "");
  for (let i = 0; i < s.length; i += 1) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return (h >>> 0).toString(16).padStart(8, "0");
}

function normalizeWhiteboardClient(wb) {
  if (!wb || typeof wb !== "object") {
    return { items: [], chair_constraints: [], wb_version: 1 };
  }
  if (Array.isArray(wb.items)) {
    wb.items = wb.items.filter((it) => {
      if (!it || typeof it !== "object") return false;
      const txt = String(it.text || "").trim();
      if (!txt) return false;
      if (!it.pinned && !it.adopted && isClientWhiteboardNoise(txt)) return false;
      return true;
    });
    return wb;
  }
  const migrated = [];
  const seen = new Set();
  const bucketMap = [
    ["carbon_plan", "carbon"],
    ["grok_risks", "grok"],
    ["astra_actions", "astra"],
  ];
  bucketMap.forEach(([bkey, seat]) => {
    const arr = Array.isArray(wb[bkey]) ? wb[bkey] : [];
    arr.forEach((rawTxt, idx) => {
      const txt = String(rawTxt || "").trim();
      if (!txt || isClientWhiteboardNoise(txt)) return;
      const norm = normalizeCompareText(txt);
      if (!norm || seen.has(norm)) return;
      seen.add(norm);
      migrated.push({
        id: `wb_${seat}_${idx}_${hashShortClient(`${seat}:${idx}:${norm}`)}`,
        text: txt,
        bucket: bkey,
        source_seat: seat,
        source_msg_id: "",
        pinned: false,
        adopted: false,
        version: 1,
      });
    });
  });
  wb.items = migrated;
  return wb;
}

function scrollToSourceMessage(sourceMsgId, sourceSeat, snippetText = "") {
  let targetId = String(sourceMsgId || "").trim();
  if (!targetId || !document.getElementById(`msg-${targetId}`)) {
    const normNeedle = normalizeCompareText(snippetText).slice(0, 12);
    const candidates = Array.from(state.messagesById.values())
      .filter((m) => m && m.speaker === sourceSeat && m.id)
      .reverse();
    const exact = normNeedle
      ? candidates.find((m) => normalizeCompareText(m.content || "").includes(normNeedle))
      : null;
    const picked = exact || candidates[0];
    targetId = picked ? picked.id : "";
  }

  if (!targetId) {
    showToast("未找到对应的左侧发言卡片", "info", 1600);
    return;
  }

  const msgObj = state.messagesById.get(targetId);
  let card = document.getElementById(`msg-${targetId}`);
  if (!card) {
    showToast("对应发言不在当前视图中", "info", 1600);
    return;
  }

  if (card.classList.contains("is-collapsed") && msgObj) {
    state.msgCollapseState.set(targetId, false);
    createOrUpdateMessageCard(msgObj);
    card = document.getElementById(`msg-${targetId}`);
  }

  state.stickToBottom = false;
  document.querySelectorAll(".msg-card.msg-source-flash").forEach((n) => {
    n.classList.remove("msg-source-flash");
  });
  card.scrollIntoView({ behavior: "smooth", block: "center" });
  card.classList.add("msg-source-flash");
  if (sourceHighlightTimer) clearTimeout(sourceHighlightTimer);
  sourceHighlightTimer = setTimeout(() => {
    card?.classList.remove("msg-source-flash");
    sourceHighlightTimer = 0;
  }, 1900);
}

function renderWhiteboardConflictBanner() {
  const banner = el("wbConflictBanner");
  if (!banner) return;
  const c = state.wbConflictState;
  if (!c || !c.message) {
    banner.classList.add("hidden");
    banner.innerHTML = "";
    return;
  }
  const canForceSave = Boolean(c.itemId && c.draftText && c.latestVersion);
  banner.innerHTML = `
    <div class="wb-conflict-text">⚠️ ${escapeHtml(c.message)}</div>
    <div class="wb-conflict-actions">
      ${
        canForceSave
          ? `<button type="button" class="wb-conflict-btn primary" data-wb-conflict-act="force-save">保留草稿覆盖保存</button>`
          : ""
      }
      <button type="button" class="wb-conflict-btn" data-wb-conflict-act="dismiss">知道了</button>
    </div>
  `;
  banner.classList.remove("hidden");
}

async function postWhiteboardMutation(payload) {
  if (!state.currentSessionId) return null;
  const res = await apiFetch(`/api/sessions/${state.currentSessionId}/whiteboard`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  const wb = res.whiteboard || res;
  if (wb && wb.conflict) {
    state.wbConflictState = {
      message: wb.conflict_message || "检测到并发版本变更，已保护当前草稿",
      itemId: payload.item_id || "",
      draftText: payload.text || "",
      latestVersion: wb.conflict_item?.version || null,
    };
    renderWhiteboardConflictBanner();
    showToast(state.wbConflictState.message, "warn", 3200);
    return wb;
  }
  state.wbConflictState = null;
  renderWhiteboardConflictBanner();
  return wb;
}

function triggerWbBadgePulse() {
  const cntBadge = el("wbCountBadge");
  if (!cntBadge) return;
  cntBadge.classList.remove("badge-pulse");
  void cntBadge.offsetWidth;
  cntBadge.classList.add("badge-pulse");
}

function renderWhiteboard(rawWb, forceRender = false, isInitialSnapshot = false) {
  if (!rawWb) return;
  const wb = normalizeWhiteboardClient(rawWb);
  state.whiteboard = wb;
  if (wb.executor_agent && AGENT_NAMES[wb.executor_agent]) {
    state.executorAgent = wb.executor_agent;
    syncPersonasAndExecutorUI();
  }
  const consensusTag = el("wbConsensusTag");
  if (consensusTag) consensusTag.textContent = wb.consensus_status || "待输入议题";

  const conciseTopicTitle = wb.topic
    ? resolveConciseTopicTitle(wb.topic, wb.topic_title || "")
    : "";
  const dedupedChairEntries = dedupeChairConstraintsClient(
    wb.topic || "",
    conciseTopicTitle,
    wb.chair_constraints || []
  );

  const allItems = Array.isArray(wb.items) ? wb.items : [];
  const confirmedItems = allItems.filter((it) => it.pinned || it.adopted);
  const unpinnedItems = allItems.filter((it) => !it.pinned && !it.adopted);

  // 计算新增卡片 ID（仅在会话首包加载完成后对新入板条目播放上浮微动效）
  const newlyAddedIds = new Set();
  if (!state.wbInitialSeeded || isInitialSnapshot) {
    state.knownWbIds.clear();
    allItems.forEach((it) => state.knownWbIds.add(it.id));
    state.wbInitialSeeded = true;
  } else {
    allItems.forEach((it) => {
      if (!state.knownWbIds.has(it.id)) {
        newlyAddedIds.add(it.id);
        state.knownWbIds.add(it.id);
      }
    });
  }

  const totalItems = dedupedChairEntries.length + allItems.length;
  const cntBadge = el("wbCountBadge");
  if (cntBadge) {
    cntBadge.textContent = String(totalItems);
    if (!isInitialSnapshot && totalItems > state.lastWbTotalCount) {
      triggerWbBadgePulse();
    }
  }
  state.lastWbTotalCount = totalItems;

  if (el("wbConfirmedCount")) {
    el("wbConfirmedCount").textContent = String(confirmedItems.length);
  }
  if (el("wbExcerptCount")) {
    el("wbExcerptCount").textContent = `${unpinnedItems.length}/${WB_EXCERPT_SOFT_CAP}`;
  }

  document.querySelectorAll("#wbSeatFilterBar [data-wb-filter]").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.wbFilter === state.wbFilterSeat);
  });

  renderWhiteboardConflictBanner();

  // 若正在编辑某张白板卡片，捕获实时草稿与光标选区，防止 SSE 局部刷新冲掉输入
  const activeDraft = state.wbEditingDraft;
  const activeTa =
    document.activeElement && document.activeElement.classList.contains("wb-edit-input")
      ? document.activeElement
      : null;
  if (activeDraft && activeTa) {
    activeDraft.draftText = activeTa.value;
    activeDraft.selStart = activeTa.selectionStart;
    activeDraft.selEnd = activeTa.selectionEnd;
  }

  // 1. 议题区（若正在编辑议题且非强制重绘则保留输入框）
  const isEditingTopic = activeDraft?.kind === "topic" && !forceRender;
  if (!isEditingTopic) {
    const topicEl = el("wbTopicText");
    if (topicEl) {
      topicEl.innerHTML = "";
      topicEl.textContent = wb.topic ? conciseTopicTitle : "未设置议题";
      topicEl.classList.toggle("editable", Boolean(wb.topic));
      topicEl.title = wb.topic ? `${wb.topic}\n（点击编辑完整议题）` : "";
      topicEl.onclick = wb.topic
        ? () => {
            const origTopic = wb.topic;
            state.wbEditingDraft = { kind: "topic", origText: origTopic, draftText: origTopic };
            topicEl.onclick = null;
            topicEl.innerHTML = "";
            const ta = document.createElement("textarea");
            ta.className = "wb-edit-input";
            ta.rows = 1;
            ta.value = origTopic;
            topicEl.appendChild(ta);
            bindAutoGrowTextarea(ta);
            ta.focus();
            ta.setSelectionRange(ta.value.length, ta.value.length);

            let done = false;
            const finish = async (save) => {
              if (done) return;
              done = true;
              state.wbEditingDraft = null;
              const nextTopic = ta.value.trim();
              if (!save || !nextTopic || nextTopic === origTopic) {
                renderWhiteboard(state.whiteboard, true);
                return;
              }
              try {
                await postWhiteboardMutation({ topic: nextTopic });
              } catch (err) {
                showToast(`更新议题失败：${err.message}`, "err");
                renderWhiteboard(state.whiteboard, true);
              }
            };

            ta.addEventListener("keydown", (ev) => {
              if (ev.isComposing || ev.keyCode === 229) return;
              if (ev.key === "Escape") {
                ev.preventDefault();
                finish(false);
              } else if (ev.key === "Enter" && !ev.shiftKey) {
                ev.preventDefault();
                finish(true);
              }
            });
            ta.addEventListener("blur", () => finish(true));
          }
        : null;
    }
  }

  // 2. 主持约束列表（带 expected_text 防并发错位）
  const isEditingConstraint = activeDraft?.kind === "constraint" && !forceRender;
  if (!isEditingConstraint) {
    const chairUl = el("wbChairList");
    if (chairUl) {
      chairUl.innerHTML = "";
      if (dedupedChairEntries.length === 0) {
        chairUl.classList.add("empty-hint");
        chairUl.innerHTML = `<li>暂无独立补充约束</li>`;
      } else {
        chairUl.classList.remove("empty-hint");
        dedupedChairEntries.forEach((entry) => {
          const itemText = entry.text;
          const realIdx = entry.origIndex;
          const li = document.createElement("li");
          li.className = "wb-item-row";
          li.innerHTML = `
            <span class="wb-item-bullet">•</span>
            <span class="wb-item-text" title="点击直接编辑此条约束">${escapeHtml(itemText)}</span>
            <button type="button" class="wb-item-del" title="移除此条">✕</button>
          `;
          li.querySelector(".wb-item-text").addEventListener("click", () => {
            state.wbEditingDraft = {
              kind: "constraint",
              index: realIdx,
              origText: itemText,
              draftText: itemText,
            };
            li.classList.add("editing");
            li.innerHTML = `<span class="wb-item-bullet">•</span><textarea class="wb-edit-input" rows="1"></textarea>`;
            const ta = li.querySelector(".wb-edit-input");
            ta.value = itemText;
            bindAutoGrowTextarea(ta);
            ta.focus();
            ta.setSelectionRange(ta.value.length, ta.value.length);

            let done = false;
            const finish = async (save) => {
              if (done) return;
              done = true;
              state.wbEditingDraft = null;
              const nextVal = ta.value.trim();
              if (!save || nextVal === itemText) {
                renderWhiteboard(state.whiteboard, true);
                return;
              }
              try {
                await postWhiteboardMutation({
                  op: "update",
                  bucket: "chair_constraints",
                  index: realIdx,
                  expected_text: itemText,
                  text: nextVal,
                });
              } catch (err) {
                showToast(`编辑失败：${err.message}`, "err");
                renderWhiteboard(state.whiteboard, true);
              }
            };

            ta.addEventListener("keydown", (ev) => {
              if (ev.isComposing || ev.keyCode === 229) return;
              if (ev.key === "Escape") {
                ev.preventDefault();
                finish(false);
              } else if (ev.key === "Enter" && !ev.shiftKey) {
                ev.preventDefault();
                finish(true);
              }
            });
            ta.addEventListener("blur", () => finish(true));
          });

          li.querySelector(".wb-item-del").addEventListener("click", async (ev) => {
            ev.stopPropagation();
            try {
              await postWhiteboardMutation({
                op: "remove",
                bucket: "chair_constraints",
                index: realIdx,
                expected_text: itemText,
              });
            } catch (err) {
              showToast(`移除失败：${err.message}`, "err");
            }
          });
          chairUl.appendChild(li);
        });
      }
    }
  }

  // 3. 结构化白板卡片渲染器（支持置顶 📌、勾选采纳 ☑、来源徽章回跳、版本号校验与编辑态草稿保护）
  const openInlineItemEditor = (liNode, itemObj, initialDraft = null) => {
    const startText = initialDraft ? initialDraft.draftText : itemObj.text;
    const expVer = initialDraft ? initialDraft.expectedVersion : itemObj.version || 1;
    const origText = initialDraft ? initialDraft.origText : itemObj.text;

    state.wbEditingDraft = {
      kind: "item",
      itemId: itemObj.id,
      expectedVersion: expVer,
      origText,
      draftText: startText,
      selStart: initialDraft?.selStart ?? startText.length,
      selEnd: initialDraft?.selEnd ?? startText.length,
    };

    if (itemObj.version && itemObj.version !== expVer && itemObj.text !== origText) {
      state.wbConflictState = {
        message: "该卡片后台已有新版本，您的编辑草稿已完整保护",
        itemId: itemObj.id,
        draftText: startText,
        latestVersion: itemObj.version,
      };
      renderWhiteboardConflictBanner();
    }

    liNode.className = "wb-pool-item editing";
    liNode.innerHTML = `
      <div class="wb-edit-box">
        <textarea class="wb-edit-input" data-edit-item-id="${escapeHtml(itemObj.id)}" rows="2"></textarea>
        <div class="wb-edit-toolbar">
          <span class="wb-edit-ver">v${escapeHtml(String(expVer))} · Enter 保存 / Esc 取消</span>
          <div class="wb-edit-btns">
            <button type="button" class="wb-edit-cancel-btn">取消</button>
            <button type="button" class="wb-edit-save-btn">保存</button>
          </div>
        </div>
      </div>
    `;
    const ta = liNode.querySelector(".wb-edit-input");
    ta.value = startText;
    bindAutoGrowTextarea(ta);
    ta.addEventListener("input", () => {
      if (state.wbEditingDraft?.itemId === itemObj.id) {
        state.wbEditingDraft.draftText = ta.value;
        state.wbEditingDraft.selStart = ta.selectionStart;
        state.wbEditingDraft.selEnd = ta.selectionEnd;
      }
    });

    let finished = false;
    const commitEdit = async (shouldSave) => {
      if (finished) return;
      finished = true;
      const nextVal = ta.value.trim();
      if (!shouldSave || nextVal === origText) {
        state.wbEditingDraft = null;
        renderWhiteboard(state.whiteboard, true);
        return;
      }
      try {
        const resWb = await postWhiteboardMutation({
          op: "update",
          item_id: itemObj.id,
          expected_version: expVer,
          text: nextVal,
        });
        if (resWb && resWb.conflict) {
          // 发生版本冲突：保持草稿不丢失，更新冲突横幅供用户确认覆盖
          finished = false;
          if (state.wbConflictState) {
            state.wbConflictState.draftText = nextVal;
          }
          renderWhiteboardConflictBanner();
          return;
        }
        state.wbEditingDraft = null;
      } catch (err) {
        finished = false;
        showToast(`保存失败：${err.message}`, "err");
      }
    };

    liNode.querySelector(".wb-edit-cancel-btn").addEventListener("mousedown", (ev) => {
      ev.preventDefault();
      commitEdit(false);
    });
    liNode.querySelector(".wb-edit-save-btn").addEventListener("mousedown", (ev) => {
      ev.preventDefault();
      commitEdit(true);
    });
    ta.addEventListener("keydown", (ev) => {
      if (ev.isComposing || ev.keyCode === 229) return;
      if (ev.key === "Escape") {
        ev.preventDefault();
        commitEdit(false);
      } else if (ev.key === "Enter" && !ev.shiftKey) {
        ev.preventDefault();
        commitEdit(true);
      }
    });

    requestAnimationFrame(() => {
      ta.focus();
      const s0 = Math.min(ta.value.length, state.wbEditingDraft?.selStart ?? ta.value.length);
      const s1 = Math.min(ta.value.length, state.wbEditingDraft?.selEnd ?? ta.value.length);
      ta.setSelectionRange(s0, s1);
    });
  };

  const renderCardPoolList = (ulId, itemsArr, emptyTipText) => {
    const ul = el(ulId);
    if (!ul) return;
    ul.innerHTML = "";
    if (!itemsArr || itemsArr.length === 0) {
      ul.classList.add("empty-hint");
      ul.innerHTML = `<li class="wb-empty-tip">${escapeHtml(emptyTipText)}</li>`;
      return;
    }
    ul.classList.remove("empty-hint");

    itemsArr.forEach((it) => {
      const li = document.createElement("li");
      if (!forceRender && activeDraft?.kind === "item" && activeDraft.itemId === it.id) {
        ul.appendChild(li);
        openInlineItemEditor(li, it, activeDraft);
        return;
      }

      const seatKey = AGENT_NAMES[it.source_seat] ? it.source_seat : "chair";
      const seatLabel = AGENT_NAMES[seatKey] || "主持";
      const seatInitial = avatarCharForSpeaker(seatKey);
      const isConfirmed = Boolean(it.pinned || it.adopted);
      const enterCls = newlyAddedIds.has(it.id) ? " wb-card-enter" : "";

      li.className = `wb-pool-item${isConfirmed ? " is-confirmed" : ""}${it.pinned ? " is-pinned" : ""}${enterCls}`;
      li.dataset.wbId = it.id;

      li.innerHTML = `
        <div class="wb-pool-main">
          <button type="button" class="wb-adopt-check ${it.adopted ? "checked" : ""}" title="${it.adopted ? "取消采纳标记" : "勾选采纳为共识决策（优先注入后续 Prompt）"}" aria-label="采纳开关">
            ${it.adopted ? "✓" : ""}
          </button>
          <div class="wb-pool-text" title="点击行内编辑此卡片（带版本号防冲突保护）">${escapeHtml(it.text)}</div>
        </div>
        <div class="wb-pool-meta">
          <button type="button" class="wb-seat-mini-badge badge-seat-${escapeHtml(seatKey)}" title="点击定位并高亮左侧 ${escapeHtml(seatLabel)} 对应原发言">
            <span class="mini-seat-dot">${escapeHtml(seatInitial)}</span>
            <span>${escapeHtml(seatLabel)}</span>
          </button>
          <div class="wb-pool-actions">
            <button type="button" class="wb-card-act pin-btn ${it.pinned ? "active" : ""}" title="${it.pinned ? "取消置顶" : "一键置顶至已确认共识（永不自动淘汰）"}">📌</button>
            <button type="button" class="wb-card-act edit-btn" title="编辑内容">✎</button>
            <button type="button" class="wb-card-act del-btn" title="删除此条">✕</button>
          </div>
        </div>
      `;

      li.querySelector(".wb-adopt-check").addEventListener("click", async (ev) => {
        ev.stopPropagation();
        try {
          await postWhiteboardMutation({ op: "toggle_adopt", item_id: it.id });
        } catch (err) {
          showToast(err.message, "err");
        }
      });

      li.querySelector(".wb-card-act.pin-btn").addEventListener("click", async (ev) => {
        ev.stopPropagation();
        try {
          await postWhiteboardMutation({ op: "toggle_pin", item_id: it.id });
        } catch (err) {
          showToast(err.message, "err");
        }
      });

      li.querySelector(".wb-seat-mini-badge").addEventListener("click", (ev) => {
        ev.stopPropagation();
        scrollToSourceMessage(it.source_msg_id, seatKey, it.text);
      });

      li.querySelector(".wb-pool-text").addEventListener("click", () => {
        openInlineItemEditor(li, it);
      });
      li.querySelector(".wb-card-act.edit-btn").addEventListener("click", (ev) => {
        ev.stopPropagation();
        openInlineItemEditor(li, it);
      });

      li.querySelector(".wb-card-act.del-btn").addEventListener("click", async (ev) => {
        ev.stopPropagation();
        try {
          await postWhiteboardMutation({
            op: "remove",
            item_id: it.id,
            expected_version: it.version || 1,
          });
        } catch (err) {
          showToast(`移除失败：${err.message}`, "err");
        }
      });

      ul.appendChild(li);
    });
  };

  renderCardPoolList(
    "wbConsensusList",
    confirmedItems,
    "点击下方摘录的 📌 置顶或勾选左侧采纳框，即可沉淀为已确认共识"
  );

  const filteredExcerpts =
    state.wbFilterSeat === "all"
      ? unpinnedItems
      : unpinnedItems.filter((it) => it.source_seat === state.wbFilterSeat);

  // 若正在编辑的条目位于较早折叠区间，临时保持展开以防编辑框隐藏
  const editingInHiddenSlice =
    activeDraft?.kind === "item" &&
    filteredExcerpts.length > WB_EXCERPT_COMPACT_LIMIT &&
    filteredExcerpts
      .slice(0, filteredExcerpts.length - WB_EXCERPT_COMPACT_LIMIT)
      .some((it) => it.id === activeDraft.itemId);

  const showAllExcerpts = state.wbExcerptsExpanded || editingInHiddenSlice;
  const visibleExcerpts =
    !showAllExcerpts && filteredExcerpts.length > WB_EXCERPT_COMPACT_LIMIT
      ? filteredExcerpts.slice(-WB_EXCERPT_COMPACT_LIMIT)
      : filteredExcerpts;

  renderCardPoolList(
    "wbExcerptList",
    visibleExcerpts,
    state.wbFilterSeat === "all"
      ? "讨论开始后将自动过滤工具独白噪音并提炼高信噪比摘录卡片"
      : `当前暂无来自 ${AGENT_NAMES[state.wbFilterSeat] || state.wbFilterSeat} 的未置顶摘录`
  );

  const expandBtn = el("wbToggleExpandBtn");
  if (expandBtn) {
    if (filteredExcerpts.length > WB_EXCERPT_COMPACT_LIMIT) {
      expandBtn.classList.remove("hidden");
      const hiddenCount = filteredExcerpts.length - WB_EXCERPT_COMPACT_LIMIT;
      expandBtn.textContent = showAllExcerpts
        ? `收起为紧凑视图（默认展示最新 ${WB_EXCERPT_COMPACT_LIMIT} 条）`
        : `展开查看全部 ${filteredExcerpts.length} 条摘录（已紧凑折叠较早 ${hiddenCount} 条）`;
    } else {
      expandBtn.classList.add("hidden");
    }
  }

  const termLogs = el("astraTermLogs");
  if (termLogs && wb.exec_logs && wb.exec_logs.length > 0 && !state.execStreamingBuffer) {
    termLogs.textContent = wb.exec_logs.join("\n");
  }
  if (wb.exec_diff !== undefined) {
    renderDiff(wb.exec_diff);
  }
  const rbBtn = el("rollbackExecBtn");
  if (rbBtn) {
    rbBtn.classList.toggle("hidden", !wb.can_rollback);
  }
}

function renderDiff(diffText) {
  state.rawDiffText = diffText || "";
  const box = el("astraDiffView");
  const statEl = el("diffStatBadge");
  if (!box) return;
  if (!diffText) {
    box.textContent = "暂无变更输出";
    if (statEl) statEl.textContent = "";
    return;
  }
  let added = 0;
  let removed = 0;
  box.innerHTML = diffText
    .split("\n")
    .map((ln) => {
      const safe = escapeHtml(ln);
      if (ln.startsWith("+") && !ln.startsWith("+++")) {
        added += 1;
        return `<span class="diff-add">${safe}</span>`;
      }
      if (ln.startsWith("-") && !ln.startsWith("---")) {
        removed += 1;
        return `<span class="diff-del">${safe}</span>`;
      }
      if (ln.startsWith("@@")) return `<span class="diff-hunk">${safe}</span>`;
      return `${safe}\n`;
    })
    .join("");
  if (statEl) statEl.textContent = added || removed ? `+${added} / -${removed}` : "";
}

function refreshTerminalDisplay() {
  const pre = el("astraTermLogs");
  if (!pre) return;
  const logs = state.whiteboard?.exec_logs || [];
  const logHeader = logs.join("\n");
  if (state.execStreamingBuffer) {
    pre.textContent = logHeader
      ? `${logHeader}\n\n── 实时输出流 ──\n${state.execStreamingBuffer}`
      : state.execStreamingBuffer;
  } else if (logHeader) {
    pre.textContent = logHeader;
  }
  pre.scrollTop = pre.scrollHeight;
}

function connectToSession(sessionId) {
  if (state.eventSource) {
    state.eventSource.close();
    state.eventSource = null;
  }
  closeAtSuggestMenu();
  closePersonaPopover();
  state.currentSessionId = sessionId;
  state.messagesById.clear();
  state.msgCollapseState.clear();
  state.thinkingStartById.clear();
  state.seatThinkingStart.clear();
  state.wbEditingDraft = null;
  state.wbConflictState = null;
  state.knownWbIds.clear();
  state.wbInitialSeeded = false;
  state.lastWbTotalCount = 0;
  state.execStartTs = 0;
  state.execStreamingBuffer = "";
  stopThinkingTickerIfIdle();
  state.stickToBottom = true;

  const streamBox = el("chatStream");
  if (streamBox) streamBox.querySelectorAll(".msg-card").forEach((n) => n.remove());
  el("emptyGuide")?.classList.remove("hidden");
  el("scrollBottomBtn")?.classList.add("hidden");
  const termLogs = el("astraTermLogs");
  if (termLogs) termLogs.textContent = "尚未触发执行任务";
  renderDiff("");

  const es = new EventSource(`/api/sessions/${sessionId}/stream`);
  state.eventSource = es;

  es.onopen = () => {
    const dot = el("sseConnDot");
    if (!dot) return;
    dot.textContent = "";
    dot.title = "本地实时服务已连接";
    dot.classList.add("online");
  };

  es.onerror = () => {
    const dot = el("sseConnDot");
    if (!dot) return;
    dot.textContent = "重连中…";
    dot.title = "实时连接中断，正在自动重连…";
    dot.classList.remove("online");
  };

  es.addEventListener("snapshot", (e) => {
    const snap = JSON.parse(e.data);
    state.currentTopic = snap.topic || "";
    state.sessionWorkspaceDir = snap.workspace_dir || "";
    state.workspaceIsGit = Boolean(snap.workspace_is_git);
    state.stage = snap.stage || "idle";
    state.isBusy = Boolean(snap.is_busy);
    state.enabledAgents = snap.enabled_agents || ["carbon", "grok", "astra"];
    if (snap.seat_personas && typeof snap.seat_personas === "object") {
      state.seatPersonas = { ...state.seatPersonas, ...snap.seat_personas };
    }
    if (snap.executor_agent) {
      state.executorAgent = snap.executor_agent;
    }

    updateWorkspaceCardDisplay(state.sessionWorkspaceDir, state.workspaceIsGit);
    const topicTitle = el("currentTopicTitle");
    if (topicTitle) {
      topicTitle.textContent = snap.topic
        ? resolveConciseTopicTitle(snap.topic, snap.title || snap.whiteboard?.topic_title || "")
        : "新圆桌会议";
      topicTitle.title = snap.topic || "";
    }
    syncCollabModeUI(snap.collab_mode || "standard_roundtable");
    syncStageStatusPill((snap.whiteboard && snap.whiteboard.consensus_status) || "");

    Object.values(snap.seat_states || {}).forEach(updateSeatUI);
    syncPersonasAndExecutorUI();

    (snap.messages || []).forEach((m) => {
      if (m.streaming && !m.clientStartTs) {
        m.clientStartTs = Date.now();
      }
      state.messagesById.set(m.id, m);
      createOrUpdateMessageCard(m);
    });
    renderWhiteboard(snap.whiteboard, true, true);
    if (!state.isBusy) {
      resetClientBusyTimersIfIdle();
    }
    syncComposerAndControls();
    scrollToBottom(true);
    refreshSessionsQuietly();
  });

  es.addEventListener("session_cleared", () => {
    state.messagesById.clear();
    state.msgCollapseState.clear();
    state.thinkingStartById.clear();
    state.knownWbIds.clear();
    state.lastWbTotalCount = 0;
    el("chatStream")?.querySelectorAll(".msg-card").forEach((n) => n.remove());
  });

  es.addEventListener("session_meta", (e) => {
    const meta = JSON.parse(e.data);
    if (meta.topic !== undefined || meta.title !== undefined) {
      if (meta.topic !== undefined) {
        state.currentTopic = meta.topic || "";
      }
      const topicTitle = el("currentTopicTitle");
      if (topicTitle) {
        topicTitle.textContent = state.currentTopic
          ? resolveConciseTopicTitle(
              state.currentTopic,
              meta.title || state.whiteboard?.topic_title || ""
            )
          : "新圆桌会议";
        topicTitle.title = state.currentTopic || "";
      }
    }
    if (typeof meta.workspace_is_git === "boolean") {
      state.workspaceIsGit = meta.workspace_is_git;
    }
    if (meta.workspace_dir !== undefined) {
      state.sessionWorkspaceDir = meta.workspace_dir || "";
      updateWorkspaceCardDisplay(state.sessionWorkspaceDir, state.workspaceIsGit);
    }
    if (meta.collab_mode) {
      syncCollabModeUI(meta.collab_mode);
    }
    if (meta.stage) state.stage = meta.stage;
    if (meta.is_busy !== undefined) {
      state.isBusy = Boolean(meta.is_busy);
      if (!state.isBusy) {
        resetClientBusyTimersIfIdle();
      }
    }
    if (Array.isArray(meta.enabled_agents)) {
      state.enabledAgents = meta.enabled_agents;
    }
    if (meta.seat_personas && typeof meta.seat_personas === "object") {
      state.seatPersonas = { ...state.seatPersonas, ...meta.seat_personas };
    }
    if (meta.executor_agent) {
      state.executorAgent = meta.executor_agent;
    }
    syncPersonasAndExecutorUI();

    if (meta.consensus_status !== undefined) {
      if (state.whiteboard) state.whiteboard.consensus_status = meta.consensus_status;
      const wbTag = el("wbConsensusTag");
      if (wbTag) wbTag.textContent = meta.consensus_status || "待输入议题";
      syncStageStatusPill(meta.consensus_status);
    }
    syncComposerAndControls();
    refreshSessionsQuietly();
  });

  es.addEventListener("seat_update", (e) => {
    updateSeatUI(JSON.parse(e.data));
    syncPersonasAndExecutorUI();
  });

  es.addEventListener("msg_start", (e) => {
    const msg = JSON.parse(e.data);
    msg.clientStartTs = Date.now();
    state.messagesById.set(msg.id, msg);
    createOrUpdateMessageCard(msg);
  });

  es.addEventListener("msg_activity", (e) => {
    const { id, activity } = JSON.parse(e.data);
    const msg = state.messagesById.get(id);
    if (!msg || !msg.streaming || (msg.content || "").trim()) return;
    msg.activity = activity || "";
    const card = document.getElementById(`msg-${id}`);
    const actNode = card?.querySelector(".thinking-activity-text");
    const placeholder = card?.querySelector(".thinking-placeholder");
    if (actNode && activity) {
      actNode.textContent = `🔍 ${activity}`;
      placeholder?.classList.add("has-live-act");
    } else {
      createOrUpdateMessageCard(msg);
    }
  });

  es.addEventListener("msg_delta", (e) => {
    const { id, delta } = JSON.parse(e.data);
    const msg = state.messagesById.get(id);
    if (!msg) return;
    msg.activity = "";
    msg.content += delta;
    pendingDeltaIds.add(id);
    if (!deltaRafId) {
      deltaRafId = requestAnimationFrame(() => {
        deltaRafId = 0;
        pendingDeltaIds.forEach((mid) => {
          const cur = state.messagesById.get(mid);
          if (cur) createOrUpdateMessageCard(cur);
        });
        pendingDeltaIds.clear();
      });
    }
  });

  es.addEventListener("msg_done", (e) => {
    const msg = JSON.parse(e.data);
    const prev = state.messagesById.get(msg.id);
    if (prev && prev.clientStartTs) {
      msg.clientStartTs = prev.clientStartTs;
    }
    pendingDeltaIds.delete(msg.id);
    state.messagesById.set(msg.id, msg);
    createOrUpdateMessageCard(msg);
  });

  es.addEventListener("whiteboard_update", (e) => {
    renderWhiteboard(JSON.parse(e.data));
  });

  es.addEventListener("term_log", (e) => {
    const { line } = JSON.parse(e.data);
    if (!state.whiteboard) state.whiteboard = { exec_logs: [] };
    if (!Array.isArray(state.whiteboard.exec_logs)) state.whiteboard.exec_logs = [];
    if (state.whiteboard.exec_logs[state.whiteboard.exec_logs.length - 1] !== line) {
      state.whiteboard.exec_logs.push(line);
    }
    refreshTerminalDisplay();
    el("execDot")?.classList.remove("hidden");
  });

  es.addEventListener("exec_delta", (e) => {
    const { delta } = JSON.parse(e.data);
    if (!delta) return;
    state.execStreamingBuffer += delta;
    if (state.execStreamingBuffer.length > 6000) {
      state.execStreamingBuffer = "…(前文详见左侧主舞台执行报告)…\n" + state.execStreamingBuffer.slice(-5500);
    }
    refreshTerminalDisplay();
    el("execDot")?.classList.remove("hidden");
  });

  es.addEventListener("exec_artifact", (e) => {
    const { diff, executor_name } = JSON.parse(e.data);
    state.execStreamingBuffer = "";
    refreshTerminalDisplay();
    renderDiff(diff);
    if (diff) {
      switchWorkbenchTab("terminal");
    }
    showToast(`${executor_name || AGENT_NAMES[state.executorAgent] || "主刀席位"} 执行交付已完成`, "ok");
  });
}

function refreshSessionsQuietly() {
  if (refreshSessionsTimer) clearTimeout(refreshSessionsTimer);
  refreshSessionsTimer = setTimeout(async () => {
    refreshSessionsTimer = 0;
    try {
      const res = await apiFetch("/api/sessions");
      renderSessionList(res.sessions);
    } catch (_) {}
  }, 160);
}

async function handlePrimaryComposerSubmit() {
  closeAtSuggestMenu();
  const input = el("topicInput");
  if (!input) return;
  const text = (input.value || "").trim();
  if (!text) {
    input.focus();
    return;
  }
  input.value = "";
  autoResizeComposer();
  renderAttachedFileChips();
  state.stickToBottom = true;
  shiftAmbientGlowForSpeaker("chair");

  try {
    if (!state.currentTopic) {
      const collabMode = el("collabModeSelect")?.value || "standard_roundtable";
      await apiFetch(`/api/sessions/${state.currentSessionId}/start`, {
        method: "POST",
        body: JSON.stringify({
          topic: text,
          collab_mode: collabMode,
          enabled_agents: state.enabledAgents,
          seat_personas: state.seatPersonas,
          executor_agent: state.executorAgent,
        }),
      });
    } else {
      await apiFetch(`/api/sessions/${state.currentSessionId}/followup`, {
        method: "POST",
        body: JSON.stringify({ message: text }),
      });
    }
  } catch (err) {
    showToast(`发送失败：${err.message}`, "err");
  }
}

function switchWorkbenchTab(tabName) {
  const shell = el("appShell");
  if (shell && shell.classList.contains("right-collapsed")) {
    toggleRightWorkbench(false);
  }
  document.querySelectorAll(".wb-tab").forEach((b) => {
    b.classList.toggle("active", b.dataset.tab === tabName);
  });
  document.querySelectorAll(".wb-pane").forEach((p) => {
    p.classList.toggle("active", p.id === `pane-${tabName}`);
  });
  if (tabName === "terminal") {
    el("execDot")?.classList.add("hidden");
  }
}

function buildMinutesMarkdown() {
  const wb = normalizeWhiteboardClient(state.whiteboard || {});
  const rawWs = state.sessionWorkspaceDir || state.systemStatus?.workspace_dir || "";
  const shownWs = isUnboundWorkspace(rawWs) ? "未绑定本地项目" : rawWs;
  const allItems = Array.isArray(wb.items) ? wb.items : [];
  const confirmed = allItems.filter((it) => it.pinned || it.adopted);
  const excerpts = allItems.filter((it) => !it.pinned && !it.adopted);
  const formatWbLine = (it) => {
    const seatName = AGENT_NAMES[it.source_seat] || "主持";
    const flag = it.pinned ? "📌 " : it.adopted ? "☑ " : "";
    return `- ${flag}[${seatName}] ${it.text}`;
  };

  const lines = [
    `# AI圆桌会议纪要：${wb.topic || "未命名会议"}`,
    ``,
    `- **共识状态**：${wb.consensus_status || ""}`,
    `- **绑定工作区**：${shownWs}`,
    `- **参会席位**：${state.enabledAgents.map((a) => `${AGENT_NAMES[a]} (${getPersonaSpec(state.seatPersonas[a], a).label})`).join("、")}`,
    `- **导出时间**：${new Date().toLocaleString()}`,
    ``,
    `## 一、议题与主持约束`,
    ...(wb.chair_constraints?.length ? wb.chair_constraints.map((x) => `- ${x}`) : ["- 无补充约束"]),
    ``,
    `## 二、已确认共识`,
    ...(confirmed.length ? confirmed.map(formatWbLine) : ["- 暂无已置顶或勾选采纳的确认共识"]),
    ``,
    `## 三、讨论摘录`,
    ...(excerpts.length ? excerpts.map(formatWbLine) : ["- 无"]),
    ``,
    `## 四、会议完整发言记录`,
    ...Array.from(state.messagesById.values()).map(
      (m) => `### [${m.timestamp}] ${m.speaker_name}（${m.phase_label}）\n${stripTrailingStatusTag(m.content)}\n`
    ),
  ];
  return lines.join("\n");
}

async function exportMinutesMarkdown() {
  const mdText = buildMinutesMarkdown();
  try {
    const res = await apiFetch(`/api/sessions/${state.currentSessionId}/export`, {
      method: "POST",
      body: JSON.stringify({ markdown: mdText }),
    });
    showToast(`纪要已保存：${res.saved_path}`, "ok", 3500);
  } catch (_) {
    const blob = new Blob([mdText], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `AI圆桌纪要_${Date.now()}.md`;
    a.click();
    URL.revokeObjectURL(url);
    showToast("已触发浏览器下载纪要文件", "ok");
  }
}

function toggleLeftSidebar(forceCollapse) {
  const shell = el("appShell");
  if (!shell) return;
  const collapsed =
    typeof forceCollapse === "boolean"
      ? forceCollapse
      : !shell.classList.contains("left-collapsed");
  shell.classList.toggle("left-collapsed", collapsed);
  const brandBtn = el("brandToggleRailBtn");
  if (brandBtn) {
    brandBtn.title = collapsed
      ? "点击展开左侧完整面板 (⌘B)"
      : "点击收起左侧面板为图标栏 (⌘B)";
  }
}

function toggleRightWorkbench(forceCollapse) {
  const shell = el("appShell");
  if (!shell) return;
  const collapsed =
    typeof forceCollapse === "boolean"
      ? forceCollapse
      : !shell.classList.contains("right-collapsed");
  shell.classList.toggle("right-collapsed", collapsed);
  el("toggleRightBtn")?.classList.toggle("active-pane", !collapsed);
}

function collectModalAgentDrafts() {
  const out = {};
  const defaults = { carbon: "agy", grok: "grok", astra: "codex" };
  const defPersonas = { carbon: "planner", grok: "red_team", astra: "implementer" };
  AGENT_ORDER.forEach((aid) => {
    const cap = aid.charAt(0).toUpperCase() + aid.slice(1);
    const driver = el(`cfg${cap}Driver`)?.value || defaults[aid];
    const model = (el(`cfg${cap}Model`)?.value || "").trim();
    const spec = resolveFrontendEffortSpec(driver, model, aid);
    const rawDiscuss = el(`cfg${cap}Effort`)?.value ?? "";
    const rawExec = el(`cfg${cap}ExecEffort`)?.value ?? "";
    out[aid] = {
      driver,
      persona: el(`cfg${cap}Persona`)?.value || defPersonas[aid],
      custom_binary: (el(`cfg${cap}Bin`)?.value || "").trim(),
      model,
      discussion_effort: spec.supportsEffort ? clampEffortBySpec(rawDiscuss, spec, false) : "",
      execution_effort: spec.supportsEffort ? clampEffortBySpec(rawExec, spec, true) : "",
      lock_discussion_effort: Boolean(el(`cfg${cap}LockEffort`)?.checked),
    };
  });
  return out;
}

async function runConnectivityProbe(useModalDraft = false, triggerBtn = null) {
  const btn = triggerBtn || el("testCliBtn");
  const origLabel = btn ? btn.textContent : "实测连通";
  if (btn) {
    btn.disabled = true;
    btn.textContent = "探活中…";
  }
  try {
    let agentPayload = {};
    if (useModalDraft) {
      agentPayload = collectModalAgentDrafts();
    } else if (state.systemStatus?.agents) {
      AGENT_ORDER.forEach((aid) => {
        const info = state.systemStatus.agents[aid];
        if (!info) return;
        agentPayload[aid] = {
          driver: info.driver || info.effective_driver || "auto",
          custom_binary: info.custom_binary || "",
          model: info.model || "",
          discussion_effort:
            info.supports_effort === false
              ? ""
              : info.effective_discussion_effort || info.discussion_effort || "",
        };
      });
    }
    const res = await apiFetch("/api/cli/test", {
      method: "POST",
      body: JSON.stringify({ agents: agentPayload }),
    });
    state.pingResults = res.results || {};
    renderSystemStatus(res.system);
    const results = Object.values(state.pingResults);
    const okCount = results.filter((x) => x.ok).length;
    const failed = results.filter((x) => !x.ok);
    if (failed.length === 0) {
      showToast(`连通实测完成：${okCount}/3 席位正常响应`, "ok");
    } else {
      const firstReason = failed[0]?.error || "部分席位未通过";
      showToast(`连通实测：${okCount}/3 正常 · ${firstReason}`, okCount > 0 ? "warn" : "err", 4200);
    }
  } catch (err) {
    showToast(`连通性测试失败：${err.message}`, "err");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = origLabel;
    }
  }
}

function openSettingsModal() {
  if (state.systemStatus) {
    const rawWs = state.sessionWorkspaceDir || state.systemStatus.workspace_dir || "";
    const wsInput = el("cfgWorkspaceDir");
    if (wsInput) wsInput.value = isUnboundWorkspace(rawWs) ? "" : rawWs;
    if (el("cfgIdleTimeout")) {
      el("cfgIdleTimeout").value = String(state.systemStatus.idle_timeout_sec || 90);
    }
    if (el("cfgTurnTimeout")) {
      el("cfgTurnTimeout").value = String(state.systemStatus.turn_timeout_sec || 300);
    }
    const singleFallback = el("cfgSingleCliFallback");
    if (singleFallback) {
      singleFallback.checked = state.systemStatus.allow_single_cli_fallback !== false;
    }
    const triadSel = el("singleCliTriadDriver");
    if (triadSel) {
      const readyDrv = detectFirstReadyDriver();
      triadSel.value = readyDrv || "auto";
    }
    const ag = state.systemStatus.agents || {};
    if (ag.carbon) {
      if (el("cfgCarbonDriver")) el("cfgCarbonDriver").value = ag.carbon.driver || "agy";
      if (el("cfgCarbonPersona")) el("cfgCarbonPersona").value = state.seatPersonas.carbon || ag.carbon.persona || "planner";
      if (el("cfgCarbonBin")) el("cfgCarbonBin").value = ag.carbon.custom_binary || "";
      if (el("cfgCarbonModel")) el("cfgCarbonModel").value = ag.carbon.model || "";
      if (el("cfgCarbonLockEffort")) el("cfgCarbonLockEffort").checked = Boolean(ag.carbon.lock_discussion_effort);
      syncModalEffortOptionsForSeat(
        "carbon",
        ag.carbon.effective_discussion_effort ?? ag.carbon.discussion_effort,
        ag.carbon.effective_execution_effort ?? ag.carbon.execution_effort
      );
    }
    if (ag.grok) {
      if (el("cfgGrokDriver")) el("cfgGrokDriver").value = ag.grok.driver || "grok";
      if (el("cfgGrokPersona")) el("cfgGrokPersona").value = state.seatPersonas.grok || ag.grok.persona || "red_team";
      if (el("cfgGrokBin")) el("cfgGrokBin").value = ag.grok.custom_binary || "";
      if (el("cfgGrokModel")) el("cfgGrokModel").value = ag.grok.model || "";
      if (el("cfgGrokLockEffort")) el("cfgGrokLockEffort").checked = Boolean(ag.grok.lock_discussion_effort);
      syncModalEffortOptionsForSeat(
        "grok",
        ag.grok.effective_discussion_effort ?? ag.grok.discussion_effort,
        ag.grok.effective_execution_effort ?? ag.grok.execution_effort
      );
    }
    if (ag.astra) {
      if (el("cfgAstraDriver")) el("cfgAstraDriver").value = ag.astra.driver || "codex";
      if (el("cfgAstraPersona")) el("cfgAstraPersona").value = state.seatPersonas.astra || ag.astra.persona || "implementer";
      if (el("cfgAstraBin")) el("cfgAstraBin").value = ag.astra.custom_binary || "";
      if (el("cfgAstraModel")) el("cfgAstraModel").value = ag.astra.model || "";
      if (el("cfgAstraLockEffort")) el("cfgAstraLockEffort").checked = Boolean(ag.astra.lock_discussion_effort);
      syncModalEffortOptionsForSeat(
        "astra",
        ag.astra.effective_discussion_effort ?? ag.astra.discussion_effort,
        ag.astra.effective_execution_effort ?? ag.astra.execution_effort
      );
    }
  } else {
    AGENT_ORDER.forEach((aid) => syncModalEffortOptionsForSeat(aid));
  }
  el("settingsModal")?.classList.remove("hidden");
}

function closeSettingsModal() {
  el("settingsModal")?.classList.add("hidden");
}

async function applySelectedWorkspacePath(chosenPath, updateModalInput = false) {
  if (!chosenPath) return;
  try {
    const res = await apiFetch("/api/system/pick-folder", {
      method: "POST",
      body: JSON.stringify({
        active_session_id: state.currentSessionId || "",
        direct_path: chosenPath,
      }),
    });
    if (res.ok && res.system) {
      state.sessionWorkspaceDir = res.path || "";
      state.workspaceIsGit = Boolean(res.system.workspace_is_git);
      renderSystemStatus(res.system);
      await refreshWorkspaceFilesIndex("");
      if (updateModalInput && el("cfgWorkspaceDir")) {
        el("cfgWorkspaceDir").value = res.path || "";
      }
      showToast(`已绑定本地项目工作区：${res.path}`, "ok");
    }
  } catch (err) {
    showToast(`绑定目录失败：${err.message}`, "err");
  }
}

async function pickWorkspaceFolder(updateModalInput = false) {
  if (window.webkit?.messageHandlers?.roundtableNative) {
    state.pendingNativeFolderModal = Boolean(updateModalInput);
    window.webkit.messageHandlers.roundtableNative.postMessage({ action: "pickFolder" });
    return;
  }
  try {
    const res = await apiFetch("/api/system/pick-folder", {
      method: "POST",
      body: JSON.stringify({ active_session_id: state.currentSessionId || "" }),
    });
    if (res.cancelled) return;
    if (res.ok && res.system) {
      state.sessionWorkspaceDir = res.path || "";
      state.workspaceIsGit = Boolean(res.system.workspace_is_git);
      renderSystemStatus(res.system);
      await refreshWorkspaceFilesIndex("");
      if (updateModalInput && el("cfgWorkspaceDir")) {
        el("cfgWorkspaceDir").value = res.path || "";
      }
      showToast(`已绑定本地项目工作区：${res.path}`, "ok");
    }
  } catch (_) {
    openSettingsModal();
    showToast("请在配置弹窗中手动填写工作区路径", "warn");
  }
}

async function createNewMeetingSession() {
  const collabMode = el("collabModeSelect")?.value || "standard_roundtable";
  const res = await apiFetch("/api/sessions", {
    method: "POST",
    body: JSON.stringify({ title: "新会议", collab_mode: collabMode }),
  });
  renderSessionList(res.sessions);
  connectToSession(res.session.session_id);
  el("topicInput")?.focus();
}

function insertMentionIntoComposer(mentionText, triggerSuggest = false) {
  const input = el("topicInput");
  if (!input) return;
  const cur = input.value;
  const prefix = cur && !cur.endsWith(" ") ? " " : "";
  input.value = `${cur}${prefix}${mentionText}`;
  autoResizeComposer();
  input.focus();
  const len = input.value.length;
  input.setSelectionRange(len, len);
  if (triggerSuggest) {
    handleComposerAtTrigger();
  } else {
    renderAttachedFileChips();
  }
}

async function stopActiveSessionFlow() {
  try {
    await apiFetch(`/api/sessions/${state.currentSessionId}/stop`, { method: "POST" });
    state.isBusy = false;
    resetClientBusyTimersIfIdle();
    syncComposerAndControls();
    showToast("已中止当前运行任务", "info", 1800);
  } catch (err) {
    showToast(err.message, "err");
  }
}

async function bootstrap() {
  const savedTheme = localStorage.getItem("ai_roundtable_theme_v2") || "light";
  const savedPalette = localStorage.getItem("ai_roundtable_palette") || "pearl";
  const savedFont = localStorage.getItem("ai_roundtable_fontsize") || "comfort";
  updatePaletteUI(savedPalette);
  updateFontScaleUI(savedFont);
  updateThemeUI(savedTheme === "dark" ? "dark" : "light");

  window.__onNativeFolderPicked = (pickedPath) => {
    const updateModal = state.pendingNativeFolderModal;
    state.pendingNativeFolderModal = false;
    if (pickedPath) {
      applySelectedWorkspacePath(pickedPath, updateModal);
    }
  };

  const appMenuBtn = el("appearanceBtn");
  const appPop = el("appearancePopover");
  if (appMenuBtn && appPop) {
    appMenuBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      const willOpen = appPop.classList.contains("hidden");
      appPop.classList.toggle("hidden", !willOpen);
      appMenuBtn.classList.toggle("active-pane", willOpen);
      appMenuBtn.setAttribute("aria-expanded", String(willOpen));
    });
    appPop.addEventListener("click", (e) => e.stopPropagation());
  }

  on("personaPopover", "click", (e) => e.stopPropagation());

  on("seatPopoverQuickActions", "click", (e) => {
    const btn = e.target.closest("[data-seat-pop-act]");
    const aid = state.activePersonaSeat;
    if (!btn || !aid) return;
    e.stopPropagation();
    const act = btn.dataset.seatPopAct;
    if (act === "mention") {
      closePersonaPopover();
      insertMentionIntoComposer(`@${AGENT_NAMES[aid]} `);
    } else if (act === "solo") {
      toggleSoloSeat(aid);
    } else if (act === "toggle-enable") {
      toggleSeatParticipation(aid);
    }
  });

  on("seatPopoverEffortBox", "click", (e) => {
    const aid = state.activePersonaSeat;
    if (!aid) return;
    const effBtn = e.target.closest("[data-seat-pop-effort]");
    if (effBtn) {
      e.stopPropagation();
      updateSeatEffortQuickly(aid, { discussion_effort: effBtn.dataset.seatPopEffort });
      return;
    }
    const lockBtn = e.target.closest("[data-seat-pop-lock]");
    if (lockBtn) {
      e.stopPropagation();
      const curLocked = Boolean(state.systemStatus?.agents?.[aid]?.lock_discussion_effort);
      updateSeatEffortQuickly(aid, { lock_discussion_effort: !curLocked });
    }
  });

  on("personaOptionList", "click", (e) => {
    const opt = e.target.closest("[data-pick-persona]");
    if (opt && state.activePersonaSeat) {
      e.stopPropagation();
      applySeatPersonaChange(state.activePersonaSeat, opt.dataset.pickPersona);
    }
  });

  document.addEventListener("click", (e) => {
    closeAppearancePopover();
    if (
      !e.target.closest("#personaPopover") &&
      !e.target.closest("[data-persona-trigger]") &&
      !e.target.closest("[data-agent-seat]")
    ) {
      closePersonaPopover();
    }
    if (!e.target.closest("#atSuggestMenu") && !e.target.closest("#topicInput") && !e.target.closest("#insertFileRefBtn")) {
      closeAtSuggestMenu();
    }
  });

  document.querySelectorAll("[data-theme-opt]").forEach((btn) => {
    btn.addEventListener("click", () => updateThemeUI(btn.dataset.themeOpt));
  });

  document.querySelectorAll("[data-palette-opt]").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (document.documentElement.dataset.theme === "dark") {
        updateThemeUI("light");
      }
      updatePaletteUI(btn.dataset.paletteOpt);
    });
  });

  document.querySelectorAll("[data-font-opt]").forEach((btn) => {
    btn.addEventListener("click", () => updateFontScaleUI(btn.dataset.fontOpt));
  });

  on("brandToggleRailBtn", "click", () => toggleLeftSidebar());
  on("collapseLeftBtn", "click", () => toggleLeftSidebar(true));
  on("expandLeftBtn", "click", () => toggleLeftSidebar(false));
  on("railSessionsBtn", "click", () => {
    toggleLeftSidebar(false);
    setTimeout(() => el("sessionSearchInput")?.focus(), 120);
  });
  on("railPickFolderBtn", "click", () => pickWorkspaceFolder(false));
  on("railNewSessionBtn", "click", createNewMeetingSession);
  on("railSettingsBtn", "click", openSettingsModal);
  on("headerWsChip", "click", () => pickWorkspaceFolder(false));
  on("toggleRightBtn", "click", () => toggleRightWorkbench());

  window.__roundtableMenu = (cmd) => {
    if (cmd === "settings") openSettingsModal();
    else if (cmd === "newSession") createNewMeetingSession();
    else if (cmd === "toggleLeft") toggleLeftSidebar();
    else if (cmd === "toggleRight") toggleRightWorkbench();
  };

  document.addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "b") {
      e.preventDefault();
      toggleLeftSidebar();
    } else if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "j") {
      e.preventDefault();
      toggleRightWorkbench();
    } else if (e.key === "Escape") {
      if (state.atMenuOpen) {
        closeAtSuggestMenu();
      } else if (state.activePersonaSeat) {
        closePersonaPopover();
      } else if (appPop && !appPop.classList.contains("hidden")) {
        closeAppearancePopover();
      } else if (el("settingsModal") && !el("settingsModal").classList.contains("hidden")) {
        closeSettingsModal();
      }
    }
  });

  on("pickFolderQuickBtn", "click", () => pickWorkspaceFolder(false));
  on("emptyBindWsBtn", "click", () => pickWorkspaceFolder(false));
  on("browseWorkspaceBtn", "click", () => pickWorkspaceFolder(true));

  on("saveQuickAdvancedBtn", "click", async () => {
    const idleSec = Math.max(20, Math.min(600, Number(el("quickIdleTimeoutInput")?.value || 90)));
    const turnSec = Math.max(idleSec, Math.min(1800, Number(el("quickTurnTimeoutInput")?.value || 300)));
    try {
      const res = await apiFetch("/api/config", {
        method: "POST",
        body: JSON.stringify({
          active_session_id: state.currentSessionId || "",
          idle_timeout_sec: idleSec,
          turn_timeout_sec: turnSec,
        }),
      });
      if (res.system) renderSystemStatus(res.system);
      showToast(`已应用超时策略：空闲心跳 ${idleSec}s / 单轮上限 ${turnSec}s`, "ok", 2200);
    } catch (err) {
      showToast(`保存超时失败：${err.message}`, "err");
    }
  });

  on("testCliBtn", "click", () => runConnectivityProbe(false, el("testCliBtn")));
  on("modalTestCliBtn", "click", () => runConnectivityProbe(true, el("modalTestCliBtn")));

  syncCollabModeUI(el("collabModeSelect")?.value || "standard_roundtable");
  on("collabModeSelect", "change", (e) => syncCollabModeUI(e.target.value));
  document.querySelectorAll("[data-collab-opt]").forEach((btn) => {
    btn.addEventListener("click", () => syncCollabModeUI(btn.dataset.collabOpt));
  });

  document.querySelectorAll("[data-lineup-preset]").forEach((btn) => {
    btn.addEventListener("click", () => applyLineupPreset(btn.dataset.lineupPreset));
  });

  on("sessionSearchInput", "input", (e) => {
    state.sessionFilter = e.target.value || "";
    renderSessionList(state.sessions);
  });
  on("newSessionBtn", "click", createNewMeetingSession);

  // 精简顶栏席位胶囊：点击统一打开轻量配置浮层（含 @点名 / 单席独奏 / 暂停参会 / 推理档位 / 身份侧重）
  document.querySelectorAll("[data-agent-seat]").forEach((seatCard) => {
    const aid = seatCard.dataset.agentSeat;
    seatCard.addEventListener("click", (e) => {
      e.stopPropagation();
      shiftAmbientGlowForSpeaker(aid);
      openPersonaPopover(aid, seatCard);
    });
  });

  document.querySelectorAll("[data-starter-topic]").forEach((card) => {
    card.addEventListener("click", () => {
      const input = el("topicInput");
      if (!input) return;
      input.value = card.dataset.starterTopic || "";
      autoResizeComposer();
      renderAttachedFileChips();
      input.focus();
    });
  });

  const chatStream = el("chatStream");
  if (chatStream) {
    chatStream.addEventListener("scroll", () => {
      state.stickToBottom = isStreamNearBottom();
      if (state.stickToBottom) {
        el("scrollBottomBtn")?.classList.add("hidden");
      }
    });

    chatStream.addEventListener("click", async (e) => {
      const copyCodeBtn = e.target.closest(".md-copy-code");
      if (copyCodeBtn) {
        const codeEl = copyCodeBtn.closest(".md-code-block")?.querySelector("code");
        if (codeEl) await copyText(codeEl.textContent || "", "代码片段已复制");
        return;
      }

      const actBtn = e.target.closest("[data-msg-act]");
      if (!actBtn) return;
      const card = actBtn.closest(".msg-card");
      const msg = state.messagesById.get(card?.dataset.msgId);
      if (!msg) return;

      const act = actBtn.dataset.msgAct;
      if (act === "toggle-fold") {
        const nextCollapsed = !card.classList.contains("is-collapsed");
        state.msgCollapseState.set(msg.id, nextCollapsed);
        createOrUpdateMessageCard(msg);
        if (nextCollapsed && card.offsetTop < chatStream.scrollTop) {
          chatStream.scrollTop = Math.max(0, card.offsetTop - 12);
        }
      } else if (act === "copy") {
        await copyText(stripTrailingStatusTag(msg.content || ""), "发言内容已复制");
      } else if (act === "reply") {
        if (AGENT_NAMES[msg.speaker]) {
          insertMentionIntoComposer(`@${AGENT_NAMES[msg.speaker]} `);
        }
      } else if (act === "open-settings") {
        openSettingsModal();
      } else if (act === "downgrade-retry") {
        await downgradeAndRetrySeat(msg, actBtn.dataset.nextEffort, actBtn);
      } else if (act === "retry-seat") {
        if (!AGENT_NAMES[msg.speaker] || !state.currentSessionId) return;
        const origTxt = actBtn.textContent;
        actBtn.disabled = true;
        actBtn.textContent = "重试中…";
        state.stickToBottom = true;
        try {
          await apiFetch(`/api/sessions/${state.currentSessionId}/retry`, {
            method: "POST",
            body: JSON.stringify({
              agent_id: msg.speaker,
              message_id: msg.id,
            }),
          });
          showToast(`已触发 ${AGENT_NAMES[msg.speaker]} 单席重试`, "info", 1800);
        } catch (err) {
          actBtn.disabled = false;
          actBtn.textContent = origTxt;
          showToast(`单席重试失败：${err.message}`, "err");
        }
      } else if (act === "pin") {
        const bucketMap = {
          carbon: "carbon_plan",
          grok: "grok_risks",
          astra: "astra_actions",
          chair: "chair_constraints",
          system: "carbon_plan",
        };
        const snippet = extractSmartPinSnippet(msg, card);
        if (!snippet) return;
        try {
          switchWorkbenchTab("whiteboard");
          await postWhiteboardMutation({
            op: "add",
            bucket: bucketMap[msg.speaker] || "chair_constraints",
            source_seat: AGENT_NAMES[msg.speaker] ? msg.speaker : "chair",
            source_msg_id: msg.id,
            text: snippet,
          });
          showToast("已收入右侧结构化白板（支持划词精准摘录，可一键置顶共识）", "ok", 2200);
        } catch (err) {
          showToast(`加入白板失败：${err.message}`, "err");
        }
      }
    });
  }

  on("scrollBottomBtn", "click", () => {
    state.stickToBottom = true;
    scrollToBottom(true);
  });

  // @文件路径 自动联想菜单交互与移除胶囊交互
  on("atSuggestMenu", "mousedown", (e) => {
    const bindItem = e.target.closest("[data-at-bind]");
    if (bindItem) {
      e.preventDefault();
      applyAtSuggestion(0);
      return;
    }
    const item = e.target.closest("[data-at-idx]");
    if (item) {
      e.preventDefault();
      applyAtSuggestion(Number(item.dataset.atIdx));
    }
  });

  on("attachedFilesBar", "click", (e) => {
    const rmBtn = e.target.closest("[data-remove-ref]");
    if (rmBtn) {
      e.stopPropagation();
      const rawToken = rmBtn.dataset.removeRef;
      const input = el("topicInput");
      if (input && rawToken) {
        input.value = input.value.replace(rawToken, "").replace(/\s{2,}/g, " ").trimStart();
        autoResizeComposer();
        renderAttachedFileChips();
        input.focus();
      }
      return;
    }
    const warnChip = e.target.closest(".file-chip-warn");
    if (warnChip && isUnboundWorkspace(state.sessionWorkspaceDir || state.systemStatus?.workspace_dir || "")) {
      pickWorkspaceFolder(false);
    }
  });

  on("topicInput", "compositionstart", () => {
    if (composingUnlockTimer) {
      clearTimeout(composingUnlockTimer);
      composingUnlockTimer = 0;
    }
    composingLock = true;
  });

  on("topicInput", "compositionend", () => {
    if (composingUnlockTimer) {
      clearTimeout(composingUnlockTimer);
    }
    composingUnlockTimer = setTimeout(() => {
      composingLock = false;
      composingUnlockTimer = 0;
    }, 35);
  });

  on("topicInput", "input", () => {
    autoResizeComposer();
    handleComposerAtTrigger();
  });

  on("topicInput", "click", handleComposerAtTrigger);

  on("primaryActionBtn", "click", handlePrimaryComposerSubmit);

  on("topicInput", "keydown", (e) => {
    if (e.isComposing || e.keyCode === 229 || composingLock) {
      return;
    }

    if (state.atMenuOpen && state.atCandidates.length > 0) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        state.atActiveIdx = (state.atActiveIdx + 1) % state.atCandidates.length;
        renderAtSuggestMenu(
          state.atCandidates,
          Boolean(state.atCandidates[0]?.isBindAction)
        );
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        state.atActiveIdx =
          (state.atActiveIdx - 1 + state.atCandidates.length) % state.atCandidates.length;
        renderAtSuggestMenu(
          state.atCandidates,
          Boolean(state.atCandidates[0]?.isBindAction)
        );
        return;
      }
      if (e.key === "Enter" || e.key === "Tab") {
        e.preventDefault();
        applyAtSuggestion(state.atActiveIdx);
        return;
      }
      if (e.key === "Escape") {
        e.preventDefault();
        closeAtSuggestMenu();
        return;
      }
    }

    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handlePrimaryComposerSubmit();
    }
  });

  // 事件委托：动态点名芯片与动态快捷追问按钮
  on("mentionChipsWrap", "click", (e) => {
    const btn = e.target.closest(".mention-btn[data-mention]");
    if (btn) {
      insertMentionIntoComposer(btn.dataset.mention);
    }
  });

  on("insertFileRefBtn", "click", (e) => {
    e.stopPropagation();
    insertMentionIntoComposer("@", true);
  });

  on("cueGroupLeft", "click", async (e) => {
    const btn = e.target.closest("[data-cue-agent]");
    if (!btn) return;
    state.stickToBottom = true;
    shiftAmbientGlowForSpeaker(btn.dataset.cueAgent);
    try {
      await apiFetch(`/api/sessions/${state.currentSessionId}/cue`, {
        method: "POST",
        body: JSON.stringify({
          agent_id: btn.dataset.cueAgent,
          instruction: btn.dataset.cueText,
        }),
      });
    } catch (err) {
      showToast(err.message, "err");
    }
  });

  on("stopFlowBtn", "click", stopActiveSessionFlow);
  on("stopExecFromTabBtn", "click", stopActiveSessionFlow);

  on("restartTopicBtn", "click", async () => {
    if (!state.currentTopic) return;
    const ok = window.confirm(
      "将清空当前会话的旧发言，并按当前讨论模式、参会席位与身份侧重重新发起本议题讨论。确认继续吗？"
    );
    if (!ok) return;
    state.stickToBottom = true;
    try {
      const collabMode = el("collabModeSelect")?.value || "standard_roundtable";
      await apiFetch(`/api/sessions/${state.currentSessionId}/start`, {
        method: "POST",
        body: JSON.stringify({
          topic: state.currentTopic,
          collab_mode: collabMode,
          enabled_agents: state.enabledAgents,
          seat_personas: state.seatPersonas,
          executor_agent: state.executorAgent,
          reset_history: true,
        }),
      });
      showToast("已重新开启本议题讨论", "info", 1800);
    } catch (err) {
      showToast(`重开失败：${err.message}`, "err");
    }
  });

  on("concludeBtn", "click", async () => {
    if (!state.currentTopic) {
      showToast("请先发起会议议题", "warn");
      return;
    }
    state.stickToBottom = true;
    try {
      await apiFetch(`/api/sessions/${state.currentSessionId}/conclude`, { method: "POST" });
    } catch (err) {
      showToast(err.message, "err");
    }
  });

  on("wbConflictBanner", "click", async (e) => {
    const btn = e.target.closest("[data-wb-conflict-act]");
    if (!btn) return;
    const act = btn.dataset.wbConflictAct;
    const c = state.wbConflictState;
    if (act === "force-save" && c && c.itemId && c.draftText && c.latestVersion) {
      try {
        state.wbEditingDraft = null;
        await postWhiteboardMutation({
          op: "update",
          item_id: c.itemId,
          expected_version: c.latestVersion,
          text: c.draftText,
        });
        state.wbConflictState = null;
        renderWhiteboardConflictBanner();
        showToast("已按最新版本号覆盖保存您的编辑草稿", "ok", 2000);
      } catch (err) {
        showToast(`覆盖保存失败：${err.message}`, "err");
      }
    } else if (act === "dismiss") {
      state.wbConflictState = null;
      state.wbEditingDraft = null;
      renderWhiteboardConflictBanner();
      renderWhiteboard(state.whiteboard, true);
    }
  });

  on("wbSeatFilterBar", "click", (e) => {
    const pill = e.target.closest("[data-wb-filter]");
    if (!pill) return;
    state.wbFilterSeat = pill.dataset.wbFilter || "all";
    renderWhiteboard(state.whiteboard, true);
  });

  on("wbToggleExpandBtn", "click", () => {
    state.wbExcerptsExpanded = !state.wbExcerptsExpanded;
    renderWhiteboard(state.whiteboard, true);
  });

  document.querySelectorAll("[data-wb-add]").forEach((btn) => {
    const bucket = btn.dataset.wbAdd;
    const wrap = el(`wb-editor-${bucket}`);
    const input = wrap?.querySelector("input");
    if (!wrap || !input) return;

    btn.addEventListener("click", () => {
      wrap.classList.toggle("hidden");
      if (!wrap.classList.contains("hidden")) input.focus();
    });

    input.addEventListener("keydown", async (e) => {
      if (e.key === "Escape") {
        wrap.classList.add("hidden");
        return;
      }
      if (e.key === "Enter" && !e.isComposing) {
        e.preventDefault();
        const val = input.value.trim();
        if (!val) return;
        input.value = "";
        wrap.classList.add("hidden");
        try {
          const defaultSource =
            bucket === "excerpt" && state.wbFilterSeat && state.wbFilterSeat !== "all"
              ? state.wbFilterSeat
              : "chair";
          await postWhiteboardMutation({
            op: "add",
            bucket,
            source_seat: defaultSource,
            pinned: bucket === "consensus",
            adopted: bucket === "consensus",
            text: val,
          });
        } catch (err) {
          showToast(err.message, "err");
        }
      }
    });
  });

  // 主刀执行席位选择（Carbon / Grok / Astra）
  document.querySelectorAll("#executorSegmented .seg-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const nextExec = btn.dataset.execAgent;
      if (!nextExec || !AGENT_NAMES[nextExec]) return;
      state.executorAgent = nextExec;
      syncPersonasAndExecutorUI();
      if (state.currentSessionId) {
        try {
          const res = await apiFetch(`/api/sessions/${state.currentSessionId}/seats`, {
            method: "POST",
            body: JSON.stringify({ executor_agent: nextExec }),
          });
          applySeatsResponse(res);
          showToast(`已指定 ${AGENT_NAMES[nextExec]} 为主刀执行席位`, "info", 1600);
        } catch (err) {
          showToast(err.message, "err");
        }
      }
    });
  });

  document.querySelectorAll("#sandboxSegmented .seg-btn").forEach((b) => {
    b.addEventListener("click", () => {
      const isWrite = b.dataset.writeMode === "write";
      const allowWrite = el("allowWriteCheckbox");
      if (allowWrite) allowWrite.checked = isWrite;
      document.querySelectorAll("#sandboxSegmented .seg-btn").forEach((x) => {
        x.classList.toggle("active", x === b);
      });
      syncExecModeUI();
    });
  });
  syncExecModeUI();

  const triggerExec = async () => {
    if (!state.currentTopic) {
      showToast("请先进行议题讨论或输入议题后再触发执行", "warn");
      return;
    }
    const execAid = AGENT_NAMES[state.executorAgent] ? state.executorAgent : "astra";
    const execName = AGENT_NAMES[execAid] || "Astra";
    const allowWrite = Boolean(el("allowWriteCheckbox")?.checked);
    const wsDir = state.sessionWorkspaceDir || state.systemStatus?.workspace_dir || "";
    const unbound = isUnboundWorkspace(wsDir);

    if (allowWrite && !unbound) {
      const parts = wsDir.split("/").filter(Boolean);
      const folderName = parts.length ? parts[parts.length - 1] : wsDir;
      const warnMsg = state.workspaceIsGit
        ? `即将授权 ${execName} 直接修改本地项目「${folderName}」中的文件（系统会自动保存执行前 Git 快照供一键回滚）。确认开始写入执行吗？`
        : `注意：项目「${folderName}」尚未初始化 Git 仓库，写入后无法通过一键 Git 回滚恢复！确认授权 ${execName} 直接修改本地文件吗？`;
      if (!window.confirm(warnMsg)) return;
    }

    switchWorkbenchTab("terminal");
    shiftAmbientGlowForSpeaker(execAid);
    state.execStreamingBuffer = "";
    if (state.whiteboard) state.whiteboard.exec_logs = [];
    const termLogs = el("astraTermLogs");
    if (termLogs) termLogs.textContent = `正在启动 ${execName} 执行引擎...`;
    try {
      await apiFetch(`/api/sessions/${state.currentSessionId}/execute`, {
        method: "POST",
        body: JSON.stringify({
          allow_workspace_write: allowWrite,
          executor_id: execAid,
        }),
      });
    } catch (err) {
      showToast(`启动执行失败：${err.message}`, "err");
    }
  };
  on("executeBtn", "click", triggerExec);
  on("runExecFromTabBtn", "click", triggerExec);
  on("wbToExecBtn", "click", () => switchWorkbenchTab("terminal"));

  document.querySelectorAll(".wb-tab").forEach((tab) => {
    tab.addEventListener("click", () => switchWorkbenchTab(tab.dataset.tab));
  });
  on("copyMdBtn", "click", () => copyText(buildMinutesMarkdown(), "完整会议纪要已复制"));
  on("exportMdBtn", "click", exportMinutesMarkdown);

  on("copyTermBtn", "click", () =>
    copyText(el("astraTermLogs")?.textContent || "", "终端日志已复制")
  );
  on("clearTermBtn", "click", () => {
    state.execStreamingBuffer = "";
    if (state.whiteboard) state.whiteboard.exec_logs = [];
    const termLogs = el("astraTermLogs");
    if (termLogs) termLogs.textContent = "日志显示已清空";
  });
  on("copyDiffBtn", "click", () => {
    if (!state.rawDiffText) {
      showToast("当前暂无可复制的 Diff 补丁", "warn");
      return;
    }
    copyText(state.rawDiffText, "Diff 补丁已复制");
  });
  on("rollbackExecBtn", "click", async () => {
    const ok = window.confirm(
      "回滚将恢复至本次执行前的 Git 快照，并删除本次新增的未跟踪文件（若您在执行后手动修改过文件也将一并还原）。确认执行回滚吗？"
    );
    if (!ok) return;
    try {
      const res = await apiFetch(`/api/sessions/${state.currentSessionId}/rollback`, {
        method: "POST",
      });
      showToast(res.message || "已回滚本地工作区修改", "ok", 3000);
    } catch (err) {
      showToast(`回滚失败：${err.message}`, "err");
    }
  });

  AGENT_ORDER.forEach((aid) => {
    const cap = aid.charAt(0).toUpperCase() + aid.slice(1);
    on(`cfg${cap}Driver`, "change", () => {
      const modelEl = el(`cfg${cap}Model`);
      const nextDriver = el(`cfg${cap}Driver`)?.value || "auto";
      if (modelEl && modelEl.value.trim()) {
        const valLow = modelEl.value.trim().toLowerCase();
        const belongsAgy = valLow.includes("gemini") || valLow.includes("orchestrator") || valLow.includes("claude");
        const belongsGrok = valLow.includes("grok");
        const belongsCodex = valLow.includes("gpt") || valLow.includes("o3") || valLow.includes("o4");
        if (
          (nextDriver === "agy" && (belongsGrok || belongsCodex)) ||
          (nextDriver === "grok" && (belongsAgy || belongsCodex)) ||
          (nextDriver === "codex" && (belongsAgy || belongsGrok))
        ) {
          modelEl.value = "";
        }
      }
      syncModalEffortOptionsForSeat(aid);
    });
    on(`cfg${cap}Model`, "input", () => syncModalEffortOptionsForSeat(aid));
    on(`cfg${cap}Model`, "change", () => syncModalEffortOptionsForSeat(aid));
  });

  on("quickSingleCliTriadBtn", "click", async () => {
    const rawPick = el("singleCliTriadDriver")?.value || "auto";
    const chosenDriver = rawPick === "auto" ? detectFirstReadyDriver() : rawPick;
    const defaultModelMap = {
      agy: "gemini-4-carbon",
      grok: "grok-4.7",
      codex: "gpt-6-astra",
    };
    const triadPersonas = {
      carbon: "planner",
      grok: "red_team",
      astra: "implementer",
    };

    let sharedCustomBin = "";
    AGENT_ORDER.forEach((aid) => {
      const cap = aid.charAt(0).toUpperCase() + aid.slice(1);
      const curDrv = el(`cfg${cap}Driver`)?.value;
      const curBin = (el(`cfg${cap}Bin`)?.value || "").trim();
      if (!sharedCustomBin && curBin && (curDrv === chosenDriver || curDrv === "auto")) {
        sharedCustomBin = curBin;
      }
    });

    if (el("cfgSingleCliFallback")) el("cfgSingleCliFallback").checked = true;

    AGENT_ORDER.forEach((aid) => {
      const cap = aid.charAt(0).toUpperCase() + aid.slice(1);
      if (el(`cfg${cap}Driver`)) el(`cfg${cap}Driver`).value = chosenDriver;
      if (el(`cfg${cap}Persona`)) el(`cfg${cap}Persona`).value = triadPersonas[aid];
      if (el(`cfg${cap}Bin`)) el(`cfg${cap}Bin`).value = sharedCustomBin;
      if (el(`cfg${cap}Model`)) el(`cfg${cap}Model`).value = defaultModelMap[chosenDriver] || "";
      const spec = resolveFrontendEffortSpec(chosenDriver, defaultModelMap[chosenDriver] || "", aid);
      syncModalEffortOptionsForSeat(aid, spec.defaultEffort, spec.defaultEffort);
    });

    const newWsDir = (el("cfgWorkspaceDir")?.value || "").trim();
    const agentsDraft = collectModalAgentDrafts();
    try {
      const res = await apiFetch("/api/config", {
        method: "POST",
        body: JSON.stringify({
          active_session_id: state.currentSessionId || "",
          workspace_dir: newWsDir,
          allow_single_cli_fallback: true,
          agents: agentsDraft,
        }),
      });
      state.pingResults = {};
      state.seatPersonas = { ...triadPersonas };
      renderSystemStatus(res.system);

      if (state.currentSessionId) {
        const seatRes = await apiFetch(`/api/sessions/${state.currentSessionId}/seats`, {
          method: "POST",
          body: JSON.stringify({
            enabled_agents: ["carbon", "grok", "astra"],
            seat_personas: triadPersonas,
            executor_agent: "astra",
          }),
        });
        applySeatsResponse(seatRes);
      } else {
        state.enabledAgents = ["carbon", "grok", "astra"];
        syncPersonasAndExecutorUI();
      }
      closeSettingsModal();
      const drvLabel = { agy: "Antigravity (agy)", grok: "Grok CLI", codex: "Codex CLI" }[chosenDriver] || chosenDriver;
      showToast(`已启用「${drvLabel}」单 CLI 分饰三席（规划 + 挑刺 + 落地），讨论将自动无状态串行进行`, "ok", 3600);
    } catch (err) {
      showToast(`一键配置失败：${err.message}`, "err");
    }
  });

  on("openSettingsBtn", "click", openSettingsModal);
  on("closeSettingsBtn", "click", closeSettingsModal);
  on("cancelSettingsBtn", "click", closeSettingsModal);
  on("settingsModal", "click", (e) => {
    if (e.target === el("settingsModal")) closeSettingsModal();
  });

  on("saveSettingsBtn", "click", async () => {
    const newWsDir = (el("cfgWorkspaceDir")?.value || "").trim();
    const idleSec = Math.max(20, Math.min(600, Number(el("cfgIdleTimeout")?.value || 90)));
    const turnSec = Math.max(idleSec, Math.min(1800, Number(el("cfgTurnTimeout")?.value || 300)));
    const agentsDraft = collectModalAgentDrafts();
    const payload = {
      active_session_id: state.currentSessionId || "",
      workspace_dir: newWsDir,
      idle_timeout_sec: idleSec,
      turn_timeout_sec: turnSec,
      allow_single_cli_fallback: Boolean(el("cfgSingleCliFallback")?.checked),
      agents: agentsDraft,
    };
    try {
      const res = await apiFetch("/api/config", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      state.pingResults = {};
      if (newWsDir) {
        state.sessionWorkspaceDir = newWsDir;
        state.workspaceIsGit = Boolean(res.system?.workspace_is_git);
      }
      state.seatPersonas = {
        carbon: payload.agents.carbon.persona,
        grok: payload.agents.grok.persona,
        astra: payload.agents.astra.persona,
      };
      renderSystemStatus(res.system);
      syncPersonasAndExecutorUI();
      await refreshWorkspaceFilesIndex("");
      closeSettingsModal();
      showToast("配置已保存并完成模型档位校验与 CLI 探测", "ok");
    } catch (err) {
      showToast(`保存失败：${err.message}`, "err");
    }
  });

  const initData = await apiFetch("/api/status");
  renderSystemStatus(initData.system);
  renderSessionList(initData.sessions);
  connectToSession(initData.default_session_id);
}

bootstrap().catch((err) => {
  console.error("初始化失败:", err);
  showToast(`连接本地服务失败：${err.message}`, "err", 5000);
});
