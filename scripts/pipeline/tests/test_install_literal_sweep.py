"""
Tests for commands/ops/install_literal_sweep.py (ST-054 TC-09,
plans/from_backlog/2026-08-16-st-054-inline-install-command-remediation.md).

The recurring full-corpus durability sweep -- reuses
verify_package_install_literals() unchanged; this module only adds
corpus-iteration, aggregation, and issue-body formatting.
"""

import json
import sys
from pathlib import Path

import pytest

_PIPELINE_ROOT = Path(__file__).resolve().parents[1]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

import commands.ops.install_literal_sweep as sut


@pytest.fixture(autouse=True)
def isolate_repo(tmp_path):
    sut.configure(repo_root=tmp_path)
    yield
    sut.configure(repo_root=None)


def _write(tmp_path: Path, rel_path: str, content: str) -> Path:
    p = tmp_path / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


_NUGET_REGISTRY = {
    "words": {"net": {"registry_type": "nuget", "candidate": {"name": "Aspose.Words.FOSS"},
                        "verification": {"published": True}}},
}

_MIXED_REGISTRY = {
    "words": {"net": {"registry_type": "nuget", "candidate": {"name": "Aspose.Words.FOSS"},
                        "verification": {"published": True}}},
    "cells": {"java": {"registry_type": "maven", "candidate": {}, "verification": {"published": True}}},
}


def test_clean_corpus_reports_zero_findings(tmp_path):
    _write(tmp_path, "content/docs.aspose.org/en/words/net/getting-started/installation.md", (
        '{{< package-install "words" "net" >}}\n'
    ))
    report = sut.run_sweep(registry=_NUGET_REGISTRY)
    assert report["total_findings"] == 0
    assert report["total_files_checked"] == 1


def test_literal_command_is_found_and_aggregated(tmp_path):
    _write(tmp_path, "content/docs.aspose.org/en/words/net/getting-started/installation.md", (
        "dotnet add package Aspose.Words.FOSS\n"
    ))
    _write(tmp_path, "content/kb.aspose.org/en/words/net/faq.md", (
        "Run `dotnet add package Aspose.Words.FOSS` to install.\n"
    ))
    report = sut.run_sweep(registry=_NUGET_REGISTRY)
    assert report["total_findings"] == 2
    assert report["total_files_with_findings"] == 2
    product = next(p for p in report["per_product"] if p["family"] == "words")
    assert product["findings"] == 2
    assert len(product["sample_findings"]) == 2


def test_maven_registry_type_out_of_scope(tmp_path):
    """maven/cargo have their own dedicated gate -- this sweep must never
    touch them, matching every other tool in this mission."""
    _write(tmp_path, "content/docs.aspose.org/en/cells/java/getting-started/installation.md", (
        "mvn dependency:get -Dartifact=org.aspose:aspose-cells-foss:1.0\n"
    ))
    report = sut.run_sweep(registry=_MIXED_REGISTRY)
    assert not any(p["family"] == "cells" for p in report["per_product"])


def test_all_locale_sites_covered(tmp_path):
    """The sweep must cover every in-scope subsite and locale, not just
    English docs -- this is the whole point of a durability sweep (ST-054's
    own history shows most debt hides in locale copies)."""
    _write(tmp_path, "content/docs.aspose.org/en/words/net/getting-started/installation.md",
           "dotnet add package Aspose.Words.FOSS\n")
    _write(tmp_path, "content/docs.aspose.org/de/words/net/getting-started/installation.md",
           "dotnet add package Aspose.Words.FOSS\n")
    _write(tmp_path, "content/kb.aspose.org/en/words/net/faq.md",
           "dotnet add package Aspose.Words.FOSS\n")
    _write(tmp_path, "content/blog.aspose.org/words/net/post/index.md",
           "dotnet add package Aspose.Words.FOSS\n")
    _write(tmp_path, "content/blog.aspose.org/words/net/post/index.fr.md",
           "dotnet add package Aspose.Words.FOSS\n")
    _write(tmp_path, "content/products.aspose.org/en/words/net/_index.md",
           "dotnet add package Aspose.Words.FOSS\n")
    report = sut.run_sweep(registry=_NUGET_REGISTRY)
    assert report["total_files_checked"] == 6
    assert report["total_findings"] == 6


def test_format_issue_body_includes_totals_and_samples(tmp_path):
    _write(tmp_path, "content/docs.aspose.org/en/words/net/getting-started/installation.md",
           "dotnet add package Aspose.Words.FOSS\n")
    report = sut.run_sweep(registry=_NUGET_REGISTRY)
    body = sut.format_issue_body(report)
    assert "1 total findings" in body
    assert "words/net" in body
    assert "installation.md" in body


def test_format_issue_body_skips_clean_products(tmp_path):
    """A product with 0 findings must not appear in the issue body table --
    keeps the report focused on what actually needs attention."""
    _write(tmp_path, "content/docs.aspose.org/en/words/net/getting-started/installation.md",
           '{{< package-install "words" "net" >}}\n')
    report = sut.run_sweep(registry=_NUGET_REGISTRY)
    body = sut.format_issue_body(report)
    assert "0 total findings" in body
    assert "words/net" not in body


def test_main_writes_issue_body_and_exits_1_on_findings(tmp_path, capsys):
    _write(tmp_path, "content/docs.aspose.org/en/words/net/getting-started/installation.md",
           "dotnet add package Aspose.Words.FOSS\n")
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "package_registry.json").write_text(json.dumps(_NUGET_REGISTRY), encoding="utf-8")
    issue_path = tmp_path / "issue-body.md"
    exit_code = sut.main(["--issue-body-out", str(issue_path)])
    assert exit_code == 1
    assert issue_path.is_file()
    assert "1 total findings" in issue_path.read_text(encoding="utf-8")


