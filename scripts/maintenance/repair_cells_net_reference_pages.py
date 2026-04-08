"""
repair_cells_net_reference_pages.py — Replace body content of 11 reference pages
in content/reference.aspose.org/en/cells/net/ while preserving existing frontmatter.

This is a one-off operator-run content repair. Run manually when the reference page
bodies need updating with corrected or improved API documentation. Do not call from
CI, hooks, or skills.

Usage:
    python scripts/maintenance/repair_cells_net_reference_pages.py [--dry-run]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BASE = REPO_ROOT / "content" / "reference.aspose.org" / "en" / "cells" / "net"

# Maps filename → replacement body (everything after closing --- of frontmatter).
NEW_BODIES: dict[str, str] = {

"AutoFilterModel.md": """\

## Overview

`AutoFilterModel` is a serialization model class that stores the configuration state of an
auto-filter: the worksheet range it covers, the per-column filter criteria, and the associated
sort state. Used for round-trip XLSX serialization of auto-filter settings.

## Properties

| Name | Type | Access | Description |
|------|------|--------|-------------|
| `Range` | `string` | Read/Write | The worksheet cell-range reference to which the auto-filter applies. |
| `FilterColumns` | `List<FilterColumnModel>` | Read | The collection of per-column filter configurations. |
| `SortState` | `AutoFilterSortStateModel` | Read | The sort state describing how filtered rows are ordered. |

## Methods

| Signature | Description |
|-----------|-------------|
| `AutoFilterModel()` | Initialises a new empty `AutoFilterModel` with default property values. |
| `Clear()` | Resets all filter criteria and sort state to their defaults. |
| `HasStoredState()` | Returns `true` if this model contains non-default state to serialise. |
""",

"AutoFilterSortStateModel.md": """\

## Overview

`AutoFilterSortStateModel` is a serialization model that captures the sort configuration for
an auto-filtered range, including sort conditions, case sensitivity, and sort method.

## Properties

| Name | Type | Access | Description |
|------|------|--------|-------------|
| `ColumnSort` | `bool` | Read/Write | Whether to sort data by column rather than by row. |
| `CaseSensitive` | `bool` | Read/Write | Whether string comparisons during sorting are case-sensitive. |
| `SortMethod` | `string` | Read/Write | The sort algorithm identifier to apply. |
| `Ref` | `string` | Read/Write | The cell range reference that defines the data to be sorted. |
| `Conditions` | `List<AutoFilterSortConditionModel>` | Read | The ordered list of sort conditions to apply. |

## Methods

| Signature | Description |
|-----------|-------------|
| `AutoFilterSortStateModel()` | Initialises a new empty `AutoFilterSortStateModel` with default settings. |
| `Clear()` | Resets all sort conditions and settings to their defaults. |
| `HasStoredState()` | Returns `true` if non-default sort settings are stored in this model. |
""",

"Cell.md": """\
## Overview

`Cell` represents a single cell in a worksheet. It provides access to the cell value, display
value, formula, and type, and supports reading and applying cell styles.

## Properties

| Name | Type | Access | Description |
|------|------|--------|-------------|
| `Value` | `object?` | Read/Write | The raw underlying value of the cell as a .NET object (string, int, bool, decimal, DateTime, or null). |
| `StringValue` | `string` | Read | The cell value converted to a string representation. |
| `DisplayStringValue` | `string` | Read | The cell value formatted as it would appear in a spreadsheet viewer. |
| `Formula` | `string` | Read/Write | The formula string for the cell (e.g. `=A1+B1`); empty when the cell holds a literal value. |
| `Type` | `CellValueType` | Read | The data type of the current cell value. |

## Methods

| Signature | Description |
|-----------|-------------|
| `PutValue(value: string)` | Stores a string value in the cell. |
| `PutValue(value: int)` | Stores an integer value in the cell. |
| `PutValue(value: decimal)` | Stores a decimal value in the cell. |
| `PutValue(value: double)` | Stores a double-precision floating-point value in the cell. |
| `PutValue(value: bool)` | Stores a boolean value in the cell. |
| `PutValue(value: DateTime)` | Stores a DateTime value in the cell. |
| `GetStyle()` | Returns a copy of the current cell style (font, fill, borders, alignment). |
| `SetStyle(style: Style)` | Applies the given style snapshot to the cell. |
""",

# Property names kept from original page (FirstRow/FirstColumn/TotalRows/TotalColumns)
"CellArea.md": """\
## Overview

