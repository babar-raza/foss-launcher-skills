"""Tests for check_api_surface_no_test_code.py (HRD-11 Layer 3)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from check_api_surface_no_test_code import discover_api_surfaces, main  # noqa: E402


def _write_surface(root: Path, family: str, platform: str, entries: list[dict]) -> None:
    merged = root / "knowledge" / family / platform / "merged"
    merged.mkdir(parents=True, exist_ok=True)
    (merged / "api_surface.json").write_text(json.dumps(entries), encoding="utf-8")


def test_real_portfolio_is_clean():
    """Runs against the actual repo's COMMITTED knowledge/ -- must stay green (this is the
    'starts green, 0 violations today' acceptance claim, re-checked live, not just asserted).
    Deliberately git-tracked-only (see _tracked_api_surface_paths): at the time this test was
    written, knowledge/psd/{net,python}/merged/api_surface.json exist on disk but are fully
    UNTRACKED (MT076 is mid-launch; psd/python's is still the old, test-contaminated 77-entry
    scout output pending its own re-sync card, TC-PSD-KNW-PY-01) -- scanning the working tree
    unconditionally would make this check red for reasons unrelated to any committed regression.
    """
    assert main([]) == 0


def test_tracked_filter_excludes_an_untracked_fixture_file(tmp_path, monkeypatch):
    """Generic regression guard for the exact bug found while writing this check: a file
    sitting on disk under KNOWLEDGE_ROOT that git does not track must never reach the scan
    (real-world case: a product mid-launch with an untracked, pre-relaunch knowledge/ artifact
    that is expected to still be stale/contaminated -- not yet a committed regression)."""
    import check_api_surface_no_test_code as module
    monkeypatch.setattr(module, "KNOWLEDGE_ROOT", tmp_path / "knowledge")
    monkeypatch.setattr(module, "_tracked_api_surface_paths", set)  # nothing is tracked
    _write_surface(tmp_path, "fixture", "python", [{"name": "TestThing", "file": "pkg_test/t.py"}])
    assert discover_api_surfaces() == []
    assert main([]) == 0


def _bypass_tracked_filter(monkeypatch, module, knowledge_root: Path) -> None:
    """Fixture tests exercise check_no_test_entries() logic, not git-tracking integration
    (tmp_path is not the real repo's git working copy) -- bypass the tracked-files filter so
    every fixture file the test wrote is considered in scope, same as discover_api_surfaces()
    would do for a real committed file."""
    monkeypatch.setattr(module, "KNOWLEDGE_ROOT", knowledge_root)
    monkeypatch.setattr(
        module, "_tracked_api_surface_paths",
        lambda: {p.resolve() for p in knowledge_root.glob("*/*/merged/api_surface.json")},
    )


def test_fails_on_a_fixture_with_a_test_like_entry(tmp_path, monkeypatch):
    import check_api_surface_no_test_code as module
    _bypass_tracked_filter(monkeypatch, module, tmp_path / "knowledge")
    _write_surface(
        tmp_path, "fixture", "python",
        [
            {"name": "Real", "file": "fixture_pkg/real.py"},
            {"name": "TestThing", "file": "fixture_pkg_test/thing.py"},
        ],
    )
    assert main([]) == 1


def test_passes_on_a_clean_fixture(tmp_path, monkeypatch):
    import check_api_surface_no_test_code as module
    _bypass_tracked_filter(monkeypatch, module, tmp_path / "knowledge")
    _write_surface(tmp_path, "fixture", "python", [{"name": "Real", "file": "fixture_pkg/real.py"}])
    assert main([]) == 0


def test_scoping_by_family_and_platform(tmp_path, monkeypatch):
    import check_api_surface_no_test_code as module
    _bypass_tracked_filter(monkeypatch, module, tmp_path / "knowledge")
    _write_surface(tmp_path, "fixture", "python", [{"name": "T", "file": "pkg_test/t.py"}])
    _write_surface(tmp_path, "other", "net", [{"name": "Real", "file": "pkg/real.py"}])
    assert main(["--family", "other", "--platform", "net"]) == 0
    assert main(["--family", "fixture", "--platform", "python"]) == 1
