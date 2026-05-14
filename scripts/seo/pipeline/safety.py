#!/usr/bin/env python3
"""Validate SEO recommendation/patch safety constraints."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.seo.pipeline.apply import validate_patch


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args(argv)
    data = json.loads(args.manifest.read_text(encoding="utf-8"))
    patches = data.get("patches", [])
    issues = []
    for index, patch in enumerate(patches):
        for error in validate_patch(patch):
            issues.append({"index": index, "page_path": patch.get("page_path"), "error": error})
    print(json.dumps({"ok": not issues, "issues": issues}, indent=2, sort_keys=True))
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
