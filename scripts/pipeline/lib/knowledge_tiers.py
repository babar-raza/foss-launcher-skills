"""knowledge_tiers.py — RPR-J-07: tier a claim_id by its ID-scheme prefix.

Two independent pipelines feed knowledge/{family}/{platform}/merged/claims.json:
  - CLM-{family}-{hash}          — deterministic extraction (scout / api_surface /
    formats; scripts/pipeline/extraction/{claims,api_surface,formats,scout}.py).
    Zero LLM involvement. Tier 1.
  - ERC-{family}-{platform}-{hash} — LLM enrichment (enrich.py::_assign_ids).
    Tier 2 — generated content, not independently verified against source.

Blocking gates (evidence_verifier.py, post_refresh_verify.py Check 2) must not
FAIL a commit purely because a Tier-2 (enriched) claim_id is missing from the
current claims.json. RPR-J-16 stabilized claim identity only for the member-doc
majority of enriched claims; capability-mode enriched claims are still
content-hash-keyed and legitimately churn across a knowledge rebuild — that
churn is expected, not a defect. A Tier-1 (scout) claim_id going missing is a
real, deterministic signal (the underlying API/format genuinely changed) and
must still block.

The tier is read from the claim_id's OWN prefix, not looked up in claims.json —
deliberately: a *missing* claim_id has no content to inspect, so tiering must be
determinable from the reference string itself, not from claim data that may not
exist.
"""
from __future__ import annotations

_TIER1_PREFIX = "CLM-"
_TIER2_PREFIX = "ERC-"


def claim_tier(claim_id: "str | None") -> int:
    """Return 1 (deterministic/scout), 2 (LLM-enriched), or 0 (unrecognized
    scheme, or not a string). 0 is deliberately NOT treated as Tier-2 —
    absent tier certainty, callers should treat it as blocking (see
    is_tier1_claim_id's docstring)."""
    if not isinstance(claim_id, str):
        return 0
    if claim_id.startswith(_TIER1_PREFIX):
        return 1
    if claim_id.startswith(_TIER2_PREFIX):
        return 2
    return 0


def is_tier1_claim_id(claim_id: "str | None") -> bool:
    """True only for a confirmed Tier-1 (CLM-*) id."""
    return claim_tier(claim_id) == 1


def is_tier2_claim_id(claim_id: "str | None") -> bool:
    """True only for a confirmed Tier-2 (ERC-*) id. An unrecognized scheme is
    NOT granted Tier-2 leniency by this function returning True — callers
    gating severity on this must keep the conservative default (blocking) for
    anything that isn't explicitly confirmed Tier-2."""
    return claim_tier(claim_id) == 2
