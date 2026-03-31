"""Platform purity evaluator — detects wrong-language contamination."""

from __future__ import annotations

import re
from typing import Any

from ..config import (
    LANG_TO_PLATFORM,
    PLATFORM_EXPECTED_LANGS,
    PLATFORM_FOREIGN_PATTERNS,
    PROSE_FOREIGN_PATTERNS,
)
from ..models import Finding, Page
from . import BaseEvaluator


class PlatformPurityEvaluator(BaseEvaluator):
    """Detects code and prose from wrong platforms.

    Scans code blocks for foreign-language patterns (e.g., Python `def` in
    a .NET page) and prose for wrong-platform tool references (e.g., `pip install`
    in a Java page).
    """

    name = "platform_purity"

    def evaluate(self, page: Page, knowledge: Any) -> list[Finding]:
        if not page.platform:
            return []

        findings: list[Finding] = []
        platform = page.platform

        # Check code blocks
        foreign_patterns = PLATFORM_FOREIGN_PATTERNS.get(platform, [])
        expected_langs = PLATFORM_EXPECTED_LANGS.get(platform, set())

        for block in page.code_blocks:
            # Skip non-code blocks (bash, shell, xml, json, yaml, etc.)
            if block.lang in ("bash", "shell", "sh", "xml", "json", "yaml",
                              "toml", "text", "plain", "html", "css", "sql",
                              "gradle", "groovy", "powershell", "bat", "cmd",
                              "console", ""):
                continue

            # Check if code block language matches the page platform
            block_platform = LANG_TO_PLATFORM.get(block.lang.lower(), "")
            if block_platform and block_platform != platform and expected_langs:
                findings.append(Finding(
                    level="FAIL",
                    category="PC",
                    filepath=str(page.filepath),
                    line_no=block.start_line,
                    message=f"Code block tagged as `{block.lang}` on {platform} page",
                    suggestion=f"Expected one of: {', '.join(sorted(expected_langs))}",
                    evaluator=self.name,
                ))

            # Check for foreign-language patterns inside code blocks
            code_lines = block.content.splitlines()
            for j, code_line in enumerate(code_lines):
                line_no = block.start_line + 1 + j
                for pattern, desc in foreign_patterns:
                    if re.search(pattern, code_line):
                        findings.append(Finding(
                            level="WARN",
                            category="PC",
                            filepath=str(page.filepath),
                            line_no=line_no,
                            message=f"Foreign code pattern in {platform} code block: {desc}",
                            suggestion=f"Verify this is not copied from another platform",
                            evaluator=self.name,
                        ))
                        break  # One finding per line

        # Check prose for platform contamination
        prose_patterns = PROSE_FOREIGN_PATTERNS.get(platform, [])
        for line_no, line_text in page.prose_lines:
            for pattern, desc in prose_patterns:
                if re.search(pattern, line_text, re.IGNORECASE):
                    findings.append(Finding(
                        level="WARN",
                        category="PC",
                        filepath=str(page.filepath),
                        line_no=line_no,
                        message=f"Platform contamination in prose: {desc}",
                        suggestion="Verify this reference belongs on this platform's page",
                        evaluator=self.name,
                    ))

        return findings
