#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Claude Code 活动可视化：会话、执行记录、任务、Git 状态。"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from claude_session import (
    ActivityEvent,
    SessionInfo,
    git_short_status,
    list_sessions,
    load_recent_history,
    load_session_tasks,
    parse_session_activities,
)

_KIND_LABEL = {
    "user": "用户",
    "assistant": "Claude",
    "tool": "工具",
    "error": "错误",
    "file": "文件",
    "system": "系统",
    "other": "其他",
}

_KIND_COLOR = {
    "user": "#89b4fa",
    "assistant": "#cba6f7",
    "tool": "#a6e3a1",
    "error": "#f38ba8",
    "file": "#fab387",
    "system": "#94a3b8",
    "other": "#6c7086",
}


class ActivityPanel(QWidget):
    """右侧活动面板：会话历史 + 执行时间线 + 任务 + Git。"""

    resume_session = pyqtSignal(str)

    def __init__(self, parent=None, *, show_header: bool = True):
        super().__init__(parent)
        self._work_dir = ""
        self._current_session: Optional[SessionInfo] = None
        self._show_header = show_header
        self._build_ui()

        self._watch_timer = QTimer(self)
        self._watch_timer.setInterval(3000)
        self._watch_timer.timeout.connect(self.refresh)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.setObjectName("secondaryBtn")
        self.refresh_btn.setFixedWidth(56)
        self.refresh_btn.clicked.connect(self.refresh)
        if self._show_header:
            header = QHBoxLayout()
            title = QLabel("活动")
            title.setObjectName("sectionTitle")
            header.addWidget(title)
            header.addStretch()
            header.addWidget(self.refresh_btn)
            root.addLayout(header)
        else:
            top = QHBoxLayout()
            top.addStretch()
            top.addWidget(self.refresh_btn)
            root.addLayout(top)

        self.summary_label = QLabel("跟随左侧工作目录自动加载")
        self.summary_label.setObjectName("hintLabel")
        self.summary_label.setWordWrap(True)
        root.addWidget(self.summary_label)

        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)

        # --- 会话 ---
        sess_tab = QWidget()
        sess_layout = QVBoxLayout(sess_tab)
        self.session_list = QListWidget()
        self.session_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.session_list.currentItemChanged.connect(self._on_session_selected)
        self.resume_session_btn = QPushButton("恢复此会话")
        self.resume_session_btn.setObjectName("secondaryBtn")
        self.resume_session_btn.clicked.connect(self._emit_resume)
        sess_layout.addWidget(self.resume_session_btn)
        sess_layout.addWidget(self.session_list)
        self.tabs.addTab(sess_tab, "会话")

        # --- 执行记录 ---
        act_tab = QWidget()
        act_layout = QVBoxLayout(act_tab)
        split = QSplitter(Qt.Orientation.Vertical)

        self.activity_tree = QTreeWidget()
        self.activity_tree.setHeaderLabels(["时间", "类型", "内容"])
        self.activity_tree.setColumnWidth(0, 72)
        self.activity_tree.setColumnWidth(1, 56)
        self.activity_tree.setRootIsDecorated(False)
        self.activity_tree.setAlternatingRowColors(True)
        self.activity_tree.itemSelectionChanged.connect(self._on_activity_selected)
        split.addWidget(self.activity_tree)

        self.detail_view = QTextEdit()
        self.detail_view.setReadOnly(True)
        self.detail_view.setPlaceholderText("选中一条记录查看详情（命令、文件路径、输出等）")
        mono = QFont("Consolas", 9)
        self.detail_view.setFont(mono)
        split.addWidget(self.detail_view)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        act_layout.addWidget(split)
        self.tabs.addTab(act_tab, "执行记录")

        # --- 任务 ---
        task_tab = QWidget()
        task_layout = QVBoxLayout(task_tab)
        self.task_list = QListWidget()
        task_layout.addWidget(self.task_list)
        self.tabs.addTab(task_tab, "任务")

        # --- Git ---
        git_tab = QWidget()
        git_layout = QVBoxLayout(git_tab)
        self.git_view = QTextEdit()
        self.git_view.setReadOnly(True)
        self.git_view.setFont(QFont("Consolas", 9))
        git_layout.addWidget(self.git_view)
        self.tabs.addTab(git_tab, "Git")

        # --- 历史输入 ---
        hist_tab = QWidget()
        hist_layout = QVBoxLayout(hist_tab)
        self.history_list = QListWidget()
        hist_layout.addWidget(self.history_list)
        self.tabs.addTab(hist_tab, "历史输入")

    def set_work_dir(self, work_dir: str):
        self._work_dir = work_dir.strip()
        self.refresh()

    def start_watching(self):
        self._watch_timer.start()

    def stop_watching(self):
        self._watch_timer.stop()

    def refresh(self):
        if not self._work_dir:
            return

        sessions = list_sessions(self._work_dir)
        self.session_list.clear()
        for s in sessions:
            item = QListWidgetItem(f"{s.modified_text}  {s.title}")
            item.setData(Qt.ItemDataRole.UserRole, s)
            self.session_list.addItem(item)

        self.summary_label.setText(
            f"工作目录: {self._work_dir}\n"
            f"找到 {len(sessions)} 个会话 · 数据来自 ~/.claude/projects/"
        )

        # 历史输入
        self.history_list.clear()
        for row in load_recent_history(self._work_dir, limit=40):
            ts = row.get("timestamp", 0)
            try:
                from datetime import datetime
                t = datetime.fromtimestamp(ts / 1000).strftime("%m-%d %H:%M") if ts else ""
            except Exception:
                t = ""
            text = str(row.get("display", "")).replace("\n", " ")[:100]
            self.history_list.addItem(f"{t}  {text}")

        # Git
        status = git_short_status(self._work_dir)
        self.git_view.setPlainText(status or "（非 Git 仓库或无变更）")

        # 自动选中最新会话
        if self.session_list.count() > 0 and not self._current_session:
            self.session_list.setCurrentRow(0)

    def _emit_resume(self):
        if not self._current_session:
            return
        self.resume_session.emit(self._current_session.session_id)

    def _on_session_selected(self, current: QListWidgetItem, _previous):
        if not current:
            return
        session = current.data(Qt.ItemDataRole.UserRole)
        if not isinstance(session, SessionInfo):
            return
        self._current_session = session
        self._load_activities(session)
        self._load_tasks(session.session_id)

    def _load_activities(self, session: SessionInfo):
        self.activity_tree.clear()
        self.detail_view.clear()
        events = parse_session_activities(session.path)
        for ev in events:
            time_str = ev.timestamp.strftime("%H:%M:%S") if ev.timestamp else ""
            kind_label = _KIND_LABEL.get(ev.kind, ev.kind)
            item = QTreeWidgetItem([time_str, kind_label, ev.title])
            item.setData(0, Qt.ItemDataRole.UserRole, ev)
            color = QColor(_KIND_COLOR.get(ev.kind, "#cdd6f4"))
            for col in range(3):
                item.setForeground(col, color)
            self.activity_tree.addTopLevelItem(item)

        if not events:
            item = QTreeWidgetItem(["", "提示", "此会话暂无工具执行记录（可能只有对话或 API 错误）"])
            self.activity_tree.addTopLevelItem(item)

    def _load_tasks(self, session_id: str):
        self.task_list.clear()
        tasks = load_session_tasks(session_id)
        if not tasks:
            self.task_list.addItem("（此会话无任务列表）")
            return
        for t in tasks:
            status = t.get("status", "")
            subj = t.get("subject", t.get("id", ""))
            icon = {"completed": "✓", "in_progress": "●", "pending": "○"}.get(status, "·")
            self.task_list.addItem(f"{icon} [{status}] {subj}")

    def _on_activity_selected(self):
        items = self.activity_tree.selectedItems()
        if not items:
            return
        ev = items[0].data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(ev, ActivityEvent):
            return
        header = f"类型: {_KIND_LABEL.get(ev.kind, ev.kind)}"
        if ev.tool_name:
            header += f"  |  工具: {ev.tool_name}"
        if ev.timestamp:
            header += f"  |  {ev.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
        self.detail_view.setPlainText(f"{header}\n\n{ev.detail or ev.title}")
