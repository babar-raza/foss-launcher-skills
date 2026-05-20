# Adapted from aspose.org scripts/ci/checks/ for standalone use
"""check_metrics_test_post_limit.py — CI gate: enforce test row count limits.

Counts test_submit posted markers in reports/metrics/posted/ and verifies they
do not exceed:
  - max_per_sprint (default: 2) — warn or soft-fail
  - hard_limit (default: 3) — always fail

Identification: posted markers with mode == "test_submit".
Ignores production_submit markers. No network calls.


Usage:
    python scripts/ci/checks/check_metrics_test_post_limit.py
    python scripts/ci/checks/check_metrics_test_post_limit.py --posted-dir path/to/posted
    python scripts/ci/checks/check_metrics_test_post_limit.py --max 2 --hard-limit 3
    python scripts/ci/checks/check_metrics_test_post_limit.py --json-output

Exit codes:
    0  Within limits
    1  Hard limit exceeded (or --strict-max and max exceeded)
    2  Max-per-sprint exceeded but within hard limit (soft warning only; exit 0 by default)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

_REPO_ROOT = Path(os.environ.get("REPO_ROOT", Path(os.environ.get("REPO_ROOT", str(Path(__file__).resolve().parent.parent.parent.parent)))))
_DEFAULT_POSTED_DIR = _REPO_ROOT / "reports" / "metrics" / "posted"

DEFAULT_MAX_PER_SPRINT = 2
DEFAULT_HARD_LIMIT = 3


@dataclass
class TestRowFile:
    path: str
    run_id: str
    job_type: str
    is_test_mode: bool


@dataclass
class PostLimitResult:
    passed: bool = True
    hard_limit_exceeded: bool = False
    max_exceeded: bool = False
    test_row_count: int = 0
    max_per_sprint: int = DEFAULT_MAX_PER_SPRINT
    hard_limit: int = DEFAULT_HARD_LIMIT
    test_row_files: list[TestRowFile] = field(default_factory=list)
    dry_run_files_ignored: int = 0
    message: str = ""


def _load_json_safe(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _is_test_posted_marker(data: dict) -> bool:
    """Return True if this posted marker is from a test_submit.

    Posted markers use mode == "test_submit" to identify test rows.
    Fields like job_type and item_name are not stored in posted markers.
    """
    return data.get("mode") == "test_submit"


def run_check(
    posted_dir: Path | None = None,
    max_per_sprint: int = DEFAULT_MAX_PER_SPRINT,
    hard_limit: int = DEFAULT_HARD_LIMIT,
    *,
    tests_dir: Path | None = None,  # deprecated alias for posted_dir
) -> PostLimitResult:
    # Resolve directory: posted_dir takes precedence; tests_dir is a deprecated alias
    scan_dir = posted_dir if posted_dir is not None else (
        tests_dir if tests_dir is not None else _DEFAULT_POSTED_DIR
    )
    result = PostLimitResult(max_per_sprint=max_per_sprint, hard_limit=hard_limit)

    if not scan_dir.exists():
        result.message = f"Posted directory not found: {scan_dir} — treating as 0 test posts"
        return result

    for json_file in sorted(scan_dir.glob("*.json")):
        data = _load_json_safe(json_file)
        if data is None:
            continue
        if not _is_test_posted_marker(data):
            continue
        run_id = data.get("run_id", json_file.stem)
        result.test_row_files.append(TestRowFile(
            path=str(json_file),
            run_id=run_id,
            job_type="test_submit",
            is_test_mode=True,
        ))

    result.test_row_count = len(result.test_row_files)

    if result.test_row_count > hard_limit:
        result.hard_limit_exceeded = True
        result.passed = False
        result.message = (f"Hard limit exceeded: {result.test_row_count} test rows found, "
                          f"hard limit is {hard_limit}")
    elif result.test_row_count > max_per_sprint:
        result.max_exceeded = True
        # Max exceeded is a soft warning by default (not a failure unless --strict-max)
        result.message = (f"Max-per-sprint soft limit exceeded: {result.test_row_count} test rows, "
                          f"max is {max_per_sprint}")
    else:
        result.message = (f"Within limits: {result.test_row_count}/{max_per_sprint} test rows "
                          f"(hard limit: {hard_limit})")

    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Enforce test row posting limits.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--posted-dir", default=str(_DEFAULT_POSTED_DIR),
                        help="reports/metrics/posted/ path (default: repo root posted dir)")
    parser.add_argument("--tests-dir", default=None,
                        help="Deprecated alias for --posted-dir; use --posted-dir instead")
    parser.add_argument("--max", type=int, default=DEFAULT_MAX_PER_SPRINT,
                        help=f"Max test rows per sprint (default: {DEFAULT_MAX_PER_SPRINT})")
    parser.add_argument("--hard-limit", type=int, default=DEFAULT_HARD_LIMIT,
                        help=f"Hard maximum test rows ever (default: {DEFAULT_HARD_LIMIT})")
    parser.add_argument("--strict-max", action="store_true",
                        help="Fail (exit 1) even when only max is exceeded (default: advisory only)")
    parser.add_argument("--json-output", action="store_true", help="Print JSON result")
    args = parser.parse_args(argv)

    # --posted-dir takes precedence; --tests-dir is deprecated alias
    posted_dir = Path(args.posted_dir)
    tests_dir_arg = Path(args.tests_dir) if args.tests_dir else None
    result = run_check(
        posted_dir=posted_dir,
        max_per_sprint=args.max,
        hard_limit=args.hard_limit,
        tests_dir=tests_dir_arg,
    )

    # Apply strict-max flag
    if args.strict_max and result.max_exceeded:
        result.passed = False

    if args.json_output:
        print(json.dumps({
            "passed": result.passed,
            "test_row_count": result.test_row_count,
            "max_per_sprint": result.max_per_sprint,
            "hard_limit": result.hard_limit,
            "hard_limit_exceeded": result.hard_limit_exceeded,
            "max_exceeded": result.max_exceeded,
            "dry_run_files_ignored": result.dry_run_files_ignored,
            "message": result.message,
            "test_row_files": [f.path for f in result.test_row_files],
        }, indent=2))
    else:
        status = "PASS" if result.passed else "FAIL"
        if result.max_exceeded and not result.hard_limit_exceeded:
            status = "WARN"
        print(f"check_metrics_test_post_limit: {status} — {result.message}")
        if result.test_row_files:
            for f in result.test_row_files:
                print(f"  {f.path}  job_type={f.job_type}  test_mode={f.is_test_mode}")

    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())
