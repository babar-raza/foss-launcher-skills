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


def validate_files(
    files: list[Path],
    slug_index: dict[str, set[str]],
    anchor_index: "dict[str, set[str]] | None" = None,
) -> list[LinkFinding]:
    findings: list[LinkFinding] = []
    for filepath in files:
        for url, subdomain, path in extract_links(filepath):
            if subdomain not in KNOWN_SUBDOMAINS:
                continue
            # Strip query/fragment from path for slug lookup
            clean_path = re.split(r"[?#]", path)[0].rstrip("/")
            # Extract anchor fragment from the full URL (path already strips it via _URL_PARSE_RE)
            fragment = url.split("#", 1)[1].split("?")[0] if "#" in url else ""
            if not clean_path:
                clean_path = "/"
            known_slugs = slug_index.get(subdomain, set())
            slug_found = (
                clean_path.lower() in known_slugs
                or (clean_path.lower() + "/") in known_slugs
            )
            if not slug_found:
                findings.append(LinkFinding(
                    level="BROKEN",
                    source_file=str(filepath.relative_to(REPO_ROOT)),
                    url=url,
                    subdomain=subdomain,
                    slug=clean_path,
                    message=f"Link target not found in local content: {subdomain}{clean_path}",
                ))
            elif fragment and anchor_index is not None:
                # Slug exists — validate anchor fragment (non-blocking WARN)
                slug_key = f"{subdomain}:{clean_path.lower()}/"
                known_anchors = anchor_index.get(slug_key, set())
                if known_anchors and _heading_to_anchor(fragment) not in known_anchors:
                    findings.append(LinkFinding(
                        level="WARN",
                        source_file=str(filepath.relative_to(REPO_ROOT)),
                        url=url,
                        subdomain=subdomain,
                        slug=clean_path,
                        message=f"Anchor '#{fragment}' not found in headings of {subdomain}{clean_path}",
                    ))
    return findings


def _heading_to_anchor(text: str) -> str:
    """Convert heading text to a Hugo anchor ID.

    Hugo lowercases, replaces whitespace runs with '-', and drops characters
    that are not alphanumeric, '-', or '_'.
    """
    anchor = text.strip().lower()
    anchor = re.sub(r"[^\w\s-]", "", anchor)
    anchor = re.sub(r"\s+", "-", anchor)
    return anchor.strip("-")


def _build_anchor_index() -> "dict[str, set[str]]":
    """Return a mapping from '{subdomain}:{slug}' to set of heading anchor IDs.

    Only called when anchor validation is enabled (--check-anchors).
    """
    index: dict[str, set[str]] = {}
    _HEADING_RE = re.compile(r"^#{1,6}\s+(.*)", re.MULTILINE)

    for md_file in CONTENT_ROOT.rglob("*.md"):
        rel = md_file.relative_to(CONTENT_ROOT).as_posix()
        parts = rel.split("/", 1)
        if len(parts) != 2:
            continue
        subdomain, path = parts
        if subdomain not in KNOWN_SUBDOMAINS:
            continue
        if path.endswith("/_index.md"):
            slug = "/" + path[: -len("/_index.md")] + "/"
        elif path.endswith("/index.md"):
            slug = "/" + path[: -len("/index.md")] + "/"
        elif path.endswith(".md"):
            slug = "/" + path[:-3] + "/"
        else:
            continue
        if slug.lower().startswith("/en/"):
            slug = slug[3:]
        key = f"{subdomain}:{slug.lower()}"
        try:
            text = md_file.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        anchors = {_heading_to_anchor(m.group(1)) for m in _HEADING_RE.finditer(text)}
        if anchors:
            index.setdefault(key, set()).update(anchors)
    return index


# Locale code pattern: 2-char or 2+2-char (e.g., ar, zh, zh-cn)
_LOCALE_RE = re.compile(r"^[a-z]{2}(?:-[a-z]{2})?$", re.I)


