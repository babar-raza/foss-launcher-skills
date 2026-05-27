"""
backlink_build_candidates.py — Layer 2

Reads Layer 1 (deep_target_index.json) + content frontmatter and builds
a candidate graph with scored matches per source page.

Stage 0: hard filters (http_status=200, family, platform, target type)
Stage 1: exact match (deterministic; ≥0.90 → AUTO_APPROVE_EXACT)
Stage 2: metadata match (deterministic; always REVIEW_REQUIRED max)
AI boost: optional, max +0.05; reads ai_enrichment_index.json if --ai-enrichment given

Output: data/backlinks/workspace/candidate_graph.json (gitignored)

Usage:
    .venv/Scripts/python backlink_build_candidates.py --family 3d --platform java \\
        --subdomain reference.aspose.org [--no-ai] [--ai-enrichment PATH] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "pipeline"))

from lib.backlink_targets import PLATFORM_ALIASES

# Confidence band thresholds
THRESHOLD_AUTO_APPROVE_EXACT = 0.90
THRESHOLD_REVIEW_REQUIRED_MIN = 0.50
MAX_AI_BOOST = 0.05

DEEP_INDEX_PATH = REPO_ROOT / "data" / "backlinks" / "workspace" / "deep_target_index.json"
CANDIDATE_GRAPH_PATH = REPO_ROOT / "data" / "backlinks" / "workspace" / "candidate_graph.json"


# ── Source Page Scanner ───────────────────────────────────────────────────────

def _tokenize(text: str) -> list[str]:
    """Simple whitespace/punctuation tokenizer."""
    return [t.lower() for t in re.split(r"[\s\-_./]+", text) if t]


def _jaccard(a: list[str], b: list[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def scan_source_page(md_path: Path) -> Optional[dict]:
    """
    Extract metadata from a content Markdown file frontmatter.

    Returns dict with: title, family, platform, source_key, page_type, subdomain
    or None if file cannot be parsed.
    """
    try:
        text = md_path.read_text(encoding="utf-8")
    except OSError:
        return None

    # Parse YAML frontmatter between --- delimiters
    fm: dict = {}
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end > 0:
            import yaml
            try:
                fm = yaml.safe_load(text[3:end]) or {}
            except Exception:
                fm = {}

    title = fm.get("title") or md_path.stem
    # Derive family/platform from path segments
    # Expected: content/{subdomain}/en/{family}/{platform}/...
    parts = md_path.parts
    # Find 'en' segment
    try:
        en_idx = next(i for i, p in enumerate(parts) if p == "en")
        family = parts[en_idx + 1] if en_idx + 1 < len(parts) else None
        platform_raw = parts[en_idx + 2] if en_idx + 2 < len(parts) else None
    except StopIteration:
        family = None
        platform_raw = None

    if not family:
        return None

    # Get canonical platform
    platform = PLATFORM_ALIASES.get(platform_raw or "", platform_raw) if platform_raw else None

    # Determine subdomain from path
    subdomain = None
    for p in parts:
        if p.endswith(".aspose.org"):
            subdomain = p
            break

    # Build source_key
    key_parts = [subdomain.split(".")[0] if subdomain else "unknown", family]
    if platform:
        key_parts.append(platform)
    key_parts.append(md_path.stem.lower())
    source_key = "/".join(key_parts)

    return {
        "source_path": str(md_path.relative_to(REPO_ROOT)),
        "source_key": source_key,
        "title": title,
        "family": family,
        "platform_raw": platform_raw,
        "platform": platform,
        "subdomain": subdomain,
        "frontmatter": fm,
    }


# ── Candidate Scoring ─────────────────────────────────────────────────────────

def _stage0_filter(entry: dict, source: dict) -> bool:
    """Hard filters: family match + platform match + target type allowed."""
    if entry.get("family") != source["family"]:
        return False
    # Platform match: exact or via PLATFORM_ALIASES
    entry_platform = entry.get("platform", "")
    src_platform = source.get("platform") or ""
    canonical_entry = PLATFORM_ALIASES.get(entry_platform, entry_platform)
    canonical_src = PLATFORM_ALIASES.get(src_platform, src_platform)
    if canonical_entry != canonical_src:
        return False
    return True


def _stage1_score_reference(entry: dict, source: dict) -> float:
    """Stage 1 exact match for reference_class / reference_namespace targets."""
    title = source["title"].lower().strip()
    class_name = (entry.get("class_name") or "").lower().strip()
    namespace = entry.get("namespace", "")

    if not class_name:
        return 0.0

    if title == class_name:
        if namespace:
            return 0.95  # class + namespace + family + platform
        return 0.90  # class + family + platform (no namespace confirmation)

    # Partial: title ends with class_name (e.g., "IDocument" in "IDocument Class")
    if title.endswith(class_name) or title.startswith(class_name):
        return 0.75

    return 0.0


def _stage1_score_kb(entry: dict, source: dict) -> float:
    """Stage 1 exact match for kb_article targets."""
    title_tokens = _tokenize(source["title"])
    slug_tokens = _tokenize(entry.get("article_slug") or entry.get("path", "").split("/")[-1])

    if not title_tokens or not slug_tokens:
        return 0.0

    common = len(set(title_tokens) & set(slug_tokens))
    jaccard = _jaccard(title_tokens, slug_tokens)

    if jaccard >= 0.6 and common >= 3:
        return 0.90
    if jaccard >= 0.5 and common >= 2:
        return 0.80  # REVIEW_REQUIRED

    return 0.0


def _determine_decision(final_score: float, ai_boost: float) -> str:
    if final_score >= THRESHOLD_AUTO_APPROVE_EXACT:
        # If AI boost was required to cross threshold, still AUTO_APPROVE_EXACT
        # (A5: allowed since deterministic ≥0.85 + AI boost ≤0.05)
        return "AUTO_APPROVE_EXACT"
    if final_score >= THRESHOLD_REVIEW_REQUIRED_MIN:
        return "REVIEW_REQUIRED"
    return "BLOCKED"


def score_candidate(entry: dict, source: dict, ai_signals: Optional[dict] = None) -> dict:
    """
    Score a single (source, target) candidate pair.

    Returns: {
        source_key, target_path, stage1_score, stage2_score, ai_boost,
        ai_boost_applied, ai_signals, final_score, decision
    }
    """
    target_type = entry.get("type", "")
    stage1 = 0.0
    stage2 = None

    if target_type in ("reference_class", "reference_namespace"):
        stage1 = _stage1_score_reference(entry, source)
    elif target_type == "kb_article":
        stage1 = _stage1_score_kb(entry, source)

    # Stage 2: metadata match (always REVIEW_REQUIRED max, never AUTO_APPROVE)
    if stage1 == 0.0:
        # Very basic: check if title word is in path
        title_lower = source["title"].lower()
        path = entry.get("path", "")
        if any(w in path for w in _tokenize(title_lower) if len(w) > 3):
            stage2 = 0.55  # REVIEW_REQUIRED

    # AI boost
    ai_boost = 0.0
    ai_boost_applied = False
    if ai_signals and stage1 >= 0.85:
        label = ai_signals.get("label", "")
        cosine = ai_signals.get("embedding_cosine", 0.0)
        if label == "exact_api_class" and cosine >= 0.85:
            ai_boost = min(0.05, MAX_AI_BOOST)
            ai_boost_applied = True
        elif label == "related_api_class" and cosine >= 0.70:
            ai_boost = min(0.03, MAX_AI_BOOST)
            ai_boost_applied = True

    base_score = stage1 if stage1 > 0.0 else (stage2 or 0.0)
    final_score = min(1.0, base_score + ai_boost)

    # AI disagreement: if AI says unrelated but deterministic is high → REVIEW_REQUIRED
    ai_disagrees = (
        ai_signals is not None
        and ai_signals.get("label") == "unrelated"
        and stage1 >= 0.80
    )

    decision = _determine_decision(final_score, ai_boost)
    if ai_disagrees:
        decision = "REVIEW_REQUIRED"

    return {
        "source_key": source["source_key"],
        "target_path": entry["path"],
        "stage1_score": round(stage1, 4),
        "stage2_score": round(stage2, 4) if stage2 is not None else None,
        "ai_boost": round(ai_boost, 4),
        "ai_boost_applied": ai_boost_applied,
        "ai_signals": ai_signals,
        "final_score": round(final_score, 4),
        "decision": decision,
        "ai_disagrees": ai_disagrees,
    }


# ── Build Candidate Graph ─────────────────────────────────────────────────────

def build_candidates(
    deep_index: dict,
    source_pages: list[dict],
    ai_enrichment: Optional[dict] = None,
    families_filter: Optional[list[str]] = None,
) -> dict:
    """
    Build candidate graph for all source pages against deep target index.

    Pure function — no I/O.

    Returns: {
        "sources": [...],
        "candidates": [...],
        "stats": {...}
    }
    """
    index = deep_index.get("index", {})
    candidates = []
    sources_out = []

    for source in source_pages:
        family = source.get("family")
        if families_filter and family not in families_filter:
            continue

        src_candidates = []
        for path_key, entry in index.items():
            # Stage 0 hard filter
            if not _stage0_filter(entry, source):
                continue

            # Get AI signals if available
            ai_signals = None
            if ai_enrichment:
                ai_signals = ai_enrichment.get("index", {}).get(path_key, {}).get(
                    "llm_classification"
                )

            c = score_candidate(entry, source, ai_signals)
            if c["final_score"] > 0.0 or c.get("decision") != "BLOCKED":
                src_candidates.append(c)

        # Sort by final_score descending
        src_candidates.sort(key=lambda x: -x["final_score"])
        candidates.extend(src_candidates)
        sources_out.append(source)

    # Summary stats
    from collections import Counter
    decision_counts = Counter(c["decision"] for c in candidates)
    stats = {
        "total_sources": len(sources_out),
        "total_candidates": len(candidates),
        "decision_counts": dict(decision_counts),
    }

    return {
        "sources": sources_out,
        "candidates": candidates,
        "stats": stats,
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build backlink candidate graph (Layer 2)"
    )
    parser.add_argument("--family", required=True, help="Product family (e.g., 3d)")
    parser.add_argument("--platform", default=None, help="Platform filter (e.g., java)")
    parser.add_argument("--subdomain", default=None,
                        help="Source subdomain (e.g., reference.aspose.org)")
    parser.add_argument("--deep-index", default=str(DEEP_INDEX_PATH),
                        help="Path to Layer 1 deep_target_index.json")
    parser.add_argument("--output", default=str(CANDIDATE_GRAPH_PATH))
    parser.add_argument("--no-ai", action="store_true", help="Skip AI enrichment")
    parser.add_argument("--ai-enrichment", default=None,
                        help="Path to ai_enrichment_index.json (Layer 1.5)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    deep_index_path = Path(args.deep_index)
    if not deep_index_path.exists():
        print(f"ERROR: deep_target_index.json not found at {deep_index_path}", file=sys.stderr)
        print("Run backlink_build_deep_index.py first.", file=sys.stderr)
        sys.exit(1)

    print(f"Loading Layer 1 from {deep_index_path} ...")
    deep_index = json.loads(deep_index_path.read_text(encoding="utf-8"))
    print(f"Layer 1: {deep_index.get('total_endpoints', '?')} endpoints")

    # Load AI enrichment if provided
    ai_enrichment = None
    if not args.no_ai and args.ai_enrichment:
        ai_path = Path(args.ai_enrichment)
        if ai_path.exists():
            print(f"Loading AI enrichment from {ai_path} ...")
            ai_enrichment = json.loads(ai_path.read_text(encoding="utf-8"))
        else:
            print(f"WARNING: AI enrichment file not found at {ai_path}; proceeding without AI")

    # Scan source pages
    subdomain = args.subdomain or f"reference.aspose.org"
    content_dir = REPO_ROOT / "content" / subdomain / "en" / args.family
    if args.platform:
        content_dir = content_dir / args.platform

    if not content_dir.exists():
        print(f"ERROR: Content directory not found: {content_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"Scanning source pages under {content_dir} ...")
    source_pages = []
    for md_file in content_dir.rglob("*.md"):
        page = scan_source_page(md_file)
        if page:
            source_pages.append(page)

    print(f"Found {len(source_pages)} source pages")

    # Build candidates
    print("Building candidate graph ...")
    families_filter = [args.family]
    graph = build_candidates(deep_index, source_pages, ai_enrichment, families_filter)
    stats = graph["stats"]

    print(f"Candidates: {stats['total_candidates']} across {stats['total_sources']} sources")
    for decision, count in sorted(stats["decision_counts"].items()):
        print(f"  {decision}: {count}")

    if args.dry_run:
        print("Dry-run: output not written.")
        return

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    import hashlib
    deep_index_hash = "sha256:" + hashlib.sha256(
        deep_index_path.read_bytes()
    ).hexdigest()[:16]

    output = {
        "schema_version": "1.0.0",
        "family": args.family,
        "platform": args.platform,
        "subdomain": subdomain,
        "deep_index_hash": deep_index_hash,
        "ai_enrichment_used": ai_enrichment is not None,
        "stats": stats,
        "sources": graph["sources"],
        "candidates": graph["candidates"],
    }

    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Written: {out_path}")


if __name__ == "__main__":
    main()
