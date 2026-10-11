"""
verify_pdf_net_reference.py
Manual verification script for pdf/net reference pages.

Inputs:
  - content/reference.aspose.org/en/pdf/net/*.md  (806 files)
  - knowledge/pdf/net/merged/api_surface.json     (805 entries)
  - runs/.clone_cache/aspose_pdf_net/             (clone root)

Outputs:
  - docs/audits/pdf-net-reference-page-inventory.csv   (806 rows)
  - docs/audits/pdf-net-reference-mismatch-report.csv  (DO-NOT-PUBLISH rows)
  - docs/audits/pdf-net-reference-source-truth-inventory.csv (source types)

Run from repo root:
  .venv/Scripts/python docs/audits/verify_pdf_net_reference.py
"""

import csv
import json
import os
import re
import sys
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# PATHS (all relative to repo root; script is run from repo root)
# ─────────────────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).parent.parent.parent
PAGES_DIR = REPO_ROOT / "content/reference.aspose.org/en/pdf/net"
API_SURFACE_JSON = REPO_ROOT / "knowledge/pdf/net/merged/api_surface.json"
CLONE_ROOT = REPO_ROOT / "runs/.clone_cache/aspose_pdf_net"
OUT_DIR = REPO_ROOT / "docs/audits"

INVENTORY_CSV = OUT_DIR / "pdf-net-reference-page-inventory.csv"
MISMATCH_CSV = OUT_DIR / "pdf-net-reference-mismatch-report.csv"
SOURCE_TRUTH_CSV = OUT_DIR / "pdf-net-reference-source-truth-inventory.csv"


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def parse_frontmatter(md_text: str) -> dict:
    """Return raw frontmatter dict from YAML block (very lightweight parser)."""
    lines = md_text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    end = None
    for i, ln in enumerate(lines[1:], 1):
        if ln.strip() == "---":
            end = i
            break
    if end is None:
        return {}
    fm_text = "\n".join(lines[1:end])
    # Use PyYAML if available; fall back to regex extraction
    try:
        import yaml
        return yaml.safe_load(fm_text) or {}
    except Exception:
        return {}


def extract_evidence(fm: dict) -> dict:
    """Pull evidence block from frontmatter."""
    return fm.get("evidence", {}) or {}


def get_categories(fm: dict) -> list:
    cats = fm.get("categories", []) or []
    if isinstance(cats, str):
        cats = [cats]
    return [c.lower() for c in cats]


def slug_from_path(p: Path) -> str:
    return p.stem  # filename without .md


def strip_disambiguation_suffix(slug: str) -> str:
    """Color-Pdf -> Color, Color-Drawing -> Color, Widget -> Widget."""
    # Known disambiguation suffixes are namespace segments
    # We'll try both the full slug and the de-suffixed version
    if "-" in slug:
        return slug.rsplit("-", 1)[0]
    return slug


# ─────────────────────────────────────────────────────────────────────────────
# LOAD API SURFACE
# ─────────────────────────────────────────────────────────────────────────────

def load_api_surface() -> dict:
    """
    Load api_surface.json and build two lookup dicts:
      by_name:  {name_lower -> [entry, ...]}           (may have multiple due to disambiguation)
      by_class_import: {class_import_lower -> entry}   (unique, fully qualified)
    """
    print(f"Loading api_surface from {API_SURFACE_JSON}...")
    with open(API_SURFACE_JSON, encoding="utf-8") as f:
        entries = json.load(f)
    print(f"  Loaded {len(entries)} entries.")

    by_name = {}
    by_name_exact = {}  # RC-002: original-case key to handle Id vs ID collision
    by_class_import = {}
    for e in entries:
        nm = (e.get("name") or "").lower()
        nm_orig = e.get("name") or ""
        ci = (e.get("class_import") or "").lower()
        by_name.setdefault(nm, []).append(e)
        by_name_exact.setdefault(nm_orig, []).append(e)
        if ci:
            by_class_import[ci] = e
    return {"entries": entries, "by_name": by_name, "by_name_exact": by_name_exact, "by_class_import": by_class_import}


