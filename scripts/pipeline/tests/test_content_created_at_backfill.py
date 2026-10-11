"""test_content_created_at_backfill.py — Unit tests for content_created_at_backfill.

Covers:
- Happy path (Source 1): file with provenance, no field, has date: → written as ISO-8601
- Happy path (Source 2): file with provenance, no field, no date:, in git map → written
- Source 1 priority: both date: and git map entry → date: wins
- Skip: content_created_at already set → not modified (write-once)
- Skip: neither date: nor git map entry → skipped (no fabricated value)
- Skip: no provenance block → skipped
- Idempotency: double-apply → 0 changes on second run
"""
from pathlib import Path

import pytest

from provenance import read_provenance, write_provenance
from content_created_at_backfill import process_file


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_page(tmp_path: Path, prov: dict | None, date_field: str | None = None,
               subdir: str = "page") -> Path:
    """Write a minimal .md file with optional date: field and provenance block."""
    d = tmp_path / subdir
    d.mkdir(parents=True, exist_ok=True)
    p = d / "index.md"
    date_line = f"date: '{date_field}'\n" if date_field else ""
    p.write_text(f"---\ntitle: Test\n{date_line}---\nBody.\n", encoding="utf-8")
    if prov is not None:
        write_provenance(p, prov)
    return p


_BASE_PROV = {"content_origin": "unknown", "last_mechanism": "unknown", "auto_updatable": True}


# ---------------------------------------------------------------------------
# Happy path: Source 1 — date: field present
# ---------------------------------------------------------------------------

def test_source1_date_field_written(tmp_path):
    """File with provenance + date: field gets content_created_at from date:."""
    page = _make_page(tmp_path, _BASE_PROV, date_field="2025-03-15")
    result = process_file(page, git_map={}, apply=True)

    assert result == "updated"
    prov = read_provenance(page)
    assert prov["content_created_at"] == "2025-03-15T00:00:00Z"


# ---------------------------------------------------------------------------
# Happy path: Source 2 — git map (no date: field)
# ---------------------------------------------------------------------------

def test_source2_git_map_written(tmp_path):
    """File with provenance + no date:, but in git map → written from map."""
    page = _make_page(tmp_path, _BASE_PROV)
    rel_path = str(page.relative_to(tmp_path.parent.parent))  # relative for lookup
    git_map = {str(page): "2024-11-01T08:30:00+00:00"}

    result = process_file(page, git_map=git_map, apply=True)

    assert result == "updated"
    prov = read_provenance(page)
    assert prov["content_created_at"] == "2024-11-01T08:30:00+00:00"


# ---------------------------------------------------------------------------
# Source 1 priority: date: wins over git map
# ---------------------------------------------------------------------------

def test_source1_priority_over_git_map(tmp_path):
    """When both date: and git map are available, date: value is used."""
    page = _make_page(tmp_path, _BASE_PROV, date_field="2025-06-01")
    git_map = {str(page): "2020-01-01T00:00:00+00:00"}

    result = process_file(page, git_map=git_map, apply=True)

    assert result == "updated"
    prov = read_provenance(page)
    assert prov["content_created_at"] == "2025-06-01T00:00:00Z"


# ---------------------------------------------------------------------------
# Skip: content_created_at already set
# ---------------------------------------------------------------------------

def test_skip_already_set(tmp_path):
    """File with content_created_at already set is skipped."""
    prov = {**_BASE_PROV, "content_created_at": "2024-01-01T00:00:00Z"}
    page = _make_page(tmp_path, prov, date_field="2025-03-15")

    result = process_file(page, git_map={}, apply=True)

    assert result == "skipped-ok"
    # Value must be unchanged
    assert read_provenance(page)["content_created_at"] == "2024-01-01T00:00:00Z"


# ---------------------------------------------------------------------------
# Skip: neither date: nor git map entry
# ---------------------------------------------------------------------------

def test_skip_no_source(tmp_path):
    """File with provenance but no date: and not in git map → skipped."""
    page = _make_page(tmp_path, _BASE_PROV)

    result = process_file(page, git_map={}, apply=True)

    assert result == "skipped-no-source"
    prov = read_provenance(page)
    assert "content_created_at" not in prov


# ---------------------------------------------------------------------------
# Skip: no provenance block
# ---------------------------------------------------------------------------

def test_skip_no_provenance(tmp_path):
    """File with no provenance block is skipped."""
    page = _make_page(tmp_path, prov=None, date_field="2025-01-01")

    result = process_file(page, git_map={}, apply=True)

    assert result == "skipped-no-prov"


# ---------------------------------------------------------------------------
# Dry-run: no writes
# ---------------------------------------------------------------------------

def test_dry_run_no_write(tmp_path):
    """apply=False returns the status but does not write."""
    page = _make_page(tmp_path, _BASE_PROV, date_field="2025-03-15")

    result = process_file(page, git_map={}, apply=False)

    assert result == "updated"  # Would update
    # But field is NOT written
    prov = read_provenance(page)
    assert "content_created_at" not in prov


# ---------------------------------------------------------------------------
# Idempotency: double-apply
# ---------------------------------------------------------------------------

def test_idempotent_double_apply(tmp_path):
    """Applying twice leaves the field unchanged and returns skipped-ok on second run."""
    page = _make_page(tmp_path, _BASE_PROV, date_field="2025-03-15")

    r1 = process_file(page, git_map={}, apply=True)
    assert r1 == "updated"

    r2 = process_file(page, git_map={}, apply=True)
    assert r2 == "skipped-ok"

    prov = read_provenance(page)
    assert prov["content_created_at"] == "2025-03-15T00:00:00Z"
