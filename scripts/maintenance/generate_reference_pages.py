#!/usr/bin/env python3
"""
Generate missing API reference pages for slides/java, slides/net, slides/cpp.
Does NOT overwrite existing files.
"""

import json
import os
import re
import textwrap

BASE = "D:/onedrive/Documents/GitHub/aspose.org"

# ---------------------------------------------------------------------------
# Platform configuration
# ---------------------------------------------------------------------------
PLATFORMS = [
    {
        "family": "slides",
        "platform": "java",
        "lang": "Java",
        "package": "com.aspose.slides",
        "model_sha": "44597f1a09feb16ed1b6f29a1c6b939df4415863",
        "model_version": "1.0.0",
        "class_kinds": {"class_declaration"},
        "enum_kinds": {"enum_declaration"},
        "interface_kinds": {"interface_declaration"},
        "record_kinds": set(),
        "category_map": {
            "class_declaration": "Class",
            "enum_declaration": "Enum",
            "interface_declaration": "Interface",
            "function": "Class",
        },
        "skip_i_prefix": False,
        "skip_bases": set(),
    },
    {
        "family": "slides",
        "platform": "net",
        "lang": "C# (.NET)",
        "package": "Aspose.Slides",
        "model_sha": "bd19e16057b628310b4a04330585d366cb40e9b7",
        "model_version": "26.3.0",
        "class_kinds": {"class_declaration", "record_declaration"},
        "enum_kinds": {"enum_declaration"},
        "interface_kinds": {"interface_declaration"},
        "record_kinds": {"record_declaration"},
        "category_map": {
            "class_declaration": "Class",
            "record_declaration": "Class",
            "enum_declaration": "Enum",
            "interface_declaration": "Interface",
        },
        "skip_i_prefix": False,
        "skip_bases": set(),
    },
    {
        "family": "slides",
        "platform": "cpp",
        "lang": "C++",
        "package": "Aspose::Slides",
        "model_sha": "25adb25c8796f06d9b89cd5f8093e490091195ef",
        "model_version": "",
        "class_kinds": {"class_specifier", "struct_specifier"},
        "enum_kinds": {"enum_specifier"},
        "interface_kinds": set(),
        "record_kinds": set(),
        "category_map": {
            "class_specifier": "Class",
            "struct_specifier": "Class",
            "enum_specifier": "Enum",
        },
        "skip_i_prefix": True,
        "skip_bases": {"BaseSlide", "GeometryShape", "PVIObject", "GraphicalObject"},
    },
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def existing_files(out_dir):
    """Return set of basenames (no extension) already in out_dir."""
    if not os.path.isdir(out_dir):
        return set()
    return {
        os.path.splitext(fn)[0]
        for fn in os.listdir(out_dir)
        if fn.endswith(".md") and fn != "_index.md"
    }


def fmt_params(params):
    if not params:
        return ""
    parts = []
    for p in params:
        name = p.get("name", "")
        typ = p.get("type", "")
        if typ:
            parts.append(f"{typ} {name}".strip())
        else:
            parts.append(name)
    return ", ".join(parts)


def clean_doc(doc):
    """Strip Javadoc-style tags and curly brace escapes."""
    if not doc:
        return ""
    # Remove {@code ...} → just the content
    doc = re.sub(r"\{@code ([^}]+)\}", r"\1", doc)
    # Remove {@link ...}
    doc = re.sub(r"\{@link ([^}]+)\}", r"\1", doc)
    # Collapse whitespace/newlines
    doc = re.sub(r"\s+", " ", doc).strip()
    # Truncate to first sentence
    m = re.match(r"([^.!?]+[.!?])", doc)
    if m:
        return m.group(1).strip()
    return doc[:120].strip()


def get_category(item, cfg):
    kind = item.get("kind", "")
    return cfg["category_map"].get(kind, "Class")


def is_enum(item, cfg):
    return item.get("kind", "") in cfg["enum_kinds"]


def should_skip_name(name, cfg):
    """Return True if this class name should be excluded."""
    if name.startswith("Test") or name.startswith("test_") or name.startswith("_"):
        return True
    if cfg["skip_i_prefix"] and re.match(r"^I[A-Z]", name):
        return True
    if name in cfg["skip_bases"]:
        return True
    return False


# ---------------------------------------------------------------------------
# Page generation
# ---------------------------------------------------------------------------

def build_page(item, cfg):
    name = item["name"]
    kind = item.get("kind", "")
    raw_doc = item.get("doc", "")
    doc = clean_doc(raw_doc) or f"{name} API type."
    bases = item.get("bases", [])
    methods = item.get("methods", [])
    properties = item.get("properties", [])
    enum_members = item.get("enum_members", [])

    category = get_category(item, cfg)
    lang = cfg["lang"]
    package = cfg["package"]
    platform = cfg["platform"]
    model_sha = cfg["model_sha"]
    model_version = cfg["model_version"]

    # Determine primary api for evidence
    primary_api = name
    non_ctor_methods = [m for m in methods if not m.get("is_constructor", False)]
    if non_ctor_methods:
        primary_api = f"{name}.{non_ctor_methods[0]['name']}"

    # Inheritance note
    bases_clean = [b for b in bases if b != name]  # skip self-referencing bases (cpp)
    inherit_note = ""
    if bases_clean:
        inherit_note = " Inherits from: " + ", ".join(f"`{b}`" for b in bases_clean) + "."

    # --- Front matter ---
    fm_lines = [
        "---",
        f"linkTitle: {name}",
        f"title: {name} \u2014 Aspose.Slides FOSS {lang} API Reference",
        f"description: {doc}",
        f"summary: {doc}",
        f"categories:",
        f"- {category}",
        f"layout: reference-single",
        f"evidence:",
        f"  model_sha: {model_sha}",
        f"  model_version: '{model_version}'",
        f"  claims: []",
        f"  apis:",
        f"  - {primary_api}",
        "---",
    ]

    body_lines = [
        "",
        f"{name} \u2014 {doc}{inherit_note}",
        "",
        f"**Package**: `{package}`",
        "",
        "---",
        "",
    ]

    # Enum page
    if is_enum(item, cfg) and enum_members:
        body_lines += [
            "## Values",
            "",
            "| Member | Description |",
            "|---|---|",
        ]
        for em in enum_members:
            em_name = em.get("name", "")
            em_doc = clean_doc(em.get("doc", "")) or ""
            body_lines.append(f"| `{em_name}` | {em_doc} |")
        body_lines.append("")
        body_lines.append("---")
        body_lines.append("")
    else:
        # Properties
        if properties:
            body_lines += [
                "## Properties",
                "",
                "| Property | Type | Access | Description |",
                "|---|---|---|---|",
            ]
            for prop in properties:
                pname = prop.get("name", "")
                ptype = prop.get("type", "")
                writable = prop.get("writable", True)
                access = "Read/Write" if writable else "Read"
                pdoc = clean_doc(prop.get("doc", "")) or ""
                body_lines.append(f"| `{pname}` | `{ptype}` | {access} | {pdoc} |")
            body_lines.append("")
            body_lines.append("---")
            body_lines.append("")

        # Methods (exclude constructors)
        public_methods = [m for m in methods if not m.get("is_constructor", False)]
        if public_methods:
            body_lines += [
                "## Methods",
                "",
                "| Method | Returns | Description |",
                "|---|---|---|",
            ]
            for m in public_methods:
                mname = m.get("name", "")
                mret = m.get("return_type", "") or "void"
                mparams = fmt_params(m.get("params", []))
                mdoc = clean_doc(m.get("doc", "")) or ""
                body_lines.append(f"| `{mname}({mparams})` | `{mret}` | {mdoc} |")
            body_lines.append("")
            body_lines.append("---")
            body_lines.append("")

        # Stub note if nothing documented
        if not properties and not public_methods:
            body_lines += [
                "No public API members documented in source.",
                "",
                "---",
                "",
            ]

    # See Also
    body_lines += [
        "## See Also",
        "",
        f"- [Aspose.Slides FOSS {lang} API Reference home](/slides/{platform}/)",
        "",
    ]

    return "\n".join(fm_lines) + "\n" + "\n".join(body_lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def process_platform(cfg):
    family = cfg["family"]
    platform = cfg["platform"]
    knowledge_dir = os.path.join(BASE, "knowledge", family, platform, "merged")
    out_dir = os.path.join(BASE, "content", "reference.aspose.org", "en", family, platform)

    index = load_json(os.path.join(knowledge_dir, "index.json"))
    api_surface_list = load_json(os.path.join(knowledge_dir, "api_surface.json"))

    # Build lookup by name
    api_by_name = {item["name"]: item for item in api_surface_list}

    # Get all valid class names from index
    class_names = index.get("classes", [])

    # Get existing files
    existing = existing_files(out_dir)

    os.makedirs(out_dir, exist_ok=True)

    generated = 0
    skipped_exists = 0
    skipped_filter = 0

    for name in class_names:
        # Apply skip filters
        if should_skip_name(name, cfg):
            skipped_filter += 1
            continue

        # Skip if file exists
        if name in existing:
            skipped_exists += 1
            continue

        # Get api_surface entry (or create minimal stub entry)
        item = api_by_name.get(name)
        if item is None:
            # Minimal stub
            item = {
                "name": name,
                "kind": "class_declaration",
                "doc": "",
                "bases": [],
                "methods": [],
                "properties": [],
                "enum_members": [],
            }

        page_content = build_page(item, cfg)
        out_path = os.path.join(out_dir, f"{name}.md")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(page_content)
        generated += 1

    print(f"  [{platform}] Generated: {generated}, Skipped (exists): {skipped_exists}, Skipped (filter): {skipped_filter}")
    return generated


if __name__ == "__main__":
    total = 0
    for cfg in PLATFORMS:
        print(f"\nProcessing slides/{cfg['platform']}...")
        n = process_platform(cfg)
        total += n
    print(f"\nTotal pages generated: {total}")
