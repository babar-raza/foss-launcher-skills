"""Tests for lib/example_verification/runners/dotnet.py's DotNetRunner (C11):
the second concrete `runners/base.py` LanguageRunner implementation.

Real acquire (`dotnet new console`) -> compile (`dotnet build`) -> execute
(`dotnet run`) is the check (never mocked) -- uses only the BCL
(`Console.WriteLine`), fully offline-installable, so these tests need no
network and no product-specific clone cache, matching the governing plan's
own "bare zero-PackageReference console .csproj" test-fixture guidance.
Requires a real `dotnet` SDK on PATH (confirmed present via the plan's own
"Verified toolchain inventory", dotnet 10.0.204).
"""
from __future__ import annotations

import shutil

import pytest

from lib.example_verification.policy import Policy, ProductContext
from lib.example_verification.runners.base import BaseRunner
from lib.example_verification.runners.dotnet import DotNetRunner

pytestmark = pytest.mark.skipif(shutil.which("dotnet") is None, reason="dotnet SDK not on PATH")


def _acquired(tmp_path):
    """A real, scaffolded, reference-free project -- no product dependency,
    hermetic regardless of the real machine's clone cache."""
    runner = DotNetRunner(family="no-such-family")
    acquired = runner.acquire(tmp_path, Policy(max_tier=3, allow_acquire=True), ProductContext())
    assert acquired["ok"], acquired.get("detail")
    return runner, acquired


class TestStartsChain:
    def test_using_directive_starts_a_new_chain(self):
        runner = DotNetRunner(family="no-such-family")
        assert runner.starts_chain('using System;\n\nConsole.WriteLine("hi");')

    def test_plain_statement_continues_the_previous_chain(self):
        runner = DotNetRunner(family="no-such-family")
        assert not runner.starts_chain('Console.WriteLine("continuing");')

    def test_leading_comment_is_skipped_before_deciding(self):
        runner = DotNetRunner(family="no-such-family")
        assert runner.starts_chain('// a comment\nusing System;')


class TestClassify:
    """Design mirrors GoRunner.classify()'s own independent-review history:
    a file-citation-basename check, not a raw reference-path substring match
    (which doesn't appear verbatim in real MSBuild/runtime output either)."""

    def test_build_error_citing_a_non_program_cs_file_is_upstream_broken(self):
        runner = DotNetRunner(family="no-such-family")
        output = r"C:\clones\aspose_words_net\Lib.cs(4,2): error CS0103: undefined: Foo"
        reason, detail = runner.classify(output, {"stage": "compile"})
        assert reason == "UPSTREAM-BROKEN"
        assert detail == output

    def test_build_error_in_program_cs_is_a_compile_error(self):
        runner = DotNetRunner(family="no-such-family")
        output = r"C:\tmp\x\Program.cs(1,19): error CS0103: The name 'Foo' does not exist"
        reason, _ = runner.classify(output, {"stage": "compile"})
        assert reason == "COMPILE-ERROR"

    def test_runtime_exception_citing_only_program_cs_is_a_runtime_error(self):
        runner = DotNetRunner(family="no-such-family")
        output = (
            "Unhandled exception. System.DivideByZeroException: Attempted to divide by zero.\n"
            r"   at Program.<Main>$(String[] args) in C:\tmp\x\Program.cs:line 2"
        )
        reason, _ = runner.classify(output, {"stage": "execute"})
        assert reason == "RUNTIME-ERROR"

    def test_no_file_citation_at_all_falls_back_to_stage(self):
        runner = DotNetRunner(family="no-such-family")
        reason, _ = runner.classify("some opaque tooling failure", {"stage": "execute"})
        assert reason == "RUNTIME-ERROR"


class TestAcquireReal:
    def test_scaffolds_a_real_project_with_no_reference_for_an_unknown_family(self, tmp_path):
        _runner, acquired = _acquired(tmp_path)
        assert acquired["program_cs"].parent == tmp_path
        assert acquired["reference_path"] is None

    def test_reports_ok_false_when_dotnet_is_missing(self, tmp_path):
        runner = DotNetRunner(family="no-such-family")
        # A path with no `dotnet` on it -- an empty PATH is the simplest real way to
        # prove the missing-toolchain branch without mutating global process state.
        import os
        real_path = os.environ.get("PATH", "")
        try:
            os.environ["PATH"] = ""
            result = runner.acquire(tmp_path, Policy(max_tier=3, allow_acquire=True), ProductContext())
        finally:
            os.environ["PATH"] = real_path
        assert result["ok"] is False
        assert "dotnet" in result["detail"]


class TestCompileRealDotnetBuild:
    def test_clean_bcl_code_compiles(self, tmp_path):
        runner, acquired = _acquired(tmp_path)
        result = runner.compile(acquired, 'Console.WriteLine("hello");', 0)
        assert result is None

    def test_undefined_identifier_is_a_real_compile_error(self, tmp_path):
        runner, acquired = _acquired(tmp_path)
        result = runner.compile(acquired, 'Console.WriteLine(NotAThing());', 0)
        assert result is not None
        assert result["reason"] == "COMPILE-ERROR"
        assert "NotAThing" in result["detail"]


class TestExecuteRealDotnetRun:
    def test_clean_bcl_code_runs_and_passes(self, tmp_path):
        runner, acquired = _acquired(tmp_path)
        result = runner.execute(acquired, 'Console.WriteLine("hello from dotnet run");', 0)
        assert result == {"status": "PASS"}

    def test_runtime_exception_is_a_real_runtime_error(self, tmp_path):
        runner, acquired = _acquired(tmp_path)
        code = 'int x = 0;\nint y = 1 / x;\nConsole.WriteLine(y);'
        result = runner.execute(acquired, code, 0)
        assert result["status"] == "BLOCKED-WITH-REASON"
        assert result["reason"] == "RUNTIME-ERROR"
        assert "divide" in result["detail"].lower() or "DivideByZero" in result["detail"]


class TestEndToEndViaBaseRunner:
    """The real, whole-ladder proof: BaseRunner(DotNetRunner(...)).run(...) against
    real blocks -- proof_tier reaches 3 for clean code via real dotnet build + real
    dotnet run."""

    def test_single_clean_block_reaches_tier_3(self, tmp_path):
        runner = DotNetRunner(family="no-such-family")
        base = BaseRunner(runner)
        blocks = [("sha-0", (1, 1), 'Console.WriteLine("integration test");')]
        results = base.run(blocks, Policy(max_tier=3, allow_acquire=True), ProductContext())
        assert len(results) == 1
        assert results[0].status == "PASS"
        assert results[0].proof_tier == 3

    def test_a_compile_failure_still_names_the_real_msbuild_error(self, tmp_path):
        runner = DotNetRunner(family="no-such-family")
        base = BaseRunner(runner)
        blocks = [("sha-0", (1, 1), 'Console.WriteLine(ThisDoesNotExist());')]
        results = base.run(blocks, Policy(max_tier=3, allow_acquire=True), ProductContext())
        assert results[0].status == "BLOCKED-WITH-REASON"
        assert results[0].reason == "COMPILE-ERROR"
