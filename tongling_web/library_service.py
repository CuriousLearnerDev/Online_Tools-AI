"""指纹库 / Nuclei 漏洞库服务（供 Web API 与 MCP 共用）。"""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from html import unescape
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

import httpx

from tongling_web.hfinger_loader import FingerprintEntry, load_hfinger_entries
from tongling_web.library_paths import (
    afrog_pocs_dir,
    hfinger_json_path,
    nuclei_index_cache_path,
    nuclei_templates_dir,
    resolve_poc_template_path,
)
from tongling_web.nuclei_index import (
    NucleiTemplateEntry,
    build_combined_poc_index,
    load_nuclei_index,
)

try:
    import mmh3  # type: ignore
except ImportError:
    mmh3 = None  # type: ignore

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)

# 指纹名称 → POC 检索关键词（用于定向漏洞挖掘）
_PRODUCT_ALIASES: Dict[str, List[str]] = {
    "泛微": ["fanwei", "weaver", "ecology", "e-office", "e-mobile", "e-cology", "泛微"],
    "致远": ["seeyon", "致远", "zhiyuan", "oa"],
    "用友": ["yonyou", "用友", "ufida", "nc", "u8"],
    "通达": ["tongda", "通达"],
    "帆软": ["finereport", "fanruan", "帆软"],
    "海康": ["hikvision", "hik", "海康"],
    "大华": ["dahua", "大华"],
    "thinkphp": ["thinkphp", "think-php"],
    "spring": ["spring", "springboot", "actuator"],
    "tomcat": ["tomcat", "apache-tomcat"],
    "weblogic": ["weblogic", "bea"],
    "shiro": ["shiro", "apache-shiro"],
    "struts": ["struts", "struts2"],
    "jenkins": ["jenkins"],
    "gitlab": ["gitlab"],
    "confluence": ["confluence"],
    "wordpress": ["wordpress", "wp-"],
    "dedecms": ["dedecms", "dede"],
    "discuz": ["discuz"],
}


