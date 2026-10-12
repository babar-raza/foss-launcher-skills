"""
llms-generator.py — LLM-Ready Markdown Generator for aspose.org

Walks Hugo content directories, strips internal frontmatter (including evidence blocks),
renders LLM-readable .md files per page, and produces llms.txt + llms-full.txt per
subdomain.

Adapted from aspose.net/scripts/generator/llms-generator.py with the following
production fixes applied:

  1. Deterministic output — dirs and files sorted in both passes; identical llms.txt
     on every rerun regardless of filesystem ordering.
  2. Frontmatter-first descriptions — uses `description` / `summary` / `subtitle` /
     `head_description` / `banner.content` YAML fields in priority order; falls back
     to body extraction only when all frontmatter fields are absent.
  3. Extension-free URLs — live Hugo URLs have no .md extension; index pages get
     trailing slash.
  4. Two-level blog hierarchy — blog.aspose.org uses {family}/{platform}/ nesting;
     llms.txt reflects ## Family / ### Platform structure.
  5. Evidence block stripped — `evidence:` YAML key excluded from rendered output so
     claim IDs, model SHAs, and API tokens never appear in llms files.
  6. llms-full.txt companion — full body content concatenated in sorted order for RAG
     ingestion, separated by --- dividers.
  7. Output path collision resolution — when a flat .md file and a directory-style
     index.md both produce the same output path, the directory-style index.md wins;
     collision is logged as a WARNING.
  8. H1-only regex — `extract_h1_and_first_sentence` matches only single-hash `#`
     headings; `##`+ headings (e.g. Related Topics treeview) are ignored.
  9. Conditional description in render_llms_tree — bullets and section headers omit
     the `: description` suffix when the description is empty.

Usage:
    python scripts/generator/llms-generator.py \\
        --input content \\
        --output llms-output \\
        --subdomain blog.aspose.org \\
        --mapping scripts/generator/mapping.json \\
        --clean-output

Output governance note:
    This script writes to llms-output/ (default) or the path specified by --output.
    llms-output/ is a git-ignored LLM generation staging area — a deliberate
    exception to the reports/ governance hub.  It is never committed to the repo
    and is not covered by path_guard.py by design (staging artifacts, not deliverables).
    Companion validation results are written to llms-output-check/ by the check script.
"""

import argparse
import datetime
import json
import logging
import os
import re
import shutil
import sys
import yaml
from pathlib import Path
from typing import Dict, List, Tuple, Optional

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "scripts" / "pipeline"))
from core.env_loader import load_env  # noqa: E402
load_env()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

LOG_FILENAME = 'llms-generator.log'

FAMILY_NAME_MAP = {
    "words": "Aspose.Words",
    "pdf": "Aspose.PDF",
    "cells": "Aspose.Cells",
    "email": "Aspose.Email",
    "slides": "Aspose.Slides",
    "imaging": "Aspose.Imaging",
    "barcode": "Aspose.BarCode",
    "diagram": "Aspose.Diagram",
    "tasks": "Aspose.Tasks",
    "ocr": "Aspose.OCR",
    "omr": "Aspose.OMR",
    "note": "Aspose.Note",
    "cad": "Aspose.CAD",
    "3d": "Aspose.3D",
    "html": "Aspose.HTML",
    "gis": "Aspose.GIS",
    "zip": "Aspose.ZIP",
    "page": "Aspose.Page",
    "psd": "Aspose.PSD",
    "pub": "Aspose.PUB",
    "svg": "Aspose.SVG",
    "finance": "Aspose.Finance",
    "drawing": "Aspose.Drawing",
    "font": "Aspose.Font",
    "tex": "Aspose.TeX",
    "total": "Aspose.Total",
}

PLATFORM_DISPLAY_MAP = {
    "python": "Python",
    "net": ".NET",
    "java": "Java",
    "cpp": "C++",
    "typescript": "TypeScript",
    "javascript": "JavaScript",
    "nodejs": "Node.js",
    "rust": "Rust",
}

# Domains whose root URL → /llms.txt and inner paths → *.md
MD_ROOT_DOMAINS = {"products.aspose.org", "docs.aspose.org"}

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def txt_path_from_md_path(md_path: str) -> str:
    """Derives .txt output path from a .md output path."""
    assert md_path.endswith('.md'), f"Expected .md path, got: {md_path}"
    return md_path[:-3] + '.txt'


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

def _fix_domain_url(url: str) -> str:
    """Rewrites products/docs .org URLs to their .md equivalents for link
    embedding inside www content (mirrors the aspose.net behaviour)."""
    for dom in MD_ROOT_DOMAINS:
        if url.rstrip('/') == f"https://{dom}":
            return f"https://{dom}/llms.txt"
        if url.startswith(f"https://{dom}/"):
            if url.endswith('/'):
                url = url[:-1]
            return f"{url}.md"
    return url


def make_page_url(site_url_base: str, rel_out_p: str, is_index: bool) -> str:
    """
    Constructs a clean, extension-free URL from a relative output path.

    For index sources (originally _index.md / index.md) we emit a trailing
    slash because Hugo serves those as directory roots.  For standalone content
    pages we strip the .md extension only.

    The sentinel value 'index.md' (used when the root _index.md maps to the
    subdomain root) resolves to the bare site root URL.

    Examples
    --------
    rel_out_p='3d/python/introducing-foss.md', is_index=True
        → https://blog.aspose.org/3d/python/introducing-foss/

    rel_out_p='3d/python/developer-guide/features.md', is_index=False
        → https://docs.aspose.org/3d/python/developer-guide/features

    rel_out_p='index.md', is_index=True
        → https://docs.aspose.org/
    """
    slug = rel_out_p[:-3] if rel_out_p.endswith('.md') else rel_out_p
    # Sentinel: root _index.md anchored at subdomain root
    if slug == 'index' and is_index:
        return f"{site_url_base}/"
    if is_index:
        return f"{site_url_base}/{slug}/"
    return f"{site_url_base}/{slug}"

# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def setup_logging(log_file: str) -> None:
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
    logger.addHandler(ch)

    fh = logging.FileHandler(log_file, mode='w', encoding='utf-8')
    fh.setLevel(logging.INFO)
    fh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s: %(message)s'))
    logger.addHandler(fh)


