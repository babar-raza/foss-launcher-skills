"""Tests for scripts/seo/pipeline/autonomy_state.py (SEO-AUTONOMY-STATE-MACHINE,
Contract I). Synthetic transitions only -- this test suite never grants a real
family/mechanism HUMAN_CLEARED status; that boundary is orthogonal to what
this module's own correctness requires."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT / "scripts" / "seo" / "pipeline"))
import autonomy_state as az  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_state(tmp_path, monkeypatch):
    """Every test gets its own throwaway repo root / state file -- never the
    real data/seo_autonomy_state.json."""
    az.configure(repo_root=tmp_path)
    yield
    az.configure(repo_root=None)


def _state_path(tmp_path):
    return tmp_path / "data" / "seo_autonomy_state.json"


# --- load/save --------------------------------------------------------------

def test_load_state_missing_file_returns_empty_dict():
    assert az.load_state() == {}


def test_save_then_load_round_trips(tmp_path):
    state = {"tex": {"schema_a_refresh": {"status": "AUTONOMOUSLY_ELIGIBLE"}}}
    az.save_state_atomic(state)
    assert az.load_state() == state


def test_save_state_atomic_uses_tempfile_and_replace(tmp_path, monkeypatch):
    """Regression guard: a crash mid-write must never leave a partially
    written file -- simulate os.replace failing and confirm no corrupt file
    is left behind, mirroring migrate_platform_labels.py's own test."""
    import os as _os

    real_replace = _os.replace

    def boom(*a, **k):
        raise OSError("simulated crash during os.replace")

    monkeypatch.setattr(_os, "replace", boom)
    with pytest.raises(OSError):
        az.save_state_atomic({"tex": {}})
    monkeypatch.setattr(_os, "replace", real_replace)
    assert not _state_path(Path(az.REPO_ROOT)).exists()
    # No leftover .tmp files either.
    data_dir = Path(az.REPO_ROOT) / "data"
    leftovers = list(data_dir.glob(".seo_autonomy_state_*.tmp")) if data_dir.exists() else []
    assert leftovers == []


def test_load_state_rejects_non_dict_top_level(tmp_path):
    path = _state_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(az.AutonomyStateError):
        az.load_state()


# --- get_record / get_status / is_autonomously_eligible ---------------------

def test_get_record_defaults_to_unreviewed_for_missing_pair():
    record = az.get_record("pdf", "title_description_writes")
    assert record["status"] == az.STATUS_UNREVIEWED
    assert record["transitioned_at"] is None
    assert record["last_reviewed_sha"] is None


def test_is_autonomously_eligible_false_by_default():
    assert az.is_autonomously_eligible("pdf", "title_description_writes") is False


def test_is_autonomously_eligible_true_after_real_transition_chain():
    az.transition("pdf", "title_description_writes", az.STATUS_REVIEW_PENDING,
                   reason="queued", actor="test")
    az.transition("pdf", "title_description_writes", az.STATUS_HUMAN_CLEARED,
                   reason="cleared", actor="independent-reviewer-agent", source_sha="deadbeef")
    az.transition("pdf", "title_description_writes", az.STATUS_AUTONOMOUSLY_ELIGIBLE,
                   reason="promoted", actor="autonomy-state-machine")
    assert az.is_autonomously_eligible("pdf", "title_description_writes") is True
    # A different, never-touched mechanism for the same family stays UNREVIEWED.
    assert az.is_autonomously_eligible("pdf", "schema_a_refresh") is False


# --- transition() legality ---------------------------------------------------

@pytest.mark.parametrize("to_status", [
    az.STATUS_HUMAN_CLEARED,
    az.STATUS_AUTONOMOUSLY_ELIGIBLE,
    az.STATUS_REVIEW_REQUIRED,
    az.STATUS_SUSPENDED,
])
def test_illegal_transition_from_unreviewed_raises(to_status):
    with pytest.raises(az.InvalidTransitionError):
        az.transition("tex", "schema_a_refresh", to_status, reason="x", actor="test")


