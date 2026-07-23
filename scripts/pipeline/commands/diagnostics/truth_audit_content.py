"""S-85: truth-audit-content — Line-level content truth audit.

<!-- CONTRACT: truth_audit_content.py
     Skill: truth-audit-content (S-85)
     Trigger: /truth-audit-content {family} {platform}
     Input: family, platform, optional --scope, --no-llm, --max-units
     Output: reports/truth-audit/{family}-{platform}-{date}.json
             reports/truth-audit/{family}-{platform}-{date}.md
             reports/truth-audit/state/{family}-{platform}.json
     Read-only: NEVER modifies content files
-->

Decomposes content pages into reviewable units (heading, paragraph, code block,
table row, list item), verifies each against clone cache + knowledge model, and
produces a structured gap ledger with stable finding IDs and evidence chains.

Usage:
    python scripts/pipeline/commands/diagnostics/truth_audit_content.py {family} {platform}
    python scripts/pipeline/commands/diagnostics/truth_audit_content.py {family} {platform} --scope docs
    python scripts/pipeline/commands/diagnostics/truth_audit_content.py {family} {platform} --no-llm
    python scripts/pipeline/commands/diagnostics/truth_audit_content.py {family} {platform} --max-units 200

Exit codes:
    0  All units VERIFIED or UNVERIFIABLE
    1  Internal error
    2  One or more CONTRADICTED or FABRICATED units found
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Imports from sibling pipeline modules (PYTHONPATH=scripts/pipeline)
# ---------------------------------------------------------------------------
_LIB_DIR = str(Path(__file__).resolve().parents[2] / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from knowledge_core import Knowledge
from content_discovery import discover_content, KNOWLEDGE_ROOT

log = logging.getLogger(__name__)

_SCRIPT_DIR = Path(__file__).resolve().parent
_DEFAULT_REPO_ROOT = _SCRIPT_DIR.parent.parent.parent.parent
_REPO_ROOT = _DEFAULT_REPO_ROOT

# ---------------------------------------------------------------------------
# Output paths
# ---------------------------------------------------------------------------
REPORTS_DIR = _REPO_ROOT / "reports" / "truth-audit"
STATE_DIR = REPORTS_DIR / "state"


def configure(*, repo_root: "Path | str | None" = None) -> None:
    """Override module-level path constants for testing."""
    global _REPO_ROOT, REPORTS_DIR, STATE_DIR
    _REPO_ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT
    REPORTS_DIR = _REPO_ROOT / "reports" / "truth-audit"
    STATE_DIR = REPORTS_DIR / "state"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SCHEMA_VERSION = 2  # v2: added claim_units, claim_verification_rate, confidence_bands, claim_type

# Unit type codes
UNIT_HEADING = "H"
UNIT_PARAGRAPH = "P"
UNIT_CODEBLOCK = "C"
UNIT_TABLEROW = "T"
UNIT_LISTITEM = "L"

ALL_UNIT_TYPES = {UNIT_HEADING, UNIT_PARAGRAPH, UNIT_CODEBLOCK, UNIT_TABLEROW, UNIT_LISTITEM}

# Verdicts
VERDICT_VERIFIED = "VERIFIED"
VERDICT_UNVERIFIABLE = "UNVERIFIABLE"
VERDICT_UNSUPPORTED = "UNSUPPORTED"
VERDICT_CONTRADICTED = "CONTRADICTED"
VERDICT_FABRICATED = "FABRICATED"

# Defect origins
ORIGIN_KNOWLEDGE_GAP = "KNOWLEDGE_GAP"
ORIGIN_GENERATION_FABRICATION = "GENERATION_FABRICATION"
ORIGIN_EVALUATOR_MISS = "EVALUATOR_MISS"
ORIGIN_SCOUT_MISS = "SCOUT_MISS"
ORIGIN_ENRICHMENT_HALLUCINATION = "ENRICHMENT_HALLUCINATION"

# Scope filters
SCOPE_MAP = {
    "products": ["products.aspose.org"],
    "docs": ["docs.aspose.org"],
    "blog": ["blog.aspose.org"],
    "kb": ["kb.aspose.org"],
    "reference": ["reference.aspose.org"],
    "all": [
        "products.aspose.org",
        "docs.aspose.org",
        "blog.aspose.org",
        "kb.aspose.org",
        "reference.aspose.org",
    ],
}

# Structural/navigational patterns that should be UNVERIFIABLE, not UNSUPPORTED
_STRUCTURAL_RE = re.compile(
    r"^(in this (?:section|article|guide|tutorial)|"
    r"the following (?:sections?|examples?|steps?|table)|"
    r"see (?:the|also)|"
    r"for more (?:information|details)|"
    r"let'?s (?:explore|look|see|start)|"
    r"below (?:is|are)|"
    r"here (?:is|are)|"
    r"this (?:section|page|article) (?:covers|explains|describes|shows))",
    re.IGNORECASE,
)

# API reference pattern for extracting identifiers from prose
# Matches `ClassName.method`, `method_name`, `method_name()`, `Class.method(args)`
_API_REF_RE = re.compile(r"`(\w+(?:\.\w+)*)(?:\([^)]*\))?`")

# Tokenizer for overlap computation
_WORD_RE = re.compile(r"[a-z][a-z0-9_]+")


def _build_method_index(knowledge: Knowledge) -> dict[str, list[str]]:
    """Build reverse index: {method_or_property_name: [class_name, ...]}."""
    index: dict[str, list[str]] = {}
    for cls_name, methods in knowledge.methods.items():
        for m in methods:
            index.setdefault(m, []).append(cls_name)
    for cls_name, props in knowledge.properties.items():
        for p in props:
            index.setdefault(p, []).append(cls_name)
    for cls_name, members in knowledge.enum_members.items():
        for em in members:
            index.setdefault(em, []).append(cls_name)
    return index


def _build_type_and_interface_names(knowledge: Knowledge) -> set[str]:
    """Build the set of bare identifiers that are genuine type or interface
    references elsewhere in the model, even though they have no class entry
    of their own -- implemented interfaces (only ever appear in another
    class's `bases`) and BCL/framework property or return types (e.g. a
    .NET `RectangleF`) are never themselves documented as a class, but are
    still real, verifiable references, not fabrications.

    Found 2026-07-23: `_is_method_like()`'s camelCase heuristic (needed to
    recognize genuine multi-word PascalCase .NET/Java/C++ method names as
    "method-like", since those platforms use PascalCase for members, not
    literal camelCase) cannot distinguish a member name from a type/interface
    name by casing alone -- both are indistinguishable multi-word PascalCase
    strings. `IFieldWithCalendar` (a real interface, confirmed present in
    four classes' own `bases` in api_surface.json) and `RectangleF` (a real
    .NET property type, confirmed on `GroupShape`/`Shape`/`ShapeBase`'s
    `Bounds` property) were both reported FABRICATED because they aren't
    method/property NAMES -- they're TYPE names -- so the reverse
    method/property index correctly never contained them.
    """
    names: set[str] = set()
    for bases in getattr(knowledge, "parents", {}).values():
        names.update(bases)
    names.update(getattr(knowledge, "property_types", {}).values())
    names.update(getattr(knowledge, "return_types", {}).values())
    return names


# Platforms where methods use camelCase convention
_CAMELCASE_PLATFORMS = frozenset({"java", "net", "cpp", "typescript", "javascript"})
_CAMELCASE_RE = re.compile(r"[a-z]+[A-Z]")


def _is_method_like(name: str, platform: str) -> bool:
    """Check if a bare name looks like a method/property for the given platform.

    - snake_case names (contain ``_``) are method-like on all platforms.
    - camelCase names are method-like on Java/C#/C++/TypeScript.
    - Unknown platforms default to conservative (underscore only).
    """
    if "_" in name:
        return True
    if platform in _CAMELCASE_PLATFORMS:
        return bool(_CAMELCASE_RE.search(name))
    return False


# Navigation / license / boilerplate patterns for unit classification
_NAV_LINK_RE = re.compile(r"^\s*-\s*\[.+\]\(.+\)")
_BOLD_DASH_RE = re.compile(r"^\s*-\s*\*\*[\w\s]+\*\*\s*[–—-]")
_CLAIM_VERB_RE = re.compile(
    r"\b(supports?|provides?|returns?|accepts?|converts?|enables?|allows?|"
    r"creates?|loads?|saves?|exports?|imports?|calls?)\b",
    re.IGNORECASE,
)

# Unit classification types
CLAIM_TYPE_CLAIM = "claim"
CLAIM_TYPE_STRUCTURAL = "structural"
CLAIM_TYPE_CODE = "code"
CLAIM_TYPE_REFERENCE = "reference"


def classify_unit(unit: dict, api_refs: list[str] | None = None) -> str:
    """Classify a unit as claim-bearing or non-claim content.

    Safety invariant: any unit with backtick API refs is always 'claim'.
    Returns one of: claim, structural, code, reference.

    Args:
        api_refs: Pre-computed _API_REF_RE.findall() result. If None, computed here.
    """
    text = unit["text"]
    unit_type = unit["type"]
    has_backtick_ref = bool(api_refs) if api_refs is not None else bool(_API_REF_RE.search(text))

    if unit_type == "heading":
        return CLAIM_TYPE_STRUCTURAL

    if unit_type == "code_block":
        return CLAIM_TYPE_CODE

    if unit_type == "table_row":
        cells = [c.strip() for c in text.split("|") if c.strip()]
        if has_backtick_ref or any(_CLAIM_VERB_RE.search(c) for c in cells):
            return CLAIM_TYPE_CLAIM
        if all(len(c.split()) <= 5 for c in cells):
            return CLAIM_TYPE_STRUCTURAL
        return CLAIM_TYPE_CLAIM

    if unit_type == "list_item":
        if has_backtick_ref:
            return CLAIM_TYPE_CLAIM
        if _NAV_LINK_RE.match(text) or _BOLD_DASH_RE.match(text):
            return CLAIM_TYPE_REFERENCE
        return CLAIM_TYPE_CLAIM

    # paragraph
    if has_backtick_ref:
        return CLAIM_TYPE_CLAIM
    words = text.split()
    if len(words) <= 6 and not _CLAIM_VERB_RE.search(text):
        return CLAIM_TYPE_STRUCTURAL
    if _STRUCTURAL_RE.match(text):
        return CLAIM_TYPE_STRUCTURAL
    return CLAIM_TYPE_CLAIM



# ============================================================================
# Unit decomposition
# ============================================================================

def _file_path_sha4(rel_path: str) -> str:
    """First 4 hex chars of SHA-256 of the relative file path."""
    return hashlib.sha256(rel_path.encode()).hexdigest()[:4]


def make_unit_id(family: str, platform: str, rel_path: str, line: int, unit_type: str) -> str:
    """Stable unit ID: U-{family}-{platform}-{path_sha4}-L{line}-{type}."""
    sha4 = _file_path_sha4(rel_path)
    return f"U-{family}-{platform}-{sha4}-L{line}-{unit_type}"


def make_finding_id(family: str, platform: str, finding_type: str,
                    file_path: str, line: int, old_value: str) -> str:
    """Stable finding ID compatible with S-43 gap-eval format."""
    type_codes = {
        "unsupported-claim": "uclm",
        "contradicted-claim": "cclm",
        "fabricated-api": "fapi",
        "fabricated-claim": "fclm",
        "wrong-format": "wfmt",
        "forbidden-claim": "forb",
    }
    code = type_codes.get(finding_type, finding_type[:4])
    raw = f"{file_path}:{line}:{old_value[:20]}"
    sha = hashlib.sha256(raw.encode()).hexdigest()[:8]
    return f"F-{family}-{platform}-{code}-{sha}"


def decompose_page(filepath: Path, family: str, platform: str,
                   unit_types: set[str] | None = None) -> list[dict]:
    """Parse a markdown file into reviewable units.

    Returns a list of unit dicts with keys:
        id, file, line_start, line_end, type, text
    """
    if unit_types is None:
        unit_types = ALL_UNIT_TYPES

    text = filepath.read_text(encoding="utf-8", errors="replace")
    lines = text.split("\n")
    rel_path = str(filepath.relative_to(_REPO_ROOT)).replace("\\", "/")

    units: list[dict] = []
    in_frontmatter = False
    in_code_block = False
    code_block_start = -1
    code_block_lines: list[str] = []
    paragraph_lines: list[str] = []
    paragraph_start = -1

    def _flush_paragraph():
        nonlocal paragraph_lines, paragraph_start
        if paragraph_lines and UNIT_PARAGRAPH in unit_types:
            text_block = " ".join(paragraph_lines).strip()
            if text_block and len(text_block) > 10:
                units.append({
                    "id": make_unit_id(family, platform, rel_path, paragraph_start, UNIT_PARAGRAPH),
                    "file": rel_path,
                    "line_start": paragraph_start,
                    "line_end": paragraph_start + len(paragraph_lines) - 1,
                    "type": "paragraph",
                    "text": text_block,
                })
        paragraph_lines = []
        paragraph_start = -1

    for i, line in enumerate(lines, start=1):
        stripped = line.strip()

        # --- Frontmatter detection ---
        if i <= 2 and stripped == "---":
            in_frontmatter = True
            continue
        if in_frontmatter:
            if stripped == "---":
                in_frontmatter = False
            continue

        # --- Code block detection ---
        if stripped.startswith("```"):
            if not in_code_block:
                _flush_paragraph()
                in_code_block = True
                code_block_start = i
                code_block_lines = []
            else:
                # End of code block
                if UNIT_CODEBLOCK in unit_types and code_block_lines:
                    code_text = "\n".join(code_block_lines)
                    if code_text.strip():
                        units.append({
                            "id": make_unit_id(family, platform, rel_path, code_block_start, UNIT_CODEBLOCK),
                            "file": rel_path,
                            "line_start": code_block_start,
                            "line_end": i,
                            "type": "code_block",
                            "text": code_text,
                        })
                in_code_block = False
                code_block_lines = []
            continue

        if in_code_block:
            code_block_lines.append(line)
            continue

        # --- Heading ---
        if stripped.startswith("#") and UNIT_HEADING in unit_types:
            _flush_paragraph()
            units.append({
                "id": make_unit_id(family, platform, rel_path, i, UNIT_HEADING),
                "file": rel_path,
                "line_start": i,
                "line_end": i,
                "type": "heading",
                "text": stripped.lstrip("#").strip(),
            })
            continue

        # --- Table row ---
        if stripped.startswith("|") and stripped.endswith("|"):
            _flush_paragraph()
            # Skip separator rows like |---|---|
            if re.match(r"^\|[\s\-:|]+\|$", stripped):
                continue
            # Skip header rows (first row of a table)
            if UNIT_TABLEROW in unit_types:
                units.append({
                    "id": make_unit_id(family, platform, rel_path, i, UNIT_TABLEROW),
                    "file": rel_path,
                    "line_start": i,
                    "line_end": i,
                    "type": "table_row",
                    "text": stripped,
                })
            continue

        # --- List item ---
        if re.match(r"^[-*+]\s|^\d+\.\s", stripped):
            _flush_paragraph()
            if UNIT_LISTITEM in unit_types:
                units.append({
                    "id": make_unit_id(family, platform, rel_path, i, UNIT_LISTITEM),
                    "file": rel_path,
                    "line_start": i,
                    "line_end": i,
                    "type": "list_item",
                    "text": stripped,
                })
            continue

        # --- Paragraph accumulation ---
        if stripped:
            if paragraph_start == -1:
                paragraph_start = i
            paragraph_lines.append(stripped)
        else:
            _flush_paragraph()

    _flush_paragraph()
    return units


# ============================================================================
# Clone cache grep
# ============================================================================

def _find_clone_cache(family: str, platform: str) -> Path | None:
    """Locate the clone cache directory for a family/platform."""
    cache_name = f"aspose_{family}_{platform}"
    # Canonical location: runs/.clone_cache/ inside the repo (never foss-launcher)
    for base in [_REPO_ROOT / "runs" / ".clone_cache"]:
        candidate = base / cache_name
        if candidate.exists():
            return candidate
    return None


def _grep_clone_cache(clone_path: Path, pattern: str, max_results: int = 5) -> list[dict]:
    """Search clone cache for a pattern, returning file:line matches."""
    if not clone_path or not clone_path.exists():
        return []
    try:
        result = subprocess.run(
            ["git", "-C", str(clone_path), "grep", "-n", "-i", "--max-count", str(max_results), pattern],
            capture_output=True, text=True, timeout=10,
        )
        if result is None or result.stdout is None:
            return []
        matches = []
        for line in result.stdout.strip().split("\n"):
            if not line or ":" not in line:
                continue
            parts = line.split(":", 2)
            if len(parts) >= 3:
                matches.append({
                    "file": parts[0],
                    "line": int(parts[1]) if parts[1].isdigit() else 0,
                    "excerpt": parts[2].strip()[:200],
                })
        return matches
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return []


# ============================================================================
# Knowledge helpers
# ============================================================================

def _load_claims(family: str, platform: str) -> list[dict]:
    path = KNOWLEDGE_ROOT / family / platform / "merged" / "claims.json"
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, KeyError):
        return []


def _load_forbidden_claims(family: str, platform: str) -> list[str]:
    path = KNOWLEDGE_ROOT / family / platform / "merged" / "index.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("forbidden_claims", [])
    except (json.JSONDecodeError, KeyError):
        return []


def _load_formats(family: str, platform: str) -> dict[str, str]:
    """Load format support as {ext: direction}.

    formats.json commonly has multiple raw entries for the same format key
    (e.g. separate LoadFormat/SaveFormat enum entries, or separate
    Reader/Writer class entries) with DIFFERENT directions -- a format that
    genuinely supports both import and export has one "import" entry and one
    "export" entry, not a single "both" entry. Naively overwriting `result[ext]`
    per entry means whichever entry happens to appear LAST in the array wins,
    silently discarding the other direction. Found 2026-07-23: Text/Txt has
    import entries (LoadFormat, TxtReader, TxtLoadOptions) and export entries
    (SaveFormat, TxtWriter, TxtSaveOptions) interleaved in formats.json; the
    last-write-wins bug resolved both to "export" and flagged a page
    correctly describing TxtLoadOptions' IMPORT behavior as CONTRADICTED.
    Mirrors format_truth.py's `_load_formats()`, which already merges
    correctly -- this was a second, independently-diverged copy of the same
    logic (duplicated knowledge lookups across evaluators/tools are a
    recurring source of exactly this kind of drift).
    """
    path = KNOWLEDGE_ROOT / family / platform / "merged" / "formats.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        result = {}
        for fmt in data:
            ext = (fmt.get("format") or fmt.get("ext") or "").lower()
            direction = (fmt.get("direction") or fmt.get("support") or "").lower()
            if not ext:
                continue
            existing = result.get(ext)
            if existing and existing != direction:
                if direction == "none":
                    pass  # keep existing
                elif existing == "none":
                    result[ext] = direction
                else:
                    result[ext] = "both"
            else:
                result[ext] = direction
        return result
    except (json.JSONDecodeError, KeyError):
        return {}


def _tokenize(text: str) -> set[str]:
    """Extract lowercase word tokens (3+ chars)."""
    return set(_WORD_RE.findall(text.lower()))


# ============================================================================
# Per-unit verification
# ============================================================================

def verify_unit(
    unit: dict,
    knowledge: Knowledge,
    claims: list[dict],
    forbidden_claims: list[str],
    format_support: dict[str, str],
    clone_path: Path | None,
    claim_token_index: list[tuple[str, str, set[str]]],
    method_index: dict[str, list[str]] | None = None,
    platform: str = "",
    type_names: set[str] | None = None,
) -> dict:
    """Verify a single unit against knowledge and clone cache.

    Returns the unit dict augmented with verdict, confidence, evidence_chain,
    tier_resolved_by, and defect_origin.
    """
    text = unit["text"]
    unit_type = unit["type"]
    tokens = _tokenize(text)

    # Default result
    verdict = VERDICT_UNVERIFIABLE
    confidence = 0.0
    evidence_chain: dict[str, Any] = {
        "knowledge_artifact": None,
        "api_surface_entry": None,
        "clone_cache_file": None,
        "clone_cache_line": None,
        "clone_cache_excerpt": None,
    }
    tier_resolved_by = 0
    defect_origin = None

    # Pre-compute API refs once (used by classify_unit and API ref checks)
    api_refs = _API_REF_RE.findall(text)

    # Classify unit — non-claim content skips verification
    claim_type = classify_unit(unit, api_refs=api_refs)
    unit["claim_type"] = claim_type

    if claim_type != CLAIM_TYPE_CLAIM:
        unit.update(verdict=VERDICT_UNVERIFIABLE, confidence=0.0,
                    evidence_chain=evidence_chain, tier_resolved_by=0,
                    defect_origin=None, review=None)
        return unit

    # Skip trivially short claim units
    if len(tokens) < 3:
        unit.update(verdict=VERDICT_UNVERIFIABLE, confidence=0.0,
                    evidence_chain=evidence_chain, tier_resolved_by=0,
                    defect_origin=None, review=None)
        return unit

    # === TIER 1: Deterministic checks ===

    # 1a. Check forbidden claims (token overlap >= 0.7)
    for fc_text in forbidden_claims:
        fc_toks = _tokenize(fc_text)
        if len(fc_toks) < 2:
            continue
        overlap = tokens & fc_toks
        if len(overlap) >= len(fc_toks) * 0.7 and len(overlap) >= 3:
            verdict = VERDICT_CONTRADICTED
            confidence = 0.9
            tier_resolved_by = 1
            defect_origin = ORIGIN_GENERATION_FABRICATION
            evidence_chain["knowledge_artifact"] = f"forbidden_claim: {fc_text[:80]}"
            unit.update(verdict=verdict, confidence=confidence,
                        evidence_chain=evidence_chain, tier_resolved_by=tier_resolved_by,
                        defect_origin=defect_origin, review=None)
            return unit

    # 1b. Check API references in backtick identifiers (api_refs already computed above)
    api_verified_count = 0
    api_failed_count = 0
    api_checked = False
    best_api_entry = None

    if api_refs and knowledge.available:
        for ref in api_refs:
            parts = ref.split(".")
            cls_name = parts[0]
            if cls_name not in knowledge.classes:
                # Bare name, no class entry of its own -- could be (a) a real
                # interface/type reference (never separately documented as a
                # class, e.g. an implemented interface or a BCL property
                # type), or (b) a real member name needing the reverse
                # method/property index. Check (a) first: _is_method_like()'s
                # casing heuristic cannot tell "RectangleF" (a type) from
                # "GetBounds" (a method) apart -- both are multi-word
                # PascalCase -- so a genuine type/interface name must be
                # checked here or it falls through to the member-name index,
                # where it will correctly never be found, and gets reported
                # FABRICATED despite being completely accurate.
                if type_names and len(parts) == 1 and cls_name in type_names:
                    api_checked = True
                    api_verified_count += 1
                    best_api_entry = cls_name
                    continue
                # Bare name — try reverse method index as fallback
                # Only consider names that look like methods for this platform
                # to avoid false positives on parameter names, package names, etc.
                if method_index and len(parts) == 1 and _is_method_like(cls_name, platform):
                    if cls_name in method_index:
                        api_checked = True
                        api_verified_count += 1
                        best_api_entry = f"{method_index[cls_name][0]}.{cls_name}"
                    else:
                        # Snake_case name not found in any class — potential fabrication
                        api_checked = True
                        api_failed_count += 1
                continue
            api_checked = True
            if len(parts) >= 2:
                member = parts[1]
                if knowledge.has_method(cls_name, member) or \
                   knowledge.has_property(cls_name, member):
                    api_verified_count += 1
                    best_api_entry = ref
                elif (cls_name in knowledge.enum_members and
                      member in knowledge.enum_members[cls_name]):
                    api_verified_count += 1
                    best_api_entry = ref
                else:
                    api_failed_count += 1
            else:
                # Class-level reference
                api_verified_count += 1
                best_api_entry = ref

    # 1c. Check format claims
    format_contradicted = False
    _FORMAT_CLAIM_RE = re.compile(
        r"(?:supports?|import|export|convert|load|save|read|write)\w*\s+"
        r"(?:the\s+)?(?:to\s+|from\s+)?(\w{2,6})\s+(?:format|file|document)",
        re.IGNORECASE,
    )
    for m in _FORMAT_CLAIM_RE.finditer(text):
        claimed = m.group(1).lower()
        if claimed in format_support:
            direction = format_support[claimed]
            text_lower = text.lower()
            if "export" in text_lower and direction == "import":
                format_contradicted = True
                evidence_chain["knowledge_artifact"] = f"formats.json: {claimed}={direction}"
            elif "import" in text_lower and direction == "export":
                format_contradicted = True
                evidence_chain["knowledge_artifact"] = f"formats.json: {claimed}={direction}"

    if format_contradicted:
        verdict = VERDICT_CONTRADICTED
        confidence = 0.85
        tier_resolved_by = 1
        defect_origin = ORIGIN_GENERATION_FABRICATION
        unit.update(verdict=verdict, confidence=confidence,
                    evidence_chain=evidence_chain, tier_resolved_by=tier_resolved_by,
                    defect_origin=defect_origin, review=None)
        return unit

    # 1d. If API references were checked and all failed — FABRICATED
    if api_checked and api_failed_count > 0 and api_verified_count == 0:
        verdict = VERDICT_FABRICATED
        confidence = 0.85
        tier_resolved_by = 1
        defect_origin = ORIGIN_GENERATION_FABRICATION
        unit.update(verdict=verdict, confidence=confidence,
                    evidence_chain=evidence_chain, tier_resolved_by=tier_resolved_by,
                    defect_origin=defect_origin, review=None)
        return unit

    # 1e. Claim overlap check
    best_overlap = 0.0
    best_claim_id = None
    best_claim_text = ""
    for claim_id, claim_text, ct in claim_token_index:
        if not ct:
            continue
        overlap = len(tokens & ct) / max(len(ct), 1)
        if overlap > best_overlap:
            best_overlap = overlap
            best_claim_id = claim_id
            best_claim_text = claim_text

    if api_checked and api_verified_count > 0 and best_overlap >= 0.5:
        verdict = VERDICT_VERIFIED
        confidence = min(0.6 + best_overlap * 0.3, 0.95)
        tier_resolved_by = 1
        evidence_chain["knowledge_artifact"] = best_claim_id
        evidence_chain["api_surface_entry"] = best_api_entry
        unit.update(verdict=verdict, confidence=confidence,
                    evidence_chain=evidence_chain, tier_resolved_by=tier_resolved_by,
                    defect_origin=None, review=None)
        return unit

    if api_checked and api_verified_count > 0:
        # API verified but no strong claim overlap — still VERIFIED at lower confidence
        verdict = VERDICT_VERIFIED
        confidence = 0.6
        tier_resolved_by = 1
        evidence_chain["api_surface_entry"] = best_api_entry
        if best_claim_id:
            evidence_chain["knowledge_artifact"] = best_claim_id
        unit.update(verdict=verdict, confidence=confidence,
                    evidence_chain=evidence_chain, tier_resolved_by=tier_resolved_by,
                    defect_origin=None, review=None)
        return unit

    if best_overlap >= 0.5:
        verdict = VERDICT_VERIFIED
        confidence = 0.5 + best_overlap * 0.2
        tier_resolved_by = 1
        evidence_chain["knowledge_artifact"] = best_claim_id
        unit.update(verdict=verdict, confidence=confidence,
                    evidence_chain=evidence_chain, tier_resolved_by=tier_resolved_by,
                    defect_origin=None, review=None)
        return unit

    # === TIER 2: Clone cache grep ===
    if clone_path:
        # Extract key identifiers to search for
        search_terms = []
        for ref in api_refs:
            search_terms.append(ref.split(".")[-1])  # method/class name
        # Also try significant content words (capitalized, 5+ chars)
        for word in re.findall(r"\b[A-Z][a-zA-Z]{4,}\b", text):
            if word not in {"These", "There", "Their", "Where", "Which", "About",
                            "After", "Before", "While", "Using", "Class", "Method",
                            "Property", "Object", "Format", "Document"}:
                search_terms.append(word)

        # Deduplicate and limit
        seen: set[str] = set()
        unique_terms: list[str] = []
        for t in search_terms:
            if t.lower() not in seen:
                seen.add(t.lower())
                unique_terms.append(t)
        search_terms = unique_terms[:5]

        clone_matches: list[dict] = []
        for term in search_terms:
            matches = _grep_clone_cache(clone_path, term, max_results=3)
            clone_matches.extend(matches)

        if clone_matches:
            best_match = clone_matches[0]
            evidence_chain["clone_cache_file"] = best_match["file"]
            evidence_chain["clone_cache_line"] = best_match["line"]
            evidence_chain["clone_cache_excerpt"] = best_match["excerpt"]

            if best_overlap >= 0.3:
                verdict = VERDICT_VERIFIED
                confidence = 0.5
                tier_resolved_by = 2
                evidence_chain["knowledge_artifact"] = best_claim_id
                unit.update(verdict=verdict, confidence=confidence,
                            evidence_chain=evidence_chain, tier_resolved_by=tier_resolved_by,
                            defect_origin=None, review=None)
                return unit

            # Clone cache has something, knowledge doesn't — possible SCOUT_MISS
            if best_overlap < 0.3 and not api_checked:
                verdict = VERDICT_UNVERIFIABLE
                confidence = 0.3
                tier_resolved_by = 2
                defect_origin = ORIGIN_SCOUT_MISS if not best_claim_id else None
                unit.update(verdict=verdict, confidence=confidence,
                            evidence_chain=evidence_chain, tier_resolved_by=tier_resolved_by,
                            defect_origin=defect_origin, review=None)
                return unit

    # === Tier 3 (LLM semantic verification) — not yet implemented ===
    # When implemented, Tier 3 would use LLM to semantically verify claims
    # against source code. Currently all units reaching this point fall through
    # to the heuristic classification below.

    # === Tier 1+2 exhausted ===

    # For paragraphs/list items with very low overlap — classify based on specificity
    if best_overlap >= 0.3:
        # Some overlap — probably true but can't fully confirm
        verdict = VERDICT_UNVERIFIABLE
        confidence = 0.3
    elif best_overlap > 0:
        # Weak overlap
        verdict = VERDICT_UNSUPPORTED
        confidence = 0.1
        defect_origin = ORIGIN_GENERATION_FABRICATION
    else:
        # No overlap at all
        # Check if it's making a specific testable claim vs generic prose
        has_specific_claim = bool(api_refs) or bool(_FORMAT_CLAIM_RE.search(text))
        if has_specific_claim:
            verdict = VERDICT_UNSUPPORTED
            confidence = 0.0
            defect_origin = ORIGIN_GENERATION_FABRICATION
        else:
            verdict = VERDICT_UNVERIFIABLE
            confidence = 0.1

    unit.update(verdict=verdict, confidence=confidence,
                evidence_chain=evidence_chain, tier_resolved_by=2,
                defect_origin=defect_origin, review=None)
    return unit


# ============================================================================
# State management (adapted from scripts/gap-eval/src/state.py)
# ============================================================================

def _state_path(family: str, platform: str) -> Path:
    return STATE_DIR / f"{family}-{platform}.json"


def load_state(family: str, platform: str) -> dict:
    path = _state_path(family, platform)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "family": family,
        "platform": platform,
        "last_run_sha": None,
        "last_run_date": None,
        "last_verdict_counts": {},
        "findings": [],
    }


def save_state(state: dict, family: str, platform: str) -> Path:
    path = _state_path(family, platform)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
    return path


def merge_findings(prior: list[dict], new: list[dict]) -> tuple[list[dict], dict]:
    """Merge findings for delta tracking."""
    prior_by_id = {f["id"]: f for f in prior}
    new_by_id = {f["id"]: f for f in new}
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    merged: list[dict] = []
    delta = {"fixed": 0, "regressions": 0, "new": 0, "unchanged": 0}

    for fid, nf in new_by_id.items():
        if fid in prior_by_id:
            pf = prior_by_id[fid]
            if pf.get("status") == "fixed":
                nf["status"] = "regression"
                nf["regression_date"] = today
                delta["regressions"] += 1
            else:
                nf["status"] = pf.get("status", "open")
                delta["unchanged"] += 1
        else:
            nf["status"] = "open"
            delta["new"] += 1
        merged.append(nf)

    for fid, pf in prior_by_id.items():
        if fid not in new_by_id:
            if pf.get("status") not in ("fixed", "wontfix"):
                pf = dict(pf)
                pf["status"] = "fixed"
                pf["fixed_date"] = today
                delta["fixed"] += 1
            merged.append(pf)

    return merged, delta


# ============================================================================
# Report generation
# ============================================================================

def _generate_markdown_report(
    family: str, platform: str, knowledge: Knowledge,
    file_summaries: list[dict], all_units: list[dict],
    findings: list[dict], defect_summary: dict, summary: dict,
    delta: dict | None,
) -> str:
    """Generate human-readable markdown report."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines = [
        f"# Truth Audit Content: {family}/{platform}",
        f"Date: {now}",
        f"Knowledge SHA: {knowledge.repo_sha}",
        f"Knowledge version: {knowledge.version}",
        f"Schema version: {SCHEMA_VERSION}",
        "",
        "## Summary",
        "",
        f"| Metric | Count | % |",
        f"|--------|-------|---|",
        f"| Total units | {summary['total_units']} | 100% |",
        f"| Claim units | {summary.get('claim_units', '—')} | {_pct(summary.get('claim_units', 0), summary['total_units'])} |",
        f"| VERIFIED | {summary['verified']} | {summary['verification_rate']*100:.1f}% |",
        f"| UNVERIFIABLE | {summary['unverifiable']} | {_pct(summary['unverifiable'], summary['total_units'])} |",
        f"| UNSUPPORTED | {summary['unsupported']} | {_pct(summary['unsupported'], summary['total_units'])} |",
        f"| CONTRADICTED | {summary['contradicted']} | {_pct(summary['contradicted'], summary['total_units'])} |",
        f"| FABRICATED | {summary['fabricated']} | {_pct(summary['fabricated'], summary['total_units'])} |",
        f"| **Claim verification rate** | — | **{summary.get('claim_verification_rate', 0)*100:.1f}%** |",
        "",
    ]

    # Confidence bands
    bands = summary.get("confidence_bands", {})
    if bands:
        lines.extend([
            "### Confidence Bands (VERIFIED units)",
            "",
            "| Band | Count |",
            "|------|-------|",
            f"| High (≥0.7) | {bands.get('high', 0)} |",
            f"| Medium (0.5–0.7) | {bands.get('medium', 0)} |",
            f"| Low (<0.5) | {bands.get('low', 0)} |",
            "",
        ])

    # Classification breakdown
    dist = summary.get("claim_type_distribution", {})
    if dist:
        lines.extend([
            "### Unit Classification",
            "",
            "| Type | Count |",
            "|------|-------|",
        ])
        for ct in ["claim", "structural", "code", "reference"]:
            lines.append(f"| {ct} | {dist.get(ct, 0)} |")
        lines.append("")

    if delta:
        lines.extend([
            "## Delta (vs prior run)",
            "",
            f"- Fixed: {delta['fixed']}",
            f"- Regressions: {delta['regressions']}",
            f"- New: {delta['new']}",
            f"- Unchanged: {delta['unchanged']}",
            "",
        ])

    # Defect origins
    lines.extend([
        "## Defect Origins",
        "",
        "| Origin | Count |",
        "|--------|-------|",
    ])
    for origin, count in sorted(defect_summary.items()):
        if count > 0:
            lines.append(f"| {origin} | {count} |")
    lines.append("")

    # Per-file summary
    lines.extend([
        "## Files",
        "",
        "| File | Units | Verified | Unsupported | Contradicted | Fabricated |",
        "|------|-------|----------|-------------|--------------|------------|",
    ])
    for fs in sorted(file_summaries, key=lambda x: -(x.get("contradicted", 0) + x.get("fabricated", 0))):
        lines.append(
            f"| {fs['path']} | {fs['unit_count']} | {fs.get('verified', 0)} | "
            f"{fs.get('unsupported', 0)} | {fs.get('contradicted', 0)} | {fs.get('fabricated', 0)} |"
        )
    lines.append("")

    # Findings detail
    if findings:
        lines.extend(["## Findings (CONTRADICTED / FABRICATED / UNSUPPORTED)", ""])
        for f in findings:
            severity = f.get("severity", "?")
            lines.append(f"### [{severity}] {f['type']} — {f['file']}:L{f['line']}")
            lines.append(f"- **Unit**: {f['unit_id']}")
            lines.append(f"- **Verdict**: {f['verdict']}")
            lines.append(f"- **Origin**: {f.get('defect_origin', 'unknown')}")
            lines.append(f"- **Text**: {f.get('description', '')[:200]}")
            lines.append("")

    return "\n".join(lines)


