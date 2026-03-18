"""Knowledge consolidation engine with optional external-source verification.

Usage:
    python scripts/merge.py {family} {platform}

Reads from:
    knowledge/{family}/{platform}/scout/
    knowledge/{family}/{platform}/external/  (optional)

Writes to:
    knowledge/{family}/{platform}/merged/

When only scout/ exists the merge is a passthrough consolidation.
When external/ also exists, claim-type-aware dual-source matching is applied.
"""
import json
import re
import shutil
import sys
import yaml
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Kind mapping: scout kind → compatible external-source kinds
# ---------------------------------------------------------------------------
KIND_MAP = {
    "api_method": {"api"},
    "api_class": {"api"},
    "api_constant": {"api"},
    "format_support": {"format"},
    "limitation": {"troubleshoot"},
    "install": {"install"},
    "doc_feature": {"api", "feature"},
}


def tokenize(text):
    words = re.findall(r"\w+", text.lower())
    return set(w for w in words if len(w) > 2)


def token_overlap(t1, t2):
    s1, s2 = tokenize(t1), tokenize(t2)
    if not s1 or not s2:
        return 0.0
    return len(s1 & s2) / len(s1 | s2)


def build_ext_class_index(ext_claims_indexed):
    """Index external claims by PascalCase class names they mention.

    Args:
        ext_claims_indexed: list of (index, claim) tuples
    Returns:
        dict mapping class name -> list of (index, claim) tuples
    """
    index = {}
    for idx, fc in ext_claims_indexed:
        if fc.get("kind") == "api":
            for cls in re.findall(r"([A-Z][A-Za-z0-9]{2,})", fc["text"]):
                index.setdefault(cls, []).append((idx, fc))
    return index


def find_semantic_match(scout_claim, ext_by_kind_indexed, ext_class_index):
    """Find the best external match for a scout claim using type-aware logic.

    Args:
        ext_by_kind_indexed: dict mapping kind -> list of (index, claim) tuples
        ext_class_index: dict mapping class name -> list of (index, claim) tuples

    Returns (ext_index, ext_claim, score) or None.
    """
    kind = scout_claim["kind"]
    text = scout_claim["text"]
    compatible_kinds = KIND_MAP.get(kind, {kind})

    # Gather candidates with compatible kinds — each is (index, claim)
    candidates = []
    for ck in compatible_kinds:
        candidates.extend(ext_by_kind_indexed.get(ck, []))

    if not candidates:
        return None

    if kind == "api_method":
        # Extract "ClassName.member" from "ClassName.member(args) -> Type"
        match = re.match(r"^([A-Z]\w+)\.(\w+)", text)
        if match:
            cls, member = match.groups()
            # Strong match: FL claim mentions BOTH class AND member
            for idx, fc in candidates:
                ft = fc["text"]
                if cls in ft and member in ft:
                    return (idx, fc, 0.90)
            # Medium match: FL claim must describe the SAME class and mention
            # the member as a distinct word. Requires member >= 5 chars.
            # The class must appear as a word boundary (not inside another name).
            if len(member) >= 5:
                cls_re = re.compile(r'\b' + re.escape(cls) + r'\b')
                member_re = re.compile(r'\b' + re.escape(member) + r'\b', re.IGNORECASE)
                for idx, fc in candidates:
                    ft = fc["text"]
                    if cls_re.search(ft) and member_re.search(ft):
                        # Verify the class appears as the subject, not just a parameter type
                        # by checking it's near the start or is the main topic
                        cls_pos = ft.find(cls)
                        if cls_pos < len(ft) // 2:
                            return (idx, fc, 0.80)
            # Weak match: class-only — below dual_fuzzy threshold (0.70),
            # so these become scout_only. This avoids false positives like
            # Entity.parent_nodes matching Entity.get_bounding_box.
            # Intentionally NOT returned as a match.

    elif kind == "api_class":
        # Extract "ClassName" from "Class ClassName defined in path"
        match = re.match(r"Class (\w+) defined in", text)
        if match:
            cls = match.group(1)
            for idx, fc in candidates:
                if cls in fc["text"]:
                    return (idx, fc, 0.90)

    elif kind == "format_support":
        # Extract format name from "export support for Collada via ..."
        match = re.search(r"support for (\w+)", text)
        if match:
            fmt = match.group(1).lower()
            for idx, fc in candidates:
                if fmt in fc["text"].lower():
                    return (idx, fc, 0.92)
            # Try partial format name matching (e.g. "gltf" vs "glTF")
            for idx, fc in candidates:
                ft_lower = fc["text"].lower()
                if any(alias in ft_lower for alias in _format_aliases(fmt)):
                    return (idx, fc, 0.85)

    elif kind in ("limitation", "install"):
        # Both sides use natural language — token overlap works
        best = None
        for idx, fc in candidates:
            score = token_overlap(text, fc["text"])
            if score >= 0.5 and (best is None or score > best[2]):
                best = (idx, fc, score)
        if best:
            return best

    # Final fallback: token overlap across all candidates
    best = None
    for idx, fc in candidates:
        score = token_overlap(text, fc["text"])
        if score > 0.5 and (best is None or score > best[2]):
            best = (idx, fc, score)
    return best


