"""Tests for check_proof_matrix.py — operator proof matrix coverage gate."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_CI_DIR = Path(__file__).resolve().parent.parent / "checks" 
if str(_CI_DIR) not in sys.path:
    sys.path.insert(0, str(_CI_DIR))

import check_proof_matrix  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_index(path: Path, entries: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries, indent=2), encoding="utf-8")
    return path


def _all_scenarios_index(path: Path) -> Path:
    entries = [
        {"bundle_id": f"bundle-{i}", "operator_scenario": i}
        for i in range(1, 7)
    ]
    return _write_index(path, entries)


def _missing_scenarios_index(path: Path, missing: list[int]) -> Path:
    entries = [
        {"bundle_id": f"bundle-{i}", "operator_scenario": i}
        for i in range(1, 7)
        if i not in missing
    ]
    return _write_index(path, entries)


@pytest.fixture(autouse=True)
def _reset(tmp_path):
    """Reset module-level state after each test."""
    orig = check_proof_matrix._INDEX_FILE
    yield
    check_proof_matrix._INDEX_FILE = orig


# ---------------------------------------------------------------------------
# TestAllScenariosCovered
# ---------------------------------------------------------------------------

class TestAllScenariosCovered:
    def test_all_6_scenarios_exits_0(self, tmp_path):
        idx = _all_scenarios_index(tmp_path / "INDEX.json")
        check_proof_matrix.configure(index_file=idx)
        assert check_proof_matrix.main([]) == 0

    def test_all_6_scenarios_json_output_pass(self, tmp_path, capsys):
        idx = _all_scenarios_index(tmp_path / "INDEX.json")
        check_proof_matrix.configure(index_file=idx)
        result = check_proof_matrix.main(["--json"])
        assert result == 0
        data = json.loads(capsys.readouterr().out)
        assert data["overall"] == "PASS"

    def test_all_6_scenarios_coverage_dict(self, tmp_path):
        idx = _all_scenarios_index(tmp_path / "INDEX.json")
        exit_code, coverage = check_proof_matrix.check(idx)
        assert exit_code == 0
        for sid in range(1, 7):
            assert coverage[sid], f"Scenario {sid} should have bundles"

    def test_multiple_bundles_per_scenario(self, tmp_path):
        entries = [
            {"bundle_id": f"bundle-{i}-a", "operator_scenario": i}
            for i in range(1, 7)
        ] + [
            {"bundle_id": f"bundle-{i}-b", "operator_scenario": i}
            for i in range(1, 7)
        ]
        idx = _write_index(tmp_path / "INDEX.json", entries)
        exit_code, coverage = check_proof_matrix.check(idx)
        assert exit_code == 0
        for sid in range(1, 7):
            assert len(coverage[sid]) == 2


# ---------------------------------------------------------------------------
# TestMissingScenarios
# ---------------------------------------------------------------------------

class TestMissingScenarios:
    def test_one_missing_scenario_exits_1(self, tmp_path):
        idx = _missing_scenarios_index(tmp_path / "INDEX.json", missing=[2])
        check_proof_matrix.configure(index_file=idx)
        assert check_proof_matrix.main([]) == 1

    def test_all_missing_exits_1(self, tmp_path):
        idx = _write_index(tmp_path / "INDEX.json", [])
        check_proof_matrix.configure(index_file=idx)
        assert check_proof_matrix.main([]) == 1

    def test_missing_scenario_json_output_fail(self, tmp_path, capsys):
        idx = _missing_scenarios_index(tmp_path / "INDEX.json", missing=[4])
        check_proof_matrix.configure(index_file=idx)
        result = check_proof_matrix.main(["--json"])
        assert result == 1
        data = json.loads(capsys.readouterr().out)
        assert data["overall"] == "FAIL"
        assert not data["scenarios"]["4"]["covered"]

    def test_missing_scenario_coverage_empty_list(self, tmp_path):
        idx = _missing_scenarios_index(tmp_path / "INDEX.json", missing=[3, 5])
        exit_code, coverage = check_proof_matrix.check(idx)
        assert exit_code == 1
        assert coverage[3] == []
        assert coverage[5] == []

    @pytest.mark.parametrize("missing_scenario", [1, 2, 3, 4, 5, 6])
    def test_each_scenario_individually_required(self, tmp_path, missing_scenario):
        idx = _missing_scenarios_index(tmp_path / "INDEX.json", missing=[missing_scenario])
        exit_code, _ = check_proof_matrix.check(idx)
        assert exit_code == 1


# ---------------------------------------------------------------------------
# TestInvalidIndex
# ---------------------------------------------------------------------------

class TestInvalidIndex:
    def test_missing_index_file_exits_0_advisory(self, tmp_path):
        # Missing INDEX.json is advisory — local-only artifact
        check_proof_matrix.configure(index_file=tmp_path / "missing.json")
        assert check_proof_matrix.main([]) == 0

    def test_malformed_json_exits_0_advisory(self, tmp_path):
        idx = tmp_path / "INDEX.json"
        idx.write_text("not valid json", encoding="utf-8")
        check_proof_matrix.configure(index_file=idx)
        assert check_proof_matrix.main([]) == 0

    def test_dict_instead_of_list_exits_0_advisory(self, tmp_path):
        idx = tmp_path / "INDEX.json"
        idx.write_text(json.dumps({"wrong": "format"}), encoding="utf-8")
        check_proof_matrix.configure(index_file=idx)
        assert check_proof_matrix.main([]) == 0

    def test_entries_without_scenario_tag_are_ignored(self, tmp_path):
        # Bundles without operator_scenario should not count toward any scenario
        entries = [{"bundle_id": "untagged", "summary": "some bundle"}]
        idx = _write_index(tmp_path / "INDEX.json", entries)
        exit_code, coverage = check_proof_matrix.check(idx)
        assert exit_code == 1
        for sid in range(1, 7):
            assert coverage[sid] == []
