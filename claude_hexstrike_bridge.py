#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Claude Code ↔ HexStrike MCP 对接辅助。

职责：健康检查、MCP 注册、生成 CLAUDE.md / 系统提示、构建扫描启动命令。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from typing import Any, Dict, List, Optional, Tuple

import requests

BURP_MCP_SERVER_NAME = "burp"
DEFAULT_BURP_SSE_URL = "http://127.0.0.1:9876"

MCP_SERVER_NAME = "hexstrike_4844553825"

MCP_PROFILES: List[Tuple[str, str]] = [
    ("full", "完整工具集 (full)"),
    ("recon", "信息收集 (recon)"),
    ("bug_bounty", "漏洞赏金 (bug_bounty)"),
    ("ai_assist", "智能决策 (ai_assist)"),
    ("compact", "轻量模式 (compact)"),
]

SCAN_SCENARIOS: List[Tuple[str, str, str]] = [
    (
        "web_recon",
        "Web 信息收集",
        "请对目标 {target} 进行授权范围内的 Web 信息收集：子域枚举、HTTP 探测、目录与参数发现、技术栈识别。"
        " 必须通过 HexStrike MCP 工具逐步执行（如 subfinder、httpx、nuclei 等），每步说明使用的工具与关键发现。",
    ),
    (
        "vuln_scan",
        "漏洞扫描",
        "请对目标 {target} 进行授权范围内的漏洞扫描，优先使用 nuclei、sqlmap、ffuf 等 HexStrike MCP 工具。"
        " 按高危→低危汇报，给出证据片段与修复建议。",
    ),
    (
        "full_pentest",
        "完整渗透评估",
        "请对目标 {target} 制定并执行完整渗透评估：信息收集 → 漏洞验证 → 风险汇总。"
        " 全程通过 HexStrike MCP 调用工具，不要仅给理论步骤。",
    ),
    (
        "port_service",
        "端口与服务",
        "请对目标 {target} 进行端口扫描与服务识别（nmap/naabu 等 MCP 工具），列出开放端口、服务版本与潜在攻击面。",
    ),
]

# HexStrike Bug Bounty 工作流 → 默认扫描场景 / 推荐技能包（storage/Skill 顶层目录名）
WORKFLOW_TO_SCAN_SCENARIO: Dict[str, str] = {
    "recon": "web_recon",
    "vuln_hunt": "vuln_scan",
    "osint": "web_recon",
    "business_logic": "full_pentest",
    "file_upload": "vuln_scan",
    "comprehensive": "full_pentest",
}

WORKFLOW_TO_SKILL_PACKS: Dict[str, List[str]] = {
    "recon": ["01-信息搜集-Reconnaissance"],
    "vuln_hunt": [
        "02-漏洞扫描-VulnerabilityScanning",
        "03-漏洞利用-Exploitation",
    ],
    "osint": ["01-信息搜集-Reconnaissance"],
    "business_logic": ["03-漏洞利用-Exploitation"],
    "file_upload": ["03-漏洞利用-Exploitation"],
    "comprehensive": [
        "01-信息搜集-Reconnaissance",
        "02-漏洞扫描-VulnerabilityScanning",
        "03-漏洞利用-Exploitation",
    ],
}

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)


def _parse_frontmatter_field(text: str, field: str) -> str:
    m = _FRONTMATTER_RE.match(text or "")
    if not m:
        return ""
    block = m.group(1)
    for line in block.splitlines():
        if line.strip().startswith(f"{field}:"):
            val = line.split(":", 1)[1].strip().strip('"').strip("'")
            return val
    return ""


def _sanitize_skill_slug(raw: str) -> str:
    s = (raw or "skill").lower().strip()
    # 优先取括号内英文，如「子域名探测 (Subdomain Discovery)」
    paren = re.search(r"\(([^)]+)\)", s)
    if paren:
        s = paren.group(1)
    s = re.sub(r"[^\w\-]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "skill"


def resolve_claude_skill_name(skill: Dict[str, str]) -> str:
    """解析 Claude Code skill 的 name（用于 .claude/skills/{name}/）。"""
    path = skill.get("path") or ""
    name = _parse_frontmatter_field_from_path(path, "name")
    if name:
        return _sanitize_skill_slug(name)
    title = _parse_frontmatter_field_from_path(path, "title") or skill.get("name") or ""
    if title:
        return _sanitize_skill_slug(title)
    base = os.path.splitext(os.path.basename(path))[0]
    return _sanitize_skill_slug(base)


def discover_hexstrike_ce_skills(hexstrike_root: str) -> List[Dict[str, str]]:
    """扫描 HexStrike CE 自带 skills/（如 web-recon），供 Claude /skill 调用。"""
    skills_dir = os.path.normpath(os.path.join(hexstrike_root or "", "skills"))
    if not os.path.isdir(skills_dir):
        return []
    entries: List[Dict[str, str]] = []
    for dirpath, _dn, filenames in os.walk(skills_dir):
        for fn in filenames:
            if fn.lower() != "skill.md":
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, skills_dir).replace("\\", "/")
            pack = rel.split("/")[0] if "/" in rel else "hexstrike-ce"
            try:
                with open(full, "r", encoding="utf-8", errors="replace") as f:
                    head = f.read(4096)
                title = _parse_frontmatter_field(head, "name") or pack
            except OSError:
                title = pack
            entries.append({
                "id": f"hexstrike-ce/{rel}",
                "pack": f"hexstrike-ce/{pack}",
                "name": title,
                "path": full,
                "source": "hexstrike-ce",
            })
    entries.sort(key=lambda x: (x.get("pack", ""), x.get("name", "")))
    return entries


