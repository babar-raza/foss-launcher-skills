"""Filesystem helper utilities.

Ported from aspose.org scripts/pipeline/core/fs.py.
No aspose-specific paths in this module.
"""
import pathlib
import shutil
from typing import List


def ensure_dir(path: pathlib.Path) -> pathlib.Path:
    """Create directory and parents if they do not exist. Return path."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def atomic_write(path: pathlib.Path, content: str, encoding: str = "utf-8") -> None:
    """Write content to a temp file then rename atomically."""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(content, encoding=encoding)
    shutil.move(str(tmp), str(path))


def list_files(root: pathlib.Path, pattern: str = "**/*") -> List[pathlib.Path]:
    """Recursively list files matching pattern under root."""
    return [p for p in root.glob(pattern) if p.is_file()]
