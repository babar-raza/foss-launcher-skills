"""Unit tests for validate_evidence_bundle.py (checks 1–10)."""

import hashlib
import io
import json
import os
import zipfile

import pytest

# Locate the fixtures directory relative to this test file.
FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "evidence_bundles")
VALID_MINIMAL = os.path.join(FIXTURES_DIR, "valid_minimal.zip")
MISMATCHED_HEAD = os.path.join(FIXTURES_DIR, "mismatched_head.zip")
MISSING_TASKCARD_STATE = os.path.join(FIXTURES_DIR, "missing_taskcard_state.zip")

from scripts.pipeline.commands.ops.validate_evidence_bundle import (
    check_bundle_validation_exists,
    check_checksums_file_exists,
    check_final_verdict_exists,
    check_head_consistency,
    check_manifest_exists,
    check_manifest_files_present,
    check_no_open_taskcards,
    check_taskcard_terminal_status,
    check_zip_stats_consistent,
    validate,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_zip(files: dict[str, bytes | str], path: str | None = None) -> str:
    """Write an in-memory ZIP to *path* (or a temp file) and return the path."""
    if path is None:
        import tempfile
        fd, path = tempfile.mkstemp(suffix=".zip")
        os.close(fd)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            if isinstance(content, str):
                content = content.encode()
            zf.writestr(name, content)
    return path


def _open(path: str) -> zipfile.ZipFile:
    return zipfile.ZipFile(path, "r")


# ---------------------------------------------------------------------------
# Test 1: valid_minimal.zip fixture — all 10 checks pass (checksums WARN only)
# ---------------------------------------------------------------------------

def test_valid_bundle(tmp_path):
    result = validate(VALID_MINIMAL)
    assert result["overall"] == "PASS"
    assert result["fail_count"] == 0
    assert result["total_checks"] == 10
    # checksums WARN is allowed
    statuses = {c["check"]: c["status"] for c in result["checks"]}
    assert statuses["zip_readable"] == "PASS"
    assert statuses["manifest_exists"] == "PASS"
    assert statuses["bundle_validation_exists"] == "PASS"
    assert statuses["head_consistency"] == "PASS"
    assert statuses["no_open_taskcards"] == "PASS"
    assert statuses["final_verdict_exists"] == "PASS"
    assert statuses["taskcard_terminal_status"] == "PASS"
    assert statuses["checksums_file_exists"] == "WARN"


# ---------------------------------------------------------------------------
# Test 2: missing manifest → manifest_exists FAIL
# ---------------------------------------------------------------------------

def test_missing_manifest(tmp_path):
    path = _make_zip({
        "bundle-validation.json": json.dumps({"head": "a" * 40}),
        "00-final-verdict.md": "# verdict\nHEAD: " + "a" * 40,
        "taskcard-state.json": json.dumps({"TC-01": "COMPLETE"}),
    }, str(tmp_path / "no_manifest.zip"))
    with _open(path) as zf:
        r = check_manifest_exists(zf)
    assert r["status"] == "FAIL"


# ---------------------------------------------------------------------------
# Test 3: missing 00-final-verdict.md → final_verdict_exists FAIL
# ---------------------------------------------------------------------------

def test_missing_final_verdict(tmp_path):
    path = _make_zip({
        "sprint-manifest.json": json.dumps({"head": "a" * 40, "files": []}),
        "bundle-validation.json": json.dumps({}),
        "taskcard-state.json": json.dumps({"TC-01": "COMPLETE"}),
    }, str(tmp_path / "no_verdict.zip"))
    with _open(path) as zf:
        r = check_final_verdict_exists(zf)
    assert r["status"] == "FAIL"


# ---------------------------------------------------------------------------
# Test 4: mismatched_head.zip → head_consistency FAIL
# ---------------------------------------------------------------------------

def test_head_inconsistency():
    with _open(MISMATCHED_HEAD) as zf:
        r = check_head_consistency(zf)
    assert r["status"] == "FAIL"
    assert "Multiple HEAD SHAs" in r["detail"]


# ---------------------------------------------------------------------------
# Test 5: flat taskcard format with PROPOSED → no_open_taskcards FAIL
# ---------------------------------------------------------------------------

def test_open_taskcard_flat(tmp_path):
    path = _make_zip({
        "taskcard-state.json": json.dumps({"T-1": "PROPOSED", "T-2": "COMPLETE"}),
        "sprint-manifest.json": json.dumps({"head": "a" * 40, "files": []}),
        "bundle-validation.json": json.dumps({}),
        "00-final-verdict.md": "# v",
    }, str(tmp_path / "flat_proposed.zip"))
    with _open(path) as zf:
        r = check_no_open_taskcards(zf)
    assert r["status"] == "FAIL"
    assert "T-1=PROPOSED" in r["detail"]


# ---------------------------------------------------------------------------
# Test 6: nested taskcard format with PROPOSED → no_open_taskcards FAIL
#   (tests the 2a bug fix — previously this would PASS incorrectly)
# ---------------------------------------------------------------------------

def test_open_taskcard_nested(tmp_path):
    state = {
        "sprint": "test-sprint",
        "taskcards": [
            {"id": "T-1", "status": "PROPOSED"},
            {"id": "T-2", "status": "CLOSED_VERIFIED"},
        ],
        "open_taskcards": [],
    }
    path = _make_zip({
        "state/taskcard-state.json": json.dumps(state),
        "sprint-manifest.json": json.dumps({"head": "a" * 40, "files": []}),
        "bundle-validation.json": json.dumps({}),
        "00-final-verdict.md": "# v",
    }, str(tmp_path / "nested_proposed.zip"))
    with _open(path) as zf:
        r = check_no_open_taskcards(zf)
    assert r["status"] == "FAIL"
    assert "T-1=PROPOSED" in r["detail"]


# ---------------------------------------------------------------------------
# Test 7: ZIP stats mismatch → zip_stats_consistent FAIL
# ---------------------------------------------------------------------------

def test_zip_stats_mismatch(tmp_path):
    wrong_size = 999999
    wrong_sha = "0" * 64
    bv = {"final_zip_size_bytes": wrong_size, "final_zip_sha256": wrong_sha}
    path = _make_zip({
        "sprint-manifest.json": json.dumps({"head": "a" * 40, "files": []}),
        "bundle-validation.json": json.dumps(bv),
        "00-final-verdict.md": "# v",
        "taskcard-state.json": json.dumps({"TC-01": "COMPLETE"}),
    }, str(tmp_path / "wrong_stats.zip"))
    with _open(path) as zf:
        r = check_zip_stats_consistent(path, zf)
    assert r["status"] == "FAIL"
    assert "mismatch" in r["detail"].lower()


# ---------------------------------------------------------------------------
# Test 8: sidecar pattern (null stats) → zip_stats_consistent PASS
# ---------------------------------------------------------------------------

def test_zip_stats_sidecar(tmp_path):
    bv = {"final_zip_size_bytes": None, "final_zip_sha256": None}
    path = _make_zip({
        "sprint-manifest.json": json.dumps({"head": "a" * 40, "files": []}),
        "bundle-validation.json": json.dumps(bv),
        "00-final-verdict.md": "# v",
        "taskcard-state.json": json.dumps({"TC-01": "COMPLETE"}),
    }, str(tmp_path / "sidecar.zip"))
    with _open(path) as zf:
        r = check_zip_stats_consistent(path, zf)
    assert r["status"] == "PASS"
    assert "sidecar" in r["detail"].lower()


# ---------------------------------------------------------------------------
# Test 9: CLOSED_SCAFFOLDED taskcard → taskcard_terminal_status FAIL
# ---------------------------------------------------------------------------

def test_non_terminal_taskcard(tmp_path):
    state = {
        "sprint": "test",
        "taskcards": [
            {"id": "T-B1", "status": "CLOSED_SCAFFOLDED"},
            {"id": "T-A1", "status": "CLOSED_VERIFIED"},
        ],
    }
    path = _make_zip({
        "state/taskcard-state.json": json.dumps(state),
        "sprint-manifest.json": json.dumps({"head": "a" * 40, "files": []}),
        "bundle-validation.json": json.dumps({}),
        "00-final-verdict.md": "# v",
    }, str(tmp_path / "scaffolded.zip"))
    with _open(path) as zf:
        r = check_taskcard_terminal_status(zf)
    assert r["status"] == "FAIL"
    assert "T-B1=CLOSED_SCAFFOLDED" in r["detail"]


# ---------------------------------------------------------------------------
# Test 10: missing checksums file → checksums_file_exists WARN (not FAIL)
# ---------------------------------------------------------------------------

def test_checksums_missing(tmp_path):
    path = _make_zip({
        "sprint-manifest.json": json.dumps({"head": "a" * 40, "files": []}),
        "bundle-validation.json": json.dumps({}),
        "00-final-verdict.md": "# v",
    }, str(tmp_path / "no_checksums.zip"))
    with _open(path) as zf:
        r = check_checksums_file_exists(zf)
    assert r["status"] == "WARN"


# ---------------------------------------------------------------------------
# Test 11: checksums file present → checksums_file_exists PASS
# ---------------------------------------------------------------------------

def test_checksums_present(tmp_path):
    path = _make_zip({
        "sprint-manifest.json": json.dumps({"head": "a" * 40, "files": []}),
        "bundle-validation.json": json.dumps({}),
        "00-final-verdict.md": "# v",
        "evidence-integrity/evidence-checksums.sha256": "abc123  foo.md\n",
    }, str(tmp_path / "with_checksums.zip"))
    with _open(path) as zf:
        r = check_checksums_file_exists(zf)
    assert r["status"] == "PASS"


# ---------------------------------------------------------------------------
# Test 12: missing_taskcard_state.zip → no_open_taskcards FAIL
# ---------------------------------------------------------------------------

def test_missing_taskcard_state_fixture():
    with _open(MISSING_TASKCARD_STATE) as zf:
        r = check_no_open_taskcards(zf)
    assert r["status"] == "FAIL"
    assert "No taskcard-state file" in r["detail"]
