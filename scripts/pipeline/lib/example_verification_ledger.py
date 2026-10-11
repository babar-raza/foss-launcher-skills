"""example_verification_ledger.py — TC-07 (MT072-2026-09-23-EXAMPLE-VERIFICATION-
PRODUCTIONIZATION): durable, git-tracked execution-proof ledger for the
`example_verification` package (lib/example_verification/).

CONTRACT: scripts/pipeline/lib/example_verification_ledger.py
  purpose: cache.py's ResultCache (lib/example_verification/cache.py) answers "is a
           rerun over unchanged inputs unnecessary" -- a hit/miss PERFORMANCE cache
           at `runs/.example_verification/{family}_{platform}/cache.json`, gitignored,
           whole-file-rewrite, no history, gone on a fresh clone. Nothing in this repo
           answers the different, audit-grade question this module exists for: "when
           was this exact code example verified, at what tier, with what result, and
           does that proof still apply." Modeled explicitly on the two proven
           append-only-ledger + O(1)-head-cache + O_EXCL-lock modules this repo already
           has (per the governing plan): baseline_ledger.py (BaselineLedger) and
           taskcard_store.py (TaskcardStore, itself modeled on baseline_ledger.py) --
           this module copies that concurrency-safety pattern verbatim rather than
           inventing a new one.
  inputs:  a real example_verification.result.VerificationReport +
           example_verification.result.BlockResult (record_result()), or a raw,
           schema-validated dict (append()).
  outputs: reports/example_verification_ledger/{family}_{platform}.jsonl
           (append-only) reports/example_verification_ledger/{family}_{platform}.head.json
           (O(1) head-cache sidecar: ledger_key() -> latest record for that exact key)
  owner_domain: content-quality
  requires_test: true

Key/value schema (governing plan, TC-07's own spec):
  key   = (code_sha256, lang, platform, baseline_component, toolchain_fp,
           runners_module_version) -- collapsed via ledger_key() into one sha256 hex
           string, the same "hash the pipe-joined tuple" idiom cache.py's own
           cache_key() already uses (verbatim priority/format, `"1|..."` version
           prefix included, for the same reason cache.py's docstring gives: an
           explicit, versioned key format survives a future field addition without
           silently colliding with an old key shape).
  value = (proof_tier, status, reason, run_id, recorded_at) -- plus enough context
           (family/platform/lang/baseline_kind/toolchain_fp/runners_module_version) for
           a reader to understand what the key's hash actually encodes without having
           to re-derive it.

Durable-proof gate (item 1 of TC-07): this ledger NEVER durably records an outcome
that cache.py's own result.py vocabulary marks as environment- or moment-dependent.
Exactly cache.py's own `is_pass() or is_deterministic_failure()` gate (BlockResult.
is_cacheable(), same underlying DETERMINISTIC_STATUSES_FOR_CACHE /
DETERMINISTIC_REASONS_FOR_CACHE sets) -- so TOOLCHAIN-UNAVAILABLE, ACQUIRE-FAILED,
ACQUIRE-SKIPPED, TIMEOUT, SLOW, FIXTURE-UNAVAILABLE, NO-CLONE-CACHE,
BUDGET-EXHAUSTED, GRAMMAR-UNAVAILABLE, NOT-VERIFIED, NOT-EXECUTABLE-LANG can never
reach disk here, at two independent layers: record_result() only ever calls append()
for a cacheable BlockResult (returns None, not an error, otherwise -- matching
ResultCache.put()'s own "silently skipped, not an error" contract), AND
_validate_ledger_record() refuses (raises ValueError) any raw append() call whose
status/reason falls outside {PASS} union {BLOCKED-WITH-REASON with a reason in
DETERMINISTIC_REASONS_FOR_CACHE} regardless of caller.

Staleness idiom (item 1): reuses cache.py's own stale_reason() priority order
verbatim (clone_head/baseline first, then toolchain, then runners_module_version),
applied to this ledger's richer, git-durable key via the module-level stale_reason()
function below.

DISCLOSED BLOCKER, found while building this (not silently worked around): this
ledger's entire purpose is to be git-DURABLE (unlike cache.py's gitignored runs/
cache) -- but reports/ is blanket-gitignored by .gitignore's generated
GIT-TRACKING-POLICY block (`reports/*` at .gitignore:22, negated only for
`reports/audit/`, `reports/plan_state/`, `reports/repo-presenter-regen-full/` --
see scripts/pipeline/config/git_tracking_policy.yaml's `policies:` list), PLUS a
second, redundant, non-generated `/reports` blanket ignore at .gitignore:148.
`reports/example_verification_ledger/` is named in NEITHER negation list, so as of
this taskcard `git add` on any file under it is silently a no-op: it behaves
exactly like cache.py's own gitignored runs/ cache (local-machine-only, invisible to
a fresh clone or another session) until a human/orchestrator adds a policy entry to
git_tracking_policy.yaml (e.g. a `literal` keep for `example_verification_ledger`)
and regenerates .gitignore via
`scripts/pipeline/commands/ops/git_tracking_policy_sync.py --fix`. Both
git_tracking_policy.yaml and .gitignore are OUTSIDE this taskcard's allowed_paths
(scripts/pipeline/lib/example_verification_ledger.py,
scripts/pipeline/tests/test_example_verification_ledger.py,
reports/example_verification_ledger/ only) -- this gap is disclosed here and in the
taskcard's evidence_refs, not fixed in this commit.

Usage::

    from example_verification_ledger import ExecutionProofLedger

    ledger = ExecutionProofLedger("pdf", "net")
    ledger.record_result(report, block, run_id="RUN-001")
    entry, reason = ledger.check_proof(
        code_sha256=block.identity.code_sha256, lang=block.identity.lang,
        current_baseline_component=report.clone_head,
        current_toolchain_fp="dotnet@8.0.100",
        current_runners_module_version=report.runners_module_version,
    )
    if entry is not None and reason is None:
        ...  # already proven, still fresh -- safe to skip re-verification
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_LIB_DIR = Path(__file__).resolve().parent
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))
_REPO_ROOT = Path(__file__).resolve().parents[3]  # lib/ -> pipeline/ -> scripts/ -> repo root

from advisory_lock import FileLock, LockTimeout  # noqa: E402
from example_verification.result import (  # noqa: E402
    DETERMINISTIC_REASONS_FOR_CACHE,
    DETERMINISTIC_STATUSES_FOR_CACHE,
)

LEDGER_SCHEMA_VERSION = 1

# The only statuses this ledger will ever durably record -- see module docstring's
# "durable-proof gate". Deliberately narrower than result.STATUSES.
_LEDGER_ALLOWED_STATUSES: "frozenset[str]" = DETERMINISTIC_STATUSES_FOR_CACHE | frozenset(
    {"BLOCKED-WITH-REASON"}
)

_STALE_LOCK_SECONDS = 120.0
_DEFAULT_LOCK_TIMEOUT = 10.0
_LOCK_POLL_INTERVAL = 0.05

_BASELINE_KINDS: "frozenset[str]" = frozenset({"clone_head", "package_version", "unknown"})


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z")


class LedgerLockTimeout(Exception):
    """Raised when a product's ledger lock could not be acquired within the timeout."""


