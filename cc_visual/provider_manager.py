#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Claude Code 模型/提供商配置管理（类似 cc-switch）。"""

from __future__ import annotations

import json
import os
import shutil
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib import error as urllib_error
from urllib import request as urllib_request

_TONGLING_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = _TONGLING_ROOT
PROVIDERS_FILE = os.path.join(_TONGLING_ROOT, "storage", "claude_agent_providers.json")
CLAUDE_USER_SETTINGS = os.path.join(
    os.environ.get("USERPROFILE", os.path.expanduser("~")),
    ".claude",
    "settings.json",
)

# Claude Code 网关相关 env 键（官方文档）
PROVIDER_ENV_KEYS = (
    "ANTHROPIC_BASE_URL",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_MODEL",
    "ANTHROPIC_DEFAULT_SONNET_MODEL",
    "ANTHROPIC_DEFAULT_OPUS_MODEL",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL",
    "ANTHROPIC_SMALL_FAST_MODEL",
)


@dataclass
class ProviderProfile:
    id: str
    name: str
    env: Dict[str, str] = field(default_factory=dict)
    model_hint: str = ""
    notes: str = ""
    builtin: bool = False

    def masked_summary(self) -> str:
        parts: List[str] = []
        base = self.env.get("ANTHROPIC_BASE_URL", "")
        if base:
            parts.append(base.replace("https://", "").split("/")[0])
        model = self.env.get("ANTHROPIC_MODEL") or self.model_hint
        if model:
            parts.append(model)
        token = self.env.get("ANTHROPIC_AUTH_TOKEN") or self.env.get("ANTHROPIC_API_KEY", "")
        if token:
            parts.append(f"key:{_mask_secret(token)}")
        return " · ".join(parts) if parts else "（官方默认 / 无自定义 env）"


def _mask_secret(value: str) -> str:
    v = (value or "").strip()
    if len(v) <= 8:
        return "***"
    return v[:4] + "…" + v[-4:]


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def builtin_presets() -> List[ProviderProfile]:
    return [
        ProviderProfile(
            id="official",
            name="官方 Anthropic",
            env={},
            model_hint="sonnet / opus（官方）",
            notes="清除自定义 BASE_URL，使用官方登录或 ANTHROPIC_API_KEY",
            builtin=True,
        ),
        ProviderProfile(
            id="deepseek",
            name="DeepSeek",
            env={
                "ANTHROPIC_BASE_URL": "https://api.deepseek.com/anthropic",
                "ANTHROPIC_MODEL": "deepseek-v4-pro",
                "ANTHROPIC_DEFAULT_SONNET_MODEL": "deepseek-v4-pro",
                "ANTHROPIC_DEFAULT_OPUS_MODEL": "deepseek-v4-pro",
                "ANTHROPIC_DEFAULT_HAIKU_MODEL": "deepseek-v4-flash",
            },
            model_hint="deepseek-v4-pro",
            notes="DeepSeek Anthropic 兼容接口",
            builtin=True,
        ),
        ProviderProfile(
            id="openrouter",
            name="OpenRouter",
            env={
                "ANTHROPIC_BASE_URL": "https://openrouter.ai/api",
                "ANTHROPIC_MODEL": "anthropic/claude-sonnet-4",
            },
            model_hint="anthropic/claude-sonnet-4",
            notes="需在 env 中填写 ANTHROPIC_AUTH_TOKEN",
            builtin=True,
        ),
        ProviderProfile(
            id="siliconflow",
            name="SiliconFlow",
            env={
                "ANTHROPIC_BASE_URL": "https://api.siliconflow.cn",
                "ANTHROPIC_MODEL": "deepseek-ai/DeepSeek-V3",
            },
            model_hint="deepseek-ai/DeepSeek-V3",
            notes="国内 API 聚合，需填写 Token",
            builtin=True,
        ),
        ProviderProfile(
            id="custom_local",
            name="本地代理 / 自定义",
            env={
                "ANTHROPIC_BASE_URL": "http://127.0.0.1:8080",
            },
            model_hint="",
            notes="填写 BASE_URL 与 Token 后启用",
            builtin=True,
        ),
    ]


def _load_store() -> dict:
    if not os.path.isfile(PROVIDERS_FILE):
        return {"active_id": "official", "providers": []}
    try:
        with open(PROVIDERS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("invalid store")
        return data
    except Exception:
        return {"active_id": "official", "providers": []}


def _save_store(data: dict) -> None:
    tmp = PROVIDERS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, PROVIDERS_FILE)


def list_all_providers() -> List[ProviderProfile]:
    store = _load_store()
    custom = [
        ProviderProfile(**p)
        for p in store.get("providers", [])
        if isinstance(p, dict)
    ]
    builtins = {p.id: p for p in builtin_presets()}
    merged: List[ProviderProfile] = list(builtins.values())
    for p in custom:
        if p.id not in builtins:
            merged.append(p)
    return merged


