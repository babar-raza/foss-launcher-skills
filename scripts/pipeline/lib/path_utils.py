"""path_utils.py — Repo-relative path helpers.

Ported from aspose.org scripts/pipeline/lib/path_utils.py.
"""
from __future__ import annotations

from pathlib import Path


def repo_rel(path: str | Path, root: str | Path | None = None) -> str:
    """Return *path* as a repo-relative forward-slash string.

    If *root* is None, the repository root is inferred by walking up from
    this file's location (scripts/pipeline/lib/ -> repo root is 3 levels up).

    Returns the forward-slash relative path string, or the original path
    as a string if it cannot be made relative (e.g. on a different drive).
    """
    if root is None:
        root = Path(__file__).resolve().parents[3]
    try:
        return str(Path(path).resolve().relative_to(Path(root).resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")
