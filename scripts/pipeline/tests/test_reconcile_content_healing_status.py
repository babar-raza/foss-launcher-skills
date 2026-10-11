"""Tests for scripts/pipeline/commands/ops/reconcile_content_healing_status.py
(PKGINSTALL-CONTENT-HEALING-STATUS-WRITEBACK).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "commands" / "ops"))

import reconcile_content_healing_status as rchs  # noqa: E402
from reconcile_content_healing_status import (  # noqa: E402
    compute_transition, find_pending_transitions, run_reconciliation, DeployTriggerNotClosedError,
    _read_literal_count,
)
import reconciliation_store as _reco  # noqa: E402
from schema_validators import validate_reconciliation_record  # noqa: E402


class _FakeTaskcardStore:
    """Minimal DI double for TaskcardStore -- only .get() is ever called by
    the code under test, so only .get() needs implementing."""

    def __init__(self, status: "str | None"):
        self._status = status

    def get(self, task_id: str):
        if self._status is None:
            return None
        return {"task_id": task_id, "status": self._status}


def _registry(family: str, platform: str, status: str) -> dict:
    return {
        family: {platform: {
            "registry_type": "pypi",
            "candidate": {"name": f"aspose-{family}-foss"},
            "candidate_owner": "asposefoss",
            "verification": {"published": True, "verified_at": "2026-08-01", "verified_owner": "Aspose",
                              "evidence_url": "https://pypi.org/x", "method": "pypi-json-api"},
            "owner_match": None,
            "content_healing_status": status,
            "content_healing_status_set_at": "2026-08-01",
        }}
    }


def _write_registry(tmp_path: Path, data: dict) -> Path:
    registry_dir = tmp_path / "data"
    registry_dir.mkdir(parents=True, exist_ok=True)
    path = registry_dir / "package_registry.json"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


class TestComputeTransition:
    def test_no_reconciliation_data_at_all_returns_none(self, tmp_path):
        store = _reco.ReconciliationStore(repo_root=tmp_path)
        result = compute_transition("words", "python", store=store)
        assert result is None

    def test_nonzero_literal_findings_returns_none(self, tmp_path):
        store = _reco.ReconciliationStore(repo_root=tmp_path)
        store.append_batch([{
            "path": "content/docs.aspose.org/en/words/python/getting-started/installation.md",
            "family": "words", "platform": "python", "site": "docs.aspose.org", "locale": "en",
            "representation": "literal", "collision_classification": None,
            "finding_count_literal": 3, "sweep_run_id": "run-1", "recorded_at": "2026-09-10T00:00:00Z",
        }])
        result = compute_transition("words", "python", store=store)
        assert result is None

    def test_zero_literal_findings_across_all_rows_proposes_healed(self, tmp_path):
        store = _reco.ReconciliationStore(repo_root=tmp_path)
        store.append_batch([
            {
                "path": "content/docs.aspose.org/en/words/python/getting-started/installation.md",
                "family": "words", "platform": "python", "site": "docs.aspose.org", "locale": "en",
                "representation": "shortcode_block", "collision_classification": None,
                "finding_count_literal": 0, "sweep_run_id": "run-1", "recorded_at": "2026-09-10T00:00:00Z",
            },
            {
                "path": "content/kb.aspose.org/en/words/python/how-to.md",
                "family": "words", "platform": "python", "site": "kb.aspose.org", "locale": "en",
                "representation": "shortcode_block", "collision_classification": None,
                "finding_count_literal": 0, "sweep_run_id": "run-1", "recorded_at": "2026-09-10T00:00:00Z",
            },
        ])
        result = compute_transition("words", "python", store=store)
        assert result is not None
        assert result["from_status"] == "pending"
        assert result["to_status"] == "healed"
        assert result["evidence_row_count"] == 2

    def test_one_zero_one_nonzero_row_returns_none(self, tmp_path):
        """A partial sweep (some pages already migrated, one still literal)
        must not be treated as fully healed."""
        store = _reco.ReconciliationStore(repo_root=tmp_path)
        store.append_batch([
            {"path": "a.md", "family": "words", "platform": "python", "site": "docs.aspose.org",
             "locale": "en", "representation": "shortcode_block", "collision_classification": None,
             "finding_count_literal": 0, "sweep_run_id": "run-1", "recorded_at": "2026-09-10T00:00:00Z"},
            {"path": "b.md", "family": "words", "platform": "python", "site": "docs.aspose.org",
             "locale": "en", "representation": "literal", "collision_classification": None,
             "finding_count_literal": 1, "sweep_run_id": "run-1", "recorded_at": "2026-09-10T00:00:00Z"},
        ])
        result = compute_transition("words", "python", store=store)
        assert result is None


class TestReadLiteralCount:
    """Unit tests for the TC-PKG-01-07-FIX helper directly."""

    def test_valid_zero_is_trusted(self):
        assert _read_literal_count({"finding_count_literal": 0}) == 0

    def test_valid_positive_is_trusted(self):
        assert _read_literal_count({"finding_count_literal": 5}) == 5

    def test_missing_key_is_none(self):
        assert _read_literal_count({}) is None

    def test_explicit_none_is_none(self):
        assert _read_literal_count({"finding_count_literal": None}) is None

    def test_negative_is_none(self):
        assert _read_literal_count({"finding_count_literal": -1}) is None

    def test_bool_is_none(self):
        """bool is a subclass of int in Python -- must not be accepted as a
        real count even though isinstance(True, int) is True."""
        assert _read_literal_count({"finding_count_literal": True}) is None

    def test_wrong_type_is_none(self):
        assert _read_literal_count({"finding_count_literal": "0"}) is None


class TestComputeTransitionMissingFindingCountLiteral:
    """TC-PKG-01-07-FIX (2026-09-17): independent review of
    PKGINSTALL-CONTENT-HEALING-STATUS-WRITEBACK found that a
    reconciliation-store row missing finding_count_literal entirely is
    schema-valid (schema_validators.validate_reconciliation_record() does
    not require it) but was silently read as "0 findings" by the pre-fix
    `row.get("finding_count_literal") or 0` logic -- directly contradicting
    this module's own "absence of data is never treated as zero findings"
    invariant, just one level down (per-row field, not per-product row
    count). These tests reproduce that exact gap and confirm the fix closes
    it without breaking the legitimate zero-evidence case."""

    def test_single_row_missing_finding_count_literal_returns_none(self, tmp_path):
        store = _reco.ReconciliationStore(repo_root=tmp_path)
        row = {
            "path": "a.md", "family": "words", "platform": "python", "site": "docs.aspose.org",
            "locale": "en", "representation": "shortcode_block", "collision_classification": None,
            "sweep_run_id": "run-1", "recorded_at": "2026-09-10T00:00:00Z",
            # finding_count_literal deliberately absent.
        }
        # Confirm the fixture really is schema-valid -- this is the exact
        # condition the independent review reproduced: a row that passes
        # validate_reconciliation_record() with zero errors despite omitting
        # finding_count_literal entirely.
        assert validate_reconciliation_record(row) == [], (
            "fixture must be schema-valid (no required-field error) to reproduce the real gap"
        )
        store.append_batch([row])

        result = compute_transition("words", "python", store=store)
        assert result is None, "a row that cannot attest to zero findings must never be read as zero"

    def test_realistic_refresh_knowledge_row_shape_among_zero_rows_returns_none(self, tmp_path):
        """Reproduces refresh_knowledge.py::_maybe_run_block_updater_dry_run()'s
        real row shape (site='knowledge', no finding_count_literal key, an
        extra block_updater_dry_run_summary field) landing alongside a
        genuine zero-finding literal-sweep row for the SAME product.
        Confirmed live (2026-09-17) this is not a hypothetical future
        writer: that call site is real, shipped code, and
        read_latest_for_product() does not distinguish rows by `site` or
        `path` -- both rows fold into the same product's evidence set."""
        store = _reco.ReconciliationStore(repo_root=tmp_path)
        store.append_batch([
            {"path": "content/docs.aspose.org/en/words/python/getting-started/installation.md",
             "family": "words", "platform": "python", "site": "docs.aspose.org", "locale": "en",
             "representation": "shortcode_block", "collision_classification": None,
             "finding_count_literal": 0, "sweep_run_id": "sweep-1", "recorded_at": "2026-09-10T00:00:00Z"},
            {"path": "knowledge/words/python/merged/install.md",
             "family": "words", "platform": "python", "site": "knowledge", "locale": "en",
             "representation": "literal", "collision_classification": None,
             "sweep_run_id": "refresh-knowledge-words-python-2026-09-11T00:00:00Z",
             "recorded_at": "2026-09-11T00:00:00Z",
             "block_updater_dry_run_summary": {
                 "files_updated": 1, "files_noop": 0, "human_review_required": [],
                 "generated_at": "2026-09-11T00:00:00Z",
             },
             # finding_count_literal deliberately absent, exactly like the real writer.
             },
        ])
        result = compute_transition("words", "python", store=store)
        assert result is None

    def test_explicit_none_finding_count_literal_returns_none(self, tmp_path):
        store = _reco.ReconciliationStore(repo_root=tmp_path)
        store.append_batch([
            {"path": "a.md", "family": "words", "platform": "python", "site": "docs.aspose.org",
             "locale": "en", "representation": "shortcode_block", "collision_classification": None,
             "finding_count_literal": None, "sweep_run_id": "run-1", "recorded_at": "2026-09-10T00:00:00Z"},
        ])
        result = compute_transition("words", "python", store=store)
        assert result is None

    def test_negative_finding_count_literal_returns_none(self, tmp_path):
        """Malformed data should never pass append_batch's own schema
        validation (it rejects negative counts), but compute_transition()
        must not blindly trust whatever is already on disk either -- e.g. a
        row written before a future schema tightening, or via any path that
        bypasses ReconciliationStore.append_batch(). Simulate that by
        corrupting the on-disk row directly."""
        store = _reco.ReconciliationStore(repo_root=tmp_path)
        store.append_batch([
            {"path": "a.md", "family": "words", "platform": "python", "site": "docs.aspose.org",
             "locale": "en", "representation": "shortcode_block", "collision_classification": None,
             "finding_count_literal": 0, "sweep_run_id": "run-1", "recorded_at": "2026-09-10T00:00:00Z"},
        ])
        corrupted = json.loads(store.path.read_text(encoding="utf-8"))
        corrupted["finding_count_literal"] = -1
        store.path.write_text(json.dumps(corrupted) + "\n", encoding="utf-8")

        result = compute_transition("words", "python", store=store)
        assert result is None

    def test_present_valid_zero_is_still_real_evidence(self, tmp_path):
        """Sanity check: the fix must not make a legitimately-present 0
        look like missing evidence -- only genuine absence/invalidity
        should refuse the transition, or the existing
        test_zero_literal_findings_across_all_rows_proposes_healed
        contract would silently break."""
        store = _reco.ReconciliationStore(repo_root=tmp_path)
        store.append_batch([
            {"path": "a.md", "family": "words", "platform": "python", "site": "docs.aspose.org",
             "locale": "en", "representation": "shortcode_block", "collision_classification": None,
             "finding_count_literal": 0, "sweep_run_id": "run-1", "recorded_at": "2026-09-10T00:00:00Z"},
        ])
        result = compute_transition("words", "python", store=store)
        assert result is not None
        assert result["to_status"] == "healed"


