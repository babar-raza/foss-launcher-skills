"""Tests for the evaluator freeze CI gate (C-24)."""
import pytest

# Import from the CI script — it uses a main() pattern for testability.
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "ci" / "checks"))
from check_evaluator_freeze import read_versions, check


# -- Fixture source texts ------------------------------------------------

_SRC_NO_FREEZE = '''\
EVALUATOR_LOGIC_VERSION = "16"
EVALUATOR_FREEZE_VERSION: str | None = None
'''

_SRC_MATCHING = '''\
EVALUATOR_LOGIC_VERSION = "16"
EVALUATOR_FREEZE_VERSION: str | None = "16"
'''

_SRC_MISMATCHED = '''\
EVALUATOR_LOGIC_VERSION = "17"
EVALUATOR_FREEZE_VERSION: str | None = "16"
'''

# PKGINSTALL-GRADE-SAFETY-OVERRIDE (2026-09-10): a trailing same-line comment
# on the EVALUATOR_FREEZE_VERSION assignment -- real, live shape (the actual
# committed content_eval/__init__.py has always carried one on this exact
# line, e.g. `= "18"  # TC-SFH-003: evidence_depth graduated to CANONICAL`).
# Confirmed this previously broke read_versions() for real: it returned
# freeze_version == '18"  # TC-SFH-003: evidence_depth graduated to
# CANONICAL' instead of '18', silently failing every comparison.
_SRC_TRAILING_COMMENT_MATCHING = '''\
EVALUATOR_LOGIC_VERSION = "18"
EVALUATOR_FREEZE_VERSION: str | None = "18"  # TC-SFH-003: evidence_depth graduated to CANONICAL
'''

_SRC_TRAILING_COMMENT_MISMATCHED = '''\
EVALUATOR_LOGIC_VERSION = "19"
EVALUATOR_FREEZE_VERSION: str | None = "18"  # TC-SFH-003: evidence_depth graduated to CANONICAL
'''


class TestReadVersions:
    def test_no_freeze(self):
        logic, freeze = read_versions(_SRC_NO_FREEZE)
        assert logic == "16"
        assert freeze is None

    def test_matching(self):
        logic, freeze = read_versions(_SRC_MATCHING)
        assert logic == "16"
        assert freeze == "16"

    def test_mismatched(self):
        logic, freeze = read_versions(_SRC_MISMATCHED)
        assert logic == "17"
        assert freeze == "16"

    def test_trailing_comment_does_not_leak_into_freeze_version(self):
        logic, freeze = read_versions(_SRC_TRAILING_COMMENT_MATCHING)
        assert logic == "18"
        assert freeze == "18", f"trailing comment leaked into parsed value: {freeze!r}"

    def test_trailing_comment_with_real_current_init_file(self):
        """End-to-end proof against the actual shipped
        content_eval/__init__.py, not just a synthetic reproduction."""
        init_path = (
            Path(__file__).resolve().parents[1] / "content_eval" / "__init__.py"
        )
        text = init_path.read_text(encoding="utf-8")
        logic, freeze = read_versions(text)
        assert freeze is None or '"' not in freeze, (
            f"a trailing comment leaked into the parsed freeze_version: {freeze!r}"
        )


class TestCheck:
    def test_no_freeze_passes(self):
        """When EVALUATOR_FREEZE_VERSION is None, the check passes (exit 0)."""
        assert check(_SRC_NO_FREEZE) == 0

    def test_matching_versions_passes(self):
        """When both versions match, the check passes (exit 0)."""
        assert check(_SRC_MATCHING) == 0

    def test_mismatched_versions_fails(self):
        """When versions diverge, the check fails (exit 1)."""
        assert check(_SRC_MISMATCHED) == 1

    def test_trailing_comment_matching_versions_passes(self):
        assert check(_SRC_TRAILING_COMMENT_MATCHING) == 0

    def test_trailing_comment_mismatched_versions_fails(self):
        assert check(_SRC_TRAILING_COMMENT_MISMATCHED) == 1

    def test_real_current_init_file_passes(self):
        """End-to-end proof: the actual shipped content_eval/__init__.py
        must pass this gate today (not merely a synthetic fixture)."""
        init_path = (
            Path(__file__).resolve().parents[1] / "content_eval" / "__init__.py"
        )
        text = init_path.read_text(encoding="utf-8")
        assert check(text) == 0
