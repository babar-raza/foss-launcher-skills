# Aspose.PDF FOSS for TypeScript

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE) [![Node.js Version](https://img.shields.io/badge/Node.js->=22%2B-blue.svg?logo=node.js)](package.json) [![Contributors](https://img.shields.io/github/contributors/aspose-pdf-foss/Aspose.PDF-FOSS-for-TypeScript.svg)](https://github.com/aspose-pdf-foss/Aspose.PDF-FOSS-for-TypeScript/graphs/contributors)

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
    o1["A PDF file"]
    o2["SVG, PNG, JPEG, TIFF, BMP or GIF images"]
    o3["HTML, Markdown, DOCX or EPUB documents"]
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
  recipients. Digital signatures (`await doc.Sign(signer, opts?)`/`doc.Certify`) support the
  `adbe.pkcs7.detached` (CMS) and `ETSI.CAdES.detached` (PAdES) subfilters from a `.p12`/`.pfx`
  keystore, DocMDP certification, RFC 3161 timestamps (`AddDocumentTimestamp`), LTV validation
  data (`AddValidationData`, `/DSS`), and full verification (`VerifySignatures`,
  `VerifyDocumentTimestamps`) including `/ByteRange` integrity and revocation checks.
- Access and edit every page through `doc.Pages` — all five boundary boxes, rotation, resources,
  decoded content — and manipulate the page set with `AddPage`, `InsertPage`, `RemovePage`,
  `Reorder`, `Split`, `ExtractPages`, `Append` and `Document.Merge`.
- Stamp and flow text with `AddText`/`AddTextBlock` and `doc.NewFlow`, using the 12 Standard-14
  Latin fonts or an embedded TrueType/OpenType/WOFF/WOFF2 font, with optional complex-text
  shaping for bidi, Arabic and OpenType GSUB/GPOS scripts.
- Draw vector graphics with `page.Graphics()` (lines, shapes, gradients, tiling patterns) and
  embed raster images (JPEG, PNG, BMP, TIFF) or vector SVG assets with `page.AddSVGObject(data,
  [x, y, w, h], opts?)` — the SVG importer covers gradients, `/SMask`/`/S /Alpha` masks, markers,
  patterns, filters (`opts.filterScale`), `<textPath>`, a real CSS cascade, and an `opts.font`/
  `opts.resolveImage` hook for fonts and non-`data:` image references; anything it cannot draw is
  named in `result.skipped`.
- Stamp a repeating text or image watermark (`doc.AddWatermark(opts)`), fill header/footer bands
  with page/date/Bates tokens (`doc.AddHeaderFooter(opts)`), and stamp a chained Bates sequence
  (`doc.AddBatesNumbering(opts?)`) across a 1-based page range or range string (e.g.
  `'1-5,8,12-'`).
- Build tables (`createTable`, spans, pagination, auto-fit columns) and multi-column flow
  documents (`doc.NewFlow`) with headings, lists, images and floats, including a table of
  contents (`page.AddTOC`) with a leader rule and clickable links.
- Render CommonMark/GFM Markdown or a full HTML document — parsed by a real HTML5 tokenizer and
  tree constructor, styled through a CSS cascade, and laid out as a CSS box tree — into a flow,
  a page rectangle, or a whole document with `AddMarkdown`/`AddHtml`.
- Generate 1D barcodes (Code 128, EAN-13, UPC-A, EAN-8) and QR codes as vector shapes or a 1-bit
  image mask, and impose pages into N-up sheets or a saddle-stitch booklet with `doc.NUp`/
  `doc.Booklet`.
- Extract text (`GetText`, `GetTextFragments`, `GetStructuredText` — composite fonts resolved
  through their `/CIDSystemInfo` and CID-to-Unicode tables), tables (`GetTables`, including
  cross-page stitching and a `{ region }` option to constrain extraction to a page-space
  rectangle), and vector paths (`GetPaths`) from any page, and search or replace text with
  `Search`/`ReplaceText`, including annotation-carried and annotation-drawn text.
- Enumerate and edit embedded images through `page.Images`/`page.InlineImages` — `RawData`
  returns the encoded stream bytes, `img.Replace(data)` swaps the picture in place, and
  `img.Remove()` drops it from the page.
- Redact content by rectangle or by text search (`Redact`/`RedactText`) — glyphs and images under
  the region are truly removed from the saved file, not merely covered — with a mark-then-apply
  workflow via `AddRedact`/`MarkRedactText`/`ApplyRedactions`.
- Create, fill and style AcroForm fields, regenerate their appearance streams so values render
  without `/NeedAppearances`, and round-trip field data through FDF/XFDF import and export.
- Read, write and search annotations (16 subtypes), outlines/bookmarks (including `/Count`),
  page labels, named destinations, document-level JavaScript, embedded-file attachments and
  portfolios (`SetCollection`/`GetCollection`, with per-file custom values via
  `Attachment.SetField(name, value)`), and manage optional-content (OCG) layers including
  authoring, visibility resolution and layer deletion.
- Read and author tagged-PDF structure — `doc.GetStructTree()`/`doc.IsTagged`/`doc.Lang` read it
  back, `AutoTag` infers structure from layout for an untagged document, and
  `doc.CreateStructTree()`/`element.Append(...)`/`element.NextMcid(page)`/
  `PageGraphics.BeginMarkedContent` let you author your own and mark content into it — page
  operations that copy structure (`Split`, `ExtractPages`, `Append`, `Document.Merge`) carry a
  tagged source's tree along automatically unless `{ preserveStructure: false }` opts out — then
  validate against PDF/UA, and validate or convert to PDF/A and PDF/X with a detailed, honest
  report of what was and wasn't fixed.
- Render a page to SVG or a raster image (PNG/JPEG/TIFF/BMP/GIF) with a pure-TypeScript software
  rasterizer, and export a whole document to reflowable or fixed-layout HTML, Markdown, DOCX or
  EPUB — each export verified against browser-rendered or real-application goldens rather than
  the library's own output.
- Optimize a document in place with `doc.Optimize({ fonts, dedup, compress })` — it subsets
  embedded fonts, recompresses photographic images, and prunes unused `/AcroForm` resources
  losslessly, returning an `OptimizeReport` naming anything it skipped — and convert pages or
  images to grayscale.

## Installation

@asposefoss/pdf has not yet been published to npm. Install directly from a local clone — as a
local file or npm workspace dependency, build once and the same import specifier resolves:

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

- Requires Node.js 22 or later (`engines.node` in `package.json`); relies on the `node:zlib`,
  `node:crypto`, and `node:fs` built-ins.

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
<summary>View Additional Examples</summary>

### Open Encrypted PDFs

```ts
import { Document, InvalidPasswordError } from '@asposefoss/pdf';

try {
  const doc = Document.OpenFile('secret.pdf', { password: 'hunter2' });
  doc.WriteTo('decrypted.pdf');    // output is plaintext
} catch (e) {
  if (e instanceof InvalidPasswordError) console.error('wrong password');
  else throw e;
}
```

### Write Encrypted Output

```ts
const doc = Document.OpenFile('in.pdf');
doc.WriteTo('locked.pdf', {
  encrypt: {
    userPassword: 'open-me',       // required to open (default '')
    ownerPassword: 'full-rights',  // default: same as userPassword
    algorithm: 'aes256',           // 'aes256' (default) | 'aes128' | 'rc4'
    permissions: { copying: false, modifying: false },
    encryptMetadata: true,
  },
});
```

The output re-opens with either password via `Document.Open(bytes, { password })`.
Permission flags (`printing`, `modifying`, `copying`, `annotating`,
`fillingForms`, `accessibility`, `assembling`, `highQualityPrinting`) each
default to allowed. An `algorithm` other than the three names throws `TypeError`.

### Encrypt With Certificate-Based (Public-Key) Encryption

```ts
import { Document } from '@asposefoss/pdf';

// Encrypt to one or more recipient certificates (PEM string or DER bytes):
const bytes = doc.Save({
  encrypt: {
    recipients: [{ certificate: recipientCertPem }],
    algorithm: 'aes256',                 // 'aes256' (default) | 'aes128' | 'rc4'
    permissions: { copying: false },     // shared across all recipients
  },
});

// Open with the recipient's private key + certificate, or a PKCS#12 bundle:
const opened = Document.Open(bytes, {
  recipient: { privateKey, certificate: recipientCertPem },
  // or: recipient: { pkcs12: p12Bytes, passphrase: '…' },
});
console.log(opened.Permissions);         // recovered permission flags (not enforced)
```

Opening a PubSec document without a matching `recipient` throws
`InvalidPasswordError`.

### Split and Merge Documents

```ts
const parts = doc.Split();                       // one Document per page
const chapter = doc.ExtractPages([3, 4, 5]);     // subset (1-based, repeats allowed) as a new Document
const merged = Document.Merge(docA, docB, docC); // new combined Document

docA.Append(docB);                               // copy all of docB's pages onto docA
docA.InsertPage(1, docB.Pages[0]);               // copy a single page across documents
```

### Parse and Serialize Content Streams

```ts
import { parseContentStream, serializeContentStream } from '@asposefoss/pdf';

const ops = parseContentStream(doc.Pages[0].Contents);
// ops: { operator: string, operands: PdfObject[], inlineImage?: {...} }[]
for (const op of ops) {
  if (op.operator === 'Tj') console.log('text op:', op.operands);
}
const bytes = serializeContentStream(ops);       // round-trips operators + operands
```

### Stamp Text on a Page

```ts
const doc = Document.OpenFile('in.pdf');
const page = doc.Pages[0];

// Page number, right-aligned near the bottom-right corner.
const w = page.Rect[2] - page.Rect[0];
page.AddText(`Page ${page.Number}`, w - 40, 20, { fontSize: 10, align: 'right' });

// Semi-transparent diagonal watermark, centered on the page.
page.AddText('DRAFT', page.Rect[2] / 2, page.Rect[3] / 2, {
  font: 'Times-Bold', fontSize: 64, color: [0.7, 0.7, 0.7], opacity: 0.4, rotate: 45, align: 'center',
});

doc.WriteTo('out.pdf');
```

Picks any of the 12 Latin Standard-14 fonts via `font` (default `'Helvetica'`):
`Helvetica`, `Times-Roman`, `Courier` and their `-Bold`/`-Italic`/`-Oblique`/
`-BoldItalic`/`-BoldOblique` variants. Each distinct font is registered into the
page resources (with `WinAnsiEncoding`) at most once. `Symbol`/`ZapfDingbats` are
not available for authoring (no WinAnsi encoder). `MeasureText(text, fontSize?,
font?)` returns the rendered width in points using that font's metrics (handy for
your own layout math). Coordinates are PDF user space (origin bottom-left,
points); characters outside WinAnsiEncoding are dropped.

For multi-line, wrapped text, `page.AddTextBlock(text, [x, y, w, h], options)`
flows `text` into the rectangle, greedily word-wrapping to the box width and
honoring explicit newlines. Space-delimited (Latin) wrapping is unchanged, but a
token too wide for the box is now broken at its **Unicode UAX #14** line-break
opportunities, so space-less scripts (CJK) and complex scripts wrap correctly
instead of overflowing. It clips to the box height and returns the unconsumed
remainder (or `null` when everything fit, or when the text was empty / all
characters were unencodable):

```ts
const rest = page.AddTextBlock(longText, [72, 600, 200, 150], {
  font: 'Times-Roman', fontSize: 11, align: 'justify', valign: 'top', leading: 14,
});
if (rest) page.AddTextBlock(rest, [300, 600, 200, 150]); // continue into a 2nd column
```

`TextBlockOptions` adds `align` (`'left'` | `'center'` | `'right'` | `'justify'`,
default `'left'`), `valign` (`'top'` | `'center'` | `'bottom'`, default `'top'`)
and `leading` (baseline-to-baseline points, default `1.2 * fontSize`) on top of
the shared `font`/`fontSize`/`color`/`opacity`/`rotate` options. A single word
wider than the box overflows horizontally rather than being hyphenated.

`AddTextBlock` also takes a **run list** instead of a string, to mix styles
within one wrapped block:

```ts
const rest = page.AddTextBlock([
  { text: 'Regular, ' },
  { text: 'bold', font: 'Helvetica-Bold' },
  { text: ', and ' },
  { text: 'code', font: 'Courier', background: [0.95, 0.95, 0.95] },
], [50, 700, 400, 60]);
// rest is a TextRun[] (or null), so it continues into another box with its
// styles intact: if (rest) page.AddTextBlock(rest, [50, 600, 400, 60]);
```

A `TextRun` may override `font`, `fontSize`, `color`, `underline`,
`strikethrough` and `background`; anything it leaves unset comes from the block.
`align`, `valign`, `leading`, `rotate` and `opacity` describe the whole block and
stay there. A word is never broken at a style boundary — `**bold**text` wraps as
one word. `Flow.AddParagraph`, `Flow.AddHeading` and a list item's `text` take
the same run list.

Three limits. `align: 'justify'` falls back to left if any run uses an embedded
font, because justification rides on `Tw`, which only moves single-byte spaces.
Complex-text shaping (`shape: true`) is not supported with runs and throws
`UnsupportedFeatureError`. And leading is block-level, so a run whose `fontSize`
exceeds the block's advances by the block's leading and can collide with the line
above.

`rotate` turns the block counter-clockwise about the rect's origin (its
bottom-left corner), the block analogue of `AddText`'s rotation about its anchor
— a diagonal multi-word watermark, a rotated header label, a spine label. The
**box turns with the text**: wrapping, alignment and the overflow remainder are
computed in the rect as given and the laid result is rotated as a unit, so
`rotate` never changes where the lines break and `measureTextBlock` needs no
knowledge of it.

```ts
page.AddTextBlock('DRAFT — NOT FOR DISTRIBUTION', [80, 80, 400, 120], {
  fontSize: 36, align: 'center', color: [0.9, 0.2, 0.2], opacity: 0.3, rotate: 45,
});
```

#### Text decoration

Both `AddText` and `AddTextBlock` accept `underline`, `strikethrough`,
`background` and `behind`. `underline: true` and `strikethrough: true` take
their thickness and offset from the font's own metrics (the Adobe AFM values for
a Standard-14 face, the `post`/OS/2 tables of an embedded one) and the text's own
colour; pass an object to override any of `color`, `thickness` (points) or
`offset` (points from the baseline, positive up). `background` is a bare RGB
tuple, or `{ color, padding }` to inset it — the fill is text-tight (one rect per
laid line, ascender to descender) rather than box-filling. `behind: true` sinks
the whole stamp — fill, glyphs and rules — beneath the existing page content.

```ts
page.AddText('Reviewed', 72, 700, { underline: true, background: [1, 1, 0.6] });
page.AddTextBlock('Struck through', [72, 600, 200, 50], {
  strikethrough: { color: [1, 0, 0], thickness: 1.5 },
});
page.AddText('WATERMARK', 200, 400, { behind: true, opacity: 0.2 });
```

Decoration rotates and aligns with the text, and is carried through the
higher-level authoring layers: flow paragraphs and headings
(`FlowParagraphOptions`), TOC rows (`TOCOptions`, including the per-entry
`style`), and watermarks / headers / footers / Bates numbers. Table cells take
`underline` and `strikethrough` under those names but spell the text fill
**`textBackground`**, because a cell's `background` already means the fill of the
whole cell box — so a cell can carry both.

`behind` is offered on `AddText` / `AddTextBlock` only. Watermarks control
z-order with their own `mode: 'underlay' | 'overlay'`, and flow, table and TOC
content is laid into a container where sinking one element beneath the page has
no coherent meaning.

#### Embedding a font (arbitrary Unicode)

To author text beyond the Standard-14 + WinAnsi ceiling, load a TrueType/OpenType
font and pass the handle as `font`:

```ts
const font = doc.AddFont(ttfBytes);          // or doc.AddFontFile('NotoSans.ttf')
doc.Pages[0].AddText('café — 你好', 72, 700, { font, fontSize: 18 });
doc.Pages[0].AddTextBlock('日本語のテキスト …', [72, 500, 200, 150], { font });
doc.WriteTo('out.pdf');
```

A font can also be found by **family name** rather than by path. Register the
folders to search — and, if you want them, the platform's own font directories —
then ask for a family:

```ts
doc.RegisterFontFolder('./assets/fonts');
doc.RegisterSystemFonts();                       // opt-in

const font = doc.LoadFontByName('Liberation Sans');
if (font) doc.Pages[0].AddText('Hello', 72, 700, { font, fontSize: 24 });
```

Two things are deliberate. The system directories are **opt-in**, because
searching them by default lets the same code build different documents on
different machines — a face found on your laptop and missing in a container,
failing at `Save` rather than at the call. And a name nothing matches returns
**`undefined`** rather than throwing or substituting a default face: a silent
substitution would render the document in metrics and glyphs you did not
choose. Matching is on the family name, trimmed and case-insensitive.
The scan opens files with a font extension (`.ttf`, `.otf`, `.ttc`, `.otc`) and
files with **no extension at all**, since a font checked into a repo or
unpacked from an archive routinely loses one; either way the file's magic
decides. For a font stored under some other extension, `RegisterFontFolder(dir,
{ sniff: true })` widens the scan to every file in the folder — opt-in, because
pointed at a general asset folder it opens every image and blob in it, and
`RegisterSystemFonts()` never sniffs for that reason.
Folders are scanned on first use and cached, so a font file added to a
registered folder later in the same process is not picked up. A `.ttc` or
`.otc` collection is indexed face by face, so each of its families is findable
by name; `AddFont`/`AddFontFile` take one directly through `{ faceIndex }`,
defaulting to face 0.

A family can be asked for by **weight and slant**, and `family` accepts a list:

```ts
const bold = doc.LoadFontByName(['Roboto', 'Liberation Sans'], { weight: 700 });
const family = doc.LoadFontFamily('Roboto');     // { regular, bold?, italic?, boldItalic? }
doc.AddMarkdown('Plain and **bold**.', { style: { font: family } });
```

