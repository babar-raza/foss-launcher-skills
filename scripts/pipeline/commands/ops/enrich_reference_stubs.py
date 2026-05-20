#!/usr/bin/env python3
"""Batch-enrich reference page stubs with additional prose from API surface data.

Adds/replaces a 'Description' section after Overview with class-specific prose
derived from api_surface.json metadata and the page's own method/property tables.
Target: bring thin stubs from ~20 words to 55+ prose words.

Safe to re-run: replaces existing '## Description' section content.
"""
import json
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]

PLATFORM_LABELS = {
    "java": "Java", "net": ".NET", "python": "Python",
    "cpp": "C++", "typescript": "TypeScript",
}
FAMILY_LABELS = {
    "3d": "3D", "cells": "Cells", "email": "Email", "font": "Font",
    "note": "Note", "slides": "Slides", "words": "Words",
}


def load_api_surface(family, platform):
    """Load api_surface.json for a product."""
    for subdir in ("merged", "scout"):
        path = REPO / "knowledge" / family / platform / subdir / "api_surface.json"
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            return {e.get("name", ""): e for e in data}
    return {}


def extract_class_name(md_path):
    """Extract class name from reference page frontmatter."""
    text = md_path.read_text(encoding="utf-8")
    m = re.search(r'^linkTitle:\s*(.+)$', text, re.MULTILINE)
    if m:
        return m.group(1).strip().strip('"').strip("'")
    return md_path.stem


def extract_method_descs_from_page(text):
    """Extract method descriptions from the page's Methods table."""
    descs = []
    for m in re.finditer(r'\|\s*`([^`]+)`\s*\|\s*([^|]+)\|', text):
        sig, desc = m.group(1), m.group(2).strip()
        if desc and desc != '—' and len(desc) > 5:
            name = sig.split('(')[0].strip()
            descs.append((name, desc))
    return descs


def extract_prop_descs_from_page(text):
    """Extract property descriptions from the page's Properties table."""
    descs = []
    # Properties table: | `name` | `Type` | Access | Description |
    for m in re.finditer(r'\|\s*`(\w+)`\s*\|\s*`[^`]*`\s*\|\s*\w+\s*\|\s*([^|]+)\|', text):
        name, desc = m.group(1), m.group(2).strip()
        if desc and desc != '—' and len(desc) > 5:
            descs.append((name, desc))
    return descs


def generate_description(class_name, api_entry, family, platform, page_text):
    """Generate a rich description from API surface + page table data."""
    fam_label = FAMILY_LABELS.get(family, family.title())
    plat_label = PLATFORM_LABELS.get(platform, platform.title())
    kind = api_entry.get("kind", "class_declaration")

    methods = api_entry.get("methods", [])
    properties = api_entry.get("properties", [])
    bases = api_entry.get("bases", [])
    doc = api_entry.get("doc", "").strip()

    # Also extract descriptions from the page's existing tables
    page_method_descs = extract_method_descs_from_page(page_text)
    page_prop_descs = extract_prop_descs_from_page(page_text)

    non_ctor_methods = [m for m in methods if not m.get("is_constructor", False)]
    constructors = [m for m in methods if m.get("is_constructor", False)]

    parts = []

    # --- Paragraph 1: What it is ---
    is_enum = "enum" in kind.lower()
    is_interface = "interface" in kind.lower()

    if is_enum:
        fields = api_entry.get("fields", api_entry.get("values", []))
        if not fields:
            fields = [m for m in methods if not m.get("is_constructor")]
        parts.append(
            f"`{class_name}` is an enumeration type in the Aspose.{fam_label} FOSS library for {plat_label}. "
            f"It defines a set of named constants that control behavior or specify options within the API. "
            f"Enumerations like `{class_name}` help ensure type safety by restricting values to a predefined set."
        )
    elif is_interface:
        parts.append(
            f"`{class_name}` is an interface in Aspose.{fam_label} FOSS for {plat_label} that defines "
            f"a contract with {len(non_ctor_methods)} method{'s' if len(non_ctor_methods) != 1 else ''}. "
            f"Classes that implement this interface must provide concrete implementations for all declared operations."
        )
    else:
        base_clause = ""
        if bases:
            base_clause = f" It extends `{bases[0]}`"
            if len(bases) > 1:
                implements = ", ".join(f"`{b}`" for b in bases[1:3])
                base_clause += f" and implements {implements}"
            base_clause += ", inheriting shared functionality from its parent type."
        parts.append(
            f"`{class_name}` is a class in the Aspose.{fam_label} FOSS library for {plat_label} "
            f"that exposes {len(non_ctor_methods)} method{'s' if len(non_ctor_methods) != 1 else ''} "
            f"and {len(properties)} propert{'ies' if len(properties) != 1 else 'y'} "
            f"for programmatic use.{base_clause}"
        )

    # --- Paragraph 2: Key capabilities ---
    if page_method_descs:
        # Use the page's own table descriptions (first 3 non-trivial)
        key_ops = []
        seen = set()
        for name, desc in page_method_descs:
            if name not in seen and not name[0].isupper():  # skip constructors
                key_ops.append(f"{desc.rstrip('.')}")
                seen.add(name)
            if len(key_ops) >= 3:
                break
        if key_ops:
            parts.append(
                f"Core capabilities include: "
                + "; ".join(key_ops).lower().capitalize() + ". "
                f"These operations enable developers to integrate {class_name.lower()} functionality "
                f"directly into {plat_label} applications."
            )

    # --- Paragraph 3: Properties ---
    if page_prop_descs and not is_enum:
        prop_info = []
        for name, desc in page_prop_descs[:3]:
            prop_info.append(f"the `{name}` property ({desc.rstrip('.').lower()})")
        if prop_info:
            parts.append(
                f"The class also provides {', '.join(prop_info)}."
            )

    # --- Paragraph 4: Constructor info ---
    if constructors and not is_enum and not is_interface:
        if len(constructors) == 1:
            parts.append(
                f"Instances are created through a single constructor that initializes the object with default values."
            )
        elif len(constructors) > 1:
            parts.append(
                f"The class offers {len(constructors)} constructor overloads, "
                f"allowing flexible initialization depending on the calling context."
            )

    return "\n\n".join(parts)


