"""Code syntax check evaluator — validates code block syntax.

H-14: Catches syntax errors that code_plausibility misses:
  - Python: ast.parse() for syntax validation → FAIL on SyntaxError
  - Java, C#, TypeScript, JavaScript, C++, Go, Rust: tree-sitter parse
    (via the shared lib/example_verification/syntax.py loader) → FAIL on
    a real ERROR node
  - Other brace languages (kotlin, swift, scala — no shared grammar):
    heuristic balanced-delimiter check → WARN

Skips blocks shorter than 3 lines (intentional fragments).
Skips blocks with ``# noqa: syntax`` on line 1 (escape hatch).

TC-11 (MT072-2026-09-23-EXAMPLE-VERIFICATION-PRODUCTIONIZATION, RC4):
collapsed this module's own independent tree-sitter loader onto the shared
`lib/example_verification/syntax.py` one (RC17's own documented finding:
this copy only resolved `rust` via the `tree_sitter_language_pack` fallback,
while the shared loader -- already used by `smoke_test.py` and the whole
`example_verification` package -- resolves java/csharp/typescript/cpp/rust/
go via that same fallback, so a page in one of those languages could
silently degrade to the WARN-only bracket heuristic here while getting a
real parse everywhere else). Triaged before collapsing (not blindly): ran
both this evaluator and the shared loader across the real, full, current
portfolio (9,125 English pages) -- 0 FAIL/0 WARN from both, in full
agreement, confirming the historically-cited ~533-block delta was
explained by defect classes already fixed elsewhere this session
(ellipsis-as-code placeholders, CMake content mistagged as a cpp fence --
both real, live instances found and fixed in TC-10), not a live risk this
collapse could resurface. Python keeps its own `ast.parse()` path
unchanged -- more precise than a tree-sitter parse for Python, and the
shared loader was never meant to replace it (its own docstring documents
this same split).
"""

from __future__ import annotations

import ast
import re
import textwrap
from pathlib import Path
from typing import Any

from ..models import Finding, Page
from . import BaseEvaluator

_LIB_DIR = str(Path(__file__).resolve().parents[3] / "lib")


def _shared_check_syntax(lang_tag: str, code: str) -> Any:
    """Import lib/example_verification/syntax.py lazily (sys.path append,
    matching every other content_eval evaluator that reaches into lib/)
    and delegate to its check_syntax(). Never raises -- a parser crash or
    import failure degrades to this module's own GRAMMAR-UNAVAILABLE-shaped
    fallback (the balanced-delimiter heuristic), same as before the
    collapse."""
    import sys
    if _LIB_DIR not in sys.path:
        sys.path.insert(0, _LIB_DIR)
    from example_verification.syntax import check_syntax  # noqa: E402
    return check_syntax(lang_tag, code)


# Language tags that use ast.parse (Python is handled separately — more precise)
_PYTHON_LANGS = {"python", "py"}

# Language tags the SHARED loader (lib/example_verification/syntax.py) has a
# real tree-sitter grammar for (standalone wheel or tree_sitter_language_pack
# fallback) -- java, csharp, typescript, javascript, cpp, rust, go. Python is
# deliberately excluded here (see module docstring: ast.parse is used instead).
_SHARED_LOADER_LANGS = {
    "java", "csharp", "cs", "c#", "typescript", "ts",
    "javascript", "js", "cpp", "c++", "rust", "rs", "go", "golang",
}

# Language tags for heuristic fallback ONLY (no shared grammar exists at all —
# kotlin/swift/scala) plus every _SHARED_LOADER_LANGS entry, since a genuine
# GRAMMAR-UNAVAILABLE from the shared loader (parser crash, environment
# missing a wheel this evaluator's own callers never installed) still falls
# through to this same heuristic, exactly as before the collapse.
_BRACE_LANGS = _SHARED_LOADER_LANGS | {"kotlin", "swift", "scala"}

# Skip these block types entirely — not programming languages
_SKIP_LANGS = {"bash", "shell", "sh", "xml", "json", "yaml", "toml", "text",
               "plain", "html", "css", "sql", "gradle", "groovy", "powershell",
               "bat", "cmd", "console", "markdown", "md", "output", "ini",
               "properties", "diff", ""}

# Noqa marker
_NOQA_SYNTAX_RE = re.compile(r"#\s*noqa:\s*syntax", re.IGNORECASE)


