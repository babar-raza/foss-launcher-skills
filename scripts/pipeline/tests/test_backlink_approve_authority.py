"""
Tests for backlink_approve_authority.py — focused on merge_authority() logic.

TC-AUTHORITY-MERGE-SAFETY-001: verifies that --merge preserves cross-family records
and that per-family runs without --merge (correctly) overwrite everything.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "pipeline"))

from commands.ops.backlink_approve_authority import merge_authority


# ── Fixtures ───────────────────────────────────────────────────────────────────

def _make_record(source_path: str, family: str, platform: str, decision: str = "AUTO_APPROVE_EXACT") -> dict:
    return {
        "source_path": source_path,
        "family": family,
        "platform": platform,
        "decision": decision,
        "score": 0.90,
    }


# ── merge_authority() tests ────────────────────────────────────────────────────

class TestMergeAuthority:

    def test_merge_preserves_other_families(self):
        """Core safety test: merging font records must not touch note/slides records."""
        existing = {
            "content/note/a.md": _make_record("content/note/a.md", "note", "python"),
            "content/slides/b.md": _make_record("content/slides/b.md", "slides", "java"),
            "content/font/old.md": _make_record("content/font/old.md", "font", "python"),
        }
        new_font = {
            "content/font/new.md": _make_record("content/font/new.md", "font", "python"),
        }

        merged = merge_authority(existing, new_font, family="font")

        # Other families intact
        assert "content/note/a.md" in merged
        assert "content/slides/b.md" in merged
        assert merged["content/note/a.md"]["family"] == "note"
        assert merged["content/slides/b.md"]["family"] == "slides"

        # Old font record removed; new font record added
        assert "content/font/old.md" not in merged
        assert "content/font/new.md" in merged
        assert merged["content/font/new.md"]["family"] == "font"

    def test_merge_removes_only_target_family(self):
        """Only records matching the specified family are removed."""
        existing = {
            "content/3d/x.md": _make_record("content/3d/x.md", "3d", "java"),
            "content/cells/y.md": _make_record("content/cells/y.md", "cells", "net"),
            "content/pdf/z.md": _make_record("content/pdf/z.md", "pdf", "java"),
        }
        new_cells = {
            "content/cells/new.md": _make_record("content/cells/new.md", "cells", "net"),
        }

        merged = merge_authority(existing, new_cells, family="cells")

        assert "content/3d/x.md" in merged
        assert "content/pdf/z.md" in merged
        assert "content/cells/y.md" not in merged
        assert "content/cells/new.md" in merged

    def test_merge_with_platform_filter(self):
        """When platform is specified, only records for that platform are replaced."""
        existing = {
            "content/slides/cpp/a.md": _make_record("content/slides/cpp/a.md", "slides", "cpp"),
            "content/slides/java/b.md": _make_record("content/slides/java/b.md", "slides", "java"),
        }
        new_slides_java = {
            "content/slides/java/new.md": _make_record("content/slides/java/new.md", "slides", "java"),
        }

        merged = merge_authority(existing, new_slides_java, family="slides", platform="java")

        # cpp record preserved
        assert "content/slides/cpp/a.md" in merged
        # java old record removed; new added
        assert "content/slides/java/b.md" not in merged
        assert "content/slides/java/new.md" in merged

    def test_merge_into_empty_existing(self):
        """Merging into empty dict works same as plain insert."""
        new_font = {
            "content/font/a.md": _make_record("content/font/a.md", "font", "python"),
        }
        merged = merge_authority({}, new_font, family="font")
        assert len(merged) == 1
        assert "content/font/a.md" in merged

    def test_merge_no_existing_records_for_family(self):
        """When family has no existing records, merge is purely additive."""
        existing = {
            "content/note/a.md": _make_record("content/note/a.md", "note", "python"),
        }
        new_font = {
            "content/font/b.md": _make_record("content/font/b.md", "font", "python"),
        }
        merged = merge_authority(existing, new_font, family="font")
        assert len(merged) == 2
        assert "content/note/a.md" in merged
        assert "content/font/b.md" in merged

    def test_merge_does_not_mutate_inputs(self):
        """merge_authority is pure — inputs are not modified."""
        existing = {
            "content/font/old.md": _make_record("content/font/old.md", "font", "python"),
        }
        new_font = {
            "content/font/new.md": _make_record("content/font/new.md", "font", "python"),
        }
        existing_copy = dict(existing)
        new_copy = dict(new_font)

        merge_authority(existing, new_font, family="font")

        assert existing == existing_copy
        assert new_font == new_copy

    def test_merge_new_records_overwrite_same_source_path(self):
        """If old and new record have same source_path, new record wins."""
        existing = {
            "content/font/a.md": _make_record("content/font/a.md", "font", "python", "REVIEW_REQUIRED"),
        }
        new_font = {
            "content/font/a.md": _make_record("content/font/a.md", "font", "python", "AUTO_APPROVE_EXACT"),
        }
        merged = merge_authority(existing, new_font, family="font")
        assert merged["content/font/a.md"]["decision"] == "AUTO_APPROVE_EXACT"

    def test_merge_without_platform_removes_all_family_platforms(self):
        """Without platform filter, all platforms for the family are replaced."""
        existing = {
            "content/slides/cpp/a.md": _make_record("content/slides/cpp/a.md", "slides", "cpp"),
            "content/slides/java/b.md": _make_record("content/slides/java/b.md", "slides", "java"),
            "content/slides/net/c.md": _make_record("content/slides/net/c.md", "slides", "net"),
        }
        new_slides = {
            "content/slides/python/d.md": _make_record("content/slides/python/d.md", "slides", "python"),
        }
        merged = merge_authority(existing, new_slides, family="slides")
        # All old slides records removed
        assert "content/slides/cpp/a.md" not in merged
        assert "content/slides/java/b.md" not in merged
        assert "content/slides/net/c.md" not in merged
        # New record present
        assert "content/slides/python/d.md" in merged
