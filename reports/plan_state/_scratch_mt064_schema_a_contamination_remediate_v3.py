"""SEO-SCHEMA-A-GENERATION-CONTAMINATION-REMEDIATION (ST-191 Part B), v3.
Gitignored (reports/), one-off -- not a pipeline module.

v2 grounded the prompt with the family display name + description, and fixed
64 of 67 cells.json entries -- but 3 slipped through: pages whose title uses
a generic-sounding word ("Tables", "Export") pulled Gemini toward a
library-agnostic interpretation (JTable/Apache POI/iText for "Tables";
generic Python file I/O for "Export") despite the prompt's soft "must be
relevant, not generic" instruction. One entry (working-with-tables.md) ended
up actively naming competitor products. Caught by an independent reviewer
who read the real page content, not just pattern-matched keywords.

v3 fixes exactly these 3 named entries with a HARDER structural constraint:
every keyword phrase must literally contain the product name (a mechanical,
verifiable requirement, not a soft "be relevant" instruction), and
regenerates with a verify-and-retry loop (up to 3 attempts) that rejects any
response where fewer than 8 of 10 keywords carry the product name or a
denylisted competitor term appears, before accepting.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if "GOOGLE_API_KEY" not in os.environ and "GEMINI_API_KEY" in os.environ:
    os.environ["GOOGLE_API_KEY"] = os.environ["GEMINI_API_KEY"]

import google.generativeai as genai  # noqa: E402

genai.configure(api_key=os.environ["GOOGLE_API_KEY"])

_RPM_PACING_SECONDS = 4.5
_MAX_429_RETRIES = 5
_BACKOFF_BASE_SECONDS = 60
_MAX_QUALITY_RETRIES = 3

_COMPETITOR_DENYLIST = [
    "apache poi", "itext", "jtable", "javafx", "swing", "pandas",
    "openpyxl", "syncfusion", "closedxml", "epplus", "npoi", "docx4j",
    "libreoffice", "openoffice", "google sheets",
]

_TARGETS = [
    {
        "family": "cells",
        "source_path": "content/docs.aspose.org/en/cells/java/developer-guide/working-with-tables.md",
        "platform": "java",
    },
    {
        "family": "cells",
        "source_path": "content/docs.aspose.org/en/cells/python/developer-guide/export-formats.md",
        "platform": "python",
    },
    {
        "family": "cells",
        "source_path": "content/docs.aspose.org/en/cells/python/developer-guide/export-formats-advanced.md",
        "platform": "python",
    },
]

_PLATFORM_LABELS = {
    "net": ".NET", "java": "Java", "python": "Python", "cpp": "C++", "go": "Go",
    "rust": "Rust", "typescript": "TypeScript", "nodejs": "Node.js", "php": "PHP",
}


def _call_gemini(prompt: str) -> "list[str] | None":
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
                print(f"  ERROR: {e}", file=sys.stderr)
                return None
    return None


def _passes_quality_gate(keywords: list[str], product_markers: list[str]) -> bool:
    if not keywords:
        return False
    lowered = " ".join(keywords).lower()
    for term in _COMPETITOR_DENYLIST:
        if term in lowered:
            return False
    marker_hits = sum(
        1 for kw in keywords if any(m in kw.lower() for m in product_markers)
    )
    return marker_hits >= max(1, int(0.8 * len(keywords)))


def get_hard_grounded_keywords(page_title: str, platform: "str | None", family_display: str, family_description: str, product_markers: list[str]) -> "list[str] | None":
    platform_phrase = "this product" if platform is None else f"the {_PLATFORM_LABELS.get(platform, platform)} platform"
    prompt = (
        f"The product is {family_display}: {family_description}\n"
        f"Generate exactly 10 SEO keyword phrases for the {family_display} product page titled "
        f"'{page_title}' (on {platform_phrase}).\n"
        f"HARD REQUIREMENT: every single keyword phrase, without exception, must literally "
        f"contain the words \"{family_display}\" (or the natural variant \"Aspose Cells\"/\"Aspose.Cells\"). "
        f"Do not generate any keyword about a generic or competing library, framework, or tool "
        f"(e.g. never mention Apache POI, iText, JTable, Swing, JavaFX, pandas, openpyxl, or any "
        f"other product). Every keyword describes {family_display} specifically doing what this "
        f"page's title describes, on {platform_phrase}.\n"
        f"Provide only the keywords, one per line, no numbering, no additional explanation."
    )
    for _ in range(_MAX_QUALITY_RETRIES):
        keywords = _call_gemini(prompt)
        if keywords and _passes_quality_gate(keywords, product_markers):
            return keywords
    return keywords  # best-effort last attempt, caller must still verify


def main():
    descriptions = json.loads((REPO_ROOT / "data" / "family_descriptions.json").read_text(encoding="utf-8"))
    display = {"cells": "Aspose.Cells FOSS"}
    product_markers = {"cells": ["aspose cells", "aspose.cells"]}

    by_family: dict[str, list] = {}
    for t in _TARGETS:
        by_family.setdefault(t["family"], [])

    results = []
    for family in by_family:
        path = REPO_ROOT / f"keywords/{family}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        by_sp = {e["sourcePath"]: e for e in data}
        desc = descriptions[family]["en"]

        for t in [x for x in _TARGETS if x["family"] == family]:
            sp = t["source_path"]
            entry = by_sp[sp]
            print(f"--- regenerating {family}/{sp} ---", file=sys.stderr)
            keywords = get_hard_grounded_keywords(
                entry["pageTitle"], t["platform"], display[family], desc, product_markers[family]
            )
            ok = bool(keywords) and _passes_quality_gate(keywords, product_markers[family])
            if ok:
                entry["keywords"] = list(keywords)
            results.append({"family": family, "sourcePath": sp, "ok": ok, "keywords": keywords})

        path.write_text(json.dumps(data, indent=4, ensure_ascii=False), encoding="utf-8")

    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
