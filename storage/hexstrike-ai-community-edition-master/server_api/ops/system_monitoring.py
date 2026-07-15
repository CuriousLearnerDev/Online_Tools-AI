from flask import Blueprint, request, jsonify
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Dict
import logging
import shutil
import subprocess
import threading
import time
import traceback
from pathlib import Path

import server_core.config_core as config_core
from server_core.command_executor import execute_command
from server_core.modern_visual_engine import ModernVisualEngine
from server_core.singletons import cache, telemetry

from server_core.tool_constants import (
    BUILT_IN_TOOLS, REQUIRE_DPKG_CHECK, REQUIRE_PIP_CHECK,
    REQUIRE_GEM_CHECK, REQUIRE_CARGO_CHECK, BINARY_NAME_OVERRIDES,
    HEALTH_TOOL_CATEGORIES
)
from server_core.pocbomber_paths import is_pocbomber_available
from server_core.fscan_paths import is_fscan_available
from server_core.springboot_scan_paths import is_springboot_scan_available

logger = logging.getLogger(__name__)

api_system_monitoring_bp = Blueprint("api_system_monitoring", __name__)

# ============================================================================
# TOOL AVAILABILITY CACHE — populated once at startup, refreshed every hour
# ============================================================================
_tool_availability_cache: Dict[str, bool] = {}
_tool_availability_lock = threading.Lock()
_tool_availability_last_refresh: float = 0.0

# Precompute the flat list of all tools at module load
ALL_TOOLS_FLAT = list({
    tool
    for tools in HEALTH_TOOL_CATEGORIES.values()
    for tool in tools
})

