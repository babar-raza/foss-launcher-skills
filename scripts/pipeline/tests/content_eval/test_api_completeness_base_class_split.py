"""ST-149: api_completeness must not flag a subclass reference page for
members that are genuinely documented on a BASE class's own reference page.

Found live 2026-08-31 (MT040 Phase I, TC-MT040-56): after `LoadOptions`/
`SaveOptions` (abstract classes) gained their own reference pages for the
first time, 12 concrete subclass pages
({Collada,Fbx,Gltf,Obj,Stl,ThreeMf}{Load,Save}Options.md) each dropped from
grade A to C, all flagged as missing 5/6 public members. Verified NOT a real
defect: `api_surface.json` records inherited-and-redeclared property names as
the SUBCLASS's OWN properties too (an extraction-shape quirk, not
investigated further here), and the base class's own page genuinely
documents them -- the documentation is complete, just correctly split across
base/subclass pages instead of duplicated on every one.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from content_eval.evaluators.api_completeness import ApiCompletenessEvaluator
from content_eval.models import Page


def _write_page(tmp_path: Path, filename_stem: str, link_title: str, body: str) -> Page:
    ref_dir = tmp_path / "content" / "reference.aspose.org" / "en" / "3d" / "typescript"
    ref_dir.mkdir(parents=True, exist_ok=True)
    md_file = ref_dir / f"{filename_stem}.md"
    frontmatter = f"---\ntitle: {link_title}\nlinkTitle: {link_title}\n---\n\n"
    md_file.write_text(frontmatter + body, encoding="utf-8")
    return Page.load(md_file)


_LOAD_OPTIONS_HIERARCHY = [
    {
        "name": "LoadOptions",
        "bases": [],
        "methods": [],
        "properties": [
            {"name": n} for n in
            ("encoding", "fileFormat", "fileName", "fileSystem", "lookupPaths")
        ],
    },
    {
        "name": "FbxLoadOptions",
        "bases": ["LoadOptions"],
        "methods": [],
        # The TS scout duplicates the 5 inherited names onto the subclass's
        # own entry (the real, confirmed extraction shape) plus one genuinely
        # own property.
        "properties": [
            {"name": n} for n in
            ("encoding", "fileFormat", "fileName", "fileSystem", "lookupPaths", "embedTextures")
        ],
    },
]

_BASE_PAGE_BODY = (
    "## Properties\n\n"
    "| Name | Type | Access | Description |\n"
    "|------|------|--------|-------------|\n"
    "| `encoding` | `: string` | Read/Write | Text encoding. |\n"
    "| `fileFormat` | `: FileFormat` | Read/Write | File format hint. |\n"
    "| `fileName` | `: string` | Read/Write | Source file name. |\n"
    "| `fileSystem` | `: FileSystem` | Read/Write | Custom file system. |\n"
    "| `lookupPaths` | `: string[]` | Read/Write | Texture lookup paths. |\n"
)


class TestBaseClassDocumentationSplit:
    def test_inherited_members_satisfied_by_base_page_are_not_flagged(self, tmp_path):
        _write_page(tmp_path, "LoadOptions", "LoadOptions", _BASE_PAGE_BODY)
        subclass_body = (
            "## Properties\n\n"
            "| Name | Type | Access | Description |\n"
            "|------|------|--------|-------------|\n"
            "| `embedTextures` | `: boolean` | Read/Write | Embed referenced textures. |\n\n"
            "Inherits additional properties from [LoadOptions](../LoadOptions).\n"
        )
        page = _write_page(tmp_path, "FbxLoadOptions", "FbxLoadOptions", subclass_body)

        ev = ApiCompletenessEvaluator()
        with patch.object(ev, "_load_api_surface", return_value=_LOAD_OPTIONS_HIERARCHY):
            findings = ev.evaluate(page, knowledge=None)

        assert findings == [], (
            "The 5 inherited properties are genuinely documented on LoadOptions.md; "
            f"must not be flagged as missing from FbxLoadOptions.md, got: {findings}"
        )

    def test_member_missing_from_both_pages_is_still_flagged(self, tmp_path):
        """Regression guard: a genuinely undocumented member (absent from
        BOTH the subclass page and the base page) must still be caught."""
        incomplete_base_body = (
            "## Properties\n\n"
            "| Name | Type | Access | Description |\n"
            "|------|------|--------|-------------|\n"
            "| `encoding` | `: string` | Read/Write | Text encoding. |\n"
            "| `fileFormat` | `: FileFormat` | Read/Write | File format hint. |\n"
            "| `fileName` | `: string` | Read/Write | Source file name. |\n"
            "| `fileSystem` | `: FileSystem` | Read/Write | Custom file system. |\n"
            # lookupPaths deliberately omitted from the base page too.
        )
        _write_page(tmp_path, "LoadOptions", "LoadOptions", incomplete_base_body)
        subclass_body = (
            "## Properties\n\n"
            "| Name | Type | Access | Description |\n"
            "|------|------|--------|-------------|\n"
            "| `embedTextures` | `: boolean` | Read/Write | Embed referenced textures. |\n"
        )
        page = _write_page(tmp_path, "FbxLoadOptions", "FbxLoadOptions", subclass_body)

        ev = ApiCompletenessEvaluator()
        with patch.object(ev, "_load_api_surface", return_value=_LOAD_OPTIONS_HIERARCHY):
            findings = ev.evaluate(page, knowledge=None)

        assert len(findings) == 1
        assert "lookupPaths" in findings[0].message
        # The 4 properties that ARE documented on the base page must not
        # be reported as missing.
        for satisfied in ("encoding", "fileFormat", "fileName", "fileSystem"):
            assert satisfied not in findings[0].message

    def test_no_base_page_on_disk_still_flags_as_before(self, tmp_path):
        """Regression guard: when the base class has no reference page at
        all (e.g. not yet generated), behavior is unchanged -- flag as
        missing, same as before this fix."""
        subclass_body = (
            "## Properties\n\n"
            "| Name | Type | Access | Description |\n"
            "|------|------|--------|-------------|\n"
            "| `embedTextures` | `: boolean` | Read/Write | Embed referenced textures. |\n"
        )
        page = _write_page(tmp_path, "FbxLoadOptions", "FbxLoadOptions", subclass_body)

        ev = ApiCompletenessEvaluator()
        with patch.object(ev, "_load_api_surface", return_value=_LOAD_OPTIONS_HIERARCHY):
            findings = ev.evaluate(page, knowledge=None)

        assert len(findings) == 1
        assert findings[0].level == "FAIL"
        for name in ("encoding", "fileFormat", "fileName", "fileSystem", "lookupPaths"):
            assert name in findings[0].message

    def test_unrelated_class_with_no_bases_unaffected(self, tmp_path):
        """A class with no `bases` at all takes the pre-existing code path
        (the base-walk loop never executes) and behaves exactly as before."""
        no_base_hierarchy = [
            {
                "name": "Standalone",
                "bases": [],
                "methods": [{"name": "doThing"}],
                "properties": [],
            },
        ]
        page = _write_page(tmp_path, "Standalone", "Standalone", "Nothing documented here.\n")

        ev = ApiCompletenessEvaluator()
        with patch.object(ev, "_load_api_surface", return_value=no_base_hierarchy):
            findings = ev.evaluate(page, knowledge=None)

        assert len(findings) == 1
        assert "doThing" in findings[0].message
