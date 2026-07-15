# mcp_tools/net_scan/naabu.py

from typing import Dict, Any
import asyncio


def register_naabu_tool(mcp, hexstrike_client, logger):
    @mcp.tool()
    async def naabu_port_scan(
        host: str = "",
        host_file: str = "",
        ports: str = "",
        top_ports: str = "",
        rate: int = 1000,
        c: int = 25,
        scan_type: str = "c",
        silent: bool = False,
        json_lines: bool = False,
        csv_output: bool = False,
        output: str = "",
        interface: str = "",
        exclude_hosts: str = "",
        verify: bool = False,
        additional_args: str = "",
    ) -> Dict[str, Any]:
        """
        Run ProjectDiscovery Naabu — fast, reliable TCP port enumeration (Go).
        Use for authorized penetration tests and network assessments.

        Args:
            host: Target host(s), comma-separated (maps to -host).
            host_file: Path to file with hosts, one per line (-l).
            ports: Ports to scan, e.g. 80,443 or 1-1000 (-p).
            top_ports: Top ports preset e.g. 100, 1000, full (-top-ports).
            rate: Packets per second (-rate, default 1000).
            c: Worker threads (-c, default 25).
            scan_type: c=CONNECT, s=SYN (-s).
            silent: Only print open ports (-silent).
            json_lines: JSONL output (-json).
            csv_output: CSV output (-csv).
            output: Write results to file (-o).
            interface: Network interface (-i).
            exclude_hosts: Comma-separated hosts to skip (-exclude-hosts).
            verify: TCP re-verify open ports (-verify).
            additional_args: Extra Naabu CLI flags as a single string.

        Returns:
            Command stdout/stderr, exit code, and execution metadata from HexStrike.
        """
        data = {
            "host": host,
            "host_file": host_file,
            "ports": ports,
            "top_ports": top_ports,
            "rate": rate,
            "c": c,
            "scan_type": scan_type,
            "silent": silent,
            "json_lines": json_lines,
            "csv": csv_output,
            "output": output,
            "interface": interface,
            "exclude_hosts": exclude_hosts,
            "verify": verify,
            "additional_args": additional_args,
        }
        logger.info("🔌 MCP Naabu: host=%s list_file=%s", host or "—", host_file or "—")
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None, lambda: hexstrike_client.safe_post("api/tools/naabu", data)
        )
        if result.get("success"):
            logger.info("✅ Naabu completed")
        else:
            logger.error("❌ Naabu failed: %s", result.get("error", result.get("stderr", ""))[:500])
        return result
