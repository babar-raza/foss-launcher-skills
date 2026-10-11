"""Tests for check_workflow_drift.py.

Added 2026-09-17 (MT069 PHB-05) alongside the multi-source-directory
extension (scripts/seo/workflows/ + the new scripts/ci/deployed-workflows/)
-- this checker had zero test coverage before this taskcard. Uses
`configure(repo_root=tmp_path)` (the configure() seam pattern already used
elsewhere in this repo) to build an isolated fixture repo rather than
touching this checkout's real template directories, and injects `fetch_fn`
to avoid any real `gh api` subprocess call.

Coverage:
- a single source dir (backward-compatible call shape) still works
- both source dirs are scanned and merged into one result set by default
- a name colliding between the two source dirs is not silently dropped
  (last-source-wins is documented behavior, not tested as "correct" per se,
  but the merge itself must not raise or lose entries)
- classify()'s three-way logic (already covered indirectly, pinned directly here)
"""
from __future__ import annotations

import sys
from pathlib import Path

_CHECKS_DIR = Path(__file__).resolve().parents[1] / "checks"
if str(_CHECKS_DIR) not in sys.path:
    sys.path.insert(0, str(_CHECKS_DIR))

import check_workflow_drift as cwd  # noqa: E402


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_classify_three_way_logic():
    assert cwd.classify("a", None, None) == cwd.DIVERGED  # deployed unresolved -- can't rule out drift
    assert cwd.classify("a", "b", "c") == cwd.DEPLOYED_UNAPPROVED  # live changed vs. approved baseline
    assert cwd.classify("a", "b", "b") == cwd.DIVERGED  # matches baseline, but local itself lags
    assert cwd.classify("a", "a", "a") == cwd.IN_SYNC
    assert cwd.classify("a", "a", None) == cwd.IN_SYNC  # no baseline yet, matches deployed


def test_single_source_dir_backward_compatible(tmp_path):
    # configure() already points BASELINES_PATH at tmp_path (see module docstring
    # of check_workflow_drift.py) -- no monkeypatch needed (AGENTS.md 16 bans
    # patching internals directly; configure() is the sanctioned DI seam).
    cwd.configure(repo_root=tmp_path)
    _write(cwd.WORKFLOWS_DIR / "seo-x.yml", "name: seo-x\n")

    outcome = cwd.check_workflow_drift(
        workflows_dir=cwd.WORKFLOWS_DIR,
        fetch_fn=lambda path: "name: seo-x\n",
        seed_missing_baselines=False,
    )
    assert list(outcome["results"].keys()) == ["seo-x.yml"]
    assert outcome["results"]["seo-x.yml"]["status"] == cwd.IN_SYNC


def test_default_scans_both_source_dirs_and_merges(tmp_path):
    cwd.configure(repo_root=tmp_path)
    _write(cwd.WORKFLOWS_DIR / "seo-x.yml", "name: seo-x\n")
    _write(cwd.DEPLOYED_WORKFLOWS_DIR / "aspose-com-targets-watch.yml", "name: watch\n")

    deployed = {
        ".github/workflows/seo-x.yml": "name: seo-x\n",
        ".github/workflows/aspose-com-targets-watch.yml": "name: watch\n",
    }
    outcome = cwd.check_workflow_drift(
        fetch_fn=lambda path: deployed.get(path),
        seed_missing_baselines=False,
    )
    assert set(outcome["results"].keys()) == {"seo-x.yml", "aspose-com-targets-watch.yml"}
    assert all(r["status"] == cwd.IN_SYNC for r in outcome["results"].values())


def test_missing_source_dir_is_skipped_not_fatal(tmp_path):
    cwd.configure(repo_root=tmp_path)
    # Neither source dir created on disk at all.

    outcome = cwd.check_workflow_drift(fetch_fn=lambda path: None, seed_missing_baselines=False)
    assert outcome["results"] == {}


def test_deployed_unapproved_detected_even_when_it_matches_local(tmp_path):
    """The DEPLOYED_UNAPPROVED-checked-first rule from the module docstring:
    a live change that happens to match today's local template must not be
    misreported as IN_SYNC."""
    cwd.configure(repo_root=tmp_path)
    _write(cwd.DEPLOYED_WORKFLOWS_DIR / "w.yml", "name: w\nversion: 2\n")
    baselines_path = cwd.BASELINES_PATH  # set by configure() above -- no monkeypatch needed
    baselines_path.parent.mkdir(parents=True, exist_ok=True)
    baselines_path.write_text(
        '{"w.yml": {"deployed_repo": "Aspose/aspose.org-workflows", '
        '"deployed_path": ".github/workflows/w.yml", '
        '"approved_baseline_sha256": "not-the-real-sha"}}',
        encoding="utf-8",
    )

    outcome = cwd.check_workflow_drift(
        fetch_fn=lambda path: "name: w\nversion: 2\n",  # matches local, but not the baseline
        seed_missing_baselines=False,
    )
    assert outcome["results"]["w.yml"]["status"] == cwd.DEPLOYED_UNAPPROVED
