#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""内嵌 PTY 终端 — winpty + VT100 彩色仿真，键盘/中文输入完整支持。"""

from __future__ import annotations

import html
import os
import select
import subprocess
import sys
from typing import Dict, List, Optional

from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QKeyEvent, QTextCursor
from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QTextEdit, QVBoxLayout, QWidget,
)

from vt100_emulator import HAS_PYTE, TerminalEmulator

try:
    from winpty import PtyProcess
    from winpty.enums import Backend

    HAS_PTY = True
    PTY_IMPORT_ERROR = ""
    try:
        from pywinpty import WinptyError as _WinptyError
    except ImportError:
        _WinptyError = type("_WinptyError", (Exception,), {})
except ImportError as exc:
    HAS_PTY = False
    PtyProcess = None  # type: ignore
    Backend = None  # type: ignore
    _WinptyError = Exception  # type: ignore
    PTY_IMPORT_ERROR = str(exc)

_PTY_IO_ERRORS = (EOFError, OSError, BrokenPipeError, ConnectionResetError)
if HAS_PTY:
    _PTY_IO_ERRORS = _PTY_IO_ERRORS + (_WinptyError,)


def pty_available() -> bool:
    return HAS_PTY and PtyProcess is not None and HAS_PYTE


def wrap_argv_for_pty(argv: List[str]) -> List[str]:
    if not argv or os.name != "nt":
        return list(argv)
    exe = os.path.basename(argv[0]).lower()
    if exe in ("cmd.exe", "powershell.exe", "pwsh.exe", "wt.exe", "claude.exe"):
        return list(argv)
    if exe.endswith((".cmd", ".bat")):
        # /c：子进程结束后 CMD 一并退出，避免僵尸 shell 占住 PTY
        return ["cmd.exe", "/q", "/c"] + list(argv)
    return list(argv)


def _spawn_pty(argv: List[str], cwd: str, env: dict, dimensions: tuple):
    backends = []
    if Backend is not None:
        # ConPTY 在现代 Windows 上更稳定
        backends.extend([Backend.ConPTY, Backend.WinPTY])
    backends.append(None)
    last_err = None
    for backend in backends:
        try:
            kw = {"cwd": cwd, "env": env, "dimensions": dimensions}
            if backend is not None:
                kw["backend"] = backend
            return PtyProcess.spawn(argv, **kw)
        except Exception as exc:
            last_err = exc
    raise last_err or RuntimeError("PTY 启动失败")


