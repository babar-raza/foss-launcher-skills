"""Cross-page deduplication checker.

Detects near-duplicate prose paragraphs across pages within the same
family+platform combination. Uses Jaccard similarity on word tokens.

Default thresholds:
  Jaccard >= 0.85  →  FAIL  (near-identical content)
  Jaccard >= 0.70  →  WARN  (high overlap, likely redundant)

Role-aware threshold adjustments:
  reference vs reference  →  FAIL 0.92, WARN 0.80  (higher tolerance)
  kb_index / products     →  FAIL 0.92, WARN 0.80  (boilerplate-heavy)

Boilerplate exemption:
  Paragraphs dominated by install commands, import statements, or
  license text are skipped (high legitimate overlap expected).

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

# --- Boilerplate detection patterns ---
_BOILERPLATE_PATTERNS = [
    re.compile(r"pip\s+install\s+", re.IGNORECASE),
    re.compile(r"dotnet\s+add\s+package\s+", re.IGNORECASE),
    re.compile(r"<dependency>\s*<groupId>", re.IGNORECASE),
    re.compile(r"npm\s+install\s+", re.IGNORECASE),
    re.compile(r"Install-Package\s+", re.IGNORECASE),
    re.compile(r"maven\s+repository", re.IGNORECASE),
    re.compile(r"licensed?\s+under\s+the\s+MIT", re.IGNORECASE),
    re.compile(r"free\s+trial\s+(version|license|download)", re.IGNORECASE),
    re.compile(r"import\s+aspose", re.IGNORECASE),
    re.compile(r"using\s+Aspose\.", re.IGNORECASE),
]
# Fraction of boilerplate-matching tokens that triggers exemption
_BOILERPLATE_THRESHOLD = 0.40

# --- Role-aware threshold matrix ---
# Roles expected to share more legitimate boilerplate get higher thresholds.
_HIGH_OVERLAP_ROLES = frozenset({"reference", "products", "kb_index"})

# Default thresholds
_FAIL_THRESHOLD = 0.85
_WARN_THRESHOLD = 0.70
# Relaxed thresholds for role pairs where legitimate overlap is expected
_FAIL_THRESHOLD_RELAXED = 0.92
_WARN_THRESHOLD_RELAXED = 0.80


def _tokenize(text: str) -> set[str]:
    """Extract lowercase word tokens from prose."""
    return set(_WORD_RE.findall(text.lower()))


def _jaccard(a: set[str], b: set[str]) -> float:
    """Jaccard similarity between two token sets."""
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _is_boilerplate(text: str) -> bool:
    """Return True if the paragraph is dominated by boilerplate patterns."""
    matches = sum(1 for p in _BOILERPLATE_PATTERNS if p.search(text))
    return matches >= 2 or (matches >= 1 and len(text.split()) < 50)


def _get_thresholds(
    role_a: str, role_b: str,
) -> tuple[float, float]:
    """Return (fail_threshold, warn_threshold) for a page-role pair."""
    if role_a in _HIGH_OVERLAP_ROLES or role_b in _HIGH_OVERLAP_ROLES:
        return _FAIL_THRESHOLD_RELAXED, _WARN_THRESHOLD_RELAXED
    if role_a == role_b == "reference":
        return _FAIL_THRESHOLD_RELAXED, _WARN_THRESHOLD_RELAXED
    return _FAIL_THRESHOLD, _WARN_THRESHOLD


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

    def _flush():
        if not current_lines:
            return
        para = " ".join(current_lines)
        tokens = _tokenize(para)
        if len(tokens) >= _MIN_WORDS and not _is_boilerplate(para):
            raw.append((current_start, para, tokens))

    for line_no, text in page.prose_lines:
        if line_no in code_ranges:
            continue
        stripped = text.strip()
        if not stripped:
            # Blank line → flush paragraph
            _flush()
            current_lines = []
            continue
        if not current_lines:
            current_start = line_no
        current_lines.append(stripped)

    # Flush final paragraph
    _flush()

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

                # Role-aware thresholds
                fail_thresh, warn_thresh = _get_thresholds(
                    pa.page_role, pb.page_role,
                )
                if sim < warn_thresh:
                    continue

                # Deduplicate findings for same pair
                key = (str(pa.filepath), la, str(pb.filepath), lb)
                if key in seen:
                    continue
                seen.add(key)

                level = "FAIL" if sim >= fail_thresh else "WARN"
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