def discover_all_agent_skills(skill_root: str, hexstrike_root: str = "") -> List[Dict[str, str]]:
    """统领 Skill 包 + HexStrike CE skills 合并列表。"""
    merged: List[Dict[str, str]] = []
    seen: set = set()
    for sk in discover_tongling_skills(skill_root):
        sid = sk.get("id", "")
        if sid not in seen:
            seen.add(sid)
            merged.append(sk)
    for sk in discover_hexstrike_ce_skills(hexstrike_root):
        sid = sk.get("id", "")
        if sid not in seen:
            seen.add(sid)
            merged.append(sk)
    return merged


def sync_skills_to_claude_workspace(
    claude_dir: str,
    selected_skills: List[Dict[str, str]],
) -> Tuple[List[str], List[str]]:
    """
    将选中技能同步到 claude_dir/.claude/skills/{name}/SKILL.md。
    返回 (claude_name 列表, 日志行)。
    """
    skills_root = os.path.join(claude_dir, ".claude", "skills")
    os.makedirs(skills_root, exist_ok=True)
    synced: List[str] = []
    logs: List[str] = []

    for sk in selected_skills or []:
        src = sk.get("path") or ""
        if not os.path.isfile(src):
            logs.append(f"跳过（文件不存在）: {src}")
            continue
        claude_name = resolve_claude_skill_name(sk)
        dest_dir = os.path.join(skills_root, claude_name)
        dest_file = os.path.join(dest_dir, "SKILL.md")
        os.makedirs(dest_dir, exist_ok=True)

        try:
            with open(src, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except OSError as e:
            logs.append(f"读取失败 {src}: {e}")
            continue

        if not _parse_frontmatter_field(content, "name"):
            title = sk.get("name") or claude_name
            desc = f"TongLing 安全技能: {title}"
            content = f"---\nname: {claude_name}\ndescription: {desc}\n---\n\n{content}"

        try:
            with open(dest_file, "w", encoding="utf-8") as f:
                f.write(content)
        except OSError as e:
            logs.append(f"写入失败 {dest_file}: {e}")
            continue

        synced.append(claude_name)
        logs.append(f"✓ /{claude_name} ← {os.path.basename(src)}")

    return synced, logs


def _skill_md_in_dir(skill_dir: str) -> str:
    for fn in ("SKILL.md", "skill.md"):
        path = os.path.join(skill_dir, fn)
        if os.path.isfile(path):
            return path
    return ""


def list_loaded_claude_skills(claude_dir: str) -> List[Dict[str, str]]:
    """扫描 claude_dir/.claude/skills/ 中已导入的 Skills。"""
    skills_root = os.path.join(claude_dir or "", ".claude", "skills")
    if not os.path.isdir(skills_root):
        return []

    entries: List[Dict[str, str]] = []
    for name in sorted(os.listdir(skills_root)):
        if not re.match(r"^[\w\-]+$", name):
            continue
        skill_dir = os.path.join(skills_root, name)
        if not os.path.isdir(skill_dir):
            continue
        skill_file = _skill_md_in_dir(skill_dir)
        if not skill_file:
            continue
        display_name = _parse_frontmatter_field_from_path(skill_file, "name") or name
        description = _parse_frontmatter_field_from_path(skill_file, "description") or ""
        try:
            mtime = os.path.getmtime(skill_file)
        except OSError:
            mtime = 0
        entries.append({
            "name": name,
            "display_name": display_name,
            "description": description,
            "path": skill_file,
            "mtime": mtime,
        })
    return entries


def remove_claude_skills(
    claude_dir: str,
    skill_names: List[str],
) -> Tuple[List[str], List[str]]:
    """从 claude_dir/.claude/skills/ 移除指定 Skills。"""
    skills_root = os.path.join(claude_dir or "", ".claude", "skills")
    removed: List[str] = []
    logs: List[str] = []

    for raw in skill_names or []:
        name = (raw or "").strip()
        if not name or not re.match(r"^[\w\-]+$", name):
            logs.append(f"跳过无效名称: {raw}")
            continue
        skill_dir = os.path.join(skills_root, name)
        if not os.path.isdir(skill_dir):
            logs.append(f"未找到: /{name}")
            continue
        try:
            shutil.rmtree(skill_dir)
            removed.append(name)
            logs.append(f"✓ 已移除 /{name}")
        except OSError as e:
            logs.append(f"移除失败 /{name}: {e}")

    return removed, logs


def enrich_loaded_skills_catalog(
    loaded: List[Dict[str, str]],
    all_skills: List[Dict[str, str]],
) -> List[Dict[str, str]]:
    """为已加载 Skills 补充技能包等目录信息。"""
    by_name: Dict[str, Dict[str, str]] = {}
    for sk in all_skills or []:
        by_name[resolve_claude_skill_name(sk)] = sk

    enriched: List[Dict[str, str]] = []
    for item in loaded or []:
        row = dict(item)
        cat = by_name.get(row.get("name") or "")
        if cat:
            row["catalog_id"] = cat.get("id") or ""
            row["pack"] = cat.get("pack") or ""
            row["source_name"] = cat.get("name") or ""
        else:
            row["catalog_id"] = ""
            row["pack"] = ""
            row["source_name"] = ""
        enriched.append(row)
    return enriched


def build_claude_agent_prompt(
    target: str,
    scenario_id: str,
    synced_skill_names: Optional[List[str]] = None,
    selected_skills: Optional[List[Dict[str, str]]] = None,
    skill_root: str = "",
    custom: str = "",
    workflow_label: str = "",
) -> str:
    """
    构建 Claude Code Agent 首条指令：优先 /skill 斜杠命令 + MCP 执行要求。
    """
    if synced_skill_names:
        slash = " ".join(f"/{n}" for n in synced_skill_names[:8])
        skill_intro = (
            f"请先加载并遵循以下 Claude Skills：{slash}。"
            f"然后对目标 `{target}` 执行授权范围内的安全测试，"
            "全程通过 HexStrike MCP 工具实际运行（nmap、subfinder、httpx、nuclei 等），不要只给命令。"
        )
        base = build_scan_user_prompt(target, scenario_id, custom)
        if custom.strip():
            return f"{skill_intro}\n\n{base}"
        lines = [skill_intro, "", base.strip()]
        if workflow_label:
            lines.insert(1, f"场景: {workflow_label}")
        lines.extend([
            "",
            "## 执行要求",
            "1. 先按 Skills 方法论规划步骤，再逐步调用 MCP 工具。",
            "2. 每阶段汇报：工具名、关键发现、下一步。",
            "3. 仅在用户授权范围内测试。",
        ])
        return "\n".join(lines)

    return build_skill_augmented_prompt(
        target, scenario_id, selected_skills or [], skill_root, custom, workflow_label,
    )


def discover_tongling_skills(skill_root: str) -> List[Dict[str, str]]:
    """
    扫描 storage/Skill，返回可被选中的技能条目。
    id 为相对 skill_root 的路径（正斜杠）。
    """
    root = os.path.normpath(skill_root or "")
    if not os.path.isdir(root):
        return []

    entries: List[Dict[str, str]] = []
    seen: set = set()

    for dirpath, _dirnames, filenames in os.walk(root):
        rel_dir = os.path.relpath(dirpath, root).replace("\\", "/")
        if rel_dir == ".":
            pack = ""
        else:
            pack = rel_dir.split("/")[0]

        for fn in filenames:
            if fn.lower() != "skill.md" and not (
                rel_dir.endswith("/skills") and fn.lower().endswith(".md")
            ):
                continue
            if fn.lower() == "readme.md":
                continue

            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root).replace("\\", "/")
            if rel in seen:
                continue
            seen.add(rel)

            title = fn.replace(".md", "")
            try:
                with open(full, "r", encoding="utf-8", errors="replace") as f:
                    head = f.read(4096)
                title = (
                    _parse_frontmatter_field(head, "name")
                    or _parse_frontmatter_field(head, "title")
                    or title
                )
            except OSError:
                pass

            entries.append({
                "id": rel,
                "pack": pack or os.path.dirname(rel).replace("\\", "/"),
                "name": title,
                "path": full,
            })

    entries.sort(key=lambda x: (x.get("pack", ""), x.get("name", "")))
    return entries


