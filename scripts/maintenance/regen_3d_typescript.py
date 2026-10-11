#!/usr/bin/env python3
"""Regenerate 3d/typescript reference pages from api_surface.json.

Fixes the TypeScript property-as-method rendering bug introduced before
FR-14 was applied: getter/setter accessors are now tagged kind:property
and rendered in a Properties table without () in the name column.
"""
from __future__ import annotations
import json
import yaml
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SURFACE_PATH = REPO_ROOT / "knowledge/3d/typescript/merged/api_surface.json"
OUTPUT_DIR = REPO_ROOT / "content/reference.aspose.org/en/3d/typescript"
MODEL_SHA = "227894a1120c22b9b6522564e23dc1d14c8fc39a"
MODEL_VERSION = "24.12.0"


def parse_frontmatter(content: str):
    if not content.startswith("---"):
        return {}, content
    end = content.find("\n---\n", 3)
    if end == -1:
        return {}, content
    fm_str = content[3:end]
    body = content[end + 4:]
    try:
        fm = yaml.safe_load(fm_str) or {}
    except Exception:
        fm = {}
    return fm, body


def classify(cls: dict) -> str:
    kind = cls.get("kind", "")
    if "enum" in kind:
        return "Enum"
    if "interface" in kind:
        return "Interface"
    return "Class"


def format_params(params: list) -> str:
    parts = []
    for p in params:
        name = p.get("name", "")
        ptype = p.get("type", "")
        optional = p.get("optional", False)
        if name and ptype:
            suffix = "?" if optional else ""
            parts.append(f"{name}{suffix}: {ptype}")
        elif name:
            parts.append(name)
    return ", ".join(parts)


def esc(s: str) -> str:
    return str(s).replace("|", r"\|")


def generate_body(cls: dict) -> str:
    name = cls["name"]
    category = classify(cls)
    bases = cls.get("bases", [])
    methods = cls.get("methods", [])
    properties = cls.get("properties", [])
    enum_values = cls.get("enum_values", [])
    doc = cls.get("doc", "").strip()

    constructors = [m for m in methods if m.get("is_constructor")]
    regular_methods = [m for m in methods if not m.get("is_constructor")]

    lines = ["## Overview", ""]
    if doc:
        lines.append(doc)
        lines.append("")
    else:
        if category == "Enum":
            lines.append(f"`{name}` is an enum in Aspose.3D FOSS for TypeScript.")
        else:
            bases_clean = [b for b in bases if b != name]
            if bases_clean:
                bases_str = ", ".join(f"`{b}`" for b in bases_clean)
                lines.append(
                    f"`{name}` is a {category.lower()} in Aspose.3D FOSS for TypeScript."
                    f" Inherits from: {bases_str}."
                )
            else:
                lines.append(
                    f"`{name}` is a {category.lower()} in Aspose.3D FOSS for TypeScript."
                )
    lines.append("")
    lines.append("**Package**: `@aspose/3d`")
    lines.append("")
    lines.append("---")
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
            lines.append(f"| `{ev_name}` | {esc(ev_doc)} |")
        lines.append("")

    # Constructors
    if constructors:
        lines.append("## Constructors")
        lines.append("")
        lines.append("| Signature | Description |")
        lines.append("|-----------|-------------|")
        for c in constructors:
            params = format_params(c.get("params", []))
            sig = f"{name}({params})"
            cdoc = c.get("doc", "").strip() or f"Creates a new `{name}` instance."
            lines.append(f"| `{sig}` | {esc(cdoc)} |")
        lines.append("")

    # Methods
    if regular_methods:
        lines.append("## Methods")
        lines.append("")
        lines.append("| Method | Returns | Description |")
        lines.append("|--------|---------|-------------|")
        for m in regular_methods:
            mname = m["name"]
            params = format_params(m.get("params", []))
            ret = m.get("return_type", "") or "void"
            mdoc = m.get("doc", "").strip()
            lines.append(f"| `{mname}({params})` | `{esc(ret)}` | {esc(mdoc)} |")
        lines.append("")

    # Properties
    if properties:
        lines.append("## Properties")
        lines.append("")
        lines.append("| Name | Type | Access | Description |")
        lines.append("|------|------|--------|-------------|")
        for p in properties:
            pname = p["name"]
            ptype = p.get("type", "") or ""
            pdoc = p.get("doc", "").strip()
            access_mode = p.get("access_mode", "")
            if access_mode == "readwrite":
                access = "read/write"
            elif access_mode == "readonly":
                access = "read"
            elif access_mode == "writeonly":
                access = "write"
            else:
                access = "read/write" if p.get("has_setter") else "read"
            lines.append(f"| `{pname}` | `{esc(ptype)}` | {access} | {esc(pdoc)} |")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## See Also")
    lines.append("")
    lines.append("- [Aspose.3D FOSS TypeScript API Reference home](/3d/typescript/)")
    lines.append("")

    return "\n".join(lines)


