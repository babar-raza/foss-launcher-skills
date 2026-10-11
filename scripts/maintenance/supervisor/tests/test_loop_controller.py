"""
test_loop_controller.py -- 24 negative controls + 2 positive controls for the
post-sprint autonomy loop controller.

Proves fail-closed behavior: every non-green path must NOT produce ACCEPT.
"""
from __future__ import annotations

import json
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SUPERVISOR = _HERE.parent
sys.path.insert(0, str(_SUPERVISOR))

from loop_controller import (
    LoopClassification,
    check_quality_scores,
    classify_summary,
    compute_decision,
    loop_control,
    validate_evidence_bundle,
)


def _make_evidence_dir(summary_yaml: str | None = None, evidence_files: dict[str, str] | None = None):
    """Create a temp evidence dir with optional summary YAML and evidence files."""
    tmpdir = tempfile.mkdtemp()
    d = Path(tmpdir)
    if summary_yaml is not None:
        (d / "stage3-final-sprint-summary.yaml").write_text(summary_yaml, encoding="utf-8")
    if evidence_files:
        for name, content in evidence_files.items():
            (d / name).write_text(content, encoding="utf-8")
    return d


def _all_green_yaml(extra_files=None):
    """Return a valid ALL_GREEN summary YAML with evidence files on disk."""
    files = extra_files or ["stage3-execution-log.md"]
    files_yaml = "\n".join(f"  - {f}" for f in files)
    return textwrap.dedent(f"""\
        outcome: ALL_GREEN
        retry_count: 0
        scores:
          accuracy: 5
          completeness: 5
          integration: 5
        taskcards:
          - id: TC-001
            status: ACCEPTED
        evidence_files:
        {files_yaml}
    """)


# ============================================================
# MISSING (tests 1-3)
# ============================================================

class TestMissing(unittest.TestCase):
    def test_01_missing_summary_file(self):
        d = _make_evidence_dir(summary_yaml=None)
        cls, _ = classify_summary(Path(d))
        self.assertEqual(cls, LoopClassification.MISSING)
        decision = compute_decision(cls, False, False)
        self.assertNotEqual(decision["action"], "ACCEPT")

    def test_02_invalid_yaml_syntax(self):
        d = _make_evidence_dir(summary_yaml="[[[not: valid: yaml: {{{")
        cls, _ = classify_summary(Path(d))
        self.assertEqual(cls, LoopClassification.MISSING)
        decision = compute_decision(cls, False, False)
        self.assertNotEqual(decision["action"], "ACCEPT")

    def test_03_empty_file(self):
        d = _make_evidence_dir(summary_yaml="")
        cls, _ = classify_summary(Path(d))
        self.assertEqual(cls, LoopClassification.MISSING)


# ============================================================
# PROSE_ONLY (tests 4-5)
# ============================================================

class TestProseOnly(unittest.TestCase):
    def test_04_no_outcome_key(self):
        d = _make_evidence_dir(summary_yaml="summary: Everything went great\nstatus: done\n")
        cls, _ = classify_summary(Path(d))
        self.assertEqual(cls, LoopClassification.PROSE_ONLY)
        decision = compute_decision(cls, False, False)
        self.assertNotEqual(decision["action"], "ACCEPT")

    def test_05_narrative_text(self):
        d = _make_evidence_dir(summary_yaml="description: The sprint completed all tasks successfully.\nnotes: No issues found.\n")
        cls, _ = classify_summary(Path(d))
        self.assertEqual(cls, LoopClassification.PROSE_ONLY)
        decision = compute_decision(cls, False, False)
        self.assertNotEqual(decision["action"], "ACCEPT")


# ============================================================
# SCORES_MISSING (tests 6-7)
# ============================================================

