"""MT074 (found live, 2026-10-09): `_first_sentence`'s sentence-boundary regex
mistook punctuation INSIDE a Javadoc `{@tag ...}` code example for the sentence
terminator -- an ellipsis's periods (`{@code { ... }} block.` -> truncated to the
dangling `{@code { ...`) and a `?`/`!` inside the example (`{@code test ? cons :
alt}.` -> truncated to `{@code test ?`), affecting 4 of 28 initially-flagged
pdf/java reference pages (Block, ObjectLit, SwitchStmt, ConditionalExpr; the other
24 had complete-but-unconverted tags, a separate, milder issue not fixed here).
Every language that funnels through `_extract_doc_comment` shares this function:
Javadoc, JSDoc, XML doc, Godoc, Python docstrings, Rust doc comments.
"""
from __future__ import annotations

# sys.path is set by tests/conftest.py
from extraction.api_surface import _first_sentence, _mask_doc_tags
from extraction.lang.java import _first_sentence as _first_sentence_java_mirror


class TestMaskDocTags:
    def test_simple_tag_fully_masked(self):
        masked = _mask_doc_tags("{@code true}.")
        assert masked == "\0" * len("{@code true}") + "."

    def test_nested_braces_balanced_correctly(self):
        text = "{@code { ... }} block."
        masked = _mask_doc_tags(text)
        tag_len = len("{@code { ... }}")
        assert masked == "\0" * tag_len + " block."

    def test_unbalanced_tag_masks_to_end_of_string(self):
        # Malformed Javadoc with no closing brace -- must not loop forever or
        # raise; masks everything from the tag start to the end.
        text = "{@code never closes"
        assert _mask_doc_tags(text) == "\0" * len(text)

    def test_plain_text_without_any_tag_is_unchanged(self):
        assert _mask_doc_tags("No tags here at all.") == "No tags here at all."


class TestFirstSentenceJavadocTagPunctuation:
    def test_question_mark_inside_code_tag_not_a_sentence_break(self):
        # The real defect: upstream's `{@code test ? cons : alt}.` on
        # ConditionalExpr was truncated to the dangling `{@code test ?`.
        assert _first_sentence("{@code test ? cons : alt}.") == "{@code test ? cons : alt}."

    def test_exclamation_inside_code_tag_not_a_sentence_break(self):
        assert _first_sentence("{@code go!} marker.") == "{@code go!} marker."

    def test_nested_braces_inside_code_tag_not_a_sentence_break(self):
        # The real defect: upstream's `{@code { ... }} block.` on Block was
        # truncated to the dangling `{@code { ...`.
        assert _first_sentence("{@code { ... }} block.") == "{@code { ... }} block."

    def test_two_tags_then_a_real_terminator(self):
        assert _first_sentence("{@code true} / {@code false}.") == "{@code true} / {@code false}."

    def test_terminator_right_after_a_tag_with_no_trailing_text(self):
        assert _first_sentence("{@code switch (disc) { ... }}") == "{@code switch (disc) { ... }}"


class TestFirstSentenceEllipsis:
    def test_ellipsis_mid_comment_is_not_a_sentence_break(self):
        assert _first_sentence("{@code { ... }} block.") == "{@code { ... }} block."

    def test_ellipsis_at_end_of_sentence_still_needs_a_real_terminator(self):
        # No non-ellipsis terminator exists -- falls back to the first-line rule.
        assert _first_sentence("Trailing thought ...") == "Trailing thought ..."

    def test_two_sentences_with_an_ellipsis_in_the_first(self):
        text = "First part ... continues here. Second sentence follows."
        assert _first_sentence(text) == "First part ... continues here."

    def test_four_dots_still_excluded(self):
        # A run of 4 periods (e.g. a stylistic "....") must not be mistaken
        # for a terminator either -- every dot in the run is excluded, so the
        # scan continues past it to the next real terminator.
        text = "Some text.... Real sentence ends here."
        assert _first_sentence(text) == text

    def test_mirror_in_lang_java_module_matches(self):
        text = "{@code { ... }} block."
        assert _first_sentence_java_mirror(text) == _first_sentence(text) == text


class TestFirstSentenceUnchangedBehavior:
    """Negative controls: the ordinary, non-ellipsis case must be unaffected."""

    def test_plain_single_sentence(self):
        assert _first_sentence("Sets the source position; returns this for chaining.") == \
            "Sets the source position; returns this for chaining."

    def test_question_mark_terminator(self):
        assert _first_sentence("Is this valid? Yes it is.") == "Is this valid?"

    def test_exclamation_terminator(self):
        assert _first_sentence("Do not call this! It is unsafe.") == "Do not call this!"

    def test_no_terminator_falls_back_to_first_line(self):
        assert _first_sentence("no terminator here\nsecond line") == "no terminator here"

    def test_multiple_ordinary_sentences_returns_only_the_first(self):
        assert _first_sentence("First sentence. Second sentence.") == "First sentence."