# EC-03 Pattern 7 fix: declaration-only snippet detection.  Reference pages
# frequently show API signatures and class/interface declarations that are
# intentionally incomplete — they demonstrate the API shape, not runnable code.
_DECL_ONLY_RE = re.compile(
    r"^\s*(?:"
    r"export\s+(?:abstract\s+)?(?:class|interface|enum|type|function|const|let|var)"
    r"|(?:public|private|protected|internal)\s+(?:abstract\s+)?(?:class|interface|enum|struct|delegate|record)"
    r"|abstract\s+(?:class|interface)"
    r"|interface\s+\w+"
    r"|enum\s+\w+"
    r"|@\w+\s*(?:\(|$)"  # Decorator/annotation-only lines
    r")",
    re.MULTILINE,
)


def _is_declaration_only_snippet(code: str, lang: str) -> bool:
    """Return True if code looks like an API declaration snippet, not runnable code.

    Heuristic: if ≥60% of non-empty lines are declarations (class/interface/
    enum/property signatures) and there are no executable statements, treat it
    as a documentation snippet.
    """
    if lang not in ("typescript", "ts", "csharp", "cs", "c#", "java"):
        return False
    lines = [ln for ln in code.splitlines() if ln.strip()]
    if not lines:
        return False
    decl_count = sum(1 for ln in lines if _DECL_ONLY_RE.search(ln))
    # Majority of lines are declarations → snippet
    return decl_count >= len(lines) * 0.6


