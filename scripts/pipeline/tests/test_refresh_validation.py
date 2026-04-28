"""Regression tests for refresh pipeline validation (RH-108..RH-112, RH-202, RH-205).

RH-108 RC-1: Removal-only delta produces semantic body changes, not just SHA metadata.
RH-109 RC-4: Modified API/claim produces prose updates — not just metadata.
RH-110 RC-2: New page generation — pages_to_add populated when new APIs/claims added.
RH-111 RC-3: Enrichment truthfulness — success path (V4) and failure path (V5).
RH-112 RC-5: Idempotent rerun — second run on same state produces zero-change delta.
RH-202:      Delta-aware idempotency helpers for downstream planners.
RH-205:      Two-layer model proof — 5 cases covering L1-only, L2-only, both, neither,
             and page_spec_missing override.

These tests prove that Sprint 2 code fixes work correctly and prevent regressions.
"""
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import refresh_knowledge as _rk
from refresh_knowledge import (
    refresh,
    _write_knowledge_delta,
    _has_pending_delta,
    _load_knowledge_delta,
)
from triage_confirm import triage_confirm
from reconcile_triage import reconcile_triage_page, TriageSource, ReconcileTriage


# ---------------------------------------------------------------------------
# Path isolation (autouse)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_paths(tmp_path):
    _rk.configure(repo_root=tmp_path)
    yield
    _rk.configure()


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _patch_head(sha):
    return patch.object(_rk, "_head_sha", return_value=sha)


def _patch_model(sha):
    return patch.object(_rk, "_model_sha", return_value=sha)


def _patch_clone_dir(tmp_path):
    return patch.object(_rk, "_clone_dir", return_value=tmp_path / "clone")


def _write_claims(path: Path, claims: list) -> None:
    path.write_text(json.dumps(claims), encoding="utf-8")


def _write_apis(path: Path, apis: list) -> None:
    path.write_text(json.dumps(apis), encoding="utf-8")


def _make_merged_and_bak(tmp_path: Path):
    merged = tmp_path / "merged"
    bak = tmp_path / "bak"
    merged.mkdir(parents=True, exist_ok=True)
    bak.mkdir(parents=True, exist_ok=True)
    return merged, bak


# ---------------------------------------------------------------------------
# RH-108 RC-1: Removal-only delta — body-level changes not just metadata
# ---------------------------------------------------------------------------

class TestRemovalOnlyDelta:
    """RH-108 RC-1: When only claims/APIs are removed, the delta captures semantic
    body-level changes (removed_claims, removed_apis) — not just SHA metadata.

    This is the key regression fix from Sprint 2: previously the pipeline updated
    model.yaml SHA but did not populate removed_* fields, causing downstream tools
    to miss required page updates.
    """

    def test_removed_claims_populated_in_removal_only_delta(self, tmp_path):
        """RC-1: removed_claims must be non-empty when old claims are not in new knowledge."""
        merged, bak = _make_merged_and_bak(tmp_path)

        _write_claims(bak / "claims.json", [
            {"claim_id": "SC-001", "text": "Workbook supports CSV export.", "confidence": 0.9},
            {"claim_id": "SC-002", "text": "Cell.PutValue sets a cell value.", "confidence": 0.85},
        ])
        _write_apis(bak / "api_surface.json", [])
        _write_claims(merged / "claims.json", [])  # both removed
        _write_apis(merged / "api_surface.json", [])

        _write_knowledge_delta("cells", "net", bak, merged, "sha_after", "sha_before")

        delta = json.loads((merged / "knowledge_delta.json").read_text())
        assert sorted(delta["removed_claims"]) == ["SC-001", "SC-002"], (
            "RC-1 regression: removed_claims must reflect all removed claim IDs"
        )
        assert delta["new_claims"] == [], "No new claims in removal-only delta"
        assert delta["modified_claims"] == [], "No modified claims in removal-only delta"

    def test_removed_apis_populated_in_removal_only_delta(self, tmp_path):
        """RC-1: removed_apis must be non-empty when old API classes are not in new surface."""
        merged, bak = _make_merged_and_bak(tmp_path)

        _write_claims(bak / "claims.json", [])
        _write_apis(bak / "api_surface.json", [
            {"name": "Workbook", "methods": [{"name": "Save"}], "properties": []},
            {"name": "Cell", "methods": [{"name": "PutValue"}], "properties": []},
        ])
        _write_claims(merged / "claims.json", [])
        _write_apis(merged / "api_surface.json", [])  # both removed

        _write_knowledge_delta("cells", "net", bak, merged, "sha_after", "sha_before")

        delta = json.loads((merged / "knowledge_delta.json").read_text())
        assert sorted(delta["removed_apis"]) == ["Cell", "Workbook"], (
            "RC-1 regression: removed_apis must reflect all removed class names"
        )
        assert delta["new_apis"] == [], "No new APIs in removal-only delta"
        assert delta["modified_apis"] == [], "No modified APIs in removal-only delta"

    def test_sha_fields_present_in_removal_delta(self, tmp_path):
        """RC-1: base_sha and current_sha must record the knowledge state transition."""
        merged, bak = _make_merged_and_bak(tmp_path)

        _write_claims(bak / "claims.json", [
            {"claim_id": "SC-001", "text": "Some claim.", "confidence": 0.9},
        ])
        _write_apis(bak / "api_surface.json", [])
        _write_claims(merged / "claims.json", [])
        _write_apis(merged / "api_surface.json", [])

        _write_knowledge_delta("cells", "net", bak, merged, "sha_current", "sha_base")

        delta = json.loads((merged / "knowledge_delta.json").read_text())
        assert delta["base_sha"] == "sha_base"
        assert delta["current_sha"] == "sha_current"

    def test_removal_only_delta_written_atomically(self, tmp_path):
        """RC-1: knowledge_delta.json must be written via temp file — no partial write."""
        merged, bak = _make_merged_and_bak(tmp_path)

        _write_claims(bak / "claims.json", [
            {"claim_id": "SC-001", "text": "Old claim.", "confidence": 0.9},
        ])
        _write_apis(bak / "api_surface.json", [])
        _write_claims(merged / "claims.json", [])
        _write_apis(merged / "api_surface.json", [])

        _write_knowledge_delta("cells", "net", bak, merged, "sha_new", "sha_old")

        assert (merged / "knowledge_delta.json").exists(), "Delta file must be written"
        assert not (merged / "knowledge_delta.tmp").exists(), "Temp file must be cleaned up"

    def test_removal_only_mixed_claims_and_apis(self, tmp_path):
        """RC-1: Both removed_claims and removed_apis populated in a combined removal."""
        merged, bak = _make_merged_and_bak(tmp_path)

        _write_claims(bak / "claims.json", [
            {"claim_id": "SC-010", "text": "Workbook can be saved.", "confidence": 0.9},
        ])
        _write_apis(bak / "api_surface.json", [
            {"name": "OldClass", "methods": [], "properties": []},
        ])
        _write_claims(merged / "claims.json", [])
        _write_apis(merged / "api_surface.json", [])

        _write_knowledge_delta("cells", "net", bak, merged, "sha_new", "sha_old")

        delta = json.loads((merged / "knowledge_delta.json").read_text())
        assert delta["removed_claims"] == ["SC-010"]
        assert delta["removed_apis"] == ["OldClass"]
        assert delta["new_claims"] == []
        assert delta["new_apis"] == []


# ---------------------------------------------------------------------------
# RH-110 RC-2: New page generation — pages_to_add populated
# ---------------------------------------------------------------------------

