"""Cross-page consistency checker — detects contradictions across subdomains."""

from __future__ import annotations

import re
from collections import defaultdict

from ..models import Finding, Page


def _extract_feature_topic(page: Page) -> str:
    """Derive a feature topic key from page path and headings."""
    # Use the page slug as the primary topic key
    stem = page.filepath.stem.lower().replace("_index", "index")
    return f"{page.family}/{stem}"


def _extract_format_claims(page: Page) -> dict[str, set[str]]:
    """Extract format claims: {format_ext: set of claimed directions}."""
    claims: dict[str, set[str]] = defaultdict(set)
    _FMT_RE = re.compile(
        r"(?:supports?|import|export|convert|load|save|read|write)\w*\s+"
        r"(?:to\s+|from\s+)?(\w{2,6})\s+(?:format|file)",
        re.IGNORECASE,
    )
    _DIR_RE = re.compile(r"\b(import|export|load|save|read|write|convert)\b", re.IGNORECASE)

    for _, line in page.prose_lines:
        for m in _FMT_RE.finditer(line):
            fmt = m.group(1).lower()
            dirs = _DIR_RE.findall(line)
            for d in dirs:
                dl = d.lower()
                if dl in ("import", "load", "read"):
                    claims[fmt].add("import")
                elif dl in ("export", "save", "write"):
                    claims[fmt].add("export")
                elif dl == "convert":
                    claims[fmt].add("both")
    return dict(claims)


def check_consistency(pages: list[Page]) -> list[Finding]:
    """Check for contradictions and inconsistencies across pages.

    Groups pages by feature topic and compares format claims.
    """
    findings: list[Finding] = []

    # Group pages by family (only compare within same family)
    family_pages: dict[str, list[Page]] = defaultdict(list)
    for page in pages:
        if page.family:
            family_pages[page.family].append(page)

    for family, family_page_list in family_pages.items():
        # Check format claim consistency across pages within the same family
        format_claims: dict[str, list[tuple[Page, set[str]]]] = defaultdict(list)
        for page in family_page_list:
            page_formats = _extract_format_claims(page)
            for fmt, dirs in page_formats.items():
                format_claims[fmt].append((page, dirs))

        for fmt, claim_list in format_claims.items():
            if len(claim_list) < 2:
                continue
            # Check if pages disagree on direction
            all_dirs = set()
            for _, dirs in claim_list:
                all_dirs.update(dirs)
            if "import" in all_dirs and "export" in all_dirs:
                # Could be legitimate (both directions) — only flag if
                # some pages say import-only while others say export-only
                import_only_pages = [p for p, d in claim_list
                                     if "import" in d and "export" not in d and "both" not in d]
                export_only_pages = [p for p, d in claim_list
                                     if "export" in d and "import" not in d and "both" not in d]
                if import_only_pages and export_only_pages:
                    for page in import_only_pages + export_only_pages:
                        findings.append(Finding(
                            level="WARN",
                            category="XP",
                            filepath=str(page.filepath),
                            line_no=1,
                            message=f"Cross-page inconsistency: {fmt.upper()} direction differs across pages",
                            suggestion="Check if format supports import, export, or both",
                            evaluator="cross_page_consistency",
                        ))

    return findings
