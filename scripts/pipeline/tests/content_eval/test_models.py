"""Tests for content_eval models."""

import tempfile
import textwrap
from pathlib import Path

import pytest

# sys.path is set by tests/conftest.py — no manual insert needed here.
from content_eval.config import (
    CANONICAL_EVALUATORS,
    EXPERIMENTAL_EVALUATORS,
    SAFETY_OVERRIDE_FINDINGS,
)
from content_eval.models import (
    CRITICAL_CATEGORIES,
    CodeBlock,
    EvalReport,
    Finding,
    Heading,
    Page,
    compute_grade_with_criticality,
)


class TestFinding:
    def test_stable_id(self):
        f = Finding("FAIL", "AA", "test.md", 10, "Method not found")
        assert f.id.startswith("CE-")
        assert len(f.id) == 11  # CE- + 8 hex chars

    def test_same_finding_same_id(self):
        f1 = Finding("FAIL", "AA", "test.md", 10, "Method not found")
        f2 = Finding("FAIL", "AA", "test.md", 10, "Method not found")
        assert f1.id == f2.id

    def test_different_finding_different_id(self):
        f1 = Finding("FAIL", "AA", "test.md", 10, "Method not found")
        f2 = Finding("FAIL", "AA", "test.md", 11, "Method not found")
        assert f1.id != f2.id


class TestPage:
    def _make_page(self, content: str, filename: str = "content/docs.aspose.org/en/slides/dotnet/test.md"):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write(content)
            f.flush()
            # Override filepath for metadata inference
            page = Page.load(Path(f.name))
            # Manually set filepath for path-based inference
            page.filepath = Path(filename)
            page._infer_metadata()
            return page

    def test_frontmatter_parsing(self):
        page = self._make_page(textwrap.dedent("""\
            ---
            title: Test Page
            description: A test
            type: docs
            ---
            Hello world.
        """))
        assert page.frontmatter["title"] == "Test Page"
        assert page.frontmatter["type"] == "docs"

    def test_code_block_extraction(self):
        page = self._make_page(textwrap.dedent("""\
            ---
            title: Test
            ---
            Some text.

            ```csharp
            var prs = new Presentation();
            prs.Save("out.pptx");
            ```

            More text.
        """))
        assert len(page.code_blocks) == 1
        assert page.code_blocks[0].lang == "csharp"
        assert "Presentation" in page.code_blocks[0].content

    def test_heading_extraction(self):
        page = self._make_page(textwrap.dedent("""\
            ---
            title: Test
            ---
            ## Overview
            Some text.
            ### Details
            More text.
        """))
        assert len(page.headings) == 2
        assert page.headings[0].level == 2
        assert page.headings[0].text == "Overview"
        assert page.headings[1].level == 3

    def test_subdomain_inference(self):
        page = self._make_page("---\ntitle: T\n---\nHi", "content/kb.aspose.org/en/slides/dotnet/faq.md")
        assert page.subdomain == "kb"
        assert page.family == "slides"
        assert page.platform == "dotnet"
        assert page.page_role == "faq"

    def test_prose_lines(self):
        page = self._make_page(textwrap.dedent("""\
            ---
            title: T
            ---
            This is prose.

            ```python
            x = 1
            ```

            More prose here.
        """))
        prose_texts = [t for _, t in page.prose_lines]
        assert "This is prose." in prose_texts
        assert "More prose here." in prose_texts
        assert "x = 1" not in prose_texts


class TestEvalReport:
    def test_severity_counts(self):
        report = EvalReport(findings=[
            Finding("FAIL", "AA", "a.md", 1, "bad"),
            Finding("WARN", "ST", "a.md", 2, "meh"),
            Finding("INFO", "RL", "b.md", 1, "fyi"),
            Finding("FAIL", "FC", "c.md", 1, "forbidden"),
        ])
        assert len(report.fails) == 2
        assert len(report.warns) == 1
        assert len(report.infos) == 1

    def test_by_file(self):
        report = EvalReport(findings=[
            Finding("FAIL", "AA", "a.md", 1, "bad"),
            Finding("WARN", "ST", "a.md", 2, "meh"),
            Finding("INFO", "RL", "b.md", 1, "fyi"),
        ])
        by_file = report.by_file()
        assert len(by_file["a.md"]) == 2
        assert len(by_file["b.md"]) == 1

    def test_by_category(self):
        report = EvalReport(findings=[
            Finding("FAIL", "AA", "a.md", 1, "bad"),
            Finding("FAIL", "AA", "b.md", 2, "also bad"),
            Finding("INFO", "RL", "c.md", 1, "fyi"),
        ])
        by_cat = report.by_category()
        assert len(by_cat["AA"]) == 2
        assert len(by_cat["RL"]) == 1


