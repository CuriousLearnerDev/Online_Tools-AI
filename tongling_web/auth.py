"""统领 Web 门户访问令牌 — 首次启动生成，之后持久保存在 storage/.tongling_web_token。"""

from __future__ import annotations

import hmac
import os
import secrets
from typing import Any, Optional, Tuple
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

TOKEN_ENV = "TONGLING_WEB_TOKEN"
TOKEN_COOKIE = "tongling_token"
TOKEN_FILENAME = ".tongling_web_token"


def token_file_path(tongling_root: str | None = None) -> str:
    root = tongling_root or os.environ.get("TONGLING_ROOT") or os.path.dirname(os.path.dirname(__file__))
    return os.path.join(root, "storage", TOKEN_FILENAME)


def init_web_token(tongling_root: str | None = None) -> str:
    """生成新 Token 并写入环境变量与 storage/.tongling_web_token。"""
    token = secrets.token_urlsafe(32)
    os.environ[TOKEN_ENV] = token
    path = token_file_path(tongling_root)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(token)
    except OSError:
        pass
    return token


def get_web_token() -> str:
    return os.environ.get(TOKEN_ENV, "").strip()


def read_web_token_file(tongling_root: str | None = None) -> str:
    path = token_file_path(tongling_root)
    if not os.path.isfile(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def ensure_web_token(tongling_root: str | None = None) -> str:
    existing = get_web_token() or read_web_token_file(tongling_root)
    if existing:
        os.environ[TOKEN_ENV] = existing
        return existing
    return init_web_token(tongling_root)


def verify_token(provided: Optional[str]) -> bool:
    """校验访问令牌。无服务端令牌时拒绝（fail-closed），不开放匿名访问。"""
    expected = get_web_token()
    if not expected or not provided:
        return False
    return hmac.compare_digest(str(provided), expected)


def auth_is_configured() -> bool:
    return bool(get_web_token())


API_TOKEN_ENV = "HEXSTRIKE_API_TOKEN"


def bind_api_token_from_web(web_token: str | None = None) -> str:
    """统领模式：将 Web 访问令牌同步为 HexStrike API Bearer 令牌。"""
    token = (web_token or get_web_token() or "").strip()
    if token:
        os.environ[API_TOKEN_ENV] = token
    return token


def get_api_token() -> str:
    return (os.environ.get(API_TOKEN_ENV) or get_web_token() or "").strip()


def api_auth_headers() -> dict[str, str]:
    token = get_api_token()
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}


def extract_api_token_from_request(request: Any) -> Optional[str]:
    if hasattr(request, "headers"):
        auth = request.headers.get("Authorization") or ""
        if auth.startswith("Bearer "):
            bearer = auth[7:].strip()
            if verify_api_token(bearer):
                return bearer
    return find_valid_token_from_request(request)


def verify_api_token(provided: Optional[str]) -> bool:
    expected = get_api_token()
    if not expected or not provided:
        return False
    return hmac.compare_digest(str(provided), expected)


def parse_ws_path(raw_path: str) -> Tuple[str, Optional[str]]:
    if not raw_path:
        return "/", None
    if "?" in raw_path:
        path, _, qs = raw_path.partition("?")
        params = parse_qs(qs)
        token = (params.get("token") or [None])[0]
        return path or "/", token
    return raw_path, None


def _cookie_token(cookie_header: str) -> Optional[str]:
    if not cookie_header:
        return None
    for part in cookie_header.split(";"):
        part = part.strip()
        if part.startswith(f"{TOKEN_COOKIE}="):
            return part.split("=", 1)[1].strip()
    return None


def _token_candidates_from_request(request: Any) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []

    def add(raw: Optional[str]) -> None:
        if not raw:
            return
        val = str(raw).strip()
        if val and val not in seen:
            seen.add(val)
            out.append(val)

    if hasattr(request, "args"):
        add(request.args.get("token"))
    if hasattr(request, "cookies"):
        add(request.cookies.get(TOKEN_COOKIE))
    if hasattr(request, "headers"):
        add(request.headers.get("X-Tongling-Token"))
        add(_cookie_token(request.headers.get("Cookie") or ""))
    return out