class TerminalScreen(QTextEdit):
    """VT100 彩色终端显示 + 键盘/输入法转发到 PTY。"""

    RENDER_INTERVAL_MS = 33  # ~30fps 上限，避免 setHtml 拖死 UI

    def __init__(self, parent=None):
        super().__init__(parent)
        self._write_cb = None
        self._emulator = TerminalEmulator()
        self._last_render = ""
        self._user_scrolled = False
        self._active = False
        self._pending_feed = False

        self._render_timer = QTimer(self)
        self._render_timer.setInterval(self.RENDER_INTERVAL_MS)
        self._render_timer.timeout.connect(self._flush_render)

        self.setReadOnly(True)
        self.setUndoRedoEnabled(False)
        self.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        mono = QFont("Cascadia Code", 11)
        if not mono.exactMatch():
            mono = QFont("Consolas", 11)
        mono.setStyleHint(QFont.StyleHint.Monospace)
        mono.setFixedPitch(True)
        self.setFont(mono)
        self.setStyleSheet("""
            QTextEdit {
                background-color: #0d1117;
                color: #c9d1d9;
                border: none;
                padding: 4px;
            }
        """)
        self.document().setDocumentMargin(0)
        self.verticalScrollBar().valueChanged.connect(self._on_scroll)

    def _on_scroll(self, _value):
        sb = self.verticalScrollBar()
        self._user_scrolled = sb.value() < sb.maximum() - 3

    def set_write_callback(self, callback):
        self._write_cb = callback

    def set_active(self, active: bool):
        self._active = active
        if active:
            self.setFocus(Qt.FocusReason.OtherFocusReason)

    def reset_emulator(self, cols: int, rows: int):
        self._render_timer.stop()
        self._pending_feed = False
        self._emulator.reset(cols, rows)
        self._last_render = ""
        self._user_scrolled = False
        self.clear()

    def feed_and_render(self, data: str):
        if not data:
            return
        self._emulator.feed(data)
        self._pending_feed = True
        if not self._render_timer.isActive():
            self._render_timer.start()

    def _flush_render(self):
        if not self._pending_feed:
            self._render_timer.stop()
            return
        self._pending_feed = False
        self._redraw()

    def _redraw(self):
        html_content = self._emulator.render_html(show_cursor=True)
        if html_content == self._last_render:
            return
        self._last_render = html_content
        at_bottom = not self._user_scrolled
        self.setHtml(html_content)
        if at_bottom:
            sb = self.verticalScrollBar()
            sb.setValue(sb.maximum())

    def append_status_line(self, msg: str):
        gray = f'<span style="color:#6e7681;">{html.escape(msg, quote=False)}</span>'
        self.setHtml(self.toHtml() + "<br>" + gray)

    def mousePressEvent(self, event):
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        super().mousePressEvent(event)

    def inputMethodEvent(self, event):
        if self._active and self._write_cb:
            text = event.commitString()
            if text:
                self._write_cb(text)
            event.accept()
            return
        super().inputMethodEvent(event)

    def _send(self, data: str) -> bool:
        if not self._active or not self._write_cb or not data:
            return False
        return self._write_cb(data)

    def keyPressEvent(self, event: QKeyEvent):
        if not self._active or not self._write_cb:
            event.ignore()
            return

        key = event.key()
        mods = event.modifiers()
        text = event.text()

        special = {
            Qt.Key.Key_Return: "\r",
            Qt.Key.Key_Enter: "\r",
            Qt.Key.Key_Backspace: "\x7f",
            Qt.Key.Key_Tab: "\t",
            Qt.Key.Key_Escape: "\x1b",
            Qt.Key.Key_Up: "\x1b[A",
            Qt.Key.Key_Down: "\x1b[B",
            Qt.Key.Key_Right: "\x1b[C",
            Qt.Key.Key_Left: "\x1b[D",
            Qt.Key.Key_Home: "\x1b[H",
            Qt.Key.Key_End: "\x1b[F",
            Qt.Key.Key_PageUp: "\x1b[5~",
            Qt.Key.Key_PageDown: "\x1b[6~",
            Qt.Key.Key_Delete: "\x1b[3~",
            Qt.Key.Key_Insert: "\x1b[2~",
        }
        if key in special:
            self._send(special[key])
            event.accept()
            return

        if mods & Qt.KeyboardModifier.ControlModifier:
            if key == Qt.Key.Key_C:
                self._send("\x03")
                event.accept()
                return
            if key == Qt.Key.Key_D:
                self._send("\x04")
                event.accept()
                return
            if key == Qt.Key.Key_L:
                self._send("\x0c")
                event.accept()
                return
            if key == Qt.Key.Key_V:
                from PyQt6.QtWidgets import QApplication
                clip = QApplication.clipboard().text()
                if clip:
                    self._send(clip)
                event.accept()
                return

        if text:
            self._send(text)
            event.accept()
            return

        event.accept()

    def insertFromMimeData(self, source):
        if self._active and self._write_cb:
            text = source.text()
            if text:
                self._write_cb(text)
            return
        super().insertFromMimeData(source)


class PtyReaderThread(QThread):
    """在后台线程读取 PTY，避免 read()/select 阻塞 GUI。"""

    data_received = pyqtSignal(str)
    reader_finished = pyqtSignal(int)

    def __init__(self, pty, parent=None):
        super().__init__(parent)
        self._pty = pty

    def run(self):
        fd = self._pty.fileno() if hasattr(self._pty, "fileno") else getattr(self._pty, "fd", None)
        while self._pty and self._pty.isalive():
            try:
                if fd is not None:
                    ready, _, _ = select.select([fd], [], [], 0.1)
                    if not ready:
                        continue
                chunk = self._pty.read(65536)
            except EOFError:
                break
            except _PTY_IO_ERRORS:
                if not self._pty.isalive():
                    break
                continue
            except Exception:
                if not self._pty.isalive():
                    break
                continue
            if chunk:
                self.data_received.emit(chunk)

        code = -1
        if self._pty is not None:
            try:
                if self._pty.isalive():
                    self._pty.wait()
            except Exception:
                pass
            try:
                code = self._pty.exitstatus if self._pty.exitstatus is not None else -1
            except Exception:
                pass
        self.reader_finished.emit(int(code))


