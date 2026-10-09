"""PDF-JAVA-REFRESH-003 (MT030): PascalCase enum constants mis-tokenized as property access.

Found live in content/kb.aspose.org/en/pdf/java/use-cases.md:233, correct code
`ConvertErrorAction.Delete` (a real enum member per knowledge/pdf/java/merged/api_surface.json,
enum_members: Delete, Delcete, None) was flagged FAIL "property not found on ConvertErrorAction".

Root cause: the extraction-time "skip enum access" heuristic in _extract_from_code_line only
recognizes ALL_CAPS member names (`prop == prop.upper()`), so a PascalCase Java enum constant
like `Delete` is tokenized as kind="property" instead of kind="enum". The enum-verification
branch already falls back to has_property() when a class has no enum_members (EC-03); the
property-verification branch had no symmetric fallback to has_enum_member().
"""
import tempfile
from pathlib import Path

import pytest

# sys.path is set by tests/conftest.py
from token_ops import extract_tokens, verify_tokens


def _make_md(content: str) -> Path:
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8"
    )
    f.write(content)
    f.close()
    return Path(f.name)


class _FakeKnowledge:
    """Minimal stand-in for knowledge_core.Knowledge, property/enum-fallback path only."""

    def __init__(self, classes, properties, enum_members, methods=None):
        self.platform = "java"
        self.surface_tier = 1
        self.classes = set(classes)
        self.properties = properties
        self.enum_members = enum_members
        self.methods = methods or {}
        self.valid_imports = set()
        self.workaround_members = set()

    def has_property(self, cls, name):
        return name in self.properties.get(cls, set())

    def has_enum_member(self, cls, name):
        return name in self.enum_members.get(cls, set())

    def has_method(self, cls, name):
        return name in self.methods.get(cls, set())

    def closest_match(self, actual, name):
        return []


class TestPascalCaseEnumPropertyFallback:
    def test_pascalcase_enum_constant_produces_no_fail(self):
        md = _make_md(
            "```java\n"
            "try (Document doc = new Document(\"input.pdf\")) {\n"
            "    doc.convert(\"log.xml\", PdfFormat.PDF_A_1B, ConvertErrorAction.Delete);\n"
            "}\n"
            "```\n"
        )
        tokens = extract_tokens(md, "java")
        knowledge = _FakeKnowledge(
            classes={"ConvertErrorAction"},
            properties={"ConvertErrorAction": {"delete"}},
            enum_members={"ConvertErrorAction": {"Delete", "Delcete", "None"}},
        )
        findings = verify_tokens(tokens, knowledge, md)
        assert not [f for f in findings if f.level == "FAIL"], findings
        md.unlink()

    def test_genuinely_invalid_member_still_fails(self):
        """Negative control: a member absent from BOTH properties and enum_members
        must still FAIL — the fallback must not silence real errors."""
        md = _make_md(
            "```java\n"
            "doc.convert(\"log.xml\", PdfFormat.PDF_A_1B, ConvertErrorAction.Bogus);\n"
            "```\n"
        )
        tokens = extract_tokens(md, "java")
        knowledge = _FakeKnowledge(
            classes={"ConvertErrorAction"},
            properties={"ConvertErrorAction": {"delete"}},
            enum_members={"ConvertErrorAction": {"Delete", "Delcete", "None"}},
        )
        findings = verify_tokens(tokens, knowledge, md)
        fails = [f for f in findings if f.level == "FAIL"]
        assert fails, "expected a FAIL for a member not present in properties or enum_members"
        assert "Bogus" in fails[0].message
        md.unlink()


class TestNestedTypeChainPropertyFallback:
    """MT074 (found live, 2026-10-08): a 3-segment nested-class-then-enum-constant chain
    (`Outer.Nested.CONSTANT`, e.g. Java's `ExcelSaveOptions.ExcelFormat.XLSX` — a real,
    compiled, run-verified example from pdf/java's own upstream docs) gets the SAME
    mis-tokenization as the PascalCase-enum case above, one level removed: the property
    regex matches `ExcelSaveOptions.ExcelFormat` as obj.prop (ExcelFormat is PascalCase,
    not ALL_CAPS, so the enum-access skip heuristic does not exclude it), and the
    verification branch then checks has_property/has_enum_member for member "ExcelFormat"
    on class "ExcelSaveOptions" — neither holds, because "ExcelFormat" is not a property
    OR an enum constant of ExcelSaveOptions, it is the SIMPLE NAME OF A SEPARATE, NESTED
    TYPE (our scout/extraction flattens Java's `ExcelSaveOptions$ExcelFormat` to a
    top-level `ExcelFormat` entry in api_surface.json, same as every other class).
    Generic fix, same shape as the existing enum-member fallback immediately above it:
    if the member name is itself a known class (a nested/sibling type reference, not a
    property), the chain is valid and must not FAIL."""

    def test_nested_type_name_as_member_produces_no_fail(self):
        md = _make_md(
            "```java\n"
            "ExcelSaveOptions options = new ExcelSaveOptions();\n"
            "options.setFormat(ExcelSaveOptions.ExcelFormat.XLSX);\n"
            "```\n"
        )
        tokens = extract_tokens(md, "java")
        knowledge = _FakeKnowledge(
            classes={"ExcelSaveOptions", "ExcelFormat"},
            properties={"ExcelSaveOptions": {"format"}},
            enum_members={"ExcelFormat": {"XLSX", "XmlSpreadSheet2003", "CSV", "ODS"}},
            methods={"ExcelSaveOptions": {"setFormat"}},
        )
        findings = verify_tokens(tokens, knowledge, md)
        assert not [f for f in findings if f.level == "FAIL"], findings

    def test_unknown_member_that_is_not_a_class_still_fails(self):
        """Negative control: a member absent from properties, enum_members AND classes
        must still FAIL — the fallback must only cover genuine nested-type references."""
        md = _make_md(
            "```java\n"
            "options.setFormat(ExcelSaveOptions.Bogus.XLSX);\n"
            "```\n"
        )
        tokens = extract_tokens(md, "java")
        knowledge = _FakeKnowledge(
            classes={"ExcelSaveOptions", "ExcelFormat"},
            properties={"ExcelSaveOptions": {"format"}},
            enum_members={"ExcelFormat": {"XLSX"}},
            methods={"ExcelSaveOptions": {"setFormat"}},
        )
        findings = verify_tokens(tokens, knowledge, md)
        fails = [f for f in findings if f.level == "FAIL"]
        assert fails, "expected a FAIL for a member that is not a property, enum member or class"
        assert "Bogus" in fails[0].message
