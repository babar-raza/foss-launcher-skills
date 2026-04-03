"""Structure evaluator — heading hierarchy, code fences, placeholders, links."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..config import PLACEHOLDER_PATTERNS
from ..models import Finding, Page
from . import BaseEvaluator

# ---------------------------------------------------------------------------
# Internal-link target resolution helpers
# ---------------------------------------------------------------------------

# Subdomains that have generated content pages in this repo.
_INTERNAL_SUBDOMAINS = frozenset({
    "reference.aspose.org",
    "docs.aspose.org",
    "kb.aspose.org",
    "blog.aspose.org",
    "products.aspose.org",
})

# Regex to extract a recognised aspose.org subdomain URL from a link href.
# Matches both https://reference.aspose.org/... and /reference.aspose.org/...
_ASPOSE_URL_RE = re.compile(
    r"(?:https?://|/)?((?:reference|docs|kb|blog|products)\.aspose\.org)"
    r"(/[^\s)\"'#?]*)",
    re.IGNORECASE,
)

# Content root relative to repository root.
_CONTENT_ROOT = Path("content")


def _resolve_link_target(url: str, repo_root: Path) -> tuple[str, bool]:
    """Check whether an aspose.org internal URL resolves to a file on disk.

    Returns (verdict, is_aspose_internal) where verdict is one of:
      "OK"               — file or directory index exists
      "UPSTREAM_MISSING" — no file found at all
      "BAD_LINK_FORMAT"  — file exists under a different casing/slug variant
      "NOT_INTERNAL"     — not a recognised aspose.org URL

    is_aspose_internal is True whenever the URL refers to a known subdomain.
    """
    m = _ASPOSE_URL_RE.search(url)
    if not m:
        return "NOT_INTERNAL", False

    subdomain = m.group(1).lower()   # e.g. "reference.aspose.org"
    path_part = m.group(2).rstrip("/")  # e.g. "/slides/net/EffectFormat"

    # Strip leading /en/ (English content is stored without the locale prefix
    # in the knowledge models but Hugo serves it under /en/).
    segments = [s for s in path_part.split("/") if s]
    if segments and segments[0] == "en":
        segments = segments[1:]

    # Build the expected filesystem path.
    # Hugo content layout: content/{subdomain}/en/{rest...}
    candidate_dirs: list[Path] = []
    base = repo_root / _CONTENT_ROOT / subdomain / "en"
    slug_path = Path(*segments) if segments else Path(".")

    # Exact match: directory with _index.md or file.md
    candidate_dirs.append(base / slug_path / "_index.md")
    candidate_dirs.append(base / slug_path / "index.md")
    if segments:
        candidate_dirs.append(base / slug_path.parent / (slug_path.name + ".md"))

    for c in candidate_dirs:
        if c.exists():
            return "OK", True

    # Case-insensitive search: look for any variant of the last segment.
    if segments:
        parent = base / Path(*segments[:-1]) if len(segments) > 1 else base
        target_lower = segments[-1].lower()
        if parent.is_dir():
            for child in parent.iterdir():
                child_stem = child.stem if child.suffix == ".md" else child.name
                if child_stem.lower() == target_lower and child_stem != segments[-1]:
                    return "BAD_LINK_FORMAT", True
            # No match at all
            return "UPSTREAM_MISSING", True
    return "UPSTREAM_MISSING", True


class StructureEvaluator(BaseEvaluator):
    """Validates structural correctness of content pages.

    Checks:
    - Frontmatter has title and description
    - No placeholder text remains
    - Heading hierarchy is valid (no skipped levels)
    - Code blocks have language identifiers
    - Filename uses kebab-case
    - Blog posts have required canonical sections (P-07)
    """

    name = "structure"

    # Minimum required H2 headings for blog posts (P-07).
    # Uses lowercase for case-insensitive matching.
    _BLOG_REQUIRED_HEADINGS = (
        "introduction",
        "quick start",
        "getting started",
    )

    def evaluate(self, page: Page, knowledge: Any) -> list[Finding]:
        findings: list[Finding] = []
        findings.extend(self._check_frontmatter(page))
        findings.extend(self._check_placeholders(page))
        findings.extend(self._check_heading_hierarchy(page))
        findings.extend(self._check_code_fences(page))
        findings.extend(self._check_filename(page))
        findings.extend(self._check_empty_body(page))
        findings.extend(self._check_broken_links(page))
        if page.page_role == "blog":
            findings.extend(self._check_blog_sections(page))
        return findings

    def _check_frontmatter(self, page: Page) -> list[Finding]:
        findings: list[Finding] = []
        fm = page.frontmatter

        if not fm.get("title"):
            findings.append(Finding(
                level="FAIL",
                category="ST",
                filepath=str(page.filepath),
                line_no=1,
                message="Missing or empty `title` in frontmatter",
                suggestion="Add a `title` field",
                evaluator=self.name,
            ))

        if not fm.get("description"):
            # Reference pages must have a description — FAIL; all others WARN
            desc_level = "FAIL" if page.subdomain == "reference" else "WARN"
            findings.append(Finding(
                level=desc_level,
                category="ST",
                filepath=str(page.filepath),
                line_no=1,
                message="Missing or empty `description` in frontmatter",
                suggestion="Add a `description` field for SEO",
                evaluator=self.name,
            ))

        # Check date format
        for date_field in ("date", "lastmod"):
            val = fm.get(date_field)
            if val and isinstance(val, str):
                if not re.match(r"^\d{4}-\d{2}-\d{2}", val):
                    findings.append(Finding(
                        level="WARN",
                        category="ST",
                        filepath=str(page.filepath),
                        line_no=1,
                        message=f"`{date_field}` not in YYYY-MM-DD format: {val}",
                        suggestion="Use format: 'YYYY-MM-DD'",
                        evaluator=self.name,
                    ))

        return findings

    def _check_placeholders(self, page: Page) -> list[Finding]:
        findings: list[Finding] = []
        for line_no, line_text in page.prose_lines:
            for pattern, desc in PLACEHOLDER_PATTERNS:
                if re.search(pattern, line_text):
                    findings.append(Finding(
                        level="FAIL",
                        category="ST",
                        filepath=str(page.filepath),
                        line_no=line_no,
                        message=f"Placeholder text found: {desc}",
                        suggestion="Replace with actual content",
                        evaluator=self.name,
                    ))
                    break  # One finding per line

        return findings

    def _check_heading_hierarchy(self, page: Page) -> list[Finding]:
        findings: list[Finding] = []
        prev_level = 0

        for heading in page.headings:
            if prev_level > 0 and heading.level > prev_level + 1:
                findings.append(Finding(
                    level="INFO",
                    category="ST",
                    filepath=str(page.filepath),
                    line_no=heading.line_no,
                    message=f"Heading level skipped: h{prev_level} → h{heading.level}",
                    suggestion=f"Use h{prev_level + 1} instead of h{heading.level}",
                    evaluator=self.name,
                ))
            prev_level = heading.level

        return findings

    def _check_code_fences(self, page: Page) -> list[Finding]:
        findings: list[Finding] = []

        _BOX_DRAWING = re.compile(r"[└├│┌┐┘┬┤─┼]")

        for block in page.code_blocks:
            if not block.lang:
                # Downgrade ASCII art / short output blocks to INFO
                lines = block.content.splitlines()
                is_ascii_art = bool(_BOX_DRAWING.search(block.content))
                is_short = len(lines) <= 3
                level = "INFO" if (is_ascii_art or is_short) else "WARN"
                findings.append(Finding(
                    level=level,
                    category="ST",
                    filepath=str(page.filepath),
                    line_no=block.start_line,
                    message="Code block missing language identifier",
                    suggestion="Add a language tag: ```python, ```csharp, etc.",
                    evaluator=self.name,
                ))

        return findings

    def _check_filename(self, page: Page) -> list[Finding]:
        findings: list[Finding] = []
        name = page.filepath.stem

        # Skip _index files
        if name == "_index":
            return findings

        # Check kebab-case (allow leading underscore)
        if not re.match(r"^_?[a-z0-9]+(?:-[a-z0-9]+)*$", name):
            # Don't flag index.md (common for blog posts)
            if name != "index":
                findings.append(Finding(
                    level="INFO",
                    category="ST",
                    filepath=str(page.filepath),
                    line_no=1,
                    message=f"Filename `{name}.md` not in kebab-case",
                    suggestion="Use lowercase with hyphens: my-page-name.md",
                    evaluator=self.name,
                ))

        return findings

    def _check_blog_sections(self, page: Page) -> list[Finding]:
        """Warn if a blog post is missing any of the minimum required H2 sections (P-07)."""
        findings: list[Finding] = []
        h2_texts = {
            h.text.strip().lower()
            for h in page.headings
            if h.level == 2
        }
        for required in self._BLOG_REQUIRED_HEADINGS:
            # Allow partial match: "getting started" matches "## Getting Started"
            if not any(required in h2 for h2 in h2_texts):
                findings.append(Finding(
                    level="WARN",
                    category="ST",
                    filepath=str(page.filepath),
                    line_no=1,
                    message=f"Blog post missing required section: `## {required.title()}`",
                    suggestion=(
                        f"Add a `## {required.title()}` section — "
                        "see skills/new-blog-post.md for the canonical 6-section structure"
                    ),
                    evaluator=self.name,
                ))
        return findings

    def _check_empty_body(self, page: Page) -> list[Finding]:
        if not page.body.strip():
            # Products pages store content in YAML frontmatter (layout: plugin)
            if page.frontmatter.get("layout") == "plugin":
                return []
            return [Finding(
                level="FAIL",
                category="ST",
                filepath=str(page.filepath),
                line_no=1,
                message="Page body is empty (only frontmatter)",
                suggestion="Add content below the frontmatter",
                evaluator=self.name,
            )]
        return []

    def _check_broken_links(self, page: Page) -> list[Finding]:
        """Detect broken internal aspose.org links and classify their cause.

        Emits WARN/ST findings with:
          cause_class: UPSTREAM_MISSING  — target page does not exist anywhere
          cause_class: BAD_LINK_FORMAT   — target exists under a different slug/casing
        """
        findings: list[Finding] = []
        # Resolve repo root: walk up from the file until we find a content/ dir.
        repo_root = page.filepath
        for _ in range(10):
            repo_root = repo_root.parent
            if (repo_root / "content").is_dir():
                break
        else:
            return findings  # Cannot locate repo root; skip silently.

        seen: set[str] = set()
        for link in page.links:
            url = link.url
            if url in seen:
                continue
            seen.add(url)

            verdict, is_internal = _resolve_link_target(url, repo_root)
            if not is_internal:
                continue
            if verdict == "OK":
                continue

            if verdict == "BAD_LINK_FORMAT":
                cause = "BAD_LINK_FORMAT"
                msg = (
                    f"Internal link target exists under a different URL format: `{url}` "
                    f"— check slug casing (reference pages use PascalCase class names)"
                )
                suggestion = (
                    "Correct the URL to match the generated page slug "
                    "(e.g. `/EffectFormat/` not `/effects/`). "
                    "Run `/link-validate` to find the exact target path."
                )
            else:  # UPSTREAM_MISSING
                cause = "UPSTREAM_MISSING"
                msg = (
                    f"Internal link target does not exist: `{url}` — "
                    "either the page has not been generated yet or the link is incorrect"
                )
                suggestion = (
                    "If the target class is in `api_surface.json`, run "
                    "`/batch-reference {family} {platform}` to generate the missing page. "
                    "If the link is wrong, correct it with `/manual-edit --scope body-wording`."
                )

            findings.append(Finding(
                level="WARN",
                category="ST",
                filepath=str(page.filepath),
                line_no=link.line_no,
                message=msg,
                suggestion=suggestion,
                evaluator=self.name,
                cause_class=cause,
            ))

        return findings
