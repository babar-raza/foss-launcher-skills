"""Tests for backlink_adjudicate_review.py — Three-Tier Adjudication."""
from __future__ import annotations

import copy
import json
import pytest
import sys
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "pipeline"))

from commands.ops.backlink_adjudicate_review import (
    adjudicate_review_required,
    promote_to_authority,
    _tier2_ai_adjudicate,
    _tier2_semantic_confirm,
    _load_page_texts,
    _sc_tokenize,
    _sc_cosine,
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
            candidates=[_make_candidate("sk1", "reference/cells/java/org.aspose.cells/Workbook", 0.75)],
        )
        promoted = [{
            "source_key": "sk1",
            "target_path": "reference/cells/java/org.aspose.cells/Workbook",
            "adjudication_result": "PROMOTE_WITH_JUSTIFICATION",
        }]
        anchor_registry = {"templates": {"default": {"pattern": "Aspose.{family} {platform} API", "fallback": True}}}
        authority = _make_authority()
        result = promote_to_authority(promoted, graph, authority, anchor_registry=anchor_registry)
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
            candidates=[_make_candidate("sk1", "cells/java/org.aspose.cells/Workbook", 0.75)],
        )
        promoted = [{
            "source_key": "sk1",
            "target_path": "cells/java/org.aspose.cells/Workbook",
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

        anchor_registry = {"templates": {"default": {"pattern": "Aspose.{family} {platform} API", "fallback": True}}}
        promo_result = promote_to_authority(result["promoted"], graph, authority, anchor_registry=anchor_registry)
        assert promo_result["promoted_count"] == 1

        rec = authority["authority"]["docs/cells/java/page1.md"]
        assert rec["allowed_for_generation"] is True
        assert rec["target_subdomain"] == "docs"
        assert rec["adjudicated_from"] == "REVIEW_REQUIRED"


# ── Null anchor guard ─────────────────────────────────────────────────────────


class TestNullAnchorGuard:
    def test_null_anchor_text_skipped(self):
        """When anchor_registry=None, promoted records are skipped (null anchor guard)."""
        graph = _make_graph(
            sources=[_make_source("sk1", "docs/cells/java/page1.md")],
            candidates=[_make_candidate("sk1", "cells/java/org.aspose.cells/Workbook", 0.75)],
        )
        promoted = [{
            "source_key": "sk1",
            "target_path": "cells/java/org.aspose.cells/Workbook",
            "adjudication_result": "PROMOTE_WITH_JUSTIFICATION",
        }]
        authority = _make_authority()
        result = promote_to_authority(promoted, graph, authority, anchor_registry=None)
        # Guard: null anchor → skipped, not promoted
        assert result["promoted_count"] == 0, "FAIL: null anchor was not blocked"
        assert len(result.get("skipped", [])) == 1, "FAIL: skipped list not populated"
        assert result["skipped"][0]["reason"] == "null_anchor_text"
        # Authority must NOT contain the source page
        assert "docs/cells/java/page1.md" not in authority["authority"]

    def test_write_and_dry_run_conflict(self):
        """CLI: --write and --dry-run together → exit code 1 with error message."""
        import subprocess
        script = str(REPO_ROOT / "scripts" / "pipeline" / "commands" / "ops" / "backlink_adjudicate_review.py")
        env = {**__import__("os").environ, "PYTHONPATH": str(REPO_ROOT / "scripts" / "pipeline")}
        proc = subprocess.run(
            [sys.executable, script, "--write", "--dry-run"],
            capture_output=True, text=True, env=env,
        )
        assert proc.returncode == 1, f"Expected exit 1, got {proc.returncode}"
        assert "mutually exclusive" in proc.stderr.lower() or "mutually exclusive" in proc.stdout.lower()


# ── CS-013: LLMRouter wiring (Tier 2 AI adjudication) ────────────────────────


class TestTier2AIAdjudication:
    """Tests for CS-013 LLMRouter integration in _tier2_ai_adjudicate()."""

    def test_dry_run_preserves_ai_explicitly_disabled(self):
        """dry_run=True: ai_status is AI_EXPLICITLY_DISABLED, score-based result unchanged."""
        candidates = [_make_candidate("docs/cells/java/sk1.md", "ref/cells/java/X", 0.88)]
        results = _tier2_ai_adjudicate(candidates, dry_run=True, promote_threshold=0.70)
        r = results[0]
        assert r["ai_status"] == "AI_EXPLICITLY_DISABLED"
        assert r["adjudication_result"] == "PROMOTE_WITH_JUSTIFICATION"
        assert r["ai_label"] is None

    def test_ai_exact_boost_promotes(self):
        """dry_run=False, LLM returns exact_api_class with base >= 0.85: boosted score promotes."""
        from unittest.mock import MagicMock, patch
        mock_router = MagicMock()
        mock_result = MagicMock()
        mock_result.status.value = "ok"
        mock_result.data = {"label": "exact_api_class", "confidence": "high", "reasoning": "direct match"}
        mock_router.call_chat.return_value = mock_result

        with patch(
            "commands.ops.backlink_adjudicate_review._try_import_llm_router",
            return_value=mock_router,
        ):
            candidates = [_make_candidate("docs/cells/java/sk1.md", "ref/cells/java/X", 0.87)]
            results = _tier2_ai_adjudicate(candidates, dry_run=False, promote_threshold=0.70)

        r = results[0]
        assert r["ai_status"] == "AI_CLASSIFIED"
        assert r["ai_label"] == "exact_api_class"
        assert r["adjudication_result"] == "PROMOTE_WITH_JUSTIFICATION"

    def test_ai_unrelated_high_base_forces_escalation(self):
        """dry_run=False, LLM returns unrelated + score >= 0.80: ESCALATE_TO_OPERATOR."""
        from unittest.mock import MagicMock, patch
        mock_router = MagicMock()
        mock_result = MagicMock()
        mock_result.status.value = "ok"
        mock_result.data = {"label": "unrelated", "confidence": "high", "reasoning": "no match"}
        mock_router.call_chat.return_value = mock_result

        with patch(
            "commands.ops.backlink_adjudicate_review._try_import_llm_router",
            return_value=mock_router,
        ):
            candidates = [_make_candidate("docs/cells/java/sk1.md", "ref/cells/java/X", 0.83)]
            results = _tier2_ai_adjudicate(candidates, dry_run=False, promote_threshold=0.70)

        r = results[0]
        assert r["ai_status"] == "AI_CLASSIFIED"
        assert r["adjudication_result"] == "ESCALATE_TO_OPERATOR"

    def test_ai_unavailable_degrades_gracefully(self):
        """dry_run=False, LLMRouter raises: AI_UNAVAILABLE_DEGRADED, score-based fallback, no crash."""
        from unittest.mock import MagicMock, patch
        mock_router = MagicMock()
        mock_router.call_chat.side_effect = RuntimeError("connection refused")

        with patch(
            "commands.ops.backlink_adjudicate_review._try_import_llm_router",
            return_value=mock_router,
        ):
            candidates = [_make_candidate("docs/cells/java/sk1.md", "ref/cells/java/X", 0.55)]
            results = _tier2_ai_adjudicate(candidates, dry_run=False, promote_threshold=0.70)

        r = results[0]
        assert r["ai_status"] == "AI_UNAVAILABLE_DEGRADED"
        assert r["adjudication_result"] == "REJECT"  # 0.55 < 0.60 floor

    def test_ai_exact_label_surfaces_dead_zone_to_tier3(self):
        """dry_run=False, LLM returns exact_api_class + score 0.55 (below threshold): ESCALATE."""
        from unittest.mock import MagicMock, patch
        mock_router = MagicMock()
        mock_result = MagicMock()
        mock_result.status.value = "ok"
        mock_result.data = {"label": "exact_api_class", "confidence": "high", "reasoning": "clear match"}
        mock_router.call_chat.return_value = mock_result

        with patch(
            "commands.ops.backlink_adjudicate_review._try_import_llm_router",
            return_value=mock_router,
        ):
            candidates = [_make_candidate("docs/email/net/sk1.md", "ref/email/net/X", 0.55)]
            results = _tier2_ai_adjudicate(candidates, dry_run=False, promote_threshold=0.70)

        r = results[0]
        assert r["ai_status"] == "AI_CLASSIFIED"
        assert r["adjudication_result"] == "ESCALATE_TO_OPERATOR"  # surfaces dead zone


# ── TC-BLINK-001: Semantic Confirmation Tests ────────────────────────────────


class TestSemanticConfirmHelpers:
    def test_sc_tokenize_basic(self):
        tokens = _sc_tokenize("The Workbook class provides spreadsheet data export")
        assert "workbook" in tokens
        assert "spreadsheet" in tokens
        assert "the" not in tokens  # stopword

    def test_sc_cosine_identical(self):
        tokens = _sc_tokenize("workbook spreadsheet cells export data")
        sim = _sc_cosine(tokens, tokens)
        assert abs(sim - 1.0) < 1e-9

    def test_sc_cosine_orthogonal(self):
        a = _sc_tokenize("workbook spreadsheet cells export")
        b = _sc_tokenize("raspberry banana strawberry grape")
        sim = _sc_cosine(a, b)
        assert sim < 0.1

    def test_sc_cosine_empty(self):
        assert _sc_cosine([], ["hello"]) == 0.0
        assert _sc_cosine(["hello"], []) == 0.0


class TestSemanticConfirmCaseA:
    """Case A: unrelated + high score → check TF-IDF similarity."""

    def test_unrelated_high_score_similar_content_promoted(self):
        """unrelated + score 0.82 + high cosine → reclassified, promoted."""
        escalated = [{
            "source_key": "docs/cells/java/workbook-export.md",
            "target_path": "ref/cells/java/Workbook",
            "ai_label": "unrelated",
            "effective_score": 0.82,
            "adjudication_result": "ESCALATE_TO_OPERATOR",
        }]
        # Same topic text: nearly identical (high token overlap → cosine > 0.80)
        source_texts = {
            "docs/cells/java/workbook-export.md": (
                "workbook class export spreadsheet data xlsx csv file format "
                "output save method cells worksheets"
            ),
            "ref/cells/java/Workbook": (
                "workbook class export spreadsheet data xlsx csv file format "
                "output save method cells"
            ),
        }
        results = _tier2_semantic_confirm(escalated, source_texts)
        assert results[0]["adjudication_result"] == "PROMOTE_WITH_JUSTIFICATION"
        assert results[0].get("semantic_override") is True
        assert "semantic_similarity" in results[0]

    def test_unrelated_high_score_different_content_stays_escalated(self):
        """unrelated + score 0.82 + low cosine → still ESCALATE_TO_OPERATOR."""
        escalated = [{
            "source_key": "docs/cells/java/workbook-export.md",
            "target_path": "ref/email/net/SmtpClient",
            "ai_label": "unrelated",
            "effective_score": 0.82,
            "adjudication_result": "ESCALATE_TO_OPERATOR",
        }]
        source_texts = {
            "docs/cells/java/workbook-export.md": (
                "The Workbook class provides methods to export spreadsheet data "
                "to various file formats including XLSX and CSV"
            ),
            "ref/email/net/SmtpClient": (
                "SmtpClient manages SMTP email connections for sending messages "
                "through mail servers with authentication"
            ),
        }
        results = _tier2_semantic_confirm(escalated, source_texts)
        assert results[0]["adjudication_result"] == "ESCALATE_TO_OPERATOR"

    def test_unrelated_high_score_no_target_text_stays_escalated(self):
        """unrelated + high score but no target text → stays ESCALATE."""
        escalated = [{
            "source_key": "docs/cells/java/sk1.md",
            "target_path": "ref/cells/java/X",
            "ai_label": "unrelated",
            "effective_score": 0.85,
            "adjudication_result": "ESCALATE_TO_OPERATOR",
        }]
        results = _tier2_semantic_confirm(escalated, {})
        assert results[0]["adjudication_result"] == "ESCALATE_TO_OPERATOR"


class TestSemanticConfirmCaseB:
    """Case B: exact/related API class + low score → check anchor validity."""

    def test_exact_api_low_score_valid_anchor_promoted(self):
        """exact_api_class + score 0.66 + valid anchor → promoted at 0.65 threshold."""
        escalated = [{
            "source_key": "docs/pdf/go/document.md",
            "target_path": "ref/pdf/go/Document",
            "ai_label": "exact_api_class",
            "effective_score": 0.66,
            "adjudication_result": "ESCALATE_TO_OPERATOR",
        }]
        anchor_valid = {"docs/pdf/go/document.md": True}
        results = _tier2_semantic_confirm(escalated, {}, anchor_valid=anchor_valid)
        assert results[0]["adjudication_result"] == "PROMOTE_WITH_JUSTIFICATION"
        assert results[0].get("semantic_override") is True

    def test_exact_api_low_score_invalid_anchor_stays_escalated(self):
        """exact_api_class + score 0.66 + invalid anchor → stays ESCALATE."""
        escalated = [{
            "source_key": "docs/pdf/go/document.md",
            "target_path": "ref/pdf/go/Document",
            "ai_label": "exact_api_class",
            "effective_score": 0.66,
            "adjudication_result": "ESCALATE_TO_OPERATOR",
        }]
        anchor_valid = {"docs/pdf/go/document.md": False}
        results = _tier2_semantic_confirm(escalated, {}, anchor_valid=anchor_valid)
        assert results[0]["adjudication_result"] == "ESCALATE_TO_OPERATOR"

    def test_exact_api_very_low_score_not_promoted(self):
        """exact_api_class + score 0.50 (below 0.65) + valid anchor → NOT promoted."""
        escalated = [{
            "source_key": "docs/pdf/go/document.md",
            "target_path": "ref/pdf/go/Document",
            "ai_label": "exact_api_class",
            "effective_score": 0.50,
            "adjudication_result": "ESCALATE_TO_OPERATOR",
        }]
        anchor_valid = {"docs/pdf/go/document.md": True}
        results = _tier2_semantic_confirm(escalated, {}, anchor_valid=anchor_valid)
        assert results[0]["adjudication_result"] == "ESCALATE_TO_OPERATOR"

    def test_related_api_low_score_valid_anchor_promoted(self):
        """related_api_class + score 0.67 + valid anchor → promoted."""
        escalated = [{
            "source_key": "docs/cells/net/range.md",
            "target_path": "ref/cells/net/Range",
            "ai_label": "related_api_class",
            "effective_score": 0.67,
            "adjudication_result": "ESCALATE_TO_OPERATOR",
        }]
        anchor_valid = {"docs/cells/net/range.md": True}
        results = _tier2_semantic_confirm(escalated, {}, anchor_valid=anchor_valid)
        assert results[0]["adjudication_result"] == "PROMOTE_WITH_JUSTIFICATION"


class TestSemanticConfirmIntegration:
    def test_semantic_confirm_flag_in_adjudicate(self):
        """semantic_confirm=True activates the confirmation layer."""
        candidates = [_make_candidate("docs/cells/java/sk1.md", "ref/cells/java/Workbook", 0.65)]
        sources = [{"source_key": "docs/cells/java/sk1.md", "source_path": "docs/cells/java/sk1.md"}]
        graph = _make_graph(sources, candidates)
        result = adjudicate_review_required(
            graph, None, dry_run=True, semantic_confirm=True,
        )
        assert "semantic_promoted" in result["tier_stats"]

    def test_semantic_confirm_off_by_default(self):
        """semantic_confirm defaults to False."""
        candidates = [_make_candidate("docs/cells/java/sk1.md", "ref/cells/java/Workbook", 0.65)]
        sources = [{"source_key": "docs/cells/java/sk1.md", "source_path": "docs/cells/java/sk1.md"}]
        graph = _make_graph(sources, candidates)
        result = adjudicate_review_required(graph, None, dry_run=True)
        # semantic_promoted should be 0 when disabled
        assert result["tier_stats"]["semantic_promoted"] == 0


class TestLoadPageTexts:
    """Tests for _load_page_texts() — path resolution correctness."""

    def test_source_path_cwd_independent(self, tmp_path):
        """Source paths resolve correctly regardless of CWD (uses repo_root join)."""
        # Create a fake source file at tmp_path/content/docs/cells/java/sk1.md
        content_dir = tmp_path / "content"
        src_dir = content_dir / "docs" / "cells" / "java"
        src_dir.mkdir(parents=True)
        src_file = src_dir / "sk1.md"
        src_file.write_text("source page text", encoding="utf-8")

        graph = {
            "sources": [
                {
                    "source_key": "docs/cells/java/sk1",
                    "source_path": "content/docs/cells/java/sk1.md",
                }
            ],
            "candidates": [],
        }
        texts = _load_page_texts(graph, content_dir)
        assert "docs/cells/java/sk1" in texts
        assert texts["docs/cells/java/sk1"] == "source page text"

    def test_target_exact_case_match(self, tmp_path):
        """Target slugs matching exact-case filenames resolve correctly."""
        content_dir = tmp_path / "content"
        ref_dir = content_dir / "reference.aspose.org" / "en" / "3d" / "net"
        ref_dir.mkdir(parents=True)
        (ref_dir / "scene.md").write_text("scene page text", encoding="utf-8")

        graph = {
            "sources": [],
            "candidates": [
                {"target_path": "reference/3d/net/scene", "score": 0.9},
            ],
        }
        texts = _load_page_texts(graph, content_dir)
        assert "reference/3d/net/scene" in texts
        assert texts["reference/3d/net/scene"] == "scene page text"

    def test_target_case_insensitive_pascalcase(self, tmp_path):
        """Target slug 'a3dobject' resolves to PascalCase file 'A3DObject.md'."""
        content_dir = tmp_path / "content"
        ref_dir = content_dir / "reference.aspose.org" / "en" / "3d" / "net"
        ref_dir.mkdir(parents=True)
        (ref_dir / "A3DObject.md").write_text("A3DObject page text", encoding="utf-8")

        graph = {
            "sources": [],
            "candidates": [
                {"target_path": "reference/3d/net/a3dobject", "score": 0.9},
            ],
        }
        texts = _load_page_texts(graph, content_dir)
        assert "reference/3d/net/a3dobject" in texts
        assert texts["reference/3d/net/a3dobject"] == "A3DObject page text"

    def test_target_namespace_stripping_java(self, tmp_path):
        """Java namespace prefix in target_path is stripped for reference targets.

        Candidate graphs use paths like 'reference/pdf/java/com.aspose.pdf/annotation'
        but content files are flat: reference.aspose.org/en/pdf/java/Annotation.md.
        """
        content_dir = tmp_path / "content"
        ref_dir = content_dir / "reference.aspose.org" / "en" / "pdf" / "java"
        ref_dir.mkdir(parents=True)
        (ref_dir / "Annotation.md").write_text("annotation page text", encoding="utf-8")

        graph = {
            "sources": [],
            "candidates": [
                {"target_path": "reference/pdf/java/com.aspose.pdf/annotation", "score": 0.9},
            ],
        }
        texts = _load_page_texts(graph, content_dir)
        assert "reference/pdf/java/com.aspose.pdf/annotation" in texts
        assert texts["reference/pdf/java/com.aspose.pdf/annotation"] == "annotation page text"

    def test_target_namespace_stripping_csharp(self, tmp_path):
        """C# namespace prefix (e.g. 'aspose.cells') is stripped for reference targets."""
        content_dir = tmp_path / "content"
        ref_dir = content_dir / "reference.aspose.org" / "en" / "cells" / "net"
        ref_dir.mkdir(parents=True)
        (ref_dir / "Workbook.md").write_text("workbook page text", encoding="utf-8")

        graph = {
            "sources": [],
            "candidates": [
                {"target_path": "reference/cells/net/aspose.cells/workbook", "score": 0.9},
            ],
        }
        texts = _load_page_texts(graph, content_dir)
        assert "reference/cells/net/aspose.cells/workbook" in texts
        assert texts["reference/cells/net/aspose.cells/workbook"] == "workbook page text"

    def test_target_non_reference_no_namespace_stripping(self, tmp_path):
        """Non-reference targets (docs, kb) should NOT strip segments with dots."""
        content_dir = tmp_path / "content"
        kb_dir = content_dir / "kb.aspose.org" / "en" / "pdf" / "java"
        kb_dir.mkdir(parents=True)
        (kb_dir / "convert-pdf.md").write_text("kb text", encoding="utf-8")

        graph = {
            "sources": [],
            "candidates": [
                {"target_path": "kb/pdf/java/convert-pdf", "score": 0.9},
            ],
        }
        texts = _load_page_texts(graph, content_dir)
        assert "kb/pdf/java/convert-pdf" in texts

    def test_missing_source_skipped_gracefully(self, tmp_path):
        """Missing source files are silently skipped (no exception)."""
        content_dir = tmp_path / "content"
        content_dir.mkdir(parents=True)
        graph = {
            "sources": [
                {"source_key": "sk1", "source_path": "content/nonexistent.md"}
            ],
            "candidates": [],
        }
        texts = _load_page_texts(graph, content_dir)
        assert "sk1" not in texts

    def test_diagnostic_output_printed(self, tmp_path, capsys):
        """Diagnostic line showing load counts is printed to stdout."""
        content_dir = tmp_path / "content"
        content_dir.mkdir(parents=True)
        graph = {"sources": [], "candidates": []}
        _load_page_texts(graph, content_dir)
        out = capsys.readouterr().out
        assert "[page_texts]" in out


# ── TC-TUNE-TEST-001: Synthetic ESCALATE Injection Tests ─────────────────────


class TestSemanticConfirmThresholds:
    """Threshold boundary tests for _tier2_semantic_confirm() Case A and Case B."""

    def test_case_a_high_similarity_promotes(self):
        """Case A: unrelated + score 0.83 + high TF-IDF cosine -> PROMOTE."""
        # Nearly identical texts -> cosine well above 0.80
        base = (
            "workbook class spreadsheet export data xlsx csv file format "
            "output save method cells worksheets range pivot table chart "
            "formula calculation style conditional"
        )
        escalated = [{
            "source_key": "docs/cells/java/workbook.md",
            "target_path": "ref/cells/java/Workbook",
            "ai_label": "unrelated",
            "effective_score": 0.83,
            "adjudication_result": "ESCALATE_TO_OPERATOR",
        }]
        source_texts = {
            "docs/cells/java/workbook.md": base,
            "ref/cells/java/Workbook": base,
        }
        results = _tier2_semantic_confirm(escalated, source_texts)
        r = results[0]
        assert r["adjudication_result"] == "PROMOTE_WITH_JUSTIFICATION"
        assert r["semantic_override"] is True
        assert r["semantic_similarity"] >= 0.80

    def test_case_a_low_similarity_stays_escalated(self):
        """Case A: unrelated + score 0.83 + low TF-IDF cosine -> stays ESCALATE."""
        escalated = [{
            "source_key": "docs/cells/java/workbook.md",
            "target_path": "ref/email/net/SmtpClient",
            "ai_label": "unrelated",
            "effective_score": 0.83,
            "adjudication_result": "ESCALATE_TO_OPERATOR",
        }]
        source_texts = {
            "docs/cells/java/workbook.md": (
                "workbook class spreadsheet export data xlsx csv file"
            ),
            "ref/email/net/SmtpClient": (
                "smtp client send email message connection authentication server"
            ),
        }
        results = _tier2_semantic_confirm(escalated, source_texts)
        r = results[0]
        assert r["adjudication_result"] == "ESCALATE_TO_OPERATOR"
        assert r["semantic_similarity"] < 0.80

    def test_case_b_valid_anchor_promotes_at_lower_threshold(self):
        """Case B: exact_api_class + score 0.66 + valid anchor -> PROMOTE at 0.65."""
        escalated = [{
            "source_key": "docs/pdf/net/document.md",
            "target_path": "ref/pdf/net/Document",
            "ai_label": "exact_api_class",
            "effective_score": 0.66,
            "adjudication_result": "ESCALATE_TO_OPERATOR",
        }]
        anchor_valid = {"docs/pdf/net/document.md": True}
        results = _tier2_semantic_confirm(escalated, {}, anchor_valid=anchor_valid)
        r = results[0]
        assert r["adjudication_result"] == "PROMOTE_WITH_JUSTIFICATION"
        assert r["semantic_override"] is True

    def test_case_b_no_anchor_stays_escalated(self):
        """Case B: exact_api_class + score 0.66 + no valid anchor -> stays ESCALATE."""
        escalated = [{
            "source_key": "docs/pdf/net/document.md",
            "target_path": "ref/pdf/net/Document",
            "ai_label": "exact_api_class",
            "effective_score": 0.66,
            "adjudication_result": "ESCALATE_TO_OPERATOR",
        }]
        results = _tier2_semantic_confirm(escalated, {})
        r = results[0]
        assert r["adjudication_result"] == "ESCALATE_TO_OPERATOR"

    def test_case_b_below_anchor_threshold_stays_escalated(self):
        """Case B: exact_api_class + score 0.60 (below 0.65) + valid anchor -> stays ESCALATE."""
        escalated = [{
            "source_key": "docs/pdf/net/document.md",
            "target_path": "ref/pdf/net/Document",
            "ai_label": "exact_api_class",
            "effective_score": 0.60,
            "adjudication_result": "ESCALATE_TO_OPERATOR",
        }]
        anchor_valid = {"docs/pdf/net/document.md": True}
        results = _tier2_semantic_confirm(escalated, {}, anchor_valid=anchor_valid)
        r = results[0]
        assert r["adjudication_result"] == "ESCALATE_TO_OPERATOR"

    def test_case_b_related_api_valid_anchor_promotes(self):
        """Case B: related_api_class + score 0.68 + valid anchor -> PROMOTE."""
        escalated = [{
            "source_key": "docs/cells/net/range.md",
            "target_path": "ref/cells/net/Range",
            "ai_label": "related_api_class",
            "effective_score": 0.68,
            "adjudication_result": "ESCALATE_TO_OPERATOR",
        }]
        anchor_valid = {"docs/cells/net/range.md": True}
        results = _tier2_semantic_confirm(escalated, {}, anchor_valid=anchor_valid)
        r = results[0]
        assert r["adjudication_result"] == "PROMOTE_WITH_JUSTIFICATION"
        assert r["semantic_override"] is True


# ── TC-H-001 / TC-H-002: CLI --classify Infrastructure Tests ────────────────

from commands.ops.backlink_adjudicate_review import main as adjudicate_main


class TestClassifyFlag:
    """Tests for --classify CLI flag behavior."""

    def _make_canned_result(self):
        """Return a canned adjudication result dict for mocking."""
        return {
            "total_review_required": 10,
            "tier1_already_approved": 3,
            "tier2_processed": 7,
            "promoted": [
                {"source_key": "sk1", "target_path": "ref/x/Y",
                 "adjudication_result": "PROMOTE_WITH_JUSTIFICATION",
                 "effective_score": 0.75},
            ],
            "escalated": [
                {"source_key": "sk2", "target_path": "ref/x/Z",
                 "adjudication_result": "ESCALATE_TO_OPERATOR",
                 "ai_label": "related_api_class",
                 "effective_score": 0.55},
            ],
            "rejected": [
                {"source_key": f"sk{i}", "target_path": f"ref/x/R{i}",
                 "adjudication_result": "REJECT"}
                for i in range(5)
            ],
            "tier_stats": {
                "tier1_count": 3,
                "tier2_promoted": 1,
                "tier2_escalated": 1,
                "tier2_rejected": 5,
                "semantic_promoted": 0,
            },
            "generated_at": "2026-06-13T00:00:00+00:00",
        }

    def test_classify_and_write_mutually_exclusive(self):
        """--write and --classify together should exit with error."""
        with pytest.raises(SystemExit):
            with patch(
                "sys.argv",
                ["prog", "--write", "--classify",
                 "--candidate-graph", "dummy.json",
                 "--authority", "dummy.json"],
            ):
                adjudicate_main()

    def test_classify_and_dry_run_mutually_exclusive(self):
        """--classify and --dry-run together should exit with error."""
        with pytest.raises(SystemExit):
            with patch(
                "sys.argv",
                ["prog", "--classify", "--dry-run",
                 "--candidate-graph", "dummy.json",
                 "--authority", "dummy.json"],
            ):
                adjudicate_main()

    def test_classify_flag_enables_ai_without_write(self, tmp_path):
        """--classify sets dry_run=False, produces report, does NOT touch authority."""
        # Create minimal candidate graph and authority files
        graph = _make_graph(
            sources=[_make_source("sk1", "docs/cells/java/page1.md")],
            candidates=[_make_candidate("sk1", "ref/cells/java/X", 0.55)],
        )
        authority = _make_authority({})
        graph_path = tmp_path / "graph.json"
        graph_path.write_text(json.dumps(graph), encoding="utf-8")
        auth_path = tmp_path / "auth.json"
        auth_path.write_text(json.dumps(authority), encoding="utf-8")
        out_dir = tmp_path / "output"

        canned = self._make_canned_result()

        with patch("sys.argv", [
            "prog", "--classify",
            "--candidate-graph", str(graph_path),
            "--authority", str(auth_path),
            "--output-dir", str(out_dir),
        ]):
            with patch(
                "commands.ops.backlink_adjudicate_review.adjudicate_review_required",
                return_value=canned,
            ) as mock_adj:
                adjudicate_main()

        # Verify AI was enabled (dry_run=False)
        call_kwargs = mock_adj.call_args[1]
        assert call_kwargs["dry_run"] is False

        # Verify authority was NOT modified
        auth_after = json.loads(auth_path.read_text(encoding="utf-8"))
        assert auth_after == authority

        # Verify report was written
        assert (out_dir / "tier2_results.md").exists()

    def test_report_json_output(self, tmp_path):
        """--classify produces JSON report with expected keys."""
        graph = _make_graph(
            sources=[_make_source("sk1", "docs/cells/java/page1.md")],
            candidates=[_make_candidate("sk1", "ref/cells/java/X", 0.55)],
        )
        authority = _make_authority({})
        graph_path = tmp_path / "graph.json"
        graph_path.write_text(json.dumps(graph), encoding="utf-8")
        auth_path = tmp_path / "auth.json"
        auth_path.write_text(json.dumps(authority), encoding="utf-8")
        out_dir = tmp_path / "output"

        canned = self._make_canned_result()

        with patch("sys.argv", [
            "prog", "--classify",
            "--candidate-graph", str(graph_path),
            "--authority", str(auth_path),
            "--output-dir", str(out_dir),
        ]):
            with patch(
                "commands.ops.backlink_adjudicate_review.adjudicate_review_required",
                return_value=canned,
            ):
                adjudicate_main()

        json_path = out_dir / "tier2_results.json"
        assert json_path.exists()
        data = json.loads(json_path.read_text(encoding="utf-8"))
        assert "generated_at" in data
        assert "total_review_required" in data
        assert "tier_stats" in data
        assert "promoted" in data
        assert "escalated" in data
        assert "rejected_sample" in data
        assert len(data["escalated"]) == 1
        assert data["escalated"][0]["ai_label"] == "related_api_class"


# ── TC-H-003: effective_score in write path ──────────────────────────────────


class TestEffectiveScoreInWritePath:
    """Verify effective_score in result dict doesn't break authority write path."""

    def test_promote_to_authority_with_effective_score(self):
        """promote_to_authority handles result dicts containing effective_score."""
        promoted = [{
            "source_key": "sk1",
            "target_path": "reference/cells/java/Workbook",
            "adjudication_result": "PROMOTE_WITH_JUSTIFICATION",
            "effective_score": 0.75,
            "final_score": 0.75,
        }]
        graph = _make_graph(
            sources=[_make_source("sk1", "docs/cells/java/page1.md")],
            candidates=[_make_candidate("sk1", "reference/cells/java/Workbook", 0.75)],
        )
        authority = _make_authority({})

        result = promote_to_authority(
            promoted, graph, authority,
            anchor_registry=None,
            families_map=None,
            platforms_map=None,
        )
        assert result["promoted_count"] >= 0
        assert not result["errors"]
