"""ST-142: _validate_formats's CamelCase compound-word heuristic must not
reject a confirmed-real format name that only LOOKS like a compound word.

Root cause: `_CAMELCASE_RE = re.compile(r"[a-z][A-Z]")` in
extraction/formats.py's `_validate_formats` rejects non-enum format names
matching lowercase-then-uppercase as compound-word false positives (e.g.
"ChartXml", "AutoFilterXML") -- correct for that shape, but it also silently
dropped "ThreeMf" (from ThreeMfExporter/ThreeMfImporter, the 3MF -- 3D
Manufacturing Format -- standard) even though both classes parse correctly
and are real, non-stub I/O implementations. Confirmed live 2026-08-31 (MT040
Phase I): a temporary hand-edit to knowledge/3d/typescript/merged/formats.json
(evidence_kind="manual_correction_ST142") was needed to unblock the
3d/typescript api-overview.md page's 3MF table row -- this test (plus the
`_CAMELCASE_FALSE_POSITIVE_EXEMPT` fix) makes the extractor itself produce
the entries natively, so that hand-edit is no longer needed.
"""
from __future__ import annotations

import sys
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parents[2]
if str(PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINE_DIR))

from extraction.formats import _validate_formats, _CAMELCASE_FALSE_POSITIVE_EXEMPT  # noqa: E402


def _entry(fmt: str, *, enum: str = "", direction: str = "export") -> dict:
    return {
        "format": fmt, "enum": enum, "value": "", "file": "x.ts", "line": 1,
        "direction": direction,
    }


class TestCamelCaseExemption:
    def test_threemf_survives_validation(self):
        valid = _validate_formats([_entry("ThreeMf")], frozenset(), frozenset())
        assert [f["format"] for f in valid] == ["ThreeMf"]

    def test_genuine_compound_word_still_rejected(self):
        # ChartXml is the exact real false-positive shape this heuristic
        # exists to catch -- must still be rejected.
        valid = _validate_formats([_entry("ChartXml")], frozenset(), frozenset())
        assert valid == []

    def test_another_genuine_compound_word_still_rejected(self):
        valid = _validate_formats([_entry("AutoFilterXml")], frozenset(), frozenset())
        assert valid == []

    def test_exemption_is_case_insensitive(self):
        valid = _validate_formats([_entry("threemf")], frozenset(), frozenset())
        assert [f["format"] for f in valid] == ["threemf"]

    def test_enum_sourced_camelcase_bypasses_check_regardless(self):
        # Enum-sourced entries already bypass the CamelCase check entirely
        # (pre-existing behavior) -- unaffected by this fix either way.
        valid = _validate_formats(
            [_entry("SomeCompoundEnum", enum="SaveFormat")], frozenset(), frozenset(),
        )
        assert [f["format"] for f in valid] == ["SomeCompoundEnum"]

    def test_exempt_set_contains_only_the_confirmed_case(self):
        # Guards against silent widening -- new exemptions must be added
        # deliberately with their own live evidence (see the module's own
        # docstring in formats.py), not accumulated casually.
        assert _CAMELCASE_FALSE_POSITIVE_EXEMPT == frozenset({"threemf"})


# ---------------------------------------------------------------------------
# Live-clone integration proof (skipped if the clone cache is absent)
# ---------------------------------------------------------------------------

import unittest  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[4]
_3D_TS_CACHE = _REPO_ROOT / "runs" / ".clone_cache" / "aspose_3d_typescript"
_3D_TS_HAS_SOURCES = (
    bool(list(_3D_TS_CACHE.rglob("*.ts"))[:1]) if _3D_TS_CACHE.exists() else False
)


@unittest.skipUnless(
    _3D_TS_HAS_SOURCES,
    "Clone cache absent or empty — run /repo-scout 3d typescript first",
)
class TestThreeMfDetectedFromRealClone:
    def test_threemf_export_and_import_detected(self):
        from extraction import formats as fmts
        from extraction.tree_helpers import get_parser

        pkg_root = _3D_TS_CACHE / "src"
        parser = get_parser("typescript")
        results, _claims = fmts.detect_formats(parser, "typescript", pkg_root, _3D_TS_CACHE, "3d")

        threemf = [r for r in results if r["format"].lower() == "threemf"]
        directions = {r["direction"] for r in threemf}
        assert "export" in directions, (
            f"ThreeMfExporter.ts must yield an export entry, got: {results}"
        )
        assert "import" in directions, (
            f"ThreeMfImporter.ts must yield an import entry, got: {results}"
        )
