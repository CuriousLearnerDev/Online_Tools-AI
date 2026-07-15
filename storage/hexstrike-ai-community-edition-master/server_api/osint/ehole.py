# server_api/osint/ehole.py
from flask import Blueprint, request, jsonify
import logging
import subprocess
import shutil
import os
import time
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

api_osint_ehole_bp = Blueprint("api_osint_ehole", __name__)

def _resolve_ehole_bin() -> str:
    """
    Find an executable for EHole.

    Preference order:
    1) Env var EHOLE_BIN
    2) PATH lookup: ehole / EHole_windows_amd64.exe
    3) Known relative location under repo root: storage/EHole/EHole_windows_amd64/
    """
    env_bin = (os.environ.get("EHOLE_BIN") or "").strip()
    if env_bin:
        return env_bin

    for name in ("ehole", "EHole_windows_amd64.exe"):
        p = shutil.which(name)
        if p:
            return p

    # server_api/osint/ehole.py -> osint -> server_api -> repo root
    repo_root = Path(__file__).resolve().parents[2]
    candidates = [
        repo_root / "storage" / "EHole" / "EHole_windows_amd64" / "ehole.exe",
        repo_root / "storage" / "EHole" / "EHole_windows_amd64" / "ehole.bat",
        repo_root / "storage" / "EHole" / "EHole_windows_amd64" / "EHole_windows_amd64.exe",
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return ""


@api_osint_ehole_bp.route("/api/tools/ehole", methods=["POST"])
def ehole():
    """
    EHole 单目标指纹识别（finger -u URL）。

    Request JSON:
      - url (required): 目标 URL，如 https://www.zssnp.top
      - config (optional): --config 路径
      - thread (optional): finger 的 -t/--thread
      - proxy (optional): finger 的 -p/--proxy
      - output (optional): finger 的 -o/--output
      - additional_args (optional): 其它参数（谨慎使用）
    """
    ehole_bin = _resolve_ehole_bin()
    if not ehole_bin:
        return jsonify({"success": False, "error": "未找到 ehole 可执行文件（请设置 PATH 或环境变量 EHOLE_BIN）"}), 400

    params = request.json or {}
    url = (params.get("url") or "").strip()
    config = (params.get("config") or "").strip()
    thread = params.get("thread", None)
    proxy = (params.get("proxy") or "").strip()
    output = (params.get("output") or "").strip()
    additional_args = (params.get("additional_args") or "").strip()

    if not url:
        return jsonify({"success": False, "error": "url 必填，例如 https://www.zssnp.top"}), 400

    # 组装命令
    cmd = [ehole_bin, "finger", "-u", url]
    if config:
        cmd += ["--config", config]
    if thread is not None and str(thread).strip() != "":
        cmd += ["-t", str(thread)]
    if proxy:
        cmd += ["-p", proxy]
    if output:
        cmd += ["-o", output]
    if additional_args:
        # 注意：这里简单 split，复杂情况可以自己在服务器本地改成更严格的解析
        cmd += additional_args.split()

    logger.info("运行 ehole 命令: %s", " ".join(cmd))

    started = time.monotonic()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.TimeoutExpired:
        return jsonify(
            {
                "success": False,
                "stdout": "",
                "stderr": "ehole timeout (>300s)",
                "return_code": 124,
                "timed_out": True,
                "partial_results": False,
                "execution_time": round(time.monotonic() - started, 4),
                "timestamp": datetime.now().isoformat(),
                "command": cmd,
            }
        ), 500
    except Exception as e:
        logger.exception("ehole 执行异常")
        return jsonify(
            {
                "success": False,
                "stdout": "",
                "stderr": f"ehole execution failed: {e}",
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
