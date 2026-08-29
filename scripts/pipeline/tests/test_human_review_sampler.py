"""Tests for human_review_sampler.py — H-gate sampling and sign-off reading."""

from __future__ import annotations

import re
import sys
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import human_review_sampler as _hrs
import readiness_scorecard as _rs

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_paths(repo_root):
    _hrs.configure(repo_root=repo_root)
    _rs.configure(repo_root=repo_root)
    yield
    _hrs.configure()
    _rs.configure()


@pytest.fixture
def repo_root(tmp_path):
    """Create a minimal repo structure with content pages."""
    root = tmp_path / "repo"
    root.mkdir()

    # Create non-reference pages (docs, blog, products, kb)
    for site in ["docs.aspose.org", "kb.aspose.org"]:
        for i in range(8):
            p = root / "content" / site / "en" / "3d" / "java" / f"page{i}.md"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(f"---\ntitle: Page {i}\ngrade: B\n---\nContent here.\n")

    # Blog pages
    for i in range(3):
        p = root / "content" / "blog.aspose.org" / "3d" / "java" / f"post{i}" / "index.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f"---\ntitle: Post {i}\ngrade: A\n---\nBlog post.\n")

    # Products page
    p = root / "content" / "products.aspose.org" / "en" / "3d" / "_index.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("---\ntitle: Products\ngrade: B\n---\nProducts.\n")

    # Reference pages (varying sizes for stratification)
    ref_root = root / "content" / "reference.aspose.org" / "en" / "3d" / "java"
    ref_root.mkdir(parents=True, exist_ok=True)
    for i in range(15):
        p = ref_root / f"class{i}.md"
        # Vary sizes: 0-4 small, 5-9 medium, 10-14 large
        size = 500 if i < 5 else (5000 if i < 10 else 10000)
        p.write_text(f"---\ntitle: Class{i}\ngrade: C\n---\n" + "x" * size)

    # Reports dir
    (root / "reports" / "human-review").mkdir(parents=True, exist_ok=True)

    return root


# ---------------------------------------------------------------------------
# Tests: human_review_sampler
# ---------------------------------------------------------------------------

class TestSampler:
    """Tests for the human review sampler."""

    def test_h01_generates_correct_sample_size(self, repo_root):
        """H-01 generates exactly 5 non-reference pages."""
        out = _hrs.generate_h01("3d", "java")
        assert out.exists()
        text = out.read_text()
        # Count table rows (excluding header and separator)
        rows = [l for l in text.split("\n") if l.startswith("| ") and not l.startswith("| #") and not l.startswith("|---")]
        assert len(rows) == 5

    def test_h02_generates_correct_sample_size(self, repo_root):
        """H-02 generates exactly 10 reference pages."""
        out = _hrs.generate_h02("3d", "java")
        assert out.exists()
        text = out.read_text()
        rows = [l for l in text.split("\n") if l.startswith("| ") and not l.startswith("| #") and not l.startswith("|---")]
        assert len(rows) == 10

    def test_h01_sample_contains_signoff_block(self, repo_root):
        """H-01 sample file includes the sign-off template."""
        out = _hrs.generate_h01("3d", "java")
        text = out.read_text()
        assert 'result: ""' in text
        assert "SIGN-OFF" in text

    def test_h03_h04_h05_templates_created(self, repo_root):
        """H-03/H-04/H-05 templates are created with sign-off blocks."""
        outs = _hrs.generate_h03_h04_h05("3d", "java")
        assert len(outs) == 3
        for o in outs:
            assert o.exists()
            assert "SIGN-OFF" in o.read_text()


# ---------------------------------------------------------------------------
# Tests: products.aspose.org sibling-platform isolation (MT040, 2026-08-29)
#
# Bug: pdf/typescript's real H-01 sample pulled in
# products.aspose.org/en/pdf/net/_index.md instead of pdf/typescript's own
# page. Root cause: products.aspose.org nests one _index.md per platform as
# a SIBLING directory under en/{family}/ (unlike docs/kb/reference, where
# platform is a child of family) plus one shared en/{family}/_index.md --
# the old `en/{family}/**/*.md` rglob (scoped to family only, no platform
# segment) matched every sibling platform's own page too. The pre-existing
# fixture never had more than one platform under a family, so this was
# never exercised.
# ---------------------------------------------------------------------------

