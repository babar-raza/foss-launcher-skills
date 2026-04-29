"""path_utils.py — Shared path rendering utilities for pipeline and CI scripts."""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent  # scripts/pipeline/lib/ -> pipeline/ -> scripts/ -> repo root


def repo_rel(path: Path, root: Path | None = None) -> str:
    """Return a repo-relative display string; fall back to absolute path if outside root.

    Args:
        path: The path to render.
        root: The root to relativise against. Defaults to the repository root.

    Returns:
        A string that is relative to *root* when *path* is a descendant of *root*,
        or the absolute path string otherwise. Never raises.
    """
    if root is None:
        root = _REPO_ROOT
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)
