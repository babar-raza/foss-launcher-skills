"""Tests for Rust extraction support (cells/rust onboarding, 2026-07-25).

Rust is the first extraction language added since Go. Its two structural
novelties are covered here against a real on-disk fixture crate
(``fixtures/rust_crate/``) rather than inline snippets, because the
impl-block association must be proven across files:

- Methods live in ``impl`` blocks outside the type (like Go receiver
  methods): ``_associate_rust_impl_methods`` must relocate them, including
  impls in a *different file* than the struct (src/save.rs → Workbook).
- Visibility is the explicit ``pub`` keyword; ``pub(crate)``/``pub(super)``
  are crate-internal and must never surface as public API.

Also covered: rustdoc (``///`` + ``#[doc]``) extraction, ``#[derive]`` bases,
trait supertraits and default methods, enum variants, Cargo.toml manifest
parsing, crate-root detection, and install/import/runtime rendering.
"""

from pathlib import Path

import pytest

# sys.path is set by tests/conftest.py — no manual insert needed here.
import scout
from extraction.api_surface import extract_api_surface
from extraction.outputs import (
    _canonical_import,
    _install_command,
    _is_enum_class,
    _runtime_requirement,
)
from extraction.package_manifest import parse_manifest
from extraction.package_root import detect_package_root

FIXTURE = Path(__file__).parent / "fixtures" / "rust_crate"


def _parse(code: str):
    parser = scout.get_parser("rust")
    return parser.parse(code.encode("utf-8")).root_node


@pytest.fixture(scope="module")
def extracted():
    """Run extract_api_surface once over the fixture crate."""
    parser = scout.get_parser("rust")
    pkg_root = FIXTURE / "src"
    classes, claims, scanned, packages, report = extract_api_surface(
        parser, "rust", pkg_root, FIXTURE, "cells"
    )
    return {
        "classes": {c["name"]: c for c in classes},
        "claims": claims,
        "scanned": scanned,
        "packages": packages,
        "report": report,
    }


# ---------------------------------------------------------------------------
# Registry constants
# ---------------------------------------------------------------------------


class TestRustRegistryConstants:
    def test_platform_to_lang(self):
        assert scout.PLATFORM_TO_LANG["rust"] == "rust"

    def test_class_types(self):
        assert scout._CLASS_TYPES["rust"] == {
            "struct_item", "enum_item", "trait_item", "union_item"
        }

    def test_func_types_include_trait_signatures(self):
        assert "function_item" in scout._FUNC_TYPES["rust"]
        assert "function_signature_item" in scout._FUNC_TYPES["rust"]

    def test_file_extension(self):
        assert scout._FILE_EXTENSIONS["rust"] == ".rs"

    def test_parser_loads(self):
        assert scout.get_parser("rust") is not None

    def test_not_impl_pattern_matches_rust_macros(self):
        pat = scout._NOT_IMPL_PATTERNS["rust"]
        assert pat.search("unimplemented!()")
        assert pat.search("todo!()")
        assert pat.search('panic!("not implemented yet")')
        assert not pat.search('panic!("index out of bounds")')


# ---------------------------------------------------------------------------
# Visibility: pub / pub(crate) / trait members / impl members
# ---------------------------------------------------------------------------


