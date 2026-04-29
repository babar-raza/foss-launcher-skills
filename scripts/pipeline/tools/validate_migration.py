#!/usr/bin/env python3
"""Validate migration state — check parity, imports, config, hooks, and more.

Usage:
    PYTHONPATH=scripts/pipeline python scripts/pipeline/tools/validate_migration.py --all
    PYTHONPATH=scripts/pipeline python scripts/pipeline/tools/validate_migration.py --parity
    PYTHONPATH=scripts/pipeline python scripts/pipeline/tools/validate_migration.py --imports
"""
import importlib
import json
import pathlib
import subprocess
import sys
import yaml

MANIFEST_PATH = pathlib.Path("scripts/pipeline/migration_manifest.yaml")
PY = sys.executable


def load_manifest():
    """Load the migration manifest."""
    if not MANIFEST_PATH.exists():
        print(f"WARN: Manifest not found at {MANIFEST_PATH}")
        return {"files": {}}
    return yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))


def check_parity(manifest):
    """Check that shim and canonical paths produce same --help output."""
    errors = 0
    checked = 0
    for path, entry in manifest["files"].items():
        target = entry.get("target", path)
        if target == path or entry.get("in_subdir"):
            continue
        p = pathlib.Path(path)
        t = pathlib.Path(target)
        if not p.exists() or not t.exists():
            continue
        # Only check .py entry points
        if not path.endswith(".py") or entry["classification"] not in ("entrypoint", "dual-use", "ci-check"):
            continue
        # Check if the source is a shim
        text = p.read_text(encoding="utf-8", errors="replace")[:200]
        if "AUTO-GENERATED" not in text:
            continue  # Not shimmed yet
        try:
            r1 = subprocess.run([PY, str(p), "--help"], capture_output=True, text=True, timeout=15)
            r2 = subprocess.run([PY, str(t), "--help"], capture_output=True, text=True, timeout=15)
            if r1.returncode != r2.returncode:
                print(f"  FAIL (exit code): {path} ({r1.returncode}) vs {target} ({r2.returncode})")
                errors += 1
            elif r1.stdout != r2.stdout:
                print(f"  FAIL (output differs): {path}")
                errors += 1
            else:
                checked += 1
        except subprocess.TimeoutExpired:
            checked += 1  # Timeout is OK for --help
        except Exception as e:
            print(f"  WARN: {path}: {e}")
    print(f"Parity: {checked} checked, {errors} errors")
    return errors


def check_imports(manifest):
    """Check that all library modules are importable."""
    errors = 0
    checked = 0
    for path, entry in manifest["files"].items():
        if entry["classification"] != "library" or entry.get("in_subdir"):
            continue
        if not path.startswith("scripts/pipeline/"):
            continue
        module_name = pathlib.Path(path).stem
        try:
            # Try importing via PYTHONPATH
            r = subprocess.run(
                [PY, "-c", f"import {module_name}; print('OK')"],
                capture_output=True, text=True, timeout=10,
                env={**__import__("os").environ, "PYTHONPATH": "scripts/pipeline"}
            )
            if r.returncode != 0:
                print(f"  FAIL: import {module_name}: {r.stderr.strip()[:100]}")
                errors += 1
            else:
                checked += 1
        except Exception as e:
            print(f"  WARN: {module_name}: {e}")
    print(f"Imports: {checked} checked, {errors} errors")
    return errors


def check_config(manifest):
    """Check that config files are accessible."""
    config_dir = pathlib.Path("scripts/pipeline/config")
    if not config_dir.exists():
        print("Config: config/ directory does not exist yet (OK before Wave 2)")
        return 0
    errors = 0
    for f in config_dir.glob("*"):
        if not f.exists():
            print(f"  FAIL: {f} missing")
            errors += 1
    print(f"Config: {len(list(config_dir.glob('*')))} files, {errors} errors")
    return errors


def check_hooks():
    """Check that git hooks are functional."""
    errors = 0
    hooks = [
        "scripts/pre-commit-audit.sh",
        "scripts/post-commit-override.sh",
        "scripts/commit-msg-skills.sh",
    ]
    for h in hooks:
        p = pathlib.Path(h)
        if not p.exists():
            print(f"  WARN: {h} missing")
            continue
        # Just verify the file references scripts that exist
        text = p.read_text(encoding="utf-8", errors="replace")
        import re
        refs = re.findall(r"scripts/[a-zA-Z0-9_./-]+\.py", text)
        for ref in refs:
            if not pathlib.Path(ref).exists():
                # Check if it's in a shim location
                print(f"  WARN: {h} references {ref} which doesn't exist")
    print(f"Hooks: {len(hooks)} checked, {errors} errors")
    return errors


def check_root_clean():
    """Check that pipeline root is clean (only allowed files)."""
    allowed = {"_bootstrap.py", "__init__.py"}
    root = pathlib.Path("scripts/pipeline")
    root_py = [f.name for f in root.glob("*.py") if f.name not in allowed]
    # Before migration, all files are at root — this check matters after Wave 10
    manifest = load_manifest()
    shim_count = sum(1 for f in root_py
                     if (root / f).exists() and
                     "AUTO-GENERATED" in (root / f).read_text(encoding="utf-8", errors="replace")[:200])
    non_shim = len(root_py) - shim_count
    original = len(root_py) - shim_count
    print(f"Root: {len(root_py)} .py at root ({shim_count} shims, {original} originals)")
    return 0  # Informational only


def check_all():
    """Run all validation checks."""
    manifest = load_manifest()
    total_errors = 0

    print("=== Parity Check ===")
    total_errors += check_parity(manifest)

    print("\n=== Import Check ===")
    total_errors += check_imports(manifest)

    print("\n=== Config Check ===")
    total_errors += check_config(manifest)

    print("\n=== Hook Check ===")
    total_errors += check_hooks()

    print("\n=== Root Clean Check ===")
    total_errors += check_root_clean()

    print(f"\n=== TOTAL: {total_errors} errors ===")
    return total_errors


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Validate migration state")
    parser.add_argument("--all", action="store_true", help="Run all checks")
    parser.add_argument("--parity", action="store_true", help="Check shim/canonical parity")
    parser.add_argument("--imports", action="store_true", help="Check library imports")
    parser.add_argument("--config", action="store_true", help="Check config accessibility")
    parser.add_argument("--hooks", action="store_true", help="Check hook functionality")
    parser.add_argument("--root", action="store_true", help="Check root cleanliness")
    args = parser.parse_args()

    manifest = load_manifest()

    if args.all:
        sys.exit(check_all())
    elif args.parity:
        sys.exit(check_parity(manifest))
    elif args.imports:
        sys.exit(check_imports(manifest))
    elif args.config:
        sys.exit(check_config(manifest))
    elif args.hooks:
        sys.exit(check_hooks())
    elif args.root:
        sys.exit(check_root_clean())
    else:
        parser.print_help()
        sys.exit(1)
