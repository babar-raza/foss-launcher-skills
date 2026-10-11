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
from grade_writer import content_hash, read_grade, write_grade


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
            assert "graded_at:" not in text  # D-1: graded_at is operational
            assert "graded_content_hash:" in text
            # ARCH-04: operational fields no longer written to frontmatter
            assert "graded_model_sha" not in text
            assert "graded_evaluators" not in text
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
            assert "grade: D" not in text
            assert text.count("grade:") == 1
            # ARCH-04: operational fields replaced by canonical-only block
            assert "old_sha" not in text
            assert "graded_model_sha" not in text
            assert "graded_evaluators" not in text
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

    def test_double_write_no_duplicate_grade_fields(self):
        """Regression: write_grade() twice must not duplicate canonical fields."""
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
            assert "grade: B" in text
            assert text.count("grade:") == 1
            assert text.count("graded_content_hash:") == 1
            # ARCH-04: operational fields absent
            assert "graded_evaluators" not in text
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
            assert "grade: A" in text
            assert "description: Some description" in text
            # ARCH-04: old operational fields replaced, new ones not written
            assert "graded_model_sha" not in text
            assert "graded_evaluators" not in text
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
            assert "grade: C" in text
            # ARCH-04: operational fields not in frontmatter
            assert "graded_evaluators" not in text
            assert "graded_model_sha" not in text
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
            assert "description: Middle content" in text
            # ARCH-04: main block no longer writes operational fields;
            # orphan graded_evaluators survives outside the block (expected)
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
        """Write then read should return consistent data for canonical fields."""
        p = _tmp_file("---\ntitle: Round Trip\n---\nBody.\n")
        try:
            write_grade(p, "D", model_sha="rtsha", evaluator_tier="structural")
            result = read_grade(p)
            assert result["grade"] == "D"
            assert len(result["content_hash"]) == 32
            # ARCH-04: operational fields not written → read back as defaults
            assert result["model_sha"] == ""
            assert result["tier"] == "full"  # default when absent
        finally:
            p.unlink(missing_ok=True)

    def test_read_grade_reads_logic_version(self):
        """graded_logic_version present in frontmatter is returned by read_grade."""
        p = _tmp_file(textwrap.dedent("""\
            ---
            title: T
            grade: A
            graded_at: "2026-04-01T00:00:00Z"
            graded_model_sha: sha1
            graded_evaluators: full
            graded_logic_version: 1
            ---

            Body.
        """))
        try:
            result = read_grade(p)
            assert result is not None
            assert result["logic_version"] == "1"
        finally:
            p.unlink(missing_ok=True)

    def test_read_grade_missing_logic_version_returns_empty(self):
        """Pages without graded_logic_version return empty string for logic_version."""
        p = _tmp_file(textwrap.dedent("""\
            ---
            title: T
            grade: B
            graded_model_sha: sha1
            graded_evaluators: full
            ---

            Body.
        """))
        try:
            result = read_grade(p)
            assert result is not None
            assert result["logic_version"] == ""
        finally:
            p.unlink(missing_ok=True)

    def test_write_grade_does_not_write_logic_version(self):
        """ARCH-04: write_grade no longer writes graded_logic_version to frontmatter."""
        p = _tmp_file("---\ntitle: T\n---\nBody.\n")
        try:
            ok = write_grade(p, "A", model_sha="sha1", evaluator_tier="full",
                             logic_version="1")
            assert ok
            text = p.read_text(encoding="utf-8")
            assert "graded_logic_version" not in text
        finally:
            p.unlink(missing_ok=True)

    def test_write_grade_no_logic_version_on_rewrite(self):
        """ARCH-04: Double write does not produce any graded_logic_version."""
        p = _tmp_file("---\ntitle: T\n---\nBody.\n")
        try:
            write_grade(p, "A", model_sha="sha1", evaluator_tier="full",
                        logic_version="1")
            write_grade(p, "B", model_sha="sha2", evaluator_tier="full",
                        logic_version="2")
            text = p.read_text(encoding="utf-8")
            assert "graded_logic_version" not in text
        finally:
            p.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# TC-03 acceptance test: write_grade MUST NOT update last_mechanism
# ---------------------------------------------------------------------------

