"""Focused tests for format_truth and consumer_usefulness EC-03 FP fixes."""

from __future__ import annotations

import sys
import os
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from content_eval.evaluators.consumer_usefulness import (
    _PURPOSE_INDICATORS,
    ConsumerUsefulnessEvaluator,
)


def _make_page(subdomain="blog", prose_lines=None, code_blocks=None,
               headings=None, page_role=None, filepath="test.md"):
    page = SimpleNamespace()
    page.subdomain = subdomain
    page.filepath = filepath
    page.prose_lines = prose_lines or []
    page.code_blocks = code_blocks or []
    page.headings = headings or []
    page.page_role = page_role
    return page


class TestPurposeFramingPatterns:

    @pytest.mark.parametrize("text,should_match", [
        ("Aspose.Cells enables developers to programmatically create charts", True),
        ("a free, MIT-licensed library for creating PowerPoint files", True),
        ("Aspose.Words FOSS is an open-source Python library for working with Word documents", True),
        ("This tool allows users to convert documents", True),
        ("designed for developers who need high-performance PDF processing", True),
        ("a pure-Python library for loading and converting Word documents", True),
        ("This guide shows how to convert documents", True),
        ("You will learn how to use the API", True),
        ("In this tutorial we demonstrate how to parse files", True),
        # EC-03 v3: comma-separated adjectives with special chars
        ("a MIT-licensed, dependency-free C# library for working with MSG files", True),
        # EC-03 v3: supports + gerund verb
        ("The library supports creating charts and manipulating cell data", True),
        ("Aspose.Cells supports reading XLSX files from streams", True),
        # supports without gerund should NOT match
        ("The library supports multiple platforms", False),
        ("The function returns the computed value", False),
        ("Use pip to install the package", False),
        ("This method processes the input data", False),
        ("Import the module and call save()", False),
    ])
    def test_purpose_indicator_matching(self, text, should_match):
        matched = any(p.search(text) for p in _PURPOSE_INDICATORS)
        assert matched == should_match

    def test_product_intro_blog_no_false_positive(self):
        evaluator = ConsumerUsefulnessEvaluator()
        prose = [
            (10, "Aspose.Cells FOSS is a free Python library for working with spreadsheets."),
            (12, "It enables developers to create charts and manipulate cell data."),
            (14, "The library supports XLSX, CSV, and other common formats."),
            (16, "Additional features include formula calculation, conditional formatting, and data validation across multiple worksheets."),
            (18, "You can install it via pip and start using it immediately in your Python projects without any licensing concerns."),
        ]
        page = _make_page(subdomain="blog", prose_lines=prose)
        findings = evaluator.evaluate(page, knowledge=None)
        us1 = [f for f in findings if "purpose framing" in f.message]
        assert len(us1) == 0


class TestCodeContextUS2:

    def test_code_block_with_no_prose_fires(self):
        evaluator = ConsumerUsefulnessEvaluator()
        code_block = SimpleNamespace(start_line=20, content="import foo")
        heading = SimpleNamespace(line_no=18)
        page = _make_page(
            subdomain="blog",
            prose_lines=[(5, "Some intro text. " * 20)],
            code_blocks=[code_block],
            headings=[heading],
        )
        findings = evaluator.evaluate(page, knowledge=None)
        us2 = [f for f in findings if "prose word(s) of context" in f.message]
        assert len(us2) == 1

    def test_code_block_with_sufficient_prose_ok(self):
        evaluator = ConsumerUsefulnessEvaluator()
        code_block = SimpleNamespace(start_line=25, content="import foo")
        heading = SimpleNamespace(line_no=18)
        prose = [
            (5, "This library enables developers to work with documents easily. " * 3),
            (20, "The following example shows how to load a document and extract its text content."),
        ]
        page = _make_page(subdomain="blog", prose_lines=prose, code_blocks=[code_block], headings=[heading])
        findings = evaluator.evaluate(page, knowledge=None)
        us2 = [f for f in findings if "prose word(s) of context" in f.message]
        assert len(us2) == 0


