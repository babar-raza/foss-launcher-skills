import argparse
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

from content_eval import cli


class _StdoutCapture:
    def __init__(self):
        self.buffer = io.BytesIO()


class _NoopEvaluator:
    def evaluate(self, page, knowledge):
        return []


class ContentEvalOutputRootTests(unittest.TestCase):
    def test_evaluate_writes_under_output_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            output_root = temp_path / "isolated"
            fake_page = SimpleNamespace(
                filepath=Path("content/docs.aspose.org/en/slides/python/demo.md"),
                family="slides",
                platform="python",
            )
            args = argparse.Namespace(
                target=["slides", "python"],
                files=None,
                evaluators=None,
                format="markdown",
                strict=False,
                dry_run=False,
                cross_page=False,
                remediation=False,
                output_root=str(output_root),
                write_grade=False,
                skip_graded=False,
                sweep=False,
            )
            stdout = _StdoutCapture()
            old_cwd = os.getcwd()
            os.chdir(temp_path)
            try:
                with mock.patch("content_eval.evaluators._ensure_loaded"), \
                        mock.patch("content_eval.evaluators.get_evaluator", return_value=_NoopEvaluator), \
                        mock.patch("content_eval.loader.load_pages", return_value=[fake_page]), \
                        mock.patch("content_eval.cli._load_knowledge", return_value=None), \
                        mock.patch("content_eval.reporters.markdown.generate_markdown", return_value="# ok"), \
                        mock.patch("core.prereqs.require_all"), \
                        mock.patch.object(sys, "stdout", stdout):
                    cli._run_evaluate(args)
            finally:
                os.chdir(old_cwd)

            isolated_reports = list((output_root / "content_eval").glob("eval-*.md"))
            default_reports = temp_path / "reports" / "content_eval"
            self.assertEqual(len(isolated_reports), 1)
            self.assertFalse(default_reports.exists())


if __name__ == "__main__":
    unittest.main()
