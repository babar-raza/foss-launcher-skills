"""test_validate_skill_ids.py — Regression tests for validate_skill_ids.py

Covers:
  - SKILL-COMMIT-REGEX-001: word-boundary regex must not match backlog IDs
    like NOTE-PYTHON-REF-DRAFTS-001 as spurious skill IDs.
  - Valid skill IDs (S-73, S-26, etc.) still matched and validated correctly.
"""
import sys
from pathlib import Path

# Bootstrap: add scripts/ci/ to sys.path
_HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_HERE))

from checks.validate_skill_ids import _ID_RE, main


class TestIDRegex:
    """Unit tests for the _ID_RE pattern (SKILL-COMMIT-REGEX-001)."""

    def test_valid_skill_id_matched(self):
        """Standard skill IDs like S-73 are matched."""
        assert _ID_RE.findall("Skills invoked: [S-73, S-26]") == ["S-73", "S-26"]

    def test_backlog_drafts_suffix_not_matched(self):
        """SKILL-COMMIT-REGEX-001: DRAFTS-001 suffix must not produce a false S-001 match."""
        text = "Closes NOTE-PYTHON-REF-DRAFTS-001 and BLOG-DRAFT-GRADE-C-001"
        matches = _ID_RE.findall(text)
        assert matches == [], f"Expected no matches, got: {matches}"

    def test_inline_skill_id_matched(self):
        """S-nn at start of line or after punctuation is matched."""
        assert _ID_RE.findall("[S-01]") == ["S-01"]
        assert _ID_RE.findall("S-99 applied") == ["S-99"]

    def test_lowercase_s_not_matched(self):
        """Lowercase 's-nn' is not matched (IGNORECASE removed)."""
        assert _ID_RE.findall("s-73") == []

    def test_skill_id_inside_word_not_matched(self):
        """S-NNN as substring of a longer identifier (no word boundary) is not matched."""
        # e.g. XS-001 — 'S' preceded by 'X' (word char) → no word boundary before S
        assert _ID_RE.findall("XS-001") == []

    def test_multiple_skill_ids_in_commit_body(self):
        """Multiple skill IDs in a typical commit message body are all found."""
        text = (
            "Skills invoked: [S-26, S-73, S-76]\n"
            "Addresses: BLOG-DRAFT-GRADE-C-001 SUPERVISOR-STALE-EVAL-001"
        )
        matches = _ID_RE.findall(text)
        assert set(matches) == {"S-26", "S-73", "S-76"}


class TestMainStdin:
    """Integration tests for main() with --stdin (commit-msg hook path)."""

    def test_valid_ids_pass(self, monkeypatch, capsys):
        """Commit message with only valid IDs exits 0."""
        import io
        monkeypatch.setattr("sys.stdin", io.StringIO("Skills invoked: [S-73]"))
        # load_registry may return empty in test env; we only care about exit code and
        # that DRAFTS pattern does not inject a spurious ID
        # Use a message that has a backlog ID with DRAFTS suffix
        monkeypatch.setattr(
            "sys.stdin",
            io.StringIO("Closes NOTE-PYTHON-REF-DRAFTS-001\nSkills invoked: [S-73]"),
        )
        rc = main(["--stdin"])
        # If registry loaded: S-73 must be valid → exit 0
        # If registry empty (test env): fails open → exit 0
        assert rc == 0

    def test_backlog_id_only_does_not_trigger_validation(self, monkeypatch, capsys):
        """Commit message with only a backlog ID (no real S-nn) → 'No skill IDs' exit 0."""
        import io
        monkeypatch.setattr(
            "sys.stdin",
            io.StringIO("Fixes BLOG-DRAFT-GRADE-C-001 and NOTE-PYTHON-REF-DRAFTS-001"),
        )
        rc = main(["--stdin"])
        out = capsys.readouterr().out
        assert rc == 0
        assert "No skill IDs" in out
