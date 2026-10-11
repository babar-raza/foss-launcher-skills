"""Focused tests for explicit-interval legacy refresh forensics."""
from __future__ import annotations

import refresh_run_forensics as rf


BASE = "---\ntitle: A\n---\n\nOriginal body.\n"
BODY_CHANGED = "---\ntitle: A\n---\n\nChanged body.\n"
FM_CHANGED = "---\ntitle: B\n---\n\nOriginal body.\n"


def _row(**overrides):
    row = {
        "page_path": "content/docs.aspose.org/en/pdf/net/page.md",
        "decision": "BODY_UPDATED",
    }
    row.update(overrides)
    return row


def test_wrong_base_window_precedes_real_change():
    disposition, evidence = rf.classify_row(
        _row(),
        base_text=BASE,
        claimed_base_text=BODY_CHANGED,
        end_text=BODY_CHANGED,
        current_text=BODY_CHANGED,
    )
    assert disposition == "WRONG_BASE_WINDOW"
    assert evidence["body_before"] != evidence["body_at_run_end"]


def test_real_body_change_is_git_founded():
    disposition, _ = rf.classify_row(
        _row(),
        base_text=BASE,
        end_text=BODY_CHANGED,
        current_text=BODY_CHANGED,
    )
    assert disposition == "REAL_BODY_CHANGE"


def test_generated_page_is_real_body_change():
    disposition, evidence = rf.classify_row(
        _row(),
        base_text=None,
        end_text=BODY_CHANGED,
        current_text=BODY_CHANGED,
    )
    assert disposition == "REAL_BODY_CHANGE"
    assert "generated" in evidence["reason"]


def test_frontmatter_only_is_distinct():
    disposition, _ = rf.classify_row(
        _row(),
        base_text=BASE,
        end_text=FM_CHANGED,
        current_text=FM_CHANGED,
    )
    assert disposition == "FRONTMATTER_ONLY"


def test_reverted_since_run_is_detected():
    disposition, _ = rf.classify_row(
        _row(),
        base_text=BASE,
        end_text=BODY_CHANGED,
        current_text=BASE,
    )
    assert disposition == "REVERTED_SINCE_RUN"


def test_unbound_unchanged_row_is_not_called_a_defect():
    disposition, _ = rf.classify_row(
        _row(),
        base_text=BASE,
        end_text=BASE,
        current_text=BASE,
    )
    assert disposition == "LEGACY_UNBOUND"


def test_schema_stamp_requires_explicit_evidence():
    disposition, _ = rf.classify_row(
        _row(schema_stamp_only=True),
        base_text=BASE,
        end_text=BASE,
        current_text=BASE,
    )
    assert disposition == "SCHEMA_STAMP_ONLY"


def test_current_defect_requires_truth_evidence_refs():
    disposition, _ = rf.classify_row(
        _row(),
        base_text=BASE,
        end_text=BASE,
        current_text=BASE,
        truth_defect={"verdict": "CURRENT_CONTENT_DEFECT"},
    )
    assert disposition == "UNKNOWN"

    disposition, evidence = rf.classify_row(
        _row(),
        base_text=BASE,
        end_text=BASE,
        current_text=BASE,
        truth_defect={
            "verdict": "CURRENT_CONTENT_DEFECT",
            "evidence_refs": ["reports/truth/page.json"],
        },
    )
    assert disposition == "CURRENT_CONTENT_DEFECT"
    assert evidence["truth_evidence_refs"]


def test_unsafe_page_path_is_rejected():
    try:
        rf._safe_page_path("../outside.md")
    except rf.ForensicError:
        pass
    else:
        raise AssertionError("unsafe path was accepted")
