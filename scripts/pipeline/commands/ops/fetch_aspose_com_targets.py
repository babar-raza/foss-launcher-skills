#!/usr/bin/env python3
# Adapted from aspose.org
"""fetch_aspose_com_targets.py — Fetch aspose.com sitemaps and build the canonical backlink target map.

Fetches sitemaps for products.aspose.com, docs.aspose.com, reference.aspose.com,
kb.aspose.com, and blog.aspose.com. Normalizes, classifies, and HTTP-verifies all
URLs. Writes data/aspose_com_targets.json and data/backlinks/aspose_com_targets.yaml.

Usage:
    python scripts/pipeline/commands/ops/fetch_aspose_com_targets.py
    python scripts/pipeline/commands/ops/fetch_aspose_com_targets.py --dry-run
    python scripts/pipeline/commands/ops/fetch_aspose_com_targets.py --skip-http-verify
    python scripts/pipeline/commands/ops/fetch_aspose_com_targets.py --families words cells

Exit codes:
    0   Success — target map written
    1   P0 sitemap unavailable — aborted (no data written)
    2   Partial failure — P1/P2 sitemaps missing (data written with warnings)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import urllib.parse
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
import os
from typing import Optional
from xml.etree import ElementTree

try:
    import requests
    from requests.exceptions import RequestException, Timeout, ConnectionError as ConnError
except ImportError:
    print("ERROR: 'requests' package required. Install with: pip install requests", file=sys.stderr)
    sys.exit(1)

try:
    import yaml
except ImportError:
    yaml = None  # YAML export will be skipped if pyyaml not available

_REPO_ROOT = Path(os.environ.get("FOSS_REPO_ROOT", str(Path(__file__).resolve().parents[4])))

REPO_ROOT = _REPO_ROOT

SCRIPT_VERSION = "1.0.0"
GENERATOR_NAME = "fetch_aspose_com_targets.py"
USER_AGENT = "aspose-backlink-governance/1.0"

# Sitemap sources per §3.1
SITEMAPS = [
    {"url": "https://products.aspose.com/sitemap.xml",  "priority": "P0", "subdomain": "products.aspose.com"},
    {"url": "https://docs.aspose.com/sitemap.xml",      "priority": "P0", "subdomain": "docs.aspose.com"},
    {"url": "https://reference.aspose.com/sitemap.xml", "priority": "P1", "subdomain": "reference.aspose.com"},
    {"url": "https://kb.aspose.com/sitemap.xml",        "priority": "P2", "subdomain": "kb.aspose.com"},
    {"url": "https://blog.aspose.com/sitemap.xml",      "priority": "P2", "subdomain": "blog.aspose.com"},
]

# Known family names (from §1.2)
KNOWN_FAMILIES = {
    "3d", "barcode", "cad", "cells", "diagram", "drawing", "email", "finance",
    "font", "gis", "html", "imaging", "medical", "note", "ocr", "omr", "page",
    "pdf", "psd", "pub", "slides", "svg", "tasks", "tex", "words", "zip",
}

# Platform canonical + alias table (§3.4)
PLATFORM_ALIASES: dict[str, str] = {
    # net
    "net": "net", "dotnet": "net", "csharp": "net",
    "net60": "net", "net48": "net", "net40": "net",
    # python
    "python": "python", "py": "python", "python3": "python",
    "python-net": "python", "python-java": "python",
    # java
    "java": "java", "java8": "java", "java11": "java", "java-android": "java",
    # cpp
    "cpp": "cpp", "c-plus-plus": "cpp", "cplusplus": "cpp", "c++": "cpp",
    # nodejs
    "nodejs": "nodejs", "node": "nodejs", "node-js": "nodejs",
    "javascript": "nodejs", "js": "nodejs",
    # android
    "android": "android", "android-java": "android",
    # cloud
    "cloud": "cloud", "rest-api": "cloud", "api": "cloud", "saas": "cloud",
    # ruby
    "ruby": "ruby", "ruby-net": "ruby",
    # go
    "go": "go", "golang": "go",
}

CANONICAL_PLATFORMS = set(PLATFORM_ALIASES.values())

# URL patterns to skip per §3.2
SKIP_PATTERNS = re.compile(
    r'/(?:search|feed|rss|sitemap|tag|category|author|page/\d+|wp-|admin|login)',
    re.IGNORECASE,
)

# XML namespace for sitemaps
NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


# ── Data structures ──────────────────────────────────────────────────────────

@dataclass
class TargetEntry:
    url: str
    http_status: int
    redirect_chain: list[str]
    validated_via: str  # "head" | "get" | "skipped"
    retry_count: int
    subdomain: str
    url_type: str  # family-products | platform-products | family-docs | platform-docs | etc.
    family: Optional[str]
    platform: Optional[str]  # canonical platform token


@dataclass
class SitemapSource:
    sitemap_url: str
    priority: str
    subdomain: str
    fetched_at: str
    source_hash: str
    http_status: int
    entry_count: int
    included_count: int
    excluded_count: int
    redirect_count: int
    warnings: list[str]


# ── URL normalization (§3.2) ──────────────────────────────────────────────────

def normalize_url(url: str) -> Optional[str]:
    """Normalize a URL per §3.2. Returns None if URL should be skipped."""
    url = url.strip().lower()
    # Force https
    if url.startswith("http://"):
        url = "https://" + url[7:]
    if not url.startswith("https://"):
        return None
    # Strip /en/ prefix
    url = re.sub(r'(/en)/', '/', url)
    # Ensure trailing slash (for path URLs)
    parsed = urllib.parse.urlparse(url)
    if parsed.path and not parsed.path.endswith('/'):
        url = url + '/'
    # Reject query strings and fragments
    if parsed.query or parsed.fragment:
        return None
    # Skip known junk patterns
    if SKIP_PATTERNS.search(parsed.path):
        return None
    return url


# ── URL classification (§3.3) ────────────────────────────────────────────────

def classify_url(url: str, subdomain: str) -> tuple[str, Optional[str], Optional[str]]:
    """
    Returns (url_type, family, canonical_platform).
    url_type is one of: family-products, platform-products, family-docs,
    platform-docs, platform-reference-root, class-reference, platform-kb-root,
    deep-url, unknown.
    """
    parsed = urllib.parse.urlparse(url)
    # Strip leading slash, split
    parts = [p for p in parsed.path.strip('/').split('/') if p]

    if not parts:
        return "root", None, None

    # Detect family
    family = parts[0] if parts[0] in KNOWN_FAMILIES else None

    # Detect platform (2nd segment)
    platform = None
    if len(parts) >= 2:
        raw_plat = parts[1]
        platform = PLATFORM_ALIASES.get(raw_plat)

    if subdomain == "products.aspose.com":
        if family and platform and len(parts) == 2:
            return "platform-products", family, platform
        if family and len(parts) == 1:
            return "family-products", family, None
        if family and platform:
            return "deep-products", family, platform
        return "unknown", family, platform

    elif subdomain == "docs.aspose.com":
        if family and platform and len(parts) == 2:
            return "platform-docs", family, platform
        if family and len(parts) == 1:
            return "family-docs", family, None
        if family and platform:
            return "deep-docs", family, platform
        return "unknown", family, platform

    elif subdomain == "reference.aspose.com":
        if family and platform and len(parts) == 2:
            return "platform-reference-root", family, platform
        if family and len(parts) == 1:
            return "family-reference", family, None
        if family and platform and len(parts) == 3:
            return "class-reference", family, platform
        if family and platform and len(parts) >= 4:
            return "nested-class-reference", family, platform
        return "unknown", family, platform

    elif subdomain == "kb.aspose.com":
        if family and platform and len(parts) == 2:
            return "platform-kb-root", family, platform
        if family and len(parts) == 1:
            return "family-kb", family, None
        if family and platform:
            return "deep-kb", family, platform
        return "unknown", family, platform

    elif subdomain == "blog.aspose.com":
        if family and platform and len(parts) == 2:
            return "platform-blog", family, platform
        if family and len(parts) == 1:
            return "family-blog", family, None
        if family and platform:
            return "deep-blog", family, platform
        return "unknown", family, platform

    return "unknown", family, platform


# ── HTTP verification (§U HEAD → GET fallback) ──────────────────────────────

def verify_url(url: str, session: requests.Session, max_retries: int = 3) -> tuple[int, list[str], str, int]:
    """
    Returns (final_http_status, redirect_chain, validated_via, retry_count).
    Uses HEAD first; falls back to GET on 403/405/timeout/suspicious.
    """
    redirect_chain: list[str] = []
    retry_delays = [2, 4, 8]
    last_status = 0
    validated_via = "head"

    for attempt in range(max_retries):
        try:
            resp = session.head(url, allow_redirects=True, timeout=15, stream=False)
            for r in resp.history:
                redirect_chain.append(r.url)
            last_status = resp.status_code
            # HEAD succeeded with a usable status
            if last_status not in (403, 405, 0):
                return last_status, redirect_chain, "head", attempt
            # Fall through to GET
        except (Timeout, ConnError, RequestException):
            pass

        # GET fallback
        try:
            redirect_chain_get: list[str] = []
            resp = session.get(url, allow_redirects=True, timeout=20, stream=True)
            for r in resp.history:
                redirect_chain_get.append(r.url)
            # Read only first 4KB
            _ = resp.raw.read(4096)
            resp.close()
            redirect_chain = redirect_chain_get
            validated_via = "get"
            return resp.status_code, redirect_chain, "get", attempt
        except (Timeout, ConnError, RequestException):
            pass

        if attempt < max_retries - 1:
            time.sleep(retry_delays[attempt])

    return last_status, redirect_chain, validated_via, max_retries


# ── Sitemap fetching ─────────────────────────────────────────────────────────

def sha256_of(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# Locale code pattern for filtering child sitemaps (all non-English locales)
_NON_EN_LOCALE_RE = re.compile(
    r'/(?:ar|bg|ca|cs|da|de|el|es|fa|fi|fr|he|hi|hr|hu|id|it|ja|ko|lt|lv|ms|nl|no|pl|pt|ro|ru|sk|sr|sv|th|tr|uk|vi|zh(?:-hant)?)/'
)


def fetch_sitemap_urls(sitemap_url: str, session: requests.Session, depth: int = 0) -> tuple[list[str], str, int]:
    """
    Recursively fetch sitemap. Returns (url_list, raw_xml_hash, http_status).
    Handles both <sitemapindex> and <urlset>.
    Max recursion depth: 2.
    """
    if depth > 2:
        return [], "", 0

    try:
        resp = session.get(sitemap_url, timeout=30, headers={"User-Agent": USER_AGENT})
        http_status = resp.status_code
        if http_status != 200:
            return [], "", http_status
        raw_xml = resp.text
        source_hash = sha256_of(raw_xml)
    except (Timeout, ConnError, RequestException) as exc:
        print(f"  WARN: Could not fetch {sitemap_url}: {exc}", file=sys.stderr)
        return [], "", 0

    try:
        root = ElementTree.fromstring(raw_xml)  # nosec B314 - input is Aspose sitemap XML from known URLs
    except ElementTree.ParseError as exc:
        print(f"  WARN: XML parse error for {sitemap_url}: {exc}", file=sys.stderr)
        return [], source_hash, http_status

    def _find_text(elem: ElementTree.Element, tag: str) -> Optional[str]:
        """Find child element by ns-prefixed tag, falling back to bare tag. Returns text or None."""
        child = elem.find("sm:" + tag, NS)
        if child is None:
            child = elem.find(tag)
        return child.text if child is not None else None

    def _findall(parent: ElementTree.Element, tag: str) -> list[ElementTree.Element]:
        """Find all children by ns-prefixed tag, falling back to bare tag."""
        results = parent.findall("sm:" + tag, NS)
        if not results:
            results = parent.findall(tag)
        return results

    # Sitemap index — recurse (English locale only)
    if root.tag in (
        "{http://www.sitemaps.org/schemas/sitemap/0.9}sitemapindex",
        "sitemapindex",
    ):
        all_urls: list[str] = []
        for sitemap_elem in _findall(root, "sitemap"):
            child_url = _find_text(sitemap_elem, "loc")
            if child_url:
                child_url = child_url.strip()
                # Skip non-English locale sub-sitemaps (e.g. /de/sitemap.xml, /fr/sitemap.xml)
                if _NON_EN_LOCALE_RE.search(child_url):
                    continue
                child_urls, _, _ = fetch_sitemap_urls(child_url, session, depth + 1)
                all_urls.extend(child_urls)
        return all_urls, source_hash, http_status

    # URL set
    urls: list[str] = []
    for url_elem in _findall(root, "url"):
        loc_text = _find_text(url_elem, "loc")
        if loc_text:
            urls.append(loc_text.strip())
    return urls, source_hash, http_status


# ── Synthesize URLs from local content (for products.aspose.com and docs.aspose.com) ──

def discover_families_and_platforms(repo_root: Path) -> dict[str, set[str]]:
    """
    Walk content/products.aspose.org/en to discover all families and their platforms.
    Returns {family: {platform1, platform2, ...}}.
    """
    products_root = repo_root / "content" / "products.aspose.org" / "en"
    result: dict[str, set[str]] = {}

    if not products_root.exists():
        return result

    for fam_dir in products_root.iterdir():
        if not fam_dir.is_dir():
            continue
        if fam_dir.name not in KNOWN_FAMILIES:
            continue
        family = fam_dir.name
        result[family] = set()
        for plat_dir in fam_dir.iterdir():
            if not plat_dir.is_dir():
                continue
            plat_name = plat_dir.name
            canonical = PLATFORM_ALIASES.get(plat_name)
            if canonical:
                result[family].add(canonical)

    return result


def synthesize_urls_for_subdomain(
    subdomain: str,
    families_platforms: dict[str, set[str]],
    filter_families: Optional[set[str]],
) -> list[tuple[str, str, Optional[str], Optional[str]]]:
    """
    Construct candidate URLs for a subdomain from known families/platforms.
    Returns list of (url, url_type, family, platform).
    """
    base = f"https://{subdomain}/"
    results: list[tuple[str, str, Optional[str], Optional[str]]] = []

    for family, platforms in sorted(families_platforms.items()):
        if filter_families and family not in filter_families:
            continue

        # Family URL
        fam_url = f"{base}{family}/"
        fam_type = "family-products" if "products" in subdomain else "family-docs"
        results.append((fam_url, fam_type, family, None))

        # Platform URLs
        for platform in sorted(platforms):
            plat_url = f"{base}{family}/{platform}/"
            plat_type = "platform-products" if "products" in subdomain else "platform-docs"
            results.append((plat_url, plat_type, family, platform))

    return results


# ── Build target map ─────────────────────────────────────────────────────────

def build_target_map(
    args: argparse.Namespace,
    session: requests.Session,
) -> tuple[dict, list[str]]:
    """
    Fetch all sitemaps, verify URLs, and build the targets dict.
    Returns (output_data, warnings).
    """
    sources: list[dict] = []
    all_entries: dict[str, TargetEntry] = {}  # url → TargetEntry
    warnings: list[str] = []
    unavailable_sources: list[str] = []

    filter_families: Optional[set[str]] = set(args.families) if args.families else None

    # Discover families + platforms from content directory (for synthesis)
    repo_root: Path = args.repo_root
    families_platforms = discover_families_and_platforms(repo_root)
    print(
        f"Discovered {len(families_platforms)} families from content directory",
        file=sys.stderr,
    )

    # Subdomains that must be synthesized (no useful product-level sitemaps)
    SYNTHESIZE_SUBDOMAINS = {"products.aspose.com", "docs.aspose.com"}

    # Handle synthesis subdomains first
    for subdomain in ("products.aspose.com", "docs.aspose.com"):
        priority = "P0"
        print(f"[{priority}] Synthesizing URLs for {subdomain} ...", file=sys.stderr)
        candidates = synthesize_urls_for_subdomain(subdomain, families_platforms, filter_families)
        included = 0
        excluded = 0
        redirects_seen = 0

        for url, url_type, family, platform in candidates:
            if args.skip_http_verify:
                http_st, rchain, via, retries = 200, [], "skipped", 0
            else:
                http_st, rchain, via, retries = verify_url(url, session)

            if rchain:
                redirects_seen += 1
            if http_st == 404:
                excluded += 1
                continue

            entry = TargetEntry(
                url=url,
                http_status=http_st,
                redirect_chain=rchain,
                validated_via=via,
                retry_count=retries,
                subdomain=subdomain,
                url_type=url_type,
                family=family,
                platform=platform,
            )
            all_entries[url] = entry
            included += 1

        sources.append({
            "sitemap_url": f"synthesized:{subdomain}",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "source_hash": "synthesized",
            "http_status": 200,
            "entry_count": len(candidates),
            "included_count": included,
            "excluded_count": excluded,
            "redirect_count": redirects_seen,
            "warnings": [],
        })
        print(f"  -> included={included} excluded={excluded}", file=sys.stderr)

    # Handle sitemap-based subdomains
    for sm_def in SITEMAPS:
        if sm_def["subdomain"] in SYNTHESIZE_SUBDOMAINS:
            continue  # already handled above
        subdomain = sm_def["subdomain"]
        priority = sm_def["priority"]
        sitemap_url = sm_def["url"]
        print(f"[{priority}] Fetching {sitemap_url} ...", file=sys.stderr)

        raw_urls, source_hash, http_status = fetch_sitemap_urls(sitemap_url, session)

        if http_status == 0 or (priority == "P0" and http_status != 200):
            msg = f"P0 sitemap unavailable: {sitemap_url} (status={http_status})"
            print(f"  ABORT: {msg}", file=sys.stderr)
            if priority == "P0":
                raise SystemExit(f"ABORT: {msg}")
            unavailable_sources.append(sitemap_url)
            continue

        if http_status != 200:
            warnings.append(f"{priority} sitemap returned {http_status}: {sitemap_url}")
            unavailable_sources.append(sitemap_url)
            print(f"  WARN: {priority} sitemap returned {http_status} — skipping", file=sys.stderr)
            continue

        print(f"  → {len(raw_urls)} raw URLs fetched", file=sys.stderr)

        included = 0
        excluded = 0
        redirects_seen = 0
        src_warnings: list[str] = []

        for raw_url in raw_urls:
            norm = normalize_url(raw_url)
            if norm is None:
                excluded += 1
                continue

            url_type, family, platform = classify_url(norm, subdomain)

            # Family filter
            if filter_families and family and family not in filter_families:
                excluded += 1
                continue

            # Verify HTTP status
            if args.skip_http_verify:
                http_st, rchain, via, retries = 200, [], "skipped", 0
            else:
                http_st, rchain, via, retries = verify_url(norm, session)

            if rchain:
                redirects_seen += 1

            if http_st == 404:
                excluded += 1
                continue

            entry = TargetEntry(
                url=norm,
                http_status=http_st,
                redirect_chain=rchain,
                validated_via=via,
                retry_count=retries,
                subdomain=subdomain,
                url_type=url_type,
                family=family,
                platform=platform,
            )
            all_entries[norm] = entry
            included += 1

        sources.append({
            "sitemap_url": sitemap_url,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "source_hash": f"sha256:{source_hash}",
            "http_status": http_status,
            "entry_count": len(raw_urls),
            "included_count": included,
            "excluded_count": excluded,
            "redirect_count": redirects_seen,
            "warnings": src_warnings,
        })
        print(f"  → included={included} excluded={excluded} redirects={redirects_seen}", file=sys.stderr)

    # Build structured targets per §3.5
    targets: dict[str, dict] = {}
    all_urls_flat: dict[str, dict] = {}

    for norm_url, entry in all_entries.items():
        sd = entry.subdomain
        if sd not in targets:
            targets[sd] = {"families": {}, "platforms": {}}

        entry_dict = {
            "url": entry.url,
            "http_status": entry.http_status,
            "redirect_chain": entry.redirect_chain,
        }
        all_urls_flat[norm_url] = {
            "http_status": entry.http_status,
            "type": entry.url_type,
            "family": entry.family,
            "platform": entry.platform,
            "redirect_chain": entry.redirect_chain,
        }

        if entry.url_type in ("family-products", "family-docs", "family-reference",
                              "family-kb", "family-blog") and entry.family:
            targets[sd]["families"][entry.family] = entry_dict

        elif entry.url_type in ("platform-products", "platform-docs", "platform-reference-root",
                                "platform-kb-root", "platform-blog") and entry.family and entry.platform:
            key = f"{entry.family}/{entry.platform}"
            targets[sd]["platforms"][key] = entry_dict

    # Build family/platform matrix
    matrix: dict[str, dict] = {}
    products_sd = "products.aspose.com"
    docs_sd = "docs.aspose.com"
    ref_sd = "reference.aspose.com"

    # Collect all families seen
    all_families: set[str] = set()
    for entry in all_entries.values():
        if entry.family:
            all_families.add(entry.family)

    for fam in sorted(all_families):
        matrix[fam] = {
            "has_family_on_products": fam in targets.get(products_sd, {}).get("families", {}),
            "has_family_on_docs": fam in targets.get(docs_sd, {}).get("families", {}),
            "has_family_on_reference": fam in targets.get(ref_sd, {}).get("families", {}),
            "platforms_on_products": sorted(
                k.split("/")[1]
                for k in targets.get(products_sd, {}).get("platforms", {})
                if k.startswith(fam + "/")
            ),
            "platforms_on_docs": sorted(
                k.split("/")[1]
                for k in targets.get(docs_sd, {}).get("platforms", {})
                if k.startswith(fam + "/")
            ),
            "platforms_on_reference": sorted(
                k.split("/")[1]
                for k in targets.get(ref_sd, {}).get("platforms", {})
                if k.startswith(fam + "/")
            ),
        }

    output_json_str = ""  # placeholder for hash computation
    output_data = {
        "schema_version": "1.0",
        "provenance": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "generator": GENERATOR_NAME,
            "generator_version": SCRIPT_VERSION,
            "sources": sources,
            "output_hash": "",  # filled below
            "total_targets": len(all_entries),
        },
        "targets": targets,
        "all_urls": all_urls_flat,
        "unavailable_sources": unavailable_sources,
        "family_platform_matrix": matrix,
    }

    # Compute output hash
    content_for_hash = json.dumps(output_data, sort_keys=True, ensure_ascii=False)
    output_data["provenance"]["output_hash"] = f"sha256:{sha256_of(content_for_hash)}"

    return output_data, warnings


# ── YAML mirror (TC-BL-TARGET-MAP-HUGO-SYNC) ────────────────────────────────

def build_hugo_yaml_mirror(output_data: dict) -> dict:
    """
    Build a flat YAML structure for Hugo: {family/platform: {url, http_status}}.
    Only includes entries with http_status == 200.
    Includes source_json_hash for sync verification.
    """
    mirror: dict[str, dict] = {}
    products_targets = output_data["targets"].get("products.aspose.com", {})

    for key, entry in products_targets.get("platforms", {}).items():
        if entry["http_status"] == 200:
            mirror[key] = {
                "url": entry["url"],
                "http_status": entry["http_status"],
            }

    for fam, entry in products_targets.get("families", {}).items():
        if entry["http_status"] == 200:
            mirror[fam] = {
                "url": entry["url"],
                "http_status": entry["http_status"],
            }

    return {
        "source_json_hash": output_data["provenance"]["output_hash"],
        "generated_at": output_data["provenance"]["generated_at"],
        "targets": mirror,
    }


# ── Report generation ────────────────────────────────────────────────────────

def generate_report(output_data: dict, warnings: list[str]) -> str:
    lines: list[str] = [
        "# Aspose.com Target Map Report",
        f"**Generated:** {output_data['provenance']['generated_at']}",
        f"**Total targets:** {output_data['provenance']['total_targets']}",
        "",
        "---",
        "",
    ]

    if warnings:
        lines.append("## Warnings")
        for w in warnings:
            lines.append(f"- {w}")
        lines.append("")

    if output_data["unavailable_sources"]:
        lines.append("## Unavailable Sitemap Sources")
        for s in output_data["unavailable_sources"]:
            lines.append(f"- {s}")
        lines.append("")

    # Per-subdomain summary
    lines.append("## Per-Subdomain Summary")
    lines.append("")
    lines.append("| Subdomain | Families | Platforms |")
    lines.append("|-----------|----------|-----------|")
    for sd, data in output_data["targets"].items():
        fam_count = len(data.get("families", {}))
        plat_count = len(data.get("platforms", {}))
        lines.append(f"| {sd} | {fam_count} | {plat_count} |")
    lines.append("")

    # Family/platform matrix
    matrix = output_data.get("family_platform_matrix", {})
    if matrix:
        lines.append("## Family �- Platform Availability Matrix")
        lines.append("")
        lines.append("| Family | Products | Docs | Reference | Products Platforms | Docs Platforms |")
        lines.append("|--------|----------|------|-----------|--------------------|----------------|")
        for fam, info in sorted(matrix.items()):
            prod = "✓" if info["has_family_on_products"] else "�-"
            docs = "✓" if info["has_family_on_docs"] else "�-"
            ref = "✓" if info["has_family_on_reference"] else "�-"
            prod_plats = ", ".join(info["platforms_on_products"]) or "—"
            docs_plats = ", ".join(info["platforms_on_docs"]) or "—"
            lines.append(f"| {fam} | {prod} | {docs} | {ref} | {prod_plats} | {docs_plats} |")
        lines.append("")

    # BLOCKED candidates (families on aspose.org products but missing everywhere on aspose.com)
    blocked = []
    for fam, info in matrix.items():
        if not info["has_family_on_products"] and not info["has_family_on_docs"]:
            blocked.append(fam)
    if blocked:
        lines.append("## Potential BLOCKED_TARGET Families")
        lines.append("")
        lines.append("These families exist in the target map data but have no products.aspose.com")
        lines.append("or docs.aspose.com family root — may cause BLOCKED_TARGET in audit.")
        lines.append("")
        for fam in blocked:
            lines.append(f"- {fam}")
        lines.append("")

    return "\n".join(lines)


# ── Main ─────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fetch aspose.com sitemaps and build the canonical backlink target map.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Fetch and process but do not write output files.",
    )
    parser.add_argument(
        "--skip-http-verify", action="store_true",
        help="Skip HEAD/GET HTTP verification (trust sitemap URLs).",
    )
    parser.add_argument(
        "--families", nargs="*", metavar="FAMILY",
        help="Restrict to specific families (e.g. words cells).",
    )
    parser.add_argument(
        "--repo-root", type=Path, default=REPO_ROOT,
        help="Override repo root path.",
    )
    args = parser.parse_args(argv)

    repo_root: Path = args.repo_root

    session = requests.Session()  # metrics-scan-exempt: web-scraping transport, not professionalize LLM
    session.headers.update({"User-Agent": USER_AGENT})

    print("=== fetch_aspose_com_targets.py ===", file=sys.stderr)
    print(f"Repo root: {repo_root}", file=sys.stderr)
    if args.dry_run:
        print("DRY RUN — no files will be written", file=sys.stderr)
    if args.skip_http_verify:
        print("HTTP verification SKIPPED", file=sys.stderr)

    # Fetch + build
    try:
        output_data, warnings = build_target_map(args, session)
    except SystemExit as exc:
        print(str(exc), file=sys.stderr)
        return 1

    # Print summary
    print("", file=sys.stderr)
    print(f"Total targets collected: {output_data['provenance']['total_targets']}", file=sys.stderr)
    for sd, data in output_data["targets"].items():
        print(f"  {sd}: families={len(data.get('families', {}))} platforms={len(data.get('platforms', {}))}", file=sys.stderr)

    if warnings:
        print("Warnings:", file=sys.stderr)
        for w in warnings:
            print(f"  ! {w}", file=sys.stderr)

    if args.dry_run:
        print("\nDRY RUN complete — no files written.", file=sys.stderr)
        return 0 if not warnings else 2

    # Write data/aspose_com_targets.json
    json_path = repo_root / "data" / "aspose_com_targets.json"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(output_data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\nWritten: {json_path}", file=sys.stderr)

    # Write data/backlinks/aspose_com_targets.yaml
    backlinks_dir = repo_root / "data" / "backlinks"
    backlinks_dir.mkdir(parents=True, exist_ok=True)
    yaml_path = backlinks_dir / "aspose_com_targets.yaml"

    hugo_mirror = build_hugo_yaml_mirror(output_data)
    if yaml is not None:
        yaml_path.write_text(
            yaml.dump(hugo_mirror, allow_unicode=True, sort_keys=True),
            encoding="utf-8",
        )
        print(f"Written: {yaml_path}", file=sys.stderr)
    else:
        # Fallback: write minimal YAML manually
        lines = [
            f"generated_at: '{hugo_mirror['generated_at']}'",
            f"source_json_hash: '{hugo_mirror['source_json_hash']}'",
            "targets:",
        ]
        for key, val in sorted(hugo_mirror["targets"].items()):
            lines.append(f"  \"{key}\":")
            lines.append(f"    url: \"{val['url']}\"")
            lines.append(f"    http_status: {val['http_status']}")
        yaml_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"Written (fallback YAML): {yaml_path}", file=sys.stderr)

    # Write report
    reports_dir = repo_root / "reports" / "backlinks"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / "aspose_com_targets_report.md"
    report_text = generate_report(output_data, warnings)
    report_path.write_text(report_text, encoding="utf-8")
    print(f"Written: {report_path}", file=sys.stderr)

    return 0 if not warnings else 2


if __name__ == "__main__":
    sys.exit(main())