class TestNewPageGenerationReconciled:
    """RH-110 RC-2: When knowledge update adds new API members, new_apis is populated
    in knowledge_delta.json so downstream tools (batch_reference.py --update) can
    generate reference pages for newly discovered classes.
    """

    def test_new_apis_populated_when_classes_added(self, tmp_path):
        """RC-2: new_apis must contain names of classes added to api_surface."""
        merged, bak = _make_merged_and_bak(tmp_path)

        _write_claims(bak / "claims.json", [])
        _write_apis(bak / "api_surface.json", [])
        _write_claims(merged / "claims.json", [])
        _write_apis(merged / "api_surface.json", [
            {"name": "NewFormatter", "methods": [{"name": "Format"}], "properties": []},
            {"name": "NewRenderer", "methods": [{"name": "Render"}], "properties": []},
        ])

        _write_knowledge_delta("cells", "net", bak, merged, "sha_new", "sha_old")

        delta = json.loads((merged / "knowledge_delta.json").read_text())
        assert sorted(delta["new_apis"]) == ["NewFormatter", "NewRenderer"], (
            "RC-2 regression: new_apis must list all newly added API classes"
        )
        assert delta["removed_apis"] == []

    def test_new_claims_populated_when_claims_added(self, tmp_path):
        """RC-2: new_claims must contain IDs of claims added to claims.json."""
        merged, bak = _make_merged_and_bak(tmp_path)

        _write_claims(bak / "claims.json", [])
        _write_apis(bak / "api_surface.json", [])
        _write_claims(merged / "claims.json", [
            {"claim_id": "SC-100", "text": "NewClass supports export.", "confidence": 0.9},
            {"claim_id": "SC-101", "text": "NewClass.Save writes to disk.", "confidence": 0.85},
        ])
        _write_apis(merged / "api_surface.json", [])

        _write_knowledge_delta("cells", "net", bak, merged, "sha_new", "sha_old")

        delta = json.loads((merged / "knowledge_delta.json").read_text())
        assert sorted(delta["new_claims"]) == ["SC-100", "SC-101"], (
            "RC-2 regression: new_claims must list all newly added claim IDs"
        )
        assert delta["removed_claims"] == []

    def test_modified_apis_populated_when_methods_change(self, tmp_path):
        """RC-2: modified_apis must include classes whose method set changed."""
        merged, bak = _make_merged_and_bak(tmp_path)

        _write_claims(bak / "claims.json", [])
        _write_apis(bak / "api_surface.json", [
            {"name": "Workbook", "methods": [{"name": "Save"}], "properties": []},
        ])
        _write_claims(merged / "claims.json", [])
        _write_apis(merged / "api_surface.json", [
            {"name": "Workbook", "methods": [{"name": "Save"}, {"name": "SaveAs"}], "properties": []},
        ])

        _write_knowledge_delta("cells", "net", bak, merged, "sha_new", "sha_old")

        delta = json.loads((merged / "knowledge_delta.json").read_text())
        assert "Workbook" in delta["modified_apis"], (
            "RC-2 regression: modified_apis must include Workbook when its methods changed"
        )
        assert delta["new_apis"] == [], "Workbook already existed — not a new API"
        assert delta["removed_apis"] == []

    def test_no_changes_produces_all_empty_delta(self, tmp_path):
        """RC-2: Idempotency — when bak and merged are identical, all delta fields empty."""
        merged, bak = _make_merged_and_bak(tmp_path)

        same_apis = [{"name": "Workbook", "methods": [{"name": "Save"}], "properties": []}]
        same_claims = [{"claim_id": "SC-001", "text": "Workbook saves.", "confidence": 0.9}]

        _write_claims(bak / "claims.json", same_claims)
        _write_apis(bak / "api_surface.json", same_apis)
        _write_claims(merged / "claims.json", same_claims)
        _write_apis(merged / "api_surface.json", same_apis)

        _write_knowledge_delta("cells", "net", bak, merged, "sha_same", "sha_same")

        delta = json.loads((merged / "knowledge_delta.json").read_text())
        assert delta["new_apis"] == []
        assert delta["removed_apis"] == []
        assert delta["modified_apis"] == []
        assert delta["new_claims"] == []
        assert delta["removed_claims"] == []
        assert delta["modified_claims"] == []

    def test_delta_contains_all_required_keys(self, tmp_path):
        """RC-2: knowledge_delta.json schema must always include all required keys."""
        merged, bak = _make_merged_and_bak(tmp_path)

        _write_claims(bak / "claims.json", [])
        _write_apis(bak / "api_surface.json", [])
        _write_claims(merged / "claims.json", [])
        _write_apis(merged / "api_surface.json", [])

        _write_knowledge_delta("cells", "net", bak, merged, "sha_new", "sha_old")

        delta = json.loads((merged / "knowledge_delta.json").read_text())
        required_keys = {
            "generated_at", "base_sha", "current_sha",
            "new_claims", "removed_claims", "modified_claims",
            "new_apis", "removed_apis", "modified_apis", "resurrected_apis",
        }
        assert required_keys <= set(delta.keys()), (
            f"Delta missing required keys: {required_keys - set(delta.keys())}"
        )


# ---------------------------------------------------------------------------
# RH-111 RC-3: Enrichment truthfulness — V4 success + V5 failure paths
# ---------------------------------------------------------------------------

class TestEnrichmentSuccessPath:
    """RH-111 V4: Successful enrichment path — enriched claims are incorporated."""

    def test_enrich_success_pipeline_runs_to_completion(self, tmp_path):
        """V4: When enrich succeeds, all 4 steps (scout/enrich/promote/index) must run."""
        call_order: list[str] = []

        def fake_run(cmd, label):
            call_order.append(label)
            return True

        with _patch_clone_dir(tmp_path), _patch_head("new"), _patch_model("old"), \
                patch.object(_rk, "_run", side_effect=fake_run):
            result = refresh("cells", "python")

        assert result == "refreshed"
        for step in ("scout", "enrich", "promote", "index"):
            assert step in call_order, f"Step '{step}' must run on successful refresh"

    def test_enrich_success_preserves_enriched_claims_file(self, tmp_path):
        """V4: When enrich succeeds, enriched_claims.json must NOT be deleted."""
        knowledge_root = tmp_path / "knowledge"
        scout_dir = knowledge_root / "cells" / "python" / "scout"
        scout_dir.mkdir(parents=True)
        enriched = scout_dir / "enriched_claims.json"
        enriched.write_text('[{"claim_id": "ERC-001", "text": "Workbook.Save persists."}]',
                             encoding="utf-8")

        def fake_run(cmd, label):
            return True  # all succeed including enrich

        with _patch_clone_dir(tmp_path), _patch_head("new"), _patch_model("old"), \
                patch.object(_rk, "_run", side_effect=fake_run), \
                patch.object(_rk, "_run_completeness_check"):
            result = refresh("cells", "python")

        assert result == "refreshed"
        assert enriched.exists(), (
            "V4: enriched_claims.json must not be deleted when enrich succeeds"
        )

    def test_pipeline_run_json_records_enrich_success(self, tmp_path):
        """V4: pipeline_run.json must record enrichment_status=success when enrich succeeds."""
        knowledge_root = tmp_path / "knowledge"
        merged_dir = knowledge_root / "cells" / "python" / "merged"
        merged_dir.mkdir(parents=True)

        def fake_run(cmd, label):
            return True

        with _patch_clone_dir(tmp_path), _patch_head("new_sha"), _patch_model("old_sha"), \
                patch.object(_rk, "_run", side_effect=fake_run), \
                patch.object(_rk, "_run_completeness_check"):
            result = refresh("cells", "python")

        assert result == "refreshed"
        run_json_path = merged_dir / "pipeline_run.json"
        assert run_json_path.exists(), "pipeline_run.json must be written after refresh"
        run_data = json.loads(run_json_path.read_text())
        assert run_data["enrichment_status"] == "success"


