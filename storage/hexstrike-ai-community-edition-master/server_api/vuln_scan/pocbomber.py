# server_api/vuln_scan/pocbomber.py
from __future__ import annotations

import logging
import os
import queue
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

from flask import Blueprint, jsonify, request

from server_core.process_manager import ProcessManager
from server_core.pocbomber_paths import resolve_pocbomber_python, resolve_pocbomber_script_path

logger = logging.getLogger(__name__)


def _flush_complete_lines(buffer: str) -> str:
    while "\n" in buffer:
        line, buffer = buffer.split("\n", 1)
        s = line.replace("\r", " ").strip()
        if s:
            logger.info("[pocbomber] %s", s)
    return buffer


def _run_pocbomber_streaming(
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
                carry = _flush_complete_lines(carry + chunk)

            now = time.monotonic()
            tail = carry.replace("\r", " ").strip()
            if tail and now - last_tail_log >= 1.5:
                snippet = tail[-500:] if len(tail) > 500 else tail
                logger.info("[pocbomber] %s", snippet)
                last_tail_log = now
            if registered_pid is not None and tail and now - last_dashboard_update >= 2.0:
                ProcessManager.update_process_progress(
                    registered_pid,
                    0.0,
                    last_output=tail[-200:],
                )
                last_dashboard_update = now

        carry = _flush_complete_lines(carry)
        if carry.strip():
            tail_final = carry.replace("\r", " ").strip()
            logger.info("[pocbomber] %s", tail_final)
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
                logger.debug("pocbomber ProcessManager.cleanup_process failed", exc_info=True)


api_vuln_scan_pocbomber_bp = Blueprint("api_vuln_scan_pocbomber", __name__)


@api_vuln_scan_pocbomber_bp.route("/api/tools/pocbomber", methods=["POST"])
def pocbomber():
    """
    Run PocBomber (Python script) for PoC/exp batch scanning.

    JSON:
      - show: if true, run --show only (lists PoC/exp info)
      - target / url: single target URL (-u)
      - file: URL list file (-f)
      - output: report path (-o)
      - poc: one or more comma-separated poc filenames (--poc)
      - thread: thread pool size (-t), 0 = omit (tool default 30)
      - attack: --attack (exp mode; use only on authorized targets)
      - dnslog: --dnslog
      - scan_timeout: wall-clock seconds (default 3600)
      - additional_args: extra CLI tokens (space-separated)
    """
    py = resolve_pocbomber_python()
    script = resolve_pocbomber_script_path()
    if not py:
        return (
            jsonify({"success": False, "error": "未找到 Python（设置 POCBOMBER_PYTHON 或将 python 加入 PATH）"}),
            400,
        )
    if not script:
        return (
            jsonify(
                {
                    "success": False,
                    "error": "未找到 pocbomber.py（设置 POCBOMBER_SCRIPT 或放到 storage/pocbomber/pocbomber.py）",
                }
            ),
            400,
        )

    script_abs = Path(script).resolve()
    work_dir = str(script_abs.parent)
    script_leaf = script_abs.name

    params = request.json or {}
    show = bool(params.get("show", False))
    url = (params.get("target") or params.get("url") or "").strip()
    url_file = (params.get("file") or "").strip()
    output = (params.get("output") or "").strip()
    poc = (params.get("poc") or "").strip()
    thread = int(params.get("thread") or 0)
    attack = bool(params.get("attack", False))
    dnslog = bool(params.get("dnslog", False))
    scan_timeout = int(params.get("scan_timeout") or 3600)
    additional_args = (params.get("additional_args") or "").strip()

    # 与统领终端别名一致：在脚本目录下执行，仅传脚本文件名，便于加载 poc 目录
    cmd: list[str] = [py, script_leaf]

    if show:
        cmd.append("--show")
    else:
        if not url and not url_file:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "请提供 target/url 或 file（批量），或设置 show=true 查看 PoC 列表",
                    }
                ),
                400,
            )
        if url:
            cmd += ["-u", url]
        if url_file:
            cmd += ["-f", url_file]
        if output:
            cmd += ["-o", output]
        if poc:
            cmd += ["--poc", poc]
        if thread > 0:
            cmd += ["-t", str(thread)]
        if attack:
            cmd.append("--attack")
        if dnslog:
            cmd.append("--dnslog")

    if additional_args:
        cmd += additional_args.split()

    logger.info("运行 pocbomber: cwd=%s %s", work_dir, " ".join(cmd))

    started = time.monotonic()
    try:
        result = _run_pocbomber_streaming(cmd, max(1, scan_timeout), cwd=work_dir)
    except subprocess.TimeoutExpired:
        return jsonify(
            {
                "success": False,
                "stdout": "",
                "stderr": f"pocbomber timeout (>{scan_timeout}s)",
                "return_code": 124,
                "timed_out": True,
                "partial_results": False,
                "execution_time": round(time.monotonic() - started, 4),
                "timestamp": datetime.now().isoformat(),
                "command": cmd,
            }
        ), 500
    except Exception as e:
        logger.exception("pocbomber 执行异常")
        return jsonify(
            {
                "success": False,
                "stdout": "",
                "stderr": f"pocbomber execution failed: {e}",
                "return_code": 1,
                "timed_out": False,
                "partial_results": False,
                "execution_time": round(time.monotonic() - started, 4),
                "timestamp": datetime.now().isoformat(),
                "command": cmd,
            }
        ), 500

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