class FingerprintLibrary:
    def __init__(self) -> None:
        self._entries: Optional[List[FingerprintEntry]] = None

    def reload(self) -> None:
        self._entries = None

    def _data(self) -> List[FingerprintEntry]:
        if self._entries is None:
            self._entries = load_hfinger_entries(hfinger_json_path())
        return self._entries

    def stats(self) -> Dict[str, Any]:
        items = self._data()
        cats = sorted({f.category for f in items})
        return {
            "total": len(items),
            "enabled": sum(1 for f in items if f.enabled),
            "categories": cats,
            "source_path": str(hfinger_json_path()),
            "source_exists": hfinger_json_path().is_file(),
        }

    def search(self, q: str = "", category: str = "", limit: int = 20) -> Dict[str, Any]:
        items = [f for f in self._data() if f.enabled]
        if category:
            items = [f for f in items if f.category == category]
        if q:
            ql = q.lower()
            items = [
                f
                for f in items
                if ql in f.name.lower()
                or ql in f.id.lower()
                or ql in f.description.lower()
                or any(ql in t.lower() for t in f.tags)
            ]
        cap = max(1, min(int(limit or 20), 100))
        page_items = items[:cap]
        return {"items": [f.to_dict() for f in page_items], "total": len(items), "shown": len(page_items)}

    def get(self, fp_id: str) -> Optional[Dict[str, Any]]:
        fp = next((f for f in self._data() if f.id == fp_id), None)
        if not fp:
            return None
        out = fp.to_dict()
        for m in fp.matchers:
            if m.get("type") == "hfinger":
                out["match_method"] = m.get("method")
                out["match_location"] = m.get("location")
                out["match_logic"] = m.get("logic")
                out["match_rules"] = m.get("rules") or []
                break
        return out

    @staticmethod
    def _normalize_target(target: str) -> str:
        t = (target or "").strip()
        if not t:
            return ""
        if not re.match(r"^https?://", t, re.I):
            t = "http://" + t
        p = urlparse(t)
        if not p.netloc:
            return ""
        return f"{p.scheme}://{p.netloc}"

    @staticmethod
    def _extract_title(body: str) -> str:
        m = _TITLE_RE.search(body or "")
        return unescape(m.group(1).strip()) if m else ""

    @staticmethod
    def _favicon_hashes(content: bytes) -> set[int]:
        if not content or not mmh3:
            return set()
        hashes: set[int] = set()
        try:
            hashes.add(mmh3.hash(content))
            hashes.add(mmh3.hash(base64.encodebytes(content)))
            hashes.add(mmh3.hash(base64.standard_b64encode(content)))
        except Exception:
            pass
        return hashes

    def _fetch_context(self, target: str) -> Tuple[str, str, str, set[int], str, str]:
        base = self._normalize_target(target)
        url = base + "/"
        favicon_url = urljoin(base + "/", "favicon.ico")
        body = ""
        title = ""
        headers_str = ""
        fav_hashes: set[int] = set()
        page_url = url
        try:
            with httpx.Client(follow_redirects=True, timeout=20.0) as client:
                resp = client.get(url, headers={"User-Agent": "Mozilla/5.0 (HFinger-MCP)"})
                body = resp.text[:120_000]
                title = self._extract_title(body)
                headers_str = "\n".join(f"{k}: {v}" for k, v in resp.headers.items())
                page_url = str(resp.url)
                try:
                    fav = client.get(favicon_url, timeout=8.0)
                    if fav.status_code == 200 and fav.content:
                        fav_hashes = self._favicon_hashes(fav.content)
                except Exception:
                    pass
        except Exception as exc:
            return base, body, title, fav_hashes, headers_str, str(exc)
        return base, body, title, fav_hashes, headers_str, page_url

    @staticmethod
    def _match_hfinger_rule(
        body: str,
        title: str,
        headers_str: str,
        fav_hashes: set[int],
        m: Dict[str, Any],
    ) -> Tuple[bool, str]:
        method = str(m.get("method", "keyword")).lower()
        location = str(m.get("location", "body")).lower()
        logic = str(m.get("logic", "and")).lower()
        rules = [str(r) for r in (m.get("rules") or []) if str(r).strip()]
        if not rules:
            return False, ""

        if method == "faviconhash":
            if not mmh3:
                return False, "faviconhash 需要 mmh3 模块"
            expected = {int(r) for r in rules if r.lstrip("-").isdigit()}
            hit = expected & fav_hashes
            if hit:
                return True, f"faviconhash={next(iter(hit))}"
            return False, ""

        haystack = {"body": body, "title": title, "header": headers_str, "headers": headers_str}
        text = haystack.get(location, body)
        hits = [r for r in rules if r in text]
        if logic == "or":
            ok = len(hits) > 0
        else:
            ok = len(hits) == len(rules)
        if ok:
            return True, f"{location} matched: {', '.join(hits[:3])}"
        return False, ""

    def _evaluate(self, body: str, title: str, headers_str: str, fav_hashes: set[int], fp: FingerprintEntry) -> Tuple[bool, str]:
        for m in fp.matchers:
            if m.get("type") != "hfinger":
                continue
            return self._match_hfinger_rule(body, title, headers_str, fav_hashes, m)
        return False, ""

    def probe(self, target: str, fingerprint_id: str) -> Dict[str, Any]:
        fp = next((f for f in self._data() if f.id == fingerprint_id), None)
        if not fp:
            return {"matched": False, "error": f"指纹不存在: {fingerprint_id}"}
        base, body, title, fav_hashes, headers_str, page_url = self._fetch_context(target)
        if not base:
            return {"matched": False, "error": "目标 URL 无效", "target": target}
        ok, evidence = self._evaluate(body, title, headers_str, fav_hashes, fp)
        return {
            "id": fp.id,
            "name": fp.name,
            "matched": ok,
            "target": base,
            "url": page_url,
            "evidence": evidence,
        }

    def scan(self, target: str, category: str = "", limit: int = 15) -> Dict[str, Any]:
        cap = max(1, min(int(limit or 15), 50))
        items = [f for f in self._data() if f.enabled]
        if category:
            items = [f for f in items if f.category == category]
        base, body, title, fav_hashes, headers_str, page_url = self._fetch_context(target)
        if not base:
            return {"target": target, "matched": 0, "total": 0, "results": [], "error": "目标 URL 无效"}

        matched_rows: List[Dict[str, Any]] = []
        unmatched_rows: List[Dict[str, Any]] = []
        for fp in items:
            ok, evidence = self._evaluate(body, title, headers_str, fav_hashes, fp)
            row = {
                "id": fp.id,
                "name": fp.name,
                "matched": ok,
                "target": base,
                "url": page_url,
                "evidence": evidence,
            }
            if ok:
                matched_rows.append(row)
            else:
                unmatched_rows.append(row)
            if len(matched_rows) >= cap:
                break

        results = matched_rows[:cap] if matched_rows else unmatched_rows[: min(3, cap)]
        return {
            "target": base,
            "kind": "fingerprint",
            "total": len(items),
            "matched": len(matched_rows),
            "results": results,
        }


