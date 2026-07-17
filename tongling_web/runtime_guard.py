# -*- coding: utf-8 -*-
"""运行时安全检查（Linux root 等）。"""

from __future__ import annotations

import os
from typing import Any, Dict


def is_running_as_root() -> bool:
    """Linux/Unix 下是否以 root（euid=0）运行。Windows 恒为 False。"""
    if os.name == "nt":
        return False
    try:
        return int(os.geteuid()) == 0
    except (AttributeError, OSError, ValueError):
        return False


def root_terminal_block_message() -> str:
    user = ""
    try:
        import getpass

        user = (getpass.getuser() or "").strip()
    except Exception:
        user = ""
    who = f"（当前用户: {user}）" if user else ""
    return (
        f"检测到当前以 root 权限运行{who}。"
        "AI 可能执行危险操作，该终端无法使用 root 用户启动。"
        "请切换到普通用户后再打开终端。"
    )


def runtime_security_flags() -> Dict[str, Any]:
    root = is_running_as_root()
    return {
        "running_as_root": root,
        "root_terminal_blocked": root,
        "root_terminal_message": root_terminal_block_message() if root else "",
    }