# ---------------------------------------------------------------------------
# PKGINSTALL-GRADE-SAFETY-OVERRIDE (GRADE_CONTRACT.md section 10)
#
# install_recipe is an EXPERIMENTAL evaluator, so none of its findings normally
# reach the grade letter. SAFETY_OVERRIDE_FINDINGS is a narrow allowlist of
# (evaluator, category) pairs whose FAIL findings DO count, and both categories
# are critical, so one such FAIL forces grade F. Until
# PKGINSTALL-GRADE-SAFETY-OVERRIDE-FIX no committed test exercised any of this,
# so removing the override (or a typo in either config tuple) would have left
# every test green while false publish claims went back to grading A.
# ---------------------------------------------------------------------------

_OVERRIDE_CATEGORIES = ("IR_PUBLISH_CLAIM", "IR_UNPUBLISHED_DISCLOSURE")


def _ir(level: str, category: str, evaluator: str = "install_recipe") -> Finding:
    return Finding(level, category, "docs/page.md", 12, "safety finding", evaluator=evaluator)


class TestSafetyOverrideGradeEffect:
    @pytest.mark.parametrize("category", _OVERRIDE_CATEGORIES)
    def test_fail_in_override_category_grades_f(self, category):
        findings = [_ir("FAIL", category)]
        assert compute_grade_with_criticality(findings) == "F"
        assert EvalReport(findings=findings).grade == "F"

    @pytest.mark.parametrize("category", _OVERRIDE_CATEGORIES)
    def test_grade_reasons_cite_the_critical_override(self, category):
        reasons = EvalReport(findings=[_ir("FAIL", category)]).grade_reasons()
        assert len(reasons) == 1, reasons
        assert f"FAIL in {category} (install_recipe)" in reasons[0]
        assert "critical category override" in reasons[0]
        assert reasons[0].endswith("-> F")

    def test_fail_in_the_untouched_ir_category_does_not_flip_the_grade(self):
        """Only the two split categories are safety-critical. The noisier
        _verify_install_accuracy FAIL keeps category "IR" and stays experimental:
        excluded from the grade, exactly as before the override existed."""
        findings = [_ir("FAIL", "IR")]
        assert compute_grade_with_criticality(findings) == "A"
        report = EvalReport(findings=findings)
        assert report.grade == "A"
        assert report.grade_reasons() == ["No findings -> grade A"]

    def test_many_untouched_ir_fails_still_do_not_flip_the_grade(self):
        assert compute_grade_with_criticality([_ir("FAIL", "IR") for _ in range(10)]) == "A"

    @pytest.mark.parametrize("category", _OVERRIDE_CATEGORIES)
    @pytest.mark.parametrize("level", ["WARN", "INFO"])
    def test_warn_and_info_in_override_categories_have_no_effect(self, category, level):
        """The allowlist is FAIL-only (section 10 eligibility bar): a WARN or INFO
        from the same evaluator and category stays experimental."""
        findings = [_ir(level, category)]
        assert compute_grade_with_criticality(findings) == "A"
        assert EvalReport(findings=findings).grade_reasons() == ["No findings -> grade A"]

    @pytest.mark.parametrize("category", _OVERRIDE_CATEGORIES)
    def test_many_warns_in_override_categories_still_do_not_count(self, category):
        assert compute_grade_with_criticality([_ir("WARN", category) for _ in range(10)]) == "A"

    def test_unknown_category_from_install_recipe_does_not_flip(self):
        assert compute_grade_with_criticality([_ir("FAIL", "IR_NEW_CHECK")]) == "A"

    def test_category_typo_silently_disables_the_override(self):
        """Documents the failure mode the consistency tests below exist to catch:
        the match is an exact (evaluator, category) pair, so a typo fails toward
        hidden, not toward blocked."""
        assert compute_grade_with_criticality([_ir("FAIL", "IR_PUBLISH_CLAIMS")]) == "A"

    def test_evaluator_typo_silently_disables_the_override(self):
        assert compute_grade_with_criticality(
            [_ir("FAIL", "IR_PUBLISH_CLAIM", evaluator="install_reciep")]) == "A"

    def test_same_category_from_another_experimental_evaluator_is_excluded(self):
        assert "structure" in EXPERIMENTAL_EVALUATORS
        assert compute_grade_with_criticality(
            [_ir("FAIL", "IR_PUBLISH_CLAIM", evaluator="structure")]) == "A"

    def test_same_category_from_a_canonical_evaluator_is_critical(self):
        """Pair semantics from the other side: the critical-category rule itself
        applies to a canonical evaluator without needing the allowlist."""
        assert "api_accuracy" in CANONICAL_EVALUATORS
        assert compute_grade_with_criticality(
            [_ir("FAIL", "IR_PUBLISH_CLAIM", evaluator="api_accuracy")]) == "F"

    def test_empty_findings_grade_a(self):
        assert compute_grade_with_criticality([]) == "A"
        assert EvalReport(findings=[]).grade_reasons() == ["No findings -> grade A"]

    def test_override_fail_dominates_otherwise_clean_or_noisy_pages(self):
        canonical_noise = [Finding("WARN", "ST", "docs/page.md", n, "meh", evaluator="api_accuracy")
                           for n in range(1, 4)]
        assert compute_grade_with_criticality(canonical_noise) == "B"
        with_override = canonical_noise + [_ir("FAIL", "IR_UNPUBLISHED_DISCLOSURE")]
        assert compute_grade_with_criticality(with_override) == "F"
        assert EvalReport(findings=with_override).grade_reasons() == [
            "FAIL in IR_UNPUBLISHED_DISCLOSURE (install_recipe) -> critical category override -> F"
        ]

    def test_experimental_noise_alongside_does_not_change_the_result(self):
        """Findings from other experimental evaluators never join the override."""
        findings = [_ir("FAIL", "IR_PUBLISH_CLAIM"),
                    Finding("FAIL", "ST", "docs/page.md", 3, "x", evaluator="structure")]
        assert compute_grade_with_criticality(findings) == "F"
        reasons = EvalReport(findings=findings).grade_reasons()
        assert len(reasons) == 1 and "IR_PUBLISH_CLAIM" in reasons[0]


