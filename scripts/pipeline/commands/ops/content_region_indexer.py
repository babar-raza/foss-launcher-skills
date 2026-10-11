"""content_region_indexer.py — Build a content region index for S-84 handler dispatch.

CONTRACT: scripts/pipeline/commands/ops/content_region_indexer.py
  purpose: Walk English content pages for a product and index which files contain
           install command blocks, format tables, feature-list pages, and code
           blocks with package coordinates (groupId, canonical import).
  inputs:  content/{site}/en/{family}/{platform}/**/*.md
           knowledge/{family}/{platform}/merged/model.yaml (for canonical_import)
           knowledge/{family}/{platform}/merged/install.md  (for package identifiers)
  outputs: reports/content_region_index/{family}/{platform}.json
           (gitignored; regenerated at the start of every S-84 run)
  idempotent: yes — overwrites output on each run
  english-only: yes — only walks /en/ paths; rejects locale-suffixed files

Usage:
    .venv/Scripts/python scripts/pipeline/commands/ops/content_region_indexer.py {family} {platform}
    .venv/Scripts/python scripts/pipeline/commands/ops/content_region_indexer.py pdf java
    .venv/Scripts/python scripts/pipeline/commands/ops/content_region_indexer.py --all

Exit codes:
    0  — index written successfully
    1  — fatal error (I/O failure)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

_PIPELINE_DIR = Path(__file__).resolve().parents[2]   # commands/ops/ -> commands/ -> pipeline/
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))

_LIB_DIR = str(Path(__file__).resolve().parents[2] / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from content_discovery import LOCALE_RE  # noqa: E402

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[4]
_REPO_ROOT = _DEFAULT_REPO_ROOT


def configure(*, repo_root: "Path | str | None" = None) -> None:
    """Override module-level path constants for testing."""
    global _REPO_ROOT
    _REPO_ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT


# ------- install block detection -------

# Platform-specific patterns to detect install command blocks in content pages.
# Each tuple: (platform_hint, compiled_regex)
_INSTALL_PATTERNS: tuple[tuple[str, re.Pattern], ...] = (
    ("python",     re.compile(r"pip install\s+[A-Za-z0-9._-]+")),
    ("net",        re.compile(r"dotnet add package\s+[A-Za-z0-9._-]+")),
    ("java",       re.compile(r"<groupId>[^<]+</groupId>")),
    ("typescript", re.compile(r"npm install\s+[@A-Za-z0-9._/-]+")),
    ("go",         re.compile(r"go get\s+\S+")),
    ("cpp",        re.compile(r"cmake\s+--install|vcpkg install")),
)


def _has_install_block(text: str) -> bool:
    """Return True if the page contains at least one install command block."""
    for _, pat in _INSTALL_PATTERNS:
        if pat.search(text):
            return True
    return False


# ------- format table detection -------

_FORMAT_TABLE_HEADER_RE = re.compile(
    r"\|\s*(?:Format|Name|Extension|Ext).*?\|",
    re.IGNORECASE,
)

_FORMAT_TABLE_DATA_RE = re.compile(
    r"\|\s*(?:COLLADA|FBX|OBJ|STL|GLTF|GLB|PLY|DRACO|PDF|DOCX|XLSX|PNG|JPG|JPEG|BMP|"
    r"CSV|HTML|ZIP|MSG|EML|TTF|OTF|WOFF|PS|EPS|XPS|TEX|AMF|RVM|U3D|JT|USD|USDA|USDC"
    r"|USDZ|3MF|VRML|WRL|DXF|WEBP|TIFF|SVG|MHT|MHTML|XPS|MD|RTF|ODT|ODS)\s*\|",
    re.IGNORECASE,
)


def _format_page_status(text: str) -> str:
    """Return 'POPULATED', 'STUB', or 'NONE' based on format table content."""
    if _FORMAT_TABLE_DATA_RE.search(text):
        return "POPULATED"
    if _FORMAT_TABLE_HEADER_RE.search(text):
        return "STUB"
    return "NONE"


# ------- coordinate detection -------

def _extract_code_block_coords(text: str) -> set[str]:
    """Extract package coordinate strings found inside fenced code blocks."""
    coords: set[str] = set()
    # Find all fenced code blocks
    for block in re.findall(r"```[^\n]*\n(.*?)```", text, re.DOTALL):
        # Java groupId patterns
        for m in re.finditer(r"((?:com|org|net|io)\.[a-zA-Z0-9._]+)", block):
            coords.add(m.group(1))
        # Python import statements
        for m in re.finditer(r"import\s+(aspose[a-zA-Z0-9._]+)", block):
            coords.add(m.group(1))
        # .NET using statements
        for m in re.finditer(r"using\s+(Aspose\.[A-Za-z0-9._]+)", block):
            coords.add(m.group(1))
        # npm package in install
        for m in re.finditer(r"npm install\s+([@A-Za-z0-9._/-]+)", block):
            coords.add(m.group(1))
        # go get module
        for m in re.finditer(r"go get\s+(\S+)", block):
            coords.add(m.group(1))
    return coords


# ------- feature-list detection -------

_FEATURE_LIST_KEYWORDS = frozenset([
    "features", "capabilities", "what-you-can-do", "key-features",
    "overview", "introduction", "getting-started",
])


def _is_feature_list_candidate(filepath: Path, text: str) -> bool:
    """Heuristic: return True if page looks like a feature-list page."""
    slug = filepath.stem.lower()
    if any(kw in slug for kw in _FEATURE_LIST_KEYWORDS):
        return True
    # Also check frontmatter role field
    if re.search(r"role:\s*feature-list", text):
        return True
    return False


# ------- main indexer -------

# Subdomain content roots to scan (English paths only)
_SITE_ROOTS: tuple[str, ...] = (
    "content/docs.aspose.org/en/{family}/{platform}",
    "content/kb.aspose.org/en/{family}/{platform}",
    "content/products.aspose.org/en/{family}",
    "content/blog.aspose.org/{family}/{platform}",
)


def build_index(family: str, platform: str) -> dict:
    """Build content region index for one product.

    Returns a dict ready to serialize as JSON.
    """
    repo = _REPO_ROOT

    index: dict = {
        "family": family,
        "platform": platform,
        "install_command_blocks": [],
        "format_tables": [],
        "format_table_status": {},
        "feature_list_pages": [],
        "code_blocks_with_coordinate": defaultdict(list),
    }

    # Collect all English .md files for this product
    md_files: list[Path] = []
    for root_template in _SITE_ROOTS:
        root = repo / root_template.format(family=family, platform=platform)
        if root.is_dir():
            for f in root.rglob("*.md"):
                # Reject locale-suffixed files (e.g. index.fr.md)
                if LOCALE_RE.search(f.name):
                    continue
                # Reject non-English paths (belt-and-suspenders for blog)
                if "/ko/" in str(f) or "/fr/" in str(f) or "/de/" in str(f):
                    continue
                md_files.append(f)

    for filepath in sorted(md_files):
        try:
            text = filepath.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        rel = str(filepath.relative_to(repo)).replace("\\", "/")

        # Install blocks
        if _has_install_block(text):
            index["install_command_blocks"].append(rel)

        # Format tables
        fmt_status = _format_page_status(text)
        if fmt_status in ("POPULATED", "STUB"):
            index["format_tables"].append(rel)
            index["format_table_status"][rel] = fmt_status

        # Feature list pages
        if _is_feature_list_candidate(filepath, text):
            index["feature_list_pages"].append(rel)

        # Code block coordinates
        coords = _extract_code_block_coords(text)
        for coord in coords:
            index["code_blocks_with_coordinate"][coord].append(rel)

    # Deduplicate and sort all lists
    index["install_command_blocks"] = sorted(set(index["install_command_blocks"]))
    index["format_tables"] = sorted(set(index["format_tables"]))
    index["feature_list_pages"] = sorted(set(index["feature_list_pages"]))

    # Deduplicate coordinate → file lists
    coord_map: dict[str, list[str]] = {}
    for coord, files in index["code_blocks_with_coordinate"].items():
        deduped = sorted(set(files))
        if deduped:
            coord_map[coord] = deduped
    index["code_blocks_with_coordinate"] = coord_map

    return index


def write_index(family: str, platform: str) -> Path:
    """Build and write the index to reports/content_region_index/{family}/{platform}.json."""
    index = build_index(family, platform)

    out_dir = _REPO_ROOT / "reports" / "content_region_index"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{family}_{platform}.json"

    tmp = out_path.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(out_path)
        print(
            f"  {family}/{platform}: content_region_index written "
            f"({len(index['install_command_blocks'])} install pages, "
            f"{len(index['format_tables'])} format tables, "
            f"{len(index['feature_list_pages'])} feature-list pages, "
            f"{len(index['code_blocks_with_coordinate'])} coord patterns)"
        )
        return out_path
    except Exception as exc:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise RuntimeError(f"Could not write content region index: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build content region index for S-84 handler dispatch."
    )
    parser.add_argument("family", nargs="?", help="Product family (e.g. pdf)")
    parser.add_argument("platform", nargs="?", help="Platform (e.g. java)")
    parser.add_argument(
        "--all", dest="all_products", action="store_true",
        help="Index all active products from data/products.json",
    )
    args = parser.parse_args(argv)

    if args.all_products:
        products_path = _REPO_ROOT / "data" / "products.json"
        if not products_path.is_file():
            print("ERROR: data/products.json not found", file=sys.stderr)
            return 1
        with open(products_path, encoding="utf-8") as f:
            products = json.load(f)
        for p in products:
            if p.get("active"):
                try:
                    write_index(p["family"], p["platform"])
                except Exception as exc:
                    print(f"  WARN: {p['family']}/{p['platform']}: {exc}")
        return 0

    if not args.family or not args.platform:
        parser.print_help()
        return 1

    try:
        write_index(args.family, args.platform)
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
