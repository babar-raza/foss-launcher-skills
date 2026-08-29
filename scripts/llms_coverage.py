"""llms_coverage.py -- audit coverage gap between content/ and llms-output/.

Generalized from aspose.org's S-LG-03 llms-coverage skill (2026-08-29 sync).
Iterates config.yaml's sites: block, same generalization as llms_generate.py.

Usage:
    .venv/bin/python scripts/llms_generate.py --output llms-output   # first
    .venv/bin/python scripts/llms_coverage.py --output llms-output --report reports/llms-coverage.json
    .venv/bin/python scripts/llms_coverage.py --output llms-output --gate 95

Exit codes (only meaningful with --gate):
  0 -- all sites at or above the gate threshold
  1 -- at least one site below threshold
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config_loader import load_config, resolve_content_repo, ConfigError
from llms_common import is_eligible_page, iter_site_pages, parse_frontmatter


def coverage_for_site(content_root: Path, output_root: Path, site_type: str, content_path_template: str) -> dict:
    eligible = []
    missing = []
    for source_path in iter_site_pages(content_root, content_path_template):
        text = source_path.read_text(encoding="utf-8", errors="replace")
        frontmatter, _ = parse_frontmatter(text)
        if not is_eligible_page(frontmatter):
            continue
        rel_source = source_path.relative_to(content_root)
        eligible.append(rel_source.as_posix())
        expected_output = output_root / site_type / rel_source.with_suffix(".txt")
        if not expected_output.is_file():
            missing.append(rel_source.as_posix())

    total = len(eligible)
    covered = total - len(missing)
    pct = (covered / total * 100.0) if total else 100.0
    return {
        "site": site_type,
        "eligible_pages": total,
        "covered_pages": covered,
        "coverage_pct": round(pct, 1),
        "missing_pages": sorted(missing),
    }


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", default="llms-output", help="llms-output directory to audit")
    parser.add_argument("--report", default=None, help="Write JSON report to this path")
    parser.add_argument("--gate", type=float, default=None, help="Minimum coverage %% per site to pass")
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
    results = {}
    for site_type, site_cfg in sorted(sites.items()):
        if "content_path" not in site_cfg:
            continue
        results[site_type] = coverage_for_site(content_root, output_root, site_type, site_cfg["content_path"])

    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(results, indent=2), encoding="utf-8")

    all_ok = True
    for site_type, result in results.items():
        status = "PASS"
        if args.gate is not None and result["coverage_pct"] < args.gate:
            status = "FAIL"
            all_ok = False
        print(f"{site_type}: {result['coverage_pct']}% [{status}]")

    return 0 if (all_ok or args.gate is None) else 1


if __name__ == "__main__":
    sys.exit(main())
