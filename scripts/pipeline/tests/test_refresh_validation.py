"""Regression tests for refresh pipeline validation (RH-108, RH-110, RH-111, RH-202).

RH-108 RC-1: Removal-only delta produces semantic body changes, not just SHA metadata.
RH-110 RC-2: New page generation — pages_to_add populated when new APIs/claims added.
RH-111 RC-3: Enrichment truthfulness — success path (V4) and failure path (V5).
RH-202:      Delta-aware idempotency helpers for downstream planners.

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
                patch.object(_rk, "_run_completeness_check"), \
                patch.object(_rk, "KNOWLEDGE_ROOT", knowledge_root):
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
                patch.object(_rk, "_run_completeness_check"), \
                patch.object(_rk, "KNOWLEDGE_ROOT", knowledge_root):
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

    def test_enrich_failure_deletes_stale_enriched_claims(self, tmp_path):
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
                patch.object(_rk, "_run_completeness_check"), \
                patch.object(_rk, "KNOWLEDGE_ROOT", knowledge_root):
            result = refresh("cells", "python")

        assert result == "refreshed"
        assert not enriched.exists(), (
            "V5: stale enriched_claims.json must be deleted when enrich fails "
            "to prevent promote.py from using outdated enriched data"
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
                patch.object(_rk, "_run_completeness_check"), \
                patch.object(_rk, "KNOWLEDGE_ROOT", knowledge_root):
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
        with patch.object(_rk, "KNOWLEDGE_ROOT", tmp_path):
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

        with patch.object(_rk, "KNOWLEDGE_ROOT", tmp_path):
            result = _load_knowledge_delta("cells", "net")

        assert isinstance(result, dict)
        assert result["new_apis"] == ["Foo"]

    def test_returns_none_on_invalid_json(self, tmp_path):
        merged = tmp_path / "cells" / "net" / "merged"
        merged.mkdir(parents=True)
        (merged / "knowledge_delta.json").write_text("{not valid json", encoding="utf-8")

        with patch.object(_rk, "KNOWLEDGE_ROOT", tmp_path):
            result = _load_knowledge_delta("cells", "net")

        assert result is None

    def test_returns_none_when_content_not_dict(self, tmp_path):
        merged = tmp_path / "cells" / "net" / "merged"
        merged.mkdir(parents=True)
        (merged / "knowledge_delta.json").write_text("[]", encoding="utf-8")

        with patch.object(_rk, "KNOWLEDGE_ROOT", tmp_path):
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
        with patch.object(_rk, "KNOWLEDGE_ROOT", tmp_path):
            assert _has_pending_delta("cells", "net") is False

    def test_false_when_all_empty(self, tmp_path):
        merged = tmp_path / "cells" / "net" / "merged"
        merged.mkdir(parents=True)
        self._write_delta(merged)

        with patch.object(_rk, "KNOWLEDGE_ROOT", tmp_path):
            assert _has_pending_delta("cells", "net") is False

    def test_true_when_new_apis_present(self, tmp_path):
        merged = tmp_path / "cells" / "net" / "merged"
        merged.mkdir(parents=True)
        self._write_delta(merged, new_apis=["NewClass"])

        with patch.object(_rk, "KNOWLEDGE_ROOT", tmp_path):
            assert _has_pending_delta("cells", "net") is True

    def test_true_when_removed_apis_present(self, tmp_path):
        merged = tmp_path / "cells" / "net" / "merged"
        merged.mkdir(parents=True)
        self._write_delta(merged, removed_apis=["OldClass"])

        with patch.object(_rk, "KNOWLEDGE_ROOT", tmp_path):
            assert _has_pending_delta("cells", "net") is True

    def test_true_when_modified_apis_present(self, tmp_path):
        merged = tmp_path / "cells" / "net" / "merged"
        merged.mkdir(parents=True)
        self._write_delta(merged, modified_apis=["ChangedClass"])

        with patch.object(_rk, "KNOWLEDGE_ROOT", tmp_path):
            assert _has_pending_delta("cells", "net") is True

    def test_true_when_removed_claims_present(self, tmp_path):
        merged = tmp_path / "cells" / "net" / "merged"
        merged.mkdir(parents=True)
        self._write_delta(merged, removed_claims=["SC-001"])

        with patch.object(_rk, "KNOWLEDGE_ROOT", tmp_path):
            assert _has_pending_delta("cells", "net") is True

    def test_true_when_new_claims_present(self, tmp_path):
        merged = tmp_path / "cells" / "net" / "merged"
        merged.mkdir(parents=True)
        self._write_delta(merged, new_claims=["SC-100"])

        with patch.object(_rk, "KNOWLEDGE_ROOT", tmp_path):
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
                patch.object(_rk, "_update_clone", return_value=None), \
                patch.object(_rk, "KNOWLEDGE_ROOT", knowledge_root):
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
                patch.object(_rk, "_update_clone", return_value=None), \
                patch.object(_rk, "KNOWLEDGE_ROOT", knowledge_root):
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
                patch.object(_rk, "_update_clone", return_value=None), \
                patch.object(_rk, "KNOWLEDGE_ROOT", knowledge_root):
            refresh("cells", "net")

        output = capsys.readouterr().out
        # Must mention the pending delta state
        assert "pending delta" in output.lower() or "pending" in output.lower(), (
            "RH-202: When knowledge is current but delta has pending changes, "
            "refresh() must emit a diagnostic for downstream planners"
        )
