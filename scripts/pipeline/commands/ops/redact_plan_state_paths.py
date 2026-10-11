"""redact_plan_state_paths.py -- TC-GOV-01-02, widened by TC-GOV-01-04
(MT071-2026-09-17-GOVERNANCE-DURABILITY-HARDENING, TC-GOV-01 children 2 and 4
of 4; TC-GOV-01-04 is the REWORK follow-up spawned by TC-GOV-01-03-REVIEW).

Detects and redacts local-machine absolute home-directory paths embedded in
reports/plan_state/** (originally scoped to *.yaml/*.jsonl only; TC-GOV-01-04
widened TARGET_GLOBS -- see its own comment below -- after finding real
leaks in .md/.json/.py/.txt/.draft files the original scope silently never
scanned). Covers mission_authority.yaml's own `governing_plan_path` field,
and any other field -- `source_finding`, free-text notes, etc. -- that
happens to quote one; confirmed live in this repo's own data, both forms:
`C:\\Users\\prora\\.claude\\plans\\*.md` and `C:/Users/prora/.claude/plans/*.md`).

Why this exists (D1 decision, plans/from_backlog/2026-09-17-mission-authority-
durability-hardening.md, TC-GOV-01): reports/plan_state/** is currently
git-ignored and exists only on the operator's own machine, so mission/
taskcard state is lost if that machine is lost and invisible to any other
concurrent session (REQ-GOV-01). Before that directory can safely become
git-tracked (TC-GOV-01-03's job), every embedded reference to the operator's
own home directory must be redacted -- committing `C:\\Users\\prora\\...`
verbatim would leak the operator's local username and directory layout into
a shared, potentially-public repository.

Modeled directly on scripts/pipeline/lib/install_change_budget.py's
probe-then-check-then-execute shape (reviewed and confirmed sound for this
kind of tool this same session):
  - `scan_file()` / `scan_all()` are the pure PROBE -- read-only, no side
    effects, safe to call as often as needed.
  - `check()` wraps the probe into a pass/fail VERDICT (`CheckResult`),
    exactly mirroring `check_budget()`'s role: still entirely read-only.
  - `fix()` is the only function that ever writes to disk (the EXECUTE
    step) -- mirroring `record_run()` only ever being called after a
    change has actually been decided and applied, never speculatively.

Substitution is a **targeted regex replace**, never a parse-and-rewrite: the
matched path span is the only thing touched anywhere in the file. This is a
deliberate, explicit design constraint (not an oversight) -- a full
YAML/JSON parse+re-dump would silently reformat unrelated content (key
order, quoting style, blank lines), which would make every future `git diff`
on these files noisy and defeat the "byte-identical minus redacted fields"
goal the parent taskcard (TC-GOV-01) requires as its acceptance bar.

--check: report every embedded path found; exit 1 if any, exit 0 if clean.
--fix:   rewrite every matched path in place to a placeholder of the form
         "<local-plan-cache>/{basename}"; exit 0 (informational; a failed
         write raises rather than returning a code, since a partial/failed
         redaction pass must not be silently reported as success).

Scope (deliberately narrow, per the taskcard's own examples): only
home-directory-shaped absolute paths -- Windows `<drive>:\\Users\\<name>\\...`
/ `<drive>:/Users/<name>/...`, Git-Bash/MSYS's own rendering of the same
Windows path as `/<drive-letter>/Users/<name>/...` (added TC-GOV-01-04,
found live in a captured shell command's own output), Unix
`/home/<name>/...`, and macOS `/Users/<name>/...`. A generic repo-root path
(e.g. `D:/onedrive/Documents/GitHub/aspose.org`, which appears throughout
this repo's own governance prose as a documented convention, not a leak) is
intentionally NOT matched -- redacting it would not close any leak (it names
no username) and would make plan-state text harder to read for no
information-security benefit.
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[4]
_REPO_ROOT = _DEFAULT_REPO_ROOT

# TC-GOV-01-04 (2026-09-18, REWORK of TC-GOV-01-03-REVIEW): the original
# ("*.yaml", "*.jsonl") pair matched only the two extensions used by
# mission_authority.yaml / taskcards.jsonl themselves and silently never
# scanned any other real file living under reports/plan_state/** -- yet the
# parent taskcard's own acceptance bar ("zero C:\Users\ or /home/ literal
# matches remain under reports/plan_state/**") makes no such distinction. A
# live, from-scratch enumeration of every file actually on disk under
# reports/plan_state/** (780 files, 2026-09-18) found real embedded-path
# leaks in .md, .json, .py, .txt and .draft files too (27 files / 104
# occurrences total -- more than double the ~12 files first reported), so
# every non-binary extension actually present in the tree is now listed
# explicitly below rather than guessed:
#   yaml, jsonl  -- original scope (mission_authority.yaml, taskcards.jsonl)
#   md, txt      -- prose evidence write-ups, findings, verdicts
#   json         -- structured evidence/results (verification, manifests)
#   log, stderr  -- captured command/test output (often quotes tmp_path etc.)
#   py           -- one-off scratch/seed scripts committed as evidence
#   draft        -- e.g. MISSION_AUTHORITY.yaml.draft: a real ".yaml"-ish
#                    file whose name does NOT end in ".yaml" (two dots), so
#                    "*.yaml" alone silently missed it even before this fix
#   orig, diff   -- patch/snapshot evidence (a unified diff can quote a path
#                    in its header)
#   html         -- rendered evidence reports
#   java, cs, csproj -- example/reference source snippets captured as evidence
#   sha256, run_id_self -- small metadata/checksum sidecar files
# Deliberately EXCLUDED: "*.zip", "*.whl" -- genuine binary archive formats
# (confirmed live: MT040's evidence zip, a 3d/python wheel) where a text
# regex substitution would corrupt the binary container rather than redact
# prose; a decode attempt against either fails immediately in
# _read_text_or_none() below, so even a stray zip/whl entry added here would
# only ever be silently skipped, never mis-fixed.
# Also out of scope: the single known extensionless file under this tree
# (reports/plan_state/MT040-.../evidence/baseline/BASE_SHA, a bare 41-char
# git SHA) -- it cannot syntactically contain a path, and glob-matching
# "no extension" would need bespoke logic (rglob has no such pattern) for
# zero realistic benefit.
TARGET_GLOBS = (
    "*.yaml", "*.jsonl",
    "*.md", "*.txt", "*.json", "*.log", "*.py", "*.draft",
    "*.orig", "*.diff", "*.html", "*.stderr",
    "*.java", "*.cs", "*.csproj", "*.sha256", "*.run_id_self",
)
PLACEHOLDER_PREFIX = "<local-plan-cache>"


def configure(*, repo_root: "Path | str | None" = None) -> None:
    """Override the repo root used to resolve the default plan_state
    directory -- test-only DI seam, mirrors install_change_budget.py's own
    `configure()` (repo_root there overrides HISTORY_PATH; here it overrides
    plan_state_root()). Omitting repo_root resets to the real repo."""
    global _REPO_ROOT
    _REPO_ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT


def plan_state_root() -> Path:
    return _REPO_ROOT / "reports" / "plan_state"


# ---------------------------------------------------------------------------
# Path-matching regex
#
# A path "segment" is any run of characters that cannot themselves be a
# path separator, quote, or a character that commonly terminates a path when
# it is embedded inline in prose (closing bracket/paren, comma, semicolon,
# angle bracket). Excluding `<`/`>` is what correctly keeps a documentation
# placeholder like "C:\Users\<user>\..." (confirmed live in this repo's own
# MT071 mission_authority.yaml) from ever being treated as a real path: the
# character immediately after the required "Users\" separator is `<`, which
# cannot start a segment, so the whole path-regex fails to match there.
#
# Separators are matched as `[\\/]{1,2}` (one or two of backslash/forward
# slash) rather than a single fixed character, because the exact same
# logical path appears in two different literal forms across this repo's
# real files depending on which tool wrote it:
#   - raw YAML text uses a single backslash per separator:
#       C:\Users\prora\.claude\plans\foo.md
#   - a JSON string (as embedded in a .jsonl line) escapes each backslash,
#     so the RAW FILE BYTES contain two backslash characters per separator:
#       C:\\Users\\prora\\.claude\\plans\\foo.md
# and some tools write Windows paths with forward slashes throughout:
#       C:/Users/prora/.claude/plans/foo.md
# `[\\/]{1,2}` matches all three forms uniformly without needing to know
# which file format is being scanned.
# A segment additionally requires at least one non-dot character, which
# matters live: this repo's own plan-state data quotes the parent plan's D1
# decision prose verbatim in places ("...embedded in reports/plan_state/**
# (52 files, e.g. C:\Users\prora\...)"), where a bare "..." follows the real
# path as an illustrative ellipsis, not a further path segment. Without this
# requirement, "..." greedily matches as one more _SEGMENT and gets swept
# into the redacted span; requiring a non-dot character makes an all-dot
# token fail to match, so the repetition below simply stops one segment
# earlier (found live against reports/plan_state/MT066-.../taskcards.jsonl).
# ---------------------------------------------------------------------------
_SEGMENT_CHAR = r'[^\s"\'\\/()\[\]{}<>,;]'
_SEGMENT = _SEGMENT_CHAR + r'*[^\s"\'\\/()\[\]{}<>,;.]' + _SEGMENT_CHAR + r'*'

# Negative lookbehinds anchor each pattern so it only fires at the genuine
# start of an absolute-path token -- never mid-token inside an unrelated
# "/"-joined or word-joined sequence. Found live: reports/plan_state/
# seo-keyword-production-integration/taskcards.jsonl contains the prose
# "...(barcode/cad/cells/home/html/imaging/ocr/page/pdf/psd/tasks/tex/words/
# zip)..." -- an alphabetized list of product families that happens to
# include one literally named "home", immediately followed by "html". With
# no lookbehind, "/home/html/.../zip" matched as if it were a real Unix home
# path, which it categorically is not (the "/" before "home" is preceded by
# "s" from "cells", not a token boundary). `(?<!\w)` / `(?<![\\/\w.])` reject
# a match whose start is preceded by a word/path character.
# TC-GOV-01-04 (2026-09-18): real bug found live during this taskcard's own
# --fix run against the widened real corpus (reports/plan_state/
# readme-refresh-pdf-typescript-scale-hardening-2026-09-03/evidence/
# verify-examples.final.result.json, a captured Node.js stack trace inside a
# JSON string): the *un-anchored* `[\\/]{1,2}` separator let a single stray
# backslash -- the start of an UNRELATED JSON escape sequence like `\n`
# (newline) immediately following the path's own JSON-double-backslash
# separators, e.g. `...\\project\\verify_block_6.mts:4\nconst bytes = ...`
# -- be consumed as "one more path separator", so the match ran on past the
# real path's end and swallowed the following prose word ("nconst") into
# the placeholder's basename. A named-group backreference now pins every
# separator within a single match to the SAME width as the very first one
# encountered (1 backslash for raw YAML, 2 for JSON-escaped, 1 or 2 for
# forward-slash forms) -- consistent with the docstring's own claim that
# only 3 uniform forms are supported; a match can no longer silently switch
# separator width mid-path to absorb an unrelated escape sequence.
_WINDOWS_HOME_PATTERN = (
    r'(?<!\w)[A-Za-z]:(?P<_gov01_wsep>[\\/]{1,2})Users(?P=_gov01_wsep)'
    + _SEGMENT + r'(?:(?P=_gov01_wsep)' + _SEGMENT + r')*'
)
_UNIX_HOME_PATTERN = r'(?<![\\/\w.])/(?:home|Users)/' + _SEGMENT + r'(?:/' + _SEGMENT + r')*'
# TC-GOV-01-04 (2026-09-18): a 5th real shape found live during this
# taskcard's own from-scratch full-tree recon (reports/plan_state/
# MT014-2026-07-29-PDF-GO-REDO/independent-verification-20260731.md:32,
# a captured shell command's own literal output, not something anyone
# authored by hand) -- Git-Bash/MSYS's own path convention renders a
# Windows drive letter as a single-letter leading path segment instead of
# "<letter>:": `/c/Users/prora/AppData/...` is the exact same leak as
# `C:\Users\prora\...`, just spelled the way `bash`/`git` on this operator's
# own machine renders it. `[A-Za-z]` (not `_SEGMENT`) between the two
# slashes deliberately requires EXACTLY one letter -- this is what keeps it
# from ever matching the already-handled "cells/home/html" false-positive
# family-list case (no single-letter segment precedes "home" there).
_MSYS_DRIVE_HOME_PATTERN = (
    r'(?<![\\/\w.])/[A-Za-z]/(?:home|Users)/' + _SEGMENT + r'(?:/' + _SEGMENT + r')*'
)
_PATH_RE = re.compile(_WINDOWS_HOME_PATTERN + "|" + _MSYS_DRIVE_HOME_PATTERN + "|" + _UNIX_HOME_PATTERN)

_SEPARATOR_RUN_RE = re.compile(r'[\\/]+')


def _basename(matched_path: str) -> str:
    """Last path segment of a matched span, robust to any mix of single-
    backslash, doubled-backslash (JSON-escaped), and forward-slash
    separators within the same matched string."""
    normalized = _SEPARATOR_RUN_RE.sub("/", matched_path)
    return normalized.rstrip("/").rsplit("/", 1)[-1]


def _placeholder_for(matched_path: str) -> str:
    return f"{PLACEHOLDER_PREFIX}/{_basename(matched_path)}"


# ---------------------------------------------------------------------------
# I/O helpers -- newline="" on both read and write disables Python's
# universal-newline translation, so CRLF/LF line endings round-trip exactly
# as they appear on disk (required for the "byte-for-byte" preservation
# guarantee on every part of the file this tool does not touch).
# ---------------------------------------------------------------------------

def _read_text(path: Path) -> str:
    with open(path, "r", encoding="utf-8", newline="") as f:
        return f.read()


def _read_text_or_none(path: Path) -> "str | None":
    """Like `_read_text`, but returns None instead of raising when `path`'s
    bytes are not valid UTF-8, rather than crashing --check/--fix.

    Confirmed live (2026-09-18): several real evidence files newly in scope
    after widening TARGET_GLOBS (e.g. reports/plan_state/MT067-.../
    promote_*.log, an MT022 pilot log) are otherwise-ordinary text that
    happens to contain a single legacy-codepage byte (e.g. 0x97, a cp1252
    em-dash) that is not valid UTF-8 -- not a genuine binary file. Every
    such file found in the real corpus was independently confirmed (raw
    byte-level search for "Users"/"/home/") to contain zero path leaks, so
    treating an undecodable file as "cannot scan, skip" here is a deliberate
    defensive fallback for this known, benign case -- not a silently-accepted
    gap. `undecodable_files()` below exposes the skipped set so --check/--fix
    can still surface it to a human rather than going fully silent."""
    try:
        return _read_text(path)
    except UnicodeDecodeError:
        return None


def _write_text(path: Path, text: str) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


@dataclass
class Finding:
    file: Path
    line_no: int
    matched_text: str
    placeholder: str


def find_matches_in_text(text: str) -> "list[tuple[int, str, str]]":
    """Pure text-level probe: every (1-based line number, matched path,
    placeholder-it-would-become) tuple in `text`, in order of appearance.
    No I/O; safe to call on arbitrary strings (used directly by tests that
    don't need a file on disk)."""
    results = []
    for m in _PATH_RE.finditer(text):
        matched = m.group(0)
        line_no = text.count("\n", 0, m.start()) + 1
        results.append((line_no, matched, _placeholder_for(matched)))
    return results


def iter_target_files(plan_state_dir: "Path | None" = None) -> "list[Path]":
    """Every file under `plan_state_dir` (default: the real
    reports/plan_state/ under the configured repo root) matching one of
    TARGET_GLOBS, recursively. TARGET_GLOBS (see its own comment above) now
    covers every non-binary extension confirmed present on disk as of
    2026-09-18 -- this is deliberately NOT "every file": the two genuine
    binary archive extensions found in the tree (*.zip, *.whl) are excluded
    by construction (not listed in TARGET_GLOBS), since a regex text
    substitution against a binary container would corrupt it rather than
    redact prose."""
    base = plan_state_dir if plan_state_dir is not None else plan_state_root()
    if not base.is_dir():
        return []
    found: "set[Path]" = set()
    for pattern in TARGET_GLOBS:
        found.update(base.rglob(pattern))
    return sorted(found)


def scan_file(path: Path) -> "list[Finding]":
    """PROBE (read-only): every embedded local-path Finding in one file.
    Returns [] (rather than raising) for a file that is not valid UTF-8 --
    see `_read_text_or_none`'s docstring; such a file is tracked separately
    by `undecodable_files()`, not silently conflated with "genuinely clean"."""
    text = _read_text_or_none(path)
    if text is None:
        return []
    return [
        Finding(file=path, line_no=line_no, matched_text=matched, placeholder=placeholder)
        for line_no, matched, placeholder in find_matches_in_text(text)
    ]


def undecodable_files(plan_state_dir: "Path | None" = None) -> "list[Path]":
    """Every target file `scan_file`/`fix` had to skip because its bytes
    are not valid UTF-8 -- informational only (never affects --check's exit
    code), surfaced so a human can audit the skip list rather than it being
    fully invisible. See `_read_text_or_none`'s docstring for why this is a
    deliberate fallback."""
    return [p for p in iter_target_files(plan_state_dir) if _read_text_or_none(p) is None]


def scan_all(plan_state_dir: "Path | None" = None) -> "list[Finding]":
    """PROBE (read-only): every embedded local-path Finding across every
    target file under `plan_state_dir`."""
    findings: "list[Finding]" = []
    for path in iter_target_files(plan_state_dir):
        findings.extend(scan_file(path))
    return findings


@dataclass
class CheckResult:
    findings: "list[Finding]" = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not self.findings


def check(plan_state_dir: "Path | None" = None) -> CheckResult:
    """CHECK (read-only verdict): mirrors check_budget()'s role -- combines
    the probe into a single allowed/not-allowed-shaped result without ever
    writing anything."""
    return CheckResult(findings=scan_all(plan_state_dir))


@dataclass
class FixResult:
    files_fixed: "list[Path]" = field(default_factory=list)
    total_redactions: int = 0


def fix(plan_state_dir: "Path | None" = None) -> FixResult:
    """EXECUTE (the only function in this module that writes to disk):
    rewrite every matched path span to its placeholder, in place, one file
    at a time. Files with zero matches are never opened for writing --
    running `fix()` a second time in a row is a true no-op (idempotent),
    which is also what makes `--check` exit 0 immediately after `--fix`."""
    result = FixResult()
    for path in iter_target_files(plan_state_dir):
        text = _read_text_or_none(path)
        if text is None:
            continue
        count = 0

        def _substitute(m: "re.Match[str]") -> str:
            nonlocal count
            count += 1
            return _placeholder_for(m.group(0))

        new_text = _PATH_RE.sub(_substitute, text)
        if count:
            _write_text(path, new_text)
            result.files_fixed.append(path)
            result.total_redactions += count
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _print_undecodable_note(root: Path) -> None:
    skipped = undecodable_files()
    if skipped:
        print(
            f"NOTE -- {len(skipped)} target file(s) under {root} are not valid UTF-8 and were "
            "skipped (not scanned/fixed); see _read_text_or_none()'s docstring:"
        )
        for path in skipped:
            print(f"  {path}")


def _print_check_report(result: CheckResult, root: Path) -> None:
    if result.clean:
        print(f"OK -- 0 embedded local-machine paths found under {root}")
    else:
        print(f"FOUND {len(result.findings)} embedded local-machine path occurrence(s) under {root}:")
        for finding in result.findings:
            print(f"  {finding.file}:{finding.line_no}: {finding.matched_text!r} -> {finding.placeholder!r}")
    _print_undecodable_note(root)


def cmd_check(_args: argparse.Namespace) -> int:
    root = plan_state_root()
    result = check()
    _print_check_report(result, root)
    return 1 if not result.clean else 0


def cmd_fix(_args: argparse.Namespace) -> int:
    root = plan_state_root()
    result = fix()
    if not result.files_fixed:
        print(f"OK -- nothing to fix under {root}")
        _print_undecodable_note(root)
        return 0
    print(f"Fixed {len(result.files_fixed)} file(s), {result.total_redactions} path occurrence(s) redacted:")
    for path in result.files_fixed:
        print(f"  {path}")
    _print_undecodable_note(root)
    return 0


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(
        prog="redact_plan_state_paths",
        description=(
            "Detect/redact local-machine absolute home-directory paths embedded in "
            "reports/plan_state/** (TC-GOV-01-02/-04; see TARGET_GLOBS for exact file-type scope)."
        ),
    )
    parser.add_argument("--repo-root", help="Override repo root (default: auto-detected)")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="Report findings; exit 1 if any found")
    mode.add_argument("--fix", action="store_true", help="Rewrite matched paths to placeholders in place")
    args = parser.parse_args(argv)

    configure(repo_root=args.repo_root)

    if args.check:
        return cmd_check(args)
    return cmd_fix(args)


if __name__ == "__main__":
    sys.exit(main())
