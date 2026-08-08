"""test_aspose_com_targets_watch.py — Unit tests for aspose_com_targets_watch.py.

Mission MT022-2026-08-06-ASPOSE-COM-TARGETS-HARDENING, TC-04.

Covers the same-run multi-check regression-confirmation logic (deliberately
NOT a cross-run persisted debounce counter -- see the module's own docstring
for why that package_publish_watch.py pattern was not copied), the
detection-only discipline (never writes data/aspose_com_targets.json), and
main()'s exit-code contract.

Run:
    python -m pytest scripts/pipeline/tests/test_aspose_com_targets_watch.py -v
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from commands.ops.aspose_com_targets_watch import (  # noqa: E402
    check_for_regressions, format_issue_body, main, configure, RegressionCheckResult,
)


def _tm_with_one_platform_entry(http_status: int = 200, url: str = "https://docs.aspose.com/cad/net/") -> dict:
    return {
        "schema_version": "1.0",
        "provenance": {"generated_at": "2026-08-06T00:00:00Z", "total_targets": 1},
        "targets": {
            "docs.aspose.com": {
                "families": {},
                "platforms": {
                    "cad/net": {"url": url, "http_status": http_status, "redirect_chain": []},
                },
            },
        },
        "all_urls": {},
        "unavailable_sources": [],
        "family_platform_matrix": {},
    }


def _tm_with_n_platform_entries(n: int, http_status: int = 200) -> dict:
    """N distinct, independently-keyed 200 entries under one subdomain --
    used for time-budget tests where the loop needs multiple checkable
    entries to observe an early stop."""
    platforms = {
        f"fam{i}/plat": {"url": f"https://docs.aspose.com/fam{i}/plat/", "http_status": http_status, "redirect_chain": []}
        for i in range(n)
    }
    return {
        "schema_version": "1.0",
        "provenance": {"generated_at": "2026-08-06T00:00:00Z", "total_targets": n},
        "targets": {"docs.aspose.com": {"families": {}, "platforms": platforms}},
        "all_urls": {},
        "unavailable_sources": [],
        "family_platform_matrix": {},
    }


def setup_function(_fn):
    configure()  # reset the sleep seam between tests


def teardown_function(_fn):
    configure()


def test_no_regression_when_entry_still_resolves():
    tm = _tm_with_one_platform_entry(200)
    session = MagicMock()

    def fake_verify(url, sess, **kw):
        return 200, [], url, "head", 0

    configure(sleep_fn=lambda s: None)
    result = check_for_regressions(tm, session, verify_fn=fake_verify)
    assert result.regressions == []
    assert result.entries_checked == 1
    assert result.entries_skipped == 0
    assert result.budget_exceeded is False


def test_confirms_regression_only_after_two_independent_non_200_checks():
    tm = _tm_with_one_platform_entry(200, url="https://docs.aspose.com/cad/net/")
    session = MagicMock()
    calls = []

    def fake_verify(url, sess, **kw):
        calls.append(url)
        return 502, [], url, "head", 0  # both checks agree: down

    sleeps = []
    configure(sleep_fn=lambda s: sleeps.append(s))
    result = check_for_regressions(tm, session, verify_fn=fake_verify)

    assert len(result.regressions) == 1
    r = result.regressions[0]
    assert r["subdomain"] == "docs.aspose.com"
    assert r["key"] == "cad/net"
    assert r["confirmed_status"] == 502
    assert len(calls) == 2, "must independently re-check before confirming, not trust a single observation"
    assert sleeps == [5], "must wait between the two independent checks (the same-run confirmation window)"


def test_transient_dip_that_recovers_is_not_reported():
    """First check sees a dip, but the independent recheck sees 200 again --
    must NOT be reported as a regression (this is exactly the class of false
    positive a single-observation watcher would have produced)."""
    tm = _tm_with_one_platform_entry(200)
    session = MagicMock()
    results = iter([502, 200])

    def fake_verify(url, sess, **kw):
        return next(results), [], url, "head", 0

    configure(sleep_fn=lambda s: None)
    result = check_for_regressions(tm, session, verify_fn=fake_verify)
    assert result.regressions == [], "a recheck that resolves to 200 must not be reported"


def test_entries_not_currently_200_are_never_watched():
    """This watcher only cares about 200 -> not-200 drift -- an entry that's
    already non-200 in the registry is someone else's problem (the original
    fetch/backfill), not this watcher's."""
    tm = _tm_with_one_platform_entry(404)
    session = MagicMock()
    verify_calls = []

    def fake_verify(url, sess, **kw):
        verify_calls.append(url)
        return 200, [], url, "head", 0

    result = check_for_regressions(tm, session, verify_fn=fake_verify)
    assert result.regressions == []
    assert verify_calls == [], "an already-non-200 entry must never even be checked by this watcher"
    assert result.total_entries == 0, "an already-non-200 entry doesn't count toward the checkable total either"


