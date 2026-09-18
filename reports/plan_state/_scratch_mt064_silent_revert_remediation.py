"""SEO-KEYWORDS-SILENT-REVERT-REMEDIATION (ST-191 Part A) scratch remediation
script. Gitignored (reports/), one-off -- not a pipeline module.

For each of the 5 families (tex, page, font, note, html): commit b68089586a
(2026-08-02) fixed contaminated keyword entries; commit 55586b637c
(2026-08-07, no "(seo)" message token) silently reverted them back to the
pre-fix content. tex/page/font/note have had zero legitimate touches since
the revert (HEAD == 55586b637c for those files); html got one legitimate
refresh since (34a412d6d8, 2026-08-26) that touched OTHER entries but left
the reverted ones untouched (confirmed by the independent reviewer's
html_verdict.json). A blind whole-file `git checkout b68089586a -- <file>`
would be safe for the first 4 but would discard html's legitimate
2026-08-26 refresh -- so this does a per-entry, sourcePath-keyed
reconciliation instead, uniformly across all 5 files:

For every entry in the CURRENT (working-tree) file, if it is byte-identical
to the REVERTED (55586b637c) version of that sourcePath AND a GOOD
(b68089586a) version of that sourcePath exists, replace the entry with the
GOOD version. Every other entry (never part of the revert, or already
legitimately refreshed since) is left untouched.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FAMILIES = ["tex", "page", "font", "note", "html"]
GOOD_SHA = "b68089586a"
REVERTED_SHA = "55586b637c"


def git_show_json(sha: str, path: str) -> list:
    # capture_output + text=True decodes with the platform's default locale
    # encoding (cp1252 on this Windows environment), silently corrupting any
    # non-ASCII byte in the JSON (e.g. an em-dash in a pageTitle) -- capture
    # raw bytes and decode as UTF-8 explicitly instead. This exact bug caused
    # the first pass of this script to spuriously treat 5 already-reverted
    # note.json entries as "already different from the revert" (mojibake
    # mismatch, not a real content difference) and skip restoring them --
    # caught by independent review.
    out = subprocess.run(
        ["git", "show", f"{sha}:{path}"], capture_output=True, check=True, cwd=REPO_ROOT
    ).stdout
    return json.loads(out.decode("utf-8"))


def by_source_path(entries: list) -> dict:
    return {e["sourcePath"]: e for e in entries if "sourcePath" in e}


def remediate_family(family: str) -> dict:
    rel_path = f"keywords/{family}.json"
    good = by_source_path(git_show_json(GOOD_SHA, rel_path))
    reverted = by_source_path(git_show_json(REVERTED_SHA, rel_path))
    current_path = REPO_ROOT / rel_path
    current_list = json.loads(current_path.read_text(encoding="utf-8"))

    restored = []
    unchanged = 0
    no_good_available = []
    new_list = []
    for entry in current_list:
        sp = entry.get("sourcePath")
        if sp and sp in reverted and entry == reverted[sp]:
            if sp in good:
                new_list.append(good[sp])
                restored.append(sp)
                continue
            else:
                no_good_available.append(sp)
        new_list.append(entry)
        unchanged += 1

    # Entries present in GOOD but entirely missing from current (dropped) --
    # should not happen (get_keywords.py never removes entries), but verify.
    missing_from_current = sorted(set(good.keys()) - {e.get("sourcePath") for e in current_list})

    current_path.write_text(
        json.dumps(new_list, indent=4, ensure_ascii=False), encoding="utf-8"
    )

    return {
        "family": family,
        "total_entries": len(new_list),
        "restored_count": len(restored),
        "restored_source_paths": sorted(restored),
        "unchanged_count": unchanged,
        "no_good_available_for": no_good_available,
        "missing_from_current_vs_good": missing_from_current,
    }


def main():
    results = [remediate_family(f) for f in FAMILIES]
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
