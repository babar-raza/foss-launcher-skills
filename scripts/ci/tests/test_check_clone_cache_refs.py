"""Tests for scripts/ci/check_clone_cache_refs.py enforcement script.

Covers:
  - Script exits 1 on active obsolete foss-launcher references
  - Script exits 0 when references have the HISTORICAL marker
  - Script exits 0 on the patched repository (integration check)
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
CHECKER = REPO_ROOT / "scripts" / "ci" / "checks" / "check_clone_cache_refs.py"


def _run_checker(*extra_args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CHECKER)] + list(extra_args),
        capture_output=True,
        text=True,
        cwd=cwd or REPO_ROOT,
    )


# ---------------------------------------------------------------------------
# 1. Script detects active obsolete reference → exit 1
# ---------------------------------------------------------------------------

def test_detects_forbidden_foss_launcher_path(tmp_path):  # TEST_FIXTURE_OBSOLETE_FOSS_LAUNCHER_REFERENCE
    """A temp file containing the forbidden path causes exit 1."""
    bad_file = tmp_path / "bad_skill.md"
    # Use a forbidden path that the scanner would pick up
    bad_file.write_text(
        "Clone cache must exist at foss-launcher/runs/.clone_cache/aspose_3d_java/\n",  # TEST_FIXTURE_OBSOLETE_FOSS_LAUNCHER_REFERENCE
        encoding="utf-8",
    )
    # Run the checker with the tmp_path as a scan target by patching via a fresh subprocess
    # approach: write a minimal wrapper that scans only the temp file
    wrapper = tmp_path / "run_check.py"
    wrapper.write_text(
        f"""
import sys
sys.path.insert(0, r'{REPO_ROOT}/scripts/ci/checks')
import check_clone_cache_refs as c
from pathlib import Path

# Override collect_files to return only our test file
c.collect_files = lambda: [Path(r'{bad_file}')]
sys.exit(c.run_checks())
""",
        encoding="utf-8",
    )
    result = subprocess.run([sys.executable, str(wrapper)], capture_output=True, text=True)
    assert result.returncode == 1, f"Expected exit 1, got {result.returncode}\n{result.stdout}"
    assert "FAIL" in result.stdout


# ---------------------------------------------------------------------------
# 2. Script permits lines with the HISTORICAL marker
# ---------------------------------------------------------------------------

def test_permits_historical_marker(tmp_path):
    """A line with the obsolete marker is not flagged."""
    ok_file = tmp_path / "ok_doc.md"
    marker = "HISTORICAL_OBSOLETE_FOSS_LAUNCHER_REFERENCE"
    ok_file.write_text(
        f"foss-launcher/runs/.clone_cache/ {marker}\n",
        encoding="utf-8",
    )
    wrapper = tmp_path / "run_check_ok.py"
    wrapper.write_text(
        f"""
import sys
sys.path.insert(0, r'{REPO_ROOT}/scripts/ci/checks')
import check_clone_cache_refs as c
from pathlib import Path

c.collect_files = lambda: [Path(r'{ok_file}')]
sys.exit(c.run_checks())
""",
        encoding="utf-8",
    )
    result = subprocess.run([sys.executable, str(wrapper)], capture_output=True, text=True)
    assert result.returncode == 0, f"Expected exit 0 (marked), got {result.returncode}\n{result.stdout}"
    assert "PASS" in result.stdout


# ---------------------------------------------------------------------------
# 3. Script passes on the patched repository
# ---------------------------------------------------------------------------

def test_passes_on_patched_repo():
    """After all patches, the enforcement script must exit 0 on the actual repo."""
    result = _run_checker()
    assert result.returncode == 0, (
        f"Enforcement script found violations in the patched repo:\n{result.stdout}"
    )
    assert "PASS" in result.stdout


# ---------------------------------------------------------------------------
# 4. Dry-run mode exits 0 even with violations
# ---------------------------------------------------------------------------

def test_dry_run_exits_zero_on_violations(tmp_path):
    """--dry-run mode reports violations but exits 0."""
    bad_file = tmp_path / "bad.md"
    bad_file.write_text("foss-launcher/runs/.clone_cache/aspose_3d_java/\n", encoding="utf-8")  # TEST_FIXTURE_OBSOLETE_FOSS_LAUNCHER_REFERENCE
    wrapper = tmp_path / "run_dry.py"
    wrapper.write_text(
        f"""
import sys
sys.path.insert(0, r'{REPO_ROOT}/scripts/ci/checks')
import check_clone_cache_refs as c
from pathlib import Path

