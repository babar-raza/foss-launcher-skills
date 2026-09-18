## Identity

Four artifacts obtained (all read directly, not summarized):

| Artifact | Path | Hash / Commit | Notes |
|---|---|---|---|
| Candidate | `reports/repo-presenter-regen-full/slides/cpp/readme.md` | sha256 `9b754ac1…c606` | Matches `last-verified.json`'s recorded `readme_sha256` exactly. mtime 2026-08-20 19:58. |
| Current upstream (clone cache) | `runs/.clone_cache/aspose_slides_cpp/README.md` | sha256 `43265877…120f0`, HEAD `ecc2baf8cc3e3e4a6ee36cbfb992ec4fa6dd7765` ("docs: correct and expand README Key Capabilities accuracy", 2026-08-17 18:10:32 +0500) | Exists; git history: `ecc2baf → 25adb25 ("Fix save format param enum") → c673681 ("Initial")`. |
| Published (real, via `gh api`) | `repos/aspose-slides-foss/Aspose.Slides-FOSS-for-Cpp/contents/README.md` | sha256 `43265877…120f0` | **Byte-identical to current upstream/clone-cache** — confirms clone cache is not stale relative to GitHub. |
| Original-at-generation-time | inferred from disposition excerpts | = current upstream (`ecc2baf`) | `content-dispositions.json`'s embedded excerpts (e.g. u0001's intro paragraph, u0012-u0021's Key Capabilities bullets) are word-for-word identical to the `ecc2baf` README text, not to the older `25adb25`/`c673681` text. The candidate = `ecc2baf` README + one new "Dependencies" section (34-line diff, see Ledger). |

Knowledge base's own pinned baseline is **older** than the README content basis actually used: `knowledge/slides/cpp/merged/model.yaml:7` records `repo_sha: 25adb25c8796f06d9b89cd5f8093e490091195ef` (promoted 2026-07-12), one commit behind `ecc2baf`. `git -C runs/.clone_cache/aspose_slides_cpp diff --stat 25adb25 ecc2baf` shows only `README.md` changed between those two shas (no code files), so this lag does not corrupt API-level knowledge, but it is a real provenance mismatch (see Verdict #7).

Publication record: `data/readme_published_state.json` has a `slides`/`cpp` row: `"last_known_publication": "2026-08-18"`, evidence "canonical candidate byte-identical (stripped) to clone-cache upstream README (mt056_tree_reconciliation.json, T2_CURRENT_PUBLISHED)". `reports/repo_presenter_actions.jsonl` contains no `slides/cpp` row at all (only `note/python` and `cells/rust`).

## Factual Accuracy

All checkable factual claims in the candidate were verified true against the live clone-cache source:

