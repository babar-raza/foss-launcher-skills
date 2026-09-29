"""registry_watch.py — MT075-T6 (plan Revision 2 SR2.5).

The unified watcher: ONE script, ONE iteration loop, covering all 6 registry
types (pypi, nuget, npm, go_modules, cargo, maven) through the shared
CheckResult adapter contract (package_registries/{pypi,nuget,npm,go,cargo,
maven}.py) -- replacing the previous split between package_publish_watch.py
(5 non-Maven registries) and publish_watcher.py (Maven only, a structurally
incompatible bespoke return shape). Both prior scripts are left in place
(retiring them is the cross-repo cutover step, T7, deliberately held for an
explicit go-ahead); this module is the new, additive consolidation.

Every observed change is routed through check_registry_merge_safety's
two-tier gate (MT075-T5) -- this is what makes "no human required" safe: a
version bump of an already-published entry auto-applies immediately; a first
publish or identity change needs out-of-band repo-release corroboration or
is HELD (never touching the live registry) for re-evaluation on a later run,
never blocked on a person.

This module only WRITES the registry file atomically (same validate-then-
write-then-reparse-validate discipline package_publish_watch.py's own
run_auto_apply() already established) -- committing that write is a
separate step the calling workflow performs via git_plumb_commit.py, exactly
like the two scripts this one consolidates. No git operations happen here.

CLI:
    PYTHONPATH=scripts/pipeline .venv/Scripts/python -m commands.ops.registry_watch
    PYTHONPATH=scripts/pipeline .venv/Scripts/python -m commands.ops.registry_watch --auto-apply
"""
from __future__ import annotations

