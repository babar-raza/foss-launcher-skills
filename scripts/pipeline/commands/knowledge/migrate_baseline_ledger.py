#!/usr/bin/env python3
"""migrate_baseline_ledger.py — RPR-C-04: one-time baseline-ledger backfill.

Products refreshed before the append-only ledger (RPR-C-01) existed have their
baseline only as a single mutable `model.yaml.repo_sha` scalar. This migration
seeds a ledger row for each active product **without fabricating history**: every
product is classified into an explicit provenance class, and none is silently
defaulted to CONFIRMED (the plan's §13 hard rule — do not silently assign the
current commit as a historical, verified baseline).

Provenance classes (plan RPR-C-04):
  CONFIRMED     — a CLOSED backlog item names the SHA (e.g. PDF-NET-REFRESH-001,
                  FONT-PYTHON-REFRESH-001). Ledger row: status=accepted,
                  sha_source=manual-recovery, accepted_at = the item's date.
  RECONSTRUCTED — model.yaml has a repo_sha but no CLOSED-item attestation. Ledger
                  row: status=accepted, sha_source=manual-recovery, with a
                  reconstruction_note recorded in the provenance report (NOT
                  presented as a verified/confirmed baseline).
  UNCERTAIN     — a known-conflated case (e.g. 3D-NET-REFRESH-002, whose backlog
                  entry itself says the SHA is "currently conflated"). Ledger row:
                  status=attempted (NOT accepted) — the head stays unresolved
                  pending RPR-C-03's orphaned-sha resolution.
  NO_BASELINE   — no model.yaml repo_sha at all. No ledger row written.

Default mode is --dry-run (classify + write the provenance report only). --apply
writes ledger rows. Idempotent: a product that already has a ledger is skipped.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_THIS = Path(__file__).resolve()
# scripts/pipeline/commands/knowledge/migrate_baseline_ledger.py
#   parents[2] = scripts/pipeline ; parents[4] = repo root
_PIPELINE_ROOT = _THIS.parents[2]
_REPO_ROOT = _THIS.parents[4]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

from lib.baseline_ledger import BaselineLedger  # noqa: E402

CONFIRMED = "CONFIRMED"
RECONSTRUCTED = "RECONSTRUCTED"
UNCERTAIN = "UNCERTAIN"
NO_BASELINE = "NO_BASELINE"

# ── Curated attestations (human-verified against CLOSED backlog items) ─────
# CONFIRMED requires a real CLOSED backlog item naming the SHA — a script cannot
# invent that attestation, so it lives here as reviewable, git-tracked data with
# the source item cited. UNCERTAIN records a backlog entry that itself flags its
# SHA as conflated. Everything NOT listed here is classified by machine signal
# (RECONSTRUCTED if a repo_sha exists, NO_BASELINE otherwise) — never CONFIRMED.
_CURATED_ATTESTATIONS: dict[tuple[str, str], dict[str, Any]] = {
    ("pdf", "net"): {
        "provenance": CONFIRMED,
        "prior_repo_sha": "d42e9f1ec",
        "new_repo_sha": "8a3131b9a6",
        "accepted_at": "2026-07-16T00:00:00Z",
        "source_item": "PDF-NET-REFRESH-001",
        "note": "CLOSED 2026-07-16, v26.7.0; commits 0b150810c5/36899ed2aa/ca0e79be34/a42ca5ba66/a6eda23a19",
    },
    ("font", "python"): {
        "provenance": CONFIRMED,
        "prior_repo_sha": None,
        "new_repo_sha": "a9aa49286f",
        "accepted_at": "2026-06-15T00:00:00Z",
        "source_item": "FONT-PYTHON-REFRESH-001",
        "note": "CLOSED 2026-06-15 baseline; later FONT-PYTHON-REFRESH-002 drift to a7448097 is "
                "REMEDIATION_REQUIRED, NOT a clean accepted refresh — this row records the last "
                "CONFIRMED accepted baseline only.",
    },
    ("3d", "net"): {
        "provenance": UNCERTAIN,
        "new_repo_sha": None,  # deliberately not asserted — the backlog says it is conflated
        "source_item": "3D-NET-REFRESH-002",
        "note": "Backlog entry states repo_sha 53cb6be63d 'does not match the 61580eaa/76ee798c "
                "pair ... currently conflated' — head left unresolved (status=attempted) pending "
                "RPR-C-03 orphaned-sha resolution.",
    },
}


@dataclass
class ProvenanceRecord:
    family: str
    platform: str
    provenance: str
    new_repo_sha: str | None
    prior_repo_sha: str | None = None
    accepted_at: str | None = None
    source_item: str | None = None
    reconstruction_note: str | None = None
    ledger_written: bool = False
    skipped_existing: bool = False
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "platform": self.platform,
            "provenance": self.provenance,
            "new_repo_sha": self.new_repo_sha,
            "prior_repo_sha": self.prior_repo_sha,
            "accepted_at": self.accepted_at,
            "source_item": self.source_item,
            "reconstruction_note": self.reconstruction_note,
            "ledger_written": self.ledger_written,
            "skipped_existing": self.skipped_existing,
            "notes": self.notes,
        }


def read_model_repo_sha(merged_dir: Path) -> str | None:
    """Read repo_sha from a product's model.yaml, or None."""
    model = merged_dir / "model.yaml"
    if not model.is_file():
        return None
    try:
        import yaml
        data = yaml.safe_load(model.read_text(encoding="utf-8")) or {}
        sha = data.get("repo_sha")
        return str(sha) if sha else None
    except Exception:  # noqa: BLE001 — a malformed model.yaml is a NO_BASELINE signal, not a crash
        return None


