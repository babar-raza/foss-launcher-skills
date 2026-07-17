"""
Tests for the 5 refresh-pipeline schema validators added to
scripts/pipeline/lib/schema_validators.py (RPR-B-01/02/03,
aspose-org-foss-refresh-tidy-lightning).
"""

from lib.schema_validators import (
    validate_baseline_ledger_entry,
    validate_page_coverage_ledger_entry,
    validate_page_patch_receipt,
    validate_product_change_record,
    validate_refresh_run_manifest,
    validate_taskcard_record,
)


# ── baseline_ledger_entry ────────────────────────────────────────────────

def _valid_ledger_entry(**overrides):
    entry = {
        "run_id": "RUN-001",
        "family": "pdf",
        "platform": "net",
        "prior_repo_sha": "aaa",
        "new_repo_sha": "bbb",
        "sha_source": "scout",
        "attempt_started_at": "2026-07-16T00:00:00Z",
        "accepted_at": "2026-07-16T00:05:00Z",
        "status": "accepted",
    }
    entry.update(overrides)
    return entry


def test_valid_baseline_ledger_entry_passes():
    assert validate_baseline_ledger_entry(_valid_ledger_entry()) == []


def test_baseline_ledger_entry_missing_required_field_fails():
    entry = _valid_ledger_entry()
    del entry["new_repo_sha"]
    errors = validate_baseline_ledger_entry(entry)
    assert any("new_repo_sha" in e for e in errors)


def test_baseline_ledger_entry_invalid_sha_source_fails():
    errors = validate_baseline_ledger_entry(_valid_ledger_entry(sha_source="made-up"))
    assert any("sha_source" in e for e in errors)


def test_baseline_ledger_entry_accepted_without_accepted_at_fails():
    entry = _valid_ledger_entry(status="accepted")
    del entry["accepted_at"]
    errors = validate_baseline_ledger_entry(entry)
    assert any("accepted_at" in e for e in errors)


def test_baseline_ledger_entry_orphaned_without_orphaned_sha_fails():
    errors = validate_baseline_ledger_entry(
        _valid_ledger_entry(sha_source="orphaned-recovered", status="attempted")
    )
    assert any("orphaned_sha" in e for e in errors)


def test_baseline_ledger_entry_orphaned_with_orphaned_sha_passes():
    errors = validate_baseline_ledger_entry(
        _valid_ledger_entry(sha_source="orphaned-recovered", status="attempted", orphaned_sha="ccc")
    )
    assert errors == []


# ── product_change_record ────────────────────────────────────────────────

def _valid_change_record(**overrides):
    record = {
        "change_id": "CHG-001",
        "change_type": "FEATURE_ADDED",
        "api_symbol": "Document.Save",
        "baseline_ref": "RUN-001",
        "routed_strategy": "PARAGRAPH_REWRITE",
        "classification_confidence": 0.9,
        "requires_llm": True,
    }
    record.update(overrides)
    return record


def test_valid_product_change_record_passes():
    assert validate_product_change_record(_valid_change_record()) == []


def test_product_change_record_invalid_change_type_fails():
    errors = validate_product_change_record(_valid_change_record(change_type="NOT_A_TYPE"))
    assert any("change_type" in e for e in errors)


def test_product_change_record_confidence_out_of_range_fails():
    errors = validate_product_change_record(_valid_change_record(classification_confidence=1.5))
    assert any("classification_confidence" in e for e in errors)


def test_product_change_record_requires_llm_inconsistent_with_strategy_fails():
    # PARAGRAPH_REWRITE must have requires_llm=True; this record claims False.
    errors = validate_product_change_record(
        _valid_change_record(routed_strategy="PARAGRAPH_REWRITE", requires_llm=False)
    )
    assert any("requires_llm" in e for e in errors)


def test_product_change_record_requires_llm_false_for_deterministic_strategy_passes():
    errors = validate_product_change_record(
        _valid_change_record(
            change_type="API_REMOVED",
            routed_strategy="SECTION_REMOVAL",
            requires_llm=False,
        )
    )
    assert errors == []


# ── page_coverage_ledger_entry ───────────────────────────────────────────

def _valid_coverage_entry(**overrides):
    entry = {
        "page_id": "content/docs.aspose.org/en/pdf/net/page.md",
        "decision": "BODY_UPDATED",
        "decision_reason": "cited claim CLM-001 modified",
        "decision_source": "pia_per_page_citation",
        "evidence_claims_checked": ["CLM-001"],
        "evidence_apis_checked": [],
        "body_diff_hash_before": "sha256:aaa",
        "body_diff_hash_after": "sha256:bbb",
        "frontmatter_only": False,
        "blocking": False,
    }
    entry.update(overrides)
    return entry


