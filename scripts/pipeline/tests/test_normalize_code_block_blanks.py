"""Tests for normalize_code_block_blanks.py.

conftest.py adds commands/content/ to sys.path, so bare imports work.
"""
import sys
from pathlib import Path

# conftest.py sys.path setup makes these importable without dotted paths
from normalize_code_block_blanks import (
    _compress_2plus_blanks,
    _fix_dq_value,
    _normalize_block_literal,
    _normalize_block_single_quoted,
    _normalize_dq_block,
    _normalize_fm_lines,
    _remove_all_blanks,
    _remove_boundary_blanks,
    _remove_boundary_blanks_sq,
    normalize_file,
)

_LNL = "\\n"  # literal 2-char backslash-n sequence used in double-quoted YAML


def _make_md(tmp_path: Path, content: str, name: str = "_index.md") -> Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# _remove_boundary_blanks — strips ALL leading/trailing blanks
# ---------------------------------------------------------------------------

def test_remove_boundary_blanks_strips_leading():
    assert _remove_boundary_blanks(["", "x = 1"]) == ["x = 1"]


def test_remove_boundary_blanks_strips_trailing():
    assert _remove_boundary_blanks(["x = 1", ""]) == ["x = 1"]


def test_remove_boundary_blanks_strips_both():
    assert _remove_boundary_blanks(["", "x = 1", ""]) == ["x = 1"]


def test_remove_boundary_blanks_preserves_internal_blank():
    assert _remove_boundary_blanks(["x = 1", "", "y = 2"]) == ["x = 1", "", "y = 2"]


def test_remove_boundary_blanks_all_blank_returns_empty():
    assert _remove_boundary_blanks(["", "", ""]) == []


def test_remove_boundary_blanks_no_change_when_clean():
    items = ["x = 1", "y = 2"]
    assert _remove_boundary_blanks(items) == ["x = 1", "y = 2"]


# ---------------------------------------------------------------------------
# _remove_boundary_blanks_sq — strips only 2+-blank RUNS at boundaries
# (single blank at boundary is harmless in single-quoted YAML)
# ---------------------------------------------------------------------------

def test_sq_boundary_single_blank_at_start_preserved():
    assert _remove_boundary_blanks_sq(["", "x = 1"]) == ["", "x = 1"]


def test_sq_boundary_single_blank_at_end_preserved():
    assert _remove_boundary_blanks_sq(["x = 1", ""]) == ["x = 1", ""]


def test_sq_boundary_double_blank_at_start_removed():
    assert _remove_boundary_blanks_sq(["", "", "x = 1"]) == ["x = 1"]


def test_sq_boundary_double_blank_at_end_removed():
    assert _remove_boundary_blanks_sq(["x = 1", "", ""]) == ["x = 1"]


def test_sq_boundary_triple_blank_run_removed():
    assert _remove_boundary_blanks_sq(["", "", "", "x = 1"]) == ["x = 1"]


def test_sq_boundary_internal_blanks_not_touched():
    assert _remove_boundary_blanks_sq(["a", "", "", "b"]) == ["a", "", "", "b"]


# ---------------------------------------------------------------------------
# _compress_2plus_blanks — compress runs of 2+ blank lines to 0; keep single
# ---------------------------------------------------------------------------

def test_compress_single_blank_preserved():
    assert _compress_2plus_blanks(["a", "", "b"]) == ["a", "", "b"]


def test_compress_double_blank_removed():
    assert _compress_2plus_blanks(["a", "", "", "b"]) == ["a", "b"]


def test_compress_triple_blank_removed():
    assert _compress_2plus_blanks(["a", "", "", "", "b"]) == ["a", "b"]


def test_compress_mixed_blanks():
    inp = ["a", "", "b", "", "", "c"]
    assert _compress_2plus_blanks(inp) == ["a", "", "b", "c"]


