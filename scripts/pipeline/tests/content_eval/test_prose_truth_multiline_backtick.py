"""Regression tests for prose_truth.py's multi-line backtick-span blindness.

Bug confirmed live 2026-08-29 running content_eval over pdf/typescript's
generated content (MT040): batch_reference.py emits reference-page property
tables whose `Type` column wraps a complex TypeScript union/object type
signature across several physical lines, e.g.

    | `listNumbering` | `:
        \\| 'None' \\| 'Disc' \\| 'Circle' \\| 'Square'
        \\| 'Decimal' \\| 'UpperRoman' \\| 'LowerRoman' \\| 'UpperAlpha' \\| 'LowerAlpha'` | Read | Gets the list numbering. |

and

    | `heading` | `: {
        /** Sizes for levels 1..6. Exactly six positive numbers.
         *  Default [24, 18, 14, 12, 10, 8] -- Flow's own heading scale. */
        sizes?: number[];
      }` | Read | Gets the heading. |

`_has_prose_strong_wording` already excludes strong words inside a
backtick-quoted span -- but only within the SAME line. A continuation line
of a wrapped table cell (the 'None'/'Disc'/... line, or the "Exactly six
positive numbers"/"Padding inside every cell" JSDoc-comment lines) carries
no backtick pair of its own, so it reads as bare, unbacked prose even
though it is verbatim, source-grounded type documentation still inside the
outer backtick span opened on an earlier line. Confirmed real: this FAILed
content_eval's canonical `prose_truth` evaluator (ceiling D on FAIL) on
reference.aspose.org/en/pdf/typescript/{ListAttributes,MarkdownStyle}.md.

Fix: `_lines_inside_multiline_backtick_span()` tracks backtick-count parity
across `page.prose_lines` in document order and marks every line inside an
still-open span; the format-claim/strong-wording loop skips those lines the
same way it already skips markdown table rows.
"""
from __future__ import annotations

import sys
import tempfile
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from content_eval.evaluators import prose_truth as _pt
from content_eval.models import Page


def _make_page(content: str, filepath: str) -> Page:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(content)
        f.flush()
        page = Page.load(Path(f.name))
        page.filepath = Path(filepath)
        page._infer_metadata()
        return page


@pytest.fixture
def evaluator():
    return _pt.ProseTruthEvaluator()


def _pt_fails(findings):
    return [f for f in findings if f.category == "PT" and f.level == "FAIL"]


class TestLinesInsideMultilineBacktickSpanUnit:
    """Unit tests for the parity-tracking helper in isolation."""

    def test_continuation_lines_of_wrapped_cell_are_marked(self):
        prose_lines = [
            (50, "| `listNumbering` | `:"),
            (51, "    \\| 'None' \\| 'Disc' \\| 'Circle' \\| 'Square'"),
            (52, "    \\| 'Decimal' \\| 'UpperRoman'` | Read | Gets the list numbering. |"),
            (53, "This is an ordinary sentence outside any span."),
        ]
        marked = _pt._lines_inside_multiline_backtick_span(prose_lines)
        assert 51 in marked
        assert 52 in marked
        assert 53 not in marked

    def test_single_line_complete_pairs_never_marked(self):
        prose_lines = [
            (1, "The `Document` class exposes `Pages`."),
            (2, "Another ordinary sentence."),
        ]
        marked = _pt._lines_inside_multiline_backtick_span(prose_lines)
        assert marked == set()

    def test_multiple_wrapped_cells_each_open_and_close_independently(self):
        prose_lines = [
            (1, "| `a` | `: {"),
            (2, "    inside first span"),
            (3, "  }` | Read | first. |"),
            (4, "| `b` | `: {"),
            (5, "    inside second span"),
            (6, "  }` | Read | second. |"),
            (7, "outside both"),
        ]
        marked = _pt._lines_inside_multiline_backtick_span(prose_lines)
        assert marked == {2, 3, 5, 6}


class TestMultilineBacktickSpanIntegration:
    """Full evaluate() tests: real Page, real reference-page shape."""

    def test_list_attributes_style_union_continuation_no_fail(self, evaluator, tmp_path):
        """The exact reproducing shape from ListAttributes.md: a `'None'`
        union member on a continuation line must not FAIL as unbacked
        strong wording."""
        page = _make_page(textwrap.dedent("""\
            ---
            title: ListAttributes
            ---
            ## Properties

            | Name | Type | Access | Description |
            |------|------|--------|-------------|
            | `listNumbering` | `:
                \\| 'None' \\| 'Disc' \\| 'Circle' \\| 'Square'
                \\| 'Decimal' \\| 'UpperRoman' \\| 'LowerRoman' \\| 'UpperAlpha' \\| 'LowerAlpha'` | Read | Gets the list numbering. |
        """), "content/reference.aspose.org/en/pdf/typescript/ListAttributes.md")
        findings = evaluator.evaluate(page, None)
        assert _pt_fails(findings) == [], (
            f"false-positive strong-wording FAIL must not fire; got: {[f.message for f in findings]}"
        )

    def test_markdown_style_wrapped_jsdoc_no_fail(self, evaluator, tmp_path):
        """The exact reproducing shape from MarkdownStyle.md: a wrapped
        JSDoc comment reading "Exactly six positive numbers" on a
        continuation line must not FAIL."""
        page = _make_page(textwrap.dedent("""\
            ---
            title: MarkdownStyle
            ---
            ## Properties

            | Name | Type | Access | Description |
            |------|------|--------|-------------|
            | `heading` | `: {
                /** Sizes for levels 1..6. Exactly six positive numbers.
                 *  Default [24, 18, 14, 12, 10, 8] -- Flow's own heading scale. */
                sizes?: number[];
              }` | Read | Gets the heading. |
        """), "content/reference.aspose.org/en/pdf/typescript/MarkdownStyle.md")
        findings = evaluator.evaluate(page, None)
        assert _pt_fails(findings) == [], (
            f"false-positive strong-wording FAIL must not fire; got: {[f.message for f in findings]}"
        )

    def test_padding_every_cell_wrapped_comment_no_fail(self, evaluator, tmp_path):
        """The third reproducing shape: "Padding inside every cell" inside
        a wrapped JSDoc comment must not FAIL."""
        page = _make_page(textwrap.dedent("""\
            ---
            title: MarkdownStyle
            ---
            ## Properties

            | Name | Type | Access | Description |
            |------|------|--------|-------------|
            | `table` | `: {
                /** Padding inside every cell. >= 0. Default 4. */
                padding?: number;
              }` | Read | Gets the table style. |
        """), "content/reference.aspose.org/en/pdf/typescript/MarkdownStyle.md")
        findings = evaluator.evaluate(page, None)
        assert _pt_fails(findings) == [], (
            f"false-positive strong-wording FAIL must not fire; got: {[f.message for f in findings]}"
        )

    def test_genuine_unbacked_strong_wording_outside_span_still_fails(self, evaluator, tmp_path):
        """Negative control: real bare prose with strong wording, entirely
        outside any backtick span, on a reference page (FAIL severity),
        must still be flagged -- the fix must not blind the check
        entirely."""
        page = _make_page(textwrap.dedent("""\
            ---
            title: SomeClass
            ---
            ## Overview

            This method always works perfectly and never fails under any
            circumstance whatsoever across every possible input.
        """), "content/reference.aspose.org/en/pdf/typescript/SomeClass.md")
        findings = evaluator.evaluate(page, None)
        assert len(_pt_fails(findings)) >= 1, (
            "genuine unbacked strong wording outside any span must still FAIL"
        )