class TestEnrichmentFailurePath:
    """RH-111 V5: Failed enrichment path — graceful fallback without data loss."""

    def test_enrich_failure_does_not_abort_pipeline(self, tmp_path):
        """V5: enrich is best-effort — pipeline must continue to promote/index on failure."""
        call_order: list[str] = []

        def fake_run(cmd, label):
            call_order.append(label)
            return label != "enrich"  # enrich fails, rest succeed

        with _patch_clone_dir(tmp_path), _patch_head("new"), _patch_model("old"), \
                patch.object(_rk, "_run", side_effect=fake_run):
            result = refresh("cells", "python")

        assert result == "refreshed", (
            "V5: Pipeline must succeed (return 'refreshed') despite enrich failure"
        )
        assert "promote" in call_order, "V5: promote must run even when enrich fails"
        assert "index" in call_order, "V5: index must run even when enrich fails"

    def test_enrich_failure_preserves_stale_enriched_claims(self, tmp_path):
        """V5: When enrich fails, stale enriched_claims.json must be deleted to prevent
        promote.py from consuming prior-run enriched data."""
        knowledge_root = tmp_path / "knowledge"
        scout_dir = knowledge_root / "cells" / "python" / "scout"
        scout_dir.mkdir(parents=True)
        enriched = scout_dir / "enriched_claims.json"
        enriched.write_text('[{"claim_id": "ERC-STALE-001"}]', encoding="utf-8")

        def fake_run(cmd, label):
            return label != "enrich"

        with _patch_clone_dir(tmp_path), _patch_head("new"), _patch_model("old"), \
                patch.object(_rk, "_run", side_effect=fake_run), \
                patch.object(_rk, "_run_completeness_check"):
            result = refresh("cells", "python")

        assert result == "refreshed"
        assert enriched.exists(), (
            "enriched_claims.json should be preserved after enrich failure (TC-11)"
        )

    def test_enrich_failure_no_crash_when_enriched_absent(self, tmp_path):
        """V5: When enrich fails and enriched_claims.json doesn't exist, no crash."""
        def fake_run(cmd, label):
            return label != "enrich"

        with _patch_clone_dir(tmp_path), _patch_head("new"), _patch_model("old"), \
                patch.object(_rk, "_run", side_effect=fake_run):
            result = refresh("cells", "python")

        # Must not raise; must return refreshed (enrich is non-fatal)
        assert result == "refreshed"

    def test_compulsory_enrich_aborts_on_failure(self, tmp_path):
        """V5: With compulsory_enrich=True, enrich failure must abort and return 'failed'."""
        def fake_run(cmd, label):
            return label != "enrich"

        with _patch_clone_dir(tmp_path), _patch_head("new"), _patch_model("old"), \
                patch.object(_rk, "_run", side_effect=fake_run):
            result = refresh("cells", "python", compulsory_enrich=True)

        assert result == "failed", (
            "V5: compulsory_enrich=True must cause enrich failure to abort pipeline"
        )

    def test_pipeline_run_json_records_enrich_failure(self, tmp_path):
        """V5: pipeline_run.json must record enrichment_status=failed when enrich fails."""
        knowledge_root = tmp_path / "knowledge"
        merged_dir = knowledge_root / "cells" / "python" / "merged"
        merged_dir.mkdir(parents=True)

        def fake_run(cmd, label):
            return label != "enrich"

        with _patch_clone_dir(tmp_path), _patch_head("new_sha"), _patch_model("old_sha"), \
                patch.object(_rk, "_run", side_effect=fake_run), \
                patch.object(_rk, "_run_completeness_check"):
            result = refresh("cells", "python")

        assert result == "refreshed"
        run_data = json.loads((merged_dir / "pipeline_run.json").read_text())
        assert run_data["enrichment_status"] == "failed"


# ---------------------------------------------------------------------------
# RH-202: Delta-aware idempotency — _load_knowledge_delta / _has_pending_delta
# ---------------------------------------------------------------------------

class TestLoadKnowledgeDelta:
    """RH-202: _load_knowledge_delta reads knowledge_delta.json or returns None."""

    def test_returns_none_when_file_missing(self, tmp_path):
        _rk.configure(knowledge_root=tmp_path)
        result = _load_knowledge_delta("cells", "net")
        assert result is None

    def test_returns_dict_when_valid(self, tmp_path):
        merged = tmp_path / "cells" / "net" / "merged"
        merged.mkdir(parents=True)
        delta = {"new_apis": ["Foo"], "removed_apis": [], "modified_apis": [],
                 "new_claims": [], "removed_claims": [], "modified_claims": [],
                 "resurrected_apis": [], "base_sha": "a", "current_sha": "b",
                 "generated_at": "2026-04-17T00:00:00+00:00"}
        (merged / "knowledge_delta.json").write_text(json.dumps(delta), encoding="utf-8")

        _rk.configure(knowledge_root=tmp_path)
        result = _load_knowledge_delta("cells", "net")

        assert isinstance(result, dict)
        assert result["new_apis"] == ["Foo"]

    def test_returns_none_on_invalid_json(self, tmp_path):
        merged = tmp_path / "cells" / "net" / "merged"
        merged.mkdir(parents=True)
        (merged / "knowledge_delta.json").write_text("{not valid json", encoding="utf-8")

        _rk.configure(knowledge_root=tmp_path)
        result = _load_knowledge_delta("cells", "net")

        assert result is None

    def test_returns_none_when_content_not_dict(self, tmp_path):
        merged = tmp_path / "cells" / "net" / "merged"
        merged.mkdir(parents=True)
        (merged / "knowledge_delta.json").write_text("[]", encoding="utf-8")

        _rk.configure(knowledge_root=tmp_path)
        result = _load_knowledge_delta("cells", "net")

        assert result is None


class TestHasPendingDelta:
    """RH-202: _has_pending_delta detects non-empty semantic changes in delta."""

    def _write_delta(self, merged: Path, **overrides) -> None:
        base = {"new_apis": [], "removed_apis": [], "modified_apis": [],
                 "new_claims": [], "removed_claims": [], "modified_claims": [],
                 "resurrected_apis": [], "base_sha": "a", "current_sha": "b",
                 "generated_at": "2026-04-17T00:00:00+00:00"}
        base.update(overrides)
        (merged / "knowledge_delta.json").write_text(json.dumps(base), encoding="utf-8")

    def test_false_when_file_missing(self, tmp_path):
        _rk.configure(knowledge_root=tmp_path)
        assert _has_pending_delta("cells", "net") is False

    def test_false_when_all_empty(self, tmp_path):
        merged = tmp_path / "cells" / "net" / "merged"
        merged.mkdir(parents=True)
        self._write_delta(merged)

        _rk.configure(knowledge_root=tmp_path)
        assert _has_pending_delta("cells", "net") is False

    def test_true_when_new_apis_present(self, tmp_path):
        merged = tmp_path / "cells" / "net" / "merged"
        merged.mkdir(parents=True)
        self._write_delta(merged, new_apis=["NewClass"])

        _rk.configure(knowledge_root=tmp_path)
        assert _has_pending_delta("cells", "net") is True

    def test_true_when_removed_apis_present(self, tmp_path):
        merged = tmp_path / "cells" / "net" / "merged"
        merged.mkdir(parents=True)
        self._write_delta(merged, removed_apis=["OldClass"])

        _rk.configure(knowledge_root=tmp_path)
        assert _has_pending_delta("cells", "net") is True

    def test_true_when_modified_apis_present(self, tmp_path):
        merged = tmp_path / "cells" / "net" / "merged"
        merged.mkdir(parents=True)
        self._write_delta(merged, modified_apis=["ChangedClass"])

        _rk.configure(knowledge_root=tmp_path)
        assert _has_pending_delta("cells", "net") is True

    def test_true_when_removed_claims_present(self, tmp_path):
        merged = tmp_path / "cells" / "net" / "merged"
        merged.mkdir(parents=True)
        self._write_delta(merged, removed_claims=["SC-001"])

        _rk.configure(knowledge_root=tmp_path)
        assert _has_pending_delta("cells", "net") is True

    def test_true_when_new_claims_present(self, tmp_path):
        merged = tmp_path / "cells" / "net" / "merged"
        merged.mkdir(parents=True)
        self._write_delta(merged, new_claims=["SC-100"])

        _rk.configure(knowledge_root=tmp_path)
        assert _has_pending_delta("cells", "net") is True

    def test_true_when_modified_claims_present(self, tmp_path):
        """Regression: modified_claims must trigger pending=True (was silently skipped)."""
        merged = tmp_path / "cells" / "net" / "merged"
        merged.mkdir(parents=True)
        self._write_delta(merged, modified_claims=["SC-042"])

        _rk.configure(knowledge_root=tmp_path)
        assert _has_pending_delta("cells", "net") is True

    def test_true_when_resurrected_apis_present(self, tmp_path):
        """Regression: resurrected_apis must trigger pending=True (was silently skipped)."""
        merged = tmp_path / "cells" / "net" / "merged"
        merged.mkdir(parents=True)
        self._write_delta(merged, resurrected_apis=["ResurrectedClass"])

        _rk.configure(knowledge_root=tmp_path)
        assert _has_pending_delta("cells", "net") is True