def get_active_provider_id() -> str:
    return str(_load_store().get("active_id") or "official")


def get_active_provider() -> Optional[ProviderProfile]:
    active_id = get_active_provider_id()
    for p in list_all_providers():
        if p.id == active_id:
            return p
    return None


def save_custom_provider(profile: ProviderProfile) -> ProviderProfile:
    if profile.builtin:
        raise ValueError("不能覆盖内置预设")
    store = _load_store()
    items = store.get("providers", [])
    profile = ProviderProfile(
        id=profile.id or _new_id(),
        name=profile.name.strip() or "未命名",
        env={k: str(v).strip() for k, v in profile.env.items() if str(v).strip()},
        model_hint=profile.model_hint.strip(),
        notes=profile.notes.strip(),
        builtin=False,
    )
    replaced = False
    for i, raw in enumerate(items):
        if isinstance(raw, dict) and raw.get("id") == profile.id:
            items[i] = asdict(profile)
            replaced = True
            break
    if not replaced:
        items.append(asdict(profile))
    store["providers"] = items
    _save_store(store)
    return profile


def delete_custom_provider(provider_id: str) -> bool:
    store = _load_store()
    before = len(store.get("providers", []))
    store["providers"] = [
        p for p in store.get("providers", [])
        if isinstance(p, dict) and p.get("id") != provider_id
    ]
    if get_active_provider_id() == provider_id:
        store["active_id"] = "official"
    _save_store(store)
    return len(store["providers"]) < before


def set_active_provider(provider_id: str) -> Tuple[bool, str]:
    profile = None
    for p in list_all_providers():
        if p.id == provider_id:
            profile = p
            break
    if not profile:
        return False, "提供商不存在"

    ok, msg = apply_provider_to_claude_settings(profile)
    if not ok:
        return False, msg

    store = _load_store()
    store["active_id"] = provider_id
    _save_store(store)
    return True, f"已切换到：{profile.name}"


