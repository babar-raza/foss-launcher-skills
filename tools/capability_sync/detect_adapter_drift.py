"""detect_adapter_drift.py — Detect stale generated adapters by content hash comparison.

Computes the SHA-256 hash of each canonical skill body and compares it to the deployed
adapter (after stripping frontmatter for .claude/commands/ comparison). Reports adapters
whose content has drifted from the canonical source.

Emits .governance/generated/drift-report.yaml.

Usage:
    python tools/capability_sync/detect_adapter_drift.py --check   # exit 1 if drift
    python tools/capability_sync/detect_adapter_drift.py --sync    # write drift-report.yaml
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
_DRIFT_REPORT = _REPO_ROOT / ".governance" / "generated" / "drift-report.yaml"

_FRONTMATTER_RE = re.compile(r"^---\n.*?\n---\n?", re.DOTALL)


def strip_frontmatter(text: str) -> str:
    stripped = _FRONTMATTER_RE.sub("", text, count=1)
    return stripped.lstrip("\n")


def sha256_short(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def load_skills() -> list[dict[str, Any]]:
    if not _HAS_YAML:
        raise RuntimeError("pyyaml required: pip install pyyaml")
    registry = _SKILLS_DIR / "registry.yaml"
    if not registry.exists():
        raise FileNotFoundError(f"skills/registry.yaml not found")
    with open(registry, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("skills", [])


def detect_drift() -> tuple[list[dict], int]:
    skills = load_skills()
    drift_entries = []
    total_adapters = 0

    for skill in skills:
        name = skill.get("name", "")
        skill_id = skill.get("id", "")
        internal = skill.get("internal", False)

        canonical_path = _SKILLS_DIR / f"{name}.md"
        if not canonical_path.exists():
            continue

        canonical_text = canonical_path.read_text(encoding="utf-8")
        canonical_body = strip_frontmatter(canonical_text)
        canonical_hash = sha256_short(canonical_body)

        # Check Claude command adapter (frontmatter stripped)
        if not internal:
            claude_path = _CLAUDE_COMMANDS / f"{name}.md"
            if claude_path.exists():
                total_adapters += 1
                claude_body = claude_path.read_text(encoding="utf-8")
                claude_hash = sha256_short(claude_body)
                if canonical_body.strip() != claude_body.strip():
                    drift_entries.append({
                        "capability_id": skill_id,
                        "name": name,
                        "adapter_type": "CLAUDE_COMMAND",
                        "adapter_path": str(claude_path.relative_to(_REPO_ROOT)),
                        "canonical_hash": canonical_hash,
                        "adapter_hash": claude_hash,
                        "drift_detected": True,
                    })

        # Check agent skill adapter (frontmatter stripped for comparison)
        for skill_dir, adapter_label in [(_AGENTS_SKILLS, "CODEX_SKILL"), (_KILO_SKILLS, "KILO_SKILL")]:
            skill_path = skill_dir / name / "SKILL.md"
            if skill_path.exists():
                total_adapters += 1
                skill_text = skill_path.read_text(encoding="utf-8")
                skill_body = strip_frontmatter(skill_text)
                skill_hash = sha256_short(skill_body)
                if canonical_body.strip() != skill_body.strip():
                    drift_entries.append({
                        "capability_id": skill_id,
                        "name": name,
                        "adapter_type": adapter_label,
                        "adapter_path": str(skill_path.relative_to(_REPO_ROOT)),
                        "canonical_hash": canonical_hash,
                        "adapter_hash": skill_hash,
                        "drift_detected": True,
                    })

    return drift_entries, total_adapters


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Detect stale generated adapters.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="Diff only; exit 1 if drift detected")
    mode.add_argument("--sync", action="store_true", help="Write drift-report.yaml")
    args = parser.parse_args(argv)

    try:
        drift_entries, total_adapters = detect_drift()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    report = {
        "generated_at": datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z"),
        "generator": "tools/capability_sync/detect_adapter_drift.py",
        "summary": {
            "total_adapters_checked": total_adapters,
            "drift_detected_count": len(drift_entries),
            "verdict": "NO_DRIFT" if not drift_entries else "DRIFT_DETECTED",
        },
        "drift_entries": drift_entries,
    }

    if args.sync and _HAS_YAML:
        _DRIFT_REPORT.parent.mkdir(parents=True, exist_ok=True)
        with open(_DRIFT_REPORT, "w", encoding="utf-8") as f:
            yaml.dump(report, f, default_flow_style=False, allow_unicode=True)
        print(f"Drift report written to {_DRIFT_REPORT.relative_to(_REPO_ROOT)}")

    if drift_entries:
        print(f"DRIFT: {len(drift_entries)} adapter(s) out of sync with canonical source:")
        for entry in drift_entries:
            print(f"  [{entry['adapter_type']}] {entry['name']} — {entry['adapter_path']}")
            print(f"    canonical: {entry['canonical_hash']}  adapter: {entry['adapter_hash']}")
        print("\nFix: run 'python tools/capability_sync/run_sync.py' to regenerate adapters.")
        if args.check:
            return 1
    else:
        print(f"PASS: all {total_adapters} adapters are in sync with canonical source")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