def test_valid_page_coverage_ledger_entry_passes():
    assert validate_page_coverage_ledger_entry(_valid_coverage_entry()) == []


def test_page_coverage_ledger_entry_invalid_decision_fails():
    errors = validate_page_coverage_ledger_entry(_valid_coverage_entry(decision="MADE_UP"))
    assert any("decision" in e for e in errors)


def test_page_coverage_ledger_entry_body_updated_with_identical_hash_fails():
    """This is the exact PDF-NET-REFRESH-001 v26.7.0 regression pattern:
    a page recorded BODY_UPDATED whose body content did not actually change."""
    errors = validate_page_coverage_ledger_entry(
        _valid_coverage_entry(body_diff_hash_before="sha256:same", body_diff_hash_after="sha256:same")
    )
    assert any("body_diff_hash_before == body_diff_hash_after" in e for e in errors)


def test_page_coverage_ledger_entry_body_updated_with_frontmatter_only_true_fails():
    errors = validate_page_coverage_ledger_entry(_valid_coverage_entry(frontmatter_only=True))
    assert any("frontmatter_only" in e for e in errors)


def test_page_coverage_ledger_entry_evidence_only_with_identical_hash_passes():
    errors = validate_page_coverage_ledger_entry(
        _valid_coverage_entry(
            decision="EVIDENCE_ONLY",
            body_diff_hash_before="sha256:same",
            body_diff_hash_after="sha256:same",
            frontmatter_only=True,
        )
    )
    assert errors == []


# ── page_patch_receipt ───────────────────────────────────────────────────

def _valid_receipt(**overrides):
    receipt = {
        "receipt_id": "RCP-001",
        "run_id": "RUN-001",
        "page_path": "content/docs.aspose.org/en/pdf/net/page.md",
        "locale": "en",
        "change_ids": ["CHG-001"],
        "strategy_used": "PARAGRAPH_REWRITE",
        "old_hash": "sha256:aaa",
        "new_hash": "sha256:bbb",
        "verdict": "BODY_UPDATED",
        "llm_invoked": True,
        "template_fallback_used": False,
    }
    receipt.update(overrides)
    return receipt


def test_valid_page_patch_receipt_passes():
    assert validate_page_patch_receipt(_valid_receipt()) == []


def test_page_patch_receipt_paragraph_rewrite_missing_observability_fields_fails():
    receipt = _valid_receipt()
    del receipt["llm_invoked"]
    del receipt["template_fallback_used"]
    errors = validate_page_patch_receipt(receipt)
    assert any("llm_invoked and template_fallback_used" in e for e in errors)


def test_page_patch_receipt_both_llm_and_template_true_fails():
    """RPR-E-01 regression guard: a receipt cannot claim both paths fired."""
    errors = validate_page_patch_receipt(
        _valid_receipt(llm_invoked=True, template_fallback_used=True)
    )
    assert any("exactly one" in e for e in errors)


def test_page_patch_receipt_invalid_fallback_reason_fails():
    """RPR-E-05: fallback_reason must be one of the known enum values."""
    errors = validate_page_patch_receipt(_valid_receipt(fallback_reason="MADE_UP"))
    assert any("invalid fallback_reason" in e for e in errors)


def test_page_patch_receipt_template_fired_requires_reason():
    """RPR-E-05: template_fallback_used=True with fallback_reason=NONE is contradictory —
    if the template fired, the receipt must say WHY."""
    errors = validate_page_patch_receipt(
        _valid_receipt(llm_invoked=False, template_fallback_used=True, fallback_reason="NONE")
    )
    assert any("requires a fallback_reason" in e for e in errors)


def test_page_patch_receipt_template_with_circuit_open_passes():
    errors = validate_page_patch_receipt(
        _valid_receipt(llm_invoked=False, template_fallback_used=True, fallback_reason="CIRCUIT_OPEN")
    )
    assert errors == []


def test_page_patch_receipt_llm_invoked_with_fallback_reason_inconsistent():
    """If the LLM's output was used, fallback_reason cannot name a fallback cause."""
    errors = validate_page_patch_receipt(
        _valid_receipt(llm_invoked=True, template_fallback_used=False, fallback_reason="LLM_ERROR")
    )
    assert any("inconsistent with fallback_reason" in e for e in errors)


def test_page_patch_receipt_neither_llm_nor_template_fails():
    errors = validate_page_patch_receipt(
        _valid_receipt(llm_invoked=False, template_fallback_used=False)
    )
    assert any("exactly one" in e for e in errors)


