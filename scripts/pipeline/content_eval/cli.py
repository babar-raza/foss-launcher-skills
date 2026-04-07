"""CLI for content_eval — the main evaluation pipeline."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import EVALUATOR_LOGIC_VERSION, __version__
from .config import ALL_EVALUATORS, DEFAULT_EVALUATORS
from .models import EvalReport, Finding, compute_grade_with_criticality


def _log(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


REPORTS_DIR = Path("reports") / "content_eval"


def _resolve_reports_dir(output_root: str | None) -> Path:
    """Resolve the report directory, allowing isolated temp roots for testing."""
    if output_root:
        return Path(output_root) / "content_eval"
    return REPORTS_DIR


def _load_knowledge(family: str, platform: str):
    """Load Knowledge from knowledge_core (shorter dependency chain than audit)."""
    _HERE = Path(__file__).resolve().parent.parent
    # sibling-import guard: content_eval sub-package needs pipeline root for knowledge_core.
    if str(_HERE) not in sys.path:
        sys.path.insert(0, str(_HERE))
    from knowledge_core import Knowledge  # noqa: E402
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

    # --skip-graded: filter out pages already graded with current knowledge
    if args.skip_graded:
        _HERE = Path(__file__).resolve().parent.parent
        if str(_HERE) not in sys.path:
            sys.path.insert(0, str(_HERE))
        from grade_writer import read_grade as _read_grade  # noqa: E402
        filtered = []
        for page in pages:
            key = (page.family, page.platform)
            if key not in knowledge_cache:
                if page.family and page.platform:
                    knowledge_cache[key] = _load_knowledge(page.family, page.platform)
                else:
                    knowledge_cache[key] = None
            k = knowledge_cache[key]
            stored = _read_grade(page.filepath)
            if (stored and stored["tier"] == "full"
                    and k and hasattr(k, "repo_sha")
                    and stored["model_sha"] == k.repo_sha
                    and stored.get("logic_version", "") == EVALUATOR_LOGIC_VERSION):
                continue  # Already graded with current knowledge, full evaluators, current logic
            filtered.append(page)
        skipped = len(pages) - len(filtered)
        if skipped:
            _log(f"Skipped {skipped} already-graded pages")
        pages = filtered

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
                import traceback as _tb
                _log(f"  ERROR in {eval_name} on {page.filepath}: {e}")
                _log(_tb.format_exc())
                report.findings.append(Finding(
                    level="WARN",
                    category="PIPELINE",
                    filepath=str(page.filepath),
                    line_no=0,
                    message=f"Evaluator '{eval_name}' raised {type(e).__name__}: {e}",
                    evaluator="cli",
                    suggestion="Check stderr for full traceback.",
                ))

        report.pages_evaluated += 1

    # Cross-page analysis
    if args.cross_page:
        from .cross_page.consistency import check_consistency
        _log("Running cross-page consistency checks...")
        report.findings.extend(check_consistency(pages))
        report.evaluators_run.append("cross_page_consistency")

    # Cross-family defect sweep
    if args.sweep and len(target_parts) == 2:
        from .cross_page.defect_sweep import extract_defect_signatures, run_sweep
        from .loader import load_all_products as _load_all

        sigs = extract_defect_signatures(report.findings)
        if sigs:
            _log(f"Sweep: {len(sigs)} defect signatures found, scanning other products...")
            all_products = _load_all()
            exclude = (target_parts[0], target_parts[1])

            def _evaluator_runner(page, eval_names):
                k = knowledge_cache.get((page.family, page.platform))
                if not k and page.family and page.platform:
                    k = _load_knowledge(page.family, page.platform)
                    knowledge_cache[(page.family, page.platform)] = k
                results = []
                for en in eval_names:
                    ec = get_evaluator(en)
                    if ec:
                        results.extend(ec().evaluate(page, k))
                return results

            sweep_findings = run_sweep(
                seed_findings=report.findings,
                all_products=all_products,
                evaluator_runner=_evaluator_runner,
                exclude=exclude,
            )
            report.findings.extend(sweep_findings)
            _log(f"Sweep: {len(sweep_findings)} additional findings across other products")
        else:
            _log("Sweep: no defect signatures to sweep")

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
    report_dir = _resolve_reports_dir(args.output_root)
    report_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    ext = "json" if args.format == "json" else "md"
    report_path = report_dir / f"eval-{timestamp}.{ext}"
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

    # --write-grade: persist computed grade into each page's frontmatter
    if args.write_grade:
        _HERE_g = Path(__file__).resolve().parent.parent
        if str(_HERE_g) not in sys.path:
            sys.path.insert(0, str(_HERE_g))
        from grade_writer import write_grade as _write_grade  # noqa: E402

        grade_counts: dict[str, int] = {}
        by_file = report.by_file()
        for page in pages:
            fp = page.filepath
            page_findings = by_file.get(str(fp), [])
            grade = compute_grade_with_criticality(page_findings)
            # Determine model_sha from cached knowledge
            k = knowledge_cache.get((page.family, page.platform))
            model_sha = k.repo_sha if k and hasattr(k, "repo_sha") else ""
            tier = "full" if k and getattr(k, "available", False) else "structural"
            _write_grade(fp, grade, model_sha=model_sha, evaluator_tier=tier,
                         logic_version=EVALUATOR_LOGIC_VERSION)
            grade_counts[grade] = grade_counts.get(grade, 0) + 1

        _log(f"  Grades written: {grade_counts}")

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


def _run_grade_summary(args):
    """Print grade distribution across all (or one) product."""
    _HERE_gs = Path(__file__).resolve().parent.parent
    if str(_HERE_gs) not in sys.path:
        sys.path.insert(0, str(_HERE_gs))
    from content_discovery import discover_content, discover_products  # noqa: E402  (R-1b)
    from grade_writer import read_grade as _read_grade  # noqa: E402

    if args.product:
        products = [(args.product[0], args.product[1])]
    else:
        products = sorted(discover_products())

    total = 0
    total_graded = 0
    overall_dist: dict[str, int] = {}
    rows = []

    for family, platform in products:
        files = discover_content(family, platform)
        dist: dict[str, int] = {}
        graded = 0
        for f in files:
            r = _read_grade(f)
            if r:
                graded += 1
                dist[r["grade"]] = dist.get(r["grade"], 0) + 1
                overall_dist[r["grade"]] = overall_dist.get(r["grade"], 0) + 1
        total += len(files)
        total_graded += graded
        rows.append((f"{family}/{platform}", len(files), graded, dict(dist)))

    # Collect ungraded files for --strict mode
    ungraded_files: list[str] = []
    if getattr(args, "strict", False):
        for family, platform in ([(args.product[0], args.product[1])] if args.product else sorted(discover_products())):
            for f in discover_content(family, platform):
                r = _read_grade(f)
                if not r:
                    ungraded_files.append(str(f))

    if args.json:
        import json as _json
        payload = {
            "total_files": total,
            "total_graded": total_graded,
            "distribution": overall_dist,
            "products": [
                {"product": r[0], "files": r[1], "graded": r[2], "distribution": r[3]}
                for r in rows
            ],
        }
        if getattr(args, "strict", False):
            payload["ungraded"] = ungraded_files
        print(_json.dumps(payload, indent=2))
    else:
        print(f"Grade Summary: {total_graded}/{total} files graded\n")
        print(f"{'Product':<25} {'Files':>5} {'Graded':>6}  A    B    C    D    F")
        print("-" * 72)
        for name, file_count, graded, dist in rows:
            parts = [f"{dist.get(g, 0):>4}" for g in ("A", "B", "C", "D", "F")]
            print(f"{name:<25} {file_count:>5} {graded:>6}  {'  '.join(parts)}")
        print("-" * 72)
        parts = [f"{overall_dist.get(g, 0):>4}" for g in ("A", "B", "C", "D", "F")]
        print(f"{'TOTAL':<25} {total:>5} {total_graded:>6}  {'  '.join(parts)}")

    if getattr(args, "strict", False) and ungraded_files:
        print(f"\nSTRICT: {len(ungraded_files)} file(s) missing grades:", file=sys.stderr)
        for uf in ungraded_files[:20]:
            print(f"  {uf}", file=sys.stderr)
        if len(ungraded_files) > 20:
            print(f"  ... and {len(ungraded_files) - 20} more", file=sys.stderr)
        raise SystemExit(1)


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
    eval_parser.add_argument("--output-root",
                             help="Override report root for isolated runs")
    eval_parser.add_argument("--write-grade", action="store_true",
                             help="Write computed grade to each page's frontmatter")
    eval_parser.add_argument("--skip-graded", action="store_true",
                             help="Skip pages already graded with current knowledge")
    eval_parser.add_argument("--sweep", action="store_true",
                             help="Sweep all products for same defect classes found in target")
    eval_parser.set_defaults(func=_run_evaluate)

    # diff command
    diff_parser = sub.add_parser("diff", help="Compare two evaluation reports")
    diff_parser.add_argument("old_report", help="Path to old JSON report")
    diff_parser.add_argument("new_report", help="Path to new JSON report")
    diff_parser.set_defaults(func=_run_diff)

    # grade-summary command
    gs_parser = sub.add_parser("grade-summary", help="Show grade distribution across content")
    gs_parser.add_argument("--product", nargs=2, metavar=("FAMILY", "PLATFORM"),
                           help="Filter to one product (e.g. --product slides python)")
    gs_parser.add_argument("--json", action="store_true", help="Output as JSON")
    gs_parser.add_argument("--strict", action="store_true",
                           help="Exit 1 if any discoverable file lacks a grade")
    gs_parser.set_defaults(func=_run_grade_summary)

    args = parser.parse_args(argv)
    args.func(args)
