import os
import sys
import tempfile
from pathlib import Path
from typing import Union


PathLike = Union[str, Path]


def get_runtime_temp_dir(app_name: str = "hexstrike") -> Path:
  """Return a writable temp directory that works on all platforms."""
  base_tmp = Path(tempfile.gettempdir())
  target = base_tmp / app_name
  target.mkdir(parents=True, exist_ok=True)
  return target


def build_temp_path(*parts: PathLike, app_name: str = "hexstrike") -> Path:
  """Build an app-scoped temporary path under the OS temp directory."""
  tmp_root = get_runtime_temp_dir(app_name=app_name)
  for part in parts:
    tmp_root = tmp_root / str(part)
  return tmp_root


def get_python_executable() -> str:
  """Return the current Python executable, with safe fallbacks."""
  if sys.executable:
    return sys.executable

  if os.name == "nt":
    return "py"

  return "python3"
