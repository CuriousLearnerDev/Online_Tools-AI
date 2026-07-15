from flask import Blueprint, request, jsonify
import logging
from pathlib import Path
from server_core.command_executor import execute_command
from server_core.shell_arg_quote import quote_shell_arg

logger = logging.getLogger(__name__)

api_web_scan_sqlmap_bp = Blueprint("api_web_scan_sqlmap", __name__)


@api_web_scan_sqlmap_bp.route("/api/tools/sqlmap", methods=["POST"])
def sqlmap():
    """Execute sqlmap with enhanced logging"""
    try:
        params = request.json
        url = params.get("url", "")
        data = params.get("data", "")
        additional_args = params.get("additional_args", "")

        if not url:
            logger.warning("🎯 SQLMap called without URL parameter")
            return jsonify({
                "error": "URL parameter is required"
            }), 400

        # Use absolute paths so execution does not depend on server cwd.
        repo_root = Path(__file__).resolve().parents[2]     # .../hexstrike-ai-community-edition-master
        storage_root = repo_root.parent                     # .../storage
        sqlmap_script = storage_root / "sqlmap" / "sqlmap.py"
        python38_exe = storage_root / "Python38" / "python.exe"

        missing = []
        if not python38_exe.exists():
            missing.append(str(python38_exe))
        if not sqlmap_script.exists():
            missing.append(str(sqlmap_script))
        if missing:
            return jsonify({
                "success": False,
                "error": "sqlmap 运行环境缺失，请检查以下路径：",
                "missing_paths": missing
            }), 500

        command = (
            f"{quote_shell_arg(str(python38_exe))} "
            f"{quote_shell_arg(str(sqlmap_script))} "
            f"-u {quote_shell_arg(url)} --batch"
        )

        if data:
            command += f" --data {quote_shell_arg(data)}"

        if additional_args:
            command += f" {additional_args}"

        logger.info(f"💉 Starting SQLMap scan: {url}")
        result = execute_command(command)
        logger.info(f"📊 SQLMap scan completed for {url}")
        return jsonify(result)
    except Exception as e:
        logger.error(f"💥 Error in sqlmap endpoint: {str(e)}")
        return jsonify({
            "error": f"Server error: {str(e)}"
        }), 500
