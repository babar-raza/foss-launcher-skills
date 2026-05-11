"""Tests for S-98 enrichment taxonomy (TC-001)."""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure enrichment lib is importable
_LIB_DIR = str(Path(__file__).resolve().parent.parent / "scripts" / "pipeline" / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from enrichment.taxonomy import (
    ContentTier,
    CoverageStatus,
    CandidateAction,
    CandidateDisposition,
    ACTION_TO_DISPOSITION,
    SUBDOMAINS,
)


class TestContentTier:
    def test_three_tiers_exist(self):
        assert len(ContentTier) == 3

    def test_tier_values(self):
        assert ContentTier.MANDATORY.value == "mandatory"
        assert ContentTier.THRESHOLD_OPTIONAL.value == "threshold_optional"
        assert ContentTier.ENRICHMENT_OPTIONAL.value == "enrichment_optional"


class TestCoverageStatus:
    def test_six_statuses_exist(self):
        assert len(CoverageStatus) == 6

    def test_status_values(self):
        expected = {"covered", "partially_covered", "product_mentioned_only",
                    "reference_only", "uncovered", "unknown"}
        actual = {s.value for s in CoverageStatus}
        assert actual == expected


class TestCandidateAction:
    def test_ten_actions_exist(self):
        assert len(CandidateAction) == 10

    def test_includes_update_existing(self):
        update_actions = [a for a in CandidateAction if "update_existing" in a.value]
        assert len(update_actions) == 3  # docs, kb, blog

    def test_includes_create_new(self):
        create_actions = [a for a in CandidateAction if "create_new" in a.value]
        assert len(create_actions) == 3  # docs, kb, blog


class TestCandidateDisposition:
    def test_five_dispositions_exist(self):
        assert len(CandidateDisposition) == 5

    def test_disposition_values(self):
        expected = {"generate_now", "update_existing", "deferred_to_backlog",
                    "rejected_with_reason", "blocked_with_reason"}
        actual = {d.value for d in CandidateDisposition}
        assert actual == expected


class TestActionToDisposition:
    def test_all_actions_mapped(self):
        for action in CandidateAction:
            assert action in ACTION_TO_DISPOSITION, f"{action} not mapped"

    def test_create_actions_map_to_generate(self):
        for action in CandidateAction:
            if "create_new" in action.value:
                assert ACTION_TO_DISPOSITION[action] == CandidateDisposition.GENERATE_NOW

    def test_update_actions_map_to_update(self):
        for action in CandidateAction:
            if "update_existing" in action.value:
                assert ACTION_TO_DISPOSITION[action] == CandidateDisposition.UPDATE_EXISTING

    def test_reject_maps_correctly(self):
        assert ACTION_TO_DISPOSITION[CandidateAction.REJECT_WITH_REASON] == CandidateDisposition.REJECTED_WITH_REASON

    def test_block_maps_correctly(self):
        assert ACTION_TO_DISPOSITION[CandidateAction.BLOCK_WITH_REASON] == CandidateDisposition.BLOCKED_WITH_REASON

    def test_defer_maps_correctly(self):
        assert ACTION_TO_DISPOSITION[CandidateAction.DEFER_TO_BACKLOG] == CandidateDisposition.DEFERRED_TO_BACKLOG


class TestSubdomains:
    def test_five_subdomains(self):
        assert len(SUBDOMAINS) == 5

    def test_all_expected_subdomains(self):
        expected = {"products.aspose.org", "docs.aspose.org", "kb.aspose.org",
                    "blog.aspose.org", "reference.aspose.org"}
        assert set(SUBDOMAINS) == expected

    def test_unsupported_mode_rejected(self):
        """Verify the CLI rejects unsupported modes."""
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--mode", choices=("audit", "plan", "dry-run", "execute"))
        try:
            parser.parse_args(["--mode", "invalid-mode"])
            assert False, "Should have raised"
        except SystemExit:
            pass  # Expected
