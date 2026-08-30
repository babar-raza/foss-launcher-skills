"""
Tests for commands/ops/registry_coverage_scan.py (Mission
MT018-2026-08-01-PACKAGE-IDENTITY-COVERAGE, TC-MT018-03).

The enumeration step driving the package-registry backfill: unions
content_discovery.discover_products() with a products.aspose.org directory
scan, diffs against data/package_registry.json + data/registry_exclusions.json.
"""

import json
import sys
from pathlib import Path

import pytest

_PIPELINE_ROOT = Path(__file__).resolve().parents[1]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

import commands.ops.registry_coverage_scan as sut


@pytest.fixture(autouse=True)
def isolate_repo(tmp_path):
    sut.configure(repo_root=tmp_path)
    yield tmp_path
    sut.configure(repo_root=None)


def _make_knowledge_product(tmp_path: Path, family: str, platform: str) -> None:
    d = tmp_path / "knowledge" / family / platform / "merged"
    d.mkdir(parents=True, exist_ok=True)
    (d / "api_surface.json").write_text("{}", encoding="utf-8")


def _make_products_page(tmp_path: Path, family: str, platform: str) -> None:
    d = tmp_path / "content" / "products.aspose.org" / "en" / family / platform
    d.mkdir(parents=True, exist_ok=True)
    (d / "_index.md").write_text("---\n---\n", encoding="utf-8")


def _write_registry(tmp_path: Path, entries: dict) -> None:
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "package_registry.json").write_text(json.dumps(entries), encoding="utf-8")


def _write_exclusions(tmp_path: Path, entries: list) -> None:
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "registry_exclusions.json").write_text(json.dumps(entries), encoding="utf-8")


def test_scan_products_directory_finds_index_pages(tmp_path):
    _make_products_page(tmp_path, "slides", "net")
    _make_products_page(tmp_path, "cells", "python")
    pairs = sut.scan_products_directory()
    assert set(pairs) == {("cells", "python"), ("slides", "net")}


def test_scan_products_directory_empty_when_no_index_md(tmp_path):
    (tmp_path / "content" / "products.aspose.org" / "en" / "slides" / "net").mkdir(parents=True)
    pairs = sut.scan_products_directory()
    assert pairs == []


def test_uncovered_pairs_computed_correctly(tmp_path):
    _make_knowledge_product(tmp_path, "slides", "net")
    _make_knowledge_product(tmp_path, "words", "net")
    _make_products_page(tmp_path, "slides", "net")
    _make_products_page(tmp_path, "words", "net")
    _write_registry(tmp_path, {"slides": {"net": {"registry_type": "nuget"}}})
    _write_exclusions(tmp_path, [])

    report = sut.scan_coverage()
    assert report["total_discovered"] == 2
    assert report["total_registered"] == 1
    assert report["uncovered_pairs"] == ["words/net"]


def test_divergent_pairs_flagged_not_silently_dropped(tmp_path):
    """A product with a knowledge model but no live page (or vice versa) is a
    real discrepancy -- must be surfaced, not silently unioned away."""
    _make_knowledge_product(tmp_path, "slides", "net")
    _make_products_page(tmp_path, "words", "net")  # different pair, no knowledge model
    _write_registry(tmp_path, {})
    _write_exclusions(tmp_path, [])

    report = sut.scan_coverage()
    assert set(report["divergent_pairs"]) == {"slides/net", "words/net"}


def test_excluded_but_still_live_is_flagged(tmp_path):
    """cells/typescript-style case: excluded in registry_exclusions.json as
    not launchable, but a live products.aspose.org page still exists."""
    _make_knowledge_product(tmp_path, "cells", "typescript")
    _make_products_page(tmp_path, "cells", "typescript")
    _write_registry(tmp_path, {})
    _write_exclusions(tmp_path, [
        {"match": "family_platform", "family": "cells", "platform": "typescript", "reason": "not launchable"},
    ])

    report = sut.scan_coverage()
    assert report["excluded_but_still_live"] == ["cells/typescript"]


def test_excluded_and_not_live_is_not_flagged(tmp_path):
    """An exclusion with no live content is not a discrepancy -- the exclusion
    worked as intended."""
    _write_registry(tmp_path, {})
    _write_exclusions(tmp_path, [
        {"match": "family_platform", "family": "cells", "platform": "typescript", "reason": "not launchable"},
    ])

    report = sut.scan_coverage()
    assert report["excluded_but_still_live"] == []


def test_no_exclusions_file_is_not_an_error(tmp_path):
    _make_knowledge_product(tmp_path, "slides", "net")
    _make_products_page(tmp_path, "slides", "net")
    _write_registry(tmp_path, {})
    # deliberately do not write data/registry_exclusions.json
    report = sut.scan_coverage()
    assert report["excluded_but_still_live"] == []


def test_cli_exit_code_reflects_uncovered_pairs(tmp_path, capsys):
    _make_knowledge_product(tmp_path, "slides", "net")
    _make_products_page(tmp_path, "slides", "net")
    _write_registry(tmp_path, {})
    _write_exclusions(tmp_path, [])

    exit_code = sut.main([])
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "slides/net" in captured.out


def test_cli_exit_code_zero_when_fully_covered(tmp_path):
    _make_knowledge_product(tmp_path, "slides", "net")
    _make_products_page(tmp_path, "slides", "net")
    _write_registry(tmp_path, {"slides": {"net": {"registry_type": "nuget"}}})
    _write_exclusions(tmp_path, [])

    exit_code = sut.main(["--json"])
    assert exit_code == 0


def test_real_repo_scan_matches_manual_audit():
    """Regression pin against the real repo (no fixture). Originally pinned
    the pre-backfill state (31 discovered, 7 registered, 24 uncovered); as
    of TC-MT018-06's full backfill (2026-08-01), coverage is complete --
    updated to pin that instead. Bumped again 31->32 (2026-08-30, MT040):
    pdf/typescript registered as the mission's 32nd product. cells/typescript's
    exclusion-drift finding is unaffected by either change (it's a
    content-vs-exclusion-list discrepancy, not a registry-coverage one) and
    must still be flagged."""
    sut.configure(repo_root=None)
    report = sut.scan_coverage()
    assert report["total_discovered"] == 32
    assert report["total_registered"] == 32
    assert report["uncovered_pairs"] == []
    assert "cells/typescript" in report["excluded_but_still_live"]
