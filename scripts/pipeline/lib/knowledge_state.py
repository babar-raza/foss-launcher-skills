"""
knowledge_state.py — durable, git-tracked per-product pipeline-state projection.

CONTRACT: scripts/pipeline/lib/knowledge_state.py
  purpose: PDF-JAVA-REFRESH-003's deep assessment (MT030-2026-08-13) found that every
           artifact proving a knowledge refresh actually happened -- model.yaml,
           baseline_ledger.jsonl, reports/refresh_runs/**/manifest.json, reports/audit/*.md --
           is gitignored (.gitignore:18,20). It is a real, working, concurrency-safe LOCAL
           CACHE within one checkout, but does not survive a fresh clone or a different
           session's checkout, in a repo whose normal operating mode is many parallel agent
           sessions. Nothing durable ever recorded "was this baseline truth-audited" or
           "does evidence still match the model" across sessions -- so backlog/BACKLOG.md
           rows (the one git-tracked record other than content itself) could only be kept
           current by an agent noticing and hand-editing them, which is exactly how
           PDF-JAVA-REFRESH-003 went stale twice (once on its stored SHA, once on its own
           "no truth-audit exists" claim, 4 days after a truth-audit actually landed).
  durability: data/knowledge_state.json is git-committed (data/ is not gitignored). It is
           the single durable projection of "last accepted baseline, last truth-audit
           verdict, known evidence-skip debt" per product -- a summary, not a replacement
           for the local caches above, which remain the fast, full-history working store.
  inputs:  none (pure writer/reader over its own state file)
  outputs: data/knowledge_state.json (single shared file, one JSON object keyed by
           "{family}/{platform}")
  idempotent: yes -- each record_*() call replaces only its own sub-key for the product;
           re-recording identical data produces a byte-identical file (no spurious churn).
  concurrency: FileLock (scripts/pipeline/lib/advisory_lock.py) around the read-modify-write,
           same pattern baseline_ledger.py already proves works under this repo's normal
           parallel-agent-sprint load. All writes are non-fatal by design (callers wrap them
           the same way promote.py already wraps BaselineLedger.append() -- a knowledge_state
           write failure must never abort the refresh/audit/attach that triggered it).

Usage::

    from knowledge_state import record_baseline_accepted, record_truth_audit, \
        record_evidence_skip, read_state

    record_baseline_accepted("pdf", "java", repo_sha="be089a7e...", sha_source="scout",
                              run_id="promote-20260729T164123Z", accepted_at="2026-07-29T16:41:23Z")
    record_truth_audit("pdf", "java", fail_count=0, warn_count=59,
                        report_path="reports/audit/pdf-java-truth-20260813.md",
                        recorded_at="2026-08-13T09:49:00Z")
    record_evidence_skip("pdf", "java", "content/kb.aspose.org/en/pdf/java/use-cases.md",
                          reason="audit_fail", recorded_at="2026-08-13T09:40:00Z")
    read_state("pdf", "java")   # -> the product's full state dict, or None
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

_LIB_DIR = Path(__file__).resolve().parent
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))
_REPO_ROOT = Path(__file__).resolve().parents[3]  # lib/ -> pipeline/ -> scripts/ -> repo root

from advisory_lock import FileLock, LockTimeout  # noqa: E402
from core.fs import atomic_write  # noqa: E402

_STATE_PATH = _REPO_ROOT / "data" / "knowledge_state.json"
_LOCK_PATH = _REPO_ROOT / "data" / "knowledge_state.json.lock"
_UPSTREAM_BASELINES_PATH = _REPO_ROOT / "data" / "upstream_baselines.json"
_UPSTREAM_BASELINES_LOCK_PATH = _REPO_ROOT / "data" / "upstream_baselines.json.lock"
_LOCK_TIMEOUT = 10.0
_LOCK_POLL_INTERVAL = 0.05


class KnowledgeStateLockTimeout(Exception):
    """Raised when the shared knowledge_state.json lock could not be acquired in time."""


def _product_key(family: str, platform: str) -> str:
    return f"{family}/{platform}"


def _load_all() -> dict[str, Any]:
    if not _STATE_PATH.exists():
        return {}
    try:
        return json.loads(_STATE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}  # tolerate a torn/corrupt file rather than raise on read


def _write_all(state: dict[str, Any]) -> None:
    atomic_write(_STATE_PATH, json.dumps(state, indent=2, sort_keys=True) + "\n")


def _update_product(family: str, platform: str, section: str, payload: dict[str, Any]) -> None:
    """Read-modify-write one product's one section, under an exclusive lock."""
    lock = FileLock(_LOCK_PATH, timeout=_LOCK_TIMEOUT, poll=_LOCK_POLL_INTERVAL)
    try:
        lock.acquire()
    except LockTimeout as exc:
        raise KnowledgeStateLockTimeout(str(exc)) from exc
    try:
        state = _load_all()
        key = _product_key(family, platform)
        product = state.setdefault(key, {"family": family, "platform": platform})
        product[section] = payload
        _write_all(state)
    finally:
        lock.release()