# ─────────────────────────────────────────────────────────────────────────────
# SOURCE FILE VERIFICATION
# ─────────────────────────────────────────────────────────────────────────────

def verify_source_file(entry: dict) -> tuple[str, str, str]:
    """
    Returns (source_file_verified, source_type_exists, source_is_public)
    Each value: YES / NO / NA
    """
    file_rel = entry.get("file", "")
    if not file_rel:
        return "NO", "NO", "NO"

    abs_path = CLONE_ROOT / file_rel
    if not abs_path.exists():
        return "NO", "NO", "NO"

    # File exists
    file_verified = "YES"

    # Read the source file and look for the type declaration near the stated line
    try:
        src_lines = abs_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return file_verified, "NO", "NO"

    line_no = entry.get("line", 0)
    type_name = entry.get("name", "")
    kind = entry.get("kind", "")

    # Search a window around the stated line
    search_start = max(0, line_no - 5)
    search_end = min(len(src_lines), line_no + 10)
    window = "\n".join(src_lines[search_start:search_end])

    # Match type declaration
    # Accept: public class X, public sealed class X, public abstract class X,
    #         public interface X, public enum X, public struct X, public static class X
    type_kw_map = {
        "class_declaration": "class",
        "interface_declaration": "interface",
        "enum_declaration": "enum",
        "struct_declaration": "struct",
    }
    type_kw = type_kw_map.get(kind, "class")

    # Pattern: public [modifier*] type_kw TypeName
    escaped_name = re.escape(type_name)
    pattern = rf"public\s+(?:(?:sealed|abstract|static|partial|readonly)\s+)*{re.escape(type_kw)}\s+{escaped_name}\b"
    match = re.search(pattern, window)

    if match:
        return file_verified, "YES", "YES"  # The pattern already requires "public"

    # Fallback: just find the name in the window (weaker check)
    if type_name in window:
        # Check if it has a public modifier anywhere nearby
        pub_pattern = rf"public\b.*\b{escaped_name}\b"
        if re.search(pub_pattern, window):
            return file_verified, "YES", "YES"
        # Found the type but no public modifier visible in window
        return file_verified, "YES", "NO"

    # Search entire file for the type
    full_text = "\n".join(src_lines)
    if re.search(pattern, full_text):
        return file_verified, "YES", "YES"
    if type_name in full_text:
        return file_verified, "YES", "NO"

    return file_verified, "NO", "NO"


# ─────────────────────────────────────────────────────────────────────────────
# MEMBER COUNT VERIFICATION
# ─────────────────────────────────────────────────────────────────────────────

def count_table_rows(md_body: str, section_heading: str) -> int:
    """Count rows in a markdown table under the given section heading."""
    lines = md_body.splitlines()
    in_section = False
    count = 0
    heading_pattern = re.compile(rf"^##\s+{re.escape(section_heading)}", re.IGNORECASE)
    for line in lines:
        if heading_pattern.match(line):
            in_section = True
            continue
        if in_section:
            if line.startswith("##"):
                break  # next section
            stripped = line.strip()
            if stripped.startswith("|") and not stripped.startswith("| ---") and not stripped.startswith("|---") and "---" not in stripped:
                # Skip header row (first pipe row after heading)
                count += 1
    # Subtract 1 for the header row
    return max(0, count - 1)


def check_member_counts(md_text: str, entry: dict) -> tuple[str, str]:
    """
    Compare method/property counts in the page vs api_surface entry.
    Returns (method_count_match, property_count_match): YES/NO/NA
    """
    kind = entry.get("kind", "")
    if kind not in ("class_declaration", "interface_declaration", "struct_declaration"):
        return "NA", "NA"

    api_methods = len(entry.get("methods", []) or [])
    api_props = len(entry.get("properties", []) or [])

    page_methods = count_table_rows(md_text, "Methods")
    page_props = count_table_rows(md_text, "Properties")

    method_match = "YES" if page_methods == api_methods else f"NO(page={page_methods},api={api_methods})"
    prop_match = "YES" if page_props == api_props else f"NO(page={page_props},api={api_props})"

    return method_match, prop_match


