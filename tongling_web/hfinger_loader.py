"""HFinger finger.json → 内部指纹条目。"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slug(text: str, max_len: int = 48) -> str:
    s = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    s = _SLUG_RE.sub("-", s.lower()).strip("-")
    return (s or "cms")[:max_len]


def _guess_category(cms: str) -> str:
    t = cms.lower()
    if any(k in t for k in ("oa", "协同", "办公", "erp", "crm")):
        return "oa"
    if any(k in t for k in ("防火墙", "waf", "vpn", "堡垒机", "审计", "安全")):
        return "security"
    if any(k in t for k in ("cms", "wordpress", "discuz", "门户", "建站")):
        return "cms"
    if any(k in t for k in ("api", "gateway", "微服务")):
        return "api"
    if any(k in t for k in ("nginx", "apache", "tomcat", "iis", "weblogic", "websphere")):
        return "middleware"
    return "cms"


@dataclass
class FingerprintEntry:
    id: str
    name: str
    category: str
    tags: List[str] = field(default_factory=list)
    description: str = ""
    enabled: bool = True
    probe: Dict[str, Any] = field(default_factory=dict)
    matchers: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "tags": self.tags,
            "description": self.description,
            "enabled": self.enabled,
            "probe": self.probe,
            "matchers": self.matchers,
        }


def load_hfinger_entries(path: Path) -> List[FingerprintEntry]:
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    raw_list = data.get("finger") or data.get("fingerprint") or []
    entries: List[FingerprintEntry] = []
    seen_ids: set[str] = set()

    for idx, raw in enumerate(raw_list):
        if not isinstance(raw, dict):
            continue
        cms = str(raw.get("cms") or raw.get("name") or f"cms-{idx}").strip()
        method = str(raw.get("method") or "keyword").lower()
        location = str(raw.get("location") or "body").lower()
        logic = str(raw.get("logic") or "and").lower()
        rules = [str(r) for r in (raw.get("rule") or raw.get("rules") or []) if str(r).strip()]
        if not rules:
            continue

        base_id = f"hf-{_slug(cms)}"
        fp_id = base_id
        n = 2
        while fp_id in seen_ids:
            fp_id = f"{base_id}-{n}"
            n += 1
        seen_ids.add(fp_id)

        entries.append(
            FingerprintEntry(
                id=fp_id,
                name=cms,
                category=_guess_category(cms),
                tags=["hfinger", method, location],
                description=f"HFinger · {method} · {location} · {logic}",
                enabled=True,
                probe={"method": "GET", "path": "/", "hfinger": True},
                matchers=[
                    {
                        "type": "hfinger",
                        "method": method,
                        "location": location,
                        "logic": logic,
                        "rules": rules,
                    }
                ],
            )
        )
    return entries