def test_compress_no_blanks_unchanged():
    assert _compress_2plus_blanks(["a", "b", "c"]) == ["a", "b", "c"]


# ---------------------------------------------------------------------------
# _remove_all_blanks
# ---------------------------------------------------------------------------

def test_remove_all_blanks_removes_every_blank():
    assert _remove_all_blanks(["", "x", "", "", "y", ""]) == ["x", "y"]


def test_remove_all_blanks_no_blanks_unchanged():
    assert _remove_all_blanks(["a", "b"]) == ["a", "b"]


def test_remove_all_blanks_all_blank_empty():
    assert _remove_all_blanks(["", ""]) == []


# ---------------------------------------------------------------------------
# _normalize_block_literal — literal | blocks
# ---------------------------------------------------------------------------

def test_literal_short_removes_all_internal_blanks():
    block = ["x = 1", "", "y = 2"]
    assert _normalize_block_literal(block, is_short=True) == ["x = 1", "y = 2"]


def test_literal_short_removes_boundary_blanks():
    block = ["", "x = 1", ""]
    assert _normalize_block_literal(block, is_short=True) == ["x = 1"]


def test_literal_short_blank_after_open_fence_removed():
    block = ["", "x = 1"]
    assert _normalize_block_literal(block, is_short=True) == ["x = 1"]


def test_literal_short_blank_before_close_fence_removed():
    block = ["x = 1", ""]
    assert _normalize_block_literal(block, is_short=True) == ["x = 1"]


def test_literal_long_preserves_internal_blank():
    # Long snippet (>8 non-empty lines): internal blank preserved; only boundary removed
    block = ["a", "b", "c", "d", "e", "f", "g", "h", "i", "", "j"]
    result = _normalize_block_literal(block, is_short=False)
    assert "" in result
    assert result[0] == "a"
    assert result[-1] == "j"


def test_literal_long_removes_only_boundary_blanks():
    block = ["", "a", "b", "c", "d", "e", "f", "g", "h", "", "i", ""]
    result = _normalize_block_literal(block, is_short=False)
    assert result[0] == "a"
    assert result[-1] == "i"
    # internal blank after 'h' preserved
    idx_h = result.index("h")
    assert result[idx_h + 1] == ""


# ---------------------------------------------------------------------------
# _normalize_block_single_quoted
# ---------------------------------------------------------------------------

def test_sq_short_compresses_double_blank_to_zero():
    block = ["x = 1", "", "", "y = 2"]
    assert _normalize_block_single_quoted(block, is_short=True) == ["x = 1", "y = 2"]


def test_sq_short_preserves_single_blank():
    # Single blank in SQ YAML = harmless (\n separator)
    block = ["x = 1", "", "y = 2"]
    assert _normalize_block_single_quoted(block, is_short=True) == ["x = 1", "", "y = 2"]


def test_sq_short_removes_double_boundary_blank():
    # Leading 2-blank run removed by _remove_boundary_blanks_sq;
    # trailing 2-blank run not at boundary (non-blank follows), compressed by _compress_2plus_blanks
    block = ["", "", "x = 1", "", "", "y = 2"]
    result = _normalize_block_single_quoted(block, is_short=True)
    assert result == ["x = 1", "y = 2"]


def test_sq_long_preserves_double_blank():
    # Long snippet: 2+ blank runs are NOT compressed
    block = ["a", "b", "c", "d", "e", "f", "g", "h", "i", "", "", "j"]
    result = _normalize_block_single_quoted(block, is_short=False)
    idx_i = result.index("i")
    idx_j = result.index("j")
    assert idx_j - idx_i == 3  # i, "", "", j — double blank preserved


# ---------------------------------------------------------------------------
# _normalize_dq_block — double-quoted virtual lines
# ---------------------------------------------------------------------------

def test_dq_short_removes_boundary_blank():
    vparts = ["", "x = 1", ""]
    assert _normalize_dq_block(vparts, is_short=True) == ["x = 1"]


