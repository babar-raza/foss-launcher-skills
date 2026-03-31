"""Claim coverage evaluator — detects phantom evidence claims.

Checks that every claim ID listed in the frontmatter ``evidence.claims``
block is actually discussed in the page body.  A claim is considered
"discussed" when its text has at least 0.2 Jaccard overlap with the page
body OR when any 3+ consecutive words from the claim text appear verbatim
in the body.  Claims that are listed but never mentioned are flagged as
phantom evidence.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..models import Finding, Page
from . import BaseEvaluator

KNOWLEDGE_ROOT = Path("knowledge")


def _load_claims(family: str, platform: str) -> dict[str, str]:
    """Return a dict of claim_id → claim text, or {} if unavailable."""
    path = KNOWLEDGE_ROOT / family / platform / "merged" / "claims.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {entry["claim_id"]: entry.get("text", "") for entry in data if "claim_id" in entry}
    except (json.JSONDecodeError, KeyError, TypeError):
        return {}


def _tokenize(text: str) -> list[str]:
    """Return list of lowercase alphanumeric tokens."""
    return re.findall(r"[a-z0-9]+", text.lower())


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _has_ngram_match(claim_tokens: list[str], body_lower: str, n: int = 3) -> bool:
    """Return True if any n consecutive tokens from claim appear as a phrase in body."""
    if len(claim_tokens) < n:
        # Shorter claims: join them and do substring search
        phrase = " ".join(claim_tokens)
        return phrase in body_lower
    for i in range(len(claim_tokens) - n + 1):
        phrase = " ".join(claim_tokens[i : i + n])
        if phrase in body_lower:
            return True
    return False


class ClaimCoverageEvaluator(BaseEvaluator):
    """Verifies that every claim cited in evidence.claims is present in page content.

    Phantom evidence — claims listed in the frontmatter that are never
    discussed in the page body — are flagged as WARN.
    """

    name = "claim_coverage"

    def evaluate(self, page: Page, knowledge: Any) -> list[Finding]:
        # Require a valid product
        if not page.family or not page.platform:
            return []

        # Only check pages that cite evidence claims
        evidence = page.frontmatter.get("evidence", {})
        if not isinstance(evidence, dict):
            return []
        cited_ids: list[str] = evidence.get("claims", [])
        if not cited_ids:
            return []

        # Need knowledge to be meaningful
        if not (hasattr(knowledge, "available") and knowledge.available):
            return []

        # Skip very short pages
        prose_word_count = sum(len(line.split()) for _, line in page.prose_lines)
        if prose_word_count < 50:
            return []

        # Load the product's claims catalogue
        claim_map = _load_claims(page.family, page.platform)
        if not claim_map:
            return []

        body_lower = page.body.lower()
        body_tokens: set[str] = set(_tokenize(page.body))

        findings: list[Finding] = []

        for claim_id in cited_ids:
            claim_text = claim_map.get(claim_id, "")
            if not claim_text:
                # Claim ID not in knowledge — that's a different problem; skip here
                continue

            claim_tokens = _tokenize(claim_text)
            claim_token_set: set[str] = set(claim_tokens)

            jaccard = _jaccard(claim_token_set, body_tokens)
            if jaccard >= 0.2:
                continue  # Sufficient overlap — claim is discussed

            if _has_ngram_match(claim_tokens, body_lower, n=3):
                continue  # 3+ consecutive words found — claim is discussed

            findings.append(Finding(
                level="WARN",
                category="CC",
                filepath=str(page.filepath),
                line_no=1,
                message=f"Claim {claim_id} listed in evidence but not found in page content",
                suggestion=(
                    f"Either add content that discusses \"{claim_text[:80]}\" "
                    f"or remove {claim_id} from evidence.claims"
                ),
                evaluator=self.name,
            ))

        return findings
