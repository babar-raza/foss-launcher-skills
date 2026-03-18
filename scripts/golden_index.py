"""Golden corpus indexer — parse golden exemplar files and produce a static JSON index.

Ported from foss-launcher's golden_loader.py. Produces golden/_index.json which
skills and scripts consume for structural contracts, style rubrics, and variant selection.

Usage:
    python scripts/golden_index.py [--golden-dir golden/] [--output golden/_index.json]
"""
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_STOP_WORDS: frozenset = frozenset({
    "a", "an", "the", "and", "or", "of", "to", "in", "for", "on",
    "with", "at", "by", "from", "as", "is", "are", "was", "be",
})

_VARIANT_RE = re.compile(r"\.variant-([a-z]+)")
_FENCE_RE = re.compile(r"```[^\n]*\n.*?```", re.DOTALL)

# ---------------------------------------------------------------------------
# Role/variant inference from file path
# ---------------------------------------------------------------------------

def _infer_role_variant(path: Path, golden_dir: Path) -> tuple:
    """Infer (page_role, variant) from file path relative to golden_dir."""
    rel = path.relative_to(golden_dir)
    parts = rel.parts
    name = path.stem

    # Extract variant from filename
    m = _VARIANT_RE.search(name)
    variant = m.group(1) if m else "standard"

    subdomain = parts[0] if parts else ""

    if "_index" in name:
        return "section_index", variant

    if subdomain == "docs.aspose.org":
        if "getting-started" in parts:
            if "installation" in name:
                return "installation", variant
            if "license" in name:
                return "license", variant
        if "developer-guide" in parts:
            return "workflow_page", variant
    elif subdomain == "kb.aspose.org":
        base = _VARIANT_RE.sub("", name)
        if base == "faq":
            return "faq", variant
        if base == "troubleshooting":
            return "troubleshooting", variant
        if base in ("feature-showcase", "use-cases"):
            return "feature_showcase", variant
        return "howto_article", variant
    elif subdomain == "reference.aspose.org":
        return "api_reference", variant
    elif subdomain == "products.aspose.org":
        return "landing", variant
    elif subdomain == "blog.aspose.org":
        return "feature_blog", variant

    return parts[-2] if len(parts) >= 2 else "unknown", variant


# ---------------------------------------------------------------------------
# Section parsing with structural fingerprints
# ---------------------------------------------------------------------------

