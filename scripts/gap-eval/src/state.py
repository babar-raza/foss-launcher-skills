"""State file read/write/merge for S-43 gap-eval.

State files track findings across runs, enabling delta reports.
Location: reports/gap-analysis/state/{family}-{platform}.json
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

STATE_DIR = Path("reports/gap-analysis/state")


def _state_path(family: str, platform: str, state_dir: Path | None = None) -> Path:
    return (state_dir or STATE_DIR) / f"{family}-{platform}.json"


def load_state(family: str, platform: str, state_dir: Path | None = None) -> dict:
    """Load prior state file; return empty state if not found."""
    path = _state_path(family, platform, state_dir)
    if path.exists():
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
            # Backward compatibility: early gap-eval reports were sometimes
            # seeded directly as state.  Preserve their clone/date metadata
            # under the canonical state keys so rerun deltas do not degrade to
            # "first run, SHA N/A".
            if not state.get("last_run_sha") and state.get("clone_sha"):
                state["last_run_sha"] = state["clone_sha"]
            if not state.get("last_run_date") and state.get("run_date"):
                state["last_run_date"] = str(state["run_date"])[:10]
            return state
        except Exception as exc:
            log.warning("Cannot read state file %s: %s — starting fresh", path, exc)
    return {
        "family": family,
        "platform": platform,
        "last_run_sha": None,
        "last_run_date": None,
        "verdict": None,
        "llm_tier_used": None,
        "findings": [],
        "tier3_cache": {},
    }


def save_state(state: dict, family: str, platform: str, state_dir: Path | None = None) -> Path:
    """Write state to disk atomically."""
    path = _state_path(family, platform, state_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp.replace(path)
    log.info("State saved to %s", path)
    return path


def make_finding_id(family: str, platform: str, finding_type: str, file_path: str, line: int, old_value: str) -> str:
    """Generate a stable finding ID from content location + issue type.

    Same content location, same issue → same ID across reruns.
    Format: F-{family}-{platform}-{type_code}-{sha8}
    """
    type_codes = {
        "wrong-package": "wpkg",
        "phantom-api": "papi",
        "wrong-api-name": "wapi",
        "wrong-claim": "wclm",
        "wrong-unit": "wunt",
        "unimplemented-as-working": "unimp",
        "broken-link": "blink",
        "missing-section": "msec",
        "structural-reference-page": "struc",
        "knowledge-model-wrong": "kmod",
    }
    code = type_codes.get(finding_type, finding_type[:4])
    raw = f"{file_path}:{line}:{old_value[:20]}"
    sha = hashlib.sha256(raw.encode()).hexdigest()[:8]
    return f"F-{family}-{platform}-{code}-{sha}"


def reset_state(family: str, platform: str, state_dir: Path | None = None) -> bool:
    """Delete the state file for family/platform.

    Returns True if a file was deleted, False if no file existed.
    Safe to call even if the file does not exist.
    Raises OSError if the file exists but cannot be deleted (e.g. Windows lock).
    """
    path = _state_path(family, platform, state_dir)
    if path.exists():
        try:
            path.unlink()
        except OSError as exc:
            log.error("State reset failed — cannot delete %s: %s", path, exc)
            raise
        log.info("State reset: deleted %s", path)
        return True
    log.debug("State reset: no state file found at %s", path)
    return False


def merge_findings(prior_findings: list[dict], new_findings: list[dict]) -> tuple[list[dict], dict]:
    """Merge new findings with prior state.

    Returns (merged_findings, delta_summary).
    - Prior findings marked 'fixed' if not in new run
    - Prior findings re-opened as 'regression' if they were 'fixed' but reappear
    - New findings added with status 'open'
    """
    prior_by_id: dict[str, dict] = {f["id"]: f for f in prior_findings}
    new_by_id: dict[str, dict] = {f["id"]: f for f in new_findings}
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    merged: list[dict] = []
    delta = {"fixed": 0, "regressions": 0, "new": 0, "unchanged": 0}

    # Process all new findings
    for fid, new_f in new_by_id.items():
        if fid in prior_by_id:
            prior_f = prior_by_id[fid]
            if prior_f.get("status") == "fixed":
                # It was fixed but now reappears = regression
                new_f["status"] = "regression"
                new_f["regression_date"] = today
                delta["regressions"] += 1
            else:
                # Still open — carry prior metadata
                new_f["status"] = prior_f.get("status", "open")
                delta["unchanged"] += 1
        else:
            new_f["status"] = "open"
            delta["new"] += 1
        merged.append(new_f)

    # Prior findings not in new run → mark fixed
    for fid, prior_f in prior_by_id.items():
        if fid not in new_by_id:
            if prior_f.get("status") not in ("fixed", "wontfix"):
                prior_f = dict(prior_f)
                prior_f["status"] = "fixed"
                prior_f["fixed_date"] = today
                delta["fixed"] += 1
            merged.append(prior_f)

    return merged, delta


def build_delta_section(
    prior_state: dict,
    new_sha: str,
    merged_findings: list[dict],
    delta: dict,
    llm_tier: str,
) -> str:
    """Return the ## Rerun Delta markdown section prepended to reports."""
    prior_sha = prior_state.get("last_run_sha") or "N/A"
    prior_date = prior_state.get("last_run_date") or "first run"
    prior_verdict = prior_state.get("verdict") or "N/A"

    open_m = sum(1 for f in merged_findings if f.get("status") == "open" and f.get("severity") == "M")
    open_s = sum(1 for f in merged_findings if f.get("status") == "open" and f.get("severity") == "S")

    if open_m:
        new_verdict = "NOT PUBLISHABLE"
    elif open_s:
        new_verdict = "CONDITIONAL"
    else:
        new_verdict = "PUBLICATION READY"

    verdict_line = f"- Verdict change: {prior_verdict} → {new_verdict}" if prior_verdict != "N/A" else f"- Verdict: {new_verdict}"

    return (
        f"## Rerun Delta (vs {prior_date}, SHA {prior_sha[:8] if len(prior_sha) >= 8 else prior_sha})\n"
        f"- SHA changed: {prior_sha[:8] if len(prior_sha) >= 8 else prior_sha} → {new_sha[:8] if len(new_sha) >= 8 else new_sha}\n"
        f"- Fixed since last run: {delta['fixed']} findings\n"
        f"- Regressions: {delta['regressions']}\n"
        f"- New findings: {delta['new']}\n"
        f"- Unchanged open: {delta['unchanged']}\n"
        f"{verdict_line}\n"
        f"- LLM tier used: {llm_tier}\n"
        f"- Open M-findings: {open_m}, Open S-findings: {open_s}\n"
    )
