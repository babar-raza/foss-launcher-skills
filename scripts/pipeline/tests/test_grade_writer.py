"""Tests for grade_writer.py and content_eval.models grade functions."""

import re
import tempfile
import textwrap
from pathlib import Path

import pytest

from content_eval.models import (
    Finding,
    compute_grade,
    compute_grade_with_criticality,
    CRITICAL_CATEGORIES,
)
from grade_writer import read_grade, write_grade


# ---------------------------------------------------------------------------
# compute_grade — boundary tests
# ---------------------------------------------------------------------------

class TestComputeGrade:
    @pytest.mark.parametrize("fails,warns,expected", [
        # A: 0 FAIL, 0-2 WARN
        (0, 0, "A"),
        (0, 1, "A"),
        (0, 2, "A"),
        # B: 0 FAIL, 3-5 WARN
        (0, 3, "B"),
        (0, 4, "B"),
        (0, 5, "B"),
        # C: 0 FAIL, 6+ WARN
        (0, 6, "C"),
        (0, 10, "C"),
        # C: 1-2 FAIL
        (1, 0, "C"),
        (2, 0, "C"),
        (2, 10, "C"),
        # D: 3-5 FAIL
        (3, 0, "D"),
        (5, 0, "D"),
        (5, 100, "D"),
        # F: 6+ FAIL
        (6, 0, "F"),
        (100, 0, "F"),
    ])
    def test_grade_boundaries(self, fails, warns, expected):
        assert compute_grade(fails, warns) == expected


class TestComputeGradeWithCriticality:
    def test_critical_fc_forces_f(self):
        findings = [
            Finding("FAIL", "FC", "a.md", 1, "forbidden claim"),
        ]
        assert compute_grade_with_criticality(findings) == "F"

    def test_critical_pc_forces_f(self):
        findings = [
            Finding("FAIL", "PC", "a.md", 1, "wrong platform"),
        ]
        assert compute_grade_with_criticality(findings) == "F"

    def test_critical_warn_not_forced(self):
        """WARN in critical category does NOT force F."""
        findings = [
            Finding("WARN", "FC", "a.md", 1, "possible forbidden claim"),
        ]
        assert compute_grade_with_criticality(findings) != "F"

    def test_non_critical_fail_uses_count(self):
        findings = [
            Finding("FAIL", "AA", "a.md", 1, "bad api"),
        ]
        assert compute_grade_with_criticality(findings) == "C"

    def test_zero_findings_gives_a(self):
        assert compute_grade_with_criticality([]) == "A"

    def test_mixed_findings(self):
        findings = [
            Finding("FAIL", "AA", "a.md", 1, "bad"),
            Finding("WARN", "ST", "a.md", 2, "meh"),
            Finding("WARN", "RL", "a.md", 3, "ok"),
        ]
        # 1 FAIL → C
        assert compute_grade_with_criticality(findings) == "C"


# ---------------------------------------------------------------------------
# grade_writer — read/write round-trip
# ---------------------------------------------------------------------------

def _tmp_file(content: str) -> Path:
    f = tempfile.NamedTemporaryFile(
        suffix=".md", mode="w", encoding="utf-8", delete=False
    )
    f.write(content)
    f.close()
    return Path(f.name)


