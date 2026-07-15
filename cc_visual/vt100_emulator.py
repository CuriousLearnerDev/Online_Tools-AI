#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""VT100 终端仿真（pyte），支持 ANSI 彩色 + 东亚双宽字符渲染。"""

from __future__ import annotations

import html
from typing import List, Optional, Tuple

try:
    import wcwidth
except ImportError:
    wcwidth = None  # type: ignore

try:
    import pyte

    HAS_PYTE = True
except ImportError:
    HAS_PYTE = False
    pyte = None  # type: ignore

DEFAULT_FG = "#c9d1d9"
DEFAULT_BG = "#0d1117"
CURSOR_FG = "#0d1117"
CURSOR_BG = "#58a6ff"

NAMED_COLORS = {
    "default": DEFAULT_FG,
    "black": "#484f58",
    "red": "#ff7b72",
    "green": "#3fb950",
    "brown": "#d29922",
    "yellow": "#d29922",
    "blue": "#58a6ff",
    "magenta": "#bc8cff",
    "cyan": "#39c5cf",
    "white": "#b1bac4",
    "brightblack": "#6e7681",
    "brightred": "#ffa198",
    "brightgreen": "#56d364",
    "brightbrown": "#e3b341",
    "brightyellow": "#e3b341",
    "brightblue": "#79c0ff",
    "brightmagenta": "#d2a8ff",
    "brightcyan": "#56d4dd",
    "brightwhite": "#f0f6fc",
}

BOLD_MAP = {
    "black": "brightblack",
    "red": "brightred",
    "green": "brightgreen",
    "brown": "brightyellow",
    "yellow": "brightyellow",
    "blue": "brightblue",
    "magenta": "brightmagenta",
    "cyan": "brightcyan",
    "white": "brightwhite",
}


def _char_width(ch: str) -> int:
    if not ch or ch == " ":
        return 1
    if wcwidth is None:
        return 2 if ord(ch) > 0x2E7F else 1
    try:
        w = wcwidth.wcwidth(ord(ch))
        return 2 if w == 2 else 1
    except Exception:
        return 1


def _is_wide(ch: str) -> bool:
    return _char_width(ch) == 2


def _is_padding_space(row, x: int) -> bool:
    """TUI 在宽字符后常插入一个空格占位，渲染时跳过以免错位。"""
    if x <= 0:
        return False
    cur = row[x].data if row[x].data else " "
    if cur != " ":
        return False
    prev = row[x - 1].data if row[x - 1].data else " "
    return _is_wide(prev)


def color_to_hex(name: str, *, is_bg: bool = False) -> str:
    if not name or name == "default":
        return DEFAULT_BG if is_bg else DEFAULT_FG
    if name in NAMED_COLORS:
        return NAMED_COLORS[name]
    cleaned = name.strip().lstrip("#")
    if len(cleaned) == 6:
        try:
            int(cleaned, 16)
            return f"#{cleaned}"
        except ValueError:
            pass
    return DEFAULT_BG if is_bg else DEFAULT_FG


def _resolve_colors(char) -> Tuple[str, str]:
    fg_name = char.fg or "default"
    bg_name = char.bg or "default"
    if char.bold and fg_name in BOLD_MAP:
        fg_name = BOLD_MAP[fg_name]
    if char.reverse:
        fg_name, bg_name = bg_name, fg_name
    return color_to_hex(fg_name, is_bg=False), color_to_hex(bg_name, is_bg=True)


def _style_css(fg: str, bg: str, bold: bool, italics: bool, underline: bool, width_ch: int) -> str:
    parts = [
        f"color:{fg}",
        f"background-color:{bg}",
        f"display:inline-block",
        f"width:{width_ch}ch",
        f"overflow:hidden",
        "vertical-align:top",
        "text-align:left",
    ]
    if bold:
        parts.append("font-weight:bold")
    if italics:
        parts.append("font-style:italic")
    if underline:
        parts.append("text-decoration:underline")
    return ";".join(parts)


def _render_cell(char, ch: str, width_ch: int, is_cursor: bool) -> str:
    if is_cursor:
        css = f"display:inline-block;width:{width_ch}ch;overflow:hidden;color:{CURSOR_FG};background-color:{CURSOR_BG}"
        return f'<span style="{css}">{html.escape(ch, quote=False)}</span>'

    fg, bg = _resolve_colors(char)
    css = _style_css(fg, bg, char.bold, char.italics, char.underscore, width_ch)
    display = ch if ch else " "
    if width_ch == 2 and len(display) == 1 and _is_wide(display):
        pass  # 宽字符占 2ch
    elif width_ch == 2 and display == " ":
        display = "  "
    return f'<span style="{css}">{html.escape(display, quote=False)}</span>'


def _char_style_key(char) -> tuple:
    fg_name = char.fg or "default"
    bg_name = char.bg or "default"
    if char.bold and fg_name in BOLD_MAP:
        fg_name = BOLD_MAP[fg_name]
    if char.reverse:
        fg_name, bg_name = bg_name, fg_name
    return (
        fg_name,
        bg_name,
        char.bold,
        char.italics,
        char.underscore,
    )