class TestRustVisibility:
    RS = """
pub struct Public;
pub(crate) struct CrateOnly;
struct Private;

pub trait Marker {
    fn required(&self);
    fn defaulted(&self) -> u32 { 0 }
}

pub struct Holder;

impl Holder {
    pub fn visible(&self) {}
    fn hidden(&self) {}
}

impl Marker for Holder {
    fn required(&self) {}
}
"""

    def _nodes(self, types):
        return scout.collect_nodes(_parse(self.RS), types)

    def test_pub_struct_public(self):
        structs = {scout._node_name(n, "rust"): n
                   for n in self._nodes({"struct_item"})}
        assert scout.is_public(structs["Public"], "rust") is True

    def test_pub_crate_struct_not_public(self):
        structs = {scout._node_name(n, "rust"): n
                   for n in self._nodes({"struct_item"})}
        assert scout.is_public(structs["CrateOnly"], "rust") is False

    def test_bare_struct_not_public(self):
        structs = {scout._node_name(n, "rust"): n
                   for n in self._nodes({"struct_item"})}
        assert scout.is_public(structs["Private"], "rust") is False

    def test_trait_members_implicitly_public(self):
        fns = {scout._node_name(n, "rust"): n
               for n in self._nodes({"function_item", "function_signature_item"})}
        assert scout.is_public(fns["required"], "rust") is True
        assert scout.is_public(fns["defaulted"], "rust") is True

    def test_inherent_impl_requires_pub(self):
        fns = {}
        for n in self._nodes({"function_item"}):
            fns.setdefault(scout._node_name(n, "rust"), []).append(n)
        assert scout.is_public(fns["visible"][0], "rust") is True
        assert scout.is_public(fns["hidden"][0], "rust") is False

    def test_trait_impl_members_public_without_pub(self):
        # `fn required` appears twice: in the trait and in the trait impl.
        nodes = [n for n in self._nodes({"function_item", "function_signature_item"})
                 if scout._node_name(n, "rust") == "required"]
        assert len(nodes) == 2
        for n in nodes:
            assert scout.is_public(n, "rust") is True


# ---------------------------------------------------------------------------
# Bases: #[derive], supertraits
# ---------------------------------------------------------------------------


class TestRustBases:
    def test_derive_traits_captured(self):
        code = "#[derive(Debug, Clone, PartialEq)]\npub struct S { pub x: u32 }\n"
        node = scout.collect_nodes(_parse(code), {"struct_item"})[0]
        bases = scout._extract_bases(node, "rust")
        assert set(bases) == {"Debug", "Clone", "PartialEq"}

    def test_supertraits_captured(self):
        code = "pub trait Child: Parent + Send {}\n"
        node = scout.collect_nodes(_parse(code), {"trait_item"})[0]
        bases = scout._extract_bases(node, "rust")
        assert "Parent" in bases
        assert "Send" in bases

    def test_no_bases_for_plain_struct(self):
        code = "pub struct Plain { pub x: u32 }\n"
        node = scout.collect_nodes(_parse(code), {"struct_item"})[0]
        assert scout._extract_bases(node, "rust") == []


# ---------------------------------------------------------------------------
# Rustdoc extraction
# ---------------------------------------------------------------------------


class TestRustdocExtraction:
    def _doc(self, code: str, node_type: str = "struct_item") -> str:
        from extraction.api_surface import _extract_doc_comment
        node = scout.collect_nodes(_parse(code), {node_type})[0]
        return _extract_doc_comment(node, "rust")

    def test_single_line_doc(self):
        assert self._doc("/// Represents a cell.\npub struct Cell;\n") == \
            "Represents a cell."

    def test_multi_line_first_sentence(self):
        code = "/// A workbook.\n/// More detail here.\npub struct Wb;\n"
        assert self._doc(code) == "A workbook."

    def test_doc_survives_derive_attribute(self):
        code = "/// Documented.\n#[derive(Debug)]\npub struct D;\n"
        assert self._doc(code) == "Documented."

    def test_doc_attr_fallback(self):
        code = '#[doc = "Attr documented."]\npub struct A;\n'
        assert self._doc(code) == "Attr documented."

    def test_inner_doc_not_attributed_to_item(self):
        code = "//! Module docs.\npub struct NoDoc;\n"
        assert self._doc(code) == ""

    def test_plain_comment_not_doc(self):
        code = "// regular comment\npub struct NoDoc;\n"
        assert self._doc(code) == ""


# ---------------------------------------------------------------------------
# Full fixture-crate extraction
# ---------------------------------------------------------------------------


