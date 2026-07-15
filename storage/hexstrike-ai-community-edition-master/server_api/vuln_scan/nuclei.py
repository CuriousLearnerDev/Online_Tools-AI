from flask import Blueprint, request, jsonify
import logging

from server_core.command_executor import execute_command
from server_core.nuclei_templates import resolve_nuclei_templates_dir
from server_core.shell_arg_quote import quote_shell_arg

logger = logging.getLogger(__name__)

api_vuln_scan_nuclei_bp = Blueprint("api_vuln_scan_nuclei", __name__)


@api_vuln_scan_nuclei_bp.route("/api/tools/nuclei", methods=["POST"])
def nuclei():
    """Execute Nuclei vulnerability scanner with enhanced logging and intelligent error handling"""
    try:
        params = request.json or {}
        target = params.get("target", "")
        severity = params.get("severity", "")
        tags = params.get("tags", "")
        template = (params.get("template") or "").strip()
        additional_args = params.get("additional_args", "")

        if not target:
            logger.warning("Nuclei called without target parameter")
            return jsonify({
                "error": "Target parameter is required"
            }), 400

        parts = ["nuclei", "-u", quote_shell_arg(target)]

        if severity:
            parts.extend(["-severity", quote_shell_arg(severity)])

        if tags:
            parts.extend(["-tags", quote_shell_arg(tags)])

        t_dir = template or resolve_nuclei_templates_dir()
        if t_dir:
            parts.extend(["-t", quote_shell_arg(t_dir)])

        if additional_args:
            parts.append(additional_args)

        command = " ".join(parts)

        logger.info(f"Starting Nuclei vulnerability scan: {target}")

        result = execute_command(command)

        logger.info(f"Nuclei scan completed for {target}")
        return jsonify(result)

    except Exception as e:
        logger.error(f"Error in nuclei endpoint: {str(e)}")
        return jsonify({
            "error": f"Server error: {str(e)}"
        }), 500
