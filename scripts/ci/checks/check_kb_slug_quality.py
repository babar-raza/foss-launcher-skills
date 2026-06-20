#!/usr/bin/env python3
"""KB how-to slug quality gate.

Checks KB how-to filenames for known slug defect patterns:

  Check C1 — CamelCase token leak
    Noun part is a single word > 12 chars that is not a known legitimate
    English noun (e.g. "javascriptextensions", "internalvalidation").
    Indicates a C# namespace directory name was not split at CamelCase
    word boundaries in the site planner.

  Check C2 — Verb-noun duplication
    The noun already starts with, ends with, or contains a nominal form of
    the verb (e.g. "how-to-extract-text-extraction-dotnet").

  Check C3 — Generic primary noun
    The first word of the noun is in the banned-generic list
    (e.g. "core", "content", "utilities") — too ambiguous for a KB URL.

  Check C4 — Compound noun without product-family keyword (TC-KBS-016)
    A hyphenated noun where none of the words match the product family's
    keyword set (e.g. "annotations-forms" for "pdf" family has neither
    "pdf" nor "annotation" nor any other pdf-specific word).
    Slug is context-dependent without URL path — fails completeness standard.

Usage — staged-file mode (pre-commit hook):
    python check_kb_slug_quality.py FILE [FILE ...]
    Exit 1 if any FILE has a defective how-to slug; exit 0 otherwise.
    Files that are not how-to slugs are silently skipped.

Usage — scan mode (full-repo reporting):
    python check_kb_slug_quality.py --scan [--root PATH]
    Scans all kb.aspose.org how-to slugs and prints findings.
    Always exits 0 in this mode (reporting only).

Exit codes:
    0  — all supplied files pass (or --scan mode)
    1  — at least one FAIL found (staged-file mode only)
    2  — configuration error (bad root in --scan mode)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants (must stay in sync with site_planner._validate_kb_slugs())
# ---------------------------------------------------------------------------

# Platform suffixes as they appear at the END of a KB how-to filename stem.
_PLATFORM_SUFFIXES: frozenset[str] = frozenset({
    "dotnet", "java", "python", "go", "cpp", "typescript", "nodejs",
})

# Compound and single verbs — longest first so "work-with" beats "work".
_KNOWN_VERBS: list[str] = sorted(
    {
        "work-with", "extract", "convert", "render", "optimize", "parse",
        "create", "generate", "compress", "encrypt", "protect", "merge",
        "split", "add", "remove", "read", "write", "edit", "save", "load",
        "open", "close", "delete", "update", "set", "get", "format",
        "export", "import", "print", "search", "replace", "copy", "move",
        "sort", "filter", "validate", "sign", "lock", "unlock", "compare",
    },
    key=len,
    reverse=True,
)

# Nominal forms that map from verb stem to suffix variants.
_VERB_NOMINAL_FORMS: dict[str, list[str]] = {
    "extract":  ["extraction"],
    "convert":  ["conversion"],
    "render":   ["rendering"],
    "optimize": ["optimization"],
    "parse":    ["parsing"],
    "create":   ["creation"],
    "generate": ["generation"],
    "compress": ["compression"],
    "encrypt":  ["encryption"],
    "protect":  ["protection"],
    "validate": ["validation"],
    "sign":     ["signing"],
    "format":   ["formatting"],
}

_KB_GENERIC_NOUNS: frozenset[str] = frozenset({
    "core", "content", "utilities", "util", "base", "common",
    "general", "data", "model", "helpers", "services",
})

# C4: Product-family keyword sets — must stay in sync with
# site_planner._FAMILY_PRODUCT_KEYWORDS (TC-KBS-016).
# Only terms specific to this family — generic terms ("annotation", "form",
# "text", "page") are excluded so ambiguous slugs cannot pass C4 incorrectly.
_FAMILY_PRODUCT_KEYWORDS: dict[str, frozenset[str]] = {
    # TC-KBS-020 calibration (2026-06-20) — confirmed false positives removed:
    #   pdf   → added "facades"  (Aspose.PDF.Facades namespace — pdf-specific)
    #   email → added "eml", "msg", "attachment"
    #   words → added "doc"  (.doc is the Word binary file format — words-specific)
    "pdf":    frozenset({"pdf", "xmp", "javascript", "facades"}),
    "cells":  frozenset({"cell", "workbook", "worksheet", "xlsx", "excel",
                         "formula", "chart", "ooxml", "spreadsheet"}),
    "slides": frozenset({"slide", "presentation", "powerpoint", "pptx",
                         "shape"}),
    "words":  frozenset({"word", "docx", "paragraph", "doc"}),
    "email":  frozenset({"email", "mailbox", "mime", "smtp", "imap", "calendar",
                         "eml", "msg", "attachment"}),
    "3d":     frozenset({"3d", "scene", "mesh", "material", "animation",
                         "geometry", "node", "fbx", "gltf", "obj"}),
    "font":   frozenset({"font", "glyph", "cff", "eot", "type1", "ttf",
                         "woff", "opentype"}),
}

# Long English nouns that are legitimate KB slug components but are
# > 12 chars without hyphens.  These are NOT CamelCase namespace leaks.
# Keep this list minimal — only add words you are certain are real.
_ALLOWED_LONG_NOUNS: frozenset[str] = frozenset({
    "presentations",   # slides API topic (13 chars)
    "configuration",   # common API noun (13 chars)
    "authentication",  # common API noun (14 chars)
    "authorisation",   # British variant (13 chars)
    "authorization",   # common API noun (13 chars)
    "implementation",  # common noun (14 chars)
})

# ---------------------------------------------------------------------------
# Slug check logic
# ---------------------------------------------------------------------------

def _strip_platform_suffix(inner: str) -> str:
    """Remove the trailing -<platform> segment if present."""
    for suf in _PLATFORM_SUFFIXES:
        if inner.endswith(f"-{suf}"):
            return inner[: -(len(suf) + 1)]
    return inner


def _parse_verb_noun(inner: str) -> tuple[str, str]:
    """Return (verb, noun) by longest-prefix match against known verbs."""
    for kv in _KNOWN_VERBS:
        prefix = kv + "-"
        if inner.startswith(prefix) and len(inner) > len(prefix):
            return kv, inner[len(prefix):]
    return "", inner


def check_slug(stem: str, family: str = "") -> tuple[str, str] | None:
    """Return (check_id, message) if the slug is defective, else None.

    ``stem`` is the filename without the ``.md`` extension, e.g.
    ``how-to-work-with-javascriptextensions-dotnet``.
    ``family`` is the product family (e.g. "pdf", "cells") used for C4 check.
    Files that are not how-to slugs always return None.
    """
    if not stem.startswith("how-to-"):
        return None

    inner = stem[len("how-to-"):]
    inner = _strip_platform_suffix(inner)
    verb, noun = _parse_verb_noun(inner)

    if not noun:
        return None

    # Check C1: single-token noun > 12 chars indicates probable CamelCase leak
    if "-" not in noun and len(noun) > 12 and noun not in _ALLOWED_LONG_NOUNS:
        return (
            "C1",
            f"noun '{noun}' is a single word > 12 chars — "
            "likely an unsplit CamelCase C# namespace name. "
            "Add a label to _FAMILY_SUBPKG_LABELS in site_planner.py.",
        )

    # Check C2: verb appears in noun (duplication)
    if verb:
        verb_forms = [verb] + [verb + s for s in ("ion", "ing", "tion", "ation")]
        verb_forms += _VERB_NOMINAL_FORMS.get(verb, [])
        noun_parts = noun.split("-")
        if (
            any(noun.startswith(f) for f in verb_forms)
            or any(noun.endswith("-" + f) for f in verb_forms)
            or any(part in verb_forms for part in noun_parts)
        ):
            return (
                "C2",
                f"noun '{noun}' contains a form of verb '{verb}' — "
                "verb-noun duplication in slug. "
                "Fix _kb_noun_from_cluster() or add a cluster label override.",
            )

    # Check C3: primary noun word is too generic
    primary = noun.split("-")[0]
    if primary in _KB_GENERIC_NOUNS:
        return (
            "C3",
            f"primary noun word '{primary}' is in the generic-noun banlist — "
            "too ambiguous for a KB URL. "
            "Add a more specific label to _FAMILY_SUBPKG_LABELS in site_planner.py.",
        )

    # Check C4: compound noun without product-family keyword (TC-KBS-016).
    # Prefix matching handles plurals: "materials" matches keyword "material".
    # Only runs when family is known.
    if "-" in noun and family:
        family_keywords = _FAMILY_PRODUCT_KEYWORDS.get(family, frozenset())
        noun_words = noun.split("-")
        if family_keywords and not any(
            word.startswith(kw) for word in noun_words for kw in family_keywords
        ):
            return (
                "C4",
                f"compound noun '{noun}' contains no {family!r} product keyword — "
                "slug is ambiguous without URL path context. "
                "Prefix noun with family term or update _FAMILY_SUBPKG_LABELS in site_planner.py.",
            )

    return None


# ---------------------------------------------------------------------------
# Modes
# ---------------------------------------------------------------------------

def _extract_family(path: str | Path) -> str:
    """Extract product family from a KB content path.

    Expected path structure: .../kb.aspose.org/en/{family}/{platform}/...
    Returns empty string if family cannot be determined.
    """
    parts = Path(path).parts
    for i, part in enumerate(parts):
        if part == "en" and i + 1 < len(parts):
            return parts[i + 1]
    return ""


def check_files(paths: list[str]) -> int:
    """Staged-file mode: check the given file paths. Return 1 if any fail."""
    failures: list[tuple[str, str, str]] = []
    for p in paths:
        stem = Path(p).stem
        family = _extract_family(p)
        result = check_slug(stem, family=family)
        if result is not None:
            check_id, msg = result
            failures.append((p, check_id, msg))

    if not failures:
        return 0

    for path, check_id, msg in failures:
        print(f"FAIL [{check_id}] {path}")
        print(f"       {msg}")

    print(
        f"\n{len(failures)} defective KB how-to slug(s). "
        "Fix the slug in site_planner.py and regenerate, or choose a better name."
    )
    return 1


def scan_root(kb_root: Path) -> list[tuple[Path, str, str]]:
    """Return (path, check_id, message) for all failing slugs under kb_root."""
    failures: list[tuple[Path, str, str]] = []
    for md in sorted(kb_root.rglob("*.md")):
        stem = md.stem
        family = _extract_family(md)
        result = check_slug(stem, family=family)
        if result is not None:
            check_id, msg = result
            failures.append((md, check_id, msg))
    return failures


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument(
        "files",
        nargs="*",
        metavar="FILE",
        help="Files to check (staged-file mode). Pass no files to run --scan.",
    )
    p.add_argument(
        "--scan",
        action="store_true",
        help="Full-repo scan mode (report only, always exits 0).",
    )
    p.add_argument(
        "--root",
        default="content",
        help="Content root directory used in --scan mode (default: content).",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.scan or not args.files:
        # Full-scan report mode — always exits 0
        content_root = Path(args.root)
        kb_root = content_root / "kb.aspose.org"
        if not kb_root.is_dir():
            print(f"ERROR: KB content root not found: {kb_root}", file=sys.stderr)
            return 2

        failures = scan_root(kb_root)
        if not failures:
            print("KB slug quality scan: 0 defective how-to slugs.")
            return 0

        for path, check_id, msg in failures:
            try:
                rel = path.relative_to(content_root)
            except ValueError:
                rel = path
            print(f"WARN [{check_id}] {rel}")
            print(f"       {msg}")

        print(
            f"\n{len(failures)} defective KB how-to slug(s) found "
            "(reporting only — no commit is blocked)."
        )
        return 0

    # Staged-file mode — exits 1 on any failure
    return check_files(args.files)


if __name__ == "__main__":
    sys.exit(main())
