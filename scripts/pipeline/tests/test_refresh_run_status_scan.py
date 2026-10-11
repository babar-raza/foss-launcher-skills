"""Tests for commands/ops/refresh_run_status_scan.py.

Mission plan: mission-plan-the-end-to-end-vast-hejlsberg.md, Task 5 (closes G1).
Covers: fresh BLOCKED not flagged, stale BLOCKED flagged (exit 1), non-BLOCKED
states ignored, unreadable/missing manifests handled without crashing, and a
multi-product scan.
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_PIPELINE_ROOT = Path(__file__).resolve().parents[1]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

import commands.ops.refresh_run_status_scan as sut

_FIXED_NOW = datetime(2026, 8, 22, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def isolate(tmp_path):
    sut.configure(repo_root=tmp_path, now=lambda: _FIXED_NOW)
    yield
    sut.configure()


def _write_run(tmp_path, family, platform, run_id, *, state, updated_at, active_updated_at=None, failure_reason=None):
    product_root = tmp_path / "reports" / "refresh_runs" / family / platform
    run_root = product_root / run_id
    run_root.mkdir(parents=True, exist_ok=True)
    (product_root / "ACTIVE.json").write_text(
        json.dumps({"run_id": run_id, "updated_at": active_updated_at or updated_at}),
        encoding="utf-8",
    )
    manifest = {
        "run_id": run_id, "family": family, "platform": platform,
        "state": state, "updated_at": updated_at,
    }
    if failure_reason is not None:
        manifest["failure_reason"] = failure_reason
    (run_root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_no_runs_directory_returns_empty_scan(tmp_path):
    result = sut.scan()
    assert result["products_scanned"] == 0
    assert result["stale_blocked_count"] == 0


def test_fresh_blocked_not_flagged(tmp_path):
    recent = (_FIXED_NOW - timedelta(days=2)).isoformat().replace("+00:00", "Z")
    _write_run(tmp_path, "cells", "go", "run-1", state="BLOCKED", updated_at=recent)
    result = sut.scan()
    assert result["stale_blocked_count"] == 0
    entry = result["entries"][0]
    assert entry["classification"] == "BLOCKED_RECENT"


def test_stale_blocked_flagged(tmp_path):
    stale = (_FIXED_NOW - timedelta(days=25)).isoformat().replace("+00:00", "Z")
    _write_run(
        tmp_path, "cells", "go", "mt011-cells-go-ref", state="BLOCKED", updated_at=stale,
        failure_reason="upstream/combined run has no knowledge_delta.json after knowledge refresh",
    )
    result = sut.scan()
    assert result["stale_blocked_count"] == 1
    entry = result["entries"][0]
    assert entry["classification"] == "STALE_BLOCKED"
    assert entry["age_days"] >= 7
    assert "knowledge_delta" in entry["failure_reason"]


def test_stale_blocked_exit_code_is_nonzero(tmp_path, capsys):
    stale = (_FIXED_NOW - timedelta(days=30)).isoformat().replace("+00:00", "Z")
    _write_run(tmp_path, "cells", "go", "run-1", state="BLOCKED", updated_at=stale)
    exit_code = sut.main([])
    assert exit_code == 1


def test_fresh_blocked_exit_code_is_zero(tmp_path):
    recent = (_FIXED_NOW - timedelta(days=1)).isoformat().replace("+00:00", "Z")
    _write_run(tmp_path, "cells", "go", "run-1", state="BLOCKED", updated_at=recent)
    exit_code = sut.main([])
    assert exit_code == 0


def test_terminal_states_produce_no_active_json_and_are_invisible(tmp_path):
    """COMMITTED/ABANDONED runs clear ACTIVE.json on the way to terminal state
    (refresh_run.py's own contract) -- this scan only ever walks ACTIVE.json,
    so a terminal-state run has nothing to discover, by construction."""
    result = sut.scan()
    assert result["products_scanned"] == 0


def test_non_blocked_active_run_is_not_flagged(tmp_path):
    recent = (_FIXED_NOW - timedelta(days=20)).isoformat().replace("+00:00", "Z")
    _write_run(tmp_path, "pdf", "java", "run-1", state="VALIDATING", updated_at=recent)
    result = sut.scan()
    assert result["stale_blocked_count"] == 0
    assert result["entries"][0]["classification"] == "ACTIVE_NOT_BLOCKED"


def test_missing_manifest_handled_without_crash(tmp_path):
    product_root = tmp_path / "reports" / "refresh_runs" / "cells" / "go"
    product_root.mkdir(parents=True, exist_ok=True)
    (product_root / "ACTIVE.json").write_text(
        json.dumps({"run_id": "ghost-run", "updated_at": "2026-08-01T00:00:00Z"}),
        encoding="utf-8",
    )
    result = sut.scan()
    assert result["entries"][0]["classification"] == "UNREADABLE"
    assert "manifest.json not found" in result["entries"][0]["detail"]


def test_multi_product_scan_reports_all(tmp_path):
    stale = (_FIXED_NOW - timedelta(days=15)).isoformat().replace("+00:00", "Z")
    recent = (_FIXED_NOW - timedelta(days=1)).isoformat().replace("+00:00", "Z")
    _write_run(tmp_path, "cells", "go", "run-a", state="BLOCKED", updated_at=stale)
    _write_run(tmp_path, "pdf", "java", "run-b", state="BLOCKED", updated_at=recent)
    _write_run(tmp_path, "3d", "python", "run-c", state="VALIDATING", updated_at=recent)
    result = sut.scan()
    assert result["products_scanned"] == 3
    assert result["stale_blocked_count"] == 1


def test_write_scan_report_creates_dated_file(tmp_path):
    result = sut.scan()
    out_path = sut.write_scan_report(result)
    assert out_path.is_file()
    assert out_path.parent.name == "_scan"
    written = json.loads(out_path.read_text(encoding="utf-8"))
    assert written["products_scanned"] == result["products_scanned"]
