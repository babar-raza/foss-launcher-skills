"""
SEO-001 validate.py
====================
Load, validate, and normalise all keyword JSON files in keywords/.
Produces:
  - reports/seo/validation_report[_{ts}].json  (written to disk)
  - returns {"schema_b": [...], "schema_a": [...]}  (in-memory)

No LLM calls. No network calls. stdlib + pathlib only.
"""
from __future__ import annotations

import json
import os
import re
import sys
import warnings
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[3]           # .../aspose.org
KEYWORDS_DIR = REPO_ROOT / "keywords"
REPORTS_DIR = REPO_ROOT / "reports" / "seo"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

# Schema B files are domain-level JSON (url/keywords/lang/lastUpdated)
# Everything else is Schema A (pageTitle/keywords)
_SCHEMA_B_NAMES = {
    "products.aspose.org.json",
    "reference.aspose.org.json",
    "websites.aspose.org.json",
    "www.aspose.org.json",
}

# These file names contain the family name only — used for quality filter
_SCHEMA_A_FAMILIES: dict[str, str] = {
    "barcode.json": "barcode",
    "cad.json": "cad",
    "cells.json": "cells",
    "home.json": "home",
    "html.json": "html",
    "imaging.json": "imaging",
    "ocr.json": "ocr",
    "page.json": "page",
    "pdf.json": "pdf",
    "psd.json": "psd",
    "tasks.json": "tasks",
    "tex.json": "tex",
    "words.json": "words",
    "zip.json": "zip",
}

# For Schema A files the "platform" cannot be determined from the filename —
# the canonical assumed platform is .NET (the original primary Aspose platform).
_DEFAULT_PLATFORM = "net"

