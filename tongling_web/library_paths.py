"""外展库（指纹 / Nuclei 漏洞模板）路径解析。"""

from __future__ import annotations

import os
from pathlib import Path

HFINGER_MCP_SERVER_NAME = "hfinger-lib"
NUCLEI_LIB_MCP_SERVER_NAME = "nuclei-lib"


def tongling_root() -> Path:
    raw = os.environ.get("TONGLING_ROOT") or os.path.dirname(os.path.dirname(__file__))
    return Path(os.path.normpath(raw))


def storage_dir() -> Path:
    return tongling_root() / "storage"


def default_github_proxy() -> str:
    return os.environ.get("GITHUB_PROXY", "http://127.0.0.1:7897").strip()


def hfinger_json_path() -> Path:
    return storage_dir() / "hfinger" / "data" / "finger.json"


def nuclei_tool_dir() -> Path:
    """工具箱下载：storage/nuclei（nuclei.exe + nuclei-templates/）。"""
    return storage_dir() / "nuclei"


def nuclei_templates_dir() -> Path:
    return nuclei_tool_dir() / "nuclei-templates"


def afrog_tool_dir() -> Path:
    """工具箱下载：storage/afrog（afrog.exe，与 POC 仓库分离）。"""
    return storage_dir() / "afrog"


def afrog_pocs_repo_dir() -> Path:
    """Afrog POC Git 仓库（storage/afrog-pocs，避免覆盖 afrog.exe）。"""
    return storage_dir() / "afrog-pocs"


def afrog_pocs_dir() -> Path:
    primary = afrog_pocs_repo_dir() / "pocs"
    if primary.is_dir():
        return primary
    legacy = storage_dir() / "afrog" / "afrog" / "pocs"
    if legacy.is_dir():
        return legacy
    return primary


def nuclei_index_cache_path() -> Path:
    return storage_dir() / "nuclei" / "poc-index-lite.json"


def hfinger_mcp_script() -> Path:
    return Path(__file__).resolve().parent / "hfinger_mcp.py"


def nuclei_lib_mcp_script() -> Path:
    return Path(__file__).resolve().parent / "nuclei_lib_mcp.py"


def resolve_poc_template_path(source: str, template_path: str) -> Path:
    rel = (template_path or "").replace("\\", "/").lstrip("/")
    if source == "afrog":
        return afrog_pocs_dir() / rel
    return nuclei_templates_dir() / rel
