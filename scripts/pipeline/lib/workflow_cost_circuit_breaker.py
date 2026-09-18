"""workflow_cost_circuit_breaker.py -- GHA cost + CI-health circuit breaker.

Modeled directly on the real, already-working install_change_budget.py
pattern (static caps, always active + a rolling-baseline anomaly check with
an explicit, always-logged warm-up period, fail-closed, never
truncate-and-continue) -- itself modeled on scripts/seo/pipeline/
change_budget.py. Deliberately NOT modeled on
scripts/translator/backends/circuit_state.py, this repo's one prior
circuit-breaker precedent: that one used a failure-COUNT trigger and was
deleted along with the whole in-house translator package; it is also the
wrong trigger type for a cost problem (design doc's own reasoning,
reports/plan_state/MT069-2026-09-16-GHA-MINUTES-REARCHITECTURE/design/
cost_telemetry_proposal.md).

This module has no knowledge of gh api, JSONL ledgers, or GitHub Issues --
workflow_usage_collect_and_check.py (the CLI entry point) builds a
ProposedWorkflowUsageVolume from the ledger's aggregated totals and calls
check_cost_budget(); it separately builds recent run conclusions and calls
check_ci_health(). Two independent checks, sharing one philosophy: **alert,
never auto-disable** -- auto-disabling was the blunt instrument that caused
MT069 to exist in the first place.

MT069-2026-09-16-GHA-MINUTES-REARCHITECTURE, PHB-03.
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_CONFIG_PATH = _DEFAULT_REPO_ROOT / "scripts" / "pipeline" / "config" / "workflow_cost_budgets.yaml"
_REPO_ROOT = _DEFAULT_REPO_ROOT
CONFIG_PATH = _DEFAULT_CONFIG_PATH
HISTORY_PATH = _REPO_ROOT / "reports" / "gha-cost-telemetry" / "cost_budget_history.json"


def configure(
    *, repo_root: "Path | str | None" = None, config_path: "Path | str | None" = None,
    history_path: "Path | str | None" = None,
) -> None:
    """Override HISTORY_PATH for testing (via repo_root) and, separately,
    CONFIG_PATH (via config_path) -- an explicit DI seam, not monkeypatching
    (AGENTS.md 16). Omitting config_path resets it to the real checked-in
    repo-wide resource; CONFIG_PATH is never derived from repo_root (mirrors
    install_change_budget.py's own comment exactly).

    `history_path` (MT069 HC-05) points the rolling-baseline history at an
    explicit file -- needed because the default lives under gitignored
    `reports/`, which a stateless CI runner loses between runs (so the
    anomaly baseline could never warm up there); the scheduled workflow
    restores and re-uploads this one file between runs."""
    global _REPO_ROOT, HISTORY_PATH, CONFIG_PATH
    _REPO_ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT
    HISTORY_PATH = (Path(history_path) if history_path is not None
                    else _REPO_ROOT / "reports" / "gha-cost-telemetry" / "cost_budget_history.json")
    CONFIG_PATH = Path(config_path) if config_path is not None else _DEFAULT_CONFIG_PATH


# ---------------------------------------------------------------------------
# Cost circuit breaker (magnitude-cap, not failure-count)
# ---------------------------------------------------------------------------


@dataclass
class ProposedWorkflowUsageVolume:
    """One collection period's reconstructed usage, ready to check against budget."""
    total_minutes: float
    minutes_by_workflow: dict = field(default_factory=dict)


@dataclass
class BudgetVerdict:
    allowed: bool
    reason: str
    static_cap_violations: list = field(default_factory=list)
    anomaly_status: str = "INACTIVE"


def load_budgets(path: "Path | None" = None) -> dict:
    path = path or CONFIG_PATH
    if yaml is None:
        raise RuntimeError("workflow_cost_circuit_breaker.py requires PyYAML: pip install pyyaml")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _atomic_write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-workflow-cost-budget-", suffix=".json")
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


def load_history() -> dict:
    return _load_json(HISTORY_PATH, {})


def period_scale(budgets: dict, period_days: "int | None") -> float:
    """Factor that converts the caps (defined for `cap_period_days`, default 7)
    to a run whose collection window is `period_days` long. Without this a
    30-day run compared against weekly caps -- unlike quantities -- and
    "tripped" on perfectly normal usage (found live 2026-09-18: 2,950 minutes
    over 30 days 'exceeded' a 1,500-minute WEEKLY cap)."""
    if not period_days:
        return 1.0
    return period_days / budgets.get("cap_period_days", 7)


def check_static_caps(volume: ProposedWorkflowUsageVolume, budgets: dict, *, period_days: "int | None" = None) -> list:
    violations = []
    scale = period_scale(budgets, period_days)
    max_total = budgets["max_total_minutes_per_period"] * scale
    max_per_workflow = budgets["max_minutes_per_workflow_per_period"] * scale

    if volume.total_minutes > max_total:
        violations.append(f"total_minutes {volume.total_minutes:.1f} > max_total_minutes_per_period {max_total:g}"
                          + (f" (scaled x{scale:g} for a {period_days}-day window)" if scale != 1 else ""))
    for name, minutes in sorted(volume.minutes_by_workflow.items()):
        if minutes > max_per_workflow:
            violations.append(f"workflow {name!r}: {minutes:.1f} > max_minutes_per_workflow_per_period {max_per_workflow:g}"
                              + (f" (scaled x{scale:g})" if scale != 1 else ""))
    return violations


def check_anomaly(
    volume: ProposedWorkflowUsageVolume, budgets: dict,
    *, history: "dict | None" = None, warmup_runs: "int | None" = None,
    period_days: "int | None" = None,
) -> "tuple[str, bool]":
    """Returns (anomaly_status_string, blocked). Never raises on missing/empty
    history -- an unseen repo is simply warm-up period 1. INACTIVE is always
    returned explicitly during warm-up, never silently skipped."""
    history = history if history is not None else load_history()
    warmup_runs = warmup_runs if warmup_runs is not None else budgets.get("warmup_periods", 3)
    periods = history.get("total_minutes", [])
    n = len(periods)

    recorded = history.get("period_days")
    if period_days and recorded and recorded != period_days:
        # A 30-day total against a baseline of 7-day totals is not a comparison.
        return f"INACTIVE (history holds {recorded}-day periods, this run is {period_days}-day)", False

    if n < warmup_runs:
        return f"INACTIVE (warm-up, N={n}/{warmup_runs})", False

    mean = sum(periods) / n
    multiplier = budgets.get("anomaly_multiplier", 2.0)
    proposed = volume.total_minutes

    if mean == 0:
        if proposed > 0:
            return f"ALERT (baseline=0 over {n} periods, proposed={proposed:.1f})", True
        return f"PASS (baseline=0 over {n} periods, proposed=0)", False

    ceiling = mean * multiplier
    if proposed > ceiling:
        return (
            f"ALERT (proposed={proposed:.1f} > ceiling={ceiling:.1f}, "
            f"baseline_mean={mean:.1f} over {n} periods)"
        ), True
    return (
        f"PASS (proposed={proposed:.1f} <= ceiling={ceiling:.1f}, "
        f"baseline_mean={mean:.1f} over {n} periods)"
    ), False


def record_period(total_minutes: float, *, history: "dict | None" = None, period_days: "int | None" = None) -> dict:
    """Append this period's ACTUAL total_minutes to history. Call only after
    a collection completes -- never with a proposed/estimated figure, and
    never before check_cost_budget() has already evaluated the period, or
    the anomaly check would be trained on its own proposal."""
    history = history if history is not None else load_history()
    updated = dict(history)
    recorded = history.get("period_days")
    if period_days and recorded and recorded != period_days:
        updated["total_minutes"] = []     # never mix period lengths in one series: start over, loudly
        updated["reset_reason"] = f"period length changed {recorded} -> {period_days} days"
    updated["total_minutes"] = list(updated.get("total_minutes", history.get("total_minutes", []))) + [total_minutes]
    if period_days:
        updated["period_days"] = period_days
    _atomic_write_json(HISTORY_PATH, updated)
    return updated


def check_cost_budget(
    volume: ProposedWorkflowUsageVolume, *, budgets: "dict | None" = None, history: "dict | None" = None,
    period_days: "int | None" = None,
) -> BudgetVerdict:
    """The main pre-flight entry point. Static caps are checked (and fully
    reported) regardless of whether the anomaly check also fires, so a
    caller/log always sees the complete picture. Note the semantic
    difference from install_change_budget.py's check_budget(): `allowed`
    here means "no alert needed", never "block the run" -- this system
    alerts, it never blocks or disables anything (design doc's own rule)."""
    budgets = budgets if budgets is not None else load_budgets()
    static_violations = check_static_caps(volume, budgets, period_days=period_days)
    anomaly_status, anomaly_tripped = check_anomaly(volume, budgets, history=history, period_days=period_days)

    if static_violations:
        return BudgetVerdict(
            allowed=False, reason="static cap(s) exceeded",
            static_cap_violations=static_violations, anomaly_status=anomaly_status,
        )
    if anomaly_tripped:
        return BudgetVerdict(allowed=False, reason="anomaly check tripped", anomaly_status=anomaly_status)
    return BudgetVerdict(allowed=True, reason="within budget", anomaly_status=anomaly_status)


# ---------------------------------------------------------------------------
# CI-health extension (a required check failing continuously)
# ---------------------------------------------------------------------------


@dataclass
class CIHealthVerdict:
    tripped: bool
    reason: str
    failure_rate: float
    run_count: int


def check_ci_health(
    workflow_name: str, recent_conclusions: "list[str]", *, budgets: "dict | None" = None,
) -> CIHealthVerdict:
    """recent_conclusions is the most recent N run conclusions for one
    workflow, newest-first-or-any-order (order doesn't matter for a rate),
    each one of "success"/"failure"/"cancelled"/"skipped"/etc. (gh api's own
    conclusion strings). Tripped when at least `ci_health_min_runs` runs are
    present AND the failure rate over them meets or exceeds
    `ci_health_failure_rate_threshold` -- this is exactly the shape that
    would have caught TC-14's platform-capabilities bug (100% failure, 40+
    runs) automatically after `ci_health_min_runs` runs instead of waiting
    12 days for a human to notice (design doc's own motivating example).
    `cancelled`/`skipped` conclusions are excluded from both numerator and
    denominator -- neither a pass nor a fail signal."""
    budgets = budgets if budgets is not None else load_budgets()
    threshold = budgets.get("ci_health_failure_rate_threshold", 0.9)
    min_runs = budgets.get("ci_health_min_runs", 5)

    scored = [c for c in recent_conclusions if c in ("success", "failure")]
    n = len(scored)
    if n < min_runs:
        return CIHealthVerdict(
            tripped=False, reason=f"INACTIVE (insufficient scored runs, N={n}/{min_runs})",
            failure_rate=0.0, run_count=n,
        )

    failures = sum(1 for c in scored if c == "failure")
    rate = failures / n
    if rate >= threshold:
        return CIHealthVerdict(
            tripped=True,
            reason=f"ALERT: {workflow_name} failure rate {rate:.0%} over last {n} runs >= threshold {threshold:.0%}",
            failure_rate=rate, run_count=n,
        )
    return CIHealthVerdict(
        tripped=False, reason=f"PASS: {workflow_name} failure rate {rate:.0%} over last {n} runs",
        failure_rate=rate, run_count=n,
    )
