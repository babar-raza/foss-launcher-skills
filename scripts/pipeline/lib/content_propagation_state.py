"""
content_propagation_state.py -- single source of per-product propagation truth.

CONTRACT: scripts/pipeline/lib/content_propagation_state.py
  purpose: Knowledge refreshes and content propagation are different events. A product's
           knowledge can be current (knowledge_sha == upstream HEAD) while no page was ever
           reconciled against it, and a knowledge-only commit must never make a product look
           "done". This module is the one durable record that keeps the two apart:
             - DRIFT fields (what upstream looks like now) are written by the fleet drift
               classifier through record_drift();
             - PROPAGATION fields (what content has provably been reconciled to) are written
               by exactly one caller, the capability-surface gate, through
               record_propagation().
  durability: data/content_propagation_state.json (git-tracked, created on first write).
  schema:  {"schema_version": 1, "products": {"<family>/<platform>": {...}}}
           Per product: upstream_head, knowledge_sha, content_propagated_sha,
           content_propagated_knowledge_commit, local_only, status, tier, release_state,
           ahead_by, files_seen, source_files, api_surface_touched, truncated,
           ground_truth_tier, baseline_assumed, capability_units, gate_verdict, volatile.
           `volatile` (observed_at, last_issue_number, ...) holds wall-clock / bookkeeping
           values; canonical_for_compare() strips it so two runs over identical upstream
           truth compare equal.
  status:  UNRECORDED       no content_propagated_sha was ever recorded
           DRIFTED          upstream_head != content_propagated_sha, OR the record is not backed
                            by a gate PASS (a hand-edited sha is never "done")
           PROPAGATED_LOCAL upstream_head == content_propagated_sha, gate_verdict == "PASS",
                            (knowledge commit or capability units recorded), local_only
           PROPAGATED       the same, pushed
           The status field is DERIVED: it is recomputed on every read and write, so a forged
           stored value is ignored.
  single writer (enforced here, not only by convention): record_propagation() rejects a
           non-"PASS" verdict, any pending disposition cell, a sha that is not 40 hex, a record
           with neither a knowledge commit nor capability units, and (monotonic) any attempt to
           lower or replace a recorded sha with one that is not a descendant -- decided by a
           caller-supplied predicate, else "equals the observed upstream head" -- unless an
           explicit non-blank force_reason is given (logged + kept in volatile.force_overrides).
  concurrency: FileLock (lib/advisory_lock.py) around every read-modify-write; the file is
           replaced atomically (temp file + os.replace) so readers never see a torn file.
  idempotent: JSON is deterministic (indent 2, sort_keys, LF, trailing newline); re-recording
           identical data yields a byte-identical file.
  corrupt file: reads tolerate it (return empty); writes REFUSE (StateCorrupt) rather than
           silently destroying whatever was there.
  windows races: os.replace, a read, or the lock-file create can raise PermissionError (WinError
           5/32, or "create while delete-pending") when another thread/process touches the file at
           that instant. Every such step is retried with bounded, jittered exponential backoff
           (total sleep <= 10s, injectable via configure()); when the budget is exhausted a clear
           StateWriteError / StateReadError is raised -- data is never lost silently, the temp
           file is removed, and the lock is released. Non-transient errors are not retried.

Usage::

    import content_propagation_state as cps
    cps.record_drift("<f>", "<p>", upstream_head=sha, knowledge_sha=ksha, tier="SOURCE",
                     release_state="released", ahead_by=3, files_seen=12, source_files=4,
                     api_surface_touched=False, truncated=False, ground_truth_tier="GT-2",
                     observed_at="2026-10-07T00:00:00Z")
    cps.read_state("<f>", "<p>")["status"]     # -> "UNRECORDED" | "DRIFTED" | ...
"""
from __future__ import annotations

import copy
import json
import logging
import os
import random
import re
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable

_LIB_DIR = Path(__file__).resolve().parent
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))
_PIPELINE_DIR = _LIB_DIR.parent
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))
_REPO_ROOT = Path(__file__).resolve().parents[3]  # lib/ -> pipeline/ -> scripts/ -> repo root

from advisory_lock import FileLock, LockTimeout  # noqa: E402

SCHEMA_VERSION = 1

_DEFAULT_STATE_PATH = _REPO_ROOT / "data" / "content_propagation_state.json"
_STATE_PATH = _DEFAULT_STATE_PATH
_LOCK_TIMEOUT = 60.0
_LOCK_POLL_INTERVAL = 0.02

