#!/usr/bin/env python3
"""Print compact facts from a generated skill inventory."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    path = Path(sys.argv[1])
    data = json.loads(path.read_text(encoding="utf-8"))
    records = data["records"]
    print("records", len(records))
    print("unregistered", [r["canonical_name"] for r in records if r["maturity_status"] != "registered"])
    print("no_script_count", sum(1 for r in records if not r["entrypoints"]))
    for key in ["canonical_markdown", "codex_skill", "claude_command", "kilocode_skill"]:
        missing = [r["canonical_name"] for r in records if r["provider_paths"].get(key) is None]
        print(key, len(missing), missing[:40])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
