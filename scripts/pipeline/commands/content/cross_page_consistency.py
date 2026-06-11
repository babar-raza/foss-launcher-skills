#!/usr/bin/env python3
"""Cross-page factual consistency checker (TC-CONSIST-001).

Detects contradictory factual claims across pages within a single product.
Example: Page A says "supports PDF export" while Page B says "PDF is import-only."

Uses TF-IDF cosine for claim clustering and regex-based negation detection.
No LLM dependency — fully deterministic.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

_PIPELINE_DIR = Path(__file__).resolve().parents[2]
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))

_LIB_DIR = str(Path(__file__).resolve().parents[2] / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)


# ── TF-IDF helpers ───────────────────────────────────────────────────────────

_STOPWORDS = frozenset(
    "a about above after again against all am an and any are as at be because "
    "been before being below between both but by can could did do does doing "
    "down during each few for from further get got had has have having he her "
    "here hers herself him himself his how i if in into is it its itself just "
    "let like me might more most my myself no nor not now of off on once only "
    "or other our ours ourselves out over own re same shall she should so some "
    "such than that the their theirs them themselves then there these they this "
    "those through to too under until up us very was we were what when where "
    "which while who whom why will with you your yours yourself yourselves".split()
)

_CLUSTER_THRESHOLD = 0.60  # Minimum cosine to cluster two claims together
_NEGATION_PATTERNS = [
    # "supports X" vs "does not support X"
    re.compile(r"\b(not|no|never|cannot|can't|doesn't|don't|isn't|won't)\b", re.IGNORECASE),
    # "X only" (import-only, read-only)
    re.compile(r"\b(\w+)[- ]only\b", re.IGNORECASE),
    # "deprecated" vs "available"
    re.compile(r"\b(deprecated|removed|unsupported|unavailable|obsolete)\b", re.IGNORECASE),
]

# Directional verbs that, when opposite, indicate contradiction
_DIRECTION_PAIRS = {
    frozenset({"import", "export"}),
    frozenset({"read", "write"}),
    frozenset({"load", "save"}),
    frozenset({"input", "output"}),
    frozenset({"encode", "decode"}),
    frozenset({"serialize", "deserialize"}),
}


def _tokenize(text: str) -> list[str]:
    words = re.findall(r"[a-z][a-z0-9_]*", text.lower())
    return [w for w in words if len(w) > 2 and w not in _STOPWORDS]


def _cosine(tokens_a: list[str], tokens_b: list[str]) -> float:
    if not tokens_a or not tokens_b:
        return 0.0
    all_docs = [tokens_a, tokens_b]
    df: dict[str, int] = {}
    for doc in all_docs:
        for term in set(doc):
            df[term] = df.get(term, 0) + 1
    idf = {term: math.log(1 + 2 / count) for term, count in df.items()}

    def to_tfidf(tokens: list[str]) -> dict[str, float]:
        tf = Counter(tokens)
        total = len(tokens) or 1
        return {t: (c / total) * idf.get(t, 0.0) for t, c in tf.items()}

    vec_a = to_tfidf(tokens_a)
    vec_b = to_tfidf(tokens_b)
    keys = set(vec_a) & set(vec_b)
    if not keys:
        return 0.0
    dot = sum(vec_a[k] * vec_b[k] for k in keys)
    mag_a = math.sqrt(sum(v * v for v in vec_a.values()))
    mag_b = math.sqrt(sum(v * v for v in vec_b.values()))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


# ── Claim extraction ─────────────────────────────────────────────────────────

def _extract_claims_from_page(filepath: Path) -> list[dict]:
    """Extract factual claim sentences from a page's evidence frontmatter."""
    from core.markdown import parse_frontmatter  # noqa: E402

    fm = parse_frontmatter(filepath)
    evidence = fm.get("evidence")
    if not evidence or not isinstance(evidence, dict):
        return []

    claims = evidence.get("claims") or []
    return [{"claim_id": c, "file": str(filepath)} for c in claims if isinstance(c, str)]


# ── Contradiction detection ──────────────────────────────────────────────────

def _has_negation(text: str) -> bool:
    """Check if text contains negation markers."""
    return any(p.search(text) for p in _NEGATION_PATTERNS)


def _has_direction_conflict(text_a: str, text_b: str) -> bool:
    """Check if two texts have opposing directional verbs."""
    words_a = set(re.findall(r"[a-z]+", text_a.lower()))
    words_b = set(re.findall(r"[a-z]+", text_b.lower()))
    for pair in _DIRECTION_PAIRS:
        if pair <= (words_a | words_b) and not pair <= words_a and not pair <= words_b:
            # One word in A, the other in B
            return True
    return False


