"""Tests for scripts/pipeline/retire_page.py (TC-04).

Tests cover:
- Single page retirement sets draft: true and retired_at in frontmatter
- --from-plan reads pages_to_remove from site_plan.yaml and retires all
- --dry-run makes no changes
- Path does not exist → exits with error, no partial writes
- Page already has draft: true → idempotent (no-op, logged)
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

_PIPELINE_DIR = Path(__file__).resolve().parents[1] / "scripts" / "pipeline"
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))

import retire_page as rp


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_page(path: Path, extra_fm: dict | None = None) -> None:
    """Write a minimal markdown page with frontmatter."""
    fm = {"title": "Test Page", "description": "A test page"}
    if extra_fm:
        fm.update(extra_fm)
    content = "---\n" + yaml.safe_dump(fm, allow_unicode=True) + "---\n\nBody content.\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _read_fm(path: Path) -> dict:
    from core.markdown import parse_frontmatter
    return parse_frontmatter(path)


def _make_plan(path: Path, pages_to_remove: list[str]) -> None:
    plan_data = {
        "plan": {
            "family": "cells",
            "platform": "net",
            "delta": {
                "pages_to_add": [],
                "pages_to_update": [],
                "pages_to_remove": pages_to_remove,
                "pages_renamed": [],
            },
        }
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(plan_data, allow_unicode=True), encoding="utf-8")


# ---------------------------------------------------------------------------
# Happy path: single page retirement sets draft: true and retired_at
# ---------------------------------------------------------------------------

def test_retire_page_sets_draft_and_retired_at(tmp_path):
    """retire_page() adds draft: true and retired_at to frontmatter."""
    page = tmp_path / "index.md"
    _make_page(page)

    result = rp.retire_page(page)

    assert result == "retired"
    fm = _read_fm(page)
    assert fm["draft"] is True
    assert "retired_at" in fm
    # retired_at should be a date string YYYY-MM-DD
    import re
    assert re.match(r"^\d{4}-\d{2}-\d{2}$", str(fm["retired_at"]))
    # Body content preserved
    assert "Body content." in page.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Happy path: --from-plan reads pages_to_remove and retires all
# ---------------------------------------------------------------------------

def test_retire_from_plan(tmp_path, monkeypatch):
    """retire_from_plan() retires all pages listed in delta.pages_to_remove."""
    page_a = tmp_path / "content" / "page_a.md"
    page_b = tmp_path / "content" / "page_b.md"
    _make_page(page_a)
    _make_page(page_b)

    plan_path = tmp_path / "site_plan.yaml"
    _make_plan(plan_path, pages_to_remove=[str(page_a), str(page_b)])

    # Patch REPO_ROOT so relative paths resolve correctly
    monkeypatch.setattr(rp, "REPO_ROOT", tmp_path)

    result = rp.retire_from_plan(plan_path)

    assert result["retired"] == 2
    assert result["errors"] == 0
    assert _read_fm(page_a)["draft"] is True
    assert _read_fm(page_b)["draft"] is True


# ---------------------------------------------------------------------------
# Happy path: --dry-run makes no changes
# ---------------------------------------------------------------------------

def test_retire_page_dry_run_no_changes(tmp_path):
    """--dry-run returns 'dry_run' and does not modify frontmatter."""
    page = tmp_path / "index.md"
    _make_page(page)
    original_content = page.read_text(encoding="utf-8")

    result = rp.retire_page(page, dry_run=True)

    assert result == "dry_run"
    assert page.read_text(encoding="utf-8") == original_content


# ---------------------------------------------------------------------------
# Failing path: path does not exist → error, no partial writes
# ---------------------------------------------------------------------------

def test_retire_page_missing_path_returns_error(tmp_path):
    """retire_page() returns 'error' when file doesn't exist."""
    non_existent = tmp_path / "does_not_exist.md"

    result = rp.retire_page(non_existent)

    assert result == "error"
    # No tmp file left behind
    assert not (tmp_path / "does_not_exist.retire_tmp").exists()


# ---------------------------------------------------------------------------
# Failing path: page already has draft: true → idempotent, no-op, skipped
# ---------------------------------------------------------------------------

def test_retire_page_already_retired_is_idempotent(tmp_path):
    """retire_page() skips pages that already have draft: true."""
    page = tmp_path / "index.md"
    _make_page(page, extra_fm={"draft": True, "retired_at": "2026-01-01"})
    original_content = page.read_text(encoding="utf-8")

    result = rp.retire_page(page)

    assert result == "skipped"
    # Content must not have changed
    assert page.read_text(encoding="utf-8") == original_content


# ---------------------------------------------------------------------------
# CLI: --help exits 0
# ---------------------------------------------------------------------------

def test_main_help_exits_0():
    """retire_page --help exits with code 0."""
    with pytest.raises(SystemExit) as exc_info:
        rp.main(["--help"])
    assert exc_info.value.code == 0
