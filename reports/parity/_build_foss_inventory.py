#!/usr/bin/env python3
"""Build reports/parity/foss-inventory.yaml and foss-test-coverage-map.yaml"""
import os
import sys
from pathlib import Path
from collections import defaultdict

FOSS_ROOT = "c:/Users/prora/OneDrive/Documents/GitHub/foss-launcher-skills-gitlab"
OUT_DIR = f"{FOSS_ROOT}/reports/parity"

os.makedirs(OUT_DIR, exist_ok=True)

# === 1. Parse registry.yaml ===
registry_path = f"{FOSS_ROOT}/skills/registry.yaml"
with open(registry_path, encoding="utf-8") as f:
    lines = f.readlines()

skills_dict = {}  # slug -> dict
i = 0
current = None

while i < len(lines):
    stripped = lines[i].strip()

    if stripped.startswith("- id:"):
        if current and "slug" in current:
            skills_dict[current["slug"]] = current
        current = {"foss_id": stripped[5:].strip()}

    elif current is not None:
        if stripped.startswith("name:"):
            current["slug"] = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("description:"):
            current["description"] = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("internal:"):
            current["internal"] = stripped.split(":", 1)[1].strip().lower() == "true"
        elif stripped.startswith("script:"):
            val = stripped.split(":", 1)[1].strip()
            current["script"] = None if val == "null" else val

    i += 1

if current and "slug" in current:
    skills_dict[current["slug"]] = current

print(f"Parsed {len(skills_dict)} skills from registry.yaml")

# === 2. File sizes ===
skills_dir = Path(f"{FOSS_ROOT}/skills")
for slug, data in skills_dict.items():
    p = skills_dir / f"{slug}.md"
    data["file_exists"] = p.exists()
    data["size_kb"] = round(p.stat().st_size / 1024, 2) if p.exists() else None

# === 3. Script existence + main() ===
for slug, data in skills_dict.items():
    script = data.get("script")
    if script:
        sp = Path(f"{FOSS_ROOT}/{script}")
        data["script_exists"] = sp.exists()
        data["script_has_main"] = False
        if sp.exists():
            try:
                content = sp.read_text(encoding="utf-8", errors="ignore")
                data["script_has_main"] = "def main(" in content
            except Exception:
                pass
    else:
        data["script_exists"] = False
        data["script_has_main"] = False

# === 4. Test coverage mapping ===
test_dir = Path(f"{FOSS_ROOT}/tests")
test_files = sorted(test_dir.glob("test_*.py"))

slug_to_tests = defaultdict(set)
test_to_slugs = defaultdict(set)

for tf in test_files:
    try:
        content = tf.read_text(encoding="utf-8", errors="ignore")
        for slug in skills_dict:
            if slug in content or slug.replace("-", "_") in content:
                slug_to_tests[slug].add(tf.name)
                test_to_slugs[tf.name].add(slug)
    except Exception:
        pass

print(f"Test files scanned: {len(test_files)}")
print(f"Skills with test coverage: {len(slug_to_tests)}")

# === 5. Layer calculation ===
def calc_layers(slug, data, slug_to_tests):
    layers = []
    if data.get("file_exists"):
        layers.append(1)
    layers.append(2)  # always registered
    if data.get("script"):
        layers.append(3)
    if data.get("script_exists") and data.get("script_has_main"):
        layers.append(4)
    if data.get("size_kb", 0) and data["size_kb"] >= 1:
        layers.append(5)
    # Layer 6: dependencies available
    if data.get("script"):
        if data.get("script_exists"):
            layers.append(6)
    else:
        layers.append(6)  # no script dep needed
    if slug in slug_to_tests:
        layers.append(7)
    # Layer 8: non-destructive (internal or audit/verify/check)
    if data.get("internal") or any(k in slug for k in ["audit", "verify", "check", "validate", "diagnose", "review"]):
        layers.append(8)
    return sorted(set(layers))

# === 6. Build inventory YAML ===
inv_lines = [
    "# reports/parity/foss-inventory.yaml",
    "# Generated 2026-05-15 — PAR-010",
    f"# {len(skills_dict)} foss-launcher skills",
    "",
    "skills:",
]

