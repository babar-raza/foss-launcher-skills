import argparse
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


_PIPELINE_ROOT = Path(__file__).resolve().parents[1]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

import remediate


class _StdoutCapture:
    def __init__(self):
        self.buffer = io.BytesIO()


class RemediateOutputRootTests(unittest.TestCase):
    def test_fix_writes_reports_under_output_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            output_root = temp_path / "isolated"
            eval_report = temp_path / "eval.json"
            eval_report.write_text('{"findings": []}', encoding="utf-8")
            triage = SimpleNamespace(
                summary={"auto_fixable": 0, "llm_needed": 0, "human_needed": 0, "skipped": 0},
                total=0,
                auto_fixable=[],
                llm_needed=[],
                human_needed=[],
                skipped=[],
            )
            args = argparse.Namespace(
                eval_report=str(eval_report),
                dry_run=True,
                categories=None,
                output_root=str(output_root),
            )
            stdout = _StdoutCapture()
            old_cwd = os.getcwd()
            os.chdir(temp_path)
            try:
                with mock.patch.object(remediate, "triage_findings", return_value=triage), \
                        mock.patch.object(remediate, "run_fixes", return_value=[]), \
                        mock.patch.object(sys, "stdout", stdout):
                    remediate._cmd_fix(args)
            finally:
                os.chdir(old_cwd)

            isolated_reports = list((output_root / "remediation").glob("rem-*.*"))
            default_reports = temp_path / "reports" / "remediation"
            self.assertEqual(len(isolated_reports), 2)
            self.assertFalse(default_reports.exists())


if __name__ == "__main__":
    unittest.main()
