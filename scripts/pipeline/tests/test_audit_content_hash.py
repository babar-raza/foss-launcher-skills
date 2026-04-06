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
