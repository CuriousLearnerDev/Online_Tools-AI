# mcp_tools/net_scan/kscan.py

from typing import Any, Dict
import asyncio


def register_kscan_tool(mcp, hexstrike_client, logger):
    @mcp.tool()
    async def kscan_scan(
        target: str = "",
        fofa: str = "",
        use_spy: bool = False,
        spy_scope: str = "",
        fofa_syntax: bool = False,
        check: bool = False,
        scan: bool = False,
        port: str = "",
        output: str = "",
        output_json: str = "",
        output_csv: str = "",
        Pn: bool = False,
        Cn: bool = False,
        Dn: bool = False,
        sV: bool = False,
        top: int = 0,
        proxy: str = "",
        threads: int = 0,
        path: str = "",
        request_host: str = "",
        timeout: int = 0,
        encoding: str = "",
        match: str = "",
        not_match: str = "",
        hydra: bool = False,
        hydra_user: str = "",
        hydra_pass: str = "",
        hydra_update: bool = False,
        hydra_mod: str = "",
        fofa_size: int = 0,
        fofa_fix_keyword: str = "",
        additional_args: str = "",
    ) -> Dict[str, Any]:
        """
        Run Kscan — Go scanner for ports, service fingerprints, and optional brute (hydra) / FOFA / spy.
        Authorized use only.

        Args:
            target: -t / --target (IP, CIDR, range, URL, file:/path, paste/clipboard).
            fofa: -f / --fofa query (needs FOFA_EMAIL, FOFA_KEY).
            use_spy: Enable --spy (LAN segment discovery); combine with scan for port scan.
            spy_scope: Optional after --spy: 192, 10, 172, all, or an IP for B-class gateway probe.
            fofa_syntax: Print FOFA syntax help (--fofa-syntax).
            check: Fingerprint only, no port scan (--check).
            scan: Port scan + fingerprint for fofa/spy targets (--scan).
            port: -p ports (e.g. 80,8080,8088-8090).
            output: -o save text result path.
            output_json: -oJ JSON output path.
            output_csv: -oC CSV output path.
            Pn: Skip smart host discovery (-Pn).
            Cn: No ANSI color (-Cn).
            Dn: Disable CDN detection (-Dn).
            sV: Full probe all ports, slow (-sV).
            top: --top N common ports (default tool TOP400); 0 = omit.
            proxy: --proxy socks5|http(s)://host:port.
            threads: --threads; 0 = tool default.
            path: --path single URL directory for HTTP requests.
            request_host: --host header for all requests.
            timeout: --timeout seconds; 0 = omit.
            encoding: --encoding gb2312 or utf-8.
            match: --match banner keyword filter.
            not_match: --not-match banner exclude.
            hydra: Enable automated hydra modules (--hydra).
            hydra_user: --hydra-user.
            hydra_pass: --hydra-pass.
            hydra_update: --hydra-update (append to default dicts).
            hydra_mod: --hydra-mod e.g. rdp,ssh.
            fofa_size: --fofa-size; 0 = omit.
            fofa_fix_keyword: --fofa-fix-keyword ({} replaced by -f value).
            additional_args: Extra CLI appended as-is.

        Returns:
            HexStrike execute result (stdout/stderr, return code).
        """
        data: Dict[str, Any] = {
            "target": target,
            "fofa": fofa,
            "use_spy": use_spy,
            "spy_scope": spy_scope,
            "fofa_syntax": fofa_syntax,
            "check": check,
            "scan": scan,
            "port": port,
            "output": output,
            "output_json": output_json,
            "output_csv": output_csv,
            "Pn": Pn,
            "Cn": Cn,
            "Dn": Dn,
            "sV": sV,
            "top": top,
            "proxy": proxy,
            "threads": threads,
            "path": path,
            "request_host": request_host,
            "timeout": timeout,
            "encoding": encoding,
            "match": match,
            "not_match": not_match,
            "hydra": hydra,
            "hydra_user": hydra_user,
            "hydra_pass": hydra_pass,
            "hydra_update": hydra_update,
            "hydra_mod": hydra_mod,
            "fofa_size": fofa_size,
            "fofa_fix_keyword": fofa_fix_keyword,
            "additional_args": additional_args,
        }
        logger.info("🛰 MCP Kscan: target=%s fofa=%s spy=%s", target or "—", fofa or "—", use_spy)
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None, lambda: hexstrike_client.safe_post("api/tools/kscan", data)
        )
        if result.get("success"):
            logger.info("✅ Kscan completed")
        else:
            logger.error(
                "❌ Kscan failed: %s",
                (result.get("error") or result.get("stderr") or "")[:500],
            )
        return result
