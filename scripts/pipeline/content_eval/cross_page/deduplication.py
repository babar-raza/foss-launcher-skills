"""Cross-page deduplication checker.

Detects near-duplicate prose paragraphs across pages within the same
family+platform combination. Uses Jaccard similarity on word tokens.

Thresholds:
  Jaccard >= 0.85  →  FAIL  (near-identical content)
  Jaccard >= 0.70  →  WARN  (high overlap, likely redundant)
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..models import Finding, Page

_WORD_RE = re.compile(r"[a-z][a-z0-9_]+")
_MIN_WORDS = 30  # skip paragraphs shorter than this


def _tokenize(text: str) -> set[str]:
    """Extract lowercase word tokens from prose."""
    return set(_WORD_RE.findall(text.lower()))


def _jaccard(a: set[str], b: set[str]) -> float:
    """Jaccard similarity between two token sets."""
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _extract_paragraphs(page: "Page") -> list[tuple[int, str]]:
    """Extract prose paragraphs (>= _MIN_WORDS, outside code blocks) from a page.

    Returns list of (line_no, paragraph_text).
    """
    # Build set of line ranges inside code blocks
    code_ranges: set[int] = set()
    for cb in page.code_blocks:
        for ln in range(cb.start_line, cb.end_line + 1):
            code_ranges.add(ln)

    paragraphs: list[tuple[int, str]] = []
    current_lines: list[str] = []
    current_start = 0

    for line_no, text in page.prose_lines:
        if line_no in code_ranges:
            continue
        stripped = text.strip()
        if not stripped:
            # Blank line → flush paragraph
            if current_lines:
                para = " ".join(current_lines)
                tokens = _WORD_RE.findall(para.lower())
                if len(tokens) >= _MIN_WORDS:
                    paragraphs.append((current_start, para))
                current_lines = []
            continue
        if not current_lines:
            current_start = line_no
        current_lines.append(stripped)

    # Flush final paragraph
    if current_lines:
        para = " ".join(current_lines)
        tokens = _WORD_RE.findall(para.lower())
        if len(tokens) >= _MIN_WORDS:
            paragraphs.append((current_start, para))

    return paragraphs


def check_deduplication(pages: list["Page"]) -> list["Finding"]:
    """Detect near-duplicate prose paragraphs across pages.

    Only compares pages within the same (family, platform) group.

    Returns
    -------
    list[Finding]
        FAIL for Jaccard >= 0.85, WARN for Jaccard >= 0.70.
    """
    from ..models import Finding

    findings: list[Finding] = []

    # Group pages by (family, platform)
    groups: dict[tuple[str, str], list["Page"]] = defaultdict(list)
    for page in pages:
        if page.family and page.platform:
            groups[(page.family, page.platform)].append(page)

    for _key, group_pages in groups.items():
        # Pre-extract and tokenize paragraphs per page
        page_paras: list[tuple["Page", int, str, set[str]]] = []
        for page in group_pages:
            for line_no, text in _extract_paragraphs(page):
                tokens = _tokenize(text)
                if len(tokens) >= _MIN_WORDS:
                    page_paras.append((page, line_no, text, tokens))

        # Compare all cross-page pairs (skip same-page pairs)
        seen: set[tuple[str, int, str, int]] = set()
        for i, (pa, la, _ta, toka) in enumerate(page_paras):
            for j in range(i + 1, len(page_paras)):
                pb, lb, _tb, tokb = page_paras[j]
                # Only compare across different pages
                if pa.filepath == pb.filepath:
                    continue

                sim = _jaccard(toka, tokb)
                if sim < 0.70:
                    continue

                # Deduplicate findings for same pair
                key = (str(pa.filepath), la, str(pb.filepath), lb)
                if key in seen:
                    continue
                seen.add(key)

                level = "FAIL" if sim >= 0.85 else "WARN"
                findings.append(Finding(
                    level=level,
                    category="XD",
                    filepath=str(pa.filepath),
                    line_no=la,
                    message=(
                        f"Near-duplicate paragraph (Jaccard={sim:.2f}) "
                        f"with {pb.filepath}:{lb}"
                    ),
                    suggestion=(
                        "Consolidate or differentiate the overlapping content "
                        "to avoid redundancy across pages."
                    ),
                    evaluator="cross_dedup",
                ))

    return findings