def _format_aliases(fmt):
    """Return common name variants for a format."""
    aliases = {
        "collada": ["collada", "dae"],
        "dae": ["collada", "dae"],
        "gltf": ["gltf", "gltf2", "gltf 2"],
        "glb": ["glb", "gltf"],
        "obj": ["obj", "wavefront"],
        "stl": ["stl"],
        "fbx": ["fbx"],
        "threemf": ["3mf", "threemf"],
        "3mf": ["3mf", "threemf"],
    }
    return aliases.get(fmt, [fmt])


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


def _build_forbidden(merged_dir):
    """Build forbidden_claims list from limitations.md in merged_dir."""
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
                forbidden.append(f"{parts[3].strip()}.{parts[4].strip()}")
    return forbidden


def _write_model(merged_dir, family, platform, scout_model, ext_model,
                 scout_claims, ext_claims, merged_claims, merged_api, stats, forbidden):
    """Write model.yaml to merged_dir."""
    merged_model = {
        "family": family,
        "platform": platform,
        "product_name": scout_model.get("product_name", ext_model.get("product_name", "")),
        "version": scout_model.get("version", ext_model.get("version", "")),
        "license": scout_model.get("license", ext_model.get("license", "")),
        "repo_sha": scout_model.get("repo_sha", ext_model.get("repo_sha", "")),
        "merged_at": datetime.now(timezone.utc).isoformat(),
        "source": "merged",
        "scout_sha": scout_model.get("repo_sha", ""),
        "external_sha": ext_model.get("repo_sha", ""),
        "stats": {
            "scout_claims": len(scout_claims),
            "external_claims": len(ext_claims),
            "merged_claims": len(merged_claims),
            "dual": stats.get("dual", 0),
            "dual_fuzzy": stats.get("dual_fuzzy", 0),
            "scout_only": stats.get("scout_only", 0),
            "external_only": stats.get("external_only", 0),
            "class_count": len(merged_api),
            "forbidden_count": len(forbidden),
        },
    }
    (merged_dir / "model.yaml").write_text(
        yaml.dump(merged_model, default_flow_style=False, sort_keys=False)
    )


def _write_report(merged_dir, family, platform, scout_model, ext_model,
                   scout_claims, ext_claims, merged_claims, stats, fuzzy_matches, forbidden):
    """Write merge_report.md to merged_dir."""
    total = sum(stats.values())
    dual_total = stats.get("dual", 0) + stats.get("dual_fuzzy", 0)
    report = [
        f"# Merge Report: {family}/{platform}",
        f"Date: {datetime.now(timezone.utc).isoformat()}",
        f"Scout SHA: {scout_model.get('repo_sha', 'n/a')}",
        f"External SHA: {ext_model.get('repo_sha', 'n/a')}",
        "",
        "## Statistics",
        "| Source | Claims |",
        "|--------|--------|",
        f"| Scout input | {len(scout_claims)} |",
        f"| External input | {len(ext_claims)} |",
        f"| Merged total | {len(merged_claims)} |",
        "",
        "## Provenance breakdown",
        "| Provenance | Count | % |",
        "|-----------|-------|---|",
    ]
    for prov in ["dual", "dual_fuzzy", "scout_only", "external_only"]:
        pct = stats.get(prov, 0) / total * 100 if total else 0
        report.append(f"| {prov} | {stats.get(prov, 0)} | {pct:.1f}% |")

    report.append("")
    report.append(f"**Dual-confirmed total: {dual_total} ({dual_total/total*100:.1f}% of {total})**" if total else "**No claims**")
    report.append(f"**Forbidden claims: {len(forbidden)}**")

    if fuzzy_matches:
        report.append("")
        report.append("## Fuzzy matches (for review)")
        report.append("| Scout claim | External claim | Score |")
        report.append("|------------|---------------|-------|")
        for fm in fuzzy_matches[:30]:
            report.append(f"| {fm['scout']} | {fm['external']} | {fm['score']} |")

    (merged_dir / "merge_report.md").write_text("\n".join(report) + "\n")


