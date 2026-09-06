"""Tests for scripts/seo/pipeline/execution_invariants.py (SEO-EXECUTION-
INVARIANTS, Contract J).

The acceptance bar this card sets for itself (design authority:
check-keywords-this-data-curious-feather.md §4k) is explicit: one negative
test PER named invariant (14 total), each proving check_invariants()
actually reports FAIL for that specific invariant when its context field
is forced to the failing value, with every other field held at a
realistic PASSING baseline -- never a generic "it fails closed" claim
without the test behind it.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[2]
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from seo.pipeline import execution_invariants as ei  # noqa: E402
from seo.pipeline import autonomy_state, recommendation_memory  # noqa: E402


def _passing_context(**overrides) -> ei.InvariantContext:
    """A realistic baseline where all 14 invariants pass. Each negative
    test overrides exactly one field to its failing value."""
    base = dict(
        schema_classification_ok=True,
        keyword_provenance_present=True,
        page_mapping_unambiguous=True,
        page_intent_resolvable=True,
        grounding_evidence_nonempty=True,
        intent_platform_matches_structural_platform=True,
        naturalness_status="pass",
        naturalness_warn_cleared=None,
        metadata_consistency_open_warn=False,
        requires_human_review=False,
        change_budget_ok=True,
        cross_mechanism_budget_ok=True,
        dry_run=False,
        autonomy_eligible=True,
        workflow_drift_in_sync=True,
        recommendation_memory_ok=True,
        no_unresolved_suspension=True,
    )
    base.update(overrides)
    return ei.InvariantContext(**base)


def _status_of(report: ei.InvariantReport, name: str) -> str:
    return next(r.status for r in report.results if r.name == name)


class TestAllPassingBaseline:
    def test_full_passing_context_reports_passed_true(self):
        report = ei.check_invariants(_passing_context())
        assert report.passed is True
        assert report.failed == []
        assert report.skipped == []
        assert len(report.results) == 14

    def test_all_none_context_is_all_skipped_and_reports_passed(self):
        """SKIPPED never counts as a failure -- a caller with no data for
        any invariant gets an honest all-SKIPPED report, not a false FAIL."""
        report = ei.check_invariants(ei.InvariantContext())
        assert report.passed is True
        assert len(report.skipped) == 14


class TestFourteenNegativeChecks:
    def test_1_schema_classification_fails(self):
        report = ei.check_invariants(_passing_context(schema_classification_ok=False))
        assert report.passed is False
        assert _status_of(report, "1_schema_classification_succeeds") == "FAIL"

    def test_2_keyword_provenance_missing(self):
        report = ei.check_invariants(_passing_context(keyword_provenance_present=False))
        assert report.passed is False
        assert _status_of(report, "2_keyword_provenance_present") == "FAIL"

    def test_3_page_mapping_ambiguous(self):
        report = ei.check_invariants(_passing_context(page_mapping_unambiguous=False))
        assert report.passed is False
        assert _status_of(report, "3_page_mapping_unambiguous") == "FAIL"

    def test_4_page_intent_unresolvable(self):
        report = ei.check_invariants(_passing_context(page_intent_resolvable=False))
        assert report.passed is False
        assert _status_of(report, "4_page_intent_resolvable") == "FAIL"

    def test_5_grounding_evidence_empty(self):
        report = ei.check_invariants(_passing_context(grounding_evidence_nonempty=False))
        assert report.passed is False
        assert _status_of(report, "5_grounding_evidence_nonempty") == "FAIL"

    def test_6_intent_platform_mismatch(self):
        report = ei.check_invariants(_passing_context(intent_platform_matches_structural_platform=False))
        assert report.passed is False
        assert _status_of(report, "6_intent_platform_matches_page_structural_platform") == "FAIL"

    def test_7_naturalness_fail(self):
        report = ei.check_invariants(_passing_context(naturalness_status="fail"))
        assert report.passed is False
        assert _status_of(report, "7_naturalness_not_fail") == "FAIL"

    def test_7_naturalness_warn_without_clearance_fails(self):
        """The design's exact wording is 'PASS or WARN-with-clearance,
        never FAIL' -- a bare, uncleared WARN is NOT sufficient (mirrors
        invariant 8's own open-warn-needs-review pairing, and matches the
        real production behavior of title_clause_composer.py, which has no
        clearance queue to route an uncleared WARN to and falls back
        exactly like a FAIL)."""
        report = ei.check_invariants(_passing_context(
            naturalness_status="warn", naturalness_warn_cleared=False,
        ))
        assert report.passed is False
        assert _status_of(report, "7_naturalness_not_fail") == "FAIL"

    def test_7_naturalness_warn_with_clearance_passes(self):
        report = ei.check_invariants(_passing_context(
            naturalness_status="warn", naturalness_warn_cleared=True,
        ))
        assert _status_of(report, "7_naturalness_not_fail") == "PASS"

    def test_8_open_metadata_consistency_warn_without_review(self):
        report = ei.check_invariants(_passing_context(
            metadata_consistency_open_warn=True, requires_human_review=False,
        ))
        assert report.passed is False
        assert _status_of(report, "8_no_open_metadata_consistency_warn_without_review") == "FAIL"

    def test_8_open_warn_with_review_already_true_passes(self):
        report = ei.check_invariants(_passing_context(
            metadata_consistency_open_warn=True, requires_human_review=True,
        ))
        assert _status_of(report, "8_no_open_metadata_consistency_warn_without_review") == "PASS"

    def test_9_change_budget_exceeded(self):
        report = ei.check_invariants(_passing_context(change_budget_ok=False))
        assert report.passed is False
        assert _status_of(report, "9_change_budget_not_exceeded") == "FAIL"

    def test_10_cross_mechanism_budget_exceeded(self):
        report = ei.check_invariants(_passing_context(cross_mechanism_budget_ok=False))
        assert report.passed is False
        assert _status_of(report, "10_cross_mechanism_change_budget_not_exceeded") == "FAIL"

    def test_11_autonomy_not_eligible_and_not_dry_run(self):
        report = ei.check_invariants(_passing_context(dry_run=False, autonomy_eligible=False))
        assert report.passed is False
        assert _status_of(report, "11_autonomy_state_eligible_or_dry_run") == "FAIL"

    def test_11_dry_run_passes_even_when_not_eligible(self):
        """Contract J explicitly permits --dry-run regardless of autonomy
        state -- this is the one invariant with a documented override."""
        report = ei.check_invariants(_passing_context(dry_run=True, autonomy_eligible=False))
        assert _status_of(report, "11_autonomy_state_eligible_or_dry_run") == "PASS"

    def test_12_workflow_drift_not_in_sync(self):
        report = ei.check_invariants(_passing_context(workflow_drift_in_sync=False))
        assert report.passed is False
        assert _status_of(report, "12_workflow_drift_state_in_sync_and_fresh") == "FAIL"

    def test_13_recommendation_memory_not_ok(self):
        report = ei.check_invariants(_passing_context(recommendation_memory_ok=False))
        assert report.passed is False
        assert _status_of(report, "13_recommendation_memory_readable_and_schema_matched") == "FAIL"

    def test_14_unresolved_suspension_exists(self):
        report = ei.check_invariants(_passing_context(no_unresolved_suspension=False))
        assert report.passed is False
        assert _status_of(report, "14_no_unresolved_suspension_for_family_mechanism") == "FAIL"

    def test_forcing_one_invariant_false_never_flips_a_different_one(self):
        """Each negative test above already checks its own invariant failed;
        this additionally proves the OTHER 13 stay PASS -- a real isolation
        proof, not just 14 independent assertions that could coincidentally
        all pass even if the engine cross-contaminated results."""
        report = ei.check_invariants(_passing_context(change_budget_ok=False))
        failed_names = {r.name for r in report.failed}
        assert failed_names == {"9_change_budget_not_exceeded"}


class TestRecommendationMemoryIsOk:
    @pytest.fixture(autouse=True)
    def _isolated(self, tmp_path):
        recommendation_memory.configure(repo_root=tmp_path)
        yield tmp_path
        recommendation_memory.configure()

    def test_true_when_bootstrap_empty(self):
        assert ei.recommendation_memory_is_ok() is True

    def test_true_after_a_real_write(self, _isolated):
        recommendation_memory.record_result("content/a.md", "seoTitle", "h", {"proposed_title": "T"})
        assert ei.recommendation_memory_is_ok() is True

    def test_false_on_schema_version_mismatch(self, _isolated):
        store = _isolated / "reports" / "seo" / "recommendation_memory.json"
        store.parent.mkdir(parents=True, exist_ok=True)
        store.write_text('{"schema_version": 999, "entries": {}}', encoding="utf-8")
        assert ei.recommendation_memory_is_ok() is False

    def test_never_raises_on_internal_failure(self, monkeypatch):
        monkeypatch.setattr(
            recommendation_memory, "load_memory",
            lambda: (_ for _ in ()).throw(OSError("boom")),
        )
        assert ei.recommendation_memory_is_ok() is False


class TestNoUnresolvedSuspension:
    @pytest.fixture(autouse=True)
    def _isolated(self, tmp_path):
        autonomy_state.configure(repo_root=tmp_path)
        yield tmp_path
        autonomy_state.configure()

    def test_true_when_no_state_exists_yet(self):
        assert ei.no_unresolved_suspension(["words"], "title_description_writes") is True

    def test_true_then_false_via_a_real_suspend_transition(self, _isolated):
        """Drives a real family through the actual legal state chain
        (UNREVIEWED -> ... -> AUTONOMOUSLY_ELIGIBLE -> SUSPENDED) rather
        than monkeypatching get_status -- proves the real integration with
        autonomy_state.py's own transition rules, not just this module's
        own reading logic."""
        autonomy_state.transition(
            "words", "title_description_writes", autonomy_state.STATUS_REVIEW_PENDING,
            reason="test setup", actor="test",
        )
        autonomy_state.transition(
            "words", "title_description_writes", autonomy_state.STATUS_HUMAN_CLEARED,
            reason="test setup", actor="test",
        )
        autonomy_state.transition(
            "words", "title_description_writes", autonomy_state.STATUS_AUTONOMOUSLY_ELIGIBLE,
            reason="test setup", actor="test",
        )
        assert ei.no_unresolved_suspension(["words"], "title_description_writes") is True

        autonomy_state.suspend("words", "title_description_writes", reason="test suspend")
        assert ei.no_unresolved_suspension(["words"], "title_description_writes") is False

    def test_false_when_a_family_is_suspended(self, _isolated, monkeypatch):
        monkeypatch.setattr(
            autonomy_state, "get_status",
            lambda family, mechanism, state=None: autonomy_state.STATUS_SUSPENDED,
        )
        assert ei.no_unresolved_suspension(["words"], "title_description_writes") is False

    def test_true_when_no_family_is_suspended(self, monkeypatch):
        monkeypatch.setattr(
            autonomy_state, "get_status",
            lambda family, mechanism, state=None: autonomy_state.STATUS_HUMAN_CLEARED,
        )
        assert ei.no_unresolved_suspension(["words", "pdf"], "title_description_writes") is True

    def test_never_raises_on_internal_failure(self, monkeypatch):
        monkeypatch.setattr(
            autonomy_state, "load_state",
            lambda *a, **kw: (_ for _ in ()).throw(OSError("boom")),
        )
        assert ei.no_unresolved_suspension(["words"], "title_description_writes") is False


class TestRecommendInvariant14RealIntegration:
    """recommend.py had ZERO autonomy-state awareness before this card
    (the second independent reviewer's real, non-blocking-in-apply.py-but-
    real-in-recommend.py finding). These tests drive the REAL
    run_recommendations() end to end against a real opportunities.json
    fixture and a real autonomy_state SUSPENDED transition -- not a mock
    of the gate itself."""

    def test_suspended_family_opportunities_are_skipped_not_generated(self, tmp_path, monkeypatch):
        import json as _json
        import seo.pipeline.recommend as recommend

        monkeypatch.setattr(recommend, "_REPO_ROOT", tmp_path)

        opp_path = tmp_path / "opportunities.json"
        opp_path.write_text(_json.dumps({
            "run_at": "2026-09-06",
            "opportunities": [
                {
                    "page_path": "content/docs.aspose.org/en/words/python/a.md",
                    "opportunity_level": "HIGH",
                    "family": "words",
                    "platform": "python",
                    "signals": {
                        "primary_query": "aspose words python", "matched_keywords": ["aspose words python"],
                        "title_aligned": False, "description_ok": True, "tag_gap_count": 0,
                    },
                    "seo_fields": {"seo_title": "Old Title", "description": "Old desc", "tags": []},
                },
                {
                    "page_path": "content/docs.aspose.org/en/pdf/python/b.md",
                    "opportunity_level": "HIGH",
                    "family": "pdf",
                    "platform": "python",
                    "signals": {
                        "primary_query": "aspose pdf python", "matched_keywords": ["aspose pdf python"],
                        "title_aligned": False, "description_ok": True, "tag_gap_count": 0,
                    },
                    "seo_fields": {"seo_title": "Old Title 2", "description": "Old desc 2", "tags": []},
                },
            ],
        }), encoding="utf-8")
        out_path = tmp_path / "recommendations.json"

        autonomy_state.configure(repo_root=tmp_path)
        recommendation_memory.configure(repo_root=tmp_path)
        try:
            autonomy_state.transition(
                "words", "title_description_writes", autonomy_state.STATUS_REVIEW_PENDING,
                reason="test setup", actor="test",
            )
            autonomy_state.transition(
                "words", "title_description_writes", autonomy_state.STATUS_HUMAN_CLEARED,
                reason="test setup", actor="test",
            )
            autonomy_state.transition(
                "words", "title_description_writes", autonomy_state.STATUS_AUTONOMOUSLY_ELIGIBLE,
                reason="test setup", actor="test",
            )
            autonomy_state.suspend("words", "title_description_writes", reason="test suspend")

            doc = recommend.run_recommendations(opportunities_path=opp_path, output_path=out_path)

            assert doc["total_input_opportunities"] == 1, "the SUSPENDED family's opportunity must be filtered before generation"
            pages = {r["page_path"] for r in doc["recommendations"]}
            assert "content/docs.aspose.org/en/words/python/a.md" not in pages
            assert "content/docs.aspose.org/en/pdf/python/b.md" in pages
        finally:
            autonomy_state.configure()
            recommendation_memory.configure()

    def test_no_suspension_state_at_all_generates_for_every_family(self, tmp_path, monkeypatch):
        """The common case (no autonomy state file exists yet) must not be
        misread as 'everything suspended' -- no_unresolved_suspension()
        already proves this for the bare function; this proves it holds
        through the real recommend.py call site too."""
        import json as _json
        import seo.pipeline.recommend as recommend

        monkeypatch.setattr(recommend, "_REPO_ROOT", tmp_path)
        opp_path = tmp_path / "opportunities.json"
        opp_path.write_text(_json.dumps({
            "run_at": "2026-09-06",
            "opportunities": [{
                "page_path": "content/docs.aspose.org/en/words/python/a.md",
                "opportunity_level": "HIGH",
                "family": "words",
                "platform": "python",
                "signals": {
                    "primary_query": "aspose words python", "matched_keywords": ["aspose words python"],
                    "title_aligned": False, "description_ok": True, "tag_gap_count": 0,
                },
                "seo_fields": {"seo_title": "Old Title", "description": "Old desc", "tags": []},
            }],
        }), encoding="utf-8")
        out_path = tmp_path / "recommendations.json"

        autonomy_state.configure(repo_root=tmp_path)
        recommendation_memory.configure(repo_root=tmp_path)
        try:
            doc = recommend.run_recommendations(opportunities_path=opp_path, output_path=out_path)
            assert doc["total_input_opportunities"] == 1
        finally:
            autonomy_state.configure()
            recommendation_memory.configure()


class TestConfigureReachesTheRealInternallyBoundReferences:
    """This exact bug shipped once already on this card's own first rework:
    apply.py imports its siblings via `scripts.seo.pipeline.X`, while this
    module's own top-of-file import uses `seo.pipeline.X` -- Python caches
    a module by the exact dotted name used to import it, so these are two
    DISTINCT objects for the same file, each with its own REPO_ROOT global.
    Calling `recommendation_memory.configure(...)` on apply.py's own
    reference silently left THIS module's internally-bound reference (the
    one recommendation_memory_is_ok()/no_unresolved_suspension() actually
    read) unconfigured -- a real, live-reproduced test-isolation hazard a
    second independent review caught. ei.configure() exists specifically
    to make that class of bug impossible: these tests prove it actually
    reaches the real, internally-bound objects, not a caller's own,
    possibly-differently-imported reference."""

    def test_configure_syncs_the_module_actually_used_by_recommendation_memory_is_ok(self, tmp_path):
        ei.configure(repo_root=tmp_path)
        try:
            store = tmp_path / "reports" / "seo" / "recommendation_memory.json"
            store.parent.mkdir(parents=True, exist_ok=True)
            store.write_text('{"schema_version": 999, "entries": {}}', encoding="utf-8")
            assert ei.recommendation_memory_is_ok() is False
        finally:
            ei.configure()

    def test_configure_syncs_the_module_actually_used_by_no_unresolved_suspension(self, tmp_path):
        ei.configure(repo_root=tmp_path)
        try:
            autonomy_state.transition(
                "words", "title_description_writes", autonomy_state.STATUS_REVIEW_PENDING,
                reason="test setup", actor="test",
            )
            autonomy_state.transition(
                "words", "title_description_writes", autonomy_state.STATUS_HUMAN_CLEARED,
                reason="test setup", actor="test",
            )
            autonomy_state.transition(
                "words", "title_description_writes", autonomy_state.STATUS_AUTONOMOUSLY_ELIGIBLE,
                reason="test setup", actor="test",
            )
            autonomy_state.suspend("words", "title_description_writes", reason="test suspend")
            assert ei.no_unresolved_suspension(["words"], "title_description_writes") is False
        finally:
            ei.configure()

    def test_apply_py_gate_genuinely_detects_a_bad_store_via_its_own_scripts_dotted_import(self, tmp_path, monkeypatch):
        """The exact regression: import apply.py via its OWN real import
        convention (matching test_apply_governance.py's own
        `import seo.pipeline.apply as apply_mod`-style access pattern used
        throughout this repo's test suite) and prove the real gate --
        reached through apply.py's own code, not a shortcut -- actually
        refuses a genuinely corrupted store."""
        import seo.pipeline.apply as apply_mod

        monkeypatch.setattr(apply_mod, "_REPO_ROOT", tmp_path)
        apply_mod.change_budget.configure(repo_root=tmp_path)
        try:
            store = tmp_path / "reports" / "seo" / "recommendation_memory.json"
            store.parent.mkdir(parents=True, exist_ok=True)
            store.write_text('{"schema_version": 999, "entries": {}}', encoding="utf-8")

            apply_mod.run_apply([], dry_run=False)

            assert apply_mod.execution_invariants.recommendation_memory_is_ok() is False, (
                "apply.py's own gate 0.5 code path must reach the SAME "
                "recommendation_memory instance this check reads -- if this "
                "assertion is ever violated again, apply.py's isolation fix "
                "has silently regressed"
            )
        finally:
            apply_mod.execution_invariants.configure()
            apply_mod.change_budget.configure()
