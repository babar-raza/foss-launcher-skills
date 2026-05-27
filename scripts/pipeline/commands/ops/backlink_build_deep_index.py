"""
backlink_build_deep_index.py — Layer 1

Reads data/aspose_com_targets.json all_urls flat index and builds a
normalized deep target index with classified endpoint types and metadata.

Only HTTP 200 endpoints are included. Pure function build_deep_index()
performs no I/O.

Output: data/backlinks/workspace/deep_target_index.json (gitignored)

Usage:
    .venv/Scripts/python backlink_build_deep_index.py [--families 3d,words] [--output PATH] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

# Resolve repo root
REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "pipeline"))

from lib.backlink_targets import PLATFORM_ALIASES, load_target_map

# Subdomain key map (host → short key)
SUBDOMAIN_KEYS = {
    "reference.aspose.com": "reference",
    "docs.aspose.com": "docs",
    "kb.aspose.com": "kb",
    "products.aspose.com": "products",
    "blog.aspose.com": "blog",
}


def classify_endpoint_type(parts: list[str], subdomain_key: str) -> str:
    """
    Classify a URL into an endpoint type based on path depth and subdomain.

    parts: URL path segments (after host), e.g. ['words', 'net'] or ['words', 'net', 'aspose.words', 'document']
    subdomain_key: 'reference', 'docs', 'kb', 'products', 'blog'
    depth: len(parts)
    """
    depth = len(parts)

    if depth == 0:
        return "subdomain_root"
    if depth == 1:
        return "family_landing"

    # depth >= 2: family/platform/...
    if depth == 2:
        # family/platform
        if subdomain_key == "reference":
            return "platform_reference_root"
        elif subdomain_key == "docs":
            return "platform_docs_root"
        elif subdomain_key == "kb":
            return "platform_kb_root"
        elif subdomain_key == "products":
            return "platform_products"
        elif subdomain_key == "blog":
            return "blog_category"
        return "platform_landing"

    if depth == 3:
        if subdomain_key == "reference":
            # family/platform/namespace
            return "reference_namespace"
        elif subdomain_key == "kb":
            # family/platform/article-slug
            return "kb_article"
        elif subdomain_key == "docs":
            return "docs_article"
        elif subdomain_key == "blog":
            return "blog_post"
        return "deep_page"

    if depth >= 4:
        if subdomain_key == "reference":
            # family/platform/namespace/class[/member]
            return "reference_class"
        return "deep_page"

    return "unknown"


def extract_metadata(parts: list[str], subdomain_key: str) -> dict:
    """
    Extract structured metadata from URL path segments.

    parts: path segments without scheme/host/trailing-slash
    Returns dict with family, platform_slug, platform (canonical), namespace, class_name, article_slug
    """
    meta: dict = {}
    depth = len(parts)

    if depth >= 1:
        meta["family"] = parts[0]
    if depth >= 2:
        slug = parts[1]
        meta["platform_slug"] = slug
        # Resolve canonical platform via PLATFORM_ALIASES
        canonical = PLATFORM_ALIASES.get(slug, slug)
        meta["platform"] = canonical
    if depth >= 3:
        if subdomain_key == "reference":
            meta["namespace"] = parts[2]
        else:
            meta["article_slug"] = parts[2]
    if depth >= 4 and subdomain_key == "reference":
        meta["class_name"] = parts[3].lower()
    if depth >= 5 and subdomain_key == "reference":
        meta["member_name"] = parts[4].lower()

    return meta


def build_deep_index(all_urls: dict, families_filter: Optional[list[str]] = None) -> dict:
    """
    Build deep target index from all_urls flat map.

    Only includes HTTP 200 endpoints.
    Pure function — no I/O.

    Returns dict keyed by normalized path (no scheme, no host, no trailing slash):
        {
            "reference/words/net/aspose.words/document": {
                "url": "https://reference.aspose.com/words/net/aspose.words/document/",
                "path": "reference/words/net/aspose.words/document",
                "http_status": 200,
                "subdomain_key": "reference",
                "type": "reference_class",
                "family": "words",
                "platform_slug": "net",
                "platform": "net",
                "namespace": "aspose.words",
                "class_name": "document",
                ...
            }
        }
    """
    index: dict = {}

    for url, entry in all_urls.items():
        # Only include verified HTTP 200 endpoints
        if entry.get("http_status") != 200:
            continue

        # Parse URL: https://{host}/{path}/
        url_stripped = url.rstrip("/")
        slash_idx = url_stripped.find("://")
        if slash_idx < 0:
            continue
        rest = url_stripped[slash_idx + 3:]  # e.g. "reference.aspose.com/words/net"
        host_end = rest.find("/")
        if host_end < 0:
            host = rest
            path_str = ""
        else:
            host = rest[:host_end]
            path_str = rest[host_end + 1:]

        subdomain_key = SUBDOMAIN_KEYS.get(host)
        if subdomain_key is None:
            continue

        # Normalize path: split into segments
        parts = [p for p in path_str.split("/") if p]

        # Apply family filter
        if families_filter and parts:
            if parts[0] not in families_filter:
                continue

        # Classify endpoint type
        endpoint_type = classify_endpoint_type(parts, subdomain_key)

        # Build normalized path key (no trailing slash, no scheme/host)
        path_key = f"{subdomain_key}/{'/'.join(parts)}" if parts else subdomain_key

        # Extract metadata
        meta = extract_metadata(parts, subdomain_key)

        record = {
            "url": url_stripped + "/",  # canonical form with trailing slash
            "path": path_key,
            "http_status": 200,
            "subdomain_key": subdomain_key,
            "type": endpoint_type,
        }
        record.update(meta)

        index[path_key] = record

    return index


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build deep target index from aspose_com_targets.json (Layer 1)"
    )
    parser.add_argument(
        "--families",
        default=None,
        help="Comma-separated family filter, e.g. '3d,words'",
    )
    parser.add_argument(
        "--output",
        default=str(REPO_ROOT / "data" / "backlinks" / "workspace" / "deep_target_index.json"),
    )
    parser.add_argument("--dry-run", action="store_true", help="Print summary; do not write output")
    args = parser.parse_args()

    families_filter = [f.strip() for f in args.families.split(",")] if args.families else None

    map_path = REPO_ROOT / "data" / "aspose_com_targets.json"
    if not map_path.exists():
        print(f"ERROR: target map not found at {map_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Loading target map from {map_path} ...")
    target_map = load_target_map(REPO_ROOT)
    all_urls: dict = target_map.get("all_urls", {})
    print(f"Loaded {len(all_urls):,} total URLs from all_urls index")

    print(f"Building deep index (families={args.families or 'all'}) ...")
    index = build_deep_index(all_urls, families_filter)

    # Summary by type
    from collections import Counter
    type_counts = Counter(rec["type"] for rec in index.values())
    total = len(index)
    print(f"Deep index: {total:,} verified HTTP 200 endpoints")
    for t, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"  {t}: {count:,}")

    # Validate at least 1 reference_class if reference/3d is in scope
    if families_filter and "3d" in families_filter:
        ref_classes = [k for k, v in index.items() if v["type"] == "reference_class" and "3d" in k]
        print(f"Reference classes for 3d: {len(ref_classes)}")
        if ref_classes:
            print(f"  Sample: {ref_classes[0]}")

    if args.dry_run:
        print("Dry-run: output not written.")
        return

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Compute hash of target map for staleness detection
    import hashlib
    map_hash = "sha256:" + hashlib.sha256(
        map_path.read_bytes()
    ).hexdigest()[:16]

    output = {
        "schema_version": "1.0.0",
        "families_filter": families_filter,
        "total_endpoints": total,
        "type_counts": dict(type_counts),
        "target_map_hash": map_hash,
        "index": index,
    }

    out_path.write_text(
        json.dumps(output, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Written: {out_path}")


if __name__ == "__main__":
    main()
