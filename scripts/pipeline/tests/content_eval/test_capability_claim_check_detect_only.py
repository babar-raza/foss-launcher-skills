"""Regression test: _direction_compatible() must not reject every claim
against a detect-only actual direction.

Found live 2026-09-11 writing imaging/net's products page (mission
MT068-2026-09-11-IMAGING-NET-LAUNCH): _claim_direction() has no verb pattern
for "detect" itself -- only import/export/both -- so it could never match
actual="detect" via the `claimed == actual` branch, and the old code
unconditionally `return False`'d for actual="detect" regardless of what was
claimed. This guarantees a FAIL for every sentence within 80 chars of a
detect-only format mention that uses ANY import-shaped verb (read/open/load/
parse) -- unavoidable in natural prose describing a header-probing library
("reads the header to detect the format"). Confirmed live: reworded the page
three times trying to avoid "support"/"handle"/"read" near TIFF and still
hit new FAILs each time, because format detection is inherently read-only
and the evaluator had no way to express that as a compatible claim.

reports/skill-gaps/2026-09-11-imaging-net-pipeline-hardening-prerequisites.md
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from content_eval.evaluators.capability_claim_check import _direction_compatible


class TestDirectionCompatibleDetectOnly:
    def test_import_claim_compatible_with_detect_only(self):
        """The real incident's shape: prose says 'reads the header' (an
        import-shaped claim) about a format whose actual direction is
        detect-only. Detection is inherently read-only -- this must be
        treated as an accurate description, not an overclaim."""
        assert _direction_compatible("import", "detect") is True

    def test_export_claim_still_rejected_against_detect_only(self):
        """A genuine overclaim (prose implying the library can WRITE/export
        a detect-only format) must still be caught."""
        assert _direction_compatible("export", "detect") is False

    def test_both_claim_still_rejected_against_detect_only(self):
        """Same reasoning as export: 'both' implies write capability the
        library does not have for a detect-only format."""
        assert _direction_compatible("both", "detect") is False

    def test_detect_actual_still_incompatible_with_import_when_actual_is_none(self):
        """Unrelated case must be unaffected: actual='none' (no capability
        at all) still rejects every claim, import included."""
        assert _direction_compatible("import", "none") is False

    def test_both_actual_still_accepts_everything(self):
        """Unrelated case must be unaffected: a genuinely bidirectional
        format still accepts any claimed direction."""
        assert _direction_compatible("import", "both") is True
        assert _direction_compatible("export", "both") is True
        assert _direction_compatible("both", "both") is True
