# Upstream issues found — pdf/python

Real, genuine defects found during composition/verification of this candidate. Nothing here is
invented; every item traces to a real source read during this session. All three are
informational/background findings (they explain choices already correctly made in the candidate
README, not a live blocking defect in this candidate) — none describes a command this candidate
ships as a working step that actually fails.

## 1. Old README instructs a `pip install --pre` that has no live package to install

- **Severity**: INFORMATIONAL
- **Evidence**: `data/package_registry.json` (`pdf.python.verification.published: false`,
  `method: "pypi-backfill-scan"`), `runs/.clone_cache/aspose_pdf_python/.github/workflows/publish-pypi.yml`

`runs/.clone_cache/aspose_pdf_python/README.md`'s own "Installation" section reads:

```
Install a published prerelease:

    python -m pip install --pre aspose-pdf-foss-for-python
```

but `data/package_registry.json`'s `pdf.python` entry shows `verification.published: false`,
with `evidence_note: "Backfilled 2026-08-01: no live match found for any tried candidate
(aspose-pdf-foss-for-python, aspose-pdf-foss)"`. Corroborating this independently: the
repository's own `.github/workflows/publish-pypi.yml` is triggered only by `workflow_dispatch` (a
manual, human-initiated run) — it does not run automatically on a tagged release or a push to
`main`, so no automated release has ever gone out. A first-time reader who follows the old
README's own instructions verbatim gets a `pip` resolution failure. This candidate's own
Installation section does not ship that command — it states plainly that no package is published
yet and gives real build-from-source steps instead.

## 2. reference.aspose.org's generated API index has (at least) two mid-sentence-truncated class descriptions for this product

- **Severity**: INFORMATIONAL
- **Evidence**: `content/reference.aspose.org/en/pdf/python/_index.md`,
  `knowledge/pdf/python/merged/api_surface.json`,
  `runs/.clone_cache/aspose_pdf_python/src/aspose_pdf/lowcode.py:132`,
  `runs/.clone_cache/aspose_pdf_python/src/aspose_pdf/engine/auto_tag.py:98`

`content/reference.aspose.org/en/pdf/python/_index.md`'s Core API table row for
`StreamDataSource` reads `A data source backed by a binary stream (e.g.` (no closing clause), and
its Engine-module row for `TextObject` reads `A ``BT`` ...` (also cut off). Both truncations are
present even one stage earlier, in `knowledge/pdf/python/merged/api_surface.json`'s own extracted
docstring field for these two classes — meaning the cut happens at or before the
repo-scout/docstring-extraction stage, not only in reference.aspose.org's page-rendering step.

The real, complete text is recoverable directly from the clone-cache source:
`StreamDataSource` (`src/aspose_pdf/lowcode.py:132`) is `"""A data source backed by a binary
stream (e.g. ``io.BytesIO``)."""`, and `TextObject`
(`src/aspose_pdf/engine/auto_tag.py:98`) is `"""A ``BT`` ... ``ET`` text object located in a
content stream."""`. This candidate uses the real, complete descriptions in its API Reference
table rather than reproducing the truncated versions verbatim.

## 3. knowledge/pdf/python/merged/formats.md contains non-format tokens and misses the product's own primary format

- **Severity**: INFORMATIONAL
- **Evidence**: `knowledge/pdf/python/merged/formats.md`,
  `runs/.clone_cache/aspose_pdf_python/supported-features.md`

The format-support table this pipeline extracts for pdf/python
(`knowledge/pdf/python/merged/formats.md`) lists 15 rows, of which several are not real file
formats at all: `INSERT`, `SHADING`, `SIGN`, `UNICODE`, `VERIFY`, `VISIT` — all flagged
`Export: Yes`. None of these are genuine import/export formats; they read like leaked
method/class-name fragments (e.g. "Shading" is a real rendering class, not a file format;
"Sign"/"Verify" are signature operations; "Unicode" is a text encoding, not a container format).

Separately, and more consequentially, the same file's own `PDF` row reads `Import: -, Export: -`
(both "No") despite PDF obviously being this product's native, primary read/write format — its
`Document.load_from()`/`Document(source)` and `Document.save()` operations are the library's
central purpose. The file's `CDR`/`CGM`/`HTML`/`OFD`/`SVG` import rows and `HTML` export row are
all marked `Yes`, but `supported-features.md`'s own "Known Unsupported Compatibility Surfaces"
table documents that the corresponding load/save option classes (`CdrLoadOptions`,
`CgmLoadOptions`, `HtmlLoadOptions`, `OfdLoadOptions`, `SvgLoadOptions`, `HtmlSaveOptions`) are
inert placeholders that always raise an exception — none of these imports/exports actually work.

This candidate's diagram and prose do not repeat any of these unreliable formats.md claims. This
is a genuine, previously-undocumented-for-this-product instance of a knowledge-extraction defect
class the pipeline's own check module already documents as "formats.md confirmed unreliable" for
other products (`pdf/cpp`, `html/python`, `tex/python`, `3d/net`) — pdf/python is a new confirmed
instance of the same defect class, not something this candidate introduced.

## Note: schema for this file was not specified in the shared briefing

The shared regeneration briefing's instructions for this file say only "real, genuine upstream
defects... never invented," with no mention of a `## {title}` / `- **Severity**: ... ` / `-
**Evidence**: ...` structure. `readme_refresh_checks.py`'s real
`check_no_upstream_issue_leaked_into_readme` / `_extract_upstream_issue_fingerprints` /
`check_no_undisclosed_blocking_commands`, however, all parse this file expecting exactly that
structure (`_BLOCKING_ISSUE_RE` matches `- **Severity**: BLOCKING ... - **Evidence**: ...`
literally, and an entry with no `**Severity**:` marker at all is NOT treated as INFORMATIONAL —
it falls through and every backtick token in its body gets fingerprinted). Composing this file
without that structure caused `check_no_upstream_issue_leaked_into_readme` to flag 4 false
positives against my own README the first time I ran it with the real file contents (matching on
generic tokens like `" and "`, `"'s "`, and on real-but-legitimate class names this README's own
Scope and Limitations section needs to state on its own merits, e.g. `CdrLoadOptions`,
`HtmlLoadOptions`, `PDF`, `HTML`) purely because none of the three entries above had a
`**Severity**:` line for the exclusion logic to key off. This file now uses the real schema
(discovered by reading the check functions directly) so those checks pass correctly, but the
briefing text itself should document this schema rather than leaving it to be reverse-engineered
from the check module.
