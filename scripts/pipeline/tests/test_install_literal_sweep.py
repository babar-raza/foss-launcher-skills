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
