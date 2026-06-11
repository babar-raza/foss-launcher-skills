"""run_outcome_log.py — Append-only JSONL log for skill execution outcomes.

Tracks skill execution results across runs, enabling cross-run feedback
queries (e.g., "which skills failed most often on this family?").

Complements ops_log.py (which tracks pre_write operations) by capturing
skill-level execution outcomes with timing, retry, and correlation information.

Key capabilities:
  - log_outcome(): append one outcome entry with optional correlation_id
  - read_outcomes(): read the most recent N entries
  - summarize_run(): aggregate outcomes for a given correlation_id
  - checkpoint_run(): persist in-progress run state for resume-after-failure
  - resume_from_checkpoint(): restore checkpointed state by correlation_id

Usage:
    from scripts.pipeline.commands.ops.run_outcome_log import (
        log_outcome,
        read_outcomes,
        summarize_run,
        checkpoint_run,
        resume_from_checkpoint,
    )

    correlation_id = "run-2026-06-10-abc123"
    log_outcome("S-21", "success", duration_ms=1200, correlation_id=correlation_id)
    log_outcome("S-26", "failure", error="timeout", correlation_id=correlation_id)

    summary = summarize_run(correlation_id)
    # {"total": 2, "success": 1, "failure": 1, "duration_ms_total": 1200, ...}

Concurrency:
    This module assumes single-process, single-thread execution. The log_outcome()
    append operation is not protected by a file lock. Concurrent calls from multiple
    processes will produce interleaved writes and may corrupt the JSONL log.
    Guarantee: callers MUST ensure only one process writes to a given log file at a time.
    Enforcement: the skill pipeline serializes all skill execution through a single
    local_gate.py process; no parallel skill execution is supported.

    checkpoint_run(correlation_id, {"last_skill": "S-26", "page": "my-page.md"})
    state = resume_from_checkpoint(correlation_id)
    # {"last_skill": "S-26", "page": "my-page.md"}
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
_DEFAULT_LOG = _REPO_ROOT / "reports" / "run_outcomes.jsonl"
_DEFAULT_CHECKPOINT_DIR = _REPO_ROOT / "reports" / "checkpoints"

VALID_STATUSES = {"success", "failure", "partial", "skipped", "exhausted"}


def log_outcome(
    skill_id: str,
    status: str,
    *,
    duration_ms: int = 0,
    retry_count: int = 0,
    error: str | None = None,
    correlation_id: str | None = None,
    log_path: Path | str | None = None,
) -> Path:
    """Append one outcome entry to the run outcomes log.

    Args:
        skill_id: Skill identifier (e.g. "S-21").
        status: One of VALID_STATUSES.
        duration_ms: Execution duration in milliseconds.
        retry_count: Number of retries before this outcome.
        error: Optional error message if status is failure/exhausted.
        correlation_id: Optional run session identifier for grouping related outcomes.
        log_path: Override default log path (for testing).

    Returns:
        The log file path.
    """
    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid status {status!r}. Must be one of {sorted(VALID_STATUSES)}")

    resolved = Path(log_path) if log_path is not None else _DEFAULT_LOG
    resolved.parent.mkdir(parents=True, exist_ok=True)

    entry: dict = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "skill_id": skill_id,
        "status": status,
        "duration_ms": duration_ms,
        "retry_count": retry_count,
    }
    if correlation_id is not None:
        entry["correlation_id"] = correlation_id
    if error is not None:
        entry["error"] = error

    with open(resolved, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")

    return resolved


def read_outcomes(
    last_n: int = 100,
    log_path: Path | str | None = None,
) -> list[dict]:
    """Read the most recent N entries from the run outcomes log."""
    resolved = Path(log_path) if log_path is not None else _DEFAULT_LOG
    if not resolved.is_file():
        return []

    entries: list[dict] = []
    with open(resolved, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                entries.append(json.loads(line))

    return entries[-last_n:] if len(entries) > last_n else entries


def summarize_run(
    correlation_id: str,
    log_path: Path | str | None = None,
) -> dict:
    """Aggregate outcome metrics for all entries sharing a correlation_id.

    Returns a dict with keys:
        total, success, failure, partial, skipped, exhausted,
        duration_ms_total, retry_count_total, skills, errors
    """
    resolved = Path(log_path) if log_path is not None else _DEFAULT_LOG
    summary: dict = {
        "correlation_id": correlation_id,
        "total": 0,
        "success": 0,
        "failure": 0,
        "partial": 0,
        "skipped": 0,
        "exhausted": 0,
        "duration_ms_total": 0,
        "retry_count_total": 0,
        "skills": [],
        "errors": [],
    }

    if not resolved.is_file():
        return summary

    with open(resolved, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            if entry.get("correlation_id") != correlation_id:
                continue

            summary["total"] += 1
            status = entry.get("status", "")
            if status in VALID_STATUSES:
                summary[status] = summary.get(status, 0) + 1

            summary["duration_ms_total"] += entry.get("duration_ms", 0)
            summary["retry_count_total"] += entry.get("retry_count", 0)
            summary["skills"].append(entry.get("skill_id", ""))

            if entry.get("error"):
                summary["errors"].append({
                    "skill_id": entry.get("skill_id", ""),
                    "error": entry["error"],
                })

    return summary


def checkpoint_run(
    correlation_id: str,
    state: dict,
    checkpoint_dir: Path | str | None = None,
) -> Path:
    """Persist in-progress run state for resume-after-failure.

    Writes a JSON checkpoint file keyed by correlation_id.
    Overwrites any existing checkpoint for the same correlation_id.

    Args:
        correlation_id: Run session identifier.
        state: Arbitrary dict of state to persist (last_skill, page, etc.).
        checkpoint_dir: Override default checkpoint directory (for testing).

    Returns:
        Path to the checkpoint file.
    """
    resolved_dir = Path(checkpoint_dir) if checkpoint_dir is not None else _DEFAULT_CHECKPOINT_DIR
    resolved_dir.mkdir(parents=True, exist_ok=True)

    safe_id = correlation_id.replace("/", "-").replace("\\", "-")
    checkpoint_path = resolved_dir / f"{safe_id}.json"

    record = {
        "correlation_id": correlation_id,
        "checkpointed_at": datetime.now(timezone.utc).isoformat(),
        "state": state,
    }

    with open(checkpoint_path, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    return checkpoint_path


def resume_from_checkpoint(
    correlation_id: str,
    checkpoint_dir: Path | str | None = None,
) -> dict | None:
    """Restore checkpointed state by correlation_id.

    Returns the state dict if a checkpoint exists, or None if not found.

    Args:
        correlation_id: Run session identifier to look up.
        checkpoint_dir: Override default checkpoint directory (for testing).
    """
    resolved_dir = Path(checkpoint_dir) if checkpoint_dir is not None else _DEFAULT_CHECKPOINT_DIR
    safe_id = correlation_id.replace("/", "-").replace("\\", "-")
    checkpoint_path = resolved_dir / f"{safe_id}.json"

    if not checkpoint_path.is_file():
        return None

    with open(checkpoint_path, encoding="utf-8") as fh:
        record = json.load(fh)

    return record.get("state")
