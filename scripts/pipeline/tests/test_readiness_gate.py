"""Tests for readiness_gate.py — G-05 (proof index completeness)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Make the pipeline package importable when running from repo root.
_PIPELINE_DIR = Path(__file__).resolve().parent.parent
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))

import readiness_gate  # noqa: E402


def _make_index(tmp_path: Path, entries: list[dict]) -> Path:
    index_file = tmp_path / "reports" / "proofs" / "INDEX.json"
    index_file.parent.mkdir(parents=True, exist_ok=True)
    index_file.write_text(json.dumps(entries, indent=2), encoding="utf-8")
    return index_file


def _make_bundle_dir(tmp_path: Path, name: str) -> Path:
    d = tmp_path / "reports" / "proofs" / name
    d.mkdir(parents=True, exist_ok=True)
    return d


@pytest.fixture(autouse=True)
def _reset_repo_root(tmp_path):
    """Point readiness_gate at tmp_path for every test; restore afterwards."""
    readiness_gate.configure(repo_root=tmp_path)
    yield
    readiness_gate.configure(repo_root=None)


# ---------------------------------------------------------------------------
# G-05 tests
# ---------------------------------------------------------------------------

def test_g05_skip_no_proofs_dir(tmp_path):
    """reports/proofs/ absent → SKIP."""
    result = readiness_gate.gate_g05_proof_index()
    assert result.status == readiness_gate.STATUS_SKIP


def test_g05_fail_missing_index(tmp_path):
    """proofs/ exists but INDEX.json is absent → FAIL."""
    (tmp_path / "reports" / "proofs").mkdir(parents=True)
    result = readiness_gate.gate_g05_proof_index()
    assert result.status == readiness_gate.STATUS_FAIL
    assert "INDEX.json missing" in result.detail


def test_g05_pass_all_registered(tmp_path):
    """All dirs are registered in INDEX.json → PASS."""
    _make_bundle_dir(tmp_path, "20260101-run")
    _make_bundle_dir(tmp_path, "20260102-run")
    _make_index(tmp_path, [
        {"bundle_id": "20260101-run", "path": "reports/proofs/20260101-run/"},
        {"bundle_id": "20260102-run", "path": "reports/proofs/20260102-run/"},
    ])
    result = readiness_gate.gate_g05_proof_index()
    assert result.status == readiness_gate.STATUS_PASS
    assert "2 bundles registered" in result.detail


def test_g05_fail_unregistered_dir(tmp_path):
    """One dir missing from INDEX.json → FAIL with the missing name listed."""
    _make_bundle_dir(tmp_path, "20260101-run")
    _make_bundle_dir(tmp_path, "20260102-unregistered")
    _make_index(tmp_path, [
        {"bundle_id": "20260101-run", "path": "reports/proofs/20260101-run/"},
    ])
    result = readiness_gate.gate_g05_proof_index()
    assert result.status == readiness_gate.STATUS_FAIL
    assert "20260102-unregistered" in result.detail
    assert "1 unregistered" in result.detail


def test_g05_ignore_files_in_proofs_dir(tmp_path):
    """Files (not dirs) in reports/proofs/ are not counted as bundles."""
    _make_bundle_dir(tmp_path, "20260101-run")
    # Create a stray file alongside the bundle dir
    stray = tmp_path / "reports" / "proofs" / "stray.txt"
    stray.write_text("ignore me", encoding="utf-8")
    _make_index(tmp_path, [
        {"bundle_id": "20260101-run", "path": "reports/proofs/20260101-run/"},
    ])
    result = readiness_gate.gate_g05_proof_index()
    assert result.status == readiness_gate.STATUS_PASS


def test_g05_pass_empty_proofs_dir(tmp_path):
    """proofs/ exists, INDEX.json is present but empty, no dirs → PASS."""
    (tmp_path / "reports" / "proofs").mkdir(parents=True)
    _make_index(tmp_path, [])
    result = readiness_gate.gate_g05_proof_index()
    assert result.status == readiness_gate.STATUS_PASS
