"""Tests for namespace_correctness evaluator v2.

Covers:
  - C# canonical namespace support (NuGet PackageId vs source-code namespace)
  - Python underscore-prefix packages (aspose_font) correctly allowed
  - Python dot-prefix proprietary imports flagged as FAIL
  - package_name missing → graceful skip (no findings)
  - TypeScript ES6 and CommonJS imports flagged and allowed
  - _build_allow_prefixes normalization for Python, TypeScript, C#
  - _is_allowed path separator handling (dot, ::, /)
"""

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
    _is_allowed,
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


def _make_platform_page(family: str, platform: str, code: str,
                        subdomain: str = "kb") -> Page:
    """Create a synthetic page with a single fenced code block for any platform."""
    lang = {"python": "python", "typescript": "typescript",
            "javascript": "javascript"}.get(platform, platform)
    raw = textwrap.dedent(f"""\
        ---
        title: "Test {family}/{platform}"
        ---

        Example:

        ```{lang}
        {code}
        ```
    """)
    return _make_page(raw, f"content/{subdomain}.aspose.org/en/{family}/{platform}/test.md")


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

    def test_python_hyphen_pkg_adds_underscore(self):
        result = _build_allow_prefixes("aspose-font", "python", None)
        assert "aspose_font" in result
        assert "aspose-font" in result

    def test_python_already_underscore_pkg(self):
        result = _build_allow_prefixes("aspose_slides_foss", "python", None)
        assert "aspose_slides_foss" in result

    def test_empty_pkg_returns_empty_set(self):
        assert _build_allow_prefixes("", "python", None) == set()

    def test_typescript_scoped_pkg(self):
        prefixes = _build_allow_prefixes("@aspose/3d", "typescript", None)
        assert "@aspose/3d" in prefixes


class TestIsAllowed:
    def test_exact_root_match(self):
        assert _is_allowed("aspose_font", {"aspose_font"})

    def test_dot_submodule_allowed(self):
        assert _is_allowed("aspose_font.font_types", {"aspose_font"})

    def test_npm_slash_subpath_allowed(self):
        assert _is_allowed("@aspose/3d/extras", {"@aspose/3d"})

    def test_wrong_package_not_allowed(self):
        assert not _is_allowed("aspose.font", {"aspose_font"})

    def test_different_package_not_allowed(self):
        assert not _is_allowed("aspose_slides", {"aspose_font"})

    def test_exact_only_rejects_prefix_match(self):
        assert not _is_allowed("Aspose.Pdf.Foss", {"Aspose.Pdf"}, exact_only=True)

    def test_exact_only_accepts_exact(self):
        assert _is_allowed("Aspose.Pdf", {"Aspose.Pdf"}, exact_only=True)


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


# ---------------------------------------------------------------------------
# Python evaluator tests (ported from v1 — configure() seam, no patch())
# ---------------------------------------------------------------------------

class TestPythonNamespaceCorrectness:
    """Tests for Python import detection using configure() seam."""

    @pytest.fixture(autouse=True)
    def _setup_font_python(self, tmp_path):
        """Create font/python knowledge dir with FOSS package name."""
        merged = tmp_path / "font" / "python" / "merged"
        merged.mkdir(parents=True)
        model = {"package_name": "aspose-font", "family": "font", "platform": "python"}
        (merged / "model.yaml").write_text(yaml.dump(model), encoding="utf-8")
        (merged / "api_surface.json").write_text("[]", encoding="utf-8")
        configure(knowledge_root=tmp_path)
        yield
        configure()

    def test_proprietary_dot_import_emits_fail(self):
        """from aspose.font import X is a proprietary namespace -> FAIL."""
        evaluator = NamespaceCorrectnessEvaluator()
        page = _make_platform_page("font", "python", "from aspose.font import Font")
        findings = evaluator.evaluate(page, None)
        fails = [f for f in findings if f.level == "FAIL"]
        assert fails, "Expected FAIL for proprietary aspose.font import"

    def test_correct_underscore_root_import_passes(self):
        """from aspose_font import FontType is the correct FOSS import -> no FAIL."""
        evaluator = NamespaceCorrectnessEvaluator()
        page = _make_platform_page("font", "python", "from aspose_font import FontType")
        findings = evaluator.evaluate(page, None)
        fails = [f for f in findings if f.level == "FAIL"]
        assert not fails, f"Unexpected FAIL for correct FOSS import: {findings}"

    def test_submodule_from_correct_root_does_not_fail(self):
        """from aspose_font.font_types import X — correct FOSS root -> no FAIL."""
        evaluator = NamespaceCorrectnessEvaluator()
        page = _make_platform_page("font", "python",
                                   "from aspose_font.font_types import FontType")
        findings = evaluator.evaluate(page, None)
        fails = [f for f in findings if f.level == "FAIL"]
        assert not fails, f"Unexpected FAIL for FOSS root submodule: {findings}"