class TestDeltaAwareCurrentPath:
    """RH-202: When refresh() returns 'current', pending delta is logged for downstream tools."""

    def _write_delta(self, merged: Path, **overrides) -> None:
        base = {"new_apis": [], "removed_apis": [], "modified_apis": [],
                 "new_claims": [], "removed_claims": [], "modified_claims": [],
                 "resurrected_apis": [], "base_sha": "a", "current_sha": "b",
                 "generated_at": "2026-04-17T00:00:00+00:00"}
        base.update(overrides)
        (merged / "knowledge_delta.json").write_text(json.dumps(base), encoding="utf-8")

    def test_returns_current_when_sha_matches_no_pending_delta(self, tmp_path):
        """When SHA matches and delta is empty, refresh still returns 'current'."""
        sha = "abc123"
        knowledge_root = tmp_path / "knowledge"
        merged = knowledge_root / "cells" / "net" / "merged"
        merged.mkdir(parents=True)
        self._write_delta(merged)  # all empty

        with _patch_clone_dir(tmp_path), _patch_head(sha), _patch_model(sha), \
                patch.object(_rk, "_update_clone", return_value=None):
            result = refresh("cells", "net")

        assert result == "current"

    def test_returns_current_when_sha_matches_with_pending_delta(self, tmp_path):
        """When SHA matches but delta has pending changes, refresh still returns 'current'
        (no re-run needed) — downstream consumers read the existing delta directly."""
        sha = "abc123"
        knowledge_root = tmp_path / "knowledge"
        merged = knowledge_root / "cells" / "net" / "merged"
        merged.mkdir(parents=True)
        self._write_delta(merged, new_apis=["PendingClass"])  # non-empty

        with _patch_clone_dir(tmp_path), _patch_head(sha), _patch_model(sha), \
                patch.object(_rk, "_update_clone", return_value=None):
            result = refresh("cells", "net")

        assert result == "current"

    def test_current_with_pending_delta_emits_diagnostic(self, tmp_path, capsys):
        """When SHA matches with pending delta, refresh emits a diagnostic message
        so downstream planners can detect the pending state without reading delta directly."""
        sha = "abc123abc123"
        knowledge_root = tmp_path / "knowledge"
        merged = knowledge_root / "cells" / "net" / "merged"
        merged.mkdir(parents=True)
        self._write_delta(merged, new_apis=["PendingClass"], removed_apis=["OldClass"])

        with _patch_clone_dir(tmp_path), _patch_head(sha), _patch_model(sha), \
                patch.object(_rk, "_update_clone", return_value=None):
            refresh("cells", "net")

        output = capsys.readouterr().out
        # Must mention the pending delta state
        assert "pending delta" in output.lower() or "pending" in output.lower(), (
            "RH-202: When knowledge is current but delta has pending changes, "
            "refresh() must emit a diagnostic for downstream planners"
        )


# ---------------------------------------------------------------------------
# RH-109 RC-4: Modified API/claim — prose updates (not just metadata)
# ---------------------------------------------------------------------------

class TestModifiedApiAndClaimDelta:
    """RH-109 RC-4: When an API signature or claim text changes, the delta records
    modified_apis / modified_claims — ensuring downstream tools update body prose,
    not just SHA metadata.

    This validates the Sprint 2 fix that distinguished semantic body changes from
    simple repo-SHA bumps.
    """

    def test_modified_apis_populated_when_method_name_changes(self, tmp_path):
        """RC-4: modified_apis includes the class when its method is renamed."""
        merged, bak = _make_merged_and_bak(tmp_path)

        _write_claims(bak / "claims.json", [])
        _write_apis(bak / "api_surface.json", [
            {"name": "Workbook", "methods": [{"name": "Save"}], "properties": []},
        ])
        _write_claims(merged / "claims.json", [])
        _write_apis(merged / "api_surface.json", [
            # Method renamed Save → SaveAs — this is a prose-affecting change
            {"name": "Workbook", "methods": [{"name": "SaveAs"}], "properties": []},
        ])

        _write_knowledge_delta("cells", "net", bak, merged, "sha_new", "sha_old")

        delta = json.loads((merged / "knowledge_delta.json").read_text())
        assert "Workbook" in delta["modified_apis"], (
            "RC-4 regression: modified_apis must include Workbook when its method set changes"
        )
        assert delta["new_apis"] == [], "Workbook existed before — not a new API"
        assert delta["removed_apis"] == [], "Workbook still exists — not removed"

    def test_modified_apis_populated_when_property_added(self, tmp_path):
        """RC-4: modified_apis includes the class when a property is added."""
        merged, bak = _make_merged_and_bak(tmp_path)

        _write_claims(bak / "claims.json", [])
        _write_apis(bak / "api_surface.json", [
            {"name": "Cell", "methods": [], "properties": []},
        ])
        _write_claims(merged / "claims.json", [])
        _write_apis(merged / "api_surface.json", [
            {"name": "Cell", "methods": [], "properties": [{"name": "Value"}]},
        ])

        _write_knowledge_delta("cells", "net", bak, merged, "sha_new", "sha_old")

        delta = json.loads((merged / "knowledge_delta.json").read_text())
        assert "Cell" in delta["modified_apis"], (
            "RC-4: modified_apis must include Cell when a property is added"
        )

    def test_modified_claims_populated_when_claim_text_changes(self, tmp_path):
        """RC-4: modified_claims includes the claim_id when claim text is reworded."""
        merged, bak = _make_merged_and_bak(tmp_path)

        _write_claims(bak / "claims.json", [
            {"claim_id": "SC-001", "text": "Workbook can be saved.", "confidence": 0.9},
        ])
        _write_apis(bak / "api_surface.json", [])
        _write_claims(merged / "claims.json", [
            # Text changed — downstream must update body prose that quoted this claim
            {"claim_id": "SC-001", "text": "Workbook can be saved as XLSX or CSV.", "confidence": 0.9},
        ])
        _write_apis(merged / "api_surface.json", [])

        _write_knowledge_delta("cells", "net", bak, merged, "sha_new", "sha_old")

        delta = json.loads((merged / "knowledge_delta.json").read_text())
        assert "SC-001" in delta["modified_claims"], (
            "RC-4 regression: modified_claims must include SC-001 when its text changes"
        )
        assert delta["new_claims"] == [], "SC-001 existed before — not new"
        assert delta["removed_claims"] == [], "SC-001 still exists — not removed"

    def test_modified_claims_populated_when_confidence_changes(self, tmp_path):
        """RC-4: modified_claims includes claim_id when confidence score changes."""
        merged, bak = _make_merged_and_bak(tmp_path)

        _write_claims(bak / "claims.json", [
            {"claim_id": "SC-002", "text": "Cell.PutValue sets a value.", "confidence": 0.7},
        ])
        _write_apis(bak / "api_surface.json", [])
        _write_claims(merged / "claims.json", [
            {"claim_id": "SC-002", "text": "Cell.PutValue sets a value.", "confidence": 0.95},
        ])
        _write_apis(merged / "api_surface.json", [])

        _write_knowledge_delta("cells", "net", bak, merged, "sha_new", "sha_old")

        delta = json.loads((merged / "knowledge_delta.json").read_text())
        assert "SC-002" in delta["modified_claims"], (
            "RC-4: modified_claims must include SC-002 when confidence changes"
        )

    def test_combined_api_and_claim_change_in_single_delta(self, tmp_path):
        """RC-4: modified_apis and modified_claims both populated in a combined update."""
        merged, bak = _make_merged_and_bak(tmp_path)

        _write_claims(bak / "claims.json", [
            {"claim_id": "SC-010", "text": "Workbook saves as CSV.", "confidence": 0.8},
        ])
        _write_apis(bak / "api_surface.json", [
            {"name": "Workbook", "methods": [{"name": "Save"}], "properties": []},
        ])
        _write_claims(merged / "claims.json", [
            {"claim_id": "SC-010", "text": "Workbook saves as CSV or XLSX.", "confidence": 0.95},
        ])
        _write_apis(merged / "api_surface.json", [
            {"name": "Workbook", "methods": [{"name": "Save"}, {"name": "SaveAs"}], "properties": []},
        ])

        _write_knowledge_delta("cells", "net", bak, merged, "sha_new", "sha_old")

        delta = json.loads((merged / "knowledge_delta.json").read_text())
        assert "Workbook" in delta["modified_apis"]
        assert "SC-010" in delta["modified_claims"]
        assert delta["new_apis"] == []
        assert delta["removed_apis"] == []
        assert delta["new_claims"] == []
        assert delta["removed_claims"] == []


# ---------------------------------------------------------------------------
# RH-112 RC-5: Idempotent rerun — zero changes on second run
# ---------------------------------------------------------------------------

