"""Tests for content_eval.runner.EvalRunner (TC-08 / MP-SR08).

Verifies that EvalRunner is injectable and testable without monkeypatching
or filesystem setup beyond a tmp_path.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Use short-form imports consistent with the conftest sys.path injection.
# scripts/pipeline/tests/conftest.py adds scripts/pipeline/ to sys.path, so
# "content_eval" resolves directly without the "scripts.pipeline." prefix
# (which would require scripts/__init__.py, which does not exist).
from content_eval.runner import EvalRunner
from content_eval.models import Page
from content_eval import EVALUATOR_LOGIC_VERSION, EVALUATOR_VERSIONS
import grade_manifest as _gm


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
# Fixtures: graded page file + knowledge directory
# ---------------------------------------------------------------------------

def _write_graded_md(tmp_path: Path, enrichment_status: str | None) -> Path:
    """Write a minimal .md file with a grade block at the given enrichment_status.

    Also writes a manifest entry so the ARCH-02 manifest-first skip path works.
    """
    import yaml as _yaml
    from grade_writer import write_grade as _write_grade, content_hash as _content_hash

    md_dir = tmp_path / "content" / "docs" / "words" / "python"
    md_dir.mkdir(parents=True, exist_ok=True)
    md_file = md_dir / "guide.md"
    body_text = "Body text here.\n"
    md_file.write_text(f"---\ntitle: Test\n---\n\n{body_text}", encoding="utf-8")
    _write_grade(
        md_file,
        grade="B",
        model_sha="deadbeef00000001",
        evaluator_tier="full",
        logic_version=EVALUATOR_LOGIC_VERSION,
        enrichment_status=enrichment_status,
    )
    # Also write a manifest entry (ARCH-02: manifest-first skip path)
    rel_path = str(md_file).replace("\\", "/")
    chash = _content_hash(body_text)
    _gm.write_manifest_entry(
        rel_path,
        content_hash=chash,
        grade="B",
        grade_reasons=["0 FAIL -> grade B"],
        evaluator_versions=dict(EVALUATOR_VERSIONS),
        model_sha="deadbeef00000001",
        logic_version=EVALUATOR_LOGIC_VERSION,
        enrichment_status=enrichment_status or "full",
        graded_evaluators="full",
        manifest_path=tmp_path / "reports" / "grade_manifest.json",
    )
    return md_file


def _make_knowledge_root(tmp_path: Path, enrichment_status: str | None) -> Path:
    """Create a minimal knowledge directory with model.yaml + api_surface.json."""
    import yaml as _yaml

    merged = tmp_path / "knowledge" / "words" / "python" / "merged"
    merged.mkdir(parents=True, exist_ok=True)
    (merged / "api_surface.json").write_text("[]", encoding="utf-8")
    model = {"repo_sha": "deadbeef00000001"}
    if enrichment_status is not None:
        model["enrichment_status"] = enrichment_status
    (merged / "model.yaml").write_text(_yaml.dump(model), encoding="utf-8")
    return tmp_path / "knowledge"


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
        from content_eval.models import EvalReport
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
        # Standardized message includes "inflated grades" context (RC-4 fix)
        assert "inflated grades" in pipeline_fails[0].message

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

    def test_knowledge_cache_exposed_as_public_attribute(self, tmp_path):
        """After run(), runner.knowledge_cache is accessible for sweep consumers."""
        page = _page(["word " * 5] * 3)
        runner = EvalRunner(
            evaluator_names=["consumer_usefulness"],
            knowledge_root=tmp_path,
        )
        runner.run([page])
        # knowledge_cache is a dict (may be empty if page had no family/platform)
        assert isinstance(runner.knowledge_cache, dict)

    def test_seed_cache_avoids_reload(self, tmp_path):
        """Knowledge in _seed_cache is reused — not reloaded — during run() (SR-01)."""
        from content_eval.runner import _load_knowledge

        kn_root = _make_knowledge_root(tmp_path, enrichment_status="full")
        # Simulate what cli.py skip-graded block does: pre-load knowledge
        pre_loaded = _load_knowledge("words", "python", knowledge_root=kn_root)
        seed = {("words", "python"): pre_loaded}

        page = _page(
            prose_lines=["word " * 5] * 3,
            family="words",
            platform="python",
        )
        runner = EvalRunner(
            evaluator_names=["consumer_usefulness"],
            knowledge_root=kn_root,
        )
        runner.run([page], _seed_cache=seed)

        # Identity check: same object must be in knowledge_cache (not a reload)
        cached = runner.knowledge_cache.get(("words", "python"))
        assert cached is pre_loaded, (
            "runner.run() must reuse seeded knowledge object, not reload it"
        )


# ---------------------------------------------------------------------------
# RC-2: skip-graded enrichment quality gate
# ---------------------------------------------------------------------------

class TestSkipGradedEnrichmentGate:
    """When enrichment quality improves on the same repo SHA, pages must be
    re-evaluated.  The skip-graded gate must compare graded_enrichment_status
    against the current knowledge enrichment_status (RC-2 fix)."""

    @pytest.fixture(autouse=True)
    def _redirect_manifest(self, tmp_path, monkeypatch):
        """Point grade_manifest to tmp_path so tests use their own manifest."""
        monkeypatch.setattr(_gm, "_DEFAULT_MANIFEST_PATH",
                            tmp_path / "reports" / "grade_manifest.json")

    def test_does_not_skip_when_enrichment_improved(self, tmp_path):
        """Page graded at scout-only must be re-evaluated when knowledge is now full."""
        # Grade was written when knowledge was scout-only
        md_file = _write_graded_md(tmp_path, enrichment_status="scout-only")
        # Knowledge has since been enriched (same repo SHA)
        kn_root = _make_knowledge_root(tmp_path, enrichment_status="full")

        page = _page(
            prose_lines=["word " * 5] * 3,
            filepath=str(md_file),
            family="words",
            platform="python",
        )
        runner = EvalRunner(
            evaluator_names=["consumer_usefulness"],
            knowledge_root=kn_root,
        )
        report = runner.run([page], skip_graded=True)

        # Page was NOT skipped: it was re-evaluated because enrichment improved
        assert report.pages_evaluated == 1, (
            "Page should be re-evaluated when enrichment_status improved from "
            "scout-only → full on the same repo SHA"
        )

    def test_skips_when_enrichment_unchanged(self, tmp_path):
        """Page graded at full enrichment is skipped when knowledge is still full."""
        # Grade was written with full enrichment
        md_file = _write_graded_md(tmp_path, enrichment_status="full")
        # Knowledge still at full enrichment (same repo SHA, same logic version)
        kn_root = _make_knowledge_root(tmp_path, enrichment_status="full")

        page = _page(
            prose_lines=["word " * 5] * 3,
            filepath=str(md_file),
            family="words",
            platform="python",
        )
        runner = EvalRunner(
            evaluator_names=["consumer_usefulness"],
            knowledge_root=kn_root,
        )
        report = runner.run([page], skip_graded=True)

        # Page WAS skipped: nothing changed since last grading
        assert report.pages_evaluated == 0, (
            "Page should be skipped when enrichment_status is unchanged (full → full)"
        )

    def test_does_not_skip_when_enrichment_degraded(self, tmp_path):
        """Page graded at full enrichment is re-evaluated if knowledge regressed
        to scout-only (e.g. after a failed enrich run)."""
        # Grade was written with full enrichment
        md_file = _write_graded_md(tmp_path, enrichment_status="full")
        # Knowledge regressed to scout-only (enrich step failed)
        kn_root = _make_knowledge_root(tmp_path, enrichment_status="scout-only")

        page = _page(
            prose_lines=["word " * 5] * 3,
            filepath=str(md_file),
            family="words",
            platform="python",
        )
        runner = EvalRunner(
            evaluator_names=["consumer_usefulness"],
            knowledge_root=kn_root,
        )
        report = runner.run([page], skip_graded=True)

        # Page was NOT skipped: enrichment quality regressed, must re-evaluate
        assert report.pages_evaluated == 1, (
            "Page should be re-evaluated when enrichment_status regressed "
            "(full → scout-only)"
        )

    def test_backward_compat_none_treated_as_full(self, tmp_path):
        """Pages graded before enrichment_status tracking (field absent in grade block)
        are treated as 'full' for backward-compat and skipped when knowledge is also full."""
        # Grade written before enrichment_status field existed (None → field absent)
        md_file = _write_graded_md(tmp_path, enrichment_status=None)
        # Knowledge is fully enriched
        kn_root = _make_knowledge_root(tmp_path, enrichment_status="full")

        page = _page(
            prose_lines=["word " * 5] * 3,
            filepath=str(md_file),
            family="words",
            platform="python",
        )
        runner = EvalRunner(
            evaluator_names=["consumer_usefulness"],
            knowledge_root=kn_root,
        )
        report = runner.run([page], skip_graded=True)

        # Page WAS skipped: absent field treated as "full" (backward-compat)
        assert report.pages_evaluated == 0, (
            "Pages with no enrichment_status in grade block should be treated as "
            "full and skipped when current knowledge is also full"
        )

    def test_backward_compat_knowledge_none_treated_as_full(self, tmp_path):
        """Knowledge model without enrichment_status field is treated as full."""
        # Grade written with full enrichment
        md_file = _write_graded_md(tmp_path, enrichment_status="full")
        # Knowledge model has no enrichment_status field (old bootstrap, field absent)
        kn_root = _make_knowledge_root(tmp_path, enrichment_status=None)

        page = _page(
            prose_lines=["word " * 5] * 3,
            filepath=str(md_file),
            family="words",
            platform="python",
        )
        runner = EvalRunner(
            evaluator_names=["consumer_usefulness"],
            knowledge_root=kn_root,
        )
        report = runner.run([page], skip_graded=True)

        # Page WAS skipped: absent knowledge enrichment_status treated as "full"
        assert report.pages_evaluated == 0, (
            "Knowledge with absent enrichment_status should be treated as full "
            "and not trigger re-evaluation"
        )


# ---------------------------------------------------------------------------
# SR-02: enrichment-degraded warning fires to stderr
# ---------------------------------------------------------------------------

class TestEnrichmentWarning:
    """Verifies the enrichment warning is emitted to stderr exactly once per
    product when enrichment_status != 'full', and is silent otherwise."""

    def test_warning_emitted_for_scout_only(self, tmp_path, capsys):
        """Warning fires to stderr when enrichment_status='scout-only'."""
        kn_root = _make_knowledge_root(tmp_path, enrichment_status="scout-only")
        page = _page(
            prose_lines=["word " * 5] * 3,
            filepath="content/docs.aspose.org/en/words/python/g.md",
            family="words",
            platform="python",
        )
        runner = EvalRunner(["consumer_usefulness"], knowledge_root=kn_root)
        runner.run([page])
        captured = capsys.readouterr()
        assert "scout-only" in captured.err
        assert "claim-based evaluators" in captured.err

    def test_no_warning_for_full_enrichment(self, tmp_path, capsys):
        """No warning emitted when enrichment_status='full'."""
        kn_root = _make_knowledge_root(tmp_path, enrichment_status="full")
        page = _page(
            prose_lines=["word " * 5] * 3,
            filepath="content/docs.aspose.org/en/words/python/g.md",
            family="words",
            platform="python",
        )
        runner = EvalRunner(["consumer_usefulness"], knowledge_root=kn_root)
        runner.run([page])
        captured = capsys.readouterr()
        assert "scout-only" not in captured.err
        assert "enrichment_status" not in captured.err

    def test_warning_emitted_once_per_product(self, tmp_path, capsys):
        """Warning fires only once even when multiple pages from the same product are evaluated."""
        kn_root = _make_knowledge_root(tmp_path, enrichment_status="scout-only")
        pages = [
            _page(
                prose_lines=["word " * 5] * 3,
                filepath=f"content/docs.aspose.org/en/words/python/g{i}.md",
                family="words",
                platform="python",
            )
            for i in range(3)
        ]
        runner = EvalRunner(["consumer_usefulness"], knowledge_root=kn_root)
        runner.run(pages)
        captured = capsys.readouterr()
        # Warning must appear exactly once, not once per page
        assert captured.err.count("scout-only") == 1
