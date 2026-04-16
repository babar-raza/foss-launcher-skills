"""Test that content_eval produces identical results across reruns.

This is the S2-4 CI consistency test. If this test fails, a non-determinism
regression has been introduced into the evaluator suite.

Strategy:
  1. Build a synthetic page (markdown with frontmatter) in a tmp directory
  2. Build minimal knowledge fixtures (api_surface, claims, model, formats)
  3. Load the real Knowledge object from knowledge_core
  4. Run every DEFAULT_EVALUATOR twice on the same (page, knowledge) pair
  5. Assert identical findings (same count, same IDs, same levels/categories)
  6. Assert identical grade
"""

from __future__ import annotations

import json
import shutil
import textwrap
from pathlib import Path

import pytest

# sys.path is set by tests/conftest.py — no manual insert needed here.
from content_eval.config import DEFAULT_EVALUATORS
from content_eval.evaluators import _ensure_loaded, get_evaluator
from content_eval.models import EvalReport, Finding, Page, compute_grade_with_criticality
from knowledge_core import Knowledge


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

_SYNTHETIC_PAGE = textwrap.dedent("""\
    ---
    title: "Working with Scene in Aspose.3D for Python"
    description: "Learn how to create and manipulate 3D scenes using Aspose.3D for Python."
    type: docs
    weight: 10
    url: /3d/python/working-with-scene/
    ---

    ## Overview

    The `Scene` class is the top-level container for 3D content in
    Aspose.3D for Python. You can load, modify, and save 3D files using
    the Scene API.

    ## Creating a Scene

    ```python
    import aspose.threed as a3d

    scene = a3d.Scene()
    node = scene.root_node.create_child_node("box")
    scene.save("output.obj")
    ```

    ## Loading a File

    Use `Scene.from_file` to load an existing 3D model:

    ```python
    scene = a3d.Scene.from_file("input.fbx")
    print(scene.root_node.name)
    ```

    ## Supported Formats

    Aspose.3D supports OBJ, STL, glTF, and FBX formats for import and export.

    ## Node Hierarchy

    Every scene has a `root_node` property of type `Node`. You can traverse
    the hierarchy using `Node.create_child_node`:

    ```python
    child = scene.root_node.create_child_node("child1")
    grandchild = child.create_child_node("grandchild1")
    ```

    ## See Also

    - [API Reference](/3d/python/api/)
""")


@pytest.fixture
def knowledge(tmp_path):
    """Build a Knowledge object from the standard test fixtures."""
    merged = tmp_path / "knowledge" / "fake" / "python" / "merged"
    merged.mkdir(parents=True)

    shutil.copy(_FIXTURES_DIR / "fake_api_surface.json", merged / "api_surface.json")
    shutil.copy(_FIXTURES_DIR / "fake_model.yaml", merged / "model.yaml")
    shutil.copy(_FIXTURES_DIR / "fake_claims.json", merged / "claims.json")
    shutil.copy(_FIXTURES_DIR / "fake_formats.json", merged / "formats.json")

    return Knowledge("fake", "python", knowledge_root=tmp_path / "knowledge")


@pytest.fixture
def page(tmp_path):
    """Write the synthetic page to disk and return a loaded Page."""
    md_path = (
        tmp_path / "content" / "docs.aspose.org" / "en" / "3d" / "python"
        / "working-with-scene" / "_index.md"
    )
    md_path.parent.mkdir(parents=True)
    md_path.write_text(_SYNTHETIC_PAGE, encoding="utf-8")
    return Page.load(md_path)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_all_default_evaluators(page: Page, knowledge: Knowledge) -> list[Finding]:
    """Run every DEFAULT_EVALUATOR on the page and return all findings."""
    _ensure_loaded()
    findings: list[Finding] = []
    for name in DEFAULT_EVALUATORS:
        evaluator_cls = get_evaluator(name)
        evaluator = evaluator_cls()
        findings.extend(evaluator.evaluate(page, knowledge))
    return findings