def test_dq_short_removes_all_internal_blanks():
    vparts = ["x = 1", "", "y = 2"]
    assert _normalize_dq_block(vparts, is_short=True) == ["x = 1", "y = 2"]


def test_dq_long_removes_boundary_blank_only():
    vparts = ["", "a", "b", "c", "d", "e", "f", "g", "h", "i", ""]
    result = _normalize_dq_block(vparts, is_short=False)
    assert result[0] == "a"
    assert result[-1] == "i"


def test_dq_long_preserves_internal_blank():
    vparts = ["a", "b", "c", "d", "e", "f", "g", "h", "", "i"]
    result = _normalize_dq_block(vparts, is_short=False)
    assert "" in result


# ---------------------------------------------------------------------------
# _fix_dq_value — double-quoted single-line with \n-encoded newlines
# ---------------------------------------------------------------------------

def test_fix_dq_removes_blank_after_open_fence():
    # "intro\n```python\n\nx = 1\n```\noutro" — blank after ```python
    raw = 'content: "intro' + _LNL + '```python' + _LNL + _LNL + 'x = 1' + _LNL + '```' + _LNL + 'outro"'
    expected = 'content: "intro' + _LNL + '```python' + _LNL + 'x = 1' + _LNL + '```' + _LNL + 'outro"'
    assert _fix_dq_value(raw) == expected


def test_fix_dq_removes_blank_before_close_fence():
    raw = 'content: "intro' + _LNL + '```python' + _LNL + 'x = 1' + _LNL + _LNL + '```' + _LNL + 'outro"'
    expected = 'content: "intro' + _LNL + '```python' + _LNL + 'x = 1' + _LNL + '```' + _LNL + 'outro"'
    assert _fix_dq_value(raw) == expected


def test_fix_dq_no_code_fence_unchanged():
    raw = 'content: "some text' + _LNL + 'no fence here"'
    assert _fix_dq_value(raw) == raw


def test_fix_dq_no_lnl_sequence_unchanged():
    # Has ``` but no \n sequence — unchanged
    raw = 'content: "```python code```"'
    assert _fix_dq_value(raw) == raw


def test_fix_dq_preserves_surrounding_content():
    raw = 'content: "intro' + _LNL + '```python' + _LNL + 'x = 1' + _LNL + '```' + _LNL + 'outro"'
    result = _fix_dq_value(raw)
    assert 'intro' in result
    assert 'outro' in result


def test_fix_dq_unclosed_fence_does_not_crash():
    # No closing ``` — should not crash; content preserved
    raw = 'content: "intro' + _LNL + '```python' + _LNL + 'x = 1"'
    result = _fix_dq_value(raw)
    assert '```python' in result


# ---------------------------------------------------------------------------
# _normalize_fm_lines — full frontmatter processing
# ---------------------------------------------------------------------------

def test_fm_literal_blank_after_open_fence_removed():
    fm = "\ncontent: |\n  ```python\n  \n  x = 1\n  ```\n"
    result = _normalize_fm_lines(fm)
    lines = result.split("\n")
    idx_open = next(i for i, l in enumerate(lines) if "```python" in l)
    assert lines[idx_open + 1].strip() != ""


def test_fm_literal_blank_before_close_fence_removed():
    fm = "\ncontent: |\n  ```python\n  x = 1\n  \n  ```\n"
    result = _normalize_fm_lines(fm)
    lines = result.split("\n")
    idx_close = next(i for i, l in enumerate(lines) if l.strip() == "```")
    assert lines[idx_close - 1].strip() != ""


def test_fm_non_code_content_unchanged():
    fm = "\ntitle: Hello World\ndescription: Some description\n"
    assert _normalize_fm_lines(fm) == fm


def test_fm_no_code_fence_unchanged():
    fm = "\ntitle: test\n  Some indented content\n"
    assert _normalize_fm_lines(fm) == fm


