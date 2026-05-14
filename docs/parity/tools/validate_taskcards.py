#!/usr/bin/env python3
"""Validate required sections exist in generated taskcards."""

from __future__ import annotations

import json
from pathlib import Path


REQUIRED = [
    "## Purpose",
    "## Exact Scope",
    "## Inputs",
    "## Files/Areas Allowed To Change",
    "## Files/Areas Forbidden To Change",
    "## Dependencies",
    "## Implementation Steps",
    "## Verification Steps",
    "## Expected Artifacts",
    "## Risk Notes",
    "## Rollback Notes",
    "## Done Criteria",
]


def main() -> int:
    root = Path("docs/parity/taskcards")
    files = sorted(path for path in root.glob("TC-P6-*.md"))
    failures = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        missing = [section for section in REQUIRED if section not in text]
        if missing:
            failures.append({"path": str(path), "missing": missing})
        if "D:/onedrive/Documents/GitHub/aspose.org/content/**" not in text:
            failures.append({"path": str(path), "missing": ["aspose.org content forbidden path"]})
    result = {"taskcards_checked": len(files), "failures": failures}
    print(json.dumps(result, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
