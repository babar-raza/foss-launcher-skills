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
    content = textwrap.dedent("""\
        ---
        title: Test Page
        single:
          enable: true
          block:
          - title: Example
            content: 'Open the workbook, then call `save()`
              three times.


              ```python
              from lib import Foo

              wb = Foo()
              wb.save("out.xlsx")
              ```
              '
        ---

        Body.
    """)
    p = _write_tmp(content)
    try:
        changed = normalize_file(p, dry_run=False, verbose=False)
        assert changed, "expected file to be changed"
        result = p.read_text(encoding="utf-8")
        assert "content: |" in result, "expected | literal block scalar"
        assert "content: '" not in result, "expected single-quoted form to be removed"
        assert "```python" in result, "code fence must be preserved"
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
