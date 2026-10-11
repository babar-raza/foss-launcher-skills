"""Shared bootstrap for scripts/pipeline — single source of path/config/env setup.

Usage in any pipeline script:
    import sys; from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[0]))
    from _bootstrap import init, PIPELINE_ROOT, REPO_ROOT, config_path; init()
"""
import os
import sys
from pathlib import Path

# Canonical directories
PIPELINE_ROOT = Path(__file__).resolve().parent
LIB_DIR = PIPELINE_ROOT / "lib"
CONFIG_DIR = PIPELINE_ROOT / "config"
REPO_ROOT = PIPELINE_ROOT.parent.parent


def init():
    """Add PIPELINE_ROOT and LIB_DIR to sys.path; load .env if present."""
    for p in (str(PIPELINE_ROOT), str(LIB_DIR)):
        if p not in sys.path:
            sys.path.insert(0, p)
    # Load .env from repo root if python-dotenv is available
    env_file = REPO_ROOT / ".env"
    if env_file.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(env_file)
        except ImportError:
            pass


def config_path(name):
    """Return path to a config file in CONFIG_DIR."""
    return CONFIG_DIR / name


def repo_path(*parts):
    """Return path relative to repo root."""
    return REPO_ROOT.joinpath(*parts)
