"""统领 Web 门户：静态页 + AI 智能体 / Skills REST API。"""

from __future__ import annotations

import os
import sys
from typing import Any, Dict, List

from flask import Blueprint, abort, g, jsonify, make_response, redirect, request, send_from_directory, Response

from claude_hexstrike_bridge import (
    MCP_SERVER_NAME,
    _find_npx_in_dir,
    build_mcp_stdio_payload,
    check_hexstrike_health,
    disable_burp_mcp,
    discover_all_agent_skills,
    enrich_loaded_skills_catalog,
    list_loaded_claude_skills,
    read_burp_mcp_status,
    read_project_mcp_servers,
    register_burp_mcp,
    register_claude_mcp,
    remove_claude_skills,
    resolve_claude_skill_name,
    skill_ids_for_packs,
    sync_skills_to_claude_workspace,
    DEFAULT_BURP_SSE_URL,
    BURP_MCP_SERVER_NAME,
)
from tongling_web.auth import (
    TOKEN_COOKIE,
    SERVICE_UNAVAILABLE_HTML,
    UNAUTHORIZED_HTML,
    api_auth_headers,
    append_token,
    bind_api_token_from_web,
    ensure_web_token,
    find_valid_token_from_request,
    get_web_token,
    portal_url,
    verify_token,
)
from tongling_web.pty_bridge import pty_available
from tongling_web.session_manager import terminal_manager
from tongling_web.ws_flask import WS_PATH, same_port_ws_available
from tongling_web.ws_server import get_ws_url, ws_port_for_api

HEXSTRIKE_CE_DIR = "hexstrike-ai-community-edition-master"
NODE_AI_DIR = "node_ai"
CLAUDE_CODE_SUBDIR = os.path.join("claude-code")
SKILL_DIR = "Skill"

_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
tongling_web_bp = Blueprint(
    "tongling_web",
    __name__,
    static_folder=_STATIC_DIR,
    static_url_path="/tongling/static",
)


def _tongling_root() -> str:
    return os.environ.get("TONGLING_ROOT") or os.path.dirname(os.path.dirname(__file__))


def _ensure_tongling_import_path() -> str:
    root = _tongling_root()
    if root not in sys.path:
        sys.path.insert(0, root)
    return root


def _storage() -> str:
    return os.path.join(_tongling_root(), "storage")


def _hexstrike_root() -> str:
    return os.path.join(_storage(), HEXSTRIKE_CE_DIR)


def _python311() -> str:
    cand = os.path.join(_storage(), "Python311", "python.exe")
    if os.path.isfile(cand):
        return cand
    if sys.platform != "win32":
        import shutil

        for name in (sys.executable, shutil.which("python3"), shutil.which("python")):
            if name and os.path.isfile(name):
                return os.path.normpath(name)
    return ""


def _mcp_py() -> str:
    return os.path.join(_hexstrike_root(), "hexstrike_mcp.py")


def _node_ai_dir() -> str:
    return os.path.join(_storage(), NODE_AI_DIR)


def _claude_workdir() -> str:
    return os.path.normpath(os.path.join(_node_ai_dir(), CLAUDE_CODE_SUBDIR))


def _npx_exe() -> str:
    na = _node_ai_dir()
    return _find_npx_in_dir(na) or _find_npx_in_dir(os.path.dirname(_claude_workdir()))


def _npm_registry_for_web() -> str:
    _ensure_tongling_import_path()
    try:
        from cc_visual.claude_launcher import resolve_npm_registry

        return resolve_npm_registry()
    except Exception:
        return "https://registry.npmmirror.com"


def _skill_root() -> str:
    return os.path.join(_storage(), SKILL_DIR)


def _api_port() -> int:
    try:
        return int(os.environ.get("HEXSTRIKE_PORT", "15038"))
    except ValueError:
        return 15038


def _guess_lan_ip() -> str:
    """用于在配置里提示手机访问地址（本机出网探测，非严谨）。"""
    import socket

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.3)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return ""


def _server_url() -> str:
    return f"http://127.0.0.1:{_api_port()}"


def _hexstrike_tool_stats() -> Dict[str, Any]:
    """Pull Tongling + HexStrike registry counts from local server."""
    import json as _json
    import urllib.error
    import urllib.request

    base = _server_url()
    headers = api_auth_headers()
    out: Dict[str, Any] = {}
    for path in ("/api/tongling/stats", "/api/tools"):
        try:
            req = urllib.request.Request(f"{base}{path}", headers=headers)
            with urllib.request.urlopen(req, timeout=6) as resp:
                data = _json.loads(resp.read().decode("utf-8", errors="replace"))
            if path.endswith("/stats") and data.get("success"):
                out.update(data)
            elif path.endswith("/tools") and data.get("success"):
                out["hexstrike_registry_total"] = data.get("total", len(data.get("tools") or []))
        except (urllib.error.URLError, OSError, ValueError, TypeError):
            continue
    return out


def _hexstrike_static_dir() -> str:
    return os.path.join(_tongling_root(), "storage", HEXSTRIKE_CE_DIR, "server_static")


_HS_TOKEN_BOOTSTRAP = """<script>
(function(){try{var t=new URLSearchParams(location.search).get('token');if(t)sessionStorage.setItem('hexstrike_token',t);}catch(e){}})();
</script>"""


def _hs_embed_index_html() -> str:
    path = os.path.join(_hexstrike_static_dir(), "index.html")
    with open(path, encoding="utf-8") as f:
        html = f.read()
    html = html.replace('"/assets/', '"/tongling/hs/assets/').replace("'/assets/", "'/tongling/hs/assets/")
    if _HS_TOKEN_BOOTSTRAP not in html:
        html = html.replace("<script type=\"module\"", _HS_TOKEN_BOOTSTRAP + "\n    <script type=\"module\"", 1)
    return html


def _register_hexstrike_ui_gate(app) -> None:
    """统领模式：根路径 / 与 /assets 永不提供 HexStrike 默认 UI。"""
    if getattr(app, "_tongling_ui_gate_registered", False):
        return
    app._tongling_ui_gate_registered = True

    @app.route("/", methods=["GET"], endpoint="tongling_root_redirect")
    def tongling_root_redirect():
        return redirect("/tongling/", code=302)

    @app.route("/assets/<path:filename>", methods=["GET"], endpoint="tongling_block_public_assets")
    def tongling_block_public_assets(filename):
        abort(404)


def register_tongling_web(app, tongling_root: str | None = None) -> None:
    if tongling_root:
        os.environ.setdefault("TONGLING_ROOT", tongling_root)
    token = ensure_web_token(tongling_root or _tongling_root())
    bind_api_token_from_web(token)
    from tongling_web.deps import ensure_simple_websocket
    from tongling_web.ws_flask import register_ws_route

    _register_hexstrike_ui_gate(app)
    ensure_simple_websocket()
    register_ws_route(tongling_web_bp)
    terminal_manager.set_audit_sync(lambda: (_server_url(), api_auth_headers()))
    from tongling_web.im_bridge.routes import im_bp
    from tongling_web.im_bridge.manager import im_manager

    app.register_blueprint(tongling_web_bp)
    app.register_blueprint(im_bp)
    im_manager.bootstrap()


@tongling_web_bp.before_request
def tongling_require_token():
    if request.path.startswith("/tongling/api/im/webhook/"):
        return None
    expected = get_web_token()
    if not expected:
        expected = ensure_web_token(_tongling_root())
    if not expected:
        if request.path.startswith("/tongling/api/"):
            return jsonify({"success": False, "error": "访问令牌未就绪，请重启服务"}), 503
        return make_response(SERVICE_UNAVAILABLE_HTML, 503)

    token = find_valid_token_from_request(request)
    if token:
        g.tongling_authed = True
        g.tongling_token_used = token
        return None
    if request.path.startswith("/tongling/api/"):
        return jsonify({"success": False, "error": "未授权，请在 URL 中提供有效 Token"}), 401
    return make_response(UNAUTHORIZED_HTML, 401)


@tongling_web_bp.after_request
def tongling_auth_cookie(response):
    tok = getattr(g, "tongling_token_used", None) or request.args.get("token")
    if getattr(g, "tongling_authed", False) and tok:
        response.set_cookie(
            TOKEN_COOKIE,
            tok,
            httponly=True,
            samesite="Lax",
            max_age=7 * 86400,
        )
    return response


@tongling_web_bp.route("/tongling/manifest.webmanifest")
def tongling_manifest():
    return send_from_directory(_STATIC_DIR, "manifest.webmanifest", mimetype="application/manifest+json")


@tongling_web_bp.route("/tongling/hs/")
@tongling_web_bp.route("/tongling/hs")
def tongling_hs_shell():
    """统领内嵌 HexStrike SPA（任务/工具/报告等），需 Token。"""
    return make_response(_hs_embed_index_html(), 200, {"Content-Type": "text/html; charset=utf-8"})


@tongling_web_bp.route("/tongling/hs/assets/<path:filename>")
def tongling_hs_assets(filename):
    return send_from_directory(os.path.join(_hexstrike_static_dir(), "assets"), filename)


@tongling_web_bp.route("/tongling")
@tongling_web_bp.route("/tongling/")
def tongling_index():
    return send_from_directory(_STATIC_DIR, "index.html")


@tongling_web_bp.route("/tongling/agent")
@tongling_web_bp.route("/tongling/agent/")
def tongling_agent():
    return send_from_directory(_STATIC_DIR, "index.html")


@tongling_web_bp.route("/tongling/skills")
@tongling_web_bp.route("/tongling/skills/")
def tongling_skills_page():
    return send_from_directory(_STATIC_DIR, "index.html")


@tongling_web_bp.route("/tongling/im")
@tongling_web_bp.route("/tongling/im/")
def tongling_im_page():
    return send_from_directory(_STATIC_DIR, "index.html")


@tongling_web_bp.route("/tongling/mcp")
@tongling_web_bp.route("/tongling/mcp/")
def tongling_mcp_page():
    return send_from_directory(_STATIC_DIR, "index.html")


@tongling_web_bp.route("/tongling/fingerprint")
@tongling_web_bp.route("/tongling/fingerprint/")
@tongling_web_bp.route("/tongling/fplib")
@tongling_web_bp.route("/tongling/fplib/")
def tongling_fingerprint_page():
    return send_from_directory(_STATIC_DIR, "index.html")


