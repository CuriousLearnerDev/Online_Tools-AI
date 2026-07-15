# mcp_tools/visual_output_tools.py

from typing import Any, Dict, List, Union
import asyncio
import json

def register_visual_output_tools(mcp, hexstrike_client, logger):
    @mcp.tool()
    async def get_live_dashboard() -> Dict[str, Any]:
        """
        Get a beautiful live dashboard showing all active processes with enhanced visual formatting.

        Returns:
            Live dashboard with visual process monitoring and system metrics
        """
        logger.info("📊 Fetching live process dashboard")
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None, lambda: hexstrike_client.safe_get("api/processes/dashboard")
        )
        if result.get("success", True):
            logger.info("✅ Live dashboard retrieved successfully")
        else:
            logger.error("❌ Failed to retrieve live dashboard")
        return result

    @mcp.tool()
    async def create_vulnerability_report(
        vulnerabilities: Union[List[Dict[str, Any]], str],
        target: str = "",
        scan_type: str = "comprehensive",
    ) -> Dict[str, Any]:
        """
        Create a vulnerability report from structured findings (MCP JSON must be valid).

        Args:
            vulnerabilities: **Prefer a JSON array of objects** in the tool arguments, e.g.
                [{"port": 21, "service": "FTP", "risk": "High", "description": "...", ...}, ...].
                Do not put that array inside another JSON string (breaks client-side JSON parsing).
                Legacy: a single string that parses to such an array is still accepted.
            target: Target that was scanned
            scan_type: Type of scan performed

        Returns:
            Formatted vulnerability report with visual enhancements
        """

        def _coerce_vuln_list(raw: Union[List[Dict[str, Any]], str]) -> List[Dict[str, Any]]:
            if isinstance(raw, list):
                out: List[Dict[str, Any]] = []
                for v in raw:
                    out.append(v if isinstance(v, dict) else {"value": v})
                return out
            if isinstance(raw, str):
                s = raw.strip()
                if not s:
                    return []
                try:
                    data = json.loads(s)
                except json.JSONDecodeError as e:
                    raise ValueError(
                        "vulnerabilities must be a JSON array of objects (or a parseable JSON string of one)"
                    ) from e
                for _ in range(3):
                    if isinstance(data, str):
                        try:
                            data = json.loads(data)
                        except json.JSONDecodeError as e:
                            raise ValueError(
                                "vulnerabilities string must parse to a JSON array"
                            ) from e
                    else:
                        break
                if isinstance(data, dict):
                    data = data.get("vulnerabilities", data.get("items", [data]))
                if not isinstance(data, list):
                    raise ValueError("vulnerabilities must decode to a JSON array")
                return [x if isinstance(x, dict) else {"value": x} for x in data]
            raise TypeError("vulnerabilities must be a list or string")

        try:
            vuln_data = _coerce_vuln_list(vulnerabilities)

            logger.info(f"📋 Creating vulnerability report for {len(vuln_data)} findings")

            vulnerability_cards = []
            loop = asyncio.get_running_loop()
            for vuln in vuln_data:
                card_result = await loop.run_in_executor(
                    None,
                    lambda v=vuln: hexstrike_client.safe_post("api/visual/vulnerability-card", v),
                )
                if card_result.get("success"):
                    vulnerability_cards.append(card_result.get("vulnerability_card", ""))

            summary_data = {
                "target": target,
                "vulnerabilities": vuln_data,
                "tools_used": [scan_type],
                "execution_time": 0,
            }

            summary_result = await loop.run_in_executor(
                None, lambda sd=summary_data: hexstrike_client.safe_post("api/visual/summary-report", sd),
            )

            logger.info("✅ Vulnerability report created successfully")
            return {
                "success": True,
                "vulnerability_cards": vulnerability_cards,
                "summary_report": summary_result.get("summary_report", ""),
                "total_vulnerabilities": len(vuln_data),
                "timestamp": summary_result.get("timestamp", "")
            }

        except Exception as e:
            logger.error(f"❌ Failed to create vulnerability report: {str(e)}")
            return {"success": False, "error": str(e)}

    @mcp.tool()
    async def format_tool_output_visual(tool_name: str, output: str, success: bool = True) -> Dict[str, Any]:
        """
        Format tool output with beautiful visual styling, syntax highlighting, and structure.

        Args:
            tool_name: Name of the security tool
            output: Raw output from the tool
            success: Whether the tool execution was successful

        Returns:
            Beautifully formatted tool output with visual enhancements
        """
        logger.info(f"🎨 Formatting output for {tool_name}")

        data = {
            "tool": tool_name,
            "output": output,
            "success": success
        }

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None, lambda: hexstrike_client.safe_post("api/visual/tool-output", data)
        )
        if result.get("success"):
            logger.info(f"✅ Tool output formatted successfully for {tool_name}")
        else:
            logger.error(f"❌ Failed to format tool output for {tool_name}")

        return result

    @mcp.tool()
    async def create_scan_summary(target: str, tools_used: str, vulnerabilities_found: int = 0,
                           execution_time: float = 0.0, findings: str = "") -> Dict[str, Any]:
        """
        Create a comprehensive scan summary report with beautiful visual formatting.

        Args:
            target: Target that was scanned
            tools_used: Comma-separated list of tools used
            vulnerabilities_found: Number of vulnerabilities discovered
            execution_time: Total execution time in seconds
            findings: Additional findings or notes

        Returns:
            Beautiful scan summary report with visual enhancements
        """
        logger.info(f"📊 Creating scan summary for {target}")

        tools_list = [tool.strip() for tool in tools_used.split(",")]

        summary_data = {
            "target": target,
            "tools_used": tools_list,
            "execution_time": execution_time,
            "vulnerabilities": [{"severity": "info"}] * vulnerabilities_found,  # Mock data for count
            "findings": findings
        }

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None, lambda: hexstrike_client.safe_post("api/visual/summary-report", summary_data)
        )
        if result.get("success"):
            logger.info("✅ Scan summary created successfully")
        else:
            logger.error("❌ Failed to create scan summary")

        return result

    @mcp.tool()
    async def display_system_metrics() -> Dict[str, Any]:
        """
        Display current system metrics and performance indicators with visual formatting.

        Returns:
            System metrics with beautiful visual presentation
        """
        logger.info("📈 Fetching system metrics")

        # Get telemetry data
        loop = asyncio.get_running_loop()
        telemetry_result = await loop.run_in_executor(
            None, lambda: hexstrike_client.safe_get("api/telemetry")
        )

        if telemetry_result.get("success", True):
            logger.info("✅ System metrics retrieved successfully")

            # Format the metrics for better display
            metrics = telemetry_result.get("system_metrics", {})
            stats = {
                "cpu_percent": metrics.get("cpu_percent", 0),
                "memory_percent": metrics.get("memory_percent", 0),
                "disk_usage": metrics.get("disk_usage", 0),
                "uptime_seconds": telemetry_result.get("uptime_seconds", 0),
                "commands_executed": telemetry_result.get("commands_executed", 0),
                "success_rate": telemetry_result.get("success_rate", "0%")
            }

            return {
                "success": True,
                "metrics": stats,
                "formatted_display": f"""
🖥️  System Performance Metrics:
├─ CPU Usage: {stats['cpu_percent']:.1f}%
├─ Memory Usage: {stats['memory_percent']:.1f}%
├─ Disk Usage: {stats['disk_usage']:.1f}%
├─ Uptime: {stats['uptime_seconds']:.0f}s
├─ Commands Executed: {stats['commands_executed']}
└─ Success Rate: {stats['success_rate']}
""",
                "timestamp": telemetry_result.get("timestamp", "")
            }
        else:
            logger.error("❌ Failed to retrieve system metrics")
            return telemetry_result
