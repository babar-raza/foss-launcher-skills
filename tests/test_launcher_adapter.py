"""Tests for scripts/launcher_adapter.py — launcher boundary module."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Import under test
# ---------------------------------------------------------------------------
_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS))
sys.path.insert(0, str(_SCRIPTS.parent))

from launcher_adapter import (
    LAUNCHER_SCRIPTS,
    LAUNCHER_SCRIPT_NAMES,
    LauncherScript,
    get_script_path,
    run_launcher_script,
    run_scout,
    run_merge,
    run_index,
    script_sha256,
    REPO_ROOT,
)


# ---------------------------------------------------------------------------
# LAUNCHER_SCRIPTS registry
# ---------------------------------------------------------------------------

class TestLauncherScriptsList:
    """Structural tests for LAUNCHER_SCRIPTS constant."""

    def test_non_empty(self):
        assert len(LAUNCHER_SCRIPTS) >= 8

    def test_all_entries_are_launcher_script_named_tuples(self):
        for ls in LAUNCHER_SCRIPTS:
            assert isinstance(ls, LauncherScript)

    def test_all_entries_have_non_empty_fields(self):
        for ls in LAUNCHER_SCRIPTS:
            assert ls.name, f"Empty name in {ls}"
            assert ls.origin, f"Empty origin in {ls}"
            assert ls.purpose, f"Empty purpose in {ls}"
            assert ls.entry_point.endswith(".py"), f"entry_point must end with .py: {ls}"

    def test_all_scripts_exist_on_disk(self):
        missing = [ls for ls in LAUNCHER_SCRIPTS if not (REPO_ROOT / ls.entry_point).exists()]
        assert missing == [], f"Launcher scripts missing on disk: {[ls.entry_point for ls in missing]}"

    def test_core_scripts_present(self):
        names = {ls.name for ls in LAUNCHER_SCRIPTS}
        for required in ("scout", "merge", "index", "embed"):
            assert required in names, f"Core launcher script '{required}' not in LAUNCHER_SCRIPTS"

    def test_all_origins_are_aspose(self):
        for ls in LAUNCHER_SCRIPTS:
            assert ls.origin == "aspose.org", f"Unexpected origin for {ls.name}: {ls.origin!r}"


class TestLauncherScriptNames:
    """Tests for LAUNCHER_SCRIPT_NAMES frozenset."""

    def test_is_frozenset(self):
        assert isinstance(LAUNCHER_SCRIPT_NAMES, frozenset)

    def test_contains_py_extension(self):
        for name in LAUNCHER_SCRIPT_NAMES:
            assert name.endswith(".py"), f"Expected .py suffix: {name!r}"

    def test_count_matches_launcher_scripts(self):
        assert len(LAUNCHER_SCRIPT_NAMES) == len(LAUNCHER_SCRIPTS)

    def test_scout_py_in_names(self):
        assert "scout.py" in LAUNCHER_SCRIPT_NAMES

    def test_merge_py_in_names(self):
        assert "merge.py" in LAUNCHER_SCRIPT_NAMES


# ---------------------------------------------------------------------------
# get_script_path
# ---------------------------------------------------------------------------

class TestGetScriptPath:
    """Tests for get_script_path()."""

    def test_returns_path_for_scout(self):
        path = get_script_path("scout")
        assert isinstance(path, Path)
        assert path.name == "scout.py"

    def test_returns_path_for_merge(self):
        path = get_script_path("merge")
        assert path.name == "merge.py"

    def test_returns_absolute_path(self):
        path = get_script_path("index")
        assert path.is_absolute()

    def test_path_exists_on_disk(self):
        path = get_script_path("embed")
        assert path.exists()

    def test_unknown_name_raises_key_error(self):
        with pytest.raises(KeyError, match="Unknown launcher script"):
            get_script_path("nonexistent_script")

    def test_all_managed_scripts_resolvable(self):
        for ls in LAUNCHER_SCRIPTS:
            path = get_script_path(ls.name)
            assert path.exists(), f"Cannot resolve path for {ls.name}"


# ---------------------------------------------------------------------------
# script_sha256
# ---------------------------------------------------------------------------

class TestScriptSha256:
    """Tests for script_sha256()."""

    def test_returns_64_char_hex_string(self):
        digest = script_sha256("scout")
        assert isinstance(digest, str)
        assert len(digest) == 64
        assert all(c in "0123456789abcdef" for c in digest)

    def test_deterministic(self):
        assert script_sha256("merge") == script_sha256("merge")

    def test_different_scripts_have_different_hashes(self):
        assert script_sha256("scout") != script_sha256("merge")

    def test_unknown_name_raises_key_error(self):
        with pytest.raises(KeyError):
            script_sha256("no_such_script")


# ---------------------------------------------------------------------------
# run_launcher_script
# ---------------------------------------------------------------------------

class TestRunLauncherScript:
    """Tests for run_launcher_script()."""

    def test_help_flag_exits_zero_or_nonzero_but_runs(self):
        # Some scripts may exit 1 for --help; we just verify no exception
        rc = run_launcher_script("golden_index", ["--help"],
                                 capture_output=True)
        assert isinstance(rc, int)

    def test_unknown_name_raises_key_error(self):
        with pytest.raises(KeyError):
            run_launcher_script("not_a_real_script", [])


# ---------------------------------------------------------------------------
# Convenience wrappers (interface contract only — not invoked end-to-end)
# ---------------------------------------------------------------------------

class TestConvenienceWrappers:
    """Verify wrappers are callable and accept the expected argument signatures."""

    def test_run_scout_is_callable(self):
        assert callable(run_scout)

    def test_run_merge_is_callable(self):
        assert callable(run_merge)

    def test_run_index_is_callable(self):
        assert callable(run_index)


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------

class TestCli:
    """Smoke tests for the CLI interface."""

    def test_list_flag_exits_zero(self):
        result = subprocess.run(
            [sys.executable, "scripts/launcher_adapter.py", "--list"],
            capture_output=True, text=True,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0

    def test_list_output_contains_scout(self):
        result = subprocess.run(
            [sys.executable, "scripts/launcher_adapter.py", "--list"],
            capture_output=True, text=True,
            cwd=str(REPO_ROOT),
        )
        assert "scout" in result.stdout

    def test_check_drift_exits_zero(self):
        result = subprocess.run(
            [sys.executable, "scripts/launcher_adapter.py", "--check-drift"],
            capture_output=True, text=True,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0

    def test_check_drift_output_contains_hashes(self):
        result = subprocess.run(
            [sys.executable, "scripts/launcher_adapter.py", "--check-drift"],
            capture_output=True, text=True,
            cwd=str(REPO_ROOT),
        )
        # Each hash line has a 16-char prefix followed by "…"
        assert "…" in result.stdout or "..." in result.stdout

    def test_no_flags_shows_list(self):
        result = subprocess.run(
            [sys.executable, "scripts/launcher_adapter.py"],
            capture_output=True, text=True,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0
        assert "Launcher-origin scripts" in result.stdout
