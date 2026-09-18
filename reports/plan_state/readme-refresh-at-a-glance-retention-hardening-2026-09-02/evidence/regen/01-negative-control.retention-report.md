# Retention report -- tex/python

## Summary

- **content**: excluded=4, reframed=8, verbatim=1
- **structural**: verbatim=1
- **code**: api_survived=3, verbatim=9
- **badge**: none
- **heading**: absorbed=4, present=6

**Needs attention (0)**: none

## Prose content units (13)

| unit | old content | disposition | target | verdict | found in | fidelity / missing words |
|---|---|---|---|---|---|---|
| u0001 | Pure-Python library for TeX/LaTeX processing. Parses TeX input and produces PDF, SVG, and  | merged_reframed | Intro | reframed | Intro (traced) | 0.83 (target_section) missing: hyphenation, input, patterns |
| u0002 | > **Status: Pre-Alpha.** The core engine and public API are under active > development. In | merged_reframed | Scope and Limitations | reframed | Scope and Limitations (traced) | 0.91 (target_section) missing: status |
| u0003 | - Python 3.10+ | merged_reframed | Installation | verbatim | Installation | 1.0 (target_section) |
| u0004 | For development: | merged_reframed | Development and Testing | reframed | Development and Testing (traced) | 1.0 (target_section) |
| u0005 | In-memory PDF: | excluded |  | excluded |  | 1.0 (document) |
| u0006 | Output to file directly: | excluded |  | excluded |  | 1.0 (document) |
| u0007 | Output to file: | excluded |  | excluded |  | 1.0 (document) |
| u0008 | Multi-page in-memory output: | excluded |  | excluded |  | 1.0 (document) |
| u0009 | SVG output is self-contained — glyph outlines are extracted from the bundled Computer Mode | merged_reframed | Key Capabilities | reframed | Key Capabilities (traced) | 0.62 (target_section) missing: contained, embedded, extracted, required, self, viewer |
| u0010 | `TeXJob.messages` returns a copy of the messages collected during the most recent run. `\m | merged_reframed | Key Capabilities | reframed | Key Capabilities (traced) | 0.59 (target_section) missing: appends, collected, copy, during, leading, prefix, recent |
| u0011 | `extra_format_paths` is searched after bundled format data and before the current working  | merged_reframed | Key Capabilities | reframed | Key Capabilities (traced) | 1.0 (target_section) |
| u0012 | The package registers a `logging.NullHandler` on the `aspose_tex` logger so applications c | merged_reframed | Development and Testing | reframed | Development and Testing (traced) | 0.93 (target_section) missing: receiving |
| u0013 | Released under the MIT License — see [LICENSE](LICENSE). Bundled Computer Modern fonts are | merged_reframed | License | reframed | License (traced) | 0.88 (target_section) missing: released |

## Structural units (1)

| unit | old content | disposition | target | verdict | found in | fidelity / missing words |
|---|---|---|---|---|---|---|
| s0001 | Options (generic_structural_block) | merged_verbatim | Additional Examples | verbatim | Additional Examples |  |

## Code units (12)

| unit | old content | disposition | target | verdict | found in | fidelity / missing words |
|---|---|---|---|---|---|---|
| c0001 | [Installation] pip install aspose-tex | corrected | Installation | api_survived | Installation, Development and Testing | 1/1 calls survive |
| c0002 | [Installation] pip install -e ".[dev]" | merged_verbatim | Installation | verbatim | Installation, Development and Testing | 1/1 calls survive |
| c0003 | [PDF output] source = create_input_source("Hello World\n\\bye") | merged_reframed | Quick Start | api_survived | Quick Start, Additional Examples | 6/6 calls survive |
| c0004 | [PDF output] source = create_input_source("Hello World\n\\bye") | merged_verbatim | Quick Start | verbatim | Quick Start | 5/5 calls survive |
| c0005 | [DVI output] source = create_input_source("Hello World\n\\bye") | merged_verbatim | Additional Examples | verbatim | Additional Examples | 5/5 calls survive |
| c0006 | [DVI output] source = create_input_source("Hello World\n\\bye") | merged_verbatim | Additional Examples | verbatim | Additional Examples | 6/6 calls survive |
| c0007 | [SVG output] source = create_input_source("Hello World\n\\bye") | merged_verbatim | Additional Examples | verbatim | Additional Examples | 5/5 calls survive |
| c0008 | [SVG output] source = create_input_source("Hello World\n\\bye") | merged_reframed | Additional Examples | api_survived | Quick Start, Additional Examples | 6/7 calls survive |
| c0009 | [SVG output] source = create_input_source("Page one\n\\eject\nPage two\n\\bye") | merged_verbatim | Additional Examples | verbatim | Additional Examples | 6/6 calls survive |
| c0010 | [Options] opts = TeXOptions(job_name="hello", magnification=1200, load_format=False) | merged_verbatim | Additional Examples | verbatim | Additional Examples | 5/5 calls survive |
| c0011 | [Messages and logging] opts = TeXOptions(load_format=False, extra_format_paths=[Path("tex- | merged_verbatim | Additional Examples | verbatim | Additional Examples | 6/6 calls survive |
| c0012 | [Messages and logging] logging.basicConfig(level=logging.INFO) | merged_verbatim | Additional Examples | verbatim | Additional Examples | 3/3 calls survive |

## Badges (0)

_none in the old README_

## Headings (10)

| unit | old content | disposition | target | verdict | found in | fidelity / missing words |
|---|---|---|---|---|---|---|
| h0001 | # aspose-tex |  |  | absorbed |  |  |
| h0002 | ## Requirements |  |  | absorbed |  |  |
| h0003 | ## Installation |  |  | present |  |  |
| h0004 | ## Quick Start |  |  | present |  |  |
| h0005 | ### PDF output |  |  | absorbed |  |  |
| h0006 | ### DVI output |  |  | present |  |  |
| h0007 | ### SVG output |  |  | present |  |  |
| h0008 | ### Options | structural_unit | s0001 | absorbed |  |  |
| h0009 | ### Messages and logging |  |  | present |  |  |
| h0010 | ## License |  |  | present |  |  |
