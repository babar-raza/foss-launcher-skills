"""Unit tests for core/clone_cache.py — public API and CLI.

Uses monkeypatching throughout; no real git clones, no network calls.
"""
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# sys.path is set by tests/conftest.py
from core.clone_cache import cache_root, clone_exists, clone_path


# ---------------------------------------------------------------------------
# cache_root() / clone_path()
# ---------------------------------------------------------------------------

def test_cache_root_default(tmp_path, monkeypatch):
    """cache_root() returns the default <repo_root>/runs/.clone_cache when env is unset."""
    monkeypatch.delenv("ASPOSE_CLONE_CACHE", raising=False)
    root = cache_root()
    assert root.name == ".clone_cache"
    assert root.parent.name == "runs"


def test_cache_root_env_override(tmp_path, monkeypatch):
    """cache_root() returns the path specified by ASPOSE_CLONE_CACHE."""
    monkeypatch.setenv("ASPOSE_CLONE_CACHE", str(tmp_path / "custom_cache"))
    root = cache_root()
    assert root == (tmp_path / "custom_cache").resolve()


def test_clone_path_naming(monkeypatch):
    """clone_path() builds the correct directory name."""
    monkeypatch.delenv("ASPOSE_CLONE_CACHE", raising=False)
    p = clone_path("3d", "net")
    assert p.name == "aspose_3d_net"
    assert p.parent == cache_root()


def test_clone_exists_false_when_missing(tmp_path, monkeypatch):
    """clone_exists() returns False when directory is absent."""
    monkeypatch.setenv("ASPOSE_CLONE_CACHE", str(tmp_path))
    assert clone_exists("3d", "net") is False


def test_clone_exists_false_without_git_dir(tmp_path, monkeypatch):
    """clone_exists() returns False when dir exists but has no .git."""
    monkeypatch.setenv("ASPOSE_CLONE_CACHE", str(tmp_path))
    (tmp_path / "aspose_3d_net").mkdir()
    assert clone_exists("3d", "net") is False


def test_clone_exists_true_with_git_dir(tmp_path, monkeypatch):
    """clone_exists() returns True when a valid-looking clone is present."""
    monkeypatch.setenv("ASPOSE_CLONE_CACHE", str(tmp_path))
    clone_dir = tmp_path / "aspose_3d_net"
    clone_dir.mkdir()
    (clone_dir / ".git").mkdir()
    assert clone_exists("3d", "net") is True


# ---------------------------------------------------------------------------
# CLI — happy path
# ---------------------------------------------------------------------------

