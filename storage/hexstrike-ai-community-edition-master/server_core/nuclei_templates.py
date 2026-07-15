"""
Default nuclei-templates directory for API / MCP when no -t is passed.

Resolution order:
  1) NUCLEI_TEMPLATES_DIR environment variable (must exist)
  2) <hexstrike_repo_parent>/nuclei/nuclei-templates  (i.e. ../nuclei/nuclei-templates from repo root)
  3) <hexstrike_repo>/nuclei/nuclei-templates
"""
from __future__ import annotations

import os
from pathlib import Path

# server_core/nuclei_templates.py -> parent = server_core, parent.parent = hexstrike project root
_REPO_ROOT = Path(__file__).resolve().parent.parent


def resolve_nuclei_templates_dir() -> str:
    env = (os.environ.get("NUCLEI_TEMPLATES_DIR") or "").strip()
    if env:
        p = Path(env)
        if p.is_dir():
            return str(p.resolve())

    candidates = [
        _REPO_ROOT.parent / "nuclei" / "nuclei-templates",
        _REPO_ROOT / "nuclei" / "nuclei-templates",
    ]
    for c in candidates:
        if c.is_dir():
            return str(c.resolve())
    return ""