def _pct(part: int, total: int) -> str:
    if total == 0:
        return "0.0%"
    return f"{part / total * 100:.1f}%"


# ============================================================================
# Main orchestration
# ============================================================================

def run_audit(
    family: str,
    platform: str,
    scope: str = "all",
    no_llm: bool = True,  # Tier 3 not implemented; parameter reserved
    max_units: int = 0,
    unit_type_filter: set[str] | None = None,
) -> dict:
    """Run the full truth audit and return the gap ledger dict."""

    # --- Step 0: Validate pre-conditions ---
    knowledge = Knowledge(family, platform)
    if not knowledge.available:
        log.error("Knowledge not available for %s/%s", family, platform)
        return {"error": f"Knowledge not available for {family}/{platform}"}

    model_path = KNOWLEDGE_ROOT / family / platform / "merged" / "model.yaml"
    import yaml
    model = yaml.safe_load(model_path.read_text(encoding="utf-8"))
    if model.get("stale_since"):
        log.error("Knowledge is stale (stale_since=%s)", model["stale_since"])
        return {"error": f"Knowledge is stale since {model['stale_since']}"}

    clone_path = _find_clone_cache(family, platform)
    if not clone_path:
        log.warning("Clone cache not found for %s/%s — Tier 2 disabled", family, platform)

    # --- Step 1: Discover content files ---
    all_files = discover_content(family, platform)
    scope_sites = SCOPE_MAP.get(scope, SCOPE_MAP["all"])
    files = [f for f in all_files if any(site in str(f) for site in scope_sites)]

    if not files:
        log.warning("No content files found for %s/%s scope=%s", family, platform, scope)
        return {"error": f"No content files for {family}/{platform} scope={scope}"}

    log.info("Found %d content files for %s/%s (scope=%s)", len(files), family, platform, scope)

    # --- Step 2: Load knowledge artifacts ---
    claims = _load_claims(family, platform)
    forbidden = _load_forbidden_claims(family, platform)
    formats = _load_formats(family, platform)

    # Build reverse method index for bare name resolution
    method_index = _build_method_index(knowledge)
    type_names = _build_type_and_interface_names(knowledge)

    # Pre-compute claim token index: (claim_id, claim_text, token_set)
    claim_token_index = []
    for c in claims:
        cid = c.get("id", c.get("claim_id", ""))
        ctext = c.get("text", c.get("claim", ""))
        if ctext:
            claim_token_index.append((cid, ctext, _tokenize(ctext)))

    # --- Step 3: Decompose and verify all pages ---
    all_units: list[dict] = []
    file_summaries: list[dict] = []
    total_processed = 0

    for filepath in files:
        units = decompose_page(filepath, family, platform, unit_type_filter)
        file_verdict_counts: dict[str, int] = defaultdict(int)

        for unit in units:
            if max_units > 0 and total_processed >= max_units:
                break

            verify_unit(
                unit, knowledge, claims, forbidden, formats,
                clone_path, claim_token_index, method_index,
                platform=platform, type_names=type_names,
            )
            file_verdict_counts[unit["verdict"]] += 1
            all_units.append(unit)
            total_processed += 1

        if units:
            rel = str(filepath.relative_to(_REPO_ROOT)).replace("\\", "/")
            file_summaries.append({
                "path": rel,
                "unit_count": len(units),
                "verified": file_verdict_counts.get(VERDICT_VERIFIED, 0),
                "unverifiable": file_verdict_counts.get(VERDICT_UNVERIFIABLE, 0),
                "unsupported": file_verdict_counts.get(VERDICT_UNSUPPORTED, 0),
                "contradicted": file_verdict_counts.get(VERDICT_CONTRADICTED, 0),
                "fabricated": file_verdict_counts.get(VERDICT_FABRICATED, 0),
            })

        if max_units > 0 and total_processed >= max_units:
            log.info("Reached max_units limit (%d)", max_units)
            break

    # Classification distribution
    claim_type_dist = Counter(u.get("claim_type", "unknown") for u in all_units)
    log.info("Classification: %s", ", ".join(f"{k}={v}" for k, v in sorted(claim_type_dist.items())))

    # --- Step 4: Generate findings from non-verified units ---
    findings: list[dict] = []
    defect_summary: dict[str, int] = defaultdict(int)

    for unit in all_units:
        v = unit.get("verdict")
        origin = unit.get("defect_origin")
        if origin:
            defect_summary[origin] += 1

        if v in (VERDICT_UNSUPPORTED, VERDICT_CONTRADICTED, VERDICT_FABRICATED):
            finding_type_map = {
                VERDICT_UNSUPPORTED: "unsupported-claim",
                VERDICT_CONTRADICTED: "contradicted-claim",
                VERDICT_FABRICATED: "fabricated-claim",
            }
            ftype = finding_type_map[v]
            severity = "M" if v in (VERDICT_CONTRADICTED, VERDICT_FABRICATED) else "S"

            fid = make_finding_id(
                family, platform, ftype,
                unit["file"], unit["line_start"], unit["text"],
            )
            findings.append({
                "id": fid,
                "unit_id": unit["id"],
                "type": ftype,
                "severity": severity,
                "verdict": v,
                "defect_origin": origin,
                "file": unit["file"],
                "line": unit["line_start"],
                "description": unit["text"][:300],
                "review": {
                    "reviewed_by": None,
                    "reviewed_at": None,
                    "disposition": None,
                    "comment": None,
                },
            })

    # --- Step 5: Build summary ---
    claim_units = sum(1 for u in all_units if u.get("claim_type") == CLAIM_TYPE_CLAIM)
    verified_count = sum(1 for u in all_units if u.get("verdict") == VERDICT_VERIFIED)

    # Confidence bands for VERIFIED units
    conf_high = sum(1 for u in all_units
                    if u.get("verdict") == VERDICT_VERIFIED and u.get("confidence", 0) >= 0.7)
    conf_medium = sum(1 for u in all_units
                      if u.get("verdict") == VERDICT_VERIFIED and 0.5 <= u.get("confidence", 0) < 0.7)
    conf_low = sum(1 for u in all_units
                   if u.get("verdict") == VERDICT_VERIFIED and u.get("confidence", 0) < 0.5)

    summary = {
        "total_units": len(all_units),
        "claim_units": claim_units,
        "verified": verified_count,
        "unverifiable": sum(1 for u in all_units if u.get("verdict") == VERDICT_UNVERIFIABLE),
        "unsupported": sum(1 for u in all_units if u.get("verdict") == VERDICT_UNSUPPORTED),
        "contradicted": sum(1 for u in all_units if u.get("verdict") == VERDICT_CONTRADICTED),
        "fabricated": sum(1 for u in all_units if u.get("verdict") == VERDICT_FABRICATED),
        "verification_rate": 0.0,
        "claim_verification_rate": 0.0,
        "defect_rate": 0.0,
        "confidence_bands": {
            "high": conf_high,
            "medium": conf_medium,
            "low": conf_low,
        },
    }
    total = summary["total_units"]
    if total > 0:
        summary["verification_rate"] = round(verified_count / total, 3)
        summary["defect_rate"] = round(
            (summary["contradicted"] + summary["fabricated"]) / total, 3
        )
    if claim_units > 0:
        summary["claim_verification_rate"] = round(verified_count / claim_units, 3)
    summary["claim_type_distribution"] = dict(claim_type_dist)

    # --- Step 6: Delta tracking ---
    prior_state = load_state(family, platform)
    merged_findings, delta = merge_findings(prior_state.get("findings", []), findings)

    # Update state
    new_state = {
        "family": family,
        "platform": platform,
        "last_run_sha": knowledge.repo_sha,
        "last_run_date": datetime.now(timezone.utc).isoformat(),
        "last_verdict_counts": {
            VERDICT_VERIFIED: summary["verified"],
            VERDICT_UNVERIFIABLE: summary["unverifiable"],
            VERDICT_UNSUPPORTED: summary["unsupported"],
            VERDICT_CONTRADICTED: summary["contradicted"],
            VERDICT_FABRICATED: summary["fabricated"],
        },
        "findings": merged_findings,
    }
    save_state(new_state, family, platform)

    # --- Step 7: Build output ledger ---
    ledger = {
        "schema_version": SCHEMA_VERSION,
        "family": family,
        "platform": platform,
        "run_date": datetime.now(timezone.utc).isoformat(),
        "clone_cache_sha": knowledge.repo_sha,
        "knowledge_version": knowledge.version,
        "summary": summary,
        "files": file_summaries,
        "units": all_units,
        "findings": findings,
        "defect_summary": dict(defect_summary),
        "delta": delta,
    }

    # Write JSON report
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    json_path = REPORTS_DIR / f"{family}-{platform}-{date_str}.json"
    json_path.write_text(
        json.dumps(ledger, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # Write markdown report
    md = _generate_markdown_report(
        family, platform, knowledge,
        file_summaries, all_units, findings,
        dict(defect_summary), summary, delta,
    )
    md_path = REPORTS_DIR / f"{family}-{platform}-{date_str}.md"
    md_path.write_text(md, encoding="utf-8")

    log.info("Reports written: %s, %s", json_path, md_path)
    log.info("State updated: %s", _state_path(family, platform))

    return ledger


# ============================================================================
# CLI
# ============================================================================

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="truth_audit_content",
        description="S-85: Line-level content truth audit against clone cache and knowledge model",
    )
    parser.add_argument("family", help="Product family (e.g. words)")
    parser.add_argument("platform", help="Platform (e.g. python)")
    parser.add_argument("--scope", default="all",
                        choices=["all", "products", "docs", "blog", "kb", "reference"],
                        help="Subdomain scope (default: all)")
    parser.add_argument("--no-llm", action="store_true",
                        help="Reserved for future Tier 3 (not yet implemented)")
    parser.add_argument("--max-units", type=int, default=0,
                        help="Maximum units to verify (0 = unlimited)")
    parser.add_argument("--unit-types", default="",
                        help="Comma-separated unit types to include (H,P,C,T,L; default: all)")
    parser.add_argument("--json", action="store_true",
                        help="Print JSON ledger to stdout")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Verbose logging")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
        stream=sys.stderr,
    )

    unit_type_filter: set[str] | None = None
    if args.unit_types:
        unit_type_filter = set(args.unit_types.upper().split(","))

    ledger = run_audit(
        family=args.family,
        platform=args.platform,
        scope=args.scope,
        no_llm=args.no_llm,
        max_units=args.max_units,
        unit_type_filter=unit_type_filter,
    )

    if "error" in ledger:
        print(f"ERROR: {ledger['error']}", file=sys.stderr)
        return 1

    if args.json:
        sys.stdout.buffer.write(json.dumps(ledger, indent=2, ensure_ascii=False).encode("utf-8"))
        sys.stdout.buffer.write(b"\n")

    # Print summary to stderr
    s = ledger["summary"]
    bands = s.get("confidence_bands", {})
    print(
        f"\nTruth Audit Content: {args.family}/{args.platform}\n"
        f"  Units: {s['total_units']} (claims: {s.get('claim_units', '—')})  |  "
        f"Verified: {s['verified']}  |  "
        f"Unverifiable: {s['unverifiable']}  |  Unsupported: {s['unsupported']}  |  "
        f"Contradicted: {s['contradicted']}  |  Fabricated: {s['fabricated']}\n"
        f"  Claim verification rate: {s.get('claim_verification_rate', 0)*100:.1f}%  |  "
        f"Overall rate: {s['verification_rate']*100:.1f}%  |  "
        f"Defect rate: {s['defect_rate']*100:.1f}%\n"
        f"  Confidence: high={bands.get('high', 0)} medium={bands.get('medium', 0)} "
        f"low={bands.get('low', 0)}",
        file=sys.stderr,
    )

    if s["contradicted"] + s["fabricated"] > 0:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())