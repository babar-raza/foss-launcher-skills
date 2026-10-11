"""Tests for the shared duplicate-row detection library (TC-DUPIDX-01, ST-059).

Covers:
- parse_grouped_md_tables() — module/subheader/stop-marker heading-level parsing
- find_duplicate_rows() — exact-duplicate class-name detection within one module's table
"""
import re

from scripts.pipeline.lib.api_table_dupes import find_duplicate_rows, parse_grouped_md_tables


# ---------------------------------------------------------------------------
# parse_grouped_md_tables()
# ---------------------------------------------------------------------------

_MODULE_RE = re.compile(r"^##\s+(.+?)\s*$")
_SUBHEADER_RE = re.compile(r"^###\s+(.+?)\s*$")
_STOP_RE = re.compile(r"^##\s*See Also\s*$", re.IGNORECASE)


def test_parse_groups_rows_under_module_header():
    body = (
        "## Core API\n\n"
        "| Class | Description |\n"
        "|---|---|\n"
        "| `Alpha` | First class. |\n"
        "| `Beta` | Second class. |\n"
    )
    tables = parse_grouped_md_tables(body, module_header_re=_MODULE_RE)
    assert tables == {"Core API": ["Alpha", "Beta"]}


def test_parse_subheader_folds_into_current_module_not_a_new_bucket():
    body = (
        "## Core API\n\n"
        "| `Alpha` | First class. |\n\n"
        "### Enumerations\n\n"
        "| Enumeration | Description |\n"
        "|---|---|\n"
        "| `Severity` | An enum. |\n"
    )
    tables = parse_grouped_md_tables(
        body, module_header_re=_MODULE_RE, subheader_re=_SUBHEADER_RE,
    )
    assert tables == {"Core API": ["Alpha", "Severity"]}
    assert "Enumerations" not in tables


def test_parse_stops_at_stop_marker():
    body = (
        "## Core API\n\n"
        "| `Alpha` | First class. |\n\n"
        "## See Also\n\n"
        "- [Some external link](https://example.com)\n"
        "| `RogueRow` | Should never be parsed. |\n"
    )
    tables = parse_grouped_md_tables(
        body, module_header_re=_MODULE_RE, stop_re=_STOP_RE,
    )
    assert tables == {"Core API": ["Alpha"]}


def test_parse_rows_before_any_module_header_are_ignored():
    body = "| `Orphan` | No module header seen yet. |\n\n## Core API\n\n| `Alpha` | x |\n"
    tables = parse_grouped_md_tables(body, module_header_re=_MODULE_RE)
    assert tables == {"Core API": ["Alpha"]}


def test_parse_empty_module_with_no_rows_yields_empty_list():
    body = "## See Also\n\n- [link](https://example.com)\n"
    tables = parse_grouped_md_tables(body, module_header_re=_MODULE_RE)
    assert tables == {"See Also": []}


# ---------------------------------------------------------------------------
# find_duplicate_rows()
# ---------------------------------------------------------------------------

def test_find_duplicate_rows_clean_table_returns_empty():
    tables = {"Core API": ["Alpha", "Beta", "Gamma"]}
    assert find_duplicate_rows(tables) == []


def test_find_duplicate_rows_flags_exact_duplicate():
    # Mirrors the real cells/cpp regression: DiagnosticSeverity listed twice, back-to-back.
    tables = {"Enumerations": ["DateSystem", "DiagnosticSeverity", "DiagnosticSeverity", "FillPattern"]}
    findings = find_duplicate_rows(tables)
    assert findings == [{
        "module": "Enumerations", "class_name": "DiagnosticSeverity", "count": 2,
        "reason": "'DiagnosticSeverity' appears 2 times in the 'Enumerations' table -- an "
                  "exact duplicate row, not two different classes",
    }]


def test_find_duplicate_rows_counts_triple_duplicate():
    tables = {"Core API": ["Alpha", "Alpha", "Alpha"]}
    findings = find_duplicate_rows(tables)
    assert findings == [{
        "module": "Core API", "class_name": "Alpha", "count": 3,
        "reason": "'Alpha' appears 3 times in the 'Core API' table -- an "
                  "exact duplicate row, not two different classes",
    }]


def test_find_duplicate_rows_same_name_in_different_modules_not_flagged():
    tables = {"Module A": ["Shared"], "Module B": ["Shared"]}
    assert find_duplicate_rows(tables) == []


def test_find_duplicate_rows_noop_on_empty_tables():
    assert find_duplicate_rows({}) == []
    assert find_duplicate_rows({"Core API": []}) == []
