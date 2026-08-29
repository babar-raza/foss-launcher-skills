"""Smoke tests for CI check scripts in scripts/ci/checks/.

These verify that check scripts can be invoked without crashing.
Follows the subprocess pattern from tests/test_governance_checks.py.
"""
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CHECKS_DIR = REPO_ROOT / "scripts" / "ci" / "checks"


def _run_check(script_name: str, args: list[str] | None = None) -> subprocess.CompletedProcess:
    """Run a CI check script via subprocess and return the result."""
    script = CHECKS_DIR / script_name
    cmd = [sys.executable, str(script)] + (args or [])
    return subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, timeout=30)


def _can_compile(script_name: str) -> bool:
    """Verify a script compiles without syntax errors."""
    script = CHECKS_DIR / script_name
    if not script.exists():
        pytest.skip(f"{script_name} does not exist")
    result = subprocess.run(
        [sys.executable, "-m", "py_compile", str(script)],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=15,
    )
    return result.returncode == 0


def test_check_knowledge_staleness_no_args():
    """check_knowledge_staleness.py with no args exits 0."""
    result = _run_check("check_knowledge_staleness.py")
    assert result.returncode == 0
    assert "No files provided" in result.stdout


def test_check_proof_matrix_compiles():
    """check_proof_matrix.py compiles without syntax errors."""
    assert _can_compile("check_proof_matrix.py")


def test_check_pipeline_registration_compiles():
    """check_pipeline_registration.py compiles without syntax errors."""
    assert _can_compile("check_pipeline_registration.py")


def test_check_skill_readme_coverage_compiles():
    """check_skill_readme_coverage.py compiles without syntax errors."""
    assert _can_compile("check_skill_readme_coverage.py")


def test_check_dar_coverage_compiles():
    """check_dar_coverage.py compiles without syntax errors."""
    assert _can_compile("check_dar_coverage.py")


def test_check_knowledge_staleness_compiles():
    """check_knowledge_staleness.py compiles without syntax errors."""
    assert _can_compile("check_knowledge_staleness.py")


def test_check_stale_file_regression_compiles():
    """check_stale_file_regression.py compiles without syntax errors (ported 2026-08-29)."""
    assert _can_compile("check_stale_file_regression.py")


def test_check_module_consumption_compiles():
    """check_module_consumption.py compiles without syntax errors (ported 2026-08-29)."""
    assert _can_compile("check_module_consumption.py")


def test_check_hardcoded_external_coupling_compiles():
    """check_hardcoded_external_coupling.py compiles without syntax errors (new 2026-08-29)."""
    assert _can_compile("check_hardcoded_external_coupling.py")
