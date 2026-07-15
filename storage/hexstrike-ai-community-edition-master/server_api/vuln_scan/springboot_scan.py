# server_api/vuln_scan/springboot_scan.py
from __future__ import annotations

import logging
import os
import queue
import shlex
import subprocess
import threading
import time
from datetime import datetime

from flask import Blueprint, jsonify, request

from server_core.process_manager import ProcessManager
from server_core.springboot_scan_paths import resolve_springboot_scan_launch

logger = logging.getLogger(__name__)

_LOG_PREFIX = "[springboot-scan]"


def _flush_lines(buffer: str) -> str:
    while "\n" in buffer:
        line, buffer = buffer.split("\n", 1)
        s = line.replace("\r", " ").strip()
        if s:
            logger.info("%s %s", _LOG_PREFIX, s)
    return buffer


def _run_streaming(
    cmd: list[str],
    scan_timeout: int,
    cwd: str | None = None,
) -> subprocess.CompletedProcess:
    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        env=os.environ,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.stdout is not None
    registered_pid: int | None = None
    try:
        if proc.pid is not None:
            cmd_display = " ".join(cmd)
            if len(cmd_display) > 400:
                cmd_display = cmd_display[:400] + "…"
            ProcessManager.register_process(proc.pid, cmd_display, proc)
            registered_pid = proc.pid

        out_q: queue.Queue[str | None] = queue.Queue()

        def reader() -> None:
            try:
                while True:
                    block = proc.stdout.read(4096)
                    if not block:
                        break
                    out_q.put(block)
            finally:
                out_q.put(None)
                try:
                    proc.stdout.close()
                except OSError:
                    pass

        threading.Thread(target=reader, daemon=True).start()

        parts: list[str] = []
        carry = ""
        last_tail_log = 0.0
        last_dashboard_update = 0.0
        deadline = time.monotonic() + max(1, int(scan_timeout))

        while True:
            wait_budget = deadline - time.monotonic()
            if wait_budget <= 0:
                proc.kill()
                try:
                    proc.wait(20)
                except Exception:
                    pass
                raise subprocess.TimeoutExpired(cmd, scan_timeout, None)

            try:
                chunk = out_q.get(timeout=min(1.0, max(0.05, wait_budget)))
            except queue.Empty:
                chunk = "__tick__"

            if chunk is None:
                break
            if chunk != "__tick__":
                parts.append(chunk)
                carry = _flush_lines(carry + chunk)

            now = time.monotonic()
            tail = carry.replace("\r", " ").strip()
            if tail and now - last_tail_log >= 1.5:
                snippet = tail[-500:] if len(tail) > 500 else tail
                logger.info("%s %s", _LOG_PREFIX, snippet)
                last_tail_log = now
            if registered_pid is not None and tail and now - last_dashboard_update >= 2.0:
                ProcessManager.update_process_progress(
                    registered_pid,
                    0.0,
                    last_output=tail[-200:],
                )
                last_dashboard_update = now

        carry = _flush_lines(carry)
        if carry.strip():
            tail_final = carry.replace("\r", " ").strip()
            logger.info("%s %s", _LOG_PREFIX, tail_final)
            if registered_pid is not None:
                ProcessManager.update_process_progress(
                    registered_pid, 0.0, last_output=tail_final[-200:]
                )

        rc = proc.wait(timeout=60)
        text = "".join(parts)
        return subprocess.CompletedProcess(cmd, rc, text, "")
    finally:
        if registered_pid is not None:
            try:
                ProcessManager.cleanup_process(registered_pid)
            except Exception:
                logger.debug("springboot-scan ProcessManager.cleanup_process failed", exc_info=True)


def _strip(s: object) -> str:
    if s is None:
        return ""
    return str(s).strip()


def _truthy(v: object) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes", "on", "y")
    return bool(v)


def _add_kv(cmd: list[str], flag: str, value: str) -> None:
    v = _strip(value)
    if v:
        cmd.extend([flag, v])


def _append_cli_args(cmd: list[str], params: dict) -> None:
    # AI / run_tool 常传 target，与多数 HexStrike 工具一致；映射为 SpringBoot-Scan 的 -u
    url = _strip(
        params.get("url")
        or params.get("u")
        or params.get("target")
        or params.get("host")
    )
    url_file = _strip(params.get("url_file") or params.get("uf") or params.get("urlfile"))
    vul = _strip(params.get("vul") or params.get("v"))
    vul_file = _strip(params.get("vul_file") or params.get("vf") or params.get("vulfile"))
    dump = _strip(params.get("dump") or params.get("d"))
    dump_file = _strip(params.get("dump_file") or params.get("df") or params.get("dumpfile"))
    proxy = _strip(params.get("proxy") or params.get("p"))
    zoomeye = _strip(params.get("zoomeye") or params.get("z"))
    fofa = _strip(params.get("fofa") or params.get("f"))
    hunter = _strip(params.get("hunter") or params.get("y"))
    newheader = _strip(params.get("newheader") or params.get("t") or params.get("header_file"))
    cookie = _strip(params.get("cookie") or params.get("c"))

    _add_kv(cmd, "-u", url)
    _add_kv(cmd, "-uf", url_file)
    _add_kv(cmd, "-v", vul)
    _add_kv(cmd, "-vf", vul_file)
    _add_kv(cmd, "-d", dump)
    _add_kv(cmd, "-df", dump_file)
    _add_kv(cmd, "-p", proxy)
    _add_kv(cmd, "-z", zoomeye)
    _add_kv(cmd, "-f", fofa)
    _add_kv(cmd, "-y", hunter)
    _add_kv(cmd, "-t", newheader)
    _add_kv(cmd, "-c", cookie)


