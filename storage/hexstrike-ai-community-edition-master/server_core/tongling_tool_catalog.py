"""Load Tongling tool catalog from tools_config.json and toollist.json."""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _decode_unicode_text(text: str) -> str:
    """Decode toollist.json style \\uXXXX escapes to readable text."""
    if not text or "\\u" not in text:
        return text
    try:
        return text.encode("utf-8").decode("unicode_escape")
    except Exception:
        try:
            return text.encode("latin-1").decode("unicode_escape")
        except Exception:
            return text


# Known CLI usage hints for AI / MCP docstrings
USAGE_HINTS: Dict[str, dict] = {
    "subjack": {
        "desc": "Subdomain takeover scanner (Go)",
        "example": "-w subdomains.txt -ssl -v -t 100",
        "category": "recon",
    },
    "sslscan": {
        "desc": "SSL/TLS cipher and certificate scanner",
        "example": "example.com:443",
        "category": "web_probe",
    },
    "nosqlmap": {
        "desc": "NoSQL injection automation tool",
        "example": "-u http://target/page?id=1",
        "category": "web_scan",
    },
    "jwt_tool": {
        "desc": "JWT decode, crack and tamper (Python jwt_tool)",
        "example": "JWT_TOKEN_HERE",
        "category": "api_scan",
    },
    "hash-identifier": {
        "desc": "Identify hash types from a hash string",
        "example": "5f4dcc3b5aa765d61d8327deb882cf99",
        "category": "password_cracking",
    },
    "hexdump": {
        "desc": "Hex dump binary or file contents",
        "example": "-C file.bin",
        "category": "data_processing",
    },
    "dddd": {
        "desc": "Batch asset recon and vuln scan pipeline",
        "example": "-t target.txt",
        "category": "vuln_scan",
    },
    "xray": {
        "desc": "Chaitin xray web vulnerability scanner",
        "example": "webscan --url http://target/ --html-output out.html",
        "category": "web_scan",
    },
    "OneForAll": {
        "desc": "Subdomain collection toolkit",
        "example": "run --target example.com",
        "category": "recon",
    },
    "oneforall": {
        "desc": "Subdomain collection toolkit",
        "example": "run --target example.com",
        "category": "recon",
    },
    "gogo": {
        "desc": "Port-based red team automation engine",
        "example": "-i 192.168.1.0/24",
        "category": "network_recon",
    },
    "AlliN": {
        "desc": "Comprehensive penetration scan helper",
        "example": "-t http://target",
        "category": "network_recon",
    },
    "nc": {
        "desc": "Netcat — connect/listen utility",
        "example": "-nv 10.0.0.1 80",
        "category": "network_recon",
    },
    "commix": {
        "desc": "Command injection exploitation (via Tongling binary)",
        "example": "--url=http://target/vuln --batch",
        "category": "exploit_framework",
    },
    "volatility2": {
        "desc": "Memory forensics framework v2",
        "example": "-f memory.dmp imageinfo",
        "category": "memory_forensics",
    },
}


@dataclass
class TonglingTool:
    alias: str
    display_name: str
    source: str  # tools_config | toollist
    tool_type: str  # exe | python | bat
    storage_path: str
    executable: str
    resolved_path: Optional[str] = None
    installed: bool = False
    category: str = "tongling"
    usage_example: str = ""
    description: str = ""


def _workspace_roots() -> List[Path]:
    storage_root = _REPO_ROOT.parent
    workspace_root = storage_root.parent
    return [workspace_root, _REPO_ROOT, storage_root]


def resolve_tools_config_path() -> Optional[Path]:
    for p in (
        _REPO_ROOT.parent / "tools_config.json",
        _REPO_ROOT / "tools_config.json",
        _REPO_ROOT / "storage" / "tools_config.json",
    ):
        if p.is_file():
            return p
    return None


def resolve_toollist_path() -> Optional[Path]:
    for p in (
        _REPO_ROOT.parent / "toollist.json",
        _REPO_ROOT / "toollist.json",
        _REPO_ROOT / "storage" / "toollist.json",
    ):
        if p.is_file():
            return p
    return None


def _resolve_relative_path(rel_path: str) -> Optional[Path]:
    rel = (rel_path or "").strip().replace("\\", "/")
    if not rel:
        return None
    rel_path = Path(rel.replace("/", os.sep))
    if rel_path.is_absolute() and rel_path.exists():
        return rel_path.resolve()
    for root in _workspace_roots():
        cand = (root / rel_path).resolve()
        if cand.exists():
            return cand
    return None


def _resolve_executable(base: Path, exe_name: str, tool_type: str) -> Optional[Path]:
    if not exe_name:
        return None
    if base.is_file():
        return base.resolve()
    direct = base / exe_name
    if direct.is_file():
        return direct.resolve()
    if tool_type == "python":
        py = _REPO_ROOT.parent / "storage" / "Python38" / "python.exe"
        if not py.is_file():
            py = Path("python")
        script = base / exe_name if base.is_dir() else base
        if script.is_file():
            return script.resolve()
    # scan directory for matching exe
    if base.is_dir():
        for pat in (exe_name, exe_name.lower(), exe_name.upper()):
            hit = base / pat
            if hit.is_file():
                return hit.resolve()
        for hit in base.glob("*.exe"):
            if hit.name.lower() == exe_name.lower():
                return hit.resolve()
    return None


