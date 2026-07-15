"""Claude Code / 统领审计 — 漏洞扫描报告索引与读取。"""

from __future__ import annotations

import base64
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from tongling_web import audit_store

_REPORT_NAME_HINTS = re.compile(
    r"报告|report|pentest|scan|安全测试|漏洞|assessment|audit",
    re.I,
)
_WROTE_MD_RE = re.compile(
    r"(?:Wrote\s+\d+\s+lines\s+to|保存至[：:]|saved\s+to|Write\()\s*[`\"']?([^\s`\"'\)]+\.md)",
    re.I,
)
_MD_IN_TEXT_RE = re.compile(
    r"([A-Za-z]:\\[^\s`\"']+\.md|/[^\s`\"']+\.md|[^\s/\\`\"']*报告[^\s`\"']*\.md)",
    re.I,
)


def _tongling_root() -> str:
    return os.environ.get("TONGLING_ROOT") or os.path.dirname(os.path.dirname(__file__))


def claude_reports_dir(workdir: str) -> str:
    return os.path.join(os.path.normpath(workdir or ""), "reports")


def sanitize_target_for_filename(target: str) -> str:
    s = re.sub(r"[^\w.\-]+", "_", (target or "").strip())[:80].strip("_")
    return s or "target"


def default_scan_report_relpath(target: str, *, stamp: Optional[str] = None) -> str:
    ts = stamp or datetime.now().strftime("%Y%m%d_%H%M")
    name = f"{sanitize_target_for_filename(target)}_{ts}.md"
    return f"reports/{name}"


def default_scan_report_abspath(workdir: str, target: str, *, stamp: Optional[str] = None) -> str:
    rel = default_scan_report_relpath(target, stamp=stamp)
    return os.path.join(os.path.normpath(workdir or ""), rel.replace("/", os.sep))


def ensure_reports_dir(workdir: str) -> str:
    path = claude_reports_dir(workdir)
    os.makedirs(path, exist_ok=True)
    return path


def _norm_path_key(path: str) -> str:
    return os.path.normcase(os.path.normpath(path or ""))


def _looks_like_report_name(name: str) -> bool:
    base = os.path.basename(name or "")
    if not base.lower().endswith(".md"):
        return False
    if _REPORT_NAME_HINTS.search(base):
        return True
    if base.lower() in ("claude.md", "readme.md"):
        return False
    return False


def _guess_target_from_text(text: str) -> str:
    for pat in (
        r"目标站点[`:\s]*([^\s`]+)",
        r"目标[`:\s]*([^\s`]+)",
        r"target[`:\s]*([^\s`]+)",
        r"https?://[^\s`]+",
        r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
    ):
        m = re.search(pat, text or "", re.I)
        if m:
            return (m.group(1) if m.lastindex else m.group(0)).strip("`")
    return ""


def _guess_target_from_filename(name: str) -> str:
    base = os.path.splitext(os.path.basename(name))[0]
    for pat in (
        r"key\.[\w.\-]+",
        r"[\w.\-]+\.(?:com|cn|net|org|top|io)",
        r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
    ):
        m = re.search(pat, base, re.I)
        if m:
            return m.group(0)
    cleaned = re.sub(r"^(?:安全测试报告|扫描报告|report|pentest)[_\-]*", "", base, flags=re.I)
    cleaned = re.sub(r"[_\-]\d{4}[_\-]\d{2}[_\-]\d{2}.*$", "", cleaned)
    if cleaned and re.match(r"^[\w.\-]+$", cleaned):
        return cleaned
    return ""


def _encode_abs_id(full_path: str) -> str:
    raw = os.path.normpath(full_path).encode("utf-8")
    return "abs:" + base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_abs_id(report_id: str) -> str:
    payload = report_id.split(":", 1)[1]
    pad = "=" * (-len(payload) % 4)
    return base64.urlsafe_b64decode(payload + pad).decode("utf-8")


