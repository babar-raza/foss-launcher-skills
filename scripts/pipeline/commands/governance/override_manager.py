"""Override manager — lifecycle management for forbidden-path write override tokens.

An override token is a structured JSON artifact that records human-approved intent to
write to a path that path_guard.py would otherwise DENY. The token is written to
reports/overrides/pending/ (local only — never staged or committed). The pre-commit
hook reads the token from disk and validates it before allowing the commit.

reports/ is a strict local-only artifact boundary. Do not use 'git add -f' to stage
tokens. The post-commit hook moves consumed tokens to archived/ automatically.

Token lifecycle:
  pending/  → token created on disk, not yet consumed
  archived/ → token consumed (linked to a commit SHA, still local only)

Usage examples:
  # Create a new pending override token
  python scripts/pipeline/commands/governance/override_manager.py create \\
    --paths AGENTS.md --reason "Add grading rules per plan lovely-wandering-reef.md" \\
    --plan lovely-wandering-reef.md

  # Validate that a pending token exists and covers a path
  python scripts/pipeline/commands/governance/override_manager.py validate-for-path AGENTS.md

  # Consume (archive) a token after its commit
  python scripts/pipeline/commands/governance/override_manager.py consume \\
    --token-id 20260331-142300-agents-md-grading-system --commit-sha abc123

  # List all pending tokens
  python scripts/pipeline/commands/governance/override_manager.py list-pending

  # Audit all consumed tokens
  python scripts/pipeline/commands/governance/override_manager.py audit

Exit codes:
  0  success / valid
  1  failure / invalid
  2  token not found or path not covered
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent  # commands/governance/ -> commands/ -> pipeline/ -> scripts/ -> repo
_DEFAULT_PENDING_DIR = _DEFAULT_REPO_ROOT / "reports" / "overrides" / "pending"
_DEFAULT_ARCHIVED_DIR = _DEFAULT_REPO_ROOT / "reports" / "overrides" / "archived"

_REPO_ROOT = _DEFAULT_REPO_ROOT
_PENDING_DIR = _DEFAULT_PENDING_DIR
_ARCHIVED_DIR = _DEFAULT_ARCHIVED_DIR
_TOKEN_TTL_DAYS = 7  # tokens expire after 7 days if not consumed


def configure(
    *,
    repo_root: "Path | str | None" = None,
    pending_dir: "Path | str | None" = None,
    archived_dir: "Path | str | None" = None,
) -> None:
    """Override module-level path constants for testing."""
    global _REPO_ROOT, _PENDING_DIR, _ARCHIVED_DIR
    if repo_root is None and pending_dir is None and archived_dir is None:
        _REPO_ROOT = _DEFAULT_REPO_ROOT
        _PENDING_DIR = _DEFAULT_PENDING_DIR
        _ARCHIVED_DIR = _DEFAULT_ARCHIVED_DIR
        return
    if repo_root is not None:
        _REPO_ROOT = Path(repo_root)
        _PENDING_DIR = _REPO_ROOT / "reports" / "overrides" / "pending"
        _ARCHIVED_DIR = _REPO_ROOT / "reports" / "overrides" / "archived"
    if pending_dir is not None:
        _PENDING_DIR = Path(pending_dir)
    if archived_dir is not None:
        _ARCHIVED_DIR = Path(archived_dir)


# ---------------------------------------------------------------------------
# Token I/O helpers
# ---------------------------------------------------------------------------

def _load_token(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save_token(path: Path, token: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(token, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _normalize(p: str) -> str:
    """Normalize a path for token storage/comparison: backslashes to forward
    slashes, and strip a leading './' prefix (repeated, for './/foo' etc).

    NOT `.lstrip("./")` (found live, production concurrency redesign,
    2026-08-01, Step 6): `str.lstrip` strips a CHARACTER SET, not a prefix
    string -- for a path like '.supervisor/prompts/x.md', it silently ate
    the leading '.' too (stopping only once it hit 's', the first character
    not in {'.', '/'}), producing 'supervisor/prompts/x.md'. Harmless for a
    single self-consistent create+validate pair (both sides normalize the
    same way), but corrupts the STORED path for every dotdir this repo
    actually protects (.supervisor/, .claude/, .agents/, .kilocode/), and a
    human reading the token file sees the wrong path entirely.
    """
    p = p.replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p


def _slug_from_paths(paths: list[str]) -> str:
    first = _normalize(paths[0]).replace("/", "-").replace(".", "-")
    return first[:40]


def _token_filename(token_id: str) -> str:
    return f"{token_id}.json"


def _is_expired(token: dict) -> bool:
    authorized_at = token.get("authorized_at", "")
    if not authorized_at:
        return False
    try:
        ts = datetime.fromisoformat(authorized_at.replace("Z", "+00:00"))
        return datetime.now(tz=timezone.utc) - ts > timedelta(days=_TOKEN_TTL_DAYS)
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_create(args: argparse.Namespace) -> int:
    """Create a new pending override token."""
    now = datetime.now(tz=timezone.utc)
    ts = now.strftime("%Y%m%d-%H%M%S")
    slug = _slug_from_paths(args.paths)
    token_id = f"{ts}-{slug}"

    token = {
        "override_id": token_id,
        "paths": [_normalize(p) for p in args.paths],
        "operation": args.operation,
        "reason": args.reason,
        "plan_reference": args.plan or "",
        "scope_description": args.scope or "",
        "authorized_at": now.isoformat().replace("+00:00", "Z"),
        "retroactive": args.retroactive,
        "consumed_by_commit": None,
    }

    out_path = _PENDING_DIR / _token_filename(token_id)
    _save_token(out_path, token)
    print(f"Created override token: {token_id}")
    print(f"  File: {out_path.relative_to(_REPO_ROOT)}")
    print(f"  Paths: {', '.join(token['paths'])}")
    print(f"  Do NOT stage or commit this file -- reports/ is gitignored by design.")
    print(f"  pre-commit-audit.sh reads it directly off local disk to authorize the")
    print(f"  forbidden-path edit; consume it with 'consume --token-id {token_id} \\")
    print(f"  --commit-sha <sha>' after the commit.")
    return 0


def find_valid_token_for_path(path: str) -> "dict | None":
    """Return the first valid (non-expired, non-consumed) pending token that
    covers path, or None. Pure function, no I/O side effects beyond reading
    reports/overrides/pending/ -- importable directly by any Python caller
    that needs an override decision without shelling out to this module's
    own CLI (e.g. git_plumb_commit.py, production concurrency redesign,
    2026-08-01, Step 8 follow-up).

    Note: an EXPIRED token that covers the path is deliberately NOT treated
    as "no token at all" -- it's a distinct, more actionable outcome (the
    caller should recreate the token, not assume no override was ever
    intended). Callers that only care about the boolean "am I covered"
    question should check `is_expired=False` alongside a non-None return.
    """
    _PENDING_DIR.mkdir(parents=True, exist_ok=True)
    target = _normalize(path)

    for token_file in sorted(_PENDING_DIR.glob("*.json")):
        try:
            token = _load_token(token_file)
        except (json.JSONDecodeError, OSError):
            continue

        covered = any(target == p or target.startswith(p.rstrip("/") + "/")
                      for p in token.get("paths", []))
        if not covered:
            continue

        if _is_expired(token) and not token.get("retroactive", False):
            continue  # expired and not retroactive -- does not count as valid coverage

        return token

    return None


def cmd_validate_for_path(args: argparse.Namespace) -> int:
    """Check that a valid (non-expired, non-consumed) pending token covers the given path."""
    target = _normalize(args.path)
    token = find_valid_token_for_path(target)

    if token is not None:
        print(f"VALID: token {token['override_id']} covers path '{target}'")
        return 0

    # Distinguish "covered but expired" from "never covered" for a clearer message
    # -- find_valid_token_for_path already filtered expired-non-retroactive tokens
    # out, so re-scan once more here purely for the diagnostic message.
    _PENDING_DIR.mkdir(parents=True, exist_ok=True)
    for token_file in sorted(_PENDING_DIR.glob("*.json")):
        try:
            candidate = _load_token(token_file)
        except (json.JSONDecodeError, OSError):
            continue
        covered = any(target == p or target.startswith(p.rstrip("/") + "/")
                      for p in candidate.get("paths", []))
        if covered and _is_expired(candidate) and not candidate.get("retroactive", False):
            print(f"EXPIRED: token {candidate['override_id']} is older than {_TOKEN_TTL_DAYS} days",
                  file=sys.stderr)
            return 2

    print(f"NO VALID TOKEN: no pending override token covers path '{target}'", file=sys.stderr)
    return 2


def consume_token(token_id: str, commit_sha: str) -> bool:
    """Importable single-token consume: move pending -> archived, stamp the
    commit SHA. Returns False if the token is not pending. Extracted from
    cmd_consume (2026-08-29 stale-guard plan) so git_plumb_commit.py and
    consume_for_commit() can consume by exact id instead of shelling out or
    sweeping."""
    pending_path = _PENDING_DIR / _token_filename(token_id)
    if not pending_path.exists():
        return False

    token = _load_token(pending_path)
    token["consumed_by_commit"] = commit_sha
    token["consumed_at"] = datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z")

    _ARCHIVED_DIR.mkdir(parents=True, exist_ok=True)
    _save_token(_ARCHIVED_DIR / _token_filename(token_id), token)
    pending_path.unlink()
    return True


def cmd_consume(args: argparse.Namespace) -> int:
    """Move a pending token to archived and record the commit SHA."""
    if not consume_token(args.token_id, args.commit_sha):
        print(f"ERROR: token {args.token_id} not found in pending/", file=sys.stderr)
        return 1
    print(f"Consumed token {args.token_id} -> archived, linked to commit {args.commit_sha}")
    return 0


def _token_covers_any(token: dict, changed_paths: "list[str]") -> bool:
    """Same prefix-directory coverage semantics as find_valid_token_for_path,
    evaluated against a commit's changed-path list."""
    token_paths = [_normalize(p) for p in token.get("paths", [])]
    for changed in changed_paths:
        c = _normalize(changed)
        for t in token_paths:
            if c == t or c.startswith(t.rstrip("/") + "/"):
                return True
    return False


