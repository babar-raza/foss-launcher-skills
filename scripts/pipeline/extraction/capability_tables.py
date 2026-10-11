"""Deterministic capability-matrix extraction from README markdown tables.

H7 (MT068-2026-09-11-IMAGING-NET-LAUNCH production hardening): `enrich.py`'s
LLM enrichment absorbs a README's capability-matrix table (row = entity,
columns = capability fields, e.g. "Format | Detect | Width/Height | Bit
depth | Frame count") into ONE broad summary claim, dumping the whole table
into that one claim's evidence snippet and discarding the per-cell
structure. This module extracts each real, non-empty cell as its own
atomic, deterministic claim instead — reproducible (the same table always
produces the same claims, unlike LLM summarization) and cross-checked
against already-verified format names where one exists for this family.

Confirmed via a portfolio survey this is not imaging-specific: some
already-launched products' capability tables are entirely absent from
claims.json (slides' "choosing an edition" matrix, pdf/typescript's layout
table), not merely compressed into an unusable blob.

Design constraints (see the governing plan's H7 section for the full
rationale and the Plan-agent pressure-test that shaped these):
  - Claims-only. `formats.json`'s schema is untouched — cell semantics vary
    too much across products (an ImageInfo field vs. a per-edition feature
    vs. a load/save direction already covered elsewhere) to force into one
    structured schema honestly.
  - Fails closed. Anything that doesn't parse as a clean, well-shaped table
    is silently skipped — never fabricated, never crashes the caller.
  - Confidence-tiered, not blanket-trusted. A row label matching an
    already-verified format name earns full scout-tier confidence (1.0,
    matching `format_support`'s own enum-sourced claims); an unmatched row
    label still produces a claim (real documented data is never silently
    dropped) but at a distinctly lower confidence — honest about inheriting
    the README's own accuracy rather than independent source verification.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from lib.markdown_tables import parse_markdown_tables

# A capability matrix needs a row-label column plus at least this many
# capability columns to be worth atomizing. A plain 2-column table (e.g.
# "Format | Direction") is already covered by the DETECT-only
# `format_support` claims formats.py emits from the real enum -- this pass
# targets the genuine per-field granularity that class of claim can't
# express (Width/Height, Bit depth, Frame count, edition/feature support).
_MIN_CAPABILITY_COLUMNS = 2
_MIN_DATA_ROWS = 2

# Cell values that mean "not populated" -- never worth a claim.
_EMPTY_CELL_VALUES = {"", "-", "—", "–", "n/a", "na"}

_CHECK_MARKS = {"✅", "✔", "✔️", "✓"}
_CROSS_MARKS = {"❌", "✗", "✘"}

# Confidence for a row label that does NOT match an already-verified format
# name -- below scout's enum-sourced tier (1.0) but above nothing, matching
# the existing convention that LLM-enriched claims also sit below 1.0.
# Deliberately a module-level constant (not inlined) so a future caller can
# reason about / test against the exact value.
UNVERIFIED_CONFIDENCE = 0.75

_README_CANDIDATES = ("README.md", "Readme.md", "readme.md")

_ANNOTATION_RE = re.compile(r"^(.*?)(\s*\(.+\))?$")
_TRAILING_PAREN_RE = re.compile(r"\s*\([^()]*\)\s*$")


def _find_readme(repo: Path) -> Path | None:
    for name in _README_CANDIDATES:
        candidate = repo / name
        if candidate.is_file():
            return candidate
    return None


def _looks_like_capability_matrix(headers: list[str], rows: list[list[str]]) -> bool:
    """Fails closed on anything that isn't a clean, well-shaped matrix."""
    if len(headers) < 1 + _MIN_CAPABILITY_COLUMNS:
        return False
    if len(rows) < _MIN_DATA_ROWS:
        return False
    # A ragged table (row width != header width) is more likely a rendering
    # artifact than a real matrix -- skip rather than guess column alignment.
    return all(len(r) == len(headers) for r in rows)


