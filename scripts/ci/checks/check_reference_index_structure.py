#!/usr/bin/env python3
"""
Reference index structure validator for reference.aspose.org.

Checks two failure modes:

1. **Flat index** -- a ``{{< children >}}`` shortcode is the only body content
   while a sufficiently large api_surface.json exists (original check).

2. **Stale grouped index** -- a page has grouped tables but the visible row
   count is suspiciously low (<10 %) compared to the filtered API entry count
   from api_surface.json.  This catches pages where knowledge was refreshed
   but the grouped index was never regenerated.  Manually-curated pages
   (last_mechanism: manual-edit-skill | human-edit | agent-edit) are skipped.

Exit code: 0 if clean, 1 if warnings found, 2 if setup error.

Usage:
    python scripts/ci/checks/check_reference_index_structure.py [--staleness]

Options:
    --staleness   Also run the stale-grouped-index check (default: off in CI
                  until threshold is tuned; always runs as advisory).
"""
import json
import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_REF_CONTENT = _REPO_ROOT / "content" / "reference.aspose.org" / "en"
_KNOWLEDGE_ROOT = _REPO_ROOT / "knowledge"
_MIN_API_ENTRIES = 5
_STALENESS_THRESHOLD = 0.10  # flag if index rows < 10 % of filtered API count

# ---------------------------------------------------------------------------
# Shared filter (TC-REF-09) — imported when available, inlined as fallback
# ---------------------------------------------------------------------------
try:
    import sys as _sys
    _sys.path.insert(0, str(_REPO_ROOT / "scripts" / "pipeline"))
    from lib.reference_filter import filtered_count as _filtered_count
    from lib.reference_filter import count_index_table_rows as _count_rows
    _HAS_SHARED_FILTER = True
