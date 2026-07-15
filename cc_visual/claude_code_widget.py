#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Claude Code 控制台 — 可嵌入统领 AI 智能体 Tab。"""

from __future__ import annotations

import os
from typing import Callable, Optional

from PyQt6.QtCore import Qt, QSettings, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from cc_visual.activity_panel import ActivityPanel
from cc_visual.claude_launcher import (
    CLAUDE_DIR,
    DEFAULT_PROXY,
    cleanup_all_substs,
    launch_claude_subcommand_external,
    launch_external_terminal,
    prepare_launch,
    resolve_claude_cli,
    run_claude_command,
)
from cc_visual.launch_options_widget import QuickActionsWidget
from cc_visual.provider_manager import get_active_provider
from cc_visual.provider_panel import ProviderPanel
from cc_visual.settings_dialog import SettingsDialog, SettingsPanel
from cc_visual.ui_styles import APP_STYLESHEET

try:
    from cc_visual.xterm_terminal import XtermTerminalWidget, xterm_available
except ImportError:
    XtermTerminalWidget = None  # type: ignore
    xterm_available = lambda: False  # type: ignore

from cc_visual.embedded_terminal import EmbeddedPtyTerminalWidget, pty_available


def _step_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("stepLabel")
    return label


class ClaudeCodeWidget(QWidget):
    """CC可视化 主界面（QWidget，非 QMainWindow）。"""

    status_message = pyqtSignal(str)

    def __init__(
        self,
        parent=None,
        *,
        settings_org: str = "统领",
        settings_app: str = "ClaudeCodeAgent",
        default_workdir: str = "",
    ):
        super().__init__(parent)
        self._settings = QSettings(settings_org, settings_app)
        self._default_workdir = default_workdir or CLAUDE_DIR
        self._settings_holder = QWidget(self)
        self._settings_holder.hide()
        self.settings_panel = SettingsPanel(self._settings, self._settings_holder)
        self._on_connect_mcp: Optional[Callable[[], None]] = None
        self._on_select_skills: Optional[Callable[[], None]] = None
        self.setStyleSheet(APP_STYLESHEET)
        self._build_ui()
        self._load_settings()
        self._refresh_version_info()

    def set_hexstrike_hooks(
        self,
        *,
        connect_mcp: Optional[Callable[[], None]] = None,
        select_skills: Optional[Callable[[], None]] = None,
    ):
        self._on_connect_mcp = connect_mcp
        self._on_select_skills = select_skills
        show = bool(connect_mcp or select_skills)
        self.hexstrike_box.setVisible(show)

    @property
    def workdir(self) -> str:
        return self.settings_panel.workdir_input.text().strip()

    @property
    def proxy(self) -> str:
        return self.settings_panel.proxy_input.text().strip()

    @property
    def terminal(self):
        return self._terminal

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter)

        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setMinimumWidth(300)
        sidebar.setMaximumWidth(380)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(10, 10, 10, 10)
        sidebar_layout.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel("Claude Code")
        title.setObjectName("titleLabel")
        header.addWidget(title)
        header.addStretch()
        self.version_label = QLabel("")
        self.version_label.setObjectName("subLabel")
        menu_btn = QPushButton("⋯")
        menu_btn.setObjectName("compactBtn")
        menu_btn.setFixedWidth(32)
        menu = QMenu(self)
        menu.addAction("设置…", self._open_settings)
        menu.addSeparator()
        menu.addAction("登录状态", self._check_auth_status)
        menu.addAction("检查更新", self._run_update_check)
        menu.addAction("MCP 管理", lambda: self._open_subcommand(["mcp"], "Claude MCP"))
        menu.addAction("Agents", lambda: self._open_subcommand(["agents"], "Claude Agents"))
        menu.addAction("恢复选中会话", self._resume_from_activity_panel)
        menu_btn.setMenu(menu)
        header.addWidget(self.version_label)
        header.addWidget(menu_btn)
        sidebar_layout.addLayout(header)

        self.sidebar_tabs = QTabWidget()
        self.sidebar_tabs.setDocumentMode(True)

        # ── Tab 1：控制台（选模型 → 应用 → 启动）──
        console_tab = QWidget()
        console_layout = QVBoxLayout(console_tab)
        console_layout.setContentsMargins(4, 8, 4, 4)
        console_layout.setSpacing(8)

        guide_bar = QWidget()
        guide_bar.setObjectName("guideBar")
        gl = QHBoxLayout(guide_bar)
        gl.setContentsMargins(8, 4, 8, 4)
        gl.addWidget(QLabel("选模型 → 应用 → 启动"))
        console_layout.addWidget(guide_bar)

        console_layout.addWidget(_step_label("API / 模型"))
        self.provider_panel = ProviderPanel()
        self.provider_panel.provider_changed.connect(self._on_provider_changed)
        console_layout.addWidget(self.provider_panel)

        self.hexstrike_box = QWidget()
        hs = QVBoxLayout(self.hexstrike_box)
        hs.setContentsMargins(0, 0, 0, 0)
        hs.setSpacing(6)
        mcp_btn = QPushButton("一键连接 MCP")
        mcp_btn.setObjectName("secondaryBtn")
        mcp_btn.clicked.connect(self._invoke_connect_mcp)
        hs.addWidget(mcp_btn)
        skills_btn = QPushButton("选择并导入 Skills")
        skills_btn.setObjectName("secondaryBtn")
        skills_btn.setToolTip("勾选要同步到 .claude/skills/ 的技能包")
        skills_btn.clicked.connect(self._invoke_select_skills)
        hs.addWidget(skills_btn)
        console_layout.addWidget(self.hexstrike_box)
        self.hexstrike_box.hide()

        self.workdir_summary = QLabel("")
        self.workdir_summary.setWordWrap(True)
        self.workdir_summary.setObjectName("hintLabel")
        console_layout.addWidget(self.workdir_summary)

        settings_btn = QPushButton("⚙  设置（目录 / 启动方式）")
        settings_btn.setObjectName("secondaryBtn")
        settings_btn.clicked.connect(self._open_settings)
        console_layout.addWidget(settings_btn)
        console_layout.addStretch()
        self.sidebar_tabs.addTab(console_tab, "控制台")

        # ── Tab 2：活动 ──
        self.activity_panel = ActivityPanel(show_header=False)
        self.sidebar_tabs.addTab(self.activity_panel, "活动")

        sidebar_layout.addWidget(self.sidebar_tabs, 1)

        launch_bar = QWidget()
        launch_bar.setObjectName("launchBar")
        bl = QVBoxLayout(launch_bar)
        bl.setContentsMargins(8, 8, 8, 8)
        self.start_btn = QPushButton("▶  启动 Claude Code")
        self.start_btn.setObjectName("primaryBtn")
        self.start_btn.clicked.connect(self._start_embedded)
        bl.addWidget(self.start_btn)
        sub = QHBoxLayout()
        self.ext_btn = QPushButton("外部 CMD")
        self.ext_btn.setObjectName("secondaryBtn")
        self.ext_btn.clicked.connect(self._start_external)
        sub.addWidget(self.ext_btn)
        self.stop_btn = QPushButton("停止")
        self.stop_btn.setObjectName("dangerBtn")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop)
        sub.addWidget(self.stop_btn)
        bl.addLayout(sub)
        sidebar_layout.addWidget(launch_bar)
        splitter.addWidget(sidebar)

        center = QWidget()
        cl = QVBoxLayout(center)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.addWidget(QLabel("终端", objectName="sectionTitle"))
        if xterm_available() and XtermTerminalWidget is not None:
            self._terminal = XtermTerminalWidget()
        else:
            self._terminal = EmbeddedPtyTerminalWidget()
        self._terminal.process_started.connect(self._on_started)
        self._terminal.process_exited.connect(self._on_exited)
        self._terminal.process_failed.connect(self._on_failed)
        cl.addWidget(self._terminal, 1)
        splitter.addWidget(center)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([340, 900])

        self.settings_panel.workdir_input.textChanged.connect(self._on_workdir_changed)
        self.settings_panel.prompt_input.textChanged.connect(self._update_cmd_preview)
        self.settings_panel.launch_options.options_changed.connect(self._update_cmd_preview)
        self.activity_panel.resume_session.connect(self._on_resume_session)

    def apply_hexstrike_setup(
        self,
        *,
        mcp_json_path: str = "",
        add_dirs: Optional[list] = None,
    ):
        """一键 MCP / Skills 后写入启动参数，确保下次启动 Claude 能加载。"""
        lo = self.settings_panel.launch_options
        if mcp_json_path and os.path.isfile(mcp_json_path):
            lo.mcp_config_input.setText(os.path.normpath(mcp_json_path))
        if add_dirs:
            existing = [p.strip() for p in lo.add_dirs_input.text().split("|") if p.strip()]
            for d in add_dirs:
                d = os.path.normpath(d)
                if d and os.path.isdir(d) and d not in existing:
                    existing.append(d)
            lo.add_dirs_input.setText("|".join(existing))
        self._save_settings()
        self._update_cmd_preview()

    def _invoke_connect_mcp(self):
        if self._on_connect_mcp:
            self._on_connect_mcp()

    def _invoke_select_skills(self):
        if self._on_select_skills:
            self._on_select_skills()

    def _emit_status(self, msg: str):
        self.status_message.emit(msg)

    def _open_settings(self):
        self.settings_panel.sync_prompt_visibility()
        self.settings_panel.show()
        dlg = SettingsDialog(self.settings_panel, self._settings_holder, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self._save_settings()
        self._on_workdir_changed(self.workdir)
        self._update_cmd_preview()
        self._emit_status("设置已保存")

    def _refresh_workdir_summary(self):
        wd = self.workdir or self._default_workdir
        mode = self.settings_panel.launch_options.mode_combo.currentText()
        self.workdir_summary.setText(f"目录：{wd}\n启动：{mode}")

    def _refresh_version_info(self):
        rt = resolve_claude_cli()
        if rt["cli_argv"]:
            self.version_label.setText(rt.get("version_hint") or "已安装")
        else:
            self.version_label.setText("未安装")

    def _on_workdir_changed(self, text: str):
        wd = text.strip()
        self.activity_panel.set_work_dir(wd)
        self.settings_panel.launch_options.set_work_dir(wd)
        self._refresh_workdir_summary()
        self._update_cmd_preview()

    def _update_cmd_preview(self):
        rt = resolve_claude_cli()
        base = rt.get("cli_argv") or ["claude"]
        self.settings_panel.launch_options.update_cmd_preview(
            base, self.settings_panel.prompt_input.toPlainText().strip()
        )

    def _on_resume_session(self, session_id: str):
        self.settings_panel.launch_options.set_resume_session(session_id)
        self._refresh_workdir_summary()
        self._emit_status(f"已设置恢复会话: {session_id[:8]}…")

    def _resume_from_activity_panel(self):
        session = self.activity_panel._current_session
        if session:
            self._on_resume_session(session.session_id)
        else:
            QMessageBox.information(self, "提示", "请先在「活动」选项卡中选中一条会话")

    def _on_provider_changed(self, provider_id: str):
        active = get_active_provider()
        name = active.name if active else provider_id
        model = (active.env.get("ANTHROPIC_MODEL") or active.model_hint) if active else ""
        msg = f"已切换为 {name}" + (f" · {model}" if model else "") + "，请重新启动"
        self._emit_status(msg)
        self.settings_panel.launch_options.set_provider_model_hint(model or "")
        self._update_cmd_preview()

    def _check_auth_status(self):
        code, out, err = run_claude_command(
            ["auth", "status", "--text"],
            work_dir=self.workdir,
            proxy=self.proxy,
        )
        text = (out or err or "无输出").strip()
        if code == 0:
            QMessageBox.information(self, "登录状态", text)
        else:
            QMessageBox.warning(self, "未登录或检查失败", text)

    def _run_update_check(self):
        if (
            QMessageBox.question(self, "检查更新", "将运行 claude update。继续？")
            != QMessageBox.StandardButton.Yes
        ):
            return
        code, out, err = run_claude_command(
            ["update"], work_dir=self.workdir, proxy=self.proxy, timeout=120,
        )
        QMessageBox.information(self, "更新结果", (out or err or "").strip() or f"退出码 {code}")

    def _open_subcommand(self, sub_args: list, title: str):
        ok, msg = launch_claude_subcommand_external(
            sub_args, work_dir=self.workdir, proxy=self.proxy, title=title,
        )
        if ok:
            self._emit_status(msg)
        else:
            QMessageBox.critical(self, "启动失败", msg)

    def _launch_spec(self, *, embedded: bool = False):
        self._save_settings()
        options = self.settings_panel.launch_options.get_options()
        prompt = self.settings_panel.prompt_input.toPlainText().strip()
        if options.mode == "print" and not prompt:
            QMessageBox.warning(self, "缺少问题", "单次提问模式需在设置里填写问题。")
            return None
        ok, msg, spec = prepare_launch(
            proxy=self.proxy,
            work_dir=self.workdir or self._default_workdir,
            initial_prompt=prompt,
            ascii_cwd=embedded,
            options=options,
        )
        if not ok or not spec:
            QMessageBox.critical(self, "启动失败", msg)
            return None
        return spec

    def _start_embedded(self):
        if not (xterm_available() or pty_available()):
            QMessageBox.critical(self, "缺少依赖", "pip install PyQt6-WebEngine pywinpty")
            return
        if self._terminal.is_running():
            QMessageBox.information(self, "提示", "终端已在运行中")
            return
        self.start_btn.setEnabled(False)
        self._emit_status("正在启动…")
        QApplication.processEvents()
        spec = self._launch_spec(embedded=True)
        if not spec:
            self.start_btn.setEnabled(True)
            return
        if hasattr(self._terminal, "apply_launch_spec"):
            self._terminal.apply_launch_spec(spec)
        if self._terminal.start_process(spec["argv"], spec["cwd"], spec["env"], real_cwd=spec.get("real_cwd")):
            note = f"（{spec['subst_drive']}）" if spec.get("subst_drive") else ""
            self._emit_status(f"运行中{note} — 点击终端输入")
            focus = getattr(self._terminal, "focus_terminal", None)
            if focus:
                QTimer.singleShot(400, focus)
            elif getattr(self._terminal, "screen", None):
                QTimer.singleShot(400, self._terminal.screen.setFocus)
        else:
            self.start_btn.setEnabled(True)

    def _start_external(self):
        spec = self._launch_spec(embedded=False)
        if not spec:
            return
        ok, msg = launch_external_terminal(spec=spec)
        if ok:
            self._emit_status(msg)
        else:
            QMessageBox.critical(self, "启动失败", msg)

    def _stop(self):
        self._terminal.stop_process()
        self._on_exited(-1)

    def _on_started(self):
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.activity_panel.start_watching()

    def _on_exited(self, code: int):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.activity_panel.stop_watching()
        self.activity_panel.refresh()
        self._emit_status(f"已退出 (code={code})")

    def _on_failed(self, msg: str):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.activity_panel.stop_watching()
        self._emit_status(msg[:120])
        QMessageBox.warning(self, "启动失败", msg)

    def _save_settings(self):
        sp = self.settings_panel
        self._settings.setValue("proxy", sp.proxy_input.text())
        self._settings.setValue("workdir", sp.workdir_input.text())
        self._settings.setValue("prompt", sp.prompt_input.toPlainText())
        sp.launch_options.save_to_settings()

    def _load_settings(self):
        sp = self.settings_panel
        saved_proxy = str(self._settings.value("proxy", DEFAULT_PROXY))
        if saved_proxy == "127.0.0.1:7897":
            saved_proxy = ""
        sp.proxy_input.setText(saved_proxy)
        sp.workdir_input.setText(str(self._settings.value("workdir", self._default_workdir)))
        p = self._settings.value("prompt", "")
        if p:
            sp.prompt_input.setPlainText(str(p))
        sp.launch_options.load_from_settings()
        sp.sync_prompt_visibility()
        self.provider_panel.sync_active_from_live()
        self._on_workdir_changed(sp.workdir_input.text())

    def cleanup(self):
        self._save_settings()
        self.activity_panel.stop_watching()
        if self._terminal.is_running():
            self._terminal.stop_process()
        cleanup_all_substs()
