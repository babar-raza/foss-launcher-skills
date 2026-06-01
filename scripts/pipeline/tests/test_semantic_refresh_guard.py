"""Tests for semantic_refresh_guard.py (Lane 4B).

Covers:
- Placement: guard requires page_decisions.json; classifier (4A) does not
- Fail-closed behavior: HIGH/MEDIUM/UNKNOWN source + infra error → exit 4
- All verdict precedence rules (8-level hierarchy)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_PIPELINE_DIR = Path(__file__).resolve().parents[1]
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))

from commands.ops.semantic_refresh_guard import evaluate, guard, _VERDICT_EXIT


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_source_delta(
    source_changed: bool = True,
    source_change_impact: str = "HIGH",
    diff_available: bool = True,
    claim_delta_count: int = 0,
    modified_claims: int = 0,
    removed_claims: int = 0,
    files_classified: list | None = None,
) -> dict:
    return {
        "source_changed": source_changed,
        "source_change_impact": source_change_impact,
        "diff_available": diff_available,
        "claim_delta_count": claim_delta_count,
        "claim_delta_detail": {
            "new_claims": 0,
            "modified_claims": modified_claims,
            "removed_claims": removed_claims,
            "new_apis": 0,
            "modified_apis": 0,
        },
        "files_classified": files_classified or [],
        "proof": [],
        "old_source_sha": "old123",
        "new_source_sha": "new456",
    }


def _make_page_decisions(body_changed_count: int = 0, evidence_only: int = 0) -> dict:
    pages = {}
    for i in range(body_changed_count):
        pages[f"body_page_{i}.md"] = {"body_hash_changed": True, "decision": "BODY_UPDATED"}
    for i in range(evidence_only):
        pages[f"ev_page_{i}.md"] = {"body_hash_changed": False, "decision": "EVIDENCE_ONLY"}
    return {"pages": pages}


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


# ---------------------------------------------------------------------------
# Placement tests
# ---------------------------------------------------------------------------

class TestPlacement:
    def test_requires_page_decisions_json(self, tmp_path):
        """Missing --page-decisions → GUARD_ERROR_BLOCKED, exit 4."""
        sd_path = tmp_path / "semantic_source_delta.json"
        _write_json(sd_path, _make_source_delta(source_change_impact="HIGH"))
        pd_path = tmp_path / "nonexistent_page_decisions.json"  # does not exist

        _, exit_code = guard(
            "font", "python",
            source_delta_path=sd_path,
            page_decisions_path=pd_path,
            out_path=tmp_path / "verdict.json",
            repo_root=tmp_path,
        )
        assert exit_code == 4

    def test_does_not_require_page_decisions_at_classifier_stage(self, tmp_path):
        """semantic_source_classifier (4A) classify() does not accept page_decisions param."""
        import inspect
        from commands.ops.semantic_source_classifier import classify as classifier_classify
        sig = inspect.signature(classifier_classify)
        param_names = list(sig.parameters.keys())
        assert "page_decisions" not in param_names, (
            f"classifier classify() must not accept page_decisions; got params: {param_names}"
        )
        assert "page_decisions_path" not in param_names, (
            f"classifier classify() must not accept page_decisions_path; got params: {param_names}"
        )

    def test_high_impact_missing_verdict_artifact(self, tmp_path):
        """If verdict file not written (e.g. guard not run), calling code must treat as blocked."""
        verdict_path = tmp_path / "verdict.json"
        # Guard not run → file absent → absence = blocked
        assert not verdict_path.exists()
        # The plan specifies: "If semantic_refresh_verdict.json is absent after step 11.5, treat as exit 4"
        # We verify the guard produces the file when it runs successfully
        sd_path = tmp_path / "semantic_source_delta.json"
        pd_path = tmp_path / "page_decisions.json"
        _write_json(sd_path, _make_source_delta(source_changed=False))
        _write_json(pd_path, _make_page_decisions())
        guard(
            "font", "python",
            source_delta_path=sd_path,
            page_decisions_path=pd_path,
            out_path=verdict_path,
            repo_root=tmp_path,
        )
        assert verdict_path.exists(), "Guard must write verdict file"


# ---------------------------------------------------------------------------
# Fail-closed tests
# ---------------------------------------------------------------------------

class TestFailClosed:
    def test_guard_error_blocks_high_source_change(self, tmp_path):
        """Missing source_delta file + HIGH impact → GUARD_ERROR_BLOCKED, exit 4."""
        sd_path = tmp_path / "nonexistent_source_delta.json"
        pd_path = tmp_path / "page_decisions.json"
        _write_json(pd_path, _make_page_decisions())

        _, exit_code = guard(
            "font", "python",
            source_delta_path=sd_path,
            page_decisions_path=pd_path,
            out_path=tmp_path / "verdict.json",
            repo_root=tmp_path,
        )
        # source_delta missing → source_impact defaults to UNKNOWN → blocking
        assert exit_code == 4

    def test_guard_error_blocks_medium_source_change(self, tmp_path):
        """source_delta missing + MEDIUM impact (default UNKNOWN) → exit 4."""
        sd_path = tmp_path / "nonexistent.json"
        pd_path = tmp_path / "pd.json"
        _write_json(pd_path, _make_page_decisions())
        _, exit_code = guard(
            "font", "python",
            source_delta_path=sd_path,
            page_decisions_path=pd_path,
            out_path=tmp_path / "v.json",
            repo_root=tmp_path,
        )
        assert exit_code == 4

    def test_guard_error_warns_internal_only(self, tmp_path):
        """source_delta has INTERNAL_ONLY + page_decisions missing → exit 5 (warn only)."""
        sd_path = tmp_path / "sd.json"
        _write_json(sd_path, _make_source_delta(
            source_changed=True,
            source_change_impact="INTERNAL_ONLY",
            diff_available=True,
        ))
        pd_path = tmp_path / "nonexistent_pd.json"

        _, exit_code = guard(
            "font", "python",
            source_delta_path=sd_path,
            page_decisions_path=pd_path,
            out_path=tmp_path / "v.json",
            repo_root=tmp_path,
        )
        assert exit_code == 5

    def test_guard_error_warns_source_not_changed(self, tmp_path):
        """source_changed=false + page_decisions missing → exit 5 (warn only)."""
        sd_path = tmp_path / "sd.json"
        _write_json(sd_path, _make_source_delta(
            source_changed=False,
            source_change_impact="UNKNOWN",
        ))
        pd_path = tmp_path / "nonexistent_pd.json"

        _, exit_code = guard(
            "font", "python",
            source_delta_path=sd_path,
            page_decisions_path=pd_path,
            out_path=tmp_path / "v.json",
            repo_root=tmp_path,
        )
        assert exit_code == 5


# ---------------------------------------------------------------------------
# Verdict precedence tests (using evaluate() directly)
# ---------------------------------------------------------------------------

class TestVerdictPrecedence:
    def test_internal_only_diff_noop_proven(self, tmp_path):
        """All TEST_ONLY files → SEMANTIC_NOOP_PROVEN, exit 0."""
        sd = _make_source_delta(
            source_changed=True,
            source_change_impact="INTERNAL_ONLY",
            diff_available=True,
            claim_delta_count=0,
        )
        pd = _make_page_decisions(body_changed_count=0)
        verdict, confidence, proof = evaluate("font", "python", sd, pd, {}, repo_root=tmp_path)
        assert verdict == "SEMANTIC_NOOP_PROVEN"
        assert _VERDICT_EXIT[verdict] == 0

    def test_user_facing_diff_empty_knowledge_delta(self, tmp_path):
        """DEFINITELY_USER_FACING + claim_delta=0 → CLAIM_EXTRACTION_MISSED_DELTA, exit 2."""
        sd = _make_source_delta(
            source_changed=True,
            source_change_impact="HIGH",
            diff_available=True,
            claim_delta_count=0,
            files_classified=[
                {"path": "src/core.py", "category": "DEFINITELY_USER_FACING", "reason": "src"}
            ],
        )
        pd = _make_page_decisions(body_changed_count=0)
        verdict, confidence, proof = evaluate("font", "python", sd, pd, {}, repo_root=tmp_path)
        assert verdict == "CLAIM_EXTRACTION_MISSED_DELTA"
        assert _VERDICT_EXIT[verdict] == 2

    def test_claim_delta_no_body_update(self, tmp_path):
        """modified_claims > 0 + body_changes=0 → PAGE_MAPPING_MISSED_IMPACT, exit 2."""
        sd = _make_source_delta(
            source_changed=True,
            source_change_impact="HIGH",
            diff_available=True,
            claim_delta_count=5,
            modified_claims=5,
            removed_claims=0,
            files_classified=[
                {"path": "src/core.py", "category": "DEFINITELY_USER_FACING", "reason": "src"}
            ],
        )
        pd = _make_page_decisions(body_changed_count=0)
        verdict, confidence, proof = evaluate("font", "python", sd, pd, {}, repo_root=tmp_path)
        assert verdict == "PAGE_MAPPING_MISSED_IMPACT"
        assert _VERDICT_EXIT[verdict] == 2

    def test_grade_reasons_trigger_remediation_not_semantic(self, tmp_path):
        """D/F grades + body_changes > 0 → GRADING_REMEDIATION_REQUIRED, exit 0."""
        sd = _make_source_delta(
            source_changed=True,
            source_change_impact="HIGH",
            diff_available=True,
            claim_delta_count=0,
        )
        pd = _make_page_decisions(body_changed_count=3)
        # Patch grade scanner to return non-zero
        with patch("commands.ops.semantic_refresh_guard._count_grade_issues", return_value=2):
            verdict, confidence, proof = evaluate("font", "python", sd, pd, {}, repo_root=tmp_path)
        assert verdict == "GRADING_REMEDIATION_REQUIRED"
        assert _VERDICT_EXIT[verdict] == 0

    def test_grading_does_not_override_semantic_failure(self, tmp_path):
        """D/F grade + modified_claims > 0 + body=0 → PAGE_MAPPING_MISSED_IMPACT wins, exit 2."""
        sd = _make_source_delta(
            source_changed=True,
            source_change_impact="HIGH",
            diff_available=True,
            claim_delta_count=3,
            modified_claims=3,
        )
        pd = _make_page_decisions(body_changed_count=0)
        with patch("commands.ops.semantic_refresh_guard._count_grade_issues", return_value=5):
            verdict, confidence, proof = evaluate("font", "python", sd, pd, {}, repo_root=tmp_path)
        # PAGE_MAPPING_MISSED_IMPACT (priority 4) beats GRADING_REMEDIATION_REQUIRED (priority 6)
        assert verdict == "PAGE_MAPPING_MISSED_IMPACT"
        assert _VERDICT_EXIT[verdict] == 2

    def test_body_updated_verified(self, tmp_path):
        """body_changes > 0 and no higher-priority failures → BODY_UPDATED_VERIFIED, exit 0."""
        sd = _make_source_delta(
            source_changed=True,
            source_change_impact="HIGH",
            diff_available=True,
            claim_delta_count=0,
        )
        pd = _make_page_decisions(body_changed_count=5)
        with patch("commands.ops.semantic_refresh_guard._count_grade_issues", return_value=0):
            verdict, confidence, proof = evaluate("font", "python", sd, pd, {}, repo_root=tmp_path)
        assert verdict == "BODY_UPDATED_VERIFIED"
        assert _VERDICT_EXIT[verdict] == 0

    def test_refresh_blocked_unproven_noop(self, tmp_path):
        """HIGH impact + body=0 + no proof → REFRESH_BLOCKED_UNPROVEN_NOOP, exit 1."""
        sd = _make_source_delta(
            source_changed=True,
            source_change_impact="HIGH",
            diff_available=True,
            claim_delta_count=0,
        )
        pd = _make_page_decisions(body_changed_count=0)
        verdict, confidence, proof = evaluate("font", "python", sd, pd, {}, repo_root=tmp_path)
        assert verdict == "REFRESH_BLOCKED_UNPROVEN_NOOP"
        assert _VERDICT_EXIT[verdict] == 1

    def test_verdict_exit_codes_correct(self):
        """All verdict exit code mappings are as specified."""
        assert _VERDICT_EXIT["BODY_UPDATED_VERIFIED"] == 0
        assert _VERDICT_EXIT["SEMANTIC_NOOP_PROVEN"] == 0
        assert _VERDICT_EXIT["GRADING_REMEDIATION_REQUIRED"] == 0
        assert _VERDICT_EXIT["SEMANTIC_REFRESH_REQUIRED"] == 1
        assert _VERDICT_EXIT["REFRESH_BLOCKED_UNPROVEN_NOOP"] == 1
        assert _VERDICT_EXIT["CLAIM_EXTRACTION_MISSED_DELTA"] == 2
        assert _VERDICT_EXIT["PAGE_MAPPING_MISSED_IMPACT"] == 2
        assert _VERDICT_EXIT["GUARD_ERROR_BLOCKED"] == 4
        assert _VERDICT_EXIT["GUARD_ERROR_WARN"] == 5
        # v2 verdicts
        assert _VERDICT_EXIT["GENERATED_ONLY_BODY_CHANGE_INSUFFICIENT"] == 1
        assert _VERDICT_EXIT["EXISTING_IMPACTED_PAGES_UPDATED_VERIFIED"] == 0
        # v3 verdict (initial refresh)
        assert _VERDICT_EXIT["INITIAL_REFRESH_ALLOWED"] == 0


# ---------------------------------------------------------------------------
# Guard v2: Generated-page masking tests (page_impact_data)
# ---------------------------------------------------------------------------

def _make_page_decisions_with_paths(entries: list[tuple[str, bool, str]]) -> dict:
    """Build page_decisions dict with explicit paths.
    entries: list of (path, body_hash_changed, decision)
    """
    pages = {}
    for path, body_changed, decision in entries:
        pages[path] = {"body_hash_changed": body_changed, "decision": decision}
    return {"pages": pages}


def _make_page_impact(entries: list[tuple[str, str, str]]) -> dict:
    """Build page_impact dict.
    entries: list of (path, subdomain, pia_score)
    """
    return {
        "pages": [
            {"path": path, "subdomain": sub, "pia_score": score}
            for path, sub, score in entries
        ]
    }


class TestGuardV2GeneratedPageMasking:
    """Tests for GENERATED_ONLY_BODY_CHANGE_INSUFFICIENT detection (v2)."""

    def test_font_python_masking_defect_blocked(self, tmp_path):
        """font/python case: 6 generated reference pages changed + 68 HIGH_IMPACT
        docs/kb pages EVIDENCE_ONLY → GENERATED_ONLY_BODY_CHANGE_INSUFFICIENT, exit 1."""
        sd = _make_source_delta(
            source_changed=True,
            source_change_impact="HIGH",
            diff_available=True,
            claim_delta_count=5,
            files_classified=[
                {"path": "src/font.py", "category": "DEFINITELY_USER_FACING", "reason": "src"}
            ],
        )
        # 6 reference stubs changed (generated)
        ref_entries = [
            (f"content/reference.aspose.org/en/font/python/Class{i}.md", True, "BODY_UPDATED")
            for i in range(6)
        ]
        # 5 HIGH_IMPACT docs pages EVIDENCE_ONLY
        docs_entries = [
            (f"content/docs.aspose.org/en/font/python/guide{i}.md", False, "EVIDENCE_ONLY")
            for i in range(5)
        ]
        pd = _make_page_decisions_with_paths(ref_entries + docs_entries)
        pi = _make_page_impact(
            [(f"content/docs.aspose.org/en/font/python/guide{i}.md", "docs", "HIGH_IMPACT")
             for i in range(5)]
        )
        with patch("commands.ops.semantic_refresh_guard._count_grade_issues", return_value=0):
            verdict, confidence, proof = evaluate(
                "font", "python", sd, pd, {}, repo_root=tmp_path, page_impact_data=pi
            )
        assert verdict == "GENERATED_ONLY_BODY_CHANGE_INSUFFICIENT", (
            f"Expected GENERATED_ONLY_BODY_CHANGE_INSUFFICIENT, got {verdict}"
        )
        assert _VERDICT_EXIT[verdict] == 1
        assert any("GENERATED_ONLY" in p for p in proof)

    def test_existing_content_page_updated_verified(self, tmp_path):
        """Existing docs page changed → EXISTING_IMPACTED_PAGES_UPDATED_VERIFIED, exit 0."""
        sd = _make_source_delta(
            source_changed=True,
            source_change_impact="HIGH",
            diff_available=True,
            claim_delta_count=0,
        )
        # 1 docs page changed + 1 reference page changed
        pd = _make_page_decisions_with_paths([
            ("content/docs.aspose.org/en/font/python/guide.md", True, "BODY_UPDATED"),
            ("content/reference.aspose.org/en/font/python/Class.md", True, "BODY_UPDATED"),
            ("content/docs.aspose.org/en/font/python/other.md", False, "EVIDENCE_ONLY"),
        ])
        pi = _make_page_impact([
            ("content/docs.aspose.org/en/font/python/guide.md", "docs", "HIGH_IMPACT"),
            ("content/docs.aspose.org/en/font/python/other.md", "docs", "HIGH_IMPACT"),
        ])
        with patch("commands.ops.semantic_refresh_guard._count_grade_issues", return_value=0):
            verdict, confidence, proof = evaluate(
                "font", "python", sd, pd, {}, repo_root=tmp_path, page_impact_data=pi
            )
        assert verdict == "EXISTING_IMPACTED_PAGES_UPDATED_VERIFIED"
        assert _VERDICT_EXIT[verdict] == 0

    def test_generated_only_no_high_impact_existing_passes(self, tmp_path):
        """Generated reference pages changed + NO HIGH/MEDIUM existing pages → BODY_UPDATED_VERIFIED."""
        sd = _make_source_delta(
            source_changed=True,
            source_change_impact="HIGH",
            diff_available=True,
            claim_delta_count=0,
        )
        # Only reference pages changed, no HIGH_IMPACT existing pages
        pd = _make_page_decisions_with_paths([
            ("content/reference.aspose.org/en/font/python/Class.md", True, "BODY_UPDATED"),
            ("content/docs.aspose.org/en/font/python/low.md", False, "EVIDENCE_ONLY"),
        ])
        pi = _make_page_impact([
            ("content/docs.aspose.org/en/font/python/low.md", "docs", "LOW_IMPACT"),
        ])
        with patch("commands.ops.semantic_refresh_guard._count_grade_issues", return_value=0):
            verdict, confidence, proof = evaluate(
                "font", "python", sd, pd, {}, repo_root=tmp_path, page_impact_data=pi
            )
        # No HIGH/MEDIUM existing pages → generated-only change is acceptable
        # ref_body=1, existing_body=0, hm_eo=0 → does NOT fire GENERATED_ONLY
        assert verdict in ("BODY_UPDATED_VERIFIED", "EXISTING_IMPACTED_PAGES_UPDATED_VERIFIED",
                           "GENERATED_ONLY_BODY_CHANGE_INSUFFICIENT")
        # Specifically: hm_eo=0 means condition not met → falls through
        assert verdict != "GENERATED_ONLY_BODY_CHANGE_INSUFFICIENT"
        assert _VERDICT_EXIT[verdict] == 0

    def test_no_page_impact_falls_back_to_v1_behavior(self, tmp_path):
        """Without page_impact_data, body_changed > 0 → BODY_UPDATED_VERIFIED (backward compat)."""
        sd = _make_source_delta(
            source_changed=True,
            source_change_impact="HIGH",
            diff_available=True,
            claim_delta_count=0,
        )
        pd = _make_page_decisions(body_changed_count=6)
        with patch("commands.ops.semantic_refresh_guard._count_grade_issues", return_value=0):
            # No page_impact_data → backward compat
            verdict, confidence, proof = evaluate(
                "font", "python", sd, pd, {}, repo_root=tmp_path, page_impact_data=None
            )
        assert verdict == "BODY_UPDATED_VERIFIED"
        assert _VERDICT_EXIT[verdict] == 0

    def test_cells_java_still_blocked_with_page_impact(self, tmp_path):
        """cells/java: modified_claims + body=0 → PAGE_MAPPING_MISSED_IMPACT (priority 3 wins)."""
        sd = _make_source_delta(
            source_changed=True,
            source_change_impact="HIGH",
            diff_available=True,
            claim_delta_count=92,
            removed_claims=92,
            files_classified=[
                {"path": "src/Workbook.java", "category": "DEFINITELY_USER_FACING", "reason": "src"}
            ],
        )
        pd = _make_page_decisions(body_changed_count=0, evidence_only=304)
        pi = _make_page_impact([
            ("content/docs.aspose.org/en/cells/java/guide.md", "docs", "HIGH_IMPACT"),
        ])
        verdict, confidence, proof = evaluate(
            "cells", "java", sd, pd, {}, repo_root=tmp_path, page_impact_data=pi
        )
        assert verdict == "PAGE_MAPPING_MISSED_IMPACT"
        assert _VERDICT_EXIT[verdict] == 2

    def test_generated_masking_does_not_override_claim_extraction(self, tmp_path):
        """CLAIM_EXTRACTION_MISSED_DELTA (priority 2) fires before generated masking check."""
        sd = _make_source_delta(
            source_changed=True,
            source_change_impact="HIGH",
            diff_available=True,
            claim_delta_count=0,  # no claim delta
            files_classified=[
                {"path": "src/font.py", "category": "DEFINITELY_USER_FACING", "reason": "src"}
            ],
        )
        # Even with reference body changes present
        pd = _make_page_decisions_with_paths([
            ("content/reference.aspose.org/en/font/python/Class.md", True, "BODY_UPDATED"),
        ])
        pi = _make_page_impact([
            ("content/docs.aspose.org/en/font/python/guide.md", "docs", "HIGH_IMPACT"),
        ])
        verdict, confidence, proof = evaluate(
            "font", "python", sd, pd, {}, repo_root=tmp_path, page_impact_data=pi
        )
        # Priority 2 (CLAIM_EXTRACTION) fires before priority 8 (GENERATED_ONLY)
        assert verdict == "CLAIM_EXTRACTION_MISSED_DELTA"
        assert _VERDICT_EXIT[verdict] == 2


# ---------------------------------------------------------------------------
# Priority 4b: INITIAL_REFRESH_ALLOWED
# ---------------------------------------------------------------------------

class TestInitialRefreshAllowed:
    """Tests for the INITIAL_REFRESH_ALLOWED verdict that breaks the chicken-and-egg
    deadlock: when claim_delta > 0, body_changed == 0, and no prior harness dispatch
    has been recorded, allow the first automated write."""

    def test_no_dispatch_history_allows_initial_refresh(self, tmp_path):
        """claim_delta > 0 (new_claims only), body=0, no dispatch_history.json → INITIAL_REFRESH_ALLOWED."""
        sd = _make_source_delta(
            source_changed=True,
            source_change_impact="HIGH",
            diff_available=True,
            claim_delta_count=100,
            modified_claims=0,
            removed_claims=0,
            files_classified=[
                {"path": "src/core.py", "category": "DEFINITELY_USER_FACING", "reason": "src"}
            ],
        )
        pd = _make_page_decisions(body_changed_count=0)
        # No dispatch_history.json exists in tmp_path/runs/state/cells/java/
        verdict, confidence, proof = evaluate("cells", "java", sd, pd, {}, repo_root=tmp_path)
        assert verdict == "INITIAL_REFRESH_ALLOWED"
        assert _VERDICT_EXIT[verdict] == 0
        assert any("no prior dispatch recorded" in p for p in proof)

    def test_dispatch_history_exists_blocks_refresh(self, tmp_path):
        """claim_delta > 0, body=0, dispatch_history.json EXISTS → SEMANTIC_REFRESH_REQUIRED."""
        sd = _make_source_delta(
            source_changed=True,
            source_change_impact="HIGH",
            diff_available=True,
            claim_delta_count=100,
            modified_claims=0,
            removed_claims=0,
            files_classified=[
                {"path": "src/core.py", "category": "DEFINITELY_USER_FACING", "reason": "src"}
            ],
        )
        pd = _make_page_decisions(body_changed_count=0)
        # Create dispatch_history.json to simulate prior dispatch
        dispatch_state = tmp_path / "runs" / "state" / "cells" / "java" / "dispatch_history.json"
        dispatch_state.parent.mkdir(parents=True, exist_ok=True)
        dispatch_state.write_text('{"first_dispatch_at": "2026-01-01T00:00:00Z"}')
        verdict, confidence, proof = evaluate("cells", "java", sd, pd, {}, repo_root=tmp_path)
        assert verdict == "SEMANTIC_REFRESH_REQUIRED"
        assert _VERDICT_EXIT[verdict] == 1
