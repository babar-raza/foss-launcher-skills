"""registry_observation_ledger.py — per-run observation ledger for the
package-install reconciliation system (Mission
MT066-2026-09-09-PACKAGE-INSTALL-RECONCILIATION, Phase 1).

Named `registry_observation_ledger.py`, not `reconciliation_ledger.py` (the
first, incorrect name this module briefly had, same session): that filename
already belonged to an unrelated, real, in-use module -- TC-PROD-005's
cross-surface reconciliation ledger for the manifest-driven refresh
architecture (scripts/pipeline/commands/ops/refresh_harness.py's actual
dependency) -- which a Write tool call silently overwrote without reading
first. Caught and fixed the same session, before the commit was pushed.

This is deliberately NOT part of data/package_registry.json. That file is
Hugo-consumed (site.Data.package_registry); a field that changes on every watcher
tick -- even a no-op tick -- would cause a spurious commit and a full-portfolio
rebuild every single day once the deploy-scanner blind spot (see the mission's
plan, section K) is fixed. This ledger lives under reports/, which the deploy
scanner never sees, and exists solely so an operator (or /plan-health-watchdog)
can tell whether a given family/platform/registry_type is still being checked at
all -- distinct from data/package_registry.json's `verified_at`, which only
advances when `published` is confirmed true and changes rarely.

Pure/impure split matches this repo's DI-over-monkeypatch testing convention
(AGENTS.md 16 / docs/development/testing-seams.md): record_observation() is a
pure function over a plain dict; load_ledger()/save_ledger() are the only I/O.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from package_registries import CheckResult


def default_ledger_path() -> Path:
    return Path("reports/package-reconciliation/observations.json")


def load_ledger(path: "Path | None" = None) -> dict[str, Any]:
    """Return the ledger dict, or {} if it doesn't exist yet. Tolerates a
    corrupt/torn file (returns {} rather than raising) -- an observability
    ledger must never itself become a reason a scheduled run fails."""
    path = path or default_ledger_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_ledger(ledger: dict[str, Any], path: "Path | None" = None) -> None:
    path = path or default_ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def record_observation(
    ledger: dict[str, Any],
    *,
    family: str,
    platform: str,
    registry_type: str,
    result: CheckResult,
    observed_at: str,
) -> dict[str, Any]:
    """Pure function: return a new ledger dict with this observation recorded,
    keyed `{family}.{platform}`. Records on EVERY check regardless of outcome
    (published, not-published, or ambiguous) -- that's the entire point: a
    silently-stopped adapter is detectable only if "we checked and got
    ambiguous" is itself recorded, not just "we checked and confirmed
    published".
    """
    updated = dict(ledger)
    key = f"{family}.{platform}"
    updated[key] = {
        "family": family,
        "platform": platform,
        "registry_type": registry_type,
        "last_observed_at": observed_at,
        "published": result.published,
        "ambiguous": result.ambiguous,
        "method": result.method,
        "live_version": result.version,
        "yanked": result.yanked,
    }
    return updated
