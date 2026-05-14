#!/usr/bin/env python3
"""Assess which pages are affected by a knowledge delta."""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

SITES = (
    ("docs", "docs.aspose.org/en/{family}/{platform}"),
    ("kb", "kb.aspose.org/en/{family}/{platform}"),
    ("products", "products.aspose.org/en/{family}/{platform}"),
    ("reference", "reference.aspose.org/en/{family}/{platform}"),
    ("blog", "blog.aspose.org/{family}/{platform}"),
)


def load_delta(knowledge_root: Path, family: str, platform: str) -> dict:
    path = knowledge_root / family / platform / "merged" / "knowledge_delta.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def delta_terms(delta: dict) -> tuple[set[str], set[str]]:
    api_terms: set[str] = set()
    claim_terms: set[str] = set()
    for key in ("modified_apis", "removed_apis"):
        for item in delta.get(key, []):
            if isinstance(item, str):
                api_terms.add(item.lower())
            elif isinstance(item, dict):
                for value in (item.get("name"), item.get("class_name")):
                    if value:
                        api_terms.add(str(value).lower())
    for key in ("modified_claims", "removed_claims"):
        for item in delta.get(key, []):
            text = item if isinstance(item, str) else item.get("text", "") if isinstance(item, dict) else ""
            claim_terms.update(word.lower() for word in re.findall(r"\b[a-zA-Z][a-zA-Z0-9]{3,}\b", text))
    return api_terms, claim_terms


def discover_pages(content_root: Path, family: str, platform: str) -> list[tuple[Path, str]]:
    pages: list[tuple[Path, str]] = []
    for site, pattern in SITES:
        root = content_root / pattern.format(family=family, platform=platform)
        if root.exists():
            pages.extend((path, site) for path in sorted(root.rglob("*.md")) if path.name == "index.md" or not re.search(r"\.[a-z]{2}\.md$", path.name))
    return pages


def score_page(path: Path, api_terms: set[str], claim_terms: set[str]) -> tuple[str, list[str]]:
    text = path.read_text(encoding="utf-8", errors="replace").lower()
    tokens = set(re.findall(r"\b[a-z][a-z0-9_]{2,}\b", text))
    api_hits = sorted(api_terms & tokens)
    if api_hits:
        return "HIGH_IMPACT", [f"api:{hit}" for hit in api_hits[:5]]
    claim_hits = sorted(claim_terms & tokens)
    if len(claim_hits) >= 2:
        return "MEDIUM_IMPACT", [f"kw:{hit}" for hit in claim_hits[:5]]
    return "LOW_IMPACT", []


def assess(content_root: Path, knowledge_root: Path, family: str, platform: str) -> dict:
    api_terms, claim_terms = delta_terms(load_delta(knowledge_root, family, platform))
    pages = []
    for path, site in discover_pages(content_root, family, platform):
        score, signals = score_page(path, api_terms, claim_terms)
        pages.append({"path": str(path.relative_to(content_root)).replace("\\", "/"), "subdomain": site, "pia_score": score, "signals_found": signals})
    summary = Counter(page["pia_score"] for page in pages)
    summary["total"] = len(pages)
    return {"family": family, "platform": platform, "pages": pages, "summary": dict(summary)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("family")
    parser.add_argument("platform")
    parser.add_argument("--content-root", type=Path, default=Path("content"))
    parser.add_argument("--knowledge-root", type=Path, default=Path("knowledge"))
    parser.add_argument("--output-root", type=Path, default=Path("reports"))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = assess(args.content_root, args.knowledge_root, args.family, args.platform)
    out = args.output_root / "refresh_review" / args.family / args.platform / "page_impact.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True) if args.json else out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
