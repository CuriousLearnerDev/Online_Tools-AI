#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""项目内便携 Git Bash — 解压即用，不依赖系统 Git 安装路径。"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from typing import Iterable, List, Optional, Tuple

_CC_PKG = os.path.dirname(os.path.abspath(__file__))
_TONGLING_ROOT = os.path.dirname(_CC_PKG)
NODE_AI_DIR = os.path.join(_TONGLING_ROOT, "storage", "node_ai")
PORTABLE_GIT_BASH_DIR = os.path.join(NODE_AI_DIR, "git-bash")
PORTABLE_BASH_EXE = os.path.join(PORTABLE_GIT_BASH_DIR, "usr", "bin", "bash.exe")
READY_MARKER = os.path.join(PORTABLE_GIT_BASH_DIR, ".ready")


def portable_bash_ready() -> bool:
    return os.path.isfile(PORTABLE_BASH_EXE)


def _unique_paths(paths: Iterable[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for raw in paths:
        norm = os.path.normpath(raw)
        if norm in seen:
            continue
        seen.add(norm)
        out.append(norm)
    return out


def _detect_system_git_root() -> str:
    if sys.platform != "win32":
        return ""
    try:
        r = subprocess.run(
            ["where.exe", "git"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )
        if r.returncode != 0:
            return ""
        for line in (r.stdout or "").splitlines():
            git_exe = line.strip().strip('"')
            if not git_exe or not os.path.isfile(git_exe):
                continue
            root = os.path.dirname(os.path.dirname(git_exe))
            if os.path.isdir(os.path.join(root, "usr", "bin")):
                return os.path.normpath(root)
    except Exception:
        pass

    for root in (
        os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Git"),
        os.path.join(
            os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), "Git"
        ),
        r"C:\Git",
    ):
        if os.path.isdir(os.path.join(root, "usr", "bin")):
            return os.path.normpath(root)
    return ""


def install_portable_git_bash(source_root: str, *, force: bool = False) -> Tuple[bool, str]:
    """
    从已有 Git for Windows 目录复制到 storage/node_ai/git-bash/。
    发布包应预置此目录；开发机可运行 setup_git_bash.bat 生成一次。
    """
    source_root = os.path.normpath(source_root)
    usr_bin = os.path.join(source_root, "usr", "bin")
    if not os.path.isdir(usr_bin):
        return False, f"无效的 Git 目录（缺少 usr/bin）: {source_root}"

    if portable_bash_ready() and not force:
        return True, f"便携 Git Bash 已存在: {PORTABLE_BASH_EXE}"

    if force and os.path.isdir(PORTABLE_GIT_BASH_DIR):
        shutil.rmtree(PORTABLE_GIT_BASH_DIR, ignore_errors=True)

    os.makedirs(os.path.join(PORTABLE_GIT_BASH_DIR, "usr", "bin"), exist_ok=True)
    os.makedirs(os.path.join(PORTABLE_GIT_BASH_DIR, "tmp"), exist_ok=True)
    os.makedirs(os.path.join(PORTABLE_GIT_BASH_DIR, "usr", "tmp"), exist_ok=True)

    copied = 0
    for name in os.listdir(usr_bin):
        src = os.path.join(usr_bin, name)
        dst = os.path.join(PORTABLE_GIT_BASH_DIR, "usr", "bin", name)
        if os.path.isfile(src):
            shutil.copy2(src, dst)
            copied += 1

    etc_src = os.path.join(source_root, "etc")
    etc_dst = os.path.join(PORTABLE_GIT_BASH_DIR, "etc")
    if os.path.isdir(etc_src):
        if os.path.isdir(etc_dst):
            shutil.rmtree(etc_dst, ignore_errors=True)
        shutil.copytree(etc_src, etc_dst)

    if not portable_bash_ready():
        return False, "复制完成但未找到 bash.exe，请检查源 Git 安装"

    with open(READY_MARKER, "w", encoding="utf-8") as fh:
        fh.write(source_root + "\n")
    return True, f"已安装便携 Git Bash（{copied} 个 usr/bin 文件）→ {PORTABLE_BASH_EXE}"


def bootstrap_from_system_git(*, quiet: bool = False) -> Tuple[bool, str]:
    if portable_bash_ready():
        return True, PORTABLE_BASH_EXE
    root = _detect_system_git_root()
    if not root:
        return False, "未找到系统 Git，无法自动安装便携 Git Bash"
    ok, msg = install_portable_git_bash(root)
    if not quiet and ok:
        print(msg, file=sys.stderr)
    return ok, msg


def resolve_git_bash_path(*, allow_system_fallback: bool = True) -> str:
    """优先使用项目内 storage/node_ai/git-bash，其次才用系统 Git。"""
    if sys.platform != "win32":
        return ""

    candidates: List[str] = [
        PORTABLE_BASH_EXE,
        os.path.join(NODE_AI_DIR, "usr", "bin", "bash.exe"),
    ]

    bundled_bin = os.path.join(NODE_AI_DIR, "claude-code", "bash.exe")
    bundled_usr = os.path.join(NODE_AI_DIR, "usr", "bin", "bash.exe")
    if os.path.isfile(bundled_bin) and os.path.isfile(bundled_usr):
        candidates.append(bundled_bin)

    if allow_system_fallback:
        root = _detect_system_git_root()
        if root:
            candidates.extend(
                [
                    os.path.join(root, "usr", "bin", "bash.exe"),
                    os.path.join(root, "bin", "bash.exe"),
                ]
            )

    for path in _unique_paths(candidates):
        if os.path.isfile(path):
            return path
    return ""


def portable_git_bash_env() -> dict:
    """为 Claude Code 注入便携 Bash 相关环境变量。"""
    env: dict = {}
    bash = resolve_git_bash_path()
    if not bash:
        return env

    env["CLAUDE_CODE_GIT_BASH_PATH"] = bash
    root = PORTABLE_GIT_BASH_DIR if portable_bash_ready() else ""
    if not root and bash.replace("\\", "/").endswith("/usr/bin/bash.exe"):
        root = os.path.normpath(os.path.join(os.path.dirname(bash), "..", ".."))

    if root and os.path.isdir(root):
        env.setdefault("MSYSTEM", "MINGW64")
        env.setdefault("MSYS2_PATH_TYPE", "inherit")
        usr_bin = os.path.join(root, "usr", "bin")
        if os.path.isdir(usr_bin):
            env["_PORTABLE_GIT_BASH_USR_BIN"] = usr_bin
    return env


def prepend_path(env: dict, folder: str) -> None:
    if folder and os.path.isdir(folder):
        env["PATH"] = folder + os.pathsep + env.get("PATH", "")


def apply_portable_git_bash_to_env(env: dict) -> None:
    pg = portable_git_bash_env()
    env.update(pg)
    usr_bin = pg.get("_PORTABLE_GIT_BASH_USR_BIN")
    if usr_bin:
        prepend_path(env, usr_bin)
        env.pop("_PORTABLE_GIT_BASH_USR_BIN", None)
