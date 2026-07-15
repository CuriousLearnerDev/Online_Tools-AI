import time
import threading
import logging
import re as _re
import subprocess
import traceback
import os
import json
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime
from wcwidth import wcswidth as _wcswidth
import server_core.config_core as config_core
from server_core.process_manager import ProcessManager
from server_core.modern_visual_engine import ModernVisualEngine

_ANSI = _re.compile(r'\x1B[@-_][0-?]*[ -/]*[@-~]')
_BOX_WIDTH = 66  # visible columns between the two │ borders


def _box_row(content_with_ansi: str) -> str:
    C = ModernVisualEngine.COLORS
    visible = _ANSI.sub('', content_with_ansi)
    w = _wcswidth(visible)
    if w < 0:
        w = len(visible)
    padding = ' ' * (_BOX_WIDTH - w)
    return f"{C['MATRIX_GREEN']}{C['BOLD']}│{C['RESET']}{content_with_ansi}{padding}{C['MATRIX_GREEN']}{C['BOLD']}│{C['RESET']}"

# Global telemetry collector
from server_core.telemetry_collector import TelemetryCollector
telemetry = TelemetryCollector()

logger = logging.getLogger(__name__)
COMMAND_TIMEOUT = config_core.get("COMMAND_TIMEOUT", 300)  # Default to 5 minutes if not set

_INJECT_PATHS_LOCK = threading.Lock()
_INJECTED_TOOL_PATHS = None  # lazy cache: list[str]