def extract_h1_and_first_sentence(markdown_content: str) -> Tuple[str, str]:
    """Extracts the first H1 heading and first body sentence from markdown."""
    h1_title = ""
    first_sentence = ""

    h1_match = re.search(r'^# ([^#].+?)\s*$', markdown_content, re.MULTILINE)
    if h1_match:
        h1_title = h1_match.group(1).strip()
        content_after = markdown_content[h1_match.end():].strip()
        for para in re.split(r'\n{2,}', content_after):
            para = para.strip()
            if not para:
                continue
            if (para.startswith('#') or para.startswith('- ') or
                    re.match(r'^\s*\d+\.\s+', para) or
                    para.startswith('```') or para.startswith('>')):
                continue
            clean = re.sub(r'\[.*?\]\(.*?\)|\*\*|__|\*|_|`', '', para)
            clean = re.sub(r'\s+', ' ', clean).strip()
            if clean:
                m = re.match(r'(.+?[.!?])(?:\s|$)', clean)
                first_sentence = m.group(1).strip() if m else clean
                break

    return h1_title, first_sentence


def extract_description(yaml_data: dict, md_body: str) -> str:
    """
    Returns the best available description for a page.

    Priority:
      1. `description` frontmatter field
      2. `summary` frontmatter field
      3. `subtitle` frontmatter field (used by docs/kb platform index pages)
      4. `head_description` frontmatter field (used by products.aspose.org pages)
      5. `banner.content` nested field (products.aspose.org root)
      6. First body sentence (fallback when all frontmatter fields absent)
    """
    for key in ('description', 'summary', 'subtitle', 'head_description'):
        val = yaml_data.get(key)
        if val:
            return str(val).strip()
    # Check nested banner.content (used by products.aspose.org pages)
    banner = yaml_data.get('banner')
    if isinstance(banner, dict):
        val = banner.get('content') or banner.get('description')
        if val:
            return str(val).strip()
    _, sentence = extract_h1_and_first_sentence(md_body)
    return sentence


def clean_title_from_filename(filename: str) -> str:
    """Converts a filename/slug to a human-readable title."""
    name = os.path.splitext(os.path.basename(filename))[0]
    name = name.replace('-', ' ').replace('_', ' ')
    return ' '.join(w.capitalize() for w in name.split())


def is_index_file(filename: str) -> bool:
    return os.path.basename(filename).lower() in ('_index.md', 'index.md')


def extract_yaml_and_body(filepath: str) -> Tuple[dict, str]:
    """Reads a markdown file and returns (yaml_data, body)."""
    with open(filepath, encoding='utf-8') as f:
        text = f.read()

    yaml_data: dict = {}
    md_body = text

    if text.startswith('---'):
        parts = text.split('---', 2)
        if len(parts) >= 3:
            yaml_content = parts[1].strip().replace("\\'", "'")
            md_body = parts[2].strip()
            try:
                yaml_data = yaml.safe_load(yaml_content) or {}
            except yaml.YAMLError as e:
                logging.warning(f"YAML parse error in {filepath}: {e}")

    return yaml_data, md_body


def sanitize_markdown(content: str) -> str:
    """Removes Hugo shortcodes, HTML tags, and excess blank lines."""
    content = re.sub(r'\{\{.*?\}\}', '', content, flags=re.DOTALL)
    content = re.sub(r'<.*?>', '', content, flags=re.DOTALL)
    content = re.sub(r'\n{3,}', '\n\n', content)
    return content.strip()


def build_llms_tree(entries: list) -> dict:
    """Builds a hierarchical tree from flat file entries for non-blog llms.txt."""
    tree: dict = {}
    for entry in entries:
        parts = entry['rel_output_path'].replace('.md', '').split('/')
        node = tree
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = {"_self": entry}
    return tree


def render_llms_tree(node: dict, depth: int = 2, root_path: Optional[str] = None) -> list:
    """Renders a hierarchical tree into markdown lines for llms.txt."""
    lines = []
    if "_self" in node:
        entry = node["_self"]
        if root_path and entry['rel_output_path'] == root_path:
            return []
        title = entry['title']
        url = entry['absolute_url']
        desc = entry['description']
        if depth <= 3:
            header = f"\n## [{title}]({url})"
            if desc:
                header += f"\n{desc}"
            lines.append(header)
        else:
            bullet = f"- [{title}]({url})"
            if desc:
                bullet += f": {desc}"
            lines.append(bullet)

    for key, child in sorted(node.items()):
        if key == "_self":
            continue
        lines.extend(render_llms_tree(child, depth + 1, root_path=root_path))

    return lines

# ---------------------------------------------------------------------------
# Site mapping
# ---------------------------------------------------------------------------

class SiteMapping:
    """Loads and provides lookup into the JSON site configuration."""

    def __init__(self, mapping_file: str) -> None:
        with open(mapping_file, encoding='utf-8') as f:
            self.mapping: dict = json.load(f)

    def get_subdomain_type(self, subdomain: str) -> str:
        return self.mapping.get(subdomain, {}).get('type', 'dir')

    def get_virtual_metadata(self, subdomain: str,
                             family: Optional[str] = None) -> Optional[dict]:
        m = self.mapping.get(subdomain)
        if not m:
            return None
        if family:
            fam = m.get('families', {}).get(family)
            if fam:
                return fam
        return m.get('root', None)

    def get_platform_description(self, subdomain: str, family: str,
                                 platform: str) -> str:
        """Returns the platform-specific description from mapping, or empty string."""
        m = self.mapping.get(subdomain, {})
        return (m.get('families', {})
                  .get(family, {})
                  .get('platforms', {})
                  .get(platform, ''))

    def get_site_url(self, subdomain: str) -> str:
        return self.mapping.get(subdomain, {}).get('url', '')

    def get_home_slug(self, subdomain: str) -> str:
        return self.mapping.get(subdomain, {}).get('home_slug', 'home')

    def get_yaml_metadata_fields(self, subdomain: str) -> Optional[List[dict]]:
        return self.mapping.get(subdomain, {}).get('metadata', None)

    def get_h1_source_path(self, subdomain: str) -> Optional[str]:
        return self.mapping.get(subdomain, {}).get('h1_path')

