"""Claude Code 就绪检测与独立 Web 一键安装。"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from typing import Any, Dict, Optional, Tuple

LAUNCH_MODE_DESKTOP = "desktop"
LAUNCH_MODE_WEB = "web-standalone"
MIN_NODE_MAJOR = 18


def _tongling_root() -> str:
    return os.environ.get("TONGLING_ROOT") or os.path.dirname(os.path.dirname(__file__))


def node_ai_dir() -> str:
    return os.path.join(_tongling_root(), "storage", "node_ai")


def claude_workdir() -> str:
    return os.path.join(node_ai_dir(), "claude-code")


def launch_mode() -> str:
    raw = (os.environ.get("TONGLING_LAUNCH_MODE") or LAUNCH_MODE_WEB).strip().lower()
    if raw in (LAUNCH_MODE_DESKTOP, "main", "gui"):
        return LAUNCH_MODE_DESKTOP
    return LAUNCH_MODE_WEB


def is_desktop_launch() -> bool:
    return launch_mode() == LAUNCH_MODE_DESKTOP


def _has_claude_package(workdir: str) -> bool:
    pkg = os.path.join(workdir, "node_modules", "@anthropic-ai", "claude-code")
    return os.path.isdir(pkg)


def _resolve_cli() -> Dict[str, Any]:
    root = _tongling_root()
    if root not in sys.path:
        sys.path.insert(0, root)
    try:
        from cc_visual.claude_launcher import resolve_claude_cli

        return resolve_claude_cli()
    except Exception as exc:
        return {"cli_argv": [], "error": str(exc)}


def node_ai_bundle_usable() -> bool:
    """node_ai 目录内是否有可用的 Node / Claude 包。"""
    if sys.platform == "win32":
        na = node_ai_dir()
        for name in ("npx.cmd", "npx.exe", "node.exe"):
            if os.path.isfile(os.path.join(na, name)):
                return True
        return _has_claude_package(claude_workdir())
    try:
        from tongling_web.node_portable import portable_node_usable

        if portable_node_usable():
            return True
    except ImportError:
        pass
    return _has_claude_package(claude_workdir())


def _needs_portable_node(tc_info: Dict[str, Any]) -> bool:
    if sys.platform == "win32" or is_desktop_launch():
        return False
    if not tc_info.get("node_path"):
        return True
    major = tc_info.get("node_major")
    return major is not None and major < MIN_NODE_MAJOR


def _install_portable_node_step(steps: list, logs: list) -> Tuple[bool, str, Dict[str, Any]]:
    try:
        from tongling_web.node_portable import install_portable_node
    except ImportError as exc:
        return False, f"缺少 node_portable 模块: {exc}", {}

    steps.append(
        {
            "id": "node_install",
            "label": "下载安装 Node.js",
            "status": "running",
            "detail": "正在从镜像下载便携 Node 20…",
        }
    )
    ok, msg, extra = install_portable_node(force=True)
    log_text = extra.get("log") or msg
    if log_text:
        logs.append(log_text)
    if not ok:
        steps[-1]["status"] = "err"
        steps[-1]["detail"] = msg
        return False, msg, extra
    steps[-1]["status"] = "ok"
    steps[-1]["detail"] = msg
    return True, msg, extra


def _parse_major_version(raw: str) -> Optional[int]:
    text = (raw or "").strip().lstrip("vV")
    m = re.match(r"(\d+)", text)
    return int(m.group(1)) if m else None


def _probe_node_toolchain(*, cwd: str = "") -> Tuple[bool, str, Dict[str, Any]]:
    """等价于 node -v && npm -v 检测，供状态接口与一键安装首步复用。"""
    env = dict(os.environ)
    try:
        from cc_visual.claude_launcher import augment_path_for_node_toolchain

        augment_path_for_node_toolchain(env)
    except ImportError:
        pass
    path_key = env.get("PATH", "")
    node = shutil.which("node", path=path_key) or ""
    npm = shutil.which("npm", path=path_key) or ""
    npx = shutil.which("npx", path=path_key) or ""
    base = os.path.normpath(cwd or _tongling_root() or os.getcwd())
    info: Dict[str, Any] = {
        "node_path": node,
        "npm_path": npm,
        "npx_path": npx,
        "node_version": "",
        "npm_version": "",
        "node_major": None,
        "node_ok": False,
        "npm_ok": False,
        "toolchain_ok": False,
    }

    if not node:
        return (
            False,
            "未找到 node 命令。请先安装 Node.js 18+，并用 ./start-web.sh 启动（或确保 node 在 PATH 中；nvm 用户可先 nvm use 18）",
            info,
        )

    code, out = _run([node, "-v"], cwd=base, env=env, timeout=20)
    node_ver = (out.splitlines()[0] if out else "").strip()
    info["node_version"] = node_ver
    major = _parse_major_version(node_ver)
    info["node_major"] = major
    if code != 0 or not node_ver:
        return False, f"node -v 执行失败: {out or code}", info
    if major is None or major < MIN_NODE_MAJOR:
        return (
            False,
            f"Node.js 版本过低（{node_ver}），需要 {MIN_NODE_MAJOR}+",
            info,
        )
    info["node_ok"] = True

    if not npm:
        return (
            False,
            f"已检测到 Node {node_ver}，但未找到 npm（请重装 Node.js 或安装 npm 包）",
            info,
        )

    code2, out2 = _run([npm, "-v"], cwd=base, env=env, timeout=20)
    npm_ver = (out2.splitlines()[0] if out2 else "").strip()
    info["npm_version"] = npm_ver
    if code2 != 0 or not npm_ver:
        return False, f"npm -v 执行失败: {out2 or code2}", info
    info["npm_ok"] = True
    info["toolchain_ok"] = True
    return True, f"Node {node_ver} · npm {npm_ver}", info


def claude_status() -> Dict[str, Any]:
    wd = claude_workdir()
    rt = _resolve_cli()
    cli_argv = rt.get("cli_argv") or []
    mode = launch_mode()
    desktop = mode == LAUNCH_MODE_DESKTOP
    tc_ok, tc_msg, tc_info = _probe_node_toolchain(cwd=wd if os.path.isdir(wd) else _tongling_root())
    npm = tc_info.get("npm_path") or shutil.which("npm", path=env.get("PATH", "") if (env := dict(os.environ)) else "") or ""
    npx = tc_info.get("npx_path") or shutil.which("npx") or ""
    can_install = (not desktop) and bool(tc_info.get("toolchain_ok"))
    can_auto_node = (not desktop) and sys.platform != "win32" and _needs_portable_node(tc_info)
    return {
        "launch_mode": mode,
        "desktop_launch": desktop,
        "workdir": wd,
        "workdir_exists": os.path.isdir(wd),
        "cli_ready": bool(cli_argv),
        "cli_source": rt.get("source") or "",
        "version_hint": rt.get("version_hint") or "",
        "node_ai_dir": node_ai_dir(),
        "node_ai_exists": os.path.isdir(node_ai_dir()),
        "node_ai_bundle_usable": node_ai_bundle_usable(),
        "npm_available": bool(npm),
        "npx_available": bool(npx),
        "npm_path": npm,
        "npx_path": npx,
        "node_version": tc_info.get("node_version") or "",
        "npm_version": tc_info.get("npm_version") or "",
        "node_ok": bool(tc_info.get("node_ok")),
        "toolchain_ok": bool(tc_info.get("toolchain_ok")),
        "toolchain_message": tc_msg,
        "can_auto_install": can_install,
        "can_auto_install_node": can_auto_node,
        "can_attempt_install": not desktop and not bool(cli_argv),
        "install_hint": _install_hint(
            desktop, bool(cli_argv), bool(tc_info.get("toolchain_ok")), tc_msg, can_auto_node
        ),
    }


def _install_hint(
    desktop: bool,
    cli_ready: bool,
    toolchain_ok: bool,
    tc_msg: str,
    can_auto_node: bool = False,
) -> str:
    if cli_ready:
        return ""
    if desktop:
        return "请在统领桌面端工具箱下载「AI 智能体 (node_ai)」资源包"
    if not toolchain_ok:
        if can_auto_node:
            return "点击「一键安装」将自动下载 Node.js 20 并安装 Claude Code"
        return tc_msg or "点击「一键安装」将自动执行 node -v / npm -v 检测"
    return "可点击「一键安装 Claude Code」（将先检测 Node/npm，再安装到 storage/node_ai/claude-code）"


def _run(cmd: list[str], *, cwd: str, env: dict, timeout: int = 600) -> Tuple[int, str]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        out = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
        return proc.returncode, out[-4000:]
    except subprocess.TimeoutExpired:
        return -1, "安装超时，请检查网络后重试"
    except OSError as exc:
        return -1, str(exc)


def _fix_unix_cli_permissions(workdir: str) -> None:
    if sys.platform == "win32":
        return
    bindir = os.path.join(workdir, "node_modules", ".bin")
    if not os.path.isdir(bindir):
        return
    for name in os.listdir(bindir):
        p = os.path.join(bindir, name)
        if os.path.isfile(p):
            try:
                os.chmod(p, 0o755)
            except OSError:
                pass


def _ensure_npx_link_for_mcp() -> None:
    """独立 Web：让 MCP 注册能在 storage/node_ai 找到 npx（Unix 软链）。"""
    if sys.platform == "win32":
        return
    env = dict(os.environ)
    try:
        from cc_visual.claude_launcher import augment_path_for_node_toolchain

        augment_path_for_node_toolchain(env)
    except ImportError:
        pass
    npx = shutil.which("npx", path=env.get("PATH", ""))
    if not npx:
        return
    na = node_ai_dir()
    os.makedirs(na, exist_ok=True)
    link = os.path.join(na, "npx")
    if os.path.lexists(link):
        return
    try:
        os.symlink(npx, link)
    except OSError:
        pass


def install_claude_code(*, workdir: str = "") -> Tuple[bool, str, Dict[str, Any]]:
    """
    非 desktop 启动时：先 node -v / npm -v，再 npm install @anthropic-ai/claude-code。
    desktop 模式拒绝（应走统领工具箱下载 node_ai）。
    """
    if is_desktop_launch():
        return False, "当前由统领桌面端启动，请在工具箱下载 AI 智能体 (node_ai)", {}

    wd = os.path.normpath(workdir or claude_workdir())
    os.makedirs(wd, exist_ok=True)

    steps: list[Dict[str, str]] = []
    logs: list[str] = []
    tc_ok, tc_msg, tc_info = _probe_node_toolchain(cwd=wd)

    if not tc_ok and _needs_portable_node(tc_info):
        node_ok, node_msg, node_extra = _install_portable_node_step(steps, logs)
        if not node_ok:
            return False, node_msg, {"steps": steps, "log": "\n".join(logs), **node_extra}
        tc_ok, tc_msg, tc_info = _probe_node_toolchain(cwd=wd)

    steps.append(
        {
            "id": "toolchain",
            "label": "检测 Node.js / npm",
            "status": "ok" if tc_ok else "err",
            "detail": tc_msg,
        }
    )
    if not tc_ok:
        return (
            False,
            tc_msg,
            {"steps": steps, "toolchain": tc_info, "log": "\n".join(logs) if logs else tc_msg},
        )

    logs.append(f"[toolchain] {tc_msg}")

    root = _tongling_root()
    if root not in sys.path:
        sys.path.insert(0, root)

    env = dict(os.environ)
    try:
        from cc_visual.claude_launcher import (
            apply_npm_registry_to_env,
            augment_path_for_node_toolchain,
            sanitize_stale_ssl_cert_env,
        )

        augment_path_for_node_toolchain(env)
        apply_npm_registry_to_env(env)
        sanitize_stale_ssl_cert_env(env)
    except ImportError:
        pass

    npm = tc_info.get("npm_path") or shutil.which("npm", path=env.get("PATH", ""))
    if not npm:
        return False, "未找到 npm", {"steps": steps, "toolchain": tc_info, "log": "\n".join(logs)}

    pkg_json = os.path.join(wd, "package.json")
    if not os.path.isfile(pkg_json):
        steps.append({"id": "npm_init", "label": "npm init", "status": "running", "detail": ""})
        code, out = _run([npm, "init", "-y"], cwd=wd, env=env, timeout=120)
        logs.append(out)
        if code != 0:
            steps[-1]["status"] = "err"
            steps[-1]["detail"] = out or str(code)
            return False, f"npm init 失败: {out or code}", {"steps": steps, "log": "\n".join(logs), "toolchain": tc_info}
        steps[-1]["status"] = "ok"
        steps[-1]["detail"] = "package.json 已创建"

    steps.append(
        {
            "id": "npm_install",
            "label": "安装 @anthropic-ai/claude-code",
            "status": "running",
            "detail": "可能需要数分钟…",
        }
    )
    code, out = _run(
        [npm, "install", "@anthropic-ai/claude-code"],
        cwd=wd,
        env=env,
        timeout=600,
    )
    logs.append(out)
    if code != 0:
        steps[-1]["status"] = "err"
        steps[-1]["detail"] = (out or str(code))[-500:]
        return False, f"npm install 失败: {out or code}", {"steps": steps, "log": "\n".join(logs), "toolchain": tc_info}
    steps[-1]["status"] = "ok"
    steps[-1]["detail"] = "安装完成"

    _fix_unix_cli_permissions(wd)
    _ensure_npx_link_for_mcp()

    try:
        from cc_visual import claude_launcher

        claude_launcher._cli_cache = None
    except Exception:
        pass

    st = claude_status()
    if not st.get("cli_ready"):
        steps.append({"id": "verify", "label": "验证 Claude CLI", "status": "err", "detail": "未检测到可执行文件"})
        return False, "安装完成但未检测到 Claude CLI，请查看日志", {
            "steps": steps,
            "log": "\n".join(logs),
            "toolchain": tc_info,
            **st,
        }

    ver = st.get("version_hint") or "ok"
    steps.append({"id": "verify", "label": "验证 Claude CLI", "status": "ok", "detail": ver})
    return (
        True,
        f"环境就绪（{tc_msg}）· Claude Code 已安装（{ver}）",
        {"steps": steps, "log": "\n".join(logs), "toolchain": tc_info, **st},
    )