@tongling_web_bp.route("/tongling/vulnlib")
@tongling_web_bp.route("/tongling/vulnlib/")
@tongling_web_bp.route("/tongling/nuclei-lib")
@tongling_web_bp.route("/tongling/nuclei-lib/")
def tongling_vulnlib_page():
    return send_from_directory(_STATIC_DIR, "index.html")


@tongling_web_bp.route("/tongling/mindmap")
@tongling_web_bp.route("/tongling/mindmap/")
def tongling_mindmap_page():
    return send_from_directory(_STATIC_DIR, "scan-viz.html")


@tongling_web_bp.route("/tongling/scan")
@tongling_web_bp.route("/tongling/scan/")
def tongling_scan_page():
    return send_from_directory(_STATIC_DIR, "scan-viz.html")


@tongling_web_bp.route("/tongling/api/scan/overview", methods=["GET"])
def api_scan_overview():
    try:
        from tongling_web.scan_viz import build_overview

        return jsonify({"success": True, "source": "hexstrike", **build_overview()})
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@tongling_web_bp.route("/tongling/api/scan/claude/sessions", methods=["GET"])
def api_scan_claude_sessions():
    try:
        from tongling_web.scan_viz import _claude_sessions_meta, list_claude_scan_sessions

        workdir = request.args.get("workdir") or _claude_workdir()
        _ensure_claude_storage_marker(workdir)
        sessions = list_claude_scan_sessions(workdir)
        meta = _claude_sessions_meta(workdir)
        return jsonify(
            {
                "success": True,
                "source": "claude",
                "workdir": workdir,
                "count": len(sessions),
                "sessions": sessions,
                **meta,
            }
        )
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@tongling_web_bp.route("/tongling/api/scan/claude/<session_id>", methods=["GET"])
def api_scan_claude_session(session_id: str):
    try:
        from tongling_web.scan_viz import build_claude_session_view

        workdir = request.args.get("workdir") or _claude_workdir()
        aggregate = request.args.get("aggregate", "1") != "0"
        data = build_claude_session_view(session_id, workdir, aggregate=aggregate)
        if not data:
            return jsonify({"success": False, "error": "Claude 会话不存在"}), 404
        return jsonify({"success": True, **data})
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@tongling_web_bp.route("/tongling/api/scan/session/<session_id>", methods=["GET"])
def api_scan_session(session_id: str):
    try:
        from tongling_web.scan_viz import (
            _stats_from_runs,
            build_chain_bundle,
            build_graph_from_runs,
            load_session_detail,
            runs_for_hexstrike_session,
        )

        data = load_session_detail(session_id)
        if not data:
            return jsonify({"success": False, "error": "会话不存在"}), 404
        runs = runs_for_hexstrike_session(data)
        stats_bundle = _stats_from_runs(runs) if runs else {}
        graph = build_graph_from_runs(runs, source="hexstrike") if runs else {"nodes": [], "edges": [], "timeline": [], "phases": []}
        chain = build_chain_bundle(runs) if runs else build_chain_bundle([])
        return jsonify(
            {
                "success": True,
                "source": "hexstrike",
                "session": data,
                "stats": {
                    **{k: v for k, v in stats_bundle.items() if k not in ("recent_findings", "top_tools")},
                    "risk_score": chain["risk"]["score"],
                    "risk_level": chain["risk"]["level"],
                },
                "risk": chain["risk"],
                "facts": chain["facts"],
                "chain": chain,
                "graph": graph,
                "recent_findings": stats_bundle.get("recent_findings", []),
                "top_tools": stats_bundle.get("top_tools", []),
                "timeline": graph.get("timeline") or [],
                "phases": graph.get("phases") or [],
            }
        )
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@tongling_web_bp.route("/tongling/api/scan/run/<run_id>", methods=["GET"])
def api_scan_run_detail(run_id: str):
    try:
        from tongling_web.scan_viz import get_run_detail

        source = request.args.get("source") or "hexstrike"
        claude_session = request.args.get("claude_session") or ""
        workdir = request.args.get("workdir") or _claude_workdir()
        detail = get_run_detail(
            run_id,
            source=source,
            claude_session_id=claude_session,
            workdir=workdir,
        )
        if not detail:
            return jsonify({"success": False, "error": "运行记录不存在"}), 404
        return jsonify({"success": True, "run": detail})
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@tongling_web_bp.route("/tongling/api/scan/node/detail", methods=["GET"])
def api_scan_node_detail():
    try:
        from tongling_web.scan_viz import get_node_detail

        node_id = request.args.get("node_id") or ""
        source = request.args.get("source") or "hexstrike"
        claude_session = request.args.get("claude_session") or ""
        workdir = request.args.get("workdir") or _claude_workdir()
        detail = get_node_detail(
            node_id,
            source=source,
            claude_session_id=claude_session,
            workdir=workdir,
        )
        if not detail:
            return jsonify({"success": False, "error": "节点不存在或无法解析"}), 404
        return jsonify({"success": True, "node_id": node_id, "run": detail})
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@tongling_web_bp.route("/tongling/chat")
@tongling_web_bp.route("/tongling/chat/")
def tongling_chat_page():
    return send_from_directory(_STATIC_DIR, "chat.html")


@tongling_web_bp.route("/tongling/api/terminal/status", methods=["GET"])
def api_terminal_status():
    return jsonify({"success": True, **terminal_manager.status()})


_host_cpu_primed = False


def _host_resource_metrics() -> Dict[str, Any]:
    """本机 CPU / 内存占用（供工作台顶栏）。依赖 psutil。"""
    global _host_cpu_primed
    try:
        import psutil  # type: ignore
    except ImportError:
        return {"ok": False, "error": "psutil 未安装"}

    # 首次调用 cpu_percent(None) 往往为 0，先 priming
    if not _host_cpu_primed:
        psutil.cpu_percent(interval=None)
        _host_cpu_primed = True
    cpu = float(psutil.cpu_percent(interval=None))
    vm = psutil.virtual_memory()
    return {
        "ok": True,
        "cpu_percent": round(cpu, 1),
        "mem_percent": round(float(vm.percent), 1),
        "mem_used_gb": round(float(vm.used) / (1024 ** 3), 2),
        "mem_total_gb": round(float(vm.total) / (1024 ** 3), 2),
    }


@tongling_web_bp.route("/tongling/api/host/metrics", methods=["GET"])
def api_host_metrics():
    m = _host_resource_metrics()
    if not m.get("ok"):
        return jsonify({"success": False, "error": m.get("error") or "无法读取主机指标"}), 503
    return jsonify({"success": True, **m})


# ── 文件管理（本机任意目录可读写，类 Dolphin；默认落点为统领项目根）──
_FILES_LIST_LIMIT = 2000
_FILES_READ_MAX = 1024 * 1024  # 预览 / 在线编辑上限 1MB
_FILES_UPLOAD_MAX = 100 * 1024 * 1024  # 单文件上传 100MB
_FILES_COMPUTER = "__computer__"
_FILES_TEXT_EXTS = {
    ".txt", ".md", ".markdown", ".json", ".jsonl", ".yaml", ".yml", ".toml",
    ".ini", ".cfg", ".conf", ".env", ".py", ".js", ".ts", ".tsx", ".jsx",
    ".css", ".html", ".htm", ".xml", ".csv", ".log", ".sh", ".bat", ".ps1",
    ".sql", ".go", ".rs", ".java", ".c", ".h", ".cpp", ".hpp", ".rb", ".php",
    ".vue", ".svelte", ".gitignore", ".dockerignore", ".editorconfig",
}


def _files_project_root() -> str:
    return os.path.realpath(_tongling_root())


def _files_path_key(abs_path: str) -> str:
    """API 使用的统一路径键（正斜杠绝对路径）。"""
    p = os.path.realpath(abs_path)
    if sys.platform == "win32":
        p = p.replace("\\", "/")
        if len(p) == 2 and p[1] == ":":
            p += "/"
    return p


def _files_is_fs_root(abs_path: str) -> bool:
    """磁盘根 / 系统根（不可删改名）。"""
    p = os.path.realpath(abs_path)
    if sys.platform == "win32":
        _drive, tail = os.path.splitdrive(p)
        return bool(_drive) and tail in ("\\", "/", "")
    return p == os.path.realpath("/")


def _files_parent_key(abs_path: str, key: str) -> str:
    if key == _FILES_COMPUTER:
        return _FILES_COMPUTER
    if _files_is_fs_root(abs_path):
        return _FILES_COMPUTER if sys.platform == "win32" else "/"
    parent = os.path.dirname(abs_path)
    if parent == abs_path:
        return _FILES_COMPUTER if sys.platform == "win32" else "/"
    return _files_path_key(parent)


def _files_crumbs(abs_path: str, key: str) -> List[Dict[str, str]]:
    if key == _FILES_COMPUTER:
        return [{"name": "计算机", "path": _FILES_COMPUTER}]
    crumbs: List[Dict[str, str]] = []
    if sys.platform == "win32":
        crumbs.append({"name": "计算机", "path": _FILES_COMPUTER})
        drive, rest = os.path.splitdrive(abs_path)
        if not drive:
            return crumbs
        drive_abs = os.path.realpath(drive + os.sep)
        crumbs.append({"name": drive + "/", "path": _files_path_key(drive_abs)})
        parts = [p for p in rest.replace("\\", "/").split("/") if p]
        acc = drive_abs
        for part in parts:
            acc = os.path.join(acc, part)
            crumbs.append({"name": part, "path": _files_path_key(acc)})
        return crumbs
    crumbs.append({"name": "/", "path": "/"})
    parts = [p for p in key.split("/") if p]
    acc = "/"
    for part in parts:
        acc = "/" + part if acc == "/" else acc + "/" + part
        crumbs.append({"name": part, "path": acc})
    return crumbs


def _files_resolve(path: str | None) -> tuple[str, str]:
    """返回 (abs_path_or_sentinel, path_key)。支持绝对路径 / 相对项目路径 / ~ / 计算机。"""
    raw = (path if path is not None else "").strip().replace("\\", "/")
    if raw in ("", ".", "./"):
        abs_path = _files_project_root()
        if not os.path.isdir(abs_path):
            raise FileNotFoundError("项目目录不存在")
        return abs_path, _files_path_key(abs_path)
    if raw == _FILES_COMPUTER:
        return _FILES_COMPUTER, _FILES_COMPUTER
    if raw.startswith("~"):
        home = os.path.expanduser("~")
        rest = raw[1:].lstrip("/")
        abs_path = os.path.realpath(os.path.join(home, rest) if rest else home)
        return abs_path, _files_path_key(abs_path)

    is_abs = raw.startswith("/") or (len(raw) >= 2 and raw[1] == ":")
    if is_abs:
        if sys.platform == "win32" and len(raw) == 2 and raw[1] == ":":
            raw = raw + "/"
        abs_path = os.path.realpath(raw)
    else:
        if ".." in raw.split("/"):
            raise ValueError("非法路径")
        abs_path = os.path.realpath(os.path.join(_files_project_root(), raw.lstrip("/")))
    return abs_path, _files_path_key(abs_path)


