"""Tests for lane_rollback_plan.py (TC-LCM-09)."""
from __future__ import annotations

import sys
from pathlib import Path

_PIPELINE_DIR = Path(__file__).resolve().parents[1]
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))

from commands.ops.lane_rollback_plan import build_rollback_plan, topological_sort_reverse


class TestTopologicalSortReverse:
    def test_no_deps_any_order(self):
        m1 = {"lane_id": "L-A", "depends_on_lanes": [], "status": "CLOSED"}
        m2 = {"lane_id": "L-B", "depends_on_lanes": [], "status": "CLOSED"}
        sorted_m, errors = topological_sort_reverse([m1, m2])
        assert not errors
        assert len(sorted_m) == 2

    def test_empty_manifests(self):
        sorted_m, errors = topological_sort_reverse([])
        assert sorted_m == []
        assert errors == []


class TestBuildRollbackPlan:
    def test_single_manifest_no_sha(self):
        manifests = [{"lane_id": "L-A", "depends_on_lanes": [], "status": "CLOSED"}]
        result = build_rollback_plan(manifests)
        assert "plan_steps" in result
        assert result["overall"] in ("PASS", "WARN", "FAIL")

    def test_empty_manifests(self):
        result = build_rollback_plan([])
        assert result["overall"] in ("PASS", "WARN")
