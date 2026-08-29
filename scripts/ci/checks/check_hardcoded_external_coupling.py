"""check_hardcoded_external_coupling.py -- advisory structural-coupling linter.

Ported from the 2026-08-29 aspose.org -> foss-launcher-skills-gitlab sync.
New in this repo (no direct aspose.org equivalent) -- built to close a real
gap found DURING that sync: tests/fixtures/portability/banned_strings.txt
catches literal Aspose brand/domain strings in skill prose, but it does not
catch STRUCTURAL coupling. Proof: scripts/content_repo_adapter.py had a
hardcoded absolute path to the aspose.org checkout
(ASPOSE_CONTENT_ROOT = Path("D:/onedrive/Documents/GitHub/aspose.org/content"))
as its write-safety boundary since this repo's very first sync, undetected
through two "parity complete" closures, because nothing ever checked for
that CLASS of bug.

This check flags two structural-coupling patterns in Python source:

  1. A hardcoded absolute filesystem path literal (Windows drive-letter or
     POSIX /home//Users/ style) used as a default/fallback value.
  2. A list/tuple literal enumerating two or more "X.aspose.org"-shaped
     strings -- the "5 hardcoded subdomains" class of bug (the same mistake
     source's own llms-*.md skills made before this sync generalized them
     to iterate config.yaml's sites: block instead).

Deliberately coarse (same honesty check_module_consumption.py already
models for its own coarseness): a regex/text heuristic, not an AST-level
data-flow analysis. False positives (a legitimate absolute path inside a
test fixture or a comment) and false negatives (coupling expressed some
other way) are expected. It exists to catch the CLASS of bug the
ASPOSE_CONTENT_ROOT constant was, not to prove a file is fully generalized.

Scope: run against new/changed files under scripts/ or skills/, not as a
one-time retrofit against the ~500 existing scripts/pipeline/ files (that
would be noisy and is its own separately-scoped cleanup -- see
TASK_BACKLOG.md). Files under tests/ or named test_*.py are skipped: they
legitimately construct absolute paths and domain-shaped strings as fixture
data, not runtime defaults.

Usage:
    .venv/bin/python scripts/ci/checks/check_hardcoded_external_coupling.py --files a.py b.py
    git diff --cached --name-only | .venv/bin/python scripts/ci/checks/check_hardcoded_external_coupling.py

Exit codes:
  0 -- no findings (including: no .py files given)
  1 -- at least one finding (advisory -- caller decides whether this blocks
       anything; this script itself never blocks a commit)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent

_ABS_PATH_RE = re.compile(
    r'["\']((?:[A-Za-z]:[\/][^"\']{3,})|(?:/(?:home|Users)/[^"\']{3,}))["\']'
)
_SUBDOMAIN_RE = re.compile(r'[a-z0-9-]+\.aspose\.org')
_LIST_LITERAL_RE = re.compile(r'[\[(][^\[\]()]{0,400}[\])]', re.DOTALL)


def _is_test_path(path: Path) -> bool:
    if path.name.startswith("test_"):
        return True
    return any(part in ("tests", "test") for part in path.parts)


def find_hardcoded_paths(text: str) -> list[str]:
    """Return distinct hardcoded absolute-path literals found in text."""
    found = []
    for match in _ABS_PATH_RE.finditer(text):
        candidate = match.group(1)
        if candidate not in found:
            found.append(candidate)
    return found


def find_hardcoded_subdomain_lists(text: str) -> list[str]:
    """Return list-literal snippets that enumerate 2+ *.aspose.org subdomains."""
    found = []
    for list_match in _LIST_LITERAL_RE.finditer(text):
        snippet = list_match.group(0)
        subdomains = sorted(set(_SUBDOMAIN_RE.findall(snippet)))
        if len(subdomains) >= 2:
            found.append(snippet.strip().replace("\n", " ")[:120])
    return found


def check_file(path: Path) -> "dict | None":
    """Check one file. Returns a finding dict if coupling is detected, else None."""
    if _is_test_path(path):
        return None
    if path.suffix != ".py":
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None

    hardcoded_paths = find_hardcoded_paths(text)
    hardcoded_lists = find_hardcoded_subdomain_lists(text)
    if not hardcoded_paths and not hardcoded_lists:
        return None

    return {
        "file": str(path),
        "hardcoded_paths": hardcoded_paths,
        "hardcoded_subdomain_lists": hardcoded_lists,
    }


def main(argv: "list[str] | None" = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--files", nargs="*", default=None,
                        help="Files to check (default: read newline-delimited paths from stdin)")
    args = parser.parse_args(argv)

    files = args.files
    if files is None:
        if sys.stdin.isatty():
            files = []
        else:
            files = [line.strip() for line in sys.stdin if line.strip()]
    if not files:
        return 0

    findings = []
    for f in files:
        path = Path(f)
        if not path.is_absolute():
            path = _REPO_ROOT / path
        result = check_file(path)
        if result:
            findings.append(result)

    if findings:
        print("HARDCODED EXTERNAL COUPLING: %d file(s) show possible structural coupling "
              "to a specific external repo/site layout:" % len(findings))
        for f in findings:
            print("  " + f["file"])
            for p in f["hardcoded_paths"]:
                print("    hardcoded absolute path: " + p)
            for snippet in f["hardcoded_subdomain_lists"]:
                print("    hardcoded subdomain list: " + snippet)
        print("")
        print("This is advisory and coarse (text heuristic, not data-flow analysis). If this "
              "is a legitimate default with a config/env override available, no action is "
              "needed; if it is a true fallback with no override, that is the class of bug "
              "this check exists to catch -- make it config-driven instead.")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