# ─────────────────────────────────────────────────────────────────────────────
# SLUG MATCHING
# ─────────────────────────────────────────────────────────────────────────────

def find_api_entry(slug: str, api: dict) -> tuple[dict | None, str]:
    """
    Find the api_surface entry for a given page slug.
    Returns (entry, match_type) where match_type is:
      'exact', 'stripped', 'class_import', 'ambiguous', 'not_found'
    """
    by_name_exact = api["by_name_exact"]  # RC-002: exact-case lookup
    by_name = api["by_name"]

    # 1. Try exact-case match first (e.g. slug "Id" finds only Id, not ID)
    candidates = by_name_exact.get(slug, [])
    if len(candidates) == 1:
        return candidates[0], "exact_case"
    if len(candidates) > 1:
        return candidates[0], "ambiguous_exact"  # rare: two entries with identical case name

    # 2. Try case-insensitive match (original behaviour for non-colliding names)
    candidates = by_name.get(slug.lower(), [])
    if len(candidates) == 1:
        return candidates[0], "exact"
    if len(candidates) > 1:
        # Disambiguated slug — need namespace suffix to pick right one
        # e.g. Color-Pdf → name=Color, namespace_suffix=Pdf
        return candidates[0], "ambiguous"  # return first, flag as ambiguous

    # 2. Try stripped (remove disambiguation suffix)
    stripped = strip_disambiguation_suffix(slug)
    if stripped.lower() != slug.lower():
        candidates = by_name.get(stripped.lower(), [])
        if len(candidates) == 1:
            return candidates[0], "stripped"
        if len(candidates) > 1:
            # Multiple matches — use namespace suffix to disambiguate
            suffix = slug[len(stripped)+1:]  # e.g. "Pdf" from "Color-Pdf"
            for c in candidates:
                ns = c.get("canonical_namespace", "")
                if ns.split(".")[-1].lower() == suffix.lower():
                    return c, "stripped_exact"
            return candidates[0], "stripped_ambiguous"

    return None, "not_found"


# ─────────────────────────────────────────────────────────────────────────────
# CLASSIFY PAGE
# ─────────────────────────────────────────────────────────────────────────────

def classify_page(
    slug: str,
    fm: dict,
    md_text: str,
    entry: dict | None,
    match_type: str,
    sfv: str,
    ste: str,
    sip: str,
    method_match: str,
    prop_match: str,
) -> tuple[str, str, str]:
    """
    Returns (classification, publish_verdict, publish_reason).
    """
    if slug == "_index":
        return "INDEX_PAGE", "PUBLISH", "Structural index page — always publish"

    if match_type == "not_found":
        return "FABRICATED", "DO-NOT-PUBLISH", "No api_surface entry found for this slug"

    if sfv == "NO":
        return "FABRICATED", "DO-NOT-PUBLISH", f"Source file not found in clone cache: {entry.get('file', 'N/A')}"

    if ste == "NO":
        return "FABRICATED", "DO-NOT-PUBLISH", f"Type '{entry.get('name')}' not found in source file at expected line"

    if sip == "NO":
        return "INTERNAL_OR_NON_PUBLIC", "DO-NOT-PUBLISH", f"Type '{entry.get('name')}' found in source but not marked public"

    # Source verified and public — check for staleness
    stale_reasons = []
    if method_match not in ("YES", "NA") and "NO(" in method_match:
        stale_reasons.append(f"method count mismatch: {method_match}")
    if prop_match not in ("YES", "NA") and "NO(" in prop_match:
        stale_reasons.append(f"property count mismatch: {prop_match}")

    if stale_reasons:
        reason = f"Verified real but stale: {'; '.join(stale_reasons)}"
        return "VERIFIED_REAL_BUT_STALE", "PUBLISH", reason

    ns = entry.get("canonical_namespace", "unknown")
    kind = entry.get("kind", "unknown").replace("_declaration", "")
    return "VERIFIED_REAL", "PUBLISH", f"Verified public {kind} in {ns}"


