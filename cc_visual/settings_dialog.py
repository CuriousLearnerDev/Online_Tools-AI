#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""启动与工作目录设置。"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from claude_launcher import CLAUDE_DIR, DEFAULT_PROXY
from launch_options_widget import LaunchOptionsWidget


class SettingsPanel(QWidget):
    """工作目录、代理、启动方式。"""

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self._settings = settings
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(16)

        layout.addWidget(self._section_title("工作目录"))
        dir_card = QWidget()
        dir_card.setObjectName("card")
        dir_layout = QVBoxLayout(dir_card)
        dir_layout.setContentsMargins(12, 10, 12, 10)
        dir_layout.setSpacing(8)

        wd_row = QHBoxLayout()
        self.workdir_input = QLineEdit(CLAUDE_DIR)
        self.workdir_input.setPlaceholderText("Claude 在哪个文件夹里工作")
        wd_row.addWidget(self.workdir_input, 1)
        self.browse_btn = QPushButton("浏览…")
        self.browse_btn.setObjectName("secondaryBtn")
        self.browse_btn.setFixedWidth(64)
        wd_row.addWidget(self.browse_btn)
        dir_layout.addLayout(wd_row)

        form = QFormLayout()
        form.setSpacing(8)
        self.proxy_input = QLineEdit(DEFAULT_PROXY)
        self.proxy_input.setPlaceholderText("不需要可留空")
        form.addRow("网络代理", self.proxy_input)
        dir_layout.addLayout(form)
        layout.addWidget(dir_card)

        layout.addWidget(self._section_title("怎么启动"))
        launch_card = QWidget()
        launch_card.setObjectName("card")
        launch_card_layout = QVBoxLayout(launch_card)
        launch_card_layout.setContentsMargins(12, 10, 12, 10)
        launch_card_layout.setSpacing(10)

        self.launch_options = LaunchOptionsWidget(self._settings)
        launch_card_layout.addWidget(self.launch_options)

        self.prompt_box = QWidget()
        prompt_layout = QVBoxLayout(self.prompt_box)
        prompt_layout.setContentsMargins(0, 0, 0, 0)
        prompt_layout.setSpacing(4)
        prompt_layout.addWidget(QLabel("要问的问题（单次提问模式必填）"))
        self.prompt_input = QTextEdit()
        self.prompt_input.setPlaceholderText("例如：帮我检查这个项目的 README 有没有错别字")
        self.prompt_input.setMaximumHeight(72)
        prompt_layout.addWidget(self.prompt_input)
        self.prompt_box.hide()
        launch_card_layout.addWidget(self.prompt_box)

        layout.addWidget(launch_card)
        layout.addStretch()

        self.launch_options.options_changed.connect(self.sync_prompt_visibility)
        self.browse_btn.clicked.connect(self._browse_workdir)

    def _browse_workdir(self):
        d = QFileDialog.getExistingDirectory(self.window(), "工作目录", self.workdir_input.text())
        if d:
            self.workdir_input.setText(d)

    @staticmethod
    def _section_title(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("stepLabel")
        return label

    def sync_prompt_visibility(self):
        self.prompt_box.setVisible(self.launch_options.needs_prompt())


class SettingsDialog(QDialog):
    def __init__(self, panel: SettingsPanel, home: QWidget, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setMinimumSize(420, 520)
        self.resize(460, 580)
        self._panel = panel
        self._home = home

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)

        hint = QLabel("工作目录、代理和启动方式在这里配置，平时不用改。")
        hint.setWordWrap(True)
        hint.setObjectName("hintLabel")
        root.addWidget(hint)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(panel)
        root.addWidget(scroll, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self.finished.connect(self._return_panel_home)

    def _return_panel_home(self):
        if self._panel is not None and self._home is not None:
            self._panel.setParent(self._home)
            self._panel.hide()
