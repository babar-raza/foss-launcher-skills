<!-- GOLDEN REFERENCE | Structural Exemplar | Language: Python (structural only) | Original-Grade: A -->
---

description: Efficiently convert documents between source and target formats, ensuring layout fidelity and format consistency across output types.
title: "{{PRODUCT_NAME}} Document Converter"
type: docs
---

{{PRODUCT_NAME}} provides a dedicated, high-performance solution to convert documents into universally accessible output formats while preserving layout fidelity and format consistency. With streamlined APIs, it ensures accurate rendering, advanced customization options, and smooth integration into {{PLATFORM}} applications.

## Installation and Setup

To integrate the converter into your project:

* Install the {{PRODUCT_FAMILY}} package using {{PACKAGE_MANAGER}} (see [Installation](/docs/{{PRODUCT_FAMILY}}/getting-started/installation/)).
* Apply metered licensing before using the APIs (see [Metered Licensing](/docs/{{PRODUCT_FAMILY}}/getting-started/metered-licensing/)).

## Features and Functionalities

{{PRODUCT_NAME}} offers a rich set of features for document processing on the {{PLATFORM}} platform, covering format conversion, layout control, security, and performance optimization.

### Comprehensive Format Support

* Convert from multiple source formats including native, open-standard, and legacy formats.
* Support for charts, tables, images, shapes, and embedded objects.
* Round-trip accuracy when exporting complex documents.

### High-Fidelity Layout and Formatting

* Preserve fonts, styles, colors, borders, margins, headers, and footers.
* Honor page breaks and the source document's print settings.
* Ensure precise alignment with original document print preview.

### Selective Conversion

* Export the full document, individual sections, or custom ranges.
* Perfect for dashboards, reports, and selective data exports.
* Minimize output file size by targeting only required sections.

### Pagination Control

* **One Page Per Section**: Force each section onto a single output page regardless of content size.
* **Custom Page Breaks**: Honor or override the source document's built-in page break settings.
* **Fit-to-Page Options**: Scale sections to fit specific page dimensions.
* **Multi-Page Handling**: Control how large sections split across multiple output pages.

### Advanced Output Options

* Define compliance targets for archival or print-ready output.
* Apply compression for text, images, and objects.
* Control image downsampling and quality thresholds.
* Add document metadata and properties.

### Flexible Output Options

* **File-Based Output**: Save directly to disk with automatic directory creation.
* **Stream-Based Output**: Write to memory buffers for in-memory processing.
* **Network Streams**: Output directly to network locations or cloud storage.

### Encryption and Security

* Protect documents with AES encryption (40–256-bit).
* Restrict permissions for printing, copying, and editing.
* Support for digital signatures (via integration with other library APIs).

### Performance and Scalability

* Stream-based processing for large documents.
* Multi-threaded conversions for server-side scaling.
* Caching of fonts and resources to optimize throughput.

### Logging and Error Handling

* Capture detailed warnings (e.g., missing fonts, unsupported features).
* Distinct exception types for licensing, format, and resource issues.
* Compatible with standard logging frameworks for centralized diagnostics.

---

## Usage Examples

The following examples demonstrate common document processing patterns with {{PRODUCT_NAME}}, from basic single-file conversion through advanced batch processing and web API integration.

### Basic Conversion

The simplest way to convert a document to the target format using a single call:

```python
import library.lowcode as lc

src = "template.xlsx"
lc.Converter.process(src, "output/result.pdf")
print("Conversion complete")
```

This converts the entire document with default settings, preserving all sections and formatting.

### Advanced Conversion with Custom Options

Configure format-specific options for precise control over the output:

```python
import library.lowcode as lc
import library

src = "template.xlsx"

# Configure load options
load_opts = lc.LoadOptions()
load_opts.input_file = src

# Configure save options
save_opts = lc.SaveOptions()
output_opts = library.OutputFormatOptions()

# Force each section to fit on a single output page
output_opts.one_page_per_section = True

save_opts.format_options = output_opts
save_opts.output_file = "output/result.pdf"

# Perform conversion
lc.Converter.process(load_opts, save_opts)
print("Advanced conversion complete")
```

### Feature Breakdown: One Page Per Section

Control how sections are paginated in the output:

```python
output_opts = library.OutputFormatOptions()

# Each section fits on exactly one output page (scaling applied if needed)
output_opts.one_page_per_section = True

# Default behavior: respect the source document's page breaks
output_opts.one_page_per_section = False
```

**Use Cases:**
- **Dashboard Exports**: Ensure each dashboard fits on a single page for presentations
- **Summary Reports**: Keep overview sections compact and readable
- **Thumbnail Generation**: Create single-page previews of sections
- **Print-Ready Documents**: Simplify printing by avoiding multi-page splits
- **Executive Summaries**: Present high-level data on one page

