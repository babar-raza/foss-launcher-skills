"""Tests for fix_ta_access.py — type_accuracy Access column repair."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from fix_ta_access import _fix_file, _load_writable_map, main


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def api_surface_dir(tmp_path: Path) -> Path:
    """Create a minimal knowledge directory with api_surface.json."""
    merged = tmp_path / "knowledge" / "cells" / "python" / "merged"
    merged.mkdir(parents=True)
    surface = [
        {
            "name": "AutoFilter",
            "properties": [
                {"name": "range", "writable": True},
                {"name": "sort_state", "writable": True},
                {"name": "filter_columns", "writable": False},  # read-only
            ],
        },
        {
            "name": "WorksheetProperties",
            "properties": [
                {"name": "name", "writable": True},
                {"name": "index", "writable": False},
            ],
        },
    ]
    (merged / "api_surface.json").write_text(json.dumps(surface), encoding="utf-8")
    return tmp_path


@pytest.fixture()
def ref_dir(tmp_path: Path) -> Path:
    p = tmp_path / "content" / "reference.aspose.org" / "en" / "cells" / "python"
    p.mkdir(parents=True)
    return p


# ---------------------------------------------------------------------------
# _load_writable_map
# ---------------------------------------------------------------------------

def test_load_writable_map_basic(api_surface_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(api_surface_dir)
    wmap = _load_writable_map("cells", "python")
    assert "AutoFilter" in wmap
    assert "range" in wmap["AutoFilter"]
    assert "sort_state" in wmap["AutoFilter"]
    assert "filter_columns" not in wmap["AutoFilter"]  # writable=False excluded


def test_load_writable_map_missing_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(FileNotFoundError, match="api_surface.json"):
        _load_writable_map("cells", "python")


# ---------------------------------------------------------------------------
# _fix_file — happy path
# ---------------------------------------------------------------------------

def test_fix_file_changes_writable_property(tmp_path: Path) -> None:
    content = textwrap.dedent("""\
        ## Properties

        | Name | Type | Access | Description |
        |------|------|--------|-------------|
        | `range` | `str` | Read | The auto-filter range |
        | `sort_state` | `obj` | Read | Current sort state |
        | `filter_columns` | `list` | Read | Filter column list |
    """)
    f = tmp_path / "AutoFilter.md"
    f.write_text(content, encoding="utf-8")

    writable_map = {
        "AutoFilter": {"range", "sort_state"},
        # filter_columns NOT in writable_map → should stay Read
    }

    changed = _fix_file(f, writable_map, dry_run=False)

    assert set(changed) == {"range", "sort_state"}
    result = f.read_text(encoding="utf-8")
    assert "| `range` | `str` | Read/Write | The auto-filter range |" in result
    assert "| `sort_state` | `obj` | Read/Write | Current sort state |" in result
    assert "| `filter_columns` | `list` | Read | Filter column list |" in result  # unchanged


# ---------------------------------------------------------------------------
# _fix_file — dry-run: no file writes
# ---------------------------------------------------------------------------

def test_fix_file_dry_run_no_write(tmp_path: Path) -> None:
    content = "| `range` | `str` | Read | desc |\n"
    f = tmp_path / "AutoFilter.md"
    f.write_text(content, encoding="utf-8")

    changed = _fix_file(f, {"AutoFilter": {"range"}}, dry_run=True)

    assert changed == ["range"]
    # File must NOT be modified in dry-run
    assert f.read_text(encoding="utf-8") == content


# ---------------------------------------------------------------------------
# _fix_file — already Read/Write is unchanged
# ---------------------------------------------------------------------------

def test_fix_file_already_readwrite_unchanged(tmp_path: Path) -> None:
    content = "| `range` | `str` | Read/Write | desc |\n"
    f = tmp_path / "AutoFilter.md"
    f.write_text(content, encoding="utf-8")

    changed = _fix_file(f, {"AutoFilter": {"range"}}, dry_run=False)

    assert changed == []
    assert f.read_text(encoding="utf-8") == content


# ---------------------------------------------------------------------------
# _fix_file — class not in writable_map → no changes
# ---------------------------------------------------------------------------

def test_fix_file_class_not_in_map(tmp_path: Path) -> None:
    content = "| `range` | `str` | Read | desc |\n"
    f = tmp_path / "AutoFilter.md"
    f.write_text(content, encoding="utf-8")

    changed = _fix_file(f, {}, dry_run=False)

    assert changed == []
    assert f.read_text(encoding="utf-8") == content


# ---------------------------------------------------------------------------
# _fix_file — property name not in writable set → unchanged
# ---------------------------------------------------------------------------

def test_fix_file_prop_not_writable_unchanged(tmp_path: Path) -> None:
    content = "| `filter_columns` | `list` | Read | desc |\n"
    f = tmp_path / "AutoFilter.md"
    f.write_text(content, encoding="utf-8")

    # Only range is writable, filter_columns is not
    changed = _fix_file(f, {"AutoFilter": {"range"}}, dry_run=False)

    assert changed == []
    assert "| Read |" in f.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# _fix_file — idempotent (running twice produces same result)
# ---------------------------------------------------------------------------

def test_fix_file_idempotent(tmp_path: Path) -> None:
    content = "| `range` | `str` | Read | desc |\n"
    f = tmp_path / "AutoFilter.md"
    f.write_text(content, encoding="utf-8")
    writable_map = {"AutoFilter": {"range"}}

    _fix_file(f, writable_map, dry_run=False)
    first_result = f.read_text(encoding="utf-8")

    _fix_file(f, writable_map, dry_run=False)
    second_result = f.read_text(encoding="utf-8")

    assert first_result == second_result
    assert "Read/Write" in first_result


# ---------------------------------------------------------------------------
# main() — integration test with real tmp filesystem
# ---------------------------------------------------------------------------

def test_main_dry_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:  # type: ignore[type-arg]
    # Set up knowledge
    merged = tmp_path / "knowledge" / "cells" / "python" / "merged"
    merged.mkdir(parents=True)
    surface = [{"name": "AutoFilter", "properties": [{"name": "range", "writable": True}]}]
    (merged / "api_surface.json").write_text(json.dumps(surface), encoding="utf-8")

    # Set up reference dir + file
    ref_dir = tmp_path / "content" / "reference.aspose.org" / "en" / "cells" / "python"
    ref_dir.mkdir(parents=True)
    md = ref_dir / "AutoFilter.md"
    original = "| `range` | `str` | Read | desc |\n"
    md.write_text(original, encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    rc = main(["--family", "cells", "--platform", "python", "--dry-run"])

    assert rc == 0
    captured = capsys.readouterr()
    assert "DRY-RUN" in captured.out
    assert "range" in captured.out
    # File must be unmodified
    assert md.read_text(encoding="utf-8") == original


def test_main_live(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    merged = tmp_path / "knowledge" / "cells" / "python" / "merged"
    merged.mkdir(parents=True)
    surface = [{"name": "AutoFilter", "properties": [{"name": "range", "writable": True}]}]
    (merged / "api_surface.json").write_text(json.dumps(surface), encoding="utf-8")

    ref_dir = tmp_path / "content" / "reference.aspose.org" / "en" / "cells" / "python"
    ref_dir.mkdir(parents=True)
    md = ref_dir / "AutoFilter.md"
    md.write_text("| `range` | `str` | Read | desc |\n", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    rc = main(["--family", "cells", "--platform", "python"])

    assert rc == 0
    assert "Read/Write" in md.read_text(encoding="utf-8")


def test_main_missing_knowledge(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:  # type: ignore[type-arg]
    monkeypatch.chdir(tmp_path)
    rc = main(["--family", "cells", "--platform", "python"])
    assert rc == 1
    assert "api_surface.json" in capsys.readouterr().err
