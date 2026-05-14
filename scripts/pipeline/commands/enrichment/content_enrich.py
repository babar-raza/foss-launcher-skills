#!/usr/bin/env python3
"""Standalone content enrichment audit and manifest scaffold."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

SUBDOMAINS = [
    "products.aspose.org",
    "docs.aspose.org",
    "kb.aspose.org",
    "blog.aspose.org",
    "reference.aspose.org",
]


def _claims_path(family: str, platform: str, knowledge_root: Path) -> Path:
    return knowledge_root / family / platform / "merged" / "claims.json"


def _load_claims(family: str, platform: str, knowledge_root: Path) -> list[dict]:
    path = _claims_path(family, platform, knowledge_root)
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else data.get("claims", [])


def build_audit(family: str, platform: str, *, knowledge_root: Path, content_root: Path) -> dict:
    claims = _load_claims(family, platform, knowledge_root)
    categories = sorted({str(item.get("category") or item.get("kind") or "uncategorized") for item in claims})
    content_counts = {}
    for subdomain in SUBDOMAINS:
        if subdomain == "blog.aspose.org":
            root = content_root / subdomain / family / platform
        else:
            root = content_root / subdomain / "en" / family / platform
        content_counts[subdomain] = len(list(root.rglob("*.md"))) if root.exists() else 0
    total_cells = max(1, len(categories) * len(SUBDOMAINS))
    covered = sum(1 for count in content_counts.values() if count > 0) * max(1, len(categories))
    covered = min(covered, total_cells)
    return {
        "family": family,
        "platform": platform,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cluster_count": len(categories),
        "total_claims": len(claims),
        "clusters": [{"category": category} for category in categories],
        "content_file_counts": content_counts,
        "summary": {
            "total_cells": total_cells,
            "covered": covered,
            "uncovered": total_cells - covered,
            "coverage_ratio": covered / total_cells,
        },
        "knowledge_available": {
            "claims": _claims_path(family, platform, knowledge_root).exists(),
        },
    }


def build_candidates(audit: dict) -> dict:
    candidates = []
    for cluster in audit.get("clusters", []):
        for subdomain, count in audit.get("content_file_counts", {}).items():
            if count == 0:
                candidates.append({
                    "category": cluster["category"],
                    "subdomain": subdomain,
                    "disposition": "deferred_to_backlog",
                    "reason": "No content files discovered for this subdomain in scaffold audit.",
                })
    return {
        "family": audit["family"],
        "platform": audit["platform"],
        "candidates": candidates,
        "denominator": {
            "total_candidates": len(candidates),
            "generate_now": 0,
            "update_existing": 0,
            "deferred_to_backlog": len(candidates),
            "rejected_with_reason": 0,
            "blocked_with_reason": 0,
            "valid": True,
        },
    }


def write_outputs(result: dict, out_dir: Path, *, mode: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "coverage-matrix.json").write_text(json.dumps(result["audit"], indent=2), encoding="utf-8")
    if "candidates" in result:
        (out_dir / "candidate-list.json").write_text(json.dumps(result["candidates"], indent=2), encoding="utf-8")
        (out_dir / "denominator-check.json").write_text(json.dumps(result["candidates"]["denominator"], indent=2), encoding="utf-8")
        manifest = {
            "family": result["audit"]["family"],
            "platform": result["audit"]["platform"],
            "mode": mode,
            "dry_run": mode != "execute",
            "handoffs": result["candidates"]["candidates"],
        }
        (out_dir / "handoff-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def run(
    family: str,
    platform: str,
    *,
    mode: str = "audit",
    output_root: Path = Path("reports/enrichment"),
    knowledge_root: Path = Path("knowledge"),
    content_root: Path = Path("content"),
) -> dict:
    audit = build_audit(family, platform, knowledge_root=knowledge_root, content_root=content_root)
    result = {"audit": audit}
    if mode in {"plan", "dry-run", "execute"}:
        result["candidates"] = build_candidates(audit)
    write_outputs(result, output_root / family / platform, mode=mode)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("family")
    parser.add_argument("platform")
    parser.add_argument("--mode", choices=("audit", "plan", "dry-run", "execute"), default="audit")
    parser.add_argument("--output-root", type=Path, default=Path("reports/enrichment"))
    parser.add_argument("--knowledge-root", type=Path, default=Path("knowledge"))
    parser.add_argument("--content-root", type=Path, default=Path("content"))
    args = parser.parse_args(argv)
    result = run(
        args.family,
        args.platform,
        mode=args.mode,
        output_root=args.output_root,
        knowledge_root=args.knowledge_root,
        content_root=args.content_root,
    )
    print(json.dumps({"mode": args.mode, "summary": result["audit"]["summary"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
