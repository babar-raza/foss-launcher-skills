"""End-to-end tests for site_planner.py --mode update (TEST-02).

Tests the delta logic in build_plan() directly (no subprocess needed since
there is no --output-dir CLI flag).  Uses real 3d/python knowledge artifacts
which are guaranteed to exist in the repo (launch is complete for 3d/python).
"""
from __future__ import annotations

import copy
from pathlib import Path

import pytest

import site_planner as sp

from _repo_root import repo_root

REPO_ROOT = repo_root()
KNOWLEDGE_3D_PY = REPO_ROOT / "knowledge" / "3d" / "python" / "merged"


# ---------------------------------------------------------------------------
# Skip guard — skip entire module if 3d/python knowledge is unavailable
# ---------------------------------------------------------------------------

pytestmark = pytest.mark.skipif(
    not KNOWLEDGE_3D_PY.exists(),
    reason="knowledge/3d/python/merged not found — skipping update-mode tests",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_launch_plan():
    """Build a fresh launch plan for 3d/python (no existing plan)."""
    plan, clusters, excluded = sp.build_plan("3d", "python", "launch", None, None)
    return plan, clusters, excluded


def _all_paths(plan: dict) -> set[str]:
    paths = set()
    for sec_data in plan.get("sections", {}).values():
        for p in sec_data.get("pages", []):
            paths.add(p.get("path", ""))
    return paths


# ---------------------------------------------------------------------------
# TEST-02-A: No existing plan → update behaves like launch (plan_version=1)
# ---------------------------------------------------------------------------

def test_update_no_existing_plan():
    """When existing_plan is None, mode=update returns a fresh plan (version 1)."""
    plan, _, _ = sp.build_plan("3d", "python", "update", None, None)
    assert plan["plan_version"] == 1
    # No delta section when existing_plan is None
    assert "delta" in plan  # delta key exists
    assert plan["delta"]["pages_to_add"] == []
    assert plan["delta"]["pages_to_remove"] == []


# ---------------------------------------------------------------------------
# TEST-02-B: Existing plan with same SHA → no delta (no pages to add/remove)
# ---------------------------------------------------------------------------

def test_update_sha_unchanged():
    """When existing plan has same repo_sha as current knowledge, delta is empty."""
    # Get current plan
    launch_plan, _, _ = _build_launch_plan()
    # Wrap in the new schema format
    existing = {"plan": launch_plan}

    # Rebuild with mode=update and same plan as existing
    plan, _, _ = sp.build_plan("3d", "python", "update", None, existing)

    assert plan["plan_version"] == 2  # incremented from 1
    # Pages should be identical → no add or remove
    assert plan["delta"]["pages_to_add"] == [], (
        f"Expected no pages_to_add but got: {plan['delta']['pages_to_add']}"
    )
    assert plan["delta"]["pages_to_remove"] == [], (
        f"Expected no pages_to_remove but got: {plan['delta']['pages_to_remove']}"
    )


# ---------------------------------------------------------------------------
# TEST-02-C: Existing plan with different SHA → pages_to_update is non-empty
# ---------------------------------------------------------------------------

def test_update_sha_changed():
    """When existing plan has a different repo_sha, retained pages appear in pages_to_update."""
    launch_plan, _, _ = _build_launch_plan()
    old_plan = copy.deepcopy(launch_plan)
    old_plan["repo_sha"] = "000000000000000000000000000000000000dead"
    existing = {"plan": old_plan}

    plan, _, _ = sp.build_plan("3d", "python", "update", None, existing)

    assert plan["plan_version"] == 2
    # pages_to_update should be non-empty (all retained pages marked updated)
    assert len(plan["delta"]["pages_to_update"]) > 0, (
        "Expected pages_to_update to be non-empty when SHA changed"
    )


# ---------------------------------------------------------------------------
# TEST-02-D: Delta detects a removed page
# ---------------------------------------------------------------------------

def test_update_detects_removed_page():
    """If a page exists in old plan but not in new, it appears in pages_to_remove."""
    launch_plan, _, _ = _build_launch_plan()
    old_plan = copy.deepcopy(launch_plan)

    # Inject a fake page into the old plan that won't exist in the fresh plan
    old_plan.setdefault("sections", {}).setdefault("docs", {}).setdefault("pages", []).append({
        "slug": "developer-guide/fake-obsolete-page",
        "path": "content/docs.aspose.org/en/3d/python/developer-guide/fake-obsolete-page.md",
        "type": "docs",
        "mandatory": False,
    })
    existing = {"plan": old_plan}

    plan, _, _ = sp.build_plan("3d", "python", "update", None, existing)

    assert (
        "content/docs.aspose.org/en/3d/python/developer-guide/fake-obsolete-page.md"
        in plan["delta"]["pages_to_remove"]
    ), f"Fake page not in pages_to_remove: {plan['delta']['pages_to_remove']}"


# ---------------------------------------------------------------------------
# TEST-02-E: Delta output is valid (parseable structure)
# ---------------------------------------------------------------------------

def test_update_delta_structure():
    """Delta keys must be present and contain lists of path strings."""
    launch_plan, _, _ = _build_launch_plan()
    existing = {"plan": launch_plan}
    plan, _, _ = sp.build_plan("3d", "python", "update", None, existing)

    delta = plan.get("delta", {})
    assert "pages_to_add" in delta
    assert "pages_to_update" in delta
    assert "pages_to_remove" in delta
    assert isinstance(delta["pages_to_add"], list)
    assert isinstance(delta["pages_to_update"], list)
    assert isinstance(delta["pages_to_remove"], list)
    # All items in each list must be strings
    for key in ("pages_to_add", "pages_to_update", "pages_to_remove"):
        for item in delta[key]:
            assert isinstance(item, str), f"{key} contains non-string: {item!r}"


# ---------------------------------------------------------------------------
# TEST-02-F: Legacy flat existing plan (backward compat)
# ---------------------------------------------------------------------------

def test_update_flat_existing_plan():
    """update mode accepts a legacy flat (non-wrapped) existing plan without crashing."""
    launch_plan, _, _ = _build_launch_plan()
    # Pass flat (non-wrapped) — old format before PATCH-03
    existing = launch_plan  # flat, no "plan" wrapper

    plan, _, _ = sp.build_plan("3d", "python", "update", None, existing)
    assert "delta" in plan
    assert isinstance(plan["delta"]["pages_to_add"], list)