class TestSafetyOverrideConfigConsistency:
    """A typo in SAFETY_OVERRIDE_FINDINGS, or drift against grade_config.yaml or
    the evaluator's own source, silently disables the override. These tests pin
    the three lists to each other."""

    @staticmethod
    def _evaluator_class(name: str):
        from content_eval.evaluators import _ensure_loaded, get_evaluator

        _ensure_loaded()
        return get_evaluator(name)

    def test_the_two_known_pairs_are_present(self):
        """Removing a pair is exactly the regression that would put false publish
        claims back on grade-A pages, so it must fail a test, not pass silently."""
        assert {("install_recipe", c) for c in _OVERRIDE_CATEGORIES} <= set(SAFETY_OVERRIDE_FINDINGS)

    def test_every_pair_names_an_experimental_evaluator(self):
        for evaluator, category in SAFETY_OVERRIDE_FINDINGS:
            assert evaluator in EXPERIMENTAL_EVALUATORS, (evaluator, category)
            assert evaluator not in CANONICAL_EVALUATORS, (
                f"{evaluator} is canonical: its findings already count, the allowlist "
                "entry is dead weight and hides a graduation that was not recorded")

    def test_every_pair_names_a_critical_category(self):
        for evaluator, category in SAFETY_OVERRIDE_FINDINGS:
            assert category in CRITICAL_CATEGORIES, (
                f"{category} ({evaluator}) is not in grade_config.yaml critical_categories: "
                "the FAIL would count as an ordinary FAIL (grade C), not force F")

    def test_every_pair_evaluator_is_registered_with_that_exact_name(self):
        """The grade filter compares Finding.evaluator (set from the class's name
        attribute) to the pair's first element, so both must be the same string."""
        for evaluator, _category in SAFETY_OVERRIDE_FINDINGS:
            assert self._evaluator_class(evaluator).name == evaluator

    def test_every_pair_category_is_literally_emitted_by_that_evaluator(self):
        import inspect
        import re
        import sys

        for evaluator, category in SAFETY_OVERRIDE_FINDINGS:
            module = sys.modules[self._evaluator_class(evaluator).__module__]
            source = inspect.getsource(module)
            pattern = r"category\s*=\s*[\"']" + re.escape(category) + r"[\"']"
            assert re.search(pattern, source), (
                f"{evaluator} never emits category={category!r}; the override matches nothing")

    def test_critical_categories_carry_no_orphan_safety_names(self):
        """The reverse direction: a category in critical_categories that looks like
        one of ours but is not in the allowlist would be a half-finished rename."""
        pair_categories = {category for _evaluator, category in SAFETY_OVERRIDE_FINDINGS}
        orphans = {c for c in CRITICAL_CATEGORIES if c.startswith("IR_")} - pair_categories
        assert not orphans, orphans