class NucleiLibrary:
    def __init__(self) -> None:
        self._entries: Optional[List[NucleiTemplateEntry]] = None

    def reload(self) -> None:
        self._entries = None

    def _data(self) -> List[NucleiTemplateEntry]:
        if self._entries is None:
            self._entries = load_nuclei_index(
                nuclei_index_cache_path(),
                nuclei_templates_dir(),
                afrog_pocs_dir(),
            )
        return self._entries

    def reindex(self) -> Dict[str, Any]:
        nuclei_dir = nuclei_templates_dir()
        afrog_dir = afrog_pocs_dir()
        if not nuclei_dir.is_dir() and not afrog_dir.is_dir():
            return {"ok": False, "error": "Nuclei / Afrog POC 目录均不存在，请先拉取最新 POC"}
        entries = build_combined_poc_index(
            nuclei_dir,
            afrog_dir,
            write_cache=nuclei_index_cache_path(),
        )
        self._entries = entries
        nu = sum(1 for e in entries if e.source == "nuclei")
        af = sum(1 for e in entries if e.source == "afrog")
        return {
            "ok": True,
            "indexed": len(entries),
            "nuclei_indexed": nu,
            "afrog_indexed": af,
            "cache": str(nuclei_index_cache_path()),
        }

    def stats(self) -> Dict[str, Any]:
        items = self._data()
        sev: Dict[str, int] = {}
        for e in items:
            sev[e.severity] = sev.get(e.severity, 0) + 1
        nuclei_dir = nuclei_templates_dir()
        afrog_dir = afrog_pocs_dir()
        nuclei_yaml = sum(1 for _ in nuclei_dir.rglob("*.yaml")) if nuclei_dir.is_dir() else 0
        afrog_yaml = sum(1 for _ in afrog_dir.rglob("*.yaml")) if afrog_dir.is_dir() else 0
        return {
            "total": len(items),
            "nuclei_indexed": sum(1 for e in items if e.source == "nuclei"),
            "afrog_indexed": sum(1 for e in items if e.source == "afrog"),
            "yaml_files_total": nuclei_yaml + afrog_yaml,
            "nuclei_yaml_total": nuclei_yaml,
            "afrog_yaml_total": afrog_yaml,
            "indexed_note": "Nuclei HTTP 模板 + Afrog POC（需先指纹识别再定向扫描）",
            "severity": sev,
            "source_path": str(nuclei_dir),
            "afrog_path": str(afrog_dir),
            "source_exists": nuclei_dir.is_dir() or afrog_dir.is_dir(),
            "index_cache": str(nuclei_index_cache_path()),
            "index_cached": nuclei_index_cache_path().is_file(),
        }

    @staticmethod
    def _keywords_from_products(products: List[str]) -> List[str]:
        keys: List[str] = []
        seen: set[str] = set()

        def add_key(raw: str) -> None:
            k = raw.strip().lower()
            if len(k) < 2 or k in seen:
                return
            seen.add(k)
            keys.append(k)

        for prod in products:
            text = (prod or "").strip()
            if not text:
                continue
            add_key(text)
            for part in re.split(r"[\s/|,，、\-_]+", text):
                add_key(part)
            lower = text.lower()
            for _label, aliases in _PRODUCT_ALIASES.items():
                if _label in text or any(a in lower for a in aliases):
                    for a in aliases:
                        add_key(a)
                    add_key(_label)
        return keys[:24]

    def select_for_products(self, identified_products: str, *, limit: int = 40) -> Dict[str, Any]:
        products = [p.strip() for p in (identified_products or "").split(",") if p.strip()]
        if not products:
            return {
                "products": [],
                "keywords": [],
                "items": [],
                "total": 0,
                "error": "identified_products 不能为空，请先运行 fingerprint_scan",
            }
        keywords = self._keywords_from_products(products)
        scored: List[Tuple[int, NucleiTemplateEntry]] = []
        for entry in self._data():
            if not entry.enabled:
                continue
            hay = f"{entry.name} {entry.template_path} {' '.join(entry.tags)}".lower()
            score = sum(2 if k in entry.name.lower() else 1 for k in keywords if k in hay)
            if score > 0:
                scored.append((score, entry))
        scored.sort(key=lambda x: (-x[0], x[1].severity != "critical", x[1].name))
        cap = max(1, min(int(limit or 40), 80))
        picked = [e for _, e in scored[:cap]]
        return {
            "products": products,
            "keywords": keywords,
            "items": [e.to_dict() for e in picked],
            "total": len(scored),
            "shown": len(picked),
        }

    def search(
        self,
        q: str = "",
        severity: str = "",
        tags: str = "",
        source: str = "",
        limit: int = 20,
    ) -> Dict[str, Any]:
        items = [e for e in self._data() if e.enabled]
        if source:
            src = source.strip().lower()
            items = [e for e in items if e.source == src]
        if severity:
            sevs = {s.strip().lower() for s in severity.split(",") if s.strip()}
            items = [e for e in items if e.severity.lower() in sevs]
        if tags:
            tag_set = {t.strip().lower() for t in tags.split(",") if t.strip()}
            items = [e for e in items if tag_set & {t.lower() for t in e.tags}]
        if q:
            ql = q.lower()
            items = [
                e
                for e in items
                if ql in e.name.lower()
                or ql in e.id.lower()
                or ql in e.template_path.lower()
                or any(ql in t.lower() for t in e.tags)
            ]
        cap = max(1, min(int(limit or 20), 100))
        page_items = items[:cap]
        return {"items": [e.to_dict() for e in page_items], "total": len(items), "shown": len(page_items)}

    def get(self, entry_id: str) -> Optional[Dict[str, Any]]:
        entry = next((e for e in self._data() if e.id == entry_id), None)
        if not entry:
            return None
        out = entry.to_dict()
        tpl_path = resolve_poc_template_path(entry.source, entry.template_path)
        out["yaml_path_abs"] = str(tpl_path)
        if tpl_path.is_file():
            try:
                out["yaml_preview"] = tpl_path.read_text(encoding="utf-8", errors="replace")[:16000]
            except OSError:
                out["yaml_preview"] = ""
        return out

    @staticmethod
    def _hexstrike_url() -> str:
        port = os.environ.get("HEXSTRIKE_PORT") or os.environ.get("TONGLING_API_PORT") or "15038"
        return os.environ.get("HEXSTRIKE_SERVER") or f"http://127.0.0.1:{port}"

    @staticmethod
    def _api_headers() -> Dict[str, str]:
        token = (os.environ.get("HEXSTRIKE_API_TOKEN") or os.environ.get("TONGLING_WEB_TOKEN") or "").strip()
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    @staticmethod
    def _find_nuclei_binary() -> str:
        env = (os.environ.get("NUCLEI_BINARY") or "").strip()
        if env and os.path.isfile(env):
            return env
        which = shutil.which("nuclei")
        return which or ""

    def scan(
        self,
        target: str,
        identified_products: str = "",
        severity: str = "critical,high,medium",
        limit: int = 30,
    ) -> Dict[str, Any]:
        """定向 POC 扫描：必须先 fingerprint_scan 识别组件，再传入 identified_products。"""
        target = (target or "").strip()
        if not target:
            return {"ok": False, "error": "target 不能为空"}
        products = [p.strip() for p in (identified_products or "").split(",") if p.strip()]
        if not products:
            return {
                "ok": False,
                "error": "必须先运行 fingerprint_scan 识别 Web 组件，再传入 identified_products（逗号分隔，如「泛微 OA,Tomcat」）",
                "hint": "禁止对未识别组件做全量漏洞扫描；流程：fingerprint_scan → nuclei_scan",
            }

        selection = self.select_for_products(identified_products, limit=limit)
        templates = selection.get("items") or []
        if not templates:
            return {
                "ok": False,
                "error": f"未找到与 {products} 匹配的 POC 模板",
                "keywords": selection.get("keywords") or [],
                "products": products,
            }

        nuclei_paths: List[str] = []
        afrog_keywords: List[str] = list(selection.get("keywords") or [])[:6]
        for t in templates:
            src = t.get("source", "nuclei")
            rel = t.get("template_path", "")
            abs_path = resolve_poc_template_path(src, rel)
            if not abs_path.is_file():
                continue
            if src == "afrog":
                continue
            nuclei_paths.append(str(abs_path))

        results: Dict[str, Any] = {
            "ok": True,
            "mode": "targeted",
            "target": target,
            "products": products,
            "keywords": selection.get("keywords") or [],
            "selected_templates": len(templates),
            "nuclei_templates": len(nuclei_paths),
            "template_preview": [t.get("name") for t in templates[:12]],
            "engines": [],
        }

        if nuclei_paths:
            nu_result = self._scan_nuclei_targeted(target, nuclei_paths, severity)
            results["engines"].append(nu_result)
            results["nuclei"] = nu_result

        if afrog_keywords:
            af_result = self._scan_afrog_targeted(target, afrog_keywords, severity)
            results["engines"].append(af_result)
            results["afrog"] = af_result

        matched = sum(int(r.get("matched") or 0) for r in results["engines"])
        results["matched"] = matched
        results["ok"] = any(r.get("ok") for r in results["engines"]) or matched > 0
        return results

    def _scan_nuclei_targeted(self, target: str, template_paths: List[str], severity: str) -> Dict[str, Any]:
        url_target = target if re.match(r"^https?://", target, re.I) else "http://" + target
        exe = self._find_nuclei_binary()
        if exe and template_paths:
            cmd = [exe, "-u", url_target, "-jsonl", "-silent", "-nc", "-severity", severity or "critical,high,medium"]
            for p in template_paths[:40]:
                cmd.extend(["-t", p])
            started = time.time()
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300, encoding="utf-8", errors="replace")
            except subprocess.TimeoutExpired:
                return {"ok": False, "engine": "nuclei-cli", "error": "nuclei CLI 超时", "matched": 0}
            findings: List[Dict[str, Any]] = []
            for line in (proc.stdout or "").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    findings.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
            return {
                "ok": proc.returncode in (0, 1),
                "engine": "nuclei-cli",
                "matched": len(findings),
                "findings": findings[:50],
                "stderr": (proc.stderr or "")[:1500],
                "duration_sec": round(time.time() - started, 2),
            }

        # HexStrike：传模板文件列表（逗号分隔）
        api_url = self._hexstrike_url().rstrip("/") + "/api/tools/nuclei"
        payload = {
            "target": url_target,
            "severity": severity,
            "template": ",".join(template_paths[:40]),
            "use_recovery": True,
        }
        return self._post_hexstrike(api_url, payload, engine="hexstrike-nuclei")

    def _scan_afrog_targeted(self, target: str, keywords: List[str], severity: str) -> Dict[str, Any]:
        api_url = self._hexstrike_url().rstrip("/") + "/api/tools/afrog"
        search = keywords[0] if keywords else ""
        payload = {
            "target": target,
            "search": search,
            "severity": severity,
            "use_recovery": True,
        }
        result = self._post_hexstrike(api_url, payload, engine="hexstrike-afrog")
        result["search_keyword"] = search
        result["keywords"] = keywords
        return result

    def _post_hexstrike(self, url: str, payload: Dict[str, Any], *, engine: str) -> Dict[str, Any]:
        started = time.time()
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers=self._api_headers(),
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=320) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")[:500]
            return {"ok": False, "engine": engine, "error": f"HTTP {exc.code}: {body}", "matched": 0}
        except Exception as exc:
            return {"ok": False, "engine": engine, "error": str(exc), "matched": 0}

        stdout = str(data.get("stdout") or "")
        matched = max(0, stdout.lower().count("[high]") + stdout.lower().count("[critical]") + stdout.lower().count("[medium]"))
        if not matched and data.get("success"):
            matched = stdout.count("vuln") or (1 if "found" in stdout.lower() else 0)
        return {
            "ok": bool(data.get("success")),
            "engine": engine,
            "matched": matched,
            "stdout": stdout[:8000],
            "stderr": str(data.get("stderr") or "")[:2000],
            "duration_sec": round(time.time() - started, 2),
        }


_fp_lib: Optional[FingerprintLibrary] = None
_nu_lib: Optional[NucleiLibrary] = None


def get_fingerprint_library() -> FingerprintLibrary:
    global _fp_lib
    if _fp_lib is None:
        _fp_lib = FingerprintLibrary()
    return _fp_lib


def get_nuclei_library() -> NucleiLibrary:
    global _nu_lib
    if _nu_lib is None:
        _nu_lib = NucleiLibrary()
    return _nu_lib
