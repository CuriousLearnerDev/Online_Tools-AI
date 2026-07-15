"""Telegram Bot API — getUpdates 长轮询 + sendMessage。"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional

from tongling_web.im_bridge.adapters.base import ImAdapter
from tongling_web.im_bridge.claude_runner import run_claude_for_im
from tongling_web.im_bridge.config_store import load_config
from tongling_web.im_bridge.http_util import http_json, split_text_chunks

logger = logging.getLogger(__name__)

API_BASE = "https://api.telegram.org/bot{token}/{method}"


class TelegramAdapter(ImAdapter):
    name = "telegram"

    def __init__(self) -> None:
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._offset = 0
        self._last_error = ""
        self._processed = 0

    def _api(self, method: str, payload: Optional[dict] = None, token: str = "") -> Optional[dict]:
        if not token:
            return None
        url = API_BASE.format(token=token, method=method)
        _, data, err = http_json(url, method="POST" if payload else "GET", body=payload, timeout=35)
        if data is None:
            self._last_error = err[:200]
            return None
        if not data.get("ok"):
            self._last_error = str(data.get("description") or err)[:200]
        return data

    def _ensure_polling_mode(self, token: str) -> None:
        """长轮询前删除 Webhook，避免与 getUpdates 冲突（官方要求二选一）。"""
        self._api("deleteWebhook", {"drop_pending_updates": False}, token=token)

    def send_text(self, chat_id: str, text: str, token: str) -> bool:
        ok = True
        for chunk in split_text_chunks(text, 4096):
            _, data, _ = http_json(
                API_BASE.format(token=token, method="sendMessage"),
                method="POST",
                body={"chat_id": chat_id, "text": chunk},
                timeout=20,
            )
            if not data or not data.get("ok"):
                ok = False
        return ok

    def _send_typing(self, chat_id: str, token: str) -> None:
        http_json(
            API_BASE.format(token=token, method="sendChatAction"),
            method="POST",
            body={"chat_id": chat_id, "action": "typing"},
            timeout=10,
        )

    def _allowed(self, chat_id: str, allowed: List[Any]) -> bool:
        if not allowed:
            return True
        return str(chat_id) in {str(x) for x in allowed}

    def _poll_loop(self) -> None:
        webhook_cleared = False
        while not self._stop.is_set():
            cfg = load_config()
            plat = (cfg.get("platforms") or {}).get("telegram") or {}
            if not cfg.get("enabled") or not plat.get("enabled"):
                webhook_cleared = False
                time.sleep(2)
                continue
            token = str(plat.get("bot_token") or "").strip()
            if not token:
                self._last_error = "未配置 Bot Token"
                time.sleep(3)
                continue

            if not webhook_cleared:
                self._ensure_polling_mode(token)
                webhook_cleared = True

            res = self._api(
                "getUpdates",
                {"offset": self._offset, "timeout": 25, "allowed_updates": ["message"]},
                token=token,
            )
            if not res or not res.get("ok"):
                time.sleep(2)
                continue

            for upd in res.get("result") or []:
                self._offset = int(upd.get("update_id", 0)) + 1
                msg = upd.get("message") or {}
                chat = msg.get("chat") or {}
                chat_id = str(chat.get("id", ""))
                text = str(msg.get("text") or "").strip()
                if not text or not chat_id:
                    continue
                if not self._allowed(chat_id, plat.get("allowed_chat_ids") or []):
                    self.send_text(chat_id, "此 Chat 未在白名单中，请在统领「社交接入」配置 allowed_chat_ids。", token)
                    continue

                chat_key = f"telegram:{chat_id}"
                self._send_typing(chat_id, token)
                ok, reply = run_claude_for_im(
                    chat_key,
                    text,
                    workdir=str(cfg.get("workdir") or ""),
                    proxy=str(cfg.get("proxy") or ""),
                    timeout_sec=int(cfg.get("reply_timeout_sec") or 300),
                )
                if not self.send_text(chat_id, reply if ok else f"❌ {reply}", token):
                    logger.warning("telegram send failed chat=%s ok=%s", chat_id, ok)
                self._processed += 1

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._poll_loop, name="im-telegram", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def status(self) -> Dict[str, Any]:
        return {
            "running": bool(self._thread and self._thread.is_alive() and not self._stop.is_set()),
            "last_error": self._last_error,
            "processed": self._processed,
            "mode": "long_polling",
        }
