"""test_provenance.py — Tests for provenance read/write/decision logic.

Verifies that the provenance system correctly:
- Reads and writes provenance blocks in frontmatter
- Preserves all non-provenance content byte-for-byte
- Updates only last_mechanism without touching other fields
- Computes source_sha and detects staleness
- Makes correct auto_updatable decisions
- Defaults to overwritable when no provenance exists (migration)
"""
import tempfile
import textwrap
from pathlib import Path

import pytest

from provenance import (
    read_provenance,
    write_provenance,
    update_mechanism,
    compute_source_sha,
    compute_content_hash,
    is_auto_updatable,
    is_stale,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tmp_md(content: str) -> Path:
    """Write content to a temp .md file and return its path."""
    f = tempfile.NamedTemporaryFile(
        suffix=".md", mode="w", encoding="utf-8", delete=False
    )
    f.write(textwrap.dedent(content))
    f.close()
    return Path(f.name)


def _cleanup(path: Path):
    path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MINIMAL_PAGE = """\
---
title: Test Page
description: A test page
type: docs
---

Some body content.
"""

PAGE_WITH_EVIDENCE = """\
---
title: Test Page
description: A test page
type: docs
evidence:
  model_sha: abc123
  model_version: 1.0.0
  claims:
  - CLM-001
---

Body with evidence.
"""

PAGE_WITH_PROVENANCE = """\
---
title: Test Page
description: A test page
provenance:
  content_origin: skill-generated
  last_mechanism: translator
  auto_updatable: true
  reviewed: false
---

Body text.
"""

PAGE_WITH_BOTH = """\
---
title: Test Page
evidence:
  model_sha: abc123
  model_version: 1.0.0
  claims: []
provenance:
  translation_origin: translator-batch
  source_file: content/docs.aspose.org/en/3d/python/_index.md
  source_sha: a1b2c3d4e5f6
  last_mechanism: translator
  auto_updatable: true
  reviewed: false
---

Full page.
"""

PAGE_NOT_UPDATABLE = """\
---
title: Protected Page
provenance:
  content_origin: human-authored
  last_mechanism: human-edit
  auto_updatable: false
  reviewed: true
---

Human-edited content.
"""

PAGE_WITH_LITERAL_BLOCK = """\
---
title: Code Page
description: |
  This is a multi-line
  description with literal block
type: docs
---

```python
print("hello")
```
"""


# ---------------------------------------------------------------------------
# test_provenance_read_write
# ---------------------------------------------------------------------------

class TestReadWrite:
    """Round-trip: write provenance, read back, fields match."""

    def test_write_and_read(self):
        p = _tmp_md(MINIMAL_PAGE)
        try:
            prov = {
                "content_origin": "skill-generated",
                "last_mechanism": "skill",
                "auto_updatable": True,
                "reviewed": False,
            }
            assert write_provenance(p, prov) is True
            result = read_provenance(p)
            assert result is not None
            assert result["content_origin"] == "skill-generated"
            assert result["last_mechanism"] == "skill"
            assert result["auto_updatable"] is True
            assert result["reviewed"] is False
        finally:
            _cleanup(p)

    def test_read_existing_provenance(self):
        p = _tmp_md(PAGE_WITH_PROVENANCE)
        try:
            result = read_provenance(p)
            assert result is not None
            assert result["content_origin"] == "skill-generated"
            assert result["auto_updatable"] is True
        finally:
            _cleanup(p)

    def test_read_absent_returns_none(self):
        p = _tmp_md(MINIMAL_PAGE)
        try:
            assert read_provenance(p) is None
        finally:
            _cleanup(p)

    def test_replace_existing_provenance(self):
        p = _tmp_md(PAGE_WITH_PROVENANCE)
        try:
            new_prov = {
                "content_origin": "agent-drafted",
                "last_mechanism": "agent-edit",
                "auto_updatable": False,
                "reviewed": True,
            }
            write_provenance(p, new_prov)
            result = read_provenance(p)
            assert result["content_origin"] == "agent-drafted"
            assert result["auto_updatable"] is False
        finally:
            _cleanup(p)

    def test_preserves_non_provenance_content(self):
        p = _tmp_md(PAGE_WITH_EVIDENCE)
        try:
            prov = {"last_mechanism": "translator", "auto_updatable": True}
            write_provenance(p, prov)
            text = p.read_text(encoding="utf-8")
            # Evidence block must still be present
            assert "model_sha: abc123" in text
            assert "CLM-001" in text
            # Title preserved
            assert "title: Test Page" in text
            # Body preserved
            assert "Body with evidence." in text
        finally:
            _cleanup(p)

    def test_preserves_literal_block_scalars(self):
        p = _tmp_md(PAGE_WITH_LITERAL_BLOCK)
        try:
            prov = {"last_mechanism": "skill", "auto_updatable": True}
            write_provenance(p, prov)
            text = p.read_text(encoding="utf-8")
            # Literal block scalar must be preserved
            assert "description: |\n" in text
            assert "  This is a multi-line" in text
            # Code block in body preserved
            assert '```python' in text
            assert 'print("hello")' in text
        finally:
            _cleanup(p)


# ---------------------------------------------------------------------------
# test_provenance_update_mechanism
# ---------------------------------------------------------------------------

class TestUpdateMechanism:
    """update_mechanism changes only last_mechanism, preserves all other fields."""

    def test_updates_existing(self):
        p = _tmp_md(PAGE_WITH_BOTH)
        try:
            update_mechanism(p, "evidence-attach")
            result = read_provenance(p)
            assert result["last_mechanism"] == "evidence-attach"
            # Other fields preserved
            assert result["translation_origin"] == "translator-batch"
            assert result["source_sha"] == "a1b2c3d4e5f6"
            assert result["auto_updatable"] is True
            assert result["source_file"] == "content/docs.aspose.org/en/3d/python/_index.md"
        finally:
            _cleanup(p)

    def test_creates_minimal_when_absent(self):
        p = _tmp_md(MINIMAL_PAGE)
        try:
            update_mechanism(p, "grade-writer")
            result = read_provenance(p)
            assert result["last_mechanism"] == "grade-writer"
            assert result["auto_updatable"] is True
        finally:
            _cleanup(p)

    def test_does_not_change_auto_updatable(self):
        p = _tmp_md(PAGE_NOT_UPDATABLE)
        try:
            update_mechanism(p, "evidence-attach")
            result = read_provenance(p)
            assert result["last_mechanism"] == "evidence-attach"
            # auto_updatable MUST stay false
            assert result["auto_updatable"] is False
            # content_origin preserved
            assert result["content_origin"] == "human-authored"
            assert result["reviewed"] is True
        finally:
            _cleanup(p)


# ---------------------------------------------------------------------------
# test_provenance_auto_updatable_default
# ---------------------------------------------------------------------------

class TestAutoUpdatableDefault:
    """Files without provenance block default to auto_updatable: true (migration)."""

    def test_no_provenance_returns_true(self):
        p = _tmp_md(MINIMAL_PAGE)
        try:
            assert is_auto_updatable(p) is True
        finally:
            _cleanup(p)

    def test_explicit_true(self):
        p = _tmp_md(PAGE_WITH_PROVENANCE)
        try:
            assert is_auto_updatable(p) is True
        finally:
            _cleanup(p)

    def test_explicit_false(self):
        p = _tmp_md(PAGE_NOT_UPDATABLE)
        try:
            assert is_auto_updatable(p) is False
        finally:
            _cleanup(p)

    def test_nonexistent_file_returns_true(self):
        p = Path(tempfile.gettempdir()) / "nonexistent_provenance_test.md"
        assert is_auto_updatable(p) is True


# ---------------------------------------------------------------------------
# test_provenance_staleness
# ---------------------------------------------------------------------------

class TestStaleness:
    """source_sha mismatch → stale; match → current."""

    def test_matching_sha_not_stale(self):
        en = _tmp_md(MINIMAL_PAGE)
        locale = _tmp_md(MINIMAL_PAGE)
        try:
            sha = compute_source_sha(en)
            write_provenance(locale, {
                "source_sha": sha,
                "last_mechanism": "translator",
                "auto_updatable": True,
            })
            assert is_stale(locale, en) is False
        finally:
            _cleanup(en)
            _cleanup(locale)

    def test_mismatched_sha_is_stale(self):
        en = _tmp_md(MINIMAL_PAGE)
        locale = _tmp_md(MINIMAL_PAGE)
        try:
            write_provenance(locale, {
                "source_sha": "000000000000",  # Wrong SHA
                "last_mechanism": "translator",
                "auto_updatable": True,
            })
            assert is_stale(locale, en) is True
        finally:
            _cleanup(en)
            _cleanup(locale)

    def test_no_provenance_is_stale(self):
        en = _tmp_md(MINIMAL_PAGE)
        locale = _tmp_md(MINIMAL_PAGE)
        try:
            assert is_stale(locale, en) is True
        finally:
            _cleanup(en)
            _cleanup(locale)


# ---------------------------------------------------------------------------
# test_source_sha
# ---------------------------------------------------------------------------

class TestSourceSha:
    """compute_source_sha returns consistent 12-char hex prefix."""

    def test_deterministic(self):
        p = _tmp_md(MINIMAL_PAGE)
        try:
            sha1 = compute_source_sha(p)
            sha2 = compute_source_sha(p)
            assert sha1 == sha2
            assert len(sha1) == 24
            assert all(c in "0123456789abcdef" for c in sha1)
        finally:
            _cleanup(p)

    def test_different_content_different_sha(self):
        p1 = _tmp_md(MINIMAL_PAGE)
        p2 = _tmp_md(PAGE_WITH_EVIDENCE)
        try:
            assert compute_source_sha(p1) != compute_source_sha(p2)
        finally:
            _cleanup(p1)
            _cleanup(p2)


# ---------------------------------------------------------------------------
# test_compute_content_hash
# ---------------------------------------------------------------------------

class TestComputeContentHash:
    """compute_content_hash returns 32-char SHA-256 of body text after frontmatter."""

    def test_returns_32_char_hex(self):
        p = _tmp_md(MINIMAL_PAGE)
        try:
            h = compute_content_hash(p)
            assert len(h) == 32
            assert all(c in "0123456789abcdef" for c in h)
        finally:
            _cleanup(p)

    def test_deterministic(self):
        p = _tmp_md(MINIMAL_PAGE)
        try:
            assert compute_content_hash(p) == compute_content_hash(p)
        finally:
            _cleanup(p)

    def test_changes_when_body_changes(self):
        body_a = "---\ntitle: T\n---\n\nBody A.\n"
        body_b = "---\ntitle: T\n---\n\nBody B — different.\n"
        pa = _tmp_md(body_a)
        pb = _tmp_md(body_b)
        try:
            assert compute_content_hash(pa) != compute_content_hash(pb)
        finally:
            _cleanup(pa)
            _cleanup(pb)

    def test_unchanged_when_only_frontmatter_changes(self):
        """Changing title in frontmatter must NOT change the content hash."""
        body_a = "---\ntitle: Title A\n---\n\nShared body.\n"
        body_b = "---\ntitle: Title B — different\n---\n\nShared body.\n"
        pa = _tmp_md(body_a)
        pb = _tmp_md(body_b)
        try:
            assert compute_content_hash(pa) == compute_content_hash(pb)
        finally:
            _cleanup(pa)
            _cleanup(pb)

    def test_file_without_frontmatter_hashes_whole_content(self):
        """A file with no --- fences → entire content is treated as body."""
        p = _tmp_md("No frontmatter here.\nJust text.\n")
        try:
            h = compute_content_hash(p)
            assert len(h) == 32
            assert h  # non-empty
        finally:
            _cleanup(p)

    def test_unreadable_file_returns_empty_string(self):
        """A path that does not exist returns empty string (not an exception)."""
        missing = Path(tempfile.gettempdir()) / "nonexistent_content_hash_test.md"
        result = compute_content_hash(missing)
        assert result == ""


# ---------------------------------------------------------------------------
# Write-once guard for content_created_at
# ---------------------------------------------------------------------------

class TestWriteOnceContentCreatedAt:
    """write_provenance() must preserve an existing content_created_at value."""

    def test_preserves_when_caller_omits_field(self, tmp_path):
        """If existing provenance has content_created_at and caller omits it, value is kept."""
        p = tmp_path / "page.md"
        p.write_text("---\ntitle: Test\n---\nBody.\n", encoding="utf-8")
        write_provenance(p, {"content_origin": "unknown", "content_created_at": "2025-01-15T00:00:00Z"})

        # Now write again WITHOUT content_created_at
        write_provenance(p, {"content_origin": "skill-generated"})

        prov = read_provenance(p)
        assert prov["content_created_at"] == "2025-01-15T00:00:00Z"
        assert prov["content_origin"] == "skill-generated"

    def test_preserves_when_caller_tries_to_change_value(self, tmp_path):
        """If caller passes a different content_created_at, existing value wins."""
        p = tmp_path / "page.md"
        p.write_text("---\ntitle: Test\n---\nBody.\n", encoding="utf-8")
        write_provenance(p, {"content_origin": "unknown", "content_created_at": "2025-01-15T00:00:00Z"})

        write_provenance(p, {"content_origin": "unknown", "content_created_at": "2099-01-01T00:00:00Z"})

        prov = read_provenance(p)
        assert prov["content_created_at"] == "2025-01-15T00:00:00Z"

    def test_no_guard_when_field_not_yet_set(self, tmp_path):
        """If no content_created_at exists yet, caller's value is written normally."""
        p = tmp_path / "page.md"
        p.write_text("---\ntitle: Test\n---\nBody.\n", encoding="utf-8")
        write_provenance(p, {"content_origin": "unknown"})

        write_provenance(p, {"content_origin": "unknown", "content_created_at": "2025-06-01T00:00:00Z"})

        prov = read_provenance(p)
        assert prov["content_created_at"] == "2025-06-01T00:00:00Z"
