"""Claude Code Web 终端 WebSocket 服务。"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
from typing import Optional

import websockets
from websockets.server import WebSocketServerProtocol

from tongling_web.auth import extract_token_from_ws, parse_ws_path, verify_token
from tongling_web.ws_output import is_inplace_tty_update
from tongling_web.ws_protocol import (
    detach_listener,
    handle_terminal_message,
    send_ready,
)

logger = logging.getLogger(__name__)

_ws_thread: Optional[threading.Thread] = None
_ws_port: Optional[int] = None


def ws_port_for_api(api_port: int) -> int:
    return int(os.environ.get("TONGLING_WS_PORT", api_port + 100))


def _bind_host() -> str:
    return os.environ.get("TONGLING_WS_HOST") or os.environ.get("HEXSTRIKE_HOST", "0.0.0.0")


def get_ws_url(api_port: int, client_host: str | None = None) -> str:
    host = (client_host or "127.0.0.1").split(":")[0]
    return f"ws://{host}:{ws_port_for_api(api_port)}/claude"


def _ws_path(ws: WebSocketServerProtocol) -> str:
    req = getattr(ws, "request", None)
    if req is not None:
        return getattr(req, "path", "") or ""
    return getattr(ws, "path", "") or ""


async def _ws_handler(ws: WebSocketServerProtocol) -> None:
    raw_path = _ws_path(ws)
    path, _ = parse_ws_path(raw_path)
    if path not in ("/claude", "/claude/"):
        await ws.close(1008, "use /claude")
        return

    if not verify_token(extract_token_from_ws(ws)):
        await ws.close(1008, "unauthorized")
        return

    loop = asyncio.get_running_loop()
    listener_id_holder: list = [None]
    out_queue: asyncio.Queue = asyncio.Queue()
    pending_out: list = []
    flush_handle: list = [None]

    async def pump_output() -> None:
        while True:
            payload = await out_queue.get()
            if payload is None:
                break
            try:
                await ws.send(json.dumps(payload, ensure_ascii=False))
            except Exception:
                break

    def _flush_pending() -> None:
        flush_handle[0] = None
        if pending_out:
            out_queue.put_nowait({"type": "output", "data": "".join(pending_out)})
            pending_out.clear()

    def send(payload: dict) -> None:
        if payload.get("type") != "output":
            if pending_out:
                loop.call_soon_threadsafe(_flush_pending)
            loop.call_soon_threadsafe(out_queue.put_nowait, payload)
            return
        data = payload.get("data") or ""
        if not data:
            return
        if is_inplace_tty_update(data):
            if flush_handle[0] is not None:
                flush_handle[0].cancel()
                flush_handle[0] = None
            if pending_out:
                loop.call_soon_threadsafe(_flush_pending)
            loop.call_soon_threadsafe(out_queue.put_nowait, payload)
            return
        pending_out.append(data)
        if flush_handle[0] is None:
            flush_handle[0] = loop.call_later(0.016, _flush_pending)

    pump_task = asyncio.create_task(pump_output())
    send_ready(send)

    try:
        async for raw in ws:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8", errors="replace")
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                from tongling_web.session_manager import terminal_manager

                terminal_manager.write(None, raw)
                continue

            handle_terminal_message(msg, send, listener_id_holder)
    except websockets.ConnectionClosed:
        pass
    finally:
        if flush_handle[0] is not None:
            flush_handle[0].cancel()
        if pending_out:
            try:
                await ws.send(json.dumps({"type": "output", "data": "".join(pending_out)}, ensure_ascii=False))
            except Exception:
                pass
        detach_listener(listener_id_holder)
        await out_queue.put(None)
        pump_task.cancel()


async def _run_server(host: str, port: int) -> None:
    async with websockets.serve(
        _ws_handler,
        host,
        port,
        max_size=4 * 1024 * 1024,
        ping_interval=30,
        ping_timeout=120,
    ):
        logger.info("Tongling Claude WebSocket terminal on ws://%s:%s/claude", host, port)
        await asyncio.Future()


def start_ws_server(api_port: int, host: str | None = None) -> int:
    global _ws_thread, _ws_port
    bind = host or _bind_host()
    port = ws_port_for_api(api_port)
    if _ws_thread and _ws_thread.is_alive() and _ws_port == port:
        return port

    def _thread_main():
        try:
            asyncio.run(_run_server(bind, port))
        except Exception:
            logger.exception(
                "Claude WebSocket 独立服务异常退出 (ws://%s:%s/claude)", bind, port
            )

    _ws_port = port
    _ws_thread = threading.Thread(target=_thread_main, name="tongling-ws-terminal", daemon=True)
    _ws_thread.start()
    logger.info(
        "Claude WebSocket 独立服务启动中: ws://%s:%s/claude (API 端口 %s)",
        bind,
        port,
        api_port,
    )
    return port
