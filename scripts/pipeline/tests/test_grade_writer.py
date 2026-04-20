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

    def test_write_grade_writes_logic_version(self):
        """write_grade with logic_version writes graded_logic_version to frontmatter."""
        p = _tmp_file("---\ntitle: T\n---\nBody.\n")
        try:
            ok = write_grade(p, "A", model_sha="sha1", evaluator_tier="full",
                             logic_version="1")
            assert ok
            text = p.read_text(encoding="utf-8")
            assert "graded_logic_version: 1" in text
        finally:
            p.unlink(missing_ok=True)

    def test_write_grade_replaces_logic_version_on_rewrite(self):
        """Double write with different logic_version replaces rather than duplicates."""
        p = _tmp_file("---\ntitle: T\n---\nBody.\n")
        try:
            write_grade(p, "A", model_sha="sha1", evaluator_tier="full",
                        logic_version="1")
            write_grade(p, "B", model_sha="sha2", evaluator_tier="full",
                        logic_version="2")
            text = p.read_text(encoding="utf-8")
            assert text.count("graded_logic_version") == 1
            assert "graded_logic_version: 2" in text
            assert "graded_logic_version: 1" not in text
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

    def test_length_is_16(self):
        """Hash is truncated to 16 hex characters."""
        h = content_hash("anything")
        assert len(h) == 16
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
            assert len(result["content_hash"]) == 16
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

    def test_grade_reasons_limited_to_3(self):
        """Only top 3 reasons are persisted."""
        p = _tmp_file("---\ntitle: T\n---\nBody.\n")
        try:
            reasons = ["reason 1", "reason 2", "reason 3", "reason 4", "reason 5"]
            write_grade(p, "D", model_sha="sha1", grade_reasons=reasons)
            result = read_grade(p)
            assert len(result["grade_reasons"]) == 3
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

    def test_writes_when_model_sha_changes(self):
        """Changed model_sha forces a write."""
        p = _tmp_file("---\ntitle: T\n---\nBody.\n")
        try:
            write_grade(p, "A", model_sha="sha1", evaluator_tier="full", logic_version="5")
            write_grade(p, "A", model_sha="sha2", evaluator_tier="full", logic_version="5")
            assert "graded_model_sha: sha2" in p.read_text(encoding="utf-8")
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

    def test_writes_when_logic_version_changes(self):
        """Changed logic_version forces a write."""
        p = _tmp_file("---\ntitle: T\n---\nBody.\n")
        try:
            write_grade(p, "A", model_sha="sha1", evaluator_tier="full", logic_version="5")
            write_grade(p, "A", model_sha="sha1", evaluator_tier="full", logic_version="6")
            assert "graded_logic_version: 6" in p.read_text(encoding="utf-8")
        finally:
            p.unlink(missing_ok=True)

    def test_writes_when_grade_final_changes(self):
        """Changing grade_final True->False forces a write."""
        p = _tmp_file("---\ntitle: T\n---\nBody.\n")
        try:
            write_grade(p, "A", model_sha="sha1", evaluator_tier="full",
                        logic_version="5", grade_final=True)
            write_grade(p, "A", model_sha="sha1", evaluator_tier="full",
                        logic_version="5", grade_final=False,
                        grade_stale_reason="upstream-dep")
            assert "grade_final: false" in p.read_text(encoding="utf-8")
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
    """graded_content_hash must appear after graded_model_sha/evaluators/logic_version."""

    def test_write_grade_field_order_correct(self):
        """graded_content_hash must come after graded_model_sha and graded_evaluators."""
        p = _tmp_file("---\ntitle: T\n---\nBody.\n")
        try:
            write_grade(p, "B", model_sha="abc123", evaluator_tier="full",
                        logic_version="13")
            text = p.read_text(encoding="utf-8")
            lines = text.splitlines()
            idx = {k: next((i for i, l in enumerate(lines) if l.startswith(k)), -1)
                   for k in ("graded_at:", "graded_model_sha:", "graded_evaluators:",
                              "graded_logic_version:", "graded_content_hash:")}
            assert idx["graded_content_hash:"] > idx["graded_model_sha:"], (
                f"graded_content_hash (line {idx['graded_content_hash:']}) must come "
                f"AFTER graded_model_sha (line {idx['graded_model_sha:']})\n{text}"
            )
            assert idx["graded_content_hash:"] > idx["graded_evaluators:"], (
                f"graded_content_hash (line {idx['graded_content_hash:']}) must come "
                f"AFTER graded_evaluators (line {idx['graded_evaluators:']})\n{text}"
            )
            assert idx["graded_content_hash:"] > idx["graded_logic_version:"], (
                f"graded_content_hash (line {idx['graded_content_hash:']}) must come "
                f"AFTER graded_logic_version (line {idx['graded_logic_version:']})\n{text}"
            )
        finally:
            p.unlink(missing_ok=True)

    def test_double_write_field_order_stable(self):
        """A second write_grade call must not displace graded_content_hash before metadata."""
        p = _tmp_file("---\ntitle: T\n---\nBody.\n")
        try:
            write_grade(p, "B", model_sha="sha1", evaluator_tier="full", logic_version="13")
            write_grade(p, "C", model_sha="sha2", evaluator_tier="audit", logic_version="13")
            text = p.read_text(encoding="utf-8")
            lines = text.splitlines()
            idx = {k: next((i for i, l in enumerate(lines) if l.startswith(k)), -1)
                   for k in ("graded_model_sha:", "graded_evaluators:",
                              "graded_logic_version:", "graded_content_hash:")}
            assert idx["graded_content_hash:"] > idx["graded_model_sha:"], (
                f"After second write: graded_content_hash must still follow "
                f"graded_model_sha\n{text}"
            )
            assert idx["graded_content_hash:"] > idx["graded_logic_version:"], (
                f"After second write: graded_content_hash must still follow "
                f"graded_logic_version\n{text}"
            )
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

    def test_write_grade_with_reasons_and_evaluator_versions_round_trip(self):
        """Grade block with both grade_reasons and graded_evaluator_versions survives read-back."""
        p = _tmp_file("---\ntitle: T\n---\nBody.\n")
        ev = {"api_accuracy": "1", "risk_language": "2", "code_syntax_check": "2"}
        try:
            write_grade(p, "B", model_sha="sha1", grade_reasons=["gap A", "gap B"],
                        evaluator_versions=ev)
            text = p.read_text(encoding="utf-8")
            assert "grade_reasons:" in text
            assert "graded_evaluator_versions:" in text
            assert '  api_accuracy: "1"' in text
            assert '  - "gap A"' in text

            stored = read_grade(p)
            assert stored["grade"] == "B"
            assert "gap A" in stored["grade_reasons"]
            assert stored["evaluator_versions"]["risk_language"] == "2"
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

    def test_replacement_leaves_no_orphaned_evaluator_version_keys(self):
        """Re-writing grade block must fully replace old graded_evaluator_versions."""
        p = _tmp_file("---\ntitle: T\n---\nBody.\n")
        ev1 = {"api_accuracy": "1", "risk_language": "1"}
        ev2 = {"api_accuracy": "2", "risk_language": "2"}
        try:
            write_grade(p, "B", model_sha="sha1", evaluator_versions=ev1)
            write_grade(p, "C", model_sha="sha2", evaluator_versions=ev2)
            text = p.read_text(encoding="utf-8")
            stored = read_grade(p)
            # Old versions must be fully replaced
            assert stored["evaluator_versions"]["api_accuracy"] == "2"
            assert stored["evaluator_versions"]["risk_language"] == "2"
            # Must appear exactly once in the text
            assert text.count("graded_evaluator_versions:") == 1
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

    def test_evaluator_versions_with_multiple_entries(self):
        """All entries in evaluator_versions are written and read back correctly."""
        p = _tmp_file("---\ntitle: T\n---\nBody.\n")
        ev = {
            "api_accuracy": "1",
            "code_syntax_check": "2",
            "consumer_usefulness": "2",
            "risk_language": "2",
        }
        try:
            write_grade(p, "B", model_sha="sha99", evaluator_versions=ev)
            stored = read_grade(p)
            assert stored["evaluator_versions"] == ev
        finally:
            p.unlink(missing_ok=True)

    def test_evaluator_versions_skip_check_logic(self):
        """Pages with matching evaluator_versions are classified as current by skip logic."""
        from content_eval import EVALUATOR_VERSIONS
        p = _tmp_file("---\ntitle: T\n---\nBody.\n")
        try:
            write_grade(p, "A", model_sha="sha1", evaluator_tier="full",
                        logic_version="15", evaluator_versions=EVALUATOR_VERSIONS)
            stored = read_grade(p)
            assert stored["tier"] == "full"
            # All evaluators should match EVALUATOR_VERSIONS
            for ev, ver in EVALUATOR_VERSIONS.items():
                assert stored["evaluator_versions"].get(ev) == ver, (
                    f"Mismatch for evaluator {ev}: expected {ver!r}, "
                    f"got {stored['evaluator_versions'].get(ev)!r}"
                )
        finally:
            p.unlink(missing_ok=True)
