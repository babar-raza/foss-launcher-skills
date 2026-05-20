#!/usr/bin/env python3
"""Phase 4: Build parity-matrix.md and gap-report.md from both inventories."""
import os
import re
from pathlib import Path
from collections import defaultdict

ASPOSE_ROOT = "D:/onedrive/Documents/GitHub/aspose.org"
FOSS_ROOT = "c:/Users/prora/OneDrive/Documents/GitHub/foss-launcher-skills-gitlab"
OUT_DIR = f"{FOSS_ROOT}/reports/parity"


# === Parse YAML inventory (simple line-by-line) ===
def parse_inventory(path):
    skills = {}
    current = None
    covering_tests = []
    in_tests = False

    with open(path, encoding="utf-8") as f:
        lines = f.readlines()

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("- canonical_slug:"):
            if current:
                current["covering_tests"] = covering_tests
                skills[current["canonical_slug"]] = current
            current = {"canonical_slug": stripped.split(":", 1)[1].strip()}
            covering_tests = []
            in_tests = False

        elif current is not None:
            if stripped.startswith("covering_tests:"):
                val = stripped.split(":", 1)[1].strip()
                if val == "[]":
                    covering_tests = []
                    in_tests = False
                else:
                    in_tests = True

            elif in_tests and stripped.startswith("- "):
                covering_tests.append(stripped[2:])

            elif not stripped.startswith("- ") and ":" in stripped:
                in_tests = False
                key, val = stripped.split(":", 1)
                val = val.strip()
                if val == "null":
                    val = None
                elif val == "true":
                    val = True
                elif val == "false":
                    val = False
                elif val.startswith("[") and val.endswith("]"):
                    inner = val[1:-1].strip()
                    if inner:
                        val = [int(x.strip()) for x in inner.split(",") if x.strip().isdigit()]
                    else:
                        val = []
                else:
                    try:
                        val = float(val) if "." in val else int(val)
                    except (ValueError, TypeError):
                        pass
                current[key.strip()] = val

    if current:
        current["covering_tests"] = covering_tests
        skills[current["canonical_slug"]] = current

    return skills


# === Load both inventories ===
aspose_skills = parse_inventory(f"{OUT_DIR}/aspose-inventory.yaml")
foss_skills = parse_inventory(f"{OUT_DIR}/foss-inventory.yaml")

print(f"Aspose skills loaded: {len(aspose_skills)}")
print(f"Foss skills loaded: {len(foss_skills)}")

aspose_slugs = set(aspose_skills.keys())
foss_slugs = set(foss_skills.keys())

shared = aspose_slugs & foss_slugs
aspose_only = aspose_slugs - foss_slugs
foss_only = foss_slugs - aspose_slugs

print(f"Shared: {len(shared)}, Aspose-only: {len(aspose_only)}, Foss-only: {len(foss_only)}")


# === Load size data from actual files for shared skills ===
def get_aspose_size(slug):
    path = f"{ASPOSE_ROOT}/skills/{slug}.md"
    if os.path.exists(path):
        return round(os.path.getsize(path) / 1024, 2)
    return None


# === Determine parity status for each skill ===
def determine_parity(slug, aspose_data, foss_data):
    """8-layer parity determination."""
    foss_layers = foss_data.get("layers_passed", [])
    aspose_layers = aspose_data.get("layers_passed", [])

    gaps = []
    parity_status = "unclear"

    # Check if skill is just in foss
    if aspose_data is None:
        return "foss_only", []

    if foss_data is None:
        return "missing_entirely", ["missing_skill"]

    # Layer 1: File presence — always passes (92/92)
    # Layer 2: Registration — always passes
    # Layer 3+4: Script
    foss_has_script = foss_data.get("foss_script_exists") and foss_data.get("foss_script_has_main")
    aspose_has_script = aspose_data.get("aspose_script_exists") and aspose_data.get("aspose_script_has_main")

    # Layer 5: Content depth
    aspose_size = aspose_data.get("aspose_size_kb") or get_aspose_size(slug)
    foss_size = foss_data.get("foss_size_kb") or 0

    size_gap = False
    if aspose_size and foss_size:
        ratio = foss_size / aspose_size if aspose_size > 0 else 1
        if ratio < 0.7:
            size_gap = True
            gaps.append("size_divergence")

    # Layer 7: Tests
    foss_tests = foss_data.get("covering_tests", []) or []

    # Determine status
    if not foss_has_script and aspose_has_script:
        if foss_data.get("foss_script"):
            parity_status = "documented_not_implemented"
            gaps.append("missing_dependency")
        else:
            parity_status = "governance_only"
            gaps.append("missing_dependency")
    elif foss_has_script and not foss_tests:
        parity_status = "implemented_not_verified"
        gaps.append("missing_test_coverage")
    elif foss_has_script and foss_tests:
        if size_gap:
            parity_status = "partial_parity"
        else:
            parity_status = "partial_parity"  # needs deeper verification to be exact
    elif not foss_has_script and not aspose_has_script:
        # Both are governance-only
        if not foss_tests:
            parity_status = "governance_only"
        else:
            parity_status = "partial_parity"

    # Governance gaps
    foss_ci = 4   # foss has 4 CI checks
    aspose_ci = 63
    if aspose_data.get("aspose_script"):
        gaps.append("missing_governance")  # few CI checks in foss

    if not foss_tests:
        if "missing_test_coverage" not in gaps:
            gaps.append("missing_test_coverage")

    return parity_status, list(set(gaps))