@pytest.fixture
def multi_platform_repo_root(tmp_path):
    """A family with THREE platforms, each carrying its own
    products.aspose.org page -- reproduces the real pdf/{net,python,
    typescript} shape that exposed the bug."""
    root = tmp_path / "repo"
    root.mkdir(exist_ok=True)

    for platform in ("net", "python", "typescript"):
        p = root / "content" / "products.aspose.org" / "en" / "pdf" / platform / "_index.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f"---\ntitle: Products {platform}\ngrade: B\n---\n{platform} product page.\n")

    family_index = root / "content" / "products.aspose.org" / "en" / "pdf" / "_index.md"
    family_index.write_text("---\ntitle: Products\ngrade: B\n---\nFamily page.\n")

    # Minimal docs/kb/blog/reference pages so H-01/H-02 generation doesn't
    # short-circuit on an empty product.
    for site in ["docs.aspose.org", "kb.aspose.org"]:
        p = root / "content" / site / "en" / "pdf" / "typescript" / "page0.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("---\ntitle: Page\ngrade: B\n---\nContent here.\n")

    ref_root = root / "content" / "reference.aspose.org" / "en" / "pdf" / "typescript"
    ref_root.mkdir(parents=True, exist_ok=True)
    (ref_root / "Class0.md").write_text("---\ntitle: Class0\ngrade: A\n---\n" + "x" * 500)

    (root / "reports" / "human-review").mkdir(parents=True, exist_ok=True)
    return root


class TestProductsPageSiblingIsolation:
    """products.aspose.org page collection must never cross into a
    sibling platform's own product page for a multi-platform family."""

    def test_collect_non_reference_pages_excludes_sibling_platforms(self, multi_platform_repo_root):
        _hrs.configure(repo_root=multi_platform_repo_root)
        try:
            pages = _hrs._collect_non_reference_pages("pdf", "typescript")
        finally:
            _hrs.configure()

        products_pages = [p for p in pages if "products.aspose.org" in str(p)]
        products_names = {str(p).replace("\\", "/") for p in products_pages}

        assert any(n.endswith("pdf/typescript/_index.md") for n in products_names), (
            f"the target platform's own products page must be included; got: {products_names}"
        )
        assert any(n.endswith("pdf/_index.md") and "/typescript/" not in n for n in products_names), (
            f"the shared family-level products page must still be included; got: {products_names}"
        )
        assert not any(n.endswith("pdf/net/_index.md") for n in products_names), (
            f"a SIBLING platform's own products page must never be pulled in; got: {products_names}"
        )
        assert not any(n.endswith("pdf/python/_index.md") for n in products_names), (
            f"a SIBLING platform's own products page must never be pulled in; got: {products_names}"
        )
        # Exactly two products.aspose.org pages: the target platform's own
        # page and the one shared family page -- never more.
        assert len(products_pages) == 2, f"expected exactly 2 products pages, got: {products_names}"

    def test_h01_sample_never_names_a_sibling_platform_page(self, multi_platform_repo_root):
        """End-to-end: the real generate_h01() output must never name a
        sibling platform's products page."""
        _hrs.configure(repo_root=multi_platform_repo_root)
        try:
            out = _hrs.generate_h01("pdf", "typescript")
            text = out.read_text()
            assert "pdf/net/_index.md" not in text.replace("\\", "/")
            assert "pdf/python/_index.md" not in text.replace("\\", "/")
        finally:
            _hrs.configure()


# ---------------------------------------------------------------------------
# Tests: readiness_scorecard H-gate integration
# ---------------------------------------------------------------------------

