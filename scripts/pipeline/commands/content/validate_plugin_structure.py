#!/usr/bin/env python3
"""validate_plugin_structure.py — Structural gate for layout: plugin product pages.

Checks every product page with ``layout: plugin`` for structural correctness
against the Hugo ``plugin.html`` template requirements.  The template reads
all content sections via ``.Params.*`` which is populated exclusively from
YAML frontmatter — content placed in the page body is invisible to Hugo.

Checks
------
1. **BODY_LEAK** (FATAL): ``overview:``, ``content:``, ``single:``, or
   ``faq:`` patterns found in the page body (after the closing ``---``
   delimiter) instead of inside frontmatter.  This is the primary defect
   this validator was created to catch.

2. **MISSING_KEY** (FATAL): A required frontmatter key (consumed by
   ``plugin.html``) is absent.

3. **MISSING_ENABLE** (ERROR): A section is present but missing its
   ``enable: true`` flag, so the template will silently skip it.

4. **EMPTY_SECTION** (WARN): A required section has no content or blocks.

Usage
-----
    # Check all plugin product pages:
    python scripts/pipeline/validate_plugin_structure.py

    # Check specific files:
    python scripts/pipeline/validate_plugin_structure.py --files path/to/file.md

    # Strict mode — also exit 1 on WARN:
    python scripts/pipeline/validate_plugin_structure.py --strict

Exit codes
----------
    0 — All checks passed
    1 — One or more FATAL or ERROR findings
    2 — Internal error
"""
from __future__ import annotations

import argparse
import re
import sys
import textwrap
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
_PRODUCTS_DIR = _REPO_ROOT / "content" / "products.aspose.org"

_PIPELINE_ROOT = Path(__file__).resolve().parent.parent.parent  # commands/content/ -> commands/ -> pipeline/
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

from core.markdown import extract_frontmatter_body, _FRONTMATTER_READER_RE  # noqa: E402

# ---------------------------------------------------------------------------
# Body-leak detection patterns — these are YAML top-level keys that belong
# in frontmatter, not in the page body.
# ---------------------------------------------------------------------------
_BODY_LEAK_PATTERNS = re.compile(
    r"^(overview|content|single|faq|supportandlearning|more_formats|back_to_top):",
    re.MULTILINE,
)

# ---------------------------------------------------------------------------
# Required frontmatter keys for layout: plugin pages.
# Derived from themes/products/layouts/_default/plugin.html template analysis.
# ---------------------------------------------------------------------------
_REQUIRED_TOP_KEYS = [
    "layout",
    "family_name",
    "plugin_description",
    "plugin_platform",
    "head_title",
    "head_description",
    "title",
    "description",
    "github_url",
]

# Core structural sections — FATAL if missing (content won't render)
_REQUIRED_SECTIONS_WITH_ENABLE = [
    "submenu",
    "overview",
    "content",
    "single",
]

# Display-control sections — ERROR if missing on English pages (S-61 post-conditions
# require these); WARN for locale translations which legitimately omit them.
_OPTIONAL_SECTIONS_WITH_ENABLE = [
    "supportandlearning",
    "more_formats",
    "back_to_top",
]

_SECTIONS_WITH_CONTENT = {
    "overview": ["title", "content"],
    "content": ["block"],
    "single": ["block"],
}


# ---------------------------------------------------------------------------
# Finding dataclass
# ---------------------------------------------------------------------------
class Finding:
    __slots__ = ("severity", "check_id", "message")

    def __init__(self, severity: str, check_id: str, message: str):
        self.severity = severity
        self.check_id = check_id
        self.message = message

    def __str__(self) -> str:
        return f"  {self.severity}: [{self.check_id}] {self.message}"


# ---------------------------------------------------------------------------
# Core check logic
# ---------------------------------------------------------------------------


def _is_english_page(filepath: Path) -> bool:
    """Return True if the page is under the English content directory."""
    parts = filepath.parts
    # English pages live under content/products.aspose.org/en/
    for i, part in enumerate(parts):
        if part == "products.aspose.org" and i + 1 < len(parts):
            return parts[i + 1] == "en"
    return False


def _extract_body(text: str) -> str:
    """Return the page body (everything after the closing --- fence)."""
    m = _FRONTMATTER_READER_RE.match(text)
    if not m:
        return text
    # Body starts after the match
    return text[m.end():]


