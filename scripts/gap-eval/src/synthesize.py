#!/usr/bin/env python3
"""S-45 gap-report — Cross-product findings synthesis.

Aggregates findings across all 11 products, clusters them using vector similarity,
names each cluster using LLM, and updates MASTER-SYNTHESIS.md.

Usage:
    python scripts/gap-eval/src/synthesize.py [--products all|{family}/{platform},...] [--dry-run]
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT / "scripts"))
sys.path.insert(0, str(_REPO_ROOT / "scripts" / "pipeline"))

from core.env_loader import load_env  # noqa: E402
load_env()

_REPORTS_DIR = _REPO_ROOT / "reports" / "gap-analysis"
_VECTORS_DIR = _REPO_ROOT / "knowledge" / "_vectors" / "_synthesis"
_SYNTHESIS_PATH = _REPO_ROOT / "reports" / "gap-analysis" / "MASTER-SYNTHESIS.md"

_router = None  # lazy singleton


def _get_router():
    """Return cached LLMRouter instance (lazy init)."""
    global _router
    if _router is None:
        from lib.llm_router import LLMRouter
        _router = LLMRouter()
    return _router


# ---------------------------------------------------------------------------
# Stage 1: Finding Aggregation
# ---------------------------------------------------------------------------

def load_all_findings(products: list[str] | None = None) -> list[dict]:
    """Load findings from all gap-analysis JSON files.

    Returns a flat list of findings, each tagged with {repo_key}.
    products: list of "family/platform" strings, or None for all.
    """
    all_findings: list[dict] = []
    json_files = sorted(_REPORTS_DIR.glob("*.json")) if _REPORTS_DIR.exists() else []

    for jf in json_files:
        repo_key = jf.stem  # e.g. "slides-java"
        if products:
            # Filter: convert "slides/java" to "slides-java"
            allowed = {p.replace("/", "-") for p in products}
            if repo_key not in allowed:
                continue
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
        except Exception as exc:
            log.warning("Cannot read %s: %s", jf, exc)
            continue
        for finding in data.get("findings", []):
            if finding.get("status") in ("fixed", "wontfix"):
                continue
            tagged = dict(finding)
            tagged["_repo"] = repo_key
            all_findings.append(tagged)

    log.info("Loaded %d open findings from %d repos", len(all_findings), len(json_files))
    return all_findings


# ---------------------------------------------------------------------------
# Stage 2: Embedding
# ---------------------------------------------------------------------------

def embed_findings(findings: list[dict]) -> dict[str, list[float]]:
    """Embed each finding's description for clustering.

    Returns {finding_key: vector}.
    Uses LLMRouter for provider routing (professionalize → Ollama fallback).
    Falls back to TF-IDF if no provider available.
    """
    texts: dict[str, str] = {}
    for f in findings:
        fid = f.get("id", "?")
        repo = f.get("_repo", "?")
        key = f"{repo}::{fid}"
        desc = f.get("description", "")
        ftype = f.get("type", "")
        sev = f.get("severity", "")
        texts[key] = f"[{repo}] {sev} {ftype}: {desc}"

    if not texts:
        return {}

    # Try embedding via LLMRouter
    try:
        from lib.llm_router import EndpointStatus as _ES
        router = _get_router()
    except (ImportError, RuntimeError) as exc:
        log.warning("LLM router unavailable for embedding: %s", exc)
        log.info("Using TF-IDF fallback for finding embedding")
        return _tfidf_embed(texts)

    keys = sorted(texts.keys())
    text_list = [texts[k] for k in keys]
    cr = router.call_embeddings(text_list, timeout=30)

    if cr.status == _ES.OK and cr.data and len(cr.data) == len(keys):
        result = {k: v for k, v in zip(keys, cr.data)}
        dims = len(cr.data[0]) if cr.data else 0
        # Write to synthesis vectors file with dimension metadata
        _VECTORS_DIR.mkdir(parents=True, exist_ok=True)
        out_path = _VECTORS_DIR / "findings.vectors.json"
        out_data = {
            "version": "1.0.0",
            "model": cr.model or "",
            "dimensions": dims,
            "provider": cr.provider or "",
            "count": len(result),
            "vectors": result,
        }
        out_path.write_text(
            json.dumps(out_data, separators=(",", ":")),
            encoding="utf-8",
        )
        log.info("Saved %d finding vectors (%d-dim) to %s", len(result), dims, out_path)
        return result

    log.warning("Embedding via LLMRouter failed (status=%s), falling back to TF-IDF", cr.status)
    return _tfidf_embed(texts)


def _tfidf_embed(texts: dict[str, str]) -> dict[str, list[float]]:
    """Compute sparse TF-IDF vectors as dense (fixed-vocab) float lists."""
    from commands.knowledge.embed import tokenize, compute_idf  # type: ignore

    tokenized = {k: tokenize(v) for k, v in texts.items()}
    idf = compute_idf(list(tokenized.values()))
    vocab = sorted(idf.keys())
    vocab_idx = {w: i for i, w in enumerate(vocab)}
    dim = len(vocab)
    if dim == 0:
        return {k: [] for k in texts}

    result: dict[str, list[float]] = {}
    for key, tokens in tokenized.items():
        from commands.knowledge.embed import compute_tf  # type: ignore
        tf = compute_tf(tokens)
        vec = [0.0] * dim
        for term, tf_val in tf.items():
            if term in vocab_idx:
                vec[vocab_idx[term]] = tf_val * idf.get(term, 0.0)
        # L2 normalise
        magnitude = math.sqrt(sum(v * v for v in vec))
        if magnitude > 0:
            vec = [v / magnitude for v in vec]
        result[key] = vec

    return result


# ---------------------------------------------------------------------------
# Stage 3: Clustering
# ---------------------------------------------------------------------------

def cosine_sim(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def kmeans_cluster(vectors: dict[str, list[float]], k: int = 6, max_iter: int = 30) -> dict[str, int]:
    """Simple K-means clustering.  Returns {key: cluster_id}."""
    import random

    if not vectors:
        return {}

    keys = list(vectors.keys())
    vecs = [vectors[k] for k in keys]
    n = len(vecs)
    k = min(k, n)

    # Initialise centroids by picking k random vectors
    rng = random.Random(42)  # deterministic seed
    centroid_indices = rng.sample(range(n), k)
    centroids = [list(vecs[i]) for i in centroid_indices]

    assignments: list[int] = [0] * n

    for _ in range(max_iter):
        # Assign each vector to nearest centroid
        changed = False
        for i, vec in enumerate(vecs):
            best_c = max(range(k), key=lambda c: cosine_sim(vec, centroids[c]))
            if best_c != assignments[i]:
                assignments[i] = best_c
                changed = True

        if not changed:
            break

        # Recompute centroids
        new_centroids: list[list[float]] = []
        dim = len(vecs[0]) if vecs else 0
        for c in range(k):
            members = [vecs[i] for i in range(n) if assignments[i] == c]
            if members:
                avg = [sum(v[d] for v in members) / len(members) for d in range(dim)]
            else:
                avg = centroids[c]  # keep old centroid if empty
            new_centroids.append(avg)
        centroids = new_centroids

    return {keys[i]: assignments[i] for i in range(n)}


def find_optimal_k(vectors: dict[str, list[float]], k_range: range) -> int:
    """Simple heuristic: try k values and pick the one with highest mean intra-cluster similarity."""
    best_k = k_range.start
    best_score = -1.0
    keys = list(vectors.keys())
    vecs = [vectors[k] for k in keys]

    for k in k_range:
        if k >= len(vecs):
            continue
        assignments = kmeans_cluster(vectors, k=k)
        # Compute mean intra-cluster cosine similarity
        cluster_members: dict[int, list[list[float]]] = {}
        for key, cid in assignments.items():
            cluster_members.setdefault(cid, []).append(vectors[key])
        scores: list[float] = []
        for members in cluster_members.values():
            if len(members) < 2:
                continue
            # Average pairwise similarity for the cluster
            total = sum(
                cosine_sim(members[i], members[j])
                for i in range(len(members))
                for j in range(i + 1, len(members))
            )
            n_pairs = len(members) * (len(members) - 1) / 2
            scores.append(total / n_pairs if n_pairs > 0 else 0.0)
        score = sum(scores) / len(scores) if scores else 0.0
        if score > best_score:
            best_score = score
            best_k = k

    return best_k


# ---------------------------------------------------------------------------
# Stage 3b: LLM pattern naming
# ---------------------------------------------------------------------------

def name_cluster(findings_in_cluster: list[dict]) -> dict:
    """Ask LLM to name this cluster of findings.

    Returns {"pattern_name": str, "description": str, "root_cause": str, "prevention": str}
    Uses LLMRouter for provider routing (professionalize → Ollama fallback).
    """
    # Build finding descriptions (max 2000 chars total)
    descriptions = []
    for f in findings_in_cluster[:20]:
        repo = f.get("_repo", "?")
        ftype = f.get("type", "?")
        desc = f.get("description", "")[:100]
        descriptions.append(f"[{repo}] {ftype}: {desc}")
    desc_text = "\n".join(descriptions)

    system = "You are a content quality analyst identifying patterns in documentation errors."
    user = (
        f"These {len(findings_in_cluster)} findings from multiple products cluster together:\n"
        f"{desc_text}\n\n"
        "Name this error pattern (3-6 words) and explain its root cause in 2 sentences.\n"
        'Output only valid JSON:\n'
        '{"pattern_name": "...", "description": "...", "root_cause": "...", "prevention": "..."}'
    )

    try:
        from lib.llm_router import EndpointStatus
        router = _get_router()
    except (ImportError, RuntimeError) as exc:
        log.warning("LLM router unavailable for cluster naming: %s", exc)
        return _fallback_cluster_name(findings_in_cluster)

    result = router.call_chat(
        system, user,
        temperature=0.3,
        timeout=30,
        json_extract=True,
        json_array=False,
    )

    if result.status == EndpointStatus.OK and isinstance(result.data, dict):
        if "pattern_name" in result.data:
            return result.data

    return _fallback_cluster_name(findings_in_cluster)


def _fallback_cluster_name(findings: list[dict]) -> dict:
    """Heuristic pattern name based on most common finding type."""
    from collections import Counter
    types = Counter(f.get("type", "unknown") for f in findings)
    most_common = types.most_common(1)[0][0] if types else "unknown"
    return {
        "pattern_name": f"Pattern: {most_common.replace('-', ' ').title()}",
        "description": f"Cluster of {len(findings)} findings of type '{most_common}'.",
        "root_cause": "LLM unavailable — heuristic cluster name assigned.",
        "prevention": "Enable LLM for pattern naming.",
    }


# ---------------------------------------------------------------------------
# Stage 4: Root cause analysis
# ---------------------------------------------------------------------------

def analyze_root_causes(patterns: list[dict]) -> list[dict]:
    """Ask LLM to identify systemic root causes across all patterns."""
    pattern_summaries = "\n".join(
        f"Pattern {i + 1}: {p['pattern_name']} ({p['count']} findings) — {p['description']}"
        for i, p in enumerate(patterns)
    )

    system = "You are a content quality analyst identifying systemic documentation quality issues."
    user = (
        "These error patterns were identified across multiple FOSS library documentation products:\n\n"
        f"{pattern_summaries}\n\n"
        "What systemic root causes explain these patterns? "
        "What pipeline changes would prevent recurrence?\n"
        'Output valid JSON:\n'
        '{"root_causes": [{"name": "...", "description": "...", "affected_patterns": [...], "system_fix": "..."}]}'
    )

    try:
        from lib.llm_router import EndpointStatus
        router = _get_router()
    except (ImportError, RuntimeError) as exc:
        log.warning("LLM router unavailable: %s", exc)
        return []

    result = router.call_chat(
        system, user,
        temperature=0.3,
        timeout=45,
        json_extract=True,
        json_array=False,
    )

    if result.status == EndpointStatus.OK and isinstance(result.data, dict):
        return result.data.get("root_causes", [])

    return []


# ---------------------------------------------------------------------------
# Stage 6: Report generation
# ---------------------------------------------------------------------------

def generate_synthesis_update(
    patterns: list[dict],
    root_causes: list[dict],
    findings: list[dict],
    repo_verdicts: dict[str, str],
) -> str:
    """Generate a MASTER-SYNTHESIS update section."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    total_findings = len(findings)
    repos_affected = len({f.get("_repo") for f in findings})

    lines = [
        f"## Synthesis Update — {today}",
        "",
        f"**Total open findings**: {total_findings} across {repos_affected} repos",
        "",
        "### Identified Patterns",
        "",
    ]

    for i, p in enumerate(patterns):
        lines += [
            f"#### Pattern {chr(65 + i)}: {p['pattern_name']}",
            f"- **Findings in cluster**: {p['count']}",
            f"- **Repos affected**: {', '.join(sorted(p.get('repos', [])))}",
            f"- **Description**: {p['description']}",
            f"- **Root cause**: {p['root_cause']}",
            f"- **Prevention**: {p['prevention']}",
            "",
        ]

    if root_causes:
        lines += ["### Systemic Root Causes", ""]
        for rc in root_causes:
            lines += [
                f"#### {rc['name']}",
                rc["description"],
                f"- **Affects patterns**: {', '.join(str(p) for p in rc.get('affected_patterns', []))}",
                f"- **System fix**: {rc['system_fix']}",
                "",
            ]

    lines += ["### Publish Sequence", ""]
    tier1 = [r for r, v in sorted(repo_verdicts.items()) if v == "PUBLICATION READY"]
    tier2 = [r for r, v in sorted(repo_verdicts.items()) if v == "CONDITIONAL"]
    tier3 = [r for r, v in sorted(repo_verdicts.items()) if v == "NOT PUBLISHABLE"]

    if tier1:
        lines.append(f"**Tier 1 — PUBLICATION READY**: {', '.join(tier1)}")
    if tier2:
        lines.append(f"**Tier 2 — CONDITIONAL**: {', '.join(tier2)}")
    if tier3:
        lines.append(f"**Tier 3 — NOT PUBLISHABLE**: {', '.join(tier3)}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main synthesis runner
# ---------------------------------------------------------------------------

def run_synthesis(
    products: list[str] | None = None,
    dry_run: bool = False,
    k: int | None = None,
) -> dict:
    """Run S-45 cross-product synthesis.

    Returns synthesis result dict.
    """
    # Stage 1: Aggregate
    findings = load_all_findings(products)
    if not findings:
        log.warning("No open findings found — synthesis has nothing to cluster")
        return {"patterns": [], "root_causes": [], "total_findings": 0}

    # Stage 2: Embed
    vectors = embed_findings(findings)
    if not vectors:
        log.warning("Embedding produced no vectors — using finding type as cluster key")
        # Degenerate clustering: group by finding type
        from collections import defaultdict
        by_type: dict[str, list[dict]] = defaultdict(list)
        for f in findings:
            by_type[f.get("type", "unknown")].append(f)
        assignments = {}
        type_to_id: dict[str, int] = {}
        for f in findings:
            ftype = f.get("type", "unknown")
            if ftype not in type_to_id:
                type_to_id[ftype] = len(type_to_id)
            repo = f.get("_repo", "?")
            fid = f.get("id", "?")
            assignments[f"{repo}::{fid}"] = type_to_id[ftype]
    else:
        # Stage 3: Cluster
        effective_k = k or find_optimal_k(vectors, range(3, min(10, len(vectors))))
        log.info("Clustering with k=%d", effective_k)
        assignments = kmeans_cluster(vectors, k=effective_k)

    # Group findings by cluster
    clusters: dict[int, list[dict]] = {}
    for f in findings:
        repo = f.get("_repo", "?")
        fid = f.get("id", "?")
        key = f"{repo}::{fid}"
        cid = assignments.get(key, 0)
        clusters.setdefault(cid, []).append(f)

    # Stage 3b: Name clusters with LLM
    patterns: list[dict] = []
    for cid in sorted(clusters.keys()):
        members = clusters[cid]
        named = name_cluster(members)
        named["id"] = cid
        named["count"] = len(members)
        named["repos"] = sorted({f.get("_repo", "?") for f in members})
        named["finding_types"] = sorted({f.get("type", "?") for f in members})
        patterns.append(named)
        log.info("Cluster %d (%d findings): %s", cid, len(members), named["pattern_name"])

    # Stage 4: Root causes
    root_causes = analyze_root_causes(patterns)

    # Stage 5: Publish sequence from state files
    repo_verdicts: dict[str, str] = {}
    state_dir = _REPO_ROOT / "reports" / "gap-analysis" / "state"
    if state_dir.exists():
        for sf in sorted(state_dir.glob("*.json")):
            try:
                state = json.loads(sf.read_text(encoding="utf-8"))
                repo_verdicts[sf.stem] = state.get("verdict", "UNKNOWN")
            except Exception:
                pass

    # Stage 6: Generate synthesis update
    synthesis_update = generate_synthesis_update(patterns, root_causes, findings, repo_verdicts)

    result = {
        "run_date": datetime.now(timezone.utc).isoformat(),
        "total_findings": len(findings),
        "patterns": patterns,
        "root_causes": root_causes,
        "repo_verdicts": repo_verdicts,
        "synthesis_update": synthesis_update,
    }

    if not dry_run:
        # Save synthesis result JSON
        out_dir = _REPO_ROOT / "reports" / "gap-analysis"
        out_dir.mkdir(parents=True, exist_ok=True)
        result_path = out_dir / "synthesis_result.json"
        result_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        log.info("Synthesis result written to %s", result_path)

        # Append synthesis update to MASTER-SYNTHESIS.md
        if _SYNTHESIS_PATH.exists():
            existing = _SYNTHESIS_PATH.read_text(encoding="utf-8")
            # Append after the last section
            updated = existing.rstrip() + "\n\n---\n\n" + synthesis_update + "\n"
            _SYNTHESIS_PATH.write_text(updated, encoding="utf-8")
            log.info("MASTER-SYNTHESIS.md updated")
        else:
            log.warning("MASTER-SYNTHESIS.md not found at %s — synthesis update not appended", _SYNTHESIS_PATH)

    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="S-45: Cross-product gap synthesis")
    parser.add_argument(
        "--products",
        default="all",
        help='Comma-separated list of "family/platform" or "all" (default: all)',
    )
    parser.add_argument("--k", type=int, default=None, help="Override cluster count k")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    products = None if args.products.lower() == "all" else args.products.split(",")
    result = run_synthesis(products=products, dry_run=args.dry_run, k=args.k)

    log.info(
        "Synthesis complete: %d findings, %d patterns, %d root causes",
        result["total_findings"],
        len(result["patterns"]),
        len(result["root_causes"]),
    )


if __name__ == "__main__":
    main()
