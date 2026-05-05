"""Code syntax check evaluator — validates code block syntax.

H-14: Catches syntax errors that code_plausibility misses:
  - Python: ast.parse() for syntax validation → FAIL on SyntaxError
  - Java, C#, TypeScript, JavaScript, C++: tree-sitter parse → FAIL on has_error
  - Other brace languages: heuristic balanced-delimiter check → WARN

Skips blocks shorter than 3 lines (intentional fragments).
Skips blocks with ``# noqa: syntax`` on line 1 (escape hatch).

Tree-sitter language packages required for full validation:
  pip install tree-sitter-python tree-sitter-java tree-sitter-c-sharp
              tree-sitter-typescript tree-sitter-javascript tree-sitter-cpp
If packages are absent, falls back to heuristic delimiter check for those languages.
"""

from __future__ import annotations

import ast
import re
import textwrap
from pathlib import Path
from typing import Any

from ..models import Finding, Page
from . import BaseEvaluator

# Language tags that use ast.parse (Python is handled separately — more precise)
_PYTHON_LANGS = {"python", "py"}

# Language tags handled by tree-sitter (when available)
_TS_LANGS = {"java", "csharp", "cs", "c#", "typescript", "ts",
             "javascript", "js", "cpp", "c++"}

# Language tags for heuristic fallback (tree-sitter absent, or other brace langs)
_BRACE_LANGS = _TS_LANGS | {"kotlin", "swift", "go", "rust", "scala"}

# Skip these block types entirely — not programming languages
_SKIP_LANGS = {"bash", "shell", "sh", "xml", "json", "yaml", "toml", "text",
               "plain", "html", "css", "sql", "gradle", "groovy", "powershell",
               "bat", "cmd", "console", "markdown", "md", "output", "ini",
               "properties", "diff", ""}

# Noqa marker
_NOQA_SYNTAX_RE = re.compile(r"#\s*noqa:\s*syntax", re.IGNORECASE)

# Tree-sitter parser cache: lang_tag -> Parser instance (or None if unavailable)
_TS_PARSER_CACHE: dict[str, Any] = {}
_TS_LOADED = False


def _load_ts_parsers() -> None:
    """Attempt to load all tree-sitter language parsers; populate _TS_PARSER_CACHE."""
    global _TS_LOADED
    if _TS_LOADED:
        return
    _TS_LOADED = True

    try:
        from tree_sitter import Language, Parser  # type: ignore[import]
    except ImportError:
        return  # tree-sitter core not available — all parsers will be None

    def _make(lang_fn):
        try:
            return Parser(Language(lang_fn()))
        except Exception:
            return None

    # Python via tree-sitter (not used — ast.parse is preferred)
    # but register to avoid fallback on explicit 'python' tag
    try:
        import tree_sitter_java as _tsj
        p = _make(_tsj.language)
        if p:
            _TS_PARSER_CACHE["java"] = p
    except ImportError:
        pass

    try:
        import tree_sitter_c_sharp as _tscs
        p = _make(_tscs.language)
        if p:
            for tag in ("csharp", "cs", "c#"):
                _TS_PARSER_CACHE[tag] = p
    except ImportError:
        pass

    try:
        import tree_sitter_typescript as _tsts
        ts_p = _make(_tsts.language_typescript)
        if ts_p:
            for tag in ("typescript", "ts"):
                _TS_PARSER_CACHE[tag] = ts_p
        tsx_p = _make(_tsts.language_tsx)
        if tsx_p:
            _TS_PARSER_CACHE["tsx"] = tsx_p
    except ImportError:
        pass

    try:
        import tree_sitter_javascript as _tsjs
        p = _make(_tsjs.language)
        if p:
            for tag in ("javascript", "js"):
                _TS_PARSER_CACHE[tag] = p
    except ImportError:
        pass

    try:
        import tree_sitter_cpp as _tscpp
        p = _make(_tscpp.language)
        if p:
            for tag in ("cpp", "c++"):
                _TS_PARSER_CACHE[tag] = p
    except ImportError:
        pass


def _ts_parser_for(lang_tag: str) -> Any | None:
    """Return a cached tree-sitter Parser for lang_tag, or None if unavailable."""
    _load_ts_parsers()
    return _TS_PARSER_CACHE.get(lang_tag)


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
            elif lang in _TS_LANGS:
                parser = _ts_parser_for(lang)
                if parser is not None:
                    findings.extend(
                        self._check_ts_syntax(content, block.start_line, page, parser, lang)
                    )
                else:
                    # Graceful fallback: tree-sitter not installed
                    findings.extend(
                        self._check_balanced_delimiters(content, block.start_line, page)
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
    # Tree-sitter (Java / C# / TypeScript / JavaScript / C++)
    # ------------------------------------------------------------------

    def _check_ts_syntax(
        self, code: str, start_line: int, page: Page, parser: Any, lang: str
    ) -> list[Finding]:
        """Use tree-sitter to validate a code block.

        FAIL when an ERROR node is found (genuine unrecognised token/structure).
        MISSING nodes (parser-inserted tokens to complete a partial parse) are
        common in valid code snippets and are NOT treated as errors.
        """
        try:
            tree = parser.parse(code.encode("utf-8", errors="replace"))
        except Exception:
            return []  # never let a parser crash block the evaluator

        if not tree.root_node.has_error:
            return []

        # Distinguish ERROR (real syntax issue) from MISSING (snippet-context artefact)
        first_error = _first_error_node(tree.root_node)
        if first_error is None:
            return []  # only MISSING nodes — not a real error in a snippet

        error_line = start_line + first_error.start_point[0]
        lang_display = {"cs": "C#", "c#": "C#", "csharp": "C#",
                        "ts": "TypeScript", "js": "JavaScript",
                        "cpp": "C++", "c++": "C++"}.get(lang, lang.title())
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
