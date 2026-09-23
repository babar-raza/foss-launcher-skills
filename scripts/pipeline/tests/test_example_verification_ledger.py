"""Tests for lib/example_verification_ledger.py (TC-07,
MT072-2026-09-23-EXAMPLE-VERIFICATION-PRODUCTIONIZATION).

Modeled on test_taskcard_store.py / test_baseline_ledger.py's own test shapes for
the sibling append-only-ledger modules this module copies its concurrency pattern
from: real append/read roundtrips, torn-last-line tolerance, a real (threading, not
mocked) concurrent-writer test, and correctness of the O(1) head-cache sidecar
against the O(n) read_latest_by_key() ground truth.
"""
from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
_LIB_DIR = str(_HERE / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from example_verification.result import BlockIdentity, BlockResult, VerificationReport  # noqa: E402
from example_verification_ledger import (  # noqa: E402
    ExecutionProofLedger,
    LedgerLockTimeout,
    ledger_key,
    resolve_baseline_component,
    resolve_toolchain_fp,
    stale_reason,
)

FAMILY = "pdf"
PLATFORM = "net"


def _base_record(**overrides) -> dict:
    record = {
        "schema_version": 1,
        "run_id": "RUN-001",
        "family": FAMILY,
        "platform": PLATFORM,
        "code_sha256": "a" * 64,
        "lang": "csharp",
        "baseline_component": "deadbeef",
        "baseline_kind": "clone_head",
        "toolchain_fp": "dotnet@8.0.100",
        "runners_module_version": "1",
        "proof_tier": 3,
        "status": "PASS",
        "reason": None,
        "detail": "",
        "recorded_at": "2026-09-23T00:00:00Z",
    }
    record.update(overrides)
    record["key"] = ledger_key(
        record["code_sha256"], record["lang"], record["platform"],
        record["baseline_component"], record["toolchain_fp"], record["runners_module_version"],
    )
    return record


# ---------------------------------------------------------------------------
# ledger_key() / resolve_baseline_component() / resolve_toolchain_fp() / stale_reason()
# ---------------------------------------------------------------------------

def test_ledger_key_is_deterministic_and_order_sensitive():
    k1 = ledger_key("sha1", "csharp", "net", "head1", "dotnet@8", "1")
    k2 = ledger_key("sha1", "csharp", "net", "head1", "dotnet@8", "1")
    assert k1 == k2
    k3 = ledger_key("sha1", "csharp", "net", "head2", "dotnet@8", "1")
    assert k1 != k3  # different clone_head -> different key


def test_resolve_baseline_component_prefers_clone_head():
    component, kind = resolve_baseline_component("abc123", "1.2.3")
    assert (component, kind) == ("abc123", "clone_head")


def test_resolve_baseline_component_falls_back_to_package_version():
    component, kind = resolve_baseline_component(None, "1.2.3")
    assert (component, kind) == ("1.2.3", "package_version")


def test_resolve_baseline_component_unknown_when_neither_present():
    component, kind = resolve_baseline_component(None, None)
    assert (component, kind) == ("", "unknown")


def test_resolve_toolchain_fp_present():
    assert resolve_toolchain_fp("dotnet", "8.0.100") == "dotnet@8.0.100"


def test_resolve_toolchain_fp_version_missing():
    assert resolve_toolchain_fp("dotnet", None) == "dotnet@unavailable"


def test_resolve_toolchain_fp_name_missing():
    assert resolve_toolchain_fp(None, None) == "unknown@unavailable"


def test_stale_reason_fresh_when_everything_matches():
    entry = _base_record()
    reason = stale_reason(
        entry, current_baseline_component="deadbeef",
        current_toolchain_fp="dotnet@8.0.100", current_runners_module_version="1",
    )
    assert reason is None


def test_stale_reason_reports_baseline_first():
    entry = _base_record()
    reason = stale_reason(
        entry, current_baseline_component="different-sha",
        current_toolchain_fp="different-toolchain", current_runners_module_version="2",
    )
    assert reason == "baseline_component"  # priority order: baseline checked first


def test_stale_reason_reports_toolchain_when_baseline_matches():
    entry = _base_record()
    reason = stale_reason(
        entry, current_baseline_component="deadbeef",
        current_toolchain_fp="dotnet@9.0.100", current_runners_module_version="2",
    )
    assert reason == "toolchain_fp"


def test_stale_reason_reports_runners_version_last():
    entry = _base_record()
    reason = stale_reason(
        entry, current_baseline_component="deadbeef",
        current_toolchain_fp="dotnet@8.0.100", current_runners_module_version="2",
    )
    assert reason == "runners_module_version"


def test_stale_reason_ignores_omitted_components():
    entry = _base_record()
    # Caller only knows the runners_module_version -- everything else omitted (None)
    # must never be checked, even though it "mismatches" a value the caller never
    # supplied.
    reason = stale_reason(entry, current_runners_module_version="1")
    assert reason is None


# ---------------------------------------------------------------------------
# append() / read_history() / read_latest_by_key() -- basic roundtrips
# ---------------------------------------------------------------------------

def test_append_then_read_history_roundtrips(tmp_path):
    ledger = ExecutionProofLedger(FAMILY, PLATFORM, ledger_dir=tmp_path)
    written = ledger.append(_base_record())
    history = ledger.read_history()
    assert len(history) == 1
    assert history[0]["run_id"] == "RUN-001"
    assert written["key"] == history[0]["key"]


def test_append_survives_a_fresh_ledger_instance_reopening_the_same_file(tmp_path):
    """Durability proof (item 4 of TC-07): a brand-new ExecutionProofLedger object
    pointed at the same directory must see everything a PRIOR instance appended --
    this is the whole point of an append-only file on disk instead of an
    in-process cache."""
    ExecutionProofLedger(FAMILY, PLATFORM, ledger_dir=tmp_path).append(_base_record())
    reopened = ExecutionProofLedger(FAMILY, PLATFORM, ledger_dir=tmp_path)
    history = reopened.read_history()
    assert len(history) == 1
    assert history[0]["code_sha256"] == "a" * 64
    # The head-cache sidecar is equally durable across a fresh instance.
    cached = reopened.lookup(
        code_sha256="a" * 64, lang="csharp", baseline_component="deadbeef",
        toolchain_fp="dotnet@8.0.100", runners_module_version="1",
    )
    assert cached is not None
    assert cached["run_id"] == "RUN-001"


def test_read_history_empty_when_file_never_created(tmp_path):
    ledger = ExecutionProofLedger(FAMILY, PLATFORM, ledger_dir=tmp_path)
    assert ledger.read_history() == []
    assert ledger.read_latest_by_key() == {}
    assert ledger.head_cache() == {}


def test_read_history_is_append_only_and_ordered(tmp_path):
    ledger = ExecutionProofLedger(FAMILY, PLATFORM, ledger_dir=tmp_path)
    ledger.append(_base_record(run_id="RUN-001"))
    ledger.append(_base_record(run_id="RUN-002"))
    history = ledger.read_history()
    assert [r["run_id"] for r in history] == ["RUN-001", "RUN-002"]


def test_read_latest_by_key_last_occurrence_wins(tmp_path):
    ledger = ExecutionProofLedger(FAMILY, PLATFORM, ledger_dir=tmp_path)
    ledger.append(_base_record(run_id="RUN-001", detail="first run"))
    ledger.append(_base_record(run_id="RUN-002", detail="second run, same key"))
    latest = ledger.read_latest_by_key()
    assert len(latest) == 1  # one entry per key, not per row
    key = _base_record()["key"]
    assert latest[key]["run_id"] == "RUN-002"


def test_read_history_tolerates_torn_last_line(tmp_path):
    """A crashed writer mid-append must not make read_history() raise -- prior,
    complete lines stay readable; the torn line is silently skipped. Same
    tolerance taskcard_store.py's read_history() has."""
    ledger = ExecutionProofLedger(FAMILY, PLATFORM, ledger_dir=tmp_path)
    ledger.append(_base_record(run_id="RUN-001"))
    with open(ledger.path, "a", encoding="utf-8") as f:
        f.write('{"run_id": "RUN-002", "status": "PA')  # truncated, no closing brace/newline
    history = ledger.read_history()
    assert len(history) == 1
    assert history[0]["run_id"] == "RUN-001"


# ---------------------------------------------------------------------------
# append() -- schema validation / durable-proof gate
# ---------------------------------------------------------------------------

def test_append_rejects_missing_field(tmp_path):
    ledger = ExecutionProofLedger(FAMILY, PLATFORM, ledger_dir=tmp_path)
    record = _base_record()
    del record["run_id"]
    with pytest.raises(ValueError, match="invalid ledger record"):
        ledger.append(record)


def test_append_rejects_mismatched_family(tmp_path):
    ledger = ExecutionProofLedger(FAMILY, PLATFORM, ledger_dir=tmp_path)
    with pytest.raises(ValueError, match="does not match"):
        ledger.append(_base_record(family="cells"))


def test_append_rejects_mismatched_platform(tmp_path):
    ledger = ExecutionProofLedger(FAMILY, PLATFORM, ledger_dir=tmp_path)
    with pytest.raises(ValueError, match="does not match"):
        ledger.append(_base_record(platform="java"))


def test_append_rejects_non_deterministic_status(tmp_path):
    """The durable-proof gate: NOT-VERIFIED/NOT-EXECUTABLE-LANG must never reach
    disk here, even via the raw append() API."""
    ledger = ExecutionProofLedger(FAMILY, PLATFORM, ledger_dir=tmp_path)
    record = _base_record(status="NOT-VERIFIED", reason=None)
    with pytest.raises(ValueError, match="invalid ledger record"):
        ledger.append(record)


def test_append_rejects_non_deterministic_reason(tmp_path):
    """TOOLCHAIN-UNAVAILABLE/ACQUIRE-FAILED/etc. are environment-dependent, not a
    property of the code block -- refused even though status is the allowed
    BLOCKED-WITH-REASON."""
    ledger = ExecutionProofLedger(FAMILY, PLATFORM, ledger_dir=tmp_path)
    record = _base_record(status="BLOCKED-WITH-REASON", reason="TOOLCHAIN-UNAVAILABLE", proof_tier=0)
    with pytest.raises(ValueError, match="invalid ledger record"):
        ledger.append(record)


def test_append_accepts_deterministic_blocked_reason(tmp_path):
    """SYNTAX-ERROR IS in DETERMINISTIC_REASONS_FOR_CACHE -- a real, durable proof
    that this exact code is broken, safe to record indefinitely."""
    ledger = ExecutionProofLedger(FAMILY, PLATFORM, ledger_dir=tmp_path)
    record = _base_record(status="BLOCKED-WITH-REASON", reason="SYNTAX-ERROR", proof_tier=1)
    written = ledger.append(record)
    assert written["reason"] == "SYNTAX-ERROR"


def test_append_rejects_reason_present_when_status_is_pass(tmp_path):
    ledger = ExecutionProofLedger(FAMILY, PLATFORM, ledger_dir=tmp_path)
    record = _base_record(status="PASS", reason="SYNTAX-ERROR")
    with pytest.raises(ValueError, match="invalid ledger record"):
        ledger.append(record)


def test_append_rejects_key_that_does_not_match_derived_key(tmp_path):
    ledger = ExecutionProofLedger(FAMILY, PLATFORM, ledger_dir=tmp_path)
    record = _base_record()
    record["key"] = "0" * 64  # tampered / stale key
    with pytest.raises(ValueError, match="invalid ledger record"):
        ledger.append(record)


def test_append_rejects_invalid_proof_tier(tmp_path):
    ledger = ExecutionProofLedger(FAMILY, PLATFORM, ledger_dir=tmp_path)
    with pytest.raises(ValueError, match="invalid ledger record"):
        ledger.append(_base_record(proof_tier=99))


def test_append_rejects_invalid_baseline_kind(tmp_path):
    ledger = ExecutionProofLedger(FAMILY, PLATFORM, ledger_dir=tmp_path)
    with pytest.raises(ValueError, match="invalid ledger record"):
        ledger.append(_base_record(baseline_kind="not-a-real-kind"))


# ---------------------------------------------------------------------------
# lookup() / find_latest_by_content() / check_proof()
# ---------------------------------------------------------------------------

def test_lookup_returns_none_for_unknown_key(tmp_path):
    ledger = ExecutionProofLedger(FAMILY, PLATFORM, ledger_dir=tmp_path)
    assert ledger.lookup(
        code_sha256="nope", lang="csharp", baseline_component="x",
        toolchain_fp="y", runners_module_version="1",
    ) is None


def test_lookup_hits_via_head_cache(tmp_path):
    ledger = ExecutionProofLedger(FAMILY, PLATFORM, ledger_dir=tmp_path)
    ledger.append(_base_record())
    hit = ledger.lookup(
        code_sha256="a" * 64, lang="csharp", baseline_component="deadbeef",
        toolchain_fp="dotnet@8.0.100", runners_module_version="1",
    )
    assert hit is not None
    assert hit["run_id"] == "RUN-001"


def test_lookup_falls_back_to_full_scan_when_head_cache_missing(tmp_path):
    """The O(1) sidecar can legitimately be absent (e.g. lost independently of the
    append-only file) -- lookup() must still find the entry via
    read_latest_by_key()."""
    ledger = ExecutionProofLedger(FAMILY, PLATFORM, ledger_dir=tmp_path)
    ledger.append(_base_record())
    ledger.head_path.unlink()
    hit = ledger.lookup(
        code_sha256="a" * 64, lang="csharp", baseline_component="deadbeef",
        toolchain_fp="dotnet@8.0.100", runners_module_version="1",
    )
    assert hit is not None
    assert hit["run_id"] == "RUN-001"


def test_head_cache_matches_read_latest_by_key_after_multiple_appends(tmp_path):
    """The O(1) sidecar and the O(n) ground truth must never disagree."""
    ledger = ExecutionProofLedger(FAMILY, PLATFORM, ledger_dir=tmp_path)
    ledger.append(_base_record(code_sha256="a" * 64))
    ledger.append(_base_record(code_sha256="b" * 64))
    ledger.append(_base_record(code_sha256="a" * 64, run_id="RUN-002", detail="rerun"))
    assert ledger.head_cache() == ledger.read_latest_by_key()


def test_check_proof_no_proof_when_never_recorded(tmp_path):
    ledger = ExecutionProofLedger(FAMILY, PLATFORM, ledger_dir=tmp_path)
    entry, reason = ledger.check_proof(code_sha256="nope", lang="csharp")
    assert entry is None
    assert reason == "no-proof"


def test_check_proof_fresh_when_context_matches(tmp_path):
    ledger = ExecutionProofLedger(FAMILY, PLATFORM, ledger_dir=tmp_path)
    ledger.append(_base_record())
    entry, reason = ledger.check_proof(
        code_sha256="a" * 64, lang="csharp", current_baseline_component="deadbeef",
        current_toolchain_fp="dotnet@8.0.100", current_runners_module_version="1",
    )
    assert entry is not None
    assert reason is None


def test_check_proof_stale_when_baseline_moved(tmp_path):
    ledger = ExecutionProofLedger(FAMILY, PLATFORM, ledger_dir=tmp_path)
    ledger.append(_base_record())
    entry, reason = ledger.check_proof(
        code_sha256="a" * 64, lang="csharp", current_baseline_component="newer-clone-head",
        current_toolchain_fp="dotnet@8.0.100", current_runners_module_version="1",
    )
    assert entry is not None
    assert reason == "baseline_component"


def test_check_proof_finds_latest_ignoring_toolchain_change(tmp_path):
    """find_latest_by_content() deliberately ignores baseline/toolchain/runners_
    version when SELECTING the entry (that's the point -- it's the "loose"
    identity check_proof() starts from); staleness is judged separately by
    stale_reason()."""
    ledger = ExecutionProofLedger(FAMILY, PLATFORM, ledger_dir=tmp_path)
    ledger.append(_base_record(toolchain_fp="dotnet@8.0.100"))
    ledger.append(_base_record(toolchain_fp="dotnet@9.0.100", run_id="RUN-002"))
    entry, reason = ledger.check_proof(
        code_sha256="a" * 64, lang="csharp", current_baseline_component="deadbeef",
        current_toolchain_fp="dotnet@9.0.100", current_runners_module_version="1",
    )
    assert entry["run_id"] == "RUN-002"  # the most recently appended row
    assert reason is None


# ---------------------------------------------------------------------------
# record_result() -- real VerificationReport/BlockResult objects
# ---------------------------------------------------------------------------

def _identity(sha="a" * 64, lang="csharp") -> BlockIdentity:
    return BlockIdentity(code_sha256=sha, lang=lang, index=0, start_line=1, end_line=3)


def test_record_result_writes_a_real_pass(tmp_path):
    ledger = ExecutionProofLedger(FAMILY, PLATFORM, ledger_dir=tmp_path)
    report = VerificationReport(runner="net", clone_head="deadbeef", runners_module_version="1")
    block = BlockResult(identity=_identity(), status="PASS", proof_tier=3, toolchain_name="dotnet", toolchain_version="8.0.100")
    written = ledger.record_result(report, block, run_id="RUN-100")
    assert written is not None
    assert written["status"] == "PASS"
    assert written["baseline_component"] == "deadbeef"
    assert written["baseline_kind"] == "clone_head"
    assert written["toolchain_fp"] == "dotnet@8.0.100"
    assert ledger.read_history() == [written]


def test_record_result_writes_a_deterministic_failure(tmp_path):
    ledger = ExecutionProofLedger(FAMILY, PLATFORM, ledger_dir=tmp_path)
    report = VerificationReport(runner="net", clone_head="deadbeef", runners_module_version="1")
    block = BlockResult(
        identity=_identity(), status="BLOCKED-WITH-REASON", reason="SYNTAX-ERROR",
        detail="unexpected token", proof_tier=1,
    )
    written = ledger.record_result(report, block, run_id="RUN-101")
    assert written is not None
    assert written["reason"] == "SYNTAX-ERROR"


def test_record_result_skips_non_cacheable_outcome(tmp_path):
    """TOOLCHAIN-UNAVAILABLE is environment-dependent -- record_result() must
    silently skip it (return None), not write anything, matching cache.py's
    ResultCache.put() contract."""
    ledger = ExecutionProofLedger(FAMILY, PLATFORM, ledger_dir=tmp_path)
    report = VerificationReport(runner="net", clone_head="deadbeef", runners_module_version="1")
    block = BlockResult(
        identity=_identity(), status="BLOCKED-WITH-REASON", reason="TOOLCHAIN-UNAVAILABLE",
        proof_tier=0,
    )
    written = ledger.record_result(report, block, run_id="RUN-102")
    assert written is None
    assert ledger.read_history() == []


def test_record_result_uses_package_version_for_whole_candidate_platforms(tmp_path):
    """python/typescript's whole-candidate reports never set clone_head -- the
    ledger must fall back to package_version as the baseline component."""
    ledger = ExecutionProofLedger("cells", "python", ledger_dir=tmp_path)
    report = VerificationReport(
        runner="python", clone_head=None, package="aspose-cells", package_version="26.6.0",
        runners_module_version="1",
    )
    block = BlockResult(identity=_identity(lang="python"), status="PASS", proof_tier=3)
    written = ledger.record_result(report, block, run_id="RUN-200")
    assert written["baseline_component"] == "26.6.0"
    assert written["baseline_kind"] == "package_version"


# ---------------------------------------------------------------------------
# Locking -- timeout, and a real concurrency proof
# ---------------------------------------------------------------------------

def test_lock_timeout_raises_when_held(tmp_path):
    ledger = ExecutionProofLedger(FAMILY, PLATFORM, ledger_dir=tmp_path)
    holder = ExecutionProofLedger(FAMILY, PLATFORM, ledger_dir=tmp_path)
    holder._acquire_lock()
    try:
        waiter = ExecutionProofLedger(FAMILY, PLATFORM, ledger_dir=tmp_path)
        with pytest.raises(LedgerLockTimeout):
            waiter._acquire_lock(timeout=0.2)
    finally:
        holder._release_lock()


def test_concurrent_appends_from_multiple_sessions_no_corruption(tmp_path):
    """Real concurrency test (threading, not mocked): N 'sessions' race to append
    DISTINCT records to the SAME product's ledger file at once. Unlike
    taskcard_store's CAS-guarded status transition, a ledger append is an
    independent fact -- every append must succeed (no CAS refusal expected here),
    the lock must serialize the actual file writes so no line is lost, torn, or
    interleaved, and every appended record must be exactly the one its own thread
    wrote (no cross-thread data mixing)."""
    n_threads = 5
    errors: "list[Exception]" = []

    def _worker(i: int) -> None:
        try:
            ExecutionProofLedger(FAMILY, PLATFORM, ledger_dir=tmp_path).append(
                _base_record(run_id=f"RUN-{i}", code_sha256=f"{i}" * 64),
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=_worker, args=(i,)) for i in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert not errors, f"unexpected exceptions under concurrent append: {errors}"

    ledger = ExecutionProofLedger(FAMILY, PLATFORM, ledger_dir=tmp_path)
    history = ledger.read_history()
    assert len(history) == n_threads
    run_ids = {r["run_id"] for r in history}
    assert run_ids == {f"RUN-{i}" for i in range(n_threads)}

    # File itself is not corrupted -- every line parses, and each record's own
    # code_sha256 matches the key it was appended under (no cross-thread mixing).
    for line in ledger.path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        expected_key = ledger_key(
            row["code_sha256"], row["lang"], row["platform"],
            row["baseline_component"], row["toolchain_fp"], row["runners_module_version"],
        )
        assert row["key"] == expected_key

    # The head-cache sidecar reflects every thread's own distinct key (each
    # thread used a distinct code_sha256, so none of them collide/overwrite).
    assert len(ledger.head_cache()) == n_threads
