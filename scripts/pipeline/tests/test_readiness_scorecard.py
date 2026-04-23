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


@pytest.fixture(autouse=True)
def _reset_rs():
    yield
    readiness_scorecard.configure()


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
        readiness_scorecard.configure(repo_root=tmp_path)
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
        # T3-MOCK: target=sys.argv reason="CLI main() does not accept argv param" removal=PERMANENT
        monkeypatch.setattr("sys.argv", ["readiness_scorecard.py",
                                         "--family", "3d", "--platform", "python",
                                         "--skip-human-review"])
        with pytest.raises(SystemExit) as exc:
            readiness_scorecard.main()
        assert exc.value.code == 0

    def test_exit_1_when_not_ready(self, tmp_path, monkeypatch):
        self._patch_main(monkeypatch, tmp_path, ready=False)
        # T3-MOCK: target=sys.argv reason="CLI main() does not accept argv param" removal=PERMANENT
        monkeypatch.setattr("sys.argv", ["readiness_scorecard.py",
                                         "--family", "3d", "--platform", "python",
                                         "--skip-human-review"])
        with pytest.raises(SystemExit) as exc:
            readiness_scorecard.main()
        assert exc.value.code == 1


# ---------------------------------------------------------------------------
# CP-P2 Bug 1-4 tests: sign-off parser hardening
# ---------------------------------------------------------------------------

class TestSignoffParserHardening:
    """Tests for CRLF normalization, case-insensitive parsing, and comment stripping."""

    def test_lowercase_pass_accepted(self, tmp_path, monkeypatch):
        """Bug 2: lowercase 'pass' must be accepted."""
        review_dir = tmp_path / "reports" / "human-review"
        review_dir.mkdir(parents=True)
        (review_dir / "3d-java-h01-sample.md").write_text(
            '# H-01\n\n```yaml\nresult: "pass"\n```\n'
        )
        readiness_scorecard.configure(repo_root=tmp_path)
        results = readiness_scorecard._read_hgate_signoffs("3d", "java")
        assert results["h01"] == "PASS"

    def test_mixed_case_pass_accepted(self, tmp_path, monkeypatch):
        """Bug 2: mixed case 'Pass' must be accepted."""
        review_dir = tmp_path / "reports" / "human-review"
        review_dir.mkdir(parents=True)
        (review_dir / "3d-java-h01-sample.md").write_text(
            '# H-01\n\n```yaml\nresult: "Pass"\n```\n'
        )
        readiness_scorecard.configure(repo_root=tmp_path)
        results = readiness_scorecard._read_hgate_signoffs("3d", "java")
        assert results["h01"] == "PASS"

    def test_crlf_line_endings_accepted(self, tmp_path, monkeypatch):
        """Bug 1: CRLF line endings must not break parsing."""
        review_dir = tmp_path / "reports" / "human-review"
        review_dir.mkdir(parents=True)
        # Write with explicit CRLF
        content = '# H-01\r\n\r\n```yaml\r\nresult: "PASS"\r\n```\r\n'
        (review_dir / "3d-java-h01-sample.md").write_bytes(content.encode("utf-8"))
        readiness_scorecard.configure(repo_root=tmp_path)
        results = readiness_scorecard._read_hgate_signoffs("3d", "java")
        assert results["h01"] == "PASS"

    def test_inline_comment_stripped(self, tmp_path, monkeypatch):
        """Bug 3: inline comments after result value must be stripped."""
        review_dir = tmp_path / "reports" / "human-review"
        review_dir.mkdir(parents=True)
        (review_dir / "3d-java-h01-sample.md").write_text(
            '# H-01\n\n```yaml\nresult: "PASS" # reviewer: looks good\n```\n'
        )
        readiness_scorecard.configure(repo_root=tmp_path)
        results = readiness_scorecard._read_hgate_signoffs("3d", "java")
        assert results["h01"] == "PASS"

    def test_lowercase_fail_accepted(self, tmp_path, monkeypatch):
        """Bug 2: lowercase 'fail' must be accepted and normalized to FAIL."""
        review_dir = tmp_path / "reports" / "human-review"
        review_dir.mkdir(parents=True)
        (review_dir / "3d-java-h02-sample.md").write_text(
            '# H-02\n\n```yaml\nresult: fail\n```\n'
        )
        readiness_scorecard.configure(repo_root=tmp_path)
        results = readiness_scorecard._read_hgate_signoffs("3d", "java")
        assert results["h02"] == "FAIL"

    def test_lowercase_conditional_accepted(self, tmp_path, monkeypatch):
        """Bug 2: lowercase 'conditional' must be accepted."""
        review_dir = tmp_path / "reports" / "human-review"
        review_dir.mkdir(parents=True)
        (review_dir / "3d-java-h03-sample.md").write_text(
            '# H-03\n\n```yaml\nresult: conditional\n```\n'
        )
        readiness_scorecard.configure(repo_root=tmp_path)
        results = readiness_scorecard._read_hgate_signoffs("3d", "java")
        assert results["h03"] == "CONDITIONAL"

    def test_skip_human_review_json_recorded(self, tmp_path, monkeypatch):
        """Bug 4: --skip-human-review should be recorded in JSON output."""
        helper = TestExitCodes()
        helper._patch_main(monkeypatch, tmp_path, ready=True)
        import io, json
        out = io.StringIO()
        # T3-MOCK: target=sys.stdout reason="capture CLI JSON output" removal=PERMANENT
        monkeypatch.setattr("sys.stdout", out)
        # T3-MOCK: target=sys.argv reason="CLI main() does not accept argv param" removal=PERMANENT
        monkeypatch.setattr("sys.argv", ["readiness_scorecard.py",
                                         "--family", "3d", "--platform", "python",
                                         "--skip-human-review", "--json"])
        with pytest.raises(SystemExit):
            readiness_scorecard.main()
        output = out.getvalue()
        # Extract the JSON object (first { to matching })
        start = output.index("{")
        # Find the matching closing brace by counting nesting
        depth = 0
        for i, c in enumerate(output[start:], start):
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        data = json.loads(output[start:end])
        assert data["skip_human_review"] is True
