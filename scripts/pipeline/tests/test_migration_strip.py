"""Tests for migrate_strip_operational_frontmatter.py — MIG-01 migration script."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from migrate_strip_operational_frontmatter import (
    CANONICAL_GRADE_FIELDS,
    OPERATIONAL_GRADE_FIELDS,
    detect_canonical_grade_fields,
    detect_operational_fields,
    find_graded_files,
    load_checkpoint,
    parse_yaml_frontmatter,
    preflight_check,
    run_migration,
    save_checkpoint,
    strip_operational_fields,
    validate_stripped,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FULL_GRADED_MD = """\
---
title: Test Page
description: A test page for migration
date: '2026-04-01'
draft: false
author: Aspose
evidence:
  model_sha: abc123
  model_version: 26.1.0
  claims:
  - CLM-test-001
grade: B
graded_at: "2026-04-12T16:06:21Z"
graded_model_sha: abc123def456
graded_evaluators: full
graded_logic_version: 7
graded_content_hash: "244db6d36622654b"
graded_evaluator_versions:
  api_accuracy: "2"
  api_backtick: "1"
  code_syntax_check: "2"
graded_enrichment_status: full
grade_final: true
grade_stale_reason: ""
grade_stale_targets: []
grade_reasons:
  - "Good API coverage"
  - "Code examples present"
provenance:
  content_origin: skill-generated
  last_mechanism: skill
  auto_updatable: true
  content_hash: 244db6d36622654bd6ae9a4e975768af
---

This is the body content.

## Section One

Some text here with `code` examples.

```python
import aspose
```
"""

CLEAN_MD = """\
---
title: Already Clean Page
description: No operational fields
grade: A
graded_content_hash: "abcd1234"
grade_reasons:
  - "Perfect score"
provenance:
  content_origin: skill-generated
---

Body content here.
"""

NO_GRADE_MD = """\
---
title: No Grade Page
description: This page has no grade fields
date: '2026-04-01'
---

