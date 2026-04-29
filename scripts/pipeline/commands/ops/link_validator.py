#!/usr/bin/env python3
"""link_validator.py — Validate cross-subdomain internal links in content files.

Finds all hyperlinks pointing to aspose.org subdomains, builds a slug index from
the local content directory, and reports BROKEN links (target slug not found).

Usage:
    python scripts/pipeline/commands/ops/link_validator.py {family} {platform}      # scan one product
    python scripts/pipeline/commands/ops/link_validator.py --files file1.md ...     # scan specific files
    python scripts/pipeline/commands/ops/link_validator.py all                       # scan all content
    python scripts/pipeline/commands/ops/link_validator.py --json {family} {platform}  # JSON output

Exit codes:
    0   No broken links
    1   One or more broken cross-subdomain links found
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[4]
_DEFAULT_CONTENT_ROOT = _DEFAULT_REPO_ROOT / "content"

REPO_ROOT = _DEFAULT_REPO_ROOT
CONTENT_ROOT = _DEFAULT_CONTENT_ROOT


def configure(
    *,
    repo_root: "Path | str | None" = None,
    content_root: "Path | str | None" = None,
) -> None:
    """Override module-level path constants for testing."""
    global REPO_ROOT, CONTENT_ROOT
    if repo_root is None and content_root is None:
        REPO_ROOT = _DEFAULT_REPO_ROOT
        CONTENT_ROOT = _DEFAULT_CONTENT_ROOT
        return
    if repo_root is not None:
        REPO_ROOT = Path(repo_root)
        CONTENT_ROOT = REPO_ROOT / "content"
    if content_root is not None:
        CONTENT_ROOT = Path(content_root)

# Aspose subdomain prefixes we know about
KNOWN_SUBDOMAINS = {
    "docs.aspose.org",
    "kb.aspose.org",
    "blog.aspose.org",
    "products.aspose.org",
    "reference.aspose.org",
}

# Pattern to find markdown links: [text](url) and bare <url>
_LINK_RE = re.compile(
    r'\[(?:[^\]]*)\]\((https?://(?:' + '|'.join(re.escape(s) for s in KNOWN_SUBDOMAINS) + r')[^)]*)\)'
    r'|<(https?://(?:' + '|'.join(re.escape(s) for s in KNOWN_SUBDOMAINS) + r')[^>]*)>',
    re.IGNORECASE,
)

# Extract subdomain + path from URL
_URL_PARSE_RE = re.compile(
    r'https?://([\w.-]+\.aspose\.org)(/?[^)>\s#?]*)',
    re.IGNORECASE,
)


@dataclass
class LinkFinding:
    level: str          # BROKEN or WARN
    source_file: str
    url: str
    subdomain: str
    slug: str
    message: str


def _build_slug_index() -> dict[str, set[str]]:
    """Build a mapping from subdomain to set of known relative paths (slugs)."""
    index: dict[str, set[str]] = {s: set() for s in KNOWN_SUBDOMAINS}

    # Phase 1: index all markdown files
    for md_file in CONTENT_ROOT.rglob("*.md"):
        rel = md_file.relative_to(CONTENT_ROOT).as_posix()
        # rel looks like: docs.aspose.org/en/cells/python/_index.md
        # → slug for docs.aspose.org: /en/cells/python/
        parts = rel.split("/", 1)
        if len(parts) != 2:
            continue
        subdomain, path = parts[0], parts[1]
        if subdomain not in KNOWN_SUBDOMAINS:
            continue
        # Strip _index.md or /index.md → parent path; strip .md → slug
        if path.endswith("/_index.md"):
            slug = "/" + path[:-len("/_index.md")] + "/"
        elif path.endswith("/index.md"):
            # Hugo leaf bundles: dir/index.md → deploys at /dir/
            slug = "/" + path[:-len("/index.md")] + "/"
        elif path.endswith(".md"):
            slug = "/" + path[:-3] + "/"
        else:
            continue
        # Hugo serves English content at root (no /en/ prefix), so strip it.
        # e.g. content/reference.aspose.org/en/slides/cpp/FillFormat/_index.md
        #      → slug /en/slides/cpp/FillFormat/ → deployed as /slides/cpp/FillFormat/
        if slug.lower().startswith("/en/"):
            slug = slug[3:]  # strip leading /en (keep the trailing /)
        index[subdomain].add(slug.lower())
        # Also add without trailing slash
        index[subdomain].add(slug.lower().rstrip("/"))

    # Phase 2: Hugo auto-generates section list pages for every non-empty directory,
    # even without a _index.md. Register all content subdirectories as valid slugs.
    for subdomain in KNOWN_SUBDOMAINS:
        subdir = CONTENT_ROOT / subdomain
        if not subdir.is_dir():
            continue
        for d in subdir.rglob("*"):
            if not d.is_dir():
                continue
            rel_dir = d.relative_to(subdir).as_posix()
            slug = "/" + rel_dir + "/"
            if slug.lower().startswith("/en/"):
                slug = slug[3:]
            index[subdomain].add(slug.lower())
            index[subdomain].add(slug.lower().rstrip("/"))

    return index


def extract_links(filepath: Path) -> list[tuple[str, str]]:
    """Return list of (url, subdomain) pairs found in the file."""
    text = filepath.read_text(encoding="utf-8", errors="ignore")
    urls = []
    for m in _LINK_RE.finditer(text):
        url = m.group(1) or m.group(2)
        if url:
            pm = _URL_PARSE_RE.match(url)
            if pm:
                urls.append((url, pm.group(1).lower(), pm.group(2)))
    return urls


def validate_files(files: list[Path], slug_index: dict[str, set[str]]) -> list[LinkFinding]:
    findings: list[LinkFinding] = []
    for filepath in files:
        for url, subdomain, path in extract_links(filepath):
            if subdomain not in KNOWN_SUBDOMAINS:
                continue
            # Normalize path: remove query strings and anchors
            clean_path = re.split(r"[?#]", path)[0].rstrip("/")
            if not clean_path:
                clean_path = "/"
            known_slugs = slug_index.get(subdomain, set())
            # Check exact match or with trailing slash
            if clean_path.lower() not in known_slugs and (clean_path.lower() + "/") not in known_slugs:
                findings.append(LinkFinding(
                    level="BROKEN",
                    source_file=str(filepath.relative_to(REPO_ROOT)),
                    url=url,
                    subdomain=subdomain,
                    slug=clean_path,
                    message=f"Link target not found in local content: {subdomain}{clean_path}",
                ))
    return findings


def discover_files(family: str, platform: str) -> list[Path]:
    """Find all English content files for the given product."""
    files = []
    for site_dir in CONTENT_ROOT.iterdir():
        if not site_dir.is_dir():
            continue
        en_dir = site_dir / "en" / family / platform
        if en_dir.exists():
            files.extend(en_dir.rglob("*.md"))
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate cross-subdomain links in content")
    parser.add_argument("target", nargs="?", help="family platform | all")
    parser.add_argument("platform", nargs="?", help="platform (when target is family)")
    parser.add_argument("--files", nargs="+", help="Specific files to check")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    # Collect target files
    if args.files:
        files = [(REPO_ROOT / f).resolve() if not Path(f).is_absolute() else Path(f).resolve()
                 for f in args.files if (REPO_ROOT / f).exists() or Path(f).exists()]
    elif args.target == "all":
        files = list(CONTENT_ROOT.rglob("*.md"))
    elif args.target and args.platform:
        files = discover_files(args.target, args.platform)
    else:
        parser.print_help()
        return 1

    if not files:
        print("No files to check.")
        return 0

    print(f"Building slug index...", file=sys.stderr)
    slug_index = _build_slug_index()
    total_slugs = sum(len(v) for v in slug_index.values())
    print(f"  Index: {total_slugs} slugs across {len(KNOWN_SUBDOMAINS)} subdomains", file=sys.stderr)

    print(f"Scanning {len(files)} file(s) for cross-subdomain links...", file=sys.stderr)
    findings = validate_files(files, slug_index)

    if args.json:
        output = {
            "files_scanned": len(files),
            "broken": len([f for f in findings if f.level == "BROKEN"]),
            "findings": [asdict(f) for f in findings],
        }
        print(json.dumps(output, indent=2))
    else:
        if not findings:
            print(f"Link validation: OK — no broken cross-subdomain links in {len(files)} file(s).")
        else:
            broken = [f for f in findings if f.level == "BROKEN"]
            print(f"Link validation: {len(broken)} BROKEN link(s) found\n")
            for f in findings:
                print(f"  [{f.level}] {f.source_file}")
                print(f"         URL: {f.url}")
                print(f"         {f.message}")
                print()

    broken_count = sum(1 for f in findings if f.level == "BROKEN")
    return 1 if broken_count > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
