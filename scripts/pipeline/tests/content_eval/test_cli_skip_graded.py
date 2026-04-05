"""Behavioral tests for the --skip-graded logic-version gate in cli._run_evaluate.

These tests prove that the skip decision behaves correctly for all logic-version
scenarios. They do NOT rely on code inspection; each test exercises the full
_run_evaluate path with controlled inputs and asserts on observable output.

Mocking pattern follows test_content_eval_output_root.py exactly.
"""

import argparse
import contextlib
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

from content_eval import cli, EVALUATOR_LOGIC_VERSION
from content_eval.cli import _run_evaluate


KNOWN_SHA = "aaabbbccc111222333444555666777888999000aaa"


class _StdoutCapture:
    def __init__(self):
        self.buffer = io.BytesIO()


class _NoopEvaluator:
    def evaluate(self, page, knowledge):
        return []


def _fake_page(name):
    """Create a minimal fake Page-like object for use as a test fixture."""
    return SimpleNamespace(
        filepath=Path(f"content/docs.aspose.org/en/slides/dotnet/{name}.md"),
        family="slides",
        platform="dotnet",
    )


def _full_grade(logic_version):
    """Return a stored grade dict simulating a page graded with tier=full."""
    return {
        "grade": "A",
        "model_sha": KNOWN_SHA,
        "tier": "full",
        "logic_version": logic_version,
    }


def _run_with_pages(pages, read_grade_fn, tmp_path, logic_version_override=None):
    """Run _run_evaluate with controlled inputs; return the write_grade mock.

    Args:
        pages: list of fake page SimpleNamespace objects
        read_grade_fn: callable(filepath) -> dict | None — controls stored grades
        tmp_path: Path to a temp directory for report output
        logic_version_override: if set, patches EVALUATOR_LOGIC_VERSION in cli module
    Returns:
        The mock object that replaced grade_writer.write_grade, enabling call assertions.
    """
    mock_knowledge = SimpleNamespace(repo_sha=KNOWN_SHA, available=True)
    stdout_capture = _StdoutCapture()
    args = argparse.Namespace(
        target=["all"],
        files=["dummy"],       # triggers load_files path; mocked below
        evaluators="structure",
        format="json",
        strict=False,
        dry_run=False,
        cross_page=False,
        remediation=False,
        output_root=str(tmp_path),
        write_grade=True,
        skip_graded=True,
        sweep=False,
    )

    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        patches = [
            mock.patch("content_eval.evaluators._ensure_loaded"),
            mock.patch("content_eval.evaluators.get_evaluator",
                       return_value=_NoopEvaluator),
            mock.patch("content_eval.loader.load_files", return_value=pages),
            mock.patch("content_eval.cli._load_knowledge",
                       return_value=mock_knowledge),
            mock.patch("grade_writer.read_grade", side_effect=read_grade_fn),
            mock.patch("content_eval.reporters.json_report.generate_json",
                       return_value="{}"),
            mock.patch.object(sys, "stdout", stdout_capture),
        ]
        write_grade_mock = mock.MagicMock()
        patches.append(mock.patch("grade_writer.write_grade", write_grade_mock))

        if logic_version_override is not None:
            patches.append(
                mock.patch("content_eval.cli.EVALUATOR_LOGIC_VERSION",
                           logic_version_override)
            )

        with contextlib.ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            _run_evaluate(args)
    finally:
        os.chdir(old_cwd)

    return write_grade_mock


