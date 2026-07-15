"""NPS npc 内网穿透 — 将当前 Web 端口映射到 NPS 服务端。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from typing import Any, Dict, Optional, Tuple

try:
    import psutil
except ImportError:
    psutil = None  # type: ignore


def _tongling_root() -> str:
    return os.environ.get("TONGLING_ROOT") or os.path.dirname(os.path.dirname(__file__))


def nps_dir(root: str | None = None) -> str:
    return os.path.join(root or _tongling_root(), "storage", "nps")


def npc_binary(root: str | None = None) -> str:
    d = nps_dir(root)
    name = "npc.exe" if sys.platform == "win32" else "npc"
    return os.path.join(d, name)


def npc_ready(root: str | None = None) -> bool:
    return os.path.isfile(npc_binary(root))


def _prefs_path(root: str | None = None) -> str:
    return os.path.join(nps_dir(root), "tunnel_prefs.json")


def _state_path(root: str | None = None) -> str:
    return os.path.join(nps_dir(root), "tunnel_state.json")


def _config_path(root: str | None = None) -> str:
    conf_dir = os.path.join(nps_dir(root), "conf")
    os.makedirs(conf_dir, exist_ok=True)
    return os.path.join(conf_dir, "tongling_web.conf")


def _log_path(root: str | None = None) -> str:
    return os.path.join(nps_dir(root), "tunnel_npc.log")


def load_prefs(root: str | None = None) -> Dict[str, Any]:
    path = _prefs_path(root)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_prefs(prefs: Dict[str, Any], root: str | None = None) -> None:
    path = _prefs_path(root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(prefs, f, ensure_ascii=False, indent=2)


def _load_state(root: str | None = None) -> Dict[str, Any]:
    path = _state_path(root)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_state(state: Dict[str, Any], root: str | None = None) -> None:
    path = _state_path(root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def _clear_state(root: str | None = None) -> None:
    path = _state_path(root)
    try:
        if os.path.isfile(path):
            os.remove(path)
    except OSError:
        pass


def _pid_alive(pid: int) -> bool:
    if not pid or pid <= 0:
        return False
    if psutil is not None:
        try:
            proc = psutil.Process(pid)
            return proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _terminate_pid(pid: int) -> None:
    if not pid or pid <= 0:
        return
    if psutil is not None:
        try:
            proc = psutil.Process(pid)
            for child in proc.children(recursive=True):
                try:
                    child.terminate()
                except Exception:
                    pass
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except Exception:
                proc.kill()
            return
        except Exception:
            pass
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                timeout=15,
                check=False,
            )
        else:
            os.kill(pid, 15)
    except Exception:
        pass


def build_npc_argv(*, server_addr: str, vkey: str, tunnel_type: str = "tcp") -> list[str]:
    """无配置文件模式：隧道在 NPS Web 管理端配置。"""
    return [
        f"-server={server_addr.strip()}",
        f"-vkey={vkey.strip()}",
        f"-type={(tunnel_type or 'tcp').strip()}",
    ]


def npc_command_preview(*, server_addr: str, vkey: str, tunnel_type: str = "tcp", root: str | None = None) -> str:
    exe = npc_binary(root)
    name = os.path.basename(exe)
    args = build_npc_argv(server_addr=server_addr, vkey=vkey, tunnel_type=tunnel_type)
    return f"{name} {' '.join(args)}"


def read_log_tail(max_chars: int = 4000, root: str | None = None) -> str:
    path = _log_path(root)
    if not os.path.isfile(path):
        return ""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            data = f.read()
        return data[-max_chars:] if len(data) > max_chars else data
    except Exception:
        return ""


def tunnel_status(*, api_port: int, root: str | None = None) -> Dict[str, Any]:
    root = root or _tongling_root()
    prefs = load_prefs(root)
    state = _load_state(root)
    pid = int(state.get("pid") or 0)
    running = _pid_alive(pid)
    if state and not running:
        _clear_state(root)
        state = {}
    server_addr = str(prefs.get("server_addr") or "")
    tunnel_type = str(prefs.get("tunnel_type") or "tcp")
    vkey = str(prefs.get("vkey") or "")
    cmd_preview = ""
    if server_addr and vkey:
        cmd_preview = npc_command_preview(
            server_addr=server_addr,
            vkey=vkey,
            tunnel_type=tunnel_type,
            root=root,
        )
    return {
        "ready": npc_ready(root),
        "npc_path": npc_binary(root),
        "running": running,
        "pid": pid if running else None,
        "started_at": state.get("started_at"),
        "api_port": int(api_port),
        "local_target": f"127.0.0.1:{int(api_port)}",
        "prefs": prefs,
        "command_preview": cmd_preview,
        "log_tail": read_log_tail(root=root) if running or os.path.isfile(_log_path(root)) else "",
        "toollist_key": "nps",
    }


def start_tunnel(*, api_port: int, prefs: Optional[Dict[str, Any]] = None, root: str | None = None) -> Tuple[bool, str]:
    root = root or _tongling_root()
    if not npc_ready(root):
        return False, "未找到 npc，请在统领工具箱下载 nps 资源包到 storage\\nps"

    status = tunnel_status(api_port=api_port, root=root)
    if status.get("running"):
        return True, "穿透已在运行"

    data = dict(load_prefs(root))
    if prefs:
        data.update({k: v for k, v in prefs.items() if v is not None})
    server_addr = str(data.get("server_addr") or "").strip()
    vkey = str(data.get("vkey") or "").strip()
    tunnel_type = str(data.get("tunnel_type") or "tcp").strip() or "tcp"
    if not server_addr or not vkey:
        return False, "请填写 NPS 服务端地址与客户端密钥 (vkey)"
    save_prefs(data, root)

    exe = npc_binary(root)
    log_path = _log_path(root)
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    log_fh = open(log_path, "a", encoding="utf-8")
    cmd = [exe] + build_npc_argv(server_addr=server_addr, vkey=vkey, tunnel_type=tunnel_type)
    log_fh.write(
        f"\n--- start {time.strftime('%Y-%m-%d %H:%M:%S')} local_web={api_port} cmd={' '.join(cmd[1:])} ---\n"
    )
    log_fh.flush()
    kwargs: Dict[str, Any] = {
        "cwd": nps_dir(root),
        "stdout": log_fh,
        "stderr": subprocess.STDOUT,
        "stdin": subprocess.DEVNULL,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    try:
        proc = subprocess.Popen(cmd, **kwargs)
    except Exception as exc:
        log_fh.close()
        return False, f"启动 npc 失败: {exc}"

    time.sleep(0.6)
    if proc.poll() is not None:
        log_fh.close()
        tail = read_log_tail(800, root=root)
        return False, f"npc 已退出 (code={proc.returncode})" + (f"\n{tail}" if tail else "")

    _save_state(
        {
            "pid": proc.pid,
            "started_at": time.time(),
            "command": " ".join(cmd),
            "local_port": int(api_port),
        },
        root=root,
    )
    msg = (
        f"已启动 npc (PID {proc.pid})。请在 NPS Web 管理端配置 TCP 隧道，"
        f"目标指向 127.0.0.1:{int(api_port)}"
    )
    return True, msg


def stop_tunnel(*, root: str | None = None) -> Tuple[bool, str]:
    root = root or _tongling_root()
    state = _load_state(root)
    pid = int(state.get("pid") or 0)
    if not pid:
        return True, "穿透未运行"
    _terminate_pid(pid)
    _clear_state(root)
    log_path = _log_path(root)
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"--- stop {time.strftime('%Y-%m-%d %H:%M:%S')} pid={pid} ---\n")
    except Exception:
        pass
    return True, "已停止 npc 穿透"
