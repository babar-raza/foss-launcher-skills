"""Tests for namespace_correctness evaluator v2 — C# canonical namespace support."""

import json
import tempfile
import textwrap
from pathlib import Path

import pytest
import yaml

from content_eval.evaluators import namespace_correctness as ns_mod
from content_eval.evaluators.namespace_correctness import (
    NamespaceCorrectnessEvaluator,
    _build_allow_prefixes,
    _load_canonical_namespaces,
    configure,
)
from content_eval.models import Page


def _make_page(content: str, filepath: str) -> Page:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(content)
        f.flush()
        page = Page.load(Path(f.name))
        page.filepath = Path(filepath)
        page._infer_metadata()
        return page


@pytest.fixture
def knowledge_dir(tmp_path):
    """Create a temporary knowledge directory with pdf/net model + api_surface."""
    merged = tmp_path / "pdf" / "net" / "merged"
    merged.mkdir(parents=True)

    model = {"package_name": "Aspose.Pdf.Foss", "family": "pdf", "platform": "net"}
    (merged / "model.yaml").write_text(yaml.dump(model), encoding="utf-8")

    api_surface = [
        {"name": "Document", "canonical_namespace": "Aspose.Pdf"},
        {"name": "TextFragmentAbsorber", "canonical_namespace": "Aspose.Pdf.Text"},
        {"name": "Annotation", "canonical_namespace": "Aspose.Pdf.Annotations"},
        {"name": "PdfFileEditor", "canonical_namespace": "Aspose.Pdf.Facades"},
    ]
    (merged / "api_surface.json").write_text(json.dumps(api_surface), encoding="utf-8")
    return tmp_path


@pytest.fixture(autouse=True)
def _reset_knowledge_root(knowledge_dir):
    """Point KNOWLEDGE_ROOT at temp dir for all tests, reset after."""
    configure(knowledge_root=knowledge_dir)
    yield
    configure()


class TestBuildAllowPrefixes:
    def test_net_uses_canonical_namespaces(self):
        ns = {"Aspose.Pdf", "Aspose.Pdf.Text"}
        result = _build_allow_prefixes("Aspose.Pdf.Foss", "net", ns)
        assert result == ns

    def test_net_falls_back_to_pkg_when_no_canonical(self):
        result = _build_allow_prefixes("Aspose.Pdf.Foss", "net", set())
        assert result == {"Aspose.Pdf.Foss"}

    def test_python_unchanged(self):
        result = _build_allow_prefixes("aspose-pdf", "python", None)
        assert "aspose-pdf" in result
        assert "aspose_pdf" in result


class TestLoadCanonicalNamespaces:
    def test_loads_from_api_surface(self, knowledge_dir):
        ns = _load_canonical_namespaces("pdf", "net")
        assert ns == {"Aspose.Pdf", "Aspose.Pdf.Text", "Aspose.Pdf.Annotations", "Aspose.Pdf.Facades"}

    def test_returns_empty_when_missing(self):
        ns = _load_canonical_namespaces("nonexistent", "net")
        assert ns == set()


class TestNamespaceCorrectnessEvaluator:
    def setup_method(self):
        self.evaluator = NamespaceCorrectnessEvaluator()

    def test_nuget_package_id_flagged_as_invalid(self):
        """using Aspose.Pdf.Foss; should FAIL — it's the NuGet PackageId, not a namespace."""
        page = _make_page(textwrap.dedent("""\
            ---
            title: Test
            ---
            ```csharp
            using Aspose.Pdf.Foss;
            var doc = new Document();
            ```
        """), "content/docs.aspose.org/en/pdf/net/test.md")

        findings = self.evaluator.evaluate(page, None)
        fails = [f for f in findings if f.level == "FAIL"]
        assert len(fails) == 1
        assert "Aspose.Pdf.Foss" in fails[0].message

    def test_valid_namespace_passes(self):
        """using Aspose.Pdf; should PASS — it's a real source-code namespace."""
        page = _make_page(textwrap.dedent("""\
            ---
            title: Test
            ---
            ```csharp
            using Aspose.Pdf;
            using Aspose.Pdf.Text;
            var doc = new Document();
            ```
        """), "content/docs.aspose.org/en/pdf/net/test.md")

        findings = self.evaluator.evaluate(page, None)
        assert len(findings) == 0

    def test_proprietary_namespace_flagged(self):
        """using Aspose.Pdf.Enterprise; should FAIL — not in canonical namespaces."""
        page = _make_page(textwrap.dedent("""\
            ---
            title: Test
            ---
            ```csharp
            using Aspose.Pdf.Enterprise;
            ```
        """), "content/docs.aspose.org/en/pdf/net/test.md")

        findings = self.evaluator.evaluate(page, None)
        fails = [f for f in findings if f.level == "FAIL"]
        assert len(fails) == 1
        assert "Aspose.Pdf.Enterprise" in fails[0].message
