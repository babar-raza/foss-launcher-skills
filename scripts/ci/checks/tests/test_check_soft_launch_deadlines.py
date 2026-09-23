"""Tests for check_soft_launch_deadlines.py (MT069 HC-15)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import check_soft_launch_deadlines as csld  # noqa: E402


def _sidecar(tmp_path, entries):
    p = tmp_path / "sidecar.json"
    p.write_text(json.dumps({"entries": entries}), encoding="utf-8")
    return p


def _entry(**overrides):
    e = {
        "id": "example", "description": "an example soft launch", "kind": "workflow-step-continue-on-error",
        "location": "somewhere.yml", "soak_started": "2026-09-01", "soak_end": "2026-09-15",
        "owning_card": "MT069-HC-15", "status": "soaking",
    }
    e.update(overrides)
    return e


class TestLoadEntries:
    def test_missing_sidecar_raises_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            csld.load_entries(tmp_path / "nope.json")

    def test_malformed_json_raises(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("{not json", encoding="utf-8")
        with pytest.raises(json.JSONDecodeError):
            csld.load_entries(p)

    def test_entries_must_be_a_list(self, tmp_path):
        p = tmp_path / "s.json"
        p.write_text(json.dumps({"entries": "nope"}), encoding="utf-8")
        with pytest.raises(ValueError, match="must be a list"):
            csld.load_entries(p)

    def test_missing_required_field_raises_naming_the_field(self, tmp_path):
        bad = _entry()
        del bad["soak_end"]
        p = _sidecar(tmp_path, [bad])
        with pytest.raises(ValueError, match="soak_end"):
            csld.load_entries(p)

    def test_invalid_status_raises(self, tmp_path):
        p = _sidecar(tmp_path, [_entry(status="not-a-real-status")])
        with pytest.raises(ValueError, match="invalid status"):
            csld.load_entries(p)

    def test_malformed_date_raises(self, tmp_path):
        p = _sidecar(tmp_path, [_entry(soak_end="not-a-date")])
        with pytest.raises(ValueError):
            csld.load_entries(p)

    def test_a_valid_sidecar_loads_cleanly(self, tmp_path):
        p = _sidecar(tmp_path, [_entry()])
        assert len(csld.load_entries(p)) == 1


class TestFindOverdue:
    def test_soaking_entry_past_its_deadline_is_overdue(self):
        entries = [_entry(soak_end="2026-09-01", status="soaking")]
        overdue = csld.find_overdue(entries, today=__import__("datetime").date(2026, 9, 23))
        assert len(overdue) == 1

    def test_soaking_entry_not_yet_due_is_not_overdue(self):
        entries = [_entry(soak_end="2026-12-31", status="soaking")]
        overdue = csld.find_overdue(entries, today=__import__("datetime").date(2026, 9, 23))
        assert overdue == []

    def test_deadline_exactly_today_is_not_yet_overdue(self):
        """The deadline day itself is not overdue -- overdue means the date has PASSED."""
        entries = [_entry(soak_end="2026-09-23", status="soaking")]
        overdue = csld.find_overdue(entries, today=__import__("datetime").date(2026, 9, 23))
        assert overdue == []

    def test_a_graduated_entry_past_its_old_deadline_is_never_overdue(self):
        """Once flipped, an entry stops being watched -- this is the exact shape that would have
        caught TC-SG-07/R-04 if it had existed: a soaking entry never re-checked, not a graduated one."""
        entries = [_entry(soak_end="2026-01-01", status="graduated")]
        overdue = csld.find_overdue(entries, today=__import__("datetime").date(2026, 9, 23))
        assert overdue == []

    def test_a_reverted_entry_is_never_overdue(self):
        entries = [_entry(soak_end="2026-01-01", status="reverted")]
        overdue = csld.find_overdue(entries, today=__import__("datetime").date(2026, 9, 23))
        assert overdue == []


class TestMainCLI:
    def test_exits_0_when_nothing_overdue(self, tmp_path):
        p = _sidecar(tmp_path, [_entry(soak_end="2099-01-01")])
        assert csld.main(["--sidecar", str(p), "--today", "2026-09-23"]) == 0

    def test_exits_1_when_something_is_overdue(self, tmp_path):
        p = _sidecar(tmp_path, [_entry(soak_end="2026-09-01")])
        assert csld.main(["--sidecar", str(p), "--today", "2026-09-23"]) == 1

    def test_exits_2_on_missing_sidecar_not_a_silent_pass(self, tmp_path):
        assert csld.main(["--sidecar", str(tmp_path / "nope.json")]) == 2

    def test_exits_2_on_malformed_sidecar_not_a_silent_pass(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text(json.dumps({"entries": [{"id": "x"}]}), encoding="utf-8")
        assert csld.main(["--sidecar", str(p)]) == 2

    def test_json_output_names_the_overdue_entries(self, tmp_path, capsys):
        p = _sidecar(tmp_path, [_entry(id="a", soak_end="2026-09-01"), _entry(id="b", soak_end="2099-01-01")])
        rc = csld.main(["--sidecar", str(p), "--today", "2026-09-23", "--json"])
        out = json.loads(capsys.readouterr().out)
        assert rc == 1
        assert out["total_entries"] == 2
        assert [e["id"] for e in out["overdue"]] == ["a"]

    def test_empty_sidecar_is_not_an_error(self, tmp_path):
        p = _sidecar(tmp_path, [])
        assert csld.main(["--sidecar", str(p)]) == 0

    def test_the_real_repo_sidecar_loads_and_is_reported_honestly(self):
        """The real data/soft_launch_deadlines.json must itself be well-formed. Not asserting a
        specific pass/fail outcome here (its entries' real dates change over time) -- only that
        loading it never raises and the CLI never silently treats a load failure as clean."""
        real_path = csld._DEFAULT_SIDECAR
        entries = csld.load_entries(real_path)  # raises loudly if the real file is malformed
        assert len(entries) >= 1