def _render_line_html(row, columns: int, cy: int, cx: int, y: int, show_cursor: bool) -> str:
    """合并相邻同样式字符，大幅减少 span 数量。"""
    parts: List[str] = []
    x = 0
    while x < columns:
        if _is_padding_space(row, x):
            x += 1
            continue

        char = row[x]
        ch = char.data if char.data else " "
        w = 2 if _is_wide(ch) else 1
        style_key = _char_style_key(char)
        is_cursor = show_cursor and y == cy and x == cx

        if is_cursor:
            css = (
                f"display:inline-block;width:{w}ch;overflow:hidden;"
                f"color:{CURSOR_FG};background-color:{CURSOR_BG}"
            )
            parts.append(f'<span style="{css}">{html.escape(ch, quote=False)}</span>')
            x += 1
            continue

        run_text: List[str] = []
        run_width = 0
        while x < columns:
            if _is_padding_space(row, x):
                break
            c = row[x]
            c_ch = c.data if c.data else " "
            c_w = 2 if _is_wide(c_ch) else 1
            if _char_style_key(c) != style_key:
                break
            if show_cursor and y == cy and x == cx:
                break
            if c_w == 2 and c_ch == " ":
                run_text.append("  ")
            else:
                run_text.append(c_ch)
            run_width += c_w
            x += 1

        if not run_text:
            x += 1
            continue

        fg, bg = color_to_hex(style_key[0], is_bg=False), color_to_hex(style_key[1], is_bg=True)
        css = _style_css(fg, bg, style_key[2], style_key[3], style_key[4], run_width)
        parts.append(f'<span style="{css}">{html.escape("".join(run_text), quote=False)}</span>')

    return "".join(parts)


class TerminalEmulator:
    def __init__(self, cols: int = 120, rows: int = 40):
        self.cols = max(80, cols)
        self.rows = max(24, rows)
        self._screen = None
        self._stream = None
        self._reset_engine()

    def _reset_engine(self):
        if not HAS_PYTE:
            return
        # 普通 Screen 即可；TUI 自行重绘，无需 HistoryScreen 滚动历史
        self._screen = pyte.Screen(self.cols, self.rows)
        self._stream = pyte.ByteStream(self.screen)

    @property
    def screen(self):
        return self._screen

    def resize(self, cols: int, rows: int):
        cols = max(80, cols)
        rows = max(24, rows)
        if cols == self.cols and rows == self.rows:
            return
        self.cols, self.rows = cols, rows
        if self._screen is not None:
            self._screen.resize(rows, cols)

    def reset(self, cols: Optional[int] = None, rows: Optional[int] = None):
        if cols is not None and rows is not None:
            self.cols = max(80, cols)
            self.rows = max(24, rows)
        self._reset_engine()

    def feed(self, data: str | bytes):
        if not data or self._stream is None:
            return
        if isinstance(data, str):
            data = data.encode("utf-8", errors="replace")
        self._stream.feed(data)

    def _line_has_content(self, row, columns: int) -> bool:
        for x in range(columns):
            ch = row[x].data if row[x].data else " "
            if ch != " ":
                return True
            if row[x].fg != "default" or row[x].bg != "default":
                return True
        return False

    def render_html(self, show_cursor: bool = True) -> str:
        if not HAS_PYTE or self._screen is None:
            return ""

        screen = self._screen
        cy = cx = -1
        if show_cursor and screen.cursor:
            cy, cx = screen.cursor.y, screen.cursor.x

        html_lines: List[str] = []
        last_content_row = -1

        for y in range(screen.lines):
            row = screen.buffer[y]
            line_html = _render_line_html(row, screen.columns, cy, cx, y, show_cursor)
            if self._line_has_content(row, screen.columns):
                last_content_row = y
            html_lines.append(
                '<div style="height:1.15em;white-space:nowrap;overflow:visible;">'
                + line_html
                + "</div>"
            )

        # 保留末尾空行以维持框线高度，但去掉多余尾部
        while len(html_lines) > last_content_row + 2:
            html_lines.pop()

        body = "".join(html_lines) if html_lines else '<div style="height:1.15em">&nbsp;</div>'
        return (
            f'<div style="margin:0;padding:0;background:{DEFAULT_BG};color:{DEFAULT_FG};'
            f'font-family:\'Cascadia Code\',\'Consolas\',\'Courier New\',monospace;'
            f'font-size:11pt;line-height:1.15;letter-spacing:0;">{body}</div>'
        )

    def render_text(self, show_cursor: bool = True) -> str:
        if not HAS_PYTE or self._screen is None:
            return ""
        lines = []
        for y in range(self._screen.lines):
            row = self._screen.buffer[y]
            parts = []
            x = 0
            while x < self._screen.columns:
                if _is_padding_space(row, x):
                    x += 1
                    continue
                ch = row[x].data if row[x].data else " "
                parts.append(ch)
                x += 1
            lines.append("".join(parts))
        while lines and not lines[-1].strip():
            lines.pop()
        return "\n".join(lines)

    @property
    def cursor_pos(self) -> Tuple[int, int]:
        if self._screen and self._screen.cursor:
            return self._screen.cursor.y, self._screen.cursor.x
        return 0, 0
