#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Claude Code 启动辅助：解析 CLI、代理、环境变量（对应 windows_start.bat）。"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple

from claude_options import LaunchOptions
from portable_git_bash import (
    apply_portable_git_bash_to_env,
    bootstrap_from_system_git,
    resolve_git_bash_path,
)

_CC_PKG = os.path.dirname(os.path.abspath(__file__))
_TONGLING_ROOT = os.path.dirname(_CC_PKG)
NODE_AI_DIR = os.path.join(_TONGLING_ROOT, "storage", "node_ai")
CLAUDE_DIR = os.path.join(NODE_AI_DIR, "claude-code")
ROOT_DIR = _CC_PKG
DEFAULT_PROXY = ""
CLAUDE_CODE_NPM_SPEC = "@anthropic-ai/claude-code@latest"
# npx 拉包默认走国内镜像；可在 config.yaml 设 npm_registry，或环境变量 NPM_CONFIG_REGISTRY 覆盖
DEFAULT_NPM_REGISTRY_CN = "https://registry.npmmirror.com"

_config_npm_registry_cache: Optional[str] = None


def resolve_npm_registry() -> str:
    """解析 npm registry：环境变量 > config.yaml > 国内 npmmirror 默认。"""
    global _config_npm_registry_cache
    for key in ("NPM_CONFIG_REGISTRY", "npm_config_registry"):
        val = (os.environ.get(key) or "").strip()
        if val:
            return val.rstrip("/")
    if _config_npm_registry_cache is None:
        _config_npm_registry_cache = _load_npm_registry_from_config()
    if _config_npm_registry_cache:
        return _config_npm_registry_cache
    return DEFAULT_NPM_REGISTRY_CN


