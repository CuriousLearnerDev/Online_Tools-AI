#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Claude Code 启动选项 — 简单模式 + 可折叠高级参数。"""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from claude_options import (
    CHROME_OPTIONS,
    EFFORT_LEVELS,
    LAUNCH_MODES,
    MODELS,
    PERMISSION_MODES,
    LaunchOptions,
    load_project_settings_summary,
    options_from_settings,
    save_options_to_settings,
)

SIMPLE_MODES = [
    ("interactive", "新对话"),
    ("continue", "继续上次"),
    ("resume", "恢复指定会话"),
    ("print", "单次提问（-p）"),
]

SIMPLE_PERMISSIONS = [
    ("", "每次询问（推荐）"),
    ("acceptEdits", "自动接受编辑"),
    ("plan", "只规划不改文件"),
    ("bypassPermissions", "全自动（慎用）"),
]

_MODE_HINTS = {
    "interactive": "正常聊天，留空下方提示词即可。",
    "continue": "接着上一次会话继续，无需选 ID。",
    "resume": "在右侧「会话」里选中后点恢复，或填写会话 ID。",
    "print": "问一句得一句，适合脚本；需在下方填写问题。",
}


class LaunchOptionsWidget(QWidget):
    """启动选项：默认只显示 2 个下拉框，高级参数可折叠。"""

    options_changed = pyqtSignal()

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self._settings = settings
        self._work_dir = ""
        self._advanced_visible = False
        self._build_ui()
        self.load_from_settings()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        self.mode_combo = QComboBox()
        for val, label in SIMPLE_MODES:
            self.mode_combo.addItem(label, val)
        self.mode_combo.currentIndexChanged.connect(self._on_simple_mode_changed)

        self.permission_combo = QComboBox()
        for val, label in SIMPLE_PERMISSIONS:
            self.permission_combo.addItem(label, val)

        self.mode_hint = QLabel(_MODE_HINTS["interactive"])
        self.mode_hint.setWordWrap(True)
        self.mode_hint.setObjectName("stepHint")

        self.resume_row = QWidget()
        resume_layout = QHBoxLayout(self.resume_row)
        resume_layout.setContentsMargins(0, 0, 0, 0)
        resume_layout.addWidget(QLabel("会话 ID"))
        self.resume_id_input = QLineEdit()
        self.resume_id_input.setPlaceholderText("留空则弹出选择器")
        resume_layout.addWidget(self.resume_id_input, 1)
        self.resume_row.hide()

        form = QFormLayout()
        form.setSpacing(8)
        form.setContentsMargins(0, 0, 0, 0)
        form.addRow("对话方式", self.mode_combo)
        form.addRow("改代码时", self.permission_combo)
        form.addRow(self.resume_row)
        root.addLayout(form)
        root.addWidget(self.mode_hint)

        self.toggle_advanced_btn = QPushButton("▸ 高级 CLI 参数（一般不用改）")
        self.toggle_advanced_btn.setObjectName("toggleBtn")
        self.toggle_advanced_btn.clicked.connect(self._toggle_advanced)
        root.addWidget(self.toggle_advanced_btn)

        self.advanced_frame = QFrame()
        self.advanced_frame.hide()
        adv_layout = QVBoxLayout(self.advanced_frame)
        adv_layout.setContentsMargins(0, 4, 0, 0)
        adv_layout.setSpacing(6)

        tabs = QTabWidget()
        tabs.addTab(self._build_extra_basic_tab(), "模型")
        tabs.addTab(self._build_session_tab(), "会话")
        tabs.addTab(self._build_advanced_tab(), "路径/MCP")
        tabs.addTab(self._build_tools_tab(), "工具")
        adv_layout.addWidget(tabs)

        self.project_settings_label = QLabel("")
        self.project_settings_label.setWordWrap(True)
        self.project_settings_label.setObjectName("hintLabel")
        adv_layout.addWidget(self.project_settings_label)

        self.cmd_preview = QLineEdit()
        self.cmd_preview.setReadOnly(True)
        self.cmd_preview.setPlaceholderText("实际执行的命令…")
        self.cmd_preview.setObjectName("cmdPreview")
        adv_layout.addWidget(self.cmd_preview)

        root.addWidget(self.advanced_frame)

        self.permission_combo.currentIndexChanged.connect(self._emit_changed)
        self.resume_id_input.textChanged.connect(self._emit_changed)

    def _build_extra_basic_tab(self) -> QWidget:
        tab = QWidget()
        form = QFormLayout(tab)

        hint = QLabel("第三方 API 的模型请在左侧「API 提供商」里设置；此处仅覆盖官方 sonnet/opus。")
        hint.setWordWrap(True)
        hint.setObjectName("hintLabel")
        form.addRow(hint)

        self.model_combo = QComboBox()
        for val, label in MODELS:
            self.model_combo.addItem(label, val)
        form.addRow("CLI 模型", self.model_combo)

        self.effort_combo = QComboBox()
        for val, label in EFFORT_LEVELS:
            self.effort_combo.addItem(label, val)
        form.addRow("工作量", self.effort_combo)

        self.chrome_combo = QComboBox()
        for val, label in CHROME_OPTIONS:
            self.chrome_combo.addItem(label, val)
        form.addRow("Chrome", self.chrome_combo)

        self.safe_mode_cb = QCheckBox("安全模式")
        self.bare_cb = QCheckBox("Bare 模式")
        self.verbose_cb = QCheckBox("详细日志")
        form.addRow(self.safe_mode_cb)
        form.addRow(self.bare_cb)
        form.addRow(self.verbose_cb)

        for ctrl in (
            self.model_combo, self.effort_combo, self.chrome_combo,
            self.safe_mode_cb, self.bare_cb, self.verbose_cb,
        ):
            if isinstance(ctrl, QComboBox):
                ctrl.currentIndexChanged.connect(self._emit_changed)
            else:
                ctrl.toggled.connect(self._emit_changed)
        return tab

    def _build_session_tab(self) -> QWidget:
        tab = QWidget()
        form = QFormLayout(tab)

        self.session_name_input = QLineEdit()
        self.session_name_input.setPlaceholderText("会话显示名")
        form.addRow("名称", self.session_name_input)

        self.fork_session_cb = QCheckBox("恢复时分叉")
        form.addRow(self.fork_session_cb)

        self.from_pr_input = QLineEdit()
        self.from_pr_input.setPlaceholderText("PR 号或 URL")
        form.addRow("关联 PR", self.from_pr_input)

        self.worktree_input = QLineEdit()
        self.worktree_input.setPlaceholderText("worktree 名称")
        form.addRow("Worktree", self.worktree_input)

        self.no_persist_cb = QCheckBox("不保存会话")
        form.addRow(self.no_persist_cb)

        for ctrl in (
            self.session_name_input, self.from_pr_input, self.worktree_input,
            self.fork_session_cb, self.no_persist_cb,
        ):
            if isinstance(ctrl, QLineEdit):
                ctrl.textChanged.connect(self._emit_changed)
            else:
                ctrl.toggled.connect(self._emit_changed)
        return tab

    def _build_advanced_tab(self) -> QWidget:
        tab = QWidget()
        form = QFormLayout(tab)

        self.add_dirs_input = QLineEdit()
        self.add_dirs_input.setPlaceholderText("多个目录用 | 分隔")
        form.addRow("附加目录", self.add_dirs_input)

        self.mcp_config_input = QLineEdit()
        btn_mcp = QPushButton("…")
        btn_mcp.setObjectName("compactBtn")
        btn_mcp.setFixedWidth(32)
        btn_mcp.clicked.connect(lambda: self._browse_file(self.mcp_config_input, "MCP JSON"))
        row_mcp = QHBoxLayout()
        row_mcp.addWidget(self.mcp_config_input, 1)
        row_mcp.addWidget(btn_mcp)
        form.addRow("MCP 配置", row_mcp)

        self.settings_path_input = QLineEdit()
        btn_set = QPushButton("…")
        btn_set.setObjectName("compactBtn")
        btn_set.setFixedWidth(32)
        btn_set.clicked.connect(lambda: self._browse_file(self.settings_path_input, "settings.json"))
        row_set = QHBoxLayout()
        row_set.addWidget(self.settings_path_input, 1)
        row_set.addWidget(btn_set)
        form.addRow("Settings", row_set)

        self.fallback_model_input = QLineEdit()
        form.addRow("备用模型", self.fallback_model_input)

        self.debug_input = QLineEdit()
        self.debug_input.setPlaceholderText("api,mcp …")
        form.addRow("Debug", self.debug_input)

        self.max_turns_spin = QSpinBox()
        self.max_turns_spin.setRange(0, 999)
        self.max_turns_spin.setSpecialValueText("不限")
        form.addRow("最大轮数", self.max_turns_spin)

        self.max_budget_input = QLineEdit()
        form.addRow("预算 USD", self.max_budget_input)

        self.extra_args_input = QLineEdit()
        form.addRow("额外参数", self.extra_args_input)

        for ctrl in (
            self.add_dirs_input, self.mcp_config_input, self.settings_path_input,
            self.fallback_model_input, self.debug_input, self.max_budget_input,
            self.extra_args_input,
        ):
            ctrl.textChanged.connect(self._emit_changed)
        self.max_turns_spin.valueChanged.connect(self._emit_changed)
        return tab

    def _build_tools_tab(self) -> QWidget:
        tab = QWidget()
        form = QFormLayout(tab)

        self.tools_input = QLineEdit()
        form.addRow("允许工具", self.tools_input)

        self.allowed_tools_input = QLineEdit()
        form.addRow("自动批准", self.allowed_tools_input)

        self.disallowed_tools_input = QLineEdit()
        form.addRow("禁止工具", self.disallowed_tools_input)

        for ctrl in (self.tools_input, self.allowed_tools_input, self.disallowed_tools_input):
            ctrl.textChanged.connect(self._emit_changed)
        return tab

    def _toggle_advanced(self):
        self._advanced_visible = not self._advanced_visible
        self.advanced_frame.setVisible(self._advanced_visible)
        self.toggle_advanced_btn.setText(
            "▾ 高级 CLI 参数（一般不用改）" if self._advanced_visible
            else "▸ 高级 CLI 参数（一般不用改）"
        )

    def _browse_file(self, target: QLineEdit, caption: str):
        path, _ = QFileDialog.getOpenFileName(self, caption, target.text() or self._work_dir)
        if path:
            target.setText(path)
            self._emit_changed()

    def _on_simple_mode_changed(self):
        mode = str(self.mode_combo.currentData() or "interactive")
        self.mode_hint.setText(_MODE_HINTS.get(mode, ""))
        self.resume_row.setVisible(mode == "resume")
        self._emit_changed()

    def _emit_changed(self):
        self.options_changed.emit()

    def set_work_dir(self, work_dir: str):
        self._work_dir = work_dir.strip()
        summary = load_project_settings_summary(self._work_dir)
        if summary and summary != "（无）":
            self.project_settings_label.setText(f"项目 settings: {summary}")
        else:
            self.project_settings_label.setText("")

    def set_resume_session(self, session_id: str):
        idx = self.mode_combo.findData("resume")
        if idx >= 0:
            self.mode_combo.setCurrentIndex(idx)
        self.resume_id_input.setText(session_id)
        self._emit_changed()

    def set_provider_model_hint(self, model: str):
        idx = self.model_combo.findData("")
        if idx >= 0:
            self.model_combo.setCurrentIndex(idx)
        self._emit_changed()

    def needs_prompt(self) -> bool:
        return str(self.mode_combo.currentData() or "") == "print"

    def get_options(self) -> LaunchOptions:
        add_dirs = [d.strip() for d in self.add_dirs_input.text().split("|") if d.strip()]
        return LaunchOptions(
            mode=str(self.mode_combo.currentData() or "interactive"),
            resume_id=self.resume_id_input.text().strip(),
            session_name=self.session_name_input.text().strip(),
            model=str(self.model_combo.currentData() or ""),
            permission_mode=str(self.permission_combo.currentData() or ""),
            effort=str(self.effort_combo.currentData() or ""),
            add_dirs=add_dirs,
            bare=self.bare_cb.isChecked(),
            safe_mode=self.safe_mode_cb.isChecked(),
            chrome=str(self.chrome_combo.currentData() or "default"),
            verbose=self.verbose_cb.isChecked(),
            debug=self.debug_input.text().strip(),
            allowed_tools=self.allowed_tools_input.text().strip(),
            disallowed_tools=self.disallowed_tools_input.text().strip(),
            tools=self.tools_input.text().strip(),
            max_turns=self.max_turns_spin.value(),
            max_budget_usd=self.max_budget_input.text().strip(),
            worktree=self.worktree_input.text().strip(),
            from_pr=self.from_pr_input.text().strip(),
            fallback_model=self.fallback_model_input.text().strip(),
            mcp_config=self.mcp_config_input.text().strip(),
            settings_path=self.settings_path_input.text().strip(),
            no_session_persistence=self.no_persist_cb.isChecked(),
            fork_session=self.fork_session_cb.isChecked(),
            extra_args=self.extra_args_input.text().strip(),
        )

    def save_to_settings(self):
        save_options_to_settings(self._settings, self.get_options())

    def load_from_settings(self):
        self._apply_options(options_from_settings(self._settings))

    def _apply_options(self, opts: LaunchOptions):
        self._set_combo(self.mode_combo, opts.mode, LAUNCH_MODES, SIMPLE_MODES)
        perm = opts.permission_mode
        if self.permission_combo.findData(perm) < 0:
            perm = ""
        self._set_combo(self.permission_combo, perm, PERMISSION_MODES, SIMPLE_PERMISSIONS)
        self._set_combo(self.model_combo, opts.model)
        self._set_combo(self.effort_combo, opts.effort)
        self._set_combo(self.chrome_combo, opts.chrome)
        self.session_name_input.setText(opts.session_name)
        self.resume_id_input.setText(opts.resume_id)
        self.add_dirs_input.setText("|".join(opts.add_dirs))
        self.safe_mode_cb.setChecked(opts.safe_mode)
        self.bare_cb.setChecked(opts.bare)
        self.verbose_cb.setChecked(opts.verbose)
        self.debug_input.setText(opts.debug)
        self.allowed_tools_input.setText(opts.allowed_tools)
        self.disallowed_tools_input.setText(opts.disallowed_tools)
        self.tools_input.setText(opts.tools)
        self.max_turns_spin.setValue(opts.max_turns)
        self.max_budget_input.setText(opts.max_budget_usd)
        self.worktree_input.setText(opts.worktree)
        self.from_pr_input.setText(opts.from_pr)
        self.fallback_model_input.setText(opts.fallback_model)
        self.mcp_config_input.setText(opts.mcp_config)
        self.settings_path_input.setText(opts.settings_path)
        self.no_persist_cb.setChecked(opts.no_session_persistence)
        self.fork_session_cb.setChecked(opts.fork_session)
        self.extra_args_input.setText(opts.extra_args)
        self._on_simple_mode_changed()

    def _set_combo(self, combo: QComboBox, value: str, *fallback_sources):
        idx = combo.findData(value)
        if idx < 0 and fallback_sources:
            for source in fallback_sources:
                for val, label in source:
                    if val == value:
                        if combo.findData(val) < 0:
                            combo.addItem(label, val)
                        idx = combo.findData(val)
                        break
                if idx >= 0:
                    break
        combo.setCurrentIndex(idx if idx >= 0 else 0)

    def update_cmd_preview(self, base_argv: list, prompt: str = ""):
        self.cmd_preview.setText(self.get_options().preview_cmdline(base_argv, prompt))


class QuickActionsWidget(QWidget):
    """次要工具 — 折叠区使用。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        hint = QLabel("在外部 CMD 打开，不影响中间的内嵌终端。")
        hint.setWordWrap(True)
        hint.setObjectName("hintLabel")
        layout.addWidget(hint)

        row1 = QHBoxLayout()
        self.auth_btn = QPushButton("登录状态")
        self.update_btn = QPushButton("检查更新")
        row1.addWidget(self.auth_btn)
        row1.addWidget(self.update_btn)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        self.mcp_btn = QPushButton("MCP 管理")
        self.agents_btn = QPushButton("Agents")
        row2.addWidget(self.mcp_btn)
        row2.addWidget(self.agents_btn)
        layout.addLayout(row2)

        self.resume_btn = QPushButton("用右侧选中的会话恢复")
        layout.addWidget(self.resume_btn)
