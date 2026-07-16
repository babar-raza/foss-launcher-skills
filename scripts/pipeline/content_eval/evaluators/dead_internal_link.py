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
        # Hugo renders a leaf page (e.g. developer-guide/diff.md) one URL segment
        # deeper than its filesystem location (developer-guide/diff/), but a
        # section index (_index.md) or leaf bundle (index.md) deploys at the
        # same depth as its directory. Relative links like ../sibling/ are
        # authored against the rendered URL, so they must resolve against that
        # same base — mirrors _build_slug_index() in link_validator.py.
        is_section_or_bundle = page.filepath.stem == "_index" or page.filepath.name == "index.md"
        base_dir = page_dir if is_section_or_bundle else page_dir / page.filepath.stem

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

            resolved = (base_dir / url_no_anchor).resolve()

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
