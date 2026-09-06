"""Tests for lib/example_verification/runners/base.py (rollout step C3
fast-follow): the shared tier ladder every future per-language runner
(C5 Go/.NET, C11-C14 Java/Rust/C++) climbs by implementing only the
5-method `LanguageRunner` protocol.

Uses a synthetic toy runner (real tier-1 syntax checking via a real,
already-registered language -- "python" -- so the real tree-sitter loader
is genuinely exercised, but a FAKE acquire/compile/execute so this suite
never spawns a real subprocess/venv/network call) rather than exercising
runners/python.py or runners/typescript.py -- those are already faithful,
parity-proven ports of live production code, and this new, only
synthetically-tested base class is deliberately NOT retrofitted onto them
in the same step (see runners/base.py's own module docstring).
"""
from __future__ import annotations

from pathlib import Path

from lib.example_verification.cache import ResultCache
from lib.example_verification.policy import Policy, ProductContext
from lib.example_verification.runners.base import BaseRunner, LanguageRunner, RunOptions


class FakeRunner:
    """A synthetic LanguageRunner: real canonical_lang ("python", so tier-1
    syntax checking is real), but fully scripted acquire/compile/execute
    results, controlled per-test via the `scripted_*` dicts keyed by
    block index."""

    canonical_lang = "python"
    ceiling_tier = 3

    def __init__(self) -> None:
        self.acquire_result: dict = {"ok": True, "detail": "fake env ready"}
        self.compile_results: "dict[int, dict | None]" = {}
        self.execute_results: "dict[int, dict]" = {}
        self.acquire_calls = 0
        self.compile_calls: list[int] = []
        self.execute_calls: list[int] = []

    def starts_chain(self, code: str) -> bool:
        return code.lstrip().startswith(("import ", "from "))

    def acquire(self, work_dir: Path, policy: Policy, product: ProductContext) -> dict:
        self.acquire_calls += 1
        return self.acquire_result

    def compile(self, acquired: dict, code: str, index: int) -> "dict | None":
        self.compile_calls.append(index)
        return self.compile_results.get(index)

    def execute(self, acquired: dict, code: str, index: int) -> dict:
        self.execute_calls.append(index)
        return self.execute_results.get(index, {"status": "PASS"})

    def classify(self, output: str, context: "dict | None" = None) -> "tuple[str, str]":
        return "RUNTIME-ERROR", output


def _blocks(*codes: str) -> "list[tuple[str, tuple[int, int], str]]":
    return [(f"sha-{i}", (i + 1, i + 1), code) for i, code in enumerate(codes)]


def test_grammar_unavailable_never_reaches_acquire():
    class UnknownLangRunner(FakeRunner):
        canonical_lang = "cobol"

    runner = UnknownLangRunner()
    base = BaseRunner(runner)
    results = base.run(_blocks("ANYTHING GOES HERE."), Policy(max_tier=3, allow_acquire=True), ProductContext())
    assert results[0].status == "BLOCKED-WITH-REASON"
    assert results[0].reason == "GRAMMAR-UNAVAILABLE"
    assert results[0].proof_tier == 0
    assert runner.acquire_calls == 0


def test_syntax_error_never_reaches_acquire():
    runner = FakeRunner()
    base = BaseRunner(runner)
    results = base.run(_blocks("def f(\n    pass\nreturn 1 +"), Policy(max_tier=3, allow_acquire=True), ProductContext())
    assert results[0].status == "BLOCKED-WITH-REASON"
    assert results[0].reason == "SYNTAX-ERROR"
    assert results[0].proof_tier == 1
    assert runner.acquire_calls == 0


def test_max_tier_1_stops_at_syntax_pass_never_acquires():
    runner = FakeRunner()
    base = BaseRunner(runner)
    results = base.run(_blocks("import os\nprint(os.getcwd())"), Policy(max_tier=1, allow_acquire=True), ProductContext())
    assert results[0].status == "PASS"
    assert results[0].proof_tier == 1
    assert runner.acquire_calls == 0


def test_allow_acquire_false_stops_at_syntax_pass():
    runner = FakeRunner()
    base = BaseRunner(runner)
    results = base.run(_blocks("import os\nprint(1)"), Policy(max_tier=3, allow_acquire=False), ProductContext())
    assert results[0].status == "PASS"
    assert results[0].proof_tier == 1
    assert runner.acquire_calls == 0


def test_full_tier_3_execution_pass():
    runner = FakeRunner()
    runner.execute_results[0] = {"status": "COMPILED+RAN CLEAN"}
    base = BaseRunner(runner)
    results = base.run(_blocks("import os\nprint(1)"), Policy(max_tier=3, allow_acquire=True), ProductContext())
    assert results[0].status == "PASS"
    assert results[0].proof_tier == 3
    assert runner.acquire_calls == 1
    assert runner.execute_calls == [0]