def _git_commit_date(path: Path, repo_root: Path) -> str | None:
    """ISO date of the last commit touching path (proxy for 'when this baseline
    was promoted'), or None if unavailable."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "log", "-1", "--format=%cI", "--", str(path)],
            capture_output=True, text=True, timeout=30,
        )
        out = result.stdout.strip()
        return out or None
    except (OSError, subprocess.SubprocessError):
        return None


def classify_product(
    family: str,
    platform: str,
    *,
    attestation: dict[str, Any] | None,
    model_repo_sha: str | None,
    model_commit_date: str | None = None,
) -> ProvenanceRecord:
    """Classify one product's baseline provenance. Pure — no I/O."""
    if attestation:
        prov = attestation["provenance"]
        if prov == CONFIRMED:
            return ProvenanceRecord(
                family, platform, CONFIRMED,
                new_repo_sha=attestation.get("new_repo_sha") or model_repo_sha,
                prior_repo_sha=attestation.get("prior_repo_sha"),
                accepted_at=attestation.get("accepted_at"),
                source_item=attestation.get("source_item"),
                notes=attestation.get("note", ""),
            )
        if prov == UNCERTAIN:
            return ProvenanceRecord(
                family, platform, UNCERTAIN,
                new_repo_sha=attestation.get("new_repo_sha") or model_repo_sha,
                source_item=attestation.get("source_item"),
                notes=attestation.get("note", ""),
            )
        # An explicit RECONSTRUCTED/NO_BASELINE attestation falls through to signal logic.

    if model_repo_sha:
        return ProvenanceRecord(
            family, platform, RECONSTRUCTED,
            new_repo_sha=model_repo_sha,
            accepted_at=model_commit_date,
            reconstruction_note=(
                "No CLOSED backlog item attests this SHA; baseline reconstructed from the "
                "existing model.yaml.repo_sha scalar. accepted_at is the model.yaml last-commit "
                "date (best available proxy), not a verified acceptance timestamp."
            ),
        )
    return ProvenanceRecord(family, platform, NO_BASELINE, new_repo_sha=None,
                            notes="No model.yaml repo_sha; no ledger row written.")


