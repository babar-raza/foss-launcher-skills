---
title: "Getting Started with Aspose.Words for Python"
description: "Learn how to process Word documents with Aspose.Words for Python"
type: docs
weight: 10
---

## Overview

Aspose.Words for Python is a library for processing Word documents programmatically.
It supports loading, editing, converting, and saving documents in multiple formats.

## Installation

Install the package using pip:

```bash
pip install aspose-words-foss
```

## Loading a Document

Use the `Document` class to load Word files from disk:

```python
from aspose.words import Document

doc = Document("input.docx")
print("Loaded document successfully")
```

## Saving a Document

Save the document back to disk:

```python
doc.save("output.docx")
```

## Converting Documents

Convert a document to PDF or other formats:

```python
doc.convert("pdf", "output.pdf")
```

## Supported Formats

Aspose.Words for Python supports the following formats:

- **DOCX** — import and export
- **PDF** — export only
- **RTF** — import and export

## Summary

This guide covered the basics of loading, editing, and converting Word documents
using Aspose.Words for Python. See the API reference for full details.
