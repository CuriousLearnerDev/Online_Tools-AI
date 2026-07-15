# core/file_ops.py
from pathlib import Path
import os
import shutil
import tempfile
from typing import Dict, Any, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


def _default_file_ops_base_dir() -> Path:
    """跨平台工作目录：优先环境变量 HEXSTRIKE_FILES_DIR，否则为系统临时目录下的 hexstrike_files。"""
    override = (os.environ.get("HEXSTRIKE_FILES_DIR") or "").strip()
    if override:
        return Path(override)
    return Path(tempfile.gettempdir()) / "hexstrike_files"


# File Operations Manager
class FileOperationsManager:
    """Handle file operations with security and validation"""

    def __init__(self, base_dir: Optional[str] = None):
        self.base_dir = Path(base_dir) if base_dir else _default_file_ops_base_dir()
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.max_file_size = 100 * 1024 * 1024  # 100MB

    def _safe_path(self, filename: str) -> Path:
        """Resolve path and guard against directory traversal."""
        resolved = (self.base_dir / filename).resolve()
        if not resolved.is_relative_to(self.base_dir.resolve()):
            raise ValueError(f"Path traversal attempt detected: {filename!r}")
        return resolved

    def create_file(self, filename: str, content: str, binary: bool = False) -> Dict[str, Any]:
        """Create a file with the specified content"""
        try:
            file_path = self._safe_path(filename)
            file_path.parent.mkdir(parents=True, exist_ok=True)

            if len(content.encode()) > self.max_file_size:
                return {"success": False, "error": f"File size exceeds {self.max_file_size} bytes"}

            mode = "wb" if binary else "w"
            with open(file_path, mode) as f:
                if binary:
                    f.write(content.encode() if isinstance(content, str) else content)
                else:
                    f.write(content)

            logger.info(f"📄 Created file: {filename} ({len(content)} bytes)")
            return {"success": True, "path": str(file_path), "size": len(content)}

        except Exception as e:
            logger.error(f"❌ Error creating file {filename}: {e}")
            return {"success": False, "error": str(e)}

    def modify_file(self, filename: str, content: str, append: bool = False) -> Dict[str, Any]:
        """Modify an existing file"""
        try:
            file_path = self._safe_path(filename)
            if not file_path.exists():
                return {"success": False, "error": "File does not exist"}

            mode = "a" if append else "w"
            with open(file_path, mode) as f:
                f.write(content)

            logger.info(f"✏️  Modified file: {filename}")
            return {"success": True, "path": str(file_path)}

        except Exception as e:
            logger.error(f"❌ Error modifying file {filename}: {e}")
            return {"success": False, "error": str(e)}

    def delete_file(self, filename: str) -> Dict[str, Any]:
        """Delete a file or directory"""
        try:
            file_path = self._safe_path(filename)
            if not file_path.exists():
                return {"success": False, "error": "File does not exist"}

            if file_path.is_dir():
                shutil.rmtree(file_path)
            else:
                file_path.unlink()

            logger.info(f"🗑️  Deleted: {filename}")
            return {"success": True}

        except Exception as e:
            logger.error(f"❌ Error deleting {filename}: {e}")
            return {"success": False, "error": str(e)}

    def list_files(self, directory: str = ".") -> Dict[str, Any]:
        """List files in a directory"""
        try:
            dir_path = self._safe_path(directory)
            if not dir_path.exists():
                return {"success": False, "error": "Directory does not exist"}

            files = []
            for item in dir_path.iterdir():
                files.append({
                    "name": item.name,
                    "type": "directory" if item.is_dir() else "file",
                    "size": item.stat().st_size if item.is_file() else 0,
                    "modified": datetime.fromtimestamp(item.stat().st_mtime).isoformat()
                })

            return {"success": True, "files": files}

        except Exception as e:
            logger.error(f"❌ Error listing files in {directory}: {e}")
            return {"success": False, "error": str(e)}

# Global file operations manager
file_manager = FileOperationsManager()