def _files_safe_name(name: str) -> str:
    n = (name or "").strip().replace("\\", "/").split("/")[-1].strip()
    if not n or n in (".", "..") or "/" in n or "\\" in n:
        raise ValueError("非法文件名")
    if any(ch in n for ch in '<>:"|?*\x00'):
        raise ValueError("文件名包含非法字符")
    return n


def _files_join_child(parent_abs: str, name: str) -> str:
    if parent_abs == _FILES_COMPUTER:
        raise ValueError("不能在「计算机」下直接创建")
    parent_real = os.path.realpath(parent_abs)
    child = os.path.realpath(os.path.join(parent_real, name))
    if child != parent_real and not child.startswith(parent_real + os.sep):
        raise ValueError("非法目标路径")
    return child


def _files_entry(abs_path: str) -> Dict[str, Any]:
    st = os.stat(abs_path)
    is_dir = os.path.isdir(abs_path)
    name = os.path.basename(abs_path.rstrip("\\/")) or abs_path
    if sys.platform == "win32" and _files_is_fs_root(abs_path):
        drive, _ = os.path.splitdrive(abs_path)
        name = (drive or name) + "/"
    return {
        "name": name,
        "path": _files_path_key(abs_path),
        "type": "dir" if is_dir else "file",
        "size": 0 if is_dir else int(st.st_size),
        "mtime": int(st.st_mtime),
    }


def _files_list_drives() -> List[Dict[str, Any]]:
    import string

    entries: List[Dict[str, Any]] = []
    if sys.platform == "win32":
        for letter in string.ascii_uppercase:
            root = f"{letter}:\\"
            if not os.path.exists(root):
                continue
            try:
                entries.append(_files_entry(root))
            except OSError:
                entries.append(
                    {
                        "name": f"{letter}:/",
                        "path": f"{letter}:/",
                        "type": "dir",
                        "size": 0,
                        "mtime": 0,
                    }
                )
    else:
        try:
            entries.append(_files_entry("/"))
        except OSError:
            entries.append({"name": "/", "path": "/", "type": "dir", "size": 0, "mtime": 0})
    return entries


def _files_guess_user_dir(*names: str) -> str | None:
    home = os.path.expanduser("~")
    for name in names:
        cand = os.path.join(home, name)
        if os.path.isdir(cand):
            return os.path.realpath(cand)
    return None


def _files_json_error(exc: Exception, code: int = 400):
    return jsonify({"success": False, "error": str(exc)}), code


@tongling_web_bp.route("/tongling/api/files/places", methods=["GET"])
def api_files_places():
    """侧栏快捷位置（本机 + 项目）。"""
    project = _files_project_root()
    home = os.path.expanduser("~")
    desktop = _files_guess_user_dir("Desktop", "桌面")
    documents = _files_guess_user_dir("Documents", "文档")
    downloads = _files_guess_user_dir("Downloads", "下载")
    places: List[Dict[str, str]] = [
        {"id": "computer", "name": "计算机", "path": _FILES_COMPUTER, "icon": "▣"},
        {"id": "home", "name": "主目录", "path": _files_path_key(home), "icon": "⌂"},
    ]
    if desktop:
        places.append({"id": "desktop", "name": "桌面", "path": _files_path_key(desktop), "icon": "▦"})
    if documents:
        places.append({"id": "documents", "name": "文档", "path": _files_path_key(documents), "icon": "▤"})
    if downloads:
        places.append({"id": "downloads", "name": "下载", "path": _files_path_key(downloads), "icon": "⬇"})
    places.append({"id": "project", "name": "项目根", "path": _files_path_key(project), "icon": "⌘"})
    for rel, label, icon in (
        ("storage", "storage", "▣"),
        ("tongling_web", "tongling_web", "▤"),
        ("storage/node_ai/claude-code", "claude-code", "⌘"),
        ("logs", "logs", "≡"),
    ):
        abs_p = os.path.join(project, *rel.split("/"))
        if os.path.isdir(abs_p):
            places.append({"id": rel, "name": label, "path": _files_path_key(abs_p), "icon": icon})
    return jsonify(
        {
            "success": True,
            "project": _files_path_key(project),
            "home": _files_path_key(home),
            "places": places,
            "scope": "system",
        }
    )


@tongling_web_bp.route("/tongling/api/files/list", methods=["GET"])
def api_files_list():
    try:
        abs_path, key = _files_resolve(request.args.get("path"))
    except FileNotFoundError as e:
        return _files_json_error(e, 404)
    except ValueError as e:
        return _files_json_error(e, 400)

    entries: List[Dict[str, Any]] = []
    truncated = False
    if key == _FILES_COMPUTER:
        entries = _files_list_drives()
        parent = _FILES_COMPUTER
        crumbs = _files_crumbs(abs_path, key)
        return jsonify(
            {
                "success": True,
                "project": _files_path_key(_files_project_root()),
                "path": key,
                "parent": parent,
                "crumbs": crumbs,
                "entries": entries,
                "truncated": False,
                "limit": _FILES_LIST_LIMIT,
                "writable": False,
                "scope": "system",
            }
        )

    if not os.path.isdir(abs_path):
        return jsonify({"success": False, "error": "不是目录或不存在"}), 400
    try:
        names = os.listdir(abs_path)
    except OSError as e:
        return jsonify({"success": False, "error": f"无法读取目录：{e}"}), 500
    names.sort(key=lambda n: (not os.path.isdir(os.path.join(abs_path, n)), n.lower()))
    for name in names:
        if len(entries) >= _FILES_LIST_LIMIT:
            truncated = True
            break
        child = os.path.join(abs_path, name)
        try:
            entries.append(_files_entry(child))
        except OSError:
            continue
    parent = _files_parent_key(abs_path, key)
    crumbs = _files_crumbs(abs_path, key)
    return jsonify(
        {
            "success": True,
            "project": _files_path_key(_files_project_root()),
            "path": key,
            "parent": parent,
            "crumbs": crumbs,
            "entries": entries,
            "truncated": truncated,
            "limit": _FILES_LIST_LIMIT,
            "writable": True,
            "scope": "system",
        }
    )


@tongling_web_bp.route("/tongling/api/files/read", methods=["GET"])
def api_files_read():
    try:
        abs_path, key = _files_resolve(request.args.get("path"))
    except FileNotFoundError as e:
        return _files_json_error(e, 404)
    except ValueError as e:
        return _files_json_error(e, 400)
    if abs_path == _FILES_COMPUTER or not os.path.isfile(abs_path):
        return jsonify({"success": False, "error": "不是文件"}), 400
    size = os.path.getsize(abs_path)
    ext = os.path.splitext(abs_path)[1].lower()
    if ext and ext not in _FILES_TEXT_EXTS and size > 64 * 1024:
        return jsonify({"success": False, "error": "该类型不支持在线预览，请下载", "path": key, "size": size}), 415
    truncated = size > _FILES_READ_MAX
    try:
        with open(abs_path, "rb") as f:
            raw = f.read(_FILES_READ_MAX + 1)
        if len(raw) > _FILES_READ_MAX:
            raw = raw[:_FILES_READ_MAX]
            truncated = True
        if b"\x00" in raw[:4096]:
            return jsonify({"success": False, "error": "二进制文件不支持预览", "path": key, "size": size}), 415
        text = raw.decode("utf-8", errors="replace")
    except OSError as e:
        return jsonify({"success": False, "error": str(e)}), 500
    return jsonify(
        {
            "success": True,
            "path": key,
            "name": os.path.basename(abs_path),
            "size": size,
            "truncated": truncated,
            "editable": not truncated and (not ext or ext in _FILES_TEXT_EXTS),
            "content": text,
        }
    )


@tongling_web_bp.route("/tongling/api/files/download", methods=["GET"])
def api_files_download():
    try:
        abs_path, _key = _files_resolve(request.args.get("path"))
    except FileNotFoundError as e:
        return _files_json_error(e, 404)
    except ValueError as e:
        return _files_json_error(e, 400)
    if abs_path == _FILES_COMPUTER or not os.path.isfile(abs_path):
        return jsonify({"success": False, "error": "不是文件"}), 400
    return send_from_directory(
        os.path.dirname(abs_path),
        os.path.basename(abs_path),
        as_attachment=True,
        download_name=os.path.basename(abs_path),
    )


@tongling_web_bp.route("/tongling/api/files/mkdir", methods=["POST"])
def api_files_mkdir():
    body = request.get_json(silent=True) or {}
    try:
        parent_abs, _ = _files_resolve(body.get("path"))
        name = _files_safe_name(str(body.get("name") or ""))
        if parent_abs == _FILES_COMPUTER or not os.path.isdir(parent_abs):
            raise ValueError("父路径不是目录")
        dest = _files_join_child(parent_abs, name)
        if os.path.exists(dest):
            raise ValueError("已存在同名项")
        os.makedirs(dest, exist_ok=False)
        return jsonify({"success": True, "path": _files_path_key(dest), "type": "dir"})
    except (FileNotFoundError, ValueError, OSError) as e:
        code = 404 if isinstance(e, FileNotFoundError) else 400
        return _files_json_error(e, code)


@tongling_web_bp.route("/tongling/api/files/create", methods=["POST"])
def api_files_create():
    body = request.get_json(silent=True) or {}
    try:
        parent_abs, _ = _files_resolve(body.get("path"))
        name = _files_safe_name(str(body.get("name") or ""))
        if parent_abs == _FILES_COMPUTER or not os.path.isdir(parent_abs):
            raise ValueError("父路径不是目录")
        dest = _files_join_child(parent_abs, name)
        if os.path.exists(dest):
            raise ValueError("已存在同名项")
        content = body.get("content")
        with open(dest, "w", encoding="utf-8", newline="") as f:
            if content is not None:
                f.write(str(content))
        return jsonify({"success": True, "path": _files_path_key(dest), "type": "file"})
    except (FileNotFoundError, ValueError, OSError) as e:
        code = 404 if isinstance(e, FileNotFoundError) else 400
        return _files_json_error(e, code)


