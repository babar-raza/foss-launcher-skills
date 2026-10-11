"""Tests for HE-01 (feature_group propagation) and HE-02 (feature_group selection).

HE-01: build_handoff_manifest() must propagate feature_group, coverage_depth,
       uncovered_apis from candidate items to manifest items.
HE-02: select_candidate() must filter by feature_group to resolve ambiguity
       when multiple items share cluster+subdomain.
"""
from __future__ import annotations

import pytest
import sys
from pathlib import Path

_PIPELINE_ROOT = Path(__file__).resolve().parents[1]
_LIB_DIR = str(_PIPELINE_ROOT / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from enrichment.candidate_generator import build_handoff_manifest
from enrichment.manifest_consumer import select_candidate


# ---------------------------------------------------------------------------
# HE-01: feature_group propagation in build_handoff_manifest
# ---------------------------------------------------------------------------

def _make_decisions(items, disposition_key="update_existing"):
    """Build a minimal decisions dict for build_handoff_manifest."""
    return {
        "family": "font",
        "platform": "python",
        "generate_now": [],
        "update_existing": items if disposition_key == "update_existing" else [],
        "deferred": items if disposition_key == "deferred" else [],
        "rejected": [],
        "blocked": [],
    }


class TestHE01FeatureGroupPropagation:
    """HE-01: feature_group, coverage_depth, uncovered_apis must appear in manifest."""

    def test_feature_group_propagated(self):
        items = [
            {
                "action": "update_existing_docs_page",
                "cluster": "core-management",
                "subdomain": "docs.aspose.org",
                "score": 0.99,
                "feature_group": "variable-fonts",
                "coverage_depth": 0.125,
            },
        ]
        decisions = _make_decisions(items)
        manifest = build_handoff_manifest(decisions, "font", "python")
        assert len(manifest["manifest_items"]) == 1
        mi = manifest["manifest_items"][0]
        assert mi["feature_group"] == "variable-fonts"
        assert mi["coverage_depth"] == 0.125

    def test_uncovered_apis_propagated(self):
        items = [
            {
                "action": "update_existing_docs_page",
                "cluster": "core-management",
                "subdomain": "docs.aspose.org",
                "score": 0.99,
                "feature_group": "variable-fonts",
                "uncovered_apis": ["VariableAxis", "SmartInstancer"],
            },
        ]
        decisions = _make_decisions(items)
        manifest = build_handoff_manifest(decisions, "font", "python")
        mi = manifest["manifest_items"][0]
        assert mi["uncovered_apis"] == ["VariableAxis", "SmartInstancer"]

    def test_missing_feature_group_omitted(self):
        """Items without feature_group should not have the key in manifest."""
        items = [
            {
                "action": "update_existing_docs_page",
                "cluster": "tables",
                "subdomain": "docs.aspose.org",
                "score": 0.85,
            },
        ]
        decisions = _make_decisions(items)
        manifest = build_handoff_manifest(decisions, "font", "python")
        mi = manifest["manifest_items"][0]
        assert "feature_group" not in mi

    def test_multiple_feature_groups_preserved(self):
        items = [
            {
                "action": "update_existing_docs_page",
                "cluster": "core-management",
                "subdomain": "docs.aspose.org",
                "score": 0.99,
                "feature_group": "variable-fonts",
                "coverage_depth": 0.125,
            },
            {
                "action": "update_existing_docs_page",
                "cluster": "core-management",
                "subdomain": "docs.aspose.org",
                "score": 0.99,
                "feature_group": "preview",
                "coverage_depth": 0.125,
            },
        ]
        decisions = _make_decisions(items)
        manifest = build_handoff_manifest(decisions, "font", "python")
        fgs = [m["feature_group"] for m in manifest["manifest_items"]]
        assert fgs == ["variable-fonts", "preview"]


# ---------------------------------------------------------------------------
# HE-02: feature_group selection in select_candidate
# ---------------------------------------------------------------------------

def _make_manifest_with_feature_groups():
    """7 items sharing cluster+subdomain, differing only by feature_group."""
    feature_groups = [
        "animation", "cli", "mcp-server", "preview",
        "qa-compatibility", "variable-fonts", "web-packaging",
    ]
    items = []
    for fg in feature_groups:
        items.append({
            "action": "update_existing_docs_page",
            "cluster": "core-management",
            "subdomain": "docs.aspose.org",
            "score": 0.99,
            "feature_group": fg,
            "coverage_depth": 0.125,
            "target_skill": "S-20",
            "dry_run": False,
        })
    return {"manifest_items": items, "backlog_items": [], "total_manifest": len(items)}


class TestHE02FeatureGroupSelection:
    """HE-02: select_candidate must disambiguate by feature_group."""

    def test_select_by_feature_group(self):
        manifest = _make_manifest_with_feature_groups()
        result = select_candidate(
            manifest, cluster="core-management",
            subdomain="docs.aspose.org", feature_group="variable-fonts",
        )
        assert result["feature_group"] == "variable-fonts"

    def test_ambiguous_without_feature_group(self):
        manifest = _make_manifest_with_feature_groups()
        with pytest.raises(ValueError, match="ambiguous"):
            select_candidate(
                manifest, cluster="core-management",
                subdomain="docs.aspose.org",
            )

    def test_select_each_feature_group(self):
        manifest = _make_manifest_with_feature_groups()
        for item in manifest["manifest_items"]:
            fg = item["feature_group"]
            result = select_candidate(
                manifest, cluster="core-management",
                subdomain="docs.aspose.org", feature_group=fg,
            )
            assert result["feature_group"] == fg

    def test_nonexistent_feature_group_raises(self):
        manifest = _make_manifest_with_feature_groups()
        with pytest.raises(ValueError, match="No items match"):
            select_candidate(
                manifest, cluster="core-management",
                subdomain="docs.aspose.org", feature_group="nonexistent",
            )

    def test_subdomain_only_with_feature_group(self):
        manifest = _make_manifest_with_feature_groups()
        result = select_candidate(
            manifest, subdomain="docs.aspose.org", feature_group="preview",
        )
        assert result["feature_group"] == "preview"

    def test_index_ignores_feature_group(self):
        manifest = _make_manifest_with_feature_groups()
        result = select_candidate(manifest, index=3)
        assert result["feature_group"] == "preview"  # 4th item

    def test_single_match_no_feature_group_needed(self):
        """If cluster+subdomain is already unique, feature_group is optional."""
        manifest = {
            "manifest_items": [{
                "action": "update_existing_docs_page",
                "cluster": "tables",
                "subdomain": "docs.aspose.org",
                "score": 0.85,
                "target_skill": "S-20",
                "dry_run": False,
            }],
        }
        result = select_candidate(manifest, cluster="tables")
        assert result["cluster"] == "tables"


# ---------------------------------------------------------------------------
# HE-02: list_candidates shows feature_group column
# ---------------------------------------------------------------------------

from enrichment.manifest_consumer import list_candidates


class TestListCandidatesFeatureGroup:
    def test_feature_group_in_header(self):
        manifest = _make_manifest_with_feature_groups()
        output = list_candidates(manifest)
        assert "Feature Group" in output

    def test_feature_group_values_in_output(self):
        manifest = _make_manifest_with_feature_groups()
        output = list_candidates(manifest)
        assert "variable-fonts" in output
        assert "preview" in output
