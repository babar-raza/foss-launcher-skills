"""SEO-SCHEMA-A-GENERATION-CONTAMINATION-REMEDIATION (ST-191 Part B) fix pass.
Gitignored (reports/), one-off -- not a pipeline module.

For every entry flagged by _scratch_mt064_schema_a_contamination_detect.py,
calls the real, already-shipped get_keywords.py generation function
(get_keywords_from_gemini) with the entry's REAL platform (derived from its
sourcePath, mirroring get_keywords.py's own _extract_platform_from_path) and
REPLACES (never unions) the contaminated keywords -- the correct semantics
for a known-wrong correction (get_keywords.py's own replace_keywords_for_entry
precedent, Finding #52: unioning would mix fresh-correct with stale-wrong).

Requires a live Gemini key. This session's environment carries it as
GEMINI_API_KEY; get_keywords.py's real pipeline (and the workflow secret) use
GOOGLE_API_KEY -- set the latter from the former for this process only.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
_SEO_SCRIPTS = REPO_ROOT / "scripts" / "seo"
sys.path.insert(0, str(_SEO_SCRIPTS))

if "GOOGLE_API_KEY" not in os.environ and "GEMINI_API_KEY" in os.environ:
    os.environ["GOOGLE_API_KEY"] = os.environ["GEMINI_API_KEY"]

import get_keywords  # noqa: E402

_TOPIC_TERMS = {
    "barcode": [
        "barcode", "bar code", "qr code", "qr-code", " qr ", "code128", "code39",
        "code 128", "code 39", "ean", "upc", "symbology", "datamatrix", "data matrix",
        "pdf417", "aztec", "codabar", "gs1", "scan", "1d barcode", "2d barcode",
    ],
    "cells": [
        "excel", "spreadsheet", "workbook", "worksheet", " cell ", " cells ",
        "xlsx", "xls ", "csv", "cell format", "pivot", "chart", "cell range",
        "cell data", "spread sheet",
    ],
}


def is_contaminated(entry: dict, terms: list[str]) -> bool:
    haystack = f" {' '.join(entry.get('keywords', [])).lower()} "
    return not any(t in haystack for t in terms)


def platform_from_source_path(source_path: str, family: str) -> "str | None":
    parts = source_path.split("/")
    try:
        idx = parts.index(family)
    except ValueError:
        return None
    rest = parts[idx + 1:]
    # rest[-1] is the filename; a platform subdir means len(rest) > 1
    if len(rest) <= 1:
        return None
    return rest[0]


def remediate_family(family: str) -> dict:
    path = REPO_ROOT / f"keywords/{family}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    terms = _TOPIC_TERMS[family]

    fixed, failed, skipped_clean = [], [], 0
    for entry in data:
        if not is_contaminated(entry, terms):
            skipped_clean += 1
            continue
        sp = entry["sourcePath"]
        platform = platform_from_source_path(sp, family)
        new_keywords = get_keywords.get_keywords_from_gemini(entry["pageTitle"], platform)
        if new_keywords is None:
            failed.append(sp)
            continue
        entry["keywords"] = list(new_keywords)
        fixed.append(sp)

    path.write_text(json.dumps(data, indent=4, ensure_ascii=False), encoding="utf-8")
    return {
        "family": family,
        "total_entries": len(data),
        "fixed_count": len(fixed),
        "failed_count": len(failed),
        "failed_source_paths": failed,
        "skipped_already_clean": skipped_clean,
    }


def main():
    results = []
    for family in ("barcode", "cells"):
        print(f"--- remediating {family} ---", file=sys.stderr)
        results.append(remediate_family(family))
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