class TestPythonMissingPackageName:
    """Test graceful skip when package_name is missing."""

    @pytest.fixture(autouse=True)
    def _setup_empty_model(self, tmp_path):
        merged = tmp_path / "font" / "python" / "merged"
        merged.mkdir(parents=True)
        model = {"family": "font", "platform": "python"}  # no package_name
        (merged / "model.yaml").write_text(yaml.dump(model), encoding="utf-8")
        (merged / "api_surface.json").write_text("[]", encoding="utf-8")
        configure(knowledge_root=tmp_path)
        yield
        configure()

    def test_missing_package_name_skips_gracefully(self):
        """No package_name -> evaluator skips (no findings, no error)."""
        evaluator = NamespaceCorrectnessEvaluator()
        page = _make_platform_page("font", "python",
                                   "from aspose_font.font_types import FontType")
        findings = evaluator.evaluate(page, None)
        assert findings == [], f"Expected [] when package_name missing, got {findings}"


# ---------------------------------------------------------------------------
# TypeScript evaluator tests (ported from v1 — configure() seam, no patch())
# ---------------------------------------------------------------------------

class TestTypeScriptNamespaceCorrectness:
    """Tests for TypeScript/ES6 import detection."""

    @pytest.fixture(autouse=True)
    def _setup_3d_typescript(self, tmp_path):
        merged = tmp_path / "3d" / "typescript" / "merged"
        merged.mkdir(parents=True)
        model = {"package_name": "@aspose/3d", "family": "3d", "platform": "typescript"}
        (merged / "model.yaml").write_text(yaml.dump(model), encoding="utf-8")
        (merged / "api_surface.json").write_text("[]", encoding="utf-8")
        configure(knowledge_root=tmp_path)
        yield
        configure()

    def test_es6_import_from_scoped_pkg_passes(self):
        """import { Foo } from '@aspose/3d' — correct FOSS package -> no FAIL."""
        evaluator = NamespaceCorrectnessEvaluator()
        page = _make_platform_page("3d", "typescript",
                                   "import { Scene } from '@aspose/3d';")
        findings = evaluator.evaluate(page, None)
        fails = [f for f in findings if f.level == "FAIL"]
        assert not fails, f"Unexpected FAIL for correct TS FOSS import: {findings}"

    def test_wrong_scoped_pkg_emits_fail(self):
        """import { Foo } from '@aspose/wrong' when package is @aspose/3d -> FAIL."""
        evaluator = NamespaceCorrectnessEvaluator()
        page = _make_platform_page("3d", "typescript",
                                   "import { Scene } from '@aspose/wrong';")
        findings = evaluator.evaluate(page, None)
        fails = [f for f in findings if f.level == "FAIL"]
        assert fails, "Expected FAIL for wrong scoped package import"


class TestTypeScriptMissingPackageName:
    """Test graceful skip for TypeScript when package_name missing."""

    @pytest.fixture(autouse=True)
    def _setup_empty_ts_model(self, tmp_path):
        merged = tmp_path / "3d" / "typescript" / "merged"
        merged.mkdir(parents=True)
        model = {"family": "3d", "platform": "typescript"}
        (merged / "model.yaml").write_text(yaml.dump(model), encoding="utf-8")
        (merged / "api_surface.json").write_text("[]", encoding="utf-8")
        configure(knowledge_root=tmp_path)
        yield
        configure()

    def test_missing_ts_package_name_skips_gracefully(self):
        """No package_name -> TypeScript evaluator skips with no findings."""
        evaluator = NamespaceCorrectnessEvaluator()
        page = _make_platform_page("3d", "typescript",
                                   "import { Scene } from '@aspose/3d';")
        findings = evaluator.evaluate(page, None)
        assert findings == [], f"Expected [] when package_name missing, got {findings}"
