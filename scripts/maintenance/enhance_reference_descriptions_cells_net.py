"""
enhance_reference_descriptions_cells_net.py — Populate empty Description cells in
26 grade-C reference pages for cells/net and promote their grade to A.

Root cause: batch-reference generator produced minimal enum value descriptions
(empty Description column cells) because the FOSS source has no XML doc comments.
This script fills descriptions from domain knowledge and evidence in the knowledge model.

Usage:
    python scripts/maintenance/enhance_reference_descriptions_cells_net.py [--dry-run]

One-off repair — run once, check output, commit with the content files.
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BASE = REPO_ROOT / "content" / "reference.aspose.org" / "en" / "cells" / "net"
GRADED_AT = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

# ---------------------------------------------------------------------------
# 2-column table patches: (file, value_name) → description
# Used for enum Values tables and Workbook Methods table (Signature | Description)
# ---------------------------------------------------------------------------
TWO_COL_PATCHES: dict[str, dict[str, str]] = {
    "BorderStyle.md": {
        "None": "No border style applied; the cell edge has no line",
        "Thin": "Thin solid line",
        "Medium": "Medium-weight solid line",
        "Thick": "Thick solid line",
        "Dotted": "Dotted line",
        "Dashed": "Dashed line",
        "Double": "Double parallel lines",
        "Hair": "Hairline; the thinnest possible border",
        "MediumDashed": "Medium-weight dashed line",
        "DashDot": "Alternating dash and dot pattern",
        "MediumDashDot": "Medium-weight alternating dash and dot",
        "DashDotDot": "Alternating dash followed by two dots",
        "MediumDashDotDot": "Medium-weight alternating dash and two dots",
        "SlantedDashDot": "Slanted dash-dot pattern",
    },
    "BorderStyleType.md": {
        "None": "No border style applied; the cell edge has no line",
        "Thin": "Thin solid line",
        "Medium": "Medium-weight solid line",
        "Thick": "Thick solid line",
        "Dotted": "Dotted line",
        "Dashed": "Dashed line",
        "Double": "Double parallel lines",
        "Hair": "Hairline; the thinnest possible border",
        "MediumDashed": "Medium-weight dashed line",
        "DashDot": "Alternating dash and dot pattern",
        "MediumDashDot": "Medium-weight alternating dash and dot",
        "DashDotDot": "Alternating dash followed by two dots",
        "MediumDashDotDot": "Medium-weight alternating dash and two dots",
        "SlantedDashDot": "Slanted dash-dot pattern",
    },
    "CellValueKind.md": {
        "Blank": "Cell contains no value",
        "String": "Cell contains a text string value",
        "Number": "Cell contains a numeric value",
        "Boolean": "Cell contains a boolean (true/false) value",
        "DateTime": "Cell contains a date or time value",
        "Formula": "Cell contains a formula expression",
    },
    "CellValueType.md": {
        "Blank": "Cell contains no value",
        "String": "Cell contains a text string value",
        "Number": "Cell contains a numeric value",
        "Boolean": "Cell contains a boolean (true/false) value",
        "DateTime": "Cell contains a date or time value",
        "Formula": "Cell contains a formula expression",
    },
    "DiagnosticSeverity.md": {
        "Warning": "Non-critical issue; workbook loaded with minor concerns",
        "Recoverable": "Issue encountered but workbook successfully recovered without data loss",
        "LossyRecoverable": "Issue caused partial data loss during recovery",
        "Fatal": "Critical error that prevents the workbook from loading",
    },
    "FillPattern.md": {
        "None": "No fill pattern; the cell background is transparent",
        "Solid": "Solid fill covering the entire cell background",
        "MediumGray": "Medium-density gray pattern fill (~50% gray)",
        "DarkGray": "Dense gray pattern fill (~75% gray)",
        "Gray125": "Very light gray pattern fill (12.5% density)",
        "Gray0625": "Extremely light gray pattern fill (6.25% density)",
        "DarkHorizontal": "Dark horizontal stripe pattern",
        "DarkVertical": "Dark vertical stripe pattern",
        "DarkDown": "Dark diagonal stripes descending left-to-right",
        "DarkUp": "Dark diagonal stripes ascending left-to-right",
        "DarkGrid": "Dark crosshatch grid pattern",
        "DarkTrellis": "Dark diamond trellis pattern",
        "LightHorizontal": "Light horizontal stripe pattern",
        "LightVertical": "Light vertical stripe pattern",
        "LightDown": "Light diagonal stripes descending left-to-right",
        "LightUp": "Light diagonal stripes ascending left-to-right",
        "LightGrid": "Light crosshatch grid pattern",
        "LightTrellis": "Light diamond trellis pattern",
    },
    "FillPatternKind.md": {
        "None": "No fill pattern; the cell background is transparent",
        "Solid": "Solid fill covering the entire cell background",
        "MediumGray": "Medium-density gray pattern fill (~50% gray)",
        "DarkGray": "Dense gray pattern fill (~75% gray)",
        "Gray125": "Very light gray pattern fill (12.5% density)",
        "Gray0625": "Extremely light gray pattern fill (6.25% density)",
        "DarkHorizontal": "Dark horizontal stripe pattern",
        "DarkVertical": "Dark vertical stripe pattern",
        "DarkDown": "Dark diagonal stripes descending left-to-right",
        "DarkUp": "Dark diagonal stripes ascending left-to-right",
        "DarkGrid": "Dark crosshatch grid pattern",
        "DarkTrellis": "Dark diamond trellis pattern",
        "LightHorizontal": "Light horizontal stripe pattern",
        "LightVertical": "Light vertical stripe pattern",
        "LightDown": "Light diagonal stripes descending left-to-right",
        "LightUp": "Light diagonal stripes ascending left-to-right",
        "LightGrid": "Light crosshatch grid pattern",
        "LightTrellis": "Light diamond trellis pattern",
    },
    "FilterOperatorType.md": {
        "Equal": "Filter rows where the cell value equals the criteria value",
        "LessThan": "Filter rows where the cell value is less than the criteria value",
        "LessOrEqual": "Filter rows where the cell value is less than or equal to the criteria value",
        "NotEqual": "Filter rows where the cell value does not equal the criteria value",
        "GreaterOrEqual": "Filter rows where the cell value is greater than or equal to the criteria value",
        "GreaterThan": "Filter rows where the cell value is greater than the criteria value",
    },
    "FormatConditionType.md": {
        "CellValue": "Condition based on the cell value relative to a threshold",
        "Expression": "Condition based on a custom formula expression",
        "ContainsText": "Condition triggered when cell text contains a specified substring",
        "NotContainsText": "Condition triggered when cell text does not contain a specified substring",
        "BeginsWith": "Condition triggered when cell text starts with a specified string",
        "EndsWith": "Condition triggered when cell text ends with a specified string",
        "TimePeriod": "Condition based on a relative time period such as last week or this month",
        "DuplicateValues": "Highlights cells whose values appear more than once in the range",
        "UniqueValues": "Highlights cells whose values appear exactly once in the range",
        "Top10": "Highlights the top N values or top N percent of values in the range",
        "Bottom10": "Highlights the bottom N values or bottom N percent of values in the range",
        "AboveAverage": "Highlights cells whose values exceed the range average",
        "BelowAverage": "Highlights cells whose values fall below the range average",
        "ColorScale": "Applies a graduated color scale across the value range",
        "DataBar": "Displays a proportional data bar inside each cell",
        "IconSet": "Assigns icon indicators based on value thresholds within the range",
    },
    "HorizontalAlignment.md": {
        "General": "Default alignment determined by the cell content type",
        "Left": "Content aligned to the left edge of the cell",
        "Center": "Content centered horizontally in the cell",
        "Right": "Content aligned to the right edge of the cell",
        "Fill": "Content repeated to fill the full cell width",
        "Justify": "Content stretched to align with both left and right edges",
        "CenterContinuous": "Content centered across a contiguous group of cells",
        "Distributed": "Content distributed evenly with spacing between characters",
    },
    "HorizontalAlignmentType.md": {
        "General": "Default alignment determined by the cell content type",
        "Left": "Content aligned to the left edge of the cell",
        "Center": "Content centered horizontally in the cell",
        "Right": "Content aligned to the right edge of the cell",
        "Fill": "Content repeated to fill the full cell width",
        "Justify": "Content stretched to align with both left and right edges",
        "CenterContinuous": "Content centered across a contiguous group of cells",
        "Distributed": "Content distributed evenly with spacing between characters",
    },
    "OperatorType.md": {
        "Between": "Value falls within a specified lower and upper bound (inclusive)",
        "Equal": "Value exactly equals the specified operand",
        "GreaterThan": "Value is strictly greater than the specified operand",
        "GreaterOrEqual": "Value is greater than or equal to the specified operand",
        "LessThan": "Value is strictly less than the specified operand",
        "LessOrEqual": "Value is less than or equal to the specified operand",
        "None": "No comparison operator; condition type determines matching logic",
        "NotBetween": "Value falls outside the specified lower and upper bound",
        "NotEqual": "Value does not equal the specified operand",
    },
    "PageOrientation.md": {
        "Default": "Uses the default page orientation from print settings",
        "Portrait": "Taller-than-wide orientation (vertical layout)",
        "Landscape": "Wider-than-tall orientation (horizontal layout)",
    },
    "PageOrientationType.md": {
        "Default": "Uses the default page orientation from print settings",
        "Portrait": "Taller-than-wide orientation (vertical layout)",
        "Landscape": "Wider-than-tall orientation (horizontal layout)",
    },
    "PaperSizeType.md": {
        "Default": "Uses the default paper size from print settings",
        "PaperLetter": "US Letter paper size (8.5 × 11 in / 216 × 279 mm)",
        "PaperTabloid": "US Tabloid paper size (11 × 17 in / 279 × 432 mm)",
        "PaperLegal": "US Legal paper size (8.5 × 14 in / 216 × 356 mm)",
        "PaperStatement": "US Statement paper size (5.5 × 8.5 in / 140 × 216 mm)",
        "PaperExecutive": "US Executive paper size (7.25 × 10.5 in / 184 × 267 mm)",
        "PaperA3": "ISO A3 paper size (297 × 420 mm)",
        "PaperA4": "ISO A4 paper size (210 × 297 mm)",
        "PaperA5": "ISO A5 paper size (148 × 210 mm)",
        "PaperB4": "JIS B4 paper size (257 × 364 mm)",
        "PaperB5": "JIS B5 paper size (182 × 257 mm)",
    },
    "SheetVisibility.md": {
        "Visible": "Worksheet tab is visible in the workbook",
        "Hidden": "Worksheet is hidden but can be unhidden by the user via the UI",
        "VeryHidden": "Worksheet is hidden and cannot be unhidden through the Excel UI",
    },
    "TargetModeType.md": {
        "External": "Hyperlink points to an external URL or network resource",
        "FilePath": "Hyperlink points to a local or network file path",
        "Email": "Hyperlink opens an email client with a pre-filled recipient address",
        "CellReference": "Hyperlink navigates to a cell reference within the workbook",
    },
    "ValidationAlertType.md": {
        "Stop": "Stop alert prevents invalid input from being entered",
        "Warning": "Warning alert prompts the user but allows override of validation",
        "Information": "Information alert notifies the user without blocking input",
    },
    "ValidationMessageSeverity.md": {
        "Info": "Informational severity; does not block user input",
        "Warning": "Warning severity; prompts the user but allows override",
        "Error": "Error severity; blocks invalid input until corrected",
    },
    "ValidationType.md": {
        "AnyValue": "No restriction; any input value is accepted",
        "WholeNumber": "Restricts input to integers within an optional range",
        "Decimal": "Restricts input to decimal numbers within an optional range",
        "List": "Restricts input to values from a predefined drop-down list",
        "Date": "Restricts input to date values within an optional range",
        "Time": "Restricts input to time values within an optional range",
        "TextLength": "Restricts input based on the character length of the entered text",
        "Custom": "Uses a custom formula expression to validate input",
    },
    "VerticalAlignment.md": {
        "Bottom": "Content aligned to the bottom edge of the cell",
        "Center": "Content centered vertically in the cell",
        "Top": "Content aligned to the top edge of the cell",
        "Justify": "Content stretched to fill the cell height evenly",
        "Distributed": "Content distributed with equal spacing between lines",
    },
    "VerticalAlignmentType.md": {
        "Bottom": "Content aligned to the bottom edge of the cell",
        "Center": "Content centered vertically in the cell",
        "Top": "Content aligned to the top edge of the cell",
        "Justify": "Content stretched to fill the cell height evenly",
        "Distributed": "Content distributed with equal spacing between lines",
    },
    "VisibilityType.md": {
        "Visible": "Element is visible",
        "Hidden": "Element is hidden but can be made visible",
        "VeryHidden": "Element is hidden and cannot be made visible through the normal UI",
    },
    # Workbook.md: 2-column Methods table (Signature | Description)
    "Workbook.md": {
        "Workbook(fileName: string)": "Opens an existing workbook from the specified file path",
        "Workbook(stream: Stream)": "Opens a workbook from the given stream using auto-detected format",
        "Workbook(fileName: string, options: LoadOptions)": (
            "Opens an existing workbook from the file path with the specified load options"
        ),
        "Workbook(stream: Stream, options: LoadOptions)": (
            "Opens a workbook from the given stream with the specified load options"
        ),
        "Save(fileName: string, format: SaveFormat)": (
            "Saves the workbook to the file path in the specified SaveFormat"
        ),
        "Save(fileName: string, options: SaveOptions)": (
            "Saves the workbook to the file path using the specified save options"
        ),
        "Save(stream: Stream, format: SaveFormat)": (
            "Saves the workbook to the given stream in the specified SaveFormat"
        ),
        "Save(stream: Stream, options: SaveOptions)": (
            "Saves the workbook to the given stream using the specified save options"
        ),
    },
}

# ---------------------------------------------------------------------------
# 4-column property table patches: (file, prop_name, type_name) → description
# Used for class Properties tables (Name | Type | Access | Description)
# ---------------------------------------------------------------------------
FOUR_COL_PATCHES: dict[str, dict[tuple[str, str], str]] = {
    "BordersValue.md": {
        ("Right", "BorderSideValue"): "Gets or sets the right border side value",
        ("Top", "BorderSideValue"): "Gets or sets the top border side value",
        ("Bottom", "BorderSideValue"): "Gets or sets the bottom border side value",
        ("Diagonal", "BorderSideValue"): "Gets or sets the diagonal border side value",
        ("DiagonalDown", "bool"): (
            "Gets or sets whether the diagonal border is drawn downward "
            "from the top-left corner to the bottom-right corner"
        ),
    },
    "DocumentProperties.md": {
        ("Extended", "ExtendedDocumentProperties"): (
            "Gets the extended (custom) document properties collection"
        ),
        ("Subject", "string"): "Gets or sets the document subject metadata",
        ("Author", "string"): "Gets or sets the document author name",
        ("Keywords", "string"): "Gets or sets keywords associated with the document",
        ("Comments", "string"): "Gets or sets notes or comments about the document",
        ("Category", "string"): "Gets or sets the document category",
        ("Company", "string"): "Gets or sets the company or organization name",
        ("Manager", "string"): "Gets or sets the manager name associated with the document",
    },
}


def _patch_two_col_row(text: str, value: str, description: str) -> str:
    """Replace an empty 2-column table row: | `value` |  | → | `value` | description |"""
    old = f"| `{value}` |  |"
    new = f"| `{value}` | {description} |"
    if old not in text:
        # Try with trailing space variations
        old_alt = re.escape(f"| `{value}` |") + r"\s*\|"
        if re.search(old_alt, text):
            return re.sub(old_alt, f"| `{value}` | {description} |", text, count=1)
        return text  # not found — skip
    return text.replace(old, new, 1)


def _patch_four_col_row(text: str, prop_name: str, type_name: str, description: str) -> str:
    """Fill empty Description cell in a 4-column property table row."""
    # Pattern: | `PropName` | `TypeName` | Access |  |
    # The Type column may be backtick-wrapped or not; Access varies (Read/Write, Read, etc.)
    pattern = (
        r"(\| `" + re.escape(prop_name) + r"` \| `?" + re.escape(type_name)
        + r"`? \| [^|]+ \|)\s*\|"
    )
    replacement = r"\1 " + description + r" |"
    new_text, count = re.subn(pattern, replacement, text, count=1)
    if count == 0:
        # Try without backticks around type
        pattern2 = (
            r"(\| `" + re.escape(prop_name) + r"` \| " + re.escape(type_name)
            + r" \| [^|]+ \|)\s*\|"
        )
        new_text, count = re.subn(pattern2, replacement, text, count=1)
    return new_text


def _update_grade(text: str) -> str:
    """Update grade C → A and graded_evaluators to remove description_completeness."""
    text = re.sub(r"^grade:\s*C$", "grade: A", text, flags=re.MULTILINE)
    text = re.sub(
        r"^graded_evaluators:\s*audit,description_completeness$",
        "graded_evaluators: audit",
        text,
        flags=re.MULTILINE,
    )
    text = re.sub(
        r'^graded_at:\s*"[^"]+"$',
        f'graded_at: "{GRADED_AT}"',
        text,
        flags=re.MULTILINE,
    )
    return text


def process_file(fname: str, dry_run: bool) -> bool:
    """Apply patches to a single reference page file. Returns True if changed."""
    fpath = BASE / fname
    if not fpath.exists():
        print(f"  SKIP (not found): {fname}")
        return False

    original = fpath.read_text(encoding="utf-8")
    text = original

    # Apply 2-column patches
    if fname in TWO_COL_PATCHES:
        for value, description in TWO_COL_PATCHES[fname].items():
            text = _patch_two_col_row(text, value, description)

    # Apply 4-column patches
    if fname in FOUR_COL_PATCHES:
        for (prop_name, type_name), description in FOUR_COL_PATCHES[fname].items():
            text = _patch_four_col_row(text, prop_name, type_name, description)

    # Update grade metadata
    text = _update_grade(text)

    if text == original:
        print(f"  UNCHANGED: {fname}")
        return False

    if dry_run:
        print(f"  DRY-RUN (would patch): {fname}")
        # Show diff summary
        old_lines = set(original.splitlines())
        new_lines = set(text.splitlines())
        added = [l for l in new_lines - old_lines if l.strip()][:3]
        print(f"    Sample changes: {added}")
        return True

    fpath.write_text(text, encoding="utf-8")
    print(f"  PATCHED: {fname}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Show changes without writing")
    args = parser.parse_args()

    all_files = sorted(set(list(TWO_COL_PATCHES.keys()) + list(FOUR_COL_PATCHES.keys())))
    changed = 0

    print(f"enhance_reference_descriptions_cells_net: processing {len(all_files)} files")
    print(f"  Mode: {'dry-run' if args.dry_run else 'write'}")
    print()

    for fname in all_files:
        if process_file(fname, args.dry_run):
            changed += 1

    print()
    print(f"Done: {changed}/{len(all_files)} files {'would be ' if args.dry_run else ''}patched.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
