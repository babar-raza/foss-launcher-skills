"""Unit tests for grade_manifest.py — external grade manifest (ARCH-01)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_PIPELINE_ROOT = Path(__file__).resolve().parent.parent
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

from grade_manifest import (  # noqa: E402
    load_manifest,
    save_manifest,
    read_manifest_entry,
    write_manifest_entry,
    manifest_skip_check,
)


# ---------------------------------------------------------------------------
# load / save round-trip
# ---------------------------------------------------------------------------

class TestLoadSave:
    def test_load_missing_file_returns_empty(self, tmp_path):
        assert load_manifest(tmp_path / "missing.json") == {}

    def test_save_and_load_round_trip(self, tmp_path):
        mp = tmp_path / "manifest.json"
        data = {
            "content/docs/page.md": {
                "content_hash": "a" * 32,
                "grade": "B",
                "grade_reasons": [],
                "evaluator_versions": {"api_accuracy": "2"},
                "model_sha": "abc",
                "logic_version": "16",
                "enrichment_status": "full",
                "graded_evaluators": "full",
                "evaluated_at": "2026-04-21T00:00:00Z",
            }
        }
        save_manifest(data, mp)
        loaded = load_manifest(mp)
        assert loaded == data

    def test_save_creates_parent_dirs(self, tmp_path):
        mp = tmp_path / "sub" / "dir" / "manifest.json"
        save_manifest({"k": {"v": 1}}, mp)
        assert mp.exists()

    def test_load_invalid_json_returns_empty(self, tmp_path):
        mp = tmp_path / "bad.json"
        mp.write_text("not json", encoding="utf-8")
        assert load_manifest(mp) == {}

    def test_load_non_dict_json_returns_empty(self, tmp_path):
        mp = tmp_path / "array.json"
        mp.write_text("[1, 2, 3]", encoding="utf-8")
        assert load_manifest(mp) == {}

    def test_save_is_sorted_and_indented(self, tmp_path):
        mp = tmp_path / "manifest.json"
        save_manifest({"z": {"a": 1}, "a": {"z": 2}}, mp)
        text = mp.read_text(encoding="utf-8")
        assert text.startswith("{\n")
        # Keys should be sorted: "a" before "z"
        assert text.index('"a"') < text.index('"z"')


# ---------------------------------------------------------------------------
# read_manifest_entry
# ---------------------------------------------------------------------------

class TestReadEntry:
    def test_read_existing_entry(self):
        manifest = {"content/page.md": {"grade": "A"}}
        assert read_manifest_entry("content/page.md", manifest) == {"grade": "A"}

    def test_read_missing_entry_returns_none(self):
        assert read_manifest_entry("missing.md", {}) is None

    def test_backslash_normalization(self):
        manifest = {"content/docs/page.md": {"grade": "B"}}
        result = read_manifest_entry("content\\docs\\page.md", manifest)
        assert result == {"grade": "B"}

    def test_read_from_disk_when_no_manifest_arg(self, tmp_path):
        mp = tmp_path / "manifest.json"
        mp.write_text(json.dumps({"f.md": {"grade": "C"}}), encoding="utf-8")
        import grade_manifest
        grade_manifest.configure(manifest_path=mp)
        try:
            assert read_manifest_entry("f.md") == {"grade": "C"}
        finally:
            grade_manifest.configure()


# ---------------------------------------------------------------------------
# write_manifest_entry
# ---------------------------------------------------------------------------

class TestWriteEntry:
    def test_write_new_entry(self, tmp_path):
        mp = tmp_path / "manifest.json"
        result = write_manifest_entry(
            "content/page.md",
            content_hash="h" * 32,
            grade="B",
            grade_reasons=["reason"],
            evaluator_versions={"api_accuracy": "2"},
            model_sha="sha1",
            logic_version="16",
            enrichment_status="full",
            manifest_path=mp,
        )
        assert "content/page.md" in result
        entry = result["content/page.md"]
        assert entry["grade"] == "B"
        assert entry["content_hash"] == "h" * 32
        assert entry["evaluated_at"]  # non-empty timestamp
        # File should be written
        assert mp.exists()

    def test_write_updates_existing(self, tmp_path):
        mp = tmp_path / "manifest.json"
        save_manifest({"content/page.md": {"grade": "C", "content_hash": "old"}}, mp)
        result = write_manifest_entry(
            "content/page.md",
            content_hash="new" + "x" * 29,
            grade="B",
            manifest_path=mp,
        )
        assert result["content/page.md"]["grade"] == "B"

    def test_write_batch_mode_no_save(self, tmp_path):
        mp = tmp_path / "manifest.json"
        manifest = {}
        write_manifest_entry(
            "a.md", content_hash="a" * 32, grade="A",
            manifest=manifest, save=False,
        )
        write_manifest_entry(
            "b.md", content_hash="b" * 32, grade="B",
            manifest=manifest, save=False,
        )
        assert len(manifest) == 2
        assert not mp.exists()  # save=False: not written to disk

    def test_backslash_path_normalized(self, tmp_path):
        mp = tmp_path / "manifest.json"
        result = write_manifest_entry(
            "content\\docs\\page.md",
            content_hash="h" * 32,
            grade="A",
            manifest_path=mp,
        )
        assert "content/docs/page.md" in result


# ---------------------------------------------------------------------------
# manifest_skip_check
# ---------------------------------------------------------------------------

class TestSkipCheck:
    def _make_entry(self, **overrides):
        base = {
            "content_hash": "h" * 32,
            "grade": "B",
            "grade_reasons": [],
            "evaluator_versions": {"api_accuracy": "2", "prose_truth": "1"},
            "model_sha": "sha",
            "logic_version": "16",
            "enrichment_status": "full",
            "graded_evaluators": "full",
            "evaluated_at": "2026-04-21T00:00:00Z",
        }
        base.update(overrides)
        return base

    def test_skip_when_all_match(self):
        manifest = {"page.md": self._make_entry()}
        can_skip, reason = manifest_skip_check(
            "page.md",
            current_content_hash="h" * 32,
            current_evaluator_versions={"api_accuracy": "2", "prose_truth": "1"},
            manifest=manifest,
        )
        assert can_skip is True
        assert reason == "manifest-match"

    def test_no_skip_missing_entry(self):
        can_skip, reason = manifest_skip_check(
            "missing.md",
            current_content_hash="h" * 32,
            current_evaluator_versions={},
            manifest={},
        )
        assert can_skip is False
        assert reason == "no-manifest-entry"

    def test_no_skip_content_hash_changed(self):
        manifest = {"page.md": self._make_entry(content_hash="old" + "x" * 29)}
        can_skip, reason = manifest_skip_check(
            "page.md",
            current_content_hash="new" + "x" * 29,
            current_evaluator_versions={"api_accuracy": "2"},
            manifest=manifest,
        )
        assert can_skip is False
        assert reason == "content-hash-changed"

    def test_no_skip_enrichment_changed(self):
        manifest = {"page.md": self._make_entry(enrichment_status="scout")}
        can_skip, reason = manifest_skip_check(
            "page.md",
            current_content_hash="h" * 32,
            current_evaluator_versions={"api_accuracy": "2"},
            current_enrichment_status="full",
            manifest=manifest,
        )
        assert can_skip is False
        assert reason == "enrichment-status-changed"

    def test_no_skip_evaluator_version_changed(self):
        manifest = {"page.md": self._make_entry()}
        can_skip, reason = manifest_skip_check(
            "page.md",
            current_content_hash="h" * 32,
            current_evaluator_versions={"api_accuracy": "3", "prose_truth": "1"},
            manifest=manifest,
        )
        assert can_skip is False
        assert "evaluator-version-changed:api_accuracy" in reason

    def test_no_skip_new_evaluator_not_in_manifest(self):
        manifest = {"page.md": self._make_entry()}
        can_skip, reason = manifest_skip_check(
            "page.md",
            current_content_hash="h" * 32,
            current_evaluator_versions={
                "api_accuracy": "2",
                "prose_truth": "1",
                "new_eval": "1",
            },
            manifest=manifest,
        )
        assert can_skip is False
        assert "evaluator-version-changed:new_eval" in reason

    def test_skip_with_evaluator_names_filter(self):
        """When evaluator_names is provided, only check those evaluators."""
        manifest = {"page.md": self._make_entry()}
        can_skip, reason = manifest_skip_check(
            "page.md",
            current_content_hash="h" * 32,
            current_evaluator_versions={"api_accuracy": "2", "prose_truth": "1", "new_eval": "1"},
            evaluator_names=["api_accuracy", "prose_truth"],  # Only check these two
            manifest=manifest,
        )
        assert can_skip is True
        assert reason == "manifest-match"

    def test_backslash_path_works(self):
        manifest = {"content/page.md": self._make_entry()}
        can_skip, reason = manifest_skip_check(
            "content\\page.md",
            current_content_hash="h" * 32,
            current_evaluator_versions={"api_accuracy": "2", "prose_truth": "1"},
            manifest=manifest,
        )
        assert can_skip is True