class TestSafetyOverrideEndToEnd:
    """Real InstallRecipeEvaluator findings on real Page objects, graded by the
    real grade functions: proves the strings the evaluator emits are the strings
    the override matches (no fabricated Finding). The registry is injected through
    the evaluator's configure() seam; nothing is monkeypatched."""

    _REGISTRY = {
        "barcode": {"python": {
            "registry_type": "pypi",
            "candidate": {"name": "aspose-barcode-foss"},
            "candidate_owner": "asposefoss",
            "verification": {"published": False, "verified_at": "2026-08-01",
                              "verified_owner": None, "evidence_url": None, "method": None},
            "owner_match": None,
        }},
    }

    @pytest.fixture(autouse=True)
    def _registry(self):
        import content_eval.evaluators.install_recipe as ir_mod

        ir_mod.configure(registry=self._REGISTRY)
        yield
        ir_mod.configure()

    @staticmethod
    def _findings(tmp_path, rel_path: str, body: str) -> list[Finding]:
        from content_eval.evaluators.install_recipe import InstallRecipeEvaluator

        path = tmp_path / "content" / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        return InstallRecipeEvaluator().evaluate(Page.load(path), None)

    _BARCODE_PAGE = "docs.aspose.org/en/barcode/python/getting-started/installation.md"

    def test_false_publish_claim_grades_f(self, tmp_path):
        findings = self._findings(
            tmp_path, self._BARCODE_PAGE,
            "---\ntitle: Installation\ngrade: A\n---\n\n## Installation\n\n"
            "Install from PyPI: `pip install aspose-barcode-foss`\n")
        assert any(f.level == "FAIL" and f.category == "IR_PUBLISH_CLAIM" for f in findings), findings
        assert compute_grade_with_criticality(findings) == "F"
        assert "IR_PUBLISH_CLAIM" in EvalReport(findings=findings).grade_reasons()[0]

    def test_unpublished_disclosure_grades_f(self, tmp_path):
        findings = self._findings(
            tmp_path, self._BARCODE_PAGE,
            "---\ntitle: Installation\n---\n\n## Installation\n\n"
            "This package is not yet published on any registry.\n")
        assert any(f.level == "FAIL" and f.category == "IR_UNPUBLISHED_DISCLOSURE"
                   for f in findings), findings
        assert compute_grade_with_criticality(findings) == "F"
        assert "IR_UNPUBLISHED_DISCLOSURE" in EvalReport(findings=findings).grade_reasons()[0]

    def test_clean_page_stays_a(self, tmp_path):
        findings = self._findings(
            tmp_path, self._BARCODE_PAGE,
            "---\ntitle: Installation\n---\n\n## Installation\n\n"
            "Clone the repository and build the package from source.\n")
        assert [f for f in findings if f.level == "FAIL"] == []
        assert compute_grade_with_criticality(findings) == "A"

    def test_untouched_ir_fail_does_not_flip_a_real_page(self, tmp_path):
        """An unregistered family with an install command is a real FAIL in the
        plain IR category. It must stay excluded from the grade."""
        import content_eval.evaluators.install_recipe as ir_mod

        ir_mod.configure(registry={})
        findings = self._findings(
            tmp_path, "kb.aspose.org/en/unknown-family/python/how-to-install.md",
            "---\ntitle: Test\n---\n\n```bash\npip install some-package\n```\n")
        ir_fails = [f for f in findings if f.level == "FAIL" and f.category == "IR"]
        assert ir_fails, findings
        assert compute_grade_with_criticality(findings) == "A"
