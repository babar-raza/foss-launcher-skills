"""Tests for the evaluator freeze CI gate (C-24)."""
import pytest

# Import from the CI script — it uses a main() pattern for testability.
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "ci"))
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
