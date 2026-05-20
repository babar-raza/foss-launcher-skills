#!/usr/bin/env python3
# Adapted from aspose.org
"""validate_product_yaml.py — CI-ready gate for products.aspose.org content quality.

Checks every Markdown file under content/products/ (or specified paths) for:

  1. GARBLED code blocks (exit 1): A fenced-code-block language tag followed by a
     space/tab then non-whitespace character inside YAML frontmatter. This indicates
     that pipeline yaml.dump round-tripping has collapsed code lines into a
     space-joined single line inside a quoted scalar.

     Pattern: ```lang<space>next-token  (inside YAML frontmatter)

  2. NON-LITERAL multi-line scalars (warning or --strict exit 1): YAML frontmatter
     contains double-quoted scalars with \\n escapes, or single-quoted flow scalars
     with continuation lines. These are not necessarily garbled, but they indicate
     the page was processed by a yaml.dump round-trip and may need normalization.

USAGE
-----
    # Check all product pages (CI mode):
    python scripts/pipeline/commands/content/validate_product_yaml.py

    # Strict mode — also exit 1 on non-literal scalars:
    python scripts/pipeline/commands/content/validate_product_yaml.py --strict

    # Check a specific file or directory:
    python scripts/pipeline/commands/content/validate_product_yaml.py content/products/en/

EXIT CODES
----------
    0 — All checks passed (or only warnings in non-strict mode)
    1 — One or more garbled code blocks found (always)
        One or more non-literal scalars found (only with --strict)
"""
from __future__ import annotations

import argparse
import re
import sys
import textwrap
from pathlib import Path



def _resolve_repo_root() -> Path:
    """Return the repo root via $CONTENT_REPO_PATH or config_loader."""
    import os as _os
    env = _os.environ.get("CONTENT_REPO_PATH")
    if env:
        return Path(env).resolve()
    try:
        return resolve_content_repo()
    except Exception:
        return _HERE.parents[3]

_REPO_ROOT = _resolve_repo_root()
_PRODUCTS_DIR = _REPO_ROOT / "content" / "products"



try:
    from core.markdown import extract_frontmatter_body  # noqa: E402
except ImportError:
    import re as _re
    _FM_RE = _re.compile(r"^---\s*\n(.*?)\n---\s*\n", _re.DOTALL)
    def extract_frontmatter_body(text):
        m = _FM_RE.match(text)
        return m.group(1) if m else None

# Garbled: language tag immediately followed by space/tab then a non-whitespace char.
# This pattern appears when code lines were joined by YAML flow-scalar line folding.
_GARBLED_CODE_RE = re.compile(r"```\w+[ \t]+\S")

# Non-literal multi-line string indicators (from normalize_yaml_style.py)
_DOUBLE_QUOTED_NL_RE = re.compile(r':\s*"[^"]*\\n[^"]*"')
_SINGLE_QUOTED_CONT_RE = re.compile(r":\s*'[^\n]*\n\s+\S", re.MULTILINE)


def check_file(filepath: Path) -> tuple[list[str], list[str]]:
    """Return (errors, warnings) for a single file.

    errors   — garbled code blocks (always cause exit 1)
    warnings — non-literal multi-line scalars (cause exit 1 only with --strict)
    """
    try:
        text = filepath.read_text(encoding="utf-8")
    except OSError as e:
        return [f"read error: {e}"], []

    fm_text = extract_frontmatter_body(text)
    if fm_text is None:
        return [], []

    errors: list[str] = []
    warnings: list[str] = []

    if _GARBLED_CODE_RE.search(fm_text):
        errors.append("garbled code block (language tag + space + non-whitespace inside YAML)")

    if _DOUBLE_QUOTED_NL_RE.search(fm_text):
        warnings.append("double-quoted scalar with \\n escape (run normalize_yaml_style.py)")
    if _SINGLE_QUOTED_CONT_RE.search(fm_text):
        warnings.append("single-quoted multi-line flow scalar (run normalize_yaml_style.py)")

    return errors, warnings


def validate_paths(
    targets: list[Path],
    strict: bool = False,
    quiet: bool = False,
) -> int:
    """Validate one or more files/directories. Returns exit code (0 or 1)."""
    error_count = 0
    warning_count = 0
    file_count = 0

    def _process(filepath: Path) -> None:
        nonlocal error_count, warning_count, file_count
        file_count += 1
        errors, warnings = check_file(filepath)
        try:
            rel = filepath.relative_to(_REPO_ROOT)
        except ValueError:
            rel = filepath

        for msg in errors:
            error_count += 1
            print(f"  ERROR: {rel}: {msg}")
        for msg in warnings:
            warning_count += 1
            if not quiet:
                print(f"  WARN:  {rel}: {msg}")

    for target in targets:
        if target.is_file():
            _process(target)
        elif target.is_dir():
            for f in sorted(target.rglob("*.md")):
                _process(f)
        else:
            print(f"WARNING: path not found: {target}", file=sys.stderr)

    # Summary
    status = "PASS" if error_count == 0 and (not strict or warning_count == 0) else "FAIL"
    print(
        f"\n[{status}] Checked {file_count} files. "
        f"{error_count} errors, {warning_count} warnings."
    )
    if error_count > 0:
        print(
            "  Errors indicate garbled code blocks — restore from git history or "
            "re-run the content pipeline with the fixed evidence/writer.py.",
            file=sys.stderr,
        )
    if warning_count > 0 and not quiet:
        print(
            "  Warnings indicate non-literal YAML scalars — run: "
            "python scripts/pipeline/commands/migration/normalize_yaml_style.py",
            file=sys.stderr,
        )

    if error_count > 0:
        return 1
    if strict and warning_count > 0:
        return 1
    return 0


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=textwrap.dedent(__doc__ or ""),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "paths",
        nargs="*",
        help="Files or directories to check. Defaults to content/products/.",
    )
    p.add_argument(
        "--strict",
        action="store_true",
        help="Also exit 1 on non-literal multi-line scalar warnings.",
    )
    p.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-file warning output; only show summary.",
    )
    return p


def main(argv=None) -> int:
    args = _build_parser().parse_args(argv)

    targets: list[Path] = []
    if args.paths:
        for p in args.paths:
            path = Path(p)
            if not path.is_absolute():
                path = Path.cwd() / path
            targets.append(path)
    else:
        targets = [_PRODUCTS_DIR]

    return validate_paths(targets, strict=args.strict, quiet=args.quiet)


if __name__ == "__main__":
    sys.exit(main())