# Retry seams (configure() overrides them; None restores the real ones).
_RETRY_BUDGET_DEFAULT = 10.0  # total seconds of backoff sleep before giving up
_RETRY_BUDGET = _RETRY_BUDGET_DEFAULT
_replace = os.replace
_sleep = time.sleep
_jitter = random.random
_read_bytes = lambda p: Path(p).read_bytes()  # noqa: E731
_tmp_counter = 0
_tmp_lock = threading.Lock()
_cfg_lock_acquire = None  # optional seam: (FileLock) -> None replaces lock.acquire()
_is_descendant = None  # optional default ancestor predicate: (old_sha, new_sha) -> bool | None
_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
_log = logging.getLogger(__name__)

STATUSES = ("UNRECORDED", "DRIFTED", "PROPAGATED_LOCAL", "PROPAGATED")
TIERS = ("NO_CHANGE", "NON_SOURCE", "SOURCE", "API_TOUCHED", "UNKNOWN")
RELEASE_STATES = ("released", "unreleased_main", "unknown")
GROUND_TRUTH_TIERS = ("GT-1", "GT-2")
DISPOSITION_SURFACES = ("reference", "docs", "kb", "blog", "products")
DISPOSITION_STATUSES = ("pending", "satisfied", "none_justified")

# Fields owned by record_propagation(); record_drift() must never touch them.
PROPAGATION_FIELDS = (
    "content_propagated_sha",
    "content_propagated_knowledge_commit",
    "local_only",
    "capability_units",
    "gate_verdict",
)


class StateLockTimeout(Exception):
    """Raised when the state-file lock could not be acquired in time."""


class StateCorrupt(Exception):
    """Raised when a WRITE finds an unparseable state file (never overwritten silently)."""


class StateWriteError(Exception):
    """A write step (lock, read-modify-write read, temp write, replace) failed for good: either a
    non-transient OS error, or a transient PermissionError that outlasted the retry budget. The
    state file is left exactly as it was."""


class StateReadError(Exception):
    """A read of the state file kept failing past the retry budget."""


class PropagationRegression(ValueError):
    """record_propagation() would lower or replace a recorded sha with one that is not a
    descendant of it (and no explicit force_reason was given)."""


def configure(state_path: "Path | str | None" = None, *, replace=None, sleep=None, jitter=None,
              read_bytes=None, retry_budget: "float | None" = None, is_descendant=None, lock_acquire=None) -> None:
    """Point the module at a different state file and/or inject the retry / ancestor seams
    (tests). Every argument left None restores its real default (configure(None) = full reset)."""
    global _STATE_PATH, _replace, _sleep, _jitter, _read_bytes, _RETRY_BUDGET, _is_descendant, _cfg_lock_acquire
    _is_descendant = is_descendant
    _cfg_lock_acquire = lock_acquire
    _STATE_PATH = Path(state_path) if state_path is not None else _DEFAULT_STATE_PATH
    _replace = replace or os.replace
    _sleep = sleep or time.sleep
    _jitter = jitter or random.random
    _read_bytes = read_bytes or (lambda p: Path(p).read_bytes())
    _RETRY_BUDGET = retry_budget if retry_budget is not None else _RETRY_BUDGET_DEFAULT


def state_path() -> Path:
    return _STATE_PATH


def _lock_path() -> Path:
    return _STATE_PATH.with_suffix(_STATE_PATH.suffix + ".lock")


def _product_key(family: str, platform: str) -> str:
    return f"{family}/{platform}"


def _empty() -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "products": {}}


def _is_transient(exc: BaseException) -> bool:
    return isinstance(exc, PermissionError) or getattr(exc, "winerror", None) in (5, 32)


def _with_retry(op, error_cls, what: str, *, also_transient: "tuple[type[BaseException], ...]" = ()):
    """Run op(); retry transient OS errors (PermissionError / WinError 5, 32) with bounded,
    jittered exponential backoff. Budget exhausted or non-transient error -> error_cls."""
    waited, attempt = 0.0, 0
    while True:
        try:
            return op()
        except OSError as exc:
            if not (_is_transient(exc) or isinstance(exc, also_transient)):
                raise error_cls(f"{what}: {exc}") from exc
            delay = min(0.02 * (2 ** attempt), 0.5) * (0.5 + _jitter() / 2)
            if waited + delay > _RETRY_BUDGET:
                raise error_cls(
                    f"{what}: still failing after {attempt} retries (~{waited:.1f}s of backoff): {exc}") from exc
            _sleep(delay)
            waited += delay
            attempt += 1


