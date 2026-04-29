"""validate_frontmatter.py — Detect structural and key-level frontmatter issues.

Checks four classes of problem:

1. **Double frontmatter** — two separate ``---...---`` blocks at the top of a
   file.  Hugo silently reads only the first block; real page metadata in the
   second block is completely ignored at render time.  This is caused by
   pipeline writers prepending a new frontmatter block to a file that already
   has one (e.g. due to a regex miss on files without a trailing newline after
   the closing ``---`` fence).

2. **Duplicate YAML keys** — the same key appears more than once inside a
   single frontmatter block.  Uses yaml.compose() to walk the YAML AST before
   key merging, preserving duplicate-key information that yaml.safe_load()
   would silently discard.

3. **Blog evidence completeness** (P-03) — blog posts under ``content/blog.aspose.org/``
   must have a populated ``evidence:`` block with non-empty ``claims`` and ``apis``
   lists, and a ``draft`` field.  Files with ``content_origin: manual-remediation``
   are exempt from the claims/apis check (they are in a remediation state).

4. **Provenance validity** (informational WARNINGs, not errors) — checks that
   ``provenance.last_mechanism``, ``provenance.content_origin``, and
   ``graded_logic_version`` are consistent with the allowed value sets defined
   in ``provenance.py``.  These warnings do NOT cause a non-zero exit code.

Usage:
    python -m validate_frontmatter                  # scan content/ directory
    python -m validate_frontmatter content/docs.aspose.org/en/
    python -m validate_frontmatter path/to/file.md
    python -m validate_frontmatter --json           # JSON output

Exit code:
    0 -- no errors found (warnings are informational and do not affect exit code)
    1 -- errors found (hard gate for CI)
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent.parent.parent
_DEFAULT_SCAN_DIR = _REPO_ROOT / "content"

# ---------------------------------------------------------------------------
# Provenance validity constants (mirrors provenance.py to avoid import cycle)
# ---------------------------------------------------------------------------

# Valid last_mechanism values.  grade-writer and evidence-attach were removed
# after corpus repair (fix_last_mechanism.py) cleaned all 1702 legacy files.
# New values: manual-edit-skill (S-73), page-update (S-20), page-enhance (S-21),
# heal-page (S-26).
_VALID_MECHANISMS = frozenset({
    "translator",
    "fixer", "content-fixer", "metadata-fixer",
    "skill", "agent-edit", "human-edit", "manual-edit-skill",
    "page-update", "page-enhance", "heal-page", "family-sync",
    "unknown",
})

# Valid content_origin values
_VALID_CONTENT_ORIGINS = frozenset({
    "skill-generated", "agent-drafted", "human-authored", "family-sync", "unknown",
})

# Window (days) within which a page is considered "recently graded" for the
# content_created_at check.  Configurable here without code changes in tests.
_CONTENT_CREATED_AT_WINDOW_DAYS = 7

# Matches the first frontmatter block; tolerates files without trailing newline
# after the closing --- (same pattern used by the pipeline writer modules).
_FIRST_FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", re.DOTALL)


def _extract_frontmatter(text: str) -> str | None:
    """Return the raw YAML between the first two --- fences, or None."""
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    return text[3:end].strip()


_BLOG_ROOT_MARKER = "content/blog.aspose.org/"
# Minimum depth inside blog.aspose.org/ for content posts ({family}/{platform}/...)
_BLOG_CONTENT_DEPTH = 3  # parts: family, platform, slug_or_index

# BCP-47 language tag pattern — matches the penultimate suffix of locale files.
# e.g. index.ar.md → suffixes[-2] = '.ar' (match → locale)
#      my-post.v2.md → suffixes[-2] = '.v2' (no match → English)
# Identical to RE_LANG_SUFFIX in scripts/ci/checks/check-blog-slugs.py for consistency.
_LANG_SUFFIX_RE = re.compile(r"\.[a-z]{2}(-[a-zA-Z]{2,4})?$", re.IGNORECASE)


@dataclass
class FrontmatterError:
    path: str
    check: str   # "duplicate_key" | "double_frontmatter" | "blog_evidence" | "provenance_validity"
    line: int
    detail: str
    severity: str = field(default="error")  # "error" | "warning"

    def __str__(self) -> str:
        prefix = "WARNING" if self.severity == "warning" else "ERROR"
        return f"{prefix}: {self.path}:{self.line}: [{self.check}] {self.detail}"


def _check_node(node, path: str, errors: list[FrontmatterError]) -> None:
    """Recursively walk a PyYAML node tree, collecting duplicate mapping keys."""
    if isinstance(node, yaml.MappingNode):
        seen: dict[str, int] = {}
        for key_node, val_node in node.value:
            key = key_node.value
            line = key_node.start_mark.line + 1  # 1-based
            if key in seen:
                errors.append(FrontmatterError(
                    path=path,
                    check="duplicate_key",
                    line=line,
                    detail=f"duplicate key '{key}' (first seen at line {seen[key]})",
                ))
            else:
                seen[key] = line
            _check_node(val_node, path, errors)
    elif isinstance(node, yaml.SequenceNode):
        for item in node.value:
            _check_node(item, path, errors)


def _check_double_frontmatter(text: str, path: str) -> list[FrontmatterError]:
    """Return errors if the file contains more than one frontmatter block.

    A double-frontmatter file looks like::

        ---
        provenance: ...
        ---

        ---
        layout: family
        ...
        ---

    Hugo reads only the first block; everything in the second is silently lost.
    """
    m = _FIRST_FM_RE.match(text)
    if not m:
        return []
    remainder = text[m.end():]
    # The remainder must not start a new --- block (ignoring blank lines).
    if re.match(r"^\s*---\s*\n", remainder):
        offset = m.end()
        # Find the line number of the second block's opening fence.
        line_no = text[:offset].count("\n") + 1
        # Peek at the first key in the second block for a diagnostic hint.
        second_key_m = re.search(r"^\s*(\w+)\s*:", remainder, re.MULTILINE)
        hint = f" (first key in second block: '{second_key_m.group(1)}')" if second_key_m else ""
        return [FrontmatterError(
            path=path,
            check="double_frontmatter",
            line=line_no,
            detail=(
                f"second frontmatter block found at line {line_no}{hint}; "
                "Hugo ignores it — real page metadata is silently lost"
            ),
        )]
    return []


def _is_blog_content_file(path: Path) -> bool:
    """Return True if path is a canonical English blog post content file.

    Only English source files (named exactly ``index.md`` or a flat ``{slug}.md``
    at depth >= 3) are checked for evidence completeness.  Locale translation
    variants (index.ar.md, index.bg.md, etc.) are excluded.
    """
    path_str = str(path).replace("\\", "/")
    if _BLOG_ROOT_MARKER not in path_str:
        return False
    # Locale files have a BCP-47 language tag as the penultimate suffix:
    #   index.ar.md    → suffixes ['.ar',    '.md'] → suffixes[-2] = '.ar'    → match
    #   index.zh-CN.md → suffixes ['.zh-CN', '.md'] → suffixes[-2] = '.zh-CN' → match
    # An English versioned post like my-post.v2.md → suffixes[-2] = '.v2' → no match
    if len(path.suffixes) > 1 and _LANG_SUFFIX_RE.search(path.suffixes[-2]):
        return False
    # Find depth inside blog root
    idx = path_str.index(_BLOG_ROOT_MARKER)
    rel = path_str[idx + len(_BLOG_ROOT_MARKER):]
    parts = [p for p in rel.split("/") if p]
    # Directory posts (index.md) live at {family}/{platform}/{slug}/index.md → 4 parts.
    # Flat posts ({slug}.md) live at {family}/{platform}/{slug}.md → 3 parts.
    # Platform-level index.md ({family}/{platform}/index.md) has 3 parts but is NOT
    # a content post — it is a section landing page.
    min_depth = _BLOG_CONTENT_DEPTH + 1 if path.name == "index.md" else _BLOG_CONTENT_DEPTH
    return len(parts) >= min_depth


def _check_blog_evidence(
    text: str, path: str, errors: list[FrontmatterError]
) -> None:
    """Check blog posts have a populated evidence block and a draft field (P-03)."""
    fm_text = _extract_frontmatter(text)
    if not fm_text:
        return
    try:
        fm = yaml.safe_load(fm_text)
    except yaml.YAMLError:
        return
    if not isinstance(fm, dict):
        return

    # draft field must be present
    if "draft" not in fm:
        errors.append(FrontmatterError(
            path=path,
            check="blog_evidence",
            line=1,
            detail="blog post missing `draft` field — add `draft: false`",
        ))

    # Skip evidence completeness check for remediation-state files
    provenance = fm.get("provenance") or {}
    if isinstance(provenance, dict):
        origin = provenance.get("content_origin", "")
        if origin == "manual-remediation":
            return

    evidence = fm.get("evidence")
    if not isinstance(evidence, dict):
        errors.append(FrontmatterError(
            path=path,
            check="blog_evidence",
            line=1,
            detail=(
                f"blog post missing `evidence:` block — "
                f"run: /evidence-repair {path}"
            ),
        ))
        return

    claims = evidence.get("claims") or []
    if not claims:
        errors.append(FrontmatterError(
            path=path,
            check="blog_evidence",
            line=1,
            detail=(
                f"blog post evidence.claims is empty — "
                f"run: /evidence-repair {path}"
            ),
        ))

    apis = evidence.get("apis") or []
    if not apis:
        errors.append(FrontmatterError(
            path=path,
            check="blog_evidence",
            line=1,
            detail=(
                f"blog post evidence.apis is empty — "
                f"run: /evidence-repair {path}"
            ),
        ))


def _check_provenance_validity(
    text: str, path: str, errors: list[FrontmatterError],
    _now: _dt.datetime | None = None,
) -> None:
    """Emit provenance_validity ERRORs for invalid mechanism/origin values and missing graded_logic_version.

    All findings are severity="error" — they WILL affect the exit code.

    *_now* is injectable for testing; defaults to ``datetime.now(UTC)`` when None.
    """
    fm_text = _extract_frontmatter(text)
    if not fm_text:
        return
    try:
        fm = yaml.safe_load(fm_text)
    except yaml.YAMLError:
        return
    if not isinstance(fm, dict):
        return

    # Check 2a: provenance block must exist on English content pages (Control 1 — AGENTS.md §6.3)
    # Structural pages (layout: list/family/reference-home) are exempt — they are Hugo section
    # indices with no narrative content. Locale files are exempt because they have provenance
    # with translation_origin (and thus are never None here). Only fires when no provenance key
    # exists at all — i.e. skill generated the page without writing a provenance block.
    _STRUCTURAL_LAYOUTS = frozenset({"list", "family", "reference-home"})
    if fm.get("provenance") is None and fm.get("layout") not in _STRUCTURAL_LAYOUTS:
        errors.append(FrontmatterError(
            path=path,
            check="provenance_validity",
            line=1,
            detail=(
                "provenance block absent — every skill-generated English content page must "
                "have a provenance block (Control 1, AGENTS.md §6.3). "
                "Run /evidence-repair or regenerate via the originating skill."
            ),
            severity="error",
        ))

    # Check 1: last_mechanism validity
    provenance = fm.get("provenance") or {}
    if isinstance(provenance, dict):
        last_mechanism = provenance.get("last_mechanism")
        if last_mechanism is not None and last_mechanism not in _VALID_MECHANISMS:
            sorted_vals = ", ".join(sorted(_VALID_MECHANISMS))
            errors.append(FrontmatterError(
                path=path,
                check="provenance_validity",
                line=1,
                detail=(
                    f"invalid last_mechanism value '{last_mechanism}' "
                    f"— must be one of: {sorted_vals}"
                ),
                severity="error",
            ))

        # Check 2: content_origin validity
        content_origin = provenance.get("content_origin")
        if content_origin is not None and content_origin not in _VALID_CONTENT_ORIGINS:
            sorted_origins = ", ".join(sorted(_VALID_CONTENT_ORIGINS))
            errors.append(FrontmatterError(
                path=path,
                check="provenance_validity",
                line=1,
                detail=(
                    f"invalid content_origin value '{content_origin}' "
                    f"— must be one of: {sorted_origins}"
                ),
                severity="error",
            ))

        # Check 2b: provenance block present but content_origin absent (English pages only)
        # Locale files use translation_origin instead — skip them.
        if (
            content_origin is None
            and "translation_origin" not in provenance
            and isinstance(provenance, dict)
            and provenance  # non-empty provenance block
        ):
            errors.append(FrontmatterError(
                path=path,
                check="provenance_validity",
                line=1,
                detail=(
                    "provenance block present but content_origin is missing — "
                    "run provenance_backfill.py or set content_origin explicitly"
                ),
                severity="error",
            ))

    # Check 3: graded_logic_version was moved to the external grade manifest (ARCH-04).
    # It no longer belongs in frontmatter — skip this check.

    # Check 4: recently graded page missing content_created_at
    graded_at_raw = fm.get("graded_at")
    if graded_at_raw is not None:
        try:
            if isinstance(graded_at_raw, _dt.datetime):
                graded_at = graded_at_raw
                if graded_at.tzinfo is None:
                    graded_at = graded_at.replace(tzinfo=_dt.timezone.utc)
            else:
                # Quoted string: "2026-04-03T10:00:00Z" or "2026-04-03T10:00:00+00:00"
                graded_at_str = str(graded_at_raw).replace("Z", "+00:00")
                graded_at = _dt.datetime.fromisoformat(graded_at_str)
                if graded_at.tzinfo is None:
                    graded_at = graded_at.replace(tzinfo=_dt.timezone.utc)

            now = _now if _now is not None else _dt.datetime.now(_dt.timezone.utc)
            age_days = (now - graded_at).days
            if 0 <= age_days < _CONTENT_CREATED_AT_WINDOW_DAYS:
                prov = fm.get("provenance") or {}
                if isinstance(prov, dict) and "content_created_at" not in prov:
                    errors.append(FrontmatterError(
                        path=path,
                        check="provenance_validity",
                        line=1,
                        detail="recently graded page missing content_created_at in provenance block",
                        severity="error",
                    ))
        except (ValueError, TypeError, OverflowError):
            pass  # Unparseable graded_at — skip check


def check_file(path: Path) -> list[FrontmatterError]:
    """Return list of frontmatter errors found in path."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    errors: list[FrontmatterError] = []

    # Check 1: double frontmatter blocks
    errors.extend(_check_double_frontmatter(text, str(path)))

    # Check 2: duplicate YAML keys within the first block
    fm_text = _extract_frontmatter(text)
    if fm_text:
        try:
            node = yaml.compose(fm_text)
            if node is not None:
                _check_node(node, str(path), errors)
        except yaml.YAMLError:
            pass  # Malformed YAML — Hugo would catch this at build time

    # Check 3 (P-03): blog evidence completeness
    if _is_blog_content_file(path):
        _check_blog_evidence(text, str(path), errors)

    # Check 4: provenance validity errors — invalid values cause non-zero exit code
    _check_provenance_validity(text, str(path), errors)

    return errors


