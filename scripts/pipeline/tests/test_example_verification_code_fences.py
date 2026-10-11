"""Tests for lib/example_verification/code_fences.py (rollout step C1,
mission MT065-2026-09-06-EXAMPLE-VERIFICATION-CENTRALIZATION).

Covers the CommonMark fence cases named by the governing plan as the reason
a shared tokenizer is needed: tilde fences, a closing fence longer than the
opening, `c#`/`c++`/`objective-c` info strings the old `\\w*`-based regexes
could not match at all (RC6/RC19), an indented fence, an unterminated
fence, and 4-backtick nesting around a literal 3-backtick example.
"""
from __future__ import annotations

from lib.example_verification.code_fences import (
    CodeBlock,
    block_spans,
    canonicalize_lang,
    enumerate_code_blocks,
    normalize_content,
)


def _one(text: str) -> CodeBlock:
    blocks = enumerate_code_blocks(text)
    assert len(blocks) == 1, f"expected exactly one block, got {len(blocks)}: {blocks}"
    return blocks[0]


def test_basic_backtick_fence():
    text = "prose\n```python\nprint(1)\n```\nmore prose\n"
    block = _one(text)
    assert block.lang == "python"
    assert block.canonical_lang == "python"
    assert block.content == "print(1)"
    assert block.start_line == 2
    assert block.end_line == 4


def test_tilde_fence():
    text = "~~~python\nprint(1)\n~~~\n"
    block = _one(text)
    assert block.fence_char == "~"
    assert block.lang == "python"
    assert block.content == "print(1)"


def test_closing_fence_longer_than_opening():
    # CommonMark: closing run length must be >= opening; a longer close is valid.
    text = "```python\nprint(1)\n`````\n"
    block = _one(text)
    assert block.fence_len == 3
    assert block.content == "print(1)"
    assert block.end_line == 3


def test_four_backtick_nesting_around_literal_three_backticks():
    text = "````markdown\nHere is an example:\n```\nprint(1)\n```\n````\n"
    block = _one(text)
    assert block.fence_len == 4
    # The inner ``` run is shorter than the opening fence and must NOT close it.
    assert "```\nprint(1)\n```" in block.content
    assert block.end_line == 6


def test_csharp_info_string():
    text = "```c#\nConsole.WriteLine(1);\n```\n"
    block = _one(text)
    assert block.lang == "c#"
    assert block.canonical_lang == "csharp"


def test_cpp_info_string():
    text = "```c++\nstd::cout << 1;\n```\n"
    block = _one(text)
    assert block.lang == "c++"
    assert block.canonical_lang == "cpp"


def test_objective_c_info_string():
    text = "```objective-c\nNSLog(@\"hi\");\n```\n"
    block = _one(text)
    assert block.lang == "objective-c"
    # No canonical alias defined for objective-c -- passes through lowercased.
    assert block.canonical_lang == "objective-c"


def test_indented_fence_dedents_content():
    text = "- item\n  ```python\n  print(1)\n  print(2)\n  ```\n"
    block = _one(text)
    assert block.indent == 2
    assert block.content == "print(1)\nprint(2)"


def test_unterminated_fence_runs_to_eof():
    text = "prose\n```python\nprint(1)\nprint(2)\n"
    block = _one(text)
    assert block.content == "print(1)\nprint(2)"
    assert block.end_line == 4  # last line of the document


def test_backtick_fence_info_string_cannot_contain_backtick():
    # The ```has`backtick line is not a valid opening fence per CommonMark
    # (a backtick fence's info string may not itself contain a backtick), so
    # it must be skipped as plain text -- but the bare ``` two lines later is
    # itself a syntactically valid (if unterminated) opening fence and must
    # still be found.
    text = "```has`backtick\nnot a fence\n```\n"
    blocks = enumerate_code_blocks(text)
    assert len(blocks) == 1
    assert blocks[0].content == ""
    assert blocks[0].start_line == 3
    assert blocks[0].end_line == 3


def test_line_offset_shifts_reported_lines():
    text = "```python\nprint(1)\n```\n"
    block = _one_with_offset(text, 10)
    assert block.start_line == 11
    assert block.end_line == 13


def _one_with_offset(text: str, offset: int) -> CodeBlock:
    blocks = enumerate_code_blocks(text, line_offset=offset)
    assert len(blocks) == 1
    return blocks[0]


def test_multiple_blocks_get_sequential_index():
    text = "```python\na = 1\n```\n\n```python\nb = 2\n```\n"
    blocks = enumerate_code_blocks(text)
    assert [b.index for b in blocks] == [0, 1]
    assert blocks[0].content == "a = 1"
    assert blocks[1].content == "b = 2"


def test_block_spans_matches_enumerate_code_blocks():
    text = "```python\na = 1\n```\n\n```go\nb := 2\n```\n"
    blocks = enumerate_code_blocks(text)
    spans = block_spans(text)
    assert spans == [(b.start_line, b.end_line) for b in blocks]


def test_canonicalize_lang_aliases():
    assert canonicalize_lang("c#") == "csharp"
    assert canonicalize_lang("cs") == "csharp"
    assert canonicalize_lang("c++") == "cpp"
    assert canonicalize_lang("ts") == "typescript"
    assert canonicalize_lang("rs") == "rust"
    assert canonicalize_lang("golang") == "go"
    assert canonicalize_lang("python") == "python"
    assert canonicalize_lang("") == ""


def test_sha256_norm_ignores_line_endings_and_edge_blank_lines():
    a = normalize_content("\nprint(1)\r\nprint(2)\n\n")
    b = normalize_content("print(1)\nprint(2)")
    assert a == b


def test_sha256_norm_dedents_common_indentation():
    a = normalize_content("  print(1)\n  print(2)")
    b = normalize_content("print(1)\nprint(2)")
    assert a == b


def test_code_block_computes_hashes_when_not_supplied():
    block = CodeBlock(lang="python", content="print(1)", start_line=1, end_line=3)
    assert len(block.sha256_exact) == 64
    assert len(block.sha256_norm) == 64
    assert block.canonical_lang == "python"


def test_no_fences_returns_empty_list():
    assert enumerate_code_blocks("just prose\nno fences here\n") == []
