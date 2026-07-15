#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Claude Code 官方 CLI 参数封装（对应 code.claude.com/docs/zh-CN/cli-reference）。"""

from __future__ import annotations

import json
import os
import shlex
from dataclasses import dataclass, field, replace
from typing import List, Optional

# 官方文档中的常用枚举
LAUNCH_MODES = [
    ("interactive", "交互式（默认）"),
    ("continue", "继续上次会话 (-c)"),
    ("resume", "恢复指定会话 (-r)"),
    ("print", "非交互 / 打印模式 (-p)"),
]

MODELS = [
    ("", "默认（使用 settings）"),
    ("sonnet", "sonnet"),
    ("opus", "opus"),
    ("haiku", "haiku"),
    ("fable", "fable"),
]

PERMISSION_MODES = [
    ("", "默认（使用 settings）"),
    ("default", "default"),
    ("acceptEdits", "acceptEdits — 自动接受编辑"),
    ("plan", "plan — 仅规划"),
    ("auto", "auto"),
    ("dontAsk", "dontAsk — 不询问"),
    ("bypassPermissions", "bypassPermissions — 跳过权限"),
]

EFFORT_LEVELS = [
    ("", "默认"),
    ("low", "low"),
    ("medium", "medium"),
    ("high", "high"),
    ("xhigh", "xhigh"),
    ("max", "max"),
]

CHROME_OPTIONS = [
    ("default", "默认"),
    ("on", "启用 (--chrome)"),
    ("off", "禁用 (--no-chrome)"),
]


@dataclass
class LaunchOptions:
    """GUI 可配置的 Claude Code 启动选项。"""

    mode: str = "interactive"
    resume_id: str = ""
    session_name: str = ""
    model: str = ""
    permission_mode: str = ""
    effort: str = ""
    add_dirs: List[str] = field(default_factory=list)
    bare: bool = False
    safe_mode: bool = False
    chrome: str = "default"
    verbose: bool = False
    debug: str = ""
    allowed_tools: str = ""
    disallowed_tools: str = ""
    tools: str = ""
    max_turns: int = 0
    max_budget_usd: str = ""
    worktree: str = ""
    from_pr: str = ""
    fallback_model: str = ""
    mcp_config: str = ""
    settings_path: str = ""
    no_session_persistence: bool = False
    fork_session: bool = False
    extra_args: str = ""
    skip_permissions: bool = True

    def with_auto_mcp_config(self, work_dir: str) -> "LaunchOptions":
        """若未指定 MCP 配置，自动使用工作目录下的 .mcp.json。"""
        if self.mcp_config.strip():
            return self
        wd = os.path.normpath(work_dir or "")
        if not wd:
            return self
        auto = os.path.join(wd, ".mcp.json")
        if os.path.isfile(auto):
            return replace(self, mcp_config=os.path.normpath(auto))
        return self

    def build_flag_args(self) -> List[str]:
        """生成 CLI 标志参数（不含初始提示词）。"""
        args: List[str] = []

        if self.safe_mode:
            args.append("--safe-mode")
        if self.bare:
            args.append("--bare")
        if self.verbose:
            args.append("--verbose")
        if self.no_session_persistence:
            args.append("--no-session-persistence")
        if self.fork_session:
            args.append("--fork-session")

        if self.mode == "continue":
            args.append("-c")
        elif self.mode == "resume":
            if self.resume_id.strip():
                args.extend(["-r", self.resume_id.strip()])
            else:
                args.append("-r")
        elif self.mode == "print":
            args.append("-p")

        if self.session_name.strip():
            args.extend(["-n", self.session_name.strip()])

        if self.model.strip():
            args.extend(["--model", self.model.strip()])

        if self.permission_mode.strip():
            args.extend(["--permission-mode", self.permission_mode.strip()])

        if self.effort.strip():
            args.extend(["--effort", self.effort.strip()])

        for d in self.add_dirs:
            d = d.strip()
            if d:
                args.extend(["--add-dir", d])

        if self.chrome == "on":
            args.append("--chrome")
        elif self.chrome == "off":
            args.append("--no-chrome")

        if self.debug.strip():
            args.extend(["--debug", self.debug.strip()])

        if self.allowed_tools.strip():
            for token in _split_tool_list(self.allowed_tools):
                args.extend(["--allowedTools", token])

        if self.disallowed_tools.strip():
            for token in _split_tool_list(self.disallowed_tools):
                args.extend(["--disallowedTools", token])

        if self.tools.strip():
            args.extend(["--tools", self.tools.strip()])

        if self.max_turns > 0:
            args.extend(["--max-turns", str(self.max_turns)])

        if self.max_budget_usd.strip():
            args.extend(["--max-budget-usd", self.max_budget_usd.strip()])

        if self.worktree.strip():
            args.extend(["-w", self.worktree.strip()])

        if self.from_pr.strip():
            args.extend(["--from-pr", self.from_pr.strip()])

        if self.fallback_model.strip():
            args.extend(["--fallback-model", self.fallback_model.strip()])

        if self.mcp_config.strip():
            args.extend(["--mcp-config", self.mcp_config.strip()])

        if self.settings_path.strip():
            args.extend(["--settings", self.settings_path.strip()])

        if self.extra_args.strip():
            try:
                args.extend(shlex.split(self.extra_args, posix=os.name != "nt"))
            except ValueError:
                args.extend(self.extra_args.split())

        if self.skip_permissions and "--dangerously-skip-permissions" not in args:
            args.append("--dangerously-skip-permissions")

        return args

    def append_prompt(self, argv: List[str], prompt: str) -> List[str]:
        """将初始提示词按模式追加到 argv。"""
        text = prompt.strip()
        if not text:
            return list(argv)
        return list(argv) + [text]

    def preview_cmdline(self, base_argv: List[str], prompt: str = "") -> str:
        full = list(base_argv) + self.build_flag_args()
        full = self.append_prompt(full, prompt)
        return _argv_to_cmdline(full)