def _read_raw() -> "bytes | None":
    """Current file bytes (None if absent), retrying transient read errors."""
    if not _STATE_PATH.exists():
        return None
    try:
        # FileNotFoundError after exists() is a replace race, not a missing file: retry it too.
        return _with_retry(lambda: _read_bytes(_STATE_PATH), StateReadError,
                           f"read {_STATE_PATH}", also_transient=(FileNotFoundError,))
    except StateReadError:
        if not _STATE_PATH.exists():
            return None
        raise


def _parse(raw: "bytes | None", *, strict: bool) -> dict[str, Any]:
    if raw is None:
        return _empty()
    try:
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("products"), dict):
            raise ValueError("state file is not {schema_version, products}")
        return data
    except (json.JSONDecodeError, ValueError) as exc:  # UnicodeDecodeError is a ValueError
        if strict:
            raise StateCorrupt(f"{_STATE_PATH}: {exc}") from exc
        return _empty()


def _load(*, strict: bool) -> dict[str, Any]:
    return _parse(_read_raw(), strict=strict)


def _dump(state: dict[str, Any]) -> bytes:
    return (json.dumps(state, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _write_atomic(data: bytes) -> None:
    """Unique temp file + retried os.replace. On any failure the temp file is removed and the
    original file is untouched."""
    global _tmp_counter
    with _tmp_lock:
        _tmp_counter += 1
        n = _tmp_counter
    tmp = _STATE_PATH.with_name(f"{_STATE_PATH.name}.{os.getpid()}.{threading.get_ident()}.{n}.tmp")
    try:
        try:
            _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_bytes(data)
        except OSError as exc:
            raise StateWriteError(f"write temp file {tmp}: {exc}") from exc
        _with_retry(lambda: _replace(str(tmp), str(_STATE_PATH)), StateWriteError,
                    f"replace {_STATE_PATH}")
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def _acquire(lock: FileLock) -> None:
    try:
        # create-while-delete-pending surfaces as PermissionError on Windows: retry it.
        _with_retry((lambda: _cfg_lock_acquire(lock)) if _cfg_lock_acquire else lock.acquire,
                    StateWriteError, f"acquire lock {lock.path}")
    except LockTimeout as exc:
        raise StateLockTimeout(str(exc)) from exc


def _new_record(family: str, platform: str) -> dict[str, Any]:
    return {
        "family": family,
        "platform": platform,
        "upstream_head": None,
        "knowledge_sha": None,
        "content_propagated_sha": None,
        "content_propagated_knowledge_commit": None,
        "local_only": False,
        "status": "UNRECORDED",
        "tier": "UNKNOWN",
        "tier_reason": None,
        "release_state": "unknown",
        "release_state_reason": None,
        "ahead_by": None,
        "files_seen": 0,
        "source_files": 0,
        "api_surface_touched": False,
        "truncated": False,
        "ground_truth_tier": "GT-2",
        "baseline_assumed": False,
        "capability_units": [],
        "gate_verdict": None,
        "volatile": {},
    }


def _mutate(family: str, platform: str, fn) -> dict[str, Any]:
    """Read-modify-write one product record under the exclusive lock; returns the new record."""
    lock = FileLock(_lock_path(), timeout=_LOCK_TIMEOUT, poll=_LOCK_POLL_INTERVAL)
    _acquire(lock)
    try:
        try:
            raw = _read_raw()
        except StateReadError as exc:
            raise StateWriteError(f"cannot read current state before writing: {exc}") from exc
        state = _parse(raw, strict=True)
        key = _product_key(family, platform)
        rec = state["products"].get(key) or _new_record(family, platform)
        fn(rec)
        rec["status"] = compute_status(rec)
        state["schema_version"] = SCHEMA_VERSION
        state["products"][key] = rec
        new_bytes = _dump(state)
        if raw != new_bytes:  # no spurious rewrite (no mtime churn, no tmp-file window)
            _write_atomic(new_bytes)
        return rec
    finally:
        lock.release()


# ── public read API ───────────────────────────────────────────────────────────

def _rederive(state: dict[str, Any]) -> dict[str, Any]:
    for rec in state["products"].values():
        if isinstance(rec, dict):
            rec["status"] = compute_status(rec)  # never trust a stored (possibly hand-edited) status
    return state


def read_all() -> dict[str, Any]:
    """Return the full state file: {"schema_version": 1, "products": {key: record}}."""
    return _rederive(_load(strict=False))


def read_state(family: str, platform: str) -> "dict[str, Any] | None":
    """Return one product's record, or None if never recorded."""
    return _rederive(_load(strict=False))["products"].get(_product_key(family, platform))


def compute_status(rec: "dict[str, Any]") -> str:
    """Derive the propagation status from a record (pure function).

    PROPAGATED / PROPAGATED_LOCAL require ALL of: content_propagated_sha == upstream_head,
    gate_verdict == "PASS", and (a knowledge commit or a non-empty capability-unit set). A record
    whose sha merely matches (hand edit, forged status) is DRIFTED, never propagated."""
    sha = rec.get("content_propagated_sha")
    if not sha:
        return "UNRECORDED"
    verified = rec.get("gate_verdict") == "PASS" and bool(
        rec.get("content_propagated_knowledge_commit") or rec.get("capability_units"))
    if rec.get("upstream_head") != sha or not verified:
        return "DRIFTED"
    return "PROPAGATED_LOCAL" if rec.get("local_only") else "PROPAGATED"


def canonical_for_compare(state: Any) -> Any:
    """Deep copy of `state` with every `volatile` key stripped (recursively), so two runs over
    identical upstream truth compare equal regardless of timestamps/bookkeeping."""
    if isinstance(state, dict):
        return {k: canonical_for_compare(v) for k, v in state.items() if k != "volatile"}
    if isinstance(state, list):
        return [canonical_for_compare(v) for v in state]
    return copy.deepcopy(state)


# ── public write API ──────────────────────────────────────────────────────────

def record_drift(
    family: str,
    platform: str,
    *,
    upstream_head: "str | None",
    knowledge_sha: "str | None",
    tier: str,
    release_state: str,
    ahead_by: "int | None",
    files_seen: int,
    source_files: int,
    api_surface_touched: bool,
    truncated: bool,
    ground_truth_tier: str,
    baseline_assumed: bool = False,
    observed_at: "str | None" = None,
    tier_reason: "str | None" = None,
    release_state_reason: "str | None" = None,
    volatile_extra: "dict[str, Any] | None" = None,
) -> dict[str, Any]:
    """Record what upstream looks like NOW. Writes drift fields ONLY.

    Never touches content_propagated_sha / content_propagated_knowledge_commit / local_only /
    capability_units / gate_verdict: a drift observation (or a knowledge refresh) can change a
    product's status to DRIFTED but can never make it PROPAGATED.
    """
    if tier not in TIERS:
        raise ValueError(f"tier must be one of {TIERS}, got {tier!r}")
    if release_state not in RELEASE_STATES:
        raise ValueError(f"release_state must be one of {RELEASE_STATES}, got {release_state!r}")
    if ground_truth_tier not in GROUND_TRUTH_TIERS:
        raise ValueError(f"ground_truth_tier must be one of {GROUND_TRUTH_TIERS}, got {ground_truth_tier!r}")

    def apply(rec: dict[str, Any]) -> None:
        rec["upstream_head"] = upstream_head
        rec["knowledge_sha"] = knowledge_sha
        rec["tier"] = tier
        rec["release_state"] = release_state
        rec["ahead_by"] = ahead_by
        rec["files_seen"] = int(files_seen)
        rec["source_files"] = int(source_files)
        rec["api_surface_touched"] = bool(api_surface_touched)
        rec["truncated"] = bool(truncated)
        rec["ground_truth_tier"] = ground_truth_tier
        rec["baseline_assumed"] = bool(baseline_assumed)
        rec["tier_reason"] = tier_reason
        rec["release_state_reason"] = release_state_reason
        vol = rec.setdefault("volatile", {})
        if observed_at is not None:
            vol["observed_at"] = observed_at
        if volatile_extra:
            vol.update(volatile_extra)

    return _mutate(family, platform, apply)


def _normalize_units(units: "list[dict[str, Any]] | None") -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for unit in units or []:
        if not isinstance(unit, dict) or not unit.get("id"):
            raise ValueError(f"capability unit needs an 'id': {unit!r}")
        disp_in = unit.get("dispositions") or {}
        disp_out: dict[str, Any] = {}
        for surface, d in disp_in.items():
            if surface not in DISPOSITION_SURFACES:
                raise ValueError(f"unknown disposition surface {surface!r}; expected {DISPOSITION_SURFACES}")
            status = (d or {}).get("status")
            if status not in DISPOSITION_STATUSES:
                raise ValueError(f"disposition status must be one of {DISPOSITION_STATUSES}, got {status!r}")
            disp_out[surface] = {
                "status": status,
                "evidence_paths": sorted({str(p) for p in (d.get("evidence_paths") or [])}),
            }
        out.append({
            "id": str(unit["id"]),
            "symbols": sorted({str(s) for s in (unit.get("symbols") or [])}),
            "availability": unit.get("availability"),
            "dispositions": disp_out,
        })
    return sorted(out, key=lambda u: u["id"])


def record_propagation(
    family: str,
    platform: str,
    *,
    content_propagated_sha: str,
    content_propagated_knowledge_commit: "str | None",
    local_only: bool,
    capability_units: "list[dict[str, Any]] | None",
    gate_verdict: "str | None",
    is_descendant: "Callable[[str, str], bool | None] | None" = None,
    force_reason: "str | None" = None,
) -> dict[str, Any]:
    """The ONLY writer of content_propagated_* (and capability_units / gate_verdict).

    MUST be called only by scripts/pipeline/commands/.../capability_surface_gate.py, after the
    gate has verified that every capability unit has a recorded disposition. No other caller
    may mark a product propagated: a refresh, a drift scan, a hand edit or a release trigger
    that wrote content_propagated_sha would be exactly the silent "done" this module exists to
    prevent. A source-scan test (test_content_propagation_state.py) enforces the allow-list, and
    the invariants below are enforced HERE so a direct call cannot bypass the gate's checks:

      * gate_verdict must be exactly "PASS";
      * no disposition cell may be "pending";
      * content_propagated_sha must be 40 hex (stored lowercase);
      * a knowledge commit or a non-empty capability-unit set must be recorded;
      * monotonic: replacing a recorded, different sha is refused (PropagationRegression) unless
        is_descendant(old, new) is True (per-call or configure()d predicate; with none, the new
        sha must equal the observed upstream_head) or a non-blank force_reason is given, which
        is logged and appended to volatile.force_overrides.
    """
    if gate_verdict != "PASS":
        raise ValueError(f"gate_verdict must be 'PASS' to record propagation, got {gate_verdict!r}")
    if not isinstance(content_propagated_sha, str) or not _SHA_RE.fullmatch(content_propagated_sha):
        raise ValueError(f"content_propagated_sha must be a 40-hex commit sha, got {content_propagated_sha!r}")
    new_sha = content_propagated_sha.lower()
    units = _normalize_units(capability_units)
    for unit in units:
        for surface, disp in unit["dispositions"].items():
            if disp["status"] == "pending":
                raise ValueError(f"capability unit {unit['id']!r} still has a pending {surface!r} disposition")
    if not content_propagated_knowledge_commit and not units:
        raise ValueError("record_propagation needs a knowledge commit or a non-empty capability-unit set")
    predicate = is_descendant or _is_descendant
    reason = (force_reason or "").strip()

    def apply(rec: dict[str, Any]) -> None:
        old = rec.get("content_propagated_sha")
        if old and old != new_sha:
            if predicate is not None:
                ok = predicate(old, new_sha) is True
            else:
                ok = rec.get("upstream_head") == new_sha
            if not ok:
                if not reason:
                    raise PropagationRegression(
                        f"refusing to replace recorded propagation sha {old} with {new_sha}: not shown to be a "
                        f"descendant (pass force_reason to override deliberately)")
                _log.warning("FORCED propagation sha change %s -> %s: %s", old, new_sha, reason)
                rec.setdefault("volatile", {}).setdefault("force_overrides", []).append(
                    {"from": old, "to": new_sha, "reason": reason})
        rec["content_propagated_sha"] = new_sha
        rec["content_propagated_knowledge_commit"] = content_propagated_knowledge_commit
        rec["local_only"] = bool(local_only)
        rec["capability_units"] = units
        rec["gate_verdict"] = gate_verdict

    return _mutate(family, platform, apply)
