"""Core data models for content_eval."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Frontmatter regex (same as audit.py)
# ---------------------------------------------------------------------------
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_CODE_FENCE_RE = re.compile(r"^```(\w*)")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)")


# ---------------------------------------------------------------------------
# Finding — extends audit.py's Finding with category, stable ID, severity
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class Finding:
    """A single evaluation finding with stable ID."""

    level: str              # FAIL, WARN, INFO
    category: str           # AA, PT, CP, RV, ST, PC, EG, RL, CG, XP, FC
    filepath: str           # relative path
    line_no: int
    message: str
    suggestion: str = ""
    evaluator: str = ""     # which evaluator produced this

    @property
    def id(self) -> str:
        """Deterministic ID: CE-{hash8}."""
        raw = f"{self.category}|{self.filepath}|{self.line_no}|{self.message}"
        return "CE-" + hashlib.sha256(raw.encode()).hexdigest()[:8]


# ---------------------------------------------------------------------------
# CodeBlock
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class CodeBlock:
    """A fenced code block extracted from markdown."""

    lang: str           # language tag (python, csharp, java, cpp, etc.)
    content: str        # raw code content
    start_line: int     # 1-based line number of the opening ```
    end_line: int       # 1-based line number of the closing ```


# ---------------------------------------------------------------------------
# Heading
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class Heading:
    """A markdown heading."""

    level: int          # 1-6
    text: str
    line_no: int


# ---------------------------------------------------------------------------
# Link
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class Link:
    """A markdown link."""

    text: str
    url: str
    line_no: int
    is_internal: bool


# ---------------------------------------------------------------------------
# Page — the central model
# ---------------------------------------------------------------------------
@dataclass
class Page:
    """A parsed content page with all extracted structures."""

    filepath: Path
    raw_text: str
    frontmatter: dict[str, Any] = field(default_factory=dict)
    body: str = ""                          # text after frontmatter
    body_offset: int = 0                    # line offset where body starts
    code_blocks: list[CodeBlock] = field(default_factory=list)
    headings: list[Heading] = field(default_factory=list)
    links: list[Link] = field(default_factory=list)
    prose_lines: list[tuple[int, str]] = field(default_factory=list)  # (line_no, text)

    # Inferred metadata
    family: str = ""
    platform: str = ""
    subdomain: str = ""     # docs, blog, kb, reference, products
    page_role: str = ""     # howto, faq, docs, blog, reference, products

    @classmethod
    def load(cls, filepath: Path) -> "Page":
        """Load and parse a markdown file into a Page."""
        raw = filepath.read_text(encoding="utf-8")
        page = cls(filepath=filepath, raw_text=raw)
        page._parse()
        page._infer_metadata()
        return page

    def _parse(self):
        """Parse frontmatter, code blocks, headings, links, prose."""
        # Frontmatter
        m = _FRONTMATTER_RE.match(self.raw_text)
        if m:
            try:
                self.frontmatter = yaml.safe_load(m.group(1)) or {}
            except yaml.YAMLError:
                self.frontmatter = {}
            self.body = self.raw_text[m.end():]
            self.body_offset = self.raw_text[:m.end()].count("\n")
        else:
            self.body = self.raw_text
            self.body_offset = 0

        lines = self.body.splitlines()
        in_code = False
        code_lang = ""
        code_start = 0
        code_lines: list[str] = []

        _LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")

        for i, line in enumerate(lines):
            abs_line = i + self.body_offset + 1  # 1-based

            # Code fence toggle
            if line.strip().startswith("```"):
                if not in_code:
                    fm = _CODE_FENCE_RE.match(line.strip())
                    code_lang = fm.group(1) if fm else ""
                    code_start = abs_line
                    code_lines = []
                    in_code = True
                else:
                    self.code_blocks.append(CodeBlock(
                        lang=code_lang,
                        content="\n".join(code_lines),
                        start_line=code_start,
                        end_line=abs_line,
                    ))
                    in_code = False
                continue

            if in_code:
                code_lines.append(line)
                continue

            # Heading
            hm = _HEADING_RE.match(line)
            if hm:
                self.headings.append(Heading(
                    level=len(hm.group(1)),
                    text=hm.group(2).strip(),
                    line_no=abs_line,
                ))

            # Links
            for lm in _LINK_RE.finditer(line):
                url = lm.group(2)
                is_internal = url.startswith("/") or url.startswith("../")
                self.links.append(Link(
                    text=lm.group(1),
                    url=url,
                    line_no=abs_line,
                    is_internal=is_internal,
                ))

            # Prose (non-heading, non-empty, non-shortcode)
            stripped = line.strip()
            if stripped and not hm and not stripped.startswith("{{% ") and not stripped.startswith("{{< "):
                self.prose_lines.append((abs_line, stripped))

    def _infer_metadata(self):
        """Infer family, platform, subdomain, page_role from path."""
        parts = self.filepath.parts
        for i, p in enumerate(parts):
            if p in ("products.aspose.org", "reference.aspose.org",
                      "docs.aspose.org", "blog.aspose.org", "kb.aspose.org"):
                self.subdomain = p.split(".")[0]
                remaining = list(parts[i + 1:])
                if remaining and remaining[0] == "en":
                    remaining = remaining[1:]
                if len(remaining) >= 2:
                    self.family = remaining[0]
                    self.platform = remaining[1]
                elif len(remaining) >= 1:
                    self.family = remaining[0]
                break

        # Page role
        if self.subdomain == "kb":
            name = self.filepath.stem.lower()
            if name == "_index":
                self.page_role = "kb_index"
            elif name == "faq" or name.startswith("faq"):
                self.page_role = "faq"
            else:
                self.page_role = "howto"
        elif self.subdomain == "reference":
            self.page_role = "reference"
        elif self.subdomain == "blog":
            self.page_role = "blog"
        elif self.subdomain == "docs":
            self.page_role = "docs"
        elif self.subdomain == "products":
            self.page_role = "products"


# ---------------------------------------------------------------------------
# EvalReport — aggregated evaluation results
# ---------------------------------------------------------------------------
@dataclass
class EvalReport:
    """Aggregated evaluation report."""

    findings: list[Finding] = field(default_factory=list)
    pages_evaluated: int = 0
    evaluators_run: list[str] = field(default_factory=list)
    scope: dict[str, Any] = field(default_factory=dict)

    @property
    def fails(self) -> list[Finding]:
        return [f for f in self.findings if f.level == "FAIL"]

    @property
    def warns(self) -> list[Finding]:
        return [f for f in self.findings if f.level == "WARN"]

    @property
    def infos(self) -> list[Finding]:
        return [f for f in self.findings if f.level == "INFO"]

    def by_file(self) -> dict[str, list[Finding]]:
        """Group findings by filepath."""
        grouped: dict[str, list[Finding]] = {}
        for f in self.findings:
            grouped.setdefault(f.filepath, []).append(f)
        return grouped

    def by_category(self) -> dict[str, list[Finding]]:
        """Group findings by category."""
        grouped: dict[str, list[Finding]] = {}
        for f in self.findings:
            grouped.setdefault(f.category, []).append(f)
        return grouped
