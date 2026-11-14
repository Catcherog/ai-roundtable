# -*- coding: utf-8 -*-
"""
AI圆桌 — 声明式 CLI 驱动目录加载器（P1.3 & P2.2 热插拔支持）
支持内置 `driver_catalog.json` 与用户 `~/.ai-roundtable/drivers.json` 增量热覆盖，无需重编译 App 即可接入新模型档位或自定义 CLI。
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .process_watchdog import (
    SupervisedProcessHandle,
    is_process_group_alive,
    spawn_supervised_cli,
    terminate_and_reap_process_group,
)

BUILTIN_CATALOG_PATH = Path(__file__).resolve().parent / "driver_catalog.json"
def _get_user_drivers_override_path() -> Path:
    return Path(os.path.expanduser(os.environ.get("AI_ROUNDTABLE_HOME") or "~/.ai-roundtable")) / "drivers.json"
USER_DRIVERS_OVERRIDE_PATH = _get_user_drivers_override_path()

_CATALOG_CACHE: Optional[dict] = None
_CATALOG_MTIME_SIG: Tuple[int, int] = (-1, -1)


def _file_mtime_ns(p: Path) -> int:
    try:
        return p.stat().st_mtime_ns
    except OSError:
        return 0


def _deep_merge_driver_catalog(base: dict, override: dict) -> dict:
    merged = copy.deepcopy(base)
    if not isinstance(override, dict):
        return merged
    if isinstance(override.get("canonical_efforts"), list) and override["canonical_efforts"]:
        merged["canonical_efforts"] = [str(x) for x in override["canonical_efforts"] if str(x).strip()]
    if isinstance(override.get("exclusive_default_models"), dict):
        merged.setdefault("exclusive_default_models", {}).update(
            {str(k): str(v) for k, v in override["exclusive_default_models"].items()}
        )
    if isinstance(override.get("drivers"), dict):
        drv_dest = merged.setdefault("drivers", {})
        for dk, dv in override["drivers"].items():
            if not isinstance(dv, dict):
                continue
            dk_norm = str(dk).strip().lower()
            if not dk_norm or dk_norm == "auto":
                continue
            if dk_norm not in drv_dest:
                drv_dest[dk_norm] = copy.deepcopy(dv)
            else:
                cur = drv_dest[dk_norm]
                for k, v in dv.items():
                    if k == "models" and isinstance(v, dict):
                        cur.setdefault("models", {}).update(copy.deepcopy(v))
                    else:
                        cur[k] = copy.deepcopy(v)
    return merged


def load_driver_catalog(force: bool = False) -> dict:
    """按 mtime_ns 增量热加载内置目录与 ~/.ai-roundtable/drivers.json 声明式扩展。"""
    global _CATALOG_CACHE, _CATALOG_MTIME_SIG
    sig = (_file_mtime_ns(BUILTIN_CATALOG_PATH), _file_mtime_ns(USER_DRIVERS_OVERRIDE_PATH))
    if not force and _CATALOG_CACHE is not None and sig == _CATALOG_MTIME_SIG:
        return _CATALOG_CACHE

    base_data: dict = {}
    try:
        base_data = json.loads(BUILTIN_CATALOG_PATH.read_text(encoding="utf-8"))
    except Exception:
        base_data = {"canonical_efforts": ["low", "medium", "high", "xhigh", "max"], "drivers": {}}

    user_override: dict = {}
    if _get_user_drivers_override_path().is_file():
        try:
            user_override = json.loads(_get_user_drivers_override_path().read_text(encoding="utf-8"))
        except Exception:
            user_override = {}

    merged = _deep_merge_driver_catalog(base_data, user_override)
    merged["user_override_path"] = str(USER_DRIVERS_OVERRIDE_PATH)
    merged["user_override_loaded"] = bool(user_override)
    _CATALOG_CACHE = merged
    _CATALOG_MTIME_SIG = sig
    return merged


def build_driver_specs_and_capabilities(force: bool = False) -> Tuple[Dict[str, dict], Dict[str, Dict[str, dict]], Dict[str, List[str]], Dict[str, str]]:
    """导出兼容旧版常量的 (DRIVER_SPECS, MODEL_EFFORT_CAPABILITIES, DRIVER_FALLBACK_PATHS, EXCLUSIVE_MODELS)。"""
    cat = load_driver_catalog(force=force)
    specs: Dict[str, dict] = {}
    caps: Dict[str, Dict[str, dict]] = {}
    fallbacks: Dict[str, List[str]] = {}
    excl: Dict[str, str] = dict(cat.get("exclusive_default_models") or {})

    for dk, dinfo in (cat.get("drivers") or {}).items():
        specs[dk] = {
            "cli_name": dinfo.get("cli_name", f"{dk.upper()} CLI"),
            "short_label": dinfo.get("short_label", dk.upper()),
            "binary_candidates": list(dinfo.get("binary_candidates") or [dk]),
            "default_model": dinfo.get("default_model", ""),
            "default_discuss_effort": dinfo.get("default_discuss_effort", "high"),
            "default_exec_effort": dinfo.get("default_exec_effort", "high"),
            "cmd_template": dinfo.get("cmd_template"),
        }
        caps[dk] = copy.deepcopy(dinfo.get("models") or {})
        fallbacks[dk] = [os.path.expanduser(p) for p in (dinfo.get("macos_fallback_paths") or [])]

    return specs, caps, fallbacks, excl


__all__ = [
    "BUILTIN_CATALOG_PATH",
    "USER_DRIVERS_OVERRIDE_PATH",
    "SupervisedProcessHandle",
    "build_driver_specs_and_capabilities",
    "is_process_group_alive",
    "load_driver_catalog",
    "spawn_supervised_cli",
    "terminate_and_reap_process_group",
]