def _find_exe_in_storage(tool_name: str) -> Optional[Path]:
    """Best-effort locate binary under storage/{tool_name}."""
    storage = _REPO_ROOT.parent
    if not storage.is_dir():
        return None
    candidates = [
        storage / tool_name,
        storage / tool_name.lower(),
        storage / tool_name.capitalize(),
    ]
    # case-insensitive folder match
    try:
        for entry in storage.iterdir():
            if entry.is_dir() and entry.name.lower() == tool_name.lower():
                candidates.append(entry)
    except OSError:
        pass

    seen = set()
    for folder in candidates:
        key = str(folder).lower()
        if key in seen or not folder.is_dir():
            continue
        seen.add(key)
        for exe in folder.glob("*.exe"):
            if exe.name.lower() not in ("uninstall.exe", "setup.exe"):
                return exe.resolve()
        bat = folder / "windows_start.bat"
        if bat.is_file():
            try:
                text = bat.read_text(encoding="utf-8", errors="replace")
                m = re.search(r"[\./\\]?([\w.-]+\.exe)", text, re.I)
                if m:
                    hit = folder / m.group(1).lstrip(".\\/")
                    if hit.is_file():
                        return hit.resolve()
            except OSError:
                pass
    return None


def _normalize_tool_alias(raw_name: str) -> tuple[str, str]:
    """Return (registry alias, human-readable label)."""
    display = _decode_unicode_text(raw_name).strip()
    if re.match(r"^[\w][\w.\-+]*$", display, re.I):
        return display.lower(), display
    found = _find_exe_in_storage(display) or _find_exe_in_storage(raw_name)
    if found:
        folder = found.parent.name
        return folder.lower(), display if display != raw_name else folder
    slug = re.sub(r"[^\w\-+]+", "-", display.lower()).strip("-")
    if slug:
        return slug, display
    return raw_name.strip().lower(), display


def _load_tools_config_entries() -> Dict[str, TonglingTool]:
    cfg_path = resolve_tools_config_path()
    if not cfg_path:
        return {}
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {}

    tools = data.get("tools") if isinstance(data, dict) else {}
    if not isinstance(tools, dict):
        return {}

    out: Dict[str, TonglingTool] = {}
    for display_name, info in tools.items():
        if not isinstance(info, dict):
            continue
        if info.get("type") == "interpreter":
            continue
        rel = (info.get("path") or "").strip()
        exe = (info.get("executable") or info.get("script") or "").strip()
        tool_type = (info.get("type") or "exe").strip().lower()
        aliases = info.get("aliases") or [display_name]
        if not isinstance(aliases, list):
            aliases = [str(aliases)]
        base = _resolve_relative_path(rel)
        resolved = _resolve_executable(base, exe, tool_type) if base else None
        hint_key = aliases[0].lower() if aliases else display_name.lower()
        hint = USAGE_HINTS.get(aliases[0]) or USAGE_HINTS.get(hint_key) or {}

        for alias in aliases:
            key = str(alias).strip().lower()
            if not key:
                continue
            out[key] = TonglingTool(
                alias=key,
                display_name=display_name,
                source="tools_config",
                tool_type=tool_type,
                storage_path=rel,
                executable=exe,
                resolved_path=str(resolved) if resolved else None,
                installed=bool(resolved and resolved.is_file()),
                category=hint.get("category", "tongling"),
                usage_example=hint.get("example", ""),
                description=hint.get("desc", f"Tongling tool: {display_name}"),
            )
    return out


def _iter_toollist_cli_tools(data: dict):
    """Walk entire toollist.json tree (all categories), yield CLI tool entries."""

    def walk(node: dict):
        for key, val in node.items():
            if not isinstance(val, dict):
                continue
            # Tool leaf: has version + commandLine
            if "commandLine" in val and "version" in val:
                if str(val.get("commandLine", "")).lower() in ("true", "1", "yes"):
                    yield key, val
                continue
            yield from walk(val)

    if isinstance(data, dict):
        yield from walk(data)


