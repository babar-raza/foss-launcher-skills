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
    return p.replace("\\", "/").lstrip("./")


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
    print(f"  Commit this file before or with the forbidden-path edit.")
    return 0


def cmd_validate_for_path(args: argparse.Namespace) -> int:
    """Check that a valid (non-expired, non-consumed) pending token covers the given path."""
    target = _normalize(args.path)
    _PENDING_DIR.mkdir(parents=True, exist_ok=True)

    for token_file in _PENDING_DIR.glob("*.json"):
        try:
            token = _load_token(token_file)
        except (json.JSONDecodeError, OSError):
            continue

        covered = any(target == p or target.startswith(p.rstrip("/") + "/")
                      for p in token.get("paths", []))
        if not covered:
            continue

        if _is_expired(token) and not token.get("retroactive", False):
            print(f"EXPIRED: token {token['override_id']} is older than {_TOKEN_TTL_DAYS} days",
                  file=sys.stderr)
            return 2

        print(f"VALID: token {token['override_id']} covers path '{target}'")
        return 0

    print(f"NO VALID TOKEN: no pending override token covers path '{target}'", file=sys.stderr)
    return 2


def cmd_consume(args: argparse.Namespace) -> int:
    """Move a pending token to archived and record the commit SHA."""
    pending_path = _PENDING_DIR / _token_filename(args.token_id)
    if not pending_path.exists():
        print(f"ERROR: token {args.token_id} not found in pending/", file=sys.stderr)
        return 1

    token = _load_token(pending_path)
    token["consumed_by_commit"] = args.commit_sha
    token["consumed_at"] = datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z")

    _ARCHIVED_DIR.mkdir(parents=True, exist_ok=True)
    archived_path = _ARCHIVED_DIR / _token_filename(args.token_id)
    _save_token(archived_path, token)
    pending_path.unlink()
    print(f"Consumed token {args.token_id} -> archived, linked to commit {args.commit_sha}")
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

    # list-pending
    sub.add_parser("list-pending", help="List all pending override tokens")

    # audit
    sub.add_parser("audit", help="List all archived (consumed) tokens")

    args = parser.parse_args(argv)

    dispatch = {
        "create": cmd_create,
        "validate-for-path": cmd_validate_for_path,
        "consume": cmd_consume,
        "list-pending": cmd_list_pending,
        "audit": cmd_audit,
    }
    return dispatch[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