class TestWriteGradePreservesLastMechanism:
    """write_grade must not touch last_mechanism in the provenance block."""

    def test_write_grade_does_not_change_last_mechanism(self):
        """After write_grade, last_mechanism must be unchanged from pre-write value."""
        p = _tmp_file(textwrap.dedent("""\
            ---
            title: Test
            type: docs
            provenance:
              content_origin: human-authored
              last_mechanism: human-edit
              auto_updatable: false
            ---

            Body content.
        """))
        try:
            ok = write_grade(p, "A", model_sha="sha1", evaluator_tier="full")
            assert ok, "write_grade returned False unexpectedly"
            text = p.read_text(encoding="utf-8")
            assert "last_mechanism: human-edit" in text, (
                f"last_mechanism was mutated by write_grade:\n{text}"
            )
            assert "grade: A" in text
        finally:
            p.unlink(missing_ok=True)

    def test_write_grade_does_not_create_provenance_if_absent(self):
        """If no provenance block exists, write_grade must NOT create one."""
        p = _tmp_file("---\ntitle: T\ntype: docs\n---\n\nBody.\n")
        try:
            write_grade(p, "B", model_sha="sha1")
            text = p.read_text(encoding="utf-8")
            assert "provenance:" not in text, (
                f"write_grade created a provenance block unexpectedly:\n{text}"
            )
        finally:
            p.unlink(missing_ok=True)

    def test_write_grade_twice_still_preserves_last_mechanism(self):
        """Two consecutive grade writes must not alter last_mechanism."""
        p = _tmp_file(textwrap.dedent("""\
            ---
            title: T
            provenance:
              last_mechanism: skill
              auto_updatable: true
            ---

            Body.
        """))
        try:
            write_grade(p, "C", model_sha="sha1")
            write_grade(p, "A", model_sha="sha2")
            text = p.read_text(encoding="utf-8")
            assert "last_mechanism: skill" in text, (
                f"last_mechanism mutated after double write_grade:\n{text}"
            )
        finally:
            p.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# content_hash — unit tests
# ---------------------------------------------------------------------------

class TestContentHash:
    def test_deterministic(self):
        """Same input always produces the same hash."""
        assert content_hash("hello") == content_hash("hello")

    def test_length_is_32(self):
        """Hash is truncated to 32 hex characters."""
        h = content_hash("anything")
        assert len(h) == 32
        assert all(c in "0123456789abcdef" for c in h)

    def test_different_content_different_hash(self):
        assert content_hash("body A") != content_hash("body B")


# ---------------------------------------------------------------------------
# graded_content_hash — write/read round-trip
# ---------------------------------------------------------------------------

class TestContentHashRoundTrip:
    def test_write_grade_stores_content_hash(self):
        """write_grade writes graded_content_hash derived from the page body."""
        p = _tmp_file("---\ntitle: T\n---\nBody text.\n")
        try:
            ok = write_grade(p, "A", model_sha="sha1")
            assert ok
            text = p.read_text(encoding="utf-8")
            assert "graded_content_hash:" in text
            result = read_grade(p)
            assert result is not None
            assert len(result["content_hash"]) == 32
        finally:
            p.unlink(missing_ok=True)

    def test_read_grade_returns_content_hash(self):
        """read_grade returns the stored content_hash."""
        p = _tmp_file(textwrap.dedent("""\
            ---
            title: T
            grade: B
            graded_content_hash: "abcdef0123456789"
            ---

            Body.
        """))
        try:
            result = read_grade(p)
            assert result is not None
            assert result["content_hash"] == "abcdef0123456789"
        finally:
            p.unlink(missing_ok=True)

    def test_missing_content_hash_returns_empty(self):
        """Pages without graded_content_hash return empty string."""
        p = _tmp_file("---\ntitle: T\ngrade: A\n---\nBody.\n")
        try:
            result = read_grade(p)
            assert result is not None
            assert result["content_hash"] == ""
        finally:
            p.unlink(missing_ok=True)

    def test_content_hash_changes_when_body_changes(self):
        """If body is modified after grading, the stored hash differs from current."""
        p = _tmp_file("---\ntitle: T\n---\nOriginal body.\n")
        try:
            write_grade(p, "A", model_sha="sha1")
            stored = read_grade(p)
            old_hash = stored["content_hash"]
            # Manually change the body while keeping frontmatter
            text = p.read_text(encoding="utf-8")
            new_text = text.replace("Original body.", "Changed body.")
            p.write_text(new_text, encoding="utf-8")
            # The stored hash should no longer match the current body
            current = content_hash("\nChanged body.\n")
            assert old_hash != current
        finally:
            p.unlink(missing_ok=True)

    def test_double_write_no_duplicate_content_hash(self):
        """Two consecutive writes must not duplicate graded_content_hash."""
        p = _tmp_file("---\ntitle: T\n---\nBody.\n")
        try:
            write_grade(p, "A", model_sha="sha1")
            write_grade(p, "B", model_sha="sha2")
            text = p.read_text(encoding="utf-8")
            assert text.count("graded_content_hash") == 1, (
                f"graded_content_hash duplicated:\n{text}"
            )
        finally:
            p.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# CP-P2 G-11: grade_reasons persistence
# ---------------------------------------------------------------------------