def _refresh_tool_availability() -> None:
    """Probe all tools with `which` in parallel and update the module-level cache."""
    global _tool_availability_last_refresh

    def probe(tool: str) -> tuple:
        if tool == "sqlmap":
            # Windows/local packaged mode: treat sqlmap as available if script + python runtime exist.
            try:
                repo_root = Path(__file__).resolve().parents[2]   # .../hexstrike-ai-community-edition-master
                storage_root = repo_root.parent                   # .../storage
                script = storage_root / "sqlmap" / "sqlmap.py"
                py38 = storage_root / "Python38" / "python.exe"
                py311 = storage_root / "Python311" / "python.exe"
                if script.exists() and (py38.exists() or py311.exists()):
                    return tool, True
            except Exception:
                pass
        if tool == "pocbomber":
            return tool, is_pocbomber_available()
        if tool == "fscan":
            return tool, is_fscan_available()
        if tool == "springboot-scan":
            return tool, is_springboot_scan_available()
        if tool in BINARY_NAME_OVERRIDES:
            tool_to_check = BINARY_NAME_OVERRIDES[tool]
        else:
            tool_to_check = tool
        if tool_to_check in BUILT_IN_TOOLS:
            # Always report built-ins as available without probing
            return tool, True
        try:
            if tool_to_check in REQUIRE_DPKG_CHECK:
                # For tools that require dpkg, check if the package is installed
                result = subprocess.run(
                    ["dpkg", "-s", tool_to_check],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return tool, result.returncode == 0
            elif tool_to_check in REQUIRE_PIP_CHECK:
                # For tools that require pip, check if the package is installed
                result = subprocess.run(
                    ["pip3", "list"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                )
                return tool, tool_to_check in result.stdout
            elif tool_to_check in REQUIRE_GEM_CHECK:
                # For tools that require gem, check if the package is installed
                result = subprocess.run(
                    ["gem", "list"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                )
                return tool, tool_to_check in result.stdout
            elif tool_to_check in REQUIRE_CARGO_CHECK:
                # For tools that require cargo, check if the package is installed
                result = subprocess.run(
                    ["cargo", "install", "--list"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                )
                return tool, tool_to_check in result.stdout
            else:
                # 使用 shutil.which：跨平台，且会尊重当前进程 PATH（例如统领启动 Server 时注入的工具目录）
                found = shutil.which(tool_to_check)
                return tool, found is not None
        except Exception:
            return tool, False

    with ThreadPoolExecutor(max_workers=20) as pool:
        results = dict(pool.map(probe, ALL_TOOLS_FLAT))

    with _tool_availability_lock:
        _tool_availability_cache.update(results)
        _tool_availability_last_refresh = time.time()

    installed = sorted(t for t, ok in results.items() if ok)
    missing = sorted(t for t, ok in results.items() if not ok)
    GREEN = ModernVisualEngine.COLORS['MATRIX_GREEN']
    RED = ModernVisualEngine.COLORS['HACKER_RED']
    RESET = ModernVisualEngine.COLORS['RESET']
    lines = ["Tool availability refreshed: %d/%d available" % (len(installed), len(results))]
    for tool in installed:
        lines.append("%s  %-30s installed%s" % (GREEN, tool, RESET))
    for tool in missing:
        lines.append("%s  %-30s NOT INSTALLED%s" % (RED, tool, RESET))
    logger.info("\n".join(lines))


def _get_tool_availability() -> Dict[str, bool]:
    """Return cached tool availability, refreshing in a background thread if stale."""
    now = time.time()
    with _tool_availability_lock:
        stale = (now - _tool_availability_last_refresh) > config_core.get("TOOL_AVAILABILITY_TTL", 3600)
        empty = not _tool_availability_cache

    if empty:
        _refresh_tool_availability()
    elif stale:
        threading.Thread(target=_refresh_tool_availability, daemon=True).start()

    # Only lock while copying the cache
    with _tool_availability_lock:
        output_status = dict(_tool_availability_cache)
    for tool in BUILT_IN_TOOLS:
        output_status[tool] = True
    return output_status

@api_system_monitoring_bp.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint with comprehensive tool detection"""
    tools_status = _get_tool_availability()

    essential_tools = HEALTH_TOOL_CATEGORIES["essential"]
    all_essential_tools_available = all(tools_status.get(t, False) for t in essential_tools)

    category_stats = {
        cat: {
            "total": len(tools),
            "available": sum(1 for t in tools if tools_status.get(t, False)),
        }
        for cat, tools in HEALTH_TOOL_CATEGORIES.items()
    }

    all_tools_count = len(tools_status)

    return jsonify({
        "status": "healthy",
        "message": "HexStrike AI Tools API Server is operational",
        "version": config_core.get("VERSION", "unknown"),
        "tools_status": tools_status,
        "all_essential_tools_available": all_essential_tools_available,
        "total_tools_available": sum(1 for available in tools_status.values() if available),
        "total_tools_count": all_tools_count,
        "category_stats": category_stats,
        "cache_stats": cache.get_stats(),
        "telemetry": telemetry.get_stats(),
        "uptime": time.time() - telemetry.stats["start_time"],
        "tool_availability_age_seconds": round(time.time() - _tool_availability_last_refresh, 1),
    })


@api_system_monitoring_bp.route("/ping", methods=["GET"])
def ping():
    return jsonify({
        "success": True,
        "message": "Pong! HexStrike AI Tools API Server is responsive",
        "timestamp": datetime.now().isoformat()
    })


@api_system_monitoring_bp.route("/api/command", methods=["POST"])
def generic_command():
    """Execute any command provided in the request with enhanced logging"""
    try:
        params = request.json
        command = params.get("command", "")
        use_cache = params.get("use_cache", True)

        if not command:
            logger.warning("Command endpoint called without command parameter")
            return jsonify({
                "error": "Command parameter is required"
            }), 400

        result = execute_command(command, use_cache=use_cache)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error in command endpoint: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            "error": f"Server error: {str(e)}"
        }), 500


@api_system_monitoring_bp.route("/api/cache/stats", methods=["GET"])
def cache_stats():
    """Get cache statistics"""
    return jsonify(cache.get_stats())


@api_system_monitoring_bp.route("/api/cache/clear", methods=["POST"])
def clear_cache():
    """Clear the cache"""
    cache.clear()
    logger.info("Cache cleared")
    return jsonify({"success": True, "message": "Cache cleared"})


@api_system_monitoring_bp.route("/api/telemetry", methods=["GET"])
def get_telemetry():
    """Get system telemetry"""
    return jsonify(telemetry.get_stats())

@api_system_monitoring_bp.route("/api/tools/categories", methods=["GET"])
def get_tool_categories():
    """Get the list of tool categories and their tools"""
    return jsonify({
        "categories": HEALTH_TOOL_CATEGORIES
    })