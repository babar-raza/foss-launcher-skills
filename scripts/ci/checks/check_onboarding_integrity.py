# Adapted from aspose.org scripts/ci/checks/ for standalone use
#!/usr/bin/env python3
# Adapted from aspose.org scripts/ci/checks/ for standalone use
"""
scripts/ci/checks/check_onboarding_integrity.py

Validates that the operator onboarding path is intact and undrifted.

Checks:
  1. docs/QUICKSTART.md is git-tracked
  2. AGENTS.md §2 contains a link to docs/QUICKSTART.md
  3. CLAUDE.md contains an onboarding pointer
  4. Relative links in operator docs resolve to existing files
  5. RUNBOOK.md / OPERATOR_GUIDE.md / CODEX.md Python commands use .venv prefix (not bare 'python scripts/')
  6. docs/QUICKSTART.md contains required structural substrings
  7. AGENTS.md TOC anchor hrefs match real heading slugs (added SR-01)

Exit 0: all checks pass
Exit 1: one or more checks failed (itemized output)

Safe to run at any time: read-only, no side effects.

Flags:
  --verbose / -v    Print PASS [Cx] lines for passing checks.
  --list-slugs      Print all heading slugs from AGENTS.md and exit.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_DEFAULT_REPO_ROOT = Path(os.environ.get("REPO_ROOT", Path(os.environ.get("REPO_ROOT", str(Path(__file__).resolve().parent.parent.parent.parent)))))
REPO_ROOT = _DEFAULT_REPO_ROOT

OPERATOR_DOCS = [
    REPO_ROOT / "docs" / "QUICKSTART.md",
    REPO_ROOT / "OPERATOR_GUIDE.md",
    REPO_ROOT / "RUNBOOK.md",
]


def configure(repo_root: Path | None = None) -> None:
    """Override REPO_ROOT (and recompute OPERATOR_DOCS) for testing."""
    global REPO_ROOT, OPERATOR_DOCS
    REPO_ROOT = repo_root if repo_root is not None else _DEFAULT_REPO_ROOT
    OPERATOR_DOCS = [
        REPO_ROOT / "docs" / "QUICKSTART.md",
        REPO_ROOT / "OPERATOR_GUIDE.md",
        REPO_ROOT / "RUNBOOK.md",
    ]

# Substrings that must appear in docs/QUICKSTART.md.
# Update here when a section is renamed — do NOT rename sections to avoid updating this list.
REQUIRED_QUICKSTART_SUBSTRINGS = [
    "Session Flow",
    "Safety Rules",
    "Further Reading",
    "/session-start",
]

# Pattern for relative markdown links: [text](target)
_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")

# ---------------------------------------------------------------------------
# Check runner
# ---------------------------------------------------------------------------

_failures: list[str] = []
_passed_labels: set[str] = set()  # labels already announced as PASS — dedup for --verbose
_verbose: bool = False  # set to True by --verbose in main(); not thread-safe


def _check(label: str, condition: bool, message: str) -> None:
    if condition:
        if _verbose and label not in _passed_labels:
            print(f"  PASS [{label}]")
            _passed_labels.add(label)
    else:
        _failures.append(f"  FAIL [{label}] {message}")
        if os.getenv("GITHUB_ACTIONS") or os.getenv("GITLAB_CI"):
            # Emit GitHub Actions inline annotation (visible in PR diff view)
            first_line = message.splitlines()[0]
            print(f"::error title=Onboarding Integrity [{label}]::{first_line}")


# ---------------------------------------------------------------------------
# Check 1 — docs/QUICKSTART.md is git-tracked
# ---------------------------------------------------------------------------


def check_quickstart_tracked() -> None:
    result = subprocess.run(
        ["git", "ls-files", "docs/QUICKSTART.md"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    _check(
        "C1-TRACKED",
        result.stdout.strip() == "docs/QUICKSTART.md",
        "docs/QUICKSTART.md is not git-tracked.\n"
        "    Fix: git add docs/QUICKSTART.md && /commit",
    )


# ---------------------------------------------------------------------------
# Check 2 — AGENTS.md §2 links to docs/QUICKSTART.md
# ---------------------------------------------------------------------------


def check_agents_link() -> None:
    path = REPO_ROOT / "AGENTS.md"
    if not path.exists():
        _check("C2-AGENTS-LINK", False, "AGENTS.md not found at repo root")
        return
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        _check(
            "C2-AGENTS-LINK",
            False,
            f"AGENTS.md contains non-UTF-8 bytes and cannot be read.\n"
            f"    Detail: {exc}\n    Fix: re-save as UTF-8 (no BOM).",
        )
        return
    _check(
        "C2-AGENTS-LINK",
        "docs/QUICKSTART.md" in text,
        "AGENTS.md §2 is missing a link to docs/QUICKSTART.md.\n"
        "    Fix: insert operator callout block after Read Order list (TC-04).",
    )


# ---------------------------------------------------------------------------
# Check 3 — CLAUDE.md has an onboarding pointer
# ---------------------------------------------------------------------------


def check_claude_ref() -> None:
    path = REPO_ROOT / "CLAUDE.md"
    if not path.exists():
        _check("C3-CLAUDE-REF", False, "CLAUDE.md not found at repo root")
        return
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        _check(
            "C3-CLAUDE-REF",
            False,
            f"CLAUDE.md contains non-UTF-8 bytes and cannot be read.\n"
            f"    Detail: {exc}\n    Fix: re-save as UTF-8 (no BOM).",
        )
        return
    _check(
        "C3-CLAUDE-REF",
        "docs/QUICKSTART.md" in text or "OPERATOR_GUIDE.md" in text,
        "CLAUDE.md is missing an onboarding pointer.\n"
        "    Fix: add reference to docs/QUICKSTART.md in Available Commands section (TC-05).",
    )


# ---------------------------------------------------------------------------
# Check 4 — Relative links in operator docs resolve
# ---------------------------------------------------------------------------


def check_relative_links() -> None:
    for doc in OPERATOR_DOCS:
        if not doc.exists():
            _check(
                "C4-LINKS",
                False,
                f"Operator doc not found: {doc.relative_to(REPO_ROOT)}",
            )
            continue
        try:
            text = doc.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            _check(
                "C4-LINKS",
                False,
                f"{doc.relative_to(REPO_ROOT)} contains non-UTF-8 bytes and cannot be read.\n"
                f"    Detail: {exc}\n    Fix: re-save as UTF-8 (no BOM).",
            )
            continue
        for match in _LINK_RE.finditer(text):
            target = match.group(2)
            # Skip absolute URLs, mailto, and anchor-only links
            if (
                target.startswith("http://")
                or target.startswith("https://")
                or target.startswith("mailto:")
                or target.startswith("#")
            ):
                continue
            # Strip fragment from path
            path_part = target.split("#")[0]
            if not path_part:
                continue
            resolved = (doc.parent / path_part).resolve()
            _check(
                "C4-LINKS",
                resolved.exists(),
                f"Broken link in {doc.relative_to(REPO_ROOT)}: "
                f"[{match.group(1)}]({target})\n"
                f"    Resolved to: {resolved}\n"
                f"    Fix: correct the relative path.",
            )


# ---------------------------------------------------------------------------
# Check 5 — Operator doc Python commands use .venv prefix
# Covers: RUNBOOK.md, OPERATOR_GUIDE.md, CODEX.md
# ---------------------------------------------------------------------------

# Docs whose fenced code blocks must use .venv-prefixed python invocations.
# RUNBOOK.md and OPERATOR_GUIDE.md are already in OPERATOR_DOCS (C4 catches missing files);
# CODEX.md is checked here only for venv-prefix compliance.
_VENV_CHECKED_DOCS = [
    "RUNBOOK.md",
    "OPERATOR_GUIDE.md",
    "CODEX.md",
]


def check_runbook_venv() -> None:
    for rel_path in _VENV_CHECKED_DOCS:
        path = REPO_ROOT / rel_path
        if not path.exists():
            # Missing RUNBOOK.md / OPERATOR_GUIDE.md caught by C4; CODEX.md absence skipped here.
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            _check(
                "C5-VENV-PREFIX",
                False,
                f"{rel_path} contains non-UTF-8 bytes and cannot be read.\n"
                f"    Detail: {exc}\n    Fix: re-save as UTF-8 (no BOM).",
            )
            continue

        # Only flag lines inside fenced code blocks
        in_block = False
        bad_lines: list[str] = []
        for lineno, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("```"):
                in_block = not in_block
                continue
            if in_block and re.match(r"^python\s+scripts/", line.lstrip()):
                bad_lines.append(f"    line {lineno}: {line.rstrip()}")

        _check(
            "C5-VENV-PREFIX",
            not bad_lines,
            f"{rel_path} contains bare 'python scripts/' commands (must use .venv/Scripts/python):\n"
            + "\n".join(bad_lines)
            + "\n    Fix: prefix all python commands with .venv/Scripts/python (TC-G7).",
        )


# ---------------------------------------------------------------------------
# Check 6 — Required substrings present in docs/QUICKSTART.md
# ---------------------------------------------------------------------------


def check_quickstart_structure() -> None:
    path = REPO_ROOT / "docs" / "QUICKSTART.md"
    if not path.exists():
        return  # C1 already reported this
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        _check(
            "C6-STRUCTURE",
            False,
            f"docs/QUICKSTART.md contains non-UTF-8 bytes and cannot be read.\n"
            f"    Detail: {exc}\n    Fix: re-save as UTF-8 (no BOM).",
        )
        return
    for substring in REQUIRED_QUICKSTART_SUBSTRINGS:
        _check(
            "C6-STRUCTURE",
            substring in text,
            f"docs/QUICKSTART.md is missing required content: '{substring}'.\n"
            f"    Fix: restore the section, or update REQUIRED_QUICKSTART_SUBSTRINGS "
            f"in this script if the section was intentionally renamed.",
        )


# ---------------------------------------------------------------------------
# Check 7 — TOC anchor hrefs in AGENTS.md match real heading slugs
# ---------------------------------------------------------------------------


def check_toc_anchors() -> None:
    """C7: Every (#anchor) href in AGENTS.md resolves to a real heading slug.

    Uses GitHub Markdown's anchor algorithm:
      1. Lowercase the heading text (strip leading #s and whitespace)
      2. Remove all characters that are not ASCII alphanumeric, space, or hyphen
      3. Replace whitespace runs with a single hyphen
    """
    agents = REPO_ROOT / "AGENTS.md"
    if not agents.exists():
        return  # C2 already reports missing AGENTS.md

    try:
        text = agents.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        _check(
            "C7-TOC-ANCHORS",
            False,
            f"AGENTS.md contains non-UTF-8 bytes and cannot be read.\n"
            f"    Detail: {exc}\n    Fix: re-save as UTF-8 (no BOM).",
        )
        return

    # Build set of valid slugs from real headings
    heading_slugs: set[str] = set()
    for line in text.splitlines():
        if not line.startswith("#"):
            continue
        heading = re.sub(r"^#+\s*", "", line)
        slug = heading.lower()
        slug = re.sub(r"[^a-z0-9\s-]", "", slug)
        slug = re.sub(r"\s+", "-", slug.strip())
        if slug:
            heading_slugs.add(slug)

    # Validate every (#anchor) reference in the file
    for href in re.findall(r"\(#([^)]+)\)", text):
        _check(
            "C7-TOC-ANCHORS",
            href in heading_slugs,
            f"AGENTS.md contains anchor '#{href}' with no matching heading.\n"
            f"    Fix: correct the TOC entry to use the valid slug.\n"
            f"    Run --list-slugs to see all valid slugs.",
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    global _verbose
    import argparse

    parser = argparse.ArgumentParser(
        description="Validate operator onboarding path integrity.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print PASS [Cx] lines for checks that pass (local debugging).",
    )
    parser.add_argument(
        "--list-slugs",
        action="store_true",
        help="Print all heading slugs from AGENTS.md and exit (TOC anchor debugging).",
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        metavar="DIR",
        help="Override repository root path (default: auto-detected from script location).",
    )
    args = parser.parse_args()
    _verbose = args.verbose

    if args.repo_root:
        configure(repo_root=Path(args.repo_root))

    if args.list_slugs:
        agents = REPO_ROOT / "AGENTS.md"
        if not agents.exists():
            print("AGENTS.md not found.")
            return 1
        try:
            text = agents.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            print(f"AGENTS.md contains non-UTF-8 bytes: {exc}")
            print("Fix: re-save as UTF-8 (no BOM).")
            return 1
        print("Valid heading slugs in AGENTS.md:")
        for line in text.splitlines():
            if line.startswith("#"):
                heading = re.sub(r"^#+\s*", "", line)
                slug = re.sub(r"[^a-z0-9\s-]", "", heading.lower())
                slug = re.sub(r"\s+", "-", slug.strip())
                if slug:
                    print(f"  #{slug:<60}  ←  {heading}")
        return 0

    check_quickstart_tracked()
    check_agents_link()
    check_claude_ref()
    check_relative_links()
    check_runbook_venv()
    check_quickstart_structure()
    check_toc_anchors()

    total_checks = 7
    if _failures:
        print(f"check_onboarding_integrity: FAILED ({len(_failures)} issue(s))\n")
        for msg in _failures:
            print(msg)
        print(f"\n{len(_failures)} issue(s) found across {total_checks} check groups.")
        return 1

    print(f"check_onboarding_integrity: PASSED ({total_checks} check groups, 0 issues)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
