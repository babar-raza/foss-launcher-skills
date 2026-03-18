<!-- GOLDEN REFERENCE | Structural Exemplar | Language: Python (structural only) | Original-Grade: A -->
---
title: Developer Guide
description: >-
  Unlock the full potential of your {{PLATFORM}} applications with the comprehensive
  {{PRODUCT_NAME}} Developer Guide for document processing and automation.
type: docs
weight: 99
---

{{PRODUCT_NAME}} is a powerful library designed to facilitate the processing, manipulation, and management of documents within {{PLATFORM}} applications. Whether you're building document automation systems, enterprise reporting tools, e-learning platforms, or content publishing workflows, {{PRODUCT_FAMILY}} provides a comprehensive set of features that cater to a wide range of document processing needs.

## Key Features

### Document Format Conversion
Convert documents between multiple formats with full fidelity preservation. Support for bidirectional conversion between native and open-standard formats enables cross-platform collaboration. Maintain layouts, fonts, themes, and embedded media during conversion without any dependency on desktop applications.

### Document Merging and Assembly
Combine multiple documents into unified outputs with full control over section order and content fidelity. Merge documents from different authors, templates, and sources while preserving formatting. Ideal for automated report generation, executive summaries, and training course assembly.

### Text Extraction and Content Analysis
Extract text from documents, sections, and embedded content for search indexing, compliance scanning, and AI-powered content analysis. Support both structured and raw extraction modes for different processing requirements.

### Multi-Format Export
Export documents to PDF (with archival compliance), HTML (for web publishing), and high-quality images (JPEG, PNG, SVG, TIFF) for various distribution channels. Customize output quality, resolution, compression, and include metadata as needed for professional document generation and archival workflows.

## Getting Started with {{PRODUCT_NAME}}

To help you get started, here are simple examples demonstrating common document processing tasks using the simplified API.

### Example: Convert Document Formats

```python
import library

# Convert between formats
doc = library.Document("legacy_input.ppt")
doc.save("modern_output.pptx")
print("Format conversion complete")

# Convert to open format
doc2 = library.Document("presentation.pptx")
doc2.save("output.odp")
print("Open format export complete")

# Convert from open format
doc3 = library.Document("document.odp")
doc3.save("converted.pptx")
print("Import complete")
```

### Example: Merge Multiple Documents

```python
import library.lowcode as lc

# Merge multiple documents into one
lc.Merger.process(
    [
        "department1.pptx",
        "department2.pptx",
        "department3.pptx",
    ],
    "quarterly-report.pptx",
)
print("Merge complete")
```

### Example: Export to Multiple Formats

```python
import library
import library.lowcode as lc

doc = library.Document("presentation.pptx")

# Export to PDF
lc.Convert.to_pdf(doc, "output.pdf")

# Export to JPEG images
lc.Convert.to_jpeg(doc, "slide.jpg")

# Export to PNG images
lc.Convert.to_png(doc, "slide.png")

# Export to SVG (scalable vector graphics)
lc.Convert.to_svg(doc, "slide.svg")

# Export to TIFF (print-ready)
lc.Convert.to_tiff(doc, "slides.tiff")

print("All exports complete")
```

### Explanation
1. **Format Conversion**: Simple API calls to convert between native and open formats while preserving all content.
2. **Document Merging**: Combine multiple documents with a single call using the Merger API.
3. **Multi-Format Export**: Export documents to PDF for archival or images for web publishing and documentation.

These examples showcase the simplicity and power of {{PRODUCT_NAME}} for handling common document processing tasks in {{PLATFORM}} applications.

## Available Modules

{{PRODUCT_NAME}} offers specialized modules for document processing tasks with flexible licensing:

- **[Document Converter](document-converter/)**: Convert between native, open-standard, and template formats with full fidelity preservation.
- **[Document Merger](document-merger/)**: Combine multiple documents into unified outputs with content control.
- **[Text Extractor](text-extractor/)**: Extract text from documents, sections, and embedded content for indexing and analysis.
- **[HTML Converter](html-converter/)**: Export documents to HTML for web publishing and online viewing.
- **[JPEG Converter](jpeg-converter/)**: Generate high-quality JPEG images for thumbnails and web previews.
- **[PDF Converter](pdf-converter/)**: Create PDF documents with compliance standards and custom settings.
- **[PNG Converter](png-converter/)**: Export lossless PNG images for UI components and documentation.
- **[SVG Converter](svg-converter/)**: Generate scalable vector graphics for responsive web design.
- **[TIFF Converter](tiff-converter/)**: Produce print-ready TIFF images for archival and document imaging.
