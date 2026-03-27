"""One-time migration: add repo_url and stale_since: null to all merged/model.yaml files.

Safe to run multiple times (idempotent). Does not overwrite existing repo_url if present.

Usage:
    python scripts/maintenance/migrate_model_yaml.py
"""
import sys
import yaml
from pathlib import Path

KNOWLEDGE_ROOT = Path("knowledge")


def migrate() -> int:
    updated = 0
    skipped = 0
    errors = 0

    model_paths = sorted(KNOWLEDGE_ROOT.glob("*/*/merged/model.yaml"))
    if not model_paths:
        print(f"No model.yaml files found under {KNOWLEDGE_ROOT}/")
        return 0

    for model_path in model_paths:
        try:
            text = model_path.read_text(encoding="utf-8")
            model = yaml.safe_load(text) or {}
        except Exception as exc:
            print(f"  ERROR  {model_path}: {exc}", file=sys.stderr)
            errors += 1
            continue

        changed = False

        if "repo_url" not in model:
            model["repo_url"] = ""
            changed = True

        if "stale_since" not in model:
            model["stale_since"] = None
            changed = True

        if changed:
            try:
                model_path.write_text(
                    yaml.dump(model, default_flow_style=False, sort_keys=False,
                              allow_unicode=True),
                    encoding="utf-8",
                )
                print(f"  UPDATED {model_path}")
                updated += 1
            except Exception as exc:
                print(f"  ERROR  {model_path}: write failed: {exc}", file=sys.stderr)
                errors += 1
        else:
            print(f"  OK      {model_path}")
            skipped += 1

    print(f"\nMigration complete: {updated} updated, {skipped} already current, {errors} errors.")
    return errors


if __name__ == "__main__":
    sys.exit(migrate())
