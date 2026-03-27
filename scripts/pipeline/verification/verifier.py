"""verifier.py — API token verification against the knowledge model.

Re-exports ``verify_tokens`` and ``Finding`` from ``token_ops``.  This
module exists to provide a clean, discoverable namespace for the
verification half of the verification layer.

Public API::

    verify_tokens(tokens: list[Token], knowledge: Knowledge, filepath: Path) -> list[Finding]
    Finding  -- verification result (FAIL/WARN/INFO)

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
    Finding,
    verify_tokens,
)

__all__ = ["Finding", "verify_tokens"]
