## Identity

Four artifact classes were sought; three were obtained directly, the fourth confirmed genuinely absent (not merely unchecked):

| Artifact | Status | Path / Ref | Hash |
|---|---|---|---|
| Candidate | Obtained | `reports/repo-presenter-regen-full/words/python/readme.md` | sha256 `755f24b18842679b5f8f84d32ade750ec73e1b2ec2fdb39753958fc0be49bf89` (matches `last-verified.json.readme_sha256` exactly; `verified_at: 2026-08-25T18:09:43Z`) |
| Current upstream | Obtained | `runs/.clone_cache/aspose_words_python/README.md`, HEAD `2d2efee2787cb9e56d071d17f8d7b740dce8b784` (2026-08-17 16:36:27 +0500, author Babar Raza <babar.raza@aspose.com>) | sha256 (CRLF-normalized) `9ef65e92ae664d9bf8cac9c98aa002fec48938cd547af00708e4f5536aeef1c0` |
| Original-at-generation-time | Obtained (= current upstream) | Same file/commit as above | Same hash — direct diff shows zero drift; `content-dispositions.json`'s embedded "old README" excerpts (e.g. `Document(filepath)`, `Body`→2 properties, `Pillow>=10.0.0`) are byte-for-byte present in this exact file, confirming it is the true generation-time source, not a later or earlier state |
| Published (real GitHub push via this pipeline) | Confirmed absent | — | No entry for `words`/`python` in `data/readme_published_state.json` (only `words`/`net` is listed) or in `reports/repo_presenter_actions.jsonl` (2 lines total: `note/python`, `cells/rust` — neither is this product). `gh api repos/aspose-words-foss/Aspose.Words-FOSS-for-Python/contents/README.md` (read-only) was fetched as a sanity cross-check regardless and found byte-identical (after CRLF normalization) to the clone-cache copy — confirming the clone cache is not stale, and confirming no pipeline-authored README has ever landed on the real repo for this product |

`git -C runs/.clone_cache/aspose_words_python log --oneline -- README.md` → `2d2efee docs: refresh README...` / `4473f8c 26.7.0` (only two commits ever touched it; no drift since generation).

## Factual Accuracy

Every checkable factual claim in the candidate was independently verified against clone-cache source and found accurate:
- Dependency versions (`olefile>=0.46`, `fpdf2>=2.7.5`, `pydantic>=2.0.0`, dev `Pillow>=10.0.0`, `pytest>=9.0.2`, `requires-python >=3.10,<3.13`) — exact match to `runs/.clone_cache/aspose_words_python/pyproject.toml` lines 15-19, 44-45.
- `Document(source=None, load_options=None, *, stream=None, data=None)` — exact match to `aspose/words_foss/document.py` lines 196-203.
- `PdfSaveOptions`'s "17 fields, 8 unused" claim — exact match: 17 fields counted in `saving.py` `__init__` (lines 209-260), and the named 8 (`text_compression`, `embed_full_fonts`, `use_core_fonts`, `font_embedding_mode`, `page_mode`, `color_mode`, `preserve_form_fields`, `memory_optimization`) are each individually marked `# Currently unused` in source.
- `MarkdownSaveOptions.image_resolution` dead-code claim in `upstream-issues.md` — confirmed via grep: exactly one repo-wide hit (`saving.py:387`, the assignment itself), zero reads.
- LICENSE path fact (root `LICENSE`, no `License/` dir, no `license.txt`) — confirmed via `git ls-files` in the clone cache: only `LICENSE` is tracked; a same-content lowercase `license` exists on disk but is untracked.
- One documented claim did **not** hold up under independent re-verification: `upstream-issues.md`'s assertion that "the repo's own root README.md links the license as `[LICENSE](License/license.txt)`" is false against the actual current file — see Verdict finding 1.

## Content-Preservation Ledger

A direct `diff` between the current-upstream/original README and the candidate (CRLF-normalized) produced exactly **5 hunks**, and every hunk corresponds one-to-one to a disclosed `"corrected"` unit in `content-dispositions.json`. No other differences exist anywhere in the 655-line file.

