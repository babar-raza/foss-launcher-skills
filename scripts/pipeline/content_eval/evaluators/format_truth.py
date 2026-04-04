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
    # note/email formats
    "one", "msg", "eml", "mht", "mhtml", "ics", "vcf", "pst", "ost",
    # spreadsheet/cell formats
    "csv", "tsv",
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

    is_enum_schema = _is_enum_name_schema(data)

    result: dict[str, str] = {}
    for entry in data:
        raw_key = (entry.get("format") or entry.get("ext") or "").lstrip(".")
        if not raw_key:
            continue
        ext = raw_key.lower()
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
        existing = result.get(ext)
        if existing and existing != direction:
            result[ext] = "both"
        else:
            result[ext] = direction

    # For enum-name schemas (e.g., OneNote2010 instead of .one), extension
    # matching against prose will not work.  But we still return the data so
    # that callers can use it for direction lookups when the enum name itself
    # appears in content.  The caller must be aware that keys are enum names,
    # not file extensions.
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


# H-09: Site-specific severity for direction mismatches.
# Reference and products pages get FAIL (factual errors are critical there),
# other sites get WARN.
_DIRECTION_MISMATCH_SEVERITY: dict[str, str] = {
    "reference": "FAIL",
    "products": "FAIL",
    "blog": "WARN",
    "kb": "WARN",
    "docs": "WARN",
}


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

            # Direction mismatch checks — H-09: site-specific severity
            _mm_level = _DIRECTION_MISMATCH_SEVERITY.get(
                page.subdomain, "WARN"
            )
            if claimed_dir == "export" and known_dir == "import":
                key = (ext, "export-mismatch")
                if key not in reported:
                    reported.add(key)
                    findings.append(Finding(
                        level=_mm_level,
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
                        level=_mm_level,
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
                        level=_mm_level,
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
            # "detect" means the format enum exists for identification only —
            # the library can recognize the format but cannot read or write it.
            # Any claim of import, export, or both is a false capability claim.
            elif known_dir == "detect" and claimed_dir in ("import", "export", "both"):
                key = (ext, "detect-only-mismatch")
                if key not in reported:
                    reported.add(key)
                    findings.append(Finding(
                        level="FAIL",
                        category="FT",
                        filepath=str(page.filepath),
                        line_no=line_no,
                        message=(
                            f"Claims {ext.upper()} {claimed_dir} support but "
                            f"formats.json shows detect-only (no I/O capability)"
                        ),
                        suggestion=(
                            f"Remove the {claimed_dir} claim for {ext.upper()} — "
                            f"the library can only detect this format, not read or write it"
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

        # FR-17d: products_format_unsupported — products pages that mention formats
        # that are neither importable nor exportable per formats.json
        if page.subdomain == "products":
            findings.extend(
                self._check_products_format_unsupported(page, format_direction)
            )

        return findings

    # ------------------------------------------------------------------
    # FR-17d helper
    # ------------------------------------------------------------------

    # Pattern for 3-5 char uppercase format tokens (e.g. FBX, OBJ, STL, GLTF, PPTX)
    _UPPERCASE_FORMAT_RE = re.compile(
        r"(?<![A-Z])([A-Z]{3,5})(?![A-Z])",
    )

    def _check_products_format_unsupported(
        self,
        page: Page,
        format_direction: dict[str, str],
    ) -> list[Finding]:
        """Emit FAIL when a products page positively mentions a format that is
        neither importable nor exportable per formats.json.

        Only fires when formats.json is available (format_direction non-empty).
        """
        if not format_direction:
            return []

        findings: list[Finding] = []
        reported: set[str] = set()

        for line_no, line_text in page.prose_lines:
            stripped = line_text.strip()
            # Only examine bullet lines or lines with "support"/"format" context
            if not any(kw in stripped.lower() for kw in ("support", "format", "import", "export", "read", "writ", "load", "save")):
                continue
            for m in self._UPPERCASE_FORMAT_RE.finditer(stripped):
                fmt_upper = m.group(1)
                fmt_lower = fmt_upper.lower()
                # Only check formats we know about in formats.json
                if fmt_lower not in format_direction:
                    continue
                if fmt_lower in reported:
                    continue
                direction = format_direction[fmt_lower]
                # "none" direction means canImport=false AND canExport=false
                if direction == "none":
                    reported.add(fmt_lower)
                    findings.append(Finding(
                        level="FAIL",
                        category="FT",
                        filepath=str(page.filepath),
                        line_no=line_no,
                        message=(
                            f"Products page positively mentions `{fmt_upper}` but "
                            f"formats.json shows canImport=false AND canExport=false"
                        ),
                        suggestion=(
                            f"Remove the `{fmt_upper}` reference or add a clear "
                            f"'not supported' caveat — the knowledge model shows "
                            f"this format is not supported"
                        ),
                        evaluator=self.name,
                    ))

        return findings