class TestScoresMissing(unittest.TestCase):
    def test_06_scores_key_absent(self):
        d = _make_evidence_dir(summary_yaml="outcome: ALL_GREEN\ntaskcards:\n  - id: TC-1\n    status: ACCEPTED\n")
        cls, _ = classify_summary(Path(d))
        self.assertEqual(cls, LoopClassification.SCORES_MISSING)
        decision = compute_decision(cls, False, False)
        self.assertNotEqual(decision["action"], "ACCEPT")

    def test_07_scores_empty_dict(self):
        d = _make_evidence_dir(summary_yaml="outcome: ALL_GREEN\nscores:\ntaskcards:\n  - id: TC-1\n    status: ACCEPTED\n")
        cls, _ = classify_summary(Path(d))
        # scores parsed as None (empty value) -> SCORES_MISSING
        self.assertEqual(cls, LoopClassification.SCORES_MISSING)


# ============================================================
# EVIDENCE_MISSING (tests 8-10)
# ============================================================

class TestEvidenceMissing(unittest.TestCase):
    def test_08_evidence_files_key_absent(self):
        yaml = "outcome: ALL_GREEN\nscores:\n  accuracy: 5\ntaskcards:\n  - id: TC-1\n    status: ACCEPTED\n"
        d = _make_evidence_dir(summary_yaml=yaml)
        cls, _ = classify_summary(Path(d))
        self.assertEqual(cls, LoopClassification.EVIDENCE_MISSING)
        decision = compute_decision(cls, False, False)
        self.assertNotEqual(decision["action"], "ACCEPT")

    def test_09_evidence_files_empty_list(self):
        yaml = "outcome: ALL_GREEN\nscores:\n  accuracy: 5\nevidence_files:\ntaskcards:\n  - id: TC-1\n    status: ACCEPTED\n"
        d = _make_evidence_dir(summary_yaml=yaml)
        cls, _ = classify_summary(Path(d))
        self.assertEqual(cls, LoopClassification.EVIDENCE_MISSING)

    def test_10_evidence_files_not_on_disk(self):
        yaml = textwrap.dedent("""\
            outcome: ALL_GREEN
            scores:
              accuracy: 5
            evidence_files:
              - does-not-exist.md
              - also-missing.md
            taskcards:
              - id: TC-1
                status: ACCEPTED
        """)
        d = _make_evidence_dir(summary_yaml=yaml)
        cls, details = classify_summary(Path(d))
        self.assertEqual(cls, LoopClassification.EVIDENCE_MISSING)
        self.assertIn("missing_evidence_files", details)


# ============================================================
# TASKCARDS_INCOMPLETE (tests 11-13)
# ============================================================

class TestTaskcardsIncomplete(unittest.TestCase):
    def test_11_taskcards_key_absent(self):
        yaml = textwrap.dedent("""\
            outcome: ALL_GREEN
            scores:
              accuracy: 5
            evidence_files:
              - log.md
        """)
        d = _make_evidence_dir(summary_yaml=yaml, evidence_files={"log.md": "ok"})
        cls, _ = classify_summary(Path(d))
        self.assertEqual(cls, LoopClassification.TASKCARDS_INCOMPLETE)

    def test_12_taskcards_missing_status(self):
        yaml = textwrap.dedent("""\
            outcome: ALL_GREEN
            scores:
              accuracy: 5
            evidence_files:
              - log.md
            taskcards:
              - id: TC-1
        """)
        d = _make_evidence_dir(summary_yaml=yaml, evidence_files={"log.md": "ok"})
        cls, _ = classify_summary(Path(d))
        self.assertEqual(cls, LoopClassification.TASKCARDS_INCOMPLETE)

    def test_13_taskcards_partial_completion(self):
        yaml = textwrap.dedent("""\
            outcome: NOT_GREEN
            scores:
              accuracy: 5
            evidence_files:
              - log.md
            taskcards:
              - id: TC-1
                status: ACCEPTED
              - id: TC-2
                status: pending
        """)
        d = _make_evidence_dir(summary_yaml=yaml, evidence_files={"log.md": "ok"})
        cls, _ = classify_summary(Path(d))
        self.assertEqual(cls, LoopClassification.STRUCTURED_NOT_GREEN)
        decision = compute_decision(cls, True, True)
        self.assertNotEqual(decision["action"], "ACCEPT")


