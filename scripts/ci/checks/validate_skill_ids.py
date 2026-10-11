"""validate_skill_ids.py — Verify that skill IDs exist in the canonical registry.

Called by the commit-msg hook and CI workflow to validate "Skills invoked:" declarations.

Usage:
  python scripts/ci/checks/validate_skill_ids.py S-01 S-23 S-48
  echo "Skills invoked: [S-01, S-48]" | python scripts/ci/checks/validate_skill_ids.py --stdin

Exit codes:
  0  All IDs are valid (or no IDs provided)
  1  One or more IDs are not in the canonical registry

TC-CIR-08 (2026-08-14, CI reliability reassessment, Root Cause E): previously parsed
AGENTS.md §12 / docs/registries/skills.md prose via regex — a SECOND source of truth,
independent of skills/registry.json (the machine-generated canonical registry
check_commit_skill_provenance.py already validates against, and
check_skill_registry_json.py already keeps current — see pre-commit Step 25b). Two
sources of truth for "is this a valid skill ID" meant a skill ID could pass this
check and content-audit.yml's re-derivation of it, yet fail skill-governance.yml's
check_commit_skill_provenance.py, or vice versa, whenever the two drifted. Now reads
skills/registry.json directly, matching check_commit_skill_provenance.py exactly.
Falls back to the old markdown-table parse only if registry.json is missing
(bootstrap/fresh-clone-before-first-sync scenario) — fail-open is preserved, not the
prose-parsing as a co-equal source.
"""
from __future__ import annotations

import json
import logging
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
REGISTRY_JSON = REPO_ROOT / "skills" / "registry.json"
AGENTS_MD = REPO_ROOT / "AGENTS.md"
SKILLS_CHILD_DOC = REPO_ROOT / "docs" / "registries" / "skills.md"

# Regex to extract skill registry rows: | skill-name | S-nn | description |
# (fallback path only — see load_registry())
_ROW_RE = re.compile(r"^\|\s*[\w\-]+\s*\|\s*(S-\d+)\s*\|", re.MULTILINE)
# Regex to extract S-nn patterns from arbitrary text.
# Word boundaries prevent matching "S-NNN" substrings inside backlog IDs
# like NOTE-PYTHON-REF-DRAFTS-001 (where "S-001" appears as a substring).
# re.IGNORECASE is intentionally removed — skill IDs are always uppercase S-.
_ID_RE = re.compile(r"\bS-\d+\b")


def _load_from_registry_json() -> frozenset[str] | None:
    """Canonical source: skills/registry.json (same file check_commit_skill_provenance.py
    reads). Returns None (not an empty set) on any failure, so the caller can fall back
    without silently treating a parse error as "zero valid skills"."""
    try:
        data = json.loads(REGISTRY_JSON.read_text(encoding="utf-8"))
        return frozenset(s["id"].upper() for s in data["skills"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def load_registry() -> frozenset[str]:
    """Canonical: skills/registry.json. Fallback (registry.json missing/unparseable
    only — a fresh clone before the first sync_providers.py run): parse §12 skill
    table from the child doc, then AGENTS.md."""
    from_json = _load_from_registry_json()
    if from_json is not None:
        return from_json
    logging.warning("FALLBACK: skills/registry.json missing or unparseable — "
                     "reading Skills reference from markdown prose instead")
    if SKILLS_CHILD_DOC.exists():
        text = SKILLS_CHILD_DOC.read_text(encoding="utf-8")
    elif AGENTS_MD.exists():
        text = AGENTS_MD.read_text(encoding="utf-8")
    else:
        return frozenset()
    return frozenset(m.group(1).upper() for m in _ROW_RE.finditer(text))


def validate_ids(ids: list[str], registry: frozenset[str]) -> list[str]:
    """Return list of IDs that are not in the registry."""
    return [id_.upper() for id_ in ids if id_.upper() not in registry]


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]

    if "--stdin" in args:
        text = sys.stdin.read()
        ids = _ID_RE.findall(text)
    else:
        ids = [a for a in args if _ID_RE.fullmatch(a.upper())]

    if not ids:
        print("No skill IDs to validate.")
        return 0

    registry = load_registry()
    if not registry:
        print("WARNING: Could not load skill registry (skills/registry.json or AGENTS.md) — "
              "skipping ID validation.", file=sys.stderr)
        return 0  # Fail open if no registry source is available (bootstrap scenarios)

    unknown = validate_ids(ids, registry)
    if unknown:
        print(f"BLOCKED: Unknown skill ID(s) in 'Skills invoked:' declaration: {unknown}")
        print(f"  Valid IDs per skills/registry.json: {sorted(registry)}")
        print("  Fix: use only IDs listed in skills/registry.json (regenerate via "
              "scripts/pipeline/commands/ops/sync_providers.py if it's stale).")
        return 1

    print(f"Skill IDs validated OK: {sorted(set(id_.upper() for id_ in ids))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
