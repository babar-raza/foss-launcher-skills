"""
backlink_capture_current_anchors.py — Capture current anchor text inventory.

Reads the anchor_text_registry.yaml and produces current_anchor_inventory.json
in reports/backlinks/anchor-hardening/. This is a reporting script used for
V18 (Current Anchor Compatibility) evidence.

Plan: A7-09 (moved from reports/workspace/).
"""
import argparse
import json
import pathlib
import hashlib
from datetime import date

import yaml


def compute_anchor_config_hash(registry_path: pathlib.Path) -> str:
    """Compute canonical JSON hash of anchor registry semantic content."""
    data = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    data.pop("config_hash", None)
    canonical = json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return "sha256:" + digest


def main():
    parser = argparse.ArgumentParser(description="Capture current anchor text inventory")
    parser.add_argument("--registry", default="data/backlinks/anchor_text_registry.yaml")
    parser.add_argument(
        "--output",
        default="reports/backlinks/anchor-hardening/current_anchor_inventory.json",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    repo_root = pathlib.Path(__file__).resolve().parent.parent.parent.parent.parent
    registry_path = repo_root / args.registry

    if not registry_path.exists():
        print(f"ERROR: Registry not found: {registry_path}")
        raise SystemExit(1)

    registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    config_hash = compute_anchor_config_hash(registry_path)

    templates = registry.get("templates", {})
    inventory = {
        "schema_version": "1.0.0",
        "generated_at": str(date.today()),
        "config_hash": config_hash,
        "template_count": len(templates),
        "templates": {
            tid: {
                "anchor_text": t.get("anchor_text", ""),
                "page_type": tid,
            }
            for tid, t in templates.items()
        },
    }

    if args.dry_run:
        print(json.dumps(inventory, indent=2))
        return

    output_path = repo_root / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(inventory, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Written: {output_path}")


if __name__ == "__main__":
    main()
