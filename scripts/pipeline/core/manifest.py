"""Pipeline run-state manifest helpers.

Each product (family/platform) has a ``.pipeline_state.json`` file in its
knowledge directory that records which pipeline steps have completed, when
they ran, and whether they succeeded.  This lets downstream steps detect
partial runs and tools skip re-processing up-to-date products.

Typical usage
-------------
After a step succeeds::

    from core.manifest import write_step_manifest
    write_step_manifest(state_path, "scout", {"repo_sha": sha, "files_written": n})

Before a step starts::

    from core.manifest import check_step_complete
    if check_step_complete(state_path, "scout"):
        print("scout already complete, skipping")
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


def write_step_manifest(
    state_path: Path,
    step: str,
    metadata: dict[str, Any],
    *,
    success: bool = True,
) -> None:
    """Record that *step* completed (or failed) for this product.

    The manifest is updated atomically so a crash mid-write never leaves
    a corrupt file.  Earlier step records are preserved.
    """
    from .fs import atomic_write  # local import avoids circular at module level

    state = _load_state(state_path)
    state[step] = {
        "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "success": success,
        **metadata,
    }
    atomic_write(state_path, json.dumps(state, indent=2, ensure_ascii=False))


def check_step_complete(state_path: Path, step: str) -> bool:
    """Return True iff *step* has a successful completion record."""
    return _load_state(state_path).get(step, {}).get("success", False)


def get_step_metadata(state_path: Path, step: str) -> dict[str, Any]:
    """Return the metadata dict for *step*, or {} if absent."""
    return _load_state(state_path).get(step, {})


def _load_state(state_path: Path) -> dict[str, Any]:
    """Load state file, returning {} on any read or parse error."""
    if not state_path.exists():
        return {}
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
