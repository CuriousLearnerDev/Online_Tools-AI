from flask import Blueprint, jsonify
import logging

from tool_registry import TOOLS
from server_core.singletons import tool_stats
from server_core.nuclei_templates import resolve_nuclei_templates_dir
from server_core.tongling_tool_catalog import _decode_unicode_text

logger = logging.getLogger(__name__)

api_tools_catalog_bp = Blueprint("api_tools_catalog", __name__)


@api_tools_catalog_bp.route("/api/tools", methods=["GET"])
def get_tools():
    """Return the full tool catalog with metadata."""
    tools = []
    for name, meta in TOOLS.items():
        baseline = meta.get("effectiveness", 0.0)
        stats = tool_stats.get_stats(name)
        effective = tool_stats.blended_effectiveness(name, baseline)
        optional = dict(meta.get("optional", {}))
        # GUI 用 optional 的字符串默认值预填输入框；留空仍会走服务端 resolve
        if name == "nuclei":
            _td = resolve_nuclei_templates_dir()
            if _td:
                optional["template"] = _td
        entry = {
            "name": name,
            "desc": _decode_unicode_text(meta.get("desc", "")),
            "category": meta.get("category", ""),
            "endpoint": meta.get("endpoint", ""),
            "method": meta.get("method", "POST"),
            "params": meta.get("params", {}),
            "optional": optional,
            "effectiveness": effective,
            "effectiveness_runs": stats["runs"],
            "effectiveness_live": stats["runs"] >= 5,
            "parent_tool": meta.get("parent_tool", None),
        }
        if meta.get("label"):
            entry["label"] = _decode_unicode_text(meta["label"])
        tools.append(entry)

    categories = sorted({t["category"] for t in tools})

    return jsonify({
        "success": True,
        "total": len(tools),
        "categories": categories,
        "tools": tools,
    })
