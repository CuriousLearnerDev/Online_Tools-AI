"""Resolve fscan executable for API and health checks (FSCAN_BIN / PATH / storage)."""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _fscan_from_tools_config() -> str:
    for cfg in (_REPO_ROOT.parent / "tools_config.json", _REPO_ROOT / "tools_config.json"):
        if not cfg.is_file():
            continue
        try:
            with open(cfg, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue
        entry = (data.get("tools") or {}).get("fscan") or {}
        rel = (entry.get("path") or "").strip().replace("\\", "/")
        exe = (entry.get("executable") or "fscan.exe").strip()
        if not rel:
            continue
        ws = cfg.resolve().parent.parent
        rel_norm = rel.replace("/", os.sep)
        cand = ws / rel_norm / exe if not rel.lower().endswith(".exe") else ws / rel_norm
        if cand.is_file():
            return str(cand.resolve())
    return ""


def resolve_fscan_bin() -> str:
    env = (os.environ.get("FSCAN_BIN") or "").strip()
    if env and Path(env).is_file():
        return str(Path(env).resolve())
    found = _fscan_from_tools_config()
    if found:
        return found
    for name in ("fscan", "fscan.exe"):
        w = shutil.which(name)
        if w:
            return w
    for c in (
        _REPO_ROOT / "storage" / "fscan" / "fscan.exe",
        _REPO_ROOT / "storage" / "fscan" / "fscan",
        _REPO_ROOT.parent / "storage" / "fscan" / "fscan.exe",
        _REPO_ROOT.parent / "storage" / "fscan" / "fscan",
    ):
        if c.is_file():
            return str(c.resolve())
    return ""


def is_fscan_available() -> bool:
    return bool(resolve_fscan_bin())
