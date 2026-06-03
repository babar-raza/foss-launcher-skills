"""Tests for backlink_adjudicate_review.py — Three-Tier Adjudication."""
from __future__ import annotations

import copy
import json
import pytest
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "pipeline"))

from commands.ops.backlink_adjudicate_review import (
    adjudicate_review_required,
    promote_to_authority,
    _tier2_ai_adjudicate,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────


def _make_candidate(source_key: str, target_path: str, score: float, decision: str = "REVIEW_REQUIRED") -> dict:
    return {
        "source_key": source_key,
        "target_path": target_path,
        "final_score": score,
        "stage1_score": score - 0.05,
        "ai_boost": 0.05,
        "decision": decision,
    }


def _make_source(source_key: str, source_path: str, family: str = "cells", platform: str = "java") -> dict:
    return {
        "source_key": source_key,
        "source_path": source_path,
        "family": family,
        "platform": platform,
        "subdomain": "docs.aspose.org",
    }


def _make_graph(sources: list[dict], candidates: list[dict]) -> dict:
    return {
        "sources": sources,
        "candidates": candidates,
        "deep_index_hash": "sha256:test1234",
    }


def _make_authority(records: dict | None = None) -> dict:
    return {"authority": records or {}}


# ── Tier 1: Pass-through for already-approved ────────────────────────────────


class TestTier1PassThrough:
    def test_already_approved_skipped(self):
        """Tier 1: source_key already in authority with allowed_for_generation → skip."""
        graph = _make_graph(
            sources=[_make_source("sk1", "docs/cells/java/page1.md")],
            candidates=[_make_candidate("sk1", "reference/cells/java/Workbook", 0.72)],
        )
        authority = _make_authority({
            "docs/cells/java/page1.md": {
                "source_key": "sk1",
                "allowed_for_generation": True,
            }
        })
        result = adjudicate_review_required(graph, authority, dry_run=True)
        assert result["tier1_already_approved"] == 1
        assert len(result["promoted"]) == 0

    def test_not_approved_passes_to_tier2(self):
        """Tier 1: source_key in authority but NOT allowed → passes to Tier 2."""
        graph = _make_graph(
            sources=[_make_source("sk1", "docs/cells/java/page1.md")],
            candidates=[_make_candidate("sk1", "reference/cells/java/Workbook", 0.72)],
        )
        authority = _make_authority({
            "docs/cells/java/page1.md": {
                "source_key": "sk1",
                "allowed_for_generation": False,
            }
        })
        result = adjudicate_review_required(graph, authority, dry_run=True)
        assert result["tier1_already_approved"] == 0
        assert result["tier2_processed"] == 1


# ── Tier 2: Promotion at correct threshold ───────────────────────────────────


class TestTier2Threshold:
    def test_above_threshold_promotes(self):
        """Score >= 0.70 → PROMOTE_WITH_JUSTIFICATION."""
        candidates = [_make_candidate("sk1", "ref/cells/java/X", 0.75)]
        results = _tier2_ai_adjudicate(candidates, dry_run=True, promote_threshold=0.70)
        assert results[0]["adjudication_result"] == "PROMOTE_WITH_JUSTIFICATION"

    def test_at_threshold_promotes(self):
        """Score == 0.70 → PROMOTE_WITH_JUSTIFICATION (boundary)."""
        candidates = [_make_candidate("sk1", "ref/cells/java/X", 0.70)]
        results = _tier2_ai_adjudicate(candidates, dry_run=True, promote_threshold=0.70)
        assert results[0]["adjudication_result"] == "PROMOTE_WITH_JUSTIFICATION"

    def test_below_threshold_escalates(self):
        """Score >= 0.60 but < 0.70 → ESCALATE_TO_OPERATOR."""
        candidates = [_make_candidate("sk1", "ref/cells/java/X", 0.65)]
        results = _tier2_ai_adjudicate(candidates, dry_run=True, promote_threshold=0.70)
        assert results[0]["adjudication_result"] == "ESCALATE_TO_OPERATOR"

    def test_low_score_rejects(self):
        """Score < 0.60 → REJECT."""
        candidates = [_make_candidate("sk1", "ref/cells/java/X", 0.45)]
        results = _tier2_ai_adjudicate(candidates, dry_run=True, promote_threshold=0.70)
        assert results[0]["adjudication_result"] == "REJECT"

    def test_old_threshold_unreachable(self):
        """Old threshold 0.85 was unreachable for RR candidates scoring max 0.75."""
        candidates = [_make_candidate("sk1", "ref/cells/java/X", 0.75)]
        results = _tier2_ai_adjudicate(candidates, dry_run=True, promote_threshold=0.85)
        # At 0.85 threshold, 0.75 should NOT promote (old bug)
        assert results[0]["adjudication_result"] != "PROMOTE_WITH_JUSTIFICATION"


# ── Tier 2: Rejection ────────────────────────────────────────────────────────


class TestTier2Rejection:
    def test_reject_very_low(self):
        """Score 0.30 → REJECT."""
        candidates = [_make_candidate("sk1", "ref/cells/java/X", 0.30)]
        results = _tier2_ai_adjudicate(candidates, dry_run=True)
        assert results[0]["adjudication_result"] == "REJECT"


# ── Authority write integration ──────────────────────────────────────────────


class TestAuthorityWriteIntegration:
    def test_promoted_record_has_all_required_fields(self):
        """Promoted record must have target_subdomain, rendered_anchor_text, allowed_for_generation."""
        graph = _make_graph(
            sources=[_make_source("sk1", "docs/cells/java/page1.md")],
            candidates=[_make_candidate("sk1", "reference/cells/java/com.aspose.cells/Workbook", 0.75)],
        )
        promoted = [{
            "source_key": "sk1",
            "target_path": "reference/cells/java/com.aspose.cells/Workbook",
            "adjudication_result": "PROMOTE_WITH_JUSTIFICATION",
        }]
        authority = _make_authority()
        result = promote_to_authority(promoted, graph, authority)
        assert result["promoted_count"] == 1
        assert result["skipped_count"] == 0

        rec = authority["authority"]["docs/cells/java/page1.md"]
        assert rec["allowed_for_generation"] is True
        assert rec["target_subdomain"] is not None
        assert rec["target_subdomain"] != ""
        assert rec["decision"] == "AUTO_APPROVE_EXACT"
        assert rec["adjudicated_from"] == "REVIEW_REQUIRED"
        assert rec["approved_at"] is not None

    def test_promoted_with_anchor_registry(self):
        """When anchor registry is provided, rendered_anchor_text must be non-null."""
        graph = _make_graph(
            sources=[_make_source("sk1", "docs/cells/java/page1.md")],
            candidates=[_make_candidate("sk1", "cells/java/com.aspose.cells/Workbook", 0.75)],
        )
        promoted = [{
            "source_key": "sk1",
            "target_path": "cells/java/com.aspose.cells/Workbook",
            "adjudication_result": "PROMOTE_WITH_JUSTIFICATION",
        }]
        # Minimal anchor registry with a fallback template
        anchor_registry = {
            "templates": {
                "default": {
                    "pattern": "Aspose.{family} {platform} API",
                    "fallback": True,
                }
            }
        }
        authority = _make_authority()
        result = promote_to_authority(
            promoted, graph, authority, anchor_registry=anchor_registry
        )
        assert result["promoted_count"] == 1
        rec = authority["authority"]["docs/cells/java/page1.md"]
        # rendered_anchor_text should be non-null (either from registry or fallback)
        assert rec["rendered_anchor_text"] is not None

    def test_missing_source_skipped(self):
        """Promoted record with unknown source_key → skipped with error."""
        graph = _make_graph(sources=[], candidates=[])
        promoted = [{"source_key": "nonexistent", "adjudication_result": "PROMOTE_WITH_JUSTIFICATION"}]
        authority = _make_authority()
        result = promote_to_authority(promoted, graph, authority)
        assert result["promoted_count"] == 0
        assert result["skipped_count"] == 1
        assert len(result["errors"]) == 1


# ── max_candidates unlimited ─────────────────────────────────────────────────


class TestMaxCandidates:
    def test_zero_means_unlimited(self):
        """max_candidates=0 processes all RR candidates (no truncation)."""
        sources = [_make_source(f"sk{i}", f"docs/cells/java/page{i}.md") for i in range(100)]
        candidates = [_make_candidate(f"sk{i}", f"ref/cells/java/C{i}", 0.65) for i in range(100)]
        graph = _make_graph(sources, candidates)
        result = adjudicate_review_required(graph, None, dry_run=True, max_candidates=0)
        assert result["total_review_required"] == 100
        assert result["tier2_processed"] == 100

    def test_positive_limit_truncates(self):
        """max_candidates=10 processes only first 10."""
        sources = [_make_source(f"sk{i}", f"docs/cells/java/page{i}.md") for i in range(50)]
        candidates = [_make_candidate(f"sk{i}", f"ref/cells/java/C{i}", 0.65) for i in range(50)]
        graph = _make_graph(sources, candidates)
        result = adjudicate_review_required(graph, None, dry_run=True, max_candidates=10)
        assert result["total_review_required"] == 50
        assert result["tier2_processed"] == 10


# ── End-to-end: adjudicate + promote ─────────────────────────────────────────


class TestEndToEnd:
    def test_full_flow_promotes_high_score(self):
        """Full flow: adjudicate → promote → authority record with all fields."""
        graph = _make_graph(
            sources=[_make_source("sk1", "docs/cells/java/page1.md")],
            candidates=[_make_candidate("sk1", "reference/cells/java/Workbook", 0.75)],
        )
        authority = _make_authority()
        result = adjudicate_review_required(graph, authority, dry_run=False, promote_threshold=0.70)
        assert len(result["promoted"]) == 1

        promo_result = promote_to_authority(result["promoted"], graph, authority)
        assert promo_result["promoted_count"] == 1

        rec = authority["authority"]["docs/cells/java/page1.md"]
        assert rec["allowed_for_generation"] is True
        assert rec["target_subdomain"] == "docs"
        assert rec["adjudicated_from"] == "REVIEW_REQUIRED"
