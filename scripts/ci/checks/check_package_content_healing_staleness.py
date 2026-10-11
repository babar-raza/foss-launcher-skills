"""check_package_content_healing_staleness.py — advisory check: has a
`content_healing_status: pending` registry entry sat unaddressed too long?
(watcher-fleet reliability hardening, 2026-09-07, Phase 3.)

`data/package_registry.json` previously recorded only DETECTION state
(`verification.published`) -- the moment a package-publish-watch proposal
was applied (`package_publish_watch.apply_proposal`), whether the matching
literal-install-text content healing (`package_install_migrator.py`) was
still owed existed only as prose in the triggering, often-since-closed
GitHub issue. Confirmed live: `3d/python`'s registry flip landed
2026-09-02 (commit f3184918fe); its 392-file/509-mention content healing
was still entirely undone five days later with zero durable record of that
fact anywhere in the repo but a closed issue's comment.

`apply_proposal` now sets `content_healing_status` (`pending` | `healed` |
`not_needed`) and `content_healing_status_set_at` atomically alongside the
publish-state flip. This check makes a `pending` entry's AGE visible and
queryable instead of invisible forever: it WARNs (never fails -- matching
this repo's existing advisory-check philosophy, see
check_module_consumption.py) on any entry that has been `pending` longer
than STALE_DAYS.

Deliberately does NOT attempt to auto-heal anything or judge whether
healing is actually complete -- AGENTS.md's S-73 mandate requires per-file
manual/agent review for every content edit regardless of scale; this check
only prevents the "nobody remembered" failure mode, it does not replace
the review itself.

Usage::

    PYTHONPATH=scripts/pipeline python scripts/ci/checks/check_package_content_healing_staleness.py
    PYTHONPATH=scripts/pipeline python scripts/ci/checks/check_package_content_healing_staleness.py --stale-days 7
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_REGISTRY_PATH = _REPO_ROOT / "data" / "package_registry.json"
DEFAULT_STALE_DAYS = 14


def _parse_date(value: str) -> "date | None":
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except (ValueError, TypeError):
        try:
            return date.fromisoformat(value)
        except (ValueError, TypeError):
            return None


def find_stale_entries(
    registry: dict, *, stale_days: int, today: "date | None" = None,
) -> list[dict]:
    """Return one dict per (family, platform) whose
    verification.content_healing_status == "pending" and
    content_healing_status_set_at is more than `stale_days` old (or
    unparseable, which is itself worth flagging). Never raises on malformed
    registry shapes -- an unexpected entry shape is skipped, not fatal,
    matching this repo's existing fail-open policy for advisory checks."""
    today = today or datetime.now(timezone.utc).date()
    stale: list[dict] = []
    for family, platforms in registry.items():
        if family.startswith("_") or not isinstance(platforms, dict):
            continue
        for platform, entry in platforms.items():
            if not isinstance(entry, dict):
                continue
            verification = entry.get("verification", {})
            if not isinstance(verification, dict):
                continue
            status = entry.get("content_healing_status")
            if status != "pending":
                continue
            set_at_raw = entry.get("content_healing_status_set_at")
            set_at = _parse_date(set_at_raw) if set_at_raw else None
            age_days = (today - set_at).days if set_at else None
            if age_days is None or age_days > stale_days:
                stale.append({
                    "family": family,
                    "platform": platform,
                    "content_healing_status_set_at": set_at_raw,
                    "age_days": age_days,
                })
    return stale


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", default=str(_DEFAULT_REGISTRY_PATH))
    parser.add_argument("--stale-days", type=int, default=DEFAULT_STALE_DAYS)
    args = parser.parse_args(argv)

    registry_path = Path(args.registry)
    if not registry_path.exists():
        print(f"WARN: {registry_path} not found -- nothing to check.", file=sys.stderr)
        return 0

    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"WARN: {registry_path} is not valid JSON ({exc}) -- skipping.", file=sys.stderr)
        return 0

    stale = find_stale_entries(registry, stale_days=args.stale_days)
    if not stale:
        print(f"OK: no content_healing_status:pending entry older than {args.stale_days} days.")
        return 0

    print(
        f"WARN: {len(stale)} package registry entr{'y is' if len(stale) == 1 else 'ies are'} "
        f"content_healing_status:pending and older than {args.stale_days} days "
        f"(advisory only -- does not fail the build):",
        file=sys.stderr,
    )
    for s in sorted(stale, key=lambda s: (s["age_days"] is None, -(s["age_days"] or 0))):
        age = f"{s['age_days']}d old" if s["age_days"] is not None else "unparseable set_at"
        print(
            f"  {s['family']}/{s['platform']}: pending since "
            f"{s['content_healing_status_set_at']!r} ({age}) -- run "
            f"package_install_migrator.py {s['family']} {s['platform']} --dry-run",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