def _parse_sections(body: str) -> list:
    """Split markdown body on ## headings and extract structural fingerprints."""
    parts = re.split(r"\n(?=#{2,6}\s)", body.strip())
    sections = []

    for part in parts:
        part = part.strip()
        if not part:
            continue
        heading_match = re.match(r"^(#{2,6})\s+(.+)", part)
        if not heading_match:
            continue

        heading = heading_match.group(2).strip()
        raw = part
        excerpt = raw[:600]

        # Prose word count (exclude code, headings, tables)
        no_code = _FENCE_RE.sub("", raw)
        no_code = re.sub(r"`[^`]+`", "", no_code)
        no_code = re.sub(r"^#{1,6}\s+.+$", "", no_code, flags=re.MULTILINE)
        no_code = re.sub(r"^\|.+$", "", no_code, flags=re.MULTILINE)
        words = [w for w in no_code.split() if w]
        word_count = len(words)

        has_code = bool(re.search(r"```", raw))
        has_list = bool(re.search(r"^\s*[-*]\s", raw, re.MULTILINE))
        has_table = bool(re.search(r"^\|", raw, re.MULTILINE))

        if word_count < 5:
            continue

        # Structural fingerprint counts
        code_block_count = len(re.findall(r"```[^\n]*\n[\s\S]*?```", raw))
        list_block_count = len(re.findall(r"^\s*[-*]\s", raw, re.MULTILINE))
        table_count = len(re.findall(r"^\|[-|]+\|", raw, re.MULTILINE))
        heading_count = len(re.findall(r"^#{2,6}\s", raw, re.MULTILINE))

        prose_chars = len(no_code.strip())
        code_chars = sum(len(m) for m in re.findall(r"```[^\n]*\n[\s\S]*?```", raw, re.DOTALL))
        code_to_prose_ratio = round(code_chars / max(prose_chars + code_chars, 1), 4)

        # Block sequence analysis
        block_sequence = []
        lines = raw.splitlines()
        in_fence = False
        pending_paragraph = []

        for line in lines:
            if line.startswith("```"):
                if in_fence:
                    in_fence = False
                else:
                    if pending_paragraph:
                        block_sequence.append("paragraph")
                        pending_paragraph = []
                    block_sequence.append("code")
                    in_fence = True
            elif in_fence:
                pass
            elif re.match(r"^\s*[-*]\s", line):
                if pending_paragraph:
                    block_sequence.append("paragraph")
                    pending_paragraph = []
                if not block_sequence or block_sequence[-1] != "list":
                    block_sequence.append("list")
            elif re.match(r"^\|", line):
                if pending_paragraph:
                    block_sequence.append("paragraph")
                    pending_paragraph = []
                if not block_sequence or block_sequence[-1] != "table":
                    block_sequence.append("table")
            elif line.strip() and not re.match(r"^#{1,6}\s", line):
                pending_paragraph.append(line)
            elif not line.strip() and pending_paragraph:
                block_sequence.append("paragraph")
                pending_paragraph = []

        if pending_paragraph:
            block_sequence.append("paragraph")

        # Error handling detection
        has_error_handling = bool(re.search(r'try:|except |try\s*\{|catch\s*\(', raw))
        has_output_verification = bool(re.search(
            r'Console\.Write|print\(|assert |\.ToString\(\)', raw, re.IGNORECASE
        ))

        # Link count
        link_count = len(re.findall(r'\[.+?\]\(.+?\)', raw))

        # Use-case bullets after code
        use_case_bullet_count = 0
        after_code = False
        uc_in_fence = False
        for line in lines:
            if line.startswith("```"):
                if not uc_in_fence:
                    uc_in_fence = True
                    after_code = False
                else:
                    uc_in_fence = False
                    after_code = True
            elif uc_in_fence:
                pass
            elif after_code and re.match(r"^\s*[-*]\s", line):
                use_case_bullet_count += 1
            elif after_code and line.strip() and not re.match(r"^\s*[-*]\s", line):
                after_code = False

        # Prose-before-code ratio
        if code_block_count == 0:
            prose_before_code_ratio = 0.0
        else:
            fences_with_prose = 0
            had_prose = False
            in_f = False
            for line in lines:
                if line.startswith("```"):
                    if not in_f:
                        if had_prose:
                            fences_with_prose += 1
                        had_prose = False
                        in_f = True
                    else:
                        in_f = False
                elif not in_f and line.strip() and not re.match(r"^#{1,6}\s|^\s*[-*]\s|^\|", line):
                    had_prose = True
            prose_before_code_ratio = round(fences_with_prose / code_block_count, 4)

        # Build structural contract string
        contract_blocks = ["paragraph"]
        if code_block_count > 0:
            contract_blocks.append(f"code ({code_block_count})")
        if list_block_count > 0:
            contract_blocks.append(f"list ({list_block_count})")
        if table_count > 0:
            contract_blocks.append(f"table ({table_count})")
        sequence_str = " → ".join(contract_blocks)
        structural_contract = (
            f"Block sequence (minimum): {sequence_str}\n"
            f"Target depth: ~{word_count} prose words | "
            f"Code blocks: >={code_block_count} | Lists: >={list_block_count} | Tables: >={table_count}\n"
            f"Rule: include ALL listed block types at minimum — expand further to fully cover the topic."
        )

        sections.append({
            "heading": heading,
            "word_count": word_count,
            "code_block_count": code_block_count,
            "list_block_count": list_block_count,
            "table_count": table_count,
            "heading_count": heading_count,
            "code_to_prose_ratio": code_to_prose_ratio,
            "block_sequence": block_sequence,
            "has_code": has_code,
            "has_list": has_list,
            "has_table": has_table,
            "has_error_handling": has_error_handling,
            "has_output_verification": has_output_verification,
            "link_count": link_count,
            "use_case_bullet_count": use_case_bullet_count,
            "prose_before_code_ratio": prose_before_code_ratio,
            "structural_contract": structural_contract,
            "excerpt": excerpt,
        })

    return sections


# ---------------------------------------------------------------------------
# File parsing
# ---------------------------------------------------------------------------

