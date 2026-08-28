"""
refresh_oracle.py — S-106: Validate refreshed content against source truth.

COMPOSES prose_stale_scan.py (C-005) — does NOT re-implement stale detection.

Validations performed:
  1. Stale claim absence — no removed API symbols in body (via prose_stale_scan.py)
  2. API symbol validity — every backtick API token must exist in api_surface.json
  3. Frontmatter/body consistency — format claims must not contradict each other
  4. Heading structure integrity — no orphan H3s without parent H2
  5. Cross-page propagation check — rerun body_impact; queue any DEFINITE impacts missed

CLI:
    PYTHONPATH=scripts/pipeline python -m commands.content.refresh_oracle pdf net
    PYTHONPATH=scripts/pipeline python -m commands.content.refresh_oracle pdf net \\
        --receipts reports/refresh_review/pdf/net/receipts/

Output per page:
    reports/refresh_review/{family}/{platform}/oracle_verdicts/*.yaml

Verdict schema:
    refresh_oracle_verdict:
      page_path: ...
      source_revision: ...
      claims_checked: 24
      body_sections_checked: 5
      examples_checked: 3
      failures: []
      verdict: PASS | FAIL
"""

from pathlib import Path
import sys

_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))
_LIB_DIR = str(_PIPELINE_ROOT / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

import argparse
import glob
import hashlib
import json
import re
import yaml
from datetime import datetime, timezone
from typing import Any

# ── Configurable defaults ──────────────────────────────────────────────────

_cfg_reports_root: str = "reports/refresh_review"
_cfg_knowledge_root: str = "knowledge"
_cfg_gap_analysis_root: str = "reports/gap-analysis"
_cfg_prose_scan_fn: Any = None  # injectable for tests


def configure(
    reports_root: str | None = None,
    knowledge_root: str | None = None,
    gap_analysis_root: str | None = None,
    prose_scan_fn: Any = None,
) -> None:
    """Override dependencies for testing."""
    global _cfg_reports_root, _cfg_knowledge_root, _cfg_gap_analysis_root, _cfg_prose_scan_fn
    if reports_root is not None:
        _cfg_reports_root = reports_root
    if knowledge_root is not None:
        _cfg_knowledge_root = knowledge_root
    if gap_analysis_root is not None:
        _cfg_gap_analysis_root = gap_analysis_root
    if prose_scan_fn is not None:
        _cfg_prose_scan_fn = prose_scan_fn


# ── Finding constants ──────────────────────────────────────────────────────

FINDING_STALE_API = "STALE_API_IN_BODY"
FINDING_INVALID_SYMBOL = "INVALID_SYMBOL"
FINDING_FM_CONTRADICTION = "FRONTMATTER_BODY_CONTRADICTION"
FINDING_ORPHAN_HEADING = "ORPHAN_H3_WITHOUT_H2"
FINDING_MISSED_IMPACT = "MISSED_IMPACT_DETECTED"

VERDICT_PASS = "PASS"
VERDICT_FAIL = "FAIL"

# API symbol pattern (backtick-quoted)
_BACKTICK_API_RE = re.compile(r"`([A-Z][A-Za-z0-9_]*(?:\.[A-Z][A-Za-z0-9_]*)*)`")
_HEADING_RE = re.compile(r"^(#{1,6})\s+")
_FRONTMATTER_SEP = re.compile(r"^---\s*$")


# ── Loaders ────────────────────────────────────────────────────────────────

def _load_api_surface(family: str, platform: str) -> set[str]:
    """Return known API tokens from api_surface.json."""
    path = Path(_cfg_knowledge_root) / family / platform / "merged" / "api_surface.json"
    if not path.exists():
        return set()
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        tokens: set[str] = set()
        if isinstance(data, list):
            for entry in data:
                name = entry.get("name", "")
                if name:
                    tokens.add(name)
                class_import = entry.get("class_import", "")
                if class_import:
                    tokens.add(class_import)
                namespace = entry.get("canonical_namespace", "")
                if namespace:
                    parts = namespace.split(".")
                    for i in range(1, len(parts) + 1):
                        tokens.add(".".join(parts[:i]))
                    tokens.add(parts[-1])
                for base in entry.get("bases", []) or []:
                    if base:
                        tokens.add(str(base))
                        tokens.add(str(base).split(".")[-1])
                for enum_member in entry.get("enum_members", []) or []:
                    member_name = enum_member.get("name") if isinstance(enum_member, dict) else str(enum_member)
                    if member_name:
                        tokens.add(member_name)
                        if name:
                            tokens.add(f"{name}.{member_name}")
                for method in entry.get("methods", []) or []:
                    if method.get("name"):
                        tokens.add(method["name"])
                        if name:
                            tokens.add(f"{name}.{method['name']}")
                for prop in entry.get("properties", []) or []:
                    if prop.get("name"):
                        tokens.add(prop["name"])
                        if name:
                            tokens.add(f"{name}.{prop['name']}")
                    if prop.get("type"):
                        tokens.add(str(prop["type"]).rstrip("?"))
            return tokens
        if isinstance(data, dict):
            return set(data.keys())
    except Exception:
        pass
    return set()


def _load_receipts(receipts_dir: str | None, family: str, platform: str) -> list[dict]:
    """Load all receipt YAML files from the receipts directory."""
    if receipts_dir is None:
        receipts_dir = str(Path(_cfg_reports_root) / family / platform / "receipts")
    receipts: list[dict] = []
    receipts_path = Path(receipts_dir)
    if not receipts_path.exists():
        return receipts
    for f in receipts_path.glob("*.yaml"):
        try:
            with open(f, encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
            if isinstance(data, dict) and "content_refresh_receipt" in data:
                receipts.append(data["content_refresh_receipt"])
        except Exception:
            continue
    return receipts


def _load_prose_stale_results(family: str, platform: str) -> dict:
    """Load prose_stale_scan output (composed — not re-implemented)."""
    path = Path(_cfg_gap_analysis_root) / f"{family}-{platform}-prose-stale.json"
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


# ── Validators ─────────────────────────────────────────────────────────────

def _read_page_body(page_path: str) -> tuple[str, str]:
    """Return (frontmatter_text, body_text)."""
    content = Path(page_path).read_text(encoding="utf-8")
    lines = content.splitlines(keepends=True)
    if not lines or not _FRONTMATTER_SEP.match(lines[0]):
        return "", content
    for i in range(1, len(lines)):
        if _FRONTMATTER_SEP.match(lines[i]):
            return "".join(lines[1:i]), "".join(lines[i + 1:])
    return "", content


def _validate_stale_absence(page_path: str, prose_stale_results: dict) -> list[dict]:
    """Return findings for stale API references found by prose_stale_scan."""
    findings: list[dict] = []
    hits = prose_stale_results.get("hits", [])
    for hit in hits:
        if hit.get("file") == page_path or hit.get("path") == page_path:
            findings.append(
                {
                    "finding_type": FINDING_STALE_API,
                    "detail": f"Stale API reference: {hit.get('symbol', '?')} "
                              f"at line {hit.get('lineno', '?')}",
                    "location": hit.get("lineno", 0),
                    "confidence": hit.get("confidence", 0.80),
                }
            )
    return findings


# RPR-ST089-01: bare-word literal/keyword tokens that are never API symbols
# regardless of family/platform -- Python's `None`/`True`/`False` keywords,
# Excel formula boolean literals (`TRUE`/`FALSE`), and the common builtin
# exception names a Python product's error-handling prose routinely cites
# by name (e.g. "raises `FileNotFoundError`"). None of these collide with a
# real class name in any product's api_surface.json (verified spot-check
# against cells/python's), and _BACKTICK_API_RE's `[A-Z]` start requirement
# means every one of them looks exactly like a claimed API-symbol reference
# to the naive matcher.
_LITERAL_AND_BUILTIN_TOKENS = {
    "None", "True", "False", "TRUE", "FALSE",
    "AttributeError", "TypeError", "ValueError", "KeyError", "IndexError",
    "FileNotFoundError", "NotImplementedError", "UnicodeDecodeError",
    "UnicodeEncodeError", "RuntimeError", "StopIteration", "ImportError",
    "OSError", "IOError", "ZeroDivisionError", "OverflowError",
    "MemoryError", "NameError", "PermissionError", "TimeoutError",
    "ConnectionError", "ArithmeticError", "LookupError",
    # Found live 2026-08-27, barcode/python: correct Python-version-compat
    # prose ("If you see `SyntaxError` or import failures, verify your
    # Python version") produced a false INVALID_SYMBOL finding -- the set
    # above was not exhaustive over Python's builtin exception hierarchy.
    "SyntaxError",
}

# RPR-ST089-02: a token made ENTIRELY of hex digit characters (0-9, A-F), in
# a byte-aligned length (2, 4, 6, or 8 characters), is overwhelmingly more
# likely to be an ARGB/RGB hex color literal or a single hex byte (e.g.
# `FF1E64C8`, `FFFFFFFF`, or bare `FF` for "fully opaque alpha") than a real
# class name -- real PascalCase API class names virtually always contain at
# least one letter outside A-F, and a genuine 2-letter class name is not a
# real-world shape this codebase uses anywhere. Found live 2026-08-18,
# cells/python: a correct styling guide citing hex color literals (8-digit)
# and the bare alpha-byte shorthand (2-digit) in backticks produced 15
# false INVALID_SYMBOL findings on a single page.
_HEX_LITERAL_RE = re.compile(r"^(?:[0-9A-F]{2}){1,4}$")

# RPR-ST091-02: a capitalized backtick token on a line that also names an
# external product/library by a possessive brand reference ("Microsoft's
# X", "Google's Y") or explicit third-party phrasing is very likely THAT
# external product's own class/API name, not this codebase's api_surface --
# general, not tied to any one vendor, so it generalizes to future content
# without needing a new allowlist entry per external library. Found live
# 2026-08-18, cells/python: "The optional `markitdown-aspose-cells-plugin`
# package integrates with Microsoft's MarkItDown library... use it
# transparently via the `MarkItDown` API" flagged `MarkItDown` as an
# unknown symbol -- it's Microsoft's own library, correctly named in a
# plugin-integration note, not a cells/python class.
#
# Scope is deliberately the SAME LINE as the match only (mirrors
# triage_confirm's RPR-ST091-01 negation-context guard) -- a page-wide
# scan risks suppressing a genuinely wrong claim elsewhere on the page
# merely because an unrelated brand name appears somewhere else on it.
_EXTERNAL_BRAND_POSSESSIVE_RE = re.compile(
    r"\b[A-Z][A-Za-z0-9]+(?:\.[A-Z][A-Za-z0-9]+)*'s\b"  # "Microsoft's", "Adobe's" -- deliberately case-SENSITIVE (lowercase "it's"/"let's" must never match)
)
_EXTERNAL_LIBRARY_PHRASE_RE = re.compile(
    r"\bthird[- ]party\b|\bexternal (?:library|libraries|tool|package)\b",
    re.IGNORECASE,
)


def _has_external_brand_context(line: str) -> bool:
    return bool(
        _EXTERNAL_BRAND_POSSESSIVE_RE.search(line)
        or _EXTERNAL_LIBRARY_PHRASE_RE.search(line)
    )

# RPR-ST089-03: a LETTER+DIGITS token (e.g. `B5`, `D5`, `AB123`) is a
# spreadsheet cell-address reference, not an API symbol -- extremely common
# in a spreadsheet product's prose ("apply the style to cell `B5`") and
# never a real class name shape (api_surface class names don't end in
# digits following a 1-3 letter prefix with no other letters).
_CELL_ADDRESS_RE = re.compile(r"^[A-Z]{1,3}[0-9]{1,7}$")


def _validate_api_symbols(page_path: str, api_surface: set[str]) -> list[dict]:
    """Return findings for backtick symbols not in api_surface."""
    if not api_surface:
        return []  # can't validate without api surface
    _, body = _read_page_body(page_path)
    findings: list[dict] = []
    framework_tokens = {
        "Stream", "MemoryStream", "FileStream", "StringBuilder", "DateTime",
        "TimeSpan", "Task", "IEnumerable", "IList", "List", "Dictionary",
        "HashSet", "Func", "Action", "IDisposable", "Exception",
        "IndexOutOfRangeException", "NotImplementedException",
        "NullReferenceException",
        "UnsupportedOperationException", "FileNotFoundException", "IOException",
        "NullPointerException", "IndexOutOfBoundsException", "InputStream", "OutputStream",
        # JDK in-memory stream subclasses -- InputStream/OutputStream (above)
        # were already allowlisted, but not their ByteArray* concrete
        # subclasses, a routine, correct pairing for in-memory I/O examples.
        # Found live 2026-08-24, pdf/java's developer-guide/io.md.
        "ByteArrayInputStream", "ByteArrayOutputStream",
        # java.awt/java.awt.image stdlib types referenced by real
        # graphics/rendering-related classes (BlendComposite, GraphicsState,
        # PdfPageRenderer, PdfViewer, XImage) whose method signatures
        # genuinely take or return these JDK types -- not aspose-pdf API
        # classes, so absent from api_surface.json by design. Found live
        # 2026-08-25, pdf/java's Task 14 upstream proof run (mission-plan-
        # the-end-to-end-vast-hejlsberg.md): `CompositeContext` is
        # `BlendComposite.createContext()`'s real return type (implements
        # `java.awt.Composite`); `BasicStroke`/`BufferedImage` are standard
        # AWT/AWT-image types used correctly in prose describing rendering
        # output.
        "CompositeContext", "BasicStroke", "BufferedImage",
        # Python stdlib email.message.EmailMessage -- MapiMessage's own
        # from_email_message()/to_email_message() methods genuinely take and
        # return this stdlib type for MSG<->EML interop, so it's a correct
        # reference in prose/code describing those methods, not an
        # aspose-email-foss API class (absent from api_surface.json by
        # design, same reasoning as the JDK AWT types above). Found live
        # 2026-08-28, email/python's MapiMessage.md reference page.
        "EmailMessage",
        # TypeScript/DOM standard lib.dom.d.ts Document interface --
        # DOMParser.parseFromString()'s own real return type, not an
        # aspose-cells-foss API class. Same accepted precision/recall
        # tradeoff as every other entry in this set: a hypothetical Aspose
        # product with its own real "Document" class would also have that
        # citation skipped, same as already-accepted "Stream"/"Exception"/
        # "List" above. Found live 2026-08-28, cells/typescript's
        # DOMParser.md reference page.
        "Document",
    }
    content_tokens = {
        "Bmp", "Jpeg", "Png", "Tiff", "Gif", "Emf", "LICENSE",
        "AF_Date_Format", "AF_Number_Format", "AF_Percent_Format",
        "HH", "MM", "Q", "THead", "TBody", "TFoot", "NextPage", "PrevPage",
        "X", "Y", "Z", "Sheet1",
        "Double.MAX_VALUE", "Double.MIN_VALUE",
        # Standard PDF spec annotation Subtype string-literal values (passed
        # as the `subtype` argument to e.g. AnnotationCollection.add(), never
        # importable classes) -- confirmed live 2026-08-17, pdf/python: a
        # correct prose sentence enumerating valid subtypes ("...such as
        # `Square`, `Circle`, `Line`, `Highlight`, or `FreeText`...") was
        # wrongly flagged as 5 INVALID_SYMBOL findings because every
        # backtick span is treated as a claimed API-symbol reference by
        # default. Full set per aspose_pdf/document.py's own
        # generate_appearances() docstring plus the PDF spec's fixed
        # Annotation Subtype enumeration; none collide with a real
        # api_surface class name (verified against pdf/python's own
        # api_surface.json).
        "Square", "Circle", "Line", "Polygon", "PolyLine", "Ink",
        "Highlight", "Underline", "StrikeOut", "Squiggly", "FreeText",
        # License-name and ARGB-format-notation tokens -- neither is ever a
        # real API class. "AARRGGBB" is the byte-order NAME for an ARGB hex
        # literal (Alpha-Red-Green-Blue), not itself valid hex (contains
        # G), so it doesn't match _HEX_LITERAL_RE and needs an explicit
        # entry. Found live 2026-08-18, cells/python.
        "MIT", "AARRGGBB",
        # Bare single-letter spreadsheet column references ("apply
        # formatting to column `C`") -- a real api_surface class name is
        # never a single uppercase letter, matching the existing
        # X/Y/Z (axis-label) precedent above for the same reasoning.
        "A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M",
        "N", "O", "P", "Q", "R", "S", "T", "U", "V", "W",
        # PDF content-stream operator codes (ISO 32000-1 §A.2) -- raw PDF
        # syntax tokens explaining the format itself, never Java class
        # names, e.g. "text operators (`BT`, `ET`, `Tf`, `Tj`)". `Tf`/`Tj`
        # match _BACKTICK_API_RE's `[A-Z][A-Za-z0-9_]*` shape (start
        # uppercase, one lowercase letter) the same way a real 2-letter
        # PascalCase-looking token would; `BT`/`ET` are all-caps and were
        # not observed triggering a finding. Found live 2026-08-24, pdf/java's
        # developer-guide/operators.md and the kb how-to-work-with-operators
        # page -- same operator table in prose on both.
        "Tf", "Tj", "BT", "ET", "Td", "TD", "Tm", "TJ", "Tc", "Tw", "Tz",
        "TL", "Tr", "Ts",
    }
    for i, line in enumerate(body.splitlines(), start=1):
        for m in _BACKTICK_API_RE.finditer(line):
            token = m.group(1)
            base = token.split(".")[0]  # ClassName part only
            if token in framework_tokens or base in framework_tokens:
                continue
            if token in content_tokens:
                continue
            if token in _LITERAL_AND_BUILTIN_TOKENS:
                continue
            if _HEX_LITERAL_RE.match(token) or _CELL_ADDRESS_RE.match(token):
                continue
            if _has_external_brand_context(line):
                continue
            if token.startswith("Aspose.Pdf") and any(
                candidate == token or candidate.startswith(token + ".")
                for candidate in api_surface
            ):
                continue
            if base not in api_surface and token not in api_surface:
                findings.append(
                    {
                        "finding_type": FINDING_INVALID_SYMBOL,
                        "detail": f"Symbol `{token}` not found in api_surface",
                        "location": i,
                        "confidence": 0.70,
                    }
                )
    return findings


def _validate_heading_structure(page_path: str) -> list[dict]:
    """Return findings for orphan H3s (H3 without a preceding H2)."""
    _, body = _read_page_body(page_path)
    findings: list[dict] = []
    has_h2 = False
    for i, line in enumerate(body.splitlines(), start=1):
        m = _HEADING_RE.match(line)
        if not m:
            continue
        level = len(m.group(1))
        if level == 2:
            has_h2 = True
        elif level == 3 and not has_h2:
            findings.append(
                {
                    "finding_type": FINDING_ORPHAN_HEADING,
                    "detail": f"H3 heading at line {i} has no preceding H2",
                    "location": i,
                    "confidence": 0.90,
                }
            )
    return findings


def _validate_frontmatter_body_consistency(page_path: str) -> list[dict]:
    """Return findings for frontmatter/body format contradictions."""
    fm_text, body = _read_page_body(page_path)
    findings: list[dict] = []
    try:
        fm = yaml.safe_load(fm_text) or {}
    except Exception:
        return findings

    evidence = fm.get("evidence", {}) or {}
    fm_formats: set[str] = set()
    for fmt_item in evidence.get("formats", []) or []:
        if isinstance(fmt_item, dict):
            name = fmt_item.get("format", fmt_item.get("name", ""))
        else:
            name = str(fmt_item)
        if name:
            fm_formats.add(name.upper())

    # Check for "does not support X" in body where X is in fm_formats
    body_lower = body.lower()
    for fmt in fm_formats:
        patterns = [
            f"does not support {fmt.lower()}",
            f"cannot convert to {fmt.lower()}",
            f"{fmt.lower()} is not supported",
        ]
        for pat in patterns:
            if pat in body_lower:
                findings.append(
                    {
                        "finding_type": FINDING_FM_CONTRADICTION,
                        "detail": f"Frontmatter lists {fmt} as supported but body claims otherwise",
                        "location": 0,
                        "confidence": 0.80,
                    }
                )
    return findings


# ── Cross-page propagation check ────────────────────────────────────────────

def _run_cross_page_propagation_check(family: str, platform: str) -> list[dict]:
    """
    Rerun body_impact logic to discover any DEFINITE impacts missed by body_refresh.
    Returns list of missed-impact findings.
    """
    try:
        from commands.content.body_impact import _load_semantic_changes, _load_claim_maps, _build_impact_entries
    except ImportError:
        return []

    try:
        changes = _load_semantic_changes(family, platform)
        claim_maps = _load_claim_maps(family, platform)
        impacts = _build_impact_entries(changes, claim_maps, None)
    except FileNotFoundError:
        return []

    missed: list[dict] = []
    for impact in impacts:
        definite_sections = [
            s for s in impact.get("affected_sections", [])
            if s.get("impact_level") == "DEFINITE"
        ]
        if definite_sections:
            missed.append(
                {
                    "finding_type": FINDING_MISSED_IMPACT,
                    "page_path": impact["page_path"],
                    "detail": f"DEFINITE impact on {len(definite_sections)} section(s) may not have been refreshed",
                    "sections": [s["section_id"] for s in definite_sections],
                }
            )
    return missed


# ── Oracle verdict emission ─────────────────────────────────────────────────

def _emit_verdict(
    page_path: str,
    findings: list[dict],
    family: str,
    platform: str,
    sections_checked: int = 0,
    claims_checked: int = 0,
    examples_checked: int = 0,
    source_revision: str = "",
) -> dict:
    """Write verdict YAML to oracle_verdicts/ and return verdict dict."""
    verdict = VERDICT_PASS if not findings else VERDICT_FAIL
    normalized_path = page_path.replace("\\", "/")
    digest = hashlib.sha1(normalized_path.encode("utf-8")).hexdigest()[:10]
    slug_base = page_path.replace("/", "_").replace("\\", "_").replace(":", "")[:80]
    slug = f"{slug_base}_{digest}"

    verdict_data = {
        "page_path": page_path,
        "source_revision": source_revision,
        "claims_checked": claims_checked,
        "body_sections_checked": sections_checked,
        "examples_checked": examples_checked,
        "failures": findings,
        "verdict": verdict,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    verdicts_dir = Path(_cfg_reports_root) / family / platform / "oracle_verdicts"
    verdicts_dir.mkdir(parents=True, exist_ok=True)
    out_path = verdicts_dir / f"{slug}.yaml"
    with open(out_path, "w", encoding="utf-8") as f:
        yaml.dump({"refresh_oracle_verdict": verdict_data}, f, default_flow_style=False, allow_unicode=True)

    return verdict_data


def _run_prose_scan(family: str, platform: str) -> dict:
    """Run or load prose stale scan results."""
    if _cfg_prose_scan_fn is not None:
        return _cfg_prose_scan_fn(family, platform)
    # Try loading existing output first
    existing = _load_prose_stale_results(family, platform)
    if existing:
        return existing
    # Try running prose_stale_scan.run_scan() directly
    try:
        from commands.ops.prose_stale_scan import run_scan
        from pathlib import Path as _Path
        result = run_scan(_Path("."), family, platform)
        return result or {}
    except Exception:
        return {}


# ── Main run ───────────────────────────────────────────────────────────────

def run(family: str, platform: str, receipts_dir: str | None = None) -> list[dict]:
    """
    Main logic entry point (importable by tests and CLI).

    Returns list of verdict dicts (one per page checked).
    """
    receipts = _load_receipts(receipts_dir, family, platform)
    api_surface = _load_api_surface(family, platform)
    prose_stale = _run_prose_scan(family, platform)

    # Derive current_sha from model.yaml
    model_path = Path(_cfg_knowledge_root) / family / platform / "merged" / "model.yaml"
    current_sha = ""
    if model_path.exists():
        try:
            with open(model_path, encoding="utf-8") as f:
                model = yaml.safe_load(f)
            current_sha = model.get("repo_sha", "")[:12]
        except Exception:
            pass

    verdicts: list[dict] = []

    # Pages to check: either from receipts or discover all
    pages_to_check: set[str] = set()
    for receipt in receipts:
        pp = receipt.get("page_path", "")
        if pp and receipt.get("verdict") == "BODY_UPDATED":
            pages_to_check.add(pp)

    if not pages_to_check:
        # Fall back to checking all discovered pages for this product
        patterns = [
            f"content/docs.aspose.org/en/{family}/{platform}/**/*.md",
            f"content/kb.aspose.org/en/{family}/{platform}/**/*.md",
        ]
        for pat in patterns:
            pages_to_check.update(glob.glob(pat, recursive=True))

    for page_path in sorted(pages_to_check):
        if not Path(page_path).exists():
            continue

        findings: list[dict] = []

        # Validation 1: stale claim absence (composed from prose_stale_scan)
        findings.extend(_validate_stale_absence(page_path, prose_stale))

        # Validation 2: API symbol validity
        findings.extend(_validate_api_symbols(page_path, api_surface))

        # Validation 3: frontmatter/body consistency
        findings.extend(_validate_frontmatter_body_consistency(page_path))

        # Validation 4: heading structure
        findings.extend(_validate_heading_structure(page_path))

        # Count metrics
        _, body = _read_page_body(page_path)
        sections_checked = len(re.findall(r"^#{2,3}\s+", body, re.MULTILINE))
        claims_checked = len(_BACKTICK_API_RE.findall(body))
        examples_checked = body.count("```")

        verdict_data = _emit_verdict(
            page_path=page_path,
            findings=findings,
            family=family,
            platform=platform,
            sections_checked=sections_checked,
            claims_checked=claims_checked,
            examples_checked=examples_checked // 2,  # opening+closing pairs
            source_revision=current_sha,
        )
        verdicts.append(verdict_data)

    # Cross-page propagation check
    missed = _run_cross_page_propagation_check(family, platform)
    for m in missed:
        # Add to the relevant page verdict if already present
        pp = m.get("page_path", "")
        if pp in pages_to_check:
            continue
        matched = next((v for v in verdicts if v["page_path"] == pp), None)
        if matched:
            matched["failures"].append(m)
            matched["verdict"] = VERDICT_FAIL
        # Note: missed pages not already in verdicts are NOT added here
        # (they'll be picked up in next body_refresh run)

    return verdicts


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "refresh_oracle — S-106: Validate refreshed content against source truth. "
            "Composes prose_stale_scan.py (C-005) for stale detection."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  PYTHONPATH=scripts/pipeline python -m commands.content.refresh_oracle pdf net
  PYTHONPATH=scripts/pipeline python -m commands.content.refresh_oracle pdf net \\
      --receipts reports/refresh_review/pdf/net/receipts/

Writes: reports/refresh_review/{family}/{platform}/oracle_verdicts/*.yaml
        """,
    )
    parser.add_argument("family", help="Product family (e.g. pdf, 3d)")
    parser.add_argument("platform", help="Platform (e.g. net, java)")
    parser.add_argument(
        "--receipts",
        default=None,
        help="Override receipts directory path",
    )
    args = parser.parse_args()

    try:
        verdicts = run(args.family, args.platform, receipts_dir=args.receipts)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    passes = sum(1 for v in verdicts if v.get("verdict") == VERDICT_PASS)
    fails = sum(1 for v in verdicts if v.get("verdict") == VERDICT_FAIL)

    print(f"refresh_oracle: {args.family}/{args.platform}")
    print(f"  pages checked : {len(verdicts)}")
    print(f"  PASS          : {passes}")
    print(f"  FAIL          : {fails}")
    out_dir = f"reports/refresh_review/{args.family}/{args.platform}/oracle_verdicts/"
    print(f"  output        : {out_dir}")

    # RPR-ORACLE-001: a clean run() (no exception) with real per-page FAIL
    # verdicts must not exit 0 -- refresh_run.py::verify_run() derives
    # manifest["validation"]["oracle"] purely from this process's exit code
    # and has no other way to see the FAIL/PASS counts above.
    if fails:
        sys.exit(1)


if __name__ == "__main__":
    main()
