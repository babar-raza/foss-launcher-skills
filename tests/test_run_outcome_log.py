"""Tests for run_outcome_log.py — JSONL outcome tracking."""

from __future__ import annotations

import json
import pytest
from pathlib import Path

from scripts.pipeline.commands.ops.run_outcome_log import (
    log_outcome,
    read_outcomes,
    summarize_run,
    checkpoint_run,
    resume_from_checkpoint,
    VALID_STATUSES,
)


class TestLogOutcome:
    """Tests for log_outcome function."""

    def test_log_outcome_creates_file(self, tmp_path):
        """Happy path: creates log file and writes one entry."""
        log_file = tmp_path / "outcomes.jsonl"
        result_path = log_outcome(
            "S-21", "success",
            duration_ms=1200,
            retry_count=0,
            log_path=log_file,
        )
        assert result_path == log_file
        assert log_file.exists()

        lines = log_file.read_text().strip().split("\n")
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["skill_id"] == "S-21"
        assert entry["status"] == "success"
        assert entry["duration_ms"] == 1200
        assert entry["retry_count"] == 0
        assert "ts" in entry
        assert "error" not in entry
        assert "correlation_id" not in entry

    def test_log_outcome_appends_jsonl(self, tmp_path):
        """Multiple calls append to the same file."""
        log_file = tmp_path / "outcomes.jsonl"
        log_outcome("S-21", "success", log_path=log_file)
        log_outcome("S-26", "failure", error="timeout", log_path=log_file)
        log_outcome("S-20", "partial", retry_count=2, log_path=log_file)

        lines = log_file.read_text().strip().split("\n")
        assert len(lines) == 3

        entries = [json.loads(line) for line in lines]
        assert entries[0]["skill_id"] == "S-21"
        assert entries[1]["skill_id"] == "S-26"
        assert entries[1]["error"] == "timeout"
        assert entries[2]["skill_id"] == "S-20"
        assert entries[2]["retry_count"] == 2

    def test_log_outcome_rejects_invalid_status(self, tmp_path):
        """Invalid status raises ValueError."""
        with pytest.raises(ValueError, match="Invalid status"):
            log_outcome("S-21", "invalid_status", log_path=tmp_path / "out.jsonl")

    def test_valid_statuses(self):
        """All expected statuses are in VALID_STATUSES."""
        expected = {"success", "failure", "partial", "skipped", "exhausted"}
        assert VALID_STATUSES == expected

    def test_log_outcome_includes_correlation_id(self, tmp_path):
        """correlation_id is stored in the entry when provided."""
        log_file = tmp_path / "outcomes.jsonl"
        log_outcome("S-21", "success", correlation_id="run-abc123", log_path=log_file)

        entry = json.loads(log_file.read_text().strip())
        assert entry["correlation_id"] == "run-abc123"

    def test_log_outcome_omits_correlation_id_when_none(self, tmp_path):
        """correlation_id is omitted when not provided."""
        log_file = tmp_path / "outcomes.jsonl"
        log_outcome("S-21", "success", log_path=log_file)

        entry = json.loads(log_file.read_text().strip())
        assert "correlation_id" not in entry


class TestReadOutcomes:
    """Tests for read_outcomes function."""

    def test_read_outcomes_returns_recent(self, tmp_path):
        """Read last_n entries from log."""
        log_file = tmp_path / "outcomes.jsonl"
        for i in range(10):
            log_outcome(f"S-{i}", "success", log_path=log_file)

        recent = read_outcomes(last_n=3, log_path=log_file)
        assert len(recent) == 3
        assert recent[0]["skill_id"] == "S-7"
        assert recent[2]["skill_id"] == "S-9"

    def test_read_outcomes_empty_file(self, tmp_path):
        """Empty or missing file returns empty list."""
        assert read_outcomes(log_path=tmp_path / "nonexistent.jsonl") == []

        empty_file = tmp_path / "empty.jsonl"
        empty_file.write_text("")
        assert read_outcomes(log_path=empty_file) == []

    def test_read_outcomes_all_when_fewer_than_limit(self, tmp_path):
        """Returns all entries when fewer than last_n exist."""
        log_file = tmp_path / "outcomes.jsonl"
        log_outcome("S-1", "success", log_path=log_file)
        log_outcome("S-2", "failure", log_path=log_file)

        results = read_outcomes(last_n=100, log_path=log_file)
        assert len(results) == 2


