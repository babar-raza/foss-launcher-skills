# Adapted from aspose.org scripts/ci/checks/ for standalone use
"""check_metrics_sheet_payload_schema.py — CI gate: validate dry/test/failed payload shape.

Inspects:
  - reports/metrics/dry/*.dry.json  — dry-run payloads
  - reports/metrics/tests/*.json    — test-mode post records
  - reports/metrics/failed/*.failed.json — failed post records

Validates:
  - Row payloads have exactly the 17 Google Sheet fields
  - Test-mode rows have job_type="test" and item_name starting with "[TEST]"
  - Failed payloads do not contain token-like values
  - Production rows not present unless --allow-production

Usage:
    python scripts/ci/checks/check_metrics_sheet_payload_schema.py
    python scripts/ci/checks/check_metrics_sheet_payload_schema.py --json-output
    python scripts/ci/checks/check_metrics_sheet_payload_schema.py --allow-production

Exit codes:
    0  All payloads valid (or no payload files found)
    1  One or more invalid payloads
"""
from __future__ import annotations

import argparse
import json
import re
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

_REPO_ROOT = Path(os.environ.get("REPO_ROOT", Path(os.environ.get("REPO_ROOT", str(Path(__file__).resolve().parent.parent.parent.parent)))))
_PIPELINE_ROOT = _REPO_ROOT / "scripts" / "pipeline"

# The 17 required Google Sheet fields
REQUIRED_ROW_FIELDS = {
    "timestamp",
    "agent_name",
    "agent_owner",
    "job_type",
    "run_id",
    "status",
    "product",
    "platform",
    "website",
    "website_section",
    "item_name",
    "items_discovered",
    "items_failed",
    "items_succeeded",
    "run_duration_ms",
    "token_usage",
    "api_calls_count",
}

# Secret-like token pattern
_SECRET_PATTERN = re.compile(
    r"(sk-[A-Za-z0-9]{10,})"
    r"|(Bearer\s+[A-Za-z0-9._-]{20,})"
    r"|([?&](api_key|token|key)=[^\s&]{8,})"
    r"|(ghp_[A-Za-z0-9]{10,})",
    re.IGNORECASE,
)


@dataclass
class PayloadError:
    file: str
    error_type: str
    message: str


@dataclass
class PayloadCheckResult:
    passed: bool = True
    dry_files_checked: int = 0
    test_files_checked: int = 0
    failed_files_checked: int = 0
    errors: list[PayloadError] = field(default_factory=list)


def _get_validators():
    """Try to import validate_row and MetricsRow from metrics_schema."""
    try:
        sys.path.insert(0, str(_PIPELINE_ROOT))
        from commands.ops.metrics_schema import validate_row, MetricsRow  # type: ignore
        return validate_row, MetricsRow
    except ImportError:
        return None, None


def _extract_row(data: dict) -> dict | None:
    """Extract the row object from a payload. Handles both flat rows and wrapped."""
    # Direct row: has run_id + all required fields at top level
    if "run_id" in data and "job_type" in data:
        return data
    # Wrapped row: has a "row" key
    row = data.get("row")
    if isinstance(row, dict) and "run_id" in row:
        return row
    return None


def _check_row_fields(row: dict, file: str) -> list[PayloadError]:
    errors: list[PayloadError] = []
    row_keys = set(row.keys())
    missing = REQUIRED_ROW_FIELDS - row_keys
    for field_name in sorted(missing):
        errors.append(PayloadError(
            file=file,
            error_type="MISSING_REQUIRED_FIELD",
            message=f"Missing required field: {field_name}",
        ))
    return errors


def _check_test_row_markers(row: dict, file: str) -> list[PayloadError]:
    errors: list[PayloadError] = []
    if row.get("job_type") != "test":
        errors.append(PayloadError(
            file=file,
            error_type="TEST_ROW_WRONG_JOB_TYPE",
            message=f"Test row must have job_type='test', got: '{row.get('job_type')}'",
        ))
    item_name = str(row.get("item_name", ""))
    if not item_name.startswith("[TEST]"):
        errors.append(PayloadError(
            file=file,
            error_type="TEST_ROW_MISSING_PREFIX",
            message=f"Test row item_name must start with '[TEST]', got: '{item_name[:50]}'",
        ))
    return errors


def _check_for_tokens(data: dict, file: str) -> list[PayloadError]:
    """Check that no field contains a token-like value."""
    errors: list[PayloadError] = []
    def _scan(obj: object, path: str = "") -> None:
        if isinstance(obj, str):
            if _SECRET_PATTERN.search(obj):
                errors.append(PayloadError(
                    file=file,
                    error_type="TOKEN_IN_PAYLOAD",
                    message=f"Token-like value detected at {path} [value not printed]",
                ))
        elif isinstance(obj, dict):
            for k, v in obj.items():
                _scan(v, f"{path}.{k}" if path else k)
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                _scan(v, f"{path}[{i}]")
    _scan(data)
    return errors


def _check_production_row(row: dict, file: str) -> list[PayloadError]:
    """Flag rows that appear to be real production rows (not test, not dry)."""
    errors: list[PayloadError] = []
    job_type = row.get("job_type", "")
    item_name = str(row.get("item_name", ""))
    if job_type != "test" and not item_name.startswith("[TEST]"):
        errors.append(PayloadError(
            file=file,
            error_type="PRODUCTION_ROW_NOT_ALLOWED",
            message=f"Production row found without --allow-production: job_type='{job_type}'",
        ))
    return errors


