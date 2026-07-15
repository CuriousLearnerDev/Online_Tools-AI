"""扫描结果 → 攻击链图谱数据（HexStrike sessions + Claude Code jsonl）。"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

TARGET_KEYS = ("target", "url", "host", "ip", "domain", "file", "u", "h")

RECON_TOOLS = {
    "nmap", "masscan", "rustscan", "subfinder", "amass", "httpx", "katana",
    "gobuster", "feroxbuster", "ffuf", "hakrawler", "waybackurls", "gau",
    "fscan", "kscan", "subjack", "dnsx", "naabu", "whois",
    "curl", "wget",
}
VULN_TOOLS = {
    "nuclei", "sqlmap", "nikto", "wpscan", "joomscan", "dalfox", "commix",
    "afrog", "springboot_scan", "graphql_scanner", "trivy", "checkov",
    "terrascan", "zap", "burpsuite",
}
EXPLOIT_TOOLS = {"hydra", "metasploit", "msfvenom", "beef", "venom"}

ALL_SCAN_TOOLS = RECON_TOOLS | VULN_TOOLS | EXPLOIT_TOOLS

# 高频探测工具 — 图谱中默认合并为「curl ×N」减少纵向堆叠
NOISE_PROBE_TOOLS = {"curl", "wget", "httpx"}

PHASE_LABELS = {
    "target": "目标 Target",
    "recon": "Recon 侦察",
    "vuln": "Scan 扫描",
    "exploit": "Exploit 利用",
    "action": "Action 其他",
}

PHASE_ORDER = {"target": 0, "recon": 1, "vuln": 2, "exploit": 3, "action": 4}

PHASE_SWIMLANES = [
    {"id": "recon", "label": "Recon 侦察", "type": "recon", "order": 1},
    {"id": "vuln", "label": "Scan 扫描", "type": "vuln", "order": 2},
    {"id": "exploit", "label": "Exploit 利用", "type": "exploit", "order": 3},
    {"id": "action", "label": "Action 其他", "type": "action", "order": 4},
]

_URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.I)
_IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_DOMAIN_RE = re.compile(r"\b[\w.-]+\.(?:com|cn|net|org|io|edu|gov|local)\b", re.I)


def _extract_target(params: Dict[str, Any]) -> str:
    if not params:
        return "unknown"
    for key in TARGET_KEYS:
        val = params.get(key)
        if val:
            return str(val).strip()[:120]
    for val in params.values():
        if isinstance(val, str) and val.strip():
            return val.strip()[:120]
    return "unknown"


def _tool_category(tool: str) -> str:
    name = (tool or "unknown").lower().split("/")[-1]
    if name in RECON_TOOLS:
        return "recon"
    if name in VULN_TOOLS:
        return "vuln"
    if name in EXPLOIT_TOOLS:
        return "exploit"
    return "action"


def _phase_label(cat: str) -> str:
    return PHASE_LABELS.get(cat or "action", cat or "action")


def _parse_timestamp(ts: Any) -> float:
    if ts is None:
        return 0.0
    if isinstance(ts, (int, float)):
        return float(ts)
    text = str(ts).strip()
    if not text:
        return 0.0
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            from datetime import datetime

            return datetime.strptime(text.replace("Z", "")[:19], fmt.replace("Z", "")).timestamp()
        except ValueError:
            continue
    try:
        from datetime import datetime

        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def _find_audit_for_run(timestamp: Any, workdir: str = "") -> Optional[str]:
    """按时间窗口匹配 Web 终端审计任务。"""
    run_ts = _parse_timestamp(timestamp)
    if not run_ts:
        return None
    try:
        from tongling_web import audit_store

        for task in audit_store.list_tasks(120):
            started = float(task.get("started_at") or 0)
            ended = float(task.get("ended_at") or 0) or (started + 86400)
            if run_ts < started - 120 or run_ts > ended + 120:
                continue
            twd = str(task.get("workdir") or "")
            if workdir and twd and workdir not in twd and twd not in workdir:
                continue
            return str(task.get("audit_id") or "")
    except Exception:
        pass
    return None


def _terminal_excerpt_for_tool(audit_id: str, tool: str, stdout: str = "") -> str:
    try:
        from tongling_web import audit_store

        log = audit_store.read_terminal_tail(audit_id, max_chars=50000)
        if not log:
            return ""
        needles = [tool]
        if stdout:
            snippet = stdout.strip()[:80]
            if len(snippet) > 12:
                needles.append(snippet)
        for needle in needles:
            if not needle:
                continue
            idx = log.find(needle)
            if idx >= 0:
                start = max(0, idx - 800)
                end = min(len(log), idx + 2400)
                chunk = log[start:end]
                if start > 0:
                    chunk = "…\n" + chunk
                if end < len(log):
                    chunk += "\n…"
                return chunk
        return audit_store.read_terminal_tail(audit_id, max_chars=4000)
    except Exception:
        return ""


def _hexstrike_run_by_id(run_id: Any) -> Optional[Dict[str, Any]]:
    try:
        rid = int(run_id)
    except (TypeError, ValueError):
        return None
    try:
        from server_core.singletons import run_history

        for run in run_history.get_all():
            if int(run.get("id") or -1) == rid:
                return dict(run)
    except Exception:
        pass
    return None


def _claude_run_by_id(session_id: str, run_id: Any, workdir: str = "") -> Optional[Dict[str, Any]]:
    wd = workdir or _default_claude_workdir()
    try:
        from cc_visual.claude_session import list_sessions

        sessions = list_sessions(wd)
    except Exception:
        return None
    target = next((s for s in sessions if s.session_id == session_id), None)
    if not target:
        return None
    runs = extract_runs_from_claude_jsonl(target.path, claude_session_id=session_id)
    try:
        rid = int(run_id)
    except (TypeError, ValueError):
        return None
    for run in runs:
        if int(run.get("id") or -1) == rid:
            return {**run, "claude_session_id": session_id, "source": "claude"}
    return None


def get_run_detail(
    run_id: Any,
    *,
    source: str = "hexstrike",
    claude_session_id: str = "",
    workdir: str = "",
) -> Optional[Dict[str, Any]]:
    """节点点击：完整 run 输出 + 审计/终端关联。"""
    run: Optional[Dict[str, Any]] = None
    src = (source or "hexstrike").lower()
    if src == "claude" and claude_session_id:
        run = _claude_run_by_id(claude_session_id, run_id, workdir)
    else:
        run = _hexstrike_run_by_id(run_id)
        if run:
            run["source"] = "hexstrike"

    if not run:
        return None

    tool = str(run.get("tool") or "")
    params = run.get("params") or {}
    target = _extract_target(params)
    cat = _tool_category(tool)
    stdout = str(run.get("stdout") or "")
    stderr = str(run.get("stderr") or "")
    audit_id = _find_audit_for_run(run.get("timestamp"), workdir)
    terminal_excerpt = _terminal_excerpt_for_tool(audit_id, tool, stdout) if audit_id else ""

    return {
        "run_id": run.get("id"),
        "tool": tool,
        "target": target,
        "phase": cat,
        "phase_label": _phase_label(cat),
        "source": run.get("source") or src,
        "claude_session_id": run.get("claude_session_id") or claude_session_id,
        "claude_tool": run.get("claude_tool", ""),
        "tool_use_id": run.get("tool_use_id", ""),
        "sequence": run.get("sequence"),
        "success": bool(run.get("success")),
        "return_code": run.get("return_code"),
        "execution_time": run.get("execution_time"),
        "timestamp": run.get("timestamp", ""),
        "params": params,
        "stdout": stdout,
        "stderr": stderr,
        "findings": _parse_severity_lines(stdout)[:20],
        "audit_id": audit_id,
        "terminal_excerpt": terminal_excerpt,
        "hexstrike_run_url": f"/tongling/hs/#/runs/{run.get('id')}" if src == "hexstrike" else "",
    }


def get_group_run_detail(
    group_key: str,
    *,
    source: str = "hexstrike",
    claude_session_id: str = "",
    workdir: str = "",
) -> Optional[Dict[str, Any]]:
    """合并节点详情 — 重新聚合后匹配 group id。"""
    runs: List[Dict[str, Any]] = []
    if source == "claude" and claude_session_id:
        wd = workdir or _default_claude_workdir()
        try:
            from cc_visual.claude_session import list_sessions

            target_sess = next(
                (s for s in list_sessions(wd) if s.session_id == claude_session_id),
                None,
            )
            if target_sess:
                runs = extract_runs_from_claude_jsonl(
                    target_sess.path, claude_session_id=claude_session_id
                )
        except Exception:
            pass
    else:
        try:
            from server_core.singletons import run_history

            runs = [dict(r) for r in run_history.get_all()]
        except Exception:
            pass
    if not runs:
        return None
    ordered = list(reversed(runs))
    display_runs, _ = _aggregate_probe_runs_session(ordered)
    for run in display_runs:
        if run.get("grouped") and str(run.get("id")) == group_key:
            tool = str(run.get("tool") or "")
            params = run.get("params") or {}
            target = _extract_target(params)
            cat = _tool_category(tool)
            stdout = str(run.get("stdout") or "")
            return {
                "run_id": group_key,
                "tool": tool,
                "target": target,
                "phase": cat,
                "phase_label": _phase_label(cat),
                "source": source,
                "claude_session_id": claude_session_id,
                "claude_tool": run.get("claude_tool", ""),
                "tool_kind": run.get("tool_kind", ""),
                "grouped": True,
                "group_count": run.get("group_count"),
                "group_members": run.get("group_members"),
                "group_samples": run.get("group_samples"),
                "success": bool(run.get("success")),
                "stdout": stdout,
                "stderr": "",
                "findings": run.get("findings") or _parse_severity_lines(stdout)[:20],
                "terminal_excerpt": "",
            }
    return None


def get_node_detail(
    node_id: str,
    *,
    source: str = "hexstrike",
    claude_session_id: str = "",
    workdir: str = "",
) -> Optional[Dict[str, Any]]:
    if not node_id:
        return None
    if node_id.startswith("group_"):
        return get_group_run_detail(
            node_id[6:],
            source=source,
            claude_session_id=claude_session_id,
            workdir=workdir,
        )
    if not node_id.startswith("run_"):
        return None
    run_id = node_id[4:]
    return get_run_detail(
        run_id,
        source=source,
        claude_session_id=claude_session_id,
        workdir=workdir,
    )


def _parse_severity_lines(text: str) -> List[Dict[str, str]]:
    if not text:
        return []
    findings: List[Dict[str, str]] = []
    patterns = [
        (r"\b(CRITICAL|HIGH|MEDIUM|LOW|INFO)\b", re.I),
        (r"(CVE-\d{4}-\d+)", re.I),
    ]
    for line in text.splitlines():
        line = line.strip()
        if len(line) < 8:
            continue
        upper = line.upper()
        if not any(k in upper for k in ("CVE-", "VULN", "CRITICAL", "HIGH", "SQL", "XSS", "RCE", "[WARN", "[CRIT")):
            continue
        sev = "info"
        if "CRIT" in upper or "CRITICAL" in upper:
            sev = "critical"
        elif "HIGH" in upper:
            sev = "high"
        elif "MEDIUM" in upper or "WARN" in upper:
            sev = "medium"
        elif "LOW" in upper:
            sev = "low"
        cve_m = re.search(r"CVE-\d{4}-\d+", line, re.I)
        findings.append({
            "severity": sev,
            "text": line[:240],
            "cve": cve_m.group(0) if cve_m else "",
        })
        if len(findings) >= 50:
            break
    return findings


def _load_hexstrike_data() -> Tuple[List[Dict], List[Dict], List[Dict]]:
    """返回 (active_sessions, completed_sessions, runs)。"""
    active: List[Dict] = []
    completed: List[Dict] = []
    runs: List[Dict] = []
    try:
        from server_core.session_store import SessionStore

        store = SessionStore()
        for sid in store.list_active():
            data = store.load(sid)
            if data:
                active.append(data)
        completed = store.list_completed()
    except Exception:
        pass
    try:
        from server_core.singletons import run_history

        runs = run_history.get_all()
    except Exception:
        pass
    return active, completed, runs


def load_session_detail(session_id: str) -> Optional[Dict[str, Any]]:
    try:
        from server_core.session_store import SessionStore

        store = SessionStore()
        data = store.load(session_id) or store.load_completed(session_id)
        return data
    except Exception:
        return None


def _is_noise_probe(tool: str) -> bool:
    return _normalize_tool_name(tool) in NOISE_PROBE_TOOLS


def _run_has_signal(run: Dict[str, Any]) -> bool:
    if not run.get("success", True):
        return True
    if _parse_severity_lines(str(run.get("stdout") or "")):
        return True
    return False


def _probe_host_key(run: Dict[str, Any]) -> str:
    """探测步骤按 host 分桶（跨会话步骤合并）。"""
    params = run.get("params") or {}
    target = _extract_target(params)
    texts = [
        target,
        str(params.get("url") or ""),
        str(params.get("host") or ""),
        str(params.get("domain") or ""),
        str(params.get("command") or ""),
    ]
    for text in texts:
        if not text or text == "unknown":
            continue
        m = _URL_RE.search(text)
        if m:
            try:
                host = urlparse(m.group(0)).netloc or urlparse(m.group(0)).path
                host = host.split("@")[-1].split(":")[0].strip().lower()
                if host:
                    return host[:120]
            except Exception:
                pass
        m = _IP_RE.search(text)
        if m:
            return m.group(0)
        m = _DOMAIN_RE.search(text)
        if m:
            return m.group(0).lower()[:120]
    if target and target != "unknown":
        return target.lower()[:120]
    return "_unknown"


def _probe_status_stats(members: List[Dict[str, Any]]) -> Dict[str, int]:
    stats: Dict[str, int] = {}
    patterns = (
        re.compile(r"< HTTP/\d[\d.]* (\d{3})", re.I),
        re.compile(r"HTTP/\d[\d.]* (\d{3})", re.I),
        re.compile(r'"status(?:Code)?"\s*:\s*(\d{3})', re.I),
    )
    for member in members:
        text = str(member.get("stdout") or "")
        for pat in patterns:
            hit = pat.search(text)
            if hit:
                code = hit.group(1)
                stats[code] = stats.get(code, 0) + 1
                break
    return dict(sorted(stats.items()))


def _make_group_run(members: List[Dict[str, Any]], *, host_key: str = "") -> Dict[str, Any]:
    first = members[0]
    tool = str(first.get("tool") or "unknown")
    target = _extract_target(first.get("params") or {})
    host = host_key or _probe_host_key(first)
    samples: List[str] = []
    for m in members[:12]:
        p = m.get("params") or {}
        samples.append(_run_subtitle(p, target) or str(p.get("command", ""))[:72])
    stdout_parts: List[str] = []
    findings: List[Dict[str, str]] = []
    for m in members:
        text = str(m.get("stdout") or "")
        if text.strip():
            stdout_parts.append(f"=== #{m.get('id')} ===\n{text[:900]}")
        findings.extend(_parse_severity_lines(text))
    combined = "\n\n".join(stdout_parts)[:16000]
    count = len(members)
    gid = f"{tool}_{host}_{first.get('id')}_{count}"
    label = f"HTTP 探测 ×{count}" if tool in NOISE_PROBE_TOOLS else f"{tool} ×{count}"
    status_stats = _probe_status_stats(members)
    subtitle = f"{host} · {count} 次"
    if status_stats:
        summary = " · ".join(f"{code}:{n}" for code, n in list(status_stats.items())[:4])
        subtitle = f"{subtitle} · {summary}"
    return {
        **first,
        "id": gid,
        "grouped": True,
        "group_count": count,
        "group_members": [m.get("id") for m in members],
        "group_samples": samples,
        "probe_host": host,
        "probe_status_stats": status_stats,
        "stdout": combined,
        "success": all(bool(m.get("success", True)) for m in members),
        "findings": findings[:24],
        "display_label": label,
        "subtitle": subtitle,
        "claude_tool": first.get("claude_tool", ""),
        "tool_kind": _claude_tool_kind(str(first.get("claude_tool") or ""), tool),
        "is_noise_probe": True,
    }


def _aggregate_probe_runs_session(runs: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
    """会话级：同 host 下全部无信号 curl/wget/httpx 合并为一个探测桶。"""
    buckets: Dict[str, List[Dict[str, Any]]] = {}
    merged = 0

    for run in runs:
        tool = str(run.get("tool") or "")
        if _is_noise_probe(tool) and not _run_has_signal(run):
            key = _probe_host_key(run)
            buckets.setdefault(key, []).append(run)

    bucket_runs: Dict[str, Dict[str, Any]] = {}
    for key, members in buckets.items():
        if len(members) == 1:
            bucket_runs[key] = members[0]
        else:
            merged += len(members) - 1
            bucket_runs[key] = _make_group_run(members, host_key=key)

    out: List[Dict[str, Any]] = []
    emitted: Set[str] = set()
    for run in runs:
        tool = str(run.get("tool") or "")
        if _is_noise_probe(tool) and not _run_has_signal(run):
            key = _probe_host_key(run)
            if key in emitted:
                continue
            emitted.add(key)
            out.append(bucket_runs[key])
        else:
            out.append(run)
    return out, merged


def build_graph_from_runs(
    runs: List[Dict[str, Any]],
    *,
    limit: int = 120,
    source: str = "hexstrike",
    claude_session_id: str = "",
    aggregate: bool = True,
) -> Dict[str, Any]:
    """按目标 + 攻击阶段构建攻击链节点/边。"""
    ordered = list(reversed(runs))  # oldest first
    merged_count = 0
    if aggregate:
        display_runs, merged_count = _aggregate_probe_runs_session(ordered)
    else:
        display_runs = ordered
    if limit and len(display_runs) > limit:
        display_runs = display_runs[-limit:]
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    node_ids: Dict[str, str] = {}
    last_by_target: Dict[str, str] = {}
    timeline: List[Dict[str, Any]] = []
    target_probe_totals: Dict[str, int] = {}
    seq = 0

    for i, run in enumerate(display_runs):
        tool = str(run.get("tool") or "unknown")
        params = run.get("params") or {}
        target = _extract_target(params)
        cat = _tool_category(tool)
        success = bool(run.get("success"))
        stdout = str(run.get("stdout") or "")
        findings = _parse_severity_lines(stdout)
        run_source = str(run.get("source") or source)
        run_id = run.get("id", i)

        claude_tool = str(run.get("claude_tool") or "")
        subtitle = _run_subtitle(params, target)
        grouped = bool(run.get("grouped"))
        is_noise = grouped or _is_noise_probe(tool)
        if grouped:
            probe_n = int(run.get("group_count") or 1)
            target_probe_totals[target] = target_probe_totals.get(target, 0) + probe_n
        if grouped:
            display_label = str(run.get("display_label") or f"{tool} ×{run.get('group_count', 1)}")
            subtitle = str(run.get("subtitle") or subtitle)
        elif run_source == "claude":
            display_label = _friendly_claude_tool_label(tool, claude_tool)
        else:
            display_label = tool
        tool_kind = _claude_tool_kind(claude_tool, tool) if run_source == "claude" else ""
        if grouped:
            tool_kind = str(run.get("tool_kind") or tool_kind)

        if target not in node_ids:
            tid = f"target_{len(node_ids)}"
            node_ids[target] = tid
            nodes.append(
                {
                    "id": tid,
                    "type": "target",
                    "phase": "target",
                    "phase_label": _phase_label("target"),
                    "phase_order": PHASE_ORDER["target"],
                    "label": target[:48],
                    "detail": target,
                    "status": "completed",
                }
            )
            last_by_target[target] = tid

        seq += 1
        if grouped:
            nid = f"group_{run.get('id')}"
        else:
            nid = f"run_{run_id}"
        status = "completed" if success else "failed"
        label = display_label
        detail_parts = [f"阶段: {_phase_label(cat)}", f"工具: {display_label}", f"目标: {target}"]
        if grouped:
            detail_parts.insert(1, f"合并 {run.get('group_count', 0)} 次 {tool} 探测")
            for idx, sample in enumerate((run.get("group_samples") or [])[:6], 1):
                detail_parts.append(f"  {idx}. {sample}")
        elif claude_tool and claude_tool != tool:
            detail_parts.insert(1, f"Claude 调用: {claude_tool}")
        if subtitle and subtitle != target:
            detail_parts.append(f"摘要: {subtitle}")
        if run.get("execution_time"):
            detail_parts.append(f"耗时: {run['execution_time']:.1f}s")
        if run.get("timestamp"):
            detail_parts.append(f"时间: {run['timestamp']}")
        if findings:
            detail_parts.append(f"发现 {len(findings)} 条线索")

        node = {
            "id": nid,
            "type": cat,
            "phase": cat,
            "phase_label": _phase_label(cat),
            "phase_order": PHASE_ORDER.get(cat, 9),
            "label": label,
            "display_label": display_label,
            "subtitle": subtitle,
            "claude_tool": claude_tool,
            "tool_kind": tool_kind,
            "grouped": grouped,
            "group_count": run.get("group_count") if grouped else None,
            "group_members": run.get("group_members") if grouped else None,
            "is_noise_probe": is_noise if not grouped else True,
            "probe_status_stats": run.get("probe_status_stats") if grouped else None,
            "detail": "\n".join(detail_parts),
            "tool": tool,
            "status": status,
            "findings": findings[:8],
            "success": success,
            "timestamp": run.get("timestamp", ""),
            "run_id": run_id,
            "source": run_source,
            "claude_session_id": run.get("claude_session_id") or claude_session_id,
            "tool_use_id": run.get("tool_use_id", ""),
            "sequence": run.get("sequence") or seq,
            "stdout_preview": stdout[:480],
            "has_stdout": bool(stdout.strip()),
        }
        nodes.append(node)

        timeline.append(
            {
                "node_id": nid,
                "run_id": run_id,
                "tool": display_label,
                "raw_tool": tool,
                "claude_tool": claude_tool,
                "tool_kind": tool_kind,
                "phase": cat,
                "phase_label": _phase_label(cat),
                "target": target,
                "subtitle": subtitle,
                "success": success,
                "timestamp": run.get("timestamp", ""),
                "sequence": node["sequence"],
                "stderr_preview": (stdout[:320] if not success else str(run.get("stderr") or "")[:320]),
                "grouped": grouped,
                "group_count": run.get("group_count") if grouped else None,
                "is_noise_probe": is_noise if not grouped else True,
            }
        )

        prev = last_by_target.get(target)
        if prev:
            edges.append({"from": prev, "to": nid, "label": _phase_label(cat)})
        last_by_target[target] = nid

    for node in nodes:
        if node.get("type") != "target":
            continue
        full_target = str(node.get("detail") or node.get("label") or "")
        total = target_probe_totals.get(full_target, 0)
        if total:
            node["probe_summary"] = f"HTTP 探测 {total} 次"
            node["subtitle"] = node["probe_summary"]

    return {
        "nodes": nodes,
        "edges": edges,
        "phases": PHASE_SWIMLANES,
        "timeline": timeline,
        "raw_step_count": len(ordered),
        "display_step_count": len([n for n in nodes if n.get("type") != "target"]),
        "merged_step_count": merged_count,
    }


def build_overview() -> Dict[str, Any]:
    active, completed, runs = _load_hexstrike_data()
    all_sessions = active + completed

    total_findings = sum(int(s.get("total_findings") or 0) for s in all_sessions)
    ok_runs = sum(1 for r in runs if r.get("success"))
    targets = set()
    for s in all_sessions:
        t = s.get("target")
        if t:
            targets.add(str(t))
    for r in runs:
        targets.add(_extract_target(r.get("params") or {}))

    severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
    recent_findings: List[Dict[str, str]] = []
    for run in runs[:30]:
        for f in _parse_severity_lines(str(run.get("stdout") or "")):
            sev = f.get("severity", "info")
            severity_counts[sev] = severity_counts.get(sev, 0) + 1
            if len(recent_findings) < 20:
                recent_findings.append({**f, "tool": run.get("tool", ""), "target": _extract_target(run.get("params") or {})})

    graph = build_graph_from_runs(runs, source="hexstrike")

    session_summaries = []
    for s in active:
        session_summaries.append(
            {
                "session_id": s.get("session_id", ""),
                "target": s.get("target", "unknown"),
                "status": s.get("status", "active"),
                "total_findings": s.get("total_findings", 0),
                "tools_executed": s.get("tools_executed", []),
                "active": True,
            }
        )
    for s in completed[:30]:
        session_summaries.append(
            {
                "session_id": s.get("session_id", ""),
                "target": s.get("target", "unknown"),
                "status": "completed",
                "total_findings": s.get("total_findings", 0),
                "tools_executed": s.get("tools_executed", []),
                "active": False,
            }
        )

    tool_stats: Dict[str, int] = {}
    for r in runs:
        t = str(r.get("tool") or "unknown")
        tool_stats[t] = tool_stats.get(t, 0) + 1
    top_tools = sorted(tool_stats.items(), key=lambda x: -x[1])[:12]

    chain = build_chain_bundle(runs)

    return {
        "stats": {
            "total_runs": len(runs),
            "success_runs": ok_runs,
            "success_rate": round(ok_runs / len(runs) * 100, 1) if runs else 0,
            "active_sessions": len(active),
            "completed_sessions": len(completed),
            "total_findings": total_findings,
            "unique_targets": len(targets),
            "severity": severity_counts,
            "risk_score": chain["risk"]["score"],
            "risk_level": chain["risk"]["level"],
        },
        "risk": chain["risk"],
        "facts": chain["facts"],
        "chain": chain,
        "graph": graph,
        "sessions": session_summaries,
        "recent_findings": recent_findings,
        "top_tools": [{"tool": t, "count": c} for t, c in top_tools],
        "timeline": graph.get("timeline") or [],
        "phases": graph.get("phases") or PHASE_SWIMLANES,
        "runs_preview": [
            {
                "id": r.get("id"),
                "tool": r.get("tool"),
                "target": _extract_target(r.get("params") or {}),
                "success": r.get("success"),
                "execution_time": r.get("execution_time"),
                "timestamp": r.get("timestamp"),
                "category": _tool_category(str(r.get("tool") or "")),
                "phase_label": _phase_label(_tool_category(str(r.get("tool") or ""))),
                "node_id": f"run_{r.get('id')}",
            }
            for r in runs[:40]
        ],
    }


def _default_claude_workdir() -> str:
    root = os.environ.get("TONGLING_ROOT") or os.path.dirname(os.path.dirname(__file__))
    return os.path.normpath(os.path.join(root, "storage", "node_ai", "claude-code"))


def _claude_sessions_meta(workdir: str) -> Dict[str, Any]:
    try:
        from cc_visual.claude_session import find_all_project_storages, read_storage_marker

        storages = find_all_project_storages(workdir)
        return {
            "workdir": workdir,
            "storage_dirs": [p.name for p in storages],
            "marker": read_storage_marker(workdir),
        }
    except Exception:
        return {"workdir": workdir, "storage_dirs": [], "marker": {}}


def _friendly_claude_tool_label(tool: str, claude_tool: str = "") -> str:
    """Claude MCP / Bash 工具名 → 图谱可读标签。"""
    raw = (claude_tool or tool or "unknown").strip()
    if raw.startswith("mcp__"):
        parts = raw.split("__")
        if len(parts) >= 3:
            return parts[-1].replace("_", " ")
        return _normalize_tool_name(raw)
    if "__" in raw:
        return raw.split("__")[-1].replace("_", " ")
    return str(tool or raw or "unknown")


def _run_subtitle(params: Dict[str, Any], target: str) -> str:
    """节点副标题：目标或 Bash 命令摘要。"""
    if target and target != "unknown":
        return target[:56]
    cmd = str((params or {}).get("command") or "").strip()
    if cmd:
        one = re.sub(r"\s+", " ", cmd)
        return one[:56] + ("…" if len(one) > 56 else "")
    for key in TARGET_KEYS:
        val = (params or {}).get(key)
        if val and str(val).strip():
            return str(val).strip()[:56]
    return ""


def _claude_tool_kind(claude_tool: str, tool: str) -> str:
    raw = (claude_tool or "").lower()
    if raw.startswith("mcp__"):
        return "mcp"
    if _normalize_tool_name(claude_tool or tool) == "bash":
        return "bash"
    return "tool"


def _normalize_tool_name(raw: str) -> str:
    name = (raw or "unknown").strip()
    if "__" in name:
        name = name.split("__")[-1]
    if "/" in name:
        name = name.split("/")[-1]
    return name.lower()


def _bash_scan_tool(command: str) -> Optional[str]:
    cmd = (command or "").lower()
    if not cmd.strip():
        return None
    for tool in sorted(ALL_SCAN_TOOLS, key=len, reverse=True):
        if re.search(rf"\b{re.escape(tool)}\b", cmd):
            return tool
    return None


def _is_scan_tool_use(raw_name: str, inp: Any) -> bool:
    norm = _normalize_tool_name(raw_name)
    if norm in ALL_SCAN_TOOLS:
        return True
    if norm == "bash":
        return _bash_scan_tool(str((inp or {}).get("command", ""))) is not None
    for tool in ALL_SCAN_TOOLS:
        if tool in norm:
            return True
    return False


def _resolve_scan_tool(raw_name: str, inp: Any) -> str:
    norm = _normalize_tool_name(raw_name)
    if norm == "bash" and isinstance(inp, dict):
        hit = _bash_scan_tool(str(inp.get("command", "")))
        if hit:
            return hit
    if norm in ALL_SCAN_TOOLS:
        return norm
    for tool in sorted(ALL_SCAN_TOOLS, key=len, reverse=True):
        if tool in norm:
            return tool
    return norm or raw_name or "unknown"


def _params_from_tool_input(raw_name: str, inp: Any) -> Dict[str, Any]:
    if not isinstance(inp, dict):
        return {}
    for key in TARGET_KEYS:
        val = inp.get(key)
        if val is not None and str(val).strip():
            return {key: str(val).strip()[:120]}
    if _normalize_tool_name(raw_name) == "bash":
        cmd = str(inp.get("command", ""))
        m = _URL_RE.search(cmd)
        if m:
            return {"url": m.group(0)[:120]}
        m = re.search(
            r"\b(?:curl|wget)(?:\.exe)?(?:\s+[-\w./:=@]+)*\s+(?:https?://)?([\w.-]+(?:\.[\w.-]+)+|\d{1,3}(?:\.\d{1,3}){3})",
            cmd,
            re.I,
        )
        if m:
            return {"host": m.group(1)[:120]}
        m = _IP_RE.search(cmd)
        if m:
            return {"target": m.group(0)}
        m = _DOMAIN_RE.search(cmd)
        if m:
            return {"domain": m.group(0)}
        return {"command": cmd[:120]}
    return {k: v for k, v in inp.items() if isinstance(v, (str, int, float, bool)) and str(v).strip()}


def _text_from_tool_result(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: List[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "\n".join(p for p in parts if p).strip()
    return ""


def _parse_jsonl_timestamp(obj: Dict[str, Any]) -> str:
    ts = obj.get("timestamp")
    if isinstance(ts, str):
        return ts
    if isinstance(ts, (int, float)):
        return str(ts)
    return ""


def extract_runs_from_claude_jsonl(
    jsonl_path: Path,
    *,
    limit: int = 200,
    claude_session_id: str = "",
) -> List[Dict[str, Any]]:
    """从 Claude Code 会话 jsonl 提取扫描相关 tool_use（MCP / Bash）。"""
    if not jsonl_path.is_file():
        return []

    runs: List[Dict[str, Any]] = []
    pending: Dict[str, Dict[str, Any]] = {}
    sequence = 0

    try:
        lines = jsonl_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return runs

    for line_no, line in enumerate(lines, 1):
        if len(runs) >= limit:
            break
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue

        ts = _parse_jsonl_timestamp(obj)
        typ = str(obj.get("type", ""))

        if typ == "assistant":
            msg = obj.get("message", {})
            content = msg.get("content", [])
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "tool_use":
                    continue
                raw_name = str(block.get("name", "tool"))
                inp = block.get("input", {})
                if not _is_scan_tool_use(raw_name, inp):
                    continue
                tool = _resolve_scan_tool(raw_name, inp)
                sequence += 1
                run: Dict[str, Any] = {
                    "id": len(runs) + 1,
                    "tool": tool,
                    "params": _params_from_tool_input(raw_name, inp),
                    "stdout": "",
                    "stderr": "",
                    "success": True,
                    "execution_time": 0.0,
                    "timestamp": ts,
                    "claude_tool": raw_name,
                    "tool_use_id": str(block.get("id", "")),
                    "sequence": sequence,
                    "jsonl_line": line_no,
                    "source": "claude",
                    "claude_session_id": claude_session_id,
                }
                use_id = str(block.get("id", ""))
                if use_id:
                    pending[use_id] = run
                runs.append(run)
            continue

        if typ == "user":
            msg = obj.get("message", {})
            content = msg.get("content", [])
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "tool_result":
                    continue
                use_id = str(block.get("tool_use_id", ""))
                if use_id not in pending:
                    continue
                text = _text_from_tool_result(block.get("content"))
                run = pending[use_id]
                run["stdout"] = text[:8000]
                lower = text.lower()
                run["success"] = not any(
                    k in lower[:400] for k in ("error:", "failed", "command not found", "permission denied")
                )

    return runs


def _stats_from_runs(runs: List[Dict[str, Any]]) -> Dict[str, Any]:
    ok = sum(1 for r in runs if r.get("success"))
    severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
    recent_findings: List[Dict[str, str]] = []
    targets = set()
    for run in runs:
        targets.add(_extract_target(run.get("params") or {}))
        for f in _parse_severity_lines(str(run.get("stdout") or "")):
            sev = f.get("severity", "info")
            severity_counts[sev] = severity_counts.get(sev, 0) + 1
            if len(recent_findings) < 20:
                recent_findings.append(
                    {
                        **f,
                        "tool": str(run.get("tool") or ""),
                        "target": _extract_target(run.get("params") or {}),
                    }
                )
    tool_stats: Dict[str, int] = {}
    for r in runs:
        t = str(r.get("tool") or "unknown")
        tool_stats[t] = tool_stats.get(t, 0) + 1
    top_tools = sorted(tool_stats.items(), key=lambda x: -x[1])[:12]
    return {
        "total_runs": len(runs),
        "success_runs": ok,
        "success_rate": round(ok / len(runs) * 100, 1) if runs else 0,
        "active_sessions": 0,
        "completed_sessions": 0,
        "total_findings": sum(severity_counts.values()),
        "unique_targets": len(targets),
        "severity": severity_counts,
        "recent_findings": recent_findings,
        "top_tools": [{"tool": t, "count": c} for t, c in top_tools],
    }


def list_claude_scan_sessions(workdir: str = "") -> List[Dict[str, Any]]:
    wd = workdir or _default_claude_workdir()
    try:
        from cc_visual.claude_session import list_sessions

        sessions = list_sessions(wd)
    except Exception:
        return []

    rows: List[Dict[str, Any]] = []
    for s in sessions:
        runs = extract_runs_from_claude_jsonl(s.path, claude_session_id=s.session_id)
        rows.append(
            {
                "session_id": s.session_id,
                "title": s.title,
                "first_prompt": (s.first_prompt or "")[:200],
                "modified_text": s.modified_text,
                "message_count": s.message_count,
                "tool_run_count": len(runs),
                "scan_tools": list(dict.fromkeys(str(r.get("tool", "")) for r in runs))[:10],
                "source": "claude",
            }
        )
    rows.sort(key=lambda r: (-int(r.get("tool_run_count") or 0), r.get("modified_text") or ""))
    return rows


def build_claude_session_view(
    session_id: str, workdir: str = "", *, aggregate: bool = True
) -> Optional[Dict[str, Any]]:
    wd = workdir or _default_claude_workdir()
    try:
        from cc_visual.claude_session import list_sessions

        sessions = list_sessions(wd)
    except Exception:
        return None

    target = next((s for s in sessions if s.session_id == session_id), None)
    if not target:
        return None

    runs = extract_runs_from_claude_jsonl(target.path, claude_session_id=target.session_id)
    stats_bundle = _stats_from_runs(runs)
    graph = (
        build_graph_from_runs(
            list(reversed(runs)),
            source="claude",
            claude_session_id=target.session_id,
            aggregate=aggregate,
        )
        if runs
        else {
            "nodes": [],
            "edges": [],
            "phases": PHASE_SWIMLANES,
            "timeline": [],
            "raw_step_count": 0,
            "display_step_count": 0,
            "merged_step_count": 0,
        }
    )

    tagged_runs = [{**r, "claude_session_id": target.session_id} for r in runs]
    chain = build_chain_bundle(
        tagged_runs,
        session_id=target.session_id,
        session_title=target.title or "",
    )
    hosts = [t["host"] for t in (chain.get("facts") or {}).get("targets") or [] if t.get("host")]
    cross = enrich_claude_cross_session_facts(wd, target.session_id, hosts)

    return {
        "source": "claude",
        "claude_session_id": target.session_id,
        "workdir": wd,
        "session": {
            "session_id": target.session_id,
            "title": target.title,
            "first_prompt": target.first_prompt,
            "modified_text": target.modified_text,
            "message_count": target.message_count,
            "tool_run_count": len(runs),
            "scan_tools": list(dict.fromkeys(str(r.get("tool", "")) for r in runs)),
        },
        "stats": {
            **{k: v for k, v in stats_bundle.items() if k not in ("recent_findings", "top_tools")},
            "risk_score": chain["risk"]["score"],
            "risk_level": chain["risk"]["level"],
        },
        "risk": chain["risk"],
        "facts": chain["facts"],
        "chain": {**chain, "cross_session": cross},
        "graph": graph,
        "recent_findings": stats_bundle["recent_findings"],
        "top_tools": stats_bundle["top_tools"],
        "timeline": graph.get("timeline") or [],
        "phases": graph.get("phases") or PHASE_SWIMLANES,
        "graph_meta": {
            "raw_step_count": graph.get("raw_step_count", len(runs)),
            "display_step_count": graph.get("display_step_count", 0),
            "merged_step_count": graph.get("merged_step_count", 0),
            "aggregate": aggregate,
        },
        "runs_preview": [
            {
                "id": r.get("id"),
                "tool": r.get("tool"),
                "target": _extract_target(r.get("params") or {}),
                "success": r.get("success"),
                "execution_time": r.get("execution_time"),
                "timestamp": r.get("timestamp"),
                "category": _tool_category(str(r.get("tool") or "")),
                "phase_label": _phase_label(_tool_category(str(r.get("tool") or ""))),
                "claude_tool": r.get("claude_tool"),
                "node_id": f"run_{r.get('id')}",
                "sequence": r.get("sequence"),
            }
            for r in runs[:40]
        ],
    }


def runs_for_hexstrike_session(session: Dict[str, Any]) -> List[Dict[str, Any]]:
    """将会话关联到 run_history 中的真实执行记录。"""
    target = str(session.get("target") or "").strip()
    matched: List[Dict[str, Any]] = []
    try:
        from server_core.singletons import run_history

        for run in run_history.get_all():
            rt = _extract_target(run.get("params") or {})
            if target and rt != target and target not in rt and rt not in target:
                continue
            matched.append({**run, "source": "hexstrike"})
    except Exception:
        pass

    if matched:
        return matched

    runs: List[Dict[str, Any]] = []
    for i, tool in enumerate(session.get("tools_executed") or []):
        runs.append(
            {
                "id": f"{session.get('session_id', 's')}_{i}",
                "tool": str(tool),
                "params": {"target": target or "unknown"},
                "success": True,
                "stdout": "",
                "stderr": "",
                "execution_time": 0,
                "timestamp": session.get("updated_at") or session.get("created_at") or "",
                "source": "hexstrike",
            }
        )
    return runs


# ── 攻击链增强：风险评分 + 跨会话事实 ──────────────────────────────

_SEV_WEIGHT = {"critical": 40, "high": 20, "medium": 8, "low": 3, "info": 1}
_PORT_RE = re.compile(
    r"(?:^|\s)(\d{1,5})/tcp\s+open|port[=:\s]+(\d{1,5})\b|Listening on.*?(\d{1,5})\b",
    re.I,
)


def _normalize_host_key(raw: str) -> str:
    text = (raw or "").strip()
    if not text or text == "unknown":
        return ""
    try:
        if "://" in text:
            host = urlparse(text).netloc or urlparse(text).path
            host = host.split("@")[-1].split(":")[0].strip().lower()
            return host[:120]
    except Exception:
        pass
    m = _IP_RE.search(text) if "_IP_RE" in globals() else re.search(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", text)
    if m:
        return m.group(0)
    host = text.split("/")[0].split(":")[0].strip().lower()
    return host[:120] if host else ""

def _extract_ports_from_text(text: str) -> List[int]:
    ports: List[int] = []
    for m in _PORT_RE.finditer(text or ""):
        for g in m.groups():
            if not g:
                continue
            try:
                p = int(g)
            except ValueError:
                continue
            if 1 <= p <= 65535 and p not in ports:
                ports.append(p)
            if len(ports) >= 40:
                return ports
    return ports


def compute_risk_score(severity: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
    sev = {
        "critical": int((severity or {}).get("critical") or 0),
        "high": int((severity or {}).get("high") or 0),
        "medium": int((severity or {}).get("medium") or 0),
        "low": int((severity or {}).get("low") or 0),
        "info": int((severity or {}).get("info") or 0),
    }
    raw = sum(_SEV_WEIGHT[k] * sev[k] for k in _SEV_WEIGHT)
    # Soft-cap: first hits weigh more; dampen huge counts
    score = int(min(100, round(100 * (1 - pow(2.718281828, -raw / 55.0)))))
    if sev["critical"] >= 1:
        level, label = "critical", "严重"
    elif score >= 70 or sev["high"] >= 2:
        level, label = "high", "高风险"
    elif score >= 40 or sev["high"] >= 1 or sev["medium"] >= 3:
        level, label = "medium", "中风险"
    elif score >= 15 or sum(sev.values()) >= 1:
        level, label = "low", "低风险"
    else:
        level, label = "none", "暂无线索"

    drivers: List[str] = []
    for k, zh in (("critical", "Critical"), ("high", "High"), ("medium", "Medium"), ("low", "Low")):
        if sev[k]:
            drivers.append(f"{sev[k]} × {zh}")
    if not drivers:
        drivers.append("未解析到明确严重度线索")

    return {
        "score": score,
        "level": level,
        "label": label,
        "severity": sev,
        "drivers": drivers[:6],
        "raw_weight": raw,
    }


def build_chain_bundle(
    runs: List[Dict[str, Any]],
    *,
    session_id: str = "",
    session_title: str = "",
) -> Dict[str, Any]:
    """从 runs 聚合攻击链事实 + 风险评分。"""
    host_map: Dict[str, Dict[str, Any]] = {}
    vuln_list: List[Dict[str, Any]] = []
    tools_global: Dict[str, int] = {}
    severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}

    for run in runs or []:
        tool = str(run.get("tool") or "unknown")
        tools_global[tool] = tools_global.get(tool, 0) + 1
        params = run.get("params") or {}
        target = _extract_target(params)
        host = _normalize_host_key(target) or _normalize_host_key(str(params.get("url") or ""))
        if not host:
            host = _probe_host_key(run) if not _is_noise_probe(tool) else _probe_host_key(run)
        if not host or host == "_unknown":
            host = "unknown"

        bucket = host_map.setdefault(
            host,
            {
                "host": host,
                "targets": set(),
                "ports": set(),
                "tools": set(),
                "findings": 0,
                "severity": {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0},
                "sessions": set(),
                "run_count": 0,
            },
        )
        bucket["run_count"] += 1
        if target and target != "unknown":
            bucket["targets"].add(str(target)[:160])
        bucket["tools"].add(tool)
        sid = str(run.get("claude_session_id") or session_id or "").strip()
        if sid:
            bucket["sessions"].add(sid)

        stdout = str(run.get("stdout") or "")
        for p in _extract_ports_from_text(stdout):
            bucket["ports"].add(p)
        # also from params
        for key in ("port", "ports"):
            val = params.get(key)
            if isinstance(val, int) and 1 <= val <= 65535:
                bucket["ports"].add(val)
            elif isinstance(val, str) and val.isdigit():
                bucket["ports"].add(int(val))

        for f in run.get("findings") or _parse_severity_lines(stdout):
            sev = str(f.get("severity") or "info").lower()
            if sev not in severity_counts:
                sev = "info"
            severity_counts[sev] += 1
            bucket["severity"][sev] = bucket["severity"].get(sev, 0) + 1
            bucket["findings"] += 1
            if len(vuln_list) < 30:
                vuln_list.append(
                    {
                        "severity": sev,
                        "text": str(f.get("text") or "")[:200],
                        "cve": str(f.get("cve") or ""),
                        "tool": tool,
                        "host": host,
                        "target": target,
                        "session_id": sid,
                    }
                )

    targets_out: List[Dict[str, Any]] = []
    for host, b in host_map.items():
        if host == "unknown" and b["run_count"] <= 0:
            continue
        host_risk = compute_risk_score(b["severity"])
        targets_out.append(
            {
                "host": host,
                "targets": sorted(b["targets"])[:8],
                "ports": sorted(b["ports"])[:24],
                "tools": sorted(b["tools"])[:12],
                "findings": b["findings"],
                "run_count": b["run_count"],
                "severity": b["severity"],
                "risk_score": host_risk["score"],
                "risk_level": host_risk["level"],
                "sessions": sorted(b["sessions"])[:12],
                "session_count": len(b["sessions"]),
            }
        )
    targets_out.sort(key=lambda x: (-int(x["risk_score"]), -int(x["findings"]), x["host"]))

    ports_flat = sorted({p for t in targets_out for p in (t.get("ports") or [])})[:40]
    risk = compute_risk_score(severity_counts)
    return {
        "risk": risk,
        "facts": {
            "target_count": len([t for t in targets_out if t["host"] != "unknown"]),
            "port_count": len(ports_flat),
            "finding_count": sum(severity_counts.values()),
            "tool_count": len(tools_global),
            "targets": targets_out[:20],
            "ports": ports_flat,
            "vulns": vuln_list[:20],
            "top_tools": [
                {"tool": t, "count": c}
                for t, c in sorted(tools_global.items(), key=lambda x: -x[1])[:10]
            ],
            "session_title": session_title,
            "session_id": session_id,
        },
    }


def enrich_claude_cross_session_facts(
    workdir: str,
    current_session_id: str,
    current_hosts: List[str],
) -> Dict[str, Any]:
    """按目标 host 关联其他 Claude 会话（跨会话事实）。"""
    hosts = {h for h in (current_hosts or []) if h and h != "unknown"}
    if not hosts:
        return {"related_sessions": [], "merged_hosts": []}

    related: List[Dict[str, Any]] = []
    merged_runs: List[Dict[str, Any]] = []
    try:
        from cc_visual.claude_session import list_sessions

        sessions = list_sessions(workdir or _default_claude_workdir())
    except Exception:
        return {"related_sessions": [], "merged_hosts": sorted(hosts)}

    for s in sessions:
        if s.session_id == current_session_id:
            continue
        runs = extract_runs_from_claude_jsonl(s.path, claude_session_id=s.session_id)
        if not runs:
            continue
        # tag session id on runs
        tagged = []
        hit_hosts = set()
        for r in runs:
            rr = {**r, "claude_session_id": s.session_id}
            tagged.append(rr)
            h = _normalize_host_key(_extract_target(r.get("params") or {})) or _probe_host_key(r)
            if h and h in hosts:
                hit_hosts.add(h)
        if not hit_hosts:
            continue
        related.append(
            {
                "session_id": s.session_id,
                "title": s.title,
                "modified_text": s.modified_text,
                "tool_run_count": len(runs),
                "shared_hosts": sorted(hit_hosts),
            }
        )
        merged_runs.extend(tagged)

    related.sort(key=lambda x: -int(x.get("tool_run_count") or 0))
    merged_bundle = build_chain_bundle(merged_runs) if merged_runs else None
    return {
        "related_sessions": related[:12],
        "merged_hosts": sorted(hosts),
        "related_risk": (merged_bundle or {}).get("risk"),
        "related_facts": (merged_bundle or {}).get("facts"),
        "related_run_count": len(merged_runs),
    }
