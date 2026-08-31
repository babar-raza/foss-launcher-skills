"""R-5 (TC-MT040-55): does D-4's mechanical module_key assignment reproduce
3d/typescript's hand-authored 16-category grouped reference index closely
enough to safely replace it on regeneration?

Per the plan (R-5): "the class -> category mapping recorded as a fixture and
a test that the D-4 assignment reproduces >=90% of the curated placements --
the remainder listed, decided, and the seed adjusted, never silently."

Measured live 2026-08-30 against 3d/typescript's real, promoted
api_surface.json and the real curated content/reference.aspose.org/en/3d/typescript/_index.md
(snapshot: scripts/pipeline/tests/fixtures/r5_3d_curation/3d_typescript_curation_snapshot.json):
only 10/75 (13.3%) of the classes present in both sets get a mechanical
module_key whose title-cased label matches the curator's category exactly --
far short of 90%. The mismatches are systematic, not noisy:

- promote.py's directory-segment strategy (a) deliberately flattens every
  format sub-package (formats/collada, formats/fbx, formats/obj, ...) into
  one "Formats" group (mirrors site_planner's existing ancestor-flattening,
  a considered TC-43 design choice) -- the curator instead split these into
  6 distinct per-format categories (COLLADA/FBX/glTF/OBJ/STL/3MF Format).
- The curator grouped classes by SEMANTIC role across directories the
  extractor has no way to see as related, e.g. Camera + Light + LightType +
  ProjectionType (Camera and Lighting) span entities/*.ts but the curator
  separated them from Mesh/Geometry (Geometry and Mesh, also entities/*.ts);
  BoundingBox (utilities/) + Transform + GlobalTransform (core-root) became
  one "Transform and Spatial" category despite living in different
  directories with no shared keyword.

Per R-5 outcome (b): since <90%, the curated page is KEPT (not regenerated)
with auto_updatable: false and a recorded reason -- see the S-73 audit trail
at reports/manual-edits/2026-08-30-3d-typescript-index-*.json and backlog
row R5-3D-CURATION-001. This test pins the CURRENT reproduction count as a
regression guard: if a future promote.py change moves this percentage
(better OR worse), that is a deliberate, visible change this test forces a
conscious update for -- not silent drift either direction.
"""
from __future__ import annotations

import json
from pathlib import Path

import promote as promote_mod

FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures" / "r5_3d_curation" / "3d_typescript_curation_snapshot.json"
)


def _load_snapshot():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class TestCurationReproductionRate:
    def test_current_reproduction_rate_is_13_percent_not_90(self):
        """Recomputes module_key fresh from the snapshot's own recorded
        mechanical assignment (not a live re-scout -- the snapshot IS the
        frozen evidence for this decision) and compares to the curated
        category labels, pinning today's known-gap count exactly."""
        snap = _load_snapshot()
        mech = snap["mechanical_module_key"]
        curated = snap["curated_category"]

        common = sorted(set(mech) & set(curated))
        assert len(common) == 75, (
            f"fixture drifted: expected 75 names in both mechanical and "
            f"curated sets, got {len(common)} -- re-derive the snapshot "
            f"before trusting this test's match count"
        )

        def label(key: str) -> str:
            return "Core API" if key == "core" else promote_mod._title_case_module_key(key)

        matches = [n for n in common if label(mech[n]).lower() == curated[n].lower()]
        match_pct = 100 * len(matches) / len(common)

        assert len(matches) == 10, (
            f"D-4 mechanical/curated reproduction rate for 3d/typescript "
            f"changed: {len(matches)}/{len(common)} ({match_pct:.1f}%) match "
            f"today, expected exactly 10/75 (13.3%) pinned 2026-08-30. If "
            f"promote.py's grouping strategy changed, re-run the R-5 "
            f"reproduction check, update this pin, and re-decide whether "
            f"3d/typescript's curated index can now be safely regenerated "
            f"(>=90% threshold) -- do not just bump this number silently."
        )
        assert match_pct < 90.0, (
            "Reproduction rate crossed the >=90% threshold -- re-evaluate "
            "R-5 outcome (a) [replace with regenerated index] vs (b) "
            "[keep curated, auto_updatable: false] for 3d/typescript."
        )

    def test_format_subpackage_flattening_is_the_largest_mismatch_class(self):
        """Documents WHY the gap exists (not just that it exists): every
        format-family class (Obj/Gltf/Stl/ThreeMf/Fbx/Collada *) mismatches
        because promote.py's tier (a) intentionally flattens format
        sub-packages into one 'Formats' group while the curator split them
        into 6. Regression guard: if this flattening behavior is ever
        changed (e.g. to preserve the sub-package segment), this test's
        mismatch count for format classes should drop -- a signal to revisit
        R-5, not evidence to silently ignore."""
        snap = _load_snapshot()
        mech = snap["mechanical_module_key"]
        curated = snap["curated_category"]

        format_families = ("Obj", "Gltf", "Stl", "ThreeMf", "Fbx", "Collada")
        format_names = [
            n for n in (set(mech) & set(curated))
            if n.startswith(format_families) and mech[n] == "formats"
        ]
        assert len(format_names) == 28, (
            f"expected exactly 28 format-family classes flattened into the "
            f"single mechanical 'formats' group (Collada x3, Fbx/Gltf/Obj/"
            f"Stl/ThreeMf x5 each), got {len(format_names)}"
        )
        # None of them should match their curated per-format category label
        # (that's precisely the flattening effect) -- if any suddenly do,
        # tier (a)'s flattening rule changed underneath this test.
        mismatching = [n for n in format_names if curated[n] != "Formats"]
        assert len(mismatching) == 28
