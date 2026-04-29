#!/usr/bin/env python3
"""page_impact_assess.py — Page Impact Assessment (PIA) for post-refresh content review.

CONTRACT: scripts/pipeline/page_impact_assess.py
  purpose: Score every English content page against the knowledge delta to identify
           which pages need body review after an upstream knowledge refresh.
  inputs:  knowledge/{family}/{platform}/merged/knowledge_delta.json
           content pages (all 5 subdomains) for the given family/platform
  outputs: reports/refresh_review/{family}/{platform}/page_impact.json
  idempotent: yes — overwrites output on each run

Impact score legend:
  HIGH_IMPACT    — page body contains a class or method name matching modified_apis or removed_apis
  MEDIUM_IMPACT  — page body contains a keyword matching modified_claims or removed_claims topics
  LOW_IMPACT     — no strong delta signals found; page may still benefit from review
  NOT_AFFECTED   — no delta signals detected; page topic unrelated to knowledge changes

Usage:
    .venv/Scripts/python scripts/pipeline/page_impact_assess.py {family} {platform}
    .venv/Scripts/python scripts/pipeline/page_impact_assess.py cells net --knowledge-root knowledge/
    .venv/Scripts/python scripts/pipeline/page_impact_assess.py cells net --json

Exit codes:
    0  — assessment complete (even if all pages NOT_AFFECTED)
    1  — fatal error (knowledge_delta.json missing and --require-delta set, or I/O failure)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_PIPELINE_DIR = Path(__file__).resolve().parents[2]  # commands/ops/ -> commands/ -> pipeline/
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))

from content_discovery import LOCALE_RE, _is_draft  # noqa: E402

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[4]
_REPO_ROOT = _DEFAULT_REPO_ROOT


def configure(*, repo_root: "Path | str | None" = None) -> None:
    """Override module-level path constants for testing."""
    global _REPO_ROOT
    _REPO_ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT

# Site pattern tuples: (subdomain_label, path_pattern_relative_to_content_root)
# Must match stale_detect.py _SITE_PATTERNS for consistency.
_SITE_PATTERNS: tuple[tuple[str, str], ...] = (
    ("docs",      "docs.aspose.org/en/{family}/{platform}"),
    ("kb",        "kb.aspose.org/en/{family}/{platform}"),
    ("products",  "products.aspose.org/en/{family}/{platform}"),
    ("reference", "reference.aspose.org/en/{family}/{platform}"),
    ("blog",      "blog.aspose.org/{family}/{platform}"),
)


def _discover_pages(
    content_root: Path,
    family: str,
    platform: str,
) -> list[tuple[Path, str]]:
    """Return (path, subdomain) pairs for all English non-draft .md files."""
    results: list[tuple[Path, str]] = []
    for subdomain, pattern in _SITE_PATTERNS:
        site_root = content_root / pattern.format(family=family, platform=platform)
        if not site_root.exists():
            continue
        for path in sorted(site_root.rglob("*.md")):
            if LOCALE_RE.search(path.name):
                continue
            if _is_draft(path):
                continue
            results.append((path, subdomain))
    return results


def _load_delta(knowledge_root: Path, family: str, platform: str) -> dict:
    """Load knowledge_delta.json; return {} if absent."""
    delta_path = knowledge_root / family / platform / "merged" / "knowledge_delta.json"
    if not delta_path.is_file():
        return {}
    try:
        return json.loads(delta_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _extract_api_names(delta: dict) -> set[str]:
    """Extract class and method names from modified_apis and removed_apis."""
    names: set[str] = set()
    for key in ("modified_apis", "removed_apis"):
        for entry in delta.get(key, []):
            if isinstance(entry, str):
                names.add(entry.lower())
            elif isinstance(entry, dict):
                class_name = entry.get("name") or entry.get("class_name") or ""
                if class_name:
                    names.add(class_name.lower())
                # Also index method names
                for method in entry.get("methods", []):
                    if isinstance(method, str):
                        names.add(method.lower())
                    elif isinstance(method, dict):
                        m = method.get("name") or ""
                        if m:
                            names.add(m.lower())
    return names


def _extract_claim_keywords(delta: dict) -> set[str]:
    """Extract significant keywords from modified/removed claim text."""
    keywords: set[str] = set()
    stopwords = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "shall",
        "should", "may", "might", "must", "can", "could", "of", "in", "to",
        "for", "on", "with", "at", "by", "from", "up", "about", "into",
        "than", "then", "so", "if", "or", "and", "but", "not", "no",
        "it", "its", "this", "that", "these", "those", "all", "any",
        "class", "method", "property", "object", "value", "type",
        "returns", "return", "true", "false", "null", "none",
        "new", "get", "set", "add", "use", "used", "using",
    }
    for key in ("modified_claims", "removed_claims"):
        for entry in delta.get(key, []):
            if isinstance(entry, str):
                text = entry
            elif isinstance(entry, dict):
                text = entry.get("text") or entry.get("description") or entry.get("claim_text") or ""
            else:
                continue
            # Extract meaningful words (4+ chars, no numbers-only, not stopwords)
            for word in re.findall(r"\b[a-zA-Z][a-zA-Z0-9]{3,}\b", text):
                w = word.lower()
                if w not in stopwords:
                    keywords.add(w)
    return keywords


def _score_page(
    path: Path,
    api_names: set[str],
    claim_keywords: set[str],
) -> tuple[str, list[str]]:
    """Return (pia_score, signals_found) for a single page.

    Reads the page body (text after frontmatter fence) and checks for:
    - API class/method name matches → HIGH_IMPACT
    - Claim keyword matches → MEDIUM_IMPACT
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "NOT_AFFECTED", []

    # Strip frontmatter to get body text
    if text.startswith("---"):
        end = text.find("\n---", 3)
        body = text[end + 4:] if end != -1 else text
    else:
        body = text

    body_lower = body.lower()
    # Tokenize body for whole-word matching
    body_tokens = set(re.findall(r"\b[a-z][a-z0-9]{2,}\b", body_lower))

    signals: list[str] = []

    # HIGH_IMPACT: exact class/method name found in body
    high_matches = api_names.intersection(body_tokens)
    if high_matches:
        signals.extend(f"api:{m}" for m in sorted(high_matches)[:5])
        return "HIGH_IMPACT", signals

    # MEDIUM_IMPACT: claim keyword found in body
    kw_matches = claim_keywords.intersection(body_tokens)
    if kw_matches:
        # Require at least 2 keyword matches to avoid single-word false positives
        if len(kw_matches) >= 2:
            signals.extend(f"kw:{k}" for k in sorted(kw_matches)[:5])
            return "MEDIUM_IMPACT", signals

    return "LOW_IMPACT", []


