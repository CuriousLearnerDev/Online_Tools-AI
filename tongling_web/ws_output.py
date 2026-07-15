"""WebSocket 终端输出辅助 — 识别 TUI 原地刷新（计时/进度条等）。"""

from __future__ import annotations


def is_inplace_tty_update(data: str) -> bool:
    """含回车/退格/ANSI 光标控制的输出需立即发送，不能批处理。"""
    if not data:
        return False
    return "\r" in data or "\x08" in data or "\x1b[" in data or "\x1b]" in data
