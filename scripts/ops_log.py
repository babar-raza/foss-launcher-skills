"""ops_log.py — Append-only JSONL operation log for the content pipeline.

Each call to log_entry() appends one JSON line to reports/ops.log (or a
custom path). Thread-safe via append-mode file open.
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow direct import of config_loader when run as a script
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config_loader import resolve_reports_root

VALID_STATUSES = {"PASS", "FAIL", "WARN", "ERROR", "ESCALATE"}


def _default_log_path() -> Path:
    return resolve_reports_root() / "ops.log"


def log_entry(
    skill: str,
    status: str,
    *,
    family: str = "",
    platform: str = "",
    artifacts_written: "list[str] | None" = None,
    errors: "list[str] | None" = None,
    log_path: "str | Path | None" = None,
) -> Path:
    """Append one entry to the ops log. Returns the log file path.

    Args:
        skill: Skill name (e.g. "ground-check", "path-guard").
        status: One of PASS, FAIL, WARN, ERROR, ESCALATE.
        family: Product family; empty string if not applicable.
        platform: Platform; empty string if not applicable.
        artifacts_written: File paths written by the skill.
        errors: Error or warning messages.
        log_path: Override default log location.

    Returns:
        Path to the log file.
    """
    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid status {status!r}. Must be one of {VALID_STATUSES}")

    resolved = Path(log_path) if log_path is not None else _default_log_path()
    resolved.parent.mkdir(parents=True, exist_ok=True)

    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "skill": skill,
        "family": family,
        "platform": platform,
        "status": status,
        "artifacts_written": artifacts_written if artifacts_written is not None else [],
        "errors": errors if errors is not None else [],
    }

    with open(resolved, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")

    return resolved


def read_log(log_path: "str | Path | None" = None) -> "list[dict]":
    """Read all entries from the ops log. Returns list of dicts."""
    resolved = Path(log_path) if log_path is not None else _default_log_path()
    if not resolved.is_file():
        return []
    entries = []
    with open(resolved, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Append a single entry to the ops log."
    )
    parser.add_argument("--skill", required=True, help="Skill name")
    parser.add_argument(
        "--status",
        required=True,
        choices=sorted(VALID_STATUSES),
        help="Entry status",
    )
    parser.add_argument("--family", default="", help="Product family")
    parser.add_argument("--platform", default="", help="Platform")
    parser.add_argument(
        "--error", action="append", dest="errors", default=[],
        metavar="MSG", help="Error/warning message (repeatable)",
    )
    parser.add_argument("--log-path", default=None, help="Override log file path")
    return parser


def main(argv: "list[str] | None" = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)
    path = log_entry(
        skill=args.skill,
        status=args.status,
        family=args.family,
        platform=args.platform,
        errors=args.errors,
        log_path=args.log_path,
    )
    print(f"Logged to {path}")


if __name__ == "__main__":
    main()