**Before and After:**
```
Without one_page_per_section:
- Large section → Multiple output pages (respects page breaks)
- Section1: Pages 1-3, Section2: Pages 4-6

With one_page_per_section = True:
- Large section → Scaled to fit single output page
- Section1: Page 1, Section2: Page 2
```

### Feature Breakdown: File-Based vs Stream-Based Output

Choose the output method that best fits your scenario:

```python
import io

# File-based output (simplest)
save_opts.output_file = "output/result.pdf"

# Stream-based output (for in-memory processing)
buffer = io.BytesIO()
save_opts.output_stream = buffer

# Network/cloud output (for remote storage)
with open("//server/share/output.pdf", "wb") as remote_stream:
    save_opts.output_stream = remote_stream
    lc.Converter.process(load_opts, save_opts)
```

**File-Based Output Advantages:**
- Simpler syntax
- Automatic directory creation
- Lower memory usage
- Ideal for batch processing

**Stream-Based Output Advantages:**
- No disk I/O required
- Flexible routing (web response, cloud, email)
- In-memory caching
- Ideal for web APIs

### Feature Breakdown: Simplified API Benefits

Compare the traditional and simplified approaches:

```python
import library

# Traditional API (verbose, more control)
doc = library.Document("Book1.xlsx")
save_options = library.OutputFormatOptions()
save_options.one_page_per_section = True
doc.save("output.pdf", save_options)

# Simplified API (concise, optimized)
import library.lowcode as lc

load_opts = lc.LoadOptions()
load_opts.input_file = "Book1.xlsx"

save_opts = lc.SaveOptions()
output_opts = library.OutputFormatOptions()
output_opts.one_page_per_section = True
save_opts.format_options = output_opts
save_opts.output_file = "output.pdf"

lc.Converter.process(load_opts, save_opts)
print("Conversion complete")
```

**Simplified API Advantages:**
- Optimized memory usage
- Faster execution
- Better resource management
- Cleaner separation of concerns

### Advanced Pagination Control

Fine-tune how content flows across output pages:

```python
output_opts = library.OutputFormatOptions()

# Single page per section with scaling
output_opts.one_page_per_section = True

# Fit all columns on one page
output_opts.all_columns_in_one_page = True

# Limit number of output pages
output_opts.page_count = 1

# Custom scaling behavior
output_opts.printing_page_type = library.PrintingPageType.IGNORE_PRINT_AREA
```

### Selective Section Export

Export only specific sections to reduce output size:

```python
output_opts = library.OutputFormatOptions()

# Export only the first section
output_opts.page_index = 0
output_opts.page_count = 1

# For multiple specific sections, use the traditional API
# with section selection methods
```

### Traditional API: Maximum Control

For scenarios requiring comprehensive customization:

```python
import library

# Load a document
doc = library.Document("sample.xlsx")

# Configure detailed output options
save_options = library.OutputFormatOptions()
save_options.one_page_per_section = True
save_options.compliance = library.Compliance.ARCHIVAL_1B
save_options.embed_standard_fonts = True
save_options.optimization_type = library.OptimizationType.MINIMUM_SIZE
save_options.calculate_formulas = True

# Add metadata
save_options.created_time = library.DateTime.now()
save_options.producer = "My Application v1.0"

# Save the document
doc.save("output.pdf", save_options)
print("Document saved with custom options")
```

### Web API Integration Example

Use document conversion in a web framework endpoint:

```python
import library.lowcode as lc
import library
import io
import os
import tempfile

def convert_to_pdf(uploaded_file):
    try:
        # Save uploaded file temporarily
        temp_path = tempfile.mktemp(suffix=".xlsx")
        with open(temp_path, "wb") as f:
            f.write(uploaded_file.read())

        # Configure conversion
        load_opts = lc.LoadOptions()
        load_opts.input_file = temp_path

        save_opts = lc.SaveOptions()
        output_opts = library.OutputFormatOptions()
        output_opts.one_page_per_section = True
        save_opts.format_options = output_opts

        buffer = io.BytesIO()
        save_opts.output_stream = buffer

        lc.Converter.process(load_opts, save_opts)

        # Clean up
        os.remove(temp_path)

        # Return converted content
        print("Conversion successful")
        return buffer.getvalue()

    except Exception as e:
        print(f"Conversion error: {e}")
        return None
```

### Batch Processing with Mixed Options

Process multiple files with different pagination settings:

