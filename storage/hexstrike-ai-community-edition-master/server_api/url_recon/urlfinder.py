from flask import Blueprint, request, jsonify
import logging
import shlex

from server_core.command_executor import execute_command

logger = logging.getLogger(__name__)

api_url_recon_urlfinder_bp = Blueprint("api_url_recon_urlfinder", __name__)


def _q(s: str) -> str:
    if not s:
        return ""
    return shlex.quote(s)


@api_url_recon_urlfinder_bp.route("/api/tools/urlfinder", methods=["POST"])
def urlfinder():
    """
    URLFinder (pingc0y) — extract URLs and JS references from pages for API/sensitive-route hunting.
    Provide ``url``, and/or ``url_file`` (-f), and/or ``url_file_one`` (-ff).
    """
    try:
        params = request.json or {}
        url = (params.get("url") or params.get("u") or "").strip()
        url_file = (params.get("url_file") or params.get("f") or "").strip()
        url_file_one = (params.get("url_file_one") or params.get("ff") or "").strip()
        user_agent = (params.get("user_agent") or params.get("a") or "").strip()
        base_url = (params.get("base_url") or params.get("baseurl") or params.get("b") or "").strip()
        cookie = (params.get("cookie") or params.get("c") or "").strip()
        domain = (params.get("domain") or params.get("d") or "").strip()
        config_file = (params.get("config_file") or params.get("i") or "").strip()
        mode = params.get("mode", None)
        max_links = params.get("max", params.get("maximum", None))
        out_file = (params.get("out_file") or params.get("o") or "").strip()
        status = (params.get("status") or params.get("s") or "").strip()
        thread = params.get("thread", params.get("t", None))
        timeout_sec = params.get("timeout", params.get("time", None))
        proxy = (params.get("proxy") or params.get("x") or "").strip()
        fuzz = params.get("fuzz", params.get("z", None))
        additional_args = (params.get("additional_args") or "").strip()

        if not url and not url_file and not url_file_one:
            logger.warning("URLFinder: missing url, url_file, and url_file_one")
            return jsonify(
                {"error": "Provide url (-u), and/or url_file (-f), and/or url_file_one (-ff)"}
            ), 400

        parts: list[str] = ["URLFinder"]
        if user_agent:
            parts.extend(["-a", _q(user_agent)])
        if base_url:
            parts.extend(["-b", _q(base_url)])
        if cookie:
            parts.extend(["-c", _q(cookie)])
        if domain:
            parts.extend(["-d", _q(domain)])
        if url_file:
            parts.extend(["-f", _q(url_file)])
        if url_file_one:
            parts.extend(["-ff", _q(url_file_one)])
        if config_file:
            parts.extend(["-i", _q(config_file)])
        if mode is not None and str(mode).strip() != "":
            try:
                mi = int(mode)
                if mi >= 1:
                    parts.extend(["-m", str(mi)])
            except (TypeError, ValueError):
                pass
        if max_links is not None and str(max_links).strip() != "":
            try:
                mx = int(max_links)
                if mx > 0:
                    parts.extend(["-max", str(mx)])
            except (TypeError, ValueError):
                pass
        if out_file:
            parts.extend(["-o", _q(out_file)])
        if status:
            parts.extend(["-s", _q(status)])
        if thread is not None and str(thread).strip() != "":
            try:
                ti = int(thread)
                if ti > 0:
                    parts.extend(["-t", str(ti)])
            except (TypeError, ValueError):
                pass
        if timeout_sec is not None and str(timeout_sec).strip() != "":
            try:
                ts = int(timeout_sec)
                if ts > 0:
                    parts.extend(["-time", str(ts)])
            except (TypeError, ValueError):
                pass
        if url:
            parts.extend(["-u", _q(url)])
        if proxy:
            parts.extend(["-x", _q(proxy)])
        if fuzz is not None and str(fuzz).strip() != "":
            try:
                zi = int(fuzz)
                if zi > 0:
                    parts.extend(["-z", str(zi)])
            except (TypeError, ValueError):
                pass
        if additional_args:
            parts.append(additional_args.strip())

        command = " ".join(parts)
        logger.info(
            "🔗 URLFinder: start (url=%s, file=%s, ff=%s)",
            bool(url),
            bool(url_file),
            bool(url_file_one),
        )
        result = execute_command(command)
        logger.info("📊 URLFinder: done (success=%s)", result.get("success"))
        return jsonify(result)
    except Exception as e:
        logger.exception("URLFinder endpoint error: %s", e)
        return jsonify({"error": f"Server error: {str(e)}"}), 500