| Original unit(s) | Disposition | Verified holds? |
|---|---|---|
| Title, intro paragraph | PRESERVED (`merged_verbatim`, u0001) | Yes |
| Navigation (11 links) | PRESERVED (u0002-u0012) | Yes — all anchors resolve to real headings in candidate |
| At a Glance (mermaid diagram) | PRESERVED (s0001/c0001) | Yes, byte-identical |
| Key Capabilities bullet "`Document(filepath)` constructor" | TRANSFORMED → `Document(source)` (u0013, `corrected`) | Yes — real param name is `source` (document.py:198) |
| Remaining 9 Key Capabilities bullets | PRESERVED (u0014-u0023) | Yes, each verified against its cited source file |
| Installation, Quick Start, Additional Examples (9 worked examples incl. mermaid-adjacent code, table of 8 `ApiExamples/` scripts) | PRESERVED (u0024-u0045, s0002-s0006, c0002-c0016) | Yes — all 8 named scripts exist in `ApiExamples/`, all 6 named test fixtures exist under `tests/data/input/` |
| Dependencies: `Pillow>=10.0.0` / `pytest>=9.0.2` (single-backtick-wrapped in old README) | TRANSFORMED → `` `Pillow` >=10.0.0 `` / `` `pytest` >=9.0.2 `` (u0032/u0033, `corrected`) | Yes — old formatting broke `check_dependency_development_claim_not_in_manifest`'s name extractor; underlying dependency facts unchanged |
| API Reference: 8 class rows (Body, Border, Font, ImageData, Row, RowFormat, Style, Table) | TRANSFORMED → corrected property counts (u0048, `corrected`) | Yes — independently recounted from `light_document_model.py`: Body 4, Border 6, Font 32, ImageData 8, Row 4, RowFormat 6, Style 15, Table 15 — all match candidate exactly |
| API Reference: `ShapeNode \| 25 properties` row | Left uncorrected, **disclosed** in u0048's `excluded_reason` as a deliberate deferral | Yes — see Verdict finding 2 |
| Detailed constructor signature | TRANSFORMED (u0057, `corrected`) | Yes, matches document.py exactly |
| Everything else (Format Readers, Markdown/PDF/DOCX Export sections, Document Object Model, Enums, Documentation & Resources, Scope and Limitations, Development and Testing, License) | PRESERVED (u0058-u0097) | Yes, byte-identical to upstream |
| Badges (PyPI version, Python versions, License, Contributors) | PRESERVED (b0001-b0004) | Yes, byte-identical |

**No units of any kind were DROPPED-WITH-REASON, DROPPED-SILENTLY, or INCORRECTLY-EXCLUDED** across all 97 content units, 6 structure units, 4 badge units, and 18 code-example units. This is an unusually clean pass — the disposition files' self-report matches ground truth exactly.

## Usability

The README is well-structured: a working Navigation TOC (all 11 anchors resolve to real headings), a Mermaid "At a Glance" diagram, collapsible `<details>` blocks keeping the verbose API table and extra examples out of the main scroll path, and an actionable Development and Testing section (`pip install -e ".[dev]"` then `pytest`, with a fixture-location note). The u0057 correction added a cross-reference to `#load-from-a-stream`, which correctly resolves to the real "Load From a Stream" H3 heading in Additional Examples — the new link target was verified, not just assumed.

## Presentation/SEO

Single H1, consistent H2/H3 hierarchy, badge row (PyPI version, Python versions, MIT license, contributor count) followed by a banner image linking to `products.aspose.org/words/python/`. No frontmatter/meta-description fields exist in a plain README (not applicable to this artifact type). Reachability of the banner image and external links was not network-verified (no `WebFetch` used, consistent with a read-only forensic pass over repo state) — noted as unverified, not treated as a defect since the task's evidence sources are all local/API reads.

## Dependency Accuracy

All 5 named dependencies plus the Python version constraint match `pyproject.toml` exactly (see Factual Accuracy). The two disclosed `corrected` dependency-formatting fixes (u0032, u0033) changed presentation only, not the underlying version facts, and were necessary to stop a real name-extractor false positive (`_bulleted_dependency_names`, per the excluded_reason) from flagging genuine dependencies as fabricated.

## Example Verification

