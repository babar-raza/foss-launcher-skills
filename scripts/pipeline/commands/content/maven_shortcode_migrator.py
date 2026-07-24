"""maven_shortcode_migrator.py — Mission MT008 (plans/master-plan.md), TC-MT008-08.

Deterministic codemod: replaces literal Maven-coordinate text for a Java-FOSS
family with the maven-coord/maven-gav Hugo shortcode calls (built in TC-MT008-02),
across all 5 subdomains and all locales. Not LLM-authored per-file -- a single
regex-driven transform applied uniformly, so the migration itself does not
carry the same "might mistype the replacement" risk the original bug did.

Per TC-MT008-00's determination, coordinate_migrator.py/install_block_updater.py
were evaluated and found not to be a structural fit (they do old-value/new-value
text substitution; this mission needs "replace this recognizable block/span with
a shortcode call" instead, and needs products.aspose.org + reference.aspose.org
coverage those tools never had). This is new, purpose-built machinery, built on
top of proven primitives where they exist (fence detection reused from the same
approach as coordinate_migrator.py; safe_content_write reused verbatim).

Scope: content/{docs,blog,kb,products}.aspose.org/**/{family}/java/** for
family in {cells, 3d, pdf} -- slides is explicitly excluded pending TC-MT008-09's
human decision, reference.aspose.org is explicitly excluded per TC-MT008-00
(package-namespace mentions there are a different, correct fact).

Two independent match/replace passes, both operating on RAW file text (not
frontmatter-stripped -- products.aspose.org pages embed their whole visible
content inside YAML frontmatter, same discovery as TC-MT008-07):

1. BLOCK pass: a fenced code block containing a recognisable
   <dependency>...<groupId>...</groupId>...<artifactId>{family-keyword}...
   </artifactId>...</dependency> shape is replaced whole (fence markers
   included, indentation preserved) with the maven-coord shortcode line.

2. INLINE pass: a groupId:artifactId(:version) coordinate mention for the
   family, backtick-wrapped or bare, is replaced with the bare maven-gav
   shortcode call (never backtick-wrapped -- it renders its own <code>,
   confirmed via a real Hugo build in TC-MT008-02).

Matching is structural (does this look like a coordinate block/mention for
THIS family), not value-based (is the current groupId literally "com.aspose")
-- deliberately, so already-corrected-but-still-literal text (e.g. the
2026-07-16 S-110 sprint's English fixes) is ALSO migrated to the shortcode,
not skipped as "already fine". A literal value is a staleness risk regardless
of whether it currently happens to be correct (see maven_coordinates.py's
audit module docstring for the same principle).

CLI:
    PYTHONPATH=scripts/pipeline .venv/Scripts/python -m commands.content.maven_shortcode_migrator cells --dry-run
    PYTHONPATH=scripts/pipeline .venv/Scripts/python -m commands.content.maven_shortcode_migrator cells --execute
    PYTHONPATH=scripts/pipeline .venv/Scripts/python -m commands.content.maven_shortcode_migrator cells --execute --limit 20
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))
_LIB_DIR = str(_PIPELINE_ROOT / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from lib.provenance import safe_content_write, ProtectedPageError  # noqa: E402

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[4]
_REPO_ROOT = _DEFAULT_REPO_ROOT
_CONTENT_ROOT = _REPO_ROOT / "content"


def configure(*, repo_root: "Path | str | None" = None) -> None:
    global _REPO_ROOT, _CONTENT_ROOT
    _REPO_ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT
    _CONTENT_ROOT = _REPO_ROOT / "content"


# Family -> substring that must appear in the artifactId for a block/inline
# match to be considered "for this family" (matches both "cells-foss" and
# "aspose-cells-foss" style artifactIds, both observed in real content).
_FAMILY_ARTIFACT_KEYWORD = {
    "cells": "cells-foss",
    "3d": "3d-foss",
    "pdf": "pdf-foss",
}

# Subdomains this codemod is allowed to touch. reference.aspose.org is
# deliberately absent -- TC-MT008-00 determined its com.aspose.* mentions are
# real Java package namespaces, not Maven coordinates.
_IN_SCOPE_SUBSITES = ("docs.aspose.org", "blog.aspose.org", "kb.aspose.org", "products.aspose.org")

_FENCE_RE = re.compile(r"^([ \t]*)(```|~~~)([^\n]*)\n(.*?)\n[ \t]*(```|~~~)[ \t]*$", re.DOTALL | re.MULTILINE)
_GROUPID_RE = re.compile(r"<groupId>\s*((?:com|org)\.aspose(?:\.[\w.]+)?)\s*</groupId>")
_ARTIFACTID_RE = re.compile(r"<artifactId>\s*([\w.-]+)\s*</artifactId>")

R_MIGRATED = "MIGRATED"
R_NOOP = "NOOP_NO_MATCH"
R_DRY_RUN = "DRY_RUN"
R_SKIPPED_PROTECTED = "SKIPPED_PROTECTED"


def _find_fenced_blocks(text: str) -> list[tuple[int, int, str]]:
    """Return (start, end, indent) for every fenced code block in text.

    indent is the leading whitespace of the opening fence line, needed to
    keep YAML block-scalar indentation valid when the block is replaced
    (products.aspose.org pages embed fenced blocks inside `content: |-`
    frontmatter values).
    """
    out = []
    for m in _FENCE_RE.finditer(text):
        out.append((m.start(), m.end(), m.group(1)))
    return out


def _block_is_dependency_for_family(block_text: str, artifact_keyword: str) -> bool:
    gid_match = _GROUPID_RE.search(block_text)
    aid_match = _ARTIFACTID_RE.search(block_text)
    if not gid_match or not aid_match:
        return False
    return artifact_keyword in aid_match.group(1)


def _build_inline_pattern(artifact_keyword: str) -> re.Pattern:
    # groupId:artifactId(:version), optionally backtick-wrapped. groupId is
    # any aspose-namespaced value (com.aspose, org.aspose, org.aspose.slides.foss
    # style) -- deliberately not anchored to a single "correct" value, matching
    # the block pass's structural (not value-based) philosophy. The optional
    # "aspose-" prefix before artifact_keyword handles the observed
    # "aspose-cells-foss" vs bare "cells-foss" variance in real content.
    pattern = (
        r"`?"
        r"(?:com|org)\.aspose(?:\.[\w.]+)?:"
        r"(?:aspose-)?" + re.escape(artifact_keyword) +
        r"(?::[\w.-]+)?"
        r"`?"
    )
    return re.compile(pattern)


def migrate_file(filepath: Path, family: str, *, dry_run: bool = True) -> dict[str, Any]:
    """Apply the block + inline migration passes to a single file.

    Returns a result dict. Never partially writes -- either the full
    transform is applied (both passes, however many matches each finds) or
    nothing is written.
    """
    result: dict[str, Any] = {
        "path": str(filepath), "result": R_NOOP,
        "block_replacements": 0, "inline_replacements": 0, "error": "",
    }

    if not filepath.is_file():
        result["error"] = "file not found"
        return result

    artifact_keyword = _FAMILY_ARTIFACT_KEYWORD[family]
    original = filepath.read_text(encoding="utf-8", errors="replace")
    text = original

    # Pass 1: block replacement. Iterate fenced blocks last-to-first so
    # earlier offsets stay valid as we splice.
    blocks = _find_fenced_blocks(text)
    block_count = 0
    for start, end, indent in reversed(blocks):
        block_text = text[start:end]
        if _block_is_dependency_for_family(block_text, artifact_keyword):
            replacement = f'{indent}{{{{< maven-coord "{family}" "java" >}}}}'
            text = text[:start] + replacement + text[end:]
            block_count += 1

    # Pass 2: inline replacement (bare or backtick-wrapped mention), applied
    # after the block pass so it never double-matches text already replaced.
    inline_pattern = _build_inline_pattern(artifact_keyword)
    inline_replacement = f'{{{{< maven-gav "{family}" "java" >}}}}'
    text, inline_count = inline_pattern.subn(inline_replacement, text)

    result["block_replacements"] = block_count
    result["inline_replacements"] = inline_count

    if block_count == 0 and inline_count == 0:
        result["result"] = R_NOOP
        return result

    if dry_run:
        result["result"] = R_DRY_RUN
        return result

    try:
        safe_content_write(filepath, text, mechanism="maven-shortcode-migrator")
    except ProtectedPageError:
        result["result"] = R_SKIPPED_PROTECTED
        return result

    result["result"] = R_MIGRATED
    return result


def discover_files(family: str) -> list[Path]:
    """Find every content file for family/java across in-scope subsites, all locales."""
    files: list[Path] = []
    for subsite in _IN_SCOPE_SUBSITES:
        base = _CONTENT_ROOT / subsite
        if subsite == "blog.aspose.org":
            search_root = base / family / "java"
        else:
            # docs/kb/products use content/{site}/{locale}/{family}/{platform}/...
            search_root = base
        if not search_root.is_dir():
            continue
        if subsite == "blog.aspose.org":
            files.extend(p for p in search_root.rglob("*.md"))
        else:
            for locale_dir in search_root.iterdir():
                if not locale_dir.is_dir():
                    continue
                target = locale_dir / family / "java"
                if target.is_dir():
                    files.extend(p for p in target.rglob("*.md"))
    return sorted(set(files))


def run_migration(family: str, *, dry_run: bool = True, limit: "int | None" = None) -> dict[str, Any]:
    if family not in _FAMILY_ARTIFACT_KEYWORD:
        raise ValueError(f"family must be one of {list(_FAMILY_ARTIFACT_KEYWORD)}, got {family!r}")

    files = discover_files(family)
    if limit is not None:
        files = files[:limit]

    summary: dict[str, Any] = {
        "family": family, "dry_run": dry_run,
        "files_checked": 0, "files_migrated": 0, "files_noop": 0,
        "files_skipped_protected": 0, "total_block_replacements": 0,
        "total_inline_replacements": 0, "results": [],
    }

    for fp in files:
        summary["files_checked"] += 1
        res = migrate_file(fp, family, dry_run=dry_run)
        summary["results"].append(res)
        r = res["result"]
        if r in (R_MIGRATED, R_DRY_RUN):
            summary["files_migrated"] += 1
            summary["total_block_replacements"] += res["block_replacements"]
            summary["total_inline_replacements"] += res["inline_replacements"]
        elif r == R_SKIPPED_PROTECTED:
            summary["files_skipped_protected"] += 1
        else:
            summary["files_noop"] += 1

    return summary


def main(argv: "list[str] | None" = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="maven_shortcode_migrator")
    parser.add_argument("family", choices=list(_FAMILY_ARTIFACT_KEYWORD))
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)

    dry_run = not args.execute
    summary = run_migration(args.family, dry_run=dry_run, limit=args.limit)

    mode = "DRY-RUN" if dry_run else "EXECUTE"
    print(f"\nmaven_shortcode_migrator [{mode}] family={args.family}")
    print(f"  files_checked:            {summary['files_checked']}")
    print(f"  files_migrated:           {summary['files_migrated']}")
    print(f"  files_noop:               {summary['files_noop']}")
    print(f"  files_skipped_protected:  {summary['files_skipped_protected']}")
    print(f"  total_block_replacements: {summary['total_block_replacements']}")
    print(f"  total_inline_replacements:{summary['total_inline_replacements']}")

    for res in summary["results"]:
        if res["result"] not in (R_NOOP,):
            print(f"    {res['result']}: {res['path']} (block={res['block_replacements']} inline={res['inline_replacements']})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
