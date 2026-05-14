#!/usr/bin/env python3
"""Rank missing dependency details from a parity JSON or the Phase 4 gap report."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parity", type=Path)
    args = parser.parse_args()
    counter: Counter[str] = Counter()
    if args.parity and args.parity.exists():
        data = json.loads(args.parity.read_text(encoding="utf-8"))
        for item in data.get("gaps", []):
            if item.get("category") != "missing dependency":
                continue
            detail = item.get("detail", "")
            if "absent from standalone:" not in detail:
                continue
            for part in detail.split("absent from standalone:", 1)[1].split(","):
                value = part.strip().strip("| ")
                if value:
                    counter[value] += 1
        for value, count in counter.most_common(50):
            print(f"{count}\t{value}")
        return 0

    for line in Path("docs/parity/gap-report-phase4.md").read_text(encoding="utf-8").splitlines():
        if "missing dependency" not in line or "Referenced aspose.org script paths absent" not in line:
            continue
        if "absent from standalone:" not in line:
            continue
        detail = line.split("absent from standalone:", 1)[1]
        for part in detail.split(","):
            value = part.strip().strip("| ")
            if value:
                counter[value] += 1
    for value, count in counter.most_common(50):
        print(f"{count}\t{value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