class TestFindPendingTransitions:
    def test_only_pending_entries_are_considered(self, tmp_path):
        store = _reco.ReconciliationStore(repo_root=tmp_path)
        store.append_batch([
            {"path": "a.md", "family": "words", "platform": "python", "site": "docs.aspose.org",
             "locale": "en", "representation": "shortcode_block", "collision_classification": None,
             "finding_count_literal": 0, "sweep_run_id": "run-1", "recorded_at": "2026-09-10T00:00:00Z"},
        ])
        data = {}
        data.update(_registry("words", "python", "pending"))
        data.update(_registry("cells", "net", "not_needed"))  # zero-findings evidence exists but status isn't pending
        store.append_batch([
            {"path": "b.md", "family": "cells", "platform": "net", "site": "docs.aspose.org",
             "locale": "en", "representation": "shortcode_block", "collision_classification": None,
             "finding_count_literal": 0, "sweep_run_id": "run-1", "recorded_at": "2026-09-10T00:00:00Z"},
        ])
        proposals = find_pending_transitions(data, store=store)
        assert len(proposals) == 1
        assert proposals[0]["family"] == "words"

    def test_skips_underscore_and_non_dict_entries(self, tmp_path):
        store = _reco.ReconciliationStore(repo_root=tmp_path)
        data = {"_comment": "not a family", "words": "not a dict either"}
        assert find_pending_transitions(data, store=store) == []


