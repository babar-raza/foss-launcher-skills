"""inventory_capabilities.py — Load and merge capability inventory.

Reads skills/registry.yaml (canonical) and .governance/capabilities/registry.yaml
(contract extensions), emits a unified capability inventory.

Usage:
    python tools/capability_sync/inventory_capabilities.py
    python tools/capability_sync/inventory_capabilities.py --json
    python tools/capability_sync/inventory_capabilities.py --output .governance/generated/baseline.yaml
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SKILLS_REGISTRY = _REPO_ROOT / "skills" / "registry.yaml"
_GOV_REGISTRY = _REPO_ROOT / ".governance" / "capabilities" / "registry.yaml"
_SKILLS_DIR = _REPO_ROOT / "skills"
_CLAUDE_COMMANDS = _REPO_ROOT / ".claude" / "commands"
_AGENTS_SKILLS = _REPO_ROOT / ".agents" / "skills"
_KILO_SKILLS = _REPO_ROOT / ".kilocode" / "skills"


def load_skills_registry() -> list[dict[str, Any]]:
    """Load skills from the canonical skills/registry.yaml."""
    if not _HAS_YAML:
        raise RuntimeError("pyyaml is required: pip install pyyaml")
    if not _SKILLS_REGISTRY.exists():
        raise FileNotFoundError(f"skills/registry.yaml not found: {_SKILLS_REGISTRY}")
    with open(_SKILLS_REGISTRY, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("skills", [])


def load_gov_metadata() -> dict[str, Any]:
    """Load contract extensions from .governance/capabilities/registry.yaml."""
    if not _HAS_YAML or not _GOV_REGISTRY.exists():
        return {}
    with open(_GOV_REGISTRY, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("capability_metadata", {})


def build_inventory() -> dict[str, Any]:
    """Build the unified capability inventory."""
    skills = load_skills_registry()
    gov_meta = load_gov_metadata()

    capabilities: list[dict[str, Any]] = []
    for skill in skills:
        skill_id = skill.get("id", "")
        name = skill.get("name", "")
        internal = skill.get("internal", False)

        # Check adapter presence
        canonical_path = _SKILLS_DIR / f"{name}.md"
        claude_path = _CLAUDE_COMMANDS / f"{name}.md"
        agents_path = _AGENTS_SKILLS / name / "SKILL.md"
        kilo_path = _KILO_SKILLS / name / "SKILL.md"

        # Merge contract extensions from .governance
        ext = gov_meta.get(skill_id, {})

        capabilities.append({
            "id": skill_id,
            "name": name,
            "description": skill.get("description", ""),
            "internal": internal,
            "script": skill.get("script"),
            "category": ext.get("category", "unknown"),
            "operation_type": ext.get("operation_type", "unknown"),
            "mutating": ext.get("mutating", None),
            "idempotency": ext.get("idempotency", "unknown"),
            "adapters": {
                "canonical": str(canonical_path.relative_to(_REPO_ROOT)) if canonical_path.exists() else None,
                "canonical_exists": canonical_path.exists(),
                "claude_command": str(claude_path.relative_to(_REPO_ROOT)) if not internal and claude_path.exists() else None,
                "claude_command_exists": (not internal and claude_path.exists()),
                "agent_skill": str(agents_path.relative_to(_REPO_ROOT)) if agents_path.exists() else None,
                "agent_skill_exists": agents_path.exists(),
                "kilo_skill": str(kilo_path.relative_to(_REPO_ROOT)) if kilo_path.exists() else None,
                "kilo_skill_exists": kilo_path.exists(),
            },
        })

    total = len(capabilities)
    public = sum(1 for c in capabilities if not c["internal"])
    internal_count = sum(1 for c in capabilities if c["internal"])

    return {
        "schema_version": 1,
        "canonical_registry": "skills/registry.yaml",
        "total_capabilities": total,
        "public_capabilities": public,
        "internal_capabilities": internal_count,
        "capabilities": capabilities,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inventory all capabilities from skills/registry.yaml.")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--output", help="Write output to file instead of stdout")
    args = parser.parse_args(argv)

    try:
        inventory = build_inventory()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.json:
        text = json.dumps(inventory, indent=2, ensure_ascii=False) + "\n"
    elif _HAS_YAML:
        text = yaml.dump(inventory, default_flow_style=False, allow_unicode=True)
    else:
        text = json.dumps(inventory, indent=2, ensure_ascii=False) + "\n"

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text, encoding="utf-8")
        print(f"Inventory written to {args.output}")
    else:
        sys.stdout.write(text)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
