"""PocBomber script/Python resolution (API + health / web-dashboard tools_status)."""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _pocbomber_entry_from_tools_config(cfg_file: Path) -> tuple[str, str]:
    """Return (path field, script filename) from tools_config, or ("", "")."""
    if not cfg_file.is_file():
        return "", ""
    try:
        with open(cfg_file, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        return "", ""
    po = (cfg.get("tools") or {}).get("pocbomber") or {}
    rel = (po.get("path") or "").strip().replace("\\", "/")
    exe = (po.get("executable") or po.get("script") or "pocbomber.py").strip()
    return rel, exe


def _resolve_from_tools_config() -> str:
    """
    与统领 tools_config.json 一致：默认 <workspace>/storage/tools_config.json，
    path 如 storage/POC-bomber，executable 如 pocbomber.py。
    """
    for cfg_file in (
        _REPO_ROOT.parent / "tools_config.json",
        _REPO_ROOT / "tools_config.json",
    ):
        rel, exe = _pocbomber_entry_from_tools_config(cfg_file)
        if not rel or not exe:
            continue
        workspace = cfg_file.resolve().parent.parent
        rel_norm = rel.replace("/", os.sep)
        if rel.lower().endswith(".py"):
            candidate = workspace / rel_norm
        else:
            candidate = workspace / rel_norm / exe
        if candidate.is_file():
            return str(candidate.resolve())
    return ""


def resolve_pocbomber_script_path() -> str:
    env = (os.environ.get("POCBOMBER_SCRIPT") or "").strip()
    if env and Path(env).is_file():
        return str(Path(env).resolve())
    found = _resolve_from_tools_config()
    if found:
        return found
    for c in (
        _REPO_ROOT / "storage" / "pocbomber" / "pocbomber.py",
        _REPO_ROOT / "storage" / "POC-bomber" / "pocbomber.py",
        _REPO_ROOT.parent / "storage" / "pocbomber" / "pocbomber.py",
        _REPO_ROOT.parent / "storage" / "POC-bomber" / "pocbomber.py",
        _REPO_ROOT.parent / "POC-bomber" / "pocbomber.py",
        _REPO_ROOT.parent / "pocbomber" / "pocbomber.py",
        _REPO_ROOT / "pocbomber" / "pocbomber.py",
    ):
        if c.is_file():
            return str(c.resolve())
    return ""


def resolve_pocbomber_python() -> str:
    """
    显式 POCBOMBER_PYTHON 用绝对路径；否则返回简短命令名 python/python3/py，
    由 PATH 解析（统领 QProcess 已把各工具目录插到 Path 前部）。
    """
    env = (os.environ.get("POCBOMBER_PYTHON") or "").strip()
    if env:
        return env
    for name in ("python", "python3", "py"):
        if shutil.which(name):
            return name
    return ""


def is_pocbomber_available() -> bool:
    """Script on disk + Python interpreter (PATH or POCBOMBER_PYTHON)."""
    return bool(resolve_pocbomber_script_path()) and bool(resolve_pocbomber_python())
