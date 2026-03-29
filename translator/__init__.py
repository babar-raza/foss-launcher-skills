"""Top-level compatibility package for the translation subsystem.

This keeps the documented `python -m translator ...` entrypoint working while the
implementation continues to live under `scripts/translator/`.
"""

from __future__ import annotations

from pathlib import Path


_HERE = Path(__file__).resolve().parent
_SCRIPTS_TRANSLATOR = _HERE.parent / "scripts" / "translator"

# Expose both this wrapper package and the implementation directory so imports
# such as `translator.cli` resolve to `scripts/translator/cli.py`.
__path__ = [str(_HERE)]  # type: ignore[name-defined]
if _SCRIPTS_TRANSLATOR.is_dir():
    __path__.append(str(_SCRIPTS_TRANSLATOR))  # type: ignore[name-defined]

from scripts.translator import (  # noqa: E402,F401
    __version__,
    ALL_LOCALES,
    LOCALE_NAMES,
    TranslatorError,
    FrontmatterParseError,
    PlaceholderLeakError,
    ConfigurationError,
    BackendUnavailableError,
)
