# mcp_tools/vuln_scan/afrog.py
from typing import Any, Dict
import asyncio


def register_afrog_tool(mcp, hexstrike_client, logger):
    @mcp.tool()
    async def afrog_scan(
        target: str,
        severity: str = "",
        search: str = "",
        rate_limit: int = 0,
        concurrency: int = 0,
        proxy: str = "",
        port_scan: bool = False,
        ports: str = "",
        skip_host_discovery: bool = False,
        output_html: str = "",
        output_json: str = "",
        silent: bool = False,
        additional_args: str = "",
    ) -> Dict[str, Any]:
        """
        Afrog: high-performance PoC-based vulnerability scanner (CVE/CNVD, misconfig, leaks, etc.).

        Typical usage: pass a single URL or host as target (same as CLI `afrog -t`).
        Optional presets: filter by severity (-S), PoC keyword (-s), rate limit (-rl),
        concurrency (-c), proxy, or enable port pre-scan (-ps) with ports (-p).

        Args:
            target: URL or host to scan (comma-separated for multiple targets)
            severity: Run PoCs for these levels only: info, low, medium, high, critical, unknown
            search: Keyword to filter PoCs (e.g. tomcat,phpinfo)
            rate_limit: Max HTTP requests per second (0 = afrog default)
            concurrency: Max parallel PoCs (0 = afrog default)
            proxy: HTTP/SOCKS5 proxy URL
            port_scan: If true, run port pre-scan (-ps) before PoCs
            ports: With port_scan, e.g. 80,443,8080 or all
            skip_host_discovery: If true, pass -Pn (use with port scan flows)
            output_html: Write HTML report to this path (-o)
            output_json: Write JSON results (-j)
            silent: If true, only print findings (-silent)
            additional_args: Extra CLI arguments (space-separated, use with care)

        Returns:
            Standard JSON from POST /api/tools/afrog (stdout, stderr, return_code, success, …)
        """
        data: Dict[str, Any] = {
            "target": target,
            "severity": severity,
            "search": search,
            "rate_limit": rate_limit,
            "concurrency": concurrency,
            "proxy": proxy,
            "port_scan": port_scan,
            "ports": ports,
            "skip_host_discovery": skip_host_discovery,
            "output_html": output_html,
            "output_json": output_json,
            "silent": silent,
            "additional_args": additional_args,
        }
        logger.info(f"🐸 Afrog scan: {data.get('target')}")

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None, lambda: hexstrike_client.safe_post("api/tools/afrog", data)
        )

        if result.get("success"):
            logger.info("✅ Afrog finished")
        else:
            logger.error(f"❌ Afrog failed: {result.get('error', result.get('stderr', ''))}")
        return result
