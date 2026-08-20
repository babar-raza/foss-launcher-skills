#!/usr/bin/env python3
"""check_precommit_audit_mutation_safety.py — best-effort static guard over
scripts/pre-commit-audit.sh's real-state-mutation safety contract.

CONTRACT: scripts/ci/checks/check_precommit_audit_mutation_safety.py
  purpose: 2026-08-20 production assessment
    (reports/skill-gaps/2026-08-20-git-plumb-commit-tier1-mutation-safety.md)
    found that pre-commit-audit.sh has exactly two steps capable of mutating
    real repo state when run as git_plumb_commit.py's Tier-1 parity check
    (against an isolated temp index) rather than as the real interactive
    commit hook it was written for: Step 10 (git restore/checkout against the
    real working tree) and Step 5 (a plain, non-git Python file write). Both
    are now gated behind the PC_AUDIT_NO_MUTATE env var. This script has TWO
    jobs, of different strength:
      1. REQUIRED (hard fail): every step registered in
         precommit_audit_mutation_registry.yaml must still have its declared
         guard present in its own block of the real script -- catches a
         guard being silently removed or the step being renamed.
      2. ADVISORY (never fails the run): a best-effort scan for common
         mutation signatures (git verbs that write, and known write-enabling
         CLI flags) OUTSIDE any registered step's block -- flags a
         plausible-looking new mutation for a human to register or dismiss.
         This is deliberately non-blocking: a script that shells out to
         arbitrary Python cannot be proven mutation-free by grepping its
         text, and a hard-blocking false positive on unrelated commits would
         be worse than an occasional missed advisory. The AUTHORITATIVE
         control for real (not just plausible-looking) mutations is
         git_plumb_commit.py's own runtime postcondition, which is
         mechanism-agnostic and does not depend on this script at all.
  inputs: scripts/pre-commit-audit.sh (default) or --script <path>,
    scripts/ci/checks/precommit_audit_mutation_registry.yaml (default) or
    --registry <path>.
  outputs: exit 0 if every registered guard is present (advisory findings
    printed but do not affect exit code); exit 1 if any registered guard is
    missing.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

_HERE = Path(__file__).resolve().parent
_DEFAULT_SCRIPT = _HERE.parents[1] / "pre-commit-audit.sh"
_DEFAULT_REGISTRY = _HERE / "precommit_audit_mutation_registry.yaml"

_STEP_START_RE = re.compile(r'_pc_step_start\s+"([^"]+)"')

# Verbs/flags that plausibly indicate a step writes to real state. Advisory
# only -- see module docstring for why this can never be exhaustive.
_MUTATION_SIGNATURE_RE = re.compile(
    r"\bgit\s+(add|commit|checkout|restore|reset|rm|stash|update-index|clean)\b"
    r"|--apply\b|--auto-stage\b|--fix\b|--write\b"
)


def _load_registry(path: Path) -> list[dict]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data.get("steps", [])


def _step_blocks(script_text: str) -> "list[tuple[str, str]]":
    """Split the script into (step_name, block_text) pairs, one per
    _pc_step_start marker, each block running to the next marker (or EOF for
    the last one). Text before the first marker is not a step and is
    dropped."""
    markers = list(_STEP_START_RE.finditer(script_text))
    blocks = []
    for i, m in enumerate(markers):
        start = m.start()
        end = markers[i + 1].start() if i + 1 < len(markers) else len(script_text)
        blocks.append((m.group(1), script_text[start:end]))
    return blocks


def check(script_path: Path, registry_path: Path) -> "tuple[bool, list[str]]":
    """Returns (ok, messages). ok=False only on a missing REQUIRED guard;
    messages includes both required-check results and advisory findings."""
    script_text = script_path.read_text(encoding="utf-8")
    registry = _load_registry(registry_path)
    blocks = dict(_step_blocks(script_text))
    registered_names = {entry["name"] for entry in registry}

    messages: list[str] = []
    ok = True

    for entry in registry:
        name = entry["name"]
        guard = entry["guard"]
        block = blocks.get(name)
        if block is None:
            ok = False
            messages.append(
                f"REQUIRED FAIL: registered step \"{name}\" not found in "
                f"{script_path} (renamed or removed? update the registry or "
                f"restore the step)"
            )
            continue
        if guard not in block:
            ok = False
            messages.append(
                f"REQUIRED FAIL: step \"{name}\" no longer contains its "
                f"registered guard \"{guard}\" -- a mutation this registry "
                f"says is gated may now be unconditional"
            )

    for name, block in blocks.items():
        if name in registered_names:
            continue
        if _MUTATION_SIGNATURE_RE.search(block):
            messages.append(
                f"ADVISORY: step \"{name}\" contains a possible mutation "
                f"signature and is not in {registry_path.name} -- register it "
                f"(with its guard) if it can write to real repo state when "
                f"run in Tier-1 check-only mode, or ignore if it's a false "
                f"positive (e.g. a read-only `git diff`/`git show`)."
            )

    return ok, messages


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--script", type=Path, default=_DEFAULT_SCRIPT)
    parser.add_argument("--registry", type=Path, default=_DEFAULT_REGISTRY)
    args = parser.parse_args(argv)

    if not args.script.exists():
        print(f"ERROR: script not found: {args.script}", file=sys.stderr)
        return 2
    if not args.registry.exists():
        print(f"ERROR: registry not found: {args.registry}", file=sys.stderr)
        return 2

    ok, messages = check(args.script, args.registry)
    for msg in messages:
        print(msg)

    if not ok:
        print("\ncheck_precommit_audit_mutation_safety: FAIL", file=sys.stderr)
        return 1
    print("check_precommit_audit_mutation_safety: PASS (required guards intact)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
