#!/usr/bin/env python3
"""
Locale frontmatter contamination gate (TC-ALIAS-005 / TC-URL-005 recurrence guard).

Runs `verify_no_non_english_aliases` and `verify_no_explicit_url` (both already
implemented in scripts/pipeline/audit/frontmatter_schema.py) against every
staged/changed .md file, INCLUDING non-English locale copies.

Why this exists as its own gate instead of relying on audit.py in the
pre-commit hook: scripts/pre-commit-audit.sh Step 5 ("API accuracy audit")
deliberately restricts its audit.py invocation to English-only files
(Mission MT008 TC-MT008-08) so translated pages aren't checked against the
English page's evidence/claims/API frontmatter. `verify_no_non_english_aliases`
and `verify_no_explicit_url` got pulled into that same exclusion by accident --
their entire purpose is to inspect non-English files, so bundling them inside
audit.py meant they never ran at commit time despite existing since
2026-07-27 (TC-ALIAS-005 / TC-URL-005). This is what let the exact same
contamination pattern reappear on 2026-09-15 across 3 more blog posts and
break the blog.aspose.org deploy workflow 3 days running.
See reports/skill-gaps/2026-09-17-blog-deploy-alias-gate-fix.md.

These two checks need no knowledge model, evidence context, or API surface --
they are pure frontmatter-text checks -- so running them unconditionally on
every changed file (English or not) is cheap and has no false-positive risk
of the kind TC-MT008-08 was fixing.

Exit code: 1 if any FAIL, 0 otherwise.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_PIPELINE_ROOT = Path(__file__).resolve().parents[2] / "pipeline"
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))
_LIB_DIR = str(_PIPELINE_ROOT / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from audit.frontmatter_schema import (  # noqa: E402
    verify_no_explicit_url,
    verify_no_non_english_aliases,
)


def _read_file_list(args: list[str]) -> list[Path]:
    """Build the file list from --files-from, --corpus-root, and/or bare
    positional paths. --corpus-root walks a directory recursively (sorted,
    deterministic order) -- added for SCAN-01 (2026-09-17) to run this same
    check as a one-off portfolio-wide sweep across content/{docs,kb,
    products,reference}.aspose.org/**, not just the files a commit/CI diff
    happens to touch."""
    files: list[str] = []
    i = 0
    while i < len(args):
        if args[i] == "--files-from":
            listfile = Path(args[i + 1])
            files.extend(
                line.strip() for line in listfile.read_text(encoding="utf-8").splitlines() if line.strip()
            )
            i += 2
        elif args[i] == "--corpus-root":
            root = Path(args[i + 1])
            files.extend(str(p) for p in sorted(root.rglob("*.md")))
            i += 2
        else:
            files.append(args[i])
            i += 1
    return [Path(f) for f in files if f.endswith(".md")]


def _extract_append_log(argv: list[str]) -> tuple[str | None, list[str]]:
    """Pull --append-log <path> out of argv (OBS-01, 2026-09-17) before the
    remaining args are treated as file paths / --files-from / --corpus-root.
    Returns (log_path_or_None, remaining_argv)."""
    log_path = None
    rest: list[str] = []
    i = 0
    while i < len(argv):
        if argv[i] == "--append-log":
            log_path = argv[i + 1]
            i += 2
        else:
            rest.append(argv[i])
            i += 1
    return log_path, rest


def _current_git_sha() -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, encoding="utf-8",
            timeout=5, check=True,
        ).stdout.strip()
    except Exception:
        return None


def _append_findings_log(log_path: str, file_fails: list[tuple[Path, list]]) -> None:
    """Append one JSON line per FAIL finding (OBS-01): durable, greppable
    trail beyond ephemeral pre-commit/CI terminal output. Never raises --
    a log-write failure must not mask the real pass/fail result."""
    try:
        out = Path(log_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        sha = _current_git_sha()
        ts = datetime.now(timezone.utc).isoformat()
        with out.open("a", encoding="utf-8") as fh:
            for f, fails in file_fails:
                for finding in fails:
                    fh.write(
                        json.dumps(
                            {
                                "timestamp": ts,
                                "git_sha": sha,
                                "file": str(f),
                                "message": finding.message,
                            },
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
    except OSError as exc:
        print(
            f"WARNING: check_locale_frontmatter_contamination could not write "
            f"--append-log {log_path}: {exc} (pass/fail result above is unaffected)",
            file=sys.stderr,
        )


def main(argv: list[str]) -> int:
    log_path, argv = _extract_append_log(argv)
    files = _read_file_list(argv)
    if not files:
        print("check_locale_frontmatter_contamination: no .md files to check.")
        return 0

    fail_count = 0
    file_fails: list[tuple[Path, list]] = []
    for f in files:
        if not f.is_file():
            continue
        findings = verify_no_non_english_aliases(f) + verify_no_explicit_url(f)
        fails = [finding for finding in findings if finding.level == "FAIL"]
        if fails:
            fail_count += len(fails)
            file_fails.append((f, fails))
            print(f"\nFAIL {f}:")
            for finding in fails:
                print(f"  - {finding.message}")

    if log_path and file_fails:
        _append_findings_log(log_path, file_fails)

    if fail_count:
        print(
            f"\nBLOCKED: {fail_count} locale frontmatter contamination finding(s) "
            "(aliases:/url: copied verbatim into a non-English locale file)."
        )
        print(
            "Fix: remove the aliases:/url: key from the flagged locale copy(ies). "
            "Only the English/default-language copy of a page may carry aliases: or url:."
        )
        return 1

    print(f"check_locale_frontmatter_contamination: {len(files)} file(s) checked, 0 FAIL.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