def test_acquire_failure_reports_acquire_failed():
    runner = FakeRunner()
    runner.acquire_result = {"ok": False, "detail": "no venv could be built"}
    base = BaseRunner(runner)
    results = base.run(_blocks("import os\nprint(1)"), Policy(max_tier=3, allow_acquire=True), ProductContext())
    assert results[0].status == "BLOCKED-WITH-REASON"
    assert results[0].reason == "ACQUIRE-FAILED"
    assert "no venv" in results[0].detail
    assert runner.execute_calls == []


def test_compile_failure_stops_before_execute():
    runner = FakeRunner()
    runner.compile_results[0] = {"reason": "TYPE-CHECK-FAILED", "detail": "type error on line 3"}
    base = BaseRunner(runner)
    results = base.run(_blocks("import os\nprint(1)"), Policy(max_tier=3, allow_acquire=True), ProductContext())
    assert results[0].status == "BLOCKED-WITH-REASON"
    assert results[0].reason == "TYPE-CHECK-FAILED"
    assert results[0].proof_tier == 2
    assert runner.execute_calls == []


def test_max_tier_2_stops_after_compile_never_executes():
    runner = FakeRunner()
    base = BaseRunner(runner)
    results = base.run(_blocks("import os\nprint(1)"), Policy(max_tier=2, allow_acquire=True), ProductContext())
    assert results[0].status == "PASS"
    assert results[0].proof_tier == 2
    assert runner.compile_calls == [0]
    assert runner.execute_calls == []


def test_execute_failure_reports_runtime_error():
    runner = FakeRunner()
    runner.execute_results[0] = {"status": "BLOCKED-WITH-REASON", "reason": "RUNTIME-ERROR", "detail": "boom"}
    base = BaseRunner(runner)
    results = base.run(_blocks("import os\nprint(1)"), Policy(max_tier=3, allow_acquire=True), ProductContext())
    assert results[0].status == "BLOCKED-WITH-REASON"
    assert results[0].reason == "RUNTIME-ERROR"
    assert results[0].proof_tier == 3


def test_chain_grouping_depends_on_failed_block():
    runner = FakeRunner()
    runner.execute_results[0] = {"status": "BLOCKED-WITH-REASON", "reason": "RUNTIME-ERROR", "detail": "boom"}
    base = BaseRunner(runner)
    results = base.run(
        _blocks("import os\nprint(1)", "print(os.getcwd())"),
        Policy(max_tier=3, allow_acquire=True), ProductContext(),
    )
    assert results[0].status == "BLOCKED-WITH-REASON"
    assert results[1].status == "BLOCKED-WITH-REASON"
    assert results[1].reason == "DEPENDS-ON-FAILED-BLOCK"
    assert results[1].depends_on == 0
    # The continuation block must never reach acquire/execute at all.
    assert runner.execute_calls == [0]


def test_new_chain_after_failure_is_independent():
    runner = FakeRunner()
    runner.execute_results[0] = {"status": "BLOCKED-WITH-REASON", "reason": "RUNTIME-ERROR", "detail": "boom"}
    runner.execute_results[1] = {"status": "COMPILED+RAN CLEAN"}
    base = BaseRunner(runner)
    results = base.run(
        _blocks("import os\nprint(1)", "import sys\nprint(2)"),
        Policy(max_tier=3, allow_acquire=True), ProductContext(),
    )
    assert results[0].status == "BLOCKED-WITH-REASON"
    assert results[1].status == "PASS"  # a fresh chain (starts with import) is unaffected
    assert runner.execute_calls == [0, 1]


def test_continuation_block_marked_continues_example():
    runner = FakeRunner()
    runner.execute_results[0] = {"status": "COMPILED+RAN CLEAN"}
    runner.execute_results[1] = {"status": "COMPILED+RAN CLEAN"}
    base = BaseRunner(runner)
    results = base.run(
        _blocks("import os\nx = 1", "print(x)"),
        Policy(max_tier=3, allow_acquire=True), ProductContext(),
    )
    assert results[0].continues_example is False
    assert results[1].continues_example is True


def test_cache_hit_skips_acquire_entirely(tmp_path):
    runner = FakeRunner()
    cache = ResultCache("testfam", "python", root=tmp_path)
    options = RunOptions(clone_head="head1", toolchain_fp="tc@1.0", runners_module_version="1")
    base = BaseRunner(runner, cache=cache)

    # First run: real (fake) execution, populates the cache.
    runner.execute_results[0] = {"status": "COMPILED+RAN CLEAN"}
    base.run(_blocks("import os\nprint(1)"), Policy(max_tier=3, allow_acquire=True), ProductContext(), options=options)
    assert runner.acquire_calls == 1

    # Second run, same content/clone_head/toolchain/runners_version: must
    # hit cache and never call acquire again.
    results = base.run(_blocks("import os\nprint(1)"), Policy(max_tier=3, allow_acquire=True), ProductContext(), options=options)
    assert results[0].status == "PASS"
    assert results[0].provenance == "cache"
    assert runner.acquire_calls == 1  # unchanged -- no second acquire