def ledger_key(
    code_sha256: str, lang: str, platform: str, baseline_component: str,
    toolchain_fp: str, runners_module_version: str,
) -> str:
    """Collapse the 6-tuple key into one sha256 hex digest -- same
    "versioned-prefix, pipe-joined, sha256" idiom as
    lib/example_verification/cache.py::cache_key(), extended with `platform`
    (cache.py's cache is already scoped to one family/platform directory, so it never
    needed platform IN the key; this ledger's per-product file is also
    family/platform-scoped, but the platform is kept in the key too so a raw record
    is still self-describing/verifiable via _validate_ledger_record() without
    needing the enclosing file path)."""
    raw = f"1|{code_sha256}|{lang}|{platform}|{baseline_component}|{toolchain_fp}|{runners_module_version}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def resolve_baseline_component(
    clone_head: "str | None", package_version: "str | None",
) -> "tuple[str, str]":
    """Priority order matching cache.py's own stale_reason() component order
    (clone_head checked before toolchain/runners) -- clone_head wins when both are
    present (a language-runner-driven block always has a clone_head; python/
    typescript's whole-candidate path never does, so the two are naturally
    mutually exclusive today, not actually racing for priority in practice)."""
    if clone_head:
        return clone_head, "clone_head"
    if package_version:
        return package_version, "package_version"
    return "", "unknown"


def resolve_toolchain_fp(toolchain_name: "str | None", toolchain_version: "str | None") -> str:
    """Same `"{name}@{version}"` / `"{name}@unavailable"` shape as
    lib/example_verification/toolchain.py::fingerprint(), built from a BlockResult's
    own toolchain_name/toolchain_version fields rather than re-probing PATH -- this
    module never shells out to a toolchain itself."""
    if toolchain_name:
        return f"{toolchain_name}@{toolchain_version or 'unavailable'}"
    return "unknown@unavailable"


