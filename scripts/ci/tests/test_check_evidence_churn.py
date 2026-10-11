"""test_check_evidence_churn.py — Regression tests for check_evidence_churn.py

Covers the YAML-based classification in is_evidence_only_change() and the
EVIDENCE-RESTAMP override annotation. Sibling to test_check_grade_churn.py.
"""
import sys
from pathlib import Path

import pytest

# Bootstrap: add scripts/ci/checks/ to sys.path
_HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_HERE))

from checks.check_evidence_churn import (
    _BULK_ANNOTATION_RE,
    _split_frontmatter,
    bypass_is_verified,
    configure,
    is_evidence_only_change,
    verify_run_citation,
)


# ---------------------------------------------------------------------------
# Fixtures — representative page content (frontmatter + body)
# ---------------------------------------------------------------------------

_BODY = "\n# Text Extraction\n\nSome prose that never changes.\n"

_OLD_PAGE = f"""---
title: Text Extraction
provenance:
  auto_updatable: true
  content_hash: 2cd43cf857551a82a62ed3e9e765111b
evidence:
  model_sha: a07dbacb7036831d1474db33e261755868061108
  model_version: 0.1.0-alpha
  claims:
  - CLM-pdf-04f590
  - CLM-pdf-16b6c0
  apis:
  - Document
---{_BODY}"""

_NEW_PAGE_RESTAMP_ONLY = f"""---
title: Text Extraction
provenance:
  auto_updatable: true
  content_hash: 2cd43cf857551a82a62ed3e9e765111b
evidence:
  model_sha: d42e9f1ecdb12486cf79903e809afc471492b5e9
  model_version: 26.6.0
  claims:
  - CLM-pdf-04f590
  - CLM-pdf-16b6c0
  apis:
  - Document
---{_BODY}"""

# Realistic case (from the actual incident): orphaned claim silently dropped
# during re-stamp, body still untouched — this IS evidence-only churn.
_NEW_PAGE_ORPHAN_DROPPED = f"""---
title: Text Extraction
provenance:
  auto_updatable: true
  content_hash: 2cd43cf857551a82a62ed3e9e765111b
evidence:
  model_sha: d42e9f1ecdb12486cf79903e809afc471492b5e9
  model_version: 26.6.0
  claims:
  - CLM-pdf-04f590
  apis:
  - Document
---{_BODY}"""

_NEW_PAGE_BODY_CHANGED = f"""---
title: Text Extraction
provenance:
  auto_updatable: true
  content_hash: 9999999999999999999999999999999a
evidence:
  model_sha: d42e9f1ecdb12486cf79903e809afc471492b5e9
  model_version: 26.6.0
  claims:
  - CLM-pdf-04f590
  - CLM-pdf-16b6c0
  apis:
  - Document
---
# Text Extraction

Some prose that DID change this time.
"""

_NEW_PAGE_TITLE_CHANGED = f"""---
title: Text Extraction — Updated
provenance:
  auto_updatable: true
  content_hash: 2cd43cf857551a82a62ed3e9e765111b
evidence:
  model_sha: d42e9f1ecdb12486cf79903e809afc471492b5e9
  model_version: 26.6.0
  claims:
  - CLM-pdf-04f590
  - CLM-pdf-16b6c0
  apis:
  - Document
---{_BODY}"""

_NEW_PAGE_KEY_ADDED = f"""---
title: Text Extraction
provenance:
  auto_updatable: true
  content_hash: 2cd43cf857551a82a62ed3e9e765111b
evidence:
  model_sha: d42e9f1ecdb12486cf79903e809afc471492b5e9
  model_version: 26.6.0
  claims:
  - CLM-pdf-04f590
  - CLM-pdf-16b6c0
  apis:
  - Document
draft: true
---{_BODY}"""

_OLD_PAGE_WITH_GRADE = f"""---
title: Text Extraction
provenance:
  auto_updatable: true
  content_hash: 2cd43cf857551a82a62ed3e9e765111b
evidence:
  model_sha: a07dbacb7036831d1474db33e261755868061108
  model_version: 0.1.0-alpha
  claims:
  - CLM-pdf-04f590
  - CLM-pdf-16b6c0
  apis:
  - Document
grade: A
grade_reasons:
  - "No findings -> grade A"
---{_BODY}"""

