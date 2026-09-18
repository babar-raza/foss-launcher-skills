# -*- coding: utf-8 -*-
import json, re

S = r"<local-plan-cache>/pdfts"
D = "reports/repo-presenter-regen-full/pdf/typescript"
P = json.load(open(f"{S}/assembled_parts.json", encoding="utf-8"))

# normalize the accidental double-blank-line left by the H3-strip regex
additional_examples_body = re.sub(r"\n\n\n+", "\n\n", P["additional_examples_body"])
api_overview_body = re.sub(r"\n\n\n+", "\n\n", P["api_overview_body"])
limitations_body = re.sub(r"\n\n\n+", "\n\n", P["limitations_body"])
development_body = re.sub(r"\n\n\n+", "\n\n", P["development_body"])
class_table_body = P["class_table_body"]

HEADER = """# Aspose.PDF FOSS for TypeScript

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE) [![Contributors](https://img.shields.io/github/contributors/aspose-pdf-foss/Aspose.PDF-FOSS-for-TypeScript.svg)](https://github.com/aspose-pdf-foss/Aspose.PDF-FOSS-for-TypeScript/graphs/contributors)

[![Aspose.PDF FOSS for TypeScript](https://products.aspose.org/media/pdf/typescript/banner-readme.png)](https://products.aspose.org/pdf/typescript/)

Aspose.PDF FOSS for TypeScript is a free, open-source, zero-dependency TypeScript library for
reading, manipulating, and writing PDF files in Node.js.

The library parses an entire PDF into an in-memory object model on `Open`. All mutations (page
edits, metadata changes, reordering) act directly on that live model, and `Save()` serializes a
fresh, renumbered document from it — no incremental updates, no temp files.

## Navigation

- [At a Glance](#at-a-glance)
- [Key Capabilities](#key-capabilities)
- [Installation](#installation)
- [Dependencies](#dependencies)
- [Quick Start](#quick-start)
- [Additional Examples](#additional-examples)
- [API Reference](#api-reference)
- [Documentation & Resources](#documentation--resources)
- [Scope and Limitations](#scope-and-limitations)
- [Development and Testing](#development-and-testing)
- [License](#license)

## At a Glance

```mermaid
flowchart TD
  subgraph StartingPoints["Starting Points"]
    direction LR
    i1["An existing PDF file"]
    i2["An HTML document"]
    i3["Markdown text (CommonMark/GFM)"]
  end
  PRODUCT["Aspose.PDF FOSS for TypeScript"]
  subgraph Capabilities["Core Capabilities"]
    direction LR
    subgraph capl[" "]
      direction TB
      c1["Parse and repair PDF documents"]
      c2["Edit pages, metadata and content streams"]
      c3["Author text, vector graphics and images"]
      c4["Build tables, flow layouts and multi-page documents"]
      c5["Create, fill and flatten AcroForm fields"]
    end
    subgraph capr[" "]
      direction TB
      c6["Manage annotations, outlines, layers and attachments"]
      c7["Encrypt, sign and validate PDF/A, PDF/X and PDF/UA"]
      c8["Extract and search text, tables and vector paths"]
      c9["Render and export to images, HTML, Markdown, DOCX and EPUB"]
    end
  end
  subgraph Outputs["Outputs"]
    direction TB
    o1["A new or modified PDF file"]
    o2["SVG, PNG, JPEG, TIFF, BMP or GIF renders"]
    o3["HTML, Markdown, DOCX or EPUB export"]
  end
  StartingPoints --> PRODUCT --> Capabilities --> Outputs
```

## Key Capabilities

- Parse both classic cross-reference tables and cross-reference streams, including object
  streams (`/ObjStm`); every filter (`FlateDecode` with PNG/TIFF predictors, `LZWDecode`,
  `ASCII85Decode`, `ASCIIHexDecode`, `RunLengthDecode`) has a matching encoder. When the
  cross-reference structure is damaged, `Document.Open` falls back to scanning the file and
  reports exactly what it repaired and lost through `doc.recovery`.
- Open PDFs protected with the standard security handler — RC4, AES-128 or AES-256 — and write
  encrypted output the same way, or as an `/Adobe.PubSec` certificate envelope for RSA/EC
  recipients. Digital signatures (`doc.Sign`/`doc.Certify`) support CMS and PAdES subfilters,
  DocMDP certification, RFC 3161 timestamps, and full verification including revocation checks.
- Access and edit every page through `doc.Pages` — all five boundary boxes, rotation, resources,
  decoded content — and manipulate the page set with `AddPage`, `InsertPage`, `RemovePage`,
  `Reorder`, `Split`, `ExtractPages`, `Append` and `Document.Merge`.
- Stamp and flow text with `AddText`/`AddTextBlock` and `doc.NewFlow`, using the 12 Standard-14
  Latin fonts or an embedded TrueType/OpenType/WOFF/WOFF2 font, with optional complex-text
  shaping for bidi, Arabic and OpenType GSUB/GPOS scripts.
- Draw vector graphics with `page.Graphics()` (lines, shapes, gradients, tiling patterns) and
  embed raster images (JPEG, PNG, BMP, TIFF) or vector SVG assets — the SVG importer covers
  gradients, masks, markers, patterns, filters, `<textPath>` and a real CSS cascade.
- Build tables (`createTable`, spans, pagination, auto-fit columns) and multi-column flow
  documents (`doc.NewFlow`) with headings, lists, images and floats, including a table of
  contents (`page.AddTOC`) with dot leaders and clickable links.
- Render CommonMark/GFM Markdown or a full HTML document — parsed by a real HTML5 tokenizer and
  tree constructor, styled through a CSS cascade, and laid out as a CSS box tree — into a flow,
  a page rectangle, or a whole document with `AddMarkdown`/`AddHtml`.
- Generate 1D barcodes (Code 128, EAN-13, UPC-A, EAN-8) and QR codes as vector shapes or a 1-bit
  image mask, and impose pages into N-up sheets or a saddle-stitch booklet with `doc.NUp`/
  `doc.Booklet`.
- Extract text (`GetText`, `GetTextFragments`, `GetStructuredText`), tables (`GetTables`,
  including cross-page stitching) and vector paths (`GetPaths`) from any page, and search or
  replace text with `Search`/`ReplaceText`, including annotation-carried and annotation-drawn
  text.
- Redact content by rectangle or by text search (`Redact`/`RedactText`) — glyphs and images under
  the region are truly removed from the saved file, not merely covered — with a mark-then-apply
  workflow via `AddRedact`/`MarkRedactText`/`ApplyRedactions`.
- Create, fill and style AcroForm fields, regenerate their appearance streams so values render
  without `/NeedAppearances`, and round-trip field data through FDF/XFDF import and export.
- Read, write and search annotations (16 subtypes), outlines/bookmarks, page labels, named
  destinations, document-level JavaScript, embedded-file attachments and portfolios, and manage
  optional-content (OCG) layers including authoring, visibility resolution and layer deletion.
- Read and author tagged-PDF structure — `AutoTag` infers structure from layout, and
  `CreateStructTree` lets you author your own — then validate against PDF/UA, and validate or
  convert to PDF/A and PDF/X with a detailed, honest report of what was and wasn't fixed.
- Render a page to SVG or a raster image (PNG/JPEG/TIFF/BMP/GIF), and export a whole document to
  reflowable or fixed-layout HTML, Markdown, DOCX or EPUB — each export verified against
  browser-rendered or real-application goldens rather than the library's own output.
- Optimize a document — subset embedded fonts, recompress photographic images, prune unused
  `/AcroForm` resources — and convert pages or images to grayscale.

## Installation

@asposefoss/pdf has not yet been published to npm. Install directly from a local clone:

```bash
git clone https://github.com/aspose-pdf-foss/Aspose.PDF-FOSS-for-TypeScript.git
cd Aspose.PDF-FOSS-for-TypeScript
npm install
npm run build
```

Once published this will become `npm install @asposefoss/pdf`.

## Dependencies

### Required Package Dependencies

No required third-party package dependencies.

### Native and System Requirements

- Requires Node.js 22 or later (`engines.node` in `package.json`).

### Development Dependencies

- `@types/node` `^20.0.0` — Node.js type definitions.
- `tsx` `^4.23.1` — run TypeScript sources directly (used by the example scripts).
- `typescript` `^5.5.0` — compiler (`npm run build` / `npm run typecheck`).
- `vitest` `^2.0.0` — test runner (`npm test`).

## Quick Start

Open an existing PDF, edit its pages and metadata, and save:

```ts
import { Document } from '@asposefoss/pdf';

// Open from disk (or Document.Open(uint8array) for in-memory data)
const doc = Document.OpenFile('input.pdf');

// Inspect and edit pages
console.log(doc.Pages.length);
doc.Pages[0].Rotate = 90;
doc.RemovePage(2);                 // 1-based page number
doc.Reorder([3, 1, 2]);

// Metadata
doc.SetMetadata({ title: 'Report', author: 'Jane', custom: { Dept: 'R&D' } });

// Save
doc.WriteTo('output.pdf');         // or: const bytes = doc.Save();
doc.WriteTo('small.pdf', { compressed: true }); // xref stream + object streams
```

To generate a PDF rather than edit one, start from `Document.New` — the counterpart to
`Document.Open`. With no argument it is a zero-page document; pass a `PageFormat` for one blank
page of that size.

```ts
import { Document, PageFormat } from '@asposefoss/pdf';

const doc = Document.New(PageFormat.A4);          // one blank A4 page
doc.Pages[0].AddText('Hello', 72, 720, { fontSize: 14 });
doc.AddPage(PageFormat.A4.landscape());           // append more as you go
doc.WriteTo('scratch.pdf');
```

## Additional Examples

More real, verified snippets are collected below, each demonstrating one operation without
obscuring the primary installation and quick-start path.

<details>
<summary><strong>View Additional Examples</strong></summary>

REPLACE_ADDITIONAL_EXAMPLES

</details>

## API Reference

The public entry points are organized around `Document` and `Page` (the core object model),
`Font`/`EmbeddedFont` (text authoring), `Annotation` and `Field` (interactive content), and
per-capability builders such as `PageGraphics`, `Flow` and `Table` — 360 public types across 9
modules.

<details>
<summary>View the Full API Surface</summary>

REPLACE_CLASS_TABLE

#### Member Quick Reference

The tables below are the library's own, more granular member-by-member reference — every public
method and property grouped by the object it belongs to, each with a one-line description.

REPLACE_API_OVERVIEW

</details>

## Documentation & Resources

- **[Feature showcase](examples/feature-showcase/)** — a single document exercising every major
  capability in one narrative: text and image authoring, every AcroForm field type, sixteen
  annotation subtypes, tables, vector graphics, flow layout, tagged PDF, standards validation,
  and digital signatures.
- **[CHANGELOG.md](CHANGELOG.md)** — release history.
- **[AGENTS.md](AGENTS.md)** and **[CLAUDE.md](CLAUDE.md)** — the agent-facing development
  workflow for this repository.
- **[docs/epub-calibre-verification.md](docs/epub-calibre-verification.md)** — how EPUB export
  was hand-verified in a real reader (Calibre 7.26.0) beyond the suite's own structural
  conformance checks.
- Found a bug or have a feature request? [Open an issue](https://github.com/aspose-pdf-foss/Aspose.PDF-FOSS-for-TypeScript/issues) on GitHub.

## Scope and Limitations

REPLACE_LIMITATIONS

These limitations apply only to Aspose.PDF FOSS for TypeScript — they don't carry over to
[Aspose.PDF — Enterprise Edition](https://products.aspose.com/pdf/), which adds broader
proprietary-format support, rendering, and advanced document-processing capabilities this FOSS
build leaves unimplemented.

## Development and Testing

REPLACE_DEVELOPMENT

Design specs and implementation plans live under [docs/superpowers/](docs/superpowers/). Issue
tracking uses [beads](https://github.com/gastownhall/beads) (`bd ready`, `bd show <id>`); see
[CLAUDE.md](CLAUDE.md) for the agent workflow.

## License

This project is licensed under the [MIT License](LICENSE). The MIT License permits use, copying,
modification, distribution, sublicensing, and commercial use, provided its copyright and
permission notice are retained. The software is provided without warranty.
"""

out = HEADER
out = out.replace("REPLACE_ADDITIONAL_EXAMPLES", additional_examples_body.rstrip())
out = out.replace("REPLACE_CLASS_TABLE", class_table_body.rstrip())
out = out.replace("REPLACE_API_OVERVIEW", api_overview_body.rstrip())
out = out.replace("REPLACE_LIMITATIONS", limitations_body.rstrip())
out = out.replace("REPLACE_DEVELOPMENT", development_body.rstrip())

open(f"{D}/readme.md", "w", encoding="utf-8", newline="\n").write(out)
print("wrote", len(out), "bytes,", out.count(chr(10)) + 1, "lines")
