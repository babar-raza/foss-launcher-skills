"""Tests for content_eval.evaluators.code_syntax_check.

Covers:
  - Python ast.parse (valid, SyntaxError)
  - Shared tree-sitter loader (lib/example_verification/syntax.py, TC-11
    collapse): Java / C# / TypeScript / JavaScript / C++ (valid, error)
  - Heuristic delimiter fallback (balanced, unbalanced, comment-ignoring)
  - Skip rules (short blocks, noqa, _SKIP_LANGS)
  - Graceful fallback when a language has no shared grammar at all
    (kotlin/swift/scala -- a real, permanent GRAMMAR-UNAVAILABLE case,
    not a monkey-patched simulation of one)
"""

from __future__ import annotations

import sys
import textwrap
import unittest
from pathlib import Path

# Ensure pipeline root is importable
_PIPELINE_ROOT = Path(__file__).resolve().parents[1]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))
_LIB_DIR = str(_PIPELINE_ROOT / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from content_eval.evaluators.code_syntax_check import (
    CodeSyntaxCheckEvaluator,
    _check_balanced_delimiters_for_test,
)
from content_eval.models import CodeBlock, Page
from example_verification.syntax import parser_for as _shared_parser_for


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _page(blocks: list[tuple[str, str, int]]) -> Page:
    """Build a minimal Page with the given code blocks (lang, content, start_line)."""
    code_blocks = [
        CodeBlock(lang=lang, content=content, start_line=start,
                  end_line=start + len(content.splitlines()))
        for lang, content, start in blocks
    ]
    p = Page.__new__(Page)
    p.filepath = Path("fake/test.md")
    p.code_blocks = code_blocks
    p.body = ""
    p.frontmatter = {}
    p.sections = []
    return p


def _eval(blocks: list[tuple[str, str, int]]) -> list:
    ev = CodeSyntaxCheckEvaluator()
    return ev.evaluate(_page(blocks), knowledge=None)


# ---------------------------------------------------------------------------
# Python: ast.parse
# ---------------------------------------------------------------------------

class TestPythonSyntax(unittest.TestCase):

    def test_valid_python_no_findings(self):
        code = textwrap.dedent("""\
            import aspose.cells as ac
            wb = ac.Workbook()
            ws = wb.worksheets[0]
            ws.cells["A1"].value = "Hello"
            wb.save("output.xlsx")
        """)
        findings = _eval([("python", code, 10)])
        self.assertEqual(findings, [])

    def test_syntax_error_produces_fail(self):
        code = textwrap.dedent("""\
            wb = Workbook(
            ws = wb.worksheets[0]
            ws.cells["A1"].value = "Hello"
        """)
        findings = _eval([("python", code, 5)])
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].level, "FAIL")
        self.assertEqual(findings[0].category, "SX")
        self.assertIn("syntax", findings[0].message.lower())

    def test_py_tag_also_checked(self):
        code = "def foo(:\n    pass\n\nfoo()\n"
        findings = _eval([("py", code, 1)])
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].level, "FAIL")

    def test_valid_python_class(self):
        code = textwrap.dedent("""\
            class Loader:
                def __init__(self, path):
                    self.path = path

                def load(self):
                    return open(self.path)
        """)
        findings = _eval([("python", code, 1)])
        self.assertEqual(findings, [])

    def test_line_number_offset(self):
        """Error line_no should be relative to block start_line."""
        code = "x = 1\ny = 2\ndef bad(:\n    pass\n"
        findings = _eval([("python", code, 20)])
        self.assertEqual(len(findings), 1)
        # SyntaxError on line 3 of the block → 20 + 3 - 1 = 22
        self.assertEqual(findings[0].line_no, 22)


# ---------------------------------------------------------------------------
# Short block / noqa / skip-lang rules
# ---------------------------------------------------------------------------

