"""
claim_parser.py — Parse docs/KB/blog page bodies into atomic claims for
cross-referencing with the semantic delta.

Input:  Single .md file  OR  all pages for a family/platform
Output: claim_map.json per page (written to --output directory)

CLI:
    # Single file:
    PYTHONPATH=scripts/pipeline python -m commands.content.claim_parser \\
        --file content/docs.aspose.org/en/pdf/net/getting-started/installation.md \\
        --output reports/refresh_review/pdf/net/claim_maps/

    # Batch (all pages for a product):
    PYTHONPATH=scripts/pipeline python -m commands.content.claim_parser \\
        pdf net --all-pages --output reports/refresh_review/pdf/net/claim_maps/

Output schema per claim_map.json:
    {
      "page_path": "...",
      "sections": [
        {
          "section_id": "installation",
          "heading": "## Installation",
          "start_line": 45,
          "end_line": 72,
          "claims": [
            {
              "sentence": "...",
              "line_number": 47,
              "detected_symbols": ["Document.Save"],
              "detected_formats": ["PDF"],
              "detected_features": ["converts"],
              "detected_versions": [".NET 6"],
              "claim_type": "API_REFERENCE"
            }
          ]
        }
      ]
    }
"""

from pathlib import Path
import sys

_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))
_LIB_DIR = str(_PIPELINE_ROOT / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

import argparse
import glob
import hashlib
import json
import re
from typing import Any

# ── Configurable defaults ──────────────────────────────────────────────────

_cfg_content_root: str = "content"


def configure(content_root: str | None = None) -> None:
    """Override content root for testing."""
    global _cfg_content_root
    if content_root is not None:
        _cfg_content_root = content_root


# ── Patterns ───────────────────────────────────────────────────────────────

# API symbols: backtick-quoted tokens containing ClassName.Method or just ClassName
_API_SYMBOL_RE = re.compile(r"`([A-Z][A-Za-z0-9_]*(?:\.[A-Z][A-Za-z0-9_]*)*(?:\([^`]*\))?)`")
# Bare uppercase class names in prose (at least 4 chars, mixed-case CamelCase)
_CAMEL_CLASS_RE = re.compile(r"\b([A-Z][a-z][A-Za-z0-9]{2,}(?:\.[A-Z][A-Za-z][A-Za-z0-9]*)*)\b")

# Format names: common document/image formats
_FORMAT_RE = re.compile(
    r"\b(PDF|DOCX?|XLSX?|PPTX?|HTML?|SVG|PNG|JPEG?|TIFF?|BMP|GIF|"
    r"EPUB|XPS|LATEX|TEX|MD|CSV|JSON|XML|RTF|ODT|ODS|ODP|"
    r"MHTML?|PCL|PS|EPS|EMF|WMF|CGM|DICOM|WEBP|HEIC|AVIF|"
    r"cfb|msg|eml|ics|vcf)\b",
    re.IGNORECASE,
)

# Feature claim triggers
_FEATURE_RE = re.compile(
    r"\b(supports?|can |allows?|enables?|converts?|exports?|imports?|"
    r"generates?|creates?|reads?|writes?|renders?|parses?|extracts?|"
    r"merges?|splits?|adds?|removes?|replaces?|edits?|sign|encrypt|"
    r"compress|annotate|watermark)\b",
    re.IGNORECASE,
)

# Version references
_VERSION_RE = re.compile(
    r"\.NET\s*(?:Core\s*)?\d+(?:\.\d+)*|"
    r"\.NET\s+(?:Standard|Framework)\s*\d+(?:\.\d+)*|"
    r"Java\s+\d+|Python\s+\d+(?:\.\d+)*|"
    r"v\d+\.\d+(?:\.\d+)?|"
    r"\b\d{2}\.\d{1,2}(?:\.\d+)?\b",
    re.IGNORECASE,
)

# Claim types
CT_API_REFERENCE = "API_REFERENCE"
CT_FORMAT_CLAIM = "FORMAT_CLAIM"
CT_FEATURE_CLAIM = "FEATURE_CLAIM"
CT_VERSION_CLAIM = "VERSION_CLAIM"
CT_GENERAL = "GENERAL"

# Heading pattern (H2 or H3)
_HEADING_RE = re.compile(r"^(#{2,3})\s+(.+)$")
_FRONTMATTER_SEP = re.compile(r"^---\s*$")


# ── Core parsing ──────────────────────────────────────────────────────────

def _split_frontmatter(content: str) -> tuple[str, str]:
    """Split YAML frontmatter from body. Returns (frontmatter, body)."""
    lines = content.splitlines(keepends=True)
    if not lines or not _FRONTMATTER_SEP.match(lines[0]):
        return "", content

    for i in range(1, len(lines)):
        if _FRONTMATTER_SEP.match(lines[i]):
            frontmatter = "".join(lines[1:i])
            body = "".join(lines[i + 1 :])
            return frontmatter, body

    return "", content


def _slugify(heading: str) -> str:
    """Convert heading text to a section_id slug."""
    slug = heading.lower()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug.strip())
    return slug[:60]


