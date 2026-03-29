"""Tests for core.env_loader.load_env().

Covers:
  - load_env() no-ops gracefully when python-dotenv is not installed (ImportError)
  - load_env() reads a real .env file when dotenv is present
  - load_env() does NOT override shell-set variables (override=False)
  - _REPO_ROOT resolves to the actual repo root (parents[3] is correct)
"""
from __future__ import annotations

import importlib
import os
import sys
import types
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# conftest.py already adds scripts/pipeline/ to sys.path
from core.env_loader import _REPO_ROOT, _DOTENV_PATH, load_env


# ---------------------------------------------------------------------------
# 1. _REPO_ROOT sanity check
# ---------------------------------------------------------------------------

def test_repo_root_contains_claude_md():
    """_REPO_ROOT must resolve to the repository root (has CLAUDE.md)."""
    assert (_REPO_ROOT / "CLAUDE.md").exists(), (
        f"_REPO_ROOT={_REPO_ROOT!r} does not contain CLAUDE.md — parents[3] is wrong"
    )


def test_dotenv_path_is_under_repo_root():
    assert _DOTENV_PATH == _REPO_ROOT / ".env"


# ---------------------------------------------------------------------------
# 2. Graceful degradation when python-dotenv absent
# ---------------------------------------------------------------------------

def test_load_env_no_op_when_dotenv_missing():
    """load_env() must not raise when dotenv is not installed."""
    with patch.dict(sys.modules, {"dotenv": None}):
        # Reload the module so the import path is re-evaluated with mocked sys.modules
        import importlib
        import core.env_loader as el
        original_load_dotenv = None
        # Patch the import inside load_env to fail
        import builtins
        real_import = builtins.__import__

        def failing_import(name, *args, **kwargs):
            if name == "dotenv":
                raise ImportError("dotenv not available")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=failing_import):
            # Should not raise
            el.load_env()


# ---------------------------------------------------------------------------
# 3. load_env() reads variables from a real .env file
# ---------------------------------------------------------------------------

def test_load_env_reads_dotenv_file(tmp_path, monkeypatch):
    """load_env() must populate os.environ from the .env file."""
    dotenv_file = tmp_path / ".env"
    dotenv_file.write_text("TEST_SENTINEL_VAR=hello_from_dotenv\n")

    # Make sure the var is absent before the call
    monkeypatch.delenv("TEST_SENTINEL_VAR", raising=False)

    import core.env_loader as el
    with patch.object(el, "_DOTENV_PATH", dotenv_file):
        el.load_env()

    assert os.environ.get("TEST_SENTINEL_VAR") == "hello_from_dotenv"
    # Cleanup
    monkeypatch.delenv("TEST_SENTINEL_VAR", raising=False)


# ---------------------------------------------------------------------------
# 4. override=False: shell-set vars take precedence over .env
# ---------------------------------------------------------------------------

def test_load_env_does_not_override_shell_vars(tmp_path, monkeypatch):
    """Shell-exported variables must NOT be overwritten by .env values."""
    dotenv_file = tmp_path / ".env"
    dotenv_file.write_text("TEST_OVERRIDE_VAR=from_dotenv\n")

    monkeypatch.setenv("TEST_OVERRIDE_VAR", "from_shell")

    import core.env_loader as el
    with patch.object(el, "_DOTENV_PATH", dotenv_file):
        el.load_env()

    assert os.environ["TEST_OVERRIDE_VAR"] == "from_shell"
    monkeypatch.delenv("TEST_OVERRIDE_VAR", raising=False)


# ---------------------------------------------------------------------------
# 5. load_env() is idempotent (safe to call multiple times)
# ---------------------------------------------------------------------------

def test_load_env_idempotent(tmp_path, monkeypatch):
    dotenv_file = tmp_path / ".env"
    dotenv_file.write_text("TEST_IDEMPOTENT_VAR=once\n")
    monkeypatch.delenv("TEST_IDEMPOTENT_VAR", raising=False)

    import core.env_loader as el
    with patch.object(el, "_DOTENV_PATH", dotenv_file):
        el.load_env()
        el.load_env()  # second call must not raise or corrupt

    assert os.environ.get("TEST_IDEMPOTENT_VAR") == "once"
    monkeypatch.delenv("TEST_IDEMPOTENT_VAR", raising=False)


# ---------------------------------------------------------------------------
# 6. load_env() does not raise when .env file is absent
# ---------------------------------------------------------------------------

def test_load_env_missing_dotenv_file(tmp_path):
    """If .env does not exist, load_env() must not raise."""
    import core.env_loader as el
    with patch.object(el, "_DOTENV_PATH", tmp_path / "nonexistent.env"):
        el.load_env()  # must not raise
