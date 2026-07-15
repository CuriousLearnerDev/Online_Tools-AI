"""社交接入配置连通性测试。"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from tongling_web.im_bridge.config_store import load_config
from tongling_web.im_bridge.http_util import append_access_token, http_json

Check = Dict[str, Any]

SECRET_KEYS = ("bot_token", "app_secret", "app_key", "access_token", "verification_token")


def merge_platform_config(platform: str, incoming: Dict[str, Any] | None) -> Dict[str, Any]:
    saved = (load_config().get("platforms") or {}).get(platform) or {}
    merged = dict(saved)
    for k, v in (incoming or {}).items():
        if k in SECRET_KEYS:
            text = str(v or "")
            if not text or "…" in text or text == "****":
                continue
        merged[k] = v
    return merged


def _checks(ok: bool, name: str, detail: str, *, warn: bool = False) -> Check:
    return {"name": name, "ok": ok, "warn": warn, "detail": detail}


def test_telegram(cfg: Dict[str, Any], *, send_test: bool = False, test_target: str = "") -> Tuple[bool, List[Check], str]:
    checks: List[Check] = []
    token = str(cfg.get("bot_token") or "").strip()
    if not token:
        checks.append(_checks(False, "Bot Token", "未填写 Bot Token"))
        return False, checks, "请填写 Bot Token"

    url = f"https://api.telegram.org/bot{token}/getMe"
    _, data, err = http_json(url, timeout=15)
    if not data or not data.get("ok"):
        detail = str((data or {}).get("description") or err)[:200]
        checks.append(_checks(False, "Bot Token 校验", detail or "getMe 失败"))
        return False, checks, "Bot Token 无效或网络不可达"

    bot = data.get("result") or {}
    username = bot.get("username") or bot.get("first_name") or "bot"
    checks.append(_checks(True, "Bot Token 校验", f"@{username}（id: {bot.get('id', '?')}）"))

    wh_url = f"https://api.telegram.org/bot{token}/getWebhookInfo"
    _, wh_data, _ = http_json(wh_url, timeout=10)
    wh = (wh_data or {}).get("result") or {}
    wh_set = bool(str(wh.get("url") or "").strip())
    if wh_set:
        checks.append(_checks(True, "Webhook 状态", f"已设置 Webhook（{wh.get('url')}），长轮询前会自动 deleteWebhook", warn=True))
    else:
        checks.append(_checks(True, "Webhook 状态", "未设置 Webhook，适合长轮询"))

    _, upd_data, _ = http_json(
        f"https://api.telegram.org/bot{token}/getUpdates",
        method="POST",
        body={"limit": 1, "timeout": 0},
        timeout=10,
    )
    if upd_data and upd_data.get("ok"):
        checks.append(_checks(True, "getUpdates", "可正常轮询收消息"))
    else:
        detail = str((upd_data or {}).get("description") or "getUpdates 失败")[:200]
        checks.append(_checks(False, "getUpdates", detail))
        return False, checks, "Token 有效但无法轮询消息"

    target = str(test_target or "").strip()
    allowed = cfg.get("allowed_chat_ids") or []
    if not target and allowed:
        target = str(allowed[0])

    if send_test and target:
        test_text = "统领 · 社交接入连通性测试 ✓"
        _, send_data, send_err = http_json(
            f"https://api.telegram.org/bot{token}/sendMessage",
            method="POST",
            body={"chat_id": target, "text": test_text},
            timeout=15,
        )
        if send_data and send_data.get("ok"):
            checks.append(_checks(True, "发送测试消息", f"已向 Chat {target} 发送"))
        else:
            detail = str((send_data or {}).get("description") or send_err)[:200]
            checks.append(_checks(False, "发送测试消息", detail))
            return False, checks, "连接正常但测试消息发送失败（请确认 Chat ID 且已与 Bot 对话过）"

    return True, checks, "Telegram 配置有效，可以接入"


def test_dingtalk(cfg: Dict[str, Any], *, send_test: bool = False, **_kw: Any) -> Tuple[bool, List[Check], str]:
    checks: List[Check] = []
    app_key = str(cfg.get("app_key") or cfg.get("client_id") or "").strip()
    app_secret = str(cfg.get("app_secret") or cfg.get("client_secret") or "").strip()
    webhook_url = str(cfg.get("webhook_url") or "").strip()

    if app_key and app_secret:
        if "…" in app_secret or app_secret == "****":
            checks.append(_checks(False, "AppSecret", "请重新粘贴完整的 Client Secret（页面加载的是脱敏值，不能用于测试）"))
            return False, checks, "AppSecret 不完整，请重新填写完整密钥"

        _, data, err = http_json(
            "https://api.dingtalk.com/v1.0/oauth2/accessToken",
            method="POST",
            body={"appKey": app_key, "appSecret": app_secret},
            timeout=15,
        )
        if data and data.get("accessToken"):
            expire = data.get("expireIn") or "?"
            checks.append(_checks(True, "AppKey / AppSecret", f"accessToken 获取成功（{expire}s）"))
        else:
            detail = str((data or {}).get("message") or (data or {}).get("errmsg") or err)[:200]
            checks.append(_checks(False, "AppKey / AppSecret", detail or "OAuth 失败"))
            return False, checks, "钉钉 AppKey / AppSecret 无效"

        try:
            import dingtalk_stream  # noqa: F401

            checks.append(_checks(True, "dingtalk-stream", "已安装，可使用 Stream 模式收消息"))
        except ImportError:
            from tongling_web.deps import ensure_dingtalk_stream

            if ensure_dingtalk_stream():
                checks.append(_checks(True, "dingtalk-stream", "已自动安装，Stream 模式可用"))
            else:
                checks.append(
                    _checks(
                        True,
                        "dingtalk-stream",
                        "未安装且自动安装失败，保存并启动时会重试；或重启服务后重试",
                        warn=True,
                    )
                )
    elif webhook_url:
        checks.append(_checks(True, "Stream 凭证", "未配置 AppKey，将仅使用 HTTP 回调 + sessionWebhook", warn=True))
    else:
        checks.append(_checks(False, "凭证", "请填写 AppKey/AppSecret，或至少配置 HTTP 回调"))
        return False, checks, "缺少钉钉凭证"

    if webhook_url:
        if send_test:
            _, wh_data, wh_err = http_json(
                webhook_url,
                method="POST",
                body={"msgtype": "text", "text": {"content": "统领 · 社交接入连通性测试 ✓"}},
                timeout=15,
            )
            if wh_data is not None and int(wh_data.get("errcode", -1)) == 0:
                checks.append(_checks(True, "备用 Webhook", "测试消息已发送"))
            else:
                detail = str((wh_data or {}).get("errmsg") or wh_err)[:200]
                checks.append(_checks(False, "备用 Webhook", detail or "发送失败"))
        else:
            checks.append(_checks(True, "备用 Webhook", "已配置（可勾选「发送测试消息」验证）"))
    else:
        checks.append(_checks(True, "备用 Webhook", "未配置（Stream/HTTP 回调回复走 sessionWebhook，可不填）"))

    return True, checks, "钉钉配置有效，请确认机器人/应用已发布并在群内可用"


def test_qq(cfg: Dict[str, Any], **_kw: Any) -> Tuple[bool, List[Check], str]:
    checks: List[Check] = []
    api_base = str(cfg.get("onebot_http_url") or "http://127.0.0.1:3000").rstrip("/")
    token = str(cfg.get("access_token") or "").strip()

    if not api_base:
        checks.append(_checks(False, "OneBot HTTP", "未填写 API 地址"))
        return False, checks, "请填写 OneBot HTTP API 地址"

    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    url = append_access_token(f"{api_base}/get_login_info", token)
    _, data, err = http_json(url, method="POST", body={}, headers=headers, timeout=10)
    if data is None:
        checks.append(_checks(False, "OneBot HTTP", f"无法连接 {api_base}：{err[:200]}"))
        return False, checks, "无法连接 NapCat/OneBot HTTP API，请确认服务已启动"

    if data.get("status") == "ok" or data.get("retcode") == 0:
        info = data.get("data") or {}
        nick = info.get("nickname") or info.get("user_id") or "已登录"
        checks.append(_checks(True, "登录状态", str(nick)))
    else:
        detail = str(data.get("message") or data.get("wording") or data)[:200]
        checks.append(_checks(False, "登录状态", detail))
        return False, checks, "OneBot API 可达但登录信息异常"

    _, status_data, _ = http_json(
        append_access_token(f"{api_base}/get_status", token),
        method="POST",
        body={},
        headers=headers,
        timeout=10,
    )
    if status_data and (status_data.get("status") == "ok" or status_data.get("retcode") == 0):
        checks.append(_checks(True, "get_status", "HTTP API 调用正常"))
    else:
        checks.append(_checks(True, "get_status", "get_login_info 已通过（get_status 可选）", warn=True))

    if token:
        checks.append(_checks(True, "Access Token", "已配置鉴权"))
    else:
        checks.append(_checks(True, "Access Token", "未配置（与 NapCat 未启用 Token 时一致）", warn=True))

    checks.append(_checks(True, "反向 HTTP", "请在 NapCat 将事件上报地址设为页面显示的 Webhook URL"))
    return True, checks, "QQ/OneBot 配置有效，请确认反向 HTTP 上报已配置"


TESTERS = {
    "telegram": test_telegram,
    "dingtalk": test_dingtalk,
    "qq": test_qq,
}


def test_platform(
    platform: str,
    plat_cfg: Dict[str, Any] | None = None,
    *,
    send_test: bool = False,
    test_target: str = "",
) -> Dict[str, Any]:
    name = str(platform or "").strip().lower()
    fn = TESTERS.get(name)
    if not fn:
        return {"success": False, "platform": name, "error": f"未知平台: {platform}", "checks": []}

    merged = merge_platform_config(name, plat_cfg or {})
    try:
        ok, checks, message = fn(merged, send_test=send_test, test_target=test_target)
    except Exception as exc:
        return {
            "success": False,
            "platform": name,
            "message": str(exc)[:300],
            "checks": [_checks(False, "异常", str(exc)[:200])],
        }

    return {
        "success": ok,
        "platform": name,
        "message": message,
        "checks": checks,
    }
