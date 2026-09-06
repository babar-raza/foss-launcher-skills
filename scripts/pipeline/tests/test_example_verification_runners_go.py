"""Tests for lib/example_verification/runners/go.py's GoRunner (C5 checkpoint 2):
the first concrete `runners/base.py` LanguageRunner implementation.

Real acquire->compile(`go vet`)->execute(`go run`) is the check (never mocked) --
uses only stdlib (`fmt`/`os`), fully offline-installable, so these tests need no
network and no product-specific clone cache, matching the governing plan's own
"fully offline-installable synthetic projects... stdlib-only Go module" guidance
for Go/.NET test fixtures. Requires a real `go` toolchain on PATH (confirmed
present via the plan's own "Verified toolchain inventory").
"""
from __future__ import annotations

import shutil

import pytest

from lib.example_verification.policy import Policy, ProductContext
from lib.example_verification.runners.base import BaseRunner
from lib.example_verification.runners.go import GoRunner

pytestmark = pytest.mark.skipif(shutil.which("go") is None, reason="go toolchain not on PATH")


def _acquired(work_dir):
    """A fake acquire() result for a stdlib-only block -- no product module,
    no replace directive, hermetic regardless of the real machine's clone cache."""
    return {"work_dir": work_dir, "module_path": "example.com/no-such-module", "replace_path": None}


class TestStartsChain:
    def test_package_line_starts_a_new_chain(self):
        runner = GoRunner(family="no-such-family")
        assert runner.starts_chain("package main\n\nfunc main() {}")

    def test_import_line_starts_a_new_chain(self):
        runner = GoRunner(family="no-such-family")
        assert runner.starts_chain('import "fmt"\n\nfmt.Println("hi")')

    def test_plain_statement_continues_the_previous_chain(self):
        runner = GoRunner(family="no-such-family")
        assert not runner.starts_chain('fmt.Println("continuing")')

    def test_leading_comment_is_skipped_before_deciding(self):
        runner = GoRunner(family="no-such-family")
        assert runner.starts_chain('// a comment\npackage main')


class TestConstructionFallback:
    def test_falls_back_to_pdf_go_default_when_family_has_no_model_yaml(self):
        runner = GoRunner(family="definitely-not-a-real-product")
        assert runner._module_path == "github.com/aspose-pdf-foss/aspose-pdf-foss-for-go"
        assert runner._extra_heuristics == []


class TestClassify:
    def test_error_citing_the_replace_target_is_upstream_broken(self):
        runner = GoRunner(family="no-such-family")
        replace_path = "D:/clones/aspose_pdf_go"
        output = f"{replace_path}/writer.go:42: undefined: someInternalHelper"
        reason, detail = runner.classify(output, {"stage": "compile", "replace_path": replace_path})
        assert reason == "UPSTREAM-BROKEN"
        assert detail == output

    def test_error_in_the_generated_wrapper_is_a_compile_error(self):
        runner = GoRunner(family="no-such-family")
        reason, _ = runner.classify("./main.go:4:2: undefined: notAThing", {"stage": "compile"})
        assert reason == "COMPILE-ERROR"

    def test_error_at_execute_stage_is_a_runtime_error(self):
        runner = GoRunner(family="no-such-family")
        reason, _ = runner.classify("panic: boom", {"stage": "execute"})
        assert reason == "RUNTIME-ERROR"


class TestCompileRealGoVet:
    def test_clean_stdlib_code_compiles(self, tmp_path):
        runner = GoRunner(family="no-such-family")
        result = runner.compile(_acquired(tmp_path), 'fmt.Println("hello")', 0)
        assert result is None

    def test_undefined_identifier_is_a_real_compile_error(self, tmp_path):
        runner = GoRunner(family="no-such-family")
        result = runner.compile(_acquired(tmp_path), 'notARealFunction()', 0)
        assert result is not None
        assert result["reason"] == "COMPILE-ERROR"
        assert "notARealFunction" in result["detail"]


class TestExecuteRealGoRun:
    def test_clean_stdlib_code_runs_and_passes(self, tmp_path):
        runner = GoRunner(family="no-such-family")
        result = runner.execute(_acquired(tmp_path), 'fmt.Println("hello from go run")', 0)
        assert result == {"status": "PASS"}

    def test_runtime_panic_is_a_real_runtime_error(self, tmp_path):
        runner = GoRunner(family="no-such-family")
        code = 'x := 0\n\ty := 1 / x\n\tfmt.Println(y)'
        result = runner.execute(_acquired(tmp_path), code, 0)
        assert result["status"] == "BLOCKED-WITH-REASON"
        assert result["reason"] == "RUNTIME-ERROR"
        assert "panic" in result["detail"].lower() or "divide" in result["detail"].lower()


class TestEndToEndViaBaseRunner:
    """The real, whole-ladder proof: BaseRunner(GoRunner(...)).run(...) against
    real blocks, exactly the call shape a future C7-style dispatch wiring would
    use -- proof_tier reaches 3 for clean code via real go vet + real go run."""

    def test_single_clean_block_reaches_tier_3(self, tmp_path):
        runner = GoRunner(family="no-such-family")
        base = BaseRunner(runner)
        blocks = [("sha-0", (1, 1), 'fmt.Println("integration test")')]
        results = base.run(blocks, Policy(max_tier=3, allow_acquire=True), ProductContext())
        assert len(results) == 1
        assert results[0].status == "PASS"
        assert results[0].proof_tier == 3

    def test_a_compile_failure_still_names_the_real_go_vet_error(self, tmp_path):
        runner = GoRunner(family="no-such-family")
        base = BaseRunner(runner)
        blocks = [("sha-0", (1, 1), 'thisFunctionDoesNotExist()')]
        results = base.run(blocks, Policy(max_tier=3, allow_acquire=True), ProductContext())
        assert results[0].status == "BLOCKED-WITH-REASON"
        assert results[0].reason == "COMPILE-ERROR"
