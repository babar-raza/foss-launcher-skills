"""check_install_recipe_safety_fails.py — PKGINSTALL-GRADE-SAFETY-OVERRIDE
stopgap (MT066 plan section R.3.3).

Hard-blocks a PR touching a content page carrying either install_recipe
safety FAIL (_verify_publish_channel_claims / _verify_no_unpublished_
disclosure), independent of that page's currently-stored grade -- ships
immediately, ahead of (and independent from) the full SAFETY_OVERRIDE_
FINDINGS mechanism (content_eval/config.py, GRADE_CONTRACT.md §10) landing
and every future grade write already reflecting these FAILs on its own.

Both checks are already real and tested (RC-W1-003, ST-054 TC-14); this
script adds no new detection logic, only a gate that runs them on PR-touched
files regardless of grade staleness -- the exact gap that let 89 real
PUBLISH-CLAIM-CONTRADICTION-001 findings ship on pages graded A (confirmed
2026-09-10, backlog/BACKLOG.md).

Retire this script once GRADE_CONTRACT.md §10's mechanism has been live
long enough that every touched page's own grade write already reflects
these FAILs -- at that point this becomes a redundant second check on the
same signal, not a gap-closer.

CLI:
    PYTHONPATH=scripts/pipeline python scripts/ci/checks/check_install_recipe_safety_fails.py \\
        content/docs.aspose.org/en/barcode/python/getting-started/installation.md
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

_PIPELINE_ROOT = Path(__file__).resolve().parents[2] / "pipeline"
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

from content_eval.loader import load_files  # noqa: E402
from content_eval.evaluators.install_recipe import InstallRecipeEvaluator  # noqa: E402


def check_files(file_paths: "list[str]") -> "list[dict[str, Any]]":
    """Run only the 2 safety checks (never _verify_install_accuracy) against
    every given file. Non-.md files and files that fail to load are silently
    skipped by content_eval.loader.load_files() itself -- matching that
    loader's own existing, already-relied-upon behavior."""
    pages = load_files(file_paths)
    evaluator = InstallRecipeEvaluator()
    findings: "list[dict[str, Any]]" = []
    for page in pages:
        for f in evaluator._verify_publish_channel_claims(page):
            findings.append({"path": str(page.filepath), "category": f.category, "message": f.message})
        for f in evaluator._verify_no_unpublished_disclosure(page):
            findings.append({"path": str(page.filepath), "category": f.category, "message": f.message})
    return findings


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="*", help="Content files to check (PR-touched .md files)")
    args = parser.parse_args(argv)

    if not args.files:
        print("No files given -- nothing to check.")
        return 0

    findings = check_files(args.files)
    if not findings:
        print(f"OK: 0 install_recipe safety FAIL(s) across {len(args.files)} file(s) checked.")
        return 0

    print(
        f"BLOCKED: {len(findings)} install_recipe safety FAIL(s), independent of stored grade:",
        file=sys.stderr,
    )
    for f in findings:
        print(f"  {f['path']} [{f['category']}]: {f['message']}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
