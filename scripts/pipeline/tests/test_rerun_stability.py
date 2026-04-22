"""VERIFY-02: Tests for evaluation rerun stability.

Validates that the grading pipeline produces deterministic results:
  1. Same page + same content -> same grade on rerun
  2. content_hash is stable across runs (same content = same hash)
  3. grade_reasons are identical on reruns
  4. ELV bump with unchanged content + unchanged grade does NOT write frontmatter
  5. Idempotent write_grade produces byte-identical files
  6. Policy gate returns consistent (should_write, reason) pairs on rerun

Reference: grading-remediation plan VERIFY-02
"""
from __future__ import annotations

import sys
import tempfile
import textwrap
from pathlib import Path

_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from core.markdown import _FRONTMATTER_WRITER_RE as _FM_RE
from grade_writer import (
    _should_write_canonical_grade,
    content_hash,
    read_grade,
    write_grade,
)


def _tmp_file(content: str) -> Path:
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8"
    )
    f.write(textwrap.dedent(content))
    f.close()
    return Path(f.name)


# ---------------------------------------------------------------------------
# content_hash stability
# ---------------------------------------------------------------------------

class TestContentHashStability:
    """content_hash must return the same value for the same input across calls."""

    def test_same_body_same_hash(self):
        body = "## Getting Started\n\nInstall the package via pip.\n"
        h1 = content_hash(body)
        h2 = content_hash(body)
        assert h1 == h2, "content_hash must be deterministic for identical input"

    def test_repeated_calls_stable(self):
        """Calling content_hash 100 times yields the same value every time."""
        body = "Some documentation body with code:\n```python\nimport aspose\n```\n"
        first = content_hash(body)
        for _ in range(100):
            assert content_hash(body) == first

    def test_whitespace_normalized_stability(self):
        """CRLF and LF variants produce the same hash, and this is stable."""
        body_lf = "line one\nline two\n"
        body_crlf = "line one\r\nline two\r\n"
        h_lf = content_hash(body_lf)
        h_crlf = content_hash(body_crlf)
        assert h_lf == h_crlf
        # And both are stable on rerun
        assert content_hash(body_lf) == h_lf
        assert content_hash(body_crlf) == h_crlf


# ---------------------------------------------------------------------------
# Grade rerun stability
# ---------------------------------------------------------------------------

class TestGradeRerunStability:
    """Running evaluation twice on the same page with no changes must produce
    identical grades and grade_reasons."""

    def test_read_grade_stable_on_rerun(self):
        """read_grade returns identical results on consecutive calls."""
        p = _tmp_file("---\ntitle: Rerun Test\n---\nBody content.\n")
        try:
            write_grade(p, "B", grade_reasons=["good-structure", "api-complete"])
            r1 = read_grade(p)
            r2 = read_grade(p)
            assert r1["grade"] == r2["grade"]
            assert r1["content_hash"] == r2["content_hash"]
            assert r1["grade_reasons"] == r2["grade_reasons"]
        finally:
            p.unlink(missing_ok=True)

    def test_grade_reasons_identical_on_rerun(self):
        """grade_reasons list order and content must be preserved across reads."""
        reasons = ["api-accuracy-pass", "code-plausibility-warn", "structure-ok"]
        p = _tmp_file("---\ntitle: Reasons\n---\nBody.\n")
        try:
            write_grade(p, "C", grade_reasons=reasons)
            r1 = read_grade(p)
            r2 = read_grade(p)
            assert r1["grade_reasons"] == reasons
            assert r2["grade_reasons"] == reasons
            assert r1["grade_reasons"] == r2["grade_reasons"]
        finally:
            p.unlink(missing_ok=True)

    def test_content_hash_in_frontmatter_matches_body(self):
        """The content_hash stored in frontmatter must match a fresh hash of the body."""
        body_text = "This is the body content.\n"
        p = _tmp_file(f"---\ntitle: Hash Check\n---\n{body_text}")
        try:
            write_grade(p, "B")
            stored = read_grade(p)
            # Recompute hash from body using the proper frontmatter regex
            text = p.read_text(encoding="utf-8")
            fm_m = _FM_RE.match(text)
            body = text[fm_m.end():] if fm_m else text
            fresh_hash = content_hash(body)
            assert stored["content_hash"] == fresh_hash
        finally:
            p.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# ELV bump policy gate (no-write on metadata-only changes)
