"""Tests for content_eval.runner.EvalRunner (TC-08 / MP-SR08).

Verifies that EvalRunner is injectable and testable without monkeypatching
or filesystem setup beyond a tmp_path.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts.pipeline.content_eval.runner import EvalRunner
from scripts.pipeline.content_eval.models import CodeBlock, Heading, Page


# ---------------------------------------------------------------------------
# Minimal Page helper (mirrors test_consumer_usefulness.py pattern)
# ---------------------------------------------------------------------------

def _page(
    prose_lines: list[str] | None = None,
    filepath: str = "content/docs.aspose.org/en/words/python/guide.md",
    family: str = "",
    platform: str = "",
) -> Page:
    p = Page.__new__(Page)
    p.filepath = Path(filepath)
    p.raw_text = ""
    p.frontmatter = {}
    p.body = ""
    p.body_offset = 0
    p.family = family
    p.platform = platform
    p.subdomain = "docs"
    p.page_role = "docs"
    p.links = []
    p.prose_lines = [(i + 1, line) for i, line in enumerate(prose_lines or [])]
    p.code_blocks = []
    p.headings = []
    return p


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

class TestEvalRunnerConstruction:
    def test_basic_init(self, tmp_path):
        runner = EvalRunner(
            evaluator_names=["consumer_usefulness"],
            output_root=tmp_path,
            knowledge_root=tmp_path / "knowledge",
        )
        assert runner.evaluator_names == ["consumer_usefulness"]
        assert runner.output_root == tmp_path
        assert runner.knowledge_root == tmp_path / "knowledge"

    def test_init_none_roots(self):
        runner = EvalRunner(evaluator_names=["consumer_usefulness"])
        assert runner.output_root is None
        assert runner.knowledge_root is None

    def test_init_string_roots(self, tmp_path):
        runner = EvalRunner(
            evaluator_names=["consumer_usefulness"],
            output_root=str(tmp_path),
            knowledge_root=str(tmp_path / "k"),
        )
        assert isinstance(runner.output_root, Path)
        assert isinstance(runner.knowledge_root, Path)


# ---------------------------------------------------------------------------
# run() — without real knowledge (knowledge unavailable)
# ---------------------------------------------------------------------------

class TestEvalRunnerRun:
    def test_run_no_pages_returns_empty_report(self, tmp_path):
        runner = EvalRunner(
            evaluator_names=["consumer_usefulness"],
            knowledge_root=tmp_path,  # empty → knowledge unavailable
        )
        from scripts.pipeline.content_eval.models import EvalReport
        report = runner.run([])
        assert report.pages_evaluated == 0
        assert report.findings == []

    def test_run_consumer_usefulness_on_short_page(self, tmp_path):
        """consumer_usefulness with <80 words emits no US-1 finding."""
        page = _page(["word " * 5] * 3)
        runner = EvalRunner(
            evaluator_names=["consumer_usefulness"],
            knowledge_root=tmp_path,  # no knowledge needed for this evaluator
        )
        report = runner.run([page])
        assert report.pages_evaluated == 1
        # No US-1 — fewer than 80 words
        us1 = [f for f in report.findings if f.category == "US" and "purpose" in f.message.lower()]
        assert us1 == []

    def test_run_consumer_usefulness_warns_on_long_page(self, tmp_path):
        """consumer_usefulness with ≥80 words and no purpose phrase → WARN."""
        page = _page(["word " * 20] * 5)
        runner = EvalRunner(
            evaluator_names=["consumer_usefulness"],
            knowledge_root=tmp_path,
        )
        report = runner.run([page])
        assert report.pages_evaluated == 1
        us1 = [f for f in report.findings if f.category == "US" and "purpose" in f.message.lower()]
        assert len(us1) == 1
        assert us1[0].level == "WARN"

    def test_run_multiple_pages(self, tmp_path):
        """Running on multiple pages accumulates findings correctly."""
        pages = [_page(["word " * 20] * 5) for _ in range(3)]
        runner = EvalRunner(
            evaluator_names=["consumer_usefulness"],
            knowledge_root=tmp_path,
        )
        report = runner.run(pages)
        assert report.pages_evaluated == 3
        us1_findings = [f for f in report.findings
                        if f.category == "US" and "purpose" in f.message.lower()]
        assert len(us1_findings) == 3

    def test_run_knowledge_unavailable_emits_pipeline_fail(self, tmp_path):
        """When knowledge root has no api_surface.json, a PIPELINE FAIL is emitted."""
        page = _page(family="words", platform="python")
        runner = EvalRunner(
            evaluator_names=["api_accuracy"],
            knowledge_root=tmp_path,  # empty → Knowledge.available = False
        )
        report = runner.run([page])
        pipeline_fails = [f for f in report.findings if f.category == "PIPELINE"]
        assert len(pipeline_fails) == 1
        assert "unavailable" in pipeline_fails[0].message.lower()

    def test_runner_injectable_without_monkeypatch(self, tmp_path):
        """Core seam test: runner can be fully configured via __init__ args only."""
        # No monkeypatching, no SKIP_SKILL_CONTEXT_CHECK, just inject via constructor
        page = _page(
            ["This guide shows how to create a chart.\n"] + ["word " * 20] * 5
        )
        runner = EvalRunner(
            evaluator_names=["consumer_usefulness"],
            output_root=tmp_path / "reports",
            knowledge_root=tmp_path / "knowledge",
        )
        report = runner.run([page])
        # Purpose phrase present → no US-1
        us1 = [f for f in report.findings
               if f.category == "US" and "purpose" in f.message.lower()]
        assert us1 == []
