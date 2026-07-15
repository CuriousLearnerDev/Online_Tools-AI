"""同步统领工具 API 到旧版 HexStrike 安装，并在 Flask 上注册路由。"""

from __future__ import annotations

import logging
import os
import shutil
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from flask import Flask

logger = logging.getLogger(__name__)

_PATCH_ROOT = os.path.join(os.path.dirname(__file__), "hexstrike_patch")

_PATCH_FILES = (
    ("server_api/tongling/__init__.py", "server_api/tongling/__init__.py"),
    ("server_api/tongling/tools.py", "server_api/tongling/tools.py"),
    ("server_core/tongling_tool_catalog.py", "server_core/tongling_tool_catalog.py"),
    ("server_core/tongling_tool_runner.py", "server_core/tongling_tool_runner.py"),
)


def _needs_sync(hexstrike_root: str) -> bool:
    marker = os.path.join(hexstrike_root, "server_api", "tongling", "tools.py")
    return not os.path.isfile(marker)


def sync_hexstrike_tongling_modules(hexstrike_root: str) -> bool:
    """将 bundled patch 复制到 HexStrike 目录（仅当缺失时）。"""
    if not _needs_sync(hexstrike_root):
        return True
    if not os.path.isdir(_PATCH_ROOT):
        logger.warning("hexstrike_patch 目录不存在，无法同步统领工具 API")
        return False

    ok = True
    for rel_src, rel_dst in _PATCH_FILES:
        src = os.path.join(_PATCH_ROOT, rel_src)
        dst = os.path.join(hexstrike_root, rel_dst)
        if not os.path.isfile(src):
            logger.warning("缺少 patch 文件: %s", rel_src)
            ok = False
            continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        logger.info("已同步 HexStrike 模块: %s", rel_dst)
    return ok


def register_hexstrike_tongling_api(app: "Flask", hexstrike_root: str) -> bool:
    """确保统领 /api/tongling/* 路由已注册（兼容旧版 HexStrike）。"""
    if hexstrike_root not in sys.path:
        sys.path.insert(0, hexstrike_root)

    sync_hexstrike_tongling_modules(hexstrike_root)

    if "api_tongling_tools" in app.blueprints:
        return True

    try:
        from server_api.tongling.tools import (  # noqa: WPS433
            api_tongling_tools_bp,
            register_tongling_alias_routes,
        )
    except ImportError as exc:
        logger.warning("无法加载统领工具 API: %s", exc)
        return False

    app.register_blueprint(api_tongling_tools_bp)
    register_tongling_alias_routes(app)
    logger.info("已注册统领工具 API (/api/tongling/stats 等)")
    return True
