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

from checks.validate_skill_ids import _ID_RE, main, load_registry, _load_from_registry_json


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


class TestRegistrySourceOfTruth:
    """TC-CIR-08 (2026-08-14, CI reliability reassessment, Root Cause E): the registry
    must be read from skills/registry.json (matching check_commit_skill_provenance.py's
    source exactly), not parsed from markdown prose as a second, independently-drifting
    source of truth. Real repo state, no mocking — this repo's registry.json is tracked
    and its currency is independently enforced by check_skill_registry_json.py."""

    def test_loads_real_registry_json(self):
        registry = _load_from_registry_json()
        assert registry is not None, "skills/registry.json must be readable in this repo"
        assert len(registry) > 50, "registry should contain the repo's real ~112 skills"
        assert "S-01" in registry
        assert "S-99" in registry

    def test_load_registry_matches_json_source_exactly(self):
        """load_registry() (the public entry point) must return the same set as the
        JSON-only loader when registry.json is present — no silent divergence."""
        assert load_registry() == _load_from_registry_json()

    def test_falls_back_when_registry_json_missing(self, monkeypatch, tmp_path):
        """A fresh clone before the first sync_providers.py run has no registry.json —
        must fall back to markdown parsing, not fail closed or crash."""
        import checks.validate_skill_ids as vsi
        missing = tmp_path / "does-not-exist.json"
        monkeypatch.setattr(vsi, "REGISTRY_JSON", missing)
        result = vsi._load_from_registry_json()
        assert result is None, "missing registry.json must return None, not an empty set"
        # load_registry() must still return a usable (non-crashing) result via fallback
        registry = vsi.load_registry()
        assert isinstance(registry, frozenset)