def _has_primary_action(params: dict) -> bool:
    if _truthy(params.get("help")) or _truthy(params.get("show_help")):
        return True
    keys = (
        "url",
        "u",
        "target",
        "host",
        "url_file",
        "uf",
        "urlfile",
        "vul",
        "v",
        "vul_file",
        "vf",
        "vulfile",
        "dump",
        "d",
        "dump_file",
        "df",
        "dumpfile",
        "proxy",
        "p",
        "zoomeye",
        "z",
        "fofa",
        "f",
        "hunter",
        "y",
        "newheader",
        "t",
        "header_file",
    )
    return any(_strip(params.get(k)) for k in keys)


api_vuln_scan_springboot_scan_bp = Blueprint("api_vuln_scan_springboot_scan", __name__)


@api_vuln_scan_springboot_scan_bp.route("/api/tools/springboot-scan", methods=["POST"])
def springboot_scan():
    """
    SpringBoot-Scan：SpringBoot 信息泄露、漏洞利用与敏感文件下载等。

    定位顺序：SPRINGBOOT_SCAN_SCRIPT → PATH 中的 SpringBoot-Scan → tools_config。
    非 .py 直接执行；仅 .py 时使用 python（可设 SPRINGBOOT_SCAN_PYTHON）。

    JSON 与 CLI 对应：url / target→-u（AI 常用 target），url_file→-uf，其余同工具 -h 帮助。
    help 或 show_help 为 true 时仅追加 -h（等价终端 SpringBoot-Scan -h）。
    至少提供上述一种模式、help，或 additional_args。
    """
    launch = resolve_springboot_scan_launch()
    if not launch:
        return (
            jsonify(
                {
                    "success": False,
                    "error": "未找到 SpringBoot-Scan：设置 SPRINGBOOT_SCAN_SCRIPT、将 SpringBoot-Scan 加入 PATH，或在 tools_config 中配置",
                }
            ),
            400,
        )

    cmd, work_dir = launch
    cmd = list(cmd)

    params = request.json or {}
    additional_args = _strip(params.get("additional_args"))
    if not _has_primary_action(params) and not additional_args:
        return (
            jsonify(
                {
                    "success": False,
                    "error": "请至少提供 url 或 target(-u)、其它模式参数、help=true，或 additional_args（如 -h）",
                }
            ),
            400,
        )
    if _truthy(params.get("help")) or _truthy(params.get("show_help")):
        cmd.append("-h")
    else:
        _append_cli_args(cmd, params)
        if additional_args:
            cmd += shlex.split(additional_args, posix=os.name == "posix")

    scan_timeout = int(params.get("scan_timeout") or 3600)

    logger.info("运行 springboot-scan: cwd=%s %s", work_dir, " ".join(cmd))

    started = time.monotonic()
    try:
        result = _run_streaming(cmd, max(1, scan_timeout), cwd=work_dir)
    except subprocess.TimeoutExpired:
        return (
            jsonify(
                {
                    "success": False,
                    "stdout": "",
                    "stderr": f"springboot-scan timeout (>{scan_timeout}s)",
                    "return_code": 124,
                    "timed_out": True,
                    "partial_results": False,
                    "execution_time": round(time.monotonic() - started, 4),
                    "timestamp": datetime.now().isoformat(),
                    "command": cmd,
                }
            ),
            500,
        )
    except Exception as e:
        logger.exception("springboot-scan 执行异常")
        return (
            jsonify(
                {
                    "success": False,
                    "stdout": "",
                    "stderr": f"springboot-scan execution failed: {e}",
                    "return_code": 1,
                    "timed_out": False,
                    "partial_results": False,
                    "execution_time": round(time.monotonic() - started, 4),
                    "timestamp": datetime.now().isoformat(),
                    "command": cmd,
                }
            ),
            500,
        )

    return jsonify(
        {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "return_code": result.returncode,
            "timed_out": False,
            "partial_results": False,
            "execution_time": round(time.monotonic() - started, 4),
            "timestamp": datetime.now().isoformat(),
            "command": cmd,
        }
    )
