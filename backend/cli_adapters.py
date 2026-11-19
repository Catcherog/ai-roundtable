# -*- coding: utf-8 -*-
"""
AI圆桌 — 真实本地 CLI 流式适配层（精准模型档位白名单 + 7大预设身份 + 单 CLI 无状态圆桌 + 流式终端）
支持能力：
1. 席位（Carbon/Grok/Astra）、底层驱动（agy/grok/codex/auto）与 7 种预设身份（Persona）三层完全解耦：
   支持任选任意席位一键独奏（设计 + 执行一体），也支持仅 1 个可用 CLI 时无状态分次串行饰演三席圆桌。
2. 建立「CLI 驱动 + 模型」维度的合法推理档位白名单：agy 下 gemini-4-carbon 精准收敛至 low/medium/high（默认 high），
   grok-4.7 允许至 xhigh，gpt-6-astra 允许至 max；异常分类精准区分档位不兼容、429/Quota、鉴权失效与超时。
3. 深度本地项目上下文感知：3 层目录树 + 5 大工程清单 + 单轮最高 12 个 @文件（支持 :起始行-结束行，单文件最高 2500 行 / 100K 字符），修复常驻增量轮次新 @文件 盲区。
4. 独立 synthesis 长文决议通道（解除短字数上限）+ 实时流式执行事件（exec_delta）。
"""

from __future__ import annotations

import ast
import asyncio
import glob
import json
import os
import re
# AI_ROUNDTABLE_V2_UPGRADE_20261114
import shutil
import signal
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import AsyncGenerator, Dict, List, Optional, Set, Tuple

from .context import (
    count_file_lines_cached,
    invalidate_workspace_index,
    run_index_in_thread,
    scan_workspace_index_cached,
)
from .domain import (
    ALL_SEAT_IDS,
    DRIVER_PROVIDER_LABELS,
    IMMUTABLE_SEAT_CATALOG,
    normalize_driver_family_key,
)
from .drivers import (
    SupervisedProcessHandle,
    build_driver_specs_and_capabilities,
    load_driver_catalog,
    spawn_supervised_cli,
    terminate_and_reap_process_group,
)
from .attachments import SessionAttachmentManager
from .workspace_backup import WorkspaceBackup


_CACHED_LOGIN_PATH: Optional[str] = None
_CACHED_HOST_ENV: Optional[Dict[str, str]] = None

VALID_EFFORT_LEVELS = ("", "none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra")
CANONICAL_EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")
ORDERED_EFFORT_LEVELS = ("minimal", "low", "medium", "high", "xhigh", "max")
VALID_DRIVERS = ("auto", "agy", "grok", "codex", "claude", "ollama")

PERSONA_PRESETS: Dict[str, dict] = {
    "planner": {
        "key": "planner",
        "label": "架构规划",
        "short_tag": "规划",
        "wb_kind": "decision",
        "wb_title": "已确认共识与约束",
        "cue_btn": "请 {name} 收敛方案",
        "cue_prompt": "请整合各方分歧，收敛出清晰的架构边界、阶段优先级与取舍结论",
        "is_synthesizer": True,
        "prompt": (
            "思维模型：自顶向下拆解系统边界、明确架构取舍优先级、制定分阶段最小闭环路线并裁定各方技术分歧。"
            "严禁客套寒暄、禁止空洞附和或复述他人原话，只输出结构化边界裁定与明确取舍结论。"
        ),
    },
    "red_team": {
        "key": "red_team",
        "label": "风险审计",
        "short_tag": "审计",
        "wb_kind": "risk",
        "wb_title": "待决争议与风险项",
        "cue_btn": "请 {name} 审计风险",
        "cue_prompt": "请审计当前方案遗漏的隐性假设、潜在风险、并发竞态与失效反例",
        "is_synthesizer": False,
        "prompt": (
            "思维模型：反向假设检验与第一性原理压力审计，专门识别架构盲区、隐性错误前提、并发竞态、异常回退缺失与极端失效反例。"
            "绝对禁止任何“同意/赞同/说得好/整体可行/基本认可/补充一点”等客套附和或缓和铺垫！"
            "开篇必须直指实质漏洞、隐性错误假设或具体失效场景，并给出可验证的安全防线或替代路线。"
        ),
    },
    "implementer": {
        "key": "implementer",
        "label": "工程实现",
        "short_tag": "工程",
        "wb_kind": "action",
        "wb_title": "待执行任务清单",
        "cue_btn": "请 {name} 评估实现",
        "cue_prompt": "请评估具体改动文件范围、接口契约、实施步骤与验证方式",
        "is_synthesizer": False,
        "prompt": (
            "思维模型：务实评估工程选型、实现复杂度、改动文件与函数调用链范围、最小验证命令与演进成本。"
            "严禁客套附和、禁止重复宏观空话或盲从过度抽象，只输出可直接编码实施的文件级改造路径。"
        ),
    },
    "fullstack_solo": {
        "key": "fullstack_solo",
        "label": "全栈架构",
        "short_tag": "全栈",
        "wb_kind": "decision",
        "wb_title": "已确认共识与约束",
        "cue_btn": "请 {name} 深化设计",
        "cue_prompt": "请深化核心全栈架构设计、关键边界防线与可直接编码的文件级实施清单",
        "is_synthesizer": True,
        "prompt": (
            "思维模型：全栈系统架构视角，统筹前后端数据流契约、关键异常边界自检与文件级可执行实施步骤，"
            "严禁客套附和与复述已知信息，兼顾顶层架构一致性与工程落地闭环。"
        ),
    },
    "product_ux": {
        "key": "product_ux",
        "label": "产品交互",
        "short_tag": "交互",
        "wb_kind": "action",
        "wb_title": "待执行任务清单",
        "cue_btn": "请 {name} 评估交互",
        "cue_prompt": "请从用户认知负担、核心操作流、信息层级与异常状态反馈维度提出交互改进方案",
        "is_synthesizer": False,
        "prompt": (
            "思维模型：以用户高频工作流与认知负荷为核心，审视界面层级、信息降噪、默认态合理性、"
            "边界状态反馈与键盘/指针交互细节，严禁寒暄附和与重复前人观点，直接收敛可感知的交互改进动作。"
        ),
    },
    "perf_sre": {
        "key": "perf_sre",
        "label": "性能与稳定性",
        "short_tag": "性能",
        "wb_kind": "risk",
        "wb_title": "待决争议与风险项",
        "cue_btn": "请 {name} 评估性能",
        "cue_prompt": "请评估端到端响应延迟瓶颈、并发锁竞争、资源泄漏与超时恢复护栏",
        "is_synthesizer": False,
        "prompt": (
            "思维模型：聚焦端到端响应延迟、子进程与内存生命周期管理、并发锁竞争、超时熔断与故障恢复护栏，"
            "严禁泛泛赞同或复述架构原话，以量化工程视角指出性能瓶颈与稳定性加固约束。"
        ),
    },
    "qa_audit": {
        "key": "qa_audit",
        "label": "测试与验证",
        "short_tag": "验证",
        "wb_kind": "action",
        "wb_title": "待执行任务清单",
        "cue_btn": "请 {name} 制定验证",
        "cue_prompt": "请制定异常边界输入测试矩阵、回归核验项与自动化验证命令",
        "is_synthesizer": False,
        "prompt": (
            "思维模型：站在严苛质量验证视角，拆解正常流、异常流、空值越界、并发冲突与状态迁移边界，"
            "严禁客套附和与笼统表态，直接输出可逐条勾选执行的验证矩阵与回归自检命令。"
        ),
    },
}

VALID_PERSONAS = tuple(PERSONA_PRESETS.keys())

DEFAULT_SEAT_PERSONAS: Dict[str, str] = {
    "carbon": "planner",
    "grok": "red_team",
    "astra": "implementer",
    "vega": "product_ux",
    "titan": "perf_sre",
    "prism": "qa_audit",
}

ROSTER_NAME_PRESETS: Dict[str, dict] = {
    "role_experts": {
        "key": "role_experts",
        "label": "专业职能称呼（推荐默认）",
        "desc": "脱离具体模型名，按圆桌席位职责直观称呼",
        "names": {
            "carbon": "架构师",
            "grok": "审计官",
            "astra": "工程师",
            "vega": "交互设计",
            "titan": "性能专家",
            "prism": "质量验证",
        },
    },
    "council_alpha": {
        "key": "council_alpha",
        "label": "中立席位代号（Alpha ~ Zeta）",
        "desc": "适合任意异构或单引擎多角色并发组合的中立代号",
        "names": {
            "carbon": "Alpha",
            "grok": "Beta",
            "astra": "Gamma",
            "vega": "Delta",
            "titan": "Epsilon",
            "prism": "Zeta",
        },
    },
    "product_studio": {
        "key": "product_studio",
        "label": "产品研发委员会（总监 / 交互 / 红队 / 主程 / SRE / QA）",
        "desc": "适合产品方案评审、交互收敛与高可靠全栈交付",
        "names": {
            "carbon": "产品总监",
            "grok": "红队审计",
            "astra": "研发主程",
            "vega": "体验设计",
            "titan": "稳定性架构",
            "prism": "测试主管",
        },
    },
    "auto_driver": {
        "key": "auto_driver",
        "label": "跟随底层引擎（自动映射 CLI·职责）",
        "desc": "根据各席实际绑定的底层 CLI 与当前职责自动生成名称",
        "names": {},
    },
    "classic": {
        "key": "classic",
        "label": "经典默认代号（Carbon / Grok / Astra / Vega / Titan / Prism）",
        "desc": "保留席位工程代号",
        "names": {
            "carbon": "Carbon",
            "grok": "Grok",
            "astra": "Astra",
            "vega": "Vega",
            "titan": "Titan",
            "prism": "Prism",
        },
    },
}

VALID_ROSTER_PRESETS = tuple(ROSTER_NAME_PRESETS.keys())

DRIVER_SPECS: Dict[str, dict] = {
    "agy": {
        "cli_name": "Antigravity CLI",
        "binary_candidates": ["agy", "antigravity"],
        "default_model": "gemini-4-carbon",
        "default_discuss_effort": "high",
        "default_exec_effort": "high",
    },
    "grok": {
        "cli_name": "Grok CLI",
        "binary_candidates": ["grok"],
        "default_model": "grok-4.7",
        "default_discuss_effort": "xhigh",
        "default_exec_effort": "xhigh",
    },
    "codex": {
        "cli_name": "Codex CLI",
        "binary_candidates": ["codex"],
        "default_model": "gpt-6-astra",
        "default_discuss_effort": "max",
        "default_exec_effort": "max",
    },
}

# 按「CLI 驱动 + 模型名」维度的合法推理档位精确映射表
MODEL_EFFORT_CAPABILITIES: Dict[str, Dict[str, dict]] = {
    "agy": {
        "gemini-4-carbon": {
            "allowed": ["low", "medium", "high"],
            "default": "high",
            "supports_effort": True,
        },
        "gemini-4-argon": {
            "allowed": ["low", "medium", "high"],
            "default": "high",
            "supports_effort": True,
        },
        "gemini-4-hydrogen": {
            "allowed": ["low", "medium", "high", "xhigh"],
            "default": "xhigh",
            "supports_effort": True,
        },
        "gemini-4-hydrogen*": {
            "allowed": ["low", "medium", "high", "xhigh"],
            "default": "xhigh",
            "supports_effort": True,
        },
        "orchestrator (carbon)": {
            "allowed": [],
            "default": "",
            "supports_effort": False,
        },
        "orchestrator (argon)": {
            "allowed": [],
            "default": "",
            "supports_effort": False,
        },
        "gemini-pro-orchestrator": {
            "allowed": [],
            "default": "",
            "supports_effort": False,
        },
        "gemini-pro-orchestrator-argon": {
            "allowed": [],
            "default": "",
            "supports_effort": False,
        },
        "gemini-*": {
            "allowed": ["low", "medium", "high"],
            "default": "high",
            "supports_effort": True,
        },
        "claude-*": {
            "allowed": ["low", "medium", "high"],
            "default": "high",
            "supports_effort": True,
        },
        "*": {
            "allowed": ["low", "medium", "high"],
            "default": "high",
            "supports_effort": True,
        },
    },
    "grok": {
        "grok-4.7": {
            "allowed": ["low", "medium", "high", "xhigh"],
            "default": "xhigh",
            "supports_effort": True,
        },
        "grok-*": {
            "allowed": ["low", "medium", "high", "xhigh"],
            "default": "xhigh",
            "supports_effort": True,
        },
        "*": {
            "allowed": ["low", "medium", "high", "xhigh"],
            "default": "xhigh",
            "supports_effort": True,
        },
    },
    "codex": {
        "gpt-6-astra": {
            "allowed": ["low", "medium", "high", "xhigh", "max"],
            "default": "max",
            "supports_effort": True,
        },
        "gpt-6.1-sol": {
            "allowed": ["low", "medium", "high", "xhigh"],
            "default": "xhigh",
            "supports_effort": True,
        },
        "*": {
            "allowed": ["low", "medium", "high", "xhigh", "max"],
            "default": "max",
            "supports_effort": True,
        },
    },
}

_DRIVER_EXCLUSIVE_DEFAULT_MODELS: Dict[str, str] = {
    "gemini-4-carbon": "agy",
    "gemini-4-argon": "agy",
    "gemini-4-hydrogen": "agy",
    "gemini-pro-orchestrator": "agy",
    "gemini-pro-orchestrator-argon": "agy",
    "orchestrator (carbon)": "agy",
    "orchestrator (argon)": "agy",
    "grok-4.7": "grok",
    "gpt-6-astra": "codex",
    "gpt-6.1-sol": "codex",
}

DEFAULT_SEAT_DRIVERS: Dict[str, str] = {
    "carbon": "agy",
    "grok": "grok",
    "astra": "codex",
    "vega": "agy",
    "titan": "codex",
    "prism": "grok",
}

DEFAULT_TOP_MODELS: Dict[str, Tuple[str, str]] = {
    "carbon": ("gemini-4-carbon", "high"),
    "grok": ("grok-4.7", "xhigh"),
    "astra": ("gpt-6-astra", "max"),
    "vega": ("", "high"),
    "titan": ("", "high"),
    "prism": ("", "high"),
}


def _refresh_declarative_driver_tables() -> None:
    """热同步外置声明式 CLI 目录（内置 driver_catalog.json + ~/.ai-roundtable/drivers.json）。"""
    global VALID_DRIVERS
    specs, caps, fb_paths, excl = build_driver_specs_and_capabilities()
    DRIVER_SPECS.update(specs)
    MODEL_EFFORT_CAPABILITIES.update(caps)
    for dk, p_list in fb_paths.items():
        if p_list:
            DRIVER_FALLBACK_PATHS[dk] = p_list
    _DRIVER_EXCLUSIVE_DEFAULT_MODELS.update(excl)
    VALID_DRIVERS = ("auto",) + tuple(DRIVER_SPECS.keys())



CODEX_MACOS_FALLBACK_PATHS: List[str] = [
    "/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex",
    "/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex",
    "/Applications/ChatGPT.app/Contents/Resources/codex",
    "/Applications/Codex.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex",
    "/Applications/Codex.app/Contents/Resources/codex-cli/bin/codex",
    "/Applications/Codex.app/Contents/Resources/codex",
    "~/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex",
    "~/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex",
    "~/Applications/ChatGPT.app/Contents/Resources/codex",
    "~/Applications/Codex.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex",
    "~/Applications/Codex.app/Contents/Resources/codex-cli/bin/codex",
    "~/Applications/Codex.app/Contents/Resources/codex",
]

AGY_MACOS_FALLBACK_PATHS: List[str] = [
    "/Applications/Antigravity.app/Contents/Resources/app/bin/agy",
    "/Applications/Antigravity.app/Contents/Resources/app/bin/antigravity",
    "~/Applications/Antigravity.app/Contents/Resources/app/bin/agy",
]

CLAUDE_MACOS_FALLBACK_PATHS: List[str] = [
    "~/.local/bin/claude",
    "/opt/homebrew/bin/claude",
    "/usr/local/bin/claude",
    "~/.npm-global/bin/claude",
]

OLLAMA_MACOS_FALLBACK_PATHS: List[str] = [
    "/opt/homebrew/bin/ollama",
    "/usr/local/bin/ollama",
    "/Applications/Ollama.app/Contents/Resources/ollama",
]

DRIVER_FALLBACK_PATHS: Dict[str, List[str]] = {
    "agy": AGY_MACOS_FALLBACK_PATHS,
    "grok": [],
    "codex": CODEX_MACOS_FALLBACK_PATHS,
    "claude": CLAUDE_MACOS_FALLBACK_PATHS,
    "ollama": OLLAMA_MACOS_FALLBACK_PATHS,
}

_refresh_declarative_driver_tables()

PROBE_CACHE_FILE = os.path.join(
    os.path.expanduser(os.environ.get("AI_ROUNDTABLE_HOME") or "~/.ai-roundtable"), "probe_cache.json"
)
_DISK_PROBE_CACHE: Optional[Dict[str, dict]] = None

_IGNORED_PROJECT_DIRS = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "dist",
    "build",
    ".next",
    ".nuxt",
    ".idea",
    ".vscode",
    "target",
    "Pods",
    ".pytest_cache",
    ".mypy_cache",
    "coverage",
}

_BINARY_FILE_EXTS = {
    ".pyc",
    ".pyo",
    ".o",
    ".so",
    ".dylib",
    ".dll",
    ".exe",
    ".bin",
    ".icns",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".ico",
    ".pdf",
    ".zip",
    ".tar",
    ".gz",
    ".woff",
    ".woff2",
    ".ttf",
    ".otf",
    ".mp3",
    ".mp4",
    ".mov",
    ".sqlite",
    ".db",
}

_AT_FILE_REF_RE = re.compile(
    r"(?<![A-Za-z0-9_.+-])@([A-Za-z0-9_\u4e00-\u9fa5./-]+\.[A-Za-z0-9]{1,10})(?::[Ll]?(\d+)(?:-[Ll]?(\d+))?)?"
)

FULL_FILE_LINE_THRESHOLD = 1200
MAX_SLICE_LINES = 1200
MAX_ROUND_SOURCE_CHARS = 120000

_WORKSPACE_TREE_CACHE: Dict[str, Tuple[float, str]] = {}
_FILE_SKELETON_CACHE: Dict[str, Tuple[int, int, str]] = {}
_CODE_TOPIC_HINT_RE = re.compile(
    r"(@[A-Za-z0-9_./-]+\.[A-Za-z0-9]{1,10}|代码|源码|函数|接口|报错|异常|bug|修复|重构|模块|文件|目录|脚本|性能|延迟|样式|前端|后端|测试|编译|打包|git|cli|api|css|html|js|py)",
    re.IGNORECASE,
)


def get_persona_spec(persona_key: str, fallback_agent_id: str = "carbon") -> dict:
    if persona_key in PERSONA_PRESETS:
        return PERSONA_PRESETS[persona_key]
    default_key = DEFAULT_SEAT_PERSONAS.get(fallback_agent_id, "planner")
    return PERSONA_PRESETS[default_key]


