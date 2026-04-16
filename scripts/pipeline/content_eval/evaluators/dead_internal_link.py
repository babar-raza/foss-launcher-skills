"""Dead internal link evaluator (FIX-08).

Checks all relative markdown links (../path, ../../path) and resolves them
against the file's directory. Emits WARN for links whose resolved target
does not exist on disk.

Category: DL (Dead Link)
"""

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
            # Strip anchor fragments (#section)
            url_no_anchor = url.split("#")[0]
            if not url_no_anchor:
                continue

            # Only check relative links (../ or ./ or bare paths)
            if url_no_anchor.startswith("/"):
                # Absolute paths like /slides/net/... — harder to resolve
                # without knowing the content root; skip for now
                continue

            resolved = (page_dir / url_no_anchor).resolve()

            # Hugo pages can be either filename.md or filename/_index.md
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
                    suggestion=(
                        "Remove the link, fix the path, or create the "
                        "missing target page."
                    ),
                    evaluator=self.name,
                ))

        return findings
