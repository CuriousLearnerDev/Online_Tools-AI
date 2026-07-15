#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""读取 Claude Code 本地会话 / 执行记录（~/.claude/projects/*.jsonl）。"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def claude_home() -> Path:
    custom = os.environ.get("CLAUDE_CONFIG_DIR", "").strip()
    if custom:
        return Path(custom)
    return Path(os.environ.get("USERPROFILE", os.path.expanduser("~"))) / ".claude"


def encode_project_path(path: str) -> str:
    """Claude Code 项目目录编码规则：非字母数字替换为 -。"""
    norm = os.path.normpath(os.path.abspath(path))
    return re.sub(r"[^a-zA-Z0-9]", "-", norm)


def _path_needs_subst(work_dir: str) -> bool:
    """Web 终端对中文路径会用 subst Z:，会话落在 projects/Z--。"""
    if os.name != "nt":
        return False
    try:
        os.path.normpath(os.path.abspath(work_dir)).encode("ascii")
        return False
    except UnicodeEncodeError:
        return True


def _storage_marker_path(work_dir: str) -> Path:
    return Path(os.path.normpath(os.path.abspath(work_dir))) / ".tongling" / "claude_storage.json"


def read_storage_marker(work_dir: str) -> Dict[str, Any]:
    path = _storage_marker_path(work_dir)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def write_storage_marker(work_dir: str, *, subst: bool = False) -> None:
    """记录 Claude 项目目录映射，供 Web 控制面板 / 扫描图谱读取会话。"""
    real = os.path.normpath(os.path.abspath(work_dir))
    aux = Path(real) / ".tongling"
    try:
        aux.mkdir(parents=True, exist_ok=True)
        payload = {
            "real_cwd": real,
            "encoded": encode_project_path(real),
            "subst": bool(subst),
        }
        (_storage_marker_path(real)).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        pass


def find_project_storage(work_dir: str) -> Optional[Path]:
    """定位 ~/.claude/projects/<encoded-path>（单目录，兼容旧调用）。"""
    storages = find_all_project_storages(work_dir)
    return storages[0] if storages else None


def find_all_project_storages(work_dir: str) -> List[Path]:
    """定位所有可能存放该工作目录 Claude 会话的 projects 子目录。"""
    projects = claude_home() / "projects"
    if not projects.is_dir():
        return []

    norm = os.path.normpath(os.path.abspath(work_dir))
    encoded = encode_project_path(norm)
    marker = read_storage_marker(norm)

    candidates: List[Tuple[int, Path]] = []

    def score(path: Path, rank: int) -> None:
        if path.is_dir():
            candidates.append((rank, path))

    score(projects / encoded, 100)
    if marker.get("encoded"):
        score(projects / str(marker["encoded"]), 95)

    use_subst = bool(marker.get("subst")) or _path_needs_subst(norm)
    if use_subst:
        score(projects / "Z--", 90)

    enc_lower = encoded.lower()
    for d in projects.iterdir():
        if not d.is_dir():
            continue
        name = d.name
        if name in (encoded, "Z--"):
            continue
        nl = name.lower()
        if nl == enc_lower:
            score(d, 85)
        elif enc_lower in nl or nl in enc_lower:
            score(d, 60)

    if not candidates:
        return []

    seen: Dict[str, Path] = {}
    for _, p in sorted(candidates, key=lambda x: (-x[0], -len(list(x[1].glob("*.jsonl"))))):
        seen[str(p)] = p
    ordered = list(seen.values())
    ordered.sort(key=lambda p: len(list(p.glob("*.jsonl"))), reverse=True)
    return ordered


@dataclass
class SessionInfo:
    session_id: str
    path: Path
    first_prompt: str = ""
    summary: str = ""
    message_count: int = 0
    modified: Optional[datetime] = None
    git_branch: str = ""

    @property
    def title(self) -> str:
        text = (self.first_prompt or self.summary or self.session_id[:8]).strip()
        return text.replace("\n", " ")[:120]

    @property
    def modified_text(self) -> str:
        if not self.modified:
            return ""
        return self.modified.strftime("%Y-%m-%d %H:%M")


