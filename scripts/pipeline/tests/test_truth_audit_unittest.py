from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


PIPELINE_DIR = Path(__file__).resolve().parent.parent
if str(PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINE_DIR))

import truth_audit  # noqa: E402


class _Finding:
    def __init__(self, level: str):
        self.level = level


class TruthAuditTests(unittest.TestCase):
    def test_run_truth_audit_json_uses_audit_runner(self):
        with patch("truth_audit.audit_product", return_value=[_Finding("FAIL"), _Finding("WARN")]), \
             patch("truth_audit.report_json", return_value='{"ok": false}') as report_json, \
             patch("lib.knowledge_state.record_truth_audit") as record_truth_audit:
            output, exit_code = truth_audit.run_truth_audit("slides", "python", json_mode=True)

        self.assertEqual(output, '{"ok": false}')
        self.assertEqual(exit_code, 1)
        report_json.assert_called_once()
        record_truth_audit.assert_called_once()
        _, kwargs = record_truth_audit.call_args
        self.assertEqual(kwargs["fail_count"], 1)
        self.assertEqual(kwargs["warn_count"], 1)

    def test_run_truth_audit_knowledge_state_failure_is_non_fatal(self):
        """A knowledge_state write failure must not break the audit itself."""
        with patch("truth_audit.audit_product", return_value=[]), \
             patch("truth_audit.report_json", return_value='{"ok": true}'), \
             patch("lib.knowledge_state.record_truth_audit", side_effect=RuntimeError("boom")):
            output, exit_code = truth_audit.run_truth_audit("slides", "python", json_mode=True)

        self.assertEqual(output, '{"ok": true}')
        self.assertEqual(exit_code, 0)

    def test_main_writes_default_report(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "truth_audit.run_truth_audit",
            return_value=("# ok", 0),
        ):
            cwd = Path.cwd()
            try:
                import os
                os.chdir(temp_dir)
                exit_code = truth_audit.main(["slides", "python"])
                report_path = Path("reports") / "audit"
                report_files = [path.resolve() for path in report_path.glob("slides-python-truth-*.md")]
                report_text = report_files[0].read_text(encoding="utf-8") if report_files else ""
            finally:
                os.chdir(cwd)

        self.assertEqual(exit_code, 0)
        self.assertEqual(len(report_files), 1)
        self.assertEqual(report_text, "# ok")


if __name__ == "__main__":
    unittest.main()