class EmbeddedPtyTerminalWidget(QWidget):
    process_started = pyqtSignal()
    process_exited = pyqtSignal(int)
    process_failed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pty = None
        self._reader: Optional[PtyReaderThread] = None
        self._session_closed = False
        self._cols = 120
        self._rows = 40
        self._last_spec: Optional[dict] = None
        self._subst_drive: Optional[str] = None
        self._real_cwd: Optional[str] = None
        self._pending_data: List[str] = []

        self._feed_timer = QTimer(self)
        self._feed_timer.setInterval(16)
        self._feed_timer.timeout.connect(self._flush_pending_data)

        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(400)
        self._resize_timer.timeout.connect(self._apply_resize)

        self._build_ui()
        self.screen.set_write_callback(self._safe_write)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)

        bar = QHBoxLayout()
        if pty_available():
            status, color = "PTY 终端就绪 — 点击终端区域输入", "#9ECE6A"
        else:
            status, color = "终端不可用", "#F7768E"

        self.status_label = QLabel(status)
        self.status_label.setStyleSheet(f"color: {color}; font-size: 9pt;")
        bar.addWidget(self.status_label, 1)

        self.stop_btn = QPushButton("停止")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_process)
        bar.addWidget(self.stop_btn)

        self.clear_btn = QPushButton("清屏")
        self.clear_btn.clicked.connect(self._clear_screen)
        bar.addWidget(self.clear_btn)
        root.addLayout(bar)

        self.screen = TerminalScreen()
        self.screen.setMinimumHeight(300)
        root.addWidget(self.screen, 1)

        if not pty_available():
            missing = []
            if not HAS_PTY:
                missing.append(f"pywinpty: {PTY_IMPORT_ERROR}")
            if not HAS_PYTE:
                missing.append("pyte")
            self.screen.setHtml(
                f'<pre style="color:#F7768E;background:#0d1117;">'
                f'内嵌终端不可用，请安装依赖后重启：<br>'
                f'pip install pywinpty PyQt6 pyte wcwidth<br><br>'
                f'{"<br>".join(html.escape(m) for m in missing)}</pre>'
            )

    def _calc_size(self) -> tuple[int, int]:
        fm = self.screen.fontMetrics()
        cell_w = max(fm.horizontalAdvance("M"), 8)
        cell_h = max(fm.height(), 14)
        # Claude 欢迎框约 115 列，尽量对齐
        cols = max(100, min(120, max(100, self.screen.width() // cell_w)))
        rows = max(28, min(50, max(28, self.screen.height() // cell_h)))
        return cols, rows

    def is_running(self) -> bool:
        return bool(self._pty and self._pty.isalive())

    def _clear_screen(self):
        if self._pty and self._pty.isalive():
            self._safe_write("\x0c")
        else:
            self.screen.reset_emulator(self._cols, self._rows)

    def clear_screen(self):
        self._clear_screen()

    def _stop_pty_only(self):
        """仅终止 PTY 与读线程，不释放 subst。"""
        self._feed_timer.stop()
        self._pending_data.clear()
        if self._reader and self._reader.isRunning():
            self._reader.wait(2000)
            self._reader = None
        if self._pty:
            try:
                if self._pty.isalive():
                    self._pty.terminate(force=False)
                    try:
                        self._pty.wait()
                    except Exception:
                        self._pty.terminate(force=True)
            except Exception:
                pass
            try:
                self._pty.close(force=True)
            except Exception:
                pass
            self._pty = None
        self.screen._render_timer.stop()
        self.screen.set_active(False)

    def stop_process(self):
        from claude_launcher import cleanup_subst

        self._stop_pty_only()
        self._session_closed = True
        self.stop_btn.setEnabled(False)
        self.status_label.setText("已停止")
        self.status_label.setStyleSheet("color: #94a3b8; font-size: 9pt;")
        if self._subst_drive:
            cleanup_subst(self._subst_drive)
            self._subst_drive = None
        self._real_cwd = None

    def apply_launch_spec(self, spec: dict) -> None:
        """从 prepare_launch 写入 subst 等信息。"""
        self._subst_drive = spec.get("subst_drive")
        self._real_cwd = spec.get("real_cwd") or spec.get("cwd")
        self._last_spec = spec

    def _ensure_launch_cwd(self, cwd: str) -> str:
        """确保 subst 映射仍有效（stop 后重新启动时需要）。"""
        from claude_launcher import needs_ascii_cwd, resolve_ascii_cwd

        real_cwd = self._real_cwd or cwd
        if self._subst_drive or needs_ascii_cwd(real_cwd):
            launch_cwd, subst_drive = resolve_ascii_cwd(real_cwd)
            self._subst_drive = subst_drive
            return launch_cwd
        return os.path.normpath(cwd)

    def _safe_write(self, data: str) -> bool:
        if self._session_closed or not self._pty or not data:
            return False
        try:
            if not self._pty.isalive():
                self._finalize_session("进程已结束", exit_code=self._pty.exitstatus)
                return False
            self._pty.write(data)
            return True
        except _PTY_IO_ERRORS as exc:
            self._finalize_session(f"管道已关闭: {exc}", exit_code=getattr(self._pty, "exitstatus", -1))
            return False
        except Exception as exc:
            self._finalize_session(f"写入失败: {exc}", exit_code=-1)
            return False

    def _finalize_session(
        self,
        status: str,
        exit_code: Optional[int] = -1,
        notify: bool = True,
    ):
        if self._session_closed:
            return
        self._session_closed = True
        self._stop_pty_only()
        self.stop_btn.setEnabled(False)
        self.status_label.setText(status[:100])
        self.status_label.setStyleSheet("color: #94a3b8; font-size: 9pt;")
        if self._subst_drive:
            from claude_launcher import cleanup_subst
            cleanup_subst(self._subst_drive)
            self._subst_drive = None
        self._real_cwd = None
        if notify and exit_code is not None:
            self.screen.append_status_line(f"[{status} exit={exit_code}]")
            self.process_exited.emit(int(exit_code))

    def start_process(
        self,
        argv: List[str],
        cwd: str = "",
        env: Optional[Dict[str, str]] = None,
        *,
        real_cwd: Optional[str] = None,
    ) -> bool:
        if not pty_available():
            self.process_failed.emit("缺少 pywinpty / pyte，请 pip install pywinpty pyte wcwidth")
            return False
        if not argv:
            self.process_failed.emit("启动命令为空")
            return False

        if real_cwd:
            self._real_cwd = real_cwd

        self._stop_pty_only()
        self._session_closed = False

        work_cwd = self._ensure_launch_cwd(cwd or self._real_cwd or "")
        if not work_cwd or not os.path.isdir(work_cwd):
            self.process_failed.emit(f"工作目录不存在: {work_cwd or cwd}")
            return False

        self._last_spec = {
            "argv": argv,
            "cwd": work_cwd,
            "real_cwd": self._real_cwd or work_cwd,
            "env": dict(env or os.environ),
            "subst_drive": self._subst_drive,
        }

        self._cols, self._rows = self._calc_size()
        self.screen.reset_emulator(self._cols, self._rows)

        proc_env = dict(env or os.environ)
        proc_env.setdefault("TERM", "xterm-256color")
        proc_env.setdefault("COLORTERM", "truecolor")
        proc_env["COLUMNS"] = str(self._cols)
        proc_env["LINES"] = str(self._rows)

        pty_argv = wrap_argv_for_pty(argv)
        try:
            self._pty = _spawn_pty(pty_argv, work_cwd, proc_env, (self._rows, self._cols))
        except Exception as e:
            self.process_failed.emit(str(e))
            return False

        self._reader = PtyReaderThread(self._pty, self)
        self._reader.data_received.connect(self._on_pty_data)
        self._reader.reader_finished.connect(self._on_reader_finished)
        self._reader.start()
        self.stop_btn.setEnabled(True)
        self.screen.set_active(True)
        self.screen.setFocus(Qt.FocusReason.OtherFocusReason)
        self.status_label.setText(f"运行中 PID {self._pty.pid} ({self._cols}×{self._rows}) — 点击终端输入")
        self.status_label.setStyleSheet("color: #9ECE6A; font-size: 9pt;")
        self.process_started.emit()
        return True

    def launch_external_fallback(self) -> bool:
        from claude_launcher import launch_external_terminal

        ok, msg = launch_external_terminal(spec=self._last_spec)
        if ok:
            self.status_label.setText("已打开外部 CMD 窗口")
        else:
            self.process_failed.emit(msg)
        return ok

    def _on_pty_data(self, text: str):
        if not text or self._session_closed:
            return
        self._pending_data.append(text)
        if not self._feed_timer.isActive():
            self._feed_timer.start()

    def _flush_pending_data(self):
        if not self._pending_data or self._session_closed:
            self._feed_timer.stop()
            self._pending_data.clear()
            return
        batch = "".join(self._pending_data)
        self._pending_data.clear()
        self.screen.feed_and_render(batch)

    def _on_reader_finished(self, code: int):
        if self._session_closed:
            return
        self._pty = None
        self._finalize_session("进程已退出", exit_code=code)

    def _apply_resize(self):
        if not self._pty or self._session_closed or not self._pty.isalive():
            return
        cols, rows = self._calc_size()
        if cols == self._cols and rows == self._rows:
            return
        self._cols, self._rows = cols, rows
        try:
            self._pty.setwinsize(rows, cols)
        except Exception:
            return
        # 仅通知子进程尺寸变化，不重建 pyte 缓冲区（避免 TUI 闪断）

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self._pty or self._session_closed or not self._pty.isalive():
            return
        self._resize_timer.start()
