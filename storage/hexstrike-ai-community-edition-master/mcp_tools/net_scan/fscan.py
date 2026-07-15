# mcp_tools/net_scan/fscan.py
from typing import Any, Dict
import asyncio


def register_fscan_tool(mcp, hexstrike_client, logger):
    @mcp.tool()
    async def fscan_scan(
        target: str = "",
        url: str = "",
        host_file: str = "",
        url_file: str = "",
        local: bool = False,
        ports: str = "",
        modules: str = "",
        output: str = "",
        output_format: str = "",
        threads: int = 0,
        nopoc: bool = False,
        full: bool = False,
        dns: bool = False,
        additional_args: str = "",
        scan_timeout: int = 7200,
    ) -> Dict[str, Any]:
        """
        Fscan: integrated internal-network scanner (live hosts, ports, services, web title, POCs).
        Use only on networks you are authorized to test.

        Provide at least one of: target (-h), url (-u), host_file (-hf), url_file (-uf), or local=true.

        Args:
            target: Host/IP/CIDR/range for -h (e.g. 192.168.1.1-255, 192.168.1.0/24)
            url: Single URL for -u
            host_file: Path to host list (-hf)
            url_file: Path to URL list (-uf)
            local: Enable local info collection (-local)
            ports: -p (e.g. main, 80,443, 1-1000)
            modules: -m (e.g. all, ssh,redis, ms17010)
            output: -o result file
            output_format: -f txt/json/csv
            threads: -t thread count (0 = default)
            nopoc: -nopoc
            full: -full (full POC e.g. Shiro keys)
            dns: -dns (dnslog)
            additional_args: Extra CLI (space-separated)
            scan_timeout: Subprocess wall-clock limit (seconds)

        Returns:
            JSON from POST /api/tools/fscan
        """
        data: Dict[str, Any] = {
            "target": target,
            "url": url,
            "host_file": host_file,
            "url_file": url_file,
            "local": local,
            "ports": ports,
            "modules": modules,
            "output": output,
            "output_format": output_format,
            "threads": threads,
            "nopoc": nopoc,
            "full": full,
            "dns": dns,
            "additional_args": additional_args,
            "scan_timeout": scan_timeout,
        }
        logger.info("Fscan: %s", {k: v for k, v in data.items() if v not in ("", 0, False)})
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None, lambda: hexstrike_client.safe_post("api/tools/fscan", data)
        )
        if result.get("success"):
            logger.info("Fscan finished")
        else:
            logger.error("Fscan failed: %s", result.get("error", result.get("stderr", "")))
        return result
