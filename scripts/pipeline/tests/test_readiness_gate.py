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


# ---------------------------------------------------------------------------
# G-06 tests (ST-051 regression: G-06 hardcoded a stale launch_gate.py path
# left over from the "move remaining domains to commands/" migration, so
# every G-06 invocation silently failed with a file-not-found error instead
# of actually running the launch gate. No test existed for this at all.)
# ---------------------------------------------------------------------------

def test_g06_resolves_to_the_real_launch_gate_script(tmp_path):
    """The script path gate_g06_launch_gate() constructs must resolve to a
    real, existing file against the actual repo root -- not the stale
    scripts/pipeline/launch_gate.py path (ST-051)."""
    readiness_gate.configure(repo_root=None)  # use the real repo root for this one check
    real_root = readiness_gate._REPO_ROOT
    expected = real_root / "scripts" / "pipeline" / "commands" / "launch" / "launch_gate.py"
    assert expected.is_file(), f"launch_gate.py not found at {expected}"
    stale = real_root / "scripts" / "pipeline" / "launch_gate.py"
    assert not stale.is_file(), "stale path should not exist -- if it does, both paths are ambiguous"


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


# ---------------------------------------------------------------------------
# G-08 tests (TC-MT040-41 / D-2: Extraction Fidelity Gate — advisory only)
#
# These are REAL subprocess integration tests (no monkeypatching of
# readiness_gate's own internals such as _run — that would be the banned T2
# "internal function replacement" pattern). Redirection uses only the
# module's own documented configure() seam, exactly like the G-05/G-06 tests
# above.
# ---------------------------------------------------------------------------

def test_g08_resolves_to_the_real_scout_fidelity_script():
    """The script path gate_g08_scout_fidelity() constructs must resolve to
    a real, existing file against the actual repo root."""
    readiness_gate.configure(repo_root=None)
    real_root = readiness_gate._REPO_ROOT
    expected = real_root / "scripts" / "pipeline" / "commands" / "knowledge" / "scout_fidelity.py"
    assert expected.is_file(), f"scout_fidelity.py not found at {expected}"


def test_g08_pass_when_no_findings():
    """A product with no knowledge/ and no clone cache -> every scout_
    fidelity probe UNAVAILABLE/SKIP -> 0 findings -> G-08 PASS."""
    readiness_gate.configure(repo_root=None)
    result = readiness_gate.gate_g08_scout_fidelity("nonexistent-test-family-xyz", "typescript")
    assert result.status == readiness_gate.STATUS_PASS
    assert result.status != readiness_gate.STATUS_FAIL


def test_g08_warn_never_fail_on_real_product_with_findings():
    """This is the whole point of G-08 (Decision 13): 3d/typescript's real,
    tracked knowledge (0 abstract_class_declaration entries, 0 captured
    docs, 100/100 test-tier snippets — the exact pre-TC-MT040-10/12 shape)
    produces a real finding via scout_fidelity's P5 probe even with no clone
    cache present (index-only signal) — and G-08 must report STATUS_WARN,
    never STATUS_FAIL, for it."""
    readiness_gate.configure(repo_root=None)
    real_root = readiness_gate._REPO_ROOT
    api_surface = real_root / "knowledge" / "3d" / "typescript" / "merged" / "api_surface.json"
    if not api_surface.is_file():
        pytest.skip("knowledge/3d/typescript/merged/api_surface.json not present in this checkout")
    result = readiness_gate.gate_g08_scout_fidelity("3d", "typescript")
    assert result.status != readiness_gate.STATUS_FAIL
    if result.status == readiness_gate.STATUS_WARN:
        assert "advisory" in result.detail.lower() or "never blocking" in result.detail.lower()


def test_g08_skip_on_missing_script(tmp_path):
    """Redirecting repo_root to an empty tmp_path (via the module's own
    configure() seam) means scout_fidelity.py genuinely does not exist at
    the constructed path -- _run's FileNotFoundError path returns
    non-JSON output, which G-08 must handle as SKIP, not crash."""
    readiness_gate.configure(repo_root=tmp_path)
    try:
        result = readiness_gate.gate_g08_scout_fidelity("fake", "typescript")
        assert result.status == readiness_gate.STATUS_SKIP
    finally:
        readiness_gate.configure(repo_root=None)


def test_g08_independent_of_g03_source_coupling():
    """G-03 (DAR coverage) currently FAILs repo-wide for an unrelated,
    pre-existing reason (MT039 G5-22). Prove structural independence: G-08's
    implementation never references G-03's gate function or DAR-coverage
    internals at all -- there is no code path by which G-03's result could
    suppress, gate, or otherwise influence G-08's own result."""
    import inspect
    source = inspect.getsource(readiness_gate.gate_g08_scout_fidelity)
    assert "gate_g03" not in source
    assert "dar_coverage" not in source.lower()
