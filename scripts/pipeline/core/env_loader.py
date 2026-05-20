# Adapted from aspose.org
"""env_loader.py — Load .env from repo root into os.environ.

Call ``load_env()`` once at the top of every CLI entry point that needs
environment variables.  Uses ``override=False`` so shell-exported variables
always take precedence over .env values.

The .env file is located by walking up from this file's location:
    core/ -> pipeline/ -> scripts/ -> repo_root
"""
from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DOTENV_PATH = _REPO_ROOT / ".env"


def load_env() -> None:
    """Load .env at repo root into os.environ (no-op if python-dotenv absent)."""
    try:
        from dotenv import load_dotenv  # type: ignore[import]
    except ImportError:
        return  # Graceful degradation: dotenv not installed, rely on shell vars
    load_dotenv(dotenv_path=_DOTENV_PATH, override=False)
