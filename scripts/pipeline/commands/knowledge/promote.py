"""Dual-source knowledge merge: merges scout and FL claims into merged/ with provenance tagging.

Usage:
    python scripts/merge.py {family} {platform}

Reads from:
    knowledge/{family}/{platform}/scout/
    knowledge/{family}/{platform}/fl/        (optional — gracefully skipped if absent)

Writes to:
    knowledge/{family}/{platform}/merged/

Provenance rules:
    dual        — same kind + Jaccard token overlap >= 0.8 in both scout and FL
    scout_only  — scout claim with no matching FL claim
    fl_only     — FL claim not matched by any scout claim (confidence penalised)
"""
import json
import re
import shutil
import sys
import yaml
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # scripts/
from config_loader import resolve_knowledge_root as _resolve_knowledge_root

# Same criteria as _is_public_api_entry in index.py — must stay in sync.
_TEST_PATH_PATTERNS = ("tests/", "/tests/", "/test_", "test_", "conftest")
_INTERNAL_PATH_PATTERNS = ("/_internal/", "/_private/", "/_impl/")

# Minimum Jaccard overlap for a scout+FL claim pair to be tagged "dual"
_DUAL_OVERLAP_THRESHOLD = 0.8


def _validate_claims(claims, source_label):
    """Validate and filter claims list. Returns valid claims, warns on bad ones."""
    if not isinstance(claims, list):
        print(f"  WARNING: {source_label} claims.json is not a list, skipping")
        return []
    valid = []
    for i, c in enumerate(claims):
        if not isinstance(c, dict):
            print(f"  WARNING: {source_label} claim #{i} is not a dict, skipping")
            continue
        if "text" not in c or "kind" not in c:
            print(f"  WARNING: {source_label} claim #{i} missing 'text' or 'kind', skipping")
            continue
        valid.append(c)
    if len(valid) < len(claims):
        print(f"  WARNING: {source_label} {len(claims) - len(valid)} invalid claims filtered")
    return valid


def _tokenize(text: str) -> set:
    """Extract lowercase word tokens from text for Jaccard overlap matching."""
    return set(re.findall(r"[a-z0-9_]+", text.lower()))


# ---------------------------------------------------------------------------
# Backward-compatibility aliases (used by test_merge_units.py)
# ---------------------------------------------------------------------------

def tokenize(text: str) -> set:
    """Public alias for _tokenize — extracts lowercase word tokens (len > 2)."""
    return set(w for w in re.findall(r"\w+", text.lower()) if len(w) > 2)


def token_overlap(t1: str, t2: str) -> float:
    """Jaccard token overlap between two text strings."""
    s1, s2 = tokenize(t1), tokenize(t2)
    if not s1 or not s2:
        return 0.0
    return len(s1 & s2) / len(s1 | s2)


# Kind mapping for find_semantic_match (backward-compat)
_KIND_MAP = {
    "api_method": {"api"},
    "api_class": {"api"},
    "api_constant": {"api"},
    "format_support": {"format"},
    "limitation": {"troubleshoot"},
    "install": {"install"},
    "doc_feature": {"api", "feature"},
}