c.collect_files = lambda: [Path(r'{bad_file}')]
sys.exit(c.run_checks(dry_run=True))
""",
        encoding="utf-8",
    )
    result = subprocess.run([sys.executable, str(wrapper)], capture_output=True, text=True)
    assert result.returncode == 0, f"Dry-run should exit 0, got {result.returncode}"
    assert "dry-run" in result.stdout.lower()


# ---------------------------------------------------------------------------
# 5. Scanner recognises TEST_FIXTURE_OBSOLETE_FOSS_LAUNCHER_REFERENCE marker
# GAP-02 closure
# ---------------------------------------------------------------------------


def test_permits_fixture_marker(tmp_path):
    """A line carrying TEST_FIXTURE_OBSOLETE_FOSS_LAUNCHER_REFERENCE is not flagged."""
    fixture_file = tmp_path / "fixture_test.md"
    fixture_file.write_text(
        "foss-launcher/runs/.clone_cache/aspose_3d_java/  TEST_FIXTURE_OBSOLETE_FOSS_LAUNCHER_REFERENCE\n",
        encoding="utf-8",
    )
    wrapper = tmp_path / "run_fixture.py"
    wrapper.write_text(
        f"""
import sys
sys.path.insert(0, r'{REPO_ROOT}/scripts/ci/checks')
import check_clone_cache_refs as c
from pathlib import Path

c.collect_files = lambda: [Path(r'{fixture_file}')]
sys.exit(c.run_checks())
""",
        encoding="utf-8",
    )
    result = subprocess.run([sys.executable, str(wrapper)], capture_output=True, text=True)
    assert result.returncode == 0, (
        f"Expected exit 0 (fixture marker permits line), got {result.returncode}\n{result.stdout}"
    )
    assert "PASS" in result.stdout


# ---------------------------------------------------------------------------
# 6. SKIP_PATH_PREFIXES must not contain broad test-directory entries
# GAP-03 closure
# ---------------------------------------------------------------------------


def test_no_broad_test_dir_skip():
    """Broad test-directory skip prefixes must not exist in SKIP_PATH_PREFIXES.

    If either scripts/pipeline/tests/ or scripts/ci/tests/ were added to
    SKIP_PATH_PREFIXES the scanner would silently ignore test fixtures that
    contain the forbidden path, defeating the enforcement guarantee.
    """
    import sys as _sys
    _sys.path.insert(0, str(REPO_ROOT / "scripts" / "ci" / "checks"))
    import check_clone_cache_refs as c

    forbidden_prefixes = [
        "scripts/pipeline/tests/",
        "scripts/ci/tests/",
        "scripts\\pipeline\\tests\\",
        "scripts\\ci\\tests\\",
    ]
    for prefix in forbidden_prefixes:
        assert prefix not in c.SKIP_PATH_PREFIXES, (
            f"Broad test-directory skip '{prefix}' found in SKIP_PATH_PREFIXES — "
            "this would silently suppress scanner coverage of test files."
        )


# ---------------------------------------------------------------------------
# 7. Scanner recognises PROHIBITION_OBSOLETE_FOSS_LAUNCHER_REFERENCE marker
# Follow-up: section-enhance skill files use active prohibition language
# ---------------------------------------------------------------------------


def test_permits_prohibition_marker(tmp_path):
    """A prohibition rule line with PROHIBITION_OBSOLETE_FOSS_LAUNCHER_REFERENCE is not flagged."""
    prohibition_file = tmp_path / "prohibition_test.md"
    prohibition_file.write_text(
        "Clone cache path must NOT contain `foss-launcher` or `foss_launcher` anywhere in the path"
        "  <!-- PROHIBITION_OBSOLETE_FOSS_LAUNCHER_REFERENCE -->\n",
        encoding="utf-8",
    )
    wrapper = tmp_path / "run_prohibition.py"
    wrapper.write_text(
        f"""
import sys
sys.path.insert(0, r'{REPO_ROOT}/scripts/ci/checks')
import check_clone_cache_refs as c
from pathlib import Path

c.collect_files = lambda: [Path(r'{prohibition_file}')]
sys.exit(c.run_checks())
""",
        encoding="utf-8",
    )
    result = subprocess.run([sys.executable, str(wrapper)], capture_output=True, text=True)
    assert result.returncode == 0, (
        f"Expected exit 0 (prohibition marker permits line), got {result.returncode}\n{result.stdout}"
    )
    assert "PASS" in result.stdout


def test_unmarked_prohibition_still_fails(tmp_path):
    """A prohibition-style line without any marker is still flagged by the scanner."""
    prohibition_file = tmp_path / "unmarked_prohibition.md"
    prohibition_file.write_text(
        "Clone cache path must NOT contain `foss-launcher` or `foss_launcher` anywhere in the path\n",  # TEST_FIXTURE_OBSOLETE_FOSS_LAUNCHER_REFERENCE
        encoding="utf-8",
    )
    wrapper = tmp_path / "run_unmarked.py"
    wrapper.write_text(
        f"""
import sys
sys.path.insert(0, r'{REPO_ROOT}/scripts/ci/checks')
import check_clone_cache_refs as c
from pathlib import Path

c.collect_files = lambda: [Path(r'{prohibition_file}')]
sys.exit(c.run_checks())
""",
        encoding="utf-8",
    )
    result = subprocess.run([sys.executable, str(wrapper)], capture_output=True, text=True)
    assert result.returncode == 1, (
        f"Expected exit 1 (unmarked prohibition line should fail), got {result.returncode}\n{result.stdout}"
    )
    assert "FAIL" in result.stdout
