"""
lib/example_verification/cli.py

CONTRACT: scripts/pipeline/lib/example_verification/cli.py
  purpose: thin argparse CLI over api.py -- `verify --file PATH --platform
           P [--family F] [--max-tier N] [--allow-acquire] [--json]`. The
           package's own command-line surface, following
           content_eval/cli.py's precedent of a package owning its own
           cli.py despite living under lib/ (example_verification is
           already a registered lib/ package per MT065; this is its
           entry point, not a new commands/{domain}/ script).
           MT072-2026-09-23-EXAMPLE-VERIFICATION-PRODUCTIONIZATION/TC-01.
  inputs:  argv
  outputs: exit 0 if every block is PASS/NOT-EXECUTABLE-LANG, 1 otherwise;
           stdout: human-readable per-block report, or --json (the
           to_legacy_s120() shape every existing consumer already knows)
  owner_domain: content-quality
  requires_test: true
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .api import verify_page
from .policy import Policy

_OK_STATUSES = frozenset({"PASS", "NOT-EXECUTABLE-LANG"})


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="example_verification")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("verify", help="Verify one markdown file's fenced code blocks.")
    p.add_argument("--file", required=True, help="Path to the markdown file to verify.")
    p.add_argument("--platform", required=True)
    p.add_argument("--family", default="")
    p.add_argument("--max-tier", type=int, default=None)
    p.add_argument("--allow-acquire", action="store_true",
                    help="Permit acquiring a real disposable environment (venv/npm/etc.).")
    p.add_argument("--json", action="store_true", help="Emit the to_legacy_s120() JSON shape.")
    return parser


def main(argv: "list[str] | None" = None) -> int:
    args = _build_parser().parse_args(argv)

    policy = Policy.for_platform(
        args.platform, max_tier=args.max_tier, allow_acquire=args.allow_acquire,
    )
    report = verify_page(
        Path(args.file), family=args.family, platform=args.platform, policy=policy,
    )

    ok = all(b.status in _OK_STATUSES for b in report.blocks)
    if args.json:
        print(json.dumps(report.to_legacy_s120(), indent=2))
    else:
        for b in report.blocks:
            detail = f" {b.reason or ''} {b.detail or ''}".rstrip()
            print(f"[{b.status}] block {b.identity.index} "
                  f"(lines {b.identity.start_line}-{b.identity.end_line}):{detail}")
        passed = sum(1 for b in report.blocks if b.status == "PASS")
        print(f"\n{passed}/{len(report.blocks)} PASS")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