`CellArea` is a value type (struct) that defines a rectangular cell range by its starting row
and column and the total number of rows and columns it spans. Static factory methods
`CreateCellArea` accept either coordinate pairs or cell-name strings (e.g. `"A1"`, `"D10"`).

## Properties

| Name | Type | Access | Description |
|------|------|--------|-------------|
| `FirstRow` | `int` | Read | Zero-based index of the first row in the range. |
| `FirstColumn` | `int` | Read | Zero-based index of the first column in the range. |
| `TotalRows` | `int` | Read | The total number of rows spanned by the range. |
| `TotalColumns` | `int` | Read | The total number of columns spanned by the range. |

## Methods

| Signature | Description |
|-----------|-------------|
| `CellArea(firstRow: int, firstColumn: int, totalRows: int, totalColumns: int)` | Initialises a `CellArea` using a start position and row/column counts. |
| `CreateCellArea(startRow: int, startColumn: int, endRow: int, endColumn: int)` | Static factory: creates a `CellArea` from inclusive start and end row/column coordinates. |
| `CreateCellArea(startCellName: string, endCellName: string)` | Static factory: creates a `CellArea` from cell-name strings such as `"A1"` and `"D10"`. |
""",

"Color.md": """\
## Overview

`Color` is an immutable value type (struct) representing an ARGB colour with alpha, red, green,
and blue byte components. Use the static `FromArgb` factory method to create instances. It
implements value equality via `IEquatable<Color>`. `Color.Empty` represents a
transparent/unset colour.

## Properties

| Name | Type | Access | Description |
|------|------|--------|-------------|
| `A` | `byte` | Read | The alpha (opacity) channel: 0 is fully transparent, 255 is fully opaque. |
| `R` | `byte` | Read | The red colour channel (0 to 255). |
| `G` | `byte` | Read | The green colour channel (0 to 255). |
| `B` | `byte` | Read | The blue colour channel (0 to 255). |
| `Empty` | `Color` | Read | A static sentinel value representing an unset or transparent colour. |

## Methods

| Signature | Description |
|-----------|-------------|
| `Color(a: byte, r: byte, g: byte, b: byte)` | Initialises a `Color` with explicit ARGB byte values. |
| `FromArgb(a: int, r: int, g: int, b: int)` | Static factory: creates a `Color` from integer ARGB channel values (0–255 each). |
| `Equals(other: Color)` | Returns `true` if `other` has identical ARGB channel values. |
| `Equals(obj: object?)` | Returns `true` if `obj` is a `Color` with identical channel values. |
| `GetHashCode()` | Returns a hash code suitable for use in hash-based collections. |
""",

"ColorValue.md": """\

## Overview

`ColorValue` is an immutable value type (struct) representing an ARGB colour, exposing
individual alpha, red, green, and blue byte components. It implements value equality via
`IEquatable<ColorValue>`.

## Properties

| Name | Type | Access | Description |
|------|------|--------|-------------|
| `A` | `byte` | Read | The alpha (opacity) channel: 0 is fully transparent, 255 is fully opaque. |
| `R` | `byte` | Read | The red colour channel (0 to 255). |
| `G` | `byte` | Read | The green colour channel (0 to 255). |
| `B` | `byte` | Read | The blue colour channel (0 to 255). |

## Methods

| Signature | Description |
|-----------|-------------|
| `ColorValue(a: byte, r: byte, g: byte, b: byte)` | Initialises a new `ColorValue` with explicit ARGB channel values. |
| `Equals(other: ColorValue)` | Returns `true` if `other` has identical ARGB channel values. |
| `Equals(obj: object?)` | Returns `true` if `obj` is a `ColorValue` with identical channel values. |
| `GetHashCode()` | Returns a hash code suitable for use in hash-based collections. |
""",

"FilterColumnModel.md": """\

