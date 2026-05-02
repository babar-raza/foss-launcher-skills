"""
TC-S96-012: Tests for selective_revert.py
7 required test cases from the plan.
"""

import json
import pathlib
from unittest.mock import patch, MagicMock

import pytest

from commands.ops.selective_revert import (
    RevertLog,
    RevertRecord,
    apply_decision,
    write_revert_log,
)
from commands.ops.cleanroom_manifest import sha256_text


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ledger(entries):
    return {
        "run_id": "test-001",
        "baseline_git_sha": "abc1234",
        "generated_at": "2026-01-01T00:00:00Z",
        "counts": {},
        "entries": entries,
    }


def _manifest_with_file(path: str, content: str) -> dict:
    sha = sha256_text(content)
    return {
        "files": {
            path: {"sha256": sha, "size_bytes": len(content), "frontmatter": {}}
        }
    }


def _write_file(tmp_path: pathlib.Path, rel: str, content: str) -> pathlib.Path:
    fp = tmp_path / rel
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text(content, encoding="utf-8")
    return fp


# ---------------------------------------------------------------------------
# TC1: BAD_REVERT tracked file — git checkout baseline_git_sha called
# ---------------------------------------------------------------------------

def test_bad_revert_tracked_calls_git_checkout(tmp_path):
    """BAD_REVERT tracked file must call git checkout {baseline_git_sha} -- {path}."""
    rel = "content/reference.aspose.org/en/cells/java/Workbook.md"
    original = "---\ntitle: Workbook\n---\n# Original\n"
    _write_file(tmp_path, rel, "modified content")
    # Manifest entry proves the file was in baseline (tracked file)
    manifest = _manifest_with_file(rel, original)

    ledger = _ledger([{"path": rel, "verdict": "BAD_REVERT", "action_taken": "REVERTED_FROM_BASELINE", "result": "SUCCESS"}])

    with patch("commands.ops.selective_revert._git_checkout_baseline") as mock_git:
        mock_git.return_value = (True, None)
        log = apply_decision(ledger, "abc1234", tmp_path, dry_run=False, manifest_data=manifest)

    mock_git.assert_called_once_with(rel, "abc1234", tmp_path, False)
    assert log.records[0].action_taken == "REVERTED_FROM_BASELINE"
    assert log.records[0].result == "SUCCESS"


# ---------------------------------------------------------------------------
# TC2: BAD_REVERT new file — file deleted
# ---------------------------------------------------------------------------

def test_bad_revert_new_file_deleted(tmp_path):
    """BAD_REVERT new file (not in baseline) must be deleted from disk."""
    rel = "content/reference.aspose.org/en/cells/java/NewPage.md"
    fp = _write_file(tmp_path, rel, "new content added")
    assert fp.exists()

    # No manifest entry → file is new (ADDED)
    ledger = _ledger([{"path": rel, "verdict": "BAD_REVERT", "action_taken": "DELETED_NEW_FILE", "result": "SUCCESS"}])

    log = apply_decision(ledger, "abc1234", tmp_path, dry_run=False, manifest_data=None)

    assert log.records[0].action_taken == "DELETED_NEW_FILE"
    assert not fp.exists()


# ---------------------------------------------------------------------------
# TC3: RISKY without flag — reverted
# ---------------------------------------------------------------------------

def test_risky_review_without_flag_reverted(tmp_path):
    """RISKY_REVIEW without --keep-risky-pending → reverted."""
    rel = "content/reference.aspose.org/en/cells/java/Risky.md"
    original = "---\ntitle: Risky\n---\n# Original\n"
    _write_file(tmp_path, rel, "risky content")
    manifest = _manifest_with_file(rel, original)

    ledger = _ledger([{"path": rel, "verdict": "RISKY_REVIEW", "action_taken": "REVERTED_FROM_BASELINE", "result": "SUCCESS"}])

    with patch("commands.ops.selective_revert._git_checkout_baseline") as mock_git:
        mock_git.return_value = (True, None)
        log = apply_decision(ledger, "abc1234", tmp_path, keep_risky_pending=False, manifest_data=manifest)

    mock_git.assert_called_once()
    assert log.records[0].action_taken == "REVERTED_FROM_BASELINE"


# ---------------------------------------------------------------------------
# TC4: RISKY with --keep-risky-pending — left on disk
# ---------------------------------------------------------------------------

def test_risky_review_with_flag_left_pending(tmp_path):
    """RISKY_REVIEW with --keep-risky-pending → left on disk."""
    rel = "content/reference.aspose.org/en/cells/java/Risky.md"
    fp = _write_file(tmp_path, rel, "risky content")

    ledger = _ledger([{"path": rel, "verdict": "RISKY_REVIEW", "action_taken": "LEFT_PENDING", "result": "SKIPPED"}])

    with patch("commands.ops.selective_revert._git_checkout_baseline") as mock_git:
        log = apply_decision(ledger, "abc1234", tmp_path, keep_risky_pending=True)

    mock_git.assert_not_called()
    assert log.records[0].action_taken == "LEFT_PENDING"
    assert fp.exists()  # file not touched


# ---------------------------------------------------------------------------
# TC5: GOOD_KEEP — untouched
# ---------------------------------------------------------------------------