Body without grade.
"""


# ---------------------------------------------------------------------------
# test_strips_operational_fields
# ---------------------------------------------------------------------------


def test_strips_operational_fields():
    """Operational fields are removed from frontmatter."""
    new_text, removed, changed = strip_operational_fields(FULL_GRADED_MD)
    assert changed is True
    assert removed == {
        "graded_at", "graded_model_sha", "graded_evaluators",
        "graded_logic_version", "graded_evaluator_versions",
        "graded_enrichment_status", "grade_final",
        "grade_stale_reason", "grade_stale_targets",
    }
    # Verify none remain in the output
    fm, _, _, _ = parse_yaml_frontmatter(new_text)
    assert fm is not None
    for field in OPERATIONAL_GRADE_FIELDS:
        assert field not in fm, f"operational field '{field}' still present"


# ---------------------------------------------------------------------------
# test_preserves_canonical_fields
# ---------------------------------------------------------------------------


def test_preserves_canonical_fields():
    """Canonical grade fields (grade, grade_reasons, graded_content_hash) are kept."""
    new_text, _, changed = strip_operational_fields(FULL_GRADED_MD)
    assert changed is True
    fm, _, _, _ = parse_yaml_frontmatter(new_text)
    assert fm is not None
    assert fm["grade"] == "B"
    assert fm["graded_content_hash"] == "244db6d36622654b"
    assert fm["grade_reasons"] == ["Good API coverage", "Code examples present"]


# ---------------------------------------------------------------------------
# test_preserves_body_content
# ---------------------------------------------------------------------------


def test_preserves_body_content():
    """Body content after frontmatter is byte-identical after stripping."""
    orig_fm, _, _, orig_body = parse_yaml_frontmatter(FULL_GRADED_MD)
    new_text, _, _ = strip_operational_fields(FULL_GRADED_MD)
    _, _, _, new_body = parse_yaml_frontmatter(new_text)
    assert orig_body == new_body


# ---------------------------------------------------------------------------
# test_preserves_non_grade_frontmatter
# ---------------------------------------------------------------------------


def test_preserves_non_grade_frontmatter():
    """Non-grade frontmatter fields (title, evidence, provenance, etc.) are unchanged."""
    new_text, _, _ = strip_operational_fields(FULL_GRADED_MD)
    fm, _, _, _ = parse_yaml_frontmatter(new_text)
    assert fm is not None
    assert fm["title"] == "Test Page"
    assert fm["description"] == "A test page for migration"
    assert fm["date"] == "2026-04-01"
    assert fm["draft"] is False
    assert fm["author"] == "Aspose"
    assert fm["evidence"]["model_sha"] == "abc123"
    assert fm["evidence"]["claims"] == ["CLM-test-001"]
    assert fm["provenance"]["content_origin"] == "skill-generated"
    assert fm["provenance"]["content_hash"] == "244db6d36622654bd6ae9a4e975768af"


# ---------------------------------------------------------------------------
# test_checkpoint_resume
# ---------------------------------------------------------------------------


def test_checkpoint_resume(tmp_path):
    """Checkpoint saves progress and resumes correctly, skipping done files."""
    cp_file = tmp_path / "checkpoint.json"

    # Save a checkpoint with one completed file
    data = {"completed_files": {"/some/file.md"}, "batch_index": 1}
    save_checkpoint(cp_file, data)

    # Load it back
    loaded = load_checkpoint(cp_file)
    assert "/some/file.md" in loaded["completed_files"]
    assert loaded["batch_index"] == 1

    # Create test content directory with graded files
    content_dir = tmp_path / "content"
    content_dir.mkdir()
    f1 = content_dir / "page1.md"
    f1.write_text(FULL_GRADED_MD, encoding="utf-8")
    f2 = content_dir / "page2.md"
    f2.write_text(FULL_GRADED_MD, encoding="utf-8")

    # Create manifest
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text("{}", encoding="utf-8")

    # First run: process both files
    cp2 = tmp_path / "cp2.json"
    result1 = run_migration(
        content_dir,
        apply=False,
        checkpoint_file=cp2,
        manifest_path=manifest_path,
    )
    assert result1["stripped"] == 2

    # Mark both as completed in checkpoint
    save_checkpoint(cp2, {
        "completed_files": {str(f1), str(f2)},
        "batch_index": 1,
    })

    # Second run: should skip both
    result2 = run_migration(
        content_dir,
        apply=False,
        checkpoint_file=cp2,
        manifest_path=manifest_path,
    )
    assert result2["skipped_checkpoint"] == 2
    assert result2["stripped"] == 0


# ---------------------------------------------------------------------------
# test_preflight_check_fails_without_manifest
# ---------------------------------------------------------------------------


def test_preflight_check_fails_without_manifest(tmp_path):
    """Pre-flight check fails when manifest file does not exist."""
    fake_manifest = tmp_path / "nonexistent_manifest.json"
    errors = preflight_check(fake_manifest, [])
    assert len(errors) > 0
    assert "not found" in errors[0]


def test_preflight_check_passes_with_manifest(tmp_path):
    """Pre-flight check passes when manifest exists."""
    manifest = tmp_path / "grade_manifest.json"
    manifest.write_text("{}", encoding="utf-8")
    errors = preflight_check(manifest, [])
    assert len(errors) == 0


# ---------------------------------------------------------------------------
# test_dry_run_no_changes
# ---------------------------------------------------------------------------


def test_dry_run_no_changes(tmp_path):
    """Dry-run mode does not modify any files on disk."""
    content_dir = tmp_path / "content"
    content_dir.mkdir()
    f1 = content_dir / "page.md"
    f1.write_text(FULL_GRADED_MD, encoding="utf-8")

    original_content = f1.read_text(encoding="utf-8")

    manifest = tmp_path / "manifest.json"
    manifest.write_text("{}", encoding="utf-8")

    result = run_migration(
        content_dir,
        apply=False,
        checkpoint_file=tmp_path / "cp.json",
        manifest_path=manifest,
    )

    assert result["stripped"] == 1
    # File on disk is UNCHANGED
    assert f1.read_text(encoding="utf-8") == original_content


# ---------------------------------------------------------------------------
# Additional tests
# ---------------------------------------------------------------------------


def test_already_clean_file():
    """File with only canonical grade fields is not modified."""
    new_text, removed, changed = strip_operational_fields(CLEAN_MD)
    assert changed is False
    assert removed == set()
    assert new_text == CLEAN_MD


def test_no_grade_file():
    """File with no grade fields at all is not modified."""
    new_text, removed, changed = strip_operational_fields(NO_GRADE_MD)
    assert changed is False
    assert removed == set()


def test_idempotent():
    """Running strip twice produces the same result."""
    text1, _, _ = strip_operational_fields(FULL_GRADED_MD)
    text2, removed2, changed2 = strip_operational_fields(text1)
    assert changed2 is False
    assert removed2 == set()
    assert text1 == text2


def test_validate_stripped_passes():
    """Validation passes for correctly stripped text."""
    new_text, _, _ = strip_operational_fields(FULL_GRADED_MD)
    errors = validate_stripped(FULL_GRADED_MD, new_text)
    assert errors == []


def test_apply_mode_writes(tmp_path):
    """Apply mode actually writes stripped content to disk."""
    content_dir = tmp_path / "content"
    content_dir.mkdir()
    f1 = content_dir / "page.md"
    f1.write_text(FULL_GRADED_MD, encoding="utf-8")

    manifest = tmp_path / "manifest.json"
    manifest.write_text("{}", encoding="utf-8")

    result = run_migration(
        content_dir,
        apply=True,
        checkpoint_file=tmp_path / "cp.json",
        manifest_path=manifest,
    )

    assert result["stripped"] == 1
    # File on disk IS changed
    new_content = f1.read_text(encoding="utf-8")
    assert new_content != FULL_GRADED_MD
    fm, _, _, _ = parse_yaml_frontmatter(new_content)
    assert "graded_at" not in fm
    assert "graded_model_sha" not in fm
    assert fm["grade"] == "B"


def test_find_graded_files(tmp_path):
    """find_graded_files returns only files with grade: field."""
    content_dir = tmp_path / "content"
    content_dir.mkdir()

    graded = content_dir / "graded.md"
    graded.write_text(FULL_GRADED_MD, encoding="utf-8")

    ungraded = content_dir / "ungraded.md"
    ungraded.write_text(NO_GRADE_MD, encoding="utf-8")

    found = find_graded_files(content_dir)
    assert len(found) == 1
    assert found[0] == graded


def test_sample_limits_files(tmp_path):
    """--sample N limits processing to N files."""
    content_dir = tmp_path / "content"
    content_dir.mkdir()
    for i in range(5):
        f = content_dir / f"page{i}.md"
        f.write_text(FULL_GRADED_MD, encoding="utf-8")

    manifest = tmp_path / "manifest.json"
    manifest.write_text("{}", encoding="utf-8")

    result = run_migration(
        content_dir,
        apply=False,
        sample=2,
        checkpoint_file=tmp_path / "cp.json",
        manifest_path=manifest,
    )
    assert result["total_graded"] == 2
    assert result["stripped"] == 2
