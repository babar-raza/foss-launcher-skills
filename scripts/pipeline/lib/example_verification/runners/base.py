"""
lib/example_verification/runners/base.py

CONTRACT: scripts/pipeline/lib/example_verification/runners/base.py
  purpose: the shared tier ladder every per-language runner climbs
           (syntax -> cache -> acquire -> chain grouping -> compile ->
           execute), implemented once here so C5 (Go/.NET) and C11-C14
           (Java/Rust/C++) implement only the `LanguageRunner` protocol's
           5 language-specific methods instead of each reinventing this
           orchestration -- exactly what the governing plan's rollout
           section names C5 as depending on ("Implement on runners/
           base.py, not as triads inside readme_refresh_run.py").
           `runners/python.py`/`runners/typescript.py` (rollout step C3,
           already shipped and proven at real end-to-end parity against
           S-120) are NOT retrofitted onto this base class in this same
           step -- they are faithful ports of already-live, already-tested
           production code, and retrofitting proven code onto a
           brand-new, only-synthetically-tested abstraction in the same
           commit would risk exactly the regression this taskcard's own
           promotion gate exists to catch. A future taskcard can retrofit
           both once 3+ concrete runners exist to derive the real shape
           from (matching this package's own stated design philosophy:
           build the abstraction from observed duplication, not guessed
           ahead of it).
  inputs:  a LanguageRunner implementation + one candidate's fenced blocks
  outputs: BaseRunner.run(blocks, policy, product) -> list[BlockResult]
  owner_domain: content-quality

Deliberately does NOT implement Round 3 F's single-execution-chain-with-
sentinel-markers redesign (that is explicit Phase 2 scope, not yet its
own taskcard) -- chain grouping here uses the same n^2-per-chain
re-execution already proven in runners/python.py/typescript.py ("behind
parity" is this whole taskcard's mandate; inventing a different chain
strategy in the one module every future runner builds on would silently
commit every later runner to an untested design before Phase 2 exists).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from .. import syntax as syntax_mod
from ..cache import CacheEntry, ResultCache, cache_key
from ..policy import Policy, ProductContext
from ..result import BlockIdentity, BlockResult


@runtime_checkable
class LanguageRunner(Protocol):
    """What a per-language runner (C5/C11-C14) must implement. `BaseRunner`
    supplies everything else (syntax tier, cache, chain grouping)."""

    canonical_lang: str
    ceiling_tier: int  # highest proof_tier this runner can ever report

    def starts_chain(self, code: str) -> bool:
        """True if `code` is a self-contained example (starts a new
        chain); False if it continues the previous block's chain."""
        ...

    def acquire(self, work_dir: Path, policy: Policy, product: ProductContext) -> dict:
        """Prepare a disposable environment. Returns at least {"ok": bool,
        "detail": str}; runner-specific extra keys (e.g. "venv_python",
        "project_dir") are passed back into compile()/execute() verbatim
        via the same dict."""
        ...

    def compile(self, acquired: dict, code: str, index: int) -> "dict | None":
        """Tier-2 compile/type-check step, or None if this runner has no
        separate compile tier (tier-3-only runners, like Python).
        Returns None on success, or a BlockResult-shaped failure dict on
        failure (status/reason/detail)."""
        ...

    def execute(self, acquired: dict, code: str, index: int) -> dict:
        """Tier-3 real execution. Returns a BlockResult-shaped dict:
        {"status": "PASS", ...} on success, or {"status":
        "BLOCKED-WITH-REASON", "reason": ..., "detail": ...} on failure."""
        ...

    def classify(self, output: str, context: "dict | None" = None) -> "tuple[str, str]":
        """(reason, detail) for one failure's raw output -- e.g.
        distinguishing UPSTREAM-BROKEN from RUNTIME-ERROR."""
        ...


@dataclass(frozen=True, slots=True)
class RunOptions:
    allow_acquire: bool = True
    use_cache: bool = True
    clone_head: str = ""
    toolchain_fp: str = ""
    runners_module_version: str = "1"


