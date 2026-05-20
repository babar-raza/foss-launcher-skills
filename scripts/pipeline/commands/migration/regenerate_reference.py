# Adapted from aspose.org
#!/usr/bin/env python3
"""Regenerate email/net reference pages from api_surface.json.

Reads the merged API surface and writes properly populated reference
pages, replacing the blank template shells produced by the initial
batch-reference run.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
FAMILY = "email"
PLATFORM = "net"
SURFACE_PATH = REPO_ROOT / f"knowledge/{FAMILY}/{PLATFORM}/merged/api_surface.json"
SURFACE_MD = REPO_ROOT / f"knowledge/{FAMILY}/{PLATFORM}/merged/api_surface.md"
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", str(REPO_ROOT / f"content/reference/en/{FAMILY}/{PLATFORM}")))
MODEL_SHA = "a8999e259143a9ffc660086b34a7f39516da29f5"


def pascal_to_kebab(name: str) -> str:
    """Convert PascalCase to kebab-case."""
    s = re.sub(r"([A-Z])", r"-\1", name).lstrip("-").lower()
    return s


def merge_partial_classes(classes: list[dict]) -> dict[str, dict]:
    """Merge partial class definitions (e.g. MapiMessage appears 3x)."""
    merged: dict[str, dict] = {}
    for cls in classes:
        name = cls["name"]
        if name not in merged:
            merged[name] = {
                "name": name,
                "kind": cls.get("kind", "class_declaration"),
                "doc": cls.get("doc", ""),
                "file": cls.get("file", ""),
                "bases": list(cls.get("bases", [])),
                "methods": list(cls.get("methods", [])),
                "properties": list(cls.get("properties", [])),
                "enum_values": list(cls.get("enum_values", [])),
                # FR-15: preserve per-class import and namespace fields
                "class_import": cls.get("class_import", ""),
                "canonical_namespace": cls.get("canonical_namespace", ""),
            }
        else:
            existing = merged[name]
            # Merge bases (take non-empty)
            if cls.get("bases") and not existing["bases"]:
                existing["bases"] = list(cls["bases"])
            # Merge doc (take non-empty)
            if cls.get("doc") and not existing["doc"]:
                existing["doc"] = cls["doc"]
            # FR-15: merge class_import and canonical_namespace (take first non-empty)
            if cls.get("class_import") and not existing.get("class_import"):
                existing["class_import"] = cls["class_import"]
            if cls.get("canonical_namespace") and not existing.get("canonical_namespace"):
                existing["canonical_namespace"] = cls["canonical_namespace"]
            # Merge methods (append, dedup by name+param types)
            seen_methods = {
                (m["name"], tuple(p.get("type", "") for p in m.get("params", [])))
                for m in existing["methods"]
            }
            for m in cls.get("methods", []):
                key = (m["name"], tuple(p.get("type", "") for p in m.get("params", [])))
                if key not in seen_methods:
                    existing["methods"].append(m)
                    seen_methods.add(key)
            # Merge properties (dedup by name)
            seen_props = {p["name"] for p in existing["properties"]}
            for p in cls.get("properties", []):
                if p["name"] not in seen_props:
                    existing["properties"].append(p)
                    seen_props.add(p["name"])
            # Merge enum values
            seen_enums = {e["name"] if isinstance(e, dict) else e for e in existing["enum_values"]}
            for e in cls.get("enum_values", []):
                ename = e["name"] if isinstance(e, dict) else e
                if ename not in seen_enums:
                    existing["enum_values"].append(e)
                    seen_enums.add(ename)
    return merged


def format_method_signature(m: dict) -> str:
    """Format a method as 'Name(param1, param2) → ReturnType'."""
    params = m.get("params", [])
    param_str = ", ".join(
        f"{p['name']}: {p.get('type', '?')}" if p.get("type") else p["name"]
        for p in params
    )
    sig = f"{m['name']}({param_str})"
    ret = m.get("return_type", "")
    if ret:
        sig += f" → {ret}"
    return sig


def format_property_access(p: dict) -> str:
    """Return access label for a property from access_mode or has_setter."""
    access_mode = p.get("access_mode", "")
    if access_mode == "readonly":
        return "Read"
    if access_mode == "writeonly":
        return "Write"
    if access_mode == "readwrite":
        return "Read/Write"
    # Fall back to has_setter for .NET / other platforms
    return "Read/Write" if p.get("has_setter") else "Read"


def is_enum(cls: dict) -> bool:
    """Check if a class is an enum."""
    return bool(cls.get("enum_values"))


def classify(cls: dict) -> str:
    """Return 'Enum', 'Interface', or 'Class'."""
    if is_enum(cls):
        return "Enum"
    kind = cls.get("kind", "")
    if "interface" in kind:
        return "Interface"
    return "Class"


def build_description(cls: dict) -> str:
    """Build a description string for frontmatter."""
    name = cls["name"]
    category = classify(cls)
    bases = cls.get("bases", [])

    if cls.get("doc"):
        return cls["doc"].strip().rstrip(".")

    base_str = ""
    if bases:
        base_str = f" ({', '.join(bases)})"

    n_methods = len([m for m in cls.get("methods", []) if not m.get("is_constructor")])
    n_props = len(cls.get("properties", []))
    n_enum = len(cls.get("enum_values", []))

    if is_enum(cls):
        return f"{name} enum with {n_enum} members{base_str}"

    parts = []
    if n_methods:
        parts.append(f"{n_methods} method{'s' if n_methods > 1 else ''}")
    if n_props:
        parts.append(f"{n_props} propert{'ies' if n_props > 1 else 'y'}")
    member_str = " and ".join(parts) if parts else "no public members"

    return f"{name} {category.lower()}{base_str} with {member_str}"


def generate_page(cls: dict) -> str:
    """Generate the full markdown content for a reference page."""
    name = cls["name"]
    category = classify(cls)
    bases = cls.get("bases", [])
    methods = cls.get("methods", [])
    properties = cls.get("properties", [])
    enum_values = cls.get("enum_values", [])
    doc = cls.get("doc", "")
    desc = build_description(cls)

    # FR-15: per-class class_import overrides root canonical_import
    class_import = cls.get("class_import", "")

    # FR-15: per-class canonical_namespace for C++ namespace label
    canonical_namespace = cls.get("canonical_namespace", "")

    constructors = [m for m in methods if m.get("is_constructor")]
    non_constructor_methods = [m for m in methods if not m.get("is_constructor")]

    # FR-14: TypeScript — split non-constructor methods into property-kind vs callable methods
    ts_property_members = [m for m in non_constructor_methods if m.get("kind") == "property"]
    regular_methods = [m for m in non_constructor_methods if m.get("kind") != "property"]

    lines = []

    # Frontmatter
    lines.append("---")
    lines.append(f"linkTitle: {name}")
    lines.append(f"title: {name}")
    lines.append(f"description: \"{desc}\"")
    lines.append(f"summary: \"{desc}\"")
    lines.append("categories:")
    lines.append(f"- {category}")
    lines.append("layout: reference-single")
    lines.append("evidence:")
    lines.append(f"  model_sha: {MODEL_SHA}")
    lines.append("  model_version: '0.1.0'")
    lines.append("  claims: []")
    api_list = []
    for m in regular_methods:
        api_list.append(f"{name}.{m['name']}")
    for p in properties:
        api_list.append(f"{name}.{p['name']}")
    if api_list:
        lines.append("  apis:")
        for api in api_list[:10]:  # cap at 10
            lines.append(f"  - \"{api}\"")
    else:
        lines.append("  apis: []")
    lines.append("---")
    lines.append("")

    # Overview
    lines.append("## Overview")
    lines.append("")
    base_str = ", ".join(bases) if bases else ""

    # FR-15: emit import/package line using per-class class_import when available
    if class_import:
        lines.append(f"Import: `{class_import}`")
        lines.append("")

    # FR-15: emit C++ namespace label using per-class canonical_namespace when available
    if canonical_namespace:
        lines.append(f"**Namespace**: {canonical_namespace}")
        lines.append("")

    if doc:
        lines.append(doc.strip())
        lines.append("")

    if is_enum(cls):
        if base_str:
            lines.append(f"`{name}` is an enum in the target library (base type: `{base_str}`).")
        else:
            lines.append(f"`{name}` is an enum in the target library.")
    else:
        if base_str:
            lines.append(f"`{name}` is a class in the target library.  ")
            lines.append(f"Inherits from: `{base_str}`.")
        else:
            lines.append(f"`{name}` is a class in the target library.")

    lines.append("")

    # Enum values
    if enum_values:
        lines.append("## Members")
        lines.append("")
        lines.append("| Name | Description |")
        lines.append("|------|-------------|")
        for ev in enum_values:
            ev_name = ev["name"] if isinstance(ev, dict) else ev
            ev_doc = ev.get("doc", "") if isinstance(ev, dict) else ""
            lines.append(f"| `{ev_name}` | {ev_doc} |")
        lines.append("")

    # Constructors
    if constructors:
        lines.append("## Constructors")
        lines.append("")
        lines.append("| Signature | Description |")
        lines.append("|-----------|-------------|")
        for c in constructors:
            sig = format_method_signature(c)
            cdoc = c.get("doc", "").strip()
            if not cdoc:
                params = c.get("params", [])
                if not params:
                    cdoc = f"Creates a new `{name}` instance."
                else:
                    cdoc = f"Creates a new `{name}` with the specified parameters."
            lines.append(f"| `{sig}` | {cdoc} |")
        lines.append("")

    # Methods
    if regular_methods:
        lines.append("## Methods")
        lines.append("")
        lines.append("| Signature | Description |")
        lines.append("|-----------|-------------|")
        for m in regular_methods:
            sig = format_method_signature(m)
            mdoc = m.get("doc", "").strip()
            # FR-16: stub callout — prepend indicator in description cell
            if m.get("stub"):
                stub_note = "> **Not implemented**: This method raises NotImplementedException in the current release.  "
                mdoc = f"{stub_note}{mdoc}" if mdoc else stub_note.strip()
            lines.append(f"| `{sig}` | {mdoc} |")
        lines.append("")

    # Properties (including FR-14: TypeScript property-kind members promoted from methods list)
    all_properties = list(properties)
    for m in ts_property_members:
        # Represent TS property-kind members as property dicts
        all_properties.append({
            "name": m["name"],
            "type": m.get("return_type", m.get("type", "")),
            "doc": m.get("doc", ""),
            "access_mode": m.get("access_mode", ""),
            "has_setter": m.get("has_setter", False),
        })

    if all_properties:
        lines.append("## Properties")
        lines.append("")
        lines.append("| Name | Type | Access | Description |")
        lines.append("|------|------|--------|-------------|")
        for p in all_properties:
            pname = p["name"]
            ptype = p.get("type", "")
            pdoc = p.get("doc", "").strip()
            access = format_property_access(p)
            lines.append(f"| `{pname}` | `{ptype}` | {access} | {pdoc} |")
        lines.append("")

    # See Also — link to related classes in same namespace
    file_path = cls.get("file", "")
    namespace = ""
    if "/Cfb/" in file_path:
        namespace = "Cfb"
    elif "/Msg/" in file_path:
        namespace = "Msg"

    lines.append("## See Also")
    lines.append("")

    return "\n".join(lines)


def main():
    if not SURFACE_PATH.exists():
        print(f"ERROR: {SURFACE_PATH} not found", file=sys.stderr)
        sys.exit(1)

    with open(SURFACE_PATH) as f:
        raw_classes = json.load(f)

    merged = merge_partial_classes(raw_classes)
    print(f"Loaded {len(raw_classes)} entries, merged to {len(merged)} unique classes")

    # Also parse api_surface.md to get enum values (not in JSON for some classes)
    enum_values_from_md = parse_enum_values_from_md()

    for cls_name, cls_data in sorted(merged.items()):
        # Supplement enum values from api_surface.md if JSON is empty
        if not cls_data["enum_values"] and cls_name in enum_values_from_md:
            cls_data["enum_values"] = [
                {"name": v, "doc": ""} for v in enum_values_from_md[cls_name]
            ]

        slug = pascal_to_kebab(cls_name)
        out_path = OUTPUT_DIR / f"{slug}.md"

        content = generate_page(cls_data)
        out_path.write_text(content, encoding="utf-8")
        n_methods = len([m for m in cls_data["methods"] if not m.get("is_constructor")])
        n_props = len(cls_data["properties"])
        n_enum = len(cls_data["enum_values"])
        print(f"  {slug}.md — {n_methods} methods, {n_props} props, {n_enum} enum values")

    print(f"\nRegenerated {len(merged)} reference pages in {OUTPUT_DIR}")


def parse_enum_values_from_md() -> dict[str, list[str]]:
    """Parse enum values from api_surface.md since JSON doesn't always have them."""
    result: dict[str, list[str]] = {}
    if not SURFACE_MD.exists():
        return result

    current_class = None
    in_enum_section = False
    text = SURFACE_MD.read_text(encoding="utf-8")

    for line in text.splitlines():
        if line.startswith("## "):
            current_class = line[3:].strip()
            in_enum_section = False
        elif line.startswith("**Enum values**"):
            in_enum_section = True
        elif line.startswith("**") and not line.startswith("**Enum"):
            in_enum_section = False
        elif in_enum_section and line.startswith("- `"):
            val = line.split("`")[1]
            if current_class:
                result.setdefault(current_class, []).append(val)

    return result


if __name__ == "__main__":
    main()
