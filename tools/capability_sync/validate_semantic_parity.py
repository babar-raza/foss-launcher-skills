"""validate_semantic_parity.py — Semantic parity validation across all agent adapter surfaces.

For each capability in skills/registry.yaml, reads the canonical skill body and
compares it to each adapter surface (.claude/commands/, .agents/skills/, .kilocode/skills/).

Reports FULL_PARITY, CLAUDE_ADAPTER_MISSING, AGENT_SKILL_ADAPTER_MISSING, or SEMANTIC_DRIFT.
Emits .governance/generated/parity-report.yaml.

Usage:
    python tools/capability_sync/validate_semantic_parity.py --check   # exit 1 on any gap
    python tools/capability_sync/validate_semantic_parity.py --sync    # write parity-report.yaml
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SKILLS_DIR = _REPO_ROOT / "skills"
_CLAUDE_COMMANDS = _REPO_ROOT / ".claude" / "commands"
_AGENTS_SKILLS = _REPO_ROOT / ".agents" / "skills"
_KILO_SKILLS = _REPO_ROOT / ".kilocode" / "skills"
_PARITY_REPORT = _REPO_ROOT / ".governance" / "generated" / "parity-report.yaml"

_FRONTMATTER_RE = re.compile(r"^---\n.*?\n---\n?", re.DOTALL)


def strip_frontmatter(text: str) -> str:
    stripped = _FRONTMATTER_RE.sub("", text, count=1)
    return stripped.lstrip("\n")


def body_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def load_skills() -> list[dict[str, Any]]:
    if not _HAS_YAML:
        raise RuntimeError("pyyaml required: pip install pyyaml")
    registry = _SKILLS_DIR / "registry.yaml"
    if not registry.exists():
        raise FileNotFoundError(f"skills/registry.yaml not found: {registry}")
    with open(registry, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("skills", [])


def check_parity() -> tuple[list[dict], dict[str, int]]:
    skills = load_skills()
    records = []
    counts = {
        "total": 0, "full_parity": 0, "claude_adapter_missing": 0,
        "agent_skill_adapter_missing": 0, "semantic_drift": 0, "internal_skip": 0,
    }

    for skill in skills:
        name = skill.get("name", "")
        skill_id = skill.get("id", "")
        internal = skill.get("internal", False)
        counts["total"] += 1

        canonical_path = _SKILLS_DIR / f"{name}.md"
        if not canonical_path.exists():
            records.append({
                "capability_id": skill_id, "name": name,
                "parity_status": "CANONICAL_CONTRACT_MISSING",
                "gaps": ["canonical skill file missing"],
            })
            continue

        canonical_body = strip_frontmatter(canonical_path.read_text(encoding="utf-8"))
        canonical_hash = body_hash(canonical_body)
        gaps = []

        # Claude command (skip for internal skills)
        claude_hash = None
        if internal:
            counts["internal_skip"] += 1
        else:
            claude_path = _CLAUDE_COMMANDS / f"{name}.md"
            if not claude_path.exists():
                gaps.append("claude_command_missing")
                counts["claude_adapter_missing"] += 1
            else:
                claude_body = claude_path.read_text(encoding="utf-8")
                claude_hash = body_hash(claude_body)
                if canonical_body.strip() != claude_body.strip():
                    gaps.append("claude_command_semantic_drift")
                    counts["semantic_drift"] += 1

        # Agent skill
        agents_path = _AGENTS_SKILLS / name / "SKILL.md"
        agent_hash = None
        if not agents_path.exists():
            gaps.append("agent_skill_missing")
            counts["agent_skill_adapter_missing"] += 1
        else:
            agent_body = strip_frontmatter(agents_path.read_text(encoding="utf-8"))
            agent_hash = body_hash(agent_body)
            if canonical_body.strip() != agent_body.strip():
                gaps.append("agent_skill_semantic_drift")
                counts["semantic_drift"] += 1

        # KiloCode skill
        kilo_path = _KILO_SKILLS / name / "SKILL.md"
        kilo_hash = None
        if not kilo_path.exists():
            gaps.append("kilo_skill_missing")
        else:
            kilo_body = strip_frontmatter(kilo_path.read_text(encoding="utf-8"))
            kilo_hash = body_hash(kilo_body)

        if gaps:
            status = "SEMANTIC_DRIFT" if any("drift" in g for g in gaps) else "CLAUDE_ADAPTER_MISSING" if "claude_command_missing" in gaps else "AGENT_SKILL_ADAPTER_MISSING"
        else:
            status = "FULL_PARITY"
            counts["full_parity"] += 1

        records.append({
            "capability_id": skill_id,
            "name": name,
            "internal": internal,
            "canonical_hash": canonical_hash,
            "claude_adapter_hash": claude_hash,
            "agent_adapter_hash": agent_hash,
            "kilo_adapter_hash": kilo_hash,
            "parity_status": status,
            "gaps": gaps,
        })

    return records, counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate semantic parity across agent adapter surfaces.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="Diff only; exit 1 if gaps found")
    mode.add_argument("--sync", action="store_true", help="Write parity-report.yaml")
    args = parser.parse_args(argv)

    try:
        records, counts = check_parity()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    gaps_total = counts["claude_adapter_missing"] + counts["agent_skill_adapter_missing"] + counts["semantic_drift"]

    report = {
        "generated_at": datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z"),
        "generator": "tools/capability_sync/validate_semantic_parity.py",
        "summary": {
            "total_capabilities": counts["total"],
            "full_parity": counts["full_parity"],
            "internal_skipped": counts["internal_skip"],
            "claude_adapter_missing": counts["claude_adapter_missing"],
            "agent_skill_adapter_missing": counts["agent_skill_adapter_missing"],
            "semantic_drift": counts["semantic_drift"],
            "gaps_total": gaps_total,
        },
        "final_verdict": "FULL_PARITY" if gaps_total == 0 else "GAPS_DETECTED",
        "capabilities": records,
    }

    if args.sync:
        if _HAS_YAML:
            _PARITY_REPORT.parent.mkdir(parents=True, exist_ok=True)
            with open(_PARITY_REPORT, "w", encoding="utf-8") as f:
                yaml.dump(report, f, default_flow_style=False, allow_unicode=True)
            print(f"Parity report written to {_PARITY_REPORT.relative_to(_REPO_ROOT)}")
        else:
            print("ERROR: pyyaml required to write YAML report", file=sys.stderr)
            return 1

    # Print summary
    print(f"Parity check: {counts['full_parity']}/{counts['total']} at FULL_PARITY")
    if gaps_total > 0:
        print(f"  GAPS: {counts['claude_adapter_missing']} claude missing, "
              f"{counts['agent_skill_adapter_missing']} agent missing, "
              f"{counts['semantic_drift']} semantic drift")
        for r in records:
            if r.get("gaps"):
                print(f"  {r['capability_id']} ({r['name']}): {', '.join(r['gaps'])}")
        if args.check:
            return 1
    else:
        print("PASS: all capabilities at FULL_PARITY")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
