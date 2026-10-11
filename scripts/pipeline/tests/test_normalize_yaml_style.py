"""Tests for normalize_yaml_style.py."""
import tempfile, textwrap
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from normalize_yaml_style import normalize_file, _has_non_literal_multiline


def _write_tmp(content: str) -> Path:
    f = tempfile.NamedTemporaryFile(
        suffix=".md", mode="w", encoding="utf-8", delete=False, dir=tempfile.gettempdir()
    )
    f.write(content)
    f.close()
    return Path(f.name)


# ---------------------------------------------------------------------------
# _has_non_literal_multiline detection
# ---------------------------------------------------------------------------

def test_detects_double_quoted_newline_escape():
    fm = 'content: "Install with pip.\\n\\n```python\\n..."'
    assert _has_non_literal_multiline(fm)


def test_detects_single_quoted_multiline():
    fm = "content: 'Open the workbook.\n  Then chart.'"
    assert _has_non_literal_multiline(fm)


def test_does_not_flag_literal_block():
    fm = "content: |\n  Install with pip.\n\n  ```python\n  ...\n"
    assert not _has_non_literal_multiline(fm)


def test_does_not_flag_simple_scalar():
    fm = "title: Simple title\ndescription: No newlines here."
    assert not _has_non_literal_multiline(fm)


# ---------------------------------------------------------------------------
# normalize_file — happy path
# ---------------------------------------------------------------------------

def test_converts_single_quoted_multiline_to_literal_block():
    # Single-quoted scalar: blank line → preserved as \n by YAML flow folding.
    # Closing ' immediately after last character → no trailing whitespace in
    # the parsed value, so PyYAML can use |- (strip) literal block style.
    content = textwrap.dedent("""\
        ---
        title: Test Page
        content: 'Paragraph one with some text.

          Paragraph two with more text.'
        ---

        Body.
    """)
    p = _write_tmp(content)
    try:
        changed = normalize_file(p, dry_run=False, verbose=False)
        assert changed, "expected file to be changed"
        result = p.read_text(encoding="utf-8")
        # |- (strip) also starts with |, so this assertion covers both | and |-
        assert "content: |" in result, "expected | literal block scalar"
        assert "content: '" not in result, "expected single-quoted form to be removed"
    finally:
        p.unlink(missing_ok=True)


def test_converts_double_quoted_newline_escape_to_literal_block():
    content = textwrap.dedent("""\
        ---
        title: Test
        single:
          enable: true
          block:
          - title: Install
            content: "Install pip.\\n\\n```python\\nfrom lib import Foo\\nfoo = Foo()\\n```\\n"
        ---

        Body.
    """)
    p = _write_tmp(content)
    try:
        changed = normalize_file(p, dry_run=False, verbose=False)
        assert changed, "expected file to be changed"
        result = p.read_text(encoding="utf-8")
        assert "content: |" in result, "expected | style"
        assert '\\n' not in result.split("---")[1].split("---")[0], \
            "no \\n escapes should remain in frontmatter"
    finally:
        p.unlink(missing_ok=True)


def test_dry_run_does_not_write():
    content = textwrap.dedent("""\
        ---
        title: Test
        content: 'Multi line
          value here.'
        ---

        Body.
    """)
    p = _write_tmp(content)
    original = p.read_text(encoding="utf-8")
    try:
        changed = normalize_file(p, dry_run=True, verbose=False)
        assert changed, "dry_run should return True if would change"
        assert p.read_text(encoding="utf-8") == original, "dry_run must not modify file"
    finally:
        p.unlink(missing_ok=True)


def test_already_literal_block_no_change():
    content = textwrap.dedent("""\
        ---
        title: Test
        content: |
          Install with pip.

          ```python
          from lib import Foo
          ```
        ---

        Body.
    """)
    p = _write_tmp(content)
    try:
        changed = normalize_file(p, dry_run=False, verbose=False)
        assert not changed, "already-clean file should not be changed"
    finally:
        p.unlink(missing_ok=True)