class TestSummarizeRun:
    """Tests for summarize_run function."""

    def test_summarize_run_empty_log(self, tmp_path):
        """Returns zeroed summary when log does not exist."""
        summary = summarize_run("run-xyz", log_path=tmp_path / "nonexistent.jsonl")
        assert summary["correlation_id"] == "run-xyz"
        assert summary["total"] == 0
        assert summary["success"] == 0
        assert summary["skills"] == []
        assert summary["errors"] == []

    def test_summarize_run_groups_by_correlation_id(self, tmp_path):
        """Only entries matching the correlation_id are included."""
        log_file = tmp_path / "outcomes.jsonl"
        log_outcome("S-21", "success", duration_ms=500, correlation_id="run-A", log_path=log_file)
        log_outcome("S-26", "failure", error="timeout", correlation_id="run-A", log_path=log_file)
        log_outcome("S-20", "success", duration_ms=200, correlation_id="run-B", log_path=log_file)

        summary = summarize_run("run-A", log_path=log_file)
        assert summary["total"] == 2
        assert summary["success"] == 1
        assert summary["failure"] == 1
        assert summary["duration_ms_total"] == 500
        assert "S-21" in summary["skills"]
        assert "S-26" in summary["skills"]
        assert len(summary["errors"]) == 1
        assert summary["errors"][0]["skill_id"] == "S-26"
        assert summary["errors"][0]["error"] == "timeout"

    def test_summarize_run_excludes_other_runs(self, tmp_path):
        """run-B entries are excluded from run-A summary."""
        log_file = tmp_path / "outcomes.jsonl"
        log_outcome("S-20", "success", correlation_id="run-B", log_path=log_file)

        summary = summarize_run("run-A", log_path=log_file)
        assert summary["total"] == 0

    def test_summarize_run_retry_count_total(self, tmp_path):
        """retry_count_total accumulates correctly."""
        log_file = tmp_path / "outcomes.jsonl"
        log_outcome("S-21", "success", retry_count=2, correlation_id="run-C", log_path=log_file)
        log_outcome("S-26", "success", retry_count=1, correlation_id="run-C", log_path=log_file)

        summary = summarize_run("run-C", log_path=log_file)
        assert summary["retry_count_total"] == 3

    def test_summarize_run_entries_without_correlation_id_excluded(self, tmp_path):
        """Entries without a correlation_id are excluded from any summarize_run call."""
        log_file = tmp_path / "outcomes.jsonl"
        log_outcome("S-21", "success", log_path=log_file)  # no correlation_id

        summary = summarize_run("run-X", log_path=log_file)
        assert summary["total"] == 0


class TestCheckpointResume:
    """Tests for checkpoint_run and resume_from_checkpoint."""

    def test_checkpoint_creates_file(self, tmp_path):
        """checkpoint_run creates a JSON file in the checkpoint directory."""
        checkpoint_dir = tmp_path / "checkpoints"
        state = {"last_skill": "S-26", "page": "getting-started.md", "retry": 1}

        path = checkpoint_run("run-abc", state, checkpoint_dir=checkpoint_dir)
        assert path.exists()
        assert path.suffix == ".json"

        record = json.loads(path.read_text())
        assert record["correlation_id"] == "run-abc"
        assert record["state"] == state
        assert "checkpointed_at" in record

    def test_resume_returns_state(self, tmp_path):
        """resume_from_checkpoint returns the stored state dict."""
        checkpoint_dir = tmp_path / "checkpoints"
        state = {"last_skill": "S-21", "completed": ["S-18", "S-19"]}

        checkpoint_run("run-resume-test", state, checkpoint_dir=checkpoint_dir)
        restored = resume_from_checkpoint("run-resume-test", checkpoint_dir=checkpoint_dir)

        assert restored == state

    def test_resume_returns_none_when_missing(self, tmp_path):
        """resume_from_checkpoint returns None if no checkpoint exists."""
        checkpoint_dir = tmp_path / "checkpoints"
        result = resume_from_checkpoint("nonexistent-run", checkpoint_dir=checkpoint_dir)
        assert result is None

    def test_checkpoint_overwrites_existing(self, tmp_path):
        """Second checkpoint call overwrites the first for the same correlation_id."""
        checkpoint_dir = tmp_path / "checkpoints"
        checkpoint_run("run-overwrite", {"step": 1}, checkpoint_dir=checkpoint_dir)
        checkpoint_run("run-overwrite", {"step": 2}, checkpoint_dir=checkpoint_dir)

        restored = resume_from_checkpoint("run-overwrite", checkpoint_dir=checkpoint_dir)
        assert restored == {"step": 2}

    def test_checkpoint_safe_id_for_slashes(self, tmp_path):
        """Slashes in correlation_id are replaced to create a safe filename."""
        checkpoint_dir = tmp_path / "checkpoints"
        state = {"k": "v"}
        path = checkpoint_run("family/platform/run-1", state, checkpoint_dir=checkpoint_dir)

        assert "/" not in path.name
        restored = resume_from_checkpoint("family/platform/run-1", checkpoint_dir=checkpoint_dir)
        assert restored == state

    def test_resume_after_partial_failure(self, tmp_path):
        """Full checkpoint/resume cycle simulating resume after partial failure."""
        checkpoint_dir = tmp_path / "checkpoints"
        log_file = tmp_path / "outcomes.jsonl"
        correlation_id = "run-partial-test"

        # Simulate: S-18 succeeded, S-19 failed — checkpoint before retry
        log_outcome("S-18", "success", duration_ms=300, correlation_id=correlation_id, log_path=log_file)
        log_outcome("S-19", "failure", error="network error", correlation_id=correlation_id, log_path=log_file)
        checkpoint_run(correlation_id, {"last_completed": "S-18", "failed": "S-19"}, checkpoint_dir=checkpoint_dir)

        # Simulate process restart — resume
        restored = resume_from_checkpoint(correlation_id, checkpoint_dir=checkpoint_dir)
        assert restored is not None
        assert restored["failed"] == "S-19"
        assert restored["last_completed"] == "S-18"

        # Verify the log still has the pre-failure entries
        summary = summarize_run(correlation_id, log_path=log_file)
        assert summary["total"] == 2
        assert summary["failure"] == 1
