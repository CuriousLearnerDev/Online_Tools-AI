"""Tongling tool API — catalog and generic execution for tools_config + toollist."""
from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

from server_core.tongling_tool_catalog import (
    DEDICATED_HEXSTRIKE_ALIASES,
    catalog_stats,
    get_catalog,
)
from server_core.tongling_tool_runner import catalog_summary, run_tongling_tool

logger = logging.getLogger(__name__)

api_tongling_tools_bp = Blueprint("api_tongling_tools", __name__)


def _parse_run_params(params: dict) -> dict:
    return {
        "target": (params.get("target") or params.get("domain") or params.get("url") or "").strip(),
        "args": (params.get("args") or params.get("additional_args") or params.get("command_args") or "").strip(),
        "additional_args": (params.get("additional_args") or "").strip(),
        "timeout": int(params.get("timeout") or params.get("scan_timeout") or 600),
    }


@api_tongling_tools_bp.route("/api/tongling/stats", methods=["GET"])
def tongling_stats():
    """Tool counts: tools_config vs full toollist CLI catalog vs registry."""
    from tool_registry import TOOLS

    stats = catalog_stats()
    tongling_registry = sum(1 for _n, m in TOOLS.items() if m.get("tongling"))
    return jsonify(
        {
            "success": True,
            **stats,
            "hexstrike_registry_total": len(TOOLS),
            "tongling_registry_entries": tongling_registry,
        }
    )


@api_tongling_tools_bp.route("/api/tongling/catalog", methods=["GET"])
def tongling_catalog():
    """List Tongling tools from tools_config.json and toollist.json (CLI)."""
    installed_only = request.args.get("installed_only", "").lower() in ("1", "true", "yes")
    category = (request.args.get("category") or "").strip()
    return jsonify(catalog_summary(installed_only=installed_only, category=category))


@api_tongling_tools_bp.route("/api/tongling/run", methods=["POST"])
def tongling_run():
    """
    Run a Tongling tool by alias.
    Body: { "tool": "subjack", "target": "example.com", "args": "-ssl -v", "timeout": 600 }
    """
    params = request.json or {}
    alias = (params.get("tool") or params.get("alias") or params.get("name") or "").strip().lower()
    if not alias:
        return jsonify({"success": False, "error": "缺少 tool 参数"}), 400

    run_params = _parse_run_params(params)
    logger.info("统领工具运行: %s target=%s args=%s", alias, run_params["target"], run_params["args"])
    result = run_tongling_tool(alias, **run_params)
    status = 200 if result.get("success") else 500
    if result.get("error") and "未知统领工具" in str(result.get("error")):
        status = 404
    if result.get("error") and "未安装" in str(result.get("error")):
        status = 400
    return jsonify(result), status


def _make_alias_handler(alias: str):
    def handler():
        params = request.json or {}
        run_params = _parse_run_params(params)
        logger.info("统领工具 /api/tools/tongling/%s", alias)
        result = run_tongling_tool(alias, **run_params)
        status = 200 if result.get("success") else 500
        if result.get("error") and "未安装" in str(result.get("error")):
            status = 400
        return jsonify(result), status

    handler.__name__ = f"tongling_tool_{alias.replace('-', '_')}"
    return handler


def register_tongling_alias_routes(app) -> None:
    """Register POST /api/tools/tongling/<alias> for non-dedicated tools."""
    for alias, tool in get_catalog().items():
        if alias in DEDICATED_HEXSTRIKE_ALIASES:
            continue
        route = f"/api/tools/tongling/{alias}"
        view = _make_alias_handler(alias)
        app.add_url_rule(route, endpoint=f"tongling_{alias}", view_func=view, methods=["POST"])
