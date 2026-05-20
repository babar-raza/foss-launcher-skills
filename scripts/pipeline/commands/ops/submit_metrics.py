# Adapted from aspose.org
"""CLI entry point for Agent Metrics API submission.

Usage:
    python submit_metrics.py --dry-run --row-json <path>
    python submit_metrics.py --export-json <out_path> --row-json <path>
    python submit_metrics.py --test-submit --row-json <path>
    python submit_metrics.py --production-submit --owner-approved --row-json <path>

Modes (mutually exclusive, default: --dry-run):
    --dry-run           Validate only. No HTTP. No file written.
    --export-json PATH  Write validated payload to PATH. No HTTP.
    --test-submit       Submit via HTTP (test-marked row required).
    --production-submit Submit to production (--owner-approved also required).

Required for submit modes:
    Env vars: AGENT_METRICS_ENDPOINT, AGENT_METRICS_TOKEN

The token is never printed to stdout/stderr.

Slice 7 of Agent Metrics Integration (METRICS-PLAN-001 v7.1).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure scripts/pipeline is on sys.path when run as a script
_PIPELINE_ROOT = Path(__file__).resolve().parents[3]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

from commands.ops.metrics_schema import (
    MetricsRow,
    generate_run_id,
    now_iso8601,
    row_to_dict,
)
from commands.ops.metrics_submitter import (
    ENV_ENDPOINT,
    ENV_TOKEN,
    MODE_DRY_RUN,
    MODE_EXPORT_JSON,
    MODE_PRODUCTION_SUBMIT,
    MODE_TEST_SUBMIT,
    MetricsSubmitter,
    SubmitResult,
)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Submit or dry-run an Agent Metrics API row.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    mode_group = p.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="(default) Validate only. No HTTP call, no file written.",
    )
    mode_group.add_argument(
        "--export-json",
        metavar="PATH",
        help="Write validated JSON payload to PATH. No HTTP call.",
    )
    mode_group.add_argument(
        "--test-submit",
        action="store_true",
        help="Submit via HTTP. Row must be test-marked (job_type=test).",
    )
    mode_group.add_argument(
        "--production-submit",
        action="store_true",
        help="Submit to production. Requires --owner-approved and env vars.",
    )

    p.add_argument(
        "--owner-approved",
        action="store_true",
        help="Required for --production-submit.",
    )
    p.add_argument(
        "--row-json",
        metavar="PATH",
        required=True,
        help="Path to a JSON file containing the MetricsRow payload.",
    )
    p.add_argument(
        "--show-endpoint",
        action="store_true",
        help="Print redacted endpoint in output (never prints token).",
    )
    return p


def load_row(path: str) -> MetricsRow:
    """Load MetricsRow from a JSON file."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return MetricsRow(**data)


def resolve_mode(args: argparse.Namespace) -> tuple[str, str | None]:
    """Return (mode, export_path)."""
    if args.export_json:
        return MODE_EXPORT_JSON, args.export_json
    if args.test_submit:
        return MODE_TEST_SUBMIT, None
    if args.production_submit:
        return MODE_PRODUCTION_SUBMIT, None
    return MODE_DRY_RUN, None


def print_result(result: SubmitResult, show_endpoint: bool = False) -> None:
    print(f"mode:            {result.mode}")
    print(f"submitted:       {result.submitted}")
    print(f"row_valid:       {result.row_valid}")
    print(f"status_code:     {result.status_code}")
    print(f"response:        {result.response_summary}")
    if result.response_run_id is not None:
        print(f"run_id:          {result.response_run_id}")
    print(f"output_path:     {result.output_path}")
    if show_endpoint and result.redacted_endpoint:
        print(f"endpoint:        {result.redacted_endpoint}")
    if result.error:
        print(f"error:           {result.error}")
    if result.validation_errors:
        print("validation_errors:")
        for e in result.validation_errors:
            print(f"  - {e}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        row = load_row(args.row_json)
    except Exception as exc:
        print(f"ERROR loading row JSON: {exc}", file=sys.stderr)
        return 1

    mode, export_path = resolve_mode(args)
    submitter = MetricsSubmitter(mode=mode, output_path=export_path)
    result = submitter.submit(row, owner_approved=args.owner_approved)

    print_result(result, show_endpoint=args.show_endpoint)
    return 0 if result.submitted or mode in (MODE_DRY_RUN, MODE_EXPORT_JSON) else 1


if __name__ == "__main__":
    sys.exit(main())
