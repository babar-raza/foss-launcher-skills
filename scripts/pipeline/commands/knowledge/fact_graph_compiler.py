"""fact_graph_compiler.py — Build canonical fact graph from merged knowledge.

Reads merged/ artifacts (model.yaml, api_surface.json, claims.json, formats.json)
and normalizes them into a deterministic FactGraph JSON file.

Usage:
    python scripts/pipeline/commands/knowledge/fact_graph_compiler.py {family} {platform} [options]

Options:
    --output PATH       Write fact_graph.json to PATH (default: stdout)
    --knowledge-root    Override knowledge root directory
    --quiet             Suppress summary output
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# --- Pipeline bootstrap ---
_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

from lib.fact_graph import compile_fact_graph


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build canonical fact graph from merged knowledge artifacts.",
    )
    parser.add_argument("family", help="Product family (e.g. pdf, cells)")
    parser.add_argument("platform", help="Platform (e.g. go, python, cpp)")
    parser.add_argument("--output", "-o", help="Output path for fact_graph.json (default: stdout)")
    parser.add_argument("--knowledge-root", help="Override knowledge root directory")
    parser.add_argument("--quiet", "-q", action="store_true", help="Suppress summary")
    args = parser.parse_args(argv)

    knowledge_root = Path(args.knowledge_root) if args.knowledge_root else None

    try:
        graph = compile_fact_graph(args.family, args.platform, knowledge_root)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    json_out = graph.to_json()

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json_out, encoding="utf-8")
        if not args.quiet:
            print(f"Wrote {out_path} ({graph.fact_count} facts)", file=sys.stderr)
    else:
        print(json_out)

    if not args.quiet and args.output:
        by_cat: dict[str, int] = {}
        for f in graph.facts:
            by_cat[f.category] = by_cat.get(f.category, 0) + 1
        for cat, count in sorted(by_cat.items()):
            print(f"  {cat}: {count}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
