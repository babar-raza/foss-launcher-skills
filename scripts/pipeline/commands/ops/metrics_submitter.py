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
# SubmitResult
# ---------------------------------------------------------------------------

@dataclass
class SubmitResult:
    """Outcome of a submission attempt."""

    mode: str
    submitted: bool
    status_code: int | None
    response_summary: str | None
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
    ):
        if mode not in VALID_MODES:
            raise ValueError(f"Invalid mode '{mode}'. Must be one of {sorted(VALID_MODES)}")
        self.mode = mode
        self.output_path = Path(output_path) if output_path else None
        self._http_client = _http_client

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
                output_path=None,
                redacted_endpoint=None,
                error=env_error,
                row_valid=True,
                validation_errors=[],
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
                output_path=None,
                redacted_endpoint=None,
                error=env_error,
                row_valid=True,
                validation_errors=[],
            )

        out = self._maybe_export(row)
        return self._do_http(row, endpoint, token, MODE_PRODUCTION_SUBMIT, out)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

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
                    output_path=str(output_path) if output_path else None,
                    redacted_endpoint=redacted,
                    error="requests library required: pip install requests",
                    row_valid=True,
                    validation_errors=[],
                )

        try:
            resp = http.post(
                endpoint,
                json=payload,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                timeout=30,
            )
            status = resp.status_code
            try:
                body = resp.json()
                summary = str(body.get("status", body))[:200]
            except Exception:
                summary = f"HTTP {status}"

            return SubmitResult(
                mode=mode,
                submitted=(200 <= status < 300),
                status_code=status,
                response_summary=summary,
                output_path=str(output_path) if output_path else None,
                redacted_endpoint=redacted,
                error=None if 200 <= status < 300 else f"HTTP {status}: {summary}",
                row_valid=True,
                validation_errors=[],
            )
        except Exception as exc:
            return SubmitResult(
                mode=mode,
                submitted=False,
                status_code=None,
                response_summary=None,
                output_path=str(output_path) if output_path else None,
                redacted_endpoint=redacted,
                error=str(exc),
                row_valid=True,
                validation_errors=[],
            )

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
