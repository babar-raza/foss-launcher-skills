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

import sys
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
    files: list[str] = []
    i = 0
    while i < len(args):
        if args[i] == "--files-from":
            listfile = Path(args[i + 1])
            files.extend(
                line.strip() for line in listfile.read_text(encoding="utf-8").splitlines() if line.strip()
            )
            i += 2
        else:
            files.append(args[i])
            i += 1
    return [Path(f) for f in files if f.endswith(".md")]


def main(argv: list[str]) -> int:
    files = _read_file_list(argv)
    if not files:
        print("check_locale_frontmatter_contamination: no .md files to check.")
        return 0

    fail_count = 0
    for f in files:
        if not f.is_file():
            continue
        findings = verify_no_non_english_aliases(f) + verify_no_explicit_url(f)
        fails = [finding for finding in findings if finding.level == "FAIL"]
        if fails:
            fail_count += len(fails)
            print(f"\nFAIL {f}:")
            for finding in fails:
                print(f"  - {finding.message}")

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
