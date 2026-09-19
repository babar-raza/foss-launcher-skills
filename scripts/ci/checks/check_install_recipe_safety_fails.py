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

Reporting contract (PKGINSTALL-GRADE-SAFETY-OVERRIDE-FIX D1a). The first version
of this script failed open in what it REPORTED: a nonexistent path, a non-.md
file and every flat locale-suffix file (index.de.md) were silently skipped by
content_eval.loader.load_files(), and the OK line counted the paths it was
GIVEN, not the pages it evaluated. Now:
  * every input path lands in exactly one bucket -- evaluated, skipped (with a
    reason, each one printed) or error -- and the summary says "evaluated N of M";
  * a nonexistent path, an unreadable file, an unreadable --files-from list and a
    crash while evaluating a page are ERRORS (exit 2), never "OK";
  * flat locale-suffix files (LOCALE_RE, e.g. blog index.de.md) ARE evaluated (the
    loader's English-only skip is deliberately not inherited) and are counted
    separately in the summary;
  * a page with no inferable family/platform (nothing in the registry to check it
    against) is reported as skipped, not as clean.

Exit codes: 0 no findings and no errors; 1 findings only (these are what a
governed override token may cover); 2 at least one error (never overridable).
--blocked-files-out writes the paths that carry findings, only when the exit code
is 1, so a caller can apply a per-file override-token check and treat "non-zero
exit + empty list" as unverifiable = blocked.

Known coverage limits (unchanged by this script, owned by other cards): the
checks read body prose and links only (not headings, frontmatter or code fences),
the disclosure regex and the negation guard are English-only, and the registry is
trusted as ground truth.

CLI:
    PYTHONPATH=scripts/pipeline python scripts/ci/checks/check_install_recipe_safety_fails.py \\
        content/docs.aspose.org/en/barcode/python/getting-started/installation.md
    PYTHONPATH=scripts/pipeline python scripts/ci/checks/check_install_recipe_safety_fails.py \\
        --files-from staged.txt --blocked-files-out blocked.txt
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_PIPELINE_ROOT = Path(__file__).resolve().parents[2] / "pipeline"
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

from content_eval.loader import LOCALE_RE  # noqa: E402
from content_eval.models import Page  # noqa: E402
from content_eval.evaluators.install_recipe import InstallRecipeEvaluator  # noqa: E402

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_ERROR = 2


@dataclass
class CheckReport:
    """Outcome of one run. Every input path is in exactly one of `evaluated`,
    `skipped` or `errors`, so len(evaluated) + len(skipped) + len(errors) == total."""

    total: int = 0
    evaluated: "list[str]" = field(default_factory=list)
    locale_suffix_evaluated: "list[str]" = field(default_factory=list)
    skipped: "list[tuple[str, str]]" = field(default_factory=list)
    errors: "list[tuple[str, str]]" = field(default_factory=list)
    findings: "list[dict[str, Any]]" = field(default_factory=list)

    @property
    def blocked_paths(self) -> "list[str]":
        seen: "dict[str, None]" = {}
        for f in self.findings:
            seen.setdefault(f["path"], None)
        return list(seen)


def _dedupe(paths: "list[str]") -> "list[str]":
    return list(dict.fromkeys(paths))


def run_check(file_paths: "list[str]") -> CheckReport:
    """Run only the 2 safety checks (never _verify_install_accuracy) against every
    given path and account for every one of them in the returned report."""
    paths = _dedupe([str(p) for p in file_paths])
    report = CheckReport(total=len(paths))
    evaluator = InstallRecipeEvaluator()

    for raw in paths:
        p = Path(raw)
        if not p.exists():
            report.errors.append((raw, "path does not exist"))
            continue
        if not p.is_file():
            report.errors.append((raw, "not a regular file"))
            continue
        if p.suffix.lower() != ".md":
            report.skipped.append((raw, "not a markdown file"))
            continue
        try:
            page = Page.load(p)
        except Exception as exc:  # unreadable / not UTF-8 / unparsable
            report.errors.append((raw, f"cannot load page: {type(exc).__name__}: {exc}"))
            continue
        if not (page.family and page.platform):
            report.skipped.append((
                raw,
                "no family/platform inferable from the path (not under a content site's "
                "{family}/{platform}/ tree); the registry check does not apply",
            ))
            continue
        try:
            page_findings = list(evaluator._verify_publish_channel_claims(page))
            page_findings += list(evaluator._verify_no_unpublished_disclosure(page))
        except Exception as exc:
            report.errors.append((raw, f"evaluation crashed: {type(exc).__name__}: {exc}"))
            continue
        report.evaluated.append(raw)
        if LOCALE_RE.search(p.name):
            report.locale_suffix_evaluated.append(raw)
        for f in page_findings:
            # The path exactly as the caller gave it (git's forward-slash form in a
            # hook), NOT Path()'s normalised form: the blocked-files list is fed back
            # to per-file override-token validation, which matches on that string.
            report.findings.append({"path": raw, "category": f.category, "message": f.message})
    return report


def check_files(file_paths: "list[str]") -> "list[dict[str, Any]]":
    """Compatibility wrapper: the findings only. It does NOT surface skipped or
    errored paths -- callers that gate on the result must use run_check() (or the
    CLI) so an unevaluated path can never read as clean."""
    return run_check(file_paths).findings


def _read_files_from(list_path: str) -> "list[str]":
    text = Path(list_path).read_text(encoding="utf-8")
    return [line.strip() for line in text.splitlines() if line.strip()]


def _summary(report: CheckReport) -> str:
    n = len(report.evaluated)
    text = f"evaluated {n} of {report.total} path(s)"
    if report.locale_suffix_evaluated:
        text += f" ({len(report.locale_suffix_evaluated)} flat locale-suffix file(s) included)"
    if report.skipped:
        text += f", skipped {len(report.skipped)}"
    return text


def _write_blocked(path: "str | None", paths: "list[str]") -> None:
    if path:
        Path(path).write_text("".join(f"{p}\n" for p in paths), encoding="utf-8")


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("files", nargs="*", help="Content files to check (PR-touched .md files)")
    parser.add_argument("--files-from", metavar="LIST",
                        help="Read paths from LIST, one per line (avoids argument-length limits); "
                             "combined with any positional paths")
    parser.add_argument("--blocked-files-out", metavar="PATH",
                        help="Write the paths that carry findings to PATH (one per line), and only "
                             "when the exit code is 1; empty for exit 0 and 2")
    args = parser.parse_args(argv)

    try:
        paths = list(args.files)
        if args.files_from:
            try:
                paths += _read_files_from(args.files_from)
            except (OSError, UnicodeDecodeError) as exc:
                print(f"ERROR: cannot read --files-from list {args.files_from!r}: "
                      f"{type(exc).__name__}: {exc}", file=sys.stderr)
                _write_blocked(args.blocked_files_out, [])
                return EXIT_ERROR

        report = run_check(paths)
    except Exception as exc:  # a crash must never read as "no findings"
        print(f"ERROR: install_recipe safety check crashed: {type(exc).__name__}: {exc}", file=sys.stderr)
        _write_blocked(args.blocked_files_out, [])
        return EXIT_ERROR

    if report.errors:
        print(f"ERROR: {len(report.errors)} path(s) could NOT be checked; {_summary(report)}:",
              file=sys.stderr)
        for path, reason in report.errors:
            print(f"  ERROR   {path}: {reason}", file=sys.stderr)
        for path, reason in report.skipped:
            print(f"  SKIPPED {path}: {reason}", file=sys.stderr)
        for f in report.findings:
            print(f"  {f['path']} [{f['category']}]: {f['message']}", file=sys.stderr)
        _write_blocked(args.blocked_files_out, [])
        return EXIT_ERROR

    if report.findings:
        print(
            f"BLOCKED: {len(report.findings)} install_recipe safety FAIL(s), independent of stored grade; "
            f"{_summary(report)}:",
            file=sys.stderr,
        )
        for f in report.findings:
            print(f"  {f['path']} [{f['category']}]: {f['message']}", file=sys.stderr)
        for path, reason in report.skipped:
            print(f"  SKIPPED {path}: {reason}", file=sys.stderr)
        _write_blocked(args.blocked_files_out, report.blocked_paths)
        return EXIT_FINDINGS

    if report.total == 0:
        print("No files given -- evaluated 0 of 0 path(s); nothing to check.")
    else:
        print(f"OK: 0 install_recipe safety FAIL(s); {_summary(report)}.")
    for path, reason in report.skipped:
        print(f"  SKIPPED {path}: {reason}")
    _write_blocked(args.blocked_files_out, [])
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
