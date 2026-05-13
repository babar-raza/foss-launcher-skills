"""Tests for launch gates L-01 through L-07.

TC-05a: Provides regression protection for gates that previously had
zero test coverage.
"""
from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest
import yaml

import launch_gate as lg
from launch_gate import (
    STATUS_FAIL,
    STATUS_PASS,
    STATUS_SKIP,
    STATUS_WARN,
    gate_l01_knowledge_freshness,
    gate_l02_evidence_coverage,
    gate_l03_forbidden_claims,
    gate_l04_api_accuracy,
    gate_l05_format_truth,
    gate_l06_promote_validation,
    gate_l07_pipeline_tests,
    gate_l12_denominator_reconciliation,
    gate_l14_grade_non_regression,
    gate_l15_snippet_syntax,
)


@pytest.fixture(autouse=True)
def _isolate_gate_paths(tmp_path):
    """Point launch_gate module globals at tmp_path for isolation."""
    saved = (lg._REPO_ROOT, lg._KNOWLEDGE_ROOT, lg._CONTENT_ROOT, lg._SCRIPTS_PIPELINE)
    lg.configure(repo_root=tmp_path)
    lg._KNOWLEDGE_ROOT = tmp_path / "knowledge"
    lg._CONTENT_ROOT = tmp_path / "content"
    lg._SCRIPTS_PIPELINE = tmp_path / "scripts" / "pipeline"
    yield
    lg._REPO_ROOT, lg._KNOWLEDGE_ROOT, lg._CONTENT_ROOT, lg._SCRIPTS_PIPELINE = saved


def _make_merged(tmp_path, family="test", platform="python"):
    """Create knowledge/{family}/{platform}/merged/ dir and return it."""
    merged = tmp_path / "knowledge" / family / platform / "merged"
    merged.mkdir(parents=True, exist_ok=True)
    return merged


