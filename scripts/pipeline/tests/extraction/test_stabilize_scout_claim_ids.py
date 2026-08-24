"""Tests for _stabilize_scout_claim_ids (Task 16, mission-plan-the-end-to-end-
vast-hejlsberg.md §9.11, closes half of G10).

Mirrors test_enrich.py's TestAssignIdsMemberDocAnchor test suite -- the same
collision-resolution architecture, applied to scout-derived claims instead of
LLM member-doc claims. Member-level scout claims must key off the
"ClassName.MemberName" anchor embedded at the start of their text (by
api_surface.py's own claim-text templates), not the exact wording, so
citations survive a rebuild whose only real change is prose/formatting.
Class-level and free-function claims (whose text never matches this pattern)
must be byte-for-byte unaffected.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

# sys.path is set by tests/conftest.py -- no manual insert needed here.
# Import via the qualified "extraction." package path, matching every other
# file in this directory (e.g. test_csharp_modifier_stack.py) -- a bare
# sys.path.insert(EXTRACTION_DIR) + unqualified import here previously caused
# a real module-identity collision with test_scout_extraction.py's own
# `import scout` (a same-named top-level module inside extraction/), corrupting
# sys.modules['scout'] for every test file collected afterward. Caught live by
# running the full extraction test surface together, not just this file alone.
from extraction.api_surface import _stabilize_scout_claim_ids, _make_claim  # noqa: E402


def _anchor_id(family: str, anchor: str, kind: str) -> str:
    stable = hashlib.sha256((anchor + "|" + kind).encode("utf-8")).hexdigest()[:8]
    return f"CLM-{family}-{stable}"


class TestStabilizeScoutClaimIds:
    def test_reworded_member_claim_keeps_same_id_across_rescouts(self):
        """The core citation-durability guarantee: two hypothetical scout
        runs with different wording for the same member resolve to the same
        claim_id (simulating a return-type formatting tweak or added prose
        between two extraction passes)."""
        claim_run1 = [{"text": "Workbook.Save writes the workbook to path.",
                        "kind": "api_method", "claim_id": "CLM-cells-oldhash1"}]
        claim_run2 = [{"text": "Workbook.Save(path, format) -> void",
                        "kind": "api_method", "claim_id": "CLM-cells-oldhash2"}]
        r1 = _stabilize_scout_claim_ids(claim_run1, "cells")
        r2 = _stabilize_scout_claim_ids(claim_run2, "cells")
        assert r1[0]["claim_id"] == r2[0]["claim_id"]

    def test_different_member_gets_different_id(self):
        claims = [
            {"text": "Workbook.Save writes the file.", "kind": "api_method"},
            {"text": "Workbook.Load reads the file.", "kind": "api_method"},
        ]
        result = _stabilize_scout_claim_ids(claims, "cells")
        assert result[0]["claim_id"] != result[1]["claim_id"]

    def test_different_class_same_member_name_gets_different_id(self):
        claims = [
            {"text": "Workbook.Save writes the file.", "kind": "api_method"},
            {"text": "Chart.Save writes the chart.", "kind": "api_method"},
        ]
        result = _stabilize_scout_claim_ids(claims, "cells")
        assert result[0]["claim_id"] != result[1]["claim_id"]

    def test_anchor_id_matches_direct_hash_computation(self):
        claim = [{"text": "Workbook.Save writes the file.", "kind": "api_method"}]
        result = _stabilize_scout_claim_ids(claim, "cells")
        assert result[0]["claim_id"] == _anchor_id("cells", "Workbook.Save", "api_method")

    def test_class_level_claim_text_unaffected(self):
        """api_surface.py's own template for kind=api_class is
        f"Class {cname} defined in {rel}" -- never matches the anchor
        pattern, so this claim keeps whatever ID _make_claim already gave it."""
        original_id = "CLM-cells-abc123"
        claim = [{"text": "Class Workbook defined in Workbook.cs",
                  "kind": "api_class", "claim_id": original_id}]
        result = _stabilize_scout_claim_ids(claim, "cells")
        assert result[0]["claim_id"] == original_id

    def test_free_function_claim_text_unaffected(self):
        """The free-function template is f"Function {fname}(...) -> {ret}"
        -- never matches the anchor pattern (no owning class to anchor to)."""
        original_id = "CLM-go-def456"
        claim = [{"text": "Function LoadFile(path) -> Document",
                  "kind": "api_method", "claim_id": original_id}]
        result = _stabilize_scout_claim_ids(claim, "go")
        assert result[0]["claim_id"] == original_id

    def test_non_dict_claim_passed_through_unchanged(self):
        """Defensive: a malformed (non-dict) entry must not crash the pass."""
        claims = [{"text": "Workbook.Save writes the file.", "kind": "api_method"}, "not-a-dict"]
        result = _stabilize_scout_claim_ids(claims, "cells")
        assert result[1] == "not-a-dict"

    def test_same_run_anchor_collision_keeps_both_no_data_loss(self):
        """Overloaded members (Save(path) vs Save(stream)) are common, not
        rare -- two distinct claims sharing one anchor must not collide into
        a duplicate claim_id, and neither may be silently dropped: one wins
        the stable anchor id, the other keeps its own pre-assigned
        (_make_claim) full-text-hash id."""
        claim_a = {"text": "Workbook.Save writes the file to disk.",
                   "kind": "api_method", "claim_id": "CLM-cells-origA"}
        claim_b = {"text": "Workbook.Save persists workbook contents.",
                   "kind": "api_method", "claim_id": "CLM-cells-origB"}
        result = _stabilize_scout_claim_ids([claim_a, claim_b], "cells")
        assert len(result) == 2
        ids = {c["claim_id"] for c in result}
        assert len(ids) == 2, "both overload claims must survive with distinct IDs"

        anchor_id = _anchor_id("cells", "Workbook.Save", "api_method")
        winner_text = min(claim_a["text"], claim_b["text"])
        winner = next(c for c in result if c["text"] == winner_text)
        loser = next(c for c in result if c["text"] != winner_text)
        assert winner["claim_id"] == anchor_id
        # Loser keeps its pre-existing ID (never recomputed by this pass).
        loser_original = claim_a["claim_id"] if loser["text"] == claim_a["text"] else claim_b["claim_id"]
        assert loser["claim_id"] == loser_original

    def test_anchor_winner_deterministic_regardless_of_input_order(self):
        claim_a = {"text": "Workbook.Save writes the file to disk.", "kind": "api_method"}
        claim_b = {"text": "Workbook.Save persists workbook contents.", "kind": "api_method"}
        r1 = _stabilize_scout_claim_ids([claim_a, claim_b], "cells")
        r2 = _stabilize_scout_claim_ids([claim_b, claim_a], "cells")
        ids1 = {c["text"]: c["claim_id"] for c in r1}
        ids2 = {c["text"]: c["claim_id"] for c in r2}
        assert ids1 == ids2

    def test_three_way_overload_collision_no_data_loss(self):
        """Three overloads of the same member (real corpus pattern -- e.g.
        multiple constructor overloads) must all survive with distinct IDs,
        exactly one of which is the stable anchor ID."""
        claims = [
            {"text": f"Matrix4.Matrix4 constructs a matrix variant {i}.", "kind": "api_method"}
            for i in range(3)
        ]
        result = _stabilize_scout_claim_ids(claims, "3d")
        ids = [c["claim_id"] for c in result]
        assert len(result) == 3
        assert len(set(ids)) == 3
        anchor_id = _anchor_id("3d", "Matrix4.Matrix4", "api_method")
        assert sum(1 for i in ids if i == anchor_id) == 1

    def test_full_scout_claim_shape_from_make_claim(self):
        """End-to-end sanity: feed real _make_claim()-shaped output (the
        actual production call shape) through the stabilizer."""
        claim = _make_claim("pdf", "api_method", "Document.getPages() -> PageCollection",
                             file="Document.java", line=42)
        original_id = claim["claim_id"]
        result = _stabilize_scout_claim_ids([claim], "pdf")
        stabilized = result[0]
        assert stabilized["claim_id"] != original_id  # anchor-based, not the raw text hash
        assert stabilized["claim_id"] == _anchor_id("pdf", "Document.getPages", "api_method")
        # Every other field must survive untouched.
        assert stabilized["text"] == claim["text"]
        assert stabilized["kind"] == claim["kind"]
        assert stabilized["claim_source"] == "scout"
        assert stabilized["evidence"] == claim["evidence"]

    def test_empty_claims_list(self):
        assert _stabilize_scout_claim_ids([], "cells") == []

    def test_does_not_mutate_input_claims(self):
        """The pass must return new dicts, never mutate the caller's list in
        place (matches _assign_ids' own contract)."""
        original = {"text": "Workbook.Save writes the file.", "kind": "api_method",
                    "claim_id": "CLM-cells-original"}
        claims = [original]
        _stabilize_scout_claim_ids(claims, "cells")
        assert original["claim_id"] == "CLM-cells-original"


class TestRealDataCompatibility:
    """Task 16's own explicitly-required "compatibility check against every
    product's already-committed merged/claims.json" (mission-plan-the-end-
    to-end-vast-hejlsberg.md §13/§15). Runs the stabilizer against real,
    already-committed scout claims from multiple already-launched products
    (not synthetic fixtures) and asserts no ID collisions and no data loss.

    This caught a REAL bug before commit: an earlier version of this function
    used [:6] hex chars (24 bits, matching _make_claim's existing full-text
    hash scheme) for the anchor-based ID too. Against pdf/java's real 14,005-
    claim scout corpus, that produced 4 genuine hash-truncation collisions
    between UNRELATED anchors (e.g. PdfFormatConversionOptions.setDefaultFontName
    and SetLineCap.SetLineCap hashed to the same 6 hex chars) -- a real
    birthday-paradox collision, not a logic bug in the collision-resolution
    algorithm itself. Fixed by widening to [:8] (32 bits), matching
    enrich.py's own _assign_ids precedent, which already uses [:8] for
    exactly this reason. Re-verified against 4 real products (~29,000 real
    scout claims total, Java/.NET/Python) with zero collisions after the fix.
    """

    _REPO_ROOT = Path(__file__).resolve().parents[4]

    @pytest.mark.parametrize("family,platform", [
        ("pdf", "java"),
        ("pdf", "net"),
        ("slides", "python"),
        ("words", "net"),
    ])
    def test_no_collisions_and_no_data_loss_on_real_product(self, family, platform):
        claims_path = self._REPO_ROOT / "knowledge" / family / platform / "merged" / "claims.json"
        if not claims_path.is_file():
            pytest.skip(f"no real claims.json for {family}/{platform} in this checkout")

        data = json.loads(claims_path.read_text(encoding="utf-8"))
        scout_claims = [c for c in data if isinstance(c, dict) and c.get("claim_source") == "scout"]
        if not scout_claims:
            pytest.skip(f"no scout claims found for {family}/{platform}")

        result = _stabilize_scout_claim_ids(scout_claims, family)

        assert len(result) == len(scout_claims), "no claim may be dropped"
        ids = [c["claim_id"] for c in result]
        assert len(ids) == len(set(ids)), (
            f"{len(ids) - len(set(ids))} duplicate claim_id(s) produced for "
            f"real {family}/{platform} data -- would hard-fail promote.py's "
            f"write-time duplicate-ID check"
        )
        # Every field except claim_id must be byte-for-byte unchanged.
        for old, new in zip(scout_claims, result):
            for key in ("text", "kind", "confidence", "claim_source", "evidence"):
                assert old.get(key) == new.get(key), (
                    f"field {key!r} changed unexpectedly for a real claim in {family}/{platform}"
                )
