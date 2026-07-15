"""社交软件接入 REST API + Webhook。"""

from __future__ import annotations

import os
from typing import Any, Dict

from flask import Blueprint, g, jsonify, make_response, request

from tongling_web.auth import (
    find_valid_token_from_request,
    get_web_token,
    ensure_web_token,
)
from tongling_web.im_bridge.config_store import load_config, save_config
from tongling_web.im_bridge.manager import im_manager
from tongling_web.im_bridge.test_connection import test_platform

im_bp = Blueprint("tongling_im", __name__)


def _tongling_root() -> str:
    return os.environ.get("TONGLING_ROOT") or os.path.dirname(os.path.dirname(__file__))


@im_bp.before_request
def im_require_token():
    if request.path.startswith("/tongling/api/im/webhook/"):
        return None
    expected = get_web_token() or ensure_web_token(_tongling_root())
    if not expected:
        return jsonify({"success": False, "error": "访问令牌未就绪"}), 503
    token = find_valid_token_from_request(request)
    if not token:
        return jsonify({"success": False, "error": "未授权"}), 401
    g.tongling_authed = True
    return None


def _claude_workdir() -> str:
    root = os.environ.get("TONGLING_ROOT") or os.path.dirname(os.path.dirname(__file__))
    return os.path.normpath(os.path.join(root, "storage", "node_ai", "claude-code"))


def _webhook_urls(base_url: str) -> Dict[str, str]:
    base = (base_url or "").rstrip("/")
    return {
        "dingtalk": f"{base}/tongling/api/im/webhook/dingtalk",
        "qq": f"{base}/tongling/api/im/webhook/qq",
        "telegram": "（Telegram 使用 Bot 长轮询，无需公网 Webhook）",
    }


@im_bp.route("/tongling/api/im/config", methods=["GET"])
def api_im_config_get():
    cfg = load_config()
    public = im_manager.public_config()
    api_base = request.host_url.rstrip("/")
    return jsonify(
        {
            "success": True,
            "config": public,
            "defaults": {"workdir": _claude_workdir()},
            "webhooks": _webhook_urls(api_base),
            "raw_enabled": bool(cfg.get("enabled")),
        }
    )


@im_bp.route("/tongling/api/im/config", methods=["POST"])
def api_im_config_save():
    body: Dict[str, Any] = request.get_json(silent=True) or {}
    cfg = load_config()
    for key in ("enabled", "workdir", "proxy", "reply_timeout_sec", "mirror_to_terminal", "terminal_proxy_enabled", "default_terminal_id"):
        if key in body:
            cfg[key] = body[key]
    plats = body.get("platforms")
    if isinstance(plats, dict):
        base_plats = cfg.setdefault("platforms", {})
        secret_keys = ("bot_token", "app_secret", "app_key", "access_token", "verification_token")
        for name, plat in plats.items():
            if name not in base_plats or not isinstance(plat, dict):
                continue
            for k, v in plat.items():
                if k in secret_keys:
                    text = str(v or "")
                    if not text or "…" in text or text == "****":
                        continue
                base_plats[name][k] = v
    if not str(cfg.get("workdir") or "").strip():
        cfg["workdir"] = _claude_workdir()
    save_config(cfg)
    if cfg.get("enabled"):
        im_manager.restart()
    else:
        im_manager.stop()
    return jsonify({"success": True, "config": im_manager.public_config()})


@im_bp.route("/tongling/api/im/status", methods=["GET"])
def api_im_status():
    api_base = request.host_url.rstrip("/")
    return jsonify(
        {
            "success": True,
            **im_manager.status(),
            "webhooks": _webhook_urls(api_base),
        }
    )


@im_bp.route("/tongling/api/im/start", methods=["POST"])
def api_im_start():
    im_manager.start()
    return jsonify({"success": True, **im_manager.status()})


@im_bp.route("/tongling/api/im/stop", methods=["POST"])
def api_im_stop():
    im_manager.stop()
    return jsonify({"success": True, **im_manager.status()})


@im_bp.route("/tongling/api/im/test", methods=["POST"])
def api_im_test():
    body: Dict[str, Any] = request.get_json(silent=True) or {}
    platform = str(body.get("platform") or "").strip().lower()
    if not platform:
        return jsonify({"success": False, "error": "缺少 platform 参数"}), 400
    plat_cfg = body.get("config") if isinstance(body.get("config"), dict) else {}
    send_test = bool(body.get("send_test"))
    test_target = str(body.get("test_target") or "").strip()
    result = test_platform(platform, plat_cfg, send_test=send_test, test_target=test_target)
    return jsonify({"success": result.get("success"), **result})


@im_bp.route("/tongling/api/im/webhook/<platform>", methods=["POST"])
def api_im_webhook(platform: str):
    payload = request.get_json(silent=True) or {}
    headers = {k: v for k, v in request.headers.items()}
    qtok = request.args.get("access_token")
    if qtok:
        headers["_query_access_token"] = qtok
    result = im_manager.handle_webhook(platform, payload, headers)
    if isinstance(result, dict):
        return jsonify(result)
    return jsonify({"success": True})
