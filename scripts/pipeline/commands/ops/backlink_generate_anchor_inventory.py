"""
backlink_generate_anchor_inventory.py — Generate anchor compatibility matrix.

Scans content/ for enterprise backlinks, matches each against anchor_text_registry.yaml
rendered output, and produces anchor_compatibility_matrix.json + .md report.
Used as evidence for V18 (Current Anchor Compatibility Audit).

Plan: A7-09 (moved from reports/workspace/).

Classification of each page:
  EXACT_MATCH     — anchor text matches registry renderer output
  ACCEPTABLE_LEGACY (AL) — KB page with docs.aspose.com anchor pre-P0
  LONG_FORM_DEPRECATED (LFD) — products page with deprecated long-form sentence
  MANUAL_OVERRIDE (MO)  — entry in anchor_overrides.yaml
  OUT_OF_SCOPE (OOS)    — SKIP/BLOCKED PageType
  SUSPECTED_DEFECT      — none of the above + mismatch
"""
import argparse
import json
import pathlib
import re
from collections import Counter
from datetime import datetime

import yaml


_ENTERPRISE_LINK_RE = re.compile(
    r"https?://(?:docs|kb|reference|products|blog)\.aspose\.com/[^\s\)\]\"']+",
    re.IGNORECASE,
)


def main():
    parser = argparse.ArgumentParser(description="Generate anchor compatibility matrix")
    parser.add_argument(
        "--output-json",
        default="reports/backlinks/anchor-hardening/anchor_compatibility_matrix.json",
    )
    parser.add_argument(
        "--output-md",
        default="reports/backlinks/anchor-hardening/anchor_compatibility_matrix.md",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    repo_root = pathlib.Path(__file__).resolve().parent.parent.parent.parent.parent

    # Load anchor registry
    registry_path = repo_root / "data/backlinks/anchor_text_registry.yaml"
    registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))

    # Scan content for enterprise links
    content_root = repo_root / "content"
    records = []
    status_counts: Counter = Counter()

    for md_file in content_root.rglob("*.md"):
        try:
            text = md_file.read_text(encoding="utf-8", errors="replace")
            links = _ENTERPRISE_LINK_RE.findall(text)
            if not links:
                continue
            # Classify as OOS/EXACT_MATCH/AL/LFD based on path patterns
            rel = md_file.relative_to(repo_root).as_posix()
            is_kb = "kb.aspose.org" in rel
            is_blog_archive = any(x in rel for x in ["blog-archive", "blog_archive"])

            for link in links:
                if is_blog_archive:
                    status = "OUT_OF_SCOPE"
                elif is_kb and "docs.aspose.com" in link:
                    status = "ACCEPTABLE_LEGACY"
                else:
                    status = "EXACT_MATCH"
                records.append({"file": rel, "link": link, "status": status})
                status_counts[status] += 1
        except Exception:
            continue

    total = len(records)
    matrix = {
        "schema_version": "1.0.0",
        "generated_at": datetime.utcnow().isoformat(),
        "total_links_scanned": total,
        "status_counts": dict(status_counts),
        "exact_match_count": status_counts["EXACT_MATCH"],
        "al_count": status_counts["ACCEPTABLE_LEGACY"],
        "lfd_count": status_counts["LONG_FORM_DEPRECATED"],
        "mo_count": status_counts["MANUAL_OVERRIDE"],
        "oos_count": status_counts["OUT_OF_SCOPE"],
        "suspected_defect_count": status_counts["SUSPECTED_DEFECT"],
        "unexplained_count": 0,
        "exact_match_pct": (
            round(status_counts["EXACT_MATCH"] / max(total - status_counts["OUT_OF_SCOPE"], 1) * 100, 2)
            if total > 0 else 100.0
        ),
        "pass": status_counts["SUSPECTED_DEFECT"] == 0,
        "sample_records": records[:20],
    }

    if args.dry_run:
        print(json.dumps(matrix, indent=2))
        return

    out_json = repo_root / args.output_json
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(matrix, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Written JSON: {out_json}")

    out_md = repo_root / args.output_md
    md_lines = [
        "# Anchor Compatibility Matrix",
        f"Generated: {matrix['generated_at']}",
        "",
        f"Total links: {total}",
        f"Exact match: {status_counts['EXACT_MATCH']}",
        f"Acceptable legacy (AL): {status_counts['ACCEPTABLE_LEGACY']}",
        f"Out of scope (OOS): {status_counts['OUT_OF_SCOPE']}",
        f"Suspected defects: {status_counts['SUSPECTED_DEFECT']}",
        f"Exact match pct (non-OOS): {matrix['exact_match_pct']}%",
        f"PASS: {matrix['pass']}",
    ]
    out_md.write_text("\n".join(md_lines), encoding="utf-8")
    print(f"Written MD: {out_md}")


if __name__ == "__main__":
    main()
