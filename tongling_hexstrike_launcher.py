#!/usr/bin/env python3
"""
统领 HexStrike 启动器：挂载 tongling_web 门户 + Claude Web 终端 WebSocket。
"""

from __future__ import annotations

import argparse
import os
import sys


def _resolve_roots():
    if getattr(sys, "frozen", False):
        tongling_root = os.path.dirname(os.path.abspath(sys.executable))
    else:
        tongling_root = os.path.dirname(os.path.abspath(__file__))
    hexstrike_root = os.path.join(
        tongling_root, "storage", "hexstrike-ai-community-edition-master"
    )
    return tongling_root, hexstrike_root


def main():
    parser = argparse.ArgumentParser(description="Run HexStrike API Server with Tongling Web portal")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("HEXSTRIKE_PORT", 15038)),
        help="Port for the API server",
    )
    parser.add_argument(
        "--host",
        type=str,
        default=os.environ.get("HEXSTRIKE_HOST", "0.0.0.0"),
        help="Host for the API server (0.0.0.0 = LAN/mobile access)",
    )
    parser.add_argument(
        "--launch-mode",
        type=str,
        default=os.environ.get("TONGLING_LAUNCH_MODE", "web-standalone"),
        choices=("desktop", "web-standalone"),
        help="desktop=统领 main.py；web-standalone=独立 Web / Docker",
    )
    args = parser.parse_args()

    tongling_root, hexstrike_root = _resolve_roots()
    os.environ["TONGLING_ROOT"] = tongling_root
    os.environ["TONGLING_LAUNCH_MODE"] = args.launch_mode
    os.environ["HEXSTRIKE_PORT"] = str(args.port)
    os.environ["HEXSTRIKE_HOST"] = args.host

    if tongling_root not in sys.path:
        sys.path.insert(0, tongling_root)
    if hexstrike_root not in sys.path:
        sys.path.insert(0, hexstrike_root)

    os.chdir(hexstrike_root)

    from tongling_web.deps import ensure_pty, ensure_simple_websocket  # noqa: E402

    ensure_pty()
    ensure_simple_websocket()

    from hexstrike_server import app, DEBUG_MODE  # noqa: E402
    from tongling_web.auth import bind_api_token_from_web, ensure_web_token, portal_url  # noqa: E402
    from tongling_web.hexstrike_sync import register_hexstrike_tongling_api  # noqa: E402
    from tongling_web.routes import register_tongling_web  # noqa: E402
    from tongling_web.ws_server import start_ws_server  # noqa: E402

    token = ensure_web_token(tongling_root)
    bind_api_token_from_web(token)
    register_hexstrike_tongling_api(app, hexstrike_root)
    register_tongling_web(app, tongling_root)
    # 始终启动独立 WS 端口 (API+100)；同端口 Flask 路由作为单端口映射时的备用
    start_ws_server(args.port, host=args.host)

    local_url = portal_url(f"http://127.0.0.1:{args.port}", token)
    print("\n" + "=" * 60)
    print("[统领 Web] 访问令牌 (保存在 storage/.tongling_web_token，重启后不变):")
    print(f"  {token}")
    print(f"[统领 Web] 本机控制台: {local_url}")
    if args.host == "0.0.0.0":
        print(f"[统领 Web] 外网/手机请仅访问 /tongling/ 并附加: ?token={token}")
        print("[统领 Web] 根路径 / 已关闭，不再提供 HexStrike 默认界面")
    print("=" * 60 + "\n")

    debug = args.debug or DEBUG_MODE
    app.run(host=args.host, port=args.port, debug=debug)


if __name__ == "__main__":
    main()
