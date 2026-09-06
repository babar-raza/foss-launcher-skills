"""
lib/example_verification/result.py

CONTRACT: scripts/pipeline/lib/example_verification/result.py
  purpose: the shared result schema every consumer of this package reads --
           BlockIdentity, BlockResult, VerificationReport -- plus adapters
           that translate a BlockResult/VerificationReport back into the
           exact dict shapes S-120's `readme_refresh_run.py` and S-63's
           `smoke_test.py` already assert in their own test suites, so
           rollout steps C3/C4/C7 can swap those modules' internals onto
           this package without changing what either module's tests (or
           downstream callers) see.
  inputs:  produced by runners/api.py (landing in later rollout steps);
           this module only defines the schema and pure adapter functions.
  outputs: BlockResult, VerificationReport, to_legacy_s120(), to_smoke()
  owner_domain: content-quality

Status/reason vocabulary (governing plan, Central module section):
  status ∈ {PASS, BLOCKED-WITH-REASON, NOT-EXECUTABLE-LANG, NOT-VERIFIED}
  reason (when status == BLOCKED-WITH-REASON) -- S-120's nine original
    reasons verbatim, plus this package's additions:
    TOOLCHAIN-UNAVAILABLE, RUNTIME-ERROR, UPSTREAM-BROKEN, TYPE-CHECK-FAILED,
    DEPENDS-ON-FAILED-BLOCK, ACQUIRE-FAILED, TIMEOUT, FIXTURE-UNAVAILABLE,
    NOT-A-PRODUCT-COMMAND (S-120 originals, confirmed verbatim against
    readme_refresh_run.py's own literals -- a prior draft of this set
    substituted NO-CLONE-CACHE/BUDGET-EXHAUSTED here by mistake; those two
    are package additions, not S-120 originals, fixed below) +
    GRAMMAR-UNAVAILABLE, SYNTAX-ERROR, COMPILE-ERROR, VERSION-SKEW, SLOW,
    ACQUIRE-SKIPPED, NO-CLONE-CACHE, BUDGET-EXHAUSTED, BUILD-VERIFIED-ONLY
    (this package's additions).
  proof_tier ∈ {0 (none/stub), 1 (syntax-parsed), 2 (compiled/type-checked),
    3 (executed, exit 0), 4 (reserved -- output/artifact assertion, not
    built in this plan)}.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

STATUSES: frozenset[str] = frozenset({
    "PASS", "BLOCKED-WITH-REASON", "NOT-EXECUTABLE-LANG", "NOT-VERIFIED",
})

# Every reason this package (or the S-120 code it will absorb in C3) can
# report. Kept as one flat set rather than per-status subsets because a
# reason's home status never changes across this codebase's history.
REASONS: frozenset[str] = frozenset({
    # S-120 originals (readme_refresh_run.py, verbatim -- confirmed by
    # grepping every "[A-Z-]+" literal in that file: exactly these 9)
    "TOOLCHAIN-UNAVAILABLE", "RUNTIME-ERROR", "UPSTREAM-BROKEN",
    "TYPE-CHECK-FAILED", "DEPENDS-ON-FAILED-BLOCK", "ACQUIRE-FAILED",
    "TIMEOUT", "FIXTURE-UNAVAILABLE", "NOT-A-PRODUCT-COMMAND",
    # This package's additions (Rounds 2-4)
    "GRAMMAR-UNAVAILABLE", "SYNTAX-ERROR", "COMPILE-ERROR", "VERSION-SKEW",
    "SLOW", "ACQUIRE-SKIPPED", "NO-CLONE-CACHE", "BUDGET-EXHAUSTED",
    "BUILD-VERIFIED-ONLY",
})

ORIGINS: frozenset[str] = frozenset({
    "upstream_verbatim", "reframed", "corrected", "new", "unknown",
})

PROVENANCES: frozenset[str] = frozenset({"executed", "cache", "snippet-index"})

# Outcomes stable enough to cache indefinitely (never a machine- or
# time-dependent status) -- see cache.py's key/never-cache-list contract.
DETERMINISTIC_STATUSES_FOR_CACHE: frozenset[str] = frozenset({
    "PASS",
})
DETERMINISTIC_REASONS_FOR_CACHE: frozenset[str] = frozenset({
    "SYNTAX-ERROR", "COMPILE-ERROR", "RUNTIME-ERROR", "UPSTREAM-BROKEN",
    "TYPE-CHECK-FAILED", "DEPENDS-ON-FAILED-BLOCK", "NOT-A-PRODUCT-COMMAND",
})
# FIXTURE-UNAVAILABLE is deliberately NOT here: like NO-CLONE-CACHE, it's a
# property of the acquire-time workspace, not of the block's own content --
# caching it would let a transient staging problem outlive its cause.


@dataclass(frozen=True, slots=True)
class BlockIdentity:
    """Content-keyed identity for one code block (Round 3 C). `index` is
    advisory only -- it shifts when an unrelated block is inserted above;
    `code_sha256` is what acceptance and cross-run comparison key on."""

    code_sha256: str
    lang: str
    index: int
    start_line: int
    end_line: int


@dataclass(slots=True)
class BlockResult:
    """One code block's verification outcome."""

    identity: BlockIdentity
    status: str
    reason: str | None = None
    detail: str = ""
    proof_tier: int = 0
    origin: str = "unknown"
    provenance: str = "executed"
    toolchain_name: str | None = None
    toolchain_version: str | None = None
    toolchain_path: str | None = None
    elapsed_seconds: float | None = None
    chain_id: int | None = None
    chain_position: int | None = None
    depends_on: int | None = None
    attribution: str | None = None
    continues_example: bool = False
    commands_run: int | None = None

    def __post_init__(self) -> None:
        if self.status not in STATUSES:
            raise ValueError(f"BlockResult: invalid status {self.status!r}")
        if self.status == "BLOCKED-WITH-REASON" and self.reason not in REASONS:
            raise ValueError(f"BlockResult: invalid reason {self.reason!r} for BLOCKED-WITH-REASON")
        if self.origin not in ORIGINS:
            raise ValueError(f"BlockResult: invalid origin {self.origin!r}")
        if self.provenance not in PROVENANCES:
            raise ValueError(f"BlockResult: invalid provenance {self.provenance!r}")

    def is_cacheable(self) -> bool:
        """True if this outcome is deterministic enough to persist in
        cache.py's ResultCache -- never a timing/acquire/toolchain-discovery
        outcome, per this module's DETERMINISTIC_*_FOR_CACHE sets."""
        if self.status in DETERMINISTIC_STATUSES_FOR_CACHE:
            return True
        if self.status == "BLOCKED-WITH-REASON" and self.reason in DETERMINISTIC_REASONS_FOR_CACHE:
            return True
        return False


