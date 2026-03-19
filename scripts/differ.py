"""Evidence Diff Engine — compare two PEFs to surface what changed.

Usage:
    python scripts/differ.py {family} {platform}           # Compare pef.json vs pef_previous.json
    python scripts/differ.py {pef_a_path} {pef_b_path}     # Compare two arbitrary PEFs
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

EVIDENCE_ROOT = Path("evidence")


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _diff_claims(old_claims, new_claims):
    """Diff claims by claim_id. Returns added/removed/modified/provenance_changed."""
    old_map = {}
    for c in old_claims:
        cid = c.get("claim_id", "")
        if cid:
            old_map[cid] = c

    new_map = {}
    for c in new_claims:
        cid = c.get("claim_id", "")
        if cid:
            new_map[cid] = c

    old_ids = set(old_map.keys())
    new_ids = set(new_map.keys())

    added = [{"claim_id": cid, "kind": new_map[cid].get("kind", ""), "text": new_map[cid].get("text", "")}
             for cid in sorted(new_ids - old_ids)]
    removed = [{"claim_id": cid, "kind": old_map[cid].get("kind", ""), "text": old_map[cid].get("text", "")}
               for cid in sorted(old_ids - new_ids)]

    modified = []
    provenance_changed = []
    for cid in sorted(old_ids & new_ids):
        old_c = old_map[cid]
        new_c = new_map[cid]
        if old_c.get("text") != new_c.get("text"):
            modified.append({
                "claim_id": cid,
                "old_text": old_c.get("text", ""),
                "new_text": new_c.get("text", ""),
                "confidence_delta": round(
                    (new_c.get("confidence", 0) or 0) - (old_c.get("confidence", 0) or 0), 3
                ),
            })
        if old_c.get("provenance") != new_c.get("provenance"):
            provenance_changed.append({
                "claim_id": cid,
                "old": old_c.get("provenance", ""),
                "new": new_c.get("provenance", ""),
            })

    return {
        "added": added,
        "removed": removed,
        "modified": modified,
        "provenance_changed": provenance_changed,
    }


def _diff_api_surface(old_api, new_api):
    """Diff API surface by class name and methods."""
    def _class_names(api):
        return {e.get("name", "") for e in api if isinstance(e, dict) and e.get("name")}

    def _methods_for(api):
        result = {}
        for entry in api:
            if not isinstance(entry, dict):
                continue
            cname = entry.get("name", "")
            methods = entry.get("methods", [])
            for m in methods:
                mname = m.get("name", "") if isinstance(m, dict) else str(m)
                if mname:
                    result.setdefault(cname, set()).add(mname)
        return result

    old_classes = _class_names(old_api)
    new_classes = _class_names(new_api)

    classes_added = sorted(new_classes - old_classes)
    classes_removed = sorted(old_classes - new_classes)

    old_methods = _methods_for(old_api)
    new_methods = _methods_for(new_api)

    methods_added = []
    methods_removed = []
    for cls in old_classes & new_classes:
        old_m = old_methods.get(cls, set())
        new_m = new_methods.get(cls, set())
        for m in sorted(new_m - old_m):
            methods_added.append({"class": cls, "method": m})
        for m in sorted(old_m - new_m):
            methods_removed.append({"class": cls, "method": m})

    return {
        "classes_added": classes_added,
        "classes_removed": classes_removed,
        "methods_added": methods_added,
        "methods_removed": methods_removed,
    }


def _diff_formats(old_formats, new_formats):
    """Diff format support."""
    def _format_set(formats):
        result = set()
        for f in formats:
            if isinstance(f, dict):
                name = f.get("format", f.get("name", ""))
                direction = f.get("direction", "")
                can_imp = f.get("can_import", False) or direction in ("import", "both")
                can_exp = f.get("can_export", False) or direction in ("export", "both")
                if can_imp:
                    result.add((name, "import"))
                if can_exp:
                    result.add((name, "export"))
        return result

    old_set = _format_set(old_formats)
    new_set = _format_set(new_formats)

    added = [{"format": f, "direction": d} for f, d in sorted(new_set - old_set)]
    removed = [{"format": f, "direction": d} for f, d in sorted(old_set - new_set)]

    return {"added": added, "removed": removed}


def _assess_impact(claims_diff, api_diff, formats_diff):
    """Determine overall impact severity and affected page types."""
    affected = set()

    # API removals are HIGH impact
    if api_diff["classes_removed"] or api_diff["methods_removed"]:
        affected.add("reference")
        affected.add("docs")

    # Claim removals affect various pages
    if claims_diff["removed"]:
        for c in claims_diff["removed"]:
            kind = c.get("kind", "")
            if kind == "api_class" or kind == "api_method":
                affected.add("reference")
            elif kind == "format_support":
                affected.add("docs")
                affected.add("kb")

    # New claims/classes
    if claims_diff["added"] or api_diff["classes_added"]:
        affected.add("reference")
        affected.add("docs")

    if formats_diff["removed"]:
        affected.add("docs")
        affected.add("kb")

    # Severity
    has_removals = (
        bool(api_diff["classes_removed"])
        or bool(api_diff["methods_removed"])
        or bool(claims_diff["removed"])
        or bool(formats_diff["removed"])
    )
    has_additions = (
        bool(api_diff["classes_added"])
        or bool(claims_diff["added"])
        or bool(formats_diff["added"])
    )
    has_modifications = bool(claims_diff["modified"])

    if has_removals:
        severity = "HIGH"
        recommendation = "Re-verify and update affected pages immediately"
    elif has_modifications:
        severity = "MEDIUM"
        recommendation = "Review modified claims and update affected sections"
    elif has_additions:
        severity = "LOW"
        recommendation = "Consider creating or expanding content for new evidence"
    else:
        severity = "NONE"
        recommendation = "No action needed"

    return {
        "severity": severity,
        "affected_page_types": sorted(affected),
        "recommendation": recommendation,
    }


def diff_pefs(pef_a, pef_b):
    """Compare two PEFs (old=a, new=b) and return structured diff."""
    claims_diff = _diff_claims(
        pef_a.get("claims", []),
        pef_b.get("claims", [])
    )
    api_diff = _diff_api_surface(
        pef_a.get("api_surface", []),
        pef_b.get("api_surface", [])
    )
    formats_diff = _diff_formats(
        pef_a.get("formats", []),
        pef_b.get("formats", [])
    )
    impact = _assess_impact(claims_diff, api_diff, formats_diff)

    family = pef_b.get("family", pef_a.get("family", ""))
    platform = pef_b.get("platform", pef_a.get("platform", ""))

    report = {
        "schema_version": 1,
        "family": family,
        "platform": platform,
        "diffed_at": datetime.now(timezone.utc).isoformat(),
        "old_sha": pef_a.get("source_sha", ""),
        "new_sha": pef_b.get("source_sha", ""),
        "old_materialized_at": pef_a.get("materialized_at", ""),
        "new_materialized_at": pef_b.get("materialized_at", ""),
        "claims": claims_diff,
        "api_surface": api_diff,
        "formats": formats_diff,
        "impact_summary": impact,
    }

    return report


def diff_product(family, platform):
    """Diff pef.json vs pef_previous.json for a product. Returns diff and writes to diffs/."""
    evidence_dir = EVIDENCE_ROOT / family / platform
    pef_path = evidence_dir / "pef.json"
    prev_path = evidence_dir / "pef_previous.json"

    if not pef_path.exists():
        print(f"  SKIP {family}/{platform}: no pef.json")
        return None
    if not prev_path.exists():
        print(f"  SKIP {family}/{platform}: no pef_previous.json (need at least 2 materializations)")
        return None

    pef_new = _read_json(pef_path)
    pef_old = _read_json(prev_path)
    report = diff_pefs(pef_old, pef_new)

    # Write to diffs/
    diffs_dir = evidence_dir / "diffs"
    diffs_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    diff_path = diffs_dir / f"{timestamp}.json"
    diff_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    summary = report["impact_summary"]
    print(f"  {family}/{platform}: severity={summary['severity']}, "
          f"claims +{len(report['claims']['added'])}/-{len(report['claims']['removed'])}, "
          f"api +{len(report['api_surface']['classes_added'])}/-{len(report['api_surface']['classes_removed'])}")
    return report


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python scripts/differ.py {family} {platform}")
        print("  python scripts/differ.py {pef_a.json} {pef_b.json}")
        sys.exit(1)

    if len(sys.argv) == 3 and sys.argv[1].endswith(".json"):
        # Direct file comparison
        pef_a = _read_json(sys.argv[1])
        pef_b = _read_json(sys.argv[2])
        report = diff_pefs(pef_a, pef_b)
        print(json.dumps(report, indent=2))
    elif len(sys.argv) >= 3:
        report = diff_product(sys.argv[1], sys.argv[2])
        if not report:
            sys.exit(1)
    else:
        print("Usage: python scripts/differ.py {family} {platform}")
        sys.exit(1)

    print("EVIDENCE-DIFF: DONE")


if __name__ == "__main__":
    main()