class TestGradeReasons:
    def test_write_grade_with_reasons(self):
        """grade_reasons parameter writes reasons to frontmatter."""
        p = _tmp_file("---\ntitle: T\n---\nBody.\n")
        try:
            ok = write_grade(p, "C", model_sha="sha1",
                             grade_reasons=["1 FAIL finding(s) -> base grade C",
                                            "AA ceiling applied"])
            assert ok
            text = p.read_text(encoding="utf-8")
            assert "grade_reasons:" in text
            assert "1 FAIL finding(s)" in text
            assert "AA ceiling applied" in text
        finally:
            p.unlink(missing_ok=True)

    def test_read_grade_returns_reasons(self):
        """read_grade returns grade_reasons list."""
        p = _tmp_file(textwrap.dedent("""\
            ---
            title: T
            grade: C
            graded_at: "2026-04-16T00:00:00Z"
            graded_content_hash: "abcd1234abcd1234"
            grade_reasons:
              - "1 FAIL finding(s) -> base grade C"
              - "AA ceiling applied"
            ---

            Body.
        """))
        try:
            result = read_grade(p)
            assert result is not None
            assert len(result["grade_reasons"]) == 2
            assert "1 FAIL" in result["grade_reasons"][0]
            assert "AA ceiling" in result["grade_reasons"][1]
        finally:
            p.unlink(missing_ok=True)

    def test_grade_reasons_round_trip(self):
        """Write then read grade_reasons should be consistent."""
        p = _tmp_file("---\ntitle: Round Trip\n---\nBody.\n")
        try:
            reasons = ["No findings -> grade A"]
            write_grade(p, "A", model_sha="sha1", grade_reasons=reasons)
            result = read_grade(p)
            assert result["grade_reasons"] == reasons
        finally:
            p.unlink(missing_ok=True)

    def test_grade_reasons_limited_to_5(self):
        """Top 5 reasons are persisted (cap raised from 3 to 5 per VERIFY-03)."""
        p = _tmp_file("---\ntitle: T\n---\nBody.\n")
        try:
            reasons = ["r1", "r2", "r3", "r4", "r5", "r6", "r7"]
            write_grade(p, "D", model_sha="sha1", grade_reasons=reasons)
            result = read_grade(p)
            assert len(result["grade_reasons"]) == 5
        finally:
            p.unlink(missing_ok=True)

    def test_no_reasons_means_empty_list(self):
        """No grade_reasons param → empty list on read."""
        p = _tmp_file("---\ntitle: T\n---\nBody.\n")
        try:
            write_grade(p, "A", model_sha="sha1")
            result = read_grade(p)
            assert result["grade_reasons"] == []
        finally:
            p.unlink(missing_ok=True)

    def test_double_write_no_duplicate_reasons(self):
        """Two writes with reasons must not duplicate grade_reasons block."""
        p = _tmp_file("---\ntitle: T\n---\nBody.\n")
        try:
            write_grade(p, "C", model_sha="sha1",
                        grade_reasons=["old reason"])
            write_grade(p, "B", model_sha="sha2",
                        grade_reasons=["new reason"])
            text = p.read_text(encoding="utf-8")
            assert text.count("grade_reasons:") == 1
            assert "old reason" not in text
            assert "new reason" in text
        finally:
            p.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# TC-GA01: Idempotency guard — graded_at-only diff skips write
# ---------------------------------------------------------------------------

