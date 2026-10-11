#!/usr/bin/env python3
"""check_backlink_target_map_freshness.py — staleness gate for data/aspose_com_targets.json.

Added 2026-08-06 (MT022-2026-08-06-ASPOSE-COM-TARGETS-HARDENING, TC-03).

data/aspose_com_targets.json's provenance.generated_at was written by
fetch_aspose_com_targets.py on every run but read by zero consumers -- a
redirect-bug-fix commit (e40ed6b509) found 5 entries had gone silently stale
(404/403/502) over 6 weeks with nothing noticing, precisely because nothing
anywhere checked this field's age. batch_reference.py now WARNs (advisory,
see scripts/pipeline/lib/backlink_targets.py::target_map_age_days /
STALE_WARN_DAYS) at generation time; this script is the harder, CI-enforceable
gate at STALE_BLOCK_DAYS.

Usage:
    python scripts/ci/checks/check_backlink_target_map_freshness.py
    python scripts/ci/checks/check_backlink_target_map_freshness.py --repo-root <path>

Exit codes:
    0   fresh (age <= STALE_BLOCK_DAYS), or file missing entirely (nothing to
        gate yet -- fetch_aspose_com_targets.py has never been run; that's a
        different, pre-existing condition this check does not own)
    1   stale (age > STALE_BLOCK_DAYS) -- run fetch_aspose_com_targets.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PIPELINE_LIB = _HERE.parents[1] / "pipeline" / "lib"
if str(_PIPELINE_LIB) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_LIB))

from backlink_targets import load_target_map, target_map_age_days, STALE_BLOCK_DAYS  # noqa: E402

_DEFAULT_REPO_ROOT = _HERE.parents[2]


def check_freshness(repo_root: Path) -> int:
    try:
        target_map = load_target_map(repo_root)
    except FileNotFoundError:
        print(
            "check_backlink_target_map_freshness: data/aspose_com_targets.json "
            "not found -- nothing to check yet (run fetch_aspose_com_targets.py "
            "to generate it). Not this check's failure mode; exiting 0.",
            file=sys.stderr,
        )
        return 0
    except Exception as exc:
        print(f"check_backlink_target_map_freshness: could not load target map: {exc}", file=sys.stderr)
        return 0

    age_days = target_map_age_days(target_map)
    if age_days is None:
        print(
            "check_backlink_target_map_freshness: provenance.generated_at "
            "missing/unparseable -- cannot determine age. Not blocking (this "
            "is a data-shape issue, not a staleness issue), but investigate.",
            file=sys.stderr,
        )
        return 0

    if age_days > STALE_BLOCK_DAYS:
        print(
            f"FAIL: data/aspose_com_targets.json is {age_days:.1f} days old "
            f"(block threshold: {STALE_BLOCK_DAYS}). Run "
            f"scripts/pipeline/commands/ops/fetch_aspose_com_targets.py to refresh.",
            file=sys.stderr,
        )
        return 1

    print(
        f"OK: data/aspose_com_targets.json is {age_days:.1f} days old "
        f"(block threshold: {STALE_BLOCK_DAYS}).",
        file=sys.stderr,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=_DEFAULT_REPO_ROOT)
    args = parser.parse_args(argv)
    return check_freshness(args.repo_root)


if __name__ == "__main__":
    sys.exit(main())
