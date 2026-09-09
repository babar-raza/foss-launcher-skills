"""Tests for scripts/pipeline/lib/reconciliation_ledger.py (Mission
MT066-2026-09-09-PACKAGE-INSTALL-RECONCILIATION, Phase 1).

record_observation() is pure (plain dict in, plain dict out); load_ledger()/
save_ledger() are the only I/O, exercised here against tmp_path per this repo's
DI-over-monkeypatch convention (AGENTS.md 16) -- no monkeypatching of internals.
"""

import json
import sys
from pathlib import Path

_LIB_DIR = Path(__file__).resolve().parents[1] / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from package_registries import CheckResult  # noqa: E402
from reconciliation_ledger import load_ledger, record_observation, save_ledger  # noqa: E402


def _result(**overrides):
    defaults = dict(published=True, ambiguous=False, evidence_url="https://example/x", method="pypi-json-api")
    defaults.update(overrides)
    return CheckResult(**defaults)


class TestRecordObservation:
    def test_records_a_new_entry_keyed_by_family_platform(self):
        ledger = record_observation(
            {}, family="pdf", platform="python", registry_type="pypi",
            result=_result(version="26.8.0"), observed_at="2026-09-09T00:00:00Z",
        )
        entry = ledger["pdf.python"]
        assert entry["family"] == "pdf"
        assert entry["platform"] == "python"
        assert entry["registry_type"] == "pypi"
        assert entry["last_observed_at"] == "2026-09-09T00:00:00Z"
        assert entry["published"] is True
        assert entry["live_version"] == "26.8.0"
        assert entry["yanked"] is False

    def test_records_on_ambiguous_outcome_too(self):
        """The entire point: a silently-stopped/erroring adapter is only
        detectable if 'we checked and got ambiguous' is itself recorded."""
        ledger = record_observation(
            {}, family="pdf", platform="go", registry_type="go_modules",
            result=_result(published=False, ambiguous=True, method="go-proxy-api"),
            observed_at="2026-09-09T01:00:00Z",
        )
        entry = ledger["pdf.go"]
        assert entry["ambiguous"] is True
        assert entry["published"] is False

    def test_does_not_mutate_the_input_ledger(self):
        original = {"pdf.python": {"stale": True}}
        updated = record_observation(
            original, family="cells", platform="rust", registry_type="cargo",
            result=_result(method="crates-io-api"), observed_at="2026-09-09T02:00:00Z",
        )
        assert "cells.rust" not in original
        assert original["pdf.python"] == {"stale": True}
        assert "cells.rust" in updated

    def test_overwrites_the_previous_observation_for_the_same_key(self):
        ledger = record_observation(
            {}, family="pdf", platform="python", registry_type="pypi",
            result=_result(version="26.7.0"), observed_at="2026-09-08T00:00:00Z",
        )
        ledger = record_observation(
            ledger, family="pdf", platform="python", registry_type="pypi",
            result=_result(version="26.8.0"), observed_at="2026-09-09T00:00:00Z",
        )
        assert len(ledger) == 1
        assert ledger["pdf.python"]["live_version"] == "26.8.0"
        assert ledger["pdf.python"]["last_observed_at"] == "2026-09-09T00:00:00Z"


class TestLoadSaveLedger:
    def test_load_returns_empty_dict_when_file_absent(self, tmp_path):
        assert load_ledger(tmp_path / "does-not-exist.json") == {}

    def test_load_returns_empty_dict_on_corrupt_file(self, tmp_path):
        path = tmp_path / "observations.json"
        path.write_text("not json{{{", encoding="utf-8")
        assert load_ledger(path) == {}

    def test_save_then_load_roundtrips(self, tmp_path):
        path = tmp_path / "sub" / "observations.json"
        ledger = record_observation(
            {}, family="pdf", platform="python", registry_type="pypi",
            result=_result(version="26.8.0"), observed_at="2026-09-09T00:00:00Z",
        )
        save_ledger(ledger, path)
        assert path.exists()
        reloaded = load_ledger(path)
        assert reloaded == ledger

    def test_save_creates_parent_directory(self, tmp_path):
        path = tmp_path / "does" / "not" / "exist" / "observations.json"
        save_ledger({}, path)
        assert path.exists()

    def test_saved_file_is_valid_json_and_ends_with_newline(self, tmp_path):
        path = tmp_path / "observations.json"
        save_ledger({"a.b": {"x": 1}}, path)
        text = path.read_text(encoding="utf-8")
        assert text.endswith("\n")
        assert json.loads(text) == {"a.b": {"x": 1}}