def find_semantic_match(scout_claim, ext_by_kind_indexed, ext_class_index):
    """Find the best external match for a scout claim using type-aware logic.

    Args:
        scout_claim: dict with 'kind' and 'text' fields
        ext_by_kind_indexed: dict mapping kind -> list of (index, claim) tuples
        ext_class_index: dict mapping class name -> list of (index, claim) tuples

    Returns (ext_index, ext_claim, score) or None.
    """
    kind = scout_claim["kind"]
    text = scout_claim["text"]
    compatible_kinds = _KIND_MAP.get(kind, {kind})

    candidates = []
    for ck in compatible_kinds:
        candidates.extend(ext_by_kind_indexed.get(ck, []))

    if not candidates:
        return None

    if kind == "api_method":
        match = re.match(r"^([A-Z]\w+)\.(\w+)", text)
        if match:
            cls, member = match.groups()
            for idx, fc in candidates:
                ft = fc["text"]
                if cls in ft and member in ft:
                    return (idx, fc, 0.90)
            if len(member) >= 5:
                cls_re = re.compile(r'\b' + re.escape(cls) + r'\b')
                member_re = re.compile(r'\b' + re.escape(member) + r'\b', re.IGNORECASE)
                for idx, fc in candidates:
                    ft = fc["text"]
                    if cls_re.search(ft) and member_re.search(ft):
                        cls_pos = ft.find(cls)
                        if cls_pos < len(ft) // 2:
                            return (idx, fc, 0.80)

    elif kind == "api_class":
        match = re.match(r"Class (\w+) defined in", text)
        if match:
            cls = match.group(1)
            for idx, fc in candidates:
                if cls in fc["text"]:
                    return (idx, fc, 0.90)

    elif kind == "format_support":
        match = re.search(r"support for (\w+)", text)
        if match:
            fmt = match.group(1).lower()
            for idx, fc in candidates:
                if fmt in fc["text"].lower():
                    return (idx, fc, 0.92)

    elif kind in ("limitation", "install"):
        best = None
        for idx, fc in candidates:
            score = token_overlap(text, fc["text"])
            if score >= 0.5 and (best is None or score > best[2]):
                best = (idx, fc, score)
        if best:
            return best

    best = None
    for idx, fc in candidates:
        score = token_overlap(text, fc["text"])
        if score > 0.5 and (best is None or score > best[2]):
            best = (idx, fc, score)
    return best


def _merge_fl_claims(scout_claims: list, fl_claims: list) -> tuple[list, dict]:
    """Merge scout and FL claims with dual-source verification (S-35 algorithm).

    Matching criteria: same ``kind`` AND Jaccard token overlap >= _DUAL_OVERLAP_THRESHOLD.

    Returns:
        (merged_list, counts) where counts has keys: dual, scout_only, fl_only
    """
    # Group FL claims by kind for O(n+m) matching
    fl_by_kind: dict[str, list] = {}
    for fc in fl_claims:
        kind = fc.get("kind", "")
        fl_by_kind.setdefault(kind, []).append(
            (fc, _tokenize(fc.get("text", "")))
        )

    matched_fl_ids: set = set()
    merged: list[dict] = []
    n_dual = 0

    for sc in scout_claims:
        mc = dict(sc)
        sc_kind = sc.get("kind", "")
        sc_tokens = _tokenize(sc.get("text", ""))

        best_fc = None
        best_overlap = 0.0

        for fc, fc_tokens in fl_by_kind.get(sc_kind, []):
            union = sc_tokens | fc_tokens
            if not union:
                continue
            overlap = len(sc_tokens & fc_tokens) / len(union)
            if overlap >= _DUAL_OVERLAP_THRESHOLD and overlap > best_overlap:
                best_overlap = overlap
                best_fc = fc

        if best_fc is not None:
            # Use id() as fallback key so we never mis-identify across claims
            fc_key = best_fc.get("claim_id") or id(best_fc)
            matched_fl_ids.add(fc_key)
            mc["provenance"] = "dual"
            mc["confidence"] = max(
                sc.get("confidence", 1.0),
                best_fc.get("confidence", 0.0),
            )
            mc["fl_claim_id"] = best_fc.get("claim_id", "")
            n_dual += 1
        else:
            mc["provenance"] = "scout_only"

        merged.append(mc)

    # FL-only claims (not matched by any scout claim)
    n_fl_only = 0
    for fc in fl_claims:
        fc_key = fc.get("claim_id") or id(fc)
        if fc_key in matched_fl_ids:
            continue
        # Confidence penalty depends on how the FL claim was produced
        src = fc.get("claim_source", "llm")
        multiplier = 0.8 if src == "deterministic" else 0.6
        mc = dict(fc)
        mc["provenance"] = "fl_only"
        mc["confidence"] = round(fc.get("confidence", 0.75) * multiplier, 4)
        merged.append(mc)
        n_fl_only += 1

    counts = {
        "dual": n_dual,
        "scout_only": len(scout_claims) - n_dual,
        "fl_only": n_fl_only,
    }
    return merged, counts