@tongling_web_bp.route("/tongling/api/files/write", methods=["POST"])
def api_files_write():
    body = request.get_json(silent=True) or {}
    try:
        abs_path, key = _files_resolve(body.get("path"))
        if abs_path == _FILES_COMPUTER or not os.path.isfile(abs_path):
            raise ValueError("不是文件")
        content = body.get("content")
        if content is None:
            raise ValueError("缺少 content")
        raw = str(content).encode("utf-8")
        if len(raw) > _FILES_READ_MAX * 2:
            raise ValueError("内容过大")
        with open(abs_path, "wb") as f:
            f.write(raw)
        return jsonify({"success": True, "path": key, "size": len(raw)})
    except (FileNotFoundError, ValueError, OSError) as e:
        code = 404 if isinstance(e, FileNotFoundError) else 400
        return _files_json_error(e, code)


@tongling_web_bp.route("/tongling/api/files/rename", methods=["POST"])
def api_files_rename():
    body = request.get_json(silent=True) or {}
    try:
        abs_path, key = _files_resolve(body.get("path"))
        if abs_path == _FILES_COMPUTER or _files_is_fs_root(abs_path):
            raise ValueError("不能重命名磁盘根目录")
        new_name = _files_safe_name(str(body.get("new_name") or ""))
        parent = os.path.dirname(abs_path)
        dest = _files_join_child(parent, new_name)
        if os.path.exists(dest):
            raise ValueError("目标名称已存在")
        os.rename(abs_path, dest)
        return jsonify({"success": True, "from": key, "path": _files_path_key(dest)})
    except (FileNotFoundError, ValueError, OSError) as e:
        code = 404 if isinstance(e, FileNotFoundError) else 400
        return _files_json_error(e, code)


@tongling_web_bp.route("/tongling/api/files/delete", methods=["POST"])
def api_files_delete():
    import shutil

    body = request.get_json(silent=True) or {}
    paths = body.get("paths") or body.get("path")
    if isinstance(paths, str):
        paths = [paths]
    if not isinstance(paths, list) or not paths:
        return jsonify({"success": False, "error": "缺少 paths"}), 400
    deleted: List[str] = []
    errors: List[str] = []
    for p in paths:
        try:
            abs_path, key = _files_resolve(str(p))
            if abs_path == _FILES_COMPUTER or _files_is_fs_root(abs_path):
                raise ValueError("不能删除磁盘根目录")
            if os.path.isdir(abs_path) and not os.path.islink(abs_path):
                shutil.rmtree(abs_path)
            else:
                os.remove(abs_path)
            deleted.append(key)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{p}: {e}")
    ok = bool(deleted) and not errors
    return jsonify({"success": ok or (bool(deleted) and bool(errors)), "deleted": deleted, "errors": errors, "partial": bool(deleted and errors)})


@tongling_web_bp.route("/tongling/api/files/copy", methods=["POST"])
def api_files_copy():
    import shutil

    body = request.get_json(silent=True) or {}
    try:
        src_abs, src_key = _files_resolve(body.get("src"))
        dest_dir_abs, _ = _files_resolve(body.get("dest_dir"))
        if src_abs == _FILES_COMPUTER or dest_dir_abs == _FILES_COMPUTER:
            raise ValueError("无效的复制位置")
        if not os.path.isdir(dest_dir_abs):
            raise ValueError("目标不是目录")
        name = _files_safe_name(str(body.get("name") or os.path.basename(src_abs.rstrip("\\/"))))
        dest = _files_join_child(dest_dir_abs, name)
        if os.path.exists(dest):
            raise ValueError("目标已存在")
        if os.path.isdir(src_abs) and not os.path.islink(src_abs):
            shutil.copytree(src_abs, dest)
        else:
            shutil.copy2(src_abs, dest)
        return jsonify({"success": True, "from": src_key, "path": _files_path_key(dest)})
    except (FileNotFoundError, ValueError, OSError) as e:
        code = 404 if isinstance(e, FileNotFoundError) else 400
        return _files_json_error(e, code)


@tongling_web_bp.route("/tongling/api/files/move", methods=["POST"])
def api_files_move():
    import shutil

    body = request.get_json(silent=True) or {}
    try:
        src_abs, src_key = _files_resolve(body.get("src"))
        if src_abs == _FILES_COMPUTER or _files_is_fs_root(src_abs):
            raise ValueError("不能移动磁盘根目录")
        dest_dir_abs, _ = _files_resolve(body.get("dest_dir"))
        if dest_dir_abs == _FILES_COMPUTER or not os.path.isdir(dest_dir_abs):
            raise ValueError("目标不是目录")
        name = _files_safe_name(str(body.get("name") or os.path.basename(src_abs.rstrip("\\/"))))
        dest = _files_join_child(dest_dir_abs, name)
        if os.path.exists(dest):
            raise ValueError("目标已存在")
        if os.path.isdir(src_abs):
            common = os.path.commonpath([src_abs, dest])
            if common == src_abs:
                raise ValueError("不能移动到自身子目录")
        shutil.move(src_abs, dest)
        return jsonify({"success": True, "from": src_key, "path": _files_path_key(dest)})
    except (FileNotFoundError, ValueError, OSError) as e:
        code = 404 if isinstance(e, FileNotFoundError) else 400
        return _files_json_error(e, code)


@tongling_web_bp.route("/tongling/api/files/upload", methods=["POST"])
def api_files_upload():
    try:
        parent_abs, parent_key = _files_resolve(request.form.get("path") or "")
        if parent_abs == _FILES_COMPUTER or not os.path.isdir(parent_abs):
            raise ValueError("目标不是目录")
        files = request.files.getlist("files") or request.files.getlist("file")
        if not files:
            raise ValueError("未选择文件")
        saved: List[str] = []
        for f in files:
            if not f or not f.filename:
                continue
            name = _files_safe_name(os.path.basename(f.filename.replace("\\", "/")))
            dest = _files_join_child(parent_abs, name)
            written = 0
            with open(dest, "wb") as out:
                while True:
                    chunk = f.stream.read(1024 * 256)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > _FILES_UPLOAD_MAX:
                        out.close()
                        try:
                            os.remove(dest)
                        except OSError:
                            pass
                        raise ValueError(f"{name} 超过 {_FILES_UPLOAD_MAX // (1024 * 1024)}MB 限制")
                    out.write(chunk)
            saved.append(_files_path_key(dest))
        if not saved:
            raise ValueError("未写入任何文件")
        return jsonify({"success": True, "dir": parent_key, "paths": saved})
    except (FileNotFoundError, ValueError, OSError) as e:
        code = 404 if isinstance(e, FileNotFoundError) else 400
        return _files_json_error(e, code)


@tongling_web_bp.route("/tongling/api/files/reveal", methods=["POST"])
def api_files_reveal():
    """在系统文件管理器中打开目录（或选中文件所在目录）。"""
    import subprocess

    body = request.get_json(silent=True) or {}
    try:
        abs_path, key = _files_resolve(body.get("path") or request.args.get("path"))
    except FileNotFoundError as e:
        return _files_json_error(e, 404)
    except ValueError as e:
        return _files_json_error(e, 400)

    if abs_path == _FILES_COMPUTER:
        if sys.platform == "win32":
            abs_path = os.path.expanduser("~")
            key = _files_path_key(abs_path)
        else:
            abs_path = "/"
            key = "/"

    target = abs_path
    select_file = False
    if os.path.isfile(abs_path):
        select_file = True
        target = os.path.dirname(abs_path)
    if not os.path.isdir(target):
        return jsonify({"success": False, "error": "目录不存在"}), 404

    try:
        if sys.platform == "win32":
            if select_file and os.path.isfile(abs_path):
                subprocess.Popen(["explorer", "/select,", abs_path], shell=False)
            else:
                os.startfile(target)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            if select_file and os.path.isfile(abs_path):
                subprocess.Popen(["open", "-R", abs_path])
            else:
                subprocess.Popen(["open", target])
        else:
            subprocess.Popen(["xdg-open", target])
    except OSError as e:
        return jsonify({"success": False, "error": f"无法打开：{e}"}), 500

    return jsonify(
        {
            "success": True,
            "path": key,
            "opened": target,
            "message": "已在系统文件管理器中打开",
        }
    )


@tongling_web_bp.route("/tongling/api/config", methods=["GET"])
def api_config():
    port = _api_port()
    py_exe = _python311()
    mcp_py = _mcp_py()
    cc_dir = _claude_workdir()
    payload = build_mcp_stdio_payload(py_exe, mcp_py, _server_url(), "full") if py_exe and os.path.isfile(mcp_py) else {}
    ok, hs_msg = check_hexstrike_health(_server_url())
    ws_port = ws_port_for_api(port)
    client_host = (request.host or "").split(":")[0]
    bind_host = os.environ.get("HEXSTRIKE_HOST", "0.0.0.0")
    lan_ip = _guess_lan_ip()
    token = get_web_token()
    mobile_base = f"http://{lan_ip}:{port}/tongling/" if lan_ip else ""
    mobile_url = append_token(mobile_base, token) if mobile_base and token else mobile_base
    ws_same_port = same_port_ws_available()
    providers_data = _providers_snapshot()
    tool_stats = _hexstrike_tool_stats() if ok else {}
    burp_status = read_burp_mcp_status(cc_dir)
    from tongling_web.runtime_guard import runtime_security_flags

    return jsonify(
        {
            "success": True,
            "web_token": token,
            "api_port": port,
            "api_base": _server_url(),
            "bind_host": bind_host,
            "ws_port": ws_port,
            "ws_url": get_ws_url(port, client_host),
            "ws_same_port": ws_same_port,
            "ws_path": WS_PATH if ws_same_port else "",
            "ws_dual": ws_same_port,
            "mobile_url": mobile_url,
            "pty_available": pty_available(),
            "hexstrike_healthy": ok,
            "hexstrike_message": hs_msg,
            "hexstrike_tool_stats": tool_stats,
            "claude_workdir": cc_dir,
            "claude_workdir_exists": os.path.isdir(cc_dir),
            "npm_registry": _npm_registry_for_web(),
            "python311": py_exe,
            "mcp_script": mcp_py,
            "mcp_server_name": MCP_SERVER_NAME,
            "mcp_payload": payload,
            "burp_mcp": {
                "server_name": BURP_MCP_SERVER_NAME,
                "default_sse_url": DEFAULT_BURP_SSE_URL,
                **burp_status,
            },
            "providers_data": providers_data,
            **runtime_security_flags(),
        }
    )