def consume_for_commit(commit_sha: str, changed_paths: "list[str]") -> "tuple[list[str], list[str]]":
    """Consume ONLY the pending tokens whose paths intersect changed_paths.

    2026-08-29 stale-guard plan (T8): the post-commit hook previously consumed
    EVERY pending token on ANY successful commit -- sampled live: 3 of the 40
    most recently archived tokens were attributed to commits that never
    touched their paths, and a concurrent session's still-needed token could
    be swept out from under its pending commit. Returns (consumed_ids,
    skipped_ids); never raises for a malformed token file."""
    consumed: "list[str]" = []
    skipped: "list[str]" = []
    if not _PENDING_DIR.exists():
        return consumed, skipped
    for token_file in sorted(_PENDING_DIR.glob("*.json")):
        try:
            token = _load_token(token_file)
        except (json.JSONDecodeError, OSError):
            continue
        token_id = token.get("override_id", token_file.stem)
        if _token_covers_any(token, changed_paths):
            if consume_token(token_id, commit_sha):
                consumed.append(token_id)
        else:
            skipped.append(token_id)
    return consumed, skipped


def cmd_consume_for_commit(args: argparse.Namespace) -> int:
    """Consume pending tokens that intersect the given commit's changed paths.
    Best-effort by design (always exit 0): this runs from the post-commit
    hook, where a failure must never be able to fail the commit flow."""
    import subprocess

    result = subprocess.run(
        ["git", "show", "--name-only", "--format=", "--diff-merges=first-parent",
         args.commit_sha],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=str(_REPO_ROOT),
    )
    if result.returncode != 0:
        print(f"consume-for-commit: could not read commit {args.commit_sha}: "
              f"{(result.stderr or '').strip()}", file=sys.stderr)
        return 0
    changed = [ln.strip() for ln in (result.stdout or "").splitlines() if ln.strip()]
    consumed, skipped = consume_for_commit(args.commit_sha, changed)
    for token_id in consumed:
        print(f"Consumed token {token_id} -> archived, linked to commit {args.commit_sha}")
    if skipped:
        print(f"consume-for-commit: left {len(skipped)} pending token(s) untouched "
              f"(paths do not intersect commit {args.commit_sha[:10]}): "
              f"{', '.join(skipped)}")
    return 0


