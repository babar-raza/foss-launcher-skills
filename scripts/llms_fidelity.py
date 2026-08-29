"""llms_fidelity.py -- score content fidelity between source .md and generated .txt.

Generalized from aspose.org's S-LG-04 llms-fidelity skill (2026-08-29 sync).
Scores per-page fidelity across title preservation, heading/code-fence/table
counts, and absence of shortcode/evidence leakage -- same dimensions as
source, same generalization approach (config.yaml sites: block) as
llms_generate.py / llms_coverage.py.

Usage:
    .venv/bin/python scripts/llms_fidelity.py --output llms-output --report reports/llms-fidelity.json
    .venv/bin/python scripts/llms_fidelity.py --output llms-output --gate 90

Exit codes (only meaningful with --gate):
  0 -- overall score at or above the gate threshold
  1 -- overall score below threshold
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config_loader import load_config, resolve_content_repo, ConfigError
from llms_common import (
    extract_title,
    is_eligible_page,
    iter_site_pages,
    parse_frontmatter,
    structural_counts,
)

_DIMENSIONS = 6


def score_page(source_text: str, output_text: str) -> dict:
    frontmatter, body = parse_frontmatter(source_text)
    title = extract_title(frontmatter, body)
    source_counts = structural_counts(body)
    output_counts = structural_counts(output_text)

    checks = {
        "title_preserved": bool(title) and title in output_text[:400],
        "h2_count_ok": output_counts["h2_count"] >= source_counts["h2_count"],
        "code_fence_count_ok": output_counts["code_fence_count"] >= source_counts["code_fence_count"],
        "table_row_count_ok": output_counts["table_row_count"] >= source_counts["table_row_count"],
        "no_shortcode": not output_counts["has_shortcode"],
        "no_evidence_field": not output_counts["has_evidence_field"],
    }
    score = round(sum(1 for v in checks.values() if v) / _DIMENSIONS * 100.0, 1)
    return {"checks": checks, "score": score}


def fidelity_for_site(content_root: Path, output_root: Path, site_type: str, content_path_template: str) -> dict:
    page_scores = []
    for source_path in iter_site_pages(content_root, content_path_template):
        source_text = source_path.read_text(encoding="utf-8", errors="replace")
        frontmatter, _ = parse_frontmatter(source_text)
        if not is_eligible_page(frontmatter):
            continue
        rel_source = source_path.relative_to(content_root)
        output_path = output_root / site_type / rel_source.with_suffix(".txt")
        if not output_path.is_file():
            continue  # coverage gap, not a fidelity concern -- see llms_coverage.py
        output_text = output_path.read_text(encoding="utf-8", errors="replace")
        result = score_page(source_text, output_text)
        page_scores.append({"page": rel_source.as_posix(), **result})

    if not page_scores:
        return {"site": site_type, "status": "no_pages", "domain_score": 0, "failing_pages": 0}

    domain_score = round(sum(p["score"] for p in page_scores) / len(page_scores), 1)
    failing = sum(1 for p in page_scores if p["score"] < 80)
    return {
        "site": site_type,
        "status": "scored",
        "domain_score": domain_score,
        "failing_pages": failing,
        "pages": page_scores,
    }


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", default="llms-output", help="llms-output directory to audit")
    parser.add_argument("--report", default=None, help="Write JSON report to this path")
    parser.add_argument("--gate", type=float, default=None, help="Minimum overall score %% to pass")
    parser.add_argument("--content-root", default=None, help="Override content root")
    args = parser.parse_args(argv)

    try:
        config = load_config()
        content_root = Path(args.content_root) if args.content_root else resolve_content_repo()
    except ConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    sites = config.get("sites", {})
    output_root = Path(args.output)
    domains = {}
    for site_type, site_cfg in sorted(sites.items()):
        if "content_path" not in site_cfg:
            continue
        domains[site_type] = fidelity_for_site(content_root, output_root, site_type, site_cfg["content_path"])

    scored_domains = [d for d in domains.values() if d["status"] == "scored"]
    overall_score = round(sum(d["domain_score"] for d in scored_domains) / len(scored_domains), 1) if scored_domains else 0.0
    gate_status = "PASS" if (args.gate is None or overall_score >= args.gate) else "FAIL"

    report = {"overall_score": overall_score, "gate": gate_status, "domains": domains}

    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"Overall score: {overall_score}% [{gate_status}]")
    for site_type, d in domains.items():
        if d["status"] != "no_pages":
            print(f"  {site_type}: {d['domain_score']}% ({d['failing_pages']} failing)")

    return 0 if gate_status != "FAIL" else 1


if __name__ == "__main__":
    sys.exit(main())
