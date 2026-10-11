"""Tests for lib/example_verification/acquire.py (rollout step C3): a
faithful port of S-120's `_stage_readme_fixtures`/`_readme_fixture_names`
(readme_refresh_run.py:4874-4923). Includes a direct parity check against
the real S-120 functions (imported unchanged, never reimplemented) proving
byte-identical behavior for the same inputs -- the "legacy-adapter
equality" the stage's own promotion gate calls for, adapted to acquire.py.
"""
from __future__ import annotations

from pathlib import Path

import readme_refresh_run as rr

from lib.example_verification.acquire import readme_fixture_names, stage_fixtures


def test_readme_fixture_names_extracts_quoted_filenames():
    blocks = [("python", 'doc = Document("input.pdf")\nout = "result.pdf"\n')]
    names = readme_fixture_names(blocks)
    assert names == ["input.pdf", "result.pdf"]


def test_readme_fixture_names_bash_bare_tokens():
    blocks = [("bash", "my-tool convert input.docx output.pdf\n")]
    names = readme_fixture_names(blocks)
    assert "input.docx" in names
    assert "output.pdf" in names


def test_readme_fixture_names_deduplicates_preserving_first_order():
    blocks = [
        ("python", 'a = "input.pdf"\n'),
        ("python", 'b = "input.pdf"\nc = "other.pdf"\n'),
    ]
    names = readme_fixture_names(blocks)
    assert names == ["input.pdf", "other.pdf"]


def test_readme_fixture_names_ignores_dotfiles_and_extensionless():
    blocks = [("python", 'a = ".gitignore"\nb = "no_extension"\nc = "real.txt"\n')]
    names = readme_fixture_names(blocks)
    assert names == ["real.txt"]


def test_stage_fixtures_copies_matching_files(tmp_path):
    clone_cache = tmp_path / "clone"
    (clone_cache / "testdata").mkdir(parents=True)
    (clone_cache / "testdata" / "input.pdf").write_bytes(b"fake-pdf-bytes")
    work_dir = tmp_path / "work"
    work_dir.mkdir()

    result = stage_fixtures(work_dir, [("python", 'Document("input.pdf")')], clone_cache)
    assert result["staged"] == {"input.pdf": "testdata/input.pdf"}
    assert result["unresolved"] == []
    assert (work_dir / "input.pdf").read_bytes() == b"fake-pdf-bytes"


def test_stage_fixtures_reports_unresolved_names(tmp_path):
    clone_cache = tmp_path / "clone"
    clone_cache.mkdir()
    work_dir = tmp_path / "work"
    work_dir.mkdir()

    result = stage_fixtures(work_dir, [("python", 'Document("missing.pdf")')], clone_cache)
    assert result["staged"] == {}
    assert result["unresolved"] == ["missing.pdf"]


def test_stage_fixtures_never_follows_symlinks(tmp_path):
    clone_cache = tmp_path / "clone"
    clone_cache.mkdir()
    real_target = tmp_path / "outside.pdf"
    real_target.write_bytes(b"outside-bytes")
    link = clone_cache / "input.pdf"
    try:
        link.symlink_to(real_target)
    except OSError:
        import pytest
        pytest.skip("symlinks not permitted in this environment")
    work_dir = tmp_path / "work"
    work_dir.mkdir()

    result = stage_fixtures(work_dir, [("python", 'Document("input.pdf")')], clone_cache)
    assert result["staged"] == {}
    assert result["unresolved"] == ["input.pdf"]


def test_stage_fixtures_skips_search_in_venv_and_node_modules(tmp_path):
    clone_cache = tmp_path / "clone"
    (clone_cache / "node_modules").mkdir(parents=True)
    (clone_cache / "node_modules" / "input.pdf").write_bytes(b"wrong-one")
    (clone_cache / "real").mkdir()
    (clone_cache / "real" / "input.pdf").write_bytes(b"right-one")
    work_dir = tmp_path / "work"
    work_dir.mkdir()

    result = stage_fixtures(work_dir, [("python", 'Document("input.pdf")')], clone_cache)
    assert result["staged"] == {"input.pdf": "real/input.pdf"}
    assert (work_dir / "input.pdf").read_bytes() == b"right-one"


# --- Parity against the real, unmodified S-120 functions -------------------

def test_readme_fixture_names_parity_with_s120():
    cases = [
        [("python", 'Document("input.pdf")\nresult = "out.pdf"\n')],
        [("bash", "convert input.docx output.pdf --flag\n")],
        [("python", 'a = ".hidden"\nb = "noext"\nc = "real.json"\n')],
        [("python", 'x = "a.pdf"\n'), ("python", 'y = "a.pdf"\nz = "b.pdf"\n')],
        [("java", "// no quoted filenames here at all\n")],
    ]
    for blocks in cases:
        assert readme_fixture_names(blocks) == rr._readme_fixture_names(blocks), blocks


def test_stage_fixtures_parity_with_s120(tmp_path):
    clone_cache = tmp_path / "clone"
    (clone_cache / "testdata").mkdir(parents=True)
    (clone_cache / "testdata" / "input.pdf").write_bytes(b"bytes")
    (clone_cache / "node_modules").mkdir()
    (clone_cache / "node_modules" / "input.pdf").write_bytes(b"wrong")

    blocks = [("python", 'Document("input.pdf")\nother = "missing.pdf"\n')]

    work_a = tmp_path / "work_a"
    work_a.mkdir()
    work_b = tmp_path / "work_b"
    work_b.mkdir()

    ours = stage_fixtures(work_a, blocks, clone_cache)
    theirs = rr._stage_readme_fixtures(work_b, blocks, clone_cache)
    assert ours == theirs
    assert (work_a / "input.pdf").read_bytes() == (work_b / "input.pdf").read_bytes()
