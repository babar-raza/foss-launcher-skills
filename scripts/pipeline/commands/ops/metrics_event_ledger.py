# Adapted from aspose.org
"""Local per-run metrics event ledger for agent metrics capture.

Writes MetricsEvent objects as JSONL to reports/metrics/events/{run_id}.jsonl.
Each record is one JSON line (no prompts, completions, or secrets).

Public API
----------
    MetricsEventLedger      — main class
    MetricsEventLedgerError — exception class
    load_events(path)       — read all events from a JSONL file
    validate_event_file(path) — validate a JSONL file, returns ValidationResult

Slice 5 of Agent Metrics Integration (METRICS-PLAN-001 v7.1).

Design invariants
-----------------
- JSONL only; one MetricsEvent per line.
- validate_before_write=True (default): invalid events are rejected before writing.
- Path traversal prevention: run_id must not contain path separators or '..'.
- No prompts, completions, API keys, or private content in any field.
- record_events() is all-or-nothing: either all events are appended or none are.
- flush() / close() are safe to call multiple times (idempotent).
- Thread-safety: NOT guaranteed (single-threaded pipeline use only).
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Iterable

from commands.ops.metrics_schema import (
    MetricsEvent,
    ValidationResult,
    event_to_dict,
    validate_event,
)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class MetricsEventLedgerError(Exception):
    """Raised for ledger-level failures (invalid run_id, path traversal, etc.)."""


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# run_id must be a non-empty string with no path separators or '..'
# Allow UUIDs, slugs, and ISO-style identifiers.
_SAFE_RUN_ID_RE = re.compile(r"^[A-Za-z0-9_\-\.]{1,128}$")

_DEFAULT_ROOT = Path("reports") / "metrics" / "events"


# ---------------------------------------------------------------------------
# MetricsEventLedger
# ---------------------------------------------------------------------------


class MetricsEventLedger:
    """Append-mode JSONL ledger for per-call MetricsEvent objects.

    Parameters
    ----------
    run_id:
        Identifier for this run. Written into the file name.
        Must match ``[A-Za-z0-9_\\-\\.]{1,128}`` (no path separators).
    root_dir:
        Directory under which ``{run_id}.jsonl`` is created.
        Defaults to ``reports/metrics/events/``.
    append:
        If True (default) and a file for ``run_id`` already exists, new
        events are appended.  If False, the file is truncated on first write.
    validate_before_write:
        If True (default), each event is validated via ``validate_event()``
        before it is written.  Invalid events raise ``MetricsEventLedgerError``.
    allow_create_dirs:
        If True (default), ``root_dir`` is created if it does not exist.
    """

    def __init__(
        self,
        run_id: str,
        root_dir: str | Path | None = None,
        *,
        append: bool = True,
        validate_before_write: bool = True,
        allow_create_dirs: bool = True,
    ) -> None:
        self._validate_run_id(run_id)
        self._run_id = run_id
        self._root_dir = Path(root_dir) if root_dir is not None else _DEFAULT_ROOT
        self._append = append
        self._validate_before_write = validate_before_write
        self._allow_create_dirs = allow_create_dirs
        self._file_handle = None
        self._closed = False
        self._first_write_done = False

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def run_id(self) -> str:
        return self._run_id

    @property
    def event_path(self) -> Path:
        """Absolute path to the JSONL file for this run."""
        return self._root_dir / f"{self._run_id}.jsonl"

    # ------------------------------------------------------------------
    # Public write methods
    # ------------------------------------------------------------------

    def record_event(self, event: MetricsEvent) -> None:
        """Validate (if configured) and append one event to the JSONL file.

        Raises
        ------
        MetricsEventLedgerError
            If validation fails or the ledger is closed.
        """
        if self._closed:
            raise MetricsEventLedgerError("Ledger is closed; cannot record events.")

        if self._validate_before_write:
            result = validate_event(event)
            if not result.valid:
                raise MetricsEventLedgerError(
                    f"Invalid MetricsEvent rejected before write: {result.errors}"
                )

        self._ensure_file_open()
        line = json.dumps(event_to_dict(event), separators=(",", ":"))
        self._file_handle.write(line + "\n")
        self._file_handle.flush()

    def record_events(self, events: Iterable[MetricsEvent]) -> int:
        """Validate all events then append them atomically (all-or-nothing).

        Validates every event first; if any fails validation, none are written.

        Returns the number of events written.

        Raises
        ------
        MetricsEventLedgerError
            If any event is invalid or the ledger is closed.
        """
        if self._closed:
            raise MetricsEventLedgerError("Ledger is closed; cannot record events.")

        event_list = list(events)

        if self._validate_before_write:
            errors_found: list[str] = []
            for i, ev in enumerate(event_list):
                result = validate_event(ev)
                if not result.valid:
                    errors_found.append(f"Event[{i}]: {result.errors}")
            if errors_found:
                raise MetricsEventLedgerError(
                    f"record_events() aborted — invalid events detected (none written): "
                    f"{errors_found}"
                )

        if not event_list:
            return 0

        self._ensure_file_open()
        for ev in event_list:
            line = json.dumps(event_to_dict(ev), separators=(",", ":"))
            self._file_handle.write(line + "\n")
        self._file_handle.flush()
        return len(event_list)

    # ------------------------------------------------------------------
    # Public read / utility methods
    # ------------------------------------------------------------------

    def read_events(self) -> list[MetricsEvent]:
        """Read all events written so far.

        Flushes the file handle before reading so in-progress writes are
        included.

        Returns an empty list if the file does not exist.
        """
        self.flush()
        if not self.event_path.exists():
            return []
        return load_events(self.event_path)

    def validate_file(self) -> ValidationResult:
        """Validate all events in the JSONL file.

        Returns a ValidationResult.  Returns valid=True with no errors if the
        file does not exist (empty ledger is valid).
        """
        return validate_event_file(self.event_path)

    def exists(self) -> bool:
        """Return True if the JSONL file exists on disk."""
        return self.event_path.exists()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def flush(self) -> None:
        """Flush the underlying file handle (no-op if not yet opened)."""
        if self._file_handle is not None and not self._file_handle.closed:
            self._file_handle.flush()

    def close(self) -> None:
        """Flush and close the file handle.  Safe to call multiple times."""
        self.flush()
        if self._file_handle is not None and not self._file_handle.closed:
            self._file_handle.close()
        self._closed = True

    def __enter__(self) -> "MetricsEventLedger":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _validate_run_id(self, run_id: str) -> None:
        """Raise MetricsEventLedgerError if run_id is unsafe."""
        if not isinstance(run_id, str) or not run_id:
            raise MetricsEventLedgerError("run_id must be a non-empty string.")
        if not _SAFE_RUN_ID_RE.match(run_id):
            raise MetricsEventLedgerError(
                f"run_id '{run_id}' contains unsafe characters. "
                "Only [A-Za-z0-9_-.] are allowed (max 128 chars)."
            )
        # Belt-and-suspenders: no path separators, no '..'
        if os.sep in run_id or "/" in run_id or "\\" in run_id or ".." in run_id:
            raise MetricsEventLedgerError(
                f"run_id '{run_id}' must not contain path separators or '..'."
            )

    def _ensure_file_open(self) -> None:
        """Open (or create) the JSONL file, creating parent dirs if needed."""
        if self._file_handle is not None and not self._file_handle.closed:
            return

        target = self.event_path

        # Path traversal check: resolved path must be under root_dir
        resolved_root = self._root_dir.resolve()
        try:
            resolved_target = target.resolve()
        except Exception as exc:
            raise MetricsEventLedgerError(
                f"Cannot resolve event path '{target}': {exc}"
            ) from exc

        if not str(resolved_target).startswith(str(resolved_root)):
            raise MetricsEventLedgerError(
                f"Path traversal detected: '{resolved_target}' is outside "
                f"root_dir '{resolved_root}'."
            )

        if self._allow_create_dirs:
            target.parent.mkdir(parents=True, exist_ok=True)
        elif not target.parent.exists():
            raise MetricsEventLedgerError(
                f"Parent directory '{target.parent}' does not exist and "
                "allow_create_dirs=False."
            )

        mode = "a" if self._append else "w"
        self._file_handle = open(target, mode, encoding="utf-8")
        self._first_write_done = True


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def load_events(path: str | Path) -> list[MetricsEvent]:
    """Read all MetricsEvent objects from a JSONL file.

    Skips blank lines.  Raises ``MetricsEventLedgerError`` on malformed JSON
    or unexpected structure.

    Parameters
    ----------
    path:
        Path to the ``.jsonl`` file.

    Returns
    -------
    list[MetricsEvent]
        Ordered list of events as they appear in the file.
    """
    path = Path(path)
    if not path.exists():
        return []

    events: list[MetricsEvent] = []
    with path.open(encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError as exc:
                raise MetricsEventLedgerError(
                    f"Malformed JSON on line {lineno} of '{path}': {exc}"
                ) from exc
            if not isinstance(data, dict):
                raise MetricsEventLedgerError(
                    f"Expected JSON object on line {lineno} of '{path}', "
                    f"got {type(data).__name__}."
                )
            try:
                event = MetricsEvent(**data)
            except TypeError as exc:
                raise MetricsEventLedgerError(
                    f"Cannot reconstruct MetricsEvent from line {lineno}: {exc}"
                ) from exc
            events.append(event)
    return events


def validate_event_file(path: str | Path) -> ValidationResult:
    """Validate every event in a JSONL file.

    Returns a ``ValidationResult`` with ``valid=True`` if the file does not
    exist (empty ledger) or all events pass ``validate_event()``.

    Returns ``valid=False`` with accumulated errors if any event is invalid
    or the file is malformed.
    """
    path = Path(path)
    if not path.exists():
        return ValidationResult(valid=True, errors=[])

    errors: list[str] = []
    lineno = 0

    try:
        with path.open(encoding="utf-8") as fh:
            for lineno, raw in enumerate(fh, start=1):
                line = raw.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError as exc:
                    errors.append(f"Line {lineno}: malformed JSON — {exc}")
                    continue
                if not isinstance(data, dict):
                    errors.append(
                        f"Line {lineno}: expected JSON object, got {type(data).__name__}"
                    )
                    continue
                try:
                    event = MetricsEvent(**data)
                except TypeError as exc:
                    errors.append(f"Line {lineno}: cannot construct MetricsEvent — {exc}")
                    continue
                result = validate_event(event)
                if not result.valid:
                    errors.extend(f"Line {lineno}: {e}" for e in result.errors)
    except OSError as exc:
        errors.append(f"Cannot read '{path}': {exc}")

    return ValidationResult(valid=len(errors) == 0, errors=errors)
