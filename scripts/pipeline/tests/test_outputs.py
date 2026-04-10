"""Tests for extraction/outputs.py — artifact generation helpers.

Covers:
- _canonical_import: all platforms (python, net, dotnet, java, typescript)
- python branch: bare name, hyphenated name, empty name
- python namespace package branch: canonical_package takes priority over name-based inference
- net/dotnet branch: name, empty
- java branch: group_id + artifact_id present/missing
- typescript branch: name, empty
- unknown platform: returns empty string
"""

import pytest

# conftest.py adds scripts/pipeline/ to sys.path
from extraction.outputs import _canonical_import


# ---------------------------------------------------------------------------
# _canonical_import
# ---------------------------------------------------------------------------

class TestCanonicalImport:

    # --- Python ---

    def test_python_bare_name(self):
        result = _canonical_import("python", {"name": "aspose_slides_foss"})
        assert result == "import aspose_slides_foss"

    def test_python_hyphenated_name_normalised(self):
        result = _canonical_import("python", {"name": "aspose-slides-foss"})
        assert result == "import aspose_slides_foss"

    def test_python_result_is_valid_import_statement(self):
        result = _canonical_import("python", {"name": "aspose-3d-foss"})
        assert result.startswith("import ")

    def test_python_empty_name_returns_empty(self):
        result = _canonical_import("python", {"name": ""})
        assert result == ""

    def test_python_missing_name_key_returns_empty(self):
        result = _canonical_import("python", {})
        assert result == ""

    def test_python_canonical_package_overrides_name_inference(self):
        # Namespace packages (e.g. aspose/email_foss/) have a dotted import path
        # that differs from the PyPI package name.  canonical_package, set by
        # package_manifest.py when pyproject.toml carries [tool.setuptools.packages.find],
        # must take priority over the hyphen→underscore name fallback.
        result = _canonical_import("python", {
            "name": "aspose-email-foss",
            "canonical_package": "aspose.email_foss",
        })
        assert result == "import aspose.email_foss"

    def test_python_canonical_package_used_even_without_name(self):
        result = _canonical_import("python", {
            "canonical_package": "aspose.slides_foss",
        })
        assert result == "import aspose.slides_foss"

    def test_python_canonical_package_empty_falls_back_to_name(self):
        # Empty string canonical_package should fall back to name-based inference.
        result = _canonical_import("python", {
            "name": "aspose-slides-foss",
            "canonical_package": "",
        })
        assert result == "import aspose_slides_foss"

    # --- .NET ---

    def test_net_returns_using_statement(self):
        result = _canonical_import("net", {"name": "Aspose.Slides.Foss"})
        assert result == "using Aspose.Slides.Foss;"

    def test_dotnet_alias_returns_using_statement(self):
        result = _canonical_import("dotnet", {"name": "Aspose.Slides.Foss"})
        assert result == "using Aspose.Slides.Foss;"

    def test_net_empty_name_returns_empty(self):
        result = _canonical_import("net", {"name": ""})
        assert result == ""

    # --- Java ---

    def test_java_with_packages_uses_common_prefix(self):
        # Prefer actual extracted packages (valid Java identifiers) over group_id.artifact_id
        result = _canonical_import("java", {
            "group_id": "org.aspose.slides.foss",
            "artifact_id": "aspose-slides-foss",
        }, packages={"org.aspose.slides.foss", "org.aspose.slides.foss.drawing"})
        assert result == "import org.aspose.slides.foss.*;"

    def test_java_without_packages_falls_back_to_group_id(self):
        # Without packages, fall back to group_id (artifact_id may contain hyphens)
        result = _canonical_import("java", {
            "group_id": "org.aspose",
            "artifact_id": "aspose-slides-foss",
        })
        assert result == "import org.aspose.*;"

    def test_java_missing_group_id_returns_empty(self):
        result = _canonical_import("java", {"artifact_id": "aspose-slides-foss"})
        assert result == ""

    def test_java_missing_artifact_id_falls_back_to_group_id(self):
        # artifact_id is no longer required; group_id alone is the fallback
        result = _canonical_import("java", {"group_id": "org.aspose"})
        assert result == "import org.aspose.*;"

    def test_java_empty_manifest_returns_empty(self):
        result = _canonical_import("java", {})
        assert result == ""

    # --- TypeScript ---

    def test_typescript_returns_import_from(self):
        result = _canonical_import("typescript", {"name": "@aspose/slides-foss"})
        assert result == 'import { ... } from "@aspose/slides-foss";'

    def test_typescript_empty_name_returns_empty(self):
        result = _canonical_import("typescript", {"name": ""})
        assert result == ""

    def test_javascript_alias_works(self):
        result = _canonical_import("javascript", {"name": "my-lib"})
        assert result == 'import { ... } from "my-lib";'

    # --- Unknown / C++ ---

    def test_cpp_returns_empty(self):
        result = _canonical_import("cpp", {"name": "aspose-slides-foss"})
        assert result == ""

    def test_unknown_platform_returns_empty(self):
        result = _canonical_import("unknown_platform", {"name": "whatever"})
        assert result == ""
