"""Nuclei + Afrog POC 轻量索引（无需 PyYAML）。"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

_ID_RE = re.compile(r"^id:\s*['\"]?([^'\"\n]+)", re.M)
_NAME_RE = re.compile(r"^\s*name:\s*['\"]?([^'\"\n]+)", re.M)
_INFO_NAME_RE = re.compile(r"^\s+name:\s*['\"]?([^'\"\n]+)", re.M)
_SEV_RE = re.compile(r"^\s*severity:\s*(\w+)", re.M)
_INFO_SEV_RE = re.compile(r"^\s+severity:\s*(\w+)", re.M)
_TAGS_RE = re.compile(r"^\s*tags:\s*(.+)$", re.M)
_SLUG_RE = re.compile(r"[^a-z0-9]+")

_SKIP_AFROG_DIRS = {"temp", "v"}
_SKIP_AFROG_FILES = {"pocs.go", "readme.md", "template.yaml", "go-demo.yaml", "tcp-demo.yaml"}


def _slug(text: str, max_len: int = 56) -> str:
    s = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    s = _SLUG_RE.sub("-", s.lower()).strip("-")
    return (s or "tpl")[:max_len]


@dataclass
class NucleiTemplateEntry:
    id: str
    name: str
    severity: str
    tags: List[str] = field(default_factory=list)
    description: str = ""
    template_path: str = ""
    source: str = "nuclei"
    enabled: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "severity": self.severity,
            "tags": self.tags,
            "description": self.description,
            "template_path": self.template_path,
            "source": self.source,
            "enabled": self.enabled,
        }


def _parse_tags(raw: str) -> List[str]:
    raw = raw.strip()
    if not raw:
        return []
    if raw.startswith("["):
        try:
            val = json.loads(raw.replace("'", '"'))
            if isinstance(val, list):
                return [str(t).strip() for t in val if str(t).strip()]
        except json.JSONDecodeError:
            pass
    return [t.strip() for t in re.split(r"[,\s]+", raw) if t.strip()]


def parse_nuclei_yaml_meta(path: Path, templates_root: Path) -> Optional[NucleiTemplateEntry]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    if "http:" not in text:
        return None
    tpl_id = (_ID_RE.search(text) or [None, path.stem])[1]
    name = (_NAME_RE.search(text) or [None, tpl_id])[1]
    severity = (_SEV_RE.search(text) or [None, "info"])[1].lower()
    tags_match = _TAGS_RE.search(text)
    tags = _parse_tags(tags_match.group(1)) if tags_match else []
    rel = str(path.relative_to(templates_root)).replace("\\", "/")
    if rel.startswith("workflows/"):
        return None
    entry_id = f"nu-{_slug(str(tpl_id))}"
    return NucleiTemplateEntry(
        id=entry_id,
        name=str(name).strip(),
        severity=severity,
        tags=["nuclei", *tags[:10]],
        description=str(name).strip()[:300],
        template_path=rel,
        source="nuclei",
        enabled=True,
    )


def parse_afrog_yaml_meta(path: Path, templates_root: Path) -> Optional[NucleiTemplateEntry]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    if path.name.lower() in _SKIP_AFROG_FILES:
        return None
    if not any(k in text for k in ("rules:", "http:", "request:", "expression:")):
        return None
    tpl_id = (_ID_RE.search(text) or [None, path.stem])[1]
    name = (_INFO_NAME_RE.search(text) or _NAME_RE.search(text) or [None, tpl_id])[1]
    sev_m = _INFO_SEV_RE.search(text) or _SEV_RE.search(text)
    severity = (sev_m.group(1) if sev_m else "info").lower()
    tags_match = _TAGS_RE.search(text)
    tags = _parse_tags(tags_match.group(1)) if tags_match else []
    rel = str(path.relative_to(templates_root)).replace("\\", "/")
    parts = rel.split("/")
    if parts and parts[0] in _SKIP_AFROG_DIRS:
        return None
    entry_id = f"af-{_slug(str(tpl_id))}"
    return NucleiTemplateEntry(
        id=entry_id,
        name=str(name).strip(),
        severity=severity,
        tags=["afrog", *tags[:10]],
        description=str(name).strip()[:300],
        template_path=rel,
        source="afrog",
        enabled=True,
    )


def _index_directory(
    root: Path,
    *,
    source: str,
    parser,
) -> List[NucleiTemplateEntry]:
    if not root.is_dir():
        return []
    entries: List[NucleiTemplateEntry] = []
    seen: set[str] = set()
    for yaml_path in sorted(root.rglob("*.yaml")):
        entry = parser(yaml_path, root)
        if not entry:
            continue
        entry.source = source
        eid = entry.id
        n = 2
        while eid in seen:
            eid = f"{entry.id}-{n}"
            n += 1
        seen.add(eid)
        entry.id = eid
        entries.append(entry)
    return entries


def build_combined_poc_index(
    nuclei_dir: Path,
    afrog_dir: Path,
    *,
    write_cache: Optional[Path] = None,
) -> List[NucleiTemplateEntry]:
    entries: List[NucleiTemplateEntry] = []
    entries.extend(_index_directory(nuclei_dir, source="nuclei", parser=parse_nuclei_yaml_meta))
    entries.extend(_index_directory(afrog_dir, source="afrog", parser=parse_afrog_yaml_meta))

    if write_cache:
        write_cache.parent.mkdir(parents=True, exist_ok=True)
        payload = [e.to_dict() for e in entries]
        write_cache.write_text(
            json.dumps({"version": 2, "count": len(payload), "templates": payload}, ensure_ascii=False),
            encoding="utf-8",
        )
    return entries


def build_nuclei_index(templates_dir: Path, *, write_cache: Optional[Path] = None) -> List[NucleiTemplateEntry]:
    """兼容旧调用：仅索引 Nuclei 目录。"""
    entries = _index_directory(templates_dir, source="nuclei", parser=parse_nuclei_yaml_meta)
    if write_cache:
        write_cache.parent.mkdir(parents=True, exist_ok=True)
        payload = [e.to_dict() for e in entries]
        write_cache.write_text(
            json.dumps({"version": 2, "count": len(payload), "templates": payload}, ensure_ascii=False),
            encoding="utf-8",
        )
    return entries


def load_nuclei_index(
    cache_path: Path,
    nuclei_dir: Path,
    afrog_dir: Optional[Path] = None,
) -> List[NucleiTemplateEntry]:
    if cache_path.is_file():
        try:
            data = json.loads(cache_path.read_text(encoding="utf-8"))
            items = data.get("templates", [])
            return [NucleiTemplateEntry(**item) for item in items]
        except (OSError, json.JSONDecodeError, TypeError):
            pass
    if afrog_dir is None:
        from tongling_web.library_paths import afrog_pocs_dir

        afrog_dir = afrog_pocs_dir()
    return build_combined_poc_index(nuclei_dir, afrog_dir, write_cache=cache_path)
