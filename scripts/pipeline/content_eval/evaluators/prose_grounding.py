"""Prose grounding evaluator -- detects ungrounded capability claims.

Extracts capability claims from prose (e.g. "supports large file export",
"provides batch conversion") and checks whether each can be traced to an
entry in claims.json via TF-IDF semantic similarity.

Design constraints:
  - WARN only, never FAIL -- this evaluator is a signal, not a gate.
  - Conservative 0.30 TF-IDF cosine similarity threshold.
  - TF-IDF based, no LLM dependency -- fully deterministic.
  - Skips gracefully if knowledge is unavailable.
  - Promoted to DEFAULT_EVALUATORS after calibration (0% FP on 278 pages).
"""

from __future__ import annotations

import re
from typing import Any

from ..models import Finding, Page
from . import BaseEvaluator
from ._claim_index import get_claim_index, load_claims

# ---------------------------------------------------------------------------
# Capability-claim extraction patterns
# ---------------------------------------------------------------------------

# Group 1: "supports/can read/write/convert/export/import/load/save {cap}"
_ACTION_VERB_RE = re.compile(
    r"\b(?:supports?|can\s+(?:read|write|convert|export|import|load|save))\s+"
    r"(.{10,80}?)(?:\.|,|;|$)",
    re.IGNORECASE,
)

# Group 2: "provides/offers/enables/allows {cap}"
_PROVISION_VERB_RE = re.compile(
    r"\b(?:provides?|offers?|enables?|allows?)\s+"
    r"(.{10,80}?)(?:\.|,|;|$)",
    re.IGNORECASE,
)

# Group 3: "automatically/efficiently/quickly {action}"
_ADVERB_RE = re.compile(
    r"\b(?:automatically|efficiently|quickly)\s+"
    r"(.{10,80}?)(?:\.|,|;|$)",
    re.IGNORECASE,
)

_CLAIM_PATTERNS = [_ACTION_VERB_RE, _PROVISION_VERB_RE, _ADVERB_RE]

# Similarity threshold -- below this, the claim is considered ungrounded
_SIMILARITY_THRESHOLD = 0.30

# Minimum token count for extracted claim to be worth checking
_MIN_CLAIM_TOKENS = 3

# Patterns that indicate extracted text is not a prose claim (false positive filters)
_FP_FILTERS = [
    re.compile(r"`"),            # Contains inline code backtick — code reference, not prose
    re.compile(r"\|.*\|"),       # Table row content
    re.compile(r"^\s*[-*]"),     # Bullet list item fragment
    re.compile(r"^the\s+`"),     # "the `ClassName`" pattern
    re.compile(r"alongside\s+the\s+`"),  # Common code-adjacent phrasing
    re.compile(r"\("),           # Contains parenthetical — often tool/format lists, not claims
    re.compile(r"\bwelcome\b"),  # Community/contribution language, not capability
    re.compile(r"^(?:the|a|an)\s+(?:full|complete|entire)\s+(?:list|set)\b", re.IGNORECASE),  # Filler
    re.compile(r"^(?:a|an)\s+\w+,\s+\w+$"),  # Short adjective phrases "a stable, typed"
]


class ProseGroundingEvaluator(BaseEvaluator):
    """Check that prose capability claims are grounded in claims.json."""

    name = "prose_grounding"

    def evaluate(self, page: Page, knowledge: Any) -> list[Finding]:
        if not page.family or not page.platform:
            return []

        claims = load_claims(page.family, page.platform)
        if not claims:
            return []  # No knowledge -- skip silently

        claim_index = get_claim_index(page.family, page.platform)
        if not claim_index.available:
            return []

        findings: list[Finding] = []
        seen_claims: set[str] = set()  # deduplicate within a page

        for line_no, line_text in page.prose_lines:
            for pattern in _CLAIM_PATTERNS:
                for m in pattern.finditer(line_text):
                    claim_text = m.group(1).strip()

                    # Skip very short or already-seen claims
                    if len(claim_text.split()) < _MIN_CLAIM_TOKENS:
                        continue
                    claim_key = claim_text.lower()
                    if claim_key in seen_claims:
                        continue
                    # Skip false-positive patterns (code refs, tables, bullets)
                    if any(fp.search(claim_text) for fp in _FP_FILTERS):
                        continue
                    seen_claims.add(claim_key)

                    similarity = claim_index.best_similarity(claim_text)
                    if similarity < _SIMILARITY_THRESHOLD:
                        findings.append(Finding(
                            level="WARN",
                            category="PG",
                            filepath=str(page.filepath),
                            line_no=line_no,
                            message=(
                                f"Prose claim not grounded in knowledge: "
                                f"\"{claim_text[:60]}\""
                                f" (best similarity: {similarity:.2f})"
                            ),
                            suggestion=(
                                "Verify this capability claim against the knowledge "
                                "model or rephrase to match a known claim"
                            ),
                            evaluator=self.name,
                        ))

        return findings
