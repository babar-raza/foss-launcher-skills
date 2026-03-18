"""Golden conformance scorer — measure structural alignment with golden templates.

Computes a continuous conformance score (0.0-1.0) across 5 weighted dimensions:
  1. Section Coverage   (0.25) — fraction of golden sections present
  2. Section Order      (0.15) — Kendall tau correlation on matched ordering
  3. Depth Proportion   (0.25) — cosine similarity of word-count distributions
  4. Block-Type Cover   (0.20) — average Jaccard of block type sets per section
  5. Code Density Align (0.15) — ratio similarity of code-to-prose per section

Ported from foss-launcher's evaluate/checks/golden_conformance.py.

Usage:
    python scripts/golden_conformance.py {content-file-path} {page_role} [--variant standard]

Output:
    reports/conformance/{slug}-conformance.json
"""
import json
import math
import re
import sys
from pathlib import Path

from config_loader import resolve_golden_dir

# Dimension weights (sum to 1.0)
_W_COVERAGE = 0.25
_W_ORDER = 0.15
_W_DEPTH = 0.25
_W_BLOCK_TYPE = 0.20
_W_CODE_DENSITY = 0.15

# Severity thresholds
_THRESHOLD_HIGH = 0.35
_THRESHOLD_MEDIUM = 0.55
_THRESHOLD_LOW = 0.75

_FENCE_RE = re.compile(r"```[^\n]*\n.*?```", re.DOTALL)
_STOP_WORDS = frozenset({
    "a", "an", "the", "and", "or", "of", "to", "in", "for", "on",
    "with", "at", "by", "from", "as", "is", "are", "was", "be",
})


# ---------------------------------------------------------------------------
# Content parsing
# ---------------------------------------------------------------------------

def _split_sections(body: str) -> list:
    """Split markdown body into (heading, body) tuples on ## headings."""
    parts = re.split(r"\n(?=#{2,6}\s)", body.strip())
    sections = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        m = re.match(r"^(#{2,6})\s+(.+)", part)
        if m:
            heading = m.group(2).strip()
            sections.append((heading, part))
        elif not sections:
            # Pre-heading content
            sections.append(("", part))
    return sections


def _prose_word_count(text: str) -> int:
    """Count prose words excluding code, headings, tables."""
    no_code = _FENCE_RE.sub("", text)
    no_code = re.sub(r"`[^`]+`", "", no_code)
    no_code = re.sub(r"^#{1,6}\s+.+$", "", no_code, flags=re.MULTILINE)
    no_code = re.sub(r"^\|.+$", "", no_code, flags=re.MULTILINE)
    return len(no_code.split())


def _get_block_types(text: str) -> set:
    """Extract set of block types from a markdown section."""
    types = set()
    lines = text.splitlines()
    in_fence = False
    has_paragraph = False

    for line in lines:
        if line.startswith("```"):
            if in_fence:
                in_fence = False
            else:
                types.add("code")
                in_fence = True
        elif in_fence:
            pass
        elif re.match(r"^\s*[-*]\s", line):
            types.add("list")
        elif re.match(r"^\|", line):
            types.add("table")
        elif line.strip() and not re.match(r"^#{1,6}\s", line):
            has_paragraph = True

    if has_paragraph:
        types.add("paragraph")
    return types


def _compute_code_ratio(text: str) -> float:
    """Compute code-to-prose character ratio."""
    code_chars = sum(len(m) for m in re.findall(r"```[^\n]*\n[\s\S]*?```", text))
    prose_text = _FENCE_RE.sub("", text)
    prose_text = re.sub(r"^#{1,6}\s+.+$", "", prose_text, flags=re.MULTILINE)
    prose_chars = len(prose_text.strip())
    total = prose_chars + code_chars
    return code_chars / total if total > 0 else 0.0


def _normalize_heading(heading: str) -> str:
    """Lowercase, strip punctuation, remove stop-words."""
    tokens = re.sub(r"[^a-z0-9\s]", "", heading.lower()).split()
    return " ".join(t for t in tokens if t not in _STOP_WORDS)


# ---------------------------------------------------------------------------
# Section matching
# ---------------------------------------------------------------------------