def _load_toollist_entries(existing: Dict[str, TonglingTool]) -> Dict[str, TonglingTool]:
    tl_path = resolve_toollist_path()
    if not tl_path:
        return {}
    try:
        with open(tl_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {}

    out: Dict[str, TonglingTool] = {}
    for name, meta in _iter_toollist_cli_tools(data):
        alias, display_name = _normalize_tool_alias(name)
        if not alias or alias in existing or alias in out:
            continue
        resolved = _find_exe_in_storage(display_name) or _find_exe_in_storage(name)
        hint = USAGE_HINTS.get(name) or USAGE_HINTS.get(display_name) or USAGE_HINTS.get(alias) or {}
        rel = f"storage/{display_name}" if display_name != name else f"storage/{name}"
        intro = _decode_unicode_text(meta.get("introduce") or "")
        out[alias] = TonglingTool(
            alias=alias,
            display_name=display_name,
            source="toollist",
            tool_type="exe",
            storage_path=rel,
            executable=resolved.name if resolved else f"{display_name}.exe",
            resolved_path=str(resolved) if resolved else None,
            installed=bool(resolved and resolved.is_file()),
            category=hint.get("category", "tongling"),
            usage_example=hint.get("example", "-h"),
            description=hint.get("desc", intro[:160] if intro else f"Tongling CLI tool: {display_name}"),
        )
    return out


_catalog_cache: Optional[Dict[str, TonglingTool]] = None


def get_catalog(*, refresh: bool = False) -> Dict[str, TonglingTool]:
    global _catalog_cache
    if _catalog_cache is not None and not refresh:
        return _catalog_cache
    cfg = _load_tools_config_entries()
    tl = _load_toollist_entries(cfg)
    merged = {**cfg, **tl}
    _catalog_cache = merged
    return merged


def get_tool(alias: str) -> Optional[TonglingTool]:
    if not alias:
        return None
    return get_catalog().get(alias.strip().lower())


def list_tools(*, installed_only: bool = False, category: str = "") -> List[dict]:
    items = []
    cat = category.strip().lower()
    for t in get_catalog().values():
        if installed_only and not t.installed:
            continue
        if cat and t.category.lower() != cat:
            continue
        items.append(
            {
                "alias": t.alias,
                "display_name": _decode_unicode_text(t.display_name),
                "source": t.source,
                "installed": t.installed,
                "category": t.category,
                "description": _decode_unicode_text(t.description),
                "usage_example": t.usage_example,
                "executable": t.executable,
                "storage_path": t.storage_path,
            }
        )
    items.sort(key=lambda x: (not x["installed"], x["alias"]))
    return items


# Aliases that already have dedicated HexStrike API handlers (skip duplicate /api/tools/{alias})
DEDICATED_HEXSTRIKE_ALIASES = frozenset(
    {
        "nmap", "subfinder", "nuclei", "ffuf", "hydra", "sqlmap", "dirsearch",
        "rustscan", "nxc", "netexec", "katana", "dalfox", "wafw00f", "gobuster",
        "amass", "httpx", "hashid", "gau", "wfuzz", "hakrawler", "jaeles",
        "masscan", "patator", "naabu", "ehole", "afrog", "kscan", "fscan",
        "pocbomber", "bettercap", "steghide", "checkov", "maltego", "photorec",
        "testdisk", "tshark", "airbase-ng", "aircrack-ng", "airdecap-ng",
        "aireplay-ng", "airodump-ng", "airolib-ng", "airserv-ng", "airtun-ng",
    }
)


def get_tongling_registry_entries(skip_aliases: Optional[Iterable[str]] = None) -> Dict[str, dict]:
    """Build compact tool_registry entries for Tongling-managed tools."""
    skip = {a.strip().lower() for a in (skip_aliases or []) if a}
    skip |= DEDICATED_HEXSTRIKE_ALIASES
    entries: Dict[str, dict] = {}
    for alias, tool in get_catalog().items():
        if alias in skip:
            continue
        endpoint = f"/api/tools/tongling/{alias}"
        entries[alias] = {
            "desc": _decode_unicode_text(tool.description or f"Run Tongling tool {tool.display_name}"),
            "label": _decode_unicode_text(tool.display_name),
            "endpoint": endpoint,
            "method": "POST",
            "category": tool.category,
            "params": {},
            "optional": {
                "target": "",
                "args": "",
                "additional_args": "",
                "timeout": 600,
            },
            "effectiveness": 0.75 if tool.installed else 0.5,
            "tongling": True,
        }
    # Generic runner always available
    entries["tongling-run"] = {
        "desc": "Run any Tongling tool by alias (tools_config + toollist CLI)",
        "endpoint": "/api/tongling/run",
        "method": "POST",
        "category": "tongling",
        "params": {"tool": {"required": True}},
        "optional": {"target": "", "args": "", "additional_args": "", "timeout": 600},
        "effectiveness": 0.85,
        "tongling": True,
    }
    entries["tongling-catalog"] = {
        "desc": "List Tongling tools available on this server",
        "endpoint": "/api/tongling/catalog",
        "method": "GET",
        "category": "tongling",
        "params": {},
        "optional": {"installed_only": False, "category": ""},
        "effectiveness": 0.9,
        "tongling": True,
    }
    return entries


def catalog_stats() -> dict:
    """Summary counts for dashboards / MCP connect UI."""
    cat = get_catalog()
    items = list(cat.values())
    from_tools_config = [t for t in items if t.source == "tools_config"]
    from_toollist = [t for t in items if t.source == "toollist"]
    installed = [t for t in items if t.installed]
    return {
        "catalog_total": len(items),
        "tools_config_count": len(from_tools_config),
        "toollist_cli_count": len(from_toollist),
        "installed_count": len(installed),
        "tools_config_installed": sum(1 for t in from_tools_config if t.installed),
        "toollist_installed": sum(1 for t in from_toollist if t.installed),
    }
