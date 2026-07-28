"""HARDEN-py-flat-package (MT013): _parse_python_manifest must detect a flat
(non-namespace) canonical_package from [tool.setuptools.packages.find].

Found live while launching pdf/python: the real pyproject.toml declares
`include = ["aspose_pdf", "aspose_pdf.*"]` (a flat top-level package -- PyPI
distribution name "aspose-pdf-foss-for-python" differs from the real import
name `aspose_pdf`). The original detection required a "." in the include
entry (designed only for namespace packages like "aspose.email_foss"), so it
silently skipped this ordinary case, leaving canonical_package unset and
falling through to a `name.replace("-", "_")` fallback that used the PyPI
name -- producing the literal generated text `import
aspose_pdf_foss_for_python`, which does not exist. The real repo's own
README confirms `from aspose_pdf import Document`.
"""
from __future__ import annotations

from pathlib import Path

from extraction.package_manifest import _parse_python_manifest


def _write_pyproject(tmp_path: Path, include: list[str], name: str = "aspose-pdf-foss-for-python") -> Path:
    include_toml = ", ".join(f'"{i}"' for i in include)
    (tmp_path / "pyproject.toml").write_text(
        f"""
[project]
name = "{name}"
version = "0.1.0"

[tool.setuptools.packages.find]
where = ["src"]
include = [{include_toml}]
exclude = ["tests*"]
""",
        encoding="utf-8",
    )
    return tmp_path


class TestFlatPackageDetection:
    def test_flat_package_name_detected(self, tmp_path):
        _write_pyproject(tmp_path, ["aspose_pdf", "aspose_pdf.*"])
        info = _parse_python_manifest(tmp_path)
        assert info["canonical_package"] == "aspose_pdf"

    def test_namespace_package_still_detected(self, tmp_path):
        """Regression guard: the original namespace-package case (dotted
        include entry) must keep working exactly as before."""
        _write_pyproject(tmp_path, ["aspose.email_foss", "aspose.email_foss.*"],
                          name="aspose-email-foss")
        info = _parse_python_manifest(tmp_path)
        assert info["canonical_package"] == "aspose.email_foss"

    def test_wildcard_only_entries_do_not_set_canonical_package(self, tmp_path):
        _write_pyproject(tmp_path, ["aspose_pdf.*"])
        info = _parse_python_manifest(tmp_path)
        assert "canonical_package" not in info

    def test_no_setuptools_find_section_no_canonical_package(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "some-package"\nversion = "0.1.0"\n',
            encoding="utf-8",
        )
        info = _parse_python_manifest(tmp_path)
        assert "canonical_package" not in info
        assert info["name"] == "some-package"
