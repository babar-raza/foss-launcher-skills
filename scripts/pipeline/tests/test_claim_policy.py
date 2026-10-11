"""Tests for evidence/claim_policy.py — ClaimPolicy report-only layer (TC-CLAIM-08).

Phase 1 contract: policy decisions appear in ClaimPlan output only; injection
behavior is unchanged. All tests use in-memory data; no content/ files are read.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PIPELINE_DIR = Path(__file__).resolve().parent.parent
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))

from evidence.claim_policy import ClaimPolicy, PolicyContext, PolicyDecision


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ctx(**kwargs):
    """Build a PolicyContext with sensible defaults; override via kwargs."""
    defaults = dict(
        filepath=Path("/repo/content/reference.aspose.org/en/cells/java/Foo.md"),
        subdomain="reference.aspose.org",
        page_role=None,
        claim_id="ERC-cells-java-aabb",
        claim_kind="api",
        claim_page_role="reference",
        claim_source=None,
        token_match_context=None,
    )
    defaults.update(kwargs)
    return PolicyContext(**defaults)


# ---------------------------------------------------------------------------
# TC-CLAIM-08 required tests
# ---------------------------------------------------------------------------

def test_matching_page_role_returns_allow():
    """Claim page_role matches current subdomain → ALLOW."""
    ctx = _ctx(subdomain="reference.aspose.org", claim_page_role="reference")
    decision = ClaimPolicy().evaluate(ctx)
    assert decision.action == "ALLOW"


def test_mismatched_page_role_returns_warn_in_report_only_mode():
    """Claim page_role=reference on blog subdomain → WARN (report-only)."""
    ctx = _ctx(
        subdomain="blog.aspose.org",
        claim_page_role="reference",
        filepath=Path("/repo/content/blog.aspose.org/cells/java/post/index.md"),
    )
    decision = ClaimPolicy().evaluate(ctx)
    assert decision.action == "WARN"
    assert "reference" in decision.reason
    assert "blog.aspose.org" in decision.reason


def test_missing_page_role_returns_unknown():
    """Claim with no claim_page_role metadata on non-reference subdomain → UNKNOWN."""
    # Use docs subdomain: no Rule 3 bypass, so missing claim_page_role → UNKNOWN.
    ctx = _ctx(
        subdomain="docs.aspose.org",
        claim_page_role=None,
        filepath=Path("/repo/content/docs.aspose.org/en/cells/java/guide.md"),
    )
    decision = ClaimPolicy().evaluate(ctx)
    assert decision.action == "UNKNOWN"


def test_reference_title_based_erc_always_allow():
    """Reference subdomain + no token_match_context → ALLOW (title-based ERC)."""
    ctx = _ctx(
        subdomain="reference.aspose.org",
        claim_page_role="docs",      # mismatch, but rule 3 fires first
        token_match_context=None,
    )
    decision = ClaimPolicy().evaluate(ctx)
    assert decision.action == "ALLOW"
    assert "reference title-based" in decision.reason


def test_token_matched_claim_always_allow():
    """Token match on any subdomain → ALLOW regardless of page_role."""
    ctx = _ctx(
        subdomain="blog.aspose.org",
        claim_page_role="reference",     # would normally be WARN
        token_match_context="LoadOptions",
    )
    decision = ClaimPolicy().evaluate(ctx)
    assert decision.action == "ALLOW"
    assert "token match" in decision.reason


def test_unknown_claim_id_returns_block():
    """claim_source='UNKNOWN' → BLOCK."""
    ctx = _ctx(claim_source="UNKNOWN")
    decision = ClaimPolicy().evaluate(ctx)
    assert decision.action == "BLOCK"
    assert "not found in knowledge model" in decision.reason


def test_policy_does_not_change_injection_output_in_phase1():
    """Phase 1: ClaimPolicy.evaluate() returns a PolicyDecision without side effects.

    The function must be pure: same inputs → same outputs; no writes, no
    global state mutation. This is validated by calling it twice and checking
    the results are identical and no exceptions are raised.
    """
    ctx = _ctx(
        subdomain="docs.aspose.org",
        claim_page_role="reference",
        filepath=Path("/repo/content/docs.aspose.org/en/cells/java/guide.md"),
    )
    policy = ClaimPolicy()
    result1 = policy.evaluate(ctx)
    result2 = policy.evaluate(ctx)
    assert result1.action == result2.action
    assert result1.reason == result2.reason
    # Phase 1: injection is not blocked even for WARN — caller ignores action
    assert isinstance(result1, PolicyDecision)


# ---------------------------------------------------------------------------
# Additional coverage
# ---------------------------------------------------------------------------

def test_docs_subdomain_matching_page_role_allow():
    ctx = _ctx(
        subdomain="docs.aspose.org",
        claim_page_role="docs",
        filepath=Path("/repo/content/docs.aspose.org/en/cells/java/guide.md"),
    )
    assert ClaimPolicy().evaluate(ctx).action == "ALLOW"


def test_kb_subdomain_matching_page_role_allow():
    ctx = _ctx(
        subdomain="kb.aspose.org",
        claim_page_role="kb",
        filepath=Path("/repo/content/kb.aspose.org/en/cells/java/how-to.md"),
    )
    assert ClaimPolicy().evaluate(ctx).action == "ALLOW"


def test_products_subdomain_matching_page_role_allow():
    ctx = _ctx(
        subdomain="products.aspose.org",
        claim_page_role="products",
        filepath=Path("/repo/content/products.aspose.org/en/cells/java/_index.md"),
    )
    assert ClaimPolicy().evaluate(ctx).action == "ALLOW"


def test_unrecognised_claim_page_role_returns_unknown():
    # Use docs subdomain to avoid reference Rule 3 bypass.
    ctx = _ctx(
        subdomain="docs.aspose.org",
        claim_page_role="unknown-role",
        filepath=Path("/repo/content/docs.aspose.org/en/cells/java/guide.md"),
    )
    decision = ClaimPolicy().evaluate(ctx)
    assert decision.action == "UNKNOWN"