Selection follows [CSS Fonts 4 §5.2](https://www.w3.org/TR/css-fonts-4/#font-style-matching):
**slant first, then the desired-weight walk.** Two consequences are worth
stating because neither is the obvious one. Slant outranks weight, so asking a
family holding *Regular, Bold, Italic* for `{ weight: 700, italic: true }`
returns the **Italic** face rather than the Bold one. And a list is a preference
chain over **families**, not a search for the best face: the first name any
installed face belongs to wins outright and matching runs inside it, so
`['Arial', 'Liberation Sans']` at weight 700 gives Arial Regular on a machine
whose Arial ships upright only. A style detail never overrides the order you
stated.

Degradation inside a family is silent — ask for bold where only upright exists
and an upright face comes back. `doc.ResolveFontByName(family, opts)` reports
what *would* be loaded, without loading it: the family and subfamily as the font
states them, the derived weight and slant, the path and face index, and an
`exact` flag saying whether your request was met. It is the only way to find
out, since the `EmbeddedFont` handle exposes nothing about the face it holds.

`LoadFontFamily` fills the `bold`, `italic` and `boldItalic` slots only when a
face actually plays that role, leaving them absent otherwise — an absent slot
falls back to `regular`, which is what `AddMarkdown` already does with a family
that states fewer than four faces.

`AddFont(bytes)` parses the sfnt and returns an opaque `EmbeddedFont` handle;
`AddFontFile(path)` reads it from disk. Raw sfnt (`.ttf`, `.otf`) as well as
**WOFF** and **WOFF2** web fonts are accepted — WOFF's per-table zlib and WOFF2's
Brotli stream plus glyf/loca (and optional hmtx) transforms are reconstructed to
sfnt in memory, then fed through the same subset/embed pipeline. So are **Type 1**
programs (`.pfb`, `.pfa`), which are converted to OpenType-CFF on the way in.
That conversion drops the font's hinting — outlines carry none — which costs a
little stem regularity at small sizes in some viewers; everything else about the
face is preserved. A `.pfb` in a registered folder is also findable by family
name, with its `/Weight` and `/ItalicAngle` driving style matching.
Macintosh **`.dfont`** suitcases are accepted too. A suitcase holding several
faces — the usual Mac packaging for a family — exposes each of them, so
`LoadFontByName('Skia', { weight: 700 })` reaches the bold face inside one file.
Unlike every other format here a `.dfont` carries no signature bytes, so it is
recognised by its structure; a classic suitcase stored without its extension is
therefore still found. The font is
**subset and embedded once per
document at `Save`**, covering only the glyphs actually drawn across every page
(text is mapped Unicode → cmap → glyph and emitted as a Type0 / Identity-H
composite font with a `/ToUnicode` map, so the result extracts and copies back as
the original text). TrueType (`glyf`) fonts are subset and embedded as
`FontFile2`; CFF (`.otf`) fonts are subset and embedded as `FontFile3`
`/Subtype /CIDFontType0C` (a compact CID-keyed CFF whose charset carries the
CID→glyph map), falling back to whole-embedding for malformed CFF. Characters
absent from the font's cmap are dropped, matching the WinAnsi path. The same
`font`/`fontSize`/`color`/`opacity`/`align`/… options apply, and `MeasureText`
accepts the handle too — except that `AddTextBlock` `'justify'` falls back to
left alignment for embedded fonts (the `Tw` operator only affects single-byte
text).

#### Complex-text shaping (embedded OpenType fonts)

`AddText` / `AddTextBlock` can shape complex scripts when drawing with an
embedded font (`doc.AddFont(bytes, { shape: true })`, or per call `{ shape: true }`):

```ts
const font = doc.AddFont(arabicTtf, { shape: true });
doc.Pages[0].AddText('السلام عليكم', 72, 700, { font, fontSize: 18, dir: 'rtl' });
```

- Unicode **bidi/RTL** reordering (UAX #9) with `dir: 'auto' | 'ltr' | 'rtl'`.
- **Arabic** cursive joining (init/medi/fina/isol) and ligatures.
- **GSUB** substitution (ligatures, contextual alternates).
- **GPOS** kerning and mark positioning.
- Optional `script` (OpenType tag) and `language` (OpenType language-system tag)
  overrides.

Shaped, ligated, and reordered text still round-trips to the original Unicode
via `/ToUnicode` (verified by `GetText()`). Standard-14 fonts do not shape
(`shape` is ignored); an embedded font with shaping off stays byte-identical to
the 1:1 path.

### Build and Style Tables

Build a table from rows and cells, then draw it onto a page. Column widths are
fixed points or fractions of the available width, and cells can span columns and
rows.

```ts
import { Document, createTable } from '@asposefoss/pdf';

const doc = Document.Open(bytes);
const table = createTable({ font: 'Helvetica', fontSize: 10 });
table.setColumnWidths([{ fixed: 120 }, { fraction: 1 }, { fraction: 1 }]);
table.addRow(['Item', 'Qty', 'Price']);            // string[] shorthand
const row = table.addRow();
row.addCell('Widget', { font: 'Helvetica-Bold' });
row.addCell('3');
row.addCell('$4.00');

doc.Pages[0].AddTable(table, 72, 720, { width: 400 }); // top-left at (72, 720)
```

A cell spans columns with `colSpan` and rows with `rowSpan`. **Rows below a
spanning cell omit the covered cells** — the cursor skips them, as HTML does,
and there is no placeholder vocabulary:

```ts
const t = createTable({ border: { width: 0.5, color: [0, 0, 0] } });
const r0 = t.addRow();
r0.addCell('Region', { rowSpan: 2 });     // occupies column 0 of rows 0 and 1
r0.addCell('Q1');
t.addRow().addCell('Q2');                 // ONE cell: column 0 is already taken
```

A spanning cell's background, border and text box are its full span box, and it
is measured against every column and row it covers. When it needs more height
than those rows supply, the whole shortfall goes to the **last** row it covers,
so a plain cell is never floated in a box taller than its own content asked for.

A `rowSpan` group is **atomic across a page or column break**: `page.AddTable`
and `flow.AddTable` both back off to the last row at which no span is sliced. A
group by itself taller than the page draws anyway and overflows, exactly as a
single oversized row does.

`rowSpan` is clamped, silently, to two things: the table's last row (rows are
appended after `addCell`, so a caller cannot know the final count when they set
the span), and — for a cell in the repeating-header rows — the end of the header
block (a continuation reprints the header and then jumps to the body, so a span
crossing that seam would paint across a discontinuity). In a tagged table the
`/RowSpan` attribute states the **clamped** value, so the structure tree never
claims rows the table does not have.

Style the table, a row, or a cell (cell overrides row overrides table): `border`
and `outerBorder` (a `BorderInfo` `{ width, color, dash?, sides? }`), `background`
fill, `align`/`valign`, `color`, and `padding`.

`padding` cascades with everything else, as a scalar or an object of sides — a
roomier `TOTAL` row or a tight-set numeric column. Each *side* resolves through
the cascade on its own, so a cell's `{ top: 10 }` over a table's `padding: 6`
gives `{ 10, 6, 6, 6 }`; an omitted side inherits rather than collapsing to zero.
`AddTable({ cellPadding })` stands in for the table level, so a row or cell
padding still beats it.

```ts
const t = createTable({ padding: 4 });
t.addRow(['Item', 'Qty']);
t.addRow(['TOTAL', '12'], { padding: { top: 12, bottom: 12, left: 4, right: 4 } });
```

`sides` chooses which edges a border paints — `'all'` (the default), `'none'`, or
an object naming exactly the edges, so `{ bottom: true }` is a header rule and
`{ left: true }` a leading rule. Omitting it emits the same bytes as before the
option existed. Borders are stroked per cell and are not de-duplicated, so two
stacked rows with `{ top: true, bottom: true }` put two coincident rules on their
shared edge.

```ts
const t = createTable({
  border: { width: 0.5, color: [0.6, 0.6, 0.6] },   // grid line on every cell
  outerBorder: { width: 1, color: [0, 0, 0] },       // frame
  padding: 4,
});
t.addRow(['Name', 'Total'], {
  background: [0.9, 0.9, 0.9], align: 'center',
  border: { width: 1, color: [0, 0, 0], sides: { bottom: true } },  // header rule only
});
t.addRow(['Widget', '$4.00']);
doc.Pages[0].AddTable(t, 72, 720, { width: 300 });
```

A row's height is derived from its content. Pass `minHeight` to `addRow` for a
floor — a banner row or a fixed-height header band — and content that needs more
still wins. `valign` then positions each cell's content within the enlarged box,
and the taller row paginates like any other.

```ts
t.addRow(['Quarterly report'], { minHeight: 54, valign: 'center', align: 'center' });

const r = t.addRow();                 // or set it on a row built cell by cell
r.setMinHeight(54).addCell('Quarterly report', { valign: 'center' });
```

A cell can hold an image (JPEG/PNG) via `cell.setImage(bytes, opts?)`. The image
is embedded (see `AddImage`) and drawn aspect-fit to the cell box; it sizes the
row by default (`imgH * innerWidth / imgW`) unless you pass an explicit `height`.
`align`/`valign` position it in the box (defaulting to the cell's), `opacity`
fades it, and it may sit under cell text. In a tagged table (below) the image
becomes a `/Figure` under its cell carrying the `alt` you pass; `artifact: true`
instead declares it decoration, marking it as an artifact with no `/Figure`. The
two are mutually exclusive, and both are ignored when the table is drawn
untagged.

```ts
const t = createTable();
const row = t.addRow();
row.addCell('').setImage(logoPng, { height: 32, align: 'center' });
row.addCell('Acme Corp.', { valign: 'center' });
doc.Pages[0].AddTable(t, 72, 720, { width: 400 });
```

#### Multi-page tables

A table taller than the space on the page paginates. `AddTable` returns an
`AddTableResult` (`{ pages, endY, remainder?, struct? }`). By default it draws the rows
that fit above `bottomMargin` (points from the page bottom, default 0) and
returns the rest as a re-drawable `remainder`:

```ts
let page = doc.Pages[0];
let remainder: ReturnType<typeof createTable> | undefined = table;
let y = 720;
while (remainder) {
  const res = page.AddTable(remainder, 72, y, { width: 468, bottomMargin: 72 });
  remainder = res.remainder;
  if (remainder) { page = doc.AddPage().page; y = 720; }
}
```

Or let `AddTable` append pages for you with `autoPaginate: true`. Appended pages
copy the anchor page's size; `topMargin` sets where each continuation starts:

```ts
const { pages, endY } = doc.Pages[0].AddTable(table, 72, 720, {
  width: 468, autoPaginate: true, bottomMargin: 72, topMargin: 72,
});
// `pages` lists every page drawn onto; `endY` is the bottom of the last row.
```

Rows are atomic: a row that will not fit moves whole to the next page (a single
row taller than a full page is drawn anyway). Each page gets its own outer
border.

#### Tagged tables

Pass `{ tagged: true }` to emit logical structure alongside the ink: the table
becomes a `/Table` of `/TR` rows whose cells are `/TD`, or `/TH` for the
repeating-header rows (`setRepeatingRowsCount`) and for any cell built with
`{ header: 'row' | 'column' }` — `header: false` opts a cell back out, so a blank
corner cell in a header row stays a `/TD`. Cell backgrounds and borders are
marked as artifacts, and a cell image gets a `/Figure` carrying the `alt` passed
to `setImage` (or `artifact: true` for purely decorative artwork). Without
`tagged`, output is byte-identical to an untagged call.

```ts
const t = createTable({ fontSize: 10 });
t.addRow(['Name', 'Amount']);
t.addRow(['Widget', '$4.00']);
t.setRepeatingRowsCount(1);            // row 0 becomes /TH cells, Scope=Column
const { struct } = doc.Pages[0].AddTable(t, 72, 720, { width: 400, tagged: true });
```

A paginated table stays a single `/Table`: automatically in `autoPaginate` mode,
and in manual mode by passing `result.struct` back as `structParent` on the next
call. A header row reprinted on a continuation page appends another `/TR` of
`/TH` cells, in draw order — the ink genuinely exists on both pages.

### Generate a Table of Contents

`page.AddTOC(entries, [x, y, w, h], opts?)` renders a table of contents: wrapped
titles (indented by `level`), a leader rule, right-aligned page labels (defaulting
to each target page's logical `/PageLabels` label), and a borderless GoTo link
per row. Entries that do not fit come back as `result.remainder` for a follow-on
call, or pass `{ autoPaginate: true }` to append pages automatically.

```ts
const { remainder } = page.AddTOC([
  { title: 'Introduction', page: 3 },
  { title: 'Scope', page: 4, level: 2 },
  { title: 'Results', page: 12, style: { fontSize: 14 } },
], [72, 100, 450, 600], { fontSize: 12, rowGap: 4 });
```

Options: `rowGap`, `indent` (default 18), `leader` (`'dots'` | `'none'`),
`leaderGap` (default 4), `links` (default true), `view` (default `{ type:
'Fit' }`), `autoPaginate`, `tagged`, `structParent`, plus the typography of
`AddTextBlock` — everything but `align`/`valign` (a TOC row owns its own column
alignment), including `behind` to sink the whole TOC beneath the page's existing
content. Rows are atomic — a wrapped title never splits across pages, so
each entry keeps exactly one link rect. The call validates every entry before
painting anything, so a rejected `AddTOC` leaves the document byte-identical.

Pass `{ tagged: true }` to emit logical structure alongside the drawing: one
`/TOC` element with a `/TOCI` per entry (`TOCI > Reference > Link`, holding the
title and page-label marked content plus the link annotation as an OBJR),
`level` mapped onto nested `/TOC` elements, and the leader rule marked as an
`/Artifact` so a screen reader does not read it aloud. `structParent` places the
`/TOC` under an existing element; `result.struct` is that `/TOC`, and passing it
back as the next call's `structParent` keeps a manually paginated TOC a single
table of contents — the continuation also resumes the nesting depth the previous
page left open, so a subtree broken across pages stays one subtree.

Call `table.setRepeatingRowsCount(n)` to reprint the first *n* rows at the top of
every continuation page (a header that repeats). It works in both pagination
modes: with `autoPaginate: true` the header is redrawn on each appended page, and
in manual mode the returned `remainder` already carries the header rows, so
re-drawing it reprints them.

```ts
const t = createTable({ fontSize: 10 });
t.addRow(['Name', 'Amount']);        // header row
for (const r of data) t.addRow([r.name, String(r.amount)]);
t.setRepeatingRowsCount(1);          // repeat the header on every page
doc.Pages[0].AddTable(t, 72, 720, { width: 400, autoPaginate: true, bottomMargin: 72 });
```

### Build Multi-Column Flow Layouts

Flow content into multi-column pages that the library appends and paginates
automatically:

```ts
import { PageFormat } from '@asposefoss/pdf';

const flow = doc.NewFlow({
  format: PageFormat.A4.landscape(),
  columns: 2,
  columnGap: 34,
  marginLeft: 48, marginRight: 48, marginTop: 128, marginBottom: 52,
  paragraphSpacing: 7,
});

flow.AddHeading(2, 'Section title');            // 18pt Helvetica-Bold by default
flow.AddParagraph('Body text that word-wraps to the column width…',
                  { font: 'Helvetica', fontSize: 11, leading: 14, spaceAfter: 6 });
flow.AddColumnBreak();
flow.AddParagraph('This starts in the next column.');
flow.AddList(['First point', 'Second point', 'Third point']);          // bullets
flow.AddList(['Step one', 'Step two'], { ordered: true, itemSpacing: 4 }); // 1. 2.

const sidebar = doc.NewFloatingBox({
  width: 120, spacing: 6, padding: 6,
  border: { width: 1, color: [0.2, 0.2, 0.6] }, background: [0.95, 0.95, 1],
});
sidebar.AddImage(pngBytes);                       // auto aspect at content width
sidebar.AddParagraph('Figure 1. Caption.', { fontSize: 9 });
flow.AddFloatBox(sidebar, 'left');                // text wraps to its right

const quote = doc.NewFloatingBox({
  width: 340, padding: 10, spacing: 8,
  border: { width: 3, color: [0.8, 0.2, 0.2], sides: { left: true } },  // rule only
});
quote.AddParagraph('Not everything that counts can be counted.', { fontSize: 13 });
flow.AddFloatingBox(quote);                       // in the flow; nothing beside it

const pages = flow.Render(); // fresh pages appended to the document
```

`Render()` returns the pages it created. It is single-shot — call it once per
flow. Page size comes from `PageFormat` (`.A4`/`.Letter`/`.Legal`,
`PageFormat.custom(w, h)`, `.landscape()`/`.portrait()`). `AddHeading(level, …)`
takes a level 1–6 that sets a default font size (24/18/14/12/10/8) and a
Helvetica-Bold default, both overridable via the options. `AddParagraph` and
`AddHeading` accept per-element `spaceBefore`/`spaceAfter` (points, additive with
the flow's `paragraphSpacing`, dropped at a column top). By default a heading is
kept with the element after it: if the heading fits at a column bottom but the
next element cannot place even one line beneath it, the heading moves to the next
column. Set `keepHeadingsWithNext: false` on `NewFlow` to disable this flow-wide,
or `keepWithNext: false` (or `true`) on an individual `AddHeading` to override the
flow default. Passing
`tagged: true` to `NewFlow` emits logical structure (`/H1`–`/H6` for headings,
`/P` for paragraphs, `/L`/`/LI`/`/Lbl`/`/LBody` for lists, `/Figure`+`/P` for
float boxes) into the document structure tree; the default is untagged.
`AddList(items, options)` takes a string per item and draws a bullet (`bullet`,
default "•") or numbered (`ordered: true`, `start`) marker, with an auto or
explicit `indent`, `itemSpacing` between items, and list-level `spaceBefore`/
`spaceAfter`. List items may nest: pass `{ text, items: [...] }` for a sub-list —
sub-lists indent per depth, ordered numbering restarts per level, and unordered
markers cycle • ◦ ▪ by depth (drawn as vector shapes). An item's
`ordered`/`bullet`/`start` override its own sub-list. An object item may also
carry per-item style overrides — `font`, `fontSize`, `color`, `align`,
`leading`, `spaceBefore`, `spaceAfter`, `indent` — each overriding the
list-level value for that item only (its marker inherits the item's
font/size/colour). `underline`, `strikethrough` and `background` decorate the
list too, at either level (an item's `underline: false` switches the list-level
rule off). The marker and the item body are decorated as **two separate runs**,
so a rule covers the bullet or ordinal and then the body text, leaving the
gutter between them blank; a background behind a vector bullet is as tall as the
font, so it lines up with the body's. `AddImage(data, options)` places a JPEG/PNG image as its own flow
block: `width` defaults to the column width (clamped down if larger, aspect
preserved), `height` auto-derives from the aspect ratio, `align` is `'left'`
(default)/`'center'`/`'right'`, and `alt` tags the image as `/Figure` when the
flow is tagged. An image paginates atomically (it never splits; one taller than a
full column is **scaled down** to fit, aspect preserved — it used to throw).
Content that cannot be scaled and cannot fit an empty column, such as a line
of text larger than the column, is drawn past the column bottom rather than
refusing the render. Both are last resorts: an image arriving near the foot of
a column still moves to the next column at full size, so a picture's size never
depends on what precedes it. `doc.NewFloatingBox({ width, padding, border, background, spacing,
alt })` builds a box (`AddParagraph`/`AddImage`), which goes into a flow one of
two ways. `flow.AddFloatBox(box, 'left' | 'right')` floats it so surrounding text
wraps in the narrowed channel beside it and resumes full width below.
`flow.AddFloatingBox(box)` instead places it **in** the flow — a pull-quote,
callout or formula card: it consumes the vertical space it needs, excludes no
band, and nothing wraps beside it. An in-flow box keeps its own `width` (it is
neither stretched nor clamped to the column) and paginates atomically — one that
does not fit in what is left of the column moves whole to the next, since a
callout split across a column boundary reads as a fault and its border and
background have no defined way to continue. Its `spacing` applies above and
below, on top of the flow's `paragraphSpacing`, as it does for a side float.

A box `border` takes the same `sides` vocabulary as the table `BorderInfo` —
`'all'` (default), `'none'`, or an object naming the edges — so a left-rule
pull-quote is `sides: { left: true }`. The border width is reserved on every side
whichever edges are drawn, so toggling `sides` changes only the ink and never
reflows the text inside the box. A left and a right box can float at once (text
flows in the middle channel), and several boxes on the same side stack
vertically — a box never shares a side, and only sits beside an opposing box
when it still fits the remaining channel. A float never pushes the text pen
past itself, so text fills the channel beside the upper box first and widens as
each box is passed. Floats are per-column: `AddColumnBreak` (and automatic
pagination) clears them. Any element takes `clear: 'left' | 'right' | 'both'`,
which drops it below the floats on those sides before it places — clearing one
side leaves a deeper float on the other still narrowing the region. A float that
does not fit the remaining column height is carried to the top of the next
column, and the content after it keeps filling the current one.

### Draw Vector Graphics

```ts
const g = doc.Pages[0].Graphics();
g.setStrokeColor([0, 0, 1]).setLineWidth(2).rect(50, 50, 200, 100).stroke();
g.setFillColor([1, 0, 0]).circle(300, 400, 40).fill();
g.apply();                       // nothing is written until apply()
```

Operators buffer in memory and are spliced into `/Contents` on `apply()` (a
no-op if nothing was drawn, and idempotent). Coordinates are PDF user space
(origin bottom-left, points). `save()`/`restore()` map to `q`/`Q` and
`transform(a,b,c,d,e,f)` to `cm`.

Beyond `rect`/`circle`/`ellipse` and the raw `moveTo`/`lineTo`/`curveTo`/`close`,
there are `polyline(points)` and `polygon(points)` (at least two `[x, y]` pairs;
`polygon` closes the path), `roundedRect(x, y, w, h, r)` with `r` clamped to half
the shorter side, and `arc(cx, cy, r, startAngle, endAngle)`. Arc angles are in
**radians**, counter-clockwise from the +x axis as in Canvas 2D; a lower
`endAngle` sweeps clockwise, and sweeps wider than 90° are split into several
cubics. An arc joins the path already under construction with a line to its start
point, or opens a new subpath when none is open — so a corner-by-corner outline
composes without hand-rolled Béziers.

```ts
g.setLineJoin(0).setMiterLimit(2)         // clamp sharp miters (default is 10)
 .polygon([[100, 100], [160, 100], [130, 160]]).stroke();
g.roundedRect(50, 200, 200, 80, 12).fill();
g.moveTo(300, 200).arc(320, 200, 20, Math.PI, 0).close().stroke();
```

`setFillGradient` fills — and `setStrokeGradient` strokes — with an axial
(linear) `ShadingType 2` or radial `ShadingType 3` ramp:

```ts
g.setFillGradient({
  kind: 'linear',
  x1: 50, y1: 0, x2: 250, y2: 0,          // page user space
  stops: [
    { offset: 0, color: [1, 0, 0] },
    { offset: 1, color: [0, 0, 1] },
  ],
});
g.rect(50, 500, 200, 100).fill();

g.setFillGradient({
  kind: 'radial',
  cx: 150, cy: 400, r: 80,                // the ramp ends on this circle
  fx: 120, fy: 430,                       // optional focus; defaults to the centre
  stops: [
    { offset: 0, color: [1, 1, 1] },
    { offset: 1, color: [0, 0.3, 0.8] },
  ],
});
g.circle(150, 400, 80).fill();
```

```ts
g.setStrokeGradient({
  kind: 'linear',
  x1: 50, y1: 0, x2: 250, y2: 0,
  stops: [
    { offset: 0, color: [1, 0, 0] },
    { offset: 1, color: [0, 0, 1] },
  ],
});
g.setLineWidth(6).drawLine(50, 300, 250, 300).stroke();
```

A gradient stroke's ramp is pinned to page space, not to the path, so its colour
at a point depends on where that point is rather than on how far along the
outline it lies.

A radial gradient runs from its focal point out to the circle `(cx, cy, r)`; a
focus outside that circle is pulled onto it, as SVG does. Gradient coordinates
are in the page's **default** user space and are not affected by `transform()` —
a PDF pattern matrix is relative to the content stream's default space, not the
CTM. `extend` (default `[true, true]`) pads the ramp beyond its endpoints, and a
uniform stop `opacity` folds into the graphics state — on that gradient's own
channel alone (`ca` for a fill, `CA` for a stroke), so a translucent gradient
stroke does not fade the fill of the same path. A gradient with one stop, a
zero-length axis, or a zero radius is drawn as a solid colour. Stops with
*differing* `opacity` are exact too, rendered through a luminosity `/SMask` — a
grayscale twin of the shading inside a transparency group, the same construct the
SVG importer uses. Both alpha forms **override** an earlier `setOpacity()` in
their channel rather than multiplying with it, and like every graphics-state
setting the mask stays in force until a `restore()`, so wrap the paint in
`save()`/`restore()` if later drawing must be unmasked.

A soft mask has no channel split — one `/ExtGState` holds one `/SMask` and it
dims both paints. So a varying-alpha fill gradient and a varying-alpha stroke
gradient cannot be in force at once: setting the second throws
`UnsupportedFeatureError`. Paint the fill and the stroke as two operations.

A **tiling pattern** repeats a tile of vector content across whatever you fill
or stroke. Create it once on the document — it is page-independent, so the same
hatch on forty pages is one object — and use it from any page's builder:

```ts
const hatch = doc.NewTilingPattern(20, 20, (t) => {
  t.setLineWidth(1).setStrokeColor([0.2, 0.2, 0.6])
   .drawLine(0, 0, 20, 20).stroke();
}, { rotation: 45 });

const g = doc.Pages[0].Graphics();
g.setFillPattern(hatch).drawRect(72, 600, 200, 100).fill();
g.apply();
```

Options are `{ xStep, yStep, x, y, rotation, uncolored }`. The steps default to
the tile's size — larger leaves gaps between cells, smaller makes them overlap.
`x`, `y` and `rotation` (degrees counter-clockwise) place the lattice.

Like a gradient, the lattice is pinned to the page's **default** user space and
ignores the CTM, so a `transform()` before the fill moves the shape and not the
tiling; that is what `x`/`y`/`rotation` are for. Tile content is clipped to the
tile box, so content that should overhang needs a larger tile with smaller steps.

With `{ uncolored: true }` the tile carries shape only and the colour is given
where the pattern is used, so one hatch serves every colour:

```ts
const dots = doc.NewTilingPattern(8, 8, (t) => {
  t.circle(4, 4, 2).fill();
}, { uncolored: true });

g.setFillPattern(dots, [0.8, 0.1, 0.1]).drawRect(72, 500, 200, 60).fill();
```

Colour operators inside an uncolored tile throw, since a viewer ignores them.
The tile callback receives a `VectorGraphics` — every drawing primitive above,
minus `apply()`, which a tile has nothing to commit to.

A **template** is a piece of content drawn once and placed many times, stored as
a single Form XObject however often it is used — a letterhead, a logo block, a
badge. `doc.NewTemplate(w, h)` hands back a template whose `page` is an ordinary
page in template space that simply is not in the document's page tree, so every
authoring API works on it:

```ts
const tpl = doc.NewTemplate(200, 80);
tpl.page.AddImage(logoPng, [8, 8, 48, 48]);
tpl.page.AddText('ACME Corp.', 64, 30, { fontSize: 18 });
tpl.page.Graphics().drawLine(8, 4, 192, 4).stroke().apply();

for (const p of doc.Pages) tpl.PlaceOn(p, [40, 700, 200, 80]);
```

`PlaceOn(page, [x, y, w, h], opts?)` takes `fit` (`'stretch'`, the default,
fills the rect exactly; `'contain'` scales uniformly and centres), `opacity`,
`rotation` (degrees counter-clockwise about the rect's origin, as `AddText`
takes), and the `tag`/`alt`/`artifact` marking options `AddBarcode` and
`AddSVGObject` take — so a placed template can be tagged or artifacted in a
tagged document.

The first `PlaceOn` builds the form and **freezes** the template: drawing into
`tpl.page` afterwards throws, since every placement must show the same content.
Build a second template if you need a variant. A template never drawn into is
refused rather than placed, and one never placed costs nothing in the saved
file.

Logical structure *inside* a template is not supported — `MarkContent` and a
`tag:` on the template's own page would reference a page that is never written.
Tag the placement instead.

### Insert Images

```ts
import { readFileSync } from 'node:fs';

const png = new Uint8Array(readFileSync('logo.png'));
doc.Pages[0].AddImage(png, [40, 700, 120, 60]);          // x, y, w, h in points
doc.Pages[0].AddImage(png, [40, 700, 120, 60], { opacity: 0.5 });
```

JPEG bytes are stored verbatim (`DCTDecode`); PNG is decoded with `node:zlib`
and re-stored as `FlateDecode`, expanding palettes to `/Indexed` and splitting an
alpha channel into an `/SMask`. CMYK JPEG and interlaced PNG throw
`UnsupportedFeatureError`.

### Generate Barcodes and QR Codes

Generate 1D (Code128, EAN-13, UPC-A, EAN-8) and 2D (QR) barcodes and place them
on a page as crisp vector graphics (default) or a 1-bit `/ImageMask` stencil:

```ts
page.AddBarcode({ type: 'qr', data: 'https://example.com', ecc: 'M' }, [x, y, 120, 120]);
page.AddBarcode({ type: 'ean13', data: '5901234123457' }, [x, y, 160, 70]);   // check digit auto
page.AddBarcode({ type: 'code128', data: 'ABC-123' }, [x, y, 200, 60], { render: 'raster' });
```

Options: `render: 'vector' | 'raster'`, `color`, `quietZone`, `text` (human-readable
digits under 1D codes — on by default for EAN/UPC), and `layer`/`tag`. QR supports
all four ECC levels (`L`/`M`/`Q`/`H`) with automatic mode selection and version
sizing (1–40). The low-level generators (`makeCode128`, `makeEan13`, `makeUpcA`,
`makeEan8`, `makeQr`) return a module model for custom placement.

Code128 auto-selects code sets A/B/C, so the full ASCII range (0x00–0x7F),
including control characters used by GS1-128, encodes. Generation only — barcode
**recognition/decoding** is out of scope.

### Manage Optional-Content Layers

`doc.OptionalContent` enumerates and toggles existing layers; it also creates new
ones and tags authored content into them:

```ts
const oc = doc.OptionalContent;
const group = oc.AddLayer('Annotations');               // group heading
const notes = oc.AddLayer('Notes', { parent: group });  // nested, shows in the panel tree
const draft = oc.AddLayer('Draft', { visible: false }); // hidden in the default config

// Tag vector content into a layer
const g = doc.Pages[0].Graphics();
g.BeginLayer(notes).setFillColor([1, 0, 0]).rect(72, 72, 100, 40).fill().EndLayer();
g.apply();

// Tag a whole image or annotation into a layer
doc.Pages[0].AddImage(pngBytes, [0, 0, 200, 120], { layer: draft });
const stamp = doc.Pages[0].AddStamp({ rect: [10, 10, 60, 40], name: 'Approved' });
stamp.Layer = notes;
```

`AddLayer` appends the new group to `/OCProperties /OCGs` and the default config's
`/D /Order` (nested under `parent` when given); `visible: false` adds it to the
config's `/OFF`. `BeginLayer`/`EndLayer` emit `/OC /… BDC … EMC` and register the
group in the page's `/Resources /Properties`. Image and annotation membership is
set on the object's `/OC`. All of it round-trips through `Save()`.

### Extract Text

```ts
const doc = Document.Open(bytes);
console.log(doc.Pages[0].GetText());   // visible text, with word/line breaks
```

Decodes simple-font encodings (WinAnsi/MacRoman/Standard/PDFDoc + `/Differences`),
`/ToUnicode` CMaps, and composite (Type0) fonts, whose `/Encoding` resolves through
an embedded CMap stream or one of the 195 bundled predefined Adobe CMaps (including
`usecmap` chains); with no `/ToUnicode`, CIDs resolve to characters through Adobe's
table for the collection `/CIDSystemInfo` names. Spacing and line breaks are
heuristic: glyph advances come from embedded width tables (`/Widths`, CID
`/W`/`/DW`) when present, and from the Adobe AFM metrics for a Standard-14 font
that omits `/Widths` (as the spec allows and this library's own stamping does),
falling back to a per-em estimate only for a glyph neither source covers;
vertical writing modes are out of scope. Image-only pages return `""`.

For positioned output, `GetTextFragments()` returns the page's text as
`TextFragment[]` instead of a flat string — each fragment is a run of consecutive
glyphs sharing one font, size, and baseline, carrying its page-space `quad`
(`[x0, y0, x1, y1]`), `fontSize`, and `fontName` (the `/BaseFont`):

```ts
for (const f of doc.Pages[0].GetTextFragments()) {
  console.log(f.text, f.fontSize, f.fontName, f.quad);
}
```

Fragments are emitted in content order; a new fragment begins when the font,
size, or baseline changes, or a wide horizontal gap opens. Image-only pages
return `[]`.

`GetStructuredText()` goes one step further, assembling those fragments into a
`TextBlock[]` tree — fragments grouped into lines by baseline, lines grouped into
paragraph-like blocks by vertical gap and left-edge alignment, ordered
top-to-bottom. Each block and line carries its joined `text` and page-space
`quad`:

```ts
for (const block of doc.Pages[0].GetStructuredText()) {
  console.log(block.quad, block.text);
  for (const line of block.lines) console.log(' ', line.text);
}
```

### Extract Vector Paths

```ts
const doc = Document.Open(bytes);
for (const p of doc.Pages[0].GetPaths()) {
  console.log(p.fill?.rgb, p.fill?.space, p.fillRule, p.bbox);
  for (const sp of p.subpaths)
    for (const seg of sp.segments) console.log(seg.op, seg);
}
```

Each `PagePath` describes one paint operation. Geometry is kept **raw**, in the
local user space of the content stream that drew it, alongside the `ctm` that
maps that space to device (page) coordinates — multiply a point by `ctm` (or read
the precomputed device-space `bbox`) to place it on the page. Segments are
uniform: `{op:'move'|'line', pt}` or `{op:'cubic', c1, c2, pt}` (a `re` rectangle
becomes a closed move+3×line subpath; `v`/`y` become full cubics). `fill` and
`stroke` are each `{rgb, space}` or `null` — `rgb` is resolved sRGB (0–255)
through the page's colorspaces (Device\*, ICCBased, Indexed, Separation, DeviceN,
Lab), and `space` names the family. `fillRule` is `'nonzero'`/`'evenodd'`,
`lineWidth` is in device units (0 when not stroked), and `clip` flags a path used
as a clip (`W`/`W*`). Paths inside Form XObjects are included, with `addr.path`
naming the XObject chain and `mcid`/`artifact` reflecting the marked-content scope.
Shadings/gradients are not evaluated (reported as `space:'Pattern'`); dash, cap,
and join are out of scope.

### Search Text

```ts
const doc = Document.Open(bytes);
for (const m of doc.Pages[0].Search('Invoice')) {
  console.log(m.text, m.quads);   // matched text + one [x0,y0,x1,y1] box per line
}
doc.Pages[0].Search(/\d{4}-\d{2}-\d{2}/);   // a RegExp is always applied globally
```

`Search` locates a literal string or `RegExp` over the same word/line assembly
as `GetText` (so matches can span inferred spaces and line breaks). Each match
carries the matched substring, one page-space quad per line it spans, and the
underlying glyph events (`hits`) with op provenance.

`Search` walks page content streams only, so it does not see the text an
**annotation** draws — a `/FreeText`'s visible words, or a filled form field's
value, both of which live in the annotation's `/AP` appearance stream.
`page.SearchAnnotations(find, options?)` searches exactly that:

```ts
for (const m of doc.Pages[0].SearchAnnotations('confidential')) {
  console.log(m.annot.Subtype, m.text, m.quads);
}
```

Results come back in `/Annots` order, reading order within each annotation, and
each annotation is assembled on its own — a query never matches across two
annotations, or across an annotation and the page text underneath it. Only
annotations a static render would draw are searched (not Hidden, not NoView,
not a `/Popup`), the same rule `ToImage`, `ToSvg` and `FlattenAnnotations` use.
`options.region` scopes it by the same centroid rule as `Search`.

Unlike `Search`, an `AnnotationMatch` carries no glyph `hits`: an appearance
stream is not addressable by the content-edit layer, so there is nothing a
caller could act on — which is also why `ReplaceText` has no annotation
counterpart. To redact what `SearchAnnotations` finds, pass the quads to
`Redact`:

```ts
const hits = page.SearchAnnotations('confidential');
page.Redact(hits.flatMap((m) => m.quads));
```

That removes any annotation whose `/Rect` those rects intersect — the whole
annotation, which is the only granularity available without surgery on the
`/AP` stream.

An annotation also **carries** text it never draws: a note's body (`/Contents`),
its author (`/T`), its subject (`/Subj`) and its rich content (`/RC`).
`page.SearchAnnotationText(find)` searches those. `/RC` holds an XHTML fragment
rather than a string, so it is reduced to plain text first — a line break
between block elements, so `<p>a</p><p>b</p>` never matches a query for `ab` —
and a fragment that will not parse contributes nothing rather than throwing.
The same reducer is exported as `richTextToPlain`, and a text field exposes
`RichTextPlain` beside the raw `RichTextValue`, which still returns markup
because FDF/XFDF round-trips it verbatim:

```ts
for (const m of doc.Pages[0].SearchAnnotationText('Lovelace')) {
  console.log(m.key, m.value);       // 'T'  'Ada Lovelace'
}
```

Each match names the entry it came from and carries that entry's whole value.
Three deliberate differences from `SearchAnnotations`, all of which read like
inconsistencies until you know why:

- It searches **every** annotation, hidden ones included. `SearchAnnotations`
  reports what a render *draws*; this reports what the file *carries*, and a
  hidden annotation's text is still in the bytes — and is still what `Redact`
  removes.
- It carries **no geometry**. This text is never drawn, so the only box
  available would be the annotation's whole `/Rect`, and redacting that covers
  whatever innocent content sits under it. Read `annot.Rect` yourself if you
  want it.
- It takes **no options**, including no `region` — scoping could only mean that
  same `/Rect`.

`/RC` (markup rich content) is not searched: it holds an XHTML fragment, and
reducing that to searchable plain text needs a rule this does not yet have.

### Replace Text

```ts
const doc = Document.Open(bytes);
const n = doc.Pages[0].ReplaceText('Draft', 'Final');   // one page -> count replaced
doc.ReplaceText(/\bv1\b/, 'v2');                         // every page, RegExp ok
```

`ReplaceText` substitutes matched text in place, re-encoding the replacement in
the matched glyphs' **same font and encoding** and rewriting the content stream.
There is **no layout reflow**: positioning operators are preserved, so a wider
replacement may overlap following text and a narrower one may leave a gap. A
Type0/composite font, or a replacement character not representable in the font's
encoding, throws `UnsupportedFeatureError`.

### Redact Content

```ts
const doc = Document.Open(bytes);
// Remove all text/images under two regions on page 1 and mark them.
doc.Pages[0].Redact([[72, 700, 300, 720], [72, 640, 300, 660]]);
// Convenience by page number (1-based), with a custom marker colour, plus a
// document-metadata scrub:
doc.Redact(1, [[72, 700, 300, 720]], { color: [1, 0, 0], scrubMetadata: true });
fs.writeFileSync('redacted.pdf', doc.Save());
```

Each rectangle is `[x0, y0, x1, y1]` in PDF user space. Covered glyphs are
removed from the content stream (partial show operators are split so surviving
glyphs keep their positions), fully-covered images are deleted, and the fonts/
XObjects they orphan are pruned so `Save()`'s mark-sweep drops them — the removed
content is not recoverable from the file. Text drawn through a shared Form
XObject is redacted via copy-on-write, leaving other pages untouched. An image
only *partially* covered by a region is decoded, the covered pixels destroyed,
and the image re-encoded under a fresh copy-on-write XObject, so only the covered
area is lost. Partial redaction requires a decodable codec; a rotated or skewed
placement is supported (the covered device region is mapped into the image and its
pixel polygon filled). Images whose samples decode in their own colorspace
(`FlateDecode`/`LZWDecode`/`CCITTFaxDecode` — DeviceGray/RGB/CMYK, ICC, Indexed,
or DeviceN, at 1/2/4/8/16 bpc) are blanked at sample level and keep their original
colorspace and bit-depth, leaving uncovered pixels byte-identical. Baseline,
progressive, arithmetic-coded, lossless, and hierarchical JPEG (`DCTDecode`)
images — Huffman DCT (SOF0/1/2), QM arithmetic DCT (SOF9/10), predictive lossless
(SOF3 Huffman / SOF11 arithmetic), and multi-frame differential/hierarchical
(SOF5-7/13-15 + DHP/EXP), at 8- or 12-bit sample precision — and any
image carrying an `/SMask` or
`/Mask`, are decoded to RGBA, blanked, and re-encoded as DeviceRGB instead (a
DCT-encoded `/SMask` soft mask is decoded so its alpha is
preserved). A JPEG 2000 (`JPXDecode`) or JBIG2 (`JBIG2Decode`) image can't be
re-encoded, so a covered one throws `UnsupportedFeatureError`.
Inline images (`BI…ID…EI`) are redacted the same way, re-encoded in place within
the content stream with the same codec and colorspace support as image XObjects.
An inline `/ImageMask` stencil is handled directly: its covered stencil bits are
blanked to the non-marking value (honoring `/Decode`) and it is re-emitted as an
inline image mask, so only the covered pixels are cleared. A non-mask inline image
that decodes with an alpha channel still throws `UnsupportedFeatureError`, since
transparency cannot be represented inline. A malformed rectangle throws `TypeError`.

#### Mark, then apply

`Redact` destroys immediately. A `/Redact` annotation instead *marks* a region
and carries the overlay to paint later, so marks can be reviewed, saved, and
handed to another tool before anyone commits to destroying anything.

```ts
// Mark — nothing is removed yet, and the text is still extractable.
page.AddRedact({ rect: [72, 700, 300, 720], overlayText: 'REDACTED' });
page.MarkRedactText(/\d{4}-\d{4}-\d{4}-\d{4}/, { overlayText: 'REDACTED' });

// Apply — now the content is destroyed and the overlay painted.
const n = doc.ApplyRedactions();
```

**A mark is not a redaction.** Until `ApplyRedactions` runs, the marked content
is still in the file and still extractable — `page.GetText()` will return it. The
appearance `AddRedact` installs reflects that: it strokes each quad's outline in
the mark colour (`color`, default red) and fills nothing, so a document saved
with marks unapplied never *looks* redacted.

`AddRedact` takes either `rect` or `quads` (exactly one), plus `fill` (`/IC`, the
colour painted on apply, default black), `overlayText`, `repeat` (tile the text),
`align` (`/Q`), `fontSize` and `textColor` (`/DA`), and the usual `contents`,
`author`, `opacity` and `popup`. `MarkRedactText(find, opts?)` takes the same
options minus the geometry and adds one mark per search hit, returning the count.

`ApplyRedactions(opts?)` routes every mark on the page through the same
destructive pipeline as `Redact`, paints each mark's overlay, then removes the
marks — returning how many were applied. It accepts `scrubMetadata` and
`keepAnnotations`. If a mark
carries an `/RO` overlay form (which we read but never author), that form is
drawn instead of the `/IC` fill and overlay text, per §12.5.6.23's precedence.
A page with no marks is left untouched and returns `0`. If the destructive pass
throws — an undecodable partially-covered image — nothing is committed and the
marks stay in place, so the call can be retried.

Redaction also removes annotations covering the region. Any annotation whose
`/Rect` intersects a redacted rect is removed — its text would otherwise survive
in the file, and an annotation with an appearance would keep drawing it over the
marker box, since annotations composite on top of page content. A covered form
field is removed whole (value included), so a radio group with one widget in the
region loses the group. Pass `keepAnnotations: true` to opt out, remembering that
doing so preserves exactly the text the redaction was meant to destroy.

In a tagged document the overlay is tagged too: the marker box is wrapped as an
`/Artifact` (it is decoration) and the overlay text becomes a `/P` element, so a
screen-reader user is told the region was redacted rather than meeting a silent
gap. An untagged document is unaffected.

### Flatten Annotations and Forms

```ts
const doc = Document.Open(bytes);
doc.Pages[0].FlattenAnnotations(); // bake one page's annotations into its content
doc.FlattenAnnotations();          // every page; returns the count flattened
doc.FlattenForm();                 // fields -> static content, drop the AcroForm
fs.writeFileSync('flat.pdf', doc.Save());
```

To bake *some* of a document rather than all of it, flatten the object itself.
`field.Flatten()` bakes one field's widgets and unwires the field from
`/AcroForm /Fields`, leaving every sibling field interactive;
`annotation.Flatten()` bakes a single annotation. Both return whether (or how
much) they baked.

```ts
doc.Form.Get('signature')!.Flatten();   // this field only; the rest stay fillable
doc.Pages[0].Annotations[0].Flatten();  // one annotation
```

Unwiring the field is the point, not a detail: baking a widget's ink while
leaving its field in `/AcroForm /Fields` produces a field that still carries a
value and has no widget anywhere. `annotation.Flatten()` therefore unwires the
field too when the annotation it bakes is a widget.

Flattening bakes each annotation's `/AP /N` appearance into the page content as a
Form XObject draw placed onto its `/Rect` (the standard BBox→Matrix→Rect mapping),
then removes the now-static object. `FlattenAnnotations` drops the baked entries
from `/Annots`; `FlattenForm` first generates every field's appearance, bakes the
widget annotations, and removes the document `/AcroForm`, so the form is no longer
interactive. Hidden / NoView annotations and any without a usable appearance are
left untouched, matching what a viewer would paint. `/Popup` note windows are
never baked either — a viewer only draws one while its note is open — and a popup
whose parent markup *was* baked is dropped from `/Annots`, since the note it
belonged to is now static content. State-bearing appearances (checkbox/radio) bake
the widget's current `/AS` state. Transparency/blend-mode fidelity is best-effort.

### Create and Fill AcroForm Fields

```ts
const form = doc.Form;                  // rebuilt from the live catalog on each access — cache it
for (const f of form.Fields) console.log(f.FullName, f.Type, f.Value);

form.Get('user.name')!.Value = 'Oleg';  // text — regenerates the /AP appearance
form.Get('agree')!.Value = true;        // checkbox — flips /V + /AS
form.Get('color')!.Value = 'Red';       // radio group (validated against widget states)
form.Get('size')!.Value = 'L';          // choice (validated against /Opt)
form.GenerateAppearances();             // (re)build every field's /AP, drop /NeedAppearances
doc.WriteTo('filled.pdf');
```

Setting a field value regenerates that field's **appearance stream** (`/AP /N`),
so the filled value renders in every viewer without relying on
`/NeedAppearances`. Text fields honor `/DA` (font, size, color), `/Q` alignment,
multi-line wrapping, comb cells, and `/MK` border/background; choice fields draw
the selected option(s); checkbox/radio reuse the widgets' existing appearance
states (and synthesize a ZapfDingbats mark when none exist). `Form.GenerateAppearances()`
rebuilds all fields and clears the global flag; `Field.GenerateAppearance()`
rebuilds one. Layout uses Standard-14 (AFM) metrics; non-standard or embedded
`/DA` fonts are measured with Helvetica as an approximation.

Fields can also be **created**. The widget lands on the named page, and a dotted
name creates (or reuses) the intermediate field nodes:

```ts
const field = doc.Form.AddTextField({
  page: 1,
  rect: [72, 700, 272, 722],
  name: 'address.city',   // FullName; '.' separates hierarchy levels
  value: 'Prague',
  font: 'Helvetica',      // Standard-14 face for /DA; default Helvetica
  fontSize: 0,            // 0 (default) auto-sizes to the box
  textColor: [0, 0, 0],
  required: true,         // /Ff bits; readOnly likewise
  multiline: true,        // wrap across lines
  maxLen: 200,            // /MaxLen; 0 or absent means unlimited
});

// Equivalently, from the page:
doc.Pages[0].AddTextField({ rect: [72, 660, 272, 682], name: 'address.zip' });

// Flags are also live on any text field, including one read from a file:
const f = doc.Form.Get('address.city') as TextField;
f.Multiline = false;
f.MaxLen = 9;
f.Comb = true;            // MaxLen evenly spaced cells
f.Password = true;        // appearance shows bullets, never the value
f.FileSelect = true;      // the value is a file pathname to submit
f.RichText = true;        // the value is rich text, carried in /RV
f.RichTextValue = '<body><p><b>bold</b></p></body>';
f.DoNotSpellCheck = true; // the viewer skips spell-checking this field
f.DoNotScroll = true;     // the field refuses text past what its box holds
```

`/AcroForm`, its `/DR` font resource and any missing field nodes are created on
demand. The appearance stream is generated at creation, so the field renders
without relying on `/NeedAppearances`, which is never set. A rejected call — a
malformed name, an out-of-range page, a duplicate name, or a name routed through
an existing terminal field — throws and leaves the document unmodified.

A **password** field's appearance shows one bullet per character — the value
never reaches the content stream, including when `GenerateAppearances()` or
`FlattenForm()` regenerates it. **Comb** requires `MaxLen > 0` and cannot be
combined with `multiline`, `password` or `fileSelect`; each forbidden pairing
throws rather than silently rendering as something else.

A **rich text** field carries its markup in `/RV` and its plain-text equivalent
in `/V`. `RichTextValue` reads either shape a producer may have written (a
string or a stream) and writes the string form; it requires the `RichText` flag,
since `/RV` without it is a payload every viewer ignores. The generated
appearance draws the plain `/V` — nothing here renders markup.

**DoNotSpellCheck** and **DoNotScroll** are editing hints for the viewer, set at
creation (`doNotSpellCheck`, `doNotScroll`) or live on the field. Neither
affects the appearance we generate, which draws the value it is given either
way.

Every field type takes **additional actions** (`/AA`), the form-scripting
triggers, at creation or afterwards:

```ts
const amount = doc.Form.AddTextField({
  page: 1, rect: [72, 600, 272, 622], name: 'amount',
  actions: { format: { type: 'javascript', script: 'AFNumber_Format(2,0,0,0,"$",true);' } },
});

amount.SetActions({
  validate: { type: 'javascript', script: 'AFRange_Validate(true,0,true,1e6);' },
  format: null,                    // remove that trigger; absent keys are kept
});
amount.Actions.validate;           // read them back
```

The four triggers are `keystroke` (`/K`), `format` (`/F`), `validate` (`/V`) and
`calculate` (`/C`). `SetActions` merges, like `SetStyle`: an absent key is left
alone and `null` removes that trigger. Only those four keys are touched — a
created field is a merged field/widget dictionary, so its `/AA` also holds the
annotation's own triggers, and `/AA` is removed only once nothing is left in it.
This is distinct from `ButtonField.Action` (`/A`), which is what *activating* a
push button does; a button has both.

Checkboxes and radio groups are created the same way. A radio group's buttons
each carry their own page, so one group may span pages:

```ts
const agree = doc.Form.AddCheckbox({
  page: 1, rect: [72, 700, 88, 716], name: 'agree',
  exportValue: 'On',   // the /AP on-state name and the export value; default 'Yes'
  checked: true,
});

const color = doc.Form.AddRadioGroup({
  name: 'color',
  selected: 'green',
  options: [
    { page: 1, rect: [72, 660, 88, 676], export: 'red' },
    { page: 1, rect: [72, 640, 88, 656], export: 'green' },
    { page: 2, rect: [72, 660, 88, 676], export: 'blue' },
  ],
});
color.Options;   // ['red', 'green', 'blue']
color.Value;     // 'green'
color.Value = 'red';
```

Both get real `/AP` appearance states at creation — a ZapfDingbats check or
filled circle — keyed by the export value you chose. `'Off'` is reserved for
the unselected state and is rejected as an export value. There is no
`page.AddRadioGroup`, since a group is not bound to a single page.

Choice fields carry an option list. An option is a bare string when its export
value and displayed text are the same, or `{ export, display }` when they
differ:

```ts
const size = doc.Form.AddComboBox({
  page: 1, rect: [72, 600, 272, 620], name: 'size',
  options: ['Small', 'Medium', 'Large'],
  value: 'Medium',
  editable: true,          // the user may type a value outside the list
});

const country = doc.Form.AddListBox({
  page: 1, rect: [72, 500, 272, 580], name: 'country',
  options: [
    { export: 'us', display: 'United States' },
    { export: 'gb', display: 'United Kingdom' },
  ],
  multiSelect: true,
  value: ['us', 'gb'],
});
country.Options;   // ['us', 'gb'] — the export values
country.Value;     // ['us', 'gb']
```

`/V` holds the **export** value, and the generated appearance draws the
**display** text. `Editable` applies only to a combo box and `MultiSelect` only
to a list box; setting either on the wrong type throws.

The list can be changed afterwards:

```ts
country.AddOption({ export: 'fr', display: 'France' });  // appended
country.RemoveOption('gb');                              // by export value
country.Options;   // ['us', 'fr']
country.Value;     // ['us'] — 'gb' was selected, so it was dropped too
```

`AddOption` rejects an export already in the list. `RemoveOption` matches on the
export half only — that is the identity `/V` carries — and rejects a value that
is not there. Removing an option keeps the rest of the field consistent: it is
dropped from the selection, `/I` is renumbered around the gap, and the
first-visible index is pulled back inside the shortened list. Free text on an
editable combo is left alone, since it never named an option.

Push buttons have no value — they carry an appearance and an action:

```ts
const submit = doc.Form.AddPushButton({
  page: 1, rect: [72, 400, 172, 428], name: 'submit',
  caption: 'Submit',
  rolloverCaption: 'Send it',      // shown while hovered
  downCaption: 'Sending…',         // shown while pressed
  icon: pngOrJpegBytes,            // optional
  iconPosition: 'icon-above-caption',
  action: {
    type: 'submit',
    url: 'https://example.com/post',
    format: 'fdf',                 // or 'html' | 'xfdf' | 'pdf'
    fields: ['name', 'email'],     // omit to submit every field
  },
});
submit.Action;                     // read it back
submit.Action = { type: 'reset' }; // or undefined to clear
```

Three appearance streams are generated — `/N`, `/R` (hover) and `/D` (pressed,
on a darkened face) — so the button reacts in any viewer. `iconPosition` covers
all seven layouts PDF 32000-1 table 189 defines; each name says where the
**icon** goes relative to the caption:

| `iconPosition` | `/MK /TP` | Layout |
|---|---|---|
| `'caption-only'` | 0 | caption fills the box; no icon |
| `'icon-only'` | 1 | icon fills the box; no caption |
| `'icon-above-caption'` | 2 | caption in a strip along the bottom |
| `'icon-below-caption'` | 3 | caption in a strip along the top |
| `'icon-left-of-caption'` | 4 | icon in a column on the left |
| `'icon-right-of-caption'` | 5 | icon in a column on the right |
| `'caption-over-icon'` | 6 | icon fills the box, caption centred over it |

The icon is drawn into all three streams, aspect-fit and centred, and is also
published as the widget's `/MK /I` form XObject with an `/IF` fit dictionary, so
a viewer that regenerates the face draws the same thing.

The same action model drives link annotations, so a link may carry any of
`goto`, `uri`, `submit`, `reset` or `javascript`:

```ts
page.AddLink({ rect: [10, 10, 110, 30], action: { type: 'javascript', script: 'app.alert(1)' } });
```

A field can also be **removed**, by full name or by handle:

```ts
doc.Form.RemoveField('address.city');   // true when it removed something
doc.Form.RemoveField(field);            // a handle works too
```

Removal unwires the field from `/AcroForm /Fields` (or its parent's `/Kids`),
drops its widgets from every page they sit on, and prunes intermediate nodes it
leaves empty — removing the last child of `address` removes `address` as well.
It returns `false` and changes nothing for a name that is not there or a handle
whose field is already gone, so it is safe to call twice. The objects themselves
go at the next `Save()`, which writes only what is still reachable.

In a tagged document, removal also unwires the widget from the logical structure
tree — the `/OBJR` kid that names it, its `/ParentTree` slot, and any structure
element the removal leaves with no kids at all. `page.RemoveAnnotation` does the
same for a tagged annotation. Without it the `/OBJR` reference, which hangs off
`/StructTreeRoot` and so is reachable from `/Root`, would keep the removed
annotation in the saved bytes with no `/Annots` entry pointing at it.

Creation, removal, filling and `ImportFdf`/`ImportXfdf` all edit the **AcroForm**
half of a form and nothing else. An `/AcroForm /XFA` packet is never parsed or
rewritten, so in a **hybrid XFA** document it keeps describing the field set it
was authored with: an XFA-aware viewer (Acrobat prefers the packet whenever one
is present) still shows the old fields and values, while every other viewer
reads the AcroForm and sees the edit. Such a document is edited rather than
rejected, because its AcroForm half is usually perfectly editable. To make the
AcroForm authoritative, delete `/XFA` from the `/AcroForm` dictionary and clear
the catalog's `/NeedsRendering` (both reachable through `doc.catalog()`) before
editing.

#### Field styling

Every creation entry point takes the same styling keys, and `Field.SetStyle`
applies them to a field that is already in the document:

```ts
// Style at creation.
doc.Pages[0].AddTextField({
  rect: [72, 700, 300, 722], name: 'email',
  backgroundColor: [0.97, 0.97, 1],                    // /MK /BG
  borderColor: [0.2, 0.2, 0.6],                        // /MK /BC
  borderWidth: 1, borderStyle: 'beveled',              // /BS /W, /BS /S
  font: 'Helvetica', fontSize: 11, textColor: [0, 0, 0], // /DA
});

// Restyle a field that was already there.
doc.Form.Get('signature.name')!.SetStyle({
  borderColor: [1, 0, 0], borderStyle: 'dashed', dashPattern: [4, 2],
});

// Turn a field's contents inside its unchanged rectangle (/MK /R).
doc.Form.Get('spine.label')!.SetStyle({ rotate: 90 });
```

`borderStyle` is one of `'solid'`, `'dashed'`, `'beveled'`, `'inset'` or
`'underline'`, and all five are drawn into the generated `/AP` rather than left
for a viewer to interpret. Colours are RGB triples in 0..1; `null` paints
nothing (the specification's empty colour array), which is how a push button's
default grey face is suppressed. An absent key is left unchanged — `SetStyle`
with only `textColor` keeps the existing face, size, border and background.

`textColor` also colours a checkbox's check and a radio button's fill mark, which are
drawn in the `/DA` colour.

`rotate` is a counter-clockwise quarter turn — `0`, `90`, `180` or `270` — of
the field's contents inside its unchanged `/Rect`. The appearance is composed in
the turned box, so a 200×50 field rotated 90° wraps and aligns its text against
the 50×200 edges a reader actually sees. It applies to every field type.

### Import and Export Form Data (FDF / XFDF)

Export the current field values to a data file, and import them back:

```ts
const doc = Document.OpenFile('form.pdf');
doc.Form.Get('name')!.Value = 'Ada';

const xfdf = doc.ExportXfdf({ file: 'form.pdf' });   // or ExportFdf()

const other = Document.OpenFile('form.pdf');
const report = other.ImportXfdf(xfdf);               // or ImportFdf()
report.imported;  // ['name']
report.skipped;   // [{ name, reason }] — unknown fields and rejected values
```

Annotations travel through the same pair of files, opt-in on both sides:

```ts
const xfdf = doc.ExportXfdf({ annotations: true });

const report = other.ImportXfdf(xfdf, { annotations: true });
report.importedAnnots;  // [{ page, subtype, name }] — page is 0-based
report.skippedAnnots;   // [{ page?, subtype?, reason }]
```

Each annotation is added to the page index it carries, replacing any annotation
already on that page with the same `/NM` — so importing the same file twice
leaves one copy, not two. Widget annotations are never carried this way; they
are form fields and travel as `/Fields`. Popup and reply (`/IRT`) links between
exported annotations are preserved.

Export omits fields with no value; pass `{ includeEmpty: true }` for a complete
snapshot. Signature and pushbutton fields are never exported. Import sets values
through the same path as `Field.Value`, so appearance streams are regenerated and
invalid values are rejected — a rejected field is reported in `skipped` and left
untouched rather than throwing. Only a container that cannot be read at all (a
bad `%FDF-` header, malformed XML, a missing `/Root`) raises `PdfParseError`.
The data file's `/F` source reference and `/ID` are surfaced on the report as
`sourceFile` / `sourceId`, but are not enforced — comparing them is the caller's
policy.

### Read and Write Outlines (Bookmarks)

```ts
const outline = doc.GetOutlines();   // OutlineItem[] (nested tree)
for (const item of outline) console.log(item.Title, item.Dest);

doc.SetOutlines([                     // replaces the whole tree
  { Title: 'Cover', Dest: { page: 1 } },
  {
    Title: 'Chapter 1',
    Dest: { page: 2, view: { type: 'XYZ', left: 0, top: 792, zoom: null } },
    Open: true,
    Color: [0.8, 0, 0],               // bookmark-panel colour (/C)
    Bold: true,                       // /F bit 2; Italic is bit 1
    Children: [{ Title: 'Section 1.1', Dest: { page: 3 } }],
  },
  { Title: 'Appendix', Dest: { name: 'appendix' } },   // named destination
]);
doc.SetOutlines([]);                  // removes the outline entirely
```

A destination is either `{ page, view? }` or `{ name }`. Destination pages are
1-based and validated against the document; the optional `view` mirrors the PDF
destination types (`XYZ`, `Fit`, `FitH`, `FitR`, ...), where `null` means
"retain the current value".

Prefer `{ name }` (paired with `SetNamedDestination`) for anything that must
outlive an edit: a page destination is resolved when it is written, so inserting
a page ahead of it silently retargets the bookmark, while a named one resolves at
view time and follows its page. The name is not required to exist yet — a forward
reference is legitimate — and `GetOutlines` reports a named target back as
`{ name }` rather than resolving it, so re-writing what you read preserves the
indirection. Use `GetNamedDestinations()` when you want the page number.

`Color` is RGB 0..1 and `Bold`/`Italic` map to the `/F` flag bits. All three are
omitted from the output when unset.

### Read and Write Page Labels

```ts
const labels = doc.GetPageLabels();   // PageLabel[] (ascending ranges)

doc.SetPageLabels([                   // replaces /Root /PageLabels
  { startIndex: 0, style: 'roman' },               // i, ii, iii, ...
  { startIndex: 3, style: 'decimal', start: 1 },   // 1, 2, 3, ...
  { startIndex: 9, style: 'decimal', prefix: 'A-' }, // A-1, A-2, ...
]);

doc.PageLabelFor(0);                  // "i"   (0-based page index -> label)
doc.PageLabelFor(3);                  // "1"
doc.SetPageLabels([]);                // removes the labels entirely
```

Ranges are sorted by `startIndex` and the first must start at `0` (else a
`RangeError`). Styles are `decimal` / `roman` / `Roman` / `alpha` / `Alpha` /
`none`; `PageLabelFor` renders `prefix + numeral(style, start + offset)` and
falls back to the decimal page number where no range applies.

### Manage Named Destinations

```ts
const dests = doc.GetNamedDestinations();   // NamedDestination[] (sorted by name)
for (const { name, dest } of dests) console.log(name, dest.page);

doc.SetNamedDestination('intro', { page: 1, view: { type: 'XYZ', left: 0, top: 792, zoom: null } });
doc.SetNamedDestination('appendix', { page: 9 });   // defaults to /Fit
doc.RemoveNamedDestination('intro');
```

`GetNamedDestinations` merges the modern `/Root /Names /Dests` name tree with the
legacy `/Root /Dests` dict (legacy wins on a name clash). `SetNamedDestination`
upserts into the name tree, writing a single flat node (no balanced-tree
rebalancing); `RemoveNamedDestination` deletes from both sources and prunes the
empty containers.

### Set Document Open Behaviour and Document-Level JavaScript

The catalog's `/OpenAction` says what happens when the document is opened, and
32000-1 permits two shapes — a destination, or an action. They are separate
calls because they are not interchangeable:

```ts
doc.SetOpenDestination({ page: 3, view: { type: 'Fit' } }); // open at page 3
doc.SetOpenAction({ type: 'javascript', script: 'app.alert("Hello");' });

doc.GetOpenAction();
// -> { kind: 'dest', dest: { page: 3, view: { type: 'Fit' } } }
// or { kind: 'action', action: { type: 'javascript', script: '...' } }
doc.RemoveOpenAction();
```

`GetOpenAction()` is `undefined` both when there is none and when the document
carries one this library does not model — the position an annotation's `/A`
already takes.

Document-level scripts live in the `/Names /JavaScript` tree, which a viewer
runs at open in name order:

```ts
doc.SetJavaScript('init', 'var total = 0;');
doc.GetJavaScripts();      // [{ name: 'init', script: 'var total = 0;' }]
doc.RemoveJavaScript('init');   // true
```

An entry that is not a JavaScript action is skipped rather than reported, since
there is no script to give back. The library stores script text and never
interprets it. Note `ConvertToPdfA` and `ConvertToPdfX` remove both constructs
unless you preserve them — they are prohibited in those profiles.

### Create and Search Annotations

```ts
const page = doc.Pages[0];

// Read: typed handles, chosen by /Subtype (.Dict is the raw escape hatch).
for (const a of page.Annotations) console.log(a.Subtype, a.Rect, a.Contents);

// Sticky note.
page.AddTextNote({ rect: [72, 700, 96, 724], contents: 'Please review', icon: 'Comment', author: 'QA' });

// Rubber stamps: standard name, custom text, or an image.
page.AddStamp({ rect: [400, 700, 540, 740], name: 'Approved' });
page.AddStamp({ rect: [400, 660, 540, 690], text: 'DRAFT', color: [1, 0, 0] });
page.AddStamp({ rect: [40, 40, 140, 100], image: new Uint8Array(readFileSync('seal.png')) });

// Text markup over /QuadPoints (four corner points per marked quad).
const quads = [72, 540, 240, 540, 72, 528, 240, 528];
page.AddHighlight({ quads, color: [1, 1, 0] }); // translucent by default (/CA 0.4) so text shows through; pass opacity to override
page.AddUnderline({ quads });

// Geometric shapes: rectangle, ellipse, and line (with optional arrowheads).
page.AddSquare({ rect: [72, 440, 240, 500], color: [0, 0, 1], fill: [0.9, 0.9, 1], width: 1.5 });
page.AddCircle({ rect: [260, 440, 380, 500], color: [1, 0, 0] });
page.AddLine({ line: [72, 420, 380, 420], color: [0, 0, 0], endEnding: 'ClosedArrow' });

// Path shapes: closed polygon, open polyline (with arrowheads), and freehand ink.
page.AddPolygon({ vertices: [72, 200, 200, 200, 136, 300], fill: [0.9, 0.9, 1] });
page.AddPolyline({ vertices: [220, 200, 300, 260, 380, 200], endEnding: 'OpenArrow' });
page.AddInk({ paths: [[72, 160, 120, 190, 170, 150], [180, 150, 220, 180]] });

// Free text, optionally with a callout leader pointing at something.
page.AddFreeText({ rect: [72, 360, 240, 410], contents: 'A typed note', fontSize: 11, align: 'left', fill: [1, 1, 0.8] });
page.AddFreeText({ rect: [260, 360, 380, 410], contents: 'See here', callout: [200, 300, 240, 340, 260, 380] });

// Popups: bind one to an existing markup, or pass `popup: {}` to any Add* call.
const note = page.AddSquare({ rect: [72, 300, 200, 340] });
page.AddPopup({ parent: note, open: false });

// A caret marking where text should be inserted, with a paragraph sign.
page.AddCaret({ rect: [72, 340, 84, 356], symbol: 'paragraph', contents: 'insert a clause here' });
page.AddHighlight({ quads, popup: { open: true } }); // one-call companion popup

// Links: jump to a page, or open a URL.
page.AddLink({ rect: [72, 500, 200, 514], action: { type: 'goto', page: 3 } });
page.AddLink({ rect: [72, 480, 200, 494], action: { type: 'uri', uri: 'https://aspose.com' } });

// Delete.
page.RemoveAnnotation(page.Annotations[0]);
```

`page.Annotations` returns `Annotation` handles whose subclass follows
`/Subtype`: `TextAnnotation` (`Icon`/`Open`/`Author`), `StampAnnotation`
(`StampName`), `MarkupAnnotation` (`MarkupType`/`QuadPoints`), `LinkAnnotation`
(`Action`/`Dest`), `FileAttachmentAnnotation` (`Icon`/`FileName`/`GetBytes()`),
`SquareCircleAnnotation` (`ShapeType`/`InteriorColor`/`BorderWidth`),
`LineAnnotation` (`Line`/`LineEndings`/`BorderWidth`),
`PolyAnnotation` (`PolyType`/`Vertices`/`InteriorColor`/`BorderWidth`/`LineEndings`),
`InkAnnotation` (`InkList`/`BorderWidth`),
`FreeTextAnnotation`
(`Alignment`/`FontSize`/`TextColor`/`BorderWidth`/`InteriorColor`/`Intent`/`CalloutLine`/`CalloutEnding`),
and `PopupAnnotation` (`Open`/`Parent`). Any markup-family `Add*` method accepts
a `popup` option to attach a companion popup in one call.
Every handle shares the base accessors
(`Rect`, `Color`, `Contents`, `Name`, `ModDate`, `Flags`, `Print`, `Hidden`,
`Opacity`) and a `.Dict` escape hatch. Created annotations default to printable
(`/F` = 4); stamp and markup annotations get a generated `/AP` appearance, while
text notes and zero-border links render natively. Coordinates are PDF user space
(origin bottom-left, points).

### Embed Files and Attachments

```ts
// Document-level attachment (shows in a viewer's attachments panel).
doc.AddAttachment('report.csv', bytes, { mimeType: 'text/csv', description: 'Q2 figures' });
for (const a of doc.GetAttachments()) console.log(a.Name, a.Size, a.GetBytes().length);
doc.RemoveAttachment('report.csv');

// On-page attachment icon (FileAttachment annotation).
doc.Pages[0].AddFileAttachment({ rect: [72, 700, 92, 720], name: 'note.txt', bytes, icon: 'PushPin' });
```

Bytes are `FlateDecode`-compressed by default; pass `compress: false` to store
them raw. `AddFileAttachment` is annotation-only by default — pass
`addToCatalog: true` to also list the file in the document attachments panel
(one shared filespec). Each `GetAttachments()` entry decodes lazily via
`GetBytes()`.

`AddAttachment` (and `GetAttachments()`) return an `Attachment` handle. Promote
the attachments into a **portfolio** by giving each file custom field values and
declaring a `/Collection` schema:

```ts
// Turn attachments into a portfolio with custom columns.
const a = doc.AddAttachment('q2.csv', bytes, { mimeType: 'text/csv' });
a.SetField('reviewer', 'Alice');
a.SetField('approved', new Date());
doc.SetCollection({
  fields: [
    { name: 'name', type: 'filename', displayName: 'File', order: 0 },
    { name: 'reviewer', type: 'string', displayName: 'Reviewer', order: 1 },
    { name: 'approved', type: 'date', displayName: 'Approved', order: 2 },
  ],
  view: 'details',
  sortBy: 'approved',
});
```

Built-in field types (`filename`, `description`, `size`, `compressedSize`,
`creationDate`, `modDate`) are derived from the file itself; custom types
(`string` / `date` / `number`) read their value from each file's `/CI`, set via
`Attachment.SetField`. `GetCollection()` reads the settings back;
`RemoveCollection()` drops the portfolio.

### Read and Write XMP Metadata

```ts
const xmp = doc.GetXmp();                 // XmpMetadata: dc/xmp/pdf fields + raw packet
console.log(xmp.title, xmp.authors, xmp.createDate);

doc.SetXmp({                              // merged over the current packet
  title: 'Annual Report',
  authors: ['Jane Doe', 'John Roe'],      // ordered dc:creator
  subjects: ['finance', '2024'],          // dc:subject bag (XMP-only)
  producer: null,                         // null deletes a field
  custom: [{                              // your own namespaced property
    namespace: 'http://acme.example/ns/1.0/', prefix: 'acme',
    name: 'BatchId', value: 'B-4711',
  }],
});
doc.WriteTo('out.pdf');
```

`GetXmp()` parses the `/Root /Metadata` packet (Dublin Core, XMP basic, and PDF
schemas) leniently — malformed packets never throw, and the original text is
returned in `raw`. `SetXmp(update)` merges the update over the current packet
(`null` deletes), rebuilds a well-formed packet, and installs it as an
uncompressed metadata stream picked up by `Save()`. Shared fields auto-mirror
with `/Info` in both directions (`SetMetadata` → XMP, `SetXmp` → `/Info`):
`title`↔`dc:title`, `author`↔`dc:creator`, `subject`↔`dc:description`, plus
`keywords`, `producer`, `creator`(tool), and the create/modify dates. XMP-only
fields (`subjects`, `rights`) and `/Info` custom keys stay on their own side.

`custom` carries properties outside those schemas — a private provenance
namespace, or a PDF/A custom schema. Each entry is emitted as an
`rdf:Description` with its `xmlns:` declaration (entries sharing a prefix are
grouped into one), and `GetXmp` reads them back using the packet's own prefix
bindings. Simple literal values only: containers (`rdf:Alt`/`Seq`/`Bag`),
structs and language alternatives are not modelled and are skipped on read. A
prefix already bound by a built-in schema (`dc`, `xmp`, `pdf`, `pdfaid`,
`pdfuaid`, `pdfxid`, `rdf`, `x`, `xml`) is rejected.

### Extract and Replace Embedded Images

```ts
for (const img of doc.Pages[0].Images) {
  console.log(img.Name, img.Width, img.Height, img.ColorSpace, img.Bits, img.Filter);
  const raw = img.RawData;     // encoded stream bytes (still Flate/DCT-encoded)
  const data = img.Decode();   // Flate/JPX -> decoded samples; DCTDecode -> JPEG bytes
}
```

Beyond reading, an image can be swapped or dropped in place:

```ts
const img = doc.Pages[0].Images[0];
img.Replace(fs.readFileSync('new.png'));           // JPEG, PNG, BMP or TIFF
doc.Pages[0].Images[1].Remove();                   // drops the draw and the resource entry
doc.Pages[0].Images[0].Remove({ sanitize: true }); // …and every other orphaned resource
```

`Replace` keeps the placement: the new image is stretched into the footprint the
old one occupied, whatever its proportions, because the `cm` that sizes an image
lives in the content stream rather than in the XObject. It builds and validates
the new image before touching anything, so a call that throws leaves the document
byte-identical, and it builds the image dict fresh — a stale `/SMask` from the
old picture cannot survive, with `/OC` the one entry carried over. Pass
`{ format }` to override magic-byte detection and `{ page }` to pick an image out
of a multi-image TIFF.

Both methods are scoped to the page the handle came from. An image shared with
another page is copied rather than mutated on replace, and removing it from one
page leaves the other page still drawing it; the object itself is swept by
`Save()` once nothing points at it. Inline (`BI…EI`) images are not enumerated by
`page.Images`, so they cannot be replaced or removed — use `Redact` over their
rectangle.

`Decode()` decodes `FlateDecode`, `LZWDecode`, `ASCII85Decode`, `ASCIIHexDecode`,
and `RunLengthDecode` (singly or chained), returns 1-bpp samples for
`CCITTFaxDecode` (Group 3 1D and 2D, and Group 4 — honoring `BlackIs1`,
`EncodedByteAlign`, `EndOfLine`, and `EndOfBlock`), returns 8-bit samples for
`JPXDecode` (JPEG 2000 — see *JPEG 2000 decoding* below), returns 1-bpp samples
for `JBIG2Decode` (arithmetic generic, symbol-dictionary, and text regions, plus
MMR/Group-4 generic, generic refinement regions, refinement within symbol
dictionaries and text regions (REFAGG/SBREFINE), and pattern dictionaries and
halftone regions (arithmetic and MMR grayscale bitplanes, HENABLESKIP), and
custom Huffman table segments, and Huffman-coded symbol dictionaries and text
regions — so every JBIG2 *coding* feature decodes; what remains is a segment
type T.88 does not assign, which throws `UnsupportedFeatureError`, and the
`0xffffffff` unknown segment data length, which throws `PdfParseError`), and
passes `DCTDecode` (JPEG) bytes
through. `RawData` and enumeration never throw.

**JPEG 2000 decoding** — `JPXDecode` images decode to 8-bit interleaved samples
(`Image.Decode()`) and render through `ToImage`/`ToSvg`. The decoder has no third-party library behind it — it is a from-scratch implementation of the
codestream: JP2 box container and bare J2K,
a single tile, multiple quality layers, all five progression orders
(LRCP/RLCP/RPCL/PCRL/CPRL), the 5/3 reversible (lossless) and 9/7 irreversible
(lossy) wavelet transforms with the full MQ arithmetic coder and EBCOT
Tier-1/Tier-2 entropy path, and 1-component (grayscale) or 3-component (RGB) with
the RCT/ICT multiple-component transforms. Component precision above 8 bits is
downshifted to 8-bit output. Not yet supported (throws `UnsupportedFeatureError`):
multiple tiles, custom precinct partitions, region of interest (`RGN`), more than
three components, and component sub-sampling.

### Use File-Based Helper Methods

Convenience wrappers that handle reading and writing for you:

```ts
import {
  splitPdfFile, readMetadataFile, updateMetadataFile, clearMetadataFile, savePageImageFile,
  exportFdfFile, exportXfdfFile, importFdfFile, importXfdfFile, htmlFileToPdf,
} from '@asposefoss/pdf';

await splitPdfFile('input.pdf', 'out/');             // writes out/page-1.pdf, page-2.pdf, ...
const meta = await readMetadataFile('input.pdf');
await updateMetadataFile('in.pdf', 'out.pdf', { title: 'New', author: null }); // null deletes a field
await clearMetadataFile('in.pdf', 'out.pdf');
await savePageImageFile('in.pdf', 0, 'page1.png', { scale: 2 }); // rasterize page 1 → PNG
await exportXfdfFile('form.pdf', 'data.xfdf');                   // or exportFdfFile
await exportXfdfFile('doc.pdf', 'notes.xfdf', { annotations: true });
const report = await importXfdfFile('form.pdf', 'data.xfdf', 'filled.pdf'); // outPath defaults to in-place
await importXfdfFile('doc.pdf', 'notes.xfdf', 'out.pdf', { annotations: true });

// HTML in, PDF out. The encoding comes from the bytes (BOM, then the
// document's own <meta charset>), and a relative <img src> is read from beside
// the HTML file — confined to its directory, so a URL, an absolute path or a
// `..` climb is refused and reported instead of fetched or followed.
const { skipped } = await htmlFileToPdf('page.html', 'out.pdf', { format: PageFormat.A4 });
```

### Optimize Fonts, Images and Structure

`doc.Optimize(opts?)` shrinks the live model in place; the next `Save()` writes
the smaller document.

| Option | Effect |
|---|---|
| `fonts` | Subset already-embedded fonts to the glyphs actually shown |
| `dedup` | Merge byte-identical streams (duplicate images, font programs) |
| `compress` | Flate unfiltered streams; re-deflate Flate streams at max level |
| `dr` | Remove `/AcroForm /DR` resources nothing in the document names |
| `images` | **Lossy.** Downsample images to `dpi` and recompress them as JPEG at `quality` |

`fonts`, `dedup`, `compress`, and `dr` are lossless and default **on**. `images` is
lossy and is **off unless supplied** — there is no `images: true` shorthand, so
the pass cannot run at settings you did not choose. `report.lossy` records
whether it ran.

```ts
const report = doc.Optimize({ compress: false });
console.log(report.bytesSaved, report.skipped);
doc.WriteTo('smaller.pdf');

// Opt in to the lossy image pass.
const r = doc.Optimize({ images: { dpi: 150, quality: 75 } });
console.log(r.lossy, r.images, r.skippedImages);
```

Returns an `OptimizeReport`: per-font glyph counts (one entry per font *program*
— a program two font dicts share is shrunk once, against the union of what both
show), a `skipped` list explaining any font left untouched, per-image dimensions
and savings, a `skippedImages` list, and an **estimated** `bytesSaved` (a
raw-delta sum, not a file-size delta — only `Save()` produces bytes).

The `dr` pass removes `/AcroForm /DR` entries — in every category, not only
`/Font` — that nothing in the document can name. A reference is a name in any
`/DA` string (the AcroForm default, a field's, a widget's, a `FreeText`
annotation's) or a name an `/AP` appearance stream cannot resolve against its own
`/Resources`. This is what collects the face a field registered at creation and
kept after `Form.RemoveField` unwired it. `report.dr.removed` names the removed
keys (`'Font/TiBo'`), and `report.dr.bytesSaved` counts the payload of the
streams the removal orphaned.

The pass declines outright — reporting `report.dr.skipped` and changing nothing —
for a document carrying `/AcroForm /XFA`, whose packet can name `/DR` faces this
library never reads, or one whose appearance streams cannot all be decoded and
parsed. A scan that cannot prove itself complete does not get to call a resource
unused.

The image pass measures each image's *effective* DPI from the CTM at every place
it is drawn and downsamples to the most demanding one, so no placement degrades;
it never upsamples, and it replaces a stream only when the re-encode is strictly
smaller. Images are skipped — and reported in `skippedImages` with a reason —
when they are image masks, non-8-bit, indexed, bilevel (JBIG2/CCITT), carry a
`/Mask` or `/Decode`, use a colorspace with no JPEG equivalent, or are never
drawn by the content scan (which is what leaves an `/SMask` untouched).

### Convert Pages and Images to Grayscale

`doc.ConvertToGrayscale(opts?)` converts a document's colour to DeviceGray in
place: page content, form XObjects, tiling patterns, Type 3 glyph procedures,
image XObjects, inline images, shadings and annotations.

```ts
const report = doc.ConvertToGrayscale({ quality: 90 });
report.images;   // one entry per converted image, with its route and byte delta
report.skipped;  // what could not convert, and why
report.lossy;    // true when a JPEG was re-encoded
```

Colour is discarded, so this is **not** reversible. A signed document throws
`UnsupportedFeatureError`, since converting one would invalidate the signature
and `Save()` would discard the change.

Every colour goes through one rule — Rec. 601 luma, `0.299R + 0.587G + 0.114B`
— reached through the same colour-space resolution the renderer uses, so
ICCBased, Indexed, Separation, DeviceN, CalRGB and Lab all convert without
special cases. Colour *operators* are neutralized rather than colour spaces
retargeted: `rg`/`k`/`sc`/`scn` become `g`/`G`, `cs` becomes `/DeviceGray`, and
the named `/ColorSpace` entries are simply left unreferenced for `Optimize`'s
`dr` pass to collect.

Images take the cheapest faithful route. An **Indexed** image greys by
rewriting its palette alone — lossless, smaller, and the only route that works
below 8 bits per component.

A **YCbCr JPEG** — which is nearly every photographic JPEG — takes a shorter
route still. Its Y channel already *is* Rec. 601 luma, so greying it needs no
decode at all: component 0's quantized coefficients and its quantization table
are carried over untouched and the two chroma components dropped, giving an
exact, generation-free greying that is smaller than the original and reports
`route: 'jpeg-exact'` without setting `lossy`. Progressive and arithmetic JPEGs
take it too, and come out baseline.

A JPEG that route declines — CMYK or YCCK, 12-bit, lossless, hierarchical, or a
three-component file whose colour transform is 0, where component 0 is red
rather than luma — re-encodes as a grey JPEG at `quality` (default 90), which is
the one thing here that loses information beyond the colour, and sets
`report.lossy`. A decline is not a `skipped` entry: the image converts either
way, and `route` is what says how. Other decodable samples become grey Flate;
a JPX image takes that route too, since the library has a JPEG 2000 decoder and
no encoder, and will usually grow — `bytesDelta` says so rather than surprising
you.

Shading functions convert exactly where that is free (type 2 through `/C0` and
`/C1`, type 3 by recursion) and are resampled into a one-output sampled function
otherwise. A mesh shading (types 4–7) with no `/Function` states its colour per
vertex in its own stream data rather than in a function, so it is converted by
re-splicing that data: each colour tuple collapses to one grey component, the
coordinates are copied bit for bit so the geometry cannot drift, and `/Decode`
keeps its coordinate ranges and gains the single grey one.

A colour-key `/Mask` is converted rather than refused, and not by re-deriving
the range: two colours can share a luma — (255,0,0) and (0,130,0) both grey to
76 — so no grey range is faithful. `/Mask` may be a stencil image as well as a
colour-key array, so the pass records WHICH PIXELS the key matched as a 1-bit
stencil in that same entry, which is exact. An Indexed image needs no
conversion at all: its key indexes sample values, and the palette route leaves
those untouched.

What cannot convert is reported in `skipped` rather than silently
left in colour: a mesh whose data ends mid-record, or whose `/Decode` states no
range for its colour components; an image carrying both a colour-key `/Mask`
and an `/SMask`, which 32000-1 makes mutually exclusive; an
image carrying a `/Decode` array; and a filtered inline image.

`/OutputIntents` is deliberately left alone — a DeviceCMYK intent on a greyed
document is odd but not invalid, and replacing it is PDF/X remediation's job.

### Render and Export a Page or Document to Other Formats

```ts
import { Document } from '@asposefoss/pdf';

const doc = Document.OpenFile('in.pdf');
const svg = doc.Pages[0].ToSvg();          // standalone <svg> string
// fs.writeFileSync('page1.svg', svg);
const png = doc.Pages[0].ToImage({ scale: 2 }); // Uint8Array of PNG bytes @144 DPI
// fs.writeFileSync('page1.png', png);
const html = doc.ToHtml();                 // standalone semantic HTML, all pages
// fs.writeFileSync('out.html', html);
const md = doc.ToMarkdown();               // GFM Markdown, all pages
// fs.writeFileSync('out.md', md);
const docx = doc.ToDocx();                 // .docx bytes, reflowed, images in the package
// fs.writeFileSync('out.docx', docx);
const fixed = doc.ToDocx({ mode: 'textbox' });  // .docx keeping each page's own geometry
// fs.writeFileSync('fixed.docx', fixed);
```

</details>

## API Reference

The public entry points are organized around `Document` and `Page` (the core object model),
`Font`/`EmbeddedFont` (text authoring), `Annotation` and `Field` (interactive content), and
per-capability builders such as `PageGraphics`, `Flow` and `Table` — 360 public types across 9
modules.

<details>
<summary>View the Full API Surface</summary>

### Core API

| Class | Description |
|---|---|
| `Background` | A bare RGB tuple, or the object form when `padding` is wanted. |
| `BarcodeModel` | Class in the PDF TypeScript API. |
| `BarcodeSpec` | Which barcode to draw. |
| `BorderSides` | Which edges of a border box are painted: every edge, no edge, or exactly the ones flagged true (an omitted flag is false, so `{ bottom: true }` is a bottom rule only). |
| `BorderStyle` | Class in the PDF TypeScript API. |
| `ButtonIconPosition` | Where a push button's icon sits relative to its caption — all seven layouts PDF 32000-1 table 189 defines. |
| `CellBuilder` | One cell in a table row: a text string, optional per-cell style, and how many columns it spans. |
| `CellHeader` | How a cell is marked in a tagged table: a /TH carrying the given /Scope, or a /TD. |
| `ChoiceOption` | One option of a choice field. |
| `CollectionFieldType` | A schema column: built-in fields derive from the filespec; custom fields (string/date/number) read their value from each file's /CI. |
| `CollectionView` | How a viewer presents the portfolio. |
| `ColumnWidth` | A column-width spec: an absolute width in points (`fixed`), or a share of the leftover space after fixed columns are allotted (`fraction`). |
| `CommitmentType` | Standard CAdES commitment-type identifiers, or a custom dotted OID string. |
| `ContentItem` | A marked-content reference owned by a structure element. |
| `ConvertCategory` | Class in the PDF TypeScript API. |
| `Decoration-svgtext` | Class in the PDF TypeScript API. |
| `Decoration-textdecor` | `true` uses the font's metrics and the text's own colour; `false` is off. |
| `DigestAlgorithm` | Class in the PDF TypeScript API. |
| `Document` | Class with 109 methods and 26 properties. |
| `Edged` | A single value, or one-per-edge [top, right, bottom, left]. |
| `EditableContent` | Editable per-stream view of a page's content (Phase 4 foundation, F1). |
| `EmbeddedFont` | An opaque handle to a font program registered with AddFont. |
| `FieldActionsUpdate` | A field-actions update: an action to set, `null` to remove that trigger, and an absent key to leave it as it is — the same shape `SetStyle` takes. |
| `FieldBorderStyle` | How a widget's border is drawn (/BS /S). |
| `FloatingBox` | A padded/bordered/filled box of paragraphs and/or an image, floated into a Flow column by `flow.AddFloatBox`. |
| `Flow` | A flow layout container. |
| `FlowClear` | Which side's floats an element must clear before it places. |
| `FlowListNode` | A list node: a bare string leaf or a FlowListItem that may nest. |
| `Form` | The document's interactive form: terminal fields of the /AcroForm tree. |
| `GoToAction` | A GoTo action: jump to a page in this document. |
| `Gradient` | Class in the PDF TypeScript API. |
| `ImageInfo` | A single embedded image XObject: a live, read-only handle over its stream. |
| `InlineImageInfo` | A single `BI … EI` image drawn on a page, addressed by its position in the content stream that draws it. |
| `InvalidPasswordError` | Class with 1 method. |
| `JavaScriptAction` | A JavaScript action. |
| `Layer` | A single optional-content group (layer): a live handle over its /OCG dict. |
| `LayerConfig` | A viewing configuration (/D or a /Configs entry). |
| `MdAlign` | GFM table alignment, from the `:` markers on the delimiter row. |
| `MdBlock` | Class in the PDF TypeScript API. |
| `MdInline` | Class in the PDF TypeScript API. |
| `MdNode` | Class in the PDF TypeScript API. |
| `OpenAction` | What a document does when it is opened: go to a view, or run an action. |
| `OptionalContent` | The document's optional-content properties (/OCProperties). |
| `Padding-floatbox` | Class with 4 properties. |
| `Padding-tableauthor` | Inner cell padding: one value for every side, or an object naming the sides that differ. |
| `Page` | A single PDF page: a live, mutable handle over its real page dict. |
| `PageFormat` | A page size in points (1/72"). |
| `PageGraphics` | A buffered builder for drawing vector content onto a page. |
| `PathSegment` | Class with 8 properties. |
| `PdfALevel` | Conformance target: part (1/2/3) + level (b/u/a). |
| `PdfAction` | Any action this library models, for an annotation's /A. |
| `PdfParseError` | Class with 1 method. |
| `PdfXLevel` | PDF/X conformance target. |
| `PubSecRecipient` | Class with 4 properties. |
| `QrEcc` | Class in the PDF TypeScript API. |
| `RGB-annotdraw` | Class in the PDF TypeScript API. |
| `RGB-structattr` | Class in the PDF TypeScript API. |
| `Rect-tablemodel` | Class extending TextRect. |
| `Rect-text` | A page-space rectangle [x0,y0,x1,y1] (corners in any order). |
| `ResetAction` | A ResetForm action: clear the named fields, or every field. |
| `RevocationFetcher` | A fetcher for revocation material: given the target and its issuer (DER), return the OCSP response / CRL bytes, or undefined when none is available. |
| `RevocationStatus` | A revocation verdict for one certificate. |
| `RowBuilder` | One row: an ordered list of cells plus an optional row-level style. |
| `SaveOptions` | Options for Save/WriteTo. |
| `Severity` | Class in the PDF TypeScript API. |
| `Signer` | Any accepted signer: a credential source, or a pre-resolved CmsSigner (certificate DER + `KeyObject`) for callers that already hold a key. |
| `StdFont` | Class in the PDF TypeScript API. |
| `StreamFilterName` | Byte-filters this pass can re-encode a stream into. |
| `StructElement` | A node in the structure tree: a live handle over its real /StructElem dict. |
| `StructTreeRoot` | The document's logical structure tree: a live handle over /StructTreeRoot. |
| `SubmitAction` | A SubmitForm action: send the form's field values to `url`. |
| `Table` | A reconstructed table: a rows×cells model with page-space quads and text, serializable to HTML or Markdown. |
| `TableBuilder` | A page-independent table: ordered rows over shared text defaults. |
| `Template` | A reusable piece of drawn content, placed on any number of pages from a single Form XObject. |
| `TextFont` | Class with 6 methods and 10 properties. |
| `TilingPattern-tiling` | A handle returned by `Document.NewTilingPattern`. |
| `TimestampProvider` | A timestamp provider: given a DER `TimeStampReq`, return either the bare `TimeStampToken` (a CMS ContentInfo) or a full `TimeStampResp`. |
| `UnsupportedFeatureError` | Class with 1 method. |
| `UriAction` | A URI action: open an external URL. |
| `ValidationReport` | The result of a validation pass (PDF/UA or PDF/A). |
| `VectorGraphics` | A buffered builder for vector content: every path constructor, paint operator, graphics-state setting and marked-content bracket, accumulated in memory as operator text. |
| `XmpUpdate` | A partial XMP update: each known field may be set, or `null` to delete. |
| `AddBarcodeOptions` | Interface with 8 properties. |
| `AddImageOptions` | Interface with 5 properties. |
| `AddImagePagesOptions` | Interface with 3 properties. |
| `AddImagePagesResult` | Interface with 2 properties. |
| `AddLayerOptions` | Options for AddLayer. |
| `AddSVGOptions` | Options for AddSVGObject. |
| `AddSVGResult` | The outcome of AddSVGObject. |
| `AddTableOptions` | Options for drawTable / `page.AddTable`. |
| `AddTableResult` | The outcome of drawTable / `page.AddTable`. |
| `AutoTagOptions` | Options for AutoTag. |
| `AutoTagReport` | Counts of the elements AutoTag produced. |
| `BackgroundStyle` | A fill painted behind the glyphs. |
| `BatesOptions` | Options for AddBatesNumbering. |
| `BookletOptions` | Options for Booklet. |
| `BorderEdges` | The four edge flags, resolved from a BorderSides. |
| `BorderInfo` | A cell/table border: stroke width (pt), RGB colour (0..1), optional dash, and which edges to paint. |
| `CadesAttributes` | Optional CAdES signed attributes for a PAdES signature. |
| `CellOptions` | `addCell` options: the per-cell text style plus an optional horizontal span. |
| `CellTextOptions` | Per-cell/row text + visual style; each field falls back through the cascade (cell ??. |
| `CertInfo` | Summary of the signer's X.509 certificate. |
| `ChainOptions` | Interface with 2 properties. |
| `ChainResult` | Interface with 3 properties. |
| `Change` | One object that changed in a revision added after a signature. |
| `CheckboxInit` | Options for Form.AddCheckbox / Page.AddCheckbox. |
| `ChoiceInit` | Options common to both choice field types. |
| `CollectionFieldDef` | Interface with 6 properties. |
| `CollectionSettings` | Interface with 5 properties. |
| `ColoredTilingPattern` | A tiling pattern that carries its own colours. |
| `ComboBoxInit` | Options for Form.AddComboBox / Page.AddComboBox. |
| `ContentAddr` | Address of an operator within a page's content. |
| `ContentOp` | Interface with 5 properties. |
| `ContentVisitor` | Interface with 3 methods. |
| `ConvertOptions` | Interface with 5 properties. |
| `Crl` | Interface with 7 properties. |
| `CrlEntry` | Interface with 2 properties. |
| `DecorationOptions` | The decoration options shared by every text-authoring options type. |
| `DecorationStyle` | A rule drawn beneath (underline) or through (strikethrough) the text. |
| `DocumentJavaScript` | One entry of the document-level JavaScript name tree. |
| `DocumentTimestampReport` | Verdict for one document timestamp (`/DocTimeStamp`): the RFC 3161 token's time and imprint/TSA-signature checks, plus coverage and the TSA cert. |
| `DrPruneResult` | Interface with 3 properties. |
| `DssEntry` | Per-signature validation data to embed under one `/VRI` entry. |
| `ElemOpts` | Options for creating a structure element. |
| `ExportFormDataOptions` | Interface with 3 properties. |
| `ExternalSigner` | Sign via an external callback (HSM/KMS/smartcard) — the key never leaves the device. |
| `ExtractPagesOptions` | Interface with 1 property. |
| `Field-structattr` | One field: its PDF key plus a decode/encode pair. |
| `FieldActions` | A field's additional-actions (/AA), PDF 32000-1 table 197. |
| `FieldInit` | Options common to every field-creation entry point. |
| `FieldStyle` | WidgetStyle plus the /DA text half. |
| `FloatBoxImageOptions` | Options for AddImage. |
| `FloatBoxOptions` | Options for NewFloatingBox. |
| `FlowCodeOptions` | Options for codeBlock / `Flow.AddCodeBlock`. |
| `FlowElement` | A unit of flow content. |
| `FlowHeadingOptions` | Options for AddHeading. |
| `FlowImageOptions` | Options for AddImage. |
| `FlowListItem` | One nested-list item. |
| `FlowListOptions` | Options for AddList. |
| `FlowOptions` | Options for NewFlow. |
| `FlowParagraphOptions` | Typographic options for AddParagraph (a subset of the text-block options; flow content is always laid top-down, so `valign` is not offered). |
| `FlowQuoteBar` | The bar drawn down a quote's gutter. |
| `FlowQuoteOptions` | Options for quote / `Flow.AddQuote`. |
| `FlowRuleOptions` | Options for rule / `Flow.AddRule`. |
| `FlowTableOptions` | Options for table / `Flow.AddTable`. |
| `FontFamily` | The four faces emphasis selects between, loaded from disk. |
| `FontMatch` | What a name resolves to -- reported without loading or embedding anything. |
| `FontOptimization` | Interface with 4 properties. |
| `FormData` | Interface with 5 properties. |
| `FormDataField` | One field's data, format-neutral. |
| `G4EncodeOptions` | Interface with 1 property. |
| `GradientStop` | One gradient stop. |
| `GrayImageResult` | Interface with 4 properties. |
| `GraySkipped` | Interface with 3 properties. |
| `GrayscaleOptions` | Document-wide grayscale conversion. |
| `GrayscaleReport` | Interface with 8 properties. |
| `HeaderFooterBand` | One band of a header/footer: up to three independently-positioned cells. |
| `HeaderFooterOptions` | Options for AddHeaderFooter. |
| `HtmlOptions` | Options for ToHtml and ToHtml. |
| `ImageEvent` | A placed image with provenance. |
| `ImageOptimization` | Interface with 7 properties. |
| `ImportOptions` | Options for the four import methods. |
| `ImportReport` | Interface with 8 properties. |
| `InsertPagesOptions` | Interface with 1 property. |
| `LayoutAttributes` | Interface with 32 properties. |
| `LinearBarcode` | 1D barcode geometry: alternating bar/space run widths in unit modules. |
| `LinearGradient` | An axial (linear) gradient: a colour ramp along the axis from (x1, y1) to (x2, y2), in the **default** user space of the content stream it paints into — see the /Matrix note on PageGraphics.setFillGradient. |
| `LinearizationCheck` | Interface with 2 properties. |
| `ListAttributes` | Interface with 1 property. |
| `ListBoxInit` | Options for Form.AddListBox / Page.AddListBox. |
| `LoadFontOptions` | A style request alongside the ordinary font options. |
| `MatrixBarcode` | 2D barcode geometry: a square matrix of dark/light modules, row-major. |
| `MdBlockQuote` | Interface with 2 properties. |
| `MdCode` | Interface with 2 properties. |
| `MdCodeBlock` | `info` is the raw info string of a fenced block, entity-decoded and backslash-unescaped but not split on whitespace; '' for an indented block. |
| `MdDocument` | The CommonMark abstract syntax tree, per CommonMark 0.31.2. |
| `MdEmph` | Interface with 2 properties. |
| `MdHardBreak` | Interface with 1 property. |
| `MdHeading` | Level 1..6, identical for the ATX (`# x`) and setext (`x\n=`) spellings. |
| `MdHtmlBlock` | Raw HTML, verbatim. |
| `MdHtmlInline` | Interface with 2 properties. |
| `MdImage` | Interface with 4 properties. |
| `MdItem` | Interface with 3 properties. |
| `MdLink` | Inline and reference links are indistinguishable here: both carry a resolved destination and title, which is what gl6o.3 wants. |
| `MdList` | `tight` decides whether an item's paragraphs render as paragraphs (loose) or as bare content (tight). |
| `MdParagraph` | Interface with 2 properties. |
| `MdSoftBreak` | Interface with 1 property. |
| `MdStrikethrough` | GFM strikethrough. |
| `MdStrong` | Interface with 2 properties. |
| `MdTable` | `align` carries one entry per column, null where the delimiter row gave none — which is not the same as 'left', since a renderer may have its own default. |
| `MdTableCell` | Holds inlines, like a paragraph does. |
| `MdTableRow` | Interface with 3 properties. |
| `MdText` | Interface with 2 properties. |
| `MdThematicBreak` | Interface with 1 property. |
| `Metadata` | Interface with 9 properties. |
| `MetadataUpdate` | Interface with 9 properties. |
| `NUpOptions` | Interface with 5 properties. |
| `ObjStmDamage` | What one /ObjStm container yielded, and what it cost. |
| `OcspResponse` | Interface with 7 properties. |
| `OcspSingleResponse` | Interface with 8 properties. |
| `OoxmlPart` | One part of an OPC package. |
| `OoxmlRelationship` | One entry of a `.rels` file. |
| `OpenOptions` | Interface with 2 properties. |
| `OptimizeImageOptions` | Target for the lossy image pass. |
| `OptimizeOptions` | Which concerns to run. |
| `OptimizeReport` | Interface with 13 properties. |
| `OverlayOptions` | Interface with 5 properties. |
| `PageLabel` | A logical page-label range in the /Root /PageLabels number tree. |
| `PagePath` | Interface with 11 properties. |
| `PathEvent` | A painted vector path, its subpaths flattened to page-space segments. |
| `PathPaint` | Interface with 2 properties. |
| `PathSubpath` | Interface with 2 properties. |
| `PdfUaConvertOptions` | Interface with 3 properties. |
| `PdfXConvertOptions` | Interface with 9 properties. |
| `PemSigner` | Sign from a PEM private key plus its PEM/DER certificate chain (leaf first). |
| `Pkcs12Signer` | Sign from a PKCS#12 (`.pfx`/`.p12`) blob; the key and chain are extracted. |
| `PlaceContext` | Where an element is being placed. |
| `PlaceElementsOptions` | Options for placeElements. |
| `PlaceElementsResult` | Result of placeElements. |
| `PlaceOptions` | Options for PlaceOn. |
| `PlaceResult` | Outcome of place. |
| `PrunePolicy` | Interface with 1 method and 1 property. |
| `PushButtonInit` | Options for Form.AddPushButton / Page.AddPushButton. |
| `QrOptions` | Interface with 2 properties. |
| `Quantized` | The result of quantizing an image. |
| `RadialGradient` | A radial gradient: the ramp runs from the focal point out to the circle (cx, cy, r). |
| `RadioGroupInit` | Options for Form.AddRadioGroup. |
| `RadioOption` | One button of a radio group. |
| `RecoveryReport` | How Open obtained its cross-reference data. |
| `Rect-barcodeplace` | A dark rectangle in PDF user space. |
| `RegionHits` | Glyph and image events intersecting a set of regions. |
| `RemoveImageOptions` | Options for removeImage / `ImageInfo.Remove`. |
| `ReplaceImageOptions` | Options for replaceImage / `ImageInfo.Replace`. |
| `ResizeOptions` | Interface with 1 property. |
| `ResolvedFamily` | A family with all four faces filled. |
| `ResolvedPadding` | Padding with every side settled to a number. |
| `RevocationMaterial` | Raw revocation material for one certificate (DER bytes, as fetched). |
| `RevocationResult` | Interface with 2 properties. |
| `RowOptions` | `addRow` options: the row-level text style plus row-only geometry. |
| `SearchOptions` | Scope for a text search. |
| `SigAlg` | Signature algorithm passed to an external signer callback: the public-key scheme plus the message-digest algorithm to hash the data with. |
| `SignerLocation` | CAdES `signer-location` signed attribute (all fields optional). |
| `SignerOptions` | Options common to the credential-source signer variants. |
| `SkippedFont` | Interface with 2 properties. |
| `SkippedFrame` | Interface with 2 properties. |
| `SkippedImage` | Interface with 3 properties. |
| `SplitOptions` | Interface with 2 properties. |
| `SvgOptions` | Interface with 2 properties. |
| `TableAttributes` | Interface with 5 properties. |
| `TableCell` | Interface with 13 properties. |
| `TableDefaults` | Table-level defaults; the cascade root, plus table-only fields. |
| `TableExtractOptions` | Interface with 2 properties. |
| `TableMetrics` | Measurement result for a table at given resolved column widths. |
| `TableRow` | Interface with 3 properties. |
| `TableStitchOptions` | Interface with 1 property. |
| `TextBlock` | A paragraph-like cluster of consecutive lines, ordered top-to-bottom. |
| `TextFieldInit` | Options for Form.AddTextField / Page.AddTextField. |
| `TextFragment` | A positioned text run sharing one font, size, and baseline — the public unit of structured extraction (`Page.GetTextFragments`). |
| `TextLine` | Interface with 4 properties. |
| `TextMatch` | A positioned text match. |
| `TextRun` | One styled span of a rich text block. |
| `TilingPattern-pagerender` | A resolved PatternType 1 (tiling) pattern. |
| `TilingPatternOptions` | Placement and repetition for a tiling pattern. |
| `TimestampInfo` | Verdict on a signature timestamp: the asserted time plus whether the token binds to the signature (imprint) and whether the TSA's signature is valid. |
| `TrailerChoice` | What trailer synthesis chose. |
| `TstInfo` | Interface with 6 properties. |
| `UncoloredTilingPattern` | A tiling pattern whose colour is supplied at use time. |
| `ValidationDataOptions` | Options for AddValidationData: callbacks that fetch the OCSP response / CRL for each signer, plus any extra certificates to embed (e.g. a trust-anchor root not carried in the CMS). |
| `ValidationIssue` | A single validation finding. |
| `VerifyOptions` | Options for VerifySignatures. |
| `WatermarkOptions` | Options for AddWatermark. |
| `WidgetStyle` | /MK + /BS: what a widget's box looks like. |
| `XmpMetadata` | Structured view of a document's XMP packet (read side). |
| `ZipEntry` | One file in an archive. |

### Annotations

| Class | Description |
|---|---|
| `Annotation` | A live, mutable handle over an annotation dictionary. |
| `AnnotationTextKey` | The annotation entries that count as carried text. |
| `AuthoringFont` | A font for the text-authoring API: one of the 12 Latin Standard-14 faces (by name) or an embedded font handle from AddFont. |
| `CaretAnnotation` | A /Caret annotation (PDF 32000-1 §12.5.6.11): a text-insertion mark, drawn as a wedge at the point where text should be added, optionally with a paragraph sign. |
| `FileAttachmentAnnotation` | A /FileAttachment annotation: an icon on the page whose /FS embeds a file. |
| `LinkAction` | @deprecated Use PdfAction. |
| `LinkAnnotation` | A /Link annotation. |
| `MarkupAnnotation` | A text-markup annotation (/Highlight, /Underline, /StrikeOut, /Squiggly) positioned by /QuadPoints (8 numbers per marked quad). |
| `MarkupType` | The four text-markup subtypes, lower-cased. |
| `RedactAnnotation` | A /Redact annotation (PDF 32000-1 §12.5.6.23): a *mark* over a region, plus the overlay to paint when it is applied. |
| `StampAnnotation` | A /Stamp (rubber-stamp) annotation. |
| `StampPosition` | Where a stamp anchors in the page's visual frame. |
| `TextAnnotation` | A /Text (sticky-note) annotation: an icon-and-popup markup with no appearance stream. |
| `AnnotData` | Interface with 4 properties. |
| `AnnotationMatch` | A match in the text one annotation's appearance stream draws. |
| `AnnotationTextMatch` | A match in the text an annotation CARRIES, rather than the text it draws. |
| `CaretOptions` | Options for Page.AddCaret. |
| `FileAttachmentOptions` | Options for AddFileAttachment. |
| `ImportedAnnot` | An annotation that was applied to the document. |
| `LinkOptions` | Options for Page.AddLink. |
| `MarkupOptions` | Options for the Page.Add{Highlight,Underline,StrikeOut,Squiggly} methods. |
| `RedactAnnotationOptions` | Options for Page.AddRedact. |
| `SkippedAnnot` | An annotation that was present in the data file but not applied. |
| `StampAnnotationOptions` | Options for Page.AddStamp. |
| `StampOptions` | Options for stamping text onto a page. |
| `StampWithOptions` | Interface with 4 properties. |
| `TextBlockOptions` | Options for flowing wrapped text into a rectangle. |
| `TextNoteOptions` | Options for Page.AddTextNote. |
| `TimeStampRequestInfo` | Interface with 3 properties. |
| `TimeStampRequestOptions` | Interface with 3 properties. |
| `TimeStampTokenOptions` | Interface with 3 properties. |

### Attachments

| Class | Description |
|---|---|
| `Attachment` | A live handle over one embedded file's /Filespec. |
| `AttachmentOptions` | Options shared by document-level attachments and FileAttachment annotations. |

### Conversion

| Class | Description |
|---|---|
| `ImageFormat` | What `ImageOptions.format` accepts. |
| `MarkdownFontSpec` | A single face (whose family is derived when it is Standard-14) or an explicit family. |
| `AddMarkdownResult` | What AddMarkdown reports. |
| `ConversionReport` | The result of a conversion run: what was applied, what still fails, pass flag. |
| `ConvertAction` | One remediation performed by a converter (PDF/A or PDF/UA). |
| `DocxExtras` | Parts and relationships a caller adds beside the minimal set — styles, numbering, images. |
| `DocxOptions` | Options for ToDocx and ToDocx. |
| `EpubOptions` | Options for ToEpub. |
| `ImageOptions` | Interface with 9 properties. |
| `MarkdownAsset` | One image file an external-image export expects to be written. |
| `MarkdownElements` | What markdownElements produced. |
| `MarkdownExportOptions` | Options for ToMarkdown and ToMarkdown. |
| `MarkdownExportResult` | Markdown plus the image files it references. |
| `MarkdownFlowOptions` | Options for the Markdown entry points. |
| `MarkdownFontFamily` | The four faces emphasis selects between. |
| `MarkdownOptions` | Options for `parseMarkdown`. |
| `MarkdownResult` | What a Markdown entry point reports. |
| `MarkdownStyle` | How Markdown renders. |
| `TiffEncodeOptions` | Interface with 1 property. |
| `TiffExportOptions` | Options for renderDocumentToTiff. |
| `TiffFrame` | One page of a TIFF. |

### Forms

| Class | Description |
|---|---|
| `ButtonField` | A push button (`/FT /Btn` with the Pushbutton flag). |
| `CheckboxField` | A checkbox (`/FT /Btn`, neither Pushbutton nor Radio). |
| `ChoiceField` | A combo box or list box (`/FT /Ch`). |
| `Field-formfield` | A terminal AcroForm field: a live, mutable handle over its field dict. |
| `FieldType` | Class in the PDF TypeScript API. |
| `RadioField` | A radio group (`/FT /Btn` with the Radio flag). |
| `TextField` | A text field (`/FT /Tx`). |

### Redaction

| Class | Description |
|---|---|
| `MarkRedactTextOptions` | Options for `Page.MarkRedactText` — everything `AddRedact` takes except the geometry, which comes from the search hit, plus the search scope. |
| `ApplyRedactionsOptions` | Options for `Page.ApplyRedactions` / `Document.ApplyRedactions`. |
| `RedactOptions` | Options for redactPage / `page.Redact` / `doc.Redact`. |

### Security

| Class | Description |
|---|---|
| `DocMdpPermission` | DocMDP permitted-changes level for a certification signature (PDF 32000-1 §12.8.2.2): the `/P` value in the DocMDP `/TransformParams`. |
| `SignatureScheme` | Class in the PDF TypeScript API. |
| `CertifyOptions` | Options for Certify: a SignOptions plus the DocMDP permitted-changes level (default `no-changes`). |
| `DocumentTimestampOptions` | Options for AddDocumentTimestamp. |
| `EncryptOptions` | Interface with 5 properties. |
| `Permissions` | Interface with 8 properties. |
| `PubSecEncryptOptions` | Interface with 6 properties. |
| `PubSecRecipientCert` | Interface with 2 properties. |
| `SignOptions` | Interface with 12 properties. |
| `SignatureAppearance` | A visible signature appearance request. |
| `SignatureField` | Read-side view of a signature field (always available, like `doc.Form`). |
| `SignatureReport` | Interface with 13 properties. |

### Structure

| Class | Description |
|---|---|
| `OutlineDest` | An outline or link target: an explicit page, or a named destination. |
| `OutlineView` | A PDF 32000-1 §12.3.2.2 destination view. |
| `AddTOCResult` | The outcome of drawTOC / `page.AddTOC`. |
| `NamedDest` | A destination given by name, resolved by the viewer through the document's named-destination tables rather than at write time. |
| `NamedDestination` | A named destination: a name plus its resolved target. |
| `OutlineItem` | A node in the document outline (bookmark) tree. |
| `PageDest` | A page destination: 1-based page number plus an optional view. |
| `TOCEntry` | One row of a table of contents. |
| `TOCOptions` | Options for AddTOC. |

### Text

| Class | Description |
|---|---|
| `GlyphEvent` | A positioned glyph with provenance back to the operator that drew it. |

#### Detailed Member Reference

The tables below are the library's own, more granular member-by-member reference — every public
method and property grouped by the object it belongs to, each with a one-line description.

| Member | Description |
|---|---|
| `Document.New(format?)` | Create a document from scratch: zero pages, or one page of `format` |
| `Document.Open(buf, opts?)` | Parse a PDF from a `Uint8Array` |
| `Document.OpenFile(name, opts?)` | Parse a PDF from disk |
| `Document.Merge(...docs)` | Build a new document from the pages of several |
| `doc.Pages` | `Page[]` in document order |
| `doc.AddPage(source?)` / `doc.InsertPage(at, source?)` | Append/insert a blank page (A4, or a `PageFormat` size), or a copy of a `Page` source |
| `doc.RemovePage(numberOrPage)` | Remove a page |
| `doc.Reorder(order)` | Permute pages (1-based) |
| `doc.Split(options?)` | One single-page `Document` per page |
| `doc.ExtractPages(numbers)` | Copy a subset of pages (1-based, repeats allowed) into a new `Document` |
| `doc.Append(other)` / `doc.InsertPages(at, other)` | Copy another document's pages in |
| `doc.GetOutlines()` / `doc.SetOutlines(items)` | Read / replace the bookmark tree (`OutlineItem[]`) |
| `doc.GetPageLabels()` / `doc.SetPageLabels(labels)` / `doc.PageLabelFor(i)` | Read / replace `/PageLabels` (`PageLabel[]`); resolve a 0-based page index to its label |
| `doc.GetNamedDestinations()` / `doc.SetNamedDestination(name, dest)` / `doc.RemoveNamedDestination(name)` | Read / upsert / delete named destinations (`NamedDestination[]`) |
| `doc.GetOpenAction()` / `doc.SetOpenDestination(dest)` / `doc.SetOpenAction(action)` / `doc.RemoveOpenAction()` | The catalog `/OpenAction`: open at a view, or run an action. `GetOpenAction()` returns `{ kind: 'dest' \| 'action' }` |
| `doc.GetJavaScripts()` / `doc.SetJavaScript(name, script)` / `doc.RemoveJavaScript(name)` | Document-level scripts (`/Names /JavaScript`), sorted by name |
| `doc.GetAttachments()` / `doc.AddAttachment(name, bytes, opts?)` / `doc.RemoveAttachment(name)` | Read / upsert / delete document-level embedded files (`Attachment[]`, lazy `GetBytes()`) |
| `doc.GetCollection()` / `doc.SetCollection(settings)` / `doc.RemoveCollection()` | Read / write / remove the `/Collection` portfolio (schema, view, sort, initial file) |
| `attachment.GetField(name)` / `attachment.SetField(name, value)` / `attachment.RemoveField(name)` | Per-file portfolio custom field values (`/CI`); value is `string \| number \| Date` |
| `doc.GetMetadata()` / `doc.SetMetadata(update)` / `doc.ClearMetadata()` | `/Info` metadata (`ClearMetadata` also drops the XMP packet) |
| `doc.GetXmp()` | Read the XMP metadata packet (`/Root /Metadata`) as `XmpMetadata` |
| `doc.SetXmp(update)` | Write/merge the XMP packet (`null` deletes); mirrors shared fields to `/Info` |
| `doc.Save(opts?)` / `doc.WriteTo(fileName, opts?)` | Serialize (`{ compressed: true }` for xref + object streams; `{ streamFilter }` to re-filter data streams) |
| `doc.Save({ encrypt })` / `WriteTo(name, { encrypt })` | Write a standard-security-handler encrypted PDF (AES-256/128, RC4) |
| `doc.Save({ linearized: true })` | Write a linearized (Fast Web View) PDF; `doc.IsLinearized` reads the flag |
| `verifyLinearization(bytes)` | Re-check linearized output offsets + hint tables (`{ linearized, errors }`) |
| `doc.Form` | Interactive form: `Fields: Field[]`, `Get(fullName)`, `AddTextField(init)`, `GenerateAppearances()` |
| `page.AddTextField(init)` | Create a text field whose widget lands on this page → `TextField` |
| `TextField` | `Multiline`, `Password`, `Comb`, `MaxLen`; `ReadOnly`/`Required` on `Field` — all regenerate the `/AP` |
| `doc.Form.AddCheckbox(init)` / `page.AddCheckbox(init)` | Create a checkbox → `CheckboxField` |
| `doc.Form.AddRadioGroup(init)` | Create a radio group, one option per page/rect/export → `RadioField` |
| `doc.Form.AddComboBox(init)` / `page.AddComboBox(init)` | Create a dropdown → `ChoiceField` |
| `doc.Form.AddListBox(init)` / `page.AddListBox(init)` | Create a list box → `ChoiceField` |
| `doc.Form.AddPushButton(init)` / `page.AddPushButton(init)` | Create a push button → `ButtonField` |
| `ButtonField.Action` | Read/write the `/A` action (`goto`, `uri`, `submit`, `reset`, `javascript`) |
| `field.SetStyle(style)` | Restyle an existing field: `/MK` background, `/BS` border, `/DA` text; regenerates the `/AP` |
| `FieldStyle` on every `Add*` | `backgroundColor`, `borderColor`, `borderWidth`, `borderStyle`, `dashPattern`, `font`, `fontSize`, `textColor` |
| `field.Name` / `field.FullName` / `field.Type` | Field identity (`text`, `checkbox`, `radio`, `choice`, ...) |
| `field.Value` | Typed value; settable for text/checkbox/radio/choice (regenerates `/AP`) |
| `field.GenerateAppearance()` | Rebuild this field's appearance stream from its value |
| `field.Options` | Choice `/Opt` exports or button on-states |
| `page.MediaBox`, `page.CropBox` | Page geometry (inherited values resolved; settable) |
| `page.Rect` | Effective visible rectangle (= `CropBox`) |
| `page.BleedBox` / `page.TrimBox` / `page.ArtBox` | Print boxes (own key only, fall back to `CropBox`; settable) |
| `page.Rotate` | Rotation in degrees (settable) |
| `page.Resize(box, opts?)` | Set MediaBox+CropBox to `box`; `scaleContent` scales content to fill it (Bleed/Trim/Art untouched) |
| `page.Scale(factor)` | Uniformly scale content and every present boundary box by `factor > 0` |
| `page.Contents` | Decoded content stream bytes |
| `page.Annotations` | Typed `Annotation[]` handles (`.Dict` for the raw dict) |
| `page.RemoveAnnotation(a)` | Remove an annotation from the page |
| `page.AddTextNote(opts)` | Add a `/Text` sticky-note annotation (icon/open/color/author) |
| `page.AddStamp(opts)` | Add a `/Stamp` annotation (standard name, custom text, or image) with a generated appearance |
| `page.AddHighlight(opts)` | Add a `/Highlight` markup over `/QuadPoints` with a fill appearance (translucent by default; pass `opacity` to override) |
| `page.AddUnderline(opts)` | Add an `/Underline` markup over `/QuadPoints` |
| `page.AddStrikeOut(opts)` | Add a `/StrikeOut` markup over `/QuadPoints` |
| `page.AddSquiggly(opts)` | Add a `/Squiggly` (wavy underline) markup over `/QuadPoints` |
| `page.AddSquare(opts)` | Add a `/Square` rectangle annotation with a stroked/filled appearance |
| `page.AddCircle(opts)` | Add a `/Circle` ellipse annotation with a stroked/filled appearance |
| `page.AddLine(opts)` | Add a `/Line` annotation between two points, with optional end arrowheads |
| `page.AddPolygon(opts)` | Add a closed `/Polygon` annotation with a stroked/filled appearance |
| `page.AddPolyline(opts)` | Add an open `/PolyLine` annotation, with optional end arrowheads |
| `page.AddInk(opts)` | Add an `/Ink` annotation of one or more freehand strokes |
| `page.AddFreeText(opts)` | Add a `/FreeText` annotation: on-page text with a generated appearance, optionally with a callout leader |
| `page.AddCaret(opts)` | Add a `/Caret` text-insertion mark, optionally with a paragraph sign (`/Sy`) |
| `page.AddPopup(opts)` | Add a `/Popup` window bound to an existing markup annotation on the page |
| `page.AddLink(opts)` | Add a `/Link` annotation (internal GoTo or external URI) |
| `page.AddFileAttachment(opts)` | Embed a file and place a `/FileAttachment` icon annotation (`addToCatalog` to also list it) |
| `page.Graphics()` | Buffered `PageGraphics` builder for vector drawing (solid, axial- or radial-gradient, and tiling-pattern fills) |
| `doc.NewTilingPattern(w, h, draw, opts?)` | Create a reusable `PatternType 1` tiling pattern; `draw` paints one tile into a `VectorGraphics`. `opts`: `xStep`/`yStep` (default the tile size), `x`/`y`/`rotation` (degrees CCW) to place the lattice, `uncolored` for a `PaintType 2` tile whose colour is given at use time |
| `doc.NewTemplate(w, h)` | A reusable Form XObject template: draw into `tpl.page` with any authoring API, then `tpl.PlaceOn(page, [x, y, w, h], opts?)` (`fit`, `opacity`, `rotation`, `tag`/`alt`/`artifact`). One allocated object however many placements; the first placement freezes it |
| `g.setFillPattern(pattern[, color])` / `g.setStrokePattern(pattern[, color])` | Fill or stroke with a tiling pattern; `color` is required for an uncolored pattern and rejected for a colored one. The lattice is pinned to default user space and ignores the CTM, as a gradient is |
| `page.AddImage(data, rect, opts?)` | Embed and paint a JPEG, PNG, BMP or TIFF raster at `[x, y, w, h]` (`opts.page` selects an image of a multi-image TIFF) |
| `tiffPageCount(bytes)` | How many images a multi-image TIFF holds, for `AddImage`'s `page` option |
| `page.AddSVGObject(data, rect, opts?)` | Parse an SVG and draw it into `[x, y, w, h]` as a Form XObject (`fit` overrides `preserveAspectRatio`); shapes, `clipPath`, `use`, solid paint, `linearGradient`/`radialGradient` (→ PDF shading patterns) , `text`/`tspan` (`opts.font` supplies a face for families the Standard-14 set lacks) , `<pattern>` (→ PDF tiling patterns, including nested tiles and `overflow="visible"`), `<image>` (`data:` URI PNG/JPEG → Image XObjects and `image/svg+xml` → nested Form XObjects capped at 4 levels, with `opts.resolveImage` supplying bytes for any other href) and `<style>` rules (type/class/id/universal/grouped selectors plus descendant and child combinators, cascaded by specificity), `<mask>`/markers, and `<filter>` (all of SVG 1.1's primitives, rasterized at `opts.filterScale` except four chains PDF expresses exactly, which stay vector); returns `{ skipped, rasterized }` naming anything it could not render and anything it flattened to a bitmap |
| `page.AddText(text, x, y, opts?)` | Stamp single-line text at `(x, y)` (font/size/color/rotate/opacity/align; `shape`/`dir`/`script`/`language` for embedded fonts) |
| `page.AddTextBlock(text, rect, opts?)` | Flow wrapped text into `[x, y, w, h]` (align/valign/leading; shaping options as `AddText`); returns the overflow remainder or `null` |
| `page.AddTable(table, x, top, opts)` | Lay out a `createTable` table with its top-left at `(x, top)` and draw it (`opts.width` = total width; `cellPadding?`); paginates a too-tall table — returns `remainder` or, with `autoPaginate`, appends `pages` (`bottomMargin?`/`topMargin?`); repeat header rows with `table.setRepeatingRowsCount(n)`, span cells with `{ colSpan }` / `{ rowSpan }` (a rowSpan group is never cut across a page), embed a cell image with `cell.setImage(bytes, opts?)`; `{ tagged: true }` also emits `/Table` + `/TR` + `/TD`/`/TH` logical structure |
| `page.AddTOC(entries, rect, opts?)` | Render a table of contents into `[x, y, w, h]`: wrapped titles indented by `level`, a leader rule, right-aligned page labels (default: the target page's `/PageLabels` label), one borderless GoTo link per row; returns `remainder` or, with `autoPaginate`, appends `pages`; `{ tagged: true }` also emits `/TOC` + `/TOCI` logical structure |
| `doc.NewFlow(opts?)` | Start a multi-column document flow (`format`, `columns`, `columnGap`, `margin*`, `paragraphSpacing`, `keepHeadingsWithNext`, `tagged`) → `Flow` |
| `flow.AddParagraph(text, opts?)` / `AddHeading(level, text, opts?)` / `AddList(items, opts?)` / `AddImage(data, opts?)` | Append a flow element — body text, a level 1–6 heading, a nestable bullet/`ordered` list, or an atomic JPEG/PNG/BMP/TIFF block; all take `spaceBefore`/`spaceAfter`/`clear` |
| `flow.AddCodeBlock(text, opts?)` / `AddQuote(blocks, opts?)` / `AddRule(opts?)` | Append a preformatted code block, a block quote (built with the `paragraph`/`list`/`codeBlock`/`quote` builders, nestable) or a thematic break |
| `flow.AddTable(t, opts?)` | Append a `createTable` table, paginated **by row** across columns and pages (`width`, `cellPadding`, `spaceBefore`/`spaceAfter`/`clear`); repeating headers via `setRepeatingRowsCount`, and one `/Table` for the whole thing under a tagged flow. Contrast `page.AddTable`, which is page-positioned |
| `flow.AddMarkdown(src, opts?)` / `page.AddMarkdown(src, rect, opts?)` / `doc.AddMarkdown(src, opts?)` | Render CommonMark (GFM with `{ gfm: true }`) — see [Markdown](#markdown) |
| `flow.AddHtml(src, opts?)` / `page.AddHtml(src, rect, opts?)` / `doc.AddHtml(src, opts?)` | Render an HTML document through the CSS cascade and box model — see [Features](#features) and [Limitations](#limitations) |
| `flow.AddColumnBreak()` / `flow.AddFloatBox(box, side)` | Force the next column, or float a `FloatingBox` left/right so text wraps beside it |
| `flow.AddFloatingBox(box, opts?)` | Place a `FloatingBox` in the flow itself (pull-quote/callout); atomic, nothing wraps beside it |
| `flow.Render()` | Single-shot: append freshly sized pages, paginate across columns → the `Page[]` it created |
| `doc.NewFloatingBox(opts)` | Build a box (`width`, `padding`, `border` incl. per-side `sides`, `background`, `spacing`, `alt`) to fill with `AddParagraph`/`AddImage` → `FloatingBox` |
| `page.MeasureText(text, fontSize?, font?, opts?)` | Rendered width in points for a Standard-14 or embedded font (`opts.shape` reflects shaping) |
| `doc.AddFont(bytes, opts?)` / `doc.AddFontFile(path, opts?)` | Register a TrueType/OpenType/WOFF/WOFF2 font, or one face of a `.ttc`/`.otc` (`{ shape }` to shape by default, `{ faceIndex }` to pick a face), returning an `EmbeddedFont` handle for `AddText`/`AddTextBlock` |
| `doc.RegisterFontFolder(dir, opts?)` | Search `dir` recursively when resolving a font by name (lazy; no I/O until a lookup). `{ sniff: true }` opens files under any extension |
| `doc.RegisterSystemFonts()` | Also search the platform's font directories (opt-in) |
| `doc.LoadFontByName(family, opts?)` | The face matching `family` (a name or a preference chain) at `{ weight, italic }`, ready to draw with — `undefined` when no registered folder holds it |
| `doc.ResolveFontByName(family, opts?)` | What a name would resolve to — family, subfamily, derived weight/slant, path, and whether the style matched exactly — without loading it |
| `doc.LoadFontFamily(family, opts?)` | The four faces emphasis selects between, ready for `AddMarkdown({ style: { font } })`; a slot is absent when no face plays that role |
| `page.StampWith(src, opts?)` | Stamp another page's content as a shared Form XObject (overlay/underlay, rect, opacity, rotate) |
| `doc.Overlay(src, opts?)` | Stamp one source page (or a `Document`'s first page) onto many pages — imported once, shared (`pages`, `underlay`, rect, opacity, rotate) |
| `doc.NUp(cols, rows, opts?)` | Impose pages `cols`×`rows` per sheet into a new `Document`, scaled-to-fit + centered (`pageSize`, `margin`, `gutter`, `order`, `drawBorder`) |
| `doc.Booklet(opts?)` | Impose pages as a saddle-stitch booklet into a new `Document` — padded to a multiple of 4, 2-up per printed side in fold order (`binding`, `pageSize`, `margin`, `gutter`, `creep`, `sheetsPerSignature`, `padSignatures`) |
| `doc.AddWatermark(opts)` | Stamp a text or image watermark across a page range — tokens, presets, `opacity`, `rotate`, overlay/underlay; the image is embedded once and shared |
| `doc.AddHeaderFooter(opts)` | Stamp `header`/`footer` cells (`left`/`center`/`right`) with `{page}`/`{total}` tokens (`pages`, `margin`, `font`, `fontSize`, `color`, `opacity`) |
| `doc.AddBatesNumbering(opts?)` | Stamp a Bates sequence (`start`, `step`, `digits`, `prefix`, `suffix`), counting stamped pages; returns the next unused number |
| `page.GetText()` | Extract visible text as a `string` (encoding/ToUnicode/Type0 aware; `""` if none) |
| `page.GetTextFragments()` | Extract positioned text as `TextFragment[]` (`text`, page-space `quad`, `fontSize`, `fontName`, `bold`/`italic`, and `script: 'sub' \| 'super'` for a run that reads as a sub/superscript of its line; `[]` if none) |
| `page.GetStructuredText()` | Extract text as a `TextBlock[]` tree (blocks → lines → fragments, each with `text` + page-space `quad`; `[]` if none) |
| `page.GetPaths()` | Extract painted vector paths as `PagePath[]` (user-space `subpaths` of line/cubic segments + `ctm`, device `bbox`, resolved `fill`/`stroke` `{rgb, space}`, `fillRule`, `lineWidth`, `clip`, `mcid`/`artifact`; descends into Form XObjects; `[]` if none) |
| `page.GetTables(options?)` | Reconstruct tables as `Table[]` (`rowCount`, `colCount`, `rows` → `TableCell[]` with `row`/`col`/`rowSpan`/`colSpan`/`quad`/`text`/`tables`), each with `toHtml()` / `toMarkdown()`. Tagged PDFs are read from the `/Table` structure tree automatically (adding `isHeader`/`scope`/`id`/`headers` per cell, section per row, table `summary`, and `tables` for nested tables inside a cell, with `toHtml()` emitting `<thead>`/`<tbody>`/`<th scope>`/`<caption>` and nested `<table>`s); untagged pages fall back to geometry. `options.region` limits extraction, `options.structure = 'off'` forces geometry-only; `[]` if none. Rotated/skewed tables (ruled and borderless) are detected too: the geometry runs in the table's upright frame and `Table.angle` (radians, 0 for axis-aligned) records the rotation |
| `doc.GetTables(options?)` | Extract tables from every page and stitch cross-page continuations into single `Table[]` (`pageSpans` records the contributing page rectangles); `{ stitch: false }` returns the flat per-page list. Same `options` as `page.GetTables` |
| `page.Search(find, options?)` | Find a string/`RegExp` → `TextMatch[]` (`text`, per-line `quads`, glyph `hits`). `options.region` restricts the search to a page-space rect |
| `page.SearchAnnotations(find, options?)` | Find a string/`RegExp` in the text the page's annotations **draw** (`/AP` appearance streams) → `AnnotationMatch[]` (`annot`, `text`, per-line `quads`), in `/Annots` order. Same `options.region`. Only annotations a static render would draw are searched (not Hidden, NoView or `/Popup`); a match carries no glyph `hits` |
| `page.SearchAnnotationText(find)` | Find a string/`RegExp` in the text the page's annotations **carry** — `/Contents`, `/T` (author), `/Subj` — → `AnnotationTextMatch[]` (`annot`, `key`, `value`, `text`). Searches **every** annotation, hidden ones included. No geometry and no options, deliberately |
| `page.ReplaceText(find, replacement, options?)` | Replace matches in place (same font/encoding, no reflow) → count. Takes `options.region` |
| `doc.ReplaceText(find, replacement)` | `ReplaceText` across every page → total count |
| `page.Redact(rects, opts?)` | Remove text/images under `[x0,y0,x1,y1]` regions, prune orphans, paint markers |
| `doc.Redact(page, rects, opts?)` | Redact one page by 1-based number (convenience over `page.Redact`) |
| `page.RedactText(find, opts?)` | Redact every occurrence of a string/RegExp on the page; returns the count. `opts.region` scopes the search |
| `doc.RedactText(find, opts?)` | Redact every occurrence across all pages; returns the total count |
| `page.AddRedact(opts)` | Add a `/Redact` **mark** over a region (removes nothing until applied) |
| `page.MarkRedactText(find, opts?)` | Mark every occurrence of a string/RegExp; returns the count |
| `doc.MarkRedactText(find, opts?)` | Mark every occurrence across all pages; returns the total count |
| `page.ApplyRedactions(opts?)` | Apply the page's marks: destroy content, paint overlays, drop the marks |
| `doc.ApplyRedactions(opts?)` | Apply every mark across all pages; returns the total count |
| `page.FlattenAnnotations()` | Bake this page's annotation appearances into content, drop them from `/Annots` → count |
| `doc.FlattenAnnotations()` | `FlattenAnnotations` across every page → total count |
| `doc.FlattenForm()` | Generate field appearances, bake widgets into content, drop the `/AcroForm` → count |
| `field.Flatten()` | Bake one field's widgets and unwire it from `/AcroForm /Fields` → count |
| `annotation.Flatten()` | Bake one annotation (unwiring its field when it is a widget) → boolean |
| `doc.ExportFdf(opts?)` / `doc.ExportXfdf(opts?)` | Export form-field values as FDF / XFDF bytes (`{ includeEmpty, file, annotations }`) |
| `doc.ImportFdf(bytes, opts?)` / `doc.ImportXfdf(bytes, opts?)` | Import field values, regenerating appearances → `ImportReport` (`imported`, `skipped`, `importedAnnots`, `skippedAnnots`); `{ annotations }` to apply annotations |
| `doc.Optimize(opts?)` | Shrink in place: fonts/dedup/compress (lossless, each opt-out) plus opt-in lossy `images` → `OptimizeReport` |
| `doc.ConvertToGrayscale(opts?)` | Convert content, images, shadings and annotations to DeviceGray in place → `GrayscaleReport` |
| `doc.AutoTag(opts?)` | Infer a `/StructTreeRoot` (headings/paragraphs/figures/tables) from layout; marks Tagged; returns per-type counts |
| `element.MarkContent(page, region)` | Tag existing page content under a structure element (returns the MCID) |
| `page.ToSvg(options?)` | Render the page to a standalone `<svg>` string (paths, `<text>`, images, clipping, gradients, annotation `/AP` appearances; honors `/Rotate` + `CropBox`; `{ box: 'media' }` for the MediaBox, `{ annotations: false }` for content only) |
| `page.ToImage(options?)` | Rasterize the page to PNG bytes (`Uint8Array`); anti-aliased vector fills at `scale`/`width`/`height`; composites annotation `/AP` appearances (`{ annotations: false }` for content only); `{ background: 'transparent' }` for RGBA; honors `/Rotate` + crop/media box. `{ format }` selects the encoding — `'png'` (default), `'jpeg'`, `'tiff'`, `'bmp'` or `'gif'`, with `{ quality }` (1..100, default 75) read by the lossy ones and `{ compression }` (`'deflate'` default, `'none'`, or `'g4'` for bilevel frames) read by TIFF; an unsupported value throws `UnsupportedFeatureError` rather than returning PNG bytes under the wrong name (`IMAGE_FORMATS` lists what is supported), as does `{ format: 'jpeg', background: 'transparent' }`, JPEG having no alpha channel |
| `doc.ToHtml(options?)` | Export every page to one standalone HTML document. `mode: 'semantic'` (default, reflowable; `/StructTree`-driven when tagged, font-size heuristics otherwise) or `mode: 'fixed'` (positioned text over a `backdrop: 'vector'` SVG (default), a `'raster'` glyph-less PNG, or a `'page'` full-page PNG with transparent selectable text; `backdropScale` defaults to 2; `forms: true` for fillable AcroForm controls; with optional `fonts: 'embed'` \| `'embed-all'` `@font-face` embedding); `{ fragment: true }` for body markup only |
| `page.ToHtml(options?)` | Export one page to a standalone HTML document (same options; a tagged semantic tree is filtered to this page's content, ancestors intact) |
| `doc.ToMarkdown(options?)` | Export every page to one GFM Markdown document. Reconstructs the document from the `/StructTree` when tagged and from font-size heuristics otherwise: ATX headings, paragraphs, pipe tables via `Table.toMarkdown()`, and images inline as `data:` URIs. From a tagged tree it also recovers nested lists (bullet, ordered with `start`, and task), fenced code blocks with their indentation, and block quotes; untagged, it infers lists and code blocks from marker text and monospaced faces. Never throws on a document it could not fully reconstruct; the one refusal is `images: 'external'`, which has nowhere to hand the bytes back — use `ToMarkdownAssets` |
| `page.ToMarkdown(options?)` | Export one page to Markdown (same options; a tagged tree is filtered to this page's content) |
| `doc.ToMarkdownAssets(options?)` / `page.ToMarkdownAssets(options?)` | Markdown plus the image files it references → `{ markdown, images }`. With the default `images: 'inline'` the list is empty; with `images: 'external'` each distinct image is one `{ path, bytes, mediaType }` to write relative to the Markdown (`imageDir`, default `images`) |
| `doc.ToDocx(options?)` / `page.ToDocx(options?)` | Export to a `.docx` (Office Open XML) as `Uint8Array`. `mode: 'flow'` (default) reflows over the same model `ToHtml` and `ToMarkdown` read: `Heading1`–`Heading6`, styled runs, lists (nested, ordered, task), hyperlinks, images and tables. `mode: 'textbox'` keeps each page's own geometry instead — every run of text becomes a page-anchored `w:framePr` frame at its PDF position, with one section per page carrying that page's size, plus `backdrop: 'raster'` for a glyph-less render of the page's graphics behind the frames and `box: 'crop' \| 'media'`. Images travel inside the package either way, so there is no assets variant |
| `doc.ToTiff(options?)` | Rasterize a page selection into ONE multi-page TIFF (`Uint8Array`) — the interchange format for document archival, fax gateways and scanning pipelines. `{ pages }` is a 1-based list or a `"1-5,8,12-"` range string (default all); the rest are `ToImage`'s options, applied to every frame, plus `{ compression }` (`'deflate'` default, `'none'`). `background: 'transparent'` is honoured, TIFF carrying alpha where JPEG cannot |
| `doc.AddImagePages(data, options?)` | Append one page per frame of an image file, sized to each frame. A multi-frame TIFF (a scan or fax) becomes one page per frame; a JPEG/PNG/BMP becomes one page. `{ frames }` selects a 0-based subset (normalized ascending, deduped), `{ dpi }` sizes the pages (default 72 — one pixel per point). A frame that will not decode is reported in `skipped` and costs only its own page; throws only if no frame decoded |
| `page.Images` | `ImageInfo[]` of embedded images (recurses into Form XObjects) |
| `image.Width` / `image.Height` / `image.Bits` / `image.ColorSpace` / `image.Filter` | Image properties |
| `image.RawData` / `image.Decode()` | Encoded bytes / decoded samples (JPEG passthrough) |
| `image.Replace(data, options?)` | Swap the picture for JPEG/PNG/BMP/TIFF bytes, keeping its placement. Copy-on-write and scoped to the page the handle came from. `{ format }` overrides detection, `{ page }` picks a TIFF image |
| `page.InlineImages` | `InlineImageInfo[]` of inline (`BI…EI`) images, in content order (recurses into Form XObjects). Separate from `page.Images`, which enumerates image XObjects; neither contains the other's entries |
| `inlineImage.Remove()` | Drop one inline image and its placement group. Any other handle from the same enumeration is invalidated and will throw |
| `image.Remove(options?)` | Drop the image from the page: every draw of it (page content and nested Form XObjects) plus its `/XObject` entry. `{ sanitize: true }` also prunes every other now-unreferenced resource name |
| `parseContentStream(bytes)` | Tokenize a content stream into `ContentOp[]` |
| `serializeContentStream(ops)` | Serialize `ContentOp[]` back to bytes |
| `new EditableContent(doc, page)` | Low-level editable per-stream op model with Form-XObject copy-on-write (the foundation `Redact`/`ReplaceText` build on) |
| `mapRegions(doc, page, rects)` / `visitContent(doc, page, visitor)` | Map page-space rectangles to the glyphs/images that occupy them; walk content emitting positioned glyph/image/path events. An `ImageEvent` carries the image XObject as `stream` (undefined for an inline image) and the enclosing `mcid`, so marked content can be tied back to the bytes it draws |

> **Breaking change:** `page.Annotations` now returns typed `Annotation` handles
> instead of raw dictionaries. Use `page.Annotations.map(a => a.Dict)` for the
> previous behaviour. Each handle exposes typed, mutable accessors (`Rect`,
> `Color`, `Contents`, `Name`, `ModDate`, `Flags`, `Print`, `Hidden`, `Opacity`).

Errors: `PdfParseError`, `UnsupportedFeatureError`, `InvalidPasswordError`.

### HTML

`parseHtml(src)` parses a string as a full HTML document and returns the node
tree, following the WHATWG HTML Standard's tokenizer and tree-construction
stages. It **never throws**: every string is a valid HTML document, and the
spec defines a recovery for every parse error.

```ts
import { parseHtml } from '@asposefoss/pdf';

const doc = parseHtml('<p>Hello<p>World');
// doc.children[0]            -> <html> element
// html.children              -> [<head>, <body>]
// body.children              -> [<p>Hello</p>, <p>World</p>]
```

`parseHtmlBytes(bytes, options?)` is the sibling entry for HTML that arrives as
**bytes**, and works the encoding out the way the HTML Standard says to: a byte
order mark decides outright, else `options.encoding` (any Encoding Standard
label — `windows-1251`, `cp1251`, `Shift_JIS`), else UTF-8 corrected by the
document's own `<meta charset>`. Reach for it whenever you did not choose the
encoding yourself — `readFile(p, 'utf8')` on a legacy page is silent mojibake,
and the document is the only thing that knows better.

```ts
import { parseHtmlBytes } from '@asposefoss/pdf';
import { readFile } from 'node:fs/promises';

const doc = parseHtmlBytes(new Uint8Array(await readFile('legacy.html')));
// A <meta charset="windows-1251"> is honoured, and so is one sitting past the
// 1024-byte window a browser's prescan gives up on.
```

There is deliberately **no prescan**. HTML's exists so a *streaming* parser can
start tokenizing before it has seen a `<meta>`; with the whole buffer in hand
the `<meta>` rule in tree construction reaches the same answer, and reaches it
for a late `<meta>` a browser misses. The decoders are `TextDecoder`'s, so
legacy coverage depends on the Node build's ICU: on a `small-icu` build an
unresolvable label is ignored and the current encoding stands, never throwing.
A UTF-16 document with **no** BOM is not detected — the spec leaves that
implementation-defined and we decline to guess.

| Member | Description |
|---|---|
| `parseHtml(src)` | HTML text → `HtmlDocument`. Never throws |
| `parseHtmlBytes(bytes, opts?)` | HTML **bytes** → `HtmlDocument`, sniffing the encoding. Never throws |
| `ParseHtmlBytesOptions.encoding` | An encoding label from outside the document. Beaten only by a BOM; an unknown label is ignored |
| `HtmlNode` | `HtmlDocument` | `HtmlDoctype` | `HtmlElement` | `HtmlText` | `HtmlComment` | `HtmlProcessingInstruction` | `HtmlFragment` |
| `HtmlProcessingInstruction` | `<?target data?>`, per whatwg/html#12118. `xml` and `xml-stylesheet` targets stay bogus comments |
| `HtmlElement.ns` | `'html'` | `'svg'` | `'math'` — an inline `<svg>` parses into its own namespace |
| `HtmlElement.content` | A `<template>`'s content fragment. Absent on every other element |

The tree is mutable and carries parent pointers, but the mutation helpers are
not exported: this is a parser, not a DOM library. Anchored by **1,918 of
web-platform-tests' 1,936** tree-construction cases, all green — the rest are
the scripting flag and `<selectedcontent>`.

Rendering HTML into a page is not wired up yet.

### Markdown

```ts
import { parseMarkdown } from '@asposefoss/pdf';

const doc = parseMarkdown('# Title\n\nSome *emphasis* and a [link](/u).\n');
// doc.children[0] -> { type: 'heading', level: 1, children: [{ type: 'text', value: 'Title' }] }
// doc.children[1] -> { type: 'paragraph', children: [ ... 'text', 'emph', 'text', 'link' ] }

// GitHub Flavored Markdown is opt-in:
const gfm = parseMarkdown('| a | b |\n| :- | -: |\n| 1 | 2 |\n', { gfm: true });
// gfm.children[0] -> { type: 'table', align: ['left', 'right'], children: [ ...rows ] }
```

| Member | Description |
|---|---|
| `parseMarkdown(src, options?)` | CommonMark 0.31.2 text → `MdDocument`. Never throws |
| `{ gfm: true }` | Adds tables, task list items, strikethrough and extended autolinks. Off by default |
| `filterDisallowedHtml(html)` | GFM's disallowed-raw-HTML transform, for consumers emitting HTML. Not applied to the tree |
| `isMdBlock(n)` / `isMdInline(n)` | Which half of the node union `n` belongs to |
| `isMdContainer(n)` | Whether `n`'s children are blocks (`document`, `block_quote`, `list`, `item`, `table`, `table_row`) |

Nodes carry no source positions.

Rendering it onto a page is `AddMarkdown`, which takes either a source string or
a parsed `MdDocument`. A whole document in one call:

```ts
import { Document, PageFormat } from '@asposefoss/pdf';

const doc = Document.New();
const { pages, skipped } = doc.AddMarkdown(source, {
  gfm: true,
  format: PageFormat.A4,
  columns: 2,
  style: { fontSize: 10, quote: { indent: 18 } },
  resolveImage: (dest) => readFileSync(join(base, dest)),
});
// skipped names anything that did not render: 'table', 'html_block',
// 'image:<destination>'.
```

Into an existing flow, mixed with hand-built content:

```ts
const flow = doc.NewFlow({ format: PageFormat.A4, tagged: true });
flow.AddHeading(1, 'Report');
flow.AddMarkdown(body, { gfm: true });
flow.Render();
```

Into a rect, continuing the overflow yourself:

```ts
const { remainder, usedHeight } = page.AddMarkdown(src, [72, 72, 451, 698]);
if (remainder.length) placeElements(doc, nextPage, remainder, [72, 72, 451, 698]);
```

For a PDF/UA-conformant document, supply the two things the library will never
invent — the content's language and the document's title:

```ts
const doc = Document.New();
doc.AddMarkdown(source, {
  format: PageFormat.A4, gfm: true,
  tagged: true,
  lang:  'en-US',              // -> /Lang on the flow's /Sect
  title: 'Quarterly Report',   // -> /Info, XMP dc:title, DisplayDocTitle
});
doc.ValidatePdfUa().Passed;    // true
```

`lang` goes on the flow's own `/Sect`, not the catalog, so two flows in
different languages can share one document and appending a flow never relabels
the document it joins. It requires `tagged: true` and throws otherwise, since an
untagged flow has no element to carry it. `page.AddMarkdown` takes no `lang`:
it already accepts a `structParent` you own, and `element.Lang = 'en-US'` is the
equivalent.

Links and tables need no extra options. A link becomes a `/URI` annotation over
its own words — one rect per line it wraps onto, all pointing at the same
destination — and a GFM table paginates across columns and pages with its header
row repeating:

```ts
const { pages } = doc.AddMarkdown(`
See [the docs](https://example.com).

| Name   | Qty |
| :---   | --: |
| apples |  12 |
`, { gfm: true, format: PageFormat.A4 });
```

| Member | Description |
|---|---|
| `doc.AddMarkdown(src, opts?)` | Whole document → appended pages. Takes the Markdown options *and* the flow's page geometry → `{ pages, skipped }` |
| `flow.AddMarkdown(src, opts?)` | Append to a flow, mixing with hand-built content → `{ skipped }` (the one `Flow.Add*` that is not chainable) |
| `page.AddMarkdown(src, rect, opts?)` | Lay into `[x, y, w, h]` → `{ usedHeight, remainder, skipped }` |
| `markdownElements(src, opts?)` | The mapping on its own → `{ elements, skipped }`, for composing with the flow builders |
| `placeElements(doc, page, els, rect, opts?)` | Place a `FlowElement[]` into one rect → `{ usedHeight, remainder }` |
| `TextRun.link` | Make any rich-text run a hyperlink; a `/Link` annotation is placed over its laid-out glyphs. Works in `page.AddTextBlock`, flow paragraphs and table cells, not only in Markdown |
| `flow.AddTable(t, opts?)` / `table(t, opts?)` | A `createTable` table as a flow element, paginating by row across columns and pages |
| `lang` (flow option) | Natural language of the flow's content, written to its `/Sect`. Requires `tagged: true` |
| `title` (an `AddHtml` option) | Document title: `/Info /Title`, XMP `dc:title` and `/ViewerPreferences /DisplayDocTitle` |
| `doc.DisplayDocTitle` | Whether a viewer shows the title rather than the file name. Required true by PDF/UA |

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

- **Damaged-file recovery is partial** — `Document.Open` falls back to scanning the file for `N G obj` headers when the cross-reference structure cannot be read, when an object will not parse at the offset the xref gave, or when `/Root` does not resolve to a `/Type /Catalog`. `doc.recovery` then describes what was `repaired` and what was `lost`; it is `undefined` after a clean parse, and a healthy file is never scanned. Objects stored inside an `/ObjStm` carry no `N G obj` header of their own, but the container does, so the scan finds it and registers everything it declares. A container whose payload is damaged is decoded as far as it goes rather than dropped whole: the objects stored before the damage are recovered, the rest are reported in `doc.recovery.objectStreams` (one record per container, naming what it recovered, what it cost, and why), and a reference to a dropped object resolves to `null`. This is the one loss recovery cannot backfill — an object inside an `/ObjStm` exists nowhere else in the file — and the recovered bytes immediately after the damage point are best-effort, so an object that parses cleanly is kept and anything malformed is dropped. When no trailer survives anywhere, one is rebuilt: `/Root` is the `/Type /Catalog` object with a walkable `/Pages` at the highest file offset, and `/Info` is the metadata-bearing dict the catalog graph does not reach — or, failing that, the `/Root /Metadata` XMP packet. `doc.recovery.trailer` then reports both choices and every catalog candidate considered. Two limits: an encrypted document that lost its trailer also lost `/ID`, which RC4 and AES-128 hash into the file key, so those are refused with an error naming `/ID` (AES-256 and certificate-based encryption derive their keys without it and recover normally); and a scan cannot distinguish a live object from a freed one whose bytes remain, so a deleted object may be revived (harmless — `Save()` sweeps anything unreferenced). Strictness is unchanged for sound files: if the xref reads and `/Root` resolves, a malformed object still throws. `Save()` rewrites the whole reachable graph, so saving a recovered document produces a clean file; signing one throws, because incremental signing appends to the damaged original bytes.
- **Encrypted output passwords are UTF-8, not SASLprep-normalized** (R6), matching the read side. Opening an RC4/AES-128 file requires the *user* password (the reader does not derive the user key from the owner password for R≤4).
- **Public-key (PubSec) encryption** supports RSA recipients (RSAES-PKCS1-v1_5 or RSAES-OAEP key transport), EC recipients (ECDH-ES via `KeyAgreeRecipientInfo`, `dhSinglePass-stdDH-*kdf` + AES key wrap), and per-recipient permission groups (recipients sharing a permission set are grouped into one CMS envelope over a shared seed). Not supported: cofactor-DH KDF schemes, the `RecipientKeyIdentifier` rid form (only `issuerAndSerialNumber` is emitted/matched), and mixing password and certificate recipients in one document. Permissions are surfaced via `doc.Permissions` but not enforced.
- **Classic xref output by default** — `Save()` writes an uncompressed classic cross-reference table unless `{ compressed: true }` is passed, which emits a cross-reference stream and compressed object streams.
- **Linearization is classic-xref and plaintext only** — `Save({ linearized: true })` rejects `compressed: true` and `encrypt` (they throw `UnsupportedFeatureError`). Only the two mandatory hint tables (page-offset, shared-object) are emitted; the optional thumbnail / outline / thread / named-destination / form hint tables are not. The primary hint stream is `FlateDecode`-compressed (uncompressed when that would not shrink it). `qpdf --check` is the external conformance gate.
- **Page copies are pruned** — pages copied between documents lose document-level links such as `GoTo` actions, `/Dest`, and `/StructParents` (see `defaultPrunePolicy` / the `PrunePolicy` option to customize).
- **Text decoration is per-call, not per-run** — `underline` / `strikethrough` / `background` apply to a whole `AddText` / `AddTextBlock` call; there is no per-character or per-span decoration, and no double / wavy / dotted rule styles. Each stamp is decorated independently, which shows in a TOC row: it is three stamps (title, leader rule, page number), so its underline breaks at the `leaderGap` blanks either side of the leader rather than running unbroken across the row. `flow.AddList` decorates the item marker and the item body the same way — two runs with a blank gutter between them, not one rule spanning both. Standard-14 vertical metrics are per family (Helvetica / Times / Courier), not per face — bold and italic differ from their family's roman by under 2% of an em.
- **Auto-tagging is heuristic** — `doc.AutoTag` infers structure from layout: reading order follows `GetStructuredText`, headings are font-size based (modal size = body; larger sizes rank `H1`..`H6`), and undescribed images are marked `/Artifact` (no fabricated alt text). Tables are tagged from `GetTables` (`Table > TR > TH/TD`, first-row-header heuristic), but `THead`/`TBody`/`TFoot` grouping, nested tables (a cell's inner table is not separately tagged), and exact rotated-table cell regions are out of scope; lists remain untagged. It does not tag content nested inside Form XObjects, or blocks whose ops span multiple content streams; `MarkContent` wraps the contiguous op span of the single top-level stream with the most content in the region. A passing structure tree is a starting point for accessibility remediation, not a guarantee of correct semantics or reading order.
- **Tagged-PDF authoring tags what you author** — `CreateStructTree` and the `tag` / `AddAnnotation` / `NextMcid` APIs build a structure tree and tag content you add; `AutoTag` (above) infers structure for pre-existing untagged content heuristically. Typed attribute interpretation covers the Table, List, and Layout owners; other owners (`/PrintField`, `/Artifact`, `/XML`/`/HTML`/`/CSS`, …) remain available only through the raw `Attributes` passthrough. Authoring into a `/ParentTree` that uses an intermediate `/Kids` number tree (some large imported tagged PDFs) throws `UnsupportedFeatureError` — trees built by `CreateStructTree` use a flat `/Nums`. A page copied multiple times in a single `ExtractPages` call carries structure only on its first occurrence.
- **PDF/UA validation is a curated subset** — `doc.ValidatePdfUa()` checks objectively decidable PDF/UA-1 rules only. It does not validate reading-order correctness, table header / `/Headers` association, or link-text adequacy, and performs no rendering-based checks. The untagged-content check covers text, images *and* vector paths, but it is heuristic and reported at `warning` severity (one per page) — it tells you something on the page is unmarked, not what. A passing report is necessary but not sufficient for full PDF/UA conformance.
- **PDF/A validation is a curated, decidable subset** — `doc.ValidatePdfA(level)` checks objectively decidable ISO 19005 (parts 1–3) rules from the object model, catalog, metadata, resources, and content streams. It does **not** parse ICC profiles for validity, verify glyph presence inside embedded font programs, perform any rendering-based or visual-fidelity check, recursively validate *embedded* PDFs as PDF/A, or validate XMP extension schemas; PDF/A-4 is not covered. Some checks are heuristic (device-color detection from content operators; standalone ICC-stream `/N`). A passing report is therefore **necessary but not sufficient** for certified PDF/A conformance.
- **PDF/A conversion is best-effort and never fabricates assets** — `doc.ConvertToPdfA` fixes what is deterministically fixable and reports the rest as `unresolved`: it cannot embed a font whose program is absent (`FontEmbedded`), flatten part-1 transparency (`Transparency` — target part 2/3 instead), transcode LZW/JPX/JBIG2 streams, resolve external streams or reference XObjects, or rewrite a non-standard rendering-intent `ri` operator inside a content stream. Level `a` (auto-tagging) is out of scope. Because conversion re-validates, `passed` is true only when the validator agrees.
- **PDF/X validation is a curated, decidable subset** — `doc.ValidatePdfX(level)` checks objectively decidable ISO 15930 rules from the object model, catalog, metadata, resources, and content streams. It does **not** parse ICC profiles for validity, verify that spot-colour names resolve against the output intent, check ink coverage or overprint semantics, or perform any rendering-based check; X-5 is not covered. The registered-characterization-name list is a subset of the ICC registry, so an unlisted but genuine condition name is reported. A passing report is **necessary but not sufficient** for certified PDF/X conformance.
- **PDF/X conversion never silently changes printed appearance** — `doc.ConvertToPdfX` fixes structural defects and reports the rest as `unresolved`: it cannot flatten live transparency for X-1a/X-3 (target X-4 instead), embed a font whose program is absent, re-encode RGB raster images, or move an annotation that overlaps the trim area (moving it would change the printed page). `passed: false` with a populated `unresolved` list is an expected outcome, not a failed call. The opt-in `convertColor` RGB → CMYK rewrite is a naive maximum-black-removal formula applied to content-stream operators only (not images, not Form XObjects); without the destination profile the resulting ink values are **not** colorimetrically correct, so it is unsuitable for colour-critical work.
- **PDF/UA conversion is mechanical only** — `doc.ConvertToPdfUa` fixes the deterministic catalog/metadata defects (`/Lang`, `DisplayDocTitle`, `/Marked`, document title, `/RoleMap`, `/Suspects`, `pdfuaid`) and reports the rest. It never synthesizes accessibility content: alt text, reading order, heading/table/list structure, and the tagging of untagged content require human authoring and surface in `ConversionReport.unresolved`. It does not fabricate a structure tree for an untagged document. Because conversion re-validates, `passed` is true only when the validator agrees — necessary but not sufficient for full PDF/UA conformance.
- **Optimize subsets embedded TrueType and CFF fonts** — `doc.Optimize({ fonts: true })` shrinks Type0 programs (CIDFontType2 via `FontFile2`, CIDFontType0 via `CIDFontType0C`), simple TrueType (`FontFile2`), and simple CFF (`FontFile3` `/Subtype /Type1C`, including `Type1`/`MMType1` dicts pointing at one). Type1 `/FontFile` (PFB), Type3, and OpenType-CFF whole-embeds are skipped and listed in `report.skipped`, along with any font whose usage the scan cannot prove complete (an unparseable content stream in scope, a font no scan reached, a CFF with a predefined charset). Where a simple font admits several defensible code→GID chains — a symbolic cmap alongside `/Differences`, or a CFF with both a PDF `/Encoding` and a built-in one — the scan keeps the **union** of what every chain resolves rather than picking one: a wrong guess silently blanks a glyph that is actually shown, so Optimize never guesses. The same rule governs a font program shared by several font dicts (a `FontFile2`/`FontFile3` two dicts both point at): the program is shrunk **once**, against the union of the glyphs every dict reaching it shows, and an incomplete scan on any one of those dicts vetoes the whole program — so `report.fonts` carries one entry per *program*, not per font dict. Shrinking preserves GID numbering, `cmap`, `/Widths`/`/W`, and `CIDToGIDMap` — nothing is renumbered — so a font program is left alone when the rewrite would not be strictly smaller. A `post` v2.0 glyph-name table is rewritten to v3.0 (names dropped) only for programs reachable exclusively from Type0 dicts, which resolve code→CID→GID and never consult a name; a program any simple font dict can reach keeps its names, since a nonsymbolic simple TrueType resolves `/Differences` names outside the Adobe Glyph List through `post`. `Optimize` throws `UnsupportedFeatureError` on a signed document, which optimizing would invalidate. `/AcroForm /DR` pruning (`dr`, default on) removes only entries no `/DA` names and no appearance stream leaves unresolved against its own `/Resources`; it does not read `/XFA` (a document carrying one is skipped outright), does not prune the `/AcroForm /DA` default itself, and leaves `/ProcSet` alone. A `/DR` entry the AcroForm-level `/DA` names therefore survives the removal of every field — that `/DA` is the live default for the next field created.
- **Optimize's image pass recompresses photographic XObjects only** — `doc.Optimize({ images })` re-encodes 8-bit Gray/RGB/CMYK images (already-JPEG, or Flate/LZW-coded) as JPEG. It skips image masks, indexed palettes, bilevel (JBIG2/CCITT), anything carrying a `/Mask` or `/Decode`, colorspaces with no JPEG equivalent, and any image the content scan never saw drawn — including `/SMask` soft masks, which are referenced rather than drawn and so are left at full resolution. Inline images (`BI`) are not recompressed: replacing one means rewriting its content stream. Images drawn from a Type3 glyph procedure are skipped, since their effective DPI depends on text state the scan does not model.
- **Form appearances** — filling a field regenerates its `/AP` appearance stream (text, choice, and synthesized checkbox/radio marks), so values render without `/NeedAppearances`. Layout uses Standard-14 metrics; non-standard/embedded `/DA` fonts are measured with Helvetica as an approximation. Signature and pushbutton fields cannot be set.
- **XFA is never read or written** — an `/AcroForm /XFA` packet is not parsed, rewritten, or removed. Field creation, `Form.RemoveField`, `Field.Value` / `SetStyle`, and `ImportFdf`/`ImportXfdf` edit the AcroForm half of a form only, so in a hybrid XFA document the packet goes on describing the field set and values it was authored with — an XFA-aware viewer (Acrobat prefers the packet whenever one is present) shows those, every other viewer shows the edited AcroForm. Hybrid documents are edited rather than rejected, since their AcroForm half is usually perfectly editable; deleting `/XFA` from the `/AcroForm` dict and clearing the catalog's `/NeedsRendering` (both reachable via `doc.catalog()`) makes the AcroForm authoritative. Dynamic XFA layout is out of scope entirely, and `ConvertToPdfA` drops `/XFA` because PDF/A prohibits it.
- **FDF/XFDF scope** — `ExportFdf`/`ExportXfdf`/`ImportFdf`/`ImportXfdf` round-trip text, checkbox, radio, and choice values, plus (with `{ annotations: true }`) the 18 XFDF annotation types. Field reconfiguration entries (`/SetFf`, `/ClrFf`, `/SetF`, `/ClrF`), embedded FDF JavaScript, and page-level FDF data (`/Pages`, `/Differences`) are **not** carried. An annotation whose type is outside the XFDF vocabulary is reported in `skippedAnnots` rather than guessed at.
- **Annotation appearances across XFDF** — FDF carries `/AP` as a real stream, so it is exact. XFDF has no normative encoding for its `<appearance>` element, so producers disagree. Two are **read**: this library's own (base64 of the `/AP` `/N` form XObject as a one-object PDF fragment), which is also the only one **written**; and Acrobat's, which is base64 of an XML serialization of the COS objects rooted at `<DICT KEY="AP">` (`STREAM`/`DICT`/`ARRAY`/`INT`/`FIXED`/`NAME`/`BOOL` elements keyed by `KEY`, stream bytes in a `DATA` child with `ENCODING="HEX"` or `"ASCII"`). An `<appearance>` this library cannot read — a third producer's encoding, or a corrupt payload — is treated as absent and the appearance is **regenerated from the annotation's properties** instead, which is lower fidelity but never fails the import. Subtypes with no generator (`Sound`, `Text`, `Stamp`, `Link`, `FileAttachment`, `Popup`) import without an appearance in that case.
- **Annotation coordinates are untransformed** — `rect`, `coords`, `vertices`, `inklist`, `start`/`end` are exchanged in unrotated PDF user space, exactly as the annotation dictionary holds them. `/Rotate` and `/UserUnit` are not applied in either direction. Rich text (`/RV`) is transported verbatim but is **not rendered** into the generated appearance, which is built from the plain `/V`. The FDF writer emits no cross-reference table (permitted for FDF); the reader scans objects sequentially and ignores an xref if one is present. Imported values are validated exactly as `Field.Value` validates them, so a value the field rejects is reported in `skipped`, not applied.
- **Optional content is manipulation-only** (no rendering). `RemoveLayer` excises marked-content (`/OC … BDC … EMC`) blocks from page content streams, drops annotations bound to the layer, and removes `/OC` from bound XObjects, but does not delete an XObject (or its `Do`) that was used only by the layer, or recurse into Form XObject streams. OCMD membership is honored via both `/OCGs` and `/VE`, and `ResolveVisibility` interprets `/VE`/`/P`. Layer authoring covers new OCGs, `/Order` nesting (via a parent layer, not label-only headings), and `/OC` tagging of graphics/images/annotations; it does not author OCMD `/VE` expressions or auto-balance `BDC`/`EMC`.
- **Text authoring: Standard-14 or embedded sfnt fonts** — `AddText`/`AddTextBlock` accept the 12 Latin Standard-14 fonts (Helvetica/Times/Courier families, WinAnsiEncoding) or a font embedded via `doc.AddFont`/`AddFontFile`. Embedding supports TrueType (`glyf`, subset as `FontFile2`) and CFF OpenType (`.otf`, subset as `FontFile3` `/CIDFontType0C`, whole-embed fallback for malformed CFF), fed from raw sfnt (`.ttf`/`.otf`) or **WOFF/WOFF2** web fonts; **bare CFF, Type1/PFB, and bitmap fonts are not supported**, nor is hinting preservation or vertical writing. Complex-text shaping is **opt-in** for embedded fonts (`{ shape: true }`); with shaping off, text maps one code point → one glyph via the font cmap. `'justify'` spreads each line's slack across its inter-word gaps for Standard-14 text (the final line and single-word lines stay left-aligned), and falls back to left alignment for embedded fonts. `Symbol`/`ZapfDingbats` remain unavailable for authoring.
- **Markdown rendering covers the block and inline vocabulary** — `AddMarkdown` renders headings, paragraphs with inline styling (emphasis, strong, code spans, strikethrough), lists (tight/loose, nested, task items), code blocks, block quotes, thematic breaks, figures, GFM tables and links. What it does **not** do: raw HTML (`html_block`/`html_inline`) and syntax highlighting are out of scope and reported in `skipped`; an inline image (one not alone in its paragraph) renders as its alt text; a link with an empty destination (`[text]()`) is styled but not linked. A table's columns are sized from their content (proportional to each column's widest unwrapped line, floored at its widest word), since GFM declares no widths — use `flow.AddTable` with `setColumnWidths` for exact control. Emphasis selects from a four-face family, so an embedded face with no bold/italic sibling falls back to its regular face rather than being synthetically slanted or emboldened.
- **Complex-text shaping caveats** — shaping applies generic OpenType GSUB/GPOS only; there are **no script-specific reordering engines** (Indic / SEA / Khmer). GPOS cursive and mark-to-ligature attachment are best-effort. `justify` alignment falls back to left for shaped/embedded text. Standard-14 fonts do not shape (`shape` is ignored — WinAnsi/Latin only). Text is shaped **as-is with no Unicode normalization** — supply input in **NFC** form (the common case, handled well by fonts' `ccmp`/`mark` features) for best results; decomposed marks are not canonically reordered and are positioned by GPOS alone.
- **Image insertion is JPEG, PNG, BMP and TIFF** — `AddImage` accepts JPEG (`DCTDecode`, including CMYK), PNG (`FlateDecode`, including interlaced/Adam7 and palette `tRNS`), BMP and TIFF (both decoded to samples and stored as `FlateDecode`; the saved file carries no trace of the original container). Still unsupported in PNG: 16-bit-with-alpha, grayscale/RGB `tRNS` color-key masks, interlaced below 8-bit, and palette `tRNS` below 8-bit. For BMP, an embedded ICC profile in a `BITMAPV5HEADER` is ignored and the image read as sRGB; and a V4/V5 file that *declares* an alpha mask and then writes zeros everywhere renders fully transparent — that is the producer contradicting itself, and honouring the declaration is the reading the format supports, but it will look like a defect here. For TIFF, declined with a named reason: BIGTIFF, `PlanarConfiguration` 2, photometric YCbCr/CIELab/transparency-mask outside the JPEG route, old-style JPEG (compression 6), 16- and 32-bit samples, and floating-point `Predictor` 3. Other raster formats remain out of scope.

- **Redaction is rectangle-driven and removes whole glyphs/images** — `Redact` takes explicit regions; `RedactText` derives them from a text search (still rectangle-based underneath — a neighboring glyph whose box overlaps a match's union quad may be removed too, and device-space quads assume unrotated pages); any glyph whose box touches a region is dropped entirely. A fully-covered image is deleted; a partially-covered image is decoded, its covered pixels destroyed, and the image re-encoded — sample-preservingly (keeping the original colorspace and bit-depth) for `FlateDecode`/`LZWDecode`/`CCITTFaxDecode`, or as DeviceRGB for baseline/progressive/arithmetic/lossless/hierarchical JPEG (`DCTDecode`) and any image carrying an `/SMask`/`/Mask`. This covers both image XObjects and inline images, and rotated/skewed placements. Only `JPXDecode`, `JBIG2Decode`, and non-mask inline images that decode with an alpha channel throw `UnsupportedFeatureError` (transparency can't be represented inline). Rasterized text inside images is not detected (no OCR), and vector artwork under a region is covered by the marker box but not removed.
- **Vertical writing reaches extraction, `ToImage`, `ToSvg` and HTML fixed mode** — `/WMode 1` (the `-V` CMaps) advances glyphs down the page by `/W2`/`/DW2`, places each at its vertical origin, and extracts columns top-to-bottom ordered right-to-left. `page.ToHtml({ mode: 'fixed' })` emits one absolutely positioned `<span>` per glyph for a vertical run (one per *run* horizontally), so a column stacks by the font's own vertical metrics rather than by whatever advance a browser would choose. That makes a vertical page markedly more markup than a horizontal one.
- **Text replace is same-font, no-reflow** — `ReplaceText` re-encodes the replacement in the matched glyphs' existing font and encoding and edits the content stream in place; it does not change fonts, embed glyphs, or re-lay-out text. Positioning operators are preserved, so a replacement of a different width may overlap following text or leave a gap. Type0/composite fonts, and any character the font's encoding can't represent, throw `UnsupportedFeatureError`.
- **Table extraction: tagged `/Table` tree first, else geometry** — for a tagged PDF, `GetTables` uses the `/Table → TR → TH/TD` structure tree as the authoritative source for rows/cells/spans (`options.structure = 'off'` forces geometry). Otherwise it reconstructs tables from horizontal/vertical ruling lines and text position, axis-aligned or rotated. The ruled path needs at least one *interior* rule: a bare rectangle outline yields a 1×1 grid, which is page furniture rather than a one-cell table, and is not reported (this also keeps it out of `AutoTag`'s structure tree, where a one-cell `Table` announces decoration as data). Borderless-table detection is heuristic and conservative (loosely-aligned columns may be missed, and a candidate is rejected unless every column carries text in most rows), and `toMarkdown()` approximates spanning cells (colspan repeats the text, rowspan leaves blanks below). Nested tables are extracted in both paths — from the tagged `/Table` tree, and (for ruled tables) in the geometry path via rule-hierarchy detection (a rule spanning < 90% of the table extent is treated as confined; a container cell whose confined rules form a ≥2×2 grid becomes a nested table). Each nested table is attached to its parent cell's `tables`, rendered as an inner `<table>` by `toHtml()`, and its text removed from the parent cell. The ruled geometry path also returns multiple tables per page: page rules are partitioned into connected stroke components (a component whose bbox sits inside a larger one is treated as a nested table, not a separate one), so two or more distinct ruled grids surface as separate `Table[]` entries in top→bottom, left→right order. Geometry nesting is heuristic: a borderless/whitespace table is always **flat**, so a sub-grid inside one of its cells is flattened into extra columns of the outer grid rather than nested (a 2×2 whose right column holds its own 2×2 comes back as one 3×3), and it infers a **column span** conservatively: a row holding a single fragment whose text clears the column boundary the *other* rows imply, by a margin, becomes one cell with a `colSpan` (a header over two columns is the usual case). The boundary it is measured against is derived from the rows with the most common fragment count, because a spanning row distorts the boundary it crosses — so the yardstick has to exclude it. A long wrapped cell in one column is geometrically identical to a spanning header, which is why the margin is deliberately conservative and a missed span leaves the previous flat output rather than a wrong merge. **`rowSpan` is never inferred** here: rows come from baselines, so a cell covering two bands is indistinguishable from ordinary wrapped text. Right-aligned numeric columns are handled: the column gap is found from a whitespace-coverage histogram, so the cells need not share a left edge. Multiple borderless tables per page *are* detected — the whitespace path recursively XY-cuts the page on full-span whitespace bands and reports one table per region. Cross-page tables are stitched by `doc.GetTables()` when the continuation shares the same column count and aligned column positions (repeated headers dropped); non-tail continuations, column-count changes across the break, and spanning-cell reflow across the seam are not handled. Rotated and skewed tables are detected (the geometry runs in the table's upright frame, with `Table.angle` recording the rotation), but the angle is resolved **once per page** from the dominant glyph baseline — falling back to rule direction mod 90° when a candidate has no text — so two tables at different rotations on the same page cannot both be recovered, and `AutoTag` does not compute exact rotated-table cell regions.
- **Digital signing is single-pass** — `doc.Sign`/`doc.Certify` produce signatures with the `adbe.pkcs7.detached` (CMS, default) or `ETSI.CAdES.detached` (PAdES, via `opts.subFilter: 'PAdES'`) subfilter, invisible or with a generated visible appearance (`opts.appearance`), optionally certifying via DocMDP (`/Perms`) and/or carrying an RFC 3161 signature timestamp (`opts.timestamp`), with LTV validation data embeddable afterwards via `doc.AddValidationData` (`/DSS`). PAdES adds the ESS `signing-certificate-v2` signed attribute (CAdES-BES; combine with `opts.timestamp` for PAdES-B-T); the CAdES signed-attribute set is otherwise the CMS one (no commitment-type or signer-location attributes). The incremental-append path requires the in-memory model to be unchanged since `Open`; any mutation through a tracked entry point (including in-place handle setters on pages/annotations/form fields) switches signing to a full rewrite. **Verification** (`doc.VerifySignatures`) checks integrity (digest), the CMS signature, certificate-chain trust (to `trustAnchors`, with validity/CA/key-usage checks), any embedded timestamp (imprint + TSA signature), revocation (OCSP/CRL, when a `getOCSP`/`getCRL`/`offline`/`/DSS` source is supplied — signature-verified; the OCSP responder/CRL issuer is checked but not yet independently chain-validated), post-signing changes (revision/coverage), and `/DocMDP` enforcement for certified documents (the `docMDP` verdict is `ok`/`violated` against the certified permission level — `no-changes`/`form-fill`/`form-fill-and-annotate` — via a structural object-level change classifier, `n/a` for non-certified documents).
- **Annotation subtypes are a curated set** — create/edit covers `/Text`, `/Stamp`, the text-markup family (`/Highlight`, `/Underline`, `/StrikeOut`, `/Squiggly`), `/Link` (GoTo/URI), the geometric shapes (`/Line`, `/Square`, `/Circle`), the path shapes (`/Polygon`, `/PolyLine`, `/Ink`), `/FreeText` (with callout leaders), `/Popup`, `/Redact` (see [Redaction](#redaction) — `/RO` is read but never authored), and `/Caret` (`/Sy` symbol; `/RD` is read but never authored). Remaining subtypes (`/Sound`, `/Movie`, `/Widget`, ...) still read back as a base `Annotation` (use `.Dict`) but have no typed setters. Path shapes stroke straight segments through their points (no Bézier smoothing), and borders are a solid width only (no dashed/cloudy `/BS /D` or `/BE` styles). Highlights use a plain fill at `/CA` opacity (no blend modes), `/QuadPoints` are supplied by the caller (not derived from a text search), and `/D` (down) appearances are not rendered (`page.ToImage`/`ToSvg` composite `/N` only, as a static render has no mouse state).
- **SVG rendering is preview-grade** — `page.ToSvg()` emits text as positioned `<text>` styled by font family/weight (glyph-outline embedding is future work), so exact glyph shapes depend on the viewer's fonts. Annotation and form-field `/AP` appearances composite by default (`annotations: false` to opt out), sharing the interpreter with `page.ToImage()`. Images decode at 8-bit (other bit depths become a gray placeholder); `JPXDecode` (JPEG 2000) decodes to samples, while `JBIG2Decode` (1-bit) decodes but renders as a gray placeholder here since the SVG image path only rasterizes 8-bit samples (`page.ToImage()` renders JBIG2 fully). Axial/radial shadings render via the `sh` operator and as `scn` shading-pattern fills, clipped to the path — or, for pattern-filled text, to a `<clipPath>` holding the run's own `<text>` element (SVG 1.1 §14.3.5), which means the gradient shows through the *viewer's* glyph shapes rather than the PDF's outlines. Transparency constructs emit their SVG equivalents — tiling patterns become `<pattern>`, soft masks `<mask>`, constant alpha `fill-opacity`/`stroke-opacity`, blend modes `mix-blend-mode`, and isolated transparency groups an `<g opacity isolation="isolate">`. That output is verified against **browser-rendered goldens**: `scripts/gen-svg-goldens.ts` rasterizes it under headless Chrome and resvg, requires the two engines to agree with each other and with the hand-computed ISO 32000-1 §11.3.5.2 values, and commits the result to `test/fixtures/svg/` — so the suite checks real rendering with no test-time dependency (see that directory's `PROVENANCE.md` for exactly what is and is not covered). Constant alpha, luminosity soft masks, tiling-pattern fills, group compositing, and the separable blend modes plus `Luminosity` are covered. Stroke patterns (`SCN`) do render: an SVG `clipPath` uses only its children's *fill* geometry, so clipping to a stroked path directly would yield an empty clip — the stroke is therefore outlined (joins, caps, dashes, flattened Béziers) into device-space polygons and the clip is taken against those.
- **Transparency groups** — `page.ToImage()` buffers any `/Group` that composites as a unit (group alpha, a blend mode, or an active soft mask) regardless of `/I`, so overlapping content inside a group does not double-darken. For a non-isolated group whose contents also blend, the buffer is seeded with the page backdrop and the backdrop is subtracted back out at composite time (ISO 32000-1 §11.4.6), so inner blend modes see the page. `page.ToSvg()` is exact for every case except a non-isolated group that *both* composites as a unit *and* blends internally: SVG group `opacity` forces a stacking context, which isolates, so that one combination has no SVG expression. Knockout groups (`/K true`) — where each element composites against the group's initial backdrop rather than the accumulated result (§11.4.6.2) — render correctly in `page.ToImage()` (isolated and non-isolated); `page.ToSvg()` has no expression for per-element backdrop reset and renders a knockout group as an ordinary group. Offscreen nesting is capped at 8 deep and a single buffer at 16M pixels; past either, the construct draws inline instead of allocating further.
- **SVG `<image>` needs the bytes handed to it** — `page.AddSVGObject` decodes an `<image>` (or an `feImage`) href itself only when it is a `data:` URI. A relative path or an `http:` href is never fetched: the library does no I/O and takes no dependency. Supply those bytes synchronously through `opts.resolveImage` — `(href) => Uint8Array | undefined`, called for any href the library cannot decode itself, with `undefined` declining — or the element is skipped and named in `result.skipped`. Resolved bytes may be a PNG, a JPEG, or an `image/svg+xml` payload, which is drawn as a nested Form XObject (a separate document: its ids, stylesheet and markers are not shared with the enclosing file) up to 4 levels of nesting.
- **DOCX flow mode reflows** — `ToDocx()` concatenates pages with **no page break** between them, exactly as `ToHtml` and `ToMarkdown` do. Headers, footers, footnotes and revision tracking are not exported, because the document model records none of them.
- **DOCX textbox mode is positional, not a renderer** — `ToDocx({ mode: 'textbox' })` places each run of text as a `w:framePr` text frame anchored to the page at its PDF position, one section per page carrying that page's own size, so a mixed-size document survives. It is a *reconstruction*, not a rasterization, and the differences are deliberate. Word re-measures the text with a substituted face, so a frame errs wide by design and the spacing **inside** a frame is Word's rather than the PDF's; the adaptive merge decides where one frame ends and the next begins, splitting at a gap wide enough to be a layout decision (a leader row, a two-column gutter) and joining everything closer, so a run of prose stays one editable box. Rotated and vertical runs are placed **unrotated** at their top-left, since a `w:framePr` frame has no rotation. `/Link` hyperlinks are not recovered. Vector ink — rules, fills, shadings — reaches the output only through `backdrop: 'raster'`, so a ruled table exports as positioned text with no rules by default. That backdrop is deliberately glyph-less: the frames are visible, so a full-page raster under them would draw every glyph twice, once baked in and once re-rendered by Word. HTML offers a second value, `'page'`, that rasterizes everything and makes the text transparent; WordprocessingML has no transparent run colour, so DOCX offers only the glyph-less backdrop. Annotation and form-field text is therefore absent, since it is drawn from `/AP` streams rather than as page text. Text drawn in a stroke-only render mode (`Tr 1`/`5`) reports its fill colour. The construct is `w:framePr` rather than a VML or DrawingML shape because it is ECMA-376 Part 1 and needs no extension namespace.
- **Emphasis is inferred, not read** (in all three exports) — a PDF records a *font*, not an emphasis. Bold and italic are derived from the producing font's descriptor and `/BaseFont` name, so a document that sets bold by using a bold face is recovered and one that fakes it with a stroke width is not.
- **Sub/superscript is inferred too, and only on `TextFragment`** — a PDF states no such thing, so `TextFragment.script` is derived from two pieces of evidence that must both hold: the run is materially smaller than its line's dominant size *and* its baseline is materially shifted from that size's baseline. Requiring both is what keeps OpenType mark positioning (a raised glyph at an unchanged size) from being labelled a script. It is producer-agnostic — it reads size and position, not `Ts` — so it catches the many producers that write a superscript by moving the text matrix. Three things it deliberately does not do: a raised run with no larger text on its line is not marked, since there is nothing to be a script *of*; a run whose baseline shift exceeds the line-grouping tolerance reads as its own line rather than a script; and all three exports consume it — DOCX as `w:vertAlign`, HTML as `<sub>`/`<sup>`, and Markdown as raw `<sub>`/`<sup>`, since CommonMark has no syntax for it and dropping it would lose the information (the same rule that makes `Table.toMarkdown` emit `<br>` for a cell newline) — so `H₂O` survives a round trip through any of them. It reaches DOCX from a tagged PDF too: the structure tree carries no line context of its own, so the classification runs once per **page** and each glyph looks its answer up — which is what makes the tagged answer identical to the untagged one rather than an approximation of it.
- **DOCX and HTML tables recover their ruling** — per-cell borders and shading are read from the page's vector ink, so a table ruled only between rows exports that way rather than as a full grid, and a shaded header row survives. Three limits: a **dashed** rule becomes solid, since the path model records no dash array; a **rotated** table is skipped and falls back to a uniform frame; and a **tagged** table has no geometry at all, so `AddTable({ tagged: true })` output round-trips less faithfully here than an untagged one — the structure tree records what a cell *is*, never what it looked like.
- **The package writer has no ZIP64**, so it refuses an archive above 4 GB or 65535 entries, and **Word compatibility is unverified in CI**: the tests prove the package is structurally conformant to ECMA-376, not that any particular consumer opens it.
- **XMP covers the known schemas** — `GetXmp`/`SetXmp` read and write Dublin Core, XMP basic, and PDF properties; `SetXmp` rebuilds the packet from those fields, so unknown/custom schemas present in a read packet's `raw` are not surgically preserved.
- **Stream decoding covers the byte filters; `Save({ streamFilter })` re-filters** — decoding supports `FlateDecode`, `LZWDecode`, `ASCII85Decode`, `ASCIIHexDecode`, and `RunLengthDecode` (with predictors and multi-filter chains), plus `DCTDecode` (baseline/progressive/arithmetic/lossless/hierarchical JPEG), `CCITTFaxDecode` (Group 3 1D/2D and Group 4), `JPXDecode` (JPEG 2000, to 8-bit samples), and `JBIG2Decode` (arithmetic generic/symbol/text + MMR, to 1-bit samples) at the image layer. Matching **encoders** (`ascii85Encode`, `asciiHexEncode`, `lzwEncode`, `runLengthEncode`) and an `encodeStream(bytes, filter)` helper build streams in those filters. `Save({ streamFilter })` now applies a document-wide re-encode pass over eligible data streams (ASCII targets armor over existing compression; `LZWDecode`/`RunLengthDecode` replace it); image-codec streams (`DCTDecode`/`CCITTFaxDecode`/`JPXDecode`/`JBIG2Decode`), XMP `/Metadata`, and structural streams are left as-is.
- **HTML export** — `ToHtml` ships both `mode: 'semantic'` (reflowable) and `mode: 'fixed'` (visual reproduction with absolutely positioned text over a vector or raster backdrop). A raster backdrop is a second pass through the rasterizer, so a raster-backed page costs one extra interpretation of its content and produces a much larger file than the vector default; `backdropScale` is the only lever on its size, since exposing width/height would let the raster's aspect ratio diverge from the page's. With `forms: true`, field values are exported as control values, so a **password field's value is present in the markup** — export it only from documents whose field data may be published. Field-level JavaScript (`/AA`) is not translated, so a form with calculated or validated fields keeps its values and loses that behaviour, and a `<form>` is emitted only when a SubmitForm button exists, so a form with no submit button cannot post anywhere. Fixed mode defaults to mapped CSS family stacks (Times New Roman / Arial / Courier New), so a viewer lacking a named font sees a small baseline drift (bounded by the ascent-ratio gap, well under a pixel at body sizes). `fonts: 'embed'` inlines each embeddable font program as a base64 WOFF `@font-face` (`'embed-all'` also embeds `fsType`-restricted fonts) so glyphs and metrics match the source. Embedding limits: non-embedded Standard-14 fonts fall back to the mapped stacks; a Type 1 (`/FontFile`) program IS embedded, converted to OpenType-CFF on the way out, which drops its hinting exactly as `AddFont` does for a `.pfb`; programs are embedded as-is (no re-subsetting to page-used glyphs); ligature and encoding-collision glyphs render from Private-Use codepoints (correct shape, but they copy/paste and search as PUA characters). Semantic mode ignores `fonts`. Semantic output carries no font styling by design. It does inline every image it emits as a `data:` URI, in both the tagged and untagged paths, so a picture-heavy document produces a large single file (the bundled showcase goes from ~24 KB to ~3.4 MB); there is no option to link images out. A `/Figure` whose content is an *inline* image (`BI`) keeps its `/Alt` but gets no `src` — the samples live in the content stream and in no object. Untagged list reconstruction (`<ul>`/`<ol>`) is not implemented — untagged bullets stay paragraph text, while tagged `/L`/`/LI` become real lists. Untagged heading levels come from font-size ranks, so a document whose headings are not larger than its body text yields `<p>` throughout. In tagged output, `/Lbl` and `/LBody` render as `<div>` inside their `<li>`, and structure types outside the mapped set fall back to `<div>`.
- **Markdown export covers headings, paragraphs, lists, code blocks, quotes, tables and images** — `ToMarkdown` reuses the same document reconstruction as semantic `ToHtml`, so it inherits that path's strengths and limits: tagged documents drive off the `/StructTree`, untagged ones off font-size ranks (a document whose headings are not larger than its body text yields paragraphs throughout). A tagged `/L` becomes a nested bullet, ordered (`start` preserved) or task list, a `/P` > `/Code` becomes a fenced block with its indentation intact, and a `/BlockQuote` becomes `>`-prefixed lines. **Untagged documents recover lists and code blocks from page geometry too**, provided the marker is text on the page: a line opening with `•`, `-`, `1.`, `(3)`, `iv.` or `☐` starts an item, nesting comes from the marker's indent, and a run of lines set in a monospaced face becomes a code block. Two limits there, both deliberate. A marked line needs corroboration — a neighbouring item or a continuation indented to its body — so a genuinely single-item list is missed rather than reading `1990. It was a good year` as a list; and a block quote has no untagged form at all, since indentation alone is not evidence of quoting. One consequence is worth stating plainly: documents *this library* renders draw their bullets and task boxes as vector geometry (WinAnsi has no ballot-box glyph), so an untagged rendering of a **bullet** list carries no marker to recognise — round-tripping one needs `{ tagged: true }`, while an ordered list round-trips either way. Links are recovered as `[text](uri)` on both paths: tagged from the `/Link` element's annotation, untagged by resolving each `/Link` annotation's rectangle to the glyphs it covers. Only external URIs become links — an internal `GoTo` names a page object rather than an address, so it renders as its text — and a linked phrase that appears twice on one line is left unlinked rather than guessed at. Images are emitted inline as `data:` URIs by default; `ToMarkdownAssets({ images: 'external' })` instead references one file per distinct image and returns the bytes to write (`saveMarkdownFile` does both from disk). Identical images are deduplicated by content in either mode, so a picture repeated across pages is encoded once and, externally, written once. `ToMarkdown` throws on `images: 'external'`, since a string has nowhere to return the bytes and the links would point at files nobody wrote. Table cells go through `Table.toMarkdown()`, which escapes the full inline set, so a cell containing `*`, `_`, `` ` `` or `[…](…)` reads back as its own text. What GFM's table grammar cannot express is reported rather than dropped: a nested table follows its parent as a separate table, a `/Summary` becomes a paragraph above it, and a cell's line breaks become `<br>`. Column alignment is not emitted, because extraction records none. A table that reports its structure and names no header row gets an empty header row (GFM requires one); a geometry-detected table, which reports no header information either way, keeps its first row as the header.
- **EPUB navigation is chapter-level** — `ToEpub` splits at the shallowest heading level the document actually contains, so the navigation lists chapters but not the sub-headings inside them; a nested TOC would need an `id` anchor on every heading, which the shared HTML serializer does not emit. A document with no headings at all is one chapter, and inference quality is inherited from the document model: a tagged PDF splits off its `/StructTree`, while an untagged one splits off font-size ranking and yields one chapter when its headings are not larger than its body text. There is no `Page.ToEpub`: a book is a document. Structural conformance to EPUB 3 is tested — the stored first-entry `mimetype`, a container resolving to the OPF, every manifest href resolving to a part, every spine idref to a manifest item, and well-formed XML throughout — The suite stays hermetic, so no test opens a reader — but opening in **Calibre 7.26.0** was verified by hand and recorded in [docs/epub-calibre-verification.md](docs/epub-calibre-verification.md), including which evidence does and does not prove the navigation document is read. Other readers, `epubcheck`, and fixtures carrying images, tables or CJK text remain unverified.
- **Bundled fonts add ~3.1 MB to the library** — `Page.ToImage()` embeds deflate-compressed TrueType outline data for the 14 Standard-14 substitute faces so non-embedded text rasterizes as real glyphs. Sources: Liberation (SIL OFL 1.1) for the 12 Latin faces, and URW Standard Symbols PS / Dingbats (AGPLv3 + font exception) for Symbol/ZapfDingbats; license texts and provenance live under `fonts/`. Only the generated data ships in the package (the raw font files are excluded); regenerate it with `npm run gen:fonts`. Symbol/ZapfDingbats coverage is best-effort (glyphs the substitute cmap cannot resolve fall back to a placeholder box), and subsetting the bundled faces to shrink this footprint is future work.

- **HTML rendering is a documented subset** — the parser and cascade beneath it are conformance-tested against vendored and browser-generated corpora (6,995 tokenizer cases, 1,918 tree-construction cases, 149 CSS syntax cases, plus Blink-generated selector, cascade and box goldens), but the *renderer* does not yet draw everything they can describe. **What it cannot draw, it reports** — `skipped` names every construct with the element it came from and whether it was *dropped* or *degraded*, so a caller can tell a lost subtree from an approximated one, and from an empty document. **Floats place**: a floated box is painted at the channel edge, text narrows beside it and resumes at full width below it, `clear` drops past it, and an auto-width float is shrink-to-fitted rather than filling the column. Three limits, each reported or documented: a float that does not fit leads the next column WHOLE rather than splitting; two same-side floats stack rather than sitting side by side, and the pair is reported as `float`/`degraded`; and a float that can neither fit nor fragment lays out in flow and is reported as `float`/`degraded` too. **Content taller than an empty column renders rather than refusing the document**: an image scales to fit, aspect preserved, and anything that cannot be scaled draws past the column bottom, reported as `image:scaled-to-fit` and under the `overflow` construct respectively. Both are decided while *placing*, so `doc.AddHtml` and `page.AddHtml` — which place before they return — include them in `skipped`, while a `Flow`, whose `AddHtml` returns before `Render` runs, takes an `onNotRendered: (r) => void` callback instead. `page.AddHtml` never draws outside the rect you gave it: an element it cannot scale comes back in `remainder`. Tables and images render, with three documented degradations: a cell holding block content (a `<p>`, a nested list, a nested table) flattens to its text, because the authoring layer's cells take runs rather than elements; CSS column widths are not read, so columns auto-fit; and four cell border edges that differ collapse to the first painted one's width and colour. **An `<img>` among words renders inline**, sized from `width`/`height` or its intrinsic pixels and clamped to the column if wider, honouring `vertical-align: baseline`, `top` and `bottom` — `middle` is not implemented and is reported, since CSS defines it against half the x-height, which the AFM tables do not expose. **Inline `<svg>` RENDERS**, through the same importer `page.AddSVGObject` uses, sized as a browser sizes it — a viewBox-only graphic fills its container, and what the importer could not draw is reported as a `text`-style `svg` record rather than lost. **`<iframe>` and `<math>` content is still deliberately not drawn**, because no browser draws the first — an `<iframe>`'s children are "ignored by conforming user agents" — and there is no MathML importer here. `<object>`, `<video>`, `<audio>` and `<canvas>` children *do* render, being genuine fallback content. **Form controls are text, not widgets**: an `<input>`'s value, a `<select>`'s selected option, a `<textarea>`'s content and a `<button>`'s caption are drawn as ordinary text — except `type=hidden` and `type=password`, which draw nothing, since a password value must never reach a content stream. `display: inline-block`, `vertical-align` and padding on an inline box are reported rather than implemented. A fragment-only `href` (`#intro`) gets no link and is reported: a `/URI` action pointing at a fragment looks clickable and does nothing, which is worse than no link. Also absent: `@property` and registered custom properties, `env()`, `@media` feature queries (media *types* are honoured, features are reported), absolute and relative positioning, `inline-block`, `vertical-align` and inline padding, and `vw`/`vh` units. What does render: block and inline formatting contexts, margins with collapsing, padding, borders and backgrounds, `width`/`height` (the latter as a minimum), `line-height`, `text-align`, `text-decoration`, colours, headings and lists, and the math functions `calc()`, `min()`, `max()` and `clamp()` at every length, percentage and number site — type-checked, so `calc(1px + 2)` is refused and reported rather than guessed at, and with one deliberate divergence from browsers: `calc(10px / 0)` is refused where Chrome follows CSS Values 4 and computes 33554432px. **Custom properties and `var()`** render too, with inheritance, `!important`, case-sensitive names, shorthands and `calc()`; an unresolvable `var()` falls back to inherited-or-initial as CSS specifies and is reported as `undefined-var` or `var-cycle` rather than silently dropped, and a substitution is capped at 65,536 tokens (a deliberate divergence: Chrome expands further). Selector support reaches `:has()`, `:lang()` and `:dir()` — the last two answered from the DOM, with `dir=auto` resolved by first strong character rather than defaulted. **Text the resolved face cannot encode is dropped — and reported.** With no `RegisterFontFolder` call the fallback is Standard-14 with WinAnsi, which has no code for Cyrillic, Greek, CJK or anything else outside Latin-1, so such text draws as nothing. It names itself as a `text` construct, `dropped` when the block drew nothing at all and `degraded` when only some characters vanished — the second being the failure you cannot see, since `alpha При omega` draws as `alpha  omega` and the page looks fine. `AddMarkdown` reports it as `text` / `text:partial`, and hand-built flow and page text through an opt-in `onUndrawable` callback. **No fallback face is substituted**: we report that Times cannot draw `При`, we do not go looking for a face that can — register a folder holding a face that covers the script and it renders normally. There is no oracle for the *rendering* step — the corpora anchor the parser, the cascade and the box arithmetic, while which builder a box goes through and where its ink lands are held by hand-built cases and mutation testing.

These limitations apply only to Aspose.PDF FOSS for TypeScript — they don't carry over to
[Aspose.PDF — Enterprise Edition](https://products.aspose.com/pdf/), which adds broader
proprietary-format support, rendering, and advanced document-processing capabilities this FOSS
build leaves unimplemented.

## Development and Testing

```bash
npm install        # dev deps only — TypeScript, vitest, tsx
npm test           # vitest run
npm run test:watch
npm run typecheck
npm run build      # tsc -> dist/ (ESM + .d.ts)
```

The bundled data tables are committed, so a normal build never regenerates
them. Each generator is pinned to the upstream version its module documents;
re-run one only when that pin moves:

```bash
npm run gen:fonts      # Standard-14 substitute font outlines
npm run gen:ucd        # Unicode character data (UAX #9 / #14, case folding)
npm run gen:entities   # HTML character references, for Markdown parsing
npm run gen:cmaps      # the 195 predefined Adobe CMaps
npm run gen:cidunicode # CID -> Unicode tables for the CJK collections
```

### Feature Showcase

[`examples/feature-showcase/`](examples/feature-showcase/) builds a single
document that exercises every major capability in one narrative — Standard-14
and embedded-font text (including Unicode, BiDi and Arabic shaping), image
embedding, every AcroForm field type, sixteen annotation subtypes, marked vs
applied redaction, single- and multi-page tables, vector graphics with gradient
fills, multi-column flow layout with floats, selective flattening, a clickable
TOC over `/PageLabels`, a nested outline, and N-up + booklet imposition sheets
rasterized by the renderer.

Six further sections cover capabilities with no counterpart in the Go original:

- **Barcodes & QR codes** — Code 128, EAN-13, UPC-A, EAN-8 and QR at two
  error-correction levels, as vector modules or a 1-bit `/ImageMask` stencil.
- **Optional-content layers** — a floor plan across six OCGs, one nested and one
  default-off, with an image and a barcode bound to layers of their own.
- **Tagged PDF** — one `AutoTag` pass over the whole document, plus
  hand-authored elements via `StructTreeRoot.Append` and
  `StructElement.MarkContent`.
- **HTML export** — the same document as reflowable semantic markup and as
  positioned pages with fonts inlined as WOFF.
- **Standards validation** — this document's own PDF/A-2b, PDF/X-4 and PDF/UA-1
  findings, and what `ConvertToPdfA` could and could not fix.
- **Digital signatures** — a certification signature with a DocMDP transform
  plus an appended approval signature, written to a signed sibling and verified.

Build it with:

```bash
npm run example:showcase   # examples/feature-showcase -> docs/feature-showcase.pdf
```

The PDF is not checked in — it is regenerated on every run with fresh `/Info`
dates, so tracking it would add a new 2.8 MB blob per commit for a document
nobody edited. Run the command above to produce it, along with four siblings.
All five are gitignored:

| File | What it is |
|---|---|
| `docs/feature-showcase.pdf` | the 21-page showcase document |
| `docs/feature-showcase.html` | reflowable semantic export |
| `docs/feature-showcase-fixed.html` | positioned export, fonts embedded as WOFF |
| `docs/feature-showcase-pdfa.pdf` | `ConvertToPdfA('2b')` applied to a copy |
| `docs/feature-showcase-signed.pdf` | certified + approval-signed copy |

The showcase does **not** pass PDF/A-2b, and its validation section says so
rather than validating a doctored copy: it stamps with Standard-14 faces that
are not embedded and carries no `/OutputIntent`. The honest report is the more
useful one — it is what a first run over your own files looks like.

The script re-opens what it wrote and asserts the claims the document makes
about itself — that the flattened page is inert while the AcroForm page stays
interactive, that applied redactions destroyed their values while unapplied
marks preserved theirs, that every navigation target resolves, that the layer
nesting and default-off state survive the save, that the late-filled pages are
hand-tagged, and that both signatures on the sibling verify with the
certification *not* covering the appended revision — so a regression fails the
run instead of producing a quietly wrong PDF.

Design specs and implementation plans live under [docs/superpowers/](docs/superpowers/). Issue tracking uses [beads](https://github.com/gastownhall/beads) (`bd ready`, `bd show <id>`); see [CLAUDE.md](CLAUDE.md) for the agent workflow.

Design specs and implementation plans live under [docs/superpowers/](docs/superpowers/). Issue
tracking uses [beads](https://github.com/gastownhall/beads) (`bd ready`, `bd show <id>`); see
[CLAUDE.md](CLAUDE.md) for the agent workflow.

## License

This project is licensed under the [MIT License](LICENSE). The MIT License permits use, copying,
modification, distribution, sublicensing, and commercial use, provided its copyright and
permission notice are retained. The software is provided without warranty.
