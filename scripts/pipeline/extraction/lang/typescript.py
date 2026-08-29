"""extraction/lang/typescript.py — TypeScript language adapter (TC-MT040-42).

See extraction/lang/__init__.py for the shared adapter contract this module
implements: declaration_kinds(), doc_anchor(), parse_doc(), export_surface(),
clear_cache().

This card (TC-MT040-42) deliberately leaves TypeScript's real reachability
and doc-anchor behavior for LATER taskcards:
  - export_surface() returns (None, None) unconditionally -- TC-MT040-11
    builds the real implementation (module/export-graph analysis).
  - doc_anchor() is the trivial identity function -- TC-MT040-12 will
    specialize it once the real TSDoc/export-wrapper node shapes are
    analyzed. A quick tree-sitter parse probe during this card did not turn
    up an obvious, low-risk redirection worth doing early (TypeScript
    exports commonly wrap a class/interface/function declaration in an
    `export_statement` node, but the *doc comment* itself already precedes
    that `export_statement` as its own sibling in every fixture sampled --
    i.e. today's plain prev_named_sibling walk in
    api_surface._extract_doc_comment already reaches it without a doc_anchor
    redirection. A `declare module` / re-export wrapper case may exist and
    was not verified against a real TS grammar tree in the time available
    for this card -- left for TC-MT040-12 to confirm properly rather than
    guessed at here).
"""
from __future__ import annotations

import re
from pathlib import Path

from extraction.tree_helpers import _CLASS_TYPES, _FUNC_TYPES, _IMPORT_TYPES, _MODULE_TYPES

_LANG = "typescript"


# ---------------------------------------------------------------------------
# declaration_kinds
# ---------------------------------------------------------------------------

def declaration_kinds() -> dict:
    """Return this language's tree-sitter node-kind sets used during
    extraction. Keys: "class_types", "func_types", "module_types",
    "import_types" -- direct per-language subsets of tree_helpers' shared
    cross-language dicts.
    """
    return {
        "class_types": _CLASS_TYPES.get(_LANG, set()),
        "func_types": _FUNC_TYPES.get(_LANG, set()),
        "module_types": _MODULE_TYPES.get(_LANG, set()),
        "import_types": _IMPORT_TYPES.get(_LANG, set()),
    }


# ---------------------------------------------------------------------------
# doc_anchor
# ---------------------------------------------------------------------------

def doc_anchor(node):
    """Return the node whose doc comment belongs to *node*.

    Trivial identity function for now -- see this module's docstring.
    TC-MT040-12 (a later taskcard) specializes this once TypeScript's real
    TSDoc/export-wrapper node shapes have been analyzed.
    """
    return node


# ---------------------------------------------------------------------------
# parse_doc
# ---------------------------------------------------------------------------

def _first_sentence(text: str) -> str:
    """Return the first sentence (up to first period-space or newline).

    Mirrors api_surface._first_sentence exactly.
    """
    text = text.strip()
    m = re.match(r"^(.+?[.!?])(?:\s|$)", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    return text.split("\n")[0].strip()[:200]


def parse_doc(raw: str) -> dict:
    """Parse a raw JSDoc comment block (``/** ... */``, full text including
    delimiters) into ``{"summary": str}``.

    Thin, independently-tested reproduction of what
    api_surface._extract_doc_comment already does for the "jsdoc" style
    today. Richer TSDoc block-tag parsing (``@param``/``@returns``/etc.) is
    explicitly out of scope for this card -- TC-MT040-12 builds that on
    this seam.
    """
    if not raw.startswith("/**"):
        return {"summary": ""}
    cleaned = re.sub(r"/\*\*|\*/|\n\s*\*\s?", " ", raw).strip()
    return {"summary": _first_sentence(cleaned)}


# ---------------------------------------------------------------------------
# export_surface
# ---------------------------------------------------------------------------

def export_surface(repo: Path, pkg_root: Path) -> "tuple[set[str] | None, Path | None]":
    """No reachability signal implemented for TypeScript yet -- always
    (None, None) (fail-safe: caller must treat every item as reachable).
    TC-MT040-11 (a later taskcard) builds the real implementation.
    """
    return None, None


# ---------------------------------------------------------------------------
# clear_cache
# ---------------------------------------------------------------------------

def clear_cache() -> None:
    """No-op -- this module holds no cached state yet."""
    return None
