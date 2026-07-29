"""SEO-DUPLICATE-TITLE-CI-CHECK: check_duplicate_titles.py tests.

Grandfather-existing-debt, block-new-regressions pattern (Finding #22/#24):
31 docs devguide pages + 28 KB FAQ pages currently share generic titles --
this check must not fail CI over pre-existing debt, only over a NEW
duplicate-title group appearing since the last reviewed baseline.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_CHECK_PATH = Path(__file__).resolve().parents[2] / "ci" / "checks" / "check_duplicate_titles.py"
_spec = importlib.util.spec_from_file_location("check_duplicate_titles", _CHECK_PATH)
check_duplicate_titles = importlib.util.module_from_spec(_spec)
sys.modules["check_duplicate_titles"] = check_duplicate_titles
_spec.loader.exec_module(check_duplicate_titles)


def _write_page(root: Path, site: str, rel: str, title: str) -> None:
    path = root / site / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\ntitle: {title}\n---\nBody\n", encoding="utf-8")


def test_find_duplicate_titles_flags_within_site_duplicates(tmp_path, monkeypatch):
    monkeypatch.setattr(check_duplicate_titles, "REPO_ROOT", tmp_path)
    _write_page(tmp_path, "docs.aspose.org", "en/pdf/net/developer-guide/_index.md", "Developer Guide")
    _write_page(tmp_path, "docs.aspose.org", "en/words/net/developer-guide/_index.md", "Developer Guide")
    _write_page(tmp_path, "docs.aspose.org", "en/pdf/net/getting-started/_index.md", "Getting Started")

    dupes = check_duplicate_titles.find_duplicate_titles(content_root=tmp_path)
    assert "docs.aspose.org::Developer Guide" in dupes
    assert len(dupes["docs.aspose.org::Developer Guide"]) == 2
    assert "docs.aspose.org::Getting Started" not in dupes  # only 1 page


def test_find_duplicate_titles_does_not_cross_site_boundaries(tmp_path, monkeypatch):
    monkeypatch.setattr(check_duplicate_titles, "REPO_ROOT", tmp_path)
    _write_page(tmp_path, "docs.aspose.org", "en/pdf/net/_index.md", "Same Title")
    _write_page(tmp_path, "kb.aspose.org", "en/pdf/net/_index.md", "Same Title")

    dupes = check_duplicate_titles.find_duplicate_titles(content_root=tmp_path)
    assert dupes == {}  # 1 per site, never combined across sites


def test_find_duplicate_titles_skips_locale_variants(tmp_path, monkeypatch):
    monkeypatch.setattr(check_duplicate_titles, "REPO_ROOT", tmp_path)
    _write_page(tmp_path, "docs.aspose.org", "en/pdf/net/index.md", "English Title")
    _write_page(tmp_path, "docs.aspose.org", "en/pdf/net/index.ar.md", "English Title")

    dupes = check_duplicate_titles.find_duplicate_titles(content_root=tmp_path)
    assert dupes == {}  # index.ar.md excluded, only 1 real (non-locale) page


def test_find_duplicate_titles_excludes_reference_site_entirely(tmp_path, monkeypatch):
    monkeypatch.setattr(check_duplicate_titles, "REPO_ROOT", tmp_path)
    _write_page(tmp_path, "reference.aspose.org", "en/pdf/java/Document.md", "Document")
    _write_page(tmp_path, "reference.aspose.org", "en/words/java/Document.md", "Document")

    dupes = check_duplicate_titles.find_duplicate_titles(content_root=tmp_path)
    assert dupes == {}  # reference.aspose.org is not a checked site


def test_diff_against_baseline_only_returns_new_groups():
    current = {"docs.aspose.org::A": ["x", "y"], "docs.aspose.org::B": ["z", "w"]}
    baseline = {"docs.aspose.org::A": ["x", "y"]}
    new_groups = check_duplicate_titles.diff_against_baseline(current, baseline)
    assert new_groups == ["docs.aspose.org::B"]


def test_diff_against_baseline_resolved_group_is_not_new():
    current = {}  # the baseline's duplicate got fixed
    baseline = {"docs.aspose.org::A": ["x", "y"]}
    assert check_duplicate_titles.diff_against_baseline(current, baseline) == []


def test_write_and_load_baseline_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(check_duplicate_titles, "BASELINE_PATH", tmp_path / "baseline.json")
    data = {"docs.aspose.org::X": ["a.md", "b.md"]}
    check_duplicate_titles.write_baseline(data)
    assert check_duplicate_titles.load_baseline() == data


def test_load_baseline_missing_file_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(check_duplicate_titles, "BASELINE_PATH", tmp_path / "does_not_exist.json")
    assert check_duplicate_titles.load_baseline() == {}


def test_main_ci_mode_blocks_on_new_group(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(check_duplicate_titles, "CONTENT_ROOT", tmp_path)
    monkeypatch.setattr(check_duplicate_titles, "REPO_ROOT", tmp_path)
    baseline_path = tmp_path / "baseline.json"
    monkeypatch.setattr(check_duplicate_titles, "BASELINE_PATH", baseline_path)

    _write_page(tmp_path, "docs.aspose.org", "en/pdf/net/_index.md", "Duplicate Title")
    _write_page(tmp_path, "docs.aspose.org", "en/words/net/_index.md", "Duplicate Title")
    baseline_path.write_text("{}", encoding="utf-8")  # empty baseline -- this group is new

    monkeypatch.setattr(sys, "argv", ["check_duplicate_titles.py", "--mode", "ci"])
    exit_code = check_duplicate_titles.main()
    assert exit_code == 1
    assert "BLOCK" in capsys.readouterr().err


def test_main_ci_mode_passes_when_group_already_baselined(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(check_duplicate_titles, "CONTENT_ROOT", tmp_path)
    monkeypatch.setattr(check_duplicate_titles, "REPO_ROOT", tmp_path)
    baseline_path = tmp_path / "baseline.json"
    monkeypatch.setattr(check_duplicate_titles, "BASELINE_PATH", baseline_path)

    _write_page(tmp_path, "docs.aspose.org", "en/pdf/net/_index.md", "Duplicate Title")
    _write_page(tmp_path, "docs.aspose.org", "en/words/net/_index.md", "Duplicate Title")
    baseline_path.write_text(
        json.dumps({"docs.aspose.org::Duplicate Title": ["a", "b"]}), encoding="utf-8"
    )

    monkeypatch.setattr(sys, "argv", ["check_duplicate_titles.py", "--mode", "ci"])
    exit_code = check_duplicate_titles.main()
    assert exit_code == 0


def test_main_ci_mode_errors_without_baseline(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(check_duplicate_titles, "CONTENT_ROOT", tmp_path)
    monkeypatch.setattr(check_duplicate_titles, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(check_duplicate_titles, "BASELINE_PATH", tmp_path / "no_baseline.json")
    monkeypatch.setattr(sys, "argv", ["check_duplicate_titles.py", "--mode", "ci"])
    exit_code = check_duplicate_titles.main()
    assert exit_code == 2


def test_main_report_mode_always_exits_zero(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(check_duplicate_titles, "CONTENT_ROOT", tmp_path)
    monkeypatch.setattr(check_duplicate_titles, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["check_duplicate_titles.py", "--mode", "report"])
    exit_code = check_duplicate_titles.main()
    assert exit_code == 0
