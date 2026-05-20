# Adapted from aspose.org
"""audit_content_created_at.py -- Baseline coverage report for content_created_at.

Scans all English .md files under the content repo and reports:
  - Files with a provenance block that have content_created_at set
  - Files with a provenance block that are missing content_created_at
  - Files with no provenance block at all

Breakdown is per-site.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from collections import defaultdict
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PIPELINE = _HERE.parents[1]
_SCRIPTS = _HERE.parents[2]
_COMMANDS = _HERE.parent
for _path in (_SCRIPTS, _PIPELINE):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from config_loader import resolve_content_repo  # noqa: E402

try:
    from provenance import read_provenance  # noqa: E402
except ImportError:
    def read_provenance(filepath):
        """Stub: provenance module not available in this repo."""
        return None


def _resolve_repo_root() -> Path:
    env = os.environ.get("CONTENT_REPO_PATH")
    if env:
        return Path(env).resolve()
    try:
        return resolve_content_repo()
    except Exception:
        return _HERE.parents[3]


_REPO_ROOT = _resolve_repo_root()
_CONTENT_ROOT = _REPO_ROOT / "content"
_DEFAULT_CSV = _REPO_ROOT / "reports" / "content_created_at_coverage.csv"

_LOCALE_INFIX_RE = __import__("re").compile(
    r"\.(ar|bg|ca|cs|da|de|el|es|fa|fi|fr|he|hi|hr|hu|id|it|ja|ko|lt|lv|ms|nl|no|pl|pt|ro|ru|sk|sr|sv|th|tr|uk|vi|zh)\.md$"
)


def _is_locale_file(path: Path) -> bool:
    name = path.name
    parts = name.split(".")
    if len(parts) >= 3 and parts[-1] == "md" and len(parts[-2]) in (2, 3):
        lang = parts[-2]
        known_langs = {
            "ar", "bg", "ca", "cs", "da", "de", "el", "es", "fa", "fi",
            "fr", "he", "hi", "hr", "hu", "id", "it", "ja", "ko", "lt",
            "lv", "ms", "nl", "no", "pl", "pt", "ro", "ru", "sk", "sr",
            "sv", "th", "tr", "uk", "vi", "zh",
        }
        return lang in known_langs
    return False


def _site_label(path: Path) -> str:
    try:
        rel = path.relative_to(_CONTENT_ROOT)
        return rel.parts[0]
    except ValueError:
        return "unknown"


def audit(scan_root: Path, csv_path: Path | None) -> None:
    counters: dict[str, dict[str, int]] = defaultdict(lambda: {"has_field": 0, "missing": 0, "no_prov": 0})
    rows: list[dict[str, str]] = []

    total = 0
    for md_file in sorted(scan_root.rglob("*.md")):
        if _is_locale_file(md_file):
            continue
        total += 1
        site = _site_label(md_file)
        prov = read_provenance(md_file)

        if prov is None:
            status = "no_prov"
        elif "content_created_at" in prov:
            status = "has_field"
        else:
            status = "missing"

        counters[site][status] += 1
        if csv_path:
            rows.append({
                "site": site,
                "file": str(md_file.relative_to(_REPO_ROOT)),
                "status": status,
                "content_created_at": prov.get("content_created_at", "") if prov else "",
            })

    print(f"content_created_at coverage -- scanned {total} English .md files")
    print()
    header = f"{'Site':<30}  {'has_field':>10}  {'missing':>10}  {'no_prov':>10}  {'total':>8}"
    print(header)
    print("-" * len(header))

    grand = {"has_field": 0, "missing": 0, "no_prov": 0}
    for site in sorted(counters):
        c = counters[site]
        row_total = c["has_field"] + c["missing"] + c["no_prov"]
        print(f"{site:<30}  {c['has_field']:>10}  {c['missing']:>10}  {c['no_prov']:>10}  {row_total:>8}")
        for k in grand:
            grand[k] += c[k]

    print("-" * len(header))
    grand_total = sum(grand.values())
    print(f"{'TOTAL':<30}  {grand['has_field']:>10}  {grand['missing']:>10}  {grand['no_prov']:>10}  {grand_total:>8}")
    print()

    if csv_path:
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["site", "file", "status", "content_created_at"])
            writer.writeheader()
            writer.writerows(rows)
        print(f"CSV written to: {csv_path}")

    assert grand["has_field"] + grand["missing"] + grand["no_prov"] == total, "Count mismatch"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Report content_created_at coverage across English .md files."
    )
    parser.add_argument("--csv", default=None, help="Write per-file CSV to this path")
    parser.add_argument("--no-csv", action="store_true", default=False, help="Skip CSV output entirely")
    parser.add_argument("--path", default=None, help="Directory to scan (default: content/ relative to repo root)")
    args = parser.parse_args()

    scan_root = Path(args.path).resolve() if args.path else _CONTENT_ROOT
    if not scan_root.exists():
        print(f"ERROR: scan path does not exist: {scan_root}", file=sys.stderr)
        sys.exit(1)

    if args.no_csv:
        csv_path = None
    else:
        csv_path = Path(args.csv).resolve() if args.csv else _DEFAULT_CSV

    audit(scan_root, csv_path)


if __name__ == "__main__":
    main()
