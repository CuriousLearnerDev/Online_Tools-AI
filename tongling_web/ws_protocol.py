"""Claude Web 终端 WebSocket 协议（独立端口 / Flask 同端口共用）。"""

from __future__ import annotations

from typing import Any, Callable, Dict

from tongling_web.pty_bridge import pty_available
from tongling_web.session_manager import terminal_manager

SendFn = Callable[[Dict[str, Any]], None]


def _sid(msg: Dict[str, Any]) -> str | None:
    raw = msg.get("session_id")
    return str(raw).strip() if raw else None


def handle_terminal_message(
    msg: Dict[str, Any],
    send: SendFn,
    listener_id_holder: list,
) -> None:
    mtype = msg.get("type")

    if mtype == "start":
        ok, detail, meta = terminal_manager.start(msg)
        if not ok or not meta:
            send({"type": "error", "message": detail})
            return
        sid = meta["session_id"]
        bind_session_listener(send, listener_id_holder, sid)
        send(
            {
                "type": "started",
                "session_id": sid,
                "title": meta.get("title"),
                "cmdline": meta.get("cmdline"),
                "cwd": meta.get("cwd"),
                "audit_id": meta.get("audit_id"),
                "claude_session_id": meta.get("claude_session_id") or "",
                "reattach": False,
                "sessions": terminal_manager.list_sessions(),
            }
        )
        return

    if mtype == "attach":
        sid = _sid(msg)
        cols = int(msg.get("cols") or 120)
        rows = int(msg.get("rows") or 40)
        ok, detail, meta = terminal_manager.attach(sid, cols, rows)
        if not ok or not meta:
            send({"type": "error", "message": detail})
            return
        sid = meta["session_id"]
        lid = listener_id_holder[0]
        if lid is not None:
            replay = terminal_manager.rebind_listener(lid, sid)
        else:
            lid, replay = terminal_manager.register_listener(sid)
            listener_id_holder[0] = lid
            terminal_manager.set_listener(lid, send, sid)
        if replay:
            send({"type": "replay", "session_id": sid, "data": replay})
        send(
            {
                "type": "attached",
                "session_id": sid,
                "title": meta.get("title"),
                "cmdline": meta.get("cmdline"),
                "cwd": meta.get("cwd"),
                "audit_id": meta.get("audit_id"),
                "claude_session_id": meta.get("claude_session_id") or "",
                "reattach": True,
                "sessions": terminal_manager.list_sessions(),
            }
        )
        return

    if mtype == "bind_claude":
        # 前端发现新建终端对应的 Claude UUID 后回写
        term_sid = _sid(msg)
        claude_sid = str(msg.get("claude_session_id") or "").strip()
        if term_sid and claude_sid and terminal_manager.set_claude_session_id(term_sid, claude_sid):
            send(
                {
                    "type": "claude_bound",
                    "session_id": term_sid,
                    "claude_session_id": claude_sid,
                    "sessions": terminal_manager.list_sessions(),
                }
            )
        else:
            send({"type": "error", "message": "无法绑定 Claude 会话"})
        return

    if mtype == "list":
        send({"type": "sessions", "sessions": terminal_manager.list_sessions()})
        return

    if mtype == "subscribe_all":
        # 同时订阅全部运行中终端，便于多窗口并行显示输出
        lid, items = terminal_manager.subscribe_all(listener_id_holder[0], send)
        listener_id_holder[0] = lid
        for sid, replay in items:
            if replay:
                send({"type": "replay", "session_id": sid, "data": replay})
        # 不推送 sessions，避免前端 render 循环；会话列表仍由 started/attached/ready 同步
        return

    if mtype == "input":
        terminal_manager.write(_sid(msg), str(msg.get("data") or ""))
        return

    if mtype == "resize":
        terminal_manager.resize(
            _sid(msg), int(msg.get("cols") or 120), int(msg.get("rows") or 40)
        )
        return

    if mtype == "stop":
        sid = _sid(msg)
        stopped, audit_id = terminal_manager.stop(sid)
        send(
            {
                "type": "stopped",
                "session_id": sid,
                "audit_id": audit_id,
                "sessions": terminal_manager.list_sessions(),
            }
        )
        if not stopped:
            send({"type": "error", "message": "没有可停止的会话"})


def send_ready(send: SendFn) -> None:
    st = terminal_manager.status()
    send(
        {
            "type": "ready",
            "pty": pty_available(),
            "session_active": st.get("active", False),
            "sessions": st.get("sessions") or [],
            "meta": st.get("meta") or {},
        }
    )


def bind_session_listener(send: SendFn, listener_id_holder: list, session_id: str) -> None:
    """复用同一 WS 的 listener，避免重复推送导致终端内容翻倍。"""
    lid = listener_id_holder[0]
    if lid is not None and terminal_manager.has_listener(lid):
        terminal_manager.touch_listener(lid, send)
        # 叠加订阅新会话，保留对其它终端的订阅（不二次回放）
        terminal_manager.rebind_listener(lid, session_id)
        return
    lid, _ = terminal_manager.register_listener(session_id)
    listener_id_holder[0] = lid
    terminal_manager.set_listener(lid, send, session_id)


def detach_listener(listener_id_holder: list) -> None:
    terminal_manager.unregister_listener(listener_id_holder[0] if listener_id_holder else None)
    if listener_id_holder:
        listener_id_holder[0] = None
