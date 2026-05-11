"""coverage_matrix.py — Cross-subdomain feature coverage audit for S-98.

Reads site_plan.yaml + content tree + knowledge artifacts to produce a
per-cluster x per-subdomain coverage matrix.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from .taxonomy import CoverageStatus, SUBDOMAINS
from .feature_detector import (
    extract_feature_groups_from_source,
    detect_shallow_coverage,
)

# ---------------------------------------------------------------------------
# Repo path resolution
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).resolve().parent
_DEFAULT_REPO_ROOT = _SCRIPT_DIR.parent.parent.parent.parent  # lib/enrichment/ -> lib/ -> pipeline/ -> scripts/ -> repo
_REPO_ROOT = _DEFAULT_REPO_ROOT


def configure(*, repo_root: "Path | str | None" = None) -> None:
    """Override repo root for testing."""
    global _REPO_ROOT
    _REPO_ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT


def _repo_root() -> Path:
    return _REPO_ROOT


# ---------------------------------------------------------------------------
# Data loading helpers
# ---------------------------------------------------------------------------

def load_site_plan(family: str, platform: str) -> dict:
    """Load site_plan.yaml for a family/platform."""
    path = _repo_root() / "reports" / "plans" / family / platform / "site_plan.yaml"
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_knowledge_artifacts(family: str, platform: str) -> dict[str, Any]:
    """Load merged knowledge artifacts (model, claims, api_surface)."""
    merged = _repo_root() / "knowledge" / family / platform / "merged"
    result: dict[str, Any] = {}

    model_path = merged / "model.yaml"
    if model_path.exists():
        result["model"] = yaml.safe_load(model_path.read_text(encoding="utf-8")) or {}

    claims_path = merged / "claims.json"
    if claims_path.exists():
        result["claims"] = json.loads(claims_path.read_text(encoding="utf-8"))

    api_path = merged / "api_surface.json"
    if api_path.exists():
        result["api_surface"] = json.loads(api_path.read_text(encoding="utf-8"))

    snippets_dir = merged / "snippets"
    if snippets_dir.exists() and snippets_dir.is_dir():
        snippets = []
        for f in sorted(snippets_dir.glob("*.json")):
            snippets.extend(json.loads(f.read_text(encoding="utf-8")) if f.stat().st_size > 2 else [])
        result["snippets"] = snippets

    index_path = merged / "index.json"
    if index_path.exists():
        result["index"] = json.loads(index_path.read_text(encoding="utf-8"))

    return result


def _discover_content_files(family: str, platform: str) -> dict[str, list[Path]]:
    """Find existing content .md files per subdomain."""
    root = _repo_root()
    locale_re = re.compile(
        r"\.(?:ar|bg|ca|cs|da|de|el|es|et|fa|fi|fr|he|hi|hr|hu|id|it|ja|ko|lt|lv|ms|nl|no|pl|pt|ro|ru|sk|sl|sr|sv|th|tr|uk|vi|zh)\.md$"
    )

    site_paths = {
        "products.aspose.org": root / "content" / "products.aspose.org" / "en" / family,
        "docs.aspose.org": root / "content" / "docs.aspose.org" / "en" / family / platform,
        "kb.aspose.org": root / "content" / "kb.aspose.org" / "en" / family / platform,
        "blog.aspose.org": root / "content" / "blog.aspose.org" / family / platform,
        "reference.aspose.org": root / "content" / "reference.aspose.org" / "en" / family / platform,
    }

    result: dict[str, list[Path]] = {}
    for subdomain, path in site_paths.items():
        if path.exists():
            files = [
                f for f in sorted(path.rglob("*.md"))
                if not locale_re.search(f.name)
            ]
            result[subdomain] = files
        else:
            result[subdomain] = []
    return result


# ---------------------------------------------------------------------------
# Cluster extraction from site plan
# ---------------------------------------------------------------------------

def extract_clusters_from_plan(site_plan: dict) -> list[dict]:
    """Extract cluster information from site_plan.yaml pages."""
    clusters: dict[str, dict] = {}
    plan = site_plan.get("plan", {})
    sections = plan.get("sections", {})

    for section_name, section_data in sections.items():
        if not isinstance(section_data, dict):
            continue
        for page in section_data.get("pages", []):
            cluster = page.get("cluster")
            if not cluster:
                continue
            if cluster not in clusters:
                clusters[cluster] = {
                    "category": cluster,
                    "claim_count": page.get("claim_count", 0),
                    "api_method_count": page.get("api_method_count", 0),
                    "sections_present": set(),
                }
            clusters[cluster]["sections_present"].add(section_name)
            # Use highest claim count and api_method_count seen
            if page.get("claim_count", 0) > clusters[cluster]["claim_count"]:
                clusters[cluster]["claim_count"] = page["claim_count"]
            if page.get("api_method_count", 0) > clusters[cluster]["api_method_count"]:
                clusters[cluster]["api_method_count"] = page["api_method_count"]

    # Convert sets to lists for serialization
    result = []
    for cat, info in sorted(clusters.items(), key=lambda x: x[1]["claim_count"], reverse=True):
        result.append({
            "category": cat,
            "claim_count": info["claim_count"],
            "api_method_count": info["api_method_count"],
            "sections_present": sorted(info["sections_present"]),
        })
    return result


# ---------------------------------------------------------------------------
# Coverage determination
# ---------------------------------------------------------------------------

def _read_frontmatter(path: Path) -> dict:
    """Read YAML frontmatter from a markdown file."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    try:
        return yaml.safe_load(text[3:end]) or {}
    except yaml.YAMLError:
        return {}


