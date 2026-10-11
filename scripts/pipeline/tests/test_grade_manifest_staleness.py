"""Unit tests for grade_manifest.py's stale/stale_reason/stale_marked_at fields
and mark_stale()/clear_stale() -- Phase B (MT037-2026-08-24-FOSS-PORTFOLIO-
FORENSIC-HEAL blind-spot audit, A-09 repair).

These fields close a real, confirmed gap: a page could carry a live,
deterministically-reproducible defect (a content_eval FAIL) while its
persisted grade still read A/B, because nothing ever re-checked a graded
page's live state after the fact and recorded the mismatch anywhere.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PIPELINE_ROOT = Path(__file__).resolve().parent.parent
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

from grade_manifest import (  # noqa: E402
    load_manifest,
    write_manifest_entry,
    mark_stale,
    clear_stale,
)


class TestWriteManifestEntryDefaultsToNotStale:
    def test_fresh_write_has_stale_false(self, tmp_path):
        mp = tmp_path / "manifest.json"
        manifest = write_manifest_entry(
            "content/docs/page.md", content_hash="a" * 32, grade="A",
            manifest_path=mp,
        )
        entry = manifest["content/docs/page.md"]
        assert entry["stale"] is False
        assert entry["stale_reason"] == ""
        assert entry["stale_marked_at"] == ""

    def test_rewrite_clears_a_prior_stale_flag(self, tmp_path):
        """A fresh grade write is, by definition, up to date -- it must clear
        any stale flag left over from before, not preserve it."""
        mp = tmp_path / "manifest.json"
        write_manifest_entry("content/docs/page.md", content_hash="a" * 32, grade="A", manifest_path=mp)
        mark_stale("content/docs/page.md", "audit.py found 1 live FAIL", manifest_path=mp)
        manifest = load_manifest(mp)
        assert manifest["content/docs/page.md"]["stale"] is True

        # Now re-grade -- this must clear the stale flag.
        manifest2 = write_manifest_entry("content/docs/page.md", content_hash="b" * 32, grade="A", manifest_path=mp)
        assert manifest2["content/docs/page.md"]["stale"] is False
        assert manifest2["content/docs/page.md"]["stale_reason"] == ""


class TestMarkStale:
    def test_marks_existing_entry(self, tmp_path):
        mp = tmp_path / "manifest.json"
        write_manifest_entry("content/docs/page.md", content_hash="a" * 32, grade="A", manifest_path=mp)

        result = mark_stale("content/docs/page.md", "audit.py found 1 live FAIL", manifest_path=mp)

        assert result is True
        manifest = load_manifest(mp)
        entry = manifest["content/docs/page.md"]
        assert entry["stale"] is True
        assert entry["stale_reason"] == "audit.py found 1 live FAIL"
        assert entry["stale_marked_at"] != ""

    def test_preserves_all_other_fields(self, tmp_path):
        """mark_stale must be a read-modify-write, never a full replace --
        grade, evaluator_versions, etc. must survive untouched."""
        mp = tmp_path / "manifest.json"
        write_manifest_entry(
            "content/docs/page.md", content_hash="a" * 32, grade="A",
            grade_reasons=["No findings -> grade A"],
            evaluator_versions={"api_accuracy": "2"},
            model_sha="deadbeef",
            manifest_path=mp,
        )

        mark_stale("content/docs/page.md", "some reason", manifest_path=mp)

        entry = load_manifest(mp)["content/docs/page.md"]
        assert entry["grade"] == "A"
        assert entry["grade_reasons"] == ["No findings -> grade A"]
        assert entry["evaluator_versions"] == {"api_accuracy": "2"}
        assert entry["model_sha"] == "deadbeef"
        assert entry["content_hash"] == "a" * 32

    def test_returns_false_for_nonexistent_entry(self, tmp_path):
        """Marking staleness on a page that was never graded is meaningless --
        must be a no-op, not a fabricated entry."""
        mp = tmp_path / "manifest.json"
        result = mark_stale("content/docs/never-graded.md", "some reason", manifest_path=mp)

        assert result is False
        assert load_manifest(mp) == {}


class TestClearStale:
    def test_clears_existing_flag(self, tmp_path):
        mp = tmp_path / "manifest.json"
        write_manifest_entry("content/docs/page.md", content_hash="a" * 32, grade="A", manifest_path=mp)
        mark_stale("content/docs/page.md", "some reason", manifest_path=mp)

        result = clear_stale("content/docs/page.md", manifest_path=mp)

        assert result is True
        entry = load_manifest(mp)["content/docs/page.md"]
        assert entry["stale"] is False
        assert entry["stale_reason"] == ""
        assert entry["stale_marked_at"] == ""

    def test_returns_false_for_nonexistent_entry(self, tmp_path):
        mp = tmp_path / "manifest.json"
        result = clear_stale("content/docs/never-graded.md", manifest_path=mp)
        assert result is False