def _recommended_skill_ids(all_skills: List[Dict[str, str]]) -> List[str]:
    """与桌面 SkillPickerDialog 一致的推荐逻辑。"""
    packs = ["01-信息搜集-Reconnaissance", "hexstrike-ce/web-recon", "hexstrike-ce"]
    rec_ids = set(skill_ids_for_packs(all_skills, packs))
    for sk in all_skills:
        blob = f"{sk.get('id', '')} {sk.get('pack', '')} {sk.get('name', '')}".lower()
        if any(
            k in blob
            for k in ("web-recon", "recon", "osint", "信息搜集", "subfinder", "httpx", "nmap")
        ):
            rec_ids.add(sk["id"])
    return sorted(rec_ids)


@tongling_web_bp.route("/tongling/api/skills", methods=["GET"])
def api_skills_list():
    skills = discover_all_agent_skills(_skill_root(), _hexstrike_root())
    packs = sorted({sk.get("pack") or "" for sk in skills if sk.get("pack")})
    return jsonify(
        {
            "success": True,
            "skills": skills,
            "count": len(skills),
            "packs": packs,
            "recommended_ids": _recommended_skill_ids(skills),
        }
    )


@tongling_web_bp.route("/tongling/api/skills/loaded", methods=["GET"])
def api_skills_loaded():
    cc_dir = request.args.get("workdir") or _claude_workdir()
    if not os.path.isdir(cc_dir):
        return jsonify({"success": False, "error": f"工作目录不存在: {cc_dir}"}), 400
    loaded = list_loaded_claude_skills(cc_dir)
    all_skills = discover_all_agent_skills(_skill_root(), _hexstrike_root())
    loaded = enrich_loaded_skills_catalog(loaded, all_skills)
    return jsonify(
        {
            "success": True,
            "loaded": loaded,
            "count": len(loaded),
            "workdir": cc_dir,
        }
    )


@tongling_web_bp.route("/tongling/api/skills/remove", methods=["POST"])
def api_skills_remove():
    body: Dict[str, Any] = request.get_json(silent=True) or {}
    names: List[str] = body.get("names") or []
    cc_dir = body.get("workdir") or _claude_workdir()
    if not names:
        return jsonify({"success": False, "error": "未指定要移除的 Skill"}), 400
    if not os.path.isdir(cc_dir):
        return jsonify({"success": False, "error": f"工作目录不存在: {cc_dir}"}), 400
    removed, logs = remove_claude_skills(cc_dir, names)
    return jsonify(
        {
            "success": bool(removed),
            "removed": removed,
            "count": len(removed),
            "logs": logs[:30],
            "workdir": cc_dir,
        }
    )


@tongling_web_bp.route("/tongling/api/skills/sync", methods=["POST"])
def api_skills_sync():
    body: Dict[str, Any] = request.get_json(silent=True) or {}
    skill_ids: List[str] = body.get("skill_ids") or []
    cc_dir = body.get("workdir") or _claude_workdir()
    if not os.path.isdir(cc_dir):
        return jsonify({"success": False, "error": f"工作目录不存在: {cc_dir}"}), 400
    all_skills = discover_all_agent_skills(_skill_root(), _hexstrike_root())
    if skill_ids:
        id_set = set(skill_ids)
        selected = [s for s in all_skills if s.get("id") in id_set]
    else:
        selected = all_skills
    if not selected:
        return jsonify({"success": False, "error": "未选中任何 Skill"}), 400
    synced, logs = sync_skills_to_claude_workspace(cc_dir, selected)
    return jsonify(
        {
            "success": bool(synced),
            "synced": synced,
            "count": len(synced),
            "logs": logs[:30],
            "workdir": cc_dir,
        }
    )


@tongling_web_bp.route("/tongling/api/mcp/status", methods=["GET"])
def api_mcp_status():
    """MCP 页：HexStrike 就绪状态、待写入/已写入 .mcp.json 预览。"""
    cc_dir = _claude_workdir()
    py_exe = _python311()
    mcp_py = _mcp_py()
    ok, hs_msg = check_hexstrike_health(_server_url())
    payload = (
        build_mcp_stdio_payload(py_exe, mcp_py, _server_url(), "full")
        if py_exe and os.path.isfile(mcp_py)
        else {}
    )
    servers = read_project_mcp_servers(cc_dir) if os.path.isdir(cc_dir) else {}
    hex_entry = servers.get(MCP_SERVER_NAME) if isinstance(servers, dict) else None
    hex_configured = isinstance(hex_entry, dict)
    hex_enabled = hex_configured and not bool(hex_entry.get("disabled"))
    tool_stats = _hexstrike_tool_stats() if ok else {}
    return jsonify(
        {
            "success": True,
            "workdir": cc_dir,
            "workdir_exists": os.path.isdir(cc_dir),
            "hexstrike_healthy": ok,
            "hexstrike_message": hs_msg,
            "mcp_server_name": MCP_SERVER_NAME,
            "mcp_script": mcp_py,
            "python311": py_exe,
            "hexstrike_configured": hex_configured,
            "hexstrike_enabled": hex_enabled,
            "pending_payload": payload,
            "mcp_servers": servers,
            "mcp_json_path": os.path.join(cc_dir, ".mcp.json") if cc_dir else "",
            "tool_stats": tool_stats,
            "burp_mcp": read_burp_mcp_status(cc_dir) if os.path.isdir(cc_dir) else {},
        }
    )


@tongling_web_bp.route("/tongling/api/mcp/connect", methods=["POST"])
def api_mcp_connect():
    body: Dict[str, Any] = request.get_json(silent=True) or {}
    cc_dir = body.get("workdir") or _claude_workdir()
    profile = str(body.get("profile") or "full")
    if not os.path.isdir(cc_dir):
        return jsonify({"success": False, "error": f"工作目录不存在: {cc_dir}"}), 400
    py_exe = _python311()
    mcp_py = _mcp_py()
    if not py_exe or not os.path.isfile(mcp_py):
        return jsonify({"success": False, "error": "未找到 Python311 或 hexstrike_mcp.py"}), 500
    ok, hs_msg = check_hexstrike_health(_server_url())
    if not ok:
        return jsonify({"success": False, "error": hs_msg}), 503
    payload = build_mcp_stdio_payload(py_exe, mcp_py, _server_url(), profile)
    ok_mcp, detail = register_claude_mcp(
        cc_dir, _npx_exe(), payload, MCP_SERVER_NAME, node_ai_dir=_node_ai_dir()
    )
    if not ok_mcp:
        return jsonify({"success": False, "error": detail or "MCP 注册失败"}), 500

    burp_notes: List[str] = []
    if "burp" in body:
        burp_cfg = body.get("burp") if isinstance(body.get("burp"), dict) else {}
        burp_enabled = bool(burp_cfg.get("enabled"))
        if burp_enabled:
            ok_burp, burp_msg = register_burp_mcp(
                cc_dir,
                str(burp_cfg.get("proxy_jar") or "").strip(),
                str(burp_cfg.get("sse_url") or DEFAULT_BURP_SSE_URL).strip(),
                str(burp_cfg.get("java") or "java").strip(),
            )
            if ok_burp:
                burp_notes.append(burp_msg)
            else:
                burp_notes.append(f"Burp MCP 未注册: {burp_msg}")
        else:
            disable_burp_mcp(cc_dir)
            burp_notes.append("Burp MCP 已禁用（.mcp.json 中保留条目）")

    tool_stats = _hexstrike_tool_stats()
    reg_total = int(tool_stats.get("hexstrike_registry_total") or 0)
    catalog_total = int(tool_stats.get("catalog_total") or 0)
    if reg_total and catalog_total:
        detail = (
            f"{detail}\n"
            f"HexStrike 注册表 {reg_total} 个工具（统领目录 {catalog_total} 个，"
            f"tools_config {tool_stats.get('tools_config_count', 0)} + "
            f"toollist CLI {tool_stats.get('toollist_cli_count', 0)}）。"
            f"请新建 Claude 终端后输入 /mcp 查看。"
        )
    if burp_notes:
        detail = detail + "\n" + "\n".join(burp_notes)
    return jsonify(
        {
            "success": True,
            "detail": detail,
            "tool_stats": tool_stats,
            "burp_mcp": read_burp_mcp_status(cc_dir),
            "mcp_json_path": os.path.join(cc_dir, ".mcp.json"),
            "workdir": cc_dir,
        }
    )


def _build_library_mcp_payload(mcp_script: str, description: str) -> Dict[str, Any]:
    py_exe = _python311()
    env = {
        "TONGLING_ROOT": _tongling_root(),
        "HEXSTRIKE_PORT": str(_api_port()),
    }
    token = (os.environ.get("HEXSTRIKE_API_TOKEN") or os.environ.get("TONGLING_WEB_TOKEN") or "").strip()
    if token:
        env["HEXSTRIKE_API_TOKEN"] = token
        env["TONGLING_WEB_TOKEN"] = token
    return {
        "command": py_exe,
        "args": [mcp_script],
        "description": description,
        "timeout": 600,
        "disabled": False,
        "env": env,
    }


def _library_mcp_status(server_name: str, mcp_script: str, description: str) -> Dict[str, Any]:
    cc_dir = _claude_workdir()
    py_exe = _python311()
    script_ok = os.path.isfile(mcp_script)
    payload = _build_library_mcp_payload(mcp_script, description) if py_exe and script_ok else {}
    servers = read_project_mcp_servers(cc_dir) if os.path.isdir(cc_dir) else {}
    entry = servers.get(server_name) if isinstance(servers, dict) else None
    configured = isinstance(entry, dict) and not entry.get("disabled")
    return {
        "mcp_server_name": server_name,
        "mcp_script": mcp_script,
        "python311": py_exe,
        "script_exists": script_ok,
        "configured": configured,
        "pending_payload": payload,
        "mcp_servers": servers,
        "mcp_json_path": os.path.join(cc_dir, ".mcp.json") if cc_dir else "",
        "workdir": cc_dir,
    }