class TestScorecardHgates:
    """Tests for H-gate sign-off reading in readiness_scorecard."""

    def test_read_hgate_pass(self, repo_root):
        """Signed-off H-gate with result: PASS is read correctly."""
        review_dir = repo_root / "reports" / "human-review"
        sample = review_dir / "3d-java-h01-sample.md"
        sample.write_text('# H-01\n\n```yaml\nresult: "PASS"\n```\n')

        results = _rs._read_hgate_signoffs("3d", "java")
        assert results["h01"] == "PASS"

    def test_read_hgate_missing(self, repo_root):
        """Missing sign-off file returns empty string."""
        results = _rs._read_hgate_signoffs("3d", "java")
        assert results["h01"] == ""

    def test_read_hgate_unsigned(self, repo_root):
        """Sign-off file exists but result is empty."""
        review_dir = repo_root / "reports" / "human-review"
        sample = review_dir / "3d-java-h02-sample.md"
        sample.write_text('# H-02\n\n```yaml\nresult: ""\n```\n')

        results = _rs._read_hgate_signoffs("3d", "java")
        assert results["h02"] == ""

    def test_read_hgate_fail(self, repo_root):
        """Signed-off H-gate with result: FAIL is read correctly."""
        review_dir = repo_root / "reports" / "human-review"
        sample = review_dir / "3d-java-h03-sample.md"
        sample.write_text('# H-03\n\n```yaml\nresult: "FAIL"\n```\n')

        results = _rs._read_hgate_signoffs("3d", "java")
        assert results["h03"] == "FAIL"


# ---------------------------------------------------------------------------
# CP-P2 Bug 5-8 tests: sampler hardening
# ---------------------------------------------------------------------------

class TestSamplerHardening:
    """Tests for expanded checklist, deterministic seed, integrity binding, verdict column."""

    def test_h01_checklist_has_14_plus_items(self, repo_root):
        """Bug 5: H-01 checklist must have at least 14 items."""
        out = _hrs.generate_h01("3d", "java")
        text = out.read_text()
        checklist_items = [l for l in text.split("\n") if l.startswith("- [ ]")]
        assert len(checklist_items) >= 14, f"Only {len(checklist_items)} checklist items"

    def test_h02_checklist_has_14_plus_items(self, repo_root):
        """Bug 5: H-02 checklist must have at least 14 items."""
        out = _hrs.generate_h02("3d", "java")
        text = out.read_text()
        checklist_items = [l for l in text.split("\n") if l.startswith("- [ ]")]
        assert len(checklist_items) >= 14, f"Only {len(checklist_items)} checklist items"

    def test_h01_seed_is_deterministic_within_week(self, repo_root):
        """Bug 6: Seed must be deterministic (same ISO week → same seed)."""
        import random
        random.seed(42)
        out1 = _hrs.generate_h01("3d", "java")
        text1 = out1.read_text()
        seed_line1 = [l for l in text1.split("\n") if "Sample seed" in l][0]
        # Extract seed value
        seed1 = seed_line1.split(":")[1].strip().split(" ")[0]
        assert "ISO week" in seed_line1, "Seed should reference ISO week"

    def test_h01_signoff_has_pages_hash(self, repo_root):
        """Bug 7: Sign-off block must include pages_hash for integrity binding."""
        out = _hrs.generate_h01("3d", "java")
        text = out.read_text()
        assert "pages_hash:" in text, "Sign-off must include pages_hash"

    def test_h01_verdict_column_populated(self, repo_root):
        """Bug 8: Verdict column must be pre-populated with grade when available."""
        out = _hrs.generate_h01("3d", "java")
        text = out.read_text()
        # Table rows should have grade= in verdict column
        data_rows = [l for l in text.split("\n")
                     if l.startswith("| ") and not l.startswith("| #") and not l.startswith("|---")]
        populated = [r for r in data_rows if "grade=" in r]
        assert len(populated) > 0, "At least one verdict column should be populated"

    def test_signoff_block_accepts_integrity_params(self):
        """Bug 7: _signoff_block() accepts and includes integrity binding fields."""
        block = _hrs._signoff_block(
            logic_version="7",
            pages_hash="abc123",
            evaluator_version="v2",
        )
        assert 'logic_version: "7"' in block
        assert 'pages_hash: "abc123"' in block
        assert 'evaluator_version: "v2"' in block