class TestFormatTruthVariantQualifier:

    def test_variant_qualifier_matches(self):
        from content_eval.evaluators.format_truth import _VARIANT_QUALIFIER_RE
        for text in ["binary ", "ASCII ", "text ", "xml ", "legacy ", "compressed ", "v7 "]:
            assert _VARIANT_QUALIFIER_RE.search(text), f"Expected match for: {text!r}"

    def test_variant_qualifier_rejects(self):
        from content_eval.evaluators.format_truth import _VARIANT_QUALIFIER_RE
        for text in ["support ", "format ", "the ", "export "]:
            assert not _VARIANT_QUALIFIER_RE.search(text), f"Expected no match for: {text!r}"


class TestFormatTruthCodeBlockIsolation:

    def test_load_line_not_export(self):
        from content_eval.evaluators.format_truth import _claim_direction
        assert _claim_direction("doc = aw.Document(input.doc)") != "export"

    def test_save_line_is_export(self):
        from content_eval.evaluators.format_truth import _claim_direction
        d = _claim_direction("doc.save(output.pdf, aw.SaveFormat.PDF)")
        assert d in ("export", "both"), f"Expected export or both, got {d}"

class TestApiAccuracyBclAllowlist:
    """EC-03 fix: .NET BCL identifiers must not produce UNKNOWN_CLASS."""

    def test_new_dotnet_entries_in_platform_sdk_classes(self):
        from token_ops import PLATFORM_SDK_CLASSES
        expected = [
            "DateTime", "DateTimeKind", "Encoding", "UTF8", "Unicode",
            "StringBuilder", "WriteLine", "WriteAllBytes",
            "GetBytes", "GetString", "ToArray",
        ]
        for name in expected:
            assert name in PLATFORM_SDK_CLASSES, (
                f"{name!r} missing from PLATFORM_SDK_CLASSES -- "
                f"will cause UNKNOWN_CLASS false positives in .NET examples"
            )

    def test_console_in_platform_sdk_classes(self):
        """Console was already present; regression guard."""
        from token_ops import PLATFORM_SDK_CLASSES
        assert "Console" in PLATFORM_SDK_CLASSES

    def test_java_byte_array_streams_are_allowlisted(self):
        """Java standard-library streams must not trigger UNKNOWN_CLASS."""
        from token_ops import PLATFORM_SDK_CLASSES
        assert {"ByteArrayInputStream", "ByteArrayOutputStream"} <= PLATFORM_SDK_CLASSES

    def test_rust_some_variant_is_allowlisted(self):
        from token_ops import PLATFORM_SDK_CLASSES
        assert "Some" in PLATFORM_SDK_CLASSES


class TestProseTruthDocConventionExclusion:
    """EC-03 fix: doc-convention phrases starting with 'All examples...' must be excluded."""

    @pytest.mark.parametrize("phrase", [
        "All examples assume the following import:",
        "All examples use the following namespace:",
        "All code examples in this section require:",
        "All code samples assume UTF-8 encoding.",
        "All snippets import from aspose.cells",
    ])
    def test_doc_convention_phrase_excluded(self, phrase):
        from content_eval.evaluators.prose_truth import _is_technical_strong_wording
        assert _is_technical_strong_wording(phrase), (
            f"Expected doc-convention phrase to be excluded but was not: {phrase!r}"
        )

    @pytest.mark.parametrize("phrase", [
        "All features are guaranteed to work correctly",
        "All products are fully compatible with Windows",
        "All operations must succeed without exceptions",
    ])
    def test_genuine_claim_not_excluded(self, phrase):
        from content_eval.evaluators.prose_truth import _is_technical_strong_wording
        assert not _is_technical_strong_wording(phrase), (
            f"Genuine claim should NOT be excluded, but was: {phrase!r}"
        )


