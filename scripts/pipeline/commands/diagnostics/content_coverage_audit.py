#!/usr/bin/env python3
"""content_coverage_audit.py — cumulative, delta-independent detector for
api_surface.json classes with no corresponding reference page.

Closes a real structural gap found live 2026-08-24 (mission-plan-the-end-to-
end-vast-hejlsberg.md, deep-reassessment pass): refresh_knowledge.py's
knowledge_delta.json is inherently CYCLE-SCOPED (comparing exactly the
previous merged/ snapshot to the current one, base_sha -> current_sha). If a
real knowledge-model advance is correctly captured by ONE refresh cycle but
content generation is never triggered for THAT cycle -- e.g. a different
session/lane advances the knowledge model (S-12/S-14, a knowledge-layer
operation) without also running batch_reference.py (a content-layer
operation) -- the delta becomes permanently invisible to every LATER cycle's
comparison, since each cycle only ever compares itself to its own immediate
predecessor, which by then already includes the unpropagated change.

Confirmed live for pdf/java: knowledge_delta.prev.json shows base_sha
12ae9e18 -> current_sha 3324fc12 with 121 new_apis (a new Structured Document
Model subsystem). The CURRENT knowledge_delta.json (3324fc12 -> 099e70a8)
shows zero new_apis, because that cycle's own predecessor (3324fc12) already
included the SDM classes -- the addition is "old news" to this narrow,
point-in-time diff, even though it was never reflected in a single reference
page. batch_reference.py's own default (no-flag) mode already implements the
correct, delta-independent generation logic (skip pages that already exist,
generate for anything that doesn't) -- confirmed by running it: it correctly
proposes generating 642 pages for pdf/java (out of 1157 candidates), 553 of
those in the mission's own release-relevant SDM subsystem or otherwise never
generated, against a sibling platform (pdf/net) needing only 27 of 881. The
missing piece was never generation capability -- it was DETECTION: nothing
in this pipeline ever surfaced "these classes have no page" independent of
which refresh cycle's delta happened to be the one currently on disk.

This script performs that direct, cumulative comparison for one product by
calling batch_reference.run(..., dry_run=True) (the same, single source of
truth batch_reference.py itself uses -- no candidate-selection logic is
duplicated here) and reporting its to_generate_names/to_update_names.
Detection only: never writes content, never calls batch_reference.py in a
mutating mode. Mirrors stale_detect.py's own philosophy (Task 11d, this same
mission) -- give every launched product an accurate, current count, so a
remediation decision can be made deliberately rather than discovered
product-by-product.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_PIPELINE_DIR = Path(__file__).resolve().parents[2]  # commands/diagnostics/ -> commands/ -> pipeline/
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))
_LIB_DIR = str(_PIPELINE_DIR / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from commands.content import batch_reference  # noqa: E402

# Relative to CWD, matching stale_detect.py's own --include-locales report
# path convention -- real usage always runs from the repo root; tests
# redirect via monkeypatch.chdir(tmp_path) rather than an absolute default.
_REPORT_ROOT = Path("reports/content_coverage")


def scan_product(family: str, platform: str) -> dict:
    """Run batch_reference.py's own dry-run for *family*/*platform* and
    report the resulting coverage gap. Never writes content -- dry_run=True
    unconditionally.

    Raises whatever batch_reference.run() itself raises (e.g. missing
    api_surface.json) -- this is a thin wrapper, not a re-implementation.
    """
    result = batch_reference.run(family, platform, dry_run=True)
    missing = result.get("to_generate_names", [])
    stale = result.get("to_update_names", [])  # only populated when update=True was also passed; empty here
    total_skipped = result.get("skipped", 0)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "family": family,
        "platform": platform,
        "total_candidates": len(missing) + total_skipped,
        "missing_page_count": len(missing),
        "existing_page_count": total_skipped,
        "missing_classes": missing,
    }


def write_report(report: dict, *, report_root: Path = _REPORT_ROOT) -> Path:
    report_root.mkdir(parents=True, exist_ok=True)
    path = report_root / f"{report['family']}-{report['platform']}.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="content_coverage_audit",
        description=(
            "Detect api_surface.json classes with no reference page, independent of "
            "any single refresh cycle's knowledge_delta.json (detection only, never writes content)"
        ),
    )
    parser.add_argument("family", help="Product family")
    parser.add_argument("platform", help="Platform")
    parser.add_argument("--json", action="store_true", help="Emit JSON to stdout instead of a summary line")
    args = parser.parse_args(argv)

    report = scan_product(args.family, args.platform)
    path = write_report(report)

    if args.json:
        sys.stdout.write(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    else:
        sys.stdout.write(
            f"{args.family}/{args.platform}: {report['missing_page_count']} of "
            f"{report['total_candidates']} classes have no reference page "
            f"(report: {path})\n"
        )
    return 1 if report["missing_page_count"] else 0


if __name__ == "__main__":
    sys.exit(main())
