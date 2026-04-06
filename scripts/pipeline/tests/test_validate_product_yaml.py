"""Tests for validate_product_yaml.py."""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from validate_product_yaml import check_file

import tempfile


def _write_tmp(content: str) -> Path:
    f = tempfile.NamedTemporaryFile(
        suffix=".md", mode="w", encoding="utf-8", delete=False, dir=tempfile.gettempdir()
    )
    f.write(content)
    f.close()
    return Path(f.name)


# ---------------------------------------------------------------------------
# extract_frontmatter_body (shared helper — used post-A2b)
# ---------------------------------------------------------------------------

def test_extract_frontmatter_body_normal_file():
    from core.markdown import extract_frontmatter_body
    text = "---\ntitle: foo\n---\n\nBody."
    assert extract_frontmatter_body(text) == "title: foo"


def test_extract_frontmatter_body_returns_none_on_no_frontmatter():
    from core.markdown import extract_frontmatter_body
    assert extract_frontmatter_body("Just a body.\n") is None


# ---------------------------------------------------------------------------
# A2b preflight — strict vs tolerant regex behavior
# ---------------------------------------------------------------------------

def test_strict_regex_does_not_match_eof_without_trailing_newline():
    """The local strict pattern does NOT match a file where closing --- is at
    EOF with no trailing newline. This is the behavioral difference driving A2b.

    validate_product_yaml._extract_frontmatter() returns None for such files,
    causing check_file() to return ([], []) — a silent clean pass — even when
    the frontmatter actually has garbled content.
    """
    strict_re = re.compile(r"^(---\s*\n)(.*?)(\n---\s*\n)", re.DOTALL)
    text_no_trailing_newline = "---\ntitle: foo\n---"
    assert strict_re.match(text_no_trailing_newline) is None, (
        "strict pattern must NOT match file ending with --- at EOF"
    )


def test_tolerant_helper_matches_eof_without_trailing_newline():
    """The shared extract_frontmatter_body() DOES match a file ending at EOF.
    This is Case B evidence: tolerant variant catches what strict misses.
    """
    from core.markdown import extract_frontmatter_body
    text_no_trailing_newline = "---\ntitle: foo\n---"
    result = extract_frontmatter_body(text_no_trailing_newline)
    assert result is not None, (
        "extract_frontmatter_body() must match file ending with --- at EOF"
    )
    assert result.strip() == "title: foo"


def test_check_file_catches_garbled_eof_no_newline_after_a2b():
    """AFTER A2b migration: check_file catches a garbled file that ends with
    --- at EOF (no trailing newline). The pre-A2b silent miss is now fixed.

    extract_frontmatter_body() uses the tolerant (?:\\n|$) pattern from
    core.markdown, so this edge case is no longer silently passed.
    """
    # File with garbled code block AND no trailing newline after ---
    garbled_content = '---\ncontent: "```python foo"\n---'
    p = _write_tmp(garbled_content)
    try:
        errors, warnings = check_file(p)
        # Post-A2b: frontmatter IS detected, garbled code block IS flagged
        assert any("garbled" in e for e in errors), (
            "after A2b: garbled content in EOF-without-newline file must be caught"
        )
    finally:
        p.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# check_file — normal behavior
# ---------------------------------------------------------------------------

def test_check_file_detects_garbled_code_block():
    content = "---\ncontent: \"```python foo bar\"\n---\n\nBody."
    p = _write_tmp(content)
    try:
        errors, warnings = check_file(p)
        assert any("garbled" in e for e in errors)
    finally:
        p.unlink(missing_ok=True)


def test_check_file_warns_on_double_quoted_newline():
    content = '---\ncontent: "line one\\nline two"\n---\n\nBody.'
    p = _write_tmp(content)
    try:
        errors, warnings = check_file(p)
        assert errors == []
        assert any("double-quoted" in w for w in warnings)
    finally:
        p.unlink(missing_ok=True)


def test_check_file_clean_file_no_issues():
    content = "---\ntitle: Clean page\ncontent: |\n  Simple text.\n---\n\nBody."
    p = _write_tmp(content)
    try:
        errors, warnings = check_file(p)
        assert errors == []
        assert warnings == []
    finally:
        p.unlink(missing_ok=True)


def test_check_file_no_frontmatter_returns_empty():
    content = "Just a body with no frontmatter.\n"
    p = _write_tmp(content)
    try:
        errors, warnings = check_file(p)
        assert errors == [] and warnings == []
    finally:
        p.unlink(missing_ok=True)
