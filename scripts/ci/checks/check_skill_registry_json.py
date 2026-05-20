"""Validate skills/registry.json matches canonical skills/ directory.

Checks:
  1. registry.json exists
  2. skill_count matches number of canonical skills with S-XX IDs
  3. Every canonical skill with an S-XX ID has an entry in registry.json
  4. No orphan entries in registry.json that don't exist in canonical

Usage:
    python scripts/ci/checks/check_skill_registry_json.py
    python scripts/ci/checks/check_skill_registry_json.py --json

Exit codes:
    0  All checks pass
    1  One or more checks failed
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
REGISTRY_PATH = _REPO_ROOT / "skills" / "registry.json"
CANONICAL_DIR = _REPO_ROOT / "skills"

_ID_RE = re.compile(r"^#\s+(S-\d+):")


def _discover_canonical() -> dict[str, str]:
    """Return {slug: skill_id} for all canonical skills with S-XX IDs."""
    result = {}
    for p in sorted(CANONICAL_DIR.glob("*.md")):
        slug = p.stem
        if slug.lower() == "readme":
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        for line in text[:1500].splitlines():
            m = _ID_RE.match(line)
            if m:
                result[slug] = m.group(1)
                break
    return result


def check() -> list[str]:
    """Run all checks. Returns list of error messages (empty = pass)."""
    errors = []

    if not REGISTRY_PATH.exists():
        errors.append("skills/registry.json does not exist. Run: python scripts/pipeline/commands/ops/sync_providers.py")
        return errors

    try:
        registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        errors.append(f"Failed to parse skills/registry.json: {e}")
        return errors

    canonical = _discover_canonical()
    registry_slugs = {s["slug"]: s["id"] for s in registry.get("skills", [])}

    # Check count
    if registry.get("skill_count") != len(canonical):
        errors.append(
            f"skill_count mismatch: registry says {registry.get('skill_count')}, "
            f"canonical has {len(canonical)}"
        )

    # Missing from registry
    for slug in sorted(canonical):
        if slug not in registry_slugs:
            errors.append(f"Missing from registry: {slug} ({canonical[slug]})")
        elif registry_slugs[slug] != canonical[slug]:
            errors.append(
                f"ID mismatch for {slug}: registry has {registry_slugs[slug]}, "
                f"canonical has {canonical[slug]}"
            )

    # Orphans in registry
    for slug in sorted(registry_slugs):
        if slug not in canonical:
            errors.append(f"Orphan in registry: {slug} (not in canonical skills/)")

    return errors


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Validate skills/registry.json matches canonical skills/.",
    )
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args(argv)

    errors = check()

    if args.json:
        print(json.dumps({"passed": not errors, "errors": errors}, indent=2))
    else:
        if errors:
            print(f"FAIL: {len(errors)} issue(s) in skills/registry.json")
            for e in errors:
                print(f"  {e}")
        else:
            print("PASS: skills/registry.json matches canonical skills/")

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
