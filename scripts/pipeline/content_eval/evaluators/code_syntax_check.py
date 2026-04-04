"""Code syntax check evaluator — validates code block syntax.

H-14: Catches syntax errors that code_plausibility misses:
  - Python: ast.parse() for syntax validation → FAIL on SyntaxError
  - Other languages: heuristic balanced-delimiter check → WARN

Skips blocks shorter than 3 lines (intentional fragments).
Skips blocks with ``# noqa: syntax`` on line 1 (escape hatch).
"""

from __future__ import annotations

import ast
import re
import textwrap
from typing import Any

from ..models import Finding, Page
from . import BaseEvaluator

# Language tags that support ast.parse()
_PYTHON_LANGS = {"python", "py"}

# Language tags for heuristic checks
_BRACE_LANGS = {"java", "csharp", "cs", "c#", "cpp", "c++", "typescript",
                "ts", "javascript", "js"}

# Skip these block types entirely
_SKIP_LANGS = {"bash", "shell", "sh", "xml", "json", "yaml", "toml", "text",
               "plain", "html", "css", "sql", "gradle", "groovy", "powershell",
               "bat", "cmd", "console", "markdown", "md", "output", "ini",
               "properties", "diff"}

# Noqa marker
_NOQA_SYNTAX_RE = re.compile(r"#\s*noqa:\s*syntax", re.IGNORECASE)


class CodeSyntaxCheckEvaluator(BaseEvaluator):
    """Validates code block syntax: ast.parse for Python, heuristic for others."""

    name = "code_syntax_check"

    def evaluate(self, page: Page, knowledge: Any) -> list[Finding]:
        findings: list[Finding] = []

        for block in page.code_blocks:
            lang = (block.lang or "").lower()
            if lang in _SKIP_LANGS:
                continue

            content = textwrap.dedent(block.content).strip()
            lines = content.splitlines()

            # Skip very short blocks (intentional fragments)
            if len(lines) < 3:
                continue

            # Skip blocks with noqa marker
            if lines and _NOQA_SYNTAX_RE.search(lines[0]):
                continue

            if lang in _PYTHON_LANGS:
                findings.extend(
                    self._check_python_syntax(content, block.start_line, page)
                )
            elif lang in _BRACE_LANGS:
                findings.extend(
                    self._check_balanced_delimiters(content, block.start_line, page)
                )

        return findings

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

    def _check_balanced_delimiters(
        self, code: str, start_line: int, page: Page
    ) -> list[Finding]:
        """Heuristic check for balanced braces, parens, brackets."""
        findings: list[Finding] = []
        # Track delimiter counts, ignoring those inside strings
        counts = {"(": 0, "[": 0, "{": 0}
        closers = {")": "(", "]": "[", "}": "{"}

        # Simple string-aware scanner (not perfect but catches obvious issues)
        in_string = False
        string_char = ""
        for i, ch in enumerate(code):
            if in_string:
                if ch == string_char and (i == 0 or code[i - 1] != "\\"):
                    in_string = False
                continue
            if ch in ('"', "'"):
                in_string = True
                string_char = ch
                continue
            if ch in counts:
                counts[ch] += 1
            elif ch in closers:
                opener = closers[ch]
                counts[opener] -= 1

        for opener, count in counts.items():
            if count > 0:
                closer = {"(": ")", "[": "]", "{": "}"}[opener]
                findings.append(Finding(
                    level="WARN",
                    category="SX",
                    filepath=str(page.filepath),
                    line_no=start_line,
                    message=f"Unbalanced delimiters: {count} unclosed '{opener}' (missing '{closer}')",
                    suggestion="Check for missing closing delimiters in code example",
                    evaluator=self.name,
                ))
            elif count < 0:
                findings.append(Finding(
                    level="WARN",
                    category="SX",
                    filepath=str(page.filepath),
                    line_no=start_line,
                    message=f"Unbalanced delimiters: {-count} extra closing '{opener}'",
                    suggestion="Check for extra closing delimiters in code example",
                    evaluator=self.name,
                ))

        return findings
