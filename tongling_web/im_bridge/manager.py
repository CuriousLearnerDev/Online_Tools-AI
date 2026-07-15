"""IM 桥接生命周期管理。"""

from __future__ import annotations

import logging
import threading
from typing import Any, Dict

from tongling_web.im_bridge.adapters.dingtalk import DingTalkAdapter
from tongling_web.im_bridge.adapters.qq_onebot import QqOneBotAdapter
from tongling_web.im_bridge.adapters.telegram import TelegramAdapter
from tongling_web.im_bridge.config_store import load_config, save_config

logger = logging.getLogger(__name__)


class ImBridgeManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._started = False
        self._adapters = {
            "telegram": TelegramAdapter(),
            "dingtalk": DingTalkAdapter(),
            "qq": QqOneBotAdapter(),
        }

    def bootstrap(self) -> None:
        cfg = load_config()
        if cfg.get("enabled"):
            self.start()

    def start(self) -> None:
        with self._lock:
            cfg = load_config()
            cfg["enabled"] = True
            save_config(cfg)
            for name, adapter in self._adapters.items():
                plat = (cfg.get("platforms") or {}).get(name) or {}
                if plat.get("enabled"):
                    try:
                        adapter.start()
                        logger.info("IM adapter started: %s", name)
                    except Exception:
                        logger.exception("IM adapter start failed: %s", name)
            self._started = True

    def stop(self) -> None:
        with self._lock:
            cfg = load_config()
            cfg["enabled"] = False
            save_config(cfg)
            for adapter in self._adapters.values():
                try:
                    adapter.stop()
                except Exception:
                    pass
            self._started = False

    def restart(self) -> None:
        self.stop()
        self.start()

    def status(self) -> Dict[str, Any]:
        cfg = load_config()
        platforms = {}
        for name, adapter in self._adapters.items():
            plat_cfg = (cfg.get("platforms") or {}).get(name) or {}
            st = adapter.status()
            st["enabled"] = bool(plat_cfg.get("enabled"))
            platforms[name] = st
        return {
            "bridge_enabled": bool(cfg.get("enabled")),
            "started": self._started,
            "workdir": cfg.get("workdir") or "",
            "reply_timeout_sec": cfg.get("reply_timeout_sec") or 300,
            "platforms": platforms,
        }

    def handle_webhook(self, platform: str, payload: Dict[str, Any], headers: Dict[str, str]) -> Any:
        adapter = self._adapters.get(platform)
        if not adapter:
            return {"success": False, "error": "unknown platform"}
        return adapter.handle_webhook(payload, headers)

    def get_adapter(self, platform: str):
        return self._adapters.get(platform)

    def public_config(self) -> Dict[str, Any]:
        cfg = load_config()
        plats = {}
        for name, plat in (cfg.get("platforms") or {}).items():
            if name not in self._adapters or not isinstance(plat, dict):
                continue
            masked = dict(plat)
            for secret_key in ("bot_token", "app_secret", "app_key", "access_token", "verification_token"):
                val = str(masked.get(secret_key) or "")
                if val:
                    masked[secret_key] = val[:4] + "…" if len(val) > 4 else "****"
            plats[name] = masked
        return {
            "enabled": bool(cfg.get("enabled")),
            "workdir": cfg.get("workdir") or "",
            "proxy": cfg.get("proxy") or "",
            "reply_timeout_sec": int(cfg.get("reply_timeout_sec") or 300),
            "mirror_to_terminal": bool(cfg.get("mirror_to_terminal", True)),
            "terminal_proxy_enabled": bool(cfg.get("terminal_proxy_enabled", True)),
            "default_terminal_id": str(cfg.get("default_terminal_id") or ""),
            "platforms": plats,
        }


im_manager = ImBridgeManager()
