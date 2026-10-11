"""check_git_tracking_policy.py — pre-commit gate for .gitignore/policy drift.

CONTRACT: scripts/ci/checks/check_git_tracking_policy.py
  purpose: block a commit that leaves .gitignore's managed
           "# BEGIN/END GIT-TRACKING-POLICY" block out of sync with
           scripts/pipeline/config/git_tracking_policy.yaml (or with the family
           registry that policy resolves against, data/blog_family_routes.yaml).
  root cause this closes: the negation-chain block in .gitignore is generated,
           not hand-authored (see git_tracking_policy_sync.py's own module
           docstring for why); a commit that hand-edits .gitignore inside the
           marked region, or that adds/removes a family in
           data/blog_family_routes.yaml without re-running --fix, would
           otherwise land silently out of sync with the policy that is
           supposed to be authoritative for that block.
  scope: only runs when a relevant file is actually staged — never blocks an
         unrelated commit (same design as check_skill_mirror_parity.py).
  usage:
    python scripts/ci/checks/check_git_tracking_policy.py --staged-files <path> [<path> ...]
    Exit 0: no relevant file staged, or --check reports clean.
    Exit 1: --check found drift — prints the diff and the fix command.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PYTHON = sys.executable

_RELEVANT_PATHS = {
    ".gitignore",
    "scripts/pipeline/config/git_tracking_policy.yaml",
    "data/blog_family_routes.yaml",
}

_SYNC_SCRIPT = _REPO_ROOT / "scripts" / "pipeline" / "commands" / "ops" / "git_tracking_policy_sync.py"


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--staged-files", nargs="*", default=[],
                         help="Staged file paths (from git diff --cached --name-only)")
    args = parser.parse_args(argv)

    staged = {p.replace("\\", "/") for p in args.staged_files}
    if not (staged & _RELEVANT_PATHS):
        print("[git-tracking-policy] No relevant file staged — skipping.")
        return 0

    result = subprocess.run(
        [_PYTHON, str(_SYNC_SCRIPT), "--check"],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.stdout:
        print(result.stdout, end="")
    if result.returncode != 0:
        if result.stderr:
            print(result.stderr, end="", file=sys.stderr)
        print(
            "[git-tracking-policy] BLOCKED — .gitignore's managed block is out of "
            "sync with scripts/pipeline/config/git_tracking_policy.yaml.",
            file=sys.stderr,
        )
        return 1

    print("[git-tracking-policy] PASS — .gitignore matches policy.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
