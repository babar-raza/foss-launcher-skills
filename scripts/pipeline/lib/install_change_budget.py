"""install_change_budget.py -- PKGINSTALL-CHANGE-BUDGET.

Content-level blast-radius circuit breaker for install-instruction content
changes, modeled directly on the real, already-working
scripts/seo/pipeline/change_budget.py pattern (static caps, always active +
a rolling-baseline anomaly check per mechanism with an explicit,
always-logged warm-up period, fail-closed, never truncate-and-continue).

Nothing today caps or validates the blast radius of a proposed
install-instruction content change before it's applied. git_plumb_commit.py
has extensive correctness/provenance safety machinery (stale-file
regression, session-ledger cross-check, atomic writes) but nothing checks
the SIZE of a proposed commit, and ST-054's own "one product per commit,
never one all-products commit" rule is prose-only guidance to the human/
agent operator, not machine-enforced anywhere. This module closes that gap
for the two mechanisms that can propose a multi-file install-content change:
package_install_migrator.py / package_install_inline_migrator.py
(mechanism="mechanical_migration") and locale_patch.py
(mechanism="locale_propagation").

Each integration site builds its own ProposedInstallChangeVolume from its
own data shape and calls check_budget() before writing -- this module has
no knowledge of patch dicts, migration results, or git diffs, exactly
mirroring change_budget.py's own division of responsibility.

History (actual per-run totals, used only to compute the next run's
baseline) lives under reports/package-reconciliation/change_budget_history.json
-- co-located with reconciliation_store.py's own artifacts, never
data/package_registry.json, for the same deploy-trigger-avoidance reasoning
governing plan section R.3.1 already established.
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
_DEFAULT_CONFIG_PATH = _DEFAULT_REPO_ROOT / "scripts" / "pipeline" / "config" / "install_change_budgets.yaml"
_REPO_ROOT = _DEFAULT_REPO_ROOT
CONFIG_PATH = _DEFAULT_CONFIG_PATH
HISTORY_PATH = _REPO_ROOT / "reports" / "package-reconciliation" / "change_budget_history.json"


def configure(*, repo_root: "Path | str | None" = None, config_path: "Path | str | None" = None) -> None:
    """Override HISTORY_PATH for testing (via repo_root) and, separately,
    CONFIG_PATH (via config_path -- an explicit DI seam so a test can point
    at a fixture budgets file instead of monkeypatching load_budgets(),
    matching this repo's DI-over-monkeypatch testing convention). Omitting
    config_path resets it to the real, checked-in repo-wide resource --
    CONFIG_PATH is never derived from repo_root (mirrors change_budget.py's
    own CONFIG_PATH comment exactly: it's a checked-in resource, not
    per-environment state)."""
    global _REPO_ROOT, HISTORY_PATH, CONFIG_PATH
    _REPO_ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT
    HISTORY_PATH = _REPO_ROOT / "reports" / "package-reconciliation" / "change_budget_history.json"
    CONFIG_PATH = Path(config_path) if config_path is not None else _DEFAULT_CONFIG_PATH


@dataclass
class ProposedInstallChangeVolume:
    """What one migration/locale-propagation run proposes to change.

    `files_by_locale` keys are locale codes ("en" for the English source,
    "fr"/"de"/etc. for locale copies) -- lets the per-locale cap catch a
    single-locale runaway independent of the overall total.
    """
    total_files: int
    files_by_locale: dict = field(default_factory=dict)

    @property
    def locale_count(self) -> int:
        return len([loc for loc in self.files_by_locale if loc != "en"])


@dataclass
class BudgetVerdict:
    allowed: bool
    reason: str
    static_cap_violations: list = field(default_factory=list)
    anomaly_status: str = "INACTIVE"


def load_budgets(path: "Path | None" = None) -> dict:
    path = path or CONFIG_PATH
    if yaml is None:
        raise RuntimeError("install_change_budget.py requires PyYAML: pip install pyyaml")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _atomic_write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-install-change-budget-", suffix=".json")
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


def _mechanism_cap(budgets: dict, mechanism: "str | None", generic_key: str) -> int:
    """A mechanism may override a generic cap with its own
    `<mechanism>_<generic_key>` entry -- see install_change_budgets.yaml's
    own comments for why mechanical_migration and locale_propagation
    legitimately operate at different real scales."""
    if mechanism:
        specific_key = f"{mechanism}_{generic_key}"
        if specific_key in budgets:
            return budgets[specific_key]
    return budgets[generic_key]


def check_static_caps(
    volume: ProposedInstallChangeVolume, budgets: dict, mechanism: "str | None" = None,
) -> list:
    violations = []
    max_files_per_run = _mechanism_cap(budgets, mechanism, "max_files_per_run")
    max_files_per_locale_per_run = _mechanism_cap(budgets, mechanism, "max_files_per_locale_per_run")

    if volume.total_files > max_files_per_run:
        violations.append(f"total_files {volume.total_files} > max_files_per_run {max_files_per_run}")
    for locale, count in sorted(volume.files_by_locale.items()):
        if count > max_files_per_locale_per_run:
            violations.append(
                f"locale {locale!r}: {count} > max_files_per_locale_per_run {max_files_per_locale_per_run}"
            )
    return violations


def check_anomaly(
    family: str, mechanism: str, volume: ProposedInstallChangeVolume, budgets: dict,
    *, history: "dict | None" = None, warmup_runs: "int | None" = None,
) -> "tuple[str, bool]":
    """Returns (anomaly_status_string, blocked). Never raises on a missing
    or empty history -- an unseen (family, mechanism) pair is simply warm-up
    run 1. The INACTIVE status during warm-up is always returned explicitly
    (never silently skipped without a visible marker), matching
    change_budget.py's own Finding #80 fix."""
    history = history if history is not None else load_history()
    warmup_runs = warmup_runs if warmup_runs is not None else budgets.get("warmup_runs", 3)
    runs = history.get(_history_key(family, mechanism), [])
    n = len(runs)

    if n < warmup_runs:
        return f"INACTIVE (warm-up, N={n}/{warmup_runs})", False

    mean = sum(runs) / n
    multiplier = budgets.get("anomaly_multiplier", 3.0)
    proposed = volume.total_files

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


def record_run(family: str, mechanism: str, actual_files: int, *, history: "dict | None" = None) -> dict:
    """Append this run's ACTUAL applied file count to history. Must be
    called only after a run completes with its real applied count -- never
    with the proposed count, and never before check_budget() has already
    gated the run, or the anomaly check would be trained on its own
    proposal."""
    history = history if history is not None else load_history()
    key = _history_key(family, mechanism)
    updated = dict(history)
    updated[key] = list(history.get(key, [])) + [actual_files]
    _atomic_write_json(HISTORY_PATH, updated)
    return updated


def check_budget(
    family: str, mechanism: str, volume: ProposedInstallChangeVolume,
    *, budgets: "dict | None" = None, history: "dict | None" = None,
) -> BudgetVerdict:
    """The main pre-flight entry point. Static caps are checked (and fully
    reported) regardless of whether the anomaly check also fails, so a
    caller/log always sees the complete picture, not just the first
    failure. Fail-closed: any violation refuses the whole run, never a
    partial/truncated apply."""
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
