"""Shared duplicate-row detection for module-grouped markdown API tables.

Extracted (TC-DUPIDX-01, 2026-08-12, ST-059) from
``readme_refresh_checks.check_api_reference_table_no_duplicate_rows()``. That check's own
proof case was ``cells/cpp``'s regenerated Enumerations table listing ``DiagnosticSeverity``
twice -- but the duplicate was live in ``content/reference.aspose.org/en/cells/cpp/_index.md``
itself, not merely in the composed README candidate the check was scoped to. This module gives
both consumers (readme-refresh's README-candidate check and
``check_reference_index_structure.py``'s reference-index Check 3) one shared implementation
instead of a second, divergent copy of the same counting logic.

Both consumers share a ``| `ClassName` | Description |`` row shape inside module-grouped
markdown, differing only in heading levels: reference.aspose.org's own ``_index.md`` pages use
``## Module`` / ``### Enumerations|Structs|Interfaces`` sub-groups; readme-refresh's composed
README candidates use ``### Module`` / ``#### ...`` sub-groups. ``parse_grouped_md_tables()``
takes the heading-level regexes as parameters so each caller supplies its own without
duplicating the walk logic.
"""

from __future__ import annotations

import re

_TABLE_ROW_RE = re.compile(r"^\|\s*`([^`]+)`\s*\|\s*(.*?)\s*\|\s*$")


def parse_grouped_md_tables(
    body_text: str,
    *,
    module_header_re: re.Pattern[str],
    subheader_re: re.Pattern[str] | None = None,
    stop_re: re.Pattern[str] | None = None,
) -> dict[str, list[str]]:
    """Parse a module-grouped markdown body into ``{module: [class_name, ...]}``.

    A ``module_header_re`` match starts a new bucket. A ``subheader_re`` match, when given,
    does NOT start a new bucket -- its rows fold into the current module, matching how both
    reference.aspose.org's Enumerations/Structs sub-tables and readme-refresh's
    Interfaces/Enumerations sub-headers group under their parent module. A ``stop_re`` match,
    when given, ends parsing entirely -- everything after it (e.g. a "See Also" section or the
    curated "Detailed Member Reference" bullets) is out of scope for this parse.
    """
    tables: dict[str, list[str]] = {}
    current_module: str | None = None
    for line in body_text.splitlines():
        if stop_re is not None and stop_re.match(line):
            break
        module_match = module_header_re.match(line)
        if module_match:
            current_module = module_match.group(1).strip()
            tables.setdefault(current_module, [])
            continue
        if subheader_re is not None and subheader_re.match(line):
            continue
        if current_module is None:
            continue
        row_match = _TABLE_ROW_RE.match(line)
        if row_match:
            tables[current_module].append(row_match.group(1))
    return tables


def find_duplicate_rows(tables: dict[str, list[str]]) -> list[dict]:
    """Find exact-duplicate class-name rows within each module's own table.

    A "row" is keyed purely on the backtick-quoted class name -- two rows with the same class
    name but different description text still count as duplicates; two rows with different
    class names but identical description text are never flagged (not a defect -- several
    small classes may legitimately share the same one-line summary).
    """
    findings: list[dict] = []
    for module, classes in tables.items():
        counts: dict[str, int] = {}
        for cls in classes:
            counts[cls] = counts.get(cls, 0) + 1
        for cls, count in counts.items():
            if count > 1:
                findings.append({
                    "module": module, "class_name": cls, "count": count,
                    "reason": f"'{cls}' appears {count} times in the '{module}' table -- an "
                              "exact duplicate row, not two different classes",
                })
    return findings
