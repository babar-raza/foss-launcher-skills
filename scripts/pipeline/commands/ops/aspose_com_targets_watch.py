"""aspose_com_targets_watch.py — Scheduled drift detection for
data/aspose_com_targets.json (the aspose.com reciprocal-backlink target map).

Mission MT022-2026-08-06-ASPOSE-COM-TARGETS-HARDENING, TC-04.

WHY THIS EXISTS
----------------
fetch_aspose_com_targets.py (the producer of data/aspose_com_targets.json) has
no scheduled re-verification -- confirmed live: zero .github/workflows/*.yml
reference it, it is purely operator-invoked. This is the direct mechanism by
which "5 status regressions" (cells/typescript, email/python, page/python,
tex/python: 404; cad/net: 502) accumulated silently over 6+ weeks before a
redirect-bug-fix commit (e40ed6b509) incidentally found them -- and even then,
the finding was only ever written to that commit's message, never to any
tracked artifact, because nothing routes a drift finding anywhere durable.

WHY THIS IS *NOT* A COPY OF package_publish_watch.py's DEBOUNCE PATTERN
--------------------------------------------------------------------------
package_publish_watch.py (the sibling watcher for data/package_registry.json)
uses a CROSS-RUN persisted debounce counter (apply_debounce /
apply_drift_debounce, REQUIRED_CONSECUTIVE_CHECKS=2): each scheduled run
increments a counter stored back to disk, and only flips/reports once the
counter reaches 2 across separate runs. Close reading of that watcher's own
deployed CI workflow (package-publish-watch.yml) found this counter is
deliberately never persisted from CI (`--no-persist-counters`) -- meaning it
is provably inert from cron alone; the counter can never reach 2 without a
human/agent running the skill interactively at least twice. Copying that
shape here would silently reproduce the exact "nothing is really watching"
problem this watcher exists to fix.

Instead: confirmation happens WITHIN a single run, not across runs. Every
currently-`http_status: 200` entry in the committed registry ("last confirmed
good") is re-verified live; any entry that comes back non-200 gets one
additional independent re-check (a fresh verify_url() call, not just relying
on verify_url()'s own internal transient-status retry loop, since that retry
loop deliberately does NOT retry a 404 -- a real "not found" signal by
design, but this watcher wants an extra outer confirmation specifically
because a false regression report is costly to chase). Only entries where
BOTH independent checks agree on non-200 are reported. No cross-run state,
no persisted counter, no flapping risk from counter resets.

DETECTION-ONLY DISCIPLINE (matches package_publish_watch.py)
--------------------------------------------------------------
This script NEVER writes data/aspose_com_targets.json itself. It only
produces a report / GitHub issue body listing confirmed regressions. A
human/agent then runs fetch_aspose_com_targets.py interactively to persist
the correction, through the normal ST-021-aware commit path (CLAUDE.md
isolated-temp-index git-plumbing). This keeps the write path single-owner
(fetch_aspose_com_targets.py) and avoids a second, independent writer to the
same file.

CLI:
    PYTHONPATH=scripts/pipeline .venv/Scripts/python -m commands.ops.aspose_com_targets_watch
    PYTHONPATH=scripts/pipeline .venv/Scripts/python -m commands.ops.aspose_com_targets_watch --issue-body-out path.md

Exit codes:
    0   no confirmed regression, full coverage (nothing to report)
    1   at least one confirmed regression, OR the internal time budget was
        exceeded (partial coverage -- reported even with zero regressions
        among the entries actually checked; see TC-09/RegressionCheckResult)
"""
from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))
_LIB_DIR = str(_PIPELINE_ROOT / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

try:
    import requests
except ImportError:
    print("ERROR: 'requests' package required. Install with: pip install requests", file=sys.stderr)
    sys.exit(1)

from backlink_targets import load_target_map  # noqa: E402
from commands.ops.fetch_aspose_com_targets import verify_url  # noqa: E402

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[4]
USER_AGENT = "aspose-backlink-governance-watch/1.0"

# Same-run re-check interval -- deliberately short (this is an in-run
# confirmation, not a cross-day debounce). configure() seam so tests never
# sleep for real.
_RECHECK_DELAY_SECONDS = 5
_sleep_fn = time.sleep

# Wall-clock budget (TC-09, MT022 pilot-rerun Finding C): live-observed in
# production -- a real workflow_dispatch run (31120889071, 2026-08-06) was
# auto-CANCELLED by GitHub Actions' own timeout-minutes:15 after the retry +
# same-run-recheck logic (TC-01 x TC-04) compounded with no internal bound,
# during a window where a meaningful fraction of the ~282 registered entries
# hit transient conditions. A cancelled job produces ZERO output -- no clean
# result, no regression report, nothing -- exactly on the days (broad
# aspose.com slowness) a signal matters most. Two calm runs on either side of
# it took 2m22s and 1m44s; this one hit 15m03s. Default kept safely below the
# workflow's own 15-minute job timeout, leaving margin for checkout/pip-
# install/freshness-check/issue-creation steps that also share that budget.
_TIME_BUDGET_SECONDS = 600  # 10 minutes
_now_fn = time.monotonic


def configure(*, sleep_fn=None, recheck_delay=None, time_budget_seconds=None, now_fn=None) -> None:
    """configure() seam (AGENTS.md 16) -- override the same-run recheck delay,
    its sleep function, the wall-clock time budget, and the clock function,
    for testing, without monkeypatching time.sleep/time.monotonic."""
    global _sleep_fn, _RECHECK_DELAY_SECONDS, _TIME_BUDGET_SECONDS, _now_fn
    _sleep_fn = sleep_fn if sleep_fn is not None else time.sleep
    if recheck_delay is not None:
        _RECHECK_DELAY_SECONDS = recheck_delay
    _TIME_BUDGET_SECONDS = time_budget_seconds if time_budget_seconds is not None else 600
    _now_fn = now_fn if now_fn is not None else time.monotonic


@dataclass
class RegressionCheckResult:
    """Return type for check_for_regressions() (TC-09). Replaces a bare list
    so a budget-exceeded partial run is structurally distinguishable from a
    complete run that simply found nothing -- silently returning an empty
    list either way would hide exactly the failure mode this taskcard exists
    to surface."""
    regressions: list[dict[str, Any]] = field(default_factory=list)
    entries_checked: int = 0
    entries_skipped: int = 0
    total_entries: int = 0
    budget_exceeded: bool = False


def _iter_entries(target_map: dict):
    """Yield (subdomain, section, key, entry) for every targets[sd][section][key]
    entry in the registry. section is 'families' or 'platforms'."""
    for subdomain, sd_data in target_map.get("targets", {}).items():
        for section in ("families", "platforms"):
            for key, entry in sd_data.get(section, {}).items():
                yield subdomain, section, key, entry


def check_for_regressions(
    target_map: dict,
    session: "requests.Session",
    *,
    verify_fn: "Callable[..., tuple] | None" = None,
) -> RegressionCheckResult:
    """Re-verify every currently-200 entry in target_map live. Returns a
    RegressionCheckResult: confirmed-regression records (both independent
    checks agreed on non-200), plus coverage accounting. Never mutates
    target_map; never writes to disk -- pure detection, matching
    package_publish_watch.py's own discipline.

    Enforces _TIME_BUDGET_SECONDS (TC-09): checked once per entry, BEFORE
    starting that entry's live check(s) -- an entry already in flight is
    always allowed to finish (never aborted mid-check), only the decision to
    *start* a new one is gated. Once the budget is exceeded, remaining
    entries are counted as skipped rather than silently dropped, and
    budget_exceeded is set so the caller can degrade gracefully (report a
    partial result) instead of relying on an external job timeout to cancel
    the whole run with zero output.
    """
    verify_fn = verify_fn if verify_fn is not None else verify_url
    all_entries = list(_iter_entries(target_map))
    regressions: list[dict[str, Any]] = []
    entries_checked = 0
    budget_exceeded = False
    start = _now_fn()

    for subdomain, section, key, entry in all_entries:
        if entry.get("http_status") != 200:
            continue  # only watching for 200 -> not-200 drift, matching the registry's own gate semantics

        url = entry.get("url")
        if not url:
            continue

        if _now_fn() - start >= _TIME_BUDGET_SECONDS:
            budget_exceeded = True
            break

        entries_checked += 1

        first_status, _chain, _resolved, _via, _retries = verify_fn(url, session)
        if first_status == 200:
            continue  # still healthy

        # First check disagreed with the registry -- confirm independently
        # before reporting, rather than trusting a single observation (this
        # is the same-run analog of package_publish_watch.py's cross-run
        # debounce, sized for one scheduled invocation instead of two).
        _sleep_fn(_RECHECK_DELAY_SECONDS)
        second_status, _chain2, _resolved2, _via2, _retries2 = verify_fn(url, session)

        if second_status == 200:
            continue  # transient blip the first check's own retry loop didn't fully absorb -- not a regression

        regressions.append({
            "subdomain": subdomain,
            "section": section,
            "key": key,
            "url": url,
            "previous_status": 200,
            "first_recheck_status": first_status,
            "confirmed_status": second_status,
        })

    checkable_total = sum(1 for _, _, _, e in all_entries if e.get("http_status") == 200 and e.get("url"))
    entries_skipped = checkable_total - entries_checked

    return RegressionCheckResult(
        regressions=regressions,
        entries_checked=entries_checked,
        entries_skipped=entries_skipped,
        total_entries=checkable_total,
        budget_exceeded=budget_exceeded,
    )


def format_issue_body(result: RegressionCheckResult) -> str:
    lines = [
        "## aspose.com Backlink Target Registry — Confirmed Status Regressions",
        "",
        "The scheduled aspose-com-targets-watch found one or more entries in "
        "`data/aspose_com_targets.json` that were `http_status: 200` but now "
        "confirmed non-200 across two independent live checks (not a single "
        "transient observation).",
        "",
        "### Action Required",
        "1. Verify each finding below independently before applying it (this "
        "issue is a report, not an auto-applied change -- this watcher never "
        "writes to data/aspose_com_targets.json itself).",
        "2. Determine whether each is a genuine page removal (site "
        "restructure, product retirement) or a longer-lived outage -- check "
        "for a redirect target or bundled sibling-platform page the way "
        "`cells/go` -> `cells/go-cpp` was resolved during the redirect-bug "
        "fix (commit e40ed6b509/94e2f01a02).",
        "3. Run `fetch_aspose_com_targets.py --families <affected families>` "
        "to persist the correction, through the normal ST-021-aware commit "
        "path (CLAUDE.md isolated-temp-index git-plumbing).",
        "4. File/update a backlog row citing this issue.",
        "",
    ]
    if result.budget_exceeded:
        lines += [
            "### ⚠ Partial run — time budget exceeded",
            "",
            f"This run checked {result.entries_checked}/{result.total_entries} "
            f"live entries before hitting its internal time budget "
            f"({_TIME_BUDGET_SECONDS}s) and stopped early rather than risk "
            f"the workflow's own job timeout cancelling it outright (see "
            f"MT022 pilot-rerun Finding C, run 31120889071, cancelled with "
            f"zero output after 15m03s). **{result.entries_skipped} entries "
            f"were not checked this run** and may hide an undetected "
            f"regression. Re-run `workflow_dispatch` manually, or wait for "
            f"tomorrow's scheduled run, to get full coverage.",
            "",
        ]
    lines += ["### Findings", ""]
    if not result.regressions:
        lines.append("_No confirmed regressions among the entries checked this run._")
    for r in result.regressions:
        lines.append(
            f"- **{r['subdomain']} / {r['key']}** ({r['section']}): {r['url']} "
            f"— was 200, now confirmed {r['confirmed_status']} "
            f"(first recheck: {r['first_recheck_status']})"
        )
    return "\n".join(lines)


def main(
    argv: "list[str] | None" = None, *,
    target_map: "dict | None" = None,
    verify_fn: "Callable[..., tuple] | None" = None,
) -> int:
    """`target_map`/`verify_fn` are test-only dependency injection (default to
    loading the real registry / the real verify_url) -- mirrors
    fetch_aspose_com_targets.py's build_fn= and package_publish_watch.py's
    adapters= injection points (AGENTS.md 16 DI-over-monkeypatch convention)."""
    parser = argparse.ArgumentParser(prog="aspose_com_targets_watch")
    parser.add_argument("--issue-body-out", metavar="PATH", help="Write the GitHub issue body to this path if any regressions are confirmed")
    parser.add_argument("--repo-root", type=Path, default=_DEFAULT_REPO_ROOT)
    args = parser.parse_args(argv)

    if target_map is None:
        try:
            target_map = load_target_map(args.repo_root)
        except FileNotFoundError as exc:
            print(f"aspose_com_targets_watch: {exc}", file=sys.stderr)
            return 0  # nothing to watch yet -- not this script's failure mode

    session = requests.Session()  # metrics-scan-exempt: web-scraping transport, not professionalize LLM
    session.headers.update({"User-Agent": USER_AGENT})

    result = check_for_regressions(target_map, session, verify_fn=verify_fn)

    if not result.regressions and not result.budget_exceeded:
        print("aspose_com_targets_watch: no confirmed regressions (all previously-200 entries still resolve, "
              "or single-observation dips didn't reconfirm on independent recheck). Nothing to report.")
        return 0

    if result.budget_exceeded:
        # Report-worthy even with zero confirmed regressions (TC-09): a silent
        # partial run is exactly the failure mode this exists to prevent --
        # see RegressionCheckResult's own docstring and MT022 pilot-rerun
        # Finding C.
        print(
            f"aspose_com_targets_watch: TIME BUDGET EXCEEDED -- checked "
            f"{result.entries_checked}/{result.total_entries} entries, "
            f"{result.entries_skipped} skipped. {len(result.regressions)} "
            f"confirmed regression(s) among those checked.",
            file=sys.stderr,
        )

    body = format_issue_body(result)
    print(body)
    if args.issue_body_out:
        Path(args.issue_body_out).write_text(body, encoding="utf-8")

    return 1


if __name__ == "__main__":
    sys.exit(main())