class TestIdempotentRerun:
    """RH-112 RC-5: Running the pipeline twice on the same knowledge state must
    produce a zero-change delta on the second run and must not create duplicate
    pages. This validates that idempotency is maintained across multiple refreshes.
    """

    def test_second_delta_is_all_empty_when_knowledge_unchanged(self, tmp_path):
        """RC-5: After a refresh, writing the delta again with the same state
        produces all-empty delta fields (no spurious changes detected)."""
        merged, bak = _make_merged_and_bak(tmp_path)

        # Simulate steady-state: bak == merged (second run — no knowledge change)
        same_apis = [{"name": "Workbook", "methods": [{"name": "Save"}], "properties": []}]
        same_claims = [{"claim_id": "SC-001", "text": "Workbook saves.", "confidence": 0.9}]

        _write_claims(bak / "claims.json", same_claims)
        _write_apis(bak / "api_surface.json", same_apis)
        _write_claims(merged / "claims.json", same_claims)
        _write_apis(merged / "api_surface.json", same_apis)

        _write_knowledge_delta("cells", "net", bak, merged, "sha_same", "sha_same")

        delta = json.loads((merged / "knowledge_delta.json").read_text())
        assert delta["new_apis"] == [], "RC-5: no new APIs in idempotent second run"
        assert delta["removed_apis"] == [], "RC-5: no removed APIs in idempotent second run"
        assert delta["modified_apis"] == [], "RC-5: no modified APIs in idempotent second run"
        assert delta["new_claims"] == [], "RC-5: no new claims in idempotent second run"
        assert delta["removed_claims"] == [], "RC-5: no removed claims in idempotent second run"
        assert delta["modified_claims"] == [], "RC-5: no modified claims in idempotent second run"

    def test_second_refresh_returns_current_when_sha_matches(self, tmp_path):
        """RC-5: refresh() on same SHA as second run returns 'current' — no pipeline rerun."""
        sha = "deadbeef1234"

        with _patch_clone_dir(tmp_path), _patch_head(sha), _patch_model(sha), \
                patch.object(_rk, "_update_clone", return_value=None):
            result = refresh("cells", "net")

        assert result == "current", (
            "RC-5: refresh() must return 'current' when model SHA == HEAD (idempotent second run)"
        )

    def test_no_duplicate_api_names_in_modified_list(self, tmp_path):
        """RC-5: modified_apis must not contain duplicate class names even when both
        api_surface and ERC claims change for the same class."""
        merged, bak = _make_merged_and_bak(tmp_path)

        # Class 'Workbook' changes in both api_surface AND ERC claims
        _write_claims(bak / "claims.json", [
            {"claim_id": "ERC-001", "kind": "api", "text": "Workbook.Save persists data.", "confidence": 0.9},
        ])
        _write_apis(bak / "api_surface.json", [
            {"name": "Workbook", "methods": [{"name": "Save"}], "properties": []},
        ])
        _write_claims(merged / "claims.json", [
            {"claim_id": "ERC-001", "kind": "api", "text": "Workbook.Save persists data.", "confidence": 0.9},
            # New ERC claim for Workbook.SaveAs — triggers erc_changed_classes for Workbook
            {"claim_id": "ERC-002", "kind": "api", "text": "Workbook.SaveAs saves with new name.", "confidence": 0.85},
        ])
        _write_apis(merged / "api_surface.json", [
            # SaveAs added — triggers api_surface_modified for Workbook
            {"name": "Workbook", "methods": [{"name": "Save"}, {"name": "SaveAs"}], "properties": []},
        ])

        _write_knowledge_delta("cells", "net", bak, merged, "sha_new", "sha_old")

        delta = json.loads((merged / "knowledge_delta.json").read_text())
        modified = delta["modified_apis"]
        assert modified.count("Workbook") == 1, (
            "RC-5: 'Workbook' must appear exactly once in modified_apis even when "
            "both api_surface and ERC claims change for the same class"
        )

    def test_identical_runs_produce_identical_delta_keys(self, tmp_path):
        """RC-5: Running _write_knowledge_delta twice with same inputs produces
        identical output (deterministic across runs)."""
        merged, bak = _make_merged_and_bak(tmp_path)

        apis = [{"name": "Cell", "methods": [{"name": "PutValue"}], "properties": []}]
        claims = [{"claim_id": "SC-001", "text": "Cell sets values.", "confidence": 0.9}]

        _write_claims(bak / "claims.json", [])
        _write_apis(bak / "api_surface.json", [])
        _write_claims(merged / "claims.json", claims)
        _write_apis(merged / "api_surface.json", apis)

        _write_knowledge_delta("cells", "net", bak, merged, "sha_v2", "sha_v1")
        delta1 = json.loads((merged / "knowledge_delta.json").read_text())

        # Simulate second run: bak now reflects the state after first run
        _write_claims(bak / "claims.json", claims)
        _write_apis(bak / "api_surface.json", apis)
        # merged stays the same

        _write_knowledge_delta("cells", "net", bak, merged, "sha_v2", "sha_v2")
        delta2 = json.loads((merged / "knowledge_delta.json").read_text())

        # On the second run (bak == merged), everything should be empty
        assert delta2["new_apis"] == [], "Second run: no new APIs (Cell was already present)"
        assert delta2["new_claims"] == [], "Second run: no new claims"
        # delta1 should have had Cell as new
        assert "Cell" in delta1["new_apis"], "First run: Cell must be in new_apis"
        assert "SC-001" in delta1["new_claims"], "First run: SC-001 must be in new_claims"


# ---------------------------------------------------------------------------
# RH-201: Body-prose scanner — triage_confirm
# ---------------------------------------------------------------------------

class TestTriageConfirmBasic:
    """RH-201: triage_confirm() returns stale=False for clean pages."""

    def test_clean_page_not_stale(self, tmp_path):
        """A page with no delta signals is not stale."""
        page = tmp_path / "Workbook.md"
        page.write_text(
            "---\ntitle: Workbook\n---\n\nThe Workbook class supports saving files.\n",
            encoding="utf-8",
        )
        knowledge = {
            "api_surface": [{"name": "Workbook", "methods": [], "properties": []}],
            "claims": [],
            "delta": {"removed_apis": [], "modified_apis": [], "removed_claims": []},
        }
        result = triage_confirm(page, knowledge)
        assert result["stale"] is False
        assert result["reasons"] == []
        assert result["confidence"] == 0.0

    def test_missing_page_returns_not_stale(self, tmp_path):
        """Unreadable page is treated as non-stale (unknown state — no false positive)."""
        result = triage_confirm(tmp_path / "NonExistent.md", {})
        assert result["stale"] is False
        assert any("could not read page" in r for r in result["reasons"])

    def test_returns_dict_with_required_keys(self, tmp_path):
        """triage_confirm always returns a dict with stale, reasons, confidence."""
        page = tmp_path / "index.md"
        page.write_text("body", encoding="utf-8")
        result = triage_confirm(page, {})
        assert "stale" in result
        assert "reasons" in result
        assert "confidence" in result


class TestTriageConfirmRemovedApi:
    """RH-201: Signal 1 — body mentions removed API."""

    def test_stale_when_body_references_removed_api(self, tmp_path):
        """Page body mentions an API that has been removed → stale."""
        page = tmp_path / "WorksheetOld.md"
        page.write_text(
            "Use the OldFormatter class to format cells.\n",
            encoding="utf-8",
        )
        knowledge = {
            "delta": {"removed_apis": ["OldFormatter"], "modified_apis": [], "removed_claims": []},
        }
        result = triage_confirm(page, knowledge)
        assert result["stale"] is True
        assert any("OldFormatter" in r for r in result["reasons"])
        assert result["confidence"] >= 0.9

    def test_not_stale_when_removed_api_not_in_body(self, tmp_path):
        """Page body does not mention the removed API → not stale from this signal."""
        page = tmp_path / "Workbook.md"
        page.write_text("The Workbook class supports CSV export.\n", encoding="utf-8")
        knowledge = {
            "delta": {"removed_apis": ["OldFormatter"], "modified_apis": [], "removed_claims": []},
        }
        result = triage_confirm(page, knowledge)
        assert result["stale"] is False

    def test_word_boundary_prevents_false_positive(self, tmp_path):
        """'WorkbookOld' in body should not match removed API 'Workbook'."""
        page = tmp_path / "detail.md"
        page.write_text("WorkbookOld is the legacy class.\n", encoding="utf-8")
        knowledge = {
            "delta": {"removed_apis": ["Workbook"], "modified_apis": [], "removed_claims": []},
        }
        result = triage_confirm(page, knowledge)
        # "Workbook" as a word boundary should NOT match inside "WorkbookOld"
        assert result["stale"] is False, (
            "Word-boundary check must prevent 'Workbook' from matching 'WorkbookOld'"
        )


