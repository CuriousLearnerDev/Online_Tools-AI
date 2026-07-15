from flask import Blueprint, request, jsonify
import logging
import shlex

from server_core.command_executor import execute_command

logger = logging.getLogger(__name__)

api_net_scan_naabu_bp = Blueprint("api_net_scan_naabu", __name__)


def _q(s: str) -> str:
    if not s:
        return ""
    return shlex.quote(s)


@api_net_scan_naabu_bp.route("/api/tools/naabu", methods=["POST"])
def naabu():
    """
    ProjectDiscovery Naabu — high-speed port enumeration (CONNECT/SYN).
    Provide either ``host`` (comma-separated) or ``host_file`` (path to target list).
    """
    try:
        params = request.json or {}
        host = (params.get("host") or "").strip()
        host_file = (params.get("host_file") or params.get("list") or "").strip()
        exclude_hosts = (params.get("exclude_hosts") or "").strip()
        exclude_file = (params.get("exclude_file") or "").strip()
        ports = (params.get("ports") or params.get("port") or "").strip()
        top_ports = (params.get("top_ports") or "").strip()
        rate = params.get("rate", 1000)
        c = params.get("c", 25)
        scan_type = (params.get("scan_type") or params.get("s") or "c").strip()
        silent = bool(params.get("silent", False))
        json_lines = bool(params.get("json_lines", False) or params.get("json", False))
        csv_out = bool(params.get("csv", False))
        output = (params.get("output") or params.get("o") or "").strip()
        interface = (params.get("interface") or params.get("i") or "").strip()
        verify = params.get("verify")
        debug = bool(params.get("debug", False))
        verbose = bool(params.get("verbose", False))
        additional_args = (params.get("additional_args") or "").strip()

        if not host and not host_file:
            logger.warning("Naabu: missing host and host_file")
            return jsonify({"error": "Provide host (comma-separated) or host_file (list path)"}), 400

        parts: list[str] = ["naabu"]
        if host:
            parts.extend(["-host", _q(host)])
        if host_file:
            parts.extend(["-l", _q(host_file)])
        if exclude_hosts:
            parts.extend(["-exclude-hosts", _q(exclude_hosts)])
        if exclude_file:
            parts.extend(["-ef", _q(exclude_file)])
        if ports:
            parts.extend(["-p", _q(ports)])
        if top_ports:
            parts.extend(["-tp", _q(top_ports)])
        try:
            parts.extend(["-rate", str(int(rate))])
        except (TypeError, ValueError):
            parts.extend(["-rate", "1000"])
        try:
            parts.extend(["-c", str(int(c))])
        except (TypeError, ValueError):
            parts.extend(["-c", "25"])
        if scan_type:
            parts.extend(["-s", _q(scan_type)])
        if interface:
            parts.extend(["-i", _q(interface)])
        if output:
            parts.extend(["-o", _q(output)])
        if silent:
            parts.append("-silent")
        if json_lines:
            parts.append("-json")
        if csv_out:
            parts.append("-csv")
        if verify is True:
            parts.append("-verify")
        if debug:
            parts.append("-debug")
        if verbose:
            parts.append("-v")
        if additional_args:
            parts.append(additional_args)

        command = " ".join(parts)
        logger.info("🔌 Naabu: starting scan (host=%s, list=%s)", bool(host), bool(host_file))
        result = execute_command(command)
        logger.info("📊 Naabu: finished (success=%s)", result.get("success"))
        return jsonify(result)
    except Exception as e:
        logger.exception("Naabu endpoint error: %s", e)
        return jsonify({"error": f"Server error: {str(e)}"}), 500
