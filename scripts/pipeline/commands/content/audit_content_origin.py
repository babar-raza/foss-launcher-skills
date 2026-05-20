#!/usr/bin/env python3
"""audit_content_origin.py — Sprint 3 inventory for content_origin: unknown recovery.

Scans all English .md files across the five production sites, identifies files
with content_origin: unknown, classifies them into recovery classes, and writes
a CSV for human review and automated processing.

Classification logic (per plan Section K.5 decision tree):
  Class 1 — Evidence-repair eligible: grade in {A, B} AND evidence block exists
             AND claims is empty list (not absent)
  Class 2 — Human review required: grade in {C, D, F} OR (grade A/B but no claims field)
  Class 3 — Structural/deferred: no grade, no evidence block

Strategy assignment:
  Class 1 → Strategy A (S-72 evidence-repair → content_origin_recover)
  Class 2 → Strategy B (human review)
  Class 3 → Strategy C (write-lock + deferral)

Usage:
    python scripts/pipeline/commands/content/audit_content_origin.py [--csv PATH] [--site SITE]

    --csv   Write per-file CSV to PATH
            (default: reports/content_origin_review_queue.csv)
    --site  Filter to one site (e.g. reference.aspose.org)
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE.parent.parent))  # scripts/pipeline/
    _LIB_DIR = str(Path(_HERE) / "lib") if isinstance(_HERE, str) else str(_HERE / "lib")
    if _LIB_DIR not in sys.path:
        sys.path.insert(0, _LIB_DIR)

from provenance import read_provenance  # noqa: E402

_DEFAULT_REPO_ROOT = (_HERE / ".." / ".." / ".." / "..").resolve()
_REPO_ROOT = _DEFAULT_REPO_ROOT
_CONTENT_ROOT = _REPO_ROOT / "content"
_DEFAULT_CSV = _REPO_ROOT / "reports" / "content_origin_review_queue.csv"


def configure(*, repo_root: "Path | str | None" = None, content_root: "Path | str | None" = None) -> None:
    """Override module-level path constants for testing."""
    global _REPO_ROOT, _CONTENT_ROOT
    _REPO_ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT
    _CONTENT_ROOT = Path(content_root) if content_root is not None else _REPO_ROOT / "content"

_SITES = [
    "blog.aspose.org",
    "docs.aspose.org",
    "kb.aspose.org",
    "products.aspose.org",
    "reference.aspose.org",
]

_LOCALE_INFIX_RE = re.compile(
    r"\.(ar|bg|ca|cs|da|de|el|es|fa|fi|fr|he|hi|hr|hu|id|it|ja|ko|lt|lv|ms|"
    r"nl|no|pl|pt|ro|ru|sk|sr|sv|th|tr|uk|vi|zh)\.md$"
)
_LOCALE_DIR_RE = re.compile(
    r"/(?:ar|bg|ca|cs|da|de|el|es|fa|fi|fr|he|hi|hr|hu|id|it|ja|ko|lt|lv|ms|"
    r"nl|no|pl|pt|ro|ru|sk|sr|sv|th|tr|uk|vi|zh)/"
)

_GRADE_RE = re.compile(r"grade:\s+(\S+)")
_CLAIMS_RE = re.compile(r"claims:\s*\[([^\]]*)\]")
_HIGH_GRADE = {"A", "B"}
_LOW_GRADE = {"C", "D", "E", "F"}


def _is_locale_file(path: Path) -> bool:
    name = path.name
    parts = name.split(".")
    if len(parts) >= 3 and parts[-1] == "md" and len(parts[-2]) in (2, 3):
        known = {
            "ar", "bg", "ca", "cs", "da", "de", "el", "es", "fa", "fi",
            "fr", "he", "hi", "hr", "hu", "id", "it", "ja", "ko", "lt",
            "lv", "ms", "nl", "no", "pl", "pt", "ro", "ru", "sk", "sr",
            "sv", "th", "tr", "uk", "vi", "zh",
        }
        return parts[-2] in known
    path_str = path.as_posix()
    if _LOCALE_DIR_RE.search(path_str):
        return True
    return False


def _site_label(path: Path) -> str:
    parts = path.parts
    try:
        idx = next(i for i, p in enumerate(parts) if "aspose.org" in p)
        return parts[idx]
    except StopIteration:
        return "unknown"


def _family_platform(path: Path, site: str) -> tuple[str, str]:
    """Extract family and platform from a content path."""
    parts = path.as_posix().split("/")
    try:
        idx = next(i for i, p in enumerate(parts) if p == site)
    except StopIteration:
        return ("unknown", "unknown")
    after = parts[idx + 1:]
    if after and after[0] == "en":
        after = after[1:]
    family = after[0] if after else "unknown"
    platform = after[1] if len(after) > 1 else "unknown"
    return (family, platform)


def _classify(grade: str, has_evidence: bool, claims_present: bool, claims_empty: bool) -> tuple[str, str]:
    """Classify a file into a recovery class and assign a strategy.

    Returns (class_label, strategy).
    """
    # Class 3: no grade, no evidence block (structural/infrastructure pages)
    if not grade and not has_evidence:
        return ("3", "C")

    # Class 3 also: no grade even with evidence (not enough signal)
    if not grade and has_evidence:
        return ("2", "B")

    # Grade present
    if grade in _HIGH_GRADE:
        if claims_present and claims_empty:
            # Grade A/B + claims: [] → evidence-repair eligible
            return ("1", "A")
        elif not claims_present:
            # Grade A/B but no claims field at all (structural evidence block or no evidence)
            if has_evidence:
                return ("2", "B")
            else:
                return ("3", "C")
        else:
            # Grade A/B + non-empty claims → should have been promoted already (anomaly)
            return ("anomaly", "investigate")

    if grade in _LOW_GRADE:
        return ("2", "B")

    # Unknown grade value
    return ("2", "B")


def audit(site_filter: str | None = None, csv_path: Path = _DEFAULT_CSV) -> dict:
    """Run the audit and write the review queue CSV."""
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    stats: dict[str, int] = defaultdict(int)
    class_counts: dict[str, int] = defaultdict(int)

    sites = [site_filter] if site_filter else _SITES

    for site in sites:
        site_root = _CONTENT_ROOT / site
        if not site_root.exists():
            continue

        for md_file in sorted(site_root.rglob("*.md")):
            if _is_locale_file(md_file):
                continue

            prov = read_provenance(md_file)
            if prov is None:
                continue

            content_origin = prov.get("content_origin", "")
            if content_origin != "unknown":
                continue

            stats["total_unknown"] += 1

            try:
                text = md_file.read_text(encoding="utf-8")
            except OSError:
                stats["read_error"] += 1
                continue

            # Extract grade
            m = _GRADE_RE.search(text)
            grade = m.group(1) if m else ""

            # Evidence block
            has_evidence = "evidence:" in text

            # Claims analysis
            cm = _CLAIMS_RE.search(text)
            claims_present = cm is not None
            claims_empty = cm is not None and not cm.group(1).strip()
            claims_non_empty = cm is not None and bool(cm.group(1).strip())

            # Has code blocks
            has_code = "```" in text

            # last_mechanism
            last_mechanism = prov.get("last_mechanism", "")

            # content_created_at
            content_created_at = prov.get("content_created_at", "")

            # Family/platform
            family, platform = _family_platform(md_file, site)

            # Classify
            class_label, strategy = _classify(grade, has_evidence, claims_present, claims_empty)
            class_counts[class_label] += 1

            rel_path = md_file.relative_to(_REPO_ROOT).as_posix()

            rows.append({
                "site": site,
                "filepath": rel_path,
                "family": family,
                "platform": platform,
                "grade": grade,
                "last_mechanism": last_mechanism,
                "has_evidence": str(has_evidence),
                "claims_present": str(claims_present),
                "claims_empty": str(claims_empty),
                "claims_non_empty": str(claims_non_empty),
                "has_code_blocks": str(has_code),
                "content_created_at": content_created_at,
                "assigned_class": class_label,
                "assigned_strategy": strategy,
                "outcome": "",  # filled by human review or apply script
            })

    # Write CSV
    fieldnames = [
        "site", "filepath", "family", "platform", "grade", "last_mechanism",
        "has_evidence", "claims_present", "claims_empty", "claims_non_empty",
        "has_code_blocks", "content_created_at", "assigned_class",
        "assigned_strategy", "outcome",
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    stats["class_1"] = class_counts.get("1", 0)
    stats["class_2"] = class_counts.get("2", 0)
    stats["class_3"] = class_counts.get("3", 0)
    stats["anomaly"] = class_counts.get("anomaly", 0)

    return dict(stats)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit content_origin: unknown files and generate review queue"
    )
    parser.add_argument(
        "--csv",
        default=str(_DEFAULT_CSV),
        help=f"Output CSV path (default: {_DEFAULT_CSV})",
    )
    parser.add_argument(
        "--site",
        default=None,
        help="Filter to one site (e.g. reference.aspose.org)",
    )
    args = parser.parse_args()

    print("content_origin audit — scanning unknown files\n")
    stats = audit(site_filter=args.site, csv_path=Path(args.csv))

    total = stats.get("total_unknown", 0)
    print(f"Total content_origin: unknown  : {total}")
    print(f"  Class 1 (evidence-repair A/B): {stats.get('class_1', 0)}")
    print(f"  Class 2 (human review C/D/F) : {stats.get('class_2', 0)}")
    print(f"  Class 3 (structural/deferred): {stats.get('class_3', 0)}")
    if stats.get("anomaly", 0):
        print(f"  ANOMALY (A/B + non-empty claims): {stats.get('anomaly', 0)}")
    if stats.get("read_error", 0):
        print(f"  Read errors                  : {stats.get('read_error', 0)}")
    print(f"\nCSV written to: {args.csv}")


if __name__ == "__main__":
    main()