def _load_npm_registry_from_config() -> str:
    cfg_path = os.path.join(_TONGLING_ROOT, "config.yaml")
    if not os.path.isfile(cfg_path):
        return ""
    try:
        import yaml

        with open(cfg_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        reg = (data.get("npm_registry") or data.get("NpmRegistry") or "").strip()
        return reg.rstrip("/") if reg else ""
    except Exception:
        return ""


def apply_npm_registry_to_env(env: dict) -> str:
    """为 npx/npm 写入 registry 环境变量（不覆盖用户已显式设置的值）。"""
    reg = resolve_npm_registry()
    env.setdefault("NPM_CONFIG_REGISTRY", reg)
    env.setdefault("npm_config_registry", reg)
    return reg


def _cert_path_usable(path: str) -> bool:
    p = (path or "").strip().strip('"').strip("'")
    return bool(p) and os.path.isfile(p)


def sanitize_stale_ssl_cert_env(env: dict) -> None:
    """
    移除指向不存在文件的 CA 证书环境变量。
    常见于 cursor-renewal 等工具遗留的 NODE_EXTRA_CA_CERTS / npm cafile。
    """
    removed_ca = False
    cert_keys = (
        "NODE_EXTRA_CA_CERTS",
        "SSL_CERT_FILE",
        "REQUESTS_CA_BUNDLE",
        "CURL_CA_BUNDLE",
    )
    for key in cert_keys:
        val = env.get(key)
        if val is None:
            continue
        if not _cert_path_usable(str(val)):
            env.pop(key, None)
            removed_ca = True

    for key in ("npm_config_cafile", "NPM_CONFIG_CAFILE"):
        val = env.get(key)
        if val is None:
            continue
        if str(val).strip() and not _cert_path_usable(str(val)):
            env.pop(key, None)
            removed_ca = True

    if removed_ca:
        # 覆盖用户 .npmrc 里可能仍指向失效路径的 cafile，避免 npx 再次注入 NODE_EXTRA_CA_CERTS
        env["npm_config_cafile"] = ""
        env["NPM_CONFIG_CAFILE"] = ""


def build_npx_claude_argv(npx: str) -> List[str]:
    """npx 启动 Claude Code，显式指定 registry 以走国内镜像。"""
    reg = resolve_npm_registry()
    return [npx, "--registry", reg, CLAUDE_CODE_NPM_SPEC]

# 内嵌终端用 subst 盘符，避免中文路径导致 TUI 框线错位
_SUBST_CANDIDATES = ("Z:", "Y:", "X:", "W:", "V:")
_active_substs: Dict[str, str] = {}  # drive -> real_path


def _has_non_ascii(path: str) -> bool:
    try:
        path.encode("ascii")
        return False
    except UnicodeEncodeError:
        return True


def needs_ascii_cwd(path: str) -> bool:
    return sys.platform == "win32" and bool(path) and _has_non_ascii(os.path.abspath(path))


def resolve_ascii_cwd(work_dir: str) -> Tuple[str, Optional[str]]:
    """
    若路径含非 ASCII 字符，用 subst Z: 映射。
    返回 (launch_cwd, subst_drive)。
    """
    cwd = os.path.normpath(os.path.abspath(work_dir))
    if sys.platform != "win32" or not _has_non_ascii(cwd):
        return cwd, None

    drive = _SUBST_CANDIDATES[0]  # Z:
    subprocess.run(["subst", drive, "/d"], capture_output=True)
    r = subprocess.run(["subst", drive, cwd], capture_output=True, text=True)
    if r.returncode != 0 or not os.path.isdir(drive + "\\"):
        return cwd, None

    _active_substs[drive] = cwd
    return drive + "\\", drive


def cleanup_subst(drive: Optional[str] = None) -> None:
    """释放 subst 盘符。"""
    if sys.platform != "win32":
        return
    drives = [drive] if drive else list(_active_substs.keys())
    for d in drives:
        if not d:
            continue
        subprocess.run(["subst", d, "/d"], capture_output=True)
        _active_substs.pop(d, None)


def cleanup_all_substs() -> None:
    cleanup_subst()


def _default_claude_cwd() -> str:
    """默认 Claude 工作目录：Windows 优先 node_ai；Unix 可用项目根或用户目录。"""
    if os.path.isdir(CLAUDE_DIR):
        return CLAUDE_DIR
    if sys.platform == "win32":
        return CLAUDE_DIR
    root = os.environ.get("TONGLING_ROOT") or _TONGLING_ROOT
    if os.path.isdir(root):
        return root
    return os.path.expanduser("~")


def _find_npx() -> str:
    if sys.platform == "win32":
        for name in ("npx.cmd", "npx.exe", "npx"):
            p = os.path.join(NODE_AI_DIR, name)
            if os.path.isfile(p):
                return p
        return ""
    return shutil.which("npx") or ""


def find_native_claude() -> str:
    """查找 claude install 安装的原生二进制。"""
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA", "")
        home = os.environ.get("USERPROFILE", "")
        candidates = [
            os.path.join(local, "claude-code", "claude.exe"),
            os.path.join(local, "Programs", "claude-code", "claude.exe"),
            os.path.join(home, ".claude", "local", "claude.exe"),
            os.path.join(home, ".local", "bin", "claude.exe"),
        ]
        for p in candidates:
            if p and os.path.isfile(p):
                return os.path.normpath(p)
        for folder in os.environ.get("PATH", "").split(os.pathsep):
            p = os.path.join(folder, "claude.exe")
            if os.path.isfile(p):
                return os.path.normpath(p)
        return ""

    home = os.environ.get("HOME") or os.path.expanduser("~")
    candidates = [
        os.path.join(home, ".local", "bin", "claude"),
        os.path.join(home, ".claude", "local", "claude"),
        os.path.join(home, "bin", "claude"),
    ]
    for p in candidates:
        if p and os.path.isfile(p) and os.access(p, os.X_OK):
            return os.path.normpath(p)
    found = shutil.which("claude")
    return found or ""


_cli_cache: Optional[Dict[str, Any]] = None


def resolve_claude_cli(*, refresh: bool = False) -> Dict[str, Any]:
    """
    解析 Claude Code 可执行方式。
    优先：原生 claude.exe > npx @latest > 本地 node_modules/.bin。
    """
    global _cli_cache
    if _cli_cache is not None and not refresh:
        return dict(_cli_cache)

    cli_argv: List[str] = []
    source = ""

    native = find_native_claude()
    if native:
        cli_argv = [native]
        source = "native"

    npx = _find_npx()
    if not cli_argv and npx:
        cli_argv = build_npx_claude_argv(npx)
        source = "npx-latest"

    if not cli_argv:
        for name in ("claude.cmd", "claude.exe", "claude"):
            local = os.path.join(CLAUDE_DIR, "node_modules", ".bin", name)
            if os.path.isfile(local):
                cli_argv = [local]
                source = "npm-local"
                break

    work_dir = CLAUDE_DIR if os.path.isdir(CLAUDE_DIR) else _default_claude_cwd()

    version_hint = ""
    if cli_argv:
        try:
            r = subprocess.run(
                cli_argv + ["--version"],
                cwd=CLAUDE_DIR,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
            if r.returncode == 0:
                version_hint = (r.stdout or r.stderr or "").strip().split("\n")[0][:80]
        except Exception:
            pass

    result = {
        "cli_argv": cli_argv,
        "work_dir": work_dir,
        "npx": npx,
        "version_hint": version_hint,
        "source": source,
        "native_path": native,
    }
    _cli_cache = result
    return dict(result)


def proxy_env(proxy: str, base_env: Optional[dict] = None) -> dict:
    env = dict(base_env or os.environ)
    url = (proxy or "").strip()
    if not url:
        return env
    if not url.lower().startswith(("http://", "https://")):
        url = "http://" + url
    env["http_proxy"] = url
    env["https_proxy"] = url
    env["HTTP_PROXY"] = url
    env["HTTPS_PROXY"] = url
    return env


def _resolve_git_bash_path() -> str:
    """解析 Bash 路径：优先项目内 git-bash，其次系统 Git。"""
    bootstrap_from_system_git(quiet=True)
    return resolve_git_bash_path(allow_system_fallback=True)


def build_launch_env(
    proxy: str = DEFAULT_PROXY,
    work_dir: str = "",
    cli_info: Optional[Dict[str, Any]] = None,
) -> dict:
    """构建与 windows_start.bat 一致的环境变量。"""
    env = proxy_env(proxy)
    apply_portable_git_bash_to_env(env)
    apply_npm_registry_to_env(env)

    rt = cli_info or resolve_claude_cli()
    for path in (
        os.path.dirname(rt["cli_argv"][0]) if rt["cli_argv"] else "",
        os.path.dirname(rt.get("npx") or ""),
        NODE_AI_DIR if sys.platform == "win32" and os.path.isdir(NODE_AI_DIR) else "",
    ):
        if path and os.path.isdir(path):
            env["PATH"] = path + os.pathsep + env.get("PATH", "")

    try:
        from provider_manager import provider_env_for_launch

        for key, value in provider_env_for_launch().items():
            if value:
                env[key] = value
    except ImportError:
        pass

    sanitize_stale_ssl_cert_env(env)
    return env


def build_launch_argv(
    extra_args: Optional[List[str]] = None,
    initial_prompt: str = "",
    cli_info: Optional[Dict[str, Any]] = None,
    options: Optional[LaunchOptions] = None,
) -> Tuple[bool, str, Optional[List[str]]]:
    """构建 Claude Code 启动参数。"""
    rt = cli_info or resolve_claude_cli()
    argv = list(rt["cli_argv"])
    if not argv:
        if sys.platform == "win32":
            return False, "未找到 Claude Code，请运行 claude install 或检查 node_ai/claude-code", None
        return False, "未找到 Claude Code，请安装: npm i -g @anthropic-ai/claude-code 或 claude install", None

    if options:
        argv.extend(options.build_flag_args())

    if extra_args:
        argv.extend(extra_args)

    if options:
        argv = options.append_prompt(argv, initial_prompt)
    elif initial_prompt.strip():
        argv.append(initial_prompt.strip())

    return True, "ok", argv


def prepare_launch(
    proxy: str = DEFAULT_PROXY,
    work_dir: str = "",
    initial_prompt: str = "",
    extra_args: Optional[List[str]] = None,
    ascii_cwd: bool = False,
    options: Optional[LaunchOptions] = None,
) -> Tuple[bool, str, Optional[dict]]:
    """准备启动规格。ascii_cwd=True 时把中文路径 subst 到 Z:，修复内嵌 TUI 错位。"""
    rt = resolve_claude_cli()

    real_cwd = os.path.normpath(work_dir) if work_dir else _default_claude_cwd()
    if not os.path.isdir(real_cwd):
        return False, f"工作目录不存在: {real_cwd}", None

    if options is None:
        options = LaunchOptions()
    options = options.with_auto_mcp_config(real_cwd)

    ok, msg, argv = build_launch_argv(extra_args, initial_prompt, cli_info=rt, options=options)
    if not ok or not argv:
        return False, msg, None

    subst_drive = None
    launch_cwd = real_cwd
    if ascii_cwd:
        launch_cwd, subst_drive = resolve_ascii_cwd(real_cwd)

    env = build_launch_env(proxy or "", real_cwd, cli_info=rt)
    # 让 Claude 显示短路径
    if subst_drive:
        env["CC_REAL_CWD"] = real_cwd

    try:
        from claude_session import write_storage_marker

        write_storage_marker(real_cwd, subst=bool(subst_drive))
    except Exception:
        pass

    mcp_config = options.mcp_config.strip() if options.mcp_config else ""

    return True, "ok", {
        "argv": argv,
        "cwd": launch_cwd,
        "real_cwd": real_cwd,
        "subst_drive": subst_drive,
        "env": env,
        "options": options,
        "mcp_config": mcp_config,
        "cmdline": subprocess.list2cmdline(argv),
    }


def run_claude_command(
    sub_args: List[str],
    *,
    work_dir: str = "",
    proxy: str = "",
    env: Optional[dict] = None,
    timeout: int = 60,
) -> Tuple[int, str, str]:
    """运行 claude 子命令（如 auth status、update），返回 (code, stdout, stderr)。"""
    rt = resolve_claude_cli()
    if not rt["cli_argv"]:
        return -1, "", "未找到 Claude Code CLI"

    cwd = os.path.normpath(work_dir) if work_dir else CLAUDE_DIR
    proc_env = env or build_launch_env(proxy or DEFAULT_PROXY, cwd, cli_info=rt)
    argv = list(rt["cli_argv"]) + sub_args

    try:
        r = subprocess.run(
            argv,
            cwd=cwd,
            env=proc_env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return r.returncode, r.stdout or "", r.stderr or ""
    except subprocess.TimeoutExpired:
        return -1, "", "命令超时"
    except Exception as exc:
        return -1, "", str(exc)


def register_mcp_with_launch_cli(
    work_dir: str,
    payload: dict,
    server_name: str,
    *,
    proxy: str = DEFAULT_PROXY,
    write_json: bool = True,
) -> Tuple[bool, str, str]:
    """
    配置项目 MCP：写 .mcp.json，并清理 local scope 重复项（避免多 scope 冲突）。
    返回 (成功, 日志, mcp_json 路径)。
    """
    cwd = os.path.normpath(work_dir) if work_dir else CLAUDE_DIR
    if not os.path.isdir(cwd):
        return False, f"工作目录不存在: {cwd}", ""

    logs: List[str] = []
    mcp_path = os.path.join(cwd, ".mcp.json")

    if write_json:
        try:
            from claude_hexstrike_bridge import write_project_mcp_json

            mcp_path = write_project_mcp_json(cwd, server_name, payload)
            logs.append(f"✓ 已写入 {mcp_path}")
        except OSError as exc:
            return False, f"写入 .mcp.json 失败: {exc}", mcp_path

    rt = resolve_claude_cli(refresh=True)
    if rt["cli_argv"]:
        rc, out, err = run_claude_command(
            ["mcp", "remove", server_name, "-s", "local"],
            work_dir=cwd,
            proxy=proxy,
            timeout=30,
        )
        merged = (out or err or "").strip()
        if merged and not _mcp_remove_benign(merged):
            logs.append(merged)
        elif merged:
            logs.append("已清理 local scope 重复 MCP 配置（保留项目 .mcp.json）。")

    if os.path.isfile(mcp_path):
        logs.append("MCP 已就绪；启动 Claude 时将自动带上 --mcp-config。")
        return True, "\n".join(logs), mcp_path
    return False, "未找到 .mcp.json", mcp_path


def _mcp_remove_benign(text: str) -> bool:
    t = (text or "").lower()
    return any(k in t for k in ("not found", "does not exist", "no such", "already removed"))


def launch_claude_subcommand_external(
    sub_args: List[str],
    *,
    work_dir: str = "",
    proxy: str = DEFAULT_PROXY,
    title: str = "Claude Code",
) -> Tuple[bool, str]:
    """在新 CMD 窗口运行 claude 子命令（交互式，如 mcp / agents）。"""
    if sys.platform != "win32":
        return False, "仅支持 Windows"

    rt = resolve_claude_cli()
    if not rt["cli_argv"]:
        return False, "未找到 Claude Code CLI"

    cwd = os.path.normpath(work_dir) if work_dir else CLAUDE_DIR
    env = build_launch_env(proxy, cwd, cli_info=rt)
    inner = subprocess.list2cmdline(list(rt["cli_argv"]) + sub_args)
    cmd_parts = ["cmd.exe", "/q", "/k", f"title {title} && cd /d {cwd} && {inner}"]

    try:
        subprocess.Popen(
            cmd_parts,
            cwd=cwd,
            env=env,
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )
        return True, f"已打开 CMD: {' '.join(sub_args)}"
    except Exception as exc:
        return False, str(exc)


def launch_external_terminal(
    proxy: str = DEFAULT_PROXY,
    work_dir: str = "",
    initial_prompt: str = "",
    spec: Optional[dict] = None,
) -> Tuple[bool, str]:
    """在新 CMD 窗口中启动 Claude Code（完整终端效果，推荐备用）。"""
    if sys.platform != "win32":
        return False, "外部终端启动仅支持 Windows"

    if spec:
        argv = spec.get("argv") or []
        cwd = spec.get("cwd") or CLAUDE_DIR
        env = spec.get("env") or build_launch_env(proxy, cwd)
    else:
        ok, msg, prepared = prepare_launch(proxy, work_dir, initial_prompt)
        if not ok or not prepared:
            return False, msg
        argv = prepared["argv"]
        cwd = prepared["cwd"]
        env = prepared["env"]

    inner = subprocess.list2cmdline(argv)
    cmd_parts = ["cmd.exe", "/q", "/k", f"title Claude Code && cd /d {cwd} && {inner}"]

    try:
        subprocess.Popen(
            cmd_parts,
            cwd=cwd,
            env=env,
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )
        return True, "已在新 CMD 窗口启动 Claude Code"
    except Exception as exc:
        return False, f"启动失败: {exc}"
