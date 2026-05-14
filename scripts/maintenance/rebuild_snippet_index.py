#!/usr/bin/env python3
"""Rebuild snippets_index.json from existing scout snippet files."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

SNIPPET_RE = re.compile(r"^snippet_(\d+)(?:_(.+))?$")


def load_api_surface(knowledge_root: Path, family: str, platform: str) -> list[dict[str, Any]]:
    for path in (
        knowledge_root / family / platform / "merged" / "api_surface.json",
        knowledge_root / family / platform / "scout" / "api_surface.json",
    ):
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return data if isinstance(data, list) else []
            except json.JSONDecodeError:
                return []
    return []


def build_lookup(api_surface: list[dict[str, Any]]) -> tuple[set[str], dict[str, set[str]]]:
    classes: set[str] = set()
    methods: dict[str, set[str]] = {}
    for item in api_surface:
        name = str(item.get("name", ""))
        if not name or name.startswith("_") or item.get("kind") == "function":
            continue
        classes.add(name)
        method_names = set()
        for key in ("methods", "method_details"):
            for method in item.get(key, []) or []:
                if isinstance(method, dict) and method.get("name"):
                    method_names.add(str(method["name"]))
        methods[name] = method_names
    return classes, methods


def build_entry(index: int, path: Path, class_names: set[str], method_index: dict[str, set[str]]) -> dict[str, Any]:
    match = SNIPPET_RE.match(path.stem)
    raw_name = match.group(2) if match else path.stem
    source_function = "(readme_block)" if str(raw_name).upper() == "README" else (raw_name or "")
    code = path.read_text(encoding="utf-8", errors="replace")
    classes_used = sorted(name for name in class_names if name in code)
    methods_used = sorted(
        f"{class_name}.{method}"
        for class_name in classes_used
        for method in method_index.get(class_name, set())
        if f"{class_name}.{method}" in code or f".{method}(" in code
    )
    return {
        "id": f"snippet_{index + 1:03d}",
        "file": path.name,
        "source_file": "",
        "source_function": source_function,
        "source_line": 0,
        "classes_used": classes_used,
        "methods_used": methods_used,
        "formats_referenced": [],
    }


def rebuild(knowledge_root: Path, family: str, platform: str, *, force: bool = False) -> int:
    snippets = knowledge_root / family / platform / "scout" / "snippets"
    if not snippets.is_dir():
        return 0
    index_path = snippets / "snippets_index.json"
    if index_path.exists() and not force:
        existing = json.loads(index_path.read_text(encoding="utf-8"))
        return len(existing) if isinstance(existing, list) else 0
    class_names, method_index = build_lookup(load_api_surface(knowledge_root, family, platform))
    files = sorted(path for path in snippets.glob("*.py") if path.name != "snippets_index.json")
    entries = [build_entry(index, path, class_names, method_index) for index, path in enumerate(files)]
    index_path.write_text(json.dumps(entries, indent=2, sort_keys=True), encoding="utf-8")
    return len(entries)


def discover_products(knowledge_root: Path) -> list[tuple[str, str]]:
    products: list[tuple[str, str]] = []
    if not knowledge_root.exists():
        return products
    for family in sorted(path for path in knowledge_root.iterdir() if path.is_dir() and not path.name.startswith("_")):
        for platform in sorted(path for path in family.iterdir() if path.is_dir()):
            snippets = platform / "scout" / "snippets"
            if snippets.exists() and list(snippets.glob("*.py")) and not (snippets / "snippets_index.json").exists():
                products.append((family.name, platform.name))
    return products


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("family")
    parser.add_argument("platform", nargs="?")
    parser.add_argument("--knowledge-root", type=Path, default=Path("knowledge"))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    if args.family == "all":
        total = sum(rebuild(args.knowledge_root, family, platform, force=args.force) for family, platform in discover_products(args.knowledge_root))
    else:
        if not args.platform:
            parser.error("platform is required unless family is 'all'")
        total = rebuild(args.knowledge_root, args.family, args.platform, force=args.force)
    print(f"REBUILD-SNIPPET-INDEX: DONE ({total} entries)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
