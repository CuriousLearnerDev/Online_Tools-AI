# server_api/net_scan/fscan.py
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

from server_core.fscan_paths import resolve_fscan_bin
from server_core.process_manager import ProcessManager

logger = logging.getLogger(__name__)

api_net_scan_fscan_bp = Blueprint("api_net_scan_fscan", __name__)


def _flush_fscan_lines(buffer: str) -> str:
    while "\n" in buffer:
        line, buffer = buffer.split("\n", 1)
        s = line.replace("\r", " ").strip()
        if s:
            logger.info("[fscan] %s", s)
    return buffer


def _run_fscan_streaming(cmd: list[str], scan_timeout: int) -> subprocess.CompletedProcess:
    """Run fscan with merged stdout/stderr, stream lines to server log and task dashboard."""
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=os.environ,
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
                carry = _flush_fscan_lines(carry + chunk)

            now = time.monotonic()
            tail = carry.replace("\r", " ").strip()
            if tail and now - last_tail_log >= 1.5:
                snippet = tail[-500:] if len(tail) > 500 else tail
                logger.info("[fscan] %s", snippet)
                last_tail_log = now
            if registered_pid is not None and tail and now - last_dashboard_update >= 2.0:
                ProcessManager.update_process_progress(
                    registered_pid,
                    0.0,
                    last_output=tail[-200:],
                )
                last_dashboard_update = now

        carry = _flush_fscan_lines(carry)
        if carry.strip():
            tail_final = carry.replace("\r", " ").strip()
            logger.info("[fscan] %s", tail_final)
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
                logger.debug("fscan ProcessManager.cleanup_process failed", exc_info=True)


def _add_kv(cmd: list[str], flag: str, value: str) -> None:
    if value is not None and str(value).strip() != "":
        cmd.extend([flag, str(value).strip()])


def _add_int(cmd: list[str], flag: str, value: object, *, omit_zero: bool = True) -> None:
    try:
        v = int(value)
    except (TypeError, ValueError):
        return
    if omit_zero and v <= 0:
        return
    cmd.extend([flag, str(v)])


def _build_fscan_cmd(params: dict) -> list[str] | None:
    exe = resolve_fscan_bin()
    if not exe:
        return None
    cmd: list[str] = [exe]

    host = (params.get("target") or params.get("h") or params.get("host") or "").strip()
    url = (params.get("url") or params.get("u") or "").strip()
    host_file = (params.get("host_file") or params.get("hf") or "").strip()
    url_file = (params.get("url_file") or params.get("uf") or "").strip()
    local = bool(params.get("local", False))

    if not host and not url and not host_file and not url_file and not local:
        return []

    if host:
        cmd.extend(["-h", host])
    if url:
        cmd.extend(["-u", url])
    if host_file:
        cmd.extend(["-hf", host_file])
    if url_file:
        cmd.extend(["-uf", url_file])
    if local:
        cmd.append("-local")

    _add_kv(cmd, "-p", params.get("ports") or params.get("p"))
    _add_kv(cmd, "-m", params.get("modules") or params.get("m"))
    _add_kv(cmd, "-o", params.get("output") or params.get("o"))
    _add_kv(cmd, "-f", params.get("output_format") or params.get("f"))
    _add_kv(cmd, "-cookie", params.get("cookie"))
    _add_kv(cmd, "-domain", params.get("domain"))
    _add_kv(cmd, "-eh", params.get("eh"))
    _add_kv(cmd, "-ep", params.get("ep"))
    _add_kv(cmd, "-lang", params.get("lang"))
    _add_kv(cmd, "-log", params.get("log"))
    _add_kv(cmd, "-pocname", params.get("pocname"))
    _add_kv(cmd, "-pocpath", params.get("pocpath"))
    _add_kv(cmd, "-proxy", params.get("proxy"))
    _add_kv(cmd, "-socks5", params.get("socks5"))
    _add_kv(cmd, "-user", params.get("user"))
    _add_kv(cmd, "-pwd", params.get("pwd"))
    _add_kv(cmd, "-usera", params.get("usera"))
    _add_kv(cmd, "-pwda", params.get("pwda"))
    _add_kv(cmd, "-userf", params.get("userf"))
    _add_kv(cmd, "-pwdf", params.get("pwdf"))
    _add_kv(cmd, "-pf", params.get("pf"))
    _add_kv(cmd, "-hash", params.get("hash"))
    _add_kv(cmd, "-hashf", params.get("hashf"))
    _add_kv(cmd, "-sshkey", params.get("sshkey"))
    _add_kv(cmd, "-api", params.get("api"))
    _add_kv(cmd, "-secret", params.get("secret"))

    _add_int(cmd, "-gt", params.get("gt"))
    _add_int(cmd, "-mt", params.get("mt"))
    _add_int(cmd, "-t", params.get("threads") or params.get("t"))
    _add_int(cmd, "-time", params.get("time"))
    _add_int(cmd, "-num", params.get("num"))
    _add_int(cmd, "-top", params.get("top"))
    _add_int(cmd, "-retry", params.get("retry"))
    _add_int(cmd, "-wt", params.get("wt"))

    bool_flags = [
        ("dns", "-dns"),
        ("full", "-full"),
        ("fingerprint", "-fingerprint"),
        ("no", "-no"),
        ("nobr", "-nobr"),
        ("nocolor", "-nocolor"),
        ("nopoc", "-nopoc"),
        ("noredis", "-noredis"),
        ("np", "-np"),
        ("pg", "-pg"),
        ("ping", "-ping"),
        ("silent", "-silent"),
        ("slow", "-slow"),
        ("sp", "-sp"),
    ]
    for key, flg in bool_flags:
        if bool(params.get(key, False)):
            cmd.append(flg)

    extra = (params.get("additional_args") or "").strip()
    if extra:
        cmd += shlex.split(extra, posix=os.name == "posix")

    return cmd


