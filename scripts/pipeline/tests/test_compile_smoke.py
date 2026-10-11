"""Tests for compile_smoke.py (TC-PSD-HRD-02): a real per-platform compile/import smoke against
a product's actual clone -- the gap tree-sitter's lenient parser can't see (HRD-02: gis/net held
at 320 real compile errors invisible to extraction). `net` and `python` get a real implementation;
every other declared platform returns an honest NOT_RUN (out of this card's scope).

Positive fixture: psd/net's real clone (`runs/.clone_cache/aspose_psd_net`) -- expect PASS.
Negative fixtures: a synthetic broken C# project and a synthetic broken Python package -- expect
FAIL. A synthetic valid Python package proves the PASS path doesn't depend on the real clone
being reachable.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from commands.launch import compile_smoke  # noqa: E402
from commands.launch.upstream_readiness_check import FAIL, NOT_RUN, PASS, WARN  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PSD_NET_CLONE = _REPO_ROOT / "runs" / ".clone_cache" / "aspose_psd_net"

_HAS_DOTNET = shutil.which("dotnet") is not None


def test_declared_platform_list_matches_yaml():
    """compile_smoke only special-cases platforms it actually implements; every OTHER declared
    platform must still return a Result (NOT_RUN), never raise."""
    for platform in ("java", "cpp", "go", "rust", "typescript"):
        result = compile_smoke.compile_smoke(platform, Path("/does/not/exist"))
        assert result.check_id == "U-07"
        assert result.status == NOT_RUN


def test_unknown_platform_not_in_yaml_is_not_run():
    result = compile_smoke.compile_smoke("cobol", Path("/does/not/exist"))
    assert result.status == NOT_RUN
    assert "not declared" in result.detail


# --------------------------------------------------------------------------- #
# net
# --------------------------------------------------------------------------- #


@pytest.mark.skipif(not _HAS_DOTNET, reason="dotnet not on PATH in this environment")
@pytest.mark.skipif(not _PSD_NET_CLONE.is_dir(), reason="psd/net clone cache not present")
def test_psd_net_real_clone_compiles(tmp_path):
    """Real repro per plan §H.7 HRD-02 row: psd/net (expect PASS)."""
    result = compile_smoke.compile_smoke("net", _PSD_NET_CLONE)
    assert result.check_id == "U-07"
    assert result.status == PASS, result.detail


@pytest.mark.skipif(not _HAS_DOTNET, reason="dotnet not on PATH in this environment")
@pytest.mark.skipif(not _PSD_NET_CLONE.is_dir(), reason="psd/net clone cache not present")
def test_psd_net_build_leaves_no_bin_or_obj_in_the_shared_clone_cache(tmp_path):
    """Regression (found live building this card): a first draft redirected only
    BaseIntermediateOutputPath, and `dotnet build` still created a real `bin/Debug/` directory
    inside the shared, read-only clone cache -- an uncoordinated mutation of a resource other
    sessions may be reading concurrently. Both BaseOutputPath and BaseIntermediateOutputPath
    must be redirected to a scratch dir."""
    from extraction.package_root import detect_package_root

    root = detect_package_root(_PSD_NET_CLONE, "net")
    before = {p for p in root.glob("*") if p.name.lower() in ("bin", "obj")}
    result = compile_smoke.compile_smoke("net", _PSD_NET_CLONE)
    after = {p for p in root.glob("*") if p.name.lower() in ("bin", "obj")}
    assert after == before, f"compile_smoke left stray build artifacts in the clone cache: {after - before}"
    assert result.status == PASS, result.detail


@pytest.mark.skipif(not _HAS_DOTNET, reason="dotnet not on PATH in this environment")
def test_synthetic_broken_csharp_fails(tmp_path):
    """Real repro per plan §H.7 HRD-02 row: a synthetic broken C# fixture (expect FAIL)."""
    proj = tmp_path / "Broken.csproj"
    proj.write_text(
        '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>'
        "<TargetFramework>net8.0</TargetFramework>"
        "</PropertyGroup></Project>",
        encoding="utf-8",
    )
    (tmp_path / "Broken.cs").write_text(
        "namespace Broken { public class Widget { public void Oops( { } } }\n",
        encoding="utf-8",
    )
    result = compile_smoke.compile_smoke("net", tmp_path)
    assert result.status == FAIL, result.detail


def test_net_no_csproj_is_fail(tmp_path):
    result = compile_smoke.compile_smoke("net", tmp_path)
    assert result.status == FAIL
    assert "csproj" in result.detail.lower()


def test_net_dotnet_missing_is_warn(tmp_path, monkeypatch):
    monkeypatch.setattr(compile_smoke.shutil, "which", lambda _exe: None)
    (tmp_path / "Widget.csproj").write_text(
        '<Project Sdk="Microsoft.NET.Sdk"></Project>', encoding="utf-8",
    )
    result = compile_smoke.compile_smoke("net", tmp_path)
    assert result.status == WARN
    assert "dotnet" in result.detail.lower()


# --------------------------------------------------------------------------- #
# python
# --------------------------------------------------------------------------- #


def test_synthetic_valid_python_package_passes(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "demo"\n', encoding="utf-8")
    pkg = tmp_path / "demo_pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("VALUE = 1\n", encoding="utf-8")
    result = compile_smoke.compile_smoke("python", tmp_path)
    assert result.status == PASS, result.detail
    assert "demo_pkg" in result.detail


def test_synthetic_broken_python_package_fails(tmp_path):
    """Real repro per plan §H.7 HRD-02 row: a synthetic broken Python fixture (expect FAIL)."""
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "demo"\n', encoding="utf-8")
    pkg = tmp_path / "demo_pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("def broken(:\n    pass\n", encoding="utf-8")
    result = compile_smoke.compile_smoke("python", tmp_path)
    assert result.status == FAIL, result.detail


def test_python_no_importable_package_is_warn(tmp_path):
    result = compile_smoke.compile_smoke("python", tmp_path)
    assert result.status == WARN


def test_python_token_like_env_vars_are_scrubbed(monkeypatch, tmp_path):
    """Hard rule: third-party code (the clone's own __init__.py) must never see a token-like
    env var. Proven by asserting the scrubbed env dict passed to the real subprocess call omits
    one, not by a mocked runner (configure() is reserved for the offline unit tests above; this
    one exercises the real _scrubbed_env() helper directly)."""
    monkeypatch.setenv("GH_TOKEN", "should-not-be-visible")
    monkeypatch.setenv("GITHUB_PAT", "also-should-not-be-visible")
    env = compile_smoke._scrubbed_env()
    assert "GH_TOKEN" not in env
    assert "GITHUB_PAT" not in env