def _generate_api_surface_md(api_list, family, model, out_dir):
    """Generate human-readable api_surface.md from merged api_surface.json.

    This file is the primary knowledge artifact for LLM prompt injection
    during content generation. It must contain every class, method, property,
    and enum value that content is allowed to reference.
    """
    special = {"3d": "3D"}
    display = special.get(family, family.title())
    lines = [
        f"# API Surface — Aspose.{display}",
        f"<!-- Generated by merge.py from merged/api_surface.json -->",
        f"<!-- repo_sha: {model.get('repo_sha', 'unknown')} -->",
        "",
    ]

    classes = sorted(api_list, key=lambda c: c.get("name", "")) if isinstance(api_list, list) else []

    for cls in classes:
        name = cls.get("name", "")
        if not name:
            continue
        kind = cls.get("kind", "class_definition")
        # Skip standalone functions and test helpers
        if kind == "function" or name.startswith("test_"):
            continue

        doc = cls.get("doc", "").strip()
        bases = cls.get("bases", [])

        lines.append(f"## {name}")
        if doc:
            lines.append(f"**Docstring**: {doc}")
        if bases:
            lines.append(f"**Bases**: {', '.join(bases)}")

        # Methods — skip dunder methods, show public API only
        methods = [m for m in cls.get("methods", [])
                   if isinstance(m, dict) and not m.get("name", "").startswith("_")]
        if methods:
            lines.append("**Methods**:")
            for m in methods:
                mname = m.get("name", "")
                params = ", ".join(p.get("name", "") for p in m.get("params", [])
                                  if isinstance(p, dict))
                ret = m.get("return_type", "")
                sig = f"{mname}({params})"
                if ret:
                    sig += f" -> {ret}"
                lines.append(f"- `{sig}`")
        else:
            lines.append("**Methods**: _none_")

        # Properties
        props = cls.get("properties", [])
        if props:
            lines.append("**Properties**:")
            for p in props:
                if not isinstance(p, dict):
                    continue
                pname = p.get("name", "")
                ptype = p.get("type", "Any")
                lines.append(f"- `{pname}: {ptype}`")

        # Enum members
        enums = cls.get("enum_members", [])
        if enums:
            lines.append("**Enum values**:")
            for e in enums:
                ename = e.get("name", e) if isinstance(e, dict) else str(e)
                lines.append(f"- `{ename}`")

        lines.append("")

    md_text = "\n".join(lines) + "\n"
    (out_dir / "api_surface.md").write_text(md_text, encoding="utf-8")
    print(f"  api_surface.md: {len(classes)} classes, {len(md_text)} bytes")


