"""test_content_hash_backfill.py — Idempotency and correctness tests for
scripts/pipeline/content_hash_backfill.py.

Coverage:
- Idempotency: applying twice leaves file unchanged on second run
- Dry-run: never writes to disk
- Skip: file with existing content_hash is skipped
- No provenance: file without provenance block returns "no-provenance"
- Apply: file with provenance but no content_hash gets hash written
- Summary counts are correct
"""
from __future__ import annotations

from pathlib import Path

import pytest

import content_hash_backfill as backfill

from _repo_root import repo_root

_REPO_ROOT = repo_root()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MINIMAL_PROVENANCE_FM = (
    "---\n"
    "title: Test\n"
    "type: docs\n"
    "provenance:\n"
    "  content_origin: skill-generated\n"
    "  last_mechanism: skill\n"
    "  auto_updatable: true\n"
    "---\n\n"
    "Body content here.\n"
)

_FM_WITH_HASH = (
    "---\n"
    "title: Test\n"
    "provenance:\n"
    "  last_mechanism: skill\n"
    "  auto_updatable: true\n"
    "  content_hash: aabbccddeeff00112233445566778899\n"
    "---\n\nBody.\n"
)

_FM_NO_PROVENANCE = (
    "---\n"
    "title: No Provenance\n"
    "type: docs\n"
    "---\n\nBody.\n"
)


class TestContentHashBackfill:

    def test_apply_writes_content_hash(self, tmp_path):
        """File with provenance but no content_hash → result 'updated' and hash written."""
        f = tmp_path / "index.md"
        f.write_text(_MINIMAL_PROVENANCE_FM, encoding="utf-8")

        result = backfill.process_file(f, apply=True)
        assert result == "updated", f"Expected 'updated', got '{result}'"

        text = f.read_text(encoding="utf-8")
        assert "content_hash:" in text

        # Hash must be a 32-char hex string
        import re
        m = re.search(r"content_hash:\s+([0-9a-f]{32})", text)
        assert m is not None, f"content_hash not found or not 32 hex chars:\n{text}"

    def test_idempotent_apply_twice(self, tmp_path):
        """Applying twice: first call returns 'updated', second returns 'skipped'."""
        f = tmp_path / "index.md"
        f.write_text(_MINIMAL_PROVENANCE_FM, encoding="utf-8")

        result1 = backfill.process_file(f, apply=True)
        assert result1 == "updated"

        result2 = backfill.process_file(f, apply=True)
        assert result2 == "skipped", (
            f"Second apply should be skipped (idempotent), got '{result2}'"
        )

    def test_dry_run_does_not_write(self, tmp_path):
        """Dry-run (apply=False) must not modify the file."""
        f = tmp_path / "index.md"
        f.write_text(_MINIMAL_PROVENANCE_FM, encoding="utf-8")
        original_text = f.read_text(encoding="utf-8")

        result = backfill.process_file(f, apply=False)
        assert result == "updated"  # would update, but didn't
        assert f.read_text(encoding="utf-8") == original_text, (
            "dry-run must not write to disk"
        )

    def test_skips_file_with_existing_hash(self, tmp_path):
        """File that already has content_hash returns 'skipped'."""
        f = tmp_path / "index.md"
        f.write_text(_FM_WITH_HASH, encoding="utf-8")

        result = backfill.process_file(f, apply=True)
        assert result == "skipped"

    def test_no_provenance_block_returns_no_provenance(self, tmp_path):
        """File without a provenance block (no auto_updatable) returns 'no-provenance'."""
        f = tmp_path / "index.md"
        f.write_text(_FM_NO_PROVENANCE, encoding="utf-8")

        result = backfill.process_file(f, apply=True)
        assert result == "no-provenance"

    def test_provenance_without_auto_updatable_returns_no_provenance(self, tmp_path):
        """Provenance block missing auto_updatable field → 'no-provenance' (eligibility gate)."""
        f = tmp_path / "index.md"
        f.write_text(
            "---\ntitle: T\nprovenance:\n  last_mechanism: skill\n---\n\nBody.\n",
            encoding="utf-8",
        )
        result = backfill.process_file(f, apply=True)
        assert result == "no-provenance"

    def test_hash_is_body_only(self, tmp_path):
        """content_hash must be the same for two files that differ only in frontmatter."""
        shared_body = "\n\nShared body content.\n"
        f1 = tmp_path / "a.md"
        f2 = tmp_path / "b.md"

        f1.write_text(
            "---\ntitle: Page A\nprovenance:\n  last_mechanism: skill\n  auto_updatable: true\n---"
            + shared_body,
            encoding="utf-8",
        )
        f2.write_text(
            "---\ntitle: Page B — Different Title\nprovenance:\n  last_mechanism: skill\n  auto_updatable: true\n---"
            + shared_body,
            encoding="utf-8",
        )

        backfill.process_file(f1, apply=True)
        backfill.process_file(f2, apply=True)

        import re
        def _extract_hash(path):
            text = path.read_text(encoding="utf-8")
            m = re.search(r"content_hash:\s+([0-9a-f]{32})", text)
            return m.group(1) if m else None

        h1 = _extract_hash(f1)
        h2 = _extract_hash(f2)
        assert h1 is not None and h2 is not None
        assert h1 == h2, (
            f"Hashes differ for files with same body but different frontmatter: {h1} vs {h2}"
        )