@api_net_scan_fscan_bp.route("/api/tools/fscan", methods=["POST"])
def fscan():
    """
    Fscan 内网综合扫描。至少提供 target(-h)、url(-u)、host_file(-hf)、url_file(-uf) 之一，或 local=true。
    运行过程中将标准输出按行写入日志前缀 [fscan]，并登记任务监控。
    """
    params = request.json or {}
    scan_timeout = int(params.get("scan_timeout") or 7200)

    cmd = _build_fscan_cmd(params)
    if cmd is None:
        return (
            jsonify(
                {
                    "success": False,
                    "error": "未找到 fscan（PATH、fscan.exe、FSCAN_BIN 或 storage/tools_config.json 中 fscan 项）",
                }
            ),
            400,
        )
    if not cmd:
        return (
            jsonify(
                {
                    "success": False,
                    "error": "请提供 target(-h)、url(-u)、host_file(-hf)、url_file(-uf) 之一，或 local=true",
                }
            ),
            400,
        )

    logger.info("运行 fscan: %s", " ".join(cmd))
    started = time.monotonic()
    try:
        result = _run_fscan_streaming(cmd, max(1, scan_timeout))
    except subprocess.TimeoutExpired:
        return jsonify(
            {
                "success": False,
                "stdout": "",
                "stderr": f"fscan timeout (>{scan_timeout}s)",
                "return_code": 124,
                "timed_out": True,
                "partial_results": False,
                "execution_time": round(time.monotonic() - started, 4),
                "timestamp": datetime.now().isoformat(),
                "command": cmd,
            }
        ), 500
    except Exception as e:
        logger.exception("fscan 执行异常")
        return jsonify(
            {
                "success": False,
                "stdout": "",
                "stderr": str(e),
                "return_code": 1,
                "timed_out": False,
                "partial_results": False,
                "execution_time": round(time.monotonic() - started, 4),
                "timestamp": datetime.now().isoformat(),
                "command": cmd,
            }
        ), 500

    elapsed = round(time.monotonic() - started, 4)
    return jsonify(
        {
            "success": result.returncode == 0,
            "stdout": result.stdout or "",
            "stderr": result.stderr or "",
            "return_code": result.returncode,
            "timed_out": False,
            "partial_results": False,
            "execution_time": elapsed,
            "timestamp": datetime.now().isoformat(),
            "command": cmd,
        }
    )
