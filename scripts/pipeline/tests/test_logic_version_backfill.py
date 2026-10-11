"""test_logic_version_backfill.py — Unit tests for logic_version_backfill.

Covers:
- Happy path: insert after graded_evaluators (primary insert point)
- Happy path: insert after graded_at (first fallback)
- Happy path: insert after grade: (last-resort fallback)
- Skip path: file with existing graded_logic_version not modified
- Skip path: file with no grade field not modified
- Regression (SR-05): graded_evaluators in body content is not matched
"""
from pathlib import Path

import pytest

from logic_version_backfill import _insert_logic_version, process_file


VERSION = "2"
INSERT_LINE = f'graded_logic_version: "{VERSION}"'


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_text(frontmatter_fields: str, body: str = "Body content.\n") -> str:
    """Build a full .md text with the given frontmatter field lines."""
    return f"---\n{frontmatter_fields}\n---\n\n{body}"


# ---------------------------------------------------------------------------
# Happy path: insert after graded_evaluators
# ---------------------------------------------------------------------------

def test_insert_after_graded_evaluators():
    """graded_logic_version is inserted immediately after graded_evaluators."""
    text = _make_text(
        "title: Foo\n"
        "grade: A\n"
        'graded_evaluators: ["eval-a"]\n'
        "graded_at: 2026-01-01\n"
    )
    result = _insert_logic_version(text, VERSION)

    assert result is not None
    lines = result.split("\n")
    ev_idx = next(i for i, ln in enumerate(lines) if ln.startswith("graded_evaluators:"))
    assert lines[ev_idx + 1].startswith(INSERT_LINE)

    # Must be within frontmatter (before closing ---)
    close_idx = next(i for i, ln in enumerate(lines) if ln.strip() == "---" and i > 0)
    assert ev_idx < close_idx


# ---------------------------------------------------------------------------
# Happy path: insert after graded_at (fallback — no graded_evaluators)
# ---------------------------------------------------------------------------

def test_insert_after_graded_at():
    """When graded_evaluators is absent, inserts after graded_at."""
    text = _make_text(
        "title: Foo\n"
        "grade: B\n"
        "graded_at: 2026-01-01\n"
    )
    result = _insert_logic_version(text, VERSION)

    assert result is not None
    lines = result.split("\n")
    at_idx = next(i for i, ln in enumerate(lines) if ln.startswith("graded_at:"))
    assert lines[at_idx + 1].startswith(INSERT_LINE)


# ---------------------------------------------------------------------------
# Happy path: insert after grade: (last resort — only grade present)
# ---------------------------------------------------------------------------

def test_insert_after_grade_last_resort():
    """When only grade: is present, inserts immediately after that line."""
    text = _make_text(
        "title: Foo\n"
        "grade: C\n"
    )
    result = _insert_logic_version(text, VERSION)

    assert result is not None
    lines = result.split("\n")
    grade_idx = next(i for i, ln in enumerate(lines) if ln.startswith("grade:"))
    assert lines[grade_idx + 1].startswith(INSERT_LINE)


# ---------------------------------------------------------------------------
# Skip path: graded_logic_version already present -> process_file returns skipped-ok
# ---------------------------------------------------------------------------

def test_process_file_skip_existing(tmp_path):
    """process_file returns skipped-ok when graded_logic_version already exists."""
    p = tmp_path / "page.md"
    p.write_text(
        _make_text(f'title: Foo\ngrade: A\ngraded_logic_version: "{VERSION}"\n'),
        encoding="utf-8",
    )
    result = process_file(p, apply=False)
    assert result == "skipped-ok"


# ---------------------------------------------------------------------------
# Skip path: no grade field -> process_file returns skipped-no-grade
# ---------------------------------------------------------------------------

def test_process_file_skip_no_grade(tmp_path):
    """process_file returns skipped-no-grade when no grade: field exists."""
    p = tmp_path / "page.md"
    p.write_text(_make_text("title: Foo\n"), encoding="utf-8")
    result = process_file(p, apply=False)
    assert result == "skipped-no-grade"


# ---------------------------------------------------------------------------
# Regression (SR-05): graded_evaluators in body must not trigger insertion
# ---------------------------------------------------------------------------

def test_body_graded_evaluators_not_matched():
    """graded_evaluators in body content must not produce a spurious insertion."""
    text = _make_text(
        "title: Foo\n"
        "grade: A\n",
        body='graded_evaluators: ["in-body"]\n\nSome prose.\n',
    )
    # Frontmatter has grade: A but no graded_evaluators — only in body.
    # Insertion should happen after grade:, and body must remain unchanged.
    result = _insert_logic_version(text, VERSION)

    assert result is not None
    assert INSERT_LINE in result

    # Locate body (everything after the closing ---)
    # The frontmatter closes at the second ---
    fm_end = result.index("\n---\n\n") + len("\n---\n\n")
    body_section = result[fm_end:]

    # graded_logic_version must NOT appear in the body
    assert INSERT_LINE not in body_section

    # Body's graded_evaluators line must still be intact
    assert 'graded_evaluators: ["in-body"]' in body_section
