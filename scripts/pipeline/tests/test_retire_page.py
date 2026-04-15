"""Tests for retire_page.py — mark content pages retired via draft: true.

Coverage:
- normal retire: draft: true added; other frontmatter fields preserved
- idempotence: already-draft page not re-modified (no double-modification)
- missing file: returns "error" gracefully
- dry-run mode: file byte-for-byte identical after call
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

import retire_page


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SIMPLE_FM = """\
---
title: Getting Started
weight: 10
description: Quick start guide.
---
Page body content here.
"""

_ALREADY_DRAFT = """\
---
draft: true
retired_at: '2026-01-01'
title: Old Page
---
Body.
"""


def _write_page(tmp_path: Path, content: str, name: str = "page.md") -> Path:
    page = tmp_path / name
    page.write_text(content, encoding="utf-8")
    return page


# ---------------------------------------------------------------------------
# TASK-08 tests
# ---------------------------------------------------------------------------

class TestNormalRetire:
    def test_draft_true_added(self, tmp_path):
        page = _write_page(tmp_path, _SIMPLE_FM)
        result = retire_page.retire_page(page)
        assert result == "retired"

        text = page.read_text(encoding="utf-8")
        # Extract frontmatter block
        parts = text.split("---", 2)
        assert len(parts) >= 3
        fm = yaml.safe_load(parts[1])
        assert fm["draft"] is True

    def test_retired_at_set(self, tmp_path):
        page = _write_page(tmp_path, _SIMPLE_FM)
        retire_page.retire_page(page)

        text = page.read_text(encoding="utf-8")
        parts = text.split("---", 2)
        fm = yaml.safe_load(parts[1])
        assert "retired_at" in fm
        # retired_at must be a valid ISO date string
        assert len(str(fm["retired_at"])) == 10  # YYYY-MM-DD

    def test_other_frontmatter_fields_preserved(self, tmp_path):
        page = _write_page(tmp_path, _SIMPLE_FM)
        retire_page.retire_page(page)

        text = page.read_text(encoding="utf-8")
        parts = text.split("---", 2)
        fm = yaml.safe_load(parts[1])
        assert fm["title"] == "Getting Started"
        assert fm["weight"] == 10
        assert fm["description"] == "Quick start guide."

    def test_body_content_preserved(self, tmp_path):
        page = _write_page(tmp_path, _SIMPLE_FM)
        retire_page.retire_page(page)

        text = page.read_text(encoding="utf-8")
        assert "Page body content here." in text


class TestIdempotence:
    def test_already_draft_page_skipped(self, tmp_path):
        """Already-draft page must return 'skipped' — not modify the file."""
        page = _write_page(tmp_path, _ALREADY_DRAFT)
        original = page.read_text(encoding="utf-8")

        result = retire_page.retire_page(page)
        assert result == "skipped"
        assert page.read_text(encoding="utf-8") == original

    def test_double_retire_does_not_corrupt_frontmatter(self, tmp_path):
        """Calling retire twice must produce a valid, uncorrupted frontmatter."""
        page = _write_page(tmp_path, _SIMPLE_FM)
        retire_page.retire_page(page)
        retire_page.retire_page(page)  # second call — should be skipped, not corrupt

        text = page.read_text(encoding="utf-8")
        parts = text.split("---", 2)
        fm = yaml.safe_load(parts[1])
        assert fm["draft"] is True
        assert fm["title"] == "Getting Started"


class TestMissingFile:
    def test_missing_file_returns_error(self, tmp_path):
        nonexistent = tmp_path / "does_not_exist.md"
        result = retire_page.retire_page(nonexistent)
        assert result == "error"


class TestDryRun:
    def test_dry_run_leaves_file_unchanged(self, tmp_path):
        """--dry-run must not touch the file."""
        page = _write_page(tmp_path, _SIMPLE_FM)
        original = page.read_text(encoding="utf-8")

        result = retire_page.retire_page(page, dry_run=True)
        assert result == "dry_run"
        assert page.read_text(encoding="utf-8") == original

    def test_dry_run_already_draft_returns_skipped(self, tmp_path):
        """Already-draft page in dry-run returns 'skipped', not 'dry_run'."""
        page = _write_page(tmp_path, _ALREADY_DRAFT)
        result = retire_page.retire_page(page, dry_run=True)
        assert result == "skipped"


class TestNoFrontmatter:
    def test_page_without_frontmatter_returns_error(self, tmp_path):
        page = _write_page(tmp_path, "No frontmatter here, just body text.\n")
        result = retire_page.retire_page(page)
        assert result == "error"


# ---------------------------------------------------------------------------
# Fix C: Un-retire tests (healing sprint 2026-04-15)
# ---------------------------------------------------------------------------

_RETIRED_FM = """\
---
title: FilterColumn
draft: true
retired_at: '2026-04-13'
layout: reference-single
---

