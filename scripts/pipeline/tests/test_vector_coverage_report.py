"""Tests for scripts/pipeline/commands/knowledge/vector_coverage_report.py (TC-VEC-06)."""

import json

# sys.path is set by tests/conftest.py — no manual insert needed here.
import vector_coverage_report as vcr


def _write_index(tmp_path, products):
    (tmp_path / "knowledge").mkdir(parents=True, exist_ok=True)
    (tmp_path / "knowledge" / "_index.json").write_text(
        json.dumps({"products": products}), encoding="utf-8"
    )


def _write_active(tmp_path, family, platform):
    root = tmp_path / "knowledge" / "_vectors" / family / platform
    root.mkdir(parents=True, exist_ok=True)
    (root / "active.json").write_text(
        json.dumps({"version": "2.0.0", "profile_id": "fake"}), encoding="utf-8"
    )


class TestCoverageRows:
    def setup_method(self):
        vcr.configure()

    def teardown_method(self):
        vcr.configure()

    def test_no_index_returns_empty(self, tmp_path):
        vcr.configure(knowledge_root=tmp_path / "knowledge")
        assert vcr.coverage_rows() == []

    def test_reports_present_and_missing_correctly(self, tmp_path):
        _write_index(
            tmp_path,
            [
                {"family": "widgets", "platform": "python"},
                {"family": "widgets", "platform": "java"},
            ],
        )
        _write_active(tmp_path, "widgets", "python")
        vcr.configure(knowledge_root=tmp_path / "knowledge")

        rows = vcr.coverage_rows()
        by_platform = {r["platform"]: r["has_vectors"] for r in rows}
        assert by_platform == {"python": True, "java": False}

    def test_rows_sorted_by_family_then_platform(self, tmp_path):
        _write_index(
            tmp_path,
            [
                {"family": "zeta", "platform": "net"},
                {"family": "alpha", "platform": "python"},
                {"family": "alpha", "platform": "java"},
            ],
        )
        vcr.configure(knowledge_root=tmp_path / "knowledge")

        rows = vcr.coverage_rows()
        pairs = [(r["family"], r["platform"]) for r in rows]
        assert pairs == [("alpha", "java"), ("alpha", "python"), ("zeta", "net")]


class TestRenderMarkdownTable:
    def test_missing_row_flagged(self):
        rows = [
            {"family": "widgets", "platform": "python", "has_vectors": True},
            {"family": "widgets", "platform": "java", "has_vectors": False},
        ]
        table = vcr.render_markdown_table(rows)
        assert "| widgets | python | yes |" in table
        assert "| widgets | java | MISSING |" in table