class TestWriteGrade:
    def test_insert_grade_into_clean_frontmatter(self):
        p = _tmp_file(textwrap.dedent("""\
            ---
            title: Test
            type: docs
            ---

            Body.
        """))
        try:
            ok = write_grade(p, "B", model_sha="abc123", evaluator_tier="full")
            assert ok
            text = p.read_text(encoding="utf-8")
            assert "grade: B" in text
            assert "graded_model_sha: abc123" in text
            assert "graded_evaluators: full" in text
            assert "graded_at:" in text
        finally:
            p.unlink(missing_ok=True)

    def test_replace_existing_grade(self):
        p = _tmp_file(textwrap.dedent("""\
            ---
            title: Test
            grade: D
            graded_at: "2025-01-01T00:00:00Z"
            graded_model_sha: old_sha
            graded_evaluators: audit
            ---

            Body.
        """))
        try:
            ok = write_grade(p, "A", model_sha="new_sha", evaluator_tier="full")
            assert ok
            text = p.read_text(encoding="utf-8")
            assert "grade: A" in text
            assert "graded_model_sha: new_sha" in text
            assert "graded_evaluators: full" in text
            assert "old_sha" not in text
            assert "grade: D" not in text
            assert text.count("grade:") == 1
        finally:
            p.unlink(missing_ok=True)

    def test_preserves_non_grade_frontmatter(self):
        p = _tmp_file(textwrap.dedent("""\
            ---
            title: My Page
            description: >
              A folded description
              that spans lines.
            type: docs
            weight: 5
            ---

            Body content.
        """))
        try:
            write_grade(p, "C", model_sha="sha1")
            text = p.read_text(encoding="utf-8")
            assert "title: My Page" in text
            assert "description: >" in text
            assert "type: docs" in text
            assert "weight: 5" in text
            assert "Body content." in text
        finally:
            p.unlink(missing_ok=True)

    def test_preserves_evidence_block(self):
        p = _tmp_file(textwrap.dedent("""\
            ---
            title: Page
            evidence:
              model_sha: evshaaa
              claims:
              - CLM-001
            ---

            Body.
        """))
        try:
            write_grade(p, "B", model_sha="grsha")
            text = p.read_text(encoding="utf-8")
            assert "evidence:" in text
            assert "model_sha: evshaaa" in text
            assert "CLM-001" in text
            assert "grade: B" in text
        finally:
            p.unlink(missing_ok=True)

    def test_rejects_invalid_grade(self):
        p = _tmp_file("---\ntitle: T\n---\nBody.\n")
        try:
            ok = write_grade(p, "X")
            assert not ok
        finally:
            p.unlink(missing_ok=True)

    def test_no_frontmatter_returns_false(self):
        p = _tmp_file("Just body text, no frontmatter.\n")
        try:
            ok = write_grade(p, "A")
            assert not ok
        finally:
            p.unlink(missing_ok=True)

    def test_idempotent_double_write(self):
        p = _tmp_file(textwrap.dedent("""\
            ---
            title: Page
            ---

            Body.
        """))
        try:
            write_grade(p, "A", model_sha="sha1")
            write_grade(p, "B", model_sha="sha2")
            text = p.read_text(encoding="utf-8")
            assert text.count("grade:") == 1
            assert "grade: B" in text
            assert "sha1" not in text
        finally:
            p.unlink(missing_ok=True)

    def test_double_write_no_duplicate_graded_evaluators(self):
        """Regression: write_grade() twice must not duplicate graded_evaluators."""
        p = _tmp_file(textwrap.dedent("""\
            ---
            title: Page
            ---

            Body.
        """))
        try:
            write_grade(p, "A", model_sha="sha1", evaluator_tier="full")
            write_grade(p, "B", model_sha="sha2", evaluator_tier="full")
            text = p.read_text(encoding="utf-8")
            assert text.count("graded_evaluators") == 1, (
                f"graded_evaluators duplicated:\n{text}"
            )
            assert "grade: B" in text
            assert "graded_evaluators: full" in text
        finally:
            p.unlink(missing_ok=True)

    def test_double_write_grade_block_mid_frontmatter(self):
        """Grade block in middle of frontmatter (content after it) stays intact."""
        p = _tmp_file(textwrap.dedent("""\
            ---
            title: Page
            grade: C
            graded_at: "2026-01-01T00:00:00Z"
            graded_model_sha: old
            graded_evaluators: structural
            description: Some description
            ---

            Body.
        """))
        try:
            write_grade(p, "A", model_sha="new_sha", evaluator_tier="full")
            text = p.read_text(encoding="utf-8")
            assert text.count("graded_evaluators") == 1, (
                f"graded_evaluators duplicated:\n{text}"
            )
            assert "grade: A" in text
            assert "graded_evaluators: full" in text
            assert "description: Some description" in text
        finally:
            p.unlink(missing_ok=True)

    def test_triple_write_idempotent(self):
        """Three consecutive writes must not duplicate any grade keys."""
        p = _tmp_file(textwrap.dedent("""\
            ---
            title: Page
            ---

            Body.
        """))
        try:
            write_grade(p, "A", model_sha="sha1", evaluator_tier="full")
            write_grade(p, "B", model_sha="sha2", evaluator_tier="full")
            write_grade(p, "C", model_sha="sha3", evaluator_tier="structural")
            text = p.read_text(encoding="utf-8")
            assert text.count("grade:") == 1
            assert text.count("graded_evaluators") == 1
            assert "grade: C" in text
            assert "graded_evaluators: structural" in text
            assert "graded_model_sha: sha3" in text
        finally:
            p.unlink(missing_ok=True)

    def test_orphan_grade_key_not_expanded(self):
        """count=1 defense: orphaned grade key is not expanded into a second block.

        When a stale grade key is separated from the main block by non-grade
        content, write_grade() replaces only the main consecutive block
        (count=1). The orphan remains inert but is NOT expanded into a full
        duplicate grade block.
        """
        p = _tmp_file(textwrap.dedent("""\
            ---
            title: Page
            grade: C
            graded_at: "2026-01-01T00:00:00Z"
            graded_model_sha: old
            graded_evaluators: structural
            description: Middle content
            graded_evaluators: orphan
            ---

            Body.
        """))
        try:
            write_grade(p, "A", model_sha="new_sha", evaluator_tier="full")
            text = p.read_text(encoding="utf-8")
            # Main block replaced correctly — only 1 grade: key
            assert text.count("grade:") == 1, f"grade: duplicated:\n{text}"
            assert "grade: A" in text
            assert "graded_evaluators: full" in text
            assert "description: Middle content" in text
            # Orphan remains inert (not expanded into a full block)
            assert text.count("graded_model_sha") == 1, (
                f"orphan expanded into full block:\n{text}"
            )
        finally:
            p.unlink(missing_ok=True)


