"""Tests for check_plan_origination.py — parallel mission/taskcard tracker detection.

Static, deterministic tests only: no network, no LLM, no subprocesses.
Covers both PO rules, the canonical-anchor escape hatch (F7), and the clean-plan
happy path, plus scan_file/collect_files/run/CLI-exit-code integration.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

_CI_ROOT = Path(__file__).resolve().parent.parent / "checks"
if str(_CI_ROOT) not in sys.path:
    sys.path.insert(0, str(_CI_ROOT))

import check_plan_origination  # noqa: E402


# ---------------------------------------------------------------------------
# Fixture texts (inline — narrow, well-understood scenarios; no fixture files
# needed for a 2-rule check)
# ---------------------------------------------------------------------------

FIXTURE_1_TRIPS_PO01 = """\
## Plan

We will track this multi-session mission ourselves.

```yaml
mission_id: MY-NEW-MISSION
taskcards:
  - id: T1
    status: TODO
```

Progress will be tracked in this custom structure going forward.
"""

FIXTURE_2_TRIPS_PO02 = """\
## Plan

This is a multi-step effort spanning several sessions.

We will create a new tracking file to record task status as we go, since
nothing currently captures this.
"""

FIXTURE_3_CLEAN_CITES_ANCHOR = """\
## Context

This plan spans multiple sessions.

## Mission binding

Per AGENTS.md §17, this plan binds to `MISSION_AUTHORITY.yaml` and
`reports/plan_state/{mission_id}/taskcards.jsonl` (schema 5f). No new tracker
is introduced.

## Fix 1

Build a script. Test it.
"""

FIXTURE_4_ILLUSTRATIVE_EXAMPLE_WITH_ANCHOR = """\
## Plan

This mission binds to the existing `MISSION_AUTHORITY.yaml` mechanism per
AGENTS.md §17 — for illustration, its shape looks like:

```yaml
mission_id: EXAMPLE-ONLY
taskcards:
  - id: T1
    status: TODO
```

No parallel tracker is created; this is purely an illustrative excerpt of the
canonical mechanism already in use.
"""


# ---------------------------------------------------------------------------
# PO-01 PARALLEL_MISSION_SCHEMA
# ---------------------------------------------------------------------------

class TestPO01ParallelMissionSchema(unittest.TestCase):

    def test_fires_on_inline_mission_schema_without_anchor(self):
        result = check_plan_origination.check_po01(FIXTURE_1_TRIPS_PO01)
        self.assertIsNotNone(result, "PO-01 should fire on an uncited mission/taskcard block")
        self.assertIn("mission", result.lower())

    def test_silent_on_clean_fixture(self):
        result = check_plan_origination.check_po01(FIXTURE_3_CLEAN_CITES_ANCHOR)
        self.assertIsNone(result)

    def test_silent_when_illustrative_example_cites_anchor(self):
        """F7 escape-hatch fixture: inline mission/taskcard YAML is fine when the
        plan also cites the canonical mechanism — proves the escape hatch works,
        not just assumed."""
        result = check_plan_origination.check_po01(FIXTURE_4_ILLUSTRATIVE_EXAMPLE_WITH_ANCHOR)
        self.assertIsNone(result)

    def test_silent_on_plain_text_with_no_fenced_block(self):
        text = "## Plan\n\nJust prose, no code fences at all.\n"
        result = check_plan_origination.check_po01(text)
        self.assertIsNone(result)

    def test_silent_on_unrelated_fenced_block(self):
        text = "## Plan\n\n```python\ndef f():\n    return 1\n```\n"
        result = check_plan_origination.check_po01(text)
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# PO-02 NEW_TRACKER_PROPOSAL
# ---------------------------------------------------------------------------

class TestPO02NewTrackerProposal(unittest.TestCase):

    def test_fires_on_new_tracker_proposal_without_anchor(self):
        result = check_plan_origination.check_po02(FIXTURE_2_TRIPS_PO02)
        self.assertIsNotNone(result, "PO-02 should fire on an uncited new-tracker proposal")

    def test_silent_on_clean_fixture(self):
        result = check_plan_origination.check_po02(FIXTURE_3_CLEAN_CITES_ANCHOR)
        self.assertIsNone(result)

    def test_silent_when_proposal_cites_anchor(self):
        text = FIXTURE_2_TRIPS_PO02 + "\nThis binds to MISSION_AUTHORITY.yaml, not a new file.\n"
        result = check_plan_origination.check_po02(text)
        self.assertIsNone(result)

    def test_silent_on_prose_with_no_tracker_proposal(self):
        text = "## Plan\n\nWe will build a new dashboard widget for the homepage.\n"
        result = check_plan_origination.check_po02(text)
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# scan_file / collect_files / run / CLI exit code
# ---------------------------------------------------------------------------

class TestScanAndRun(unittest.TestCase):

    def _write(self, tmp_dir: Path, name: str, text: str) -> str:
        path = tmp_dir / name
        path.write_text(text, encoding="utf-8")
        return str(path)

    def test_scan_file_reports_po01(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            path = self._write(Path(d), "plan.md", FIXTURE_1_TRIPS_PO01)
            findings = check_plan_origination.scan_file(path)
            rules = {f.rule for f in findings}
            self.assertIn("PO-01", rules)

    def test_scan_file_clean_plan_zero_findings(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            path = self._write(Path(d), "plan.md", FIXTURE_3_CLEAN_CITES_ANCHOR)
            findings = check_plan_origination.scan_file(path)
            self.assertEqual(findings, [])

    def test_scan_file_nonexistent_returns_read_error(self):
        findings = check_plan_origination.scan_file("/nonexistent/path/plan.md")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].rule, "READ_ERROR")

    def test_run_json_output_valid(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            path = self._write(Path(d), "plan.md", FIXTURE_2_TRIPS_PO02)
            output = check_plan_origination.run([path], as_json=True)
            data = json.loads(output)
            self.assertEqual(data["finding_count"], 1)
            self.assertEqual(data["findings"][0]["rule"], "PO-02")

    def test_has_findings_true_on_violation(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            path = self._write(Path(d), "plan.md", FIXTURE_1_TRIPS_PO01)
            self.assertTrue(check_plan_origination.has_findings([path]))

    def test_has_findings_false_on_clean_plan(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            path = self._write(Path(d), "plan.md", FIXTURE_3_CLEAN_CITES_ANCHOR)
            self.assertFalse(check_plan_origination.has_findings([path]))

    def test_main_exit_code_1_on_violation(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            path = self._write(Path(d), "plan.md", FIXTURE_1_TRIPS_PO01)
            exit_code = check_plan_origination.main([path])
            self.assertEqual(exit_code, 1)

    def test_main_exit_code_0_on_clean_plan(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            path = self._write(Path(d), "plan.md", FIXTURE_3_CLEAN_CITES_ANCHOR)
            exit_code = check_plan_origination.main([path])
            self.assertEqual(exit_code, 0)

    def test_main_exit_code_0_on_illustrative_example_with_anchor(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            path = self._write(Path(d), "plan.md", FIXTURE_4_ILLUSTRATIVE_EXAMPLE_WITH_ANCHOR)
            exit_code = check_plan_origination.main([path])
            self.assertEqual(exit_code, 0)


if __name__ == "__main__":
    unittest.main()