def _merge_snippets(base, scout_dir, merged_dir):
    """Merge snippets from scout/ and fl/ into merged/snippets/.

    Priority logic:
    - If both scout/snippets/ and fl/snippets/ exist: merge, preferring scout
      (de-duplicate by source_function name).
    - If only scout/snippets/ exists: copy to merged/.
    - If only fl/snippets/ exists: copy to merged/.
    - Returns the total snippet count.
    """
    fl_dir = base / "fl"
    scout_snip = scout_dir / "snippets"
    fl_snip = fl_dir / "snippets"
    merged_snip = merged_dir / "snippets"

    has_scout_snip = (scout_snip / "snippets_index.json").exists()
    has_fl_snip = (fl_snip / "snippets_index.json").exists()

    if not has_scout_snip and not has_fl_snip:
        print("  Snippets: none available")
        return 0

    # Build the set of public API class names so that classes_used in merged
    # snippet entries only references developer-visible classes.
    # api_surface.json is already written to merged_dir before this function runs.
    _public_class_names: set = set()
    api_surface_path = merged_dir / "api_surface.json"
    if api_surface_path.exists():
        try:
            _api_list = json.loads(api_surface_path.read_text(encoding="utf-8"))
            for _c in _api_list:
                if not isinstance(_c, dict):
                    continue
                if _c.get("kind") == "function":
                    continue
                _name = _c.get("name", "")
                if not _name or _name.startswith("_"):
                    continue
                _file = _c.get("file", "")
                if any(pat in _file for pat in _TEST_PATH_PATTERNS):
                    continue
                if any(pat in _file for pat in _INTERNAL_PATH_PATTERNS):
                    continue
                _public_class_names.add(_name)
        except (json.JSONDecodeError, OSError):
            pass

    merged_snip.mkdir(parents=True, exist_ok=True)

    scout_index = []
    fl_index = []

    if has_scout_snip:
        try:
            scout_index = json.loads(
                (scout_snip / "snippets_index.json").read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            scout_index = []

    if has_fl_snip:
        try:
            fl_index = json.loads(
                (fl_snip / "snippets_index.json").read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            fl_index = []

    # De-duplicate: prefer scout version when source_function matches
    seen_functions = set()
    merged_index = []
    snippet_num = 0

    # Scout snippets first (preferred)
    for entry in scout_index:
        if not isinstance(entry, dict):
            continue
        src_fn = entry.get("source_function", "")
        seen_functions.add(src_fn)

        snippet_num += 1
        new_id = f"snippet_{snippet_num:03d}"
        src_file = entry.get("file", "")

        # Copy the snippet file if it exists
        if src_file and (scout_snip / src_file).exists():
            shutil.copy2(scout_snip / src_file, merged_snip / src_file)

        merged_entry = dict(entry)
        merged_entry["id"] = new_id
        merged_entry["provenance"] = "scout"
        if _public_class_names:
            merged_entry["classes_used"] = [
                c for c in merged_entry.get("classes_used", [])
                if c in _public_class_names
            ]
        merged_index.append(merged_entry)

    # FL snippets (only if not already covered by scout)
    for entry in fl_index:
        if not isinstance(entry, dict):
            continue
        src_fn = entry.get("source_function", "")
        # Also accept entries keyed by "source_file" for fl-style indices
        if not src_fn:
            src_fn = entry.get("source_file", "")
        if src_fn in seen_functions:
            continue
        seen_functions.add(src_fn)

        snippet_num += 1
        new_id = f"snippet_{snippet_num:03d}"

        # fl uses "id" like "snip_001" — map the file from that
        fl_file = entry.get("file", "")
        if not fl_file:
            old_id = entry.get("id", "")
            if old_id:
                # Infer file name from id + lang
                lang = entry.get("lang", "")
                ext_map = {"python": ".py", "typescript": ".ts",
                           "javascript": ".js", "java": ".java",
                           "csharp": ".cs", "cpp": ".cpp"}
                fl_ext = ext_map.get(lang, ".txt")
                fl_file = f"{old_id}{fl_ext}"

        if fl_file and (fl_snip / fl_file).exists():
            shutil.copy2(fl_snip / fl_file, merged_snip / fl_file)

        merged_entry = dict(entry)
        merged_entry["id"] = new_id
        merged_entry["provenance"] = "fl"
        if _public_class_names:
            merged_entry["classes_used"] = [
                c for c in merged_entry.get("classes_used", [])
                if c in _public_class_names
            ]
        merged_index.append(merged_entry)

    # Write merged index
    (merged_snip / "snippets_index.json").write_text(
        json.dumps(merged_index, indent=2, ensure_ascii=False),
        encoding="utf-8")

    print(f"  Snippets: {len(merged_index)} "
          f"(scout: {len(scout_index)}, fl: {len(fl_index)}, "
          f"after dedup: {len(merged_index)})")

    return len(merged_index)


def merge(family, platform):
    """Run the dual-source merge pipeline for a given family/platform.

    Merges scout/ claims (deterministic, confidence=1.0) with fl/ claims
    (LLM-enriched, confidence varies) using provenance tagging.  When fl/
    is absent the output is identical to the previous scout-only behaviour.
    """
    base = _resolve_knowledge_root() / family / platform
    scout_dir = base / "scout"
    fl_dir = base / "fl"
    merged_dir = base / "merged"
    merged_dir.mkdir(parents=True, exist_ok=True)

    # Scout is required
    has_scout = (scout_dir / "claims.json").exists()
    if not has_scout:
        print(f"ERROR: No scout knowledge found for {family}/{platform}")
        return False

    # Load and validate scout data
    scout_claims_raw = json.loads((scout_dir / "claims.json").read_text(encoding="utf-8"))
    scout_claims = _validate_claims(scout_claims_raw, "scout")
    scout_model = yaml.safe_load((scout_dir / "model.yaml").read_text()) if (scout_dir / "model.yaml").exists() else {}

    # API surface
    scout_api = json.loads((scout_dir / "api_surface.json").read_text()) if (scout_dir / "api_surface.json").exists() else []

    scout_class_names: set[str] = set()
    if isinstance(scout_api, list):
        scout_class_names = {c["name"] for c in scout_api if isinstance(c, dict) and "name" in c}

    # Load FL claims (optional — gracefully skipped if absent)
    fl_claims_path = fl_dir / "claims.json"
    has_fl = fl_claims_path.exists()
    fl_claims: list = []
    fl_claim_count = 0
    if has_fl:
        try:
            fl_raw = json.loads(fl_claims_path.read_text(encoding="utf-8"))
            fl_claims = _validate_claims(fl_raw, "fl")
            fl_claim_count = len(fl_claims)
        except (json.JSONDecodeError, OSError) as e:
            print(f"  WARNING: Could not read fl/claims.json: {e}")
            has_fl = False

    print(f"Merge: {family}/{platform}")
    print(f"  Scout: {len(scout_claims)} claims, {len(scout_class_names)} classes")
    if has_fl:
        print(f"  FL:    {fl_claim_count} claims")
    else:
        print("  FL:    not present — scout-only merge")

    # -----------------------------------------------------------------------
    # Merge claims with dual-source verification
    # -----------------------------------------------------------------------
    if has_fl and fl_claims:
        merged_claims, merge_counts = _merge_fl_claims(scout_claims, fl_claims)
        print(f"  Dual: {merge_counts['dual']}, "
              f"Scout-only: {merge_counts['scout_only']}, "
              f"FL-only: {merge_counts['fl_only']}")
    else:
        merged_claims = [{**sc, "provenance": "scout_only"} for sc in scout_claims]
        merge_counts = {
            "dual": 0,
            "scout_only": len(scout_claims),
            "fl_only": 0,
        }

    print(f"  Total claims: {len(merged_claims)}")

    # Write merged claims
    (merged_dir / "claims.json").write_text(
        json.dumps(merged_claims, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # -----------------------------------------------------------------------
    # Copy API surface directly from scout
    # -----------------------------------------------------------------------
    merged_api = list(scout_api) if isinstance(scout_api, list) else []
    print(f"  API surface: {len(merged_api)} classes")
    (merged_dir / "api_surface.json").write_text(
        json.dumps(merged_api, indent=2, ensure_ascii=False)
    )

    # -----------------------------------------------------------------------
    # Copy scout artifacts to merged
    # -----------------------------------------------------------------------
    if (scout_dir / "formats.json").exists():
        shutil.copy2(scout_dir / "formats.json", merged_dir / "formats.json")

    for f in ["class_graph.json", "coverage_matrix.json", "limitations.md", "install.md",
              "constants.json"]:
        src = scout_dir / f
        if src.exists():
            shutil.copy2(src, merged_dir / f)

    # -----------------------------------------------------------------------
    # Merge snippets from scout/ and fl/ into merged/snippets/
    # -----------------------------------------------------------------------
    snippet_count = _merge_snippets(base, scout_dir, merged_dir)

    # Build formats.md from formats.json if available
    fmt_path = merged_dir / "formats.json"
    if fmt_path.exists():
        formats = json.loads(fmt_path.read_text())
        fmt_lines = ["# Format Support\n", "| Format | Import | Export |", "|--------|--------|--------|"]
        for fmt in formats:
            name = fmt.get("name", fmt.get("format", ""))
            imp = "Y" if fmt.get("can_import") else "-"
            exp = "Y" if fmt.get("can_export") else "-"
            fmt_lines.append(f"| {name} | {imp} | {exp} |")
        (merged_dir / "formats.md").write_text("\n".join(fmt_lines) + "\n")

    # Build forbidden_claims from limitations
    forbidden = []
    lim_path = merged_dir / "limitations.md"
    if lim_path.exists():
        for line in lim_path.read_text().splitlines():
            if "|" not in line or "---" in line:
                continue
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 5 and parts[1] == "File":
                continue
            if len(parts) >= 5 and parts[3] and parts[4]:
                cls = parts[3].strip()
                method = parts[4].strip()
                forbidden.append(f"{cls}.{method}")

    # -----------------------------------------------------------------------
    # Write model.yaml
    # -----------------------------------------------------------------------
    is_dual = has_fl and bool(fl_claims)
    merged_model = {
        "family": family,
        "platform": platform,
        "product_name": scout_model.get("product_name", ""),
        "version": scout_model.get("version", ""),
        "license": scout_model.get("license", ""),
        "repo_url": scout_model.get("repo_url", ""),
        "repo_sha": scout_model.get("repo_sha", ""),
        "stale_since": None,
        "merged_at": datetime.now(timezone.utc).isoformat(),
        "source": "dual" if is_dual else "scout_only",
        "has_conflicts": False,
        "stats": {
            "scout_claims": len(scout_claims),
            "fl_claims": fl_claim_count,
            "merged_claims": len(merged_claims),
            "dual": merge_counts["dual"],
            "scout_only": merge_counts["scout_only"],
            "fl_only": merge_counts["fl_only"],
            "class_count": len(merged_api),
            "forbidden_count": len(forbidden),
            "snippet_count": snippet_count,
        },
    }
    (merged_dir / "model.yaml").write_text(
        yaml.dump(merged_model, default_flow_style=False, sort_keys=False)
    )

    # -----------------------------------------------------------------------
    # Build api_surface.md
    # -----------------------------------------------------------------------
    _generate_api_surface_md(merged_api, family, merged_model, merged_dir)

    # -----------------------------------------------------------------------
    # Write merge_report.md
    # -----------------------------------------------------------------------
    source_label = "dual-source (scout + fl)" if is_dual else "scout-only (no FL merge)"
    dual_pct = (
        round(merge_counts["dual"] / len(scout_claims) * 100, 1)
        if is_dual and scout_claims else 0
    )

    report = [
        f"# Merge Report: {family}/{platform}",
        f"Date: {datetime.now(timezone.utc).isoformat()}",
        f"Scout SHA: {scout_model.get('repo_sha', 'n/a')}",
        f"Source: {source_label}",
        "",
        "## Statistics",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Scout claims | {len(scout_claims)} |",
        f"| FL claims | {fl_claim_count} |",
        f"| Merged claims | {len(merged_claims)} |",
        f"| Dual (both sources) | {merge_counts['dual']} |",
        f"| Scout-only | {merge_counts['scout_only']} |",
        f"| FL-only | {merge_counts['fl_only']} |",
        f"| Classes | {len(merged_api)} |",
        f"| Forbidden claims | {len(forbidden)} |",
        f"| Snippets | {snippet_count} |",
        "",
    ]

    if is_dual:
        report.append(f"Dual-confirmed rate: {dual_pct}% of scout claims have FL corroboration.")
    else:
        report.append("All claims have `provenance: scout_only` (deterministic code analysis, confidence=1.0).")

    (merged_dir / "merge_report.md").write_text("\n".join(report) + "\n")

    # Clean up legacy merge_conflicts.md if present (no active conflict detection yet)
    conflicts_path = merged_dir / "merge_conflicts.md"
    if conflicts_path.exists():
        conflicts_path.unlink()
        print("  Removed legacy merge_conflicts.md")

    print(f"  Forbidden claims: {len(forbidden)}")
    print(f"  All artifacts written to {merged_dir}")
    print(f"  Files: {sorted(f.name for f in merged_dir.iterdir())}")

    return True


def main():
    if len(sys.argv) < 3:
        print("Usage: python scripts/merge.py {family} {platform}")
        print("Example: python scripts/merge.py 3d python")
        sys.exit(1)

    family = sys.argv[1]
    platform = sys.argv[2]
    success = merge(family, platform)
    print(f"\nTRUTH-MERGE: {'PASS' if success else 'FAIL'}")
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