def detect_contradictions(
    claims_with_text: list[dict],
    *,
    cluster_threshold: float = _CLUSTER_THRESHOLD,
) -> list[dict]:
    """Detect contradictions among claim texts.

    Args:
        claims_with_text: List of {claim_id, text, file} dicts.
        cluster_threshold: Cosine threshold for topic clustering.

    Returns: List of contradiction dicts with claim pairs and reasoning.
    """
    contradictions = []

    for i, ca in enumerate(claims_with_text):
        for j in range(i + 1, len(claims_with_text)):
            cb = claims_with_text[j]
            # Skip same-page claims (same page can't contradict itself for this analysis)
            if ca["file"] == cb["file"]:
                continue

            text_a = ca.get("text", "")
            text_b = cb.get("text", "")
            if not text_a or not text_b:
                continue

            tokens_a = _tokenize(text_a)
            tokens_b = _tokenize(text_b)
            similarity = _cosine(tokens_a, tokens_b)

            # Only check for contradiction if claims are about the same topic
            if similarity < cluster_threshold:
                continue

            # Check for contradiction signals
            reasons = []
            neg_a = _has_negation(text_a)
            neg_b = _has_negation(text_b)
            if neg_a != neg_b:
                reasons.append("negation_mismatch")

            if _has_direction_conflict(text_a, text_b):
                reasons.append("direction_conflict")

            if reasons:
                contradictions.append({
                    "claim_a": ca["claim_id"],
                    "claim_b": cb["claim_id"],
                    "file_a": ca["file"],
                    "file_b": cb["file"],
                    "text_a": text_a,
                    "text_b": text_b,
                    "similarity": round(similarity, 4),
                    "reasons": reasons,
                })

    return contradictions


# ── Product scan ─────────────────────────────────────────────────────────────

_SITE_PATTERNS = (
    "docs.aspose.org/en/{family}/{platform}",
    "kb.aspose.org/en/{family}/{platform}",
    "products.aspose.org/en/{family}/{platform}",
    "blog.aspose.org/{family}/{platform}",
)


def scan_product(
    family: str,
    platform: str,
    *,
    content_root: Path = Path("content"),
    knowledge_root: Path = Path("knowledge"),
) -> dict:
    """Scan a product for cross-page factual contradictions.

    Returns a report dict with contradictions found.
    """
    from content_discovery import LOCALE_RE, _is_draft  # noqa: E402
    from knowledge_core import Knowledge  # noqa: E402

    knowledge = Knowledge(family, platform, knowledge_root=knowledge_root)

    # Build claim_id → text lookup from knowledge
    claim_texts: dict[str, str] = {}
    claims_path = knowledge_root / family / platform / "merged" / "claims.json"
    if claims_path.exists():
        raw = json.loads(claims_path.read_text(encoding="utf-8"))
        for c in raw:
            cid = c.get("claim_id", "")
            text = c.get("text", "")
            if cid and text:
                claim_texts[cid] = text

    # Collect all page claims with text
    all_claims: list[dict] = []
    files_scanned = 0
    for pattern in _SITE_PATTERNS:
        site_root = content_root / Path(pattern.format(family=family, platform=platform))
        if not site_root.exists():
            continue
        for path in sorted(site_root.rglob("*.md")):
            if LOCALE_RE.search(path.name):
                continue
            if _is_draft(path):
                continue
            files_scanned += 1
            page_claims = _extract_claims_from_page(path)
            for pc in page_claims:
                text = claim_texts.get(pc["claim_id"], "")
                if text:
                    all_claims.append({**pc, "text": text})

    contradictions = detect_contradictions(all_claims)

    return {
        "family": family,
        "platform": platform,
        "files_scanned": files_scanned,
        "claims_analyzed": len(all_claims),
        "contradictions_found": len(contradictions),
        "contradictions": contradictions,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cross_page_consistency",
        description="Detect cross-page factual contradictions within a product",
    )
    parser.add_argument("family", help="Product family")
    parser.add_argument("platform", help="Platform")
    parser.add_argument("--content-root", type=Path, default=Path("content"))
    parser.add_argument("--knowledge-root", type=Path, default=Path("knowledge"))
    parser.add_argument("--output", type=Path, help="Output report path")
    args = parser.parse_args(argv)

    report = scan_product(
        args.family,
        args.platform,
        content_root=args.content_root,
        knowledge_root=args.knowledge_root,
    )

    output = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")

    sys.stdout.buffer.write(output.encode("utf-8"))
    sys.stdout.buffer.write(b"\n")
    return 1 if report["contradictions_found"] else 0


if __name__ == "__main__":
    sys.exit(main())