# ============================================================
# CONTRADICTORY (tests 14-16)
# ============================================================

class TestContradictory(unittest.TestCase):
    def test_14_outcome_green_scores_below(self):
        yaml = textwrap.dedent("""\
            outcome: ALL_GREEN
            scores:
              accuracy: 2
              completeness: 5
            evidence_files:
              - log.md
            taskcards:
              - id: TC-1
                status: ACCEPTED
        """)
        d = _make_evidence_dir(summary_yaml=yaml, evidence_files={"log.md": "ok"})
        cls, details = classify_summary(Path(d))
        self.assertEqual(cls, LoopClassification.CONTRADICTORY)
        decision = compute_decision(cls, True, False)
        self.assertEqual(decision["action"], "BLOCK")

    def test_15_outcome_green_taskcards_failed(self):
        yaml = textwrap.dedent("""\
            outcome: ALL_GREEN
            scores:
              accuracy: 5
            evidence_files:
              - log.md
            taskcards:
              - id: TC-1
                status: FAILED
        """)
        d = _make_evidence_dir(summary_yaml=yaml, evidence_files={"log.md": "ok"})
        cls, _ = classify_summary(Path(d))
        self.assertEqual(cls, LoopClassification.CONTRADICTORY)

    def test_16_scores_pass_outcome_not_green(self):
        yaml = textwrap.dedent("""\
            outcome: NOT_GREEN
            scores:
              accuracy: 5
              completeness: 5
            evidence_files:
              - log.md
            taskcards:
              - id: TC-1
                status: ACCEPTED
        """)
        d = _make_evidence_dir(summary_yaml=yaml, evidence_files={"log.md": "ok"})
        cls, _ = classify_summary(Path(d))
        # Valid NOT_GREEN, not contradictory (asymmetry)
        self.assertEqual(cls, LoopClassification.STRUCTURED_NOT_GREEN)


# ============================================================
# BLOCKED_EXTERNAL (tests 17-18)
# ============================================================

class TestBlockedExternal(unittest.TestCase):
    def test_17_outcome_blocked(self):
        yaml = textwrap.dedent("""\
            outcome: BLOCKED
            scores:
              accuracy: 3
            evidence_files:
              - log.md
            taskcards:
              - id: TC-1
                status: BLOCKED_EXTERNAL
        """)
        d = _make_evidence_dir(summary_yaml=yaml, evidence_files={"log.md": "ok"})
        cls, _ = classify_summary(Path(d))
        self.assertEqual(cls, LoopClassification.BLOCKED_EXTERNAL)
        decision = compute_decision(cls, True, False)
        self.assertEqual(decision["action"], "BLOCK")

    def test_18_outcome_blocked_green_scores(self):
        yaml = textwrap.dedent("""\
            outcome: BLOCKED
            scores:
              accuracy: 5
              completeness: 5
            evidence_files:
              - log.md
            taskcards:
              - id: TC-1
                status: ACCEPTED
        """)
        d = _make_evidence_dir(summary_yaml=yaml, evidence_files={"log.md": "ok"})
        cls, _ = classify_summary(Path(d))
        self.assertEqual(cls, LoopClassification.BLOCKED_EXTERNAL)


# ============================================================
# STRUCTURED_NOT_GREEN (tests 19-21)
# ============================================================

