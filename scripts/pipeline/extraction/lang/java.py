"""extraction/lang/java.py — Java language adapter (TC-MT040-42).

See extraction/lang/__init__.py for the shared adapter contract this module
implements: declaration_kinds(), doc_anchor(), parse_doc(), export_surface(),
clear_cache().

No reachability signal is implemented for Java yet -- export_surface()
returns (None, None) unconditionally (fail-safe default). Java is not part
of this mission's TypeScript-hardening scope; declaring the seam here keeps
the adapter set uniform for the day a real signal is added.
"""
from __future__ import annotations

import re
from pathlib import Path

from extraction.tree_helpers import _CLASS_TYPES, _FUNC_TYPES, _IMPORT_TYPES, _MODULE_TYPES

_LANG = "java"


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

    Javadoc (``/** ... */``) comments precede the item as a single sibling
    comment node -- no wrapper redirection needed, identity.
    """
    return node


# ---------------------------------------------------------------------------
# parse_doc
# ---------------------------------------------------------------------------

def _mask_doc_tags(text: str) -> str:
    """Mirrors api_surface._mask_doc_tags exactly -- see its docstring."""
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        if text[i] == "{" and i + 1 < n and text[i + 1] == "@":
            depth = 1
            j = i + 1
            while j < n and depth > 0:
                if text[j] == "{":
                    depth += 1
                elif text[j] == "}":
                    depth -= 1
                j += 1
            out.append("\0" * (j - i))
            i = j
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


def _first_sentence(text: str) -> str:
    """Return the first sentence (up to first period-space or newline).

    Mirrors api_surface._first_sentence exactly, including its MT074 fix
    (2026-10-09): punctuation inside a ``{@tag ...}`` span (balanced braces)
    or an ellipsis's own periods is never mistaken for the sentence
    terminator -- see api_surface._first_sentence's docstring for the full
    incident writeup.
    """
    text = text.strip()
    masked = _mask_doc_tags(text)
    m = re.match(r"^(.+?(?:(?<!\.)\.(?!\.)|[!?]))(?:\s|$)", masked, re.DOTALL)
    if m:
        return text[: m.end(1)].strip()
    return text.split("\n")[0].strip()[:200]


def parse_doc(raw: str) -> dict:
    """Parse a raw Javadoc comment block (``/** ... */``, full text
    including delimiters) into ``{"summary": str}``.

    Thin, independently-tested reproduction of what
    api_surface._extract_doc_comment already does for the "javadoc" style
    today.
    """
    if not raw.startswith("/**"):
        return {"summary": ""}
    cleaned = re.sub(r"/\*\*|\*/|\n\s*\*\s?", " ", raw).strip()
    return {"summary": _first_sentence(cleaned)}


# ---------------------------------------------------------------------------
# export_surface
# ---------------------------------------------------------------------------

def export_surface(repo: Path, pkg_root: Path) -> "tuple[set[str] | None, Path | None]":
    """No reachability signal implemented for Java yet -- always (None, None)
    (fail-safe: caller must treat every item as reachable).
    """
    return None, None


# ---------------------------------------------------------------------------
# clear_cache
# ---------------------------------------------------------------------------

def clear_cache() -> None:
    """No-op -- this module holds no cached state."""
    return None
