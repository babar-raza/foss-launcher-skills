#!/usr/bin/env python3
"""Backlink compliance gate (TC14, backlink-governance-redesign).

Blocks a commit that introduces (or edits into a worse state) a
non-compliant aspose.com backlink -- wrong anchor wording, a duplicate
link, or a duplicate-subdomain pairing -- on any staged content file.

Deliberately scoped to files whose STAGED DIFF actually touches an
aspose.com link (a changed line containing "aspose.com"), not merely any
compliance-relevant file: the repo currently carries a known, uncorrected
backlog of ~125+ non-compliant pages (see mission backlink-governance-redesign,
pending TC15's staged backfill). A blanket "block if non-compliant" gate
would immediately block any unrelated edit to any of those pages before
that backlog is fixed. Scoping to "did this diff touch a backlink" means
this gate only ever fires on a genuinely new or newly-worsened defect, not
on pre-existing debt the commit didn't create or touch.

Usage — staged-file mode (pre-commit):
    check_backlink_compliance.py FILE [FILE ...]
    Exit 1 if any FAIL; exit 0 otherwise.

Usage — scan mode (unscoped, e.g. CI reporting -- ignores the diff-touch
scoping above and checks every given file's current compliance state
regardless of what changed):
    check_backlink_compliance.py --scan FILE [FILE ...]

Exit codes:
    0 — all pass (or nothing to check)
    1 — at least one FAIL
    2 — configuration error (target map missing, etc.)
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parents[2]  # scripts/ci/checks -> repo root

sys.path.insert(0, str(_REPO_ROOT / "scripts" / "pipeline"))

import json

from lib.backlink_targets import load_target_map, load_canonical_overrides  # noqa: E402
from commands.ops.backlink_audit import (  # noqa: E402
    audit_file,
    STATUS_WRONG_TARGET, STATUS_OVER_LIMIT, STATUS_BLOCKED_TARGET,
    STATUS_WRONG_ANCHOR_TEXT, STATUS_DUPLICATE_LINK, STATUS_DUPLICATE_SUBDOMAIN,
)
from commands.ops.backlink_backfill import _load_display_maps  # noqa: E402

# MISSING/SKIPPED/FAMILY_FALLBACK/COMPLIANT are deliberately NOT here --
# see module docstring. This gate is for confidently-wrong states only.
BLOCKING_STATUSES = frozenset({
    STATUS_WRONG_TARGET, STATUS_OVER_LIMIT, STATUS_BLOCKED_TARGET,
    STATUS_WRONG_ANCHOR_TEXT, STATUS_DUPLICATE_LINK, STATUS_DUPLICATE_SUBDOMAIN,
})


class Finding(NamedTuple):
    file: str
    rule: str
    message: str
    level: str  # "FAIL" or "WARN"

    def __str__(self) -> str:
        return f"{self.level} [{self.rule}] {self.file} — {self.message}"


def diff_touches_aspose_com_link(path: Path, repo_root: Path) -> bool:
    """True if this file's staged diff has a changed line mentioning
    aspose.com -- the scoping heuristic that keeps this gate from firing on
    pre-existing, unrelated debt (see module docstring)."""
    try:
        rel = path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        rel = str(path)
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "-U0", "--", rel],
            cwd=str(repo_root), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        # Can't determine the diff -- fail safe by treating it as touched,
        # so a real defect is never silently skipped due to a tooling failure.
        return True
    for line in result.stdout.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+") and "aspose.com" in line:
            return True
    return False


def check_file(
    path: Path,
    repo_root: Path,
    target_map: dict,
    canonical_overrides: dict | None,
    families_map: dict,
    platforms_map: dict,
    *,
    scan_mode: bool = False,
    authority: dict | None = None,
) -> list[Finding]:
    rel = path.resolve().relative_to(repo_root.resolve()).as_posix() if path.is_relative_to(repo_root) else str(path)

    if not scan_mode and not diff_touches_aspose_com_link(path, repo_root):
        return []

    try:
        rec = audit_file(
            path, repo_root, target_map,
            canonical_overrides=canonical_overrides,
            families_map=families_map, platforms_map=platforms_map,
            exact_deep_match_enabled=bool(authority), authority=authority,
        )
    except Exception as exc:
        return [Finding(rel, "AUDIT_ERROR", f"Could not audit file: {exc}", "FAIL")]

    if rec.status not in BLOCKING_STATUSES:
        return []

    return [Finding(
        rel, rec.status,
        f"{rec.resolution_evidence} (existing: {', '.join(rec.existing_com_links) or '(none)'})",
        "FAIL",
    )]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check staged content files for newly-introduced backlink compliance violations."
    )
    parser.add_argument("files", nargs="*", help="Specific files to check")
    parser.add_argument(
        "--files-from",
        help="Path to a text file listing repo-relative content paths (one per "
             "line) -- avoids OS argument-list-too-long errors on large commits, "
             "matching audit.py's own --files-from convention.",
    )
    parser.add_argument(
        "--scan", action="store_true",
        help="Check every given file's current status regardless of diff content "
             "(no diff-touch scoping) -- for full-repo CI reporting, not pre-commit.",
    )
    parser.add_argument("--repo-root", default=str(_REPO_ROOT))
    args = parser.parse_args(argv)

    file_args = list(args.files)
    if args.files_from:
        try:
            file_args.extend(
                line.strip() for line in Path(args.files_from).read_text(encoding="utf-8").splitlines()
                if line.strip()
            )
        except OSError as exc:
            print(f"ERROR: cannot read --files-from {args.files_from}: {exc}", file=sys.stderr)
            return 2

    if not file_args:
        parser.print_help()
        return 2

    repo_root = Path(args.repo_root)
    content_files = [
        Path(f) for f in file_args
        if Path(f).suffix == ".md" and "content/" in Path(f).as_posix()
    ]
    if not content_files:
        return 0

    try:
        target_map = load_target_map(repo_root)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: cannot load target map: {exc}", file=sys.stderr)
        return 2

    canonical_overrides = load_canonical_overrides(repo_root)
    families_map, platforms_map = _load_display_maps(repo_root)

    # BL-GATE-DEEP-WIRE (2026-08-24): this gate must never falsely block a
    # page that carries a legitimate, pre-approved Layer 3 deep link (e.g.
    # reference.aspose.org's exact class-name matches) -- without consulting
    # backlink_authority.json, audit_file() only ever resolves the shallow
    # family/platform target, so a correct deep link reads as WRONG_TARGET.
    # Loaded unconditionally (no --deep flag here, unlike the audit/backfill
    # CLIs) because this gate's job is exclusively to catch real regressions;
    # a false positive here blocks a commit outright, so the deep index --
    # already pre-verified, safe to trust -- is always consulted when present.
    authority_path = repo_root / "data" / "backlinks" / "workspace" / "backlink_authority.json"
    authority: dict | None = None
    if authority_path.exists():
        try:
            authority = json.loads(authority_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print(f"WARNING: could not load deep authority index: {exc}", file=sys.stderr)

    all_findings: list[Finding] = []
    for path in content_files:
        full_path = path if path.is_absolute() else (repo_root / path)
        if not full_path.exists():
            continue  # deleted file, nothing to check
        findings = check_file(
            full_path, repo_root, target_map, canonical_overrides,
            families_map, platforms_map, scan_mode=args.scan,
            authority=authority,
        )
        all_findings.extend(findings)
        for f in findings:
            print(f)

    fails = [f for f in all_findings if f.level == "FAIL"]
    if fails:
        print(f"\n{len(fails)} backlink compliance FAIL(s) found.", file=sys.stderr)
        return 1

    print(f"OK: {len(content_files)} file(s) checked, 0 backlink compliance failures.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
