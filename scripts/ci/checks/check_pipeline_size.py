#!/usr/bin/env python3
"""check_pipeline_size.py — Advisory size alert for scripts/pipeline/ root files.

Emits warnings (non-blocking) when root .py files exceed configured thresholds.
Helps maintainers identify files that have grown beyond a sustainable size
before they become maintenance hotspots.

Thresholds:
  WARN  : >= 600 lines  (current p95 ≈ 660)
  ALERT : >= 1000 lines (hard alert; file is likely doing too much)

This script is ADVISORY only — it always exits 0.
It is designed to be run as a CI step in content-audit.yml.

Usage:
    python scripts/ci/checks/check_pipeline_size.py
    python scripts/ci/checks/check_pipeline_size.py --fail-on-alert  # exit 1 if any ALERT
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PIPELINE_ROOT = REPO_ROOT / "scripts" / "pipeline"

WARN_LINES = 600
ALERT_LINES = 1000


def count_lines(path: Path) -> int:
    try:
        return sum(1 for _ in path.read_text(encoding="utf-8", errors="replace").splitlines())
    except OSError:
        return 0


def check_sizes(fail_on_alert: bool = False) -> int:
    py_files = sorted(PIPELINE_ROOT.glob("*.py"))
    warns: list[tuple[str, int]] = []
    alerts: list[tuple[str, int]] = []

    for f in py_files:
        if f.name == "__init__.py":
            continue
        n = count_lines(f)
        rel = str(f.relative_to(REPO_ROOT))
        if n >= ALERT_LINES:
            alerts.append((rel, n))
        elif n >= WARN_LINES:
            warns.append((rel, n))

    if warns:
        print(f"SIZE-WARN: {len(warns)} file(s) >= {WARN_LINES} lines:", file=sys.stderr)
        for rel, n in warns:
            print(f"  {rel}: {n} lines", file=sys.stderr)

    if alerts:
        print(f"SIZE-ALERT: {len(alerts)} file(s) >= {ALERT_LINES} lines:", file=sys.stderr)
        for rel, n in alerts:
            print(f"  {rel}: {n} lines (consider splitting)", file=sys.stderr)

    total = len(warns) + len(alerts)
    status = "ADVISORY" if not (fail_on_alert and alerts) else "FAIL"
    print(
        f"[{status}] Pipeline size check: {len(py_files)} files scanned, "
        f"{len(alerts)} alerts, {len(warns)} warnings."
    )

    if fail_on_alert and alerts:
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--fail-on-alert",
        action="store_true",
        help=f"Exit 1 if any file >= {ALERT_LINES} lines (default: always exit 0)",
    )
    args = parser.parse_args()
    return check_sizes(fail_on_alert=args.fail_on_alert)


if __name__ == "__main__":
    sys.exit(main())