@tongling_web_bp.route("/tongling/api/lib/fingerprint/status", methods=["GET"])
def api_lib_fingerprint_status():
    from tongling_web.library_paths import HFINGER_MCP_SERVER_NAME, hfinger_json_path, hfinger_mcp_script
    from tongling_web.library_service import get_fingerprint_library

    try:
        stats = get_fingerprint_library().stats()
        st = _library_mcp_status(
            HFINGER_MCP_SERVER_NAME,
            str(hfinger_mcp_script()),
            "HFinger 指纹库 — 统领 MCP",
        )
        return jsonify({"success": True, "stats": stats, **st})
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@tongling_web_bp.route("/tongling/api/lib/fingerprint/connect", methods=["POST"])
def api_lib_fingerprint_connect():
    from tongling_web.library_paths import HFINGER_MCP_SERVER_NAME, hfinger_json_path, hfinger_mcp_script

    if not hfinger_json_path().is_file():
        return jsonify({"success": False, "error": f"指纹库不存在: {hfinger_json_path()}"}), 404
    cc_dir = (request.get_json(silent=True) or {}).get("workdir") or _claude_workdir()
    if not os.path.isdir(cc_dir):
        return jsonify({"success": False, "error": f"工作目录不存在: {cc_dir}"}), 400
    py_exe = _python311()
    script = str(hfinger_mcp_script())
    if not py_exe or not os.path.isfile(script):
        return jsonify({"success": False, "error": "未找到 Python311 或 hfinger_mcp.py"}), 500
    payload = _build_library_mcp_payload(script, "HFinger 指纹库 — 统领 MCP")
    ok, detail = register_claude_mcp(
        cc_dir, _npx_exe(), payload, HFINGER_MCP_SERVER_NAME, node_ai_dir=_node_ai_dir()
    )
    if not ok:
        return jsonify({"success": False, "error": detail or "MCP 注册失败"}), 500
    return jsonify(
        {
            "success": True,
            "detail": detail + "\n请新建 Claude 终端后输入 /mcp 查看 hfinger-lib 工具。",
            "mcp_json_path": os.path.join(cc_dir, ".mcp.json"),
            "workdir": cc_dir,
        }
    )


@tongling_web_bp.route("/tongling/api/lib/fingerprint/search", methods=["GET"])
def api_lib_fingerprint_search():
    from tongling_web.library_service import get_fingerprint_library

    q = request.args.get("q") or ""
    category = request.args.get("category") or ""
    try:
        limit = int(request.args.get("limit") or 24)
    except ValueError:
        limit = 24
    try:
        data = get_fingerprint_library().search(q=q, category=category, limit=limit)
        return jsonify({"success": True, **data})
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@tongling_web_bp.route("/tongling/api/lib/fingerprint/<fp_id>", methods=["GET"])
def api_lib_fingerprint_get(fp_id: str):
    from tongling_web.library_service import get_fingerprint_library

    try:
        item = get_fingerprint_library().get(fp_id)
        if not item:
            return jsonify({"success": False, "error": "指纹不存在"}), 404
        return jsonify({"success": True, "item": item})
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@tongling_web_bp.route("/tongling/api/lib/nuclei/status", methods=["GET"])
def api_lib_nuclei_status():
    from tongling_web.library_paths import NUCLEI_LIB_MCP_SERVER_NAME, nuclei_lib_mcp_script, nuclei_templates_dir
    from tongling_web.library_service import get_nuclei_library

    try:
        stats = get_nuclei_library().stats()
        st = _library_mcp_status(
            NUCLEI_LIB_MCP_SERVER_NAME,
            str(nuclei_lib_mcp_script()),
            "Nuclei 漏洞模板库 — 统领 MCP",
        )
        st["templates_dir"] = str(nuclei_templates_dir())
        return jsonify({"success": True, "stats": stats, **st})
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@tongling_web_bp.route("/tongling/api/lib/pocs/bootstrap", methods=["POST"])
def api_lib_pocs_bootstrap():
    """打开漏洞库 Tab 时调用：检测模板、按需拉取 Afrog POC、建索引，并返回分步进度。"""
    from tongling_web.library_sync import ensure_poc_libraries_ready

    body = request.get_json(silent=True) or {}
    use_proxy = body.get("use_proxy", True)
    try:
        result = ensure_poc_libraries_ready(use_proxy=bool(use_proxy), auto_sync_afrog=True)
        if not result.get("ok"):
            return jsonify({"success": False, **result}), 404
        return jsonify({"success": True, **result})
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc), "steps": []}), 500


@tongling_web_bp.route("/tongling/api/lib/nuclei/connect", methods=["POST"])
def api_lib_nuclei_connect():
    from tongling_web.library_paths import (
        NUCLEI_LIB_MCP_SERVER_NAME,
        afrog_pocs_dir,
        nuclei_lib_mcp_script,
        nuclei_templates_dir,
    )

    if not nuclei_templates_dir().is_dir() and not afrog_pocs_dir().is_dir():
        return jsonify(
            {"success": False, "error": "漏洞库目录不存在，请先点击「拉取最新 POC」"}
        ), 404
    cc_dir = (request.get_json(silent=True) or {}).get("workdir") or _claude_workdir()
    if not os.path.isdir(cc_dir):
        return jsonify({"success": False, "error": f"工作目录不存在: {cc_dir}"}), 400
    py_exe = _python311()
    script = str(nuclei_lib_mcp_script())
    if not py_exe or not os.path.isfile(script):
        return jsonify({"success": False, "error": "未找到 Python311 或 nuclei_lib_mcp.py"}), 500
    payload = _build_library_mcp_payload(script, "Nuclei 漏洞模板库 — 统领 MCP")
    ok, detail = register_claude_mcp(
        cc_dir, _npx_exe(), payload, NUCLEI_LIB_MCP_SERVER_NAME, node_ai_dir=_node_ai_dir()
    )
    if not ok:
        return jsonify({"success": False, "error": detail or "MCP 注册失败"}), 500
    return jsonify(
        {
            "success": True,
            "detail": detail + "\n请新建 Claude 终端后输入 /mcp 查看 nuclei-lib 工具。",
            "mcp_json_path": os.path.join(cc_dir, ".mcp.json"),
            "workdir": cc_dir,
        }
    )


@tongling_web_bp.route("/tongling/api/lib/pocs/sync", methods=["POST"])
def api_lib_pocs_sync():
    from tongling_web.library_sync import sync_all_poc_libraries

    body = request.get_json(silent=True) or {}
    use_proxy = body.get("use_proxy", True)
    try:
        result = sync_all_poc_libraries(use_proxy=bool(use_proxy))
        if not result.get("ok"):
            return jsonify({"success": False, **result}), 500
        return jsonify({"success": True, **result})
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@tongling_web_bp.route("/tongling/api/lib/nuclei/reindex", methods=["POST"])
def api_lib_nuclei_reindex():
    from tongling_web.library_service import get_nuclei_library

    try:
        result = get_nuclei_library().reindex()
        if not result.get("ok"):
            return jsonify({"success": False, **result}), 404
        stats = get_nuclei_library().stats()
        return jsonify({"success": True, **result, "stats": stats})
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@tongling_web_bp.route("/tongling/api/lib/nuclei/search", methods=["GET"])
def api_lib_nuclei_search():
    from tongling_web.library_service import get_nuclei_library

    q = request.args.get("q") or ""
    severity = request.args.get("severity") or ""
    tags = request.args.get("tags") or ""
    source = request.args.get("source") or ""
    try:
        limit = int(request.args.get("limit") or 24)
    except ValueError:
        limit = 24
    try:
        data = get_nuclei_library().search(q=q, severity=severity, tags=tags, source=source, limit=limit)
        return jsonify({"success": True, **data})
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@tongling_web_bp.route("/tongling/api/lib/nuclei/<entry_id>", methods=["GET"])
def api_lib_nuclei_get(entry_id: str):
    from tongling_web.library_service import get_nuclei_library

    try:
        item = get_nuclei_library().get(entry_id)
        if not item:
            return jsonify({"success": False, "error": "模板不存在"}), 404
        return jsonify({"success": True, "item": item})
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


def _provider_to_json(profile) -> Dict[str, Any]:
    return {
        "id": profile.id,
        "name": profile.name,
        "summary": profile.masked_summary(),
        "model_hint": profile.model_hint,
        "notes": profile.notes,
        "builtin": profile.builtin,
    }


def _provider_env_form(profile) -> Dict[str, Any]:
    from cc_visual.provider_manager import _mask_secret

    token = profile.env.get("ANTHROPIC_AUTH_TOKEN") or profile.env.get("ANTHROPIC_API_KEY") or ""
    return {
        "ANTHROPIC_BASE_URL": profile.env.get("ANTHROPIC_BASE_URL", ""),
        "ANTHROPIC_MODEL": profile.env.get("ANTHROPIC_MODEL", ""),
        "ANTHROPIC_DEFAULT_SONNET_MODEL": profile.env.get("ANTHROPIC_DEFAULT_SONNET_MODEL", ""),
        "ANTHROPIC_DEFAULT_OPUS_MODEL": profile.env.get("ANTHROPIC_DEFAULT_OPUS_MODEL", ""),
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": profile.env.get("ANTHROPIC_DEFAULT_HAIKU_MODEL", ""),
        "token_masked": f"key:{_mask_secret(token)}" if token else "",
        "token_set": bool(str(token).strip()),
    }


def _find_provider(provider_id: str):
    from cc_visual.provider_manager import list_all_providers

    for p in list_all_providers():
        if p.id == provider_id:
            return p
    return None


def _profile_from_body(body: Dict[str, Any]):
    from cc_visual.provider_manager import ProviderProfile

    env_in = body.get("env") or {}
    env: Dict[str, str] = {}
    for key in (
        "ANTHROPIC_BASE_URL",
        "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_MODEL",
        "ANTHROPIC_DEFAULT_SONNET_MODEL",
        "ANTHROPIC_DEFAULT_OPUS_MODEL",
        "ANTHROPIC_DEFAULT_HAIKU_MODEL",
    ):
        val = env_in.get(key)
        if val is not None and str(val).strip():
            env[key] = str(val).strip()
    pid = str(body.get("id") or "").strip()
    existing = _find_provider(pid) if pid else None
    return ProviderProfile(
        id=pid or "",
        name=str(body.get("name") or (existing.name if existing else "")).strip() or "未命名",
        env=env,
        model_hint=str(env.get("ANTHROPIC_MODEL") or body.get("model_hint") or "").strip(),
        notes=str(body.get("notes") or "").strip(),
        builtin=bool(existing and existing.builtin),
    )


def _providers_response_extra():
    from cc_visual.provider_manager import get_active_provider, read_live_env

    active = get_active_provider()
    live = read_live_env()
    return {
        "active_id": active.id if active else "",
        "active_name": active.name if active else "",
        "active_summary": active.masked_summary() if active else "",
        "live_env": _mask_live_env(live),
        "live_model": live.get("ANTHROPIC_MODEL", ""),
    }