class TestRunReconciliationDryRun:
    def setup_method(self):
        rchs.configure()

    def teardown_method(self):
        rchs.configure()

    def test_dry_run_never_writes_the_registry(self, tmp_path):
        data = _registry("words", "python", "pending")
        registry_path = _write_registry(tmp_path, data)
        original_bytes = registry_path.read_text(encoding="utf-8")
        rchs.configure(repo_root=tmp_path)

        store = _reco.ReconciliationStore(repo_root=tmp_path)
        store.append_batch([
            {"path": "a.md", "family": "words", "platform": "python", "site": "docs.aspose.org",
             "locale": "en", "representation": "shortcode_block", "collision_classification": None,
             "finding_count_literal": 0, "sweep_run_id": "run-1", "recorded_at": "2026-09-10T00:00:00Z"},
        ])

        result = run_reconciliation(dry_run=True, store=store)

        assert result["wrote_changes"] is False
        assert len(result["proposals"]) == 1
        assert registry_path.read_text(encoding="utf-8") == original_bytes, "dry-run must never write"

    def test_no_proposals_is_a_clean_noop(self, tmp_path):
        data = _registry("words", "python", "pending")
        _write_registry(tmp_path, data)
        rchs.configure(repo_root=tmp_path)
        store = _reco.ReconciliationStore(repo_root=tmp_path)  # empty -- no evidence

        result = run_reconciliation(dry_run=True, store=store)
        assert result["proposals"] == []
        assert result["wrote_changes"] is False


