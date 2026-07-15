from flask import Blueprint, request, jsonify
import logging
import shlex

from server_core.command_executor import execute_command

logger = logging.getLogger(__name__)

api_net_scan_kscan_bp = Blueprint("api_net_scan_kscan", __name__)


def _q(s: str) -> str:
    if not s:
        return ""
    return shlex.quote(s)


@api_net_scan_kscan_bp.route("/api/tools/kscan", methods=["POST"])
def kscan():
    """
    Kscan (lcvvvv) — Go-based scanner: ports, fingerprints, optional hydra/FOFA/spy.
    Require one of: ``target`` (-t), ``fofa`` (-f), ``use_spy`` (--spy), or ``fofa_syntax``.
    """
    try:
        params = request.json or {}
        fofa_syntax = bool(params.get("fofa_syntax", False))
        target = (params.get("target") or params.get("t") or "").strip()
        fofa = (params.get("fofa") or params.get("f") or "").strip()
        use_spy = bool(params.get("use_spy", False))
        spy_scope = (params.get("spy_scope") or "").strip()

        if not fofa_syntax and not target and not fofa and not use_spy:
            logger.warning("Kscan: need target, fofa, use_spy, or fofa_syntax")
            return jsonify(
                {"error": "Provide target (-t), fofa (-f), use_spy (--spy), or fofa_syntax"}
            ), 400

        parts: list[str] = ["kscan"]

        if fofa_syntax:
            parts.append("--fofa-syntax")

        if target:
            parts.extend(["-t", _q(target)])
        if fofa:
            parts.extend(["-f", _q(fofa)])
        if use_spy:
            parts.append("--spy")
            if spy_scope:
                parts.append(_q(spy_scope))

        if bool(params.get("check", False)):
            parts.append("--check")
        if bool(params.get("scan", False)):
            parts.append("--scan")

        ports = (params.get("port") or params.get("ports") or "").strip()
        if ports:
            parts.extend(["-p", _q(ports)])

        output = (params.get("output") or params.get("o") or "").strip()
        if output:
            parts.extend(["-o", _q(output)])

        oj = (params.get("output_json") or params.get("oJ") or "").strip()
        if oj:
            parts.extend(["-oJ", _q(oj)])

        oc = (params.get("output_csv") or params.get("oC") or "").strip()
        if oc:
            parts.extend(["-oC", _q(oc)])

        if bool(params.get("Pn", False)) or bool(params.get("pn", False)):
            parts.append("-Pn")
        if bool(params.get("Cn", False)) or bool(params.get("cn", False)):
            parts.append("-Cn")
        if bool(params.get("Dn", False)) or bool(params.get("dn", False)):
            parts.append("-Dn")
        if bool(params.get("sV", False)) or bool(params.get("sv", False)):
            parts.append("-sV")

        top = params.get("top", None)
        if top is not None and str(top).strip() != "":
            try:
                ti = int(top)
                if ti > 0:
                    parts.extend(["--top", str(ti)])
            except (TypeError, ValueError):
                pass

        proxy = (params.get("proxy") or "").strip()
        if proxy:
            parts.extend(["--proxy", _q(proxy)])

        threads = params.get("threads", None)
        if threads is not None and str(threads).strip() != "":
            try:
                th = int(threads)
                if th > 0:
                    parts.extend(["--threads", str(th)])
            except (TypeError, ValueError):
                pass

        url_path = (params.get("path") or "").strip()
        if url_path:
            parts.extend(["--path", _q(url_path)])

        request_host = (params.get("request_host") or params.get("http_host") or "").strip()
        if request_host:
            parts.extend(["--host", _q(request_host)])

        timeout = params.get("timeout", None)
        if timeout is not None and str(timeout).strip() != "":
            try:
                to = int(timeout)
                if to > 0:
                    parts.extend(["--timeout", str(to)])
            except (TypeError, ValueError):
                pass

        encoding = (params.get("encoding") or "").strip()
        if encoding:
            parts.extend(["--encoding", _q(encoding)])

        match_banner = (params.get("match") or "").strip()
        if match_banner:
            parts.extend(["--match", _q(match_banner)])

        not_match = (params.get("not_match") or "").strip()
        if not_match:
            parts.extend(["--not-match", _q(not_match)])

        if bool(params.get("hydra", False)):
            parts.append("--hydra")

        hydra_user = (params.get("hydra_user") or "").strip()
        if hydra_user:
            parts.extend(["--hydra-user", _q(hydra_user)])
        hydra_pass = (params.get("hydra_pass") or "").strip()
        if hydra_pass:
            parts.extend(["--hydra-pass", _q(hydra_pass)])
        if bool(params.get("hydra_update", False)):
            parts.append("--hydra-update")
        hydra_mod = (params.get("hydra_mod") or "").strip()
        if hydra_mod:
            parts.extend(["--hydra-mod", _q(hydra_mod)])

        fofa_size = params.get("fofa_size", None)
        if fofa_size is not None and str(fofa_size).strip() != "":
            try:
                fsz = int(fofa_size)
                if fsz > 0:
                    parts.extend(["--fofa-size", str(fsz)])
            except (TypeError, ValueError):
                pass

        fofa_fix = (params.get("fofa_fix_keyword") or "").strip()
        if fofa_fix:
            parts.extend(["--fofa-fix-keyword", _q(fofa_fix)])

        additional_args = (params.get("additional_args") or "").strip()
        if additional_args:
            parts.append(additional_args)

        command = " ".join(parts)
        logger.info(
            "🛰 Kscan: start (target=%s, fofa=%s, spy=%s)",
            bool(target),
            bool(fofa),
            use_spy,
        )
        result = execute_command(command)
        logger.info("📊 Kscan: done (success=%s)", result.get("success"))
        return jsonify(result)
    except Exception as e:
        logger.exception("Kscan endpoint error: %s", e)
        return jsonify({"error": f"Server error: {str(e)}"}), 500
