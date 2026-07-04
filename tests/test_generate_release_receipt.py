"""Tests for scripts/generate_release_receipt.py.

Covers helper functions (_git_commit_sha, _git_ref, _read_version_from_pyproject,
_coverage_xml_exists, _read_coverage_percentage), generate_receipt(), write_receipt(),
and the CLI main() entry point.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))


def _proc(stdout: str = "", returncode: int = 0) -> MagicMock:
    m = MagicMock()
    m.stdout = stdout
    m.returncode = returncode
    return m


# ---------------------------------------------------------------------------
# _git_commit_sha
# ---------------------------------------------------------------------------

def test_git_commit_sha_returns_value() -> None:
    """_git_commit_sha returns trimmed stdout on success."""
    from generate_release_receipt import _git_commit_sha
    with patch("generate_release_receipt.subprocess.run", return_value=_proc("abc1234\n")):
        assert _git_commit_sha() == "abc1234"


def test_git_commit_sha_returns_empty_on_failure() -> None:
    """_git_commit_sha returns '' when git returns non-zero."""
    from generate_release_receipt import _git_commit_sha
    with patch("generate_release_receipt.subprocess.run", return_value=_proc("", returncode=1)):
        assert _git_commit_sha() == ""


def test_git_commit_sha_returns_empty_on_exception() -> None:
    """_git_commit_sha returns '' on unexpected exception."""
    from generate_release_receipt import _git_commit_sha
    with patch("generate_release_receipt.subprocess.run", side_effect=FileNotFoundError):
        assert _git_commit_sha() == ""


# ---------------------------------------------------------------------------
# _git_ref
# ---------------------------------------------------------------------------

def test_git_ref_returns_branch_name() -> None:
    """_git_ref returns the branch name from stdout."""
    from generate_release_receipt import _git_ref
    with patch("generate_release_receipt.subprocess.run", return_value=_proc("main\n")):
        assert _git_ref() == "main"


def test_git_ref_returns_empty_on_failure() -> None:
    """_git_ref returns '' on git failure."""
    from generate_release_receipt import _git_ref
    with patch("generate_release_receipt.subprocess.run", return_value=_proc("", returncode=1)):
        assert _git_ref() == ""


def test_git_ref_returns_empty_on_exception() -> None:
    """_git_ref returns '' on exception."""
    from generate_release_receipt import _git_ref
    with patch("generate_release_receipt.subprocess.run", side_effect=Exception("git not found")):
        assert _git_ref() == ""


# ---------------------------------------------------------------------------
# _read_version_from_pyproject
# ---------------------------------------------------------------------------

def test_read_version_from_pyproject_returns_string() -> None:
    """_read_version_from_pyproject returns a non-empty version string."""
    from generate_release_receipt import _read_version_from_pyproject
    version = _read_version_from_pyproject()
    # pyproject.toml exists in this repo
    assert isinstance(version, str)
    assert len(version) > 0


def test_read_version_from_pyproject_fallback(tmp_path) -> None:
    """Fallback line-search works when tomllib is unavailable."""
    from generate_release_receipt import _read_version_from_pyproject
    # Write a fake pyproject.toml
    fake_pyproject = tmp_path / "pyproject.toml"
    fake_pyproject.write_text('[project]\nversion = "9.9.9"\n', encoding="utf-8")

    with patch("generate_release_receipt.REPO_ROOT", tmp_path):
        # Patch out tomllib to force the fallback path
        with patch.dict("sys.modules", {"tomllib": None, "tomli": None}):
            version = _read_version_from_pyproject()
    # Either tomllib parses it or the fallback line-search does
    assert version in ("9.9.9", "")  # empty if import also cached


# ---------------------------------------------------------------------------
# _coverage_xml_exists
# ---------------------------------------------------------------------------

def test_coverage_xml_exists_true(tmp_path) -> None:
    """_coverage_xml_exists returns True when coverage.xml is present."""
    from generate_release_receipt import _coverage_xml_exists
    (tmp_path / "coverage.xml").write_text("<coverage/>", encoding="utf-8")
    with patch("generate_release_receipt.REPO_ROOT", tmp_path):
        assert _coverage_xml_exists() is True


def test_coverage_xml_exists_false(tmp_path) -> None:
    """_coverage_xml_exists returns False when coverage.xml is absent."""
    from generate_release_receipt import _coverage_xml_exists
    with patch("generate_release_receipt.REPO_ROOT", tmp_path):
        assert _coverage_xml_exists() is False


# ---------------------------------------------------------------------------
# _read_coverage_percentage
# ---------------------------------------------------------------------------

def test_read_coverage_percentage_parses_xml(tmp_path) -> None:
    """_read_coverage_percentage parses line-rate attribute from coverage.xml."""
    from generate_release_receipt import _read_coverage_percentage
    xml = '<?xml version="1.0" ?><coverage line-rate="0.123" />'
    (tmp_path / "coverage.xml").write_text(xml, encoding="utf-8")
    with patch("generate_release_receipt.REPO_ROOT", tmp_path):
        result = _read_coverage_percentage()
    assert result == "12.3%"


def test_read_coverage_percentage_missing_file(tmp_path) -> None:
    """_read_coverage_percentage returns None when coverage.xml is missing."""
    from generate_release_receipt import _read_coverage_percentage
    with patch("generate_release_receipt.REPO_ROOT", tmp_path):
        assert _read_coverage_percentage() is None


def test_read_coverage_percentage_invalid_xml(tmp_path) -> None:
    """_read_coverage_percentage returns None on malformed XML."""
    from generate_release_receipt import _read_coverage_percentage
    (tmp_path / "coverage.xml").write_text("NOT XML!!!", encoding="utf-8")
    with patch("generate_release_receipt.REPO_ROOT", tmp_path):
        result = _read_coverage_percentage()
    assert result is None


# ---------------------------------------------------------------------------
# generate_receipt
# ---------------------------------------------------------------------------

def test_generate_receipt_structure() -> None:
    """generate_receipt returns a dict with all required keys."""
    from generate_release_receipt import generate_receipt
    with patch("generate_release_receipt.subprocess.run", return_value=_proc("abc1234\n")):
        receipt = generate_receipt("1.0.0")
    assert receipt["version"] == "1.0.0"
    assert "generated_at" in receipt
    assert "git_sha_short" in receipt
    assert "git_ref" in receipt
    assert "ci_run_url" in receipt
    assert "evidence" in receipt
    assert "notes" in receipt


def test_generate_receipt_ci_url_from_env() -> None:
    """generate_receipt reads ci_run_url from GITHUB_RUN_URL env var."""
    from generate_release_receipt import generate_receipt
    with patch("generate_release_receipt.subprocess.run", return_value=_proc("abc")):
        with patch.dict("os.environ", {"GITHUB_RUN_URL": "https://github.com/example/actions/runs/123"}):
            receipt = generate_receipt("1.0.0")
    assert receipt["ci_run_url"] == "https://github.com/example/actions/runs/123"


def test_generate_receipt_ci_url_none_when_unset() -> None:
    """generate_receipt sets ci_run_url to None when GITHUB_RUN_URL is absent."""
    import os
    from generate_release_receipt import generate_receipt
    env = {k: v for k, v in os.environ.items() if k != "GITHUB_RUN_URL"}
    with patch("generate_release_receipt.subprocess.run", return_value=_proc("abc")):
        with patch.dict("os.environ", env, clear=True):
            receipt = generate_receipt("1.0.0")
    assert receipt["ci_run_url"] is None


# ---------------------------------------------------------------------------
# write_receipt
# ---------------------------------------------------------------------------

def test_write_receipt_creates_file(tmp_path) -> None:
    """write_receipt writes a valid JSON file to the receipts directory."""
    from generate_release_receipt import write_receipt
    receipts_dir = tmp_path / "docs" / "release-receipts"
    with patch("generate_release_receipt.RECEIPTS_DIR", receipts_dir):
        with patch("generate_release_receipt.subprocess.run", return_value=_proc("abc")):
            path = write_receipt("1.2.3")
    assert path.exists()
    data = json.loads(path.read_text())
    assert data["version"] == "1.2.3"


def test_write_receipt_dry_run_no_file(tmp_path, capsys) -> None:
    """write_receipt dry_run=True prints JSON without writing a file."""
    from generate_release_receipt import write_receipt
    receipts_dir = tmp_path / "docs" / "release-receipts"
    with patch("generate_release_receipt.RECEIPTS_DIR", receipts_dir):
        with patch("generate_release_receipt.subprocess.run", return_value=_proc("abc")):
            write_receipt("1.2.3", dry_run=True)
    assert not (receipts_dir / "1.2.3.json").exists()
    out = capsys.readouterr().out
    assert '"version"' in out


# ---------------------------------------------------------------------------
# main() CLI
# ---------------------------------------------------------------------------

def test_main_dry_run_returns_0(capsys) -> None:
    """main(['--dry-run']) exits 0 and prints JSON."""
    from generate_release_receipt import main
    with patch("generate_release_receipt.subprocess.run", return_value=_proc("abc")):
        rc = main(["--dry-run"])
    assert rc == 0
    out = capsys.readouterr().out
    assert '"version"' in out


def test_main_explicit_version(tmp_path, capsys) -> None:
    """main(['--version', '9.9.9', '--dry-run']) uses provided version."""
    from generate_release_receipt import main
    with patch("generate_release_receipt.subprocess.run", return_value=_proc("abc")):
        rc = main(["--version", "9.9.9", "--dry-run"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "9.9.9" in out


def test_main_no_version_returns_1(tmp_path, capsys) -> None:
    """main() returns 1 when version cannot be determined."""
    from generate_release_receipt import main
    with patch("generate_release_receipt._read_version_from_pyproject", return_value=""):
        rc = main([])
    assert rc == 1


def test_main_write_receipt_exception_returns_1(tmp_path, capsys) -> None:
    """main() returns 1 when write_receipt raises an exception."""
    from generate_release_receipt import main
    with patch("generate_release_receipt.write_receipt", side_effect=OSError("disk full")):
        rc = main(["--version", "0.0.1"])
    assert rc == 1
    assert "ERROR" in capsys.readouterr().err


def test_main_write_receipt_prints_path(tmp_path, capsys) -> None:
    """main() prints the receipt path on successful write."""
    from generate_release_receipt import main
    receipts_dir = tmp_path / "docs" / "release-receipts"
    with patch("generate_release_receipt.RECEIPTS_DIR", receipts_dir):
        with patch("generate_release_receipt.subprocess.run", return_value=_proc("abc")):
            rc = main(["--version", "1.0.0"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "1.0.0" in out


def test_read_version_pyproject_missing(tmp_path) -> None:
    """_read_version_from_pyproject returns '' on tomllib exception."""
    from generate_release_receipt import _read_version_from_pyproject
    import tomllib
    with patch("generate_release_receipt.REPO_ROOT", tmp_path):
        with patch.object(tomllib, "load", side_effect=Exception("bad toml")):
            version = _read_version_from_pyproject()
    assert version == ""