def _resolve_tools_config_path() -> Optional[Path]:
    """
    Try likely locations for tools_config.json.
    Supports both standalone CE repo and outer launcher layout.
    """
    here = Path(__file__).resolve()
    repo_root = here.parents[1]           # .../hexstrike-ai-community-edition-master
    storage_root = repo_root.parent        # .../storage
    workspace_root = storage_root.parent   # .../<workspace>
    candidates = [
        repo_root / "storage" / "tools_config.json",
        storage_root / "tools_config.json",
        workspace_root / "storage" / "tools_config.json",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None

def _compute_injected_tool_paths() -> list[str]:
    cfg = _resolve_tools_config_path()
    if not cfg:
        return []
    try:
        with open(cfg, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return []

    tools = data.get("tools", {}) if isinstance(data, dict) else {}
    if not isinstance(tools, dict):
        return []

    repo_root = Path(__file__).resolve().parents[1]
    storage_root = repo_root.parent
    workspace_root = storage_root.parent
    roots = [workspace_root, repo_root, storage_root]

    ordered = []
    seen = set()
    for _, info in tools.items():
        if not isinstance(info, dict):
            continue
        rel_path = (info.get("path") or "").strip()
        if not rel_path:
            continue
        resolved = None
        rel = Path(rel_path)
        if rel.is_absolute():
            if rel.exists():
                resolved = rel
        else:
            for r in roots:
                cand = (r / rel).resolve()
                if cand.exists():
                    resolved = cand
                    break
        if not resolved:
            continue
        pdir = resolved if resolved.is_dir() else resolved.parent
        sval = str(pdir)
        if sval not in seen:
            seen.add(sval)
            ordered.append(sval)
    return ordered

def _get_injected_tool_paths() -> list[str]:
    global _INJECTED_TOOL_PATHS
    if _INJECTED_TOOL_PATHS is not None:
        return _INJECTED_TOOL_PATHS
    with _INJECT_PATHS_LOCK:
        if _INJECTED_TOOL_PATHS is None:
            _INJECTED_TOOL_PATHS = _compute_injected_tool_paths()
    return _INJECTED_TOOL_PATHS

class EnhancedCommandExecutor:
    """Enhanced command executor with caching, progress tracking, and better output handling"""

    def __init__(self, command: str, timeout: int = COMMAND_TIMEOUT):
        self.command = command
        self.timeout = timeout
        self.process = None
        self.stdout_data = ""
        self.stderr_data = ""
        self._stdout_chunks: list = []
        self._stderr_chunks: list = []
        self.stdout_thread = None
        self.stderr_thread = None
        self.return_code = None
        self.timed_out = False
        self.start_time = None
        self.end_time = None

    def _read_stdout(self):
        """Thread function to continuously read and display stdout"""
        if not self.process or not self.process.stdout:
            return
        try:
            for line in iter(self.process.stdout.readline, ''):
                if line:
                    self._stdout_chunks.append(line)
                    # Real-time output display
                    logger.info(f"📤 STDOUT: {line.strip()}")
        except Exception as e:
            logger.error(f"Error reading stdout: {e}")
        finally:
            self.stdout_data = "".join(self._stdout_chunks)

    def _read_stderr(self):
        """Thread function to continuously read and display stderr"""
        if not self.process or not self.process.stderr:
            return
        try:
            for line in iter(self.process.stderr.readline, ''):
                if line:
                    self._stderr_chunks.append(line)
                    # Real-time error output display
                    logger.warning(f"📥 STDERR: {line.strip()}")
        except Exception as e:
            logger.error(f"Error reading stderr: {e}")
        finally:
            self.stderr_data = "".join(self._stderr_chunks)

    def _show_progress(self):
        """Show enhanced progress indication for long-running commands"""
        progress_chars = ModernVisualEngine.PROGRESS_STYLES['dots']
        start = time.time()
        i = 0
        while self.process and self.process.poll() is None:
            elapsed = time.time() - start
            char = progress_chars[i % len(progress_chars)]

            # Calculate progress percentage (rough estimate)
            progress_percent = min((elapsed / self.timeout) * 100, 99.9)
            progress_fraction = progress_percent / 100

            # Calculate ETA
            eta = 0
            if progress_percent > 5:  # Only show ETA after 5% progress
                eta = ((elapsed / progress_percent) * 100) - elapsed

            # Calculate speed
            bytes_processed = sum(len(c) for c in self._stdout_chunks) + sum(len(c) for c in self._stderr_chunks)
            speed = f"{bytes_processed/elapsed:.0f} B/s" if elapsed > 0 else "0 B/s"

            # Update process manager with progress
            ProcessManager.update_process_progress(
                self.process.pid,
                progress_fraction,
                f"Running for {elapsed:.1f}s",
                bytes_processed
            )

            # Create beautiful progress bar using ModernVisualEngine
            progress_bar = ModernVisualEngine.render_progress_bar(
                progress_fraction,
                width=30,
                style='cyber',
                label=f"⚡ PROGRESS {char}",
                eta=eta,
                speed=speed
            )

            logger.info(f"{progress_bar} | {elapsed:.1f}s | PID: {self.process.pid}")
            time.sleep(0.8)
            i += 1
            if elapsed > self.timeout:
                break

    def execute(self) -> Dict[str, Any]:
        """Execute the command with enhanced monitoring and output"""
        # Reset per-execution state so the instance can be reused across calls
        self.stdout_data = ""
        self.stderr_data = ""
        self._stdout_chunks = []
        self._stderr_chunks = []
        self.process = None
        self.stdout_thread = None
        self.stderr_thread = None
        self.return_code = None
        self.timed_out = False
        self.end_time = None
        self.start_time = time.time()

        logger.info(f"🚀 EXECUTING: {self.command}")
        logger.info(f"⏱️  TIMEOUT: {self.timeout}s | PID: Starting...")

        try:
            # stdin=DEVNULL: many CLIs (e.g. Go httpx) treat inherited stdin as a pipe and wait for
            # URLs forever when not a TTY — works in an interactive console but hangs under Flask/MCP.
            # shell=True pipelines (echo x | tool) still get stdin from the inner pipe, not this handle.
            self.process = subprocess.Popen(
                self.command,
                shell=True,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                # Injected only for AI server subprocesses; does not modify system/global env.
                env=(lambda base: (
                    {**base, "PATH": os.pathsep.join(_get_injected_tool_paths() + [base.get("PATH", "")])}
                    if _get_injected_tool_paths() else base
                ))(os.environ.copy()),
            )

            pid = self.process.pid
            logger.info(f"🆔 PROCESS: PID {pid} started")

            # Register process with ProcessManager (v5.0 enhancement)
            ProcessManager.register_process(pid, self.command, self.process)

            # Start threads to read output continuously
            self.stdout_thread = threading.Thread(target=self._read_stdout)
            self.stderr_thread = threading.Thread(target=self._read_stderr)
            self.stdout_thread.daemon = True
            self.stderr_thread.daemon = True
            self.stdout_thread.start()
            self.stderr_thread.start()

            # Start progress tracking only for commands expected to run > 2 s
            if self.timeout > 2:
                progress_thread = threading.Thread(target=self._show_progress)
                progress_thread.daemon = True
                progress_thread.start()

            # Wait for the process to complete or timeout
            try:
                self.return_code = self.process.wait(timeout=self.timeout)
                self.end_time = time.time()

                # Process completed, join the threads
                self.stdout_thread.join(timeout=1)
                self.stderr_thread.join(timeout=1)

                execution_time = self.end_time - self.start_time

                # Cleanup process from registry (v5.0 enhancement)
                ProcessManager.cleanup_process(pid)

                if self.return_code == 0:
                    logger.info(f"✅ SUCCESS: Command completed | Exit Code: {self.return_code} | Duration: {execution_time:.2f}s")
                    telemetry.record_execution(True, execution_time)
                else:
                    logger.warning(f"⚠️  WARNING: Command completed with errors | Exit Code: {self.return_code} | Duration: {execution_time:.2f}s")
                    telemetry.record_execution(False, execution_time)

            except subprocess.TimeoutExpired:
                self.end_time = time.time()
                execution_time = self.end_time - self.start_time

                # Process timed out but we might have partial results
                self.timed_out = True
                logger.warning(f"⏰ TIMEOUT: Command timed out after {self.timeout}s | Terminating PID {self.process.pid}")

                # Try to terminate gracefully first
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    # Force kill if it doesn't terminate
                    logger.error(f"🔪 FORCE KILL: Process {self.process.pid} not responding to termination")
                    self.process.kill()

                self.return_code = -1
                telemetry.record_execution(False, execution_time)

            # Always consider it a success if we have output, even with timeout
            success = True if self.timed_out and (self.stdout_data or self.stderr_data) else (self.return_code == 0)

            # Log enhanced final results with summary using ModernVisualEngine
            output_size = len(self.stdout_data) + len(self.stderr_data)
            execution_time = self.end_time - self.start_time if self.end_time else 0

            # Create status summary
            status_icon = "✅" if success else "❌"
            status_color = ModernVisualEngine.COLORS['MATRIX_GREEN'] if success else ModernVisualEngine.COLORS['HACKER_RED']
            timeout_status = f" {ModernVisualEngine.COLORS['WARNING']}[TIMEOUT]{ModernVisualEngine.COLORS['RESET']}" if self.timed_out else ""

            # Create beautiful results summary
            C = ModernVisualEngine.COLORS
            _hr = '─' * _BOX_WIDTH
            box_lines = [
                f"{C['MATRIX_GREEN']}{C['BOLD']}╭{_hr}╮{C['RESET']}",
                _box_row(f" {status_color}📊 FINAL RESULTS {status_icon}{C['RESET']}"),
                f"{C['MATRIX_GREEN']}{C['BOLD']}├{_hr}┤{C['RESET']}",
                _box_row(f" {C['NEON_BLUE']}🚀 Command:{C['RESET']} {self.command[:55]}{'...' if len(self.command) > 55 else ''}"),
                _box_row(f" {C['CYBER_ORANGE']}⏰ Duration:{C['RESET']} {execution_time:.2f}s{timeout_status}"),
                _box_row(f" {C['WARNING']}📊 Output Size:{C['RESET']} {output_size} bytes"),
                _box_row(f" {C['ELECTRIC_PURPLE']}🔢 Exit Code:{C['RESET']} {self.return_code}"),
                _box_row(f" {status_color}📈 Status:{C['RESET']} {'SUCCESS' if success else 'FAILED'} | Cached: Yes"),
                f"{C['MATRIX_GREEN']}{C['BOLD']}╰{_hr}╯{C['RESET']}",
            ]
            print('\n'.join(box_lines), flush=True)

            return {
                "stdout": self.stdout_data,
                "stderr": self.stderr_data,
                "return_code": self.return_code,
                "success": success,
                "timed_out": self.timed_out,
                "partial_results": self.timed_out and (self.stdout_data or self.stderr_data),
                "execution_time": self.end_time - self.start_time if self.end_time else 0,
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            self.end_time = time.time()
            execution_time = self.end_time - self.start_time if self.start_time else 0

            logger.error(f"💥 ERROR: Command execution failed: {str(e)}")
            logger.error(f"🔍 TRACEBACK: {traceback.format_exc()}")
            telemetry.record_execution(False, execution_time)

            return {
                "stdout": self.stdout_data,
                "stderr": f"Error executing command: {str(e)}\n{self.stderr_data}",
                "return_code": -1,
                "success": False,
                "timed_out": False,
                "partial_results": bool(self.stdout_data or self.stderr_data),
                "execution_time": execution_time,
                "timestamp": datetime.now().isoformat()
            }
