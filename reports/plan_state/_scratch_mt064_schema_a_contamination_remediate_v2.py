"""SEO-SCHEMA-A-GENERATION-CONTAMINATION-REMEDIATION (ST-191 Part B), v2.
Gitignored (reports/), one-off -- not a pipeline module.

v1 (_scratch_mt064_schema_a_contamination_remediate.py) called
get_keywords.py's real get_keywords_from_gemini(page_title, platform)
verbatim -- the exact function/prompt template the real pipeline uses -- and
it "succeeded" (0 API failures) but did NOT actually fix the contamination:
every one of the 9 barcode + 67 cells flagged entries has a GENERIC page
title ("Frequently Asked Questions", "Getting Started", "Installation",
"License", "Features", bare "_index" pages) with zero product/topic word in
the title itself. get_keywords.py's prompt embeds ONLY the bare page_title,
so for these pages Gemini has no way to know the page is about barcode/Excel
at all -- it reproduces generic platform-flavored keywords every time,
regardless of retries. Every entry that WAS already topical has the product
name directly in its title ("Aspose.BarCode FOSS", "Barcode Rendering",
"Choosing a Barcode Symbology", etc.) -- confirmed directly by reading every
clean entry's pageTitle in keywords/barcode.json.

This is a real, structural weakness in get_keywords.py's prompt template
(out of this card's allowed_paths to fix at the source -- flagged
separately, see the commit message / plan resolver card), not something a
retry or a different model fixes. v2 works around it for this remediation
only: for exactly the flagged entries, builds a prompt that also includes
the real family display name + one-line product description (read from
data/family_descriptions.json, the same registry get_keywords.py's own
canonical_families() already treats as authoritative), so Gemini has real
topic grounding even when the page's own title is generic.
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

import google.generativeai as genai  # noqa: E402

genai.configure(api_key=os.environ["GOOGLE_API_KEY"])

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

_PLATFORM_LABELS = {
    "net": ".NET", "java": "Java", "python": "Python", "cpp": "C++", "go": "Go",
    "rust": "Rust", "typescript": "TypeScript", "nodejs": "Node.js", "php": "PHP",
}

_RPM_PACING_SECONDS = 4.5
_MAX_429_RETRIES = 5
_BACKOFF_BASE_SECONDS = 60


def is_contaminated(entry: dict, terms: list[str]) -> bool:
    haystack = f" {' '.join(entry.get('keywords', [])).lower()} "
    return not any(t in haystack for t in terms)


def platform_from_source_path(source_path: str, family: str) -> "str | None":
    parts = source_path.split("/")
    idx = parts.index(family)
    rest = parts[idx + 1:]
    return rest[0] if len(rest) > 1 else None


def get_grounded_keywords(page_title: str, platform: "str | None", family_display: str, family_description: str) -> "list[str] | None":
    platform_phrase = "this product" if platform is None else f"the {_PLATFORM_LABELS.get(platform, platform)} platform"
    prompt = (
        f"The product is {family_display}: {family_description}\n"
        f"Generate a concise list of SEO keywords for the product page titled '{page_title}', "
        f"which belongs to {family_display}. Focus on long tail keywords related to "
        f"{family_display} and {platform_phrase} having medium to high search volume, and low "
        f"to medium competition. Every keyword must be specifically relevant to {family_display}'s "
        f"real subject matter, not generic {platform_phrase} programming advice unrelated to it. "
        f"Provide only the keywords, with each keyword on a new line, and no additional explanations."
    )
    model = genai.GenerativeModel("gemini-flash-lite-latest")
    for attempt in range(1, _MAX_429_RETRIES + 1):
        try:
            response = model.generate_content(prompt)
            keywords = [kw.strip() for kw in response.text.split("\n") if kw.strip()]
            time.sleep(_RPM_PACING_SECONDS)
            return keywords
        except Exception as e:
            if "429" in str(e):
                if attempt == _MAX_429_RETRIES:
                    return None
                time.sleep(_BACKOFF_BASE_SECONDS * attempt)
            else:
                print(f"  ERROR for '{page_title}': {e}", file=sys.stderr)
                return None
    return None


def remediate_family(family: str, family_display: str, family_description: str) -> dict:
    path = REPO_ROOT / f"keywords/{family}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    terms = _TOPIC_TERMS[family]

    fixed, failed = [], []
    for entry in data:
        if not is_contaminated(entry, terms):
            continue
        sp = entry["sourcePath"]
        platform = platform_from_source_path(sp, family)
        new_keywords = get_grounded_keywords(entry["pageTitle"], platform, family_display, family_description)
        if new_keywords is None:
            failed.append(sp)
            continue
        entry["keywords"] = list(new_keywords)
        fixed.append(sp)

    path.write_text(json.dumps(data, indent=4, ensure_ascii=False), encoding="utf-8")
    return {"family": family, "fixed_count": len(fixed), "failed_count": len(failed), "failed_source_paths": failed}


def main():
    descriptions = json.loads((REPO_ROOT / "data" / "family_descriptions.json").read_text(encoding="utf-8"))
    targets = {
        "barcode": "Aspose.BarCode FOSS",
        "cells": "Aspose.Cells FOSS",
    }
    results = []
    for family, display in targets.items():
        print(f"--- remediating {family} (v2, grounded prompt) ---", file=sys.stderr)
        desc = descriptions[family]["en"]
        results.append(remediate_family(family, display, desc))
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