class TestIdempotencyGuard:
    """write_grade() must not touch the file when only graded_at would change."""

    def test_idempotent_skip_when_only_graded_at_differs(self):
        """Second write_grade with same grade/sha/hash/tier/version skips the write."""
        p = _tmp_file("---\ntitle: T\n---\nBody.\n")
        try:
            ok1 = write_grade(p, "A", model_sha="sha1", evaluator_tier="full",
                              logic_version="5")
            assert ok1
            mtime1 = p.stat().st_mtime
            ok2 = write_grade(p, "A", model_sha="sha1", evaluator_tier="full",
                              logic_version="5")
            assert ok2  # still True -- skip is not an error
            mtime2 = p.stat().st_mtime
            assert mtime1 == mtime2, "File must not be touched on idempotent re-write"
        finally:
            p.unlink(missing_ok=True)

    def test_writes_when_grade_letter_changes(self):
        """Grade letter A->B forces a write even if everything else is the same."""
        p = _tmp_file("---\ntitle: T\n---\nBody.\n")
        try:
            write_grade(p, "A", model_sha="sha1", evaluator_tier="full", logic_version="5")
            mtime1 = p.stat().st_mtime
            write_grade(p, "B", model_sha="sha1", evaluator_tier="full", logic_version="5")
            mtime2 = p.stat().st_mtime
            assert mtime2 >= mtime1
            assert "grade: B" in p.read_text(encoding="utf-8")
        finally:
            p.unlink(missing_ok=True)

    def test_skips_when_only_model_sha_changes(self):
        """ARCH-04: Changed model_sha does NOT force a write (operational field)."""
        p = _tmp_file("---\ntitle: T\n---\nBody.\n")
        try:
            write_grade(p, "A", model_sha="sha1", evaluator_tier="full", logic_version="5")
            mtime1 = p.stat().st_mtime
            write_grade(p, "A", model_sha="sha2", evaluator_tier="full", logic_version="5")
            mtime2 = p.stat().st_mtime
            assert mtime1 == mtime2, "Operational-only change must not touch file"
        finally:
            p.unlink(missing_ok=True)

    def test_writes_when_content_hash_changes(self):
        """Changed body (-> different content_hash) forces a write."""
        p = _tmp_file("---\ntitle: T\n---\nBody.\n")
        try:
            write_grade(p, "A", model_sha="sha1", evaluator_tier="full", logic_version="5")
            # Rewrite the file with a different body so content_hash differs
            text = p.read_text(encoding="utf-8")
            p.write_text(text.replace("Body.", "Body changed."), encoding="utf-8")
            ok = write_grade(p, "A", model_sha="sha1", evaluator_tier="full", logic_version="5")
            assert ok
            # content_hash in frontmatter must reflect the new body
            from grade_writer import content_hash as ch
            new_body = "Body changed.\n"
            expected_hash = ch(new_body)
            assert expected_hash in p.read_text(encoding="utf-8")
        finally:
            p.unlink(missing_ok=True)

    def test_skips_when_only_logic_version_changes(self):
        """ARCH-04: Changed logic_version does NOT force a write (operational field)."""
        p = _tmp_file("---\ntitle: T\n---\nBody.\n")
        try:
            write_grade(p, "A", model_sha="sha1", evaluator_tier="full", logic_version="5")
            mtime1 = p.stat().st_mtime
            write_grade(p, "A", model_sha="sha1", evaluator_tier="full", logic_version="6")
            mtime2 = p.stat().st_mtime
            assert mtime1 == mtime2, "Operational-only change must not touch file"
        finally:
            p.unlink(missing_ok=True)

    def test_skips_when_only_grade_final_changes(self):
        """ARCH-04: Changing grade_final does NOT force a write (operational field)."""
        p = _tmp_file("---\ntitle: T\n---\nBody.\n")
        try:
            write_grade(p, "A", model_sha="sha1", evaluator_tier="full",
                        logic_version="5", grade_final=True)
            mtime1 = p.stat().st_mtime
            write_grade(p, "A", model_sha="sha1", evaluator_tier="full",
                        logic_version="5", grade_final=False,
                        grade_stale_reason="upstream-dep")
            mtime2 = p.stat().st_mtime
            assert mtime1 == mtime2, "Operational-only change must not touch file"
            # grade_final not in frontmatter
            assert "grade_final" not in p.read_text(encoding="utf-8")
        finally:
            p.unlink(missing_ok=True)

    def test_always_writes_when_no_existing_grade(self):
        """First-time write (no existing grade block) always writes."""
        p = _tmp_file("---\ntitle: T\n---\nBody.\n")
        try:
            assert "grade:" not in p.read_text(encoding="utf-8")
            ok = write_grade(p, "B", model_sha="sha1")
            assert ok
            assert "grade: B" in p.read_text(encoding="utf-8")
        finally:
            p.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# GI-01: Field order correctness — graded_content_hash must follow metadata
# ---------------------------------------------------------------------------

class TestGradeFieldOrder:
    """D-1 + ARCH-04: Only canonical fields remain. Verify correct order: grade, graded_content_hash."""

    def test_write_grade_canonical_field_order(self):
        """Canonical fields appear in order: grade, graded_content_hash (no graded_at)."""
        p = _tmp_file("---\ntitle: T\n---\nBody.\n")
        try:
            write_grade(p, "B", model_sha="abc123", evaluator_tier="full",
                        logic_version="13")
            text = p.read_text(encoding="utf-8")
            lines = text.splitlines()
            idx = {k: next((i for i, l in enumerate(lines) if l.startswith(k)), -1)
                   for k in ("grade:", "graded_content_hash:")}
            assert idx["grade:"] != -1
            assert idx["graded_content_hash:"] != -1
            assert idx["graded_content_hash:"] > idx["grade:"]
            # D-1: graded_at is operational, not in frontmatter
            assert "graded_at:" not in text
            # No operational fields
            assert "graded_model_sha" not in text
            assert "graded_evaluators" not in text
            assert "graded_logic_version" not in text
        finally:
            p.unlink(missing_ok=True)

    def test_double_write_field_order_stable(self):
        """A second write_grade call preserves canonical field order."""
        p = _tmp_file("---\ntitle: T\n---\nBody.\n")
        try:
            write_grade(p, "B", model_sha="sha1", evaluator_tier="full", logic_version="13")
            write_grade(p, "C", model_sha="sha2", evaluator_tier="audit", logic_version="13")
            text = p.read_text(encoding="utf-8")
            lines = text.splitlines()
            idx = {k: next((i for i, l in enumerate(lines) if l.startswith(k)), -1)
                   for k in ("grade:", "graded_content_hash:")}
            assert idx["graded_content_hash:"] > idx["grade:"]
            # D-1: graded_at not present
            assert "graded_at:" not in text
        finally:
            p.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# SR-03: _GRADE_BLOCK_RE regression tests — list + mapping coexistence (TC-5)
