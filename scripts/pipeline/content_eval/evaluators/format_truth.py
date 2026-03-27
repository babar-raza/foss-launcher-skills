"""Format truth evaluator — comprehensive check of format support claims vs formats.json.

Scans both prose lines and code blocks for format extension mentions and
direction claims (import / export / convert).  Cross-references every
mentioned format against the product's ``formats.json`` knowledge file:

* Unknown formats → INFO
* Direction mismatch (e.g. claiming export when knowledge says import-only) → WARN
* Claiming bidirectional support when only one direction is known → WARN
* Many unknown formats on a structured page → WARN
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..models import Finding, Page
from . import BaseEvaluator

KNOWLEDGE_ROOT = Path("knowledge")

# Broad list of format extensions to watch for
_KNOWN_EXTENSIONS = {
    "obj", "fbx", "gltf", "glb", "stl", "ply", "3mf", "dae", "x3d",
    "pptx", "ppt", "odp", "xlsx", "xls", "ods", "docx", "doc", "odt",
    "pdf", "html", "svg", "png", "jpg", "jpeg", "gif", "bmp", "tiff",
    "mp4", "mp3", "wav",
    # additional common formats
    "u3d", "amf", "rvm", "ma", "mb", "blend", "draco",
    "zip", "tar", "gz",
}

# Regex: matches format extensions used as tokens (case-insensitive)
# e.g.  OBJ, .obj, *.obj, "FBX", 'gltf'
_FORMAT_TOKEN_RE = re.compile(
    r"(?<![a-zA-Z])(?:\*\.|\.)?" + r"(" +
    "|".join(re.escape(ext) for ext in sorted(_KNOWN_EXTENSIONS, key=len, reverse=True)) +
    r")" + r"(?![a-zA-Z0-9])",
    re.IGNORECASE,
)

# Direction verbs preceding a format reference
_EXPORT_VERB_RE = re.compile(
    r"\b(?:export|save|write|convert\s+to|render\s+to)\b",
    re.IGNORECASE,
)
_IMPORT_VERB_RE = re.compile(
    r"\b(?:import|load|read|open|convert\s+from|parse)\b",
    re.IGNORECASE,
)
_BOTH_VERB_RE = re.compile(
    r"\b(?:support|handle|process|convert)\b",
    re.IGNORECASE,
)


_EXT_RE = re.compile(r"^[a-z0-9]{2,6}$")


def _is_enum_name_schema(entries: list[dict]) -> bool:
    """Return True when formats.json uses enum names (e.g. OneNote2010) not file extensions.

    Heuristic: if every non-empty format/ext value either contains uppercase letters
    or is longer than 8 characters, the schema is enum-based and extension matching
    will produce only false positives.
    """
    keys = []
    for entry in entries:
        key = (entry.get("format") or entry.get("ext") or "").lstrip(".")
        if key:
            keys.append(key)
    if not keys:
        return False
    return all(not _EXT_RE.match(k) for k in keys)


def _load_formats(family: str, platform: str) -> dict[str, str]:
    """Return dict ext → direction string ("import", "export", "both", ...).

    Returns an empty dict when formats.json is absent, unreadable, or uses
    an enum-name schema (e.g. OneNote2010 / OneNoteOnline) rather than file
    extensions.  Enum-name schemas produce only false positives for extension
    matching so we skip them entirely.
    """
    path = KNOWLEDGE_ROOT / family / platform / "merged" / "formats.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, TypeError):
        return {}

    # Skip extension matching when the schema uses enum names, not extensions
    if _is_enum_name_schema(data):
        return {}

    result: dict[str, str] = {}
    for entry in data:
        ext = (entry.get("format") or entry.get("ext") or "").lower().lstrip(".")
        if not ext:
            continue
        direction = (entry.get("direction") or entry.get("support") or "").lower()
        if not direction:
            # Infer from boolean fields
            can_import = entry.get("import", False)
            can_export = entry.get("export", False)
            if can_import and can_export:
                direction = "both"
            elif can_import:
                direction = "import"
            elif can_export:
                direction = "export"
            else:
                direction = "none"
        result[ext] = direction
    return result


def _extract_format_mentions(text: str) -> list[tuple[str, int]]:
    """Return list of (ext_lower, start_pos) for every format token found."""
    return [(m.group(1).lower(), m.start()) for m in _FORMAT_TOKEN_RE.finditer(text)]


def _claim_direction(context: str) -> str | None:
    """Guess claimed direction from surrounding context text.

    Returns "export", "import", "both", or None if unclear.
    """
    window = context[-80:] + context[:80]  # look before and after
    has_export = bool(_EXPORT_VERB_RE.search(window))
    has_import = bool(_IMPORT_VERB_RE.search(window))
    has_both = bool(_BOTH_VERB_RE.search(window))

    if has_export and has_import:
        return "both"
    if has_export:
        return "export"
    if has_import:
        return "import"
    if has_both:
        return "both"
    return None


class FormatTruthEvaluator(BaseEvaluator):
    """Comprehensive check that format support claims match formats.json knowledge.

    More thorough than prose_truth's format check: scans code blocks in
    addition to prose, uses a broad format list, and reports direction
    mismatches at the WARN level (separate FT category).
    """

    name = "format_truth"

    def evaluate(self, page: Page, knowledge: Any) -> list[Finding]:
        if not page.family or not page.platform:
            return []

        format_direction = _load_formats(page.family, page.platform)
        if not format_direction:
            return []  # No format knowledge available

        findings: list[Finding] = []
        # Track per-page stats for the "many unknown" check
        unknown_formats: set[str] = set()
        all_mentioned: set[str] = set()
        # Deduplicate (format, direction_claim) pairs already reported
        reported: set[tuple[str, str]] = set()

        def _check(ext: str, claimed_dir: str | None, line_no: int, source: str):
            all_mentioned.add(ext)
            known_dir = format_direction.get(ext)

            if known_dir is None:
                # Format not found in knowledge at all
                unknown_formats.add(ext)
                key = (ext, "unknown")
                if key not in reported:
                    reported.add(key)
                    findings.append(Finding(
                        level="INFO",
                        category="FT",
                        filepath=str(page.filepath),
                        line_no=line_no,
                        message=f"Format {ext.upper()} mentioned but not found in formats.json",
                        suggestion=(
                            f"Verify that {ext.upper()} is supported by this product "
                            f"or remove the reference"
                        ),
                        evaluator=self.name,
                    ))
                return

            if claimed_dir is None:
                return  # No direction context; can't check mismatch

            # Direction mismatch checks
            if claimed_dir == "export" and known_dir == "import":
                key = (ext, "export-mismatch")
                if key not in reported:
                    reported.add(key)
                    findings.append(Finding(
                        level="WARN",
                        category="FT",
                        filepath=str(page.filepath),
                        line_no=line_no,
                        message=(
                            f"Claims {ext.upper()} export but formats.json shows import-only"
                        ),
                        suggestion=f"Fix direction: {ext.upper()} only supports import",
                        evaluator=self.name,
                    ))
            elif claimed_dir == "import" and known_dir == "export":
                key = (ext, "import-mismatch")
                if key not in reported:
                    reported.add(key)
                    findings.append(Finding(
                        level="WARN",
                        category="FT",
                        filepath=str(page.filepath),
                        line_no=line_no,
                        message=(
                            f"Claims {ext.upper()} import but formats.json shows export-only"
                        ),
                        suggestion=f"Fix direction: {ext.upper()} only supports export",
                        evaluator=self.name,
                    ))
            elif claimed_dir == "both" and known_dir in ("import", "export"):
                key = (ext, "both-mismatch")
                if key not in reported:
                    reported.add(key)
                    findings.append(Finding(
                        level="WARN",
                        category="FT",
                        filepath=str(page.filepath),
                        line_no=line_no,
                        message=(
                            f"Claims bidirectional {ext.upper()} support but "
                            f"formats.json shows {known_dir}-only"
                        ),
                        suggestion=(
                            f"Clarify that {ext.upper()} is {known_dir}-only, "
                            f"not both import and export"
                        ),
                        evaluator=self.name,
                    ))

        # --- Scan prose lines ---
        for line_no, line_text in page.prose_lines:
            mentions = _extract_format_mentions(line_text)
            for ext, pos in mentions:
                # Build context around the position for direction detection
                before = line_text[max(0, pos - 60) : pos]
                after = line_text[pos : min(len(line_text), pos + 40)]
                claimed_dir = _claim_direction(before + after)
                _check(ext, claimed_dir, line_no, "prose")

        # --- Scan code blocks ---
        for block in page.code_blocks:
            for ext, pos in _extract_format_mentions(block.content):
                before = block.content[max(0, pos - 60) : pos]
                after = block.content[pos : min(len(block.content), pos + 40)]
                claimed_dir = _claim_direction(before + after)
                _check(ext, claimed_dir, block.start_line, "code")

        # Aggregate: many unknown formats on a structured page
        if page.page_role in ("docs", "reference") and len(all_mentioned) >= 5:
            if len(unknown_formats) > 2:
                findings.append(Finding(
                    level="WARN",
                    category="FT",
                    filepath=str(page.filepath),
                    line_no=1,
                    message=(
                        f"Multiple formats mentioned that are not in knowledge model: "
                        f"{', '.join(sorted(f.upper() for f in unknown_formats))}"
                    ),
                    suggestion=(
                        "Review formats.json or remove unverified format references"
                    ),
                    evaluator=self.name,
                ))

        return findings
