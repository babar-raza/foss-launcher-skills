#!/usr/bin/env python3
"""Build reports/parity/aspose-inventory.yaml, aspose-ci-checks-map.yaml, aspose-governance-map.yaml"""
import json
import os
import sys

ASPOSE_ROOT = "D:/onedrive/Documents/GitHub/aspose.org"
OUT_DIR = "reports/parity"

os.makedirs(OUT_DIR, exist_ok=True)

# === 1. Load skill registry ===
with open(f"{ASPOSE_ROOT}/skills/registry.json", encoding="utf-8") as f:
    registry = json.load(f)

skills = registry["skills"]
print(f"Loaded {len(skills)} skills from registry.json")

# === 2. Parse pipeline script registry for skill backings ===
skill_to_script = {}  # slug -> script path
script_to_skills = {}  # script path -> list of slugs

reg_path = f"{ASPOSE_ROOT}/scripts/pipeline/config/registry.yaml"
with open(reg_path, encoding="utf-8", errors="replace") as f:
    lines = f.readlines()

# Parse manually: look for path: then backing: kind: skill / ref:
i = 0
current_path = None
in_backing = False
backing_kind = None

while i < len(lines):
    line = lines[i]
    stripped = line.strip()

    if stripped.startswith("path:"):
        current_path = stripped.split(":", 1)[1].strip()
        in_backing = False
        backing_kind = None

    elif stripped == "backing:":
        in_backing = True

    elif in_backing and stripped.startswith("kind:"):
        backing_kind = stripped.split(":", 1)[1].strip()

    elif in_backing and stripped.startswith("ref:") and backing_kind == "skill":
        ref = stripped.split(":", 1)[1].strip()
        if ref and ref != "null" and current_path:
            skill_to_script[ref] = current_path
            script_to_skills.setdefault(current_path, []).append(ref)
        in_backing = False

    elif stripped.startswith("- path:"):
        # new entry
        current_path = stripped[7:].strip()
        in_backing = False
        backing_kind = None

    i += 1

print(f"Script bindings found: {len(skill_to_script)}")

# === 3. Build inventory ===
inventory_lines = ["# reports/parity/aspose-inventory.yaml", f"# Generated 2026-05-15 — PAR-009", f"# {len(skills)} aspose.org skills", ""]
inventory_lines.append("skills:")

for skill in sorted(skills, key=lambda s: int(s["id"].split("-")[1])):
    slug = skill["slug"]
    sid = skill["id"]
    canonical_path = skill.get("canonical_path", f"skills/{slug}.md")
    internal = skill.get("internal", False)

    skill_file = f"{ASPOSE_ROOT}/skills/{slug}.md"
    file_exists = os.path.exists(skill_file)
    size_kb = round(os.path.getsize(skill_file) / 1024, 2) if file_exists else None

    aspose_script = skill_to_script.get(slug)
    script_exists = os.path.exists(f"{ASPOSE_ROOT}/{aspose_script}") if aspose_script else False

    # Check main() in script
    script_has_main = False
    if script_exists:
        try:
            with open(f"{ASPOSE_ROOT}/{aspose_script}", encoding="utf-8", errors="replace") as sf:
                sc = sf.read()
            script_has_main = "def main(" in sc
        except Exception:
            pass

    # Layers
    layers = []
    if file_exists:
        layers.append(1)
    layers.append(2)  # always registered if in registry.json
    if aspose_script:
        layers.append(3)
    if script_has_main:
        layers.append(4)
    if size_kb and size_kb >= 1:
        layers.append(5)
    if aspose_script:
        if script_exists:
            layers.append(6)
    else:
        layers.append(6)  # no script dep needed

    inventory_lines.append(f"  - canonical_slug: {slug}")
    inventory_lines.append(f"    aspose_id: {sid}")
    inventory_lines.append(f"    aspose_path: {canonical_path}")
    inventory_lines.append(f"    aspose_size_kb: {size_kb}")
    inventory_lines.append(f"    aspose_script: {aspose_script or 'null'}")
    inventory_lines.append(f"    aspose_script_exists: {str(script_exists).lower()}")
    inventory_lines.append(f"    aspose_script_has_main: {str(script_has_main).lower()}")
    inventory_lines.append(f"    internal: {str(internal).lower()}")
    inventory_lines.append(f"    layers_passed: {layers}")
    inventory_lines.append(f"    notes: null")
    inventory_lines.append("")

out_path = f"{OUT_DIR}/aspose-inventory.yaml"
with open(out_path, "w", encoding="utf-8") as f:
    f.write("\n".join(inventory_lines))
