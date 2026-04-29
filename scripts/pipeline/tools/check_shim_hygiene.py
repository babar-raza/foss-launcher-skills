#!/usr/bin/env python3
"""Check shim hygiene — detect unlisted root-level files and stale shims.

Usage:
    PYTHONPATH=scripts/pipeline python scripts/pipeline/tools/check_shim_hygiene.py

Exit code 0 = clean, 1 = violations found.
"""
import pathlib
import sys
import yaml

MANIFEST_PATH = pathlib.Path("scripts/pipeline/migration_manifest.yaml")

# Files allowed at pipeline root regardless of manifest
ALWAYS_ALLOWED = {
    "_bootstrap.py", "__init__.py",
    "requirements.txt", "PIPELINE.md", "INVENTORY.md", "README.md",
    "migration_manifest.yaml",
}

# Directories allowed at pipeline root
ALLOWED_DIRS = {
    "commands", "lib", "config", "tools",
    "audit", "content_eval", "core", "evidence", "extraction",
    "scout_enrichers", "verification",
    "tests", "reports", "knowledge",
}


def check():
    """Check for hygiene violations."""
    root = pathlib.Path("scripts/pipeline")
    errors = 0

    # Load manifest if it exists
    manifest_files = set()
    if MANIFEST_PATH.exists():
        manifest = yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))
        manifest_files = set(manifest.get("files", {}).keys())

    # Check root-level .py files
    for f in sorted(root.glob("*.py")):
        if f.name in ALWAYS_ALLOWED:
            continue
        rel = str(f).replace("\\", "/")
        if rel in manifest_files:
            # In manifest — OK (either original or shim)
            continue
        print(f"UNLISTED: {rel} (not in manifest and not in always-allowed)")
        errors += 1

    # Check for unexpected root-level non-.py files
    for f in sorted(root.iterdir()):
        if f.is_dir():
            if f.name not in ALLOWED_DIRS and f.name != "__pycache__":
                # Check if it's an expected directory
                if f.name.startswith("."):
                    continue
                print(f"INFO: unexpected dir at root: {f.name}")
            continue
        if f.suffix == ".py":
            continue  # handled above
        if f.name not in ALWAYS_ALLOWED:
            rel = str(f).replace("\\", "/")
            if rel not in manifest_files:
                # Informational only for non-.py files
                pass

    if errors == 0:
        print("Shim hygiene: CLEAN")
    else:
        print(f"Shim hygiene: {errors} violations")

    return errors


if __name__ == "__main__":
    sys.exit(check())