def _read_claude_settings() -> dict:
    if not os.path.isfile(CLAUDE_USER_SETTINGS):
        return {}
    try:
        with open(CLAUDE_USER_SETTINGS, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _backup_settings() -> None:
    if not os.path.isfile(CLAUDE_USER_SETTINGS):
        return
    backup_dir = os.path.join(APP_DIR, "settings_backups")
    os.makedirs(backup_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy2(CLAUDE_USER_SETTINGS, os.path.join(backup_dir, f"settings_{ts}.json"))


def apply_provider_to_claude_settings(
    profile: ProviderProfile,
    *,
    preserve_token: bool = True,
) -> Tuple[bool, str]:
    """写入 ~/.claude/settings.json 的 env 块（cc-switch 同款机制）。"""
    settings = _read_claude_settings()
    old_env = dict(settings.get("env") or {})
    env = dict(old_env)

    for key in PROVIDER_ENV_KEYS:
        env.pop(key, None)

    for key, value in profile.env.items():
        if key in PROVIDER_ENV_KEYS and str(value).strip():
            env[key] = str(value).strip()

    if preserve_token and not env.get("ANTHROPIC_AUTH_TOKEN") and not env.get("ANTHROPIC_API_KEY"):
        for tk in ("ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY"):
            if old_env.get(tk):
                env[tk] = old_env[tk]
                break

    if env:
        settings["env"] = env
    elif "env" in settings:
        settings["env"] = {}

    os.makedirs(os.path.dirname(CLAUDE_USER_SETTINGS), exist_ok=True)
    _backup_settings()
    tmp = CLAUDE_USER_SETTINGS + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
        os.replace(tmp, CLAUDE_USER_SETTINGS)
    except OSError as exc:
        return False, f"写入 settings.json 失败: {exc}"
    return True, "ok"


def import_from_claude_settings(name: str = "从当前配置导入") -> ProviderProfile:
    settings = _read_claude_settings()
    env_block = settings.get("env") or {}
    picked = {
        k: str(v)
        for k, v in env_block.items()
        if k in PROVIDER_ENV_KEYS and str(v).strip()
    }
    profile = ProviderProfile(
        id=_new_id(),
        name=name,
        env=picked,
        model_hint=str(picked.get("ANTHROPIC_MODEL", "")),
        notes="从 ~/.claude/settings.json 导入",
    )
    return save_custom_provider(profile)


def read_live_env() -> Dict[str, str]:
    """读取当前 Claude settings 中的 provider env。"""
    env = _read_claude_settings().get("env") or {}
    return {k: str(env[k]) for k in PROVIDER_ENV_KEYS if k in env}


def provider_env_for_launch() -> Dict[str, str]:
    """启动 Claude 时合并到进程环境变量（含 Token）。"""
    live = read_live_env()
    active = get_active_provider()
    merged = dict(live)
    if active:
        for k, v in active.env.items():
            if k in PROVIDER_ENV_KEYS and str(v).strip():
                merged[k] = str(v).strip()
    return merged


def mark_active_provider(provider_id: str) -> None:
    store = _load_store()
    store["active_id"] = provider_id
    _save_store(store)


def detect_matching_provider_id() -> Optional[str]:
    live = read_live_env()
    if not live:
        return "official"
    for p in list_all_providers():
        if not p.env:
            continue
        if all(live.get(k) == v for k, v in p.env.items() if k in ("ANTHROPIC_BASE_URL", "ANTHROPIC_MODEL")):
            return p.id
    return None


def _messages_api_url(base_url: str) -> str:
    if not str(base_url or "").strip():
        return "https://api.anthropic.com/v1/messages"
    base = str(base_url).strip().rstrip("/")
    if base.endswith("/messages"):
        return base
    if base.endswith("/v1"):
        return f"{base}/messages"
    if base.endswith("/anthropic"):
        return f"{base}/v1/messages"
    return f"{base}/v1/messages"


def _parse_api_error(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return "未知错误"
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            err = data.get("error")
            if isinstance(err, dict) and err.get("message"):
                return str(err["message"])[:240]
            if isinstance(err, str):
                return err[:240]
            if data.get("message"):
                return str(data["message"])[:240]
    except Exception:
        pass
    return text[:240]


def resolve_env_for_test(
    *,
    provider_id: str = "",
    env_override: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    """合并提供商预设、表单输入与 settings 中已保存的 Key。"""
    env: Dict[str, str] = {}
    pid = str(provider_id or "").strip()
    if pid:
        for p in list_all_providers():
            if p.id == pid:
                env.update({k: str(v).strip() for k, v in p.env.items() if str(v).strip()})
                break
    live = read_live_env()
    for key in PROVIDER_ENV_KEYS:
        if key not in env and live.get(key):
            env[key] = live[key]
    if env_override:
        for key, value in env_override.items():
            if value is not None and str(value).strip():
                env[key] = str(value).strip()
    return env


def test_provider_api(env: Dict[str, str], *, timeout: float = 25.0) -> Tuple[bool, str, Dict[str, Any]]:
    """向 Anthropic 兼容接口发送最小 messages 请求，验证 Key 是否可用。"""
    base = str(env.get("ANTHROPIC_BASE_URL") or "").strip()
    token = str(env.get("ANTHROPIC_AUTH_TOKEN") or env.get("ANTHROPIC_API_KEY") or "").strip()
    model = (
        str(env.get("ANTHROPIC_MODEL") or "").strip()
        or str(env.get("ANTHROPIC_DEFAULT_HAIKU_MODEL") or "").strip()
        or "claude-3-5-haiku-latest"
    )
    meta: Dict[str, Any] = {"endpoint": _messages_api_url(base), "model": model}

    if not token:
        if not base:
            return False, "官方 Anthropic 未配置 API Key，请在 Token 字段填写或在 Claude Code 中登录", meta
        return False, "未填写 API Key（Token 留空且 settings 中无已保存 Key）", meta

    url = meta["endpoint"]
    payload = json.dumps(
        {
            "model": model,
            "max_tokens": 8,
            "messages": [{"role": "user", "content": "ping"}],
        },
        ensure_ascii=False,
    ).encode("utf-8")

    auth_modes = (
        {"x-api-key": token, "anthropic-version": "2023-06-01"},
        {"Authorization": f"Bearer {token}", "anthropic-version": "2023-06-01"},
    )
    last_detail = ""
    started = time.monotonic()

    for headers in auth_modes:
        req_headers = {
            "Content-Type": "application/json",
            **headers,
        }
        req = urllib_request.Request(url, data=payload, headers=req_headers, method="POST")
        try:
            with urllib_request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                elapsed_ms = int((time.monotonic() - started) * 1000)
                meta["elapsed_ms"] = elapsed_ms
                meta["http_status"] = getattr(resp, "status", 200)
                if resp.status in (200, 201):
                    return True, f"Key 有效 · HTTP {resp.status} · {elapsed_ms}ms", meta
                last_detail = _parse_api_error(raw)
        except urllib_error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            last_detail = _parse_api_error(raw)
            meta["http_status"] = exc.code
            if exc.code in (401, 403):
                continue
            elapsed_ms = int((time.monotonic() - started) * 1000)
            meta["elapsed_ms"] = elapsed_ms
            return False, f"请求失败 · HTTP {exc.code}: {last_detail}", meta
        except urllib_error.URLError as exc:
            reason = getattr(exc, "reason", exc)
            return False, f"连接失败: {reason}", meta
        except OSError as exc:
            return False, f"连接失败: {exc}", meta

    elapsed_ms = int((time.monotonic() - started) * 1000)
    meta["elapsed_ms"] = elapsed_ms
    status = meta.get("http_status")
    if status in (401, 403):
        return False, f"Key 无效或无权访问 · HTTP {status}: {last_detail or '认证失败'}", meta
    return False, last_detail or "验证失败", meta