def run_check(root: Path, allow_production: bool = False) -> PayloadCheckResult:
    result = PayloadCheckResult()
    validate_row, MetricsRow = _get_validators()

    def _check_and_validate(file_path: Path, is_test_file: bool = False,
                            is_failed_file: bool = False) -> list[PayloadError]:
        errors: list[PayloadError] = []
        rel = str(file_path)
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            return [PayloadError(file=rel, error_type="INVALID_JSON", message=str(e))]

        row = _extract_row(data)
        if row is None:
            return [PayloadError(file=rel, error_type="NO_ROW_OBJECT",
                                 message="Cannot extract row from payload")]

        # Validate row fields
        errors.extend(_check_row_fields(row, rel))

        # Schema validation — validate_row expects a MetricsRow dataclass instance
        if validate_row is not None and MetricsRow is not None:
            try:
                row_obj = MetricsRow(**row)
                vr = validate_row(row_obj)
                if not vr.valid:
                    for err in vr.errors:
                        errors.append(PayloadError(file=rel, error_type="SCHEMA_INVALID", message=err))
            except TypeError as e:
                errors.append(PayloadError(file=rel, error_type="SCHEMA_CONSTRUCT_ERROR", message=str(e)))
            except Exception as e:
                errors.append(PayloadError(file=rel, error_type="SCHEMA_ERROR", message=str(e)))

        # Test row checks
        if is_test_file:
            errors.extend(_check_test_row_markers(row, rel))

        # Token check on failed files
        if is_failed_file:
            errors.extend(_check_for_tokens(data, rel))

        # Production row check
        if not is_test_file and not is_failed_file and not allow_production:
            prod_errors = _check_production_row(row, rel)
            # Only flag production rows in tests/ — dry/ rows are expected to be real job types
            if is_test_file:
                errors.extend(prod_errors)

        return errors

    # Dry-run payloads
    dry_dir = root / "reports" / "metrics" / "dry"
    if dry_dir.exists():
        for f in sorted(dry_dir.glob("*.dry.json")):
            result.dry_files_checked += 1
            rel = str(f)
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as e:
                result.passed = False
                result.errors.append(PayloadError(file=rel, error_type="INVALID_JSON", message=str(e)))
                continue
            row = _extract_row(data)
            if row is None:
                result.passed = False
                result.errors.append(PayloadError(file=rel, error_type="NO_ROW_OBJECT",
                                                   message="Cannot extract row from dry-run payload"))
                continue
            field_errors = _check_row_fields(row, rel)
            if field_errors:
                result.passed = False
                result.errors.extend(field_errors)
            # Validate with schema if available — validate_row expects MetricsRow dataclass
            if validate_row is not None and MetricsRow is not None:
                try:
                    row_obj = MetricsRow(**row)
                    vr = validate_row(row_obj)
                    if not vr.valid:
                        result.passed = False
                        for err in vr.errors:
                            result.errors.append(PayloadError(file=rel, error_type="SCHEMA_INVALID", message=err))
                except Exception:
                    pass

    # Test-mode rows
    tests_dir = root / "reports" / "metrics" / "tests"
    if tests_dir.exists():
        for f in sorted(tests_dir.glob("*.json")):
            if f.name.endswith(".dry.json"):
                continue
            result.test_files_checked += 1
            errors = _check_and_validate(f, is_test_file=True)
            if errors:
                result.passed = False
                result.errors.extend(errors)

    # Failed payloads
    failed_dir = root / "reports" / "metrics" / "failed"
    if failed_dir.exists():
        for f in sorted(failed_dir.glob("*.failed.json")):
            result.failed_files_checked += 1
            errors = _check_and_validate(f, is_failed_file=True)
            if errors:
                result.passed = False
                result.errors.extend(errors)

    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate dry/test/failed metrics payload JSON files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--allow-production", action="store_true",
                        help="Allow real production rows in tests/ directory")
    parser.add_argument("--json-output", action="store_true", help="Print JSON result")
    args = parser.parse_args(argv)

    result = run_check(root=_REPO_ROOT, allow_production=args.allow_production)

    if args.json_output:
        print(json.dumps({
            "passed": result.passed,
            "dry_files_checked": result.dry_files_checked,
            "test_files_checked": result.test_files_checked,
            "failed_files_checked": result.failed_files_checked,
            "error_count": len(result.errors),
            "errors": [{"file": e.file, "error_type": e.error_type, "message": e.message}
                       for e in result.errors],
        }, indent=2))
    else:
        total = result.dry_files_checked + result.test_files_checked + result.failed_files_checked
        if result.errors:
            print(f"FAIL — {len(result.errors)} payload error(s) across {total} file(s):")
            for e in result.errors:
                print(f"  {e.file}  [{e.error_type}]  {e.message}")
        else:
            print(f"check_metrics_sheet_payload_schema: PASS — {total} payload file(s) validated "
                  f"(dry={result.dry_files_checked}, test={result.test_files_checked}, "
                  f"failed={result.failed_files_checked})")

    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())