def test_cache_miss_on_different_clone_head(tmp_path):
    runner = FakeRunner()
    runner.execute_results[0] = {"status": "COMPILED+RAN CLEAN"}
    cache = ResultCache("testfam", "python", root=tmp_path)
    base = BaseRunner(runner, cache=cache)

    base.run(
        _blocks("import os\nprint(1)"), Policy(max_tier=3, allow_acquire=True), ProductContext(),
        options=RunOptions(clone_head="head1"),
    )
    base.run(
        _blocks("import os\nprint(1)"), Policy(max_tier=3, allow_acquire=True), ProductContext(),
        options=RunOptions(clone_head="head2"),
    )
    assert runner.acquire_calls == 2  # different clone_head -- must re-acquire, not reuse the stale cache entry


def test_without_a_cache_every_call_reexecutes():
    runner = FakeRunner()
    runner.execute_results[0] = {"status": "BLOCKED-WITH-REASON", "reason": "RUNTIME-ERROR", "detail": "boom"}
    base = BaseRunner(runner, cache=None)
    base.run(_blocks("import os\nprint(1)"), Policy(max_tier=3, allow_acquire=True), ProductContext())
    base.run(_blocks("import os\nprint(1)"), Policy(max_tier=3, allow_acquire=True), ProductContext())
    assert runner.acquire_calls == 2


def test_deterministic_failure_is_cached_and_reused(tmp_path):
    runner = FakeRunner()
    runner.execute_results[0] = {"status": "BLOCKED-WITH-REASON", "reason": "RUNTIME-ERROR", "detail": "boom"}
    cache = ResultCache("testfam", "python", root=tmp_path)
    base = BaseRunner(runner, cache=cache)
    options = RunOptions(clone_head="head1")

    base.run(_blocks("import os\nprint(1)"), Policy(max_tier=3, allow_acquire=True), ProductContext(), options=options)
    assert runner.acquire_calls == 1

    results = base.run(_blocks("import os\nprint(1)"), Policy(max_tier=3, allow_acquire=True), ProductContext(), options=options)
    assert results[0].status == "BLOCKED-WITH-REASON"
    assert results[0].reason == "RUNTIME-ERROR"
    assert results[0].provenance == "cache"
    assert runner.acquire_calls == 1  # unchanged -- the cached failure was reused, not re-executed


def test_chain_continuation_cache_key_reflects_chain_prefix_not_just_own_hash(tmp_path):
    # Regression test for a real bug found by independent review: a
    # continuation block's cache key used to be keyed on ONLY its own
    # code_sha256, ignoring chain_prefix -- but the actual unit that gets
    # compiled/executed for a continuation block is `chain_prefix + code`
    # (see BaseRunner._climb). A byte-identical continuation block must
    # NOT reuse a stale cache entry from a run where an EARLIER block in
    # the same chain had different content.
    cache = ResultCache("testfam", "python", root=tmp_path)
    options = RunOptions(clone_head="head1")

    head_v1 = "import os\nhelper_val = 1"
    continuation = "assert helper_val == 1"  # only ever valid if helper_val == 1

    runner1 = FakeRunner()
    runner1.execute_results[0] = {"status": "COMPILED+RAN CLEAN"}
    runner1.execute_results[1] = {"status": "COMPILED+RAN CLEAN"}
    base1 = BaseRunner(runner1, cache=cache)
    r1 = base1.run(_blocks(head_v1, continuation), Policy(max_tier=3, allow_acquire=True), ProductContext(), options=options)
    assert r1[0].status == "PASS"
    assert r1[1].status == "PASS"

    # Second run: the chain HEAD changes (helper_val = 2), but the
    # continuation block's own text is byte-identical to run 1. The real
    # concatenated script for the continuation is now different
    # ("helper_val = 2\nassert helper_val == 1" would actually fail) --
    # the fake runner models this explicitly via execute_results[1].
    head_v2 = "import os\nhelper_val = 2"
    runner2 = FakeRunner()
    runner2.execute_results[0] = {"status": "COMPILED+RAN CLEAN"}
    runner2.execute_results[1] = {"status": "BLOCKED-WITH-REASON", "reason": "RUNTIME-ERROR", "detail": "AssertionError"}
    base2 = BaseRunner(runner2, cache=cache)
    r2 = base2.run(_blocks(head_v2, continuation), Policy(max_tier=3, allow_acquire=True), ProductContext(), options=options)

    assert r2[0].status == "PASS"  # head changed -> new hash -> correctly re-executed
    # The continuation block must be RE-EXECUTED (chain prefix changed),
    # never silently served run 1's stale cached PASS.
    assert 1 in runner2.execute_calls, "continuation block was never re-executed -- stale cache hit"
    assert r2[1].status == "BLOCKED-WITH-REASON"
    assert r2[1].reason == "RUNTIME-ERROR"
    assert r2[1].provenance != "cache"


def test_language_runner_is_a_runtime_checkable_protocol():
    runner = FakeRunner()
    assert isinstance(runner, LanguageRunner)
