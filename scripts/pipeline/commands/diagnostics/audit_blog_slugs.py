#!/usr/bin/env python3
"""audit_blog_slugs.py — SEO slug audit with AI-proposed replacements.

Scans every blog post in content/blog.aspose.org, classifies each slug by
SEO quality pattern, and optionally calls the LLM to propose better slugs
for posts with mechanical/generic slugs.

Usage:
    # Dry-run audit (no LLM, pattern-based classification only):
    python scripts/pipeline/commands/diagnostics/audit_blog_slugs.py

    # With AI slug proposals:
    python scripts/pipeline/commands/diagnostics/audit_blog_slugs.py --ai

    # Filter by severity:
    python scripts/pipeline/commands/diagnostics/audit_blog_slugs.py --ai --severity introducing,key-features

    # Filter by family/platform:
    python scripts/pipeline/commands/diagnostics/audit_blog_slugs.py --ai --family cells --platform python

    # Show worst N only:
    python scripts/pipeline/commands/diagnostics/audit_blog_slugs.py --ai --top 10
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

_HERE = Path(__file__).resolve()
_REPO_ROOT = _HERE.parents[4]
sys.path.insert(0, str(_REPO_ROOT / "scripts" / "pipeline"))

import yaml  # noqa: E402
from lib.blog_slug_policy import (  # noqa: E402
    generate_seo_slug,
    validate_seo_slug,
)

# ---------------------------------------------------------------------------
# SEO pattern classification (separate from identity-based classifier)
# ---------------------------------------------------------------------------

_INTRODUCING_RE = re.compile(r"^introducing-")
_KEY_FEATURES_RE = re.compile(r"key-features|^cells-foss-java$")
_WORKING_WITH_RE = re.compile(r"^working-with-")
_GENERIC_TOPIC_RE = re.compile(r"^[a-z]+-(?:in|management-in)-[a-z]+$")


def classify_seo_pattern(slug: str) -> str:
    """Classify a slug's SEO pattern. Returns category string."""
    if _INTRODUCING_RE.search(slug):
        return "introducing"
    if _KEY_FEATURES_RE.search(slug):
        return "key-features"
    if _WORKING_WITH_RE.search(slug):
        return "working-with"
    if _GENERIC_TOPIC_RE.match(slug):
        return "generic-topic"
    return "good"


# SEO pattern severity order (worst first)
_SEO_SEVERITY = {
    "introducing": 0,
    "key-features": 1,
    "working-with": 2,
    "generic-topic": 3,
    "good": 4,
}


# ---------------------------------------------------------------------------
# Blog post scanning
# ---------------------------------------------------------------------------

_FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", re.DOTALL)


@dataclass
class BlogPost:
    family: str
    platform: str
    slug: str
    title: str
    description: str
    summary: str
    seo_pattern: str
    auto_updatable: bool = True
    proposed_slug: str = ""
    seo_violations: list[str] = field(default_factory=list)