# HARDEN-EC-01: evidence re-stamp with a co-occurring grade_reasons reword,
# body still untouched -- this IS evidence-only churn (grade is derived).
_NEW_PAGE_RESTAMP_WITH_GRADE_REASONS_CHANGE = f"""---
title: Text Extraction
provenance:
  auto_updatable: true
  content_hash: 2cd43cf857551a82a62ed3e9e765111b
evidence:
  model_sha: d42e9f1ecdb12486cf79903e809afc471492b5e9
  model_version: 26.6.0
  claims:
  - CLM-pdf-04f590
  - CLM-pdf-16b6c0
  apis:
  - Document
grade: A
grade_reasons:
  - "1 WARN finding(s) [audit] -> base grade A"
---{_BODY}"""

# Grade *letter* can also shift as a side effect of an evidence re-stamp
# (e.g. a new claim now grounds a previously-failing evaluator) -- still
# evidence-driven, still evidence-only for this guard's purposes.
_NEW_PAGE_RESTAMP_WITH_GRADE_LETTER_CHANGE = f"""---
title: Text Extraction
provenance:
  auto_updatable: true
  content_hash: 2cd43cf857551a82a62ed3e9e765111b
evidence:
  model_sha: d42e9f1ecdb12486cf79903e809afc471492b5e9
  model_version: 26.6.0
  claims:
  - CLM-pdf-04f590
  - CLM-pdf-16b6c0
  apis:
  - Document
grade: C
grade_reasons:
  - "No findings -> grade A"
---{_BODY}"""


# ---------------------------------------------------------------------------
# is_evidence_only_change() tests
# ---------------------------------------------------------------------------


def test_pure_restamp_is_evidence_only():
    """model_sha/model_version bump, body untouched -> evidence-only."""
    assert is_evidence_only_change(_OLD_PAGE, _NEW_PAGE_RESTAMP_ONLY)


def test_orphan_claim_dropped_is_still_evidence_only():
    """Silent orphan-claim drop during re-stamp (real attach_evidence.py
    behavior) with an unchanged body is still evidence-only churn."""
    assert is_evidence_only_change(_OLD_PAGE, _NEW_PAGE_ORPHAN_DROPPED)


def test_body_change_is_not_evidence_only():
    """A body prose change disqualifies the file, even with a real model bump."""
    assert not is_evidence_only_change(_OLD_PAGE, _NEW_PAGE_BODY_CHANGED)


def test_non_evidence_frontmatter_change_is_not_evidence_only():
    """A title change alongside the model bump disqualifies the file."""
    assert not is_evidence_only_change(_OLD_PAGE, _NEW_PAGE_TITLE_CHANGED)


def test_added_top_level_key_is_not_evidence_only():
    """Adding a new top-level frontmatter key (e.g. draft:) disqualifies the file."""
    assert not is_evidence_only_change(_OLD_PAGE, _NEW_PAGE_KEY_ADDED)


def test_grade_reasons_change_alongside_evidence_is_still_evidence_only():
    """HARDEN-EC-01: a grade_reasons reword riding on the same evidence
    re-stamp must not disqualify the file -- grade is derived, not editorial."""
    assert is_evidence_only_change(
        _OLD_PAGE_WITH_GRADE, _NEW_PAGE_RESTAMP_WITH_GRADE_REASONS_CHANGE
    )


def test_grade_letter_change_alongside_evidence_is_still_evidence_only():
    """A grade letter shift (e.g. C -> A from a newly-grounding claim) is
    also a derived side effect of the evidence change, not disqualifying."""
    assert is_evidence_only_change(
        _OLD_PAGE_WITH_GRADE, _NEW_PAGE_RESTAMP_WITH_GRADE_LETTER_CHANGE
    )


def test_identical_content_is_not_evidence_only():
    """No diff at all is not a churn candidate."""
    assert not is_evidence_only_change(_OLD_PAGE, _OLD_PAGE)


def test_missing_old_text_is_not_evidence_only():
    """A new file (no old revision) cannot be evidence-only churn."""
    assert not is_evidence_only_change(None, _NEW_PAGE_RESTAMP_ONLY)


def test_missing_new_text_is_not_evidence_only():
    assert not is_evidence_only_change(_OLD_PAGE, None)


def test_no_frontmatter_is_not_evidence_only():
    """A file without --- delimited frontmatter never classifies as evidence-only."""
    assert not is_evidence_only_change("plain body text, no frontmatter", "different plain body text")


# ---------------------------------------------------------------------------
# _split_frontmatter() tests
# ---------------------------------------------------------------------------


def test_split_frontmatter_basic():
    fm, body = _split_frontmatter(_OLD_PAGE)
    assert fm is not None
    assert "model_sha" in fm
    assert body == _BODY


def test_split_frontmatter_no_delimiter():
    fm, body = _split_frontmatter("# Just a heading\n\nNo frontmatter here.\n")
    assert fm is None


