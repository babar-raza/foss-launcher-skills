#!/usr/bin/env python3
"""Member-level audit wrapper over the deterministic audit engine."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path


_PIPELINE_DIR = Path(__file__).resolve().parents[2]  # commands/diagnostics/ -> commands/ -> pipeline/
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))

from audit.reports import report_json, report_text  # noqa: E402
from audit.runner import audit_product  # noqa: E402


def run_truth_audit(
    family: str,
    platform: str,
    *,
    json_mode: bool = False,
    check_evidence: bool = True,
    check_snippets: bool = False,
) -> tuple[str, int]:
    findings = audit_product(
        family,
        platform,
        check_evidence=check_evidence,
        check_snippets=check_snippets,
    )
    products_checked = [f"{family}/{platform}"]
    output = report_json(findings, products_checked) if json_mode else report_text(findings, products_checked)
    exit_code = 1 if any(getattr(finding, "level", "") == "FAIL" for finding in findings) else 0
    return output, exit_code


def _default_output_path(family: str, platform: str, json_mode: bool) -> Path:
    date_str = datetime.now().strftime("%Y%m%d")
    suffix = "json" if json_mode else "md"
    return Path("reports") / "audit" / f"{family}-{platform}-truth-{date_str}.{suffix}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="truth_audit",
        description="Run member-level deterministic audit for a single product.",
    )
    parser.add_argument("family", help="Product family")
    parser.add_argument("platform", help="Platform")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of markdown")
    parser.add_argument("--output", type=Path, help="Optional report output path")
    parser.add_argument("--no-evidence", action="store_true", help="Skip evidence frontmatter checks")
    parser.add_argument("--check-snippets", action="store_true", help="Include snippet coverage checks")
    args = parser.parse_args(argv)

    output, exit_code = run_truth_audit(
        args.family,
        args.platform,
        json_mode=args.json,
        check_evidence=not args.no_evidence,
        check_snippets=args.check_snippets,
    )

    output_path = args.output or _default_output_path(args.family, args.platform, args.json)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(output, encoding="utf-8")

    sys.stdout.buffer.write(output.encode("utf-8"))
    sys.stdout.buffer.write(b"\n")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