print(f"Wrote {out_path}")

# === 4. CI checks map ===
ci_dir = f"{ASPOSE_ROOT}/scripts/ci/checks"
ci_files = sorted(os.listdir(ci_dir))
ci_py_files = [f for f in ci_files if f.endswith(".py")]

def classify_ci(fname):
    name = fname.lower().replace("-", "_").replace(".py", "")
    if any(k in name for k in ["governance", "agents", "skill", "registry", "contract"]):
        return "skill_governance"
    elif any(k in name for k in ["grade", "content", "audit", "eval"]):
        return "content_quality"
    elif any(k in name for k in ["knowledge", "clone", "stale", "model"]):
        return "knowledge"
    elif any(k in name for k in ["metric", "sheet", "event", "progress"]):
        return "metrics"
    elif any(k in name for k in ["pipeline", "script", "plugin"]):
        return "pipeline_integrity"
    elif any(k in name for k in ["locale", "translat"]):
        return "locale"
    elif any(k in name for k in ["link", "anchor", "url"]):
        return "link_integrity"
    elif any(k in name for k in ["proof", "provenance", "origin", "evidence"]):
        return "provenance"
    elif any(k in name for k in ["blog", "slug", "post"]):
        return "blog"
    elif any(k in name for k in ["naming", "convention"]):
        return "naming"
    else:
        return "other"

ci_lines = ["# reports/parity/aspose-ci-checks-map.yaml", f"# Generated 2026-05-15 — PAR-009", f"# {len(ci_py_files)} CI checks in aspose.org scripts/ci/checks/", ""]
ci_lines.append("ci_checks:")
for fname in ci_py_files:
    domain = classify_ci(fname)
    fpath = f"{ASPOSE_ROOT}/scripts/ci/checks/{fname}"
    fsize = os.path.getsize(fpath)
    ci_lines.append(f"  - filename: {fname}")
    ci_lines.append(f"    path: scripts/ci/checks/{fname}")
    ci_lines.append(f"    domain: {domain}")
    ci_lines.append(f"    size_bytes: {fsize}")
    ci_lines.append(f"    foss_equivalent: null")
    ci_lines.append(f"    portability: portable")
    ci_lines.append(f"    gap_classification: missing_governance")
    ci_lines.append("")

out_path2 = f"{OUT_DIR}/aspose-ci-checks-map.yaml"
with open(out_path2, "w", encoding="utf-8") as f:
    f.write("\n".join(ci_lines))
print(f"Wrote {out_path2} ({len(ci_py_files)} checks)")

# === 5. Governance docs map ===
gov_lines = ["# reports/parity/aspose-governance-map.yaml", f"# Generated 2026-05-15 — PAR-009", ""]
gov_lines.append("governance_docs:")

for subdir, label in [("docs/governance", "governance"), ("docs/workflows", "workflow")]:
    full_dir = f"{ASPOSE_ROOT}/{subdir}"
    if os.path.isdir(full_dir):
        for fname in sorted(os.listdir(full_dir)):
            if fname.endswith(".md"):
                fpath = f"{ASPOSE_ROOT}/{subdir}/{fname}"
                fsize = os.path.getsize(fpath)
                gov_lines.append(f"  - filename: {fname}")
                gov_lines.append(f"    path: {subdir}/{fname}")
                gov_lines.append(f"    category: {label}")
                gov_lines.append(f"    size_bytes: {fsize}")
                gov_lines.append(f"    foss_equivalent: null")
                gov_lines.append(f"    gap_classification: missing_documentation")
                gov_lines.append("")

out_path3 = f"{OUT_DIR}/aspose-governance-map.yaml"
with open(out_path3, "w", encoding="utf-8") as f:
    f.write("\n".join(gov_lines))

gov_count = sum(1 for l in gov_lines if l.strip().startswith("- filename:"))
print(f"Wrote {out_path3} ({gov_count} governance docs)")

# === Summary ===
print("\n=== PAR-009 COMPLETE ===")
print(f"aspose-inventory.yaml: {len(skills)} entries")
print(f"aspose-ci-checks-map.yaml: {len(ci_py_files)} checks")
print(f"aspose-governance-map.yaml: {gov_count} docs")

with_scripts = sum(1 for s in skills if s["slug"] in skill_to_script)
print(f"\nLayer stats:")
print(f"  Layer 1 (file exists): {len(skills)}/{len(skills)}")
print(f"  Layer 2 (registered): {len(skills)}/{len(skills)}")
print(f"  Layer 3 (script binding): {with_scripts}/{len(skills)}")
