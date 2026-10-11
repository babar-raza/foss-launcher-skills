"""Tests for evidence/apply_gate.py — ClaimPlan apply gate (TC-CLAIM-09).

All tests use tmp_path; no real content/ or knowledge/ files are read.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from evidence.apply_gate import (
    ApplyGateError,
    validate_plan,
    write_ledger_entry,
    _build_ledger_entry,
    _get_repo_head,
    ApplyResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_plan(
    plan_id: str = "plan-test-001",
    repo_head: str = "abc123",
    claims_hash: str = "hash001",
    knowledge_repo_sha: str = "sha-001",
    subdomain: str = "reference.aspose.org",
    family: str = "cells",
    platform: str = "java",
    records: list | None = None,
) -> dict:
    return {
        "plan_id": plan_id,
        "repo_head": repo_head,
        "claims_hash": claims_hash,
        "knowledge_repo_sha": knowledge_repo_sha,
        "subdomain": subdomain,
        "family": family,
        "platform": platform,
        "records": records or [],
    }


def _make_knowledge(tmp_path: Path, claims: list[dict],
                    family: str = "cells", platform: str = "java") -> Path:
    merged = tmp_path / family / platform / "merged"
    merged.mkdir(parents=True)
    (merged / "api_surface.json").write_text("[]", encoding="utf-8")
    import yaml
    (merged / "model.yaml").write_text(
        yaml.dump({"version": "1.0", "repo_sha": "sha-001"}),
        encoding="utf-8",
    )
    claims_bytes = json.dumps(claims).encode("utf-8")
    (merged / "claims.json").write_bytes(claims_bytes)
    return tmp_path  # knowledge_root


def _claims_hash(claims: list[dict]) -> str:
    return hashlib.sha256(json.dumps(claims).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# validate_plan tests
# ---------------------------------------------------------------------------

class TestValidatePlan:
    def test_valid_plan_passes(self, tmp_path):
        """A well-formed plan with matching HEAD and claims_hash should pass."""
        claims = [{"claim_id": "CLM-cells-abc"}]
        knowledge_root = _make_knowledge(tmp_path / "k", claims)
        ch = _claims_hash(claims)
        plan = _make_plan(claims_hash=ch, repo_head="")  # empty HEAD = skip HEAD check

        # Should not raise
        validate_plan(plan, knowledge_root, max_files=20,
                      repo_root=tmp_path)

    def test_refuses_if_repo_head_changed(self, tmp_path):
        """Raises ApplyGateError when repo HEAD changed since plan."""
        claims = [{"claim_id": "CLM-cells-abc"}]
        knowledge_root = _make_knowledge(tmp_path / "k", claims)
        ch = _claims_hash(claims)
        plan = _make_plan(claims_hash=ch, repo_head="old-head")

        with patch("evidence.apply_gate._get_repo_head", return_value="new-head"):
            with pytest.raises(ApplyGateError, match="Repo HEAD changed"):
                validate_plan(plan, knowledge_root, max_files=20,
                              repo_root=tmp_path)

    def test_refuses_if_claims_hash_changed(self, tmp_path):
        """Raises ApplyGateError when claims_hash changed since plan."""
        old_claims = [{"claim_id": "CLM-cells-old"}]
        new_claims = [{"claim_id": "CLM-cells-new"}]
        knowledge_root = _make_knowledge(tmp_path / "k", new_claims)
        old_ch = _claims_hash(old_claims)
        plan = _make_plan(claims_hash=old_ch, repo_head="")  # empty = skip HEAD check

        with pytest.raises(ApplyGateError, match="claims_hash changed"):
            validate_plan(plan, knowledge_root, max_files=20,
                          repo_root=tmp_path)

    def test_refuses_if_no_subdomain_in_plan(self, tmp_path):
        """Raises ApplyGateError when plan has no subdomain."""
        claims = [{"claim_id": "CLM-cells-abc"}]
        knowledge_root = _make_knowledge(tmp_path / "k", claims)
        ch = _claims_hash(claims)
        plan = _make_plan(claims_hash=ch, repo_head="", subdomain="")

        with pytest.raises(ApplyGateError, match="without --subdomain"):
            validate_plan(plan, knowledge_root, max_files=20,
                          repo_root=tmp_path)

    def test_refuses_if_block_actions_present(self, tmp_path):
        """Raises ApplyGateError when any claim has BLOCK policy_status."""
        claims = [{"claim_id": "CLM-cells-abc"}]
        knowledge_root = _make_knowledge(tmp_path / "k", claims)
        ch = _claims_hash(claims)
        records = [{
            "filepath": str(tmp_path / "test.md"),
            "action": "WOULD_UPDATE",
            "proposed_claims": [
                {"claim_id": "CLM-unknown", "policy_status": "BLOCK",
                 "policy_reason": "Unknown claim ID"}
            ],
        }]
        plan = _make_plan(claims_hash=ch, repo_head="", records=records)

        with pytest.raises(ApplyGateError, match="BLOCK policy action"):
            validate_plan(plan, knowledge_root, max_files=20,
                          repo_root=tmp_path)

    def test_refuses_if_file_count_exceeds_max(self, tmp_path):
        """Raises ApplyGateError when write count exceeds --max-files."""
        claims = [{"claim_id": "CLM-cells-abc"}]
        knowledge_root = _make_knowledge(tmp_path / "k", claims)
        ch = _claims_hash(claims)
        # 5 WOULD_UPDATE records
        records = [
            {"filepath": str(tmp_path / f"file{i}.md"),
             "action": "WOULD_UPDATE", "proposed_claims": []}
            for i in range(5)
        ]
        plan = _make_plan(claims_hash=ch, repo_head="", records=records)

        with pytest.raises(ApplyGateError, match="max-files"):
            validate_plan(plan, knowledge_root, max_files=3,
                          repo_root=tmp_path)

    def test_refuses_missing_required_fields(self, tmp_path):
        """Raises ApplyGateError when plan is missing required fields."""
        knowledge_root = _make_knowledge(tmp_path / "k", [])
        incomplete_plan = {"plan_id": "test"}

        with pytest.raises(ApplyGateError, match="missing required field"):
            validate_plan(incomplete_plan, knowledge_root, max_files=20,
                          repo_root=tmp_path)

    def test_skips_files_where_frontmatter_unparseable(self, tmp_path):
        """Raises ApplyGateError when a target file has malformed frontmatter."""
        claims = [{"claim_id": "CLM-cells-abc"}]
        knowledge_root = _make_knowledge(tmp_path / "k", claims)
        ch = _claims_hash(claims)

        bad_file = tmp_path / "bad.md"
        bad_file.write_text("no frontmatter here", encoding="utf-8")

        records = [{
            "filepath": str(bad_file),
            "action": "WOULD_UPDATE",
            "proposed_claims": [],
        }]
        plan = _make_plan(claims_hash=ch, repo_head="", records=records)

        with pytest.raises(ApplyGateError, match="malformed frontmatter"):
            validate_plan(plan, knowledge_root, max_files=20,
                          repo_root=tmp_path)


# ---------------------------------------------------------------------------
# Run ledger tests
# ---------------------------------------------------------------------------

class TestRunLedger:
    def test_apply_writes_run_ledger_entry(self, tmp_path):
        """write_ledger_entry must create and append to ledger file."""
        ledger_path = tmp_path / "runs" / "ledger" / "claim-apply-ledger.json"
        entry = {"plan_id": "test-001", "apply_result": "PASS", "files_written": 3}

        write_ledger_entry(entry, ledger_path)

        assert ledger_path.exists()
        data = json.loads(ledger_path.read_text(encoding="utf-8"))
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["plan_id"] == "test-001"

    def test_ledger_appends_multiple_entries(self, tmp_path):
        """write_ledger_entry appends; does not overwrite existing entries."""
        ledger_path = tmp_path / "ledger.json"
        write_ledger_entry({"run": 1}, ledger_path)
        write_ledger_entry({"run": 2}, ledger_path)

        data = json.loads(ledger_path.read_text(encoding="utf-8"))
        assert len(data) == 2
        assert data[0]["run"] == 1
        assert data[1]["run"] == 2

    def test_build_ledger_entry_contains_required_fields(self, tmp_path):
        """_build_ledger_entry must include all required ledger fields."""
        plan = _make_plan(plan_id="plan-001", repo_head="abc",
                          claims_hash="hash001", subdomain="reference.aspose.org")
        result = ApplyResult(
            plan_id="plan-001", subdomain="reference.aspose.org",
            files_written=5, files_skipped=2, warn_count=1, blocked_count=0,
            apply_status="PASS",
        )
        entry = _build_ledger_entry(plan, result, "attach_evidence --apply-claim-plan plan.json")

        required_keys = {
            "claim_plan_id", "repo_head", "knowledge_repo_sha", "claims_hash",
            "subdomain", "file_count", "files_written", "files_skipped",
            "warn_count", "blocked_count", "applied_by_command", "apply_result",
            "applied_at",
        }
        for key in required_keys:
            assert key in entry, f"Ledger entry missing required field: {key!r}"

    def test_dry_run_plan_includes_plan_id_and_hashes(self, tmp_path):
        """ClaimPlan format from TC-CLAIM-03 must include plan_id and claims_hash."""
        # Verify via validate_plan: a plan lacking these fields raises ApplyGateError
        knowledge_root = _make_knowledge(tmp_path / "k", [])
        incomplete = {"records": [], "subdomain": "reference.aspose.org"}

        with pytest.raises(ApplyGateError, match="plan_id"):
            validate_plan(incomplete, knowledge_root, max_files=20,
                          repo_root=tmp_path)