class TestSkipRules(unittest.TestCase):

    def test_short_block_skipped(self):
        # < 3 lines — should be skipped
        findings = _eval([("python", "wb = Workbook()\nwb.save()\n", 1)])
        self.assertEqual(findings, [])

    def test_noqa_syntax_marker_skips_block(self):
        code = "# noqa: syntax\ndef foo(\n    pass\n\nfoo()\n"
        findings = _eval([("python", code, 1)])
        self.assertEqual(findings, [])

    def test_noqa_case_insensitive(self):
        code = "# NOQA: SYNTAX\ndef foo(\n    pass\n"
        findings = _eval([("python", code, 1)])
        self.assertEqual(findings, [])

    def test_skip_langs_not_checked(self):
        for lang in ("bash", "json", "xml", "yaml", "shell", "html", "sql"):
            code = "this is not valid code at all"
            # Need at least 3 lines to pass the short-block filter
            code3 = code + "\nline2\nline3\n"
            findings = _eval([(lang, code3, 1)])
            self.assertEqual(findings, [], f"Expected no findings for lang={lang}")

    def test_empty_lang_tag_skipped(self):
        code = "def bad(\n    pass\n\nfoo()\n"
        findings = _eval([("", code, 1)])
        self.assertEqual(findings, [])


# ---------------------------------------------------------------------------
# Tree-sitter: Java
# ---------------------------------------------------------------------------

class TestJavaSyntax(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.ts_available = _shared_parser_for("java") is not None

    def test_valid_java_no_findings(self):
        code = textwrap.dedent("""\
            Workbook wb = new Workbook();
            Worksheet ws = wb.getWorksheets().get(0);
            ws.getCells().get("A1").putValue("Hello");
            wb.save("output.xlsx");
        """)
        findings = _eval([("java", code, 1)])
        if self.ts_available:
            self.assertEqual(findings, [])

    def test_java_syntax_error_produces_fail(self):
        if not self.ts_available:
            self.skipTest("tree-sitter-java not installed")
        code = textwrap.dedent("""\
            Workbook wb = new Workbook(
            Worksheet ws = wb.getWorksheets().get(0);
            ws.getCells().get("A1").putValue("Hello");
        """)
        findings = _eval([("java", code, 1)])
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].level, "FAIL")
        self.assertEqual(findings[0].category, "SX")

    def test_java_complete_class_valid(self):
        code = textwrap.dedent("""\
            public class Example {
                public static void main(String[] args) {
                    System.out.println("Hello");
                }
            }
        """)
        findings = _eval([("java", code, 1)])
        if self.ts_available:
            self.assertEqual(findings, [])

    def test_java_method_body_valid(self):
        code = textwrap.dedent("""\
            public void save(String path) {
                workbook.save(path);
                System.out.println("Saved to " + path);
            }
        """)
        findings = _eval([("java", code, 1)])
        if self.ts_available:
            self.assertEqual(findings, [])


# ---------------------------------------------------------------------------
# Tree-sitter: C#
# ---------------------------------------------------------------------------

class TestCSharpSyntax(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.ts_available = _shared_parser_for("csharp") is not None

    def test_valid_csharp_no_findings(self):
        code = textwrap.dedent("""\
            using Aspose.Cells;
            var wb = new Workbook();
            var ws = wb.Worksheets[0];
            ws.Cells["A1"].Value = "Hello";
            wb.Save("output.xlsx");
        """)
        findings = _eval([("csharp", code, 1)])
        if self.ts_available:
            self.assertEqual(findings, [])

    def test_cs_tag_recognized(self):
        code = textwrap.dedent("""\
            var wb = new Workbook();
            wb.Save("output.xlsx");
            Console.WriteLine("Done");
        """)
        findings = _eval([("cs", code, 1)])
        if self.ts_available:
            self.assertEqual(findings, [])

    def test_csharp_syntax_error(self):
        if not self.ts_available:
            self.skipTest("tree-sitter-c-sharp not installed")
        # Use an invalid token (@@) which tree-sitter-c-sharp marks as ERROR
        code = textwrap.dedent("""\
            var wb = new Workbook();
            wb.@@invalid;
            Console.WriteLine("Done");
        """)
        findings = _eval([("csharp", code, 1)])
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].level, "FAIL")

    def test_csharp_complete_class_valid(self):
        code = textwrap.dedent("""\
            using System;
            class Example {
                static void Main() {
                    Console.WriteLine("Hello");
                }
            }
        """)
        findings = _eval([("csharp", code, 1)])
        if self.ts_available:
            self.assertEqual(findings, [])