def _load_disk_probe_cache() -> Dict[str, dict]:
    global _DISK_PROBE_CACHE
    if _DISK_PROBE_CACHE is not None:
        return _DISK_PROBE_CACHE
    try:
        if os.path.isfile(PROBE_CACHE_FILE):
            with open(PROBE_CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                _DISK_PROBE_CACHE = data
                return _DISK_PROBE_CACHE
    except Exception:
        pass
    _DISK_PROBE_CACHE = {}
    return _DISK_PROBE_CACHE


def _save_disk_probe_cache() -> None:
    if _DISK_PROBE_CACHE is None:
        return
    try:
        os.makedirs(os.path.dirname(PROBE_CACHE_FILE), exist_ok=True)
        tmp_file = f"{PROBE_CACHE_FILE}.tmp"
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(_DISK_PROBE_CACHE, f, ensure_ascii=False)
        os.replace(tmp_file, PROBE_CACHE_FILE)
    except Exception:
        pass


def _strip_control_plane_secrets(env: Dict[str, str]) -> Dict[str, str]:
    for key in list(env.keys()):
        if key in (
            "AI_ROUNDTABLE_BOOT_TOKEN",
            "AI_ROUNDTABLE_BOOTSTRAP_CODE",
            "AI_ROUNDTABLE_BOOT_ID",
        ) or key.upper().startswith("AI_ROUNDTABLE_BOOT_"):
            env.pop(key, None)
    return env


def build_host_env() -> Dict[str, str]:
    """构建宿主机环境变量（缓存登录 Shell PATH，实时感知代理变更，并剥离控制面敏感凭据防子进程泄露）。"""
    global _CACHED_LOGIN_PATH, _CACHED_HOST_ENV
    if _CACHED_HOST_ENV is not None:
        fresh = os.environ.copy()
        fresh["PATH"] = _CACHED_HOST_ENV["PATH"]
        return _strip_control_plane_secrets(fresh)

    env = os.environ.copy()
    home = os.path.expanduser("~")

    if os.name == "nt":
        extra = [os.path.join(home, ".local", "bin"), os.path.join(home, ".grok", "bin"),
                 os.path.join(env.get("APPDATA", home), "npm")]
        env["PATH"] = os.pathsep.join([env.get("PATH", ""), *(p for p in extra if os.path.isdir(p))])
        _strip_control_plane_secrets(env)
        _CACHED_HOST_ENV = env.copy()
        return env

    if _CACHED_LOGIN_PATH is None:
        if env.get("AI_ROUNDTABLE_LOGIN_SHELL") == "1":
            _CACHED_LOGIN_PATH = env.get("PATH", "")
        else:
            zsh_bin = shutil.which("zsh") or "zsh"
            try:
                out = subprocess.check_output(
                    [zsh_bin, "-lic", 'printf "%s" "$PATH"'],
                    stdin=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=2.0,
                )
                _CACHED_LOGIN_PATH = out.decode("utf-8", errors="ignore").strip()
            except Exception:
                _CACHED_LOGIN_PATH = ""

    homebrew_opt = os.path.join(os.sep, "opt", "homebrew")
    usr_local_bin = os.path.join(os.sep, "usr", "local", "bin")
    candidate_dirs: List[str] = [
        os.path.join(homebrew_opt, "bin"),
        os.path.join(homebrew_opt, "sbin"),
        usr_local_bin,
        os.path.join(home, ".local", "bin"),
        os.path.join(home, ".grok", "bin"),
        os.path.join(home, ".bun", "bin"),
        os.path.join(home, ".volta", "bin"),
        os.path.join(home, "Library", "pnpm"),
        os.path.join(home, ".npm-global", "bin"),
        os.path.join(home, ".cargo", "bin"),
        os.path.join(home, "bin"),
        "/Applications/Antigravity.app/Contents/Resources/app/bin",
        "/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS",
        "/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin",
        "/Applications/ChatGPT.app/Contents/Resources",
        "/Applications/Codex.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS",
        "/Applications/Codex.app/Contents/Resources/codex-cli/bin",
        "/Applications/Codex.app/Contents/Resources",
        os.path.join(home, "Applications", "ChatGPT.app", "Contents", "Resources", "codex-cli", "CodexCLI.app", "Contents", "MacOS"),
        os.path.join(home, "Applications", "ChatGPT.app", "Contents", "Resources", "codex-cli", "bin"),
        os.path.join(home, "Applications", "Codex.app", "Contents", "Resources", "codex-cli", "CodexCLI.app", "Contents", "MacOS"),
        os.path.join(home, "Applications", "Codex.app", "Contents", "Resources", "codex-cli", "bin"),
    ]
    nvm_bins = sorted(glob.glob(os.path.join(home, ".nvm", "versions", "node", "*", "bin")), reverse=True)
    candidate_dirs.extend(nvm_bins)

    merged: List[str] = []
    for raw in [env.get("PATH", ""), _CACHED_LOGIN_PATH or ""]:
        for p in raw.split(os.pathsep):
            p = p.strip()
            if p and p not in merged:
                merged.append(p)

    for d in candidate_dirs:
        if d not in merged and os.path.isdir(d):
            merged.append(d)

    env["PATH"] = os.pathsep.join(merged)
    _strip_control_plane_secrets(env)
    _CACHED_HOST_ENV = {"PATH": env["PATH"]}
    return env.copy()


def _expand_app_bundle_binary(path_str: str) -> Optional[str]:
    if not path_str.endswith(".app") or not os.path.isdir(path_str):
        return None
    inner_rel_candidates = [
        "Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex",
        "Contents/Resources/codex-cli/bin/codex",
        "Contents/MacOS/codex",
        "Contents/Resources/codex",
        "Contents/Resources/app/bin/agy",
        "Contents/Resources/app/bin/antigravity",
    ]
    for rel in inner_rel_candidates:
        full = os.path.join(path_str, rel)
        if os.path.isfile(full) and os.access(full, os.X_OK):
            return full
    return None


def resolve_binary(
    candidates: List[str],
    custom_path: str = "",
    fallback_paths: Optional[List[str]] = None,
) -> Optional[str]:
    env = build_host_env()
    if custom_path.strip():
        expanded = os.path.expanduser(custom_path.strip().strip('"').strip("'"))
        bundle_bin = _expand_app_bundle_binary(expanded)
        if bundle_bin:
            return bundle_bin
        if os.path.isfile(expanded) and os.access(expanded, os.X_OK):
            return expanded
        found_custom = shutil.which(expanded, path=env.get("PATH"))
        if found_custom:
            return found_custom

    for name in candidates:
        if os.path.isabs(name) or name.startswith("~"):
            exp = os.path.expanduser(name)
            if os.path.isfile(exp) and os.access(exp, os.X_OK):
                return exp
        found = shutil.which(name, path=env.get("PATH"))
        if found:
            return found

    for fb in fallback_paths or []:
        exp_fb = os.path.expanduser(fb)
        if os.path.isfile(exp_fb) and os.access(exp_fb, os.X_OK):
            return exp_fb

    return None


def detect_driver_binary(driver_key: str, custom_path: str = "") -> Optional[str]:
    spec = DRIVER_SPECS.get(driver_key)
    if not spec:
        return None
    return resolve_binary(
        spec["binary_candidates"],
        custom_path=custom_path,
        fallback_paths=DRIVER_FALLBACK_PATHS.get(driver_key, []),
    )


def _binary_stat_signature(binary_path: str) -> str:
    try:
        st = os.stat(binary_path)
        return f"{st.st_mtime_ns}:{st.st_size}"
    except Exception:
        return ""


def _run_probe_flag(binary_path: str, flag: str, env: Dict[str, str]) -> str:
    try:
        argv = [binary_path, flag]
        if os.name == "nt":
            from .drivers.windows_support import native_command
            argv = native_command(argv, env)
        out = subprocess.run(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            timeout=6.0,
        )
        return out.stdout.decode("utf-8", errors="replace")
    except Exception as exc:
        return f"__ERR__:{exc}"


def probe_cli_metadata(binary_path: str, persist: bool = True) -> Dict[str, str]:
    """并发探测 --version 与 --help，并结合二进制 mtime 落盘缓存，热启动耗时 < 0.5ms。"""
    sig = _binary_stat_signature(binary_path)
    disk_cache = _load_disk_probe_cache()
    cached = disk_cache.get(binary_path)
    if cached and sig and cached.get("sig") == sig:
        return {"version": cached.get("version", ""), "help": cached.get("help", "")}

    env = build_host_env()
    with ThreadPoolExecutor(max_workers=2) as pool:
        fut_v = pool.submit(_run_probe_flag, binary_path, "--version", env)
        fut_h = pool.submit(_run_probe_flag, binary_path, "--help", env)
        raw_v = fut_v.result()
        raw_h = fut_h.result()

    if raw_v.startswith("__ERR__:"):
        version_str = f"探测异常: {raw_v[8:]}"
    else:
        lines = [ln.strip() for ln in raw_v.splitlines() if ln.strip()]
        version_str = lines[0][:80] if lines else ""

    help_str = "" if raw_h.startswith("__ERR__:") else raw_h
    meta = {"version": version_str, "help": help_str}
    if sig:
        disk_cache[binary_path] = {"sig": sig, "version": version_str, "help": help_str}
        if persist:
            _save_disk_probe_cache()
    return meta


def is_real_bound_workspace(workspace_dir: str) -> Tuple[bool, str]:
    """判断目录是否为真实绑定的用户项目工作区（排除默认空沙箱与系统主目录）。"""
    if not workspace_dir or not os.path.isdir(workspace_dir):
        return False, ""
    real_ws = os.path.realpath(os.path.expanduser(workspace_dir))
    default_empty = os.path.realpath(os.path.join(os.path.expanduser(os.environ.get("AI_ROUNDTABLE_HOME") or "~/.ai-roundtable"), "workspace"))
    default_root = os.path.realpath(os.path.expanduser(os.environ.get("AI_ROUNDTABLE_HOME") or "~/.ai-roundtable"))
    home_real = os.path.realpath(os.path.expanduser("~"))
    if real_ws in (default_empty, default_root, home_real):
        return False, real_ws
    return True, real_ws


def is_git_workspace(workspace_dir: str) -> bool:
    """快速判断工作区是否处于 Git 版本控制下（供前端准确展示回滚能力与风险提示）。"""
    bound, real_ws = is_real_bound_workspace(workspace_dir)
    if not bound:
        return False
    cur = real_ws
    for _ in range(6):
        if os.path.exists(os.path.join(cur, ".git")):
            return True
        parent = os.path.dirname(cur)
        if not parent or parent == cur:
            break
        cur = parent
    return False


def list_workspace_files(workspace_dir: str, query: str = "", limit: int = 200) -> dict:
    """枚举并检索绑定项目内的可读源码与配置文件列表，支撑前端 @文件路径 实时联想与存在性校验。"""
    bound, real_ws = is_real_bound_workspace(workspace_dir)
    if not bound:
        return {
            "ok": True,
            "bound": False,
            "is_git": False,
            "workspace_dir": real_ws,
            "files": [],
            "total": 0,
        }

    q_low = (query or "").strip().lower().lstrip("@")
    cap = max(1, min(int(limit or 200), 400))
    all_items = scan_workspace_index_cached(
        real_ws,
        _IGNORED_PROJECT_DIRS,
        _BINARY_FILE_EXTS,
        max_depth=5,
        max_scan=2500,
    )

    total_count = len(all_items)
    if q_low:
        scored: List[Tuple[int, str, dict]] = []
        for item in all_items:
            p_low = item["path"].lower()
            base_low = os.path.basename(p_low)
            if base_low.startswith(q_low):
                scored.append((0, p_low, item))
            elif q_low in base_low:
                scored.append((1, p_low, item))
            elif q_low in p_low:
                scored.append((2, p_low, item))
        scored.sort(key=lambda x: (x[0], len(x[1]), x[1]))
        matched = [x[2] for x in scored[:cap]]
    else:
        matched = all_items[:cap]

    return {
        "ok": True,
        "bound": True,
        "is_git": is_git_workspace(real_ws),
        "workspace_dir": real_ws,
        "files": matched,
        "total": total_count,
    }


def build_file_outline_skeleton(rel_path: str, all_lines: List[str]) -> str:
    """
    针对超过 1200 行且未显式指定行号区间的长源码文件，提取「文件头部注释 + 类/函数/关键常量行号索引骨架」，
    避免超大文件盲目全量注入撑爆上下文，并提示模型按行号区间精确查看。
    """
    total_lines = len(all_lines)
    ext = os.path.splitext(rel_path)[1].lower()

    # 1. 提取头部注释与说明（前 36 行内的注释/模块说明/核心导入概览）
    header_lines: List[str] = []
    header_chars = 0
    for idx, raw_ln in enumerate(all_lines[:36], start=1):
        s_ln = raw_ln.rstrip()
        if not s_ln and len(header_lines) >= 4:
            continue
        clipped = s_ln[:140] + ("…" if len(s_ln) > 140 else "")
        entry = f"L{idx}: {clipped}"
        if header_chars + len(entry) > 1400:
            break
        header_lines.append(entry)
        header_chars += len(entry) + 1

    # 2. 提取类 / 函数 / 关键常量 / 样式与结构锚点行号大纲
    outline_items: List[str] = []

    if ext == ".py":
        parsed_ok = False
        try:
            tree = ast.parse("\n".join(all_lines))
            parsed_ok = True
            for node in tree.body:
                if isinstance(node, ast.Assign):
                    for tgt in node.targets:
                        if isinstance(tgt, ast.Name) and (tgt.id.isupper() or tgt.id.startswith("DEFAULT_")):
                            end_ln = getattr(node, "end_lineno", node.lineno) or node.lineno
                            outline_items.append(f"  L{node.lineno}-L{end_ln}: const {tgt.id}")
                elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                    tid = node.target.id
                    if tid.isupper() or tid.startswith("DEFAULT_"):
                        end_ln = getattr(node, "end_lineno", node.lineno) or node.lineno
                        outline_items.append(f"  L{node.lineno}-L{end_ln}: const {tid}")
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
                    args = [a.arg for a in node.args.args[:5]]
                    if len(node.args.args) > 5:
                        args.append("...")
                    end_ln = getattr(node, "end_lineno", node.lineno) or node.lineno
                    outline_items.append(f"  L{node.lineno}-L{end_ln}: {prefix} {node.name}({', '.join(args)})")
                elif isinstance(node, ast.ClassDef):
                    end_ln = getattr(node, "end_lineno", node.lineno) or node.lineno
                    outline_items.append(f"  L{node.lineno}-L{end_ln}: class {node.name}")
                    for sub in node.body:
                        if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            m_prefix = "async def" if isinstance(sub, ast.AsyncFunctionDef) else "def"
                            m_end = getattr(sub, "end_lineno", sub.lineno) or sub.lineno
                            outline_items.append(f"    L{sub.lineno}-L{m_end}: {m_prefix} {sub.name}(...)")
        except Exception:
            parsed_ok = False

        if not parsed_ok:
            py_re = re.compile(r"^(\s*)(class\s+\w+|(?:async\s+)?def\s+\w+|[A-Z][A-Z0-9_]{2,}\s*=)")
            for idx, raw_ln in enumerate(all_lines, start=1):
                m = py_re.match(raw_ln)
                if m:
                    indent = "    " if len(m.group(1)) > 0 else "  "
                    outline_items.append(f"{indent}L{idx}: {raw_ln.strip()[:100]}")

    elif ext in (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"):
        js_re = re.compile(
            r"^\s*(?:"
            r"(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+([A-Za-z0-9_$]+)"
            r"|(?:export\s+)?class\s+([A-Za-z0-9_$]+)"
            r"|(?:export\s+)?(?:const|let|var)\s+([A-Za-z0-9_$]+)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z0-9_$]+)\s*=>"
            r"|(?:export\s+)?const\s+([A-Z][A-Z0-9_]{2,})\s*="
            r"|/\*\s*={2,}\s*(.+?)\s*={2,}\s*\*/"
            r"|//\s*[-=]{3,}\s*(.+)"
            r")"
        )
        for idx, raw_ln in enumerate(all_lines, start=1):
            s = raw_ln.strip()
            if not s:
                continue
            if js_re.match(raw_ln) or "addEventListener(" in s:
                outline_items.append(f"  L{idx}: {s[:110]}")

    elif ext in (".css", ".scss", ".less"):
        css_re = re.compile(
            r"^(?:/\*\s*[-=]*\s*([^*]+?)\s*[-=]*\s*\*/|(@media[^{]+|@keyframes\s+[^{]+|:root|[.#][A-Za-z0-9_-]+(?:\s+[.#][A-Za-z0-9_-]+)?)\s*\{)"
        )
        for idx, raw_ln in enumerate(all_lines, start=1):
            s = raw_ln.strip()
            m = css_re.match(s)
            if m:
                outline_items.append(f"  L{idx}: {s[:100]}")

    elif ext in (".html", ".htm", ".vue", ".svelte"):
        html_re = re.compile(
            r'^\s*(?:<!--\s*(.+?)\s*-->|<(header|aside|main|section|nav|footer|dialog|form|details)\b[^>]*>|<\w+[^>]*\bid="[^"]+"[^>]*>)'
        )
        for idx, raw_ln in enumerate(all_lines, start=1):
            s = raw_ln.strip()
            if html_re.search(raw_ln):
                outline_items.append(f"  L{idx}: {s[:110]}")

    else:
        gen_re = re.compile(
            r"^\s*(?:#{1,4}\s+.+|(?:pub\s+)?(?:async\s+)?(?:fn|func|def|class|struct|interface|enum|impl)\s+[A-Za-z0-9_]+|[A-Za-z0-9_]+\(\)\s*\{)"
        )
        for idx, raw_ln in enumerate(all_lines, start=1):
            s = raw_ln.strip()
            if gen_re.match(raw_ln):
                outline_items.append(f"  L{idx}: {s[:110]}")

    if len(outline_items) > 95:
        head_part = outline_items[:75]
        tail_part = outline_items[-18:]
        omitted = len(outline_items) - len(head_part) - len(tail_part)
        outline_items = head_part + [f"  ...（中间省略 {omitted} 个次级符号锚点，可按行号区间只读）..."] + tail_part

    header_txt = "\n".join(header_lines) if header_lines else "（无文件头部注释）"
    outline_txt = "\n".join(outline_items) if outline_items else f"  L1-L{total_lines}: （未检测到显式类/函数定义，可按行号区间精确查看）"
    skeleton = (
        f"[文件头部注释 (L1-L{min(total_lines, 36)})]\n{header_txt}\n\n"
        f"[类/函数/关键常量行号索引骨架 (共 {total_lines} 行)]\n{outline_txt}\n\n"
        f"[按行号区间精确查看指引] 该文件共 {total_lines} 行（超过 {FULL_FILE_LINE_THRESHOLD} 行且未指定行号区间，已转为索引骨架）；"
        f"如需核对某段实现细节，请按上述 L起始-L结束 行号区间精确只读（或在追问中使用 @{rel_path}:起始行-结束行）。"
    )
    return skeleton[:8000]


def validate_referenced_files_snapshot(
    workspace_dir: str,
    reference_texts: str,
) -> List[str]:
    """
    原子校验待发文本中的显式 @path/to/file.ext[:start-end] 引用快照可读性（Section 1.2）：
    - 若当前未绑定工作区且文本中显式包含带目录层级的 @path/file.ext，返回未绑仓阻断错误；
    - 若已绑定工作区但目标文件不存在、路径越界、不可读或起始行超出文件总行数，返回逐项错误列表；
    - 忽略邮箱地址（已由 _AT_FILE_REF_RE 负向前瞻过滤）与无文件后缀的 @席位名。
    """
    if not reference_texts:
        return []
    matches = list(_AT_FILE_REF_RE.finditer(reference_texts))
    if not matches:
        return []
    bound, real_ws = is_real_bound_workspace(workspace_dir)
    errors: List[str] = []
    seen_refs: Set[str] = set()
    for m in matches:
        rel_raw = m.group(1).lstrip("/")
        start_s, end_s = m.group(2), m.group(3)
        raw_tok = f"@{rel_raw}" + (f":{start_s}" + (f"-{end_s}" if end_s else "") if start_s else "")
        if raw_tok in seen_refs:
            continue
        seen_refs.add(raw_tok)
        if not bound:
            if "/" in rel_raw or start_s:
                errors.append(f"{raw_tok}（当前为纯研讨未绑目录状态，请先在顶栏绑定项目工作区或移除该文件引用）")
            continue
        cand_path = os.path.realpath(os.path.join(real_ws, rel_raw))
        if not cand_path.startswith(real_ws + os.sep):
            errors.append(f"{raw_tok}（引用路径超出项目工作区安全边界）")
            continue
        if not os.path.isfile(cand_path):
            errors.append(f"{raw_tok}（工作区内未找到该文件，请核对相对路径）")
            continue
        try:
            with open(cand_path, "r", encoding="utf-8", errors="replace") as rf:
                all_lines = rf.read().splitlines()
            total_lines = len(all_lines)
            if start_s:
                s_ln = int(start_s)
                e_ln = int(end_s) if end_s else s_ln
                lo_ln = min(s_ln, e_ln)
                if total_lines == 0 or lo_ln > total_lines:
                    errors.append(f"{raw_tok}（文件共 {total_lines} 行，起始行 L{lo_ln} 超出范围）")
        except Exception as exc:
            errors.append(f"{raw_tok}（读取快照失败：{exc}）")
    return errors


def extract_referenced_files_context(
    workspace_dir: str,
    reference_texts: str,
    max_files: int = 12,
    max_lines_per_file: int = MAX_SLICE_LINES,
    max_chars_per_file: int = MAX_ROUND_SOURCE_CHARS,
    max_total_chars: int = MAX_ROUND_SOURCE_CHARS,
    exclude_refs: Optional[Set[str]] = None,
) -> Tuple[str, Set[str]]:
    """
    解析文本中的 @path/to/file.ext 或 @path/to/file.ext:start-end 引用并构建高信噪比源码附件：
    - 当引用文件在 1200 行以内或显式指定了 @path:start-end 行号区间时，完整注入带行号的真实源码；
    - 仅当单文件超过 1200 行且未指定行号范围时，注入「文件头部注释 + 类/函数/关键常量行号索引骨架」并提示按行号区间精确查看；
    - 单轮源码附件总注入上限受 max_total_chars（默认 120,000 字符）保护。
    """
    bound, real_ws = is_real_bound_workspace(workspace_dir)
    if not bound or not reference_texts:
        return "", set()

    eff_total_cap = max(8000, int(max_total_chars or MAX_ROUND_SOURCE_CHARS))
    eff_file_cap = max(8000, min(int(max_chars_per_file or eff_total_cap), eff_total_cap))
    skip_set = exclude_refs or set()
    blocks: List[str] = []
    loaded_keys: Set[str] = set()
    used_chars = 0

    for m in _AT_FILE_REF_RE.finditer(reference_texts):
        rel_raw = m.group(1).lstrip("/")
        start_s, end_s = m.group(2), m.group(3)
        ref_key = f"{rel_raw}:{start_s or ''}-{end_s or ''}"
        if ref_key in loaded_keys or ref_key in skip_set:
            continue
        cand_path = os.path.realpath(os.path.join(real_ws, rel_raw))
        if not (cand_path.startswith(real_ws + os.sep) and os.path.isfile(cand_path)):
            continue

        try:
            with open(cand_path, "r", encoding="utf-8", errors="replace") as rf:
                all_lines = rf.read().splitlines()
            total_lines = len(all_lines)
            if total_lines == 0:
                continue

            ext = os.path.splitext(rel_raw)[1].lstrip(".")
            if start_s:
                s_ln = max(1, int(start_s))
                if end_s:
                    e_ln = int(end_s)
                    if e_ln < s_ln:
                        s_ln, e_ln = e_ln, s_ln
                    e_ln = min(total_lines, e_ln)
                else:
                    e_ln = min(total_lines, s_ln + max_lines_per_file - 1)
                s_ln = min(s_ln, total_lines)
                sliced = [f"L{ln_no}: {all_lines[ln_no - 1]}" for ln_no in range(s_ln, e_ln + 1)]
                body_txt = "\n".join(sliced)
                if len(body_txt) > eff_file_cap:
                    body_txt = body_txt[:eff_file_cap] + "\n... [片段超单轮预算上限已截断，请缩小行号区间]"
                range_label = f"行号切片 L{s_ln}–L{e_ln} / 共 {total_lines} 行"
                block = f"【引用源码片段 @{rel_raw}（{range_label}）】：\n```{ext}\n{body_txt}\n```"
            elif total_lines <= FULL_FILE_LINE_THRESHOLD:
                numbered_lines = [f"L{ln_no}: {ln_txt}" for ln_no, ln_txt in enumerate(all_lines, start=1)]
                body_txt = "\n".join(numbered_lines)
                if len(body_txt) > eff_file_cap:
                    body_txt = body_txt[:eff_file_cap] + "\n... [单文件字符超预算已截断]"
                range_label = f"完整源码 L1–L{total_lines}（共 {total_lines} 行）"
                block = f"【引用源码 @{rel_raw}（{range_label}）】：\n```{ext}\n{body_txt}\n```"
            else:
                try:
                    st_f = os.stat(cand_path)
                    sk_cached = _FILE_SKELETON_CACHE.get(cand_path)
                    if sk_cached and sk_cached[0] == st_f.st_mtime_ns and sk_cached[1] == st_f.st_size:
                        skeleton_txt = sk_cached[2]
                    else:
                        skeleton_txt = build_file_outline_skeleton(rel_raw, all_lines)
                        _FILE_SKELETON_CACHE[cand_path] = (st_f.st_mtime_ns, st_f.st_size, skeleton_txt)
                except Exception:
                    skeleton_txt = build_file_outline_skeleton(rel_raw, all_lines)
                range_label = f"索引骨架（全文件共 {total_lines} 行 > {FULL_FILE_LINE_THRESHOLD} 行阈值）"
                block = f"【引用文件大纲 @{rel_raw}（{range_label}）】：\n```text\n{skeleton_txt}\n```"

            if not block.strip():
                continue

            remaining_budget = eff_total_cap - used_chars
            if remaining_budget <= 320:
                blocks.append(f"【提示：已达单轮源码注入 {eff_total_cap:,} 字符总预算上限，其余引用文件请按行号区间精确只读】")
                break
            if len(block) > remaining_budget:
                clipped_block = block[: max(260, remaining_budget - 110)].rstrip()
                if clipped_block.count("```") % 2 == 1:
                    clipped_block += "\n```"
                clipped_block += f"\n... [已达单轮源码注入 {eff_total_cap:,} 字符上限，后续请按行号区间精确查看]"
                blocks.append(clipped_block)
                loaded_keys.add(ref_key)
                used_chars = eff_total_cap
                break

            blocks.append(block)
            loaded_keys.add(ref_key)
            used_chars += len(block) + 2
            if len(blocks) >= max_files:
                break
        except Exception:
            continue

    if not blocks:
        return "", set()

    anti_reread_notice = (
        "【源码上下文使用规则：已提供结构大纲或片段的文件请勿全量重复读取；"
        "若确需核对大纲中某段实现细节，仅限按大纲标注的行号区间精准只读一次】"
    )
    return anti_reread_notice + "\n\n" + "\n\n".join(blocks), loaded_keys


def build_workspace_context_snapshot(
    workspace_dir: str,
    reference_texts: str = "",
    prebuilt_ref_block: Optional[str] = None,
    max_ref_chars: int = MAX_ROUND_SOURCE_CHARS,
    lightweight_hint_only: bool = False,
) -> str:
    """
    构建深度本地项目快照（支持 20s 目录树内存缓存 + 非代码议题轻量摘要模式）：
    兼顾亚毫秒级读取速度与全栈代码架构全景感知，避免无关非代码议题注入冗长目录树拖慢首字响应。
    """
    bound, real_ws = is_real_bound_workspace(workspace_dir)
    if not bound:
        return ""

    if prebuilt_ref_block is not None:
        ref_block = prebuilt_ref_block
    else:
        ref_block, _ = extract_referenced_files_context(
            real_ws,
            reference_texts,
            max_total_chars=max_ref_chars,
        )

    if lightweight_hint_only and not ref_block:
        return (
            f"【当前绑定本地项目】：{os.path.basename(real_ws)} ({real_ws})\n"
            "（本议题未显式引用源码文件；如分析无需依赖具体代码实现，请直接作答，切勿盲目遍历工作区文件。）"
        )

    now_mono = time.monotonic()
    cached_base = _WORKSPACE_TREE_CACHE.get(real_ws)
    if cached_base and (now_mono - cached_base[0]) < 20.0:
        base_text = cached_base[1]
        if not base_text:
            return ""
        return f"{base_text}\n\n{ref_block}" if ref_block else base_text

    try:
        top_entries = sorted(os.listdir(real_ws))
    except Exception:
        return ""

    visible_top = [
        e
        for e in top_entries
        if not e.startswith(".") and e not in _IGNORED_PROJECT_DIRS and not e.endswith(".app")
    ]
    if not visible_top:
        return ""

    tree_lines: List[str] = []
    for name in visible_top[:80]:
        full = os.path.join(real_ws, name)
        if os.path.isdir(full):
            tree_lines.append(f"  - {name}/")
            try:
                sub_entries = [
                    s
                    for s in sorted(os.listdir(full))
                    if not s.startswith(".") and s not in _IGNORED_PROJECT_DIRS and not s.endswith(".app")
                ]
                for sub_name in sub_entries[:35]:
                    sub_full = os.path.join(full, sub_name)
                    if os.path.isdir(sub_full):
                        try:
                            leaf_entries = [
                                lf
                                for lf in sorted(os.listdir(sub_full))
                                if not lf.startswith(".") and lf not in _IGNORED_PROJECT_DIRS
                            ]
                            leaf_preview = ", ".join(leaf_entries[:16])
                            if len(leaf_entries) > 16:
                                leaf_preview += f" ...(+{len(leaf_entries) - 16})"
                            tree_lines.append(
                                f"    - {sub_name}/ ({leaf_preview})" if leaf_preview else f"    - {sub_name}/"
                            )
                        except Exception:
                            tree_lines.append(f"    - {sub_name}/")
                    else:
                        tree_lines.append(f"    - {sub_name}")
                if len(sub_entries) > 35:
                    tree_lines.append(f"    - ... (其余 {len(sub_entries) - 35} 项)")
            except Exception:
                pass
        else:
            tree_lines.append(f"  - {name}")

    manifest_snippets: List[str] = []
    manifest_candidates = (
        "package.json",
        "pyproject.toml",
        "Cargo.toml",
        "go.mod",
        "README.md",
        "CLAUDE.md",
        "AGENTS.md",
        "Makefile",
        "requirements.txt",
    )
    for mf in manifest_candidates:
        mf_path = os.path.join(real_ws, mf)
        if os.path.isfile(mf_path):
            try:
                with open(mf_path, "r", encoding="utf-8", errors="replace") as f:
                    head_lines = [ln.rstrip() for _, ln in zip(range(90), f)]
                snippet = "\n".join(head_lines).strip()[:3600]
                if snippet:
                    manifest_snippets.append(f"[{mf} 关键内容]:\n{snippet}")
                if len(manifest_snippets) >= 4:
                    break
            except Exception:
                pass

    base_parts = [
        f"【当前绑定本地项目】：{os.path.basename(real_ws)} ({real_ws})",
        "【项目目录结构快照（支持用 @相对路径 或 @相对路径:起始行-结束行 引用源码）】：\n" + "\n".join(tree_lines),
    ]
    if manifest_snippets:
        base_parts.append("\n\n".join(manifest_snippets))
    base_text = "\n\n".join(base_parts)
    _WORKSPACE_TREE_CACHE[real_ws] = (now_mono, base_text)
    return f"{base_text}\n\n{ref_block}" if ref_block else base_text


def _safe_terminate_proc(proc: Optional[asyncio.subprocess.Process]) -> None:
    if proc and proc.returncode is None:
        try:
            if hasattr(os, "killpg") and proc.pid:
                os.killpg(proc.pid, signal.SIGKILL)
                return
        except Exception:
            pass
        try:
            proc.kill()
        except Exception:
            pass


async def _read_stderr_tail(reader: asyncio.StreamReader) -> str:
    tail = b""
    while True:
        chunk = await reader.read(16384)
        if not chunk:
            return tail.decode("utf-8", errors="replace").strip()
        tail = (tail + chunk)[-65536:]


def resolve_effective_model_for_driver(
    driver_key: str,
    model: str,
    is_shared_fb: bool = False,
) -> str:
    """
    解析指定底层 CLI 驱动下的实际生效模型名：
    - 若处于自动单 CLI 借用回退模式，或模型名属于其他驱动专属默认模型（如将 Grok/Astra 席位改绑到 agy 但残留 grok-4.7 / gpt-6-astra），
      自动映射为当前驱动的默认主力模型；
    - 用户针对当前驱动手动填写的自定义模型名保持原样透传。
    """
    drv = driver_key if driver_key in DRIVER_SPECS else "agy"
    spec = DRIVER_SPECS[drv]
    m = (model or "").strip()
    if is_shared_fb:
        owner = _DRIVER_EXCLUSIVE_DEFAULT_MODELS.get(m.lower())
        if not m or (owner and owner != drv):
            return spec["default_model"]
        return m
    if not m:
        return spec["default_model"]
    owner = _DRIVER_EXCLUSIVE_DEFAULT_MODELS.get(m.lower())
    if owner and owner != drv:
        return spec["default_model"]
    return m


def get_model_effort_spec(driver_key: str, model: str = "", help_text: str = "") -> dict:
    """按「CLI 驱动 + 模型名」返回合法推理档位列表、默认档位、最高合法档位与是否支持 --effort。"""
    drv = driver_key if driver_key in MODEL_EFFORT_CAPABILITIES else "agy"
    drv_table = MODEL_EFFORT_CAPABILITIES[drv]
    eff_model = resolve_effective_model_for_driver(drv, model, is_shared_fb=False)
    m_low = eff_model.strip().lower()

    matched_spec: Optional[dict] = None
    if m_low in drv_table:
        matched_spec = drv_table[m_low]
    elif drv == "agy" and "orchestrator" in m_low:
        matched_spec = drv_table["orchestrator (carbon)"]
    elif drv == "agy" and "hydrogen" in m_low:
        matched_spec = drv_table["gemini-4-hydrogen"]
    else:
        for pat, item in drv_table.items():
            if pat == "*":
                continue
            if pat.endswith("*"):
                prefix = pat[:-1]
                if m_low.startswith(prefix):
                    matched_spec = item
                    break
        if matched_spec is None and drv == "agy":
            if "carbon" in m_low or "argon" in m_low or "gemini" in m_low:
                matched_spec = drv_table["gemini-*"]
        if matched_spec is None:
            matched_spec = drv_table["*"]

    if matched_spec.get("supports_effort") is False:
        return {
            "driver": drv,
            "model": eff_model,
            "supports_effort": False,
            "allowed": [],
            "default": "",
            "max": "",
        }

    allowed = [e for e in ORDERED_EFFORT_LEVELS if e in matched_spec["allowed"]]
    if drv == "agy" and help_text and "--effort" in help_text:
        filtered = [
            e for e in allowed if (e in ("minimal", "low", "medium", "high") or e in help_text)
        ]
        if filtered:
            allowed = filtered

    if not allowed:
        allowed = ["low", "medium", "high"]
    default_eff = matched_spec.get("default", allowed[-1])
    if default_eff not in allowed:
        default_eff = allowed[-1]
    return {
        "driver": drv,
        "model": eff_model,
        "supports_effort": True,
        "allowed": allowed,
        "default": default_eff,
        "max": allowed[-1],
    }


def normalize_model_effort(
    driver_key: str,
    model: str = "",
    effort: str = "",
    help_text: str = "",
    strict: bool = False,
    **_kwargs: object,
) -> str:
    """
    将任意输入推理档位严格收敛至「CLI 驱动 + 模型名」支持的合法档位：
    - agy + gemini-4-carbon / gemini-4-argon 传入 xhigh / max 时强制回退至 high；
    - agy + Orchestrator (Carbon) / Orchestrator (Argon) 返回空字符串（不传 --effort）。
    """
    spec = get_model_effort_spec(driver_key, model=model, help_text=help_text)
    if not spec.get("supports_effort", True):
        return ""
    allowed: List[str] = spec["allowed"]
    e = (effort or "").strip().lower()
    if e in ("none",):
        e = ""
    if e == "ultra":
        e = "max"
    if not e:
        return spec["default"]
    if e in allowed:
        return e
    if e in ORDERED_EFFORT_LEVELS:
        req_idx = ORDERED_EFFORT_LEVELS.index(e)
        lower_or_eq = [
            cand for cand in allowed if cand in ORDERED_EFFORT_LEVELS and ORDERED_EFFORT_LEVELS.index(cand) <= req_idx
        ]
        return lower_or_eq[-1] if lower_or_eq else allowed[0]
    return spec["default"]


def step_down_model_effort(
    driver_key: str,
    model: str = "",
    current_effort: str = "",
    help_text: str = "",
) -> str:
    """将当前模型的推理档位临时下调一档（仅用于单轮降级档位重试，不修改全局保存配置）。"""
    spec = get_model_effort_spec(driver_key, model=model, help_text=help_text)
    if not spec.get("supports_effort", True):
        return ""
    allowed: List[str] = spec.get("allowed") or []
    if not allowed:
        return ""
    norm = normalize_model_effort(driver_key, model=model, effort=current_effort, help_text=help_text)
    if norm in allowed:
        idx = allowed.index(norm)
        return allowed[idx - 1] if idx > 0 else allowed[0]
    return allowed[0]


async def list_workspace_files_async(workspace_dir: str, query: str = "", limit: int = 200) -> dict:
    """后台线程异步检索工作区文件清单，零事件循环阻塞。"""
    return await run_index_in_thread(list_workspace_files, workspace_dir, query, limit)


def export_model_effort_catalog() -> dict:
    _refresh_declarative_driver_tables()
    """导出前端可直接消费的「CLI 驱动 + 模型名」推理档位能力表、分级目录与订阅档位矩阵。"""
    raw_cat = load_driver_catalog()
    drivers_info: Dict[str, dict] = {}
    for drv, dspec in DRIVER_SPECS.items():
        drivers_info[drv] = {
            "provider": dspec.get("provider", "Custom"),
            "cli_name": dspec["cli_name"],
            "short_label": dspec.get("short_label", drv.upper()),
            "default_model": dspec["default_model"],
            "default_discuss_effort": dspec["default_discuss_effort"],
            "default_exec_effort": dspec["default_exec_effort"],
            "recommended_models": dspec.get("recommended_models", []),
            "model_groups": dspec.get("model_groups", []),
            "models": MODEL_EFFORT_CAPABILITIES.get(drv, {}),
        }
    return {
        "schema_version": raw_cat.get("schema_version", 2),
        "canonical_efforts": list(CANONICAL_EFFORT_LEVELS),
        "ordered_efforts": list(ORDERED_EFFORT_LEVELS),
        "subscription_tiers": raw_cat.get("subscription_tiers", {}),
        "vendor_plans": raw_cat.get("vendor_plans", {}),
        "exclusive_default_models": dict(_DRIVER_EXCLUSIVE_DEFAULT_MODELS),
        "drivers": drivers_info,
    }


class CLIInvocationError(RuntimeError):
    """结构化 CLI 调用异常，携带精确错误分类、进程退出码与原始 stderr 摘要。"""

    def __init__(
        self,
        message: str,
        *,
        error_kind: str = "process_error",
        exit_code: Optional[int] = None,
        stderr: str = "",
        driver: str = "",
        model: str = "",
        effort: str = "",
    ):
        super().__init__(message)
        self.error_kind = error_kind
        self.exit_code = exit_code
        self.stderr = (stderr or "").strip()
        self.driver = driver
        self.model = model
        self.effort = effort


def _first_meaningful_error_line(text: str) -> str:
    if not text:
        return ""
    noise_prefixes = ("traceback", "  file ", "warning:", "warn:", "(node:")
    for raw_ln in text.splitlines():
        ln = raw_ln.strip()
        if not ln:
            continue
        if ln.lower().startswith(noise_prefixes):
            continue
        return ln[:220]
    first = text.strip().splitlines()[0].strip() if text.strip() else ""
    return first[:220]


def classify_cli_error(
    driver_key: str,
    raw_err: str = "",
    stderr: str = "",
    exit_code: Optional[int] = None,
    model: str = "",
    effort: str = "",
    is_timeout: bool = False,
    timeout_sec: float = 0.0,
) -> CLIInvocationError:
    """
    解析进程退出码与 stderr/流内错误，精准区分：
    1) timeout: 超时
    2) unsupported_effort_or_model: 当前模型不支持该推理档位或模型名无效
    3) quota_rate_limit: 额度或并发限流（429 / Quota）
    4) auth_expired: 登录鉴权失效（401 / 未登录 / API Key 失效）
    5) process_error: 其他进程退出或空输出异常（严禁将空输出误报为登录鉴权错误）
    """
    cli_label = DRIVER_SPECS.get(driver_key, {}).get("cli_name", driver_key or "CLI")
    parts: List[str] = []
    for piece in (raw_err.strip(), stderr.strip()):
        if piece and piece not in parts:
            parts.append(piece)
    combined = "\n".join(parts).strip()
    low = combined.lower()
    stderr_summary = (stderr.strip() or raw_err.strip())[:2400]
    rc_label = str(exit_code) if exit_code is not None else "0"
    looks_like_usage_dump = "usage:" in low or "options:" in low

    if is_timeout or any(
        k in low for k in ("timed out", "etimedout", "deadline exceeded", "request timeout")
    ):
        dur_txt = f"超过 {int(timeout_sec)} 秒" if timeout_sec > 0 else "等待逾时"
        msg = (
            f"{cli_label} 调用超时（{dur_txt}，模型 {model or '默认'} · 档位 {effort or '默认'}）。"
            "可直接点击下方「原配置重试（不限时）」、「降级档位重试」或「切换备用引擎代答」。"
        )
        return CLIInvocationError(
            msg,
            error_kind="timeout",
            exit_code=exit_code,
            stderr=stderr_summary or f"Timeout ({dur_txt})",
            driver=driver_key,
            model=model,
            effort=effort,
        )

    effort_keywords = (
        "effort",
        "reasoning_effort",
        "model_reasoning_effort",
        "thinking_level",
        "thinking budget",
        "reasoning budget",
        "invalid model selection",
    )
    effort_rejection_markers = (
        "invalid",
        "unsupported",
        "not support",
        "not supported",
        "does not support",
        "unknown variant",
        "unknown value",
        "valid values",
        "possible values",
        "allowed values",
        "must be one of",
        "error",
        "rejected",
    )
    has_effort_kw = any(k in low for k in effort_keywords) and (
        any(m in low for m in effort_rejection_markers) or (exit_code not in (None, 0))
    )
    if has_effort_kw:
        spec = get_model_effort_spec(driver_key, model=model)
        snippet = _first_meaningful_error_line(combined)
        detail_tail = f"（原始摘要：{snippet[:120]}）" if snippet else ""
        if not spec.get("supports_effort", True):
            msg = (
                f"当前模型「{model or spec['model']}」不支持传入 --effort 推理档位参数"
                f"（退出码 {rc_label}）{detail_tail}。已为您自动识别无档位模式，请重试。"
            )
        else:
            legal_str = " / ".join(spec["allowed"])
            msg = (
                f"当前模型「{model or spec['model']}」不支持推理档位「{effort or '当前档位'}」"
                f"（{cli_label} 合法档位：{legal_str}，退出码 {rc_label}）{detail_tail}。"
                f"请在设置中切换至 {spec['max']} 或更低档位后重试。"
            )
        return CLIInvocationError(
            msg,
            error_kind="unsupported_effort_or_model",
            exit_code=exit_code,
            stderr=stderr_summary,
            driver=driver_key,
            model=model,
            effort=effort,
        )

    quota_keywords = (
        "429",
        "rate limit",
        "rate_limit",
        "ratelimit",
        "quota",
        "resource_exhausted",
        "resource exhausted",
        "too many requests",
        "insufficient_quota",
        "insufficient_g1_credits",
        "credits balance is too low",
        "usage limit",
        "credit balance",
        "overloaded",
        "capacity exceeded",
        "concurrency limit",
        "concurrent requests",
    )
    if any(k in low for k in quota_keywords):
        snippet = _first_meaningful_error_line(combined)
        detail_tail = f"（{snippet[:110]}）" if snippet else ""
        msg = (
            f"{cli_label} 触发额度或并发限流保护（429 / Quota，退出码 {rc_label}）{detail_tail}。"
            "可点击「切换备用引擎代答」或稍候点击「原配置重试（不限时）」。"
        )
        return CLIInvocationError(
            msg,
            error_kind="quota_rate_limit",
            exit_code=exit_code,
            stderr=stderr_summary,
            driver=driver_key,
            model=model,
            effort=effort,
        )

    auth_keywords = (
        "401",
        "unauthorized",
        "unauthenticated",
        "authentication required",
        "authentication failed",
        "auth failed",
        "not logged in",
        "login required",
        "please login",
        "please log in",
        "please sign in",
        "sign in required",
        "invalid_api_key",
        "invalid api key",
        "missing api key",
        "api key not found",
        "token expired",
        "expired token",
        "re-authenticate",
    )
    if not looks_like_usage_dump and (
        any(k in low for k in auth_keywords)
        or ("403" in low and any(x in low for x in ("forbidden", "permission", "credential", "token", "auth")))
    ):
        snippet = _first_meaningful_error_line(combined)
        detail_tail = f"（{snippet[:110]}）" if snippet else ""
        msg = (
            f"{cli_label} 登录鉴权失效或凭证未就绪（退出码 {rc_label}）{detail_tail}。"
            "请在终端完成对应 CLI 登录鉴权后点击「单席重试」。"
        )
        return CLIInvocationError(
            msg,
            error_kind="auth_expired",
            exit_code=exit_code,
            stderr=stderr_summary,
            driver=driver_key,
            model=model,
            effort=effort,
        )

    model_or_param_keywords = (
        "unknown variant",
        "unsupported value",
        "does not support",
        "not supported",
        "is not supported",
        "model not found",
        "model_not_found",
        "unknown model",
        "invalid model",
        "no such model",
        "no model configuration is available",
        "not available for model",
        "access to model",
        "invalid_argument",
        "invalid argument",
    )
    if any(k in low for k in model_or_param_keywords):
        snippet = _first_meaningful_error_line(combined)
        detail_tail = f"：{snippet[:120]}" if snippet else ""
        msg = (
            f"{cli_label} 当前模型或推理档位不受支持（模型：{model or '默认'} · 档位：{effort or '默认'}，"
            f"退出码 {rc_label}）{detail_tail}"
        )
        return CLIInvocationError(
            msg,
            error_kind="unsupported_effort_or_model",
            exit_code=exit_code,
            stderr=stderr_summary,
            driver=driver_key,
            model=model,
            effort=effort,
        )

    snippet = _first_meaningful_error_line(combined)
    if snippet:
        msg = f"{cli_label} 进程执行异常（退出码 {rc_label}）：{snippet}"
    else:
        msg = (
            f"{cli_label} 进程已结束但未返回有效输出（退出码 {rc_label}，stderr 为空）。"
            "可展开查看诊断详情或点击「单席重试」重新调用。"
        )
    return CLIInvocationError(
        msg,
        error_kind="process_error",
        exit_code=exit_code,
        stderr=stderr_summary or f"Process exited with code {rc_label} and empty stdout/stderr.",
        driver=driver_key,
        model=model,
        effort=effort,
    )


def _is_model_or_effort_rejection(err_or_exc: object) -> bool:
    if isinstance(err_or_exc, CLIInvocationError):
        return err_or_exc.error_kind == "unsupported_effort_or_model"
    classified = classify_cli_error("agy", raw_err=str(err_or_exc or ""))
    return classified.error_kind == "unsupported_effort_or_model"


@dataclass
class AgentRoleConfig:
    agent_id: str
    name: str
    title: str
    cli_name: str
    binary_candidates: List[str]
    fallback_paths: List[str] = field(default_factory=list)
    driver: str = "auto"
    persona: str = ""
    custom_name: str = ""
    custom_binary: str = ""
    model: str = ""
    discussion_effort: str = "high"
    execution_effort: str = "high"
    lock_discussion_effort: bool = False
    _cached_probe_path: str = field(default="", repr=False)
    _cached_meta: Dict[str, str] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        if self.persona not in PERSONA_PRESETS:
            self.persona = DEFAULT_SEAT_PERSONAS.get(self.agent_id, "planner")
        self.title = PERSONA_PRESETS[self.persona]["short_tag"]

    def preferred_driver_key(self) -> str:
        if self.driver in DRIVER_SPECS:
            return self.driver
        return DEFAULT_SEAT_DRIVERS.get(self.agent_id, "agy")

    def detect_primary_binary(self) -> Optional[str]:
        drv = self.preferred_driver_key()
        spec = DRIVER_SPECS.get(drv) or DRIVER_SPECS["agy"]
        return resolve_binary(
            spec["binary_candidates"],
            self.custom_binary,
            DRIVER_FALLBACK_PATHS.get(drv, []),
        )

    def resolve_effective_driver_and_binary(self, allow_single_cli_fallback: bool = True) -> Tuple[str, Optional[str], bool]:
        """
        返回 (effective_driver, binary_path, is_shared_fallback)。
        当客户本机只安装了 1 种 CLI 且开启单 CLI 多席位弹性复用时，自动借用可用 CLI 驱动该席位。
        """
        pref = self.preferred_driver_key()
        primary_bin = self.detect_primary_binary()
        if primary_bin and self.driver != "auto":
            return pref, primary_bin, False
        if primary_bin and self.driver == "auto":
            return pref, primary_bin, False

        if allow_single_cli_fallback or self.driver == "auto":
            fallback_order = ["agy", "codex", "claude", "grok"] + [
                k for k in DRIVER_SPECS.keys() if k not in ("agy", "codex", "claude", "grok")
            ]
            for cand_drv in fallback_order:
                if cand_drv == pref:
                    continue
                alt_bin = detect_driver_binary(cand_drv)
                if alt_bin:
                    return cand_drv, alt_bin, True

        return pref, None, False

    def detect_binary(self, allow_single_cli_fallback: bool = True) -> Optional[str]:
        _, bpath, _ = self.resolve_effective_driver_and_binary(allow_single_cli_fallback=allow_single_cli_fallback)
        return bpath

    def get_probe_info(
        self,
        persist_cache: bool = True,
        allow_single_cli_fallback: bool = True,
    ) -> Tuple[Optional[str], str, str, str, bool]:
        eff_drv, bpath, is_fb = self.resolve_effective_driver_and_binary(
            allow_single_cli_fallback=allow_single_cli_fallback
        )
        if not bpath:
            return None, "", "", eff_drv, False
        if bpath != self._cached_probe_path or not self._cached_meta:
            self._cached_meta = probe_cli_metadata(bpath, persist=persist_cache)
            self._cached_probe_path = bpath
        return bpath, self._cached_meta.get("version", ""), self._cached_meta.get("help", ""), eff_drv, is_fb


DEFAULT_IDLE_TIMEOUT_SEC = 300
DEFAULT_TURN_TIMEOUT_SEC = 600


@dataclass
class RuntimeSettings:
    workspace_dir: str = field(default_factory=lambda: os.getcwd())
    allow_single_cli_fallback: bool = True
    pacing_mode: str = "standard"  # "standard" (300s/600s) | "extended" | "custom"
    idle_timeout_sec: int = DEFAULT_IDLE_TIMEOUT_SEC
    turn_timeout_sec: int = DEFAULT_TURN_TIMEOUT_SEC
    max_ref_chars: int = MAX_ROUND_SOURCE_CHARS
    roster_preset: str = "role_experts"
    single_cli_concurrency: int = 3
    post_exec_verify_cmd: str = ""
    subscription_tier: str = "all"
    vendor_subscriptions: Dict[str, str] = field(default_factory=dict)
    agents: Dict[str, AgentRoleConfig] = field(default_factory=dict)
    _status_cache: Optional[Dict[str, dict]] = field(default=None, repr=False)
    _status_cache_ts: float = field(default=0.0, repr=False)

    def invalidate_status_cache(self) -> None:
        self._status_cache = None
        self._status_cache_ts = 0.0

    def resolve_seat_name(
        self,
        agent_id: str,
        eff_drv: str = "",
        eff_model: str = "",
        persona_key: str = "",
    ) -> str:
        cfg = self.agents.get(agent_id)
        if cfg and cfg.custom_name.strip():
            return cfg.custom_name.strip()[:20]
        preset_key = self.roster_preset if self.roster_preset in ROSTER_NAME_PRESETS else "role_experts"
        if preset_key == "auto_driver":
            drv = eff_drv or (cfg.preferred_driver_key() if cfg else "agy")
            short_drv = DRIVER_SPECS.get(drv, {}).get("short_label") or {"agy": "AGY", "grok": "Grok", "codex": "Codex", "claude": "Claude", "ollama": "Ollama"}.get(drv, drv.upper())
            pspec = get_persona_spec(persona_key or (cfg.persona if cfg else ""), fallback_agent_id=agent_id)
            return f"{short_drv}·{pspec['short_tag']}"
        preset_names = ROSTER_NAME_PRESETS[preset_key].get("names") or {}
        if preset_names.get(agent_id):
            return preset_names[agent_id]
        return {
            "carbon": "架构师",
            "grok": "审计官",
            "astra": "工程师",
            "vega": "交互设计",
            "titan": "性能专家",
            "prism": "质量验证",
        }.get(agent_id, agent_id.capitalize())

    @classmethod
    def create_default(cls, workspace_dir: str) -> "RuntimeSettings":
        _refresh_declarative_driver_tables()
        return cls(
            workspace_dir=workspace_dir,
            allow_single_cli_fallback=True,
            pacing_mode="standard",
            idle_timeout_sec=DEFAULT_IDLE_TIMEOUT_SEC,
            turn_timeout_sec=DEFAULT_TURN_TIMEOUT_SEC,
            max_ref_chars=MAX_ROUND_SOURCE_CHARS,
            roster_preset="role_experts",
            single_cli_concurrency=3,
            post_exec_verify_cmd="",
            agents={
                "carbon": AgentRoleConfig(
                    agent_id="carbon",
                    name="架构师",
                    title="规划",
                    cli_name="Antigravity CLI",
                    binary_candidates=["agy", "antigravity"],
                    fallback_paths=list(AGY_MACOS_FALLBACK_PATHS),
                    driver="agy",
                    persona="planner",
                    model=DEFAULT_TOP_MODELS["carbon"][0],
                    discussion_effort=DEFAULT_TOP_MODELS["carbon"][1],
                    execution_effort=DEFAULT_TOP_MODELS["carbon"][1],
                ),
                "grok": AgentRoleConfig(
                    agent_id="grok",
                    name="审计官",
                    title="审计",
                    cli_name="Grok CLI",
                    binary_candidates=["grok"],
                    driver="grok",
                    persona="red_team",
                    model=DEFAULT_TOP_MODELS["grok"][0],
                    discussion_effort=DEFAULT_TOP_MODELS["grok"][1],
                    execution_effort=DEFAULT_TOP_MODELS["grok"][1],
                ),
                "astra": AgentRoleConfig(
                    agent_id="astra",
                    name="工程师",
                    title="工程",
                    cli_name="Codex CLI",
                    binary_candidates=["codex"],
                    fallback_paths=list(CODEX_MACOS_FALLBACK_PATHS),
                    driver="codex",
                    persona="implementer",
                    model=DEFAULT_TOP_MODELS["astra"][0],
                    discussion_effort=DEFAULT_TOP_MODELS["astra"][1],
                    execution_effort=DEFAULT_TOP_MODELS["astra"][1],
                ),
                "vega": AgentRoleConfig(
                    agent_id="vega",
                    name="交互设计",
                    title="交互",
                    cli_name="Auto CLI",
                    binary_candidates=["agy", "codex", "grok"],
                    fallback_paths=list(AGY_MACOS_FALLBACK_PATHS) + list(CODEX_MACOS_FALLBACK_PATHS),
                    driver="auto",
                    persona="product_ux",
                    model="",
                    discussion_effort="high",
                    execution_effort="high",
                ),
                "titan": AgentRoleConfig(
                    agent_id="titan",
                    name="性能专家",
                    title="性能",
                    cli_name="Auto CLI",
                    binary_candidates=["agy", "codex", "grok"],
                    fallback_paths=list(AGY_MACOS_FALLBACK_PATHS) + list(CODEX_MACOS_FALLBACK_PATHS),
                    driver="auto",
                    persona="perf_sre",
                    model="",
                    discussion_effort="high",
                    execution_effort="high",
                ),
                "prism": AgentRoleConfig(
                    agent_id="prism",
                    name="质量验证",
                    title="验证",
                    cli_name="Auto CLI",
                    binary_candidates=["agy", "codex", "grok"],
                    fallback_paths=list(AGY_MACOS_FALLBACK_PATHS) + list(CODEX_MACOS_FALLBACK_PATHS),
                    driver="auto",
                    persona="qa_audit",
                    model="",
                    discussion_effort="high",
                    execution_effort="high",
                ),
            },
        )

    def detect_available_drivers(self) -> List[dict]:
        """探测本机独立已安装的 CLI 驱动族（按 realpath 去重防软链接伪异构），供前端『异构混编推荐』调用。"""
        _refresh_declarative_driver_tables()
        found: List[dict] = []
        seen_families: Set[str] = set()
        ordered_drvs = ["agy", "codex", "claude", "grok"] + [
            k for k in DRIVER_SPECS.keys() if k not in ("agy", "codex", "claude", "grok")
        ]
        for drv_k in ordered_drvs:
            spec = DRIVER_SPECS.get(drv_k)
            if not spec:
                continue
            bpath = detect_driver_binary(drv_k)
            if not bpath:
                continue
            fam_k = normalize_driver_family_key(drv_k, bpath)
            if fam_k in seen_families:
                continue
            seen_families.add(fam_k)
            prov_name, cli_disp = DRIVER_PROVIDER_LABELS.get(drv_k, (spec.get("provider", "Custom"), spec["cli_name"]))
            found.append({
                "driver": drv_k,
                "cli_name": cli_disp,
                "provider": prov_name,
                "binary_path": bpath,
                "driver_family_key": fam_k,
                "default_model": spec.get("default_model", ""),
            })
        return found

    def inspect_status(self, force_refresh: bool = False) -> Dict[str, dict]:
        """并发探测所有 CLI 元信息并缓存（5s TTL），实时热加载外置驱动目录并计算异构/同源独立性元数据。"""
        _refresh_declarative_driver_tables()
        now_m = time.monotonic()
        if not force_refresh and self._status_cache is not None and (now_m - self._status_cache_ts) < 5.0:
            return {k: dict(v) for k, v in self._status_cache.items()}
        items = list(self.agents.items())
        need_parallel = any(
            (cfg.detect_binary(self.allow_single_cli_fallback) or "") != cfg._cached_probe_path
            or not cfg._cached_meta
            for _, cfg in items
        )
        if need_parallel:
            with ThreadPoolExecutor(max_workers=3) as pool:
                list(
                    pool.map(
                        lambda kv: kv[1].get_probe_info(
                            persist_cache=False,
                            allow_single_cli_fallback=self.allow_single_cli_fallback,
                        ),
                        items,
                    )
                )
            _save_disk_probe_cache()

        # 按 realpath 规范化驱动族统计复用度，消除『· 单引擎多角色』模糊占位，透出真实提供方与独立性标签
        fam_counts: Dict[str, int] = {}
        probed_map: Dict[str, Tuple[Optional[str], str, str, str, bool]] = {}
        for aid, cfg in items:
            pinfo = cfg.get_probe_info(
                persist_cache=False,
                allow_single_cli_fallback=self.allow_single_cli_fallback,
            )
            probed_map[aid] = pinfo
            if pinfo[0]:
                fk = normalize_driver_family_key(pinfo[3], pinfo[0])
                fam_counts[fk] = fam_counts.get(fk, 0) + 1

        result: Dict[str, dict] = {}
        for aid, cfg in items:
            bpath, ver, help_text, eff_drv, is_shared_fb = probed_map[aid]
            eff_spec = DRIVER_SPECS.get(eff_drv, DRIVER_SPECS["agy"])
            effective_model = resolve_effective_model_for_driver(
                eff_drv,
                cfg.model,
                is_shared_fb=is_shared_fb,
            )
            fam_key = normalize_driver_family_key(eff_drv, bpath or "") if bpath else normalize_driver_family_key(eff_drv, "")
            shared_multi_seat = is_shared_fb or (bool(bpath) and fam_counts.get(fam_key, 0) > 1)
            prov_name, clean_cli_name = DRIVER_PROVIDER_LABELS.get(eff_drv, ("Custom", eff_spec["cli_name"]))
            display_cli_name = clean_cli_name or eff_spec["cli_name"]
            is_heterogeneous = bool(bpath) and not shared_multi_seat
            indep_label = "异构独立" if is_heterogeneous else ("同源复用" if bool(bpath) else "未就绪")

            effort_spec = get_model_effort_spec(eff_drv, model=effective_model, help_text=help_text)
            eff_discuss = normalize_model_effort(
                eff_drv,
                model=effective_model,
                effort=cfg.discussion_effort,
                help_text=help_text,
            )
            eff_exec = normalize_model_effort(
                eff_drv,
                model=effective_model,
                effort=cfg.execution_effort,
                help_text=help_text,
            )

            pspec = get_persona_spec(cfg.persona, fallback_agent_id=aid)
            cfg.title = pspec["short_tag"]
            resolved_name = self.resolve_seat_name(
                aid,
                eff_drv=eff_drv,
                eff_model=effective_model,
                persona_key=pspec["key"],
            )
            cfg.name = resolved_name

            result[aid] = {
                "agent_id": aid,
                "name": resolved_name,
                "custom_name": cfg.custom_name,
                "avatar_char": resolved_name[0].upper() if resolved_name else aid[0].upper(),
                "title": pspec["short_tag"],
                "persona": pspec["key"],
                "persona_label": pspec["label"],
                "wb_kind": pspec.get("wb_kind", "decision"),
                "wb_title": pspec["wb_title"],
                "cue_btn": pspec["cue_btn"],
                "driver": cfg.driver,
                "effective_driver": eff_drv,
                "provider_name": prov_name,
                "driver_family_key": fam_key,
                "is_heterogeneous": is_heterogeneous,
                "independence_label": indep_label,
                "shared_fallback": is_shared_fb,
                "shared_cli_group": shared_multi_seat,
                "cli_name": display_cli_name,
                "binary_candidates": DRIVER_SPECS[cfg.preferred_driver_key()]["binary_candidates"],
                "binary_detected": bool(bpath),
                "binary_path": bpath or "",
                "version": ver,
                "custom_binary": cfg.custom_binary,
                "model": cfg.model,
                "effective_model": effective_model,
                "supports_effort": effort_spec.get("supports_effort", True),
                "allowed_efforts": effort_spec["allowed"],
                "default_effort": effort_spec["default"],
                "max_effort": effort_spec["max"],
                "discussion_effort": eff_discuss,
                "effective_discussion_effort": eff_discuss,
                "execution_effort": eff_exec,
                "effective_execution_effort": eff_exec,
                "lock_discussion_effort": bool(cfg.lock_discussion_effort),
            }
        self._status_cache = {k: dict(v) for k, v in result.items()}
        self._status_cache_ts = now_m
        return result


def _short_activity_path(raw_path: str, cwd: str = "") -> str:
    p = str(raw_path or "").strip().strip("'\"")
    if not p:
        return ""
    if cwd:
        try:
            real_cwd = os.path.realpath(cwd)
            real_p = os.path.realpath(os.path.join(real_cwd, p) if not os.path.isabs(p) else p)
            if real_p.startswith(real_cwd + os.sep):
                p = os.path.relpath(real_p, real_cwd)
        except Exception:
            pass
    parts = [seg for seg in p.replace("\\", "/").split("/") if seg]
    if len(parts) > 2:
        p = "/".join(parts[-2:])
    return p[:48]


def _format_cli_tool_activity(driver_key: str, tool_name: str, info: object, cwd: str = "") -> str:
    """将底层 CLI 工具读取或思考事件格式化为简洁可读的前端实时状态文案。"""
    tname = str(tool_name or "").strip().lower()
    meta = info if isinstance(info, dict) else {}

    if driver_key == "agy":
        params = meta.get("parameters") if isinstance(meta.get("parameters"), dict) else {}
        if not params and isinstance(meta.get("tool_info"), dict):
            params = meta["tool_info"].get("parameters") or {}
        if "read" in tname or "view" in tname:
            target_p = _short_activity_path(params.get("Path") or params.get("path") or params.get("file_path") or "", cwd)
            s_ln = params.get("StartLine") or params.get("start_line")
            e_ln = params.get("EndLine") or params.get("end_line")
            if target_p and s_ln and e_ln:
                return f"正在读取 {target_p} (L{s_ln}-L{e_ln})…"
            if target_p:
                return f"正在读取 {target_p}…"
            return "正在只读查看源码…"
        if "grep" in tname or "search" in tname or "find" in tname:
            q = str(params.get("Query") or params.get("query") or params.get("pattern") or "").strip()[:26]
            return f"正在检索代码「{q}」…" if q else "正在检索项目源码…"
        if "list" in tname or "glob" in tname or "dir" in tname:
            return "正在浏览项目目录…"
        if tname:
            return f"正在执行只读检查 ({tname[:20]})…"
        return ""

    if driver_key == "grok":
        raw_in = meta.get("rawInput") if isinstance(meta.get("rawInput"), dict) else {}
        locs = meta.get("locations") if isinstance(meta.get("locations"), list) else []
        loc_path = ""
        if locs and isinstance(locs[0], dict):
            loc_path = str(locs[0].get("path") or "")
        if "read" in tname or (not tname and loc_path):
            target_p = _short_activity_path(
                raw_in.get("target_file") or raw_in.get("path") or raw_in.get("file_path") or loc_path,
                cwd,
            )
            offset = raw_in.get("offset") or raw_in.get("start_line")
            limit = raw_in.get("limit")
            if target_p and offset and limit:
                try:
                    s_i = int(offset)
                    e_i = s_i + int(limit) - 1
                    return f"正在读取 {target_p} (L{s_i}-L{e_i})…"
                except Exception:
                    pass
            if target_p:
                return f"正在读取 {target_p}…"
            return "正在只读查看源码…"
        if "grep" in tname or "search" in tname:
            q = str(raw_in.get("pattern") or raw_in.get("query") or "").strip()[:26]
            return f"正在检索代码「{q}」…" if q else "正在检索项目源码…"
        if "list" in tname or "dir" in tname or "glob" in tname:
            target_p = _short_activity_path(raw_in.get("target_directory") or raw_in.get("path") or loc_path, cwd)
            return f"正在浏览目录 {target_p}…" if target_p else "正在浏览项目目录…"
        if tname:
            return f"正在分析上下文 ({tname[:20]})…"
        return ""

    if driver_key == "codex":
        if tname == "reasoning":
            return "正在深度推演方案与边界…"
        if tname in ("command_execution", "local_shell_call"):
            cmd_str = str(meta.get("command") or "").strip()
            m_file = re.search(r"([A-Za-z0-9_./-]+\.(?:py|js|ts|tsx|jsx|css|html|json|md|sh))\b", cmd_str)
            if m_file:
                short_f = _short_activity_path(m_file.group(1), cwd)
                if any(k in cmd_str for k in ("rg ", "grep ")):
                    return f"正在检索 {short_f}…"
                return f"正在读取 {short_f}…"
            if any(k in cmd_str for k in ("rg ", "grep ")):
                return "正在检索项目代码…"
            return "正在只读核对项目上下文…"
        if "search" in tname or "read" in tname:
            return "正在读取项目源码…"
    return ""


class WarmAntigravityProcess:
    """Antigravity CLI (`agy --input-format stream-json --output-format stream-json`) 席位隔离常驻进程。"""

    def __init__(
        self,
        binary_path: str,
        model: str,
        effort: str,
        cwd: str,
        session_id: str = "",
        seat_id: str = "",
        disable_slash: bool = True,
        supports_effort: bool = True,
        sandbox: bool = True,
        help_text: str = "",
    ):
        self.binary_path = binary_path
        self.model = model.strip()
        self.help_text = help_text
        self.effort = self.normalize_agy_effort(effort.strip(), help_text=help_text, model=self.model)
        self.cwd = cwd
        self.session_id = session_id
        self.seat_id = seat_id
        self.disable_slash = disable_slash
        self.supports_effort = supports_effort
        self.sandbox = sandbox
        self.proc: Optional[asyncio.subprocess.Process] = None
        self._supervised = None
        self._call_tmp = ""
        self.turn_count: int = 0
        self._lock = asyncio.Lock()

    @staticmethod
    def normalize_agy_effort(effort: str, help_text: str = "", model: str = "") -> str:
        """
        按 agy 下具体模型（如 gemini-4-carbon 仅允许 low|medium|high）精准收敛推理档位，
        严禁向服务端透传不支持的 xhigh / max。
        """
        return normalize_model_effort("agy", model=model or "gemini-4-carbon", effort=effort, help_text=help_text)

    async def ensure_started(self) -> None:
        if self.proc and self.proc.returncode is None:
            return
        if self._supervised is not None or self._call_tmp:
            await self.close()
        self.turn_count = 0
        cmd = [
            self.binary_path,
            "--input-format",
            "stream-json",
            "--output-format",
            "stream-json",
        ]
        if self.disable_slash:
            cmd.append("--disable-slash-commands")
        if self.sandbox and "--sandbox" in self.help_text:
            cmd.append("--sandbox")
        if self.model:
            cmd.extend(["--model", self.model])
        norm_eff = self.normalize_agy_effort(self.effort, help_text=self.help_text, model=self.model)
        if self.supports_effort and norm_eff:
            cmd.extend(["--effort", norm_eff])
        env, self._call_tmp = UnifiedAgentRunner._prepare_isolated_call_env(
            self.session_id or "prewarm", self.seat_id or "carbon"
        )
        try:
            self._supervised = await spawn_supervised_cli(
                cmd, cwd=self.cwd if os.path.isdir(self.cwd) else os.getcwd(), env=env,
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE, limit=4 * 1024 * 1024,
            )
            self.proc = self._supervised.proc
        except BaseException:
            await self.close()
            raise

    async def stream_turn(
        self,
        prompt: str,
        *,
        session_attachments: Optional[List[dict]] = None,
        att_mgr: Optional[SessionAttachmentManager] = None,
    ) -> AsyncGenerator[dict, None]:
        async with self._lock:
            await self.ensure_started()
            assert self.proc and self.proc.stdin and self.proc.stdout
            eff_prompt = prompt
            if session_attachments and att_mgr is not None and self.session_id:
                att_block, _ = att_mgr.stage_for_cli_turn(self.session_id, session_attachments, self._call_tmp)
                if att_block:
                    eff_prompt = f"{att_block}\n\n{prompt}"
            payload = json.dumps({"event": "user", "message": {"content": eff_prompt}}, ensure_ascii=False) + "\n"
            self.proc.stdin.write(payload.encode("utf-8"))
            await self.proc.stdin.drain()

            emitted = False
            saw_tool_since_text = False
            ended_with_nl = True
            last_activity = ""
            turn_finished = False
            try:
                while True:
                    line_b = await self.proc.stdout.readline()
                    if not line_b:
                        turn_finished = True
                        err_msg = ""
                        rc: Optional[int] = None
                        if self.proc.stderr:
                            err_msg = (await self.proc.stderr.read()).decode("utf-8", errors="replace").strip()
                        try:
                            rc = await asyncio.wait_for(self.proc.wait(), timeout=1.0)
                        except Exception:
                            rc = self.proc.returncode
                        await self.close()
                        if not emitted:
                            raise classify_cli_error(
                                "agy",
                                raw_err=err_msg,
                                stderr=err_msg,
                                exit_code=rc,
                                model=self.model,
                                effort=self.effort,
                            )
                        break

                    line = line_b.decode("utf-8", errors="replace").strip()
                    if not line:
                        continue
                    try:
                        evt = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    etype = evt.get("event")
                    if etype == "step_update":
                        su = evt.get("step_update", {})
                        st_type = su.get("step_type", "")
                        if st_type == "agent_response":
                            delta = su.get("text_delta", "")
                            if delta:
                                if saw_tool_since_text and emitted and not ended_with_nl:
                                    yield {"type": "delta", "text": "\n\n"}
                                saw_tool_since_text = False
                                emitted = True
                                ended_with_nl = delta.endswith("\n")
                                yield {"type": "delta", "text": delta}
                            elif su.get("state") in ("ACTIVE", "RUNNING") and not emitted:
                                act = "正在组织推演输出…"
                                last_activity = act
                                yield {"type": "status", "detail": act}
                        elif st_type == "tool" and su.get("state") in ("ACTIVE", "RUNNING", None):
                            saw_tool_since_text = True
                            act = _format_cli_tool_activity("agy", su.get("tool_name", ""), su, cwd=self.cwd) or "正在执行只读源码检查…"
                            last_activity = act
                            yield {"type": "status", "detail": act}
                        elif st_type in ("thinking", "thought"):
                            act = "正在深度推演方案与边界…"
                            last_activity = act
                            yield {"type": "status", "detail": act}
                        elif st_type and st_type != "agent_response":
                            act = _format_cli_tool_activity("agy", st_type, su, cwd=self.cwd) or f"正在推进步骤 ({st_type[:18]})…"
                            last_activity = act
                            yield {"type": "status", "detail": act}
                    elif etype and etype != "result" and not emitted:
                        yield {"type": "status", "detail": last_activity or "正在深度推演方案与边界…"}
                    elif etype == "result":
                        turn_finished = True
                        res = evt.get("result", {})
                        if not emitted and res.get("response"):
                            emitted = True
                            yield {"type": "delta", "text": res["response"]}
                        if res.get("status") not in ("SUCCESS", None) and not emitted:
                            raw_res_err = str(res.get("error") or f"Antigravity 状态异常: {res.get('status')}")
                            raise classify_cli_error(
                                "agy",
                                raw_err=raw_res_err,
                                stderr=raw_res_err,
                                exit_code=self.proc.returncode,
                                model=self.model,
                                effort=self.effort,
                            )
                        break

                if emitted:
                    self.turn_count += 1
            finally:
                if not turn_finished:
                    await self.close()

    async def close(self) -> None:
        handle, temp = self._supervised, self._call_tmp
        self._supervised, self._call_tmp, self.proc = None, "", None
        self.turn_count = 0
        try:
            if handle is not None:
                await terminate_and_reap_process_group(handle)
        finally:
            UnifiedAgentRunner._cleanup_isolated_call_tmp(temp)


class UnifiedAgentRunner:
    """
    真实本地 CLI 统一流式执行器：
    - 支持按 (session_id, agent_id) 严格物理隔离多席位上下文（单 CLI 分饰多角绝不串台）
    - 支持席位切换预设身份后自动刷新角色提示词注入
    - 支持增量会话中新 @文件 动态补齐注入，以及 synthesis 独立长文决议通道
    - 支持任意席位作为执行主刀人实时流式输出（exec_delta）完成只读预演或工作区代码写入
    """

    def __init__(self, settings: RuntimeSettings):
        self.settings = settings
        self.attachments: Optional[SessionAttachmentManager] = None
        self._prewarmed_agy: Optional[WarmAntigravityProcess] = None
        self._warm_agy_pool: Dict[Tuple[str, str], WarmAntigravityProcess] = {}
        self._codex_threads: Dict[Tuple[str, str], str] = {}
        self._last_seen_msg_idx: Dict[Tuple[str, str], int] = {}
        self._last_persona_by_seat: Dict[Tuple[str, str], str] = {}
        self._injected_refs: Dict[Tuple[str, str], Set[str]] = {}
        self._binary_semaphores: Dict[Tuple[str, int], asyncio.Semaphore] = {}
        self._active_raw_procs: Dict[Tuple[str, str], Set[asyncio.subprocess.Process]] = {}
        self._active_supervised_handles: Dict[Tuple[str, str], Set[SupervisedProcessHandle]] = {}

    def _get_attachment_manager(self) -> SessionAttachmentManager:
        if self.attachments is None:
            self.attachments = SessionAttachmentManager()
        return self.attachments

    def _get_binary_semaphore(self, binary_path: str, stateless_shared: bool = False) -> asyncio.Semaphore:
        real_key = os.path.realpath(binary_path) if (binary_path and "://" not in binary_path and os.path.lexists(binary_path)) else binary_path
        cap = (
            max(1, min(6, int(getattr(self.settings, "single_cli_concurrency", 3) or 3)))
            if stateless_shared
            else 4
        )
        key = (real_key, cap)
        sem = self._binary_semaphores.get(key)
        if sem is None:
            sem = asyncio.Semaphore(cap)
            self._binary_semaphores[key] = sem
        return sem

    @staticmethod
    def _prepare_isolated_call_env(session_id: str, agent_id: str) -> Tuple[Dict[str, str], str]:
        """为单 CLI 多路并发调用构造独立临时运行目录（隔离 TMPDIR/锁文件，同时保留用户登录态 HOME）。"""
        env = build_host_env()
        iso_root = os.path.join(os.path.expanduser(os.environ.get("AI_ROUNDTABLE_HOME") or "~/.ai-roundtable"), "tmp_runs")
        os.makedirs(iso_root, exist_ok=True)
        call_tmp = tempfile.mkdtemp(prefix=f"{session_id}_{agent_id}_", dir=iso_root)
        env["TMPDIR"] = call_tmp
        env["TEMP"] = call_tmp
        env["TMP"] = call_tmp
        env["AI_ROUNDTABLE_SEAT_ID"] = agent_id
        return env, call_tmp

    @staticmethod
    def _cleanup_isolated_call_tmp(call_tmp: str) -> None:
        if call_tmp and os.path.isdir(call_tmp):
            shutil.rmtree(call_tmp, ignore_errors=True)

    def _register_raw_proc(self, seat_key: Tuple[str, str], proc: asyncio.subprocess.Process) -> None:
        self._active_raw_procs.setdefault(seat_key, set()).add(proc)

    def _unregister_raw_proc(self, seat_key: Tuple[str, str], proc: asyncio.subprocess.Process) -> None:
        bucket = self._active_raw_procs.get(seat_key)
        if bucket is not None:
            bucket.discard(proc)
            if not bucket:
                self._active_raw_procs.pop(seat_key, None)

    async def prewarm(self) -> None:
        """服务启动后异步预热 1 个空闲 Antigravity 常驻流，供首个匹配席位零延迟认领。"""
        try:
            cfg = self.settings.agents.get("carbon")
            if not cfg:
                return
            bpath, _, help_text, eff_drv, is_fb = cfg.get_probe_info(
                allow_single_cli_fallback=self.settings.allow_single_cli_fallback
            )
            if eff_drv != "agy" or not bpath or "--input-format" not in help_text:
                return
            if self._prewarmed_agy and self._prewarmed_agy.proc and self._prewarmed_agy.proc.returncode is None:
                return
            eff_model = resolve_effective_model_for_driver("agy", cfg.model, is_shared_fb=is_fb)
            effort_spec = get_model_effort_spec("agy", model=eff_model, help_text=help_text)
            bound_ws, real_ws = is_real_bound_workspace(self.settings.workspace_dir)
            prewarm_cwd = real_ws if bound_ws else self._discussion_sandbox_cwd()
            prewarm_eff = WarmAntigravityProcess.normalize_agy_effort(
                cfg.discussion_effort,
                help_text=help_text,
                model=eff_model,
            )
            self._prewarmed_agy = WarmAntigravityProcess(
                binary_path=bpath,
                model=eff_model,
                effort=prewarm_eff,
                cwd=prewarm_cwd,
                session_id="",
                seat_id="",
                disable_slash="--disable-slash-commands" in help_text,
                supports_effort=("--effort" in help_text) and effort_spec.get("supports_effort", True),
                sandbox=True,
                help_text=help_text,
            )
            await self._prewarmed_agy.ensure_started()
        except Exception:
            pass

    async def reset_session_context(self, session_id: str) -> None:
        for key in [k for k in self._codex_threads if k[0] == session_id]:
            self._codex_threads.pop(key, None)
        for key in [k for k in self._last_seen_msg_idx if k[0] == session_id]:
            self._last_seen_msg_idx.pop(key, None)
        for key in [k for k in self._last_persona_by_seat if k[0] == session_id]:
            self._last_persona_by_seat.pop(key, None)
        for key in [k for k in self._injected_refs if k[0] == session_id]:
            self._injected_refs.pop(key, None)
        for key in [k for k in self._warm_agy_pool if k[0] == session_id]:
            proc = self._warm_agy_pool.pop(key, None)
            if proc:
                await proc.close()

    async def cancel_seat_active_stream(self, session_id: str, agent_id: str) -> None:
        """单席跳过本轮时立即终止该席位的常驻流与一次性 CLI 子进程组，释放信号量，绝不阻塞其余席位。"""
        seat_key = (session_id, agent_id)
        proc = self._warm_agy_pool.pop(seat_key, None)
        if proc:
            await proc.close()
        raw_set = self._active_raw_procs.pop(seat_key, None)
        if raw_set:
            for rproc in list(raw_set):
                _safe_terminate_proc(rproc)

    async def shutdown(self) -> None:
        if self._prewarmed_agy:
            await self._prewarmed_agy.close()
            self._prewarmed_agy = None
        for proc in list(self._warm_agy_pool.values()):
            await proc.close()
        self._warm_agy_pool.clear()
        for raw_set in list(self._active_raw_procs.values()):
            for rproc in list(raw_set):
                _safe_terminate_proc(rproc)
        self._active_raw_procs.clear()

    @staticmethod
    def _discussion_sandbox_cwd() -> str:
        discuss_dir = os.path.join(os.path.expanduser(os.environ.get("AI_ROUNDTABLE_HOME") or "~/.ai-roundtable"), "discuss_sandbox")
        try:
            os.makedirs(discuss_dir, exist_ok=True)
            return discuss_dir
        except Exception:
            return tempfile.gettempdir()

    def _effective_workspace_cwd(self, session_workspace: str = "") -> str:
        raw = session_workspace.strip() if session_workspace else self.settings.workspace_dir
        bound, real_ws = is_real_bound_workspace(raw)
        if bound and real_ws and os.path.isdir(real_ws):
            return os.path.realpath(real_ws)
        safe_ws = os.path.join(os.path.expanduser(os.environ.get("AI_ROUNDTABLE_HOME") or "~/.ai-roundtable"), "workspace")
        try:
            os.makedirs(safe_ws, exist_ok=True)
            return os.path.realpath(safe_ws)
        except Exception:
            return os.path.realpath(tempfile.gettempdir())

    def _require_binary(
        self,
        agent_id: str,
        override: Optional[dict] = None,
    ) -> Tuple[AgentRoleConfig, str, str, str, bool]:
        base_cfg = self.settings.agents[agent_id]
        if isinstance(override, dict) and override:
            drv = str(override.get("driver", base_cfg.driver) or base_cfg.driver).strip().lower()
            if drv not in VALID_DRIVERS:
                drv = base_cfg.driver
            custom_bin = (
                str(override.get("custom_binary", base_cfg.custom_binary) or "").strip()
                if "custom_binary" in override
                else base_cfg.custom_binary
            )
            model_val = (
                str(override.get("model", base_cfg.model) or "").strip()
                if "model" in override
                else base_cfg.model
            )
            if "discussion_effort" in override:
                disc_eff = str(override.get("discussion_effort") or "").strip().lower()
            elif "effort" in override:
                disc_eff = str(override.get("effort") or "").strip().lower()
            else:
                disc_eff = base_cfg.discussion_effort
            exec_eff = (
                str(override.get("execution_effort") or "").strip().lower()
                if "execution_effort" in override
                else base_cfg.execution_effort
            )
            persona_val = str(override.get("persona", base_cfg.persona) or base_cfg.persona).strip()
            lock_eff = (
                bool(override.get("lock_discussion_effort"))
                if "lock_discussion_effort" in override
                else base_cfg.lock_discussion_effort
            )
            cfg = AgentRoleConfig(
                agent_id=base_cfg.agent_id,
                name=base_cfg.name,
                title=base_cfg.title,
                cli_name=base_cfg.cli_name,
                binary_candidates=list(base_cfg.binary_candidates),
                fallback_paths=list(base_cfg.fallback_paths),
                driver=drv,
                persona=persona_val if persona_val in PERSONA_PRESETS else base_cfg.persona,
                custom_name=base_cfg.custom_name,
                custom_binary=custom_bin,
                model=model_val,
                discussion_effort=disc_eff,
                execution_effort=exec_eff,
                lock_discussion_effort=lock_eff,
            )
        else:
            cfg = base_cfg

        bpath, _, help_text, eff_drv, is_fb = cfg.get_probe_info(
            allow_single_cli_fallback=self.settings.allow_single_cli_fallback
        )
        if not bpath:
            spec = DRIVER_SPECS[cfg.preferred_driver_key()]
            cands = " / ".join(spec["binary_candidates"])
            raise CLIInvocationError(
                f"未检测到 {spec['cli_name']} 可执行文件（查找命令：{cands}）。请确认已在终端安装，或在「设置」中指定路径或启用「单引擎多角色串行模式」。",
                error_kind="binary_missing",
                driver=cfg.preferred_driver_key(),
                model=cfg.model,
                effort=cfg.discussion_effort,
            )
        return cfg, bpath, help_text, eff_drv, is_fb

    @staticmethod
    def _build_fallback_attempts(
        driver_key: str,
        model: str,
        effort: str,
        help_text: str = "",
    ) -> List[Tuple[str, str]]:
        eff_model = resolve_effective_model_for_driver(driver_key, model, is_shared_fb=False)
        norm_e = normalize_model_effort(
            driver_key,
            model=eff_model,
            effort=effort,
            help_text=help_text,
        )
        attempts: List[Tuple[str, str]] = []

        def _add(cand_m: str, cand_e: str) -> None:
            pair = (cand_m, cand_e)
            if pair not in attempts:
                attempts.append(pair)

        _add(eff_model, norm_e)
        spec = get_model_effort_spec(driver_key, model=eff_model, help_text=help_text)
        allowed = spec["allowed"]
        if spec.get("supports_effort", True) and allowed and norm_e in allowed:
            cur_idx = allowed.index(norm_e)
            if cur_idx > 0 and norm_e not in ("low", "medium", "high"):
                # 若高档位偶发受限，同模型平滑降一档重试，绝不伪造不存在的模型名
                step_down = "high" if "high" in allowed else allowed[cur_idx - 1]
                _add(eff_model, step_down)

        default_m = DRIVER_SPECS.get(driver_key, DRIVER_SPECS["agy"])["default_model"]
        if eff_model == default_m and driver_key == "agy":
            _add("gemini-4-argon", normalize_model_effort("agy", model="gemini-4-argon", effort=norm_e or "high", help_text=help_text))
        elif eff_model == default_m and driver_key == "codex":
            _add("gpt-6.1-sol", normalize_model_effort("codex", model="gpt-6.1-sol", effort=norm_e or "xhigh", help_text=help_text))

        return attempts

    def _has_active_session_memory(self, session_id: str, agent_id: str, eff_drv: str) -> bool:
        seat_key = (session_id, agent_id)
        if eff_drv == "agy":
            w = self._warm_agy_pool.get(seat_key)
            return bool(w and w.proc and w.proc.returncode is None and w.turn_count > 0)
        if eff_drv == "codex":
            return seat_key in self._codex_threads
        return False

    @staticmethod
    def _format_transcript_within_budget(
        messages: List[Dict[str, str]],
        max_messages: int = 80,
        max_chars: int = 140000,
    ) -> str:
        if not messages:
            return ""
        sliced = messages[-max_messages:]
        lines: List[str] = []
        used = 0
        for m in reversed(sliced):
            entry = f"- {m['speaker']}: {m['content']}"
            if used + len(entry) > max_chars and lines:
                lines.append("- [系统提示：更早期历史已收敛至白板要点]")
                break
            lines.append(entry)
            used += len(entry) + 1
        lines.reverse()
        return "\n".join(lines)

    @staticmethod
    def _format_whiteboard_for_prompt(whiteboard: dict, seat_names: Optional[Dict[str, str]] = None) -> str:
        """拼装三区结构化白板与负面防回流清单上下文摘要，支持 1~6 席动态成员称呼映射。"""
        dyn = seat_names or {}
        seat_labels = {
            aid: dyn.get(aid) or IMMUTABLE_SEAT_CATALOG[aid]["default_name"]
            for aid in ALL_SEAT_IDS
        }
        seat_labels["chair"] = "主持"
        seat_labels["system"] = "系统"

        chair_constraints = [
            str(x).strip()
            for x in (whiteboard.get("chair_constraints") or [])
            if str(x).strip()
        ]
        abandoned_raw = whiteboard.get("abandoned_proposals") or []
        abandoned_lines: List[str] = []
        for ab_it in abandoned_raw[:16]:
            if isinstance(ab_it, dict):
                ab_txt = str(ab_it.get("text") or "").strip()
                ab_reason = str(ab_it.get("reason") or "").strip()
                if ab_txt:
                    abandoned_lines.append(f"  · [已淘汰] {ab_txt}" + (f"（原因：{ab_reason}）" if ab_reason else ""))
            elif isinstance(ab_it, str) and ab_it.strip():
                abandoned_lines.append(f"  · [已淘汰] {ab_it.strip()}")

        raw_items = whiteboard.get("items")
        if isinstance(raw_items, list) and (raw_items or chair_constraints or abandoned_lines):
            decision_lines: List[str] = []
            seen_dec: Set[str] = set()
            for c_txt in chair_constraints[:16]:
                norm_c = re.sub(r"\W+", "", c_txt.lower())
                if norm_c and norm_c not in seen_dec:
                    seen_dec.add(norm_c)
                    decision_lines.append(f"  · [主持硬约束] {c_txt}")

            risk_lines: List[str] = []
            action_lines: List[str] = []
            ordered_items = [
                it for it in raw_items if isinstance(it, dict) and it.get("pinned")
            ] + [
                it for it in raw_items if isinstance(it, dict) and not it.get("pinned")
            ]
            for it in ordered_items:
                txt = str(it.get("text") or "").strip()
                if not txt:
                    continue
                author = str(it.get("author") or it.get("source_seat") or "").lower()
                src = seat_labels.get(author, "白板")
                origin_tier = str(it.get("origin_tier") or "").strip()
                if origin_tier == "chair_directive" and author != "chair":
                    src = f"主持指定·{src}"
                kind = str(it.get("kind") or "").lower()
                if not kind:
                    if it.get("adopted") or it.get("pinned") or it.get("bucket") in ("chair_constraints", "carbon_plan"):
                        kind = "decision"
                    elif it.get("bucket") == "grok_risks":
                        kind = "risk"
                    else:
                        kind = "action"

                if kind == "decision":
                    norm_d = re.sub(r"\W+", "", txt.lower())
                    if norm_d and norm_d not in seen_dec:
                        seen_dec.add(norm_d)
                        decision_lines.append(f"  · [{src}] {txt}")
                elif kind == "risk":
                    risk_lines.append(f"  · [{src}] {txt}")
                elif kind == "action":
                    chk = "✓" if it.get("checked", False) else "○"
                    action_lines.append(f"  · [{chk}·{src}] {txt}")

            sections: List[str] = []
            if decision_lines:
                sections.append(
                    "【已锁定会议共识与硬约束（后续分析须严格遵循）】：\n" + "\n".join(decision_lines[:32])
                )
            if abandoned_lines:
                sections.append(
                    "【已确认放弃/证伪淘汰的差方案（严禁回流复用）】：\n" + "\n".join(abandoned_lines[:16])
                )
            if risk_lines:
                sections.append("【待决争议与风险项】：\n" + "\n".join(risk_lines[:16]))
            if action_lines:
                sections.append("【待执行任务清单草稿】：\n" + "\n".join(action_lines[:16]))
            return ("\n" + "\n".join(sections)) if sections else ""

        wb_digest_parts: List[str] = []
        if chair_constraints:
            wb_digest_parts.append(
                "【已锁定会议共识与硬约束（后续分析须严格遵循）】：\n"
                + "\n".join(f"  · [主持] {c}" for c in chair_constraints[:16])
            )
        if abandoned_lines:
            wb_digest_parts.append(
                "【已确认放弃/证伪淘汰的差方案（严禁回流复用）】：\n" + "\n".join(abandoned_lines[:16])
            )
        legacy_lines: List[str] = []
        for wb_label, wb_key in (
            ("已确认共识", "carbon_plan"),
            ("争议与风险", "grok_risks"),
            ("待执行任务", "astra_actions"),
        ):
            pts = whiteboard.get(wb_key) or []
            if pts:
                legacy_lines.append(f"  · {wb_label}：{'；'.join(pts[-8:])}")
        if legacy_lines:
            wb_digest_parts.append("【当前白板沉淀要点】：\n" + "\n".join(legacy_lines))
        return ("\n" + "\n".join(wb_digest_parts)) if wb_digest_parts else ""

    @classmethod
    def _build_prompt(
        cls,
        agent_id: str,
        stage: str,
        topic: str,
        collab_mode: str,
        whiteboard: dict,
        recent_messages: List[Dict[str, str]],
        cue_instruction: str = "",
        incremental_only: bool = False,
        workspace_snapshot: str = "",
        persona_key: str = "",
        is_solo_mode: bool = False,
        extra_ref_block: str = "",
        shared_cli_roster: str = "",
        collab_mode_key: str = "",
        seat_names_map: Optional[Dict[str, str]] = None,
    ) -> str:
        seat_names = {
            aid: (seat_names_map or {}).get(aid) or IMMUTABLE_SEAT_CATALOG[aid]["default_name"]
            for aid in ALL_SEAT_IDS
        }
        seat_display = seat_names.get(agent_id, agent_id.capitalize())
        pspec = get_persona_spec(persona_key, fallback_agent_id=agent_id)
        role_header = f"你是圆桌席位中的 {seat_display}，当前担任【{pspec['label']}】。{pspec['prompt']}"
        if is_solo_mode:
            role_header += (
                "（当前为单席专注模式：由你独立负责架构设计、边界自检与实施方案收敛，无需点名其他席位，请给出结构严谨、可直接执行的完整结论。）"
            )
        elif shared_cli_roster:
            role_header += (
                f"\n【单引擎多席位并行正交扮演铁律（严禁同源模型自我附和，必须彻底锁定本席专属专业视角独立交锋）】：本场会议由同一底层引擎无状态分次承担多个角色（参会阵容：{shared_cli_roster}）。"
                f"你本轮仅代表【{seat_display} · {pspec['label']}】，严禁复述前序席位原话或客套附和（禁止出现“同意/赞同/说得好/整体可行/补充一点”），"
                "必须独立输出当前角色职责视角的实质判断、风险审计或具体工程方案！"
            )

        is_code_review = collab_mode_key == "code_review" or ("代码审查" in collab_mode)
        is_rapid = collab_mode_key == "rapid_consensus" or ("快速合议" in collab_mode)
        if is_code_review:
            role_header += (
                "\n【代码审查铁律（基于源码证据立论）】：所有分析必须明确指出项目中的具体文件路径、函数/类名、状态流转或接口字段，严禁脱离源码空谈泛化原则！"
            )

        constraints = "；".join(whiteboard.get("chair_constraints", [])) or "无"
        wb_digest = cls._format_whiteboard_for_prompt(whiteboard, seat_names=seat_names)
        quality_constraint = (
            "请简明分点直出关键要点、核心风险与明确动作；严禁客套寒暄与无效复述，确保每条具备实质信息增量"
            if is_rapid and stage != "synthesis"
            else "篇幅按问题复杂度自然展开，允许输出完整推演链条、反例分析、接口契约或对比表格；严禁客套寒暄与无效复述，确保每段具备实质信息增量"
        )

        # 旗舰级全量防遗漏 + 废案强隔离决议合成通道：永远使用完整讨论档案与全量消息，绝不走增量截断
        if stage == "synthesis":
            artifact_type = str(whiteboard.get("artifact_type") or "code_patch").strip().lower()
            sec4_heading = {
                "code_patch": "## 四、文件级待执行任务清单（明确模块路径、改动职责与回归验收标准）",
                "decision_matrix": "## 四、方案对比决策矩阵与落地行动清单（明确选型结论、触发条件与执行动作）",
                "ux_checklist": "## 四、产品体验分级走查与打磨清单（明确交互节点、预期体感与验收标准）",
                "doc_export": "## 四、根因排查闭环与结构化定稿清单（明确核验步骤、定稿口径与交付动作）",
            }.get(artifact_type, "## 四、待执行交付任务清单（明确改动职责与验收标准）")
            epistemic_badge = str(whiteboard.get("epistemic_badge") or "").strip()
            epistemic_rule = (
                f"\n【认知防伪披露硬约束】：当前会话独立性状态为 `{epistemic_badge}`；若处于同源模型或单席模式，正文中严禁出现“多 AI 独立交叉验证共识”字样，须如实保留该认知标记。"
                if epistemic_badge and ("同源" in epistemic_badge or "单席" in epistemic_badge)
                else ""
            )
            dossier_block = str(whiteboard.get("_synthesis_dossier_block") or "").strip()
            dossier_section = f"\n{dossier_block}\n" if dossier_block else ""
            synth_instruction = cue_instruction or (
                "请基于全轮次会议讨论、演进定论账本与主持约束，输出一份【零成果遗漏、零废案回流】的旗舰级《会议最终决议》"
            )
            synth_tail = (
                f"只读汇总严禁调用工具修改磁盘文件，严禁调用任何 shell 命令或脚本统计字数；{quality_constraint}。{epistemic_rule}\n"
                "【决议合成铁律（必须 100% 遵守）】：\n"
                "1. 全量保留不遗漏：主持人的初始硬约束、历次插话追问要求、各轮经质询后达成或修订成熟的方案细节、量化阈值与接口契约必须完整纳入第一节与第四节，严禁概括丢失关键参数！\n"
                "2. 废案显式剥离防回流：凡在讨论中已被反驳证伪、席位主动声明放弃（[放弃原方案]）、被修订方案取代（[修正原方案] 之前的旧草案）或被主持人否决的差方案，严禁混入第一节『已确认共识』或第四节『待执行任务』，必须单独归档至第二节『已确认放弃与证伪淘汰方案』并注明淘汰理由！\n"
                f"3. 请严格按以下四节一级结构输出：\n"
                "   - `## 一、已确认共识与全量采纳成果`\n"
                "   - `## 二、已确认放弃与证伪淘汰方案（防回流负面清单）`\n"
                "   - `## 三、边界风险防线、未决争议与参会披露`\n"
                f"   - `{sec4_heading}`\n"
                "末尾必须独立换行附带两行结构化标记（禁止省略）：\n"
                "[白板: 共识=核心采纳裁定结论（多条以分号分隔） | 弃案=已确认放弃或淘汰的旧方案（多条以分号分隔，无则填无） | 风险=关键边界防线（多条以分号分隔） | 任务=具体待执行动作（多条以分号分隔）]\n"
                "[状态: 决议已成 | 共识: 已达成 | 点名: 无]"
            )
            transcript = cls._format_transcript_within_budget(recent_messages, max_messages=240, max_chars=180000) or "（暂无前序发言）"
            ws_block = f"{workspace_snapshot}\n\n" if workspace_snapshot else ""
            ref_section = f"{extra_ref_block}\n\n" if extra_ref_block else ""
            return (
                f"{role_header}\n"
                f"【当前环节：形成会议最终决议（全量成果收敛 + 废案剥离）】{synth_instruction}\n"
                f"【讨论策略】：{collab_mode}\n"
                f"【议题】：{topic}\n"
                f"【主持要求】：{constraints}"
                f"{wb_digest}"
                f"{dossier_section}\n"
                f"{ws_block}"
                f"{ref_section}"
                f"【会议完整全轮次讨论记录】：\n{transcript}\n\n"
                f"要求：{synth_tail}"
            )

        cue_note = f"（专项指引：{cue_instruction}）" if cue_instruction and stage != "cue" else ""
        stance_protocol_hint = (
            "为便于分歧追踪与淘汰废案识别，请在对应段落开头按需附带显式立场锚点："
            "质疑他席写 `[反驳 @席位名：核心分歧]`；吸收质疑修正自身前序方案写 `[修正原方案：原设计 -> 新设计]`；"
            "明确撤回或淘汰劣势方案写 `[放弃原方案：被弃方案及原因]`；确认无实质分歧写 `[无异议]`。"
        )
        stage_desc_map = {
            "opening": (
                f"【当前环节：单席深度方案设计】请立足【{pspec['label']}】视角，针对议题输出完整的「核心方案主张 + 关键接口/状态设计 + 分阶段实施路径」。{cue_note}"
                if is_solo_mode
                else (
                    f"【当前环节：独立立论（首轮盲评隔离）】请立足【{pspec['label']}】视角独立破题，明确给出：「1. 核心方案主张；2. 成立前提假设；3. 关键实现路径与边界约束」。"
                    f"严禁客套寒暄或猜测迎合他人观点。{cue_note}"
                )
            ),
            "solo_audit": (
                f"【当前环节：单席边界自检与执行清单收敛】请对你刚提出的初版方案进行严苛反向自检："
                f"1) 排查隐含假设漏洞、异常/并发回退边界；2) 修正设计瑕疵（若有淘汰初版设计请标注 `[放弃原方案：...]`）并收敛可直接勾选交付的待执行任务清单。{cue_note}"
            ),
            "cross_talk": (
                f"【当前环节：交叉质询（证伪与边界审计协议）】严禁出现“同意/赞同/说得好/整体可行/补充一点”等附和套话，禁止复述已达成观点！"
                f"必须严格执行：1) 对存在分歧的设计列出 `方案 A vs 方案 B` 的工程代价对比与具体失效反例；"
                f"2) 对已达成共识的模块补充极端异常边界或量化验收条件；"
                f"3) {stance_protocol_hint}{cue_note}"
            ),
            "rebuttal": (
                f"【当前环节：定向答辩】你在上一轮交叉质询中被点名质询{cue_note}。"
                f"请直面质询焦点：对指出的真实漏洞直接吸收并标注 `[修正原方案：...]` 或 `[放弃原方案：...]` 给出修正后的契约；对不成立的质疑给出具体技术依据正面反驳，严禁回避核心问题。"
            ),
            "lead_synthesis": (
                f"【当前环节：架构裁定】请作为本场主控收敛席，综合前序独立立论、交叉质询与定向答辩结果，"
                f"输出《分歧裁定与阶段推进方案》：明确各项争议的最终采纳结论、已淘汰废案（标注 `[放弃原方案：...]`）、风险防线与分阶段实施任务。{cue_note}"
            ),
            "adv_propose": (
                f"【当前环节：正反辩证 · 主方案立论】你担任本场正方主方案席，请针对议题先行独立输出一份结构完整、细节扎实的主推荐方案"
                f"（涵盖核心架构选型、数据流/接口契约、关键实现路径与预期工程收益）。{cue_note}"
            ),
            "adv_attack": (
                f"【当前环节：正反辩证 · 反向压力审计】你担任本场反向压力审计席，请针对正方主方案执行破坏性压力测试："
                f"1) 拆穿方案中的隐含错误假设；2) 指出极端负载、异常输入或并发竞态下的具体失效点；"
                f"3) 明确提出至少一条可行的替代路线并对比工程代价。{stance_protocol_hint}{cue_note}"
            ),
            "adv_defend": (
                f"【当前环节：正反辩证 · 防御修正】请针对反向压力审计指出的各项实质风险与替代路线正面答辩："
                f"对确有隐患的环节标注 `[修正原方案：...]` 或 `[放弃原方案：...]` 直接修订原方案架构与状态边界；对不合理的质疑给出量化成本或源码级反驳。{cue_note}"
            ),
            "adv_verdict": (
                f"【当前环节：正反辩证 · 综合裁定】请站在终审裁定席视角，权衡正方主方案、反向压力审计与防御修正，"
                f"给出最终权衡裁定、明确淘汰的次优/高危方案（标注 `[放弃原方案：...]`）、必须固化的安全护栏以及清晰的执行边界。{cue_note}"
            ),
            "div_expand": (
                f"【当前环节：发散收敛 · 多维方案发散】本轮严禁过早自我否定或保守趋同！"
                f"请严格聚焦分配给你的正交探索维度{cue_note}，尽可能打开解空间，给出逻辑自洽、特色鲜明的完整设计方案与代表性实现方式。"
            ),
            "div_evaluate": (
                f"【当前环节：发散收敛 · 可行性与成本评估】请按照「用户感知价值 × 实现复杂度 × 维护风险」三维评估矩阵，"
                f"横向对比第 1 轮各维度的发散方案（可输出对比表格），明确指出应淘汰的次优项（标注 `[放弃原方案：...]`）及优选项的改造代价。{cue_note}"
            ),
            "div_converge": (
                f"【当前环节：发散收敛 · 优选方案收敛】请基于「用户感知价值 × 实现复杂度 × 维护风险」三维矩阵完成终局收敛，"
                f"明确剥离淘汰的次优方案（标注 `[放弃原方案：...]`），输出唯一推荐的实施路径、保留约束与分步落地清单。{cue_note}"
            ),
            "cr_locate": (
                f"【当前环节：代码审查 · 源码证据定位】请严格基于源码证据独立定位问题根因、架构耦合点或潜在缺陷，"
                f"逐项指明具体文件路径、函数/类名、关键变量或状态流转链路，严禁脱离代码空谈。{cue_note}"
            ),
            "cr_verify": (
                f"【当前环节：代码审查 · 调用链交叉核验】请交叉核验前序席位定位的源码证据，检查上下游调用链影响面、"
                f"跨模块状态同步与潜在回归风险，指出遗漏的文件/函数或偏差归因。{stance_protocol_hint}{cue_note}"
            ),
            "cr_plan": (
                f"【当前环节：代码审查 · 文件级修改方案】请汇总源码证据与调用链核验结论，剥离误判或高风险修补草案，输出精确到"
                f"「文件路径 → 函数/类名 → 具体修改逻辑 → 验证命令」的文件级修改方案。{cue_note}"
            ),
            "rapid_open": (
                f"【当前环节：快速合议 · 单轮要点直出】请立足【{pspec['label']}】职责，简明分点直出核心改造要点与不可突破的底线风险。{cue_note}"
            ),
            "rapid_align": (
                f"【当前环节：快速合议 · 生成执行清单】请快速核对各席核心要点与底线风险，剔除冲突劣势做法，去重整合为清晰可勾选执行的任务清单与硬约束。{cue_note}"
            ),
            "redebate": (
                f"【当前环节：双席定向再辩（1 轮焦点交锋）】请严格围绕指定争议焦点正面交锋，禁止泛化发散！"
                f"给出明确的技术判据、修正契约（`[修正原方案：...]` / `[放弃原方案：...]`）或量化取舍结论。{cue_note}"
            ),
            "interrupt_reply": f"【当前环节：响应主持人追问与约束】请针对主持人最新指示输出增量调整、边界防线或深化设计（若推翻旧方案请标注 `[放弃原方案：...]`），禁止复述旧话。{cue_note}",
            "cue": f"【当前环节：主持人定向提问】具体问题：{cue_instruction}",
        }
        stage_desc = stage_desc_map.get(stage, f"【当前环节：会议研讨】{cue_note}")

        mention_cands = "或".join(f"@{seat_names[a]}" for a in ("carbon", "grok", "astra"))
        mention_hint = "无" if is_solo_mode else f"{mention_cands}或无"
        tail_rule = (
            f"{quality_constraint}；"
            "圆桌讨论阶段仅允许按需精准只读源码（已提供源码或索引骨架的文件请勿全量重复读取；单轮只读查看收敛在 1–3 处最关键代码段以内，禁止全仓遍历扫盘），严禁修改任何磁盘文件，"
            "严禁调用任何 shell 命令、脚本或工具去统计字数、计算篇幅或自我删改截断！"
            "正文中严禁输出“我先只读某文件/我先核对源码路径/不改任何文件”等工具探索独白，直接输出正式分析结论。\n"
            "末尾请独立换行附带两行结构化标记（独立提取，不挤压正文分析深度）：\n"
            "[白板: 共识=已确认共识或约束 | 弃案=本轮确认放弃或证伪的方案（无则填无） | 风险=待决争议或风险项 | 任务=具体待执行任务（按需填写1至3项）]\n"
            f"[状态: 核心立场摘要 | 共识: 已达成或需继续 | 点名: {mention_hint}]"
        )

        if incremental_only and recent_messages:
            delta_lines = cls._format_transcript_within_budget(recent_messages, max_messages=30, max_chars=70000)
            ref_section = f"\n{extra_ref_block}\n" if extra_ref_block else ""
            return (
                f"【你当前角色】：{seat_display} · {pspec['label']}\n"
                f"{stage_desc}\n"
                f"【最新主持约束】：{constraints}"
                f"{wb_digest}"
                f"{ref_section}\n"
                f"【上一轮新增发言】：\n{delta_lines}\n\n"
                f"请严格站在【{pspec['label']}】职责立场回应（{tail_rule}）"
            )

        transcript = cls._format_transcript_within_budget(recent_messages) or (
            "（当前为单席首轮方案设计）" if is_solo_mode else "（当前为首轮独立立论，尚无他人发言）"
        )
        ws_block = f"{workspace_snapshot}\n\n" if workspace_snapshot else ""
        return (
            f"{role_header}\n"
            f"{stage_desc}\n"
            f"【讨论策略】：{collab_mode}\n"
            f"【议题】：{topic}\n"
            f"【主持要求】：{constraints}"
            f"{wb_digest}\n\n"
            f"{ws_block}"
            f"【会议讨论记录】：\n{transcript}\n\n"
            f"要求：{tail_rule}"
        )

    @classmethod
    def parse_structured_tail_with_kinds(
        cls,
        full_text: str,
        seat_names: Optional[Dict[str, str]] = None,
    ) -> Tuple[str, str, Optional[str], List[dict], Optional[bool]]:
        """
        独立解析末尾 [白板: 共识=... | 风险=... | 任务=...]（兼容旧版 [白板: 要点1；要点2]）
        与 [状态: ... | 共识: ... | 点名: ...] 结构化标记。
        返回 (clean_body, badge, target, wb_typed_items, consensus_reached)，
        其中 wb_typed_items 每项为 {"kind": "decision"|"risk"|"action"|None, "text": "..."}。
        """
        raw_clean = re.sub(r"(?:\r?\n)*Finishing session[….]*\s*$", "", (full_text or "").strip())
        working = raw_clean.strip()
        wb_typed_items: List[dict] = []
        consensus_reached: Optional[bool] = None
        badge = "发言完成"
        target: Optional[str] = None

        alias_to_aid: Dict[str, str] = {
            "carbon": "carbon",
            "grok": "grok",
            "astra": "astra",
            "vega": "vega",
            "titan": "titan",
            "prism": "prism",
            "架构师": "carbon",
            "审计官": "grok",
            "工程师": "astra",
            "交互设计": "vega",
            "性能专家": "titan",
            "质量验证": "prism",
            "alpha": "carbon",
            "beta": "grok",
            "gamma": "astra",
            "产品总监": "carbon",
            "红队审计": "grok",
            "研发主程": "astra",
        }
        if isinstance(seat_names, dict):
            for k_aid, disp_n in seat_names.items():
                if k_aid in ALL_SEAT_IDS and disp_n and str(disp_n).strip():
                    alias_to_aid[str(disp_n).strip().lower()] = k_aid

        status_pat = re.compile(
            r"\[(?:状态|徽章)[:：]\s*([^\]|｜]+?)"
            r"(?:\s*[|｜]\s*共识[:：]\s*([^\]|｜]+?))?"
            r"(?:\s*[|｜]\s*点名[:：]\s*@?([A-Za-z0-9_·\-\u4e00-\u9fa5]+))?\s*\]\s*$"
        )
        wb_pat = re.compile(r"\[白板(?:要点)?[:：]\s*([^\]]+)\]\s*$")
        wb_block_pat = re.compile(r"(?:^|\n)\[白板(?:要点)?\]\s*:?\s*\n((?:\s*(?:[-*•]|\d+[.)、])\s*.+(?:\n|$))+)\s*$")
        kind_prefix_pat = re.compile(
            r"^(共识|决策|约束|结论|弃案|淘汰|废弃|放弃|否决|风险|争议|审计|隐患|边界|任务|行动|动作|执行|实施|待办|清单)\s*[=:：]\s*(.+)$"
        )
        placeholder_vals = {"无", "暂无", "待补充", "略", "可选", "none", "n/a", "..."}

        def _kw_to_kind(kw_s: str) -> str:
            if kw_s in ("共识", "决策", "约束", "结论"):
                return "decision"
            if kw_s in ("弃案", "淘汰", "废弃", "放弃", "否决"):
                return "abandoned"
            if kw_s in ("风险", "争议", "审计", "隐患", "边界"):
                return "risk"
            return "action"

        for _ in range(3):
            m_status = status_pat.search(working)
            if m_status:
                candidate_body = working[: m_status.start()].strip()
                if candidate_body:
                    working = candidate_body
                badge = m_status.group(1).strip()[:16] or "发言完成"
                raw_cons = (m_status.group(2) or "").strip()
                if raw_cons:
                    if any(k in raw_cons for k in ("已达成", "达成", "同意", "通过", "一致")):
                        consensus_reached = True
                    elif any(k in raw_cons for k in ("需继续", "分歧", "存疑", "未达成", "继续")):
                        consensus_reached = False
                raw_target = (m_status.group(3) or "").strip().lower()
                target = alias_to_aid.get(raw_target)
                continue

            m_wb = wb_pat.search(working)
            if m_wb:
                candidate_body = working[: m_wb.start()].strip()
                if candidate_body:
                    working = candidate_body
                pipe_segments = re.split(r"[｜|\n]+", m_wb.group(1))
                for seg in pipe_segments:
                    seg_s = seg.strip()
                    if not seg_s:
                        continue
                    m_kp = kind_prefix_pat.match(seg_s)
                    seg_kind: Optional[str] = None
                    rhs = seg_s
                    if m_kp:
                        seg_kind = _kw_to_kind(m_kp.group(1))
                        rhs = m_kp.group(2).strip()
                    for sub in re.split(r"[；;]+", rhs):
                        sub_s = re.sub(r"^(?:\d+[.)、]|[-*•])\s*", "", sub.strip())
                        m_inner = kind_prefix_pat.match(sub_s)
                        item_kind = seg_kind
                        if m_inner:
                            item_kind = _kw_to_kind(m_inner.group(1))
                            sub_s = m_inner.group(2).strip()
                        if len(sub_s) >= 4 and sub_s.lower() not in placeholder_vals:
                            wb_typed_items.append({"kind": item_kind, "text": sub_s[:180]})
                continue

            m_wb_blk = wb_block_pat.search(working)
            if m_wb_blk:
                candidate_body = working[: m_wb_blk.start()].strip()
                if candidate_body:
                    working = candidate_body
                for blk_ln in m_wb_blk.group(1).splitlines():
                    sub_s = re.sub(r"^\s*(?:\d+[.)、]|[-*•])\s*", "", blk_ln.strip())
                    if not sub_s:
                        continue
                    m_inner = kind_prefix_pat.match(sub_s)
                    item_kind = None
                    if m_inner:
                        item_kind = _kw_to_kind(m_inner.group(1))
                        sub_s = m_inner.group(2).strip()
                    if len(sub_s) >= 4 and sub_s.lower() not in placeholder_vals:
                        wb_typed_items.append({"kind": item_kind, "text": sub_s[:180]})
                continue
            break

        if target is None:
            sorted_aliases = sorted((k for k in alias_to_aid.keys() if len(k) >= 2), key=len, reverse=True)
            if sorted_aliases:
                alias_union = "|".join(re.escape(a) for a in sorted_aliases)
                m_at = re.search(rf"@({alias_union})(?![A-Za-z0-9_])", working, flags=re.IGNORECASE)
                if m_at:
                    target = alias_to_aid.get(m_at.group(1).lower())

        return working, badge, target, wb_typed_items[:16], consensus_reached

    @classmethod
    def parse_structured_tail(cls, full_text: str) -> Tuple[str, str, Optional[str], List[str], Optional[bool]]:
        clean_body, badge, target, typed_items, consensus_reached = cls.parse_structured_tail_with_kinds(full_text)
        wb_points = [it["text"] for it in typed_items]
        return clean_body, badge, target, wb_points, consensus_reached

    @classmethod
    def split_status_tag(cls, full_text: str) -> Tuple[str, str, Optional[str]]:
        clean_body, badge, target, _, _ = cls.parse_structured_tail(full_text)
        return clean_body, badge, target

    async def ping_agent(
        self,
        agent_id: str,
        timeout_sec: float = 75.0,
        override: Optional[dict] = None,
    ) -> dict:
        start_ts = time.perf_counter()
        try:
            cfg, bpath, help_text, eff_drv, is_fb = self._require_binary(agent_id, override=override)
        except CLIInvocationError as exc:
            return {
                "agent_id": agent_id,
                "ok": False,
                "binary_path": "",
                "driver": exc.driver,
                "model": exc.model,
                "effort": exc.effort,
                "elapsed_ms": 0,
                "reply": "",
                "error_kind": exc.error_kind,
                "stderr": exc.stderr,
                "exit_code": exc.exit_code,
                "error": str(exc),
            }
        except Exception as exc:
            return {
                "agent_id": agent_id,
                "ok": False,
                "binary_path": "",
                "elapsed_ms": 0,
                "reply": "",
                "error_kind": "binary_missing",
                "stderr": "",
                "exit_code": None,
                "error": str(exc),
            }

        prompt = "请仅回复四个字：连接正常。不要调用任何工具。"
        chunks: List[str] = []
        ping_cwd = self._discussion_sandbox_cwd()
        explicit_model = str(override.get("model") or "").strip() if isinstance(override, dict) else ""
        if explicit_model:
            eff_model = resolve_effective_model_for_driver(eff_drv, explicit_model, is_shared_fb=False)
        else:
            eff_model = resolve_effective_model_for_driver(eff_drv, cfg.model, is_shared_fb=is_fb)

        spec = get_model_effort_spec(eff_drv, model=eff_model, help_text=help_text)
        explicit_eff_supplied = isinstance(override, dict) and (
            "discussion_effort" in override or "effort" in override
        )
        raw_req_eff = (cfg.discussion_effort or "").strip().lower()
        if raw_req_eff == "none":
            raw_req_eff = ""
        if raw_req_eff == "ultra":
            raw_req_eff = "max"

        # 若前端/调用方显式指定了超出该模型白名单的档位，立即精准返回档位不兼容诊断
        if explicit_eff_supplied and raw_req_eff:
            if not spec.get("supports_effort", True):
                err_obj = classify_cli_error(
                    eff_drv,
                    raw_err=f'--effort "{raw_req_eff}" is not supported for model "{eff_model}"',
                    stderr=f'error: invalid model selection (--model "{eff_model}" --effort "{raw_req_eff}"): --effort is not supported for model "{eff_model}"',
                    exit_code=2,
                    model=eff_model,
                    effort=raw_req_eff,
                )
                return {
                    "agent_id": agent_id,
                    "ok": False,
                    "binary_path": bpath,
                    "driver": eff_drv,
                    "shared_fallback": is_fb,
                    "model": eff_model,
                    "effort": raw_req_eff,
                    "supports_effort": False,
                    "elapsed_ms": int((time.perf_counter() - start_ts) * 1000),
                    "reply": "",
                    "error_kind": err_obj.error_kind,
                    "stderr": err_obj.stderr,
                    "exit_code": err_obj.exit_code,
                    "error": str(err_obj),
                }
            if raw_req_eff not in spec["allowed"]:
                err_obj = classify_cli_error(
                    eff_drv,
                    raw_err=f'unsupported effort "{raw_req_eff}" for model "{eff_model}" (valid values: {", ".join(spec["allowed"])})',
                    stderr=f'error: model "{eff_model}" does not support reasoning effort "{raw_req_eff}" (allowed: {", ".join(spec["allowed"])})',
                    exit_code=2,
                    model=eff_model,
                    effort=raw_req_eff,
                )
                return {
                    "agent_id": agent_id,
                    "ok": False,
                    "binary_path": bpath,
                    "driver": eff_drv,
                    "shared_fallback": is_fb,
                    "model": eff_model,
                    "effort": raw_req_eff,
                    "supports_effort": True,
                    "elapsed_ms": int((time.perf_counter() - start_ts) * 1000),
                    "reply": "",
                    "error_kind": err_obj.error_kind,
                    "stderr": err_obj.stderr,
                    "exit_code": err_obj.exit_code,
                    "error": str(err_obj),
                }

        eff_effort = normalize_model_effort(
            eff_drv,
            model=eff_model,
            effort=cfg.discussion_effort,
            help_text=help_text,
        )
        sem = self._get_binary_semaphore(bpath, stateless_shared=is_fb)
        try:
            async def _collect() -> None:
                async with sem:
                    async for ev in self._stream_raw_cli(
                        session_id=f"ping_{agent_id}_{int(time.time() * 1000)}",
                        agent_id=agent_id,
                        driver_key=eff_drv,
                        binary_path=bpath,
                        help_text=help_text,
                        model=eff_model,
                        effort=eff_effort,
                        prompt=prompt,
                        use_warm=False,
                        cwd_override=ping_cwd,
                        discuss_readonly=True,
                    ):
                        if ev.get("type") == "delta" and ev.get("text"):
                            chunks.append(ev["text"])

            await asyncio.wait_for(_collect(), timeout=timeout_sec)
            elapsed_ms = int((time.perf_counter() - start_ts) * 1000)
            reply = "".join(chunks).strip()
            if not reply:
                empty_err = classify_cli_error(
                    eff_drv,
                    raw_err="",
                    stderr="CLI exited 0 with empty stdout.",
                    exit_code=0,
                    model=eff_model,
                    effort=eff_effort,
                )
                return {
                    "agent_id": agent_id,
                    "ok": False,
                    "binary_path": bpath,
                    "driver": eff_drv,
                    "shared_fallback": is_fb,
                    "model": eff_model,
                    "effort": eff_effort,
                    "supports_effort": spec.get("supports_effort", True),
                    "elapsed_ms": elapsed_ms,
                    "reply": "",
                    "error_kind": empty_err.error_kind,
                    "stderr": empty_err.stderr,
                    "exit_code": empty_err.exit_code,
                    "error": str(empty_err),
                }
            return {
                "agent_id": agent_id,
                "ok": True,
                "binary_path": bpath,
                "driver": eff_drv,
                "shared_fallback": is_fb,
                "model": eff_model,
                "effort": eff_effort,
                "supports_effort": spec.get("supports_effort", True),
                "elapsed_ms": elapsed_ms,
                "reply": reply[:120],
                "error_kind": "",
                "stderr": "",
                "exit_code": 0,
                "error": "",
            }
        except asyncio.TimeoutError:
            t_err = classify_cli_error(
                eff_drv,
                is_timeout=True,
                timeout_sec=timeout_sec,
                model=eff_model,
                effort=eff_effort,
            )
            return {
                "agent_id": agent_id,
                "binary_path": bpath,
                "driver": eff_drv,
                "shared_fallback": is_fb,
                "model": eff_model,
                "effort": eff_effort,
                "supports_effort": spec.get("supports_effort", True),
                "ok": False,
                "elapsed_ms": int((time.perf_counter() - start_ts) * 1000),
                "reply": "".join(chunks).strip()[:120],
                "error_kind": t_err.error_kind,
                "stderr": t_err.stderr,
                "exit_code": t_err.exit_code,
                "error": str(t_err),
            }
        except CLIInvocationError as exc:
            return {
                "agent_id": agent_id,
                "ok": False,
                "binary_path": bpath,
                "driver": eff_drv,
                "shared_fallback": is_fb,
                "model": eff_model,
                "effort": eff_effort,
                "supports_effort": spec.get("supports_effort", True),
                "elapsed_ms": int((time.perf_counter() - start_ts) * 1000),
                "reply": "",
                "error_kind": exc.error_kind,
                "stderr": exc.stderr,
                "exit_code": exc.exit_code,
                "error": str(exc),
            }
        except Exception as exc:
            c_err = classify_cli_error(
                eff_drv,
                raw_err=str(exc),
                model=eff_model,
                effort=eff_effort,
            )
            return {
                "agent_id": agent_id,
                "ok": False,
                "binary_path": bpath,
                "driver": eff_drv,
                "shared_fallback": is_fb,
                "model": eff_model,
                "effort": eff_effort,
                "supports_effort": spec.get("supports_effort", True),
                "elapsed_ms": int((time.perf_counter() - start_ts) * 1000),
                "reply": "",
                "error_kind": c_err.error_kind,
                "stderr": c_err.stderr,
                "exit_code": c_err.exit_code,
                "error": str(c_err),
            }

    async def stream_discussion_turn(
        self,
        session_id: str,
        agent_id: str,
        stage: str,
        topic: str,
        collab_mode: str,
        whiteboard: dict,
        recent_messages: List[Dict[str, str]],
        cue_instruction: str = "",
        all_completed_count: int = 0,
        session_workspace: str = "",
        persona_key: str = "",
        is_solo_mode: bool = False,
        stateless: bool = False,
        shared_cli_roster: str = "",
        collab_mode_key: str = "",
        turn_override: Optional[dict] = None,
    ) -> AsyncGenerator[dict, None]:
        start_ts = time.perf_counter()
        ttft_ms: Optional[int] = None
        ov = turn_override if isinstance(turn_override, dict) else None
        cfg, bpath, help_text, eff_drv, is_fb = self._require_binary(agent_id, override=ov)

        eff_persona = persona_key if persona_key in PERSONA_PRESETS else cfg.persona
        seen_key = (session_id, agent_id)
        persona_switched = self._last_persona_by_seat.get(seen_key) != eff_persona
        eff_ws = session_workspace or self.settings.workspace_dir
        ref_budget = max(10000, int(getattr(self.settings, "max_ref_chars", MAX_ROUND_SOURCE_CHARS) or MAX_ROUND_SOURCE_CHARS))

        use_stateless = stateless or bool(ov and ov.get("stateless"))
        has_mem = False if use_stateless else self._has_active_session_memory(session_id, agent_id, eff_drv)
        prev_seen = self._last_seen_msg_idx.get(seen_key, 0)
        already_injected = self._injected_refs.setdefault(seen_key, set())
        newly_loaded_refs: Set[str] = set()

        if stage != "synthesis" and has_mem and not persona_switched and all_completed_count > prev_seen and prev_seen > 0:
            delta_count = min(len(recent_messages), max(1, all_completed_count - prev_seen))
            msgs_for_prompt = recent_messages[-delta_count:]
            incremental = True
            ws_snapshot = ""
            inc_corpus = "\n".join(
                [cue_instruction]
                + (whiteboard.get("chair_constraints") or [])[-3:]
                + [m["content"] for m in msgs_for_prompt]
            )
            extra_ref_block, newly_loaded_refs = extract_referenced_files_context(
                eff_ws,
                inc_corpus,
                max_total_chars=ref_budget,
                exclude_refs=already_injected,
            )
        else:
            msgs_for_prompt = recent_messages
            incremental = False
            extra_ref_block = ""
            ref_corpus = "\n".join(
                [topic, cue_instruction]
                + (whiteboard.get("chair_constraints") or [])
                + [m["content"] for m in recent_messages[-24:]]
            )
            full_ref_block, newly_loaded_refs = extract_referenced_files_context(
                eff_ws,
                ref_corpus,
                max_total_chars=ref_budget,
            )
            use_lightweight_ws = (
                collab_mode_key != "code_review"
                and not full_ref_block
                and not bool(_CODE_TOPIC_HINT_RE.search(f"{topic}\n{cue_instruction}"))
            )
            ws_snapshot = build_workspace_context_snapshot(
                eff_ws,
                reference_texts=ref_corpus,
                prebuilt_ref_block=full_ref_block,
                max_ref_chars=ref_budget,
                lightweight_hint_only=use_lightweight_ws,
            )

        seat_names_now = {
            aid_k: self.settings.resolve_seat_name(aid_k)
            for aid_k in ALL_SEAT_IDS
        }
        prompt = self._build_prompt(
            agent_id=agent_id,
            stage=stage,
            topic=topic,
            collab_mode=collab_mode,
            whiteboard=whiteboard,
            recent_messages=msgs_for_prompt,
            cue_instruction=cue_instruction,
            incremental_only=incremental,
            workspace_snapshot=ws_snapshot,
            persona_key=eff_persona,
            is_solo_mode=is_solo_mode,
            extra_ref_block=extra_ref_block,
            shared_cli_roster=shared_cli_roster,
            collab_mode_key=collab_mode_key,
            seat_names_map=seat_names_now,
        )

        explicit_ov_model = str(ov.get("model") or "").strip() if ov else ""
        eff_model = resolve_effective_model_for_driver(
            eff_drv,
            explicit_ov_model or cfg.model,
            is_shared_fb=False if explicit_ov_model else is_fb,
        )
        # 严格遵循用户配置的 discussion_effort（或单轮临时覆盖档位），绝不静默自动降档
        eff_effort = normalize_model_effort(
            eff_drv,
            model=eff_model,
            effort=cfg.discussion_effort,
            help_text=help_text,
        )

        chunks: List[str] = []
        bound_ws, real_ws = is_real_bound_workspace(eff_ws)
        discuss_cwd = real_ws if bound_ws else self._discussion_sandbox_cwd()
        sem = self._get_binary_semaphore(bpath, stateless_shared=use_stateless)

        is_unlimited = bool(ov and ov.get("unlimited_timeout"))
        raw_idle = int(getattr(self.settings, "idle_timeout_sec", DEFAULT_IDLE_TIMEOUT_SEC) or DEFAULT_IDLE_TIMEOUT_SEC)
        if raw_idle <= 0:
            raw_idle = DEFAULT_IDLE_TIMEOUT_SEC
        _min_idle_b = 1 if os.environ.get("AI_ROUNDTABLE_FAST_TEST") == "1" else 15
        idle_timeout = 1800.0 if is_unlimited else float(max(_min_idle_b, min(1800, raw_idle)))

        raw_turn = int(getattr(self.settings, "turn_timeout_sec", DEFAULT_TURN_TIMEOUT_SEC) or DEFAULT_TURN_TIMEOUT_SEC)
        if raw_turn <= 0:
            raw_turn = DEFAULT_TURN_TIMEOUT_SEC
        total_timeout: float = 3600.0 if is_unlimited else float(max(30, min(3600, raw_turn)))
        if stage == "synthesis":
            total_timeout = max(total_timeout, 600.0)

        if sem.locked():
            conc_cap = max(1, min(6, int(getattr(self.settings, "single_cli_concurrency", 3) or 3)))
            yield {
                "type": "status",
                "detail": f"等待单引擎并发槽位（当前上限 {conc_cap} 路并行）…",
                "driver": eff_drv,
                "model": eff_model,
                "effort": eff_effort,
            }

        async with sem:
            yield {
                "type": "status",
                "detail": "正在启动模型深度推理…",
                "driver": eff_drv,
                "model": eff_model,
                "effort": eff_effort,
            }
            sess_atts = whiteboard.get("session_attachments") if isinstance(whiteboard, dict) else None
            stream_iter = self._stream_with_fallback(
                session_id=session_id,
                agent_id=agent_id,
                driver_key=eff_drv,
                model=eff_model,
                effort=eff_effort,
                binary_path=bpath,
                help_text=help_text,
                prompt=prompt,
                use_warm=not use_stateless,
                cwd_override=discuss_cwd,
                discuss_readonly=True,
                disable_stepdown_fallback=bool(ov and ov.get("strict_effort")),
                session_attachments=sess_atts if isinstance(sess_atts, list) else None,
            ).__aiter__()
            hard_deadline = time.perf_counter() + total_timeout
            terminal_ok = False
            try:
                while True:
                    total_rem = hard_deadline - time.perf_counter()
                    if total_rem <= 0:
                        raise asyncio.TimeoutError("turn_cap_exceeded")
                    step_wait = max(0.2, min(idle_timeout, total_rem))
                    try:
                        ev = await asyncio.wait_for(stream_iter.__anext__(), timeout=step_wait)
                    except StopAsyncIteration:
                        break
                    ev_type = ev.get("type")
                    if ev_type in ("status", "activity"):
                        act_txt = str(ev.get("detail") or ev.get("text") or "").strip()
                        if act_txt:
                            yield {
                                "type": "status",
                                "detail": act_txt,
                                "driver": eff_drv,
                                "model": eff_model,
                                "effort": eff_effort,
                            }
                    elif ev_type == "delta":
                        delta = ev.get("text") or ""
                        if delta:
                            if ttft_ms is None:
                                ttft_ms = int((time.perf_counter() - start_ts) * 1000)
                            chunks.append(delta)
                            yield {"type": "delta", "text": delta}
                    elif ev_type == "terminal":
                        terminal_ok = bool(ev.get("ok", True))
            except asyncio.TimeoutError:
                # P0.3 红线：彻底废除 >=80 字符吞超时分支！任何空闲超时或整轮超时无论已输出多少字符一律抛出超时异常，严禁残稿入白板
                hit_total = bool(time.perf_counter() >= (hard_deadline - 0.25))
                reported_sec = total_timeout if hit_total else idle_timeout
                raise classify_cli_error(
                    eff_drv,
                    is_timeout=True,
                    timeout_sec=reported_sec,
                    model=eff_model,
                    effort=eff_effort,
                )
            finally:
                try:
                    await stream_iter.aclose()
                except Exception:
                    pass

        full_raw = "".join(chunks).strip()
        if not full_raw:
            raise classify_cli_error(
                eff_drv,
                raw_err="",
                stderr="CLI stream ended with empty output.",
                exit_code=0,
                model=eff_model,
                effort=eff_effort,
            )

        if newly_loaded_refs and not use_stateless:
            already_injected.update(newly_loaded_refs)
        if not use_stateless:
            self._last_persona_by_seat[seen_key] = eff_persona
            if all_completed_count >= 0:
                self._last_seen_msg_idx[seen_key] = all_completed_count + 1

        clean_body, badge, target, wb_typed_items, consensus_reached = self.parse_structured_tail_with_kinds(full_raw, seat_names=seat_names_now)
        wb_points = [it["text"] for it in wb_typed_items]
        if is_solo_mode or stage == "synthesis" or target == agent_id:
            target = None
        elapsed_ms = int((time.perf_counter() - start_ts) * 1000)
        yield {
            "type": "done",
            "status": "success",
            "terminal_received": True if terminal_ok or bool(clean_body.strip()) else False,
            "partial_output": False,
            "error_kind": "",
            "binary_path": bpath,
            "full_text": clean_body,
            "badge": badge,
            "target": target,
            "wb_points": wb_points,
            "wb_items": wb_typed_items,
            "consensus": consensus_reached,
            "driver": eff_drv,
            "model": eff_model,
            "effort": eff_effort,
            "ttft_ms": ttft_ms or elapsed_ms,
            "elapsed_ms": elapsed_ms,
        }

    async def _stream_with_fallback(
        self,
        session_id: str,
        agent_id: str,
        driver_key: str,
        model: str,
        effort: str,
        binary_path: str,
        help_text: str,
        prompt: str,
        use_warm: bool = True,
        cwd_override: Optional[str] = None,
        discuss_readonly: bool = True,
        disable_stepdown_fallback: bool = False,
        session_attachments: Optional[List[dict]] = None,
    ) -> AsyncGenerator[dict, None]:
        """按候选模型与推理档位顺序尝试流式请求；单次波动回退绝不篡改用户保存的配置。"""
        if disable_stepdown_fallback:
            eff_m = resolve_effective_model_for_driver(driver_key, model, is_shared_fb=False)
            eff_e = normalize_model_effort(driver_key, model=eff_m, effort=effort, help_text=help_text)
            attempts = [(eff_m, eff_e)]
        else:
            attempts = self._build_fallback_attempts(driver_key, model, effort, help_text=help_text)
        terminal_exc: Optional[Exception] = None

        for cand_model, cand_effort in attempts:
            # P0.3：每次候选尝试前独立清空前序尝试的异常记录与状态，绝不跨候选污染
            attempt_exc: Optional[Exception] = None
            emitted_delta = False
            retried_burst_429 = False
            while True:
                try:
                    async for ev in self._stream_raw_cli(
                        session_id=session_id,
                        agent_id=agent_id,
                        driver_key=driver_key,
                        binary_path=binary_path,
                        help_text=help_text,
                        model=cand_model,
                        effort=cand_effort,
                        prompt=prompt,
                        use_warm=use_warm,
                        cwd_override=cwd_override,
                        discuss_readonly=discuss_readonly,
                        session_attachments=session_attachments,
                    ):
                        if ev.get("type") == "delta" and ev.get("text"):
                            emitted_delta = True
                        yield ev
                    if emitted_delta:
                        return
                    break
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    attempt_exc = exc
                    # 单 CLI 多路并发下若首字节前触发瞬时并发限流（429），自动微退避重试 1 次
                    if (
                        not use_warm
                        and not emitted_delta
                        and not retried_burst_429
                        and isinstance(exc, CLIInvocationError)
                        and exc.error_kind == "quota_rate_limit"
                    ):
                        retried_burst_429 = True
                        attempt_exc = None
                        yield {"type": "status", "detail": "检测到并发瞬时限流，正在错峰重试…"}
                        await asyncio.sleep(0.65 + (hash(f"{session_id}:{agent_id}") % 5) * 0.12)
                        continue
                    if emitted_delta or not _is_model_or_effort_rejection(exc):
                        raise
                    terminal_exc = attempt_exc
                    break

        if terminal_exc:
            raise terminal_exc

    async def _stream_raw_cli(
        self,
        session_id: str,
        agent_id: str,
        driver_key: str,
        binary_path: str,
        help_text: str,
        model: str,
        effort: str,
        prompt: str,
        use_warm: bool = True,
        cwd_override: Optional[str] = None,
        discuss_readonly: bool = True,
        session_attachments: Optional[List[dict]] = None,
    ) -> AsyncGenerator[dict, None]:
        cwd = cwd_override if (cwd_override and os.path.isdir(cwd_override)) else self._effective_workspace_cwd()
        seat_key = (session_id, agent_id)
        att_mgr = self._get_attachment_manager() if session_attachments else None

        async def spawn_call_with_attachments(build_cmd_fn, stdin):
            env, call_tmp = self._prepare_isolated_call_env(session_id, agent_id)
            try:
                staged_prompt = prompt
                staged_imgs: List[str] = []
                if session_attachments and att_mgr is not None:
                    att_blk, staged_imgs = att_mgr.stage_for_cli_turn(session_id, session_attachments, call_tmp)
                    if att_blk:
                        staged_prompt = f"{att_blk}\n\n{prompt}"
                final_cmd = build_cmd_fn(staged_prompt, staged_imgs)
                handle = await spawn_supervised_cli(final_cmd, cwd=cwd, env=env, stdin=stdin)
                return handle, call_tmp, staged_prompt
            except BaseException:
                self._cleanup_isolated_call_tmp(call_tmp)
                raise

        if driver_key == "agy":
            supports_stream_json = "stream-json" in help_text or "--output-format" in help_text
            has_disable_slash = "--disable-slash-commands" in help_text
            effort_spec = get_model_effort_spec("agy", model=model, help_text=help_text)
            has_effort = ("--effort" in help_text) and effort_spec.get("supports_effort", True)
            agy_effort = (
                WarmAntigravityProcess.normalize_agy_effort(effort, help_text=help_text, model=model)
                if has_effort
                else ""
            )

            if use_warm and "--input-format" in help_text and supports_stream_json:
                warm_inst = self._warm_agy_pool.get(seat_key)
                if (
                    warm_inst is None
                    and self._prewarmed_agy
                    and self._prewarmed_agy.proc
                    and self._prewarmed_agy.proc.returncode is None
                    and self._prewarmed_agy.binary_path == binary_path
                    and self._prewarmed_agy.model == model
                    and self._prewarmed_agy.effort == agy_effort
                    and self._prewarmed_agy.supports_effort == has_effort
                    and self._prewarmed_agy.cwd == cwd
                    and self._prewarmed_agy.sandbox == discuss_readonly
                    and self._prewarmed_agy.turn_count == 0
                ):
                    warm_inst = self._prewarmed_agy
                    self._prewarmed_agy = None
                    warm_inst.session_id = session_id
                    warm_inst.seat_id = agent_id
                    self._warm_agy_pool[seat_key] = warm_inst
                elif (
                    warm_inst is None
                    or warm_inst.binary_path != binary_path
                    or warm_inst.model != model
                    or warm_inst.effort != agy_effort
                    or warm_inst.supports_effort != has_effort
                    or warm_inst.cwd != cwd
                    or warm_inst.sandbox != discuss_readonly
                ):
                    if warm_inst:
                        await warm_inst.close()
                    warm_inst = WarmAntigravityProcess(
                        binary_path=binary_path,
                        model=model,
                        effort=agy_effort,
                        cwd=cwd,
                        session_id=session_id,
                        seat_id=agent_id,
                        disable_slash=has_disable_slash,
                        supports_effort=has_effort,
                        sandbox=discuss_readonly,
                        help_text=help_text,
                    )
                    self._warm_agy_pool[seat_key] = warm_inst
                try:
                    async for ev in warm_inst.stream_turn(
                        prompt,
                        session_attachments=session_attachments,
                        att_mgr=att_mgr,
                    ):
                        yield ev
                    return
                except asyncio.CancelledError:
                    await warm_inst.close()
                    self._warm_agy_pool.pop(seat_key, None)
                    raise
                except Exception as warm_exc:
                    await warm_inst.close()
                    self._warm_agy_pool.pop(seat_key, None)
                    if isinstance(warm_exc, CLIInvocationError) and warm_exc.error_kind in (
                        "unsupported_effort_or_model",
                        "quota_rate_limit",
                        "auth_expired",
                        "timeout",
                    ):
                        raise
                    if _is_model_or_effort_rejection(warm_exc):
                        raise

            def _build_agy_cmd(eff_p: str, _imgs: List[str]) -> List[str]:
                c = [binary_path, "-p", eff_p]
                if has_disable_slash:
                    c.append("--disable-slash-commands")
                if discuss_readonly and "--sandbox" in help_text:
                    c.append("--sandbox")
                if supports_stream_json:
                    c.extend(["--output-format", "stream-json"])
                if model:
                    c.extend(["--model", model])
                if has_effort and agy_effort:
                    c.extend(["--effort", agy_effort])
                return c

            sup_handle, call_tmp_dir, _ = await spawn_call_with_attachments(_build_agy_cmd, asyncio.subprocess.DEVNULL)
            proc = sup_handle.proc
            self._register_raw_proc(seat_key, proc)
            try:
                assert proc.stdout is not None
                emitted = False
                saw_tool_since_text = False
                ended_with_nl = True
                last_activity = ""
                stream_err = ""
                if supports_stream_json:
                    while True:
                        line_b = await proc.stdout.readline()
                        if not line_b:
                            break
                        line_s = line_b.decode("utf-8", errors="replace").strip()
                        if not line_s:
                            continue
                        try:
                            evt = json.loads(line_s)
                            if evt.get("event") == "step_update":
                                su = evt.get("step_update", {})
                                st_type = su.get("step_type", "")
                                if st_type == "agent_response" and su.get("text_delta"):
                                    delta_t = su["text_delta"]
                                    if saw_tool_since_text and emitted and not ended_with_nl:
                                        yield {"type": "delta", "text": "\n\n"}
                                    saw_tool_since_text = False
                                    emitted = True
                                    ended_with_nl = delta_t.endswith("\n")
                                    yield {"type": "delta", "text": delta_t}
                                elif st_type == "agent_response" and su.get("state") in ("ACTIVE", "RUNNING") and not emitted:
                                    act = "正在组织推演输出…"
                                    last_activity = act
                                    yield {"type": "status", "detail": act}
                                elif st_type == "tool" and su.get("state") in ("ACTIVE", "RUNNING", None):
                                    saw_tool_since_text = True
                                    act = _format_cli_tool_activity("agy", su.get("tool_name", ""), su, cwd=cwd) or "正在执行只读源码检查…"
                                    last_activity = act
                                    yield {"type": "status", "detail": act}
                                elif st_type in ("thinking", "thought"):
                                    act = "正在深度推演方案与边界…"
                                    last_activity = act
                                    yield {"type": "status", "detail": act}
                                elif st_type and st_type != "agent_response":
                                    act = _format_cli_tool_activity("agy", st_type, su, cwd=cwd) or f"正在推进步骤 ({st_type[:18]})…"
                                    last_activity = act
                                    yield {"type": "status", "detail": act}
                            elif evt.get("event") == "result":
                                res = evt.get("result", {})
                                if not emitted and res.get("response"):
                                    emitted = True
                                    yield {"type": "delta", "text": res["response"]}
                                if res.get("status") not in ("SUCCESS", None) and not emitted:
                                    stream_err = str(res.get("error") or f"Antigravity 状态异常: {res.get('status')}")
                        except json.JSONDecodeError:
                            if not line_s.startswith("warning:"):
                                emitted = True
                                yield {"type": "delta", "text": line_s + "\n"}
                else:
                    while True:
                        chunk = await proc.stdout.read(256)
                        if not chunk:
                            break
                        emitted = True
                        yield {"type": "delta", "text": chunk.decode("utf-8", errors="replace")}

                rc = await proc.wait()
                if rc != 0 or stream_err or not emitted:
                    err_txt = (await proc.stderr.read()).decode("utf-8", errors="replace").strip() if proc.stderr else ""
                    raise classify_cli_error(
                        "agy",
                        raw_err=stream_err,
                        stderr=err_txt,
                        exit_code=rc,
                        model=model,
                        effort=agy_effort,
                    )
                yield {"type": "terminal", "ok": True}
                return
            finally:
                self._unregister_raw_proc(seat_key, proc)
                await terminate_and_reap_process_group(sup_handle, proc)
                self._cleanup_isolated_call_tmp(call_tmp_dir)

        if driver_key == "grok":
            grok_eff = normalize_model_effort("grok", model=model, effort=effort, help_text=help_text)
            supports_streaming_json = "streaming-json" in help_text
            cmd = [binary_path, "-p", prompt]
            if supports_streaming_json:
                cmd.extend(["--output-format", "streaming-json"])
            if model and ("--model" in help_text or "-m" in help_text):
                cmd.extend(["--model", model])
            if grok_eff and "--effort" in help_text:
                cmd.extend(["--effort", grok_eff])
            if discuss_readonly:
                if "--tools" in help_text:
                    cmd.extend(["--tools", "read_file,list_dir,grep"])
                elif "--disallowed-tools" in help_text:
                    cmd.extend(["--disallowed-tools", "run_terminal_command,bash,sh,write,search_replace,todo_write"])
            if "--no-plan" in help_text:
                cmd.append("--no-plan")
            if "--no-subagents" in help_text:
                cmd.append("--no-subagents")
            if "--permission-mode" in help_text:
                cmd.extend(["--permission-mode", "dontAsk"])

            def _build_grok_cmd(eff_p: str, _imgs: List[str]) -> List[str]:
                return [*cmd[:2], eff_p, *cmd[3:]]

            sup_handle, call_tmp_dir, _ = await spawn_call_with_attachments(_build_grok_cmd, asyncio.subprocess.DEVNULL)
            proc = sup_handle.proc
            self._register_raw_proc(seat_key, proc)
            try:
                assert proc.stdout is not None
                emitted = False
                saw_tool_since_text = False
                ended_with_nl = True
                last_activity = ""
                stream_err = ""
                saw_json_event = False
                non_json_lines: List[str] = []

                if supports_streaming_json:
                    while True:
                        line_b = await proc.stdout.readline()
                        if not line_b:
                            break
                        line_s = line_b.decode("utf-8", errors="replace").rstrip("\r\n")
                        stripped = line_s.strip()
                        if not stripped:
                            continue
                        if stripped.startswith("Finishing session") or stripped.startswith("warning:"):
                            continue
                        try:
                            evt = json.loads(stripped)
                            saw_json_event = True
                        except json.JSONDecodeError:
                            non_json_lines.append(line_s)
                            continue

                        etype = str(evt.get("type") or "")
                        if etype in ("text", "text_delta", "content_block_delta"):
                            txt = evt.get("data")
                            if txt is None:
                                delta_obj = evt.get("delta")
                                if isinstance(delta_obj, dict):
                                    txt = delta_obj.get("text") or ""
                                else:
                                    txt = evt.get("text") or ""
                            txt_s = str(txt or "")
                            if txt_s:
                                if saw_tool_since_text and emitted and not ended_with_nl:
                                    yield {"type": "delta", "text": "\n\n"}
                                saw_tool_since_text = False
                                emitted = True
                                ended_with_nl = txt_s.endswith("\n")
                                yield {"type": "delta", "text": txt_s}
                        elif etype in ("tool_call", "tool_call_update"):
                            saw_tool_since_text = True
                            tname = str(evt.get("toolName") or evt.get("title") or "")
                            act = _format_cli_tool_activity("grok", tname, evt, cwd=cwd) or "正在分析项目上下文…"
                            last_activity = act
                            yield {"type": "status", "detail": act}
                        elif etype in ("thinking", "reasoning"):
                            act = "正在深度推演方案与边界…"
                            last_activity = act
                            yield {"type": "status", "detail": act}
                        elif etype in ("start", "session_start", "init") and not emitted:
                            yield {"type": "status", "detail": "已建立会话，正在深度思考…"}
                        elif etype in ("message", "assistant") and not emitted:
                            msg_obj = evt.get("message") if isinstance(evt.get("message"), dict) else evt
                            content_blocks = msg_obj.get("content")
                            if isinstance(content_blocks, list):
                                joined = "".join(
                                    str(b.get("text") or "")
                                    for b in content_blocks
                                    if isinstance(b, dict) and b.get("type") == "text"
                                )
                                if joined:
                                    emitted = True
                                    yield {"type": "delta", "text": joined}
                        elif etype == "error":
                            stream_err = str(evt.get("message") or evt.get("error") or stream_err)
                        elif etype == "end":
                            if evt.get("error") and not emitted:
                                stream_err = str(evt.get("error"))

                    if not emitted and not saw_json_event and non_json_lines:
                        fallback_plain = "\n".join(non_json_lines).strip()
                        if fallback_plain:
                            emitted = True
                            yield {"type": "delta", "text": fallback_plain}
                else:
                    while True:
                        chunk = await proc.stdout.read(256)
                        if not chunk:
                            break
                        emitted = True
                        yield {"type": "delta", "text": chunk.decode("utf-8", errors="replace")}

                rc = await proc.wait()
                if rc != 0 or stream_err or not emitted:
                    err_txt = (await proc.stderr.read()).decode("utf-8", errors="replace").strip() if proc.stderr else ""
                    raise classify_cli_error(
                        "grok",
                        raw_err=stream_err,
                        stderr=err_txt,
                        exit_code=rc,
                        model=model,
                        effort=grok_eff,
                    )
                yield {"type": "terminal", "ok": True}
                return
            finally:
                self._unregister_raw_proc(seat_key, proc)
                await terminate_and_reap_process_group(sup_handle, proc)
                self._cleanup_isolated_call_tmp(call_tmp_dir)

        if driver_key == "claude":
            claude_eff = normalize_model_effort("claude", model=model, effort=effort, help_text=help_text)
            supports_stream_json = "stream-json" in help_text or "--output-format" in help_text

            def _build_claude_cmd(eff_p: str, _imgs: List[str]) -> List[str]:
                c = [binary_path, "-p", eff_p]
                if supports_stream_json:
                    c.extend(["--output-format", "stream-json"])
                    if "--verbose" in help_text:
                        c.append("--verbose")
                if model and "--model" in help_text:
                    c.extend(["--model", model])
                if claude_eff and "--effort" in help_text:
                    c.extend(["--effort", claude_eff])
                if discuss_readonly:
                    if "--tools" in help_text:
                        c.extend(["--tools", "Read,Grep,Glob,LS"])
                    elif "--permission-mode" in help_text:
                        c.extend(["--permission-mode", "plan"])
                return c

            sup_handle, call_tmp_dir, _ = await spawn_call_with_attachments(_build_claude_cmd, asyncio.subprocess.DEVNULL)
            proc = sup_handle.proc
            self._register_raw_proc(seat_key, proc)
            try:
                assert proc.stdout is not None
                emitted = False
                stream_err = ""
                if supports_stream_json:
                    while True:
                        line_b = await proc.stdout.readline()
                        if not line_b:
                            break
                        line_s = line_b.decode("utf-8", errors="replace").strip()
                        if not line_s:
                            continue
                        try:
                            evt = json.loads(line_s)
                        except json.JSONDecodeError:
                            emitted = True
                            yield {"type": "delta", "text": line_s + "\n"}
                            continue
                        etype = str(evt.get("type") or "")
                        if etype in ("content_block_delta", "text_delta"):
                            delta_obj = evt.get("delta") if isinstance(evt.get("delta"), dict) else {}
                            txt_s = str(delta_obj.get("text") or evt.get("text") or "")
                            if txt_s:
                                emitted = True
                                yield {"type": "delta", "text": txt_s}
                        elif etype == "assistant":
                            msg_obj = evt.get("message") if isinstance(evt.get("message"), dict) else {}
                            c_blocks = msg_obj.get("content") if isinstance(msg_obj.get("content"), list) else []
                            joined = "".join(
                                str(b.get("text") or "")
                                for b in c_blocks
                                if isinstance(b, dict) and b.get("type") == "text"
                            )
                            if joined and not emitted:
                                emitted = True
                                yield {"type": "delta", "text": joined}
                        elif etype == "result":
                            if evt.get("is_error"):
                                stream_err = str(evt.get("result") or evt.get("error") or "Claude CLI error")
                            elif not emitted and evt.get("result"):
                                emitted = True
                                yield {"type": "delta", "text": str(evt["result"])}
                        elif etype == "error":
                            stream_err = str(evt.get("message") or evt.get("error") or stream_err)
                else:
                    while True:
                        chunk = await proc.stdout.read(256)
                        if not chunk:
                            break
                        emitted = True
                        yield {"type": "delta", "text": chunk.decode("utf-8", errors="replace")}
                rc = await proc.wait()
                if rc != 0 or stream_err or not emitted:
                    err_txt = (await proc.stderr.read()).decode("utf-8", errors="replace").strip() if proc.stderr else ""
                    raise classify_cli_error(
                        "claude",
                        raw_err=stream_err,
                        stderr=err_txt,
                        exit_code=rc,
                        model=model,
                        effort=claude_eff,
                    )
                yield {"type": "terminal", "ok": True}
                return
            finally:
                self._unregister_raw_proc(seat_key, proc)
                await terminate_and_reap_process_group(sup_handle, proc)
                self._cleanup_isolated_call_tmp(call_tmp_dir)

        if driver_key != "codex" and DRIVER_SPECS.get(driver_key, {}).get("cmd_template"):
            tpl = DRIVER_SPECS[driver_key]["cmd_template"]
            uses_prompt_placeholder = any("{prompt}" in str(t) for t in tpl)

            def _build_tpl_cmd(eff_p: str, _imgs: List[str]) -> List[str]:
                return [
                    str(tok).format(binary=binary_path, model=model, effort=effort, prompt=eff_p, cwd=cwd)
                    for tok in tpl
                ]

            sup_handle, call_tmp_dir, eff_stdin_p = await spawn_call_with_attachments(
                _build_tpl_cmd,
                asyncio.subprocess.DEVNULL if uses_prompt_placeholder else asyncio.subprocess.PIPE,
            )
            proc = sup_handle.proc
            self._register_raw_proc(seat_key, proc)
            try:
                if not uses_prompt_placeholder and proc.stdin is not None:
                    proc.stdin.write(eff_stdin_p.encode("utf-8"))
                    await proc.stdin.drain()
                    proc.stdin.close()
                assert proc.stdout is not None
                emitted = False
                while True:
                    chunk = await proc.stdout.read(256)
                    if not chunk:
                        break
                    txt_c = chunk.decode("utf-8", errors="replace")
                    if txt_c:
                        emitted = True
                        yield {"type": "delta", "text": txt_c}
                rc = await proc.wait()
                if rc != 0 or not emitted:
                    err_txt = (await proc.stderr.read()).decode("utf-8", errors="replace").strip() if proc.stderr else ""
                    raise classify_cli_error(
                        driver_key,
                        raw_err="",
                        stderr=err_txt,
                        exit_code=rc,
                        model=model,
                        effort=effort,
                    )
                yield {"type": "terminal", "ok": True}
                return
            finally:
                self._unregister_raw_proc(seat_key, proc)
                await terminate_and_reap_process_group(sup_handle, proc)
                self._cleanup_isolated_call_tmp(call_tmp_dir)

        existing_tid = self._codex_threads.get(seat_key) if use_warm else None
        codex_eff = normalize_model_effort("codex", model=model, effort=effort, help_text=help_text)
        def _build_codex_or_ext_cmd(eff_p: str, imgs: List[str]) -> List[str]:
            c = [binary_path, "exec", "--json", "--skip-git-repo-check", "--sandbox", "read-only"]
            if codex_eff in ORDERED_EFFORT_LEVELS:
                c.extend(["-c", f'model_reasoning_effort="{codex_eff}"'])
            if model:
                c.extend(["-m", model])
            if existing_tid:
                c.append("resume")
            if imgs and "--image" in help_text:
                for img_p in imgs[-4:]:
                    c.extend(["--image", img_p])
                c.append("--")
            if existing_tid:
                c.append(existing_tid)
            c.append("-")
            return c

        sup_handle, call_tmp_dir, eff_stdin_prompt = await spawn_call_with_attachments(
            _build_codex_or_ext_cmd, asyncio.subprocess.PIPE
        )
        proc = sup_handle.proc
        self._register_raw_proc(seat_key, proc)
        try:
            assert proc.stdin is not None and proc.stdout is not None
            proc.stdin.write(eff_stdin_prompt.encode("utf-8"))
            await proc.stdin.drain()
            proc.stdin.close()

            seen_lengths: Dict[str, int] = {}
            completed_item_count = 0
            emitted = False
            last_activity = ""
            stream_err = ""
            turn_completed = turn_failed = False
            while True:
                line_b = await proc.stdout.readline()
                if not line_b:
                    break
                line_s = line_b.decode("utf-8", errors="replace").strip()
                if not line_s:
                    continue
                try:
                    evt = json.loads(line_s)
                except json.JSONDecodeError:
                    emitted = True
                    yield {"type": "delta", "text": line_s + "\n"}
                    continue

                etype = evt.get("type", "")
                if etype == "thread.started":
                    if evt.get("thread_id") and use_warm:
                        self._codex_threads[seat_key] = evt["thread_id"]
                    if not emitted:
                        yield {"type": "status", "detail": "已连接推理线程，正在分析上下文…"}
                elif etype == "turn.completed":
                    turn_completed = True
                elif etype == "turn.started":
                    if not emitted:
                        yield {"type": "status", "detail": "已进入高阶推理回合，正在深度思考…"}
                elif etype == "item.started":
                    item = evt.get("item", {})
                    itype = item.get("type", "")
                    act = _format_cli_tool_activity("codex", itype, item, cwd=cwd) or (
                        "正在深度推演方案与边界…" if "reason" in itype else f"正在处理 ({itype or 'step'})…"
                    )
                    last_activity = act
                    yield {"type": "status", "detail": act}
                elif etype in ("item.updated", "item.completed"):
                    item = evt.get("item", {})
                    itype = item.get("type", "")
                    if itype == "agent_message":
                        item_id = str(item.get("id") or "default")
                        txt = item.get("text", "")
                        prev_len = seen_lengths.get(item_id, 0)
                        if len(txt) > prev_len:
                            if prev_len == 0 and completed_item_count > 0:
                                yield {"type": "delta", "text": "\n\n"}
                            emitted = True
                            yield {"type": "delta", "text": txt[prev_len:]}
                            seen_lengths[item_id] = len(txt)
                        if etype == "item.completed" and txt:
                            completed_item_count += 1
                    elif itype == "reasoning":
                        act = "正在深度推演方案与边界…"
                        last_activity = act
                        yield {"type": "status", "detail": act}
                    elif itype in ("command_execution", "local_shell_call"):
                        act = _format_cli_tool_activity("codex", itype, item, cwd=cwd) or "正在只读核对项目源码…"
                        last_activity = act
                        yield {"type": "status", "detail": act}
                    elif itype == "error":
                        stream_err = item.get("message") or stream_err
                elif etype in ("error", "turn.failed"):
                    turn_failed = turn_failed or etype == "turn.failed"
                    err_obj = evt.get("error")
                    if isinstance(err_obj, dict):
                        stream_err = err_obj.get("message") or str(err_obj)
                    else:
                        stream_err = evt.get("message") or str(err_obj or "")

            rc = await proc.wait()
            # A startup warning is also emitted as an item of type "error". A
            # completed turn with a real assistant message confirms recovery.
            if rc != 0 or turn_failed or not emitted or (stream_err and not (turn_completed and completed_item_count)):
                stderr_txt = (await proc.stderr.read()).decode("utf-8", errors="replace").strip() if proc.stderr else ""
                raise classify_cli_error(
                    driver_key,
                    raw_err=stream_err,
                    stderr=stderr_txt,
                    exit_code=rc,
                    model=model,
                    effort=codex_eff,
                )
            yield {"type": "terminal", "ok": True}
        finally:
            self._unregister_raw_proc(seat_key, proc)
            await terminate_and_reap_process_group(sup_handle, proc)
            self._cleanup_isolated_call_tmp(call_tmp_dir)

    @staticmethod
    async def _collect_git_diff_async(cwd: str) -> str:
        git_bin = shutil.which("git") or "git"
        try:
            proc = await asyncio.create_subprocess_exec(
                git_bin,
                "diff",
                "--",
                ".",
                cwd=cwd,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=3.0)
            return out.decode("utf-8", errors="replace").strip()
        except Exception:
            return ""

    @staticmethod
    async def capture_workspace_backup(cwd: str) -> Optional[WorkspaceBackup]:
        return await asyncio.to_thread(WorkspaceBackup.capture, cwd)

    @staticmethod
    async def rollback_workspace_backup(backup: WorkspaceBackup) -> Tuple[bool, str]:
        try:
            return await asyncio.to_thread(backup.restore)
        except (ValueError, OSError, subprocess.SubprocessError) as exc:
            return False, f"回滚失败：{exc}"

    async def stream_agent_execution(
        self,
        topic: str,
        whiteboard: dict,
        allow_workspace_write: bool = False,
        session_workspace: str = "",
        agent_id: str = "astra",
        persona_key: str = "",
        session_id: str = "",
        on_pgid_spawned=None,
    ) -> AsyncGenerator[dict, None]:
        """
        多席位动态主刀实时流式执行引擎：
        支持任选 Carbon / Grok / Astra 作为执行主刀人，实时输出 exec_delta 流式文本与终端进展日志，
        完成只读预演（含 agy --mode plan）或直接写入本地项目工作区。
        """
        target_aid = agent_id if agent_id in self.settings.agents else "astra"
        cfg, bpath, help_text, eff_drv, is_fb = self._require_binary(target_aid)
        pspec = get_persona_spec(persona_key or cfg.persona, fallback_agent_id=target_aid)
        cwd = self._effective_workspace_cwd(session_workspace)

        raw_wb_items = whiteboard.get("items")
        chair_c_list = [str(x).strip() for x in (whiteboard.get("chair_constraints") or []) if str(x).strip()]
        decision_pts: List[str] = []
        checked_action_pts: List[str] = []
        unchecked_action_pts: List[str] = []
        risk_pts: List[str] = []
        has_structured_actions = False

        seen_dec_exec: Set[str] = set()
        for cx in chair_c_list:
            nk = re.sub(r"\W+", "", cx.lower())
            if nk and nk not in seen_dec_exec:
                seen_dec_exec.add(nk)
                decision_pts.append(f"- [主持约束] {cx}")

        if isinstance(raw_wb_items, list) and raw_wb_items:
            for it in raw_wb_items:
                if not isinstance(it, dict):
                    continue
                t = str(it.get("text") or "").strip()
                if not t:
                    continue
                author = str(it.get("author") or it.get("source_seat") or "白板").upper()
                kind = str(it.get("kind") or "").lower()
                if not kind:
                    if it.get("adopted") or it.get("pinned") or it.get("bucket") in ("chair_constraints", "carbon_plan"):
                        kind = "decision"
                    elif it.get("bucket") == "grok_risks":
                        kind = "risk"
                    else:
                        kind = "action"

                if kind == "decision":
                    nk = re.sub(r"\W+", "", t.lower())
                    if nk and nk not in seen_dec_exec:
                        seen_dec_exec.add(nk)
                        decision_pts.append(f"- [{author}] {t}")
                elif kind == "action":
                    has_structured_actions = True
                    if it.get("checked", True):
                        checked_action_pts.append(f"- [x] [{author}] {t}")
                    else:
                        unchecked_action_pts.append(f"- [ ] {t}")
                elif kind == "risk":
                    risk_pts.append(f"- [{author}] {t}")
        else:
            for x in whiteboard.get("carbon_plan") or []:
                if str(x).strip():
                    decision_pts.append(f"- [共识] {str(x).strip()}")
            for x in whiteboard.get("grok_risks") or []:
                if str(x).strip():
                    risk_pts.append(f"- [风险] {str(x).strip()}")
            for x in whiteboard.get("astra_actions") or []:
                if str(x).strip():
                    checked_action_pts.append(f"- [x] {str(x).strip()}")

        ref_budget = max(10000, int(getattr(self.settings, "max_ref_chars", MAX_ROUND_SOURCE_CHARS) or MAX_ROUND_SOURCE_CHARS))
        ref_corpus = "\n".join([topic] + decision_pts + checked_action_pts + risk_pts)
        ws_snapshot = await run_index_in_thread(build_workspace_context_snapshot, cwd, ref_corpus, None, ref_budget, False)
        has_real_project = bool(ws_snapshot)

        decisions_block = "\n".join(decision_pts) if decision_pts else "- 按议题目标与工程最佳实践推进"
        if has_structured_actions:
            actions_block = (
                "\n".join(checked_action_pts)
                if checked_action_pts
                else "- （当前白板任务清单中无已勾选任务项，请仅在遵循已确认共识的前提下输出最小必要交付）"
            )
        else:
            actions_block = "\n".join(checked_action_pts) if checked_action_pts else "- 依据已确认共识完成实施方案与代码交付"

        excluded_block = (
            "\n【已取消勾选的任务项（本次严禁执行或改动相关逻辑）】：\n" + "\n".join(unchecked_action_pts) + "\n"
            if unchecked_action_pts
            else ""
        )
        risks_block = "\n".join(risk_pts) if risk_pts else "- 注意边界输入、并发竞争与异常回退保护"

        if allow_workspace_write:
            mode_instruction = "（当前已授权写入本地项目工作区：请严格围绕已确认共识与已勾选任务直接修改或创建目标项目文件，并运行必要的语法/单测校验，完成后总结改动清单与验证结果）"
        elif has_real_project:
            mode_instruction = "（当前为只读安全预演模式：请勿改动磁盘文件，严格围绕已确认共识与已勾选任务输出完整详尽的实施方案与关键 Unified Diff 代码补丁预览）"
        else:
            mode_instruction = "（当前为方案交付模式：请输出一份结构严谨、细节完整、可直接实施的完整方案文档与验证清单）"

        exec_prompt = (
            f"你是本次会议指定的执行席位 {cfg.name}（当前角色职责：{pspec['label']}）。"
            f"请严格以「全部已确认共识与约束」+「已勾选的待执行任务项」为核心执行范围完成交付{mode_instruction}：\n"
            f"【议题】：{topic}\n"
            f"{ws_snapshot + chr(10) if ws_snapshot else ''}"
            f"【一、已确认共识与约束（核心准绳，必须全部遵循）】：\n{decisions_block}\n"
            f"【二、已勾选待执行任务清单（核心执行范围）】：\n{actions_block}\n"
            f"{excluded_block}"
            f"【三、风险审计与安全护栏参考（实施时须规避）】：\n{risks_block}\n"
        )

        eff_model = resolve_effective_model_for_driver(eff_drv, cfg.model, is_shared_fb=is_fb)
        exec_effort = normalize_model_effort(
            eff_drv,
            model=eff_model,
            effort=cfg.execution_effort or cfg.discussion_effort,
            help_text=help_text,
        )
        attempts = self._build_fallback_attempts(eff_drv, eff_model, exec_effort, help_text=help_text)

        if eff_drv != "codex":
            mode_label = "write:accept-edits" if allow_workspace_write else "readonly:plan"
            yield {
                "type": "term_log",
                "line": f"$ {os.path.basename(bpath)} [{cfg.name} · {DRIVER_SPECS[eff_drv]['cli_name']}] (cwd={cwd}, mode={mode_label})",
            }
            for idx, (cand_model, cand_effort) in enumerate(attempts):
                if eff_drv == "agy":
                    effort_spec = get_model_effort_spec("agy", model=cand_model, help_text=help_text)
                    agy_eff = (
                        WarmAntigravityProcess.normalize_agy_effort(
                            cand_effort,
                            help_text=help_text,
                            model=cand_model,
                        )
                        if effort_spec.get("supports_effort", True)
                        else ""
                    )
                    cmd = [bpath, "-p", exec_prompt]
                    if "--disable-slash-commands" in help_text:
                        cmd.append("--disable-slash-commands")
                    if "--output-format" in help_text:
                        cmd.extend(["--output-format", "stream-json"])
                    if cand_model.strip():
                        cmd.extend(["--model", cand_model.strip()])
                    if "--effort" in help_text and agy_eff:
                        cmd.extend(["--effort", agy_eff])
                    if allow_workspace_write:
                        if "--mode" in help_text:
                            cmd.extend(["--mode", "accept-edits"])
                        if "--dangerously-skip-permissions" in help_text:
                            cmd.append("--dangerously-skip-permissions")
                    else:
                        if "--sandbox" in help_text:
                            cmd.append("--sandbox")
                        elif "--mode" in help_text and "plan" in help_text and "--disable-slash-commands" not in help_text:
                            cmd.extend(["--mode", "plan"])
                elif eff_drv == "claude":
                    claude_eff = normalize_model_effort("claude", model=cand_model, effort=cand_effort, help_text=help_text)
                    cmd = [bpath, "-p", exec_prompt]
                    if "stream-json" in help_text or "--output-format" in help_text:
                        cmd.extend(["--output-format", "stream-json"])
                        if "--verbose" in help_text:
                            cmd.append("--verbose")
                    if cand_model.strip() and "--model" in help_text:
                        cmd.extend(["--model", cand_model.strip()])
                    if claude_eff and "--effort" in help_text:
                        cmd.extend(["--effort", claude_eff])
                    if allow_workspace_write:
                        if "--permission-mode" in help_text:
                            cmd.extend(["--permission-mode", "acceptEdits"])
                    else:
                        if "--tools" in help_text:
                            cmd.extend(["--tools", "Read,Grep,Glob,LS"])
                        elif "--permission-mode" in help_text:
                            cmd.extend(["--permission-mode", "plan"])
                elif DRIVER_SPECS.get(eff_drv, {}).get("cmd_template"):
                    tpl = DRIVER_SPECS[eff_drv]["cmd_template"]
                    cmd = [
                        str(tok).format(binary=bpath, model=cand_model, effort=cand_effort, prompt=exec_prompt, cwd=cwd)
                        for tok in tpl
                    ]
                else:
                    grok_eff = normalize_model_effort("grok", model=cand_model, effort=cand_effort, help_text=help_text)
                    cmd = [bpath, "-p", exec_prompt]
                    if "streaming-json" in help_text:
                        cmd.extend(["--output-format", "streaming-json"])
                    if cand_model.strip():
                        cmd.extend(["--model", cand_model.strip()])
                    if "--effort" in help_text and grok_eff:
                        cmd.extend(["--effort", grok_eff])
                    if not allow_workspace_write:
                        if "--tools" in help_text:
                            cmd.extend(["--tools", "read_file,list_dir,grep"])
                        if "--permission-mode" in help_text:
                            cmd.extend(["--permission-mode", "dontAsk"])

                exec_env, exec_tmp = self._prepare_isolated_call_env(session_id or "exec", target_aid)
                exec_atts = whiteboard.get("session_attachments") if isinstance(whiteboard, dict) else None
                if exec_atts and session_id:
                    att_b, _ = self._get_attachment_manager().stage_for_cli_turn(session_id, exec_atts, exec_tmp)
                    if att_b and len(cmd) >= 3 and cmd[1] == "-p":
                        cmd = list(cmd)
                        cmd[2] = f"{att_b}\n\n{exec_prompt}"
                sup_handle = await spawn_supervised_cli(
                    cmd,
                    cwd=cwd,
                    env=exec_env,
                    stdin=asyncio.subprocess.DEVNULL,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    limit=4 * 1024 * 1024,
                    wait_release=bool(on_pgid_spawned is not None),
                )
                if on_pgid_spawned is not None:
                    await on_pgid_spawned(sup_handle.pgid)
                    sup_handle.release_gate()
                proc = sup_handle.proc
                seat_exec_key = (session_id or "exec", target_aid)
                self._register_raw_proc(seat_exec_key, proc)
                stderr_task = asyncio.create_task(_read_stderr_tail(proc.stderr))
                exec_idle_sec = float(max(30, int(getattr(self.settings, "idle_timeout_sec", DEFAULT_IDLE_TIMEOUT_SEC) or DEFAULT_IDLE_TIMEOUT_SEC)))
                exec_turn_sec = float(max(60, int(getattr(self.settings, "turn_timeout_sec", DEFAULT_TURN_TIMEOUT_SEC) or DEFAULT_TURN_TIMEOUT_SEC)))
                exec_deadline = time.perf_counter() + exec_turn_sec
                try:
                    assert proc.stdout is not None
                    collected: List[str] = []
                    stream_err = ""
                    while True:
                        rem_exec = exec_deadline - time.perf_counter()
                        if rem_exec <= 0:
                            raise classify_cli_error(eff_drv, is_timeout=True, timeout_sec=exec_turn_sec, model=cand_model, effort=cand_effort)
                        try:
                            line_b = await asyncio.wait_for(proc.stdout.readline(), timeout=min(exec_idle_sec, rem_exec))
                        except asyncio.TimeoutError:
                            raise classify_cli_error(eff_drv, is_timeout=True, timeout_sec=min(exec_idle_sec, exec_turn_sec), model=cand_model, effort=cand_effort)
                        if not line_b:
                            break
                        line_s = line_b.decode("utf-8", errors="replace").rstrip("\r\n")
                        stripped_s = line_s.strip()
                        if not stripped_s or stripped_s.startswith("Finishing session") or stripped_s.startswith("warning:"):
                            continue
                        if eff_drv == "agy" and stripped_s.startswith("{"):
                            try:
                                evt = json.loads(stripped_s)
                                if evt.get("event") == "step_update":
                                    su = evt.get("step_update", {})
                                    st_type = su.get("step_type", "")
                                    if st_type == "agent_response" and su.get("text_delta"):
                                        delta_txt = su["text_delta"]
                                        collected.append(delta_txt)
                                        yield {"type": "exec_delta", "text": delta_txt}
                                    elif st_type and st_type != "agent_response":
                                        act = _format_cli_tool_activity("agy", su.get("tool_name", st_type), su, cwd=cwd)
                                        yield {"type": "term_log", "line": f"▶ {act or f'[{st_type}] 执行步骤推进中...'}"}
                                elif evt.get("event") == "result":
                                    res = evt.get("result", {})
                                    if res.get("status") not in ("SUCCESS", None):
                                        stream_err = str(res.get("error") or res.get("status") or "")
                                    if not collected and res.get("response"):
                                        collected.append(res["response"])
                                        yield {"type": "exec_delta", "text": res["response"]}
                                continue
                            except json.JSONDecodeError:
                                pass
                        elif eff_drv == "claude" and stripped_s.startswith("{"):
                            try:
                                evt = json.loads(stripped_s)
                                ctype = str(evt.get("type") or "")
                                if ctype in ("content_block_delta", "text_delta"):
                                    d_obj = evt.get("delta") if isinstance(evt.get("delta"), dict) else {}
                                    ctxt = str(d_obj.get("text") or evt.get("text") or "")
                                    if ctxt:
                                        collected.append(ctxt)
                                        yield {"type": "exec_delta", "text": ctxt}
                                elif ctype == "assistant" and not collected:
                                    msg_o = evt.get("message") if isinstance(evt.get("message"), dict) else {}
                                    c_blks = msg_o.get("content") if isinstance(msg_o.get("content"), list) else []
                                    joined_c = "".join(
                                        str(b.get("text") or "")
                                        for b in c_blks
                                        if isinstance(b, dict) and b.get("type") == "text"
                                    )
                                    if joined_c:
                                        collected.append(joined_c)
                                        yield {"type": "exec_delta", "text": joined_c}
                                elif ctype == "result":
                                    if evt.get("is_error"):
                                        stream_err = str(evt.get("result") or evt.get("error") or "Claude CLI error")
                                    elif not collected and evt.get("result"):
                                        r_txt = str(evt["result"])
                                        collected.append(r_txt)
                                        yield {"type": "exec_delta", "text": r_txt}
                                continue
                            except json.JSONDecodeError:
                                pass
                        elif eff_drv == "grok" and stripped_s.startswith("{"):
                            try:
                                evt = json.loads(stripped_s)
                                gtype = str(evt.get("type") or "")
                                if gtype in ("text", "text_delta"):
                                    gtxt = str(evt.get("data") or evt.get("text") or "")
                                    if gtxt:
                                        collected.append(gtxt)
                                        yield {"type": "exec_delta", "text": gtxt}
                                elif gtype in ("tool_call", "tool_call_update"):
                                    act = _format_cli_tool_activity("grok", evt.get("toolName") or evt.get("title") or "", evt, cwd=cwd)
                                    if act:
                                        yield {"type": "term_log", "line": f"▶ {act}"}
                                elif gtype == "error":
                                    stream_err = str(evt.get("message") or evt.get("error") or stream_err)
                                elif gtype == "end" and evt.get("error"):
                                    stream_err = str(evt["error"])
                                continue
                            except json.JSONDecodeError:
                                pass
                        chunk_line = line_s + "\n"
                        collected.append(chunk_line)
                        yield {"type": "exec_delta", "text": chunk_line}

                    rc = await proc.wait()
                    final_txt = "".join(collected).strip()
                    if rc or stream_err or not final_txt:
                        stderr_txt = await stderr_task
                        classified = classify_cli_error(
                            eff_drv,
                            raw_err=stream_err,
                            stderr=stderr_txt,
                            exit_code=rc,
                            model=cand_model,
                            effort=cand_effort,
                        )
                        if not collected and idx + 1 < len(attempts) and _is_model_or_effort_rejection(classified):
                            yield {"type": "term_log", "line": "↻ 当前档位受限，自动切换备用模型档位重试..."}
                            continue
                        raise classified

                    git_diff = await self._collect_git_diff_async(cwd) if allow_workspace_write else ""
                    if not git_diff and final_txt:
                        m = re.search(r"```(?:diff|patch)?\n(.*?)```", final_txt, flags=re.DOTALL)
                        if m:
                            git_diff = m.group(1).strip()
                    yield {"type": "term_log", "line": f"✔ {cfg.name} 执行任务已完成。"}
                    yield {
                        "type": "exec_artifact",
                        "executor_id": target_aid,
                        "executor_name": cfg.name,
                        "summary": final_txt or f"{cfg.name} 执行已完成。",
                        "diff": git_diff,
                    }
                    return
                finally:
                    self._unregister_raw_proc(seat_exec_key, proc)
                    stderr_task.cancel()
                    await terminate_and_reap_process_group(sup_handle, proc)
                    self._cleanup_isolated_call_tmp(exec_tmp)

        sandbox_mode = "workspace-write" if allow_workspace_write else "read-only"
        for idx, (cand_model, cand_effort) in enumerate(attempts):
            cmd = [bpath, "exec", "--json", "--skip-git-repo-check", "--sandbox", sandbox_mode]
            if cand_effort in CANONICAL_EFFORT_LEVELS:
                cmd.extend(["-c", f'model_reasoning_effort="{cand_effort}"'])
            if cand_model.strip():
                cmd.extend(["-m", cand_model.strip()])
            cmd.append("-")

            yield {"type": "term_log", "line": f"$ {' '.join(cmd[:-1])} <{cfg.name}决议指令> (cwd={cwd})"}

            exec_env, exec_tmp = self._prepare_isolated_call_env(session_id or "exec", target_aid)
            eff_codex_exec_prompt = exec_prompt
            exec_atts = whiteboard.get("session_attachments") if isinstance(whiteboard, dict) else None
            if exec_atts and session_id:
                att_b, exec_imgs = self._get_attachment_manager().stage_for_cli_turn(session_id, exec_atts, exec_tmp)
                if att_b:
                    eff_codex_exec_prompt = f"{att_b}\n\n{exec_prompt}"
                if exec_imgs and "--image" in help_text:
                    cmd = list(cmd[:-1])
                    for img_p in exec_imgs[:4]:
                        cmd.extend(["--image", img_p])
                    cmd.append("-")
            sup_handle = await spawn_supervised_cli(
                cmd,
                cwd=cwd,
                env=exec_env,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                limit=4 * 1024 * 1024,
                wait_release=bool(on_pgid_spawned is not None),
            )
            if on_pgid_spawned is not None:
                await on_pgid_spawned(sup_handle.pgid)
                sup_handle.release_gate()
            proc = sup_handle.proc
            seat_exec_key = (session_id or "exec", target_aid)
            self._register_raw_proc(seat_exec_key, proc)
            stderr_task = asyncio.create_task(_read_stderr_tail(proc.stderr))
            exec_idle_sec = float(max(30, int(getattr(self.settings, "idle_timeout_sec", DEFAULT_IDLE_TIMEOUT_SEC) or DEFAULT_IDLE_TIMEOUT_SEC)))
            exec_turn_sec = float(max(60, int(getattr(self.settings, "turn_timeout_sec", DEFAULT_TURN_TIMEOUT_SEC) or DEFAULT_TURN_TIMEOUT_SEC)))
            exec_deadline = time.perf_counter() + exec_turn_sec
            try:
                assert proc.stdin is not None and proc.stdout is not None
                proc.stdin.write(eff_codex_exec_prompt.encode("utf-8"))
                await proc.stdin.drain()
                proc.stdin.close()

                seen_lengths: Dict[str, int] = {}
                completed_msg_parts: List[str] = []
                stream_err = ""
                turn_failed = False
                while True:
                    rem_exec = exec_deadline - time.perf_counter()
                    if rem_exec <= 0:
                        raise classify_cli_error("codex", is_timeout=True, timeout_sec=exec_turn_sec, model=cand_model, effort=cand_effort)
                    try:
                        line_b = await asyncio.wait_for(proc.stdout.readline(), timeout=min(exec_idle_sec, rem_exec))
                    except asyncio.TimeoutError:
                        raise classify_cli_error("codex", is_timeout=True, timeout_sec=min(exec_idle_sec, exec_turn_sec), model=cand_model, effort=cand_effort)
                    if not line_b:
                        break
                    line_s = line_b.decode("utf-8", errors="replace").strip()
                    if not line_s:
                        continue
                    try:
                        evt = json.loads(line_s)
                    except json.JSONDecodeError:
                        yield {"type": "term_log", "line": line_s}
                        continue

                    etype = evt.get("type", "")
                    if etype == "turn.started":
                        yield {
                            "type": "term_log",
                            "line": f"[{cfg.name} · Codex] 已启动执行轮次 (model={cand_model or 'default'}, effort={cand_effort})...",
                        }
                    elif etype == "item.started":
                        item = evt.get("item", {})
                        itype = item.get("type", "")
                        if itype == "command_execution":
                            yield {"type": "term_log", "line": f"▶ 运行命令: {item.get('command', '')}"}
                        elif itype == "file_change":
                            yield {"type": "term_log", "line": "▶ 正在应用文件变更..."}
                    elif etype in ("item.updated", "item.completed"):
                        item = evt.get("item", {})
                        itype = item.get("type", "")
                        if itype == "agent_message":
                            item_id = str(item.get("id") or "default")
                            txt = item.get("text", "")
                            prev_len = seen_lengths.get(item_id, 0)
                            if len(txt) > prev_len:
                                if prev_len == 0 and completed_msg_parts:
                                    yield {"type": "exec_delta", "text": "\n\n"}
                                delta_piece = txt[prev_len:]
                                seen_lengths[item_id] = len(txt)
                                yield {"type": "exec_delta", "text": delta_piece}
                            if etype == "item.completed" and txt:
                                completed_msg_parts.append(txt)
                        elif itype == "command_execution" and etype == "item.completed":
                            exit_c = item.get("exit_code", 0)
                            yield {"type": "term_log", "line": f"✔ 命令完成 (exit={exit_c})"}
                        elif itype == "error":
                            stream_err = item.get("message") or stream_err
                    elif etype in ("error", "turn.failed"):
                        turn_failed = etype == "turn.failed" or turn_failed
                        err_obj = evt.get("error")
                        if isinstance(err_obj, dict):
                            err_m = err_obj.get("message") or str(err_obj)
                        else:
                            err_m = evt.get("message") or str(err_obj or "执行异常")
                        stream_err = err_m
                        yield {"type": "term_log", "line": f"✖ 错误: {err_m}"}

                rc = await proc.wait()
                final_message = "\n\n".join(completed_msg_parts).strip()
                if rc or turn_failed or not final_message:
                    stderr_txt = await stderr_task
                    classified = classify_cli_error(
                        "codex",
                        raw_err=stream_err,
                        stderr=stderr_txt,
                        exit_code=rc,
                        model=cand_model,
                        effort=cand_effort,
                    )
                    if not seen_lengths and idx + 1 < len(attempts) and _is_model_or_effort_rejection(classified):
                        next_m, next_e = attempts[idx + 1]
                        yield {
                            "type": "term_log",
                            "line": f"↻ 当前档位受限，自动回退至最高可用组合 ({next_m or 'default'} / {next_e})...",
                        }
                        continue
                    raise classified

                git_diff = await self._collect_git_diff_async(cwd) if allow_workspace_write else ""
                if not git_diff and final_message:
                    m = re.search(r"```(?:diff|patch)?\n(.*?)```", final_message, flags=re.DOTALL)
                    if m:
                        git_diff = m.group(1).strip()

                yield {"type": "term_log", "line": f"✔ {cfg.name} 执行任务已完成。"}
                yield {
                    "type": "exec_artifact",
                    "executor_id": target_aid,
                    "executor_name": cfg.name,
                    "summary": final_message or f"{cfg.name} 执行已完成。",
                    "diff": git_diff,
                }
                return
            finally:
                self._unregister_raw_proc(seat_exec_key, proc)
                stderr_task.cancel()
                await terminate_and_reap_process_group(sup_handle, proc)
                self._cleanup_isolated_call_tmp(exec_tmp)

    async def stream_astra_execution(
        self,
        topic: str,
        whiteboard: dict,
        allow_workspace_write: bool = False,
        session_workspace: str = "",
        agent_id: str = "astra",
        persona_key: str = "",
    ) -> AsyncGenerator[dict, None]:
        """向后兼容别名：转发至通用多席位执行引擎 stream_agent_execution。"""
        async for ev in self.stream_agent_execution(
            topic=topic,
            whiteboard=whiteboard,
            allow_workspace_write=allow_workspace_write,
            session_workspace=session_workspace,
            agent_id=agent_id,
            persona_key=persona_key,
        ):
            yield ev


def parse_structured_tail_with_kinds(
    full_text: str,
    seat_names: Optional[Dict[str, str]] = None,
) -> Tuple[str, List[dict]]:
    """模块级白板结构化尾标解析辅助函数：返回 (clean_body, wb_typed_items)。"""
    clean_body, _, _, wb_typed_items, _ = UnifiedAgentRunner.parse_structured_tail_with_kinds(
        full_text,
        seat_names=seat_names,
    )
    return clean_body, wb_typed_items
