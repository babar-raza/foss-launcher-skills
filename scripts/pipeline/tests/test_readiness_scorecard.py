"""Tests for readiness_scorecard.py — launch verdict computation.

Coverage:
- 0 D/F pages → ready=True (when all other criteria met)
- any F page → ready=False, blocker in list
- D page also blocks
- translation coverage below threshold → not ready
- missing checkpoint → not ready
- H-gate FAIL → not ready
- H-gate not reviewed → not ready
- skip_human_review=True → H-gate not checked
- compute_verdict is a pure function (no I/O)
"""
from __future__ import annotations

import pytest

import readiness_scorecard
from readiness_scorecard import (
    _SUBDOMAINS,
    _THRESHOLDS,
    _LOCALES,
    compute_verdict,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _passing_coverage() -> dict:
    """Coverage dict where all subdomains exceed their thresholds."""
    total = len(_LOCALES)
    result = {}
    for site in _SUBDOMAINS:
        threshold = _THRESHOLDS[site]
        required = int(threshold * total)
        present = required + 2  # safely above threshold
        result[site] = {
            "locales_present": present,
            "total_locales": total,
            "coverage": present / total,
            "total_files": present * 5,
        }
    return result


def _passing_checkpoints() -> dict:
    return {
        "truth_audit_done": True,
        "translation_done": True,
        "knowledge_ready": True,
        "quality_done": True,
    }


def _passing_hgates() -> dict[str, str]:
    return {gate: "PASS" for gate in ["h01", "h02", "h03", "h04", "h05"]}


def _passing_grades() -> dict:
    return {"A": 10, "B": 5, "C": 2, "D": 0, "F": 0, "ungraded": 0}


# ---------------------------------------------------------------------------
# Grade criteria
# ---------------------------------------------------------------------------

class TestGradeCriteria:
    def test_no_df_pages_passes_grade_criterion(self):
        ready, blockers = compute_verdict(
            _passing_grades(),
            _passing_coverage(),
            _passing_checkpoints(),
            _passing_hgates(),
            skip_human_review=True,
        )
        assert ready is True
        assert not any("graded D or F" in b for b in blockers)

    def test_f_page_blocks_launch(self):
        """Core: F grade must block the launch."""
        grades = _passing_grades()
        grades["F"] = 1

        ready, blockers = compute_verdict(
            grades,
            _passing_coverage(),
            _passing_checkpoints(),
            _passing_hgates(),
            skip_human_review=True,
        )
        assert ready is False
        assert any("graded D or F" in b for b in blockers)

    def test_d_page_blocks_launch(self):
        """D grade also blocks — not just F."""
        grades = _passing_grades()
        grades["D"] = 2

        ready, blockers = compute_verdict(
            grades,
            _passing_coverage(),
            _passing_checkpoints(),
            _passing_hgates(),
            skip_human_review=True,
        )
        assert ready is False
        assert any("2 page(s) graded D or F" in b for b in blockers)

    def test_d_and_f_counts_combined(self):
        grades = _passing_grades()
        grades["D"] = 1
        grades["F"] = 2  # total = 3

        ready, blockers = compute_verdict(
            grades,
            _passing_coverage(),
            _passing_checkpoints(),
            _passing_hgates(),
            skip_human_review=True,
        )
        assert any("3 page(s)" in b for b in blockers)


# ---------------------------------------------------------------------------
# Translation coverage criteria
# ---------------------------------------------------------------------------

class TestTranslationCoverage:
    def test_below_threshold_blocks(self):
        coverage = _passing_coverage()
        site = "docs.aspose.org"
        threshold = _THRESHOLDS[site]
        total = len(_LOCALES)
        required = int(threshold * total)
        # Set present to just below required
        coverage[site]["locales_present"] = required - 2
        coverage[site]["coverage"] = (required - 2) / total

        ready, blockers = compute_verdict(
            _passing_grades(),
            coverage,
            _passing_checkpoints(),
            _passing_hgates(),
            skip_human_review=True,
        )
        assert ready is False
        assert any("docs.aspose.org" in b for b in blockers)

    def test_empty_coverage_dict_passes(self):
        """Empty coverage (no content yet) doesn't block via coverage criterion."""
        ready, blockers = compute_verdict(
            _passing_grades(),
            {},  # empty coverage
            _passing_checkpoints(),
            _passing_hgates(),
            skip_human_review=True,
        )
        # Checkpoint criteria will still fire but not coverage
        coverage_blockers = [b for b in blockers if "locales" in b]
        assert len(coverage_blockers) == 0


# ---------------------------------------------------------------------------
# Checkpoint criteria
# ---------------------------------------------------------------------------

class TestCheckpointCriteria:
    def test_missing_truth_audit_blocks(self):
        checkpoints = _passing_checkpoints()
        checkpoints["truth_audit_done"] = False

        ready, blockers = compute_verdict(
            _passing_grades(),
            _passing_coverage(),
            checkpoints,
            _passing_hgates(),
            skip_human_review=True,
        )
        assert ready is False
        assert any("truth_audit_done" in b for b in blockers)

    def test_missing_translation_done_blocks(self):
        checkpoints = _passing_checkpoints()
        del checkpoints["translation_done"]

        ready, blockers = compute_verdict(
            _passing_grades(),
            _passing_coverage(),
            checkpoints,
            _passing_hgates(),
            skip_human_review=True,
        )
        assert ready is False
        assert any("translation_done" in b for b in blockers)


# ---------------------------------------------------------------------------
# H-gate criteria
# ---------------------------------------------------------------------------

class TestHGateCriteria:
    def test_fail_gate_blocks(self):
        hgates = _passing_hgates()
        hgates["h01"] = "FAIL"

        ready, blockers = compute_verdict(
            _passing_grades(),
            _passing_coverage(),
            _passing_checkpoints(),
            hgates,
        )
        assert ready is False
        assert any("FAIL" in b for b in blockers)

    def test_not_reviewed_blocks(self):
        hgates = _passing_hgates()
        hgates["h02"] = ""  # not reviewed

        ready, blockers = compute_verdict(
            _passing_grades(),
            _passing_coverage(),
            _passing_checkpoints(),
            hgates,
        )
        assert ready is False
        assert any("not reviewed" in b for b in blockers)

    def test_skip_human_review_bypasses_hgates(self):
        hgates = {gate: "" for gate in ["h01", "h02", "h03", "h04", "h05"]}  # none reviewed

        ready, blockers = compute_verdict(
            _passing_grades(),
            _passing_coverage(),
            _passing_checkpoints(),
            hgates,
            skip_human_review=True,
        )
        # Only checkpoint/grade/coverage blockers — no H-gate blockers
        hgate_blockers = [b for b in blockers if "not reviewed" in b or "FAIL" in b]
        assert len(hgate_blockers) == 0

    def test_conditional_gate_blocks(self):
        hgates = _passing_hgates()
        hgates["h03"] = "CONDITIONAL"

        ready, blockers = compute_verdict(
            _passing_grades(),
            _passing_coverage(),
            _passing_checkpoints(),
            hgates,
        )
        assert ready is False
        assert any("CONDITIONAL" in b for b in blockers)


# ---------------------------------------------------------------------------
# Pure function: no side effects
# ---------------------------------------------------------------------------

class TestPureFunction:
    def test_does_not_modify_inputs(self):
        """compute_verdict must not mutate the input dicts."""
        grades = _passing_grades()
        coverage = _passing_coverage()
        checkpoints = _passing_checkpoints()
        hgates = _passing_hgates()
        grades_copy = dict(grades)
        checkpoints_copy = dict(checkpoints)

        compute_verdict(grades, coverage, checkpoints, hgates, skip_human_review=True)

        assert grades == grades_copy
        assert checkpoints == checkpoints_copy


# ---------------------------------------------------------------------------
# Exit-code contract: main() must exit 0 on ready, 1 on not-ready
# ---------------------------------------------------------------------------

class TestExitCodes:
    def _patch_main(self, monkeypatch, tmp_path, ready: bool):
        """Patch all I/O in main() so it runs cleanly to sys.exit."""
        # Redirect file output path so report write doesn't crash
        monkeypatch.setattr(readiness_scorecard, "_ROOT", tmp_path)
        (tmp_path / "reports" / "3d" / "python").mkdir(parents=True)

        # Stub data-reading functions (called before compute_verdict)
        monkeypatch.setattr(readiness_scorecard, "_read_checkpoints",
                            lambda f, p: {})
        monkeypatch.setattr(readiness_scorecard, "_collect_grades",
                            lambda f, p: {"A": 5, "B": 0, "C": 0, "D": 0, "F": 0, "ungraded": 0})
        monkeypatch.setattr(readiness_scorecard, "_count_locale_coverage",
                            lambda s, f, p: {
                                "locales_present": 30, "total_locales": 36,
                                "coverage": 30 / 36, "total_files": 150,
                            })
        monkeypatch.setattr(readiness_scorecard, "_read_hgate_signoffs",
                            lambda f, p: {g: "PASS" for g in
                                          ["h01", "h02", "h03", "h04", "h05"]})

        # The contract under test: does main() correctly translate ready → exit code?
        monkeypatch.setattr(readiness_scorecard, "compute_verdict",
                            lambda *a, **kw: (ready, [] if ready else ["F-grade: 1"]))

        # Prevent real subprocess call to project_phase_store.py
        monkeypatch.setattr(readiness_scorecard, "_set_checkpoint",
                            lambda *a, **kw: None)

    def test_exit_0_when_ready(self, tmp_path, monkeypatch):
        self._patch_main(monkeypatch, tmp_path, ready=True)
        monkeypatch.setattr("sys.argv", ["readiness_scorecard.py",
                                         "--family", "3d", "--platform", "python",
                                         "--skip-human-review"])
        with pytest.raises(SystemExit) as exc:
            readiness_scorecard.main()
        assert exc.value.code == 0

    def test_exit_1_when_not_ready(self, tmp_path, monkeypatch):
        self._patch_main(monkeypatch, tmp_path, ready=False)
        monkeypatch.setattr("sys.argv", ["readiness_scorecard.py",
                                         "--family", "3d", "--platform", "python",
                                         "--skip-human-review"])
        with pytest.raises(SystemExit) as exc:
            readiness_scorecard.main()
        assert exc.value.code == 1
