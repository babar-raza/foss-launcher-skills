"""Install recipe evaluator — detects API documentation pages that lack installation guidance.

Documentation pages that demonstrate API usage (code blocks or backtick
references) but contain no installation instructions and no link to an
installation page are flagged as INFO.  This is a cross-page concern, so the
severity is kept low.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..models import Finding, Page
from . import BaseEvaluator

KNOWLEDGE_ROOT = Path("knowledge")

# Package-manager / install command patterns (case-insensitive)
_INSTALL_PROSE_RE = re.compile(
    r"pip\s+install|mvn\b|<dependency\b|dotnet\s+add\s+package|nuget\b"
    r"|npm\s+install|cargo\s+add|\[dependencies\]|gem\s+install"
    r"|composer\s+require",
    re.IGNORECASE,
)

# Heading text patterns that indicate an install/setup section
_INSTALL_HEADING_RE = re.compile(
    r"\b(?:install|setup|prerequisite|requirement|getting[\s-]started)\b",
    re.IGNORECASE,
)

# URL fragments that suggest a link to an install page
_INSTALL_URL_RE = re.compile(
    r"installation|getting-started|getting_started|quickstart",
    re.IGNORECASE,
)

# Slug patterns: if the page itself is an install/setup page, skip it
_INSTALL_SLUG_RE = re.compile(
    r"installation|getting-started|getting_started|install\b|setup",
    re.IGNORECASE,
)

# Backtick API reference pattern in prose
_BACKTICK_API_RE = re.compile(r"`[A-Z][A-Za-z0-9]+(?:\.[a-zA-Z0-9]+)?`")

# H-16: Package name extraction from install commands
_PKG_NAME_RE = re.compile(
    r"(?:pip\s+install|npm\s+install|dotnet\s+add\s+package|nuget\s+install"
    r"|cargo\s+add)\s+(\S+)",
    re.IGNORECASE,
)

# H-16: Platform → expected package managers
_PLATFORM_PKG_MANAGERS: dict[str, set[str]] = {
    "python": {"pip"},
    "net": {"dotnet", "nuget"},
    "java": {"mvn", "gradle"},
    "cpp": {"vcpkg", "conan", "cmake"},
    "typescript": {"npm", "yarn", "pnpm"},
    "javascript": {"npm", "yarn", "pnpm"},
    "rust": {"cargo"},
}

# Package manager detection pattern
_PKG_MANAGER_RE = re.compile(
    r"\b(pip|npm|yarn|pnpm|dotnet|nuget|mvn|gradle|vcpkg|conan|cmake|cargo|gem|composer)\b",
    re.IGNORECASE,
)


class InstallRecipeEvaluator(BaseEvaluator):
    """Flags documentation pages that demonstrate API usage but lack install guidance.

    Only applies to ``docs`` subdomain pages with role ``docs`` or ``howto``
    that are not index pages.  Level is INFO because installation instructions
    may legitimately live on a linked page.
    """

    name = "install_recipe"

    def evaluate(self, page: Page, knowledge: Any) -> list[Finding]:
        # Gate: only docs subdomain, docs/howto role, non-index pages
        if page.subdomain != "docs":
            return []
        if page.page_role not in ("docs", "howto"):
            return []
        if page.filepath.name == "_index.md":
            return []

        # H-16: Always run install accuracy check (even if install instructions exist)
        accuracy_findings = self._verify_install_accuracy(page)

        # Skip if this page IS an installation/setup page
        page_path_str = str(page.filepath).replace("\\", "/")
        if _INSTALL_SLUG_RE.search(page_path_str):
            return accuracy_findings

        # Check whether the page has meaningful API usage
        code_block_count = len(page.code_blocks)
        backtick_api_count = sum(
            len(_BACKTICK_API_RE.findall(line))
            for _, line in page.prose_lines
        )
        has_api_usage = code_block_count >= 1 or backtick_api_count >= 3
        if not has_api_usage:
            return accuracy_findings

        # Check for installation content in prose
        for _, line in page.prose_lines:
            if _INSTALL_PROSE_RE.search(line):
                return accuracy_findings  # Install instructions present

        # Check for install instructions inside code blocks
        for block in page.code_blocks:
            if _INSTALL_PROSE_RE.search(block.content):
                return accuracy_findings

        # Check for install-related headings
        for heading in page.headings:
            if _INSTALL_HEADING_RE.search(heading.text):
                return accuracy_findings

        # Check for links pointing to an installation page
        for link in page.links:
            if _INSTALL_URL_RE.search(link.url):
                return accuracy_findings

        # No install content found — build a helpful suggestion
        suggestion = (
            "Add installation instructions or link to an installation page. "
        )
        if page.family and page.platform:
            install_md = KNOWLEDGE_ROOT / page.family / page.platform / "merged" / "install.md"
            if install_md.exists():
                content = install_md.read_text(encoding="utf-8", errors="replace")
                if len(content) > 50:
                    suggestion += (
                        f"Installation content is available at "
                        f"knowledge/{page.family}/{page.platform}/merged/install.md"
                    )

        accuracy_findings.append(Finding(
            level="INFO",
            category="IR",
            filepath=str(page.filepath),
            line_no=1,
            message=(
                f"Page demonstrates API usage ({code_block_count} code block(s), "
                f"{backtick_api_count} backtick ref(s)) but has no installation instructions"
            ),
            suggestion=suggestion.strip(),
            evaluator=self.name,
        ))
        return accuracy_findings

    # ------------------------------------------------------------------
    # H-16: Install accuracy verification
    # ------------------------------------------------------------------

    def _verify_install_accuracy(self, page: Page) -> list[Finding]:
        """Cross-check install commands against knowledge/merged/install.md."""
        if not page.family or not page.platform:
            return []

        install_md = KNOWLEDGE_ROOT / page.family / page.platform / "merged" / "install.md"
        if not install_md.exists():
            return []

        try:
            knowledge_text = install_md.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return []
        if len(knowledge_text) < 20:
            return []

        knowledge_packages = set(
            m.group(1).lower()
            for m in _PKG_NAME_RE.finditer(knowledge_text)
        )

        findings: list[Finding] = []

        # Check page code blocks for install commands
        for block in page.code_blocks:
            if block.lang not in ("bash", "shell", "sh", "powershell", "cmd",
                                  "console", "text", "plain", ""):
                continue
            page_packages = set(
                m.group(1).lower()
                for m in _PKG_NAME_RE.finditer(block.content)
            )
            for pkg in page_packages:
                if knowledge_packages and pkg not in knowledge_packages:
                    findings.append(Finding(
                        level="WARN",
                        category="IR",
                        filepath=str(page.filepath),
                        line_no=block.start_line,
                        message=(
                            f"Install command references `{pkg}` but "
                            f"knowledge install.md uses different package(s)"
                        ),
                        suggestion=(
                            f"Verify package name against "
                            f"knowledge/{page.family}/{page.platform}/merged/install.md"
                        ),
                        evaluator=self.name,
                    ))

            # Check for wrong-platform package managers
            expected_managers = _PLATFORM_PKG_MANAGERS.get(page.platform, set())
            if expected_managers:
                for m in _PKG_MANAGER_RE.finditer(block.content):
                    manager = m.group(1).lower()
                    if manager not in expected_managers:
                        findings.append(Finding(
                            level="WARN",
                            category="IR",
                            filepath=str(page.filepath),
                            line_no=block.start_line + block.content[:m.start()].count("\n"),
                            message=(
                                f"Package manager `{manager}` is not appropriate "
                                f"for {page.platform} platform"
                            ),
                            suggestion=(
                                f"Use {', '.join(sorted(expected_managers))} "
                                f"instead of `{manager}` for {page.platform}"
                            ),
                            evaluator=self.name,
                        ))

        return findings