def find_valid_token_from_request(request: Any) -> Optional[str]:
    for candidate in _token_candidates_from_request(request):
        if verify_token(candidate):
            return candidate
    return None


def extract_token_from_request(request: Any) -> Optional[str]:
    valid = find_valid_token_from_request(request)
    if valid:
        return valid
    candidates = _token_candidates_from_request(request)
    return candidates[0] if candidates else None


def extract_token_from_ws(ws: Any) -> Optional[str]:
    candidates: list[str] = []
    seen: set[str] = set()

    def add(raw: Optional[str]) -> None:
        if not raw:
            return
        val = str(raw).strip()
        if val and val not in seen:
            seen.add(val)
            candidates.append(val)

    path = ""
    req = getattr(ws, "request", None)
    if req is not None:
        path = getattr(req, "path", "") or ""
        headers = getattr(req, "headers", None)
        if headers:
            add(headers.get("X-Tongling-Token") or headers.get("x-tongling-token"))
            add(_cookie_token(headers.get("Cookie") or headers.get("cookie") or ""))
    if not path:
        path = getattr(ws, "path", "") or ""
    _, qs_token = parse_ws_path(path)
    add(qs_token)

    for candidate in candidates:
        if verify_token(candidate):
            return candidate
    return candidates[0] if candidates else None


def append_token(url: str, token: str) -> str:
    if not token:
        return url
    parsed = urlparse(url)
    q = parse_qs(parsed.query, keep_blank_values=True)
    q["token"] = [token]
    new_query = urlencode(q, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


def portal_url(base: str, token: str | None = None) -> str:
    tok = token or get_web_token()
    url = base.rstrip("/") + "/tongling/"
    return append_token(url, tok) if tok else url


UNAUTHORIZED_HTML = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>需要访问令牌 · 统领</title>
<style>
  body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;background:#0d0f14;color:#8b95a8;font-family:system-ui,sans-serif}
  .box{max-width:420px;padding:32px;border:1px solid #252836;border-radius:12px;background:#13161e}
  h1{color:#e2e8f0;font-size:20px;margin:0 0 12px}
  p{line-height:1.6;margin:0 0 10px;font-size:14px}
  code{color:#00e676;background:rgba(0,230,118,.1);padding:2px 6px;border-radius:4px}
  ol{margin:8px 0 0;padding-left:20px;line-height:1.7;font-size:14px}
</style></head><body><div class="box">
<h1>访问令牌无效或已过期</h1>
<p>统领 Web 控制台已启用 Token 保护。当前 URL 中的令牌与服务端不一致。</p>
<ol>
<li>在统领桌面点击顶栏 <strong>「打开 Web 终端」</strong>，会自动带上正确令牌；或</li>
<li>查看 <code>storage/.tongling_web_token</code> 文件中的最新令牌，重新访问 <code>/tongling/?token=…</code></li>
</ol>
<p>若仍无法访问，请重启统领 / HexStrike Server 后再试。</p>
</div></body></html>"""

SERVICE_UNAVAILABLE_HTML = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>服务未就绪 · 统领</title>
<style>
  body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;background:#0d0f14;color:#8b95a8;font-family:system-ui,sans-serif}
  .box{max-width:420px;padding:32px;border:1px solid #252836;border-radius:12px;background:#13161e}
  h1{color:#e2e8f0;font-size:20px;margin:0 0 12px}
  p{line-height:1.6;margin:0 0 10px;font-size:14px}
</style></head><body><div class="box">
<h1>访问令牌未就绪</h1>
<p>统领 Web 控制台未能加载访问令牌，已拒绝本次请求。</p>
<p>请<strong>重启统领 / HexStrike Server</strong>，或从桌面「打开 Web 控制台」重新进入。</p>
</div></body></html>"""
