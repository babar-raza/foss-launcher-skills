"""Tests for content_eval models."""

import tempfile
import textwrap
from pathlib import Path

import pytest
import sys

# Add pipeline to path for audit imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts" / "pipeline"))

from scripts.pipeline.content_eval.models import (
    CodeBlock,
    EvalReport,
    Finding,
    Heading,
    Page,
)


class TestFinding:
    def test_stable_id(self):
        f = Finding("FAIL", "AA", "test.md", 10, "Method not found")
        assert f.id.startswith("CE-")
        assert len(f.id) == 11  # CE- + 8 hex chars

    def test_same_finding_same_id(self):
        f1 = Finding("FAIL", "AA", "test.md", 10, "Method not found")
        f2 = Finding("FAIL", "AA", "test.md", 10, "Method not found")
        assert f1.id == f2.id

    def test_different_finding_different_id(self):
        f1 = Finding("FAIL", "AA", "test.md", 10, "Method not found")
        f2 = Finding("FAIL", "AA", "test.md", 11, "Method not found")
        assert f1.id != f2.id


class TestPage:
    def _make_page(self, content: str, filename: str = "content/docs.aspose.org/en/slides/dotnet/test.md"):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write(content)
            f.flush()
            # Override filepath for metadata inference
            page = Page.load(Path(f.name))
            # Manually set filepath for path-based inference
            page.filepath = Path(filename)
            page._infer_metadata()
            return page

    def test_frontmatter_parsing(self):
        page = self._make_page(textwrap.dedent("""\
            ---
            title: Test Page
            description: A test
            type: docs
            ---
            Hello world.
        """))
        assert page.frontmatter["title"] == "Test Page"
        assert page.frontmatter["type"] == "docs"

    def test_code_block_extraction(self):
        page = self._make_page(textwrap.dedent("""\
            ---
            title: Test
            ---
            Some text.

            ```csharp
            var prs = new Presentation();
            prs.Save("out.pptx");
            ```

            More text.
        """))
        assert len(page.code_blocks) == 1
        assert page.code_blocks[0].lang == "csharp"
        assert "Presentation" in page.code_blocks[0].content

    def test_heading_extraction(self):
        page = self._make_page(textwrap.dedent("""\
            ---
            title: Test
            ---
            ## Overview
            Some text.
            ### Details
            More text.
        """))
        assert len(page.headings) == 2
        assert page.headings[0].level == 2
        assert page.headings[0].text == "Overview"
        assert page.headings[1].level == 3

    def test_subdomain_inference(self):
        page = self._make_page("---\ntitle: T\n---\nHi", "content/kb.aspose.org/en/slides/dotnet/faq.md")
        assert page.subdomain == "kb"
        assert page.family == "slides"
        assert page.platform == "dotnet"
        assert page.page_role == "faq"

    def test_prose_lines(self):
        page = self._make_page(textwrap.dedent("""\
            ---
            title: T
            ---
            This is prose.

            ```python
            x = 1
            ```

            More prose here.
        """))
        prose_texts = [t for _, t in page.prose_lines]
        assert "This is prose." in prose_texts
        assert "More prose here." in prose_texts
        assert "x = 1" not in prose_texts


class TestEvalReport:
    def test_severity_counts(self):
        report = EvalReport(findings=[
            Finding("FAIL", "AA", "a.md", 1, "bad"),
            Finding("WARN", "ST", "a.md", 2, "meh"),
            Finding("INFO", "RL", "b.md", 1, "fyi"),
            Finding("FAIL", "FC", "c.md", 1, "forbidden"),
        ])
        assert len(report.fails) == 2
        assert len(report.warns) == 1
        assert len(report.infos) == 1

    def test_by_file(self):
        report = EvalReport(findings=[
            Finding("FAIL", "AA", "a.md", 1, "bad"),
            Finding("WARN", "ST", "a.md", 2, "meh"),
            Finding("INFO", "RL", "b.md", 1, "fyi"),
        ])
        by_file = report.by_file()
        assert len(by_file["a.md"]) == 2
        assert len(by_file["b.md"]) == 1

    def test_by_category(self):
        report = EvalReport(findings=[
            Finding("FAIL", "AA", "a.md", 1, "bad"),
            Finding("FAIL", "AA", "b.md", 2, "also bad"),
            Finding("INFO", "RL", "c.md", 1, "fyi"),
        ])
        by_cat = report.by_category()
        assert len(by_cat["AA"]) == 2
        assert len(by_cat["RL"]) == 1
