"""st054_seed_taskcards.py — ST-054 TC-19
(plans/from_backlog/2026-08-16-st-054-inline-install-command-remediation.md).

Seeds the ST-054-REMEDIATION mission's taskcards.jsonl (via TaskcardStore,
schema 5f) with the per-product remediation queue. This is the durable
work-queue replacement for what this campaign's TC-06/07/08 previously did by
hand, one CLI invocation at a time, per session, with no persisted state of
what had already been attempted -- the structural reason a fully-built
toolchain only net-fixed ~68 of 6,522 occurrences in a dedicated remediation
pass (see the governing plan's Reassessment section).

4 steps per product, `dependencies`-chained so taskcard_cli.py's own `ready`
command sequences them correctly without this module needing to reimplement
that logic:

    block_migrate (wave 1) -> inline_migrate (wave 2) -> verify (wave 3) -> commit (wave 4)

Deliberately only 4 steps, not 5 -- the original plan named a separate
"locale_patch" step driven by S-75, but package_install_migrator.py's own
discover_files() already walks every locale directory + locale-suffix file
for a product (confirmed via direct read, not assumed: its docstring says
"across in-scope subsites, all locales"), and migrate_file() in BOTH
migrators is path-agnostic -- neither function has an English-only
assumption baked in, only package_install_inline_migrator.py's separate
discover_files_english_only() enforces that restriction, as a TC-06 SCOPING
CHOICE ("S-75 handles locale propagation separately"), not a technical
requirement. st054_campaign_worker.py's block_migrate/inline_migrate steps
therefore run against every locale directly, reusing each migrator's own
already-tested, already-safety-proven transform logic uniformly, rather than
adding a second, S-75-based patch-derivation layer on top.

`cells/net` (the one product reports/audit/st-054-collision-classification-2026-08-16.md
calls a genuine structural collision, not a benign packaging-convention hit)
gets every row tagged `needs_manual_review: true` -- consumed by
st054_campaign_worker.py to require a human diff review between `verify` and
`commit`, per explicit operator direction, rather than fully unattended
commit-and-push like every other product.

CLI:
    PYTHONPATH=scripts/pipeline .venv/Scripts/python -m commands.ops.st054_seed_taskcards \
        --products note/python cells/python --mission ST-054-REMEDIATION
    PYTHONPATH=scripts/pipeline .venv/Scripts/python -m commands.ops.st054_seed_taskcards \
        --products cells/net --needs-manual-review --mission ST-054-REMEDIATION
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))
_LIB_DIR = str(_PIPELINE_ROOT / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from taskcard_store import TaskcardStore  # noqa: E402
from session_identity import resolve_sanitized as _resolve_session_identity  # noqa: E402

DEFAULT_MISSION_ID = "ST-054-REMEDIATION"

STEPS = ("block_migrate", "inline_migrate", "verify", "commit")
_WAVE_OF = {step: i + 1 for i, step in enumerate(STEPS)}

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[4]
_REPO_ROOT = _DEFAULT_REPO_ROOT


def configure(*, repo_root: "Path | str | None" = None) -> None:
    global _REPO_ROOT
    _REPO_ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT


def task_id(family: str, platform: str, step: str) -> str:
    return f"TC-{family}-{platform}-{step}"


def build_rows_for_product(
    family: str, platform: str, *, needs_manual_review: bool = False,
) -> list[dict[str, Any]]:
    """The 4-row, dependency-chained taskcard set for one product. Pure --
    no I/O, easy to unit test and to inspect before seeding."""
    rows = []
    prior_id = None
    for step in STEPS:
        tid = task_id(family, platform, step)
        row: dict[str, Any] = {
            "task_id": tid,
            "mission_id": DEFAULT_MISSION_ID,
            "status": "TODO",
            "title": f"{family}/{platform}: {step}",
            "family": family,
            "platform": platform,
            "step": step,
            "dependencies": [prior_id] if prior_id else [],
            "priority": "P1",
            "wave": _WAVE_OF[step],
            "evidence_refs": [],
        }
        if needs_manual_review:
            row["needs_manual_review"] = True
        rows.append(row)
        prior_id = tid
    return rows


def seed_products(
    products: list[tuple[str, str]],
    *,
    mission_id: str = DEFAULT_MISSION_ID,
    needs_manual_review_products: "set[tuple[str, str]] | None" = None,
    force: bool = False,
    recorded_by: "str | None" = None,
) -> dict[str, Any]:
    """Idempotent: a product whose task_ids already have rows in this
    mission is skipped unless force=True (matching taskcard_cli.py's own
    seed --force semantics, reimplemented here directly against
    TaskcardStore rather than shelling out, since seeding is a one-shot
    setup step, not part of the concurrent claim/advance hot path
    st054_campaign_worker.py drives through the real taskcard_cli.py)."""
    needs_manual_review_products = needs_manual_review_products or set()
    store = TaskcardStore(mission_id, repo_root=_REPO_ROOT)
    existing = store.read_latest()
    who = recorded_by or _resolve_session_identity()

    seeded: list[str] = []
    skipped: list[str] = []
    for family, platform in products:
        needs_review = (family, platform) in needs_manual_review_products
        rows = build_rows_for_product(family, platform, needs_manual_review=needs_review)
        for row in rows:
            if row["task_id"] in existing and not force:
                skipped.append(row["task_id"])
                continue
            row.setdefault("recorded_by", who)
            row.setdefault("recorded_at", datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
            store.append(row)
            seeded.append(row["task_id"])

    return {"mission_id": mission_id, "seeded": seeded, "skipped_existing": skipped}


def _parse_product(spec: str) -> tuple[str, str]:
    if "/" not in spec:
        raise ValueError(f"expected family/platform, got {spec!r}")
    family, platform = spec.split("/", 1)
    return family, platform


def main(argv: "list[str] | None" = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="st054_seed_taskcards")
    parser.add_argument("--products", nargs="+", required=True, metavar="family/platform")
    parser.add_argument("--mission", default=DEFAULT_MISSION_ID)
    parser.add_argument(
        "--needs-manual-review", action="store_true",
        help="Tag every seeded product's rows needs_manual_review (use for cells/net, "
             "never combine with multiple --products unless all of them genuinely need it)",
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    products = [_parse_product(p) for p in args.products]
    needs_review = set(products) if args.needs_manual_review else set()

    result = seed_products(
        products, mission_id=args.mission,
        needs_manual_review_products=needs_review, force=args.force,
    )
    print(f"mission={result['mission_id']} seeded={len(result['seeded'])} skipped_existing={len(result['skipped_existing'])}")
    for tid in result["seeded"]:
        print(f"  seeded: {tid}")
    for tid in result["skipped_existing"]:
        print(f"  skipped (already exists): {tid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
