<!-- GOLDEN REFERENCE | Structural Exemplar | Language: Python (structural only) | Original-Grade: B+ | Source: aspose.org/content/kb.aspose.org/cells/en/python/faq.md | Extracted: 2026-03-17 -->
---

title: "{{PRODUCT_NAME}} FAQ"
description: "Frequently asked questions about {{PRODUCT_NAME}} — installation, basic operations, supported formats, and common API mistakes."
date: 2025-01-17
lastmod: 2025-01-17
weight: 8
draft: false
type: "faq"
keywords: [
   "{{PRODUCT_FAMILY}} faq",
   "{{PRODUCT_FAMILY}} python",
   "{{PRODUCT_FAMILY}} common questions",
   "{{PRODUCT_FAMILY}} troubleshooting",
   "{{PRODUCT_FAMILY}} getting started"]
---

## Frequently Asked Questions

This section answers the most common questions about installing, configuring, and using {{PRODUCT_NAME}} in {{PLATFORM}} projects. Each answer includes a runnable code example.

### How do I install {{PRODUCT_NAME}}?

Install it from PyPI using pip:

```python
pip install {{PACKAGE_NAME}}>=26.3.1
```

After installation, verify it works:

```python
import library

obj = library.Document()
print("Installation successful")
```

### How do I read data from a loaded document?

Use the appropriate property accessor. Properties are accessed directly — do not add parentheses.

```python
import library

doc = library.Document("input.source")
section = doc.sections[0]

# Correct: .value is a property (no parentheses)
val = section.content["A1"].value
print(val)

# Also correct: access by index (0-based)
val2 = section.content[0, 0].value
print(val2)
```

### How do I write data to a document?

Assign to `.value` or `.formula` directly. Both are properties, not methods.

```python
import library

doc = library.Document()
section = doc.sections[0]

# Write a value
section.content["A1"].value = "Product"
section.content["B1"].value = 100

# Write a formula
section.content["C1"].formula = "=SUM(A1:B1)"

doc.save("output.target")
```

### Does {{PRODUCT_NAME}} support PDF export?

No. PDF export is not available in the FOSS edition. The supported save formats are:

- **Primary format** — `doc.save("output.primary")`
- **CSV** — `doc.save("output.csv")`
- **Markdown** — `doc.save_as_markdown("output.md")`

### How do I load a file with non-default options?

Use `LoadOptions` with the appropriate `LoadFormat` as the second argument:

```python
import library

opts = library.LoadOptions(library.LoadFormat.CSV)
doc = library.Document("data.csv", opts)
section = doc.sections[0]
val = section.content["A1"].value
```

### How do I create a visual element (chart or diagram)?

Use one of the `add_*` methods on the relevant collection. Each method takes positional arguments for the bounding box: `top_row`, `left_col`, `bottom_row`, `right_col`.

```python
import library

doc = library.Document()
section = doc.sections[0]

# Add data
section.content["A1"].value = "Category"
section.content["B1"].value = "Value"
section.content["A2"].value = "Item A"
section.content["B2"].value = 1200
section.content["A3"].value = "Item B"
section.content["B3"].value = 1500

# Add a chart (top_row, left_col, bottom_row, right_col)
chart_idx = section.charts.add_bar(5, 0, 20, 8)
chart = section.charts[chart_idx]
chart.title = "Summary"
chart.n_series.add("B2:B3", True)

doc.save("output.target")
```

### Why does `element.value()` raise a TypeError?

Because `.value` is a property, not a method. Calling `element.value()` attempts to call the returned value as a function, which raises `TypeError`. Always use assignment or direct attribute access:

```python
# Wrong — raises TypeError
element.value("Hello")
element.formula("=SUM(A1:A5)")
val = element.value()

# Correct
element.value = "Hello"
element.formula = "=SUM(A1:A5)"
val = element.value
```

### What file formats can be loaded?

| Format | Extension | How to load |
|--------|-----------|-------------|
| Primary format | .primary | `library.Document("file.primary")` |
| Legacy format | .legacy | `library.Document("file.legacy")` |
| CSV | .csv | `library.Document("file.csv", library.LoadOptions(library.LoadFormat.CSV))` |

## See Also

{{PRODUCT_NAME}} is licensed under the MIT License. Review the full license terms in the [LICENSE]({{REPO_URL}}/blob/main/License/license.txt) file. For installation and basic usage, see the [README]({{REPO_URL}}/blob/main/README.md) and the [examples directory]({{REPO_URL}}/tree/main/examples).

- [Convert file formats](/kb.aspose.org/{{FAMILY}}/{{PLATFORM}}/how-to-convert-formats/)
- [Fix common errors](/kb.aspose.org/{{FAMILY}}/{{PLATFORM}}/how-to-fix-errors/)
- [Load files](/kb.aspose.org/{{FAMILY}}/{{PLATFORM}}/how-to-load-files/)
- [Optimize performance](/kb.aspose.org/{{FAMILY}}/{{PLATFORM}}/how-to-optimize-performance/)
- [Save files](/kb.aspose.org/{{FAMILY}}/{{PLATFORM}}/how-to-save-files/)
