#!/usr/bin/env python3
"""Annotate gap-eval findings with deterministic origin and repair routing."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

CONTENT = "CONTENT"
PIPELINE = "PIPELINE"
UPSTREAM = "UPSTREAM"
AMBIGUOUS = "AMBIGUOUS"


def classify_finding(finding: dict[str, Any], *, no_grep: bool = True) -> dict[str, Any]:
    ftype = str(finding.get("type", ""))
    old_value = str(finding.get("old_value") or "")
    if finding.get("tier_resolved_by") == 3 and not finding.get("tier3_cache_hit", False):
        return _annotation(AMBIGUOUS, "low-confidence", "LOW", "Tier 3 finding without cache hit.", "AMBIGUOUS", True)
    if ftype == "broken-link":
        return _annotation(UPSTREAM, "broken-link-upstream", "HIGH", f"Broken target: {old_value}", "S-74")
    if ftype in {"knowledge-model-wrong", "phantom-api"}:
        return _annotation(PIPELINE, "extraction-miss", "HIGH", "Knowledge artifact or scout output requires repair.", "HUMAN-PIPELINE")
    if ftype in {"wrong-package", "wrong-api-name", "wrong-claim", "wrong-unit", "unimplemented-as-working"}:
        certainty = "LOW" if no_grep and ftype == "wrong-api-name" else "MEDIUM"
        route = "AMBIGUOUS" if certainty == "LOW" else "S-46"
        return _annotation(CONTENT if route != "AMBIGUOUS" else AMBIGUOUS, "hallucination", certainty, "Content-level finding from gap-eval metadata.", route)
    if ftype in {"missing-section", "missing-page", "structural-reference-page"}:
        return _annotation(CONTENT, "planner-gap", "MEDIUM", "Missing or malformed generated content surface.", "S-26")
    return _annotation(AMBIGUOUS, "unknown-type", "LOW", f"Unknown finding type: {ftype}", "AMBIGUOUS")


def _annotation(
    origin_class: str,
    origin_subclass: str,
    origin_certainty: str,
    origin_evidence: str,
    repair_route: str,
    tier3_non_determinism_flag: bool = False,
) -> dict[str, Any]:
    return {
        "origin_class": origin_class,
        "origin_subclass": origin_subclass,
        "origin_certainty": origin_certainty,
        "origin_evidence": origin_evidence,
        "repair_route": repair_route,
        "tier3_non_determinism_flag": tier3_non_determinism_flag,
    }


def annotate_findings(findings: list[dict[str, Any]], *, no_grep: bool = True) -> list[dict[str, Any]]:
    return [{**finding, **classify_finding(finding, no_grep=no_grep)} for finding in findings]


def build_summary(annotated: list[dict[str, Any]]) -> dict[str, Any]:
    by_class: dict[str, int] = {}
    by_route: dict[str, int] = {}
    for finding in annotated:
        by_class[finding["origin_class"]] = by_class.get(finding["origin_class"], 0) + 1
        by_route[finding["repair_route"]] = by_route.get(finding["repair_route"], 0) + 1
    return {
        "total": len(annotated),
        "by_class": by_class,
        "by_route": by_route,
        "tier3_non_deterministic_count": sum(1 for finding in annotated if finding.get("tier3_non_determinism_flag")),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("gap_eval_json", type=Path)
    parser.add_argument("family")
    parser.add_argument("platform")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--no-grep", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    if not args.gap_eval_json.exists():
        print(f"error: input file not found: {args.gap_eval_json}", file=sys.stderr)
        return 1
    data = json.loads(args.gap_eval_json.read_text(encoding="utf-8"))
    findings = data.get("findings", [])
    if not isinstance(findings, list):
        print("error: findings must be a list", file=sys.stderr)
        return 2
    annotated = annotate_findings([item for item in findings if isinstance(item, dict)], no_grep=args.no_grep)
    output = {**data, "family": args.family, "platform": args.platform, "findings": annotated, "origin_summary": build_summary(annotated)}
    if args.dry_run:
        print(json.dumps(output, indent=2, sort_keys=True))
        return 0
    out_path = args.out or args.gap_eval_json.with_name(args.gap_eval_json.stem + "-origin.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2, sort_keys=True), encoding="utf-8")
    print(out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
