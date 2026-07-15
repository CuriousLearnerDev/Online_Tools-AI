# mcp_tools/url_recon/urlfinder.py

from typing import Dict, Any
import asyncio


def register_urlfinder_tool(mcp, hexstrike_client, logger):
    @mcp.tool()
    async def urlfinder_js_url_extract(
        url: str = "",
        url_file: str = "",
        url_file_one: str = "",
        user_agent: str = "",
        base_url: str = "",
        cookie: str = "",
        domain: str = "",
        config_file: str = "",
        mode: int = 0,
        max_links: int = 0,
        out_file: str = "",
        status: str = "",
        thread: int = 0,
        timeout_sec: int = 0,
        proxy: str = "",
        fuzz: int = 0,
        additional_args: str = "",
    ) -> Dict[str, Any]:
        """
        Run URLFinder — fast extraction of links and JS URLs from web pages (pingc0y).
        Use on authorized targets to surface hidden or sensitive API paths in front-end assets.

        Args:
            url: Single target URL (-u).
            url_file: Batch URL list file (-f).
            url_file_one: Batch file; merge all results as one logical URL (-ff).
            user_agent: Custom User-Agent (-a).
            base_url: Base URL (-b).
            cookie: Cookie header (-c).
            domain: Domain filter, regex supported (-d).
            config_file: YAML config (-i).
            mode: Crawl mode 1=normal, 2=thorough, 3=security (-m); 0 = omit (tool default).
            max_links: Max URLs to collect (-max); 0 = omit.
            out_file: Export csv/json/html path (-o).
            status: Filter by status codes, comma-separated or all (-s).
            thread: Worker threads (-t); 0 = omit (default 50).
            timeout_sec: Per-request timeout seconds (-time); 0 = omit (default 5).
            proxy: HTTP/SOCKS proxy (-x).
            fuzz: 404 fuzz mode 1–3 (-z); 0 = omit. Often used with -s.
            additional_args: Extra CLI text appended as-is.

        Returns:
            HexStrike command result (stdout/stderr, exit code, timing).
        """
        data = {
            "url": url,
            "url_file": url_file,
            "url_file_one": url_file_one,
            "user_agent": user_agent,
            "base_url": base_url,
            "cookie": cookie,
            "domain": domain,
            "config_file": config_file,
            "mode": mode,
            "max": max_links,
            "out_file": out_file,
            "status": status,
            "thread": thread,
            "timeout": timeout_sec,
            "proxy": proxy,
            "fuzz": fuzz,
            "additional_args": additional_args,
        }
        logger.info(
            "🔗 MCP URLFinder: url=%s file=%s",
            url or "—",
            url_file or url_file_one or "—",
        )
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None, lambda: hexstrike_client.safe_post("api/tools/urlfinder", data)
        )
        if result.get("success"):
            logger.info("✅ URLFinder completed")
        else:
            logger.error(
                "❌ URLFinder failed: %s",
                (result.get("error") or result.get("stderr") or "")[:500],
            )
        return result
