"""Web PTY 桥接 — Windows: pywinpty；Linux/macOS: stdlib pty + select。"""

from __future__ import annotations

import os
import select
import signal
import struct
import sys
import threading
import time
from typing import Callable, List, Optional, Tuple

_WINPTY = False
PtyProcess = None  # type: ignore
Backend = None  # type: ignore
_WinptyError = Exception

if os.name == "nt":
    try:
        from winpty import PtyProcess as _WinPtyProcess
        from winpty.enums import Backend as _WinBackend

        PtyProcess = _WinPtyProcess
        Backend = _WinBackend
        _WINPTY = True
        try:
            from pywinpty import WinptyError as _WinptyError
        except ImportError:
            _WinptyError = type("_WinptyError", (Exception,), {})
    except ImportError:
        pass

_PTY_IO_ERRORS = (EOFError, OSError, BrokenPipeError, ConnectionResetError)
if _WINPTY:
    _PTY_IO_ERRORS = _PTY_IO_ERRORS + (_WinptyError,)


class _PosixPtyProcess:
    """POSIX PTY 包装，接口与 winpty.PtyProcess 对齐。"""

    def __init__(self, master_fd: int, pid: int) -> None:
        self._master = master_fd
        self._pid = pid
        self._exitstatus: Optional[int] = None
        self.fd = master_fd

    @classmethod
    def spawn(cls, argv: List[str], *, cwd: str, env: dict, dimensions: tuple) -> "_PosixPtyProcess":
        import fcntl
        import pty
        import termios

        cols, rows = dimensions
        master, slave = pty.openpty()

        def _set_winsize(fd: int, r: int, c: int) -> None:
            winsize = struct.pack("HHHH", r, c, 0, 0)
            fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)

        _set_winsize(slave, rows, cols)

        pid = os.fork()
        if pid == 0:
            try:
                os.close(master)
                os.setsid()
                os.dup2(slave, 0)
                os.dup2(slave, 1)
                os.dup2(slave, 2)
                if slave > 2:
                    os.close(slave)
                if cwd:
                    os.chdir(cwd)
                os.execvpe(argv[0], argv, env)
            except Exception:
                os._exit(127)
        os.close(slave)
        return cls(master, pid)

    def fileno(self) -> int:
        return self._master

    def isalive(self) -> bool:
        if self._exitstatus is not None:
            return False
        pid, status = os.waitpid(self._pid, os.WNOHANG)
        if pid == self._pid:
            self._exitstatus = self._status_to_code(status)
            return False
        return True

    @staticmethod
    def _status_to_code(status: int) -> int:
        if hasattr(os, "waitstatus_to_exitcode"):
            try:
                return int(os.waitstatus_to_exitcode(status))
            except Exception:
                pass
        if os.WIFEXITED(status):
            return int(os.WEXITSTATUS(status))
        if os.WIFSIGNALED(status):
            return 128 + int(os.WTERMSIG(status))
        return int(status)

    def read(self, size: int) -> str:
        try:
            data = os.read(self._master, size)
        except OSError:
            return ""
        if not data:
            return ""
        return data.decode("utf-8", errors="replace")

    def write(self, data: str | bytes) -> None:
        if isinstance(data, str):
            data = data.encode("utf-8", errors="replace")
        os.write(self._master, data)

    def setwinsize(self, rows: int, cols: int) -> None:
        import fcntl
        import termios

        winsize = struct.pack("HHHH", rows, cols, 0, 0)
        fcntl.ioctl(self._master, termios.TIOCSWINSZ, winsize)

    def terminate(self, force: bool = False) -> None:
        sig = signal.SIGKILL if force else signal.SIGTERM
        try:
            os.kill(self._pid, sig)
        except ProcessLookupError:
            pass

    def wait(self) -> None:
        while True:
            pid, status = os.waitpid(self._pid, 0)
            if pid == self._pid:
                self._exitstatus = self._status_to_code(status)
                break

    def close(self, force: bool = True) -> None:
        try:
            os.close(self._master)
        except OSError:
            pass

    @property
    def exitstatus(self) -> Optional[int]:
        return self._exitstatus


def pty_available() -> bool:
    if os.name == "nt":
        return _WINPTY and PtyProcess is not None
    return hasattr(os, "fork") and sys.platform != "win32"


def wrap_argv_for_pty(argv: List[str]) -> List[str]:
    if not argv or os.name != "nt":
        return list(argv)
    exe = os.path.basename(argv[0]).lower()
    if exe in ("cmd.exe", "powershell.exe", "pwsh.exe", "wt.exe", "claude.exe", "claude"):
        return list(argv)
    if exe.endswith((".cmd", ".bat")):
        return ["cmd.exe", "/q", "/c"] + list(argv)
    return list(argv)


