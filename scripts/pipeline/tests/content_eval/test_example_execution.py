"""Tests for example_execution.py (C8, MT065-2026-09-06-EXAMPLE-VERIFICATION-
CENTRALIZATION) -- the EXPERIMENTAL, inherit-first execution-proof advisory
evaluator built on the centralized lib.example_verification package.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from content_eval.evaluators import example_execution as _ee
from content_eval.evaluators.example_execution import ExampleExecutionEvaluator
from content_eval.config import CANONICAL_EVALUATORS, DEFAULT_EVALUATORS, EXPERIMENTAL_EVALUATORS
from content_eval.models import Page
from knowledge_core import Knowledge


@pytest.fixture(autouse=True)
def _reset_configure():
    yield
    _ee.configure()


def _make_page(tmp_path: Path, family: str, platform: str, body: str) -> Page:
    content_dir = tmp_path / "content" / "docs.aspose.org" / "en" / family / platform
    content_dir.mkdir(parents=True, exist_ok=True)
    md_file = content_dir / "test.md"
    md_file.write_text(f"---\ntitle: test\n---\n\n{body}\n", encoding="utf-8")
    return Page.load(md_file)


def _make_knowledge(tmp_path: Path, family: str, platform: str,
                     snippet_index: "list[dict] | None" = None) -> Knowledge:
    merged = tmp_path / family / platform / "merged"
    merged.mkdir(parents=True, exist_ok=True)
    (merged / "model.yaml").write_text("version: '1.0'\nrepo_sha: abc123\n", encoding="utf-8")
    (merged / "api_surface.json").write_text("[]", encoding="utf-8")
    if snippet_index is not None:
        snippets_dir = merged / "snippets"
        snippets_dir.mkdir(parents=True, exist_ok=True)
        (snippets_dir / "snippets_index.json").write_text(
            json.dumps(snippet_index), encoding="utf-8")
    return Knowledge(family, platform, knowledge_root=tmp_path)


def _norm(code: str) -> str:
    from lib.example_verification.code_fences import normalize_content
    import hashlib
    return hashlib.sha256(normalize_content(code).encode("utf-8")).hexdigest()


PY_CLEAN = "def f(x, y):\n    return x + y\n"
PY_BROKEN = "def f(x, y:\n    return x + y\n"


class TestRegistration:
    """The plan requires this evaluator to be EXPERIMENTAL + DEFAULT, and to
    never contribute to the canonical frontmatter grade."""

    def test_registered_experimental_and_default_never_canonical(self):
        assert "example_execution" in EXPERIMENTAL_EVALUATORS
        assert "example_execution" in DEFAULT_EVALUATORS
        assert "example_execution" not in CANONICAL_EVALUATORS


class TestNoIndexAtAll:
    """Today's real portfolio state: zero of ~32 products have code_sha256
    populated anywhere (C10's own live measurement) -- this must degrade to
    one page-level SKIP notice, not a WARN per block."""

    def test_no_snippet_index_file_produces_one_info_not_a_warn_per_block(self, tmp_path):
        page = _make_page(tmp_path, "acme", "python", f"```python\n{PY_CLEAN}```\n")
        knowledge = _make_knowledge(tmp_path, "acme", "python", snippet_index=None)

        findings = ExampleExecutionEvaluator().evaluate(page, knowledge)

        assert len(findings) == 1
        assert findings[0].level == "INFO"
        assert findings[0].category == "EX"
        assert "SKIPPED" in findings[0].message

    def test_snippet_index_present_but_no_code_sha256_field_also_skips(self, tmp_path):
        page = _make_page(tmp_path, "acme", "python", f"```python\n{PY_CLEAN}```\n")
        knowledge = _make_knowledge(tmp_path, "acme", "python", snippet_index=[
            {"id": "snippet_001", "classes_used": ["Foo"]},
        ])

        findings = ExampleExecutionEvaluator().evaluate(page, knowledge)

        assert len(findings) == 1
        assert findings[0].level == "INFO"
        assert "SKIPPED" in findings[0].message

    def test_page_with_no_code_blocks_produces_no_findings(self, tmp_path):
        page = _make_page(tmp_path, "acme", "python", "Just prose, no code.\n")
        knowledge = _make_knowledge(tmp_path, "acme", "python", snippet_index=None)

        assert ExampleExecutionEvaluator().evaluate(page, knowledge) == []

    def test_non_executable_lang_blocks_are_skipped(self, tmp_path):
        page = _make_page(tmp_path, "acme", "python", "```json\n{\"a\": 1}\n```\n")
        knowledge = _make_knowledge(tmp_path, "acme", "python", snippet_index=None)

        assert ExampleExecutionEvaluator().evaluate(page, knowledge) == []

    def test_shell_family_blocks_are_skipped_not_grammar_unavailable_noise(self, tmp_path):
        """Independent-review finding (round 1): syntax.py has no tree-sitter
        grammar for any shell-family language, so without this exclusion
        every install-command bash block in the whole portfolio would
        produce a permanent, predictable GRAMMAR-UNAVAILABLE WARN -- not a
        real signal, just noise. A page with ONLY a bash block must produce
        no findings at all (not even the SKIP INFO, since there are no
        in-scope blocks to check)."""
        page = _make_page(tmp_path, "acme", "python", "```bash\npip install acme\n```\n")
        knowledge = _make_knowledge(tmp_path, "acme", "python", snippet_index=None)

        assert ExampleExecutionEvaluator().evaluate(page, knowledge) == []


class TestLookupProof:
    """Once a product's index HAS code_sha256 populated (a future, not yet
    real, state), per-block lookup activates."""

    def test_exact_match_with_execution_proof_is_inherited_info(self, tmp_path):
        page = _make_page(tmp_path, "acme", "python", f"```python\n{PY_CLEAN}```\n")
        knowledge = _make_knowledge(tmp_path, "acme", "python", snippet_index=[
            {
                "id": "snippet_001",
                "code_sha256": {"norm": _norm(PY_CLEAN), "exact": "x"},
                "execution_proof": {"tier": 3, "runner_version": "1"},
            },
        ])

        findings = ExampleExecutionEvaluator().evaluate(page, knowledge)

        info = [f for f in findings if f.level == "INFO" and "inherited" in f.message]
        assert len(info) == 1
        assert "snippet_001" in info[0].message
        assert "tier 3" in info[0].message

    def test_no_matching_entry_is_novel_unverified_warn(self, tmp_path):
        page = _make_page(tmp_path, "acme", "python", f"```python\n{PY_CLEAN}```\n")
        knowledge = _make_knowledge(tmp_path, "acme", "python", snippet_index=[
            {
                "id": "snippet_999",
                "code_sha256": {"norm": "some-other-hash", "exact": "x"},
                "execution_proof": {"tier": 3, "runner_version": "1"},
            },
        ])

        findings = ExampleExecutionEvaluator().evaluate(page, knowledge)

        warns = [f for f in findings if f.level == "WARN" and "Novel code block" in f.message]
        assert len(warns) == 1

    def test_matching_entry_with_no_execution_proof_yet_is_novel_unverified(self, tmp_path):
        """The exact real-world case: code_sha256 exists (product was
        promoted after C6) but the post-promote execution sweep hasn't run
        for it yet -- must not be silently treated as verified."""
        page = _make_page(tmp_path, "acme", "python", f"```python\n{PY_CLEAN}```\n")
        knowledge = _make_knowledge(tmp_path, "acme", "python", snippet_index=[
            {"id": "snippet_001", "code_sha256": {"norm": _norm(PY_CLEAN), "exact": "x"}},
        ])

        findings = ExampleExecutionEvaluator().evaluate(page, knowledge)

        warns = [f for f in findings if f.level == "WARN" and "Novel code block" in f.message]
        assert len(warns) == 1

    def test_stale_runner_version_is_stale_by_warn(self, tmp_path):
        page = _make_page(tmp_path, "acme", "python", f"```python\n{PY_CLEAN}```\n")
        knowledge = _make_knowledge(tmp_path, "acme", "python", snippet_index=[
            {
                "id": "snippet_001",
                "code_sha256": {"norm": _norm(PY_CLEAN), "exact": "x"},
                "execution_proof": {"tier": 3, "runner_version": "999-stale"},
            },
        ])

        findings = ExampleExecutionEvaluator().evaluate(page, knowledge)

        warns = [f for f in findings if f.level == "WARN" and "stale" in f.message]
        assert len(warns) == 1
        assert "snippet_001" in warns[0].message

    def test_configured_max_tier_never_downgrades_a_higher_inherited_tier(self, tmp_path):
        """max_tier ceilings this evaluator's own LIVE checks (which never
        exceed tier 1 regardless, since it never acquires) -- it must never
        cause a higher, already-inherited tier to be reported as unverified;
        more inherited proof is strictly more trustworthy, never less."""
        _ee.configure(max_tier=1)
        page = _make_page(tmp_path, "acme", "python", f"```python\n{PY_CLEAN}```\n")
        knowledge = _make_knowledge(tmp_path, "acme", "python", snippet_index=[
            {
                "id": "snippet_001",
                "code_sha256": {"norm": _norm(PY_CLEAN), "exact": "x"},
                "execution_proof": {"tier": 3, "runner_version": "1"},
            },
        ])

        findings = ExampleExecutionEvaluator().evaluate(page, knowledge)

        info = [f for f in findings if f.level == "INFO" and "inherited" in f.message]
        assert len(info) == 1
        assert "tier 3" in info[0].message


class TestLiveSyntaxCheck:
    """Independent of proof-inheritance status: a live tier-1 syntax check
    always runs (never acquires), FAILing only when a real parse ran and
    found a genuine error."""

    def test_broken_python_produces_fail(self, tmp_path):
        page = _make_page(tmp_path, "acme", "python", f"```python\n{PY_BROKEN}```\n")
        knowledge = _make_knowledge(tmp_path, "acme", "python", snippet_index=None)

        findings = ExampleExecutionEvaluator().evaluate(page, knowledge)

        fails = [f for f in findings if f.level == "FAIL"]
        assert len(fails) == 1
        assert fails[0].category == "EX"
        assert "syntax error" in fails[0].message

    def test_clean_python_produces_no_fail(self, tmp_path):
        page = _make_page(tmp_path, "acme", "python", f"```python\n{PY_CLEAN}```\n")
        knowledge = _make_knowledge(tmp_path, "acme", "python", snippet_index=None)

        findings = ExampleExecutionEvaluator().evaluate(page, knowledge)

        assert not any(f.level == "FAIL" for f in findings)

    def test_unknown_language_is_grammar_unavailable_warn_not_fail(self, tmp_path):
        page = _make_page(tmp_path, "acme", "python", "```cobol\nSOME NONSENSE HERE\n```\n")
        knowledge = _make_knowledge(tmp_path, "acme", "python", snippet_index=None)

        findings = ExampleExecutionEvaluator().evaluate(page, knowledge)

        assert not any(f.level == "FAIL" for f in findings)
        assert any("no tree-sitter grammar available" in f.message
                   for f in findings if f.level == "WARN")

    def test_fail_line_number_points_at_the_actual_broken_line(self, tmp_path):
        """Independent-review finding (round 1): block.start_line is the
        OPENING FENCE line itself, so content line 1 is start_line + 1 --
        an earlier draft computed start_line + (error_line - 1), landing
        one line short (on the fence line itself when the error was on the
        block's first content line). This body places the real syntax
        error on line 3 of the block's own content."""
        body = "```python\nx = 1\ndef f(x, y:\n    return x + y\n```\n"
        page = _make_page(tmp_path, "acme", "python", body)
        # frontmatter is "---\ntitle: test\n---\n\n" = 4 lines, then the
        # fence opens on file line 5; content line 2 ("def f(x, y:",
        # tree-sitter's own 1-based error_line) is file line 7.
        knowledge = _make_knowledge(tmp_path, "acme", "python", snippet_index=None)

        findings = ExampleExecutionEvaluator().evaluate(page, knowledge)

        fails = [f for f in findings if f.level == "FAIL"]
        assert len(fails) == 1
        assert fails[0].line_no == 7

    def test_broken_java_produces_fail(self, tmp_path):
        page = _make_page(
            tmp_path, "acme", "java",
            "```java\npublic class Foo { void bar() { int x = ; } }\n```\n")
        knowledge = _make_knowledge(tmp_path, "acme", "java", snippet_index=None)

        findings = ExampleExecutionEvaluator().evaluate(page, knowledge)

        assert any(f.level == "FAIL" for f in findings)


class TestBudget:
    def test_budget_exhausted_produces_one_warn_and_stops_per_block_checks(self, tmp_path):
        body = "".join(f"```python\n{PY_CLEAN}```\n\n" for _ in range(3))
        page = _make_page(tmp_path, "acme", "python", body)
        knowledge = _make_knowledge(tmp_path, "acme", "python", snippet_index=None)
        _ee.configure(budget=0.0)

        findings = ExampleExecutionEvaluator().evaluate(page, knowledge)

        budget_findings = [f for f in findings if "BUDGET-EXHAUSTED" in f.message]
        assert len(budget_findings) == 1
        # No per-block syntax/proof findings beyond the SKIP + the one budget WARN.
        assert not any(f.level == "FAIL" for f in findings)


class TestNonKnowledgeInput:
    def test_missing_knowledge_object_produces_no_findings(self, tmp_path):
        page = _make_page(tmp_path, "acme", "python", f"```python\n{PY_CLEAN}```\n")
        assert ExampleExecutionEvaluator().evaluate(page, None) == []
