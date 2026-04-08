"""Remove stale claim IDs from EN content pages across all repos."""
import json
import re
from pathlib import Path

# Repos to fix: (family, platform, claims_json_path, content_dirs)
REPOS = [
    {
        "family": "3d", "platform": "python",
        "claims": "knowledge/3d/python/merged/claims.json",
        "content_roots": [
            "content/kb.aspose.org/en/3d/python",
            "content/docs.aspose.org/en/3d/python",
            "content/reference.aspose.org/en/3d/python",
            "content/products.aspose.org/en/3d",
            "content/blog.aspose.org/3d/python",
        ],
    },
    {
        "family": "cells", "platform": "python",
        "claims": "knowledge/cells/python/merged/claims.json",
        "content_roots": [
            "content/kb.aspose.org/en/cells/python",
            "content/docs.aspose.org/en/cells/python",
            "content/reference.aspose.org/en/cells/python",
            "content/products.aspose.org/en/cells",
            "content/blog.aspose.org/cells/python",
        ],
    },
]

CLAIM_RE = re.compile(r"^\s+- (CLM-[a-z0-9-]+)\s*$", re.MULTILINE)
FM_RE = re.compile(r"^(---\n.*?\n---\n)", re.DOTALL)


def fix_repo(cfg: dict) -> int:
    claims_path = Path(cfg["claims"])
    if not claims_path.exists():
        print(f"  SKIP: {claims_path} not found")
        return 0

    claims = json.load(claims_path.open(encoding="utf-8"))
    valid_ids = {c["claim_id"] for c in claims}
    total_fixed = 0

    for root_str in cfg["content_roots"]:
        root = Path(root_str)
        if not root.exists():
            continue
        for md_file in root.rglob("*.md"):
            content = md_file.read_text(encoding="utf-8")
            fm_match = FM_RE.match(content)
            if not fm_match:
                continue
            fm = fm_match.group(1)
            claim_ids = CLAIM_RE.findall(fm)
            stale = [c for c in claim_ids if c not in valid_ids]
            if not stale:
                continue
            new_fm = fm
            for sid in stale:
                new_fm = re.sub(
                    rf"^\s+- {re.escape(sid)}\s*\n", "", new_fm, flags=re.MULTILINE
                )
            new_content = new_fm + content[fm_match.end():]
            md_file.write_text(new_content, encoding="utf-8")
            total_fixed += 1

    return total_fixed


total = 0
for cfg in REPOS:
    count = fix_repo(cfg)
    total += count
    print(f"  {cfg['family']}/{cfg['platform']}: {count} pages fixed")

print(f"\nTotal pages fixed: {total}")
