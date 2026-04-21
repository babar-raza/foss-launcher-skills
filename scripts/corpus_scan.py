"""Golden corpus scanner — extract style/structure profiles from existing content.

Usage:
    python scripts/corpus_scan.py {family} {platform} {site-type}

Reads existing content pages from the content repo (resolved via config),
extracts structural and stylistic patterns, merges golden corpus data from
golden/_index.json, and writes an enriched corpus profile that generation
skills use for structural consistency and style anchoring.

Output:
    knowledge/{family}/{platform}/_corpus/{site-type}_profile.json
"""
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from config_loader import golden_corpus_config, load_config, resolve_content_repo, resolve_golden_dir, resolve_knowledge_root as _resolve_knowledge_root


def _parse_frontmatter(text):
    """Extract YAML frontmatter fields from markdown text."""
    match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not match:
        return {}
    fields = {}
    for line in match.group(1).splitlines():
        m = re.match(r"^(\w[\w_-]*):\s*(.*)", line)
        if m:
            fields[m.group(1)] = m.group(2).strip()
    return fields


def _extract_structure(text):
    """Extract structural features from markdown content."""
    lines = text.splitlines()

    h2_headings = []
    h3_headings = []
    code_blocks = []
    current_lang = None
    in_code = False
    code_line_count = 0
    shortcodes = set()
    has_dividers = False
    word_count = len(re.findall(r"\w+", text))

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("```"):
            if not in_code:
                in_code = True
                lang = stripped[3:].strip().split()[0] if len(stripped) > 3 else ""
                current_lang = lang or "unknown"
                code_line_count = 0
            else:
                in_code = False
                code_blocks.append({"language": current_lang, "lines": code_line_count})
            continue

        if in_code:
            code_line_count += 1
            continue

        if stripped.startswith("## ") and not stripped.startswith("### "):
            h2_headings.append(stripped[3:].strip())
        elif stripped.startswith("### "):
            h3_headings.append(stripped[4:].strip())
        elif stripped == "---" and not re.match(r"^---\s*$", lines[0] if lines else ""):
            has_dividers = True

        # Detect Hugo shortcodes
        sc_match = re.findall(r"\{\{[<%]\s*(\w+)", stripped)
        for sc in sc_match:
            shortcodes.add(sc)

    return {
        "h2_headings": h2_headings,
        "h3_headings": h3_headings,
        "code_blocks": code_blocks,
        "shortcodes": sorted(shortcodes),
        "has_dividers": has_dividers,
        "word_count": word_count,
    }


def _scan_pages(content_dir, min_words):
    """Scan all markdown pages in a content directory."""
    pages = []
    if not content_dir.is_dir():
        return pages

    for md_file in sorted(content_dir.rglob("*.md")):
        try:
            text = md_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        fm = _parse_frontmatter(text)
        structure = _extract_structure(text)

        if structure["word_count"] < min_words:
            continue

        pages.append({
            "path": str(md_file.relative_to(content_dir)),
            "abs_path": str(md_file),
            "frontmatter": fm,
            "structure": structure,
        })

    return pages