# ---------------------------------------------------------------------------

class TestGradeBlockRegexSR03:
    """Verify _GRADE_BLOCK_RE correctly handles grade blocks containing both
    grade_reasons (YAML list items: '  - …') and graded_evaluator_versions
    (YAML mapping entries: '  key: val'), and that these don't break
    idempotency or replacement."""

    def test_write_grade_with_reasons_no_evaluator_versions_in_frontmatter(self):
        """ARCH-04: grade_reasons written but evaluator_versions NOT in frontmatter."""
        p = _tmp_file("---\ntitle: T\n---\nBody.\n")
        ev = {"api_accuracy": "1", "risk_language": "2", "code_syntax_check": "2"}
        try:
            write_grade(p, "B", model_sha="sha1", grade_reasons=["gap A", "gap B"],
                        evaluator_versions=ev)
            text = p.read_text(encoding="utf-8")
            assert "grade_reasons:" in text
            assert '  - "gap A"' in text
            # ARCH-04: evaluator_versions go to manifest only
            assert "graded_evaluator_versions:" not in text

            stored = read_grade(p)
            assert stored["grade"] == "B"
            assert "gap A" in stored["grade_reasons"]
            assert stored["evaluator_versions"] == {}  # not in frontmatter
        finally:
            p.unlink(missing_ok=True)

    def test_idempotency_with_evaluator_versions(self):
        """Second write_grade with identical evaluator_versions must not touch the file."""
        p = _tmp_file("---\ntitle: T\n---\nBody.\n")
        ev = {"api_accuracy": "1", "risk_language": "2"}
        try:
            write_grade(p, "A", model_sha="sha1", evaluator_tier="full",
                        logic_version="15", evaluator_versions=ev)
            mtime1 = p.stat().st_mtime
            write_grade(p, "A", model_sha="sha1", evaluator_tier="full",
                        logic_version="15", evaluator_versions=ev)
            mtime2 = p.stat().st_mtime
            assert mtime1 == mtime2, "File must not be touched on idempotent re-write with evaluator_versions"
        finally:
            p.unlink(missing_ok=True)

    def test_no_evaluator_versions_in_frontmatter_after_rewrite(self):
        """ARCH-04: Re-writing grade block must not include evaluator_versions."""
        p = _tmp_file("---\ntitle: T\n---\nBody.\n")
        ev1 = {"api_accuracy": "1", "risk_language": "1"}
        ev2 = {"api_accuracy": "2", "risk_language": "2"}
        try:
            write_grade(p, "B", model_sha="sha1", evaluator_versions=ev1)
            write_grade(p, "C", model_sha="sha2", evaluator_versions=ev2)
            text = p.read_text(encoding="utf-8")
            assert "graded_evaluator_versions:" not in text
            stored = read_grade(p)
            assert stored["evaluator_versions"] == {}
        finally:
            p.unlink(missing_ok=True)

    def test_grade_reasons_list_still_parsed_when_evaluator_versions_present(self):
        """_GRADE_BLOCK_RE broadening must not break grade_reasons list parsing."""
        p = _tmp_file("---\ntitle: T\n---\nBody content.\n")
        ev = {"api_accuracy": "1"}
        try:
            write_grade(p, "D", grade_reasons=["reason X", "reason Y"],
                        evaluator_versions=ev)
            stored = read_grade(p)
            assert "reason X" in stored["grade_reasons"]
            assert "reason Y" in stored["grade_reasons"]
        finally:
            p.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# SR-04 (grade_writer portion): TC-5 — read_grade parses graded_evaluator_versions
# ---------------------------------------------------------------------------

