"""Quote one argument for shell=True (cmd.exe on Windows, shlex on POSIX)."""
from __future__ import annotations

import os
import shlex
import subprocess


def quote_shell_arg(s: str) -> str:
    text = str(s)
    if os.name == "nt":
        return subprocess.list2cmdline([text])
    return shlex.quote(text)
