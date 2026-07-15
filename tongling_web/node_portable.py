"""独立 Web：下载便携 Node.js 到 storage/node_ai（Linux / macOS）。"""

from __future__ import annotations

import json
import os
import platform
import shutil
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Tuple

DEFAULT_NODE_VERSION = "20.18.2"
MARKER_FILENAME = ".portable-node.json"
NPPMIRROR_BASE = "https://npmmirror.com/mirrors/node"
NODEJS_BASE = "https://nodejs.org/dist"


def _tongling_root() -> str:
    return os.environ.get("TONGLING_ROOT") or os.path.dirname(os.path.dirname(__file__))


def node_ai_dir() -> str:
    return os.path.join(_tongling_root(), "storage", "node_ai")


def _resolve_node_version() -> str:
    raw = (os.environ.get("TONGLING_NODE_VERSION") or DEFAULT_NODE_VERSION).strip().lstrip("v")
    return raw or DEFAULT_NODE_VERSION


def _platform_archive() -> Tuple[str, str, str]:
    """返回 (folder_suffix, 下载扩展名, 官方 dist 子路径)。"""
    sys_name = sys.platform
    machine = platform.machine().lower()
    if machine in ("x86_64", "amd64"):
        arch = "x64"
    elif machine in ("aarch64", "arm64"):
        arch = "arm64"
    else:
        raise RuntimeError(f"不支持的 CPU 架构: {machine}")

    if sys_name == "linux":
        return f"linux-{arch}", "tar.xz", "linux"
    if sys_name == "darwin":
        return f"darwin-{arch}", "tar.gz", "darwin"
    raise RuntimeError(f"便携 Node 自动安装暂不支持: {sys_name}")


def _folder_name(version: str, suffix: str) -> str:
    ver = version.lstrip("v")
    return f"node-v{ver}-{suffix}"


def _marker_path() -> str:
    return os.path.join(node_ai_dir(), MARKER_FILENAME)


def _read_marker() -> Dict[str, Any]:
    path = _marker_path()
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _write_marker(data: Dict[str, Any]) -> None:
    os.makedirs(node_ai_dir(), exist_ok=True)
    with open(_marker_path(), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def portable_node_root() -> str:
    """已安装的便携 Node 根目录（含 bin/node）。"""
    marker = _read_marker()
    root_name = (marker.get("folder") or "").strip()
    na = node_ai_dir()
    if root_name:
        root = os.path.join(na, root_name)
        if os.path.isfile(os.path.join(root, "bin", "node")):
            return os.path.normpath(root)

    if not os.path.isdir(na):
        return ""
    for name in sorted(os.listdir(na), reverse=True):
        if not name.startswith("node-v"):
            continue
        root = os.path.join(na, name)
        if os.path.isfile(os.path.join(root, "bin", "node")):
            return os.path.normpath(root)
    return ""


def portable_node_bin_dir() -> str:
    root = portable_node_root()
    if not root:
        return ""
    bindir = os.path.join(root, "bin")
    node = os.path.join(bindir, "node")
    if os.path.isfile(node):
        return os.path.normpath(bindir)
    return ""


def portable_node_usable() -> bool:
    bindir = portable_node_bin_dir()
    if not bindir:
        return False
    node = os.path.join(bindir, "node")
    return os.access(node, os.X_OK)


def _download_urls(version: str, folder: str, ext: str) -> list[str]:
    ver = version.lstrip("v")
    filename = f"{folder}.{ext}"
    return [
        f"{NPPMIRROR_BASE}/v{ver}/{filename}",
        f"{NODEJS_BASE}/v{ver}/{filename}",
    ]


def _download_file(urls: list[str], dest: str, timeout: int = 600) -> str:
    last_err = ""
    for url in urls:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "TongLing-Web/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp, open(dest, "wb") as out:
                shutil.copyfileobj(resp, out, length=1024 * 256)
            if os.path.getsize(dest) > 1024 * 1024:
                return url
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            last_err = f"{url}: {exc}"
    raise RuntimeError(last_err or "下载 Node.js 失败")


def _extract_archive(archive: str, dest_dir: str) -> str:
    ext = archive.lower()
    mode = "r:xz" if ext.endswith(".xz") else "r:gz"
    with tarfile.open(archive, mode) as tf:
        members = tf.getmembers()
        if not members:
            raise RuntimeError("压缩包为空")
        top = members[0].name.split("/")[0]
        tf.extractall(dest_dir)
    root = os.path.join(dest_dir, top)
    if not os.path.isfile(os.path.join(root, "bin", "node")):
        raise RuntimeError(f"解压后未找到 bin/node: {root}")
    return os.path.normpath(root)


def _link_tools(bindir: str) -> None:
    na = node_ai_dir()
    os.makedirs(na, exist_ok=True)
    for name in ("node", "npm", "npx"):
        src = os.path.join(bindir, name)
        if not os.path.isfile(src):
            continue
        dst = os.path.join(na, name)
        if os.path.lexists(dst):
            try:
                os.remove(dst)
            except OSError:
                pass
        try:
            os.chmod(src, 0o755)
            os.symlink(src, dst)
        except OSError:
            pass


def can_auto_install_portable_node() -> bool:
    return sys.platform in ("linux", "darwin") and not getattr(
        sys, "frozen", False
    )


def install_portable_node(*, version: str = "", force: bool = False) -> Tuple[bool, str, Dict[str, Any]]:
    """
    下载官方 Node 二进制到 storage/node_ai/node-v*，并创建 node/npm/npx 软链。
    """
    if sys.platform == "win32":
        return False, "Windows 请使用统领工具箱下载 node_ai 资源包", {}
    if not can_auto_install_portable_node():
        return False, f"当前平台 ({sys.platform}) 不支持自动安装 Node", {}

    ver = _resolve_node_version() if not version else version.lstrip("v")
    na = node_ai_dir()
    os.makedirs(na, exist_ok=True)

    if not force and portable_node_usable():
        bindir = portable_node_bin_dir()
        return True, f"便携 Node 已存在（{bindir}）", {"bin_dir": bindir, "skipped": True}

    try:
        suffix, ext, _ = _platform_archive()
    except RuntimeError as exc:
        return False, str(exc), {}

    folder = _folder_name(ver, suffix)
    logs: list[str] = []

    with tempfile.TemporaryDirectory(prefix="tongling-node-") as tmp:
        archive = os.path.join(tmp, f"{folder}.{ext}")
        urls = _download_urls(ver, folder, ext)
        logs.append(f"下载 Node v{ver} …")
        try:
            used = _download_file(urls, archive)
            logs.append(f"已下载: {used}")
        except RuntimeError as exc:
            return False, f"Node.js 下载失败: {exc}", {"log": "\n".join(logs)}

        target_parent = na
        existing = os.path.join(target_parent, folder)
        if os.path.isdir(existing):
            shutil.rmtree(existing, ignore_errors=True)

        logs.append("解压中…")
        try:
            root = _extract_archive(archive, target_parent)
        except (tarfile.TarError, OSError, RuntimeError) as exc:
            return False, f"Node.js 解压失败: {exc}", {"log": "\n".join(logs)}

    bindir = os.path.join(root, "bin")
    _link_tools(bindir)
    _write_marker({"version": ver, "folder": os.path.basename(root), "bin_dir": bindir})
    logs.append(f"便携 Node 已安装: {bindir}")

    return True, f"Node.js v{ver} 已安装到 storage/node_ai", {
        "version": ver,
        "root": root,
        "bin_dir": bindir,
        "log": "\n".join(logs),
    }
