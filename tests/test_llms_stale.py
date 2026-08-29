"""Tests for scripts/llms_stale.py (new 2026-08-29, TASK_BACKLOG.md SYNC-7)."""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "generic_hugo_repo"
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import llms_generate  # noqa: E402
import llms_stale  # noqa: E402

_SITES = {"docs": {"content_path": "content/docs.example.org/en/{family}/{platform}/"}}


def test_build_current_hashes_excludes_drafts():
    hashes = llms_stale.build_current_hashes(FIXTURE_ROOT, _SITES)
    paths = hashes["docs"].keys()
    assert not any("draft-page" in p for p in paths)
    assert len(hashes["docs"]) == 2


def test_build_current_hashes_deterministic():
    h1 = llms_stale.build_current_hashes(FIXTURE_ROOT, _SITES)
    h2 = llms_stale.build_current_hashes(FIXTURE_ROOT, _SITES)
    assert h1 == h2


def test_diff_against_manifest_detects_new_pages_on_empty_manifest(tmp_path):
    current = llms_stale.build_current_hashes(FIXTURE_ROOT, _SITES)
    diff = llms_stale.diff_against_manifest(current, {}, tmp_path)
    assert set(diff["docs"]["new"]) == set(current["docs"].keys())
    assert diff["docs"]["stale"] == []


def test_diff_against_manifest_detects_stale_page():
    current = llms_stale.build_current_hashes(FIXTURE_ROOT, _SITES)
    prior = {"docs": dict(current["docs"])}
    changed_key = next(iter(prior["docs"]))
    prior["docs"][changed_key] = "deadbeef" * 8  # simulate an old, different hash
    diff = llms_stale.diff_against_manifest(current, prior, Path("/nonexistent"))
    assert changed_key in diff["docs"]["stale"]


def test_diff_against_manifest_detects_missing_output(tmp_path):
    current = llms_stale.build_current_hashes(FIXTURE_ROOT, _SITES)
    prior = {"docs": dict(current["docs"])}  # unchanged hashes, but no output on disk
    diff = llms_stale.diff_against_manifest(current, prior, tmp_path)  # tmp_path has no llms-output
    assert len(diff["docs"]["missing"]) == 2


def test_diff_against_manifest_clean_when_generated_and_unchanged(tmp_path):
    llms_generate.generate_site(FIXTURE_ROOT, tmp_path, "docs", _SITES["docs"]["content_path"])
    current = llms_stale.build_current_hashes(FIXTURE_ROOT, _SITES)
    prior = {"docs": dict(current["docs"])}
    diff = llms_stale.diff_against_manifest(current, prior, tmp_path)
    assert diff["docs"]["stale"] == []
    assert diff["docs"]["missing"] == []


# --- manifest file I/O -------------------------------------------------------

def test_manifest_round_trip(tmp_path):
    reports_root = tmp_path / "reports"
    current = llms_stale.build_current_hashes(FIXTURE_ROOT, _SITES)
    path = llms_stale.manifest_path(reports_root)
    path.parent.mkdir(parents=True)
    import json
    path.write_text(json.dumps(current), encoding="utf-8")
    loaded = llms_stale.load_manifest(reports_root)
    assert loaded == current


def test_load_manifest_missing_returns_empty(tmp_path):
    assert llms_stale.load_manifest(tmp_path / "nonexistent-reports") == {}


# --- CLI-level end-to-end -----------------------------------------------------

def _patch_config(monkeypatch, sites=None):
    # IMPORTANT: llms_stale.py does `from config_loader import load_config`,
    # which binds its OWN local name at import time -- patching
    # config_loader.load_config does NOT affect that local binding (this bit
    # a first version of these tests: they silently "passed" while actually
    # reading the real project config.yaml's 5 aspose-shaped sites, which
    # matched nothing under the fixture, so every count read 0/0/0). Patch
    # llms_stale's own local name instead.
    fixture_config = {
        "content_repo": str(FIXTURE_ROOT),
        "knowledge_root": "knowledge",
        "reports_path": "reports",
        "sites": sites if sites is not None else _SITES,
    }
    monkeypatch.setattr(llms_stale, "load_config", lambda: fixture_config)


def test_cli_update_then_check_only_is_clean(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    _patch_config(monkeypatch)
    output_dir = tmp_path / "llms-output"
    llms_generate.generate_site(FIXTURE_ROOT, output_dir, "docs", _SITES["docs"]["content_path"])

    code = llms_stale.main(["--output", str(output_dir), "--content-root", str(FIXTURE_ROOT), "--update-manifest"])
    assert code == 0
    manifest = llms_stale.load_manifest(Path("reports"))
    assert len(manifest.get("docs", {})) == 2  # proves the fixture's own 2 pages were actually hashed

    code = llms_stale.main([
        "--output", str(output_dir), "--content-root", str(FIXTURE_ROOT),
        "--check-only",
    ])
    assert code == 0


def test_cli_check_only_detects_stale_after_source_edit(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _patch_config(monkeypatch)
    # Own copy of the fixture so we can mutate it without touching the real one.
    import shutil
    local_fixture = tmp_path / "fixture"
    shutil.copytree(FIXTURE_ROOT, local_fixture)

    output_dir = tmp_path / "llms-output"
    llms_generate.generate_site(local_fixture, output_dir, "docs", _SITES["docs"]["content_path"])
    llms_stale.main(["--output", str(output_dir), "--content-root", str(local_fixture), "--update-manifest"])

    edited = local_fixture / "content" / "docs.example.org" / "en" / "widgetkit" / "python" / "getting-started.md"
    edited.write_text(edited.read_text(encoding="utf-8") + "\nAn extra paragraph.\n", encoding="utf-8")

    code = llms_stale.main(["--output", str(output_dir), "--content-root", str(local_fixture), "--check-only"])
    assert code == 1


def test_cli_check_and_update_together_reports_this_runs_staleness_not_zero(tmp_path, monkeypatch):
    """Regression test for the exact bug fixed during implementation: doing
    --update-manifest and --check-only in one pass must report what was
    stale on entry to this run, not silently compare the freshly-updated
    manifest against itself (which would always read clean)."""
    monkeypatch.chdir(tmp_path)
    _patch_config(monkeypatch)
    import shutil
    local_fixture = tmp_path / "fixture"
    shutil.copytree(FIXTURE_ROOT, local_fixture)

    output_dir = tmp_path / "llms-output"
    llms_generate.generate_site(local_fixture, output_dir, "docs", _SITES["docs"]["content_path"])
    llms_stale.main(["--output", str(output_dir), "--content-root", str(local_fixture), "--update-manifest"])

    edited = local_fixture / "content" / "docs.example.org" / "en" / "widgetkit" / "python" / "getting-started.md"
    edited.write_text(edited.read_text(encoding="utf-8") + "\nAn extra paragraph.\n", encoding="utf-8")

    code = llms_stale.main([
        "--output", str(output_dir), "--content-root", str(local_fixture),
        "--update-manifest", "--check-only",
    ])
    assert code == 1  # must still catch the staleness, not just refresh silently
