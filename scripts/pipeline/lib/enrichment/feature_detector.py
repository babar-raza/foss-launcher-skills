"""feature_detector.py — Detect feature groups within overloaded clusters (TC-003).

Scans source modules, README headings, API surface, and existing content
to identify hidden feature groups inside large clusters, enabling
shallow-coverage detection and feature-level candidate generation.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml


# ---------------------------------------------------------------------------
# Shared helpers (avoid circular import with coverage_matrix)
# ---------------------------------------------------------------------------

def _repo_root() -> Path:
    """Access repo root via coverage_matrix (lazy import to break cycle)."""
    from .coverage_matrix import _repo_root as _cm_repo_root
    return _cm_repo_root()


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


# ---------------------------------------------------------------------------
# Feature group extraction from source modules
# ---------------------------------------------------------------------------

# Map source module filenames to human-readable feature group names.
# Only modules that represent distinct, documentable feature areas.
_MODULE_FEATURE_MAP: dict[str, str] = {
    "animation": "animation",
    "cleaner": "metadata-cleaning",
    "cli": "cli",
    "compatibility": "qa-compatibility",
    "converter": "conversion",
    "delta": "delta-inspection",
    "instancing": "variable-fonts",
    "loader": "font-loading",
    "mcp": "mcp-server",
    "preview": "preview",
    "rasterizer": "preview",          # supports preview
    "reporting": "reporting",
    "serializer": "serialization",
    "subsetter": "subsetting",
    "subset_presets": "subsetting",    # supports subsetting
    "text": "text-rendering",
    "variation": "variable-fonts",     # supports variable-fonts
    "web": "web-packaging",
}

# Feature groups that are high-value and merit dedicated content
HIGH_VALUE_FEATURES: set[str] = {
    "variable-fonts",
    "subsetting",
    "preview",
    "animation",
    "web-packaging",
    "qa-compatibility",
    "cli",
    "mcp-server",
}


def extract_feature_groups_from_source(family: str, platform: str) -> list[dict]:
    """Scan clone cache source modules to identify feature groups.

    Returns a list of feature group dicts:
      {"name": str, "source_modules": list[str], "high_value": bool}
    """
    clone_dir = _find_clone_dir(family, platform)
    if not clone_dir:
        return []

    src_dirs = [
        clone_dir / "src",
        clone_dir / "lib",
        clone_dir / family.replace("-", "_"),
    ]

    modules_found: dict[str, set[str]] = {}  # feature -> set of module filenames

    for src_dir in src_dirs:
        if not src_dir.exists():
            continue
        for py_file in src_dir.rglob("*.py"):
            stem = py_file.stem
            if stem.startswith("_") or stem == "__init__":
                continue
            feature = _MODULE_FEATURE_MAP.get(stem)
            if feature:
                modules_found.setdefault(feature, set()).add(str(py_file.relative_to(clone_dir)))

    result = []
    for feature, modules in sorted(modules_found.items()):
        result.append({
            "name": feature,
            "source_modules": sorted(modules),
            "high_value": feature in HIGH_VALUE_FEATURES,
        })
    return result


def extract_feature_groups_from_readme(family: str, platform: str) -> list[str]:
    """Extract feature group names from README capability headings."""
    clone_dir = _find_clone_dir(family, platform)
    if not clone_dir:
        return []

    readme = clone_dir / "README.md"
    if not readme.exists():
        return []

    text = readme.read_text(encoding="utf-8", errors="replace")
    features: list[str] = []

    # Extract from "Capability Snapshot" table rows
    for match in re.finditer(r"^\|\s*([A-Z][^|]+?)\s*\|", text, re.MULTILINE):
        name = match.group(1).strip().lower().replace(" ", "-")
        if name not in ("area", "---") and len(name) > 2:
            features.append(name)

    # Extract from ## headings that look like feature areas
    for match in re.finditer(r"^#{2,3}\s+(.+)$", text, re.MULTILINE):
        heading = match.group(1).strip().lower()
        # Skip generic headings
        if heading in ("install", "development", "license", "why-this-library",
                        "quick-start", "real-example-results"):
            continue
        if any(kw in heading for kw in ("variable", "font", "animation", "preview",
                                         "delta", "cli", "mcp", "web", "subset",
                                         "qa", "api")):
            features.append(heading.replace(" ", "-"))

    return sorted(set(features))


def _find_clone_dir(family: str, platform: str) -> Path | None:
    """Locate the clone cache directory for a product."""
    root = _repo_root()
    # Convention: runs/.clone_cache/aspose_{family}_{platform}/
    cache_dir = root / "runs" / ".clone_cache" / f"aspose_{family}_{platform}"
    if cache_dir.exists():
        return cache_dir
    # Try without underscores
    cache_dir2 = root / "runs" / ".clone_cache" / f"aspose_{family.replace('-', '_')}_{platform}"
    if cache_dir2.exists():
        return cache_dir2
    return None


# ---------------------------------------------------------------------------
# Shallow coverage detection
# ---------------------------------------------------------------------------

def detect_shallow_coverage(
    cluster_category: str,
    cluster_claim_count: int,
    feature_groups: list[dict],
    subdomain: str,
    content_files: list[Path],
    family: str,
    platform: str,
) -> dict:
    """Detect whether a 'covered' cluster has shallow coverage.

    Returns:
        {
            "is_shallow": bool,
            "total_features": int,
            "covered_features": list[str],
            "uncovered_features": list[str],
            "coverage_depth": float,  # 0.0-1.0
        }
    """
    if not feature_groups:
        return {
            "is_shallow": False,
            "total_features": 0,
            "covered_features": [],
            "uncovered_features": [],
            "coverage_depth": 1.0,
        }

    # Only check high-value features for shallow coverage
    high_value = [fg for fg in feature_groups if fg.get("high_value")]
    if not high_value:
        return {
            "is_shallow": False,
            "total_features": len(feature_groups),
            "covered_features": [fg["name"] for fg in feature_groups],
            "uncovered_features": [],
            "coverage_depth": 1.0,
        }

    # Check which feature groups are mentioned in existing content
    covered_features: list[str] = []
    uncovered_features: list[str] = []

    # Collect text from all content files for this subdomain
    content_text = _collect_content_text(content_files, cluster_category)

    for fg in high_value:
        if _feature_mentioned_in_content(fg["name"], content_text):
            covered_features.append(fg["name"])
        else:
            uncovered_features.append(fg["name"])

    total_hv = len(high_value)
    covered_count = len(covered_features)
    depth = covered_count / total_hv if total_hv > 0 else 1.0

    # Shallow if < 50% of high-value features covered, or cluster is large (>500 claims)
    # and depth < 70%
    is_shallow = (
        (total_hv >= 3 and depth < 0.5) or
        (cluster_claim_count > 500 and depth < 0.7)
    )

    return {
        "is_shallow": is_shallow,
        "total_features": total_hv,
        "covered_features": covered_features,
        "uncovered_features": uncovered_features,
        "coverage_depth": round(depth, 3),
    }


def _collect_content_text(content_files: list[Path], cluster_category: str) -> str:
    """Collect text from content files that match a cluster for feature scanning."""
    texts: list[str] = []
    for f in content_files:
        fm = _read_frontmatter(f)
        # Only inspect pages that match or relate to this cluster
        evidence = fm.get("evidence", {})
        slug = f.stem.replace("_index", "").replace("-", "_").lower()
        cat_norm = cluster_category.replace("-", "_").lower()

        is_related = False
        if isinstance(evidence, dict) and evidence.get("cluster") == cluster_category:
            is_related = True
        elif cat_norm and cat_norm in slug:
            is_related = True
        else:
            cat_parts = [p for p in cluster_category.lower().split("-") if len(p) > 2]
            title = str(fm.get("title", "")).lower()
            if cat_parts and all(p in (slug + " " + title) for p in cat_parts):
                is_related = True

        if is_related:
            try:
                texts.append(f.read_text(encoding="utf-8", errors="replace").lower())
            except OSError:
                pass

    return " ".join(texts)


def _feature_mentioned_in_content(feature_name: str, content_text: str) -> bool:
    """Check if a feature group is substantively mentioned in content text."""
    # Build search terms from feature name
    terms = feature_name.replace("-", " ").split()
    # Also check for common variations
    aliases: dict[str, list[str]] = {
        "variable-fonts": ["variable font", "variable-font", "axes", "named instance",
                           "smart instancer", "fvar", "gvar", "hvar"],
        "subsetting": ["subset", "subsetting", "fontsubsetter"],
        "preview": ["preview", "specimen", "waterfall", "fontpreviewbuilder"],
        "animation": ["animation", "apng", "animationpreviewbuilder", "sweep"],
        "web-packaging": ["web font", "web-font", "webfontbuilder", "woff2 bundle",
                          "css generation", "web packaging"],
        "qa-compatibility": ["compatibility", "compatibilitychecker", "delta inspector",
                             "deltainspector", "interpolation"],
        "cli": ["command line", "command-line", "cli", "aspose-font info",
                "aspose-font convert"],
        "mcp-server": ["mcp server", "mcp", "ai client"],
    }

    # Check aliases first
    feature_aliases = aliases.get(feature_name, [])
    for alias in feature_aliases:
        if alias in content_text:
            return True

    # Check if ALL significant terms appear (for multi-word features)
    significant = [t for t in terms if len(t) > 3]
    if significant and all(t in content_text for t in significant):
        return True

    return False


# ---------------------------------------------------------------------------
# Feature-level candidate generation
# ---------------------------------------------------------------------------

def generate_feature_candidates(
    cluster: dict,
    feature_groups: list[dict],
    shallow_info: dict[str, dict],  # subdomain -> shallow coverage result
    existing_coverage: dict[str, str],  # subdomain -> coverage_status
) -> list[dict]:
    """Generate candidates for uncovered feature groups within covered clusters.

    Returns a list of candidate-like dicts for each uncovered high-value
    feature in subdomains where the parent cluster is marked 'covered'
    but coverage is actually shallow.
    """
    candidates: list[dict] = []

    for subdomain, info in shallow_info.items():
        if not info.get("is_shallow"):
            continue

        parent_status = existing_coverage.get(subdomain, "unknown")
        if parent_status not in ("covered", "partially_covered"):
            continue

        # Skip reference and products — no narrative content
        if subdomain in ("reference.aspose.org", "products.aspose.org"):
            continue

        for feature_name in info.get("uncovered_features", []):
            candidates.append({
                "cluster": cluster["category"],
                "feature_group": feature_name,
                "subdomain": subdomain,
                "candidate_type": "feature_gap",
                "parent_coverage": parent_status,
                "coverage_depth": info.get("coverage_depth", 0),
            })

    return candidates
