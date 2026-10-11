"""Tests for lane_staging_checker.py (TC-LCM-05)."""
from __future__ import annotations

import sys
from pathlib import Path

_PIPELINE_DIR = Path(__file__).resolve().parents[1]
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))

from commands.ops.lane_staging_checker import is_owned, check_staged


class TestIsOwned:
    def test_prefix_match(self):
        assert is_owned("content/docs.aspose.org/en/cells/java/foo.md", ["content/docs.aspose.org/en/cells/java/"])

    def test_no_prefix_match(self):
        assert not is_owned("scripts/pipeline/foo.py", ["content/"])


class TestCheckStaged:
    MANIFEST = {
        "lane_id": "L-TEST",
        "owned_path_prefixes": ["content/docs.aspose.org/en/cells/java/"],
    }

    def test_owned_staged_pass(self):
        result = check_staged(["content/docs.aspose.org/en/cells/java/foo.md"], self.MANIFEST)
        assert result["overall"] == "PASS"

    def test_unowned_staged_fail(self):
        result = check_staged(["content/docs.aspose.org/en/pdf/java/bar.md"], self.MANIFEST)
        assert result["overall"] == "FAIL"

    def test_empty_staged_pass(self):
        result = check_staged([], self.MANIFEST)
        assert result["overall"] == "PASS"
