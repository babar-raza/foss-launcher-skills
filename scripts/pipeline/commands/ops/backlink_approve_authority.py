"""
backlink_approve_authority.py — Layer 3 (Approved Backlink Authority)

Reads Layer 2 (candidate_graph.json) and writes exactly ONE canonical target
per (source_key, link_slot), or BLOCKED, for each source page.

Confidence bands:
  AUTO_APPROVE_EXACT (AAE): score ≥ 0.90, Stage 1 only
  REVIEW_REQUIRED (RR):     0.50–0.89 (all Stage 2/3, near-misses, tie < 0.10)
  BLOCKED (BLK):            < 0.50; AI-only; wrong namespace; blog; cross-platform

Authority records include anchor provenance:
  anchor_template_id, anchor_config_hash, rendered_anchor_text

Output: data/backlinks/workspace/backlink_authority.json (gitignored)

Usage:
    .venv/Scripts/python backlink_approve_authority.py --auto-only [--family 3d] [--platform java]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "pipeline"))

from lib.backlink_targets import (
    PLATFORM_ALIASES,
    compute_anchor_config_hash,
    load_anchor_registry,
    render_anchor_text,
    select_anchor_template_id,
)

CANDIDATE_GRAPH_PATH = REPO_ROOT / "data" / "backlinks" / "workspace" / "candidate_graph.json"
AUTHORITY_PATH = REPO_ROOT / "data" / "backlinks" / "workspace" / "backlink_authority.json"
FAMILIES_PATH = REPO_ROOT / "data" / "families.json"
METRICS_TAXONOMY_PATH = REPO_ROOT / "scripts" / "pipeline" / "config" / "metrics_taxonomy.yaml"

POLICY_VERSION = "1.0.0"
THRESHOLD_AUTO_APPROVE_EXACT = 0.90
STALENESS_STALE_DAYS = 180
STALENESS_AGING_DAYS = 90


# ── Display name helpers ───────────────────────────────────────────────────────

def _load_families_map() -> dict:
    """Load data/families.json → {family_key: display_name}."""
    if FAMILIES_PATH.exists():
        raw = json.loads(FAMILIES_PATH.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            return {item["key"]: item.get("title", item["key"].title()) for item in raw if "key" in item}
        if isinstance(raw, dict):
            return raw
    return {}


def _load_platforms_map() -> dict:
    """Load metrics_taxonomy.yaml platforms block → {platform_key: display_name}."""
    if METRICS_TAXONOMY_PATH.exists():
        try:
            import yaml
            data = yaml.safe_load(METRICS_TAXONOMY_PATH.read_text(encoding="utf-8")) or {}
            return data.get("platforms", {})
        except Exception:
            pass
    # Minimal fallback
    return {
        "net": ".NET", "java": "Java", "cpp": "C++", "python": "Python",
        "nodejs": "Node.js", "go": "Go", "android": "Android", "php": "PHP",
        "ruby": "Ruby",
    }


# ── Source-key hashing ─────────────────────────────────────────────────────────

def _compute_source_hash(source: dict) -> str:
    """Compute a stable hash for a source record (based on source_key + source_path)."""
    canonical = json.dumps({
        "source_key": source.get("source_key", ""),
        "source_path": source.get("source_path", ""),
    }, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _compute_target_index_hash(candidate_graph: dict) -> str:
    """Derive target_index_hash from deep_index_hash stored in candidate_graph."""
    return candidate_graph.get("deep_index_hash", "sha256:unknown")


# ── Core approval logic ────────────────────────────────────────────────────────

def approve_candidates(
    candidate_graph: dict,
    *,
    auto_only: bool = True,
    families_filter: Optional[list] = None,
    anchor_registry: Optional[dict] = None,
    families_map: Optional[dict] = None,
    platforms_map: Optional[dict] = None,
) -> dict:
    """
    Build Layer 3 approved backlink authority from Layer 2 candidate graph.

    Pure business logic — no I/O.

    Returns: {
        "authority": {source_path: authority_record},
        "stats": {...}
    }
    """
    if families_map is None:
        families_map = {}
    if platforms_map is None:
        platforms_map = {}

    anchor_config_hash = None
    if anchor_registry is not None:
        # Compute hash inline from registry content
        try:
            anchor_config_hash = compute_anchor_config_hash()
        except Exception:
            anchor_config_hash = "sha256:unavailable"

    target_index_hash = _compute_target_index_hash(candidate_graph)
    sources_index = {s["source_path"]: s for s in candidate_graph.get("sources", [])}

    # Group candidates by source_path
    from collections import defaultdict
    by_source: dict = defaultdict(list)
    for c in candidate_graph.get("candidates", []):
        # Look up source_path from source_key
        source_key = c.get("source_key", "")
        source = next((s for s in candidate_graph.get("sources", []) if s.get("source_key") == source_key), None)
        if source is None:
            continue
        source_path = source.get("source_path", "")
        by_source[source_path].append(c)

    authority: dict = {}
    approved_count = 0
    review_count = 0
    blocked_count = 0

    for source_path, candidates in by_source.items():
        source = sources_index.get(source_path)
        if source is None:
            continue

        family = source.get("family", "")
        platform = source.get("platform") or ""
        if families_filter and family not in families_filter:
            continue

        # Sort by final_score descending
        sorted_candidates = sorted(candidates, key=lambda x: -x.get("final_score", 0.0))

        if not sorted_candidates:
            continue

        top = sorted_candidates[0]
        decision = top.get("decision", "BLOCKED")

        # In auto-only mode, skip REVIEW_REQUIRED and BLOCKED
        if auto_only and decision != "AUTO_APPROVE_EXACT":
            review_count += 1 if decision == "REVIEW_REQUIRED" else 0
            blocked_count += 1 if decision == "BLOCKED" else 0
            authority[source_path] = {
                "source_path": source_path,
                "source_key": source.get("source_key", ""),
                "family": family,
                "platform": platform,
                "target_path": top.get("target_path", ""),
                "decision": decision,
                "score": top.get("final_score", 0.0),
                "allowed_for_generation": False,
                "anchor_template_id": None,
                "anchor_config_hash": None,
                "rendered_anchor_text": None,
                "rendered_anchor_source": None,
                "source_hash": _compute_source_hash(source),
                "target_index_hash": target_index_hash,
                "policy_version": POLICY_VERSION,
                "approved_at": datetime.now(timezone.utc).isoformat(),
                "freshness_status": "FRESH",
            }
            continue

        if decision == "AUTO_APPROVE_EXACT":
            raw_target_path = top.get("target_path", "")
            # Determine target_subdomain from source subdomain
            target_subdomain = _infer_subdomain(source.get("subdomain", ""), raw_target_path)
            # Strip subdomain prefix from target_path if present
            # (deep index stores "reference/3d/java/..." but authority should store "3d/java/...")
            sd_prefix = target_subdomain + "/"
            if raw_target_path.startswith(sd_prefix):
                target_path = raw_target_path[len(sd_prefix):]
            else:
                target_path = raw_target_path

            # Compute anchor
            rendered_anchor = None
            template_id = None
            rendered_source = None
            if anchor_registry is not None:
                try:
                    # Use canonical platform (not bridge slug)
                    canonical_plat = PLATFORM_ALIASES.get(platform, platform) if platform else platform
                    # Compose target_url for template selection (uses stripped path)
                    target_url = f"https://{_SUBDOMAIN_TO_HOST.get(target_subdomain, 'reference.aspose.com')}/{target_path}/"
                    # Infer target type from stripped path
                    target_type = _infer_target_type(target_path, target_subdomain)
                    template_id = select_anchor_template_id(
                        target_url,
                        target_type,
                        source.get("subdomain", ""),
                    )
                    rendered_anchor = render_anchor_text(
                        template_id=template_id,
                        family=family,
                        platform=canonical_plat or None,
                        target_url=target_url,
                        registry=anchor_registry,
                        families_map=families_map,
                        platforms_map=platforms_map,
                    )
                    rendered_source = f"anchor_text_registry.yaml:templates.{template_id}"
                except Exception as exc:
                    rendered_anchor = f"Aspose.{family.title()} — Enterprise Reference"
                    rendered_source = f"fallback:{exc}"

            authority[source_path] = {
                "source_path": source_path,
                "source_key": source.get("source_key", ""),
                "family": family,
                "platform": platform,
                "target_path": target_path,
                "target_subdomain": target_subdomain,
                "decision": decision,
                "score": top.get("final_score", 0.0),
                "stage1_score": top.get("stage1_score", 0.0),
                "ai_boost": top.get("ai_boost", 0.0),
                "allowed_for_generation": True,
                "anchor_template_id": template_id,
                "anchor_config_hash": anchor_config_hash,
                "rendered_anchor_text": rendered_anchor,
                "rendered_anchor_source": rendered_source,
                "source_hash": _compute_source_hash(source),
                "target_index_hash": target_index_hash,
                "policy_version": POLICY_VERSION,
                "approved_at": datetime.now(timezone.utc).isoformat(),
                "freshness_status": "FRESH",
            }
            approved_count += 1

    return {
        "authority": authority,
        "stats": {
            "approved_count": approved_count,
            "review_count": review_count,
            "blocked_count": blocked_count,
            "total_sources": len(by_source),
        },
    }


_SUBDOMAIN_TO_HOST = {
    "reference": "reference.aspose.com",
    "kb": "kb.aspose.com",
    "docs": "docs.aspose.com",
    "products": "products.aspose.com",
    "blog": "blog.aspose.com",
}

_SOURCE_SD_TO_TARGET_SD = {
    "reference.aspose.org": "reference",
    "kb.aspose.org": "kb",
    "docs.aspose.org": "docs",
    "products.aspose.org": "products",
    "blog.aspose.org": "blog",
}


def _infer_subdomain(source_subdomain: str, target_path: str) -> str:
    """Infer target subdomain from source subdomain."""
    return _SOURCE_SD_TO_TARGET_SD.get(source_subdomain, "reference")


def _infer_target_type(target_path: str, subdomain: str) -> str:
    """Infer target type from path depth and subdomain."""
    parts = target_path.strip("/").split("/")
    # e.g. "3d/java/com.aspose.threed/a3dobject" → 4 segments → reference_class
    if subdomain == "reference":
        if len(parts) >= 4:
            return "reference_class"
        if len(parts) >= 3:
            return "reference_namespace"
        return "platform_landing"
    if subdomain == "kb":
        if len(parts) >= 3:
            return "kb_article"
        return "platform_landing"
    return "platform_landing"


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build approved backlink authority (Layer 3)"
    )
    parser.add_argument("--auto-only", action="store_true", default=True,
                        help="Only include AUTO_APPROVE_EXACT decisions (default: True)")
    parser.add_argument("--family", default=None, help="Filter by family (e.g., 3d)")
    parser.add_argument("--platform", default=None, help="Filter by platform (e.g., java)")
    parser.add_argument("--candidate-graph", default=str(CANDIDATE_GRAPH_PATH))
    parser.add_argument("--output", default=str(AUTHORITY_PATH))
    parser.add_argument("--dry-run", action="store_true",
                        help="Print stats without writing output")
    args = parser.parse_args()

    graph_path = Path(args.candidate_graph)
    if not graph_path.exists():
        print(f"ERROR: candidate_graph.json not found at {graph_path}", file=sys.stderr)
        print("Run backlink_build_candidates.py first.", file=sys.stderr)
        sys.exit(1)

    print(f"Loading Layer 2 from {graph_path} ...")
    candidate_graph = json.loads(graph_path.read_text(encoding="utf-8"))
    print(f"Layer 2: {candidate_graph.get('stats', {}).get('total_candidates', '?')} candidates "
          f"across {candidate_graph.get('stats', {}).get('total_sources', '?')} sources")

    # Load anchor registry
    anchor_registry = None
    try:
        anchor_registry = load_anchor_registry()
        print("Anchor text registry loaded.")
    except FileNotFoundError:
        print("WARNING: anchor_text_registry.yaml not found — anchors will use fallback wording.")

    families_map = _load_families_map()
    platforms_map = _load_platforms_map()

    families_filter = [args.family] if args.family else None
    print(f"Building authority (auto-only={args.auto_only}, family={args.family or 'all'}) ...")

    result = approve_candidates(
        candidate_graph,
        auto_only=args.auto_only,
        families_filter=families_filter,
        anchor_registry=anchor_registry,
        families_map=families_map,
        platforms_map=platforms_map,
    )
    stats = result["stats"]

    print(f"Authority: {stats['approved_count']} approved, "
          f"{stats['review_count']} review, {stats['blocked_count']} blocked")
    print(f"Total sources processed: {stats['total_sources']}")

    if args.dry_run:
        print("Dry-run: output not written.")
        return

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    output = {
        "schema_version": "1.0.0",
        "family": args.family,
        "platform": args.platform,
        "policy_version": POLICY_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "stats": stats,
        "authority": result["authority"],
    }

    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Written: {out_path}")


if __name__ == "__main__":
    main()
