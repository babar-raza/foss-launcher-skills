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

# Maps enum-style canonical keys (lowercased) to their common file-extension
# equivalents so that content using "3MF" matches formats.json key "ThreeMf".
_FORMAT_ALIASES: dict[str, str] = {
    "threemf": "3mf",
    "microsoft3mf": "3mf",
}

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
# ST-029 pattern (3): "output" is added alongside the explicit export verbs so
# that "Image output ... supports BMP/GIF/..." resolves to export-only, not
# "both" (the bare "supports" in _BOTH_VERB_RE would otherwise win) — directionless
# "supports" following an "output" framing is export framing, not bidirectional.
_EXPORT_VERB_RE = re.compile(
    r"\b(?:export|save|write|convert\s+to|render\s+to|output)\b",
    re.IGNORECASE,
)
_IMPORT_VERB_RE = re.compile(
    r"\b(?:import|load|read(?!-only)|open|convert\s+from|parse|input)\b",
    re.IGNORECASE,
)
_BOTH_VERB_RE = re.compile(
    r"\b(?:support(?:s|ed)?|handle|process|convert)\b",
    re.IGNORECASE,
)


_EXT_RE = re.compile(r"^[a-z0-9]{2,6}$")

# Negation context — when a format mention is surrounded by these phrases it is
# explicitly described as unsupported and should NOT be counted as an "unknown" mention.
_NEGATION_RE = re.compile(
    r"\b(?:not\s+support|unsupport|are\s+not|is\s+not|cannot|no\s+support|"
    r"does\s+not\s+support|don't\s+support|doesn't\s+support)\b",
    re.IGNORECASE,
)

# Variant qualifiers — when a format mention is immediately preceded by one of
# these words (e.g. "binary FBX", "ASCII OBJ"), a negation on the same line
# applies to the variant, not the format as a whole.  EC-03 FP fix.
_VARIANT_QUALIFIER_RE = re.compile(
    r"\b(?:binary|ascii|text|xml|legacy|old|v[0-9]+|compressed|uncompressed"
    r"|embedded|standalone|raw|plain)\s+$",
    re.IGNORECASE,
)

# ST-029 pattern (2): "Aspose.PDF", "Aspose.Cells", etc. name the PRODUCT
# family, not a format-extension claim — even though the family name can be
# identical to a real format token (PDF is both a product family and a
# format). Real example: "Aspose.PDF FOSS ... does not support .NET
# Framework" was misread as "PDF format is not supported", when the negated
# subject is the .NET runtime, not the PDF format.
_PRODUCT_NAME_PREFIX_RE = re.compile(r"aspose\.?\s*$", re.IGNORECASE)


def _is_product_name_mention(text: str, pos: int) -> bool:
    """True if the format token whose match starts at `pos` is really part of
    an "Aspose.<Name>" product-family reference, not a format-extension claim.
    `pos` is m.start(0) from _FORMAT_TOKEN_RE, i.e. it points at the leading
    dot (or the token itself if no dot matched) — the text immediately before
    it is exactly what would precede "Aspose.PDF"'s dot."""
    return bool(_PRODUCT_NAME_PREFIX_RE.search(text[max(0, pos - 10):pos]))


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
        # Normalize enum_only: the enum constant exists for identification.
        # If functional == False, the constant is a stub (cannot read or write).
        # If functional is absent or True, reading is supported (direction = import).
        if direction == "enum_only":
            functional = entry.get("functional", None)
            if functional is False:
                direction = "none"
            else:
                direction = "import"
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
            # Don't upgrade to "both" if either entry is "none" — a non-functional
            # enum_only stub from one direction does not add real capability.
            if direction == "none":
                pass  # keep existing
            elif existing == "none":
                result[ext] = direction  # replace none with actual direction
            else:
                result[ext] = "both"
        else:
            result[ext] = direction

    # Register aliases so human-readable display names match enum canonical keys.
    for canon, alias in _FORMAT_ALIASES.items():
        if canon in result and alias not in result:
            result[alias] = result[canon]

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


