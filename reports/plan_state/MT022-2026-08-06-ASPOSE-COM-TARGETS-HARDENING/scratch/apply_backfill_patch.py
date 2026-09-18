import sys, json, hashlib
sys.path.insert(0, r"d:\onedrive\Documents\GitHub\aspose.org\scripts\pipeline")
from datetime import datetime, timezone
from commands.ops.fetch_aspose_com_targets import build_hugo_yaml_mirror, generate_report, sha256_of

REPO = r"d:\onedrive\Documents\GitHub\aspose.org"
JSON_PATH = REPO + r"\data\aspose_com_targets.json"

with open(JSON_PATH, encoding="utf-8") as f:
    data = json.load(f)

targets = data["targets"]
all_urls = data["all_urls"]

removed = []
updated = []

# Confirmed genuine 404s (both docs.aspose.com and products.aspose.com), live-
# reverified 2026-08-06 with the hardened retry-on-transient-status verify_url()
# (429/500/502/503/504 retried; 404 is NOT transient and was confirmed on the
# FIRST observation for each of these, matching verify_url's own terminal-404
# design). Matches the real script's own exclusion semantics: http_status==404
# entries are excluded from targets/all_urls entirely, not stored as "404".
DEAD_404 = [
    ("docs.aspose.com", "platforms", "cells/typescript", "https://docs.aspose.com/cells/typescript/"),
    ("products.aspose.com", "platforms", "cells/typescript", "https://products.aspose.com/cells/typescript/"),
    ("docs.aspose.com", "platforms", "page/python", "https://docs.aspose.com/page/python/"),
    ("products.aspose.com", "platforms", "page/python", "https://products.aspose.com/page/python/"),
    ("docs.aspose.com", "platforms", "tex/python", "https://docs.aspose.com/tex/python/"),
    ("products.aspose.com", "platforms", "tex/python", "https://products.aspose.com/tex/python/"),
]

for sd, section, key, url in DEAD_404:
    if key in targets.get(sd, {}).get(section, {}):
        del targets[sd][section][key]
        removed.append((sd, key))
    if url in all_urls:
        del all_urls[url]

# Confirmed 403 (access denied) on BOTH docs.aspose.com and products.aspose.com,
# re-verified twice (default UA + a delayed browser-UA retry) -- not resolved by
# either variation, so treated as a real current status, not a WAF artifact of
# the check itself. 403 is not auto-excluded by the real script's logic (only
# 404 is) -- stored as observed, same as any other non-200/non-404 status.
FORBIDDEN_403 = [
    ("docs.aspose.com", "platforms", "email/python", "https://docs.aspose.com/email/python/"),
    ("products.aspose.com", "platforms", "email/python", "https://products.aspose.com/email/python/"),
]
for sd, section, key, url in FORBIDDEN_403:
    entry = targets.get(sd, {}).get(section, {}).get(key)
    if entry:
        entry["http_status"] = 403
        entry["redirect_chain"] = []
        updated.append((sd, key, 403))
    if url in all_urls:
        all_urls[url]["http_status"] = 403
        all_urls[url]["redirect_chain"] = []

# Confirmed persistent 502 on reference.aspose.com specifically (survived 3
# retry attempts under the hardened verify_url() -- NOT a transient blip).
# docs.aspose.com/products.aspose.com/kb.aspose.com cad/net entries are
# healthy (200) and untouched.
sd, key, url = "reference.aspose.com", "cad/net", "https://reference.aspose.com/cad/net/"
entry = targets.get(sd, {}).get("platforms", {}).get(key)
if entry:
    entry["http_status"] = 502
    entry["redirect_chain"] = []
    updated.append((sd, key, 502))
if url in all_urls:
    all_urls[url]["http_status"] = 502
    all_urls[url]["redirect_chain"] = []