```python
import library.lowcode as lc
import library
import os

conversions = [
    {"file": "sample.xlsx", "one_page": True},
    {"file": "example.xlsx", "one_page": False},
    {"file": "document.xlsx", "one_page": True},
]

for conv in conversions:
    load_opts = lc.LoadOptions()
    load_opts.input_file = conv["file"]

    save_opts = lc.SaveOptions()
    output_opts = library.OutputFormatOptions()
    output_opts.one_page_per_section = conv["one_page"]
    save_opts.format_options = output_opts

    base_name = os.path.splitext(conv["file"])[0]
    save_opts.output_file = f"{base_name}.pdf"

    lc.Converter.process(load_opts, save_opts)
    print(f"Converted: {conv['file']}")
```

---

## Tips and Best Practices

Follow these guidelines to get the best results from {{PRODUCT_NAME}} in production deployments, covering layout quality, performance tuning, and resource management.

### Layout Optimization

* **Define Print Areas**: Set print areas and page setup in source documents before conversion for consistent results.
* **Use One Page Per Section**: Enable for dashboards, summaries, and presentation materials to ensure compact output.
* **Test Page Breaks**: Preview the source document's print layout to understand how content will flow in the output.

### Performance Optimization

* **Use Simplified API**: Leverage the simplified conversion methods for optimized memory usage and faster execution.
* **Pool Settings**: For high-volume conversions, reuse option objects to reduce overhead.
* **Profile Memory**: Monitor memory usage for very large documents; consider splitting exports if needed.

### Output Quality

* **Font Embedding**: Enable standard font embedding to ensure consistent rendering across platforms.
* **Compliance Standards**: Set the compliance property for archival or print-ready requirements.
* **Compression**: Apply optimization settings to balance file size and quality.

### Resource Management

* **Clean Up Properly**: Close file handles and release document objects promptly to free resources.
* **File vs Stream**: Use file-based output for batch jobs, streams for web APIs.
* **Temporary Files**: Clean up temporary files after processing in web applications.

### Production Deployment

* **Error Handling**: Wrap conversions in try/except blocks for robust error management.
* **Logging**: Log conversion metrics (file size, page count, duration) for monitoring.
* **Track Usage**: Monitor metered licensing token usage for cost management.
* **Output Validation**: Verify output file size and page count after conversion.

---

## Common Issues and Resolutions

| Issue | Resolution |
|-------|------------|
| **File not found** | Verify file paths and ensure proper path separators for your operating system |
| **Unsupported format** | Ensure the input file is one of the supported types for this library |
| **Large file performance** | Enable streaming, disable one-page-per-section for very large documents |
| **Content cut off** | Content is scaled to fit; check original document page setup and print preview |
| **Blurry text** | Increase DPI in output options or disable one-page-per-section |
| **Missing fonts** | Enable font embedding or install required fonts on the server |
| **Output file locked** | Ensure all file handles are properly closed after conversion |
| **Memory overflow** | Process large files in chunks or adjust pagination settings |

---

## Frequently Asked Questions

**What is {{PRODUCT_NAME}}?**
A specialized tool for converting documents to the target output format with high fidelity and precise pagination control.

**How does it differ from the full {{PRODUCT_FAMILY}} library?**
{{PRODUCT_FAMILY}} supports a broad range of document manipulation tasks, while this converter focuses specifically on accurate format export with streamlined APIs.

**Can I customize the output?**
Yes, using the output format options you can control compliance, compression, security, font embedding, and pagination behavior.

**Which formats are supported for conversion?**
Multiple source and target formats are supported, including native, open-standard, CSV, HTML, XML, JSON, and more.

**What does one-page-per-section do?**
It forces each document section to fit on exactly one output page by applying automatic scaling, ideal for dashboards and summary reports.

**When should I use one-page-per-section?**
Use it for dashboards, executive summaries, or any content that should remain on a single page. Avoid it for detailed reports with large data tables.

**Can I output to memory instead of files?**
Yes! Use the output_stream property with a BytesIO buffer for complete in-memory processing.

**How do I choose between file-based and stream-based output?**
Use output_file for batch processing and disk-based workflows. Use output_stream for web APIs, cloud storage, or in-memory operations.

**Does the simplified API support all features?**
The simplified API exposes the most commonly used features. For advanced scenarios (digital signatures, custom security), use the traditional Document API.

---

## API Reference Summary

The {{PRODUCT_NAME}} API is organized around a small set of core classes that handle loading, configuring, and saving documents in the target format.

### Key Classes

- **`Converter`**: Simplified class providing streamlined conversion methods
- **`LoadOptions`**: Configuration for loading source documents
- **`SaveOptions`**: Configuration for output (file or stream)
- **`OutputFormatOptions`**: Detailed conversion settings for the target format

### Essential Properties

- **`input_file`**: Source document file path
- **`output_file`**: Target file path (file-based output)
- **`output_stream`**: Target stream for output (stream-based output)
- **`format_options`**: Format-specific rendering options
- **`one_page_per_section`**: Force each section onto a single output page
- **`compliance`**: Output compliance standard for archival or print
- **`optimization_type`**: Balance between file size and quality