def stale_reason(
    entry: "dict[str, Any]", *, current_baseline_component: "str | None" = None,
    current_toolchain_fp: "str | None" = None, current_runners_module_version: "str | None" = None,
) -> "str | None":
    """Name the first recorded component whose value differs from the caller's
    current value, in this fixed priority order: baseline_component -> toolchain_fp
    -> runners_module_version. Returns None if every supplied component matches (the
    entry is fresh). Any component the caller omits (passes None) is not checked --
    the exact idiom lib/example_verification/cache.py::stale_reason() already proved
    at the smaller (hit/miss cache) scale, reused verbatim here rather than
    reinvented, just applied to this ledger's own field names."""
    if (
        current_baseline_component is not None
        and entry.get("baseline_component")
        and current_baseline_component != entry["baseline_component"]
    ):
        return "baseline_component"
    if (
        current_toolchain_fp is not None
        and entry.get("toolchain_fp")
        and current_toolchain_fp != entry["toolchain_fp"]
    ):
        return "toolchain_fp"
    if (
        current_runners_module_version is not None
        and entry.get("runners_module_version")
        and current_runners_module_version != entry["runners_module_version"]
    ):
        return "runners_module_version"
    return None


def _validate_ledger_record(record: "dict[str, Any]") -> "list[str]":
    """Schema-validation-on-write, same discipline taskcard_store.py's
    validate_taskcard_record() / baseline_ledger.py's validate_baseline_ledger_entry()
    apply before every write -- a malformed OR under-qualified (non-durable-proof) row
    is refused before it ever reaches disk, not just flagged after the fact."""
    errors: "list[str]" = []
    required = [
        "schema_version", "key", "run_id", "family", "platform", "code_sha256", "lang",
        "baseline_component", "baseline_kind", "toolchain_fp", "runners_module_version",
        "proof_tier", "status", "reason", "detail", "recorded_at",
    ]
    for field in required:
        if field not in record:
            errors.append(f"missing required field: {field}")
    if errors:
        return errors  # every check below assumes these fields exist

    if record["schema_version"] != LEDGER_SCHEMA_VERSION:
        errors.append(f"unsupported schema_version: {record['schema_version']!r}")
    if not record["run_id"]:
        errors.append("run_id must be non-empty")
    if not record["family"]:
        errors.append("family must be non-empty")
    if not record["platform"]:
        errors.append("platform must be non-empty")
    if not record["code_sha256"]:
        errors.append("code_sha256 must be non-empty")
    if not record["lang"]:
        errors.append("lang must be non-empty")
    if record["baseline_kind"] not in _BASELINE_KINDS:
        errors.append(f"invalid baseline_kind: {record['baseline_kind']!r}")
    if not isinstance(record["proof_tier"], int) or isinstance(record["proof_tier"], bool) or not (0 <= record["proof_tier"] <= 4):
        errors.append(f"invalid proof_tier: {record['proof_tier']!r}")

    status = record["status"]
    reason = record["reason"]
    if status not in _LEDGER_ALLOWED_STATUSES:
        errors.append(
            f"status must be one of {sorted(_LEDGER_ALLOWED_STATUSES)}, got {status!r} -- "
            "this ledger records durable PROOF only, never a transient/"
            "environment-dependent outcome (see module docstring's durable-proof gate)"
        )
    elif status == "BLOCKED-WITH-REASON":
        if reason not in DETERMINISTIC_REASONS_FOR_CACHE:
            errors.append(
                f"reason {reason!r} is not in DETERMINISTIC_REASONS_FOR_CACHE -- refusing to "
                "durably record a non-deterministic/environment-dependent failure"
            )
    elif reason is not None:
        errors.append(f"reason must be null when status is {status!r}, got {reason!r}")

    if not errors:
        expected_key = ledger_key(
            record["code_sha256"], record["lang"], record["platform"],
            record["baseline_component"], record["toolchain_fp"], record["runners_module_version"],
        )
        if record["key"] != expected_key:
            errors.append("key does not match ledger_key() derived from this record's own fields")
    return errors


