"""提示词库 — storage/prompts/prompts.json"""

from __future__ import annotations

import os
import re
import secrets
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

_lock = threading.Lock()
_STORE_NAME = "prompts.json"

# tag: scan | daily | custom
PROMPT_TAGS = (
    ("scan", "扫描场景"),
    ("daily", "日常助手"),
    ("custom", "自定义"),
)

_BUILTIN_SEED: List[Dict[str, Any]] = [
    {
        "id": "builtin_web_recon",
        "name": "Web 信息收集",
        "description": "子域、HTTP 探测、目录与技术栈识别",
        "tag": "scan",
        "scenario_id": "web_recon",
        "content": (
            "请对目标 {target} 进行授权范围内的 Web 信息收集：子域枚举、HTTP 探测、目录与参数发现、技术栈识别。"
            " 必须通过 HexStrike MCP 工具逐步执行（如 subfinder、httpx、nuclei 等），每步说明使用的工具与关键发现。"
        ),
    },
    {
        "id": "builtin_vuln_scan",
        "name": "漏洞扫描",
        "description": "nuclei / sqlmap / ffuf 等工具链",
        "tag": "scan",
        "scenario_id": "vuln_scan",
        "content": (
            "请对目标 {target} 进行授权范围内的漏洞扫描，优先使用 nuclei、sqlmap、ffuf 等 HexStrike MCP 工具。"
            " 按高危→低危汇报，给出证据片段与修复建议。"
        ),
    },
    {
        "id": "builtin_full_pentest",
        "name": "完整渗透评估",
        "description": "信息收集 → 漏洞验证 → 风险汇总",
        "tag": "scan",
        "scenario_id": "full_pentest",
        "content": (
            "请对目标 {target} 制定并执行完整渗透评估：信息收集 → 漏洞验证 → 风险汇总。"
            " 全程通过 HexStrike MCP 调用工具，不要仅给理论步骤。"
        ),
    },
    {
        "id": "builtin_port_service",
        "name": "端口与服务",
        "description": "nmap / naabu 端口与服务识别",
        "tag": "scan",
        "scenario_id": "port_service",
        "content": (
            "请对目标 {target} 进行端口扫描与服务识别（nmap/naabu 等 MCP 工具），"
            "列出开放端口、服务版本与潜在攻击面。"
        ),
    },
    {
        "id": "builtin_daily_mcp",
        "name": "检查 MCP 工具",
        "description": "新建终端后快速确认 MCP 可用性",
        "tag": "daily",
        "content": "请执行 /mcp，列出当前可用 MCP 服务器与工具，并简要说明 HexStrike 是否已就绪。",
    },
    {
        "id": "builtin_daily_summary",
        "name": "会话总结",
        "description": "让 Claude 汇总本轮发现",
        "tag": "daily",
        "content": (
            "请总结本次会话已确认的资产、漏洞线索、下一步建议；"
            "若适合落盘，请写入 {report_path}（Markdown）。"
        ),
    },
]


def _tongling_root() -> str:
    return os.environ.get("TONGLING_ROOT") or os.path.dirname(os.path.dirname(__file__))


def prompts_dir() -> str:
    return os.path.join(_tongling_root(), "storage", "prompts")


def _store_path() -> str:
    return os.path.join(prompts_dir(), _STORE_NAME)


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _read_json(path: str, default: Any) -> Any:
    if not os.path.isfile(path):
        return default
    try:
        import json

        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _write_json(path: str, data: Any) -> None:
    import json

    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _new_id(prefix: str = "prompt") -> str:
    return f"{prefix}_{int(time.time())}_{secrets.token_hex(3)}"


