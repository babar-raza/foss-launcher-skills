#!/usr/bin/env python3
# Adapted from aspose.org scripts/ci/checks/ for standalone use
"""render_inventory.py — Validate registry.yaml and generate INVENTORY.md.

Usage:
    python scripts/ci/checks/render_inventory.py           # validate + generate
    python scripts/ci/checks/render_inventory.py --check   # validate only (no write)
    python scripts/ci/checks/render_inventory.py --dry-run # show what would be written

Exit codes:
    0 — all checks pass (+ file written unless --check)
    1 — schema violations or missing files found
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(os.environ.get("REPO_ROOT", Path(__file__).resolve().parents[3]))
REGISTRY_PATH = REPO_ROOT / "scripts" / "pipeline" / "config" / "registry.yaml"
INVENTORY_PATH = REPO_ROOT / "scripts" / "pipeline" / "INVENTORY.md"

REQUIRED_FIELDS = {
    "path", "kind", "lifecycle", "public_entrypoint",
    "cli_contract", "owner_domain", "backing", "test_targets", "notes",
}
VALID_KINDS = {"entrypoint", "library", "one-shot", "shim", "deprecated", "test-support"}
VALID_LIFECYCLES = {"active", "maintenance", "deprecated"}
VALID_CLI_CONTRACT = {"stable", "none"}
VALID_BACKING_KINDS = {"skill", "workflow", "internal"}


def load_registry() -> list[dict]:
    try:
        import yaml
    except ImportError:
        print("ERROR: PyYAML not installed. Run: pip install pyyaml", file=sys.stderr)
        sys.exit(1)
    with open(REGISTRY_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("scripts", [])


def validate(entries: list[dict]) -> list[str]:
    errors: list[str] = []
    seen_paths: set[str] = set()

    for i, entry in enumerate(entries):
        path_str = entry.get("path", f"<entry #{i}>")
        prefix = f"  [{path_str}]"

        # Required fields present
        for field in REQUIRED_FIELDS:
            if field not in entry:
                errors.append(f"{prefix} missing required field: {field}")

        # No duplicate paths
        if path_str in seen_paths:
            errors.append(f"{prefix} duplicate path in registry")
        seen_paths.add(path_str)

        # kind valid
        kind = entry.get("kind", "")
        if kind not in VALID_KINDS:
            errors.append(f"{prefix} invalid kind={kind!r}; must be one of {sorted(VALID_KINDS)}")

        # lifecycle valid
        lc = entry.get("lifecycle", "")
        if lc not in VALID_LIFECYCLES:
            errors.append(f"{prefix} invalid lifecycle={lc!r}")

        # cli_contract valid
        cc = entry.get("cli_contract", "")
        if cc not in VALID_CLI_CONTRACT:
            errors.append(f"{prefix} invalid cli_contract={cc!r}")

        # backing.kind valid
        backing = entry.get("backing", {}) or {}
        bk = backing.get("kind", "")
        if bk not in VALID_BACKING_KINDS:
            errors.append(f"{prefix} invalid backing.kind={bk!r}")

        # File exists on disk
        if path_str and not path_str.startswith("<"):
            disk_path = REPO_ROOT / path_str
            if not disk_path.exists():
                errors.append(f"{prefix} file not found on disk: {disk_path}")

        # test_targets exist if listed
        for t in (entry.get("test_targets") or []):
            if not (REPO_ROOT / t).exists():
                errors.append(f"{prefix} test_target not found: {t}")

    # Every root .py file in scripts/pipeline/ must be in registry
    pipeline_root = REPO_ROOT / "scripts" / "pipeline"
    disk_scripts = {
        f"scripts/pipeline/{p.name}"
        for p in pipeline_root.glob("*.py")
        if p.name != "__init__.py"
    }
    registry_paths = {e.get("path", "") for e in entries}
    unregistered = disk_scripts - registry_paths
    for u in sorted(unregistered):
        errors.append(f"  [UNREGISTERED] {u} exists on disk but has no registry entry")

    return errors


def render_markdown(entries: list[dict]) -> str:
    lines: list[str] = [
        "# scripts/pipeline — Script Inventory",
        "",
        "> **Generated file** — do not edit directly.",
        "> Edit `scripts/pipeline/registry.yaml` and run `python scripts/ci/checks/render_inventory.py`.",
        "",
    ]

    # Group by owner_domain then by kind
    from collections import defaultdict
    by_domain: dict[str, list[dict]] = defaultdict(list)
    for e in entries:
        by_domain[e.get("owner_domain", "uncategorised")].append(e)

    domain_order = [
        "content-quality", "knowledge-pipeline", "content-remediation",
        "content-grading", "content-governance", "backtrack",
        "knowledge-infrastructure", "governance", "kilocode-provider",
        "provenance-maintenance", "product-registry", "cpp-platform",
    ]
    # Append any domains not explicitly listed
    all_domains = list(domain_order)
    for d in sorted(by_domain):
        if d not in all_domains:
            all_domains.append(d)

    total = len(entries)
    lines.append(f"Total scripts: **{total}**\n")

    for domain in all_domains:
        if domain not in by_domain:
            continue
        domain_entries = sorted(by_domain[domain], key=lambda e: e["path"])
        lines.append(f"## {domain.replace('-', ' ').title()} ({len(domain_entries)} files)\n")
        lines.append("| Script | Kind | Lifecycle | Backing | Change Impact | Notes |")
        lines.append("|--------|------|-----------|---------|---------------|-------|")
        for e in domain_entries:
            name = Path(e["path"]).name
            kind = e.get("kind", "")
            lc = e.get("lifecycle", "")
            backing = e.get("backing", {}) or {}
            bk = backing.get("kind", "")
            bref = backing.get("ref") or "—"
            backing_str = f"{bk}/{bref}" if bref != "—" else bk
            impact = (e.get("change_impact") or "—").replace("|", "\\|")
            notes = (e.get("notes") or "").replace("|", "\\|")
            lines.append(f"| `{name}` | {kind} | {lc} | {backing_str} | {impact} | {notes} |")
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Validate only; do not write INVENTORY.md")
    parser.add_argument("--dry-run", action="store_true", help="Show output without writing")
    args = parser.parse_args()

    if not REGISTRY_PATH.exists():
        print(f"ERROR: registry not found at {REGISTRY_PATH}", file=sys.stderr)
        return 1

    entries = load_registry()
    errors = validate(entries)

    if errors:
        print(f"FAIL: {len(errors)} registry error(s):", file=sys.stderr)
        for e in errors:
            print(e, file=sys.stderr)
        return 1

    print(f"OK: registry valid ({len(entries)} entries)")

    if args.check:
        return 0

    md = render_markdown(entries)

    if args.dry_run:
        print("\n--- INVENTORY.md preview ---")
        print(md[:2000])
        if len(md) > 2000:
            print(f"... ({len(md) - 2000} more characters)")
        return 0

    INVENTORY_PATH.write_text(md, encoding="utf-8")
    print(f"Written: {INVENTORY_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
