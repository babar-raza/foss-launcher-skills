# Adapted from aspose.org scripts/ci/checks/ for standalone use
#!/usr/bin/env python3
"""check_pipeline_path_integrity.py — Verify all scripts/pipeline/ path references exist.

Five check categories (each reports file:line on failure):

  CHECK 1 — Skill CONTRACT tags in skills/*.md
  CHECK 2 — CI workflow (.github/workflows/content-audit.yml)
  CHECK 3 — AGENTS.md
  CHECK 4 — Pipeline docs (README.md, PIPELINE.md)
  CHECK 5 — Skill docs that hardcode paths (skills/commit.md)

Usage:
    python scripts/ci/checks/check_pipeline_path_integrity.py
    python scripts/ci/checks/check_pipeline_path_integrity.py --dry-run   # report only, exit 0

Exit codes:
    0 — all referenced paths exist
    1 — one or more referenced paths are missing
"""
from __future__ import annotations

import argparse
import re
import os
import sys
from pathlib import Path

REPO_ROOT = Path(os.environ.get("REPO_ROOT", str(Path(__file__).resolve().parents[3])))

# Pattern to extract scripts/pipeline/X.py (or scripts/tests/pipeline/X.py) references
_PATH_RE = re.compile(r"scripts/(?:pipeline|tests/pipeline)/[\w./]+\.py")


def scan_file(filepath: Path) -> list[tuple[int, str]]:
    """Return list of (line_number, matched_path) from file."""
    hits: list[tuple[int, str]] = []
    try:
        text = filepath.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return hits
    for lineno, line in enumerate(text.splitlines(), 1):
        for m in _PATH_RE.finditer(line):
            hits.append((lineno, m.group()))
    return hits


def check_paths(label: str, source_file: Path, findings: list[tuple[int, str]]) -> list[str]:
    """Return error lines for missing paths."""
    errors: list[str] = []
    for lineno, ref_path in findings:
        full = REPO_ROOT / ref_path
        if not full.exists():
            errors.append(f"  MISSING  {source_file.relative_to(REPO_ROOT)}:{lineno}  →  {ref_path}")
    return errors


def run_checks(dry_run: bool) -> int:
    all_errors: list[str] = []

    # CHECK 1 — Skill CONTRACT tags
    skills_dir = REPO_ROOT / "skills"
    for skill_file in sorted(skills_dir.glob("*.md")):
        hits = scan_file(skill_file)
        # Only report CONTRACT-tagged paths for stricter signal
        contract_hits = []
        try:
            text = skill_file.read_text(encoding="utf-8", errors="replace")
            for lineno, line in enumerate(text.splitlines(), 1):
                if "CONTRACT:" in line:
                    for m in _PATH_RE.finditer(line):
                        contract_hits.append((lineno, m.group()))
        except OSError:
            pass
        errs = check_paths("CHECK 1 (CONTRACT)", skill_file, contract_hits)
        all_errors.extend(errs)

    # CHECK 2 — CI workflow
    ci_yml = REPO_ROOT / ".github" / "workflows" / "content-audit.yml"
    if ci_yml.exists():
        errs = check_paths("CHECK 2 (CI workflow)", ci_yml, scan_file(ci_yml))
        all_errors.extend(errs)

    # CHECK 3 — AGENTS.md
    agents_md = REPO_ROOT / "AGENTS.md"
    if agents_md.exists():
        errs = check_paths("CHECK 3 (AGENTS.md)", agents_md, scan_file(agents_md))
        all_errors.extend(errs)

    # CHECK 4 — Pipeline docs
    for doc in [
        REPO_ROOT / "scripts" / "pipeline" / "README.md",
        REPO_ROOT / "scripts" / "pipeline" / "PIPELINE.md",
    ]:
        if doc.exists():
            errs = check_paths("CHECK 4 (pipeline docs)", doc, scan_file(doc))
            all_errors.extend(errs)

    # CHECK 5 — Skill docs that hardcode paths
    for skill_doc in [
        REPO_ROOT / "skills" / "commit.md",
    ]:
        if skill_doc.exists():
            errs = check_paths("CHECK 5 (skill path refs)", skill_doc, scan_file(skill_doc))
            all_errors.extend(errs)

    if all_errors:
        print(f"FAIL: {len(all_errors)} broken path reference(s):", file=sys.stderr)
        for e in all_errors:
            print(e, file=sys.stderr)
        if dry_run:
            print("\n(dry-run: exiting 0 despite failures)")
            return 0
        return 1

    checks = ["CONTRACT tags", "CI workflow", "AGENTS.md", "pipeline docs", "skill path refs"]
    print(f"OK: path integrity verified ({len(checks)} check categories, 0 broken references)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="Report issues but always exit 0")
    args = parser.parse_args()
    return run_checks(dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