class TestStructuredNotGreen(unittest.TestCase):
    def test_19_one_score_below_threshold(self):
        yaml = textwrap.dedent("""\
            outcome: NOT_GREEN
            scores:
              accuracy: 5
              completeness: 3
            evidence_files:
              - log.md
            taskcards:
              - id: TC-1
                status: ACCEPTED
        """)
        d = _make_evidence_dir(summary_yaml=yaml, evidence_files={"log.md": "ok"})
        cls, _ = classify_summary(Path(d))
        self.assertEqual(cls, LoopClassification.STRUCTURED_NOT_GREEN)
        decision = compute_decision(cls, True, False)
        self.assertEqual(decision["action"], "RETRY")

    def test_20_all_scores_below(self):
        yaml = textwrap.dedent("""\
            outcome: NOT_GREEN
            scores:
              accuracy: 2
              completeness: 1
            evidence_files:
              - log.md
            taskcards:
              - id: TC-1
                status: REROUTED
        """)
        d = _make_evidence_dir(summary_yaml=yaml, evidence_files={"log.md": "ok"})
        cls, _ = classify_summary(Path(d))
        self.assertEqual(cls, LoopClassification.STRUCTURED_NOT_GREEN)

    def test_21_outcome_not_green_scores_pass(self):
        yaml = textwrap.dedent("""\
            outcome: NOT_GREEN
            scores:
              accuracy: 5
            evidence_files:
              - log.md
            taskcards:
              - id: TC-1
                status: ACCEPTED
        """)
        d = _make_evidence_dir(summary_yaml=yaml, evidence_files={"log.md": "ok"})
        cls, _ = classify_summary(Path(d))
        self.assertEqual(cls, LoopClassification.STRUCTURED_NOT_GREEN)
        decision = compute_decision(cls, True, True)
        self.assertEqual(decision["action"], "RETRY")


# ============================================================
# RETRY EXHAUSTION (tests 22-23)
# ============================================================

class TestRetryExhaustion(unittest.TestCase):
    def test_22_retry_at_max(self):
        decision = compute_decision(
            LoopClassification.STRUCTURED_NOT_GREEN,
            evidence_complete=True, scores_pass=False,
            retry_count=2, max_retries=2,
        )
        self.assertEqual(decision["action"], "ESCALATE")

    def test_23_retry_above_max(self):
        decision = compute_decision(
            LoopClassification.PROSE_ONLY,
            evidence_complete=False, scores_pass=False,
            retry_count=5, max_retries=2,
        )
        self.assertEqual(decision["action"], "ESCALATE")


# ============================================================
# FAIL-CLOSED META-TEST (test 24)
# ============================================================

class TestFailClosed(unittest.TestCase):
    def test_24_no_non_green_classification_produces_accept(self):
        """Parametric: all non-ALL_GREEN classifications must NOT produce ACCEPT."""
        non_green = [
            LoopClassification.MISSING,
            LoopClassification.PROSE_ONLY,
            LoopClassification.SCORES_MISSING,
            LoopClassification.EVIDENCE_MISSING,
            LoopClassification.TASKCARDS_INCOMPLETE,
            LoopClassification.BLOCKED_EXTERNAL,
            LoopClassification.CONTRADICTORY,
            LoopClassification.STRUCTURED_NOT_GREEN,
        ]
        for cls in non_green:
            for ev in (True, False):
                for sc in (True, False):
                    decision = compute_decision(cls, ev, sc)
                    self.assertNotEqual(
                        decision["action"], "ACCEPT",
                        f"{cls.value} with evidence={ev} scores={sc} should not ACCEPT"
                    )


# ============================================================
# POSITIVE CONTROLS
# ============================================================

class TestPositiveControls(unittest.TestCase):
    def test_structured_all_green_accepts(self):
        yaml = _all_green_yaml(["log.md"])
        d = _make_evidence_dir(summary_yaml=yaml, evidence_files={"log.md": "ok"})
        trace, exit_code = loop_control(d, run_id="test-green", dry_run=True)
        self.assertEqual(exit_code, 0)
        self.assertEqual(trace["classification"], "STRUCTURED_ALL_GREEN")
        self.assertEqual(trace["decision"]["action"], "ACCEPT")

    def test_dry_run_no_file_written(self):
        yaml = _all_green_yaml(["log.md"])
        d = _make_evidence_dir(summary_yaml=yaml, evidence_files={"log.md": "ok"})
        trace, _ = loop_control(d, run_id="test-dry", dry_run=True)
        self.assertIsNone(trace["yaml_path"])


# ============================================================
# UNIT TESTS for helpers
# ============================================================

