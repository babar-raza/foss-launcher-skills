"""Tests for autonomous_runner.py — dry-run enforcement, next-action schema, stop reasons."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_PIPELINE_ROOT = Path(__file__).resolve().parents[1] / "scripts" / "pipeline"
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

from lib.product_state import Phase, ProductState, StopReason
from commands.ops.autonomous_runner import (
    PHASE_ACTIONS,
    RUNNER_SCHEMA_VERSION,
    append_audit_log,
    determine_next_action,
    main,
)


class TestNextAction:
    def test_discovered_suggests_scout(self):
        state = ProductState(family="pdf", platform="go", phase=Phase.DISCOVERED.value)
        action = determine_next_action(state)
        assert action["action_id"] == "scout"
        assert action["dry_run"] is True
        assert "repo-scout" in action["command"]

    def test_facts_extracted_suggests_verify(self):
        state = ProductState(family="pdf", platform="go", phase=Phase.FACTS_EXTRACTED.value)
        action = determine_next_action(state)
        assert action["action_id"] == "verify-facts"
        assert "truth-merge" in action["command"]

    def test_terminal_state_stops(self):
        state = ProductState(
            family="pdf", platform="go",
            phase=Phase.QUARANTINED.value,
            stop_reason=StopReason.QUARANTINED_REPEATED_FAILURE.value,
        )
        action = determine_next_action(state)
        assert action["action_id"] == "stop"
        assert action["command"] is None
        assert action["dry_run"] is True

    def test_ready_for_review_stops(self):
        state = ProductState(
            family="pdf", platform="go",
            phase=Phase.READY_FOR_REVIEW.value,
            stop_reason=StopReason.READY_FOR_AGENT_REVIEW.value,
        )
        action = determine_next_action(state)
        assert action["action_id"] == "stop"

    def test_schema_version(self):
        state = ProductState(family="pdf", platform="go")
        action = determine_next_action(state)
        assert action["schema_version"] == RUNNER_SCHEMA_VERSION


class TestNextActionSchema:
    def test_all_actionable_phases_have_commands(self):
        """Every non-terminal phase should produce a command."""
        terminal = {Phase.READY_FOR_REVIEW.value, Phase.BLOCKED_EXTERNAL.value,
                    Phase.QUARANTINED.value, Phase.RETRYABLE_FAILURE.value,
                    Phase.AGENT_REVIEWED.value, Phase.REPAIR_REQUIRED.value,
                    Phase.APPROVED_FOR_DRAFT_WRITE.value, Phase.DRAFT_WRITTEN.value}
        for phase in Phase:
            if phase.value in terminal:
                continue
            state = ProductState(family="pdf", platform="go", phase=phase.value)
            action = determine_next_action(state)
            assert action["command"] is not None, f"No command for phase {phase.value}"

    def test_all_actions_have_family_platform(self):
        for phase in Phase:
            state = ProductState(family="pdf", platform="go", phase=phase.value)
            action = determine_next_action(state)
            assert action["family"] == "pdf"
            assert action["platform"] == "go"


class TestAuditLog:
    def test_append_creates_file(self, tmp_path):
        log_path = tmp_path / "audit.jsonl"
        append_audit_log(log_path, {"event": "test", "value": 42})
        assert log_path.exists()
        lines = log_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["event"] == "test"
        assert "timestamp" in entry

    def test_append_multiple(self, tmp_path):
        log_path = tmp_path / "audit.jsonl"
        append_audit_log(log_path, {"event": "first"})
        append_audit_log(log_path, {"event": "second"})
        lines = log_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2


class TestDryRunEnforcement:
    def test_cli_requires_dry_run(self, tmp_path):
        """CLI should fail without --dry-run."""
        with pytest.raises(SystemExit) as exc_info:
            main(["--family", "pdf", "--platform", "go",
                  "--output-dir", str(tmp_path)])
        assert exc_info.value.code == 2

    def test_cli_with_dry_run(self, tmp_path):
        result = main(["--dry-run", "--family", "pdf", "--platform", "go",
                       "--output-dir", str(tmp_path)])
        assert result == 0
        assert (tmp_path / "next_action.json").exists()
        assert (tmp_path / "audit_log.jsonl").exists()

    def test_output_files_valid_json(self, tmp_path):
        main(["--dry-run", "--family", "pdf", "--platform", "go",
              "--output-dir", str(tmp_path)])
        action = json.loads((tmp_path / "next_action.json").read_text(encoding="utf-8"))
        assert action["dry_run"] is True
        assert action["family"] == "pdf"