def test_rerun_idempotent_against_unchanged_live_state():
    """Running check_for_regressions twice against the same (mocked) live
    state must produce identical results -- no flapping."""
    tm = _tm_with_one_platform_entry(200)
    session = MagicMock()

    def fake_verify(url, sess, **kw):
        return 404, [], url, "head", 0

    configure(sleep_fn=lambda s: None)
    first_run = check_for_regressions(tm, session, verify_fn=fake_verify)
    second_run = check_for_regressions(tm, session, verify_fn=fake_verify)
    assert first_run == second_run


def test_format_issue_body_includes_key_fields():
    result = RegressionCheckResult(regressions=[{
        "subdomain": "docs.aspose.com", "section": "platforms", "key": "cad/net",
        "url": "https://docs.aspose.com/cad/net/", "previous_status": 200,
        "first_recheck_status": 502, "confirmed_status": 502,
    }], entries_checked=1, entries_skipped=0, total_entries=1, budget_exceeded=False)
    body = format_issue_body(result)
    assert "cad/net" in body
    assert "docs.aspose.com" in body
    assert "502" in body
    assert "fetch_aspose_com_targets.py" in body, "must point the reader at the actual write-path script"
    assert "Partial run" not in body, "a complete run must not show the partial-coverage warning"


def test_format_issue_body_shows_partial_coverage_warning_when_budget_exceeded():
    result = RegressionCheckResult(
        regressions=[], entries_checked=3, entries_skipped=7, total_entries=10, budget_exceeded=True,
    )
    body = format_issue_body(result)
    assert "Partial run" in body
    assert "3/10" in body
    assert "7 entries" in body
    assert "No confirmed regressions among the entries checked" in body


# ---------------------------------------------------------------------------
# Wall-clock time budget (TC-09, MT022 pilot-rerun Finding C)
#
# Live-observed in production: a real workflow_dispatch run (31120889071,
# 2026-08-06) was auto-CANCELLED by GitHub Actions' own timeout-minutes:15
# after this watcher's retry+recheck logic compounded with no internal
# bound, producing ZERO output. These tests use an injected now_fn (a fake
# monotonic clock) rather than real time.monotonic(), so they run instantly
# and deterministically.
# ---------------------------------------------------------------------------

def test_budget_exceeded_stops_starting_new_entries():
    tm = _tm_with_n_platform_entries(5)
    session = MagicMock()
    verify_calls = []

    def fake_verify(url, sess, **kw):
        verify_calls.append(url)
        return 200, [], url, "head", 0

    # Clock is read once at loop start, then once per entry's pre-check
    # (never inside verify_fn). start=0; entry0's pre-check reads 0 (still
    # within budget, proceeds); entry1's pre-check reads 1000 (past the
    # 600s budget) -- so exactly 1 of 5 entries should be checked.
    clock = iter([0.0, 0.0] + [1000.0] * 20)
    configure(sleep_fn=lambda s: None, time_budget_seconds=600, now_fn=lambda: next(clock))

    result = check_for_regressions(tm, session, verify_fn=fake_verify)

    assert result.budget_exceeded is True
    assert result.entries_checked == 1, "the first entry (checked while still within budget) should complete"
    assert result.entries_skipped == 4
    assert result.total_entries == 5
    assert len(verify_calls) == 1, "no new entry's verify_fn should be called once the budget is exhausted"


def test_budget_not_exceeded_when_clock_stays_within_budget():
    tm = _tm_with_n_platform_entries(5)
    session = MagicMock()

    def fake_verify(url, sess, **kw):
        return 200, [], url, "head", 0

    configure(sleep_fn=lambda s: None, time_budget_seconds=600, now_fn=lambda: 1.0)  # constant, always "1 second elapsed"

    result = check_for_regressions(tm, session, verify_fn=fake_verify)

    assert result.budget_exceeded is False
    assert result.entries_checked == 5
    assert result.entries_skipped == 0