# ---------------------------------------------------------------------------
# Converter
# ---------------------------------------------------------------------------

class Yml2MdConverter:
    """Converts Hugo markdown files to LLM-readable format."""

    def __init__(self, site_mapping: SiteMapping) -> None:
        self.site_mapping = site_mapping
        self._current_subdomain = ""

    def _convert_dates_to_strings(self, obj):
        if isinstance(obj, dict):
            return {k: self._convert_dates_to_strings(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._convert_dates_to_strings(e) for e in obj]
        if isinstance(obj, (datetime.date, datetime.datetime)):
            return obj.isoformat()
        return obj

    def _render_item_template(self, template: str, data: dict) -> str:
        def replace_placeholder(match):
            key_path = match.group(1).split('.')
            value = data
            try:
                for part in key_path:
                    if isinstance(value, dict):
                        value = value[int(part)] if part.isdigit() and int(part) in value else value[part]
                    elif isinstance(value, list) and part.isdigit():
                        value = value[int(part)]
                    else:
                        raise KeyError
                return str(value)
            except (KeyError, IndexError, TypeError):
                return match.group(0)

        raw = re.sub(r'\{([a-zA-Z0-9_.]+)\}', replace_placeholder, template)

        if self._current_subdomain in MD_ROOT_DOMAINS:
            raw = re.sub(
                r'https://(?:products|docs)\.aspose\.org[^\s)\]]*',
                lambda m: _fix_domain_url(m.group(0)),
                raw,
            )
        return raw

    def _render_block(self, block_rule: dict, yaml_data: dict) -> str:
        key_path = block_rule["key"].split(".")
        node = yaml_data
        for part in key_path[:-1]:
            node = node.get(part) if isinstance(node, dict) else None
            if node is None:
                return ""

        last_key = key_path[-1]
        node = node.get(last_key) if isinstance(node, dict) else None
        if node is None:
            return ""

        if isinstance(node, dict) and node.get("enabled") is False:
            return ""

        if block_rule.get("repeat"):
            if isinstance(node, list):
                items = node
            elif isinstance(node, dict):
                for k in ("items", "list", "features", "stories", "reasons"):
                    if isinstance(node.get(k), list):
                        items = node[k]
                        break
                else:
                    return ""
            else:
                return ""

            rendered = [
                self._render_item_template(block_rule["template"], item)
                for item in items if isinstance(item, dict)
            ]
            if not rendered:
                return ""

            body = "\n".join(rendered)
            if "wrapper" in block_rule:
                wrapper = self._render_item_template(block_rule["wrapper"], yaml_data)
                return wrapper.replace("{items}", body)
            return body

        return self._render_item_template(block_rule["template"], yaml_data)

    def _render_markdown_content(self, yaml_data: dict, md_body: str,
                                  subdomain: str, relpath: str) -> str:
        output_parts = []
        yaml_data = self._convert_dates_to_strings(yaml_data)
        metadata_rules = self.site_mapping.get_yaml_metadata_fields(subdomain)
        h1_source_path = self.site_mapping.get_h1_source_path(subdomain)

        if h1_source_path and relpath == h1_source_path:
            title_rule = next((r for r in metadata_rules if r.get('key') == 'title'), None)
            if title_rule and 'title' in yaml_data:
                output_parts.append(self._render_item_template(title_rule['template'], yaml_data))

        if metadata_rules:
            for rule in metadata_rules:
                key_path = rule['key']
                if h1_source_path and relpath == h1_source_path and key_path == 'title':
                    continue

                top_key = key_path.split('.')[0]
                top_data = yaml_data.get(top_key)
                if isinstance(top_data, dict) and top_data.get('enable') is False:
                    logging.debug(f"Skipping disabled block '{key_path}' in {relpath}")
                    continue

                if rule.get('repeat'):
                    rendered = self._render_block(rule, yaml_data)
                    if rendered:
                        output_parts.append(rendered)
                else:
                    rendered = self._render_item_template(rule['template'], yaml_data)
                    if rendered and rendered != rule['template']:
                        output_parts.append(rendered)

        if md_body:
            output_parts.append(md_body)

        return '\n\n'.join(filter(None, output_parts)).strip()

    def process_file(self, filepath: str, subdomain: str, input_root: str) -> str:
        """Processes a single markdown file to LLM-ready output."""
        yaml_data, md_body = extract_yaml_and_body(filepath)
        self._current_subdomain = subdomain

        # Strip internal-only evidence block — claim IDs, SHAs, and API tokens
        # must never appear in llms output.
        yaml_data.pop('evidence', None)

        relpath = os.path.relpath(filepath, input_root).replace('\\', '/')
        logging.info(f"Processing: {relpath}")

        # Inject virtual metadata for blog.aspose.org
        # blog content: {subdomain}/{family}/{platform}/{slug}/index.md
        # No /en/ locale directory in blog.
        if subdomain == "blog.aspose.org":
            path_segments = relpath.split('/')

            # Root blog index: blog.aspose.org/_index.md or blog.aspose.org/index.md
            is_root = (len(path_segments) == 2 and is_index_file(path_segments[1]))
            if is_root:
                virtual = self.site_mapping.get_virtual_metadata(subdomain)
                if virtual:
                    merged = virtual.copy()
                    merged.update(yaml_data)
                    yaml_data = merged

            elif len(path_segments) >= 3 and is_index_file(path_segments[-1]):
                # Family or platform index
                family_name = path_segments[1]
                virtual = self.site_mapping.get_virtual_metadata(subdomain, family=family_name)
                if virtual:
                    merged = virtual.copy()
                    merged.update(yaml_data)
                    yaml_data = merged

        return self._render_markdown_content(yaml_data, md_body, subdomain, relpath)

# ---------------------------------------------------------------------------
# Page type detection
# ---------------------------------------------------------------------------

# Page type constants
PAGE_TYPE_REFERENCE = "reference"
PAGE_TYPE_DOCS      = "docs"
PAGE_TYPE_KB        = "kb"
PAGE_TYPE_BLOG      = "blog"
PAGE_TYPE_PRODUCT   = "product"
PAGE_TYPE_INDEX     = "index"
PAGE_TYPE_UNKNOWN   = "unknown"


def detect_page_type(source_path: str, filename: str, subdomain: str) -> str:
    """
    Determine the page type from the source path and subdomain.

    Rules (applied in order):
      - Any _index.md or index.md file               → PAGE_TYPE_INDEX
      - Subdomain is 'reference.aspose.org'
        AND the filename starts with an uppercase letter → PAGE_TYPE_REFERENCE
      - Subdomain is 'docs.aspose.org'               → PAGE_TYPE_DOCS
      - Subdomain is 'kb.aspose.org'                 → PAGE_TYPE_KB
      - Subdomain is 'blog.aspose.org'               → PAGE_TYPE_BLOG
      - Subdomain is 'products.aspose.org'           → PAGE_TYPE_PRODUCT
      - Fallback                                     → PAGE_TYPE_UNKNOWN
    """
    fname_lower = filename.lower()

    # Index files first (applies to all subdomains)
    if fname_lower in ('_index.md', 'index.md'):
        return PAGE_TYPE_INDEX

    # Subdomain-based dispatch
    if subdomain == 'reference.aspose.org':
        # Reference class pages start with uppercase (e.g., Document.md, AbsorbedCell.md)
        # Non-class reference pages (e.g., _index.md) already caught above
        if filename and filename[0].isupper():
            return PAGE_TYPE_REFERENCE
        return PAGE_TYPE_REFERENCE  # all reference pages are type reference

    if subdomain == 'docs.aspose.org':
        return PAGE_TYPE_DOCS

    if subdomain == 'kb.aspose.org':
        return PAGE_TYPE_KB

    if subdomain == 'blog.aspose.org':
        return PAGE_TYPE_BLOG

    if subdomain == 'products.aspose.org':
        return PAGE_TYPE_PRODUCT

    return PAGE_TYPE_UNKNOWN


# ---------------------------------------------------------------------------
# Page header block (TC-W4-003)
# ---------------------------------------------------------------------------

# Human-readable product name map (family → display name)
_PRODUCT_DISPLAY_NAMES: Dict[str, str] = {
    '3d':     'Aspose.3D',
    'cells':  'Aspose.Cells',
    'email':  'Aspose.Email',
    'font':   'Aspose.Font',
    'note':   'Aspose.Note',
    'page':   'Aspose.Page',
    'pdf':    'Aspose.PDF',
    'slides': 'Aspose.Slides',
    'tex':    'Aspose.TeX',
    'words':  'Aspose.Words',
}


def build_page_header(
    page_type: str,
    family: Optional[str],
    platform: Optional[str],
    canonical_url: str,
) -> str:
    """
    Build the stable YAML-fence metadata header prepended to every page .txt output.

    Format:
        ---
        Product: Aspose.PDF
        Platform: net
        Page Type: reference
        Canonical URL: https://reference.aspose.org/pdf/net/Document
        ---

    Index pages and pages without a resolvable family/platform get a minimal header.
    """
    product = _PRODUCT_DISPLAY_NAMES.get(family or '', family or 'Aspose')
    plat = platform or ''

    lines = ['---']
    if product:
        lines.append(f'Product: {product}')
    if plat:
        lines.append(f'Platform: {plat}')
    lines.append(f'Page Type: {page_type}')
    if canonical_url:
        lines.append(f'Canonical URL: {canonical_url}')
    lines.append('---')
    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Hierarchical index generation (--mode hierarchical)
# ---------------------------------------------------------------------------

def _extract_family_platform(rel_output_path: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Derive (family, platform) from the relative output path inside a subdomain dir.
    Examples:
      'pdf/net/Document.md'        -> ('pdf', 'net')
      '3d/java/how-to-load.md'     -> ('3d', 'java')
      '3d.md'                      -> ('3d', None)
      'en/pdf/net/Document.md'     -> ('pdf', 'net')   # en/ already stripped by generator
      'index.md'                   -> (None, None)
    """
    parts = rel_output_path.replace('\\', '/').split('/')
    # Skip any leading 'en' segment (shouldn't occur after generator strips it, but guard)
    if parts and parts[0] == 'en':
        parts = parts[1:]
    if not parts:
        return None, None
    family = parts[0].replace('.md', '').replace('.txt', '')
    if not family or family in ('index', '_index', ''):
        return None, None
    if len(parts) == 1:
        # Family-level only (e.g. products.aspose.org/3d.md)
        return family, None
    platform = parts[1].replace('.md', '').replace('.txt', '')
    if not platform or platform in ('index', '_index', ''):
        return family, None
    return family, platform


def generate_hierarchical_indexes(
    all_files_info: list,
    subdomain_output_dir: str,
    site_url_base: str,
    subdomain: str,
    site_mapping: 'SiteMapping',
) -> None:
    """
    Generate hierarchical llms.txt indexes in hierarchical mode.

    Writes:
      {subdomain_output_dir}/{family}/{platform}/llms.txt  — per-product index
      {subdomain_output_dir}/llms.txt                      — root index (replaces flat)

    Root index is kept ≤200 lines; per-product indexes ≤500 lines.
    """
    # Group pages by (family, platform)
    groups: Dict[Tuple[Optional[str], Optional[str]], list] = {}
    for entry in all_files_info:
        fp = _extract_family_platform(entry['rel_output_path'])
        if fp[0] is None:
            continue
        if fp not in groups:
            groups[fp] = []
        groups[fp].append(entry)

    if not groups:
        logging.warning(f"generate_hierarchical_indexes: no family/platform groups found for {subdomain}")
        return

    # Sort groups for deterministic output
    sorted_groups = sorted(groups.items(), key=lambda kv: (kv[0][0] or '', kv[0][1] or ''))

    product_index_urls: List[str] = []  # paths written; used for root index

    # Write per-product llms.txt
    for (family, platform), pages in sorted_groups:
        if platform:
            product_dir = os.path.join(subdomain_output_dir, family, platform)
            index_url = f"{site_url_base}/{family}/{platform}/llms.txt"
        else:
            product_dir = os.path.join(subdomain_output_dir, family)
            index_url = f"{site_url_base}/{family}/llms.txt"

        os.makedirs(product_dir, exist_ok=True)
        index_path = os.path.join(product_dir, "llms.txt")

        # Product title / description from mapping.json families key
        fam_meta = site_mapping.mapping.get(subdomain, {}).get('families', {}).get(family, {})
        if fam_meta:
            fam_title = fam_meta.get('title', FAMILY_NAME_MAP.get(family, family.capitalize()))
            fam_desc = fam_meta.get('description', '')
            plat_desc = fam_meta.get('platforms', {}).get(platform, '') if platform else ''
        else:
            fam_title = FAMILY_NAME_MAP.get(family, family.capitalize())
            fam_desc = ''
            plat_desc = ''

        if platform:
            plat_display = PLATFORM_DISPLAY_MAP.get(platform, platform.capitalize())
            product_title = f"{fam_title} for {plat_display}"
            product_url = f"{site_url_base}/{family}/{platform}/"
        else:
            product_title = fam_title
            product_url = f"{site_url_base}/{family}/"

        lines: List[str] = [f"# [{product_title}]({product_url})"]
        if fam_desc:
            lines.append(fam_desc)
        if plat_desc:
            lines.append(plat_desc)
        lines.append("")

        # List all pages in this product (sorted, excluding index pages)
        page_entries = sorted(pages, key=lambda e: e['rel_output_path'])
        for entry in page_entries:
            if entry['is_original_index']:
                continue
            title = entry['title'] or clean_title_from_filename(
                os.path.basename(entry['rel_output_path']))
            url = entry['absolute_url']
            desc = entry['description']
            bullet = f"- [{title}]({url})"
            if desc:
                bullet += f": {desc}"
            lines.append(bullet)

        # Truncate to ≤500 lines
        if len(lines) > 500:
            lines = lines[:499]
            lines.append("... (truncated — see full site index for remaining pages)")

        try:
            with open(index_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines))
            logging.info(f"Hierarchical index written: {index_path}")
        except Exception as e:
            logging.error(f"Error writing hierarchical index {index_path}: {e}")
            continue

        product_index_urls.append((product_title, product_url, index_url, fam_desc or plat_desc))

    # Write root hierarchical llms.txt (replaces flat)
    root_meta = site_mapping.mapping.get(subdomain, {})
    root_title = root_meta.get('root', {}).get('title', '') if isinstance(root_meta.get('root'), dict) else ''
    root_desc = root_meta.get('root', {}).get('description', '') if isinstance(root_meta.get('root'), dict) else ''
    if not root_title:
        root_title = subdomain.replace('.aspose.org', '').capitalize() + ' API Reference'

    root_lines: List[str] = [f"# [{root_title}]({site_url_base}/)"]
    if root_desc:
        root_lines.append(root_desc)
    root_lines.append("")
    root_lines.append("> This is a hierarchical index. Each product has a dedicated llms.txt with its full page list.")
    root_lines.append("")

    current_family_header = None
    for (prod_title, prod_url, idx_url, desc) in product_index_urls:
        # Group by family in the root index using H2 headers
        fam = idx_url.split(site_url_base + '/')[-1].split('/')[0]
        fam_display = FAMILY_NAME_MAP.get(fam, fam.capitalize())
        if current_family_header != fam_display:
            current_family_header = fam_display
            root_lines.append(f"\n## {fam_display}")
        bullet = f"- [{prod_title}]({idx_url})"
        if desc:
            bullet += f": {desc[:120]}"
        root_lines.append(bullet)

    # Truncate to ≤200 lines
    if len(root_lines) > 200:
        root_lines = root_lines[:199]
        root_lines.append("... (truncated)")

    root_llms_path = os.path.join(subdomain_output_dir, "llms.txt")
    try:
        with open(root_llms_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(root_lines))
        logging.info(f"Root hierarchical llms.txt written: {root_llms_path}")
    except Exception as e:
        logging.error(f"Error writing root hierarchical llms.txt: {e}")

    logging.info(f"generate_hierarchical_indexes: {len(product_index_urls)} product indexes written for {subdomain}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="LLM-Ready Markdown Generator for aspose.org"
    )
    parser.add_argument("--input", required=True,
                        help="Input root directory (e.g. content/)")
    parser.add_argument("--output", required=True,
                        help="Output root directory (e.g. llms-output/)")
    parser.add_argument("--subdomain", required=False, default=None,
                        help="Subdomain to process (e.g. blog.aspose.org). "
                             "Omit when using --all-subdomains.")
    parser.add_argument("--mapping", required=True,
                        help="Path to mapping.json")
    parser.add_argument("--clean-output", action="store_true",
                        help="Delete subdomain output folder before processing")
    parser.add_argument("--mode", choices=["flat", "hierarchical"], default="flat",
                        help="Output mode: flat (default) or hierarchical "
                             "(adds per-product llms.txt indexes alongside flat output)")
    parser.add_argument("--all-subdomains", action="store_true",
                        help="Process all subdomains defined in mapping.json")
    args = parser.parse_args()

    if args.all_subdomains and args.subdomain:
        parser.error("--subdomain and --all-subdomains are mutually exclusive")
    if not args.all_subdomains and not args.subdomain:
        parser.error("--subdomain is required unless --all-subdomains is specified")

    setup_logging(LOG_FILENAME)

    # --all-subdomains: re-invoke this script once per domain in mapping.json
    if args.all_subdomains:
        import subprocess as _sp
        try:
            with open(args.mapping, encoding='utf-8') as _mf:
                _mapping_data = json.load(_mf)
        except Exception as _e:
            logging.error(f"Cannot load mapping for --all-subdomains: {_e}")
            return
        for _domain in _mapping_data.keys():
            _cmd = [sys.executable, os.path.abspath(__file__),
                    "--input", args.input,
                    "--output", args.output,
                    "--subdomain", _domain,
                    "--mapping", args.mapping]
            if args.clean_output:
                _cmd.append("--clean-output")
            if args.mode != "flat":
                _cmd.extend(["--mode", args.mode])
            logging.info(f"--all-subdomains: invoking for {_domain}")
            _result = _sp.run(_cmd)
            if _result.returncode != 0:
                logging.error(f"--all-subdomains: {_domain} exited {_result.returncode}")
        logging.info("--all-subdomains: all domains complete.")
        return

    input_base_dir = os.path.abspath(args.input)
    output_base_dir = os.path.abspath(args.output)
    os.makedirs(output_base_dir, exist_ok=True)

    try:
        site_mapping = SiteMapping(args.mapping)
    except FileNotFoundError:
        logging.error(f"Mapping file not found: {args.mapping}")
        return
    except json.JSONDecodeError:
        logging.error(f"Invalid JSON in mapping file: {args.mapping}")
        return

    converter = Yml2MdConverter(site_mapping=site_mapping)
    subdomain_output_dir = os.path.join(output_base_dir, args.subdomain)

    if args.clean_output and os.path.exists(subdomain_output_dir):
        logging.info(f"Cleaning output dir: {subdomain_output_dir}")
        try:
            shutil.rmtree(subdomain_output_dir)
        except OSError as e:
            logging.error(f"Could not clean {subdomain_output_dir}: {e}")
            return

    os.makedirs(subdomain_output_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # Pass 1: Pre-collect — map every English input file to its output
    # path and display name.  Sorting dirs and files here is the primary
    # determinism guarantee.
    # ------------------------------------------------------------------
    file_output_mapping: Dict[str, Tuple[str, str]] = {}
    out_path_claimed: Dict[str, str] = {}  # out_path → input_path that claimed it
    logging.info("Pass 1: pre-collecting file paths…")

    for root, dirs, files in os.walk(input_base_dir):
        dirs.sort()  # deterministic walk order
        files_sorted = sorted(files)

        for file in files_sorted:
            if not file.lower().endswith('.md'):
                continue

            input_path = os.path.join(root, file)
            rel_from_root = os.path.relpath(input_path, input_base_dir).replace('\\', '/')

            if not rel_from_root.startswith(args.subdomain):
                continue

            # Skip non-EN locale *folders*  (two-letter codes that are not 'en')
            segments = rel_from_root.split('/')
            if any(re.fullmatch(r'[a-z]{2}', s) and s != 'en' for s in segments):
                logging.debug(f"Skip (locale folder): {rel_from_root}")
                continue

            # Skip locale-suffixed filenames e.g. index.es.md
            if re.search(r'\.[a-z]{2}\.md$', file.lower()):
                logging.debug(f"Skip (locale filename): {rel_from_root}")
                continue

            # Derive output path
            out_path = input_path.replace(input_base_dir, output_base_dir)
            out_path = out_path.replace(os.sep + "en" + os.sep, os.sep)

            yaml_data_for_title, _ = extract_yaml_and_body(input_path)
            yaml_data_for_title.pop('evidence', None)

            if yaml_data_for_title.get('draft') is True:
                logging.debug(f"Skip (draft=true): {rel_from_root}")
                continue

            if is_index_file(file):
                # _index.md / index.md  →  {parent}.md
                parent_dir = os.path.dirname(out_path)
                base = os.path.basename(parent_dir)
                grandparent = os.path.dirname(parent_dir)
                candidate = os.path.join(grandparent, f"{base}.md")
                # Guard: if the candidate escapes the subdomain output dir
                # (happens when a root _index.md sits at the top of the
                # subdomain folder after /en/ stripping), anchor it to
                # index.md inside the subdomain dir.  make_page_url()
                # maps 'index.md' → the bare site root URL.
                abs_candidate = os.path.abspath(candidate)
                abs_subdir = os.path.abspath(subdomain_output_dir)
                # Use commonpath to correctly detect containment (avoids
                # prefix false-positives like dir.md vs dir/)
                try:
                    is_inside = os.path.commonpath([abs_candidate, abs_subdir]) == abs_subdir
                except ValueError:
                    is_inside = False
                if not is_inside:
                    out_path = os.path.join(subdomain_output_dir, "index.md")
                else:
                    out_path = candidate
                display = yaml_data_for_title.get('title') or clean_title_from_filename(base)
            else:
                display = yaml_data_for_title.get('title') or clean_title_from_filename(file)

            # Collision detection: two inputs mapping to the same output path
            # (e.g. flat introducing-foo.md + directory introducing-foo/index.md).
            # Prefer the directory-style index.md source over a flat file.
            if out_path in out_path_claimed:
                existing_input = out_path_claimed[out_path]
                new_is_index = is_index_file(file)
                existing_is_index = is_index_file(os.path.basename(existing_input))
                if new_is_index and not existing_is_index:
                    # New is index.md — replace the flat file entry
                    logging.warning(
                        f"Output collision: replacing flat {existing_input} "
                        f"with directory-index {input_path} → {out_path}"
                    )
                    del file_output_mapping[existing_input]
                    # Fall through to register new
                else:
                    # Keep existing; skip current
                    logging.warning(
                        f"Output collision: keeping {existing_input}, "
                        f"skipping {input_path} → {out_path}"
                    )
                    continue

            out_path_claimed[out_path] = input_path
            file_output_mapping[input_path] = (out_path, display)

    logging.info(f"Pass 1 complete — {len(file_output_mapping)} files mapped.")

    # ------------------------------------------------------------------
    # Pass 2: Convert — render each file and write to output.
    # ------------------------------------------------------------------
    logging.info("Pass 2: converting files…")

    for root, dirs, files in os.walk(input_base_dir):
        # Keep walk deterministic and skip non-EN locale folders
        dirs[:] = sorted(
            d for d in dirs
            if not (re.fullmatch(r'[a-z]{2}', d) and d != 'en')
        )

        for file in sorted(files):
            input_path = os.path.join(root, file)
            if input_path not in file_output_mapping:
                continue

            final_out_path, _ = file_output_mapping[input_path]

            # Build child treeview for index files
            treeview = ""
            if is_index_file(file):
                children_links = []
                for child_name in sorted(os.listdir(root)):
                    child_path = os.path.join(root, child_name)
                    if child_path == input_path:
                        continue

                    lookup = child_path
                    if os.path.isdir(child_path):
                        found = False
                        for idx in ('_index.md', 'index.md'):
                            candidate = os.path.join(child_path, idx)
                            if os.path.exists(candidate):
                                lookup = candidate
                                found = True
                                break
                        if not found:
                            continue

                    if lookup in file_output_mapping:
                        child_out, child_display = file_output_mapping[lookup]
                        child_rel = os.path.relpath(child_out, subdomain_output_dir).replace('\\', '/')
                        child_is_idx = is_index_file(os.path.basename(lookup))
                        child_url = make_page_url(
                            site_mapping.get_site_url(args.subdomain),
                            child_rel,
                            child_is_idx,
                        )
                        children_links.append(f"- [{child_display}]({child_url})")

                if children_links:
                    treeview = "\n\n## Related Topics\n" + "\n".join(children_links)

            try:
                md_out = converter.process_file(input_path, args.subdomain, input_base_dir)
                if treeview:
                    md_out += treeview
                md_out = sanitize_markdown(md_out)

                # TC-W4-003: Prepend stable page header block to all outputs.
                # Header is computed here, after sanitization, so it never
                # gets sanitized away. Index files get a minimal header too.
                _rel_out_for_header = os.path.relpath(
                    final_out_path, subdomain_output_dir
                ).replace('\\', '/')
                _page_type = detect_page_type(input_path, file, args.subdomain)
                _family, _platform = _extract_family_platform(_rel_out_for_header)
                _site_url = site_mapping.get_site_url(args.subdomain)
                _is_idx = is_index_file(file)
                _canonical = make_page_url(_site_url, _rel_out_for_header, _is_idx)
                _header = build_page_header(_page_type, _family, _platform, _canonical)
                md_out = _header + '\n\n' + md_out

                os.makedirs(os.path.dirname(final_out_path), exist_ok=True)
                with open(final_out_path, 'w', encoding='utf-8') as f:
                    f.write(md_out)
                logging.info(f"Written: {final_out_path}")

                txt_out_path = txt_path_from_md_path(final_out_path)
                with open(txt_out_path, 'w', encoding='utf-8') as f:
                    f.write(md_out)
                logging.info(f"Written txt: {txt_out_path}")

            except Exception as e:
                logging.error(f"Error processing {input_path}: {e}")

    logging.info("Pass 2 complete.")

    # ------------------------------------------------------------------
    # Collect metadata for llms.txt generation
    # ------------------------------------------------------------------
    site_url_base = site_mapping.get_site_url(args.subdomain)
    all_files_info = []

    for input_p, (final_out_p, display_name) in file_output_mapping.items():
        rel_out_p = os.path.relpath(final_out_p, subdomain_output_dir).replace('\\', '/')

        md_content = ""
        try:
            with open(final_out_p, encoding='utf-8') as f:
                md_content = f.read()
        except Exception as e:
            logging.warning(f"Cannot read {final_out_p} for llms.txt: {e}")
            continue

        # Re-read yaml to get frontmatter description (evidence already stripped
        # during conversion, but we re-read separately for description lookup).
        yaml_data_raw, md_body_raw = extract_yaml_and_body(input_p)
        yaml_data_raw.pop('evidence', None)
        description = extract_description(yaml_data_raw, md_body_raw)

        original_is_index = is_index_file(os.path.basename(input_p))
        abs_url = make_page_url(site_url_base, rel_out_p, original_is_index)

        h1_title, _ = extract_h1_and_first_sentence(md_content)

        h1_source_path_cfg = site_mapping.get_h1_source_path(args.subdomain)
        is_root_h1_source = False
        if h1_source_path_cfg:
            input_rel = os.path.relpath(input_p, input_base_dir).replace('\\', '/')
            is_root_h1_source = (input_rel == h1_source_path_cfg)

        all_files_info.append({
            'input_path': input_p,
            'final_output_path': final_out_p,
            'rel_output_path': rel_out_p,
            'absolute_url': abs_url,
            'title': h1_title or display_name,
            'description': description,
            'is_original_index': original_is_index,
            'is_root_h1_source': is_root_h1_source,
            'md_content': md_content,
        })

    # Deterministic sort
    all_files_info.sort(key=lambda x: x['rel_output_path'])

    # ------------------------------------------------------------------
    # Generate llms.txt
    # ------------------------------------------------------------------
    logging.info("Generating llms.txt…")
    llms_lines: List[str] = []

    if args.subdomain == "blog.aspose.org":
        # ----------------------------------------------------------------
        # Blog: two-level  ## Family / ### Platform / - post bullets
        # ----------------------------------------------------------------
        blog_root_meta = site_mapping.get_virtual_metadata(args.subdomain)
        root_title = blog_root_meta.get('title', 'Aspose FOSS Blog') if blog_root_meta else 'Aspose FOSS Blog'
        root_desc = blog_root_meta.get('description', '') if blog_root_meta else ''
        root_url = site_url_base + '/'

        # Find the root index file info if it exists
        blog_root_info = None
        for info in all_files_info:
            segs = [s for s in os.path.relpath(
                info['input_path'], input_base_dir
            ).replace('\\', '/').split('/') if s]
            # Root index: subdomain/_index.md or subdomain/index.md at depth 2
            if (len(segs) == 2 and segs[0] == args.subdomain
                    and is_index_file(segs[1])):
                blog_root_info = info
                break

        if blog_root_info:
            root_url = blog_root_info['absolute_url']
            if blog_root_info['title']:
                root_title = blog_root_info['title']

        llms_lines.append(f"# [{root_title}]({root_url})\n{root_desc}")

        current_family: Optional[str] = None
        current_platform: Optional[str] = None

        for entry in all_files_info:
            # Skip root
            if blog_root_info and entry['final_output_path'] == blog_root_info['final_output_path']:
                continue

            parts = entry['rel_output_path'].split('/')
            # Determine family and platform from path
            # Possible shapes:
            #   ['family.md']                              — family index
            #   ['family', 'platform.md']                 — platform index
            #   ['family', 'platform', 'slug.md']         — post (was index.md)

            if not parts:
                continue

            family_raw = parts[0].replace('.md', '')
            if family_raw not in FAMILY_NAME_MAP and family_raw not in site_mapping.mapping.get(args.subdomain, {}).get('families', {}):
                # Not a recognised family; skip (e.g. archive pages)
                continue

            if len(parts) == 1:
                # Family-level index page — emit family header
                if current_family != family_raw:
                    current_family = family_raw
                    current_platform = None
                    fam_meta = site_mapping.get_virtual_metadata(args.subdomain, family=family_raw)
                    fam_title = fam_meta.get('title', FAMILY_NAME_MAP.get(family_raw, clean_title_from_filename(family_raw))) if fam_meta else FAMILY_NAME_MAP.get(family_raw, clean_title_from_filename(family_raw))
                    fam_desc = fam_meta.get('description', '') if fam_meta else ''
                    fam_url = f"{site_url_base}/{family_raw}/"
                    llms_lines.append(f"\n## [{fam_title}]({fam_url})\n{fam_desc}")
                # Don't emit a bullet for the index itself
                continue

            platform_raw = parts[1].replace('.md', '') if len(parts) >= 2 else ''

            # Emit family header if changed
            if current_family != family_raw:
                current_family = family_raw
                current_platform = None
                fam_meta = site_mapping.get_virtual_metadata(args.subdomain, family=family_raw)
                fam_title = fam_meta.get('title', FAMILY_NAME_MAP.get(family_raw, clean_title_from_filename(family_raw))) if fam_meta else FAMILY_NAME_MAP.get(family_raw, clean_title_from_filename(family_raw))
                fam_desc = fam_meta.get('description', '') if fam_meta else ''
                fam_url = f"{site_url_base}/{family_raw}/"
                llms_lines.append(f"\n## [{fam_title}]({fam_url})\n{fam_desc}")

            if len(parts) == 2:
                # Platform-level index — emit platform header
                if current_platform != platform_raw:
                    current_platform = platform_raw
                    plat_display = PLATFORM_DISPLAY_MAP.get(platform_raw, platform_raw.capitalize())
                    plat_desc = site_mapping.get_platform_description(args.subdomain, family_raw, platform_raw)
                    plat_url = f"{site_url_base}/{family_raw}/{platform_raw}/"
                    header = f"\n### [{plat_display}]({plat_url})"
                    if plat_desc:
                        header += f"\n{plat_desc}"
                    llms_lines.append(header)
                # Don't emit a bullet for the platform index itself
                continue

            # len(parts) >= 3 — actual post
            if current_platform != platform_raw:
                current_platform = platform_raw
                plat_display = PLATFORM_DISPLAY_MAP.get(platform_raw, platform_raw.capitalize())
                plat_desc = site_mapping.get_platform_description(args.subdomain, family_raw, platform_raw)
                plat_url = f"{site_url_base}/{family_raw}/{platform_raw}/"
                header = f"\n### [{plat_display}]({plat_url})"
                if plat_desc:
                    header += f"\n{plat_desc}"
                llms_lines.append(header)

            title = entry['title'] or clean_title_from_filename(parts[-1])
            desc = entry['description']
            url = entry['absolute_url']
            bullet = f"- [{title}]({url})"
            if desc:
                bullet += f": {desc}"
            llms_lines.append(bullet)

    else:
        # ----------------------------------------------------------------
        # Non-blog subdomains: tree-based rendering
        # ----------------------------------------------------------------
        root_info = None

        # Try the configured h1_path first
        h1_path_key = site_mapping.get_h1_source_path(args.subdomain)
        if h1_path_key:
            for info in all_files_info:
                if info['is_root_h1_source']:
                    root_info = info
                    break

        # Fallback: find the shallowest _index.md under the subdomain.
        # We measure depth ignoring the 'en' locale directory layer so that
        # subdomain/en/_index.md (depth 1 effective) sorts before
        # subdomain/en/3d/_index.md (depth 2 effective).
        if not root_info:
            candidates = []
            for info in all_files_info:
                segs = os.path.relpath(
                    info['input_path'], input_base_dir
                ).replace('\\', '/').split('/')
                if segs[0] != args.subdomain or not is_index_file(segs[-1]):
                    continue
                effective = [s for s in segs[1:] if s != 'en']
                candidates.append((len(effective), info))
            if candidates:
                candidates.sort(key=lambda x: x[0])
                root_info = candidates[0][1]

        root_title = clean_title_from_filename(args.subdomain)
        root_desc = ''
        root_url = site_url_base

        if root_info:
            root_title = root_info['title'] or root_title
            root_desc = root_info['description']
            root_url = root_info['absolute_url']
        else:
            root_meta = site_mapping.get_virtual_metadata(args.subdomain)
            if root_meta:
                root_title = root_meta.get('title', root_title)
                root_desc = root_meta.get('description', root_desc)
            logging.warning(f"No root H1 found for {args.subdomain}; using defaults.")

        llms_lines.append(f"# [{root_title}]({root_url})\n{root_desc}")

        llms_tree = build_llms_tree(all_files_info)
        root_rel_path = root_info['rel_output_path'] if root_info else None
        llms_lines.extend(render_llms_tree(llms_tree, root_path=root_rel_path))

    # Write llms.txt
    llms_out_path = os.path.join(subdomain_output_dir, "llms.txt")
    try:
        with open(llms_out_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(llms_lines))
        logging.info(f"llms.txt written: {llms_out_path}")
    except Exception as e:
        logging.error(f"Error writing llms.txt: {e}")

    # ------------------------------------------------------------------
    # Generate llms-full.txt — complete page content for RAG ingestion
    # ------------------------------------------------------------------
    logging.info("Generating llms-full.txt…")
    full_parts: List[str] = []

    for entry in all_files_info:
        header = f"# {entry['title']}\nURL: {entry['absolute_url']}"
        if entry['description']:
            header += f"\n{entry['description']}"
        body = entry['md_content'].strip()
        full_parts.append(f"{header}\n\n{body}")

    llms_full_path = os.path.join(subdomain_output_dir, "llms-full.txt")
    try:
        with open(llms_full_path, 'w', encoding='utf-8') as f:
            f.write('\n\n---\n\n'.join(full_parts))
        logging.info(f"llms-full.txt written: {llms_full_path}")
    except Exception as e:
        logging.error(f"Error writing llms-full.txt: {e}")

    # ------------------------------------------------------------------
    # Hierarchical index generation (optional)
    # ------------------------------------------------------------------
    if args.mode == 'hierarchical':
        logging.info("Generating hierarchical indexes…")
        generate_hierarchical_indexes(
            all_files_info,
            subdomain_output_dir,
            site_url_base,
            args.subdomain,
            site_mapping,
        )

    logging.info("Done.")
    print(f"INFO: Done.")
    print(f"Output written to: {subdomain_output_dir}")
    print(f"See {LOG_FILENAME} for details.")


if __name__ == "__main__":
    main()
