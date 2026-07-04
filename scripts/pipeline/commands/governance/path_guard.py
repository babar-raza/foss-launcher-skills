# Adapted from aspose.org
"""Deterministic path guard -- validates proposed write paths against an allowlist.

Checks whether a given file path is permitted for agent/pipeline writes.
Forbidden governance paths are rejected first, then allowed content prefixes
are checked, and anything else is denied by default.

Usage:
    path_guard.py <path>
    path_guard.py --json <path>
    git diff --cached --name-only | path_guard.py --stdin

Exit codes:
    0  ALLOW - path is in the allowlist (single-path mode)
             - all paths are ALLOW (stdin batch mode)
    2  DENY  - path is forbidden or not in the allowlist (single-path)
             - one or more paths are DENY (stdin batch mode)

Stdin batch mode (--stdin):
    Reads one path per line from stdin.  Prints only DENY paths to stdout
    (one per line).  With --json, prints a JSON array of {path, decision, reason}
    objects for DENY entries only.  Exit code 0 if all paths ALLOW, 2 if any DENY.
    This mode allows the pre-commit hook to check all staged files in a single
    Python invocation instead of one subprocess per file.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# Allowlist / denylist definitions
# ---------------------------------------------------------------------------

# Configurable allowed prefixes -- override for your project content layout.
ALLOWED_PREFIXES: tuple[str, ...] = (
    "content/",
    "knowledge/",
    "reports/",
    "data/",
    "scripts/pipeline/",
    "scripts/ci/",
    "scripts/maintenance/",
    "scripts/generator/",
    "tests/",
    "backlog/",
    "plans/",
    "docs/",
    # Cross-agent governance layer: capability registry, schemas, reports, pilots
    ".governance/",
    # Unified capability sync tooling
    "tools/",
    # Skill contracts and generated adapters (modified under skill context + override token)
    "skills/",
    ".claude/commands/",
    ".agents/skills/",
    ".kilocode/skills/",
    # Root-level scripts (pre-commit hooks, sync scripts not under sub-prefixes)
    "scripts/",
)

# Configurable forbidden prefixes -- override for your project governance layout.
FORBIDDEN_PREFIXES: tuple[str, ...] = (
    "themes/",
    "layouts/",
    "configs/",
    ".claude/",
    ".agents/",
    "docs/governance/",
    "docs/workflows/",
    "docs/registries/",
)

# Configurable forbidden exact paths -- override for your project governance files.
FORBIDDEN_EXACT: frozenset[str] = frozenset({
    "AGENTS.md",
    "CLAUDE.md",
    # Self-protection: path_guard.py is its own enforcement oracle.
    "scripts/pipeline/commands/governance/path_guard.py",
})


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def _normalize(path_str: str) -> str:
    """Normalize a path for comparison: backslashes → forward slashes, strip leading './'."""
    path_str = path_str.replace("\\", "/")
    while path_str.startswith("./"):
        path_str = path_str[2:]
    return path_str


def check_path(path_str: str) -> tuple[str, str]:
    """Return (decision, reason) for a proposed write path.

    decision is ``"ALLOW"`` or ``"DENY"``.
    """
    normalized = _normalize(path_str)

    # Forbidden exact matches
    if normalized in FORBIDDEN_EXACT:
        return ("DENY", f"governance file cannot be modified: {normalized}")

    # Forbidden prefixes
    for prefix in FORBIDDEN_PREFIXES:
        if normalized.startswith(prefix):
            return ("DENY", f"path under forbidden prefix: {prefix}")

    # Allowed prefixes
    for prefix in ALLOWED_PREFIXES:
        if normalized.startswith(prefix):
            return ("ALLOW", f"path under allowed prefix: {prefix}")

    # Default deny
    return ("DENY", "path not in allowlist")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="path_guard",
        description="Deterministic write-path allowlist guard.",
    )
    parser.add_argument(
        "path",
        nargs="?",
        help="Proposed file path to validate (omit when using --stdin)",
    )
    parser.add_argument("--json", action="store_true", help="Machine-readable JSON output")
    parser.add_argument(
        "--stdin",
        action="store_true",
        help=(
            "Batch mode: read one path per line from stdin, print only DENY paths to stdout. "
            "Exit 0 if all ALLOW, 2 if any DENY."
        ),
    )
    args = parser.parse_args(argv)

    if args.stdin:
        # Batch mode: process all paths from stdin in a single Python invocation.
        # Force LF-only output so shell consumers (while read, mapfile) don't
        # receive CR-contaminated paths on Windows text-mode stdout.
        sys.stdout.reconfigure(newline="\n")  # type: ignore[attr-defined]
        denied: list[dict[str, str]] = []
        for line in sys.stdin:
            path_str = line.rstrip("\r\n")
            if not path_str:
                continue
            decision, reason = check_path(path_str)
            if decision == "DENY":
                denied.append({"path": path_str, "decision": decision, "reason": reason})

        if args.json:
            sys.stdout.write(json.dumps(denied, ensure_ascii=False))
            sys.stdout.write("\n")
        else:
            for entry in denied:
                sys.stdout.write(entry["path"] + "\n")

        return 2 if denied else 0

    # Single-path mode (original behaviour)
    if not args.path:
        parser.error("path argument is required unless --stdin is used")

    decision, reason = check_path(args.path)

    if args.json:
        payload = {"path": args.path, "decision": decision, "reason": reason}
        sys.stdout.write(json.dumps(payload, indent=2, ensure_ascii=False))
        sys.stdout.write("\n")
    else:
        print(f"{decision}: {reason}")

    return 0 if decision == "ALLOW" else 2


if __name__ == "__main__":
    raise SystemExit(main())
