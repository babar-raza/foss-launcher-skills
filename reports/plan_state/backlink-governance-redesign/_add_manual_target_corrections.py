import json
import sys
from pathlib import Path

sys.path.insert(0, "scripts/pipeline")
import commands.ops.fetch_aspose_com_targets as fetcher  # noqa: E402

json_path = Path("data/aspose_com_targets.json")
yaml_path = Path("data/backlinks/aspose_com_targets.yaml")

output_data = json.loads(json_path.read_text(encoding="utf-8"))

platforms = output_data["targets"]["products.aspose.com"]["platforms"]

new_entries = {
    "tex/python": {
        "url": "https://products.aspose.com/tex/python-net/",
        "http_status": 200,
        "redirect_chain": [],
        "validated_via": "manual-correction-2026-08-24-tc15-backfill-regression-check",
    },
    "page/python": {
        "url": "https://products.aspose.com/page/python-net/",
        "http_status": 200,
        "redirect_chain": [],
        "validated_via": "manual-correction-2026-08-24-tc15-backfill-regression-check",
    },
}

for key, entry in new_entries.items():
    if key in platforms:
        print(f"ABORT: {key} already exists in platforms map: {platforms[key]}")
        sys.exit(1)
    platforms[key] = entry
    print(f"Added: {key} -> {entry['url']}")

# Recompute output_hash exactly as fetch_aspose_com_targets.py does.
output_data["provenance"]["output_hash"] = ""
content_for_hash = json.dumps(output_data, sort_keys=True, ensure_ascii=False)
output_data["provenance"]["output_hash"] = f"sha256:{fetcher.sha256_of(content_for_hash)}"

json_path.write_text(json.dumps(output_data, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"Written: {json_path}")

hugo_mirror = fetcher.build_hugo_yaml_mirror(output_data)
import yaml as _yaml
yaml_path.write_text(_yaml.dump(hugo_mirror, allow_unicode=True, sort_keys=True), encoding="utf-8")
print(f"Written: {yaml_path}")