## Overview

`FilterColumnModel` is a serialization model representing the filter criteria for a single
column within an auto-filter range. It supports string value lists, custom expression filters,
colour filters, dynamic date filters, and top-N filters.

## Properties

| Name | Type | Access | Description |
|------|------|--------|-------------|
| `ColumnIndex` | `int` | Read/Write | Zero-based column index within the auto-filtered range. |
| `HiddenButton` | `bool` | Read/Write | Whether the auto-filter drop-down button is hidden for this column. |
| `Filters` | `List<string>` | Read | List of literal string values for simple equality filtering. |
| `CustomFilters` | `List<AutoFilterCustomFilterModel>` | Read | List of custom comparison-based filter conditions. |
| `CustomFiltersAnd` | `bool` | Read/Write | `true` to combine custom filters with AND; `false` for OR. |
| `ColorFilter` | `AutoFilterColorFilterModel` | Read | Colour-based filter configuration for this column. |
| `DynamicFilter` | `AutoFilterDynamicFilterModel` | Read | Dynamic filter configuration such as date period or average comparisons. |
| `Top10` | `AutoFilterTop10Model` | Read | Top-N or bottom-N filter configuration for this column. |

## Methods

| Signature | Description |
|-----------|-------------|
| `FilterColumnModel()` | Initialises a new empty `FilterColumnModel` with default property values. |
| `ClearCriteria()` | Removes all filter criteria from this column, causing all rows to be shown. |
| `HasStoredState()` | Returns `true` if this column model contains non-default filter settings. |
""",

"PageSetup.md": """\
## Overview

`PageSetup` configures print and page layout settings for a worksheet, including paper size,
orientation, margins, headers and footers, print area, and page break management.

## Properties

| Name | Type | Access | Description |
|------|------|--------|-------------|
| `PaperSize` | `PaperSizeType` | Read/Write | The paper size for printing (e.g. A4, Letter). |
| `Orientation` | `PageOrientationType` | Read/Write | Portrait or landscape page orientation. |
| `FirstPageNumber` | `int?` | Read/Write | The starting page number for the printed output. |
| `Scale` | `int?` | Read/Write | The scaling percentage for printed output (e.g. 75 for 75%). |
| `FitToPagesWide` | `int?` | Read/Write | Number of pages wide to fit the print area onto. |
| `FitToPagesTall` | `int?` | Read/Write | Number of pages tall to fit the print area onto. |
| `PrintArea` | `string` | Read/Write | The cell range to include in the print area (e.g. `A1:F50`). |
| `PrintTitleRows` | `string` | Read/Write | The row range to repeat at the top of each printed page. |
| `PrintTitleColumns` | `string` | Read/Write | The column range to repeat at the left of each printed page. |
| `LeftMargin` | `double` | Read/Write | Left page margin in centimetres. |
| `RightMargin` | `double` | Read/Write | Right page margin in centimetres. |
| `TopMargin` | `double` | Read/Write | Top page margin in centimetres. |
| `BottomMargin` | `double` | Read/Write | Bottom page margin in centimetres. |
| `HeaderMargin` | `double` | Read/Write | Header margin in centimetres (distance from top edge). |
| `FooterMargin` | `double` | Read/Write | Footer margin in centimetres (distance from bottom edge). |
| `LeftMarginInch` | `double` | Read/Write | Left page margin in inches. |
| `RightMarginInch` | `double` | Read/Write | Right page margin in inches. |
| `TopMarginInch` | `double` | Read/Write | Top page margin in inches. |
| `BottomMarginInch` | `double` | Read/Write | Bottom page margin in inches. |
| `HeaderMarginInch` | `double` | Read/Write | Header margin in inches. |
| `FooterMarginInch` | `double` | Read/Write | Footer margin in inches. |
| `LeftHeader` | `string` | Read/Write | Text or format codes for the left section of the page header. |
| `CenterHeader` | `string` | Read/Write | Text or format codes for the centre section of the page header. |
| `RightHeader` | `string` | Read/Write | Text or format codes for the right section of the page header. |
| `LeftFooter` | `string` | Read/Write | Text or format codes for the left section of the page footer. |
| `CenterFooter` | `string` | Read/Write | Text or format codes for the centre section of the page footer. |
| `RightFooter` | `string` | Read/Write | Text or format codes for the right section of the page footer. |
| `PrintGridlines` | `bool` | Read/Write | Whether cell gridlines are included in the printed output. |
| `PrintHeadings` | `bool` | Read/Write | Whether row and column headings are included in the printed output. |
| `CenterHorizontally` | `bool` | Read/Write | Whether the print area is centred horizontally on the page. |
| `CenterVertically` | `bool` | Read/Write | Whether the print area is centred vertically on the page. |
| `HorizontalPageBreaks` | `IReadOnlyList<int>` | Read | The list of row indices where horizontal page breaks have been inserted. |
| `VerticalPageBreaks` | `IReadOnlyList<int>` | Read | The list of column indices where vertical page breaks have been inserted. |

