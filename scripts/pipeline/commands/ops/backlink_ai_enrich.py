"""
backlink_ai_enrich.py — Layer 1.5 (AI Advisory Enrichment)

Reads Layer 1 (deep_target_index.json) + content frontmatter, calls LLMRouter
for embeddings (CS-011: qwen3-embedding-8b) and classification (CS-012: gpt-oss),
and writes an advisory enrichment index.

BOUNDARY INVARIANT:
  - Output is advisory only; NEVER read by resolver or backfill
  - Only backlink_build_candidates.py reads this file (via --ai-enrichment flag)
  - AI unavailability → graceful skip; pipeline continues with stage1+2 scoring only

Output: data/backlinks/workspace/ai_enrichment_index.json (gitignored)

Usage:
    .venv/Scripts/python backlink_ai_enrich.py --family 3d --platform java [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "pipeline"))

from lib.backlink_targets import PLATFORM_ALIASES

CALLSITE_EMBED = "CS-011"
CALLSITE_CLASSIFY = "CS-012"
DEEP_INDEX_PATH = REPO_ROOT / "data" / "backlinks" / "workspace" / "deep_target_index.json"
AI_ENRICHMENT_PATH = REPO_ROOT / "data" / "backlinks" / "workspace" / "ai_enrichment_index.json"

# Closed-set classification labels (A1-04)
VALID_LABELS = frozenset({
    "exact_api_class",
    "related_api_class",
    "same_topic",
    "weakly_related",
    "unrelated",
})

CLASSIFICATION_PROMPT = """\
You are classifying the relationship between an aspose.org source page and an aspose.com target endpoint.

Source: {source_title} ({source_family}/{source_platform}, type: {source_type})
Target: {target_path} (type: {target_type})

Classify the relationship as exactly one of:
- exact_api_class: Target is the direct enterprise API reference for this source page
- related_api_class: Target is a related class in the same namespace/family
- same_topic: Target covers the same topic but different type (e.g., KB article about same feature)
- weakly_related: Some topical overlap but not a direct match
- unrelated: No meaningful relationship