def _spawn_pty(argv: List[str], cwd: str, env: dict, dimensions: tuple):
    if os.name == "nt":
        backends = []
        if Backend is not None:
            backends.extend([Backend.ConPTY, Backend.WinPTY])
        backends.append(None)
        last_err = None
        for backend in backends:
            try:
                kw = {"cwd": cwd, "env": env, "dimensions": dimensions}
                if backend is not None:
                    kw["backend"] = backend
                return PtyProcess.spawn(argv, **kw)
            except Exception as exc:
                last_err = exc
        raise last_err or RuntimeError("PTY 启动失败")
    return _PosixPtyProcess.spawn(argv, cwd=cwd, env=env, dimensions=dimensions)


class PtySession:
    """单个 WebSocket 终端会话。"""

    def __init__(
        self,
        on_output: Callable[[str], None],
        on_exit: Callable[[int, str], None],
    ):
        self._on_output = on_output
        self._on_exit = on_exit
        self._pty = None
        self._reader: Optional[threading.Thread] = None
        self._closed = False
        self._subst_drive: Optional[str] = None
        self._cols = 120
        self._rows = 40

    @property
    def running(self) -> bool:
        return bool(self._pty and self._pty.isalive())

    def start(self, spec: dict) -> Tuple[bool, str]:
        if not pty_available():
            hint = "Windows 需安装 pywinpty；Linux/macOS 需 Python 支持 os.fork"
            return False, f"缺少 PTY 支持，无法启动 Web 终端（{hint}）"
        argv = spec.get("argv") or []
        if not argv:
            return False, "启动命令为空"

        cwd = spec.get("cwd") or ""
        env = dict(spec.get("env") or os.environ)
        try:
            from cc_visual.claude_launcher import sanitize_stale_ssl_cert_env

            sanitize_stale_ssl_cert_env(env)
        except ImportError:
            pass
        self._subst_drive = spec.get("subst_drive")
        self._cols = int(spec.get("cols") or 120)
        self._rows = int(spec.get("rows") or 40)

        env.setdefault("TERM", "xterm-256color")
        env.setdefault("COLORTERM", "truecolor")
        env["COLUMNS"] = str(self._cols)
        env["LINES"] = str(self._rows)

        pty_argv = wrap_argv_for_pty(list(argv))
        try:
            self._pty = _spawn_pty(
                pty_argv,
                cwd,
                env,
                (self._cols, self._rows),
            )
        except Exception as exc:
            return False, f"PTY 启动失败: {exc}"

        self._closed = False
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()
        return True, spec.get("cmdline") or " ".join(argv)

    def write(self, data: str | bytes) -> bool:
        if self._closed or not self._pty or data is None:
            return False
        if isinstance(data, str) and not data:
            return False
        try:
            if not self._pty.isalive():
                self.close(notify=True)
                return False
            try:
                self._pty.write(data)
            except (TypeError, UnicodeEncodeError):
                if isinstance(data, str):
                    self._pty.write(data.encode("utf-8"))
                else:
                    raise
            return True
        except _PTY_IO_ERRORS:
            self.close(notify=True)
            return False

    def send_input(self, text: str) -> bool:
        """模拟用户在终端输入一行或多行（与 Web xterm Enter 行为一致）。"""
        payload = (text or "").rstrip("\r\n")
        if not payload:
            return False
        lines = payload.split("\n")
        enter = "\r"
        for line in lines:
            chunk = line if line else " "
            if not self.write(chunk):
                return False
            if not self.write(enter):
                return False
            time.sleep(0.06)
        return True

    def resize(self, cols: int, rows: int) -> None:
        if cols < 20 or rows < 5:
            return
        self._cols, self._rows = cols, rows
        if self._pty and self._pty.isalive():
            try:
                self._pty.setwinsize(rows, cols)
            except Exception:
                pass

    def close(self, notify: bool = False) -> None:
        if self._closed:
            return
        self._closed = True
        code = -1
        if self._pty:
            try:
                if self._pty.isalive():
                    self._pty.terminate(force=False)
                    try:
                        self._pty.wait()
                    except Exception:
                        self._pty.terminate(force=True)
            except Exception:
                pass
            try:
                code = self._pty.exitstatus if self._pty.exitstatus is not None else -1
            except Exception:
                pass
            try:
                self._pty.close(force=True)
            except Exception:
                pass
            self._pty = None

        if self._subst_drive:
            try:
                from cc_visual.claude_launcher import cleanup_subst

                cleanup_subst(self._subst_drive)
            except Exception:
                pass
            self._subst_drive = None

        if notify:
            self._on_exit(int(code), "会话已结束")

    def _read_loop(self) -> None:
        pty = self._pty
        if not pty:
            return
        fd = pty.fileno() if hasattr(pty, "fileno") else getattr(pty, "fd", None)
        while not self._closed and pty.isalive():
            try:
                if fd is not None:
                    ready, _, _ = select.select([fd], [], [], 0.05)
                    if not ready:
                        continue
                chunk = pty.read(16384)
            except EOFError:
                break
            except _PTY_IO_ERRORS:
                if not pty.isalive():
                    break
                continue
            except Exception:
                if not pty.isalive():
                    break
                continue
            if chunk:
                if isinstance(chunk, bytes):
                    chunk = chunk.decode("utf-8", errors="replace")
                self._on_output(chunk)
        self.close(notify=True)
