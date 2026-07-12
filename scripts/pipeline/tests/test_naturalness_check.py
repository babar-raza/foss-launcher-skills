"""Tests for naturalness_check.py (TC-10)."""
import pytest

from commands.ops.naturalness_check import (
    NaturalnessResult,
    check,
    _split_sentences,
    _avg_word_count,
    _strip_code_blocks,
)


class TestSplitSentences:
    def test_splits_on_period(self):
        result = _split_sentences("First sentence. Second sentence.")
        assert len(result) == 2

    def test_splits_on_question_mark(self):
        result = _split_sentences("Is it done? Yes it is.")
        assert len(result) == 2

    def test_empty_string(self):
        assert _split_sentences("") == []

    def test_single_sentence(self):
        result = _split_sentences("Only one sentence here.")
        assert len(result) == 1


class TestStripCodeBlocks:
    def test_removes_backtick_fences(self):
        text = "Before.\n```python\ncode here\n```\nAfter."
        result = _strip_code_blocks(text)
        assert "code here" not in result
        assert "Before." in result
        assert "After." in result

    def test_removes_tilde_fences(self):
        text = "Before.\n~~~\ncode\n~~~\nAfter."
        result = _strip_code_blocks(text)
        assert "code" not in result

    def test_no_code_blocks_unchanged(self):
        text = "Just prose here."
        assert _strip_code_blocks(text) == text


class TestAvgWordCount:
    def test_empty_returns_zero(self):
        assert _avg_word_count([]) == 0.0

    def test_single_sentence(self):
        assert _avg_word_count(["one two three"]) == 3.0

    def test_two_sentences(self):
        assert _avg_word_count(["one two", "three four five"]) == 2.5


class TestCheckInjectionMarkers:
    def test_detects_note_that(self):
        result = check("API reads data.", "Note that API reads data.")
        assert result.verdict == "WARNING"
        assert any("note that" in f.lower() for f in result.findings)

    def test_detects_additionally(self):
        result = check(
            "API reads data files.",
            "Additionally, this API reads data files.",
        )
        assert result.verdict == "WARNING"
        assert any("additionally" in f.lower() for f in result.findings)

    def test_detects_furthermore(self):
        result = check(
            "API reads data files.",
            "Furthermore, the API reads data files.",
        )
        assert result.verdict == "WARNING"

    def test_verdict_is_warning_not_fail(self):
        # Checker never emits FAIL
        result = check("Original.", "Note that this is injected.")
        assert result.verdict in {"PASS", "WARNING"}
        assert result.verdict != "FAIL"

    def test_case_insensitive(self):
        result = check("API reads data.", "NOTE THAT API reads data.")
        assert result.verdict == "WARNING"


class TestCheckSentenceDelta:
    def test_matching_sentence_count_passes(self):
        original = "The API reads files."
        generated = "The API reads files."
        result = check(original, generated)
        assert not any("SENTENCE_DELTA" in f for f in result.findings)

    def test_three_extra_sentences_warns(self):
        # Original: 1 sentence; generated: 4 sentences = delta 3 > threshold 2
        original = "One sentence."
        generated = "Sentence one. Sentence two. Sentence three. Sentence four."
        result = check(original, generated)
        assert result.verdict == "WARNING"
        assert any("SENTENCE_DELTA" in f for f in result.findings)

    def test_fewer_sentences_does_not_warn(self):
        original = "One. Two. Three. Four. Five."
        generated = "One. Two."
        result = check(original, generated)
        assert not any("SENTENCE_DELTA" in f for f in result.findings)


class TestCheckRegisterShift:
    def test_large_register_shift_warns(self):
        # Original: very short sentences (~2 words)
        original = "API reads. It writes. Done."
        # Generated: very long sentences (significant deviation)
        generated = (
            "The application programming interface provides comprehensive "
            "file reading capabilities across numerous supported output formats. "
            "The write operations are similarly feature-rich and support "
            "extensive configuration options through the various options classes."
        )
        result = check(original, generated)
        assert any("REGISTER_SHIFT" in f for f in result.findings)

    def test_identical_text_no_register_shift(self):
        text = "The API converts files. It saves documents."
        result = check(text, text)
        assert not any("REGISTER_SHIFT" in f for f in result.findings)


class TestNaturalnessResult:
    def test_pass_is_truthy(self):
        r = NaturalnessResult(verdict="PASS")
        assert bool(r) is True

    def test_warning_is_falsy(self):
        r = NaturalnessResult(verdict="WARNING", findings=["something"])
        assert bool(r) is False

    def test_empty_findings_on_pass(self):
        r = NaturalnessResult(verdict="PASS")
        assert r.findings == []


class TestCheckCodeBlocksIgnored:
    def test_injection_markers_in_code_blocks_ignored(self):
        # "Note that" inside a code block should not trigger injection warning
        generated = (
            "The API reads data.\n"
            "```python\n"
            "# Note that this is sample code\n"
            "api.read(path)\n"
            "```"
        )
        result = check("The API reads data.", generated)
        # Should not trigger injection marker on the code comment
        assert result.verdict == "PASS"
