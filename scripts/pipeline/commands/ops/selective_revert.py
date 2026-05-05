"""
TC-S96-012: Selective Revert.

Reverts BAD_REVERT and RISKY_REVIEW files using baseline_git_sha.
NEVER uses HEAD for reverts. Deletes new bad files. Writes revert-log.json.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass
class RevertRecord:
    path: str
    verdict: str
    action_taken: str
    method: str
    result: str
    verified: Optional[bool] = None
    error: Optional[str] = None


@dataclass
class RevertLog:
    run_id: str
    baseline_git_sha: str
    generated_at: str
    dry_run: bool
    keep_risky_pending: bool
    keep_unclear_pending: bool
    records: List[RevertRecord] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "baseline_git_sha": self.baseline_git_sha,
            "generated_at": self.generated_at,
            "dry_run": self.dry_run,
            "keep_risky_pending": self.keep_risky_pending,
            "keep_unclear_pending": self.keep_unclear_pending,
            "records": [
                {
                    "path": r.path,
                    "verdict": r.verdict,
                    "action_taken": r.action_taken,
                    "method": r.method,
                    "result": r.result,
                    "verified": r.verified,
                    "error": r.error,
                }
                for r in self.records
            ],
        }


def _git_checkout_baseline(
    rel_path: str,
    baseline_git_sha: str,
    repo_root: pathlib.Path,
    dry_run: bool,
) -> tuple[bool, Optional[str]]:
    """Run git checkout {sha} -- {path}. Returns (success, error_message)."""
    if dry_run:
        return True, None
    try:
        result = subprocess.run(
            ["git", "checkout", baseline_git_sha, "--", rel_path],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            return True, None
        return False, result.stderr.strip()
    except Exception as e:
        return False, str(e)


def _sha256_file(path: pathlib.Path) -> str:
    import hashlib
    raw = path.read_bytes()
    normalized = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(normalized).hexdigest()


def apply_decision(
    ledger: Dict[str, Any],
    baseline_git_sha: str,
    repo_root: pathlib.Path,
    dry_run: bool = False,
    keep_risky_pending: bool = False,
    keep_unclear_pending: bool = False,
    manifest_data: Optional[Dict[str, Any]] = None,
) -> RevertLog:
    """Apply decisions from review ledger. Returns RevertLog."""
    run_id = ledger.get("run_id", "unknown")
    entries = ledger.get("entries", [])
    manifest_files = (manifest_data or {}).get("files", {})

    log = RevertLog(
        run_id=run_id,
        baseline_git_sha=baseline_git_sha,
        generated_at=datetime.now(timezone.utc).isoformat(),
        dry_run=dry_run,
        keep_risky_pending=keep_risky_pending,
        keep_unclear_pending=keep_unclear_pending,
    )

    for entry in entries:
        path = entry.get("path", "")
        verdict = entry.get("verdict", "")

        if verdict == "GOOD_KEEP":
            log.records.append(RevertRecord(
                path=path, verdict=verdict,
                action_taken="KEPT", method="no-op",
                result="SKIPPED", verified=None,
            ))
            continue

        if verdict == "RISKY_REVIEW" and keep_risky_pending:
            log.records.append(RevertRecord(
                path=path, verdict=verdict,
                action_taken="LEFT_PENDING", method="--keep-risky-pending",
                result="SKIPPED", verified=None,
            ))
            continue

        if verdict == "UNCLEAR_NEEDS_EVIDENCE" and keep_unclear_pending:
            log.records.append(RevertRecord(
                path=path, verdict=verdict,
                action_taken="LEFT_PENDING", method="--keep-unclear-pending",
                result="SKIPPED", verified=None,
            ))
            continue

        # Need to revert or delete
        in_baseline = path in manifest_files
        abs_path = repo_root / path

        if in_baseline:
            # Tracked file — revert from baseline_git_sha
            method = f"git checkout {baseline_git_sha} -- {path}"
            success, err = _git_checkout_baseline(path, baseline_git_sha, repo_root, dry_run)
            if success:
                # Verify sha matches baseline
                verified = False
                if not dry_run and abs_path.exists() and path in manifest_files:
                    expected_sha = manifest_files[path].get("sha256", "")
                    actual_sha = _sha256_file(abs_path)
                    verified = actual_sha == expected_sha
                elif dry_run:
                    verified = None
                log.records.append(RevertRecord(
                    path=path, verdict=verdict,
                    action_taken="REVERTED_FROM_BASELINE", method=method,
                    result="SUCCESS", verified=verified,
                ))
            else:
                log.records.append(RevertRecord(
                    path=path, verdict=verdict,
                    action_taken="REVERTED_FROM_BASELINE", method=method,
                    result="FAILED", error=err,
                ))
        else:
            # New file — delete it
            if not dry_run and abs_path.exists():
                abs_path.unlink()
            log.records.append(RevertRecord(
                path=path, verdict=verdict,
                action_taken="DELETED_NEW_FILE",
                method=f"unlink {path}",
                result="SUCCESS" if (dry_run or not abs_path.exists()) else "FAILED",
            ))

    return log


def write_revert_log(log: RevertLog, output: pathlib.Path) -> None:
    """Write RevertLog to JSON atomically."""
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_suffix(".tmp")
    tmp.write_text(json.dumps(log.to_dict(), indent=2), encoding="utf-8")
    os.replace(tmp, output)
