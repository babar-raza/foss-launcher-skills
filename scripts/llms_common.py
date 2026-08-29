"""llms_common.py -- shared helpers for the llms_generate/coverage/fidelity family.

Generalized 2026-08-29 from aspose.org's llms-generate/llms-coverage/
llms-fidelity skills (S-LG-01/03/04). aspose.org's own backing scripts
(scripts/generator/llms-generator.py etc.) hardcode a fixed list of 5
aspose.org subdomains -- this port replaces that with iteration over
config.yaml's existing `sites:` block, which already has exactly the right
shape (site-type -> content_path template) for this. Live-HTTP endpoint
verification (source's llms-verify) and the provenance-hash staleness
manifest (source's llms-stale) are explicitly NOT ported this pass -- see
docs/parity/source-anchors.yaml notes and TASK_BACKLOG.md.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?", re.DOTALL)
_H2_RE = re.compile(r"^##[ \t]", re.MULTILINE)
_CODE_FENCE_RE = re.compile(r"^```", re.MULTILINE)
_TABLE_ROW_RE = re.compile(r"^\|.+\|[ \t]*$", re.MULTILINE)
_SHORTCODE_RE = re.compile(r"\{\{|\{%")
_EVIDENCE_FIELD_RE = re.compile(r"\b(claim_id|model_sha|graded_content_hash)\s*:")
_H1_RE = re.compile(r"^#[ \t]+(.+)$", re.MULTILINE)


def site_base_dir(content_path_template: str) -> str:
    """The walkable directory prefix of a config.yaml site content_path
    template, e.g. 'content/docs.aspose.org/en/{family}/{platform}/' ->
    'content/docs.aspose.org/en'."""
    prefix = content_path_template.split("{", 1)[0]
    return prefix.rstrip("/")


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Split simple YAML-ish frontmatter (key: value lines only -- no
    nested structures) from the body. Returns ({}, text) if no frontmatter
    block is found."""
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    raw = match.group(1)
    body = text[match.end():]
    fields: dict[str, Any] = {}
    for line in raw.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if value.lower() == "true":
            fields[key] = True
        elif value.lower() == "false":
            fields[key] = False
        elif value:
            fields[key] = value
    return fields, body


def extract_title(frontmatter: dict, body: str) -> str:
    if frontmatter.get("title"):
        return str(frontmatter["title"])
    h1 = _H1_RE.search(body)
    return h1.group(1).strip() if h1 else ""


def is_eligible_page(frontmatter: dict) -> bool:
    """English, non-draft pages only -- matches source's llms-generate scope."""
    if frontmatter.get("draft"):
        return False
    return True


def iter_site_pages(content_root: Path, content_path_template: str):
    """Yield every .md file under a site's base directory."""
    base = content_root / site_base_dir(content_path_template)
    if not base.is_dir():
        return
    for path in sorted(base.rglob("*.md")):
        yield path


def structural_counts(text: str) -> dict:
    return {
        "h2_count": len(_H2_RE.findall(text)),
        "code_fence_count": len(_CODE_FENCE_RE.findall(text)),
        "table_row_count": len(_TABLE_ROW_RE.findall(text)),
        "has_shortcode": bool(_SHORTCODE_RE.search(text)),
        "has_evidence_field": bool(_EVIDENCE_FIELD_RE.search(text)),
    }
