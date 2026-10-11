"""SEO-SCHEMA-A-GENERATION-CONTAMINATION-REMEDIATION (ST-191 Part B) detection
pass. Gitignored (reports/), one-off -- not a pipeline module.

Detects entries in keywords/barcode.json and keywords/cells.json whose
keywords contain zero mention of any family-topic term -- the same signal
the independent reviewers used ("9 of 23 entries... zero barcode/QR/
symbology relevance", "70 of 142 entries... zero mention of any Cells/
Excel-topic term"). Prints the flagged sourcePaths for manual/scripted
remediation; makes no writes.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

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


def load(family: str) -> list:
    return json.loads((REPO_ROOT / f"keywords/{family}.json").read_text(encoding="utf-8"))


def is_contaminated(entry: dict, terms: list[str]) -> bool:
    haystack = " ".join(entry.get("keywords", [])).lower()
    haystack = f" {haystack} "  # padding so " cell " style terms can match at edges
    return not any(t in haystack for t in terms)


def main():
    for family in ("barcode", "cells"):
        entries = load(family)
        terms = _TOPIC_TERMS[family]
        contaminated = [e for e in entries if is_contaminated(e, terms)]
        print(f"=== {family}: {len(contaminated)}/{len(entries)} contaminated ===")
        for e in contaminated:
            print(" ", e["sourcePath"])


if __name__ == "__main__":
    main()
