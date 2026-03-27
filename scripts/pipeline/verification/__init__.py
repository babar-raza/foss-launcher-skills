"""verification/ — API token extraction and verification layer.

This package is a clean re-export shim over ``token_ops.py``.  It provides
the same public API under a more descriptive namespace, aligned with the
target architecture described in the Phase 3/6 plan.

Modules:
- extractor.py: extract_tokens, _extract_from_code_line, Token
- verifier.py:  verify_tokens, Finding

Usage::

    from verification.extractor import extract_tokens
    from verification.verifier import verify_tokens

Backward compat: ``token_ops.py`` continues to export all the same symbols
and is not modified.  Both import paths work simultaneously.
"""
from __future__ import annotations

import sys
from pathlib import Path

# sibling-import guard: verification/ sub-package needs the pipeline root
# for token_ops imports. Not the antipattern — Python adds the sub-package
# dir to sys.path, not the pipeline root.
_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from .extractor import extract_tokens, _extract_from_code_line, Token  # noqa: E402
from .verifier import verify_tokens, Finding  # noqa: E402

__all__ = [
    "extract_tokens",
    "_extract_from_code_line",
    "Token",
    "verify_tokens",
    "Finding",
]
