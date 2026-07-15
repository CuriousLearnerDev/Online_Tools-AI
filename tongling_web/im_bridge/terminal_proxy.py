"""解析社交消息中的终端 ID，并转发到 Web PTY 终端。"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
_OSC_RE = re.compile(r"\x1b\].*?(?:\x07|\\)")
_CSI_RE = re.compile(r"\x1b\([A-Z0-9]")
_ID_LINE = re.compile(r"^(?:ID|id|终端)\s*[:：]?\s*(\d+)\s*$")
_ID_INLINE = re.compile(r"^(?:ID|id|终端)\s*[:：]?\s*(\d+)\s+([\s\S]+)$", re.DOTALL)
_BULLET_RE = re.compile(r"^[●◆•]\s*(.+)$")
_TOOL_BULLET_RE = re.compile(
    r"^[●◆•]\s*(Bash|Read|Write|Edit|Grep|Glob|Task|WebFetch|Skill|TodoWrite|Agent)\s*[\(:]",
    re.I,
)
_STATUS_RE = re.compile(r"^(✻|✶|✽|✢).*(worked|thinking|hatching|brewed|swirling)", re.I)


def strip_ansi(text: str) -> str:
    s = _ANSI_RE.sub("", text or "")
    s = _OSC_RE.sub("", s)
    s = _CSI_RE.sub("", s)
    return s


def _is_table_line(s: str) -> bool:
    return any(c in s for c in "┌┐└┘├┤│┃┼═")


def _is_noise_line(line: str) -> bool:
    s = (line or "").strip()
    if not s:
        return True
    if _is_table_line(s):
        return False
    if _STATUS_RE.match(s):
        return True
    if s.count("─") >= 12 and "│" not in s:
        return True
    if s.startswith("❯") or s.startswith("⎿"):
        return True
    low = s.lower()
    noise_keys = (
        "bypass permissions",
        "esc to interrupt",
        "shift+tab",
        "for agents",
        "ctrl+o to expand",
        "claude code",
        "thought for ",
        "thinking for ",
        "the user just said",
        "shell cwd was reset",
        "↓",
        "tokens",
    )
    if any(k in low for k in noise_keys):
        return True
    return False


def _is_answer_bullet(line: str) -> bool:
    s = (line or "").strip()
    if not _BULLET_RE.match(s):
        return False
    if _TOOL_BULLET_RE.match(s):
        return False
    return True


def extract_claude_reply(raw: str) -> str:
    """从 Claude Code TUI 输出提取最终助手回复（跳过高具调用行）。"""
    text = strip_ansi(raw)
    lines = text.splitlines()

    last_answer = -1
    for i, line in enumerate(lines):
        if _is_answer_bullet(line):
            last_answer = i

    if last_answer < 0:
        kept: List[str] = []
        for line in lines:
            s = line.rstrip()
            stripped = s.strip()
            if not stripped or _is_noise_line(stripped):
                continue
            kept.append(stripped)
        return "\n".join(kept[-8:]).strip() if kept else ""

    kept: List[str] = []
    for line in lines[last_answer:]:
        s = line.rstrip()
        stripped = s.strip()
        if not stripped:
            if kept:
                kept.append("")
            continue
        if _is_noise_line(stripped):
            if kept and stripped.count("─") >= 12:
                break
            continue
        if _TOOL_BULLET_RE.match(stripped):
            continue
        m = _BULLET_RE.match(stripped)
        if m:
            body = m.group(1).strip()
            kept.append(body if body else stripped)
        else:
            kept.append(s)

    while kept and kept[-1] == "":
        kept.pop()
    return "\n".join(kept).strip()


def format_for_im(text: str) -> str:
    """纯文本回复（钉钉 Stream reply_text 最稳定）。"""
    body = (text or "").strip()
    if not body:
        return ""
    if len(body) > 12000:
        body = body[:11800] + "\n…（已截断）"
    return body


def parse_terminal_directive(text: str) -> Tuple[Optional[str], str, bool]:
    """解析 ID：N 指令。返回 (terminal_id, body, is_bind_only)。"""
    raw = (text or "").strip()
    if not raw:
        return None, "", False

    upper = raw.upper()
    if upper in ("ID:LIST", "ID：LIST", "终端列表", "LIST"):
        return "__list__", "", False

    lines = raw.replace("\r\n", "\n").replace("\r", "\n").splitlines()
    if lines:
        head = lines[0].strip()
        m_line = _ID_LINE.match(head)
        if m_line:
            tid = f"t{m_line.group(1)}"
            body = "\n".join(lines[1:]).strip()
            return tid, body, not body

    m_inline = _ID_INLINE.match(raw)
    if m_inline:
        return f"t{m_inline.group(1)}", m_inline.group(2).strip(), False

    return None, raw, False


def format_terminal_list(sessions: list) -> str:
    if not sessions:
        return "当前没有运行中的 AI 终端。请先在「AI 智能体」新建终端。"
    lines = ["运行中的终端："]
    for s in sessions:
        sid = s.get("id") or ""
        num = sid[1:] if sid.startswith("t") else sid
        title = s.get("title") or sid
        lines.append(f"  ID：{num} → {title} ({sid})")
    lines.append("发送示例：\nID：1\n你好")
    return "\n".join(lines)
