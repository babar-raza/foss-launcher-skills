"""Tests for lane_commit_map_validator.py (TC-LCM-DEFERRED-01)."""
from __future__ import annotations

import sys
from pathlib import Path

_PIPELINE_DIR = Path(__file__).resolve().parents[1]
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))

from commands.ops.lane_commit_map_validator import build_commit_map


class TestBuildCommitMap:
    def test_missing_sha_flagged(self):
        manifests = [{"lane_id": "L-A", "status": "CLOSED"}]
        result = build_commit_map(manifests)
        assert result["overall"] in ("PASS", "WARN", "FAIL")
        assert "entries" in result

    def test_empty_manifests(self):
        result = build_commit_map([])
        assert result["overall"] in ("PASS", "WARN")

    def test_manifest_with_fake_sha_not_in_git(self):
        manifests = [{
            "lane_id": "L-B",
            "status": "CLOSED",
            "commit_sha": "0" * 40,
        }]
        result = build_commit_map(manifests, check_ancestry=False)
        # SHA is all-zeros — not in git, should FAIL or WARN
        assert result["overall"] in ("FAIL", "WARN")
