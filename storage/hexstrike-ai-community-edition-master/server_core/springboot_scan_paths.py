"""SpringBoot-Scan 启动解析（API、健康检查 tools_status）。

仅三处来源（不做 storage 目录遍历）：
1. 环境变量 SPRINGBOOT_SCAN_SCRIPT：可执行文件/脚本的绝对路径，或已在 PATH 中的命令名（如 SpringBoot-Scan）
2. PATH 中的 SpringBoot-Scan / SpringBoot-Scan.exe
3. tools_config.json：键 springboot-scan / springboot_scan / SpringBoot-Scan

默认直接执行解析到的非 .py；解析为 .py 时按顺序选解释器：SPRINGBOOT_SCAN_PYTHON → tools_config 的 python →
storage/Python38（与 windows_start.bat）→ 工具目录 venv → sys.executable（与 HexStrike 相同）→ PATH python。

注册表/健康检查对外名称：springboot-scan。环境变量不能用连字符，故仍为 SPRINGBOOT_SCAN_*。"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path


def _tool_entry_from_tools_config(cfg_file: Path) -> tuple[str, str, str]:
    if not cfg_file.is_file():
        return "", "", ""
    try:
        with open(cfg_file, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        return "", "", ""
    tools = cfg.get("tools") or {}
    po = (
        tools.get("springboot-scan")
        or tools.get("springboot_scan")
        or tools.get("SpringBoot-Scan")
        or {}
    )
    rel = (po.get("path") or "").strip().replace("\\", "/")
    exe = (po.get("executable") or po.get("script") or "SpringBoot-Scan.py").strip()
    py_hint = (po.get("python") or po.get("python_exe") or "").strip()
    return rel, exe, py_hint


def _resolve_python_hint_from_tools_config() -> str:
    """tools_config 里可选 python / python_exe（相对 workspace 或绝对路径）。"""
    repo_root = Path(__file__).resolve().parent.parent
    for cfg_file in (
        repo_root.parent / "tools_config.json",
        repo_root / "tools_config.json",
    ):
        rel, _exe, py_hint = _tool_entry_from_tools_config(cfg_file)
        if not py_hint:
            continue
        workspace = cfg_file.resolve().parent.parent
        cand = workspace / py_hint.replace("/", os.sep)
        if cand.is_file():
            return str(cand.resolve())
        hp = Path(py_hint)
        if hp.is_file():
            return str(hp.resolve())
    return ""


def _resolve_from_tools_config() -> str:
    repo_root = Path(__file__).resolve().parent.parent
    for cfg_file in (
        repo_root.parent / "tools_config.json",
        repo_root / "tools_config.json",
    ):
        rel, exe, _pyh = _tool_entry_from_tools_config(cfg_file)
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


def resolve_springboot_scan_executable_path() -> str:
    """
    单一可执行目标：SPRINGBOOT_SCAN_SCRIPT → which(SpringBoot-Scan) → tools_config。
    """
    env = (os.environ.get("SPRINGBOOT_SCAN_SCRIPT") or "").strip()
    if env:
        ep = Path(env)
        if ep.is_file():
            return str(ep.resolve())
        w = shutil.which(env)
        if w:
            return w
    for name in ("SpringBoot-Scan", "SpringBoot-Scan.exe"):
        found = shutil.which(name)
        if found:
            return found
    return _resolve_from_tools_config()


def resolve_springboot_scan_script_path() -> str:
    """兼容旧名。"""
    return resolve_springboot_scan_executable_path()


def resolve_springboot_scan_python() -> str:
    """仅 PATH 回退；运行 .py 时请用 interpreter_for_springboot_script。"""
    env = (os.environ.get("SPRINGBOOT_SCAN_PYTHON") or "").strip()
    if env:
        return env
    for name in ("python", "python3", "py"):
        if shutil.which(name):
            return name
    return ""


def interpreter_for_springboot_script(script_abs: str) -> str | None:
    """
    与命令行调试环境对齐：优先 SPRINGBOOT_SCAN_PYTHON、tools_config 的 python、
    storage/Python38（windows_start.bat 常用）、工具目录下 venv、再与 HexStrike 同解释器 sys.executable，
    最后才 PATH 的 python（避免与终端用的环境不一致导致缺 tqdm 等）。
    """
    env = (os.environ.get("SPRINGBOOT_SCAN_PYTHON") or "").strip()
    if env:
        ep = Path(env)
        if ep.is_file():
            return str(ep.resolve())
        w = shutil.which(env)
        if w:
            return w
        return env

    hinted = _resolve_python_hint_from_tools_config()
    if hinted:
        return hinted

    tool_dir = Path(script_abs).resolve().parent
    parent = tool_dir.parent
    for sub in (
        "Python38",
        "Python39",
        "Python310",
        "Python311",
        "Python312",
        "Python313",
        "python38",
        "python39",
    ):
        exe = parent / sub / "python.exe"
        if exe.is_file():
            return str(exe.resolve())

    for vname in ("venv", ".venv"):
        win_py = tool_dir / vname / "Scripts" / "python.exe"
        if win_py.is_file():
            return str(win_py.resolve())
        nix_py = tool_dir / vname / "bin" / "python3"
        if nix_py.is_file():
            return str(nix_py.resolve())
        nix_py2 = tool_dir / vname / "bin" / "python"
        if nix_py2.is_file():
            return str(nix_py2.resolve())

    import sys

    if getattr(sys, "executable", None):
        sexe = Path(sys.executable)
        if sexe.is_file():
            return str(sexe.resolve())

    return resolve_springboot_scan_python() or None


def resolve_springboot_scan_launch() -> tuple[list[str], str | None] | None:
    """
    返回 (argv 前缀, cwd)。非 .py 时为 [绝对路径] + 工作目录为所在目录；
    .py 时为 [解释器, 文件名] + 工作目录为脚本目录。
    """
    raw = resolve_springboot_scan_executable_path()
    if not raw:
        return None
    p = Path(raw)
    if p.is_file():
        abs_path = str(p.resolve())
    else:
        w = shutil.which(raw)
        if not w:
            return None
        abs_path = str(Path(w).resolve())

    suffix = Path(abs_path).suffix.lower()
    parent = str(Path(abs_path).parent)
    if suffix == ".py":
        py = interpreter_for_springboot_script(abs_path)
        if not py:
            return None
        return [py, Path(abs_path).name], parent
    return [abs_path], parent


def is_springboot_scan_available() -> bool:
    return resolve_springboot_scan_launch() is not None