class TestFixtureCrateExtraction:
    EXPECTED_TYPES = {"Workbook", "SheetRef", "CellValue", "Saveable", "Coord"}

    def test_exact_public_type_set(self, extracted):
        type_names = {n for n, c in extracted["classes"].items()
                      if c.get("kind") != "function"}
        assert type_names == self.EXPECTED_TYPES

    def test_pub_crate_types_excluded(self, extracted):
        assert "HiddenState" not in extracted["classes"]
        assert "Scratchpad" not in extracted["classes"]

    def test_no_parse_errors(self, extracted):
        assert extracted["report"]["parse_errors"] == []

    def test_workbook_methods_associated(self, extracted):
        methods = {m["name"] for m in extracted["classes"]["Workbook"]["methods"]}
        assert {"new", "save", "export_pdf"} <= methods

    def test_cross_file_trait_impl_associated(self, extracted):
        """impl Saveable for Workbook lives in src/save.rs, not workbook.rs."""
        methods = {m["name"] for m in extracted["classes"]["Workbook"]["methods"]}
        assert "save_as" in methods

    def test_trait_impl_recorded_in_bases(self, extracted):
        assert "Saveable" in extracted["classes"]["Workbook"]["bases"]

    def test_derive_traits_in_bases(self, extracted):
        bases = extracted["classes"]["Workbook"]["bases"]
        assert "Debug" in bases
        assert "Clone" in bases

    def test_private_impl_method_excluded(self, extracted):
        methods = {m["name"] for m in extracted["classes"]["Workbook"]["methods"]}
        assert "touch" not in methods

    def test_new_marked_constructor(self, extracted):
        new = next(m for m in extracted["classes"]["Workbook"]["methods"]
                   if m["name"] == "new")
        assert new["is_constructor"] is True

    def test_method_return_type(self, extracted):
        save = next(m for m in extracted["classes"]["Workbook"]["methods"]
                    if m["name"] == "save")
        assert save["return_type"] == "Result<(), String>"

    def test_method_params_skip_self(self, extracted):
        save = next(m for m in extracted["classes"]["Workbook"]["methods"]
                    if m["name"] == "save")
        assert [p["name"] for p in save["params"]] == ["path"]
        assert save["params"][0]["type"] == "&str"

    def test_method_doc(self, extracted):
        new = next(m for m in extracted["classes"]["Workbook"]["methods"]
                   if m["name"] == "new")
        assert new["doc"] == "Creates a new empty workbook."

    def test_pub_fields_extracted(self, extracted):
        props = {p["name"]: p for p in extracted["classes"]["Workbook"]["properties"]}
        assert set(props) == {"path", "sheet_count"}
        assert props["path"]["type"] == "String"
        assert props["path"]["doc"] == "File system path of the workbook."

    def test_non_pub_fields_excluded(self, extracted):
        props = {p["name"] for p in extracted["classes"]["Workbook"]["properties"]}
        assert "dirty" not in props        # pub(crate)
        assert "internal_id" not in props  # private

    def test_generic_struct_field(self, extracted):
        props = {p["name"] for p in extracted["classes"]["SheetRef"]["properties"]}
        assert "inner" in props

    def test_enum_variants(self, extracted):
        cv = extracted["classes"]["CellValue"]
        assert cv["kind"] == "enum_item"
        names = [m["name"] for m in cv["enum_members"]]
        assert names == ["Number", "Text", "Empty"]
        assert _is_enum_class(cv) is True

    def test_trait_methods_extracted(self, extracted):
        methods = {m["name"]: m for m in extracted["classes"]["Saveable"]["methods"]}
        assert set(methods) == {"save_as", "format_tag"}
        assert methods["save_as"]["return_type"] == "Result<(), String>"
        assert methods["save_as"]["doc"] == "Persists the object to the given path."

    def test_trait_default_method_flattened_into_impl_type(self, extracted):
        """_flatten_inheritance copies Saveable.format_tag into Workbook."""
        methods = {m["name"] for m in extracted["classes"]["Workbook"]["methods"]}
        assert "format_tag" in methods

    def test_doc_attr_struct(self, extracted):
        assert extracted["classes"]["Coord"]["doc"] == "Cell coordinate pair."

    def test_class_doc_first_sentence(self, extracted):
        assert extracted["classes"]["Workbook"]["doc"] == "A spreadsheet workbook."

    def test_class_import_module_path(self, extracted):
        wb = extracted["classes"]["Workbook"]
        assert wb["class_import"] == "workbook::Workbook"
        assert wb["canonical_namespace"] == "workbook"
        assert extracted["classes"]["CellValue"]["class_import"] == "cell::CellValue"

    def test_top_level_function_kept(self, extracted):
        fn = extracted["classes"]["open"]
        assert fn["kind"] == "function"
        assert fn["return_type"] == "Workbook"
        assert "receiver_type" not in fn

    def test_private_functions_excluded(self, extracted):
        assert "private_helper" not in extracted["classes"]
        assert "scratch" not in extracted["classes"]       # pub(crate)
        assert "coord_roundtrip" not in extracted["classes"]  # #[cfg(test)] fn

    def test_modules_tracked_as_packages(self, extracted):
        assert "workbook" in extracted["packages"]
        assert "cell" in extracted["packages"]

    def test_visibility_field(self, extracted):
        assert extracted["classes"]["Workbook"]["visibility"] == "public"


