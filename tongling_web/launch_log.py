# -*- coding: utf-8 -*-
"""Claude 终端启动运行日志：写文件 + 供前端展示。"""

from __future__ import annotations

import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional


def _tongling_root() -> str:
    return os.environ.get("TONGLING_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def launch_log_path() -> str:
    root = _tongling_root()
    log_dir = os.path.join(root, "logs")
    try:
        os.makedirs(log_dir, exist_ok=True)
    except OSError:
        pass
    return os.path.join(log_dir, "claude_launch.log")


def _safe(val: Any, limit: int = 500) -> str:
    s = str(val if val is not None else "").strip()
    if len(s) > limit:
        return s[: limit - 1] + "…"
    return s


def build_launch_log_lines(
    *,
    stage: str,
    ok: bool,
    detail: str = "",
    spec: Optional[Dict[str, Any]] = None,
    body: Optional[Dict[str, Any]] = None,
    session_id: str = "",
    extra: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """生成可读启动日志行（不包含密钥内容）。"""
    spec = spec or {}
    body = body or {}
    extra = extra or {}
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        f"======== Claude 启动日志 {ts} ========",
        f"阶段: {stage}",
        f"结果: {'成功' if ok else '失败'}",
    ]
    if session_id:
        lines.append(f"会话: {session_id}")
    if detail:
        lines.append(f"详情: {_safe(detail, 800)}")

    source = spec.get("source") or extra.get("source") or ""
    if not source and isinstance(spec.get("options"), object):
        source = ""
    # prepare_launch 可能没塞 source，从 cli 侧字段兜底
    prefer_latest = spec.get("prefer_latest")
    if prefer_latest is None and "npx_latest" in body:
        prefer_latest = bool(body.get("npx_latest"))

    cmdline = spec.get("cmdline") or extra.get("cmdline") or ""
    argv = spec.get("argv") or extra.get("argv") or []
    cwd = spec.get("cwd") or ""
    real_cwd = spec.get("real_cwd") or ""
    subst = spec.get("subst_drive") or ""
    version = extra.get("version_hint") or spec.get("version_hint") or ""
    npx = extra.get("npx") or spec.get("npx") or ""
    native = extra.get("native_path") or spec.get("native_path") or ""
    pty_argv = extra.get("pty_argv") or []

    if source:
        lines.append(f"CLI 来源: {source}")
    if prefer_latest is not None:
        lines.append(f"始终拉取最新: {'是' if prefer_latest else '否'}")
    if version:
        lines.append(f"版本探测: {_safe(version, 120)}")
    if npx:
        lines.append(f"npx: {_safe(npx, 260)}")
    if native:
        lines.append(f"原生 claude: {_safe(native, 260)}")
    if cmdline:
        lines.append(f"命令: {_safe(cmdline, 1000)}")
    elif argv:
        try:
            import subprocess

            lines.append(f"命令: {_safe(subprocess.list2cmdline(list(argv)), 1000)}")
        except Exception:
            lines.append(f"argv: {_safe(argv, 1000)}")
    if pty_argv:
        try:
            import subprocess

            lines.append(f"PTY 实际启动: {_safe(subprocess.list2cmdline(list(pty_argv)), 1000)}")
        except Exception:
            lines.append(f"PTY argv: {_safe(pty_argv, 1000)}")
    if real_cwd:
        lines.append(f"工作目录: {_safe(real_cwd, 400)}")
    if cwd and cwd != real_cwd:
        lines.append(f"启动 cwd: {_safe(cwd, 400)}")
    if subst:
        lines.append(f"subst 盘符: {subst}")

    model = body.get("model") or ""
    if model:
        lines.append(f"CLI 模型: {model}")
    skip = body.get("skip_permissions")
    if skip is not None:
        lines.append(f"跳过权限: {'是' if skip else '否'}")
    proxy = (body.get("proxy") or "").strip()
    if proxy:
        lines.append(f"代理: {_safe(proxy, 120)}")
    launch_mode = body.get("launch_mode") or ""
    if launch_mode:
        lines.append(f"启动模式: {launch_mode}")

    for k, v in extra.items():
        if k in ("cmdline", "argv", "pty_argv", "source", "version_hint", "npx", "native_path"):
            continue
        if v is None or v == "":
            continue
        lines.append(f"{k}: {_safe(v, 300)}")

    lines.append("")
    return lines


def append_launch_log(lines: List[str]) -> str:
    """追加写入 logs/claude_launch.log，返回日志文件路径。"""
    path = launch_log_path()
    text = "\n".join(lines)
    if not text.endswith("\n"):
        text += "\n"
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(text)
    except OSError:
        pass
    return path


def enrich_spec_with_cli_meta(spec: Dict[str, Any]) -> Dict[str, Any]:
    """把 resolve_claude_cli 的来源信息补进 spec（若缺失）。"""
    if not spec:
        return spec
    if spec.get("source") and spec.get("version_hint") is not None:
        return spec
    try:
        from cc_visual.claude_launcher import resolve_claude_cli

        prefer_latest = bool(spec.get("prefer_latest"))
        rt = resolve_claude_cli(prefer_latest=prefer_latest)
        spec.setdefault("source", rt.get("source") or "")
        spec.setdefault("version_hint", rt.get("version_hint") or "")
        spec.setdefault("npx", rt.get("npx") or "")
        spec.setdefault("native_path", rt.get("native_path") or "")
    except Exception:
        pass
    return spec


def format_launch_log_for_terminal(lines: List[str]) -> str:
    """转成可写入 xterm 的 ANSI 文本。"""
    out = []
    for line in lines:
        if not line.strip():
            out.append("\r\n")
            continue
        if line.startswith("========"):
            out.append(f"\x1b[36m{line}\x1b[0m\r\n")
        elif line.startswith("结果: 失败") or line.startswith("详情:"):
            color = "31" if "失败" in line or line.startswith("详情:") else "90"
            out.append(f"\x1b[{color}m[启动] {line}\x1b[0m\r\n")
        else:
            out.append(f"\x1b[90m[启动] {line}\x1b[0m\r\n")
    return "".join(out)
