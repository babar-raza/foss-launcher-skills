"""test_provenance_normalize_hash.py — Tests for hash normalization script."""
import textwrap
from pathlib import Path

import pytest

from provenance import compute_content_hash, read_provenance
from provenance_normalize_hash import normalize_file


def test_provenance_normalize_hash_importable():
    """Smoke test: provenance_normalize_hash.py resolves sys.path correctly.

    Guards against regression where _HERE.parent.parent.parent.parent (repo root)
    was inserted instead of _HERE.parent.parent (scripts/pipeline/), causing
    ModuleNotFoundError: No module named 'provenance' on every hook invocation.
    """
    import provenance_normalize_hash  # noqa: F401
    from provenance import compute_content_hash, read_provenance, write_provenance  # noqa: F401
    assert callable(compute_content_hash)
    assert callable(read_provenance)
    assert callable(write_provenance)


def _write_md(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


class TestNormalizeFile:
    def test_updates_stale_hash(self, tmp_path):
        """File with wrong content_hash should be updated."""
        p = _write_md(tmp_path, "test.md", """\
            ---
            title: Test
            provenance:
              content_origin: skill-generated
              last_mechanism: skill
              auto_updatable: true
              content_hash: 00000000000000000000000000000000
            ---

            Body text here.
        """)
        result = normalize_file(p, apply=True)
        assert result == "updated"
        prov = read_provenance(p)
        assert prov["content_hash"] == compute_content_hash(p)

    def test_skips_current_hash(self, tmp_path):
        """File with correct hash should be skipped."""
        p = _write_md(tmp_path, "test.md", """\
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
        # Write the correct hash
        real_hash = compute_content_hash(p)
        text = p.read_text(encoding="utf-8").replace("placeholder", real_hash)
        p.write_text(text, encoding="utf-8")

        result = normalize_file(p, apply=True)
        assert result == "skipped"

    def test_adds_missing_hash(self, tmp_path):
        """File with provenance but no content_hash gets hash added."""
        p = _write_md(tmp_path, "test.md", """\
            ---
            title: Test
            provenance:
              content_origin: skill-generated
              last_mechanism: skill
              auto_updatable: true
            ---

            Body text here.
        """)
        result = normalize_file(p, apply=True)
        assert result == "updated"
        prov = read_provenance(p)
        assert prov["content_hash"] == compute_content_hash(p)

    def test_no_provenance_skipped(self, tmp_path):
        """File without provenance block should be skipped."""
        p = _write_md(tmp_path, "test.md", """\
            ---
            title: Test
            ---

            Body text here.
        """)
        result = normalize_file(p, apply=True)
        assert result == "no-provenance"

    def test_dry_run_does_not_modify(self, tmp_path):
        """Dry-run should not write to disk."""
        p = _write_md(tmp_path, "test.md", """\
            ---
            title: Test
            provenance:
              content_origin: skill-generated
              last_mechanism: skill
              auto_updatable: true
              content_hash: 00000000000000000000000000000000
            ---

            Body text here.
        """)
        original = p.read_text(encoding="utf-8")
        result = normalize_file(p, apply=False)
        assert result == "updated"
        assert p.read_text(encoding="utf-8") == original

    def test_preserves_last_mechanism(self, tmp_path):
        """Normalization must not overwrite last_mechanism."""
        p = _write_md(tmp_path, "test.md", """\
            ---
            title: Test
            provenance:
              content_origin: skill-generated
              last_mechanism: agent-edit
              auto_updatable: true
              content_hash: 00000000000000000000000000000000
            ---

            Body text here.
        """)
        normalize_file(p, apply=True)
        prov = read_provenance(p)
        assert prov["last_mechanism"] == "agent-edit"

    def test_preserves_content_created_at(self, tmp_path):
        """Normalization must not overwrite content_created_at."""
        p = _write_md(tmp_path, "test.md", """\
            ---
            title: Test
            provenance:
              content_origin: skill-generated
              last_mechanism: skill
              auto_updatable: true
              content_hash: 00000000000000000000000000000000
              content_created_at: "2026-01-01T00:00:00Z"
            ---

            Body text here.
        """)
        normalize_file(p, apply=True)
        prov = read_provenance(p)
        assert "2026-01-01" in str(prov["content_created_at"])

    def test_idempotent(self, tmp_path):
        """Running normalize twice should produce no change on second run."""
        p = _write_md(tmp_path, "test.md", """\
            ---
            title: Test
            provenance:
              content_origin: skill-generated
              last_mechanism: skill
              auto_updatable: true
              content_hash: 00000000000000000000000000000000
            ---

            Body text here.
        """)
        result1 = normalize_file(p, apply=True)
        assert result1 == "updated"
        content_after_first = p.read_text(encoding="utf-8")

        result2 = normalize_file(p, apply=True)
        assert result2 == "skipped"
        assert p.read_text(encoding="utf-8") == content_after_first
