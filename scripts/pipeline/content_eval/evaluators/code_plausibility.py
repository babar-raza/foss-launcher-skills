"""Code plausibility evaluator — validates code structure beyond token presence."""

from __future__ import annotations

import re
from typing import Any

from ..models import Finding, Page
from . import BaseEvaluator

# Common patterns that indicate implausible code
_EMPTY_BLOCK_RE = re.compile(r"^\s*$")
_UNCLOSED_STRING_RE = re.compile(r'(?<![\\])\"[^\"]*$|(?<![\\])\'[^\']*$')
_MULTIPLE_DOTS_RE = re.compile(r"\.\.\.")  # Ellipsis in code (placeholder)
_PSEUDO_COMMENT_RE = re.compile(
    r"//\s*(?:TODO|FIXME|HACK|add\s+your|replace\s+with|your\s+code\s+here)",
    re.IGNORECASE,
)


class CodePlausibilityEvaluator(BaseEvaluator):
    """Validates that code examples are structurally plausible.

    Checks:
    - Code blocks are not empty
    - No pseudo-code placeholder comments
    - No obviously truncated code (ellipsis as content)
    - Code blocks have reasonable length for their context
    """

    name = "code_plausibility"

    def evaluate(self, page: Page, knowledge: Any) -> list[Finding]:
        findings: list[Finding] = []

        for block in page.code_blocks:
            # Skip non-code blocks
            if block.lang in ("bash", "shell", "sh", "xml", "json", "yaml",
                              "toml", "text", "plain", "html", "css", "sql",
                              "gradle", "groovy", "powershell", "bat", "cmd",
                              "console", "markdown", "md"):
                continue

            content = block.content.strip()

            # Empty code block
            if not content:
                findings.append(Finding(
                    level="WARN",
                    category="CP",
                    filepath=str(page.filepath),
                    line_no=block.start_line,
                    message="Empty code block",
                    suggestion="Add code content or remove the block",
                    evaluator=self.name,
                ))
                continue

            lines = content.splitlines()

            # Check for pseudo-code placeholders
            for i, line in enumerate(lines):
                if _PSEUDO_COMMENT_RE.search(line):
                    findings.append(Finding(
                        level="WARN",
                        category="CP",
                        filepath=str(page.filepath),
                        line_no=block.start_line + 1 + i,
                        message="Placeholder comment in code example",
                        suggestion="Replace with actual working code",
                        evaluator=self.name,
                    ))

            # Check for ellipsis-as-code (truncated examples)
            ellipsis_lines = [i for i, line in enumerate(lines)
                              if line.strip() == "..." or line.strip() == "// ..."]
            if len(ellipsis_lines) > 0:
                findings.append(Finding(
                    level="INFO",
                    category="CP",
                    filepath=str(page.filepath),
                    line_no=block.start_line + 1 + ellipsis_lines[0],
                    message="Ellipsis in code example (truncated/incomplete)",
                    suggestion="Provide a complete, runnable example",
                    evaluator=self.name,
                ))

            # Very short code blocks in docs (not reference — reference commonly
            # has single-line signatures which are fine)
            if len(lines) == 1 and page.page_role == "docs":
                findings.append(Finding(
                    level="INFO",
                    category="CP",
                    filepath=str(page.filepath),
                    line_no=block.start_line,
                    message="Single-line code example in docs page",
                    suggestion="Consider expanding to a more complete example",
                    evaluator=self.name,
                ))

        return findings
