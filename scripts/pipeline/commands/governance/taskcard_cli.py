"""
taskcard_cli.py — SEO-LOOP-TASKCARD-CLI (MT064-2026-09-05-SEO-KEYWORD-UTILIZATION-ENGINE).

CONTRACT: scripts/pipeline/commands/governance/taskcard_cli.py
  purpose: TaskcardStore (scripts/pipeline/lib/taskcard_store.py) is library-only;
           its own docstring names ad hoc `python -c` snippets over it as the
           failure mode it replaced. This is the thin argparse CLI a /loop-driven
           mission uses so every ledger write goes through one reviewed surface
           instead of an inline snippet per call site. It adds nothing to
           TaskcardStore's concurrency guarantees (lock + row-level CAS) or
           schema validation (schema_validators.validate_taskcard_record) —
           it is a command-line skin over both.
  inputs:  reports/plan_state/{mission_id}/taskcards.jsonl (via TaskcardStore)
  outputs: same file (append-only)
  subcommands (exactly the seven named by the governing plan's
           SEO-LOOP-TASKCARD-CLI row — do not add more without updating that
           row): latest, ready, seed, claim, advance, release, recover-expired.
  identity: `recorded_by` defaults to session_identity.resolve_sanitized() when
           --session-id is not given, matching every other governance CLI in
           this tree (mission_authority.py, override_manager.py).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
_LIB_DIR = _HERE.parents[1] / "lib"  # governance -> commands -> pipeline, then /lib
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from taskcard_store import (  # noqa: E402
    TaskcardStore,
    TaskcardAlreadyExistsError,
    TaskcardCASError,
    TaskcardLockTimeout,
    TaskcardNotFoundError,
)

try:
    from session_identity import resolve_sanitized as _resolve_session_identity  # noqa: E402
except Exception:  # pragma: no cover - identity module unavailable in some test contexts
    _resolve_session_identity = None

_REPO_ROOT = _HERE.parents[3]  # commands/governance -> commands -> pipeline -> scripts -> repo root

_TERMINAL_STATUSES = {"CLOSED", "SUPERSEDED", "OUT_OF_SCOPE"}
_ELIGIBLE_BASE_STATUSES = {"READY", "TODO"}
_PRIORITY_RANK = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
_EXTERNAL_GATE_TIMEOUT_SECONDS = 20


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _now_iso() -> str:
    return _now().isoformat().replace("+00:00", "Z")


def _parse_iso(value: "str | None") -> "datetime | None":
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _resolve_recorded_by(session_id: "str | None") -> str:
    if session_id:
        return session_id
    if _resolve_session_identity is not None:
        try:
            return _resolve_session_identity()
        except Exception:
            pass
    raise SystemExit("taskcard_cli: --session-id is required (identity could not be resolved)")


def _store(args: argparse.Namespace) -> TaskcardStore:
    repo_root = Path(args.repo_root) if getattr(args, "repo_root", None) else _REPO_ROOT
    return TaskcardStore(args.mission, repo_root=repo_root)


def _print_json(obj: Any) -> None:
    print(json.dumps(obj, indent=2, sort_keys=True, default=str))


def _parse_field(existing: dict, key: str, raw_value: str) -> Any:
    """`--field key=value`. A value of the form '+N' means increment the
    field's existing numeric value (default 0) by N — used for
    rework_count=+1. Otherwise the value is parsed as JSON when possible
    (so lists/ints/bools round-trip), falling back to a plain string."""
    if raw_value.startswith("+") and raw_value[1:].isdigit():
        return int(existing.get(key, 0) or 0) + int(raw_value[1:])
    try:
        return json.loads(raw_value)
    except json.JSONDecodeError:
        return raw_value


def _apply_fields(existing: dict, field_args: "list[str] | None") -> dict:
    out: dict[str, Any] = {}
    for item in field_args or []:
        if "=" not in item:
            raise SystemExit(f"taskcard_cli: --field must be key=value, got {item!r}")
        key, _, raw_value = item.partition("=")
        out[key] = _parse_field(existing, key, raw_value)
    return out


# ── latest ───────────────────────────────────────────────────────────────

def cmd_latest(args: argparse.Namespace) -> int:
    store = _store(args)
    latest = store.read_latest()
    if args.task:
        row = latest.get(args.task)
        if row is None:
            print(f"taskcard_cli: no row for task_id={args.task!r}", file=sys.stderr)
            return 1
        _print_json(row)
        return 0
    if args.json:
        _print_json(latest)
    else:
        for task_id in sorted(latest):
            row = latest[task_id]
            print(f"{task_id}\t{row.get('status')}\t{row.get('recorded_at')}\t{row.get('recorded_by')}")
    return 0


# ── seed ─────────────────────────────────────────────────────────────────

def cmd_seed(args: argparse.Namespace) -> int:
    store = _store(args)
    recorded_by = _resolve_recorded_by(args.session_id)
    rows = json.loads(Path(args.from_json).read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise SystemExit("taskcard_cli seed: --from-json must contain a JSON array of row objects")

    existing = store.read_latest()
    seeded, skipped = [], []
    for row in rows:
        task_id = row.get("task_id")
        if not task_id:
            raise SystemExit(f"taskcard_cli seed: row missing task_id: {row!r}")
        if task_id in existing and not args.force:
            skipped.append(task_id)
            continue
        record = dict(row)
        record.setdefault("mission_id", args.mission)
        record.setdefault("recorded_at", _now_iso())
        record.setdefault("recorded_by", recorded_by)
        record.setdefault("evidence_refs", [])
        # H2 (2026-09-11): expect_absent=not force re-checks freshly under
        # the lock rather than trusting the pre-loop `existing` snapshot
        # above, closing a real TOCTOU race between two concurrent seed
        # calls for the same brand-new task_id. --force intentionally keeps
        # the old blind-append behavior (expect_absent=False).
        try:
            store.append(record, expect_absent=not args.force)
        except TaskcardAlreadyExistsError:
            skipped.append(task_id)
            continue
        seeded.append(task_id)

    _print_json({"seeded": seeded, "skipped_existing": skipped})
    return 0


# ── claim ────────────────────────────────────────────────────────────────

def cmd_claim(args: argparse.Namespace) -> int:
    store = _store(args)
    recorded_by = _resolve_recorded_by(args.session_id)
    claimed_at = _now()
    expires_at = claimed_at.timestamp() + args.lease_minutes * 60
    expires_iso = datetime.fromtimestamp(expires_at, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    try:
        record = store.update_taskcard_status(
            args.task,
            expected_status=args.expected,
            new_status="IN_PROGRESS",
            recorded_by=recorded_by,
            evidence_refs=[],
            claim_id=args.run_id,
            worker_id=recorded_by,
            claimed_at=_now_iso(),
            claim_expires_at=expires_iso,
        )
    except TaskcardCASError as exc:
        _print_json({"outcome": "CONTENDED", "task_id": args.task, "detail": str(exc)})
        return 3
    except TaskcardNotFoundError as exc:
        print(f"taskcard_cli claim: {exc}", file=sys.stderr)
        return 4
    except TaskcardLockTimeout as exc:
        print(f"taskcard_cli claim: lock timeout: {exc}", file=sys.stderr)
        return 5
    _print_json(record)
    return 0


# ── advance ──────────────────────────────────────────────────────────────

def cmd_advance(args: argparse.Namespace) -> int:
    store = _store(args)
    recorded_by = _resolve_recorded_by(args.session_id)
    existing = store.get(args.task) or {}
    extra = _apply_fields(existing, args.field)
    try:
        record = store.update_taskcard_status(
            args.task,
            expected_status=args.expected,
            new_status=args.to,
            recorded_by=recorded_by,
            evidence_refs=list(args.evidence) if args.evidence else None,
            **extra,
        )
    except TaskcardCASError as exc:
        _print_json({"outcome": "CONTENDED", "task_id": args.task, "detail": str(exc)})
        return 3
    except TaskcardNotFoundError as exc:
        print(f"taskcard_cli advance: {exc}", file=sys.stderr)
        return 4
    except ValueError as exc:
        print(f"taskcard_cli advance: {exc}", file=sys.stderr)
        return 2
    _print_json(record)
    return 0


# ── release ──────────────────────────────────────────────────────────────

def cmd_release(args: argparse.Namespace) -> int:
    store = _store(args)
    recorded_by = _resolve_recorded_by(args.session_id)
    existing = store.get(args.task)
    if existing is None:
        print(f"taskcard_cli release: no existing row for task_id={args.task!r}", file=sys.stderr)
        return 4
    expected = args.expected or existing.get("status")
    extra = _apply_fields(existing, args.field)
    extra["release_reason"] = args.reason
    try:
        record = store.update_taskcard_status(
            args.task,
            expected_status=expected,
            new_status=args.to,
            recorded_by=recorded_by,
            evidence_refs=list(args.evidence) if args.evidence else None,
            **extra,
        )
    except TaskcardCASError as exc:
        _print_json({"outcome": "CONTENDED", "task_id": args.task, "detail": str(exc)})
        return 3
    except ValueError as exc:
        print(f"taskcard_cli release: {exc}", file=sys.stderr)
        return 2
    _print_json(record)
    return 0


# ── recover-expired ──────────────────────────────────────────────────────

def cmd_recover_expired(args: argparse.Namespace) -> int:
    store = _store(args)
    recorded_by = _resolve_recorded_by(args.session_id)
    now = _now()
    recovered = []
    for task_id, row in store.read_latest().items():
        if row.get("status") != "IN_PROGRESS":
            continue
        expires = _parse_iso(row.get("claim_expires_at"))
        if expires is None or expires >= now:
            continue  # no lease info, or not yet expired — never touch a live foreign claim
        try:
            store.update_taskcard_status(
                task_id,
                expected_status="IN_PROGRESS",
                new_status="READY",
                recorded_by=recorded_by,
                evidence_refs=[],
                recovered_from_claim=row.get("claim_id"),
                recovered_from_worker=row.get("worker_id"),
            )
            recovered.append(task_id)
        except TaskcardCASError:
            continue  # someone else already advanced it between read and write — fine
    _print_json({"recovered": recovered})
    return 0


# ── ready (selection rule) ───────────────────────────────────────────────

def _dependencies_closed(row: dict, latest: dict) -> bool:
    # TC-PSD-HRD-9N-8: a dependency resolved to any _TERMINAL_STATUSES
    # member (CLOSED, SUPERSEDED, OUT_OF_SCOPE) is satisfied -- not just
    # the literal "CLOSED" string. Before this fix, a dependent task was
    # permanently hidden from `ready`'s listing the moment its dependency
    # resolved to OUT_OF_SCOPE/SUPERSEDED, even though this same file's
    # own _TERMINAL_STATUSES set already models both as valid, non-
    # blocking terminal outcomes (line 372 already uses it correctly for
    # self-dependency/cycle filtering -- this function just never did).
    deps = row.get("dependencies") or []
    for dep in deps:
        dep_row = latest.get(dep)
        if dep_row is None or dep_row.get("status") not in _TERMINAL_STATUSES:
            return False
    return True


def _external_gate_ready(row: dict) -> "bool | None":
    """None = no gate (not applicable); True/False = gate's resume_check result."""
    gate = row.get("external_gate")
    if not gate:
        return None
    resume_check = gate.get("resume_check") if isinstance(gate, dict) else None
    if not resume_check:
        return False
    try:
        result = subprocess.run(
            resume_check, shell=True, cwd=_REPO_ROOT,
            capture_output=True, timeout=_EXTERNAL_GATE_TIMEOUT_SECONDS,
        )
        return result.returncode == 0
    except Exception:
        return False


