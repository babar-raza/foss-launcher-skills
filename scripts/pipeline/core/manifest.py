"""Manifest helpers - read/write JSON manifests atomically.

Ported from aspose.org scripts/pipeline/core/manifest.py.
"""
import json
import pathlib
from typing import Any, Dict

from .fs import atomic_write


def read_manifest(path: pathlib.Path) -> Dict[str, Any]:
    """Read a JSON manifest file. Returns empty dict if not found."""
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_manifest(path: pathlib.Path, data: Dict[str, Any], indent: int = 2) -> None:
    """Write a JSON manifest file atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, json.dumps(data, indent=indent, default=str) + "\n")
