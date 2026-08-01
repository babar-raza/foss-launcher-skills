"""
Tests for commands/ops/registry_backfill.py (Mission
MT018-2026-08-01-PACKAGE-IDENTITY-COVERAGE, TC-MT018-06).

The backfill orchestrator: manifest-extract -> naming-convention-guess ->
search-fallback-with-corroboration -> honest unpublished fallback. All
tests use fixture repos + injected fetch -- zero live network calls.
"""

import json
import sys
from pathlib import Path

import pytest

_PIPELINE_ROOT = Path(__file__).resolve().parents[1]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

import commands.ops.registry_backfill as sut
from package_registries import FetchResponse


@pytest.fixture(autouse=True)
def isolate_repo(tmp_path):
    sut.configure(repo_root=tmp_path)
    yield tmp_path
    sut.configure(repo_root=None)


def _fake_fetch_by_url(mapping: dict, default_status: int = 404):
    def _fetch(url: str):
        for substr, (status_code, body) in mapping.items():
            if substr in url:
                return FetchResponse(status_code=status_code, body=body)
        return FetchResponse(status_code=default_status, body=b"")
    return _fetch


def _write_pyproject(tmp_path: Path, family: str, platform: str, name: str) -> None:
    d = tmp_path / "runs" / ".clone_cache" / f"aspose_{family}_{platform}"
    d.mkdir(parents=True, exist_ok=True)
    (d / "pyproject.toml").write_text(
        f'[project]\nname = "{name}"\nversion = "1.0.0"\n', encoding="utf-8"
    )


def test_manifest_extracted_name_takes_priority_when_it_resolves(tmp_path):
    _write_pyproject(tmp_path, "cells", "python", "aspose-cells-foss")
    fetch = _fake_fetch_by_url({
        "pypi/aspose-cells-foss/json": (200, b'{"info": {"author": "Aspose", "project_urls": {}}}'),
    })
    entry = sut.backfill_entry("cells", "python", fetch=fetch)
    assert entry["candidate"]["name"] == "aspose-cells-foss"
    assert entry["verification"]["published"] is True
    assert entry["verification"]["identity_basis"] == "manifest-extracted"
    assert entry["scout_source"] == "package_manifest.py:python"


def test_falls_back_to_naming_convention_when_manifest_absent(tmp_path):
    # No clone cache dir at all -- manifest extraction yields nothing.
    fetch = _fake_fetch_by_url({
        "pypi/aspose-barcode-foss/json": (200, b'{"info": {"author": "Aspose"}}'),
    })
    entry = sut.backfill_entry("barcode", "python", fetch=fetch)
    assert entry["candidate"]["name"] == "aspose-barcode-foss"
    assert entry["verification"]["identity_basis"] == "foss-convention-match"
    assert entry["scout_source"] == "naming-convention-fallback"


def test_search_fallback_finds_non_conforming_name_with_corroboration(tmp_path):
    """Real note/python case: manifest gives nothing, convention guess
    (aspose-note-foss) 404s, but search() finds aspose-note and
    corroborates it via project_url."""
    fetch = _fake_fetch_by_url({
        "pypi/aspose-note-foss/json": (404, b""),
        "pypi/aspose-note/json": (
            200,
            b'{"info": {"author": "Aspose", "project_urls": '
            b'{"Repository": "https://github.com/aspose-note-foss/x"}}}',
        ),
        "pypi/aspose_note/json": (404, b""),
        "pypi/asposenote/json": (404, b""),
    })
    entry = sut.backfill_entry("note", "python", fetch=fetch)
    assert entry["candidate"]["name"] == "aspose-note"
    assert entry["verification"]["identity_basis"] == "corroborated-non-convention-match"
    assert entry["verification"]["published"] is True


def test_search_hit_without_corroboration_is_rejected(tmp_path):
    """Real page/python case: the naming-convention guess doesn't resolve,
    and a search hit (the unrelated commercial aspose-page) has no foss
    substring and no matching project_url -- must NOT be accepted."""
    fetch = _fake_fetch_by_url({
        "pypi/aspose-page-foss/json": (404, b""),
        "pypi/aspose-page/json": (
            200,
            b'{"info": {"author": "SomeCommercialVendor", "home_page": "https://products.aspose.com/page/python-net/"}}',
        ),
        "pypi/aspose_page/json": (404, b""),
        "pypi/asposepage/json": (404, b""),
    })
    entry = sut.backfill_entry("page", "python", fetch=fetch)
    assert entry["verification"]["published"] is False
    assert entry["verification"]["identity_basis"] is None


def test_nuget_cpp_search_excludes_net_only_matches(tmp_path):
    """Real email/cpp case: search for 'aspose email' surfaces the .NET
    package (Aspose.Email.Foss, which DOES contain 'foss'), but it must be
    excluded for the cpp platform since it isn't cpp-specific."""
    search_body = b'{"data": [{"id": "Aspose.Email.Foss"}]}'
    flat_body = b'{"versions": ["26.7.0"]}'
    fetch = _fake_fetch_by_url({
        "azuresearch": (200, search_body),
        "aspose.email.cpp.foss": (404, b""),
        "aspose.email.foss": (200, flat_body),
        "registration5-semver1": (503, b""),
    })
    entry = sut.backfill_entry("email", "cpp", fetch=fetch)
    assert entry["verification"]["published"] is False


def test_unpublished_entry_records_best_available_candidate_name(tmp_path):
    fetch = _fake_fetch_by_url({})  # everything 404s
    entry = sut.backfill_entry("tex", "python", fetch=fetch)
    assert entry["verification"]["published"] is False
    assert entry["candidate"]["name"] == "aspose-tex-foss"  # convention guess, since no manifest
    assert entry["verification"]["identity_basis"] is None
    assert entry["verification"]["evidence_note"]  # never silently empty


def test_go_modules_uses_module_path_key(tmp_path):
    fetch = _fake_fetch_by_url({})
    entry = sut.backfill_entry("cells", "go", fetch=fetch)
    assert "module_path" in entry["candidate"]
    assert "name" not in entry["candidate"]


def test_java_platform_returns_none_out_of_scope(tmp_path):
    assert sut.backfill_entry("cells", "java", fetch=lambda url: None) is None


def test_write_entries_merges_into_existing_registry(tmp_path):
    registry_path = tmp_path / "data" / "package_registry.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(json.dumps({"cells": {"java": {"registry_type": "maven"}}}), encoding="utf-8")

    sut.write_entries({"cells": {"net": {"registry_type": "nuget"}}})
    data = json.loads(registry_path.read_text(encoding="utf-8"))
    assert data["cells"]["java"]["registry_type"] == "maven"  # untouched
    assert data["cells"]["net"]["registry_type"] == "nuget"  # merged in


def test_write_entries_is_atomic_no_tmp_file_left_behind(tmp_path):
    registry_path = tmp_path / "data" / "package_registry.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text("{}", encoding="utf-8")

    sut.write_entries({"words": {"net": {"registry_type": "nuget"}}})
    assert not (tmp_path / "data" / "package_registry.json.tmp").exists()
    assert registry_path.is_file()


def test_cli_dry_run_does_not_write(tmp_path, capsys):
    registry_path = tmp_path / "data" / "package_registry.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text("{}", encoding="utf-8")

    exit_code = sut.main(["--only", "tex/python"])
    assert exit_code == 0
    assert json.loads(registry_path.read_text(encoding="utf-8")) == {}
    captured = capsys.readouterr()
    assert "DRY-RUN" in captured.out
