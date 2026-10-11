"""_repo_root.py — Stable repo-root resolver for pipeline tests.

Use this instead of Path(__file__).parents[N] to avoid brittle depth assumptions
when test files are moved between directories.
"""
from __future__ import annotations

from pathlib import Path


def repo_root() -> Path:
    """Return the repo root regardless of where this file lives."""
    p = Path(__file__).resolve()
    for parent in p.parents:
        if (parent / "AGENTS.md").exists():
            return parent
    raise RuntimeError(
        f"Cannot locate repo root: no AGENTS.md found above {p}"
    )
