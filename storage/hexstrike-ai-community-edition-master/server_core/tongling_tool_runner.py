"""Execute Tongling tools resolved from tools_config / toollist."""
from __future__ import annotations

import os
import shlex
import shutil
from typing import Any, Dict, List, Optional

from server_core.command_executor import execute_command
from server_core.tongling_tool_catalog import TonglingTool, get_tool, get_catalog


def _python_interpreter() -> str:
    for cand in (
        os.environ.get("TONGING_PYTHON") or os.environ.get("SPRINGBOOT_SCAN_PYTHON") or "",
        str((__import__("pathlib").Path(__file__).resolve().parents[1].parent / "storage" / "Python38" / "python.exe")),
    ):
        if cand and os.path.isfile(cand):
            return cand
    found = shutil.which("python") or shutil.which("python3") or "python"
    return found


def build_argv(tool: TonglingTool, *, target: str = "", args: str = "") -> tuple[List[str], str]:
    """Return (argv list, error message). Empty error means success."""
    extra = (args or "").strip()
    tgt = (target or "").strip()

    if not tool.resolved_path or not os.path.isfile(tool.resolved_path):
        return [], f"工具未安装或路径无效: {tool.display_name} ({tool.storage_path})"

    exe_path = tool.resolved_path
    argv: List[str] = []

    if tool.tool_type == "python":
        script = exe_path
        argv = [_python_interpreter(), script]
    elif tool.tool_type == "bat":
        argv = ["cmd", "/c", exe_path]
    else:
        argv = [exe_path]

    # Smart defaults for common tools when only target is given
    if tgt and not extra:
        alias = tool.alias
        if alias == "subjack":
            extra = f"-d {shlex.quote(tgt)} -ssl -v"
        elif alias == "sslscan":
            extra = tgt if ":" in tgt else f"{tgt}:443"
        elif alias in ("jwt_tool", "hash-identifier"):
            extra = tgt
        elif alias == "hexdump":
            extra = f"-C {shlex.quote(tgt)}"
        else:
            extra = tgt

    if extra:
        argv.extend(shlex.split(extra, posix=os.name != "nt"))

    cmd_str = " ".join(shlex.quote(a) for a in argv)
    return argv, ""


def run_tongling_tool(
    alias: str,
    *,
    target: str = "",
    args: str = "",
    additional_args: str = "",
    timeout: int = 600,
) -> Dict[str, Any]:
    tool = get_tool(alias)
    if not tool:
        return {
            "success": False,
            "error": f"未知统领工具: {alias}。请调用 GET /api/tongling/catalog 查看可用列表。",
            "stdout": "",
            "stderr": "",
            "return_code": 1,
        }

    merged_args = args or additional_args or ""
    argv, err = build_argv(tool, target=target, args=merged_args)
    if err:
        return {
            "success": False,
            "error": err,
            "stdout": "",
            "stderr": err,
            "return_code": 1,
            "tool": tool.alias,
            "installed": tool.installed,
        }

    cmd_str = " ".join(shlex.quote(a) for a in argv)
    cwd = os.path.dirname(argv[0]) if tool.tool_type == "exe" else None
    if tool.tool_type == "python" and len(argv) > 1:
        cwd = os.path.dirname(argv[1])

    # execute_command runs via shell; quote argv for Windows safety
    if cwd and os.path.isdir(cwd):
        old_cwd = os.getcwd()
        try:
            os.chdir(cwd)
            result = execute_command(cmd_str, use_cache=False, timeout=max(30, int(timeout)))
        finally:
            os.chdir(old_cwd)
    else:
        result = execute_command(cmd_str, use_cache=False, timeout=max(30, int(timeout)))

    result["tool"] = tool.alias
    result["display_name"] = tool.display_name
    result["command"] = cmd_str
    result["category"] = tool.category
    result["usage_example"] = tool.usage_example
    return result


def catalog_summary(*, installed_only: bool = False, category: str = "") -> Dict[str, Any]:
    from server_core.tongling_tool_catalog import list_tools

    tools = list_tools(installed_only=installed_only, category=category)
    installed = sum(1 for t in tools if t["installed"])
    return {
        "success": True,
        "total": len(tools),
        "installed": installed,
        "tools": tools,
    }