def _parse_golden_file(path: Path, golden_dir: Path) -> dict | None:
    """Parse a single golden .md file into a structured dict."""
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeDecodeError):
        return None

    if not raw.strip():
        return None

    page_role, variant = _infer_role_variant(path, golden_dir)
    rel = path.relative_to(golden_dir)
    subdomain = rel.parts[0] if rel.parts else ""

    # Strip GOLDEN REFERENCE comment
    content = raw
    if raw.startswith("<!--"):
        end_comment = raw.find("-->")
        if end_comment != -1:
            content = raw[end_comment + 3:].lstrip("\n")

    # Parse grade from frontmatter
    grade = "A"
    body = content
    if content.startswith("---"):
        end = content.find("\n---", 3)
        if end != -1:
            fm_text = content[3:end]
            for line in fm_text.splitlines():
                if line.startswith("grade:"):
                    raw_grade = line.split(":", 1)[1].strip().strip('"').strip("'")
                    if raw_grade and raw_grade[0].upper() in ("A", "B", "C", "D", "F"):
                        grade = raw_grade
                    break
            body = content[end + 4:]

    sections = _parse_sections(body)
    total_word_count = sum(s["word_count"] for s in sections)

    if not sections:
        return None

    # Derive style rubric
    sections_with_code = [s for s in sections if s["has_code"]]
    pbcr_values = [s["prose_before_code_ratio"] for s in sections_with_code]
    avg_pbcr = sum(pbcr_values) / len(pbcr_values) if pbcr_values else 1.0

    total_code_blocks = sum(s["code_block_count"] for s in sections)

    style_rubric = {
        "prose_before_code": avg_pbcr >= 0.5,
        "use_case_required": any(s["use_case_bullet_count"] > 0 for s in sections),
        "code_completeness_required": any(
            s["has_error_handling"] or s["has_output_verification"]
            for s in sections
        ),
        "avg_sentence_length": max(15, min(35, total_word_count // max(len(sections) * 3, 1))),
        "min_code_variety": max(1, min(total_code_blocks, 3)),
    }

    return {
        "page_role": page_role,
        "variant": variant,
        "subdomain": subdomain,
        "grade": grade,
        "source_path": str(rel).replace("\\", "/"),
        "total_word_count": total_word_count,
        "sections": sections,
        "style_rubric": style_rubric,
    }


# ---------------------------------------------------------------------------
# Index builder
# ---------------------------------------------------------------------------

def build_index(golden_dir: Path) -> dict:
    """Build the complete golden index from all .md files in golden_dir."""
    pages = []
    role_variants: dict[str, set] = {}

    for md_file in sorted(golden_dir.rglob("*.md")):
        if md_file.name == "README.md":
            continue

        page = _parse_golden_file(md_file, golden_dir)
        if page is None:
            continue

        pages.append(page)

        role = page["page_role"]
        if role not in role_variants:
            role_variants[role] = set()
        role_variants[role].add(page["variant"])

    # Build role_variant_map with sorted lists
    role_variant_map = {
        role: sorted(variants)
        for role, variants in sorted(role_variants.items())
    }

    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "page_count": len(pages),
        "pages": pages,
        "role_variant_map": role_variant_map,
        "tier_selection": {
            "C": "minimal",
            "B": "standard",
            "A": "standard",
        },
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Build golden corpus index")
    parser.add_argument("--golden-dir", default=None, help="Path to golden/ directory")
    parser.add_argument("--output", default=None, help="Output path for _index.json")
    args = parser.parse_args()

    # Resolve golden dir
    if args.golden_dir:
        golden_dir = Path(args.golden_dir)
    else:
        # Try importing config_loader
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            from config_loader import resolve_golden_dir
            golden_dir = resolve_golden_dir()
        except ImportError:
            golden_dir = Path("golden/")

    if not golden_dir.is_dir():
        print(f"ERROR: Golden directory not found: {golden_dir}")
        sys.exit(1)

    print(f"Golden index: scanning {golden_dir}")

    index = build_index(golden_dir)

    # Determine output path
    output_path = Path(args.output) if args.output else golden_dir / "_index.json"
    output_path.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"  Pages indexed: {index['page_count']}")
    print(f"  Roles: {list(index['role_variant_map'].keys())}")
    for role, variants in index["role_variant_map"].items():
        print(f"    {role}: {variants}")
    print(f"  Index written: {output_path}")


if __name__ == "__main__":
    main()