## Methods

| Signature | Description |
|-----------|-------------|
| `AddHorizontalPageBreak(rowIndex: int)` | Inserts a horizontal page break before the specified row. |
| `AddVerticalPageBreak(columnIndex: int)` | Inserts a vertical page break before the specified column. |
| `ClearHorizontalPageBreaks()` | Removes all horizontal page breaks from the worksheet. |
| `ClearVerticalPageBreaks()` | Removes all vertical page breaks from the worksheet. |
""",

"Workbook.md": """\
## Overview

`Workbook` is the top-level entry point for Aspose.Cells FOSS for .NET. It can be instantiated
with no arguments to create a blank workbook, or with a file path or stream to load an existing
XLSX file. `Save` overloads write the workbook to a file path or stream. Implements
`IDisposable`.

## Properties

| Name | Type | Access | Description |
|------|------|--------|-------------|
| `Worksheets` | `WorksheetCollection` | Read | The collection of worksheets; use to access, add, or remove sheets. |
| `Settings` | `WorkbookSettings` | Read | Workbook-level settings such as the 1904 date system and culture information. |
| `Properties` | `WorkbookProperties` | Read | Workbook properties such as code name and protection settings. |
| `DocumentProperties` | `DocumentProperties` | Read | Document metadata properties (author, title, subject, keywords). |
| `DefinedNames` | `DefinedNameCollection` | Read | The collection of named ranges and defined name formulas. |
| `LoadDiagnostics` | `LoadDiagnostics` | Read | Diagnostic information gathered during workbook load; `null` if no warnings were raised. |

## Methods

| Signature | Description |
|-----------|-------------|
| `Workbook()` | Creates a new blank workbook with one default worksheet. |
| `Workbook(fileName: string)` | Loads a workbook from the specified file path. |
| `Workbook(stream: Stream)` | Loads a workbook from the specified stream. |
| `Workbook(fileName: string, options: LoadOptions)` | Loads a workbook with custom load options. |
| `Workbook(stream: Stream, options: LoadOptions)` | Loads a workbook from a stream with custom load options. |
| `Save(fileName: string)` | Saves the workbook to the specified file path in XLSX format. |
| `Save(fileName: string, format: SaveFormat)` | Saves the workbook to a file path in the specified format. |
| `Save(fileName: string, options: SaveOptions)` | Saves the workbook to a file path with custom save options. |
| `Save(stream: Stream, format: SaveFormat)` | Saves the workbook to a stream in the specified format. |
| `Save(stream: Stream, options: SaveOptions)` | Saves the workbook to a stream with custom save options. |
| `Dispose()` | Releases resources held by the workbook. |
""",

"WorkbookPropertiesModel.md": """\

## Overview

`WorkbookPropertiesModel` is a serialization model that aggregates workbook-level settings for
round-trip XLSX preservation, including privacy settings, display options, calculation
properties, and protection configuration.

## Properties