class TestReadGrade:
    def test_read_existing_grade(self):
        p = _tmp_file(textwrap.dedent("""\
            ---
            title: T
            grade: B
            graded_at: "2026-03-29T14:00:00Z"
            graded_model_sha: abc123
            graded_evaluators: full
            ---

            Body.
        """))
        try:
            result = read_grade(p)
            assert result is not None
            assert result["grade"] == "B"
            assert result["model_sha"] == "abc123"
            assert result["tier"] == "full"
        finally:
            p.unlink(missing_ok=True)

    def test_read_no_grade_returns_none(self):
        p = _tmp_file("---\ntitle: T\n---\nBody.\n")
        try:
            assert read_grade(p) is None
        finally:
            p.unlink(missing_ok=True)

    def test_read_nonexistent_file_returns_none(self):
        assert read_grade(Path("/nonexistent/file.md")) is None

    def test_read_defaults_tier_to_full(self):
        """If graded_evaluators is absent, default tier is 'full'."""
        p = _tmp_file("---\ntitle: T\ngrade: A\ngraded_model_sha: s1\n---\nBody.\n")
        try:
            result = read_grade(p)
            assert result["tier"] == "full"
        finally:
            p.unlink(missing_ok=True)

    def test_read_grade_only_no_sha_no_tier(self):
        """File with grade: but no graded_model_sha or graded_evaluators."""
        p = _tmp_file("---\ntitle: T\ngrade: C\n---\nBody.\n")
        try:
            result = read_grade(p)
            assert result is not None
            assert result["grade"] == "C"
            assert result["model_sha"] == ""
            assert result["tier"] == "full"  # default
        finally:
            p.unlink(missing_ok=True)

    def test_read_grade_with_sha_no_tier(self):
        """File with grade + sha but no evaluators field."""
        p = _tmp_file("---\ntitle: T\ngrade: B\ngraded_model_sha: abc\n---\nBody.\n")
        try:
            result = read_grade(p)
            assert result["grade"] == "B"
            assert result["model_sha"] == "abc"
            assert result["tier"] == "full"
        finally:
            p.unlink(missing_ok=True)

    def test_read_invalid_grade_value_returns_none(self):
        """grade: X (not A-F) should return None."""
        p = _tmp_file("---\ntitle: T\ngrade: X\n---\nBody.\n")
        try:
            assert read_grade(p) is None
        finally:
            p.unlink(missing_ok=True)

    def test_read_grade_empty_value_returns_none(self):
        """grade: (no value) should return None."""
        p = _tmp_file("---\ntitle: T\ngrade:\n---\nBody.\n")
        try:
            assert read_grade(p) is None
        finally:
            p.unlink(missing_ok=True)

    def test_round_trip(self):
        """Write then read should return consistent data."""
        p = _tmp_file("---\ntitle: Round Trip\n---\nBody.\n")
        try:
            write_grade(p, "D", model_sha="rtsha", evaluator_tier="structural")
            result = read_grade(p)
            assert result["grade"] == "D"
            assert result["model_sha"] == "rtsha"
            assert result["tier"] == "structural"
        finally:
            p.unlink(missing_ok=True)