def merge(family, platform):
    """Run the merge pipeline for a given family/platform."""
    base = Path("knowledge") / family / platform
    scout_dir = base / "scout"
    ext_dir = base / "external"
    merged_dir = base / "merged"
    merged_dir.mkdir(parents=True, exist_ok=True)

    # Determine which sources exist
    has_scout = (scout_dir / "claims.json").exists()
    has_ext = (ext_dir / "claims.json").exists()

    if not has_scout and not has_ext:
        print(f"ERROR: No knowledge sources found for {family}/{platform}")
        return False

    # Load and validate data
    scout_claims_raw = json.loads((scout_dir / "claims.json").read_text()) if has_scout else []
    ext_claims_raw = json.loads((ext_dir / "claims.json").read_text()) if has_ext else []
    scout_claims = _validate_claims(scout_claims_raw, "scout")
    ext_claims = _validate_claims(ext_claims_raw, "external")
    scout_model = yaml.safe_load((scout_dir / "model.yaml").read_text()) if has_scout and (scout_dir / "model.yaml").exists() else {}
    ext_model = yaml.safe_load((ext_dir / "model.yaml").read_text()) if has_ext and (ext_dir / "model.yaml").exists() else {}

    # API surface
    scout_api = json.loads((scout_dir / "api_surface.json").read_text()) if has_scout and (scout_dir / "api_surface.json").exists() else []
    ext_api = json.loads((ext_dir / "api_surface.json").read_text()) if has_ext and (ext_dir / "api_surface.json").exists() else []

    print(f"Merge: {family}/{platform}")
    print(f"  Scout:    {len(scout_claims)} claims, {len(scout_api) if isinstance(scout_api, list) else '?'} classes")
    print(f"  External: {len(ext_claims)} claims")

    # ----- Scout-only fast path -----
    if has_scout and not has_ext:
        print("  Mode: scout-only passthrough consolidation")
        for sc in scout_claims:
            sc["provenance"] = "scout_only"
        (merged_dir / "claims.json").write_text(
            json.dumps(scout_claims, indent=2, ensure_ascii=False)
        )
        merged_api = list(scout_api) if isinstance(scout_api, list) else []
        (merged_dir / "api_surface.json").write_text(
            json.dumps(merged_api, indent=2, ensure_ascii=False)
        )
        for f in ["formats.json", "class_graph.json", "coverage_matrix.json",
                   "constants.json", "limitations.md", "install.md"]:
            src = scout_dir / f
            if src.exists():
                shutil.copy2(src, merged_dir / f)
        if (merged_dir / "formats.json").exists():
            formats = json.loads((merged_dir / "formats.json").read_text())
            fmt_lines = ["# Format Support\n", "| Format | Import | Export |", "|--------|--------|--------|"]
            for fmt in formats:
                name = fmt.get("name", fmt.get("format", ""))
                imp = "Y" if fmt.get("can_import") else "-"
                exp = "Y" if fmt.get("can_export") else "-"
                fmt_lines.append(f"| {name} | {imp} | {exp} |")
            (merged_dir / "formats.md").write_text("\n".join(fmt_lines) + "\n")
        forbidden = _build_forbidden(merged_dir)
        stats = {"scout_only": len(scout_claims)}
        _write_model(merged_dir, family, platform, scout_model, {}, scout_claims, [],
                     scout_claims, merged_api, stats, forbidden)
        _write_report(merged_dir, family, platform, scout_model, {}, scout_claims, [],
                      scout_claims, stats, [], forbidden)
        print(f"  Total: {len(scout_claims)} claims (all scout_only)")
        print(f"  All artifacts written to {merged_dir}")
        return True

    # ----- Dual-source matching -----
    # Build external indices for fast lookup — each entry is (index, claim)
    ext_by_kind_indexed = {}
    for i, fc in enumerate(ext_claims):
        k = fc.get("kind", "unknown")
        ext_by_kind_indexed.setdefault(k, []).append((i, fc))

    ext_class_index = build_ext_class_index(list(enumerate(ext_claims)))

    # -----------------------------------------------------------------------
    # Merge claims with type-aware matching
    # -----------------------------------------------------------------------
    merged_claims = []
    ext_matched = set()  # tracks external indices (integers)
    stats = Counter()
    fuzzy_matches = []

    for sc in scout_claims:
        result = find_semantic_match(sc, ext_by_kind_indexed, ext_class_index)

        if result:
            ext_idx, fc, score = result
            mc = dict(sc)

            if score >= 0.85:
                mc["provenance"] = "dual"
                mc["confidence"] = max(sc.get("confidence", 0.8), fc.get("confidence", 0.8))
                stats["dual"] += 1
                ext_matched.add(ext_idx)
            elif score >= 0.70:
                mc["provenance"] = "dual_fuzzy"
                mc["confidence"] = max(sc.get("confidence", 0.8), fc.get("confidence", 0.8))
                stats["dual_fuzzy"] += 1
                ext_matched.add(ext_idx)
                fuzzy_matches.append({
                    "scout": sc["text"][:80],
                    "external": fc["text"][:80],
                    "score": round(score, 3),
                })
            else:
                mc["provenance"] = "scout_only"
                stats["scout_only"] += 1

            merged_claims.append(mc)
        else:
            mc = dict(sc)
            mc["provenance"] = "scout_only"
            merged_claims.append(mc)
            stats["scout_only"] += 1

    # Add external-only claims
    for i, fc in enumerate(ext_claims):
        if i not in ext_matched:
            mc = dict(fc)
            src = fc.get("claim_source", "")
            if src in ("llm", "llm_fallback"):
                mc["provenance"] = "external_only"
                mc["confidence"] = fc.get("confidence", 0.8) * 0.6
            else:
                mc["provenance"] = "external_only"
                mc["confidence"] = fc.get("confidence", 0.8) * 0.8
            merged_claims.append(mc)
            stats["external_only"] += 1

    print(f"\n  Merge stats: {dict(stats)}")
    print(f"  Total merged: {len(merged_claims)}")

    # Write merged claims
    (merged_dir / "claims.json").write_text(
        json.dumps(merged_claims, indent=2, ensure_ascii=False)
    )

    # -----------------------------------------------------------------------
    # Merge API surface
    # -----------------------------------------------------------------------
    scout_class_names = set()
    if isinstance(scout_api, list):
        scout_class_names = {c["name"] for c in scout_api if isinstance(c, dict) and "name" in c}
    merged_api = list(scout_api) if isinstance(scout_api, list) else []
    ext_only_classes = []

    if isinstance(ext_api, dict):
        ext_class_names = ext_api.get("api_identifiers", [])
        for name in ext_class_names:
            if name not in scout_class_names:
                ext_only_classes.append(name)
                merged_api.append({"name": name, "kind": "class", "methods": [], "properties": [], "source": "external"})
    elif isinstance(ext_api, list):
        for fc in ext_api:
            name = fc.get("name", "") if isinstance(fc, dict) else fc
            if name not in scout_class_names:
                ext_only_classes.append(name)
                entry = fc if isinstance(fc, dict) else {"name": name, "kind": "class", "methods": [], "properties": [], "source": "external"}
                merged_api.append(entry)

    print(f"  API surface: {len(scout_class_names)} scout + {len(ext_only_classes)} external-only = {len(merged_api)}")
    (merged_dir / "api_surface.json").write_text(
        json.dumps(merged_api, indent=2, ensure_ascii=False)
    )

    # -----------------------------------------------------------------------
    # Copy other artifacts (prefer scout, fall back to external)
    # -----------------------------------------------------------------------
    for f in ["formats.json", "class_graph.json", "coverage_matrix.json", "constants.json"]:
        src = scout_dir / f
        if not src.exists() and has_ext:
            src = ext_dir / f
        if src.exists():
            shutil.copy2(src, merged_dir / f)

    for f in ["limitations.md", "install.md"]:
        src = scout_dir / f
        if not src.exists() and has_ext:
            src = ext_dir / f
        if src.exists():
            shutil.copy2(src, merged_dir / f)

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

    forbidden = _build_forbidden(merged_dir)
    _write_model(merged_dir, family, platform, scout_model, ext_model,
                 scout_claims, ext_claims, merged_claims, merged_api, stats, forbidden)
    _write_report(merged_dir, family, platform, scout_model, ext_model,
                  scout_claims, ext_claims, merged_claims, stats, fuzzy_matches, forbidden)

    dual_total = stats["dual"] + stats["dual_fuzzy"]
    print(f"  Forbidden claims: {len(forbidden)}")
    total = sum(stats.values())
    print(f"  Dual-confirmed: {dual_total} ({dual_total/total*100:.1f}%)" if total else "  No claims")
    print(f"  All artifacts written to {merged_dir}")
    print(f"  Files: {sorted(f.name for f in merged_dir.iterdir())}")

    return dual_total > 0 or not has_ext  # Success if we got dual matches or only one source


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