# ─────────────────────────────────────────────────────────────────────────────
# SOURCE TRUTH EXTRACTION (basic)
# ─────────────────────────────────────────────────────────────────────────────

def extract_source_truth(api: dict) -> list[dict]:
    """
    Build source truth inventory from api_surface.json (which was derived from source).
    We verify each entry's source file exists and the type is public.
    Returns list of dicts for CSV output.
    """
    rows = []
    for entry in api["entries"]:
        sfv, ste, sip = verify_source_file(entry)
        rows.append({
            "name": entry.get("name", ""),
            "kind": entry.get("kind", "").replace("_declaration", ""),
            "namespace": entry.get("canonical_namespace", ""),
            "file_path": entry.get("file", ""),
            "line_number": entry.get("line", ""),
            "visibility": entry.get("visibility", ""),
            "method_count": len(entry.get("methods", []) or []),
            "property_count": len(entry.get("properties", []) or []),
            "source_file_verified": sfv,
            "source_type_exists": ste,
            "source_is_public": sip,
        })
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print("PDF/NET Reference Manual Verification")
    print("=" * 70)

    # Load api_surface
    api = load_api_surface()

    # Find all .md files
    md_files = sorted(PAGES_DIR.glob("*.md"))
    print(f"\nFound {len(md_files)} .md files in reference pages directory.")

    # ── BUG-05: Row count summary ────────────────────────────────────────────
    EXPECTED_ENTRIES = 805
    EXPECTED_PAGES = 806
    print(f"\nCount check:")
    print(f"  Expected: {EXPECTED_ENTRIES} api_surface entries, {EXPECTED_PAGES} pages")
    print(f"  Actual:   {len(api['entries'])} entries, {len(md_files)} pages")
    if len(api["entries"]) != EXPECTED_ENTRIES:
        print(f"  WARNING: api_surface entry count differs from expected ({len(api['entries'])} != {EXPECTED_ENTRIES})")
    if len(md_files) != EXPECTED_PAGES:
        print(f"  WARNING: page count differs from expected ({len(md_files)} != {EXPECTED_PAGES}) — expected if RC-001 was applied")

    # ── Phase 2: Page inventory ──────────────────────────────────────────────
    inventory_rows = []
    mismatch_rows = []

    counts = {
        "total": 0, "publish": 0, "do_not_publish": 0,
        "VERIFIED_REAL": 0, "VERIFIED_REAL_BUT_STALE": 0, "INDEX_PAGE": 0,
        "FABRICATED": 0, "INTERNAL_OR_NON_PUBLIC": 0, "DUPLICATE": 0,
        "UNKNOWN_NEEDS_MANUAL_REVIEW": 0, "TEMPLATE_FILLER": 0,
        "grade_A": 0, "grade_other": 0,
        "class_pages": 0, "enum_pages": 0, "interface_pages": 0,
        "struct_pages": 0, "index_pages": 0, "other_type": 0,
        "method_count_mismatches": 0, "prop_count_mismatches": 0,
    }

    # BUG-01: track covered class_imports for reverse mapping check
    covered_class_imports: set = set()
    # BUG-07: track seen slugs for duplicate detection
    seen_slugs: set = set()

    print(f"\nProcessing {len(md_files)} pages...")
    for i, md_path in enumerate(md_files, 1):
        if i % 100 == 0:
            print(f"  {i}/{len(md_files)} pages processed...")

        slug = slug_from_path(md_path)
        md_text = md_path.read_text(encoding="utf-8", errors="replace")
        fm = parse_frontmatter(md_text)
        ev = extract_evidence(fm)
        cats = get_categories(fm)
        grade = fm.get("grade", "")
        auto_updatable = fm.get("provenance", {}).get("auto_updatable", True) if fm.get("provenance") else True
        model_sha = ev.get("model_sha", "")
        apis_list = ev.get("apis", []) or []
        api_member_count = len(apis_list)

        # BUG-07: duplicate slug detection (before all other processing)
        if slug in seen_slugs:
            dup_row = {
                "path": str(md_path.relative_to(REPO_ROOT)).replace("\\", "/"),
                "slug": slug,
                "type_kind": "unknown",
                "namespace": "",
                "grade": grade,
                "auto_updatable": str(auto_updatable),
                "model_sha": model_sha,
                "api_member_count": api_member_count,
                "source_file_verified": "NA",
                "source_type_exists": "NA",
                "source_is_public": "NA",
                "method_count_match": "NA",
                "property_count_match": "NA",
                "classification": "DUPLICATE",
                "publish_verdict": "DO-NOT-PUBLISH",
                "publish_reason": f"Duplicate slug '{slug}' — same slug as a previously processed page",
            }
            inventory_rows.append(dup_row)
            mismatch_rows.append(dup_row)
            counts["total"] += 1
            counts["do_not_publish"] += 1
            counts["DUPLICATE"] = counts.get("DUPLICATE", 0) + 1
            continue
        seen_slugs.add(slug)

        # Determine type_kind from categories
        if "class" in cats:
            type_kind = "class"
            counts["class_pages"] += 1
        elif "enum" in cats:
            type_kind = "enum"
            counts["enum_pages"] += 1
        elif "interface" in cats:
            type_kind = "interface"
            counts["interface_pages"] += 1
        elif slug == "_index":
            type_kind = "index"
            counts["index_pages"] += 1
        else:
            # Check from description
            desc = fm.get("description", "")
            if "struct" in desc.lower() or "Struct" in str(cats):
                type_kind = "struct"
                counts["struct_pages"] += 1
            else:
                type_kind = "unknown"
                counts["other_type"] += 1

        # Grade counting
        if grade == "A":
            counts["grade_A"] += 1
        elif grade:
            counts["grade_other"] += 1

        # Find namespace from apis list or description
        namespace = ""
        if apis_list:
            # First entry is usually "ClassName" — try to get namespace from api_surface
            pass  # will be filled from entry lookup

        # Find api_surface entry
        entry, match_type = find_api_entry(slug, api)

        # BUG-01: track covered class_imports for reverse mapping check
        if entry is not None:
            covered_class_imports.add((entry.get("class_import") or "").lower())

        # BUG-04: derive type_kind from api_surface entry (more reliable than frontmatter heuristics)
        if entry is not None and slug != "_index":
            kind_raw = entry.get("kind", "")
            kind_map = {
                "class_declaration": "class",
                "enum_declaration": "enum",
                "interface_declaration": "interface",
                "struct_declaration": "struct",
            }
            entry_kind = kind_map.get(kind_raw, "")
            if entry_kind and entry_kind != type_kind:
                # Override frontmatter heuristic with api_surface fact
                # Adjust counts: undo the heuristic count, add the correct one
                if type_kind == "class":
                    counts["class_pages"] -= 1
                elif type_kind == "enum":
                    counts["enum_pages"] -= 1
                elif type_kind == "interface":
                    counts["interface_pages"] -= 1
                elif type_kind == "struct":
                    counts["struct_pages"] -= 1
                elif type_kind == "unknown":
                    counts["other_type"] -= 1
                type_kind = entry_kind
                if entry_kind == "class":
                    counts["class_pages"] += 1
                elif entry_kind == "enum":
                    counts["enum_pages"] += 1
                elif entry_kind == "interface":
                    counts["interface_pages"] += 1
                elif entry_kind == "struct":
                    counts["struct_pages"] += 1

        # Get namespace from entry
        if entry:
            namespace = entry.get("canonical_namespace", "")

        # Verify source
        if slug == "_index" or entry is None:
            sfv, ste, sip = "NA", "NA", "NA"
        else:
            sfv, ste, sip = verify_source_file(entry)

        # Check member counts
        if entry and slug != "_index":
            method_match, prop_match = check_member_counts(md_text, entry)
        else:
            method_match, prop_match = "NA", "NA"

        if "NO(" in method_match:
            counts["method_count_mismatches"] += 1
        if "NO(" in prop_match:
            counts["prop_count_mismatches"] += 1

        # Classify
        classification, verdict, reason = classify_page(
            slug, fm, md_text, entry, match_type, sfv, ste, sip, method_match, prop_match
        )

        counts["total"] += 1
        counts[verdict.replace("-", "_").lower()] = counts.get(verdict.replace("-", "_").lower(), 0) + 1
        counts[classification] = counts.get(classification, 0) + 1
        if verdict == "PUBLISH":
            counts["publish"] += 1
        else:
            counts["do_not_publish"] += 1

        row = {
            "path": str(md_path.relative_to(REPO_ROOT)).replace("\\", "/"),
            "slug": slug,
            "type_kind": type_kind,
            "namespace": namespace,
            "grade": grade,
            "auto_updatable": str(auto_updatable),
            "model_sha": model_sha,
            "api_member_count": api_member_count,
            "source_file_verified": sfv,
            "source_type_exists": ste,
            "source_is_public": sip,
            "method_count_match": method_match,
            "property_count_match": prop_match,
            "classification": classification,
            "publish_verdict": verdict,
            "publish_reason": reason,
        }
        inventory_rows.append(row)

        if verdict != "PUBLISH":
            mismatch_rows.append(row)

    # ── BUG-01: Reverse mapping — find api_surface entries with no page ───────
    print("\nChecking reverse mapping (api_surface -> pages)...")
    missing_pages = []
    for e in api["entries"]:
        ci = (e.get("class_import") or "").lower()
        if ci and ci not in covered_class_imports:
            missing_pages.append(e)
            print(f"  MISSING PAGE: {e.get('name')} ({e.get('canonical_namespace')}) — "
                  f"api_surface has this entry but no reference page found")
    counts["missing_pages"] = len(missing_pages)
    if not missing_pages:
        print("  All api_surface entries have corresponding reference pages.")

    # ── Write inventory CSV ──────────────────────────────────────────────────
    print(f"\nWriting inventory CSV ({len(inventory_rows)} rows)...")
    fieldnames = [
        "path", "slug", "type_kind", "namespace", "grade", "auto_updatable",
        "model_sha", "api_member_count", "source_file_verified", "source_type_exists",
        "source_is_public", "method_count_match", "property_count_match",
        "classification", "publish_verdict", "publish_reason",
    ]
    with open(INVENTORY_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(inventory_rows)
    print(f"  Written: {INVENTORY_CSV}")

    # ── Write mismatch CSV ───────────────────────────────────────────────────
    print(f"\nWriting mismatch CSV ({len(mismatch_rows)} rows)...")
    with open(MISMATCH_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(mismatch_rows)
    print(f"  Written: {MISMATCH_CSV}")

    # ── Phase 3: Source truth extraction ───────────────────────────────────
    print("\nExtracting source truth inventory...")
    source_rows = extract_source_truth(api)
    src_fieldnames = [
        "name", "kind", "namespace", "file_path", "line_number", "visibility",
        "method_count", "property_count", "source_file_verified", "source_type_exists", "source_is_public",
    ]
    with open(SOURCE_TRUTH_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=src_fieldnames)
        w.writeheader()
        w.writerows(source_rows)
    print(f"  Written: {SOURCE_TRUTH_CSV}")

    # ── Print summary ────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("VERIFICATION SUMMARY")
    print("=" * 70)
    print(f"Total pages processed:     {counts['total']}")
    print(f"  PUBLISH:                 {counts['publish']}")
    print(f"  DO-NOT-PUBLISH:          {counts['do_not_publish']}")
    print()
    print(f"Classification breakdown:")
    print(f"  VERIFIED_REAL:           {counts.get('VERIFIED_REAL', 0)}")
    print(f"  VERIFIED_REAL_BUT_STALE: {counts.get('VERIFIED_REAL_BUT_STALE', 0)}")
    print(f"  INDEX_PAGE:              {counts.get('INDEX_PAGE', 0)}")
    print(f"  FABRICATED:              {counts.get('FABRICATED', 0)}")
    print(f"  INTERNAL_OR_NON_PUBLIC:  {counts.get('INTERNAL_OR_NON_PUBLIC', 0)}")
    print(f"  DUPLICATE:               {counts.get('DUPLICATE', 0)}")
    print(f"  TEMPLATE_FILLER:         {counts.get('TEMPLATE_FILLER', 0)}")
    print(f"  UNKNOWN_NEEDS_REVIEW:    {counts.get('UNKNOWN_NEEDS_MANUAL_REVIEW', 0)}")
    print()
    print(f"Type breakdown:")
    print(f"  class:     {counts['class_pages']}")
    print(f"  enum:      {counts['enum_pages']}")
    print(f"  interface: {counts['interface_pages']}")
    print(f"  struct:    {counts['struct_pages']}")
    print(f"  index:     {counts['index_pages']}")
    print(f"  unknown:   {counts['other_type']}")
    print()
    print(f"Grade breakdown:")
    print(f"  Grade A:   {counts['grade_A']}")
    print(f"  Other:     {counts['grade_other']}")
    print()
    print(f"Member count verification:")
    print(f"  Method count mismatches:   {counts['method_count_mismatches']}")
    print(f"  Property count mismatches: {counts['prop_count_mismatches']}")

    # Source truth summary
    src_verified = sum(1 for r in source_rows if r["source_file_verified"] == "YES")
    src_public = sum(1 for r in source_rows if r["source_is_public"] == "YES")
    print()
    print(f"Source truth verification (all 805 api_surface entries):")
    print(f"  Source file found:     {src_verified} / {len(source_rows)}")
    print(f"  Public in source:      {src_public} / {len(source_rows)}")

    # BUG-06: stale is warning-only (not a hard fail — expected after api_surface updates)
    if counts.get("VERIFIED_REAL_BUT_STALE", 0) > 0:
        print(f"\nWARNING: {counts['VERIFIED_REAL_BUT_STALE']} pages are VERIFIED_REAL_BUT_STALE")
        print("  These pages exist and are real but have count mismatches vs current api_surface.")
        print("  Regeneration recommended. This does NOT block publication.")

    # BUG-08: cross-reference summary
    print(f"\nCross-reference summary:")
    covered_count = len(api["entries"]) - counts.get("missing_pages", 0)
    print(f"  api_surface entries covered by pages: {covered_count} / {len(api['entries'])}")
    print(f"  api_surface entries with NO page:     {counts.get('missing_pages', 0)}")
    print(f"  Pages with NO api_surface entry:      {counts.get('FABRICATED', 0)}")

    # Gate results
    if counts["do_not_publish"] == 0 and counts.get("missing_pages", 0) == 0:
        print("\n[PASS] GATE B: All pages map to verified api_surface entries")
        print("[PASS] GATE C: Zero fabricated pages")
        print("[PASS] GATE D: All api_surface entries have reference pages")
    else:
        if counts["do_not_publish"] > 0:
            print(f"\nFAIL: {counts['do_not_publish']} pages marked DO-NOT-PUBLISH")
            print(f"  See: {MISMATCH_CSV}")
        if counts.get("missing_pages", 0) > 0:
            print(f"\nFAIL: {counts['missing_pages']} api_surface entries have no reference page")

    print("\n" + "=" * 70)
    return counts, inventory_rows, mismatch_rows, source_rows, missing_pages


if __name__ == "__main__":
    counts, inventory_rows, mismatch_rows, source_rows, missing_pages = main()
    if counts["do_not_publish"] > 0 or counts.get("missing_pages", 0) > 0:
        sys.exit(1)
    sys.exit(0)