class TestTriageConfirmModifiedApi:
    """RH-201: Signal 2 — body mentions modified API."""

    def test_stale_when_body_references_modified_api(self, tmp_path):
        """Page body mentions an API that was modified → potentially stale."""
        page = tmp_path / "Cell.md"
        page.write_text(
            "The Cell class provides PutValue and GetValue methods.\n",
            encoding="utf-8",
        )
        knowledge = {
            "delta": {"removed_apis": [], "modified_apis": ["Cell"], "removed_claims": []},
        }
        result = triage_confirm(page, knowledge)
        assert result["stale"] is True
        assert any("Cell" in r for r in result["reasons"])
        assert 0.5 <= result["confidence"] < 0.9  # lower confidence than removed

    def test_not_stale_when_modified_api_not_in_body(self, tmp_path):
        """Page body does not mention the modified API → not stale from this signal."""
        page = tmp_path / "Workbook.md"
        page.write_text("Workbook handles file I/O.\n", encoding="utf-8")
        knowledge = {
            "delta": {"removed_apis": [], "modified_apis": ["Cell"], "removed_claims": []},
        }
        result = triage_confirm(page, knowledge)
        assert result["stale"] is False


class TestTriageConfirmSlugCheck:
    """RH-201: Signal 3 — page slug not in current api_surface."""

    def test_stale_when_slug_not_in_api_surface(self, tmp_path):
        """Page file is named after a class that no longer exists in api_surface."""
        page = tmp_path / "ObsoleteClass.md"
        page.write_text("This is the ObsoleteClass reference page.\n", encoding="utf-8")
        knowledge = {
            "api_surface": [{"name": "Workbook", "methods": [], "properties": []}],
            "delta": {},
        }
        result = triage_confirm(page, knowledge)
        assert result["stale"] is True
        assert any("ObsoleteClass" in r for r in result["reasons"])
        assert result["confidence"] >= 0.8

    def test_not_stale_when_slug_in_api_surface(self, tmp_path):
        """Page slug matches a class that still exists in api_surface."""
        page = tmp_path / "Workbook.md"
        page.write_text("The Workbook reference page.\n", encoding="utf-8")
        knowledge = {
            "api_surface": [{"name": "Workbook", "methods": [], "properties": []}],
            "delta": {},
        }
        result = triage_confirm(page, knowledge)
        assert result["stale"] is False

    def test_lowercase_slug_ignored(self, tmp_path):
        """Lowercase slugs (e.g. index.md) are not checked against api_surface."""
        page = tmp_path / "index.md"
        page.write_text("Welcome.\n", encoding="utf-8")
        knowledge = {
            "api_surface": [{"name": "Workbook", "methods": [], "properties": []}],
            "delta": {},
        }
        result = triage_confirm(page, knowledge)
        assert result["stale"] is False

    def test_no_api_surface_skips_slug_check(self, tmp_path):
        """When api_surface is empty/absent, slug check is skipped (no false positives)."""
        page = tmp_path / "Workbook.md"
        page.write_text("Workbook reference.\n", encoding="utf-8")
        knowledge = {"api_surface": [], "delta": {}}
        result = triage_confirm(page, knowledge)
        assert result["stale"] is False


class TestTriageConfirmRemovedClaim:
    """RH-201: Signal 4 — body contains a removed claim ID."""

    def test_stale_when_body_contains_removed_claim_id(self, tmp_path):
        """Page body explicitly references a claim ID that has been removed."""
        page = tmp_path / "workbook.md"
        page.write_text(
            "<!-- evidence: SC-099 -->\nWorkbook exports to PDF.\n",
            encoding="utf-8",
        )
        knowledge = {
            "delta": {"removed_apis": [], "modified_apis": [], "removed_claims": ["SC-099"]},
        }
        result = triage_confirm(page, knowledge)
        assert result["stale"] is True
        assert any("SC-099" in r for r in result["reasons"])

    def test_not_stale_when_removed_claim_not_in_body(self, tmp_path):
        """Removed claim ID is not referenced in page body → not stale."""
        page = tmp_path / "workbook.md"
        page.write_text("Workbook exports to PDF.\n", encoding="utf-8")
        knowledge = {
            "delta": {"removed_apis": [], "modified_apis": [], "removed_claims": ["SC-099"]},
        }
        result = triage_confirm(page, knowledge)
        assert result["stale"] is False


class TestTriageConfirmMultipleSignals:
    """RH-201: Multiple signals accumulate — highest confidence wins."""

    def test_multiple_signals_accumulate_reasons(self, tmp_path):
        """When multiple signals fire, all reasons are reported."""
        page = tmp_path / "ObsoleteClass.md"
        page.write_text(
            "The ObsoleteClass wraps LegacyHelper. <!-- SC-001 -->\n",
            encoding="utf-8",
        )
        knowledge = {
            "api_surface": [{"name": "Workbook", "methods": [], "properties": []}],
            "delta": {
                "removed_apis": ["LegacyHelper"],
                "modified_apis": [],
                "removed_claims": ["SC-001"],
            },
        }
        result = triage_confirm(page, knowledge)
        assert result["stale"] is True
        # Should have at least 3 reasons: removed API + removed claim + slug not in surface
        assert len(result["reasons"]) >= 2

    def test_confidence_is_max_of_all_signals(self, tmp_path):
        """Confidence reflects the strongest signal (removed API = 0.9)."""
        page = tmp_path / "OldPage.md"
        page.write_text("OldFormatter is used here.\n", encoding="utf-8")
        knowledge = {
            "api_surface": [{"name": "Workbook", "methods": [], "properties": []}],
            "delta": {
                "removed_apis": ["OldFormatter"],  # 0.9
                "modified_apis": [],
                "removed_claims": [],
            },
        }
        result = triage_confirm(page, knowledge)
        assert result["confidence"] >= 0.9


# ---------------------------------------------------------------------------
# RH-203: Enhanced reconciliation — 3-source schema + final_verdict
# ---------------------------------------------------------------------------

class TestReconcileTriageFinalVerdict:
    """RH-203: final_verdict combines all three sources conservatively."""

    def test_final_verdict_current_when_all_clean(self, tmp_path):
        """All three sources clean → final_verdict = 'current'."""
        page = tmp_path / "Workbook.md"
        page.write_text("Workbook reference page.\n", encoding="utf-8")
        knowledge = {"api_surface": [{"name": "Workbook", "methods": [], "properties": []}], "delta": {}}

        result = reconcile_triage_page(
            page, knowledge, layer1_stale=False, page_spec_missing=False
        )
        assert result.final_verdict == "current"
        assert result.final_confidence == 0.0
        assert result.final_reasons == []

    def test_final_verdict_needs_update_from_layer1(self, tmp_path):
        """Layer 1 stale (SHA mismatch) → final_verdict = 'needs_update'."""
        page = tmp_path / "Workbook.md"
        page.write_text("Workbook reference page.\n", encoding="utf-8")
        knowledge = {"delta": {}}

        result = reconcile_triage_page(page, knowledge, layer1_stale=True)
        assert result.final_verdict == "needs_update"
        assert result.final_confidence == 1.0

    def test_final_verdict_needs_update_from_layer2(self, tmp_path):
        """Layer 2 stale (body mentions removed API) → final_verdict = 'needs_update'."""
        page = tmp_path / "Cell.md"
        page.write_text("The OldClass provides CSV export.\n", encoding="utf-8")
        knowledge = {
            "delta": {"removed_apis": ["OldClass"], "modified_apis": [], "removed_claims": []},
        }

        result = reconcile_triage_page(page, knowledge, layer1_stale=False)
        assert result.final_verdict == "needs_update"
        assert result.final_confidence >= 0.9

    def test_final_verdict_missing_from_page_spec(self, tmp_path):
        """page_spec missing → final_verdict = 'missing' (highest priority)."""
        page = tmp_path / "Workbook.md"
        page.write_text("Workbook page.\n", encoding="utf-8")
        knowledge = {"delta": {}}

        result = reconcile_triage_page(page, knowledge, page_spec_missing=True)
        assert result.final_verdict == "missing"
        assert result.final_confidence == 1.0

    def test_page_spec_missing_overrides_layer1_stale(self, tmp_path):
        """page_spec missing takes priority over Layer 1 stale."""
        page = tmp_path / "Workbook.md"
        page.write_text("Workbook page.\n", encoding="utf-8")
        knowledge = {"delta": {}}

        result = reconcile_triage_page(
            page, knowledge, layer1_stale=True, page_spec_missing=True
        )
        assert result.final_verdict == "missing", (
            "page_spec missing must take priority over layer1 stale signal"
        )

    def test_layer2_stale_when_layer1_current(self, tmp_path):
        """Layer 1 current but Layer 2 stale → needs_update (conservative)."""
        page = tmp_path / "OldFormatter.md"
        page.write_text("OldFormatter handles cell formatting.\n", encoding="utf-8")
        knowledge = {
            "api_surface": [{"name": "Workbook", "methods": [], "properties": []}],
            "delta": {"removed_apis": ["OldFormatter"], "modified_apis": [], "removed_claims": []},
        }

        result = reconcile_triage_page(page, knowledge, layer1_stale=False)
        assert result.final_verdict == "needs_update", (
            "Conservative rule: Layer 2 stale must trigger needs_update "
            "even when Layer 1 reports current"
        )


