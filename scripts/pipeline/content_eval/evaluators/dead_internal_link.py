"""Dead internal link evaluator -- validates relative markdown links resolve to files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..models import Finding, Page
from . import BaseEvaluator


class DeadInternalLinkEvaluator(BaseEvaluator):
    """Validates that relative links in content point to existing files."""

    name = "dead_internal_link"

    def evaluate(self, page: Page, knowledge: Any) -> list[Finding]:
        findings: list[Finding] = []

        if not page.links:
            return findings

        page_dir = page.filepath.parent

        for link in page.links:
            if not link.is_internal:
                continue

            url = link.url
            url_no_anchor = url.split("#")[0]
            if not url_no_anchor:
                continue

            if url_no_anchor.startswith("/"):
                continue

            resolved = (page_dir / url_no_anchor).resolve()

            exists = (
                resolved.exists()
                or resolved.with_suffix(".md").exists()
                or (resolved / "_index.md").exists()
            )

            if not exists:
                findings.append(Finding(
                    level="WARN",
                    category="DL",
                    filepath=str(page.filepath),
                    line_no=link.line_no,
                    message=(
                        f"Dead internal link: `{link.url}` resolves to "
                        f"`{resolved}` which does not exist"
                    ),
                    suggestion="Remove the link, fix the path, or create the missing target page.",
                    evaluator=self.name,
                ))

        return findings