def _segment_sections(body: str) -> list[dict]:
    """Split body text into sections by H2/H3 headings."""
    lines = body.splitlines()
    sections: list[dict] = []
    current: dict | None = None

    for i, line in enumerate(lines):
        m = _HEADING_RE.match(line)
        if m:
            if current is not None:
                current["end_line"] = i - 1
                sections.append(current)
            level = len(m.group(1))
            heading_text = m.group(2).strip()
            current = {
                "section_id": _slugify(heading_text),
                "heading": line.rstrip(),
                "heading_level": level,
                "start_line": i,
                "end_line": i,
                "raw_lines": [],
            }
        elif current is not None:
            current["raw_lines"].append((i, line))

    if current is not None:
        current["end_line"] = len(lines) - 1
        sections.append(current)

    if not sections:
        # No headings — treat whole body as one section
        sections.append(
            {
                "section_id": "body",
                "heading": "",
                "heading_level": 0,
                "start_line": 0,
                "end_line": max(len(lines) - 1, 0),
                "raw_lines": [(i, l) for i, l in enumerate(lines)],
            }
        )

    return sections


def _extract_api_symbols(text: str) -> list[str]:
    """Extract API symbol references from text (backtick and CamelCase prose)."""
    symbols: list[str] = []
    # Backtick-quoted identifiers take priority
    for m in _API_SYMBOL_RE.finditer(text):
        s = m.group(1)
        # Must contain a dot or be pure CamelCase with 5+ chars
        if "." in s or re.match(r"^[A-Z][a-z][A-Za-z]{3,}$", s):
            symbols.append(s)
    # CamelCase bare names in prose (only if no backtick captures already)
    if not symbols:
        for m in _CAMEL_CLASS_RE.finditer(text):
            s = m.group(1)
            if len(s) >= 5 and not s.isupper():
                symbols.append(s)
    return list(dict.fromkeys(symbols))  # deduplicate preserving order


def _extract_format_claims(text: str) -> list[str]:
    """Extract document format names from text."""
    found = [m.group(0).upper() for m in _FORMAT_RE.finditer(text)]
    return list(dict.fromkeys(found))


def _extract_feature_claims(text: str) -> list[str]:
    """Extract feature-capability keyword matches from text."""
    found = [m.group(0).lower().rstrip("s") for m in _FEATURE_RE.finditer(text)]
    return list(dict.fromkeys(found))


def _extract_version_claims(text: str) -> list[str]:
    """Extract version/platform references from text."""
    found = [m.group(0) for m in _VERSION_RE.finditer(text)]
    return list(dict.fromkeys(found))


def _classify_claim(symbols: list, formats: list, features: list, versions: list) -> str:
    """Assign primary claim type based on detected elements."""
    if symbols:
        return CT_API_REFERENCE
    if formats:
        return CT_FORMAT_CLAIM
    if features:
        return CT_FEATURE_CLAIM
    if versions:
        return CT_VERSION_CLAIM
    return CT_GENERAL


def _parse_section_claims(section: dict) -> list[dict]:
    """Extract claims from a section's raw lines."""
    claims: list[dict] = []
    for line_no, line in section["raw_lines"]:
        line_text = line.strip()
        if not line_text or line_text.startswith("```") or line_text.startswith("#"):
            continue

        symbols = _extract_api_symbols(line_text)
        formats = _extract_format_claims(line_text)
        features = _extract_feature_claims(line_text)
        versions = _extract_version_claims(line_text)

        if not (symbols or formats or features or versions):
            continue

        claims.append(
            {
                "sentence": line_text[:300],
                "line_number": line_no,
                "detected_symbols": symbols,
                "detected_formats": formats,
                "detected_features": features,
                "detected_versions": versions,
                "claim_type": _classify_claim(symbols, formats, features, versions),
            }
        )
    return claims


def parse_page(page_path: str) -> dict:
    """
    Parse a single .md file into a claim map.

    Returns the claim_map dict (not written to disk).
    """
    content = Path(page_path).read_text(encoding="utf-8")
    _, body = _split_frontmatter(content)
    sections = _segment_sections(body)

    result_sections: list[dict] = []
    for sec in sections:
        claims = _parse_section_claims(sec)
        result_sections.append(
            {
                "section_id": sec["section_id"],
                "heading": sec["heading"],
                "start_line": sec["start_line"],
                "end_line": sec["end_line"],
                "claims": claims,
            }
        )

    return {
        "page_path": page_path,
        "sections": result_sections,
    }