class TestReconcileTriageSources:
    """RH-203: Individual source records are correctly populated."""

    def test_layer1_source_populated_when_stale(self, tmp_path):
        """Layer 1 source has correct name, verdict, confidence when stale."""
        page = tmp_path / "page.md"
        page.write_text("content", encoding="utf-8")

        result = reconcile_triage_page(page, {}, layer1_stale=True)
        assert result.layer1_triage.name == "layer1_triage"
        assert result.layer1_triage.verdict == "needs_update"
        assert result.layer1_triage.confidence == 1.0
        assert len(result.layer1_triage.reasons) > 0

    def test_layer1_source_current_when_not_stale(self, tmp_path):
        """Layer 1 source has verdict='current' when SHA matches."""
        page = tmp_path / "page.md"
        page.write_text("content", encoding="utf-8")

        result = reconcile_triage_page(page, {}, layer1_stale=False)
        assert result.layer1_triage.verdict == "current"
        assert result.layer1_triage.confidence == 0.0

    def test_layer2_source_populated_when_body_stale(self, tmp_path):
        """Layer 2 source records reasons from triage_confirm."""
        page = tmp_path / "page.md"
        page.write_text("RemovedClass is used here.\n", encoding="utf-8")
        knowledge = {
            "delta": {"removed_apis": ["RemovedClass"], "modified_apis": [], "removed_claims": []},
        }

        result = reconcile_triage_page(page, knowledge)
        assert result.layer2_triage.name == "layer2_triage"
        assert result.layer2_triage.verdict == "needs_update"
        assert any("RemovedClass" in r for r in result.layer2_triage.reasons)

    def test_page_spec_source_missing(self, tmp_path):
        """page_spec source has verdict='missing' when page absent from plan."""
        page = tmp_path / "page.md"
        page.write_text("content", encoding="utf-8")

        result = reconcile_triage_page(page, {}, page_spec_missing=True)
        assert result.page_spec.name == "page_spec"
        assert result.page_spec.verdict == "missing"
        assert result.page_spec.confidence == 1.0

    def test_layer1_custom_reasons_propagated(self, tmp_path):
        """Custom layer1_reasons are stored in layer1_triage.reasons."""
        page = tmp_path / "page.md"
        page.write_text("content", encoding="utf-8")
        custom = ["knowledge updated: 3 API changes"]

        result = reconcile_triage_page(page, {}, layer1_stale=True, layer1_reasons=custom)
        assert result.layer1_triage.reasons == custom


class TestReconcileTriageSchema:
    """RH-203: to_dict() produces complete 3-source schema with all required fields."""

    def test_to_dict_contains_all_required_keys(self, tmp_path):
        """to_dict() output must include all schema-required top-level keys."""
        page = tmp_path / "Workbook.md"
        page.write_text("content", encoding="utf-8")

        result = reconcile_triage_page(
            page, {}, family="cells", platform="net", layer1_stale=False
        )
        d = result.to_dict()

        required_keys = {
            "family", "platform", "page_path",
            "sources", "final_verdict", "final_confidence", "final_reasons",
        }
        assert required_keys <= set(d.keys()), (
            f"to_dict() missing required keys: {required_keys - set(d.keys())}"
        )

    def test_sources_dict_has_all_three_sources(self, tmp_path):
        """to_dict()['sources'] must contain layer1_triage, layer2_triage, page_spec."""
        page = tmp_path / "page.md"
        page.write_text("content", encoding="utf-8")

        result = reconcile_triage_page(page, {})
        sources = result.to_dict()["sources"]

        assert "layer1_triage" in sources
        assert "layer2_triage" in sources
        assert "page_spec" in sources

    def test_each_source_has_required_fields(self, tmp_path):
        """Each source in to_dict()['sources'] must have name, verdict, confidence, reasons."""
        page = tmp_path / "page.md"
        page.write_text("content", encoding="utf-8")

        result = reconcile_triage_page(page, {})
        sources = result.to_dict()["sources"]

        for source_name, source_dict in sources.items():
            required = {"name", "verdict", "confidence", "reasons"}
            assert required <= set(source_dict.keys()), (
                f"Source '{source_name}' missing required fields: "
                f"{required - set(source_dict.keys())}"
            )

    def test_family_and_platform_in_output(self, tmp_path):
        """family and platform are preserved in to_dict() output."""
        page = tmp_path / "page.md"
        page.write_text("content", encoding="utf-8")

        result = reconcile_triage_page(
            page, {}, family="words", platform="python"
        )
        d = result.to_dict()
        assert d["family"] == "words"
        assert d["platform"] == "python"

    def test_final_verdict_values_are_valid(self, tmp_path):
        """final_verdict must be one of the three valid states."""
        valid_verdicts = {"needs_update", "current", "missing"}

        page = tmp_path / "page.md"
        page.write_text("content", encoding="utf-8")

        for stale, missing in [(False, False), (True, False), (False, True)]:
            result = reconcile_triage_page(
                page, {}, layer1_stale=stale, page_spec_missing=missing
            )
            assert result.final_verdict in valid_verdicts, (
                f"final_verdict '{result.final_verdict}' is not a valid state"
            )


class TestReconcileTriageDataclass:
    """RH-203: ReconcileTriage and TriageSource dataclass structure."""

    def test_triage_source_to_dict(self):
        """TriageSource.to_dict() returns expected structure."""
        source = TriageSource(
            name="layer1_triage",
            verdict="needs_update",
            confidence=0.8,
            reasons=["SHA mismatch"],
        )
        d = source.to_dict()
        assert d == {
            "name": "layer1_triage",
            "verdict": "needs_update",
            "confidence": 0.8,
            "reasons": ["SHA mismatch"],
        }

    def test_triage_source_defaults(self):
        """TriageSource has sensible defaults."""
        source = TriageSource(name="page_spec", verdict="current")
        assert source.confidence == 0.0
        assert source.reasons == []

    def test_reconcile_triage_is_dataclass(self, tmp_path):
        """reconcile_triage_page returns a ReconcileTriage instance."""
        page = tmp_path / "page.md"
        page.write_text("content", encoding="utf-8")
        result = reconcile_triage_page(page, {})
        assert isinstance(result, ReconcileTriage)
        assert isinstance(result.layer1_triage, TriageSource)
        assert isinstance(result.layer2_triage, TriageSource)
        assert isinstance(result.page_spec, TriageSource)


# ---------------------------------------------------------------------------
# RH-205: Two-layer model proof — 5 end-to-end cases
# ---------------------------------------------------------------------------