# ---------------------------------------------------------------------------
# _BULK_ANNOTATION_RE tests
# ---------------------------------------------------------------------------


def test_bulk_annotation_match():
    text = "EVIDENCE-RESTAMP: approved by admin on 2026-07-16, reason: knowledge model regen"
    assert _BULK_ANNOTATION_RE.search(text)


def test_bulk_annotation_lowercase_match():
    text = "evidence-restamp: approved by admin"
    assert _BULK_ANNOTATION_RE.search(text)


def test_bulk_annotation_not_matched_without_approved_by():
    text = "EVIDENCE-RESTAMP: some other text"
    assert not _BULK_ANNOTATION_RE.search(text)


# ---------------------------------------------------------------------------
# G14 hardening tests (mission-plan-the-end-to-end-vast-hejlsberg.md Task 22):
# the bypass must cite a real, verified run -- not just matching text.
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_repo_root():
    yield
    configure()


def _write_manifest(tmp_path, family, platform, run_id, *, state):
    run_root = tmp_path / "reports" / "refresh_runs" / family / platform / run_id
    run_root.mkdir(parents=True, exist_ok=True)
    import json
    (run_root / "manifest.json").write_text(json.dumps({"state": state}), encoding="utf-8")
    return f"reports/refresh_runs/{family}/{platform}/{run_id}"


class TestVerifyRunCitation:
    def test_verified_when_state_is_validating(self, tmp_path):
        configure(repo_root=tmp_path)
        ref = _write_manifest(tmp_path, "pdf", "java", "run-1", state="VALIDATING")
        ok, reason = verify_run_citation(ref)
        assert ok
        assert "VALIDATING" in reason

    def test_verified_when_state_is_committed(self, tmp_path):
        configure(repo_root=tmp_path)
        ref = _write_manifest(tmp_path, "pdf", "java", "run-1", state="COMMITTED")
        ok, _ = verify_run_citation(ref)
        assert ok

    def test_not_verified_when_state_is_planned(self, tmp_path):
        """The exact scenario this hardening exists for: a run cited before it
        actually did any real reconciliation work is not evidence of anything."""
        configure(repo_root=tmp_path)
        ref = _write_manifest(tmp_path, "pdf", "java", "run-1", state="PLANNED")
        ok, reason = verify_run_citation(ref)
        assert not ok
        assert "PLANNED" in reason

    def test_not_verified_when_manifest_missing(self, tmp_path):
        configure(repo_root=tmp_path)
        ok, reason = verify_run_citation("reports/refresh_runs/pdf/java/does-not-exist")
        assert not ok
        assert "not found" in reason

    def test_accepts_explicit_manifest_json_suffix(self, tmp_path):
        configure(repo_root=tmp_path)
        ref = _write_manifest(tmp_path, "pdf", "java", "run-1", state="VALIDATING")
        ok, _ = verify_run_citation(ref + "/manifest.json")
        assert ok


class TestBypassIsVerified:
    def test_no_annotation_at_all_is_not_granted(self, tmp_path):
        configure(repo_root=tmp_path)
        granted, reason = bypass_is_verified("just a normal commit message")
        assert not granted
        assert "no EVIDENCE-RESTAMP" in reason

    def test_annotation_without_run_citation_is_not_granted(self, tmp_path):
        """This is the exact gap this hardening closes: the pre-hardening
        behavior granted an unconditional bypass on this exact text."""
        configure(repo_root=tmp_path)
        granted, reason = bypass_is_verified(
            "EVIDENCE-RESTAMP: approved by someone on 2026-08-22, reason: because I said so"
        )
        assert not granted
        assert "no run=" in reason

    def test_annotation_with_verified_run_is_granted(self, tmp_path):
        configure(repo_root=tmp_path)
        ref = _write_manifest(tmp_path, "pdf", "java", "run-1", state="READY_TO_COMMIT")
        granted, reason = bypass_is_verified(
            f"EVIDENCE-RESTAMP: approved by X on 2026-08-22, reason: real refresh, run={ref}"
        )
        assert granted
        assert "READY_TO_COMMIT" in reason

    def test_annotation_with_unverified_run_is_not_granted(self, tmp_path):
        configure(repo_root=tmp_path)
        ref = _write_manifest(tmp_path, "pdf", "java", "run-1", state="APPLYING")
        granted, reason = bypass_is_verified(
            f"EVIDENCE-RESTAMP: approved by X on 2026-08-22, reason: too early, run={ref}"
        )
        assert not granted
        assert "APPLYING" in reason
