"""Tests for scripts/pipeline/commands/ops/install_defect_sweep.py
(PKGINSTALL-DEFECT-SWEEP-REDESIGN, MT066 plan section R.3.4).
"""
import json
import sys
from pathlib import Path

import pytest

_PIPELINE_ROOT = Path(__file__).resolve().parent.parent
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

import commands.ops.install_defect_sweep as sut  # noqa: E402
import content_eval.evaluators.install_recipe as install_recipe  # noqa: E402
from content_eval.loader import load_all_products  # noqa: E402
from content_eval.models import Page  # noqa: E402
import reconciliation_store as _reco  # noqa: E402


@pytest.fixture(autouse=True)
def isolate(tmp_path):
    sut.configure(repo_root=tmp_path)
    install_recipe.configure()
    yield
    sut.configure(repo_root=None)
    install_recipe.configure()


def _write_page(tmp_path: Path, family: str, platform: str, filename: str, text: str) -> Path:
    p = tmp_path / "content" / "docs.aspose.org" / "en" / family / platform / filename
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def _unpublished_pypi_registry(family: str, platform: str) -> dict:
    return {
        family: {platform: {
            "registry_type": "pypi",
            "candidate": {"name": f"aspose-{family}-foss"},
            "verification": {"published": False, "verified_at": "2026-08-01"},
        }}
    }


class TestRunLiteralSweep:
    def test_delegates_to_install_literal_sweep_unchanged(self, tmp_path):
        _write_page(
            tmp_path, "words", "net", "installation.md",
            "dotnet add package Aspose.Words.FOSS\n",
        )
        registry = {
            "words": {"net": {"registry_type": "nuget", "candidate": {"name": "Aspose.Words.FOSS"},
                                "verification": {"published": True}}},
        }
        report = sut.run_literal_sweep(registry=registry)
        assert report["total_findings"] == 1
        assert report["total_files_checked"] == 1


class TestRunInstallRecipeSweep:
    def test_publish_claim_contradiction_detected(self, tmp_path):
        page_path = _write_page(
            tmp_path, "barcode", "python", "installation.md",
            "Install the package. It is available on PyPI, just run the usual command.\n",
        )
        install_recipe.configure(registry=_unpublished_pypi_registry("barcode", "python"))
        page = Page.load(page_path)
        report = sut.run_install_recipe_sweep(products={("barcode", "python"): [page]})

        assert report["total_publish_claim_contradiction_findings"] == 1
        assert report["total_pages_checked"] == 1
        assert len(report["per_product"]) == 1
        assert report["per_product"][0]["family"] == "barcode"

    def test_no_findings_for_a_clean_page(self, tmp_path):
        page_path = _write_page(
            tmp_path, "barcode", "python", "installation.md",
            "Not yet published -- build from source until it ships.\n",
        )
        install_recipe.configure(registry=_unpublished_pypi_registry("barcode", "python"))
        page = Page.load(page_path)
        report = sut.run_install_recipe_sweep(products={("barcode", "python"): [page]})

        assert report["total_publish_claim_contradiction_findings"] == 0
        assert report["per_product"] == []

    def test_real_regression_pin_against_current_content(self):
        """Acceptance check: reproduces the same 89 real
        PUBLISH-CLAIM-CONTRADICTION-001 findings (backlog/BACKLOG.md) when
        run against current content -- no override, real portfolio."""
        sut.configure(repo_root=None)
        install_recipe.configure()
        report = sut.run_install_recipe_sweep()
        assert report["total_publish_claim_contradiction_findings"] == 89, (
            f"expected the known-real 89 PUBLISH-CLAIM-CONTRADICTION-001 findings, "
            f"got {report['total_publish_claim_contradiction_findings']} -- if this is a "
            f"genuine change (fixed or regressed), update backlog/BACKLOG.md's own row "
            f"and this pin together, not just one"
        )


class TestReconciliationRows:
    def test_shared_sweep_run_id_and_row_per_touched_product(self, tmp_path):
        literal_report = {"per_product": [
            {"family": "words", "platform": "python", "findings": 3, "files_checked": 10},
        ]}
        recipe_report = {"per_product": [
            {"family": "words", "platform": "python", "pages_checked": 10,
             "publish_claim_contradiction_findings": 2, "unpublished_disclosure_findings": 0},
            {"family": "barcode", "platform": "python", "pages_checked": 5,
             "publish_claim_contradiction_findings": 1, "unpublished_disclosure_findings": 0},
        ]}
        rows = sut._reconciliation_rows(literal_report, recipe_report, sweep_run_id="run-x", recorded_at="2026-09-10T00:00:00Z")
        assert len(rows) == 2
        assert all(r["sweep_run_id"] == "run-x" for r in rows)
        words_row = next(r for r in rows if r["family"] == "words")
        assert words_row["finding_count_literal"] == 3
        assert words_row["finding_count_install_recipe_fail"] == 2
        barcode_row = next(r for r in rows if r["family"] == "barcode")
        assert barcode_row["finding_count_literal"] == 0
        assert barcode_row["finding_count_install_recipe_fail"] == 1


class TestRunCombinedSweep:
    def test_appends_rows_under_one_shared_sweep_run_id(self, tmp_path):
        _write_page(
            tmp_path, "words", "net", "installation.md",
            "dotnet add package Aspose.Words.FOSS\n",
        )
        registry = {
            "words": {"net": {"registry_type": "nuget", "candidate": {"name": "Aspose.Words.FOSS"},
                                "verification": {"published": True}}},
        }
        store = _reco.ReconciliationStore(repo_root=tmp_path)
        result = sut.run_combined_sweep(registry=registry, products={}, store=store)

        assert result["reconciliation_rows_written"] >= 1
        history = store.read_history()
        run_ids = {row["sweep_run_id"] for row in history}
        assert run_ids == {result["sweep_run_id"]}

    def test_explicit_sweep_run_id_is_honored(self, tmp_path):
        store = _reco.ReconciliationStore(repo_root=tmp_path)
        registry = {
            "words": {"net": {"registry_type": "nuget", "candidate": {"name": "Aspose.Words.FOSS"},
                                "verification": {"published": True}}},
        }
        result = sut.run_combined_sweep(registry=registry, products={}, store=store, sweep_run_id="fixed-run-id")
        assert result["sweep_run_id"] == "fixed-run-id"


class TestDefectClassFindings:
    def test_flattens_all_three_defect_classes(self):
        result = {
            "literal_report": {"per_product": [
                {"family": "words", "platform": "python", "findings": 3, "sample_findings": []},
                {"family": "clean", "platform": "python", "findings": 0, "sample_findings": []},
            ]},
            "recipe_report": {"per_product": [
                {"family": "barcode", "platform": "python", "publish_claim_contradiction_findings": 2,
                 "unpublished_disclosure_findings": 1,
                 "sample_publish_claim_contradiction": [], "sample_unpublished_disclosure": []},
            ]},
        }
        findings = sut.defect_class_findings(result)
        classes = {(f["family"], f["platform"], f["defect_class"]) for f in findings}
        assert ("words", "python", "literal_install_command") in classes
        assert ("barcode", "python", "publish_claim_contradiction") in classes
        assert ("barcode", "python", "unpublished_disclosure") in classes
        assert ("clean", "python", "literal_install_command") not in classes