def _split_tool_list(text: str) -> List[str]:
    text = text.strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            val = json.loads(text)
            if isinstance(val, list):
                return [str(x) for x in val]
        except json.JSONDecodeError:
            pass
    parts: List[str] = []
    for chunk in text.split('"'):
        chunk = chunk.strip().strip(",").strip()
        if chunk:
            parts.append(chunk.strip('"'))
    if len(parts) <= 1:
        return [p.strip() for p in text.split(",") if p.strip()]
    return parts


def _argv_to_cmdline(argv: List[str]) -> str:
    if os.name == "nt":
        import subprocess
        return subprocess.list2cmdline(argv)
    return " ".join(shlex.quote(a) for a in argv)


def load_project_settings_summary(work_dir: str) -> str:
    """读取项目 .claude/settings.json 摘要。"""
    path = os.path.join(work_dir, ".claude", "settings.json")
    if not os.path.isfile(path):
        return "（无项目 settings.json）"
    try:
        data = json.loads(open(path, encoding="utf-8").read())
        parts = []
        for key in ("model", "defaultMode", "effortLevel", "permissions"):
            if key in data and data[key]:
                val = data[key]
                if isinstance(val, dict):
                    val = json.dumps(val, ensure_ascii=False)[:80]
                parts.append(f"{key}={val}")
        return " · ".join(parts) if parts else "（settings.json 为空）"
    except Exception as exc:
        return f"（读取失败: {exc}）"


def options_from_settings(settings) -> LaunchOptions:
    """从 QSettings 恢复 LaunchOptions。"""
    add_dirs_raw = str(settings.value("opt/add_dirs", ""))
    add_dirs = [d.strip() for d in add_dirs_raw.split("|") if d.strip()]
    return LaunchOptions(
        mode=str(settings.value("opt/mode", "interactive")),
        resume_id=str(settings.value("opt/resume_id", "")),
        session_name=str(settings.value("opt/session_name", "")),
        model=str(settings.value("opt/model", "")),
        permission_mode=str(settings.value("opt/permission_mode", "")),
        effort=str(settings.value("opt/effort", "")),
        add_dirs=add_dirs,
        bare=settings.value("opt/bare", False, type=bool),
        safe_mode=settings.value("opt/safe_mode", False, type=bool),
        chrome=str(settings.value("opt/chrome", "default")),
        verbose=settings.value("opt/verbose", False, type=bool),
        debug=str(settings.value("opt/debug", "")),
        allowed_tools=str(settings.value("opt/allowed_tools", "")),
        disallowed_tools=str(settings.value("opt/disallowed_tools", "")),
        tools=str(settings.value("opt/tools", "")),
        max_turns=int(settings.value("opt/max_turns", 0) or 0),
        max_budget_usd=str(settings.value("opt/max_budget_usd", "")),
        worktree=str(settings.value("opt/worktree", "")),
        from_pr=str(settings.value("opt/from_pr", "")),
        fallback_model=str(settings.value("opt/fallback_model", "")),
        mcp_config=str(settings.value("opt/mcp_config", "")),
        settings_path=str(settings.value("opt/settings_path", "")),
        no_session_persistence=settings.value("opt/no_session_persistence", False, type=bool),
        fork_session=settings.value("opt/fork_session", False, type=bool),
        extra_args=str(settings.value("opt/extra_args", "")),
        skip_permissions=settings.value("opt/skip_permissions", True, type=bool),
    )


def save_options_to_settings(settings, opts: LaunchOptions) -> None:
    settings.setValue("opt/mode", opts.mode)
    settings.setValue("opt/resume_id", opts.resume_id)
    settings.setValue("opt/session_name", opts.session_name)
    settings.setValue("opt/model", opts.model)
    settings.setValue("opt/permission_mode", opts.permission_mode)
    settings.setValue("opt/effort", opts.effort)
    settings.setValue("opt/add_dirs", "|".join(opts.add_dirs))
    settings.setValue("opt/bare", opts.bare)
    settings.setValue("opt/safe_mode", opts.safe_mode)
    settings.setValue("opt/chrome", opts.chrome)
    settings.setValue("opt/verbose", opts.verbose)
    settings.setValue("opt/debug", opts.debug)
    settings.setValue("opt/allowed_tools", opts.allowed_tools)
    settings.setValue("opt/disallowed_tools", opts.disallowed_tools)
    settings.setValue("opt/tools", opts.tools)
    settings.setValue("opt/max_turns", opts.max_turns)
    settings.setValue("opt/max_budget_usd", opts.max_budget_usd)
    settings.setValue("opt/worktree", opts.worktree)
    settings.setValue("opt/from_pr", opts.from_pr)
    settings.setValue("opt/fallback_model", opts.fallback_model)
    settings.setValue("opt/mcp_config", opts.mcp_config)
    settings.setValue("opt/settings_path", opts.settings_path)
    settings.setValue("opt/no_session_persistence", opts.no_session_persistence)
    settings.setValue("opt/fork_session", opts.fork_session)
    settings.setValue("opt/extra_args", opts.extra_args)
    settings.setValue("opt/skip_permissions", opts.skip_permissions)
