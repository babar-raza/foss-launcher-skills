"""Tests for claim-level stale detection delta (TC-STALE-001).

Verifies that --claim-delta mode only marks pages stale when their
cited claims were actually removed from the current knowledge model.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pytest
import yaml

PIPELINE_DIR = Path(__file__).resolve().parents[1]
if str(PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINE_DIR))

from stale_detect import scan_product, main


def _setup(tmp_path: Path, repo_sha: str, claims: list[dict], page_sha: str, page_claims: list[str]):
    """Create minimal knowledge + content for testing."""
    merged = tmp_path / "knowledge" / "fake" / "python" / "merged"
    merged.mkdir(parents=True)
    (merged / "api_surface.json").write_text("[]", encoding="utf-8")
    (merged / "claims.json").write_text(json.dumps(claims), encoding="utf-8")
    (merged / "model.yaml").write_text(
        yaml.safe_dump({"repo_sha": repo_sha, "version": "1.0"}),
        encoding="utf-8",
    )

    page = tmp_path / "content" / "docs.aspose.org" / "en" / "fake" / "python" / "page.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    claims_yaml = "[" + ", ".join(page_claims) + "]" if page_claims else "[]"
    page.write_text(
        f"---\ntitle: Test\nevidence:\n  model_sha: {page_sha}\n  claims: {claims_yaml}\n---\n\nBody.\n",
        encoding="utf-8",
    )


class TestClaimDeltaMode:
    def test_sha_changed_no_claims_removed_not_stale(self, tmp_path):
        """SHA changed but all cited claims still present → not stale."""
        _setup(
            tmp_path,
            repo_sha="new_sha_123",
            claims=[{"claim_id": "CLM-1", "text": "Foo"}, {"claim_id": "CLM-2", "text": "Bar"}],
            page_sha="old_sha_999",
            page_claims=["CLM-1", "CLM-2"],
        )
        report = scan_product(
            "fake", "python",
            content_root=tmp_path / "content",
            knowledge_root=tmp_path / "knowledge",
            claim_delta=True,
        )
        # Page should NOT be counted as stale (actionable)
        assert report["stale_pages"] == 0
        # But should still appear in pages list with info-level issue
        assert len(report["pages"]) == 1
        assert "stale_model_sha_no_impact" in report["pages"][0]["issues"]
        assert report["claim_delta_skipped"] == 1

    def test_sha_changed_cited_claim_removed_is_stale(self, tmp_path):
        """SHA changed and a cited claim was removed → stale."""
        _setup(
            tmp_path,
            repo_sha="new_sha_123",
            claims=[{"claim_id": "CLM-1", "text": "Foo"}],  # CLM-2 removed
            page_sha="old_sha_999",
            page_claims=["CLM-1", "CLM-2"],
        )
        report = scan_product(
            "fake", "python",
            content_root=tmp_path / "content",
            knowledge_root=tmp_path / "knowledge",
            claim_delta=True,
        )
        assert report["stale_pages"] == 1
        assert "stale_model_sha" in report["pages"][0]["issues"]
        assert "orphaned_claims" in report["pages"][0]["issues"]
        assert "CLM-2" in report["pages"][0]["orphaned_claims"]

    def test_sha_matches_no_stale(self, tmp_path):
        """SHA matches → not stale regardless of claim_delta flag."""
        _setup(
            tmp_path,
            repo_sha="same_sha",
            claims=[{"claim_id": "CLM-1", "text": "Foo"}],
            page_sha="same_sha",
            page_claims=["CLM-1"],
        )
        report = scan_product(
            "fake", "python",
            content_root=tmp_path / "content",
            knowledge_root=tmp_path / "knowledge",
            claim_delta=True,
        )
        assert report["stale_pages"] == 0
        assert len(report["pages"]) == 0

    def test_flag_off_preserves_existing_behavior(self, tmp_path):
        """Without claim_delta, SHA mismatch → stale even if all claims present."""
        _setup(
            tmp_path,
            repo_sha="new_sha_123",
            claims=[{"claim_id": "CLM-1", "text": "Foo"}],
            page_sha="old_sha_999",
            page_claims=["CLM-1"],
        )
        report = scan_product(
            "fake", "python",
            content_root=tmp_path / "content",
            knowledge_root=tmp_path / "knowledge",
            claim_delta=False,
        )
        assert report["stale_pages"] == 1
        assert "stale_model_sha" in report["pages"][0]["issues"]
        assert "claim_delta_skipped" not in report

    def test_no_claims_on_page_still_stale(self, tmp_path):
        """Page with no cited claims + SHA mismatch → stale even in claim_delta mode."""
        _setup(
            tmp_path,
            repo_sha="new_sha_123",
            claims=[{"claim_id": "CLM-1", "text": "Foo"}],
            page_sha="old_sha_999",
            page_claims=[],
        )
        report = scan_product(
            "fake", "python",
            content_root=tmp_path / "content",
            knowledge_root=tmp_path / "knowledge",
            claim_delta=True,
        )
        # Empty claims list → not eligible for claim_delta skip
        assert report["stale_pages"] == 1
        assert "stale_model_sha" in report["pages"][0]["issues"]

    def test_missing_evidence_still_detected(self, tmp_path):
        """Missing evidence block is always detected regardless of claim_delta."""
        merged = tmp_path / "knowledge" / "fake" / "python" / "merged"
        merged.mkdir(parents=True)
        (merged / "api_surface.json").write_text("[]", encoding="utf-8")
        (merged / "claims.json").write_text("[]", encoding="utf-8")
        (merged / "model.yaml").write_text(
            yaml.safe_dump({"repo_sha": "abc", "version": "1.0"}), encoding="utf-8"
        )
        page = tmp_path / "content" / "docs.aspose.org" / "en" / "fake" / "python" / "page.md"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text("---\ntitle: Test\n---\n\nBody.\n", encoding="utf-8")

        report = scan_product(
            "fake", "python",
            content_root=tmp_path / "content",
            knowledge_root=tmp_path / "knowledge",
            claim_delta=True,
        )
        assert report["stale_pages"] == 1
        assert "missing_evidence" in report["pages"][0]["issues"]

    def test_claim_delta_skipped_count(self, tmp_path):
        """claim_delta_skipped counts pages where SHA differs but no impact."""
        _setup(
            tmp_path,
            repo_sha="new_sha",
            claims=[{"claim_id": "CLM-1", "text": "Foo"}, {"claim_id": "CLM-2", "text": "Bar"}],
            page_sha="old_sha",
            page_claims=["CLM-1"],
        )
        report = scan_product(
            "fake", "python",
            content_root=tmp_path / "content",
            knowledge_root=tmp_path / "knowledge",
            claim_delta=True,
        )
        assert report["claim_delta_skipped"] == 1
        assert report["stale_pages"] == 0


class TestClaimDeltaCLI:
    def test_cli_flag_accepted(self, tmp_path):
        """--claim-delta flag is parsed without error."""
        _setup(
            tmp_path,
            repo_sha="sha1",
            claims=[{"claim_id": "CLM-1", "text": "Foo"}],
            page_sha="sha1",
            page_claims=["CLM-1"],
        )
        exit_code = main([
            "fake", "python",
            "--content-root", str(tmp_path / "content"),
            "--knowledge-root", str(tmp_path / "knowledge"),
            "--claim-delta", "--json",
        ])
        assert exit_code == 0

    def test_cli_without_flag_works(self, tmp_path):
        """Without --claim-delta, CLI works as before."""
        _setup(
            tmp_path,
            repo_sha="sha1",
            claims=[{"claim_id": "CLM-1", "text": "Foo"}],
            page_sha="sha1",
            page_claims=["CLM-1"],
        )
        exit_code = main([
            "fake", "python",
            "--content-root", str(tmp_path / "content"),
            "--knowledge-root", str(tmp_path / "knowledge"),
            "--json",
        ])
        assert exit_code == 0