def _match_sections(golden_sections, gen_sections) -> list:
    """Match golden sections to generated sections via heading similarity.

    Returns list of (golden_idx, gen_idx, golden_section, gen_heading, gen_body).
    """
    candidates = []

    for g_idx, gs in enumerate(golden_sections):
        g_heading_norm = _normalize_heading(gs["heading"])
        g_heading_raw = gs["heading"].lower().strip()

        for gen_idx, (gen_heading, gen_body) in enumerate(gen_sections):
            if not gen_heading:
                continue
            gen_norm = _normalize_heading(gen_heading)
            gen_raw = gen_heading.lower().strip()

            # Exact normalized match
            if g_heading_norm == gen_norm:
                candidates.append((g_idx, gen_idx, gs, gen_heading, gen_body, 1.0))
                continue

            # Substring match
            if g_heading_raw in gen_raw or gen_raw in g_heading_raw:
                candidates.append((g_idx, gen_idx, gs, gen_heading, gen_body, 0.8))
                continue

            # Jaccard similarity
            g_words = set(g_heading_norm.split())
            gen_words = set(gen_norm.split())
            if len(g_words) >= 2 and len(gen_words) >= 2:
                intersection = len(g_words & gen_words)
                union = len(g_words | gen_words)
                score = intersection / union if union > 0 else 0.0
                if score >= 0.5:
                    candidates.append((g_idx, gen_idx, gs, gen_heading, gen_body, score))

    # Greedy assignment
    candidates.sort(key=lambda c: (-c[5], c[0], c[1]))
    used_golden = set()
    used_gen = set()
    matched = []
    for g_idx, gen_idx, gs, gen_heading, gen_body, _score in candidates:
        if g_idx not in used_golden and gen_idx not in used_gen:
            matched.append((g_idx, gen_idx, gs, gen_heading, gen_body))
            used_golden.add(g_idx)
            used_gen.add(gen_idx)

    return matched


# ---------------------------------------------------------------------------
# 5 dimensions
# ---------------------------------------------------------------------------

def _dim_section_coverage(golden_sections, matched) -> float:
    total = len(golden_sections)
    if total == 0:
        return 1.0
    return len(matched) / total


def _dim_section_order(matched) -> float:
    n = len(matched)
    if n < 2:
        return 1.0
    pairs = sorted([(g_idx, gen_idx) for g_idx, gen_idx, *_ in matched])
    concordant = 0
    discordant = 0
    for i in range(n):
        for j in range(i + 1, n):
            if pairs[i][1] < pairs[j][1]:
                concordant += 1
            elif pairs[i][1] > pairs[j][1]:
                discordant += 1
    denom = n * (n - 1) / 2
    if denom == 0:
        return 1.0
    tau = (concordant - discordant) / denom
    return (tau + 1.0) / 2.0


def _dim_depth_proportionality(golden_sections, gen_sections, matched) -> float:
    if not matched:
        return 0.0
    golden_total = sum(s["word_count"] for s in golden_sections) or 1
    gen_total = sum(_prose_word_count(body) for _, body in gen_sections) or 1
    golden_vec = []
    gen_vec = []
    for g_idx, gen_idx, gs, gen_heading, gen_body in matched:
        golden_vec.append(gs["word_count"] / golden_total)
        gen_vec.append(_prose_word_count(gen_body) / gen_total)
    return _cosine_similarity(golden_vec, gen_vec)


def _dim_block_type_coverage(matched) -> float:
    if not matched:
        return 0.0
    scores = []
    for g_idx, gen_idx, gs, gen_heading, gen_body in matched:
        golden_types = set(gs.get("block_sequence", []))
        gen_types = _get_block_types(gen_body)
        if not golden_types and not gen_types:
            scores.append(1.0)
        elif not golden_types or not gen_types:
            scores.append(0.0)
        else:
            intersection = len(golden_types & gen_types)
            union = len(golden_types | gen_types)
            scores.append(intersection / union if union > 0 else 0.0)
    return sum(scores) / len(scores) if scores else 0.0


def _dim_code_density_alignment(matched) -> float:
    scores = []
    for g_idx, gen_idx, gs, gen_heading, gen_body in matched:
        golden_ratio = gs.get("code_to_prose_ratio", 0.0)
        if golden_ratio <= 0.0 and not gs.get("has_code", False):
            continue
        gen_ratio = _compute_code_ratio(gen_body)
        diff = abs(golden_ratio - gen_ratio)
        scores.append(max(0.0, 1.0 - diff))
    if not scores:
        return 1.0
    return sum(scores) / len(scores)


def _cosine_similarity(a, b) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0.0 or mag_b == 0.0:
        return 0.0
    return max(0.0, min(1.0, dot / (mag_a * mag_b)))


# ---------------------------------------------------------------------------
# Main scoring
# ---------------------------------------------------------------------------