def test_full_legal_chain_unreviewed_to_autonomously_eligible():
    az.transition("tex", "schema_a_refresh", az.STATUS_REVIEW_PENDING, reason="x", actor="test")
    az.transition("tex", "schema_a_refresh", az.STATUS_HUMAN_CLEARED, reason="x", actor="test", source_sha="sha1")
    rec = az.transition("tex", "schema_a_refresh", az.STATUS_AUTONOMOUSLY_ELIGIBLE, reason="x", actor="test")
    assert rec["status"] == az.STATUS_AUTONOMOUSLY_ELIGIBLE


def test_autonomously_eligible_can_suspend_but_not_skip_to_human_cleared_again_directly():
    _promote_to_eligible("html")
    rec = az.transition("html", "schema_a_refresh", az.STATUS_SUSPENDED, reason="budget breach", actor="change_budget")
    assert rec["status"] == az.STATUS_SUSPENDED
    # SUSPENDED must go back through HUMAN_CLEARED, never straight to AUTONOMOUSLY_ELIGIBLE.
    with pytest.raises(az.InvalidTransitionError):
        az.transition("html", "schema_a_refresh", az.STATUS_AUTONOMOUSLY_ELIGIBLE, reason="x", actor="test")
    rec2 = az.transition("html", "schema_a_refresh", az.STATUS_HUMAN_CLEARED, reason="re-cleared", actor="test")
    assert rec2["status"] == az.STATUS_HUMAN_CLEARED


def test_unknown_status_raises_autonomy_state_error():
    with pytest.raises(az.AutonomyStateError):
        az.transition("tex", "schema_a_refresh", "NOT_A_REAL_STATUS", reason="x", actor="test")


def _promote_to_eligible(family, mechanism="schema_a_refresh", sha="shaX"):
    az.transition(family, mechanism, az.STATUS_REVIEW_PENDING, reason="x", actor="test")
    az.transition(family, mechanism, az.STATUS_HUMAN_CLEARED, reason="x", actor="test", source_sha=sha)
    az.transition(family, mechanism, az.STATUS_AUTONOMOUSLY_ELIGIBLE, reason="x", actor="test")


# --- idempotency-by-source_sha ----------------------------------------------

def test_transition_idempotent_on_identical_source_sha():
    _promote_to_eligible("cells", sha="shaA")
    first = az.transition("cells", "schema_a_refresh", az.STATUS_SUSPENDED, reason="r1", actor="a1", source_sha="shaB")
    second = az.transition("cells", "schema_a_refresh", az.STATUS_SUSPENDED, reason="r2-different", actor="a2-different", source_sha="shaB")
    assert first == second
    assert second["transition_reason"] == "r1"


def test_transition_with_different_source_sha_after_terminal_is_illegal_not_silently_applied():
    """A second SUSPENDED-triggering event with a genuinely different SHA is
    NOT idempotent (different sha), and SUSPENDED -> SUSPENDED is not a
    legal edge -- it must raise, not silently overwrite the first
    suspension's reason."""
    _promote_to_eligible("barcode", sha="shaA")
    az.transition("barcode", "schema_a_refresh", az.STATUS_SUSPENDED, reason="r1", actor="a1", source_sha="shaB")
    with pytest.raises(az.InvalidTransitionError):
        az.transition("barcode", "schema_a_refresh", az.STATUS_SUSPENDED, reason="r2", actor="a2", source_sha="shaC")


# --- is_self_commit ----------------------------------------------------------

@pytest.mark.parametrize("message,expected", [
    ("chore(seo): Schema A keyword refresh -- tex, barcode", True),
    ("CHORE(SEO): schema a keyword refresh weekly run", True),
    ("fix(seo): tex keyword contamination remediation", False),
    ("chore(seo): Schema A keyword refresh dependency bump", True),
    (None, False),
    ("", False),
])
def test_is_self_commit(message, expected):
    assert az.is_self_commit(message) is expected


# --- check_commit_for_review_required ---------------------------------------

def test_check_commit_flips_eligible_to_review_required_on_non_self_commit():
    _promote_to_eligible("font")
    rec = az.check_commit_for_review_required(
        "font", "schema_a_refresh", commit_sha="abc123", commit_message="fix(seo): unrelated font tweak"
    )
    assert rec is not None
    assert rec["status"] == az.STATUS_REVIEW_REQUIRED
    assert az.is_autonomously_eligible("font", "schema_a_refresh") is False


