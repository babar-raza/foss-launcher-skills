"""Tests for check_mission_id_ledger_coverage.py (ST-157 regression gate)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from check_mission_id_ledger_coverage import find_uncovered, main  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "pipeline" / "lib"))
from mission_id_ledger import MissionIdLedger  # noqa: E402


def test_clean_repo_with_nothing_to_scan_is_covered(tmp_path):
    assert find_uncovered(tmp_path) == []
    assert main(["--root", str(tmp_path)]) == 0


def test_seeded_plans_missions_id_is_covered(tmp_path):
    missions_dir = tmp_path / "plans" / "missions"
    missions_dir.mkdir(parents=True)
    (missions_dir / "MT005-2026-09-01-EXAMPLE.md").write_text("# x\n", encoding="utf-8")

    ledger = MissionIdLedger(repo_root=tmp_path)
    ledger.seed(number=5, mission_id="MT005-2026-09-01-EXAMPLE", track="main", source="test")

    assert find_uncovered(tmp_path) == []


def test_unseeded_plans_missions_id_is_flagged_advisory_not_blocking(tmp_path, capsys):
    """Negative control: an id that bypassed allocate/seed-ledger must be
    detected -- advisory mode reports it but still exits 0 (the deliberate
    first-landing posture, matching check_pipeline_registration.py's own
    advisory rollout)."""
    missions_dir = tmp_path / "plans" / "missions"
    missions_dir.mkdir(parents=True)
    (missions_dir / "MT007-2026-09-01-BYPASSED.md").write_text("# x\n", encoding="utf-8")

    uncovered = find_uncovered(tmp_path)
    assert uncovered == ["MT007-2026-09-01-BYPASSED"]

    exit_code = main(["--root", str(tmp_path)])
    assert exit_code == 0  # advisory: reported, not blocking
    out = capsys.readouterr().out
    assert "ADVISORY" in out
    assert "MT007-2026-09-01-BYPASSED" in out


def test_strict_mode_fails_on_the_same_finding(tmp_path):
    missions_dir = tmp_path / "plans" / "missions"
    missions_dir.mkdir(parents=True)
    (missions_dir / "MT007-2026-09-01-BYPASSED.md").write_text("# x\n", encoding="utf-8")

    exit_code = main(["--root", str(tmp_path), "--strict"])
    assert exit_code == 1


def test_free_text_slug_missions_never_flagged(tmp_path):
    missions_dir = tmp_path / "plans" / "missions"
    missions_dir.mkdir(parents=True)
    (missions_dir / "backlink-governance-redesign.md").write_text("# x\n", encoding="utf-8")

    assert find_uncovered(tmp_path) == []


def test_track_b_number_covered_by_a_real_non_placeholder_id_is_not_double_flagged(tmp_path):
    """The bug caught live: seed-ledger deliberately does NOT write a
    placeholder when a real id for that number already exists from another
    source, so the check must match by NUMBER for Track B, not by
    reconstructing the placeholder string."""
    doc_dir = tmp_path / "docs" / "readme-refresh"
    doc_dir.mkdir(parents=True)
    (doc_dir / "plan-system-forensic-reconciliation.md").write_text(
        "| MT021 | 2026-08-06 | some incident |\n", encoding="utf-8",
    )
    ledger = MissionIdLedger(repo_root=tmp_path)
    ledger.seed(number=21, mission_id="MT021-2026-08-06-REAL-MAIN-TRACK-MISSION", track="main", source="test")

    assert find_uncovered(tmp_path) == []


def test_track_b_number_with_no_coverage_at_all_is_flagged(tmp_path):
    doc_dir = tmp_path / "docs" / "readme-refresh"
    doc_dir.mkdir(parents=True)
    (doc_dir / "plan-system-forensic-reconciliation.md").write_text(
        "| MT099 | 2026-08-06 | some incident |\n", encoding="utf-8",
    )
    uncovered = find_uncovered(tmp_path)
    assert uncovered == ["MT099-README-REFRESH-TRACK-B-PLACEHOLDER"]
