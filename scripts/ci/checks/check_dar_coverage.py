#!/usr/bin/env python3
"""DAR coverage checker — verifies AGENTS.md §6a DAR table against skill file preconditions.

Reports:
  MISSING_DAR_ENTRY  — skill declares a precondition but no DAR entry exists
  DAR_MISMATCH       — DAR entry exists but skill file does not declare the precondition
  SKILLS_NOT_IN_S12  — skill file exists in skills/ but is not listed in §12

Exit codes:
  0 — no issues (clean)
  1 — one or more issues found (violations must be fixed before merging)
"""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
AGENTS_MD = REPO_ROOT / "AGENTS.md"
DAR_CHILD_DOC = REPO_ROOT / "docs" / "governance" / "dar-table.md"
SKILLS_CHILD_DOC = REPO_ROOT / "docs" / "registries" / "skills.md"
SKILLS_DIR = REPO_ROOT / "skills"

# ── Parse AGENTS.md ──────────────────────────────────────────────────────────

def parse_dar_table(text: str) -> list[tuple[str, str, str]]:
    """Extract (downstream, upstream, trigger) triples from the DAR table."""
    rows = []
    in_table = False
    for line in text.splitlines():
        if "| Downstream skill |" in line:
            in_table = True
            continue
        if in_table and "---" in line:
            continue
        if in_table and line.startswith("|"):
            cols = [c.strip() for c in line.split("|")[1:-1]]
            if len(cols) >= 3:
                rows.append((cols[0], cols[1], cols[2]))
        elif in_table and not line.startswith("|"):
            in_table = False
    return rows


def parse_s12_skills(text: str) -> set[str]:
    """Extract skill names from the §12 Skills reference table."""
    names = set()
    in_skills = False
    for line in text.splitlines():
        if "### Skills reference" in line or "Skills reference" in line:
            in_skills = True
            continue
        if in_skills and line.startswith("| ") and "---" not in line and "Skill" not in line:
            cols = [c.strip() for c in line.split("|")[1:-1]]
            if cols:
                names.add(cols[0].strip())
        if in_skills and line.startswith("##") and "Skills reference" not in line:
            in_skills = False
    return names


# ── Parse skill files ────────────────────────────────────────────────────────

KB_PATTERN = re.compile(r"/knowledge-bootstrap|knowledge.bootstrap", re.IGNORECASE)
PRECONDITIONS_PATTERN = re.compile(
    # Matches either a formal ## Pre-conditions / ## Knowledge Pre-conditions section header,
    # OR an inline "Bootstrap knowledge" step referencing /knowledge-bootstrap (used by scaffold
    # skills like new-docs-index, new-kb-index, new-reference-index that integrate the check
    # inline in their ## Steps section rather than in a separate preconditions block).
    r"(?:^##\s+(?:Pre-conditions|Knowledge Pre-conditions))"
    r"|(?:Bootstrap knowledge.*?/knowledge-bootstrap)",
    re.MULTILINE | re.IGNORECASE | re.DOTALL,
)
SKILL_REF = re.compile(r"(?:S-\d+|/[\w-]+)")

# Skills that declare knowledge-bootstrap but are intentionally excluded from the DAR table.
# Reasons:
#   - Orchestrators manage their own dependency chain (do not require external activation)
#   - False positives: script matches a contextual mention, not a precondition declaration
# To add a new exception: document the reason here first, then add the skill name.
# Process: confirm Category B or C per AGENTS.md §6a DAR scope rule, document reason,
# run this script and confirm only the intended warning is suppressed.
DAR_EXCEPTIONS = {
    "knowledge-update",    # Category B orchestrator: invokes bootstrap internally as part of its own chain
    "launch-product",      # Category B orchestrator: Stage 0 explicitly invokes /knowledge-bootstrap
    "project-phase-store", # Category C false positive: utility with no actual bootstrap dependency
    "update-registry",     # Category C false positive: knowledge-bootstrap mentioned in step examples as
                           # post-discovery guidance, not as a formal precondition for registry scanning
    "diagnose-skill-failure",  # Category C false positive: /knowledge-bootstrap appears only in the
                               # navigation note "Cross-skill references like /knowledge-bootstrap refer
                               # to sibling skills in this directory" — Pre-conditions section says None
    "eval-page",           # Category C false positive: same navigation note as diagnose-skill-failure;
                           # eval-page evaluates existing content; no bootstrap precondition required
    "gap-eval",            # Category B self-managing: includes its own bootstrap-state error table
                           # (shows Run /knowledge-bootstrap if not bootstrapped); manages check internally
    "triage-confirm",      # Category B self-managing: Step 1 is "Knowledge bootstrap check" — halts
                           # and redirects to /knowledge-update if stale; manages check internally
}

# Non-skill markdown files that coexist with skills in skills/ but are not skills themselves
_NON_SKILL_SLUGS: set[str] = {"readme"}


