"""Prose claim binding evaluator — verifies factual prose maps to claims.json.

H-11: Extracts declarative sentences from prose (those containing verbs like
"supports", "provides", "enables") and checks whether each can be traced to
a claim in the knowledge model via TF-IDF semantic matching.

Site-specific severity:
    reference → FAIL  (must be fully grounded)
    blog / kb → WARN  (should be grounded)
    docs      → INFO  (may contain introductory framing)
    products  → WARN
"""

from __future__ import annotations

import re
from typing import Any

from ..models import Finding, Page
from . import BaseEvaluator
from ._claim_index import get_claim_index, load_claims, tokenize

# Verbs that signal a factual, declarative sentence about capability
_DECLARATIVE_VERB_RE = re.compile(
    r"\b(?:supports?|provides?|enables?|includes?|offers?|allows?|"
    r"implements?|delivers?|exposes?|ships?\s+with|comes?\s+with)\b",
    re.IGNORECASE,
)

# Site-specific severity for unbound claims
_CLAIM_BINDING_SEVERITY: dict[str, str] = {
    "reference": "FAIL",
    "blog": "WARN",
    "kb": "WARN",
    "docs": "INFO",
    "products": "WARN",
}

# Minimum sentence length to check (skip short fragments)
_MIN_WORDS = 8


class ProseClaimBindingEvaluator(BaseEvaluator):
    """Check that factual prose sentences trace to claims.json entries."""

    name = "prose_claim_binding"

    def evaluate(self, page: Page, knowledge: Any) -> list[Finding]:
        if not page.family or not page.platform:
            return []

        claims = load_claims(page.family, page.platform)
        if not claims:
            return []  # No claims to match against

        claim_index = get_claim_index(page.family, page.platform)
        if not claim_index.available:
            return []

        # Build token sets for fast overlap check
        claim_token_sets = [
            tokenize(c.get("text", ""))
            for c in claims if c.get("text")
        ]

        findings: list[Finding] = []
        level = _CLAIM_BINDING_SEVERITY.get(page.subdomain, "WARN")

        for line_no, line_text in page.prose_lines:
            if not _DECLARATIVE_VERB_RE.search(line_text):
                continue

            words = line_text.split()
            if len(words) < _MIN_WORDS:
                continue

            line_tokens = tokenize(line_text)
            if len(line_tokens) < 4:
                continue

            # Primary tier: token overlap
            best_overlap = 0.0
            for ct in claim_token_sets:
                if ct:
                    overlap = len(line_tokens & ct) / max(len(ct), 1)
                    best_overlap = max(best_overlap, overlap)

            if best_overlap >= 0.3:
                continue  # Matched by token overlap

            # Secondary tier: TF-IDF semantic similarity
            similarity = claim_index.best_similarity(line_text)
            if similarity >= 0.3:
                continue  # Matched by semantic similarity

            findings.append(Finding(
                level=level,
                category="CB",
                filepath=str(page.filepath),
                line_no=line_no,
                message="Factual claim not traceable to any entry in claims.json",
                suggestion="Verify claim against knowledge model or add supporting evidence",
                evaluator=self.name,
            ))

        return findings
