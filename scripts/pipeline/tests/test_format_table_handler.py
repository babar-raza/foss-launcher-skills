"""
Tests for format_table_handler.py (TC-06).

8 test scenarios per the plan:
  T1: STUB page population from formats.json
  T2: MISSING page creation
  T3: FORMAT_ADDED to POPULATED page
  T4: FORMAT_REMOVED from POPULATED page
  T5: FORMAT_DIRECTION_CHANGED in POPULATED page
  T6: Prose cross-ref detection (removed format found in prose)
  T7: English-only guard
  T8: Idempotency (second run produces no change if table already matches)
"""

import json
import sys
import tempfile
from pathlib import Path

import pytest

_PIPELINE_ROOT = Path(__file__).resolve().parents[1]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

import commands.content.format_table_handler as sut

# ── Fixtures ───────────────────────────────────────────────────────────────

SAMPLE_FORMATS_JSON = [
    {"format": "Collada", "direction": "import", "file": "src/formats/ColladaReader.cs", "enum": "", "value": "", "line": 1},
    {"format": "Collada", "direction": "export", "file": "src/formats/ColladaWriter.cs", "enum": "", "value": "", "line": 1},
    {"format": "Obj", "direction": "import", "file": "src/formats/ObjReader.cs", "enum": "", "value": "", "line": 1},
    {"format": "Obj", "direction": "export", "file": "src/formats/ObjWriter.cs", "enum": "", "value": "", "line": 1},
    {"format": "Stl", "direction": "import", "file": "src/formats/StlReader.cs", "enum": "", "value": "", "line": 1},
    {"format": "Stl", "direction": "export", "file": "src/formats/StlWriter.cs", "enum": "", "value": "", "line": 1},
    {"format": "Gltf", "direction": "import", "file": "src/formats/GltfReader.cs", "enum": "", "value": "", "line": 1},
    {"format": "Ply", "direction": "import", "file": "src/formats/PlyReader.cs", "enum": "", "value": "", "line": 1},
]

POPULATED_TABLE_CONTENT = """\
---
title: Format Support
provenance:
  auto_updatable: true
  content_hash: abc123
---

## Supported Formats

| Format | Extension | Read | Write | Options class | Notes |
|--------|-----------|:----:|:-----:|---------------|-------|
| Collada | `.collada` | Yes | Yes | — | — |
| Obj | `.obj` | Yes | Yes | — | — |
| Stl | `.stl` | Yes | Yes | — | — |

## See Also
"""

STUB_CONTENT = """\
---
title: Format Support
provenance:
  auto_updatable: true
  content_hash: abc123
---

## Overview

Formats supported by this library.

## See Also
"""

STUB_WITH_HEADER_CONTENT = """\
---
title: Format Support
provenance:
  auto_updatable: true
  content_hash: abc123
---

## Supported Formats

| Format | Extension | Read | Write | Options class | Notes |
|--------|-----------|:----:|:-----:|---------------|-------|

## See Also
"""


@pytest.fixture(autouse=True)
def isolate_repo(tmp_path):
    sut.configure(repo_root=tmp_path)
    yield
    sut.configure(repo_root=None)


def _make_page(tmp_path: Path, family: str, platform: str, content: str) -> Path:
    p = tmp_path / "content" / "docs.aspose.org" / "en" / family / platform / "developer-guide" / "format-support.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _make_formats_json(tmp_path: Path, family: str, platform: str, records: list) -> Path:
    p = tmp_path / "knowledge" / family / platform / "merged" / "formats.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(records), encoding="utf-8")
    return p


def _make_format_delta(tmp_path: Path, family: str, platform: str, delta: dict) -> Path:
    p = tmp_path / "knowledge" / family / platform / "merged" / "format_delta.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(delta), encoding="utf-8")
    return p


# ── T1: STUB page population ──────────────────────────────────────────────

def test_t1_stub_page_populated_from_formats_json(tmp_path):
    """T1: STUB page (no data rows) gets populated from formats.json."""
    _make_page(tmp_path, "3d", "net", STUB_WITH_HEADER_CONTENT)
    _make_formats_json(tmp_path, "3d", "net", SAMPLE_FORMATS_JSON)

    summary = sut.handle_format_table("3d", "net", dry_run=True)

    assert summary["page_state"] == "STUB"
    assert summary["result"] == sut.R_DRY_RUN
    assert summary["rows_added"] > 0