def test_main_exits_0_on_clean_sweep(tmp_path):
    _write(tmp_path, "content/docs.aspose.org/en/words/net/getting-started/installation.md",
           '{{< package-install "words" "net" >}}\n')
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "package_registry.json").write_text(json.dumps(_NUGET_REGISTRY), encoding="utf-8")
    exit_code = sut.main([])
    assert exit_code == 0


class TestDurablePersistence:
    """ST-054 TC-17: prior to this fix, install_literal_sweep.py only wrote a
    report when --issue-body-out was passed, and CI pointed that at /tmp
    (ephemeral) -- every 'current count' this campaign ever had existed only
    as narrative text pasted into a plan/backlog cell, which is directly why
    three same-day measurements (6,522 / 6,248 / 6,454) were never
    reconciled. This is the durability fix: persist every run, SHA-stamped,
    by default."""

    def test_run_sweep_persists_json_and_md_by_default(self, tmp_path):
        _write(tmp_path, "content/docs.aspose.org/en/words/net/getting-started/installation.md",
               "dotnet add package Aspose.Words.FOSS\n")
        (tmp_path / "data").mkdir(parents=True, exist_ok=True)
        (tmp_path / "data" / "package_registry.json").write_text(json.dumps(_NUGET_REGISTRY), encoding="utf-8")
        sut.main([])
        report_dir = tmp_path / "reports" / "audit" / "st054"
        json_files = list(report_dir.glob("sweep-*.json"))
        md_files = list(report_dir.glob("sweep-*.md"))
        assert len(json_files) == 1, f"expected exactly 1 persisted JSON report, found {json_files}"
        assert len(md_files) == 1, f"expected exactly 1 persisted MD report, found {md_files}"

    def test_no_persist_flag_skips_writing(self, tmp_path):
        _write(tmp_path, "content/docs.aspose.org/en/words/net/getting-started/installation.md",
               "dotnet add package Aspose.Words.FOSS\n")
        (tmp_path / "data").mkdir(parents=True, exist_ok=True)
        (tmp_path / "data" / "package_registry.json").write_text(json.dumps(_NUGET_REGISTRY), encoding="utf-8")
        sut.main(["--no-persist"])
        assert not (tmp_path / "reports" / "audit" / "st054").exists()

    def test_report_dir_override(self, tmp_path):
        _write(tmp_path, "content/docs.aspose.org/en/words/net/getting-started/installation.md",
               "dotnet add package Aspose.Words.FOSS\n")
        (tmp_path / "data").mkdir(parents=True, exist_ok=True)
        (tmp_path / "data" / "package_registry.json").write_text(json.dumps(_NUGET_REGISTRY), encoding="utf-8")
        custom_dir = tmp_path / "custom-reports"
        sut.main(["--report-dir", str(custom_dir)])
        assert list(custom_dir.glob("sweep-*.json"))

    def test_build_provenance_degrades_gracefully_outside_a_git_worktree(self, tmp_path):
        """Provenance is a best-effort honesty aid, not a hard requirement --
        a sweep in a non-git tmp_path fixture must not raise, just report
        base_sha=None rather than crash."""
        prov = sut.build_provenance()
        assert prov["base_sha"] is None
        assert prov["generated_at"]

    def test_write_report_record_includes_provenance_and_paths(self, tmp_path):
        _write(tmp_path, "content/docs.aspose.org/en/words/net/getting-started/installation.md",
               "dotnet add package Aspose.Words.FOSS\n")
        report = sut.run_sweep(registry=_NUGET_REGISTRY)
        record = sut.write_report(report)
        assert "provenance" in record
        assert "generated_at" in record["provenance"]
        assert Path(record["json_path"]).is_file()
        assert Path(record["md_path"]).is_file()
        # Round-trips cleanly -- report content on disk matches what was returned.
        on_disk = json.loads(Path(record["json_path"]).read_text(encoding="utf-8"))
        assert on_disk["report"]["total_findings"] == report["total_findings"]

    def test_format_report_markdown_includes_every_product_not_just_findings(self, tmp_path):
        """Unlike format_issue_body() (deliberately skips clean products to
        keep a GitHub issue focused), the persisted audit-trail report must
        include every tracked product -- matching TC-04's original full-table
        style, needed to trust a 0-findings result is real and not silently
        dropped."""
        _write(tmp_path, "content/docs.aspose.org/en/words/net/getting-started/installation.md",
               '{{< package-install "words" "net" >}}\n')
        report = sut.run_sweep(registry=_NUGET_REGISTRY)
        record = {"provenance": sut.build_provenance(), "report": report}
        body = sut.format_report_markdown(record)
        assert "words/net" in body
        assert "0 total findings" in body

    def test_main_warns_on_dirty_tree_but_still_persists(self, tmp_path, capsys):
        """A dirty tree doesn't block persistence (the sweep still ran and is
        still evidence) -- it must be flagged, not hidden, so a future
        comparison doesn't silently treat a noisy measurement as clean."""
        _write(tmp_path, "content/docs.aspose.org/en/words/net/getting-started/installation.md",
               "dotnet add package Aspose.Words.FOSS\n")
        (tmp_path / "data").mkdir(parents=True, exist_ok=True)
        (tmp_path / "data" / "package_registry.json").write_text(json.dumps(_NUGET_REGISTRY), encoding="utf-8")
        exit_code = sut.main([])
        # Not a git worktree at all (tmp_path) -- must warn about missing
        # provenance rather than silently proceeding as if it were clean.
        assert exit_code == 1
        stderr = capsys.readouterr().err
        assert "base_sha" in stderr
