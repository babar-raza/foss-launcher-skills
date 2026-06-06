"""page_plan_compiler.py — Deterministic page plan from fact graph.

Consumes a FactGraph JSON and emits a deterministic page plan specifying
which pages to create/update across subdomains, with required sections
and provenance references.

No LLM calls. No content/ writes. Output to stdout or --output path.

Usage:
    python scripts/pipeline/commands/content/page_plan_compiler.py {family} {platform} \\
        --fact-graph PATH [--output PATH]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# --- Pipeline bootstrap ---
_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

from lib.fact_graph import FactGraph

PAGE_PLAN_SCHEMA_VERSION = "1.0.0"

# ---------------------------------------------------------------------------
# Subdomain templates
# ---------------------------------------------------------------------------

SUBDOMAIN_TEMPLATES: dict[str, dict[str, Any]] = {
    "reference": {
        "page_type": "reference",
        "required_sections": ["description", "properties", "methods", "examples"],
        "fact_categories": ["api_class", "api_method"],
    },
    "docs": {
        "page_type": "documentation",
        "required_sections": ["overview", "prerequisites", "steps", "code_example", "see_also"],
        "fact_categories": ["api_class", "api_method", "claim", "format"],
    },
    "blog": {
        "page_type": "blog_post",
        "required_sections": ["introduction", "feature_overview", "code_example", "conclusion"],
        "fact_categories": ["claim", "format"],
    },
    "kb": {
        "page_type": "knowledge_base",
        "required_sections": ["problem", "solution", "code_example", "references"],
        "fact_categories": ["claim", "api_method"],
    },
    "products": {
        "page_type": "product_landing",
        "required_sections": ["hero", "features", "formats", "code_sample", "pricing"],
        "fact_categories": ["claim", "format"],
    },
}


def _slugify(text: str) -> str:
    """Convert text to URL-safe slug."""
    return text.lower().replace("::", "-").replace(".", "-").replace(" ", "-").replace("_", "-")


def compile_page_plan(graph: FactGraph) -> dict[str, Any]:
    """Build a deterministic page plan from a fact graph.

    Returns a JSON-serializable dict with page entries per subdomain.
    """
    plan: dict[str, Any] = {
        "schema_version": PAGE_PLAN_SCHEMA_VERSION,
        "family": graph.family,
        "platform": graph.platform,
        "repo_sha": graph.repo_sha,
        "subdomains": {},
    }

    # Group facts by category
    by_category: dict[str, list[dict]] = {}
    for fact in graph.facts:
        by_category.setdefault(fact.category, []).append({
            "fact_id": fact.fact_id,
            "text": fact.text,
            "fact_type": fact.fact_type,
            "confidence": fact.confidence,
        })

    for subdomain, template in sorted(SUBDOMAIN_TEMPLATES.items()):
        pages: list[dict[str, Any]] = []

        if subdomain == "reference":
            # One page per API class
            for cls_fact in sorted(by_category.get("api_class", []), key=lambda f: f["text"]):
                cls_name = cls_fact["text"]
                # Collect methods for this class
                methods = [
                    m for m in by_category.get("api_method", [])
                    if m["text"].startswith(f"{cls_name}.")
                ]
                pages.append({
                    "page_type": template["page_type"],
                    "slug": f"reference/{graph.family}/{graph.platform}/{_slugify(cls_name)}",
                    "title": cls_name,
                    "required_sections": template["required_sections"],
                    "required_facts": [cls_fact["fact_id"]] + [m["fact_id"] for m in methods],
                    "provenance_refs": [cls_fact["fact_id"]],
                })

        elif subdomain == "products":
            # Single landing page per product
            relevant_facts = []
            for cat in template["fact_categories"]:
                relevant_facts.extend(by_category.get(cat, []))
            if relevant_facts:
                pages.append({
                    "page_type": template["page_type"],
                    "slug": f"products/{graph.family}/{graph.platform}",
                    "title": f"Aspose.{graph.family.title()} for {graph.platform.title()}",
                    "required_sections": template["required_sections"],
                    "required_facts": sorted(f["fact_id"] for f in relevant_facts),
                    "provenance_refs": sorted(f["fact_id"] for f in relevant_facts[:5]),
                })

        elif subdomain == "docs":
            # Overview page + format-specific pages
            all_facts = []
            for cat in template["fact_categories"]:
                all_facts.extend(by_category.get(cat, []))
            if all_facts:
                pages.append({
                    "page_type": template["page_type"],
                    "slug": f"docs/{graph.family}/{graph.platform}/overview",
                    "title": f"{graph.family.title()} {graph.platform.title()} Overview",
                    "required_sections": template["required_sections"],
                    "required_facts": sorted(f["fact_id"] for f in all_facts[:20]),
                    "provenance_refs": sorted(f["fact_id"] for f in all_facts[:5]),
                })
            # Format-specific docs pages
            for fmt_fact in sorted(by_category.get("format", []), key=lambda f: f["text"]):
                pages.append({
                    "page_type": template["page_type"],
                    "slug": f"docs/{graph.family}/{graph.platform}/formats/{_slugify(fmt_fact['text'])}",
                    "title": f"Working with {fmt_fact['text'].split(':')[1] if ':' in fmt_fact['text'] else fmt_fact['text']}",
                    "required_sections": ["overview", "code_example", "see_also"],
                    "required_facts": [fmt_fact["fact_id"]],
                    "provenance_refs": [fmt_fact["fact_id"]],
                })

        elif subdomain in ("blog", "kb"):
            # Aggregate page from claims
            claims = by_category.get("claim", [])
            if claims:
                pages.append({
                    "page_type": template["page_type"],
                    "slug": f"{subdomain}/{graph.family}/{graph.platform}/overview",
                    "title": f"Aspose.{graph.family.title()} for {graph.platform.title()}",
                    "required_sections": template["required_sections"],
                    "required_facts": sorted(f["fact_id"] for f in claims[:10]),
                    "provenance_refs": sorted(f["fact_id"] for f in claims[:3]),
                })

        plan["subdomains"][subdomain] = {
            "page_count": len(pages),
            "pages": pages,
        }

    # Total page count
    plan["total_page_count"] = sum(
        sd["page_count"] for sd in plan["subdomains"].values()
    )

    return plan


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compile deterministic page plan from fact graph.",
    )
    parser.add_argument("family", help="Product family")
    parser.add_argument("platform", help="Platform")
    parser.add_argument("--fact-graph", required=True, help="Path to fact_graph.json")
    parser.add_argument("--output", "-o", help="Output path (default: stdout)")
    parser.add_argument("--quiet", "-q", action="store_true")
    args = parser.parse_args(argv)

    fg_path = Path(args.fact_graph)
    if not fg_path.exists():
        print(f"ERROR: Fact graph not found: {fg_path}", file=sys.stderr)
        return 1

    graph = FactGraph.read(fg_path)

    if graph.family != args.family or graph.platform != args.platform:
        print(
            f"WARNING: Fact graph family/platform ({graph.family}/{graph.platform}) "
            f"differs from arguments ({args.family}/{args.platform})",
            file=sys.stderr,
        )

    plan = compile_page_plan(graph)
    json_out = json.dumps(plan, indent=2, ensure_ascii=False)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json_out, encoding="utf-8")
        if not args.quiet:
            print(f"Wrote {out_path} ({plan['total_page_count']} pages)", file=sys.stderr)
    else:
        print(json_out)

    return 0


if __name__ == "__main__":
    sys.exit(main())
