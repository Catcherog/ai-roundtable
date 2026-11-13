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
import shutil
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import AsyncGenerator, Dict, List, Optional, Set, Tuple


_CACHED_LOGIN_PATH: Optional[str] = None
_CACHED_HOST_ENV: Optional[Dict[str, str]] = None

VALID_EFFORT_LEVELS = ("", "none", "low", "medium", "high", "xhigh", "max", "ultra")
CANONICAL_EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")
VALID_DRIVERS = ("auto", "agy", "grok", "codex")

PERSONA_PRESETS: Dict[str, dict] = {
    "planner": {
        "key": "planner",
        "label": "架构规划",
        "short_tag": "规划",
        "wb_title": "阶段规划共识",
        "cue_btn": "请 {name} 收敛",
        "cue_prompt": "请整合各方分歧，收敛出清晰的阶段优先级与取舍结论",
        "is_synthesizer": True,
        "prompt": (
            "思维模型：自顶向下拆解目标边界、明确取舍优先级、制定分阶段最小闭环路线并裁决各方分歧。"
            "严禁客套寒暄、禁止空洞附和或复述他人原话，只输出结构化边界裁决与明确取舍结论。"
        ),
    },
    "red_team": {
        "key": "red_team",
        "label": "红队挑刺",
        "short_tag": "挑刺",
        "wb_title": "风险防线与补充",
        "cue_btn": "请 {name} 挑刺",
        "cue_prompt": "请指出当前方案遗漏的边界条件、潜在风险与反例",
        "is_synthesizer": False,
        "prompt": (
            "思维模型：反向假设检验与第一性原理审计，专门寻找盲区、算不清的经济账、合规卡点、并发竞态与极端反例。"
            "绝对禁止任何“同意/赞同/说得好/整体可行/基本认可/补充一点”等客套赞同或缓和铺垫！"
            "首句必须直指实质漏洞、隐性错误假设或失效反例，至少指出 1–2 个致命边界并给出可执行硬防线。"
        ),
    },
    "implementer": {
        "key": "implementer",
        "label": "工程落地",
        "short_tag": "落地",
        "wb_title": "工程落地清单",
        "cue_btn": "请 {name} 评落地",
        "cue_prompt": "请评估具体改动文件范围、实施步骤与验证方式",
        "is_synthesizer": False,
        "prompt": (
            "思维模型：务实评估技术选型、实现复杂度、改动文件与函数范围、最小验证命令与交付工时。"
            "严禁客套附和、禁止重复宏观空话或盲从复杂抽象，对过度设计果断做减法，只给可直接编码落地的增量步骤。"
        ),
    },
    "fullstack_solo": {
        "key": "fullstack_solo",
        "label": "全栈主程",
        "short_tag": "主程",
        "wb_title": "全栈设计与执行清单",
        "cue_btn": "请 {name} 深化方案",
        "cue_prompt": "请深化核心架构设计、关键边界防线与可直接编码的文件级实施清单",
        "is_synthesizer": True,
        "prompt": (
            "思维模型：独当一面的全栈主程视角，统筹系统架构拆解、关键异常边界自检与文件级可执行实施步骤，"
            "严禁客套附和与复述已知信息，兼顾顶层设计与工程闭环，直奔高质量交付。"
        ),
    },
    "product_ux": {
        "key": "product_ux",
        "label": "产品交互",
        "short_tag": "交互",
        "wb_title": "体验与交互建议",
        "cue_btn": "请 {name} 审交互",
        "cue_prompt": "请从用户操作路径、信息降噪与异常状态反馈维度提出体验优化建议",
        "is_synthesizer": False,
        "prompt": (
            "思维模型：以用户直觉与高频操作流为核心，审视界面层级、信息密度降噪、默认态合理性、"
            "边界状态反馈与交互手感，严禁寒暄附和与重复前人观点，直接砍掉繁琐路径并给出可感知的体验升级点。"
        ),
    },
    "perf_sre": {
        "key": "perf_sre",
        "label": "性能稳定",
        "short_tag": "性能",
        "wb_title": "性能与稳定护栏",
        "cue_btn": "请 {name} 审性能",
        "cue_prompt": "请排查响应延迟瓶颈、并发竞争、资源泄漏与超时降级隐患",
        "is_synthesizer": False,
        "prompt": (
            "思维模型：聚焦端到端响应延迟、进程与内存回收、并发锁竞争、超时熔断与故障自愈护栏，"
            "严禁泛泛赞同或复述架构原话，以量化工程视角直指性能瓶颈与稳定性加固策略。"
        ),
    },
    "qa_audit": {
        "key": "qa_audit",
        "label": "测试验收",
        "short_tag": "测试",
        "wb_title": "测试与验收矩阵",
        "cue_btn": "请 {name} 列验收",
        "cue_prompt": "请梳理极端边界输入、回归检查矩阵与自动化验证方案",
        "is_synthesizer": False,
        "prompt": (
            "思维模型：站在严苛质量验收官视角，拆解正常流、异常流、空值越界与状态切换边界，"
            "严禁客套附和与笼统表态，直接输出可逐条勾选验证的测试用例矩阵与回归自检命令。"
        ),
    },
}

VALID_PERSONAS = tuple(PERSONA_PRESETS.keys())

DEFAULT_SEAT_PERSONAS: Dict[str, str] = {
    "carbon": "planner",
    "grok": "red_team",
    "astra": "implementer",
}

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
}

DEFAULT_TOP_MODELS: Dict[str, Tuple[str, str]] = {
    "carbon": ("gemini-4-carbon", "high"),
    "grok": ("grok-4.7", "xhigh"),
    "astra": ("gpt-6-astra", "max"),
}

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

DRIVER_FALLBACK_PATHS: Dict[str, List[str]] = {
    "agy": AGY_MACOS_FALLBACK_PATHS,
    "grok": [],
    "codex": CODEX_MACOS_FALLBACK_PATHS,
}

PROBE_CACHE_FILE = os.path.expanduser("~/.ai-roundtable/probe_cache.json")
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
    r"@([A-Za-z0-9_\u4e00-\u9fa5./-]+\.[A-Za-z0-9]{1,10})(?::[Ll]?(\d+)(?:-[Ll]?(\d+))?)?"
)

FULL_FILE_LINE_THRESHOLD = 350
MAX_SLICE_LINES = 400
MAX_ROUND_SOURCE_CHARS = 30000


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


