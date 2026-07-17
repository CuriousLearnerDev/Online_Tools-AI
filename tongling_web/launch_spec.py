"""Claude 启动参数准备（Web 终端共用）。"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional, Tuple


def _as_bool(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    s = str(value).strip().lower()
    if s in ("0", "false", "no", "off", ""):
        return False
    if s in ("1", "true", "yes", "on"):
        return True
    return default


def prepare_claude_spec(body: Dict[str, Any]) -> Tuple[bool, str, Optional[dict]]:
    tongling_root = os.environ.get("TONGLING_ROOT") or os.path.dirname(os.path.dirname(__file__))
    if tongling_root not in __import__("sys").path:
        __import__("sys").path.insert(0, tongling_root)

    from cc_visual.claude_launcher import prepare_launch
    from cc_visual.claude_options import LaunchOptions

    workdir = body.get("workdir") or ""
    proxy = str(body.get("proxy") or "")
    initial_prompt = str(body.get("initial_prompt") or "")
    cols = int(body.get("cols") or 120)
    rows = int(body.get("rows") or 40)

    opts = LaunchOptions()
    if body.get("model"):
        opts.model = str(body["model"])
    if body.get("permission_mode"):
        opts.permission_mode = str(body["permission_mode"])

    # 默认跳过权限确认；前端可传 skip_permissions=false 关闭
    if "skip_permissions" in body:
        opts.skip_permissions = _as_bool(body.get("skip_permissions"), True)

    # 默认不拉 @latest；前端可传 npx_latest=true 始终拉取最新版
    prefer_latest = _as_bool(body.get("npx_latest"), False) if "npx_latest" in body else False

    launch_mode = str(body.get("launch_mode") or "interactive").strip()
    if launch_mode in ("continue", "resume", "print"):
        opts.mode = launch_mode
    if launch_mode == "resume" and body.get("resume_id"):
        opts.resume_id = str(body["resume_id"]).strip()
    if body.get("fork_session"):
        opts.fork_session = True

    ok, msg, spec = prepare_launch(
        proxy=proxy,
        work_dir=workdir,
        initial_prompt=initial_prompt,
        ascii_cwd=True,
        options=opts,
        prefer_latest=prefer_latest,
    )
    if not ok or not spec:
        return False, msg or "无法准备启动", None
    spec["cols"] = cols
    spec["rows"] = rows
    return True, msg, spec
