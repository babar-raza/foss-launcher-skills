# Adapted from aspose.org scripts/ci/checks/ for standalone use
"""check_metrics_event_ledger_schema.py — CI gate: validate JSONL event ledger files.

Inspects reports/metrics/events/*.jsonl and validates:
- Each line is valid JSON
- Each event passes metrics_schema.validate_event()
- No token-like values present

Reports line numbers for invalid rows. Missing events directory is OK
unless --require-events is passed.

Usage:
    python scripts/ci/checks/check_metrics_event_ledger_schema.py
    python scripts/ci/checks/check_metrics_event_ledger_schema.py --events-dir path/to/events
    python scripts/ci/checks/check_metrics_event_ledger_schema.py --require-events
    python scripts/ci/checks/check_metrics_event_ledger_schema.py --json-output

Exit codes:
    0  All ledger files valid (or no ledger files found and --require-events not set)
    1  One or more invalid events or invalid JSON
"""
from __future__ import annotations

import argparse
import json
import re
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

_REPO_ROOT = Path(os.environ.get("REPO_ROOT", Path(__file__).resolve().parent.parent.parent.parent))
_DEFAULT_EVENTS_DIR = _REPO_ROOT / "reports" / "metrics" / "events"
_PIPELINE_ROOT = _REPO_ROOT / "scripts" / "pipeline"

# Secret-like pattern for event content
_SECRET_IN_EVENT = re.compile(
    r"(sk-[A-Za-z0-9]{10,})"
    r"|(Bearer\s+[A-Za-z0-9._-]{20,})"
    r"|([?&](api_key|token|key)=[^\s&]{8,})",
    re.IGNORECASE,
)


@dataclass
class LedgerError:
    file: str
    line: int
    error_type: str
    message: str


@dataclass
class LedgerCheckResult:
    passed: bool = True
    files_checked: int = 0
    events_validated: int = 0
    errors: list[LedgerError] = field(default_factory=list)
    missing_dir: bool = False


def _get_validators():
    """Try to import validate_event + MetricsEvent from metrics_schema."""
    try:
        sys.path.insert(0, str(_PIPELINE_ROOT))
        from commands.ops.metrics_schema import validate_event, MetricsEvent  # type: ignore
        return validate_event, MetricsEvent
    except ImportError:
        return None, None


def _get_validate_event_file():
    """Try to import validate_event_file from metrics_event_ledger."""
    try:
        sys.path.insert(0, str(_PIPELINE_ROOT))
        from commands.ops.metrics_event_ledger import validate_event_file  # type: ignore
        return validate_event_file
    except ImportError:
        return None


def _check_event_for_secrets(event_data: dict, file: str, line: int) -> list[LedgerError]:
    """Check event fields for secret-like values."""
    errors: list[LedgerError] = []
    suspicious_fields = ["endpoint", "redacted_error_summary"]
    for field_name in suspicious_fields:
        val = str(event_data.get(field_name, ""))
        if _SECRET_IN_EVENT.search(val):
            errors.append(LedgerError(
                file=file,
                line=line,
                error_type="SECRET_IN_EVENT_FIELD",
                message=f"Secret-like value in field '{field_name}' [value not printed]",
            ))
    return errors


def run_check(events_dir: Path, require_events: bool = False) -> LedgerCheckResult:
    result = LedgerCheckResult()

    if not events_dir.exists():
        result.missing_dir = True
        if require_events:
            result.passed = False
            result.errors.append(LedgerError(
                file=str(events_dir),
                line=0,
                error_type="EVENTS_DIR_MISSING",
                message=f"Events directory not found: {events_dir} (--require-events set)",
            ))
        return result

    validate_event, MetricsEvent = _get_validators()

    jsonl_files = sorted(events_dir.glob("*.jsonl"))
    if not jsonl_files and require_events:
        result.passed = False
        result.errors.append(LedgerError(
            file=str(events_dir),
            line=0,
            error_type="NO_EVENT_FILES",
            message="No .jsonl files found in events directory (--require-events set)",
        ))
        return result

    for jsonl_file in jsonl_files:
        result.files_checked += 1
        rel = str(jsonl_file)
        try:
            text = jsonl_file.read_text(encoding="utf-8")
        except OSError as e:
            result.passed = False
            result.errors.append(LedgerError(file=rel, line=0, error_type="READ_ERROR", message=str(e)))
            continue

        for lineno, raw_line in enumerate(text.splitlines(), start=1):
            stripped = raw_line.strip()
            if not stripped:
                continue

            # 1. Valid JSON
            try:
                event_data = json.loads(stripped)
            except json.JSONDecodeError as e:
                result.passed = False
                result.errors.append(LedgerError(
                    file=rel, line=lineno,
                    error_type="INVALID_JSON",
                    message=f"JSON decode error: {e.msg}",
                ))
                continue

            # 2. Schema validation — validate_event expects a MetricsEvent dataclass
            if validate_event is not None and MetricsEvent is not None:
                try:
                    event_obj = MetricsEvent(**event_data)
                    validation = validate_event(event_obj)
                    if not validation.valid:
                        result.passed = False
                        for err in validation.errors:
                            result.errors.append(LedgerError(
                                file=rel, line=lineno,
                                error_type="SCHEMA_INVALID",
                                message=err,
                            ))
                except (TypeError, Exception) as e:
                    result.passed = False
                    result.errors.append(LedgerError(
                        file=rel, line=lineno,
                        error_type="SCHEMA_CONSTRUCT_ERROR",
                        message=str(e),
                    ))
            else:
                # Minimal check: required fields present
                required = ["event_id", "call_site_id", "status", "timestamp"]
                for req in required:
                    if req not in event_data:
                        result.passed = False
                        result.errors.append(LedgerError(
                            file=rel, line=lineno,
                            error_type="MISSING_FIELD",
                            message=f"Required field missing: {req}",
                        ))

            # 3. Secret scan on event fields
            secret_errors = _check_event_for_secrets(event_data, rel, lineno)
            if secret_errors:
                result.passed = False
                result.errors.extend(secret_errors)

            result.events_validated += 1

    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate JSONL event ledger files for schema compliance.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--events-dir", default=str(_DEFAULT_EVENTS_DIR),
                        help="reports/metrics/events/ directory path")
    parser.add_argument("--require-events", action="store_true",
                        help="Fail if events directory or files are missing")
    parser.add_argument("--json-output", action="store_true", help="Print JSON result")
    args = parser.parse_args(argv)

    result = run_check(
        events_dir=Path(args.events_dir),
        require_events=args.require_events,
    )

    if args.json_output:
        print(json.dumps({
            "passed": result.passed,
            "files_checked": result.files_checked,
            "events_validated": result.events_validated,
            "error_count": len(result.errors),
            "missing_dir": result.missing_dir,
            "errors": [
                {"file": e.file, "line": e.line, "error_type": e.error_type, "message": e.message}
                for e in result.errors
            ],
        }, indent=2))
    else:
        if result.missing_dir and not result.errors:
            print("check_metrics_event_ledger_schema: PASS (no events directory — OK by default)")
        elif result.errors:
            print(f"FAIL — {len(result.errors)} event ledger error(s) in {result.files_checked} file(s):")
            for e in result.errors:
                print(f"  {e.file}:{e.line}  [{e.error_type}]  {e.message}")
        else:
            print(f"check_metrics_event_ledger_schema: PASS — "
                  f"{result.events_validated} events validated in {result.files_checked} file(s)")

    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())