# A keyword string is stale-old if the file mtime is older than this many days.
_STALE_DAYS = 365

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_valid_https_url(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    return value.startswith("https://")


def _is_valid_lang_code(value: Any) -> tuple[bool, bool]:
    """Return (is_valid_2char, is_section_code).
    'ai' is flagged as a section code, not a language."""
    if not isinstance(value, str):
        return False, False
    if len(value) == 2 and re.match(r"^[a-z]{2}$", value):
        is_section = value == "ai"
        return True, is_section
    return False, False


def _parse_iso_date(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True
    except ValueError:
        pass
    try:
        datetime.fromisoformat(value)
        return True
    except ValueError:
        return False


def _file_is_stale(file_path: Path) -> bool:
    mtime = file_path.stat().st_mtime
    age_days = (datetime.now().timestamp() - mtime) / 86400
    return age_days > _STALE_DAYS


def _quality_filter_keywords(keywords: list, family_name: str) -> list[str]:
    """Drop keywords that:
      - exceed 12 words
      - contain 'http'
      - are identical (case-insensitive) to the bare family name
    Returns filtered list.
    """
    family_lower = family_name.lower().strip()
    out: list[str] = []
    for kw in keywords:
        if not isinstance(kw, str):
            continue
        if len(kw.split()) > 12:
            continue
        if "http" in kw.lower():
            continue
        if kw.lower().strip() == family_lower:
            continue
        out.append(kw)
    return out


def _deduplicate_entries(entries: list[dict]) -> list[dict]:
    """Merge duplicate pageTitle entries (union of keywords)."""
    seen: dict[str, list[str]] = {}
    for entry in entries:
        title = entry.get("pageTitle", "")
        kws = entry.get("keywords", [])
        if title in seen:
            seen[title] = list(dict.fromkeys(seen[title] + kws))
        else:
            seen[title] = list(kws)
    return [{"pageTitle": t, "keywords": kws} for t, kws in seen.items()]


# ---------------------------------------------------------------------------
# Schema B validation
# ---------------------------------------------------------------------------


def _validate_schema_b(filename: str, raw: list, file_path: Path) -> tuple[dict, list[dict]]:
    """Validate a Schema B file. Returns (file_summary, validated_records)."""
    issues: list[str] = []
    valid_entries: list[dict] = []
    rejected = 0
    has_queries_global = any("queries" in entry for entry in raw)

    for idx, entry in enumerate(raw):
        entry_issues: list[str] = []

        # url
        url = entry.get("url", "")
        if not _is_valid_https_url(url):
            entry_issues.append(f"entry {idx}: url is not a valid https:// URL ({url!r})")

        # lang
        lang_raw = entry.get("lang", "")
        lang_ok, is_section_code = _is_valid_lang_code(lang_raw)
        if not lang_ok:
            entry_issues.append(f"entry {idx}: lang is not a 2-letter code ({lang_raw!r})")
        if is_section_code:
            entry_issues.append(f"entry {idx}: lang='ai' flagged as section_code, not a language")

        # lastUpdated
        lu = entry.get("lastUpdated", "")
        if not _parse_iso_date(lu):
            entry_issues.append(f"entry {idx}: lastUpdated not a valid ISO date ({lu!r})")

        # queries (optional)
        if "queries" in entry:
            for qidx, q in enumerate(entry["queries"]):
                if not isinstance(q.get("query"), str):
                    entry_issues.append(f"entry {idx} query {qidx}: 'query' must be str")
                if not isinstance(q.get("clicks"), int) or q.get("clicks", -1) < 0:
                    entry_issues.append(f"entry {idx} query {qidx}: 'clicks' must be int >= 0")
                if not isinstance(q.get("impressions"), int) or q.get("impressions", -1) < 0:
                    entry_issues.append(f"entry {idx} query {qidx}: 'impressions' must be int >= 0")
                ctr = q.get("ctr")
                if not isinstance(ctr, (int, float)) or not (0.0 <= float(ctr) <= 1.0):
                    entry_issues.append(f"entry {idx} query {qidx}: 'ctr' must be float 0-1")
                pos = q.get("position")
                if not isinstance(pos, (int, float)) or float(pos) <= 0:
                    entry_issues.append(f"entry {idx} query {qidx}: 'position' must be float > 0")

        if entry_issues:
            # Non-fatal per entry for section_code flag — still include the record
            # but tag it
            issues.extend(entry_issues)

        norm = dict(entry)
        if is_section_code:
            norm["section_code"] = True
            norm["lang"] = lang_raw  # keep original
        norm["metrics_missing"] = not has_queries_global

        valid_entries.append(norm)

    summary = {
        "filename": filename,
        "schema": "B",
        "total_entries": len(raw),
        "valid_entries": len(valid_entries),
        "rejected_entries": rejected,
        "metrics_missing": not has_queries_global,
        "issues": issues,
    }
    return summary, valid_entries


# ---------------------------------------------------------------------------
# Schema A validation
# ---------------------------------------------------------------------------


def _validate_schema_a(filename: str, raw: list, file_path: Path) -> tuple[dict, list[dict]]:
    """Validate a Schema A file. Returns (file_summary, validated_records)."""
    family = _SCHEMA_A_FAMILIES.get(filename, filename.replace(".json", ""))
    issues: list[str] = []
    valid_raw: list[dict] = []
    rejected = 0

    for idx, entry in enumerate(raw):
        # Detect malformed entry (wrong keys)
        has_page_title = "pageTitle" in entry
        has_keywords = "keywords" in entry
        if not has_page_title or not has_keywords:
            issues.append(f"1 malformed entry (wrong keys): entry index {idx} (keys: {list(entry.keys())})")
            rejected += 1
            continue

        page_title = entry["pageTitle"]
        keywords = entry["keywords"]

        if not isinstance(page_title, str) or not page_title.strip():
            issues.append(f"entry {idx}: pageTitle is empty or not a string")
            rejected += 1
            continue

        if not isinstance(keywords, list) or len(keywords) == 0:
            issues.append(f"entry {idx}: keywords must be a non-empty array")
            rejected += 1
            continue

        # Quality-filter keywords
        filtered_kws = _quality_filter_keywords(keywords, family)
        valid_raw.append({"pageTitle": page_title, "keywords": filtered_kws})

    # Deduplicate by pageTitle
    deduped = _deduplicate_entries(valid_raw)

    # Determine staleness
    stale = _file_is_stale(file_path)

    summary = {
        "filename": filename,
        "schema": "A",
        "total_entries": len(raw),
        "valid_entries": len(deduped),
        "rejected_entries": rejected,
        "stale": stale,
        "platform_assumed": _DEFAULT_PLATFORM,
        "issues": issues,
    }

    # Annotate each record with file-level metadata
    records = [
        {
            "pageTitle": e["pageTitle"],
            "keywords": e["keywords"],
            "family": family,
            "platform_assumed": _DEFAULT_PLATFORM,
            "stale": stale,
            "source_file": filename,
        }
        for e in deduped
    ]
    return summary, records


# ---------------------------------------------------------------------------
# Main validation orchestrator
# ---------------------------------------------------------------------------


def run_validation(keywords_dir: Path | None = None) -> dict:
    """
    Validate all keyword JSON files.

    Returns:
        {
          "schema_b": [validated Schema B records],
          "schema_a": [validated Schema A records],
        }

    Side effect: writes validation_report.json (or timestamped variant) to
    reports/seo/.
    """
    if keywords_dir is None:
        keywords_dir = KEYWORDS_DIR

    all_files = sorted(keywords_dir.glob("*.json"))
    file_summaries: list[dict] = []
    schema_b_records: list[dict] = []
    schema_a_records: list[dict] = []

    for file_path in all_files:
        filename = file_path.name
        try:
            raw = json.loads(file_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            file_summaries.append({
                "filename": filename,
                "schema": "unknown",
                "total_entries": 0,
                "valid_entries": 0,
                "rejected_entries": 0,
                "issues": [f"Failed to parse JSON: {exc}"],
            })
            warnings.warn(f"validate.py: could not parse {filename}: {exc}")
            continue

        if not isinstance(raw, list):
            file_summaries.append({
                "filename": filename,
                "schema": "unknown",
                "total_entries": 0,
                "valid_entries": 0,
                "rejected_entries": 0,
                "issues": ["Root element is not a JSON array"],
            })
            continue

        if filename in _SCHEMA_B_NAMES:
            summary, records = _validate_schema_b(filename, raw, file_path)
            schema_b_records.extend(records)
        else:
            summary, records = _validate_schema_a(filename, raw, file_path)
            schema_a_records.extend(records)

        file_summaries.append(summary)

    report = {
        "run_at": date.today().isoformat(),
        "files": file_summaries,
    }

    # Safe-write: avoid overwriting an existing report
    report_path = REPORTS_DIR / "validation_report.json"
    if report_path.exists():
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = REPORTS_DIR / f"validation_report_{ts}.json"

    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    return {
        "schema_b": schema_b_records,
        "schema_a": schema_a_records,
        "_report_path": str(report_path),
        "_file_summaries": file_summaries,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _print_summary(result: dict) -> None:
    summaries = result.get("_file_summaries", [])
    print(f"\n=== Keyword Validation Summary ===")
    print(f"Total files processed : {len(summaries)}")
    schema_b_files = [s for s in summaries if s.get("schema") == "B"]
    schema_a_files = [s for s in summaries if s.get("schema") == "A"]
    print(f"  Schema B files      : {len(schema_b_files)}")
    print(f"  Schema A files      : {len(schema_a_files)}")
    print(f"  Unknown/error files : {len(summaries) - len(schema_b_files) - len(schema_a_files)}")
    print()

    total_entries = sum(s.get("total_entries", 0) for s in summaries)
    valid_entries = sum(s.get("valid_entries", 0) for s in summaries)
    rejected_entries = sum(s.get("rejected_entries", 0) for s in summaries)
    print(f"Total entries         : {total_entries}")
    print(f"  Valid               : {valid_entries}")
    print(f"  Rejected            : {rejected_entries}")
    print()

    stale_files = [s["filename"] for s in schema_a_files if s.get("stale")]
    print(f"Stale Schema A files  : {len(stale_files)}")
    for f in stale_files:
        print(f"  {f}")

    metrics_missing = [s["filename"] for s in schema_b_files if s.get("metrics_missing")]
    print(f"Schema B no metrics   : {len(metrics_missing)}")
    for f in metrics_missing:
        print(f"  {f}")

    all_issues: list[tuple[str, str]] = []
    for s in summaries:
        for issue in s.get("issues", []):
            all_issues.append((s["filename"], issue))
    print(f"\nTotal issues flagged  : {len(all_issues)}")
    for fname, issue in all_issues[:20]:
        print(f"  [{fname}] {issue}")
    if len(all_issues) > 20:
        print(f"  ... and {len(all_issues) - 20} more")

    print(f"\nReport written to     : {result['_report_path']}")
    print()

    # Per-file table
    print(f"{'Filename':<35} {'Schema':<8} {'Total':>6} {'Valid':>6} {'Rej':>5} {'Issues':>7}")
    print("-" * 75)
    for s in summaries:
        issues_count = len(s.get("issues", []))
        print(
            f"{s['filename']:<35} {s.get('schema','?'):<8} "
            f"{s.get('total_entries',0):>6} {s.get('valid_entries',0):>6} "
            f"{s.get('rejected_entries',0):>5} {issues_count:>7}"
        )


if __name__ == "__main__":
    result = run_validation()
    _print_summary(result)
    print(f"\nSchema B records : {len(result['schema_b'])}")
    print(f"Schema A records : {len(result['schema_a'])}")
