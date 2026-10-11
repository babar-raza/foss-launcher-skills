"""taxonomy.py — Content tier and coverage status enums for S-98 enrichment.

Defines the three-tier content model and per-subdomain coverage statuses
used by the enrichment audit and candidate generation system.
"""
from __future__ import annotations

import enum


class ContentTier(enum.Enum):
    """Three-tier content model for launch and enrichment decisions."""
    MANDATORY = "mandatory"
    THRESHOLD_OPTIONAL = "threshold_optional"
    ENRICHMENT_OPTIONAL = "enrichment_optional"


class CoverageStatus(enum.Enum):
    """Per-subdomain coverage status for a cluster or sub-cluster."""
    COVERED = "covered"
    PARTIALLY_COVERED = "partially_covered"
    PRODUCT_MENTIONED_ONLY = "product_mentioned_only"
    REFERENCE_ONLY = "reference_only"
    UNCOVERED = "uncovered"
    UNKNOWN = "unknown"


class CandidateAction(enum.Enum):
    """Classification of enrichment candidate actions."""
    CREATE_NEW_DOCS_PAGE = "create_new_docs_page"
    UPDATE_EXISTING_DOCS_PAGE = "update_existing_docs_page"
    CREATE_NEW_KB_PAGE = "create_new_kb_page"
    UPDATE_EXISTING_KB_PAGE = "update_existing_kb_page"
    CREATE_NEW_BLOG_POST = "create_new_blog_post"
    UPDATE_EXISTING_BLOG_POST = "update_existing_blog_post"
    NO_ACTION_REFERENCE_ONLY = "no_action_reference_only"
    DEFER_TO_BACKLOG = "defer_to_backlog"
    REJECT_WITH_REASON = "reject_with_reason"
    BLOCK_WITH_REASON = "block_with_reason"


class CandidateDisposition(enum.Enum):
    """High-level disposition bucket for denominator invariant."""
    GENERATE_NOW = "generate_now"
    UPDATE_EXISTING = "update_existing"
    DEFERRED_TO_BACKLOG = "deferred_to_backlog"
    REJECTED_WITH_REASON = "rejected_with_reason"
    BLOCKED_WITH_REASON = "blocked_with_reason"


# Map CandidateAction to CandidateDisposition
ACTION_TO_DISPOSITION: dict[CandidateAction, CandidateDisposition] = {
    CandidateAction.CREATE_NEW_DOCS_PAGE: CandidateDisposition.GENERATE_NOW,
    CandidateAction.UPDATE_EXISTING_DOCS_PAGE: CandidateDisposition.UPDATE_EXISTING,
    CandidateAction.CREATE_NEW_KB_PAGE: CandidateDisposition.GENERATE_NOW,
    CandidateAction.UPDATE_EXISTING_KB_PAGE: CandidateDisposition.UPDATE_EXISTING,
    CandidateAction.CREATE_NEW_BLOG_POST: CandidateDisposition.GENERATE_NOW,
    CandidateAction.UPDATE_EXISTING_BLOG_POST: CandidateDisposition.UPDATE_EXISTING,
    CandidateAction.NO_ACTION_REFERENCE_ONLY: CandidateDisposition.REJECTED_WITH_REASON,
    CandidateAction.DEFER_TO_BACKLOG: CandidateDisposition.DEFERRED_TO_BACKLOG,
    CandidateAction.REJECT_WITH_REASON: CandidateDisposition.REJECTED_WITH_REASON,
    CandidateAction.BLOCK_WITH_REASON: CandidateDisposition.BLOCKED_WITH_REASON,
}


SUBDOMAINS = [
    "products.aspose.org",
    "docs.aspose.org",
    "kb.aspose.org",
    "blog.aspose.org",
    "reference.aspose.org",
]
