"""
SEO-TITLE-TEMPLATE-REGISTRY title_templates.py
=================================================
Loads scripts/pipeline/config/title_templates.yaml (the peer-consistent
title skeleton registry, Finding #22) and provides two operations every
downstream title-consistency consumer needs:

  resolve_title()      -- format a page_type's skeleton (or its fallback,
                           when no content clause is available/appropriate)
                           into a concrete title string.
  check_conformance()   -- given an EXISTING title, determine whether it
                           already matches its page_type's registered
                           pattern (rigid types: exact skeleton match;
                           docs_devguide_index: prefix + <=6-word clause,
                           OR the literal fallback).

This module does NOT decide *which* content clause to use for a page (that
priority cascade -- gsc_query -> description -> formats_json -> claims_json
-> curated_keywords -- is SEO-TITLE-CONSISTENCY-EVALUATOR's job, the next
task in this lane); it only knows how to plug an already-chosen clause into
the skeleton, and how to check an existing title's shape.

No LLM calls. No network calls. stdlib + pathlib + pyyaml only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    sys.exit("title_templates.py requires PyYAML: pip install pyyaml")

REPO_ROOT = Path(__file__).resolve().parents[3]
REGISTRY_PATH = REPO_ROOT / "scripts" / "pipeline" / "config" / "title_templates.yaml"

_PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")


class UnknownPageType(KeyError):
    pass


class MissingPlaceholder(KeyError):
    pass


def load_registry(path: Path | None = None) -> dict:
    path = path or REGISTRY_PATH
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _page_type_entry(registry: dict, page_type: str) -> dict:
    page_types = registry.get("page_types", {})
    if page_type not in page_types:
        raise UnknownPageType(f"page_type '{page_type}' is not registered in title_templates.yaml")
    return page_types[page_type]


def _format_skeleton(skeleton: str, values: dict[str, str]) -> str:
    placeholders = _PLACEHOLDER_RE.findall(skeleton)
    missing = [p for p in placeholders if p not in values or values[p] is None]
    if missing:
        raise MissingPlaceholder(f"missing value(s) for placeholder(s): {missing}")
    return skeleton.format(**values)


def resolve_title(
    page_type: str,
    *,
    family: str,
    platform: str | None = None,
    class_name: str | None = None,
    category: str | None = None,
    content_clause: str | None = None,
    registry: dict | None = None,
) -> str:
    """Resolve a concrete title string for `page_type`.

    If `content_clause` is None (or the page_type is rigid, i.e. never takes
    a content clause), the fallback_skeleton is used instead of raising --
    a page type intentionally without page-specific signal (kb_faq,
    products_family_root, reference_class) always resolves successfully.
    """
    registry = registry or load_registry()
    entry = _page_type_entry(registry, page_type)

    values = {
        "Family": family,
        "Platform": platform,
        "ClassName": class_name,
        "Category": category,
        "ContentClause": content_clause,
    }

    use_fallback = entry.get("rigid", False) or not content_clause
    skeleton = entry["fallback_skeleton"] if use_fallback else entry["skeleton"]
    return _format_skeleton(skeleton, values)


def _skeleton_to_conformance_regex(skeleton: str, values: dict[str, str], clause_placeholder: str, max_clause_words: int) -> re.Pattern:
    """Build a regex that matches skeleton with `clause_placeholder` replaced
    by a bounded free-text clause, and every other placeholder replaced by
    its literal (escaped) known value.
    """
    parts = _PLACEHOLDER_RE.split(skeleton)
    # re.split with a capturing group returns [literal, placeholder, literal, placeholder, ..., literal]
    pattern_parts = []
    for i, part in enumerate(parts):
        if i % 2 == 1:  # this part is a placeholder name
            if part == clause_placeholder:
                # bounded: 1..max_clause_words words, each word has no " — " etc.
                pattern_parts.append(r"\S+(?:\s+\S+){0,%d}" % (max_clause_words - 1))
            else:
                literal = values.get(part, "")
                pattern_parts.append(re.escape(str(literal)))
        else:
            pattern_parts.append(re.escape(part))
    return re.compile("^" + "".join(pattern_parts) + "$")


def check_conformance(
    title: str,
    page_type: str,
    *,
    family: str,
    platform: str | None = None,
    class_name: str | None = None,
    category: str | None = None,
    registry: dict | None = None,
) -> bool:
    """Whether `title` already matches page_type's registered pattern.

    Rigid types (kb_faq, products_family_root, reference_class): exact match
    against the fully-resolved fallback_skeleton (there is no clause to vary).

    docs_devguide_index (not rigid): matches EITHER the literal fallback
    ("...Developer Guide") OR the skeleton with a bounded (<=6-word) clause
    in the ContentClause slot.
    """
    registry = registry or load_registry()
    entry = _page_type_entry(registry, page_type)
    max_words = registry.get("max_content_clause_words", 6)

    values = {"Family": family, "Platform": platform, "ClassName": class_name, "Category": category}

    fallback_resolved = _format_skeleton(entry["fallback_skeleton"], values)
    if title == fallback_resolved:
        return True

    if entry.get("rigid", False):
        return False

    pattern = _skeleton_to_conformance_regex(entry["skeleton"], values, "ContentClause", max_words)
    return bool(pattern.match(title))
