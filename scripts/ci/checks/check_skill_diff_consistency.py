"""check_skill_diff_consistency.py — Warn when declared skills don't match PR diff patterns.

Compares "Skills invoked:" declarations in PR commit messages against the actual
files changed. Uses skill metadata (diff_pattern) to detect likely mismatches.

This is a WARNING-only check by design — false positives are possible when skills
are invoked for planning/assessment without producing file changes. The check flags
plausibly inaccurate declarations for human review.

Concrete case study: commit 8df7786f4 claimed S-48 (family-sync) but modified only
locale translation files — family-sync expects changes to family landing pages.

Usage:
  # Check all commits in the PR
  python scripts/ci/checks/check_skill_diff_consistency.py --pr-diff-files file1 file2 ...

Exit codes:
  0  No suspicious mismatches (or warnings only)
  0  Always exits 0 — this is a warning-only checker (use ::warning:: in CI)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent

# Skill diff patterns: maps skill ID to (expected_description, path_patterns)
# path_patterns are checked against the actual changed files
SKILL_DIFF_PATTERNS: dict[str, tuple[str, list[str]]] = {
    "S-48": (
        "family-sync: updates family landing pages for a product",
        [
            r"content/products\.aspose\.org/en/",
            r"content/[^/]+/en/[^/]+/_index\.md",
        ],
    ),
    "S-37": (
        "knowledge-enrich: generates enriched claims from scout artifacts",
        [
            r"knowledge/[^/]+/[^/]+/enriched_claims\.json",
            r"knowledge/[^/]+/[^/]+/scout/",
        ],
    ),
    "S-52": (
        "translate-page: translates a single English page to locales",
        [
            r"content/[^/]+/(?!en/)[a-z]{2}(-[A-Z]{2})?/",
        ],
    ),
    "S-53": (
        "translate-batch: translates all pages for a family/platform to locales",
        [
            r"content/[^/]+/(?!en/)[a-z]{2}(-[A-Z]{2})?/",
        ],
    ),
    "S-34": (
        "repo-scout: extracts truth from FOSS repository",
        [
            r"knowledge/[^/]+/[^/]+/scout/",
        ],
    ),
    "S-19": (
        "page-draft: drafts page content",
        [
            r"content/",
        ],
    ),
    "S-21": (
        "page-enhance: enhances page quality",
        [
            r"content/",
        ],
    ),
    "S-26": (
        "heal-page: heals low-quality page",
        [
            r"content/",
        ],
    ),
    "S-20": (
        "page-update: updates page after knowledge change",
        [
            r"content/",
        ],
    ),
}

# Skills that legitimately produce no file changes (assessment/gate skills)
ASSESSMENT_ONLY_SKILLS = {
    "S-01",  # path-guard: gate check, no file output
    "S-12",  # knowledge-diff: detection only
    "S-13",  # stale-detect: detection only
    "S-23",  # content-check: validation only
    "S-25",  # eval-page: evaluation only
    "S-32",  # content-audit: audit only
    "S-33",  # change-guard: gate check
    "S-38",  # truth-audit: verification only
    "S-43",  # gap-eval: evaluation only
    "S-44",  # gap-plan: planning only
    "S-45",  # gap-report: report generation
    "S-54",  # knowledge-bootstrap: pre-condition gate
    "S-55",  # no-downgrade-guard: internal gate
}

_ID_RE = re.compile(r"S-\d+", re.IGNORECASE)


def extract_skill_ids(text: str) -> list[str]:
    """Extract S-{n} IDs from text."""
    return [m.upper() for m in _ID_RE.findall(text)]


def check_consistency(
    declared_ids: list[str],
    changed_files: list[str],
) -> list[dict]:
    """Return list of warning dicts for potentially inconsistent declarations."""
    warnings = []

    for skill_id in declared_ids:
        sid = skill_id.upper()
        if sid not in SKILL_DIFF_PATTERNS:
            continue  # No pattern defined — skip
        if sid in ASSESSMENT_ONLY_SKILLS:
            continue  # Assessment skills don't produce file changes

        description, patterns = SKILL_DIFF_PATTERNS[sid]
        matched = any(
            any(re.search(pat, f) for pat in patterns)
            for f in changed_files
        )
        if not matched:
            warnings.append({
                "skill_id": sid,
                "description": description,
                "finding": f"Declared but no matching file changes found in diff",
                "expected_patterns": patterns,
                "files_checked": len(changed_files),
            })

    return warnings


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]

    changed_files = []
    declared_ids_from_args = []
    skill_ids_flag = False

    i = 0
    while i < len(args):
        if args[i] == "--pr-diff-files":
            i += 1
            while i < len(args) and not args[i].startswith("--"):
                changed_files.append(args[i])
                i += 1
        elif args[i] == "--skill-ids":
            i += 1
            while i < len(args) and not args[i].startswith("--"):
                declared_ids_from_args.append(args[i])
                i += 1
            skill_ids_flag = True
        else:
            changed_files.append(args[i])
            i += 1

    if not changed_files and not declared_ids_from_args:
        print("Usage: check_skill_diff_consistency.py --pr-diff-files file1 ... [--skill-ids S-xx ...]")
        return 0

    # If skill IDs not provided as args, try reading from stdin or PR commit messages
    if not declared_ids_from_args:
        # Attempt to read from git log if available
        import subprocess
        try:
            result = subprocess.run(
                ["git", "log", "origin/main...HEAD", "--format=%B", "--", "content/**/*.md"],
                capture_output=True, text=True, cwd=REPO_ROOT
            )
            declared_ids_from_args = extract_skill_ids(result.stdout)
        except (subprocess.SubprocessError, FileNotFoundError):
            pass

    if not declared_ids_from_args:
        print("No skill IDs to check consistency for.")
        return 0

    warnings = check_consistency(declared_ids_from_args, changed_files)

    if warnings:
        print(f"\nSKILL-DIFF CONSISTENCY: {len(warnings)} potential mismatch(es) detected:")
        for w in warnings:
            print(f"\n  Skill {w['skill_id']} ({w['description']})")
            print(f"    Finding: {w['finding']}")
            print(f"    Expected one of: {w['expected_patterns']}")
            print(f"    Files checked: {w['files_checked']}")
        print("\n  NOTE: This is a warning — skills may be invoked without producing matching")
        print("  file changes (e.g., in assessment or planning contexts). Review the")
        print("  declarations and ensure accuracy. See proof bundle for case study:")
        print("  reports/proof-bundles/observability-case-study-8df7786f4.json")
    else:
        print("Skill-diff consistency: no suspicious mismatches detected.")

    return 0  # Always exits 0 — warning only


if __name__ == "__main__":
    raise SystemExit(main())