def test_t1_stub_execute_writes_table_rows(tmp_path):
    """T1 (execute): Written file contains data rows."""
    page = _make_page(tmp_path, "3d", "net", STUB_WITH_HEADER_CONTENT)
    _make_formats_json(tmp_path, "3d", "net", SAMPLE_FORMATS_JSON)

    summary = sut.handle_format_table("3d", "net", dry_run=False)

    assert summary["result"] == sut.R_POPULATED
    written = page.read_text(encoding="utf-8")
    assert "| Collada |" in written
    assert "| Obj |" in written


# ── T2: MISSING page creation ─────────────────────────────────────────────

def test_t2_missing_page_created(tmp_path):
    """T2: No format-support.md exists; page is created with table."""
    # Don't create a page — let the handler detect MISSING
    _make_formats_json(tmp_path, "3d", "net", SAMPLE_FORMATS_JSON)

    summary = sut.handle_format_table("3d", "net", dry_run=True)

    assert summary["page_state"] == "MISSING"
    assert summary["result"] == sut.R_DRY_RUN
    assert summary["rows_added"] > 0


def test_t2_missing_execute_creates_file(tmp_path):
    """T2 (execute): File is created at the correct path."""
    _make_formats_json(tmp_path, "3d", "net", SAMPLE_FORMATS_JSON)

    summary = sut.handle_format_table("3d", "net", dry_run=False)

    assert summary["result"] == sut.R_CREATED
    page = tmp_path / "content" / "docs.aspose.org" / "en" / "3d" / "net" / "developer-guide" / "format-support.md"
    assert page.is_file()
    content = page.read_text(encoding="utf-8")
    assert "Format | Extension | Read | Write" in content
    assert "| Collada |" in content


# ── T3: FORMAT_ADDED to POPULATED page ────────────────────────────────────

def test_t3_format_added_to_populated(tmp_path):
    """T3: FORMAT_ADDED event adds a new row to an existing populated table."""
    page = _make_page(tmp_path, "3d", "net", POPULATED_TABLE_CONTENT)
    _make_formats_json(tmp_path, "3d", "net", SAMPLE_FORMATS_JSON)
    _make_format_delta(tmp_path, "3d", "net", {
        "formats_added": [{"name": "Gltf", "ext": "gltf", "support": "both"}],
        "formats_removed": [],
        "formats_direction_changed": [],
    })

    summary = sut.handle_format_table("3d", "net", dry_run=False)

    assert summary["result"] == sut.R_UPDATED
    assert summary["rows_added"] == 1
    written = page.read_text(encoding="utf-8")
    assert "| Gltf |" in written


# ── T4: FORMAT_REMOVED from POPULATED page ────────────────────────────────

def test_t4_format_removed_from_populated(tmp_path):
    """T4: FORMAT_REMOVED event removes the row from the table."""
    page = _make_page(tmp_path, "3d", "net", POPULATED_TABLE_CONTENT)
    _make_formats_json(tmp_path, "3d", "net", SAMPLE_FORMATS_JSON)
    _make_format_delta(tmp_path, "3d", "net", {
        "formats_added": [],
        "formats_removed": [{"name": "Stl", "ext": "stl"}],
        "formats_direction_changed": [],
    })

    summary = sut.handle_format_table("3d", "net", dry_run=False)

    assert summary["result"] == sut.R_UPDATED
    assert summary["rows_removed"] == 1
    written = page.read_text(encoding="utf-8")
    assert "| Stl |" not in written
    assert "| Collada |" in written  # Other rows preserved


# ── T5: FORMAT_DIRECTION_CHANGED ──────────────────────────────────────────

