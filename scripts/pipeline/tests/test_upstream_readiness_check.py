"""HRD-01 (MT076-2026-10-07-PSD-NET-PYTHON-LAUNCH): upstream_readiness_check.py.

The family-first launch preconditions (upstream LICENSE, real merged source, a source-install
command that can work, ...) used to live only in backlog prose (INV-014/INV-015). These tests
pin the machine version, including the negative controls that prove the gate bites, and NC-13
(the real-portfolio license-check acceptance): U-01 must be file-first, never API-only (F-PSD-15
-- an API-only check false-fails 5 already-launched `cells/*` products whose LICENSE file GitHub's
API does not recognize).
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from commands.launch import upstream_readiness_check as urc


@pytest.fixture(autouse=True)
def _reset_configure():
    yield
    urc.configure()  # restore defaults after every test


def _proc(out="", rc=0):
    return SimpleNamespace(stdout=out, stderr="", returncode=rc)


def _make_repo(tmp_path, *, family="psd", platform="python", published=None, files=(),
               license_file=None, overrides_license=None, spdx_out="MIT",
               head="aaaa1111", remote="aaaa1111", hooks=False, family_page=None):
    root = tmp_path / "repo"
    (root / "data").mkdir(parents=True)
    product = {"family": family, "platform": platform,
               "repo_url": f"https://github.com/aspose-{family}-foss/Aspose.{family.upper()}-FOSS-for-X"}
    if overrides_license:
        product["overrides"] = {"license": overrides_license}
    (root / "data" / "products.json").write_text(json.dumps([product]), encoding="utf-8")
    reg = {} if published is None else {family: {platform: {"verification": {"published": published}}}}
    (root / "data" / "package_registry.json").write_text(json.dumps(reg), encoding="utf-8")
    clone = root / "runs" / ".clone_cache" / f"aspose_{family}_{platform}"
    clone.mkdir(parents=True)
    for rel in files:
        p = clone / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x\n", encoding="utf-8")
    if license_file:
        (clone / license_file).write_text("MIT License\n", encoding="utf-8")
    if hooks:
        (root / ".git" / "hooks").mkdir(parents=True)
        (root / ".git" / "hooks" / "pre-commit").write_text("#!/bin/sh\n", encoding="utf-8")
    if family_page is not None:
        pg = root / "content" / "products.aspose.org" / "en" / family
        pg.mkdir(parents=True)
        (pg / "_index.md").write_text(family_page, encoding="utf-8")

    def runner(cmd, *, cwd=None, timeout=None):
        if cmd[:2] == ["gh", "api"] and cmd[-1] == ".license.spdx_id":
            return _proc(spdx_out if spdx_out is not None else "null")
        if cmd[:2] == ["gh", "api"] and cmd[-1] == ".sha":
            return _proc(remote)
        if "rev-parse" in cmd:
            return _proc(head)
        return _proc("", 1)

    urc.configure(runner=runner, repo_root=root)
    return root


PY_SRC = ["pkg/a.py", "pkg/b.py", "pkg/c.py"]


# ---------------------------------------------------------------------------
# U-01: file-first license detection (R1/R2, F-PSD-15)
# ---------------------------------------------------------------------------

def test_no_license_file_warns_not_fails(tmp_path):
    """The exact MT076 case: psd/net and psd/python have no LICENSE file. Must WARN, never FAIL,
    and must not fail the gate even without --strict (owner decision: not a launch blocker)."""
    _make_repo(tmp_path, files=PY_SRC + ["pyproject.toml"], license_file=None, spdx_out="null")
    results = urc.run_checks("psd", "python")
    res = {r.check_id: r for r in results}
    assert res["U-01"].status == urc.WARN
    assert "MISCONFIGURED_NO_LICENSE_FILE" in res["U-01"].detail
    assert res["U-01"].license_link_allowed is False
    assert urc.verdict(results) == 0  # WARN alone never fails the gate (non-strict)


def test_license_file_present_passes_even_when_api_says_null(tmp_path):
    """F-PSD-15: the 5 cells/* repos have a LICENSE file GitHub's API does not recognize. A
    file-backed PASS must never depend on the API agreeing."""
    _make_repo(tmp_path, files=PY_SRC, license_file="LICENSE", spdx_out="null")
    res = {r.check_id: r for r in urc.run_checks("psd", "python")}["U-01"]
    assert res.status == urc.PASS
    assert res.license_link_allowed is True
    assert "not recognized" in res.detail


def test_license_file_present_and_api_recognizes_it(tmp_path):
    _make_repo(tmp_path, files=PY_SRC, license_file="LICENSE", spdx_out="MIT")
    res = {r.check_id: r for r in urc.run_checks("psd", "python")}["U-01"]
    assert res.status == urc.PASS
    assert "MIT" in res.detail


@pytest.mark.parametrize("name", ["LICENSE", "LICENSE.txt", "LICENSE.md", "COPYING", "UNLICENSE.md"])
def test_license_file_name_variants_all_detected(tmp_path, name):
    _make_repo(tmp_path, files=PY_SRC, license_file=name, spdx_out="null")
    assert {r.check_id: r for r in urc.run_checks("psd", "python")}["U-01"].status == urc.PASS


def test_license_nested_under_a_license_directory_is_detected(tmp_path):
    """Found live in all 5 cells/* repos (java, net, python, cpp, go... go has it at root, the
    other 4 nest it): a root-level `License/` directory holding `LICENSE.txt`, not a root-level
    file. GitHub's license API does not detect it there either -- matches the measured API-null
    result -- but it is real, on-disk license text and must PASS, not WARN."""
    root = _make_repo(tmp_path, files=PY_SRC, license_file=None, spdx_out="null")
    clone = root / "runs" / ".clone_cache" / "aspose_psd_python"
    (clone / "License").mkdir()
    (clone / "License" / "LICENSE.txt").write_text("MIT License\n", encoding="utf-8")
    res = {r.check_id: r for r in urc.run_checks("psd", "python")}["U-01"]
    assert res.status == urc.PASS
    assert res.license_link_allowed is True


def test_a_directory_unrelated_to_licensing_is_not_mistaken_for_one(tmp_path):
    root = _make_repo(tmp_path, files=PY_SRC, license_file=None, spdx_out="null")
    clone = root / "runs" / ".clone_cache" / "aspose_psd_python"
    (clone / "License").mkdir()
    (clone / "License" / "readme.md").write_text("not a license\n", encoding="utf-8")
    res = {r.check_id: r for r in urc.run_checks("psd", "python")}["U-01"]
    assert res.status == urc.WARN  # the directory exists but holds no license-named file inside it


def test_gh_api_failure_does_not_downgrade_a_file_backed_pass(tmp_path):
    root = _make_repo(tmp_path, files=PY_SRC, license_file="LICENSE")
    urc.configure(runner=lambda cmd, **k: _proc("", 1), repo_root=root)
    res = {r.check_id: r for r in urc.run_checks("psd", "python")}["U-01"]
    assert res.status == urc.PASS  # API failure is best-effort only; the file already decided PASS


def test_owner_attestation_carried_without_a_file(tmp_path):
    """psd/net and psd/python will eventually carry overrides.license: MIT (REG-01-03/REG-02-03,
    not this card) even with no upstream file -- the attestation must still surface."""
    _make_repo(tmp_path, files=PY_SRC, license_file=None, overrides_license="MIT")
    res = {r.check_id: r for r in urc.run_checks("psd", "python")}["U-01"]
    assert res.status == urc.WARN
    assert res.license_statement == "MIT"
    assert res.license_link_allowed is False


def test_no_file_and_no_attestation_has_no_license_statement(tmp_path):
    _make_repo(tmp_path, files=PY_SRC, license_file=None, overrides_license=None)
    res = {r.check_id: r for r in urc.run_checks("psd", "python")}["U-01"]
    assert res.license_statement is None


# ---------------------------------------------------------------------------
# U-02..U-07 (unchanged design; re-pinned against the real module)
# ---------------------------------------------------------------------------

def test_source_stub_fails(tmp_path):
    _make_repo(tmp_path, files=["README.md"])
    assert {r.check_id: r for r in urc.run_checks("psd", "python")}["U-02"].status == urc.FAIL


def test_source_only_in_test_directory_does_not_count(tmp_path):
    _make_repo(tmp_path, files=["pkg_test/a.py", "pkg_test/b.py", "pkg_test/c.py", "tests/d.py"])
    assert {r.check_id: r for r in urc.run_checks("psd", "python")}["U-02"].status == urc.FAIL


def test_f_psd_07_unpublished_python_without_manifest_fails(tmp_path):
    _make_repo(tmp_path, files=PY_SRC, published=False)
    r = {x.check_id: x for x in urc.run_checks("psd", "python")}["U-04"]
    assert r.status == urc.FAIL and "cannot work" in r.detail


def test_published_package_does_not_need_a_source_install_manifest(tmp_path):
    _make_repo(tmp_path, files=PY_SRC, published=True)
    assert {x.check_id: x for x in urc.run_checks("psd", "python")}["U-04"].status == urc.PASS


def test_unpublished_python_with_pyproject_passes(tmp_path):
    _make_repo(tmp_path, files=PY_SRC + ["pyproject.toml"], published=False)
    assert {x.check_id: x for x in urc.run_checks("psd", "python")}["U-04"].status == urc.PASS


@pytest.mark.parametrize("root_files,expected", [
    (["App.sln"], urc.PASS), (["App.slnx"], urc.PASS), (["App.csproj"], urc.PASS),
    (["A.sln", "B.sln"], urc.FAIL), ([], urc.FAIL),
])
def test_net_install_viability_rules(tmp_path, root_files, expected):
    _make_repo(tmp_path, platform="net", files=["src/A.cs", "src/B.cs", "src/C.cs"] + root_files, published=False)
    assert {x.check_id: x for x in urc.run_checks("psd", "net")}["U-04"].status == expected


def test_clone_behind_remote_warns(tmp_path):
    _make_repo(tmp_path, files=PY_SRC + ["pyproject.toml"], head="aaaa1111", remote="bbbb2222")
    assert {x.check_id: x for x in urc.run_checks("psd", "python")}["U-03"].status == urc.WARN


def test_hooks_missing_warns_present_passes(tmp_path):
    _make_repo(tmp_path, files=PY_SRC, hooks=False)
    assert {x.check_id: x for x in urc.run_checks("psd", "python")}["U-05"].status == urc.WARN
    _make_repo(tmp_path / "b", files=PY_SRC, hooks=True)
    assert {x.check_id: x for x in urc.run_checks("psd", "python")}["U-05"].status == urc.PASS


def test_family_placeholder_detected(tmp_path):
    _make_repo(tmp_path, files=PY_SRC, family_page="Aspose.PSD FOSS is coming soon as an open-source library.")
    assert {x.check_id: x for x in urc.run_checks("psd", "python")}["U-06"].status == urc.WARN


def test_compile_smoke_is_not_run_and_never_a_pass(tmp_path):
    _make_repo(tmp_path, files=PY_SRC + ["pyproject.toml"], published=False)
    results = urc.run_checks("psd", "python")
    smoke = {x.check_id: x for x in results}["U-07"]
    assert smoke.status == urc.NOT_RUN
    assert urc.verdict(results, strict=True) == 1   # NOT_RUN/WARN fail under --strict


def test_ready_product_exits_zero(tmp_path):
    _make_repo(tmp_path, files=PY_SRC + ["pyproject.toml"], published=False, hooks=True)
    assert urc.verdict(urc.run_checks("psd", "python")) == 0


def test_unknown_product_is_a_usage_error(tmp_path, capsys):
    _make_repo(tmp_path, files=PY_SRC)
    assert urc.main(["nosuch", "python"]) == 2


# ---------------------------------------------------------------------------
# NC-13: real-portfolio acceptance (the actual repo, not a fixture)
# ---------------------------------------------------------------------------

_REAL_REPO_ROOT = Path(__file__).resolve().parents[3]


def _real_registered_products() -> "list[tuple[str, str]]":
    rows = json.loads((_REAL_REPO_ROOT / "data" / "products.json").read_text(encoding="utf-8"))
    return sorted((r["family"], r["platform"]) for r in rows)


# Measured 2026-10-07: GitHub's license API recognizes MIT on 27 of 36; 5 (`cells/*`) have a
# LICENSE file the API does not recognize; 4 have no LICENSE file at all.
_EXPECTED_WARN = {("psd", "net"), ("psd", "python"), ("gis", "net"), ("3d", "typescript")}
_EXPECTED_FILE_BUT_UNRECOGNIZED_BY_API = {
    ("cells", "java"), ("cells", "net"), ("cells", "python"), ("cells", "cpp"), ("cells", "go"),
}


def test_nc13_real_portfolio_license_check_matches_the_measured_facts():
    """Runs U-01 for real against every registered product's real clone cache -- no mocked
    runner, no fixture. This is the acceptance claim itself, not a description of it."""
    products = _real_registered_products()
    assert len(products) == 36, f"expected 36 registered products, found {len(products)} -- re-measure before trusting this test's own expectations"

    warn, passed, other = [], [], []
    for family, platform in products:
        product = urc.find_product(family, platform)
        assert product is not None
        clone = _REAL_REPO_ROOT / "runs" / ".clone_cache" / f"aspose_{family}_{platform}"
        result = urc.check_license(product, clone)
        if result.status == urc.WARN:
            warn.append((family, platform))
        elif result.status == urc.PASS:
            passed.append((family, platform))
        else:
            other.append((family, platform, result.status))

    assert other == [], f"U-01 produced a non-PASS/WARN status (should never happen): {other}"
    assert set(warn) == _EXPECTED_WARN, f"WARN set drifted: {set(warn)} != {_EXPECTED_WARN}"
    assert len(passed) == 36 - len(_EXPECTED_WARN)
    assert _EXPECTED_FILE_BUT_UNRECOGNIZED_BY_API <= set(passed), (
        "the 5 cells/* products with a file-but-API-unrecognized LICENSE must still PASS "
        f"(file-first design) -- missing: {_EXPECTED_FILE_BUT_UNRECOGNIZED_BY_API - set(passed)}"
    )
    # Never gates the exit code even without --strict: WARN-only never fails.
    for family, platform in warn:
        clone = _REAL_REPO_ROOT / "runs" / ".clone_cache" / f"aspose_{family}_{platform}"
        result = urc.check_license(urc.find_product(family, platform), clone)
        assert urc.verdict([result]) == 0
