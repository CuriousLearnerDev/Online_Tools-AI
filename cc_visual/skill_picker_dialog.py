#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Skills 多选对话框 — 供一键导入时选择性同步。"""

from __future__ import annotations

from typing import Dict, List, Optional, Set

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from claude_hexstrike_bridge import skill_ids_for_packs


def recommended_skill_ids(all_skills: List[Dict[str, str]]) -> Set[str]:
    """按渗透/信息搜集场景推荐 Skill id。"""
    packs = ["01-信息搜集-Reconnaissance", "hexstrike-ce/web-recon", "hexstrike-ce"]
    rec_ids = set(skill_ids_for_packs(all_skills, packs))
    for sk in all_skills:
        blob = f"{sk.get('id', '')} {sk.get('pack', '')} {sk.get('name', '')}".lower()
        if any(
            k in blob
            for k in ("web-recon", "recon", "osint", "信息搜集", "subfinder", "httpx", "nmap")
        ):
            rec_ids.add(sk["id"])
    return rec_ids


class SkillPickerDialog(QDialog):
    """勾选要同步到 .claude/skills/ 的 Skills。"""

    def __init__(
        self,
        all_skills: List[Dict[str, str]],
        parent=None,
        *,
        preselect_recommended: bool = True,
    ):
        super().__init__(parent)
        self._all_skills = list(all_skills)
        self._selected: List[Dict[str, str]] = []
        self.setWindowTitle("选择要导入的 Skills")
        self.resize(560, 480)
        self._build_ui()
        self._reload_packs()
        if preselect_recommended:
            self._apply_recommended()

    def selected_skills(self) -> List[Dict[str, str]]:
        return list(self._selected)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(8)

        hint = QLabel(
            "勾选要同步到 claude-code/.claude/skills/ 的技能。"
            " 导入后请重新启动 Claude Code 终端。"
        )
        hint.setWordWrap(True)
        hint.setObjectName("hintLabel")
        root.addWidget(hint)

        pack_row = QHBoxLayout()
        pack_row.addWidget(QLabel("技能包"))
        self.pack_combo = QComboBox()
        self.pack_combo.currentIndexChanged.connect(self._on_pack_changed)
        pack_row.addWidget(self.pack_combo, 1)
        rec_btn = QPushButton("推荐")
        rec_btn.setObjectName("secondaryBtn")
        rec_btn.clicked.connect(self._apply_recommended)
        pack_row.addWidget(rec_btn)
        all_btn = QPushButton("全选")
        all_btn.setObjectName("secondaryBtn")
        all_btn.clicked.connect(lambda: self._set_all(True))
        pack_row.addWidget(all_btn)
        none_btn = QPushButton("全不选")
        none_btn.setObjectName("secondaryBtn")
        none_btn.clicked.connect(lambda: self._set_all(False))
        pack_row.addWidget(none_btn)
        root.addLayout(pack_row)

        self.skill_list = QListWidget()
        self.skill_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.skill_list.itemChanged.connect(lambda _item: self._update_count())
        root.addWidget(self.skill_list, 1)

        self.count_label = QLabel("")
        self.count_label.setObjectName("hintLabel")
        root.addWidget(self.count_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _reload_packs(self):
        self.pack_combo.blockSignals(True)
        self.pack_combo.clear()
        self.pack_combo.addItem("全部技能包", "")
        packs = sorted({sk.get("pack") or "" for sk in self._all_skills if sk.get("pack")})
        for pack in packs:
            self.pack_combo.addItem(pack, pack)
        self.pack_combo.blockSignals(False)
        self._populate_list("")

    def _on_pack_changed(self, _idx: int):
        pack = self.pack_combo.currentData()
        self._populate_list(str(pack or ""))

    def _populate_list(self, filter_pack: str):
        checked_ids = self._checked_ids()
        self.skill_list.clear()
        fp = (filter_pack or "").strip().lower()
        for sk in self._all_skills:
            pack = sk.get("pack") or ""
            if fp and pack.lower() != fp:
                continue
            item = QListWidgetItem(f"{sk.get('name', '?')}  [{pack}]")
            item.setData(int(Qt.ItemDataRole.UserRole), sk.get("id"))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            sid = sk.get("id")
            item.setCheckState(
                Qt.CheckState.Checked if sid in checked_ids else Qt.CheckState.Unchecked
            )
            self.skill_list.addItem(item)
        self._update_count()

    def _checked_ids(self) -> Set[str]:
        ids: Set[str] = set()
        for i in range(self.skill_list.count()):
            item = self.skill_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                sid = item.data(int(Qt.ItemDataRole.UserRole))
                if sid:
                    ids.add(str(sid))
        return ids

    def _set_all(self, checked: bool):
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for i in range(self.skill_list.count()):
            self.skill_list.item(i).setCheckState(state)
        self._update_count()

    def _apply_recommended(self):
        rec_ids = recommended_skill_ids(self._all_skills)
        if not rec_ids:
            QMessageBox.information(self, "推荐 Skills", "未找到匹配的推荐技能，请手动勾选。")
            return
        fp = str(self.pack_combo.currentData() or "")
        self._populate_list(fp)
        for i in range(self.skill_list.count()):
            item = self.skill_list.item(i)
            sid = item.data(int(Qt.ItemDataRole.UserRole))
            item.setCheckState(
                Qt.CheckState.Checked if sid in rec_ids else Qt.CheckState.Unchecked
            )
        self._update_count()

    def _collect_selected(self) -> List[Dict[str, str]]:
        by_id = {sk["id"]: sk for sk in self._all_skills}
        out: List[Dict[str, str]] = []
        for i in range(self.skill_list.count()):
            item = self.skill_list.item(i)
            if item.checkState() != Qt.CheckState.Checked:
                continue
            sid = item.data(int(Qt.ItemDataRole.UserRole))
            if sid in by_id:
                out.append(by_id[sid])
        return out

    def _update_count(self):
        n = len(self._collect_selected())
        self.count_label.setText(f"已勾选 {n} 个 Skill")

    def _on_accept(self):
        self._selected = self._collect_selected()
        if not self._selected:
            QMessageBox.warning(self, "未选择", "请至少勾选一个 Skill，或点「取消」。")
            return
        self.accept()
