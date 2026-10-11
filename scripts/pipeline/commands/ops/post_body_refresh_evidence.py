"""
post_body_refresh_evidence.py — TC-09: Re-attach evidence after body_refresh writes.

Reads the writes log at reports/body_refresh_writes/{run_id}.txt (produced by
body_refresh.py for each successful file write) and calls attach_evidence for each
written file to ensure evidence frontmatter (model_sha, claim_ids) stays current
after body prose updates.

This closes the gap where body_refresh.py updates prose but leaves stale evidence
blocks pointing to removed claims (proven in 3d/net Scene.md, RC-05 in plan).

CLI:
    PYTHONPATH=scripts/pipeline python -m commands.ops.post_body_refresh_evidence 3d net
    PYTHONPATH=scripts/pipeline python -m commands.ops.post_body_refresh_evidence --run-id body-refresh-3d-net
    PYTHONPATH=scripts/pipeline python -m commands.ops.post_body_refresh_evidence --writes-file path/to/writes.txt

S-20 Step 9 invocation:
    PYTHONPATH=scripts/pipeline python -m commands.ops.post_body_refresh_evidence {family} {platform}
"""

from pathlib import Path
import sys

_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

import argparse
from datetime import datetime, timezone

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[4]
_REPO_ROOT = _DEFAULT_REPO_ROOT
_REPORTS_ROOT = _REPO_ROOT / "reports"
_BODY_REFRESH_WRITES_ROOT = _REPORTS_ROOT / "body_refresh_writes"


def configure(*, repo_root: "Path | str | None" = None) -> None:
    """Reconfigure module paths (used by tests)."""
    global _REPO_ROOT, _REPORTS_ROOT, _BODY_REFRESH_WRITES_ROOT
    if repo_root is not None:
        _REPO_ROOT = Path(repo_root)
        _REPORTS_ROOT = _REPO_ROOT / "reports"
        _BODY_REFRESH_WRITES_ROOT = _REPORTS_ROOT / "body_refresh_writes"
    else:
        _REPO_ROOT = _DEFAULT_REPO_ROOT
        _REPORTS_ROOT = _DEFAULT_REPO_ROOT / "reports"
        _BODY_REFRESH_WRITES_ROOT = _REPORTS_ROOT / "body_refresh_writes"


def _find_writes_file(family: str, platform: str) -> "Path | None":
    """Find the most recent writes log for a given product."""
    run_id = f"body-refresh-{family}-{platform}"
    path = _BODY_REFRESH_WRITES_ROOT / f"{run_id}.txt"
    if path.is_file():
        return path
    return None


def run_evidence_reattach(
    paths: list[str],
    *,
    dry_run: bool = False,
    max_files: int = 200,
) -> dict:
    """Call attach_evidence for each file path in paths.

    Returns a summary dict with counts.
    """
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "files_total": len(paths),
        "files_processed": 0,
        "files_skipped": 0,
        "errors": [],
        "dry_run": dry_run,
    }

    if not paths:
        return summary

    # Filter to existing files only
    existing = [p for p in paths if Path(p).is_file()]
    summary["files_skipped"] = len(paths) - len(existing)

    if not existing:
        return summary

    # Limit to max_files
    to_process = existing[:max_files]
    if len(existing) > max_files:
        print(f"  WARNING: {len(existing)} files in writes log; processing first {max_files}")

    if dry_run:
        print(f"  [DRY-RUN] Would re-attach evidence for {len(to_process)} files")
        summary["files_processed"] = len(to_process)
        return summary

    # Call attach_evidence runner
    try:
        _HERE = Path(__file__).resolve().parent
        attach_evidence_root = _HERE.parent / "healing"
        if str(attach_evidence_root.parent) not in sys.path:
            sys.path.insert(0, str(attach_evidence_root.parent))

        from evidence.runner import main as attach_main
        # attach_evidence --files path1 path2 ...
        argv = ["--files", "--max-files", str(max_files)] + to_process
        try:
            attach_main(argv)
            summary["files_processed"] = len(to_process)
        except SystemExit as e:
            if e.code not in (0, None):
                summary["errors"].append(f"attach_evidence exited with code {e.code}")
    except ImportError as e:
        summary["errors"].append(f"ImportError loading evidence.runner: {e}")
        print(f"  WARNING: Could not import evidence.runner: {e}")
        print("  Evidence re-attachment skipped.")

    return summary


def process_product(
    family: str,
    platform: str,
    *,
    dry_run: bool = False,
) -> dict:
    """Re-attach evidence for all files written during body_refresh for a product."""
    writes_file = _find_writes_file(family, platform)
    if not writes_file:
        return {
            "family": family,
            "platform": platform,
            "result": "NO_WRITES_FILE",
            "message": f"No writes log found at {_BODY_REFRESH_WRITES_ROOT}/body-refresh-{family}-{platform}.txt",
        }

    paths = [
        line.strip()
        for line in writes_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    print(f"  post_body_refresh_evidence: {family}/{platform}")
    print(f"  writes_file: {writes_file}")
    print(f"  files_in_log: {len(paths)}")

    summary = run_evidence_reattach(paths, dry_run=dry_run)
    summary["family"] = family
    summary["platform"] = platform
    summary["writes_file"] = str(writes_file)
    return summary


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(
        prog="post_body_refresh_evidence",
        description="Re-attach evidence frontmatter after body_refresh writes (TC-09).",
    )
    parser.add_argument("family", nargs="?", help="Product family (e.g. 3d)")
    parser.add_argument("platform", nargs="?", help="Platform (e.g. net)")
    parser.add_argument(
        "--run-id",
        metavar="RUN_ID",
        help="Override run ID (default: body-refresh-{family}-{platform})",
    )
    parser.add_argument(
        "--writes-file",
        metavar="PATH",
        help="Override path to writes log file",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without writing",
    )
    args = parser.parse_args(argv)

    # Direct writes-file mode
    if args.writes_file:
        writes_path = Path(args.writes_file)
        if not writes_path.is_file():
            print(f"ERROR: writes file not found: {writes_path}")
            return 2
        paths = [
            line.strip()
            for line in writes_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        summary = run_evidence_reattach(paths, dry_run=args.dry_run)
        print(f"  files_processed: {summary['files_processed']}")
        return 0

    if not args.family or not args.platform:
        parser.print_help()
        return 1

    summary = process_product(args.family, args.platform, dry_run=args.dry_run)
    result = summary.get("result", "")
    if result == "NO_WRITES_FILE":
        print(f"  {summary['message']}")
        return 2

    print(f"  files_processed: {summary.get('files_processed', 0)}")
    print(f"  files_skipped:   {summary.get('files_skipped', 0)}")
    if summary.get("errors"):
        for err in summary["errors"]:
            print(f"  ERROR: {err}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