# ---------------------------------------------------------------------------
# Crate root detection + Cargo.toml manifest
# ---------------------------------------------------------------------------


class TestRustPackageIdentity:
    def test_detect_rust_root_is_src(self):
        assert detect_package_root(FIXTURE, "rust") == FIXTURE / "src"

    def test_manifest_fields(self):
        info = parse_manifest(FIXTURE, "rust")
        assert info["name"] == "aspose-cells-fixture"
        assert info["version"] == "0.9.1"
        assert info["license"] == "MIT"
        assert info["edition"] == "2021"
        assert info["rust_version"] == "1.70"
        assert info["canonical_package"] == "aspose_cells_fixture"

    def test_manifest_missing_cargo_toml(self, tmp_path):
        assert parse_manifest(tmp_path, "rust") == {}


# ---------------------------------------------------------------------------
# Install / import / runtime rendering
# ---------------------------------------------------------------------------


class TestRustInstallRendering:
    MANIFEST = {
        "name": "aspose-cells-foss-rust",
        "version": "26.7.0",
        "canonical_package": "aspose_cells_foss_rust",
        "rust_version": "1.70",
        "edition": "2021",
    }

    def test_git_dependency_form(self):
        cmd = _install_command(
            "rust", self.MANIFEST,
            "https://github.com/aspose-cells-foss/Aspose.Cells-FOSS-for-Rust.git",
        )
        assert "[dependencies]" in cmd
        assert ('aspose-cells-foss-rust = { git = '
                '"https://github.com/aspose-cells-foss/Aspose.Cells-FOSS-for-Rust" }'
                ) in cmd
        assert ".git" not in cmd.split("git = ")[1]

    def test_cargo_add_fallback_without_repo_url(self):
        assert _install_command("rust", self.MANIFEST) == \
            "cargo add aspose-cells-foss-rust@26.7.0"

    def test_canonical_import(self):
        assert _canonical_import("rust", self.MANIFEST) == \
            "use aspose_cells_foss_rust::*;"

    def test_canonical_import_falls_back_to_crate_name(self):
        assert _canonical_import("rust", {"name": "my-crate"}) == "use my_crate::*;"

    def test_runtime_requirement_prefers_rust_version(self):
        assert _runtime_requirement("rust", self.MANIFEST) == "Rust 1.70+"

    def test_runtime_requirement_edition_fallback(self):
        assert _runtime_requirement("rust", {"edition": "2021"}) == \
            "Rust edition 2021"

    def test_other_platforms_unchanged(self):
        assert _install_command("python", {"name": "pkg", "version": "1.0"}) == \
            "pip install pkg>=1.0"


# ---------------------------------------------------------------------------
# Scout constructor smoke (no run() — snippets/formats land in the next slice)
# ---------------------------------------------------------------------------


class TestScoutRustConstruction:
    def test_scout_constructs_for_rust(self, tmp_path):
        from extraction.scout import Scout
        s = Scout(family="cells", platform="rust", repo=FIXTURE,
                  output=tmp_path / "out")
        assert s.language == "rust"
        assert s.pkg_root == FIXTURE / "src"
        assert s.manifest["name"] == "aspose-cells-fixture"


# ---------------------------------------------------------------------------
# validate_scout_output
# ---------------------------------------------------------------------------


class TestValidateScoutOutputRust:
    def test_counts_rs_files(self):
        from extraction.validate_scout_output import _count_class_bearing_files
        assert _count_class_bearing_files(FIXTURE, "rust") > 0

    def test_extraction_failure_verdict_when_zero_classes(self):
        from extraction.validate_scout_output import validate_scout_output
        result = validate_scout_output(
            {"stats": {"class_count": 0}}, FIXTURE, "rust")
        assert result["verdict"] == "EXTRACTION_FAILURE"
