"""Refresh golden corpus files from an external source.

Optional maintenance utility — NOT a runtime dependency. The project works
entirely standalone without this script.

Usage:
    python scripts/refresh_golden.py [--source /path/to/foss-launcher/golden]

Defaults to ../foss-launcher/golden/ as source. Copies files, reports changes,
and regenerates golden/_index.json.
"""
import filecmp
import shutil
import subprocess
import sys
from pathlib import Path

from config_loader import load_config, resolve_golden_dir


def _find_source(override: str = "") -> Path:
    """Find the source golden directory."""
    if override:
        return Path(override)

    config = load_config()
    source = config.get("golden_source", "")
    if source and Path(source).is_dir():
        return Path(source)

    # Default: sibling repo
    default = Path(__file__).resolve().parent.parent.parent / "foss-launcher" / "golden"
    if default.is_dir():
        return default

    return Path("")


def refresh(source: Path, target: Path) -> dict:
    """Copy golden files from source to target, returning change summary."""
    if not source.is_dir():
        print(f"ERROR: Source directory not found: {source}")
        return {"error": str(source)}

    target.mkdir(parents=True, exist_ok=True)

    added = []
    modified = []
    unchanged = []

    for src_file in sorted(source.rglob("*.md")):
        rel = src_file.relative_to(source)
        dst_file = target / rel

        if not dst_file.exists():
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dst_file)
            added.append(str(rel))
        elif not filecmp.cmp(src_file, dst_file, shallow=False):
            shutil.copy2(src_file, dst_file)
            modified.append(str(rel))
        else:
            unchanged.append(str(rel))

    # Check for deleted files in target that no longer exist in source
    deleted = []
    for dst_file in sorted(target.rglob("*.md")):
        if dst_file.name == "README.md":
            continue
        rel = dst_file.relative_to(target)
        src_file = source / rel
        if not src_file.exists():
            deleted.append(str(rel))
            # Don't auto-delete — just report

    return {
        "added": added,
        "modified": modified,
        "unchanged": unchanged,
        "deleted_in_source": deleted,
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Refresh golden corpus from external source")
    parser.add_argument("--source", default="", help="Path to source golden/ directory")
    parser.add_argument("--no-index", action="store_true", help="Skip regenerating golden/_index.json")
    args = parser.parse_args()

    source = _find_source(args.source)
    target = resolve_golden_dir()

    print(f"Refresh golden corpus")
    print(f"  Source: {source}")
    print(f"  Target: {target}")

    if not source.is_dir():
        print(f"  ERROR: Source not found. Specify --source or set golden_source in config.yaml")
        sys.exit(1)

    result = refresh(source, target)

    print(f"\n  Added:     {len(result['added'])}")
    for f in result["added"]:
        print(f"    + {f}")
    print(f"  Modified:  {len(result['modified'])}")
    for f in result["modified"]:
        print(f"    ~ {f}")
    print(f"  Unchanged: {len(result['unchanged'])}")
    if result["deleted_in_source"]:
        print(f"  Deleted in source (NOT auto-removed): {len(result['deleted_in_source'])}")
        for f in result["deleted_in_source"]:
            print(f"    ! {f}")

    total_changes = len(result["added"]) + len(result["modified"])
    if total_changes == 0:
        print("\n  No changes detected.")
    elif not args.no_index:
        print("\n  Regenerating golden/_index.json...")
        scripts_dir = Path(__file__).resolve().parent
        subprocess.run(
            [sys.executable, str(scripts_dir / "golden_index.py")],
            check=True,
        )
        print("  Index regenerated.")

    print(f"\nREFRESH: {'PASS' if 'error' not in result else 'FAIL'}")


if __name__ == "__main__":
    main()