def _normalize_item(raw: Dict[str, Any], *, is_builtin: bool = False) -> Dict[str, Any]:
    tag = str(raw.get("tag") or "custom").strip().lower()
    if tag not in {t for t, _ in PROMPT_TAGS}:
        tag = "custom"
    content = str(raw.get("content") or "").strip()
    name = str(raw.get("name") or "").strip() or "未命名模板"
    item = {
        "id": str(raw.get("id") or _new_id()),
        "name": name[:80],
        "description": str(raw.get("description") or "").strip()[:200],
        "tag": tag,
        "content": content,
        "enabled": bool(raw.get("enabled", True)),
        "is_builtin": bool(raw.get("is_builtin", is_builtin)),
        "scenario_id": str(raw.get("scenario_id") or "").strip(),
        "created_at": str(raw.get("created_at") or _now_iso()),
        "updated_at": str(raw.get("updated_at") or _now_iso()),
    }
    return item


def _seed_builtins() -> List[Dict[str, Any]]:
    now = _now_iso()
    items = []
    for seed in _BUILTIN_SEED:
        items.append(
            _normalize_item(
                {
                    **seed,
                    "enabled": True,
                    "is_builtin": True,
                    "created_at": now,
                    "updated_at": now,
                },
                is_builtin=True,
            )
        )
    return items


def _load_raw() -> Dict[str, Any]:
    data = _read_json(_store_path(), None)
    if not isinstance(data, dict) or not isinstance(data.get("prompts"), list):
        prompts = _seed_builtins()
        payload = {"version": 1, "prompts": prompts}
        _write_json(_store_path(), payload)
        return payload

    existing_ids = {str(p.get("id")) for p in data["prompts"] if isinstance(p, dict)}
    changed = False
    for seed in _seed_builtins():
        if seed["id"] not in existing_ids:
            data["prompts"].append(seed)
            changed = True
    if changed:
        _write_json(_store_path(), data)
    return data


def _save_raw(data: Dict[str, Any]) -> None:
    _write_json(_store_path(), data)


def list_prompts(
    *,
    tag: str = "",
    q: str = "",
    enabled_only: bool = False,
) -> List[Dict[str, Any]]:
    with _lock:
        data = _load_raw()
        items = [_normalize_item(p) for p in data.get("prompts") or [] if isinstance(p, dict)]

    tag = (tag or "").strip().lower()
    q = (q or "").strip().lower()
    if tag:
        items = [p for p in items if p["tag"] == tag]
    if enabled_only:
        items = [p for p in items if p["enabled"]]
    if q:
        items = [
            p
            for p in items
            if q in p["name"].lower()
            or q in p["description"].lower()
            or q in p["content"].lower()
            or q in p["id"].lower()
        ]

    tag_order = {t: i for i, (t, _) in enumerate(PROMPT_TAGS)}
    items.sort(
        key=lambda p: (
            0 if p["is_builtin"] else 1,
            tag_order.get(p["tag"], 99),
            p["name"].lower(),
        )
    )
    return items


def get_prompt(prompt_id: str) -> Optional[Dict[str, Any]]:
    pid = (prompt_id or "").strip()
    if not pid:
        return None
    for p in list_prompts():
        if p["id"] == pid:
            return p
    return None


def create_prompt(body: Dict[str, Any]) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    name = str(body.get("name") or "").strip()
    content = str(body.get("content") or "").strip()
    if not name:
        return False, "请填写模板名称", None
    if not content:
        return False, "请填写提示词内容", None

    now = _now_iso()
    item = _normalize_item(
        {
            "id": _new_id("custom"),
            "name": name,
            "description": body.get("description") or "",
            "tag": body.get("tag") or "custom",
            "content": content,
            "enabled": body.get("enabled", True),
            "is_builtin": False,
            "scenario_id": "",
            "created_at": now,
            "updated_at": now,
        }
    )
    with _lock:
        data = _load_raw()
        data.setdefault("prompts", []).append(item)
        _save_raw(data)
    return True, "已创建", item


