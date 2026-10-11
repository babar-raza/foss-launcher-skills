## Identity

Four of the four requested artifact types were obtained and directly read:

| Artifact | Path | Content hash / ref |
|---|---|---|
| Original-at-generation-time README | `runs/.clone_cache/aspose_cells_rust/README.md` @ pinned SHA `0339b7e7dcb65c3ac0f77ddbe0effb69c83f0e2e` (retrieved via `git -C runs/.clone_cache/aspose_cells_rust show 0339b7e:README.md`) | 163 lines; not separately hashed but full text read and diffed |
| Current live upstream README | `runs/.clone_cache/aspose_cells_rust/README.md` (working tree, HEAD = `1a6004a`) | sha256 `b0460fc66e5cbc03f71d48f9d913ee1a3dca7ff3dee1a3ff4ac0ac94458b5cca` (CRLF line endings) |
| Candidate | `reports/repo-presenter-regen-full/cells/rust/readme.md` | sha256 `71de1b2fe224df2ec332c6f4b2ee0c181afb659e5c6b01ad4703d9d3ecd8e436` (matches `last-verified.json`'s `readme_sha256`) |
| Actually-published README (real GitHub API read) | `gh api repos/aspose-cells-foss/Aspose.Cells-FOSS-for-Rust/contents/README.md` | sha256 `71de1b2fe224df2ec332c6f4b2ee0c181afb659e5c6b01ad4703d9d3ecd8e436` — **identical** to candidate and to live clone-cache README after normalizing line endings (`diff --strip-trailing-cr` → empty on both comparisons) |

Git history of the clone cache (`git -C runs/.clone_cache/aspose_cells_rust log --oneline -- README.md`):
```
1a6004a docs: refresh repository presentation (#1)
0339b7e V26.7.0
```
`1a6004a` is authored by Babar Raza, `Co-authored-by: Claude Sonnet 5 <noreply@anthropic.com>`, dated 2026-08-14, "748 lines changed, 651 insertions(+), 97 deletions(-)" on `README.md` only (`git diff --stat 0339b7e 1a6004a -- . ':!README.md'` → empty, confirming **zero source-code drift** between the knowledge-pinned SHA and current HEAD).

**Key identity finding**: this "candidate" is not a pending, unreviewed artifact — it is already live in production, byte-identical (mod CRLF) to what's actually published on GitHub. See Verdict for the tracking-ledger implications.

## Factual Accuracy

- Intro claims (pure-Rust, no proprietary runtime, no MS Office install, no external Aspose dependency, from-scratch OOXML implementation) — consistent with the crate being a pure-Rust `zip`/`roxmltree`/`chrono`/`sha2`/`base64`/`getrandom`/`serde_json` implementation confirmed against `Cargo.toml`. No contradicting evidence found.
- "213 public types" (readme.md:344) — independently cross-verified: `grep -o '"kind": *"[a-zA-Z_]*_item"' knowledge/cells/rust/merged/api_surface.json | sort | uniq -c` → 177 struct_item + 35 enum_item + 1 trait_item = 213, and the candidate's own Structs/Enumerations/Traits tables have exactly 177/35/1 rows respectively (verified by `awk`-scoped `grep -c '^| \`'` per table). **Confirmed accurate.**
- "Not yet published to crates.io" (readme.md:105, 674) — confirmed independently via `data/package_registry.json` line 37: `"verification": {"published": false, ...}` for `aspose-cells-foss-rust`.
- "No automated test suite ships... cargo test --all-targets reports 0 tests" (readme.md:671, 684-685) — consistent with `upstream-issues.md`'s disclosed finding and with the CI workflow at `runs/.clone_cache/aspose_cells_rust/.github/workflows/ci.yml:56-57` (`cargo test --all-targets` step exists but there is no `tests/` dir).
- CI matrix claim "Linux x64, Windows x64, macOS ARM, macOS x64" (readme.md:702-703) — verified verbatim against `.github/workflows/ci.yml:31-38` matrix `include:` block (exact `name:`/`os:` values match).
- Chart-type breadth claim (readme.md:87-89: "column, line, bar, area, pie, doughnut, scatter, radar, bubble, and stock families, plus their stacked and 3D variants") — verified against the real `ChartType` enum in `src/Aspose.Cells_FOSS/ChartType.rs`: all nine named families exist (`Bar`, `Area`/`AreaStacked`/`Area3D`, `Column`/`ColumnStacked`/`Column3D`, `Pie`/`Pie3D`, `Doughnut`, `Scatter*`, `Radar*`, `Bubble`/`Bubble3D`, `Stock*`) plus additional undisclosed families (`Cone`, `Cylinder`, `Pyramid`) that the README doesn't even claim — i.e. the claim **understates** rather than overstates real capability. No inaccuracy.
- No fabricated or unverifiable claims were found anywhere in the candidate.