def test_fm_literal_short_removes_internal_blank():
    fm = "\ncontent: |\n  ```python\n  a = 1\n  \n  b = 2\n  ```\n"
    result = _normalize_fm_lines(fm)
    lines = result.split("\n")
    idx_open = next(i for i, l in enumerate(lines) if "```python" in l)
    idx_close = next(i for i, l in enumerate(lines) if l.strip() == "```")
    inner = lines[idx_open + 1: idx_close]
    assert all(l.strip() != "" for l in inner)


def test_fm_long_snippet_preserves_internal_blank():
    # >8 non-empty lines — internal blank preserved
    inner_lines = [f"  line_{i} = {i}" for i in range(9)]
    inner_with_blank = inner_lines[:4] + ["  "] + inner_lines[4:]
    code_block = "  ```python\n" + "\n".join(inner_with_blank) + "\n  ```"
    fm = "\ncontent: |\n" + code_block + "\n"
    result = _normalize_fm_lines(fm)
    lines = result.split("\n")
    idx_open = next(i for i, l in enumerate(lines) if "```python" in l)
    idx_close = next(i for i, l in enumerate(lines) if l.strip() == "```")
    inner = lines[idx_open + 1: idx_close]
    assert any(l.strip() == "" for l in inner), "internal blank must be preserved for long snippet"


# ---------------------------------------------------------------------------
# normalize_file — top-level API
# ---------------------------------------------------------------------------

def test_normalize_file_no_change_when_clean(tmp_path):
    content = "---\ncontent: |\n  ```python\n  x = 1\n  ```\n---\nbody\n"
    p = _make_md(tmp_path, content)
    changed, old_len, new_len = normalize_file(p)
    assert not changed
    assert old_len == new_len


def test_normalize_file_detects_and_removes_blank_after_open_fence(tmp_path):
    content = "---\ncontent: |\n  ```python\n  \n  x = 1\n  ```\n---\nbody\n"
    p = _make_md(tmp_path, content)
    changed, old_len, new_len = normalize_file(p)
    assert changed
    assert new_len < old_len
    fixed = p.read_text(encoding="utf-8")
    assert "  ```python\n  \n" not in fixed


def test_normalize_file_dry_run_reports_change_but_does_not_write(tmp_path):
    content = "---\ncontent: |\n  ```python\n  \n  x = 1\n  ```\n---\nbody\n"
    p = _make_md(tmp_path, content)
    original = p.read_text(encoding="utf-8")
    changed, _, _ = normalize_file(p, dry_run=True)
    assert changed                                          # would change
    assert p.read_text(encoding="utf-8") == original       # file untouched


def test_normalize_file_no_frontmatter_skipped(tmp_path):
    content = "No frontmatter here\n```python\nx = 1\n```\n"
    p = _make_md(tmp_path, content)
    changed, old_len, new_len = normalize_file(p)
    assert not changed
    assert old_len == 0
    assert new_len == 0


def test_normalize_file_incomplete_frontmatter_skipped(tmp_path):
    # Only one --- separator — not a valid frontmatter block
    content = "---\ntitle: test\n"
    p = _make_md(tmp_path, content)
    changed, old_len, new_len = normalize_file(p)
    assert not changed


def test_normalize_file_writes_correct_content(tmp_path):
    content = "---\ncontent: |\n  ```python\n  \n  x = 1\n  ```\n---\nbody here\n"
    p = _make_md(tmp_path, content)
    normalize_file(p, dry_run=False)
    result = p.read_text(encoding="utf-8")
    assert result.startswith("---\n")
    assert "---\nbody here\n" in result
    assert "  ```python\n  \n" not in result


