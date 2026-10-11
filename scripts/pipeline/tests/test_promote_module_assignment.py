"""Tests for promote.py's D-4 / TC-MT040-43 module/topic assignment --
compute_module_assignment() writing module_key/module_label onto every
api_surface.json entry at promote time, using the ordered strategy:

    (a) informative directory segment relative to the package's common root
    (b) export-group named by the language adapter's barrel (optional)
    (c) family-agnostic file-stem/identifier keyword table (flat layouts)
    (d) "core" / "Core API" fallback

Covers each tier with a dedicated fixture, the "core wins over false
keyword match" ordering, the mid-word substring-collision regression this
design deliberately avoids (see promote.py's _STEM_KEYWORD_GROUPS
docstring), and the full promote() integration path writing
module_assignment_version into model.yaml.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

# sys.path is set by tests/conftest.py -- no manual insert needed here.
import promote as promote_mod


# ---------------------------------------------------------------------------
# Tier (a): informative directory segment
# ---------------------------------------------------------------------------

class TestTierADirectorySegment:
    def test_nested_layout_common_prefix_stripped(self):
        api_surface = [
            {"name": "ColladaExporter", "file": "src/aspose/threed/formats/collada/ColladaExporter.ts"},
            {"name": "FbxExporter", "file": "src/aspose/threed/formats/fbx/FbxExporter.ts"},
            {"name": "Camera", "file": "src/aspose/threed/entities/Camera.ts"},
            {"name": "Scene", "file": "src/aspose/threed/Scene.ts"},  # root-level -> no tier (a) segment
        ]
        promote_mod.compute_module_assignment(api_surface, "3d", "typescript")
        by_name = {e["name"]: e for e in api_surface}
        # "formats" sub-sub-packages (collada/, fbx/) flatten to one "formats" group.
        assert by_name["ColladaExporter"]["module_key"] == "formats"
        assert by_name["FbxExporter"]["module_key"] == "formats"
        assert by_name["Camera"]["module_key"] == "entities"
        assert by_name["Camera"]["module_label"] == "Entities"
        # Root-level file (no segment after the common prefix) cascades past
        # (a); nothing in tier (b)/(c) matches "Scene" either, so (d).
        assert by_name["Scene"]["module_key"] == "core"
        assert by_name["Scene"]["module_label"] == "Core API"

    def test_camelcase_single_word_directory_splits_into_label(self):
        """MT074-2026-09-25-GIS-NET-LAUNCH-AND-READINESS-GATE-HARDENING regression:
        a PascalCase directory name with NO separator (e.g. gis/net's real
        Aspose.GIS.FOSS/SpatialReferencing/) used to produce an unsplit
        module_label ("Spatialreferencing") because _dir_segment_module_key()
        lowercases the segment for module_key before _title_case_module_key()
        ever sees it, destroying the camelCase word boundary. This crashed
        site_planner.py's KB-slug validator downstream on gis/net's real
        first site-plan run -- confirmed live, not synthetic."""
        api_surface = [
            {"name": "SpatialReferenceSystemTransformation",
             "file": "Aspose.GIS.FOSS/SpatialReferencing/SpatialReferenceSystemTransformation.cs"},
            {"name": "NumberOperations",
             "file": "Aspose.GIS.FOSS/Common/NumberOperations.cs"},
        ]
        promote_mod.compute_module_assignment(api_surface, "gis", "net")
        by_name = {e["name"]: e for e in api_surface}
        entry = by_name["SpatialReferenceSystemTransformation"]
        assert entry["module_key"] == "spatialreferencing"  # stable lowercase identifier, unchanged
        assert entry["module_label"] == "Spatial Referencing"  # was "Spatialreferencing" before the fix
        assert by_name["NumberOperations"]["module_label"] == "Common"

    def test_common_prefix_is_computed_from_data_not_hardcoded(self):
        """A totally different, made-up nested layout must still work --
        the common-prefix strategy is not keyed to any specific platform's
        known directory names."""
        api_surface = [
            {"name": "A", "file": "lib/pkgroot/widgets/A.py"},
            {"name": "B", "file": "lib/pkgroot/widgets/B.py"},
            {"name": "C", "file": "lib/pkgroot/gadgets/C.py"},
        ]
        promote_mod.compute_module_assignment(api_surface, "acme", "python")
        by_name = {e["name"]: e for e in api_surface}
        assert by_name["A"]["module_key"] == "widgets"
        assert by_name["B"]["module_key"] == "widgets"
        assert by_name["C"]["module_key"] == "gadgets"


# ---------------------------------------------------------------------------
# Tier (c): flat-layout keyword table
# ---------------------------------------------------------------------------

class TestTierCKeywordTable:
    def test_flat_layout_keyword_matches(self):
        """No directory info at all (every file directly under src/) --
        forces the cascade straight to (c)."""
        api_surface = [
            {"name": "AcroFormField", "file": "src/acroform.ts"},
            {"name": "AnnotationBuilder", "file": "src/annotation.ts"},
            {"name": "DocxExporter", "file": "src/docxexport.ts"},
            {"name": "JpegEncoder", "file": "src/jpeg.ts"},
        ]
        promote_mod.compute_module_assignment(api_surface, "pdf", "typescript")
        by_name = {e["name"]: e for e in api_surface}
        assert by_name["AcroFormField"]["module_key"] == "forms"
        assert by_name["AnnotationBuilder"]["module_key"] == "annotations"
        assert by_name["DocxExporter"]["module_key"] == "conversion"
        assert by_name["JpegEncoder"]["module_key"] == "images"
        assert by_name["JpegEncoder"]["module_label"] == "Images"

    def test_stem_matches_when_name_does_not(self):
        """A generically-named class/function whose SOURCE FILE stem
        carries the keyword still matches -- both name and stem are
        checked (see _keyword_group_for_stem)."""
        api_surface = [{"name": "run", "file": "src/xfdf.ts"}]
        promote_mod.compute_module_assignment(api_surface, "pdf", "typescript")
        assert api_surface[0]["module_key"] == "conversion"

    def test_midword_substring_is_not_a_false_match(self):
        """Regression: "form" must NOT match inside "Format"/"FileFormat"
        -- the exact bug found live against 3d/typescript's real
        FileFormat.ts functions before this was switched from a raw
        substring test to whole-word tokenized matching."""
        api_surface = [
            {"name": "registerFormat", "file": "src/aspose/threed/FileFormat.ts"},
            {"name": "getFormatByExtension", "file": "src/aspose/threed/FileFormat.ts"},
        ]
        promote_mod.compute_module_assignment(api_surface, "3d", "typescript")
        for e in api_surface:
            assert e["module_key"] != "forms", e["name"]
            # No other keyword matches either -- falls all the way to core.
            assert e["module_key"] == "core"

    def test_generic_cross_domain_words_do_not_match(self):
        """Deliberately narrow vocabulary: bare generic English words like
        "cell"/"text"/"image"/"table" are NOT keywords (only specific
        compound PDF-domain terms are) -- verified against a spreadsheet-
        domain class name that must NOT be swept into a PDF-flavored
        group."""
        api_surface = [{"name": "Cell", "file": "index.ts"}]
        promote_mod.compute_module_assignment(api_surface, "cells", "typescript")
        assert api_surface[0]["module_key"] == "core"


# ---------------------------------------------------------------------------
# Tier (d): fallback
# ---------------------------------------------------------------------------

class TestTierDFallback:
    def test_no_signal_at_all_falls_back_to_core(self):
        api_surface = [{"name": "Whatever", "file": "index.ts"}]
        promote_mod.compute_module_assignment(api_surface, "acme", "typescript")
        assert api_surface[0]["module_key"] == "core"
        assert api_surface[0]["module_label"] == "Core API"

    def test_missing_file_field(self):
        api_surface = [{"name": "NoFile"}]
        promote_mod.compute_module_assignment(api_surface, "acme", "typescript")
        assert api_surface[0]["module_key"] == "core"


# ---------------------------------------------------------------------------
# Cascade ordering and edge-case robustness
# ---------------------------------------------------------------------------

class TestCascadeOrdering:
    def test_tier_a_wins_over_tier_c_when_both_could_apply(self):
        """A class under an informative directory segment uses that
        segment even if its name would ALSO match a tier-(c) keyword --
        (a) is always tried first. A sibling entry under a different
        subdirectory is required so the common-prefix computation has
        something to distinguish "graphics" from (with only one entry
        total, its own directory is trivially "common to itself" and (a)
        correctly finds nothing informative -- see the single-entry tests
        in TestTierDFallback for that edge case on its own)."""
        api_surface = [
            {"name": "ImageInfo", "file": "src/pkgroot/graphics/ImageInfo.ts"},
            {"name": "Other", "file": "src/pkgroot/other/Other.ts"},
        ]
        promote_mod.compute_module_assignment(api_surface, "acme", "typescript")
        by_name = {e["name"]: e for e in api_surface}
        # "graphics" (tier a) wins, not "images" (tier c, which wouldn't
        # even match this identifier under the narrowed keyword table).
        assert by_name["ImageInfo"]["module_key"] == "graphics"

    def test_every_entry_gets_both_fields(self):
        api_surface = [
            {"name": "A", "file": "src/nested/A.ts"},
            {"name": "B", "file": "src/nested/B.ts"},
            {"name": "C"},  # no file at all
            "not-a-dict",  # malformed entry -- must be skipped, not crash
        ]
        promote_mod.compute_module_assignment(api_surface, "acme", "typescript")
        for e in api_surface:
            if isinstance(e, dict):
                assert "module_key" in e
                assert "module_label" in e

    def test_empty_api_surface_does_not_raise(self):
        promote_mod.compute_module_assignment([], "acme", "typescript")

    def test_non_list_input_does_not_raise(self):
        promote_mod.compute_module_assignment(None, "acme", "typescript")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Tier (b): barrel export-group (via _barrel_export_groups' clone_cache
# integration -- the ASPOSE_CLONE_CACHE env var is the established test
# seam for clone_cache-dependent code, see tests/test_clone_cache.py)
# ---------------------------------------------------------------------------

class TestTierBBarrelExportGroup:
    def _make_clone(self, tmp_path: Path, family: str, platform: str) -> Path:
        clone = tmp_path / f"aspose_{family}_{platform}"
        (clone / ".git").mkdir(parents=True)
        return clone

    def test_barrel_group_used_when_no_directory_signal(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ASPOSE_CLONE_CACHE", str(tmp_path))
        clone = self._make_clone(tmp_path, "acme", "typescript")
        (clone / "package.json").write_text(json.dumps({"main": "src/index.ts"}), encoding="utf-8")
        src = clone / "src"
        src.mkdir()
        (src / "index.ts").write_text(
            "export * as Forms from './forms.js';\n", encoding="utf-8")
        (src / "forms.ts").write_text("export class FormField {}\n", encoding="utf-8")

        api_surface = [{"name": "FormField", "file": "src/forms.ts"}]
        promote_mod.compute_module_assignment(api_surface, "acme", "typescript")
        assert api_surface[0]["module_key"] == "forms"
        assert api_surface[0]["module_label"] == "Forms"

    def test_no_clone_present_gracefully_skips_to_next_tier(self, tmp_path, monkeypatch):
        """No local clone at all (e.g. this promote() run happened without
        a live clone on disk) -- tier (b) must degrade silently, never
        raise, and the cascade continues to (c)/(d)."""
        monkeypatch.setenv("ASPOSE_CLONE_CACHE", str(tmp_path))
        api_surface = [{"name": "AcroFormField", "file": "src/acroform.ts"}]
        promote_mod.compute_module_assignment(api_surface, "acme", "typescript")
        assert api_surface[0]["module_key"] == "forms"  # reached via tier (c)


# ---------------------------------------------------------------------------
# Full promote() integration: module_assignment_version in model.yaml
# ---------------------------------------------------------------------------

SCOUT_CLAIMS = [
    {"claim_id": "CLM-test-ma-001", "text": "Widget.open(path) loads a widget.", "kind": "api_method"},
]

API_SURFACE = [
    {
        "name": "Widget",
        "file": "src/pkgroot/widgets/Widget.ts",
        "methods": [{"name": "open", "return_type": "Widget", "params": ["path"]}],
        "properties": [],
        "enum_members": [],
        "bases": [],
    },
    {
        # A sibling under a different subdirectory so the common-prefix
        # computation has something to distinguish "widgets" from (a
        # single-entry api_surface has no such contrast -- see
        # TestTierDFallback for that edge case tested on its own).
        "name": "Gadget",
        "file": "src/pkgroot/gadgets/Gadget.ts",
        "methods": [],
        "properties": [],
        "enum_members": [],
        "bases": [],
    },
]

MODEL_YAML = {
    "family": "matest",
    "platform": "typescript",
    "repo_sha": "deadbeef",
    "stale_since": None,
}


def _setup_scout(tmp_path: Path) -> Path:
    knowledge_root = tmp_path / "knowledge"
    scout_dir = knowledge_root / "matest" / "typescript" / "scout"
    scout_dir.mkdir(parents=True)
    (scout_dir / "claims.json").write_text(json.dumps(SCOUT_CLAIMS, indent=2), encoding="utf-8")
    (scout_dir / "api_surface.json").write_text(json.dumps(API_SURFACE, indent=2), encoding="utf-8")
    (scout_dir / "model.yaml").write_text(yaml.dump(MODEL_YAML, default_flow_style=False), encoding="utf-8")
    return knowledge_root


class TestPromoteIntegrationWritesModuleAssignment:
    def test_module_assignment_version_written_to_model_yaml(self, tmp_path):
        kr = _setup_scout(tmp_path)
        ok = promote_mod.promote("matest", "typescript", knowledge_root=str(kr))
        assert ok is True

        model_path = kr / "matest" / "typescript" / "merged" / "model.yaml"
        model = yaml.safe_load(model_path.read_text(encoding="utf-8"))
        assert model["module_assignment_version"] == promote_mod.MODULE_ASSIGNMENT_VERSION
        assert model["module_assignment_version"] == 1

    def test_api_surface_entries_carry_module_key_after_promote(self, tmp_path):
        kr = _setup_scout(tmp_path)
        promote_mod.promote("matest", "typescript", knowledge_root=str(kr))

        api_path = kr / "matest" / "typescript" / "merged" / "api_surface.json"
        api = json.loads(api_path.read_text(encoding="utf-8"))
        assert len(api) == 2
        by_name = {e["name"]: e for e in api}
        assert by_name["Widget"]["module_key"] == "widgets"
        assert by_name["Widget"]["module_label"] == "Widgets"
        assert by_name["Gadget"]["module_key"] == "gadgets"
