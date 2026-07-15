#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全局 UI 主题与样式。"""

APP_STYLESHEET = """
QMainWindow, QWidget {
    background-color: #11111b;
    color: #cdd6f4;
    font-size: 9pt;
}
QWidget#sidebar {
    background-color: #181825;
    border-radius: 12px;
}
QWidget#launchBar {
    background-color: #1e1e2e;
    border-radius: 10px;
    border: 1px solid #313244;
}
QWidget#card {
    background-color: #1e1e2e;
    border: 1px solid #313244;
    border-radius: 10px;
}
QWidget#guideBar {
    background-color: #11111b;
    border: 1px solid #313244;
    border-radius: 8px;
}
QLabel#titleLabel {
    font-size: 15pt;
    font-weight: bold;
    color: #cba6f7;
}
QLabel#stepLabel {
    color: #89b4fa;
    font-weight: bold;
    font-size: 9pt;
}
QLabel#stepHint {
    color: #6c7086;
    font-size: 8pt;
}
QLabel#subLabel, QLabel#hintLabel {
    color: #6c7086;
    font-size: 8pt;
}
QLabel#badgeOk {
    color: #a6e3a1;
    background-color: #1e2e24;
    border: 1px solid #3d5a44;
    border-radius: 6px;
    padding: 4px 8px;
    font-size: 8pt;
}
QLabel#sectionTitle {
    color: #bac2de;
    font-weight: bold;
    font-size: 9pt;
}
QGroupBox {
    border: 1px solid #313244;
    border-radius: 10px;
    margin-top: 8px;
    padding: 12px 10px 10px 10px;
    background-color: #1e1e2e;
    font-weight: bold;
    color: #89b4fa;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
}
QLineEdit, QTextEdit {
    background-color: #11111b;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 8px;
    padding: 7px 10px;
    selection-background-color: #45475a;
}
QLineEdit:focus, QTextEdit:focus {
    border: 1px solid #89b4fa;
}
QLineEdit#cmdPreview {
    color: #9399b2;
    font-size: 8pt;
    padding: 5px 8px;
    background-color: #181825;
}
QPushButton {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 8px;
    padding: 8px 14px;
}
QPushButton:hover {
    background-color: #45475a;
    border-color: #585b70;
}
QPushButton:pressed {
    background-color: #585b70;
}
QPushButton#primaryBtn {
    background-color: #a6e3a1;
    color: #11111b;
    border: none;
    font-size: 11pt;
    font-weight: bold;
    padding: 12px 16px;
    min-height: 20px;
}
QPushButton#primaryBtn:hover {
    background-color: #b8f0b4;
}
QPushButton#primaryBtn:disabled {
    background-color: #45475a;
    color: #6c7086;
}
QPushButton#secondaryBtn {
    background-color: transparent;
    color: #89b4fa;
    border: 1px solid #45475a;
    padding: 7px 12px;
}
QPushButton#ghostBtn {
    background-color: transparent;
    color: #6c7086;
    border: none;
    padding: 4px 8px;
    font-weight: normal;
}
QPushButton#ghostBtn:hover {
    color: #cdd6f4;
    background-color: #313244;
}
QPushButton#dangerBtn {
    background-color: #452636;
    color: #f38ba8;
    border: 1px solid #663344;
}
QPushButton#dangerBtn:hover {
    background-color: #5c3040;
}
QPushButton#compactBtn {
    padding: 6px 10px;
    min-width: 28px;
}
QPushButton#toggleBtn {
    text-align: left;
    padding: 8px 10px;
    background-color: transparent;
    border: 1px dashed #45475a;
    color: #a6adc8;
    font-weight: normal;
}
QPushButton#toggleBtn:hover {
    border-color: #89b4fa;
    color: #cdd6f4;
}
QStatusBar {
    background-color: #11111b;
    color: #7f849c;
    border-top: 1px solid #313244;
}
QTabWidget::pane {
    border: 1px solid #313244;
    border-radius: 8px;
    background: #1e1e2e;
    top: -1px;
}
QTabBar::tab {
    background: #181825;
    color: #7f849c;
    padding: 7px 14px;
    margin-right: 2px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
}
QTabBar::tab:selected {
    background: #313244;
    color: #cdd6f4;
}
QListWidget, QTreeWidget {
    background-color: #11111b;
    color: #cdd6f4;
    border: 1px solid #313244;
    border-radius: 8px;
    outline: none;
}
QListWidget::item {
    padding: 6px 8px;
    border-radius: 4px;
}
QListWidget::item:selected {
    background-color: #313244;
}
QTreeWidget::item:selected {
    background-color: #313244;
}
QComboBox {
    background-color: #11111b;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 8px;
    padding: 7px 10px;
    min-height: 18px;
}
QComboBox:focus {
    border-color: #89b4fa;
}
QComboBox::drop-down {
    border: none;
    width: 24px;
}
QComboBox QAbstractItemView {
    background-color: #1e1e2e;
    border: 1px solid #45475a;
    selection-background-color: #45475a;
}
QSpinBox {
    background-color: #11111b;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 8px;
    padding: 5px 8px;
}
QCheckBox {
    color: #bac2de;
    spacing: 6px;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 1px solid #585b70;
    background: #11111b;
}
QCheckBox::indicator:checked {
    background: #89b4fa;
    border-color: #89b4fa;
}
QScrollArea {
    border: none;
    background: transparent;
}
QMenu {
    background-color: #1e1e2e;
    border: 1px solid #45475a;
    border-radius: 8px;
    padding: 4px;
}
QMenu::item {
    padding: 8px 24px 8px 12px;
    border-radius: 4px;
}
QMenu::item:selected {
    background-color: #313244;
}
QSplitter::handle {
    background-color: #313244;
    width: 2px;
}
"""