# Recompute family_platform_matrix for the 4 affected families only (cells,
# email, page, tex) -- exactly the same derivation build_target_map() uses,
# scoped to families this patch actually touched (matrix entries for all
# other families are untouched, matching the targeted-backfill scope of this
# patch, not a full registry regeneration).
products_sd, docs_sd, ref_sd = "products.aspose.com", "docs.aspose.com", "reference.aspose.com"
matrix = data["family_platform_matrix"]
for fam in ["cells", "email", "page", "tex"]:
    matrix[fam] = {
        "has_family_on_products": fam in targets.get(products_sd, {}).get("families", {}),
        "has_family_on_docs": fam in targets.get(docs_sd, {}).get("families", {}),
        "has_family_on_reference": fam in targets.get(ref_sd, {}).get("families", {}),
        "platforms_on_products": sorted(
            k.split("/")[1] for k in targets.get(products_sd, {}).get("platforms", {}) if k.startswith(fam + "/")
        ),
        "platforms_on_docs": sorted(
            k.split("/")[1] for k in targets.get(docs_sd, {}).get("platforms", {}) if k.startswith(fam + "/")
        ),
        "platforms_on_reference": sorted(
            k.split("/")[1] for k in targets.get(ref_sd, {}).get("platforms", {}) if k.startswith(fam + "/")
        ),
    }

# Provenance: this is a targeted backfill (5 known regressions re-verified
# live), NOT a full registry regeneration -- generated_at is updated
# (matching the existing script's own behavior for --families-scoped runs,
# which also stamps the whole file's generated_at even though only the
# scoped families were freshly checked), but total_targets reflects the
# post-patch all_urls count, not a claim that all 283 other entries were
# re-verified this run.
data["provenance"]["generated_at"] = datetime.now(timezone.utc).isoformat()
data["provenance"]["total_targets"] = len(all_urls)
data["provenance"].setdefault("sources", [])
data["provenance"]["sources"].append({
    "sitemap_url": "targeted-backfill:MT022-2026-08-06-ASPOSE-COM-TARGETS-HARDENING-TC-02",
    "fetched_at": data["provenance"]["generated_at"],
    "source_hash": "n/a",
    "http_status": 200,
    "entry_count": len(DEAD_404) + len(FORBIDDEN_403) + 1,
    "included_count": len(FORBIDDEN_403) + 1,
    "excluded_count": len(DEAD_404),
    "redirect_count": 0,
    "warnings": [
        "Targeted patch, not a full re-crawl: only the 5 originally-untracked "
        "status-regression families (cells/typescript, email/python, "
        "page/python, tex/python, cad/net) were live-reverified this run. "
        "The other ~283 entries were NOT re-checked and retain their prior "
        "(2026-06-19) verification timestamp implicitly -- see "
        "STALE_WARN_DAYS/STALE_BLOCK_DAYS in backlink_targets.py and the new "
        "scheduled aspose-com-targets-watch.yml for ongoing coverage.",
    ],
})

# output_hash itself must not be part of what's hashed (matches the real
# script: it sets output_hash to "" before computing, then fills it in after).
data["provenance"]["output_hash"] = ""
content_for_hash = json.dumps(data, sort_keys=True, ensure_ascii=False)
data["provenance"]["output_hash"] = f"sha256:{sha256_of(content_for_hash)}"

with open(JSON_PATH, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

# Regenerate the Hugo YAML mirror + human report using the REAL script's own
# functions, not hand-rolled logic, so they stay byte-consistent with what a
# real fetch_aspose_com_targets.py run would produce from this same data.
yaml_path = REPO + r"\data\backlinks\aspose_com_targets.yaml"
import yaml as _yaml
hugo_mirror = build_hugo_yaml_mirror(data)
with open(yaml_path, "w", encoding="utf-8") as f:
    f.write(_yaml.dump(hugo_mirror, allow_unicode=True, sort_keys=True))

report_path = REPO + r"\reports\backlinks\aspose_com_targets_report.md"
report_text = generate_report(data, [])
with open(report_path, "w", encoding="utf-8") as f:
    f.write(report_text)

print("Removed (404, excluded):", removed)
print("Updated (403/502):", updated)
print("New generated_at:", data["provenance"]["generated_at"])
print("New output_hash:", data["provenance"]["output_hash"])
print("Written:", JSON_PATH, yaml_path, report_path)
