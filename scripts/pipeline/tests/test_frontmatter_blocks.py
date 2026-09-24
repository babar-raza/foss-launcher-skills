"""Tests for lib/example_verification/frontmatter_blocks.py (TC-18,
MT072-2026-09-23-EXAMPLE-VERIFICATION-PRODUCTIONIZATION).
"""
from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
_LIB_DIR = str(_HERE / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from example_verification.frontmatter_blocks import (  # noqa: E402
    _strip_frontmatter_delimiters,
    _walk_strings,
    extract_frontmatter_embedded_blocks,
)


def test_strip_frontmatter_delimiters_whole_file_is_frontmatter():
    text = "---\ntitle: x\ndescription: y\n---\n"
    assert _strip_frontmatter_delimiters(text) == "\ntitle: x\ndescription: y"


def test_strip_frontmatter_delimiters_no_leading_marker_returns_unchanged():
    text = "title: x\n"
    assert _strip_frontmatter_delimiters(text) == text


def test_walk_strings_scalar():
    assert _walk_strings("hello") == ["hello"]


def test_walk_strings_nested_dict_and_list():
    node = {"a": "x", "b": [{"c": "y"}, "z"], "d": {"e": {"f": "w"}}}
    assert sorted(_walk_strings(node)) == ["w", "x", "y", "z"]


def test_walk_strings_ignores_non_string_scalars():
    node = {"a": 1, "b": True, "c": None, "d": "keep"}
    assert _walk_strings(node) == ["keep"]


def test_extract_no_code_returns_empty():
    text = "---\ntitle: x\noverview:\n  content: Just prose, no fences here.\n---\n"
    assert extract_frontmatter_embedded_blocks(text) == []


def test_extract_real_embedded_example():
    text = (
        "---\ntitle: x\nsingle:\n  block:\n  - title: Example\n    content: |\n"
        "      ```go\n      package main\n      func main() {}\n      ```\n"
        "---\n"
    )
    blocks = extract_frontmatter_embedded_blocks(text)
    assert len(blocks) == 1
    assert blocks[0].canonical_lang == "go"
    assert "package main" in blocks[0].content


def test_extract_multiple_examples_across_fields():
    text = (
        "---\ntitle: x\nsingle:\n  block:\n"
        "  - title: One\n    content: |\n      ```python\n      print(1)\n      ```\n"
        "  - title: Two\n    content: |\n      ```python\n      print(2)\n      ```\n"
        "---\n"
    )
    blocks = extract_frontmatter_embedded_blocks(text)
    assert len(blocks) == 2
    assert [b.content.strip() for b in blocks] == ["print(1)", "print(2)"]


def test_extract_malformed_yaml_returns_empty_not_raises():
    text = "---\ntitle: [unterminated\n---\n"
    assert extract_frontmatter_embedded_blocks(text) == []


def test_extract_no_frontmatter_at_all_returns_empty():
    assert extract_frontmatter_embedded_blocks("just plain text\n") == []