def cmd_list_pending(args: argparse.Namespace) -> int:
    """List all pending override tokens."""
    _PENDING_DIR.mkdir(parents=True, exist_ok=True)
    tokens = sorted(_PENDING_DIR.glob("*.json"))
    if not tokens:
        print("No pending override tokens.")
        return 0
    for tp in tokens:
        try:
            t = _load_token(tp)
            expired = " [EXPIRED]" if _is_expired(t) and not t.get("retroactive") else ""
            retro = " [RETROACTIVE]" if t.get("retroactive") else ""
            print(f"  {t['override_id']}{expired}{retro}: {', '.join(t['paths'])}")
            print(f"    reason: {t['reason'][:80]}")
        except (json.JSONDecodeError, OSError) as e:
            print(f"  {tp.name}: ERROR reading token — {e}")
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    """List all archived (consumed) override tokens."""
    _ARCHIVED_DIR.mkdir(parents=True, exist_ok=True)
    tokens = sorted(_ARCHIVED_DIR.glob("*.json"))
    if not tokens:
        print("No archived override tokens.")
        return 0
    print(f"{'Override ID':<50} {'Paths':<40} {'Commit':<12} {'Retro'}")
    print("-" * 120)
    for tp in tokens:
        try:
            t = _load_token(tp)
            paths_str = ", ".join(t.get("paths", []))[:38]
            commit = (t.get("consumed_by_commit") or "—")[:10]
            retro = "yes" if t.get("retroactive") else "no"
            print(f"{t['override_id']:<50} {paths_str:<40} {commit:<12} {retro}")
        except (json.JSONDecodeError, OSError) as e:
            print(f"{tp.name}: ERROR — {e}")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="override_manager",
        description="Lifecycle manager for forbidden-path override tokens.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # create
    p_create = sub.add_parser("create", help="Create a new pending override token")
    p_create.add_argument("--paths", nargs="+", required=True, help="Forbidden paths to override")
    p_create.add_argument("--reason", required=True, help="Why this override is needed")
    p_create.add_argument("--plan", default="", help="Plan reference (filename)")
    p_create.add_argument("--scope", default="", help="Specific scope of the change")
    p_create.add_argument("--operation", default="edit", choices=["edit", "create", "delete"])
    p_create.add_argument("--retroactive", action="store_true",
                          help="Mark token as retroactive (covers a past edit)")

    # validate-for-path
    p_val = sub.add_parser("validate-for-path",
                            help="Check a pending token covers a path (exit 0=valid, 2=not found)")
    p_val.add_argument("path", help="The forbidden path to check coverage for")

    # consume
    p_consume = sub.add_parser("consume", help="Archive a token after its commit")
    p_consume.add_argument("--token-id", required=True)
    p_consume.add_argument("--commit-sha", required=True)

    # consume-for-commit (2026-08-29: scoped replacement for the post-commit
    # hook's consume-everything sweep)
    p_cfc = sub.add_parser("consume-for-commit",
                            help="Consume only pending tokens whose paths intersect the commit's changed files")
    p_cfc.add_argument("--commit-sha", required=True)

    # list-pending
    sub.add_parser("list-pending", help="List all pending override tokens")

    # audit
    sub.add_parser("audit", help="List all archived (consumed) tokens")

    args = parser.parse_args(argv)

    dispatch = {
        "create": cmd_create,
        "validate-for-path": cmd_validate_for_path,
        "consume": cmd_consume,
        "consume-for-commit": cmd_consume_for_commit,
        "list-pending": cmd_list_pending,
        "audit": cmd_audit,
    }
    return dispatch[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
