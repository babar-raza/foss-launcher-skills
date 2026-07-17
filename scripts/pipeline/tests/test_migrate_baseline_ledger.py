"""Tests for migrate_baseline_ledger.py (RPR-C-04) — one fixture per provenance class."""
import json
import sys
from pathlib import Path

import pytest

_KNOW = Path(__file__).resolve().parents[1] / "commands" / "knowledge"
if str(_KNOW) not in sys.path:
    sys.path.insert(0, str(_KNOW))

import migrate_baseline_ledger as mig  # noqa: E402
from lib.baseline_ledger import BaselineLedger  # noqa: E402


def _make_model(repo_root, family, platform, repo_sha):
    merged = repo_root / "knowledge" / family / platform / "merged"
    merged.mkdir(parents=True, exist_ok=True)
    if repo_sha is not None:
        (merged / "model.yaml").write_text(f"repo_sha: {repo_sha}\n", encoding="utf-8")
    return merged


# ── classify_product (pure) ───────────────────────────────────────────────

def test_classify_confirmed():
    att = {"provenance": mig.CONFIRMED, "new_repo_sha": "abc", "prior_repo_sha": "aaa",
           "accepted_at": "2026-07-16T00:00:00Z", "source_item": "PDF-NET-REFRESH-001"}
    rec = mig.classify_product("pdf", "net", attestation=att, model_repo_sha="abc")
    assert rec.provenance == mig.CONFIRMED
    assert rec.new_repo_sha == "abc" and rec.source_item == "PDF-NET-REFRESH-001"


def test_classify_reconstructed_when_sha_but_no_attestation():
    rec = mig.classify_product("cells", "java", attestation=None, model_repo_sha="deadbeef",
                               model_commit_date="2026-05-01T00:00:00Z")
    assert rec.provenance == mig.RECONSTRUCTED
    assert rec.new_repo_sha == "deadbeef"
    assert rec.accepted_at == "2026-05-01T00:00:00Z"
    assert "reconstructed" in rec.reconstruction_note.lower()


def test_classify_uncertain_leaves_head_unasserted():
    att = {"provenance": mig.UNCERTAIN, "new_repo_sha": None, "source_item": "3D-NET-REFRESH-002",
           "note": "conflated"}
    rec = mig.classify_product("3d", "net", attestation=att, model_repo_sha="53cb6be63d")
    assert rec.provenance == mig.UNCERTAIN
    # The conflated model.yaml sha is used as a hint but is NOT asserted as accepted.
    assert rec.new_repo_sha in (None, "53cb6be63d")
    assert rec.accepted_at is None


def test_classify_no_baseline_when_no_sha():
    rec = mig.classify_product("new", "product", attestation=None, model_repo_sha=None)
    assert rec.provenance == mig.NO_BASELINE
    assert rec.new_repo_sha is None


# ── migrate() end-to-end with ledger writes ───────────────────────────────

def test_migrate_apply_writes_expected_rows_per_class(tmp_path):
    _make_model(tmp_path, "pdf", "net", "8a3131b9a6")
    _make_model(tmp_path, "cells", "java", "deadbeef")
    _make_model(tmp_path, "3d", "net", "53cb6be63d")
    _make_model(tmp_path, "empty", "prod", None)  # no repo_sha -> NO_BASELINE
    products = [
        {"family": "pdf", "platform": "net"},
        {"family": "cells", "platform": "java"},
        {"family": "3d", "platform": "net"},
        {"family": "empty", "platform": "prod"},
    ]
    attestations = {
        ("pdf", "net"): {"provenance": mig.CONFIRMED, "new_repo_sha": "8a3131b9a6",
                         "prior_repo_sha": "d42e9f1ec", "accepted_at": "2026-07-16T00:00:00Z",
                         "source_item": "PDF-NET-REFRESH-001"},
        ("3d", "net"): {"provenance": mig.UNCERTAIN, "new_repo_sha": "53cb6be63d",
                        "source_item": "3D-NET-REFRESH-002", "note": "conflated"},
    }
    records = mig.migrate(products, attestations=attestations, repo_root=tmp_path, apply=True)
    by = {(r.family, r.platform): r for r in records}

    # CONFIRMED -> accepted/manual-recovery
    conf = BaselineLedger("pdf", "net", merged_dir=tmp_path / "knowledge/pdf/net/merged").last_accepted()
    assert conf is not None and conf["sha_source"] == "manual-recovery" and conf["new_repo_sha"] == "8a3131b9a6"
    assert by[("pdf", "net")].provenance == mig.CONFIRMED and by[("pdf", "net")].ledger_written

    # RECONSTRUCTED -> accepted/manual-recovery + note
    rec = BaselineLedger("cells", "java", merged_dir=tmp_path / "knowledge/cells/java/merged").last_accepted()
    assert rec is not None and rec["sha_source"] == "manual-recovery"
    assert by[("cells", "java")].provenance == mig.RECONSTRUCTED
    assert by[("cells", "java")].reconstruction_note

    # UNCERTAIN -> attempted (NOT accepted); last_accepted() must be None
    led = BaselineLedger("3d", "net", merged_dir=tmp_path / "knowledge/3d/net/merged")
    assert led.last_accepted() is None
    assert led.history() and led.history()[-1]["status"] == "attempted"

    # NO_BASELINE -> no ledger file at all
    assert not (tmp_path / "knowledge/empty/prod/merged/baseline_ledger.jsonl").exists()
    assert by[("empty", "prod")].provenance == mig.NO_BASELINE


def test_migrate_dry_run_writes_no_ledger(tmp_path):
    _make_model(tmp_path, "pdf", "net", "8a3131b9a6")
    products = [{"family": "pdf", "platform": "net"}]
    records = mig.migrate(products, attestations={}, repo_root=tmp_path, apply=False)
    assert not (tmp_path / "knowledge/pdf/net/merged/baseline_ledger.jsonl").exists()
    assert records[0].ledger_written is False


def test_migrate_is_idempotent_skips_existing_ledger(tmp_path):
    merged = _make_model(tmp_path, "pdf", "net", "8a3131b9a6")
    products = [{"family": "pdf", "platform": "net"}]
    mig.migrate(products, attestations={}, repo_root=tmp_path, apply=True)
    # Second run must skip (not append a duplicate).
    n_before = len(BaselineLedger("pdf", "net", merged_dir=merged).history())
    records = mig.migrate(products, attestations={}, repo_root=tmp_path, apply=True)
    n_after = len(BaselineLedger("pdf", "net", merged_dir=merged).history())
    assert n_before == n_after
    assert records[0].skipped_existing is True


def test_no_product_silently_defaults_to_confirmed(tmp_path):
    """The plan's §13 hard rule: nothing without a curated attestation may be CONFIRMED."""
    _make_model(tmp_path, "words", "python", "cafe1234")
    products = [{"family": "words", "platform": "python"}]
    records = mig.migrate(products, attestations={}, repo_root=tmp_path, apply=True)
    assert records[0].provenance == mig.RECONSTRUCTED  # NOT CONFIRMED
