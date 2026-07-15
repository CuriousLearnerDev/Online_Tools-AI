# mcp_tools/vuln_scan/springboot_scan.py
from typing import Any, Dict
import asyncio


def register_springboot_scan_tool(mcp, hexstrike_client, logger):
    @mcp.tool(name="springboot-scan")
    async def springboot_scan(
        target: str = "",
        url: str = "",
        url_file: str = "",
        vul: str = "",
        vul_file: str = "",
        dump: str = "",
        dump_file: str = "",
        proxy: str = "",
        zoomeye: str = "",
        fofa: str = "",
        hunter: str = "",
        newheader: str = "",
        cookie: str = "",
        show_help: bool = False,
        scan_timeout: int = 3600,
        additional_args: str = "",
    ) -> Dict[str, Any]:
        """
        SpringBoot-Scan：针对 SpringBoot / Spring 的信息泄露扫描、漏洞利用与敏感文件下载（开源框架，仅用于授权测试）。

        与 CLI 对应：``url`` 或 ``target``→-u（与其它工具一致可只传 target），``url_file``→-uf，
        ``vul``→-v，``vul_file``→-vf，``dump``→-d，``dump_file``→-df，``proxy``→-p，
        ``zoomeye``→-z，``fofa``→-f，``hunter``→-y，``newheader``→-t，``cookie``→-c。
        ``show_help`` 为 True 时等价命令行 ``SpringBoot-Scan -h``。

        Args:
            target: 单目标 URL，与 url 相同含义 (-u)，AI 调用时优先使用
            url: 单 URL 信息泄露扫描 (-u)
            url_file: 目标列表 TXT (-uf)
            vul: 单 URL 漏洞利用 (-v)
            vul_file: 批量漏洞扫描 TXT (-vf)
            dump: 扫描并下载敏感文件 (-d)
            dump_file: 批量敏感文件扫描 TXT (-df)
            proxy: HTTP 代理 host:port (-p)
            zoomeye: ZoomEye API Key (-z)
            fofa: Fofa API Key (-f)
            hunter: Hunter API Key (-y)
            newheader: 自定义 HTTP 头 TXT 路径 (-t)
            cookie: 请求 Cookie (-c)
            show_help: 为 True 时只打印帮助 (-h)
            scan_timeout: 子进程超时（秒）
            additional_args: 额外 CLI 参数（空格分隔）

        Returns:
            POST /api/tools/springboot-scan 的 JSON（stdout、return_code、success 等）
        """
        data: Dict[str, Any] = {
            "target": target,
            "url": url,
            "url_file": url_file,
            "vul": vul,
            "vul_file": vul_file,
            "dump": dump,
            "dump_file": dump_file,
            "proxy": proxy,
            "zoomeye": zoomeye,
            "fofa": fofa,
            "hunter": hunter,
            "newheader": newheader,
            "cookie": cookie,
            "help": show_help,
            "show_help": show_help,
            "scan_timeout": scan_timeout,
            "additional_args": additional_args,
        }
        logger.info("SpringBoot-Scan: %s", data)

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None, lambda: hexstrike_client.safe_post("api/tools/springboot-scan", data)
        )

        if result.get("success"):
            logger.info("SpringBoot-Scan finished")
        else:
            logger.error(
                "SpringBoot-Scan failed: %s",
                result.get("error", result.get("stderr", "")),
            )
        return result
