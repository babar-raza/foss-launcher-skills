"""Cross-page deduplication checker.

Detects near-duplicate prose paragraphs across pages within the same
family+platform combination. Uses Jaccard similarity on word tokens.

Thresholds:
  Jaccard >= 0.85  →  FAIL  (near-identical content)
  Jaccard >= 0.70  →  WARN  (high overlap, likely redundant)

Performance caps:
  _MAX_PARAGRAPHS_PER_PAGE = 15   (keep longest by token count)
  _MAX_COMPARISONS = 10_000       (stop comparing after this many pairs)
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..models import Finding, Page

log = logging.getLogger(__name__)

_WORD_RE = re.compile(r"[a-z][a-z0-9_]+")
_MIN_WORDS = 30  # skip paragraphs shorter than this
_MAX_PARAGRAPHS_PER_PAGE = 15  # keep longest paragraphs per page
_MAX_COMPARISONS = 10_000  # cap total cross-page paragraph comparisons


def _tokenize(text: str) -> set[str]:
    """Extract lowercase word tokens from prose."""
    return set(_WORD_RE.findall(text.lower()))


def _jaccard(a: set[str], b: set[str]) -> float:
    """Jaccard similarity between two token sets."""
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _extract_paragraphs(page: "Page") -> list[tuple[int, str, set[str]]]:
    """Extract prose paragraphs (>= _MIN_WORDS, outside code blocks) from a page.

    Returns list of (line_no, paragraph_text, token_set), sorted by token
    count descending and capped at _MAX_PARAGRAPHS_PER_PAGE.
    """
    # Build set of line ranges inside code blocks
    code_ranges: set[int] = set()
    for cb in page.code_blocks:
        for ln in range(cb.start_line, cb.end_line + 1):
            code_ranges.add(ln)

    raw: list[tuple[int, str, set[str]]] = []
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
                tokens = _tokenize(para)
                if len(tokens) >= _MIN_WORDS:
                    raw.append((current_start, para, tokens))
                current_lines = []
            continue
        if not current_lines:
            current_start = line_no
        current_lines.append(stripped)

    # Flush final paragraph
    if current_lines:
        para = " ".join(current_lines)
        tokens = _tokenize(para)
        if len(tokens) >= _MIN_WORDS:
            raw.append((current_start, para, tokens))

    # Cap: keep longest paragraphs (by token count), stable sort on ties
    raw.sort(key=lambda t: (-len(t[2]), t[0]))
    return raw[:_MAX_PARAGRAPHS_PER_PAGE]


def check_deduplication(pages: list["Page"]) -> list["Finding"]:
    """Detect near-duplicate prose paragraphs across pages.

    Only compares pages within the same (family, platform) group.
    Capped at _MAX_COMPARISONS total cross-page paragraph comparisons.

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

    total_comparisons = 0
    total_pages = 0
    cap_hit = False

    for _key, group_pages in groups.items():
        total_pages += len(group_pages)

        # Pre-extract and tokenize paragraphs per page (single pass)
        page_paras: list[tuple["Page", int, str, set[str]]] = []
        for page in group_pages:
            for line_no, text, tokens in _extract_paragraphs(page):
                page_paras.append((page, line_no, text, tokens))

        # Compare all cross-page pairs (skip same-page pairs)
        seen: set[tuple[str, int, str, int]] = set()
        for i, (pa, la, _ta, toka) in enumerate(page_paras):
            if cap_hit:
                break
            for j in range(i + 1, len(page_paras)):
                pb, lb, _tb, tokb = page_paras[j]
                # Only compare across different pages
                if pa.filepath == pb.filepath:
                    continue

                total_comparisons += 1
                if total_comparisons > _MAX_COMPARISONS:
                    cap_hit = True
                    break

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

    # Summary logging
    fail_count = sum(1 for f in findings if f.level == "FAIL")
    warn_count = sum(1 for f in findings if f.level == "WARN")
    log.info(
        "cross_dedup: %d pages, %d comparisons, %d findings (%d FAIL, %d WARN)%s",
        total_pages, total_comparisons, len(findings), fail_count, warn_count,
        " [comparison cap reached]" if cap_hit else "",
    )

    return findings
