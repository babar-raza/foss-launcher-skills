"""check_commit_skill_provenance.py — CI check for skill provenance in content commits.

Validates that commits touching content files include a valid "Skills invoked:"
field with skill IDs that exist in the canonical registry (skills/registry.json).

Usage:
  # Check commits in current PR branch vs main
  python scripts/ci/checks/check_commit_skill_provenance.py

  # Check specific commit range
  python scripts/ci/checks/check_commit_skill_provenance.py --range main..HEAD

  # Check a single commit
  python scripts/ci/checks/check_commit_skill_provenance.py --commit abc123

Exit codes:
  0  All content commits have valid skill provenance
  1  One or more content commits lack valid skill provenance
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_REGISTRY = _REPO_ROOT / "skills" / "registry.json"
_SKILL_ID_RE = re.compile(r"S-\d+")
_SKILLS_INVOKED_RE = re.compile(r"[Ss]kills?\s*[Ii]nvoked", re.IGNORECASE)


def _load_valid_ids() -> set[str]:
    """Load valid skill IDs from registry.json."""
    if not _REGISTRY.exists():
        print(f"WARNING: Registry not found at {_REGISTRY}", file=sys.stderr)
        return set()
    with open(_REGISTRY, encoding="utf-8") as f:
        data = json.load(f)
    return {s["id"] for s in data.get("skills", []) if "id" in s}


def _get_commits(commit_range: str) -> list[str]:
    """Get commit SHAs in a range."""
    result = subprocess.run(
        ["git", "log", "--format=%H", commit_range],
        capture_output=True, text=True, cwd=_REPO_ROOT,
    )
    if result.returncode != 0:
        return []
    return [sha.strip() for sha in result.stdout.strip().split("\n") if sha.strip()]


def _commit_touches_content(sha: str) -> bool:
    """Check if a commit touches content files."""
    result = subprocess.run(
        ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", sha],
        capture_output=True, text=True, cwd=_REPO_ROOT,
    )
    if result.returncode != 0:
        return False
    return any(
        line.startswith("content/") and line.endswith(".md")
        for line in result.stdout.strip().split("\n")
    )


def _get_commit_message(sha: str) -> str:
    result = subprocess.run(
        ["git", "log", "-1", "--format=%B", sha],
        capture_output=True, text=True, cwd=_REPO_ROOT,
    )
    return result.stdout if result.returncode == 0 else ""


def _validate_commit(sha: str, valid_ids: set[str]) -> list[str]:
    """Validate a single commit. Returns list of errors (empty = pass)."""
    errors = []
    msg = _get_commit_message(sha)

    if not _SKILLS_INVOKED_RE.search(msg):
        errors.append(f"Missing 'Skills invoked:' field")
        return errors

    # Extract skill IDs from the Skills invoked line
    for line in msg.split("\n"):
        if _SKILLS_INVOKED_RE.search(line):
            ids = _SKILL_ID_RE.findall(line)
            if not ids:
                errors.append(f"'Skills invoked:' field contains no valid S-XX IDs")
            for sid in ids:
                if sid not in valid_ids:
                    errors.append(f"Unknown skill ID: {sid}")
            break

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate skill provenance in content commits.",
    )
    parser.add_argument("--range", default="",
                        help="Git commit range to check (e.g. main..HEAD)")
    parser.add_argument("--commit", default="",
                        help="Single commit SHA to check")
    args = parser.parse_args(argv)

    valid_ids = _load_valid_ids()
    if not valid_ids:
        print("ERROR: Could not load skill registry.", file=sys.stderr)
        return 1

    if args.commit:
        shas = [args.commit]
    elif args.range:
        shas = _get_commits(args.range)
    else:
        # Default: check PR range (main..HEAD)
        shas = _get_commits("main..HEAD")

    if not shas:
        print("No commits to check.")
        return 0

    failures = []
    checked = 0
    for sha in shas:
        if not _commit_touches_content(sha):
            continue
        checked += 1
        errors = _validate_commit(sha, valid_ids)
        if errors:
            short_sha = sha[:12]
            msg_first_line = _get_commit_message(sha).split("\n")[0][:60]
            failures.append((short_sha, msg_first_line, errors))

    print(f"Checked {checked} content commits out of {len(shas)} total.")

    if not failures:
        print("PASS: All content commits have valid skill provenance.")
        return 0

    print(f"\nFAIL: {len(failures)} content commit(s) lack valid skill provenance:\n")
    for short_sha, msg, errors in failures:
        print(f"  {short_sha} — {msg}")
        for err in errors:
            print(f"    - {err}")
    print()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
