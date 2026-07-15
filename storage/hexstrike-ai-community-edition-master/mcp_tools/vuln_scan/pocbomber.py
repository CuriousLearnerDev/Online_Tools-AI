# mcp_tools/vuln_scan/pocbomber.py
from typing import Any, Dict
import asyncio


def register_pocbomber_tool(mcp, hexstrike_client, logger):
    @mcp.tool()
    async def pocbomber_scan(
        target: str = "",
        url_file: str = "",
        show: bool = False,
        poc: str = "",
        output: str = "",
        thread: int = 0,
        attack: bool = False,
        dnslog: bool = False,
        scan_timeout: int = 3600,
        additional_args: str = "",
    ) -> Dict[str, Any]:
        """
        PocBomber: PoC/exp batch scanner for quick validation and red-team-style triage (tr0uble-mAker / GitHub).

        Typical: single URL scan with ``target`` (maps to ``-u``). For URL list use ``url_file`` (``-f``).
        Use ``show=true`` to list bundled PoC/exp metadata (``--show``). ``attack`` enables exploit mode
        (``--attack``) — only on systems you are authorized to test.

        Args:
            target: Target URL (-u), e.g. https://192.168.1.1
            url_file: Path to file containing URLs (-f) for batch mode
            show: If true, run --show (PoC/exp listing); target/file ignored
            poc: Comma-separated poc script names (--poc), e.g. thinkphp2_rce.py
            output: Report file path (-o)
            thread: Thread pool max (-t); 0 = use tool default (30)
            attack: Exp/attack mode (--attack)
            dnslog: Enable dnslog for blind checks (--dnslog)
            scan_timeout: Subprocess wall-clock limit in seconds
            additional_args: Extra CLI arguments (space-separated)

        Returns:
            JSON from POST /api/tools/pocbomber (stdout, stderr, return_code, success, …)
        """
        data: Dict[str, Any] = {
            "target": target,
            "file": url_file,
            "show": show,
            "poc": poc,
            "output": output,
            "thread": thread,
            "attack": attack,
            "dnslog": dnslog,
            "scan_timeout": scan_timeout,
            "additional_args": additional_args,
        }
        logger.info("PocBomber: %s", data)

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None, lambda: hexstrike_client.safe_post("api/tools/pocbomber", data)
        )

        if result.get("success"):
            logger.info("PocBomber finished")
        else:
            logger.error("PocBomber failed: %s", result.get("error", result.get("stderr", "")))
        return result