- Intro/CMake integration claims (`FetchContent`, no PowerPoint/COM dependency) — consistent with `CMakeLists.txt`.
- License = MIT — `runs/.clone_cache/aspose_slides_cpp/LICENSE` confirms "MIT License / Copyright (c) 2026 Aspose Pty Ltd".
- `ShapeCollection::reorder()` exists — `include/Aspose/Slides/Foss/shape_collection.h:81,84`. Candidate's claim (readme.md:68) is accurate.
- `SlideCollection` has no reorder/move/swap method — confirmed absent from `slide_collection.h`. Candidate correctly omits this claim (matching upstream-issues.md's own note that this is a real gap, not a wording fix).
- Format support (PPTX import/export only) matches `knowledge/slides/cpp/merged/formats.md` exactly (all other formats "-").
- Banner image `https://products.aspose.org/media/slides/cpp/banner-readme.png` resolves to a real local asset: `static/media/slides/cpp/banner-readme.png` (313,725 bytes).
- Documentation cross-links (`docs.aspose.org/slides/cpp/`, `kb.aspose.org/slides/cpp/`, `reference.aspose.org/slides/cpp/`) all have real corresponding local content directories (3, 17, 165 entries respectively) — not premature/broken links.

No factually false statement was found in the candidate's prose itself. The accuracy problems found are in the **API Reference table's scope** (see API Accuracy) and in the **surrounding audit artifacts** (upstream-issues.md, disposition ledgers), not in the README's narrative claims.

## Content-Preservation Ledger

Original (= `ecc2baf` upstream, per Identity) vs. candidate, unit-by-unit, cross-checked against the candidate text myself (not just the JSON's self-report):

| Original unit type | Count | Disposition (per JSON) | My verification |
|---|---|---|---|
| Prose/content units (`content-dispositions.json`) | 114 (u0001–u0114) | 100% `merged_verbatim` | Confirmed: every excerpt I sampled (intro, Key Capabilities bullets, Installation, Scope and Limitations, License) appears verbatim in `readme.md` at the stated `target_section`. **PRESERVED**, correctly reasoned. |
| Structural units (`structure-dispositions.json`) | 1 (s0001, the "At a Glance" mermaid diagram) | `merged_verbatim` | Confirmed present unchanged at readme.md:25-54. **PRESERVED**. |
| Badges (`badge-dispositions.json`) | 3 (License, C++/language, Contributors) | 100% `preserved` | Confirmed present verbatim at readme.md:3. **PRESERVED**. |
| Code examples (`code-example-dispositions.json`) | 13 top-level ids (c0001–c0013, some split a/b/c) | 100% `merged_verbatim` | Confirmed: 13 real fenced blocks in candidate map 1:1 to these ids and target sections (mermaid, 2 build/CMake blocks, 2 Quick Start blocks, format/fill, table, connector, shadow, notes, comments, doc-properties, ctest). **PRESERVED**. |
| **New "Dependencies" section** (readme.md:14, 129–144 — nav entry + H2 + 3×H3 + 4 bullets, ~16 lines) | 1 major addition | **Not present in any of the 4 ledgers** | Grepped all four JSON files for `"Dependencies"`, `"Required Package"`, `"Native and System"`, `"Development Dependencies"` — the only hit is an unrelated pre-existing sentence ("Dependencies are fetched automatically…", content-dispositions.json:292, which is the *old* inline Installation-section text, not the new section). **UNTRACKED-ADDITION** — does not fit PRESERVED/TRANSFORMED/MERGED/DROPPED taxonomy since it's net-new candidate content with zero disposition record of any kind, despite being independently verifiable as accurate (see Dependency Accuracy). |

No unit was found DROPPED-SILENTLY, DROPPED-WITH-REASON, or INCORRECTLY-EXCLUDED from the original — the candidate is a strict superset of the `ecc2baf` original plus the untracked Dependencies section.

## Usability

- Navigation TOC (readme.md:9-21) matches actual heading order and all 11 anchors resolve correctly, including the trickier GitHub slug for "Documentation & Resources" → `#documentation--resources` (double-hyphen, matches GitHub's actual `&`-stripping slug algorithm) — verified correct, not a bug.
- Progressive disclosure via `<details>` for Additional Examples and API Reference keeps the top of the README scannable — good practice, preserved from original.
- Usability harm from API Accuracy finding below: a developer skimming "View the Core API Surface" cannot tell which of the ~160 listed types are meant for direct use vs. internal plumbing (`XmlElement`, `ContentTypesManager`, `RelationshipsManager`, etc.), which actively invites misuse of unstable internal types.
- The mislabeled `NotesSlidePart-Aspose_Slides_Foss` row (see API Accuracy) is a literal identifier fragment that isn't valid C++ and will confuse a reader trying to match it to real code.

## Presentation/SEO

- Heading hierarchy is well-formed (single H1, consistent H2/H3 nesting including the new Dependencies H3s).
- Badges have proper alt text; banner image has alt text ("Aspose.Slides FOSS for C++") and links to the product page.
- No broken Markdown table syntax found in the large Classes/Structs/Enums tables (spot-checked several hundred rows during earlier reads — well-formed pipes throughout).
- No SEO-relevant defects found (title, description-equivalent intro paragraph, and structured headings are all present and accurate).

## Dependency Accuracy

All dependency claims verified directly against `runs/.clone_cache/aspose_slides_cpp/CMakeLists.txt`:

- `pugixml` v1.14 (XML parsing) — CMakeLists.txt:19-27 (`GIT_TAG v1.14`). ✓
- `miniz` 3.0.2 (ZIP I/O) — CMakeLists.txt:29-36 (`GIT_TAG 3.0.2`). ✓
- `googletest` v1.15.2 (build/test only) — CMakeLists.txt:38-44 (`GIT_TAG v1.15.2`), plus `enable_testing()`/`gtest_discover_tests()` at CMakeLists.txt:47,52. ✓
- C++20 / CMake 3.20+ — CMakeLists.txt:1 (`cmake_minimum_required(VERSION 3.20)`), CMakeLists.txt:5 (`set(CMAKE_CXX_STANDARD 20)`). ✓

The new, ledger-untracked "Dependencies" section (readme.md:129-144) is itself **factually accurate** against this same source — the accuracy problem for this section is purely one of missing provenance/audit-trail (see Ledger), not of incorrect content.

## Example Verification

All three upstream-only compile bugs flagged in `upstream-issues.md` are **already corrected in the candidate**, and the corrected forms match the real declared signatures:

- **Notes**: `notes_slide_manager.h:49` declares `INotesSlide* add_notes_slide() override;` (pointer). Candidate (readme.md:305-308) uses `auto* notes = …; notes->notes_text_frame().set_text(...)` — correct.
- **Table/Cell**: `cell.h:145` declares `[[nodiscard]] TextFrame* text_frame() noexcept` (pointer). Candidate (readme.md:233) uses `cell.text_frame()->set_text("Blue")` — correct.
- **Comments**: `comment_collection.h:35` declares `Comment& add_comment(const std::string&, Slide& slide, …)` (reference, not pointer). Candidate (readme.md:330-332) passes `slide` by reference, not `&slide` — correct.
- The Format/Fill example (readme.md:199-208) correctly calls `shape.fill_format()` (the shape's own fill, per `shape.h`) rather than the old buggy version's `fmt.fill_format()` (portion-level fill) — a deliberate, verified-correct redesign matching what independently landed upstream in `ecc2baf` too.

## API Accuracy

Two related, well-evidenced defects in the "Core API Surface" table (readme.md:363-622):

1. **Internal-namespace classes presented as public API.** The README's own text calls this table (and the linked `reference.aspose.org` page) "the complete, browsable reference for the public API surface" (readme.md:630-632). At least 22 of the table's rows are sourced from headers under the upstream repo's own `_internal/` directory — a directory name the upstream project itself uses to mark non-public implementation detail (confirmed via `find runs/.clone_cache/aspose_slides_cpp/include -iname "xml_element.h"` etc., which shows these types exist *only* under `_internal/`, with no public-path counterpart). Confirmed leaked rows include: `AppPropertiesPart`, `AuthorData`, `CommentAuthorsPart`, `CommentsPart`, `ContentTypesManager`, `CorePropertiesPart`, `CustomPropertiesPart`, `ExporterBase`, `ExporterRegistry`, `InMemoryOpcPackage`, `LayoutSlidePart`, `MasterSlidePart`, `NotesSlidePart`, `OpcPackage`, `PptxExporter`, `PptxExporterFactory`, `RelationshipsManager`, `SlidePart`, `XmlElement`, `Attributes`, `Elements`, `Ns`, `Relationship` (readme.md lines 369, 370, 389, 392, 394-396, 399-400, 416, 420, 427, 432, 434, 448-449, 453, 464, 471, 477-478, 481, 486). `knowledge/slides/cpp/merged/api_surface.json` has zero `is_public`/`is_internal` field anywhere (`Grep` returned 0 matches), indicating this C++ product's scout does not tag public-vs-internal status at all — a likely systemic gap for the C++ language adapter (the clone cache also holds `aspose_cells_cpp`, `aspose_email_cpp`, `aspose_pdf_cpp`, which plausibly use the same `_internal/` convention).

2. **The one real name collision is disambiguated backwards.** Two distinct real classes are both literally named `NotesSlidePart`: `Aspose::Slides::Foss::Internal::pptx::NotesSlidePart` (`_internal/pptx/notes_slide_part.h`, doc "Manages a notes slide XML part…") and the actual public `Aspose::Slides::Foss::NotesSlidePart` (`notes_slide_part.h`, doc "Internal representation of a notes slide's placeholder storage…"). The candidate assigns the clean, unsuffixed name `NotesSlidePart` (readme.md:432) to the **internal** class, and relegates the **actual public** class to the synthetic, non-compilable identifier `NotesSlidePart-Aspose_Slides_Foss` (readme.md:433) — the disambiguation logic picked the wrong one to keep clean.

## Link/Rendering

- All 11 internal TOC anchors resolve to real headings, including the special-character case (`Documentation & Resources` → `#documentation--resources`, GitHub's actual double-hyphen slug — verified correct).
- Mermaid diagram (readme.md:25-54) is syntactically well-formed (`flowchart TD`, balanced subgraphs) and artifacts render mermaid natively on GitHub.
- External links (GitHub issues, pugixml/miniz/googletest repos, `products.aspose.com` Enterprise Edition) are well-formed and consistent with the product family's URL conventions; not independently re-verified via a live HTTP fetch (no network tool used, per read-only scope), but every *internal* aspose.org cross-link (docs/kb/reference/products for slides/cpp) was confirmed to have real corresponding local content.
- No malformed Markdown, no dangling image references, no broken table syntax found.

## Verdict

No BLOCKER found — every factual/code claim I could check in the candidate's own visible text (dependencies, all three previously-buggy examples, the reorder claim and its deliberate omission for SlideCollection, cross-links, banner asset) is accurate against source. The defects below are about the **API Reference table's scope/labeling** and the **integrity of the supporting audit trail**, not about false narrative prose.

1. **MAJOR — SYSTEMIC (likely).** Internal-namespace (`_internal/`) implementation classes leak into the "Core API Surface" table that the README itself labels the public API surface (22 confirmed rows: readme.md:369,370,389,392,394-396,399-400,416,420,427,432,434,448-449,453,464,471,477-478,481,486). Root cause: `knowledge/slides/cpp/merged/api_surface.json` has no `is_public`/`is_internal` field at all (0 Grep matches) — the C++ scout does not implement the `_internal/`-path exclusion that other language scouts appear to have (cf. Python's underscore-prefix exclusion). Likely recurs on `cells/cpp`, `email/cpp`, `pdf/cpp` (all present in `runs/.clone_cache/`) if they use the same convention.

2. **MAJOR — product-specific, but the underlying mechanism (finding #1) is systemic.** The one genuine cross-namespace name collision, `NotesSlidePart`, is disambiguated backwards: the internal class keeps the clean name (readme.md:432, `api_surface.json:3430-3436`) while the real public class is relabeled to the malformed, non-compilable `NotesSlidePart-Aspose_Slides_Foss` (readme.md:433, `api_surface.json:33857-33862`).

3. **MAJOR — SYSTEMIC (likely).** An entire new "## Dependencies" section (readme.md:14, 129-144) is present in the candidate with **zero corresponding entry in any of the four disposition ledgers** (verified by reading and grepping all of `content-dispositions.json`, `structure-dispositions.json`, `badge-dispositions.json`, `code-example-dispositions.json` — no hit for "Dependencies" as a new section, only an unrelated pre-existing sentence at content-dispositions.json:292). The content is independently verified accurate against `CMakeLists.txt`, but the ledgers' apparent purpose — accounting for every unit of candidate content — is broken for any net-new section a refresh adds rather than transforms from the original, which is plausibly a general pattern for this pipeline's disposition-tracking design, not unique to this product.

4. **MAJOR — product-specific.** `upstream-issues.md` is stale: it reports 3 FUNCTIONAL-DEFECT compile bugs as unresolved in "the real README," "Verified: 2026-08-13 against … repo_sha 25adb25" (upstream-issues.md:1-4), but the real upstream repo fixed all three in commit `ecc2baf` ("docs: correct and expand README Key Capabilities accuracy", dated 2026-08-17 18:10:32 +0500 — 4 days after the stated verification date; confirmed via `git -C runs/.clone_cache/aspose_slides_cpp log --oneline -- README.md` and `git … diff 25adb25 ecc2baf -- README.md`). The candidate (generated 2026-08-20, after the fix) already reflects the corrected content, so this is purely a stale/unrefreshed side-artifact, not a candidate defect — but it now actively misinforms anyone consulting it about the present state of the real upstream repo.

5. **MINOR.** `content-dispositions.json` units u0042/u0043/u0044 (readme.md:367-538, the entire Classes/Structs/Enums tables spanning dozens of source files) all cite the identical, non-specific `"evidence_ref": "include/Aspose/Slides/Foss/presentation.h"` as their `verified_against_source` proof (content-dispositions.json:568-604). This citation grain is too coarse to catch findings #1/#2 and lets "verified_against_source" status pass without row-level checking — exactly the kind of self-report the audit brief warned not to trust.

6. **MINOR / informational.** `data/readme_published_state.json`'s `slides`/`cpp` row (`last_known_publication: 2026-08-18`, "canonical candidate byte-identical (stripped) to clone-cache upstream README") was true as of that date but is now stale given finding #3 — a republish is effectively pending to sync the new Dependencies section, though the record's own design doc says this is meant to be mechanically re-derived per audit run rather than trusted long-term. Separately, `reports/repo_presenter_actions.jsonl` has zero rows for `slides/cpp` (only `note/python` and `cells/rust` are logged) despite a real publication being recorded elsewhere — a traceability gap between the two logs.

7. **NIT.** `knowledge/slides/cpp/merged/model.yaml:7` pins `repo_sha: 25adb25…`, one commit behind the README content basis actually reflected in the candidate (`ecc2baf`). Harmless here only because `git diff --stat 25adb25 ecc2baf` shows exclusively `README.md` changed (no API/code files), so no factual knowledge went stale — but the field itself is not an accurate record of what upstream state the candidate reflects.

## Stage B: Source Cross-Check

All citations below are my own, obtained by directly reading the named files/running the named commands in this session (not copied from Stage A).

### Factual Accuracy

| # | Claim | Verdict | My evidence |
|---|---|---|---|
| 1 | CMake `FetchContent` integration, no PowerPoint/COM dependency | **CONFIRMED** | `runs/.clone_cache/aspose_slides_cpp/CMakeLists.txt:20-44` — three `FetchContent_Declare`/`FetchContent_MakeAvailable` blocks (pugixml, miniz, googletest); no COM/PowerPoint reference anywhere in the file. |
| 2 | License = MIT, copyright Aspose Pty Ltd 2026 | **CONFIRMED** | `runs/.clone_cache/aspose_slides_cpp/LICENSE:1-3` — read in full: "MIT License / Copyright (c) 2026 Aspose Pty Ltd". |
| 3 | `ShapeCollection::reorder()` exists (candidate readme.md:68) | **CONFIRMED** | `runs/.clone_cache/aspose_slides_cpp/include/Aspose/Slides/Foss/shape_collection.h:81` (`void reorder(std::size_t new_index, Shape& shape) override;`) and `:84` (span overload). |
| 4 | `SlideCollection` has no reorder/move/swap | **CONFIRMED** | Read `slide_collection.h` in full (197 lines) — only `add_clone`/`insert_clone`/`add_empty_slide`/`insert_empty_slide`/`remove`/`remove_at`/`index_of`/iterators; no reorder/move/swap/set_index method anywhere. |
| 5 | Format support = PPTX import/export only, all else "-" | **CONFIRMED** | `knowledge/slides/cpp/merged/formats.md:1-25` — every row is `-`/`-` except `| PPTX | Yes | Yes |`. |
| 6 | Banner asset resolves, 313,725 bytes | **CONFIRMED** | `ls -la static/media/slides/cpp/banner-readme.png` → `313725` bytes exactly. |
| 7 | docs/kb/reference cross-links have real local content | **CONFIRMED** (methodology differs from Stage A) | `find content/kb.aspose.org/en/slides/cpp -maxdepth 2 -type f \| wc -l` → 17 (matches Stage A). `find content/reference.aspose.org/en/slides/cpp -maxdepth 2 -type f \| wc -l` → 165 (matches Stage A). For docs, my recursive file count is 14, not 3 — but `find content/docs.aspose.org/en/slides/cpp -maxdepth 1` shows exactly 3 top-level entries (`_index.md`, `developer-guide/`, `getting-started/`), so Stage A's "3" is a non-recursive listing count, mine is a recursive file count; both confirm real, non-empty content — no actual disagreement, just different counting granularity worth noting. |
| 8 | Chart/SmartArt/OLE shape types don't exist (Scope and Limitations) | **CONFIRMED** | `grep` over all 263 `api_surface.json` names for chart/smartart/ole → zero hits; `find include -iname "*chart*" -o -iname "*smartart*" -o -iname "*ole*"` → no files. |
| 9 | Only a PPTX exporter registered | **CONFIRMED** | `include/Aspose/Slides/Foss/_internal/export/` contains only `exporter_base.h`, `exporter_registry.h`, `pptx_exporter.h` — no other exporter implementation exists. |
| 10 | `Presentation` is file-path-only, no stream/byte-buffer save | **CONFIRMED** | `presentation.h:34-39` (only `Presentation()` and `explicit Presentation(std::string_view path)`), `:101` (`void save(std::string_view path, SaveFormat format) override;`) — no stream/span overload anywhere in the 167-line file. |

### Dependency Accuracy

All four confirmed directly against `runs/.clone_cache/aspose_slides_cpp/CMakeLists.txt` (read in full, 53 lines):
- pugixml v1.14 — line 24 (`GIT_TAG v1.14`). **CONFIRMED**
- miniz 3.0.2 — line 33 (`GIT_TAG 3.0.2`). **CONFIRMED**
- googletest v1.15.2 — line 42 (`GIT_TAG v1.15.2`). **CONFIRMED**
- C++20 / CMake 3.20+ — line 1 (`cmake_minimum_required(VERSION 3.20)`), line 5 (`set(CMAKE_CXX_STANDARD 20)`). **CONFIRMED**
- `data/package_registry.json` → `slides.cpp`: `"registry_type": "nuget"`, `"verification": {"published": false, ...}` — independently supports the candidate's "No NuGet package has been published for this library yet" claim (readme.md:93). **CONFIRMED**

### Example Verification (previously-buggy patterns)

- `add_notes_slide()` returns `INotesSlide*` — **CONFIRMED**, `notes_slide_manager.h:49` (`INotesSlide* add_notes_slide() override;`). Candidate's `auto* notes = …; notes->notes_text_frame().set_text(...)` (readme.md:306-307) is correct; also confirmed `notes->notes_text_frame()` itself returns `TextFrame&` via `notes_slide.h:62`.
- `Cell::text_frame()` returns `TextFrame*` — **CONFIRMED**, `cell.h:145` (`[[nodiscard]] TextFrame* text_frame() noexcept { return text_frame_.get(); }`). Candidate's `cell.text_frame()->set_text("Blue")` (readme.md:233) is correct.
- `CommentCollection::add_comment` takes `Slide&`, not `Slide*` — **CONFIRMED**, `comment_collection.h:35-37` (`Comment& add_comment(const std::string& text, Slide& slide, Drawing::PointF position, std::chrono::system_clock::time_point created_time) override;`). Candidate passes `slide` (already `Slide&` from `auto& slide = pres.slides()[0];` at readme.md:329) by reference — correct.
- Fill-format redesign (`shape.fill_format()`) — **CONFIRMED**, `shape.h:69` (`[[nodiscard]] FillFormat& fill_format() override { return fill_format_; }`) exists on `Shape` itself; candidate's `shape.fill_format().set_fill_type(...)` (readme.md:205) is correct.
- `upstream-issues.md` staleness — **CONFIRMED**: file itself (read in full) states "Verified: 2026-08-13 ... repo_sha 25adb25...". `git -C runs/.clone_cache/aspose_slides_cpp log --oneline -- README.md` → `ecc2baf → 25adb25 → c673681`; `git show -s --format='%H %ci %s' ecc2baf...` → `2026-08-17 18:10:32 +0500 docs: correct and expand README Key Capabilities accuracy` (4 days after the stated verification date). `git diff --stat 25adb25 ecc2baf` → `README.md | 610 +++... 1 file changed, 503 insertions(+), 107 deletions(-)` — only README.md changed, no code files, confirming the knowledge-lag is harmless as Stage A concluded.

### API Accuracy

**Finding #1 (internal-namespace leak) — CONFIRMED, but Stage A's scope count is materially understated.** I parsed `knowledge/slides/cpp/merged/api_surface.json` programmatically (263 total entries: 206 classes, 42 enums, 15 structs) and found **29** top-level entries whose `canonical_namespace` contains `::Internal::` (not "at least 22"/23 as Stage A listed). I then grepped `reports/repo-presenter-regen-full/slides/cpp/readme.md` for every one of those 29 names and confirmed **all 29 appear as rows in the candidate's "Core API Surface" table**, including six that Stage A's list omitted entirely:
- `XmlWriter` — readme.md:491 (Structs table) ← `api_surface.json` canonical_namespace `Aspose::Slides::Foss::Internal::opc`, file `_internal/opc/content_types_manager.h`
- `HeadingPairData` — readme.md:479 ← `Internal::pptx`, `_internal/pptx/app_properties_part.h`
- `PortionFormatSource` — readme.md:484 ← `Internal::pptx`, `_internal/pptx/bulk_text_format.h`
- `ParagraphFormatSource` — readme.md:482 ← same file
- `TextFrameFormatSource` — readme.md:490 ← same file
- `CommentData` — readme.md:391 ← `Internal::pptx`, `_internal/pptx/comments_part.h`

None of these six have a public-namespace counterpart (verified via `by_name` lookup — single hit each, all `Internal`). A further consequence I confirmed: of the 15 total struct-kind entries in `api_surface.json`, **9 (60%)** are internal-only (the 6 above plus `Ns`, `Elements`, `Attributes`, `Relationship` that Stage A did list) — meaning the README's "Structs" sub-table (readme.md:475-491) is majority internal-implementation detail, not a minor edge case. The remaining 6 structs (`PointF`, `RectangleF`, `Size`, `SizeF`, `MasterReference`, `SlideReference`) are genuinely public (`Aspose::Slides::Foss` / `Aspose::Slides::Foss::Drawing`, no `Internal`). No `enum_specifier` entries are internal (checked all 42) — the Enumerations table is clean. Root-cause claim (`api_surface.json` has no `is_public`/`is_internal` field) independently reconfirmed: 0 matches for either key anywhere in the 43,858-line file.

**Finding #2 (NotesSlidePart collision reversed) — CONFIRMED with exact citations.** Two distinct classes both named `NotesSlidePart` exist in `api_surface.json`:
- Entry at `api_surface.json:3430-3436`: `"canonical_namespace": "Aspose::Slides::Foss::Internal::pptx"`, `"doc": "Manages a notes slide XML part (ppt/notesSlides/notesSlideN.xml). Provides access to notes text and placeholder management."`, `"file": "include/Aspose/Slides/Foss/_internal/pptx/notes_slide_part.h"`, `"line": 37` — matches the real header I read at `_internal/pptx/notes_slide_part.h:34-37` verbatim ("Manages a notes slide XML part... Provides access to notes text and placeholder management." / `class NotesSlidePart final {` at line 37).
- Entry at `api_surface.json:33856-33862`: `"canonical_namespace": "Aspose::Slides::Foss"` (no `Internal`), `"doc": "Internal representation of a notes slide's placeholder storage. Tracks which placeholders are present and their text content."`, `"file": "include/Aspose/Slides/Foss/notes_slide_part.h"`, `"line": 14` — matches the real public-path header I read verbatim (`notes_slide_part.h:12-14`).

Candidate readme.md:432 (`NotesSlidePart` — "Manages a notes slide XML part...") uses the doc text of the **`Internal::pptx`-namespaced** entry, and readme.md:433 (`NotesSlidePart-Aspose_Slides_Foss` — "Internal representation of a notes slide's placeholder storage.") uses the doc text of the **`Aspose::Slides::Foss`-namespaced (non-Internal)** entry. This confirms Stage A's finding exactly, and additionally reveals the mangling mechanism: the `-Aspose_Slides_Foss` suffix is literally the public entry's own `canonical_namespace` (`Aspose::Slides::Foss`) with `::`→`_`, i.e., the disambiguator suffixed the namespace-*public* class and left the namespace-*internal* one with the bare name — backwards, as Stage A described, now with the exact mechanism identified.

**New finding (unflagged by Stage A) — MINOR, API Reference prose self-inconsistency.** readme.md:562 states `Slide` — `notes_slide_manager() -> NotesSlideManager&`. The actual declared return type is `INotesSlideManager&` (the interface), not the concrete `NotesSlideManager&` class: `runs/.clone_cache/aspose_slides_cpp/include/Aspose/Slides/Foss/slide.h:74,77` —
```
[[nodiscard]] INotesSlideManager& notes_slide_manager() override { return notes_slide_manager_; }
[[nodiscard]] const INotesSlideManager& notes_slide_manager() const override { ... }
```
This is a real signature inaccuracy, and notably the README is self-inconsistent about it: two lines later in the same table (readme.md:613) it correctly documents `NotesSlideManager::add_notes_slide() -> INotesSlide*` using the interface-typed return — so the document is careful about interface-vs-concrete return types everywhere except this one line. Functionally harmless (both types expose the same three methods used in the examples — confirmed via `i_notes_slide_manager.h:16,19,22`), but it is a factual error in a table that otherwise prides itself on signature precision (e.g., correctly flagging `Cell::text_frame() -> TextFrame*` as a pointer). Everything else spot-checked in the Detailed Member Reference (readme.md:544-621) against source — `Presentation`'s `slides()/comment_authors()/images()/document_properties()/masters()/layout_slides()/save()` (`presentation.h:61-101`), `Slide::shapes()` (`slide.h:55-56`), `GroupShape::shapes()` (`group_shape.h:18,21`), `EffectFormat::outer_shadow_effect() -> OuterShadow*` (`effect_format.h:72`), `ImageCollection::add_image()` byte-span-only (`image_collection.h:31`, confirmed no other overload exists), and `DocumentProperties`' `set_title`/`set_author`/`set_custom_property_value`/`get_custom_property_value`/`remove_custom_property` (`document_properties.h:42,52,207,210,216`) — is **CONFIRMED** accurate.

### Ledger / provenance cross-checks (independently re-run, not just re-cited)

- `content-dispositions.json` — parsed with Python: **114** units, `Counter({'merged_verbatim': 114})` — 100% merged_verbatim, ids u0001–u0114. **CONFIRMED.**
- `structure-dispositions.json` — 1 unit, `s0001`, `"disposition": "merged_verbatim"`, heading "At a Glance". **CONFIRMED.**
- `badge-dispositions.json` — 3 units (`b0001` license, `b0002` language_version, `b0003` contributor_count), all `"action": "preserved"`. **CONFIRMED.**
- `code-example-dispositions.json` — grepped unit_ids: `c0001..c0005, c0006a/b/c, c0007a/b/c, c0008a/b/c, c0009a/b/c, c0010, c0011a/b/c, c0012, c0013` = 13 top-level ids with a/b/c splits. **CONFIRMED.**
- "Dependencies" section untracked — grepped all four ledger files for "Dependencies"/"Required Package"/"Native and System"/"Development Dependencies": the only hit across all four files is `content-dispositions.json:292` (`"excerpt": "Dependencies are fetched automatically via CMake \`FetchContent\`:"`), which is the pre-existing Installation-section sentence, not the new H2 "## Dependencies" section (readme.md:129-144, nav entry at readme.md:14). **CONFIRMED — zero ledger entries for the new section**, and its content (pugixml v1.14, miniz 3.0.2, googletest v1.15.2, C++20/CMake 3.20+) is independently accurate against `CMakeLists.txt` as re-verified above.
- u0042/u0043/u0044 coarse evidence — read directly: all three cite `"evidence_ref": "include/Aspose/Slides/Foss/presentation.h"` (lines 576, 589, 602) for the entire Classes (u0042), Structs (u0043), and Enumerations (u0044) tables. **CONFIRMED**, and u0042's own excerpt text embeds the mangled `NotesSlidePart-Aspose_Slides_Foss` string verbatim — i.e., the disposition ledger recorded the defect's output without flagging it.
- `data/readme_published_state.json` — `slides`/`cpp` row: `"last_known_publication": "2026-08-18"`, evidence `"MT056 reconciliation: canonical candidate byte-identical (stripped) to clone-cache upstream README (mt056_tree_reconciliation.json, T2_CURRENT_PUBLISHED)"`. **CONFIRMED verbatim.**
- `reports/repo_presenter_actions.jsonl` — parsed all rows: only `('cells','rust')` and `('note','python')` families present; **zero** `slides`/`cpp` rows. **CONFIRMED.**
- `knowledge/slides/cpp/merged/model.yaml:7` — `repo_sha: 25adb25c8796f06d9b89cd5f8093e490091195ef`. **CONFIRMED verbatim**, and independently reconfirmed harmless via `git diff --stat 25adb25 ecc2baf` (README.md only, no code files) as shown above.
- `limitations.md` (43-row stub/unimplemented-method table) — scanned in full; nothing in it contradicts any candidate claim (its `NotesSlide`/`AuthorData`/`CommentData` "empty body" rows are trivial-constructor/stub false-positives from the extraction heuristic, not functional gaps the README claims otherwise about).

No REFUTED claims and no additional BLOCKER-level defects were found. All UNVERIFIABLE items from Stage A (live external HTTP links) remain unverifiable under this same read-only, no-network scope.

## Stage C: Adversarial Verification

**1. MAJOR — SYSTEMIC (likely): Internal-namespace classes leak into "Core API Surface".** **CONFIRMED**, and understated rather than overstated. Independently re-parsed `api_surface.json`: confirmed 0 matches for `is_public`/`is_internal` field names, but the schema does carry a `visibility` field — populated as `"public"` on literally all 263/263 entries (checked programmatically), which is arguably worse than "field absent" since it looks like a real signal but is inert. Recomputed the internal-namespace set independently (matched on `canonical_namespace` containing `Internal`): got **29**, matching Stage B, not Stage A's Verdict-text "22" — and the Verdict's own cited line list (`369,370,389,392,394-396,...`) expands to 23 line numbers by my count, not 22, an internal arithmetic slip in the finding's own text. All 29 names confirmed present as rows in readme.md's Classes/Structs tables by direct read. The "likely recurs on cells/cpp, email/cpp, pdf/cpp" breadth claim is **only partly supported**: `pdf/cpp`'s own scouted `api_surface.json` has 92/340 (27%) entries sourced from an `include/internal/` directory — stronger evidence than the hedge implies; `cells/cpp` has a weak signal (3/200, an `InternalValidation` namespace); but `email/cpp` shows **zero** internal-marked entries (no internal directory exists in its clone at all) — the "likely recurs" claim does not hold for that specific product. Severity MAJOR is fairly calibrated for slides/cpp itself.

**2. MAJOR — product-specific, mechanism systemic: `NotesSlidePart` collision reversed.** **CONFIRMED exactly.** Re-read `api_surface.json:3430-3436` and `:33856-33862` verbatim — both doc strings, file paths, and line numbers (37, 14) match the citations character-for-character, and both match the real headers I re-read directly. Re-read readme.md:432-433 — confirmed the internal class keeps the bare `NotesSlidePart` name and the public class is relabeled `NotesSlidePart-Aspose_Slides_Foss`. Product-specific tag is justified (this exact name collision is particular to this repo's history); severity MAJOR is reasonable given the identifier is literally non-compilable if copy-pasted.

**3. MAJOR — SYSTEMIC (likely): "Dependencies" section untracked in any ledger.** **CONFIRMED, and the systemic tag is understated rather than overstated.** Re-grepped all four ledger JSONs myself — only one hit across all of them (`content-dispositions.json:292`, the pre-existing Installation sentence), zero entries for the new H2. Went further than either prior stage: read `check_content_unit_disposition_coverage`'s actual implementation in `readme_refresh_checks.py` — it is structurally one-directional: it only requires that every unit `extract_old_readme_content_units` finds *in the old README* has a disposition; there is no corresponding check that walks the *new candidate* and flags prose/sections with no disposition trace. This is a designed one-way gate, not a one-off miss — so "(likely)" is arguably too weak a hedge; this will recur for *any* refresh that adds a net-new section. Severity MAJOR is justified given this is a hole in the pipeline's core verification guarantee, not merely a paperwork gap.

**4. MAJOR — product-specific: `upstream-issues.md` is stale.** **CONFIRMED fully**, all citations reproduced independently. `git log --oneline -- README.md` → `ecc2baf → 25adb25 → c673681`; `git show -s` on `ecc2baf` → `2026-08-17 18:10:32 +0500`, four days after the file's stated "Verified: 2026-08-13." Went further and confirmed the *actual fix content* is present in current upstream (not just inferred from the candidate): `runs/.clone_cache/aspose_slides_cpp/README.md` itself now uses `auto* notes = …; notes->notes_text_frame().set_text(...)` (line 288-289), `cell.text_frame()->set_text("Blue")` (line 215), and passes `slide` by reference to `add_comment` (lines 310-312) — all three previously-buggy patterns are gone from upstream itself, not just patched in the candidate. Also confirmed real downstream consequence: `upstream_issue_workflow.py` actively ingests `upstream-issues.md` into a finding-ID pipeline, so this staleness isn't inert — supports MAJOR, not overstated.

**5. MINOR: u0042/u0043/u0044 share one coarse `evidence_ref`.** **CONFIRMED exactly.** Re-read `content-dispositions.json` lines 566-604 directly — all three cite `"evidence_ref": "include/Aspose/Slides/Foss/presentation.h"` verbatim at exactly lines 576, 589, 602 as claimed, and u0042's embedded excerpt does contain the mangled `NotesSlidePart-Aspose_Slides_Foss` string verbatim. MINOR severity is properly calibrated — this is a citation-granularity defect, not a factual one.

**6. MINOR/informational: publication-state staleness + `repo_presenter_actions.jsonl` traceability gap.** **CONFIRMED verbatim.** `data/readme_published_state.json`'s `slides`/`cpp` row matches the quoted text exactly (line 14). `reports/repo_presenter_actions.jsonl` parsed independently: exactly 2 lines, families `{('cells','rust'), ('note','python')}`, zero `slides`/`cpp` rows. Calibration as MINOR/informational is reasonable — doesn't affect reader-facing content accuracy.

**7. NIT: `model.yaml` `repo_sha` one commit behind.** **CONFIRMED verbatim.** Read `model.yaml:7` directly → `repo_sha: 25adb25c8796f06d9b89cd5f8093e490091195ef`, matches exactly. Re-ran `git diff --stat 25adb25 ecc2baf` myself → `README.md | 610 +++... 1 file changed, 503 insertions(+), 107 deletions(-)`, confirming only README.md changed (no code files) — the "harmless" qualifier holds. NIT severity is appropriate.

No Verdict finding was falsified or found to overstate its core claim; if anything, findings #1 and #3 are calibrated slightly conservatively relative to what direct re-verification shows (finding #1's true internal-leak count is 29, not 22, and `pdf/cpp` shows a *worse* leak ratio than slides/cpp itself; finding #3's "systemic (likely)" is a structural guarantee, provable from the checker's own code, not merely a probabilistic inference). The one real overreach is finding #1's specific naming of `email/cpp` as a likely-recurrence candidate — that product's clone cache has no internal-marked entries at all.