def _providers_snapshot() -> Dict[str, Any]:
    """提供商列表快照，供 /config 与 /providers 共用。"""
    try:
        _ensure_tongling_import_path()
        from cc_visual.provider_manager import (
            get_active_provider,
            get_active_provider_id,
            list_all_providers,
            read_live_env,
        )

        active = get_active_provider()
        live = read_live_env()
        return {
            "active_id": get_active_provider_id(),
            "active_name": active.name if active else "",
            "active_summary": active.masked_summary() if active else "",
            "live_env": _mask_live_env(live),
            "live_model": live.get("ANTHROPIC_MODEL", ""),
            "providers": [_provider_to_json(p) for p in list_all_providers()],
        }
    except Exception as exc:
        return {"error": str(exc), "providers": []}


def _mask_live_env(env: Dict[str, str]) -> Dict[str, str]:
    from cc_visual.provider_manager import _mask_secret

    out: Dict[str, str] = {}
    for key, value in env.items():
        if key in ("ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY"):
            out[key] = f"key:{_mask_secret(value)}"
        else:
            out[key] = value
    return out


@tongling_web_bp.route("/tongling/api/providers", methods=["GET"])
def api_providers_list():
    snap = _providers_snapshot()
    if snap.get("error") and not snap.get("providers"):
        return jsonify({"success": False, "error": snap["error"]}), 500
    return jsonify({"success": True, **snap})


@tongling_web_bp.route("/tongling/api/providers/active", methods=["POST"])
def api_providers_set_active():
    _ensure_tongling_import_path()
    from cc_visual.provider_manager import set_active_provider

    body: Dict[str, Any] = request.get_json(silent=True) or {}
    provider_id = str(body.get("id") or "").strip()
    if not provider_id:
        return jsonify({"success": False, "error": "缺少提供商 id"}), 400

    ok, msg = set_active_provider(provider_id)
    if not ok:
        return jsonify({"success": False, "error": msg}), 400

    from cc_visual.provider_manager import get_active_provider, read_live_env

    active = get_active_provider()
    live = read_live_env()
    return jsonify(
        {
            "success": True,
            "message": msg,
            "active_id": provider_id,
            "active_name": active.name if active else "",
            "active_summary": active.masked_summary() if active else "",
            "live_env": _mask_live_env(live),
            "live_model": live.get("ANTHROPIC_MODEL", ""),
        }
    )


@tongling_web_bp.route("/tongling/api/providers/<provider_id>", methods=["GET"])
def api_providers_get(provider_id: str):
    _ensure_tongling_import_path()
    profile = _find_provider(provider_id)
    if not profile:
        return jsonify({"success": False, "error": "提供商不存在"}), 404
    return jsonify(
        {
            "success": True,
            "provider": {**_provider_to_json(profile), "env_form": _provider_env_form(profile)},
        }
    )


@tongling_web_bp.route("/tongling/api/providers/save", methods=["POST"])
def api_providers_save():
    """保存自定义提供商，或覆盖应用内置/自定义 env（与桌面 ProviderPanel 一致）。"""
    _ensure_tongling_import_path()
    from cc_visual.provider_manager import (
        ProviderProfile,
        apply_provider_to_claude_settings,
        mark_active_provider,
        save_custom_provider,
    )

    body: Dict[str, Any] = request.get_json(silent=True) or {}
    apply = bool(body.get("apply", True))
    profile = _profile_from_body(body)
    existing = _find_provider(profile.id) if profile.id else None

    if existing and existing.builtin:
        merged_env = dict(existing.env)
        merged_env.update(profile.env)
        profile = ProviderProfile(
            id=existing.id,
            name=profile.name or existing.name,
            env=merged_env,
            model_hint=profile.model_hint or existing.model_hint,
            notes=profile.notes or existing.notes,
            builtin=True,
        )
        saved = profile
    else:
        if not profile.name:
            return jsonify({"success": False, "error": "请填写名称"}), 400
        saved = save_custom_provider(
            ProviderProfile(
                id=profile.id,
                name=profile.name,
                env=profile.env,
                model_hint=profile.model_hint,
                notes=profile.notes,
                builtin=False,
            )
        )

    message = f"已保存：{saved.name}"
    if apply:
        token_sent = bool(
            (body.get("env") or {}).get("ANTHROPIC_AUTH_TOKEN")
            or (body.get("env") or {}).get("ANTHROPIC_API_KEY")
        )
        ok, msg = apply_provider_to_claude_settings(saved, preserve_token=not token_sent)
        if not ok:
            return jsonify({"success": False, "error": msg}), 500
        mark_active_provider(saved.id)
        message = f"已保存并应用：{saved.name} · 请新建终端生效"

    snap = _providers_snapshot()
    return jsonify(
        {
            "success": True,
            "message": message,
            "provider": {**_provider_to_json(saved), "env_form": _provider_env_form(saved)},
            **snap,
        }
    )


@tongling_web_bp.route("/tongling/api/providers/<provider_id>", methods=["DELETE"])
def api_providers_delete(provider_id: str):
    _ensure_tongling_import_path()
    from cc_visual.provider_manager import delete_custom_provider

    profile = _find_provider(provider_id)
    if not profile:
        return jsonify({"success": False, "error": "提供商不存在"}), 404
    if profile.builtin:
        return jsonify({"success": False, "error": "内置预设不可删除"}), 400
    if not delete_custom_provider(provider_id):
        return jsonify({"success": False, "error": "删除失败"}), 400
    snap = _providers_snapshot()
    return jsonify({"success": True, "message": "已删除", **snap})


@tongling_web_bp.route("/tongling/api/providers/import", methods=["POST"])
def api_providers_import():
    _ensure_tongling_import_path()
    from cc_visual.provider_manager import import_from_claude_settings

    body: Dict[str, Any] = request.get_json(silent=True) or {}
    name = str(body.get("name") or "从当前配置导入").strip()
    try:
        profile = import_from_claude_settings(name)
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    snap = _providers_snapshot()
    return jsonify(
        {
            "success": True,
            "message": f"已导入：{profile.name}",
            "provider": {**_provider_to_json(profile), "env_form": _provider_env_form(profile)},
            **snap,
        }
    )


@tongling_web_bp.route("/tongling/api/providers/test", methods=["POST"])
def api_providers_test():
    """测试 API Key 是否可用（Anthropic 兼容 messages 接口）。"""
    _ensure_tongling_import_path()
    from cc_visual.provider_manager import resolve_env_for_test, test_provider_api

    body: Dict[str, Any] = request.get_json(silent=True) or {}
    env_in = body.get("env") or {}
    env_override: Dict[str, str] = {}
    for key in (
        "ANTHROPIC_BASE_URL",
        "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_MODEL",
        "ANTHROPIC_DEFAULT_HAIKU_MODEL",
    ):
        val = env_in.get(key)
        if val is not None and str(val).strip():
            env_override[key] = str(val).strip()

    provider_id = str(body.get("id") or "").strip()
    if not provider_id and not env_override.get("ANTHROPIC_BASE_URL"):
        provider_id = str(_providers_snapshot().get("active_id") or "").strip()

    env = resolve_env_for_test(provider_id=provider_id, env_override=env_override or None)
    ok, message, meta = test_provider_api(env)
    return jsonify(
        {
            "success": ok,
            "valid": ok,
            "message": message,
            "endpoint": meta.get("endpoint", ""),
            "model": meta.get("model", ""),
            "elapsed_ms": meta.get("elapsed_ms"),
            "http_status": meta.get("http_status"),
        }
    ), (200 if ok else 400)


def _claude_session_dict(session) -> Dict[str, Any]:
    return {
        "session_id": session.session_id,
        "title": session.title,
        "first_prompt": (session.first_prompt or "")[:200],
        "summary": session.summary or "",
        "message_count": session.message_count,
        "modified": session.modified.isoformat() if session.modified else "",
        "modified_text": session.modified_text,
        "git_branch": session.git_branch or "",
    }


def _ensure_claude_storage_marker(workdir: str) -> None:
    """写入 .tongling/claude_storage.json，便于定位 subst Z: 下的 Z-- 会话目录。"""
    _ensure_tongling_import_path()
    try:
        from cc_visual.claude_session import _path_needs_subst, write_storage_marker

        write_storage_marker(workdir, subst=_path_needs_subst(workdir))
    except Exception:
        pass


@tongling_web_bp.route("/tongling/api/claude/sessions", methods=["GET"])
def api_claude_sessions():
    """列出 Claude Code 本地会话（~/.claude/projects/）。"""
    _ensure_tongling_import_path()
    from cc_visual.claude_session import find_all_project_storages, list_sessions

    workdir = request.args.get("workdir") or _claude_workdir()
    _ensure_claude_storage_marker(workdir)
    try:
        sessions = list_sessions(workdir)
        storages = find_all_project_storages(workdir)
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500
    return jsonify(
        {
            "success": True,
            "workdir": workdir,
            "count": len(sessions),
            "storage_dirs": [p.name for p in storages],
            "sessions": [_claude_session_dict(s) for s in sessions],
        }
    )


@tongling_web_bp.route("/tongling/api/claude/sessions/<session_id>", methods=["GET"])
def api_claude_session_detail(session_id: str):
    """单个 Claude 会话摘要与最近活动。"""
    _ensure_tongling_import_path()
    from cc_visual.claude_session import list_sessions, parse_session_activities

    workdir = request.args.get("workdir") or _claude_workdir()
    try:
        sessions = list_sessions(workdir)
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500
    target = next((s for s in sessions if s.session_id == session_id), None)
    if not target:
        return jsonify({"success": False, "error": "会话不存在"}), 404
    events = parse_session_activities(target.path, max_events=40)
    return jsonify(
        {
            "success": True,
            "session": _claude_session_dict(target),
            "activities": [
                {
                    "kind": e.kind,
                    "title": e.title,
                    "detail": (e.detail or "")[:500],
                    "timestamp": e.timestamp.isoformat() if e.timestamp else "",
                    "tool_name": e.tool_name,
                }
                for e in events
            ],
        }
    )


@tongling_web_bp.route("/tongling/api/audit", methods=["GET"])
def api_audit_list():
    from tongling_web import audit_store

    limit = int(request.args.get("limit") or 50)
    audits = audit_store.list_tasks(limit=limit)
    return jsonify({"success": True, "audits": audits, "count": len(audits)})


