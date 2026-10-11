"""deletion_governance_manager.py — Lifecycle management for Deletion Governance Records (DGR).

A DGR is a YAML artifact that records human-approved intent to delete or rename
a tracked file. DGRs are stored in ``deletion-approvals/`` (tracked, CI-visible).
Pending DGRs awaiting consumption are the committed YAML files themselves.

DGR lifecycle:
  1. Create: ``create`` command writes DGR to deletion-approvals/
  2. Commit DGR to repo before staging the deletion
  3. Stage deletion; pre-commit Step 0b validates DGR via ``validate-for-path``
  4. Commit deletion with token "Deletion-Approved: DGR-<id>" in message
  5. Consume: ``consume`` command archives the DGR (moves to deletion-approvals/archived/)

Usage examples:
  # Create a new DGR
  python scripts/pipeline/commands/governance/deletion_governance_manager.py create \\
    --files content/products.aspose.org/ar/old/_index.md \\
    --reason "Locale page removed; English source deleted" \\
    --plan humming-wondering-storm \\
    --class T-01

  # Validate that a DGR covers a path (exit 0=valid, 2=not covered/expired)
  python scripts/pipeline/commands/governance/deletion_governance_manager.py validate-for-path \\
    content/products.aspose.org/ar/old/_index.md

  # Consume (archive) after deletion commit
  python scripts/pipeline/commands/governance/deletion_governance_manager.py consume \\
    --dgr-id DGR-20260704-content-products-asp --commit-sha abc123

  # List pending DGRs
  python scripts/pipeline/commands/governance/deletion_governance_manager.py list-pending

  # Audit archived DGRs
  python scripts/pipeline/commands/governance/deletion_governance_manager.py audit

Exit codes:
  0   success / valid
  1   failure / invalid input
  2   DGR not found, expired, or T-00 rejected
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
_DEFAULT_DGR_DIR = _DEFAULT_REPO_ROOT / "deletion-approvals"
_DEFAULT_ARCHIVED_DIR = _DEFAULT_DGR_DIR / "archived"

_REPO_ROOT = _DEFAULT_REPO_ROOT
_DGR_DIR = _DEFAULT_DGR_DIR
_ARCHIVED_DIR = _DEFAULT_ARCHIVED_DIR

_DGR_TTL_DAYS = 7

# T-00 paths that can never have a DGR
_FORBIDDEN_EXACT: frozenset[str] = frozenset({
    "AGENTS.md",
    "CODEX.md",
    "CLAUDE.md",
    "docs/OPERATOR_BYPASSES.md",
    "scripts/pipeline/commands/governance/path_guard.py",
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

_FORBIDDEN_PREFIXES: tuple[str, ...] = (
    "themes/", "layouts/", "configs/", ".claude/", ".agents/", ".kilocode/",
    "skills/", "docs/governance/", "docs/workflows/", "docs/registries/",
    ".github/workflows/",
)


def configure(
    *,
    repo_root: "Path | str | None" = None,
    dgr_dir: "Path | str | None" = None,
    archived_dir: "Path | str | None" = None,
) -> None:
    """Override module-level path constants for testing."""
    global _REPO_ROOT, _DGR_DIR, _ARCHIVED_DIR
    if repo_root is None and dgr_dir is None and archived_dir is None:
        _REPO_ROOT = _DEFAULT_REPO_ROOT
        _DGR_DIR = _DEFAULT_DGR_DIR
        _ARCHIVED_DIR = _DEFAULT_ARCHIVED_DIR
        return
    if repo_root is not None:
        _REPO_ROOT = Path(repo_root)
        _DGR_DIR = _REPO_ROOT / "deletion-approvals"
        _ARCHIVED_DIR = _DGR_DIR / "archived"
    if dgr_dir is not None:
        _DGR_DIR = Path(dgr_dir)
    if archived_dir is not None:
        _ARCHIVED_DIR = Path(archived_dir)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize(p: str) -> str:
    p = p.replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p


def _slug_from_path(path: str) -> str:
    norm = _normalize(path).replace("/", "-").replace(".", "-").replace("_", "-")
    return norm[:35]


def _dgr_filename(dgr_id: str) -> str:
    return f"{dgr_id}.yaml"


def _load_yaml(path: Path) -> dict:
    try:
        import yaml  # type: ignore
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        # Minimal fallback
        data: dict = {}
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.rstrip("\n")
                if ":" not in line or line.lstrip().startswith("#"):
                    continue
                k, _, v = line.partition(":")
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k and v:
                    data[k] = v
        return data


def _write_yaml(path: Path, dgr: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import yaml  # type: ignore
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            yaml.dump(dgr, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    except ImportError:
        # Minimal fallback serializer
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            for k, v in dgr.items():
                if isinstance(v, list):
                    f.write(f"{k}:\n")
                    for item in v:
                        if isinstance(item, dict):
                            lines = list(item.items())
                            f.write(f"  - {lines[0][0]}: {lines[0][1]}\n")
                            for fk, fv in lines[1:]:
                                f.write(f"    {fk}: {fv}\n")
                        else:
                            f.write(f"  - {item}\n")
                elif v is None:
                    f.write(f"{k}: null\n")
                else:
                    f.write(f'{k}: "{v}"\n')


def _is_t00(path_str: str) -> bool:
    norm = _normalize(path_str)
    if norm in _FORBIDDEN_EXACT:
        return True
    return any(norm.startswith(p) for p in _FORBIDDEN_PREFIXES)


def _is_expired(dgr: dict) -> bool:
    expires_at = dgr.get("expires_at", "")
    if not expires_at:
        return False
    try:
        ts = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
        return datetime.now(tz=timezone.utc) > ts
    except (ValueError, TypeError):
        return True  # malformed -> expired (fail-closed)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_create(args: argparse.Namespace) -> int:
    """Create a new DGR YAML in deletion-approvals/."""
    files_list = args.files if isinstance(args.files, list) else [args.files]

    # Reject T-00 paths
    for path in files_list:
        if _is_t00(path):
            print(
                f"ERROR: '{path}' is a T-00 path. T-00 paths can never be deleted. "
                "No DGR can be created for T-00 paths.",
                file=sys.stderr,
            )
            return 2

    deletion_class = getattr(args, "class") or "T-01"
    operation = args.operation or "hard_delete"

    now = datetime.now(tz=timezone.utc)
    ts = now.strftime("%Y%m%d")
    slug = _slug_from_path(files_list[0])
    dgr_id = f"DGR-{ts}-{slug}"

    dgr = {
        "dgr_id": dgr_id,
        "dgr_version": "1.0",
        "approver": "human-maintainer",
        "approved_at": now.isoformat().replace("+00:00", "Z"),
        "expires_at": (now + timedelta(days=_DGR_TTL_DAYS)).isoformat().replace("+00:00", "Z"),
        "plan_ref": args.plan or "",
        "reason": args.reason,
        "files": [
            {
                "path": _normalize(p),
                "deletion_class": deletion_class,
                "operation": operation,
            }
            for p in files_list
        ],
        "rename_destination": args.rename_destination or None,
        "redirect_plan": args.redirect_plan or "",
        "references_updated": False,
        "commit_message_token": f"Deletion-Approved: {dgr_id}",
    }

    out_path = _DGR_DIR / _dgr_filename(dgr_id)
    _write_yaml(out_path, dgr)

    print(f"Created DGR: {dgr_id}")
    print(f"  File:  {out_path.relative_to(_REPO_ROOT)}")
    print(f"  Files: {', '.join(_normalize(p) for p in files_list)}")
    print(f"  Expires: {dgr['expires_at']}")
    print(f"  Commit message token: {dgr['commit_message_token']}")
    print(f"")
    print(f"  NEXT STEPS:")
    print(f"  1. Stage and commit this DGR file: git add deletion-approvals/{dgr_id}.yaml")
    print(f"  2. Stage the deletion: git rm <path>")
    print(f"  3. Commit with token in message: git commit -m 'feat: ... Deletion-Approved: {dgr_id}'")
    return 0


def cmd_validate_for_path(args: argparse.Namespace) -> int:
    """Check that a valid non-expired DGR covers the given path."""
    norm = _normalize(args.path)
    _DGR_DIR.mkdir(parents=True, exist_ok=True)

    for dgr_file in sorted(_DGR_DIR.glob("*.yaml")):
        if dgr_file.parent.name == "archived":
            continue
        try:
            dgr = _load_yaml(dgr_file)
        except (OSError, Exception) as e:
            print(f"WARNING: malformed DGR {dgr_file.name}: {e}", file=sys.stderr)
            continue

        files = dgr.get("files", [])
        if not isinstance(files, list):
            continue

        covered = any(
            isinstance(entry, dict) and _normalize(str(entry.get("path", ""))) == norm
            for entry in files
        )
        if not covered:
            continue

        if _is_expired(dgr):
            print(
                f"EXPIRED: DGR {dgr.get('dgr_id', dgr_file.stem)} expired — "
                f"expired_at: {dgr.get('expires_at', '?')}",
                file=sys.stderr,
            )
            return 2

        print(f"VALID: DGR {dgr.get('dgr_id', dgr_file.stem)} covers path '{norm}'")
        return 0

    print(f"NO VALID DGR: no pending DGR covers path '{norm}'", file=sys.stderr)
    return 2


def cmd_consume(args: argparse.Namespace) -> int:
    """Archive a DGR after its deletion commit."""
    dgr_file = _DGR_DIR / _dgr_filename(args.dgr_id)
    if not dgr_file.exists():
        print(f"ERROR: DGR {args.dgr_id} not found at {dgr_file}", file=sys.stderr)
        return 1

    dgr = _load_yaml(dgr_file)
    dgr["consumed_by_commit"] = args.commit_sha
    dgr["consumed_at"] = datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z")

    _ARCHIVED_DIR.mkdir(parents=True, exist_ok=True)
    archived_path = _ARCHIVED_DIR / _dgr_filename(args.dgr_id)
    _write_yaml(archived_path, dgr)
    dgr_file.unlink()

    print(f"Consumed DGR {args.dgr_id} -> archived, linked to commit {args.commit_sha}")
    return 0


def cmd_list_pending(args: argparse.Namespace) -> int:
    """List all pending DGRs in deletion-approvals/ (excluding archived/)."""
    _DGR_DIR.mkdir(parents=True, exist_ok=True)
    dgrs = [f for f in sorted(_DGR_DIR.glob("*.yaml")) if f.parent == _DGR_DIR]
    if not dgrs:
        print("No pending DGRs.")
        return 0
    for f in dgrs:
        try:
            dgr = _load_yaml(f)
            expired = " [EXPIRED]" if _is_expired(dgr) else ""
            files_list = dgr.get("files", [])
            paths = ", ".join(
                entry.get("path", "?") for entry in files_list
                if isinstance(entry, dict)
            )
            print(f"  {dgr.get('dgr_id', f.stem)}{expired}")
            print(f"    paths:   {paths}")
            print(f"    reason:  {str(dgr.get('reason', ''))[:80]}")
            print(f"    expires: {dgr.get('expires_at', '?')}")
        except Exception as e:
            print(f"  {f.name}: ERROR reading — {e}")
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    """List all archived (consumed) DGRs."""
    _ARCHIVED_DIR.mkdir(parents=True, exist_ok=True)
    dgrs = sorted(_ARCHIVED_DIR.glob("*.yaml"))
    if not dgrs:
        print("No archived DGRs.")
        return 0
    print(f"{'DGR ID':<50} {'Consumed by':<14} {'Paths'}")
    print("-" * 100)
    for f in dgrs:
        try:
            dgr = _load_yaml(f)
            files_list = dgr.get("files", [])
            paths = ", ".join(
                entry.get("path", "?") for entry in files_list
                if isinstance(entry, dict)
            )[:40]
            commit = str(dgr.get("consumed_by_commit") or "-")[:12]
            print(f"{dgr.get('dgr_id', f.stem):<50} {commit:<14} {paths}")
        except Exception as e:
            print(f"{f.name}: ERROR — {e}")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(
        prog="deletion_governance_manager",
        description="Lifecycle manager for Deletion Governance Records (DGRs).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # create
    p_create = sub.add_parser("create", help="Create a new DGR")
    p_create.add_argument("--files", nargs="+", required=True,
                          help="Paths to be deleted/renamed (T-00 paths rejected)")
    p_create.add_argument("--reason", required=True, help="Why this deletion is needed")
    p_create.add_argument("--plan", default="", help="Plan reference slug")
    p_create.add_argument("--class", default="T-01", choices=["T-01", "T-02"],
                          dest="class", help="Tier class (T-01 or T-02, never T-00)")
    p_create.add_argument("--operation", default="hard_delete",
                          choices=["hard_delete", "rename", "retire"],
                          help="Type of deletion operation")
    p_create.add_argument("--rename-destination", default="",
                          help="Destination path if operation=rename")
    p_create.add_argument("--redirect-plan", default="",
                          help="Description of redirect plan for renamed/retired content")

    # validate-for-path
    p_val = sub.add_parser("validate-for-path",
                            help="Check a DGR covers a path (exit 0=valid, 2=blocked)")
    p_val.add_argument("path", help="Path to validate DGR coverage for")

    # consume
    p_consume = sub.add_parser("consume", help="Archive a DGR after its commit")
    p_consume.add_argument("--dgr-id", required=True, help="DGR ID to consume")
    p_consume.add_argument("--commit-sha", required=True, help="Commit SHA that deleted the file")

    # list-pending
    sub.add_parser("list-pending", help="List all pending DGRs")

    # audit
    sub.add_parser("audit", help="List all archived (consumed) DGRs")

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
