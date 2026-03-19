"""Evidence Materializer — aggregate knowledge artifacts into a canonical PEF.

Usage:
    python scripts/materialize.py {family} {platform}   # Single product
    python scripts/materialize.py all                     # All discovered products
"""
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

KNOWLEDGE_ROOT = Path("knowledge")
EVIDENCE_ROOT = Path("evidence")


def _display_name(family):
    special = {"3d": "3D"}
    return f"Aspose.{special.get(family, family.title())}"


def _parse_limitations_md(path):
    """Parse limitations.md table into list of limitation strings."""
    limitations = []
    if not path.exists():
        return limitations
    for line in path.read_text(encoding="utf-8").splitlines():
        if "|" not in line or "---" in line:
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) >= 5 and parts[3] and parts[3] != "Class" and parts[3] != "Limitations":
            entry = f"{parts[3]}.{parts[4]}" if parts[4] else parts[3]
            if entry.strip():
                limitations.append(entry)
    return limitations


def _read_json(path, default=None):
    if default is None:
        default = []
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _read_yaml(path):
    if not path.exists():
        return {}
    import yaml
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _read_text(path):
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _install_command(family, platform, version=""):
    pkg = f"aspose-{family}-foss"
    if platform == "python":
        return f"pip install {pkg}"
    elif platform == "typescript":
        return f"npm install {pkg}"
    elif platform == "dotnet":
        return f"dotnet add package {pkg.replace('-', '.')}"
    return f"pip install {pkg}"


def _list_snippets(merged_dir):
    snippets_dir = merged_dir / "snippets"
    if not snippets_dir.exists():
        return []
    return [
        {"filename": f.name, "path": str(f.relative_to(merged_dir))}
        for f in sorted(snippets_dir.iterdir())
        if f.is_file()
    ]


def _compute_provenance_summary(claims):
    counts = {}
    for c in claims:
        p = c.get("provenance", "unknown")
        counts[p] = counts.get(p, 0) + 1
    dual = counts.get("dual", 0)
    dual_fuzzy = counts.get("dual_fuzzy", 0)
    scout_only = counts.get("scout_only", 0)
    external_only = counts.get("external_only", 0)
    total = len(claims)
    dual_pct = round((dual + dual_fuzzy) / total * 100, 1) if total > 0 else 0.0
    return {
        "dual": dual,
        "dual_fuzzy": dual_fuzzy,
        "scout_only": scout_only,
        "external_only": external_only,
        "total": total,
        "dual_pct": dual_pct,
    }


def _compute_api_confidence(prov_summary):
    dual_pct = prov_summary["dual_pct"]
    if dual_pct > 50:
        return "high"
    elif dual_pct > 20:
        return "medium"
    return "low"


def _rotate_previous(evidence_dir):
    """Move current pef.json to pef_previous.json before writing new one."""
    pef_path = evidence_dir / "pef.json"
    if pef_path.exists():
        prev_path = evidence_dir / "pef_previous.json"
        shutil.copy2(str(pef_path), str(prev_path))


