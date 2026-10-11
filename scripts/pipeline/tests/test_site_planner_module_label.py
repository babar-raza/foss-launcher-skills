"""detect_clusters(): an automatic module_label that would yield an unsplit
single-token cluster slug (> 12 chars, the exact shape _validate_kb_slugs
Check 1 rejects) must not override an explicit label from
_subpkg_to_label() (family/global label maps).

Labels that are fine today must keep winning, so already-shipped site plans
do not change.
"""
from __future__ import annotations

import site_planner as sp


def _claims(api_surface: list[dict], per_class: int = 3) -> list[dict]:
    return [
        {"kind": "api_method", "text": f"{e['name']}.m{j}()", "category": e["name"]}
        for e in api_surface
        for j in range(per_class)
    ]


def _categories(api_surface: list[dict], family: str) -> set[str]:
    clusters = sp.detect_clusters(_claims(api_surface), api_surface, [], "", family=family)
    return {c["category"] for c in clusters}


class TestAutomaticLabelYieldsToExplicitLabel:
    def test_pdf_family_long_single_token_uses_explicit_label(self):
        api = [{"name": "LogicalStructure", "file": "x/LogicalStructure.java",
                "module_key": "logicalstructure", "module_label": "Logicalstructure"}]
        assert _categories(api, "pdf") == {"logical-structure"}

    def test_gis_family_long_single_token_uses_explicit_label(self):
        api = [{"name": "Srs", "file": "x/Srs.cs",
                "module_key": "spatialreferencing", "module_label": "Spatialreferencing"}]
        assert _categories(api, "gis") == {"spatial-referencing"}

    def test_kb_slug_validation_passes_for_the_overridden_label(self):
        api = [{"name": "LogicalStructure", "file": "x/LogicalStructure.java",
                "module_key": "logicalstructure", "module_label": "Logicalstructure"}]
        clusters = sp.detect_clusters(_claims(api, per_class=40), api, [], "", family="pdf")
        pages = sp.plan_kb("pdf", "java", clusters, 400, 10, "full")  # validates slugs
        how_tos = [p["slug"] for p in pages if p["slug"].startswith("how-to-")]
        assert how_tos and all("logicalstructure" not in s for s in how_tos)


class TestUnchangedBehaviour:
    def test_short_automatic_label_still_wins_over_explicit_label(self):
        # "forms" has an explicit pdf label ("pdf-annotations"); the automatic
        # label is fine (short), so it must keep winning exactly as before.
        api = [{"name": "Form", "file": "x/Form.java",
                "module_key": "forms", "module_label": "Forms"}]
        assert _categories(api, "pdf") == {"Forms"}

    def test_hyphenated_automatic_label_still_wins(self):
        api = [{"name": "Srs", "file": "x/Srs.cs",
                "module_key": "spatialreferencing", "module_label": "Spatial Referencing"}]
        assert _categories(api, "gis") == {"Spatial Referencing"}

    def test_long_token_without_explicit_label_is_left_alone(self):
        api = [{"name": "Thing", "file": "x/Thing.py",
                "module_key": "unmappedlongkeyname", "module_label": "Unmappedlongkeyname"}]
        assert _categories(api, "acme") == {"Unmappedlongkeyname"}

    def test_no_module_label_uses_explicit_label_as_before(self):
        api = [{"name": "LogicalStructure", "file": "x/LogicalStructure.java",
                "module_key": "logicalstructure"}]
        assert _categories(api, "pdf") == {"logical-structure"}
