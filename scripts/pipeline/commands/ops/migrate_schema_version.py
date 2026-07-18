"""migrate_schema_version.py — ST-035: stamp schema_version onto pre-existing
derived artifacts, without re-deriving any of their content.

RPR-J-08 made progress.json, execution_reconciliation.json, and
page_decisions.json writers stamp a schema_version field on every NEW write,
and made 4 --verify read sites route a missing/mismatched version to
UNKNOWN rather than trusting a stale-shape field default. RPR-J-10's
independent Lane I review found the natural, expected consequence: every
real, already-on-disk artifact for the pilot products predates
schema_version, so Check 8 Case A (the exact tracking-gap detector this
whole re-foundation exists to fix) is currently safe-but-inert on real
data — it correctly reports UNKNOWN, but that means it is not actually
guarding anything yet.

This is deliberately a FORMAT migration, not a content regeneration: it
adds the schema_version key to an existing, already-correct file's data —
it does not re-run page_impact_assess, write_reconciliation, or any other
decision-producing step, and it does not change any existing field's
value. Re-deriving decisions from scratch is a much larger, riskier
operation (it could change what a page's disposition actually IS, not
just how a reader interprets its shape) and is explicitly out of scope
here — this only makes an old-shape "empty-looking" file readable by the
new, stricter schema-version-aware checks.

Usage:
    python migrate_schema_version.py                    # dry-run: report what would change
    python migrate_schema_version.py --apply             # write the migrated files
    python migrate_schema_version.py --apply --family pdf --platform net   # one product only
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PIPELINE_ROOT = _HERE.parent.parent
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

_REPO_ROOT = Path(__file__).resolve().parents[4]

_PROGRESS_SCHEMA_VERSION = 2
_RECONCILIATION_SCHEMA_VERSION = 2
_PAGE_DECISIONS_SCHEMA_VERSION = 2

# (relative dir under reports/, filename, schema_version) -- mirrors the three
# artifact kinds post_refresh_verify.py / refresh_review.py know about.
_ARTIFACT_KINDS = (
    ("refresh_state", "progress.json", _PROGRESS_SCHEMA_VERSION),
    ("refresh_state", "execution_reconciliation.json", _RECONCILIATION_SCHEMA_VERSION),
    ("refresh_review", "page_decisions.json", _PAGE_DECISIONS_SCHEMA_VERSION),
)


def _discover_products(repo_root: Path) -> list[tuple[str, str]]:
    """Find every (family, platform) pair with at least one of the three
    artifact kinds present under reports/{refresh_state,refresh_review}/."""
    found: set[tuple[str, str]] = set()
    for subdir, filename, _ in _ARTIFACT_KINDS:
        base = repo_root / "reports" / subdir
        if not base.is_dir():
            continue
        for path in base.glob(f"*/*/{filename}"):
            platform = path.parent.name
            family = path.parent.parent.name
            found.add((family, platform))
    return sorted(found)


def migrate_one(
    repo_root: Path, family: str, platform: str, *, apply: bool
) -> list[dict]:
    """Return a list of per-artifact result dicts for one product.
    {"path": str, "kind": str, "action": "already_current"|"would_migrate"|"migrated"|"absent"|"unreadable"}
    """
    results = []
    for subdir, filename, expected_version in _ARTIFACT_KINDS:
        path = repo_root / "reports" / subdir / family / platform / filename
        entry = {"path": str(path.relative_to(repo_root)), "kind": filename}
        if not path.is_file():
            entry["action"] = "absent"
            results.append(entry)
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            entry["action"] = "unreadable"
            entry["error"] = str(exc)
            results.append(entry)
            continue
        if not isinstance(data, dict):
            entry["action"] = "unreadable"
            entry["error"] = "top-level JSON is not an object"
            results.append(entry)
            continue
        if data.get("schema_version") == expected_version:
            entry["action"] = "already_current"
            results.append(entry)
            continue
        entry["previous_schema_version"] = data.get("schema_version")
        if not apply:
            entry["action"] = "would_migrate"
            results.append(entry)
            continue
        data["schema_version"] = expected_version
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        entry["action"] = "migrated"
        results.append(entry)
    return results


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="migrate_schema_version",
        description="ST-035: stamp schema_version onto pre-existing derived artifacts (format-only migration).",
    )
    parser.add_argument("--apply", action="store_true",
                        help="Write the migrated files (default: dry-run, report only)")
    parser.add_argument("--family", default=None, help="Migrate one product only (requires --platform)")
    parser.add_argument("--platform", default=None, help="Migrate one product only (requires --family)")
    parser.add_argument("--repo-root", default=str(_REPO_ROOT))
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root)

    if args.family and args.platform:
        products = [(args.family, args.platform)]
    elif args.family or args.platform:
        print("ERROR: --family and --platform must be given together", file=sys.stderr)
        return 2
    else:
        products = _discover_products(repo_root)

    if not products:
        print("No products found with progress.json / execution_reconciliation.json / "
              "page_decisions.json under reports/.")
        return 0

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"migrate_schema_version.py ({mode}) — {len(products)} product(s)")

    totals = {"already_current": 0, "would_migrate": 0, "migrated": 0, "absent": 0, "unreadable": 0}
    for family, platform in products:
        results = migrate_one(repo_root, family, platform, apply=args.apply)
        for r in results:
            totals[r["action"]] += 1
            if r["action"] in ("would_migrate", "migrated"):
                prev = r.get("previous_schema_version")
                print(f"  [{r['action']}] {r['path']} (schema_version: {prev!r} -> current)")
            elif r["action"] == "unreadable":
                print(f"  [unreadable] {r['path']}: {r.get('error')}")

    print(
        f"Totals: already_current={totals['already_current']} "
        f"{'migrated' if args.apply else 'would_migrate'}="
        f"{totals['migrated'] if args.apply else totals['would_migrate']} "
        f"absent={totals['absent']} unreadable={totals['unreadable']}"
    )
    if not args.apply and totals["would_migrate"] > 0:
        print("Run with --apply to write these changes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