import copy
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))
_LIB_DIR = str(_PIPELINE_ROOT / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from package_registries import CheckResult, pypi, nuget, npm, go, cargo, maven  # noqa: E402
from package_registry_data import load_registry, validate_package_registry  # noqa: E402
from commands.ops import check_registry_merge_safety as gate  # noqa: E402

_DEFAULT_DATA_PATH = _PIPELINE_ROOT.parent.parent / "data" / "package_registry.json"
DATA_PATH = _DEFAULT_DATA_PATH

_ADAPTERS: "dict[str, Any]" = {
    "pypi": pypi, "nuget": nuget, "npm": npm, "go_modules": go, "cargo": cargo, "maven": maven,
}


def configure(*, data_path: "Path | str | None" = None) -> None:
    global DATA_PATH
    DATA_PATH = Path(data_path) if data_path is not None else _DEFAULT_DATA_PATH


def observe_entry(
    registry_type: str, candidate: dict, *, adapters: "dict[str, Any] | None" = None, fetch=None,
) -> "CheckResult | None":
    """Dispatch one candidate to its adapter -- None for an unrecognized
    registry_type (defensive; the schema enum should already prevent this)."""
    adapters = adapters if adapters is not None else _ADAPTERS
    adapter = adapters.get(registry_type)
    if adapter is None:
        return None
    return adapter.check_published(candidate, fetch=fetch)


def build_candidate_entry(base_entry: dict, result: CheckResult, *, recorded_at: str) -> dict:
    """A new entry dict reflecting one live CheckResult, preserving every
    other field from base_entry (identity_basis, candidate_owner,
    content_healing_status, ...) -- only the fields a live observation can
    actually speak to are updated."""
    candidate_out = copy.deepcopy(base_entry)
    cand_block = candidate_out.setdefault("candidate", {})
    registry_type = candidate_out.get("registry_type")
    # Only flat-name registries have a `candidate.name` identity field at
    # all -- injecting one for maven (group_id/artifact_id) or go_modules
    # (module_path) corrupts _candidate_identity_key's classification.
    # Independent review (2026-09-28) reproduced this live: both real
    # go_modules entries have no `name` key at all, so writing one here
    # turned an unchanged version-bump observation into a spurious
    # TIER_2_IDENTITY_CHANGE on every single run.
    if result.candidate_name and registry_type in ("pypi", "nuget", "npm", "cargo"):
        cand_block["name"] = result.candidate_name
    if result.version:
        cand_block["version"] = result.version
    else:
        # A live check that reported no version has no version claim to
        # make, regardless of what `published` says -- never let a stale,
        # previously-recorded version leak through as if it were freshly
        # observed. Live-data proof run (2026-09-28) caught this for the
        # not-published case (cells/rust's base entry carried an old
        # placeholder version; crates.io returned a definitive 404, but the
        # stale version passed straight through and got corroborated as a
        # false first-publish). Independent review then found the same hole
        # on the PUBLISHED side too: an adapter can return published=True
        # with version=None (NuGet's versions list empty/unparseable, Go's
        # @latest failing after @v/list succeeds, PyPI missing info.version)
        # and the original fix (elif not result.published) left the stale
        # version untouched in exactly that case. Nulling unconditionally
        # whenever result.version is falsy closes both.
        cand_block["version"] = None

    # Only continuity of an ALREADY-established, already-published identity
    # may fall back to a stale verified_owner/project_url when this run's
    # observation didn't re-derive one (some adapters don't always fetch
    # owner metadata on a plain version check). A first publish or any
    # previously-unpublished entry must reflect exactly what THIS run
    # observed -- never carry forward a claim nobody just verified.
    base_was_published = bool((base_entry.get("verification") or {}).get("published"))

    verification = candidate_out.setdefault("verification", {})
    verification["published"] = result.published
    verification["verified_at"] = recorded_at
    verification["verified_owner"] = result.verified_owner or (
        verification.get("verified_owner") if base_was_published else None
    )
    verification["evidence_url"] = result.evidence_url
    verification["method"] = result.method
    verification["evidence_note"] = (
        f"registry_watch observation {recorded_at}: published={result.published} "
        f"version={result.version!r} method={result.method}"
    )
    verification["project_url"] = result.project_url or (
        verification.get("project_url") if base_was_published else None
    )
    return candidate_out


def _iter_entries(data: dict):
    for family, platforms in sorted(data.items()):
        if not isinstance(platforms, dict):
            continue
        for platform, entry in sorted(platforms.items()):
            if isinstance(entry, dict):
                yield family, platform, entry


def run_watch(
    data: dict, *, adapters: "dict[str, Any] | None" = None, fetch=None,
    corroboration_check: "Callable[[str, str, str], bool] | None" = None,
    velocity_check: "Callable[[str], tuple[bool, str]] | None" = None,
    recorded_at: "str | None" = None,
) -> dict[str, Any]:
    """Observe every entry once, classify+gate each observed change, and
    return a full report: an updated_registry (base data with every
    AUTO_APPLY candidate merged in, capped at gate.MAX_ENTRIES_PER_BATCH --
    extras are demoted to held, never silently dropped) plus applied/held/
    rejected/no_change/ambiguous breakdowns for reporting."""
    recorded_at = recorded_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    updated_registry = copy.deepcopy(data)

    applied: list[dict[str, Any]] = []
    held: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    no_change: list[dict[str, Any]] = []
    ambiguous: list[dict[str, Any]] = []

    for family, platform, entry in _iter_entries(data):
        registry_type = entry.get("registry_type")
        result = observe_entry(registry_type, entry.get("candidate") or {}, adapters=adapters, fetch=fetch)
        if result is None or result.ambiguous:
            ambiguous.append({"family": family, "platform": platform, "reason": "no adapter or ambiguous fetch"})
            continue

        candidate_entry = build_candidate_entry(entry, result, recorded_at=recorded_at)
        verdict = gate.evaluate_entry_change(
            family, platform, entry, candidate_entry,
            corroboration_check=corroboration_check, velocity_check=velocity_check,
        )
        row = {
            "family": family, "platform": platform, "tier": verdict.tier,
            "decision": verdict.decision, "reason": verdict.reason,
        }
        if verdict.decision == gate.DECISION_AUTO_APPLY:
            if len(applied) >= gate.MAX_ENTRIES_PER_BATCH:
                row["reason"] = f"clear to apply but batch cap ({gate.MAX_ENTRIES_PER_BATCH}) reached this run"
                held.append(row)
                continue
            applied.append(row)
            updated_registry.setdefault(family, {})[platform] = candidate_entry
        elif verdict.decision == gate.DECISION_HOLD:
            held.append(row)
        elif verdict.decision == gate.DECISION_NO_CHANGE:
            no_change.append(row)
        else:
            rejected.append(row)

    return {
        "recorded_at": recorded_at,
        "updated_registry": updated_registry,
        "applied": applied,
        "held": held,
        "rejected": rejected,
        "no_change": no_change,
        "ambiguous": ambiguous,
    }


def run_auto_apply(
    *, adapters: "dict[str, Any] | None" = None, fetch=None,
    corroboration_check: "Callable[[str, str, str], bool] | None" = None,
    velocity_check: "Callable[[str], tuple[bool, str]] | None" = None,
    record_apply: "Callable[[str, int], None] | None" = None,
) -> dict[str, Any]:
    """Observe, gate, and atomically write data/package_registry.json --
    mirrors package_publish_watch.run_auto_apply()'s validate-then-write-
    then-reparse-validate discipline exactly, applied here to a candidate
    built through the unified 6-registry gate instead of the old bespoke
    proposal-application functions.

    MT075-T9: after a successful write, records each family's REAL applied
    count into change_budget's rolling history (gate.record_registry_watch_apply,
    injectable as `record_apply` for tests) -- never the proposed count, and
    never before the write has actually landed, matching change_budget's own
    documented contract."""
    original_bytes = DATA_PATH.read_text(encoding="utf-8")
    data = json.loads(original_bytes)

    result = run_watch(
        data, adapters=adapters, fetch=fetch,
        corroboration_check=corroboration_check, velocity_check=velocity_check,
    )
    result["wrote_changes"] = False
    result["validation_errors"] = []

    if not result["applied"]:
        return result

    updated_registry = result["updated_registry"]
    errors = validate_package_registry(updated_registry)
    if errors:
        result["validation_errors"] = errors
        result["applied"] = []
        return result

    if updated_registry == data:
        return result

    new_bytes = json.dumps(updated_registry, indent=2) + "\n"
    tmp_path = DATA_PATH.with_name(DATA_PATH.name + ".tmp")
    tmp_path.write_text(new_bytes, encoding="utf-8")
    reparsed = json.loads(tmp_path.read_text(encoding="utf-8"))
    reparse_errors = validate_package_registry(reparsed)
    if reparse_errors:
        tmp_path.unlink(missing_ok=True)
        result["validation_errors"] = reparse_errors
        result["applied"] = []
        return result
    os.replace(tmp_path, DATA_PATH)
    result["wrote_changes"] = True

    record = record_apply or gate.record_registry_watch_apply
    by_family: dict[str, int] = {}
    for row in result["applied"]:
        by_family[row["family"]] = by_family.get(row["family"], 0) + 1
    for family, count in by_family.items():
        record(family, count)

    return result


def format_summary(result: dict[str, Any]) -> str:
    def _fmt(rows):
        return ", ".join(f"{r['family']}/{r['platform']}" for r in rows) or "(none)"

    return (
        f"applied={len(result['applied'])} [{_fmt(result['applied'])}] | "
        f"held={len(result['held'])} [{_fmt(result['held'])}] | "
        f"rejected={len(result['rejected'])} [{_fmt(result['rejected'])}] | "
        f"no_change={len(result['no_change'])} | ambiguous={len(result['ambiguous'])}"
    )


def main(argv: "list[str] | None" = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="registry_watch")
    parser.add_argument("--auto-apply", action="store_true", help="Write eligible changes to data/package_registry.json")
    parser.add_argument("--held-report-out", metavar="PATH", help="Write the held/rejected candidates as JSON")
    args = parser.parse_args(argv)

    if args.auto_apply:
        result = run_auto_apply()
    else:
        data = load_registry(DATA_PATH)
        result = run_watch(data)
        result["wrote_changes"] = False

    print(format_summary(result))
    if result.get("validation_errors"):
        print(f"VALIDATION ERRORS (nothing written): {result['validation_errors']}", file=sys.stderr)

    if args.held_report_out and (result["held"] or result["rejected"]):
        Path(args.held_report_out).write_text(
            json.dumps({"held": result["held"], "rejected": result["rejected"]}, indent=2), encoding="utf-8",
        )

    return 1 if result.get("validation_errors") else 0


if __name__ == "__main__":
    raise SystemExit(main())