class TestValidateEvidenceBundle(unittest.TestCase):
    def test_none_returns_false(self):
        ok, missing = validate_evidence_bundle(Path("/tmp"), None)
        self.assertFalse(ok)

    def test_empty_list_returns_false(self):
        ok, missing = validate_evidence_bundle(Path("/tmp"), [])
        self.assertFalse(ok)


class TestCheckQualityScores(unittest.TestCase):
    def test_none_returns_false(self):
        ok, failing = check_quality_scores(None)
        self.assertFalse(ok)

    def test_below_threshold(self):
        ok, failing = check_quality_scores({"a": 3, "b": 5}, threshold=4)
        self.assertFalse(ok)
        self.assertIn("a", failing)

    def test_all_pass(self):
        ok, failing = check_quality_scores({"a": 4, "b": 5}, threshold=4)
        self.assertTrue(ok)
        self.assertEqual(failing, [])


# ============================================================
# INTEGRATION TESTS (end-to-end loop_control)
# ============================================================

class TestLoopIntegration(unittest.TestCase):
    def test_integration_full_green_path(self):
        """End-to-end: all-green evidence → ACCEPT with exit 0."""
        yaml = _all_green_yaml(["execution-log.md"])
        d = _make_evidence_dir(
            summary_yaml=yaml,
            evidence_files={"execution-log.md": "Sprint completed successfully."},
        )
        trace, exit_code = loop_control(d, run_id="integ-green", dry_run=True)
        self.assertEqual(exit_code, 0)
        self.assertEqual(trace["classification"], "STRUCTURED_ALL_GREEN")
        self.assertEqual(trace["decision"]["action"], "ACCEPT")
        self.assertTrue(trace["evidence_validation"]["complete"])
        self.assertTrue(trace["quality_check"]["all_pass"])
        self.assertEqual(trace["status"], "LOOP_COMPLETE")

    def test_integration_retry_path(self):
        """End-to-end: NOT_GREEN evidence → RETRY with correct next_stage."""
        yaml = textwrap.dedent("""\
            outcome: NOT_GREEN
            scores:
              accuracy: 3
              completeness: 4
            evidence_files:
              - log.md
            taskcards:
              - id: TC-001
                status: ACCEPTED
        """)
        d = _make_evidence_dir(summary_yaml=yaml, evidence_files={"log.md": "ok"})
        trace, exit_code = loop_control(d, run_id="integ-retry", dry_run=True)
        self.assertEqual(exit_code, 0)
        self.assertEqual(trace["classification"], "STRUCTURED_NOT_GREEN")
        self.assertEqual(trace["decision"]["action"], "RETRY")
        self.assertEqual(trace["decision"]["next_stage"], "prompt2 -> prompt3")

    def test_integration_contradiction_path(self):
        """End-to-end: contradictory evidence → BLOCK with exit 2."""
        yaml = textwrap.dedent("""\
            outcome: ALL_GREEN
            scores:
              accuracy: 2
              completeness: 1
            evidence_files:
              - log.md
            taskcards:
              - id: TC-001
                status: ACCEPTED
        """)
        d = _make_evidence_dir(summary_yaml=yaml, evidence_files={"log.md": "ok"})
        trace, exit_code = loop_control(d, run_id="integ-contra", dry_run=True)
        self.assertEqual(exit_code, 2)
        self.assertEqual(trace["classification"], "CONTRADICTORY")
        self.assertEqual(trace["decision"]["action"], "BLOCK")
        self.assertEqual(trace["status"], "LOOP_BLOCKED")


# ============================================================
# EXTENDED NEGATIVE CONTROLS (taskcard transitions, evidence mismatch, reroute contradictions)
# ============================================================

from loop_controller import validate_taskcard_transition, VALID_TRANSITIONS


