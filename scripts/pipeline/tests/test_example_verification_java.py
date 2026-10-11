"""Tests for lib/example_verification/runners/java.py's JavaRunner (C12):
the third concrete `runners/base.py` LanguageRunner implementation.

Real acquire (toolchain discovery) -> compile (`javac`) -> execute (`java`)
is the check (never mocked) -- uses only the JDK's own standard library
(`System.out.println`), fully offline, so these tests need no network and
acquire no real product JAR (the product-jar path is covered by
test_example_verification_product_jar.py). Requires a discoverable JDK:
MT074 B6 widened discovery from PATH-only to PATH -> JAVA_HOME -> configured
roots (`ASPOSE_TOOLCHAIN_ROOTS` + per-OS defaults), so a JDK that is merely
installed (not on PATH) now counts. If NO JDK is discoverable these tests are
SKIPPED with a loud reason -- they never pass silently.
"""
from __future__ import annotations

import pytest

from lib.example_verification import toolchain as tc_mod
from lib.example_verification.policy import Policy, ProductContext
from lib.example_verification.runners.base import BaseRunner
from lib.example_verification.runners.java import EMPTY_TOOLCHAIN, JavaRunner, _exec_java

_DISCOVERED = tc_mod.discover_java_toolchain()

pytestmark = pytest.mark.skipif(
    _DISCOVERED.jdk is None,
    reason=("NO JDK (>= 11) DISCOVERABLE via PATH / JAVA_HOME / roots "
            f"{list(_DISCOVERED.searched_roots)} -- every real-javac/java test in this "
            "module is SKIPPED, not passed; install a JDK or set ASPOSE_TOOLCHAIN_ROOTS"),
)


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

    def test_acquire_records_discovery_source_path_and_version(self, tmp_path):
        _runner, acquired = _acquired(tmp_path)
        meta = acquired["result_meta"]
        assert meta["toolchain_name"] == "java"
        assert meta["toolchain_version"] == acquired["toolchain_version"]
        assert meta["toolchain_path"] == acquired["javac_exe"]
        tool = meta["artifact"]["toolchain"]
        assert tool["jdk_source"] != "none"
        assert tool["jdk_version"] == acquired["toolchain_version"]

    def test_no_discoverable_jdk_is_an_explicit_blocked_toolchain_outcome(self, tmp_path):
        """Replaces the old PATH="" probe: discovery now (correctly) finds a
        JDK in JAVA_HOME / roots even with an empty PATH, so 'nothing
        discoverable' is expressed with an injected empty toolchain."""
        runner = JavaRunner(family="no-such-family", toolchain=EMPTY_TOOLCHAIN)
        result = runner.acquire(tmp_path, Policy(max_tier=3, allow_acquire=True), ProductContext())
        assert result["ok"] is False
        assert result["reason"] == "TOOLCHAIN-UNAVAILABLE"
        assert result["detail"].startswith("BLOCKED_TOOLCHAIN:")

    def test_discovery_with_nothing_on_path_or_roots_finds_no_jdk(self):
        empty = tc_mod.discover_java_toolchain(env={}, roots=[], which=lambda _n: None)
        assert empty.jdk is None and empty.maven is None


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

    def test_a_block_comment_led_import_compiles(self, tmp_path):
        """Independent-reviewer finding (round 2), fixed: the first version of
        _wrap_fragment's hoisting loop only recognized `//` line comments as skippable
        preamble -- a leading `/* ... */` block comment stopped hoisting early, landing
        the import back inside main() and reproducing the exact "illegal start of
        expression" bug the first fix claimed to have closed."""
        runner, acquired = _acquired(tmp_path)
        code = (
            "/* Uses the product's List API */\n"
            "import java.util.List;\n\n"
            "List<String> items = new java.util.ArrayList<>();\n"
            "System.out.println(items);"
        )
        result = runner.compile(acquired, code, 0)
        assert result is None, result

    def test_a_string_literal_containing_comment_syntax_does_not_corrupt_class_name_detection(self, tmp_path):
        """Independent-reviewer finding (round 2), fixed: _strip_comments's block-comment
        regex was not string-literal-aware -- a string literal containing `/*` with no
        REAL closing `*/` of its own (e.g. `"/* unterminated"`) let the non-greedy regex
        span from inside that literal all the way to an unrelated, LATER real `*/`
        elsewhere in the block (a real trailing comment is required to reproduce this --
        with no real `*/` anywhere after the literal, the naive regex has nothing to
        close on and never matches at all, which is why this exact shape is needed, not
        a simpler one). That deleted real code (including the real `public class
        Widget` declaration) along with it, so _class_name_for picked the WRONG
        (non-public) class -- reproducing the exact "class X is public, should be
        declared in a file named X.java" bug the first fix claimed to have closed."""
        runner, acquired = _acquired(tmp_path)
        code = (
            'class Helper {\n'
            '    static String note() { return "/* unterminated"; }\n'
            '}\n\n'
            'public class Widget {\n'
            '    public static void main(String[] args) {\n'
            '        /* a real trailing comment */\n'
            '        System.out.println(Helper.note());\n'
            '    }\n'
            '}\n'
        )
        result = runner.compile(acquired, code, 0)
        assert result is None, result
        assert (acquired["work_dir"] / "Widget.class").is_file()

    def test_a_same_line_comment_followed_by_real_code_keeps_that_code(self, tmp_path):
        """Independent-reviewer finding (round 3), fixed: the round-2 hoisting fix
        unconditionally hoisted an ENTIRE line starting with `/*`, even when real code
        follows the comment's own closing `*/` later on that same line -- silently
        dropping that trailing code from the generated program instead of keeping it as
        body content (`/* note */ code;` is ordinary, legal Java inside a method)."""
        runner, acquired = _acquired(tmp_path)
        code = '/* explanation */ System.out.println("hi from after the comment");'
        result = runner.execute(acquired, code, 0)
        assert result == {"status": "PASS"}

    def test_a_class_mention_inside_a_text_block_does_not_corrupt_class_name_detection(self, tmp_path):
        """Independent-reviewer finding (round 3), fixed: _strip_comments preserved
        string/char literal CONTENT verbatim (round 2's fix), which correctly stopped
        comment-like characters inside a literal from corrupting the scan, but left a
        `class X` mention EMBEDDED inside a literal's own content (e.g. a Java 15+ text
        block storing example source as documentation text) fully visible to the later
        class-detection scan -- reproducing the exact "wrong class picked" defect via a
        third, different trigger shape."""
        runner, acquired = _acquired(tmp_path)
        code = (
            'class Helper {\n'
            '    static String exampleDoc = """\n'
            'public class Evil\n'
            '""";\n'
            '}\n'
            'public class Widget {\n'
            '    public static void main(String[] a) {\n'
            '        System.out.println(Helper.exampleDoc);\n'
            '    }\n'
            '}\n'
        )
        result = runner.compile(acquired, code, 0)
        assert result is None, result
        assert (acquired["work_dir"] / "Widget.class").is_file()


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
