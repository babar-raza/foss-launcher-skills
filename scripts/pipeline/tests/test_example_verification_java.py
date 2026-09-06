"""Tests for lib/example_verification/runners/java.py's JavaRunner (C12):
the third concrete `runners/base.py` LanguageRunner implementation.

Real acquire (`mvn -version` toolchain discovery) -> compile (`javac`) ->
execute (`java`) is the check (never mocked) -- uses only the JDK's own
standard library (`System.out.println`), fully offline, so these tests need
no network and acquire no real product JAR (disclosed scope limit -- see
runners/java.py's own module docstring). Requires a real `mvn`+JDK on PATH
(confirmed present via the plan's own "Verified toolchain inventory":
Temurin JDK 21.0.11, Apache Maven 3.9.16 -- resolving JDK 17.0.19 for its
own builds, the exact real-world wrinkle this runner's toolchain discovery
exists to handle correctly).
"""
from __future__ import annotations

import shutil

import pytest

from lib.example_verification.policy import Policy, ProductContext
from lib.example_verification.runners.base import BaseRunner
from lib.example_verification.runners.java import JavaRunner, _exec_java

pytestmark = pytest.mark.skipif(shutil.which("mvn") is None, reason="mvn not on PATH")


def _acquired(tmp_path):
    runner = JavaRunner(family="no-such-family")
    acquired = runner.acquire(tmp_path, Policy(max_tier=3, allow_acquire=True), ProductContext())
    assert acquired["ok"], acquired.get("detail")
    return runner, acquired


class TestStartsChain:
    def test_import_line_starts_a_new_chain(self):
        runner = JavaRunner(family="no-such-family")
        assert runner.starts_chain('import java.util.List;\n\nSystem.out.println("hi");')

    def test_class_declaration_starts_a_new_chain(self):
        runner = JavaRunner(family="no-such-family")
        assert runner.starts_chain('public class Demo {\n    static void run() {}\n}')

    def test_plain_statement_continues_the_previous_chain(self):
        runner = JavaRunner(family="no-such-family")
        assert not runner.starts_chain('System.out.println("continuing");')

    def test_leading_comment_is_skipped_before_deciding(self):
        runner = JavaRunner(family="no-such-family")
        assert runner.starts_chain('// a comment\nimport java.util.List;')


class TestClassify:
    def test_compile_error_citing_a_non_own_file_is_upstream_broken(self):
        runner = JavaRunner(family="no-such-family")
        output = "Lib.java:3: error: cannot find symbol\n  symbol:   method undefinedHelper()"
        reason, detail = runner.classify(output, {"stage": "compile", "own_file": "Main.java"})
        assert reason == "UPSTREAM-BROKEN"
        assert detail == output

    def test_compile_error_in_own_file_is_a_compile_error(self):
        runner = JavaRunner(family="no-such-family")
        output = "Main.java:3: error: cannot find symbol"
        reason, _ = runner.classify(output, {"stage": "compile", "own_file": "Main.java"})
        assert reason == "COMPILE-ERROR"

    def test_stack_frame_citing_only_own_file_is_a_runtime_error(self):
        runner = JavaRunner(family="no-such-family")
        output = (
            "Exception in thread \"main\" java.lang.ArithmeticException: / by zero\n"
            "\tat Main.main(Main.java:4)"
        )
        reason, _ = runner.classify(output, {"stage": "execute", "own_file": "Main.java"})
        assert reason == "RUNTIME-ERROR"

    def test_stack_frame_citing_a_different_file_is_upstream_broken(self):
        runner = JavaRunner(family="no-such-family")
        output = (
            "Exception in thread \"main\" java.lang.ArithmeticException: / by zero\n"
            "\tat Lib.doThing(Lib.java:4)\n"
            "\tat Main.main(Main.java:3)"
        )
        reason, _ = runner.classify(output, {"stage": "execute", "own_file": "Main.java"})
        assert reason == "UPSTREAM-BROKEN"

    def test_no_file_citation_at_all_falls_back_to_stage(self):
        runner = JavaRunner(family="no-such-family")
        reason, _ = runner.classify("some opaque tooling failure", {"stage": "execute", "own_file": "Main.java"})
        assert reason == "RUNTIME-ERROR"


