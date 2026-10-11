"""claim_policy.py — Pure policy module for claim injection decisions.

Evaluates whether a candidate claim should be ALLOW, WARN, BLOCK, or UNKNOWN
for a given target page. Phase 1 behavior: report-only, no injection change.

This module is stateless and does not write to any file. It is called from
runner.py during ClaimPlan (--dry-run-json) generation.

Phase 1 contract:
  - All claims continue to be injected regardless of policy_status.
  - WARN/BLOCK/UNKNOWN appear in ClaimPlan output only.
  - Phase 2 (post apply-gate): BLOCK can be enforced via config.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal


@dataclass
class PolicyContext:
    """Context for evaluating a single candidate claim injection."""
    filepath: Path
    subdomain: str                   # e.g. "blog.aspose.org"
    page_role: "str | None"          # from page frontmatter; None if absent
    claim_id: str                    # e.g. "ERC-cells-java-c60e46fb"
    claim_kind: "str | None"         # "api", "feature", "format", etc.; None if unknown
    claim_page_role: "str | None"    # page_role field from merged/claims.json; None if absent
    claim_source: "str | None"       # "scout", "llm_member_doc", etc.; None if unknown
    token_match_context: "str | None"  # matched API token (e.g. "LoadOptions"); None if absent


@dataclass
class PolicyDecision:
    """Policy evaluation result for one candidate claim."""
    action: Literal["ALLOW", "WARN", "BLOCK", "UNKNOWN"]
    reason: str


# Subdomains where reference-style title-based ERC injection is authorised.
_REFERENCE_SUBDOMAINS = frozenset({"reference.aspose.org"})


class ClaimPolicy:
    """Evaluates claim injection policy for a single candidate.

    Phase 1 (report-only): All claims are injected regardless of the returned
    action. The action and reason appear in ClaimPlan output only.

    Rules (in priority order):
      1. Claim not in knowledge → BLOCK (unknown claim should never be injected)
      2. Token-matched claims → ALLOW (direct code evidence)
      3. Reference title-based ERC (subdomain=reference.aspose.org, no token) → ALLOW
      4. page_role match between claim and page → ALLOW
      5. page_role mismatch → WARN
      6. claim_page_role absent → UNKNOWN
      7. Fallback → ALLOW
    """

    def evaluate(self, ctx: PolicyContext) -> PolicyDecision:
        """Return a PolicyDecision for the given context."""
        claim_id = ctx.claim_id

        # Rule 1: Unknown claim ID — claim is not in the knowledge model
        # (caller must pass claim_source=None and claim_page_role=None when
        # the claim is not found; we detect this by a missing claim_source AND
        # claim_page_role AND the ID not matching known prefixes — but since we
        # have no knowledge reference here, callers signal this by setting
        # claim_source="UNKNOWN" or via a sentinel.)
        if ctx.claim_source == "UNKNOWN":
            return PolicyDecision(
                action="BLOCK",
                reason=f"claim {claim_id!r} not found in knowledge model",
            )

        # Rule 2: Token-matched claim → ALLOW regardless of page_role
        if ctx.token_match_context:
            return PolicyDecision(
                action="ALLOW",
                reason=f"token match: {ctx.token_match_context!r}",
            )

        # Rule 3: Reference subdomain title-based ERC injection → ALLOW
        # (runner.py:73-90 injects ERC from page title when no token matches;
        # this is an intentional design for reference pages)
        if ctx.subdomain in _REFERENCE_SUBDOMAINS and not ctx.token_match_context:
            return PolicyDecision(
                action="ALLOW",
                reason="reference title-based ERC injection (authorised by design)",
            )

        # Rules 4/5/6: page_role comparison
        claim_page_role = ctx.claim_page_role
        if claim_page_role is None:
            # No page_role metadata on claim — cannot evaluate
            return PolicyDecision(
                action="UNKNOWN",
                reason=f"claim {claim_id!r} has no page_role metadata",
            )

        # Derive expected subdomain from claim_page_role
        role_to_subdomain = {
            "reference": "reference.aspose.org",
            "docs": "docs.aspose.org",
            "blog": "blog.aspose.org",
            "kb": "kb.aspose.org",
            "products": "products.aspose.org",
        }
        expected_subdomain = role_to_subdomain.get(claim_page_role)

        if expected_subdomain is None:
            # Unrecognised page_role value
            return PolicyDecision(
                action="UNKNOWN",
                reason=f"unrecognised claim page_role={claim_page_role!r}",
            )

        if ctx.subdomain == expected_subdomain:
            return PolicyDecision(
                action="ALLOW",
                reason=f"claim page_role={claim_page_role!r} matches subdomain",
            )

        # Mismatch: claim targets a different subdomain
        return PolicyDecision(
            action="WARN",
            reason=(
                f"claim page_role={claim_page_role!r} targets {expected_subdomain!r}; "
                f"current subdomain is {ctx.subdomain!r}"
            ),
        )