# ---------------------------------------------------------------------------
# Tree-sitter: TypeScript
# ---------------------------------------------------------------------------

class TestTypeScriptSyntax(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.ts_available = _shared_parser_for("typescript") is not None

    def test_valid_typescript_no_findings(self):
        code = textwrap.dedent("""\
            const wb = new Workbook();
            const ws = wb.worksheets[0];
            ws.cells.get("A1").value = "Hello";
            wb.save("output.xlsx");
        """)
        findings = _eval([("typescript", code, 1)])
        if self.ts_available:
            self.assertEqual(findings, [])

    def test_ts_tag_recognized(self):
        code = textwrap.dedent("""\
            const x: string = "hello";
            const y: number = 42;
            console.log(x, y);
        """)
        findings = _eval([("ts", code, 1)])
        if self.ts_available:
            self.assertEqual(findings, [])

    def test_typescript_syntax_error(self):
        if not self.ts_available:
            self.skipTest("tree-sitter-typescript not installed")
        code = textwrap.dedent("""\
            const x: = "broken type annotation";
            const y = 42;
            console.log(x, y);
        """)
        findings = _eval([("typescript", code, 1)])
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].level, "FAIL")

    def test_typescript_function_valid(self):
        code = textwrap.dedent("""\
            function greet(name: string): string {
                return `Hello, ${name}!`;
            }
            console.log(greet("World"));
        """)
        findings = _eval([("typescript", code, 1)])
        if self.ts_available:
            self.assertEqual(findings, [])


# ---------------------------------------------------------------------------
# Tree-sitter: C++
# ---------------------------------------------------------------------------

class TestCppSyntax(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.ts_available = _shared_parser_for("cpp") is not None

    def test_valid_cpp_no_findings(self):
        code = textwrap.dedent("""\
            #include <iostream>
            int main() {
                std::cout << "Hello" << std::endl;
                return 0;
            }
        """)
        findings = _eval([("cpp", code, 1)])
        if self.ts_available:
            self.assertEqual(findings, [])

    def test_cpp_tag_recognized(self):
        code = textwrap.dedent("""\
            auto doc = std::make_shared<Document>();
            doc->Save("output.docx");
            std::cout << "Saved" << std::endl;
        """)
        findings = _eval([("c++", code, 1)])
        if self.ts_available:
            self.assertEqual(findings, [])

    def test_cpp_syntax_error(self):
        if not self.ts_available:
            self.skipTest("tree-sitter-cpp not installed")
        code = textwrap.dedent("""\
            auto doc = new Document(opts missing_arg;
            doc->Save("out.docx");
            delete doc;
        """)
        findings = _eval([("cpp", code, 1)])
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].level, "FAIL")


# ---------------------------------------------------------------------------
# Heuristic delimiter checker (fallback + other brace langs)
# ---------------------------------------------------------------------------

