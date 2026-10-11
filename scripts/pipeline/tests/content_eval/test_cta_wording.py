"""Tests for the cta_wording evaluator."""

import tempfile
import textwrap
from pathlib import Path

import pytest

from content_eval.models import Page


def _make_page(content: str, filepath: str = "content/products.aspose.org/en/cells/_index.md") -> Page:
    """Create a Page from markdown content string."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(content)
        f.flush()
        page = Page.load(Path(f.name))
        page.filepath = Path(filepath)
        page._infer_metadata()
        return page


class TestCTAWording:
    def setup_method(self):
        from content_eval.evaluators.cta_wording import CTAWordingEvaluator
        self.evaluator = CTAWordingEvaluator()

    # -- Scope gate: only products pages --

    def test_non_products_page_skipped(self):
        """Evaluator should produce no findings for non-products pages."""
        page = _make_page(
            textwrap.dedent("""\
                ---
                title: Getting Started
                ---
                ## Overview
                Try it free today! Download now from releases.aspose.com.
            """),
            filepath="content/docs.aspose.org/en/cells/python/getting-started.md",
        )
        findings = self.evaluator.evaluate(page, None)
        assert findings == []

    # -- FAIL: deprecated CTA phrases --

    def test_try_it_free_fail(self):
        """'Try it free' should produce FAIL."""
        page = _make_page(textwrap.dedent("""\
            ---
            title: Aspose.Cells
            ---
            ## Get Started
            Try it free with our latest release.
        """))
        findings = self.evaluator.evaluate(page, None)
        cw = [f for f in findings if f.category == "CW"]
        assert len(cw) == 1
        assert cw[0].level == "FAIL"
        assert "Try it free" in cw[0].message

    def test_free_trial_fail(self):
        """'Free trial' should produce FAIL."""
        page = _make_page(textwrap.dedent("""\
            ---
            title: Aspose.Cells
            ---
            ## Overview
            Start your Free Trial today.
        """))
        findings = self.evaluator.evaluate(page, None)
        cw = [f for f in findings if f.category == "CW"]
        assert len(cw) == 1
        assert cw[0].level == "FAIL"
        assert "Free trial" in cw[0].message

    def test_download_now_fail(self):
        """'Download now' should produce FAIL."""
        page = _make_page(textwrap.dedent("""\
            ---
            title: Aspose.Cells
            ---
            ## Overview
            Download Now to get started.
        """))
        findings = self.evaluator.evaluate(page, None)
        cw = [f for f in findings if f.category == "CW"]
        assert len(cw) == 1
        assert cw[0].level == "FAIL"
        assert "Download now" in cw[0].message

    def test_deprecated_phrases_case_insensitive(self):
        """Deprecated phrases should match regardless of case."""
        page = _make_page(textwrap.dedent("""\
            ---
            title: Aspose.Cells
            ---
            ## Overview
            TRY IT FREE right now.
        """))
        findings = self.evaluator.evaluate(page, None)
        cw = [f for f in findings if f.category == "CW"]
        assert len(cw) == 1
        assert cw[0].level == "FAIL"

    # -- FAIL: old download URLs --

    def test_releases_aspose_com_fail(self):
        """releases.aspose.com URL should produce FAIL."""
        page = _make_page(textwrap.dedent("""\
            ---
            title: Aspose.Cells
            ---
            ## Download
            Get it from [here](https://releases.aspose.com/cells/net/).
        """))
        findings = self.evaluator.evaluate(page, None)
        cw = [f for f in findings if f.category == "CW"]
        assert any(f.level == "FAIL" and "releases.aspose.com" in f.message for f in cw)

    def test_downloads_aspose_com_fail(self):
        """downloads.aspose.com URL should produce FAIL."""
        page = _make_page(textwrap.dedent("""\
            ---
            title: Aspose.Cells
            ---
            ## Download
            Visit downloads.aspose.com for the latest version.
        """))
        findings = self.evaluator.evaluate(page, None)
        cw = [f for f in findings if f.category == "CW"]
        assert any(f.level == "FAIL" and "downloads.aspose.com" in f.message for f in cw)

    # -- FAIL: double-prefix URLs --

    def test_double_prefix_slash_fail(self):
        """/products/products/ double prefix should produce FAIL."""
        page = _make_page(textwrap.dedent("""\
            ---
            title: Aspose.Cells
            ---
            ## Links
            See [the page](/products/products/cells/).
        """))
        findings = self.evaluator.evaluate(page, None)
        cw = [f for f in findings if f.category == "CW"]
        assert any(f.level == "FAIL" and "Double-prefix" in f.message for f in cw)

    def test_double_prefix_domain_fail(self):
        """products.aspose.org/products/ double prefix should produce FAIL."""
        page = _make_page(textwrap.dedent("""\
            ---
            title: Aspose.Cells
            ---
            ## Links
            Visit https://products.aspose.org/products/cells/ for details.
        """))
        findings = self.evaluator.evaluate(page, None)
        cw = [f for f in findings if f.category == "CW"]
        assert any(f.level == "FAIL" and "Double-prefix" in f.message for f in cw)

    # -- WARN: placeholder language --

    def test_coming_soon_warn(self):
        """'coming soon' should produce WARN."""
        page = _make_page(textwrap.dedent("""\
            ---
            title: Aspose.Cells
            ---
            ## Features
            Python support is coming soon.
        """))
        findings = self.evaluator.evaluate(page, None)
        cw = [f for f in findings if f.category == "CW"]
        assert len(cw) == 1
        assert cw[0].level == "WARN"
        assert "coming soon" in cw[0].message

    def test_coming_soon_hyphenated_warn(self):
        """'coming-soon' (hyphenated) should produce WARN."""
        page = _make_page(textwrap.dedent("""\
            ---
            title: Aspose.Cells
            ---
            ## Features
            This feature is coming-soon in the next release.
        """))
        findings = self.evaluator.evaluate(page, None)
        cw = [f for f in findings if f.category == "CW"]
        assert len(cw) == 1
        assert cw[0].level == "WARN"

    # -- Clean page: no findings --

    def test_clean_page_no_findings(self):
        """A page with no issues should produce no findings."""
        page = _make_page(textwrap.dedent("""\
            ---
            title: Aspose.Cells for .NET
            ---
            ## Overview
            Aspose.Cells for .NET is a spreadsheet programming API that allows
            developers to create, manipulate, and convert Excel files from within
            their own applications.

            ## Getting Started
            Install via NuGet: `Install-Package Aspose.Cells`.
        """))
        findings = self.evaluator.evaluate(page, None)
        assert findings == []

    # -- Multiple findings on one page --

    def test_multiple_findings(self):
        """Page with multiple issues should report all of them."""
        page = _make_page(textwrap.dedent("""\
            ---
            title: Aspose.Cells
            ---
            ## Overview
            Try it free today!
            Download from https://releases.aspose.com/cells/.
            Python support is coming soon.
        """))
        findings = self.evaluator.evaluate(page, None)
        cw = [f for f in findings if f.category == "CW"]
        levels = {f.level for f in cw}
        assert "FAIL" in levels
        assert "WARN" in levels
        assert len(cw) >= 3  # at least: try it free, old URL, coming soon
