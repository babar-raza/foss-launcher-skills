"""Tests for scripts/ci/checks/check_install_recipe_safety_fails.py
(PKGINSTALL-GRADE-SAFETY-OVERRIDE stopgap).
"""
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_LIB_DIR = _REPO_ROOT / "scripts" / "pipeline" / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))
_CI_CHECKS_DIR = _REPO_ROOT / "scripts" / "ci" / "checks"
if str(_CI_CHECKS_DIR) not in sys.path:
    sys.path.insert(0, str(_CI_CHECKS_DIR))

import content_eval.evaluators.install_recipe as _ir_mod  # noqa: E402
import check_install_recipe_safety_fails as sut  # noqa: E402


_BARCODE_PYTHON_UNPUBLISHED = {
    "barcode": {"python": {
        "registry_type": "pypi",
        "candidate": {"name": "aspose-barcode-foss"},
        "candidate_owner": "asposefoss",
        "verification": {"published": False, "verified_at": "2026-08-01", "verified_owner": None,
                          "evidence_url": None, "method": None},
        "owner_match": None,
    }}
}


def _write_page(tmp_path: Path, rel_path: str, body: str) -> Path:
    path = tmp_path / "content" / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def teardown_function(_fn):
    _ir_mod.configure()


class TestCheckFiles:
    def test_no_files_given(self):
        assert sut.check_files([]) == []

    def test_clean_file_produces_no_findings(self, tmp_path):
        _ir_mod.configure(knowledge_root=tmp_path / "knowledge", registry=_BARCODE_PYTHON_UNPUBLISHED)
        path = _write_page(
            tmp_path, "docs.aspose.org/en/barcode/python/getting-started/installation.md",
            "---\ntitle: Installation\n---\n\n## Installation\n\ngit clone https://github.com/aspose-barcode-foss/example.git\n",
        )
        findings = sut.check_files([str(path)])
        assert findings == []

    def test_publish_claim_contradiction_is_caught_independent_of_grade(self, tmp_path):
        """The whole point of this stopgap: it never consults any stored
        grade at all -- it just re-runs the 2 real checks fresh."""
        _ir_mod.configure(knowledge_root=tmp_path / "knowledge", registry=_BARCODE_PYTHON_UNPUBLISHED)
        path = _write_page(
            tmp_path, "docs.aspose.org/en/barcode/python/getting-started/installation.md",
            "---\ntitle: Installation\ngrade: A\n---\n\n"
            "## Installation\n\nInstall from PyPI: `pip install aspose-barcode-foss`\n",
        )
        findings = sut.check_files([str(path)])
        assert len(findings) >= 1
        assert findings[0]["category"] == "IR_PUBLISH_CLAIM"

    def test_unpublished_disclosure_is_caught(self, tmp_path):
        _ir_mod.configure(knowledge_root=tmp_path / "knowledge", registry=_BARCODE_PYTHON_UNPUBLISHED)
        path = _write_page(
            tmp_path, "docs.aspose.org/en/barcode/python/getting-started/installation.md",
            "---\ntitle: Installation\n---\n\n"
            "## Installation\n\nAspose.BarCode FOSS for Python is not yet published on PyPI.\n",
        )
        findings = sut.check_files([str(path)])
        assert len(findings) >= 1
        assert findings[0]["category"] == "IR_UNPUBLISHED_DISCLOSURE"

    def test_install_accuracy_findings_are_never_included(self, tmp_path):
        """This stopgap only ever runs the 2 safety checks -- a wrong-
        package-name H-16 finding (category 'IR', untouched) must not
        appear here at all."""
        registry = {
            "3d": {"net": {
                "registry_type": "nuget",
                "candidate": {"name": "Aspose.3D.FOSS"},
                "candidate_owner": "asposefoss",
                "verification": {"published": True, "verified_at": None, "verified_owner": None,
                                  "evidence_url": None, "method": None},
                "owner_match": None,
            }}
        }
        _ir_mod.configure(knowledge_root=tmp_path / "knowledge", registry=registry)
        path = _write_page(
            tmp_path, "docs.aspose.org/en/3d/net/getting-started/installation.md",
            "---\ntitle: Installation\n---\n\n"
            "## Installation\n\n```\ndotnet add package Aspose.3D.Converter\n```\n",
        )
        findings = sut.check_files([str(path)])
        assert findings == [], f"H-16 accuracy findings (category IR) must never appear here: {findings}"


class TestMain:
    def test_no_files_exits_zero(self, capsys):
        assert sut.main([]) == 0

    def test_clean_files_exit_zero(self, tmp_path, capsys):
        _ir_mod.configure(knowledge_root=tmp_path / "knowledge", registry=_BARCODE_PYTHON_UNPUBLISHED)
        path = _write_page(
            tmp_path, "docs.aspose.org/en/barcode/python/getting-started/installation.md",
            "---\ntitle: Installation\n---\n\n## Installation\n\ngit clone https://example.com/repo.git\n",
        )
        assert sut.main([str(path)]) == 0

    def test_finding_exits_one_and_prints_to_stderr(self, tmp_path, capsys):
        _ir_mod.configure(knowledge_root=tmp_path / "knowledge", registry=_BARCODE_PYTHON_UNPUBLISHED)
        path = _write_page(
            tmp_path, "docs.aspose.org/en/barcode/python/getting-started/installation.md",
            "---\ntitle: Installation\n---\n\n## Installation\n\nInstall from PyPI: `pip install aspose-barcode-foss`\n",
        )
        exit_code = sut.main([str(path)])
        assert exit_code == 1
        captured = capsys.readouterr()
        assert "BLOCKED" in captured.err
        assert "IR_PUBLISH_CLAIM" in captured.err