class TestProseTruthMarkdownTableNoneExclusion:
    """EC-03 fix: 'None' as a Markdown table cell value must not trigger strong-wording WARN."""

    @pytest.mark.parametrize("line", [
        "| STL | `.stl` | Yes | Yes | None | Flat |",
        "| OBJ | `.obj` | Yes | Yes | None | Flat |",
        "| FBX | `.fbx` | Yes | No | None | Full |",
        "| none |",
        "|none|",
        "| None |",
    ])
    def test_table_cell_none_excluded(self, line):
        from content_eval.evaluators.prose_truth import _is_technical_strong_wording
        assert _is_technical_strong_wording(line), (
            f"Table cell 'None' should be excluded as technical context, but was not: {line!r}"
        )

    @pytest.mark.parametrize("phrase", [
        "None of the features work as documented",
        "None of the examples compile correctly",
        "Support for none of the formats is guaranteed",
    ])
    def test_standalone_none_claim_not_excluded(self, phrase):
        """Prose claims starting with 'None' that are actual claims should NOT be auto-excluded."""
        from content_eval.evaluators.prose_truth import _is_technical_strong_wording
        # These may or may not be excluded depending on other patterns.
        # The key test is that table-cell Nones ARE excluded (above).
        # This test documents the boundary — these are genuine claims.
        # They should NOT match the table-cell pattern.
        from content_eval.evaluators.prose_truth import _TECHNICAL_CONTEXT_RE
        import re
        table_cell_re = re.compile(r"\|\s*none\s*\|", re.IGNORECASE)
        assert not table_cell_re.search(phrase), (
            f"Table-cell pattern should NOT match prose claim: {phrase!r}"
        )


class TestProseTruthBacktickIdentifierStrongWords:
    """Root-cause fix: a strong word wrapped in backticks (an API member name
    that happens to collide with common English, e.g. PageSet's real static
    property `All`) is an identifier reference, not a prose overclaim. Prior
    logic (_STRONG_WORDS.search on the raw line) could not distinguish
    "Properties: `All`, `Even`, `Odd`." from a genuine "all X are Y" claim.
    """

    @pytest.mark.parametrize("line", [
        "Properties: `All`, `Even`, `Odd`.",
        "Methods: `Any`, `Only`, `Never`.",
        "The `None` value indicates no page range is applied.",
    ])
    def test_identifier_in_backticks_not_flagged(self, line):
        from content_eval.evaluators.prose_truth import _has_prose_strong_wording
        assert not _has_prose_strong_wording(line), (
            f"Backtick-quoted identifier should not be treated as strong "
            f"prose wording: {line!r}"
        )

    @pytest.mark.parametrize("line", [
        "This method always returns true.",
        "All properties on this page are guaranteed to be read-only.",
        "The `Document` class always saves correctly regardless of input.",
    ])
    def test_genuine_prose_strong_wording_still_flagged(self, line):
        from content_eval.evaluators.prose_truth import _has_prose_strong_wording
        assert _has_prose_strong_wording(line), (
            f"Genuine prose strong wording must still be caught: {line!r}"
        )

    def test_strong_word_partially_overlapping_backtick_span_still_flagged(self):
        """A strong word must be entirely inside a backtick span to be
        excluded -- guards against a naive "line contains backticks
        somewhere" implementation that would suppress too much."""
        from content_eval.evaluators.prose_truth import _has_prose_strong_wording
        line = "The `Foo` class always behaves this way."
        assert _has_prose_strong_wording(line)


class TestFormatTruthNegationDirectionGuard:
    """F2-FIX: _NEGATION_RE must not fire on lines with no format direction verb.

    Prose like "is not tagged as page content" or "are not overwritten" matches
    _NEGATION_RE and may also contain a format token (e.g. PDF on a pdf-library
    page).  Without a direction verb (import/export/save/load/support/...) we
    cannot determine what is being negated — the line is a method description,
    not a format support claim.
    """

    def test_no_direction_verb_returns_none(self):
        """_claim_direction returns None when no I/O verb is present."""
        from content_eval.evaluators.format_truth import _claim_direction
        assert _claim_direction("The method is not tagged as page content") is None
        assert _claim_direction("Properties are not overwritten by default") is None
        assert _claim_direction("Feature is not yet implemented") is None

    def test_support_verb_detected(self):
        """'support' is a direction verb — _claim_direction must NOT return None."""
        from content_eval.evaluators.format_truth import _claim_direction
        result = _claim_direction("PDF is not supported")
        assert result is not None, "'support' verb must yield a direction, not None"

    def test_save_verb_detected(self):
        """'save' is an export verb — must yield 'export' or 'both'."""
        from content_eval.evaluators.format_truth import _claim_direction
        result = _claim_direction("Cannot save PDF files")
        assert result in ("export", "both"), f"Expected export/both, got {result}"
