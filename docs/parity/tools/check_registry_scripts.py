#!/usr/bin/env python3
"""Check whether skills/registry.yaml script bindings exist."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def parse_registry(path: Path) -> list[dict[str, str | None]]:
    items: list[dict[str, str | None]] = []
    current: dict[str, str | None] | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if re.match(r"^\s*-\s+id:\s*", line):
            if current:
                items.append(current)
            current = {"id": line.split(":", 1)[1].strip()}
        elif current is not None and re.match(r"^\s+[a-z_]+:\s*", line):
            key, value = line.strip().split(":", 1)
            value = value.strip()
            if "#" in value:
                value = value.split("#", 1)[0].strip()
            current[key] = None if value == "null" else value
    if current:
        items.append(current)
    return items


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    items = parse_registry(root / "skills" / "registry.yaml")
    present = []
    null = []
    missing = []
    for item in items:
        script = item.get("script")
        name = item.get("name")
        if not script:
            null.append(name)
        elif not (root / script).exists():
            missing.append({"name": name, "script": script})
        else:
            present.append({"name": name, "script": script})
    print(
        json.dumps(
            {
                "registry_items": len(items),
                "script_present": len(present),
                "script_null": len(null),
                "script_missing": missing,
                "script_null_names": null,
            },
            indent=2,
        )
    )
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