except ImportError:
    _HAS_SHARED_FILTER = False

    # --- inline fallback (kept in sync with reference_filter.py) ---
    _ENUM_KINDS: frozenset = frozenset({"enum_specifier", "enum_declaration", "enum_definition"})
    _CLASS_KINDS_BY_PLATFORM: dict = {
        "java":       {"class_declaration", "interface_declaration"},
        "net":        {"class_declaration", "interface_declaration",
                       "struct_declaration", "record_declaration"},
        "cpp":        {"class_specifier", "struct_specifier"},
        "python":     {"class_definition"},
        "typescript": {"class_declaration", "interface_declaration",
                       "type_alias_declaration"},
        "go":         {"type_spec"},
    }
    _INTERNAL_MARKERS = ("/internal/", "\\internal\\", "/_internal/", "\\_internal\\")

    def _passes_scope(entry: dict, platform: str) -> bool:
        kind = entry.get("kind", "")
        name = entry.get("name", "")
        f = entry.get("file", "")
        if any(m in f for m in _INTERNAL_MARKERS):
            return False
        if name.startswith("_"):
            return False
        ck = _CLASS_KINDS_BY_PLATFORM.get(platform, set())
        return kind in ck or kind in _ENUM_KINDS

    def _filtered_count(api: list, platform: str) -> int:  # type: ignore[misc]
        return sum(1 for e in api
                   if _passes_scope(e, platform)
                   and e.get("visibility", "public") != "internal")

    def _count_rows(text: str) -> int:  # type: ignore[misc]
        body = text
        if text.startswith("---"):
            end = text.find("---", 3)
            if end != -1:
                body = text[end + 3:]
        return sum(
            1 for l in body.splitlines()
            if l.strip().startswith("|") and "---" not in l and l.count("|") >= 2
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_body(text: str) -> str:
    """Return markdown body after YAML frontmatter."""
    if text.startswith("---"):
        end = text.find("---", 3)
        if end != -1:
            return text[end + 3:].strip()
    return text.strip()


def _is_flat(body: str) -> bool:
    """Return True if the body is essentially just {{< children >}}."""
    stripped = re.sub(r"##\s*See Also.*", "", body, flags=re.DOTALL).strip()
    lines = [line.strip() for line in stripped.splitlines() if line.strip()]
    has_h2 = any(line.startswith("## ") for line in lines)
    has_table = any(line.startswith("|") for line in lines)
    if has_h2 and has_table:
        return False  # Has grouped content
    return "{{< children" in stripped


def _is_manually_curated(text: str) -> bool:
    """Check if the page was manually curated (should not be auto-healed)."""
    return bool(re.search(
        r"last_mechanism:\s*(manual-edit-skill|human-edit|agent-edit)", text
    ))


# ---------------------------------------------------------------------------
# Main validator
# ---------------------------------------------------------------------------

def run(check_staleness: bool = True) -> int:
    """Run the validator. Returns exit code."""
    if not _REF_CONTENT.is_dir():
        print(f"ERROR: Reference content root not found: {_REF_CONTENT}",
              file=sys.stderr)
        return 2

    flat_warnings: list[dict] = []
    stale_warnings: list[dict] = []
    checked = 0

    for family_dir in sorted(_REF_CONTENT.iterdir()):
        if not family_dir.is_dir():
            continue
        family = family_dir.name
        for plat_dir in sorted(family_dir.iterdir()):
            if not plat_dir.is_dir():
                continue
            platform = plat_dir.name
            index_path = plat_dir / "_index.md"
            if not index_path.exists():
                continue

            checked += 1
            text = index_path.read_text(encoding="utf-8")
            body = _extract_body(text)

            api_path = _KNOWLEDGE_ROOT / family / platform / "merged" / "api_surface.json"

            # --- Check 1: flat index ---
            if _is_flat(body) and not _is_manually_curated(text):
                if api_path.exists():
                    try:
                        api = json.loads(api_path.read_text(encoding="utf-8"))
                    except Exception:
                        api = []
                    if len(api) >= _MIN_API_ENTRIES:
                        flat_warnings.append({
                            "family": family,
                            "platform": platform,
                            "path": str(index_path.relative_to(_REPO_ROOT)),
                            "api_count": len(api),
                        })
                continue  # no point checking staleness on a flat page

            # --- Check 2: stale grouped index (advisory) ---
            if check_staleness and not _is_flat(body) and not _is_manually_curated(text):
                if api_path.exists():
                    try:
                        api = json.loads(api_path.read_text(encoding="utf-8"))
                    except Exception:
                        api = []
                    if len(api) >= _MIN_API_ENTRIES:
                        fc = _filtered_count(api, platform)
                        rows = _count_rows(text)
                        if fc > 0 and rows / fc < _STALENESS_THRESHOLD:
                            stale_warnings.append({
                                "family": family,
                                "platform": platform,
                                "path": str(index_path.relative_to(_REPO_ROOT)),
                                "index_rows": rows,
                                "filtered_api": fc,
                                "ratio": round(rows / fc, 3),
                            })

    # --- Report ---
    exit_code = 0

    if flat_warnings:
        print(f"WARN: {len(flat_warnings)} reference index page(s) use flat "
              f"{{{{< children >}}}} when grouped metadata is available:")
        print()
        for w in flat_warnings:
            print(f"  {w['family']}/{w['platform']}: "
                  f"{w['api_count']} API entries available")
            print(f"    Path:   {w['path']}")
            print(f"    Fix:    .venv/Scripts/python scripts/pipeline/commands/content/"
                  f"batch_reference.py {w['family']} {w['platform']} --generate-index")
            print()
        # Flat index in a product with >=5 API entries is a launch blocker.
        # Use exit code 2 (FAIL) so CI gates block the deploy.
        exit_code = 2

    if stale_warnings:
        print(f"ADVISORY: {len(stale_warnings)} grouped reference index page(s) may be "
              f"stale (index rows < {int(_STALENESS_THRESHOLD * 100)}% of filtered API):")
        print()
        for w in stale_warnings:
            pct = int(w["ratio"] * 100)
            print(f"  {w['family']}/{w['platform']}: "
                  f"{w['index_rows']} rows / {w['filtered_api']} filtered api = {pct}%")
            print(f"    Path:   {w['path']}")
            print(f"    Fix:    .venv/Scripts/python scripts/pipeline/commands/content/"
                  f"batch_reference.py {w['family']} {w['platform']} --generate-index")
            print()
        # Advisory only — does not change exit code

    filter_note = "(using shared reference_filter)" if _HAS_SHARED_FILTER else "(inline filter fallback)"
    print(f"OK: {checked} reference index pages checked {filter_note}.")
    if not flat_warnings and not stale_warnings:
        print("All pages have appropriate structure.")
    else:
        print(f"Flat: {len(flat_warnings)}  Stale (advisory): {len(stale_warnings)}")

    return exit_code


if __name__ == "__main__":
    staleness = "--staleness" in sys.argv or "--no-staleness" not in sys.argv
    sys.exit(run(check_staleness=staleness))