def build_host_env() -> Dict[str, str]:
    """构建完整的宿主机环境变量并内存缓存；若父进程已完成登录 Shell 初始化则直接复用。"""
    global _CACHED_LOGIN_PATH, _CACHED_HOST_ENV
    if _CACHED_HOST_ENV is not None:
        return _CACHED_HOST_ENV.copy()

    env = os.environ.copy()
    home = os.path.expanduser("~")

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
            merged.insert(0, d)

    env["PATH"] = os.pathsep.join(merged)
    _CACHED_HOST_ENV = env
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
        out = subprocess.run(
            [binary_path, flag],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
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
    default_empty = os.path.realpath(os.path.expanduser("~/.ai-roundtable/workspace"))
    default_root = os.path.realpath(os.path.expanduser("~/.ai-roundtable"))
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
    all_items: List[dict] = []
    max_scan = 2500

    for root, dirs, files in os.walk(real_ws):
        dirs[:] = sorted(
            d
            for d in dirs
            if not d.startswith(".") and d not in _IGNORED_PROJECT_DIRS and not d.endswith(".app")
        )
        rel_dir = os.path.relpath(root, real_ws)
        depth = 0 if rel_dir == "." else rel_dir.count(os.sep) + 1
        if depth > 5:
            dirs[:] = []
            continue

        for fname in sorted(files):
            if fname.startswith("."):
                continue
            _, ext = os.path.splitext(fname)
            if ext.lower() in _BINARY_FILE_EXTS:
                continue
            full_p = os.path.join(root, fname)
            rel_p = fname if rel_dir == "." else f"{rel_dir.replace(os.sep, '/')}/{fname}"
            try:
                sz = os.path.getsize(full_p)
            except Exception:
                sz = 0
            all_items.append({"path": rel_p, "size_kb": round(max(sz, 1) / 1024.0, 1)})
            if len(all_items) >= max_scan:
                break
        if len(all_items) >= max_scan:
            break

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
    针对超过 350 行的长源码文件，提取「文件头部说明 + 函数/类/关键常量行号大纲骨架」，
    避免整份大文件全量注入造成 19 万字符级上下文爆炸，同时支持模型按行号范围精准只读一次。
    """
    total_lines = len(all_lines)
    ext = os.path.splitext(rel_path)[1].lower()

    # 1. 提取头部说明（前 32 行内的注释/模块说明/核心导入概览）
    header_lines: List[str] = []
    header_chars = 0
    for idx, raw_ln in enumerate(all_lines[:32], start=1):
        s_ln = raw_ln.rstrip()
        if not s_ln and len(header_lines) >= 4:
            continue
        clipped = s_ln[:140] + ("…" if len(s_ln) > 140 else "")
        entry = f"L{idx}: {clipped}"
        if header_chars + len(entry) > 1200:
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

    header_txt = "\n".join(header_lines) if header_lines else "（无文件头说明）"
    outline_txt = "\n".join(outline_items) if outline_items else f"  L1-L{total_lines}: （未检测到显式类/函数定义，可按行号分段只读）"
    skeleton = (
        f"[文件头部说明 (L1-L{min(total_lines, 32)})]\n{header_txt}\n\n"
        f"[函数/类/关键常量与结构行号大纲 (共 {total_lines} 行)]\n{outline_txt}\n\n"
        f"[按需精准读取指引] 该文件共 {total_lines} 行（>{FULL_FILE_LINE_THRESHOLD} 行已自动转为大纲骨架）；"
        f"已提供结构大纲的文件请勿全量重复读取，仅在确需某处实现细节时按上述 L起始-L结束 行号范围只读一次。"
    )
    return skeleton[:6200]


def extract_referenced_files_context(
    workspace_dir: str,
    reference_texts: str,
    max_files: int = 12,
    max_lines_per_file: int = MAX_SLICE_LINES,
    max_chars_per_file: int = 18000,
    max_total_chars: int = MAX_ROUND_SOURCE_CHARS,
    exclude_refs: Optional[Set[str]] = None,
) -> Tuple[str, Set[str]]:
    """
    解析文本中的 @path/to/file.ext 或 @path/to/file.ext:start-end 引用并构建高信噪比源码附件：
    - 支持 @path:start-end 按行号切片注入；
    - 引用整份文件且超过 350 行时，自动转为「文件头部说明 + 函数/类/关键常量行号大纲骨架」，禁止全量塞入；
    - 单轮源码附件总注入上限严格控制在 30,000 字符以内。
    """
    bound, real_ws = is_real_bound_workspace(workspace_dir)
    if not bound or not reference_texts:
        return "", set()

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
                e_ln = int(end_s) if end_s else min(total_lines, s_ln + max_lines_per_file - 1)
                if e_ln < s_ln:
                    s_ln, e_ln = e_ln, s_ln
                e_ln = min(total_lines, s_ln + max_lines_per_file - 1, e_ln)
                sliced = [f"L{ln_no}: {all_lines[ln_no - 1]}" for ln_no in range(s_ln, e_ln + 1)]
                body_txt = "\n".join(sliced)
                if len(body_txt) > max_chars_per_file:
                    body_txt = body_txt[:max_chars_per_file] + "\n... [片段超长已截断，请缩小行号区间]"
                range_label = f"行号切片 L{s_ln}–L{e_ln} / 共 {total_lines} 行"
                block = f"【引用源码片段 @{rel_raw}（{range_label}）】：\n```{ext}\n{body_txt}\n```"
            elif total_lines <= FULL_FILE_LINE_THRESHOLD:
                numbered_lines = [f"L{ln_no}: {ln_txt}" for ln_no, ln_txt in enumerate(all_lines, start=1)]
                body_txt = "\n".join(numbered_lines)
                if len(body_txt) > max_chars_per_file:
                    body_txt = body_txt[:max_chars_per_file] + "\n... [单文件字符超限已截断]"
                range_label = f"完整源码 L1–L{total_lines}（共 {total_lines} 行）"
                block = f"【引用源码 @{rel_raw}（{range_label}）】：\n```{ext}\n{body_txt}\n```"
            else:
                skeleton_txt = build_file_outline_skeleton(rel_raw, all_lines)
                range_label = f"结构大纲骨架（全文件共 {total_lines} 行 > {FULL_FILE_LINE_THRESHOLD} 行阈值）"
                block = f"【引用文件大纲 @{rel_raw}（{range_label}）】：\n```text\n{skeleton_txt}\n```"

            if not block.strip():
                continue

            remaining_budget = max_total_chars - used_chars
            if remaining_budget <= 320:
                blocks.append(f"【提示：已达单轮源码附件 {max_total_chars:,} 字符总预算上限，其余引用文件请按需用行号范围精准只读】")
                break
            if len(block) > remaining_budget:
                clipped_block = block[: max(260, remaining_budget - 110)].rstrip()
                if clipped_block.count("```") % 2 == 1:
                    clipped_block += "\n```"
                clipped_block += f"\n... [已达单轮源码附件 {max_total_chars:,} 字符上限，后续请按行号精准只读]"
                blocks.append(clipped_block)
                loaded_keys.add(ref_key)
                used_chars = max_total_chars
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
) -> str:
    """
    构建深度本地项目快照（3 层目录树 + 最多 5 份核心工程清单 + @文件名 智能大纲/切片源码），
    兼顾毫秒级读取速度与全栈代码架构全景感知，杜绝超大文件全量注入爆炸。
    """
    bound, real_ws = is_real_bound_workspace(workspace_dir)
    if not bound:
        return ""

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

    if prebuilt_ref_block is not None:
        ref_block = prebuilt_ref_block
    else:
        ref_block, _ = extract_referenced_files_context(real_ws, reference_texts)

    parts = [
        f"【当前绑定本地项目】：{os.path.basename(real_ws)} ({real_ws})",
        "【项目目录结构快照（支持用 @相对路径 或 @相对路径:起始行-结束行 引用源码）】：\n" + "\n".join(tree_lines),
    ]
    if manifest_snippets:
        parts.append("\n\n".join(manifest_snippets))
    if ref_block:
        parts.append(ref_block)
    return "\n\n".join(parts)


def _safe_terminate_proc(proc: Optional[asyncio.subprocess.Process]) -> None:
    if proc and proc.returncode is None:
        try:
            proc.kill()
        except Exception:
            pass


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

    allowed = [e for e in CANONICAL_EFFORT_LEVELS if e in matched_spec["allowed"]]
    if drv == "agy" and help_text and "--effort" in help_text:
        filtered = [
            e for e in allowed if (e in ("low", "medium", "high") or e in help_text)
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
    if e in CANONICAL_EFFORT_LEVELS:
        req_idx = CANONICAL_EFFORT_LEVELS.index(e)
        lower_or_eq = [
            cand for cand in allowed if CANONICAL_EFFORT_LEVELS.index(cand) <= req_idx
        ]
        return lower_or_eq[-1] if lower_or_eq else allowed[0]
    return spec["default"]


def export_model_effort_catalog() -> dict:
    """导出前端可直接消费的「CLI 驱动 + 模型名」推理档位能力表与驱动默认参数。"""
    drivers_info: Dict[str, dict] = {}
    for drv, dspec in DRIVER_SPECS.items():
        drivers_info[drv] = {
            "cli_name": dspec["cli_name"],
            "default_model": dspec["default_model"],
            "default_discuss_effort": dspec["default_discuss_effort"],
            "default_exec_effort": dspec["default_exec_effort"],
            "models": MODEL_EFFORT_CAPABILITIES.get(drv, {}),
        }
    return {
        "canonical_efforts": list(CANONICAL_EFFORT_LEVELS),
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
            "可直接点击卡片内「降档并单席重试」或「原档重试」。"
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
            "请稍候片刻点击「单席重试」或切换其他可用 CLI。"
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
        if self.driver in ("agy", "grok", "codex"):
            return self.driver
        return DEFAULT_SEAT_DRIVERS.get(self.agent_id, "agy")

    def detect_primary_binary(self) -> Optional[str]:
        drv = self.preferred_driver_key()
        spec = DRIVER_SPECS[drv]
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
            for cand_drv in ("agy", "codex", "grok"):
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


@dataclass
class RuntimeSettings:
    workspace_dir: str = field(default_factory=lambda: os.getcwd())
    allow_single_cli_fallback: bool = True
    idle_timeout_sec: int = 90
    turn_timeout_sec: int = 300
    agents: Dict[str, AgentRoleConfig] = field(default_factory=dict)

    @classmethod
    def create_default(cls, workspace_dir: str) -> "RuntimeSettings":
        return cls(
            workspace_dir=workspace_dir,
            allow_single_cli_fallback=True,
            agents={
                "carbon": AgentRoleConfig(
                    agent_id="carbon",
                    name="Carbon",
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
                    name="Grok",
                    title="挑刺",
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
                    name="Astra",
                    title="落地",
                    cli_name="Codex CLI",
                    binary_candidates=["codex"],
                    fallback_paths=list(CODEX_MACOS_FALLBACK_PATHS),
                    driver="codex",
                    persona="implementer",
                    model=DEFAULT_TOP_MODELS["astra"][0],
                    discussion_effort=DEFAULT_TOP_MODELS["astra"][1],
                    execution_effort=DEFAULT_TOP_MODELS["astra"][1],
                ),
            },
        )

    def inspect_status(self) -> Dict[str, dict]:
        """三路并发探测所有 CLI 元信息并统一落盘缓存，真实反馈实际运行模型、合法推理档位与预设身份状态。"""
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

        # 统计底层生效 CLI 驱动复用数，用于在状态面板清晰展示同源多角模式
        drv_counts: Dict[str, int] = {}
        probed_map: Dict[str, Tuple[Optional[str], str, str, str, bool]] = {}
        for aid, cfg in items:
            pinfo = cfg.get_probe_info(
                persist_cache=False,
                allow_single_cli_fallback=self.allow_single_cli_fallback,
            )
            probed_map[aid] = pinfo
            if pinfo[0]:
                drv_counts[pinfo[3]] = drv_counts.get(pinfo[3], 0) + 1

        result: Dict[str, dict] = {}
        for aid, cfg in items:
            bpath, ver, help_text, eff_drv, is_shared_fb = probed_map[aid]
            eff_spec = DRIVER_SPECS.get(eff_drv, DRIVER_SPECS["agy"])
            effective_model = resolve_effective_model_for_driver(
                eff_drv,
                cfg.model,
                is_shared_fb=is_shared_fb,
            )
            shared_multi_seat = is_shared_fb or (bool(bpath) and drv_counts.get(eff_drv, 0) > 1)

            display_cli_name = eff_spec["cli_name"]
            if shared_multi_seat:
                display_cli_name = f"{eff_spec['cli_name']} (单CLI多角)"

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

            result[aid] = {
                "agent_id": aid,
                "name": cfg.name,
                "title": pspec["short_tag"],
                "persona": pspec["key"],
                "persona_label": pspec["label"],
                "wb_title": pspec["wb_title"],
                "driver": cfg.driver,
                "effective_driver": eff_drv,
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
        self.proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.cwd if os.path.isdir(self.cwd) else None,
            env=build_host_env(),
            limit=4 * 1024 * 1024,
        )

    async def stream_turn(self, prompt: str) -> AsyncGenerator[dict, None]:
        async with self._lock:
            await self.ensure_started()
            assert self.proc and self.proc.stdin and self.proc.stdout
            payload = json.dumps({"event": "user", "message": {"content": prompt}}, ensure_ascii=False) + "\n"
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
                        self.proc = None
                        self.turn_count = 0
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
                                act = "正在深度推演方案与边界…"
                                if act != last_activity:
                                    last_activity = act
                                    yield {"type": "activity", "text": act}
                        elif st_type == "tool" and su.get("state") in ("ACTIVE", "RUNNING", None):
                            saw_tool_since_text = True
                            act = _format_cli_tool_activity("agy", su.get("tool_name", ""), su, cwd=self.cwd)
                            if act and act != last_activity:
                                last_activity = act
                                yield {"type": "activity", "text": act}
                        elif st_type in ("thinking", "thought") and not emitted:
                            act = "正在深度推演方案与边界…"
                            if act != last_activity:
                                last_activity = act
                                yield {"type": "activity", "text": act}
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
        if self.proc and self.proc.returncode is None:
            try:
                if self.proc.stdin:
                    self.proc.stdin.close()
                self.proc.kill()
            except Exception:
                pass
        self.proc = None
        self.turn_count = 0


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
        self._prewarmed_agy: Optional[WarmAntigravityProcess] = None
        self._warm_agy_pool: Dict[Tuple[str, str], WarmAntigravityProcess] = {}
        self._codex_threads: Dict[Tuple[str, str], str] = {}
        self._last_seen_msg_idx: Dict[Tuple[str, str], int] = {}
        self._last_persona_by_seat: Dict[Tuple[str, str], str] = {}
        self._injected_refs: Dict[Tuple[str, str], Set[str]] = {}
        self._binary_semaphores: Dict[str, asyncio.Semaphore] = {}

    def _get_binary_semaphore(self, binary_path: str) -> asyncio.Semaphore:
        sem = self._binary_semaphores.get(binary_path)
        if sem is None:
            sem = asyncio.Semaphore(1)
            self._binary_semaphores[binary_path] = sem
        return sem

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
            if prewarm_eff in ("xhigh", "max") and not cfg.lock_discussion_effort and "high" in (effort_spec.get("allowed") or []):
                prewarm_eff = "high"
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

    async def shutdown(self) -> None:
        if self._prewarmed_agy:
            await self._prewarmed_agy.close()
            self._prewarmed_agy = None
        for proc in list(self._warm_agy_pool.values()):
            await proc.close()
        self._warm_agy_pool.clear()

    @staticmethod
    def _discussion_sandbox_cwd() -> str:
        discuss_dir = os.path.expanduser("~/.ai-roundtable/discuss_sandbox")
        try:
            os.makedirs(discuss_dir, exist_ok=True)
            return discuss_dir
        except Exception:
            return tempfile.gettempdir()

    def _effective_workspace_cwd(self, session_workspace: str = "") -> str:
        raw = session_workspace.strip() if session_workspace else self.settings.workspace_dir
        home = os.path.realpath(os.path.expanduser("~"))
        if raw and os.path.isdir(raw):
            if os.path.realpath(raw) != home:
                return raw
        safe_ws = os.path.expanduser("~/.ai-roundtable/workspace")
        try:
            os.makedirs(safe_ws, exist_ok=True)
            return safe_ws
        except Exception:
            return tempfile.gettempdir()

    def _require_binary(
        self,
        agent_id: str,
        override: Optional[dict] = None,
    ) -> Tuple[AgentRoleConfig, str, str, str, bool]:
        base_cfg = self.settings.agents[agent_id]
        if isinstance(override, dict) and override:
            drv = str(override.get("driver", base_cfg.driver) or base_cfg.driver).strip().lower()
            if drv not in ("auto", "agy", "grok", "codex"):
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
                f"未检测到 {spec['cli_name']} 可执行文件（查找命令：{cands}）。请确认已在终端安装，或在「配置」中指定路径或使用「单 CLI 分饰三席」。",
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
    def _format_whiteboard_for_prompt(whiteboard: dict) -> str:
        """
        拼装白板上下文摘要：优先全量注入「已置顶 / 已采纳共识项」，其次补充近期未置顶讨论摘录，
        同时平滑兼容旧版仅含纯字符串数组的会话白板。
        """
        seat_labels = {"carbon": "Carbon", "grok": "Grok", "astra": "Astra", "chair": "主持"}
        raw_items = whiteboard.get("items")
        if isinstance(raw_items, list) and raw_items:
            confirmed_lines: List[str] = []
            excerpt_lines: List[str] = []
            for it in raw_items:
                if not isinstance(it, dict) or it.get("bucket") == "chair_constraints":
                    continue
                txt = str(it.get("text") or "").strip()
                if not txt:
                    continue
                src = seat_labels.get(str(it.get("source_seat") or "").lower(), "白板")
                if it.get("pinned") or it.get("adopted"):
                    confirmed_lines.append(f"  · [{src}] {txt}")
                else:
                    excerpt_lines.append(f"  · [{src}] {txt}")

            sections: List[str] = []
            if confirmed_lines:
                sections.append("【白板已确认共识与置顶决策（最高优先级）】：\n" + "\n".join(confirmed_lines[:30]))
            if excerpt_lines:
                sections.append("【近期白板讨论摘录】：\n" + "\n".join(excerpt_lines[-16:]))
            return ("\n" + "\n".join(sections)) if sections else ""

        wb_digest_parts: List[str] = []
        for wb_label, wb_key in (
            ("Carbon要点", "carbon_plan"),
            ("Grok要点", "grok_risks"),
            ("Astra要点", "astra_actions"),
        ):
            pts = whiteboard.get(wb_key) or []
            if pts:
                wb_digest_parts.append(f"  · {wb_label}：{'；'.join(pts[-8:])}")
        return ("\n【当前白板已沉淀要点】：\n" + "\n".join(wb_digest_parts)) if wb_digest_parts else ""

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
    ) -> str:
        seat_names = {"carbon": "Carbon", "grok": "Grok", "astra": "Astra"}
        seat_display = seat_names.get(agent_id, agent_id.capitalize())
        pspec = get_persona_spec(persona_key, fallback_agent_id=agent_id)
        role_header = f"你是圆桌席位中的 {seat_display}，当前担任【{pspec['label']}】。{pspec['prompt']}"
        if is_solo_mode:
            role_header += "（当前为单席位独奏模式：由你独立向主持人汇报，无需点名其他 AI 成员，请直接给出结构完整、可直接推进执行的核心结论。）"
        elif shared_cli_roster:
            role_header += (
                f"\n【单 CLI 多席独立扮演铁律】：本场圆桌由同一底层 CLI 无状态分次饰演多席（参会阵容：{shared_cli_roster}）。"
                f"你本轮仅代表【{seat_display} · {pspec['label']}】，严禁复述前序席位原话或客套附和（禁止出现“同意/赞同/说得好/整体可行/补充一点”），"
                "必须独立输出你专属身份视角的增量判断、尖锐挑刺或具体修正！"
            )

        constraints = "；".join(whiteboard.get("chair_constraints", [])) or "无"
        wb_digest = cls._format_whiteboard_for_prompt(whiteboard)

        # 独立长文决议通道：彻底解除字数限制
        if stage == "synthesis":
            synth_instruction = cue_instruction or (
                "请基于完整会议讨论、白板已确认共识与主持约束，输出一份完整详尽、可直接落地的《会议最终决议》"
            )
            synth_tail = (
                "只读汇总严禁调用工具修改磁盘文件，也严禁调用任何 shell 命令或脚本统计字数；篇幅不设上限，请以结构清晰、细节完整、可直接交由工程师照单执行为准（包含：1. 核心架构结论与取舍；2. 分阶段文件级实施清单；3. 关键边界风险防线与验收标准）。\n"
                "末尾必须独立换行附带两行结构化标记（禁止省略）：\n"
                "[白板: 一条核心决议结论；第二条关键实施动作（可选）]\n"
                "[状态: 决议已成 | 共识: 已达成 | 点名: 无]"
            )
            if incremental_only and recent_messages:
                delta_lines = cls._format_transcript_within_budget(recent_messages, max_messages=40, max_chars=80000)
                ref_section = f"\n{extra_ref_block}\n" if extra_ref_block else ""
                return (
                    f"【当前环节：形成最终会议决议】{synth_instruction}\n"
                    f"【最新主持约束】：{constraints}"
                    f"{wb_digest}"
                    f"{ref_section}\n"
                    f"【本轮补充发言】：\n{delta_lines}\n\n"
                    f"要求：{synth_tail}"
                )

            transcript = cls._format_transcript_within_budget(recent_messages) or "（暂无前序发言）"
            ws_block = f"{workspace_snapshot}\n\n" if workspace_snapshot else ""
            return (
                f"{role_header}\n"
                f"【当前环节：形成最终会议决议】{synth_instruction}\n"
                f"【会议模式】：{collab_mode}\n"
                f"【议题】：{topic}\n"
                f"【主持要求】：{constraints}"
                f"{wb_digest}\n\n"
                f"{ws_block}"
                f"【会议完整讨论记录】：\n{transcript}\n\n"
                f"要求：{synth_tail}"
            )

        stage_desc = {
            "opening": (
                "【当前环节：独奏方案初评】请立足你的当前身份视角，直接针对议题给出清晰完整的方案设计、关键边界与实施要点。"
                if is_solo_mode
                else "【当前环节：首轮独立初评】请严格立足你的专属身份视角独立审视议题，直击核心判断、具体路径或锋利漏洞，严禁空泛寒暄、禁止客套附和或复述前序席位观点。"
            ),
            "cross_talk": (
                "【当前环节：交叉交锋与边界收敛】绝对禁止“同意/@某人说得好/整体可行/补充一点”等空洞客套附和，禁止复述前人已达成观点！"
                "请深度推进讨论：1) 对已达成共识项补充关键边界条件、极端异常防线或明确验收标准；"
                "2) 对存在分歧或盲区的方案给出具体反例、技术依据与可落地的折中方案（可用 @Carbon / @Grok / @Astra 定向质询）。"
            ),
            "interrupt_reply": "【当前环节：响应主持人指示】请根据主持人最新补充约束输出增量调整、边界防线或深化方案，禁止复述旧话与客套附和。",
            "cue": f"【当前环节：主持人点名提问】具体问题：{cue_instruction}",
        }.get(stage, "【当前环节：会议讨论】")

        mention_hint = "无" if is_solo_mode else "@Carbon或@Grok或@Astra或无"
        if stage in ("cue", "interrupt_reply"):
            structure_guide = "请聚焦问题充分展开核心论点（含判断依据、具体改法与验收边界，篇幅按分析深度自然舒展）"
        elif is_solo_mode:
            structure_guide = "请展开 3–4 个核心模块要点（含判断依据、取舍理由与具体实施改法，篇幅自然舒展）"
        else:
            structure_guide = "请展开 2–4 个核心论点（每点均需包含明确判断依据与具体改法/验收条件，篇幅自然舒展，不设死板字数硬区间）"

        tail_rule = (
            f"{structure_guide}；严禁客套附和；"
            "圆桌讨论阶段仅允许按需精准只读源码（已提供结构大纲或片段的文件请勿全量重复读取；单轮只读查看请收敛在 1–3 处最关键代码段以内，禁止全仓遍历扫盘），严禁修改任何磁盘文件，"
            "严禁调用任何 shell 命令、脚本或工具去统计字数、计算篇幅或自我删改截断！"
            "正文中禁止输出“我先只读某文件/我先核对源码路径”等工具执行独白，直接输出完整分析结论。\n"
            "末尾请独立换行附带两行结构化标记（独立提取，不挤压正文分析深度）：\n"
            "[白板: 一条精炼可执行结论；第二条可执行结论（可选）]\n"
            f"[状态: 核心立场摘要 | 共识: 已达成或需继续 | 点名: {mention_hint}]"
        )

        if incremental_only and recent_messages:
            delta_lines = cls._format_transcript_within_budget(recent_messages, max_messages=30, max_chars=70000)
            ref_section = f"\n{extra_ref_block}\n" if extra_ref_block else ""
            return (
                f"【你当前身份】：{seat_display} · {pspec['label']}\n"
                f"{stage_desc}\n"
                f"【最新主持约束】：{constraints}"
                f"{wb_digest}"
                f"{ref_section}\n"
                f"【上一轮新增发言】：\n{delta_lines}\n\n"
                f"请严格站在【{pspec['label']}】立场回应（{tail_rule}）"
            )

        transcript = cls._format_transcript_within_budget(recent_messages) or (
            "（当前为独奏首轮方案设计）" if is_solo_mode else "（当前为首轮并发初评，尚无他人发言）"
        )
        ws_block = f"{workspace_snapshot}\n\n" if workspace_snapshot else ""
        return (
            f"{role_header}\n"
            f"{stage_desc}\n"
            f"【会议模式】：{collab_mode}\n"
            f"【议题】：{topic}\n"
            f"【主持要求】：{constraints}"
            f"{wb_digest}\n\n"
            f"{ws_block}"
            f"【会议讨论记录】：\n{transcript}\n\n"
            f"要求：{tail_rule}"
        )

    @classmethod
    def parse_structured_tail(cls, full_text: str) -> Tuple[str, str, Optional[str], List[str], Optional[bool]]:
        """
        独立解析末尾 [白板: ...] 与 [状态: ... | 共识: ... | 点名: ...] 结构化标记，
        兼容顺序互换与 CLI 尾部状态行清理，确保完整保留正文分析内容。
        返回 (clean_body, badge, target, wb_points, consensus_reached)。
        """
        raw_clean = re.sub(r"(?:\r?\n)*Finishing session[….]*\s*$", "", (full_text or "").strip())
        working = raw_clean.strip()
        wb_points: List[str] = []
        consensus_reached: Optional[bool] = None
        badge = "发言完成"
        target: Optional[str] = None

        status_pat = re.compile(
            r"\[(?:状态|徽章)[:：]\s*([^\]|｜]+?)"
            r"(?:\s*[|｜]\s*共识[:：]\s*([^\]|｜]+?))?"
            r"(?:\s*[|｜]\s*点名[:：]\s*@?([A-Za-z\u4e00-\u9fa5]+))?\s*\]\s*$"
        )
        wb_pat = re.compile(r"\[白板(?:要点)?[:：]\s*([^\]]+)\]\s*$")

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
                target = raw_target if raw_target in ("carbon", "grok", "astra") else None
                continue

            m_wb = wb_pat.search(working)
            if m_wb:
                candidate_body = working[: m_wb.start()].strip()
                if candidate_body:
                    working = candidate_body
                raw_items = re.split(r"[；;｜|\n]+", m_wb.group(1))
                for item in raw_items:
                    cleaned_item = re.sub(r"^(?:\d+[.)、]|[-*•])\s*", "", item.strip())
                    if len(cleaned_item) >= 4 and cleaned_item not in ("无", "暂无"):
                        wb_points.append(cleaned_item[:160])
                continue
            break

        return working, badge, target, wb_points[:2], consensus_reached

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
        sem = self._get_binary_semaphore(bpath)
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
    ) -> AsyncGenerator[dict, None]:
        start_ts = time.perf_counter()
        ttft_ms: Optional[int] = None
        cfg, bpath, help_text, eff_drv, is_fb = self._require_binary(agent_id)

        eff_persona = persona_key if persona_key in PERSONA_PRESETS else cfg.persona
        seen_key = (session_id, agent_id)
        persona_switched = self._last_persona_by_seat.get(seen_key) != eff_persona
        eff_ws = session_workspace or self.settings.workspace_dir

        has_mem = False if stateless else self._has_active_session_memory(session_id, agent_id, eff_drv)
        prev_seen = self._last_seen_msg_idx.get(seen_key, 0)
        already_injected = self._injected_refs.setdefault(seen_key, set())
        newly_loaded_refs: Set[str] = set()

        if has_mem and not persona_switched and all_completed_count > prev_seen and prev_seen > 0:
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
                exclude_refs=already_injected,
            )
        else:
            msgs_for_prompt = recent_messages
            incremental = False
            extra_ref_block = ""
            ref_corpus = "\n".join(
                [topic, cue_instruction]
                + (whiteboard.get("chair_constraints") or [])
                + [m["content"] for m in recent_messages[-20:]]
            )
            full_ref_block, newly_loaded_refs = extract_referenced_files_context(eff_ws, ref_corpus)
            ws_snapshot = build_workspace_context_snapshot(
                eff_ws,
                reference_texts=ref_corpus,
                prebuilt_ref_block=full_ref_block,
            )

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
        )

        eff_model = resolve_effective_model_for_driver(eff_drv, cfg.model, is_shared_fb=is_fb)
        eff_effort = normalize_model_effort(
            eff_drv,
            model=eff_model,
            effort=cfg.discussion_effort,
            help_text=help_text,
        )
        effort_spec = get_model_effort_spec(eff_drv, model=eff_model, help_text=help_text)
        # 第 1–2 轮讨论阶段（opening / cross_talk）若配置为 xhigh/max 且未显式强锁，默认自动降为 high 档提速
        if (
            stage in ("opening", "cross_talk")
            and eff_effort in ("xhigh", "max")
            and not getattr(cfg, "lock_discussion_effort", False)
            and "high" in (effort_spec.get("allowed") or [])
        ):
            eff_effort = "high"

        chunks: List[str] = []
        bound_ws, real_ws = is_real_bound_workspace(eff_ws)
        discuss_cwd = real_ws if bound_ws else self._discussion_sandbox_cwd()
        sem = self._get_binary_semaphore(bpath)

        idle_timeout = float(max(20, int(getattr(self.settings, "idle_timeout_sec", 90) or 90)))
        base_turn_cap = float(max(60, int(getattr(self.settings, "turn_timeout_sec", 300) or 300)))
        total_timeout = max(base_turn_cap, 420.0) if stage == "synthesis" else base_turn_cap

        async with sem:
            stream_iter = self._stream_with_fallback(
                session_id=session_id,
                agent_id=agent_id,
                driver_key=eff_drv,
                model=eff_model,
                effort=eff_effort,
                binary_path=bpath,
                help_text=help_text,
                prompt=prompt,
                use_warm=not stateless,
                cwd_override=discuss_cwd,
                discuss_readonly=True,
            ).__aiter__()
            hard_deadline = time.perf_counter() + total_timeout
            try:
                while True:
                    now_ts = time.perf_counter()
                    total_rem = hard_deadline - now_ts
                    if total_rem <= 0:
                        raise asyncio.TimeoutError("turn_cap_exceeded")
                    step_wait = max(1.0, min(idle_timeout, total_rem))
                    try:
                        ev = await asyncio.wait_for(stream_iter.__anext__(), timeout=step_wait)
                    except StopAsyncIteration:
                        break
                    ev_type = ev.get("type")
                    if ev_type == "activity":
                        act_txt = str(ev.get("text") or "").strip()
                        if act_txt:
                            yield {"type": "activity", "text": act_txt}
                    elif ev_type == "delta":
                        delta = ev.get("text") or ""
                        if delta:
                            if ttft_ms is None:
                                ttft_ms = int((time.perf_counter() - start_ts) * 1000)
                            chunks.append(delta)
                            yield {"type": "delta", "text": delta}
            except asyncio.TimeoutError:
                partial_now = "".join(chunks).strip()
                if len(partial_now) < 80:
                    hit_total = time.perf_counter() >= (hard_deadline - 0.5)
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

        if newly_loaded_refs:
            already_injected.update(newly_loaded_refs)
        self._last_persona_by_seat[seen_key] = eff_persona
        if all_completed_count >= 0:
            self._last_seen_msg_idx[seen_key] = all_completed_count + 1

        clean_body, badge, target, wb_points, consensus_reached = self.parse_structured_tail(full_raw)
        if is_solo_mode or stage == "synthesis":
            target = None
        elapsed_ms = int((time.perf_counter() - start_ts) * 1000)
        yield {
            "type": "done",
            "full_text": clean_body,
            "badge": badge,
            "target": target,
            "wb_points": wb_points,
            "consensus": consensus_reached,
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
    ) -> AsyncGenerator[dict, None]:
        """按候选模型与推理档位顺序尝试流式请求；单次波动回退不再篡改用户保存的配置。"""
        attempts = self._build_fallback_attempts(driver_key, model, effort, help_text=help_text)
        last_exc: Optional[Exception] = None

        for cand_model, cand_effort in attempts:
            emitted_delta = False
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
                ):
                    if ev.get("type") == "delta" and ev.get("text"):
                        emitted_delta = True
                    yield ev
                if emitted_delta:
                    return
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                last_exc = exc
                if emitted_delta or not _is_model_or_effort_rejection(exc):
                    raise
                continue

        if last_exc:
            raise last_exc

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
    ) -> AsyncGenerator[dict, None]:
        cwd = cwd_override if (cwd_override and os.path.isdir(cwd_override)) else self._effective_workspace_cwd()
        env = build_host_env()
        seat_key = (session_id, agent_id)

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
                    async for ev in warm_inst.stream_turn(prompt):
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

            cmd = [binary_path, "-p", prompt]
            if has_disable_slash:
                cmd.append("--disable-slash-commands")
            if discuss_readonly and "--sandbox" in help_text:
                cmd.append("--sandbox")
            if supports_stream_json:
                cmd.extend(["--output-format", "stream-json"])
            if model:
                cmd.extend(["--model", model])
            if has_effort and agy_effort:
                cmd.extend(["--effort", agy_effort])

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=env,
                limit=4 * 1024 * 1024,
            )
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
                                elif st_type == "tool" and su.get("state") in ("ACTIVE", "RUNNING", None):
                                    saw_tool_since_text = True
                                    act = _format_cli_tool_activity("agy", su.get("tool_name", ""), su, cwd=cwd)
                                    if act and act != last_activity:
                                        last_activity = act
                                        yield {"type": "activity", "text": act}
                                elif st_type in ("thinking", "thought") and not emitted:
                                    act = "正在深度推演方案与边界…"
                                    if act != last_activity:
                                        last_activity = act
                                        yield {"type": "activity", "text": act}
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
                if not emitted:
                    err_txt = (await proc.stderr.read()).decode("utf-8", errors="replace").strip() if proc.stderr else ""
                    raise classify_cli_error(
                        "agy",
                        raw_err=stream_err,
                        stderr=err_txt,
                        exit_code=rc,
                        model=model,
                        effort=agy_effort,
                    )
                return
            finally:
                _safe_terminate_proc(proc)

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

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=env,
                limit=4 * 1024 * 1024,
            )
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
                            act = _format_cli_tool_activity("grok", tname, evt, cwd=cwd)
                            if act and act != last_activity:
                                last_activity = act
                                yield {"type": "activity", "text": act}
                        elif etype in ("thinking", "reasoning") and not emitted:
                            act = "正在深度推演方案与边界…"
                            if act != last_activity:
                                last_activity = act
                                yield {"type": "activity", "text": act}
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
                # 只要本回合已生成有效分析正文（即便后续工具被权限拦截提前结束），一律完整保留已输出正文
                if not emitted:
                    err_txt = (await proc.stderr.read()).decode("utf-8", errors="replace").strip() if proc.stderr else ""
                    raise classify_cli_error(
                        "grok",
                        raw_err=stream_err,
                        stderr=err_txt,
                        exit_code=rc,
                        model=model,
                        effort=grok_eff,
                    )
                return
            finally:
                _safe_terminate_proc(proc)

        existing_tid = self._codex_threads.get(seat_key) if use_warm else None
        codex_eff = normalize_model_effort("codex", model=model, effort=effort, help_text=help_text)
        cmd = [binary_path, "exec", "--json", "--skip-git-repo-check", "--sandbox", "read-only"]
        if codex_eff in CANONICAL_EFFORT_LEVELS:
            cmd.extend(["-c", f'model_reasoning_effort="{codex_eff}"'])
        if model:
            cmd.extend(["-m", model])
        if existing_tid:
            cmd.extend(["resume", existing_tid, "-"])
        else:
            cmd.append("-")

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=env,
            limit=4 * 1024 * 1024,
        )
        try:
            assert proc.stdin is not None and proc.stdout is not None
            proc.stdin.write(prompt.encode("utf-8"))
            await proc.stdin.drain()
            proc.stdin.close()

            seen_lengths: Dict[str, int] = {}
            completed_item_count = 0
            emitted = False
            last_activity = ""
            stream_err = ""
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
                if etype == "thread.started" and evt.get("thread_id") and use_warm:
                    self._codex_threads[seat_key] = evt["thread_id"]
                elif etype == "item.started":
                    item = evt.get("item", {})
                    itype = item.get("type", "")
                    act = _format_cli_tool_activity("codex", itype, item, cwd=cwd)
                    if act and act != last_activity:
                        last_activity = act
                        yield {"type": "activity", "text": act}
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
                    elif itype == "command_execution" and etype == "item.updated":
                        act = _format_cli_tool_activity("codex", itype, item, cwd=cwd)
                        if act and act != last_activity:
                            last_activity = act
                            yield {"type": "activity", "text": act}
                    elif itype == "error":
                        stream_err = item.get("message") or stream_err
                elif etype in ("error", "turn.failed"):
                    err_obj = evt.get("error")
                    if isinstance(err_obj, dict):
                        stream_err = err_obj.get("message") or str(err_obj)
                    else:
                        stream_err = evt.get("message") or str(err_obj or "")

            rc = await proc.wait()
            if not emitted:
                stderr_txt = (await proc.stderr.read()).decode("utf-8", errors="replace").strip() if proc.stderr else ""
                raise classify_cli_error(
                    "codex",
                    raw_err=stream_err,
                    stderr=stderr_txt,
                    exit_code=rc,
                    model=model,
                    effort=codex_eff,
                )
        finally:
            _safe_terminate_proc(proc)

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
    async def capture_workspace_backup(cwd: str) -> Optional[dict]:
        """在执行写入工作区前记录当前子目录内跟踪文件的原始内容快照，支持一键安全回滚。"""
        git_bin = shutil.which("git") or "git"
        try:
            proc_chk = await asyncio.create_subprocess_exec(
                git_bin,
                "rev-parse",
                "--is-inside-work-tree",
                cwd=cwd,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            out_chk, _ = await asyncio.wait_for(proc_chk.communicate(), timeout=2.0)
            if proc_chk.returncode != 0 or b"true" not in out_chk:
                return None

            proc_diff = await asyncio.create_subprocess_exec(
                git_bin,
                "diff",
                "--binary",
                "HEAD",
                "--",
                ".",
                cwd=cwd,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            pre_patch, _ = await asyncio.wait_for(proc_diff.communicate(), timeout=3.0)

            proc_untracked = await asyncio.create_subprocess_exec(
                git_bin,
                "ls-files",
                "--others",
                "--exclude-standard",
                "--",
                ".",
                cwd=cwd,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            untracked_out, _ = await asyncio.wait_for(proc_untracked.communicate(), timeout=2.0)
            untracked = [
                ln.strip()
                for ln in untracked_out.decode("utf-8", errors="replace").splitlines()
                if ln.strip()
            ]
            return {
                "cwd": cwd,
                "pre_patch": pre_patch.decode("utf-8", errors="replace"),
                "pre_untracked": untracked,
                "timestamp": time.time(),
            }
        except Exception:
            return None

    @staticmethod
    async def rollback_workspace_backup(backup: dict) -> Tuple[bool, str]:
        """恢复执行前的 Git 工作区状态并清理本次执行新增的未跟踪文件。"""
        cwd = backup.get("cwd", "")
        if not cwd or not os.path.isdir(cwd):
            return False, "原工作区目录不存在，无法回滚"
        git_bin = shutil.which("git") or "git"
        try:
            proc_reset = await asyncio.create_subprocess_exec(
                git_bin,
                "checkout",
                "--",
                ".",
                cwd=cwd,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc_reset.communicate(), timeout=5.0)

            pre_patch = backup.get("pre_patch", "")
            if pre_patch.strip():
                proc_apply = await asyncio.create_subprocess_exec(
                    git_bin,
                    "apply",
                    "--whitespace=nowarn",
                    "-",
                    cwd=cwd,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                assert proc_apply.stdin is not None
                proc_apply.stdin.write(pre_patch.encode("utf-8"))
                await proc_apply.stdin.drain()
                proc_apply.stdin.close()
                await asyncio.wait_for(proc_apply.wait(), timeout=5.0)

            proc_untracked = await asyncio.create_subprocess_exec(
                git_bin,
                "ls-files",
                "--others",
                "--exclude-standard",
                "--",
                ".",
                cwd=cwd,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            now_untracked_out, _ = await asyncio.wait_for(proc_untracked.communicate(), timeout=3.0)
            pre_set = set(backup.get("pre_untracked") or [])
            removed_cnt = 0
            for ln in now_untracked_out.decode("utf-8", errors="replace").splitlines():
                rel = ln.strip()
                if rel and rel not in pre_set:
                    full_p = os.path.realpath(os.path.join(cwd, rel))
                    if full_p.startswith(os.path.realpath(cwd) + os.sep) and os.path.isfile(full_p):
                        os.remove(full_p)
                        removed_cnt += 1
            return True, f"已成功回滚工作区至执行前状态（清理新增文件 {removed_cnt} 个）"
        except Exception as exc:
            return False, f"回滚异常：{exc}"

    async def stream_agent_execution(
        self,
        topic: str,
        whiteboard: dict,
        allow_workspace_write: bool = False,
        session_workspace: str = "",
        agent_id: str = "astra",
        persona_key: str = "",
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
        confirmed_exec_pts: List[str] = []
        if isinstance(raw_wb_items, list) and raw_wb_items:
            for it in raw_wb_items:
                if isinstance(it, dict) and it.get("bucket") != "chair_constraints" and (it.get("pinned") or it.get("adopted")):
                    t = str(it.get("text") or "").strip()
                    if t:
                        confirmed_exec_pts.append(f"- [{str(it.get('source_seat') or '共识').upper()}] {t}")

        ref_corpus = "\n".join(
            [topic]
            + confirmed_exec_pts
            + (whiteboard.get("chair_constraints") or [])
            + (whiteboard.get("carbon_plan") or [])
            + (whiteboard.get("grok_risks") or [])
            + (whiteboard.get("astra_actions") or [])
        )
        ws_snapshot = build_workspace_context_snapshot(cwd, reference_texts=ref_corpus)
        has_real_project = bool(ws_snapshot)

        constraints = "\n".join(f"- {x}" for x in whiteboard.get("chair_constraints", []))
        confirmed_section = (
            "【已确认置顶共识（最高优先级交付基准）】：\n" + "\n".join(confirmed_exec_pts) + "\n"
            if confirmed_exec_pts
            else ""
        )
        plans = "\n".join(f"- {x}" for x in whiteboard.get("carbon_plan", [])) or "- 按议题目标推进"
        risks = "\n".join(f"- {x}" for x in whiteboard.get("grok_risks", [])) or "- 注意边界异常处理"
        actions = "\n".join(f"- {x}" for x in whiteboard.get("astra_actions", [])) or "- 输出实施方案与交付物"

        if allow_workspace_write:
            mode_instruction = "（当前已授权写入本地项目工作区：请直接修改或创建目标项目文件，并运行必要的语法/单测校验，完成后总结改动清单与验证结果）"
        elif has_real_project:
            mode_instruction = "（当前为只读安全预演模式：请勿改动磁盘文件，直接输出完整详尽的实施方案与关键 Unified Diff 代码补丁预览）"
        else:
            mode_instruction = "（当前为产研/调研交付模式：请输出一份结构严谨、细节完整、可直接落地的完整方案书与实施验证清单）"

        exec_prompt = (
            f"你是本次会议指定的主刀执行官 {cfg.name}（当前侧重身份：{pspec['label']}）。"
            f"请综合白板共识高质量完成交付{mode_instruction}：\n"
            f"【议题】：{topic}\n"
            f"{('【主持人补充约束】：' + chr(10) + constraints + chr(10)) if constraints else ''}"
            f"{confirmed_section}"
            f"{ws_snapshot + chr(10) if ws_snapshot else ''}"
            f"【Carbon 要点】：\n{plans}\n"
            f"【Grok 要点】：\n{risks}\n"
            f"【Astra 要点】：\n{actions}\n"
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

                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdin=asyncio.subprocess.DEVNULL,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=cwd,
                    env=build_host_env(),
                    limit=4 * 1024 * 1024,
                )
                try:
                    assert proc.stdout is not None
                    collected: List[str] = []
                    stream_err = ""
                    while True:
                        line_b = await proc.stdout.readline()
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
                                continue
                            except json.JSONDecodeError:
                                pass
                        chunk_line = line_s + "\n"
                        collected.append(chunk_line)
                        yield {"type": "exec_delta", "text": chunk_line}

                    rc = await proc.wait()
                    final_txt = "".join(collected).strip()
                    if not final_txt:
                        stderr_txt = (await proc.stderr.read()).decode("utf-8", errors="replace").strip() if proc.stderr else ""
                        classified = classify_cli_error(
                            eff_drv,
                            raw_err=stream_err,
                            stderr=stderr_txt,
                            exit_code=rc,
                            model=cand_model,
                            effort=cand_effort,
                        )
                        if idx + 1 < len(attempts) and _is_model_or_effort_rejection(classified):
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
                    _safe_terminate_proc(proc)

        sandbox_mode = "workspace-write" if allow_workspace_write else "read-only"
        for idx, (cand_model, cand_effort) in enumerate(attempts):
            cmd = [bpath, "exec", "--json", "--skip-git-repo-check", "--sandbox", sandbox_mode]
            if cand_effort in CANONICAL_EFFORT_LEVELS:
                cmd.extend(["-c", f'model_reasoning_effort="{cand_effort}"'])
            if cand_model.strip():
                cmd.extend(["-m", cand_model.strip()])
            cmd.append("-")

            yield {"type": "term_log", "line": f"$ {' '.join(cmd[:-1])} <{cfg.name}决议指令> (cwd={cwd})"}

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=build_host_env(),
            )
            try:
                assert proc.stdin is not None and proc.stdout is not None
                proc.stdin.write(exec_prompt.encode("utf-8"))
                await proc.stdin.drain()
                proc.stdin.close()

                seen_lengths: Dict[str, int] = {}
                completed_msg_parts: List[str] = []
                stream_err = ""
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
                        err_obj = evt.get("error")
                        if isinstance(err_obj, dict):
                            err_m = err_obj.get("message") or str(err_obj)
                        else:
                            err_m = evt.get("message") or str(err_obj or "执行异常")
                        stream_err = err_m
                        yield {"type": "term_log", "line": f"✖ 错误: {err_m}"}

                rc = await proc.wait()
                final_message = "\n\n".join(completed_msg_parts).strip()
                if not final_message:
                    stderr_txt = (await proc.stderr.read()).decode("utf-8", errors="replace").strip() if proc.stderr else ""
                    classified = classify_cli_error(
                        "codex",
                        raw_err=stream_err,
                        stderr=stderr_txt,
                        exit_code=rc,
                        model=cand_model,
                        effort=cand_effort,
                    )
                    if idx + 1 < len(attempts) and _is_model_or_effort_rejection(classified):
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
                _safe_terminate_proc(proc)

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
