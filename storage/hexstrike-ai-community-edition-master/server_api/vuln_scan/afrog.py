# server_api/vuln_scan/afrog.py
from flask import Blueprint, request, jsonify
import logging
import os
import queue
import shutil
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

from server_core.process_manager import ProcessManager

logger = logging.getLogger(__name__)


def _flush_complete_lines(buffer: str) -> str:
    """Split buffer on newlines, log each non-empty line; return remaining tail."""
    while "\n" in buffer:
        line, buffer = buffer.split("\n", 1)
        s = line.replace("\r", " ").strip()
        if s:
            logger.info("[afrog] %s", s)
    return buffer


def _run_afrog_streaming(cmd: list[str], scan_timeout: int) -> subprocess.CompletedProcess:
    """
    Run afrog with stdout/stderr merged, stream lines to the server log as they arrive.
    Registers the subprocess with ProcessManager so /api/processes/dashboard (任务监控) lists it.
    """
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
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
                logger.info("[afrog] %s", snippet)
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
            logger.info("[afrog] %s", tail_final)
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
                logger.debug("afrog ProcessManager.cleanup_process failed", exc_info=True)


api_vuln_scan_afrog_bp = Blueprint("api_vuln_scan_afrog", __name__)


def _resolve_afrog_bin() -> str:
    """
    Resolve afrog executable.

    Order: AFROG_BIN, PATH (afrog / afrog.exe), then common paths next to the repo.
    """
    env_bin = (os.environ.get("AFROG_BIN") or "").strip()
    if env_bin:
        return env_bin

    for name in ("afrog", "afrog.exe"):
        p = shutil.which(name)
        if p:
            return p

    # server_api/vuln_scan/afrog.py -> parents[2] = hexstrike project root
    repo_root = Path(__file__).resolve().parents[2]
    candidates = [
        repo_root / "storage" / "afrog" / "afrog.exe",
        repo_root / "storage" / "afrog" / "afrog",
        repo_root.parent / "storage" / "afrog" / "afrog.exe",
        repo_root.parent / "storage" / "afrog" / "afrog",
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return ""


@api_vuln_scan_afrog_bp.route("/api/tools/afrog", methods=["POST"])
def afrog():
    """
    Run afrog PoC vulnerability scanner against one or more targets.

    JSON body:
      - target (required): URL(s) or host(s), comma-separated for multiple (-t)
      - url: alias for target
      - severity (optional): -S / -severity (info,low,medium,high,critical,unknown)
      - search (optional): -s keyword filter for PoCs
      - rate_limit (optional): -rl requests per second (0 = omit, use afrog default)
      - concurrency (optional): -c parallel PoCs (0 = omit)
      - proxy (optional): -proxy
      - port_scan (optional): enable -ps (port pre-scan before PoC)
      - ports (optional): -p e.g. 80,443,8080 or \"all\" (with port_scan)
      - skip_host_discovery (optional): -Pn (with port scan flows)
      - output_html (optional): -o HTML report path
      - output_json (optional): -j JSON path (no full req/resp)
      - json_all (optional): -ja JSON with full results
      - disable_output_html (optional): -doh
      - silent (optional): -silent
      - stop_on_first_vuln (optional): -vsb
      - timeout (optional): -timeout seconds for HTTP (afrog flag)
      - scan_timeout (optional): subprocess wall-clock cap in seconds (default 3600)
      - additional_args (optional): extra CLI tokens (space-separated)
    """
    afrog_bin = _resolve_afrog_bin()
    if not afrog_bin:
        return (
            jsonify(
                {
                    "success": False,
                    "error": "未找到 afrog 可执行文件（加入 PATH、使用 venv，或设置环境变量 AFROG_BIN）",
                }
            ),
            400,
        )

    params = request.json or {}
    target = (params.get("target") or params.get("url") or "").strip()
    severity = (params.get("severity") or "").strip()
    search = (params.get("search") or "").strip()
    rate_limit = params.get("rate_limit", 0)
    concurrency = params.get("concurrency", 0)
    proxy = (params.get("proxy") or "").strip()
    port_scan = bool(params.get("port_scan", False))
    ports = (params.get("ports") or "").strip()
    skip_host_discovery = bool(params.get("skip_host_discovery", False))
    output_html = (params.get("output_html") or "").strip()
    output_json = (params.get("output_json") or "").strip()
    json_all = (params.get("json_all") or "").strip()
    disable_output_html = bool(params.get("disable_output_html", False))
    silent = bool(params.get("silent", False))
    stop_on_first_vuln = bool(params.get("stop_on_first_vuln", False))
    timeout_flag = params.get("timeout", None)
    scan_timeout = int(params.get("scan_timeout") or 3600)
    additional_args = (params.get("additional_args") or "").strip()

    if not target:
        return (
            jsonify({"success": False, "error": "target 必填，例如 https://example.com 或 1.2.3.4"}),
            400,
        )

    cmd: list[str] = [afrog_bin, "-t", target]

    if severity:
        cmd += ["-S", severity]
    if search:
        cmd += ["-s", search]
    if rate_limit is not None and int(rate_limit) > 0:
        cmd += ["-rl", str(int(rate_limit))]
    if concurrency is not None and int(concurrency) > 0:
        cmd += ["-c", str(int(concurrency))]
    if proxy:
        cmd += ["-proxy", proxy]
    if port_scan:
        cmd.append("-ps")
    if ports:
        cmd += ["-p", ports]
    if skip_host_discovery:
        cmd.append("-Pn")
    if output_html:
        cmd += ["-o", output_html]
    if output_json:
        cmd += ["-j", output_json]
    if json_all:
        cmd += ["-ja", json_all]
    if disable_output_html:
        cmd.append("-doh")
    if silent:
        cmd.append("-silent")
    if stop_on_first_vuln:
        cmd.append("-vsb")
    if timeout_flag is not None and str(timeout_flag).strip() != "":
        cmd += ["-timeout", str(int(timeout_flag))]
    if additional_args:
        cmd += additional_args.split()

    logger.info("运行 afrog: %s", " ".join(cmd))

    started = time.monotonic()
    try:
        result = _run_afrog_streaming(cmd, max(1, scan_timeout))
    except subprocess.TimeoutExpired:
        return jsonify(
            {
                "success": False,
                "stdout": "",
                "stderr": f"afrog timeout (>{scan_timeout}s)",
                "return_code": 124,
                "timed_out": True,
                "partial_results": False,
                "execution_time": round(time.monotonic() - started, 4),
                "timestamp": datetime.now().isoformat(),
                "command": cmd,
            }
        ), 500
    except Exception as e:
        logger.exception("afrog 执行异常")
        return jsonify(
            {
                "success": False,
                "stdout": "",
                "stderr": f"afrog execution failed: {e}",
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
