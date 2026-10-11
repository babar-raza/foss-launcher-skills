"""apply_gate.py — ClaimPlan apply gate for safe evidence injection.

Implements TC-CLAIM-09: separates plan generation from plan application.
All writes are gated behind provenance checks.

Public API:
    ApplyGateError     — raised when a gate condition fails
    validate_plan(plan, knowledge_root, max_files, repo_head) -> None
    apply_plan(plan, knowledge_root, max_files, repo_head) -> ApplyResult
    write_ledger_entry(entry, ledger_path) -> None
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal


class ApplyGateError(Exception):
    """Raised when an apply gate condition fails."""


def _get_repo_head(repo_root: Path) -> str:
    """Return current git HEAD SHA. Returns '' on error."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            cwd=str(repo_root), timeout=10,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        return ""


def _get_knowledge_claims_hash(family: str, platform: str,
                                knowledge_root: Path) -> str:
    """Compute sha256 of the current merged/claims.json."""
    claims_path = knowledge_root / family / platform / "merged" / "claims.json"
    if not claims_path.exists():
        return ""
    return hashlib.sha256(claims_path.read_bytes()).hexdigest()


def _body_unchanged(filepath: Path) -> bool:
    """Return True if the body outside frontmatter can be safely preserved.

    This is a pre-check before writing. Since we only modify frontmatter
    (evidence block), the body should never change. This guard detects if
    the file cannot be safely parsed (e.g. malformed frontmatter).
    Returns True when the file has parseable frontmatter (safe to write).
    Returns False when frontmatter is undetectable (write would be unsafe).
    """
    try:
        text = filepath.read_text(encoding="utf-8")
        if not text.startswith("---"):
            return False
        end = text.find("\n---", 3)
        return end != -1
    except OSError:
        return False


def validate_plan(
    plan: dict,
    knowledge_root: Path,
    max_files: int,
    repo_root: Path,
) -> None:
    """Validate a ClaimPlan dict against all apply gate conditions.

    Raises ApplyGateError with a descriptive message if any gate fails.

    Gate conditions (from TC-CLAIM-09):
    1. plan contains plan_id, repo_head, knowledge_repo_sha, claims_hash fields
    2. current repo HEAD matches plan's repo_head
    3. current knowledge claims_hash matches plan's claims_hash
    4. plan was generated with explicit subdomain (not None)
    5. plan file_count <= max_files
    6. no BLOCK policy actions in proposed_claims
    7. all target files have parseable frontmatter (body-change pre-check)
    """
    # Gate 1: required plan fields
    for field_name in ("plan_id", "repo_head", "knowledge_repo_sha",
                       "claims_hash", "subdomain", "records"):
        if field_name not in plan:
            raise ApplyGateError(
                f"Plan is missing required field {field_name!r}. "
                "Generate a new plan with --dry-run-json."
            )

    # Gate 2: repo HEAD unchanged
    plan_head = plan["repo_head"]
    current_head = _get_repo_head(repo_root)
    if current_head and plan_head and current_head != plan_head:
        raise ApplyGateError(
            f"Repo HEAD changed since plan was generated.\n"
            f"  Plan HEAD:    {plan_head}\n"
            f"  Current HEAD: {current_head}\n"
            "Regenerate the plan with --dry-run-json before applying."
        )

    # Gate 3: claims_hash unchanged
    subdomain = plan.get("subdomain")
    family = plan.get("family", "")
    platform = plan.get("platform", "")
    plan_claims_hash = plan.get("claims_hash", "")
    if family and platform and plan_claims_hash:
        current_claims_hash = _get_knowledge_claims_hash(
            family, platform, knowledge_root
        )
        if current_claims_hash and current_claims_hash != plan_claims_hash:
            raise ApplyGateError(
                f"Knowledge claims_hash changed since plan was generated.\n"
                f"  Plan hash:    {plan_claims_hash}\n"
                f"  Current hash: {current_claims_hash}\n"
                "Regenerate the plan with --dry-run-json before applying."
            )

    # Gate 4: subdomain must be set
    if not subdomain:
        raise ApplyGateError(
            "Plan was generated without --subdomain scope. "
            "Scoped plans required for apply; use "
            "--subdomain <name> or --all-subdomains --confirm-all-subdomains."
        )

    # Gate 5: file count <= max_files
    records = plan.get("records", [])
    write_count = sum(
        1 for r in records
        if r.get("action") in ("WOULD_UPDATE", "WOULD_UPDATE_METADATA")
    )
    if write_count > max_files:
        raise ApplyGateError(
            f"Plan would write {write_count} files but --max-files={max_files}. "
            "Use --max-files N to increase the limit (default: 20)."
        )

    # Gate 6: no BLOCK policy actions
    for rec in records:
        for claim_rec in rec.get("proposed_claims", []):
            if isinstance(claim_rec, dict) and claim_rec.get("policy_status") == "BLOCK":
                raise ApplyGateError(
                    f"Plan contains BLOCK policy action for claim "
                    f"{claim_rec.get('claim_id')!r} in {rec.get('filepath')!r}. "
                    "Resolve blocked claims before applying."
                )

    # Gate 7: all target files have parseable frontmatter
    for rec in records:
        if rec.get("action") not in ("WOULD_UPDATE", "WOULD_UPDATE_METADATA"):
            continue
        fp = Path(rec["filepath"])
        if fp.exists() and not _body_unchanged(fp):
            raise ApplyGateError(
                f"File has malformed frontmatter; body-change pre-check failed: {fp}\n"
                "Fix the frontmatter before applying."
            )