## Content-Preservation Ledger

Original README (163 lines, pinned SHA `0339b7e`) mapped against the candidate (717 lines). Note: `content-dispositions.json`'s `"excerpt"` field actually quotes the **candidate's** final text (not the original's), with `verification.evidence_ref` pointing at clone-cache source — so the JSON is a destination-indexed provenance ledger, not an original-indexed one. I built the original→candidate mapping myself by reading both files directly.

| Original unit | Disposition | Evidence |
|---|---|---|
| Title | PRESERVED | identical `# Aspose.Cells FOSS for Rust` |
| Intro paragraph | TRANSFORMED (merged_reframed, u0001) | candidate reframes/expands; core facts kept |
| Inline crate hyperlinks in intro (`[zip](https://crates.io/crates/zip)` etc., 7 links, orig lines 11-16) | **DROPPED-SILENTLY** | `grep -n "crates.io/crates" .../readme.md` → 0 matches in candidate; present in original (6 hits). Not listed among the 3 disclosed omissions in `upstream-issues.md` |
| `## Status` heading + prose | MERGED into "Scope and Limitations" (u0103) | content preserved, heading dropped (non-lossy restructure) |
| `## Features` (14 bullets) | MERGED/TRANSFORMED into "Key Capabilities" (u0014-u0025) | all 14 original feature items traced into the 12 expanded bullets; none missing |
| `## Installation` (incl. wrong `cd "Aspose.Cells FOSS for Rust - Github"` bug) | TRANSFORMED — bug **fixed** | candidate uses correct `cd Aspose.Cells-FOSS-for-Rust`; fix disclosed in `upstream-issues.md` §"Old README's local-build path did not match the real repository name" |
| `## Quick start` code block | PRESERVED VERBATIM | byte-for-byte identical code between orig lines 76-104 and candidate lines 155-183 |
| `## Documentation` (samples link, AGENTS.md link, `cargo doc`, GH Pages) | MERGED/relocated into "Documentation & Resources" + "Development and Testing" | samples/README.md link (u0098) and AGENTS.md link (u0099) preserved; `cargo doc`/Pages text relocated into u0108, content intact |
| `## Samples` heading + 13-row table with per-file "Focus" descriptions | TRANSFORMED (table → prose list, u0107/u0108) | Focus-column detail not silently lost: candidate's redirect "(see samples/README.md for the full overview)" is truthful — verified `samples/README.md` still carries the same 13-row Focus table |
| `## Project layout` (short tree) | TRANSFORMED/EXPANDED (u0041) | grounded against `src/lib.rs`; adds License/, AGENTS.md, Cargo.toml, README.md entries |
| `## License` one-liner | PRESERVED+EXPANDED (u0109) | adds accurate description of what MIT permits |
| New in candidate, not from original: badges, banner image, Navigation TOC, "At a Glance" diagram, "Additional Examples" (5 snippets), "Dependencies" section (versioned), "API Reference" section (213-type table + detailed member reference), docs/kb/reference.aspose.org links, "Open an issue" link | ADDED | all independently verified against source (see Example/API/Dependency sections below); none fabricated |

Every `content-dispositions.json` / `structure-dispositions.json` / `code-example-dispositions.json` / `badge-dispositions.json` unit's claimed `target_section` was checked by reading the candidate and holds true — no unit points at a section where its text does not actually appear.

## Usability

- TOC → heading anchors all resolve under GitHub's slug algorithm (spot-checked `#documentation--resources` against heading `## Documentation & Resources`, which strips `&` and doubles the hyphen correctly).
- Two `<details>/<summary>` collapsible blocks ("Additional Examples", "Complete Public API Surface") are both correctly opened and closed (`grep -c "<details>"` = 2, `grep -c "</details>"` = 2), so neither swallows trailing sections on GitHub's renderer.
- All 12 fenced code blocks (`mermaid`, `toml` ×2, `bash` ×2, `rust` ×7) are properly paired — verified by listing every fence line and confirming each opener has a matching bare `` ``` `` closer.
- Quick Start example is a near-verbatim excerpt of the real, compiling `samples/basic.rs` (matches lines 15-32 of that file for the shared portion), so a reader who copies it gets working code.
- No usability defects found.

## Presentation/SEO

- Badges: License (MIT) and Rust Edition (2021) both verified accurate against `LICENSE.txt` presence and `Cargo.toml`'s `edition = "2021"`.
- Banner image `https://products.aspose.org/media/cells/rust/banner-readme.png` — local asset exists at `static/media/cells/rust/banner-readme.png`.
- No SEO-relevant defects (no keyword stuffing, no broken heading hierarchy — single H1, sequential H2/H3 use) found.

## Dependency Accuracy

All 7 declared runtime dependencies independently cross-checked against the real, live `runs/.clone_cache/aspose_cells_rust/Cargo.toml` `[dependencies]` table (not just trusting `dependency-verification-matrix.json`'s self-report):

| Crate | README version | Cargo.toml version | Match |
|---|---|---|---|
| chrono | 0.4 | 0.4 | ✓ |
| zip | 0.6 | 0.6 | ✓ |
| sha2 | 0.10 | 0.10 | ✓ |
| base64 | 0.22 | 0.22 | ✓ |
| serde_json | 1 | 1 | ✓ |
| roxmltree | 0.20 | 0.20 | ✓ |
| getrandom | 0.3 | 0.3 | ✓ |

No `[dev-dependencies]` section exists in `Cargo.toml`, consistent with `dependency-verification-matrix.json`'s empty `scoped_claims`. One preservation defect noted above: the crates.io hyperlinks that accompanied each dependency in the original README were dropped without disclosure.

## Example Verification

All code examples were checked against the real, checked-in `samples/*.rs` files (not just the self-reported dispositions):

- Quick Start snippet — matches `samples/basic.rs` lines 15-32 (same variable names, same cell addresses, same API calls, minus the `chrono` timestamp cell — a legitimate simplification for a minimal quickstart).
- "Add Charts From Data Ranges" — `charts.add(ChartType::Column, "Charts!$B$1:$B$13".to_string(), 0, 4, 18, 8)` matches `samples/charts.rs` argument-for-argument.
- "Apply Conditional Formatting Rules" — `add_area`, `add_condition_with_details`, `set_priority(1)`, `FillPattern::Solid`, `fill_color = Some("FFFFC7CE")` all verified present verbatim in `samples/conditional_formatting.rs` lines 41-59.
- "Enforce Data Validation Rules" — matches `samples/validations.rs` (List type, `set_formula1`, `set_in_cell_drop_down`, `set_show_error`, `set_error_title`/`set_error_message`).
- "Build a Structured Excel Table (ListObject)" — `add_a1("A1","D5",true)`, `set_display_name`, `set_table_style_type(TableStyleMedium2)`, `set_show_totals(true)`, `get_list_columns().get(3)...set_totals_calculation(Sum)` all verified against `samples/list_objects.rs` lines 46-70 (column index 3 = Quantity, confirmed correct).
- "Hyperlinks and Defined Names" — `set_text_to_display`, `set_screen_tip`, `get_defined_names`, `set_hidden` all verified present in `samples/hyperlinks_and_names.rs`.

No fabricated, incorrect, or non-compiling-looking example was found.

## API Accuracy

- Struct/enum/trait table totals (177/35/1 = 213) verified exactly against `knowledge/cells/rust/merged/api_surface.json`'s item-kind counts (see Factual Accuracy).
- `CellsError` "enum, 10 members including Unsupported(&'static str), Io(String)" (readme.md:648) — verified against `src/Aspose.Cells_FOSS/api.rs:653-664`: exactly 10 variants (`SheetNotFound`, `WorksheetIndexOutOfRange`, `InvalidSheetName`, `InvalidZoom`, `InvalidCellReference`, `InvalidInput`, `IndexOutOfRange`, `Io`, `OverlappingMergedRange`, `Unsupported`), including both named examples. **Exact match.**
- `Workbook` methods listed in "Detailed Member Reference" (readme.md:586-597: `new`, `load_xlsx`, `load_xlsx_from_stream`, `load_xlsx_from_bytes`, `load_xlsx_with_options`, `get_worksheets`/`get_worksheets_mut`, `worksheet(name)`, `get_settings`/`get_properties`, `get_document_properties`, `get_defined_names`, `get_load_diagnostics`, `save`/`save_xlsx`, `save_xlsx_to_stream`/`save_xlsx_to_bytes`) — every one verified to exist in `src/Aspose.Cells_FOSS/Workbook.rs`.
- Minor NIT: prose signatures in the API Reference section systematically drop `&self`/reference-return annotations (e.g. `worksheet(name) -> Result<Worksheet, CellsError>` vs. the real `pub fn worksheet(&self, name: &str) -> Result<&Worksheet, CellsError>`; `get_worksheets() -> Worksheets` vs. real `Worksheets<'_>`). This is applied uniformly throughout the section (a documentation-style simplification, not a factual error) and does not mislead given the accompanying, accurate code examples.

## Link/Rendering

- `runs/.clone_cache/aspose_cells_rust/LICENSE.txt`, `AGENTS.md`, `.github/workflows/ci.yml`, `.github/workflows/pages.yml`, `samples/README.md` — all confirmed to exist via `ls`.
- `docs.aspose.org/cells/rust/`, `kb.aspose.org/cells/rust/`, `reference.aspose.org/cells/rust/`, `products.aspose.org/cells/rust/` — all four subdomain content directories exist locally with real content (9/5/214/1 files respectively via `find ... -type f | wc -l`), not empty stubs.
- GitHub issues link `https://github.com/aspose-cells-foss/Aspose.Cells-FOSS-for-Rust/issues` — repo confirmed to exist and be reachable (the `gh api .../contents/README.md` call in Identity succeeded against this exact repo).
- No broken or dangling links found.

## Verdict

**Finding 1 — MAJOR — likely systemic — Real publication untracked in both governance ledgers.**
The candidate is already live in production: `gh api repos/aspose-cells-foss/Aspose.Cells-FOSS-for-Rust/contents/README.md --jq .content | base64 -d` returns content with sha256 `71de1b2fe224df2ec332c6f4b2ee0c181afb659e5c6b01ad4703d9d3ecd8e436`, identical to `reports/repo-presenter-regen-full/cells/rust/readme.md` and to `runs/.clone_cache/aspose_cells_rust/README.md` (both diff clean with `--strip-trailing-cr`), and matches `last-verified.json`'s recorded `readme_sha256`. This was merged as commit `1a6004af47b1ef15385f9d36d381a8172428cc7e` ("docs: refresh repository presentation (#1)", `git -C runs/.clone_cache/aspose_cells_rust log --oneline -- README.md`), authored 2026-08-14, `Co-authored-by: Claude Sonnet 5`. Yet:
  - `reports/repo_presenter_actions.jsonl` (2 lines total) contains exactly one cells/rust event: `{"action": "readme_push_dry_run", "timestamp": "2026-08-18T18:14:31Z", "details": {"commit_sha": "71ef1a02bbbc39c018943c2299fa1294b1225e20", "pr_url": null, "dry_run": true}}` — a **dry run**, four days *after* the real merge, citing a *different* commit SHA than the one actually merged.
  - `data/readme_published_state.json` has zero entries for `family=cells, platform=rust` (only `go`/`java`/`net` exist for the `cells` family), despite the file's own stated purpose — "durable per-product record of README publication events... `_do_push` appends/updates an entry on every real (non-dry-run) push... Seeded 2026-08-18 from the authoritative plan's own recorded PR/merge history."
  This is precisely the class of gap this ledger was built to close (its own header cites TC-HARDEN-47/48 as the motivating incident), yet it missed a product that was already merged four days before the seeding date. Because the ledger is what feeds the `published_readme_current` advisory drift-check, cells/rust currently has no mechanism watching for future upstream README drift. Flagged systemic because the omission traces to the MT056 seeding sweep's methodology, not to anything specific to cells/rust.

**Finding 2 — MINOR — possibly systemic (unconfirmed on other products) — Dependency crates.io hyperlinks dropped silently.**
The original README (`git show 0339b7e:README.md` lines 11-16) linked each of the 7 runtime crates to its crates.io page (`` [`zip`](https://crates.io/crates/zip) `` etc.). The candidate's "## Dependencies" section (readme.md:137-143) lists the same 7 crates with version numbers but zero hyperlinks (`grep -n "crates.io/crates" reports/repo-presenter-regen-full/cells/rust/readme.md` → no matches). This omission is not among the three items disclosed in `upstream-issues.md`, so it reads as an unintentional, silent content loss rather than a documented trade-off.

**Finding 3 — NIT — product-specific — `last-verified.json` missing run linkage.**
`reports/repo-presenter-regen-full/cells/rust/last-verified.json` records `"verified_by_run_id": null` alongside a populated `"verified_at": "2026-08-25T17:58:34.059097Z"`, so the verification event cannot be traced back to a specific run record. Low-impact traceability gap only.

**Finding 4 — NIT — systemic by design (uniform across the doc) — API Reference signatures elide borrows/lifetimes.**
E.g. `worksheet(name) -> Result<Worksheet, CellsError>` (readme.md:590) vs. the real `pub fn worksheet(&self, name: &str) -> Result<&Worksheet, CellsError>` (`src/Aspose.Cells_FOSS/Workbook.rs:236`); `get_worksheets() -> Worksheets` (readme.md:589) vs. real `Worksheets<'_>`. Applied consistently as a doc-style simplification throughout the "Detailed Member Reference" section; does not mislead given the accurate, verified code examples elsewhere in the same document. Not a factual-accuracy defect.

No BLOCKER-severity findings were identified. Dependency accuracy, API accuracy (member existence, counts, and the CellsError enum), all six code examples, the CI-matrix claims, and the chart-type breadth claim all independently verified correct against live source — this is one of the more thoroughly source-grounded README candidates reviewable in this audit family. The dominant issue is not content quality but governance/tracking: the artifact under review is not actually a pending candidate at all — it's already shipped — and that fact is invisible in the very ledger built to prevent exactly this kind of blind spot.

All independent verification complete. Here is the Stage B section.

## Stage B: Source Cross-Check

**Method**: every claim below was re-verified by reading the cited source files myself in this session — no citation was reused from Stage A without independently re-running the check.

### Dependency Accuracy — all CONFIRMED

`runs/.clone_cache/aspose_cells_rust/Cargo.toml` `[dependencies]` block, read directly:
```
chrono = "0.4"
zip = "0.6"
sha2 = "0.10"
base64 = "0.22"
serde_json = "1"
roxmltree = "0.20"
getrandom = "0.3"
```
This is an exact, complete match to the candidate's "Dependencies" section (`reports/repo-presenter-regen-full/cells/rust/readme.md:137-143`) and to the table in Stage A. **CONFIRMED**, all 7 crates, all versions. No `[dev-dependencies]` section exists in `Cargo.toml` — confirmed by full-file read, not just Stage A's report reference.

### Factual Accuracy claims

- **"Not yet published to crates.io"** — **CONFIRMED**. `data/package_registry.json:26-38` (`"rust": {...}`) shows `"verification": {"published": false, ...}` for the `aspose-cells-foss-rust` candidate at `repo_sha 0339b7e7dcb65c3ac0f77ddbe0effb69c83f0e2e`. Read directly, not assumed from Stage A's line citation.

- **"No automated test suite ships... cargo test --all-targets reports 0 tests"** — **CONFIRMED**. `ls runs/.clone_cache/aspose_cells_rust/tests` → `No such file or directory` (no tests directory exists at all). `runs/.clone_cache/aspose_cells_rust/.github/workflows/ci.yml` (full file read) contains a `- name: cargo test` / `run: cargo test --all-targets` step inside the `build-and-test` job — the step exists but with zero discoverable tests, exactly as claimed.

- **CI matrix "Linux x64, Windows x64, macOS ARM, macOS x64"** — **CONFIRMED verbatim**. Full `ci.yml` `matrix.include` block:
```
- name: Linux x64      os: ubuntu-latest
- name: Windows x64    os: windows-latest
- name: macOS ARM      os: macos-14
- name: macOS x64      os: macos-13
```
Exact string match to readme.md:702-703's four names, in the same order.

- **Chart-type breadth claim** (readme.md:87-89: "column, line, bar, area, pie, doughnut, scatter, radar, bubble, and stock families, plus their stacked and 3D variants")** — **CONFIRMED, and confirmed as an understatement**. Full read of `src/Aspose.Cells_FOSS/ChartType.rs` (92 lines) shows all nine claimed families present with stacked/3D variants (`Column`/`ColumnStacked`/`Column3D`/`Column3DClustered`/`Column3D100PercentStacked`, `Bar`/`BarStacked`/`Bar3D*`, `Area`/`AreaStacked`/`Area3D*`, `Pie`/`Pie3D`/`PiePie`/`PieExploded`, `Doughnut`/`DoughnutExploded`, `Scatter` + 4 connected variants, `Radar`/`RadarWithDataMarkers`/`RadarFilled`, `Bubble`/`Bubble3D`, `Stock` + 4 variants, `Line` + variants). The enum additionally contains undisclosed families the README never mentions: `Cone*`, `Cylinder*`, `ConicalBar*`, `CylindricalBar*`, `Pyramid*`, `Surface3D`, `SurfaceWireframe3D`, `Contour`, `SurfaceContour*`, `BoxAndWhisker`, `BoxWhisker`, `Funnel`, `ParetoLine`, `Sunburst`, `Treemap`, `Waterfall`, `Histogram`, `Map`, `Unknown`. Claim is accurate and conservative, not inflated.

### API Accuracy claims

- **"213 public types" / 177 structs + 35 enums + 1 trait** — **CONFIRMED, independently recomputed twice**. (1) Against `knowledge/cells/rust/merged/api_surface.json`: `grep -o '"kind": *"[a-zA-Z_]*"'` → `177 struct_item`, `35 enum_item`, `1 trait_item` (also `176 property`, `6 function`, not claimed in the README's headline count). (2) Against the candidate document itself, by `awk`-scoping each of its own three tables and counting `^| \`` rows: Structs table = 177 rows, Enumerations table = 35 rows, Traits table = 1 row. Both independent counts agree exactly: 177+35+1 = 213.

- **`CellsError` "enum, 10 members including Unsupported(&'static str), Io(String)"** — **CONFIRMED, exact match**. `runs/.clone_cache/aspose_cells_rust/src/Aspose.Cells_FOSS/api.rs:653-664`, full enum body read directly:
```rust
pub enum CellsError {
    SheetNotFound(String), WorksheetIndexOutOfRange(usize), InvalidSheetName,
    InvalidZoom(i32), InvalidCellReference(String), InvalidInput(String),
    IndexOutOfRange(String), Io(String), OverlappingMergedRange,
    Unsupported(&'static str),
}
```
Exactly 10 variants; both named examples (`Unsupported(&'static str)`, `Io(String)`) present verbatim.

- **`Workbook` method list (readme.md:586-597)** — **CONFIRMED**. `grep -n "pub fn "` over the full `Workbook.rs` (694 lines) shows every claimed method exists: `new`, `load_xlsx`, `load_xlsx_from_stream`, `load_xlsx_from_bytes`, `load_xlsx_with_options`, `get_worksheets`/`get_worksheets_mut`, `worksheet(name)`, `get_settings`/`get_properties`, `get_document_properties`, `get_defined_names`, `get_load_diagnostics`, `save`/`save_xlsx`, `save_xlsx_to_stream`/`save_xlsx_to_bytes`. All present, no fabrications.

- **NIT re: elided borrows/lifetimes** — **CONFIRMED as a real, systemic simplification**. Source signatures read directly: `Workbook.rs:236` → `pub fn worksheet(&self, name: &str) -> Result<&Worksheet, CellsError>` vs. candidate's `worksheet(name) -> Result<Worksheet, CellsError>`; `Workbook.rs:268` → `pub fn get_worksheets(&self) -> Worksheets<'_>` vs. candidate's `get_worksheets() -> Worksheets`. Confirmed non-misleading given the exact, verbatim code examples elsewhere in the same document (see Example Verification below).

### Example Verification — independently re-run against live sample source, all CONFIRMED

- Quick Start: candidate readme.md:155-183 vs. `samples/basic.rs:1-35` (full file read) — identical variable names, cell addresses (A1–G1), and API call sequence, with only the `E1`/timestamp `put_value_date_time` line omitted (legitimate quickstart simplification, confirmed by direct diff-by-eye of both blocks).
- Charts: `charts.add(ChartType::Column, "Charts!$B$1:$B$13".to_string(), 0, 4, 18, 8)` — matches `samples/charts.rs:35-36` (`ChartType::Column` at that call site) argument-for-argument.
- Conditional formatting: `add_area`, `add_condition_with_details(FormatConditionType::CellValue, OperatorType::Between, "3", "7")`, `set_priority(1)`, `FillPattern::Solid`, `fill_color = Some("FFFFC7CE"...)` — all read verbatim in `samples/conditional_formatting.rs:35-58`.
- Validations: `ValidationType::List`, `set_formula1("\"Open,Closed\"")`, `set_in_cell_drop_down(true)`, `set_show_error(true)`, `set_error_title("Invalid")`, `set_error_message("Choose from the list")` — all read verbatim in `samples/validations.rs:29-38`.
- ListObject: `tables.add_a1("A1", "D5", true)`, `set_display_name("Products")`, `set_table_style_type(TableStyleType::TableStyleMedium2)`, `set_show_totals(true)`, `columns.get(3)...set_totals_calculation(TotalsCalculation::Sum)` — verified against `samples/list_objects.rs:1-70`. Column-index check done independently: header row at `list_objects.rs:16-19` is `A1="Product", B1="Category", C1="Price", D1="Quantity"`, so 0-indexed column 3 = D = Quantity. **Confirmed correct**, not just trusted from Stage A.
- Hyperlinks/defined names: `set_text_to_display`, `set_screen_tip`, `get_defined_names`, `set_hidden` — all read verbatim in `samples/hyperlinks_and_names.rs:44-79`.

### Presentation/badges — CONFIRMED

- `edition = "2021"` — confirmed at `Cargo.toml:4`, matches "Rust 2021 edition" badge.
- MIT license badge — confirmed: `runs/.clone_cache/aspose_cells_rust/LICENSE.txt:1` reads "The MIT License (MIT)".
- Banner asset `static/media/cells/rust/banner-readme.png` — confirmed to exist on disk (312,511 bytes).

### New finding not surfaced by Stage A — Samples table row-count claim is inaccurate

Stage A's Content-Preservation Ledger asserts: *"verified `samples/README.md` still carries the same 13-row Focus table."* This is **REFUTED** on independent re-count:

- Original README's Samples table (`git -C runs/.clone_cache/aspose_cells_rust show 0339b7e:README.md`, lines 118-144) has **13 rows** (`basic.rs` through `document_properties.rs`), and it does **not** include `loading.rs`.
- The current, live `runs/.clone_cache/aspose_cells_rust/samples/README.md` (full file read) has **14 rows** — `grep -c "^| \`"` → 14 — because a `sample_loading` / `loading.rs` row (line 28) was added that has no counterpart in the original 13-row table. This matches the 14 `[[bin]]` targets independently counted in `Cargo.toml` and the 14 `.rs` files (excluding `common.rs`) independently listed in `ls samples/`.

So the *content* is still accurate and non-lossy (the candidate's own redirect text — "see `samples/README.md` for the full overview" — remains true, and no information was lost), but Stage A's specific verification claim ("the same 13-row table") is factually wrong: it's a 14-row table, and it is not "the same" as the original — it has one additional row (`loading.rs`) that never existed in the pre-refresh README. This is a NIT-level correction to Stage A's own citation, not a defect in the candidate document itself.

### Summary

Every claim in Stage A's Factual Accuracy, Dependency Accuracy, and API Accuracy sections that I independently re-checked against live source (`Cargo.toml`, `ChartType.rs`, `api.rs`, `Workbook.rs`, `ci.yml`, `package_registry.json`, `api_surface.json`, and all six referenced `samples/*.rs` files) is **CONFIRMED** with my own fresh evidence, matching Stage A's conclusions exactly. No REFUTED or UNVERIFIABLE findings emerged among the flagged claims themselves. The one new issue found via independent re-verification is procedural, not substantive: Stage A mis-stated the samples-table row count in its own supporting citation (claimed 13 rows "the same" as original; actual current count is 14, with `loading.rs` added since the original). No additional unflagged high-risk claims were found during this pass — the Scope and Limitations text (no XLS/ODS/CSV, one-worksheet-minimum, no test suite, not on crates.io) is also independently confirmed against `knowledge/cells/rust/merged/formats.md` (XLSX-only, Import/Export both Yes) and `limitations.md` ("No NotImplementedError patterns detected").

## Stage C: Adversarial Verification

**Finding 1 — MAJOR, "likely systemic" — Real publication untracked in both governance ledgers.**
CONFIRMED, and the "likely systemic" hedge is actually understated. Independently re-verified every load-bearing fact: `gh api repos/aspose-cells-foss/Aspose.Cells-FOSS-for-Rust/contents/README.md` (live network call, not reused from the review) decodes to sha256 `71de1b...b5cca`, diff-clean (`--strip-trailing-cr`) against both the candidate and the clone-cache README; `git -C runs/.clone_cache/aspose_cells_rust show -s --format=%H|%an|%ad|%s|%b 1a6004a` confirms the exact SHA, author, 2026-08-14 date, and Co-authored-by trailer cited; `git diff --stat 0339b7e 1a6004a -- . ':!README.md'` is genuinely empty (zero source drift); `reports/repo_presenter_actions.jsonl` genuinely contains only 2 lines total, with the cells/rust row a `readme_push_dry_run` dated 2026-08-18 citing a different SHA (`71ef1a0...`) than the real merge; `data/readme_published_state.json` genuinely has zero `cells/rust` entries (only go/java/net) and its own `_comment` genuinely cites TC-HARDEN-47/48 as the motivating incident. Beyond the review's own evidence, I independently found a **second, live-verified instance of the identical gap**: `cells/cpp`'s own "docs: refresh README... (#2)" merge (`9f852d0`, 2026-08-13) is *also* byte-identical (mod CRLF) to the real live GitHub README (independently fetched and diffed by me), and `cells/cpp` is *also* absent from `readme_published_state.json`. A same-pattern scan of all 30 clone caches turned up roughly a dozen more candidates (barcode/python, cells/python, cells/typescript, email/cpp, email/net, email/python, font/python, html/python, pdf/go, pdf/python, slides/java, slides/net, slides/python, words/python) with an apparent local "docs: refresh" commit not reflected in the ledger — unverified against live GitHub by me, so not asserted as fact, but strong circumstantial support that this is not an edge case. Severity MAJOR is not overstated.

**Finding 2 — MINOR, "possibly systemic (unconfirmed on other products)" — Dependency crates.io hyperlinks dropped silently.**
CONFIRMED. Re-ran the exact checks: original `0339b7e:README.md` lines 11–16 do contain 7 distinct `crates.io/crates/*` links (zip, roxmltree, chrono, sha2, base64, getrandom, serde_json — confirmed via `grep -o ... | sort -u`) across 6 matching lines (sha2+base64 share one line, which reconciles the review's own "7 links... 6 hits" phrasing rather than contradicting it); `grep -n "crates.io/crates"` on the candidate returns zero matches (exit 1); the 3-item disclosed list in `reports/repo-presenter-regen-full/cells/rust/upstream-issues.md` was read in full and contains no mention of dropped hyperlinks. Severity MINOR and the explicitly-hedged "unconfirmed on other products" tag are both fair — not overclaimed.

**Finding 3 — NIT, "product-specific" — `last-verified.json` missing run linkage.**
UPGRADED (tag refuted, not the underlying fact). The `verified_by_run_id: null` field is real (confirmed by direct read), but "product-specific" is false: I checked every `last-verified.json` under `reports/repo-presenter-regen-full/` (`find ... -name last-verified.json | wc -l` → 30) and every single one — cells/go, cells/java, cells/net, words/net, and all 26 others — has `verified_by_run_id: null` with zero exceptions (`grep -l "verified_by_run_id\": \""` → 0 matches; `grep -l "verified_by_run_id\": null"` → 30/30). This is a universal, systemic gap in the verification tooling (it apparently never populates this field for anyone), not something specific to cells/rust. The NIT severity may even be too low once its true scope (100% of the tracking ledger has zero run provenance) is accounted for, but at minimum the "product-specific" characterization should be "systemic."

**Finding 4 — NIT, "systemic by design (uniform across the doc)" — API Reference signatures elide borrows/lifetimes.**
DOWNGRADED (the "uniform"/"applied consistently" framing is refuted; the base defect stands). Re-read `readme.md:589-590` and `Workbook.rs:236,268` and confirmed the two cited elisions exactly as stated (`worksheet(name) -> Result<Worksheet, CellsError>` vs. real `&self, name: &str) -> Result<&Worksheet, ...>`; `get_worksheets() -> Worksheets` vs. real `Worksheets<'_>`). But scanning the same "Detailed Member Reference" section for any reference/lifetime annotation (`grep -n "&self\|<'_>\|-> &"`) turns up a direct counter-example the review missed in both Stage A and Stage B: `readme.md:625` reads `get_font_mut() -> &mut Font`, and the real source (`Style.rs:383`) is `pub fn get_font_mut(&mut self) -> &mut Font` — here the candidate *keeps* the borrow annotation on the return type, in the same section, a few lines from where it drops it elsewhere. So the pattern is not actually uniform/"by design" — it's inconsistent. This doesn't change the NIT severity (still non-misleading given accurate examples), but "applied uniformly throughout the section" is a specific, checkable sub-claim that is false as stated.