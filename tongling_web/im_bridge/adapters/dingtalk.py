"""钉钉 — Stream 收消息 + sessionWebhook 回复（官方推荐）。"""

from __future__ import annotations

import concurrent.futures
import functools
import logging
import threading
from typing import Any, Dict, Optional

from tongling_web.im_bridge.adapters.base import ImAdapter
from tongling_web.im_bridge.claude_runner import run_im_message
from tongling_web.im_bridge.config_store import load_config
from tongling_web.im_bridge.im_send import send_webhook_message
from tongling_web.im_bridge.terminal_proxy import format_for_im

logger = logging.getLogger(__name__)

_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="im-dingtalk")


class DingTalkAdapter(ImAdapter):
    name = "dingtalk"

    def __init__(self) -> None:
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._client = None
        self._last_error = ""
        self._processed = 0

    def _reply_session_webhook(self, session_webhook: str, text: str) -> bool:
        ok, err = send_webhook_message(session_webhook, text)
        if not ok:
            self._last_error = err[:200]
        return ok

    def _reply_fallback_webhook(self, text: str, webhook_url: str) -> bool:
        ok, err = send_webhook_message(webhook_url, text)
        if not ok:
            self._last_error = err[:200]
        return ok

    def _on_message(self, text: str, sender_id: str, session_webhook: str = "") -> None:
        cfg = load_config()
        plat = (cfg.get("platforms") or {}).get("dingtalk") or {}
        chat_key = f"dingtalk:{sender_id or 'unknown'}"
        ok, reply = run_im_message(
            chat_key,
            text,
            workdir=str(cfg.get("workdir") or ""),
            proxy=str(cfg.get("proxy") or ""),
            timeout_sec=int(cfg.get("reply_timeout_sec") or 300),
        )
        body = format_for_im(reply if ok else f"❌ {reply}")
        sent = False
        if body and session_webhook:
            sent = self._reply_session_webhook(session_webhook, body)
        if not sent:
            sent = self._reply_fallback_webhook(body, str(plat.get("webhook_url") or ""))
        if sent:
            self._processed += 1

    def _load_stream_modules(self):
        try:
            import dingtalk_stream
            from dingtalk_stream import AckMessage, ChatbotHandler, ChatbotMessage, Credential, DingTalkStreamClient

            return dingtalk_stream, AckMessage, ChatbotHandler, ChatbotMessage, Credential, DingTalkStreamClient
        except ImportError:
            from tongling_web.deps import ensure_dingtalk_stream

            if ensure_dingtalk_stream():
                import dingtalk_stream
                from dingtalk_stream import AckMessage, ChatbotHandler, ChatbotMessage, Credential, DingTalkStreamClient

                return dingtalk_stream, AckMessage, ChatbotHandler, ChatbotMessage, Credential, DingTalkStreamClient
        return None

    def _stream_loop(self) -> None:
        outer = self
        mods = None
        while not self._stop.is_set() and mods is None:
            mods = self._load_stream_modules()
            if mods:
                break
            self._last_error = "dingtalk-stream 未安装，正在尝试自动安装…"
            self._stop.wait(10)

        if not mods or self._stop.is_set():
            return

        dingtalk_stream, AckMessage, ChatbotHandler, ChatbotMessage, Credential, DingTalkStreamClient = mods
        self._last_error = ""

        class Handler(ChatbotHandler):
            async def process(self, callback: dingtalk_stream.CallbackMessage):
                incoming = ChatbotMessage.from_dict(callback.data)
                text = (incoming.text.content or "").strip() if incoming.text else ""
                if not text:
                    return AckMessage.STATUS_OK, "OK"

                cfg = load_config()
                sender = str(
                    getattr(incoming, "sender_staff_id", "")
                    or getattr(incoming, "sender_id", "")
                    or "unknown"
                )
                chat_key = f"dingtalk:{sender}"
                loop = __import__("asyncio").get_event_loop()
                fn = functools.partial(
                    run_im_message,
                    chat_key,
                    text,
                    workdir=str(cfg.get("workdir") or ""),
                    proxy=str(cfg.get("proxy") or ""),
                    timeout_sec=int(cfg.get("reply_timeout_sec") or 300),
                )
                ok, reply = await loop.run_in_executor(_executor, fn)
                body = format_for_im(reply if ok else f"❌ {reply}")
                if body:
                    self.reply_text(body, incoming)
                outer._processed += 1
                return AckMessage.STATUS_OK, "OK"

        while not self._stop.is_set():
            cfg = load_config()
            plat = (cfg.get("platforms") or {}).get("dingtalk") or {}
            if not cfg.get("enabled") or not plat.get("enabled"):
                self._stop.wait(2)
                continue
            app_key = str(plat.get("app_key") or plat.get("client_id") or "").strip()
            app_secret = str(plat.get("app_secret") or plat.get("client_secret") or "").strip()
            if not app_key or not app_secret:
                self._last_error = "未配置 AppKey / AppSecret"
                self._stop.wait(3)
                continue
            try:
                cred = Credential(app_key, app_secret)
                client = DingTalkStreamClient(cred)
                client.register_callback_handler(ChatbotMessage.TOPIC, Handler())
                self._client = client
                client.start_forever()
            except Exception as exc:
                self._last_error = str(exc)[:200]
                logger.exception("dingtalk stream error")
                self._stop.wait(5)

    def handle_webhook(self, payload: Dict[str, Any], headers: Dict[str, str]) -> Optional[Dict[str, Any]]:
        """HTTP 模式回调 — 解析钉钉官方 JSON（含 sessionWebhook）。"""
        cfg = load_config()
        plat = (cfg.get("platforms") or {}).get("dingtalk") or {}
        if not cfg.get("enabled") or not plat.get("enabled"):
            return {"success": False, "error": "bridge disabled"}

        msgtype = str(payload.get("msgtype") or "")
        text = ""
        if msgtype == "text":
            text = str((payload.get("text") or {}).get("content") or "").strip()
        else:
            text = str(payload.get("content") or payload.get("text") or "").strip()

        if not text:
            return {"success": False, "error": "empty text"}

        sender = str(payload.get("senderStaffId") or payload.get("senderId") or "webhook")
        session_webhook = str(payload.get("sessionWebhook") or "")
        threading.Thread(
            target=self._on_message,
            args=(text, sender, session_webhook),
            daemon=True,
        ).start()
        return {"success": True}

    def start(self) -> None:
        cfg = load_config()
        plat = (cfg.get("platforms") or {}).get("dingtalk") or {}
        if not plat.get("app_key") and not plat.get("client_id"):
            return
        if plat.get("enabled") or cfg.get("enabled"):
            from tongling_web.deps import ensure_dingtalk_stream

            ensure_dingtalk_stream()
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._stream_loop, name="im-dingtalk", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._client = None

    def status(self) -> Dict[str, Any]:
        plat = (load_config().get("platforms") or {}).get("dingtalk") or {}
        mode = "stream" if (plat.get("app_key") or plat.get("client_id")) else "http_webhook"
        return {
            "running": bool(self._thread and self._thread.is_alive()) if mode == "stream" else True,
            "last_error": self._last_error,
            "processed": self._processed,
            "mode": mode,
        }
