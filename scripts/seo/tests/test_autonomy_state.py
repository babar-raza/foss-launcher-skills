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
                   reason="cleared", actor="independent-reviewer-agent", source_sha="deadbeef",
                   source_verdict="fake-verdict-sha256-for-test")
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


# --- source_verdict enforcement on real review-actor HUMAN_CLEARED grants ---
# (Contract I hardening added after an independent reviewer REJECTed an
# earlier revision for seeding real AUTONOMOUSLY_ELIGIBLE grants with no
# checksummed review-verdict provenance at all.)

def test_human_cleared_from_review_actor_without_source_verdict_raises():
    az.transition("tex", "schema_a_refresh", az.STATUS_REVIEW_PENDING, reason="x", actor="test")
    with pytest.raises(az.AutonomyStateError):
        az.transition("tex", "schema_a_refresh", az.STATUS_HUMAN_CLEARED,
                       reason="cleared", actor="independent-reviewer-agent")


def test_human_cleared_from_review_actor_with_source_verdict_succeeds():
    az.transition("tex", "schema_a_refresh", az.STATUS_REVIEW_PENDING, reason="x", actor="test")
    rec = az.transition("tex", "schema_a_refresh", az.STATUS_HUMAN_CLEARED,
                         reason="cleared", actor="independent-reviewer-agent",
                         source_verdict="abc123deadbeef")
    assert rec["source_verdict"] == "abc123deadbeef"


def test_human_cleared_from_non_review_actor_does_not_require_source_verdict():
    az.transition("page", "schema_a_refresh", az.STATUS_REVIEW_PENDING, reason="x", actor="test")
    rec = az.transition("page", "schema_a_refresh", az.STATUS_HUMAN_CLEARED, reason="x", actor="test")
    assert rec["status"] == az.STATUS_HUMAN_CLEARED
    assert rec["source_verdict"] is None


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
    # Real merged commit messages (git log --all -i --grep="Schema A keyword",
    # verified 2026-09-05: PRs #45, #46, #60, #69 all use this exact form --
    # an earlier revision of this regex used the wrong word order ("Schema A
    # keyword refresh") and a REJECT-worthy independent review caught that it
    # would never have matched a single real cron commit).
    ("chore(seo): refresh Schema A keywords [2026-08-30] (#69)", True),
    ("chore(seo): refresh Schema A keywords [2026-08-26] (#60)", True),
    ("chore(seo): refresh Schema A keywords [2026-08-02] (#46)", True),
    ("chore(seo): refresh Schema A keywords [2026-07] (#45)", True),
    ("CHORE(SEO): REFRESH SCHEMA A KEYWORDS [case-insensitive check]", True),
    ("fix(seo): tex keyword contamination remediation", False),
    ("chore(seo): Schema A keyword refresh -- old wrong word order", False),
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
        commit_message="chore(seo): refresh Schema A keywords [2026-09-06] (#70)",
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


# --- seed_from_product_review_log --------------------------------------------
# The checked-in, tested seeding path a real SEO-PER-PRODUCT-COMMIT-REVIEW
# run's product_review_log.jsonl must go through -- replaces an earlier
# unchecked-in ad hoc pass an independent reviewer REJECTed for granting
# AUTONOMOUSLY_ELIGIBLE regardless of each family's real verdict.

def _write_review_log(tmp_path, rows):
    log_path = tmp_path / "product_review_log.jsonl"
    with open(log_path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    return log_path


def _write_verdict_file(tmp_path, name, content):
    verdicts_dir = tmp_path / "verdicts"
    verdicts_dir.mkdir(exist_ok=True)
    path = verdicts_dir / f"{name}_verdict.json"
    path.write_text(json.dumps(content), encoding="utf-8")
    return path


def test_seed_grants_only_cleared_families_and_skips_not_cleared(tmp_path):
    cleared_verdict = _write_verdict_file(tmp_path, "email", {"family": "email", "verdict": "CLEARED"})
    _write_verdict_file(tmp_path, "tex", {"family": "tex", "verdict": "NOT_CLEARED"})
    log_path = _write_review_log(tmp_path, [
        {"family": "email", "verdict": "CLEARED", "run_id": "it-0005", "actor": "independent-reviewer-agent",
         "evidence_file": str(cleared_verdict), "summary": "clean history"},
        {"family": "tex", "verdict": "NOT_CLEARED", "run_id": "it-0005", "actor": "independent-reviewer-agent",
         "evidence_file": str(tmp_path / "verdicts" / "tex_verdict.json"), "summary": "contaminated"},
    ])

    result = az.seed_from_product_review_log(log_path)

    assert result["granted"] == ["email"]
    assert result["skipped_not_cleared"] == ["tex"]
    assert az.is_autonomously_eligible("email", "schema_a_refresh") is True
    assert az.is_autonomously_eligible("tex", "schema_a_refresh") is False
    assert az.get_status("tex", "schema_a_refresh") == az.STATUS_UNREVIEWED


def test_seed_records_real_verdict_file_sha256_as_source_verdict(tmp_path):
    verdict_path = _write_verdict_file(tmp_path, "pdf", {"family": "pdf", "verdict": "CLEARED"})
    expected_sha = az._sha256_hex(verdict_path.read_bytes())
    log_path = _write_review_log(tmp_path, [
        {"family": "pdf", "verdict": "CLEARED", "run_id": "it-0005", "actor": "independent-reviewer-agent",
         "evidence_file": str(verdict_path), "summary": "clean"},
    ])

    az.seed_from_product_review_log(log_path)

    rec = az.get_record("pdf", "schema_a_refresh")
    assert rec["source_verdict"] == expected_sha
    assert rec["status"] == az.STATUS_AUTONOMOUSLY_ELIGIBLE


def test_seed_uses_latest_row_when_a_family_is_reviewed_twice(tmp_path):
    """Append-only log: a later row for the same family supersedes an
    earlier one (mirrors a real re-review after remediation)."""
    verdict_path = _write_verdict_file(tmp_path, "cells", {"family": "cells", "verdict": "CLEARED"})
    log_path = _write_review_log(tmp_path, [
        {"family": "cells", "verdict": "NOT_CLEARED", "run_id": "it-0005", "actor": "independent-reviewer-agent",
         "evidence_file": str(verdict_path), "summary": "contaminated (first pass)"},
        {"family": "cells", "verdict": "CLEARED", "run_id": "it-0009", "actor": "independent-reviewer-agent",
         "evidence_file": str(verdict_path), "summary": "remediated and re-cleared"},
    ])

    result = az.seed_from_product_review_log(log_path)

    assert result["granted"] == ["cells"]
    assert az.is_autonomously_eligible("cells", "schema_a_refresh") is True


def test_seed_never_grants_title_description_writes_mechanism(tmp_path):
    """Default mechanism is schema_a_refresh -- the review log's clearance
    covers only the Schema A pipeline it actually inspected, never the
    unrelated, never-yet-exercised title/description write mechanism."""
    verdict_path = _write_verdict_file(tmp_path, "words", {"family": "words", "verdict": "CLEARED"})
    log_path = _write_review_log(tmp_path, [
        {"family": "words", "verdict": "CLEARED", "run_id": "it-0005", "actor": "independent-reviewer-agent",
         "evidence_file": str(verdict_path), "summary": "clean"},
    ])

    az.seed_from_product_review_log(log_path)

    assert az.is_autonomously_eligible("words", "schema_a_refresh") is True
    assert az.is_autonomously_eligible("words", "title_description_writes") is False