def extract_preconditions(skill_path: Path) -> dict:
    """Extract precondition info from a skill file."""
    text = skill_path.read_text(encoding="utf-8", errors="ignore")
    return {
        "has_kb_precond": bool(KB_PATTERN.search(text)),
        "mentions_preconditions": "pre-condition" in text.lower() or "prerequisite" in text.lower(),
        "referenced_skills": set(SKILL_REF.findall(text)),
        "text": text,
    }


# ── Main ─────────────────────────────────────────────────────────────────────

def _load_dar_source() -> str:
    """Dual-read: prefer child doc, fall back to AGENTS.md."""
    if DAR_CHILD_DOC.exists():
        return DAR_CHILD_DOC.read_text(encoding="utf-8")
    logging.warning("FALLBACK: reading DAR from AGENTS.md — child doc missing")
    return AGENTS_MD.read_text(encoding="utf-8")


def main() -> None:
    agents_text = AGENTS_MD.read_text(encoding="utf-8")
    dar_source = _load_dar_source()
    dar_rows = parse_dar_table(dar_source)
    # Dual-read: prefer child doc for §12 skills table
    if SKILLS_CHILD_DOC.exists():
        s12_text = SKILLS_CHILD_DOC.read_text(encoding="utf-8")
    else:
        logging.warning("FALLBACK: reading §12 Skills from AGENTS.md — child doc missing")
        s12_text = agents_text
    s12_skills = parse_s12_skills(s12_text)

    # Normalize DAR downstream skill names for matching
    # Format: `` `/page-plan` (S-18) `` → page-plan
    dar_downstreams = set()
    for downstream, _, _ in dar_rows:
        # Extract all skill-like names from the cell (handles backticks)
        for m in re.finditer(r"/([\w-]+)", downstream):
            dar_downstreams.add(m.group(1))
        # Also check for "Any content write" which is a wildcard
        if "any content" in downstream.lower():
            dar_downstreams.add("_any_content_write")

    issues: list[tuple[str, str, str]] = []
    suppressed_exceptions: list[str] = []

    # Check all skill files
    skill_files = sorted(SKILLS_DIR.glob("*.md"))
    for skill_path in skill_files:
        skill_name = skill_path.stem
        if skill_name.lower() in _NON_SKILL_SLUGS:
            continue
        info = extract_preconditions(skill_path)

        # Check: skill declares kb precondition but not in DAR
        # Exclude knowledge-bootstrap itself (self-reference) and skills that
        # are orchestrators managing their own internal chains (DAR_EXCEPTIONS)
        if info["has_kb_precond"] and skill_name not in dar_downstreams and skill_name != "knowledge-bootstrap":
            if skill_name in DAR_EXCEPTIONS:
                suppressed_exceptions.append(skill_name)
            else:
                issues.append((
                    "MISSING_DAR_ENTRY",
                    skill_name,
                    "Declares knowledge-bootstrap precondition but has no DAR entry",
                ))

        # Check: skill not in §12
        if skill_name not in s12_skills:
            issues.append((
                "SKILLS_NOT_IN_S12",
                skill_name,
                f"Exists in skills/ but not listed in AGENTS.md §12",
            ))

    # Check: DAR entries where skill file doesn't declare the precondition
    for downstream, upstream, trigger in dar_rows:
        # Skip wildcard rows
        if "any content" in downstream.lower():
            continue
        m = re.search(r"/([\w-]+)", downstream)
        if not m:
            continue
        skill_name = m.group(1)
        skill_path = SKILLS_DIR / f"{skill_name}.md"
        if not skill_path.exists():
            issues.append((
                "DAR_MISMATCH",
                skill_name,
                f"DAR entry exists but no skill file found at skills/{skill_name}.md",
            ))
            continue

        info = extract_preconditions(skill_path)
        if "knowledge-bootstrap" in upstream.lower() and not info["has_kb_precond"]:
            issues.append((
                "DAR_MISMATCH",
                skill_name,
                "DAR requires knowledge-bootstrap but skill file does not declare it",
            ))

        # Check: DAR-listed downstream skill has a Pre-conditions section
        if not PRECONDITIONS_PATTERN.search(info["text"]):
            issues.append((
                "MISSING_PRECONDITION_SECTION",
                skill_name,
                "DAR-listed downstream skill has no ## Pre-conditions section",
            ))

    # Report
    if not issues:
        print("DAR coverage: OK — no issues found")
    else:
        print(f"DAR coverage: {len(issues)} issue(s) found\n")
        for category, skill, detail in sorted(issues):
            print(f"  [{category}] {skill}: {detail}")

        # Summary by category
        cats: dict[str, int] = {}
        for cat, _, _ in issues:
            cats[cat] = cats.get(cat, 0) + 1
        print(f"\nSummary: {cats}")

    # Always print suppressed exception count so it is auditable
    if suppressed_exceptions:
        print(f"\nSuppressed {len(suppressed_exceptions)} DAR_EXCEPTIONS (justified): "
              f"{', '.join(sorted(suppressed_exceptions))}")

    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())
