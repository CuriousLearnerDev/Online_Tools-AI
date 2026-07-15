# mcp_tools/fingerprint/ehole.py
from typing import Dict, Any
import asyncio

def register_ehole_tool(mcp, hexstrike_client, logger):
    @mcp.tool()
    async def ehole_finger(
        url: str,
        thread: int = 100,
        proxy: str = "",
        output: str = "",
        config: str = "",
        additional_args: str = "",
    ) -> Dict[str, Any]:
        """
        EHole 单目标指纹识别（finger -u）。

        Args:
            url: 目标 URL，例如 https://www.zssnp.top
            thread: 指纹识别线程大小（默认 100）
            proxy: 代理，例如 http://127.0.0.1:8080 或 socks5://127.0.0.1:1080
            output: 输出文件（仅 json/xlsx 后缀）
            config: ehole 配置文件路径 (--config)
            additional_args: 其它额外参数（谨慎使用）

        Returns:
            后端 /api/tools/ehole 的标准 JSON 返回
        """
        data = {
            "url": url,
            "thread": thread,
            "proxy": proxy,
            "output": output,
            "config": config,
            "additional_args": additional_args,
        }
        logger.info(f"🔍 调用 EHole: {data}")

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None, lambda: hexstrike_client.safe_post("api/tools/ehole", data)
        )

        if result.get("success"):
            logger.info("✅ EHole 执行成功")
        else:
            logger.error(f"❌ EHole 执行失败: {result.get('error')}")
        return result
