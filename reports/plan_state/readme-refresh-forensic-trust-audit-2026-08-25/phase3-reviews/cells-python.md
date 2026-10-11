## Identity

Four artifact classes were sought; all four were obtainable, and two turned out to be the same commit.

| Artifact | Obtained? | Identifier |
|---|---|---|
| **Candidate** | Yes | `reports/repo-presenter-regen-full/cells/python/readme.md` — sha256 `910dfd88f81860d94b093d03ce821450ff4f3a1cd7b982dca172e2b424be23f9` (matches `last-verified.json`'s `readme_sha256` exactly; verified via `sha256sum`) |
| **Current upstream** | Yes | `runs/.clone_cache/aspose_cells_python/README.md`, HEAD = commit `26c3bd1633e84b91c0f6fad1fd353662fd61fb54` ("docs: refresh README with verified capabilities, examples, and API reference", author Babar Raza, 2026-08-14). `git -C runs/.clone_cache/aspose_cells_python log --oneline -- README.md` shows only this commit and one earlier one (`1139a9a90280783cd91a7d3747adfdaa97a9cb47`, "V26.7.0", 2026-07-24) — upstream has **not moved since generation**. |
| **Original-at-generation-time** | Yes — **same commit as current upstream** | The disposition JSONs' own recorded excerpts (e.g. `content-dispositions.json` unit `u0044`, the Mermaid diagram, the Navigation list, the 130-type API table) verbatim-match commit `26c3bd1`, not the older `1139a9a`. Confirmed by diffing both: `git -C runs/.clone_cache/aspose_cells_python show 1139a9a:README.md` is a completely different, much shorter (160-line) README with no Mermaid diagram, no "Scope and Limitations", no Enterprise Edition link, and lowercase repo/license naming — none of which matches the dispositions. So generation was performed against `26c3bd1`, and upstream has not diverged from it since. |
| **Published (real GitHub content)** | Yes | Fetched via `gh api repos/aspose-cells-foss/Aspose.Cells-FOSS-for-Python/contents/README.md --jq .content \| base64 -d`. Byte-different sha256 from the clone-cache file (`49b4e52a...` vs clone-cache's `b0ad9854...`) but **content-identical after CRLF normalization** (`tr -d '\r'` on both sides → `diff` exit 0). This is expected: this product's "real GitHub repo" *is* the upstream FOSS repo itself (not a separate downstream mirror), so "published" and "current upstream" are the same content. No S-120 publish event exists for cells/python in `data/readme_published_state.json` (grep for `cells/python` returns nothing) or `reports/repo_presenter_actions.jsonl` (2 total lines, for `note/python` and `cells/rust` only) — this repo's README reached its current state via a human commit, not an S-120 push. |

## Factual Accuracy

Spot-verified claims against the actual clone-cache source (`runs/.clone_cache/aspose_cells_python/`):

- **Dependencies** (`pyproject.toml` lines 31–34, 37–40, 10): `pycryptodome>=3.15.0`, `olefile>=0.46`, `pytest>=7.0.0`, `pytest-cov>=4.0.0`, `requires-python = ">=3.7"` — all match the candidate's Installation/Dependencies text exactly.
- **16 chart types "each with its own dedicated XML writer"** (readme.md u0018): confirmed real. `chart.py:1062-1065`'s `ChartCollection.add()` dispatcher's `supported` tuple lists all 16 `ChartType` values; `xml_chart_saver.py:74-145` routes every one of them (including waterfall/treemap/box-whisker/sunburst/histogram/funnel/map via the `is_chart_ex` branch, combo/scatter/surface/radar via dedicated `elif` branches) to its own formatter. Claim holds.
- **Enterprise Edition link** (readme.md:399, `https://products.aspose.com/cells/python-net/`): **correct**, per the hand-curated, HTTP-verified override `data/backlinks/platform_canonical_overrides.yaml:44-49` (`cells/python: target_platform: "python-net"`, verified 2026-07-03, HTTP 200 at that exact URL). See Verdict for the surrounding ledger/documentation problems this uncovered.
- **130 public types**: internally consistent — `awk` count of the candidate's own tables gives 114 Core-API rows + 16 Enumeration rows = 130 exactly (`readme.md` "Core API"/"Enumerations" tables).
- **Scope and Limitations**: matches `knowledge/cells/python/merged/limitations.md`'s two real, reachable `NotImplementedError`s (Standard encryption unsupported — `cfb_handler.py:138`, `xlsx_encryptor.py:79/317`; FormulaEvaluator is basic — confirmed by class name/purpose). The candidate correctly omits the other two rows in `limitations.md` (`xml_chart_saver.py:498`, `chart.py:1067`), which are unreachable internal defensive branches, not real limitations (see Content-Preservation Ledger).
- No fabricated version numbers, no invented API members found in the sections checked.

## Content-Preservation Ledger

62 total disposed units across the four files: 46 in `content-dispositions.json`, 3 in `structure-dispositions.json`, 4 in `badge-dispositions.json`, 9 in `code-example-dispositions.json`. Disposition-by-disposition:

| Unit(s) | Category | Claimed disposition | Verified in candidate? | Actual status |
|---|---|---|---|---|
| u0001–u0043, u0045, u0046 (43 of 46) | Intro, Nav, Key Capabilities, Installation, Quick Start, API Reference tables, Documentation & Resources, Scope/Limitations, Dev & Testing, License | `merged_verbatim` | Yes — spot-checked ~15 of these directly against `readme.md`, all byte-identical to their recorded excerpts | **PRESERVED** |
| s0001–s0003 | Mermaid diagram, 2 collapsible code-example headers | `merged_verbatim` | Yes, confirmed present at cited `target_section` | **PRESERVED** |
| c0001–c0009 | All code blocks (At a Glance diagram, install, Quick Start x2, styling, data validation, CSV export, password protect, dev/test commands) | `merged_verbatim` | Yes; further verified the underlying API calls are real (see Example Verification) | **PRESERVED** |
| b0001–b0004 | PyPI/Python-version/License/Contributors badges | `superseded_by_duplicate` | Yes — new badges in candidate line 3 use identical images/targets (License badge additionally upgraded to point at the real local `License/LICENSE.txt` instead of the old generic `opensource.org` link) | **TRANSFORMED (correctly, and correctly disposed)** |
| **u0044** | Enterprise Edition paragraph (Scope and Limitations) | `merged_verbatim` — excerpt reads `.../cells/python-java/` (`content-dispositions.json:871-881`) | **No** — `readme.md:399` actually reads `.../cells/python-net/`, a different URL than the disposition's own recorded excerpt | **TRANSFORMED, but mislabeled `merged_verbatim`** — see Verdict finding 2 |
| *(no unit exists)* | The entire `## Dependencies` section (readme.md:19,116-133: "Required Package Dependencies" / "Native and System Requirements" / "Development Dependencies") | *none* | Content is new relative to the source README structure (verified: source has no such section) | **New content with zero disposition record** — not preservation-incorrect (nothing dropped), but a **ledger completeness gap** — see Verdict finding 3 |

No units were found DROPPED-SILENTLY or INCORRECTLY-EXCLUDED. `git -C runs/.clone_cache/aspose_cells_python show 26c3bd1:README.md` diffed line-for-line against the candidate (`grep -vFxf` both directions) surfaces only two real differences: the Enterprise-link URL (u0044, above) and the added Dependencies section (above) — everything else in the 26c3bd1 upstream README is present, unchanged, in the candidate.

## Usability

- Table of Contents (`## Navigation`, readme.md:14-26) lists 11 anchors; all 11 headings exist in the document in the same order, including the newly-added `#dependencies` anchor which does resolve to a real heading.
- Progressive disclosure is used appropriately: `<details>` wraps the secondary code examples (readme.md:186-227) and the full 130-row API table (readme.md:235-378), keeping the primary read short.
- Quick Start gives two complete, runnable snippets (create+save, then read) before Additional Examples branches into styling/validation/CSV/password use cases — a sensible on-ramp.
- Development and Testing section gives the exact two commands (`pip install -e ".[dev]"`, `pytest`) verified against `pyproject.toml`'s `[project.optional-dependencies].dev` and `[tool.pytest.ini_options]`.
- No usability defects found.

## Presentation/SEO

- Badge row (readme.md:3) and banner image (readme.md:5, `products.aspose.org/media/cells/python/banner-readme.png`) render before the descriptive paragraph, standard for this portfolio's convention.
- Documentation & Resources section (readme.md:380-387) links docs/kb/reference/products.aspose.org consistently in the family/platform pattern used elsewhere in the repo.
- No keyword-stuffing, no broken heading hierarchy, no duplicate H1s observed.

## Dependency Accuracy

Fully verified against `runs/.clone_cache/aspose_cells_python/pyproject.toml`:

| Candidate claim (readme.md:120-123, 127, 131-132) | pyproject.toml | Match? |
|---|---|---|
| `pycryptodome` >=3.15.0 | line 32: `"pycryptodome>=3.15.0"` | Yes |
| `olefile` >=0.46 | line 33: `"olefile>=0.46"` | Yes |
| Python >=3.7 | line 10: `requires-python = ">=3.7"` | Yes |
| `pytest` >=7.0.0 (dev) | line 38: `"pytest>=7.0.0"` | Yes |
| `pytest-cov` >=4.0.0 (dev) | line 39: `"pytest-cov>=4.0.0"` | Yes |

No dependency-accuracy defects found.

## Example Verification

All code examples' API surface checked directly against source, all real:

- `Workbook(file_path=None, password=None)` — `workbook.py:92` — matches all three constructor call shapes used (no-arg, path-only, path+password).
- `Workbook.worksheets` — `@property` at `workbook.py:140-141` — matches `workbook.worksheets[0]` usage.
- `Cell.value` getter/setter — `cell.py:61,74-75` — matches `worksheet.cells["A1"].value = ...`.
- `Workbook.save(file_path, save_format=None, options=None, password=None, encryption_params=None)` — `workbook.py:379` — matches both plain and `password=` call forms.
- `Cell.get_style()` / `apply_style()` — `cell.py:333,348`; `Font.size/color/bold` — `style.py:46-48` — matches the styling example exactly.
- `Worksheet.data_validations` property → `.add("A1:A10")` — `worksheet.py:380,399` (docstring example is nearly identical to the README's own example) — real.
- `DataValidationType.LIST` — `data_validation.py:27` (`LIST = 3`) — real.
- `Workbook.save_as_csv()` — `workbook.py:523` — real.

No fabricated or incorrect API usage found in any example.

## API Accuracy

- Core API table (114 rows) + Enumerations table (16 rows) = 130, matching the stated "130 public types" claim exactly (counted directly from the candidate via `awk`/`grep -c`).
- Spot-checked several individual entries (`ChartCollection`, `DataValidationCollection`, `TableCollection`, `SparklineGroupCollection`, `XLSXEncryptor`) against their actual source modules — descriptions match real class purposes.
- The one deliberately-disambiguated duplicate-name row (`CFBWriter-cfb_handler`, readme.md:251) correctly explains it's a distinct class in `cfb_handler.py` from the general-purpose `CFBWriter` — this is accurate and a good catch by the generation process, not a defect.
- Did not exhaustively verify all 130 rows against source (out of scope for the time available); no inaccuracies found in the sample checked.

## Link/Rendering

- `AGENTS.md` (contributor guide link) exists at repo root — confirmed via `ls`.
- `examples/` directory exists and is populated — confirmed via `ls`.
- `License/LICENSE.txt` exists with the exact case the candidate links to — confirmed via `ls`.
- GitHub issues link (`github.com/aspose-cells-foss/Aspose.Cells-FOSS-for-Python/issues`) uses the correct, current, title-cased repo name.
- **Enterprise Edition link** (readme.md:399, `products.aspose.com/cells/python-net/`) resolves correctly per the HTTP-verified override (`data/backlinks/platform_canonical_overrides.yaml:44-49`) — but see Verdict: the *live upstream* repo's own README (same commit the rest of this run is built from) still links to the wrong `products.aspose.com/cells/python-java/`, which the candidate silently and correctly avoided.
- No other broken or unverifiable links found in the sections reviewed.

## Verdict

Four findings, no BLOCKERs against the shipped candidate's own correctness — the substantive problems are in the surrounding audit-trail artifacts, not the README that would actually ship.

**1. MAJOR — systemic risk — `upstream-issues.md` reports three "genuine defects" that are all stale/false relative to the actual knowledge baseline this run used.**
- Evidence: `reports/repo-presenter-regen-full/cells/python/upstream-issues.md` Issue #1 (stale lowercase repo-name links) and Issue #2 (lowercase `License/license.txt`) describe the README at commit `1139a9a90280783cd91a7d3747adfdaa97a9cb47` (`git -C runs/.clone_cache/aspose_cells_python show 1139a9a:README.md` lines 5, 142, 156, 160 — lowercase `aspose-cells-python`, `License/license.txt`). Both are already fixed in the commit this run's own `content-dispositions.json` and `readme.md` were actually built from, `26c3bd1633e84b91c0f6fad1fd353662fd61fb54` (`git -C runs/.clone_cache/aspose_cells_python show 26c3bd1:README.md` lines 3, 387, 395 — title-cased repo name, correct-case `License/LICENSE.txt`).
- Issue #3 claims `knowledge/cells/python/merged/model.yaml` is pinned at stale `version: 26.3.1` / `repo_sha: 5b5b28eb...`. Directly contradicted: `knowledge/cells/python/merged/model.yaml:4,6-7` currently reads `version: 26.7.0`, `repo_sha: 26c3bd1633e84b91c0f6fad1fd353662fd61fb54` — exactly the commit already in use. There is no staleness.
- Root cause (timeline via `ls -la`/`git log`): `upstream-issues.md` mtime is 2026-08-13 09:18:37; `model.yaml` was updated 2026-08-18 23:25:45 (`git log --oneline -- knowledge/cells/python/merged/model.yaml` → "knowledge(cells/python): re-promote scout-only knowledge rebaseline"); `readme.md`/`content-dispositions.json` were generated 2026-08-20. `upstream-issues.md` predates the knowledge rebaseline by 5 days and was never regenerated.
- Product-specific occurrence, but the mechanism (nothing forces `upstream-issues.md` to regenerate when the knowledge baseline or upstream commit moves between passes) is systemic and could recur on any product refreshed across multiple sessions.

**2. MAJOR (ledger-integrity) / not a shipped-content defect — `content-dispositions.json` unit `u0044` is mislabeled `merged_verbatim`, and in the process the one real, currently-live upstream defect went undocumented.**
- `content-dispositions.json:871-881` (`u0044`) records the Enterprise Edition paragraph as `merged_verbatim` with excerpt `.../cells/python-java/`. The actual candidate (`readme.md:399`) reads `.../cells/python-net/` — a different link, not a verbatim merge.
- The candidate's value is the *correct* one: `data/backlinks/platform_canonical_overrides.yaml:44-49` HTTP-verified `cells/python -> python-net` (2026-07-03), corroborated by `scripts/pipeline/commands/foss/readme_refresh_run.py:1144-1155`, whose docstring names this exact case: "the override file's own dated policy states `cells/python -> python-net`... but the raw cached target map instead held a later, less-explained `python-java` correction."
- The wrong `python-java` value is what's actually live today in the real upstream repo (`runs/.clone_cache/aspose_cells_python/README.md:380`, confirmed identical in the real GitHub content fetched via `gh api repos/aspose-cells-foss/Aspose.Cells-FOSS-for-Python/contents/README.md`) — a genuine, currently-open upstream defect that the readme-refresh machinery correctly avoided reproducing, but which `upstream-issues.md` (whose stated purpose is exactly this) never records.
- Net effect: the shipped candidate is factually fine, but its own audit trail is unreliable for this unit, and the one real upstream defect is invisible to anyone reading `upstream-issues.md`. Systemic risk: any product whose Enterprise link needed an override correction is exposed to the same disposition/excerpt drift.

**3. MINOR — the new `## Dependencies` section has zero disposition record.**
- `readme.md:19,116-133` (nav entry + full section: Required Package Dependencies / Native and System Requirements / Development Dependencies) has no corresponding unit in any of the four disposition files — confirmed via `grep -n "Dependencies" content-dispositions.json structure-dispositions.json badge-dispositions.json code-example-dispositions.json` returning zero matches.
- Content itself is accurate (cross-verified against `pyproject.toml`, see Dependency Accuracy), so this is not a factual defect, but it is a completeness gap in the preservation ledger: net-new synthesized sections are not tracked by the disposition system, so this class of addition would not be caught by disposition-review alone if it were ever wrong on a different product. Product-specific instance, systemic gap.

**4. NIT — two `limitations.md` rows are internal-only noise, correctly not surfaced (positive confirmation, not a defect).**
- `knowledge/cells/python/merged/limitations.md` rows for `xml_chart_saver.py:498` and `chart.py:1067` are unreachable defensive branches, not real limitations — confirmed by reading `chart.py:1062-1065` (all 16 `ChartType` values are in the "supported" tuple) and `xml_chart_saver.py:74-145` (every type has a real dedicated formatter). The candidate correctly omits both from "Scope and Limitations." Recorded for completeness of the ledger review, not as a problem.

## Stage B: Source Cross-Check

### Factual Accuracy claims

**Dependencies (pyproject.toml)** — CONFIRMED, re-read directly.
`D:\onedrive\Documents\GitHub\aspose.org\runs\.clone_cache\aspose_cells_python\pyproject.toml`: line 32 `"pycryptodome>=3.15.0"`, line 33 `"olefile>=0.46"`, line 10 `requires-python = ">=3.7"`, line 38 `"pytest>=7.0.0"`, line 39 `"pytest-cov>=4.0.0"`. All five match the candidate exactly.

**"16 chart types, each with its own dedicated XML writer" (readme.md:92, unit u0018)** — **PARTIALLY REFUTED.** The count of 16 is CONFIRMED (`chart.py:11-28`, `class ChartType(IntEnum)` has exactly 16 members: LINE=0 … MAP=15; `chart.py:1062-1065`'s `supported` tuple in `ChartCollection.add()` lists all 16). But "each with its own dedicated XML writer" is false for 4 of the 16: `xml_chart_saver.py:492-580` shows `LINE`, `BAR`, `PIE`, and `AREA` are all routed through **one shared function**, `_format_chart_xml()` (dispatch at `xml_chart_saver.py:148`), which branches internally by `chart.type` (`xml_chart_saver.py:517-527` — `if chart.type == ChartType.LINE: ... elif chart.type == ChartType.BAR: ... elif chart.type == ChartType.AREA: ... else:` for PIE). Only `STOCK` gets a truly separate function nested off that same call (`_format_stock_chart_xml`, `xml_chart_saver.py:580`, called from inside `_format_chart_xml` itself at line 494-495). The other 11 types each do have a genuinely separate, individually-named formatter: `_format_scatter_chart_xml` (685), `_format_surface_chart_xml` (723), `_format_radar_chart_xml` (777), `_format_combo_chart_xml` (817), `_format_box_whisker_chart_ex_xml` (982), `_format_map_chart_ex_xml` (1062), `_format_funnel_chart_ex_xml` (1138), `_format_histogram_chart_ex_xml` (1207), `_format_sunburst_chart_ex_xml` (1283), `_format_waterfall_chart_ex_xml` (1350), `_format_treemap_chart_ex_xml` (1414). Net: 12 of 16 types have their own dedicated writer; 4 (LINE/BAR/PIE/AREA) share one. The candidate's literal wording overstates this. Stage A's spot-check ("confirmed real") missed this because it verified the dispatch table but not whether the destinations were actually distinct per-type functions.

**Enterprise Edition link `python-net` (readme.md:399)** — CONFIRMED. `data/backlinks/platform_canonical_overrides.yaml:44-49`: `cells/python: target_platform: "python-net"`, `http_verified: true`, `verification_date: "2026-07-03"`, `verification_url: "https://products.aspose.com/cells/python-net/"`. `readme.md:399` reads `.../cells/python-net/`. Match confirmed by my own read of both files.

**u0044 mislabeling** — INDEPENDENTLY CONFIRMED. `content-dispositions.json:871-875` records `u0044` as `disposition: "merged_verbatim"` with excerpt containing `https://products.aspose.com/cells/python-java/`. The candidate (`readme.md:399`) actually reads `.../cells/python-net/` — different URL, so this was a transformation, not a verbatim merge. I further confirmed the excerpt's `python-java` value is exactly what the live upstream commit contains: `git -C runs/.clone_cache/aspose_cells_python show 26c3bd1:README.md | grep python` → line 380 `https://products.aspose.com/cells/python-java/`.

**Scope and Limitations / Standard encryption (readme.md:393-394)** — **NEW FINDING, precision gap, not caught by Stage A.** Text reads: "Only Agile encryption ... is supported for reading and writing password-protected workbooks; Standard encryption (Section 3) is **not yet supported for reading**." I independently read both encryption-direction code paths: `xlsx_encryptor.py:76-79` (`_encrypt_package`, the **write** path) — `if self.params.encryption_type != EncryptionType.AGILE: raise NotImplementedError("Only Agile encryption is currently supported")` — and `xlsx_encryptor.py:314-317` (`_decrypt_package`, the **read** path) — same guard. Both directions reject non-Agile. `cfb_handler.py:125-138` (`_parse_standard_encryption_info`) is a third, read-side rejection. So Standard encryption is unsupported for **both reading and writing**, not just reading as the sentence states. This isn't a fabrication (nothing false is claimed about Agile), but the sentence under-discloses a limitation that also applies to writing.

**FormulaEvaluator "basic evaluator"** — CONFIRMED. `formula_evaluator.py:21-23`: `class FormulaEvaluator: """ Basic formula evaluator for xlsx cells without cached values. ...`. Verbatim match to the README wording.

**limitations.md's two excluded rows (chart.py:1067, xml_chart_saver.py:498) correctly treated as internal noise** — CONFIRMED. `chart.py:1062-1065`'s `supported` tuple contains all 16 `ChartType` values (so the `raise NotImplementedError` at `chart.py:1067` in `ChartCollection.add()` is unreachable dead code, confirmed by direct read). `xml_chart_saver.py:497-498`: `if chart.type not in (ChartType.LINE, ChartType.BAR, ChartType.PIE, ChartType.AREA): raise NotImplementedError(...)` — also unreachable in practice since `_format_chart_xml` is only ever invoked (from `write_chart_parts`, `xml_chart_saver.py:148`) after the type has already been narrowed by the `elif`/`else` chain at lines 116-148, which routes STOCK and all chartEx/combo/scatter/surface/radar types elsewhere before falling through to `_format_chart_xml`.

### Dependency Accuracy

All 5 rows independently re-verified against `pyproject.toml` (cited above) — CONFIRMED, no discrepancies.

### API Accuracy / Example Verification

All spot-checked members CONFIRMED by direct read, with exact line numbers matching Stage A's citations:
- `Workbook.__init__(self, file_path=None, password=None)` — `workbook.py:92`.
- `Workbook.worksheets` property — `workbook.py:140-141`.
- `Cell.value` getter/setter — `cell.py:60-75` (getter at 61, setter at 74).
- `Workbook.save(self, file_path, save_format=None, options=None, password=None, encryption_params=None)` — `workbook.py:379`.
- `Cell.apply_style`/`get_style` — `cell.py:333`/`cell.py:348`.
- `Font.__init__` params `size`/`color`/`bold` — `style.py:46,47,48`.
- `Worksheet.data_validations` property → `.add(...)` — `worksheet.py:380`, usage docstring `worksheet.py:399`.
- `DataValidationType.LIST = 3` — `data_validation.py:24-27` (`IntEnum`, `LIST = 3` on line 27).
- `Workbook.save_as_csv` — `workbook.py:523`.
- Class-description spot checks, all verbatim docstring matches: `ChartCollection` → `chart.py:1046-1047` "Collection of charts in a worksheet."; `DataValidationCollection` → `data_validation.py:651-654`; `TableCollection` → `table.py:140-141` "Collection of Table objects belonging to a worksheet (ws.tables)."; `SparklineGroupCollection` → `sparkline.py:196-197` "Collection of SparklineGroup objects (ws.sparkline_groups)."; `XLSXEncryptor` → `xlsx_encryptor.py:30-33` "Handles encryption of XLSX files."
- `CFBWriter` (general) → `cfb_writer.py:30-33` "Writes CFB (Compound File Binary) files according to MS-CFB specification."; `CFBWriter-cfb_handler` → `cfb_handler.py:336-339` "Writes encrypted XLSX to CFB format." — disambiguation text is accurate.

**"130 public types" count** — CONFIRMED by an independent method (not just recounting the candidate's own table rows). Direct `grep -rn "^class " aspose/cells_foss/*.py` returns 131 top-level class definitions; one (`_Node`) is private by convention and correctly excluded, leaving exactly 130 — matching the candidate's 114 Core-API + 16 Enumeration rows (independently re-counted via `awk`/`grep -c '^| \`'` on the two table sections: 114 and 16). The `CFBWriter` name collision (`cfb_writer.py:30` and `cfb_handler.py:336`, both counted in the raw 131) is correctly split into two disambiguated rows in the table, so the count isn't inflated or deflated by that collision.

### Unflagged findings from independent investigation (not in Stage A's review)

**F1 — `knowledge/cells/python/merged/api_surface.json` silently drops one of the two `CFBWriter` classes.** Querying the file directly: it contains only 129 unique class names (one fewer than the true 130), and the entry named `CFBWriter` in it points only to `aspose/cells_foss/cfb_handler.py` — the general-purpose `CFBWriter` in `cfb_writer.py` has **no entry at all** in `api_surface.json`. This means the README's correct 130-count and correct two-row disambiguation could not have been produced from `api_surface.json` alone; whatever generated the table must have re-scanned source directly. This is a real fidelity gap in the knowledge artifact I was asked to check (same class of same-name-collision bug noted in memory for MT013's `batch_reference.py` namespace disambiguation), even though it did not cause a defect in the shipped candidate this time.

**F2 — `formats.md`/`formats.json` incorrectly mark TSV export as non-functional, contradicting `claims.json`, and I confirmed the code is genuinely functional.** `knowledge/cells/python/merged/formats.md:11`: `| TSV | - | - |`. Underlying `formats.json` entry (lines 52-60): `"format": "TSV", ... "direction": "enum_only", "functional": false`. But `knowledge/cells/python/merged/claims.json` line 18051 (`claim_id: "CLM-cells-5179e2"`, confidence 1.0) states: `"text": "export support for TSV via SaveFormat"`, evidence `workbook.py:28`. I independently verified in source that TSV export is real and working: `workbook.py:42` declares `TSV = auto()` in `SaveFormat`; `workbook.py:435-441` in `Workbook.save()`: `elif save_format == SaveFormat.TSV: # TSV is CSV with tab delimiter\n if options is None: options = CSVSaveOptions()\n options.delimiter = '\t'\n self.save_as_csv(file_path, options)` — a fully functional dispatch, not a stub. So `formats.md` is simply wrong (scout tool's functionality heuristic missed the delegate-to-CSV-with-different-delimiter pattern), and this is a knowledge-base internal contradiction. Consequence for the candidate: the README's "Scope and Limitations" (readme.md:390-391) lists only "CSV, JSON, and Markdown" as additional text-format export targets, omitting TSV — an incompleteness (real, working capability left undocumented), not a fabrication, and not previously flagged.

**F3 — A second real, currently-live upstream defect, parallel to Stage A's finding #2, that `upstream-issues.md` also fails to record.** 19 docstrings inside the source package itself use a non-existent import path `from aspose_cells import ...` (e.g. `auto_filter.py:194`, `cell.py:24`, `cell.py:341`, `cells.py:21`, `conditional_format.py:20`, and 14 more — counted via `grep -rn "from aspose_cells import" aspose/cells_foss/*.py | wc -l` → 19). No `aspose_cells` top-level package exists anywhere in the repo (`find . -iname "aspose_cells*"` returns nothing; `pyproject.toml:49` declares `packages = ["aspose", "aspose.cells_foss", "examples"]`). The candidate README correctly uses the real import everywhere instead (`grep -n "^from aspose" readme.md` → six occurrences, all `from aspose.cells_foss import ...`). So, like the Enterprise-link `python-java` defect Stage A found, this is a genuine live upstream documentation bug the candidate silently avoided reproducing — and it is likewise invisible in `upstream-issues.md`, reinforcing Stage A's Finding 1's systemic point that `upstream-issues.md` is stale/incomplete relative to the actual `26c3bd1` baseline this run used.

No other unflagged high-risk factual, dependency, or API discrepancies were found in the areas re-checked.

## Stage C: Adversarial Verification

**Finding 1 (MAJOR — upstream-issues.md's three "genuine defects" are stale/false)** — **CONFIRMED.** Independently re-read all cited evidence: `git show 1139a9a:README.md` does contain lowercase `github.com/aspose-cells-foss/aspose-cells-python` (line 14) and `License/license.txt` (line 25); `git show 26c3bd1:README.md` does contain the title-cased `Aspose.Cells-FOSS-for-Python` path and correctly-cased `License/LICENSE.txt`. `knowledge/cells/python/merged/model.yaml` currently reads `version: 26.7.0` / `repo_sha: 26c3bd1633e84b91c0f6fad1fd353662fd61fb54` (lines 4/7) — Issue #3's stale-pin claim is indeed false today. mtimes independently re-pulled via `ls -la --time-style=full-iso` match exactly: `upstream-issues.md` 2026-08-13 09:18:37, `model.yaml` 2026-08-18 23:25:45, `readme.md`/`content-dispositions.json` 2026-08-20. Severity (MAJOR) is calibrated correctly — it's an audit-trail-only defect (explicitly not a shipped-content BLOCKER), but a reviewer trusting `upstream-issues.md` at face value would be actively misled about defects that are already fixed. The "systemic" tag (regeneration isn't forced when the knowledge baseline moves between passes) is a reasonable mechanism inference from this one instance but was not independently cross-checked against any other product's `upstream-issues.md` in this pass — treat that half of the tag as plausible-but-unverified rather than proven.

**Finding 2 (MAJOR — u0044 mislabeled `merged_verbatim`; live upstream defect undocumented)** — **CONFIRMED**, and this is the most solidly-evidenced of the four. Direct re-reads all match exactly as cited: `content-dispositions.json:871` excerpt reads `.../cells/python-java/`; `readme.md:399` actually reads `.../cells/python-net/` — genuinely different, so the `merged_verbatim` label is wrong (this was a transformation). `data/backlinks/platform_canonical_overrides.yaml:44-49` reads exactly as quoted (`cells/python: target_platform: "python-net"`, `verification_date: "2026-07-03"`). `readme_refresh_run.py:1140-1155`'s `_load_canonical_overrides()` docstring independently corroborates the "python-net vs python-java" mechanism verbatim. Live upstream confirmed via `grep -n python-java` on both the clone-cache working tree and `git show 26c3bd1:README.md` — both show `.../cells/python-java/` at line 380, i.e. a real, currently-live upstream documentation defect that `upstream-issues.md` never records. Severity and "not a shipped-content defect" framing are both correctly calibrated — the candidate itself is right; only the ledger and the upstream-defect catalog are wrong.

**Finding 3 (MINOR — new `## Dependencies` section has zero disposition record)** — **CONFIRMED.** `grep -n "Dependencies"` across all four disposition files (`content-`, `structure-`, `badge-`, `code-example-dispositions.json`) returned zero matches, exactly as claimed. `readme.md:19` is the nav entry (`- [Dependencies](#dependencies)`) and `readme.md:116-133` is the full section (Required Package Dependencies / Native and System Requirements / Development Dependencies) — both confirmed present. Confirmed the section is genuinely new: `grep -n "^## "` on both the clone-cache working tree and `git show 26c3bd1:README.md` shows the upstream README goes straight from `## Installation` (106) to `## Quick Start` (115) with no `## Dependencies` heading at all — the candidate's insertion has no upstream analog and no disposition unit. MINOR is well-calibrated: the content is accurate (independently re-verified against `pyproject.toml` in the Dependency Accuracy checks) so this is purely a ledger-completeness gap, not a factual defect.

**Finding 4 (NIT — two `limitations.md` rows correctly omitted as unreachable dead code)** — **CONFIRMED**, and actually more rigorously than Stage A/B's own pass. Re-read `chart.py:1046-1067`: the `supported` tuple in `ChartCollection.add()` lists all 16 members of `ChartType` (independently re-verified the enum itself, `chart.py:11-28`, has exactly 16 members, `LINE=0` … `MAP=15`, none missing) — so the `raise NotImplementedError` at line 1067 is unreachable for any valid `ChartType` value, confirmed dead code. For `xml_chart_saver.py:492-498`: confirmed via `grep -n "_format_chart_xml("` that this method has exactly one call site (line 148), reached only through an `elif`/`else` chain (lines 125-148) that has already routed TREEMAP/WATERFALL/BOX_WHISKER/SUNBURST/HISTOGRAM/FUNNEL/MAP/COMBO/SCATTER/SURFACE/RADAR to dedicated formatters before falling through — leaving only LINE/BAR/PIE/AREA/STOCK reachable inside `_format_chart_xml`, all of which pass its internal STOCK-check-then-tuple-check without hitting the raise. Dead code confirmed from both ends (enum exhaustiveness and unique call-site narrowing), not just asserted. NIT labeling (positive confirmation, not a defect) is appropriate.

**Summary:** all four Verdict-section findings CONFIRMED against their own cited evidence with no downgrades or upgrades warranted; severities are calibrated appropriately (MAJOR/MAJOR/MINOR/NIT all track the actual blast radius — audit-trail integrity twice, ledger-completeness once, and a correct non-finding once). The one soft spot is Finding 1's "systemic" half, which rests on an unverified generalization beyond the single cited product.