def test_in_flight_entry_is_never_aborted_mid_check():
    """The budget is only checked BEFORE starting a new entry -- an entry
    already in flight (including its same-run recheck sleep+second call,
    which never re-reads the clock) must always be allowed to finish, even
    if the budget is exhausted by the time the NEXT entry is considered.

    Clock is called exactly once per loop iteration (the pre-check) plus
    once at the very start -- never inside verify_fn or between an entry's
    two checks -- so for 2 entries the full call sequence is exactly
    [start, entry0's pre-check, entry1's pre-check]."""
    tm = _tm_with_n_platform_entries(2)
    session = MagicMock()
    verify_calls = []

    def fake_verify(url, sess, **kw):
        verify_calls.append(url)
        return 502, [], url, "head", 0  # triggers the recheck path (2 verify_fn calls for entry 0)

    clock = iter([0.0, 0.0, 600.0])  # start=0; entry0 pre-check: 0-0=0<600 (proceeds); entry1 pre-check: 600-0=600>=600 (stop)
    configure(sleep_fn=lambda s: None, time_budget_seconds=600, now_fn=lambda: next(clock))

    result = check_for_regressions(tm, session, verify_fn=fake_verify)

    assert result.entries_checked == 1, "entry 0 must fully complete (both its own checks) before entry 1 is even considered"
    assert len(verify_calls) == 2, "entry 0's own confirm-recheck must run to completion, not be cut short"
    assert len(result.regressions) == 1, "entry 0's confirmed regression must still be reported despite the run ending early"
    assert result.entries_skipped == 1
    assert result.budget_exceeded is True


def test_main_exit_1_on_budget_exceeded_even_with_zero_regressions(tmp_path):
    tm = _tm_with_n_platform_entries(3)

    def fake_verify(url, sess, **kw):
        return 200, [], url, "head", 0  # perfectly healthy -- would normally be exit 0

    clock = iter([0.0, 0.0] + [1000.0] * 10)  # entry0 checked within budget; entry1's pre-check exceeds it
    configure(sleep_fn=lambda s: None, time_budget_seconds=600, now_fn=lambda: next(clock))

    exit_code = main(["--repo-root", str(tmp_path)], target_map=tm, verify_fn=fake_verify)

    assert exit_code == 1, "a partial run must be reported (exit 1) even with no confirmed regressions -- silence is the failure mode being fixed"


def test_main_full_coverage_zero_regressions_still_exits_0(tmp_path):
    """Sanity check: the budget feature must not change behavior for a normal, complete run."""
    tm = _tm_with_n_platform_entries(3)

    def fake_verify(url, sess, **kw):
        return 200, [], url, "head", 0

    configure(sleep_fn=lambda s: None, time_budget_seconds=600, now_fn=lambda: 1.0)
    exit_code = main(["--repo-root", str(tmp_path)], target_map=tm, verify_fn=fake_verify)
    assert exit_code == 0


def test_main_never_writes_the_registry_file(tmp_path):
    """Detection-only discipline: main() must never write
    data/aspose_com_targets.json, even when regressions are confirmed."""
    tm = _tm_with_one_platform_entry(200)

    def fake_verify(url, sess, **kw):
        return 404, [], url, "head", 0

    configure(sleep_fn=lambda s: None)
    exit_code = main(["--repo-root", str(tmp_path)], target_map=tm, verify_fn=fake_verify)

    assert exit_code == 1
    assert not (tmp_path / "data" / "aspose_com_targets.json").exists(), (
        "this watcher must never write the registry -- only fetch_aspose_com_targets.py owns that write path"
    )


def test_main_exit_0_when_registry_missing(tmp_path):
    exit_code = main(["--repo-root", str(tmp_path)])
    assert exit_code == 0


def test_main_writes_issue_body_file(tmp_path):
    tm = _tm_with_one_platform_entry(200)

    def fake_verify(url, sess, **kw):
        return 502, [], url, "head", 0

    configure(sleep_fn=lambda s: None)
    out_path = tmp_path / "issue.md"
    exit_code = main(
        ["--repo-root", str(tmp_path), "--issue-body-out", str(out_path)],
        target_map=tm, verify_fn=fake_verify,
    )

    assert exit_code == 1
    assert out_path.exists()
    assert "cad/net" in out_path.read_text(encoding="utf-8")
