"""delta_adapter.py — Knowledge delta adapter for update_existing candidates.

TC-CE-024: Converts S-98 enrichment manifest candidates into structured
page-update input by combining the manifest candidate with knowledge artifacts
(knowledge_delta.json, claims.json) and the target page's current evidence.

Does NOT write content. Produces a JSON artifact consumed by S-20/page-update.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

_THIS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _THIS_DIR.parents[3]


def _load_json(path: Path) -> dict | list:
    """Load a JSON file, return empty dict if missing."""
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _extract_evidence(text: str) -> dict:
    """Extract the evidence block from YAML frontmatter."""
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    try:
        fm = yaml.safe_load(text[3:end])
    except yaml.YAMLError:
        return {}
    return fm.get("evidence", {}) if isinstance(fm, dict) else {}


def _sha256_str(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()[:12]


def resolve_target_file(
    candidate: dict,
    family: str,
    platform: str,
    *,
    repo_root: Path | None = None,
) -> str | None:
    """Resolve the actual content file path for an update_existing candidate.

    Tries template-based path, then falls back to glob search.
    Returns repo-relative path or None if not found.
    """
    root = repo_root or _REPO_ROOT
    subdomain = candidate.get("subdomain", "")
    cluster = candidate.get("cluster", "")

    # Template-based search patterns by subdomain
    search_dirs: dict[str, Path] = {
        "docs.aspose.org": root / "content" / "docs.aspose.org" / "en" / family / platform,
        "kb.aspose.org": root / "content" / "kb.aspose.org" / "en" / family / platform,
        "blog.aspose.org": root / "content" / "blog.aspose.org" / family / platform,
    }

    search_dir = search_dirs.get(subdomain)
    if not search_dir or not search_dir.exists():
        return None

    # Look for files matching the cluster name
    cluster_slug = cluster.replace("_", "-").replace(" ", "-").lower()
    candidates_found: list[Path] = []

    for md_file in search_dir.rglob("*.md"):
        if md_file.name == "_index.md":
            continue
        stem = md_file.stem.lower()
        if cluster_slug in stem or stem in cluster_slug:
            candidates_found.append(md_file)

    if len(candidates_found) == 1:
        return str(candidates_found[0].relative_to(root))

    # Multiple matches — prefer exact stem match
    for f in candidates_found:
        if f.stem.lower() == cluster_slug:
            return str(f.relative_to(root))

    # If blog, look in subdirectories
    if subdomain == "blog.aspose.org":
        for d in search_dir.iterdir():
            if d.is_dir() and cluster_slug in d.name.lower():
                idx = d / "index.md"
                if idx.exists():
                    return str(idx.relative_to(root))

    return str(candidates_found[0].relative_to(root)) if candidates_found else None


def build_delta(
    candidate: dict,
    family: str,
    platform: str,
    *,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Build a structured page-update delta for one update_existing candidate.

    Returns a dict suitable for writing as JSON. Returns error info if
    target cannot be resolved or knowledge artifacts are missing.
    """
    root = repo_root or _REPO_ROOT
    knowledge_dir = root / "knowledge" / family / platform / "merged"

    # Load knowledge artifacts
    knowledge_delta = _load_json(knowledge_dir / "knowledge_delta.json")
    claims = _load_json(knowledge_dir / "claims.json")

    # Resolve target file
    target_rel = resolve_target_file(candidate, family, platform, repo_root=root)
    if not target_rel:
        return {
            "error": "target_not_resolved",
            "message": f"Could not resolve target file for cluster={candidate.get('cluster')} "
                       f"subdomain={candidate.get('subdomain')}",
            "candidate_ref": candidate,
        }

    target_abs = root / target_rel
    if not target_abs.exists():
        return {
            "error": "target_not_found",
            "message": f"Resolved target does not exist: {target_rel}",
            "candidate_ref": candidate,
        }

    # Read page evidence
    page_text = target_abs.read_text(encoding="utf-8")
    page_evidence = _extract_evidence(page_text)

    # Build claim-level delta
    new_claims = knowledge_delta.get("new_claims", [])
    removed_claims = knowledge_delta.get("removed_claims", [])
    modified_claims = knowledge_delta.get("modified_claims", [])
    new_apis = knowledge_delta.get("new_apis", [])
    removed_apis = knowledge_delta.get("removed_apis", [])

    # Page's current references
    current_claims = page_evidence.get("claims", [])
    current_apis = page_evidence.get("apis", [])
    model_sha = page_evidence.get("model_sha", "")

    # Feature gap info (if present on candidate)
    feature_gap: dict[str, Any] | None = None
    feature_group = candidate.get("feature_group", "")
    if feature_group:
        feature_gap = {
            "feature_group": feature_group,
            "uncovered_apis": candidate.get("uncovered_apis", []),
            "uncovered_claims": candidate.get("uncovered_claims", []),
            "coverage_depth": candidate.get("coverage_depth", 0),
        }

    # Compute delta SHA for provenance
    delta_text = json.dumps(knowledge_delta, sort_keys=True)
    delta_sha = _sha256_str(delta_text)

    run_id = f"delta-adapt-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"

    return {
        "adapter_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "family": family,
        "platform": platform,
        "target_file": target_rel,
        "candidate_ref": {
            "cluster": candidate.get("cluster", ""),
            "subdomain": candidate.get("subdomain", ""),
            "action": candidate.get("action", ""),
            "score": candidate.get("score", 0),
        },
        "delta": {
            "new_claims": new_claims[:50] if len(new_claims) > 50 else new_claims,
            "new_claims_total": len(new_claims),
            "removed_claims": removed_claims,
            "modified_claims": modified_claims,
            "new_apis": new_apis[:50] if len(new_apis) > 50 else new_apis,
            "new_apis_total": len(new_apis) if isinstance(new_apis, list) else 0,
            "removed_apis": removed_apis,
        },
        "feature_gap": feature_gap,
        "page_context": {
            "current_claims": current_claims,
            "current_apis": current_apis,
            "model_sha": model_sha,
        },
        "provenance": {
            "knowledge_delta_sha": delta_sha,
            "adapter_run_id": run_id,
        },
    }


def write_delta(
    delta: dict[str, Any],
    family: str,
    platform: str,
    *,
    repo_root: Path | None = None,
) -> Path:
    """Write delta artifact to reports/enrichment/{family}/{platform}/delta-adapt/.

    Returns path to the written file.
    """
    root = repo_root or _REPO_ROOT
    out_dir = root / "reports" / "enrichment" / family / platform / "delta-adapt"
    out_dir.mkdir(parents=True, exist_ok=True)

    target_file = delta.get("target_file", "unknown")
    slug = Path(target_file).stem if target_file != "unknown" else "unknown"
    out_path = out_dir / f"{slug}.json"
    out_path.write_text(json.dumps(delta, indent=2) + "\n", encoding="utf-8")
    return out_path