class ExecutionProofLedger:
    """Append-only, lock-guarded execution-proof ledger for one product
    (family/platform). API shape modeled on TaskcardStore (append() / read_history()
    / a latest-by-key lookup), with baseline_ledger.py's O(1) head-cache sidecar file
    added on top so a caller doesn't have to scan the whole history for the common
    "has this exact key already been proven" query."""

    def __init__(
        self,
        family: str,
        platform: str,
        *,
        repo_root: "Path | str | None" = None,
        ledger_dir: "Path | str | None" = None,
    ):
        """
        Args:
            repo_root: repo root; the ledger lives at
                {repo_root}/reports/example_verification_ledger/. Ignored if
                ledger_dir is given.
            ledger_dir: explicit override for the ledger directory -- takes
                precedence over repo_root (used by tests, and by any future caller
                that already computes this path under its own convention).
        """
        self.family = family
        self.platform = platform
        if ledger_dir is not None:
            resolved_dir = Path(ledger_dir)
            self.repo_root = None
        else:
            self.repo_root = Path(repo_root) if repo_root is not None else _REPO_ROOT
            resolved_dir = self.repo_root / "reports" / "example_verification_ledger"
        stem = f"{family}_{platform}"
        self.path = resolved_dir / f"{stem}.jsonl"
        self.head_path = resolved_dir / f"{stem}.head.json"
        self.lock_path = resolved_dir / f"{stem}.jsonl.lock"
        self._active_lock: "FileLock | None" = None

    # ── Locking ──────────────────────────────────────────────────────────

    def _acquire_lock(self, timeout: "float | None" = None) -> None:
        lock = FileLock(
            self.lock_path,
            stale_seconds=_STALE_LOCK_SECONDS,
            timeout=timeout if timeout is not None else _DEFAULT_LOCK_TIMEOUT,
            poll=_LOCK_POLL_INTERVAL,
        )
        try:
            lock.acquire()
        except LockTimeout as exc:
            raise LedgerLockTimeout(str(exc)) from exc
        self._active_lock = lock

    def _release_lock(self) -> None:
        lock = self._active_lock
        if lock is not None:
            self._active_lock = None
            lock.release()
            return
        try:
            self.lock_path.unlink()
        except OSError:
            pass  # already released or never acquired -- safe to ignore

    # ── Reads (safe without the lock -- append-only file; worst case is a torn
    #    read of the very last line mid-write, never corruption of prior lines) ──

    def read_history(self) -> "list[dict[str, Any]]":
        """Return every row ever appended, in append order. Tolerates a torn last
        line from a crashed writer (skipped, never raises) -- same tolerance
        taskcard_store.py's read_history() / baseline_ledger.py's history() have."""
        if not self.path.exists():
            return []
        rows: "list[dict[str, Any]]" = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # torn last line from a crashed writer -- never raise on read
        return rows

    def read_latest_by_key(self) -> "dict[str, dict[str, Any]]":
        """ledger_key() -> its latest row (append-only: last occurrence wins),
        the ground-truth (O(n)) equivalent of head_cache()'s O(1) sidecar --
        used as a fallback when the sidecar is missing/stale, and as the
        correctness oracle in tests."""
        latest: "dict[str, dict[str, Any]]" = {}
        for row in self.read_history():
            key = row.get("key")
            if key:
                latest[key] = row
        return latest

    def head_cache(self) -> "dict[str, dict[str, Any]]":
        """O(1) read of the cached head sidecar (ledger_key() -> latest record for
        that exact key). Never raises -- a missing or corrupt sidecar reads as
        empty, matching baseline_ledger.py's head()/cache.py's ResultCache._load()
        tolerance for a missing/corrupt file."""
        if not self.head_path.exists():
            return {}
        try:
            data = json.loads(self.head_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def find_latest_by_content(self, code_sha256: str, lang: str) -> "dict[str, Any] | None":
        """The most recently appended row for this exact (code_sha256, lang) pair,
        regardless of what baseline/toolchain/runners_module_version it was proven
        under -- the "loose" identity a staleness check starts from (see
        check_proof()). O(n) full-history scan: this module is not wired into any
        consumer yet (that is a later taskcard's job), so there is no head-cache
        sidecar for this looser index -- documented, not hidden."""
        for record in reversed(self.read_history()):
            if record.get("code_sha256") == code_sha256 and record.get("lang") == lang:
                return record
        return None

    def lookup(
        self, *, code_sha256: str, lang: str, baseline_component: str,
        toolchain_fp: str, runners_module_version: str, platform: "str | None" = None,
    ) -> "dict[str, Any] | None":
        """Exact-key O(1) lookup (head_cache() first, falling back to a full
        read_latest_by_key() scan if the sidecar is missing or doesn't have this
        key -- e.g. a hand-edited jsonl, or a sidecar lost/corrupted independently
        of the append-only file it mirrors)."""
        key = ledger_key(
            code_sha256, lang, platform or self.platform, baseline_component,
            toolchain_fp, runners_module_version,
        )
        cached = self.head_cache().get(key)
        if cached is not None:
            return cached
        return self.read_latest_by_key().get(key)

    def check_proof(
        self, *, code_sha256: str, lang: str, current_baseline_component: "str | None" = None,
        current_toolchain_fp: "str | None" = None, current_runners_module_version: "str | None" = None,
    ) -> "tuple[dict[str, Any] | None, str | None]":
        """Answer "has this exact block already been proven, and is that proof
        still fresh" -- item 3b of TC-07. Returns (entry, reason): entry is None
        with reason "no-proof" if nothing was ever recorded for this
        (code_sha256, lang); otherwise entry is the latest record found via
        find_latest_by_content() and reason is stale_reason()'s verdict (None means
        fresh)."""
        entry = self.find_latest_by_content(code_sha256, lang)
        if entry is None:
            return None, "no-proof"
        reason = stale_reason(
            entry, current_baseline_component=current_baseline_component,
            current_toolchain_fp=current_toolchain_fp,
            current_runners_module_version=current_runners_module_version,
        )
        return entry, reason

    # ── Writes ───────────────────────────────────────────────────────────

    def append(self, record: "dict[str, Any]") -> "dict[str, Any]":
        """Append one schema-validated row and refresh the head-cache sidecar for
        its key. Never rewrites existing lines or existing sidecar entries for
        OTHER keys -- purely additive, matching taskcard_store.py's append()
        (blind append; each call adds one row/fact, not a CAS). family/platform are
        auto-filled from this store if absent from record; a record whose own
        family/platform disagrees with this store's is rejected (one ledger file
        belongs to exactly one product, same rule taskcard_store.py applies to
        mission_id).

        Raises ValueError if the record fails schema validation (including the
        durable-proof gate -- see module docstring), LedgerLockTimeout if the
        product's lock cannot be acquired within the timeout.
        """
        record = dict(record)
        record.setdefault("family", self.family)
        record.setdefault("platform", self.platform)
        if record["family"] != self.family:
            raise ValueError(
                f"record family {record['family']!r} does not match this store's family {self.family!r}"
            )
        if record["platform"] != self.platform:
            raise ValueError(
                f"record platform {record['platform']!r} does not match this store's platform {self.platform!r}"
            )
        errors = _validate_ledger_record(record)
        if errors:
            raise ValueError(f"invalid ledger record, refusing to write: {errors}")

        self._acquire_lock()
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
            self._update_head_cache(record)
            return record
        finally:
            self._release_lock()

    def _update_head_cache(self, record: "dict[str, Any]") -> None:
        """Merge `record` into the head-cache sidecar under its own key. Called
        while the caller (append()) already holds the lock -- never acquires it
        itself, mirroring baseline_ledger.py's head_path.write_text() call inside
        its own locked append()."""
        cache = self.head_cache()
        cache[record["key"]] = record
        self.head_path.parent.mkdir(parents=True, exist_ok=True)
        self.head_path.write_text(json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8")

    def record_result(
        self, report: Any, block: Any, *, run_id: str, recorded_at: "str | None" = None,
    ) -> "dict[str, Any] | None":
        """Convenience wrapper over append(): derive a schema-valid ledger record
        from a real `example_verification.result.VerificationReport` +
        `BlockResult` and append it -- item 3a of TC-07. Returns None (skipped, not
        an error) if `block.is_cacheable()` is False, matching
        lib/example_verification/cache.py::ResultCache.put()'s own "not every
        outcome is durable" contract."""
        if not block.is_cacheable():
            return None
        baseline_component, baseline_kind = resolve_baseline_component(
            report.clone_head, getattr(report, "package_version", None),
        )
        toolchain_fp = resolve_toolchain_fp(block.toolchain_name, block.toolchain_version)
        code_sha256 = block.identity.code_sha256
        lang = block.identity.lang
        runners_module_version = report.runners_module_version
        record: "dict[str, Any]" = {
            "schema_version": LEDGER_SCHEMA_VERSION,
            "run_id": run_id,
            "family": self.family,
            "platform": self.platform,
            "code_sha256": code_sha256,
            "lang": lang,
            "baseline_component": baseline_component,
            "baseline_kind": baseline_kind,
            "toolchain_fp": toolchain_fp,
            "runners_module_version": runners_module_version,
            "proof_tier": block.proof_tier,
            "status": block.status,
            "reason": block.reason if block.status == "BLOCKED-WITH-REASON" else None,
            "detail": block.detail,
            "recorded_at": recorded_at or _now_iso(),
        }
        record["key"] = ledger_key(
            code_sha256, lang, self.platform, baseline_component, toolchain_fp, runners_module_version,
        )
        return self.append(record)