def _hash_pef(pef):
    """Compute a stable hash of the PEF for cache invalidation."""
    content = json.dumps(pef, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def _append_changelog(evidence_dir, pef, previous):
    """Append entry to changelog.json with timestamp and summary of changes."""
    changelog_path = evidence_dir / "changelog.json"
    entries = _read_json(changelog_path, default=[])

    entry = {
        "timestamp": pef["materialized_at"],
        "source_sha": pef["source_sha"],
        "claims_total": pef["provenance_summary"]["total"],
        "api_confidence": pef["api_confidence"],
    }

    if previous:
        old_claims = {c.get("claim_id", i): c for i, c in enumerate(previous.get("claims", []))}
        new_claims = {c.get("claim_id", i): c for i, c in enumerate(pef.get("claims", []))}
        added = len(set(new_claims) - set(old_claims))
        removed = len(set(old_claims) - set(new_claims))
        entry["delta"] = {"claims_added": added, "claims_removed": removed}
        entry["previous_sha"] = previous.get("source_sha", "")
    else:
        entry["delta"] = None

    entries.append(entry)
    changelog_path.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")


def materialize(family, platform):
    """Build and write PEF for a single family/platform. Returns PEF dict."""
    merged_dir = KNOWLEDGE_ROOT / family / platform / "merged"

    if not merged_dir.exists():
        print(f"  SKIP {family}/{platform}: no merged/ directory")
        return None

    model = _read_yaml(merged_dir / "model.yaml")
    if not model:
        print(f"  SKIP {family}/{platform}: no model.yaml")
        return None

    claims = _read_json(merged_dir / "claims.json")
    api_surface = _read_json(merged_dir / "api_surface.json")
    formats = _read_json(merged_dir / "formats.json")
    class_graph = _read_json(merged_dir / "class_graph.json", default=[])
    coverage_matrix = _read_json(merged_dir / "coverage_matrix.json", default=[])
    constants = _read_json(merged_dir / "constants.json")
    limitations = _parse_limitations_md(merged_dir / "limitations.md")
    install_md = _read_text(merged_dir / "install.md")
    index_metadata = _read_json(merged_dir / "index.json", default={})
    snippets = _list_snippets(merged_dir)

    prov_summary = _compute_provenance_summary(claims)
    api_confidence = _compute_api_confidence(prov_summary)

    # Build forbidden claims from limitations
    forbidden = [f"supports {l}" for l in limitations if l.strip()]

    pef = {
        "schema_version": 1,
        "family": family,
        "platform": platform,
        "display_name": _display_name(family),
        "materialized_at": datetime.now(timezone.utc).isoformat(),
        "source_sha": model.get("repo_sha", ""),
        "provenance_summary": prov_summary,
        "api_confidence": api_confidence,
        "claims": claims,
        "api_surface": api_surface,
        "formats": formats,
        "class_graph": class_graph,
        "coverage_matrix": coverage_matrix,
        "constants": constants,
        "limitations": limitations,
        "install": {
            "command": model.get("install_command", _install_command(family, platform)),
            "version": model.get("version", ""),
            "raw_md": install_md,
        },
        "snippets": snippets,
        "forbidden_claims": forbidden,
        "index_metadata": index_metadata if isinstance(index_metadata, dict) else {},
    }

    # Write to evidence directory
    evidence_dir = EVIDENCE_ROOT / family / platform
    evidence_dir.mkdir(parents=True, exist_ok=True)

    # Load previous for changelog before rotating
    prev_pef_path = evidence_dir / "pef.json"
    previous = _read_json(prev_pef_path, default=None) if prev_pef_path.exists() else None

    _rotate_previous(evidence_dir)

    pef_path = evidence_dir / "pef.json"
    pef_path.write_text(json.dumps(pef, indent=2, ensure_ascii=False), encoding="utf-8")

    _append_changelog(evidence_dir, pef, previous)

    print(f"  {family}/{platform}: {prov_summary['total']} claims, "
          f"confidence={api_confidence}, sha={pef['source_sha'][:8]}")
    return pef


def discover_products():
    """Find all family/platform combinations with merged knowledge."""
    products = []
    if not KNOWLEDGE_ROOT.exists():
        return products
    for family_dir in sorted(KNOWLEDGE_ROOT.iterdir()):
        if not family_dir.is_dir() or family_dir.name.startswith("_"):
            continue
        for platform_dir in sorted(family_dir.iterdir()):
            if not platform_dir.is_dir():
                continue
            if (platform_dir / "merged" / "model.yaml").exists():
                products.append((family_dir.name, platform_dir.name))
    return products


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python scripts/materialize.py {family} {platform}")
        print("  python scripts/materialize.py all")
        sys.exit(1)

    if sys.argv[1] == "all":
        products = discover_products()
        if not products:
            print("No products found with merged knowledge.")
            sys.exit(1)
        print(f"Materializing {len(products)} products:")
        for family, platform in products:
            materialize(family, platform)
    else:
        if len(sys.argv) < 3:
            print("Usage: python scripts/materialize.py {family} {platform}")
            sys.exit(1)
        family = sys.argv[1]
        platform = sys.argv[2]
        result = materialize(family, platform)
        if not result:
            sys.exit(1)

    print("EVIDENCE-MATERIALIZE: PASS")


if __name__ == "__main__":
    main()