_SENTENCE_BOUNDARY_RE = re.compile(r"[.!?]\s+")


def _resolve_list_direction(claimed_dir: "str | None", line_text: str, pos: int) -> "str | None":
    """ST-029 pattern (3): resolve a bare "both" claim for a format that is
    part of an enumerated list ("Image output ... supports BMP, GIF, JPEG,
    PNG, TIFF") where only the first item falls inside _claim_direction's
    narrow +/-80-char window — later items in the same list see no local
    export/import verb at all and fall back to the generic "both" from a bare
    "supports". Only applied when the narrow window itself found no
    distinguishing verb (claimed_dir == "both").

    Widens the search back to the START OF THE CURRENT SENTENCE (not the
    whole line) — a single line can hold multiple distinct sentences/claims
    (e.g. "The library reads and writes PDF. Image output ... supports BMP,
    GIF, ..."), and widening to the whole line would let an earlier,
    unrelated clause's verbs leak into a later, separate claim's direction.
    If exactly one of export/import framing appears within the current
    sentence (not both), that framing wins.
    """
    if claimed_dir != "both":
        return claimed_dir
    sentence_start = 0
    for m in _SENTENCE_BOUNDARY_RE.finditer(line_text[:pos]):
        sentence_start = m.end()
    preceding = line_text[sentence_start:pos]
    has_export = bool(_EXPORT_VERB_RE.search(preceding))
    has_import = bool(_IMPORT_VERB_RE.search(preceding))
    if has_export and not has_import:
        return "export"
    if has_import and not has_export:
        return "import"
    return claimed_dir


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

        # EC-03 Pattern 4 fix: enum reference pages (SaveFormat, SourceFormat,
        # etc.) list enum constants as API documentation — mentioning a format
        # name in the enum table is NOT a claim about I/O direction.  Suppress
        # direction-mismatch checks entirely on these pages.
        categories = page.frontmatter.get("categories") or []
        layout = page.frontmatter.get("layout", "")
        if "Enum" in categories and layout.startswith("reference"):
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

        # Regex: detects Markdown table access-column values ("| Read |",
        # "| Write |", "| Read/Write |") that should not count as I/O verbs.
        _TABLE_ACCESS_COL_RE = re.compile(
            r"\|\s*(?:Read(?:/Write)?|Write)\s*\|", re.IGNORECASE
        )

        # --- Scan prose lines ---
        for line_no, line_text in page.prose_lines:
            # Lines that explicitly state a format is NOT supported need a
            # separate check: if formats.json says it IS supported, the claim
            # is a false limitation (VBD-01 fix).
            # Direction-aware: infer what direction the negation is claiming is
            # unsupported using the WHOLE LINE context (not per-position), so
            # that verb context from any part of the line is considered.
            if _NEGATION_RE.search(line_text):
                # Determine the direction context for the whole line once
                line_neg_dir = _claim_direction(line_text)
                for ext, _pos in _extract_format_mentions(line_text):
                    known_dir = format_direction.get(ext)
                    if not known_dir or known_dir in ("none", "detect"):
                        continue  # Content correctly says it's unsupported
                    # ST-029 pattern (2): "Aspose.PDF ... does not support .NET
                    # Framework" — the negated subject is the runtime, not the
                    # format; "PDF" here names the product, not a format claim.
                    if _is_product_name_mention(line_text, _pos):
                        continue
                    # EC-03 FP fix: skip variant-qualified mentions like
                    # "binary FBX is not implemented" — the negation applies
                    # to the variant, not the format as a whole.
                    pre_text = line_text[:_pos]
                    if _VARIANT_QUALIFIER_RE.search(pre_text):
                        continue
                    # If direction is unknown we cannot determine what is being negated:
                    # prose like "is not tagged as page content" matches _NEGATION_RE
                    # but carries no format I/O claim.  Skip to avoid false positives.
                    if line_neg_dir is None:
                        continue
                    # If the negated direction is not covered by known_dir, it's correct
                    if line_neg_dir == "export" and known_dir == "import":
                        continue  # "can't export X" — correct, only import is supported
                    if line_neg_dir == "import" and known_dir == "export":
                        continue  # "can't import X" — correct, only export is supported
                    key = (ext, "false-negative-claim")
                    if key not in reported:
                        reported.add(key)
                        _neg_level = _DIRECTION_MISMATCH_SEVERITY.get(
                            page.subdomain, "WARN"
                        )
                        findings.append(Finding(
                            level=_neg_level,
                            category="FT",
                            filepath=str(page.filepath),
                            line_no=line_no,
                            message=(
                                f"Claims {ext.upper()} is not supported but "
                                f"formats.json shows {known_dir} support"
                            ),
                            suggestion=(
                                f"Remove the 'not supported' limitation for "
                                f"{ext.upper()} — formats.json confirms "
                                f"{known_dir} capability is present"
                            ),
                            evaluator=self.name,
                        ))
                continue  # Don't double-count this line as a positive claim
            # Normalize table access-column values BEFORE extracting mentions so
            # that "| Read |" / "| Write |" cells are never part of the direction
            # context window, regardless of where the format token falls on the
            # line (avoids pos-60 boundary splitting the pattern).
            scan_text = _TABLE_ACCESS_COL_RE.sub("| - |", line_text)
            mentions = _extract_format_mentions(scan_text)
            for ext, pos in mentions:
                tail = scan_text[pos + len(ext):]
                # Skip Python type-annotation context: "doc: Type" where the
                # format token is a variable name, not a file-extension claim.
                if tail.lstrip().startswith(":"):
                    continue
                # Skip Markdown inline spans (*doc*, `doc`, _doc_) where the
                # format token is a variable reference, not a format claim.
                pre_char = scan_text[pos - 1 : pos] if pos > 0 else ""
                if pre_char in ("*", "`", "_") and tail[:1] == pre_char:
                    continue
                # ST-029 pattern (2): "Aspose.PDF" names the product, not a
                # format-extension claim.
                if _is_product_name_mention(scan_text, pos):
                    continue
                before = scan_text[max(0, pos - 60) : pos]
                after = scan_text[pos : min(len(scan_text), pos + 40)]
                claimed_dir = _claim_direction(before + after)
                claimed_dir = _resolve_list_direction(claimed_dir, scan_text, pos)
                _check(ext, claimed_dir, line_no, "prose")

        # --- Scan code blocks ---
        for block in page.code_blocks:
            for ext, pos in _extract_format_mentions(block.content):
                # Skip variable-name false positives: "doc.save()", "doc = ..."
                # A format token immediately followed by ".<letter>" or " =" is
                # a Python identifier, not a file-extension mention.
                tail = block.content[pos + len(ext):]
                if tail and (
                    re.match(r"\.[a-zA-Z]", tail)   # doc.save(), doc.get_text()
                    or tail.lstrip().startswith("=")  # doc = Document(...)
                ):
                    continue
                # Skip file-path literals: "input.docx", 'report.pdf', etc.
                # These are I/O arguments, not capability claims.
                pre = block.content[max(0, pos - 30) : pos]
                if re.search(r'["\'][^"\']*\.\s*$', pre):
                    continue
                # EC-03 FP fix: limit direction context to the same line
                # within the code block to prevent cross-statement bleed
                # (e.g. a load statement picking up save() from the next line).
                line_start = block.content.rfind("\n", 0, pos) + 1
                line_end = block.content.find("\n", pos)
                if line_end == -1:
                    line_end = len(block.content)
                code_line = block.content[line_start:line_end]
                claimed_dir = _claim_direction(code_line)
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
