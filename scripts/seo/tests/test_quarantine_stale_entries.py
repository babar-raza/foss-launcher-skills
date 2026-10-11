"""SEO-SCHEMA-A-QUARANTINE-STALE-ENTRIES: quarantine-plan and apply tests.

Only drifted_title_mismatch orphans (family HAS launched content, but this
specific title matches nothing on disk) should ever be quarantined.
prospective_no_launched_content orphans (family has zero launched content --
the mission's only keyword signal for stub-tier families) must never be
touched, even though audit_schema_a.py flags both as "orphan_candidates".
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[2]
_PIPELINE = _SCRIPTS / "pipeline"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
if str(_PIPELINE) not in sys.path:
    sys.path.insert(0, str(_PIPELINE))

import seo.pipeline.quarantine_stale_entries as quarantine  # noqa: E402


def _fake_audit_report():
    return {
        "families": [
            {
                "family": "cad",
                "orphan_classification": "prospective_no_launched_content",
                "orphans": [{"index": 0, "pageTitle": "Future CAD Article"}],
            },
            {
                "family": "words",
                "orphan_classification": "drifted_title_mismatch",
                "orphans": [
                    {"index": 1, "pageTitle": "Old Words KB Title"},
                    {"index": 3, "pageTitle": "Another Old Title"},
                ],
            },
            {
                "family": "pdf",
                "orphan_classification": "n/a",
                "orphans": [],
            },
        ]
    }


def test_plan_quarantine_only_includes_drifted_families():
    plan = quarantine.plan_quarantine(_fake_audit_report())
    assert "words" in plan
    assert "cad" not in plan  # prospective -- never quarantined
    assert "pdf" not in plan  # n/a, no orphans


def test_plan_quarantine_collects_correct_indices():
    plan = quarantine.plan_quarantine(_fake_audit_report())
    assert plan["words"] == [1, 3]


def test_apply_quarantine_dry_run_does_not_write(tmp_path, monkeypatch):
    monkeypatch.setattr(quarantine, "KEYWORDS_DIR", tmp_path)
    monkeypatch.setattr(quarantine, "STALE_DIR", tmp_path / "_stale")

    live = [
        {"pageTitle": "Keep Me", "keywords": ["a"]},
        {"pageTitle": "Old Title", "keywords": ["b"]},
    ]
    (tmp_path / "words.json").write_text(json.dumps(live), encoding="utf-8")

    summary = quarantine.apply_quarantine("words", [1], execute=False)
    assert summary["moved"] == 1
    assert not (tmp_path / "_stale" / "words.json").exists()
    # live file untouched
    assert json.loads((tmp_path / "words.json").read_text(encoding="utf-8")) == live


def test_apply_quarantine_execute_moves_entry(tmp_path, monkeypatch):
    monkeypatch.setattr(quarantine, "KEYWORDS_DIR", tmp_path)
    monkeypatch.setattr(quarantine, "STALE_DIR", tmp_path / "_stale")

    live = [
        {"pageTitle": "Keep Me", "keywords": ["a"]},
        {"pageTitle": "Old Title", "keywords": ["b"]},
    ]
    (tmp_path / "words.json").write_text(json.dumps(live), encoding="utf-8")

    summary = quarantine.apply_quarantine("words", [1], execute=True)
    assert summary["moved"] == 1
    assert summary["remaining_live"] == 1

    remaining = json.loads((tmp_path / "words.json").read_text(encoding="utf-8"))
    assert remaining == [{"pageTitle": "Keep Me", "keywords": ["a"]}]

    stale = json.loads((tmp_path / "_stale" / "words.json").read_text(encoding="utf-8"))
    assert stale == [{"pageTitle": "Old Title", "keywords": ["b"]}]


def test_apply_quarantine_execute_appends_to_existing_stale_file(tmp_path, monkeypatch):
    monkeypatch.setattr(quarantine, "KEYWORDS_DIR", tmp_path)
    monkeypatch.setattr(quarantine, "STALE_DIR", tmp_path / "_stale")
    (tmp_path / "_stale").mkdir()

    (tmp_path / "_stale" / "words.json").write_text(
        json.dumps([{"pageTitle": "Already Quarantined", "keywords": ["x"]}]), encoding="utf-8"
    )
    (tmp_path / "words.json").write_text(
        json.dumps([{"pageTitle": "New Stale One", "keywords": ["y"]}]), encoding="utf-8"
    )

    quarantine.apply_quarantine("words", [0], execute=True)

    stale = json.loads((tmp_path / "_stale" / "words.json").read_text(encoding="utf-8"))
    assert len(stale) == 2
    titles = {e["pageTitle"] for e in stale}
    assert titles == {"Already Quarantined", "New Stale One"}


def test_apply_quarantine_is_idempotent_on_rerun(tmp_path, monkeypatch):
    """Re-running after a previous quarantine (same entry already moved) must
    not duplicate it in _stale/ even if somehow re-selected."""
    monkeypatch.setattr(quarantine, "KEYWORDS_DIR", tmp_path)
    monkeypatch.setattr(quarantine, "STALE_DIR", tmp_path / "_stale")
    (tmp_path / "_stale").mkdir()

    (tmp_path / "_stale" / "words.json").write_text(
        json.dumps([{"pageTitle": "Dup Title", "keywords": ["a", "b"]}]), encoding="utf-8"
    )
    (tmp_path / "words.json").write_text(
        json.dumps([{"pageTitle": "Dup Title", "keywords": ["b", "a"]}]), encoding="utf-8"
    )

    summary = quarantine.apply_quarantine("words", [0], execute=True)
    assert summary["already_quarantined_skipped"] == 1
    assert summary["newly_added_to_stale"] == 0

    stale = json.loads((tmp_path / "_stale" / "words.json").read_text(encoding="utf-8"))
    assert len(stale) == 1


def test_run_produces_one_summary_per_drifted_family(tmp_path, monkeypatch):
    monkeypatch.setattr(quarantine, "KEYWORDS_DIR", tmp_path)
    monkeypatch.setattr(quarantine, "STALE_DIR", tmp_path / "_stale")

    (tmp_path / "words.json").write_text(
        json.dumps([{"pageTitle": "A", "keywords": []}, {"pageTitle": "B", "keywords": []}, {"pageTitle": "C", "keywords": []}, {"pageTitle": "D", "keywords": []}]),
        encoding="utf-8",
    )

    summaries = quarantine.run(_fake_audit_report(), execute=False)
    assert len(summaries) == 1
    assert summaries[0]["family"] == "words"