def _discover_pages(family: str, platform: str) -> list[str]:
    """Discover all docs/KB/blog .md pages for a family/platform."""
    patterns = [
        f"{_cfg_content_root}/docs.aspose.org/en/{family}/{platform}/**/*.md",
        f"{_cfg_content_root}/kb.aspose.org/en/{family}/{platform}/**/*.md",
        f"{_cfg_content_root}/products.aspose.org/en/{family}/{platform}/**/*.md",
        f"{_cfg_content_root}/blog.aspose.org/{family}/{platform}/**/*.md",
    ]
    pages: list[str] = []
    for pattern in patterns:
        # glob.glob's recursive "**" segment is joined with os.sep on Windows,
        # producing mixed-separator paths (e.g. ".../go\\_index.md") that no
        # longer match the forward-slash page_path convention used everywhere
        # else in the pipeline (scope.json, page_impact.json, page_decisions).
        pages.extend(
            Path(p).as_posix() for p in glob.glob(pattern, recursive=True)
        )
    return sorted(pages)


def run_file(page_path: str, output_dir: str) -> dict:
    """Parse a single file and write claim_map.json to output_dir."""
    claim_map = parse_page(page_path)
    # Truncate + hash-suffix the slug (mirrors refresh_oracle.py's
    # _emit_verdict, the established precedent for this exact problem): a
    # long content page path under output_dir's own deeply-nested run
    # directory can push the full file path over Windows' 260-char MAX_PATH,
    # crashing open() with a FileNotFoundError that looks like a missing
    # directory (mkdir below succeeds fine -- the final open() is what
    # fails). The filename itself is never read back (body_impact.py globs
    # `*.claim_map.json` and keys results by the `page_path` field inside
    # each file, not the filename), so truncation is safe. Found live
    # 2026-08-28, cells/typescript.
    normalized_path = page_path.replace("\\", "/")
    digest = hashlib.sha1(normalized_path.encode("utf-8")).hexdigest()[:10]
    slug_base = page_path.replace("/", "_").replace("\\", "_").replace(":", "")[:80]
    slug = f"{slug_base}_{digest}"
    out = Path(output_dir) / f"{slug}.claim_map.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(claim_map, f, indent=2)
    return claim_map


def run_batch(family: str, platform: str, output_dir: str) -> list[dict]:
    """Parse all pages for a family/platform and write claim maps."""
    pages = _discover_pages(family, platform)
    results = []
    for page in pages:
        claim_map = run_file(page, output_dir)
        results.append(claim_map)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "claim_parser — Parse docs/KB/blog page bodies into atomic claims "
            "for cross-referencing with the semantic delta."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Single file:
  PYTHONPATH=scripts/pipeline python -m commands.content.claim_parser \\
      --file content/docs.aspose.org/en/pdf/net/getting-started/installation.md \\
      --output reports/refresh_review/pdf/net/claim_maps/

  # Batch mode (all pages for product):
  PYTHONPATH=scripts/pipeline python -m commands.content.claim_parser \\
      pdf net --all-pages --output reports/refresh_review/pdf/net/claim_maps/
        """,
    )
    parser.add_argument("family", nargs="?", help="Product family (e.g. pdf, 3d)")
    parser.add_argument("platform", nargs="?", help="Platform (e.g. net, java)")
    parser.add_argument("--file", default=None, help="Single .md file to parse")
    parser.add_argument("--all-pages", action="store_true", help="Parse all pages for family/platform")
    parser.add_argument(
        "--output",
        default=None,
        help="Output directory for claim_map JSON files",
    )
    args = parser.parse_args()

    if args.file:
        out_dir = args.output or "reports/refresh_review/claim_maps"
        result = run_file(args.file, out_dir)
        total_claims = sum(len(s["claims"]) for s in result["sections"])
        print(f"claim_parser: {args.file}")
        print(f"  sections : {len(result['sections'])}")
        print(f"  claims   : {total_claims}")
        print(f"  output   : {out_dir}")

    elif args.all_pages and args.family and args.platform:
        out_dir = args.output or f"reports/refresh_review/{args.family}/{args.platform}/claim_maps"
        results = run_batch(args.family, args.platform, out_dir)
        total_claims = sum(
            len(s["claims"]) for r in results for s in r["sections"]
        )
        print(f"claim_parser: {args.family}/{args.platform}")
        print(f"  pages    : {len(results)}")
        print(f"  claims   : {total_claims}")
        print(f"  output   : {out_dir}")

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
