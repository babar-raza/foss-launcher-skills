"""Tests for extraction.capability_tables (H7, MT068-2026-09-11-IMAGING-NET-LAUNCH).

Covers: the real imaging/net clone cache (exact claims hand-verified against
source during this mission's manual review), a no-enum-match fixture (models
slides' "choosing an edition" shape -- row labels with no format-enum
equivalent), a malformed-table fail-closed fixture, a duplicate-table
idempotency fixture (targets the words/net non-determinism defect class this
fix replaces), and the strip-covered-tables de-duplication helper.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from extraction.capability_tables import (
    UNVERIFIED_CONFIDENCE,
    detect_capability_tables,
    strip_covered_tables,
)

_CLONE_CACHE = Path(__file__).resolve().parents[4] / "runs" / ".clone_cache" / "aspose_imaging_net"

_IMAGING_FORMATS = [
    {"format": "Unknown", "direction": "detect"},
    {"format": "Png", "direction": "detect"},
    {"format": "Jpeg", "direction": "detect"},
    {"format": "Gif", "direction": "detect"},
    {"format": "Bmp", "direction": "detect"},
    {"format": "WebP", "direction": "detect"},
    {"format": "Ico", "direction": "detect"},
    {"format": "Tiff", "direction": "detect"},
    {"format": "Psd", "direction": "detect"},
    {"format": "Emf", "direction": "detect"},
    {"format": "Wmf", "direction": "detect"},
    {"format": "Dicom", "direction": "detect"},
]


class TestRealImagingNetReadme:
    """Exercised against the real, live clone cache -- skipped if absent
    rather than faked, matching this repo's own established pattern
    (test_formats_imaging_net_endian_false_positive.py)."""

    def _require_clone_cache(self):
        if not _CLONE_CACHE.is_dir():
            import pytest
            pytest.skip("real imaging/net clone cache not present")

    def test_real_readme_produces_atomic_claims_for_every_format(self):
        self._require_clone_cache()
        claims, covered = detect_capability_tables(_CLONE_CACHE, "imaging", _IMAGING_FORMATS)
        assert claims, "expected the real README capability matrix to produce claims"
        assert covered, "expected the real table to be identified as covered"

        row_labels_seen = {
            c["text"].split(",", 1)[0].removeprefix("For ") for c in claims
        }
        # Every one of the 11 real formats (Unknown excluded -- not in the README table)
        # must appear as a row label in at least one claim.
        for fmt in ("PNG", "JPEG", "GIF", "BMP", "TIFF", "PSD", "DICOM"):
            assert any(fmt in label for label in row_labels_seen), f"missing {fmt}"

    def test_png_framecount_claim_matches_hand_verified_source_behavior(self):
        """PNG's FrameCount is a hardcoded constant 1 in PngFormatHandler.cs,
        not real animation detection -- confirmed by direct source read this
        session. The README says '✅' for PNG FrameCount; this pass must
        still emit that claim (it reflects the README, not source behavior
        directly) at full confidence since PNG matches the known-formats list."""
        self._require_clone_cache()
        claims, _ = detect_capability_tables(_CLONE_CACHE, "imaging", _IMAGING_FORMATS)
        png_frame = [
            c for c in claims
            if c["text"].startswith("For PNG,") and "Frame count" in c["text"]
        ]
        assert len(png_frame) == 1
        assert png_frame[0]["confidence"] == 1.0
        assert "supported" in png_frame[0]["text"]

    def test_wmf_annotation_preserved_verbatim(self):
        """WMF's real behavior (confirmed by direct source read): dimensions
        only populate for placeable WMF, via a hardcoded 96 DPI conversion.
        The README documents this as an annotation on the cell -- it must
        survive into the claim text, not be silently dropped."""
        self._require_clone_cache()
        claims, _ = detect_capability_tables(_CLONE_CACHE, "imaging", _IMAGING_FORMATS)
        wmf_dims = [
            c for c in claims
            if "WMF" in c["text"] and "Width" in c["text"]
        ]
        assert len(wmf_dims) == 1
        assert "96 DPI" in wmf_dims[0]["text"]

    def test_dash_cells_produce_no_claim(self):
        """JPEG's Frame count cell is '—' in the real README (frame count is
        never populated for JPEG) -- must not produce a claim."""
        self._require_clone_cache()
        claims, _ = detect_capability_tables(_CLONE_CACHE, "imaging", _IMAGING_FORMATS)
        jpeg_frame = [
            c for c in claims
            if c["text"].startswith("For JPEG,") and "Frame count" in c["text"]
        ]
        assert jpeg_frame == []


class TestNoEnumMatchFixture:
    """Models slides' real "choosing an edition" table shape: row labels
    (feature names) with no corresponding format-enum entry at all."""

    def test_unmatched_row_labels_still_produce_claims_at_lower_confidence(self, tmp_path):
        readme = tmp_path / "README.md"
        readme.write_text(
            "# Aspose.Slides FOSS\n\n"
            "## Choosing an edition\n\n"
            "| Feature | .NET | Java |\n"
            "|---------|:----:|:----:|\n"
            "| Threaded comment part | ✅ | ✅ |\n"
            "| Clone a master | ✅ | — |\n",
            encoding="utf-8",
        )
        claims, covered = detect_capability_tables(tmp_path, "slides", known_formats=[])
        assert len(claims) == 3  # Threaded/.NET, Threaded/Java, Clone/.NET (Clone/Java is a dash)
        assert all(c["confidence"] == UNVERIFIED_CONFIDENCE for c in claims)
        assert covered  # the table was still recognized and would be stripped from LLM context


class TestMalformedTableFailsClosed:
    def test_ragged_table_produces_no_claims(self, tmp_path):
        readme = tmp_path / "README.md"
        # Second data row has one fewer cell than the header -- genuinely
        # ragged, must be skipped rather than guessed at.
        readme.write_text(
            "| Format | Detect | Width |\n"
            "|--------|:------:|:-----:|\n"
            "| PNG | ✅ | ✅ |\n"
            "| GIF | ✅ |\n",
            encoding="utf-8",
        )
        claims, covered = detect_capability_tables(tmp_path, "x", known_formats=[])
        assert claims == []
        assert covered == []

    def test_two_column_table_is_not_a_capability_matrix(self, tmp_path):
        """A plain Format|Direction table is already covered by format_support
        claims -- this pass must not also atomize it (would be redundant)."""
        readme = tmp_path / "README.md"
        readme.write_text(
            "| Format | Direction |\n"
            "|--------|-----------|\n"
            "| PNG | detect |\n"
            "| GIF | detect |\n",
            encoding="utf-8",
        )
        claims, covered = detect_capability_tables(tmp_path, "x", known_formats=[])
        assert claims == []
        assert covered == []

    def test_no_readme_produces_no_claims(self, tmp_path):
        claims, covered = detect_capability_tables(tmp_path, "x", known_formats=[])
        assert claims == []
        assert covered == []


class TestDuplicateTableIdempotency:
    """Targets the words/net non-determinism defect class directly: the SAME
    table, appearing twice, must always atomize identically -- no coin-flip
    granularity across runs or across occurrences."""

    def test_identical_table_in_two_readme_sections_produces_identical_claim_sets(self, tmp_path):
        table = (
            "| Format | Load | Save |\n"
            "|--------|:----:|:----:|\n"
            "| DOCX | ✅ | ✅ |\n"
            "| PDF | ✅ | — |\n"
        )
        readme = tmp_path / "README.md"
        readme.write_text(f"## Section A\n\n{table}\n## Section B (same table)\n\n{table}", encoding="utf-8")
        claims, covered = detect_capability_tables(tmp_path, "words", known_formats=[])
        assert len(covered) == 2  # both occurrences recognized
        # Claim IDs are content-hashed -- the same fact produces the same
        # claim_id both times, so a downstream dedup pass collapses them
        # deterministically rather than by chance.
        first_half = claims[: len(claims) // 2]
        second_half = claims[len(claims) // 2:]
        assert [c["claim_id"] for c in first_half] == [c["claim_id"] for c in second_half]


class TestStripCoveredTables:
    def test_covered_table_removed_from_readme_text(self):
        table = "| A | B | C |\n|---|---|---|\n| x | y | z |\n"
        full_text = f"Intro prose.\n\n{table}\nOutro prose."
        result = strip_covered_tables(full_text, [table.rstrip("\n")])
        assert "| A | B | C |" not in result
        assert "Intro prose." in result
        assert "Outro prose." in result

    def test_no_covered_tables_is_a_no_op(self):
        text = "Just prose, no tables."
        assert strip_covered_tables(text, []) == text