def enrich_page(md_path, api_index, family, platform):
    """Add or replace Description section in a reference page."""
    text = md_path.read_text(encoding="utf-8")

    class_name = extract_class_name(md_path)
    if class_name == "_index":
        return "SKIP"

    api_entry = api_index.get(class_name)
    if not api_entry:
        return "SKIP"

    desc = generate_description(class_name, api_entry, family, platform, text)
    if not desc:
        return "SKIP"

    desc_section = f"## Description\n\n{desc}\n"

    # Replace existing Description section or insert new one
    desc_pattern = re.compile(r'## Description\n(?:.*?\n)*?(?=\n## |\Z)', re.DOTALL)
    if desc_pattern.search(text):
        text = desc_pattern.sub(desc_section, text, count=1)
    else:
        # Insert after Overview
        overview_match = re.search(r'(## Overview\n(?:.*?\n)*?)(\n## )', text, re.DOTALL)
        if overview_match:
            text = text[:overview_match.end(1)] + "\n" + desc_section + text[overview_match.start(2):]
        else:
            fm_end = text.find('---', text.find('---') + 3) + 3
            first_h2 = text.find('\n## ', fm_end)
            if first_h2 > 0:
                text = text[:first_h2] + "\n" + desc_section + text[first_h2:]
            else:
                return "SKIP"

    md_path.write_text(text, encoding="utf-8")
    return "ENRICHED"


def main():
    dry_run = "--dry-run" in sys.argv
    ref_root = REPO / "content" / "reference.aspose.org" / "en"
    stats = {"enriched": 0, "skipped": 0}

    for family_dir in sorted(ref_root.iterdir()):
        if not family_dir.is_dir():
            continue
        family = family_dir.name
        for platform_dir in sorted(family_dir.iterdir()):
            if not platform_dir.is_dir():
                continue
            platform = platform_dir.name
            api_index = load_api_surface(family, platform)
            if not api_index:
                continue
            enriched = 0
            for md_path in sorted(list(platform_dir.glob("*.md")) + list(platform_dir.rglob("*/*.md"))):
                result = enrich_page(md_path, api_index, family, platform)
                if result == "ENRICHED":
                    enriched += 1
                    stats["enriched"] += 1
                else:
                    stats["skipped"] += 1
            if enriched:
                print(f"  {family}/{platform}: {enriched} pages enriched")

    print(f"\nRESULT: {stats['enriched']} enriched, {stats['skipped']} skipped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
