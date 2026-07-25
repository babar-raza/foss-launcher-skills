"""RUST-TOKENOPS-001: Rust `EnumName::Variant` scope-resolution enum access.

Rust enum variants are accessed as `CellValue::Number`, `ChartType::Column`, etc. — the
`::` syntax already has C++ handling (_CPP_ENUM_ACCESS), but that pattern requires
ALL_CAPS members (C++ convention) and never matched Rust's PascalCase variant names.
This left every real Rust enum-variant reference in generated content unextracted,
so token_ops silently skipped verifying them — the actual UNKNOWN_CLASS WARN seen on
cells/rust content (`CellValue::Number`) came from a *different* code path (bare word
extraction), not from enum verification never firing correctly.

Confirmed against the real cells/rust knowledge model (2026-07-25): all 8 distinct
`Type::Variant` patterns present in shipped content are genuine enum members in
api_surface.json (CellValue::Number, ChartType::Column/Line, OperatorType::Between,
ValidationAlertType::Warning, ValidationType::Custom/Decimal/List).
"""
import sys
import tempfile
from pathlib import Path

import pytest

# sys.path is set by tests/conftest.py
from token_ops import Token, _extract_from_code_line, extract_tokens, verify_tokens


def _make_md(content: str) -> Path:
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8"
    )
    f.write(content)
    f.close()
    return Path(f.name)


class _FakeKnowledge:
    """Minimal stand-in for knowledge_core.Knowledge, enum-path only."""

    def __init__(self, classes: dict[str, set[str]]):
        self.platform = "rust"
        self.surface_tier = 1
        self.classes = set(classes)
        self.enum_members = classes
        self.methods = {}
        self.properties = {}
        self.valid_imports = set()

    def has_property(self, cls, name):
        return False

    def has_enum_member(self, cls, name):
        return name in self.enum_members.get(cls, set())

    def closest_match(self, actual, name):
        return []


class TestRustEnumAccessExtraction:
    """_extract_from_code_line must extract Type::Variant as an 'enum' token for rust."""

    def test_extracts_enum_variant_access(self):
        var_types: dict = {}
        tokens = _extract_from_code_line(
            'cells.get("G1")?.put_formula_with_cached_value("=F1*2", CellValue::Number(20.0))?;',
            1, var_types, "rust",
        )
        enum_tokens = [t for t in tokens if t.kind == "enum"]
        assert len(enum_tokens) == 1
        assert enum_tokens[0].class_name == "CellValue"
        assert enum_tokens[0].member_name == "Number"

    def test_extracts_multiple_variants_same_line(self):
        var_types: dict = {}
        tokens = _extract_from_code_line(
            "charts.add(ChartType::Column, range1)?; charts.add(ChartType::Line, range2)?;",
            1, var_types, "rust",
        )
        enum_tokens = [(t.class_name, t.member_name) for t in tokens if t.kind == "enum"]
        assert ("ChartType", "Column") in enum_tokens
        assert ("ChartType", "Line") in enum_tokens

    @pytest.mark.parametrize("cls,member", [
        ("OperatorType", "Between"),
        ("ValidationAlertType", "Warning"),
        ("ValidationType", "Custom"),
        ("ValidationType", "Decimal"),
        ("ValidationType", "List"),
    ])
    def test_extracts_every_confirmed_pattern(self, cls, member):
        var_types: dict = {}
        tokens = _extract_from_code_line(f"x.set_type({cls}::{member});", 1, var_types, "rust")
        enum_tokens = [(t.class_name, t.member_name) for t in tokens if t.kind == "enum"]
        assert (cls, member) in enum_tokens

    def test_associated_function_not_misread_as_enum(self):
        """Workbook::new / Workbook::load_xlsx are snake_case fn names — must never
        be extracted as enum-variant access (the member group requires uppercase)."""
        var_types: dict = {}
        tokens = _extract_from_code_line(
            "let mut workbook = Workbook::new();", 1, var_types, "rust",
        )
        assert not [t for t in tokens if t.kind == "enum"]

        tokens2 = _extract_from_code_line(
            'let loaded = Workbook::load_xlsx("hello.xlsx")?;', 1, var_types, "rust",
        )
        assert not [t for t in tokens2 if t.kind == "enum"]

    def test_other_platforms_unaffected(self):
        """The C++ ALL_CAPS pattern and non-rust platforms must not pick up
        PascalCase Rust-style variant access, and vice versa."""
        var_types: dict = {}
        # cpp: PascalCase member must NOT match the C++ ALL_CAPS-only pattern
        tokens = _extract_from_code_line("auto x = CellValue::Number;", 1, var_types, "cpp")
        assert not [t for t in tokens if t.kind == "enum"]

    def test_rust_scope_access_ignored_on_non_rust_platform(self):
        var_types: dict = {}
        tokens = _extract_from_code_line(
            "let v = CellValue::Number(1.0);", 1, var_types, "python",
        )
        assert not [t for t in tokens if t.kind == "enum"]


class TestRustEnumAccessEndToEnd:
    """extract_tokens + verify_tokens over a real fenced rust block."""

    def test_confirmed_variant_produces_no_unknown_class_warn(self):
        md = _make_md(
            "```rust\n"
            'cells.get("G1")?.put_formula_with_cached_value("=F1*2", CellValue::Number(20.0))?;\n'
            "```\n"
        )
        tokens = extract_tokens(md, "rust")
        knowledge = _FakeKnowledge({"CellValue": {"Number", "String", "Bool"}})
        findings = verify_tokens(tokens, knowledge, md)
        assert not [f for f in findings if "UNKNOWN_CLASS" in f.message]
        assert not [f for f in findings if f.level == "FAIL"]
        md.unlink()

    def test_genuinely_wrong_variant_still_flagged(self):
        """A fabricated variant on a real enum must still FAIL — this fix must not
        create a blanket suppression for the rust `::` syntax."""
        md = _make_md(
            "```rust\n"
            "cells.get(\"A1\")?.put_value(CellValue::NotARealVariant(1.0))?;\n"
            "```\n"
        )
        tokens = extract_tokens(md, "rust")
        knowledge = _FakeKnowledge({"CellValue": {"Number", "String", "Bool"}})
        findings = verify_tokens(tokens, knowledge, md)
        assert any(f.level == "FAIL" and "enum member not found" in f.message for f in findings)
        md.unlink()

    def test_unknown_enum_class_still_flagged(self):
        """A `::`-accessed type that genuinely isn't in api_surface.json must still
        produce UNKNOWN_CLASS — the fix must not blanket-allowlist Rust `::` access."""
        md = _make_md(
            "```rust\n"
            "let x = TotallyFakeType::SomeVariant;\n"
            "```\n"
        )
        tokens = extract_tokens(md, "rust")
        knowledge = _FakeKnowledge({"CellValue": {"Number"}})
        findings = verify_tokens(tokens, knowledge, md)
        assert any("UNKNOWN_CLASS" in f.message and "TotallyFakeType" in f.message
                   for f in findings)
        md.unlink()
