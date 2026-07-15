#!/usr/bin/env python3
"""HFinger 指纹库 MCP — Claude Code 可调用 fingerprint_scan / fingerprint_search 等。"""

from __future__ import annotations

import json
import os
import sys

_ROOT = os.environ.get("TONGLING_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from fastmcp import FastMCP

from tongling_web.library_service import get_fingerprint_library

mcp = FastMCP("HFinger 指纹库")
_lib = get_fingerprint_library()


@mcp.tool()
def fingerprint_stats() -> str:
    """返回 HFinger 指纹库统计（条目数、分类、数据文件路径）。"""
    return json.dumps(_lib.stats(), ensure_ascii=False)


@mcp.tool()
def fingerprint_search(q: str = "", category: str = "", limit: int = 20) -> str:
    """按关键词/分类搜索指纹规则。recon 阶段可先 search 再 probe。"""
    return json.dumps(_lib.search(q=q, category=category, limit=limit), ensure_ascii=False)


@mcp.tool()
def fingerprint_probe(target: str, fingerprint_id: str) -> str:
    """对单个目标探测指定指纹 ID（来自 fingerprint_search）。"""
    return json.dumps(_lib.probe(target, fingerprint_id), ensure_ascii=False)


@mcp.tool()
def fingerprint_scan(target: str, category: str = "", limit: int = 15) -> str:
    """批量指纹识别目标技术栈（recon 优先使用）。命中后请将组件名传给 nuclei_scan 的 identified_products 做定向 POC 挖掘。"""
    return json.dumps(_lib.scan(target, category=category, limit=limit), ensure_ascii=False)


if __name__ == "__main__":
    try:
        mcp.run(show_banner=False)
    except TypeError:
        mcp.run()
