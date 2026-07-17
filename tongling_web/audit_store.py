"""操作审计落盘 — storage/audit/<audit_id>/"""

from __future__ import annotations

import json
import logging
import os
import secrets
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_INDEX_NAME = "index.json"
_MAX_INDEX = 300
_lock = threading.Lock()


def _tongling_root() -> str:
    return os.environ.get("TONGLING_ROOT") or os.path.dirname(os.path.dirname(__file__))


def audit_root() -> str:
    return os.path.join(_tongling_root(), "storage", "audit")


def _task_dir(audit_id: str) -> str:
    safe = "".join(c for c in audit_id if c.isalnum() or c in ("_", "-"))
    return os.path.join(audit_root(), safe)


def _read_json(path: str, default: Any) -> Any:
    if not os.path.isfile(path):
        return default
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def _write_json(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _load_index() -> List[Dict[str, Any]]:
    return list(_read_json(os.path.join(audit_root(), _INDEX_NAME), []) or [])


def _save_index(entries: List[Dict[str, Any]]) -> None:
    os.makedirs(audit_root(), exist_ok=True)
    trimmed = entries[:_MAX_INDEX]
    _write_json(os.path.join(audit_root(), _INDEX_NAME), trimmed)


def _upsert_index(summary: Dict[str, Any]) -> None:
    with _lock:
        entries = _load_index()
        aid = summary.get("audit_id")
        entries = [e for e in entries if e.get("audit_id") != aid]
        entries.insert(0, summary)
        _save_index(entries)


def _append_event(audit_id: str, event_type: str, data: Optional[Dict[str, Any]] = None) -> None:
    path = os.path.join(_task_dir(audit_id), "events.jsonl")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    line = {
        "ts": time.time(),
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "type": event_type,
        "data": data or {},
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")


def _new_audit_id(terminal_session_id: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = (terminal_session_id or "t0").replace(" ", "")
    tail = secrets.token_hex(2)
    return f"{stamp}_{suffix}_{tail}"


def begin_task(
    *,
    terminal_session_id: str,
    title: str = "",
    workdir: str = "",
    cmdline: str = "",
    extra: Optional[Dict[str, Any]] = None,
) -> str:
    """新建审计任务（Web 终端 start 时调用）。"""
    audit_id = _new_audit_id(terminal_session_id)
    tdir = _task_dir(audit_id)
    os.makedirs(tdir, exist_ok=True)

    meta = {
        "audit_id": audit_id,
        "title": title or f"终端 {terminal_session_id}",
        "terminal_session_id": terminal_session_id,
        "workdir": workdir or "",
        "cmdline": cmdline or "",
        "started_at": time.time(),
        "started_at_text": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "ended_at": None,
        "ended_at_text": "",
        "status": "running",
        "exit_code": None,
        "tool_run_count": 0,
        "terminal_bytes": 0,
        "extra": extra or {},
    }
    _write_json(os.path.join(tdir, "meta.json"), meta)
    open(os.path.join(tdir, "terminal.log"), "w", encoding="utf-8").close()
    _write_json(os.path.join(tdir, "tools.json"), {"runs": [], "synced_at": None})

    _append_event(
        audit_id,
        "task_start",
        {
            "terminal_session_id": terminal_session_id,
            "workdir": workdir,
            "cmdline": cmdline,
        },
    )

    _upsert_index(
        {
            "audit_id": audit_id,
            "title": meta["title"],
            "terminal_session_id": terminal_session_id,
            "workdir": workdir,
            "started_at": meta["started_at"],
            "started_at_text": meta["started_at_text"],
            "ended_at": None,
            "status": "running",
            "tool_run_count": 0,
        }
    )
    logger.info("审计任务已开始: %s (%s)", audit_id, terminal_session_id)
    return audit_id


def append_terminal(audit_id: str, text: str) -> None:
    if not audit_id or not text:
        return
    tdir = _task_dir(audit_id)
    if not os.path.isdir(tdir):
        return
    log_path = os.path.join(tdir, "terminal.log")
    try:
        with open(log_path, "a", encoding="utf-8", errors="replace") as f:
            f.write(text)
        meta_path = os.path.join(tdir, "meta.json")
        meta = _read_json(meta_path, {})
        if isinstance(meta, dict):
            meta["terminal_bytes"] = int(meta.get("terminal_bytes") or 0) + len(text.encode("utf-8", errors="replace"))
            _write_json(meta_path, meta)
    except OSError as exc:
        logger.debug("append_terminal failed: %s", exc)


def sync_hexstrike_runs(
    audit_id: str,
    base_url: str,
    headers: Optional[Dict[str, str]] = None,
    *,
    limit: int = 500,
) -> int:
    """从 HexStrike /api/runs/history 拉取工具执行记录并合并到审计目录。"""
    import urllib.error
    import urllib.request

    tdir = _task_dir(audit_id)
    meta_path = os.path.join(tdir, "meta.json")
    if not os.path.isfile(meta_path):
        return 0

    meta = _read_json(meta_path, {})
    if not isinstance(meta, dict):
        return 0

    started_at = float(meta.get("started_at") or 0)
    tools_path = os.path.join(tdir, "tools.json")
    store = _read_json(tools_path, {"runs": []})
    if not isinstance(store, dict):
        store = {"runs": []}
    existing = store.get("runs") or []
    known_ids = {r.get("id") for r in existing if isinstance(r, dict)}

    url = f"{base_url.rstrip('/')}/api/runs/history?limit={int(limit)}"
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError) as exc:
        logger.warning("审计同步 HexStrike runs 失败 %s: %s", audit_id, exc)
        _append_event(audit_id, "sync_error", {"error": str(exc)[:300]})
        return 0

    runs = payload.get("runs") if isinstance(payload, dict) else []
    if not isinstance(runs, list):
        runs = []

    new_count = 0
    for run in runs:
        if not isinstance(run, dict):
            continue
        rid = run.get("id")
        if rid in known_ids:
            continue
        ts_text = str(run.get("timestamp") or "")
        run_ts = _parse_run_ts(ts_text) if ts_text else started_at
        if started_at and run_ts and run_ts + 120 < started_at:
            continue
        existing.append(run)
        known_ids.add(rid)
        new_count += 1
        _append_event(
            audit_id,
            "tool_run",
            {
                "id": rid,
                "tool": run.get("tool"),
                "endpoint": run.get("endpoint"),
                "success": run.get("success"),
                "return_code": run.get("return_code"),
            },
        )

    store["runs"] = existing
    store["synced_at"] = time.time()
    store["synced_at_text"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _write_json(tools_path, store)

    meta["tool_run_count"] = len(existing)
    _write_json(meta_path, meta)
    if new_count:
        logger.info("审计 %s 同步 %d 条新工具记录", audit_id, new_count)
    return new_count


def _parse_run_ts(text: str) -> float:
    text = (text or "").strip()
    if not text:
        return 0.0
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(text.replace("Z", "")[:19], fmt.replace("Z", "")).timestamp()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def generate_report(audit_id: str) -> str:
    tdir = _task_dir(audit_id)
    meta = _read_json(os.path.join(tdir, "meta.json"), {})
    tools = _read_json(os.path.join(tdir, "tools.json"), {"runs": []})
    events = load_events(audit_id, limit=500)

    if not isinstance(meta, dict):
        meta = {}
    runs = tools.get("runs") if isinstance(tools, dict) else []

    lines = [
        f"# 统领 AI 渗透审计报告",
        "",
        f"- **任务 ID**: `{audit_id}`",
        f"- **标题**: {meta.get('title', '')}",
        f"- **状态**: {meta.get('status', '')}",
        f"- **开始**: {meta.get('started_at_text', '')}",
        f"- **结束**: {meta.get('ended_at_text', '') or '—'}",
        f"- **工作目录**: `{meta.get('workdir', '')}`",
        f"- **终端会话**: `{meta.get('terminal_session_id', '')}`",
        f"- **终端输出**: {int(meta.get('terminal_bytes') or 0)} 字节 → `terminal.log`",
        f"- **MCP/工具执行**: {len(runs)} 条",
    ]
    extra = meta.get("extra") if isinstance(meta.get("extra"), dict) else {}
    if extra.get("target"):
        lines.append(f"- **扫描目标**: `{extra.get('target')}`")
    if extra.get("report_path"):
        lines.append(f"- **Claude 报告路径**: `{extra.get('report_path')}`")

    lines.extend(["", "## 工具 / MCP 执行摘要", ""])

    if not runs:
        lines.append("_（会话期间未同步到 HexStrike 工具记录，或服务未启动 MCP 调用）_")
    else:
        lines.append("| # | 工具 | 成功 | 返回码 | 时间 |")
        lines.append("|---|------|------|--------|------|")
        for i, run in enumerate(runs[:80], 1):
            if not isinstance(run, dict):
                continue
            lines.append(
                f"| {i} | `{run.get('tool', '')}` | {run.get('success')} | "
                f"{run.get('return_code', '')} | {run.get('timestamp', '')} |"
            )
        if len(runs) > 80:
            lines.append(f"\n_… 另有 {len(runs) - 80} 条，见 tools.json_")

    lines.extend(["", "## 事件时间线", ""])
    if not events:
        lines.append("_无事件_")
    else:
        for ev in events[-60:]:
            lines.append(
                f"- `{ev.get('time', '')}` **{ev.get('type', '')}** "
                + json.dumps(ev.get("data") or {}, ensure_ascii=False)[:200]
            )

    lines.extend(
        [
            "",
            "## 文件",
            "",
            f"- 目录: `storage/audit/{audit_id}/`",
            "- `meta.json` — 元数据",
            "- `events.jsonl` — 事件流",
            "- `terminal.log` — Web 终端完整输出",
            "- `tools.json` — HexStrike 工具执行",
            "",
            f"_报告生成于 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}_",
        ]
    )

    report = "\n".join(lines) + "\n"
    report_path = os.path.join(tdir, "report.md")
    try:
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report)
    except OSError:
        pass
    return report


def finalize_task(
    audit_id: str,
    *,
    exit_code: Optional[int] = None,
    status: str = "completed",
    sync_hexstrike: bool = True,
    server_url: str = "",
    auth_headers: Optional[Dict[str, str]] = None,
) -> None:
    tdir = _task_dir(audit_id)
    meta_path = os.path.join(tdir, "meta.json")
    if not os.path.isfile(meta_path):
        return

    meta = _read_json(meta_path, {})
    if not isinstance(meta, dict):
        return

    if sync_hexstrike and server_url:
        sync_hexstrike_runs(audit_id, server_url, auth_headers)

    meta["ended_at"] = time.time()
    meta["ended_at_text"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    meta["status"] = status
    meta["exit_code"] = exit_code
    tools = _read_json(os.path.join(tdir, "tools.json"), {"runs": []})
    if isinstance(tools, dict):
        meta["tool_run_count"] = len(tools.get("runs") or [])

    _write_json(meta_path, meta)
    _append_event(audit_id, "task_end", {"exit_code": exit_code, "status": status})
    generate_report(audit_id)

    _upsert_index(
        {
            "audit_id": audit_id,
            "title": meta.get("title", ""),
            "terminal_session_id": meta.get("terminal_session_id", ""),
            "workdir": meta.get("workdir", ""),
            "started_at": meta.get("started_at"),
            "started_at_text": meta.get("started_at_text", ""),
            "ended_at": meta.get("ended_at"),
            "ended_at_text": meta.get("ended_at_text", ""),
            "status": status,
            "tool_run_count": meta.get("tool_run_count", 0),
        }
    )
    logger.info("审计任务已结束: %s status=%s", audit_id, status)


def list_tasks(limit: int = 50) -> List[Dict[str, Any]]:
    entries = _load_index()
    return entries[: max(1, min(limit, _MAX_INDEX))]


def delete_task(audit_id: str) -> Tuple[bool, str]:
    """删除单条审计记录（目录 + 索引）。"""
    import shutil

    safe = "".join(c for c in (audit_id or "") if c.isalnum() or c in ("_", "-"))
    if not safe or safe != (audit_id or "").strip():
        return False, "无效的审计 ID"
    tdir = _task_dir(safe)
    with _lock:
        entries = _load_index()
        entries = [e for e in entries if e.get("audit_id") != safe]
        _save_index(entries)
    if os.path.isdir(tdir):
        try:
            shutil.rmtree(tdir, ignore_errors=True)
        except OSError as exc:
            return False, f"删除目录失败: {exc}"
    elif not any(e.get("audit_id") == safe for e in _load_index()):
        # 目录已不在且索引已清理
        pass
    return True, "已删除"


def clear_tasks() -> Tuple[bool, str, int]:
    """清空全部操作审计。"""
    entries = _load_index()
    if not entries:
        return True, "暂无审计记录", 0
    deleted = 0
    for e in list(entries):
        aid = str(e.get("audit_id") or "")
        if not aid:
            continue
        ok, _ = delete_task(aid)
        if ok:
            deleted += 1
    return True, f"已删除 {deleted} 条审计记录", deleted


def get_task(audit_id: str) -> Optional[Dict[str, Any]]:
    tdir = _task_dir(audit_id)
    meta_path = os.path.join(tdir, "meta.json")
    if not os.path.isfile(meta_path):
        return None
    meta = _read_json(meta_path, {})
    tools = _read_json(os.path.join(tdir, "tools.json"), {"runs": []})
    if not isinstance(meta, dict):
        return None
    return {
        **meta,
        "tools": tools.get("runs") if isinstance(tools, dict) else [],
        "events_count": len(load_events(audit_id, limit=10000)),
        "has_terminal_log": os.path.isfile(os.path.join(tdir, "terminal.log")),
        "has_report": os.path.isfile(os.path.join(tdir, "report.md")),
    }


def load_events(audit_id: str, limit: int = 200) -> List[Dict[str, Any]]:
    path = os.path.join(_task_dir(audit_id), "events.jsonl")
    if not os.path.isfile(path):
        return []
    out: List[Dict[str, Any]] = []
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    if limit and len(out) > limit:
        return out[-limit:]
    return out


def read_terminal_tail(audit_id: str, max_chars: int = 12000) -> str:
    path = os.path.join(_task_dir(audit_id), "terminal.log")
    if not os.path.isfile(path):
        return ""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            data = f.read()
        if len(data) <= max_chars:
            return data
        return "…(截断)\n" + data[-max_chars:]
    except OSError:
        return ""


def read_report(audit_id: str) -> str:
    path = os.path.join(_task_dir(audit_id), "report.md")
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as f:
                return f.read()
        except OSError:
            pass
    return generate_report(audit_id)