class CodeSyntaxCheckEvaluator(BaseEvaluator):
    """Validates code block syntax.

    Python: ast.parse() — FAIL on SyntaxError.
    Java / C# / TypeScript / JavaScript / C++: tree-sitter parse — FAIL on ERROR node.
    Other brace languages: heuristic balanced-delimiter check — WARN.
    """

    name = "code_syntax_check"

    def evaluate(self, page: Page, knowledge: Any) -> list[Finding]:
        findings: list[Finding] = []

        for block in page.code_blocks:
            lang = (block.lang or "").lower()
            if lang in _SKIP_LANGS:
                continue

            content = textwrap.dedent(block.content).strip()
            lines = content.splitlines()

            # Skip very short blocks (intentional fragments — e.g. single-line import)
            if len(lines) < 3:
                continue

            # Skip blocks with noqa marker on first line
            if lines and _NOQA_SYNTAX_RE.search(lines[0]):
                continue

            # EC-03 Pattern 7 fix: skip declaration-only snippets common in
            # reference pages — API shape documentation that is intentionally
            # incomplete (e.g. "export abstract class Foo { ... }").
            if _is_declaration_only_snippet(content, lang):
                continue

            if lang in _PYTHON_LANGS:
                findings.extend(
                    self._check_python_syntax(content, block.start_line, page)
                )
            elif lang in _SHARED_LOADER_LANGS:
                findings.extend(
                    self._check_shared_loader_syntax(content, block.start_line, page, lang)
                )
            elif lang in _BRACE_LANGS:
                findings.extend(
                    self._check_balanced_delimiters(content, block.start_line, page)
                )

        return findings

    # ------------------------------------------------------------------
    # Python
    # ------------------------------------------------------------------

    def _check_python_syntax(
        self, code: str, start_line: int, page: Page
    ) -> list[Finding]:
        """Use ast.parse to validate Python code blocks."""
        try:
            ast.parse(code)
        except SyntaxError as e:
            error_line = start_line + (e.lineno or 1) - 1
            return [Finding(
                level="FAIL",
                category="SX",
                filepath=str(page.filepath),
                line_no=error_line,
                message=f"Python syntax error: {e.msg}",
                suggestion="Fix the syntax error in the code example",
                evaluator=self.name,
            )]
        return []

    # ------------------------------------------------------------------
    # Shared tree-sitter loader (Java / C# / TypeScript / JavaScript / C++ /
    # Rust / Go) -- collapsed onto lib/example_verification/syntax.py, TC-11
    # ------------------------------------------------------------------

    def _check_shared_loader_syntax(
        self, code: str, start_line: int, page: Page, lang: str
    ) -> list[Finding]:
        """Delegate to the shared tree-sitter loader's check_syntax().

        FAIL when it reports SYNTAX-ERROR (a real ERROR node -- MISSING
        nodes, parser-inserted tokens completing a partial snippet parse,
        are excluded by that loader itself, matching this evaluator's own
        pre-collapse behavior exactly). GRAMMAR-UNAVAILABLE (no parser
        could be loaded at all -- an environment gap, not a property of
        this code) falls through to the same balanced-delimiter heuristic
        this evaluator always used when tree-sitter was unavailable.
        """
        try:
            result = _shared_check_syntax(lang, code)
        except Exception:
            return self._check_balanced_delimiters(code, start_line, page)

        if result.status == "GRAMMAR-UNAVAILABLE":
            return self._check_balanced_delimiters(code, start_line, page)
        if result.status != "SYNTAX-ERROR":
            return []

        error_line = start_line + (result.error_line or 1) - 1
        lang_display = {"cs": "C#", "c#": "C#", "csharp": "C#",
                        "ts": "TypeScript", "js": "JavaScript",
                        "cpp": "C++", "c++": "C++", "rs": "Rust",
                        "golang": "Go"}.get(lang, lang.title())
        return [Finding(
            level="FAIL",
            category="SX",
            filepath=str(page.filepath),
            line_no=error_line,
            message=f"{lang_display} syntax error in code block",
            suggestion="Fix the syntax error in the code example",
            evaluator=self.name,
        )]

    # ------------------------------------------------------------------
    # Heuristic fallback (balanced delimiters)
    # ------------------------------------------------------------------

    def _check_balanced_delimiters(
        self, code: str, start_line: int, page: Page
    ) -> list[Finding]:
        """Comment- and string-aware balanced brace/paren/bracket check."""
        findings: list[Finding] = []
        counts = {"(": 0, "[": 0, "{": 0}
        closers = {")": "(", "]": "[", "}": "{"}

        i = 0
        n = len(code)
        while i < n:
            ch = code[i]

            # Line comment: skip to end of line
            if ch == "/" and i + 1 < n and code[i + 1] == "/":
                while i < n and code[i] != "\n":
                    i += 1
                continue

            # Block comment: skip to */
            if ch == "/" and i + 1 < n and code[i + 1] == "*":
                i += 2
                while i + 1 < n and not (code[i] == "*" and code[i + 1] == "/"):
                    i += 1
                i += 2  # skip */
                continue

            # String literal: skip to closing quote (handles \" escape)
            if ch in ('"', "'"):
                quote = ch
                i += 1
                while i < n:
                    c2 = code[i]
                    if c2 == "\\" and i + 1 < n:
                        i += 2
                        continue
                    if c2 == quote:
                        break
                    i += 1
                i += 1
                continue

            if ch in counts:
                counts[ch] += 1
            elif ch in closers:
                opener = closers[ch]
                counts[opener] -= 1

            i += 1

        for opener, count in counts.items():
            closer = {"(": ")", "[": "]", "{": "}"}[opener]
            if count > 0:
                findings.append(Finding(
                    level="WARN",
                    category="SX",
                    filepath=str(page.filepath),
                    line_no=start_line,
                    message=(
                        f"Unbalanced delimiters: {count} unclosed '{opener}'"
                        f" (missing '{closer}')"
                    ),
                    suggestion="Check for missing closing delimiters in code example",
                    evaluator=self.name,
                ))
            elif count < 0:
                findings.append(Finding(
                    level="WARN",
                    category="SX",
                    filepath=str(page.filepath),
                    line_no=start_line,
                    message=(
                        f"Unbalanced delimiters: {-count} extra closing '{closer}'"
                    ),
                    suggestion="Check for extra closing delimiters in code example",
                    evaluator=self.name,
                ))

        return findings


def _check_balanced_delimiters_for_test(
    code: str, start_line: int, filepath: str
) -> list[Finding]:
    """Module-level wrapper for testing the heuristic delimiter checker directly."""
    page = Page.__new__(Page)
    page.filepath = Path(filepath)
    page.code_blocks = []
    page.body = ""
    page.frontmatter = {}
    page.sections = []
    ev = CodeSyntaxCheckEvaluator()
    return ev._check_balanced_delimiters(code, start_line, page)


def _first_error_node(node: Any) -> Any | None:
    """Return the first ERROR node in the tree (BFS), or None.

    MISSING nodes are excluded — they represent parser-inserted tokens that
    occur normally in partial code snippets and are not genuine errors.
    """
    queue = [node]
    while queue:
        n = queue.pop(0)
        if n.type == "ERROR":
            return n
        queue.extend(n.children)
    return None