def _other_active_session_touched(repo_root: Path, session_id: str) -> "set[str]":
    touched: set[str] = set()
    state_dir = repo_root / "reports" / "session-state"
    if not state_dir.is_dir():
        return touched
    for path in state_dir.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        if data.get("session_id") == session_id:
            continue
        if data.get("status") != "ACTIVE":
            continue
        for f in data.get("touched_files") or []:
            touched.add(str(f).replace("\\", "/"))
    return touched


def _paths_conflict(allowed_paths: "list[str] | None", touched: "set[str]") -> bool:
    if not allowed_paths or not touched:
        return False
    prefixes = []
    for p in allowed_paths:
        p = str(p).replace("\\", "/")
        prefix = p.split("*", 1)[0]
        prefixes.append(prefix)
    for t in touched:
        for prefix in prefixes:
            if prefix and (t.startswith(prefix) or prefix.startswith(t)):
                return True
    return False


def _non_terminal_dependent_count(task_id: str, latest: dict) -> int:
    count = 0
    for other_id, other_row in latest.items():
        if task_id in (other_row.get("dependencies") or []) and other_row.get("status") not in _TERMINAL_STATUSES:
            count += 1
    return count


def cmd_ready(args: argparse.Namespace) -> int:
    store = _store(args)
    session_id = _resolve_recorded_by(args.session_id)
    latest = store.read_latest()
    now = _now()
    touched_elsewhere = _other_active_session_touched(store.repo_root or _REPO_ROOT, session_id)

    candidates = []
    for task_id, row in latest.items():
        status = row.get("status")
        reasons = []

        is_own_resume = status == "IN_PROGRESS" and row.get("worker_id") == session_id
        rework_ok = status == "REWORK_REQUIRED" and int(row.get("rework_count", 0) or 0) < 2
        base_ok = status in _ELIGIBLE_BASE_STATUSES

        if not (is_own_resume or rework_ok or base_ok):
            reasons.append(f"status={status} not selectable")

        if not _dependencies_closed(row, latest):
            open_deps = [d for d in (row.get("dependencies") or [])
                         if (latest.get(d) or {}).get("status") not in _TERMINAL_STATUSES]
            reasons.append(f"dependencies not CLOSED/terminal: {open_deps}")

        not_before = _parse_iso(row.get("not_before"))
        if not_before is not None and not_before > now:
            reasons.append(f"not_before={row.get('not_before')} in the future")

        gate_result = _external_gate_ready(row)
        if gate_result is False:
            reasons.append("external_gate.resume_check not currently true")

        if _paths_conflict(row.get("allowed_paths"), touched_elsewhere):
            reasons.append("allowed_paths overlap another active session's touched_files")

        eligible = not reasons
        priority_rank = _PRIORITY_RANK.get(row.get("priority"), 9)
        wave = row.get("wave", 99)
        sort_key = (
            0 if is_own_resume else 1,
            priority_rank,
            wave,
            -_non_terminal_dependent_count(task_id, latest),
            task_id,
        )
        candidates.append({
            "task_id": task_id,
            "status": status,
            "eligible": eligible,
            "exclusion_reasons": reasons,
            "sort_key": list(sort_key),
        })

    candidates.sort(key=lambda c: c["sort_key"])
    result = {"eligible": [c for c in candidates if c["eligible"]], "all": candidates}
    _print_json(result)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Thin CLI over TaskcardStore for one mission's taskcards.jsonl")
    p.add_argument("--mission", required=True, help="mission_id, e.g. MT064-2026-09-05-SEO-KEYWORD-UTILIZATION-ENGINE")
    p.add_argument("--repo-root", default=None, help="Repo root override (tests)")
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("latest")
    sp.add_argument("--task", default=None)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_latest)

    sp = sub.add_parser("ready")
    sp.add_argument("--session-id", default=None)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_ready)

    sp = sub.add_parser("seed")
    sp.add_argument("--from-json", required=True)
    sp.add_argument("--session-id", default=None)
    sp.add_argument("--force", action="store_true", help="Re-append even if the task_id already has a row")
    sp.set_defaults(func=cmd_seed)

    sp = sub.add_parser("claim")
    sp.add_argument("--task", required=True)
    sp.add_argument("--expected", required=True)
    sp.add_argument("--run-id", required=True)
    sp.add_argument("--session-id", default=None)
    sp.add_argument("--lease-minutes", type=int, default=90)
    sp.set_defaults(func=cmd_claim)

    sp = sub.add_parser("advance")
    sp.add_argument("--task", required=True)
    sp.add_argument("--expected", required=True)
    sp.add_argument("--to", required=True)
    sp.add_argument("--session-id", default=None)
    sp.add_argument("--evidence", action="append", default=None)
    sp.add_argument("--field", action="append", default=None, help="key=value, repeatable")
    sp.set_defaults(func=cmd_advance)

    sp = sub.add_parser("release")
    sp.add_argument("--task", required=True)
    sp.add_argument("--to", required=True)
    sp.add_argument("--expected", default=None, help="defaults to the task's current status")
    sp.add_argument("--reason", required=True)
    sp.add_argument("--session-id", default=None)
    sp.add_argument("--evidence", action="append", default=None)
    sp.add_argument("--field", action="append", default=None, help="key=value, repeatable")
    sp.set_defaults(func=cmd_release)

    sp = sub.add_parser("recover-expired")
    sp.add_argument("--session-id", default=None)
    sp.set_defaults(func=cmd_recover_expired)

    return p


def main(argv: "list[str] | None" = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
