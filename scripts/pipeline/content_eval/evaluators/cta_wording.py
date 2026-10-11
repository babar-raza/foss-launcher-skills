"""CTA wording evaluator — detects deprecated CTAs, old URLs, and placeholder language."""

from __future__ import annotations

import re
from typing import Any

from ..models import Finding, Page
from . import BaseEvaluator

# Case-insensitive deprecated CTA phrases
_DEPRECATED_PHRASES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\btry\s+it\s+free\b", re.IGNORECASE), "Deprecated CTA phrase: \"Try it free\""),
    (re.compile(r"\bfree\s+trial\b", re.IGNORECASE), "Deprecated CTA phrase: \"Free trial\""),
    (re.compile(r"\bdownload\s+now\b", re.IGNORECASE), "Deprecated CTA phrase: \"Download now\""),
]

# Old download/release URLs
_OLD_URL_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"releases\.aspose\.com", re.IGNORECASE), "Old download URL: releases.aspose.com"),
    (re.compile(r"downloads\.aspose\.com", re.IGNORECASE), "Old download URL: downloads.aspose.com"),
]

# Double-prefix URL patterns
_DOUBLE_PREFIX_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"/products/products/", re.IGNORECASE), "Double-prefix URL: /products/products/"),
    (re.compile(r"products\.aspose\.org/products/", re.IGNORECASE), "Double-prefix URL: products.aspose.org/products/"),
]

# Placeholder language
_PLACEHOLDER_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bcoming[\s-]soon\b", re.IGNORECASE), "Placeholder language: \"coming soon\""),
]

# Path pattern for product pages
_PRODUCTS_PATH_RE = re.compile(
    r"content[/\\]products\.aspose\.org[/\\]en[/\\].*[/\\]?_index\.md$"
)


class CTAWordingEvaluator(BaseEvaluator):
    """Detects deprecated CTA phrases, old download URLs, double-prefix URLs,
    and placeholder language on product pages.

    Only activates for files matching content/products.aspose.org/en/**/_index.md.
    """

    name = "cta_wording"

    def evaluate(self, page: Page, knowledge: Any) -> list[Finding]:
        # Only activate for product pages
        filepath_str = str(page.filepath).replace("\\", "/")
        if not _PRODUCTS_PATH_RE.search(str(page.filepath)):
            return []

        findings: list[Finding] = []

        for line_no, line_text in page.prose_lines:
            # Check deprecated CTA phrases
            for pattern, desc in _DEPRECATED_PHRASES:
                if pattern.search(line_text):
                    findings.append(Finding(
                        level="FAIL",
                        category="CW",
                        filepath=str(page.filepath),
                        line_no=line_no,
                        message=desc,
                        suggestion="Replace with current CTA wording per brand guidelines",
                        evaluator=self.name,
                    ))

            # Check old download URLs
            for pattern, desc in _OLD_URL_PATTERNS:
                if pattern.search(line_text):
                    findings.append(Finding(
                        level="FAIL",
                        category="CW",
                        filepath=str(page.filepath),
                        line_no=line_no,
                        message=desc,
                        suggestion="Replace with current product URL (products.aspose.org or nuget/pip/maven links)",
                        evaluator=self.name,
                    ))

            # Check double-prefix URLs
            for pattern, desc in _DOUBLE_PREFIX_PATTERNS:
                if pattern.search(line_text):
                    findings.append(Finding(
                        level="FAIL",
                        category="CW",
                        filepath=str(page.filepath),
                        line_no=line_no,
                        message=desc,
                        suggestion="Remove the duplicate /products/ prefix from the URL",
                        evaluator=self.name,
                    ))

            # Check placeholder language
            for pattern, desc in _PLACEHOLDER_PATTERNS:
                if pattern.search(line_text):
                    findings.append(Finding(
                        level="WARN",
                        category="CW",
                        filepath=str(page.filepath),
                        line_no=line_no,
                        message=desc,
                        suggestion="Replace placeholder with actual content or remove the section",
                        evaluator=self.name,
                    ))

        return findings
