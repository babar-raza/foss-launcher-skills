"""test_fix_last_mechanism.py — Tests for the last_mechanism repair script."""
import tempfile
import textwrap
from pathlib import Path

import pytest

from fix_last_mechanism import determine_replacement, process_file


def _tmp_md(content: str) -> Path:
    f = tempfile.NamedTemporaryFile(
        suffix=".md", mode="w", encoding="utf-8", delete=False
    )
    f.write(textwrap.dedent(content))
    f.close()
    return Path(f.name)


class TestDetermineReplacement:
    def test_skill_generated_maps_to_skill(self):
        assert determine_replacement({"content_origin": "skill-generated"}) == "skill"

    def test_unknown_origin_maps_to_unknown(self):
        assert determine_replacement({"content_origin": "unknown"}) == "unknown"

    def test_missing_origin_maps_to_unknown(self):
        assert determine_replacement({}) == "unknown"

    def test_human_authored_maps_to_unknown(self):
        assert determine_replacement({"content_origin": "human-authored"}) == "unknown"


class TestProcessFile:
    _STALE = frozenset({"grade-writer"})

    def test_repairs_grade_writer_skill_generated(self):
        """grade-writer with skill-generated origin → repaired to skill."""
        p = _tmp_md("""\
            ---
            title: Test
            provenance:
              content_origin: skill-generated
              last_mechanism: grade-writer
              auto_updatable: true
            ---

            Body.
        """)
        try:
            result = process_file(p, self._STALE, apply=True)
            assert result == "repaired"
            from provenance import read_provenance
            prov = read_provenance(p)
            assert prov["last_mechanism"] == "skill"
            assert prov["content_origin"] == "skill-generated"
        finally:
            p.unlink(missing_ok=True)

    def test_repairs_grade_writer_unknown_origin(self):
        """grade-writer with unknown origin → repaired to unknown."""
        p = _tmp_md("""\
            ---
            title: Test
            provenance:
              content_origin: unknown
              last_mechanism: grade-writer
              auto_updatable: true
            ---

            Body.
        """)
        try:
            result = process_file(p, self._STALE, apply=True)
            assert result == "repaired"
            from provenance import read_provenance
            prov = read_provenance(p)
            assert prov["last_mechanism"] == "unknown"
        finally:
            p.unlink(missing_ok=True)

    def test_skips_valid_mechanism(self):
        """File with valid last_mechanism should be skipped."""
        p = _tmp_md("""\
            ---
            title: Test
            provenance:
              content_origin: skill-generated
              last_mechanism: skill
              auto_updatable: true
            ---

            Body.
        """)
        try:
            result = process_file(p, self._STALE, apply=True)
            assert result == "skipped"
        finally:
            p.unlink(missing_ok=True)

    def test_dry_run_does_not_modify(self):
        """Dry-run mode should not modify the file."""
        p = _tmp_md("""\
            ---
            title: Test
            provenance:
              content_origin: skill-generated
              last_mechanism: grade-writer
              auto_updatable: true
            ---

            Body.
        """)
        try:
            original = p.read_text(encoding="utf-8")
            result = process_file(p, self._STALE, apply=False)
            assert result == "repaired"
            assert p.read_text(encoding="utf-8") == original
        finally:
            p.unlink(missing_ok=True)

    def test_no_provenance_skipped(self):
        """File without provenance returns no-provenance."""
        p = _tmp_md("""\
            ---
            title: Test
            ---

            Body.
        """)
        try:
            result = process_file(p, self._STALE, apply=True)
            assert result == "no-provenance"
        finally:
            p.unlink(missing_ok=True)

    def test_preserves_other_fields(self):
        """Repair should preserve content_origin, auto_updatable, content_hash."""
        p = _tmp_md("""\
            ---
            title: Test
            provenance:
              content_origin: skill-generated
              last_mechanism: grade-writer
              auto_updatable: true
              content_hash: abcdef1234567890abcdef1234567890
            ---

            Body.
        """)
        try:
            process_file(p, self._STALE, apply=True)
            from provenance import read_provenance
            prov = read_provenance(p)
            assert prov["content_origin"] == "skill-generated"
            assert prov["auto_updatable"] is True
            assert prov["content_hash"] == "abcdef1234567890abcdef1234567890"
            assert prov["last_mechanism"] == "skill"
        finally:
            p.unlink(missing_ok=True)
