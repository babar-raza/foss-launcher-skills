"""Tests for scripts/ci/checks/check_backlink_regression.py (TC14).

Covers:
  - Empty backlink-audit.json is treated as a tool crash (exit 2), not a
    silent pass. backlink_audit.py's build_report() only writes JSON once,
    after the whole scan completes.
  - Well-formed results within baseline pass (exit 0).
  - Well-formed results exceeding baseline fail (exit 1).
  - Improvement (fewer violations than baseline) still passes -- the
    ratchet only ever blocks on regression, never demands immediate zero.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CHECKER = REPO_ROOT / "scripts" / "ci" / "checks" / "check_backlink_regression.py"


def _run_checker(current: Path, baseline: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CHECKER), str(current), str(baseline)],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )


def _by_family_report(counts: dict) -> dict:
    return {
        "schema_version": "1.0",
        "generated_at": "2026-08-22T00:00:00Z",
        "generator": "backlink_audit.py test fixture",
        "target_map_version": "test",
        "totals": {},
        "by_subdomain": {},
        "by_family": counts,
        "records": [],
    }


def test_empty_current_file_fails_not_passes(tmp_path: Path) -> None:
    current = tmp_path / "backlink-audit.json"
    current.write_text("", encoding="utf-8")
    baseline = tmp_path / "baseline.json"
    baseline.write_text("{}", encoding="utf-8")

    result = _run_checker(current, baseline)

    assert result.returncode == 2
    assert "crashed" in result.stderr.lower()


def test_within_baseline_passes(tmp_path: Path) -> None:
    current = tmp_path / "backlink-audit.json"
    current.write_text(json.dumps(_by_family_report({
        "pdf": {"compliant": 5, "duplicate_link": 2, "missing": 3},
    })), encoding="utf-8")
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"pdf": {"count": 2}}), encoding="utf-8")

    result = _run_checker(current, baseline)

    assert result.returncode == 0
    assert "OK" in result.stdout


def test_exceeding_baseline_fails(tmp_path: Path) -> None:
    current = tmp_path / "backlink-audit.json"
    current.write_text(json.dumps(_by_family_report({
        "pdf": {"compliant": 5, "duplicate_link": 4, "wrong_anchor_text": 1},
    })), encoding="utf-8")
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"pdf": {"count": 2}}), encoding="utf-8")

    result = _run_checker(current, baseline)

    assert result.returncode == 1
    assert "REGRESSION" in result.stderr
    assert "pdf" in result.stderr


def test_missing_not_counted_toward_blocking_total(tmp_path: Path) -> None:
    """MISSING/SKIPPED/FAMILY_FALLBACK/COMPLIANT are not blocking statuses
    (matching check_backlink_compliance.py's own BLOCKING_KEYS) -- a family
    with a huge MISSING backlog but zero confidently-wrong statuses must
    pass against a zero baseline."""
    current = tmp_path / "backlink-audit.json"
    current.write_text(json.dumps(_by_family_report({
        "words": {"compliant": 2, "missing": 40, "skipped": 5},
    })), encoding="utf-8")
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"words": {"count": 0}}), encoding="utf-8")

    result = _run_checker(current, baseline)

    assert result.returncode == 0


def test_improvement_over_baseline_passes(tmp_path: Path) -> None:
    """The ratchet only blocks regressions -- fewer violations than the
    checked-in baseline must still pass (not force an immediate zero)."""
    current = tmp_path / "backlink-audit.json"
    current.write_text(json.dumps(_by_family_report({
        "pdf": {"duplicate_link": 1},
    })), encoding="utf-8")
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"pdf": {"count": 5}}), encoding="utf-8")

    result = _run_checker(current, baseline)

    assert result.returncode == 0


def test_bare_int_baseline_format_supported(tmp_path: Path) -> None:
    """Matches check_audit_regression.py's own dual-format support: baseline
    entries may be a bare int, not only {"count": N}."""
    current = tmp_path / "backlink-audit.json"
    current.write_text(json.dumps(_by_family_report({
        "pdf": {"duplicate_link": 3},
    })), encoding="utf-8")
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"pdf": 2}), encoding="utf-8")

    result = _run_checker(current, baseline)

    assert result.returncode == 1
