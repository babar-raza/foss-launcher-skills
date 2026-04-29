#!/usr/bin/env python3
"""Stage 8 — Readiness Scorecard for launch-product orchestration.

Collects per-subdomain translation coverage and content grades,
then prints a READY TO SHIP / NOT READY verdict.

Translation coverage is reported informationally but does not block the verdict.

Usage:
    python scripts/pipeline/readiness_scorecard.py --family slides --platform python
    python scripts/pipeline/readiness_scorecard.py --family slides --platform python --set-checkpoint
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_DEFAULT_ROOT = Path(__file__).resolve().parents[4]
_ROOT = _DEFAULT_ROOT
_CONTENT = _ROOT / "content"
_PHASE_STATE = _ROOT / "reports" / "phase_state.json"


def configure(*, repo_root: "Path | str | None" = None) -> None:
    """Override module-level path constants for testing."""
    global _ROOT, _CONTENT, _PHASE_STATE
    _ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_ROOT
    _CONTENT = _ROOT / "content"
    _PHASE_STATE = _ROOT / "reports" / "phase_state.json"

_SUBDOMAINS = ["products.aspose.org", "docs.aspose.org", "kb.aspose.org",
               "reference.aspose.org", "blog.aspose.org"]

_HGATES = ["h01", "h02", "h03", "h04", "h05"]
_HGATE_NAMES = {
    "h01": "Human prose review",
    "h02": "Reference accuracy",
    "h03": "Format table spot-check",
    "h04": "Link validation",
    "h05": "License accuracy",
}

_LOCALES = [
    "ar", "bg", "ca", "cs", "da", "de", "el", "es", "fa", "fi",
    "fr", "he", "hi", "hr", "hu", "id", "it", "ja", "ko", "lt",
    "lv", "ms", "nl", "no", "pl", "pt", "ro", "ru", "sk", "sr",
    "sv", "th", "tr", "uk", "vi", "zh",
]



def _count_locale_coverage(site: str, family: str, platform: str) -> dict:
    """Count how many of the 36 locales have at least one translated file."""
    site_root = _CONTENT / site
    locales_present = set()
    total_files = 0

    if site == "blog.aspose.org":
        # Blog: content/blog.aspose.org/{family}/{platform}/{post}/index.{locale}.md
        blog_root = site_root / family / platform
        if blog_root.is_dir():
            for md in blog_root.rglob("index.*.md"):
                # Extract locale from index.{locale}.md
                m = re.match(r"index\.([a-z]{2})\.md$", md.name)
                if m and m.group(1) in _LOCALES:
                    locales_present.add(m.group(1))
                    total_files += 1
    else:
        # Standard: content/{site}/{locale}/{family}/{platform}/
        for locale in _LOCALES:
            locale_dir = site_root / locale / family / platform
            if locale_dir.is_dir():
                files = list(locale_dir.rglob("*.md"))
                if files:
                    locales_present.add(locale)
                    total_files += len(files)

    return {
        "locales_present": len(locales_present),
        "total_locales": len(_LOCALES),
        "coverage": len(locales_present) / len(_LOCALES) if _LOCALES else 0,
        "total_files": total_files,
    }


def _count_en_pages(site: str, family: str, platform: str) -> int:
    """Count English source pages for a subdomain."""
    site_root = _CONTENT / site
    if site == "blog.aspose.org":
        blog_root = site_root / family / platform
        if not blog_root.is_dir():
            return 0
        return len(list(blog_root.rglob("index.md")))
    else:
        en_root = site_root / "en" / family / platform
        if not en_root.is_dir():
            # products has family directly under en (no platform for some)
            en_root = site_root / "en" / family
            if not en_root.is_dir():
                return 0
        return len(list(en_root.rglob("*.md")))


def _collect_grades(family: str, platform: str) -> dict:
    """Collect content grades from frontmatter across all EN pages."""
    grades = {"A": 0, "B": 0, "C": 0, "D": 0, "F": 0, "ungraded": 0}
    grade_re = re.compile(r"^grade:\s*([A-F])\s*$", re.MULTILINE)

    for site in _SUBDOMAINS:
        site_root = _CONTENT / site
        if site == "blog.aspose.org":
            search_root = site_root / family / platform
        else:
            search_root = site_root / "en" / family / platform
            if not search_root.is_dir():
                search_root = site_root / "en" / family

        if not search_root.is_dir():
            continue

        for md in search_root.rglob("*.md"):
            if md.name.startswith("index.") and md.name != "index.md":
                continue  # skip locale files in blog
            try:
                text = md.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            m = grade_re.search(text[:2000])  # grades are in frontmatter
            if m:
                grades[m.group(1)] += 1
            else:
                grades["ungraded"] += 1

    return grades


def _read_hgate_signoffs(family: str, platform: str) -> dict[str, str]:
    """Read human review gate sign-off results.

    Returns dict mapping gate id (h01..h05) to result (PASS/FAIL/CONDITIONAL/"").
    Empty string means no sign-off file found or sign-off not completed.
    """
    review_dir = _ROOT / "reports" / "human-review"
    results: dict[str, str] = {}
    for gate in _HGATES:
        sample_file = review_dir / f"{family}-{platform}-{gate}-sample.md"
        if not sample_file.is_file():
            results[gate] = ""
            continue
        try:
            text = sample_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            results[gate] = ""
            continue
        # Normalize CRLF → LF and strip inline comments before parsing
        text = text.replace("\r\n", "\n")
        text = re.sub(r"#[^\n]*$", "", text, flags=re.MULTILINE)
        # Parse the YAML sign-off block (case-insensitive)
        m = re.search(
            r'^result:\s*"?(PASS|FAIL|CONDITIONAL)"?\s*$',
            text,
            re.MULTILINE | re.IGNORECASE,
        )
        results[gate] = m.group(1).upper() if m else ""
    return results


def _read_checkpoints(family: str, platform: str) -> dict:
    """Read checkpoint state for this product."""
    if not _PHASE_STATE.is_file():
        return {}
    with open(_PHASE_STATE, encoding="utf-8") as f:
        data = json.load(f)
    key = f"{family}/{platform}"
    entry = data.get(key, {})
    return entry.get("values", {})


def _set_checkpoint(family: str, platform: str, key: str, value: str):
    """Set a checkpoint via project_phase_store CLI."""
    import subprocess
    cmd = [sys.executable, str(_ROOT / "scripts" / "pipeline" / "project_phase_store.py"),
           "set", family, platform, key, value]
    subprocess.run(cmd, check=True, capture_output=True)


def compute_verdict(
    grades: dict[str, int],
    coverage: dict[str, dict],
    checkpoints: dict,
    hgate_results: dict[str, str],
    *,
    skip_human_review: bool = False,
) -> tuple[bool, list[str]]:
    """Compute launch readiness verdict. Pure function — no I/O, no sys.exit.

    Args:
        grades: grade-letter → count, e.g. {"A": 5, "B": 3, "D": 1, "F": 0, ...}
        coverage: subdomain → {"locales_present": n, "total_locales": 36, "coverage": 0.5}
        checkpoints: pipeline checkpoint dict (keys like "truth_audit_done")
        hgate_results: gate_id → "PASS" | "FAIL" | "CONDITIONAL" | ""
        skip_human_review: if True, skip H-gate criterion

    Returns:
        (ready: bool, blockers: list[str])
    """
    blockers: list[str] = []

    # Criterion 1: 0 D/F pages
    df_count = grades.get("D", 0) + grades.get("F", 0)
    if df_count > 0:
        blockers.append(f"{df_count} page(s) graded D or F")

    # Criterion 2: key checkpoints
    if not checkpoints.get("truth_audit_done"):
        blockers.append("truth_audit_done checkpoint not set")

    # Criterion 3: human review gates (H-01 through H-05)
    if not skip_human_review:
        for gate in _HGATES:
            result = hgate_results.get(gate, "")
            if result == "PASS":
                continue
            elif result == "FAIL":
                blockers.append(f"{_HGATE_NAMES[gate]} ({gate.upper()}): FAIL")
            elif result == "CONDITIONAL":
                blockers.append(f"{_HGATE_NAMES[gate]} ({gate.upper()}): CONDITIONAL — requires follow-up")
            else:
                blockers.append(
                    f"{_HGATE_NAMES[gate]} ({gate.upper()}): not reviewed."
                )

    ready = len(blockers) == 0
    return ready, blockers


def main():
    parser = argparse.ArgumentParser(description="Stage 8 — Launch Readiness Scorecard")
    parser.add_argument("--family", required=True)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--set-checkpoint", action="store_true",
                        help="Set readiness_done=true if READY TO SHIP")
    parser.add_argument("--json", action="store_true",
                        help="Output JSON instead of human-readable text")
    parser.add_argument("--skip-human-review", action="store_true",
                        help="Skip H-gate checks (development use only)")
    args = parser.parse_args()

    family = args.family
    platform = args.platform

    # Prerequisite check
    try:
        from core.prereqs import require_all
        require_all(family, platform)
    except SystemExit:
        raise
    except Exception:
        pass  # prereqs is best-effort

    # Collect data
    checkpoints = _read_checkpoints(family, platform)
    grades = _collect_grades(family, platform)
    coverage = {}
    for site in _SUBDOMAINS:
        coverage[site] = _count_locale_coverage(site, family, platform)

    # Evaluate readiness criteria
    hgate_results = _read_hgate_signoffs(family, platform)
    if args.skip_human_review:
        print(f"  AUDIT: --skip-human-review used for {family}/{platform}", file=sys.stderr)
    ready, blockers = compute_verdict(
        grades, coverage, checkpoints, hgate_results,
        skip_human_review=args.skip_human_review,
    )
    verdict = "READY TO SHIP" if ready else "NOT READY"

    if args.json:
        result = {
            "family": family,
            "platform": platform,
            "verdict": verdict,
            "ready": ready,
            "grades": grades,
            "coverage": coverage,
            "checkpoints": {k: v for k, v in checkpoints.items()
                           if k.endswith("_done")},
            "blockers": blockers,
            "human_review": hgate_results,
            "skip_human_review": args.skip_human_review,
        }
        print(json.dumps(result, indent=2))
    else:
        print(f"=== LAUNCH READINESS: {family}/{platform} ===\n")

        # Grades
        total_graded = sum(v for k, v in grades.items() if k != "ungraded")
        print("Content grades:")
        for g in ["A", "B", "C", "D", "F"]:
            print(f"  {g}: {grades[g]}")
        if grades["ungraded"]:
            print(f"  Ungraded: {grades['ungraded']}")
        print()

        # Translation coverage
        print("Translation coverage (informational — not a launch blocker):")
        for site in _SUBDOMAINS:
            cov = coverage[site]
            en_pages = _count_en_pages(site, family, platform)
            print(f"  {site:25s} {cov['locales_present']:2d}/{cov['total_locales']} locales "
                  f"({cov['coverage']:5.1%})  {cov['total_files']:4d} files  "
                  f"[{en_pages} EN pages]")
        print()

        # Human review gates
        print("Human review gates:")
        if args.skip_human_review:
            print("  (skipped via --skip-human-review)")
        else:
            for gate in _HGATES:
                result = hgate_results.get(gate, "")
                status = result if result else "NOT REVIEWED"
                mark = "+" if result == "PASS" else "-"
                print(f"  [{mark}] {gate.upper()} {_HGATE_NAMES[gate]}: {status}")
        print()

        # Checkpoints
        print("Checkpoints:")
        for ck in ["knowledge_ready", "truth_audit_done",
                    "quality_done", "readiness_done"]:
            val = checkpoints.get(ck, False)
            mark = "+" if val else "-"
            print(f"  [{mark}] {ck}")
        print()

        # Verdict
        print(f">>> {verdict} <<<")
        if blockers:
            print("\nBlockers:")
            for b in blockers:
                print(f"  - {b}")

    # Write report file
    report_dir = _ROOT / "reports" / family / platform
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "readiness.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(f"# Readiness Scorecard: {family}/{platform}\n\n")
        f.write(f"**Verdict**: {verdict}\n\n")
        f.write("## Translation Coverage (informational — not a launch blocker)\n\n")
        f.write("| Subdomain | Locales | Coverage | Files |\n")
        f.write("|-----------|---------|----------|-------|\n")
        for site in _SUBDOMAINS:
            cov = coverage[site]
            f.write(f"| {site} | {cov['locales_present']}/{cov['total_locales']} | "
                    f"{cov['coverage']:.0%} | {cov['total_files']} |\n")
        f.write(f"\n## Grades\n\n")
        for g in ["A", "B", "C", "D", "F"]:
            f.write(f"- {g}: {grades[g]}\n")
        f.write(f"\n## Human Review Gates\n\n")
        f.write("| Gate | Name | Result |\n")
        f.write("|------|------|--------|\n")
        for gate in _HGATES:
            result = hgate_results.get(gate, "")
            f.write(f"| {gate.upper()} | {_HGATE_NAMES[gate]} | {result or 'NOT REVIEWED'} |\n")

        if blockers:
            f.write(f"\n## Blockers\n\n")
            for b in blockers:
                f.write(f"- {b}\n")

    print(f"\nReport written to: {report_path}")

    # Set checkpoint if requested and ready
    if args.set_checkpoint and ready:
        _set_checkpoint(family, platform, "readiness_done", "true")
        print(f"Checkpoint readiness_done=true set for {family}/{platform}")

    sys.exit(0 if ready else 1)


if __name__ == "__main__":
    main()
