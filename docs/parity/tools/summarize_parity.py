#!/usr/bin/env python3
"""Print compact parity matrix groups."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    for status in sorted({row["status"] for row in data["rows"]}):
        print()
        print(status)
        for row in [item for item in data["rows"] if item["status"] == status][:30]:
            print("-", row["canonical_name"], row["gap_categories"])
    print()
    print("standalone-only", [item["canonical_name"] for item in data["standalone_only_capabilities"]])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
