"""Tests for check_package_content_healing_staleness.py (watcher-fleet
reliability hardening, 2026-09-07, Phase 3)."""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "checks"))

import check_package_content_healing_staleness as sut  # noqa: E402


def _entry(*, status, set_at=None, published=True):
    return {
        "verification": {"published": published},
        "content_healing_status": status,
        "content_healing_status_set_at": set_at,
    }


def test_fresh_pending_entry_is_not_flagged():
    registry = {"3d": {"python": _entry(status="pending", set_at="2026-09-07")}}
    stale = sut.find_stale_entries(registry, stale_days=14, today=date(2026, 9, 7))
    assert stale == []


def test_pending_entry_older_than_threshold_is_flagged():
    registry = {"3d": {"python": _entry(status="pending", set_at="2026-08-01")}}
    stale = sut.find_stale_entries(registry, stale_days=14, today=date(2026, 9, 7))
    assert len(stale) == 1
    assert stale[0]["family"] == "3d"
    assert stale[0]["platform"] == "python"
    assert stale[0]["age_days"] == 37


def test_healed_and_not_needed_entries_are_never_flagged():
    registry = {
        "cells": {
            "python": _entry(status="healed", set_at="2020-01-01"),
            "net": _entry(status="not_needed", set_at="2020-01-01"),
        },
    }
    assert sut.find_stale_entries(registry, stale_days=14, today=date(2026, 9, 7)) == []


def test_entry_with_no_content_healing_status_is_not_flagged():
    """Entries predating this feature (no content_healing_status key at all)
    must not be treated as an unparseable-and-therefore-stale pending entry --
    only an EXPLICIT "pending" status is ever flagged."""
    registry = {"cells": {"java": {"verification": {"published": True}}}}
    assert sut.find_stale_entries(registry, stale_days=14, today=date(2026, 9, 7)) == []


def test_unparseable_set_at_is_flagged_as_stale():
    registry = {"3d": {"python": _entry(status="pending", set_at="not-a-date")}}
    stale = sut.find_stale_entries(registry, stale_days=14, today=date(2026, 9, 7))
    assert len(stale) == 1
    assert stale[0]["age_days"] is None


def test_main_exits_zero_and_warns_on_stale_entries(tmp_path, capsys):
    registry = {"3d": {"python": _entry(status="pending", set_at="2026-08-01")}}
    registry_path = tmp_path / "package_registry.json"
    registry_path.write_text(json.dumps(registry), encoding="utf-8")

    rc = sut.main(["--registry", str(registry_path), "--stale-days", "14"])
    assert rc == 0
    captured = capsys.readouterr()
    assert "3d/python" in captured.err
    assert "WARN" in captured.err


def test_main_exits_zero_when_registry_missing(tmp_path):
    rc = sut.main(["--registry", str(tmp_path / "does-not-exist.json")])
    assert rc == 0