class TestEvaluatorVersionsReadWrite:
    """Committed tests for TC-5 graded_evaluator_versions round-trip (SR-04)."""

    def test_write_grade_no_evaluator_versions_returns_empty_dict(self):
        """Legacy pages without evaluator_versions return empty dict from read_grade."""
        p = _tmp_file("---\ntitle: T\n---\nBody.\n")
        try:
            write_grade(p, "A", model_sha="sha1")
            stored = read_grade(p)
            assert stored["evaluator_versions"] == {}
            assert "graded_evaluator_versions:" not in p.read_text(encoding="utf-8")
        finally:
            p.unlink(missing_ok=True)

    def test_evaluator_versions_not_in_frontmatter(self):
        """ARCH-04: evaluator_versions not written to frontmatter (manifest only)."""
        p = _tmp_file("---\ntitle: T\n---\nBody.\n")
        ev = {
            "api_accuracy": "1",
            "code_syntax_check": "2",
            "consumer_usefulness": "2",
            "risk_language": "2",
        }
        try:
            write_grade(p, "B", model_sha="sha99", evaluator_versions=ev)
            text = p.read_text(encoding="utf-8")
            assert "graded_evaluator_versions:" not in text
            stored = read_grade(p)
            assert stored["evaluator_versions"] == {}
        finally:
            p.unlink(missing_ok=True)

    def test_evaluator_versions_skip_check_uses_manifest_not_frontmatter(self):
        """ARCH-04: evaluator_versions for skip-check logic now use manifest, not frontmatter."""
        from content_eval import EVALUATOR_VERSIONS
        p = _tmp_file("---\ntitle: T\n---\nBody.\n")
        try:
            write_grade(p, "A", model_sha="sha1", evaluator_tier="full",
                        logic_version="15", evaluator_versions=EVALUATOR_VERSIONS)
            stored = read_grade(p)
            # Canonical fields written
            assert stored["grade"] == "A"
            assert len(stored["content_hash"]) == 32
            # Operational fields NOT in frontmatter → empty on read
            assert stored["evaluator_versions"] == {}
            assert "graded_evaluator_versions" not in p.read_text(encoding="utf-8")
        finally:
            p.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# D-1: graded_at removed from canonical frontmatter — regression tests
# ---------------------------------------------------------------------------

class TestD1GradedAtRemoval:
    """D-1 fix: graded_at is operational and must NOT appear in new writes."""

    def test_canonical_fields_exactly_three(self):
        """CANONICAL_FRONTMATTER_FIELDS contains exactly {grade, graded_content_hash, grade_reasons}."""
        from grade_writer import CANONICAL_FRONTMATTER_FIELDS
        assert CANONICAL_FRONTMATTER_FIELDS == frozenset({
            "grade", "graded_content_hash", "grade_reasons",
        })

    def test_new_write_has_no_graded_at(self):
        """Fresh write_grade() must NOT emit graded_at."""
        p = _tmp_file("---\ntitle: T\n---\nBody.\n")
        try:
            write_grade(p, "B", model_sha="sha1")
            text = p.read_text(encoding="utf-8")
            assert "graded_at:" not in text
            assert "grade: B" in text
            assert "graded_content_hash:" in text
        finally:
            p.unlink(missing_ok=True)

    def test_rewrite_strips_legacy_graded_at(self):
        """Overwriting a page that has graded_at must NOT preserve it."""
        p = _tmp_file(textwrap.dedent("""\
            ---
            title: T
            grade: C
            graded_at: "2026-01-01T00:00:00Z"
            graded_content_hash: "abcd1234abcd1234abcd1234abcd1234"
            ---

            Body.
        """))
        try:
            write_grade(p, "A", model_sha="sha1")
            text = p.read_text(encoding="utf-8")
            assert "graded_at:" not in text
            assert "grade: A" in text
        finally:
            p.unlink(missing_ok=True)

    def test_idempotency_with_legacy_graded_at(self):
        """Page with legacy graded_at: idempotent re-write at same grade must not touch file."""
        p = _tmp_file("---\ntitle: T\n---\nBody.\n")
        try:
            write_grade(p, "A", model_sha="sha1")
            mtime1 = p.stat().st_mtime
            # Second write with identical grade + body → idempotent skip
            write_grade(p, "A", model_sha="sha1")
            mtime2 = p.stat().st_mtime
            assert mtime1 == mtime2, "File must not be touched on idempotent re-write"
        finally:
            p.unlink(missing_ok=True)

    def test_only_three_grade_fields_emitted(self):
        """After write, only grade, graded_content_hash, and optionally grade_reasons are present."""
        p = _tmp_file("---\ntitle: T\n---\nBody.\n")
        try:
            write_grade(p, "C", grade_reasons=["api_accuracy FAIL"])
            text = p.read_text(encoding="utf-8")
            # Exactly these canonical fields present
            assert "grade: C" in text
            assert "graded_content_hash:" in text
            assert "grade_reasons:" in text
            # No operational fields
            for field in ("graded_at:", "graded_model_sha:", "graded_evaluators:",
                          "graded_logic_version:", "graded_evaluator_versions:",
                          "graded_enrichment_status:", "grade_final:", "grade_stale_reason:"):
                assert field not in text, f"Operational field {field} found in frontmatter"
        finally:
            p.unlink(missing_ok=True)

    def test_mig01_alignment(self):
        """D-1 core: runtime canonical set matches MIG-01 canonical set (3 fields, no graded_at)."""
        from grade_writer import CANONICAL_FRONTMATTER_FIELDS
        # MIG-01 script defines: CANONICAL_GRADE_FIELDS = {"grade", "grade_reasons", "graded_content_hash"}
        mig01_fields = frozenset({"grade", "grade_reasons", "graded_content_hash"})
        assert CANONICAL_FRONTMATTER_FIELDS == mig01_fields, (
            f"D-1 discrepancy: grade_writer={CANONICAL_FRONTMATTER_FIELDS}, "
            f"MIG-01={mig01_fields}"
        )


