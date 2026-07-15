# mcp_tools/tongling/tools.py
"""MCP tools for Tongling storage tools (tools_config + toollist CLI)."""

from __future__ import annotations

import asyncio
from typing import Any, Dict

from server_core.tongling_tool_catalog import catalog_stats


def register_tongling_tools(mcp, hexstrike_client, logger):
  @mcp.tool()
  async def list_tongling_tools(
      installed_only: bool = False,
      category: str = "",
  ) -> Dict[str, Any]:
      """
      List security tools available from Tongling storage (tools_config.json + toollist CLI tools).
      Use before run_tongling_tool to discover aliases and usage examples.

      Args:
          installed_only: If true, only return tools with binaries present on disk
          category: Optional filter (recon, web_scan, network_recon, tongling, ...)

      Returns:
          Catalog with tool aliases, descriptions, and usage examples
      """
      params = {}
      if installed_only:
          params["installed_only"] = "true"
      if category:
          params["category"] = category
      loop = asyncio.get_running_loop()
      return await loop.run_in_executor(
          None,
          lambda: hexstrike_client.safe_get("api/tongling/catalog", params=params),
      )

  @mcp.tool()
  async def run_tongling_tool(
      tool: str,
      target: str = "",
      args: str = "",
      timeout: int = 600,
  ) -> Dict[str, Any]:
      """
      Execute a Tongling-packaged security tool by alias.
      Covers tools from统领 storage/tools_config.json and CLI tools from toollist.json
      that are not yet exposed as dedicated HexStrike MCP tools.

      Examples:
          run_tongling_tool(tool="subjack", target="example.com", args="-ssl -v")
          run_tongling_tool(tool="sslscan", target="example.com:443")
          run_tongling_tool(tool="dddd", args="-t targets.txt")
          run_tongling_tool(tool="jwt_tool", args="<JWT_TOKEN>")

      Args:
          tool: Tool alias (e.g. subjack, sslscan, nosqlmap, jwt_tool, dddd, xray)
          target: Optional target host/URL/domain (auto-mapped for some tools)
          args: Additional CLI arguments passed to the binary
          timeout: Max execution seconds (default 600)

      Returns:
          Command stdout/stderr and return code
      """
      data = {
          "tool": tool,
          "target": target,
          "args": args,
          "timeout": timeout,
      }
      logger.info("统领 MCP 工具: %s", tool)
      loop = asyncio.get_running_loop()
      result = await loop.run_in_executor(
          None,
          lambda: hexstrike_client.safe_post("api/tongling/run", data),
      )
      if result.get("success"):
          logger.info("统领工具 %s 完成", tool)
      else:
          logger.error("统领工具 %s 失败: %s", tool, result.get("error", result.get("stderr", "")))
      return result

  # 统领工具统一走 list_tongling_tools + run_tongling_tool（避免为每个工具单独占 MCP 槽位）
