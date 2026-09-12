"""Tests for the shared GFM pipe-table parser (H7, MT068-2026-09-11-IMAGING-NET-LAUNCH).

Extracted from content_eval/evaluators/description_completeness.py's own
_parse_tables — these tests pin the extracted behavior so a second consumer
(extraction/capability_tables.py) can rely on it without re-verifying parsing
correctness itself.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from lib.markdown_tables import parse_markdown_tables


class TestParseMarkdownTables:
    def test_simple_table(self):
        body = (
            "| Format | Detect |\n"
            "|--------|:------:|\n"
            "| PNG    | Yes    |\n"
            "| JPEG   | Yes    |\n"
        )
        tables = parse_markdown_tables(body)
        assert len(tables) == 1
        assert tables[0]["headers"] == ["Format", "Detect"]
        assert tables[0]["rows"] == [["PNG", "Yes"], ["JPEG", "Yes"]]
        assert tables[0]["header_line"] == 1

    def test_body_offset_shifts_header_line(self):
        body = "| A | B |\n|---|---|\n| 1 | 2 |\n"
        tables = parse_markdown_tables(body, body_offset=10)
        assert tables[0]["header_line"] == 11

    def test_escaped_pipe_does_not_split_cell(self):
        body = (
            "| Type | Description |\n"
            "|------|--------------|\n"
            "| str \\| None | optional string |\n"
        )
        tables = parse_markdown_tables(body)
        assert tables[0]["rows"] == [["str | None", "optional string"]]

    def test_no_table_returns_empty_list(self):
        assert parse_markdown_tables("Just some prose.\n\nNo tables here.") == []

    def test_alignment_colons_in_separator_accepted(self):
        body = "| A | B |\n|:---|---:|\n| x | y |\n"
        tables = parse_markdown_tables(body)
        assert len(tables) == 1
        assert tables[0]["rows"] == [["x", "y"]]

    def test_two_tables_in_one_body(self):
        body = (
            "| A | B |\n|---|---|\n| 1 | 2 |\n"
            "\nSome prose in between.\n\n"
            "| C | D |\n|---|---|\n| 3 | 4 |\n"
        )
        tables = parse_markdown_tables(body)
        assert len(tables) == 2
        assert tables[0]["headers"] == ["A", "B"]
        assert tables[1]["headers"] == ["C", "D"]

    def test_real_imaging_net_capability_matrix_shape(self):
        """Pins parsing of the exact real-world table this extraction was built for."""
        body = (
            "| Format | Detect | Width / Height | Bit depth | Frame count |\n"
            "|--------|:------:|:---------------:|:---------:|:-----------:|\n"
            "| PNG    | ✅ | ✅ | ✅ | ✅ |\n"
            "| WMF (placeable) | ✅ | ✅ (assumes 96 DPI) | — | — |\n"
        )
        tables = parse_markdown_tables(body)
        assert len(tables) == 1
        assert tables[0]["headers"] == ["Format", "Detect", "Width / Height", "Bit depth", "Frame count"]
        assert tables[0]["rows"][0] == ["PNG", "✅", "✅", "✅", "✅"]
        assert tables[0]["rows"][1] == ["WMF (placeable)", "✅", "✅ (assumes 96 DPI)", "—", "—"]