def test_page_patch_receipt_deterministic_strategy_does_not_require_llm_fields():
    receipt = _valid_receipt(strategy_used="SECTION_REMOVAL")
    del receipt["llm_invoked"]
    del receipt["template_fallback_used"]
    assert validate_page_patch_receipt(receipt) == []


# ── refresh_run_manifest ─────────────────────────────────────────────────

def _valid_manifest(**overrides):
    manifest = {
        "run_id": "RUN-001",
        "family": "pdf",
        "platform": "net",
        "started_at": "2026-07-16T00:00:00Z",
        "baseline_ledger_ref": "RUN-001",
        "product_change_refs": ["CHG-001"],
        "page_coverage_ledger_ref": "RUN-001",
        "patch_receipt_refs": ["RCP-001"],
        "validation": {
            "post_refresh_verify": "PASS",
            "oracle": "PASS",
            "triage_confirm": "PASS",
            "seo_stability": "PASS",
        },
        "status": "committed",
        "commit_sha": "abc123",
    }
    manifest.update(overrides)
    return manifest


def test_valid_refresh_run_manifest_passes():
    assert validate_refresh_run_manifest(_valid_manifest()) == []


def test_refresh_run_manifest_committed_without_commit_sha_fails():
    manifest = _valid_manifest()
    del manifest["commit_sha"]
    errors = validate_refresh_run_manifest(manifest)
    assert any("commit_sha" in e for e in errors)


def test_refresh_run_manifest_committed_with_failed_validation_fails():
    """Plan §13 rollback rule: a partially-failed run must never be status=committed."""
    manifest = _valid_manifest()
    manifest["validation"]["oracle"] = "FAIL"
    errors = validate_refresh_run_manifest(manifest)
    assert any("not every validation field is PASS" in e for e in errors)


def test_refresh_run_manifest_commit_sha_without_committed_status_fails():
    errors = validate_refresh_run_manifest(_valid_manifest(status="blocked"))
    assert any("commit_sha is set but status" in e for e in errors)


def test_refresh_run_manifest_in_progress_without_commit_sha_passes():
    manifest = _valid_manifest(status="in_progress")
    del manifest["commit_sha"]
    manifest["validation"] = {
        "post_refresh_verify": "PASS", "oracle": "PASS",
        "triage_confirm": "FAIL", "seo_stability": "PASS",
    }
    assert validate_refresh_run_manifest(manifest) == []


def test_refresh_run_manifest_intentional_renames_must_be_list():
    """RPR-F-05: intentional_renames is optional, but when present must be a list."""
    manifest = _valid_manifest(status="in_progress")
    del manifest["commit_sha"]
    manifest["intentional_renames"] = "content/p.md"  # string, not a list
    errors = validate_refresh_run_manifest(manifest)
    assert any("intentional_renames" in e for e in errors)


def test_refresh_run_manifest_intentional_renames_list_passes():
    manifest = _valid_manifest(status="in_progress")
    del manifest["commit_sha"]
    manifest["intentional_renames"] = ["content/p.md", "content/q.md"]
    assert validate_refresh_run_manifest(manifest) == []


def test_refresh_run_manifest_invalid_validation_value_fails():
    manifest = _valid_manifest(status="in_progress")
    del manifest["commit_sha"]
    manifest["validation"]["oracle"] = "MAYBE"
    errors = validate_refresh_run_manifest(manifest)
    assert any("must be PASS or FAIL" in e for e in errors)


def test_refresh_run_manifest_base_commit_sha_optional_absent_passes():
    """RPR-J-17: base_commit_sha is optional -- a manifest without it is still valid."""
    assert validate_refresh_run_manifest(_valid_manifest()) == []


def test_refresh_run_manifest_base_commit_sha_string_passes():
    manifest = _valid_manifest(base_commit_sha="8a3131b9a6f7e97c20214896c615dbee86272459")
    assert validate_refresh_run_manifest(manifest) == []


def test_refresh_run_manifest_base_commit_sha_null_passes():
    """An explicit null is treated the same as absent (no captured baseline yet)."""
    manifest = _valid_manifest(base_commit_sha=None)
    assert validate_refresh_run_manifest(manifest) == []


def test_refresh_run_manifest_base_commit_sha_wrong_type_fails():
    manifest = _valid_manifest(base_commit_sha=12345)
    errors = validate_refresh_run_manifest(manifest)
    assert any("base_commit_sha" in e for e in errors)


def test_refresh_run_manifest_base_commit_sha_empty_string_fails():
    manifest = _valid_manifest(base_commit_sha="")
    errors = validate_refresh_run_manifest(manifest)
    assert any("base_commit_sha" in e and "empty" in e for e in errors)


