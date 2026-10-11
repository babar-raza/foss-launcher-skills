"""Tests for site_planner.py's D-4 / TC-MT040-43 consumption of
module_key/module_label -- the knowledge-layer module/topic assignment
promote.py writes onto api_surface.json entries (see
commands/knowledge/promote.py's "Module/topic assignment" section).

Covers:
  - detect_clusters() reads module_key/module_label when present, falls
    back to the existing _class_to_subpackage()-based directory-path logic
    unchanged when absent (older knowledge that hasn't been re-promoted).
  - A synthetic flat-layout fixture (no directory info at all) with
    keyword-matchable class names produces >= 4 non-degenerate clusters
    through the real compute_module_assignment() + detect_clusters()
    pipeline -- the site-planner half of the G-TS-01 regression proof
    (batch_reference's grouped-reference-index half lives in
    test_batch_reference_module_assignment.py).
"""
from __future__ import annotations

import site_planner as sp
from commands.knowledge.promote import compute_module_assignment


def _make_claims(api_surface: list[dict], per_class: int = 5) -> list[dict]:
    claims = []
    for entry in api_surface:
        cls_name = entry["name"]
        for j in range(per_class):
            claims.append({
                "kind": "api_method",
                "text": f"{cls_name}.method_{j}()",
                "category": cls_name,
            })
    return claims


class TestDetectClustersModuleAssignment:
    def test_module_key_used_instead_of_directory_path(self):
        """A root-level file (would derive "" -> family root label via the
        old directory-path logic) instead uses its module_key directly."""
        api_surface = [
            {"name": "Widget", "file": "src/Widget.ts", "module_key": "widgets",
             "module_label": "Widgets"},
        ]
        claims = _make_claims(api_surface)
        clusters = sp.detect_clusters(claims, api_surface, [], "", family="acme")
        categories = {c["category"] for c in clusters}
        assert "Widgets" in categories
        # The old root-label fallback ("core-management" style) must NOT
        # have been used.
        assert "core-management" not in categories

    def test_falls_back_to_directory_logic_when_module_key_absent(self):
        """Same shape as before this change: no module_key anywhere ->
        byte-identical to the pre-existing behavior (the real
        _class_to_subpackage() + _subpkg_to_label() derivation, whatever
        it currently maps "entities" to for family "3d" -- not re-asserted
        here, just proven unchanged/still reached)."""
        api_surface = [
            {"name": "Mesh", "file": "aspose/threed/entities/Mesh.py"},
        ]
        claims = _make_claims(api_surface)
        clusters = sp.detect_clusters(claims, api_surface, [], "", family="3d")
        categories = {c["category"] for c in clusters}
        assert categories == {sp._subpkg_to_label("entities", "3d")}

    def test_mixed_entries_with_and_without_module_key(self):
        """A partially re-promoted product (some entries carry module_key,
        others don't -- e.g. mid-migration) handles both per-entry."""
        api_surface = [
            {"name": "New", "file": "src/new.ts", "module_key": "forms", "module_label": "Forms"},
            {"name": "Old", "file": "aspose/threed/entities/Old.py"},
        ]
        claims = _make_claims(api_surface)
        clusters = sp.detect_clusters(claims, api_surface, [], "", family="3d")
        categories = {c["category"] for c in clusters}
        assert "Forms" in categories
        assert sp._subpkg_to_label("entities", "3d") in categories

    def test_module_label_missing_falls_back_to_subpkg_label_derivation(self):
        """module_key present but module_label absent (partial/older data)
        -- degrades to the existing _subpkg_to_label() derivation rather
        than crashing or losing the class."""
        api_surface = [
            {"name": "Widget", "file": "src/Widget.ts", "module_key": "widgets"},
        ]
        claims = _make_claims(api_surface)
        clusters = sp.detect_clusters(claims, api_surface, [], "", family="acme")
        assert sum(len(c["class_names"]) for c in clusters) >= 1
        assert any("Widget" in c["class_names"] for c in clusters)


class TestFlatLayoutFixtureProducesNonDegenerateClusters:
    """The site-planner half of the G-TS-01 regression proof: a flat repo
    (every file directly under src/) must not collapse into one
    degenerate cluster once promote.py's compute_module_assignment() has
    run -- matches the acceptance criterion in the mission plan
    ("a synthetic flat-layout fixture with keyword-matchable class names
    -> >= 4 clusters in site_planner's detect_clusters")."""

    FLAT_API_SURFACE = [
        {"name": "AcroFormField", "file": "src/acroform.ts"},
        {"name": "AnnotationBuilder", "file": "src/annotation.ts"},
        {"name": "DocxExporter", "file": "src/docxexport.ts"},
        {"name": "TableAbsorber", "file": "src/tableabsorber.ts"},
        {"name": "RedactionBuilder", "file": "src/redaction.ts"},
        {"name": "Document", "file": "src/document.ts"},  # no keyword match -> core
    ]

    def test_flat_fixture_yields_at_least_four_clusters(self):
        api_surface = [dict(e) for e in self.FLAT_API_SURFACE]
        compute_module_assignment(api_surface, "pdf", "typescript")
        claims = _make_claims(api_surface)

        clusters = sp.detect_clusters(claims, api_surface, [], "", family="pdf")
        assert len(clusters) >= 4, f"expected >= 4 clusters, got {clusters}"
        categories = {c["category"] for c in clusters}
        assert {"Forms", "Annotations", "Conversion", "Tables", "Redaction"}.issubset(categories)
        assert "Core API" in categories

    def test_flat_fixture_is_degenerate_without_module_key(self):
        """Direct regression guard for the exact G-TS-01 symptom: without
        module_key, this same flat fixture collapses into one cluster."""
        api_surface = [dict(e) for e in self.FLAT_API_SURFACE]
        claims = _make_claims(api_surface)
        clusters = sp.detect_clusters(claims, api_surface, [], "", family="pdf")
        assert len(clusters) == 1