def _page_matches_cluster(
    page_path: Path,
    page_fm: dict,
    cluster_category: str,
    family: str,
    platform: str,
) -> str:
    """Check if a page covers a cluster. Returns 'dedicated', 'mentions', or 'no'."""
    # Check frontmatter evidence.cluster
    evidence = page_fm.get("evidence", {})
    if isinstance(evidence, dict) and evidence.get("cluster") == cluster_category:
        return "dedicated"

    # Check slug/filename match — exact cluster slug in filename
    slug = page_path.stem.replace("_index", "").replace("-", "_").lower()
    cat_normalized = cluster_category.replace("-", "_").lower()
    if cat_normalized and cat_normalized in slug:
        return "dedicated"

    # Check if all significant cluster-name parts appear in slug or title
    # e.g. "core-management" -> ["core", "management"] — both must appear
    cat_parts = [p for p in cluster_category.lower().split("-") if len(p) > 2]
    title = str(page_fm.get("title", "")).lower()
    combined = slug + " " + title

    if cat_parts and all(part in combined for part in cat_parts):
        return "dedicated"

    # Single significant part match in title = weak mention
    if cat_parts and any(part in title for part in cat_parts if len(part) > 3):
        return "mentions"

    return "no"


def determine_subdomain_coverage(
    subdomain: str,
    cluster_category: str,
    content_files: list[Path],
    family: str,
    platform: str,
) -> CoverageStatus:
    """Determine coverage status for one cluster in one subdomain."""
    if not content_files:
        return CoverageStatus.UNCOVERED

    # Reference-only: if this is reference subdomain, any files = reference_only
    if subdomain == "reference.aspose.org":
        return CoverageStatus.REFERENCE_ONLY if content_files else CoverageStatus.UNCOVERED

    # Products: check if product page exists (it's a landing page, not cluster-specific)
    if subdomain == "products.aspose.org":
        for f in content_files:
            fm = _read_frontmatter(f)
            title = str(fm.get("title", "")).lower()
            cat_words = cluster_category.replace("-", " ").lower()
            if cat_words in title:
                return CoverageStatus.COVERED
        # Product pages mention features generally
        return CoverageStatus.PRODUCT_MENTIONED_ONLY if content_files else CoverageStatus.UNCOVERED

    has_dedicated = False
    has_mention = False

    for f in content_files:
        fm = _read_frontmatter(f)
        match = _page_matches_cluster(f, fm, cluster_category, family, platform)
        if match == "dedicated":
            has_dedicated = True
            break
        elif match == "mentions":
            has_mention = True

    if has_dedicated:
        return CoverageStatus.COVERED
    elif has_mention:
        return CoverageStatus.PARTIALLY_COVERED
    else:
        return CoverageStatus.UNCOVERED


# ---------------------------------------------------------------------------
# Main coverage matrix builder
# ---------------------------------------------------------------------------

