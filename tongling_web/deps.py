"""统领 Web 依赖：缺失时尝试用当前/便携 Python 自动 pip 安装。"""

from __future__ import annotations

import logging
import os
import subprocess
import sys

logger = logging.getLogger(__name__)

_ensure_simple_websocket_attempted = False
_ensure_pywinpty_attempted = False
_ensure_dingtalk_stream_attempted = False


def _tongling_root() -> str:
    return os.environ.get("TONGLING_ROOT") or os.path.dirname(os.path.dirname(__file__))


def _pip_python_exe() -> str:
    """用于 pip 安装的 Python；打包 exe 时回退到 storage\\Python311。"""
    if not getattr(sys, "frozen", False):
        return sys.executable
    cand = os.path.join(_tongling_root(), "storage", "Python311", "python.exe")
    if os.path.isfile(cand):
        return cand
    return sys.executable


def _can_pip_with(exe: str) -> bool:
    base = os.path.basename(exe).lower()
    return base in {"python.exe", "python3.exe", "python", "python3"} or base.startswith("python")


def ensure_simple_websocket() -> bool:
    """若未安装 simple-websocket，则自动 pip install；成功返回 True。"""
    global _ensure_simple_websocket_attempted
    try:
        import simple_websocket  # noqa: F401

        return True
    except ImportError:
        pass

    if _ensure_simple_websocket_attempted:
        return False
    _ensure_simple_websocket_attempted = True

    py = _pip_python_exe()
    if not _can_pip_with(py):
        logger.warning(
            "simple-websocket 未安装且无法自动安装（当前解释器非 Python）。"
            "请在 storage\\Python311 中执行: python.exe -m pip install simple-websocket"
        )
        return False

    logger.info("simple-websocket 未安装，正在自动安装 …")
    try:
        proc = subprocess.run(
            [py, "-m", "pip", "install", "simple-websocket", "-q"],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except Exception as exc:
        logger.warning("simple-websocket 自动安装异常: %s", exc)
        return False

    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        logger.warning(
            "simple-websocket 自动安装失败 (exit %s): %s",
            proc.returncode,
            detail[:500] if detail else "无输出",
        )
        return False

    try:
        import simple_websocket  # noqa: F401

        logger.info("simple-websocket 已自动安装，Claude 终端将优先使用同端口 WebSocket")
        return True
    except ImportError:
        logger.warning(
            "simple-websocket 安装完成但当前进程仍无法导入；"
            "请重启统领 Web 服务后重试，或手动: %s -m pip install simple-websocket",
            py,
        )
        return False


def _reload_pty_bridge() -> None:
    """pip 安装 pywinpty 后刷新 pty_bridge 探测结果。"""
    try:
        import importlib

        import tongling_web.pty_bridge as pb

        importlib.reload(pb)
    except Exception as exc:
        logger.debug("pty_bridge reload: %s", exc)


def ensure_pywinpty() -> bool:
    """Windows：若未安装 pywinpty/winpty，则自动 pip install；成功返回 True。"""
    global _ensure_pywinpty_attempted
    if os.name != "nt":
        return True
    try:
        from winpty import PtyProcess  # noqa: F401

        return True
    except ImportError:
        pass

    if _ensure_pywinpty_attempted:
        return False
    _ensure_pywinpty_attempted = True

    py = _pip_python_exe()
    if not _can_pip_with(py):
        logger.warning(
            "pywinpty 未安装且无法自动安装（当前解释器非 Python）。"
            "请在 storage\\Python311 中执行: python.exe -m pip install pywinpty"
        )
        return False

    logger.info("pywinpty 未安装，正在自动安装 …")
    try:
        proc = subprocess.run(
            [py, "-m", "pip", "install", "pywinpty", "-q"],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except Exception as exc:
        logger.warning("pywinpty 自动安装异常: %s", exc)
        return False

    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        logger.warning(
            "pywinpty 自动安装失败 (exit %s): %s",
            proc.returncode,
            detail[:500] if detail else "无输出",
        )
        return False

    _reload_pty_bridge()
    try:
        from winpty import PtyProcess  # noqa: F401

        logger.info("pywinpty 已自动安装，Claude Web 终端可用")
        return True
    except ImportError:
        logger.warning(
            "pywinpty 安装完成但当前进程仍无法导入；"
            "请重启统领 Web 服务后重试，或手动: %s -m pip install pywinpty",
            py,
        )
        return False


def ensure_pty() -> bool:
    """确保 Web 终端 PTY 可用：Windows 安装 pywinpty，Unix 使用 stdlib pty。"""
    if os.name != "nt":
        return True
    return ensure_pywinpty()


def ensure_dingtalk_stream() -> bool:
    """若未安装 dingtalk-stream，则自动 pip install；成功返回 True。"""
    global _ensure_dingtalk_stream_attempted
    try:
        import dingtalk_stream  # noqa: F401

        return True
    except ImportError:
        pass

    if _ensure_dingtalk_stream_attempted:
        return False
    _ensure_dingtalk_stream_attempted = True

    py = _pip_python_exe()
    if not _can_pip_with(py):
        logger.warning(
            "dingtalk-stream 未安装且无法自动安装（当前解释器非 Python）。"
            "请在 storage\\Python311 中执行: python.exe -m pip install dingtalk-stream"
        )
        return False

    logger.info("dingtalk-stream 未安装，正在自动安装 …")
    try:
        proc = subprocess.run(
            [py, "-m", "pip", "install", "dingtalk-stream", "-q"],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except Exception as exc:
        logger.warning("dingtalk-stream 自动安装异常: %s", exc)
        return False

    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        logger.warning(
            "dingtalk-stream 自动安装失败 (exit %s): %s",
            proc.returncode,
            detail[:500] if detail else "无输出",
        )
        return False

    try:
        import dingtalk_stream  # noqa: F401

        logger.info("dingtalk-stream 已自动安装，钉钉 Stream 模式可用")
        return True
    except ImportError:
        logger.warning(
            "dingtalk-stream 安装完成但当前进程仍无法导入；"
            "请重启统领 Web 服务后重试，或手动: %s -m pip install dingtalk-stream",
            py,
        )
        return False