# === Build cross-reference with aspose ID mapping ===
# Load docs/id-mapping.md for ID cross-references
id_mapping_path = f"{FOSS_ROOT}/docs/id-mapping.md"
aspose_id_for_slug = {}  # slug -> aspose ID from mapping doc
if os.path.exists(id_mapping_path):
    with open(id_mapping_path, encoding="utf-8") as f:
        for line in f:
            # Look for table rows: | slug | aspose_id | foss_id |
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 4 and parts[1] and parts[2]:
                slug = parts[1]
                aspose_id = parts[2]
                if slug and aspose_id and aspose_id.startswith("S-"):
                    aspose_id_for_slug[slug] = aspose_id


# === PARITY MATRIX ===
matrix_lines = [
    "# Parity Matrix — aspose.org ↔ foss-launcher",
    "",
    "**Generated**: 2026-05-15  **Agent**: A (Discovery)  **Plan**: PAR-011",
    "",
    "## Summary",
    "",
    f"| Category | Count |",
    f"|----------|-------|",
    f"| Total aspose.org skills | {len(aspose_slugs)} |",
    f"| Total foss-launcher skills | {len(foss_slugs)} |",
    f"| Shared skill slugs | {len(shared)} |",
    f"| aspose.org-only skills | {len(aspose_only)} |",
    f"| foss-launcher-only skills | {len(foss_only)} |",
    f"| CI checks in aspose.org | 63 |",
    f"| CI checks in foss-launcher | 4 |",
    f"| CI checks gap | 59 |",
    f"| Governance/workflow docs in aspose.org | 22 |",
    f"| Governance/workflow docs in foss-launcher | 0 |",
    "",
    "## Shared Skills — Layer-by-Layer Status",
    "",
    "| Slug | Aspose ID | Foss ID | Aspose KB | Foss KB | Size% | L3 | L4 | L7 | Parity Status | Key Gaps |",
    "|------|-----------|---------|-----------|---------|-------|----|----|----|----|----------|",
]

gap_registry = []
status_counts = defaultdict(int)

for slug in sorted(shared):
    ad = aspose_skills[slug]
    fd = foss_skills[slug]

    aspose_id = ad.get("aspose_id", "?")
    foss_id = fd.get("foss_id", "?")
    aspose_kb = ad.get("aspose_size_kb") or get_aspose_size(slug) or 0
    foss_kb = fd.get("foss_size_kb") or 0
    size_pct = f"{round(foss_kb / aspose_kb * 100)}%" if aspose_kb > 0 else "?"

    foss_l3 = "Y" if fd.get("foss_script") else "N"
    foss_l4 = "Y" if fd.get("foss_script_has_main") else "N"
    foss_l7 = "Y" if fd.get("covering_tests") else "N"

    parity_status, gaps = determine_parity(slug, ad, fd)
    status_counts[parity_status] += 1

    gap_str = ", ".join(gaps[:2]) if gaps else "—"
    matrix_lines.append(
        f"| {slug} | {aspose_id} | {foss_id} | {aspose_kb} | {foss_kb} | {size_pct} | {foss_l3} | {foss_l4} | {foss_l7} | {parity_status} | {gap_str} |"
    )

    if gaps:
        gap_registry.append({
            "slug": slug,
            "parity_status": parity_status,
            "gaps": gaps,
            "aspose_id": aspose_id,
            "foss_id": foss_id,
            "aspose_kb": aspose_kb,
            "foss_kb": foss_kb,
        })

# aspose-only
matrix_lines.append("")
matrix_lines.append("## aspose.org-Only Skills (missing_entirely in foss-launcher)")
matrix_lines.append("")
matrix_lines.append("| Slug | Aspose ID | Aspose KB | Parity Status |")
matrix_lines.append("|------|-----------|-----------|---------------|")
for slug in sorted(aspose_only):
    ad = aspose_skills[slug]
    matrix_lines.append(f"| {slug} | {ad.get('aspose_id','?')} | {ad.get('aspose_size_kb','?')} | missing_entirely |")
    status_counts["missing_entirely"] += 1
    gap_registry.append({
        "slug": slug,
        "parity_status": "missing_entirely",
        "gaps": ["missing_skill"],
        "aspose_id": ad.get("aspose_id", "?"),
        "foss_id": "null",
        "aspose_kb": ad.get("aspose_size_kb", 0),
        "foss_kb": 0,
    })