def skill_ids_for_packs(all_skills: List[Dict[str, str]], pack_names: List[str]) -> List[str]:
    packs = {p.lower() for p in pack_names if p}
    ids: List[str] = []
    for sk in all_skills:
        pack = (sk.get("pack") or "").lower()
        sid = sk.get("id") or ""
        if pack in packs or any(sid.lower().startswith(p.lower()) for p in pack_names):
            ids.append(sid)
    return ids


def build_skill_augmented_prompt(
    target: str,
    scenario_id: str,
    selected_skills: List[Dict[str, str]],
    skill_root: str,
    custom: str = "",
    workflow_label: str = "",
) -> str:
    """组合扫描场景、技能引用与 HexStrike MCP 执行要求。"""
    base = build_scan_user_prompt(target, scenario_id, custom)
    lines = [base.strip(), ""]

    if workflow_label:
        lines.append(f"## 工作流场景: {workflow_label}")

    if selected_skills:
        lines.append("## 必须参考的安全 Skills（统领 storage/Skill）")
        lines.append(
            "请先阅读下列技能文档中的方法论与命令示例，再调用 HexStrike MCP 工具实际执行。"
        )
        for sk in selected_skills:
            rel = sk.get("id", "")
            name = sk.get("name", rel)
            abs_path = sk.get("path") or os.path.join(skill_root, rel.replace("/", os.sep))
            lines.append(f"- **{name}**: `{abs_path}`")
        lines.append("")
        slash_names = []
        for sk in selected_skills:
            nm = _parse_frontmatter_field_from_path(sk.get("path", ""), "name")
            if nm:
                slash_names.append(f"/{nm}")
        if slash_names:
            lines.append(
                "若 Claude Code 已加载同名 skill，可优先使用: "
                + " ".join(slash_names[:8])
            )
            lines.append("")

    lines.extend([
        "## 执行要求",
        "1. 全程通过 HexStrike MCP 调用工具，不要只输出命令。",
        "2. 每阶段汇报：工具名、关键发现、下一步。",
        "3. 仅在用户授权范围内测试。",
        f"4. 目标: `{target}`",
    ])
    return "\n".join(lines)


