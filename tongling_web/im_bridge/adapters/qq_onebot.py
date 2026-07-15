"""QQ — OneBot 11 / NapCat 反向 HTTP 上报 + HTTP API 发消息。"""

from __future__ import annotations

import logging
import threading
from typing import Any, Dict, List, Optional

from tongling_web.im_bridge.adapters.base import ImAdapter
from tongling_web.im_bridge.claude_runner import run_claude_for_im
from tongling_web.im_bridge.config_store import load_config
from tongling_web.im_bridge.http_util import append_access_token, http_json, split_text_chunks

logger = logging.getLogger(__name__)


class QqOneBotAdapter(ImAdapter):
    name = "qq"

    def __init__(self) -> None:
        self._last_error = ""
        self._processed = 0

    def _auth_headers(self, token: str) -> Dict[str, str]:
        hdrs = {"Content-Type": "application/json"}
        if token:
            hdrs["Authorization"] = f"Bearer {token}"
        return hdrs

    def _onebot_post(self, api_base: str, action: str, body: Dict[str, Any], token: str) -> bool:
        base = (api_base or "").rstrip("/")
        url = append_access_token(f"{base}/{action}", token)
        _, data, err = http_json(url, method="POST", body=body, headers=self._auth_headers(token), timeout=15)
        if data is None:
            self._last_error = err[:200]
            return False
        if data.get("status") == "ok" or data.get("retcode") == 0:
            return True
        self._last_error = str(data.get("message") or data.get("wording") or data)[:200]
        return False

    def _send_private(self, user_id: str, text: str, api_base: str, token: str) -> bool:
        uid: Any = int(user_id) if str(user_id).isdigit() else user_id
        ok = True
        for chunk in split_text_chunks(text, 4000):
            if not self._onebot_post(
                api_base,
                "send_private_msg",
                {"user_id": uid, "message": chunk},
                token,
            ):
                ok = False
        return ok

    def _send_group(self, group_id: str, text: str, api_base: str, token: str) -> bool:
        gid: Any = int(group_id) if str(group_id).isdigit() else group_id
        ok = True
        for chunk in split_text_chunks(text, 4000):
            if not self._onebot_post(
                api_base,
                "send_group_msg",
                {"group_id": gid, "message": chunk},
                token,
            ):
                ok = False
        return ok

    def _extract_text(self, payload: Dict[str, Any]) -> str:
        raw = payload.get("raw_message")
        if raw is None:
            raw = payload.get("message") or ""
        if isinstance(raw, list):
            parts: List[str] = []
            for seg in raw:
                if isinstance(seg, dict) and seg.get("type") == "text":
                    parts.append(str(seg.get("data", {}).get("text", "")))
            return "".join(parts).strip()
        return str(raw).strip()

    def _handle_event(self, payload: Dict[str, Any]) -> None:
        cfg = load_config()
        plat = (cfg.get("platforms") or {}).get("qq") or {}
        if str(payload.get("post_type") or "") != "message":
            return

        msg_type = str(payload.get("message_type") or "")
        if msg_type not in ("private", "group"):
            return

        text = self._extract_text(payload)
        if not text or text.startswith("/"):
            return

        # 群聊需 @ 机器人才响应（NapCat 会在 raw_message 中带 @）
        if msg_type == "group":
            self_id = str(payload.get("self_id") or "")
            if self_id and f"[CQ:at,qq={self_id}]" not in text and "@" not in text:
                return
            text = text.replace(f"[CQ:at,qq={self_id}]", "").strip()

        user_id = str(payload.get("user_id") or payload.get("sender", {}).get("user_id") or "")
        group_id = str(payload.get("group_id") or "")
        chat_key = f"qq:{msg_type}:{group_id or user_id}"

        ok, reply = run_claude_for_im(
            chat_key,
            text,
            workdir=str(cfg.get("workdir") or ""),
            proxy=str(cfg.get("proxy") or ""),
            timeout_sec=int(cfg.get("reply_timeout_sec") or 300),
        )
        body = reply if ok else f"❌ {reply}"

        api_base = str(plat.get("onebot_http_url") or "http://127.0.0.1:3000")
        token = str(plat.get("access_token") or "")

        sent = False
        if msg_type == "private":
            sent = self._send_private(user_id, body, api_base, token)
        elif msg_type == "group" and group_id:
            sent = self._send_group(group_id, body, api_base, token)
        if sent:
            self._processed += 1

    def handle_webhook(self, payload: Dict[str, Any], headers: Dict[str, str]) -> Optional[Dict[str, Any]]:
        cfg = load_config()
        plat = (cfg.get("platforms") or {}).get("qq") or {}
        if not cfg.get("enabled") or not plat.get("enabled"):
            return {"status": "ignored"}

        expect = str(plat.get("access_token") or "")
        auth = headers.get("Authorization") or headers.get("authorization") or ""
        qtok = str(headers.get("_query_access_token") or "")
        if expect:
            bearer = auth.replace("Bearer ", "").strip()
            if bearer != expect and qtok != expect:
                return {"status": "forbidden"}

        threading.Thread(target=self._handle_event, args=(payload,), daemon=True).start()
        return {"status": "ok"}

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def status(self) -> Dict[str, Any]:
        return {
            "running": True,
            "last_error": self._last_error,
            "processed": self._processed,
            "mode": "onebot_http_post",
        }
