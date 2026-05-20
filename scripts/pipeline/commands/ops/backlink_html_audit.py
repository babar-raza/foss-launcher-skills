#!/usr/bin/env python3
# Adapted from aspose.org
"""backlink_html_audit.py — Post-Hugo rendered HTML backlink validator (TC-BL-010).

Parses generated HTML files in a Hugo public/ output directory and validates that
qualifying aspose.com links are present in the main content area (not nav/header/footer).

For products pages specifically counts overview + CTA links per §Y:
  COMPLIANT_TWO_LINKS  — overview link (1) + CTA link (1) = 2
  COMPLIANT_ONE_LINK   — overview link only (family page or plugin without CTA)
  COMPLIANT_CTA_ONLY   — CTA exists, overview missing → flag for review
  OVER_LIMIT           — > 2 qualifying content-area links
  MISSING              — 0 qualifying links in content area

Usage:
    python scripts/pipeline/commands/ops/backlink_html_audit.py --public-dir public/
    python scripts/pipeline/commands/ops/backlink_html_audit.py --public-dir public/ --subdomain products.aspose.org
    python scripts/pipeline/commands/ops/backlink_html_audit.py --public-dir public/ --family words

Exit codes:
    0   Audit complete (report written)
    1   Fatal error (public dir not found, etc.)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
import os

_REPO_ROOT = Path(os.environ.get("FOSS_REPO_ROOT", str(Path(__file__).resolve().parents[4])))

SCRIPT_VERSION = "1.0.0"

# Regex to match qualifying aspose.com links (case-insensitive)
_ASPOSE_COM_RE = re.compile(
    r'https?://[a-z0-9-]+\.aspose\.com/[^\s"\'<>]*', re.IGNORECASE
)

# CSS classes / element patterns for excluded layout areas
_EXCLUDED_CLASSES = frozenset({
    "navbar", "nav", "footer", "header", "breadcrumb", "breadcrumbs",
    "sidebar", "aside", "menu", "site-header", "site-footer",
    "support-resources",  # globally-repeated about.aspose.com section (§D.3 / §Y)
})

# CSS classes for the products CTA section (counted separately, §R.4)
_CTA_SECTION_CLASSES = frozenset({
    "downloadbtn-section",
    "container-fluid downloadbtn-section",
})

# CSS classes for overview content area (plugin.html:30, family.html:19)
# Also includes article body classes for docs/kb/blog/reference themes
_OVERVIEW_CLASSES = frozenset({
    "mt-20",        # plugin.html:30 — plugin page overview div
    "mt-3",         # family.html:19 — family page overview paragraph
    "content",      # hextra docs/reference/kb article body div
    "post-content", # blog theme article body div
})

# HTML elements that are excluded by tag name regardless of class
_EXCLUDED_TAGS = frozenset({"nav", "footer", "header", "aside"})


@dataclass
class ContentAreaLink:
    href: str
    text: str
    in_overview: bool
    in_cta: bool


class BacklinkHTMLParser(HTMLParser):
    """Parse a rendered HTML page and extract content-area aspose.com links."""

    def __init__(self) -> None:
        super().__init__()
        self._stack: list[tuple[str, dict[str, str]]] = []   # (tag, attrs)
        self._depth_excluded: int = 0                         # depth of excluded sections
        self._depth_overview: int = 0
        self._depth_cta: int = 0
        self.links: list[ContentAreaLink] = []
        self._current_text: list[str] = []

    # ------------------------------------------------------------------
    # Helper: attr dict from HTMLParser list
    # ------------------------------------------------------------------
    @staticmethod
    def _attrs_dict(attrs: list) -> dict[str, str]:
        return {k.lower(): (v or "") for k, v in attrs}

    def _is_excluded(self, tag: str, attrs: dict[str, str]) -> bool:
        if tag in _EXCLUDED_TAGS:
            return True
        cls = attrs.get("class", "")
        # Use word-boundary matching: split class into tokens and check exact membership.
        # Substring matching would match Tailwind calc() vars like var(--navbar-height).
        cls_tokens = set(cls.split())
        for excl in _EXCLUDED_CLASSES:
            if excl in cls_tokens:
                return True
        return False

    def _is_overview(self, tag: str, attrs: dict[str, str]) -> bool:
        cls = attrs.get("class", "")
        # Use word-boundary matching: split class into tokens and check exact membership.
        # Substring matching would match Tailwind utilities like "before:hx-content-['']".
        cls_tokens = set(cls.split())
        for ov in _OVERVIEW_CLASSES:
            if ov in cls_tokens:
                return True
        return False

    def _is_cta(self, tag: str, attrs: dict[str, str]) -> bool:
        cls = attrs.get("class", "")
        for cta in _CTA_SECTION_CLASSES:
            if cta in cls:
                return True
        return False

    def handle_starttag(self, tag: str, attrs: list) -> None:
        ad = self._attrs_dict(attrs)
        self._stack.append((tag, ad))

        if self._is_excluded(tag, ad):
            self._depth_excluded += 1
        if self._is_overview(tag, ad):
            self._depth_overview += 1
        if self._is_cta(tag, ad):
            self._depth_cta += 1

        # Capture anchor links to aspose.com
        if tag == "a":
            href = ad.get("href", "")
            if _ASPOSE_COM_RE.match(href):
                in_overview = self._depth_overview > 0 and self._depth_excluded == 0
                in_cta = self._depth_cta > 0 and self._depth_excluded == 0
                in_content = self._depth_excluded == 0
                if in_content:
                    self.links.append(ContentAreaLink(
                        href=href,
                        text="",
                        in_overview=in_overview,
                        in_cta=in_cta,
                    ))

    def handle_endtag(self, tag: str) -> None:
        # Walk stack to find the matching open tag
        if not self._stack:
            return
        # Pop the most recent matching open tag
        for i in range(len(self._stack) - 1, -1, -1):
            if self._stack[i][0] == tag:
                popped_tag, popped_attrs = self._stack.pop(i)
                if self._is_excluded(popped_tag, popped_attrs):
                    self._depth_excluded = max(0, self._depth_excluded - 1)
                if self._is_overview(popped_tag, popped_attrs):
                    self._depth_overview = max(0, self._depth_overview - 1)
                if self._is_cta(popped_tag, popped_attrs):
                    self._depth_cta = max(0, self._depth_cta - 1)
                break

    def handle_data(self, data: str) -> None:
        if self.links and not self.links[-1].text:
            # Attach text to the last link if it's an anchor child
            pass  # text accumulation not critical for counting


def parse_html_page(html_path: Path) -> list[ContentAreaLink]:
    """Parse an HTML file and return content-area aspose.com links."""
    try:
        content = html_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise RuntimeError(f"Cannot read {html_path}: {exc}") from exc

    parser = BacklinkHTMLParser()
    parser.feed(content)
    return parser.links


@dataclass
class HTMLAuditRecord:
    file: str                      # path relative to public_dir
    total_content_links: int
    overview_links: int
    cta_links: int
    link_urls: list[str]
    classification: str            # COMPLIANT_TWO_LINKS / COMPLIANT_ONE_LINK / etc.
    warning_messages: list[str] = field(default_factory=list)


def classify_html_record(
    overview_links: int,
    cta_links: int,
    total: int,
) -> str:
    """Classify products page rendered HTML per §Y."""
    if total > 2:
        return "OVER_LIMIT"
    if overview_links >= 1 and cta_links >= 1:
        return "COMPLIANT_TWO_LINKS"
    if overview_links >= 1 and cta_links == 0:
        return "COMPLIANT_ONE_LINK"
    if overview_links == 0 and cta_links >= 1:
        return "COMPLIANT_CTA_ONLY"   # plan deviation — flag
    return "MISSING"


def audit_html_file(html_path: Path, public_dir: Path) -> HTMLAuditRecord:
    """Audit a single rendered HTML file."""
    rel = html_path.relative_to(public_dir).as_posix()
    warnings: list[str] = []

    try:
        links = parse_html_page(html_path)
    except RuntimeError as exc:
        warnings.append(str(exc))
        return HTMLAuditRecord(
            file=rel, total_content_links=0, overview_links=0, cta_links=0,
            link_urls=[], classification="ERROR", warning_messages=warnings,
        )

    # All content-area links (excluded sections already filtered by parser)
    total = len(links)
    overview_count = sum(1 for lnk in links if lnk.in_overview)
    cta_count = sum(1 for lnk in links if lnk.in_cta)
    link_urls = [lnk.href for lnk in links]

    classification = classify_html_record(overview_count, cta_count, total)

    return HTMLAuditRecord(
        file=rel, total_content_links=total, overview_links=overview_count,
        cta_links=cta_count, link_urls=link_urls, classification=classification,
        warning_messages=warnings,
    )


@dataclass
class HTMLAuditTotals:
    scanned: int = 0
    compliant_two_links: int = 0
    compliant_one_link: int = 0
    compliant_cta_only: int = 0
    over_limit: int = 0
    missing: int = 0
    errors: int = 0


# 2-letter locale codes used by Hugo for products.aspose.org multi-language output
_LOCALE_CODES: frozenset[str] = frozenset({
    "ar", "bg", "ca", "cs", "da", "de", "el", "es", "fa", "fi", "fr", "he",
    "hi", "hr", "hu", "id", "it", "ja", "ko", "lt", "lv", "ms", "nl", "no",
    "pl", "pt", "ro", "ru", "sk", "sr", "sv", "th", "tr", "uk", "vi", "zh",
})


def run_html_audit(
    public_dir: Path,
    subdomain_filter: str | None = None,
    family_filter: str | None = None,
    english_only: bool = False,
) -> tuple[list[HTMLAuditRecord], HTMLAuditTotals]:
    """Walk public/ HTML files and audit each one."""
    if not public_dir.exists():
        raise FileNotFoundError(f"Public dir not found: {public_dir}")

    # Collect HTML files
    html_files: list[Path] = []
    search_root = public_dir
    if subdomain_filter:
        # Hugo may output per-subdomain in subdirs or root; adapt as needed
        sub_dir = public_dir / subdomain_filter
        if sub_dir.exists():
            search_root = sub_dir

    for f in sorted(search_root.rglob("index.html")):
        rel_parts = f.relative_to(search_root).parts
        # Filter locale-prefixed paths (e.g., ar/words/python/index.html)
        # Also filter subdirectory locale paths (e.g., products-pilot/ar/3d/index.html)
        if english_only and any(p in _LOCALE_CODES for p in rel_parts):
            continue
        if family_filter:
            if not any(p == family_filter for p in rel_parts):
                continue
        html_files.append(f)

    print(f"  Scanning {len(html_files)} HTML files in {public_dir}...", file=sys.stderr)

    records: list[HTMLAuditRecord] = []
    totals = HTMLAuditTotals(scanned=len(html_files))

    for fpath in html_files:
        rec = audit_html_file(fpath, public_dir)
        records.append(rec)
        c = rec.classification
        if c == "COMPLIANT_TWO_LINKS": totals.compliant_two_links += 1
        elif c == "COMPLIANT_ONE_LINK": totals.compliant_one_link += 1
        elif c == "COMPLIANT_CTA_ONLY": totals.compliant_cta_only += 1
        elif c == "OVER_LIMIT":         totals.over_limit += 1
        elif c == "MISSING":            totals.missing += 1
        elif c == "ERROR":              totals.errors += 1

    return records, totals


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rendered HTML backlink validator for Hugo-built aspose.org pages."
    )
    parser.add_argument(
        "--public-dir", required=True,
        help="Path to Hugo public/ output directory",
    )
    parser.add_argument("--subdomain", help="Restrict to a specific subdomain subdir")
    parser.add_argument("--family", help="Restrict to a specific family")
    parser.add_argument(
        "--output",
        help="Output JSON path (default: reports/backlinks/backlink_html_audit_{ts}.json)",
    )
    parser.add_argument(
        "--show-compliant", action="store_true",
        help="Show COMPLIANT records in console output",
    )
    parser.add_argument(
        "--english-only", action="store_true",
        help="Skip locale-prefixed output paths (ar/, zh/, etc.) — audit English pages only",
    )
    args = parser.parse_args()

    public_dir = Path(args.public_dir)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")

    reports_dir = _REPO_ROOT / "reports" / "backlinks"
    reports_dir.mkdir(parents=True, exist_ok=True)

    json_out = Path(args.output) if args.output else reports_dir / f"backlink_html_audit_{ts}.json"
    md_out = json_out.with_suffix(".md")

    print(f"Running HTML backlink audit (generator v{SCRIPT_VERSION})...", file=sys.stderr)

    try:
        records, totals = run_html_audit(
            public_dir=public_dir,
            subdomain_filter=args.subdomain,
            family_filter=args.family,
            english_only=args.english_only,
        )
    except FileNotFoundError as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        return 1

    # Build report
    report = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generator": f"backlink_html_audit.py v{SCRIPT_VERSION}",
        "public_dir": str(public_dir),
        "totals": asdict(totals),
        "records": [asdict(r) for r in records],
        "non_compliant": [
            asdict(r) for r in records
            if r.classification in ("OVER_LIMIT", "MISSING", "COMPLIANT_CTA_ONLY", "ERROR")
        ],
    }

    json_out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    # Markdown summary
    t = totals
    md_lines = [
        "# Backlink HTML Audit Summary",
        "",
        f"**Generated:** {report['generated_at']}",
        f"**Public dir:** `{public_dir}`",
        "",
        "## Totals",
        "",
        "| Classification | Count |",
        "|---------------|-------|",
        f"| Scanned | {t.scanned} |",
        f"| COMPLIANT_TWO_LINKS | {t.compliant_two_links} |",
        f"| COMPLIANT_ONE_LINK | {t.compliant_one_link} |",
        f"| COMPLIANT_CTA_ONLY (flag) | {t.compliant_cta_only} |",
        f"| OVER_LIMIT | {t.over_limit} |",
        f"| MISSING | {t.missing} |",
        f"| Errors | {t.errors} |",
        "",
    ]
    if report["non_compliant"]:
        md_lines += ["## Non-Compliant Pages", ""]
        for r in report["non_compliant"]:
            md_lines.append(f"- `{r['file']}` — {r['classification']}")
        md_lines.append("")
    md_out.write_text("\n".join(md_lines), encoding="utf-8")

    # Console output
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"HTML Backlink Audit Complete", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)
    print(f"  Scanned:              {t.scanned}", file=sys.stderr)
    print(f"  COMPLIANT_TWO_LINKS:  {t.compliant_two_links}", file=sys.stderr)
    print(f"  COMPLIANT_ONE_LINK:   {t.compliant_one_link}", file=sys.stderr)
    print(f"  COMPLIANT_CTA_ONLY:   {t.compliant_cta_only}", file=sys.stderr)
    print(f"  OVER_LIMIT:           {t.over_limit}", file=sys.stderr)
    print(f"  MISSING:              {t.missing}", file=sys.stderr)
    print(f"  Errors:               {t.errors}", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)
    print(f"  JSON: {json_out}", file=sys.stderr)
    print(f"  MD:   {md_out}", file=sys.stderr)

    for rec in records:
        if rec.classification in ("OVER_LIMIT", "MISSING", "COMPLIANT_CTA_ONLY", "ERROR"):
            print(f"  [{rec.classification}] {rec.file}", file=sys.stderr)
        elif args.show_compliant and rec.classification.startswith("COMPLIANT"):
            print(f"  [{rec.classification}] {rec.file}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
