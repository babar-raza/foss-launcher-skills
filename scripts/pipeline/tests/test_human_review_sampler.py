"""Tests for human_review_sampler.py — H-gate sampling and sign-off reading."""

from __future__ import annotations

import re
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

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
        from scripts.pipeline.human_review_sampler import generate_h01, _ROOT
        with patch.object(
            __import__("scripts.pipeline.human_review_sampler", fromlist=["_ROOT"]),
            "_ROOT", repo_root
        ), patch.object(
            __import__("scripts.pipeline.human_review_sampler", fromlist=["_CONTENT"]),
            "_CONTENT", repo_root / "content"
        ), patch.object(
            __import__("scripts.pipeline.human_review_sampler", fromlist=["_REPORT_DIR"]),
            "_REPORT_DIR", repo_root / "reports" / "human-review"
        ):
            out = generate_h01("3d", "java")
            assert out.exists()
            text = out.read_text()
            # Count table rows (excluding header and separator)
            rows = [l for l in text.split("\n") if l.startswith("| ") and not l.startswith("| #") and not l.startswith("|---")]
            assert len(rows) == 5

    def test_h02_generates_correct_sample_size(self, repo_root):
        """H-02 generates exactly 10 reference pages."""
        from scripts.pipeline.human_review_sampler import generate_h02
        with patch.object(
            __import__("scripts.pipeline.human_review_sampler", fromlist=["_ROOT"]),
            "_ROOT", repo_root
        ), patch.object(
            __import__("scripts.pipeline.human_review_sampler", fromlist=["_CONTENT"]),
            "_CONTENT", repo_root / "content"
        ), patch.object(
            __import__("scripts.pipeline.human_review_sampler", fromlist=["_REPORT_DIR"]),
            "_REPORT_DIR", repo_root / "reports" / "human-review"
        ):
            out = generate_h02("3d", "java")
            assert out.exists()
            text = out.read_text()
            rows = [l for l in text.split("\n") if l.startswith("| ") and not l.startswith("| #") and not l.startswith("|---")]
            assert len(rows) == 10

    def test_h01_sample_contains_signoff_block(self, repo_root):
        """H-01 sample file includes the sign-off template."""
        from scripts.pipeline.human_review_sampler import generate_h01
        with patch.object(
            __import__("scripts.pipeline.human_review_sampler", fromlist=["_ROOT"]),
            "_ROOT", repo_root
        ), patch.object(
            __import__("scripts.pipeline.human_review_sampler", fromlist=["_CONTENT"]),
            "_CONTENT", repo_root / "content"
        ), patch.object(
            __import__("scripts.pipeline.human_review_sampler", fromlist=["_REPORT_DIR"]),
            "_REPORT_DIR", repo_root / "reports" / "human-review"
        ):
            out = generate_h01("3d", "java")
            text = out.read_text()
            assert 'result: ""' in text
            assert "SIGN-OFF" in text

    def test_h03_h04_h05_templates_created(self, repo_root):
        """H-03/H-04/H-05 templates are created with sign-off blocks."""
        from scripts.pipeline.human_review_sampler import generate_h03_h04_h05
        with patch.object(
            __import__("scripts.pipeline.human_review_sampler", fromlist=["_ROOT"]),
            "_ROOT", repo_root
        ), patch.object(
            __import__("scripts.pipeline.human_review_sampler", fromlist=["_REPORT_DIR"]),
            "_REPORT_DIR", repo_root / "reports" / "human-review"
        ):
            outs = generate_h03_h04_h05("3d", "java")
            assert len(outs) == 3
            for o in outs:
                assert o.exists()
                assert "SIGN-OFF" in o.read_text()


# ---------------------------------------------------------------------------
# Tests: readiness_scorecard H-gate integration
# ---------------------------------------------------------------------------

class TestScorecardHgates:
    """Tests for H-gate sign-off reading in readiness_scorecard."""

    def test_read_hgate_pass(self, repo_root):
        """Signed-off H-gate with result: PASS is read correctly."""
        from scripts.pipeline.readiness_scorecard import _read_hgate_signoffs, _ROOT
        review_dir = repo_root / "reports" / "human-review"
        sample = review_dir / "3d-java-h01-sample.md"
        sample.write_text('# H-01\n\n```yaml\nresult: "PASS"\n```\n')

        with patch.object(
            __import__("scripts.pipeline.readiness_scorecard", fromlist=["_ROOT"]),
            "_ROOT", repo_root
        ):
            results = _read_hgate_signoffs("3d", "java")
            assert results["h01"] == "PASS"

    def test_read_hgate_missing(self, repo_root):
        """Missing sign-off file returns empty string."""
        from scripts.pipeline.readiness_scorecard import _read_hgate_signoffs
        with patch.object(
            __import__("scripts.pipeline.readiness_scorecard", fromlist=["_ROOT"]),
            "_ROOT", repo_root
        ):
            results = _read_hgate_signoffs("3d", "java")
            assert results["h01"] == ""

    def test_read_hgate_unsigned(self, repo_root):
        """Sign-off file exists but result is empty."""
        from scripts.pipeline.readiness_scorecard import _read_hgate_signoffs
        review_dir = repo_root / "reports" / "human-review"
        sample = review_dir / "3d-java-h02-sample.md"
        sample.write_text('# H-02\n\n```yaml\nresult: ""\n```\n')

        with patch.object(
            __import__("scripts.pipeline.readiness_scorecard", fromlist=["_ROOT"]),
            "_ROOT", repo_root
        ):
            results = _read_hgate_signoffs("3d", "java")
            assert results["h02"] == ""

    def test_read_hgate_fail(self, repo_root):
        """Signed-off H-gate with result: FAIL is read correctly."""
        from scripts.pipeline.readiness_scorecard import _read_hgate_signoffs
        review_dir = repo_root / "reports" / "human-review"
        sample = review_dir / "3d-java-h03-sample.md"
        sample.write_text('# H-03\n\n```yaml\nresult: "FAIL"\n```\n')

        with patch.object(
            __import__("scripts.pipeline.readiness_scorecard", fromlist=["_ROOT"]),
            "_ROOT", repo_root
        ):
            results = _read_hgate_signoffs("3d", "java")
            assert results["h03"] == "FAIL"
