"""Rebuild snippets_index.json from orphaned snippet files in scout/snippets/.

When a scout run writes snippet files but crashes or is interrupted before writing
snippets_index.json, merge.py cannot detect or promote those snippets (it gates on
the index file's existence). This script reconstructs the index from the files on
disk without requiring the FOSS repos to be cloned again.

Snippet files must follow the naming convention:
  snippet_NNNN_<source_function>.py  (e.g. snippet_0022_test_multiple_meshes_export.py)
  snippet_NNNN_README.py             (README code block extracts)
  snippet_NNNN_<any_name>.py

Cross-referencing uses api_surface.json from merged/ (preferred) or scout/ as fallback.

Usage:
    python scripts/maintenance/rebuild_snippet_index.py 3d python
    python scripts/maintenance/rebuild_snippet_index.py cells python
    python scripts/maintenance/rebuild_snippet_index.py all
"""
import json
import re
import sys
from pathlib import Path

KNOWLEDGE_ROOT = Path("knowledge")

# Same criteria as _is_public_api_entry in index.py — must stay in sync.
_TEST_PATH_PATTERNS = ("tests/", "/tests/", "/test_", "test_", "conftest")
_INTERNAL_PATH_PATTERNS = ("/_internal/", "/_private/", "/_impl/")

# Regex to parse snippet filenames:
#   snippet_0022_test_multiple_meshes_export.py  → fn_name = "test_multiple_meshes_export"
#   snippet_0032_README.py                       → fn_name = "(readme_block)"
#   snippet_0001.py  (old format, no fn name)    → fn_name = ""
_SNIPPET_RE = re.compile(r"^snippet_(\d+)(?:_(.+))?$")


def _load_api_surface(family, platform):
    """Load api_surface.json, preferring merged/ over scout/."""
    merged_path = KNOWLEDGE_ROOT / family / platform / "merged" / "api_surface.json"
    scout_path = KNOWLEDGE_ROOT / family / platform / "scout" / "api_surface.json"
    for path in (merged_path, scout_path):
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
    return []


def _build_lookup(api_list):
    """Build class → set-of-methods lookup from api_surface list.

    Only public API entries are included — free functions, private names,
    test-file classes, and internal implementation classes are excluded so
    that snippets_index.json classes_used lists are clean.
    """
    class_names = set()
    method_index = {}  # class_name → set of method names
    for cls in api_list:
        if not isinstance(cls, dict):
            continue
        if cls.get("kind") == "function":
            continue
        name = cls.get("name", "")
        if not name or name.startswith("_"):
            continue
        file = cls.get("file", "")
        if any(pat in file for pat in _TEST_PATH_PATTERNS):
            continue
        if any(pat in file for pat in _INTERNAL_PATH_PATTERNS):
            continue
        class_names.add(name)
        meths = set()
        for m in cls.get("methods", []):
            if isinstance(m, dict) and m.get("name"):
                meths.add(m["name"])
        method_index[name] = meths
    return class_names, method_index


def _build_entry(idx, filepath, class_names, method_index):
    """Build one snippets_index entry from a single snippet file."""
    stem = filepath.stem  # e.g. "snippet_0022_test_multiple_meshes_export"
    m = _SNIPPET_RE.match(stem)
    if m:
        raw_name = m.group(2) or ""
        if raw_name.upper() == "README":
            source_function = "(readme_block)"
        else:
            source_function = raw_name
    else:
        source_function = stem

    try:
        code = filepath.read_text(encoding="utf-8", errors="replace")
    except OSError:
        code = ""

    # Cross-reference: which API classes appear in the code?
    classes_used = []
    methods_used = []
    for cname in class_names:
        if cname in code:
            classes_used.append(cname)
            for mname in method_index.get(cname, set()):
                if f"{cname}.{mname}" in code or f".{mname}(" in code:
                    methods_used.append(f"{cname}.{mname}")

    return {
        "id": f"snippet_{idx + 1:03d}",
        "file": filepath.name,
        "source_file": "",
        "source_function": source_function,
        "source_line": 0,
        "classes_used": sorted(set(classes_used)),
        "methods_used": sorted(set(methods_used)),
        "formats_referenced": [],
    }


def rebuild(family, platform):
    """Rebuild snippets_index.json for one family/platform."""
    scout_snip = KNOWLEDGE_ROOT / family / platform / "scout" / "snippets"

    if not scout_snip.is_dir():
        print(f"  SKIP {family}/{platform}: scout/snippets/ does not exist")
        return 0

    index_path = scout_snip / "snippets_index.json"
    if index_path.exists():
        existing = json.loads(index_path.read_text(encoding="utf-8"))
        print(f"  SKIP {family}/{platform}: snippets_index.json already exists "
              f"({len(existing)} entries) — delete it first to rebuild")
        return len(existing)

    api_list = _load_api_surface(family, platform)
    if not api_list:
        print(f"  WARN {family}/{platform}: no api_surface.json found; "
              f"classes_used and methods_used will be empty")
    class_names, method_index = _build_lookup(api_list)

    snippet_files = sorted(
        f for f in scout_snip.iterdir()
        if f.suffix == ".py" and f.name != "snippets_index.json"
    )

    if not snippet_files:
        print(f"  SKIP {family}/{platform}: no .py files in scout/snippets/")
        return 0

    entries = [
        _build_entry(idx, fp, class_names, method_index)
        for idx, fp in enumerate(snippet_files)
    ]

    index_path.write_text(json.dumps(entries, indent=2, ensure_ascii=False),
                          encoding="utf-8")

    classes_covered = set(c for e in entries for c in e["classes_used"])
    empty_count = sum(1 for e in entries if not e["classes_used"])
    print(f"  {family}/{platform}: wrote {len(entries)} entries, "
          f"{len(classes_covered)} classes covered")
    if empty_count:
        print(f"  WARN: {empty_count} entries have empty classes_used "
              f"(snippet files may not use any API classes, or api_surface.json was unavailable)")
    return len(entries)


def discover_products():
    """Find all family/platform combinations with orphaned scout snippets (no index)."""
    products = []
    if not KNOWLEDGE_ROOT.exists():
        return products
    for family_dir in sorted(KNOWLEDGE_ROOT.iterdir()):
        if not family_dir.is_dir() or family_dir.name.startswith("_"):
            continue
        for platform_dir in sorted(family_dir.iterdir()):
            if not platform_dir.is_dir():
                continue
            snip_dir = platform_dir / "scout" / "snippets"
            if not snip_dir.is_dir():
                continue
            index_file = snip_dir / "snippets_index.json"
            py_files = list(snip_dir.glob("*.py"))
            if py_files and not index_file.exists():
                products.append((family_dir.name, platform_dir.name))
    return products


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python scripts/maintenance/rebuild_snippet_index.py {family} {platform}")
        print("  python scripts/maintenance/rebuild_snippet_index.py all")
        sys.exit(1)

    if sys.argv[1] == "all":
        products = discover_products()
        if not products:
            print("No products with orphaned snippets found.")
            return
        print(f"Found {len(products)} product(s) with orphaned snippets:")
        for family, platform in products:
            rebuild(family, platform)
    else:
        if len(sys.argv) < 3:
            print("Usage: python scripts/maintenance/rebuild_snippet_index.py {family} {platform}")
            sys.exit(1)
        rebuild(sys.argv[1], sys.argv[2])

    print("REBUILD-SNIPPET-INDEX: DONE")


if __name__ == "__main__":
    main()