| Name | Type | Access | Description |
|------|------|--------|-------------|
| `CodeName` | `string` | Read/Write | The VBA module code name for the workbook. |
| `ShowObjects` | `string` | Read/Write | How embedded objects are displayed: all, placeholders, or none. |
| `FilterPrivacy` | `bool` | Read/Write | Whether personal information is stripped from the file on save. |
| `ShowBorderUnselectedTables` | `bool` | Read/Write | Whether borders are shown around unselected tables. |
| `ShowInkAnnotation` | `bool` | Read/Write | Whether ink annotations are displayed. |
| `BackupFile` | `bool` | Read/Write | Whether a backup copy is created on save. |
| `SaveExternalLinkValues` | `bool` | Read/Write | Whether cached values from external links are preserved on save. |
| `UpdateLinks` | `string` | Read/Write | How external links are updated on open: always, never, or prompt. |
| `HidePivotFieldList` | `bool` | Read/Write | Whether the PivotTable field list panel is hidden. |
| `DefaultThemeVersion` | `int?` | Read/Write | The default Office theme version applied to the workbook. |
| `Protection` | `WorkbookProtectionModel` | Read | The workbook-level protection settings model. |
| `View` | `WorkbookViewModel` | Read | The workbook view settings model. |
| `Calculation` | `CalculationPropertiesModel` | Read | The formula calculation settings model. |

## Methods

| Signature | Description |
|-----------|-------------|
| `WorkbookPropertiesModel()` | Initialises a new `WorkbookPropertiesModel` with default property values. |
| `CopyFrom(source: WorkbookPropertiesModel)` | Copies all property values from the source model into this instance. |
| `HasWorkbookPropertiesState()` | Returns `true` if any property holds a non-default value requiring serialisation. |
""",

"WorksheetCollection.md": """\
## Overview

`WorksheetCollection` provides indexed and named access to all worksheets in a workbook. It
supports adding worksheets by name, removing them by name or index, and iterating over them.
Implements `IEnumerable<Worksheet>`.

## Properties

| Name | Type | Access | Description |
|------|------|--------|-------------|
| `Count` | `int` | Read | The number of worksheets in the collection. |
| `ActiveSheetIndex` | `int` | Read/Write | The zero-based index of the currently active (selected) worksheet. |
| `ActiveSheetName` | `string` | Read/Write | The name of the currently active (selected) worksheet. |

## Methods

| Signature | Description |
|-----------|-------------|
| `Add()` | Creates a new blank worksheet, appends it to the collection, and returns it. |
| `Add(sheetName: string)` | Creates a new worksheet with the specified name, appends it, and returns it. |
| `RemoveAt(sheetName: string)` | Removes the worksheet with the given name from the collection. |
| `RemoveAt(index: int)` | Removes the worksheet at the given zero-based index from the collection. |
| `GetEnumerator()` | Returns an enumerator that iterates over all worksheets in order. |
""",

}


def replace_body(path: Path, new_body: str, dry_run: bool) -> bool:
    """Return True on success, False on error."""
    if not path.exists():
        print(f"  ERROR: file not found: {path}", file=sys.stderr)
        return False
    try:
        content = path.read_text(encoding="utf-8")
        first = content.index("---\n")
        second = content.index("---\n", first + 4)
        frontmatter = content[: second + 4]  # includes closing ---\n
        new_content = frontmatter + "\n" + new_body
        if dry_run:
            print(f"  DRY-RUN: would update {path.name}")
        else:
            path.write_text(new_content, encoding="utf-8", newline="\n")  # type: ignore[call-overload]
            print(f"  Updated: {path.name}")
        return True
    except (ValueError, OSError) as exc:
        print(f"  ERROR processing {path.name}: {exc}", file=sys.stderr)
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be changed without writing files.")
    args = parser.parse_args()

    errors = 0
    for filename, body in NEW_BODIES.items():
        if not replace_body(BASE / filename, body, dry_run=args.dry_run):
            errors += 1

    total = len(NEW_BODIES)
    success = total - errors
    print(f"\n{'DRY-RUN: ' if args.dry_run else ''}{success}/{total} files updated.")
    return errors


if __name__ == "__main__":
    sys.exit(main())