def _aggregate_profile(pages, family, platform, site_type, content_dir):
    """Build an aggregate profile from scanned pages."""
    if not pages:
        return {
            "family": family,
            "platform": platform,
            "site_type": site_type,
            "scanned_at": datetime.now(timezone.utc).isoformat(),
            "content_dir": str(content_dir),
            "page_count": 0,
            "golden_examples": [],
            "frontmatter_schema": {},
            "section_pattern": {},
            "code_style": {},
            "link_patterns": {},
        }

    # Frontmatter schema
    fm_fields = Counter()
    fm_type_values = Counter()
    for p in pages:
        for key in p["frontmatter"]:
            fm_fields[key] += 1
        if "type" in p["frontmatter"]:
            fm_type_values[p["frontmatter"]["type"]] += 1

    threshold = len(pages) * 0.5
    required = sorted(k for k, v in fm_fields.items() if v >= threshold)
    optional = sorted(k for k, v in fm_fields.items() if v < threshold and v >= 2)
    type_value = fm_type_values.most_common(1)[0][0] if fm_type_values else ""

    # Section patterns
    all_h2 = Counter()
    h2_counts = []
    h3_counts = []
    divider_count = 0
    for p in pages:
        s = p["structure"]
        h2_counts.append(len(s["h2_headings"]))
        h3_counts.append(len(s["h3_headings"]))
        for h in s["h2_headings"]:
            all_h2[h] += 1
        if s["has_dividers"]:
            divider_count += 1

    common_sections = [h for h, c in all_h2.most_common(10) if c >= 2]

    # Code style
    all_langs = Counter()
    block_counts = []
    block_lines = []
    for p in pages:
        blocks = p["structure"]["code_blocks"]
        block_counts.append(len(blocks))
        for b in blocks:
            all_langs[b["language"]] += 1
            block_lines.append(b["lines"])

    # Shortcodes
    all_shortcodes = Counter()
    for p in pages:
        for sc in p["structure"]["shortcodes"]:
            all_shortcodes[sc] += 1

    # Golden examples — top N by word count
    corpus_cfg = golden_corpus_config()
    sample_count = corpus_cfg.get("sample_count", 3)
    sorted_pages = sorted(pages, key=lambda p: p["structure"]["word_count"], reverse=True)
    golden = [p["path"] for p in sorted_pages[:sample_count]]

    return {
        "family": family,
        "platform": platform,
        "site_type": site_type,
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "content_dir": str(content_dir),
        "page_count": len(pages),
        "golden_examples": golden,
        "frontmatter_schema": {
            "required_fields": required,
            "optional_fields": optional,
            "type_value": type_value,
        },
        "section_pattern": {
            "typical_h2_count": round(sum(h2_counts) / len(h2_counts)) if h2_counts else 0,
            "typical_h3_count": round(sum(h3_counts) / len(h3_counts)) if h3_counts else 0,
            "uses_dividers": divider_count > len(pages) * 0.5,
            "common_sections": common_sections,
            "shortcodes": [sc for sc, _ in all_shortcodes.most_common(5)] if all_shortcodes else [],
        },
        "code_style": {
            "languages": [lang for lang, _ in all_langs.most_common(5)] if all_langs else [],
            "avg_blocks_per_page": round(sum(block_counts) / len(block_counts), 1) if block_counts else 0,
            "avg_block_lines": round(sum(block_lines) / len(block_lines), 1) if block_lines else 0,
        },
    }


# Site-type to golden page_role mapping
_SITE_TYPE_ROLES = {
    "docs": ["workflow_page", "installation", "license", "section_index"],
    "blog": ["feature_blog"],
    "kb": ["howto_article", "faq", "troubleshooting", "feature_showcase"],
    "products": ["landing"],
    "reference": ["api_reference"],
}


def _load_golden_data(site_type):
    """Load golden index and extract data relevant to a site type.

    Returns a dict with golden_anchors, golden_structural_contracts,
    golden_style_rubric, available_variants, or empty dict on failure.
    """
    try:
        golden_dir = resolve_golden_dir()
        index_path = golden_dir / "_index.json"
        if not index_path.is_file():
            print(f"  WARNING: Golden index not found: {index_path}", file=sys.stderr)
            return {}

        index = json.loads(index_path.read_text(encoding="utf-8"))
    except Exception:
        return {}

    target_roles = _SITE_TYPE_ROLES.get(site_type, [])
    if not target_roles:
        return {}

    # Collect matching golden pages
    anchors = []
    structural_contracts = {}
    style_rubric = None
    available_variants = set()

    for page in index.get("pages", []):
        if page["page_role"] not in target_roles:
            continue

        available_variants.add(page["variant"])
        anchors.append({
            "page_role": page["page_role"],
            "variant": page["variant"],
            "grade": page["grade"],
            "source_path": page["source_path"],
            "total_word_count": page["total_word_count"],
            "section_count": len(page.get("sections", [])),
        })

        # Collect structural contracts from all sections
        for section in page.get("sections", []):
            key = f"{page['page_role']}/{page['variant']}/{section['heading']}"
            structural_contracts[key] = section.get("structural_contract", "")

        # Use first matching style rubric (prefer standard variant)
        if style_rubric is None or page["variant"] == "standard":
            style_rubric = page.get("style_rubric", {})

    # Determine variant selection from tier_selection map
    tier_selection = index.get("tier_selection", {"C": "minimal", "B": "standard", "A": "standard"})

    return {
        "golden_anchors": anchors,
        "golden_structural_contracts": structural_contracts,
        "golden_style_rubric": style_rubric or {},
        "available_variants": sorted(available_variants),
        "tier_selection": tier_selection,
    }