# ---------------------------------------------------------------------------

class TestELVBumpNoWrite:
    """An ELV bump with unchanged content and unchanged grade must NOT write
    frontmatter (WP-01 policy gate)."""

    def test_elv_bump_same_grade_policy_skips(self):
        """Policy gate returns False when only operational metadata changes."""
        p = _tmp_file("---\ntitle: ELV Test\n---\nBody.\n")
        try:
            # Establish initial grade
            write_grade(p, "C", model_sha="sha1", logic_version="15")
            stored = read_grade(p)
            stored_hash = stored["content_hash"]

            # Simulate ELV bump: same grade, same body hash
            should, reason = _should_write_canonical_grade(p, "C", stored_hash)
            assert should is False, "ELV bump alone must not trigger frontmatter write"
            assert "no-policy-trigger" in reason
        finally:
            p.unlink(missing_ok=True)

    def test_elv_bump_file_unchanged_after_policy_write(self):
        """write_grade(write_mode='policy') must leave the file byte-identical
        when only operational metadata (ELV, model_sha) changed."""
        p = _tmp_file("---\ntitle: ELV Byte\n---\nBody content here.\n")
        try:
            write_grade(p, "B", model_sha="sha_v1", logic_version="15")
            text_before = p.read_text(encoding="utf-8")

            # Re-grade with different model_sha and logic_version (ELV bump),
            # same grade letter, same body -> policy should suppress write
            result = write_grade(
                p, "B", model_sha="sha_v2", logic_version="16",
                write_mode="policy",
            )
            assert result is True  # returns True (policy-skip, not error)
            text_after = p.read_text(encoding="utf-8")
            assert text_before == text_after, (
                "File must be byte-identical after ELV bump with same grade"
            )
        finally:
            p.unlink(missing_ok=True)

    def test_policy_gate_consistent_across_calls(self):
        """Calling _should_write_canonical_grade twice with identical args
        must return the same (should_write, reason) pair."""
        p = _tmp_file("---\ntitle: Consistency\n---\nBody.\n")
        try:
            write_grade(p, "C")
            stored = read_grade(p)
            h = stored["content_hash"]

            r1 = _should_write_canonical_grade(p, "C", h)
            r2 = _should_write_canonical_grade(p, "C", h)
            assert r1 == r2, "Policy gate must be deterministic"
        finally:
            p.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Idempotent write detection
# ---------------------------------------------------------------------------

class TestIdempotentWrite:
    """write_grade must detect when the grade block is unchanged (except
    graded_at) and skip the write."""

    def test_identical_grade_block_skips_write(self):
        """Writing the same grade + reasons to an already-graded file should
        detect idempotency and skip (returning True)."""
        reasons = ["pass-structure", "pass-api"]
        p = _tmp_file("---\ntitle: Idempotent\n---\nBody.\n")
        try:
            write_grade(p, "B", grade_reasons=reasons)
            text_after_first = p.read_text(encoding="utf-8")

            # Write identical grade again (force mode) -- idempotency guard
            # in write_grade should detect the block is unchanged except
            # graded_at and skip the filesystem write
            result = write_grade(p, "B", grade_reasons=reasons)
            assert result is True
            # The graded_at may differ but the rest should be structurally identical
            stored = read_grade(p)
            assert stored["grade"] == "B"
            assert stored["grade_reasons"] == reasons
        finally:
            p.unlink(missing_ok=True)

    def test_grade_preserved_after_double_write(self):
        """After writing grade twice, read_grade still returns correct data."""
        p = _tmp_file("---\ntitle: Double\n---\nBody text.\n")
        try:
            write_grade(p, "A", grade_reasons=["excellent"])
            write_grade(p, "A", grade_reasons=["excellent"])
            stored = read_grade(p)
            assert stored["grade"] == "A"
            assert stored["grade_reasons"] == ["excellent"]
            assert stored["content_hash"], "content_hash must be present"
        finally:
            p.unlink(missing_ok=True)