# ---------------------------------------------------------------------------
# SR-09: Orphan guard repair — write_grade on pre-corrupted files
# ---------------------------------------------------------------------------

class TestOrphanGuardRepair:
    """write_grade() must produce valid YAML even when the input file has
    orphaned grade keys or bare root-level list items from a prior corrupt write."""

    def test_write_on_pre_corrupted_file_cleans_orphans(self):
        """write_grade on a file with orphaned bare list items must produce valid YAML."""
        import yaml
        corrupted_fm = textwrap.dedent("""\
            ---
            title: T
            grade: C
            graded_content_hash: "abc123abc123abc123abc123abc123ab"
            grade_reasons:
              - "old reason"
            - orphaned item
            ---
            Body.
        """)
        p = _tmp_file(corrupted_fm)
        try:
            ok = write_grade(p, "A", model_sha="sha1", grade_reasons=["clean reason"])
            assert ok, "write_grade must return True on pre-corrupted file"
            text = p.read_text(encoding="utf-8")
            # Must be valid YAML
            parts = text.split("---")
            assert len(parts) >= 3, "Frontmatter delimiters must be intact"
            parsed = yaml.safe_load(parts[1])
            assert isinstance(parsed, dict), "Frontmatter must parse as a dict"
            # Must have exactly one grade_reasons block
            assert text.count("grade_reasons:") == 1
            # Orphaned item must be gone
            assert "orphaned item" not in text
            # New content must be present
            assert "clean reason" in text
            assert "grade: A" in text
        finally:
            p.unlink(missing_ok=True)

    def test_write_on_file_with_duplicate_grade_block_cleans_extras(self):
        """write_grade on a file with two grade blocks (non-contiguous) must produce valid YAML."""
        import yaml
        # Simulate a file where a second grade block leaked outside the first
        corrupted_fm = textwrap.dedent("""\
            ---
            title: T
            grade: C
            graded_content_hash: "abc123abc123abc123abc123abc123ab"
            grade_reasons:
              - "first block reason"
            some_other_key: value
            grade: D
            graded_content_hash: "def456def456def456def456def456de"
            ---
            Body.
        """)
        p = _tmp_file(corrupted_fm)
        try:
            ok = write_grade(p, "B", model_sha="sha2", grade_reasons=["repair reason"])
            assert ok, "write_grade must return True on file with duplicate grade blocks"
            text = p.read_text(encoding="utf-8")
            parts = text.split("---")
            assert len(parts) >= 3
            parsed = yaml.safe_load(parts[1])
            assert isinstance(parsed, dict), "Frontmatter must parse as a dict"
            assert text.count("grade_reasons:") == 1
            assert "repair reason" in text
            assert "grade: B" in text
        finally:
            p.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# TC-GW-002: categories/tags preservation regression tests
# ---------------------------------------------------------------------------