@tongling_web_bp.route("/tongling/api/audit/<audit_id>", methods=["GET"])
def api_audit_detail(audit_id: str):
    from tongling_web import audit_store

    task = audit_store.get_task(audit_id)
    if not task:
        return jsonify({"success": False, "error": "审计任务不存在"}), 404
    include_terminal = request.args.get("terminal") == "1"
    payload: Dict[str, Any] = {"success": True, "audit": task}
    if include_terminal:
        payload["terminal_tail"] = audit_store.read_terminal_tail(audit_id)
    payload["events"] = audit_store.load_events(audit_id, limit=int(request.args.get("events") or 100))
    return jsonify(payload)


@tongling_web_bp.route("/tongling/api/audit/<audit_id>/sync", methods=["POST"])
def api_audit_sync(audit_id: str):
    from tongling_web import audit_store

    if not audit_store.get_task(audit_id):
        return jsonify({"success": False, "error": "审计任务不存在"}), 404
    added = audit_store.sync_hexstrike_runs(audit_id, _server_url(), api_auth_headers())
    task = audit_store.get_task(audit_id)
    return jsonify({"success": True, "added": added, "audit": task})


@tongling_web_bp.route("/tongling/api/audit/<audit_id>/report", methods=["GET"])
def api_audit_report(audit_id: str):
    from tongling_web import audit_store

    if not audit_store.get_task(audit_id):
        return jsonify({"success": False, "error": "审计任务不存在"}), 404
    content = audit_store.read_report(audit_id)
    fmt = (request.args.get("format") or "markdown").lower()
    if fmt == "json":
        return jsonify({"success": True, "audit_id": audit_id, "report": content})
    return Response(content, mimetype="text/markdown; charset=utf-8")


@tongling_web_bp.route("/tongling/api/reports", methods=["GET"])
def api_reports_list():
    from tongling_web import report_store

    workdir = request.args.get("workdir") or _claude_workdir()
    limit = int(request.args.get("limit") or 80)
    reports = report_store.list_reports(workdir, limit=limit)
    return jsonify(
        {
            "success": True,
            "reports": reports,
            "count": len(reports),
            "workdir": workdir,
            "reports_dir": report_store.claude_reports_dir(workdir),
        }
    )


@tongling_web_bp.route("/tongling/api/reports/<path:report_id>", methods=["GET"])
def api_reports_get(report_id: str):
    from tongling_web import report_store

    workdir = request.args.get("workdir") or _claude_workdir()
    ok, content, meta = report_store.read_report_content(report_id, workdir)
    if not ok:
        return jsonify({"success": False, "error": content, **meta}), 404
    fmt = (request.args.get("format") or "markdown").lower()
    if fmt == "json":
        return jsonify({"success": True, "content": content, **meta})
    return Response(content, mimetype="text/markdown; charset=utf-8")


@tongling_web_bp.route("/tongling/api/scan/prepare", methods=["POST"])
def api_scan_prepare():
    """准备 Claude Code 扫描：写入 CLAUDE.md、约定报告路径、返回首条指令。"""
    _ensure_tongling_import_path()
    from claude_hexstrike_bridge import (
        MCP_SERVER_NAME,
        SCAN_SCENARIOS,
        build_claude_agent_prompt,
        build_mcp_stdio_payload,
        check_hexstrike_health,
        register_claude_mcp,
        write_hexstrike_project_files,
    )
    from tongling_web import report_store

    body: Dict[str, Any] = request.get_json(silent=True) or {}
    target = str(body.get("target") or "").strip()
    if not target:
        return jsonify({"success": False, "error": "请填写扫描目标（URL / IP / 域名）"}), 400

    scenario_id = str(body.get("scenario") or "vuln_scan").strip()
    profile = str(body.get("profile") or "full").strip()
    cc_dir = body.get("workdir") or _claude_workdir()
    if not os.path.isdir(cc_dir):
        return jsonify({"success": False, "error": f"Claude 工作目录不存在: {cc_dir}"}), 400

    ok, hs_msg = check_hexstrike_health(_server_url())
    if not ok:
        return jsonify({"success": False, "error": hs_msg}), 503

    py_exe = _python311()
    mcp_py = _mcp_py()
    if body.get("register_mcp", True) and py_exe and os.path.isfile(mcp_py):
        payload = build_mcp_stdio_payload(py_exe, mcp_py, _server_url(), profile)
        reg_ok, reg_log = register_claude_mcp(
            cc_dir, _npx_exe(), payload, MCP_SERVER_NAME, node_ai_dir=_node_ai_dir()
        )
        if not reg_ok:
            return jsonify({"success": False, "error": reg_log or "MCP 注册失败"}), 500

    report_rel = str(body.get("report_path") or "").strip() or report_store.default_scan_report_relpath(target)
    report_store.ensure_reports_dir(cc_dir)

    base_prompt = build_claude_agent_prompt(target, scenario_id)
    save_hint = (
        f"\n\n扫描完成后，请将完整漏洞扫描报告写入 `{report_rel}`（Markdown），"
        "包含：目标、范围、工具摘要、漏洞列表（含等级与证据）、修复建议、结论。"
    )
    initial_prompt = base_prompt + save_hint

    write_hexstrike_project_files(
        cc_dir,
        target,
        _server_url(),
        profile,
        initial_prompt,
        report_relpath=report_rel,
    )

    scenario_label = next((lbl for sid, lbl, _ in SCAN_SCENARIOS if sid == scenario_id), scenario_id)
    return jsonify(
        {
            "success": True,
            "message": f"已准备扫描：{target}",
            "target": target,
            "scenario": scenario_id,
            "scenario_label": scenario_label,
            "initial_prompt": initial_prompt,
            "report_path": report_rel,
            "report_abs": os.path.join(cc_dir, report_rel.replace("/", os.sep)),
            "workdir": cc_dir,
            "hexstrike_message": hs_msg,
        }
    )


@tongling_web_bp.route("/tongling/api/nps/status", methods=["GET"])
def api_nps_status():
    from tongling_web.nps_tunnel import tunnel_status

    return jsonify({"success": True, **tunnel_status(api_port=_api_port())})


@tongling_web_bp.route("/tongling/api/nps/prefs", methods=["POST"])
def api_nps_save_prefs():
    from tongling_web.nps_tunnel import load_prefs, save_prefs

    body = request.get_json(silent=True) or {}
    prefs = load_prefs()
    for key in ("server_addr", "vkey", "tunnel_type"):
        if key in body and body[key] is not None:
            prefs[key] = body[key]
    save_prefs(prefs)
    return jsonify({"success": True, "prefs": prefs})


@tongling_web_bp.route("/tongling/api/prompts", methods=["GET"])
def api_prompts_list():
    from tongling_web import prompt_store

    tag = request.args.get("tag") or ""
    q = request.args.get("q") or ""
    enabled_only = (request.args.get("enabled") or "").lower() in ("1", "true", "yes")
    items = prompt_store.list_prompts(tag=tag, q=q, enabled_only=enabled_only)
    return jsonify(
        {
            "success": True,
            "prompts": items,
            "tags": prompt_store.tag_labels(),
            "stats": prompt_store.stats(),
        }
    )


@tongling_web_bp.route("/tongling/api/prompts/<prompt_id>", methods=["GET"])
def api_prompts_get(prompt_id: str):
    from tongling_web import prompt_store

    item = prompt_store.get_prompt(prompt_id)
    if not item:
        return jsonify({"success": False, "error": "模板不存在"}), 404
    return jsonify({"success": True, "prompt": item})


@tongling_web_bp.route("/tongling/api/prompts", methods=["POST"])
def api_prompts_create():
    from tongling_web import prompt_store

    body = request.get_json(silent=True) or {}
    ok, msg, item = prompt_store.create_prompt(body)
    if not ok:
        return jsonify({"success": False, "error": msg}), 400
    return jsonify({"success": True, "message": msg, "prompt": item})


@tongling_web_bp.route("/tongling/api/prompts/<prompt_id>", methods=["PUT", "PATCH"])
def api_prompts_update(prompt_id: str):
    from tongling_web import prompt_store

    body = request.get_json(silent=True) or {}
    ok, msg, item = prompt_store.update_prompt(prompt_id, body)
    if not ok:
        code = 404 if "不存在" in msg else 400
        return jsonify({"success": False, "error": msg}), code
    return jsonify({"success": True, "message": msg, "prompt": item})


@tongling_web_bp.route("/tongling/api/prompts/<prompt_id>", methods=["DELETE"])
def api_prompts_delete(prompt_id: str):
    from tongling_web import prompt_store

    ok, msg = prompt_store.delete_prompt(prompt_id)
    if not ok:
        code = 404 if "不存在" in msg else 400
        return jsonify({"success": False, "error": msg}), code
    return jsonify({"success": True, "message": msg})


@tongling_web_bp.route("/tongling/api/prompts/<prompt_id>/render", methods=["POST"])
def api_prompts_render(prompt_id: str):
    from tongling_web import prompt_store

    body = request.get_json(silent=True) or {}
    variables = body.get("variables") if isinstance(body.get("variables"), dict) else {}
    if body.get("target") is not None:
        variables["target"] = body.get("target")
    if body.get("report_path") is not None:
        variables["report_path"] = body.get("report_path")
    ok, msg, item = prompt_store.render_prompt(prompt_id, variables)
    if not ok:
        code = 404 if "不存在" in msg else 400
        return jsonify({"success": False, "error": msg}), code
    return jsonify({"success": True, "prompt": item, "rendered": item.get("rendered")})


@tongling_web_bp.route("/tongling/api/prompts/<prompt_id>/reset", methods=["POST"])
def api_prompts_reset(prompt_id: str):
    from tongling_web import prompt_store

    ok, msg, item = prompt_store.reset_builtin(prompt_id)
    if not ok:
        return jsonify({"success": False, "error": msg}), 400
    return jsonify({"success": True, "message": msg, "prompt": item})


@tongling_web_bp.route("/tongling/api/nps/start", methods=["POST"])
def api_nps_start():
    from tongling_web.nps_tunnel import start_tunnel

    body = request.get_json(silent=True) or {}
    ok, msg = start_tunnel(api_port=_api_port(), prefs=body or None)
    if not ok:
        return jsonify({"success": False, "error": msg}), 400
    return jsonify({"success": True, "message": msg})


@tongling_web_bp.route("/tongling/api/nps/stop", methods=["POST"])
def api_nps_stop():
    from tongling_web.nps_tunnel import stop_tunnel

    ok, msg = stop_tunnel()
    return jsonify({"success": True, "message": msg})
