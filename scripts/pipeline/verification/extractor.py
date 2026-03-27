"""extractor.py — API token extraction from content markdown files.

Re-exports ``extract_tokens``, ``_extract_from_code_line``, and ``Token``
from ``token_ops``.  This module exists to provide a clean, discoverable
namespace for the extraction half of the verification layer.

Public API::

    extract_tokens(filepath: Path, platform: str) -> list[Token]
    _extract_from_code_line(line, line_no, var_types, platform) -> list[Token]
    Token  -- extracted API token dataclass

All logic lives in token_ops.py; this file is a transparent re-export shim.
"""
from __future__ import annotations

import sys
from pathlib import Path

# sibling-import guard: this sub-module needs pipeline root for token_ops.
_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from token_ops import (  # noqa: E402
    Token,
    extract_tokens,
    _extract_from_code_line,
)

__all__ = ["Token", "extract_tokens", "_extract_from_code_line"]
