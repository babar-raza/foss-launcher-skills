"""Fixer: add missing language tag to bare code fences.

Detects ````` ``` ````` without a language identifier and adds the
platform-appropriate language (python, csharp, java, cpp, etc.).
"""

from __future__ import annotations

import re
from typing import Any

from ...config import PLATFORM_EXPECTED_LANGS
from ...models import Finding
from . import BaseFixer

# Primary language tag for each platform (first choice)
_PLATFORM_PRIMARY_LANG: dict[str, str] = {
    "python": "python",
    "dotnet": "csharp",
    "java": "java",
    "cpp": "cpp",
    "typescript": "typescript",
    "javascript": "javascript",
}

# Heuristics to detect shell/output blocks
_SHELL_INDICATORS = re.compile(
    r"^(\$\s|>\s|pip\s+install|npm\s+install|dotnet\s+add|mvn\s|cmake\s|nuget\s)",
    re.MULTILINE,
)
_XML_INDICATOR = re.compile(r"^\s*<\w+", re.MULTILINE)
_CMAKE_INDICATOR = re.compile(r"^\s*(?:cmake_minimum_required|find_package|add_library)", re.MULTILINE)


class CodeFenceLangFixer(BaseFixer):
    name = "code_fence_lang"
    categories = {"ST"}

    def can_fix(self, finding: Finding, page_text: str, meta: dict[str, Any]) -> bool:
        if "language" not in finding.message.lower():
            return False
        platform = meta.get("platform", "")
        if not platform:
            return False
        return True

    def apply(self, finding: Finding, page_text: str, meta: dict[str, Any]) -> str:
        platform = meta.get("platform", "")
        line_no = finding.line_no  # 1-based line of the opening ```

        lines = page_text.split("\n")
        if line_no < 1 or line_no > len(lines):
            return page_text

        idx = line_no - 1
        line = lines[idx]

        # Only fix bare ``` (with optional whitespace)
        if not re.match(r"^\s*```\s*$", line):
            return page_text

        # Gather the code block content to determine language
        code_lines = []
        for i in range(idx + 1, len(lines)):
            if lines[i].strip().startswith("```"):
                break
            code_lines.append(lines[i])

        lang = self._detect_language(code_lines, platform)

        # Replace the bare ``` with ```{lang}
        indent = line[: len(line) - len(line.lstrip())]
        lines[idx] = f"{indent}```{lang}"

        return "\n".join(lines)

    def _detect_language(self, code_lines: list[str], platform: str) -> str:
        """Detect appropriate language tag from code content and platform."""
        content = "\n".join(code_lines)

        # Check for shell/CLI content
        if _SHELL_INDICATORS.search(content):
            return "bash"

        # Check for XML (Maven pom, NuGet config)
        if _XML_INDICATOR.search(content) and "</" in content:
            return "xml"

        # Check for CMake
        if _CMAKE_INDICATOR.search(content):
            return "cmake"

        # Short blocks that look like plain output (no code keywords)
        if len(code_lines) <= 3 and not any(
            re.search(r"[=(){}\[\];]", ln) for ln in code_lines
        ):
            return "text"

        # Default to platform primary language
        return _PLATFORM_PRIMARY_LANG.get(platform, "text")