@dataclass
class ApplyResult:
    """Result of a plan apply run."""
    plan_id: str
    subdomain: str
    files_written: int
    files_skipped: int
    warn_count: int
    blocked_count: int
    errors: list[str] = field(default_factory=list)
    apply_status: Literal["PASS", "FAIL", "BLOCKED"] = "PASS"


def apply_plan(
    plan: dict,
    knowledge_root: Path,
    max_files: int,
    repo_root: Path,
) -> ApplyResult:
    """Apply a validated ClaimPlan. Raises ApplyGateError on gate failure.

    Does NOT write content files directly — it delegates to attach_evidence.
    Returns ApplyResult with per-file outcome counts.

    Note: this function first validates the plan via validate_plan(), then
    applies WOULD_UPDATE records by calling attach_evidence(force=True).
    SKIP and WOULD_UPDATE_METADATA records are not written to frontmatter.
    """
    validate_plan(plan, knowledge_root, max_files, repo_root)

    # Import here to avoid circular imports
    sys_path_guard = str(Path(__file__).resolve().parent.parent)
    if sys_path_guard not in sys.path:
        sys.path.insert(0, sys_path_guard)

    from knowledge_core import Knowledge  # noqa: E402
    from evidence.runner import attach_evidence  # noqa: E402

    family = plan.get("family", "")
    platform = plan.get("platform", "")
    knowledge = Knowledge(family, platform, knowledge_root=knowledge_root)
    if not knowledge.available:
        raise ApplyGateError(
            f"Knowledge not available for {family}/{platform}. "
            "Cannot apply plan without knowledge model."
        )

    records = plan.get("records", [])
    files_written = 0
    files_skipped = 0
    warn_count = 0
    blocked_count = 0
    errors = []

    for rec in records:
        action = rec.get("action")
        fp = Path(rec["filepath"])

        if action not in ("WOULD_UPDATE",):
            files_skipped += 1
            continue

        # Count policy warnings/blocks
        for claim_rec in rec.get("proposed_claims", []):
            if isinstance(claim_rec, dict):
                ps = claim_rec.get("policy_status")
                if ps == "WARN":
                    warn_count += 1
                elif ps == "BLOCK":
                    blocked_count += 1

        if not fp.exists():
            errors.append(f"File not found: {fp}")
            files_skipped += 1
            continue

        status = attach_evidence(fp, knowledge, force=True)
        if status in ("UPDATED",):
            files_written += 1
        elif status.startswith("ERROR"):
            errors.append(f"Error writing {fp}: {status}")
            files_skipped += 1
        else:
            files_skipped += 1

    apply_status = "FAIL" if errors else ("BLOCKED" if blocked_count else "PASS")
    return ApplyResult(
        plan_id=plan.get("plan_id", ""),
        subdomain=plan.get("subdomain", ""),
        files_written=files_written,
        files_skipped=files_skipped,
        warn_count=warn_count,
        blocked_count=blocked_count,
        errors=errors,
        apply_status=apply_status,
    )


def write_ledger_entry(entry: dict, ledger_path: Path) -> None:
    """Append a run ledger entry to the ledger JSON file (creates if absent).

    The ledger is a JSON array. Each call appends one entry.
    The ledger file is gitignored (runs/ledger/ is excluded).
    """
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    if ledger_path.exists():
        try:
            existing = json.loads(ledger_path.read_text(encoding="utf-8"))
            if not isinstance(existing, list):
                existing = []
        except (json.JSONDecodeError, OSError):
            existing = []
    else:
        existing = []
    existing.append(entry)
    ledger_path.write_text(
        json.dumps(existing, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _build_ledger_entry(
    plan: dict,
    result: ApplyResult,
    command: str,
    dry_run_json_path: str = "",
) -> dict:
    """Build a structured run ledger entry from a plan + result."""
    return {
        "applied_at": datetime.now(timezone.utc).isoformat(),
        "applied_by_command": command,
        "apply_result": result.apply_status,
        "blocked_count": result.blocked_count,
        "claims_hash": plan.get("claims_hash", ""),
        "claim_plan_id": plan.get("plan_id", ""),
        "dry_run_json_path": dry_run_json_path,
        "errors": result.errors,
        "family": plan.get("family", ""),
        "file_count": result.files_written + result.files_skipped,
        "files_skipped": result.files_skipped,
        "files_written": result.files_written,
        "knowledge_repo_sha": plan.get("knowledge_repo_sha", ""),
        "platform": plan.get("platform", ""),
        "repo_head": plan.get("repo_head", ""),
        "subdomain": plan.get("subdomain", ""),
        "warn_count": result.warn_count,
    }