def _allowed_abs_path(full_path: str, workdir: str) -> bool:
    full = os.path.normpath(full_path)
    if not os.path.isfile(full):
        return False
    roots = [
        os.path.normpath(workdir or ""),
        os.path.normpath(_tongling_root()),
        os.path.normpath(os.environ.get("USERPROFILE", "")),
    ]
    for root in roots:
        if root and (full == root or full.startswith(root + os.sep)):
            return True
    return _looks_like_report_name(full)


def _file_meta(full_path: str, *, source: str = "claude", rel_hint: str = "") -> Optional[Dict[str, Any]]:
    full = os.path.normpath(full_path)
    if not os.path.isfile(full):
        return None
    try:
        mtime = os.path.getmtime(full)
        size = os.path.getsize(full)
    except OSError:
        return None
    title = os.path.splitext(os.path.basename(full))[0]
    target = ""
    try:
        with open(full, encoding="utf-8", errors="replace") as f:
            head = f.read(8192)
        if not _looks_like_report_name(full) and "报告" not in head and "# " not in head[:200]:
            if size < 400:
                return None
        target = _guess_target_from_text(head) or _guess_target_from_filename(title)
    except OSError:
        pass
    wd = os.path.normpath(_tongling_root())
    rel = rel_hint
    if not rel:
        try:
            if os.path.commonpath([full, wd]) == wd:
                rel = os.path.relpath(full, wd).replace("\\", "/")
            else:
                rel = full
        except ValueError:
            rel = full
    rid = f"file:{rel}" if not os.path.isabs(full) or rel != full else _encode_abs_id(full)
    return {
        "id": rid,
        "source": source,
        "audit_id": "",
        "title": title,
        "target": target,
        "status": "saved",
        "started_at_text": datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S"),
        "ended_at_text": "",
        "mtime": mtime,
        "mtime_text": datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S"),
        "path": rel,
        "abs_path": full,
        "size": size,
    }


def _file_report_entry(workdir: str, rel_path: str) -> Optional[Dict[str, Any]]:
    wd = os.path.normpath(workdir or "")
    rel = rel_path.replace("\\", "/").lstrip("/")
    full = os.path.normpath(os.path.join(wd, rel.replace("/", os.sep)))
    if not wd or not full.startswith(wd) or not os.path.isfile(full):
        return None
    meta = _file_meta(full, rel_hint=rel)
    if meta:
        meta["id"] = f"file:{rel}"
    return meta