All 12 Python code blocks in the candidate parse as syntactically valid Python (`ast.parse` via the project's own `.venv` interpreter — 12/12 OK, no syntax errors). Every API symbol used in the examples was cross-checked against real source, not just assumed from prose:
- `aw.Document`, `aw.SaveFormat`, `aw.LoadFormat`, `aw.LoadOptions`, `aw.MarkdownLoadOptions`, `aw.saving` — all real top-level exports (`aspose/words_foss/__init__.py` lines 1-9).
- `aw.saving.CompressionLevel.MAXIMUM` — `CompressionLevel` is defined in `saving.py:271`, member `MAXIMUM = 1` at line 284.
- `OoxmlSaveOptions.pretty_format` (saving.py:351) and `MarkdownSaveOptions.encoding` (saving.py:392) both exist.
- All 8 named `ApiExamples/*.py` scripts and all 6 named `tests/data/input/*.docx` fixtures referenced in the README exist in the clone cache exactly as named.

Execution against the real installed package was not attempted (out of scope for a read-only audit; no package install/pytest run performed).

## API Accuracy

The 8 corrected API-table property counts were independently recounted directly from `light_document_model.py` field-by-field and matched the candidate exactly in every case: Body 4 (2 fields + 2 `@property`), Border 6 fields, Font 32 fields, ImageData 8 (7 fields + 1 `@property`), Row 4 fields, RowFormat 6 fields, Style 15 fields, Table 15 (13 fields + 2 `@property`). The disposition's "AST-verified" claim (u0048) holds.

`ShapeNode` does not exist as a class anywhere in the clone cache — the real class is `Shape` (`light_document_model.py:494`), independently recounted at 24 properties (all fields, no `@property` methods). The candidate still carries the incorrect `ShapeNode | 25 properties` row unchanged from upstream; this is **disclosed**, not silent (see Verdict finding 2).

## Link/Rendering

All internal Markdown anchors in the candidate (`#at-a-glance`, `#key-capabilities`, `#installation`, `#dependencies`, `#quick-start`, `#additional-examples`, `#api-reference`, `#documentation--resources`, `#scope-and-limitations`, `#development-and-testing`, `#license`, `#load-from-a-stream`) resolve to real, correctly-slugged headings present in the candidate itself. The Mermaid `flowchart TD` block in "At a Glance" is syntactically well-formed and is byte-identical to the version already live and rendering on the real upstream repo. External links (docs/kb/reference.aspose.org, GitHub repo/issues, PyPI, commercial product page) were not live-fetched (no network verification tool used); this is noted, not flagged, as consistent with the read-only local-evidence scope of this audit.

## Verdict

Two findings, both evidence-integrity/disclosure issues rather than content defects in the shipped candidate. No BLOCKER or MAJOR findings.

**Finding 1 — MINOR, likely systemic (evidence-staleness across verification passes)**
`upstream-issues.md`'s "Old README's LICENSE link is broken" entry asserts, as a present-tense fact checked "against `runs/.clone_cache/aspose_words_python`" (stated verification date 2026-08-16): *"the repo's own root README.md links the license as `[LICENSE](License/license.txt)`."* This is false against the actual current tracked file. Evidence:
- `Grep` for `license.txt|License/` over `runs/.clone_cache/aspose_words_python/README.md` → "No matches found."
- `git -C runs/.clone_cache/aspose_words_python log --oneline -- README.md` → HEAD is `2d2efee` ("docs: refresh README...", author Babar Raza, 2026-08-17 16:36:27 +0500).
- `git -C runs/.clone_cache/aspose_words_python diff 4473f8c 2d2efee -- README.md` shows the *pre-2d2efee* text was `This project is licensed under the MIT License - see the [LICENSE](License/license.txt) file for details.`, replaced in 2d2efee by the correct `[MIT License](LICENSE)` form — i.e., upstream itself already fixed this exact defect on 2026-08-17, independent of this pipeline.
- `reports/repo-presenter-regen-full/words/python/upstream-issues.md` lines 9-13 still narrate the pre-fix state as current.
- The candidate's own LICENSE link is correct (inherited unchanged from the already-fixed upstream, confirmed by the diff in the Content-Preservation Ledger showing zero difference in the badge row / License section between original and candidate) — so end-user impact is nil. The defect is in the audit trail's factual accuracy, not the shipped artifact. Likely systemic: `last-verified.json` shows a later verification pass (2026-08-25) than `upstream-issues.md`'s stated check date (2026-08-16), with `checks_module_version: 2`, but nothing forces `upstream-issues.md`'s own prose to be re-checked against a clone-cache HEAD that has since advanced — any product whose upstream repo commits between two such passes could carry the same staleness.

**Finding 2 — NIT, disclosed (not hidden), product-specific with a shared systemic cause**
The candidate's API Reference table still shows `ShapeNode | Class with 25 properties` (`readme.md:393`) even though no `ShapeNode` class exists in source — the real class is `Shape` (`light_document_model.py:494`), independently recounted here at 24 properties. `content-dispositions.json`'s u0048 `excluded_reason` explicitly discloses this and explains it was deliberately left unfixed to avoid a one-sided divergence from `content/reference.aspose.org/en/words/python/_index.md`, which independently carries the identical `ShapeNode`/25 text (confirmed: `Grep` on that file, lines 382 and 400). The disposition's self-report holds up under verification — this is flagged only because the underlying cross-page defect remains genuinely live and public-facing, requiring a coordinated fix outside this taskcard's forbidden-paths scope.

No other findings. All dependency claims, the 8 corrected API property counts, the `Document()` signature correction, the `PdfSaveOptions` 17/9/8 breakdown, the `MarkdownSaveOptions.image_resolution` dead-code claim, all 12 code blocks' syntax, every referenced example script and test fixture path, every internal anchor link, and all 4 badges were independently verified accurate and consistent across candidate, disposition files, and clone-cache source.

## Stage B: Source Cross-Check

Independent re-verification performed by reading source directly (not by re-checking Stage A's citations). All line numbers below are from my own reads/greps against `runs/.clone_cache/aspose_words_python/` at HEAD `2d2efee`, unless otherwise noted.

### Dependency Accuracy — all CONFIRMED

- `runs/.clone_cache/aspose_words_python/pyproject.toml` lines 15-19: `dependencies = ["olefile>=0.46", "fpdf2>=2.7.5", "pydantic>=2.0.0"]`, line 20: `requires-python = ">=3.10,<3.13"`, lines 44-45 (`[project.optional-dependencies].dev`): `"Pillow>=10.0.0"`, `"pytest>=9.0.2"`. Exact match to candidate's Dependencies section. **CONFIRMED.**
- Package name: `pyproject.toml` line 2 `name = "aspose-words-foss"` matches `data/package_registry.json` line 442 (`words.python.candidate.name: "aspose-words-foss"`, `verification.published: true`, PyPI-verified) and every badge/pip-install reference in the candidate. **CONFIRMED.**
- Real usage of each dependency (not just declared): `grep -n "import olefile" runs/.clone_cache/aspose_words_python/aspose/words_foss/doc_reader/doc_file_reader_core.py:11`; `pdf_writer/*.py` (color.py, font.py, page_bands.py, constants.py, _context.py) all import `fpdf`; `light_document_model.py` imports pydantic (`BaseModel`). **CONFIRMED** — these aren't just declared, they're load-bearing.

### API Accuracy — all 8 corrected property counts CONFIRMED by independent field-by-field recount of `aspose/words_foss/light_document_model.py`

| Class | My count | Candidate says | Old upstream said (verified via `git show 4473f8c:README.md` / current README pre-correction) |
|---|---|---|---|
| `Body` (line 956) | 2 fields (`type`,`children`) + 2 `@property` (`paragraphs`,`tables`) = **4** | 4 | 2 (stale) |
| `Border` (line 139) | 6 fields, no property = **6** | 6 | 3 (stale) |
| `Font` (line 273) | 32 fields (counted name→locale_id_far_east), no property = **32** | 32 | 23 (stale) |
| `ImageData` (line 461) | 7 fields + 1 `@property` (`content_type`) = **8** | 8 | 7 (stale) |
| `Row` (line 797) | 4 fields (`type`,`row_format`,`cells`,`preferred_width`), no property = **4** | 4 | 3 (stale) |
| `RowFormat` (line 788) | 6 fields, no property = **6** | 6 | 7 (stale — this one moved *down*, not just up) |
| `Style` (line 1011) | 15 fields, no property = **15** | 15 | 11 (stale) |
| `Table` (line 824) | 13 fields + 2 `@property` (`first_row`,`last_row`) = **15** | 15 | 11 (stale) |

All 8 **CONFIRMED**. I independently pulled the actual pre-fix upstream text via `git show 4473f8c:README.md` (and the current unmodified upstream README, same numbers) and it does carry the stale counts named in `content-dispositions.json`'s u0048 excerpt — the "corrected" disposition is a real, verifiable fix, not a fabricated pretext.

- `Shape` class (`light_document_model.py:494`): 24 fields, zero `@property` (excludes 3 underscore-prefixed `PrivateAttr` runtime fields `_is_positioned`, `_page_left_mm`, `_page_top_mm`, which are private and correctly not counted). **CONFIRMED — 24, matching Stage A's independent recount.**
- `ShapeNode`: `grep -rn "ShapeNode" runs/.clone_cache/aspose_words_python/ --include=*.py` → **zero matches**. No such class exists anywhere in source; the real class is `Shape`. **CONFIRMED — the candidate's `ShapeNode | 25 properties` row (readme.md:393) is a real, live inaccuracy**, correctly left uncorrected-but-disclosed per `content-dispositions.json` u0048's `excluded_reason` (verified at that exact line: it names both the reason and the cross-page conflict with `content/reference.aspose.org/en/words/python/_index.md:400`, which I confirmed independently also carries `ShapeNode | 25 properties` at that exact line, plus a second `ShapeNode` mention at line 382 inside a `Paragraph` description — both match Stage A's citation exactly).
- `Document.__init__` signature (`document.py:196-203`): `def __init__(self, source: Optional[Union[str, Path, BinaryIO]] = None, load_options: Optional[LoadOptions] = None, *, stream: Optional[BinaryIO] = None, data: Optional[bytes] = None)`. **CONFIRMED** exact match to both the corrected Key-Capabilities bullet and the corrected Detailed Member Reference signature.
- `PdfSaveOptions.__init__` (`saving.py:209-260`): independently counted 17 assigned fields; of these, exactly 8 carry a `# Currently unused` comment: `text_compression` (222), `embed_full_fonts` (227), `use_core_fonts` (229), `font_embedding_mode` (231), `page_mode` (235), `color_mode` (239), `preserve_form_fields` (248), `memory_optimization` (252). **CONFIRMED**, and the exact "17 fields, 8 unused" phrasing with the same 8 names appears verbatim at `readme.md:625` and `content-dispositions.json:1881`.
- `MarkdownSaveOptions.image_resolution` (`saving.py:387`): `grep -rn "image_resolution" runs/.clone_cache/aspose_words_python/ --include=*.py` → **exactly one hit**, the assignment itself, marked `# Currently unused`. **CONFIRMED zero reads / dead code.**
- `CompressionLevel.MAXIMUM = 1` at `saving.py:284`; `OoxmlSaveOptions.pretty_format` at `saving.py:351`; `MarkdownSaveOptions.encoding` at `saving.py:392` — all **CONFIRMED** present exactly as cited.
- Top-level exports `aw.Document`, `aw.SaveFormat`, `aw.LoadFormat`, `aw.LoadOptions`, `aw.MarkdownLoadOptions` (`__init__.py` lines 1-6) and `aw.saving`/`aw.loading` (line 7) — **CONFIRMED** real.
- `SaveFormat.DOC` "reserved, not implemented" claim (readme.md:617-618): independently traced `Document.save()`'s dispatch (`document.py:401-413`) — it branches on MARKDOWN/TEXT/PDF/DOCX only; DOC falls through to `raise ValueError("Unsupported save format...")`. **CONFIRMED accurate**, unflagged by Stage A but verified correct.
- LICENSE facts: `find ... -iname "license*"` on disk → only `LICENSE` at repo root; no `License/` directory exists anywhere in the tree; current README (`README.md:653`) reads `[MIT License](LICENSE)`. **CONFIRMED**, and independently re-derived Stage A's Finding-1 diff myself: `git show 4473f8c:README.md` line 164 reads `...see the [LICENSE](License/license.txt) file for details.` — proving the broken-link text `upstream-issues.md` narrates as current is genuinely the pre-`2d2efee` state, now stale in the audit trail. **Finding 1 independently reproduced, CONFIRMED.**

### Factual Accuracy — remaining items independently reproduced

- 12 ```python fenced blocks in the candidate: `grep -c '^```python' readme.md` → **12**. **CONFIRMED.**
- All 8 named `ApiExamples/*.py` scripts (`convert_document.py`, `loading_document.py`, `loading_markdown.py`, `working_with_markdown_save_options.py`, `working_with_ooxml_save_options.py`, `working_with_pdf_save_options.py`, `working_with_txt_save_options.py`, `working_with_images.py`) exist verbatim in `runs/.clone_cache/aspose_words_python/ApiExamples/` (directory listing matches exactly, plus non-referenced support files `__init__.py`/`conftest.py`/`docs_examples_base.py`/`pytest.ini`). **CONFIRMED.**
- "146 public types" claim (readme.md:328-329, unflagged by Stage A): counted actual table rows from `### Core API` through the end of the `## API Reference` H2 (all module subsections: Core API, Converters, DOC Reader, DOCX Reader, DOCX Writer, Model, Parsers, PDF Writer) → **146 rows exactly**, matching the prose's own stated count. **CONFIRMED self-consistent** (not cross-checked against the raw 189-class/135-function count in `knowledge/words/python/merged/api_surface.json`, since the README table groups/renames some entries e.g. `Document-light_document_model` — that reconciliation wasn't attempted and isn't a defect on its own).

### New, unflagged defect Stage A did not catch: broken "Verify the install" command

`readme.md:107` (preserved verbatim from upstream `README.md:107`, byte-identical, same line number): 

```
python -c "import aspose_words_foss; print('aspose_words_foss OK')"
```

I executed this exactly, from the clone-cache root, against the repo's own `.venv`:

```
$ cd runs/.clone_cache/aspose_words_python && PYTHONPATH=. .venv/Scripts/python.exe -c "import aspose_words_foss; print('aspose_words_foss OK')"
Traceback (most recent call last):
  File "<string>", line 1, in <module>
ModuleNotFoundError: No module named 'aspose_words_foss'
```

**REFUTED as a working instruction.** There is no top-level `aspose_words_foss` module or package anywhere in the tree — only `aspose/words_foss/` (a regular sub-package of the real `aspose` package; `pyproject.toml:66` confirms `packages = ["aspose"]`). Every one of the other 12 code blocks in the README correctly uses `import aspose.words_foss as aw` (verified: `grep -n "import aspose.words_foss as aw" readme.md` → 12 hits, all with the dot). I confirmed the dotted form actually works the same way: `import aspose.words_foss` → `aspose.words_foss OK`. This is a genuine, upstream-origin, reproducible bug in the shipped README's own "Verify the install" snippet — every user who copy-pastes it gets an immediate `ModuleNotFoundError`. It slipped past Stage A's "Example Verification" section because that pass only ran `ast.parse` (syntax-only) over the 12 fenced ```python blocks; this defective line is a `bash`-fenced shell command, outside that scan, and its module target was never cross-checked against the real package layout. Not disclosed in `upstream-issues.md`. Root cause is upstream (present before this pipeline ever touched the file), so it is correctly *preserved* rather than a pipeline defect — but it is a live, user-facing inaccuracy in the candidate as shipped that neither Stage A's review nor the disposition files flag anywhere.

### Second unflagged, lower-severity item: stale minimum-version pin in Installation

`readme.md:92` / upstream `README.md:92` (byte-identical, preserved verbatim): `pip install aspose-words-foss>=26.5.0`. Independently confirmed via `git log -p --follow -- README.md`: this exact string was introduced once and never revised since, even as the package advanced to its current version. Meanwhile the merged-knowledge canonical install guidance disagrees with it: `knowledge/words/python/merged/install.md:4` says `pip install aspose-words-foss>=26.7.0`, and `knowledge/words/python/merged/model.yaml:33` / `claims.json:17682` both independently state `26.7.0` as the current version — matching `pyproject.toml:3` (`version = "26.7.0"`) exactly. Not technically false (26.7.0 does satisfy `>=26.5.0`), and correctly preserved per the "don't diverge from upstream absent a disclosed reason" rule, but it is a real, unflagged inconsistency between the shipped Installation section and the pipeline's own canonical `install.md` knowledge artifact — worth a disclosed note the way u0032/u0033/u0048 got one, since a new user reading only the badge/pip line has no way to know 26.7.0 is current-recommended.

### No other discrepancies found

Every other claim I independently traced in the Factual Accuracy, Dependency Accuracy, and API Accuracy sections — dependency versions and their real-source usage, the `Document()` signature, the `PdfSaveOptions` 17/8 breakdown, the `image_resolution` dead-code claim, all 8 corrected class property counts, the `ShapeNode`/`Shape` discrepancy and its disclosure, the top-level export list, `CompressionLevel.MAXIMUM`, `OoxmlSaveOptions.pretty_format`, `MarkdownSaveOptions.encoding`, the LICENSE facts, and Finding 1's diff — reproduced identically from my own independent reads of `runs/.clone_cache/aspose_words_python/` and `knowledge/words/python/merged/`, with no divergence from Stage A's reported values.

## Stage C: Adversarial Verification

**Finding 1 — MINOR, likely systemic (upstream-issues.md's stale LICENSE-link claim)**
Independently re-ran every cited check: `git -C runs/.clone_cache/aspose_words_python log --oneline -- README.md` reproduces the same two commits (`4473f8c`/26.7.0, `2d2efee`/docs refresh); `git show 4473f8c:README.md` line 164 reproduces the broken `[LICENSE](License/license.txt)` text verbatim; the current tracked `README.md` (line 653) reproduces the fixed `[MIT License](LICENSE)` form verbatim; `2d2efee`'s commit date (2026-08-17 16:36:27 +0500) postdates `upstream-issues.md`'s stated verification date (2026-08-16), confirming the claim was true when written and only went stale afterward; and `reports/.../upstream-issues.md` lines 9-13 do still narrate the pre-fix text as current. The candidate's own License section is confirmed correct (zero shipped-artifact impact). Evidence fully reproduces. **CONFIRMED.** Severity (MINOR) is defensible given nil end-user impact, if anything on the generous side rather than overstated. The "likely systemic" tag is appropriately hedged in the original text but rests on zero cross-product evidence — it's a plausible process argument, not a demonstrated pattern; treat that half of the claim as speculative, not verified.

**Finding 2 — NIT, disclosed (ShapeNode/Shape mismatch)**
Independently confirmed every citation: `grep -rn "ShapeNode" --include=*.py` over the full clone cache returns zero hits (no such class exists); `class Shape(BaseModel, NodeCastMixin):` is at `light_document_model.py:494` exactly, and a field-by-field re-read of lines 495-524 (excluding the three underscore-prefixed `PrivateAttr` runtime fields, correctly excluded) independently recounts to exactly 24 fields with no `@property`, matching the claim precisely; the candidate (`reports/.../readme.md:393`) still reads `| ShapeNode | Class with 25 properties. |`, unchanged; `content-dispositions.json`'s u0048 `excluded_reason` (verified verbatim) does explicitly name the ShapeNode/Shape mismatch, the correct class/count, and the forbidden-paths rationale; and `content/reference.aspose.org/en/words/python/_index.md` reproduces the identical text at both cited lines (382, 400). I additionally traced the root-cause claim one step further than either stage did: the current upstream README at HEAD `2d2efee` (i.e., the "original-at-generation-time" file itself) already contains the identical `ShapeNode | Class with 25 properties.` at the same line 393 — so this is genuinely inherited from upstream, not introduced by either pipeline output — while the pipeline's own *merged* knowledge (`knowledge/words/python/merged/api_surface.json`, `class_graph.json`) already correctly names the class `Shape`, showing the non-fix on the README side is a deliberate scoping choice, not a stale-knowledge accident (only the older pre-merge `scout/enriched_claims.json` and `knowledge_delta*.json` artifacts still say "ShapeNode"). Evidence fully reproduces — core claim **CONFIRMED**, including the "shared systemic cause" tag (both public pages verifiably carry the same upstream-origin text). However, severity is miscalibrated: **UPGRADED** from NIT to at least MINOR. This is a live, reproducible, public-facing factual error on two production pages (a class name that doesn't exist, with a wrong property count) — the review's own severity scale rates comparably-impactful issues (`SaveFormat.DOC` unusable, broken LICENSE link) as MINOR elsewhere in this same audit trail. Being "disclosed" only inside an internal, non-public audit file (`content-dispositions.json` — evidence/disposition data is internal-only per repo convention, never surfaced to a reader of the actual README or reference page) does not reduce real-world severity; it only means the *investigation* isn't blindsided by it. Calling this a "NIT" while calling the zero-impact License staleness "MINOR" inverts the two findings' actual relative severity.