def test_cli_resolve_happy_path(tmp_path, monkeypatch):
    """CLI 'resolve' prints the clone path and exits 0 when clone exists."""
    monkeypatch.setenv("ASPOSE_CLONE_CACHE", str(tmp_path))
    # Fake a valid clone so ensure_clone returns immediately without git
    clone_dir = tmp_path / "aspose_3d_net"
    clone_dir.mkdir()
    (clone_dir / ".git").mkdir()

    result = subprocess.run(
        [sys.executable, "core/clone_cache.py", "resolve", "3d", "net"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parent.parent,
        env={**__import__("os").environ, "ASPOSE_CLONE_CACHE": str(tmp_path)},
    )
    assert result.returncode == 0, result.stderr
    assert "aspose_3d_net" in result.stdout.strip()


# ---------------------------------------------------------------------------
# CLI — error paths
# ---------------------------------------------------------------------------

def test_cli_wrong_subcommand_exits_1(tmp_path):
    """CLI with wrong subcommand prints usage to stderr and exits 1."""
    result = subprocess.run(
        [sys.executable, "core/clone_cache.py", "badcmd", "3d", "net"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parent.parent,
    )
    assert result.returncode == 1
    assert "Usage" in result.stderr


def test_cli_too_few_args_exits_1():
    """CLI with too few arguments exits 1."""
    result = subprocess.run(
        [sys.executable, "core/clone_cache.py", "resolve", "3d"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parent.parent,
    )
    assert result.returncode == 1
    assert "Usage" in result.stderr


def test_cli_no_args_exits_1():
    """CLI with no arguments exits 1."""
    result = subprocess.run(
        [sys.executable, "core/clone_cache.py"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parent.parent,
    )
    assert result.returncode == 1
    assert "Usage" in result.stderr


def test_cli_resolve_runtime_error_exits_1(tmp_path, monkeypatch):
    """CLI exits 1 and prints error message when product not in products.json."""
    # Point to empty tmp_path as cache (no pre-existing clone) and a products.json
    # with no matching entry so ensure_clone raises RuntimeError.
    import json, os
    empty_products = tmp_path / "data" / "products.json"
    empty_products.parent.mkdir(parents=True)
    empty_products.write_text(json.dumps([]), encoding="utf-8")

    # We cannot easily override _PRODUCTS_JSON at runtime via env — use subprocess
    # with a patched products.json path by monkeypatching the module constant via
    # a wrapper script approach; instead, verify the error message text is present
    # when the real products.json lacks the product key by using an unknown family.
    result = subprocess.run(
        [sys.executable, "core/clone_cache.py", "resolve", "nonexistent", "fake"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parent.parent,
        env={**os.environ, "ASPOSE_CLONE_CACHE": str(tmp_path)},
    )
    assert result.returncode == 1
    assert "error:" in result.stderr


# ---------------------------------------------------------------------------
# Anti-regression: foss-launcher must never be used as clone cache
# ---------------------------------------------------------------------------

def test_cache_root_default_never_foss_launcher(monkeypatch):
    """cache_root() default must not contain 'foss-launcher' in any form."""
    monkeypatch.delenv("ASPOSE_CLONE_CACHE", raising=False)
    root = cache_root()
    assert "foss-launcher" not in str(root).lower()
    assert "foss_launcher" not in str(root).lower()  # TEST_FIXTURE_OBSOLETE_FOSS_LAUNCHER_REFERENCE


def test_cache_root_env_valid_non_foss_launcher(tmp_path, monkeypatch):
    """ASPOSE_CLONE_CACHE pointing to a valid non-foss-launcher path is accepted."""
    monkeypatch.setenv("ASPOSE_CLONE_CACHE", str(tmp_path / "my_cache"))
    root = cache_root()
    assert root == (tmp_path / "my_cache").resolve()


def test_cache_root_env_foss_launcher_forward_slash_rejected(monkeypatch):
    """ASPOSE_CLONE_CACHE pointing to foss-launcher path raises ValueError."""
    import pytest
    monkeypatch.setenv("ASPOSE_CLONE_CACHE", "/some/path/foss-launcher/runs/.clone_cache")  # TEST_FIXTURE_OBSOLETE_FOSS_LAUNCHER_REFERENCE
    with pytest.raises(ValueError, match="obsolete foss-launcher"):
        cache_root()


def test_cache_root_env_foss_launcher_backslash_rejected(monkeypatch):
    """ASPOSE_CLONE_CACHE with backslash foss-launcher path raises ValueError."""
    import pytest
    monkeypatch.setenv("ASPOSE_CLONE_CACHE", r"C:\foss-launcher\runs\.clone_cache")  # TEST_FIXTURE_OBSOLETE_FOSS_LAUNCHER_REFERENCE
    with pytest.raises(ValueError, match="obsolete foss-launcher"):
        cache_root()


def test_cache_root_env_foss_underscore_launcher_rejected(monkeypatch):
    """ASPOSE_CLONE_CACHE with foss_launcher variant raises ValueError."""  # TEST_FIXTURE_OBSOLETE_FOSS_LAUNCHER_REFERENCE
    import pytest
    monkeypatch.setenv("ASPOSE_CLONE_CACHE", "/some/path/foss_launcher/runs/.clone_cache")  # TEST_FIXTURE_OBSOLETE_FOSS_LAUNCHER_REFERENCE
    with pytest.raises(ValueError, match="obsolete foss-launcher"):
        cache_root()
