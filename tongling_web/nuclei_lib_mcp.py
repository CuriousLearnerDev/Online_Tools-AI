#!/usr/bin/env python3
"""Nuclei + Afrog POC 库 MCP — 须先指纹识别，再定向漏洞挖掘。"""

from __future__ import annotations

import json
import os
import sys

_ROOT = os.environ.get("TONGLING_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from fastmcp import FastMCP

from tongling_web.library_service import get_nuclei_library

mcp = FastMCP("Nuclei 漏洞库")
_lib = get_nuclei_library()


@mcp.tool()
def nuclei_stats() -> str:
    """返回 POC 库统计（Nuclei + Afrog 索引数、严重级别分布、目录路径）。"""
    return json.dumps(_lib.stats(), ensure_ascii=False)


@mcp.tool()
def nuclei_search(q: str = "", severity: str = "", tags: str = "", source: str = "", limit: int = 20) -> str:
    """搜索 POC 模板（按关键词、severity、tags、来源 nuclei|afrog）。"""
    return json.dumps(_lib.search(q=q, severity=severity, tags=tags, source=source, limit=limit), ensure_ascii=False)


@mcp.tool()
def nuclei_select_pocs(identified_products: str, limit: int = 40) -> str:
    """根据 fingerprint_scan 识别出的组件，预览将用于定向扫描的 POC 列表。"""
    return json.dumps(_lib.select_for_products(identified_products, limit=limit), ensure_ascii=False)


@mcp.tool()
def nuclei_scan(
    target: str,
    identified_products: str,
    severity: str = "critical,high,medium",
    limit: int = 30,
) -> str:
    """定向 POC 扫描：必须先 fingerprint_scan 识别 Web 组件，再传入 identified_products（逗号分隔）。"""
    return json.dumps(
        _lib.scan(target, identified_products=identified_products, severity=severity, limit=limit),
        ensure_ascii=False,
    )


@mcp.tool()
def poc_sync() -> str:
    """从 GitHub 拉取最新 Nuclei 模板与 Afrog POC（默认代理 127.0.0.1:7897），并重建索引。"""
    from tongling_web.library_sync import sync_all_poc_libraries

    _lib.reload()
    return json.dumps(sync_all_poc_libraries(), ensure_ascii=False)


@mcp.tool()
def nuclei_reindex() -> str:
    """仅重建本地 POC 索引缓存（不拉取 GitHub）。"""
    _lib.reload()
    return json.dumps(_lib.reindex(), ensure_ascii=False)


if __name__ == "__main__":
    try:
        mcp.run(show_banner=False)
    except TypeError:
        mcp.run()