def test_check_commit_excludes_self_commit_pattern():
    _promote_to_eligible("note")
    rec = az.check_commit_for_review_required(
        "note", "schema_a_refresh", commit_sha="abc123",
        commit_message="chore(seo): Schema A keyword refresh -- note, html",
    )
    assert rec is None
    assert az.is_autonomously_eligible("note", "schema_a_refresh") is True


def test_check_commit_noop_when_not_currently_eligible():
    rec = az.check_commit_for_review_required(
        "words", "schema_a_refresh", commit_sha="abc123", commit_message="fix(seo): whatever"
    )
    assert rec is None


def test_check_commit_noop_when_commit_is_the_one_already_reviewed():
    """last_reviewed_sha records the commit HEAD was at when a human last
    reviewed this pair (v14 design doc field definition) -- it is set only
    by a real HUMAN_CLEARED transition, never by a REVIEW_REQUIRED flip. If
    a caller re-checks the exact commit that was the basis of the last
    clearance (not a genuinely later one), that must be a no-op."""
    az.transition("email", "schema_a_refresh", az.STATUS_REVIEW_PENDING, reason="x", actor="test")
    az.transition("email", "schema_a_refresh", az.STATUS_HUMAN_CLEARED, reason="cleared",
                   actor="test", source_sha="reviewed-sha")
    az.transition("email", "schema_a_refresh", az.STATUS_AUTONOMOUSLY_ELIGIBLE, reason="x", actor="test")
    rec = az.get_record("email", "schema_a_refresh")
    assert rec["last_reviewed_sha"] == "reviewed-sha"
    rec2 = az.check_commit_for_review_required(
        "email", "schema_a_refresh", commit_sha="reviewed-sha", commit_message="fix(seo): touch"
    )
    assert rec2 is None
    assert az.is_autonomously_eligible("email", "schema_a_refresh") is True


def test_check_commit_flips_on_genuinely_later_commit_after_review():
    az.transition("words", "schema_a_refresh", az.STATUS_REVIEW_PENDING, reason="x", actor="test")
    az.transition("words", "schema_a_refresh", az.STATUS_HUMAN_CLEARED, reason="cleared",
                   actor="test", source_sha="reviewed-sha")
    az.transition("words", "schema_a_refresh", az.STATUS_AUTONOMOUSLY_ELIGIBLE, reason="x", actor="test")
    rec = az.check_commit_for_review_required(
        "words", "schema_a_refresh", commit_sha="later-sha", commit_message="fix(seo): a later real change"
    )
    assert rec is not None
    assert rec["status"] == az.STATUS_REVIEW_REQUIRED


# --- suspend() ---------------------------------------------------------------

def test_suspend_noop_when_not_eligible():
    assert az.suspend("3d", "schema_a_refresh", reason="whatever") is None


def test_suspend_transitions_eligible_to_suspended():
    _promote_to_eligible("3d")
    rec = az.suspend("3d", "schema_a_refresh", reason="workflow-drift detected")
    assert rec["status"] == az.STATUS_SUSPENDED
    assert rec["actor"] == "autonomy-state-machine"


# --- family_from_page_path ----------------------------------------------------

@pytest.mark.parametrize("path,expected", [
    ("content/kb.aspose.org/en/pdf/python/faq.md", "pdf"),
    ("content/docs.aspose.org/en/slides/net/getting-started.md", "slides"),
    ("content/reference.aspose.org/en/slides/net/SaveFormat.md", "slides"),
    ("content/products.aspose.org/en/cells/_index.md", "cells"),
    ("content/blog.aspose.org/pdf/python/some-post/index.md", "pdf"),
    ("content/websites.aspose.org/some-page/index.md", None),
    ("content/www.aspose.org/index.md", None),
    ("not/a/content/path.md", None),
])
def test_family_from_page_path(path, expected):
    assert az.family_from_page_path(path) == expected


def test_family_from_page_path_accepts_windows_style_backslashes():
    assert az.family_from_page_path("content\\kb.aspose.org\\en\\pdf\\python\\faq.md") == "pdf"
