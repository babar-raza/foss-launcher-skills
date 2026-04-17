"""Tests for check_plan_quality.py — plan quality static analysis.

Static, deterministic tests only: no network, no LLM, no subprocesses.
Covers all 5 PQ rules plus happy-path (clean plan → 0 findings).
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

_CI_ROOT = Path(__file__).resolve().parent.parent
if str(_CI_ROOT) not in sys.path:
    sys.path.insert(0, str(_CI_ROOT))

import check_plan_quality  # noqa: E402


REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "plan-normalize"


def _read_fixture(name: str) -> str:
    return (FIXTURE_DIR / name).read_text(encoding="utf-8", errors="ignore")


# ---------------------------------------------------------------------------
# PQ-01 MIXED_CONTEXT
# ---------------------------------------------------------------------------

class TestPQ01MixedContext(unittest.TestCase):

    def test_fires_on_mixed_historical_fixture(self):
        text = _read_fixture("mixed-historical-and-current.md")
        result = check_plan_quality.check_pq01(text)
        self.assertIsNotNone(result, "PQ-01 should fire on mixed-historical fixture")
        self.assertIn("sprint", result.lower())

    def test_silent_on_clean_fixture(self):
        text = _read_fixture("clean-execution-plan.md")
        result = check_plan_quality.check_pq01(text)
        self.assertIsNone(result, "PQ-01 should not fire on clean fixture")

    def test_fires_when_archive_h2_and_ready_status(self):
        text = "## Sprint 3 Retrospective\n\nWe did stuff.\n\n## Open Work\n\n- item\n  - Status: ready\n"
        result = check_plan_quality.check_pq01(text)
        self.assertIsNotNone(result)

    def test_silent_when_only_archive_h2_no_open_actions(self):
        text = "## Sprint 3 Retrospective\n\nWe completed everything.\n"
        result = check_plan_quality.check_pq01(text)
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# PQ-02 STALE_UNNORMALIZED
# ---------------------------------------------------------------------------

class TestPQ02StaleUnnormalized(unittest.TestCase):

    def test_fires_on_old_file_without_normalization_record(self, tmp_path=None):
        import tempfile, os, time
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False,
                                        encoding="utf-8") as f:
            f.write("## Plan\n\nSome content.\n")
            fname = f.name
        # Set mtime to 30 days ago
        old_time = (
            __import__("datetime").datetime.now()
            - __import__("datetime").timedelta(days=30)
        ).timestamp()
        os.utime(fname, (old_time, old_time))
        try:
            result = check_plan_quality.check_pq02(fname, open(fname).read(), min_age_days=7)
            self.assertIsNotNone(result, "PQ-02 should fire on stale file")
            self.assertIn("30", result)
        finally:
            os.unlink(fname)

    def test_silent_on_file_with_normalization_record(self, tmp_path=None):
        import tempfile, os
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False,
                                        encoding="utf-8") as f:
            f.write("## Plan\n\nContent.\n\n## Plan Normalization Record\n\nDone.\n")
            fname = f.name
        old_time = (
            __import__("datetime").datetime.now()
            - __import__("datetime").timedelta(days=30)
        ).timestamp()
        os.utime(fname, (old_time, old_time))
        try:
            result = check_plan_quality.check_pq02(fname, open(fname).read(), min_age_days=7)
            self.assertIsNone(result, "PQ-02 should be silent when normalization record present")
        finally:
            os.unlink(fname)

    def test_silent_on_fresh_file(self, tmp_path=None):
        import tempfile, os
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False,
                                        encoding="utf-8") as f:
            f.write("## Plan\n\nContent.\n")
            fname = f.name
        # mtime is now (fresh)
        try:
            result = check_plan_quality.check_pq02(fname, open(fname).read(), min_age_days=7)
            self.assertIsNone(result, "PQ-02 should be silent on freshly-created file")
        finally:
            os.unlink(fname)

    def test_uses_patched_mtime(self):
        """Verify mtime patching works for testing purposes."""
        text = "## Plan\n\nContent.\n"
        old_ts = (
            __import__("datetime").datetime.now()
            - __import__("datetime").timedelta(days=15)
        ).timestamp()
        with patch("os.path.getmtime", return_value=old_ts):
            result = check_plan_quality.check_pq02("fake.md", text, min_age_days=7)
        self.assertIsNotNone(result)
        self.assertIn("15", result)


# ---------------------------------------------------------------------------
# PQ-03 COMPLETED_MIXED_WITH_OPEN
# ---------------------------------------------------------------------------

class TestPQ03CompletedMixedWithOpen(unittest.TestCase):

    def test_fires_when_both_sections_present(self):
        text = "## Completed\n\nOld stuff.\n\n## Open Work\n\nNew things.\n"
        result = check_plan_quality.check_pq03(text)
        self.assertIsNotNone(result)

    def test_fires_on_done_and_backlog(self):
        text = "## Done\n\nFinished.\n\n## Backlog\n\nQueued.\n"
        result = check_plan_quality.check_pq03(text)
        self.assertIsNotNone(result)

    def test_silent_on_clean_fixture(self):
        text = _read_fixture("clean-execution-plan.md")
        result = check_plan_quality.check_pq03(text)
        self.assertIsNone(result)

    def test_silent_when_only_open_work(self):
        text = "## Open Work\n\nTasks.\n"
        result = check_plan_quality.check_pq03(text)
        self.assertIsNone(result)

    def test_silent_when_only_completed(self):
        text = "## Completed\n\nAll done.\n"
        result = check_plan_quality.check_pq03(text)
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# PQ-04 MATURITY_AMBIGUITY
# ---------------------------------------------------------------------------

class TestPQ04MaturityAmbiguity(unittest.TestCase):

    def test_fires_on_partially_validated_fixture(self):
        text = _read_fixture("partially-validated-capabilities.md")
        result = check_plan_quality.check_pq04(text)
        self.assertIsNotNone(result, "PQ-04 should fire on partially-validated fixture")

    def test_fires_on_spec_only_with_ready(self):
        text = "## Open Work\n\n1. Do thing\n   - Relies on: spec-only module\n   - Status: ready\n"
        result = check_plan_quality.check_pq04(text)
        self.assertIsNotNone(result)

    def test_silent_on_clean_fixture(self):
        text = _read_fixture("clean-execution-plan.md")
        result = check_plan_quality.check_pq04(text)
        self.assertIsNone(result)

    def test_silent_when_spec_only_in_different_section_from_ready(self):
        # spec-only in one section, ready in another — rule is per-section
        text = (
            "## Constraints\n\nThe spec-only interface is deferred.\n\n"
            "## Other Work\n\n- item\n  - Status: ready\n"
        )
        result = check_plan_quality.check_pq04(text)
        # Different sections — should NOT fire
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# PQ-05 LONG_UNNORMALIZED
# ---------------------------------------------------------------------------

class TestPQ05LongUnnormalized(unittest.TestCase):

    def _make_long_plan(self, num_h2: int, with_record: bool = False) -> str:
        sections = [f"## Section {i}\n\nContent {i}.\n" for i in range(1, num_h2 + 1)]
        text = "# Plan\n\n" + "\n".join(sections)
        if with_record:
            text += "\n## Plan Normalization Record\n\nNormalized.\n"
        return text

    def test_fires_on_five_h2_without_record(self):
        text = self._make_long_plan(5)
        result = check_plan_quality.check_pq05(text)
        self.assertIsNotNone(result)
        self.assertIn("5", result)

    def test_silent_on_four_h2(self):
        text = self._make_long_plan(4)
        result = check_plan_quality.check_pq05(text)
        self.assertIsNone(result)

    def test_silent_on_five_h2_with_normalization_record(self):
        text = self._make_long_plan(5, with_record=True)
        result = check_plan_quality.check_pq05(text)
        self.assertIsNone(result)

    def test_silent_on_empty_file(self):
        result = check_plan_quality.check_pq05("")
        self.assertIsNone(result)

    def test_silent_on_file_with_no_h2(self):
        text = "# Title\n\nJust a paragraph.\n"
        result = check_plan_quality.check_pq05(text)
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# Integration: scan_file and collect_files
# ---------------------------------------------------------------------------

class TestScanFile(unittest.TestCase):

    def test_scan_clean_fixture_returns_no_pq_findings(self):
        path = str(FIXTURE_DIR / "clean-execution-plan.md")
        findings = check_plan_quality.scan_file(path, min_age_days=7)
        pq_findings = [f for f in findings if f.rule.startswith("PQ-")]
        self.assertEqual(pq_findings, [],
                         f"Clean fixture should produce 0 PQ findings, got: {pq_findings}")

    def test_scan_mixed_historical_fires_pq01(self):
        path = str(FIXTURE_DIR / "mixed-historical-and-current.md")
        findings = check_plan_quality.scan_file(path, min_age_days=7)
        rules = {f.rule for f in findings}
        self.assertIn("PQ-01", rules)

    def test_scan_partially_validated_fires_pq04(self):
        path = str(FIXTURE_DIR / "partially-validated-capabilities.md")
        findings = check_plan_quality.scan_file(path, min_age_days=7)
        rules = {f.rule for f in findings}
        self.assertIn("PQ-04", rules)

    def test_scan_nonexistent_file_returns_read_error(self):
        findings = check_plan_quality.scan_file("/nonexistent/path/file.md", min_age_days=7)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].rule, "READ_ERROR")

    def test_collect_files_directory(self):
        files = check_plan_quality.collect_files([str(FIXTURE_DIR)])
        self.assertGreater(len(files), 0)
        for f in files:
            self.assertTrue(f.endswith(".md"))

    def test_collect_files_sorted_deduped(self):
        path = str(FIXTURE_DIR / "clean-execution-plan.md")
        files = check_plan_quality.collect_files([path, path])
        self.assertEqual(len(files), 1)

    def test_collect_files_skips_non_md(self):
        files = check_plan_quality.collect_files([str(FIXTURE_DIR / "clean-execution-plan.md"),
                                                   "scripts/ci/check_plan_quality.py"])
        for f in files:
            self.assertTrue(f.endswith(".md"))


# ---------------------------------------------------------------------------
# Integration: run() + JSON output
# ---------------------------------------------------------------------------

class TestRunOutput(unittest.TestCase):

    def test_run_clean_fixture_zero_findings(self):
        output = check_plan_quality.run(
            [str(FIXTURE_DIR / "clean-execution-plan.md")],
            min_age_days=7,
        )
        self.assertIn("0 finding(s)", output)

    def test_run_mixed_fixture_has_warnings(self):
        output = check_plan_quality.run(
            [str(FIXTURE_DIR / "mixed-historical-and-current.md")],
            min_age_days=7,
        )
        self.assertIn("WARN", output)
        self.assertIn("PQ-01", output)

    def test_run_json_output_valid(self):
        output = check_plan_quality.run(
            [str(FIXTURE_DIR)],
            min_age_days=0,  # age 0 to avoid flakiness on fresh fixtures
            as_json=True,
        )
        data = json.loads(output)
        self.assertIn("files_scanned", data)
        self.assertIn("finding_count", data)
        self.assertIn("findings", data)
        self.assertIsInstance(data["findings"], list)

    def test_run_summary_line_present(self):
        output = check_plan_quality.run(
            [str(FIXTURE_DIR / "clean-execution-plan.md")],
            min_age_days=7,
        )
        self.assertRegex(output, r"\d+ file\(s\) scanned, \d+ finding\(s\)")


if __name__ == "__main__":
    unittest.main()