class TestHeuristicDelimiters(unittest.TestCase):
    """Direct tests of _check_balanced_delimiters_for_test helper."""

    def _check(self, code: str) -> list:
        """Invoke the heuristic checker directly."""
        return _check_balanced_delimiters_for_test(code, start_line=1,
                                                    filepath="test.md")

    def test_balanced_code_no_findings(self):
        code = textwrap.dedent("""\
            function foo() {
                const x = [1, 2, 3];
                return (x[0] + x[1]);
            }
        """)
        self.assertEqual(self._check(code), [])

    def test_unclosed_brace(self):
        code = textwrap.dedent("""\
            function foo() {
                const x = 1;
                return x;
            """)  # missing closing }
        findings = self._check(code)
        self.assertTrue(any("unclosed '{'" in f.message for f in findings))

    def test_extra_closing_paren(self):
        code = textwrap.dedent("""\
            function foo() {
                return (1 + 2));
            }
        """)
        findings = self._check(code)
        self.assertTrue(any("extra closing ')'" in f.message for f in findings))

    def test_comment_braces_ignored(self):
        """Braces inside // comments must not affect counts."""
        code = textwrap.dedent("""\
            function foo() {
                // This comment has { an unclosed brace
                return 1;
            }
        """)
        self.assertEqual(self._check(code), [])

    def test_block_comment_braces_ignored(self):
        """Braces inside /* */ comments must not affect counts."""
        code = textwrap.dedent("""\
            function foo() {
                /* { unclosed in comment */
                return 1;
            }
        """)
        self.assertEqual(self._check(code), [])

    def test_string_braces_ignored(self):
        """Braces inside string literals must not affect counts."""
        code = textwrap.dedent("""\
            function foo() {
                const s = "value { with { braces";
                return s;
            }
        """)
        self.assertEqual(self._check(code), [])

    def test_escaped_quote_in_string(self):
        """Escaped quote inside a string must not terminate the string early."""
        code = textwrap.dedent("""\
            function foo() {
                const s = "say \\"hello\\"";
                return s;
            }
        """)
        self.assertEqual(self._check(code), [])

    def test_multiple_imbalances_reported(self):
        """All delimiter types with imbalance are reported."""
        code = textwrap.dedent("""\
            function foo(x {
                const y = [1;
                return (x;
            """)
        findings = self._check(code)
        # Should get at least 3 warnings: (, [, {
        self.assertGreaterEqual(len(findings), 3)
        self.assertTrue(all(f.level == "WARN" for f in findings))


# ---------------------------------------------------------------------------
# Graceful fallback when tree-sitter unavailable
# ---------------------------------------------------------------------------

class TestTreeSitterFallback(unittest.TestCase):
    """Uses `kotlin` -- a real, permanent GRAMMAR-UNAVAILABLE case (no
    shared grammar exists for it at all, unlike java/csharp/typescript/cpp/
    rust/go, which all have one now that TC-13 installed the missing
    toolchains) -- instead of monkey-patching java's own now-real parser
    cache away (banned T1/T2 pattern; also no longer possible post-TC-11
    collapse, since the shared loader owns its own private cache)."""

    def test_falls_back_to_heuristic_when_grammar_unavailable(self):
        """If no shared grammar exists for a language, the heuristic
        balanced-delimiter checker is used instead."""
        code = textwrap.dedent("""\
            fun foo(): Int {
                return 1 + 2
            }
        """)
        findings = _eval([("kotlin", code, 1)])
        # Should get no error (balanced code) from the heuristic fallback
        self.assertEqual(findings, [])

    def test_fallback_catches_unbalanced_without_grammar(self):
        """Heuristic fallback still catches obvious imbalances."""
        code = textwrap.dedent("""\
            fun foo(): Int {
                return (1 + 2
            }
        """)
        findings = _eval([("kotlin", code, 1)])
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].level, "WARN")


# ---------------------------------------------------------------------------
# Multiple blocks on the same page
# ---------------------------------------------------------------------------

class TestMultipleBlocks(unittest.TestCase):

    def test_findings_from_all_blocks(self):
        good_py = textwrap.dedent("""\
            wb = Workbook()
            wb.save("out.xlsx")
            print("done")
        """)
        bad_py = textwrap.dedent("""\
            wb = Workbook(
            wb.save("out.xlsx")
            print("done")
        """)
        findings = _eval([
            ("python", good_py, 1),
            ("python", bad_py, 20),
        ])
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].line_no, 20)  # error in second block

    def test_evaluator_name_on_findings(self):
        bad_py = "def bad(:\n    pass\n\nfoo()\n"
        findings = _eval([("python", bad_py, 1)])
        self.assertTrue(all(f.evaluator == "code_syntax_check" for f in findings))


if __name__ == "__main__":
    unittest.main()