def build_coverage_matrix(
    family: str,
    platform: str,
) -> dict:
    """Build the full cross-subdomain coverage matrix.

    Returns a dict with:
      - family, platform
      - clusters: list of cluster dicts
      - matrix: dict[cluster_category][subdomain] -> CoverageStatus.value
      - summary: aggregate statistics
    """
    site_plan = load_site_plan(family, platform)
    if not site_plan:
        return {"error": f"No site_plan.yaml found for {family}/{platform}"}

    knowledge = load_knowledge_artifacts(family, platform)
    clusters = extract_clusters_from_plan(site_plan)
    content_files = _discover_content_files(family, platform)

    # Extract feature groups from source for shallow coverage detection
    feature_groups = extract_feature_groups_from_source(family, platform)

    plan_meta = site_plan.get("plan", {})
    total_claims = plan_meta.get("evidence_summary", {}).get("total_claim_count", 0)
    # Fallback: sum cluster claim counts if plan metadata missing
    if not total_claims:
        total_claims = sum(c.get("claim_count", 0) for c in clusters)

    # Identify the largest cluster — the catch-all that likely aggregates
    # unrelated features.  Feature detection applies only to this cluster,
    # and only if it holds >40% of total claims (i.e., actually overloaded).
    largest_cluster = ""
    if clusters and total_claims > 0:
        top = clusters[0]  # sorted by claim_count descending
        if top["claim_count"] / total_claims > 0.4 and top["claim_count"] > 200:
            largest_cluster = top["category"]

    matrix: dict[str, dict[str, str]] = {}
    shallow_coverage: dict[str, dict[str, dict]] = {}  # cluster -> subdomain -> info
    for cluster in clusters:
        cat = cluster["category"]
        row: dict[str, str] = {}
        cluster_shallow: dict[str, dict] = {}
        # Feature groups only apply to the single largest cluster (the catch-all
        # mega-cluster that aggregates unrelated features). Other large clusters
        # like "vendor" are well-scoped and don't contain hidden feature groups.
        cluster_features = feature_groups if cat == largest_cluster else []

        for subdomain in SUBDOMAINS:
            status = determine_subdomain_coverage(
                subdomain, cat, content_files.get(subdomain, []),
                family, platform,
            )

            # Shallow coverage check for clusters marked "covered"
            if status == CoverageStatus.COVERED and cluster_features:
                sc_info = detect_shallow_coverage(
                    cat, cluster.get("claim_count", 0),
                    cluster_features, subdomain,
                    content_files.get(subdomain, []),
                    family, platform,
                )
                if sc_info.get("is_shallow"):
                    status = CoverageStatus.PARTIALLY_COVERED
                    cluster_shallow[subdomain] = sc_info

            row[subdomain] = status.value
        matrix[cat] = row
        if cluster_shallow:
            shallow_coverage[cat] = cluster_shallow

    # Summary statistics
    total_cells = len(clusters) * len(SUBDOMAINS)
    covered = sum(
        1 for row in matrix.values()
        for s in row.values()
        if s in (CoverageStatus.COVERED.value, CoverageStatus.REFERENCE_ONLY.value)
    )
    partially = sum(
        1 for row in matrix.values()
        for s in row.values()
        if s == CoverageStatus.PARTIALLY_COVERED.value
    )
    uncovered = sum(
        1 for row in matrix.values()
        for s in row.values()
        if s == CoverageStatus.UNCOVERED.value
    )
    product_only = sum(
        1 for row in matrix.values()
        for s in row.values()
        if s == CoverageStatus.PRODUCT_MENTIONED_ONLY.value
    )

    return {
        "family": family,
        "platform": platform,
        "repo_sha": plan_meta.get("repo_sha", ""),
        "total_claims": total_claims,
        "cluster_count": len(clusters),
        "clusters": clusters,
        "matrix": matrix,
        "summary": {
            "total_cells": total_cells,
            "covered": covered,
            "partially_covered": partially,
            "product_mentioned_only": product_only,
            "uncovered": uncovered,
            "coverage_ratio": round(covered / total_cells, 3) if total_cells else 0,
        },
        "subdomains": SUBDOMAINS,
        "content_file_counts": {
            sd: len(files) for sd, files in content_files.items()
        },
        "knowledge_available": {
            "model": "model" in knowledge,
            "claims": "claims" in knowledge,
            "api_surface": "api_surface" in knowledge,
            "snippets": "snippets" in knowledge,
            "index": "index" in knowledge,
        },
        "feature_groups": feature_groups,
        "shallow_coverage": shallow_coverage,
    }


def matrix_to_markdown(result: dict) -> str:
    """Convert coverage matrix result to a human-readable markdown table."""
    if "error" in result:
        return f"# Coverage Matrix Error\n\n{result['error']}\n"

    lines = [
        f"# Coverage Matrix: {result['family']}/{result['platform']}",
        "",
        f"- Clusters: {result['cluster_count']}",
        f"- Total claims: {result['total_claims']}",
        f"- Coverage ratio: {result['summary']['coverage_ratio']:.1%}",
        "",
        "## Matrix",
        "",
    ]

    # Header
    short_names = {
        "products.aspose.org": "Products",
        "docs.aspose.org": "Docs",
        "kb.aspose.org": "KB",
        "blog.aspose.org": "Blog",
        "reference.aspose.org": "Reference",
    }
    header = "| Cluster | " + " | ".join(short_names.get(sd, sd) for sd in SUBDOMAINS) + " |"
    sep = "|" + "|".join("---" for _ in range(len(SUBDOMAINS) + 1)) + "|"
    lines.append(header)
    lines.append(sep)

    status_icons = {
        "covered": "COVERED",
        "partially_covered": "PARTIAL",
        "product_mentioned_only": "PRODUCT_ONLY",
        "reference_only": "REF_ONLY",
        "uncovered": "UNCOVERED",
        "unknown": "UNKNOWN",
    }

    matrix = result["matrix"]
    for cluster in result["clusters"]:
        cat = cluster["category"]
        row = matrix.get(cat, {})
        cells = " | ".join(status_icons.get(row.get(sd, "unknown"), "?") for sd in SUBDOMAINS)
        lines.append(f"| {cat} ({cluster['claim_count']}) | {cells} |")

    lines.append("")
    lines.append("## Summary")
    lines.append("")
    s = result["summary"]
    lines.append(f"- Total cells: {s['total_cells']}")
    lines.append(f"- Covered: {s['covered']}")
    lines.append(f"- Partially covered: {s['partially_covered']}")
    lines.append(f"- Product mentioned only: {s['product_mentioned_only']}")
    lines.append(f"- Uncovered: {s['uncovered']}")
    lines.append("")

    return "\n".join(lines)
