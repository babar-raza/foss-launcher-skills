"""batch_regrade.py — Re-grade all Grade C reference pages using updated evaluators.

Usage:
    PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/batch_regrade.py
    PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/batch_regrade.py --dry-run
    PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/batch_regrade.py --family slides --platform net

Reads all non-draft Grade C reference pages, re-runs evaluators, writes updated grade.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
if str(_HERE / "lib") not in sys.path:
    sys.path.insert(0, str(_HERE / "lib"))

from knowledge_core import Knowledge  # noqa: E402
from content_discovery import infer_product  # noqa: E402
from token_ops import extract_tokens, verify_tokens  # noqa: E402
from content_eval.models import Page, compute_grade  # noqa: E402
from content_eval.evaluators.description_completeness import DescriptionCompletenessEvaluator  # noqa: E402
from content_eval.evaluators.content_substance import ContentSubstanceEvaluator  # noqa: E402
from grade_writer import read_grade, write_grade  # noqa: E402


def regrade_file(fp: Path, knowledge: Knowledge, dry_run: bool = False) -> str:
    """Re-grade a single file. Returns new_grade or 'SKIP'."""
    current = read_grade(fp)
    if not current or current.get("grade") != "C":
        return "SKIP"

    try:
        tokens = extract_tokens(fp, knowledge.platform)
        findings = verify_tokens(tokens, knowledge, fp)
    except Exception as e:
        print(f"  ERROR verify_tokens {fp}: {e}", file=sys.stderr)
        return "ERROR"

    fails = [f for f in findings if f.level == "FAIL"]
    if fails:
        return "SKIP_AUDIT_FAIL"

    warn_count = sum(1 for f in findings if f.level == "WARN")
    fail_count = 0

    try:
        page = Page.load(fp)
        dc_findings = DescriptionCompletenessEvaluator().evaluate(page, knowledge)
        cs_findings = ContentSubstanceEvaluator().evaluate(page, knowledge)
        extra = dc_findings + cs_findings
        fail_count += sum(1 for f in extra if f.level == "FAIL")
        warn_count += sum(1 for f in extra if f.level == "WARN")
    except Exception as e:
        print(f"  ERROR evaluators {fp}: {e}", file=sys.stderr)
        return "ERROR"

    new_grade = compute_grade(fail_count, warn_count)
    if new_grade == "C":
        return "UNCHANGED_C"

    if dry_run:
        print(f"  DRY-RUN {fp}: C -> {new_grade} (fail={fail_count} warn={warn_count})")
        return f"WOULD_UPDATE_{new_grade}"

    result = write_grade(fp, new_grade, model_sha=knowledge.repo_sha)
    if result:
        return new_grade
    return "ERROR"


def main():
    parser = argparse.ArgumentParser(description="Re-grade Grade C reference pages")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--family", help="Restrict to one family (e.g. slides)")
    parser.add_argument("--platform", help="Restrict to one platform (e.g. net)")
    args = parser.parse_args()

    ref_root = Path(__file__).resolve().parents[2] / "content" / "reference.aspose.org" / "en"

    # Collect Grade C pages
    candidates = []
    for f in sorted(ref_root.rglob("*.md")):
        g = read_grade(f)
        if g and g.get("grade") == "C":
            candidates.append(f)

    print(f"Found {len(candidates)} Grade C reference pages")

    # Apply family/platform filter
    if args.family or args.platform:
        filtered = []
        for f in candidates:
            family, platform = infer_product(f)
            if args.family and family != args.family:
                continue
            if args.platform and platform != args.platform:
                continue
            filtered.append(f)
        candidates = filtered
        print(f"Filtered to {len(candidates)} pages (family={args.family} platform={args.platform})")

    # Group by product to avoid loading Knowledge repeatedly
    from collections import defaultdict
    by_product: dict[tuple, list] = defaultdict(list)
    for f in candidates:
        family, platform = infer_product(f)
        by_product[(family, platform)].append(f)

    counts: dict[str, int] = {}
    for (family, platform), files in sorted(by_product.items()):
        print(f"\n  {family}/{platform}: {len(files)} Grade C pages")
        try:
            knowledge = Knowledge(family, platform)
            if not knowledge.available:
                print(f"    SKIP: no knowledge model")
                continue
        except Exception as e:
            print(f"    ERROR loading knowledge: {e}")
            continue

        for fp in files:
            status = regrade_file(fp, knowledge, dry_run=args.dry_run)
            counts[status] = counts.get(status, 0) + 1
            if status not in ("SKIP", "SKIP_AUDIT_FAIL", "UNCHANGED_C"):
                print(f"    {status}: {fp.name}")

    print(f"\n=== Summary ===")
    for k, v in sorted(counts.items()):
        print(f"  {k}: {v}")

    upgraded = sum(v for k, v in counts.items() if k in ("A", "B"))
    print(f"\n  Grade C -> A/B: {upgraded} pages")
    remaining_c = counts.get("UNCHANGED_C", 0)
    print(f"  Remaining Grade C: {remaining_c} pages")


if __name__ == "__main__":
    main()
