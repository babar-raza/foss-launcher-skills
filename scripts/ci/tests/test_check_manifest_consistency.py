"""Tests for check_manifest_consistency.py — GUARD-04 blocking behavior.

SR-05: MIG-01 transition complete — verify that grade manifest vs frontmatter
inconsistencies now exit 1 (blocking), not 0 (advisory).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_CI_ROOT = Path(__file__).resolve().parent.parent / "checks" 
_PIPELINE_ROOT = _CI_ROOT.parent / "pipeline"
for _p in (str(_CI_ROOT), str(_PIPELINE_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import check_manifest_consistency as cmc  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_page(tmp_path: Path, name: str, grade: str, content_hash: str = "abc123") -> Path:
    """Write a minimal .md file with grade frontmatter."""
    page = tmp_path / name
    page.write_text(
        f"---\ntitle: Test\ngrade: {grade}\ngraded_content_hash: \"{content_hash}\"\n---\nBody.\n",
        encoding="utf-8",
    )
    return page


def _make_manifest(tmp_path: Path, entries: dict) -> Path:
    """Write a grade manifest JSON and monkeypatch MANIFEST_PATH."""
    m = tmp_path / "grade_manifest.json"
    m.write_text(json.dumps(entries), encoding="utf-8")
    return m


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestManifestConsistencyExitCodes:
    """GUARD-04: blocking exit code behavior after MIG-01."""

    def test_consistent_grade_exits_0(self, tmp_path, monkeypatch):
        page = _make_page(tmp_path, "guide.md", grade="B", content_hash="hash1")
        m = _make_manifest(tmp_path, {str(page).replace("\\", "/"): {"grade": "B", "content_hash": "hash1"}})
        monkeypatch.setattr(cmc, "MANIFEST_PATH", m)
        assert cmc.main([str(page)]) == 0

    def test_inconsistent_grade_exits_1(self, tmp_path, monkeypatch):
        """frontmatter A vs manifest B same hash → must exit 1 (blocking)."""
        page = _make_page(tmp_path, "guide.md", grade="A", content_hash="hash1")
        m = _make_manifest(tmp_path, {str(page).replace("\\", "/"): {"grade": "B", "content_hash": "hash1"}})
        monkeypatch.setattr(cmc, "MANIFEST_PATH", m)
        assert cmc.main([str(page)]) == 1

    def test_frontmatter_a_manifest_c_exits_1(self, tmp_path, monkeypatch):
        """frontmatter A vs manifest C → blocking regression path."""
        page = _make_page(tmp_path, "guide.md", grade="A", content_hash="samehash")
        m = _make_manifest(tmp_path, {str(page).replace("\\", "/"): {"grade": "C", "content_hash": "samehash"}})
        monkeypatch.setattr(cmc, "MANIFEST_PATH", m)
        assert cmc.main([str(page)]) == 1

    def test_different_content_hash_no_block(self, tmp_path, monkeypatch):
        """Different hashes = stale comparison — acceptable, exits 0."""
        page = _make_page(tmp_path, "guide.md", grade="A", content_hash="oldhash")
        m = _make_manifest(tmp_path, {str(page).replace("\\", "/"): {"grade": "C", "content_hash": "newhash"}})
        monkeypatch.setattr(cmc, "MANIFEST_PATH", m)
        assert cmc.main([str(page)]) == 0

    def test_no_manifest_entry_exits_0(self, tmp_path, monkeypatch):
        """No manifest entry for file — no comparison possible, exits 0."""
        page = _make_page(tmp_path, "guide.md", grade="A", content_hash="hash1")
        m = _make_manifest(tmp_path, {})  # empty manifest
        monkeypatch.setattr(cmc, "MANIFEST_PATH", m)
        assert cmc.main([str(page)]) == 0

    def test_no_grade_in_frontmatter_exits_0(self, tmp_path, monkeypatch):
        """Ungraded page — no frontmatter grade, exits 0."""
        page = tmp_path / "guide.md"
        page.write_text("---\ntitle: Test\n---\nBody.\n", encoding="utf-8")
        key = str(page).replace("\\", "/")
        m = _make_manifest(tmp_path, {key: {"grade": "B", "content_hash": "hash1"}})
        monkeypatch.setattr(cmc, "MANIFEST_PATH", m)
        assert cmc.main([str(page)]) == 0

    def test_missing_manifest_file_exits_0(self, tmp_path, monkeypatch):
        """No manifest file on disk — skip check, exits 0."""
        page = _make_page(tmp_path, "guide.md", grade="A", content_hash="hash1")
        monkeypatch.setattr(cmc, "MANIFEST_PATH", tmp_path / "nonexistent.json")
        assert cmc.main([str(page)]) == 0

    def test_no_files_exits_0(self, tmp_path, monkeypatch):
        m = _make_manifest(tmp_path, {})
        monkeypatch.setattr(cmc, "MANIFEST_PATH", m)
        assert cmc.main([]) == 0

    def test_multiple_files_one_inconsistent_exits_1(self, tmp_path, monkeypatch):
        """Multiple files, one inconsistency → must exit 1."""
        page_ok = _make_page(tmp_path, "ok.md", grade="B", content_hash="hash1")
        page_bad = _make_page(tmp_path, "bad.md", grade="A", content_hash="hash2")
        manifest_data = {
            str(page_ok).replace("\\", "/"): {"grade": "B", "content_hash": "hash1"},
            str(page_bad).replace("\\", "/"): {"grade": "C", "content_hash": "hash2"},
        }
        m = _make_manifest(tmp_path, manifest_data)
        monkeypatch.setattr(cmc, "MANIFEST_PATH", m)
        assert cmc.main([str(page_ok), str(page_bad)]) == 1

    def test_multiple_files_all_consistent_exits_0(self, tmp_path, monkeypatch):
        page1 = _make_page(tmp_path, "a.md", grade="A", content_hash="h1")
        page2 = _make_page(tmp_path, "b.md", grade="B", content_hash="h2")
        manifest_data = {
            str(page1).replace("\\", "/"): {"grade": "A", "content_hash": "h1"},
            str(page2).replace("\\", "/"): {"grade": "B", "content_hash": "h2"},
        }
        m = _make_manifest(tmp_path, manifest_data)
        monkeypatch.setattr(cmc, "MANIFEST_PATH", m)
        assert cmc.main([str(page1), str(page2)]) == 0