# Sort by numeric ID
def sort_key(item):
    slug, data = item
    fid = data.get("foss_id", "S-999")
    try:
        return int(fid.split("-")[1])
    except Exception:
        return 999

for slug, data in sorted(skills_dict.items(), key=sort_key):
    layers = calc_layers(slug, data, slug_to_tests)
    tests = sorted(slug_to_tests.get(slug, set()))

    # parity_status heuristic
    if data.get("script_exists") and data.get("script_has_main") and len(tests) > 0:
        ps = "implemented_not_verified"  # needs cross-check with aspose
    elif data.get("script_exists") and data.get("script_has_main"):
        ps = "implemented_not_verified"
    elif data.get("script") and not data.get("script_exists"):
        ps = "documented_not_implemented"
    elif not data.get("script"):
        ps = "governance_only"
    else:
        ps = "unclear"

    inv_lines.append(f"  - canonical_slug: {slug}")
    inv_lines.append(f"    foss_id: {data.get('foss_id', 'null')}")
    inv_lines.append(f"    foss_path: skills/{slug}.md")
    inv_lines.append(f"    foss_size_kb: {data.get('size_kb')}")
    inv_lines.append(f"    foss_script: {data.get('script') or 'null'}")
    inv_lines.append(f"    foss_script_exists: {str(data.get('script_exists', False)).lower()}")
    inv_lines.append(f"    foss_script_has_main: {str(data.get('script_has_main', False)).lower()}")
    inv_lines.append(f"    internal: {str(data.get('internal', False)).lower()}")
    inv_lines.append(f"    layers_passed: {layers}")
    inv_lines.append(f"    parity_status: {ps}")
    if tests:
        inv_lines.append(f"    covering_tests:")
        for t in tests:
            inv_lines.append(f"      - {t}")
    else:
        inv_lines.append(f"    covering_tests: []")
    inv_lines.append(f"    notes: null")
    inv_lines.append("")

out1 = f"{OUT_DIR}/foss-inventory.yaml"
with open(out1, "w", encoding="utf-8") as f:
    f.write("\n".join(inv_lines))
print(f"Wrote {out1}")

# === 7. Test coverage map ===
cov_lines = [
    "# reports/parity/foss-test-coverage-map.yaml",
    "# Generated 2026-05-15 — PAR-010",
    f"# {len(test_files)} test files mapped",
    "",
    "test_files:",
]

for tf in test_files:
    slugs = sorted(test_to_slugs.get(tf.name, set()))
    cov_lines.append(f"  - filename: {tf.name}")
    if slugs:
        cov_lines.append(f"    covers_skills:")
        for s in slugs:
            cov_lines.append(f"      - {s}")
    else:
        cov_lines.append(f"    covers_skills: []")
    cov_lines.append("")

out2 = f"{OUT_DIR}/foss-test-coverage-map.yaml"
with open(out2, "w", encoding="utf-8") as f:
    f.write("\n".join(cov_lines))
print(f"Wrote {out2}")

# === 8. Summary ===
all_layers = [calc_layers(slug, data, slug_to_tests) for slug, data in skills_dict.items()]
print("\n=== PAR-010 COMPLETE ===")
print(f"foss-inventory.yaml: {len(skills_dict)} entries")
print(f"foss-test-coverage-map.yaml: {len(test_files)} test files")
print(f"\nLayer stats:")
for L in range(1, 9):
    count = sum(1 for ls in all_layers if L in ls)
    print(f"  Layer {L}: {count}/{len(skills_dict)}")

# Status breakdown
status_counts = defaultdict(int)
for slug, data in skills_dict.items():
    layers = calc_layers(slug, data, slug_to_tests)
    if data.get("script_exists") and data.get("script_has_main"):
        status_counts["has_script_with_main"] += 1
    elif data.get("script") and not data.get("script_exists"):
        status_counts["script_missing"] += 1
    elif not data.get("script"):
        status_counts["no_script_registered"] += 1
    else:
        status_counts["other"] += 1

print(f"\nScript status:")
for k, v in sorted(status_counts.items()):
    print(f"  {k}: {v}")