def score_conformance(content_path: Path, page_role: str, variant: str = "standard") -> dict:
    """Compute conformance score for a content file against golden template."""
    # Load golden index
    golden_dir = resolve_golden_dir()
    index_path = golden_dir / "_index.json"
    if not index_path.is_file():
        return {"error": f"Golden index not found: {index_path}"}

    index = json.loads(index_path.read_text(encoding="utf-8"))

    # Find matching golden page
    golden_page = None
    for page in index.get("pages", []):
        if page["page_role"] == page_role and page["variant"] == variant:
            golden_page = page
            break
    if golden_page is None:
        # Fallback to standard variant
        for page in index.get("pages", []):
            if page["page_role"] == page_role and page["variant"] == "standard":
                golden_page = page
                break
    if golden_page is None:
        return {"error": f"No golden page found for role={page_role}, variant={variant}"}

    golden_sections = golden_page.get("sections", [])
    if not golden_sections:
        return {"error": "Golden page has no sections"}

    # Parse content file
    try:
        content = content_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        return {"error": f"Cannot read content file: {e}"}

    # Strip frontmatter
    body = re.sub(r"^---\n.*?\n---\n?", "", content, flags=re.DOTALL)
    gen_sections = _split_sections(body)
    gen_sections = [(h, b) for h, b in gen_sections if h]

    slug = content_path.stem

    if not gen_sections:
        return {
            "slug": slug,
            "page_role": page_role,
            "variant": variant,
            "conformance_score": 0.0,
            "breakdown": {
                "section_coverage": 0.0,
                "section_order": 0.0,
                "depth_proportionality": 0.0,
                "block_type_coverage": 0.0,
                "code_density_alignment": 0.0,
            },
            "severity": "high",
            "findings": ["No sections found in generated page"],
        }

    # Match sections
    matched = _match_sections(golden_sections, gen_sections)

    # Compute dimensions
    coverage = _dim_section_coverage(golden_sections, matched)
    order = _dim_section_order(matched)
    depth = _dim_depth_proportionality(golden_sections, gen_sections, matched)
    block_type = _dim_block_type_coverage(matched)
    code_density = _dim_code_density_alignment(matched)

    score = (
        _W_COVERAGE * coverage
        + _W_ORDER * order
        + _W_DEPTH * depth
        + _W_BLOCK_TYPE * block_type
        + _W_CODE_DENSITY * code_density
    )

    breakdown = {
        "section_coverage": round(coverage, 4),
        "section_order": round(order, 4),
        "depth_proportionality": round(depth, 4),
        "block_type_coverage": round(block_type, 4),
        "code_density_alignment": round(code_density, 4),
    }

    # Determine severity
    if score < _THRESHOLD_HIGH:
        severity = "high"
    elif score < _THRESHOLD_MEDIUM:
        severity = "medium"
    elif score < _THRESHOLD_LOW:
        severity = "low"
    else:
        severity = "none"

    # Build findings
    findings = []
    if coverage < 0.6:
        findings.append(f"Section coverage low ({coverage:.2f}): {len(matched)}/{len(golden_sections)} golden sections matched")
    if order < 0.6:
        findings.append(f"Section order divergence (tau={order:.2f})")
    if depth < 0.6:
        findings.append(f"Depth proportionality low ({depth:.2f}): word count distribution differs from golden")
    if block_type < 0.6:
        findings.append(f"Block type coverage low ({block_type:.2f}): missing required block types")
    if code_density < 0.6:
        findings.append(f"Code density misalignment ({code_density:.2f})")
    if not findings and severity != "none":
        findings.append(f"Minor structural divergence (score={score:.2f})")

    return {
        "slug": slug,
        "page_role": page_role,
        "variant": variant,
        "conformance_score": round(score, 4),
        "breakdown": breakdown,
        "severity": severity,
        "findings": findings,
        "matched_sections": len(matched),
        "golden_sections": len(golden_sections),
        "generated_sections": len(gen_sections),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Score golden conformance of a content page")
    parser.add_argument("content_path", help="Path to the content .md file")
    parser.add_argument("page_role", help="Golden page role (e.g. workflow_page, howto_article)")
    parser.add_argument("--variant", default="standard", help="Golden variant (default: standard)")
    parser.add_argument("--output-dir", default="reports/conformance", help="Output directory for JSON report")
    args = parser.parse_args()

    content_path = Path(args.content_path)
    if not content_path.is_file():
        print(f"ERROR: Content file not found: {content_path}")
        sys.exit(1)

    result = score_conformance(content_path, args.page_role, args.variant)

    if "error" in result:
        print(f"ERROR: {result['error']}")
        sys.exit(1)

    # Write report
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = result["slug"]
    out_path = out_dir / f"{slug}-conformance.json"
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    # Print summary
    score = result["conformance_score"]
    severity = result["severity"]
    print(f"GOLDEN CONFORMANCE — {content_path}")
    print(f"  Page role: {args.page_role} (variant: {args.variant})")
    print(f"  Score: {score:.2f} (severity: {severity})")
    print(f"  Matched: {result['matched_sections']}/{result['golden_sections']} golden sections")
    print(f"  Breakdown:")
    for dim, val in result["breakdown"].items():
        print(f"    {dim}: {val:.4f}")
    if result["findings"]:
        print(f"  Findings:")
        for f in result["findings"]:
            print(f"    - {f}")
    print(f"  Report: {out_path}")


if __name__ == "__main__":
    main()
