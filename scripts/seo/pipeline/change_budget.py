"""Contract G -- Change-Budget Guard (Finding #75, hardened per Finding #80).

This mission already had a real, hardened *computational* budget (Gemini
--max-calls, quota-paced rollout, circuit breakers) but never a
*production-content-change* budget -- nothing capped how many real pages a
single run may modify, and nothing compared a run's proposed change volume
against historical baseline to catch a runaway/bugged run before it writes.

Two checks, both fail-closed (refuse to proceed, never silently truncate to
the cap and continue):

  1. Static caps (scripts/seo/config/change_budgets.yaml) -- checked on
     every run, always active.
  2. Rolling-baseline anomaly check, per (family, mechanism): if a run's
     PROPOSED total_metadata_changes exceeds `anomaly_multiplier` times the
     mean of that (family, mechanism)'s last N ACTUAL run totals, refuse.
     The first `warmup_runs` runs for any (family, mechanism) have no real
     history yet -- Finding #80's fix is an explicit warm-up mode: static
     caps only, with the anomaly check's status always visibly logged as
     "INACTIVE (warm-up, N=<k>/<warmup_runs>)", never silently skipped.

History (actual per-run totals, used only to compute the next run's
baseline) and the cross-mechanism weekly counter live under reports/seo/ --
this card's allowed_paths lists no other state file, and reports/** is
always a permitted write surface per the loop protocol's dirty-path gate.

Two real integration points (both v14 Finding #75's own design, not
generalized here further): check_merge_safety.py's new Gate 5 for the
Schema A auto-merge path (mechanism="schema_a_refresh", one family's
keywords/{family}.json file per check), and apply.py's new pre-flight check
before any real write (mechanism="title_description_writes", called once
per batch, not per file). Each integration site builds its own
ProposedChangeVolume from its own data shape and calls check_budget(); this
module has no knowledge of patch dicts or git diffs.
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

try:
    import yaml
except ImportError:
    yaml = None

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[3]
REPO_ROOT = _DEFAULT_REPO_ROOT
# CONFIG_PATH always resolves from the real repo root, never from
# configure()'s repo_root override: change_budgets.yaml is a real,
# checked-in, repo-wide resource -- not per-environment state -- so a
# caller under a different repo_root (an isolated test fixture, an apply.py
# invocation with a monkeypatched _REPO_ROOT) still reads the one real
# config rather than needing its own copy. A test that wants different
# budget values passes `budgets=`/`path=` explicitly instead.
CONFIG_PATH = _DEFAULT_REPO_ROOT / "scripts" / "seo" / "config" / "change_budgets.yaml"
HISTORY_PATH = REPO_ROOT / "reports" / "seo" / "change_budget_history.json"
CROSS_MECHANISM_PATH = REPO_ROOT / "reports" / "seo" / "change_budget_cross_mechanism.json"


def configure(*, repo_root: "Path | str | None" = None) -> None:
    """Override module-level state-path constants for testing (HISTORY_PATH,
    CROSS_MECHANISM_PATH). Does not affect CONFIG_PATH -- see its comment."""
    global REPO_ROOT, HISTORY_PATH, CROSS_MECHANISM_PATH
    REPO_ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT
    HISTORY_PATH = REPO_ROOT / "reports" / "seo" / "change_budget_history.json"
    CROSS_MECHANISM_PATH = REPO_ROOT / "reports" / "seo" / "change_budget_cross_mechanism.json"


@dataclass
class ProposedChangeVolume:
    """What one run/batch proposes to change, in mechanism-neutral units.

    `items_by_scope` keys are site names for title_description_writes,
    family names for schema_a_refresh (see module docstring). Only
    title_changes/description_changes are meaningful for
    title_description_writes; leave them at 0 for schema_a_refresh (its
    "changes" are keyword entries, counted only in total_items).
    """
    total_items: int
    items_by_scope: dict = field(default_factory=dict)
    title_changes: int = 0
    description_changes: int = 0

    @property
    def total_metadata_changes(self) -> int:
        return self.title_changes + self.description_changes


@dataclass
class BudgetVerdict:
    allowed: bool
    reason: str
    static_cap_violations: list = field(default_factory=list)
    anomaly_status: str = "INACTIVE"


def load_budgets(path: "Path | None" = None) -> dict:
    path = path or CONFIG_PATH
    if yaml is None:
        raise RuntimeError("change_budget.py requires PyYAML: pip install pyyaml")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _atomic_write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-change-budget-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)
            f.write("\n")
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _history_key(family: str, mechanism: str) -> str:
    return f"{family}/{mechanism}"


def load_history() -> dict:
    return _load_json(HISTORY_PATH, {})


def week_start_for(dt: "datetime | None" = None) -> str:
    """ISO week (Monday) start date, as YYYY-MM-DD, for `dt` (default: now, UTC)."""
    dt = dt or datetime.now(timezone.utc)
    monday = dt - timedelta(days=dt.weekday())
    return monday.strftime("%Y-%m-%d")


def _mechanism_cap(budgets: dict, mechanism: "str | None", generic_key: str) -> int:
    """A mechanism may override a generic cap with its own
    `<mechanism>_<generic_key>` entry (e.g. schema_a_refresh's real regenerate
    volume operates at a completely different scale than apply.py's real
    content-write pilot cohort -- confirmed live against the actual
    2026-08-30 PR #69 commit, which regenerated 105 entries in
    keywords/3d.json in one legitimate run during that family's
    platform-label migration completion; a shared, pilot-scale cap would
    have wrongly blocked that already-successful production run)."""
    if mechanism:
        specific_key = f"{mechanism}_{generic_key}"
        if specific_key in budgets:
            return budgets[specific_key]
    return budgets[generic_key]


def check_static_caps(volume: ProposedChangeVolume, budgets: dict, mechanism: "str | None" = None) -> list:
    violations = []
    max_pages_per_run = _mechanism_cap(budgets, mechanism, "max_pages_per_run")
    max_pages_per_site_per_run = _mechanism_cap(budgets, mechanism, "max_pages_per_site_per_run")

    if volume.total_items > max_pages_per_run:
        violations.append(
            f"total_items {volume.total_items} > max_pages_per_run {max_pages_per_run}"
        )
    for scope, count in sorted(volume.items_by_scope.items()):
        if count > max_pages_per_site_per_run:
            violations.append(
                f"scope {scope!r}: {count} > max_pages_per_site_per_run {max_pages_per_site_per_run}"
            )
    if volume.title_changes > budgets["max_title_changes_per_run"]:
        violations.append(
            f"title_changes {volume.title_changes} > max_title_changes_per_run {budgets['max_title_changes_per_run']}"
        )
    if volume.description_changes > budgets["max_description_changes_per_run"]:
        violations.append(
            f"description_changes {volume.description_changes} > "
            f"max_description_changes_per_run {budgets['max_description_changes_per_run']}"
        )
    total_metadata = volume.total_metadata_changes
    if total_metadata > budgets["max_total_metadata_changes_per_run"]:
        violations.append(
            f"total_metadata_changes {total_metadata} > "
            f"max_total_metadata_changes_per_run {budgets['max_total_metadata_changes_per_run']}"
        )
    return violations


def _anomaly_measure(volume: ProposedChangeVolume) -> int:
    """The single number the anomaly check tracks: total_metadata_changes for
    title_description_writes, total_items for schema_a_refresh (a Schema A
    run has no title/description split -- see module docstring)."""
    return volume.total_metadata_changes or volume.total_items


def check_anomaly(
    family: str, mechanism: str, volume: ProposedChangeVolume, budgets: dict,
    *, history: "dict | None" = None, warmup_runs: "int | None" = None,
) -> "tuple[str, bool]":
    """Returns (anomaly_status_string, blocked). Never raises on a missing
    or empty history -- an unseen (family, mechanism) pair is simply warm-up
    run 1."""
    history = history if history is not None else load_history()
    warmup_runs = warmup_runs if warmup_runs is not None else budgets.get("warmup_runs", 3)
    runs = history.get(_history_key(family, mechanism), [])
    n = len(runs)

    if n < warmup_runs:
        return f"INACTIVE (warm-up, N={n}/{warmup_runs})", False

    mean = sum(runs) / n
    multiplier = budgets.get("anomaly_multiplier", 3.0)
    proposed = _anomaly_measure(volume)

    if mean == 0:
        if proposed > 0:
            return f"BLOCKED (baseline=0 over {n} runs, proposed={proposed})", True
        return f"PASS (baseline=0 over {n} runs, proposed=0)", False

    ceiling = mean * multiplier
    if proposed > ceiling:
        return (
            f"BLOCKED (proposed={proposed} > ceiling={ceiling:.1f}, "
            f"baseline_mean={mean:.1f} over {n} runs)"
        ), True
    return (
        f"PASS (proposed={proposed} <= ceiling={ceiling:.1f}, "
        f"baseline_mean={mean:.1f} over {n} runs)"
    ), False


def record_run(family: str, mechanism: str, actual_measure: int, *, history: "dict | None" = None) -> dict:
    """Append this run's ACTUAL change count to history. Must be called only
    after a run completes with its real applied count -- never with the
    proposed count, and never before check_budget() has already gated the
    run, or the anomaly check would be trained on its own proposal."""
    history = history if history is not None else load_history()
    key = _history_key(family, mechanism)
    updated = dict(history)
    updated[key] = list(history.get(key, [])) + [actual_measure]
    _atomic_write_json(HISTORY_PATH, updated)
    return updated


def check_cross_mechanism_budget(
    family: str, proposed_additional: int, budgets: dict,
    *, week_start: "str | None" = None, cross_state: "dict | None" = None,
) -> "tuple[bool, str]":
    """Weekly, cross-mechanism (schema_a_refresh + title_description_writes
    combined) counter for one family. Returns (allowed, reason). This is the
    counter SEO-EXECUTION-INVARIANTS (Contract J) will call as its
    `cross_mechanism_change_budget_not_exceeded` invariant; recording a
    change into the counter is a separate, explicit step
    (record_cross_mechanism_change), never implied by a passing check."""
    week_start = week_start or week_start_for()
    cross_state = cross_state if cross_state is not None else _load_json(CROSS_MECHANISM_PATH, {})
    key = f"{family}/{week_start}"
    current = cross_state.get(key, 0)
    cap = budgets.get("max_cross_mechanism_changes_per_family_per_week", budgets["max_total_metadata_changes_per_run"])
    projected = current + proposed_additional
    if projected > cap:
        return False, f"{family} week {week_start}: {current} already + {proposed_additional} proposed = {projected} > cap {cap}"
    return True, f"{family} week {week_start}: {current} + {proposed_additional} = {projected} <= cap {cap}"


def record_cross_mechanism_change(
    family: str, count: int, *, week_start: "str | None" = None, cross_state: "dict | None" = None,
) -> dict:
    week_start = week_start or week_start_for()
    cross_state = cross_state if cross_state is not None else _load_json(CROSS_MECHANISM_PATH, {})
    key = f"{family}/{week_start}"
    updated = dict(cross_state)
    updated[key] = updated.get(key, 0) + count
    _atomic_write_json(CROSS_MECHANISM_PATH, updated)
    return updated


def check_budget(
    family: str, mechanism: str, volume: ProposedChangeVolume,
    *, budgets: "dict | None" = None, history: "dict | None" = None,
) -> BudgetVerdict:
    """The main pre-flight entry point. Static caps are checked (and fully
    reported) regardless of whether the anomaly check also fails, so a
    caller/log always sees the complete picture, not just the first failure."""
    budgets = budgets if budgets is not None else load_budgets()
    static_violations = check_static_caps(volume, budgets, mechanism=mechanism)
    anomaly_status, anomaly_blocked = check_anomaly(family, mechanism, volume, budgets, history=history)

    if static_violations:
        return BudgetVerdict(
            allowed=False, reason="static cap(s) exceeded",
            static_cap_violations=static_violations, anomaly_status=anomaly_status,
        )
    if anomaly_blocked:
        return BudgetVerdict(allowed=False, reason="anomaly check blocked run", anomaly_status=anomaly_status)
    return BudgetVerdict(allowed=True, reason="within budget", anomaly_status=anomaly_status)