class TestRunReconciliationExecuteGate:
    def setup_method(self):
        rchs.configure()

    def teardown_method(self):
        rchs.configure()

    def test_execute_refused_when_gating_taskcard_not_closed(self, tmp_path):
        data = _registry("words", "python", "pending")
        _write_registry(tmp_path, data)
        rchs.configure(repo_root=tmp_path)
        store = _reco.ReconciliationStore(repo_root=tmp_path)
        store.append_batch([
            {"path": "a.md", "family": "words", "platform": "python", "site": "docs.aspose.org",
             "locale": "en", "representation": "shortcode_block", "collision_classification": None,
             "finding_count_literal": 0, "sweep_run_id": "run-1", "recorded_at": "2026-09-10T00:00:00Z"},
        ])
        fake_taskcards = _FakeTaskcardStore(status="READY")

        try:
            run_reconciliation(dry_run=False, store=store, taskcard_store=fake_taskcards)
            assert False, "expected DeployTriggerNotClosedError"
        except DeployTriggerNotClosedError:
            pass

    def test_execute_refused_when_gating_taskcard_never_recorded(self, tmp_path):
        data = _registry("words", "python", "pending")
        _write_registry(tmp_path, data)
        rchs.configure(repo_root=tmp_path)
        store = _reco.ReconciliationStore(repo_root=tmp_path)
        store.append_batch([
            {"path": "a.md", "family": "words", "platform": "python", "site": "docs.aspose.org",
             "locale": "en", "representation": "shortcode_block", "collision_classification": None,
             "finding_count_literal": 0, "sweep_run_id": "run-1", "recorded_at": "2026-09-10T00:00:00Z"},
        ])
        fake_taskcards = _FakeTaskcardStore(status=None)

        try:
            run_reconciliation(dry_run=False, store=store, taskcard_store=fake_taskcards)
            assert False, "expected DeployTriggerNotClosedError"
        except DeployTriggerNotClosedError:
            pass

    def test_execute_with_zero_proposals_never_even_checks_the_gate(self, tmp_path):
        """Nothing to apply -- no need to consult (or fail loudly about) the
        gating taskcard at all."""
        data = _registry("words", "python", "pending")
        _write_registry(tmp_path, data)
        rchs.configure(repo_root=tmp_path)
        store = _reco.ReconciliationStore(repo_root=tmp_path)  # empty

        result = run_reconciliation(dry_run=False, store=store, taskcard_store=_FakeTaskcardStore(status="READY"))
        assert result["proposals"] == []
        assert result["wrote_changes"] is False

    def test_execute_applies_and_writes_when_gate_is_closed(self, tmp_path):
        data = _registry("words", "python", "pending")
        registry_path = _write_registry(tmp_path, data)
        rchs.configure(repo_root=tmp_path)
        store = _reco.ReconciliationStore(repo_root=tmp_path)
        store.append_batch([
            {"path": "a.md", "family": "words", "platform": "python", "site": "docs.aspose.org",
             "locale": "en", "representation": "shortcode_block", "collision_classification": None,
             "finding_count_literal": 0, "sweep_run_id": "run-1", "recorded_at": "2026-09-10T00:00:00Z"},
        ])
        fake_taskcards = _FakeTaskcardStore(status="CLOSED")

        result = run_reconciliation(
            dry_run=False, checked_at="2026-09-10", store=store, taskcard_store=fake_taskcards,
        )

        assert result["wrote_changes"] is True
        assert result["validation_errors"] == []
        written = json.loads(registry_path.read_text(encoding="utf-8"))
        entry = written["words"]["python"]
        assert entry["content_healing_status"] == "healed"
        assert entry["content_healing_status_set_at"] == "2026-09-10"
        assert "reconciliation-store row" in entry["content_healing_status_reason"]

    def test_written_registry_is_still_schema_valid(self, tmp_path):
        data = _registry("words", "python", "pending")
        registry_path = _write_registry(tmp_path, data)
        rchs.configure(repo_root=tmp_path)
        store = _reco.ReconciliationStore(repo_root=tmp_path)
        store.append_batch([
            {"path": "a.md", "family": "words", "platform": "python", "site": "docs.aspose.org",
             "locale": "en", "representation": "shortcode_block", "collision_classification": None,
             "finding_count_literal": 0, "sweep_run_id": "run-1", "recorded_at": "2026-09-10T00:00:00Z"},
        ])
        run_reconciliation(
            dry_run=False, checked_at="2026-09-10", store=store,
            taskcard_store=_FakeTaskcardStore(status="CLOSED"),
        )
        from package_registry_data import validate_package_registry
        written = json.loads(registry_path.read_text(encoding="utf-8"))
        assert validate_package_registry(written) == []