Body content here.
"""

_NOT_RETIRED_FM = """\
---
title: FilterColumn
layout: reference-single
---

Body content here.
"""


class TestUnRetirePage:
    """Fix C: un_retire_page removes draft and retired_at from frontmatter."""

    def test_un_retire_removes_draft_and_retired_at(self, tmp_path):
        page = _write_page(tmp_path, _RETIRED_FM)
        result = retire_page.un_retire_page(page)
        assert result == "un_retired"

        text = page.read_text(encoding="utf-8")
        parts = text.split("---", 2)
        fm = yaml.safe_load(parts[1])
        assert "draft" not in fm
        assert "retired_at" not in fm
        assert fm["title"] == "FilterColumn"
        assert fm["layout"] == "reference-single"

    def test_un_retire_skips_non_retired_page(self, tmp_path):
        page = _write_page(tmp_path, _NOT_RETIRED_FM)
        result = retire_page.un_retire_page(page)
        assert result == "skipped"

    def test_un_retire_dry_run_leaves_file_unchanged(self, tmp_path):
        page = _write_page(tmp_path, _RETIRED_FM)
        original = page.read_text(encoding="utf-8")
        result = retire_page.un_retire_page(page, dry_run=True)
        assert result == "dry_run"
        assert page.read_text(encoding="utf-8") == original

    def test_un_retire_missing_file_returns_error(self, tmp_path):
        result = retire_page.un_retire_page(tmp_path / "missing.md")
        assert result == "error"

    def test_un_retire_idempotent(self, tmp_path):
        """Calling un_retire twice: first succeeds, second skips."""
        page = _write_page(tmp_path, _RETIRED_FM)
        assert retire_page.un_retire_page(page) == "un_retired"
        assert retire_page.un_retire_page(page) == "skipped"


class TestUnRetireFromDelta:
    """Fix C: un_retire_from_delta reads resurrected_apis from knowledge_delta.json."""

    def _setup_delta_and_pages(self, tmp_path, resurrected_apis):
        import json

        # Create knowledge structure
        merged = tmp_path / "knowledge" / "test" / "net" / "merged"
        merged.mkdir(parents=True)
        delta = {"resurrected_apis": resurrected_apis}
        (merged / "knowledge_delta.json").write_text(json.dumps(delta), encoding="utf-8")

        # Create reference pages
        ref_root = tmp_path / "content" / "reference.aspose.org" / "en" / "test" / "net"
        ref_root.mkdir(parents=True)
        for name in resurrected_apis:
            (ref_root / f"{name}.md").write_text(
                f"---\ntitle: {name}\ndraft: true\nretired_at: '2026-04-13'\nlayout: reference-single\n---\nBody.\n",
                encoding="utf-8",
            )
        # Add a non-retired page that is NOT in the list
        (ref_root / "SomeOtherClass.md").write_text(
            "---\ntitle: SomeOtherClass\nlayout: reference-single\n---\nBody.\n",
            encoding="utf-8",
        )
        return merged, ref_root

    def test_un_retires_matching_pages(self, tmp_path, monkeypatch):
        merged, ref_root = self._setup_delta_and_pages(tmp_path, ["ClassA", "ClassB"])
        monkeypatch.setattr(retire_page, "REPO_ROOT", tmp_path)

        result = retire_page.un_retire_from_delta("test", "net")
        assert result["un_retired"] == 2
        assert result["errors"] == 0

        # Verify draft removed
        for name in ["ClassA", "ClassB"]:
            text = (ref_root / f"{name}.md").read_text(encoding="utf-8")
            fm = yaml.safe_load(text.split("---", 2)[1])
            assert "draft" not in fm

        # Verify non-resurrected page untouched
        text = (ref_root / "SomeOtherClass.md").read_text(encoding="utf-8")
        fm = yaml.safe_load(text.split("---", 2)[1])
        assert "draft" not in fm  # it was never retired

    def test_empty_resurrected_apis_is_noop(self, tmp_path, monkeypatch):
        import json
        merged = tmp_path / "knowledge" / "test" / "net" / "merged"
        merged.mkdir(parents=True)
        (merged / "knowledge_delta.json").write_text(
            json.dumps({"resurrected_apis": []}), encoding="utf-8"
        )
        monkeypatch.setattr(retire_page, "REPO_ROOT", tmp_path)
        result = retire_page.un_retire_from_delta("test", "net")
        assert result["un_retired"] == 0

    def test_missing_delta_is_noop(self, tmp_path, monkeypatch):
        monkeypatch.setattr(retire_page, "REPO_ROOT", tmp_path)
        result = retire_page.un_retire_from_delta("test", "net")
        assert result["un_retired"] == 0