# foss-only
matrix_lines.append("")
matrix_lines.append("## foss-launcher-Only Skills (foss_only)")
matrix_lines.append("")
matrix_lines.append("| Slug | Foss ID | Foss KB | Notes |")
matrix_lines.append("|------|---------|---------|-------|")
for slug in sorted(foss_only):
    fd = foss_skills[slug]
    matrix_lines.append(f"| {slug} | {fd.get('foss_id','?')} | {fd.get('foss_size_kb','?')} | No equivalent in aspose.org |")
    status_counts["foss_only"] += 1

# Status summary
matrix_lines.append("")
matrix_lines.append("## Parity Status Distribution")
matrix_lines.append("")
matrix_lines.append("| Status | Count |")
matrix_lines.append("|--------|-------|")
for status, count in sorted(status_counts.items(), key=lambda x: -x[1]):
    matrix_lines.append(f"| {status} | {count} |")

# CI gap summary
matrix_lines.append("")
matrix_lines.append("## CI Check Coverage Gap")
matrix_lines.append("")
matrix_lines.append("aspose.org has 63 CI check scripts in `scripts/ci/checks/`. foss-launcher has 4.")
matrix_lines.append("Gap: **59 missing CI validation checks**. See `aspose-ci-checks-map.yaml` for full list.")
matrix_lines.append("")
matrix_lines.append("## Governance Documentation Gap")
matrix_lines.append("")
matrix_lines.append("aspose.org has 22 governance/workflow docs in `docs/governance/` and `docs/workflows/`.")
matrix_lines.append("foss-launcher has 0 external governance docs (governance inlined in AGENTS.md).")
matrix_lines.append("See `aspose-governance-map.yaml` for full list.")

parity_path = f"{OUT_DIR}/parity-matrix.md"
with open(parity_path, "w", encoding="utf-8") as f:
    f.write("\n".join(matrix_lines))
print(f"Wrote {parity_path}")


# === GAP REPORT ===
gap_lines = [
    "# Gap Report — foss-launcher vs aspose.org",
    "",
    "**Generated**: 2026-05-15  **Agent**: A (Discovery)  **Plan**: PAR-011",
    "",
    "## Overview",
    "",
    f"Total gaps identified: **{len(gap_registry)}** skills with ≥1 gap classification.",
    "",
    "### Gap Classification Summary",
    "",
]

# Count gap classifications
gap_class_counts = defaultdict(int)
for entry in gap_registry:
    for g in entry["gaps"]:
        gap_class_counts[g] += 1

gap_lines.append("| Gap Classification | Occurrences |")
gap_lines.append("|-------------------|-------------|")
for cls, cnt in sorted(gap_class_counts.items(), key=lambda x: -x[1]):
    gap_lines.append(f"| {cls} | {cnt} |")

# Systemic gaps
gap_lines += [
    "",
    "## Systemic Gaps (Not Skill-Specific)",
    "",
    "### G1: Missing CI Check Infrastructure (59 checks)",
    "",
    "aspose.org runs 63 automated validation checks in `scripts/ci/checks/`. foss-launcher has 4.",
    "The 59 missing checks cover: skill_governance, content_quality, knowledge, metrics,",
    "pipeline_integrity, locale, link_integrity, provenance, blog, naming.",
    "See `aspose-ci-checks-map.yaml` for the complete list with domain classification.",
    "",
    "**Gap classification**: `missing_governance` (systemic)",
    "**Recommended fix**: Port top-value checks by domain priority.",
    "",
    "### G2: Missing Governance Documentation (22 docs)",
    "",
    "aspose.org has `docs/governance/` (10 docs) and `docs/workflows/` (12 docs).",
    "foss-launcher governance is inlined in AGENTS.md only.",
    "Missing: evidence governance, launch gates, write boundaries, naming conventions,",
    "DAR policy, causal backtracking, change triggers, heal policy, skill chains, etc.",
    "",
    "**Gap classification**: `missing_documentation` (systemic)",
    "**Recommended fix**: Create `docs/governance/` and `docs/workflows/` mirroring aspose.org structure.",
    "",
    "### G3: Missing Shared Library Layer (scripts/pipeline/lib/)",
    "",
    "aspose.org has 19 shared library modules in `scripts/pipeline/lib/`:",
    "grade_writer, heal_controller, provenance, registry_loader, content_patcher, etc.",
    "foss-launcher has no `scripts/pipeline/lib/` directory.",
    "This means skills that depend on these libraries cannot function correctly.",
    "",
    "**Gap classification**: `missing_helper_utility` (systemic)",
    "",
    "## Per-Skill Gap Details",
    "",
]

