"""Tests for enrich.py's _filter_redundant_format_summary_claims (H7,
MT068-2026-09-11-IMAGING-NET-LAUNCH).

Found live: stripping a covered capability-matrix table out of the LLM's
source context did NOT stop the LLM reconstructing the same broad "can
detect and probe PNG, JPEG, ..." summary claim -- it still had the same
format names available from other context (README intro prose, the
verified-facts block built from formats.json). This deterministic
post-filter is what actually closes the gap.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from commands.knowledge.enrich import _filter_redundant_format_summary_claims


class TestFilterRedundantFormatSummaryClaims(unittest.TestCase):
    def test_broad_summary_claim_naming_all_covered_formats_is_dropped(self):
        claims = [{
            "kind": "format",
            "text": "The library can detect and probe PNG, JPEG, GIF, BMP, WebP, "
                    "ICO, TIFF, PSD, EMF, WMF, and DICOM image files.",
        }]
        covered = {"png", "jpeg", "gif", "bmp", "webp", "ico", "tiff", "psd", "emf", "wmf", "dicom"}
        result = _filter_redundant_format_summary_claims(claims, covered)
        self.assertEqual(result, [])

    def test_claim_about_one_specific_format_is_kept(self):
        """A genuinely distinct claim (not a broad listing) must survive."""
        claims = [{
            "kind": "format",
            "text": "DICOM parsing stops rather than guesses on an undefined-length sequence.",
        }]
        covered = {"png", "jpeg", "gif", "bmp", "webp", "ico", "tiff", "psd", "emf", "wmf", "dicom"}
        result = _filter_redundant_format_summary_claims(claims, covered)
        self.assertEqual(result, claims)

    def test_non_format_kind_claims_are_never_touched(self):
        claims = [{
            "kind": "api",
            "text": "ImageProbe.ProbeFile reads only enough of the header to populate ImageInfo.",
        }]
        covered = {"png", "jpeg"}
        result = _filter_redundant_format_summary_claims(claims, covered)
        self.assertEqual(result, claims)

    def test_empty_covered_set_is_a_no_op(self):
        claims = [{"kind": "format", "text": "Supports PNG, JPEG, and GIF."}]
        result = _filter_redundant_format_summary_claims(claims, set())
        self.assertEqual(result, claims)

    def test_small_partial_overlap_is_kept(self):
        """Mentioning only 1-2 of many covered formats is a genuinely narrow
        claim, not a broad redundant summary -- must not be dropped."""
        claims = [{
            "kind": "format",
            "text": "PNG headers are 8 bytes before the IHDR chunk begins.",
        }]
        covered = {"png", "jpeg", "gif", "bmp", "webp", "ico", "tiff", "psd", "emf", "wmf", "dicom"}
        result = _filter_redundant_format_summary_claims(claims, covered)
        self.assertEqual(result, claims)


if __name__ == "__main__":
    unittest.main()