def build_frontmatter(cls: dict, existing_fm: dict) -> dict:
    name = cls["name"]
    category = classify(cls)
    doc = cls.get("doc", "").strip()
    methods = [m for m in cls.get("methods", []) if not m.get("is_constructor")]
    properties = cls.get("properties", [])

    if doc:
        desc = doc.rstrip(".")[:200]
    elif category == "Enum":
        desc = f"{name} enum in the Aspose.3D FOSS TypeScript API."
    else:
        n_m = len(methods)
        n_p = len(properties)
        parts = []
        if n_m:
            parts.append(f'{n_m} method{"s" if n_m > 1 else ""}')
        if n_p:
            parts.append(f'{n_p} propert{"ies" if n_p > 1 else "y"}')
        member_str = " and ".join(parts) if parts else "no public members"
        desc = f"{name} {category.lower()} in Aspose.3D FOSS TypeScript with {member_str}."

    api_list = [f"{name}.{m['name']}" for m in methods[:5]]
    api_list += [f"{name}.{p['name']}" for p in properties[:5]]
    api_list = api_list[:10]

    fm: dict = {
        "linkTitle": name,
        "title": f"{name} — Aspose.3D FOSS TypeScript API Reference",
        "description": desc,
        "summary": desc,
        "categories": [category],
        "layout": "single",
        "evidence": {
            "model_sha": MODEL_SHA,
            "model_version": MODEL_VERSION,
            "claims": [],
            "apis": api_list,
        },
    }

    # Preserve grade/graded/provenance fields
    for key in (
        "grade",
        "graded_at",
        "graded_model_sha",
        "graded_evaluators",
        "graded_logic_version",
        "provenance",
    ):
        if key in existing_fm:
            fm[key] = existing_fm[key]

    return fm


def main():
    with open(SURFACE_PATH) as f:
        raw_data = json.load(f)

    classes_raw = raw_data if isinstance(raw_data, list) else raw_data.get("classes", [])

    # Filter to real classes/interfaces/enums (PascalCase names)
    real_classes = {
        cls["name"]: cls
        for cls in classes_raw
        if cls.get("kind")
        in (
            "class_declaration",
            "interface_declaration",
            "enum_declaration",
            "abstract_class_declaration",
        )
        and cls["name"][0].isupper()
    }

    # Map class names to existing files (case-insensitive)
    existing_files = {
        f.stem.lower(): f for f in OUTPUT_DIR.glob("*.md") if f.stem != "_index"
    }
    class_to_file: dict[str, Path] = {}
    for name in real_classes:
        key = name.lower()
        if key in existing_files:
            class_to_file[name] = existing_files[key]

    print(f"Real classes: {len(real_classes)}, Mapped to files: {len(class_to_file)}")

    updated = 0
    unchanged = 0
    errors = []

    for cls_name in sorted(class_to_file.keys()):
        file_path = class_to_file[cls_name]
        try:
            existing_content = file_path.read_text(encoding="utf-8")
            existing_fm, _ = parse_frontmatter(existing_content)

            cls = real_classes[cls_name]
            new_fm = build_frontmatter(cls, existing_fm)
            new_body = generate_body(cls)

            fm_str = yaml.dump(
                new_fm, default_flow_style=False, allow_unicode=True, sort_keys=False
            )
            new_content = f"---\n{fm_str}---\n\n{new_body}"

            if new_content != existing_content:
                file_path.write_text(new_content, encoding="utf-8")
                n_props = len(cls.get("properties", []))
                n_methods = len([m for m in cls.get("methods", []) if not m.get("is_constructor")])
                print(f"  {cls_name}: {n_methods} methods, {n_props} props")
                updated += 1
            else:
                unchanged += 1
        except Exception as e:
            errors.append((cls_name, str(e)))
            print(f"  ERROR: {cls_name}: {e}")

    print(f"\nUpdated: {updated}, Unchanged: {unchanged}, Errors: {len(errors)}")
    if errors:
        for name, err in errors:
            print(f"  ERROR: {name}: {err}")


if __name__ == "__main__":
    main()