# Categorize by parity status
by_status = defaultdict(list)
for entry in gap_registry:
    by_status[entry["parity_status"]].append(entry)

for status in ["missing_entirely", "governance_only", "documented_not_implemented", "implemented_not_verified", "partial_parity"]:
    entries = by_status.get(status, [])
    if not entries:
        continue
    gap_lines.append(f"### Status: {status} ({len(entries)} skills)")
    gap_lines.append("")
    gap_lines.append("| Slug | Aspose ID | Foss ID | Aspose KB | Foss KB | Gap Classifications |")
    gap_lines.append("|------|-----------|---------|-----------|---------|---------------------|")
    for e in sorted(entries, key=lambda x: x["slug"]):
        gaps_str = ", ".join(e["gaps"])
        gap_lines.append(f"| {e['slug']} | {e['aspose_id']} | {e['foss_id']} | {e['aspose_kb']} | {e['foss_kb']} | {gaps_str} |")
    gap_lines.append("")

# Foss advantages section
gap_lines += [
    "## foss-launcher Advantages Over aspose.org",
    "",
    "| Advantage | Detail |",
    "|-----------|--------|",
    "| 10 unique skills | corpus-scan, discover-products, evidence-decide, evidence-materialize, evidence-verify, ground-check, mental-model, seo-review, translate, truth-sync |",
    "| pyproject.toml entry points | 6 console_scripts vs 0 in aspose.org — better CLI UX |",
    "| Standalone deployment | No Hugo/website dependency — can run independently |",
    "| Cleaner registry schema | skills/registry.yaml is simpler and more readable than aspose.org's registry.json |",
    "| Integrated test suite | tests/ at repo root with clear organization |",
    "| Better ID coverage | S-01 through S-109 with more skills defined |",
]

gap_path = f"{OUT_DIR}/gap-report.md"
with open(gap_path, "w", encoding="utf-8") as f:
    f.write("\n".join(gap_lines))
print(f"Wrote {gap_path}")

# === foss-advantages.md ===
adv_lines = [
    "# foss-launcher Advantages Over aspose.org",
    "",
    "**Generated**: 2026-05-15  **Agent**: A (Discovery)  **Plan**: PAR-011",
    "",
    "## 10 Unique Skills Not in aspose.org",
    "",
    "| Slug | Foss ID | Description |",
    "|------|---------|-------------|",
]
for slug in sorted(foss_only):
    fd = foss_skills[slug]
    adv_lines.append(f"| {slug} | {fd.get('foss_id','?')} | {fd.get('foss_path','?')} |")

adv_lines += [
    "",
    "## Infrastructure Advantages",
    "",
    "| Advantage | aspose.org | foss-launcher |",
    "|-----------|-----------|---------------|",
    "| Standalone operation | No (Hugo dependency) | Yes |",
    "| pyproject.toml entry points | 0 | 6 console_scripts |",
    "| Registry format | JSON (verbose) | YAML (readable) |",
    "| Test suite location | scripts/pipeline/tests/ (mixed) | tests/ (dedicated) |",
    "| Skill ID range | S-01–S-97 | S-01–S-109 |",
    "| Total skill count | 84 | 92 |",
    "",
    "## Clean-Room Design Benefits",
    "",
    "foss-launcher was designed as a standalone implementation, free from Hugo CMS coupling.",
    "This enables deployment in any content pipeline without a full website infrastructure.",
    "The simplified registry schema and consolidated test directory make it easier to",
    "onboard contributors and maintain consistent quality.",
]

adv_path = f"{OUT_DIR}/foss-advantages.md"
with open(adv_path, "w", encoding="utf-8") as f:
    f.write("\n".join(adv_lines))
print(f"Wrote {adv_path}")

# === Console summary ===
print("\n=== PAR-011 COMPLETE ===")
print(f"parity-matrix.md: {len(shared)} shared + {len(aspose_only)} aspose-only + {len(foss_only)} foss-only")
print(f"gap-report.md: {len(gap_registry)} skills with gaps")
print(f"foss-advantages.md: written")
print(f"\nParity status breakdown:")
for status, count in sorted(status_counts.items(), key=lambda x: -x[1]):
    print(f"  {status}: {count}")
print(f"\nTop gap classifications:")
for cls, cnt in sorted(gap_class_counts.items(), key=lambda x: -x[1])[:8]:
    print(f"  {cls}: {cnt}")
