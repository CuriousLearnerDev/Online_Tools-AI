"""IM 桥接配置持久化 — storage/im_bridge/config.json"""

from __future__ import annotations

import json
import os
import threading
from copy import deepcopy
from typing import Any, Dict

_lock = threading.Lock()

DEFAULT_CONFIG: Dict[str, Any] = {
    "enabled": False,
    "workdir": "",
    "proxy": "",
    "reply_timeout_sec": 300,
    "mirror_to_terminal": True,
    "terminal_proxy_enabled": True,
    "default_terminal_id": "",
    "platforms": {
        "telegram": {
            "enabled": False,
            "bot_token": "",
            "allowed_chat_ids": [],
        },
        "dingtalk": {
            "enabled": False,
            "app_key": "",
            "app_secret": "",
            "webhook_url": "",
        },
        "qq": {
            "enabled": False,
            "access_token": "",
            "onebot_http_url": "http://127.0.0.1:3000",
        },
    },
    "chat_sessions": {},
}


def _root() -> str:
    return os.environ.get("TONGLING_ROOT") or os.path.dirname(os.path.dirname(os.path.dirname(__file__)))


def config_path() -> str:
    return os.path.join(_root(), "storage", "im_bridge", "config.json")


def _merge_defaults(data: Dict[str, Any]) -> Dict[str, Any]:
    out = deepcopy(DEFAULT_CONFIG)
    if not isinstance(data, dict):
        return out
    for key in ("enabled", "workdir", "proxy", "reply_timeout_sec", "mirror_to_terminal", "terminal_proxy_enabled", "default_terminal_id"):
        if key in data:
            out[key] = data[key]
    plats = data.get("platforms")
    if isinstance(plats, dict):
        for name, cfg in plats.items():
            if name in out["platforms"] and isinstance(cfg, dict):
                out["platforms"][name].update(cfg)
    sessions = data.get("chat_sessions")
    if isinstance(sessions, dict):
        out["chat_sessions"] = sessions
    return out


def load_config() -> Dict[str, Any]:
    path = config_path()
    with _lock:
        if not os.path.isfile(path):
            return deepcopy(DEFAULT_CONFIG)
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            return _merge_defaults(data if isinstance(data, dict) else {})
        except (OSError, json.JSONDecodeError):
            return deepcopy(DEFAULT_CONFIG)


def save_config(config: Dict[str, Any]) -> None:
    path = config_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    merged = _merge_defaults(config if isinstance(config, dict) else {})
    tmp = path + ".tmp"
    with _lock:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(merged, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)


def get_chat_session(chat_key: str) -> Dict[str, Any]:
    cfg = load_config()
    sessions = cfg.get("chat_sessions") or {}
    entry = sessions.get(chat_key)
    return dict(entry) if isinstance(entry, dict) else {}


def set_chat_session(chat_key: str, entry: Dict[str, Any]) -> None:
    cfg = load_config()
    sessions = dict(cfg.get("chat_sessions") or {})
    sessions[chat_key] = entry
    cfg["chat_sessions"] = sessions
    save_config(cfg)
