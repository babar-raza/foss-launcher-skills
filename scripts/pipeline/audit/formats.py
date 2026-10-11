"""audit/formats.py — enum_only SaveFormat warning check.

Verifies that SaveFormat constants with ``direction: enum_only`` in
``knowledge/{family}/{platform}/merged/formats.json`` are not presented as
functional export options without an explicit ValueError or
not-implemented warning in their Markdown table row.

Why this check exists
---------------------
FOSS libraries sometimes define SaveFormat enum members for API symmetry
with the commercial library without implementing the corresponding save
path.  ``formats.json`` records these as ``direction: enum_only``.  If a
reference or docs page lists such a constant in an Output Formats table
without a warning, developers will attempt to call
``Document.save(..., SaveFormat.DOCX)`` and receive an unexpected
``ValueError`` at runtime.

Root cause this prevents
------------------------
GAP-01 words/python session 2026-04-10: ``Document.md`` Output Formats
table listed ``SaveFormat.DOCX`` and ``SaveFormat.DOC`` without a
ValueError note, contradicting ``limitations.md`` and ``formats.json``
``enum_only`` markers.  Fixed via S-73; this check prevents recurrence.

Category code
-------------
FD — Format Direction (distinct from FM used by format_completeness.py
and FT used by format_truth.py).

Severity: FAIL — omitting the warning is a factual accuracy error.
"""
from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import List

import sys  # noqa: E402
_LIB_DIR = str(Path(__file__).resolve().parents[1] / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from token_ops import Finding

_log = logging.getLogger(__name__)

_DEFAULT_KNOWLEDGE_ROOT = Path("knowledge")
KNOWLEDGE_ROOT = _DEFAULT_KNOWLEDGE_ROOT


def configure(*, knowledge_root: "Path | str | None" = None) -> None:
    """Override module-level path constants for testing."""
    global KNOWLEDGE_ROOT
    KNOWLEDGE_ROOT = Path(knowledge_root) if knowledge_root is not None else _DEFAULT_KNOWLEDGE_ROOT


# ---------------------------------------------------------------------------
# Compiled patterns
# ---------------------------------------------------------------------------

# Match any Markdown table row (starts with |, has ≥1 | after the match)
# containing `SaveFormat.NAME` in any column position.
# Group 1 captures the format constant name (e.g. "DOCX").
# The full match (group 0) is used for _has_warning().
#
# Example rows matched:
#   | DOCX | `SaveFormat.DOCX` | — |          (SaveFormat in col 2)
#   | `SaveFormat.DOCX` | DOCX format | — |   (SaveFormat in col 1)
#   | DOCX | Legacy | `SaveFormat.DOCX` |     (SaveFormat in col 3)
_SAVEFORMAT_ROW_RE = re.compile(
    r"^\|[^\n]*`SaveFormat\.(\w+)`[^\n]*\|[^\n]*$",
    re.MULTILINE,
)

# Keywords indicating a table row already carries a sufficient warning.
# Lower-cased at match time.
_WARNING_KEYWORDS: tuple[str, ...] = (
    "valueerror",
    "not implemented",
    "raises",
    "not supported",
    "read-only constant",
    "enum_only",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@lru_cache(maxsize=None)
def _load_enum_only_formats(family: str, platform: str) -> set[str]:
    """Return the set of uppercase format names marked ``direction: enum_only``.

    Results are cached per ``(family, platform)`` pair for the lifetime of
    the process — ``formats.json`` does not change during a single audit run.
    Call ``_load_enum_only_formats.cache_clear()`` in tests to prevent state
    bleed between test cases that write different ``formats.json`` fixtures.

    Logging behaviour:
    - ``DEBUG``: ``formats.json`` not found (expected for products with no
      enum-only formats; not an error).
    - ``WARNING``: ``formats.json`` exists but cannot be parsed or is not a
      JSON list (unexpected misconfiguration; operator attention needed).

    Returns an empty set on any error so callers always get a safe result.
    """
    path = KNOWLEDGE_ROOT / family / platform / "merged" / "formats.json"
    if not path.exists():
        _log.debug(
            "audit/formats: no formats.json at %s — FD check skipped", path
        )
        return set()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, TypeError, OSError) as exc:
        _log.warning(
            "audit/formats: could not load %s (%s) — FD check skipped", path, exc
        )
        return set()
    if not isinstance(raw, list):
        _log.warning(
            "audit/formats: %s is not a JSON list — FD check skipped", path
        )
        return set()
    result: set[str] = set()
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        if entry.get("direction") != "enum_only":
            continue
        # Accept both "name" (legacy hand-edited) and "format" (extraction output)
        fname = entry.get("name") or entry.get("format") or ""
        if isinstance(fname, str) and fname:
            result.add(fname.upper())
    return result


def _has_warning(row_text: str) -> bool:
    """Return True if *row_text* already contains a ValueError/not-implemented note."""
    low = row_text.lower()
    return any(kw in low for kw in _WARNING_KEYWORDS)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_CAPABILITY_CLAIM_ROW_LABEL_RE = re.compile(r"^For\s+(.+?),\s+.+\s+is\s+.+\.$")
_TRAILING_PAREN_RE = re.compile(r"\s*\([^()]*\)\s*$")


@lru_cache(maxsize=None)
def _load_known_format_names(family: str, platform: str) -> frozenset[str]:
    """Return the lowercased set of format names currently in formats.json.

    Same cache-per-process, empty-set-on-any-error contract as
    ``_load_enum_only_formats`` — this check must never crash an audit run
    over a missing or malformed formats.json, only report FEWER findings.
    """
    path = KNOWLEDGE_ROOT / family / platform / "merged" / "formats.json"
    if not path.exists():
        return frozenset()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, TypeError, OSError):
        return frozenset()
    if not isinstance(raw, list):
        return frozenset()
    return frozenset(
        e["format"].lower() for e in raw
        if isinstance(e, dict) and e.get("format")
    )