class TestClassifyRealUpstreamError:
    """Real, non-mocked reproduction of the exact scenario TestClassify's unit tests
    only simulate: a genuine bug in a separately-compiled class already sitting on
    the implicit classpath (javac/java both default to including the invoking
    directory), surfaced through real javac + java calls via JavaRunner itself."""

    def test_real_referenced_class_runtime_error_is_classified_upstream_broken(self, tmp_path):
        runner, acquired = _acquired(tmp_path)
        # Pre-compile a separate "Lib" class with a real bug directly into the same
        # work_dir JavaRunner's compile()/execute() will use -- proving the implicit
        # cwd-default classpath picks it up, the same way a real product's
        # already-built classes would sit alongside a block's generated wrapper.
        lib_src = tmp_path / "Lib.java"
        lib_src.write_text(
            "public class Lib {\n"
            "    public static void doThing() {\n"
            "        int x = 0;\n"
            "        int y = 1 / x;\n"
            "    }\n"
            "}\n",
            encoding="utf-8",
        )
        compile_outcome, compile_detail = _exec_java(
            [acquired["javac_exe"], "-d", str(acquired["work_dir"]), str(lib_src)],
            acquired["work_dir"], 30,
        )
        assert compile_outcome == "OK", compile_detail
        lib_src.unlink()  # only the .class matters from here, matching a real product jar

        result = runner.execute(acquired, "Lib.doThing();", 0)

        assert result["status"] == "BLOCKED-WITH-REASON"
        assert result["reason"] == "UPSTREAM-BROKEN"
        assert "Lib.java" in result["detail"]


class TestAcquireReal:
    def test_discovers_a_real_toolchain(self, tmp_path):
        _runner, acquired = _acquired(tmp_path)
        assert acquired["java_exe"]
        assert acquired["javac_exe"]
        assert acquired["toolchain_version"]

    def test_reports_ok_false_when_mvn_is_missing(self, tmp_path):
        runner = JavaRunner(family="no-such-family")
        import os
        real_path = os.environ.get("PATH", "")
        try:
            os.environ["PATH"] = ""
            result = runner.acquire(tmp_path, Policy(max_tier=3, allow_acquire=True), ProductContext())
        finally:
            os.environ["PATH"] = real_path
        assert result["ok"] is False
        assert "mvn" in result["detail"]