### Common Enumerations

- **`Compliance`**: NONE, STANDARD_15, ARCHIVAL_1B, ARCHIVAL_2U, PRINT_X1A
- **`OptimizationType`**: STANDARD, MINIMUM_SIZE
- **`PrintingPageType`**: DEFAULT, IGNORE_PRINT_AREA, IGNORE_STYLE

## Overview

{{PRODUCT_NAME}} provides a comprehensive set of document processing capabilities
for the {{PLATFORM}} platform. The library enables developers to load, transform,
and save documents in multiple formats without requiring any desktop application
dependencies or external rendering engines.

## Code Examples

The following examples demonstrate common usage patterns for {{PRODUCT_NAME}}.

```python
import library

# Load a document and inspect its structure
doc = library.Document("input.source")
print(f"Document loaded: {doc.page_count} pages")

# Convert to a different format
options = library.SaveOptions()
options.format = library.SaveFormat.TARGET
doc.save("output.target", options)
print("Conversion complete")
```

- Load any supported source format with a single constructor call
- Inspect document structure and metadata before processing
- Convert between formats using save options for fine-grained control

## Core Concepts

Understanding the following core concepts will help you use {{PRODUCT_NAME}} effectively:

- **Document Model**: Every file is loaded into an in-memory document object that
  exposes pages, sections, and content elements for inspection and manipulation.
- **Format Options**: Each output format supports specific options (quality, layout,
  encryption) configured via dedicated option classes.
- **Processing Pipeline**: The standard workflow follows Load → Configure → Process → Save → Verify.
- **Stream Support**: All operations support both file-path and stream-based I/O for
  integration into web services and containerized environments.

## Implementation

To implement {{PRODUCT_NAME}} in your project, follow these steps:

1. Install the library using {{PACKAGE_MANAGER}}: `{{PACKAGE_MANAGER}} install {{PACKAGE_NAME}}`
2. Import the library module in your script
3. Load the source document using the main document class
4. Configure output options for your target format
5. Call the conversion or processing method
6. Verify the output file exists and has expected content

```python
import library

# Step 1-2: Import and load
doc = library.Document("report.source")

# Step 3-4: Configure and process
options = library.OutputFormatOptions()
options.quality = "high"
doc.save("report.target", options)

# Step 5: Verify
import os
assert os.path.exists("report.target"), "Output file was not created"
print(f"Output size: {os.path.getsize('report.target')} bytes")
```

## Summary

{{PRODUCT_NAME}} simplifies document processing for {{PLATFORM}} developers by providing
a unified API for loading, transforming, and saving documents across multiple formats.
The library handles format-specific complexity internally, allowing developers to focus
on their application logic rather than document parsing details.

## Notes and Best Practices

- Always verify output files after conversion — check that the file exists and has non-zero size.
- Use stream-based I/O when processing documents in web services or serverless functions
  to avoid temporary file management.
- Configure format-specific options explicitly rather than relying on defaults — this
  ensures consistent output quality across different document types.
- Wrap processing calls in try/except blocks to handle corrupt input files gracefully.
- For batch processing, reuse option objects across iterations to reduce memory allocation.

## Features and Capabilities

{{PRODUCT_NAME}} offers the following capabilities for {{PLATFORM}} developers:

- **Multi-Format Support**: Read and write documents in multiple source and target formats
  without external dependencies.
- **Layout Preservation**: Maintain fonts, styles, images, and page layout during conversion.
- **Batch Processing**: Process multiple files in a single script using loops or parallel execution.
- **Security Features**: Apply encryption, password protection, and digital signatures to output documents.
- **Streaming API**: Process documents directly from and to streams for cloud-native applications.

## Troubleshooting

### File Not Found During Load

**Symptom**: `FileNotFoundError` when calling `library.Document("path/to/file")`.

**Cause**: The file path is incorrect or the file does not exist at the specified location.

**Fix**: Verify the file path using `os.path.exists()` before loading. Use absolute paths
in production environments to avoid working-directory issues.

### Output File Is Empty or Corrupt

**Symptom**: The output file has zero bytes or cannot be opened.

**Cause**: The save operation failed silently, or the output format is incompatible with
the source document structure.

**Fix**: Check the return value of the save operation and verify format compatibility.
Enable logging to capture conversion warnings.

### Memory Issues with Large Documents

**Symptom**: `MemoryError` or excessive memory consumption during processing.

**Cause**: Very large documents (100+ pages, many images) may exceed available memory.

**Fix**: Use stream-based processing to avoid loading the entire document into memory.
Process documents in chunks when possible.
