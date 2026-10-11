"""Tests for lane_diff_checker.py (TC-LCM-04, TC-LCM-06)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PIPELINE_DIR = Path(__file__).resolve().parents[1]
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))

from commands.ops.lane_diff_checker import is_owned, is_shared, check_diff


class TestIsOwned:
    def test_exact_prefix_match(self):
        assert is_owned("content/docs.aspose.org/en/cells/java/foo.md", ["content/docs.aspose.org/en/cells/java/"])

    def test_no_match(self):
        assert not is_owned("scripts/pipeline/foo.py", ["content/"])

    def test_empty_prefixes_not_owned(self):
        assert not is_owned("content/foo.md", [])


class TestIsShared:
    def test_shared_file_detected(self):
        shared, pattern = is_shared("scripts/pipeline/config/registry.yaml")
        assert shared

    def test_non_shared_file(self):
        shared, _ = is_shared("content/docs.aspose.org/en/cells/java/foo.md")
        assert not shared


class TestCheckDiff:
    MANIFEST = {
        "lane_id": "L-TEST",
        "owned_path_prefixes": ["content/docs.aspose.org/en/cells/java/"],
        "shared_path_prefixes": [],
    }

    def test_all_owned_pass(self):
        result = check_diff(["content/docs.aspose.org/en/cells/java/foo.md"], self.MANIFEST)
        assert result["overall"] == "PASS"

    def test_out_of_scope_fail(self):
        result = check_diff(["content/docs.aspose.org/en/pdf/java/bar.md"], self.MANIFEST)
        assert result["overall"] == "FAIL"

    def test_empty_files_pass(self):
        result = check_diff([], self.MANIFEST)
        assert result["overall"] == "PASS"