@dataclass(slots=True)
class VerificationReport:
    """The whole-candidate report: every block's result plus run metadata."""

    runner: str
    blocks: list[BlockResult] = field(default_factory=list)
    runners_module_version: str = "1"
    clone_head: str | None = None
    package: str | None = None
    package_version: str | None = None
    install_source: str | None = None

    @property
    def blocks_found(self) -> int:
        return len(self.blocks)

    @property
    def all_named(self) -> bool:
        """True once every block has a status -- S-120's original gate.
        Kept here verbatim: Round 2 (RC2) found this gate non-enforcing
        precisely because it never checks *what* the status is, only that
        one was assigned; fixing that is Phase 1, not this module's job."""
        return all(b.status in STATUSES for b in self.blocks)

    @property
    def tier_histogram(self) -> dict[int, int]:
        hist: dict[int, int] = {}
        for b in self.blocks:
            hist[b.proof_tier] = hist.get(b.proof_tier, 0) + 1
        return hist

    def to_legacy_s120(self) -> dict[str, Any]:
        """Produce the exact dict shape S-120's own tests assert (see
        test_readme_refresh_run.py, e.g. `{"index": 0, "status": "COMPILED+RAN
        CLEAN"}` for a clean tier-3 execution, `{"index": .., "status":
        "BLOCKED-WITH-REASON", "reason": .., "detail": ..}` otherwise).
        A block reaches tier 3 with no reason and gets the legacy
        "COMPILED+RAN CLEAN" label; every other status stays
        "BLOCKED-WITH-REASON" using this module's own reason vocabulary,
        which is already S-120's vocabulary plus this package's additions."""
        blocks_out: list[dict[str, Any]] = []
        for b in self.blocks:
            if b.status == "PASS" and b.proof_tier >= 3:
                entry: dict[str, Any] = {"index": b.identity.index, "status": "COMPILED+RAN CLEAN"}
                if b.continues_example:
                    entry["continues_example"] = True
                if b.commands_run is not None:
                    entry["commands_run"] = b.commands_run
                blocks_out.append(entry)
                continue
            reason = b.reason if b.status == "BLOCKED-WITH-REASON" else "TOOLCHAIN-UNAVAILABLE"
            blocks_out.append({
                "index": b.identity.index,
                "status": "BLOCKED-WITH-REASON",
                "reason": reason,
                "detail": b.detail,
            })
        return {
            "runner": self.runner,
            "blocks_found": self.blocks_found,
            "all_named": self.all_named,
            "blocks": blocks_out,
        }

    def to_smoke(self) -> dict[str, Any]:
        """Produce smoke_test.py's BlockResult-shaped view: PASS/WARN/FAIL
        per block (tier-1-only semantics -- smoke_test.py never executes)."""
        blocks_out: list[dict[str, Any]] = []
        pass_count = warn_count = fail_count = 0
        for b in self.blocks:
            if b.status == "PASS":
                status = "PASS"
                pass_count += 1
            elif b.reason == "GRAMMAR-UNAVAILABLE":
                status = "WARN"
                warn_count += 1
            elif b.status == "NOT-EXECUTABLE-LANG":
                continue
            else:
                status = "FAIL"
                fail_count += 1
            blocks_out.append({
                "block_index": b.identity.index,
                "start_line": b.identity.start_line,
                "status": status,
                "message": b.detail,
            })
        return {
            "blocks_checked": len(blocks_out),
            "pass_count": pass_count,
            "warn_count": warn_count,
            "fail_count": fail_count,
            "results": blocks_out,
        }