def check_file(filepath: Path) -> list[Finding]:
    """Run all structural checks on a single file. Returns list of findings."""
    findings: list[Finding] = []

    try:
        text = filepath.read_text(encoding="utf-8")
    except OSError as e:
        findings.append(Finding("FATAL", "READ_ERROR", str(e)))
        return findings

    # Parse frontmatter
    fm_raw = extract_frontmatter_body(text)
    if fm_raw is None:
        findings.append(Finding("FATAL", "NO_FRONTMATTER", "file has no YAML frontmatter"))
        return findings

    try:
        fm = yaml.safe_load(fm_raw) or {}
    except yaml.YAMLError as e:
        findings.append(Finding("FATAL", "BAD_YAML", f"YAML parse error: {e}"))
        return findings

    # Only check layout: plugin pages
    if fm.get("layout") != "plugin":
        return findings

    # --- Check 1: Body content leak ---
    body = _extract_body(text)
    body_stripped = body.strip()
    if body_stripped:
        leaked = _BODY_LEAK_PATTERNS.findall(body_stripped)
        if leaked:
            findings.append(Finding(
                "FATAL",
                "BODY_LEAK",
                f"content sections found in page body instead of frontmatter: "
                f"{', '.join(leaked)}. Hugo reads .Params.* only from frontmatter.",
            ))
        elif body_stripped:
            findings.append(Finding(
                "WARN",
                "NONEMPTY_BODY",
                "page body is not empty (plugin layout expects all content in frontmatter)",
            ))

    # --- Check 2: Required top-level keys ---
    for key in _REQUIRED_TOP_KEYS:
        if key not in fm or fm[key] is None or (isinstance(fm[key], str) and not fm[key].strip()):
            findings.append(Finding("FATAL", "MISSING_KEY", f"required key '{key}' is missing or empty"))

    # --- Check 3: Required sections with enable: true ---
    for section_name in _REQUIRED_SECTIONS_WITH_ENABLE:
        section = fm.get(section_name)
        if section is None:
            findings.append(Finding("FATAL", "MISSING_KEY", f"required section '{section_name}' is missing"))
            continue
        if not isinstance(section, dict):
            findings.append(Finding("FATAL", "MISSING_KEY", f"'{section_name}' must be a mapping, got {type(section).__name__}"))
            continue
        if not section.get("enable"):
            findings.append(Finding("ERROR", "MISSING_ENABLE", f"'{section_name}.enable' is not true"))

    # --- Check 3b: Display-control sections (ERROR for English, WARN for locale) ---
    is_english = _is_english_page(filepath)
    display_sev = "ERROR" if is_english else "WARN"
    for section_name in _OPTIONAL_SECTIONS_WITH_ENABLE:
        section = fm.get(section_name)
        if section is None:
            findings.append(Finding(display_sev, "MISSING_DISPLAY", f"display section '{section_name}' is missing"))
        elif isinstance(section, dict) and not section.get("enable"):
            findings.append(Finding(display_sev, "MISSING_ENABLE", f"'{section_name}.enable' is not true"))

    # --- Check 4: Sections with required sub-keys ---
    for section_name, sub_keys in _SECTIONS_WITH_CONTENT.items():
        section = fm.get(section_name)
        if not isinstance(section, dict):
            continue  # Already flagged above
        for sub_key in sub_keys:
            val = section.get(sub_key)
            if val is None:
                findings.append(Finding("WARN", "EMPTY_SECTION", f"'{section_name}.{sub_key}' is missing"))
            elif isinstance(val, list) and len(val) == 0:
                findings.append(Finding("WARN", "EMPTY_SECTION", f"'{section_name}.{sub_key}' is an empty list"))
            elif isinstance(val, str) and not val.strip():
                findings.append(Finding("WARN", "EMPTY_SECTION", f"'{section_name}.{sub_key}' is empty"))

    # --- Check 5: Provenance and evidence (required for English, warn for locale) ---
    is_english = _is_english_page(filepath)
    sev = "FATAL" if is_english else "WARN"
    if "provenance" not in fm:
        findings.append(Finding(sev, "MISSING_KEY", "required key 'provenance' is missing"))
    if "evidence" not in fm:
        findings.append(Finding(sev, "MISSING_KEY", "required key 'evidence' is missing"))

    return findings


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _collect_plugin_pages(targets: list[Path]) -> list[Path]:
    """Collect all .md files from targets, filtering to layout: plugin pages."""
    files: list[Path] = []
    for target in targets:
        if target.is_file():
            files.append(target)
        elif target.is_dir():
            files.extend(sorted(target.rglob("_index.md")))
    return files


def validate_paths(targets: list[Path], strict: bool = False) -> int:
    """Validate files. Returns exit code."""
    files = _collect_plugin_pages(targets)

    fatal_count = 0
    error_count = 0
    warn_count = 0
    checked = 0

    for filepath in files:
        findings = check_file(filepath)
        if not findings:
            checked += 1
            continue

        # Only count if this was actually a plugin page (findings exist)
        checked += 1
        try:
            rel = filepath.relative_to(_REPO_ROOT)
        except ValueError:
            rel = filepath

        for f in findings:
            if f.severity == "FATAL":
                fatal_count += 1
            elif f.severity == "ERROR":
                error_count += 1
            else:
                warn_count += 1
            print(f"  {rel}: {f}")

    # Summary
    has_failures = fatal_count > 0 or error_count > 0 or (strict and warn_count > 0)
    status = "FAIL" if has_failures else "PASS"
    print(
        f"\n[{status}] Checked {checked} plugin pages. "
        f"{fatal_count} fatal, {error_count} errors, {warn_count} warnings."
    )

    return 1 if has_failures else 0


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=textwrap.dedent(__doc__ or ""),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--files",
        nargs="+",
        help="Specific files to check. Defaults to all product pages.",
    )
    p.add_argument(
        "--strict",
        action="store_true",
        help="Also exit 1 on WARN-level findings.",
    )
    return p


def main(argv=None) -> int:
    args = _build_parser().parse_args(argv)

    targets: list[Path] = []
    if args.files:
        for p in args.files:
            path = Path(p)
            if not path.is_absolute():
                path = Path.cwd() / path
            targets.append(path)
    else:
        targets = [_PRODUCTS_DIR]

    return validate_paths(targets, strict=args.strict)


if __name__ == "__main__":
    sys.exit(main())
