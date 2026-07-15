"""将 IM 消息转发为 Claude Code 非交互调用（-p / -c）或遥控 Web 终端。"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from typing import Tuple

from tongling_web.im_bridge.config_store import get_chat_session, load_config, set_chat_session
from tongling_web.im_bridge.terminal_proxy import (
    format_terminal_list,
    parse_terminal_directive,
)

logger = logging.getLogger(__name__)

MAX_REPLY_CHARS = 3500

_PLATFORM_TAG = {
    "telegram": "Telegram",
    "dingtalk": "钉钉",
    "qq": "QQ",
}


def _normalize_terminal_id(raw: str) -> str:
    tid = str(raw or "").strip()
    if tid.isdigit():
        return f"t{tid}"
    return tid


def _resolve_terminal_id(chat_key: str, session: dict, explicit: str = "") -> str:
    cfg = load_config()
    tid = _normalize_terminal_id(explicit or str(session.get("terminal_id") or ""))
    if not tid:
        tid = _normalize_terminal_id(str(cfg.get("default_terminal_id") or ""))
    return tid


def _mirror_to_terminal(chat_key: str, role: str, text: str, *, session_id: str = "") -> None:
    cfg = load_config()
    if not cfg.get("mirror_to_terminal", True):
        return
    platform = str(chat_key or "").split(":", 1)[0]
    tag = _PLATFORM_TAG.get(platform, "社交接入")
    body = f"{role}: {text}"
    sid = _normalize_terminal_id(session_id) or _resolve_terminal_id(chat_key, get_chat_session(chat_key))
    try:
        from tongling_web.session_manager import terminal_manager

        terminal_manager.inject_log(body, tag=tag, session_id=sid or None)
    except Exception:
        logger.debug("mirror im log to terminal failed", exc_info=True)


def _ensure_import_path() -> None:
    root = os.environ.get("TONGLING_ROOT") or os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    if root not in sys.path:
        sys.path.insert(0, root)


def _default_workdir() -> str:
    root = os.environ.get("TONGLING_ROOT") or os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    cand = os.path.normpath(os.path.join(root, "storage", "node_ai", "claude-code"))
    if os.path.isdir(cand):
        return cand
    return os.path.normpath(root)


def _run_terminal_proxy(
    chat_key: str,
    terminal_id: str,
    body: str,
    *,
    timeout_sec: int = 300,
) -> Tuple[bool, str]:
    from tongling_web.session_manager import terminal_manager

    tid = _normalize_terminal_id(terminal_id)
    if not terminal_manager.session_running(tid):
        sessions = terminal_manager.list_sessions()
        if len(sessions) == 1:
            tid = str(sessions[0].get("id") or tid)
            set_chat_session(
                chat_key,
                {**get_chat_session(chat_key), "terminal_id": tid, "mode": "terminal_proxy"},
            )
        elif not sessions:
            return False, (
                "当前没有运行中的 AI 终端。请先在 Web「AI 智能体」新建终端，"
                "再发：\nID：1\n你好\n或发送「终端列表」查看 ID"
            )
        else:
            ids = ", ".join(
                f"ID：{(s.get('id') or '')[1:] if str(s.get('id', '')).startswith('t') else s.get('id')}"
                for s in sessions
            )
            return False, f"终端 {terminal_id} 未运行。当前可用：{ids}。请重新发送 ID：N 绑定。"

    _mirror_to_terminal(chat_key, "用户", body, session_id=tid)

    ok, reply = terminal_manager.write_and_collect(
        tid,
        body,
        timeout_sec=float(timeout_sec or 300),
    )
    if ok:
        set_chat_session(
            chat_key,
            {"terminal_id": tid, "mode": "terminal_proxy", "started": True, "last_ok": True},
        )
    return ok, reply


def run_im_message(
    chat_key: str,
    user_text: str,
    *,
    workdir: str = "",
    proxy: str = "",
    timeout_sec: int = 300,
) -> Tuple[bool, str]:
    """处理 IM 消息：支持 ID：N 遥控 Web 终端，否则走后台 claude -p/-c。"""
    cfg = load_config()
    session = get_chat_session(chat_key)
    terminal_id, body, bind_only = parse_terminal_directive(user_text)

    if terminal_id == "__list__":
        from tongling_web.session_manager import terminal_manager

        return True, format_terminal_list(terminal_manager.list_sessions())

    if terminal_id:
        set_chat_session(
            chat_key,
            {**session, "terminal_id": terminal_id, "mode": "terminal_proxy"},
        )
        if bind_only:
            num = terminal_id[1:] if terminal_id.startswith("t") else terminal_id
            from tongling_web.session_manager import terminal_manager

            if not terminal_manager.session_running(terminal_id):
                extra = format_terminal_list(terminal_manager.list_sessions())
                return False, (
                    f"已记录绑定终端 {num}（{terminal_id}），但该终端当前未运行。\n"
                    "请先在 Web「AI 智能体」新建/打开终端，再发消息。\n\n" + extra
                )
            return True, f"已绑定 AI 终端 {num}（{terminal_id}）。后续可直接发消息，无需重复 ID。"

    use_terminal = cfg.get("terminal_proxy_enabled", True)
    bound_tid = _resolve_terminal_id(chat_key, session, terminal_id or "")

    if use_terminal and bound_tid and body:
        return _run_terminal_proxy(chat_key, bound_tid, body, timeout_sec=timeout_sec)

    if not body:
        return False, "消息为空。遥控终端请发：\nID：1\n你好\n或先发 ID：1 绑定后再发消息。"

    return _run_claude_headless(chat_key, body, workdir=workdir, proxy=proxy, timeout_sec=timeout_sec)


def run_claude_for_im(
    chat_key: str,
    user_text: str,
    *,
    workdir: str = "",
    proxy: str = "",
    timeout_sec: int = 300,
) -> Tuple[bool, str]:
    """兼容旧调用名。"""
    return run_im_message(
        chat_key,
        user_text,
        workdir=workdir,
        proxy=proxy,
        timeout_sec=timeout_sec,
    )


def _run_claude_headless(
    chat_key: str,
    user_text: str,
    *,
    workdir: str = "",
    proxy: str = "",
    timeout_sec: int = 300,
) -> Tuple[bool, str]:
    """后台 claude -p / -c（与 Web 终端独立）。"""
    text = (user_text or "").strip()
    if not text:
        return False, "消息为空"

    _mirror_to_terminal(chat_key, "用户", text)

    _ensure_import_path()
    from cc_visual.claude_launcher import prepare_launch
    from cc_visual.claude_options import LaunchOptions

    wd = os.path.normpath(workdir or _default_workdir())
    if not os.path.isdir(wd):
        return False, f"Claude 工作目录不存在: {wd}"

    session = get_chat_session(chat_key)
    use_continue = bool(session.get("started")) and session.get("mode") != "terminal_proxy"
    opts = LaunchOptions(mode="continue" if use_continue else "print", skip_permissions=True)

    ok, msg, spec = prepare_launch(
        proxy=proxy or "",
        work_dir=wd,
        initial_prompt=text,
        ascii_cwd=False,
        options=opts,
    )
    if not ok or not spec:
        return False, msg or "无法准备 Claude 启动参数"

    argv = spec.get("argv") or []
    cwd = spec.get("cwd") or wd
    env = spec.get("env") or os.environ.copy()

    try:
        proc = subprocess.run(
            argv,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=max(30, int(timeout_sec or 300)),
        )
    except subprocess.TimeoutExpired:
        return False, f"Claude 响应超时（>{timeout_sec}s），请缩短问题或调大超时"
    except Exception as exc:
        logger.exception("claude im invoke failed")
        return False, str(exc)[:500]

    output = (proc.stdout or proc.stderr or "").strip()
    if not output:
        output = f"Claude 已结束（退出码 {proc.returncode}），无文本输出。"

    if proc.returncode == 0:
        set_chat_session(chat_key, {"started": True, "last_ok": True, "mode": "headless"})

    if len(output) > MAX_REPLY_CHARS:
        output = output[: MAX_REPLY_CHARS - 20] + "\n\n…（回复已截断）"

    label = "Claude" if proc.returncode == 0 else "Claude 错误"
    _mirror_to_terminal(chat_key, label, output)
    return proc.returncode == 0, output
