"""Tests for check_mission_id_no_new_duplicates.py (ST-194 regression gate)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from check_mission_id_no_new_duplicates import find_duplicate_numbers, main  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "pipeline" / "lib"))
from mission_id_ledger import MissionIdLedger  # noqa: E402


def _write_baseline(root: Path, numbers: list[int]) -> None:
    config_dir = root / "scripts" / "pipeline" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "mission-id-known-duplicates.json").write_text(
        json.dumps({"known_duplicate_numbers": numbers}), encoding="utf-8",
    )


def test_clean_ledger_with_no_duplicates_passes(tmp_path):
    ledger = MissionIdLedger(repo_root=tmp_path)
    ledger.seed(number=1, mission_id="MT001-2026-01-01-ONLY", track="main", source="test")

    assert find_duplicate_numbers(tmp_path) == {}
    assert main(["--root", str(tmp_path)]) == 0
    assert main(["--root", str(tmp_path), "--strict"]) == 0


def test_duplicate_in_baseline_is_reported_as_known_not_new(tmp_path, capsys):
    ledger = MissionIdLedger(repo_root=tmp_path)
    ledger.seed(number=18, mission_id="MT018-2026-08-01-A", track="main", source="test")
    ledger.seed(number=18, mission_id="MT018-2026-08-01-B", track="main", source="test")
    _write_baseline(tmp_path, [18])

    duplicates = find_duplicate_numbers(tmp_path)
    assert duplicates == {18: ["MT018-2026-08-01-A", "MT018-2026-08-01-B"]}

    exit_code = main(["--root", str(tmp_path), "--strict"])
    assert exit_code == 0  # baselined: known duplicate, not a regression
    out = capsys.readouterr().out
    assert "INFO" in out
    assert "PASS" in out


def test_duplicate_not_in_baseline_is_flagged_advisory_not_blocking(tmp_path, capsys):
    """Negative control: a genuinely NEW duplicate number (not in the
    baseline) must be detected -- advisory mode reports it but still exits 0
    (matching this check's two siblings' own first-landing posture)."""
    ledger = MissionIdLedger(repo_root=tmp_path)
    ledger.seed(number=99, mission_id="MT099-2026-09-01-A", track="main", source="test")
    ledger.seed(number=99, mission_id="MT099-2026-09-01-B", track="main", source="test")
    _write_baseline(tmp_path, [18])  # 99 is not baselined

    exit_code = main(["--root", str(tmp_path)])
    assert exit_code == 0  # advisory: reported, not blocking
    out = capsys.readouterr().out
    assert "ADVISORY" in out
    assert "MT099-2026-09-01-A" in out
    assert "MT099-2026-09-01-B" in out


def test_strict_mode_fails_on_a_new_duplicate_not_in_baseline(tmp_path):
    ledger = MissionIdLedger(repo_root=tmp_path)
    ledger.seed(number=99, mission_id="MT099-2026-09-01-A", track="main", source="test")
    ledger.seed(number=99, mission_id="MT099-2026-09-01-B", track="main", source="test")
    _write_baseline(tmp_path, [18])

    exit_code = main(["--root", str(tmp_path), "--strict"])
    assert exit_code == 1


def test_missing_baseline_file_treats_every_duplicate_as_new(tmp_path):
    """No baseline file at all (e.g. a repo that hasn't adopted it yet) must
    not crash -- every duplicate is conservatively treated as new."""
    ledger = MissionIdLedger(repo_root=tmp_path)
    ledger.seed(number=5, mission_id="MT005-2026-01-01-A", track="main", source="test")
    ledger.seed(number=5, mission_id="MT005-2026-01-01-B", track="main", source="test")

    duplicates = find_duplicate_numbers(tmp_path)
    assert duplicates == {5: ["MT005-2026-01-01-A", "MT005-2026-01-01-B"]}
    assert main(["--root", str(tmp_path), "--strict"]) == 1