def _write_ledger_row(rec: ProvenanceRecord, merged_dir: Path, run_id: str) -> bool:
    """Write the ledger row implied by a provenance record. Returns True if written."""
    ledger = BaselineLedger(rec.family, rec.platform, merged_dir=merged_dir)
    if rec.provenance in (CONFIRMED, RECONSTRUCTED):
        if not rec.new_repo_sha:
            return False
        ledger.append(
            run_id=run_id,
            new_repo_sha=rec.new_repo_sha,
            prior_repo_sha=rec.prior_repo_sha,
            sha_source="manual-recovery",
            status="accepted",
            accepted_at=rec.accepted_at or "2026-07-17T00:00:00Z",
        )
        return True
    if rec.provenance == UNCERTAIN:
        if not rec.new_repo_sha:
            # Head deliberately unresolved — record nothing rather than assert a conflated SHA.
            return False
        ledger.append(
            run_id=run_id,
            new_repo_sha=rec.new_repo_sha,
            sha_source="manual-recovery",
            status="attempted",  # NOT accepted — head stays unresolved
        )
        return True
    return False  # NO_BASELINE


def migrate(
    products: list[dict[str, Any]],
    *,
    attestations: dict[tuple[str, str], dict[str, Any]] | None = None,
    repo_root: Path,
    apply: bool = False,
    run_id: str = "MIGRATE-C04",
) -> list[ProvenanceRecord]:
    """Classify (and, if apply, backfill) every product's baseline provenance."""
    attestations = _CURATED_ATTESTATIONS if attestations is None else attestations
    records: list[ProvenanceRecord] = []
    for p in products:
        family, platform = p["family"], p["platform"]
        merged_dir = repo_root / "knowledge" / family / platform / "merged"
        model_sha = read_model_repo_sha(merged_dir)
        commit_date = _git_commit_date(merged_dir / "model.yaml", repo_root) if model_sha else None
        rec = classify_product(
            family, platform,
            attestation=attestations.get((family, platform)),
            model_repo_sha=model_sha,
            model_commit_date=commit_date,
        )
        # Idempotency: never double-seed a product that already has a ledger.
        if (merged_dir / "baseline_ledger.jsonl").exists():
            rec.skipped_existing = True
        elif apply:
            rec.ledger_written = _write_ledger_row(rec, merged_dir, run_id)
        records.append(rec)
    return records


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Backfill the baseline ledger for active products (RPR-C-04).")
    parser.add_argument("--apply", action="store_true", help="Write ledger rows (default: dry-run classify only)")
    parser.add_argument("--products", default="data/products.json", help="Active-product roster")
    parser.add_argument("--report", default="reports/baseline_migration/provenance.json",
                        help="Where to write the provenance classification report")
    parser.add_argument("--repo-root", default=str(_REPO_ROOT))
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root)
    products = json.loads((repo_root / args.products).read_text(encoding="utf-8"))
    records = migrate(products, repo_root=repo_root, apply=args.apply)

    report = {
        "mode": "apply" if args.apply else "dry-run",
        "total": len(records),
        "by_class": {
            c: sum(1 for r in records if r.provenance == c)
            for c in (CONFIRMED, RECONSTRUCTED, UNCERTAIN, NO_BASELINE)
        },
        "records": [r.to_dict() for r in records],
    }
    report_path = repo_root / args.report
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"[{report['mode']}] {report['total']} products classified: {report['by_class']}")
    print(f"report: {args.report}")
    # Hard guard on the plan's rule: nothing may be silently defaulted to CONFIRMED.
    confirmed_without_attestation = [
        r for r in records
        if r.provenance == CONFIRMED and (r.family, r.platform) not in _CURATED_ATTESTATIONS
    ]
    if confirmed_without_attestation:
        print("ERROR: a product was classified CONFIRMED without a curated attestation", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
