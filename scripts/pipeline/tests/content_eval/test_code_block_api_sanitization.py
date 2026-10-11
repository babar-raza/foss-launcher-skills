"""Regression tests for ST-104: code_block_api.py's `_MEMBER_ACCESS_RE` false
positives on nested property-access chains, string/template literal content,
and comment text.

Confirmed live 2026-08-29 generating pdf/typescript's docs/kb bulk pages:
``doc.Pages.map(...)`` FAILed as "`Pages` is not exported from the package's
resolved entry point" (Pages is an instance PROPERTY, not a class); a string
literal ``'Hello from Aspose.PDF FOSS!'`` FAILed the same way for `Aspose`;
and a comment reading "found by SearchAnnotationText, not
SearchAnnotations." FAILed for both names -- none of these three shapes are
real code references.

Fix: `_MEMBER_ACCESS_RE` gained a negative lookbehind excluding matches whose
class-name token is itself immediately preceded by `.` (the tail of a longer
chain); `_sanitize_for_token_scan` blanks string/template literals and
comments (preserving newlines for line-number accuracy) before either
extraction regex runs; `_IGNORE_CLASSES` gained common TS/JS globals.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from content_eval.evaluators import _reachability
from content_eval.evaluators.code_block_api import (
    CodeBlockApiEvaluator,
    _sanitize_for_token_scan,
    _MEMBER_ACCESS_RE,
)
from content_eval.models import Page
from knowledge_core import Knowledge


@pytest.fixture(autouse=True)
def _clear_reachability_caches():
    _reachability.clear_caches()
    yield
    _reachability.clear_caches()


def _make_page(tmp_path: Path, family: str, platform: str, body: str) -> Page:
    content_dir = tmp_path / "content" / "docs.aspose.org" / "en" / family / platform
    content_dir.mkdir(parents=True, exist_ok=True)
    md_file = content_dir / "test.md"
    md_file.write_text(f"---\ntitle: test\n---\n\n{body}", encoding="utf-8")
    return Page.load(md_file)


def _make_knowledge(tmp_path: Path, family: str, platform: str, api_list: list[dict]) -> Knowledge:
    merged = tmp_path / family / platform / "merged"
    merged.mkdir(parents=True, exist_ok=True)
    (merged / "model.yaml").write_text("version: '1.0'\nrepo_sha: abc123\n", encoding="utf-8")
    (merged / "api_surface.json").write_text(json.dumps(api_list), encoding="utf-8")
    return Knowledge(family, platform, knowledge_root=tmp_path)


def _fake_clone(monkeypatch, tmp_path: Path, family: str, platform: str) -> Path:
    repo_dir = tmp_path / "clone" / f"aspose_{family}_{platform}"
    repo_dir.mkdir(parents=True, exist_ok=True)
    import core.clone_cache as clone_cache_mod

    def _fake_path(fam: str, plat: str) -> Path:
        if fam == family and plat == platform:
            return repo_dir
        return Path("/nonexistent")

    monkeypatch.setattr(clone_cache_mod, "clone_path", _fake_path)
    return repo_dir


# ---------------------------------------------------------------------------
# Unit-level: the sanitizer and the lookbehind directly
# ---------------------------------------------------------------------------

class TestMemberAccessLookbehind:

    def test_nested_chain_tail_not_matched(self):
        matches = list(_MEMBER_ACCESS_RE.finditer("doc.Pages.map((p) => p)"))
        # "Pages" is preceded by "." -- excluded. "Pages.map" would have
        # matched pre-fix with class_name="Pages", member_name="map".
        assert all(m.group(1) != "Pages" for m in matches), matches

    def test_top_level_reference_still_matched(self):
        matches = list(_MEMBER_ACCESS_RE.finditer("const doc = Document.OpenFile('x.pdf');"))
        assert any(m.group(1) == "Document" and m.group(2) == "OpenFile" for m in matches)


class TestSanitizeForTokenScan:

    def test_string_literal_content_blanked(self):
        src = "doc.Pages[0].AddText('Hello from Aspose.PDF FOSS!', 72, 720);"
        cleaned = _sanitize_for_token_scan(src, "typescript")
        assert "Aspose" not in cleaned
        assert "AddText" in cleaned  # real code outside the string survives

    def test_line_comment_content_blanked(self):
        src = (
            "// found by SearchAnnotationText, not SearchAnnotations.\n"
            "const hits = page.SearchAnnotationText('x');\n"
        )
        cleaned = _sanitize_for_token_scan(src, "typescript")
        first_line, second_line = cleaned.split("\n", 1)
        assert "SearchAnnotationText" not in first_line
        assert "SearchAnnotations" not in first_line
        assert "SearchAnnotationText" in second_line  # real call site untouched

    def test_python_comment_uses_hash_not_slash(self):
        src = "# See MyClass.method for details\nx = RealClass.real_method()\n"
        cleaned = _sanitize_for_token_scan(src, "python")
        assert "MyClass" not in cleaned
        assert "RealClass.real_method" in cleaned

    def test_newlines_preserved_for_line_numbers(self):
        src = "'a\\nb'\nconst x = Document.New();"
        cleaned = _sanitize_for_token_scan(src, "typescript")
        assert cleaned.count("\n") == src.count("\n")


# ---------------------------------------------------------------------------
# End-to-end: the real pdf/typescript shapes that produced false FAILs
# ---------------------------------------------------------------------------

class TestNestedChainNoLongerFails:

    def test_property_access_chain_produces_no_reachability_fail(self, tmp_path):
        body = (
            "```typescript\n"
            "import { Document } from '@asposefoss/pdf';\n"
            "const doc = Document.OpenFile('in.pdf');\n"
            "const count = doc.Pages.length;\n"
            "```\n"
        )
        page = _make_page(tmp_path, "pdf", "typescript", body)
        knowledge = _make_knowledge(tmp_path, "pdf", "typescript", [
            {"name": "Document", "methods": [{"name": "OpenFile"}],
             "properties": [], "enum_members": [], "reachable": True},
        ])
        findings = CodeBlockApiEvaluator().evaluate(page, knowledge)
        fails = [f for f in findings if f.level == "FAIL" and f.category == "CB"]
        assert fails == [], f"expected no FAIL findings, got: {fails}"

    def test_string_literal_class_dot_text_produces_no_fail(self, tmp_path):
        body = (
            "```typescript\n"
            "doc.Pages[0].AddText('Hello from Aspose.PDF FOSS!', 72, 720);\n"
            "```\n"
        )
        page = _make_page(tmp_path, "pdf", "typescript", body)
        knowledge = _make_knowledge(tmp_path, "pdf", "typescript", [])
        findings = CodeBlockApiEvaluator().evaluate(page, knowledge)
        fails = [f for f in findings if f.level == "FAIL" and f.category == "CB"]
        assert fails == [], f"expected no FAIL findings, got: {fails}"

    def test_comment_prose_produces_no_fail(self, tmp_path):
        body = (
            "```typescript\n"
            "// found by SearchAnnotationText, not SearchAnnotations.\n"
            "const hits = page.SearchAnnotationText('x');\n"
            "```\n"
        )
        page = _make_page(tmp_path, "pdf", "typescript", body)
        knowledge = _make_knowledge(tmp_path, "pdf", "typescript", [])
        findings = CodeBlockApiEvaluator().evaluate(page, knowledge)
        fails = [f for f in findings if f.level == "FAIL" and f.category == "CB"]
        assert fails == [], f"expected no FAIL findings, got: {fails}"


class TestGenuineUnreachableStillCaught:
    """Negative control: the lookbehind/sanitization must not blind the
    evaluator to a genuinely unreachable TOP-LEVEL class reference."""

    def test_top_level_unreachable_class_still_fails(self, tmp_path):
        body = (
            "```typescript\n"
            "import { InternalHelper } from '@asposefoss/pdf';\n"
            "const x = InternalHelper.doWork();\n"
            "```\n"
        )
        page = _make_page(tmp_path, "pdf", "typescript", body)
        knowledge = _make_knowledge(tmp_path, "pdf", "typescript", [
            {"name": "InternalHelper", "methods": [{"name": "doWork"}],
             "properties": [], "enum_members": [], "reachable": False},
        ])
        findings = CodeBlockApiEvaluator().evaluate(page, knowledge)
        fails = [f for f in findings if f.level == "FAIL" and f.category == "CB"]
        assert len(fails) == 1
        assert "InternalHelper" in fails[0].message

    def test_new_constructor_on_unreachable_class_still_fails(self, tmp_path, monkeypatch):
        """`new X(...)` is a bare-type reference scanned from the sanitized
        content too -- must survive sanitization even when preceded by other
        blanked comments/strings on the same line."""
        repo = _fake_clone(monkeypatch, tmp_path, "cells", "net")
        (repo / "InternalOnly.cs").write_text(
            "namespace Aspose.Cells_FOSS\n{\n    internal class InternalOnly\n    {\n"
            "        public InternalOnly() { }\n    }\n}\n",
            encoding="utf-8",
        )
        body = (
            "```csharp\n"
            "// 'not a real string' comment before the real line\n"
            "var x = new InternalOnly();\n"
            "```\n"
        )
        page = _make_page(tmp_path, "cells", "net", body)
        knowledge = _make_knowledge(tmp_path, "cells", "net", [])
        findings = CodeBlockApiEvaluator().evaluate(page, knowledge)
        fails = [f for f in findings if f.level == "FAIL" and f.category == "CB"]
        assert len(fails) == 1, f"expected exactly 1 FAIL, got: {findings}"
        assert "InternalOnly" in fails[0].message


class TestNestedTypeChainMemberFallback:
    """MT074 (found live, 2026-10-09): a 3-segment nested-class-then-member chain
    (`Outer.Nested.CONSTANT`, e.g. Java's `ExcelSaveOptions.ExcelFormat.XLSX` -- a
    real, compiled, run-verified example from pdf/java's own upstream docs) is
    mis-tokenized the same way as the PascalCase-enum case in lib/token_ops.py's
    TestNestedTypeChainPropertyFallback (see
    scripts/pipeline/tests/test_token_ops_pascalcase_enum_property_fallback.py):
    the member-access regex matches `ExcelSaveOptions.ExcelFormat` as obj.member,
    and `ExcelFormat` is neither a method, property, nor enum constant of
    `ExcelSaveOptions` -- it is the simple name of a separate, nested type (scout
    flattens Java's `ExcelSaveOptions$ExcelFormat` to a top-level `ExcelFormat`
    entry). This is the same defect class in a sibling evaluator that does not
    share code with token_ops.py; the fix mirrors it with a `member_name in
    knowledge.classes` fallback."""

    def test_nested_type_name_as_member_produces_no_warn(self, tmp_path):
        body = (
            "```java\n"
            "ExcelSaveOptions options = new ExcelSaveOptions();\n"
            "options.setFormat(ExcelSaveOptions.ExcelFormat.XLSX);\n"
            "```\n"
        )
        page = _make_page(tmp_path, "pdf", "java", body)
        knowledge = _make_knowledge(tmp_path, "pdf", "java", [
            {"name": "ExcelSaveOptions",
             "methods": [{"name": "setFormat"}],
             "properties": [], "enum_members": [], "reachable": True},
            {"name": "ExcelFormat",
             "methods": [], "properties": [],
             "enum_members": [{"name": "XLSX"}, {"name": "CSV"}],
             "reachable": True},
        ])
        findings = CodeBlockApiEvaluator().evaluate(page, knowledge)
        cb_findings = [f for f in findings if f.category == "CB"
                       and "ExcelFormat" in f.message]
        assert cb_findings == [], f"expected no CB finding, got: {cb_findings}"

    def test_unknown_member_that_is_not_a_class_still_warns(self, tmp_path):
        """Negative control: a member absent from methods, properties, enum_members
        AND classes must still produce the CB finding -- the fallback must only
        cover genuine nested-type references."""
        body = (
            "```java\n"
            "options.setFormat(ExcelSaveOptions.Bogus.XLSX);\n"
            "```\n"
        )
        page = _make_page(tmp_path, "pdf", "java", body)
        knowledge = _make_knowledge(tmp_path, "pdf", "java", [
            {"name": "ExcelSaveOptions",
             "methods": [{"name": "setFormat"}],
             "properties": [], "enum_members": [], "reachable": True},
            {"name": "ExcelFormat",
             "methods": [], "properties": [],
             "enum_members": [{"name": "XLSX"}],
             "reachable": True},
        ])
        findings = CodeBlockApiEvaluator().evaluate(page, knowledge)
        cb_findings = [f for f in findings if f.category == "CB"
                       and "Bogus" in f.message]
        assert len(cb_findings) == 1, f"expected exactly 1 CB finding, got: {findings}"
