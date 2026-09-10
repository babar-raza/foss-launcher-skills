"""Tests for install_change_budget.py (PKGINSTALL-CHANGE-BUDGET).

Mirrors scripts/seo/tests/test_change_budget.py's own shapes/conventions --
same underlying pattern (static caps + rolling-baseline anomaly check +
explicit warm-up logging), adapted for install-content file counts instead
of SEO metadata-change counts.
"""
from __future__ import annotations

import pytest

import install_change_budget as icb


@pytest.fixture(autouse=True)
def _reset_module_state():
    yield
    icb.configure()


_BUDGETS = {
    "max_files_per_run": 50,
    "max_files_per_locale_per_run": 30,
    "mechanical_migration_max_files_per_run": 50,
    "mechanical_migration_max_files_per_locale_per_run": 30,
    "locale_propagation_max_files_per_run": 400,
    "locale_propagation_max_files_per_locale_per_run": 30,
    "anomaly_multiplier": 3.0,
    "warmup_runs": 3,
}


def _volume(**kwargs):
    return icb.ProposedInstallChangeVolume(total_files=kwargs.pop("total_files", 1), **kwargs)


# ---------------------------------------------------------------------------
# check_static_caps
# ---------------------------------------------------------------------------

def test_static_caps_pass_when_under_every_cap():
    v = _volume(total_files=5, files_by_locale={"en": 5})
    assert icb.check_static_caps(v, _BUDGETS) == []


def test_static_caps_flag_total_files_over_cap():
    v = _volume(total_files=51)
    violations = icb.check_static_caps(v, _BUDGETS)
    assert any("max_files_per_run" in x for x in violations)


def test_static_caps_flag_per_locale_over_cap():
    v = _volume(total_files=31, files_by_locale={"fr": 31})
    violations = icb.check_static_caps(v, _BUDGETS)
    assert any("max_files_per_locale_per_run" in x for x in violations)


def test_mechanism_override_widens_cap_for_locale_propagation():
    """Without the mechanism override, 200 files would exceed the generic
    max_files_per_run (50) -- with locale_propagation's own override (400),
    it must pass, matching the real ST-054 TC-07 precedent (250 locale
    files patched across 3 products in one session)."""
    v = _volume(total_files=200)
    generic_violations = icb.check_static_caps(v, _BUDGETS, mechanism=None)
    assert any("max_files_per_run" in x for x in generic_violations)

    override_violations = icb.check_static_caps(v, _BUDGETS, mechanism="locale_propagation")
    assert override_violations == []


def test_mechanical_migration_override_matches_generic_cap():
    v = _volume(total_files=51)
    violations = icb.check_static_caps(v, _BUDGETS, mechanism="mechanical_migration")
    assert any("max_files_per_run" in x for x in violations)


# ---------------------------------------------------------------------------
# check_anomaly
# ---------------------------------------------------------------------------

def test_anomaly_warmup_mode_is_always_logged_not_silently_skipped():
    status, blocked = icb.check_anomaly(
        "cells", "mechanical_migration", _volume(total_files=5), _BUDGETS, history={},
    )
    assert not blocked
    assert "INACTIVE" in status
    assert "warm-up" in status
    assert "N=0/3" in status


def test_anomaly_passes_within_ceiling(tmp_path):
    history = {"cells/mechanical_migration": [5, 6, 4]}
    status, blocked = icb.check_anomaly(
        "cells", "mechanical_migration", _volume(total_files=10), _BUDGETS, history=history,
    )
    assert not blocked
    assert "PASS" in status


def test_anomaly_blocks_when_proposed_exceeds_ceiling():
    history = {"cells/mechanical_migration": [5, 5, 5]}  # mean=5, ceiling=15
    status, blocked = icb.check_anomaly(
        "cells", "mechanical_migration", _volume(total_files=20), _BUDGETS, history=history,
    )
    assert blocked
    assert "BLOCKED" in status


def test_anomaly_zero_baseline_blocks_any_proposed_change():
    history = {"cells/mechanical_migration": [0, 0, 0]}
    status, blocked = icb.check_anomaly(
        "cells", "mechanical_migration", _volume(total_files=1), _BUDGETS, history=history,
    )
    assert blocked
    assert "baseline=0" in status


def test_anomaly_zero_baseline_and_zero_proposed_passes():
    history = {"cells/mechanical_migration": [0, 0, 0]}
    status, blocked = icb.check_anomaly(
        "cells", "mechanical_migration", _volume(total_files=0), _BUDGETS, history=history,
    )
    assert not blocked


# ---------------------------------------------------------------------------
# check_budget (integration)
# ---------------------------------------------------------------------------

def test_check_budget_allows_within_budget():
    verdict = icb.check_budget(
        "cells", "mechanical_migration", _volume(total_files=5),
        budgets=_BUDGETS, history={},
    )
    assert verdict.allowed
    assert verdict.static_cap_violations == []


def test_check_budget_refuses_on_static_cap_violation_fail_closed():
    verdict = icb.check_budget(
        "cells", "mechanical_migration", _volume(total_files=51),
        budgets=_BUDGETS, history={},
    )
    assert not verdict.allowed
    assert verdict.reason == "static cap(s) exceeded"
    assert verdict.static_cap_violations != []


def test_check_budget_refuses_on_anomaly_violation():
    history = {"cells/mechanical_migration": [5, 5, 5]}
    verdict = icb.check_budget(
        "cells", "mechanical_migration", _volume(total_files=20),
        budgets=_BUDGETS, history=history,
    )
    assert not verdict.allowed
    assert verdict.reason == "anomaly check blocked run"


def test_check_budget_reports_static_violations_even_when_anomaly_also_fails():
    """Static caps are checked (and fully reported) regardless of whether
    the anomaly check also fails -- a caller must see the complete
    picture, not just the first failure."""
    history = {"cells/mechanical_migration": [1, 1, 1]}  # ceiling = 3
    verdict = icb.check_budget(
        "cells", "mechanical_migration", _volume(total_files=51),
        budgets=_BUDGETS, history=history,
    )
    assert not verdict.allowed
    assert verdict.static_cap_violations != []
    assert "BLOCKED" in verdict.anomaly_status


# ---------------------------------------------------------------------------
# record_run / load_history (real file I/O, isolated via configure())
# ---------------------------------------------------------------------------

def test_record_run_persists_and_load_history_reads_it_back(tmp_path):
    icb.configure(repo_root=tmp_path)
    icb.record_run("cells", "mechanical_migration", 5)
    icb.record_run("cells", "mechanical_migration", 6)
    history = icb.load_history()
    assert history["cells/mechanical_migration"] == [5, 6]


def test_load_history_missing_file_returns_empty_dict(tmp_path):
    icb.configure(repo_root=tmp_path)
    assert icb.load_history() == {}


def test_history_lives_under_reports_package_reconciliation(tmp_path):
    icb.configure(repo_root=tmp_path)
    icb.record_run("cells", "mechanical_migration", 1)
    assert icb.HISTORY_PATH.exists()
    assert "package-reconciliation" in str(icb.HISTORY_PATH)
    assert "data" not in icb.HISTORY_PATH.relative_to(tmp_path).parts


# ---------------------------------------------------------------------------
# load_budgets against the real, checked-in config
# ---------------------------------------------------------------------------

def test_load_budgets_reads_the_real_config_file():
    budgets = icb.load_budgets()
    assert budgets["max_files_per_run"] == 50
    assert budgets["locale_propagation_max_files_per_run"] == 400
    assert budgets["warmup_runs"] == 3
