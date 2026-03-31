"""CLI for content_eval — the main evaluation pipeline."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .config import ALL_EVALUATORS, DEFAULT_EVALUATORS
from .models import EvalReport, Finding

_PIPELINE = Path(__file__).resolve().parent.parent  # scripts/pipeline/
import sys as _sys
if str(_PIPELINE) not in _sys.path:
    _sys.path.insert(0, str(_PIPELINE))

_SCRIPTS = _PIPELINE.parent  # scripts/
if str(_SCRIPTS) not in _sys.path:
    _sys.path.insert(0, str(_SCRIPTS))

from config_loader import resolve_reports_root as _resolve_reports_root  # noqa: E402


def _log(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def _load_knowledge(family: str, platform: str):
    """Load Knowledge from audit.py."""
    from audit import Knowledge  # noqa: E402
    return Knowledge(family, platform)


def _run_evaluate(args):
    """Run the evaluation pipeline."""
    from .evaluators import _ensure_loaded, get_evaluator
    from .loader import load_all_products, load_files, load_pages
    from .reporters.json_report import generate_json
    from .reporters.markdown import generate_markdown
    from .remediation.planner import plan_remediation

    _ensure_loaded()

    # Determine evaluator set
    if args.evaluators:
        evaluator_names = [e.strip() for e in args.evaluators.split(",")]
    else:
        evaluator_names = DEFAULT_EVALUATORS

    # Validate evaluator names
    for name in evaluator_names:
        if name not in ALL_EVALUATORS:
            _log(f"Unknown evaluator: {name}. Available: {ALL_EVALUATORS}")
            sys.exit(1)

    # Load pages
    pages = []
    target_parts = args.target  # list from nargs="*"
    target_str = " ".join(target_parts)

    if args.files:
        pages = load_files(args.files)
        _log(f"Loaded {len(pages)} files")
    elif target_parts == ["all"]:
        all_products = load_all_products()
        for product_pages in all_products.values():
            pages.extend(product_pages)
        _log(f"Loaded {len(pages)} pages across {len(all_products)} products")
    elif len(target_parts) == 2:
        family, platform = target_parts
        pages = load_pages(family, platform)
        _log(f"Loaded {len(pages)} pages for {family}/{platform}")
    elif len(target_parts) == 1:
        family = target_parts[0]
        all_products = load_all_products()
        for (f, p), product_pages in all_products.items():
            if f == family:
                pages.extend(product_pages)
        _log(f"Loaded {len(pages)} pages for {family}")
    else:
        _log(f"Invalid target: {target_str}. Use 'family platform' or 'all'")
        sys.exit(1)

    if not pages:
        _log("No pages found")
        sys.exit(0)

    if args.dry_run:
        _log(f"Dry run: would evaluate {len(pages)} pages with {evaluator_names}")
        for p in pages[:10]:
            _log(f"  {p.filepath}")
        if len(pages) > 10:
            _log(f"  ... and {len(pages) - 10} more")
        return

    # Run evaluators
    report = EvalReport(
        evaluators_run=evaluator_names,
        scope={
            "target": target_str if not args.files else "files",
            "files": args.files or [],
        },
    )

    # Cache knowledge per product
    knowledge_cache: dict[tuple[str, str], object] = {}

    for page in pages:
        key = (page.family, page.platform)
        if key not in knowledge_cache:
            if page.family and page.platform:
                knowledge_cache[key] = _load_knowledge(page.family, page.platform)
            else:
                knowledge_cache[key] = None

        knowledge = knowledge_cache[key]

        for eval_name in evaluator_names:
            evaluator_cls = get_evaluator(eval_name)
            evaluator = evaluator_cls()
            try:
                findings = evaluator.evaluate(page, knowledge)
                report.findings.extend(findings)
            except Exception as e:
                _log(f"  ERROR in {eval_name} on {page.filepath}: {e}")

        report.pages_evaluated += 1

    # Cross-page analysis
    if args.cross_page:
        from .cross_page.consistency import check_consistency
        _log("Running cross-page consistency checks...")
        report.findings.extend(check_consistency(pages))
        report.evaluators_run.append("cross_page_consistency")

    # Generate remediation plan
    remediation = None
    if args.remediation:
        remediation = plan_remediation(report)

    # Generate report
    if args.format == "json":
        output = generate_json(report, remediation)
    else:
        output = generate_markdown(report, remediation)

    # Write to file
    REPORTS_DIR = _resolve_reports_root() / "content_eval"
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    ext = "json" if args.format == "json" else "md"
    report_path = REPORTS_DIR / f"eval-{timestamp}.{ext}"
    report_path.write_text(output, encoding="utf-8")

    # Also print to stdout (handle Windows encoding)
    sys.stdout.buffer.write(output.encode("utf-8"))
    sys.stdout.buffer.write(b"\n")

    # Summary to stderr
    _log(f"\nEvaluation complete:")
    _log(f"  Pages: {report.pages_evaluated}")
    _log(f"  FAIL: {len(report.fails)}")
    _log(f"  WARN: {len(report.warns)}")
    _log(f"  INFO: {len(report.infos)}")
    _log(f"  Report: {report_path}")

    # Exit code
    if args.strict and report.fails:
        sys.exit(1)


def _run_diff(args):
    """Compare two evaluation reports."""
    old = json.loads(Path(args.old_report).read_text(encoding="utf-8"))
    new = json.loads(Path(args.new_report).read_text(encoding="utf-8"))

    old_ids = {f["id"] for f in old.get("findings", [])}
    new_ids = {f["id"] for f in new.get("findings", [])}

    added = new_ids - old_ids
    removed = old_ids - new_ids
    unchanged = old_ids & new_ids

    print(f"Report Diff")
    print(f"  New findings: {len(added)}")
    print(f"  Resolved findings: {len(removed)}")
    print(f"  Unchanged: {len(unchanged)}")
    print()

    if added:
        new_findings = [f for f in new["findings"] if f["id"] in added]
        print("## New Findings")
        for f in new_findings:
            print(f"  [{f['level']}] {f['category']} {f['file']}:{f['line']} — {f['message']}")
    if removed:
        old_findings = [f for f in old["findings"] if f["id"] in removed]
        print("\n## Resolved Findings")
        for f in old_findings:
            print(f"  [{f['level']}] {f['category']} {f['file']}:{f['line']} — {f['message']}")


def main(argv: list[str] | None = None):
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="content_eval",
        description=f"Content evaluation against repo truth v{__version__}",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # evaluate command
    eval_parser = sub.add_parser("evaluate", help="Run evaluation pipeline")
    eval_parser.add_argument("target", nargs="*", default=["all"],
                             help="'family platform', 'family', or 'all'")
    eval_parser.add_argument("--files", nargs="+", help="Specific files to evaluate")
    eval_parser.add_argument("--evaluators", help="Comma-separated evaluator names")
    eval_parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    eval_parser.add_argument("--strict", action="store_true",
                             help="Exit 1 on any FAIL finding")
    eval_parser.add_argument("--dry-run", action="store_true",
                             help="Print what would be evaluated")
    eval_parser.add_argument("--cross-page", action="store_true",
                             help="Enable cross-page consistency analysis")
    eval_parser.add_argument("--remediation", action="store_true",
                             help="Include remediation plan")
    eval_parser.set_defaults(func=_run_evaluate)

    # diff command
    diff_parser = sub.add_parser("diff", help="Compare two evaluation reports")
    diff_parser.add_argument("old_report", help="Path to old JSON report")
    diff_parser.add_argument("new_report", help="Path to new JSON report")
    diff_parser.set_defaults(func=_run_diff)

    args = parser.parse_args(argv)
    args.func(args)
