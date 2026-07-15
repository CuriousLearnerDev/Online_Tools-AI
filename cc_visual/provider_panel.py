#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""模型/提供商切换面板（cc-switch 风格）。"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from provider_manager import (
    ProviderProfile,
    delete_custom_provider,
    detect_matching_provider_id,
    get_active_provider_id,
    import_from_claude_settings,
    list_all_providers,
    mark_active_provider,
    read_live_env,
    resolve_env_for_test,
    save_custom_provider,
    set_active_provider,
    test_provider_api,
)


class ProviderEditDialog(QDialog):
    def __init__(self, profile: ProviderProfile | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("编辑提供商" if profile else "添加提供商")
        self.setMinimumWidth(420)
        self._profile = profile

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.name_input = QLineEdit(profile.name if profile else "")
        self.name_input.setPlaceholderText("如：我的 DeepSeek / 公司网关")
        form.addRow("名称:", self.name_input)

        self.base_url_input = QLineEdit((profile.env.get("ANTHROPIC_BASE_URL") if profile else ""))
        self.base_url_input.setPlaceholderText("https://api.example.com/anthropic")
        form.addRow("API 地址:", self.base_url_input)

        self.token_input = QLineEdit()
        token = ""
        if profile:
            token = profile.env.get("ANTHROPIC_AUTH_TOKEN") or profile.env.get("ANTHROPIC_API_KEY") or ""
        self.token_input.setText(token)
        self.token_input.setPlaceholderText("sk-…（ANTHROPIC_AUTH_TOKEN）")
        self.token_input.setEchoMode(QLineEdit.EchoMode.Password)
        token_row = QHBoxLayout()
        token_row.addWidget(self.token_input, 1)
        self.test_key_btn = QPushButton("测试 Key")
        self.test_key_btn.setObjectName("secondaryBtn")
        self.test_key_btn.clicked.connect(self._test_api_key)
        token_row.addWidget(self.test_key_btn)
        form.addRow("API Key:", token_row)

        self.model_input = QLineEdit((profile.env.get("ANTHROPIC_MODEL") if profile else ""))
        self.model_input.setPlaceholderText("如 deepseek-v4-pro")
        form.addRow("主模型:", self.model_input)

        self.sonnet_input = QLineEdit((profile.env.get("ANTHROPIC_DEFAULT_SONNET_MODEL") if profile else ""))
        form.addRow("Sonnet 别名:", self.sonnet_input)

        self.opus_input = QLineEdit((profile.env.get("ANTHROPIC_DEFAULT_OPUS_MODEL") if profile else ""))
        form.addRow("Opus 别名:", self.opus_input)

        self.haiku_input = QLineEdit((profile.env.get("ANTHROPIC_DEFAULT_HAIKU_MODEL") if profile else ""))
        form.addRow("Haiku 别名:", self.haiku_input)

        self.notes_input = QTextEdit(profile.notes if profile else "")
        self.notes_input.setMaximumHeight(60)
        form.addRow("备注:", self.notes_input)

        layout.addLayout(form)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def build_profile(self) -> ProviderProfile:
        env = {}
        mapping = [
            ("ANTHROPIC_BASE_URL", self.base_url_input.text()),
            ("ANTHROPIC_AUTH_TOKEN", self.token_input.text()),
            ("ANTHROPIC_MODEL", self.model_input.text()),
            ("ANTHROPIC_DEFAULT_SONNET_MODEL", self.sonnet_input.text()),
            ("ANTHROPIC_DEFAULT_OPUS_MODEL", self.opus_input.text()),
            ("ANTHROPIC_DEFAULT_HAIKU_MODEL", self.haiku_input.text()),
        ]
        for key, val in mapping:
            if val.strip():
                env[key] = val.strip()
        return ProviderProfile(
            id=self._profile.id if self._profile else "",
            name=self.name_input.text().strip() or "未命名",
            env=env,
            model_hint=self.model_input.text().strip(),
            notes=self.notes_input.toPlainText().strip(),
            builtin=False,
        )

    def _test_api_key(self):
        env_override = {}
        mapping = [
            ("ANTHROPIC_BASE_URL", self.base_url_input.text()),
            ("ANTHROPIC_AUTH_TOKEN", self.token_input.text()),
            ("ANTHROPIC_MODEL", self.model_input.text()),
            ("ANTHROPIC_DEFAULT_HAIKU_MODEL", self.haiku_input.text()),
        ]
        for key, val in mapping:
            if val.strip():
                env_override[key] = val.strip()
        provider_id = self._profile.id if self._profile else ""
        env = resolve_env_for_test(provider_id=provider_id, env_override=env_override or None)
        self.test_key_btn.setEnabled(False)
        self.test_key_btn.setText("测试中…")
        try:
            ok, message, _meta = test_provider_api(env)
            if ok:
                QMessageBox.information(self, "Key 有效", message)
            else:
                QMessageBox.warning(self, "Key 无效", message)
        finally:
            self.test_key_btn.setEnabled(True)
            self.test_key_btn.setText("测试 Key")


class ProviderPanel(QWidget):
    """快速切换 Claude Code API 提供商。"""

    provider_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self._providers: list[ProviderProfile] = []
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        self.badge_label = QLabel("正在读取…")
        self.badge_label.setObjectName("badgeOk")
        self.badge_label.setWordWrap(True)
        layout.addWidget(self.badge_label)

        self.provider_combo = QComboBox()
        layout.addWidget(self.provider_combo)

        row = QHBoxLayout()
        row.setSpacing(6)
        self.activate_btn = QPushButton("应用此模型")
        self.activate_btn.setToolTip("写入 ~/.claude/settings.json，然后重新启动终端")
        self.activate_btn.clicked.connect(self._activate_selected)
        row.addWidget(self.activate_btn, 1)

        self.edit_btn = QPushButton("编辑")
        self.edit_btn.setObjectName("secondaryBtn")
        self.edit_btn.clicked.connect(self._edit_provider)
        row.addWidget(self.edit_btn)

        self.test_btn = QPushButton("测试 Key")
        self.test_btn.setObjectName("secondaryBtn")
        self.test_btn.setToolTip("验证当前选中提供商的 API Key")
        self.test_btn.clicked.connect(self._test_selected_key)
        row.addWidget(self.test_btn)

        self.more_btn = QPushButton("⋯")
        self.more_btn.setObjectName("compactBtn")
        self.more_btn.setFixedWidth(36)
        menu = QMenu(self)
        menu.addAction("添加自定义", self._add_provider)
        menu.addAction("从 settings 导入", self._import_current)
        menu.addAction("删除自定义", self._delete_provider)
        self.more_btn.setMenu(menu)
        row.addWidget(self.more_btn)
        layout.addLayout(row)

    def refresh(self):
        self._providers = list_all_providers()
        active_id = get_active_provider_id()
        live = read_live_env()

        self.provider_combo.blockSignals(True)
        self.provider_combo.clear()
        active_idx = 0
        for i, p in enumerate(self._providers):
            label = p.name
            if p.id == active_id:
                label = f"✓ {p.name}"
            self.provider_combo.addItem(label, p.id)
            if p.id == active_id:
                active_idx = i
        if self.provider_combo.count():
            self.provider_combo.setCurrentIndex(active_idx)
        self.provider_combo.blockSignals(False)

        base = live.get("ANTHROPIC_BASE_URL", "")
        model = live.get("ANTHROPIC_MODEL", "")
        parts = [p.name for p in self._providers if p.id == active_id]
        name = parts[0] if parts else active_id
        if base:
            host = base.replace("https://", "").split("/")[0]
            detail = f"{host} · {model}" if model else host
        elif model:
            detail = model
        else:
            detail = "官方 API"
        self.badge_label.setText(f"当前生效：{name}  ·  {detail}")

    def _selected_id(self) -> str | None:
        pid = self.provider_combo.currentData()
        return str(pid) if pid else None

    def _selected_profile(self) -> ProviderProfile | None:
        pid = self._selected_id()
        if not pid:
            return None
        for p in self._providers:
            if p.id == pid:
                return p
        return None

    def _activate_selected(self):
        pid = self._selected_id()
        if not pid:
            QMessageBox.information(self, "提示", "请先选择一个提供商")
            return
        profile = self._selected_profile()
        if (
            profile
            and profile.builtin
            and profile.id != "official"
            and not profile.env.get("ANTHROPIC_AUTH_TOKEN")
            and not read_live_env().get("ANTHROPIC_AUTH_TOKEN")
        ):
            dlg = ProviderEditDialog(profile, self)
            dlg.setWindowTitle(f"填写 {profile.name} 的 API Key")
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return
            edited = dlg.build_profile()
            from provider_manager import apply_provider_to_claude_settings

            ok, msg = apply_provider_to_claude_settings(edited, preserve_token=False)
            if not ok:
                QMessageBox.critical(self, "切换失败", msg)
                return
            mark_active_provider(profile.id)
            self.refresh()
            self.provider_changed.emit(profile.id)
            QMessageBox.information(self, "已启用", f"{profile.name}\n\n请重新启动终端。")
            return

        ok, msg = set_active_provider(pid)
        if ok:
            self.refresh()
            self.provider_changed.emit(pid)
            QMessageBox.information(self, "已启用", f"{msg}\n\n请重新启动终端。")
        else:
            QMessageBox.critical(self, "切换失败", msg)

    def _test_selected_key(self):
        profile = self._selected_profile()
        if not profile:
            QMessageBox.information(self, "提示", "请先选择一个提供商")
            return
        env = resolve_env_for_test(provider_id=profile.id)
        self.test_btn.setEnabled(False)
        self.test_btn.setText("测试中…")
        try:
            ok, message, _meta = test_provider_api(env)
            if ok:
                QMessageBox.information(self, "Key 有效", message)
            else:
                QMessageBox.warning(self, "Key 无效", message)
        finally:
            self.test_btn.setEnabled(True)
            self.test_btn.setText("测试 Key")

    def _add_provider(self):
        dlg = ProviderEditDialog(None, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        profile = save_custom_provider(dlg.build_profile())
        self.refresh()
        idx = self.provider_combo.findData(profile.id)
        if idx >= 0:
            self.provider_combo.setCurrentIndex(idx)

    def _edit_provider(self):
        profile = self._selected_profile()
        if not profile:
            QMessageBox.information(self, "提示", "请先选择一项")
            return
        if profile.builtin and profile.id == "official":
            QMessageBox.information(self, "提示", "官方预设不可编辑，直接「启用」即可")
            return
        if profile.builtin:
            from provider_manager import apply_provider_to_claude_settings

            dlg = ProviderEditDialog(profile, self)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return
            edited = dlg.build_profile()
            ok, msg = apply_provider_to_claude_settings(edited)
            if ok:
                mark_active_provider(profile.id)
                self.refresh()
                self.provider_changed.emit(profile.id)
                QMessageBox.information(self, "已应用", "参数已写入 settings.json")
            else:
                QMessageBox.critical(self, "失败", msg)
            return
        dlg = ProviderEditDialog(profile, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        updated = dlg.build_profile()
        updated.id = profile.id
        save_custom_provider(updated)
        self.refresh()

    def _delete_provider(self):
        profile = self._selected_profile()
        if not profile:
            QMessageBox.information(self, "提示", "请先选择一项")
            return
        if profile.builtin:
            QMessageBox.information(self, "提示", "内置预设不能删除")
            return
        if (
            QMessageBox.question(self, "确认", f"删除「{profile.name}」？")
            != QMessageBox.StandardButton.Yes
        ):
            return
        delete_custom_provider(profile.id)
        self.refresh()

    def _import_current(self):
        profile = import_from_claude_settings()
        self.refresh()
        idx = self.provider_combo.findData(profile.id)
        if idx >= 0:
            self.provider_combo.setCurrentIndex(idx)
        QMessageBox.information(self, "已导入", f"已保存为「{profile.name}」")

    def sync_active_from_live(self):
        matched = detect_matching_provider_id()
        if matched:
            mark_active_provider(matched)
        self.refresh()
