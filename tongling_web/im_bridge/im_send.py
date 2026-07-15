"""各 IM 平台统一发消息封装。"""

from __future__ import annotations

from typing import Tuple

from tongling_web.im_bridge.http_util import http_json, split_text_chunks
from tongling_web.im_bridge.terminal_proxy import format_for_im


def send_webhook_message(url: str, text: str, *, timeout: float = 15) -> Tuple[bool, str]:
    """向钉钉 Webhook 发送纯文本（分段）。"""
    webhook = (url or "").strip()
    content = format_for_im(text)
    if not webhook or not content:
        return False, "empty url or content"

    ok = True
    last_err = ""
    for chunk in split_text_chunks(content, 4000):
        _, data, err = http_json(
            webhook,
            method="POST",
            body={"msgtype": "text", "text": {"content": chunk}},
            timeout=timeout,
        )
        if data is None or int(data.get("errcode", -1)) != 0:
            ok = False
            last_err = str((data or {}).get("errmsg") or err)[:200]
    return ok, last_err