def test_normalize_file_multiple_code_blocks(tmp_path):
    content = (
        "---\n"
        "content: |\n"
        "  ```python\n"
        "  \n"
        "  x = 1\n"
        "  ```\n"
        "  Some text\n"
        "  ```csharp\n"
        "  \n"
        "  var x = 1;\n"
        "  ```\n"
        "---\nbody\n"
    )
    p = _make_md(tmp_path, content)
    changed, _, _ = normalize_file(p)
    assert changed
    fixed = p.read_text(encoding="utf-8")
    assert "  ```python\n  \n" not in fixed
    assert "  ```csharp\n  \n" not in fixed


def test_normalize_file_en_path_not_skipped_by_normalize_file(tmp_path):
    # normalize_file() itself does NOT skip /en/ paths.
    # The /en/ guard was removed from main() in GAP-CSSP-R01 fix.
    en_dir = tmp_path / "en" / "words"
    en_dir.mkdir(parents=True)
    p = en_dir / "_index.md"
    content = "---\ncontent: |\n  ```python\n  \n  x = 1\n  ```\n---\nbody\n"
    p.write_text(content, encoding="utf-8")
    changed, old_len, new_len = normalize_file(p)
    assert changed  # normalize_file processes EN paths; blank after open fence is a defect


def test_main_processes_en_locale_pages(tmp_path):
    """main() must process EN-locale pages (GAP-CSSP-R01: /en/ exclusion removed)."""
    import normalize_code_block_blanks as m
    products = tmp_path / "products.aspose.org"
    en_dir = products / "en" / "words" / "python"
    en_dir.mkdir(parents=True)
    p = en_dir / "_index.md"
    content = "---\ncontent: |\n  ```python\n  \n  x = 1\n  ```\n---\n"
    p.write_text(content, encoding="utf-8")
    orig_repo, orig_default = m.REPO, m.DEFAULT_PRODUCTS
    m.REPO = tmp_path
    m.DEFAULT_PRODUCTS = products
    try:
        exit_code = m.main()
    finally:
        m.REPO, m.DEFAULT_PRODUCTS = orig_repo, orig_default
    assert exit_code == 0
    assert "  ```python\n  \n" not in p.read_text(encoding="utf-8")


def test_main_idempotent_on_already_clean_pages(tmp_path):
    """Running main() twice produces no additional changes (idempotency)."""
    import normalize_code_block_blanks as m
    products = tmp_path / "products.aspose.org"
    locale_dir = products / "ar" / "words" / "python"
    locale_dir.mkdir(parents=True)
    p = locale_dir / "_index.md"
    content = "---\ncontent: |\n  ```python\n  \n  x = 1\n  ```\n---\n"
    p.write_text(content, encoding="utf-8")
    orig_repo, orig_default = m.REPO, m.DEFAULT_PRODUCTS
    m.REPO = tmp_path
    m.DEFAULT_PRODUCTS = products
    try:
        m.main()
        snapshot = p.read_text(encoding="utf-8")
        m.main()
        assert p.read_text(encoding="utf-8") == snapshot
    finally:
        m.REPO, m.DEFAULT_PRODUCTS = orig_repo, orig_default


# ---------------------------------------------------------------------------
# Multi-line double-quoted YAML with YAML folding — known limitation (GAP-CSSP-R09)
# ---------------------------------------------------------------------------

def test_fix_dq_value_does_not_handle_multiline_folded_yaml():
    """Document known limitation: _fix_dq_value handles only single-line DQ scalars.

    Multi-line double-quoted YAML using YAML line folding (trailing backslash on
    physical lines) is NOT normalized by _fix_dq_value or _normalize_fm_lines.
    Such pages require a direct S-73 edit rather than automated normalization.
    The EN pdf/net page (block[1]) was fixed this way (2026-07-02).
    """
    # Key line has " but no ``` or \n — single-line DQ pattern does not match.
    key_line = '    content: "intro'
    assert "```" not in key_line

    # Continuation line has \n and ``` but no " — also does not match.
    continuation = "      \\n```csharp\\nusing Aspose.Pdf;\\n\\n"
    assert '"' not in continuation