Respond with JSON only: {{"label": "...", "confidence": "high|medium|low", "reasoning": "one sentence"}}"""


@dataclass
class EnrichmentRecord:
    target_path: str
    embedding_model: Optional[str] = None
    embedding_provider: Optional[str] = None
    llm_classification: Optional[dict] = None
    token_usage: Optional[dict] = None
    latency_ms: Optional[float] = None
    enriched_at: Optional[str] = None
    status: str = "pending"  # pending | enriched | skipped | failed
    error: Optional[str] = None


def _try_import_llm_router():
    """Try to import LLMRouter; return None if unavailable."""
    try:
        from commands.ops.llm_router import LLMRouter
        return LLMRouter()
    except Exception as exc:
        return None


def _classify_target(
    router,
    source_title: str,
    source_family: str,
    source_platform: str,
    source_type: str,
    target_path: str,
    target_type: str,
) -> dict:
    """Call LLM (CS-012) to classify source↔target relationship. Returns closed-set dict."""
    prompt = CLASSIFICATION_PROMPT.format(
        source_title=source_title,
        source_family=source_family,
        source_platform=source_platform or "unknown",
        source_type=source_type,
        target_path=target_path,
        target_type=target_type,
    )
    try:
        result = router.call_chat(
            messages=[{"role": "user", "content": prompt}],
            model="gpt-oss",
            call_site=CALLSITE_CLASSIFY,
            temperature=0.0,
            max_tokens=100,
        )
        # Parse JSON response
        raw_text = result.content if hasattr(result, "content") else str(result)
        # Extract JSON from response
        import re
        m = re.search(r"\{.*?\}", raw_text, re.DOTALL)
        if not m:
            return {"status": "failed", "error": "no_json_in_response"}

        parsed = json.loads(m.group(0))
        label = parsed.get("label", "")

        # Reject free-text / invalid labels
        if label not in VALID_LABELS:
            return {"status": "failed", "error": f"invalid_label: {label!r}"}

        token_usage = None
        if hasattr(result, "usage"):
            usage = result.usage
            token_usage = {
                "prompt": getattr(usage, "prompt_tokens", 0),
                "completion": getattr(usage, "completion_tokens", 0),
            }

        provider = getattr(result, "provider", "unknown")

        return {
            "label": label,
            "confidence": parsed.get("confidence", "low"),
            "reasoning": parsed.get("reasoning", ""),
            "model": "gpt-oss",
            "provider": provider,
            "token_usage": token_usage,
            "status": "enriched",
        }
    except Exception as exc:
        return {"status": "failed", "error": str(exc)[:200]}


def build_enrichment(
    deep_index: dict,
    family: str,
    platform: Optional[str],
    router=None,
    source_type: str = "REF_CLASS",
    dry_run: bool = False,
) -> dict:
    """
    Build Layer 1.5 AI enrichment index for target endpoints matching family/platform.

    Pure business logic — accepts router as dependency injection.
    Returns: {status, index: {path_key: EnrichmentRecord}}
    """
    from datetime import datetime, timezone

    index_entries = deep_index.get("index", {})
    enrichment_index: dict = {}
    enriched_count = 0
    skipped_count = 0
    failed_count = 0

    for path_key, entry in index_entries.items():
        entry_family = entry.get("family", "")
        entry_platform = entry.get("platform", "")

        if entry_family != family:
            continue

        if platform:
            canonical_entry = PLATFORM_ALIASES.get(entry_platform, entry_platform)
            canonical_src = PLATFORM_ALIASES.get(platform, platform)
            if canonical_entry != canonical_src:
                continue

        if dry_run:
            enrichment_index[path_key] = {
                "target_path": path_key,
                "status": "skipped",
                "error": "dry_run",
            }
            skipped_count += 1
            continue

        if router is None:
            enrichment_index[path_key] = {
                "target_path": path_key,
                "status": "skipped",
                "error": "ai_unavailable",
            }
            skipped_count += 1
            continue

        # Build minimal source context from target metadata
        class_name = entry.get("class_name") or entry.get("article_slug") or path_key.split("/")[-1]
        source_title = class_name.title()

        t0 = time.monotonic()
        classification = _classify_target(
            router,
            source_title=source_title,
            source_family=family,
            source_platform=platform or "",
            source_type=source_type,
            target_path=path_key,
            target_type=entry.get("type", "unknown"),
        )
        latency_ms = (time.monotonic() - t0) * 1000

        if classification.get("status") == "enriched":
            enrichment_index[path_key] = {
                "target_path": path_key,
                "embedding_model": None,  # embedding call skipped for now
                "embedding_provider": None,
                "llm_classification": {
                    "label": classification["label"],
                    "confidence": classification.get("confidence", "low"),
                    "reasoning": classification.get("reasoning", ""),
                    "model": classification.get("model", "gpt-oss"),
                    "provider": classification.get("provider", "unknown"),
                },
                "token_usage": classification.get("token_usage"),
                "latency_ms": round(latency_ms, 1),
                "enriched_at": datetime.now(timezone.utc).isoformat(),
                "status": "enriched",
                "error": None,
            }
            enriched_count += 1
        else:
            enrichment_index[path_key] = {
                "target_path": path_key,
                "status": "failed",
                "error": classification.get("error"),
            }
            failed_count += 1

    total = len(enrichment_index)
    degraded_rate = (skipped_count + failed_count) / total if total > 0 else 0.0
    ai_status = (
        "AI_EXPLICITLY_DISABLED" if router is None
        else "AI_ENRICHED_PRIMARY" if enriched_count > 0
        else "AI_UNAVAILABLE_DEGRADED"
    )
    if degraded_rate > 0.20 and router is not None:
        ai_status = "AI_DEGRADATION_RATE_WARNING"

    return {
        "enriched_count": enriched_count,
        "skipped_count": skipped_count,
        "failed_count": failed_count,
        "ai_status": ai_status,
        "index": enrichment_index,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build AI enrichment index for backlink candidates (Layer 1.5)"
    )
    parser.add_argument("--family", required=True, help="Product family (e.g., 3d)")
    parser.add_argument("--platform", default=None, help="Platform filter (e.g., java)")
    parser.add_argument("--deep-index", default=str(DEEP_INDEX_PATH))
    parser.add_argument("--output", default=str(AI_ENRICHMENT_PATH))
    parser.add_argument("--dry-run", action="store_true",
                        help="Skip AI calls; write skipped records")
    parser.add_argument("--no-ai", action="store_true",
                        help="Same as --dry-run; explicitly disable AI")
    args = parser.parse_args()

    deep_index_path = Path(args.deep_index)
    if not deep_index_path.exists():
        print(f"ERROR: deep_target_index.json not found at {deep_index_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Loading Layer 1 from {deep_index_path} ...")
    deep_index = json.loads(deep_index_path.read_text(encoding="utf-8"))

    dry_run = args.dry_run or args.no_ai
    router = None
    if not dry_run:
        router = _try_import_llm_router()
        if router is None:
            print("WARNING: LLMRouter unavailable — proceeding with AI-skipped mode "
                  "(AI_UNAVAILABLE_DEGRADED)")

    print(f"Building AI enrichment (family={args.family}, platform={args.platform or 'all'}) ...")
    result = build_enrichment(
        deep_index,
        family=args.family,
        platform=args.platform,
        router=router,
        dry_run=dry_run,
    )

    print(f"Enrichment: {result['enriched_count']} enriched, "
          f"{result['skipped_count']} skipped, {result['failed_count']} failed")
    print(f"AI status: {result['ai_status']}")

    if dry_run:
        print("Dry-run/no-ai mode: all records marked skipped.")

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    from datetime import datetime, timezone
    output = {
        "schema_version": "1.0.0",
        "family": args.family,
        "platform": args.platform,
        "ai_status": result["ai_status"],
        "enriched_count": result["enriched_count"],
        "skipped_count": result["skipped_count"],
        "failed_count": result["failed_count"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "index": result["index"],
    }

    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Written: {out_path}")


if __name__ == "__main__":
    main()