def _findings_signature(findings: list[Finding]) -> list[tuple[str, str, str, int, str]]:
    """Return a stable, sortable signature of each finding.

    Tuple: (id, level, category, line_no, evaluator)
    """
    return sorted(
        (f.id, f.level, f.category, f.line_no, f.evaluator)
        for f in findings
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestEvalRerunConsistency:
    """Two identical evaluations must produce byte-identical findings."""

    def test_findings_identical_across_runs(self, page, knowledge):
        """Run evaluators twice; both runs must produce the same findings."""
        run1 = _run_all_default_evaluators(page, knowledge)
        run2 = _run_all_default_evaluators(page, knowledge)

        sig1 = _findings_signature(run1)
        sig2 = _findings_signature(run2)

        assert sig1 == sig2, (
            f"Findings differ between runs.\n"
            f"Run 1 ({len(run1)} findings): {sig1}\n"
            f"Run 2 ({len(run2)} findings): {sig2}"
        )

    def test_finding_count_identical(self, page, knowledge):
        """Both runs must produce the same number of findings."""
        run1 = _run_all_default_evaluators(page, knowledge)
        run2 = _run_all_default_evaluators(page, knowledge)

        assert len(run1) == len(run2), (
            f"Finding count differs: run1={len(run1)}, run2={len(run2)}"
        )

    def test_grade_identical_across_runs(self, page, knowledge):
        """Both runs must produce the same aggregate grade."""
        run1 = _run_all_default_evaluators(page, knowledge)
        run2 = _run_all_default_evaluators(page, knowledge)

        grade1 = compute_grade_with_criticality(run1)
        grade2 = compute_grade_with_criticality(run2)

        assert grade1 == grade2, (
            f"Grade differs: run1={grade1}, run2={grade2}"
        )

    def test_finding_ids_identical(self, page, knowledge):
        """Stable IDs (CE-{hash}) must match across runs."""
        run1 = _run_all_default_evaluators(page, knowledge)
        run2 = _run_all_default_evaluators(page, knowledge)

        ids1 = sorted(f.id for f in run1)
        ids2 = sorted(f.id for f in run2)

        assert ids1 == ids2, (
            f"Finding IDs differ.\n"
            f"Only in run1: {set(ids1) - set(ids2)}\n"
            f"Only in run2: {set(ids2) - set(ids1)}"
        )

    def test_per_evaluator_consistency(self, page, knowledge):
        """Each evaluator individually must be deterministic."""
        _ensure_loaded()
        for name in DEFAULT_EVALUATORS:
            evaluator_cls = get_evaluator(name)

            findings_a = evaluator_cls().evaluate(page, knowledge)
            findings_b = evaluator_cls().evaluate(page, knowledge)

            sig_a = _findings_signature(findings_a)
            sig_b = _findings_signature(findings_b)

            assert sig_a == sig_b, (
                f"Evaluator '{name}' is non-deterministic.\n"
                f"Run A ({len(findings_a)}): {sig_a}\n"
                f"Run B ({len(findings_b)}): {sig_b}"
            )

    def test_evaluators_produce_some_findings(self, page, knowledge):
        """Sanity: the synthetic page should trigger at least a few findings.

        If zero findings are produced, the test is vacuously true and
        provides no real coverage against non-determinism.
        """
        findings = _run_all_default_evaluators(page, knowledge)
        assert len(findings) > 0, (
            "Synthetic page produced zero findings — test is vacuous. "
            "Update _SYNTHETIC_PAGE to trigger at least one evaluator."
        )

    def test_report_grade_matches_findings(self, page, knowledge):
        """EvalReport.grade must match compute_grade_with_criticality on same data."""
        findings = _run_all_default_evaluators(page, knowledge)

        report = EvalReport(findings=findings)
        report_grade = report.grade

        direct_grade = compute_grade_with_criticality(findings)

        # EvalReport.grade now uses compute_grade_with_criticality (T-06 fix),
        # so both must return the same value.
        assert report_grade == direct_grade, (
            f"EvalReport.grade ({report_grade}) != "
            f"compute_grade_with_criticality ({direct_grade})"
        )

        # Stability across reruns
        findings2 = _run_all_default_evaluators(page, knowledge)
        report2 = EvalReport(findings=findings2)

        assert report_grade == report2.grade, (
            f"EvalReport.grade not stable: {report_grade} vs {report2.grade}"
        )
        assert direct_grade == compute_grade_with_criticality(findings2), (
            f"compute_grade_with_criticality not stable: "
            f"{direct_grade} vs {compute_grade_with_criticality(findings2)}"
        )