def test_t5_format_direction_changed(tmp_path):
    """T5: FORMAT_DIRECTION_CHANGED updates Read/Write columns for a row."""
    page = _make_page(tmp_path, "3d", "net", POPULATED_TABLE_CONTENT)
    _make_formats_json(tmp_path, "3d", "net", SAMPLE_FORMATS_JSON)
    # Collada changes from both -> export-only
    _make_format_delta(tmp_path, "3d", "net", {
        "formats_added": [],
        "formats_removed": [],
        "formats_direction_changed": [
            {"name": "Collada", "old_support": "both", "new_support": "export-only"}
        ],
    })

    summary = sut.handle_format_table("3d", "net", dry_run=False)

    assert summary["result"] == sut.R_UPDATED
    assert summary["rows_updated"] == 1
    written = page.read_text(encoding="utf-8")
    # Collada row should now show No for Read, Yes for Write
    # Find the Collada row
    for line in written.splitlines():
        if "| Collada |" in line:
            assert "| No |" in line or "No" in line
            break


# ── T6: Prose cross-ref detection ─────────────────────────────────────────

def test_t6_prose_mention_detected_for_removed_format(tmp_path):
    """T6: When a removed format is mentioned in prose, prose_mentions is populated."""
    content_with_prose = POPULATED_TABLE_CONTENT + "\nAspose.3D supports Stl files natively.\n"
    page = _make_page(tmp_path, "3d", "net", content_with_prose)
    _make_formats_json(tmp_path, "3d", "net", SAMPLE_FORMATS_JSON)
    _make_format_delta(tmp_path, "3d", "net", {
        "formats_added": [],
        "formats_removed": [{"name": "Stl", "ext": "stl"}],
        "formats_direction_changed": [],
    })

    summary = sut.handle_format_table("3d", "net", dry_run=False)

    assert summary["rows_removed"] == 1
    assert "Stl" in summary["prose_mentions"]


# ── T7: English-only guard ────────────────────────────────────────────────

def test_t7_non_english_path_rejected(tmp_path):
    """T7: A page under /fr/ directory is rejected."""
    # Create a French locale page
    page = tmp_path / "content" / "docs.aspose.org" / "fr" / "3d" / "net" / "developer-guide" / "format-support.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(STUB_WITH_HEADER_CONTENT, encoding="utf-8")
    _make_formats_json(tmp_path, "3d", "net", SAMPLE_FORMATS_JSON)

    # The handler always uses the /en/ path — so French page is simply not touched.
    # The English page is MISSING (we didn't create it), so result is DRY_RUN for MISSING.
    summary = sut.handle_format_table("3d", "net", dry_run=True)
    assert summary["page_state"] == "MISSING"  # /en/ path doesn't exist
    # French page is untouched
    assert page.read_text(encoding="utf-8") == STUB_WITH_HEADER_CONTENT


# ── T8: Idempotency ────────────────────────────────────────────────────────

def test_t8_idempotency_second_run_noop(tmp_path):
    """T8: Running the handler twice on the same POPULATED page with empty delta -> NOOP."""
    page = _make_page(tmp_path, "3d", "net", POPULATED_TABLE_CONTENT)
    _make_formats_json(tmp_path, "3d", "net", SAMPLE_FORMATS_JSON)
    _make_format_delta(tmp_path, "3d", "net", {
        "formats_added": [],
        "formats_removed": [],
        "formats_direction_changed": [],
    })

    summary = sut.handle_format_table("3d", "net", dry_run=True)

    assert summary["result"] == sut.R_NOOP
    assert summary["rows_added"] == 0
    assert summary["rows_removed"] == 0
    assert summary["rows_updated"] == 0


def test_t8_stub_then_second_run_noop(tmp_path):
    """T8: After populating a STUB page, running again detects POPULATED + empty delta -> NOOP."""
    _make_page(tmp_path, "3d", "net", STUB_WITH_HEADER_CONTENT)
    _make_formats_json(tmp_path, "3d", "net", SAMPLE_FORMATS_JSON)

    # First run: populate
    summary1 = sut.handle_format_table("3d", "net", dry_run=False)
    assert summary1["result"] == sut.R_POPULATED

    # Create empty delta for second run
    _make_format_delta(tmp_path, "3d", "net", {
        "formats_added": [],
        "formats_removed": [],
        "formats_direction_changed": [],
    })

    # Second run: NOOP
    summary2 = sut.handle_format_table("3d", "net", dry_run=True)
    assert summary2["page_state"] == "POPULATED"
    assert summary2["result"] == sut.R_NOOP