@dataclass
class ActivityEvent:
    kind: str  # user | assistant | tool | error | system | file | other
    title: str
    detail: str = ""
    timestamp: Optional[datetime] = None
    tool_name: str = ""
    session_id: str = ""
    raw_type: str = ""


def _parse_ts(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value / 1000 if value > 1e12 else value)
        except (OSError, ValueError):
            return None
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            return None
    return None


def _text_from_content(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: List[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(str(block.get("text", "")))
                elif block.get("type") == "tool_result":
                    parts.append(str(block.get("content", "")))
        return "\n".join(p for p in parts if p).strip()
    return ""


def _first_user_prompt(jsonl_path: Path) -> str:
    try:
        for line in jsonl_path.read_text(encoding="utf-8", errors="replace").splitlines():
            obj = json.loads(line)
            if obj.get("type") != "user":
                continue
            msg = obj.get("message", {})
            text = _text_from_content(msg.get("content"))
            if text and not text.startswith("<"):
                return text[:200]
    except Exception:
        pass
    return ""


def list_sessions(work_dir: str) -> List[SessionInfo]:
    storages = find_all_project_storages(work_dir)
    if not storages:
        return []

    by_id: Dict[str, SessionInfo] = {}

    for storage in storages:
        index_path = storage / "sessions-index.json"
        indexed: Dict[str, dict] = {}
        if index_path.is_file():
            try:
                data = json.loads(index_path.read_text(encoding="utf-8"))
                entries = data.get("entries", data) if isinstance(data, dict) else data
                if isinstance(entries, list):
                    for e in entries:
                        sid = str(e.get("sessionId", ""))
                        if sid:
                            indexed[sid] = e
            except Exception:
                pass

        for fp in storage.glob("*.jsonl"):
            if fp.name.startswith("agent-"):
                continue
            sid = fp.stem
            meta = indexed.get(sid, {})
            modified = _parse_ts(meta.get("modified")) or datetime.fromtimestamp(fp.stat().st_mtime)
            info = SessionInfo(
                session_id=sid,
                path=fp,
                first_prompt=str(meta.get("firstPrompt") or _first_user_prompt(fp)),
                summary=str(meta.get("summary") or ""),
                message_count=int(meta.get("messageCount") or 0),
                modified=modified,
                git_branch=str(meta.get("gitBranch") or ""),
            )
            prev = by_id.get(sid)
            if not prev or (info.modified or datetime.min) >= (prev.modified or datetime.min):
                by_id[sid] = info

    sessions = list(by_id.values())
    sessions.sort(key=lambda s: s.modified or datetime.min, reverse=True)
    return sessions


def parse_session_activities(jsonl_path: Path, max_events: int = 500) -> List[ActivityEvent]:
    events: List[ActivityEvent] = []
    if not jsonl_path.is_file():
        return events

    try:
        lines = jsonl_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return events

    for line in lines:
        if len(events) >= max_events:
            break
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue

        ts = _parse_ts(obj.get("timestamp"))
        session_id = str(obj.get("sessionId", ""))
        typ = str(obj.get("type", ""))

        if typ == "user":
            msg = obj.get("message", {})
            text = _text_from_content(msg.get("content"))
            if not text or text.startswith("<"):
                continue
            events.append(
                ActivityEvent(
                    kind="user",
                    title=text[:160],
                    detail=text,
                    timestamp=ts,
                    session_id=session_id,
                    raw_type=typ,
                )
            )
            continue

        if typ == "assistant":
            msg = obj.get("message", {})
            content = msg.get("content", [])
            if isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    bt = block.get("type")
                    if bt == "tool_use":
                        name = str(block.get("name", "tool"))
                        inp = block.get("input", {})
                        summary = _tool_summary(name, inp)
                        events.append(
                            ActivityEvent(
                                kind="tool",
                                title=f"{name}: {summary}",
                                detail=json.dumps(inp, ensure_ascii=False, indent=2),
                                timestamp=ts,
                                tool_name=name,
                                session_id=session_id,
                                raw_type=bt,
                            )
                        )
                    elif bt == "text":
                        text = str(block.get("text", "")).strip()
                        if text:
                            events.append(
                                ActivityEvent(
                                    kind="assistant",
                                    title=text[:160],
                                    detail=text,
                                    timestamp=ts,
                                    session_id=session_id,
                                    raw_type=typ,
                                )
                            )
            elif obj.get("isApiErrorMessage") or obj.get("error"):
                text = _text_from_content(content) or "API 错误"
                events.append(
                    ActivityEvent(
                        kind="error",
                        title=text[:160],
                        detail=text,
                        timestamp=ts,
                        session_id=session_id,
                        raw_type="api_error",
                    )
                )
            continue

        if typ == "system":
            subtype = str(obj.get("subtype", ""))
            if subtype == "api_error":
                attempt = obj.get("retryAttempt", "")
                events.append(
                    ActivityEvent(
                        kind="error",
                        title=f"API 重试 {attempt}/{obj.get('maxRetries', '')}",
                        detail=json.dumps(obj.get("error", {}), ensure_ascii=False),
                        timestamp=ts,
                        session_id=session_id,
                        raw_type=subtype,
                    )
                )
            continue

        if typ == "file-history-snapshot":
            snap = obj.get("snapshot", {})
            backups = snap.get("trackedFileBackups", {})
            if backups:
                files = ", ".join(list(backups.keys())[:5])
                events.append(
                    ActivityEvent(
                        kind="file",
                        title=f"文件快照 ({len(backups)} 个文件)",
                        detail=files,
                        timestamp=ts,
                        session_id=session_id,
                        raw_type=typ,
                    )
                )

    return events


def _tool_summary(name: str, inp: Any) -> str:
    if not isinstance(inp, dict):
        return str(inp)[:120]
    if name == "Bash":
        return str(inp.get("command", ""))[:120]
    if name in ("Read", "Write", "Edit", "NotebookEdit"):
        return str(inp.get("file_path", inp.get("path", "")))[:120]
    if name == "Grep":
        return str(inp.get("pattern", ""))[:80]
    if name == "Glob":
        return str(inp.get("pattern", ""))[:80]
    if name == "WebFetch":
        return str(inp.get("url", ""))[:120]
    # 通用
    for key in ("command", "path", "file_path", "url", "query", "description"):
        if inp.get(key):
            return str(inp[key])[:120]
    return json.dumps(inp, ensure_ascii=False)[:120]


def load_recent_history(work_dir: str, limit: int = 30) -> List[dict]:
    """全局 history.jsonl 里与本项目相关的最近输入。"""
    path = claude_home() / "history.jsonl"
    if not path.is_file():
        return []

    norm = os.path.normpath(os.path.abspath(work_dir))
    rows: List[dict] = []
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            proj = os.path.normpath(str(obj.get("project", "")))
            if proj != norm:
                continue
            rows.append(obj)
    except OSError:
        return rows

    rows.sort(key=lambda r: r.get("timestamp", 0), reverse=True)
    return rows[:limit]


def load_session_tasks(session_id: str) -> List[dict]:
    tasks_dir = claude_home() / "tasks" / session_id
    if not tasks_dir.is_dir():
        return []
    items: List[dict] = []
    for fp in sorted(tasks_dir.glob("*.json"), key=lambda p: int(p.stem) if p.stem.isdigit() else p.stem):
        try:
            items.append(json.loads(fp.read_text(encoding="utf-8")))
        except Exception:
            continue
    return items


def git_short_status(work_dir: str) -> str:
    import subprocess

    if not os.path.isdir(work_dir):
        return ""
    try:
        r = subprocess.run(
            ["git", "status", "--short", "--branch"],
            cwd=work_dir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=8,
        )
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except Exception:
        pass
    return ""
