"""test_backlink_merge_candidate_graphs.py — Tests for multi-subdomain candidate graph merge.

Tests cover:
- Basic merge: two input files combined into one output
- Source and candidate list accumulation
- decision_counts aggregation
- Missing input files: warning printed to stderr, skipped gracefully
- Schema markers: merged output has subdomain=MULTI_SUBDOMAIN_MERGED
- family field propagated correctly
- Stats computed from merged data

Run:
    python -m pytest scripts/pipeline/tests/test_backlink_merge_candidate_graphs.py -v
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT / "scripts" / "pipeline"))

from commands.ops.backlink_merge_candidate_graphs import merge


def _make_graph(
    tmp_path: Path,
    name: str,
    subdomain: str,
    family: str,
    sources: list,
    candidates: list,
) -> str:
    """Write a minimal candidate graph JSON file; return its path string."""
    data = {
        "schema_version": "1.0.0",
        "family": family,
        "subdomain": subdomain,
        "sources": sources,
        "candidates": candidates,
    }
    p = tmp_path / name
    p.write_text(json.dumps(data), encoding="utf-8")
    return str(p)


# ---------------------------------------------------------------------------
# Basic merge tests
# ---------------------------------------------------------------------------

class TestMergeBasic:
    def test_output_file_created(self, tmp_path):
        a = _make_graph(tmp_path, "a.json", "docs.aspose.org", "pdf", ["s1"], [])
        b = _make_graph(tmp_path, "b.json", "kb.aspose.org", "pdf", ["s2"], [])
        out = str(tmp_path / "merged.json")
        merge([a, b], out, "pdf")
        assert Path(out).exists()

    def test_sources_accumulated(self, tmp_path):
        a = _make_graph(tmp_path, "a.json", "docs.aspose.org", "pdf", ["s1", "s2"], [])
        b = _make_graph(tmp_path, "b.json", "kb.aspose.org", "pdf", ["s3"], [])
        out = str(tmp_path / "merged.json")
        result = merge([a, b], out, "pdf")
        assert len(result["sources"]) == 3

    def test_candidates_accumulated(self, tmp_path):
        c1 = {"source_key": "k1", "decision": "AUTO_APPROVE_EXACT"}
        c2 = {"source_key": "k2", "decision": "REVIEW_REQUIRED"}
        c3 = {"source_key": "k3", "decision": "AUTO_APPROVE_EXACT"}
        a = _make_graph(tmp_path, "a.json", "docs.aspose.org", "pdf", [], [c1, c2])
        b = _make_graph(tmp_path, "b.json", "kb.aspose.org", "pdf", [], [c3])
        out = str(tmp_path / "merged.json")
        result = merge([a, b], out, "pdf")
        assert len(result["candidates"]) == 3

    def test_family_set_correctly(self, tmp_path):
        a = _make_graph(tmp_path, "a.json", "docs.aspose.org", "cells", [], [])
        out = str(tmp_path / "merged.json")
        result = merge([a], out, "cells")
        assert result["family"] == "cells"

    def test_subdomain_marker_is_multi(self, tmp_path):
        a = _make_graph(tmp_path, "a.json", "docs.aspose.org", "pdf", [], [])
        out = str(tmp_path / "merged.json")
        result = merge([a], out, "pdf")
        assert result["subdomain"] == "MULTI_SUBDOMAIN_MERGED"

    def test_output_is_valid_json(self, tmp_path):
        a = _make_graph(tmp_path, "a.json", "docs.aspose.org", "pdf", ["s1"], [{"decision": "AUTO_APPROVE_EXACT"}])
        out = str(tmp_path / "merged.json")
        merge([a], out, "pdf")
        parsed = json.loads(Path(out).read_text(encoding="utf-8"))
        assert isinstance(parsed, dict)
        assert "candidates" in parsed
        assert "sources" in parsed


# ---------------------------------------------------------------------------
# decision_counts aggregation
# ---------------------------------------------------------------------------

class TestDecisionCounts:
    def test_counts_aggregated_across_inputs(self, tmp_path):
        ca1 = {"decision": "AUTO_APPROVE_EXACT"}
        ca2 = {"decision": "AUTO_APPROVE_EXACT"}
        cr1 = {"decision": "REVIEW_REQUIRED"}
        a = _make_graph(tmp_path, "a.json", "docs.aspose.org", "pdf", [], [ca1, ca2])
        b = _make_graph(tmp_path, "b.json", "kb.aspose.org", "pdf", [], [cr1])
        out = str(tmp_path / "merged.json")
        result = merge([a, b], out, "pdf")
        counts = result["stats"]["decision_counts"]
        assert counts.get("AUTO_APPROVE_EXACT") == 2
        assert counts.get("REVIEW_REQUIRED") == 1

    def test_total_candidates_in_stats(self, tmp_path):
        a = _make_graph(tmp_path, "a.json", "docs.aspose.org", "pdf", [], [{"decision": "X"}, {"decision": "X"}])
        b = _make_graph(tmp_path, "b.json", "kb.aspose.org", "pdf", [], [{"decision": "X"}])
        out = str(tmp_path / "merged.json")
        result = merge([a, b], out, "pdf")
        assert result["stats"]["total_candidates"] == 3

    def test_total_sources_in_stats(self, tmp_path):
        a = _make_graph(tmp_path, "a.json", "docs.aspose.org", "pdf", ["s1", "s2"], [])
        b = _make_graph(tmp_path, "b.json", "kb.aspose.org", "pdf", ["s3"], [])
        out = str(tmp_path / "merged.json")
        result = merge([a, b], out, "pdf")
        assert result["stats"]["total_sources"] == 3


# ---------------------------------------------------------------------------
# Missing file handling
# ---------------------------------------------------------------------------

class TestMissingFiles:
    def test_missing_file_skipped_no_crash(self, tmp_path):
        a = _make_graph(tmp_path, "a.json", "docs.aspose.org", "pdf", ["s1"], [])
        missing = str(tmp_path / "nonexistent.json")
        out = str(tmp_path / "merged.json")
        result = merge([a, missing], out, "pdf")
        assert result is not None

    def test_missing_file_does_not_reduce_valid_sources(self, tmp_path):
        a = _make_graph(tmp_path, "a.json", "docs.aspose.org", "pdf", ["s1", "s2"], [])
        missing = str(tmp_path / "nonexistent.json")
        out = str(tmp_path / "merged.json")
        result = merge([a, missing], out, "pdf")
        assert len(result["sources"]) == 2

    def test_missing_file_warning_goes_to_stderr(self, tmp_path, capsys):
        a = _make_graph(tmp_path, "a.json", "docs.aspose.org", "pdf", [], [])
        missing = str(tmp_path / "nonexistent.json")
        out = str(tmp_path / "merged.json")
        merge([a, missing], out, "pdf")
        captured = capsys.readouterr()
        assert "WARNING" in captured.err or "not found" in captured.err.lower()

    def test_all_missing_produces_empty_merge(self, tmp_path):
        out = str(tmp_path / "merged.json")
        result = merge([str(tmp_path / "x.json")], out, "pdf")
        assert result["stats"]["total_candidates"] == 0
        assert result["stats"]["total_sources"] == 0


# ---------------------------------------------------------------------------
# Output directory creation
# ---------------------------------------------------------------------------

class TestOutputDirectory:
    def test_nested_output_dir_created(self, tmp_path):
        a = _make_graph(tmp_path, "a.json", "docs.aspose.org", "pdf", [], [])
        out = str(tmp_path / "nested" / "deep" / "merged.json")
        merge([a], out, "pdf")
        assert Path(out).exists()
