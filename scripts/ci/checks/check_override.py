# Adapted from aspose.org scripts/ci/checks/ for standalone use
"""check_override.py — Verify a forbidden-path write is covered by an active override.

Called by the pre-commit hook for any file that path_guard.py would DENY.
Reads overrides/active-override.json and validates:
  - File exists (an override was declared)
  - Proposed path is within the declared scope
  - Override has not expired

Exit codes:
  0  Override present and covers this path
  1  No override, wrong scope, or expired — commit is blocked

Usage:
  python scripts/ci/checks/check_override.py <proposed-path>
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(os.environ.get("REPO_ROOT", Path(__file__).resolve().parent.parent.parent.parent))
OVERRIDE_FILE = REPO_ROOT / "overrides" / "active-override.json"


def _normalize(path_str: str) -> str:
    p = path_str.replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p


def check_override(proposed_path: str) -> tuple[bool, str]:
    """Return (permitted, message)."""
    normalized = _normalize(proposed_path)

    if not OVERRIDE_FILE.exists():
        return (
            False,
            f"BLOCKED: No active override declared for forbidden path '{normalized}'.\n"
            "  Create overrides/active-override.json per governance docs §4 before committing.\n"
            "  See overrides/schema.json for the required format.",
        )

    try:
        with OVERRIDE_FILE.open("r", encoding="utf-8") as fh:
            override = json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        return (
            False,
            f"BLOCKED: overrides/active-override.json is unreadable or malformed ({exc}).\n"
            "  Fix or remove the file and declare a valid override.",
        )

    # Schema: declared_by must be human
    if override.get("declared_by") != "human":
        return (
            False,
            "BLOCKED: Override 'declared_by' must be 'human'. "
            "Agents cannot self-grant protected-path overrides.",
        )

    # Scope check: proposed path must appear exactly in the scope list
    scope: list[str] = [_normalize(s) for s in override.get("scope", [])]
    if normalized not in scope:
        return (
            False,
            f"BLOCKED: Override scope {scope} does not cover '{normalized}'.\n"
            "  Add the exact path to the 'scope' list in overrides/active-override.json.",
        )

    # Reason must be non-trivial (schema enforces ≥20 chars, double-check here)
    reason = override.get("reason", "")
    if len(reason.strip()) < 20:
        return (
            False,
            "BLOCKED: Override 'reason' is too short. Provide a meaningful justification.",
        )

    # Expiry: only single-use is supported
    expiry = override.get("expiry", "")
    if expiry != "single-use":
        return (
            False,
            f"BLOCKED: Override 'expiry' must be 'single-use'. Got '{expiry}'.",
        )

    return (
        True,
        f"OVERRIDE PERMITTED: '{normalized}' covered by active override.\n"
        f"  Reason: {reason}\n"
        "  Override will be archived after this commit.",
    )


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print("Usage: check_override.py <proposed-path>", file=sys.stderr)
        return 1

    proposed_path = args[0]
    permitted, message = check_override(proposed_path)
    print(message)
    return 0 if permitted else 1


if __name__ == "__main__":
    raise SystemExit(main())