def _write_model(merged, stale_since=None, extra=None):
    """Write a model.yaml into merged dir."""
    data = {
        "family": "test",
        "platform": "python",
        "version": "1.0.0",
        "repo_sha": "abc123",
        "stale_since": stale_since,
    }
    if extra:
        data.update(extra)
    (merged / "model.yaml").write_text(
        yaml.dump(data, default_flow_style=False), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# L-01: Knowledge freshness
# ---------------------------------------------------------------------------

class TestGateL01KnowledgeFreshness:
    """L-01: model.yaml stale_since must be null."""

    def test_pass_when_stale_since_null(self, tmp_path):
        merged = _make_merged(tmp_path)
        _write_model(merged, stale_since=None)
        result = gate_l01_knowledge_freshness("test", "python")
        assert result.status == STATUS_PASS
        assert result.gate_id == "L-01"

    def test_fail_when_stale_since_set(self, tmp_path):
        merged = _make_merged(tmp_path)
        _write_model(merged, stale_since="2026-01-01")
        result = gate_l01_knowledge_freshness("test", "python")
        assert result.status == STATUS_FAIL
        assert "2026-01-01" in result.detail

    def test_fail_when_model_yaml_missing(self, tmp_path):
        _make_merged(tmp_path)  # dir exists but no model.yaml
        result = gate_l01_knowledge_freshness("test", "python")
        assert result.status == STATUS_FAIL
        assert "not found" in result.detail

    def test_fail_when_model_yaml_unparseable(self, tmp_path):
        merged = _make_merged(tmp_path)
        (merged / "model.yaml").write_text(": invalid: yaml: [", encoding="utf-8")
        result = gate_l01_knowledge_freshness("test", "python")
        assert result.status == STATUS_FAIL
        assert "parse error" in result.detail


# ---------------------------------------------------------------------------
# L-02: Evidence coverage
# ---------------------------------------------------------------------------

class TestGateL02EvidenceCoverage:
    """L-02: all content files must have evidence: block."""

    def _make_content(self, tmp_path, family="test", platform="python"):
        d = tmp_path / "content" / "reference.aspose.org" / "en" / family / platform
        d.mkdir(parents=True, exist_ok=True)
        return d

    def test_skip_when_no_content_files(self, tmp_path):
        result = gate_l02_evidence_coverage("test", "python")
        assert result.status == STATUS_SKIP

    def test_pass_when_all_files_have_evidence(self, tmp_path):
        d = self._make_content(tmp_path)
        (d / "Font.md").write_text(
            "---\ntitle: Font\nevidence:\n  model_sha: abc\n---\nContent\n",
            encoding="utf-8",
        )
        result = gate_l02_evidence_coverage("test", "python")
        assert result.status == STATUS_PASS
        assert "1/1" in result.detail

    def test_fail_when_file_missing_evidence(self, tmp_path):
        d = self._make_content(tmp_path)
        (d / "Good.md").write_text(
            "---\ntitle: Good\nevidence:\n  model_sha: abc\n---\n",
            encoding="utf-8",
        )
        (d / "Bad.md").write_text(
            "---\ntitle: Bad\n---\nNo evidence here\n",
            encoding="utf-8",
        )
        result = gate_l02_evidence_coverage("test", "python")
        assert result.status == STATUS_FAIL
        assert "1/2" in result.detail

    def test_fail_when_no_frontmatter(self, tmp_path):
        d = self._make_content(tmp_path)
        (d / "NoFM.md").write_text("Just plain text\n", encoding="utf-8")
        result = gate_l02_evidence_coverage("test", "python")
        assert result.status == STATUS_FAIL


# ---------------------------------------------------------------------------
# L-03: Forbidden claims (subprocess — test SKIP paths)
# ---------------------------------------------------------------------------

class TestGateL03ForbiddenClaims:
    """L-03: Tests SKIP paths (subprocess not invoked in test)."""

    def test_skip_when_no_merged_dir(self, tmp_path):
        result = gate_l03_forbidden_claims("test", "python")
        assert result.status == STATUS_SKIP
        assert "no merged knowledge" in result.detail

    def test_skip_when_no_claims_json(self, tmp_path):
        merged = _make_merged(tmp_path)
        result = gate_l03_forbidden_claims("test", "python")
        assert result.status == STATUS_SKIP
        assert "no merged/claims.json" in result.detail

    def test_skip_when_claims_empty(self, tmp_path):
        merged = _make_merged(tmp_path)
        (merged / "claims.json").write_text("[]", encoding="utf-8")
        result = gate_l03_forbidden_claims("test", "python")
        assert result.status == STATUS_SKIP
        assert "no claim text" in result.detail


# ---------------------------------------------------------------------------
# L-04: API accuracy (subprocess — test behavior indirectly)
# ---------------------------------------------------------------------------

class TestGateL04ApiAccuracy:
    """L-04: Since this runs a subprocess, test that it handles missing script."""

    def test_fail_when_audit_script_missing(self, tmp_path):
        """audit.py doesn't exist at tmp_path — subprocess will fail."""
        result = gate_l04_api_accuracy("test", "python")
        assert result.status == STATUS_FAIL


# ---------------------------------------------------------------------------
# L-05: Format truth (subprocess)
# ---------------------------------------------------------------------------

class TestGateL05FormatTruth:
    """L-05: Tests subprocess failure path."""

    def test_fail_when_content_eval_unavailable(self, tmp_path):
        """content_eval module not available from tmp_path — subprocess will fail."""
        result = gate_l05_format_truth("test", "python")
        assert result.status == STATUS_FAIL


# ---------------------------------------------------------------------------
# L-06: Promote validation
# ---------------------------------------------------------------------------

class TestGateL06PromoteValidation:
    """L-06: formats.json + model.yaml existence + stale_since check."""

    def test_fail_when_no_merged_artifacts(self, tmp_path):
        _make_merged(tmp_path)  # empty dir
        result = gate_l06_promote_validation("test", "python")
        assert result.status == STATUS_FAIL
        assert "missing merged artifacts" in result.detail

    def test_fail_when_only_model_yaml(self, tmp_path):
        merged = _make_merged(tmp_path)
        _write_model(merged)
        result = gate_l06_promote_validation("test", "python")
        assert result.status == STATUS_FAIL
        assert "formats.json" in result.detail

    def test_fail_when_stale(self, tmp_path):
        merged = _make_merged(tmp_path)
        _write_model(merged, stale_since="2026-01-01")
        (merged / "formats.json").write_text('{"formats": []}', encoding="utf-8")
        result = gate_l06_promote_validation("test", "python")
        assert result.status == STATUS_FAIL
        assert "stale_since" in result.detail

    def test_skip_when_all_present_and_fresh(self, tmp_path):
        """L-06 returns SKIP (not PASS) because promote --dry-run is unavailable."""
        merged = _make_merged(tmp_path)
        _write_model(merged, stale_since=None)
        (merged / "formats.json").write_text('{"formats": []}', encoding="utf-8")
        result = gate_l06_promote_validation("test", "python")
        assert result.status == STATUS_SKIP
        assert "dry-run not available" in result.detail


# ---------------------------------------------------------------------------
# L-07: Pipeline tests (subprocess)
# ---------------------------------------------------------------------------

class TestGateL07PipelineTests:
    """L-07: pytest subprocess — test SKIP path."""

    def test_skip_when_no_test_dir(self, tmp_path):
        """No scripts/pipeline/tests/ at tmp_path -> SKIP."""
        result = gate_l07_pipeline_tests("test", "python")
        assert result.status == STATUS_SKIP
        assert "no test directories" in result.detail


# ---------------------------------------------------------------------------
# L-12: Denominator reconciliation
# ---------------------------------------------------------------------------

class TestGateL12DenominatorReconciliation:
    """L-12: generation manifest denominator gap must be 0."""

    def test_pass_with_manifest_gap_zero(self, tmp_path):
        manifest_dir = tmp_path / "reports" / "generation"
        manifest_dir.mkdir(parents=True)
        (manifest_dir / "test-python.yaml").write_text(
            "denominator_gap: 0\nscope_eligible: 10\n", encoding="utf-8"
        )
        result = gate_l12_denominator_reconciliation("test", "python")
        assert result.status == STATUS_PASS

    def test_warn_with_small_gap(self, tmp_path):
        manifest_dir = tmp_path / "reports" / "generation"
        manifest_dir.mkdir(parents=True)
        (manifest_dir / "test-python.yaml").write_text(
            "denominator_gap: 3\nscope_eligible: 100\n", encoding="utf-8"
        )
        result = gate_l12_denominator_reconciliation("test", "python")
        assert result.status == STATUS_WARN

    def test_fail_with_large_gap(self, tmp_path):
        manifest_dir = tmp_path / "reports" / "generation"
        manifest_dir.mkdir(parents=True)
        (manifest_dir / "test-python.yaml").write_text(
            "denominator_gap: 10\nscope_eligible: 100\n", encoding="utf-8"
        )
        result = gate_l12_denominator_reconciliation("test", "python")
        assert result.status == STATUS_FAIL

    def test_skip_when_no_manifest_and_no_knowledge(self, tmp_path):
        """No manifest + no knowledge = reconciler SKIP."""
        result = gate_l12_denominator_reconciliation("test", "python")
        assert result.status == STATUS_SKIP


# ---------------------------------------------------------------------------
# L-14: Grade non-regression
# ---------------------------------------------------------------------------

class TestGateL14GradeNonRegression:
    """L-14: grade manifest comparison."""

    def test_skip_when_no_manifest(self, tmp_path):
        result = gate_l14_grade_non_regression("test", "python")
        assert result.status == STATUS_SKIP

    def test_skip_when_no_relevant_pages(self, tmp_path):
        report_dir = tmp_path / "reports"
        report_dir.mkdir(parents=True)
        (report_dir / "grade_manifest.json").write_text(
            '[{"path": "content/reference.aspose.org/en/other/java/Foo.md", "grade": "A"}]',
            encoding="utf-8",
        )
        result = gate_l14_grade_non_regression("test", "python")
        assert result.status == STATUS_SKIP

    def test_pass_with_graded_pages(self, tmp_path):
        report_dir = tmp_path / "reports"
        report_dir.mkdir(parents=True)
        (report_dir / "grade_manifest.json").write_text(
            '[{"path": "content/reference.aspose.org/en/test/python/Font.md", "grade": "A"},'
            ' {"path": "content/reference.aspose.org/en/test/python/Glyph.md", "grade": "C"}]',
            encoding="utf-8",
        )
        result = gate_l14_grade_non_regression("test", "python")
        assert result.status == STATUS_PASS
        assert "2 pages graded" in result.detail


# ---------------------------------------------------------------------------
# L-15: Snippet syntax
# ---------------------------------------------------------------------------

class TestGateL15SnippetSyntax:
    """L-15: snippet syntax validation."""

    def test_skip_when_no_snippets_dir(self, tmp_path):
        result = gate_l15_snippet_syntax("test", "python")
        assert result.status == STATUS_SKIP

    def test_pass_with_valid_snippets(self, tmp_path):
        snippets = tmp_path / "knowledge" / "test" / "python" / "merged" / "snippets"
        snippets.mkdir(parents=True)
        (snippets / "example.py").write_text(
            "def hello():\n    print('hello')\n", encoding="utf-8"
        )
        result = gate_l15_snippet_syntax("test", "python")
        assert result.status == STATUS_PASS

    def test_warn_with_empty_snippet(self, tmp_path):
        snippets = tmp_path / "knowledge" / "test" / "python" / "merged" / "snippets"
        snippets.mkdir(parents=True)
        (snippets / "empty.py").write_text("", encoding="utf-8")
        result = gate_l15_snippet_syntax("test", "python")
        assert result.status == STATUS_WARN
        assert "1 snippet issue" in result.detail