# ── enum-drift guard (RPR-B-02's originally-specified enum-match test, added
#    RPR-D-03 after the integration caught a missing decision value) ──────────

def test_page_coverage_decisions_match_refresh_review_source():
    """The schema's accepted page-coverage decisions MUST equal refresh_review's
    live VALID_DECISIONS constant, byte-for-byte. If they drift, a decision that
    refresh_review.record_decision() accepts would be rejected by the schema
    validator (or vice versa) — the exact failure that surfaced
    EXISTING_IMPACTED_PAGES_UPDATED_VERIFIED missing from the schema when
    RPR-D-03 first wired the two together."""
    import sys
    from pathlib import Path
    _ops = Path(__file__).resolve().parents[1] / "commands" / "ops"
    if str(_ops) not in sys.path:
        sys.path.insert(0, str(_ops))
    import refresh_review
    from lib.schema_validators import _PAGE_COVERAGE_DECISIONS

    assert set(_PAGE_COVERAGE_DECISIONS) == set(refresh_review.VALID_DECISIONS), (
        "schema _PAGE_COVERAGE_DECISIONS has drifted from refresh_review.VALID_DECISIONS; "
        f"schema-only={set(_PAGE_COVERAGE_DECISIONS) - set(refresh_review.VALID_DECISIONS)}, "
        f"source-only={set(refresh_review.VALID_DECISIONS) - set(_PAGE_COVERAGE_DECISIONS)}"
    )


# ── taskcard_record (schema 5f, RPR-G-04 / §2.5 SW-4) ─────────────────────

def _valid_taskcard(**overrides):
    tc = {
        "task_id": "RPR-A-01",
        "mission_id": "aspose-org-foss-refresh-tidy-lightning",
        "status": "TODO",
        "recorded_at": "2026-07-17T00:00:00Z",
        "evidence_refs": [],
        "recorded_by": "session-4",
    }
    tc.update(overrides)
    return tc


def test_valid_taskcard_todo_passes():
    assert validate_taskcard_record(_valid_taskcard()) == []


def test_taskcard_missing_required_field_fails():
    tc = _valid_taskcard()
    del tc["recorded_by"]
    errors = validate_taskcard_record(tc)
    assert any("recorded_by" in e for e in errors)


def test_taskcard_invalid_status_fails():
    errors = validate_taskcard_record(_valid_taskcard(status="DEFINITELY_DONE"))
    assert any("invalid status" in e for e in errors)


def test_taskcard_evidence_refs_must_be_list():
    errors = validate_taskcard_record(_valid_taskcard(evidence_refs="scripts/x.py"))
    assert any("evidence_refs" in e for e in errors)


def test_taskcard_verified_status_requires_evidence():
    """The core SW-4 rule: a status past IMPLEMENTED with no evidence is rejected —
    the exact shape of TC-W11-001.C7 claiming progress while citing nothing."""
    errors = validate_taskcard_record(_valid_taskcard(status="FOCUSED_VERIFIED", evidence_refs=[]))
    assert any("requires a non-empty evidence_refs" in e for e in errors)


def test_taskcard_verified_status_with_evidence_passes():
    tc = _valid_taskcard(status="CLOSED", evidence_refs=["scripts/x.py", "test_x.py"])
    assert validate_taskcard_record(tc) == []


def test_taskcard_implemented_does_not_require_evidence():
    """IMPLEMENTED = code written, not yet verified — evidence not yet required."""
    assert validate_taskcard_record(_valid_taskcard(status="IMPLEMENTED", evidence_refs=[])) == []


def test_taskcard_blocked_status_does_not_require_evidence():
    assert validate_taskcard_record(_valid_taskcard(status="BLOCKED_EXTERNAL", evidence_refs=[])) == []


def test_this_missions_taskcards_file_is_schema_valid():
    """The plan's own live taskcards.jsonl (RPR-G-04 step 2) must validate — it is
    the mission's own first test case per the plan's acceptance criteria."""
    import json
    from pathlib import Path
    repo_root = Path(__file__).resolve().parents[3]
    store = repo_root / "reports" / "plan_state" / "aspose-org-foss-refresh-tidy-lightning" / "taskcards.jsonl"
    if not store.is_file():
        import pytest
        pytest.skip("mission taskcards.jsonl not present")
    rows = 0
    for line in store.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows += 1
        errs = validate_taskcard_record(json.loads(line))
        assert errs == [], f"invalid taskcard row: {errs}"
    assert rows >= 1
