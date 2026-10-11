"""CI gate: a changed content_eval evaluator must bump its own version.

PKGINSTALL-VERSION-BUMP-AND-LINT (2026-09-10): closes a real, repeated process gap
-- `install_recipe.py` had three real logic changes in 2026 (RC-W1-003 2026-08-14,
ST-054 TC-14 2026-09-10, ST-054 TC-16 2026-09-10) and its `EVALUATOR_VERSIONS` entry
was never bumped for any of them, silently defeating `--skip-graded`'s staleness
detection for that evaluator the whole time. This check makes that class of miss
impossible to repeat silently for any evaluator, not just `install_recipe`.

Rule: if a PR changes `scripts/pipeline/content_eval/evaluators/{name}.py`, the same
diff must also change either `EVALUATOR_VERSIONS[name]`'s value or the cross-cutting
`EVALUATOR_LOGIC_VERSION` in `scripts/pipeline/content_eval/__init__.py` -- a
cross-cutting ELV bump always satisfies every evaluator changed in the same diff.

Escape hatch, deliberately narrow and self-documenting (checked by this script
itself, not `override_manager.py` -- that governs forbidden-path writes, a
different concern): a line added in this diff to the evaluator file containing
`EVALUATOR-VERSION-BUMP-EXEMPT: <reason>` exempts that one evaluator's change from
this check, e.g. for a genuinely cosmetic/docstring-only edit.

Usage:
    python scripts/ci/checks/check_evaluator_version_bump.py
    python scripts/ci/checks/check_evaluator_version_bump.py --base main
    python scripts/ci/checks/check_evaluator_version_bump.py --files scripts/pipeline/content_eval/evaluators/install_recipe.py

Exit codes:
  0 -- no changed evaluator is missing a version bump (or none changed)
  1 -- at least one changed evaluator has no corresponding version bump and no
       exemption marker (BLOCKING, not advisory -- unlike check_script_skill_sync.py,
       this one is meant to actually enforce, not just remind)
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_INIT_REL_PATH = "scripts/pipeline/content_eval/__init__.py"
_INIT_PATH = _REPO_ROOT / _INIT_REL_PATH

_EVALUATOR_FILE_RE = re.compile(r"^scripts/pipeline/content_eval/evaluators/([a-z0-9_]+)\.py$")
_EXEMPT_RE = re.compile(r"EVALUATOR-VERSION-BUMP-EXEMPT:\s*(.+)")
_VERSIONS_ENTRY_RE = re.compile(r'"(\w+)"\s*:\s*"(\d+)"')
_LOGIC_VERSION_RE = re.compile(r'^EVALUATOR_LOGIC_VERSION\s*=\s*"(\d+)"', re.MULTILINE)


def _run_git(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, encoding="utf-8",
        errors="replace", cwd=_REPO_ROOT,
    )


def get_changed_files(base: str) -> list[str]:
    """Return list of files changed vs base branch using git diff.

    Falls back to diffing the last commit when the base ref's merge-base
    can't be resolved (mirrors check_script_skill_sync.py's own fallback).
    """
    result = _run_git(["diff", "--name-only", f"{base}...HEAD"])
    if result.returncode == 0:
        return [f.strip() for f in result.stdout.splitlines() if f.strip()]
    result = _run_git(["diff", "--name-only", "HEAD~1", "HEAD"])
    return [f.strip() for f in result.stdout.splitlines() if f.strip()]


def changed_evaluator_names(changed_files: list[str]) -> set[str]:
    """Return the set of evaluator names whose own evaluators/{name}.py changed."""
    names = set()
    for f in changed_files:
        m = _EVALUATOR_FILE_RE.match(f.replace("\\", "/"))
        if m:
            names.add(m.group(1))
    return names


def parse_versions(init_text: str) -> tuple[dict[str, str], str | None]:
    """Parse EVALUATOR_VERSIONS and EVALUATOR_LOGIC_VERSION from __init__.py source text."""
    versions: dict[str, str] = {}
    in_dict = False
    for line in init_text.splitlines():
        stripped = line.strip()
        if not in_dict:
            if stripped.startswith("EVALUATOR_VERSIONS"):
                in_dict = True
            continue
        if stripped.startswith("}"):
            break
        m = _VERSIONS_ENTRY_RE.search(line)
        if m:
            versions[m.group(1)] = m.group(2)

    m_logic = _LOGIC_VERSION_RE.search(init_text)
    logic_version = m_logic.group(1) if m_logic else None
    return versions, logic_version


def _file_at_ref(path_rel: str, ref: str) -> str | None:
    result = _run_git(["show", f"{ref}:{path_rel}"])
    return result.stdout if result.returncode == 0 else None


def _diff_added_lines(path_rel: str, base: str, *, staged: bool = False) -> list[str]:
    # TC-15-followup (independent review, 2026-09-17): `{base}...HEAD` is a real diff
    # only for an already-committed change (CI usage). For a pre-commit/staged
    # invocation, HEAD does not yet include the pending change at all, so this
    # would always return an empty diff regardless of what is staged -- silently
    # blinding the EXEMPT-marker escape hatch to any staged-but-uncommitted marker.
    # `--staged` compares the base ref directly against the INDEX instead.
    args = ["diff", "--cached", base, "--", path_rel] if staged else ["diff", f"{base}...HEAD", "--", path_rel]
    result = _run_git(args)
    if result.returncode not in (0, 1):
        return []
    return [
        line[1:] for line in result.stdout.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    ]


def _exemption_from_lines(diff_lines: list[str]) -> "str | None":
    """Pure helper: return the exemption reason if any added line carries the
    EXEMPT marker, else None. Split out from has_exemption() so tests can
    inject diff lines directly instead of needing a real git subprocess."""
    for line in diff_lines:
        m = _EXEMPT_RE.search(line)
        if m:
            return m.group(1).strip()
    return None


def has_exemption(evaluator_path: str, base: str, *, staged: bool = False) -> "str | None":
    """Return the exemption reason if the diff added an EXEMPT marker, else None."""
    return _exemption_from_lines(_diff_added_lines(evaluator_path, base, staged=staged))


def _read_init_head_text(staged: bool) -> str:
    """The real head-text read, switching between the git INDEX (staged) and
    disk (not staged). Extracted to its own named function so tests can
    inject a replacement via check()'s read_head_text_fn parameter (a plain
    keyword argument) instead of monkeypatching _file_at_ref/_INIT_PATH
    directly -- AGENTS.md 16 classifies patching either as T2 (internal
    function/constant replacement), banned; an explicit DI seam is the
    required alternative."""
    if staged:
        return _file_at_ref(_INIT_REL_PATH, "") or ""
    return _INIT_PATH.read_text(encoding="utf-8")


def check(
    base: str,
    *,
    changed_files: "list[str] | None" = None,
    init_head_text: "str | None" = None,
    init_base_text: "str | None" = None,
    exemption_diff_lines: "dict[str, list[str]] | None" = None,
    staged: bool = False,
    read_head_text_fn: "Callable[[bool], str] | None" = None,
) -> tuple[int, list[tuple[str, "str | None"]]]:
    """Run the check. Returns (exit_code, problems) where problems is a list of
    (evaluator_name, exemption_reason_or_None) for evaluators missing a bump.
    An empty problems list with exit_code 0 means either nothing changed or
    every changed evaluator was correctly bumped or exempted.

    exemption_diff_lines, when given, maps evaluator_path -> its diff's added
    lines, letting tests inject a synthetic diff instead of needing a real git
    subprocess; when None (the real/production path), has_exemption() runs a
    real `git diff` per evaluator.

    staged (TC-15-followup, independent review, 2026-09-17): a pre-commit
    invocation must judge the commit that is ABOUT TO BE MADE, i.e. the git
    INDEX, not the working tree. `_INIT_PATH.read_text()` reads disk, so a
    version bump made to __init__.py but never `git add`-ed would previously
    read as "bumped" here and pass, even though the resulting commit would not
    actually contain it (a real fail-open gap, not hypothetical). When staged
    is True and init_head_text isn't explicitly injected, head_text instead
    comes from the index via `git show :path` (empty ref = index in git's own
    pathspec syntax, reusing _file_at_ref unchanged) -- see
    _read_init_head_text().

    read_head_text_fn, when given, replaces _read_init_head_text() entirely --
    the injectable seam for tests exercising the staged-vs-disk branching
    itself (init_head_text alone can't do this, since providing it skips the
    branch being tested)."""
    changed = changed_files if changed_files is not None else get_changed_files(base)
    names = changed_evaluator_names(changed)
    if not names:
        return 0, []

    if init_head_text is not None:
        head_text = init_head_text
    else:
        reader = read_head_text_fn or _read_init_head_text
        head_text = reader(staged)
    base_text = init_base_text if init_base_text is not None else (_file_at_ref(_INIT_REL_PATH, base) or "")
    head_versions, head_logic = parse_versions(head_text)
    base_versions, base_logic = parse_versions(base_text)

    logic_bumped = head_logic is not None and head_logic != base_logic

    problems: list[tuple[str, "str | None"]] = []
    for name in sorted(names):
        if logic_bumped:
            continue  # cross-cutting ELV bump covers every evaluator changed in this diff
        if head_versions.get(name) != base_versions.get(name):
            continue  # this evaluator's own EVALUATOR_VERSIONS entry was bumped
        evaluator_path = f"scripts/pipeline/content_eval/evaluators/{name}.py"
        if exemption_diff_lines is not None:
            exemption = _exemption_from_lines(exemption_diff_lines.get(evaluator_path, []))
        else:
            exemption = has_exemption(evaluator_path, base, staged=staged)
        if exemption is not None:
            continue
        problems.append((name, None))

    return (1 if problems else 0), problems


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(
        prog="check_evaluator_version_bump",
        description="Block a PR that changes a content_eval evaluator without bumping its version.",
    )
    parser.add_argument("--base", default="main", help="Base branch/ref for git diff (default: main)")
    parser.add_argument("--files", nargs="+", help="Explicit list of changed files (overrides git diff)")
    parser.add_argument(
        "--staged", action="store_true",
        help="Judge the git INDEX (about to be committed) instead of the working-tree "
             "disk copy of __init__.py -- use this for a pre-commit invocation so an "
             "unstaged version bump on disk cannot pass a check it will not actually "
             "be part of (TC-15-followup, 2026-09-17).",
    )
    args = parser.parse_args(argv)

    exit_code, problems = check(args.base, changed_files=args.files, staged=args.staged)

    if not problems:
        print("OK: every changed content_eval evaluator has a corresponding version bump (or none changed).")
        return exit_code

    print(f"BLOCKED: {len(problems)} evaluator(s) changed without a version bump:")
    for name, _ in problems:
        print(f"  scripts/pipeline/content_eval/evaluators/{name}.py")
        print(f"    ACTION: bump EVALUATOR_VERSIONS[\"{name}\"] in {_INIT_REL_PATH}")
        print(f"            (or EVALUATOR_LOGIC_VERSION for a cross-cutting change),")
        print(f"            or add a line 'EVALUATOR-VERSION-BUMP-EXEMPT: <reason>' to this")
        print(f"            diff if the change is genuinely cosmetic (docstring/comment only).")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