def assess_product(
    family: str,
    platform: str,
    *,
    content_root: Path | None = None,
    knowledge_root: Path | None = None,
) -> dict:
    """Run PIA for all English content pages of a product.

    Returns a dict with structure::

        {
          "family": ..., "platform": ...,
          "delta_sha": ...,
          "api_signals_count": N,
          "claim_keyword_count": N,
          "pages": [
            {"path": ..., "subdomain": ..., "pia_score": ..., "signals_found": [...]},
            ...
          ],
          "summary": {
            "HIGH_IMPACT": N, "MEDIUM_IMPACT": N,
            "LOW_IMPACT": N, "NOT_AFFECTED": N,
            "total": N
          }
        }
    """
    if content_root is None:
        content_root = _REPO_ROOT / "content"
    if knowledge_root is None:
        knowledge_root = _REPO_ROOT / "knowledge"

    delta = _load_delta(knowledge_root, family, platform)
    delta_sha = delta.get("current_sha") or delta.get("base_sha") or ""

    api_names = _extract_api_names(delta)
    claim_keywords = _extract_claim_keywords(delta)

    pages_data = []
    summary: dict[str, int] = {
        "HIGH_IMPACT": 0,
        "MEDIUM_IMPACT": 0,
        "LOW_IMPACT": 0,
        "NOT_AFFECTED": 0,
        "total": 0,
    }

    # Compute repo root for relative path calculation.
    # content_root is typically {repo_root}/content, so repo_root = content_root.parent.
    # For tests that pass a tmp_path, this still produces correct relative paths.
    effective_repo_root = content_root.parent

    page_pairs = _discover_pages(content_root, family, platform)
    for path, subdomain in page_pairs:
        try:
            rel_path = str(path.relative_to(effective_repo_root)).replace("\\", "/")
        except ValueError:
            rel_path = str(path).replace("\\", "/")

        if not api_names and not claim_keywords:
            # No delta signals — all pages are NOT_AFFECTED (delta absent or empty)
            score, signals = "NOT_AFFECTED", []
        else:
            score, signals = _score_page(path, api_names, claim_keywords)

        pages_data.append({
            "path": rel_path,
            "subdomain": subdomain,
            "pia_score": score,
            "signals_found": signals,
        })
        summary[score] = summary.get(score, 0) + 1
        summary["total"] += 1

    return {
        "family": family,
        "platform": platform,
        "delta_sha": delta_sha,
        "api_signals_count": len(api_names),
        "claim_keyword_count": len(claim_keywords),
        "pages": pages_data,
        "summary": summary,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="page_impact_assess",
        description="Score content pages against knowledge delta for post-refresh impact assessment",
    )
    parser.add_argument("family", help="Product family (e.g. cells)")
    parser.add_argument("platform", help="Platform (e.g. net)")
    parser.add_argument("--content-root", type=Path, default=None)
    parser.add_argument("--knowledge-root", type=Path, default=None)
    parser.add_argument(
        "--output-dir", type=Path, default=None,
        help="Directory for page_impact.json output (default: reports/refresh_review/{family}/{platform}/)"
    )
    parser.add_argument("--json", action="store_true", help="Emit result JSON to stdout")
    parser.add_argument(
        "--require-delta", action="store_true",
        help="Exit 1 if knowledge_delta.json is absent (default: warn and continue)"
    )
    args = parser.parse_args(argv)

    kr = args.knowledge_root or (_REPO_ROOT / "knowledge")
    delta_path = kr / args.family / args.platform / "merged" / "knowledge_delta.json"
    if not delta_path.is_file():
        if args.require_delta:
            print(f"ERROR: knowledge_delta.json not found at {delta_path}", file=sys.stderr)
            return 1
        print(f"WARN: knowledge_delta.json not found at {delta_path}; all pages will score NOT_AFFECTED")

    result = assess_product(
        args.family,
        args.platform,
        content_root=args.content_root,
        knowledge_root=args.knowledge_root,
    )

    if args.output_dir:
        out_dir = args.output_dir
    else:
        out_dir = _REPO_ROOT / "reports" / "refresh_review" / args.family / args.platform

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "page_impact.json"
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"PIA complete: {result['summary']['total']} pages assessed")
    print(f"  HIGH_IMPACT:   {result['summary']['HIGH_IMPACT']}")
    print(f"  MEDIUM_IMPACT: {result['summary']['MEDIUM_IMPACT']}")
    print(f"  LOW_IMPACT:    {result['summary']['LOW_IMPACT']}")
    print(f"  NOT_AFFECTED:  {result['summary']['NOT_AFFECTED']}")
    print(f"  Output: {out_path}")

    if args.json:
        sys.stdout.buffer.write(json.dumps(result, indent=2, ensure_ascii=False).encode("utf-8"))
        sys.stdout.buffer.write(b"\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