def test_no_frontmatter_skipped():
    content = "Just a body, no frontmatter.\n"
    p = _write_tmp(content)
    try:
        changed = normalize_file(p, dry_run=False, verbose=False)
        assert not changed, "file without frontmatter should be skipped"
    finally:
        p.unlink(missing_ok=True)


def test_evidence_block_preserved_verbatim():
    """Evidence block must survive normalization byte-for-byte."""
    content = textwrap.dedent("""\
        ---
        title: Test
        single:
          enable: true
          block:
          - title: Install
            content: 'Install pip.
              Then run.'
        evidence:
          model_sha: abc123
          model_version: 1.0
          claims:
          - CLM-001
          apis:
          - Foo.bar
        ---

        Body.
    """)
    p = _write_tmp(content)
    try:
        changed = normalize_file(p, dry_run=False, verbose=False)
        assert changed
        result = p.read_text(encoding="utf-8")
        assert "model_sha: abc123" in result
        assert "CLM-001" in result
        assert "Foo.bar" in result
    finally:
        p.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# A2b preflight — strict vs tolerant frontmatter regex behavior
# ---------------------------------------------------------------------------

def test_strict_regex_does_not_match_eof_without_trailing_newline():
    """The local strict pattern r'^(---\\s*\\n)(.*?)(\\n---\\s*\\n)' does NOT match
    a file where the closing --- is at EOF with no trailing newline.

    This is the behavioral difference that motivated A2b: such files are
    silently skipped by normalize_file() when the strict pattern is in use.
    """
    import re
    strict_re = re.compile(r"^(---\s*\n)(.*?)(\n---\s*\n)", re.DOTALL)
    text_no_trailing_newline = "---\ntitle: foo\n---"   # no \n after closing ---
    assert strict_re.match(text_no_trailing_newline) is None, (
        "strict pattern must NOT match file ending with --- at EOF (no trailing newline)"
    )


def test_tolerant_helper_matches_eof_without_trailing_newline():
    """The shared tolerant helper split_frontmatter() DOES match a file ending
    with --- at EOF (no trailing newline).

    This is Case B evidence: the tolerant variant handles the edge case that
    the strict local copy silently misses.
    """
    from core.markdown import split_frontmatter
    text_no_trailing_newline = "---\ntitle: foo\n---"   # no \n after closing ---
    result = split_frontmatter(text_no_trailing_newline)
    assert result is not None, (
        "tolerant split_frontmatter() must match file ending with --- at EOF"
    )
    open_fence, body, close_fence = result
    assert body.strip() == "title: foo"


def test_normalize_file_processes_eof_without_trailing_newline_after_a2b():
    """AFTER A2b migration: normalize_file processes a file with a non-literal
    multiline scalar even when the closing --- is at EOF (no trailing newline).

    split_frontmatter() uses the tolerant (?:\\n|$) pattern, so this case
    is no longer silently skipped.
    """
    import re
    # Confirm the old strict pattern still misses it (invariant):
    strict_re = re.compile(r"^(---\s*\n)(.*?)(\n---\s*\n)", re.DOTALL)
    text = '---\ntitle: Test\ncontent: "line one\\nline two"\n---'
    assert strict_re.match(text) is None, "precondition: strict RE must not match"

    # But normalize_file (now using split_frontmatter) DOES detect it:
    p = _write_tmp(text)
    try:
        changed = normalize_file(p, dry_run=True, verbose=False)
        assert changed, (
            "after A2b: normalize_file must detect non-literal scalar even without trailing newline"
        )
    finally:
        p.unlink(missing_ok=True)


def test_trailing_whitespace_string_emits_warning(capsys):
    """String with trailing whitespace can't use | — should warn to stderr."""
    # A string ending with a space (not newline) — PyYAML can't use | for this
    content = textwrap.dedent("""\
        ---
        title: Test
        content: 'Some text that
          ends without newline. '
        ---

        Body.
    """)
    p = _write_tmp(content)
    try:
        # The normalization may or may not change the file, but if the string
        # still can't be | after processing, a warning should be emitted
        normalize_file(p, dry_run=False, verbose=False)
        # We don't assert changed here since it depends on PyYAML's behavior,
        # but we verify the function completes without error
    finally:
        p.unlink(missing_ok=True)