def update_prompt(prompt_id: str, body: Dict[str, Any]) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    pid = (prompt_id or "").strip()
    if not pid:
        return False, "缺少模板 id", None

    with _lock:
        data = _load_raw()
        prompts = data.get("prompts") or []
        idx = next((i for i, p in enumerate(prompts) if isinstance(p, dict) and p.get("id") == pid), -1)
        if idx < 0:
            return False, "模板不存在", None

        cur = _normalize_item(prompts[idx])
        if "name" in body:
            name = str(body.get("name") or "").strip()
            if not name:
                return False, "名称不能为空", None
            cur["name"] = name[:80]
        if "description" in body:
            cur["description"] = str(body.get("description") or "").strip()[:200]
        if "tag" in body:
            tag = str(body.get("tag") or "custom").strip().lower()
            if tag not in {t for t, _ in PROMPT_TAGS}:
                return False, "无效分类", None
            if not cur["is_builtin"]:
                cur["tag"] = tag
        if "content" in body:
            content = str(body.get("content") or "").strip()
            if not content:
                return False, "内容不能为空", None
            cur["content"] = content
        if "enabled" in body:
            cur["enabled"] = bool(body.get("enabled"))
        cur["updated_at"] = _now_iso()
        prompts[idx] = cur
        data["prompts"] = prompts
        _save_raw(data)
    return True, "已更新", cur


def delete_prompt(prompt_id: str) -> Tuple[bool, str]:
    pid = (prompt_id or "").strip()
    if not pid:
        return False, "缺少模板 id"

    with _lock:
        data = _load_raw()
        prompts = data.get("prompts") or []
        target = next((p for p in prompts if isinstance(p, dict) and p.get("id") == pid), None)
        if not target:
            return False, "模板不存在"
        if target.get("is_builtin"):
            return False, "内置模板不可删除，可禁用或编辑"
        data["prompts"] = [p for p in prompts if not (isinstance(p, dict) and p.get("id") == pid)]
        _save_raw(data)
    return True, "已删除"


def reset_builtin(prompt_id: str) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """将内置模板恢复为种子内容。"""
    pid = (prompt_id or "").strip()
    seed = next((s for s in _BUILTIN_SEED if s["id"] == pid), None)
    if not seed:
        return False, "不是可重置的内置模板", None

    with _lock:
        data = _load_raw()
        prompts = data.get("prompts") or []
        idx = next((i for i, p in enumerate(prompts) if isinstance(p, dict) and p.get("id") == pid), -1)
        now = _now_iso()
        item = _normalize_item(
            {
                **seed,
                "enabled": True,
                "is_builtin": True,
                "created_at": (prompts[idx].get("created_at") if idx >= 0 else now),
                "updated_at": now,
            },
            is_builtin=True,
        )
        if idx >= 0:
            prompts[idx] = item
        else:
            prompts.append(item)
        data["prompts"] = prompts
        _save_raw(data)
    return True, "已恢复内置内容", item


_VAR_RE = re.compile(r"\{([a-zA-Z_][\w]*)\}")


def render_content(content: str, variables: Optional[Dict[str, Any]] = None) -> str:
    vars_map = {str(k): str(v if v is not None else "") for k, v in (variables or {}).items()}
    # defaults for common placeholders
    vars_map.setdefault("target", vars_map.get("target") or "{target}")
    vars_map.setdefault("report_path", vars_map.get("report_path") or "reports/scan_report.md")

    def repl(m: re.Match) -> str:
        key = m.group(1)
        if key in vars_map:
            return vars_map[key]
        return m.group(0)

    return _VAR_RE.sub(repl, content or "")


def render_prompt(prompt_id: str, variables: Optional[Dict[str, Any]] = None) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    item = get_prompt(prompt_id)
    if not item:
        return False, "模板不存在", None
    if not item.get("enabled", True):
        return False, "模板已禁用", None
    text = render_content(item["content"], variables)
    return True, "", {**item, "rendered": text}


def stats() -> Dict[str, int]:
    items = list_prompts()
    return {
        "total": len(items),
        "enabled": sum(1 for p in items if p["enabled"]),
        "builtin": sum(1 for p in items if p["is_builtin"]),
        "custom": sum(1 for p in items if not p["is_builtin"]),
        "scan": sum(1 for p in items if p["tag"] == "scan"),
        "daily": sum(1 for p in items if p["tag"] == "daily"),
    }


def tag_labels() -> List[Dict[str, str]]:
    return [{"id": tid, "label": label} for tid, label in PROMPT_TAGS]
