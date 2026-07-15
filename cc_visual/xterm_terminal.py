#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""xterm.js 内嵌终端 — 完整 VT100/XTerm 仿真，Claude Code TUI 显示正确。"""

from __future__ import annotations

import os
from typing import Dict, List, Optional

from PyQt6.QtCore import QObject, QTimer, QUrl, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from embedded_terminal import (
    HAS_PTY,
    PtyReaderThread,
    _PTY_IO_ERRORS,
    _spawn_pty,
    wrap_argv_for_pty,
)

try:
    from PyQt6.QtWebChannel import QWebChannel
    from PyQt6.QtWebEngineWidgets import QWebEngineView

    HAS_WEBENGINE = True
except ImportError:
    HAS_WEBENGINE = False
    QWebChannel = None  # type: ignore
    QWebEngineView = None  # type: ignore

WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
TERMINAL_HTML = os.path.join(WEB_DIR, "terminal.html")


def xterm_available() -> bool:
    return HAS_PTY and HAS_WEBENGINE and os.path.isfile(TERMINAL_HTML)


class PtyBridge(QObject):
    """Python ↔ xterm.js 双向桥。"""

    output = pyqtSignal(str)

    def __init__(self, terminal_widget: "XtermTerminalWidget"):
        super().__init__()
        self._term = terminal_widget

    @pyqtSlot(str)
    def sendInput(self, data: str):
        self._term._safe_write(data)

    @pyqtSlot(int, int)
    def resize(self, cols: int, rows: int):
        self._term._resize_pty(cols, rows)

    @pyqtSlot()
    def ready(self):
        self._term._on_bridge_ready()


class XtermTerminalWidget(QWidget):
    """基于 xterm.js + QWebEngineView 的终端，与原生 CMD 显示一致。"""

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
        self._bridge_ready = False
        self._pending_output: List[str] = []
        self._bridge: Optional[PtyBridge] = None
        self._channel: Optional[QWebChannel] = None

        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(300)
        self._resize_timer.timeout.connect(self._fit_terminal)

        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)

        bar = QHBoxLayout()
        if xterm_available():
            status, color = "xterm.js 终端就绪 — 完整 TUI 支持", "#9ECE6A"
        else:
            status, color = "xterm 终端不可用", "#F7768E"

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

        if HAS_WEBENGINE and QWebEngineView is not None:
            self._view = QWebEngineView()
            self._view.setStyleSheet("background:#0d1117; border:none;")
            self._bridge = PtyBridge(self)
            self._channel = QWebChannel()
            self._channel.registerObject("bridge", self._bridge)
            self._view.page().setWebChannel(self._channel)
            self._view.load(QUrl.fromLocalFile(TERMINAL_HTML))
            root.addWidget(self._view, 1)
        else:
            self._view = None
            err = QLabel("请安装 PyQt6-WebEngine：pip install PyQt6-WebEngine")
            err.setStyleSheet("color:#F7768E; padding:12px;")
            root.addWidget(err, 1)

    @property
    def screen(self):
        """兼容 main.py 的 focus 调用。"""
        return self._view

    def focus_terminal(self):
        if self._view:
            self._view.setFocus()

    def is_running(self) -> bool:
        return bool(self._pty and self._pty.isalive())

    def apply_launch_spec(self, spec: dict) -> None:
        self._subst_drive = spec.get("subst_drive")
        self._real_cwd = spec.get("real_cwd") or spec.get("cwd")
        self._last_spec = spec

    def _ensure_launch_cwd(self, cwd: str) -> str:
        from claude_launcher import needs_ascii_cwd, resolve_ascii_cwd

        real_cwd = self._real_cwd or cwd
        if self._subst_drive or needs_ascii_cwd(real_cwd):
            launch_cwd, subst_drive = resolve_ascii_cwd(real_cwd)
            self._subst_drive = subst_drive
            return launch_cwd
        return os.path.normpath(cwd)

    def _emit_output(self, data: str):
        if not data:
            return
        if self._bridge_ready and self._bridge:
            self._bridge.output.emit(data)
        else:
            self._pending_output.append(data)

    def _on_bridge_ready(self):
        self._bridge_ready = True
        if self._pending_output:
            batch = "".join(self._pending_output)
            self._pending_output.clear()
            self._emit_output(batch)
        self._fit_terminal()

    def _fit_terminal(self):
        if self._view:
            self._view.page().runJavaScript(
                "if (window.fitTerminal) window.fitTerminal();"
            )

    def _resize_pty(self, cols: int, rows: int):
        if cols < 20 or rows < 5:
            return
        if cols == self._cols and rows == self._rows:
            return
        self._cols, self._rows = cols, rows
        if self._pty and self._pty.isalive():
            try:
                self._pty.setwinsize(rows, cols)
            except Exception:
                pass

    def _clear_screen(self):
        if self._pty and self._pty.isalive():
            self._safe_write("\x0c")
        elif self._bridge_ready and self._bridge:
            self._bridge.output.emit("\x1b[2J\x1b[H")

    def _stop_pty_only(self):
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

    def stop_process(self):
        from claude_launcher import cleanup_subst

        self._stop_pty_only()
        self._session_closed = True
        self._pending_output.clear()
        self.stop_btn.setEnabled(False)
        self.status_label.setText("已停止")
        self.status_label.setStyleSheet("color: #94a3b8; font-size: 9pt;")
        if self._subst_drive:
            cleanup_subst(self._subst_drive)
            self._subst_drive = None
        self._real_cwd = None

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
            self._finalize_session(
                f"管道已关闭: {exc}",
                exit_code=getattr(self._pty, "exitstatus", -1),
            )
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
            self._emit_output(f"\r\n[{status} exit={exit_code}]\r\n")
            self.process_exited.emit(int(exit_code))

    def start_process(
        self,
        argv: List[str],
        cwd: str = "",
        env: Optional[Dict[str, str]] = None,
        *,
        real_cwd: Optional[str] = None,
    ) -> bool:
        if not xterm_available():
            self.process_failed.emit(
                "缺少 PyQt6-WebEngine，请运行：pip install PyQt6-WebEngine pywinpty"
            )
            return False
        if not argv:
            self.process_failed.emit("启动命令为空")
            return False

        if real_cwd:
            self._real_cwd = real_cwd

        self._stop_pty_only()
        self._session_closed = False
        self._pending_output.clear()

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

        # xterm fit 决定初始尺寸，先用合理默认值
        self._cols, self._rows = 120, 40

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
        self.status_label.setText(
            f"运行中 PID {self._pty.pid} — xterm.js 完整终端"
        )
        self.status_label.setStyleSheet("color: #9ECE6A; font-size: 9pt;")
        self.process_started.emit()
        QTimer.singleShot(300, self._fit_terminal)
        QTimer.singleShot(400, self.focus_terminal)
        return True

    def _on_pty_data(self, text: str):
        if text and not self._session_closed:
            self._emit_output(text)

    def _on_reader_finished(self, code: int):
        if self._session_closed:
            return
        self._pty = None
        self._finalize_session("进程已退出", exit_code=code)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._resize_timer.start()
