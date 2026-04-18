"""Tests for fix_grade_field_order.py — GI-02.

Covers:
- dry-run does not write files
- apply corrects non-consecutive grade field ordering
- already-correct files are not touched
- idempotency: applying twice produces no second change
- non-grade frontmatter keys are preserved byte-for-byte
- multi-line grade_reasons block is not corrupted
"""
from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

_PIPELINE_DIR = Path(__file__).resolve().parents[2]
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))

import fix_grade_field_order as fgfo


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tmp_md(content: str, tmp_path: Path) -> Path:
    p = tmp_path / "test.md"
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


_ANOMALOUS_FM = """\
---
title: Test Page
grade: B
graded_at: "2026-04-12T16:06:21Z"
graded_content_hash: "abc123"
graded_model_sha: deadbeef
graded_evaluators: full
graded_logic_version: 13
---
Body text here.
"""

_CORRECT_FM = """\
---
title: Test Page
grade: B
graded_at: "2026-04-12T16:06:21Z"
graded_model_sha: deadbeef
graded_evaluators: full
graded_logic_version: 13
graded_content_hash: "abc123"
---
Body text here.
"""

_NO_GRADE_FM = """\
---
title: No Grade Yet
description: A page with no grade block at all.
---
Body text here.
"""


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDryRun:
    def test_dry_run_does_not_write(self, tmp_path):
        """--apply not passed: files must not be modified."""
        p = _tmp_md(_ANOMALOUS_FM, tmp_path)
        original = p.read_text(encoding="utf-8")

        result = fgfo.fix_file(p, apply=False)

        assert result is not None and result.startswith("WOULD FIX"), (
            f"Expected WOULD FIX result, got: {result!r}"
        )
        assert p.read_text(encoding="utf-8") == original, (
            "File must not be modified in dry-run mode"
        )

    def test_dry_run_correct_file_returns_none(self, tmp_path):
        """Already-correct files return None (no change needed)."""
        p = _tmp_md(_CORRECT_FM, tmp_path)
        result = fgfo.fix_file(p, apply=False)
        assert result is None, f"Correct file should return None, got {result!r}"


class TestApply:
    def test_apply_corrects_field_order(self, tmp_path):
        """--apply rewrites file with graded_content_hash after graded_model_sha."""
        p = _tmp_md(_ANOMALOUS_FM, tmp_path)

        result = fgfo.fix_file(p, apply=True)
        assert result is not None and result.startswith("FIXED"), (
            f"Expected FIXED result, got: {result!r}"
        )

        text = p.read_text(encoding="utf-8")
        lines = text.splitlines()
        idx = {k: next((i for i, l in enumerate(lines) if l.startswith(k + ":")), -1)
               for k in ("graded_at", "graded_model_sha", "graded_evaluators",
                          "graded_logic_version", "graded_content_hash")}

        assert idx["graded_content_hash"] > idx["graded_model_sha"], (
            f"graded_content_hash must follow graded_model_sha\n{text}"
        )
        assert idx["graded_content_hash"] > idx["graded_evaluators"], (
            f"graded_content_hash must follow graded_evaluators\n{text}"
        )
        assert idx["graded_content_hash"] > idx["graded_logic_version"], (
            f"graded_content_hash must follow graded_logic_version\n{text}"
        )

    def test_already_correct_not_touched(self, tmp_path):
        """Files already in correct order must not be rewritten."""
        p = _tmp_md(_CORRECT_FM, tmp_path)
        mtime_before = p.stat().st_mtime

        result = fgfo.fix_file(p, apply=True)
        assert result is None, f"Correct file must not be touched; got {result!r}"

        # mtime should be unchanged
        assert p.stat().st_mtime == mtime_before, "File mtime changed on a no-op"

    def test_idempotent(self, tmp_path):
        """Applying fix twice produces no change on the second pass."""
        p = _tmp_md(_ANOMALOUS_FM, tmp_path)

        first = fgfo.fix_file(p, apply=True)
        assert first is not None and first.startswith("FIXED")

        text_after_first = p.read_text(encoding="utf-8")

        second = fgfo.fix_file(p, apply=True)
        assert second is None, (
            "Second apply must report no change (idempotent)"
        )
        assert p.read_text(encoding="utf-8") == text_after_first, (
            "File content changed on second apply"
        )

    def test_no_grade_file_not_touched(self, tmp_path):
        """Files with no grade block at all are skipped."""
        p = _tmp_md(_NO_GRADE_FM, tmp_path)
        original = p.read_text(encoding="utf-8")

        result = fgfo.fix_file(p, apply=True)
        assert result is None
        assert p.read_text(encoding="utf-8") == original


class TestNonGradePreservation:
    def test_non_grade_frontmatter_preserved(self, tmp_path):
        """All non-grade frontmatter keys are preserved byte-for-byte."""
        content = textwrap.dedent("""\
            ---
            title: My Title
            description: A description with special chars & "quotes"
            categories:
              - Reference
              - Python
            grade: A
            graded_at: "2026-01-01T00:00:00Z"
            graded_content_hash: "hash123"
            graded_model_sha: abc
            provenance:
              content_origin: skill-generated
              auto_updatable: true
            ---
            Body text.
        """)
        p = _tmp_md(content, tmp_path)
        fgfo.fix_file(p, apply=True)
        result = p.read_text(encoding="utf-8")

        assert 'title: My Title' in result
        assert 'description: A description with special chars & "quotes"' in result
        assert '  - Reference' in result
        assert '  - Python' in result
        assert 'content_origin: skill-generated' in result
        assert 'auto_updatable: true' in result
        assert 'Body text.' in result

    def test_body_preserved_exactly(self, tmp_path):
        """Page body (after closing ---) is not modified."""
        p = _tmp_md(_ANOMALOUS_FM, tmp_path)
        fgfo.fix_file(p, apply=True)
        text = p.read_text(encoding="utf-8")
        assert text.endswith("Body text here.\n"), (
            f"Body was modified:\n{text}"
        )

    def test_grade_reasons_block_preserved(self, tmp_path):
        """Multi-line grade_reasons list is not corrupted by reordering."""
        content = textwrap.dedent("""\
            ---
            title: T
            grade: C
            graded_at: "2026-01-01T00:00:00Z"
            graded_content_hash: "hash456"
            graded_model_sha: abc
            graded_evaluators: full
            graded_logic_version: 13
            grade_reasons:
              - "1 FAIL finding(s) -> base grade C"
              - "AA ceiling applied"
            ---
            Body.
        """)
        p = _tmp_md(content, tmp_path)
        fgfo.fix_file(p, apply=True)
        result = p.read_text(encoding="utf-8")

        assert "grade_reasons:" in result
        assert '  - "1 FAIL finding(s) -> base grade C"' in result
        assert '  - "AA ceiling applied"' in result
        # graded_content_hash must still be after graded_model_sha
        lines = result.splitlines()
        idx_hash = next((i for i, l in enumerate(lines)
                         if l.startswith("graded_content_hash:")), -1)
        idx_sha = next((i for i, l in enumerate(lines)
                        if l.startswith("graded_model_sha:")), -1)
        assert idx_hash > idx_sha, "graded_content_hash must follow graded_model_sha"