def record_baseline_accepted(
    family: str,
    platform: str,
    *,
    repo_sha: str,
    sha_source: str,
    run_id: str,
    accepted_at: str,
) -> None:
    """Record the last accepted knowledge baseline for a product.

    Called from promote.py's acceptance choke point, paired with (not replacing)
    BaselineLedger.append() -- same acceptance event, one more durable consumer.
    """
    _update_product(family, platform, "accepted_baseline", {
        "repo_sha": repo_sha,
        "sha_source": sha_source,
        "run_id": run_id,
        "accepted_at": accepted_at,
    })


def record_truth_audit(
    family: str,
    platform: str,
    *,
    fail_count: int,
    warn_count: int,
    report_path: str,
    recorded_at: str,
) -> None:
    """Record the verdict of the most recent S-38 truth-audit run for a product."""
    _update_product(family, platform, "truth_audit", {
        "fail_count": fail_count,
        "warn_count": warn_count,
        "verdict": "PASS" if fail_count == 0 else "FAIL",
        "report_path": report_path,
        "recorded_at": recorded_at,
    })


def record_evidence_skip(
    family: str,
    platform: str,
    filepath: str,
    *,
    reason: str,
    recorded_at: str,
) -> None:
    """Record one page that attach_evidence.py permanently skipped (draft or audit-FAIL).

    A page skipped for "audit_fail" stays stale on every future refresh cycle until the
    underlying content defect is fixed -- this makes that debt queryable per product
    instead of a stdout line nobody reads (the confirmed root cause of the one live
    evidence-staleness gap in PDF-JAVA-REFRESH-003).
    """
    lock = FileLock(_LOCK_PATH, timeout=_LOCK_TIMEOUT, poll=_LOCK_POLL_INTERVAL)
    try:
        lock.acquire()
    except LockTimeout as exc:
        raise KnowledgeStateLockTimeout(str(exc)) from exc
    try:
        state = _load_all()
        key = _product_key(family, platform)
        product = state.setdefault(key, {"family": family, "platform": platform})
        skips = product.setdefault("evidence_skips", {})
        skips[filepath] = {"reason": reason, "recorded_at": recorded_at}
        _write_all(state)
    finally:
        lock.release()


def update_upstream_baseline(family: str, platform: str, repo_sha: str) -> None:
    """Update this product's entry in data/upstream_baselines.json.

    That file is read by the scheduled .github/workflows/upstream-monitor.yml cron
    (via scripts/ci/checks/check_upstream_drift.py) but, before this fix, had zero
    writers anywhere in the codebase -- confirmed frozen at pre-refresh SHAs for
    every product it tracks. Write it at the same promote.py acceptance choke point
    as record_baseline_accepted() so the two never drift apart again.
    """
    lock = FileLock(_UPSTREAM_BASELINES_LOCK_PATH, timeout=_LOCK_TIMEOUT, poll=_LOCK_POLL_INTERVAL)
    try:
        lock.acquire()
    except LockTimeout as exc:
        raise KnowledgeStateLockTimeout(str(exc)) from exc
    try:
        try:
            baselines = json.loads(_UPSTREAM_BASELINES_PATH.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            baselines = {}
        baselines[_product_key(family, platform)] = repo_sha
        atomic_write(_UPSTREAM_BASELINES_PATH, json.dumps(baselines, indent=2, sort_keys=True) + "\n")
    finally:
        lock.release()


def read_state(family: str, platform: str) -> dict[str, Any] | None:
    """Return one product's full recorded state, or None if never recorded."""
    return _load_all().get(_product_key(family, platform))


def read_all() -> dict[str, Any]:
    """Return the full state file as a dict keyed by 'family/platform'."""
    return _load_all()