def _parse_frontmatter_field_from_path(path: str, field: str) -> str:
    if not path or not os.path.isfile(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return _parse_frontmatter_field(f.read(4096), field)
    except OSError:
        return ""


def collect_skill_add_dirs(skill_root: str, selected_skills: List[Dict[str, str]]) -> List[str]:
    """为 Claude --add-dir 收集技能包目录（去重）。"""
    dirs: List[str] = []
    seen: set = set()
    root = os.path.normpath(skill_root or "")
    if root and os.path.isdir(root):
        seen.add(root)
        dirs.append(root)

    for sk in selected_skills:
        pack = sk.get("pack") or ""
        if not pack:
            continue
        pack_dir = os.path.normpath(os.path.join(root, pack.replace("/", os.sep)))
        if os.path.isdir(pack_dir) and pack_dir not in seen:
            seen.add(pack_dir)
            dirs.append(pack_dir)
    return dirs


def build_mcp_stdio_payload(
    py_exe: str,
    mcp_py: str,
    server_url: str,
    profile: str = "full",
) -> dict:
    args = [mcp_py, "--server", server_url, "--profile", profile]
    token = (
        os.environ.get("HEXSTRIKE_API_TOKEN")
        or os.environ.get("TONGLING_WEB_TOKEN")
        or ""
    ).strip()
    if token:
        args.extend(["--auth-token", token])
    return {
        "command": py_exe,
        "args": args,
        "description": "HexStrike AI Community Edition — 统领自动配置",
        "timeout": 600,
        "disabled": False,
    }


def _find_npx_in_dir(base: str) -> str:
    if not base:
        return ""
    for name in ("npx.cmd", "npx.exe", "npx"):
        p = os.path.join(base, name)
        if os.path.isfile(p):
            return p
    return ""


def resolve_claude_cli(cc_dir: str, node_ai_dir: str = "") -> Dict[str, Any]:
    """
    解析 Claude Code 可执行方式。
    优先 npx（默认不带 @latest），其次 node_modules/.bin/claude.cmd。
    """
    try:
        from cc_visual.claude_launcher import CLAUDE_CODE_NPM_SPEC
    except ImportError:
        CLAUDE_CODE_NPM_SPEC = "@anthropic-ai/claude-code"

    cc_dir = os.path.normpath(cc_dir or "")
    node_ai = os.path.normpath(node_ai_dir or "")
    bundled_cc = os.path.join(node_ai, "claude-code") if node_ai else ""

    def _has_package(d: str) -> bool:
        return os.path.isdir(
            os.path.join(d, "node_modules", "@anthropic-ai", "claude-code")
        )

    package_cc = cc_dir
    if not _has_package(cc_dir) and bundled_cc and _has_package(bundled_cc):
        package_cc = bundled_cc

    npx = _find_npx_in_dir(node_ai) or _find_npx_in_dir(
        os.path.dirname(package_cc)
    ) or _find_npx_in_dir(os.path.dirname(cc_dir))

    cli_argv: List[str] = []
    if npx:
        try:
            from cc_visual.claude_launcher import build_npx_claude_argv

            cli_argv = build_npx_claude_argv(npx, prefer_latest=False)
        except ImportError:
            cli_argv = [npx, CLAUDE_CODE_NPM_SPEC]
    if not cli_argv:
        for name in ("claude.cmd", "claude.exe", "claude"):
            local = os.path.join(package_cc, "node_modules", ".bin", name)
            if os.path.isfile(local):
                cli_argv = [local]
                break

    version_hint = ""
    supports_mcp_cli = False
    if cli_argv:
        rc, out = _run_claude_cli(
            cli_argv + ["--version"], package_cc or cc_dir, timeout=45
        )
        if rc == 0:
            version_hint = (out or "").strip().split("\n")[0][:80]
        rc2, out2 = _run_claude_cli(
            cli_argv + ["mcp", "--help"], package_cc or cc_dir, timeout=45
        )
        merged = (out2 or "").lower()
        supports_mcp_cli = rc2 == 0 and "unknown command" not in merged

    return {
        "cli_argv": cli_argv,
        "cwd": package_cc or cc_dir,
        "work_dir": cc_dir or package_cc,
        "npx": npx,
        "package_dir": package_cc,
        "supports_mcp_cli": supports_mcp_cli,
        "version_hint": version_hint,
    }


def _run_claude_cli(
    cli_argv: List[str],
    cwd: str,
    timeout: int = 120,
) -> Tuple[int, str]:
    if not cli_argv:
        return -1, "未找到 Claude Code 可执行文件"
    env = dict(os.environ)
    try:
        from cc_visual.claude_launcher import apply_npm_registry_to_env, sanitize_stale_ssl_cert_env

        apply_npm_registry_to_env(env)
        sanitize_stale_ssl_cert_env(env)
    except ImportError:
        pass
    try:
        r = subprocess.run(
            cli_argv,
            cwd=cwd or None,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        merged = ((r.stdout or "").rstrip() + "\n" + (r.stderr or "").rstrip()).strip()
        return r.returncode, merged
    except subprocess.TimeoutExpired:
        return -1, "命令超时"
    except Exception as e:
        return -1, str(e)


def write_project_mcp_json(
    work_dir: str,
    server_name: str,
    payload: dict,
) -> str:
    """写入项目级 .mcp.json（Claude 启动时自动加载，不依赖 claude mcp 子命令）。"""
    work_dir = os.path.normpath(work_dir or "")
    os.makedirs(work_dir, exist_ok=True)
    path = os.path.join(work_dir, ".mcp.json")
    data: Dict[str, Any] = {"mcpServers": {}}
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                existing = json.load(f)
            if isinstance(existing, dict):
                data = existing
        except Exception:
            pass
    if not isinstance(data.get("mcpServers"), dict):
        data["mcpServers"] = {}
    entry = {
        "command": payload.get("command", ""),
        "args": payload.get("args", []),
    }
    if payload.get("description"):
        entry["description"] = payload["description"]
    if payload.get("timeout") is not None:
        entry["timeout"] = payload["timeout"]
    if "disabled" in payload:
        entry["disabled"] = payload["disabled"]
    if payload.get("env") and isinstance(payload["env"], dict):
        entry["env"] = payload["env"]
    data["mcpServers"][server_name] = entry
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return path


def build_burp_mcp_payload(
    java_exe: str,
    proxy_jar: str,
    sse_url: str = DEFAULT_BURP_SSE_URL,
    *,
    disabled: bool = False,
) -> dict:
    """PortSwigger Burp MCP：stdio 代理 jar → Burp 扩展 SSE 服务。"""
    return {
        "command": (java_exe or "java").strip() or "java",
        "args": [
            "-jar",
            os.path.normpath(proxy_jar),
            "--sse-url",
            (sse_url or DEFAULT_BURP_SSE_URL).strip().rstrip("/"),
        ],
        "description": "Burp Suite MCP（PortSwigger mcp-proxy-all.jar → SSE）— 统领可选",
        "timeout": 120,
        "disabled": bool(disabled),
    }


def read_project_mcp_servers(work_dir: str) -> Dict[str, Any]:
    path = os.path.join(os.path.normpath(work_dir or ""), ".mcp.json")
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        servers = data.get("mcpServers") if isinstance(data, dict) else {}
        return servers if isinstance(servers, dict) else {}
    except (OSError, json.JSONDecodeError, TypeError):
        return {}


def read_burp_mcp_status(work_dir: str) -> Dict[str, Any]:
    servers = read_project_mcp_servers(work_dir)
    entry = servers.get(BURP_MCP_SERVER_NAME) if isinstance(servers, dict) else None
    if not isinstance(entry, dict):
        return {"configured": False, "enabled": False}
    args = entry.get("args") or []
    sse_url = DEFAULT_BURP_SSE_URL
    proxy_jar = ""
    if isinstance(args, list):
        for i, arg in enumerate(args):
            if arg == "--sse-url" and i + 1 < len(args):
                sse_url = str(args[i + 1])
            if isinstance(arg, str) and arg.lower().endswith(".jar"):
                proxy_jar = arg
    return {
        "configured": True,
        "enabled": not bool(entry.get("disabled")),
        "java": str(entry.get("command") or "java"),
        "proxy_jar": proxy_jar,
        "sse_url": sse_url,
    }


def register_burp_mcp(
    work_dir: str,
    proxy_jar: str,
    sse_url: str = DEFAULT_BURP_SSE_URL,
    java_exe: str = "java",
) -> Tuple[bool, str]:
    jar = os.path.normpath((proxy_jar or "").strip())
    if not jar or not os.path.isfile(jar):
        return False, f"未找到 mcp-proxy-all.jar：{jar or '（未填写路径）'}"
    payload = build_burp_mcp_payload(java_exe, jar, sse_url, disabled=False)
    try:
        path = write_project_mcp_json(work_dir, BURP_MCP_SERVER_NAME, payload)
        return True, f"✓ Burp MCP 已写入 {path}（SSE {payload['args'][-1]}）"
    except OSError as e:
        return False, f"写入 Burp MCP 失败: {e}"


def disable_burp_mcp(work_dir: str) -> None:
    """禁用项目 .mcp.json 中的 Burp 条目（保留配置供下次启用）。"""
    work_dir = os.path.normpath(work_dir or "")
    path = os.path.join(work_dir, ".mcp.json")
    if not os.path.isfile(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return
        servers = data.get("mcpServers")
        if not isinstance(servers, dict) or BURP_MCP_SERVER_NAME not in servers:
            return
        entry = servers[BURP_MCP_SERVER_NAME]
        if isinstance(entry, dict):
            entry["disabled"] = True
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except (OSError, json.JSONDecodeError, TypeError):
        pass


def _hexstrike_auth_headers() -> Dict[str, str]:
    token = (
        os.environ.get("HEXSTRIKE_API_TOKEN")
        or os.environ.get("TONGLING_WEB_TOKEN")
        or ""
    ).strip()
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}


def check_hexstrike_health(base_url: str, timeout: float = 6.0) -> Tuple[bool, str]:
    base = base_url.rstrip("/")
    headers = _hexstrike_auth_headers()
    for path in ("/web-dashboard", "/api/tools"):
        try:
            r = requests.get(f"{base}{path}", timeout=timeout, verify=False, headers=headers)
            if r.status_code == 200:
                return True, f"HexStrike 在线 ({path}, HTTP 200)"
        except requests.ConnectionError:
            return False, f"无法连接 {base}，请先在「终端工作台」启动 HexStrike Server"
        except Exception as e:
            return False, str(e)[:200]
    return False, f"HexStrike 未响应 (最后尝试 {base})"


def run_claude_mcp_list(
    cwd: str,
    npx: str = "",
    node_ai_dir: str = "",
) -> Tuple[int, str]:
    rt = resolve_claude_cli(cwd, node_ai_dir)
    if not rt.get("cli_argv"):
        return -1, "未找到 Claude Code（请确认工作目录或 node_ai 已安装）"
    return _run_claude_cli(
        rt["cli_argv"] + ["mcp", "list"], rt.get("cwd") or cwd, timeout=90
    )


def mcp_already_registered(list_output: str, server_name: str = MCP_SERVER_NAME) -> bool:
    return server_name.lower() in (list_output or "").lower()


def mcp_cli_output_is_benign(text: str) -> bool:
    """CLI 返回「已存在 / 多 scope」等可忽略信息时视为正常。"""
    t = (text or "").lower()
    return any(
        k in t
        for k in (
            "already exists",
            "exists in multiple scopes",
            "multiple scopes",
            "not found",
            "does not exist",
            "no such",
        )
    )


def register_claude_mcp(
    cwd: str,
    npx: str,
    payload: dict,
    server_name: str = MCP_SERVER_NAME,
    force_refresh: bool = True,
    node_ai_dir: str = "",
) -> Tuple[bool, str]:
    """
    注册 HexStrike MCP：写入项目 .mcp.json（主配置源）。
    可选清理 local scope 重复项，避免与 project .mcp.json 冲突。
    不再执行 add-json（Claude 2.x 多 scope 会报错且阻塞 UI）。
    """
    logs: List[str] = []
    rt = resolve_claude_cli(cwd, node_ai_dir)
    work_dir = rt.get("work_dir") or cwd
    cli_argv = rt.get("cli_argv") or []

    if not cli_argv:
        return False, (
            "未找到 Claude Code 可执行文件。\n"
            f"工作目录: {cwd}\n"
            "请将「工作目录」设为 storage\\node_ai\\claude-code，"
            "或在该目录执行 npm install @anthropic-ai/claude-code@latest"
        )

    if rt.get("version_hint"):
        logs.append(f"Claude CLI: {rt['version_hint']}")
    logs.append(f"包目录: {rt.get('package_dir', cwd)}")

    try:
        mcp_json = write_project_mcp_json(work_dir, server_name, payload)
        logs.append(f"✓ 已写入 {mcp_json}")
    except OSError as e:
        return False, f"写入 .mcp.json 失败: {e}"

    if force_refresh and rt.get("supports_mcp_cli"):
        for scope in ("local",):
            rc, out = run_claude_mcp_cmd(
                cwd,
                npx,
                ["remove", server_name, "-s", scope],
                timeout=30,
                node_ai_dir=node_ai_dir,
            )
            out = (out or "").strip()
            if out and not mcp_cli_output_is_benign(out):
                logs.append(out)
            elif out and "remove" not in out.lower()[:20]:
                logs.append(out)

    logs.append(
        "MCP 已通过项目 .mcp.json 配置。"
        " 启动 Claude 时使用 --mcp-config 加载（无需 CLI add-json）。"
    )
    return True, "\n".join(logs)


def run_claude_mcp_cmd(
    cwd: str,
    npx: str,
    mcp_args: List[str],
    timeout: int = 120,
    node_ai_dir: str = "",
) -> Tuple[int, str]:
    rt = resolve_claude_cli(cwd, node_ai_dir)
    cli_argv = rt.get("cli_argv") or []
    if not cli_argv:
        try:
            from cc_visual.claude_launcher import CLAUDE_CODE_NPM_SPEC
        except ImportError:
            CLAUDE_CODE_NPM_SPEC = "@anthropic-ai/claude-code"
        if npx:
            try:
                from cc_visual.claude_launcher import build_npx_claude_argv

                cli_argv = build_npx_claude_argv(npx, prefer_latest=False)
            except ImportError:
                cli_argv = [npx, CLAUDE_CODE_NPM_SPEC]
        else:
            return -1, "未找到 Claude Code 可执行文件"
    cmd = cli_argv + ["mcp"] + mcp_args
    return _run_claude_cli(cmd, rt.get("cwd") or cwd, timeout=timeout)


def build_scan_user_prompt(target: str, scenario_id: str, custom: str = "") -> str:
    custom = (custom or "").strip()
    if custom:
        return custom.replace("{target}", target)
    for sid, _label, template in SCAN_SCENARIOS:
        if sid == scenario_id:
            return template.format(target=target)
    return SCAN_SCENARIOS[0][2].format(target=target)


def write_hexstrike_project_files(
    claude_dir: str,
    target: str,
    server_url: str,
    profile: str,
    user_prompt: str,
    selected_skills: Optional[List[Dict[str, str]]] = None,
    skill_root: str = "",
    report_relpath: str = "",
) -> str:
    """
    在 claude-code 目录写入 CLAUDE.md 与系统提示文件，供 Claude 会话加载。
    返回辅助目录路径。
    """
    aux = os.path.join(claude_dir, ".tongling_hexstrike")
    os.makedirs(aux, exist_ok=True)

    report_rel = (report_relpath or "").strip().replace("\\", "/")
    if not report_rel:
        from datetime import datetime

        stamp = datetime.now().strftime("%Y%m%d_%H%M")
        safe = re.sub(r"[^\w.\-]+", "_", (target or "target").strip())[:80] or "target"
        report_rel = f"reports/{safe}_{stamp}.md"
    report_abs = os.path.join(claude_dir, report_rel.replace("/", os.sep))
    os.makedirs(os.path.dirname(report_abs), exist_ok=True)

    claude_md = f"""# HexStrike 渗透扫描 — 统领 AI 终端

## 当前任务
- **目标**: `{target}`
- **HexStrike API**: `{server_url}`
- **MCP Profile**: `{profile}`
- **报告输出**: `{report_rel}`（扫描完成后必须写入此文件）

## 必须遵守
1. **仅**在用户已明确授权的目标范围内测试。
2. 执行扫描时 **必须调用 HexStrike MCP 工具**（如 `nmap`、`subfinder`、`httpx`、`nuclei`、`ffuf`、`sqlmap` 等），不要只输出命令让用户手打。
3. 每完成一个阶段，简要汇报：用了什么工具、发现什么、下一步计划。
4. 若 MCP 工具报错，说明错误并尝试替代工具或缩小 scope。
5. 在统领「任务监控」页可查看后台进程输出。
6. **扫描结束后**，将完整漏洞扫描报告写入 **`{report_rel}`**（Markdown），须包含：目标、扫描范围、工具与命令摘要、漏洞/风险列表（含等级）、证据片段、修复建议、结论。
7. **禁止**将报告写到其他盘符或工作区外路径（不要写 `Z:\\`、`C:\\Users\\...` 等）；**必须**使用上方 `{report_rel}` 相对路径。

## 推荐流程（Web 目标）
1. 子域 / 资产发现 → 2. 存活探测 → 3. 目录与参数 → 4. 漏洞模板扫描 → 5. 汇总报告 → 6. 写入 `{report_rel}`

## 用户初始指令
{user_prompt}
"""
    if selected_skills:
        skill_lines = ["\n## 已选 Skills\n"]
        for sk in selected_skills:
            skill_lines.append(f"- {sk.get('name', sk.get('id', ''))}: `{sk.get('path', '')}`")
        claude_md += "\n".join(skill_lines) + "\n"

    with open(os.path.join(claude_dir, "CLAUDE.md"), "w", encoding="utf-8") as f:
        f.write(claude_md)

    system_txt = (
        "你是统领 AI 渗透终端中的 Claude 智能体。"
        f"已接入 HexStrike MCP（{server_url}，profile={profile}）。"
        "用户要求你通过 MCP 工具实际执行安全扫描，而非仅给出文字建议。"
        "每次调用工具前说明目的；工具返回后提炼关键结果。"
    )
    with open(os.path.join(aux, "system.txt"), "w", encoding="utf-8") as f:
        f.write(system_txt)

    with open(os.path.join(aux, "last_prompt.txt"), "w", encoding="utf-8") as f:
        f.write(user_prompt)

    with open(os.path.join(aux, "report_path.txt"), "w", encoding="utf-8") as f:
        f.write(report_rel)

    return aux


def build_claude_launch_argv(
    cli_argv: List[str],
    user_prompt: str,
    system_prompt_file: Optional[str] = None,
    skip_permissions: bool = True,
    add_dirs: Optional[List[str]] = None,
    mcp_config_file: Optional[str] = None,
    cc_dir: Optional[str] = None,
) -> List[str]:
    """构建启动 Claude Code 交互会话的参数（不含 cmd.exe）。"""
    if not cli_argv:
        raise ValueError("cli_argv 为空，无法启动 Claude Code")
    argv = list(cli_argv)
    if skip_permissions:
        argv.append("--dangerously-skip-permissions")
    mcp_path = mcp_config_file
    if not mcp_path and cc_dir:
        cand = os.path.join(cc_dir, ".mcp.json")
        if os.path.isfile(cand):
            mcp_path = cand
    if mcp_path and os.path.isfile(mcp_path):
        argv.extend(["--mcp-config", os.path.normpath(mcp_path)])
    for d in add_dirs or []:
        if d and os.path.isdir(d):
            argv.extend(["--add-dir", os.path.normpath(d)])
    if system_prompt_file and os.path.isfile(system_prompt_file):
        argv.extend(["--append-system-prompt-file", system_prompt_file])
    argv.append(user_prompt)
    return argv


def run_claude_automation_setup(
    cc_dir: str,
    npx: str,
    py_exe: str,
    mcp_py: str,
    server_url: str,
    profile: str,
    target: str,
    user_prompt: str,
    server_name: str = MCP_SERVER_NAME,
    register_mcp: bool = True,
    selected_skills: Optional[List[Dict[str, str]]] = None,
    skill_root: str = "",
    sync_skills: bool = True,
    node_ai_dir: str = "",
) -> Tuple[bool, str, Optional[dict]]:
    """
    Claude Code Agent 一键前置：健康检查 → MCP 注册 → Skills 同步 → CLAUDE.md。
    成功时返回 (True, msg, result_dict)。
    """
    ok, health_msg = check_hexstrike_health(server_url)
    if not ok:
        return False, health_msg, None

    reg_log = ""
    mcp_json_path = ""
    if register_mcp:
        payload = build_mcp_stdio_payload(py_exe, mcp_py, server_url, profile)
        reg_ok, reg_log = register_claude_mcp(
            cc_dir,
            npx,
            payload,
            server_name=server_name,
            force_refresh=True,
            node_ai_dir=node_ai_dir,
        )
        if not reg_ok:
            return False, reg_log or "MCP 注册失败", None
        try:
            mcp_json_path = write_project_mcp_json(cc_dir, server_name, payload)
        except OSError:
            mcp_json_path = os.path.join(cc_dir, ".mcp.json")

    rt = resolve_claude_cli(cc_dir, node_ai_dir)

    synced_names: List[str] = []
    sync_logs: List[str] = []
    if sync_skills and selected_skills:
        synced_names, sync_logs = sync_skills_to_claude_workspace(cc_dir, selected_skills)

    aux_dir = write_hexstrike_project_files(
        cc_dir,
        target,
        server_url,
        profile,
        user_prompt,
        selected_skills=selected_skills,
        skill_root=skill_root,
    )
    if synced_names:
        with open(os.path.join(aux_dir, "synced_skills.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(synced_names))

    system_file = os.path.join(aux_dir, "system.txt")
    add_dirs = collect_skill_add_dirs(skill_root, selected_skills or [])
    return True, health_msg, {
        "health": health_msg,
        "register_log": reg_log,
        "sync_log": "\n".join(sync_logs),
        "synced_skill_names": synced_names,
        "user_prompt": user_prompt,
        "system_file": system_file,
        "aux_dir": aux_dir,
        "add_dirs": add_dirs,
        "mcp_json_path": mcp_json_path,
        "cli_argv": rt.get("cli_argv") or [],
        "cli_cwd": rt.get("cwd") or cc_dir,
    }


def prepare_claude_launch_spec(
    cc_dir: str,
    npx: str,
    user_prompt: str,
    system_file: str,
    http_proxy: str = "",
    add_dirs: Optional[List[str]] = None,
    skip_permissions: bool = True,
    base_env: Optional[dict] = None,
    cli_argv: Optional[List[str]] = None,
    mcp_config_file: Optional[str] = None,
    node_ai_dir: str = "",
) -> Tuple[bool, str, Optional[dict]]:
    """构建 Claude 启动参数（内嵌 PTY 或外部 CMD 共用）。"""
    rt = resolve_claude_cli(cc_dir, node_ai_dir)
    launch_argv = list(cli_argv or rt.get("cli_argv") or [])
    if not launch_argv and npx:
        try:
            from cc_visual.claude_launcher import build_npx_claude_argv

            launch_argv = build_npx_claude_argv(npx, prefer_latest=False)
        except ImportError:
            launch_argv = [npx, "@anthropic-ai/claude-code"]
    if not launch_argv:
        return False, "未找到 Claude Code（请设置工作目录为 storage\\node_ai\\claude-code）", None
    if not http_proxy:
        return False, "请先填写代理地址（AI智能体页 Claude 代理）", None

    launch_cwd = rt.get("work_dir") or cc_dir
    mcp_file = mcp_config_file or os.path.join(launch_cwd, ".mcp.json")

    argv = build_claude_launch_argv(
        launch_argv,
        user_prompt,
        system_file,
        skip_permissions=skip_permissions,
        add_dirs=add_dirs,
        mcp_config_file=mcp_file if os.path.isfile(mcp_file) else None,
        cc_dir=launch_cwd,
    )
    env = proxy_env(http_proxy, dict(base_env or os.environ))
    env["IS_DEMO"] = "1"
    try:
        from cc_visual.claude_launcher import apply_npm_registry_to_env, sanitize_stale_ssl_cert_env

        apply_npm_registry_to_env(env)
        sanitize_stale_ssl_cert_env(env)
    except ImportError:
        pass
    bin_dir = os.path.dirname(launch_argv[0])
    if bin_dir:
        env["PATH"] = bin_dir + os.pathsep + env.get("PATH", "")
    npx_p = rt.get("npx") or npx
    if npx_p:
        env["PATH"] = os.path.dirname(npx_p) + os.pathsep + env.get("PATH", "")

    return True, "ok", {
        "argv": argv,
        "cwd": launch_cwd,
        "env": env,
        "cmdline": subprocess.list2cmdline(argv),
    }


def launch_claude_in_console(
    cc_dir: str,
    npx: str,
    user_prompt: str,
    system_file: str,
    http_proxy: str = "",
    add_dirs: Optional[List[str]] = None,
    skip_permissions: bool = True,
    base_env: Optional[dict] = None,
    cli_argv: Optional[List[str]] = None,
    mcp_config_file: Optional[str] = None,
    node_ai_dir: str = "",
) -> Tuple[bool, str]:
    """在 Windows 新 CMD 中启动 Claude Code。"""
    import sys

    if sys.platform != "win32":
        return False, "一键启动仅支持 Windows"

    ok, msg, spec = prepare_claude_launch_spec(
        cc_dir,
        npx,
        user_prompt,
        system_file,
        http_proxy=http_proxy,
        add_dirs=add_dirs,
        skip_permissions=skip_permissions,
        base_env=base_env,
        cli_argv=cli_argv,
        mcp_config_file=mcp_config_file,
        node_ai_dir=node_ai_dir,
    )
    if not ok or not spec:
        return False, msg

    try:
        subprocess.Popen(
            ["cmd.exe", "/k"] + spec["argv"],
            cwd=spec["cwd"],
            env=spec["env"],
            creationflags=0x00000010,
        )
        return True, "已在新 CMD 启动 Claude Code"
    except Exception as e:
        return False, str(e)


def launch_claude_in_embedded_terminal(
    terminal,
    cc_dir: str,
    npx: str,
    user_prompt: str,
    system_file: str,
    http_proxy: str = "",
    add_dirs: Optional[List[str]] = None,
    skip_permissions: bool = True,
    base_env: Optional[dict] = None,
    cli_argv: Optional[List[str]] = None,
    mcp_config_file: Optional[str] = None,
    node_ai_dir: str = "",
) -> Tuple[bool, str]:
    """在 EmbeddedPtyTerminalWidget 中启动 Claude Code。"""
    ok, msg, spec = prepare_claude_launch_spec(
        cc_dir,
        npx,
        user_prompt,
        system_file,
        http_proxy=http_proxy,
        add_dirs=add_dirs,
        skip_permissions=skip_permissions,
        base_env=base_env,
        cli_argv=cli_argv,
        mcp_config_file=mcp_config_file,
        node_ai_dir=node_ai_dir,
    )
    if not ok or not spec:
        return False, msg
    if terminal is None:
        return False, "内嵌终端未初始化"
    if not terminal.start_process(spec["argv"], spec["cwd"], spec["env"]):
        return False, "内嵌终端启动失败"
    return True, "已在内嵌终端启动 Claude Code"


def proxy_env(http_proxy_url: str, base_env: Optional[dict] = None) -> dict:
    env = dict(base_env or os.environ)
    url = (http_proxy_url or "").strip()
    if not url:
        return env
    if not url.lower().startswith(("http://", "https://")):
        url = "http://" + url
    env["http_proxy"] = url
    env["https_proxy"] = url
    env["HTTP_PROXY"] = url
    env["HTTPS_PROXY"] = url
    return env
