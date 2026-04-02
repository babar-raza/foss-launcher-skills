"""Tests for scripts/ops_log.py — append-only JSONL operation log."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

# Ensure scripts/ is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from ops_log import log_entry, read_log, VALID_STATUSES


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _log(tmp_path, **kwargs):
    """Shorthand: call log_entry with a tmp log path."""
    kwargs.setdefault("log_path", tmp_path / "ops.log")
    return log_entry(**kwargs)


# ---------------------------------------------------------------------------
# 1. log_entry creates the file
# ---------------------------------------------------------------------------

def test_log_entry_creates_file(tmp_path):
    log_file = tmp_path / "ops.log"
    assert not log_file.exists()
    result = log_entry("ground-check", "PASS", log_path=log_file)
    assert log_file.exists()
    assert result == log_file


# ---------------------------------------------------------------------------
# 2. log_entry appends a valid JSON line
# ---------------------------------------------------------------------------

def test_log_entry_writes_valid_json(tmp_path):
    log_file = tmp_path / "ops.log"
    log_entry("ground-check", "PASS", log_path=log_file)
    lines = log_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert isinstance(parsed, dict)


# ---------------------------------------------------------------------------
# 3. Multiple calls append multiple lines (not overwrite)
# ---------------------------------------------------------------------------

def test_multiple_calls_append(tmp_path):
    log_file = tmp_path / "ops.log"
    for status in ("PASS", "FAIL", "WARN"):
        log_entry("skill-x", status, log_path=log_file)
    lines = log_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3


# ---------------------------------------------------------------------------
# 4. Entry contains all required fields
# ---------------------------------------------------------------------------

def test_entry_has_all_required_fields(tmp_path):
    log_file = tmp_path / "ops.log"
    log_entry(
        "launch-product", "PASS",
        family="words", platform="python",
        log_path=log_file,
    )
    entry = json.loads(log_file.read_text(encoding="utf-8").splitlines()[0])
    for field in ("ts", "skill", "family", "platform", "status", "artifacts_written", "errors"):
        assert field in entry, f"Missing field: {field}"


# ---------------------------------------------------------------------------
# 5. read_log returns list with correct count
# ---------------------------------------------------------------------------

def test_read_log_count(tmp_path):
    log_file = tmp_path / "ops.log"
    for i in range(5):
        log_entry(f"skill-{i}", "PASS", log_path=log_file)
    entries = read_log(log_file)
    assert len(entries) == 5


# ---------------------------------------------------------------------------
# 6. log_path param overrides default location
# ---------------------------------------------------------------------------

def test_log_path_override(tmp_path):
    custom = tmp_path / "custom" / "my.log"
    log_entry("path-guard", "WARN", log_path=custom)
    assert custom.exists()
    entries = read_log(custom)
    assert len(entries) == 1


# ---------------------------------------------------------------------------
# 7. All valid status values are preserved
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("status", ["PASS", "FAIL", "WARN", "ERROR", "ESCALATE"])
def test_status_values_preserved(tmp_path, status):
    log_file = tmp_path / "ops.log"
    log_entry("skill-x", status, log_path=log_file)
    entry = read_log(log_file)[0]
    assert entry["status"] == status


# ---------------------------------------------------------------------------
# 8. artifacts_written defaults to []
# ---------------------------------------------------------------------------

def test_artifacts_written_default_empty(tmp_path):
    log_file = tmp_path / "ops.log"
    log_entry("skill-x", "PASS", log_path=log_file)
    entry = read_log(log_file)[0]
    assert entry["artifacts_written"] == []


# ---------------------------------------------------------------------------
# 9. errors defaults to []
# ---------------------------------------------------------------------------

def test_errors_default_empty(tmp_path):
    log_file = tmp_path / "ops.log"
    log_entry("skill-x", "PASS", log_path=log_file)
    entry = read_log(log_file)[0]
    assert entry["errors"] == []


# ---------------------------------------------------------------------------
# 10. Timestamp is valid ISO-8601 with timezone info
# ---------------------------------------------------------------------------

def test_timestamp_is_valid_iso8601(tmp_path):
    log_file = tmp_path / "ops.log"
    log_entry("ground-check", "PASS", log_path=log_file)
    entry = read_log(log_file)[0]
    ts = entry["ts"]
    # Must parse without error and have tzinfo
    parsed = datetime.fromisoformat(ts)
    assert parsed.tzinfo is not None


# ---------------------------------------------------------------------------
# 11. skill and family/platform are stored correctly
# ---------------------------------------------------------------------------

def test_skill_family_platform_stored(tmp_path):
    log_file = tmp_path / "ops.log"
    log_entry(
        "launch-product", "PASS",
        family="cells", platform="net",
        log_path=log_file,
    )
    entry = read_log(log_file)[0]
    assert entry["skill"] == "launch-product"
    assert entry["family"] == "cells"
    assert entry["platform"] == "net"


# ---------------------------------------------------------------------------
# 12. artifacts_written list is persisted
# ---------------------------------------------------------------------------

def test_artifacts_written_list_persisted(tmp_path):
    log_file = tmp_path / "ops.log"
    artifacts = ["reports/gc/words-python-20260331.md", "reports/gc/summary.json"]
    log_entry("ground-check", "PASS", artifacts_written=artifacts, log_path=log_file)
    entry = read_log(log_file)[0]
    assert entry["artifacts_written"] == artifacts


# ---------------------------------------------------------------------------
# 13. errors list is persisted
# ---------------------------------------------------------------------------

def test_errors_list_persisted(tmp_path):
    log_file = tmp_path / "ops.log"
    errors = ["stale model detected", "missing claim CLM-007"]
    log_entry("ground-check", "FAIL", errors=errors, log_path=log_file)
    entry = read_log(log_file)[0]
    assert entry["errors"] == errors


# ---------------------------------------------------------------------------
# 14. read_log on missing file returns empty list
# ---------------------------------------------------------------------------

def test_read_log_missing_file_returns_empty(tmp_path):
    result = read_log(tmp_path / "does_not_exist.log")
    assert result == []


# ---------------------------------------------------------------------------
# 15. Invalid status raises ValueError
# ---------------------------------------------------------------------------

def test_invalid_status_raises(tmp_path):
    with pytest.raises(ValueError, match="Invalid status"):
        log_entry("skill-x", "UNKNOWN", log_path=tmp_path / "ops.log")


# ---------------------------------------------------------------------------
# 16. Parent directories are created automatically
# ---------------------------------------------------------------------------

def test_parent_dirs_created(tmp_path):
    deep = tmp_path / "a" / "b" / "c" / "ops.log"
    log_entry("skill-x", "PASS", log_path=deep)
    assert deep.exists()


# ---------------------------------------------------------------------------
# 17. family and platform default to empty string
# ---------------------------------------------------------------------------

def test_family_platform_default_empty(tmp_path):
    log_file = tmp_path / "ops.log"
    log_entry("path-guard", "PASS", log_path=log_file)
    entry = read_log(log_file)[0]
    assert entry["family"] == ""
    assert entry["platform"] == ""


# ---------------------------------------------------------------------------
# 18. log_entry returns the Path to the log file
# ---------------------------------------------------------------------------

def test_log_entry_returns_path(tmp_path):
    log_file = tmp_path / "ops.log"
    result = log_entry("skill-x", "PASS", log_path=log_file)
    assert isinstance(result, Path)
    assert result == log_file


# ---------------------------------------------------------------------------
# 19. Entries from read_log are dicts with correct types
# ---------------------------------------------------------------------------

def test_read_log_entry_types(tmp_path):
    log_file = tmp_path / "ops.log"
    log_entry(
        "ground-check", "WARN",
        family="words", platform="python",
        artifacts_written=["a.md"], errors=["msg"],
        log_path=log_file,
    )
    entry = read_log(log_file)[0]
    assert isinstance(entry["ts"], str)
    assert isinstance(entry["skill"], str)
    assert isinstance(entry["family"], str)
    assert isinstance(entry["platform"], str)
    assert isinstance(entry["status"], str)
    assert isinstance(entry["artifacts_written"], list)
    assert isinstance(entry["errors"], list)


# ---------------------------------------------------------------------------
# 20. VALID_STATUSES set contains exactly the five expected values
# ---------------------------------------------------------------------------

def test_valid_statuses_set():
    assert VALID_STATUSES == {"PASS", "FAIL", "WARN", "ERROR", "ESCALATE"}
