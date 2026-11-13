#!/usr/bin/env python3
"""SSEC provider, review, concurrency, and advisory budget configuration.

This module does NOT enforce runtime sandbox, billing limits, or process limits.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

PROVIDERS = ("gemini", "codex", "both", "agy")
PERMISSIONS = ("read_only", "propose_patches", "request_write_approval")
AUDIT_LEVELS = ("basic", "standard", "strict")
DEFAULT_CONFIG: dict[str, Any] = {
    "schema_version": 1,
    "provider_mode": "gemini",
    "max_parallel_agents": 2,
    "permissions": "request_write_approval",
    "budget": {"max_runtime_minutes": 60, "max_estimated_cost_usd": 10},
    "audit_level": "standard",
}


def validate_config(raw: dict[str, Any]) -> dict[str, Any]:
    """Strictly validate a JSON-safe policy (fail closed on typos/unknowns)."""
    if not isinstance(raw, dict):
        raise ValueError("config must be a JSON object")
    if set(raw) != set(DEFAULT_CONFIG):
        raise ValueError(f"config fields must be exactly: {sorted(DEFAULT_CONFIG)}")
    if type(raw["schema_version"]) is not int or raw["schema_version"] != 1:
        raise ValueError("unsupported schema_version; expected 1")
    if raw["provider_mode"] not in PROVIDERS:
        raise ValueError("provider_mode must be gemini, codex, both or agy")
    cap = raw["max_parallel_agents"]
    if type(cap) is not int or not (1 <= cap <= 12):
        raise ValueError("max_parallel_agents must be an integer from 1 to 12")
    if raw["permissions"] not in PERMISSIONS:
        raise ValueError("unknown permissions policy")
    if raw["audit_level"] not in AUDIT_LEVELS:
        raise ValueError("unknown audit level")
    b = raw["budget"]
    if not isinstance(b, dict) or set(b) != set(DEFAULT_CONFIG["budget"]):
        raise ValueError("budget requires max_runtime_minutes and max_estimated_cost_usd")
    minutes = b["max_runtime_minutes"]
    amount = b["max_estimated_cost_usd"]
    if type(minutes) is not int or not 1 <= minutes <= 1440:
        raise ValueError("max_runtime_minutes must be integer 1..1440")
    if type(amount) not in (int, float) or not (0 <= amount <= 10000):
        raise ValueError("max_estimated_cost_usd must be finite nonnegative number <= 10000")
    # Reject NaN and Infinity. Float allows decimal values (JSON serializable).
    if amount != amount or amount == float("inf") or amount == float("-inf"):
        raise ValueError("max_estimated_cost_usd must be finite")
    return json.loads(json.dumps(raw, ensure_ascii=False, allow_nan=False))


def load_config(path: Path) -> dict[str, Any]:
    return validate_config(json.loads(path.read_text(encoding="utf-8")))


def config_path(project: Path) -> Path:
    return project / ".ssec" / "config.json"


def save_config(project: Path, raw: dict[str, Any]) -> Path:
    """Explicit save only; reject symlinks and atomically replace this owned file."""
    config = validate_config(raw)
    if not project.is_dir() or project.is_symlink():
        raise ValueError("project must be an existing non-symlink directory")
    target = config_path(project)
    folder = target.parent
    if folder.is_symlink() or target.is_symlink():
        raise ValueError("cannot write through symlinks")
    if folder.exists() and not folder.is_dir():
        raise ValueError(".ssec exists but is not a folder")
    folder.mkdir(exist_ok=True)
    text = json.dumps(config, ensure_ascii=False, indent=2) + "\n"
    if target.exists() and target.read_text(encoding="utf-8") == text:
        return target
    fd, tmp = tempfile.mkstemp(prefix=".config-", suffix=".tmp", dir=str(folder))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return target
