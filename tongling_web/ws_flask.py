"""Claude Web 终端 — 与 Flask 同端口 WebSocket。"""

from __future__ import annotations

import json
import logging
import threading
from queue import Empty, Queue
from typing import Optional

from flask import Blueprint, request

from tongling_web.auth import find_valid_token_from_request, verify_token
from tongling_web.deps import ensure_simple_websocket
from tongling_web.ws_output import is_inplace_tty_update
from tongling_web.ws_protocol import (
    detach_listener,
    handle_terminal_message,
    send_ready,
)

logger = logging.getLogger(__name__)

WS_PATH = "/tongling/ws/claude"

_HAS_FLASK_WS: Optional[bool] = None
WsServer = None  # type: ignore
ConnectionClosed = Exception  # type: ignore


def _load_flask_ws() -> bool:
    global _HAS_FLASK_WS, WsServer, ConnectionClosed
    if _HAS_FLASK_WS is not None:
        return _HAS_FLASK_WS

    ensure_simple_websocket()
    try:
        from simple_websocket import ConnectionClosed as _CC
        from simple_websocket import Server as _WS

        WsServer = _WS
        ConnectionClosed = _CC
        _HAS_FLASK_WS = True
    except ImportError:
        _HAS_FLASK_WS = False

    return _HAS_FLASK_WS


def same_port_ws_available() -> bool:
    return _load_flask_ws()


def _run_claude_ws(ws) -> None:
    if not find_valid_token_from_request(request):
        ws.send('{"type":"error","message":"未授权，Token 无效"}')
        ws.close()
        return

    listener_id_holder: list = [None]
    out_q: Queue = Queue()
    pending_out: list = []
    flush_timer: list = [None]

    def send(payload: dict) -> None:
        if payload.get("type") != "output":
            if pending_out:
                out_q.put({"type": "output", "data": "".join(pending_out)})
                pending_out.clear()
                if flush_timer[0]:
                    flush_timer[0].cancel()
                    flush_timer[0] = None
            out_q.put(payload)
            return
        data = payload.get("data") or ""
        if not data:
            return
        if is_inplace_tty_update(data):
            if flush_timer[0]:
                flush_timer[0].cancel()
                flush_timer[0] = None
            if pending_out:
                out_q.put({"type": "output", "data": "".join(pending_out)})
                pending_out.clear()
            out_q.put(payload)
            return
        pending_out.append(data)
        if flush_timer[0] is None:
            def _flush() -> None:
                flush_timer[0] = None
                if pending_out:
                    out_q.put({"type": "output", "data": "".join(pending_out)})
                    pending_out.clear()

            flush_timer[0] = threading.Timer(0.016, _flush)
            flush_timer[0].daemon = True
            flush_timer[0].start()

    send_ready(send)

    while True:
        while True:
            try:
                item = out_q.get_nowait()
            except Empty:
                break
            try:
                ws.send(json.dumps(item, ensure_ascii=False))
            except Exception:
                if flush_timer[0]:
                    flush_timer[0].cancel()
                detach_listener(listener_id_holder)
                return

        try:
            raw = ws.receive(timeout=0.05)
        except ConnectionClosed:
            break
        if raw is None:
            continue

        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")

        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            from tongling_web.session_manager import terminal_manager

            terminal_manager.write(None, raw)
            continue

        handle_terminal_message(msg, send, listener_id_holder)

    if flush_timer[0]:
        flush_timer[0].cancel()
    if pending_out:
        try:
            ws.send(json.dumps({"type": "output", "data": "".join(pending_out)}, ensure_ascii=False))
        except Exception:
            pass
    detach_listener(listener_id_holder)


def register_ws_route(bp: Blueprint) -> bool:
    if not _load_flask_ws():
        logger.warning(
            "simple-websocket 不可用，Claude 终端将使用独立端口 (API+100)。"
            "可手动安装: python -m pip install simple-websocket"
        )
        return False

    @bp.route(WS_PATH, websocket=True)
    def claude_ws_endpoint():
        ws = WsServer.accept(request.environ)
        try:
            _run_claude_ws(ws)
        except ConnectionClosed:
            pass
        except Exception:
            logger.exception("Claude WebSocket handler error")
        finally:
            try:
                ws.close()
            except Exception:
                pass
        return ""

    logger.info("Claude Web 终端同端口 WebSocket 已注册: %s", WS_PATH)
    return True
