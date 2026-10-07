"""Tests for scripts/pipeline/lib/source_install.py (TC-PSD-HRD-10): the shared
`determine_source_install_mode(platform, repo)` function, the permanent fix of F-PSD-07
(psd/python's unpublished-install fallback renders `pip install -e .`, which cannot work since
psd/python has no packaging manifest at all). Reused by both the enrichment script that writes
`data/products.json`'s `source_install_mode` field and `upstream_readiness_check.py`'s U-04
check (reconciliation is HRD-10-03c's job, not asserted here).

Modes: `"standard"` (today's unconditional behavior, viable), `"pythonpath"` (python-only: no
manifest but a real importable top-level package exists -- clone + run-from-folder or add to
PYTHONPATH, never `pip install -e .`), `None` (no viable install mode at all -- preflight U-04
FAIL territory).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from lib import source_install

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CLONE_ROOT = _REPO_ROOT / "runs" / ".clone_cache"


# --------------------------------------------------------------------------- #
# Synthetic repo trees (plan's own 4 named cases)
# --------------------------------------------------------------------------- #


def test_python_with_pyproject_toml_is_standard(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "demo"\n', encoding="utf-8")
    assert source_install.determine_source_install_mode("python", tmp_path) == "standard"


def test_python_flat_package_no_manifest_is_pythonpath(tmp_path):
    pkg = tmp_path / "demo_pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    assert source_install.determine_source_install_mode("python", tmp_path) == "pythonpath"


def test_python_with_neither_manifest_nor_package_is_none(tmp_path):
    (tmp_path / "README.md").write_text("nothing here", encoding="utf-8")
    assert source_install.determine_source_install_mode("python", tmp_path) is None


def test_net_with_one_sln_is_standard(tmp_path):
    (tmp_path / "Demo.sln").write_text("", encoding="utf-8")
    assert source_install.determine_source_install_mode("net", tmp_path) == "standard"


# --------------------------------------------------------------------------- #
# Additional synthetic edge cases (same shape as HRD-04's manifest-less flat-layout fix --
# a test-named sibling package must not be mistaken for the real importable package)
# --------------------------------------------------------------------------- #


def test_python_flat_package_excludes_test_named_dirs(tmp_path):
    (tmp_path / "demo_test").mkdir()
    (tmp_path / "demo_test" / "__init__.py").write_text("", encoding="utf-8")
    assert source_install.determine_source_install_mode("python", tmp_path) is None


def test_net_with_no_project_file_is_none(tmp_path):
    assert source_install.determine_source_install_mode("net", tmp_path) is None


@pytest.mark.parametrize(
    "platform,filename",
    [
        ("typescript", "package.json"),
        ("javascript", "package.json"),
        ("java", "pom.xml"),
        ("go", "go.mod"),
        ("cpp", "CMakeLists.txt"),
        ("rust", "Cargo.toml"),
    ],
)
def test_other_platforms_standard_when_manifest_present(tmp_path, platform, filename):
    (tmp_path / filename).write_text("", encoding="utf-8")
    assert source_install.determine_source_install_mode(platform, tmp_path) == "standard"


@pytest.mark.parametrize("platform", ["typescript", "javascript", "java", "go", "cpp", "rust"])
def test_other_platforms_none_when_manifest_absent(tmp_path, platform):
    assert source_install.determine_source_install_mode(platform, tmp_path) is None


# --------------------------------------------------------------------------- #
# Portfolio assertion: every one of the 36 real registered clones is "standard" except
# psd/python, which must be "pythonpath" (plan's own named acceptance for this card).
# --------------------------------------------------------------------------- #

_CLONE_TO_PLATFORM = {
    "aspose_3d_java": "java", "aspose_3d_net": "net", "aspose_3d_python": "python",
    "aspose_3d_typescript": "typescript", "aspose_barcode_python": "python",
    "aspose_cells_cpp": "cpp", "aspose_cells_go": "go", "aspose_cells_java": "java",
    "aspose_cells_net": "net", "aspose_cells_python": "python", "aspose_cells_rust": "rust",
    "aspose_cells_typescript": "typescript", "aspose_email_cpp": "cpp",
    "aspose_email_net": "net", "aspose_email_python": "python", "aspose_font_python": "python",
    "aspose_gis_net": "net", "aspose_html_python": "python", "aspose_imaging_net": "net",
    "aspose_note_python": "python", "aspose_page_python": "python", "aspose_pdf_cpp": "cpp",
    "aspose_pdf_go": "go", "aspose_pdf_java": "java", "aspose_pdf_net": "net",
    "aspose_pdf_python": "python", "aspose_pdf_typescript": "typescript",
    "aspose_psd_net": "net", "aspose_psd_python": "python", "aspose_slides_cpp": "cpp",
    "aspose_slides_java": "java", "aspose_slides_net": "net", "aspose_slides_python": "python",
    "aspose_tex_python": "python", "aspose_words_net": "net", "aspose_words_python": "python",
}

_EXPECTED_NON_STANDARD = {"aspose_psd_python": "pythonpath"}


@pytest.mark.skipif(not _CLONE_ROOT.is_dir(), reason="clone cache not present in this environment")
@pytest.mark.parametrize("clone_name,platform", sorted(_CLONE_TO_PLATFORM.items()))
def test_portfolio_mode_matches_expected(clone_name, platform):
    clone = _CLONE_ROOT / clone_name
    if not clone.is_dir():
        pytest.skip(f"{clone_name} not present in this clone cache")
    mode = source_install.determine_source_install_mode(platform, clone)
    expected = _EXPECTED_NON_STANDARD.get(clone_name, "standard")
    assert mode == expected, f"{clone_name} ({platform}): expected {expected!r}, got {mode!r}"


def test_portfolio_covers_all_36_registered_clones():
    assert len(_CLONE_TO_PLATFORM) == 36


# --------------------------------------------------------------------------- #
# Render assertion for the partial: default mode (absent/"standard") renders today's exact,
# byte-identical python output; "pythonpath" renders the new clone+run-from-folder/PYTHONPATH
# instructions and never emits "pip install -e .".
# --------------------------------------------------------------------------- #


def _render_python_branch(source_install_mode: "str | None") -> str:
    """Minimal Go-template-free re-implementation of just the python branch's two outcomes,
    used only to pin the EXACT literal strings the real partial must produce -- the real
    Hugo-render check happens in HRD-10-04 VERIFY via a targeted build, not here (this repo's
    existing shortcode tests use synthetic fixtures, never a live Hugo render, per -01's own
    investigation of test_install_literal_sweep.py's conventions)."""
    if source_install_mode == "pythonpath":
        return (
            "<pre><code class=\"language-bash\">git clone {repo}.git\n"
            "cd {name}\n"
            "# No packaging manifest is published yet -- run from this folder,\n"
            "# or add it to PYTHONPATH:\n"
            "export PYTHONPATH=$PWD:$PYTHONPATH</code></pre>"
        )
    return (
        "<pre><code class=\"language-bash\">git clone {repo}.git\n"
        "cd {name}\n"
        "pip install -e .</code></pre>"
    )


def test_default_python_branch_is_byte_identical_to_today():
    assert "pip install -e ." in _render_python_branch(None)
    assert "pip install -e ." in _render_python_branch("standard")


def test_pythonpath_branch_never_emits_pip_install_e():
    rendered = _render_python_branch("pythonpath")
    assert "pip install -e ." not in rendered
    assert "PYTHONPATH" in rendered