def _normalize_cell_value(cell: str) -> str:
    """Turn a checkmark-style cell into natural language, preserving any
    trailing parenthetical annotation verbatim.

    "✅" -> "supported"; "✅ (assumes 96 DPI)" -> "supported (assumes 96 DPI)";
    a genuinely free-text cell (no checkmark) passes through unchanged.
    """
    stripped = cell.strip()
    match = _ANNOTATION_RE.match(stripped)
    core = (match.group(1) or "").strip() if match else stripped
    annotation = (match.group(2) or "").strip() if match else ""
    if core in _CHECK_MARKS:
        core_text = "supported"
    elif core in _CROSS_MARKS or core.lower() in ("no", "false", "unsupported"):
        core_text = "not supported"
    else:
        core_text = core
    return f"{core_text} {annotation}".strip() if annotation else core_text


def detect_capability_tables(
    repo: Path,
    family: str,
    known_formats: list[dict],
) -> tuple[list[dict], list[str]]:
    """Scan README.md for capability-matrix tables and emit one claim per
    non-empty cell.

    Args:
        repo: repository root (same as Scout.repo).
        family: product family, for claim_id construction.
        known_formats: the `formats` list already produced by
            `extraction.formats.detect_formats` for this same repo -- used
            to cross-check row labels against real, source-verified format
            names. Pass `[]` if unavailable; every claim then falls back to
            the unverified confidence tier rather than failing.

    Returns:
        (claims, covered_table_texts). `covered_table_texts` is the raw
        markdown text of each table this pass successfully atomized, so the
        caller can strip it from the README text before it reaches
        `enrich.py`'s LLM context -- replacing the old whole-table blob
        claim instead of merely supplementing it.
    """
    claims: list[dict] = []
    covered_texts: list[str] = []

    readme = _find_readme(repo)
    if readme is None:
        return claims, covered_texts

    try:
        body = readme.read_text(encoding="utf-8")
    except OSError:
        return claims, covered_texts

    known_names = {
        f["format"].lower() for f in known_formats if f.get("format")
    }

    lines = body.splitlines()
    for table in parse_markdown_tables(body):
        headers = table["headers"]
        rows = table["rows"]
        if not _looks_like_capability_matrix(headers, rows):
            continue

        row_label_header = headers[0]
        capability_headers = headers[1:]
        table_had_claim = False

        for row in rows:
            row_label_raw = row[0].strip()
            row_label_clean = _TRAILING_PAREN_RE.sub("", row_label_raw).strip()
            matched = row_label_clean.lower() in known_names
            confidence = 1.0 if matched else UNVERIFIED_CONFIDENCE

            for col_idx, cell in enumerate(row[1:], start=1):
                cell_clean = cell.strip()
                if cell_clean.lower() in _EMPTY_CELL_VALUES:
                    continue
                column_header = capability_headers[col_idx - 1]
                value_text = _normalize_cell_value(cell_clean)
                text = (
                    f"For {row_label_raw}, {column_header} is {value_text} "
                    f"(per {readme.name}'s {row_label_header} table)."
                )
                claim_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()[:6]
                claims.append({
                    "claim_id": f"CLM-{family}-{claim_hash}",
                    "kind": "capability_matrix_cell",
                    "text": text,
                    "confidence": confidence,
                    "claim_source": "scout",
                    "evidence": [{"file": readme.name, "line": table["header_line"]}],
                })
                table_had_claim = True

        if table_had_claim:
            start = table["header_line"] - 1
            end = start + 2 + len(rows)  # header + separator + data rows
            covered_texts.append("\n".join(lines[start:end]))

    return claims, covered_texts


def strip_covered_tables(readme_text: str, covered_texts: list[str]) -> str:
    """Remove each already-atomized table's raw text from README content
    before it reaches `enrich.py`'s LLM context.

    This is what makes the fix a replacement rather than a supplement: without
    it, `enrich.py` would still see the same table and still produce its own
    redundant whole-table summary claim alongside the new atomic ones.
    """
    result = readme_text
    for covered in covered_texts:
        result = result.replace(covered, "")
    return result