def scan_paths(paths: list[Path]) -> list[FrontmatterError]:
    """Scan a list of files and/or directories for frontmatter issues."""
    all_errors: list[FrontmatterError] = []
    for p in paths:
        if p.is_dir():
            for f in sorted(p.rglob("*.md")):
                all_errors.extend(check_file(f))
        elif p.is_file() and p.suffix == ".md":
            all_errors.extend(check_file(p))
    return all_errors


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Detect structural and key-level frontmatter issues."
    )
    parser.add_argument(
        "paths", nargs="*", type=Path,
        help="Files or directories to check. Defaults to content/",
    )
    parser.add_argument(
        "--files-from", dest="files_from", metavar="FILE",
        help="Read paths to check (one per line) from FILE. "
             "Merged with any positional paths. Empty lines are ignored.",
    )
    parser.add_argument(
        "--json", dest="json_output", action="store_true",
        help="Output results as JSON",
    )
    args = parser.parse_args(argv)

    scan_targets: list[Path] = list(args.paths) if args.paths else []
    if args.files_from:
        try:
            extra = Path(args.files_from).read_text(encoding="utf-8").splitlines()
            scan_targets.extend(Path(p) for p in extra if p.strip())
        except OSError as exc:
            print(f"ERROR: cannot read --files-from '{args.files_from}': {exc}", file=sys.stderr)
            return 1
        # If --files-from was given but the file was empty, treat as "no files to check"
        # (do NOT fall back to the default full scan — that would be surprising).
    elif not scan_targets:
        scan_targets = [_DEFAULT_SCAN_DIR]
    all_findings = scan_paths(scan_targets)
    hard_errors = [e for e in all_findings if e.severity == "error"]
    warnings = [e for e in all_findings if e.severity == "warning"]

    if args.json_output:
        print(json.dumps(
            [
                {
                    "path": e.path,
                    "check": e.check,
                    "line": e.line,
                    "detail": e.detail,
                    "severity": e.severity,
                }
                for e in all_findings
            ],
            indent=2,
        ))
    else:
        if hard_errors:
            print(f"ERROR: {len(hard_errors)} frontmatter issue(s) found:", file=sys.stderr)
            for e in hard_errors:
                print(f"  {e}", file=sys.stderr)
        else:
            print("OK: no frontmatter errors found.")
        if warnings:
            print(
                f"WARNING: {len(warnings)} provenance warning(s) (informational, not blocking):",
                file=sys.stderr,
            )
            for w in warnings:
                print(f"  {w}", file=sys.stderr)

    return 1 if hard_errors else 0


if __name__ == "__main__":
    sys.exit(main())
