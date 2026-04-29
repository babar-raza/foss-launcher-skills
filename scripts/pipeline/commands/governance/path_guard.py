"""Deterministic path guard — validates proposed write paths against an allowlist.

Checks whether a given file path is permitted for agent/pipeline writes.
Forbidden governance paths are rejected first, then allowed content prefixes
are checked, and anything else is denied by default.

Usage:
    python scripts/pipeline/commands/governance/path_guard.py <path>
    python scripts/pipeline/commands/governance/path_guard.py --json <path>
    git diff --cached --name-only | python scripts/pipeline/commands/governance/path_guard.py --stdin

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

ALLOWED_PREFIXES: tuple[str, ...] = (
    "content/docs.aspose.org/",
    "content/blog.aspose.org/",
    "content/kb.aspose.org/",
    "content/products.aspose.org/",
    "content/reference.aspose.org/",
    "knowledge/",
    "reports/",
    # Hugo-managed registry data — written by update_product_registry.py.
    "data/",
    # SEO patch manifests — written by scripts/seo/pipeline/report.py.
    "patches/",
    # SEO keyword data — written exclusively by the seo-keyword-refresh CI workflow.
    "keywords/",
    # Pipeline and CI maintenance scripts are allowed for operational maintenance.
    # path_guard.py itself is self-protected via FORBIDDEN_EXACT below.
    "scripts/pipeline/",
    "scripts/ci/",
    # Operator-run one-off mutation scripts (repairs, migrations); see AGENTS.md §4b.
    "scripts/maintenance/",
    # Subsystem packages — self-contained tools with their own package structure.
    "scripts/translator/",
    "scripts/gap-eval/",
    "scripts/generator/",
    "scripts/seo/",
    "tests/",
    # Canonical backlog and plan system — shared across all agents (Kilo, Claude).
    # These are gitignored internal-only directories.
    "backlog/",
    "plans/",
    # Human-authored repo documentation (QUICKSTART.md, OPERATOR_BYPASSES.md, etc.).
    # Agents may write here only when adding operator-visible documentation as part of a
    # registered skill.  Root-level writes are still DENY (no trailing slash match at root).
    "docs/",
)

FORBIDDEN_PREFIXES: tuple[str, ...] = (
    "themes/",
    "layouts/",
    "configs/",
    ".claude/",
    ".agents/",
    ".kilocode/",
    # Kilo-specific workspace prohibition — block custom backlog/plan folders.
    # These would bypass the shared system at backlog/ and plans/.
    ".kilo-backlog/",
    ".kilo-plans/",
    "kilo-backlog/",
    "kilo-plans/",
    "skills/",
    # Governance child-doc protection (governance refactor Phase 0)
    "docs/governance/",
    "docs/workflows/",
    "docs/registries/",
)

FORBIDDEN_EXACT: frozenset[str] = frozenset({
    "AGENTS.md",
    "CODEX.md",
    "CLAUDE.md",
    # Operator bypass documentation — agent-invisible by design.
    "docs/OPERATOR_BYPASSES.md",
    # Self-protection: path_guard.py is its own enforcement oracle.
    # Editing it bypasses all guard checks. Requires explicit override token.
    "scripts/pipeline/commands/governance/path_guard.py",
    # Hook script self-protection (TC-08 / DR-05):
    # These scripts ARE in ALLOWED_PREFIXES (scripts/ci/), so an agent with an
    # active skill context scoped to scripts/ci/* could otherwise modify them.
    # Adding them to FORBIDDEN_EXACT blocks that path — hook governance scripts
    # must not be self-modifiable by agents at runtime.
    "scripts/ci/hooks/check_session_gate.sh",
    "scripts/ci/hooks/bootstrap_session_gate.sh",
    "scripts/ci/hooks/check_content_edit_hook.sh",
    "scripts/ci/hooks/check_content_write_hook.sh",
    "scripts/ci/hooks/check_py_write_hook.sh",
    "scripts/ci/hooks/check_write_path_hook.sh",
    "scripts/ci/hooks/check_skill_context_hook.sh",
    "scripts/ci/hooks/check_venv_bash_hook.sh",
    "scripts/ci/hooks/check_destructive_bash_hook.sh",
    "scripts/ci/hooks/find_python.sh",
    "scripts/ci/hooks/check_venv.sh",
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
