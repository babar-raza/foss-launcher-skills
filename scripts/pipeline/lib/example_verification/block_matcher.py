"""block_matcher.py — TC-01 (MT073-2026-09-24-LOCALE-CODE-BLOCK-DEFECT-
REMEDIATION): match English code blocks to their locale counterparts even
when the two pages' block COUNTS differ.

CONTRACT: scripts/pipeline/lib/example_verification/block_matcher.py
  purpose: `locale_code_block_equivalence.py` (MT072/TC-14) and TC-19's own
           ad-hoc categorization script both paired English block N to
           locale block N by raw positional index -- correct only when the
           two pages have the exact same block count. TC-19's own report
           disclosed this: an automated position-based check only
           mechanically confirmed 271 of 7,322 real tag-mistranslation
           instances, because widespread English/locale block-count drift
           (a single inserted/removed block anywhere in the document)
           silently misaligns every position-based comparison from that
           point onward. This module fixes the pairing, not the downstream
           consumers -- callers get a real (index, index-or-None,
           confidence) mapping instead of blindly trusting position.
  inputs:  two lists of `CodeBlock` (English, locale), in document order
  outputs: list[BlockMatch], one entry per English block, in English order
  owner_domain: content-quality
  requires_test: true

Strategy: exact position first (cheap, correct, and by far the common case
-- most pages have NO block-count drift at all). When counts differ, fall
back to a greedy best-similarity assignment using `difflib.SequenceMatcher`
on each block's raw content: real code identifiers and API calls survive
translation even when comments don't, so a genuine English/locale
correspondence scores far higher than a coincidental one. Deliberately does
NOT force every English block to match something -- a block whose best
candidate scores below `min_similarity` is reported UNMATCHED rather than
wrongly paired. A wrong pairing is strictly worse than no pairing for
anything downstream (e.g. a tag-restore fixer) that trusts this module's
output: an unmatched block is skipped and disclosed; a mis-matched one
would silently corrupt a fix.
"""
from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .code_fences import CodeBlock

DEFAULT_MIN_SIMILARITY = 0.5


@dataclass(slots=True)
class BlockMatch:
    """One English block's pairing outcome.

    `locale_index` is None when no locale block scored above
    `min_similarity` (or there were no locale blocks left to assign) --
    callers must treat this as "no confident correspondence exists", not
    coerce it to the same-position block.
    """

    en_index: int
    locale_index: "int | None"
    similarity: float
    method: str  # "position" | "content-similarity" | "unmatched"


def _similarity(a: str, b: str) -> float:
    if not a and not b:
        return 1.0
    return SequenceMatcher(None, a, b, autojunk=False).ratio()


def match_blocks(
    en_blocks: "list[CodeBlock]",
    locale_blocks: "list[CodeBlock]",
    *,
    min_similarity: float = DEFAULT_MIN_SIMILARITY,
) -> "list[BlockMatch]":
    """Return one BlockMatch per English block, in English block order.

    Fast path: equal counts -> position pairing (similarity fixed at 1.0;
    this module does not re-verify content similarity in that case --
    matching TC-19's own original, still-valid assumption for the common,
    non-drifted case).

    Fallback: unequal counts -> global greedy best-similarity assignment.
    Every (English, locale) pair is scored once; pairs are assigned in
    descending score order, skipping any English or locale index already
    used. This is O(n*m) content comparisons, fine at the block counts
    real pages have (rarely more than ~20).
    """
    if len(en_blocks) == len(locale_blocks):
        return [
            BlockMatch(en_index=i, locale_index=i, similarity=1.0, method="position")
            for i in range(len(en_blocks))
        ]

    scored: "list[tuple[float, int, int]]" = []
    for ei, eb in enumerate(en_blocks):
        for li, lb in enumerate(locale_blocks):
            scored.append((_similarity(eb.content, lb.content), ei, li))
    scored.sort(key=lambda p: -p[0])

    assigned: "dict[int, BlockMatch]" = {}
    used_locale: "set[int]" = set()
    for score, ei, li in scored:
        if ei in assigned or li in used_locale:
            continue
        if score < min_similarity:
            continue
        assigned[ei] = BlockMatch(en_index=ei, locale_index=li, similarity=score, method="content-similarity")
        used_locale.add(li)

    return [
        assigned.get(ei, BlockMatch(en_index=ei, locale_index=None, similarity=0.0, method="unmatched"))
        for ei in range(len(en_blocks))
    ]
