"""
Shared utilities for the aspose.org Local Supervisor Control Plane.
All functions are deterministic. No LLM calls.
"""
from __future__ import annotations

import json
import os
import fnmatch
import sys
from pathlib import Path
from typing import Any


def find_repo_root(start=None):
    """Walk up from start (or cwd) until we find AGENTS.md or .git."""
    here = Path(start or os.getcwd()).resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "AGENTS.md").exists() or (candidate / ".git").exists():
            return candidate
    return here


REPO_ROOT = find_repo_root()

# Supervisor must NEVER write to these paths (in any mode)
FORBIDDEN_WRITE_GLOBS = [
    "AGENTS.md",
    "CLAUDE.md",
    "content/**",
    "knowledge/**",
    "backlog/**",
    "scripts/pipeline/**",
    ".taskmaster/**",
]


def is_forbidden(path, repo_root=None):
    """Return True if path matches any forbidden write pattern."""
    if repo_root is None:
        repo_root = REPO_ROOT
    rel = Path(path)
    try:
        rel = rel.relative_to(repo_root)
    except ValueError:
        pass
    rel_str = str(rel).replace("\\", "/")
    for pattern in FORBIDDEN_WRITE_GLOBS:
        if fnmatch.fnmatch(rel_str, pattern):
            return True
        if pattern.endswith("/**"):
            prefix = pattern[:-3]
            if rel_str == prefix or rel_str.startswith(prefix + "/"):
                return True
    return False


def safe_emit(data, output_path, dry_run=False):
    """Write JSON to output_path. Raises PermissionError if path is forbidden."""
    p = Path(output_path)
    if is_forbidden(p):
        raise PermissionError(f"FORBIDDEN WRITE BLOCKED: {p}")
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)
    return data


def base_args(description):
    import argparse
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="Run read-only; do not mutate protected paths (default: True)")
    parser.add_argument("--execute", action="store_true", default=False,
                        help="Enable execute mode (writes to backlog/HANDOFF.md). Gated.")
    parser.add_argument("--output", type=str, default=None,
                        help="Path to write JSON/markdown output")
    return parser
