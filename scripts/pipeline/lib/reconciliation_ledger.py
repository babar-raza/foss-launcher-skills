# Adapted from aspose.org scripts/pipeline/lib/ for standalone use
"""reconciliation_ledger.py — TC-PROD-005: Cross-surface reconciliation ledger.

Records the decision, manifest proof, and outcome for every expected surface in a run.
Enforces the rule: surfaces_silently_skipped must be 0.

Phase 3 (shadow mode): ledger is written to shadow path only.
  reports/shadow-reconciliation/{run_id}/{family}-{platform}.json
post_refresh_verify.py behavior is NOT changed.

Ledger invariants:
  - Every expected surface must have a record (no silent omissions).
  - FRESH surfaces must include manifest_proof_path.
  - BLOCKED surfaces must be listed explicitly in partial_pass_surfaces.
  - surfaces_silently_skipped must be 0 for a shadow run to pass.
  - A BLOCKED surface never produces an overall PASS.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


_REPO_ROOT = Path(os.environ.get("CONTENT_REPO_PATH", str(Path(__file__).resolve().parents[3])))

# Valid run-level statuses
PASS = "PASS"
PARTIAL_PASS = "PARTIAL_PASS"
FAIL = "FAIL"
BLOCKED = "BLOCKED"
DRY_RUN_PASS = "DRY_RUN_PASS"

_VALID_RUN_STATUSES = frozenset({PASS, PARTIAL_PASS, FAIL, BLOCKED, DRY_RUN_PASS})


@dataclass
class SurfaceRecord:
    """Record for a single (product, subdomain) surface in the ledger."""

    product: str
    subdomain: str
    decision: str
    outcome: str                        # PASS, FAIL, BLOCKED, SKIP (for FRESH/VALIDATE_ONLY)
    manifest_proof_path: Optional[str]  # Required when decision is FRESH
    explanation: str = ""
    changed_input_fingerprints: list = field(default_factory=list)
    tc_conditions_met: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "product": self.product,
            "subdomain": self.subdomain,
            "decision": self.decision,
            "outcome": self.outcome,
            "manifest_proof_path": self.manifest_proof_path,
            "explanation": self.explanation,
            "changed_input_fingerprints": self.changed_input_fingerprints,
            "tc_conditions_met": self.tc_conditions_met,
        }


class ReconciliationLedger:
    """Ledger tracking all surfaces for a single refresh run.

    Usage:
        ledger = ReconciliationLedger(run_id="20260501-100000")
        ledger.add_record(SurfaceRecord(...))
        ledger.finalize()  # computes run_status
        ledger.save(shadow_root)
    """

    def __init__(self, run_id: str):
        self.run_id = run_id
        self.records: list[SurfaceRecord] = []
        self.run_status: Optional[str] = None
        self.surfaces_silently_skipped: int = 0
        self.partial_pass_surfaces: list[str] = []

    def add_record(self, record: SurfaceRecord) -> None:
        """Add a surface record to the ledger."""
        self.records.append(record)

    def finalize(self) -> str:
        """Compute run_status from all records. Returns the run_status string.

        Rules:
        - If any surface has outcome FAIL: run_status = FAIL
        - If any surface has outcome BLOCKED: run_status = PARTIAL_PASS;
          blocked surfaces listed in partial_pass_surfaces
        - If surfaces_silently_skipped > 0: run_status = FAIL (evidence gap)
        - If all surfaces PASS/SKIP: run_status = PASS
        """
        if self.surfaces_silently_skipped > 0:
            self.run_status = FAIL
            return self.run_status

        blocked = [r for r in self.records if r.outcome == BLOCKED]
        failed = [r for r in self.records if r.outcome == FAIL]

        if failed:
            self.run_status = FAIL
        elif blocked:
            self.run_status = PARTIAL_PASS
            self.partial_pass_surfaces = [
                f"{r.product}/{r.subdomain}" for r in blocked
            ]
        else:
            self.run_status = PASS

        return self.run_status

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "run_status": self.run_status,
            "surfaces_silently_skipped": self.surfaces_silently_skipped,
            "partial_pass_surfaces": self.partial_pass_surfaces,
            "records": [r.to_dict() for r in self.records],
        }

    def save(self, shadow_root: Path, product: str) -> Path:
        """Atomically write the ledger to shadow_root/{run_id}/{family}-{platform}.json.

        Args:
            shadow_root: Root directory for shadow reconciliation output.
            product: Product slug "family/platform" (used in filename).

        Returns:
            Path to the written file.
        """
        slug = product.replace("/", "-")
        out_dir = shadow_root / self.run_id
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{slug}.json"
        tmp_path = out_path.with_suffix(".tmp")
        tmp_path.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        os.replace(str(tmp_path), str(out_path))
        return out_path


def load_tc_closure_conditions(repo_root: Optional[Path] = None) -> dict:
    """Load data/tc-closure-conditions.json.

    Returns empty dict if the file does not exist (graceful degradation).
    """
    root = repo_root if repo_root is not None else _REPO_ROOT
    path = root / "data" / "tc-closure-conditions.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def check_tc_conditions(
    record: SurfaceRecord,
    tc_conditions: dict,
) -> list:
    """Check which TC closure conditions are met for a surface record.

    Returns list of TC IDs whose conditions are satisfied.
    This is shadow-only; it does not update closure status.
    """
    met = []
    for tc_id, condition in tc_conditions.items():
        if not isinstance(condition, dict):
            continue  # skip _comment and _version metadata keys
        required_decision = condition.get("required_decision")
        required_subdomain = condition.get("required_subdomain")
        required_product_pattern = condition.get("required_product_pattern", "")

        if required_decision and record.decision != required_decision:
            continue
        if required_subdomain and record.subdomain != required_subdomain:
            continue
        if required_product_pattern and required_product_pattern not in record.product:
            continue

        met.append(tc_id)
    return met


def build_ledger(
    run_id: str,
    surface_records: list[SurfaceRecord],
    expected_surfaces: list[str],
    tc_conditions: Optional[dict] = None,
) -> ReconciliationLedger:
    """Build a complete ledger from surface records, checking for silent skips.

    Args:
        run_id: Unique run identifier.
        surface_records: Records for each surface that was evaluated.
        expected_surfaces: List of "{product}/{subdomain}" strings expected in this run.
        tc_conditions: Optional TC closure conditions from tc-closure-conditions.json.

    Returns:
        Finalized ReconciliationLedger.
    """
    ledger = ReconciliationLedger(run_id=run_id)

    # Track which expected surfaces have records
    recorded = set()
    for record in surface_records:
        key = f"{record.product}/{record.subdomain}"
        recorded.add(key)

        # Check TC conditions
        if tc_conditions:
            record.tc_conditions_met = check_tc_conditions(record, tc_conditions)

        ledger.add_record(record)

    # Count silent skips (expected but no record)
    ledger.surfaces_silently_skipped = sum(
        1 for s in expected_surfaces if s not in recorded
    )

    ledger.finalize()
    return ledger
