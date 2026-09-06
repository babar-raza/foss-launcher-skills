"""Tests for smoke_test.py's fix in rollout step C2: the loader now
delegates to lib/example_verification/syntax.py (RC17 -- this used to be an
independent copy that disagreed with content_eval's own loader on which
languages got a tree_sitter_language_pack fallback), and a genuinely
missing grammar now reports a loud WARN instead of silently PASSing
(smoke_test.py:424-434, pre-fix).

Deliberately a separate file from tests/test_smoke_test.py (which is
outside this taskcard's allowed_paths) -- exercises smoke_test.py only
through its public check_file() API.
"""
from __future__ import annotations

from pathlib import Path

from smoke_test import check_file


def _write_md(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "page.md"
    p.write_text(content, encoding="utf-8")
    return p


def test_missing_grammar_is_a_loud_warn_not_a_silent_pass(tmp_path):
    # "cobol" is not a language lib.example_verification.syntax knows about
    # -- parser_for() returns None, standing in for a genuinely unavailable
    # grammar (the same code path a real missing grammar takes).
    md = _write_md(tmp_path, "```cobol\nIDENTIFICATION DIVISION.\n```\n")
    result = check_file(md, langs=frozenset({"cobol"}))
    assert result.warn_count == 1
    assert result.pass_count == 0
    assert result.fail_count == 0
    assert "GRAMMAR-UNAVAILABLE" in result.results[0].message
    assert result.results[0].status == "WARN"


def test_java_still_passes_through_shared_loader(tmp_path):
    md = _write_md(tmp_path, "```java\npublic class Foo {\n    void bar() {}\n}\n```\n")
    result = check_file(md, langs=frozenset({"java"}))
    assert result.pass_count == 1
    assert result.warn_count == 0
    assert result.fail_count == 0


def test_java_syntax_error_still_fails_through_shared_loader(tmp_path):
    md = _write_md(tmp_path, "```java\npublic class Foo {\n    void bar( {\n```\n")
    result = check_file(md, langs=frozenset({"java"}))
    assert result.fail_count == 1