class TestSkipGradedLogicVersion(unittest.TestCase):
    """Behavioral proof for the logic-version gate in --skip-graded."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.tmp_path = Path(self.tmp)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_skip_when_all_conditions_match(self):
        """A page is NOT re-graded when tier, sha, and logic_version all match.

        Behavioral proof: write_grade is not called for a page whose stored grade
        has tier=full, model_sha=KNOWN_SHA, and logic_version=EVALUATOR_LOGIC_VERSION.
        """
        page = _fake_page("skip_me")

        def read_grade_fn(fp):
            return _full_grade(EVALUATOR_LOGIC_VERSION)

        wg_mock = _run_with_pages([page], read_grade_fn, self.tmp_path)

        # write_grade must not be called for this page — it was skipped
        called_paths = [call.args[0] for call in wg_mock.call_args_list]
        self.assertNotIn(
            page.filepath, called_paths,
            f"write_grade should NOT be called for a page that matches all skip conditions; "
            f"was called for: {called_paths}"
        )

    def test_regraded_when_logic_version_missing(self):
        """A page IS re-graded when graded_logic_version is absent (stored as empty string).

        This covers the backward-compatibility case: pages graded before the logic-version
        field was introduced have logic_version="" in read_grade's return dict.
        """
        page = _fake_page("rgrade_missing")

        def read_grade_fn(fp):
            return _full_grade("")  # empty string = field absent

        wg_mock = _run_with_pages([page], read_grade_fn, self.tmp_path)

        called_paths = [call.args[0] for call in wg_mock.call_args_list]
        self.assertIn(
            page.filepath, called_paths,
            f"write_grade SHOULD be called for a page with missing logic_version; "
            f"was not in: {called_paths}"
        )

    def test_regraded_when_logic_version_old(self):
        """A page IS re-graded when graded_logic_version is present but stale.

        Covers the case of a page graded with a prior evaluator logic version (e.g., "0").
        """
        page = _fake_page("rgrade_old")

        stale_version = str(int(EVALUATOR_LOGIC_VERSION) - 1) if EVALUATOR_LOGIC_VERSION.isdigit() else "0"

        def read_grade_fn(fp):
            return _full_grade(stale_version)

        wg_mock = _run_with_pages([page], read_grade_fn, self.tmp_path)

        called_paths = [call.args[0] for call in wg_mock.call_args_list]
        self.assertIn(
            page.filepath, called_paths,
            f"write_grade SHOULD be called for a page with old logic_version={stale_version!r}; "
            f"was not in: {called_paths}"
        )

    def test_regraded_after_version_bump(self):
        """A page IS re-graded after EVALUATOR_LOGIC_VERSION is bumped, even if
        its stored logic_version previously matched.

        Simulates: page was graded with version "1", then EVALUATOR_LOGIC_VERSION
        is bumped to "2". On the next --skip-graded run, the page must be re-graded.
        """
        page = _fake_page("rgrade_bump")
        old_version = EVALUATOR_LOGIC_VERSION
        new_version = str(int(old_version) + 1) if old_version.isdigit() else "2"

        def read_grade_fn(fp):
            # Page was graded with old version — stored value matches what WAS current
            return _full_grade(old_version)

        # Simulate the bumped version by patching the constant in cli module
        wg_mock = _run_with_pages(
            [page], read_grade_fn, self.tmp_path,
            logic_version_override=new_version,
        )

        called_paths = [call.args[0] for call in wg_mock.call_args_list]
        self.assertIn(
            page.filepath, called_paths,
            f"write_grade SHOULD be called after version bump "
            f"({old_version!r} → {new_version!r}); was not in: {called_paths}"
        )

    def test_mixed_pages_only_unmatched_regraded(self):
        """Combined scenario: one page should skip, one should re-grade.

        Proves the filter operates per-page, not per-run: matched pages are skipped
        and unmatched pages are evaluated, within the same _run_evaluate call.
        """
        page_skip = _fake_page("should_skip")
        page_rgrade = _fake_page("should_rgrade")

        def read_grade_fn(fp):
            if fp == page_skip.filepath:
                return _full_grade(EVALUATOR_LOGIC_VERSION)  # current — skip
            return _full_grade("")                            # missing version — re-grade

        wg_mock = _run_with_pages(
            [page_skip, page_rgrade], read_grade_fn, self.tmp_path
        )

        called_paths = [call.args[0] for call in wg_mock.call_args_list]
        self.assertNotIn(
            page_skip.filepath, called_paths,
            f"write_grade must NOT be called for page_skip; got calls for: {called_paths}"
        )
        self.assertIn(
            page_rgrade.filepath, called_paths,
            f"write_grade MUST be called for page_rgrade; got calls for: {called_paths}"
        )


if __name__ == "__main__":
    unittest.main()