def discover_files(
    family: str,
    platform: str,
    *,
    include_locales: bool = False,
) -> list[Path]:
    """Find content files for the given product.

    Always includes English files from sites with an /en/ prefix tree.
    When ``include_locales=True``, also includes:

    - Locale subdirectory structure: ``{site}/{locale}/{family}/{platform}/``
      (e.g., ``docs.aspose.org/ar/cells/python/``)
    - Inline locale variants co-located with non-en English files: any
      ``*.{locale}.md`` file under ``{site}/{family}/{platform}/``
      (e.g., ``blog.aspose.org/3d/java/post/index.ar.md``)
    """
    seen: set[Path] = set()
    files: list[Path] = []

    def _add(p: Path) -> None:
        if p not in seen:
            seen.add(p)
            files.append(p)

    for site_dir in CONTENT_ROOT.iterdir():
        if not site_dir.is_dir():
            continue

        # English files under /en/ prefix (docs, kb, reference, products)
        en_dir = site_dir / "en" / family / platform
        if en_dir.exists():
            for p in en_dir.rglob("*.md"):
                _add(p)

        if not include_locales:
            continue

        # Locale subdirectory structure: {site}/{locale}/{family}/{platform}/
        for child in site_dir.iterdir():
            if not child.is_dir() or child.name.lower() == "en":
                continue
            if not _LOCALE_RE.match(child.name):
                continue
            locale_target = child / family / platform
            if locale_target.exists():
                for p in locale_target.rglob("*.md"):
                    _add(p)

        # Inline locale variants co-located with non-en English files
        # (blog.aspose.org/{family}/{platform}/{post}/index.ar.md)
        direct_dir = site_dir / family / platform
        if direct_dir.exists():
            for p in direct_dir.rglob("*"):
                if p.is_file() and re.match(
                    r"^.+\.([a-z]{2}|[a-z]{2}-[a-z]{2})\.md$", p.name, re.I
                ):
                    _add(p)

    return files


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate cross-subdomain links in content")
    parser.add_argument("target", nargs="?", help="family platform | all")
    parser.add_argument("platform", nargs="?", help="platform (when target is family)")
    parser.add_argument("--files", nargs="+", help="Specific files to check")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument(
        "--include-locales",
        action="store_true",
        default=False,
        help="Also scan locale variant files (index.ar.md, locale subdirs, etc.)",
    )
    parser.add_argument(
        "--check-anchors",
        action="store_true",
        default=False,
        help="Emit WARN when a link's #fragment anchor does not match a known heading",
    )
    args = parser.parse_args()

    # Collect target files
    if args.files:
        files = [(REPO_ROOT / f).resolve() if not Path(f).is_absolute() else Path(f).resolve()
                 for f in args.files if (REPO_ROOT / f).exists() or Path(f).exists()]
    elif args.target == "all":
        files = list(CONTENT_ROOT.rglob("*.md"))
    elif args.target and args.platform:
        files = discover_files(args.target, args.platform, include_locales=args.include_locales)
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

    anchor_index = None
    if args.check_anchors:
        print("Building anchor index...", file=sys.stderr)
        anchor_index = _build_anchor_index()
        total_anchors = sum(len(v) for v in anchor_index.values())
        print(f"  Anchors: {total_anchors} headings across {len(anchor_index)} pages", file=sys.stderr)

    print(f"Scanning {len(files)} file(s) for cross-subdomain links...", file=sys.stderr)
    findings = validate_files(files, slug_index, anchor_index=anchor_index)

    broken = [f for f in findings if f.level == "BROKEN"]
    warns = [f for f in findings if f.level == "WARN"]

    if args.json:
        output = {
            "files_scanned": len(files),
            "broken": len(broken),
            "warnings": len(warns),
            "findings": [asdict(f) for f in findings],
        }
        print(json.dumps(output, indent=2))
    else:
        if not findings:
            print(f"Link validation: OK — no broken cross-subdomain links in {len(files)} file(s).")
        else:
            if broken:
                print(f"Link validation: {len(broken)} BROKEN link(s) found\n")
            if warns:
                print(f"Link validation: {len(warns)} WARN anchor(s)\n")
            for f in findings:
                print(f"  [{f.level}] {f.source_file}")
                print(f"         URL: {f.url}")
                print(f"         {f.message}")
                print()

    return 1 if len(broken) > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
