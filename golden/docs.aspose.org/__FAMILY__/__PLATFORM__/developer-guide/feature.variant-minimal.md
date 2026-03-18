<!-- GOLDEN REFERENCE | Structural Exemplar | Language: Python (structural only) | Original-Grade: derived -->
---
description: Efficiently convert documents between source and target formats with high fidelity using {{PRODUCT_NAME}}.
title: "{{PRODUCT_NAME}} Format Converter"
type: docs
---

{{PRODUCT_NAME}} enables seamless, high-fidelity conversion between source and target document formats. It exposes a focused API tailored for format export and import, ensuring quick integration into any {{PLATFORM}} application that requires rendering or processing document content.

## Usage Examples

### Basic Conversion

The simplest way to convert a document to the target format using a single call:

```python
import library.lowcode as lc
import library

src = "template.xlsx"
lc.Converter.process(src, "output/result.html")
print("Conversion complete")
```

## See Also

- [Installation](/docs/{{PRODUCT_FAMILY}}/getting-started/installation/)
- [Metered Licensing](/docs/{{PRODUCT_FAMILY}}/getting-started/metered-licensing/)
