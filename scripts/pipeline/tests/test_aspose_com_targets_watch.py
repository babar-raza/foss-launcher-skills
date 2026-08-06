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
    check_for_regressions, format_issue_body, main, configure,
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
    regressions = check_for_regressions(tm, session, verify_fn=fake_verify)
    assert regressions == []


def test_confirms_regression_only_after_two_independent_non_200_checks():
    tm = _tm_with_one_platform_entry(200, url="https://docs.aspose.com/cad/net/")
    session = MagicMock()
    calls = []

    def fake_verify(url, sess, **kw):
        calls.append(url)
        return 502, [], url, "head", 0  # both checks agree: down

    sleeps = []
    configure(sleep_fn=lambda s: sleeps.append(s))
    regressions = check_for_regressions(tm, session, verify_fn=fake_verify)

    assert len(regressions) == 1
    r = regressions[0]
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
    regressions = check_for_regressions(tm, session, verify_fn=fake_verify)
    assert regressions == [], "a recheck that resolves to 200 must not be reported"


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

    regressions = check_for_regressions(tm, session, verify_fn=fake_verify)
    assert regressions == []
    assert verify_calls == [], "an already-non-200 entry must never even be checked by this watcher"


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
    regressions = [{
        "subdomain": "docs.aspose.com", "section": "platforms", "key": "cad/net",
        "url": "https://docs.aspose.com/cad/net/", "previous_status": 200,
        "first_recheck_status": 502, "confirmed_status": 502,
    }]
    body = format_issue_body(regressions)
    assert "cad/net" in body
    assert "docs.aspose.com" in body
    assert "502" in body
    assert "fetch_aspose_com_targets.py" in body, "must point the reader at the actual write-path script"


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