class TestNegativeControlsExtended(unittest.TestCase):
    """Negative controls for taskcard state transitions and extended scenarios."""

    # ---- Taskcard state transition controls ----

    def test_nc_taskcard_skip_verified(self):
        """IMPLEMENTED → ACCEPTED is invalid (must go through VERIFIED + SCORED)."""
        self.assertFalse(validate_taskcard_transition("IMPLEMENTED", "ACCEPTED"))

    def test_nc_taskcard_skip_scored(self):
        """VERIFIED → ACCEPTED is invalid (must be SCORED first)."""
        self.assertFalse(validate_taskcard_transition("VERIFIED", "ACCEPTED"))

    def test_nc_rerouted_to_accepted(self):
        """REROUTED → ACCEPTED is invalid (must be REWORKED first)."""
        self.assertFalse(validate_taskcard_transition("REROUTED", "ACCEPTED"))

    def test_nc_proposed_to_accepted(self):
        """PROPOSED → ACCEPTED is invalid (cannot skip everything)."""
        self.assertFalse(validate_taskcard_transition("PROPOSED", "ACCEPTED"))

    def test_nc_terminal_state_no_outgoing(self):
        """Terminal states (ACCEPTED, BLOCKED_EXTERNAL, DEFERRED) have no valid transitions."""
        for terminal in ["ACCEPTED", "ACCEPTED_WITH_LIMITATIONS", "BLOCKED_EXTERNAL", "DEFERRED_WITH_REASON"]:
            self.assertEqual(VALID_TRANSITIONS[terminal], [], f"{terminal} should have no outgoing transitions")

    def test_nc_unknown_state_returns_false(self):
        """Unknown source state returns False."""
        self.assertFalse(validate_taskcard_transition("NONEXISTENT", "READY"))

    # ---- Valid transitions (positive controls) ----

    def test_pc_proposed_to_ready(self):
        self.assertTrue(validate_taskcard_transition("PROPOSED", "READY"))

    def test_pc_scored_to_rerouted(self):
        self.assertTrue(validate_taskcard_transition("SCORED", "REROUTED"))

    def test_pc_reworked_to_verified(self):
        self.assertTrue(validate_taskcard_transition("REWORKED", "VERIFIED"))

    # ---- Reroute contradiction controls ----

    def test_nc_rerouted_accepted_without_reeval(self):
        """STRUCTURED_NOT_GREEN with rerouted taskcard must NOT produce ACCEPT."""
        yaml = textwrap.dedent("""\
            outcome: NOT_GREEN
            scores:
              accuracy: 4
              completeness: 4
            evidence_files:
              - log.md
            taskcards:
              - id: TC-001
                status: REROUTED
        """)
        d = _make_evidence_dir(summary_yaml=yaml, evidence_files={"log.md": "ok"})
        cls, _ = classify_summary(d)
        self.assertEqual(cls, LoopClassification.STRUCTURED_NOT_GREEN)
        decision = compute_decision(cls, True, True, retry_count=0)
        self.assertNotEqual(decision["action"], "ACCEPT")

    def test_nc_evidence_manifest_mismatch(self):
        """Evidence files list referencing non-existent file → EVIDENCE_MISSING."""
        yaml = textwrap.dedent("""\
            outcome: ALL_GREEN
            scores:
              accuracy: 5
              completeness: 5
            evidence_files:
              - this-file-does-not-exist.md
            taskcards:
              - id: TC-001
                status: ACCEPTED
        """)
        d = _make_evidence_dir(summary_yaml=yaml)
        cls, details = classify_summary(d)
        self.assertEqual(cls, LoopClassification.EVIDENCE_MISSING)

    def test_nc_summary_all_green_reroute_contradiction(self):
        """outcome=ALL_GREEN + taskcard status=REROUTED → CONTRADICTORY."""
        yaml = textwrap.dedent("""\
            outcome: ALL_GREEN
            scores:
              accuracy: 5
              completeness: 5
            evidence_files:
              - log.md
            taskcards:
              - id: TC-001
                status: REROUTED
        """)
        d = _make_evidence_dir(summary_yaml=yaml, evidence_files={"log.md": "ok"})
        cls, details = classify_summary(d)
        self.assertEqual(cls, LoopClassification.CONTRADICTORY)


if __name__ == "__main__":
    unittest.main()
