# mcp_tools/intelligent_decision_engine.py

"""
本文件属于 MCP（Model Context Protocol）工具注册层：

- 作用：把 HexStrike Server 的 AI/情报类 HTTP API 封装成 MCP 工具，供 AI 渗透终端/外部 AI 客户端调用。
- 设计：MCP 工具本身不做重逻辑，主要负责参数整理、调用后端 endpoint、以及做少量日志与错误处理。
- 调用链（常见）：
  1) analyze_target_intelligence  -> 目标画像（轻量）
  2) select_optimal_tools_ai      -> 根据画像/目标选择工具（策略）
  3) optimize_tool_parameters_ai  -> 给某个工具生成推荐参数（参数层）
  4) intelligent_smart_scan       -> 端到端：画像→选工具→并发执行→汇总（会真正跑工具）
  5) create_attack_chain_ai       -> 生成“攻击链计划”（不直接执行）

注意：
- 本项目同时存在单文件版 `storage/hexstrike_mcp.py` 与分模块版 `mcp_tools/*`。
  你当前编辑的是分模块版（profile 控制加载哪些工具）。
"""

from typing import Dict, Any
from datetime import datetime
import asyncio

def register_intelligent_decision_engine_tools(mcp, hexstrike_client, logger, HexStrikeColors):
    @mcp.tool()
    async def analyze_target_intelligence(target: str) -> Dict[str, Any]:
        """
        【目标画像】分析目标并生成 target_profile（轻量情报，不等价于全量实扫）。

        后端接口：
        - POST `api/intelligence/analyze-target`

        适用输入：
        - 域名：`example.com`
        - URL：`https://example.com`
        - IP：`1.2.3.4`

        返回说明（常见字段）：
        - `target_profile.target_type`: web_application / api_endpoint / network_host ...
        - `ip_addresses`: DNS 解析出来的 IP（可能为空）
        - `technologies`: 技术栈推断（可能为 unknown）
        - `open_ports/subdomains/endpoints`: 可能为空（因为本接口默认不做深度实扫）

        Args:
            target: 需要分析的目标（域名/URL/IP）

        Returns:
            result(dict): 后端返回 JSON，包含 `success/target_profile/timestamp` 等
        """
        logger.info(f"🧠 Analyzing target intelligence for: {target}")

        data = {"target": target}
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None, lambda: hexstrike_client.safe_post("a pi/intelligence/analyze-target", data)
        )

        if result.get("success"):
            profile = result.get("target_profile", {})
            logger.info(f"✅ Target analysis completed - Type: {profile.get('target_type')}, Risk: {profile.get('risk_level')}")
        else:
            logger.error(f"❌ Target analysis failed for {target}")

        return result

    @mcp.tool()
    async def select_optimal_tools_ai(target: str, objective: str = "comprehensive") -> Dict[str, Any]:
        """
        【工具推荐】根据目标画像 + 目标（objective）返回推荐工具列表。

        后端接口：
        - POST `api/intelligence/select-tools`

        objective 常用值：
        - comprehensive：覆盖优先（更“全”）
        - quick：速度优先（快速摸底）
        - stealth：隐蔽优先（减少噪音）

        提示：
        - 本接口只“推荐”，不执行工具。想直接跑可用 `intelligent_smart_scan`。

        Args:
            target: 目标（域名/URL/IP）
            objective: 扫描目标策略（comprehensive/quick/stealth）

        Returns:
            result(dict): 通常包含 `selected_tools` 与 `target_profile`
        """
        logger.info(f"🎯 Selecting optimal tools for {target} with objective: {objective}")

        data = {
            "target": target,
            "objective": objective
        }
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None, lambda: hexstrike_client.safe_post("api/intelligence/select-tools", data)
        )

        if result.get("success"):
            tools = result.get("selected_tools", [])
            logger.info(f"✅ AI selected {len(tools)} optimal tools: {', '.join(tools[:3])}{'...' if len(tools) > 3 else ''}")
        else:
            logger.error(f"❌ Tool selection failed for {target}")

        return result

    @mcp.tool()
    async def optimize_tool_parameters_ai(target: str, tool: str, context: str = "{}") -> Dict[str, Any]:
        """
        【参数优化】给指定工具生成“更适配该目标”的参数建议。

        后端接口：
        - POST `api/intelligence/optimize-parameters`

        context：
        - 以 JSON 字符串传入（例如 `{"stealth": true, "aggressive": false}`）
        - 解析失败会回退为 `{}`，避免因为格式问题中断流程

        常见调用方式：
        - 先 `analyze_target_intelligence`
        - 再对某个 tool 调本接口拿参数
        - 最后调用具体工具接口（如 nuclei/ffuf/gobuster 等）

        Args:
            target: 目标
            tool: 工具名（例如 "nuclei" / "nmap" / "ffuf"）
            context: JSON 字符串形式的额外上下文/偏好

        Returns:
            result(dict): 通常包含 `optimized_parameters`
        """
        import json

        logger.info(f"⚙️  Optimizing parameters for {tool} against {target}")

        # 兼容处理：如果 context 已经是 dict，直接使用
        if isinstance(context, dict):
            context_dict = context
        else:
            try:
                # 如果是字符串，尝试解析 JSON
                context_dict = json.loads(context) if context and context != "{}" else {}
            except json.JSONDecodeError:
                context_dict = {}

        data = {
            "target": target,
            "tool": tool,
            "context": context_dict
        }
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None, lambda: hexstrike_client.safe_post("api/intelligence/optimize-parameters", data)
        )

        if result.get("success"):
            params = result.get("optimized_parameters", {})
            logger.info(f"✅ Parameters optimized for {tool} - {len(params)} parameters configured")
        else:
            logger.error(f"❌ Parameter optimization failed for {tool}")

        return result

    @mcp.tool()
    async def create_attack_chain_ai(target: str, objective: str = "comprehensive") -> Dict[str, Any]:
        """
        【攻击链计划】生成攻击链（步骤/顺序/预估成功率等），用于编排与人工复核。

        后端接口：
        - POST `api/intelligence/create-attack-chain`

        注意：
        - 这是“计划生成”，不直接执行工具进程。

        Args:
            target: 目标
            objective: 目标策略（comprehensive/quick/stealth）

        Returns:
            result(dict): 通常包含 `attack_chain`
        """
        logger.info(f"⚔️  Creating AI-driven attack chain for {target}")

        data = {
            "target": target,
            "objective": objective
        }
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None, lambda: hexstrike_client.safe_post("api/intelligence/create-attack-chain", data)
        )

        if result.get("success"):
            chain = result.get("attack_chain", {})
            steps = len(chain.get("steps", []))
            success_prob = chain.get("success_probability", 0)
            estimated_time = chain.get("estimated_time", 0)

            logger.info(f"✅ Attack chain created - {steps} steps, {success_prob:.2f} success probability, ~{estimated_time}s")
        else:
            logger.error(f"❌ Attack chain creation failed for {target}")

        return result

    @mcp.tool()
    async def intelligent_smart_scan(target: str, objective: str = "comprehensive", max_tools: int = 5) -> Dict[str, Any]:
        """
        【端到端智能扫描】画像 → 选工具 → 并发执行 → 汇总输出（会真正执行工具）。

        后端接口：
        - POST `api/intelligence/smart-scan`

        特点：
        - 会调用多个工具（可能很多条命令）
        - 受后端环境影响很大（Windows 下某些 Linux 工具不可用，会失败）
        - max_tools 用于限制执行工具数量，避免压垮主机或刷屏

        Args:
            target: 目标
            objective: 策略（comprehensive/quick/stealth）
            max_tools: 最多执行多少个工具（越大越慢/越吵）

        Returns:
            result(dict): 通常包含 `scan_results` 与执行摘要 `execution_summary`
        """
        logger.info(f"{HexStrikeColors.FIRE_RED}🚀 Starting intelligent smart scan for {target}{HexStrikeColors.RESET}")

        data = {
            "target": target,
            "objective": objective,
            "max_tools": max_tools
        }
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None, lambda: hexstrike_client.safe_post("api/intelligence/smart-scan", data)
        )

        if result.get("success"):
            scan_results = result.get("scan_results", {})
            tools_executed = scan_results.get("tools_executed", [])
            execution_summary = scan_results.get("execution_summary", {})

            # Enhanced logging with detailed results
            logger.info(f"{HexStrikeColors.SUCCESS}✅ Intelligent scan completed for {target}{HexStrikeColors.RESET}")
            logger.info(f"{HexStrikeColors.CYBER_ORANGE}📊 Execution Summary:{HexStrikeColors.RESET}")
            logger.info(f"   • Tools executed: {execution_summary.get('successful_tools', 0)}/{execution_summary.get('total_tools', 0)}")
            logger.info(f"   • Success rate: {execution_summary.get('success_rate', 0):.1f}%")
            logger.info(f"   • Total vulnerabilities: {scan_results.get('total_vulnerabilities', 0)}")
            logger.info(f"   • Execution time: {execution_summary.get('total_execution_time', 0):.2f}s")

            # Log successful tools
            successful_tools = [t['tool'] for t in tools_executed if t.get('success')]
            if successful_tools:
                logger.info(f"{HexStrikeColors.HIGHLIGHT_GREEN} Successful tools: {', '.join(successful_tools)} {HexStrikeColors.RESET}")

            # Log failed tools
            failed_tools = [t['tool'] for t in tools_executed if not t.get('success')]
            if failed_tools:
                logger.warning(f"{HexStrikeColors.HIGHLIGHT_RED} Failed tools: {', '.join(failed_tools)} {HexStrikeColors.RESET}")

            # Log vulnerabilities found
            if scan_results.get('total_vulnerabilities', 0) > 0:
                logger.warning(f"{HexStrikeColors.VULN_HIGH}🚨 {scan_results['total_vulnerabilities']} vulnerabilities detected!{HexStrikeColors.RESET}")
        else:
            logger.error(f"{HexStrikeColors.ERROR}❌ Intelligent scan failed for {target}: {result.get('error', 'Unknown error')}{HexStrikeColors.RESET}")

        return result

    @mcp.tool()
    async def detect_technologies_ai(target: str) -> Dict[str, Any]:
        """
        【技术栈识别】识别技术栈并给出针对性建议（偏“建议/画像”，不是漏洞验证）。

        后端接口：
        - POST `api/intelligence/technology-detection`

        Args:
            target: 目标

        Returns:
            result(dict): 包含 `detected_technologies/cms_type/technology_recommendations`
        """
        logger.info(f"🔍 Detecting technologies for {target}")

        data = {"target": target}
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None, lambda: hexstrike_client.safe_post("api/intelligence/technology-detection", data)
        )

        if result.get("success"):
            technologies = result.get("detected_technologies", [])
            cms = result.get("cms_type")
            recommendations = result.get("technology_recommendations", {})

            tech_info = f"Technologies: {', '.join(technologies)}"
            if cms:
                tech_info += f", CMS: {cms}"

            logger.info(f"✅ Technology detection completed - {tech_info}")
            logger.info(f"📋 Generated {len(recommendations)} technology-specific recommendations")
        else:
            logger.error(f"❌ Technology detection failed for {target}")

        return result

    @mcp.tool()
    async def ai_reconnaissance_workflow(target: str, depth: str = "standard") -> Dict[str, Any]:
        """
        【侦察工作流】把“画像/攻击链/扫描”串起来的一条龙流程。

        后端接口组合：
        - analyze-target
        - create-attack-chain
        - smart-scan

        depth：
        - surface：浅层，工具更少、更快
        - standard：默认
        - deep：更深，工具更多、更慢

        Args:
            target: 目标
            depth: 深度（surface/standard/deep）

        Returns:
            result(dict): 组合返回（target_analysis/attack_chain/scan_results）
        """
        logger.info(f"🕵️  Starting AI reconnaissance workflow for {target} (depth: {depth})")

        # First analyze the target
        loop = asyncio.get_running_loop()
        analysis_result = await loop.run_in_executor(
            None, lambda: hexstrike_client.safe_post("api/intelligence/analyze-target", {"target": target})
        )

        if not analysis_result.get("success"):
            return analysis_result

        # Create attack chain for reconnaissance
        objective = "comprehensive" if depth == "deep" else "quick" if depth == "surface" else "comprehensive"
        loop = asyncio.get_running_loop()
        chain_result = await loop.run_in_executor(
            None, lambda: hexstrike_client.safe_post("api/intelligence/create-attack-chain", {
            "target": target,
            "objective": objective
        })
        )

        if not chain_result.get("success"):
            return chain_result

        # Execute the reconnaissance
        loop = asyncio.get_running_loop()
        scan_result = await loop.run_in_executor(
            None, lambda: hexstrike_client.safe_post("api/intelligence/smart-scan", {
            "target": target,
            "objective": objective,
            "max_tools": 8 if depth == "deep" else 3 if depth == "surface" else 5
        })
        )

        logger.info(f"✅ AI reconnaissance workflow completed for {target}")

        return {
            "success": True,
            "target": target,
            "depth": depth,
            "target_analysis": analysis_result.get("target_profile", {}),
            "attack_chain": chain_result.get("attack_chain", {}),
            "scan_results": scan_result.get("scan_results", {}),
            "timestamp": datetime.now().isoformat()
        }

    @mcp.tool()
    async def ai_vulnerability_assessment(target: str, focus_areas: str = "all") -> Dict[str, Any]:
        """
        【漏洞评估工作流】根据 focus_areas 选择策略后执行 smart-scan，并汇总风险评估。

        focus_areas：
        - "all"：默认
        - "web" / "network" / "api"：可按逗号分隔组合（此处实现是简单包含判断）

        Args:
            target: 目标
            focus_areas: 关注面（web/network/api/all）

        Returns:
            result(dict): 包含 vulnerability_scan + risk_assessment（评分来自画像/启发式）
        """
        logger.info(f"🔬 Starting AI vulnerability assessment for {target}")

        # Analyze target first
        loop = asyncio.get_running_loop()
        analysis_result = await loop.run_in_executor(
            None, lambda: hexstrike_client.safe_post("api/intelligence/analyze-target", {"target": target})
        )

        if not analysis_result.get("success"):
            return analysis_result

        profile = analysis_result.get("target_profile", {})
        target_type = profile.get("target_type", "unknown")

        # Select tools based on focus areas and target type
        if focus_areas == "all":
            objective = "comprehensive"
        elif "web" in focus_areas and target_type == "web_application":
            objective = "comprehensive"
        elif "network" in focus_areas and target_type == "network_host":
            objective = "comprehensive"
        else:
            objective = "quick"

        # Execute vulnerability assessment
        loop = asyncio.get_running_loop()
        scan_result = await loop.run_in_executor(
            None, lambda: hexstrike_client.safe_post("api/intelligence/smart-scan", {
            "target": target,
            "objective": objective,
            "max_tools": 6
        })
        )

        logger.info(f"✅ AI vulnerability assessment completed for {target}")

        return {
            "success": True,
            "target": target,
            "focus_areas": focus_areas,
            "target_analysis": profile,
            "vulnerability_scan": scan_result.get("scan_results", {}),
            "risk_assessment": {
                "risk_level": profile.get("risk_level", "unknown"),
                "attack_surface_score": profile.get("attack_surface_score", 0),
                "confidence_score": profile.get("confidence_score", 0)
            },
            "timestamp": datetime.now().isoformat()
        }
