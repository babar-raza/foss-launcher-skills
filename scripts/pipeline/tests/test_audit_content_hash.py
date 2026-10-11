"""test_audit_content_hash.py — Tests for the content hash audit script."""
import tempfile
import textwrap
from pathlib import Path

import pytest

from audit_content_hash import audit_file, main


def _tmp_md(content: str) -> Path:
    f = tempfile.NamedTemporaryFile(
        suffix=".md", mode="w", encoding="utf-8", delete=False
    )
    f.write(textwrap.dedent(content))
    f.close()
    return Path(f.name)


class TestAuditFile:
    def test_matching_hash_returns_none(self):
        """File with correct content_hash should report no mismatch."""
        from provenance import compute_content_hash

        p = _tmp_md("""\
            ---
            title: Test
            provenance:
              content_origin: skill-generated
              last_mechanism: skill
              auto_updatable: true
              content_hash: placeholder
            ---

            Body text here.
        """)
        try:
            # Compute the real hash and write it
            real_hash = compute_content_hash(p)
            text = p.read_text(encoding="utf-8")
            text = text.replace("placeholder", real_hash)
            p.write_text(text, encoding="utf-8")

            result = audit_file(p)
            assert result is None
        finally:
            p.unlink(missing_ok=True)

    def test_stale_hash_returns_mismatch(self):
        """File with wrong content_hash should report a mismatch."""
        p = _tmp_md("""\
            ---
            title: Test
            provenance:
              content_origin: skill-generated
              last_mechanism: skill
              auto_updatable: true
              content_hash: 0000000000000000000000000000dead
            ---

            Body text here.
        """)
        try:
            result = audit_file(p)
            assert result is not None
            assert result["stored"] == "0000000000000000000000000000dead"
            assert result["computed"] != result["stored"]
        finally:
            p.unlink(missing_ok=True)

    def test_no_provenance_returns_none(self):
        """File without provenance block should be skipped."""
        p = _tmp_md("""\
            ---
            title: Test
            ---

            Body text here.
        """)
        try:
            result = audit_file(p)
            assert result is None
        finally:
            p.unlink(missing_ok=True)

    def test_no_hash_field_returns_none(self):
        """File with provenance but no content_hash should be skipped."""
        p = _tmp_md("""\
            ---
            title: Test
            provenance:
              content_origin: skill-generated
              last_mechanism: skill
              auto_updatable: true
            ---

            Body text here.
        """)
        try:
            result = audit_file(p)
            assert result is None
        finally:
            p.unlink(missing_ok=True)


class TestMainCLI:
    def test_specific_file_clean(self, tmp_path):
        """CLI with --files on a clean file exits 0."""
        from provenance import compute_content_hash

        md = tmp_path / "test.md"
        md.write_text("---\ntitle: T\nprovenance:\n  content_hash: placeholder\n  auto_updatable: true\n---\n\nBody.\n", encoding="utf-8")
        real_hash = compute_content_hash(md)
        md.write_text(f"---\ntitle: T\nprovenance:\n  content_hash: {real_hash}\n  auto_updatable: true\n---\n\nBody.\n", encoding="utf-8")

        rc = main(["--files", str(md)])
        assert rc == 0

    def test_specific_file_stale(self, tmp_path):
        """CLI with --files on a stale file exits 1."""
        md = tmp_path / "test.md"
        md.write_text("---\ntitle: T\nprovenance:\n  content_hash: deadbeef0000000000000000000dead0\n  auto_updatable: true\n---\n\nBody.\n", encoding="utf-8")

        rc = main(["--files", str(md)])
        assert rc == 1


# ── RPR-F-04: frontmatter-only-refresh detection ─────────────────────────────

from audit_content_hash import (  # noqa: E402
    is_frontmatter_only_change,
    is_evidence_only_grade_regression,
)


def _page(evidence_sha: str, grade: str, body: str) -> str:
    return (
        "---\n"
        "title: FAQ\n"
        "evidence:\n"
        f"  model_sha: {evidence_sha}\n"
        "  claims:\n"
        "  - CLM-x\n"
        f"grade: {grade}\n"
        "---\n\n"
        f"{body}\n"
    )


class TestFrontmatterOnlyChange:
    def test_flags_model_sha_change_with_identical_body_hash(self):
        old = _page("aaa", "A", "Identical body prose.")
        new = _page("bbb", "A", "Identical body prose.")  # evidence bumped, body same
        v = is_frontmatter_only_change(old, new)
        assert v is not None
        assert v["body_identical"] is True
        assert v["old_model_sha"] == "aaa"
        assert v["new_model_sha"] == "bbb"

    def test_no_flag_when_body_changed(self):
        old = _page("aaa", "A", "Old body prose.")
        new = _page("bbb", "A", "New, different body prose.")
        assert is_frontmatter_only_change(old, new) is None

    def test_no_flag_when_evidence_unchanged(self):
        old = _page("aaa", "A", "Same body.")
        new = _page("aaa", "A", "Same body.")
        assert is_frontmatter_only_change(old, new) is None

    def test_body_hash_whitespace_insensitive(self):
        """CRLF / trailing-whitespace differences in the body are not 'body changed'."""
        old = _page("aaa", "A", "Body line one.")
        new = _page("bbb", "A", "Body line one.  ")  # trailing spaces only
        assert is_frontmatter_only_change(old, new) is not None


class TestEvidenceOnlyGradeRegression:
    def test_a_to_c_kb_page_regression_fixture_flagged(self):
        """The exact PDF-NET-REFRESH-001 v26.7.0 defect: identical body, evidence
        model_sha bumped, grade dropped A->C."""
        old = _page("d42e9f1e", "A", "The FAQ answer text, unchanged.")
        new = _page("8a3131b9", "C", "The FAQ answer text, unchanged.")
        v = is_evidence_only_grade_regression(old, new)
        assert v is not None
        assert v["grade_before"] == "A"
        assert v["grade_after"] == "C"

    def test_no_regression_when_grade_same(self):
        old = _page("aaa", "A", "Same body.")
        new = _page("bbb", "A", "Same body.")  # frontmatter-only but grade unchanged
        assert is_evidence_only_grade_regression(old, new) is None

    def test_grade_improvement_not_flagged(self):
        old = _page("aaa", "C", "Same body.")
        new = _page("bbb", "A", "Same body.")  # improvement, not a regression
        assert is_evidence_only_grade_regression(old, new) is None

    def test_no_regression_when_body_changed(self):
        old = _page("aaa", "A", "Old body.")
        new = _page("bbb", "C", "New body entirely.")  # body changed → not frontmatter-only
        assert is_evidence_only_grade_regression(old, new) is None
