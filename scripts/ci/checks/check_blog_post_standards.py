#!/usr/bin/env python3
"""Blog post standards quality gate.

Checks blog.aspose.org post frontmatter for production defect patterns:

  C1 — Tags must be empty
    Non-empty tags: array causes frontend tag leakage via Hugo theme.

  C2 — Category format
    categories must be present and contain the canonical taxonomy_term
    from data/blog_family_routes.yaml (e.g., "Aspose.PDF").

  C3 — Enterprise product link present
    Post body must contain a products.aspose.com/ link (in any section).
    The link may appear in prose, Related Resources, or any other section.
    Only one instance is required — duplicates should be avoided.

  C4 — No type: post [WARNING only, exit 0]
    type: post is an old S-57 template artifact. Does not block commit.

  C5 — Platform target registered
    family/platform must appear in products.aspose.com.platforms in
    data/aspose_com_targets.json.

  C6 — Getting Started section present
    Post body must contain ## Getting Started with at least one link to
    docs.aspose.org, kb.aspose.org, or reference.aspose.org. This section
    provides platform cross-links and is required on all live blog posts.

Scope:
    Files matching content/blog.aspose.org/{family}/{platform}/{slug}/index.md
    (5 path segments after content root). Excludes _index.md section pages.

Usage — staged-file mode (pre-commit):
    check_blog_post_standards.py FILE [FILE ...]
    Exit 1 if any FAIL; exit 0 otherwise.

Usage — scan mode (CI/reporting):
    check_blog_post_standards.py --scan [--root content]
    Scans all blog posts and prints findings. Exit 1 if any FAIL found.

Exit codes:
    0 — all pass (or warnings only)
    1 — at least one FAIL
    2 — configuration error
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import NamedTuple

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Repo root discovery
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------

def _load_family_routes() -> dict[str, str]:
    """Return {family_slug: taxonomy_term} from data/blog_family_routes.yaml."""
    path = _REPO_ROOT / "data" / "blog_family_routes.yaml"
    if yaml is None:
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return {
            slug: info["taxonomy_term"]
            for slug, info in data.get("families", {}).items()
        }
    except (OSError, KeyError, TypeError):
        return {}


def _load_registered_platforms() -> set[str]:
    """Return set of 'family/platform' keys from data/aspose_com_targets.json."""
    path = _REPO_ROOT / "data" / "aspose_com_targets.json"
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        platforms = (
            data.get("targets", {})
            .get("products.aspose.com", {})
            .get("platforms", {})
        )
        return set(platforms.keys())
    except (OSError, json.JSONDecodeError, AttributeError):
        return set()


def _load_registered_families() -> set[str]:
    """Return set of family keys with a verified family-level target in
    data/aspose_com_targets.json.

    Found live 2026-08-29 (pdf/typescript blog-post qualification, mission
    MT040): C5 below previously required an EXACT family/platform match,
    with no awareness of the family-level fallback
    lib/backlink_targets.py's own resolution algorithm already implements
    (_lookup_family()/resolve_best_verified_ancestor() -- a brand-new
    platform correctly falls back to its family's verified target, e.g.
    3d/typescript and now pdf/typescript both resolve to
    https://products.aspose.com/pdf/ with no commercial per-platform page
    existing to fabricate). C5 was blocking every first-launch blog post
    on a brand-new platform for a "gap" the real backlink-injection
    mechanism never had -- this closes that inconsistency by teaching C5
    the same fallback, not by exempting new platforms from the check.
    """
    path = _REPO_ROOT / "data" / "aspose_com_targets.json"
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        families = (
            data.get("targets", {})
            .get("products.aspose.com", {})
            .get("families", {})
        )
        return set(families.keys())
    except (OSError, json.JSONDecodeError, AttributeError):
        return set()


# ---------------------------------------------------------------------------
# Frontmatter parser
# ---------------------------------------------------------------------------

def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Return (frontmatter_dict, body_text). frontmatter_dict is empty on failure."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    fm_text = text[3:end].strip()
    body = text[end + 4:].lstrip("\n")
    if yaml is None:
        return {}, body
    try:
        fm = yaml.safe_load(fm_text) or {}
    except Exception:  # noqa: BLE001
        fm = {}
    return fm if isinstance(fm, dict) else {}, body


# ---------------------------------------------------------------------------
# Check helpers
# ---------------------------------------------------------------------------

class Finding(NamedTuple):
    check: str      # C1 / C2 / C3 / C4 / C5
    level: str      # FAIL / WARN
    message: str


def _check_post(
    path: Path,
    family: str,
    platform: str,
    family_routes: dict[str, str],
    registered_platforms: set[str],
    registered_families: set[str] = frozenset(),
) -> list[Finding]:
    findings: list[Finding] = []

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        findings.append(Finding("C0", "FAIL", f"Cannot read file: {exc}"))
        return findings

    fm, body = _parse_frontmatter(text)

    # Skip draft posts — not published, defects don't affect live site
    if fm.get("draft") is True:
        return findings

    # C1 — Tags must be empty
    tags = fm.get("tags")
    if tags is not None and tags != [] and tags != "":
        findings.append(Finding(
            "C1", "FAIL",
            f"tags is non-empty: {tags!r} — causes frontend tag leakage. Set tags: []",
        ))

    # C2 — Category format
    taxonomy_term = family_routes.get(family)
    categories = fm.get("categories")
    if taxonomy_term is None:
        if family:
            findings.append(Finding(
                "C2", "WARN",
                f"family '{family}' not found in blog_family_routes.yaml "
                f"— cannot verify categories",
            ))
    elif not categories or not isinstance(categories, list) or taxonomy_term not in categories:
        findings.append(Finding(
            "C2", "FAIL",
            f"categories must include {taxonomy_term!r} "
            f"(got {categories!r}). Fix: categories:\\n- {taxonomy_term}",
        ))

    # C3 — Enterprise product link anywhere in body
    has_enterprise_link = "products.aspose.com/" in body
    if not has_enterprise_link:
        findings.append(Finding(
            "C3", "FAIL",
            "Missing products.aspose.com/ link in post body. "
            "Add an enterprise product link in any section (prose or Related Resources).",
        ))

    # C6 — Getting Started section with aspose.org platform links
    has_getting_started = bool(re.search(
        r"##\s+Getting\s+Started\b[^\n]*\n(?:[^\n]*\n)*?[^\n]*(docs|kb|reference)\.aspose\.org/",
        body,
        re.IGNORECASE,
    ))
    if not has_getting_started:
        findings.append(Finding(
            "C6", "FAIL",
            "Missing '## Getting Started' section with docs/kb/reference.aspose.org links. "
            "Add the section before ## Related Resources.",
        ))

    # C4 — No type: post (warning only)
    if fm.get("type") == "post":
        findings.append(Finding(
            "C4", "WARN",
            "type: post is an old S-57 template artifact. Remove the type: field.",
        ))

    # C5 — Platform target registered in JSON, or a family-level fallback
    # exists (mirrors lib/backlink_targets.py's own ancestor-fallback
    # resolution -- see _load_registered_families()'s docstring).
    platform_key = f"{family}/{platform}"
    has_platform_target = platform_key in registered_platforms
    has_family_fallback = family in registered_families
    if registered_platforms and not has_platform_target and not has_family_fallback:
        findings.append(Finding(
            "C5", "FAIL",
            f"'{platform_key}' not found in data/aspose_com_targets.json "
            f"(products.aspose.com.platforms), and family '{family}' has no "
            f"family-level fallback target either. "
            "Run fetch_aspose_com_targets.py after deploying products site.",
        ))

    return findings


# ---------------------------------------------------------------------------
# Path extraction
# ---------------------------------------------------------------------------

_BLOG_POST_RE = re.compile(
    r"[/\\]blog\.aspose\.org[/\\]([^/\\]+)[/\\]([^/\\]+)[/\\][^/\\]+[/\\]index\.md$"
)


def _is_blog_post(path: str | Path) -> bool:
    """True for content/blog.aspose.org/{family}/{platform}/{slug}/index.md."""
    return bool(_BLOG_POST_RE.search(str(path)))


def _extract_family_platform(path: str | Path) -> tuple[str, str]:
    """Return (family, platform) from a blog post path."""
    m = _BLOG_POST_RE.search(str(path))
    if m:
        return m.group(1), m.group(2)
    return "", ""


# ---------------------------------------------------------------------------
# Modes
# ---------------------------------------------------------------------------

def check_files(
    paths: list[str],
    family_routes: dict[str, str],
    registered_platforms: set[str],
    registered_families: set[str] = frozenset(),
) -> int:
    """Staged-file mode: check given paths. Return 1 if any FAIL, 0 otherwise."""
    fail_count = 0
    warn_count = 0

    for p in paths:
        if not _is_blog_post(p):
            continue
        family, platform = _extract_family_platform(p)
        findings = _check_post(
            Path(p), family, platform, family_routes, registered_platforms,
            registered_families,
        )
        for f in findings:
            tag = f"[{f.check}] {f.level}"
            print(f"{tag} {p}")
            print(f"       {f.message}")
            if f.level == "FAIL":
                fail_count += 1
            else:
                warn_count += 1

    if fail_count:
        print(f"\n{fail_count} blog post standard failure(s). Fix frontmatter before committing.")
        return 1

    if warn_count:
        print(f"\n{warn_count} blog post warning(s). Review recommended.")
    return 0


def scan_root(
    blog_root: Path,
    family_routes: dict[str, str],
    registered_platforms: set[str],
    registered_families: set[str] = frozenset(),
) -> list[tuple[Path, Finding]]:
    """Return (path, finding) for all failing/warning posts under blog_root."""
    results: list[tuple[Path, Finding]] = []
    for md in sorted(blog_root.rglob("index.md")):
        if not _is_blog_post(md):
            continue
        family, platform = _extract_family_platform(md)
        for finding in _check_post(
            md, family, platform, family_routes, registered_platforms,
            registered_families,
        ):
            results.append((md, finding))
    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "files",
        nargs="*",
        metavar="FILE",
        help="Files to check (staged-file mode).",
    )
    p.add_argument(
        "--scan",
        action="store_true",
        help="Full-repo scan mode. Exit 1 if any FAIL found.",
    )
    p.add_argument(
        "--root",
        default="content",
        help="Content root directory for --scan mode (default: content).",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if yaml is None:
        print("ERROR: PyYAML is required. Install with: pip install pyyaml", file=sys.stderr)
        return 2

    family_routes = _load_family_routes()
    registered_platforms = _load_registered_platforms()
    registered_families = _load_registered_families()

    if args.scan or not args.files:
        content_root = Path(args.root)
        blog_root = content_root / "blog.aspose.org"
        if not blog_root.is_dir():
            print(f"ERROR: blog content root not found: {blog_root}", file=sys.stderr)
            return 2

        results = scan_root(blog_root, family_routes, registered_platforms, registered_families)
        if not results:
            print("Blog post standards scan: 0 issues found.")
            return 0

        fail_count = 0
        for path, finding in results:
            try:
                rel = path.relative_to(content_root)
            except ValueError:
                rel = path
            print(f"[{finding.check}] {finding.level} {rel}")
            print(f"       {finding.message}")
            if finding.level == "FAIL":
                fail_count += 1

        total = len(results)
        print(f"\n{total} finding(s): {fail_count} FAIL, {total - fail_count} WARN.")
        return 1 if fail_count else 0

    return check_files(args.files, family_routes, registered_platforms, registered_families)


if __name__ == "__main__":
    sys.exit(main())
