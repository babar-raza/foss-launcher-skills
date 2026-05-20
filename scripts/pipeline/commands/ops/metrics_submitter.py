# Adapted from aspose.org
"""Production-safe Agent Metrics API submission layer.

Provides MetricsSubmitter — a controlled submission layer that enforces
dry-run as default, requires explicit environment variables and approval
flags for production writes, and never hardcodes endpoints or tokens.

Submission modes
----------------
dry_run (DEFAULT)
    Validates the row and returns a result with submitted=False.
    Writes nothing to disk unless output_path is provided.

export_json
    Same as dry_run but also writes the validated payload to a local JSON file.
    No HTTP call.

test_submit
    Submits via injected HTTP client (or real HTTP if approved).
    Row MUST have job_type='test' or item_name starting with '[TEST] '.
    Requires AGENT_METRICS_ENDPOINT and AGENT_METRICS_TOKEN.
    Safe for CI/test environments.

production_submit
    Same as test_submit but:
    - requires owner_approved=True explicitly passed to submit()
    - row must NOT have job_type='test'
    - enforced by taxonomy: production_requires_owner_approval=True
    - hard limit checked (max_test_rows_per_sprint is a soft limit for test rows)

Safety invariants
-----------------
- AGENT_METRICS_TOKEN is NEVER included in SubmitResult, logs, or output JSON.
- endpoint is partially redacted in SubmitResult (middle characters masked).
- Dry-run is the default; production requires two explicit flags.
- validate_row() runs before any HTTP call.
- No hardcoded endpoint, token, or metrics values.
- _http_client injection for zero-network tests.

Slice 7 of Agent Metrics Integration (METRICS-PLAN-001 v7.1).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Load scripts/pipeline/.env if env vars not already set (override=False: system env wins)
load_dotenv(Path(__file__).parent.parent.parent / ".env", override=False)

from commands.ops.metrics_schema import (
    MetricsRow,
    ValidationResult,
    row_to_dict,
    validate_row,
    validate_test_row,
)

# ---------------------------------------------------------------------------
# Environment variable names (canonical — never hardcoded elsewhere)
# ---------------------------------------------------------------------------

ENV_ENDPOINT = "AGENT_METRICS_ENDPOINT"
ENV_TOKEN = "AGENT_METRICS_TOKEN"

# ---------------------------------------------------------------------------
# Submission modes
# ---------------------------------------------------------------------------

MODE_DRY_RUN = "dry_run"
MODE_EXPORT_JSON = "export_json"
MODE_TEST_SUBMIT = "test_submit"
MODE_PRODUCTION_SUBMIT = "production_submit"

VALID_MODES = frozenset({
    MODE_DRY_RUN,
    MODE_EXPORT_JSON,
    MODE_TEST_SUBMIT,
    MODE_PRODUCTION_SUBMIT,
})

# ---------------------------------------------------------------------------
# Test-row posting limits (taxonomy: posting_modes section)
# ---------------------------------------------------------------------------

_SOFT_TEST_ROW_LIMIT = 2  # max_test_rows_per_sprint
_HARD_TEST_ROW_LIMIT = 3  # hard_test_row_limit

# ---------------------------------------------------------------------------
# SubmitResult
# ---------------------------------------------------------------------------

@dataclass
class SubmitResult:
    """Outcome of a submission attempt."""

    mode: str
    submitted: bool
    status_code: int | None
    response_summary: str | None
    response_run_id: str | None
    output_path: str | None
    redacted_endpoint: str | None
    error: str | None
    row_valid: bool
    validation_errors: list[str]


# ---------------------------------------------------------------------------
# MetricsSubmitter
# ---------------------------------------------------------------------------

class MetricsSubmitter:
    """Production-safe submitter for MetricsRow payloads.

    Parameters
    ----------
    mode:
        One of MODE_DRY_RUN (default), MODE_EXPORT_JSON, MODE_TEST_SUBMIT,
        MODE_PRODUCTION_SUBMIT.
    output_path:
        For export_json mode: path to write the JSON payload.
        Optional in other modes (if set, also writes export).
    _http_client:
        Injected HTTP transport for tests. Must support:
            post(url, *, json, headers, timeout) -> response
        where response has .status_code and .json() -> dict.
        If None, uses requests (only in submit modes).
    """

    def __init__(
        self,
        mode: str = MODE_DRY_RUN,
        output_path: str | Path | None = None,
        *,
        _http_client: Any = None,
        _markers_root: str | Path | None = None,
        _failed_root: str | Path | None = None,
        _dry_root: str | Path | None = None,
    ):
        if mode not in VALID_MODES:
            raise ValueError(f"Invalid mode '{mode}'. Must be one of {sorted(VALID_MODES)}")
        self.mode = mode
        self.output_path = Path(output_path) if output_path else None
        self._http_client = _http_client
        self._markers_root = Path(_markers_root) if _markers_root else Path("reports/metrics/posted")
        self._failed_root = Path(_failed_root) if _failed_root else Path("reports/metrics/failed")
        self._dry_root = Path(_dry_root) if _dry_root else Path("reports/metrics/dry")

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def submit(
        self,
        row: MetricsRow,
        *,
        owner_approved: bool = False,
    ) -> SubmitResult:
        """Validate and submit (or dry-run) a MetricsRow.

        Parameters
        ----------
        row:
            Fully-populated MetricsRow to submit.
        owner_approved:
            Must be True for production_submit. Ignored in other modes.

        Returns
        -------
        SubmitResult
            Never raises; all errors are captured in SubmitResult.error.
        """
        # Step 1: validate row
        validation = validate_row(row)
        if not validation.valid:
            return SubmitResult(
                mode=self.mode,
                submitted=False,
                status_code=None,
                response_summary=None,
                response_run_id=None,
                output_path=None,
                redacted_endpoint=None,
                error=f"Row validation failed: {'; '.join(validation.errors)}",
                row_valid=False,
                validation_errors=validation.errors,
            )

        # Step 2: dispatch by mode
        if self.mode == MODE_DRY_RUN:
            return self._dry_run(row, validation)

        if self.mode == MODE_EXPORT_JSON:
            return self._export_json(row, validation)

        if self.mode == MODE_TEST_SUBMIT:
            return self._test_submit(row, validation)

        if self.mode == MODE_PRODUCTION_SUBMIT:
            return self._production_submit(row, validation, owner_approved=owner_approved)

        # Should not reach here
        return SubmitResult(
            mode=self.mode,
            submitted=False,
            status_code=None,
            response_summary=None,
            response_run_id=None,
            output_path=None,
            redacted_endpoint=None,
            error=f"Unknown mode: {self.mode}",
            row_valid=True,
            validation_errors=[],
        )

    # ------------------------------------------------------------------
    # Mode implementations
    # ------------------------------------------------------------------

    def _dry_run(self, row: MetricsRow, validation: ValidationResult) -> SubmitResult:
        """Validate only. Write export if output_path set. No HTTP."""
        out = self._maybe_export(row)
        return SubmitResult(
            mode=MODE_DRY_RUN,
            submitted=False,
            status_code=None,
            response_summary="dry_run — no HTTP call",
            response_run_id=None,
            output_path=str(out) if out else None,
            redacted_endpoint=None,
            error=None,
            row_valid=True,
            validation_errors=[],
        )

    def _export_json(self, row: MetricsRow, validation: ValidationResult) -> SubmitResult:
        """Write validated payload to JSON. No HTTP."""
        out = self._write_export(row, self.output_path)
        return SubmitResult(
            mode=MODE_EXPORT_JSON,
            submitted=False,
            status_code=None,
            response_summary="export_json — payload written to disk",
            response_run_id=None,
            output_path=str(out),
            redacted_endpoint=None,
            error=None,
            row_valid=True,
            validation_errors=[],
        )

    def _test_submit(self, row: MetricsRow, validation: ValidationResult) -> SubmitResult:
        """Submit in test mode. Row must be test-marked."""
        # Enforce test row marker
        test_validation = validate_test_row(row)
        if not test_validation.valid:
            return SubmitResult(
                mode=MODE_TEST_SUBMIT,
                submitted=False,
                status_code=None,
                response_summary=None,
                response_run_id=None,
                output_path=None,
                redacted_endpoint=None,
                error=f"test_submit requires test-marked row: {'; '.join(test_validation.errors)}",
                row_valid=True,
                validation_errors=test_validation.errors,
            )

        endpoint, token, env_error = self._read_env()
        if env_error:
            return SubmitResult(
                mode=MODE_TEST_SUBMIT,
                submitted=False,
                status_code=None,
                response_summary=None,
                response_run_id=None,
                output_path=None,
                redacted_endpoint=None,
                error=env_error,
                row_valid=True,
                validation_errors=[],
            )

        # Idempotency: skip if already posted
        marker = self._markers_root / f"{row.run_id}.posted.json"
        if marker.exists():
            return SubmitResult(
                mode=MODE_TEST_SUBMIT,
                submitted=False,
                status_code=None,
                response_summary="skipped — already posted",
                response_run_id=None,
                output_path=None,
                redacted_endpoint=None,
                error="already posted",
                row_valid=True,
                validation_errors=[],
            )

        # Enforce test-row count limits (taxonomy: posting_modes)
        existing_count = self._count_test_submit_markers()
        if existing_count >= _HARD_TEST_ROW_LIMIT:
            return SubmitResult(
                mode=MODE_TEST_SUBMIT,
                submitted=False,
                status_code=None,
                response_summary=None,
                response_run_id=None,
                output_path=None,
                redacted_endpoint=None,
                error=(
                    f"hard test row limit reached: {existing_count}/{_HARD_TEST_ROW_LIMIT} "
                    f"test rows already posted (hard limit: {_HARD_TEST_ROW_LIMIT})"
                ),
                row_valid=True,
                validation_errors=[],
            )
        if existing_count >= _SOFT_TEST_ROW_LIMIT:
            import logging as _logging
            _logging.getLogger(__name__).warning(
                "test row count (%d/%d) at soft limit — hard limit is %d",
                existing_count,
                _SOFT_TEST_ROW_LIMIT,
                _HARD_TEST_ROW_LIMIT,
            )

        out = self._maybe_export(row)
        return self._do_http(row, endpoint, token, MODE_TEST_SUBMIT, out)

    def _production_submit(
        self,
        row: MetricsRow,
        validation: ValidationResult,
        *,
        owner_approved: bool,
    ) -> SubmitResult:
        """Submit to production. Requires owner_approved=True, env vars, non-test row."""
        if not owner_approved:
            return SubmitResult(
                mode=MODE_PRODUCTION_SUBMIT,
                submitted=False,
                status_code=None,
                response_summary=None,
                response_run_id=None,
                output_path=None,
                redacted_endpoint=None,
                error="production_submit requires owner_approved=True",
                row_valid=True,
                validation_errors=[],
            )

        if row.job_type == "test":
            return SubmitResult(
                mode=MODE_PRODUCTION_SUBMIT,
                submitted=False,
                status_code=None,
                response_summary=None,
                response_run_id=None,
                output_path=None,
                redacted_endpoint=None,
                error="production_submit must not use job_type='test'",
                row_valid=True,
                validation_errors=[],
            )

        endpoint, token, env_error = self._read_env()
        if env_error:
            return SubmitResult(
                mode=MODE_PRODUCTION_SUBMIT,
                submitted=False,
                status_code=None,
                response_summary=None,
                response_run_id=None,
                output_path=None,
                redacted_endpoint=None,
                error=env_error,
                row_valid=True,
                validation_errors=[],
            )

        # Idempotency: skip if already posted
        marker = self._markers_root / f"{row.run_id}.posted.json"
        if marker.exists():
            return SubmitResult(
                mode=MODE_PRODUCTION_SUBMIT,
                submitted=False,
                status_code=None,
                response_summary="skipped — already posted",
                response_run_id=None,
                output_path=None,
                redacted_endpoint=None,
                error="already posted",
                row_valid=True,
                validation_errors=[],
            )

        # Preflight: require matching dry-run file before production submission
        dry_file = self._dry_root / f"{row.run_id}.dry.json"
        if not dry_file.exists():
            return SubmitResult(
                mode=MODE_PRODUCTION_SUBMIT,
                submitted=False,
                status_code=None,
                response_summary=None,
                response_run_id=None,
                output_path=None,
                redacted_endpoint=None,
                error=(
                    f"production_submit requires a matching dry-run file: "
                    f"{dry_file} not found"
                ),
                row_valid=True,
                validation_errors=[],
            )

        out = self._maybe_export(row)
        return self._do_http(row, endpoint, token, MODE_PRODUCTION_SUBMIT, out)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _count_test_submit_markers(self) -> int:
        """Count existing posted markers with mode='test_submit'.

        Returns 0 if the markers directory does not exist or any file cannot be read.
        Corrupt/unreadable files are skipped silently.
        """
        if not self._markers_root.exists():
            return 0
        count = 0
        for path in self._markers_root.glob("*.posted.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if data.get("mode") == MODE_TEST_SUBMIT:
                    count += 1
            except Exception:
                pass  # skip corrupt files
        return count

    def _read_env(self) -> tuple[str, str, str | None]:
        """Read AGENT_METRICS_ENDPOINT and AGENT_METRICS_TOKEN from env.

        Returns (endpoint, token, error_string_or_None).
        """
        endpoint = os.environ.get(ENV_ENDPOINT, "").strip()
        token = os.environ.get(ENV_TOKEN, "").strip()
        if not endpoint:
            return "", "", f"{ENV_ENDPOINT} is not set"
        if not token:
            return endpoint, "", f"{ENV_TOKEN} is not set"
        return endpoint, token, None

    def _do_http(
        self,
        row: MetricsRow,
        endpoint: str,
        token: str,
        mode: str,
        output_path: Path | None,
    ) -> SubmitResult:
        """Execute HTTP POST. Token never appears in result."""
        payload = row_to_dict(row)
        redacted = _redact_endpoint(endpoint)

        http = self._http_client
        if http is None:
            try:
                import requests as _requests
                http = _requests
            except ImportError:
                return SubmitResult(
                    mode=mode,
                    submitted=False,
                    status_code=None,
                    response_summary=None,
                    response_run_id=None,
                    output_path=str(output_path) if output_path else None,
                    redacted_endpoint=redacted,
                    error="requests library required: pip install requests",
                    row_valid=True,
                    validation_errors=[],
                )

        # Token passed as query param (endpoint contract); never stored in result
        url = f"{endpoint}?token={token}"

        try:
            resp = http.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30,
            )
            status = resp.status_code
            body: dict = {}
            try:
                body = resp.json()
                # Prefer human-readable message; fall back to body status code
                if isinstance(body, dict) and body.get("message"):
                    summary = str(body["message"])[:200]
                else:
                    summary = str(body.get("status", body))[:200] if isinstance(body, dict) else f"HTTP {status}"
            except Exception:
                summary = f"HTTP {status}"

            # Extract run_id returned by endpoint (safe — it mirrors our payload run_id)
            response_run_id: str | None = None
            if isinstance(body, dict):
                raw = body.get("run_id")
                if isinstance(raw, str) and raw.strip():
                    response_run_id = raw.strip()

            # Application-level success: HTTP 2xx AND body doesn't signal a non-2xx int status
            body_status = body.get("status") if isinstance(body, dict) else None
            # Only treat as failure if body status is an int outside 2xx range
            app_error = isinstance(body_status, int) and not (200 <= body_status < 300)
            http_ok = 200 <= status < 300
            is_success = http_ok and not app_error

            if is_success:
                self._write_posted_marker(row, mode, status, summary)
            else:
                self._write_failed_record(row, mode, f"HTTP {status}: {summary}")

            return SubmitResult(
                mode=mode,
                submitted=is_success,
                status_code=status,
                response_summary=summary,
                response_run_id=response_run_id,
                output_path=str(output_path) if output_path else None,
                redacted_endpoint=redacted,
                error=None if is_success else f"HTTP {status}: {summary}",
                row_valid=True,
                validation_errors=[],
            )
        except Exception as exc:
            self._write_failed_record(row, mode, str(exc))
            return SubmitResult(
                mode=mode,
                submitted=False,
                status_code=None,
                response_summary=None,
                response_run_id=None,
                output_path=str(output_path) if output_path else None,
                redacted_endpoint=redacted,
                error=str(exc),
                row_valid=True,
                validation_errors=[],
            )

    def _write_posted_marker(
        self,
        row: MetricsRow,
        mode: str,
        status_code: int,
        response_summary: str,
    ) -> None:
        """Write {run_id}.posted.json idempotency marker. No token or endpoint value."""
        import datetime
        self._markers_root.mkdir(parents=True, exist_ok=True)
        marker_path = self._markers_root / f"{row.run_id}.posted.json"
        marker = {
            "run_id": row.run_id,
            "posted_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "mode": mode,
            "status_code": status_code,
            "response_summary": response_summary[:200],
        }
        marker_path.write_text(json.dumps(marker, indent=2), encoding="utf-8")

    def _write_failed_record(self, row: MetricsRow, mode: str, error: str) -> None:
        """Write {run_id}.failed.json on HTTP exception or non-2xx. No token."""
        import datetime
        self._failed_root.mkdir(parents=True, exist_ok=True)
        failed_path = self._failed_root / f"{row.run_id}.failed.json"
        record = {
            "run_id": row.run_id,
            "failed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "mode": mode,
            "error": error[:500],
            "row": row_to_dict(row),
        }
        failed_path.write_text(json.dumps(record, indent=2), encoding="utf-8")

    def _maybe_export(self, row: MetricsRow) -> Path | None:
        """Write export if output_path is set, else return None."""
        if self.output_path:
            return self._write_export(row, self.output_path)
        return None

    def _write_export(self, row: MetricsRow, path: Path) -> Path:
        """Write MetricsRow as JSON to path. Never includes token."""
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = row_to_dict(row)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _redact_endpoint(endpoint: str) -> str:
    """Return endpoint with middle portion masked (token-safe display)."""
    if not endpoint or len(endpoint) < 20:
        return "***"
    # Keep scheme + first 15 chars and last 8 chars, mask middle
    prefix = endpoint[:20]
    suffix = endpoint[-8:]
    return f"{prefix}***{suffix}"


# ---------------------------------------------------------------------------
# Environment variable for production mode
# ---------------------------------------------------------------------------

ENV_PRODUCTION = "AGENT_METRICS_PRODUCTION"


# ---------------------------------------------------------------------------
# Convenience: try production submit (never raises)
# ---------------------------------------------------------------------------

def try_production_submit(row: MetricsRow) -> SubmitResult | None:
    """Attempt production submission if AGENT_METRICS_PRODUCTION=1.

    Returns SubmitResult on attempt, None if production mode is disabled.
    Never raises — all errors captured in SubmitResult.error.
    """
    if os.environ.get(ENV_PRODUCTION, "").strip() != "1":
        return None
    import logging
    _log = logging.getLogger(__name__)
    try:
        submitter = MetricsSubmitter(mode=MODE_PRODUCTION_SUBMIT)
        result = submitter.submit(row, owner_approved=True)
        if result.submitted:
            _log.info("Metrics production submit OK: run_id=%s", row.run_id)
        else:
            _log.warning("Metrics production submit skipped: %s", result.error)
        return result
    except Exception as exc:
        _log.debug("Metrics production submit failed: %s", exc)
        return SubmitResult(
            mode=MODE_PRODUCTION_SUBMIT,
            submitted=False,
            status_code=None,
            response_summary=None,
            response_run_id=None,
            output_path=None,
            redacted_endpoint=None,
            error=str(exc),
            row_valid=False,
            validation_errors=[],
        )
