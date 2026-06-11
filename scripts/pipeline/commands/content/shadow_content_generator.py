"""shadow_content_generator.py — Generate draft content candidates from page plan + fact graph.

Produces markdown candidates ONLY to a specified output directory.
NEVER writes to content/. All output is shadow/draft for review only.

Usage:
    python scripts/pipeline/commands/content/shadow_content_generator.py \\
        {family} {platform} --page-plan PATH --fact-graph PATH --output-dir PATH \\
        [--page-types reference,docs,products] [--limit N] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# --- Pipeline bootstrap ---
_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

from lib.fact_graph import FactGraph

SHADOW_GENERATOR_VERSION = "1.0.0"

# Test function pattern — exclude test functions across all platforms
_TEST_CLAIM_RE = re.compile(
    r"^Function Test[A-Z_]"       # Go: TestXxx
    r"|^Function test_"            # Python: test_xxx
    r"|^Method test[A-Z]"          # Java: testXxx convention
)
# Raw API signature pattern (less descriptive than prose claims)
_API_SIGNATURE_RE = re.compile(r"^(Function |Class |Method )\S")


def _filter_feature_claims(claims: list[dict]) -> list[dict]:
    """Filter and rank claims for feature display.

    Excludes test function claims and ranks descriptive prose claims
    above raw API signatures so feature sections read naturally.
    """
    filtered = [c for c in claims if not _TEST_CLAIM_RE.match(c.get("text", ""))]
    descriptive = [c for c in filtered if not _API_SIGNATURE_RE.match(c.get("text", ""))]
    api_sigs = [c for c in filtered if _API_SIGNATURE_RE.match(c.get("text", ""))]
    return descriptive + api_sigs


# Paths that must NEVER receive output
FORBIDDEN_OUTPUT_PREFIXES = ("content/", "content\\")


def _is_forbidden_output(output_dir: str) -> bool:
    """Check if output_dir would write to forbidden paths."""
    normalized = output_dir.replace("\\", "/").lower()
    for prefix in ("content/",):
        if normalized.startswith(prefix) or f"/{prefix}" in normalized:
            # Check if it's literally the content/ directory of this repo
            resolved = Path(output_dir).resolve()
            repo_content = Path(__file__).resolve().parents[4] / "content"
            try:
                resolved.relative_to(repo_content)
                return True
            except ValueError:
                pass
    return False


def _build_fact_index(graph: FactGraph) -> dict[str, dict]:
    """Build a lookup index from fact_id to fact data."""
    index = {}
    for fact in graph.facts:
        index[fact.fact_id] = {
            "fact_id": fact.fact_id,
            "fact_type": fact.fact_type,
            "category": fact.category,
            "text": fact.text,
            "confidence": fact.confidence,
            "verification_status": fact.verification_status,
        }
    return index


def generate_reference_candidate(
    page: dict,
    fact_index: dict[str, dict],
    family: str,
    platform: str,
) -> str:
    """Generate a reference page markdown candidate."""
    title = page["title"]
    slug = page["slug"]
    facts = [fact_index[fid] for fid in page.get("required_facts", []) if fid in fact_index]

    # Separate class fact from method facts
    class_facts = [f for f in facts if f["category"] == "api_class"]
    method_facts = [f for f in facts if f["category"] == "api_method"]

    lines = []
    # Frontmatter
    lines.append("---")
    lines.append(f'title: "{title}"')
    lines.append(f"type: docs")
    lines.append(f"url: /{slug}/")
    lines.append(f"weight: 10")
    lines.append(f"draft: true")
    lines.append(f"shadow_candidate: true")
    lines.append(f"generator_version: {SHADOW_GENERATOR_VERSION}")
    lines.append(f"generated_at: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}")
    lines.append(f"family: {family}")
    lines.append(f"platform: {platform}")
    prov_ids = [f["fact_id"] for f in facts[:5]]
    lines.append(f"provenance_fact_ids: {json.dumps(prov_ids)}")
    lines.append("---")
    lines.append("")

    # Title
    lines.append(f"# {title}")
    lines.append("")

    # Description
    if class_facts:
        lines.append("## Description")
        lines.append("")
        lines.append(f"The `{title}` class is part of the Aspose.{family.title()} library for {platform.title()}.")
        lines.append("")
        lines.append(f"<!-- fact_ref: {class_facts[0]['fact_id']} -->")
        lines.append("")

    # Methods
    if method_facts:
        lines.append("## Methods")
        lines.append("")
        lines.append("| Method | Fact ID |")
        lines.append("|--------|---------|")
        for mf in sorted(method_facts, key=lambda f: f["text"]):
            method_name = mf["text"].split(".")[-1] if "." in mf["text"] else mf["text"]
            lines.append(f"| `{method_name}` | `{mf['fact_id']}` |")
        lines.append("")

        # Method details
        for mf in sorted(method_facts, key=lambda f: f["text"])[:10]:
            method_name = mf["text"].split(".")[-1] if "." in mf["text"] else mf["text"]
            lines.append(f"### {method_name}")
            lines.append("")
            lines.append(f"<!-- fact_ref: {mf['fact_id']} -->")
            lines.append("")

    # See Also
    lines.append("## See Also")
    lines.append("")
    lines.append(f"- [Aspose.{family.title()} for {platform.title()} API Reference](https://reference.aspose.com/{family}/{platform}/)")
    lines.append("")

    return "\n".join(lines)


def generate_docs_candidate(
    page: dict,
    fact_index: dict[str, dict],
    family: str,
    platform: str,
) -> str:
    """Generate a docs overview markdown candidate."""
    title = page["title"]
    slug = page["slug"]
    facts = [fact_index[fid] for fid in page.get("required_facts", []) if fid in fact_index]

    claim_facts = _filter_feature_claims([f for f in facts if f["category"] == "claim"])
    format_facts = [f for f in facts if f["category"] == "format"]

    # Fallback: when required_facts contain no claims (e.g. all api_class), sample
    # high-confidence claims from the full fact_index so the Features section is populated.
    # Sort by (-confidence, claim_id) for deterministic ordering across reruns.
    if not claim_facts:
        claim_facts = _filter_feature_claims(sorted(
            [f for f in fact_index.values() if f.get("category") == "claim" and f.get("confidence", 0) >= 0.9],
            key=lambda f: (-f.get("confidence", 0), f.get("fact_id", "")),
        ))[:10]

    lines = []
    lines.append("---")
    lines.append(f'title: "{title}"')
    lines.append(f"type: docs")
    lines.append(f"url: /{slug}/")
    lines.append(f"weight: 1")
    lines.append(f"draft: true")
    lines.append(f"shadow_candidate: true")
    lines.append(f"generator_version: {SHADOW_GENERATOR_VERSION}")
    lines.append(f"generated_at: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}")
    lines.append(f"family: {family}")
    lines.append(f"platform: {platform}")
    prov_ids = [f["fact_id"] for f in facts[:5]]
    for cf in claim_facts[:5]:
        if cf["fact_id"] not in prov_ids:
            prov_ids.append(cf["fact_id"])
    prov_ids = prov_ids[:10]
    lines.append(f"provenance_fact_ids: {json.dumps(prov_ids)}")
    lines.append("---")
    lines.append("")
    lines.append(f"# {title}")
    lines.append("")

    lines.append("## Overview")
    lines.append("")
    lines.append(f"Aspose.{family.title()} for {platform.title()} provides a comprehensive API for working with {family.upper()} documents.")
    lines.append("")

    if claim_facts:
        lines.append("## Features")
        lines.append("")
        for cf in claim_facts[:10]:
            lines.append(f"- {cf['text']} <!-- fact_ref: {cf['fact_id']} -->")
        lines.append("")

    if format_facts:
        lines.append("## Supported Formats")
        lines.append("")
        lines.append("| Format | Support |")
        lines.append("|--------|---------|")
        for ff in format_facts:
            parts = ff["text"].split(":")
            ext = parts[1] if len(parts) > 1 else ff["text"]
            support = parts[2] if len(parts) > 2 else "unknown"
            lines.append(f"| {ext} | {support} |")
        lines.append("")

    lines.append("## See Also")
    lines.append("")
    lines.append(f"- [API Reference](https://reference.aspose.com/{family}/{platform}/)")
    lines.append("")

    return "\n".join(lines)


def generate_product_candidate(
    page: dict,
    fact_index: dict[str, dict],
    family: str,
    platform: str,
) -> str:
    """Generate a products landing page candidate."""
    title = page["title"]
    slug = page["slug"]
    facts = [fact_index[fid] for fid in page.get("required_facts", []) if fid in fact_index]

    claim_facts = _filter_feature_claims([f for f in facts if f["category"] == "claim"])
    format_facts = [f for f in facts if f["category"] == "format"]

    lines = []
    lines.append("---")
    lines.append(f'title: "{title}"')
    lines.append(f"type: products")
    lines.append(f"url: /{slug}/")
    lines.append(f"draft: true")
    lines.append(f"shadow_candidate: true")
    lines.append(f"generator_version: {SHADOW_GENERATOR_VERSION}")
    lines.append(f"generated_at: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}")
    lines.append(f"family: {family}")
    lines.append(f"platform: {platform}")
    prov_ids = [f["fact_id"] for f in facts[:5]]
    lines.append(f"provenance_fact_ids: {json.dumps(prov_ids)}")
    lines.append("---")
    lines.append("")
    lines.append(f"# {title}")
    lines.append("")

    if claim_facts:
        lines.append("## Key Features")
        lines.append("")
        for cf in claim_facts[:8]:
            lines.append(f"- {cf['text']} <!-- fact_ref: {cf['fact_id']} -->")
        lines.append("")

    if format_facts:
        lines.append("## Format Support")
        lines.append("")
        for ff in format_facts[:5]:
            parts = ff["text"].split(":")
            ext = parts[1] if len(parts) > 1 else ff["text"]
            lines.append(f"- {ext}")
        lines.append("")

    return "\n".join(lines)


def generate_blog_candidate(
    page: dict,
    fact_index: dict[str, dict],
    family: str,
    platform: str,
) -> str:
    """Generate a blog post candidate."""
    title = page["title"]
    slug = page["slug"]
    facts = [fact_index[fid] for fid in page.get("required_facts", []) if fid in fact_index]
    claim_facts = _filter_feature_claims([f for f in facts if f["category"] == "claim"])

    lines = []
    lines.append("---")
    lines.append(f'title: "{title}"')
    lines.append(f"type: blog")
    lines.append(f"url: /{slug}/")
    lines.append(f"draft: true")
    lines.append(f"shadow_candidate: true")
    lines.append(f"generator_version: {SHADOW_GENERATOR_VERSION}")
    lines.append(f"generated_at: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}")
    lines.append(f"family: {family}")
    lines.append(f"platform: {platform}")
    prov_ids = [f["fact_id"] for f in facts[:5]]
    lines.append(f"provenance_fact_ids: {json.dumps(prov_ids)}")
    lines.append("---")
    lines.append("")
    lines.append(f"# {title}")
    lines.append("")
    lines.append("## Introduction")
    lines.append("")
    lines.append(f"Aspose.{family.title()} for {platform.title()} is a powerful library for working with {family.upper()} documents programmatically.")
    lines.append("")

    if claim_facts:
        lines.append("## Feature Overview")
        lines.append("")
        for cf in claim_facts[:8]:
            lines.append(f"- {cf['text']} <!-- fact_ref: {cf['fact_id']} -->")
        lines.append("")

    lines.append("## Conclusion")
    lines.append("")
    lines.append(f"Aspose.{family.title()} for {platform.title()} provides a comprehensive solution for {family.upper()} document processing.")
    lines.append("")

    return "\n".join(lines)


def generate_kb_candidate(
    page: dict,
    fact_index: dict[str, dict],
    family: str,
    platform: str,
) -> str:
    """Generate a knowledge base article candidate."""
    title = page["title"]
    slug = page["slug"]
    facts = [fact_index[fid] for fid in page.get("required_facts", []) if fid in fact_index]
    claim_facts = _filter_feature_claims([f for f in facts if f["category"] == "claim"])
    method_facts = [f for f in facts if f["category"] == "api_method"]

    lines = []
    lines.append("---")
    lines.append(f'title: "{title}"')
    lines.append(f"type: kb")
    lines.append(f"url: /{slug}/")
    lines.append(f"draft: true")
    lines.append(f"shadow_candidate: true")
    lines.append(f"generator_version: {SHADOW_GENERATOR_VERSION}")
    lines.append(f"generated_at: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}")
    lines.append(f"family: {family}")
    lines.append(f"platform: {platform}")
    prov_ids = [f["fact_id"] for f in facts[:5]]
    lines.append(f"provenance_fact_ids: {json.dumps(prov_ids)}")
    lines.append("---")
    lines.append("")
    lines.append(f"# {title}")
    lines.append("")
    lines.append("## Problem")
    lines.append("")
    lines.append(f"How to use Aspose.{family.title()} for {platform.title()} to process {family.upper()} documents.")
    lines.append("")
    lines.append("## Solution")
    lines.append("")

    if claim_facts:
        lines.append(f"Aspose.{family.title()} for {platform.title()} provides the following capabilities:")
        lines.append("")
        for cf in claim_facts[:6]:
            lines.append(f"- {cf['text']} <!-- fact_ref: {cf['fact_id']} -->")
        lines.append("")

    if method_facts:
        lines.append("## References")
        lines.append("")
        for mf in method_facts[:5]:
            lines.append(f"- `{mf['text']}` <!-- fact_ref: {mf['fact_id']} -->")
        lines.append("")

    return "\n".join(lines)


# Dispatcher
_GENERATORS = {
    "reference": generate_reference_candidate,
    "documentation": generate_docs_candidate,
    "product_landing": generate_product_candidate,
    "blog_post": generate_blog_candidate,
    "knowledge_base": generate_kb_candidate,
}


def generate_candidates(
    plan: dict,
    graph: FactGraph,
    output_dir: Path,
    page_types: set[str] | None = None,
    limit: int = 0,
) -> list[dict]:
    """Generate shadow content candidates from a page plan.

    Returns list of generation records.
    """
    fact_index = _build_fact_index(graph)
    family = plan["family"]
    platform = plan["platform"]
    records = []
    count = 0

    for sd_name, sd_data in sorted(plan.get("subdomains", {}).items()):
        for page in sd_data.get("pages", []):
            page_type = page.get("page_type", "")
            if page_types and page_type not in page_types:
                continue

            generator = _GENERATORS.get(page_type)
            if not generator:
                continue

            if limit > 0 and count >= limit:
                break

            content = generator(page, fact_index, family, platform)
            slug = page.get("slug", "unknown")
            safe_name = slug.replace("/", "_").replace("\\", "_").replace(":", "_").replace("<", "_").replace(">", "_").replace("*", "_").replace("?", "_").replace('"', "_").replace("|", "_") + ".md"
            out_path = output_dir / safe_name
            out_path.write_text(content, encoding="utf-8")

            # Count fact references in output
            fact_refs = [fid for fid in fact_index if f"fact_ref: {fid}" in content or f'"{fid}"' in content]

            records.append({
                "page_type": page_type,
                "slug": slug,
                "title": page.get("title", ""),
                "output_path": str(out_path),
                "fact_ref_count": len(fact_refs),
                "required_facts": len(page.get("required_facts", [])),
                "status": "generated",
            })
            count += 1

        if limit > 0 and count >= limit:
            break

    return records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate shadow content candidates from page plan + fact graph.",
    )
    parser.add_argument("family", help="Product family")
    parser.add_argument("platform", help="Platform")
    parser.add_argument("--page-plan", required=True, help="Path to page_plan.json")
    parser.add_argument("--fact-graph", required=True, help="Path to fact_graph.json")
    parser.add_argument("--output-dir", required=True, help="Output directory for candidates")
    parser.add_argument("--page-types", help="Comma-separated page types to generate (default: all)")
    parser.add_argument("--limit", type=int, default=0, help="Max candidates to generate (0=unlimited)")
    parser.add_argument("--dry-run", action="store_true", help="Print plan without writing files")
    args = parser.parse_args(argv)

    # Safety check: never write to content/
    if _is_forbidden_output(args.output_dir):
        print("ERROR: Output directory is under content/ — this is forbidden.", file=sys.stderr)
        return 1

    plan_path = Path(args.page_plan)
    fg_path = Path(args.fact_graph)

    if not plan_path.exists():
        print(f"ERROR: Page plan not found: {plan_path}", file=sys.stderr)
        return 1
    if not fg_path.exists():
        print(f"ERROR: Fact graph not found: {fg_path}", file=sys.stderr)
        return 1

    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    graph = FactGraph.read(fg_path)

    page_types = set(args.page_types.split(",")) if args.page_types else None

    if args.dry_run:
        total = 0
        for sd_data in plan.get("subdomains", {}).values():
            for page in sd_data.get("pages", []):
                pt = page.get("page_type", "")
                if page_types and pt not in page_types:
                    continue
                if pt in _GENERATORS:
                    total += 1
        print(f"[DRY-RUN] Would generate {total} candidates")
        return 0

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    records = generate_candidates(plan, graph, output_dir, page_types, args.limit)

    # Write generation manifest
    manifest = {
        "generator_version": SHADOW_GENERATOR_VERSION,
        "family": args.family,
        "platform": args.platform,
        "candidates_generated": len(records),
        "records": records,
    }
    manifest_path = output_dir / "generation_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"Generated {len(records)} candidates to {output_dir}")
    for r in records:
        print(f"  [{r['page_type']}] {r['title']} ({r['fact_ref_count']} fact refs)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