def scan_blog_posts(content_root: Path) -> list[BlogPost]:
    """Scan all blog posts and classify their slugs."""
    blog_root = content_root / "blog.aspose.org"
    if not blog_root.is_dir():
        print(f"ERROR: {blog_root} not found", file=sys.stderr)
        return []

    posts: list[BlogPost] = []
    for idx in sorted(blog_root.rglob("index.md")):
        if idx.name == "_index.md":
            continue
        parts = idx.relative_to(blog_root).parts
        if len(parts) < 3:
            continue
        family, platform, slug = parts[0], parts[1], parts[2]

        text = idx.read_text(encoding="utf-8", errors="replace")
        m = _FM_RE.match(text)
        if not m:
            continue
        try:
            fm = yaml.safe_load(m.group(1)) or {}
        except yaml.YAMLError:
            continue

        prov = fm.get("provenance") or {}
        au = prov.get("auto_updatable", True)

        posts.append(BlogPost(
            family=family,
            platform=platform,
            slug=slug,
            title=fm.get("title", ""),
            description=fm.get("description", "") or "",
            summary=fm.get("summary", "") or "",
            seo_pattern=classify_seo_pattern(slug),
            auto_updatable=au is not False,
        ))

    return posts


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_report(
    posts: list[BlogPost],
    *,
    severity_filter: set[str] | None = None,
    family_filter: str | None = None,
    platform_filter: str | None = None,
    top_n: int | None = None,
) -> str:
    """Generate a formatted audit report."""
    # Filter
    filtered = posts
    if severity_filter:
        filtered = [p for p in filtered if p.seo_pattern in severity_filter]
    if family_filter:
        filtered = [p for p in filtered if p.family == family_filter]
    if platform_filter:
        filtered = [p for p in filtered if p.platform == platform_filter]

    # Sort by severity (worst first), then family/platform
    filtered.sort(key=lambda p: (
        _SEO_SEVERITY.get(p.seo_pattern, 99), p.family, p.platform, p.slug
    ))

    if top_n:
        filtered = filtered[:top_n]

    # Build report
    lines = [
        "BLOG SLUG SEO AUDIT",
        "=" * 60,
        "",
        f"Total posts scanned: {len(posts)}",
        f"Posts shown: {len(filtered)}",
        "",
    ]

    # Summary by category
    from collections import Counter
    cat_counts = Counter(p.seo_pattern for p in posts)
    lines.append("Category breakdown (all posts):")
    for cat in sorted(cat_counts, key=lambda c: _SEO_SEVERITY.get(c, 99)):
        lines.append(f"  {cat:20s} {cat_counts[cat]:3d}")
    lines.append("")

    # Detail table
    lines.append(f"{'Pattern':15s} | {'Family/Plat':16s} | {'Current Slug':50s} | {'Proposed Slug':40s} | Title")
    lines.append("-" * 160)

    for p in filtered:
        if not p.auto_updatable:
            proposed = "[LOCKED]"
        elif p.proposed_slug:
            proposed = p.proposed_slug
        elif p.seo_pattern == "good":
            proposed = "(no change)"
        else:
            proposed = "(run with --ai)"
        title_trunc = p.title[:60] + "..." if len(p.title) > 60 else p.title
        lines.append(
            f"{p.seo_pattern:15s} | {p.family}/{p.platform:10s} | {p.slug:50s} | {proposed:40s} | {title_trunc}"
        )

    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="SEO slug audit for blog posts")
    parser.add_argument("--root", default=str(_REPO_ROOT / "content"),
                        help="Content root directory")
    parser.add_argument("--ai", action="store_true",
                        help="Use LLM to propose replacement slugs")
    parser.add_argument("--severity", default=None,
                        help="Comma-separated severity filter: introducing,key-features,working-with,generic-topic,good")
    parser.add_argument("--family", default=None, help="Filter by family")
    parser.add_argument("--platform", default=None, help="Filter by platform")
    parser.add_argument("--top", type=int, default=None, help="Show only top N worst slugs")
    args = parser.parse_args()

    content_root = Path(args.root)
    posts = scan_blog_posts(content_root)
    if not posts:
        print("No blog posts found.", file=sys.stderr)
        return 1

    # Optionally generate AI slug proposals
    if args.ai:
        router = None
        try:
            from commands.ops.llm_router import LLMRouter
            router = LLMRouter()
        except Exception as exc:
            print(f"WARNING: LLM router unavailable ({exc}), skipping AI proposals",
                  file=sys.stderr)

        need_proposal = [p for p in posts if p.seo_pattern != "good" and p.auto_updatable]
        for i, p in enumerate(need_proposal, 1):
            print(f"  [{i}/{len(need_proposal)}] Generating slug for {p.family}/{p.platform}/{p.slug}...",
                  file=sys.stderr)
            p.proposed_slug = generate_seo_slug(
                title=p.title,
                description=p.description,
                summary=p.summary,
                family=p.family,
                platform=p.platform,
                llm_router=router,
            )
            p.seo_violations = validate_seo_slug(p.proposed_slug)

    severity_filter = set(args.severity.split(",")) if args.severity else None

    report = generate_report(
        posts,
        severity_filter=severity_filter,
        family_filter=args.family,
        platform_filter=args.platform,
        top_n=args.top,
    )
    print(report)

    # Summary: how many need change
    changeable = [p for p in posts if p.seo_pattern != "good"]
    print(f"\nSlugs needing improvement: {len(changeable)}/{len(posts)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
