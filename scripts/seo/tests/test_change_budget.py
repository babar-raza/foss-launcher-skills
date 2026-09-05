"""Tests for change_budget.py (Contract G, SEO-CHANGE-BUDGET-GUARD, Finding #75/#80)."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[2]
_PIPELINE = _SCRIPTS / "pipeline"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
if str(_PIPELINE) not in sys.path:
    sys.path.insert(0, str(_PIPELINE))

import seo.pipeline.change_budget as cb  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_module_state():
    yield
    cb.configure()


_BUDGETS = {
    "max_pages_per_run": 15,
    "max_pages_per_site_per_run": 10,
    "max_title_changes_per_run": 10,
    "max_description_changes_per_run": 15,
    "max_total_metadata_changes_per_run": 20,
    "anomaly_multiplier": 3.0,
    "warmup_runs": 3,
    "max_cross_mechanism_changes_per_family_per_week": 20,
}


def _volume(**kwargs):
    return cb.ProposedChangeVolume(total_items=kwargs.pop("total_items", 1), **kwargs)


# ---------------------------------------------------------------------------
# check_static_caps
# ---------------------------------------------------------------------------

def test_static_caps_pass_when_under_every_cap():
    v = _volume(total_items=5, items_by_scope={"kb.aspose.org": 5}, title_changes=2, description_changes=3)
    assert cb.check_static_caps(v, _BUDGETS) == []


def test_static_caps_flag_total_pages_over_cap():
    v = _volume(total_items=16)
    violations = cb.check_static_caps(v, _BUDGETS)
    assert any("max_pages_per_run" in x for x in violations)


def test_static_caps_flag_per_site_over_cap():
    v = _volume(total_items=11, items_by_scope={"kb.aspose.org": 11})
    violations = cb.check_static_caps(v, _BUDGETS)
    assert any("max_pages_per_site_per_run" in x for x in violations)


def test_static_caps_flag_title_changes_over_cap():
    v = _volume(total_items=11, title_changes=11)
    violations = cb.check_static_caps(v, _BUDGETS)
    assert any("max_title_changes_per_run" in x for x in violations)


def test_static_caps_flag_description_changes_over_cap():
    v = _volume(total_items=16, description_changes=16)
    violations = cb.check_static_caps(v, _BUDGETS)
    assert any("max_description_changes_per_run" in x for x in violations)


def test_static_caps_flag_total_metadata_changes_over_cap_even_when_split_under_each():
    # 9 title + 14 description = 23 total, each individually under its own
    # cap (10/15) but over the combined cap (20).
    v = _volume(total_items=23, title_changes=9, description_changes=14)
    violations = cb.check_static_caps(v, _BUDGETS)
    assert any("max_total_metadata_changes_per_run" in x for x in violations)


def test_static_caps_report_multiple_violations_simultaneously():
    v = _volume(total_items=100, items_by_scope={"kb.aspose.org": 100}, title_changes=50, description_changes=50)
    violations = cb.check_static_caps(v, _BUDGETS)
    assert len(violations) >= 4


def test_mechanism_override_replaces_generic_cap_when_present():
    budgets = dict(_BUDGETS, schema_a_refresh_max_pages_per_run=150, schema_a_refresh_max_pages_per_site_per_run=150)
    v = _volume(total_items=105, items_by_scope={"3d": 105})
    # would fail the generic caps (15/10) but the schema_a_refresh overrides (150/150) allow it
    violations = cb.check_static_caps(v, budgets, mechanism="schema_a_refresh")
    assert violations == []


def test_mechanism_without_override_falls_back_to_generic_cap():
    budgets = dict(_BUDGETS, schema_a_refresh_max_pages_per_run=150)
    v = _volume(total_items=16)
    # title_description_writes has no override -- must still use the generic 15
    violations = cb.check_static_caps(v, budgets, mechanism="title_description_writes")
    assert any("max_pages_per_run" in x for x in violations)


def test_mechanism_override_applies_only_to_pages_caps_not_metadata_caps():
    """schema_a_refresh has no title/description split -- its volume always
    carries title_changes=description_changes=0, so the metadata caps are
    inert for it by construction, not because they were overridden."""
    budgets = dict(_BUDGETS, schema_a_refresh_max_pages_per_run=150, schema_a_refresh_max_pages_per_site_per_run=150)
    v = _volume(total_items=105, items_by_scope={"3d": 105})
    verdict = cb.check_budget("3d", "schema_a_refresh", v, budgets=budgets, history={})
    assert verdict.allowed


def test_real_pr69_regeneration_volume_passes_schema_a_refresh_override():
    """Regression pin for a real historical run: PR #69 (commit c27b98fc03,
    2026-08-30, cited in this mission's own Finding #4) regenerated 105
    entries in keywords/3d.json in one legitimate run while completing that
    family's platform-label migration -- confirmed live via
    check_merge_safety._count_changed_entries against the real commit.
    Gate 5, using the real checked-in change_budgets.yaml, must not have
    retroactively blocked this already-successful production run."""
    budgets = cb.load_budgets()
    v = _volume(total_items=105, items_by_scope={"3d": 105})
    verdict = cb.check_budget("3d", "schema_a_refresh", v, budgets=budgets, history={})
    assert verdict.allowed, verdict.static_cap_violations


# ---------------------------------------------------------------------------
# check_anomaly -- warm-up + rolling baseline
# ---------------------------------------------------------------------------

def test_anomaly_inactive_during_warmup_with_no_history():
    v = _volume(total_items=1000)  # would be a wild anomaly if the check were active
    status, blocked = cb.check_anomaly("tex", "schema_a_refresh", v, _BUDGETS, history={})
    assert not blocked
    assert "INACTIVE" in status
    assert "N=0/3" in status


def test_anomaly_inactive_counts_up_through_warmup_runs():
    history = {"tex/schema_a_refresh": [5]}
    v = _volume(total_items=1000)
    status, blocked = cb.check_anomaly("tex", "schema_a_refresh", v, _BUDGETS, history=history)
    assert not blocked
    assert "N=1/3" in status


def test_anomaly_active_and_passes_once_warmup_complete_and_within_ceiling():
    history = {"tex/title_description_writes": [10, 10, 10]}  # mean=10, ceiling=30
    v = _volume(total_items=20, title_changes=20)
    status, blocked = cb.check_anomaly("tex", "title_description_writes", v, _BUDGETS, history=history)
    # title_description_writes measure = total_metadata_changes = 20 <= 30
    assert not blocked
    assert "PASS" in status


def test_anomaly_blocks_once_warmup_complete_and_over_ceiling():
    history = {"tex/schema_a_refresh": [10, 10, 10]}  # mean=10, ceiling=30
    v = _volume(total_items=31)
    status, blocked = cb.check_anomaly("tex", "schema_a_refresh", v, _BUDGETS, history=history)
    assert blocked
    assert "BLOCKED" in status


def test_anomaly_zero_baseline_blocks_any_nonzero_proposal():
    history = {"tex/schema_a_refresh": [0, 0, 0]}
    v = _volume(total_items=1)
    status, blocked = cb.check_anomaly("tex", "schema_a_refresh", v, _BUDGETS, history=history)
    assert blocked
    assert "baseline=0" in status


def test_anomaly_zero_baseline_passes_zero_proposal():
    history = {"tex/schema_a_refresh": [0, 0, 0]}
    v = _volume(total_items=0)
    status, blocked = cb.check_anomaly("tex", "schema_a_refresh", v, _BUDGETS, history=history)
    assert not blocked
    assert "PASS" in status


def test_anomaly_is_scoped_per_family_and_mechanism_independently():
    history = {"tex/schema_a_refresh": [5, 5, 5], "cells/schema_a_refresh": [50, 50, 50]}
    v = _volume(total_items=20)
    tex_status, tex_blocked = cb.check_anomaly("tex", "schema_a_refresh", v, _BUDGETS, history=history)
    cells_status, cells_blocked = cb.check_anomaly("cells", "schema_a_refresh", v, _BUDGETS, history=history)
    assert tex_blocked  # 20 > 5*3=15
    assert not cells_blocked  # 20 <= 50*3


def test_anomaly_does_not_confuse_mechanisms_for_the_same_family():
    history = {"tex/schema_a_refresh": [100, 100, 100]}
    v = _volume(total_items=20)
    # tex/title_description_writes has NO history of its own -- must be its
    # own independent warm-up, not borrow schema_a_refresh's baseline.
    status, blocked = cb.check_anomaly("tex", "title_description_writes", v, _BUDGETS, history=history)
    assert not blocked
    assert "N=0/3" in status


# ---------------------------------------------------------------------------
# check_budget -- combined entry point
# ---------------------------------------------------------------------------

def test_check_budget_allowed_when_static_and_anomaly_both_pass():
    v = _volume(total_items=5)
    verdict = cb.check_budget("tex", "schema_a_refresh", v, budgets=_BUDGETS, history={})
    assert verdict.allowed
    assert verdict.static_cap_violations == []


def test_check_budget_blocked_by_static_cap_reports_violations():
    v = _volume(total_items=100)
    verdict = cb.check_budget("tex", "schema_a_refresh", v, budgets=_BUDGETS, history={})
    assert not verdict.allowed
    assert verdict.static_cap_violations != []
    assert "static" in verdict.reason


def test_check_budget_blocked_by_anomaly_when_static_caps_pass():
    history = {"tex/schema_a_refresh": [1, 1, 1]}  # mean=1, ceiling=3
    v = _volume(total_items=5)  # under static cap (15), over anomaly ceiling
    verdict = cb.check_budget("tex", "schema_a_refresh", v, budgets=_BUDGETS, history=history)
    assert not verdict.allowed
    assert verdict.static_cap_violations == []
    assert "anomaly" in verdict.reason


def test_check_budget_reports_static_violations_even_when_anomaly_also_blocked():
    """Static violations must always be visible in the verdict, regardless
    of whether the anomaly check would also have blocked the run."""
    history = {"tex/schema_a_refresh": [1, 1, 1]}
    v = _volume(total_items=100)  # blows both static cap AND anomaly ceiling
    verdict = cb.check_budget("tex", "schema_a_refresh", v, budgets=_BUDGETS, history=history)
    assert not verdict.allowed
    assert verdict.static_cap_violations != []
    assert verdict.reason == "static cap(s) exceeded"


# ---------------------------------------------------------------------------
# record_run / load_history -- atomic persistence
# ---------------------------------------------------------------------------

def test_record_run_appends_and_persists(tmp_path):
    cb.configure(repo_root=tmp_path)
    cb.record_run("tex", "schema_a_refresh", 5)
    cb.record_run("tex", "schema_a_refresh", 7)
    history = cb.load_history()
    assert history["tex/schema_a_refresh"] == [5, 7]
    on_disk = json.loads(cb.HISTORY_PATH.read_text(encoding="utf-8"))
    assert on_disk == history


def test_record_run_keeps_families_and_mechanisms_independent(tmp_path):
    cb.configure(repo_root=tmp_path)
    cb.record_run("tex", "schema_a_refresh", 5)
    cb.record_run("cells", "schema_a_refresh", 9)
    cb.record_run("tex", "title_description_writes", 2)
    history = cb.load_history()
    assert history == {
        "tex/schema_a_refresh": [5],
        "cells/schema_a_refresh": [9],
        "tex/title_description_writes": [2],
    }


def test_load_history_returns_empty_dict_when_file_absent(tmp_path):
    cb.configure(repo_root=tmp_path)
    assert cb.load_history() == {}


def test_load_history_returns_empty_dict_on_corrupt_json(tmp_path):
    cb.configure(repo_root=tmp_path)
    cb.HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    cb.HISTORY_PATH.write_text("{not valid", encoding="utf-8")
    assert cb.load_history() == {}


def test_config_path_is_never_moved_by_configure(tmp_path):
    """change_budgets.yaml is a real, checked-in resource -- configure()
    must only redirect state paths (history/cross-mechanism), never the
    config path, or an isolated test/production caller with a different
    repo_root would silently lose access to the real budgets."""
    before = cb.CONFIG_PATH
    cb.configure(repo_root=tmp_path)
    assert cb.CONFIG_PATH == before
    assert cb.HISTORY_PATH == tmp_path / "reports" / "seo" / "change_budget_history.json"


# ---------------------------------------------------------------------------
# Cross-mechanism weekly counter
# ---------------------------------------------------------------------------

def test_cross_mechanism_budget_allows_first_change_in_a_week():
    allowed, reason = cb.check_cross_mechanism_budget(
        "tex", 5, _BUDGETS, week_start="2026-09-01", cross_state={},
    )
    assert allowed


def test_cross_mechanism_budget_blocks_when_combined_total_exceeds_cap():
    cross_state = {"tex/2026-09-01": 18}
    allowed, reason = cb.check_cross_mechanism_budget(
        "tex", 5, _BUDGETS, week_start="2026-09-01", cross_state=cross_state,
    )
    assert not allowed
    assert "18" in reason and "5" in reason


def test_cross_mechanism_budget_is_scoped_per_family_and_week():
    cross_state = {"tex/2026-09-01": 18}
    # different family, same week -- unaffected by tex's near-cap usage
    allowed, _ = cb.check_cross_mechanism_budget(
        "cells", 5, _BUDGETS, week_start="2026-09-01", cross_state=cross_state,
    )
    assert allowed
    # same family, different week -- also unaffected
    allowed2, _ = cb.check_cross_mechanism_budget(
        "tex", 5, _BUDGETS, week_start="2026-09-08", cross_state=cross_state,
    )
    assert allowed2


def test_record_cross_mechanism_change_accumulates(tmp_path):
    cb.configure(repo_root=tmp_path)
    cb.record_cross_mechanism_change("tex", 5, week_start="2026-09-01")
    cb.record_cross_mechanism_change("tex", 3, week_start="2026-09-01")
    state = json.loads(cb.CROSS_MECHANISM_PATH.read_text(encoding="utf-8"))
    assert state["tex/2026-09-01"] == 8


def test_week_start_for_returns_monday():
    # 2026-09-05 is a Saturday (per the mission's own real-world dates this
    # session) -- its week's Monday is 2026-08-31.
    dt = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)
    assert cb.week_start_for(dt) == "2026-08-31"


def test_week_start_for_monday_is_itself():
    dt = datetime(2026, 8, 31, 0, 0, tzinfo=timezone.utc)
    assert cb.week_start_for(dt) == "2026-08-31"


# ---------------------------------------------------------------------------
# load_budgets -- real config file, real repo
# ---------------------------------------------------------------------------

def test_load_budgets_reads_the_real_checked_in_config():
    budgets = cb.load_budgets()
    for key in (
        "max_pages_per_run", "max_pages_per_site_per_run",
        "max_title_changes_per_run", "max_description_changes_per_run",
        "max_total_metadata_changes_per_run", "anomaly_multiplier",
        "warmup_runs", "max_cross_mechanism_changes_per_family_per_week",
        "schema_a_refresh_max_pages_per_run", "schema_a_refresh_max_pages_per_site_per_run",
    ):
        assert key in budgets, f"missing {key} in real change_budgets.yaml"