def verify_capability_matrix_claims_current(
    family: str, platform: str
) -> List[Finding]:
    """H7 durable correctness guard (MT068-2026-09-11-IMAGING-NET-LAUNCH).

    ``extraction.capability_tables`` emits a ``capability_matrix_cell`` claim
    at full (1.0) confidence when its row label matches a format name that
    was verified against source at EXTRACTION time. Unlike ``format_support``
    claims, nothing previously re-verified that match on every subsequent
    run — a claim recorded as full-confidence would sit there looking
    authoritative even after the upstream repo's real format list changed
    (a format renamed or removed), which is *more* dangerous than the
    original compression defect this whole fix replaces: a wrong claim that
    LOOKS verified is worse than one that's visibly missing.

    Re-derives each claim's row label from its own mechanically-generated
    text (see ``capability_tables.py``'s exact template) and re-checks it
    against the CURRENT ``formats.json`` on every audit run — the same
    "re-verify every time, don't trust extraction-time state forever"
    guarantee ``format_support`` claims already get for free via
    ``verify_format_direction`` above.

    Returns a WARN (not FAIL) per drifted claim — this is knowledge-model
    staleness, not a content defect on any specific page, so it does not
    block a commit the way ``verify_format_direction``'s FAIL does; it
    signals "re-run knowledge-bootstrap", not "fix this page's prose".
    """
    claims_path = KNOWLEDGE_ROOT / family / platform / "merged" / "claims.json"
    if not claims_path.exists():
        return []
    try:
        claims = json.loads(claims_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, TypeError, OSError):
        return []
    if not isinstance(claims, list):
        return []

    known_names = _load_known_format_names(family, platform)
    findings: List[Finding] = []
    for claim in claims:
        if not isinstance(claim, dict) or claim.get("kind") != "capability_matrix_cell":
            continue
        if claim.get("confidence") != 1.0:
            continue  # already-unverified-tier claims have nothing to drift from
        text = claim.get("text", "")
        m = _CAPABILITY_CLAIM_ROW_LABEL_RE.match(text)
        if not m:
            continue  # not this pass's own claim shape — don't guess
        row_label = _TRAILING_PAREN_RE.sub("", m.group(1)).strip()
        if row_label.lower() not in known_names:
            findings.append(
                Finding(
                    level="WARN",
                    filepath=str(claims_path),
                    line_no=0,
                    message=(
                        f"capability_matrix_cell claim {claim.get('claim_id', '?')} "
                        f"row label '{row_label}' no longer matches any format name "
                        f"in current formats.json (was full-confidence at extraction "
                        f"time — the upstream format list has likely changed)."
                    ),
                    suggestion=(
                        f"Re-run /knowledge-bootstrap {family} {platform} to "
                        f"regenerate claims.json against the current source."
                    ),
                )
            )
    return findings


def verify_format_direction(
    file_path: str, family: str, platform: str
) -> List[Finding]:
    """Return FAIL findings for enum_only SaveFormat rows missing a warning note.

    Scans *file_path* for Markdown table rows that reference a
    ``SaveFormat.NAME`` constant where ``NAME`` is listed as
    ``direction: enum_only`` in ``formats.json``.  Rows that already
    contain a ValueError / not-implemented note pass silently.

    Returns an empty list if ``formats.json`` has no ``enum_only``
    entries, the file cannot be read, or no problematic rows are found.
    """
    enum_only = _load_enum_only_formats(family, platform)
    if not enum_only:
        return []

    try:
        content = Path(file_path).read_text(encoding="utf-8")
    except OSError:
        return []

    findings = []
    for m in _SAVEFORMAT_ROW_RE.finditer(content):
        format_name = m.group(1).upper()
        if format_name not in enum_only:
            continue
        if _has_warning(m.group(0)):
            continue
        line_no = content[: m.start()].count("\n") + 1
        findings.append(
            Finding(
                level="FAIL",
                filepath=str(file_path),
                line_no=line_no,
                message=(
                    f"SaveFormat.{format_name} is direction:enum_only in "
                    f"formats.json but appears in a table without a "
                    f"ValueError/not-implemented note.  Omitting this note "
                    f"misleads users: Document.save(..., SaveFormat.{format_name}) "
                    f"raises ValueError at runtime."
                ),
                suggestion=(
                    f"Update the SaveFormat.{format_name} row to include: "
                    f'"Read-only constant. `Document.save()` does not support '
                    f"{format_name} \u2014 raises `ValueError`.\""
                ),
            )
        )
    return findings