def _determine_richness_tier(page_count, family, platform):
    """Determine richness tier based on published content and API surface.

    Tier A: >= 10 published pages AND >= 50 API classes
    Tier B: >= 5 published pages OR >= 20 API classes
    Tier C: everything else
    """
    # Check API surface size from knowledge model if available
    api_class_count = 0
    try:
        index_path = _resolve_knowledge_root() / family / platform / "merged" / "index.json"
        if index_path.is_file():
            kindex = json.loads(index_path.read_text(encoding="utf-8"))
            api_class_count = len(kindex.get("classes", []))
    except Exception:
        pass

    if page_count >= 10 and api_class_count >= 50:
        return "A"
    if page_count >= 5 or api_class_count >= 20:
        return "B"
    return "C"


def scan(family, platform, site_type):
    """Run the corpus scan for a given product and site type."""
    config = load_config()
    sites = config.get("sites", {})

    if site_type not in sites:
        print(f"ERROR: Unknown site type '{site_type}'. Valid: {list(sites.keys())}")
        return False

    template = sites[site_type].get("content_path", "")
    path_str = template.replace("{family}", family).replace("{platform}", platform)
    content_repo = resolve_content_repo()
    content_dir = content_repo / path_str

    print(f"Corpus scan: {family}/{platform} [{site_type}]")
    print(f"  Content dir: {content_dir}")

    if not content_dir.is_dir():
        print(f"  WARNING: Content directory does not exist: {content_dir}")
        print(f"  Set content_repo in config.yaml or $CONTENT_REPO_PATH env var")
        return False

    corpus_cfg = golden_corpus_config()
    min_words = corpus_cfg.get("min_words", 200)
    pages = _scan_pages(content_dir, min_words)
    print(f"  Pages found: {len(pages)} (min {min_words} words)")

    profile = _aggregate_profile(pages, family, platform, site_type, content_dir)

    # Merge golden corpus data into profile
    golden_data = _load_golden_data(site_type)
    if golden_data:
        profile.update(golden_data)
        richness_tier = _determine_richness_tier(len(pages), family, platform)
        profile["richness_tier"] = richness_tier
        tier_map = golden_data.get("tier_selection", {"C": "minimal", "B": "standard", "A": "standard"})
        profile["selected_variant"] = tier_map.get(richness_tier, "standard")
        print(f"  Golden anchors: {len(golden_data.get('golden_anchors', []))}")
        print(f"  Richness tier: {richness_tier} -> variant: {profile['selected_variant']}")
    else:
        print(f"  Golden index: not found (run: python scripts/golden_index.py)")
        profile["richness_tier"] = "C"
        profile["selected_variant"] = "standard"

    # Write profile
    profile_dir_name = corpus_cfg.get("profile_dir", "_corpus")
    out_dir = _resolve_knowledge_root() / family / platform / profile_dir_name
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{site_type}_profile.json"
    out_path.write_text(json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"  Profile written: {out_path}")
    print(f"  Golden examples: {profile['golden_examples']}")
    print(f"  Common sections: {profile['section_pattern'].get('common_sections', [])}")
    return True


def main():
    if len(sys.argv) < 4:
        print("Usage: python scripts/corpus_scan.py {family} {platform} {site-type}")
        print("Example: python scripts/corpus_scan.py 3d python docs")
        print("Valid site types: docs, blog, kb, products, reference")
        sys.exit(1)

    family = sys.argv[1]
    platform = sys.argv[2]
    site_type = sys.argv[3]

    success = scan(family, platform, site_type)
    print(f"\nCORPUS-SCAN: {'PASS' if success else 'FAIL'}")
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
