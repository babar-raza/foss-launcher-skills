"""Capability claim evaluator — detects prose format/feature claims and
cross-references against the knowledge model's formats.json.

Flags prose lines that claim import/export support for a format when
formats.json says otherwise (e.g., claiming export when the format is
import-only, or claiming support when direction is "detect" only).

Category: CF (Capability/Format claim)
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..models import Finding, Page
from . import BaseEvaluator

try:
    import sys as _sys
    from pathlib import Path as _Path
    _scripts = _Path(__file__).resolve().parent.parent.parent.parent
    if str(_scripts) not in _sys.path:
        _sys.path.insert(0, str(_scripts))
    from config_loader import resolve_knowledge_root as _rkr
    KNOWLEDGE_ROOT = _rkr()
except Exception:
    KNOWLEDGE_ROOT = Path("knowledge")
try:
    import sys as _sys
    from pathlib import Path as _Path
    _scripts = _Path(__file__).resolve().parent.parent.parent.parent
    if str(_scripts) not in _sys.path:
        _sys.path.insert(0, str(_scripts))
    from config_loader import resolve_knowledge_root as _rkr
    KNOWLEDGE_ROOT = _rkr()
except Exception:
    KNOWLEDGE_ROOT = Path("knowledge")


try:
    import sys as _sys
    from pathlib import Path as _Path
    _scripts = _Path(__file__).resolve().parent.parent.parent.parent
    if str(_scripts) not in _sys.path:
        _sys.path.insert(0, str(_scripts))
    from config_loader import resolve_knowledge_root as _rkr
    KNOWLEDGE_ROOT = _rkr()
except Exception:
    KNOWLEDGE_ROOT = Path("knowledge")
# Direction verbs
_EXPORT_VERB_RE = re.compile(
    r"\b(?:export|save|write|convert\s+to|render\s+to)\b",
    re.IGNORECASE,
)
_IMPORT_VERB_RE = re.compile(
    r"\b(?:import|load|read(?!-only)|open|convert\s+from|parse)\b",
    re.IGNORECASE,
)
# Bidirectional verbs — "supports/handles/processes X" implies bidirectional capability.
# When present near a format token, _claim_direction returns "both".
_BOTH_VERB_RE = re.compile(
    r"\b(?:support|handle|process|convert)s?\b",
    re.IGNORECASE,
)

# Broad format extensions to look for
_KNOWN_EXTENSIONS = {
    "obj", "fbx", "gltf", "glb", "stl", "ply", "3mf", "dae", "x3d",
    "pptx", "ppt", "odp", "xlsx", "xls", "ods", "docx", "doc", "odt",
    "pdf", "html", "svg", "png", "jpg", "jpeg", "gif", "bmp", "tiff",
    "u3d", "amf", "rvm", "draco",
    "one", "msg", "eml", "mht", "mhtml", "ics", "vcf", "pst", "ost",
    "csv", "tsv",
}

# Regex to match format names in prose
_FORMAT_TOKEN_RE = re.compile(
    r"(?<![a-zA-Z])(?:\*\.|\.)?" +
    r"(" + "|".join(re.escape(ext) for ext in sorted(_KNOWN_EXTENSIONS, key=len, reverse=True)) +
    r")" + r"(?![a-zA-Z0-9])",
    re.IGNORECASE,
)

# Negation — skip lines that say "does not support" etc.
_NEGATION_RE = re.compile(
    r"\b(?:not|no\s+longer|without|don'?t|doesn'?t|cannot|unsupported|"
    r"removed|deprecated|limitation|except)\b",
    re.IGNORECASE,
)

# Table access column normalizer — replaces "Read", "Write", "Read/Write" cell content
# (between | delimiters) with "-" before scanning.  Uses lookahead/lookbehind so the
# shared | between adjacent cells is not consumed, allowing both cells to be matched
# in a single re.sub pass even when they share a delimiter (e.g. "| Read | Write |").
_TABLE_ACCESS_COL_RE = re.compile(
    r"(?<=\|)\s*(?:Read(?:/Write)?|Write)\s*(?=\|)",
    re.IGNORECASE,
)

# Severity by subdomain
_SEVERITY: dict[str, str] = {
    "reference": "FAIL",
    "products": "FAIL",
    "kb": "WARN",
    "blog": "WARN",
    "docs": "INFO",
}


def _load_formats(family: str, platform: str) -> dict[str, str]:
    """Load formats.json and build a format→direction lookup.

    Direction values: "import", "export", "both", "detect", "none".
    Multiple entries for the same format are merged (import+export→both).
    """
    for subdir in ("merged", "scout"):
        path = KNOWLEDGE_ROOT / family / platform / subdir / "formats.json"
        if path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                break
            except (json.JSONDecodeError, OSError):
                continue
    else:
        return {}

    lookup: dict[str, str] = {}
    for entry in raw:
        # Handle both "format" and "extension" key styles
        ext = (entry.get("format") or entry.get("extension") or "").lower()
        direction = (entry.get("direction") or entry.get("support") or "").lower()

        if not ext:
            continue

        # Normalize enum_only: the enum constant exists for identification.
        # If functional == False, the constant is a stub (cannot read or write).
        # If functional is absent or True, reading is supported (direction = import).
        if direction == "enum_only":
            functional = entry.get("functional", None)
            if functional is False:
                direction = "none"
            else:
                direction = "import"

        existing = lookup.get(ext)
        if existing is None:
            lookup[ext] = direction
        elif existing != direction:
            # Don't upgrade to "both" if either entry is "none" — a non-functional
            # enum_only stub from one direction does not add real capability.
            if direction == "none":
                pass  # keep existing
            elif existing == "none":
                lookup[ext] = direction  # replace none with actual direction
            # Merge: if one says import and another says export → both
            elif {existing, direction} <= {"import", "export"}:
                lookup[ext] = "both"
            elif "both" in (existing, direction) or "read/write" in (existing, direction):
                lookup[ext] = "both"
            elif "detect" in (existing, direction):
                # detect is weaker than import/export — keep the stronger
                other = direction if existing == "detect" else existing
                if other in ("import", "export", "both", "read/write"):
                    lookup[ext] = other
            # else keep existing (first wins for unusual combos)

    return lookup


def _claim_direction(text: str, start: int, end: int) -> str | None:
    """Guess claimed direction from context around the format mention."""
    # 80 chars before and after the format match
    window_start = max(0, start - 80)
    window = text[window_start:end + 80]

    has_export = bool(_EXPORT_VERB_RE.search(window))
    has_import = bool(_IMPORT_VERB_RE.search(window))
    has_both = bool(_BOTH_VERB_RE.search(window))

    if has_both or (has_export and has_import):
        return "both"
    if has_export:
        return "export"
    if has_import:
        return "import"
    return None


def _direction_compatible(claimed: str, actual: str) -> bool:
    """Check if a claimed direction is compatible with the actual direction."""
    if actual in ("both", "read/write"):
        return True
    if claimed == actual:
        return True
    if actual == "detect":
        return False  # detect means identification only, no I/O
    if actual == "none":
        return False
    return False


class CapabilityClaimCheckEvaluator(BaseEvaluator):
    name = "capability_claim_check"

    def evaluate(self, page: Page, knowledge: Any) -> list[Finding]:
        if not page.family or not page.platform:
            return []

        format_lookup = _load_formats(page.family, page.platform)
        if not format_lookup:
            return []

        level = _SEVERITY.get(page.subdomain, "WARN")
        findings: list[Finding] = []

        from .version_claim_check import _extract_scannable_lines

        for line_no, text in _extract_scannable_lines(page):
            # Normalize table access columns ("| Read |", "| Write |") to neutral "| - |"
            # before scanning, preventing column headers from polluting direction context.
            scan_text = _TABLE_ACCESS_COL_RE.sub(" - ", text)

            # Skip negation context
            if _NEGATION_RE.search(scan_text):
                continue

            for m in _FORMAT_TOKEN_RE.finditer(scan_text):
                fmt = m.group(1).lower()
                actual_direction = format_lookup.get(fmt)

                if actual_direction is None:
                    continue  # Unknown format — handled by format_truth

                # Prose guards: skip type-annotation and inline-formatting contexts.
                # doc: Type → not a capability claim; `csv`, *pdf*, _odt_ → inline span.
                tail = scan_text[m.end():]
                if tail.lstrip().startswith(":"):
                    continue
                pre_char = scan_text[m.start() - 1 : m.start()] if m.start() > 0 else ""
                if pre_char in ("*", "`", "_") and tail[:1] == pre_char:
                    continue

                claimed = _claim_direction(scan_text, m.start(), m.end())
                if claimed is None:
                    continue  # No direction claim detected

                if not _direction_compatible(claimed, actual_direction):
                    findings.append(Finding(
                        level=level,
                        category="CF",
                        filepath=str(page.filepath),
                        line_no=line_no,
                        message=(
                            f"Claims {fmt.upper()} {claimed} but knowledge says "
                            f"direction is '{actual_direction}'"
                        ),
                        suggestion=(
                            f"Verify {fmt.upper()} capabilities against formats.json. "
                            f"Actual direction: {actual_direction}"
                        ),
                        evaluator=self.name,
                    ))

        return findings