def _audit_report_entry(task: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    audit_id = str(task.get("audit_id") or "").strip()
    if not audit_id:
        return None
    tdir = audit_store._task_dir(audit_id)
    report_path = os.path.join(tdir, "report.md")
    if not os.path.isfile(report_path):
        return None
    try:
        mtime = os.path.getmtime(report_path)
    except OSError:
        mtime = float(task.get("started_at") or 0)
    extra = task.get("extra") if isinstance(task.get("extra"), dict) else {}
    if not extra:
        full = audit_store.get_task(audit_id)
        if isinstance(full, dict):
            extra = full.get("extra") if isinstance(full.get("extra"), dict) else {}
    target = str(extra.get("target") or "").strip()
    if not target:
        target = _guess_target_from_text(str(task.get("title") or ""))
    return {
        "id": f"audit:{audit_id}",
        "source": "audit",
        "audit_id": audit_id,
        "title": task.get("title") or audit_id,
        "target": target,
        "status": task.get("status") or "",
        "started_at_text": task.get("started_at_text") or "",
        "ended_at_text": task.get("ended_at_text") or "",
        "mtime": mtime,
        "mtime_text": datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S"),
        "path": f"storage/audit/{audit_id}/report.md",
        "size": os.path.getsize(report_path) if os.path.isfile(report_path) else 0,
    }


def _extract_md_paths_from_text(text: str) -> List[str]:
    found: List[str] = []
    seen: Set[str] = set()
    for m in _WROTE_MD_RE.finditer(text or ""):
        p = (m.group(1) or "").strip().strip("`\"'")
        if p and _norm_path_key(p) not in seen:
            seen.add(_norm_path_key(p))
            found.append(p)
    for m in _MD_IN_TEXT_RE.finditer(text or ""):
        p = (m.group(1) or "").strip().strip("`\"'")
        if p.lower().endswith(".md") and _looks_like_report_name(p):
            k = _norm_path_key(p)
            if k not in seen:
                seen.add(k)
                found.append(p)
    return found


def _extract_writes_from_claude_jsonl(jsonl_path: Path) -> List[str]:
    if not jsonl_path.is_file():
        return []
    paths: List[str] = []
    seen: Set[str] = set()
    try:
        lines = jsonl_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return paths
    for line in lines:
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if str(obj.get("type", "")) != "assistant":
            continue
        msg = obj.get("message", {})
        content = msg.get("content", [])
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            name = str(block.get("name", "")).lower()
            if name not in ("write", "edit", "multiedit"):
                continue
            inp = block.get("input") or {}
            if not isinstance(inp, dict):
                continue
            fp = str(
                inp.get("file_path")
                or inp.get("path")
                or inp.get("file")
                or ""
            ).strip()
            if not fp.lower().endswith(".md"):
                continue
            if not _looks_like_report_name(fp):
                continue
            k = _norm_path_key(fp)
            if k not in seen:
                seen.add(k)
                paths.append(fp)
    return paths


def _collect_from_claude_sessions(workdir: str) -> List[str]:
    paths: List[str] = []
    try:
        from cc_visual.claude_session import list_sessions
    except ImportError:
        return paths
    wd = os.path.normpath(workdir or "")
    if not wd:
        return paths
    for session in list_sessions(wd)[:30]:
        fp = getattr(session, "path", None)
        if fp:
            paths.extend(_extract_writes_from_claude_jsonl(Path(fp)))
    return paths


def _collect_from_audit_logs(limit: int = 40) -> List[str]:
    paths: List[str] = []
    for task in audit_store.list_tasks(limit):
        audit_id = str(task.get("audit_id") or "")
        if not audit_id:
            continue
        tail = audit_store.read_terminal_tail(audit_id, max_chars=200000)
        paths.extend(_extract_md_paths_from_text(tail))
    return paths


def _collect_workdir_md(workdir: str, *, max_depth: int = 2) -> List[str]:
    wd = os.path.normpath(workdir or "")
    if not wd or not os.path.isdir(wd):
        return []
    found: List[str] = []
    seen: Set[str] = set()

    def walk(base: str, depth: int) -> None:
        if depth > max_depth:
            return
        try:
            names = os.listdir(base)
        except OSError:
            return
        for name in names:
            if name.startswith(".") and name not in (".tongling_hexstrike",):
                continue
            full = os.path.join(base, name)
            if os.path.isfile(full) and name.lower().endswith(".md"):
                if _looks_like_report_name(name) or name.lower().startswith("安全"):
                    k = _norm_path_key(full)
                    if k not in seen:
                        seen.add(k)
                        found.append(full)
            elif os.path.isdir(full) and depth < max_depth:
                if name.lower() in ("node_modules", ".git", "vendor", "__pycache__"):
                    continue
                walk(full, depth + 1)

    walk(wd, 0)
    reports_root = claude_reports_dir(wd)
    if os.path.isdir(reports_root):
        walk(reports_root, 0)
    return found


def _resolve_path_candidate(raw: str, workdir: str) -> Optional[str]:
    p = (raw or "").strip().strip("`\"'")
    if not p:
        return None
    if os.path.isabs(p):
        return os.path.normpath(p) if os.path.isfile(p) else None
    wd = os.path.normpath(workdir or "")
    candidates = [
        os.path.join(wd, p.replace("/", os.sep)),
        os.path.join(os.getcwd(), p.replace("/", os.sep)),
    ]
    aux = os.path.join(wd, ".tongling_hexstrike", "last_report_dir.txt")
    for c in candidates:
        full = os.path.normpath(c)
        if os.path.isfile(full):
            return full
    return None


def _read_expected_report_path(workdir: str) -> str:
    aux = os.path.join(os.path.normpath(workdir or ""), ".tongling_hexstrike", "report_path.txt")
    if not os.path.isfile(aux):
        return ""
    try:
        return open(aux, encoding="utf-8").read().strip()
    except OSError:
        return ""


def list_reports(workdir: str = "", *, limit: int = 80) -> List[Dict[str, Any]]:
    """合并 audit、reports/、工作区与 Claude Write/终端日志中的 .md 报告。"""
    wd = os.path.normpath(workdir or "")
    items: List[Dict[str, Any]] = []
    seen_ids: Set[str] = set()
    seen_paths: Set[str] = set()

    def add_entry(entry: Optional[Dict[str, Any]]) -> None:
        if not entry:
            return
        ap = entry.get("abs_path") or entry.get("path") or ""
        pk = _norm_path_key(str(ap)) if ap else ""
        if pk and pk in seen_paths:
            return
        if entry["id"] in seen_ids:
            return
        seen_ids.add(entry["id"])
        if pk:
            seen_paths.add(pk)
        items.append(entry)

    for task in audit_store.list_tasks(max(limit, 50)):
        if isinstance(task, dict):
            add_entry(_audit_report_entry(task))

    discovered_paths: Set[str] = set(seen_paths)

    if wd and os.path.isdir(wd):
        rel_expected = _read_expected_report_path(wd)
        if rel_expected:
            add_entry(_file_report_entry(wd, rel_expected))
            full = os.path.join(wd, rel_expected.replace("/", os.sep))
            if os.path.isfile(full):
                discovered_paths.add(_norm_path_key(full))

        for full in _collect_workdir_md(wd):
            add_entry(_file_meta(full, rel_hint=os.path.relpath(full, wd).replace("\\", "/") if full.startswith(wd) else full))

    for raw in _collect_from_claude_sessions(wd):
        full = _resolve_path_candidate(raw, wd) or (raw if os.path.isabs(raw) and os.path.isfile(raw) else None)
        if full:
            discovered_paths.add(_norm_path_key(full))
            add_entry(_file_meta(full))

    for raw in _collect_from_audit_logs(limit * 2):
        full = _resolve_path_candidate(raw, wd) or (raw if os.path.isabs(raw) and os.path.isfile(raw) else None)
        if full:
            discovered_paths.add(_norm_path_key(full))
            add_entry(_file_meta(full))

    items.sort(key=lambda x: float(x.get("mtime") or 0), reverse=True)
    return items[: max(1, min(limit, 200))]


def read_report_content(report_id: str, workdir: str = "") -> Tuple[bool, str, Dict[str, Any]]:
    rid = (report_id or "").strip()
    meta: Dict[str, Any] = {"id": rid}
    wd = os.path.normpath(workdir or "")

    if rid.startswith("audit:"):
        audit_id = rid.split(":", 1)[1]
        if not audit_store.get_task(audit_id):
            return False, "审计任务不存在", meta
        meta["audit_id"] = audit_id
        meta["source"] = "audit"
        return True, audit_store.read_report(audit_id), meta

    if rid.startswith("file:"):
        rel = rid.split(":", 1)[1]
        full = os.path.normpath(os.path.join(wd, rel.replace("/", os.sep)))
        if not wd or not full.startswith(wd) or not os.path.isfile(full):
            return False, "报告文件不存在", meta
        try:
            with open(full, encoding="utf-8", errors="replace") as f:
                return True, f.read(), {**meta, "source": "claude", "path": rel, "abs_path": full}
        except OSError as exc:
            return False, str(exc), meta

    if rid.startswith("abs:"):
        try:
            full = _decode_abs_id(rid)
        except Exception:
            return False, "无效的路径编码", meta
        if not _allowed_abs_path(full, wd):
            return False, f"报告文件不可访问: {full}", meta
        try:
            with open(full, encoding="utf-8", errors="replace") as f:
                return True, f.read(), {**meta, "source": "claude", "path": full, "abs_path": full}
        except OSError as exc:
            return False, str(exc), meta

    return False, "无效的报告 ID", meta
