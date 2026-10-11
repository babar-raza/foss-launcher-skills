"""checkout_sync (CLI) — scoped, clean-verified real-index/worktree sync after
a ref advance, plus the read-only residue report (2026-08-29 stale-guard plan,
T11 / TC-SG-03).

Backs the manual plumbing and object-level-merge recipes in CLAUDE.md: after
`git push <sha>:refs/heads/main` + `git update-ref refs/heads/main <sha>`, run

    python scripts/pipeline/commands/ops/checkout_sync.py sync \
        --old <pre-advance HEAD> --new <sha> [--paths <exact files...>]

so the real index stops holding the pre-commit blobs (which the next porcelain
`git commit` from ANY session would otherwise sweep into history as byte-exact
silent reverts — the MT018 / 2026-08-07 incident class). `git_plumb_commit.py`
calls the library form of this automatically after every commit it builds.

    python scripts/pipeline/commands/ops/checkout_sync.py report

lists the residue entries currently in the real index (read-only; printed by
/session-start so a session sees the traps before committing anything).

Exit codes: 0 ok (including nothing to do); 1 sync aborted on a held
index.lock or git errors (details printed); 2 usage.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

from lib import checkout_sync as _lib  # noqa: E402


def main(argv: "list[str] | None" = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(prog="checkout_sync", description=__doc__)
    parser.add_argument("--repo-root", default=None,
                        help="Repo root (default: this checkout)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_sync = sub.add_parser("sync", help="Sync index (and optionally worktree) after a ref advance")
    p_sync.add_argument("--old", required=True, help="Pre-advance HEAD sha")
    p_sync.add_argument("--new", required=True, help="Post-advance sha (usually the new HEAD)")
    p_sync.add_argument("--paths", nargs="*", default=None,
                        help="Exact paths to consider (default: every path that differs "
                             "between --old and --new)")
    p_sync.add_argument("--paths-from", default=None,
                        help="Read paths (one per line) from FILE; merged with --paths")
    p_sync.add_argument("--mode", choices=["index", "index+worktree"], default="index",
                        help="index: fix index residue only (worktree untouched). "
                             "index+worktree: also restore worktree content for paths "
                             "whose on-disk bytes provably equal the pre-advance state "
                             "(the remote-advance / reconcile case).")

    p_report = sub.add_parser("report", help="List real-index residue entries (read-only)")
    p_report.add_argument("--max", type=int, default=200)

    args = parser.parse_args(argv)
    repo_root = Path(args.repo_root) if args.repo_root else None

    if args.command == "report":
        rows = _lib.residue_report(repo_root=repo_root, max_entries=args.max)
        if not rows:
            print("checkout_sync report: no index residue found.")
            return 0
        print(f"checkout_sync report: {len(rows)} real-index entr{'y' if len(rows) == 1 else 'ies'} "
              f"hold pre-commit content -- the next porcelain `git commit` would revert:")
        for row in rows:
            print(f"  {row['path']}  (would revert {row['reverts_commit'][:10]})")
        print("Remedy: checkout_sync.py sync --old <that commit>^ --new HEAD --paths <path...>  "
              "or git restore --staged -- <path...>")
        return 0

    paths = list(args.paths) if args.paths else None
    if args.paths_from:
        try:
            extra = Path(args.paths_from).read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            print(f"ERROR: cannot read --paths-from '{args.paths_from}': {exc}", file=sys.stderr)
            return 2
        paths = (paths or []) + [p.strip() for p in extra if p.strip()]

    report = _lib.sync_after_ref_advance(
        args.old, args.new, paths=paths, repo_root=repo_root, mode=args.mode,
    )
    print(report.summary())
    for skipped in report.skipped_dirty:
        print(f"  left untouched (not provably pre-advance state): {skipped}")
    if report.index_locked or report.errors:
        for err in report.errors:
            print(f"  error: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
