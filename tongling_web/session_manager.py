"""多 Claude 终端会话 — 可同时运行多个，刷新后可 attach 恢复。"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from tongling_web import audit_store
from tongling_web.launch_spec import prepare_claude_spec
from tongling_web.pty_bridge import PtySession, pty_available

MAX_SCROLLBACK_CHARS = 500_000
MAX_SESSIONS = 8

Listener = Callable[[Dict[str, Any]], None]


@dataclass
class ManagedSession:
    session_id: str
    pty: PtySession
    meta: Dict[str, Any]
    title: str
    scrollback: List[str] = field(default_factory=list)
    scrollback_len: int = 0


class TerminalSessionManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: Dict[str, ManagedSession] = {}
        # listener_id -> (callback, subscribed session ids)；可同时订阅多个终端
        self._listeners: Dict[int, Tuple[Listener, Set[str]]] = {}
        self._next_session_num = 1
        self._next_listener_id = 1
        self._audit_sync = None

    def set_audit_sync(self, callback: Optional[Callable[[], Tuple[str, Dict[str, str]]]]) -> None:
        """注册 HexStrike 同步参数 (server_url, auth_headers)。"""
        self._audit_sync = callback

    def _finalize_audit(self, audit_id: Optional[str], exit_code: Optional[int], status: str) -> None:
        if not audit_id:
            return
        server_url = ""
        headers: Dict[str, str] = {}
        if self._audit_sync:
            try:
                server_url, headers = self._audit_sync()
            except Exception:
                pass
        audit_store.finalize_task(
            audit_id,
            exit_code=exit_code,
            status=status,
            server_url=server_url,
            auth_headers=headers,
        )

    def _new_session_id(self) -> str:
        with self._lock:
            sid = f"t{self._next_session_num}"
            self._next_session_num += 1
            return sid

    def _append_scrollback(self, ms: ManagedSession, data: str) -> None:
        if not data:
            return
        ms.scrollback.append(data)
        ms.scrollback_len += len(data)
        while ms.scrollback_len > MAX_SCROLLBACK_CHARS and ms.scrollback:
            dropped = ms.scrollback.pop(0)
            ms.scrollback_len -= len(dropped)

    def _emit_session(self, session_id: str, payload: Dict[str, Any]) -> None:
        payload = {**payload, "session_id": session_id}
        with self._lock:
            bindings = [
                cb
                for _, (cb, sids) in self._listeners.items()
                if session_id in sids
            ]
        for cb in bindings:
            try:
                cb(payload)
            except Exception:
                pass

    def _drop_session_from_listeners(self, session_id: str) -> None:
        for lid, (cb, sids) in list(self._listeners.items()):
            if session_id in sids:
                next_sids = set(sids)
                next_sids.discard(session_id)
                self._listeners[lid] = (cb, next_sids)

    def _make_handlers(self, session_id: str):
        def on_output(data: str) -> None:
            audit_id = None
            with self._lock:
                ms = self._sessions.get(session_id)
                if not ms:
                    return
                audit_id = ms.meta.get("audit_id")
                self._append_scrollback(ms, data)
            if audit_id:
                audit_store.append_terminal(audit_id, data)
            self._emit_session(session_id, {"type": "output", "data": data})

        def on_exit(code: int, msg: str) -> None:
            audit_id = None
            with self._lock:
                ms = self._sessions.get(session_id)
                if ms:
                    audit_id = ms.meta.get("audit_id")
                self._sessions.pop(session_id, None)
            self._finalize_audit(audit_id, code, "completed")
            # 先推送给仍订阅该会话的客户端，再解除订阅
            self._emit_session(
                session_id,
                {"type": "exit", "code": code, "message": msg or "会话已结束", "audit_id": audit_id},
            )
            with self._lock:
                self._drop_session_from_listeners(session_id)

        return on_output, on_exit

    def list_sessions(self) -> List[Dict[str, Any]]:
        with self._lock:
            items = []
            for sid, ms in self._sessions.items():
                if ms.pty.running:
                    items.append(
                        {
                            "id": sid,
                            "title": ms.title,
                            "cwd": ms.meta.get("cwd"),
                            "started_at": ms.meta.get("started_at"),
                            "claude_session_id": ms.meta.get("claude_session_id") or "",
                            "audit_id": ms.meta.get("audit_id") or "",
                        }
                    )
            items.sort(key=lambda x: x.get("started_at") or 0)
            return items

    def status(self) -> Dict[str, Any]:
        from tongling_web.runtime_guard import runtime_security_flags

        sessions = self.list_sessions()
        return {
            "active": len(sessions) > 0,
            "pty_available": pty_available(),
            "sessions": sessions,
            "meta": sessions[-1] if sessions else {},
            **runtime_security_flags(),
        }

    def register_listener(self, session_id: str) -> Tuple[int, str]:
        with self._lock:
            lid = self._next_listener_id
            self._next_listener_id += 1
            ms = self._sessions.get(session_id)
            replay = "".join(ms.scrollback) if ms else ""
            return lid, replay

    def set_listener(self, listener_id: int, callback: Listener, session_id: str) -> None:
        with self._lock:
            sids: Set[str] = set()
            if session_id:
                sids.add(session_id)
            self._listeners[listener_id] = (callback, sids)

    def has_listener(self, listener_id: Optional[int]) -> bool:
        if listener_id is None:
            return False
        with self._lock:
            return listener_id in self._listeners

    def touch_listener(self, listener_id: int, callback: Listener) -> None:
        """更新 callback，保留已有订阅集合。"""
        with self._lock:
            if listener_id not in self._listeners:
                return
            _, sids = self._listeners[listener_id]
            self._listeners[listener_id] = (callback, set(sids))

    def rebind_listener(self, listener_id: int, session_id: str) -> str:
        """订阅 session（可叠加多个）；若已订阅则不再回放 scrollback。"""
        with self._lock:
            if listener_id not in self._listeners:
                return ""
            cb, sids = self._listeners[listener_id]
            sids = set(sids)
            already = bool(session_id) and session_id in sids
            if session_id:
                sids.add(session_id)
            self._listeners[listener_id] = (cb, sids)
            if already or not session_id:
                return ""
            ms = self._sessions.get(session_id)
            return "".join(ms.scrollback) if ms else ""

    def subscribe_all(
        self, listener_id: Optional[int], callback: Listener
    ) -> Tuple[int, List[Tuple[str, str]]]:
        """订阅当前全部运行中会话。返回 (listener_id, [(session_id, replay), ...])。"""
        out: List[Tuple[str, str]] = []
        with self._lock:
            if listener_id is None or listener_id not in self._listeners:
                lid = self._next_listener_id
                self._next_listener_id += 1
                self._listeners[lid] = (callback, set())
                listener_id = lid
            else:
                _, sids0 = self._listeners[listener_id]
                self._listeners[listener_id] = (callback, set(sids0))
            cb, sids = self._listeners[listener_id]
            sids = set(sids)
            for sid, ms in self._sessions.items():
                if not ms.pty.running:
                    continue
                already = sid in sids
                sids.add(sid)
                replay = "" if already else "".join(ms.scrollback)
                out.append((sid, replay))
            self._listeners[listener_id] = (cb, sids)
            return listener_id, out

    def unregister_listener(self, listener_id: Optional[int]) -> None:
        if listener_id is None:
            return
        with self._lock:
            self._listeners.pop(listener_id, None)

    def start(self, body: Dict[str, Any]) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        from tongling_web.launch_log import (
            append_launch_log,
            build_launch_log_lines,
            enrich_spec_with_cli_meta,
            launch_log_path,
        )
        from tongling_web.runtime_guard import is_running_as_root, root_terminal_block_message

        if is_running_as_root():
            detail = root_terminal_block_message()
            lines = build_launch_log_lines(stage="root_guard", ok=False, detail=detail, body=body)
            append_launch_log(lines)
            return False, detail, {
                "launch_log": lines,
                "launch_log_file": launch_log_path(),
                "running_as_root": True,
            }

        with self._lock:
            active = sum(1 for ms in self._sessions.values() if ms.pty.running)
            if active >= MAX_SESSIONS:
                detail = f"最多同时运行 {MAX_SESSIONS} 个终端"
                lines = build_launch_log_lines(stage="start", ok=False, detail=detail, body=body)
                append_launch_log(lines)
                return False, detail, {"launch_log": lines, "launch_log_file": launch_log_path()}

        ok, detail, spec = prepare_claude_spec(body)
        if not ok or not spec:
            # 准备失败时仍尽量解析 CLI，方便对照「选了哪个入口」
            try:
                from cc_visual.claude_launcher import resolve_claude_cli

                prefer_latest = bool(body.get("npx_latest"))
                rt = resolve_claude_cli(prefer_latest=prefer_latest)
                fallback_spec = {
                    "prefer_latest": prefer_latest,
                    "source": rt.get("source") or "",
                    "version_hint": rt.get("version_hint") or "",
                    "npx": rt.get("npx") or "",
                    "native_path": rt.get("native_path") or "",
                }
            except Exception:
                fallback_spec = spec
            lines = build_launch_log_lines(
                stage="prepare",
                ok=False,
                detail=detail or "无法准备启动",
                body=body,
                spec=fallback_spec,
            )
            append_launch_log(lines)
            return False, detail or "无法准备启动", {
                "launch_log": lines,
                "launch_log_file": launch_log_path(),
            }

        enrich_spec_with_cli_meta(spec)
        sid = self._new_session_id()
        on_output, on_exit = self._make_handlers(sid)
        session = PtySession(on_output=on_output, on_exit=on_exit)
        ok2, info = session.start(spec)
        if not ok2:
            lines = build_launch_log_lines(
                stage="pty",
                ok=False,
                detail=info,
                body=body,
                spec=spec,
                session_id=sid,
            )
            append_launch_log(lines)
            return False, info, {
                "launch_log": lines,
                "launch_log_file": launch_log_path(),
                "cmdline": spec.get("cmdline") or "",
            }

        title = f"终端 {sid[1:]}"
        workdir = spec.get("real_cwd") or spec.get("cwd") or ""
        scan_target = str(body.get("scan_target") or "").strip()
        report_path = str(body.get("report_path") or "").strip()
        scenario = str(body.get("scenario") or "").strip()
        extra: Dict[str, Any] = {}
        if scan_target:
            extra["target"] = scan_target
            title = f"扫描 {scan_target[:48]}"
        if report_path:
            extra["report_path"] = report_path
        if scenario:
            extra["scenario"] = scenario
        audit_id = audit_store.begin_task(
            terminal_session_id=sid,
            title=title,
            workdir=workdir,
            cmdline=info,
            extra=extra or None,
        )
        lines = build_launch_log_lines(
            stage="started",
            ok=True,
            detail=info,
            body=body,
            spec=spec,
            session_id=sid,
            extra={"cmdline": info},
        )
        log_file = append_launch_log(lines)
        meta = {
            "session_id": sid,
            "cmdline": info,
            "cwd": workdir,
            "started_at": time.time(),
            "title": title,
            "audit_id": audit_id,
            "launch_log": lines,
            "launch_log_file": log_file,
            "cli_source": spec.get("source") or "",
            "prefer_latest": bool(spec.get("prefer_latest")),
            "version_hint": spec.get("version_hint") or "",
        }
        resume_id = str(body.get("resume_id") or "").strip()
        if resume_id:
            meta["claude_session_id"] = resume_id
        with self._lock:
            self._sessions[sid] = ManagedSession(
                session_id=sid,
                pty=session,
                meta=meta,
                title=title,
            )
        return True, info, meta

    def set_claude_session_id(self, session_id: str, claude_session_id: str) -> bool:
        """把当前终端关联到 Claude 会话 UUID（扫描摘要 / 图谱用）。"""
        sid = (session_id or "").strip()
        cid = (claude_session_id or "").strip()
        if not sid or not cid:
            return False
        with self._lock:
            ms = self._sessions.get(sid)
            if not ms:
                return False
            ms.meta["claude_session_id"] = cid
            return True

    def _resolve_session_id(self, session_id: Optional[str]) -> Optional[str]:
        with self._lock:
            if session_id and session_id in self._sessions:
                ms = self._sessions[session_id]
                if ms.pty.running:
                    return session_id
            running = [sid for sid, ms in self._sessions.items() if ms.pty.running]
            if len(running) == 1:
                return running[0]
        return None

    def attach(
        self, session_id: Optional[str], cols: int, rows: int
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        sid = self._resolve_session_id(session_id)
        if not sid:
            return False, "没有可恢复的运行中会话，请先新建终端", None
        with self._lock:
            ms = self._sessions.get(sid)
            if not ms or not ms.pty.running:
                return False, "会话不存在或已结束", None
            meta = dict(ms.meta)
        ms.pty.resize(cols, rows)
        return True, "已恢复会话", meta

    def write(self, session_id: Optional[str], data: str) -> None:
        sid = self._resolve_session_id(session_id)
        if not sid:
            return
        with self._lock:
            ms = self._sessions.get(sid)
        if ms and ms.pty.running:
            ms.pty.write(data)

    def resize(self, session_id: Optional[str], cols: int, rows: int) -> None:
        sid = self._resolve_session_id(session_id)
        if not sid:
            return
        with self._lock:
            ms = self._sessions.get(sid)
        if ms and ms.pty.running:
            ms.pty.resize(cols, rows)

    def stop(self, session_id: Optional[str]) -> Tuple[bool, Optional[str]]:
        sid = self._resolve_session_id(session_id)
        if not sid:
            return False, None
        audit_id = None
        with self._lock:
            ms = self._sessions.pop(sid, None)
            if ms:
                audit_id = ms.meta.get("audit_id")
            self._drop_session_from_listeners(sid)
        if ms:
            ms.pty.close(notify=False)
            self._finalize_audit(audit_id, -1, "stopped")
            return True, audit_id
        return False, None

    def inject_log(
        self,
        text: str,
        *,
        session_id: Optional[str] = None,
        tag: str = "社交接入",
    ) -> bool:
        """向 Web 终端滚动区注入日志（不写入 PTY  stdin，仅展示）。"""
        sid = self._resolve_session_id(session_id)
        if not sid or not (text or "").strip():
            return False
        line = f"\r\n\x1b[36m[{tag}]\x1b[0m {(text or '').strip()}\r\n"
        with self._lock:
            ms = self._sessions.get(sid)
            if not ms or not ms.pty.running:
                return False
            audit_id = ms.meta.get("audit_id")
            self._append_scrollback(ms, line)
        if audit_id:
            audit_store.append_terminal(audit_id, line)
        self._emit_session(sid, {"type": "output", "data": line})
        return True

    def session_running(self, session_id: str) -> bool:
        with self._lock:
            ms = self._sessions.get(session_id)
            return bool(ms and ms.pty.running)

    def write_and_collect(
        self,
        session_id: str,
        text: str,
        *,
        timeout_sec: float = 120,
        idle_sec: float = 5.0,
    ) -> Tuple[bool, str]:
        """向指定 Web 终端 PTY 写入输入并收集 Claude 输出（社交遥控）。"""
        sid = (session_id or "").strip()
        payload = (text or "").strip()
        if not sid or not payload:
            return False, "消息为空"

        with self._lock:
            ms = self._sessions.get(sid)
            if not ms or not ms.pty.running:
                running = [x for x, m in self._sessions.items() if m.pty.running]
                hint = f"可用: {', '.join(running)}" if running else "请先在 AI 智能体新建终端"
                return False, f"终端 {sid} 未运行。{hint}"
            start_text = "".join(ms.scrollback)
            pty = ms.pty

        time.sleep(0.15)
        if not pty.send_input(payload):
            return False, "无法写入终端 PTY，请确认终端未卡住并重试"

        deadline = time.time() + max(15.0, float(timeout_sec))
        last_len = len(start_text)
        last_change = time.time()
        saw_pty_output = False
        from tongling_web.im_bridge.terminal_proxy import extract_claude_reply, strip_ansi

        while time.time() < deadline:
            time.sleep(0.35)
            with self._lock:
                ms = self._sessions.get(sid)
                if not ms or not ms.pty.running:
                    return False, f"终端 {sid} 已断开"
                cur = "".join(ms.scrollback)
            if len(cur) > last_len:
                saw_pty_output = True
                last_len = len(cur)
                last_change = time.time()
            elif saw_pty_output:
                delta_so_far = cur[len(start_text) :] if len(cur) > len(start_text) else ""
                reply_so_far = extract_claude_reply(delta_so_far)
                idle_need = 4.0 if reply_so_far else idle_sec
                if time.time() - last_change >= idle_need:
                    break

        with self._lock:
            ms = self._sessions.get(sid)
            cur = "".join(ms.scrollback) if ms else start_text

        delta = cur[len(start_text) :] if len(cur) > len(start_text) else ""
        reply = extract_claude_reply(delta)
        if not reply:
            cleaned = strip_ansi(delta).strip()
            lines = [ln.strip() for ln in cleaned.splitlines() if ln.strip() and not ln.strip().startswith("⎿")]
            reply = "\n".join(lines[-6:]).strip() if lines else ""

        if reply:
            if len(reply) > 12000:
                reply = reply[:11800] + "\n…（回复已截断）"
            return True, reply

        return True, "（Claude 正在处理，请在 Web 终端查看完整输出）"


terminal_manager = TerminalSessionManager()
