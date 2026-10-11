"""Tests for page_spec.py — site plan loading and reconciliation."""
from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest
import yaml

from page_spec import (
    PageSpec,
    SectionPlan,
    SitePlan,
    ReconcileResult,
    load_plan,
    reconcile,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MINIMAL_PLAN = {
    "plan": {
        "schema_version": 1,
        "plan_version": 1,
        "family": "3d",
        "platform": "python",
        "generated_at": "2026-04-16T00:00:00Z",
        "repo_sha": "abc123",
        "knowledge_version": "26.1.0",
        "launch_tier": "full",
        "sections": {
            "products": {
                "page_count": 1,
                "pages": [
                    {
                        "slug": "_index",
                        "path": "content/products.aspose.org/en/3d/_index.md",
                        "weight": 1,
                        "mandatory": True,
                        "page_class": "structural",
                        "layout": "family",
                        "note": "Family landing page",
                    }
                ],
            },
            "reference": {
                "page_count": 2,
                "pages": [
                    {
                        "slug": "Scene",
                        "path": "content/reference.aspose.org/en/3d/python/Scene.md",
                        "weight": 1,
                        "mandatory": False,
                        "page_class": "generated",
                    },
                    {
                        "slug": "Node",
                        "path": "content/reference.aspose.org/en/3d/python/Node.md",
                        "weight": 2,
                        "mandatory": False,
                        "page_class": "generated",
                    },
                ],
            },
        },
    }
}


@pytest.fixture
def plan_file(tmp_path):
    """Write a minimal plan YAML and return its path."""
    p = tmp_path / "site_plan.yaml"
    p.write_text(yaml.dump(MINIMAL_PLAN, default_flow_style=False), encoding="utf-8")
    return p


@pytest.fixture
def plan_with_content(tmp_path):
    """Write plan + create some content files on disk."""
    p = tmp_path / "site_plan.yaml"
    p.write_text(yaml.dump(MINIMAL_PLAN, default_flow_style=False), encoding="utf-8")

    # Create the products page (exists)
    products_dir = tmp_path / "content" / "products.aspose.org" / "en" / "3d"
    products_dir.mkdir(parents=True)
    (products_dir / "_index.md").write_text("---\ntitle: 3D\n---\n")

    # Create one reference page (Scene exists, Node does not)
    ref_dir = tmp_path / "content" / "reference.aspose.org" / "en" / "3d" / "python"
    ref_dir.mkdir(parents=True)
    (ref_dir / "Scene.md").write_text("---\ntitle: Scene\n---\n")
    # Also create an extra page not in plan
    (ref_dir / "Extra.md").write_text("---\ntitle: Extra\n---\n")

    return p, tmp_path


# ---------------------------------------------------------------------------
# PageSpec
# ---------------------------------------------------------------------------

class TestPageSpec:
    def test_from_dict_basic(self):
        d = {"slug": "test", "path": "content/test.md", "weight": 5, "mandatory": True}
        ps = PageSpec.from_dict(d)
        assert ps.slug == "test"
        assert ps.path == "content/test.md"
        assert ps.weight == 5
        assert ps.mandatory is True

    def test_from_dict_ignores_unknown_keys(self):
        d = {"slug": "test", "path": "content/test.md", "unknown_field": 42}
        ps = PageSpec.from_dict(d)
        assert ps.slug == "test"
        assert not hasattr(ps, "unknown_field") or ps.__dict__.get("unknown_field") is None

    def test_from_dict_defaults(self):
        d = {"slug": "test", "path": "content/test.md"}
        ps = PageSpec.from_dict(d)
        assert ps.weight == 0
        assert ps.mandatory is False
        assert ps.page_class == "generated"
        assert ps.note == ""

    def test_from_dict_all_optional_fields(self):
        d = {
            "slug": "test", "path": "content/test.md",
            "layout": "family", "type": "docs", "page_role": "toc",
            "blog_role": "announcement", "source": "discovered",
            "cluster": "io-ops", "claim_count": 10, "api_method_count": 5,
        }
        ps = PageSpec.from_dict(d)
        assert ps.layout == "family"
        assert ps.type == "docs"
        assert ps.cluster == "io-ops"
        assert ps.claim_count == 10


# ---------------------------------------------------------------------------
# SectionPlan
# ---------------------------------------------------------------------------

class TestSectionPlan:
    def test_from_dict(self):
        d = {
            "page_count": 2,
            "pages": [
                {"slug": "a", "path": "content/a.md"},
                {"slug": "b", "path": "content/b.md"},
            ],
        }
        sp = SectionPlan.from_dict("docs", d)
        assert sp.name == "docs"
        assert sp.page_count == 2
        assert len(sp.pages) == 2
        assert sp.pages[0].slug == "a"

    def test_from_dict_empty_pages(self):
        sp = SectionPlan.from_dict("blog", {"page_count": 0, "pages": []})
        assert sp.page_count == 0
        assert sp.pages == []

    def test_from_dict_infers_page_count(self):
        d = {"pages": [{"slug": "x", "path": "content/x.md"}]}
        sp = SectionPlan.from_dict("kb", d)
        assert sp.page_count == 1


# ---------------------------------------------------------------------------
# SitePlan
# ---------------------------------------------------------------------------

class TestSitePlan:
    def test_all_pages_flattens(self):
        plan = SitePlan(
            family="3d", platform="python",
            sections={
                "products": SectionPlan("products", 1, [
                    PageSpec(slug="a", path="content/a.md"),
                ]),
                "reference": SectionPlan("reference", 2, [
                    PageSpec(slug="b", path="content/b.md"),
                    PageSpec(slug="c", path="content/c.md"),
                ]),
            },
        )
        assert len(plan.all_pages) == 3

    def test_total_page_count(self):
        plan = SitePlan(
            family="3d", platform="python",
            sections={
                "products": SectionPlan("products", 5, []),
                "docs": SectionPlan("docs", 10, []),
            },
        )
        assert plan.total_page_count == 15


# ---------------------------------------------------------------------------
# load_plan
# ---------------------------------------------------------------------------

class TestLoadPlan:
    def test_load_minimal_plan(self, plan_file):
        plan = load_plan(plan_file)
        assert plan.family == "3d"
        assert plan.platform == "python"
        assert plan.schema_version == 1
        assert plan.repo_sha == "abc123"
        assert "products" in plan.sections
        assert "reference" in plan.sections
        assert len(plan.sections["products"].pages) == 1
        assert len(plan.sections["reference"].pages) == 2

    def test_load_plan_page_details(self, plan_file):
        plan = load_plan(plan_file)
        products_page = plan.sections["products"].pages[0]
        assert products_page.slug == "_index"
        assert products_page.mandatory is True
        assert products_page.layout == "family"
        assert products_page.page_class == "structural"

    def test_load_plan_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_plan(tmp_path / "nonexistent.yaml")

    def test_load_plan_invalid_structure(self, tmp_path):
        bad = tmp_path / "bad.yaml"
        bad.write_text("not_a_plan: true", encoding="utf-8")
        with pytest.raises(ValueError, match="missing top-level"):
            load_plan(bad)

    def test_load_real_plan(self):
        """Smoke test: load an actual plan file if it exists."""
        real = Path("reports/plans/note/python/site_plan.yaml")
        if not real.exists():
            pytest.skip("No real plan file available")
        plan = load_plan(real)
        assert plan.family == "note"
        assert plan.platform == "python"
        assert plan.total_page_count > 0


# ---------------------------------------------------------------------------
# reconcile
# ---------------------------------------------------------------------------

class TestReconcile:
    def test_all_files_present(self, tmp_path):
        plan = SitePlan(
            family="3d", platform="python",
            sections={
                "docs": SectionPlan("docs", 1, [
                    PageSpec(slug="features", path="content/docs/features.md"),
                ]),
            },
        )
        (tmp_path / "content" / "docs").mkdir(parents=True)
        (tmp_path / "content" / "docs" / "features.md").write_text("---\ntitle: F\n---\n")

        result = reconcile(plan, root=tmp_path)
        assert result.is_clean
        assert len(result.matched) == 1
        assert len(result.missing) == 0
        assert len(result.extra) == 0

    def test_missing_file_detected(self, tmp_path):
        plan = SitePlan(
            family="3d", platform="python",
            sections={
                "docs": SectionPlan("docs", 1, [
                    PageSpec(slug="missing", path="content/docs/missing.md", mandatory=True),
                ]),
            },
        )
        (tmp_path / "content" / "docs").mkdir(parents=True)

        result = reconcile(plan, root=tmp_path)
        assert not result.is_clean
        assert len(result.missing) == 1
        assert result.missing[0].slug == "missing"
        assert result.missing[0].mandatory is True

    def test_extra_file_detected(self, plan_with_content):
        plan_file, root = plan_with_content
        plan = load_plan(plan_file)
        result = reconcile(plan, root=root)

        assert len(result.extra) == 1
        assert "Extra.md" in result.extra[0]

    def test_mixed_state(self, plan_with_content):
        plan_file, root = plan_with_content
        plan = load_plan(plan_file)
        result = reconcile(plan, root=root)

        # products/_index.md exists, Scene.md exists, Node.md missing, Extra.md extra
        assert len(result.matched) == 2  # _index + Scene
        assert len(result.missing) == 1  # Node
        assert len(result.extra) == 1    # Extra

    def test_section_filter(self, plan_with_content):
        plan_file, root = plan_with_content
        plan = load_plan(plan_file)

        # Only reconcile products section
        result = reconcile(plan, root=root, sections=["products"])
        assert len(result.matched) == 1  # _index exists
        assert len(result.missing) == 0
        assert len(result.extra) == 0  # Extra.md is in reference, not products

    def test_summary_format(self, plan_with_content):
        plan_file, root = plan_with_content
        plan = load_plan(plan_file)
        result = reconcile(plan, root=root)
        text = result.summary()

        assert "RECONCILE" in text
        assert "3d/python" in text
        assert "Missing:" in text
        assert "Extra" in text

    def test_to_dict_structure(self, plan_with_content):
        plan_file, root = plan_with_content
        plan = load_plan(plan_file)
        result = reconcile(plan, root=root)
        d = result.to_dict()

        assert d["family"] == "3d"
        assert d["platform"] == "python"
        assert isinstance(d["missing"], list)
        assert isinstance(d["extra"], list)
        assert "is_clean" in d
        assert d["matched_count"] == 2


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

class TestCLI:
    def test_cli_text_output(self, plan_with_content, capsys):
        plan_file, root = plan_with_content
        import page_spec
        page_spec.configure(repo_root=root)
        try:
            import sys
            sys.argv = ["page_spec", str(plan_file)]
            with pytest.raises(SystemExit) as exc:
                page_spec.main()
            # Exit 2 = not clean (has missing + extra)
            assert exc.value.code == 2
            captured = capsys.readouterr()
            assert "RECONCILE" in captured.out
        finally:
            page_spec.configure()

    def test_cli_json_output(self, plan_with_content, capsys):
        plan_file, root = plan_with_content
        import page_spec
        page_spec.configure(repo_root=root)
        try:
            import sys
            sys.argv = ["page_spec", str(plan_file), "--json"]
            with pytest.raises(SystemExit):
                page_spec.main()
            captured = capsys.readouterr()
            data = json.loads(captured.out)
            assert "missing_count" in data
        finally:
            page_spec.configure()

    def test_cli_strict_mode(self, tmp_path, capsys):
        """--strict exits 1 when mandatory pages are missing."""
        plan_data = {
            "plan": {
                "family": "test", "platform": "py",
                "sections": {
                    "docs": {
                        "page_count": 1,
                        "pages": [{"slug": "req", "path": "content/req.md", "mandatory": True}],
                    }
                },
            }
        }
        pf = tmp_path / "plan.yaml"
        pf.write_text(yaml.dump(plan_data), encoding="utf-8")

        import page_spec
        page_spec.configure(repo_root=tmp_path)
        try:
            import sys
            sys.argv = ["page_spec", str(pf), "--strict"]
            with pytest.raises(SystemExit) as exc:
                page_spec.main()
            assert exc.value.code == 1
        finally:
            page_spec.configure()
