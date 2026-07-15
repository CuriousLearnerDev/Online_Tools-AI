from flask import Blueprint, request, jsonify
import logging
import re
from server_core.command_executor import execute_command
from server_core.singletons import COMMON_DIRB_PATH

logger = logging.getLogger(__name__)

api_web_fuzz_wfuzz_bp = Blueprint("api_web_fuzz_wfuzz", __name__)


@api_web_fuzz_wfuzz_bp.route("/api/tools/wfuzz", methods=["POST"])
def wfuzz():
    """Execute Wfuzz for web application fuzzing with enhanced logging"""
    try:
        params = request.json
        url = params.get("url", "")
        wordlist = params.get("wordlist", COMMON_DIRB_PATH)
        additional_args = params.get("additional_args", "")

        if not url:
            logger.warning("🌐 Wfuzz called without URL parameter")
            return jsonify({
                "error": "URL parameter is required"
            }), 400

        # wfuzz 推荐用 -z file,<wordlist> 指定 payload 源；URL 需要包含 FUZZ 注入点
        # 清洗用户输入：去掉首尾引号；若重复出现 http(s):// 仅保留最后一个（避免 http://'https://...' 这种目标）
        target = (url or "").strip()
        # strip wrapping quotes repeatedly
        while len(target) >= 2 and ((target[0] == target[-1]) and target[0] in ("'", '"')):
            target = target[1:-1].strip()
        # if multiple schemes exist, keep the last one
        scheme_matches = list(re.finditer(r"(https?://)", target, flags=re.IGNORECASE))
        if len(scheme_matches) >= 2:
            target = target[scheme_matches[-1].start():].strip()
        if "FUZZ" not in target:
            target = target.rstrip("/") + "/FUZZ"
        # Windows cmd.exe 下单引号不作为引用符（shell=True），会导致 URL 带入多余的 ' 字符。
        # 这里统一使用双引号包裹参数，避免出现 http://'https://...' 这类坏目标。
        wl_arg = f"file,{wordlist}"
        command = f'wfuzz -z "{wl_arg}" "{target}"'

        if additional_args:
            command += f" {additional_args}"

        logger.info(f"🔍 Starting Wfuzz scan: {url}")
        result = execute_command(command)
        logger.info(f"📊 Wfuzz scan completed for {url}")
        return jsonify(result)
    except Exception as e:
        logger.error(f"💥 Error in wfuzz endpoint: {str(e)}")
        return jsonify({
            "error": f"Server error: {str(e)}"
        }), 500
