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
        """Acceptance check: reproduces the same 67 real
        PUBLISH-CLAIM-CONTRADICTION-001 findings (backlog/BACKLOG.md) when
        run against current content -- no override, real portfolio.

        TC-PKG-01-08-FIX (2026-09-17): re-pinned from 89 -> 67. The original
        89 (set 2026-09-10, commit 30a955550e) went stale as real content was
        fixed on some flagged pages by unrelated work landing on main between
        then and now -- an organic improvement (fewer contradictions), not a
        regression in the wrong direction, and not a logic bug in this sweep.
        Independently re-derived fresh (not copied from a prior review) via
        two methods: this pytest run, and a standalone script calling
        run_install_recipe_sweep() directly -- both agree on 67, with the
        same per-product breakdown: 3d/typescript=1, barcode/python=9,
        cells/typescript=1, font/python=21, html/python=12, page/python=2,
        pdf/python=19, tex/python=2 (unpublished_disclosure=0, unchanged).
        Kept as an exact pin (not loosened to a range/inequality): this is a
        regression-pin control whose entire purpose is to force a human/agent
        to look whenever the number moves, in either direction -- a range
        would silently swallow future regressions up to its ceiling instead
        of surfacing them here.
        """
        sut.configure(repo_root=None)
        install_recipe.configure()
        report = sut.run_install_recipe_sweep()
        assert report["total_publish_claim_contradiction_findings"] == 67, (
            f"expected the known-real 67 PUBLISH-CLAIM-CONTRADICTION-001 findings, "
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

    def test_writes_both_aggregate_and_english_source_per_file_rows(self, tmp_path):
        """TC-PKG-02-READINESS-GATE-FIX: run_combined_sweep must write BOTH
        the pre-existing product-level aggregate row (synthetic
        reports/audit/install-defect-sweep/{family}-{platform} path) AND a
        real per-file row keyed at the actual content/ path -- the exact
        shape is_english_source_ready() looks up. Before this fix, 0 of the
        sweep's own rows ever had a content/-prefixed path (confirmed live
        by 3 independent taskcards: TC-PKG-02-05/07/18)."""
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

        assert result["english_source_file_rows_written"] == 1
        history = store.read_history()
        paths = {row["path"] for row in history}
        assert "content/docs.aspose.org/en/words/net/installation.md" in paths
        assert any(p.startswith("reports/audit/install-defect-sweep/") for p in paths)
        content_row = next(r for r in history if r["path"] == "content/docs.aspose.org/en/words/net/installation.md")
        assert content_row["family"] == "words"
        assert content_row["platform"] == "net"
        assert content_row["site"] == "docs.aspose.org"
        assert content_row["locale"] == "en"
        assert content_row["representation"] == "literal"
        assert content_row["finding_count_literal"] == 1
        assert content_row["sweep_run_id"] == result["sweep_run_id"]


class TestEnglishSourceFileRows:
    """PKGINSTALL-DEFECT-SWEEP-REDESIGN's writer only ever emitted one
    synthetic-path row per (family, platform) -- never a real per-file row
    keyed the way locale_patch.is_english_source_ready()'s
    _reconciliation_key() looks up. These tests pin the new per-file writer
    directly, independent of run_combined_sweep's aggregate path."""

    def test_emits_one_row_per_english_source_file_with_real_content_path(self, tmp_path):
        _write_page(
            tmp_path, "words", "net", "installation.md",
            "dotnet add package Aspose.Words.FOSS\n",
        )
        registry = {
            "words": {"net": {"registry_type": "nuget", "candidate": {"name": "Aspose.Words.FOSS"},
                                "verification": {"published": True}}},
        }
        rows = sut._english_source_file_rows(registry=registry, sweep_run_id="run-y", recorded_at="2026-09-18T00:00:00Z")
        assert len(rows) == 1
        row = rows[0]
        assert row["path"] == "content/docs.aspose.org/en/words/net/installation.md"
        assert row["family"] == "words"
        assert row["platform"] == "net"
        assert row["site"] == "docs.aspose.org"
        assert row["locale"] == "en"
        assert row["representation"] == "literal"
        assert row["finding_count_literal"] == 1
        assert row["collision_classification"] is None
        assert row["sweep_run_id"] == "run-y"
        assert row["recorded_at"] == "2026-09-18T00:00:00Z"

    def test_clean_file_gets_zero_finding_count_and_non_literal_representation(self, tmp_path):
        _write_page(
            tmp_path, "words", "net", "installation.md",
            '{{< package-install "words" "net" >}}\n',
        )
        registry = {
            "words": {"net": {"registry_type": "nuget", "candidate": {"name": "Aspose.Words.FOSS"},
                                "verification": {"published": True}}},
        }
        rows = sut._english_source_file_rows(registry=registry, sweep_run_id="r", recorded_at="t")
        assert len(rows) == 1
        assert rows[0]["representation"] != "literal"
        assert rows[0]["finding_count_literal"] == 0

    def test_non_english_locale_copy_is_excluded(self, tmp_path):
        p = tmp_path / "content" / "docs.aspose.org" / "fr" / "words" / "net" / "installation.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("dotnet add package Aspose.Words.FOSS\n", encoding="utf-8")
        registry = {
            "words": {"net": {"registry_type": "nuget", "candidate": {"name": "Aspose.Words.FOSS"},
                                "verification": {"published": True}}},
        }
        rows = sut._english_source_file_rows(registry=registry, sweep_run_id="r", recorded_at="t")
        assert rows == []

    def test_blog_site_english_index_included_locale_suffix_excluded(self, tmp_path):
        en = tmp_path / "content" / "blog.aspose.org" / "words" / "net" / "some-post" / "index.md"
        en.parent.mkdir(parents=True, exist_ok=True)
        en.write_text("dotnet add package Aspose.Words.FOSS\n", encoding="utf-8")
        fr = en.with_name("index.fr.md")
        fr.write_text("dotnet add package Aspose.Words.FOSS\n", encoding="utf-8")
        registry = {
            "words": {"net": {"registry_type": "nuget", "candidate": {"name": "Aspose.Words.FOSS"},
                                "verification": {"published": True}}},
        }
        rows = sut._english_source_file_rows(registry=registry, sweep_run_id="r", recorded_at="t")
        assert len(rows) == 1
        assert rows[0]["path"] == "content/blog.aspose.org/words/net/some-post/index.md"

    def test_rows_are_schema_valid_against_the_real_reconciliation_store(self, tmp_path):
        """Not just shape-plausible -- actually accepted by
        reconciliation_store.append_batch()'s real
        validate_reconciliation_record() gate."""
        _write_page(
            tmp_path, "words", "net", "installation.md",
            "dotnet add package Aspose.Words.FOSS\n",
        )
        registry = {
            "words": {"net": {"registry_type": "nuget", "candidate": {"name": "Aspose.Words.FOSS"},
                                "verification": {"published": True}}},
        }
        rows = sut._english_source_file_rows(registry=registry, sweep_run_id="r", recorded_at="2026-09-18T00:00:00Z")
        store = _reco.ReconciliationStore(repo_root=tmp_path)
        written = store.append_batch(rows)
        assert written == len(rows) == 1


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