class BaseRunner:
    """Climbs the tier ladder for one language's blocks: syntax (tier 1,
    via the shared syntax.py loader) -> cache lookup -> acquire -> chain
    grouping -> compile -> execute -> BlockResult. A concrete runner
    (e.g. runners/go.py, C5) constructs this with its own `LanguageRunner`
    implementation and calls `run()`."""

    def __init__(self, language_runner: LanguageRunner, cache: "ResultCache | None" = None) -> None:
        self.runner = language_runner
        self.cache = cache

    def run(
        self, blocks: "list[tuple[str, str, str]]", policy: Policy, product: ProductContext,
        *, options: "RunOptions | None" = None,
    ) -> list[BlockResult]:
        """`blocks` is a list of `(code_sha256, start_line_and_end_line_key, code)`
        -- callers pass whatever identity tuple they already have; this
        method assigns `index` positionally in the order given, matching
        every existing runner's own indexing convention."""
        opts = options or RunOptions()
        results: list[BlockResult] = []
        chain_prefix: list[str] = []
        chain_failed_at: "int | None" = None

        for index, (code_sha256, line_key, code) in enumerate(blocks):
            start_line, end_line = line_key
            identity = BlockIdentity(
                code_sha256=code_sha256, lang=self.runner.canonical_lang,
                index=index, start_line=start_line, end_line=end_line,
            )

            if self.runner.starts_chain(code):
                chain_prefix, chain_failed_at = [], None

            if chain_failed_at is not None:
                results.append(BlockResult(
                    identity=identity, status="BLOCKED-WITH-REASON", reason="DEPENDS-ON-FAILED-BLOCK",
                    detail=f"continues the example started in block {chain_failed_at}, which already failed",
                    depends_on=chain_failed_at,
                ))
                continue

            # Tier 1: syntax proof, always attempted (cheap, no acquire needed).
            syntax_result = syntax_mod.check_syntax(self.runner.canonical_lang, code)

            block_result = self._climb(
                identity, code, chain_prefix, policy, product, opts, syntax_result,
            )
            if block_result.status == "BLOCKED-WITH-REASON":
                chain_failed_at = index
            if chain_prefix:
                block_result.continues_example = True
            chain_prefix.append(code)
            results.append(block_result)

        return results

    def _cache_key_for(self, code_sha256: str, options: RunOptions) -> str:
        return cache_key(
            code_sha256, self.runner.canonical_lang, options.clone_head,
            options.toolchain_fp, options.runners_module_version,
        )

    def _climb(
        self, identity: BlockIdentity, code: str, chain_prefix: "list[str]",
        policy: Policy, product: ProductContext, options: RunOptions, syntax_result: Any,
    ) -> BlockResult:
        if syntax_result.status == "GRAMMAR-UNAVAILABLE":
            return BlockResult(
                identity=identity, status="BLOCKED-WITH-REASON", reason="GRAMMAR-UNAVAILABLE",
                detail=syntax_result.message, proof_tier=0,
            )
        if syntax_result.status == "SYNTAX-ERROR":
            return BlockResult(
                identity=identity, status="BLOCKED-WITH-REASON", reason="SYNTAX-ERROR",
                detail=syntax_result.message, proof_tier=1,
            )
        # PASS at tier 1 -- proceed up the ladder if the policy/runner allow it.
        if policy.max_tier <= 1:
            return BlockResult(identity=identity, status="PASS", proof_tier=1)

        if self.cache is not None and options.use_cache:
            key = self._cache_key_for(identity.code_sha256, options)
            cached = self.cache.get(key, policy.max_tier)
            if cached is not None:
                return self._entry_to_result(identity, cached)

        if not policy.allow_acquire or self.runner.ceiling_tier < 2:
            return BlockResult(identity=identity, status="PASS", proof_tier=1)

        with _disposable_dir() as work_dir:
            acquired = self.runner.acquire(work_dir, policy, product)
            if not acquired.get("ok"):
                return BlockResult(
                    identity=identity, status="BLOCKED-WITH-REASON", reason="ACQUIRE-FAILED",
                    detail=acquired.get("detail", ""), proof_tier=0,
                )

            script = "\n".join([*chain_prefix, code]) if chain_prefix else code

            compile_failure = self.runner.compile(acquired, script, identity.index)
            if compile_failure is not None:
                result = BlockResult(
                    identity=identity, status="BLOCKED-WITH-REASON",
                    reason=compile_failure.get("reason", "COMPILE-ERROR"),
                    detail=compile_failure.get("detail", ""), proof_tier=2,
                )
                self._maybe_cache(identity, options, result)
                return result

            if policy.max_tier < 3 or self.runner.ceiling_tier < 3:
                result = BlockResult(identity=identity, status="PASS", proof_tier=2)
                self._maybe_cache(identity, options, result)
                return result

            executed = self.runner.execute(acquired, script, identity.index)
            result = self._executed_to_result(identity, executed)
            self._maybe_cache(identity, options, result)
            return result

    def _executed_to_result(self, identity: BlockIdentity, executed: dict) -> BlockResult:
        if executed.get("status") == "PASS" or executed.get("status") == "COMPILED+RAN CLEAN":
            return BlockResult(identity=identity, status="PASS", proof_tier=3)
        return BlockResult(
            identity=identity, status="BLOCKED-WITH-REASON",
            reason=executed.get("reason", "RUNTIME-ERROR"),
            detail=executed.get("detail", ""), proof_tier=3,
        )

    def _entry_to_result(self, identity: BlockIdentity, entry: CacheEntry) -> BlockResult:
        return BlockResult(
            identity=identity, status=entry.status, reason=entry.reason,
            detail=entry.detail, proof_tier=entry.proof_tier, provenance="cache",
        )

    def _maybe_cache(self, identity: BlockIdentity, options: RunOptions, result: BlockResult) -> None:
        if self.cache is None or not result.is_cacheable():
            return
        key = self._cache_key_for(identity.code_sha256, options)
        self.cache.put(key, CacheEntry(
            status=result.status, proof_tier=result.proof_tier, reason=result.reason,
            detail=result.detail, clone_head=options.clone_head,
            toolchain_version=options.toolchain_fp, runners_module_version=options.runners_module_version,
            code_sha256=identity.code_sha256,
        ))


class _disposable_dir:
    """Thin wrapper over tempfile.TemporaryDirectory returning a Path."""

    def __enter__(self) -> Path:
        import tempfile
        self._tmp = tempfile.TemporaryDirectory(prefix="example-verification-")
        return Path(self._tmp.name)

    def __exit__(self, *exc_info: Any) -> None:
        self._tmp.cleanup()