class TestCompileRealJavac:
    def test_clean_stdlib_fragment_compiles(self, tmp_path):
        runner, acquired = _acquired(tmp_path)
        result = runner.compile(acquired, 'System.out.println("hello");', 0)
        assert result is None

    def test_undefined_identifier_is_a_real_compile_error(self, tmp_path):
        runner, acquired = _acquired(tmp_path)
        result = runner.compile(acquired, 'System.out.println(notAThing());', 0)
        assert result is not None
        assert result["reason"] == "COMPILE-ERROR"
        assert "notAThing" in result["detail"]

    def test_a_complete_class_block_keeps_its_own_class_name(self, tmp_path):
        runner, acquired = _acquired(tmp_path)
        code = (
            "public class Widget {\n"
            "    public static void main(String[] args) {\n"
            "        System.out.println(\"hi\");\n"
            "    }\n"
            "}\n"
        )
        result = runner.compile(acquired, code, 0)
        assert result is None
        assert (acquired["work_dir"] / "Widget.class").is_file()

    def test_an_import_led_fragment_compiles(self, tmp_path):
        """Independent-reviewer finding, fixed: the original _wrap_fragment indented
        the ENTIRE fragment -- including a leading `import` -- straight into the
        generated main() method body, which is illegal Java (imports must precede the
        class declaration). This is the exact shape starts_chain() itself is designed
        to recognize as a valid chain start -- and the realistic shape of virtually
        every real Java Quick Start snippet (an import of the product's own class)."""
        runner, acquired = _acquired(tmp_path)
        code = (
            "import java.util.List;\n\n"
            "List<String> items = new java.util.ArrayList<>();\n"
            "System.out.println(items);"
        )
        result = runner.compile(acquired, code, 0)
        assert result is None, result

    def test_a_helper_class_before_the_public_class_keeps_the_public_name(self, tmp_path):
        """Independent-reviewer finding, fixed: _class_name_for used to return the
        FIRST `class` match regardless of modifier, silently picking a helper class's
        name (and thus the wrong file/invoked-class name) instead of the real, public
        one Java actually requires the file to be named after."""
        runner, acquired = _acquired(tmp_path)
        code = (
            "class Helper {\n"
            "    static void help() {}\n"
            "}\n\n"
            "public class Widget {\n"
            "    public static void main(String[] args) {\n"
            "        System.out.println(\"hi\");\n"
            "    }\n"
            "}\n"
        )
        result = runner.compile(acquired, code, 0)
        assert result is None, result
        assert (acquired["work_dir"] / "Widget.class").is_file()

    def test_a_class_mention_inside_a_comment_does_not_suppress_wrapping(self, tmp_path):
        """Independent-reviewer finding, fixed: _CLASS_DECL_RE used to match a `class X`
        mention inside a comment (prose, not a real declaration), which incorrectly
        skipped wrapping a bare fragment -- a real compile failure ("illegal start of
        expression" on the comment-adjacent code) for what should be an ordinary,
        wrappable statement fragment."""
        runner, acquired = _acquired(tmp_path)
        code = '// class Widget usage pattern.\nSystem.out.println("hi");'
        result = runner.compile(acquired, code, 0)
        assert result is None, result


class TestExecuteRealJava:
    def test_clean_stdlib_fragment_runs_and_passes(self, tmp_path):
        runner, acquired = _acquired(tmp_path)
        result = runner.execute(acquired, 'System.out.println("hello from java run");', 0)
        assert result == {"status": "PASS"}

    def test_runtime_exception_is_a_real_runtime_error(self, tmp_path):
        runner, acquired = _acquired(tmp_path)
        code = 'int x = 0;\n\tint y = 1 / x;\n\tSystem.out.println(y);'
        result = runner.execute(acquired, code, 0)
        assert result["status"] == "BLOCKED-WITH-REASON"
        assert result["reason"] == "RUNTIME-ERROR"
        assert "ArithmeticException" in result["detail"] or "/ by zero" in result["detail"]


class TestEndToEndViaBaseRunner:
    """The real, whole-ladder proof: BaseRunner(JavaRunner(...)).run(...) against
    real blocks -- proof_tier reaches 3 for clean code via real javac + real java."""

    def test_single_clean_block_reaches_tier_3(self, tmp_path):
        runner = JavaRunner(family="no-such-family")
        base = BaseRunner(runner)
        blocks = [("sha-0", (1, 1), 'System.out.println("integration test");')]
        results = base.run(blocks, Policy(max_tier=3, allow_acquire=True), ProductContext())
        assert len(results) == 1
        assert results[0].status == "PASS"
        assert results[0].proof_tier == 3

    def test_a_compile_failure_still_names_the_real_javac_error(self, tmp_path):
        runner = JavaRunner(family="no-such-family")
        base = BaseRunner(runner)
        blocks = [("sha-0", (1, 1), 'System.out.println(thisDoesNotExist());')]
        results = base.run(blocks, Policy(max_tier=3, allow_acquire=True), ProductContext())
        assert results[0].status == "BLOCKED-WITH-REASON"
        assert results[0].reason == "COMPILE-ERROR"
