"""Tests for the content_substance evaluator."""

import tempfile
import textwrap
from pathlib import Path

import pytest

from content_eval.models import Page


def _make_page(content: str, filepath: str = "content/docs.aspose.org/en/3d/python/rendering.md") -> Page:
    """Create a Page from markdown content string."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(content)
        f.flush()
        page = Page.load(Path(f.name))
        page.filepath = Path(filepath)
        page._infer_metadata()
        return page


class TestContentSubstance:
    def setup_method(self):
        from content_eval.evaluators.content_substance import ContentSubstanceEvaluator
        self.evaluator = ContentSubstanceEvaluator()

    def test_stub_page_fail(self):
        """Page with <50 prose words → FAIL."""
        page = _make_page(textwrap.dedent("""\
            ---
            title: Rendering
            ---
            ## Overview
            This page covers rendering.
        """))
        findings = self.evaluator.evaluate(page, None)
        cs_findings = [f for f in findings if f.category == "CS"]
        assert len(cs_findings) == 1
        assert cs_findings[0].level == "FAIL"
        assert "stub" in cs_findings[0].message.lower()

    def test_reference_no_code_thin_prose_warn(self):
        """Reference page with 0 code blocks and <200 words → WARN."""
        # Generate ~100 words of prose
        prose = " ".join(["word"] * 100)
        page = _make_page(textwrap.dedent(f"""\
            ---
            title: Scene
            ---
            ## Scene Class
            {prose}
        """), "content/reference.aspose.org/en/3d/python/Scene.md")
        findings = self.evaluator.evaluate(page, None)
        cs_findings = [f for f in findings if f.category == "CS"]
        assert len(cs_findings) == 1
        assert cs_findings[0].level == "WARN"
        assert "reference" in cs_findings[0].message.lower()

    def test_reference_with_code_no_warn(self):
        """Reference page with code blocks but thin prose → no WARN."""
        page = _make_page(textwrap.dedent("""\
            ---
            title: Scene
            ---
            ## Scene Class
            The Scene class represents a 3D scene.

            ```python
            from aspose.threed import Scene
            scene = Scene()
            scene.open("model.fbx")
            ```
        """), "content/reference.aspose.org/en/3d/python/Scene.md")
        findings = self.evaluator.evaluate(page, None)
        cs_findings = [f for f in findings if f.category == "CS"]
        # Should not warn because code blocks exist (even though prose is thin,
        # the page has substantive code examples)
        warn_findings = [f for f in cs_findings if f.level == "WARN"]
        assert len(warn_findings) == 0

    def test_howto_no_code_thin_prose_warn(self):
        """Howto page with 0 code blocks and <150 words → WARN."""
        prose = " ".join(["word"] * 80)
        page = _make_page(textwrap.dedent(f"""\
            ---
            title: How to Build Mesh
            type: topic
            ---
            ## Introduction
            {prose}
        """), "content/kb.aspose.org/en/3d/python/how-to-build-mesh.md")
        findings = self.evaluator.evaluate(page, None)
        cs_findings = [f for f in findings if f.category == "CS"]
        assert len(cs_findings) == 1
        assert cs_findings[0].level == "WARN"

    def test_substantial_page_no_finding(self):
        """Page with 300+ words and code blocks → no CS findings."""
        prose = " ".join(["word"] * 300)
        page = _make_page(textwrap.dedent(f"""\
            ---
            title: Working with Scenes
            ---
            ## Overview
            {prose}

            ```python
            from aspose.threed import Scene
            scene = Scene()
            ```

            ## More Details
            Additional information about scene handling.
        """))
        findings = self.evaluator.evaluate(page, None)
        cs_findings = [f for f in findings if f.category == "CS"]
        assert len(cs_findings) == 0

    def test_index_page_exempt(self):
        """_index.md page with <50 words → no findings (exempt)."""
        page = _make_page(textwrap.dedent("""\
            ---
            title: Developer Guide
            ---
            {{< children >}}
        """), "content/docs.aspose.org/en/3d/python/developer-guide/_index.md")
        findings = self.evaluator.evaluate(page, None)
        cs_findings = [f for f in findings if f.category == "CS"]
        assert len(cs_findings) == 0

    def test_products_page_exempt(self):
        """Products page with thin content → no findings (exempt)."""
        page = _make_page(textwrap.dedent("""\
            ---
            title: Aspose.3D
            layout: plugin
            ---
            Product overview.
        """), "content/products.aspose.org/en/3d/_index.md")
        findings = self.evaluator.evaluate(page, None)
        cs_findings = [f for f in findings if f.category == "CS"]
        assert len(cs_findings) == 0
