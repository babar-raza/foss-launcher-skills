# Adapted from aspose.org
#!/usr/bin/env python3
"""normalize_yaml_style.py — Restore | literal block scalar style for product pages.

PROBLEM
-------
scripts/pipeline/evidence/writer.py (now fixed) previously performed a full
yaml.safe_load + yaml.dump round-trip on Hugo page frontmatter. This silently
converted | literal block scalars (the correct and unambiguous style for
code-containing content fields) to PyYAML-chosen equivalents:

  - Double-quoted with \\n escapes:
      content: "Install with pip...\\n\\n```bash\\n..."

  - Single-quoted multi-line flow scalar (6-space continuation indent):
      content: 'Open the workbook saved above, add a bar chart over a range of rows,
        then call `save()` three times...

        ```python
        from aspose.cells_foss import Workbook

Both forms can render differently in Hugo/goldmark — code fences may arrive with
unexpected leading whitespace, or blank lines may be lost/added.

STRATEGY
--------
For every file in content/products/:

1. Parse the frontmatter with yaml.safe_load to recover the actual string values.
2. Re-serialize with a custom LiteralDumper that forces | style for any string
   containing newlines (multi-line).
3. Re-apply the fixed evidence/writer.py to restore the evidence block from the
   parsed metadata (so it is NOT passed through the full yaml.dump).
4. Validate that the parsed content of each multi-line field is semantically
   identical before and after normalization.

IMPORTANT: This script only touches content/products/. It must NOT be
run on blog, docs, kb, or reference content — single blank lines in those files are
legitimate Python/Java style and must be preserved.

USAGE
-----
    # Dry run (show what would change, do not write):
    python scripts/pipeline/commands/migration/normalize_yaml_style.py --dry-run

    # Apply to all product pages:
    python scripts/pipeline/commands/migration/normalize_yaml_style.py

    # Apply to a specific file:
    python scripts/pipeline/commands/migration/normalize_yaml_style.py content/products/en/cells/python/_index.md
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import textwrap
from pathlib import Path

_PIPELINE_ROOT = Path(__file__).resolve().parent.parent.parent  # commands/{domain}/ -> commands/ -> pipeline/
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

import yaml
from core.fs import atomic_write  # noqa: E402
from core.markdown import split_frontmatter  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
_PRODUCTS_DIR = Path(os.environ.get("PRODUCTS_DIR", str(_REPO_ROOT / "content" / "products")))

# Matches the evidence block (to extract and re-apply separately)
_EVIDENCE_BLOCK_RE = re.compile(
    r"^evidence:[ \t]*(?:\n[ \t]+[^\n]*)*",
    re.MULTILINE,
)


# ---------------------------------------------------------------------------
# Custom YAML dumper: forces | style for multi-line strings
# ---------------------------------------------------------------------------

class _LiteralDumper(yaml.Dumper):
    """YAML dumper that serializes all multi-line strings as | literal block scalars."""
    pass


def _literal_str_representer(dumper, data):
    if "\n" in data:
        # Ensure the string ends with exactly one newline (| style requires it)
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


_LiteralDumper.add_representer(str, _literal_str_representer)


def _serialize_frontmatter_literal(fm_dict: dict) -> str:
    """Serialize frontmatter dict with | style for all multi-line strings."""
    return yaml.dump(
        fm_dict,
        Dumper=_LiteralDumper,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
    )


# ---------------------------------------------------------------------------
# Evidence block extraction and re-application
# ---------------------------------------------------------------------------

def _extract_evidence_block(fm_text: str) -> str | None:
    """Return the raw evidence: block text from frontmatter, or None."""
    m = _EVIDENCE_BLOCK_RE.search(fm_text)
    return m.group(0) if m else None


def _strip_evidence(fm_text: str) -> str:
    """Remove the evidence: block from frontmatter text."""
    return _EVIDENCE_BLOCK_RE.sub("", fm_text).rstrip("\n") + "\n"


# ---------------------------------------------------------------------------
# Core normalization
# ---------------------------------------------------------------------------

def _has_non_literal_multiline(fm_text: str) -> bool:
    """Return True if any multi-line string in the frontmatter is NOT in | style.

    Detection heuristics:
    - Double-quoted scalar with \\n escape: key: "...\\n..."
    - Single-quoted multi-line flow scalar (continuation lines indented past the key)
    """
    # Double-quoted with \n escape
    if re.search(r':\s*"[^"]*\\n[^"]*"', fm_text):
        return True
    # Single-quoted multi-line flow scalar: value starts with ' and the
    # next physical line is indented (continuation)
    if re.search(r":\s*'[^\n]*\n\s+\S", fm_text, re.MULTILINE):
        return True
    return False


def normalize_file(filepath: Path, dry_run: bool = False, verbose: bool = True) -> bool:
    """Normalize YAML scalar styles in a single product page file.

    Returns True if the file was changed (or would be changed in dry_run).
    """
    text = filepath.read_text(encoding="utf-8")
    parts = split_frontmatter(text)
    if parts is None:
        return False  # no frontmatter to fix

    open_fence, fm_text, close_fence = parts
    # body = everything after the matched frontmatter block
    # split_frontmatter consumed: open_fence + fm_text + close_fence
    body = text[len(open_fence) + len(fm_text) + len(close_fence):]

    # Quick check: if frontmatter already uses correct styles, skip
    if not _has_non_literal_multiline(fm_text):
        return False

    # Parse the frontmatter to get actual string values
    try:
        fm_dict = yaml.safe_load(fm_text) or {}
    except yaml.YAMLError as e:
        print(f"  SKIP (YAML error): {filepath.relative_to(_REPO_ROOT)}: {e}",
              file=sys.stderr)
        return False

    # Extract evidence block text to re-apply after normalization
    evidence_text = _extract_evidence_block(fm_text)

    # Remove evidence from the dict and text before normalization
    # (it will be re-applied via the fixed writer)
    fm_dict_no_ev = {k: v for k, v in fm_dict.items() if k != "evidence"}

    # Re-serialize with | style for all multi-line strings
    new_fm = _serialize_frontmatter_literal(fm_dict_no_ev)

    # Re-append the evidence block verbatim (not through yaml.dump)
    if evidence_text:
        new_fm = new_fm.rstrip("\n") + "\n" + evidence_text

    # Validate: parsed content of all multi-line fields must be identical
    try:
        new_fm_dict = yaml.safe_load(new_fm) or {}
    except yaml.YAMLError as e:
        print(f"  SKIP (validation error): {filepath.relative_to(_REPO_ROOT)}: {e}",
              file=sys.stderr)
        return False

    # Compare all non-evidence fields
    orig_no_ev = {k: v for k, v in fm_dict.items() if k != "evidence"}
    new_no_ev = {k: v for k, v in new_fm_dict.items() if k != "evidence"}
    if orig_no_ev != new_no_ev:
        print(
            f"  SKIP (semantic mismatch): {filepath.relative_to(_REPO_ROOT)}\n"
            f"    Original keys: {set(orig_no_ev)}\n"
            f"    New keys: {set(new_no_ev)}",
            file=sys.stderr,
        )
        return False

    # Post-conversion check: warn if any multi-line string still can't use | style.
    # This happens when PyYAML rejects | for a string with trailing whitespace or
    # no trailing newline (e.g. "value ``` " — trailing space prevents | conversion).
    if _has_non_literal_multiline(new_fm):
        try:
            rel = filepath.relative_to(_REPO_ROOT)
        except ValueError:
            rel = filepath
        print(
            f"  WARN (could not fully convert to | style): {rel} — "
            f"some multi-line strings have trailing whitespace or missing trailing \\n",
            file=sys.stderr,
        )

    new_text = f"{open_fence}{new_fm}{close_fence}{body}"

    if new_text == text:
        return False  # no actual change

    if verbose:
        rel = filepath.relative_to(_REPO_ROOT)
        if dry_run:
            print(f"  WOULD FIX: {rel}")
        else:
            print(f"  FIXED: {rel}")

    if not dry_run:
        atomic_write(filepath, new_text)

    return True


def normalize_directory(
    directory: Path,
    dry_run: bool = False,
    verbose: bool = True,
) -> tuple[int, int]:
    """Normalize all .md files in a directory tree.

    Returns (changed_count, skipped_count).
    """
    changed = skipped = 0
    files = sorted(directory.rglob("*.md"))
    for f in files:
        try:
            if normalize_file(f, dry_run=dry_run, verbose=verbose):
                changed += 1
            else:
                skipped += 1
        except Exception as e:
            print(f"  ERROR: {f}: {e}", file=sys.stderr)
            skipped += 1
    return changed, skipped


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=textwrap.dedent(__doc__ or ""),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "paths",
        nargs="*",
        help="Specific files or directories to normalize. "
             "Defaults to content/products/.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be changed without writing files.",
    )
    p.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-file output; only show summary.",
    )
    return p


def main(argv=None):
    args = _build_parser().parse_args(argv)
    verbose = not args.quiet

    targets: list[Path] = []
    if args.paths:
        for p in args.paths:
            path = Path(p)
            if not path.is_absolute():
                path = Path.cwd() / path
            targets.append(path)
    else:
        targets = [_PRODUCTS_DIR]

    total_changed = total_skipped = 0
    for target in targets:
        if target.is_file():
            changed = normalize_file(target, dry_run=args.dry_run, verbose=verbose)
            total_changed += int(changed)
            total_skipped += int(not changed)
        elif target.is_dir():
            c, s = normalize_directory(target, dry_run=args.dry_run, verbose=verbose)
            total_changed += c
            total_skipped += s
        else:
            print(f"WARNING: path not found: {target}", file=sys.stderr)

    action = "Would fix" if args.dry_run else "Fixed"
    print(f"\n{action} {total_changed} files. {total_skipped} files unchanged or skipped.")
    return 0 if total_changed >= 0 else 1


if __name__ == "__main__":
    sys.exit(main())