def test_good_keep_file_untouched(tmp_path):
    """GOOD_KEEP files must not be touched by selective revert."""
    rel = "content/reference.aspose.org/en/cells/java/Keep.md"
    fp = _write_file(tmp_path, rel, "good content")

    ledger = _ledger([{"path": rel, "verdict": "GOOD_KEEP", "action_taken": "KEPT", "result": "SKIPPED"}])

    with patch("commands.ops.selective_revert._git_checkout_baseline") as mock_git:
        log = apply_decision(ledger, "abc1234", tmp_path)

    mock_git.assert_not_called()
    assert log.records[0].action_taken == "KEPT"
    assert fp.read_text() == "good content"  # unchanged


# ---------------------------------------------------------------------------
# TC6: Verification after revert — sha256 check
# ---------------------------------------------------------------------------

def test_verification_after_revert_sha_check(tmp_path):
    """After revert, sha256 of restored file must match baseline."""
    rel = "content/reference.aspose.org/en/cells/java/Verify.md"
    original_content = "---\ntitle: Verify\n---\n# Original\n"
    sha = sha256_text(original_content)

    # Write the "reverted" content (simulating git checkout restoring it)
    fp = _write_file(tmp_path, rel, original_content)

    manifest = _manifest_with_file(rel, original_content)
    ledger = _ledger([{"path": rel, "verdict": "BAD_REVERT", "action_taken": "REVERTED_FROM_BASELINE", "result": "SUCCESS"}])

    with patch("commands.ops.selective_revert._git_checkout_baseline") as mock_git:
        mock_git.return_value = (True, None)
        log = apply_decision(ledger, "abc1234", tmp_path, manifest_data=manifest)

    record = log.records[0]
    assert record.result == "SUCCESS"
    # verified=True because the sha of the file matches baseline after mocked revert
    assert record.verified is True


# ---------------------------------------------------------------------------
# TC7: Dry-run — no changes
# ---------------------------------------------------------------------------

def test_dry_run_no_changes_made(tmp_path):
    """Dry-run mode must not modify any files or call git."""
    rel_revert = "content/reference.aspose.org/en/cells/java/RevertMe.md"
    rel_delete = "content/reference.aspose.org/en/cells/java/DeleteMe.md"
    original = "---\ntitle: RevertMe\n---\n# Original\n"

    fp_revert = _write_file(tmp_path, rel_revert, "to be reverted")
    fp_delete = _write_file(tmp_path, rel_delete, "to be deleted")
    # rel_revert is tracked; rel_delete is new (no manifest entry)
    manifest = _manifest_with_file(rel_revert, original)

    ledger = _ledger([
        {"path": rel_revert, "verdict": "BAD_REVERT", "action_taken": "REVERTED_FROM_BASELINE", "result": "SUCCESS"},
        {"path": rel_delete, "verdict": "BAD_REVERT", "action_taken": "DELETED_NEW_FILE", "result": "SUCCESS"},
    ])

    with patch("commands.ops.selective_revert._git_checkout_baseline") as mock_git:
        mock_git.return_value = (True, None)
        log = apply_decision(ledger, "abc1234", tmp_path, dry_run=True, manifest_data=manifest)

    # Files must still exist (dry run = no changes)
    assert fp_revert.exists()
    assert fp_delete.exists()
    assert log.dry_run is True
    # git checkout called with dry_run=True for the tracked file
    mock_git.assert_called_once_with(rel_revert, "abc1234", tmp_path, True)


# ---------------------------------------------------------------------------
# TC8: Never uses HEAD for revert
# ---------------------------------------------------------------------------

def test_revert_uses_baseline_sha_not_head(tmp_path):
    """Revert must use baseline_git_sha, NEVER 'HEAD'."""
    rel = "content/reference.aspose.org/en/cells/java/Page.md"
    original = "---\ntitle: Page\n---\n# Original\n"
    _write_file(tmp_path, rel, "modified")
    manifest = _manifest_with_file(rel, original)

    ledger = _ledger([{"path": rel, "verdict": "BAD_REVERT", "action_taken": "REVERTED_FROM_BASELINE", "result": "SUCCESS"}])
    sha = "deadbeef1234567"

    with patch("commands.ops.selective_revert._git_checkout_baseline") as mock_git:
        mock_git.return_value = (True, None)
        apply_decision(ledger, sha, tmp_path, manifest_data=manifest)

    call_args = mock_git.call_args
    assert call_args[0][1] == sha  # second positional arg is baseline_git_sha
    assert call_args[0][1] != "HEAD"


# ---------------------------------------------------------------------------
# Write log test
# ---------------------------------------------------------------------------

def test_write_revert_log_produces_json(tmp_path):
    log = RevertLog(
        run_id="test-log", baseline_git_sha="abc",
        generated_at="2026-01-01T00:00:00Z",
        dry_run=False, keep_risky_pending=False, keep_unclear_pending=False,
        records=[
            RevertRecord(path="foo.md", verdict="BAD_REVERT",
                         action_taken="REVERTED_FROM_BASELINE",
                         method="git checkout abc -- foo.md",
                         result="SUCCESS", verified=True)
        ]
    )
    output = tmp_path / "revert-log.json"
    write_revert_log(log, output)
    assert output.exists()
    data = json.loads(output.read_text())
    assert data["run_id"] == "test-log"
    assert len(data["records"]) == 1
    assert data["records"][0]["action_taken"] == "REVERTED_FROM_BASELINE"
