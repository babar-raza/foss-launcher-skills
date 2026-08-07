"""Tests for check_media_asset_size.py.

Reproduces the actual incidents this check exists to prevent: an oversized
canonical PNG dropped straight into static/media/ (found live 2026-08-06,
static/media/email/*, and again 2026-08-07, static/media/html/* and
static/media/page/*), reaching git history because nothing blocked it before
S-119's own compression skill got a chance to run.
"""
from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_HERE))

from checks import check_media_asset_size as cmas  # noqa: E402


def _write_file(path: Path, size: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\0" * size)
    return path


def test_no_violations_when_under_budget(tmp_path):
    _write_file(tmp_path / "static/media/pdf/python/icon.png", 500_000)

    violations = cmas.find_oversized(["static/media/pdf/python/icon.png"], repo_root=tmp_path)

    assert violations == []


def test_flags_over_budget_png(tmp_path):
    over_size = cmas._cfg_max_bytes + 1
    _write_file(tmp_path / "static/media/pdf/python/icon.png", over_size)

    violations = cmas.find_oversized(["static/media/pdf/python/icon.png"], repo_root=tmp_path)

    assert violations == [("static/media/pdf/python/icon.png", over_size)]


def test_flags_over_budget_webp(tmp_path):
    over_size = cmas._cfg_max_bytes + 12345
    _write_file(tmp_path / "static/media/email/cpp/banner.webp", over_size)

    violations = cmas.find_oversized(["static/media/email/cpp/banner.webp"], repo_root=tmp_path)

    assert violations == [("static/media/email/cpp/banner.webp", over_size)]


def test_ignores_files_outside_static_media(tmp_path):
    _write_file(tmp_path / "static/other/big.png", cmas._cfg_max_bytes + 1)

    violations = cmas.find_oversized(["static/other/big.png"], repo_root=tmp_path)

    assert violations == []


def test_ignores_non_image_files_under_static_media(tmp_path):
    _write_file(tmp_path / "static/media/pdf/python/README.txt", cmas._cfg_max_bytes + 1)

    violations = cmas.find_oversized(["static/media/pdf/python/README.txt"], repo_root=tmp_path)

    assert violations == []


def test_ignores_staged_deletion_no_longer_on_disk(tmp_path):
    # A staged deletion still appears in `git diff --cached --name-only`, but
    # the file is gone from the working tree -- nothing to measure, not a
    # violation.
    violations = cmas.find_oversized(["static/media/pdf/python/icon.png"], repo_root=tmp_path)

    assert violations == []


def test_backslash_paths_normalized(tmp_path):
    # Windows git status/diff output can use backslashes.
    over_size = cmas._cfg_max_bytes + 1
    _write_file(tmp_path / "static/media/pdf/python/icon.png", over_size)

    violations = cmas.find_oversized([r"static\media\pdf\python\icon.png"], repo_root=tmp_path)

    assert violations == [("static/media/pdf/python/icon.png", over_size)]


def test_main_exit_code_and_message(tmp_path, monkeypatch, capsys):
    over_size = cmas._cfg_max_bytes + 1
    _write_file(tmp_path / "static/media/pdf/python/icon.png", over_size)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cmas, "_REPO_ROOT", tmp_path)

    exit_code = cmas.main(["--files", "static/media/pdf/python/icon.png"])

    assert exit_code == 1
    out = capsys.readouterr().out
    assert "static/media/pdf/python/icon.png" in out
    assert "S-119" in out


def test_main_exit_zero_when_clean(tmp_path, monkeypatch, capsys):
    _write_file(tmp_path / "static/media/pdf/python/icon.png", 500_000)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cmas, "_REPO_ROOT", tmp_path)

    exit_code = cmas.main(["--files", "static/media/pdf/python/icon.png"])

    assert exit_code == 0
    assert capsys.readouterr().out == ""
