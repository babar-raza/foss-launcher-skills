"""test_source_sha_backfill.py — Unit tests for source_sha_backfill.process_file.

Covers:
- Happy path: file with 12-char sha gets recomputed to 24 chars
- Skip path: file with 24-char sha is not touched
- Skip path: file with no source_sha field is skipped
- Skip path: file with no provenance block is skipped
- Error path: file with source_file pointing to missing source is skipped with WARN
"""
from pathlib import Path
from unittest.mock import patch

import pytest

from source_sha_backfill import process_file
from provenance import read_provenance, write_provenance


_FAKE_24_SHA = "abcdef1234567890abcdef12"  # 24 chars
_FAKE_12_SHA = "abcdef123456"               # 12 chars


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_page(tmp_path: Path, prov: dict | None, subdir: str = "page") -> Path:
    """Write a minimal .md file; insert provenance block if prov is not None."""
    d = tmp_path / subdir
    d.mkdir(parents=True, exist_ok=True)
    p = d / "index.md"
    p.write_text("---\ntitle: Test\n---\nBody.\n", encoding="utf-8")
    if prov is not None:
        write_provenance(p, prov)
    return p


# ---------------------------------------------------------------------------
# Happy path: 12-char sha -> recomputed to 24 chars
# ---------------------------------------------------------------------------

def test_happy_12_to_24(tmp_path):
    """File with 12-char source_sha gets recomputed to 24 chars on apply."""
    source_file = "blog.aspose.org/3d/java/article/index.md"
    prov = {
        "translation_origin": "unknown",
        "source_file": source_file,
        "source_sha": _FAKE_12_SHA,
        "last_mechanism": "unknown",
        "auto_updatable": True,
    }
    locale_page = _make_page(tmp_path, prov, "locale")

    # Create a fake source file so path-exists check passes
    src = tmp_path / "content" / source_file
    src.parent.mkdir(parents=True)
    src.write_text("source content", encoding="utf-8")

    with patch("source_sha_backfill.compute_source_sha", return_value=_FAKE_24_SHA):
        result = process_file(locale_page, tmp_path, apply=True)

    assert result == "updated"
    updated_prov = read_provenance(locale_page)
    assert updated_prov["source_sha"] == _FAKE_24_SHA


# ---------------------------------------------------------------------------
# Skip path: already 24-char sha -> not touched, compute_source_sha not called
# ---------------------------------------------------------------------------

def test_skip_already_24(tmp_path):
    """File with 24-char source_sha is returned as skipped-ok; sha not recomputed."""
    source_file = "blog.aspose.org/3d/java/article/index.md"
    prov = {
        "translation_origin": "unknown",
        "source_file": source_file,
        "source_sha": _FAKE_24_SHA,
        "last_mechanism": "unknown",
        "auto_updatable": True,
    }
    page = _make_page(tmp_path, prov)

    with patch("source_sha_backfill.compute_source_sha") as mock_compute:
        result = process_file(page, tmp_path, apply=True)

    assert result == "skipped-ok"
    mock_compute.assert_not_called()


# ---------------------------------------------------------------------------
# Skip path: no source_sha field in provenance
# ---------------------------------------------------------------------------

def test_skip_no_source_sha(tmp_path):
    """File with provenance but no source_sha field is returned as skipped-no-sha."""
    prov = {
        "translation_origin": "unknown",
        "source_file": "blog.aspose.org/3d/java/article/index.md",
        "last_mechanism": "unknown",
        "auto_updatable": True,
    }
    page = _make_page(tmp_path, prov)

    result = process_file(page, tmp_path, apply=True)
    assert result == "skipped-no-sha"


# ---------------------------------------------------------------------------
# Skip path: no provenance block at all
# ---------------------------------------------------------------------------

def test_skip_no_provenance(tmp_path):
    """File with no provenance block is returned as skipped-no-prov."""
    page = _make_page(tmp_path, prov=None)

    result = process_file(page, tmp_path, apply=True)
    assert result == "skipped-no-prov"


# ---------------------------------------------------------------------------
# Error path: source_file points to non-existent source -> WARN + skip
# ---------------------------------------------------------------------------

def test_warn_missing_source(tmp_path, capsys):
    """File whose source_file path does not exist is skipped with a WARN message."""
    prov = {
        "translation_origin": "unknown",
        "source_file": "blog.aspose.org/3d/java/does-not-exist/index.md",
        "source_sha": _FAKE_12_SHA,
        "last_mechanism": "unknown",
        "auto_updatable": True,
    }
    page = _make_page(tmp_path, prov)

    result = process_file(page, tmp_path, apply=True)

    assert result == "skipped-missing-source"
    assert "WARN" in capsys.readouterr().out