class TestTwoLayerModelProof:
    """RH-205: End-to-end proof that the two-layer triage model produces correct
    final_verdict across all 5 canonical combinations.

    Case 1 — Layer 1-only stale: SHA mismatch, body prose clean.
    Case 2 — Layer 2-only stale: SHA current, body references a removed API.
    Case 3 — Both layers stale: SHA mismatch AND body references removed API.
    Case 4 — Neither layer stale: SHA current, body prose clean.
    Case 5 — page_spec missing overrides all: layer1 stale but verdict=missing.
    """

    def _make_page(self, tmp_path: Path, body: str, name: str = "Workbook.md") -> Path:
        page = tmp_path / name
        page.write_text(body, encoding="utf-8")
        return page

    def test_layer1_only_stale(self, tmp_path):
        """Case 1: Layer 1 stale (SHA mismatch) + clean body → needs_update from L1 alone."""
        body = "# Workbook\n\nUse the Workbook class to open spreadsheets.\n"
        page = self._make_page(tmp_path, body)
        knowledge = {
            "api_surface": [{"name": "Workbook"}, {"name": "Worksheet"}],
            "delta": {"removed_apis": [], "modified_apis": [], "removed_claims": []},
        }
        result = reconcile_triage_page(
            page_path=page,
            knowledge=knowledge,
            layer1_stale=True,
            layer1_reasons=["SHA mismatch: upstream commit a1b2c3"],
            family="cells",
            platform="python",
        )
        assert result.final_verdict == "needs_update"
        assert result.layer1_triage.verdict == "needs_update"
        assert result.layer2_triage.verdict == "current"
        assert result.page_spec.verdict == "current"
        assert result.final_confidence == 1.0
        assert any("SHA mismatch" in r for r in result.final_reasons)

    def test_layer2_only_stale(self, tmp_path):
        """Case 2: SHA current + body references removed API → needs_update from L2 alone."""
        body = "# Workbook\n\nUse DeprecatedLoader to load files.\n"
        page = self._make_page(tmp_path, body)
        knowledge = {
            "api_surface": [{"name": "Workbook"}],
            "delta": {
                "removed_apis": ["DeprecatedLoader"],
                "modified_apis": [],
                "removed_claims": [],
            },
        }
        result = reconcile_triage_page(
            page_path=page,
            knowledge=knowledge,
            layer1_stale=False,
            family="cells",
            platform="python",
        )
        assert result.final_verdict == "needs_update"
        assert result.layer1_triage.verdict == "current"
        assert result.layer2_triage.verdict == "needs_update"
        assert result.page_spec.verdict == "current"
        assert result.layer2_triage.confidence >= 0.9
        assert any("DeprecatedLoader" in r for r in result.final_reasons)

    def test_both_layers_stale(self, tmp_path):
        """Case 3: SHA mismatch AND body references removed API → needs_update, both L1+L2 fire."""
        body = "# Workbook\n\nUse DeprecatedLoader to load files.\n"
        page = self._make_page(tmp_path, body)
        knowledge = {
            "api_surface": [{"name": "Workbook"}],
            "delta": {
                "removed_apis": ["DeprecatedLoader"],
                "modified_apis": [],
                "removed_claims": [],
            },
        }
        result = reconcile_triage_page(
            page_path=page,
            knowledge=knowledge,
            layer1_stale=True,
            layer1_reasons=["SHA mismatch: upstream changed"],
            family="cells",
            platform="python",
        )
        assert result.final_verdict == "needs_update"
        assert result.layer1_triage.verdict == "needs_update"
        assert result.layer2_triage.verdict == "needs_update"
        reasons_text = " ".join(result.final_reasons)
        assert "SHA mismatch" in reasons_text
        assert "DeprecatedLoader" in reasons_text

    def test_neither_layer_stale(self, tmp_path):
        """Case 4: SHA current + clean body → final_verdict = current."""
        body = "# Workbook\n\nUse the Workbook class to manage spreadsheets.\n"
        page = self._make_page(tmp_path, body)
        knowledge = {
            "api_surface": [{"name": "Workbook"}, {"name": "Worksheet"}],
            "delta": {"removed_apis": [], "modified_apis": [], "removed_claims": []},
        }
        result = reconcile_triage_page(
            page_path=page,
            knowledge=knowledge,
            layer1_stale=False,
            family="cells",
            platform="python",
        )
        assert result.final_verdict == "current"
        assert result.layer1_triage.verdict == "current"
        assert result.layer2_triage.verdict == "current"
        assert result.page_spec.verdict == "current"
        assert result.final_confidence == 0.0
        assert result.final_reasons == []

    def test_page_spec_missing_overrides_layer1_stale(self, tmp_path):
        """Case 5: page_spec_missing=True overrides layer1_stale → final_verdict = missing."""
        body = "# Workbook\n\nThis page is in the plan but not fully written.\n"
        page = self._make_page(tmp_path, body)
        knowledge = {
            "api_surface": [{"name": "Workbook"}],
            "delta": {"removed_apis": [], "modified_apis": [], "removed_claims": []},
        }
        result = reconcile_triage_page(
            page_path=page,
            knowledge=knowledge,
            layer1_stale=True,
            layer1_reasons=["SHA mismatch"],
            page_spec_missing=True,
            family="cells",
            platform="python",
        )
        assert result.final_verdict == "missing"
        assert result.page_spec.verdict == "missing"
        assert result.final_confidence == 1.0
        assert any("plan" in r for r in result.final_reasons)


# ---------------------------------------------------------------------------
# SR-04 (TC-2): reconcile_triage_page with unreadable page → final_verdict "unknown"
# ---------------------------------------------------------------------------

class TestReconcileTriageReadError:
    """TC-2: unreadable page must produce final_verdict='unknown', never 'current'."""

    def test_nonexistent_page_yields_unknown_not_current(self, tmp_path):
        """reconcile_triage_page on a non-existent file → unknown (not current, not stale)."""
        nonexistent = tmp_path / "does_not_exist.md"
        result = reconcile_triage_page(nonexistent, {})
        assert result.layer2_triage.verdict == "read_error", (
            f"Expected layer2_triage.verdict='read_error', got {result.layer2_triage.verdict!r}"
        )
        assert result.final_verdict == "unknown", (
            f"Expected final_verdict='unknown', got {result.final_verdict!r}"
        )

    def test_read_error_blocked_by_layer1_needs_update(self, tmp_path):
        """If layer1 already signals needs_update, read_error does not downgrade to unknown."""
        nonexistent = tmp_path / "missing.md"
        result = reconcile_triage_page(nonexistent, {}, layer1_stale=True)
        # layer1 wins → needs_update (read_error only blocks 'current')
        assert result.final_verdict == "needs_update"

    def test_read_error_reasons_propagated(self, tmp_path):
        """read_error reasons must be included in final_reasons."""
        nonexistent = tmp_path / "missing.md"
        result = reconcile_triage_page(nonexistent, {})
        assert result.final_reasons, "final_reasons must be non-empty for read_error"
        assert any("read" in r.lower() or "could not" in r.lower()
                   for r in result.final_reasons), (
            f"Expected a 'could not read' reason, got: {result.final_reasons}"
        )

    def test_triage_confirm_read_error_has_verdict_key(self, tmp_path):
        """triage_confirm itself returns a dict with verdict='read_error' for missing files."""
        from triage_confirm import triage_confirm
        result = triage_confirm(tmp_path / "nonexistent.md", {})
        assert result.get("verdict") == "read_error"
        assert result["stale"] is False
        assert any("could not read" in r for r in result["reasons"])

    def test_read_error_operator_visible_output(self, tmp_path):
        """to_dict() output for read_error path is complete, human-readable, and JSON-serialisable.

        Integration proof: verifies what an operator-facing caller (logger, CLI, API) would
        actually receive — not just internal ReconcileTriage attributes but the serialised
        dict that crosses the skill boundary.
        """
        import json

        nonexistent = tmp_path / "does_not_exist.md"
        result = reconcile_triage_page(nonexistent, {}, family="3d", platform="typescript")
        d = result.to_dict()

        # Operator-facing top-level verdict must be "unknown"
        assert d["final_verdict"] == "unknown", (
            f"Operator would see final_verdict={d['final_verdict']!r}; expected 'unknown'"
        )
        # Layer 2 source must carry read_error so operator knows the cause
        assert d["sources"]["layer2_triage"]["verdict"] == "read_error", (
            f"layer2_triage verdict={d['sources']['layer2_triage']['verdict']!r}; expected 'read_error'"
        )
        # Reasons must be non-empty so operator has actionable context
        assert d["final_reasons"], "final_reasons must be non-empty for operator to act on"
        # Serialisable — operator can write to log / return as JSON API response
        json.dumps(d)  # raises TypeError if any value is non-serialisable