class TestListItemPreservation:
    """Regression tests for _strip_orphaned_list_items — verify that write_grade()
    does NOT strip valid YAML list items under categories: or tags: keys."""

    def test_categories_preserved_through_write_grade(self, tmp_path):
        p = tmp_path / "page.md"
        p.write_text(textwrap.dedent("""\
            ---
            title: Test
            categories:
            - Aspose.Words
            ---

            Body.
        """), encoding="utf-8")
        ok = write_grade(p, "A", model_sha="sha1")
        assert ok
        text = p.read_text(encoding="utf-8")
        assert "categories:" in text
        assert "- Aspose.Words" in text

    def test_tags_preserved_through_write_grade(self, tmp_path):
        p = tmp_path / "page.md"
        p.write_text(textwrap.dedent("""\
            ---
            title: Test
            tags:
            - python
            ---

            Body.
        """), encoding="utf-8")
        ok = write_grade(p, "A", model_sha="sha1")
        assert ok
        text = p.read_text(encoding="utf-8")
        assert "tags:" in text
        assert "- python" in text

    def test_orphaned_bare_list_item_stripped(self, tmp_path):
        """A stray root-level '- orphaned' line NOT under any key must be removed."""
        # Simulate the corruption that write_grade is designed to fix:
        # a grade block that somehow left a dangling list item.
        # We inject it directly into the frontmatter outside any mapping key.
        raw = "---\ntitle: Test\n- orphaned\ngrade: B\ngraded_content_hash: \"abc\"\ngrade_reasons:\n  - some reason\n---\n\nBody.\n"
        p = tmp_path / "page.md"
        p.write_text(raw, encoding="utf-8")
        ok = write_grade(p, "A", model_sha="sha2")
        assert ok
        text = p.read_text(encoding="utf-8")
        assert "- orphaned" not in text

    def test_categories_survive_repeated_write_grade_calls(self, tmp_path):
        p = tmp_path / "page.md"
        p.write_text(textwrap.dedent("""\
            ---
            title: Test
            categories:
            - Aspose.Cells
            ---

            Body.
        """), encoding="utf-8")
        write_grade(p, "A", model_sha="sha1")
        write_grade(p, "B", model_sha="sha2")
        text = p.read_text(encoding="utf-8")
        assert "categories:" in text
        assert "- Aspose.Cells" in text

    def test_strip_orphaned_list_items_unit(self):
        """Unit test for _strip_orphaned_list_items() directly."""
        from grade_writer import _strip_orphaned_list_items

        # Valid items under mapping keys must be preserved
        text_with_valid = "categories:\n- Aspose.Words\ntags:\n- python\n"
        result = _strip_orphaned_list_items(text_with_valid)
        assert "- Aspose.Words" in result
        assert "- python" in result

        # Orphaned item (no preceding key line) must be stripped
        text_with_orphan = "title: Test\n- orphaned\ndescription: desc\n"
        result = _strip_orphaned_list_items(text_with_orphan)
        assert "- orphaned" not in result
        assert "title: Test" in result
        assert "description: desc" in result

    def test_multi_item_list_fully_preserved(self):
        """Regression for a real 2026-07-23 bug: every item AFTER the first in a
        valid multi-item root-level list was wrongly treated as orphaned (its
        preceding line is the previous list item, not a ':'-terminated key),
        silently truncating e.g. `keywords:` from 7 entries down to 1 whenever
        write_grade() had any other cleanup to do. This must never regress."""
        from grade_writer import _strip_orphaned_list_items

        text = (
            "keywords:\n"
            "- first keyword\n"
            "- second keyword\n"
            "- third keyword\n"
            "- fourth keyword\n"
            "provenance:\n"
            "  content_origin: skill-generated\n"
        )
        result = _strip_orphaned_list_items(text)
        assert "- first keyword" in result
        assert "- second keyword" in result
        assert "- third keyword" in result
        assert "- fourth keyword" in result
        assert "provenance:" in result

    def test_multiple_orphaned_items_in_a_row_all_stripped(self):
        """Multiple consecutive genuinely-orphaned items (no valid parent key)
        must ALL be stripped, not just the first."""
        from grade_writer import _strip_orphaned_list_items

        text = "title: Test\n- orphaned1\n- orphaned2\n- orphaned3\ndescription: desc\n"
        result = _strip_orphaned_list_items(text)
        assert "- orphaned1" not in result
        assert "- orphaned2" not in result
        assert "- orphaned3" not in result
        assert "title: Test" in result
        assert "description: desc" in result

    def test_multi_item_keywords_preserved_through_write_grade(self, tmp_path):
        """End-to-end regression: write_grade() replacing an EXISTING grade block
        (the only code path that invokes _strip_orphaned_list_items — a fresh
        first-time grade write takes a different, non-cleanup append path and
        would not have exercised this bug at all) must not truncate a genuine
        multi-item keywords: list sitting outside that grade block, even while
        a real stray orphaned item elsewhere IS correctly cleaned up."""
        p = tmp_path / "page.md"
        p.write_text(textwrap.dedent("""\
            ---
            title: Test
            - stray orphaned line
            keywords:
            - alpha keyword
            - beta keyword
            - gamma keyword
            grade: B
            graded_content_hash: "oldhash"
            provenance:
              content_origin: skill-generated
            ---

            Body.
        """), encoding="utf-8")
        ok = write_grade(p, "A", model_sha="sha-multi-kw")
        assert ok
        text = p.read_text(encoding="utf-8")
        assert "- alpha keyword" in text
        assert "- beta keyword" in text
        assert "- gamma keyword" in text
        assert "- stray orphaned line" not in text
