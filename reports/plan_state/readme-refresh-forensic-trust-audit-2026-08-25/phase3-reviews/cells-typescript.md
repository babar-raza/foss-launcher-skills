## Identity

Four distinct artifact states were sought; all four were obtained.

| Artifact | Source | Obtained? | SHA-256 (as read) | SHA-256 (LF-normalized) |
|---|---|---|---|---|
| Original-at-generation-time | `git -C runs/.clone_cache/aspose_cells_typescript show cabbb9d8ba2067854f7cb3dcdc4acfeec849747b:README.md` (the commit cited by `upstream-issues.md:3`) | Yes | `1a2a4cf34bf48db85412a5b25ccc196c38b6fc735cbc308a4941a4219b881aa8` | n/a (LF already) |
| Current live upstream (clone cache) | `runs/.clone_cache/aspose_cells_typescript/README.md` (HEAD = commit `fc186507e5b7124f4664aa6035f25cfd3112367d`) | Yes | `4b01eb5a90b8a9560a6765259a25b05d677323b6ecbec12adb16a1c10169ace0` (CRLF) | `6e92da3a04ae70dadbe600431c38b19f7b16b50af338417fb2e7f2baadd0826c` |
| Candidate | `reports/repo-presenter-regen-full/cells/typescript/readme.md` | Yes | `a8af6b3ecf322969ebf22abba6073f2124b9702268c619028e8be752300b3534` (CRLF) | `d9ad00aac333e1faf07a186df8f87f2ff82aa7389b82a77e6e1db0cbf33c3d8a` |
| Published (real GitHub) | `gh api repos/aspose-cells-foss/Aspose.Cells-FOSS-for-TypeScript/contents/README.md --jq .content \| base64 -d` | Yes | `6e92da3a04ae70dadbe600431c38b19f7b16b50af338417fb2e7f2baadd0826c` (LF) | identical to clone cache |

Key identity facts:
- The clone cache's checked-out `README.md` is **byte-identical** to the real, currently-published GitHub `README.md` (once CRLF is stripped) — confirms the clone cache is not stale relative to the live repo.
- A **real, non-dry-run publish already happened**: `git -C runs/.clone_cache/aspose_cells_typescript log --oneline -- README.md` shows `fc18650 docs: refresh README with verified content, diagram, and dependency docs` on top of `cabbb9d add agents.md`. `gh api repos/aspose-cells-foss/Aspose.Cells-FOSS-for-TypeScript/commits` confirms `fc186507e5b7124f4664aa6035f25cfd3112367d` is a real commit on the real upstream default branch, authored by the user (`babar.raza@aspose.com`) with `Co-Authored-By: Claude Sonnet 5`, dated 2026-08-14. This publication is **not recorded** in `data/readme_published_state.json` or `reports/repo_presenter_actions.jsonl` (`grep -n -i "cells/typescript" data/readme_published_state.json reports/repo_presenter_actions.jsonl` → no matches in either file) — see Verdict finding V-3.
- The candidate under audit differs from the live/published README by exactly **one line** (line 323 — see Factual Accuracy).
- Expected sibling artifacts `last-verified.json` and `code-example-dispositions.json` **do not exist** for this product (`ls -la reports/repo-presenter-regen-full/cells/typescript/` → only `badge-dispositions.json`, `content-dispositions.json`, `readme.md`, `structure-dispositions.json`, `upstream-issues.md`), while both exist for sibling products `cells/net` and `cells/rust` in the same family. Code-example units for this product are instead embedded inside `structure-dispositions.json` (entries `s0001`/`s0002`) using a richer schema (`heading`, `excerpt`, `kind`) than the bare schema seen in other products' `structure-dispositions.json` (e.g. `3d/net`, verified directly).
- Knowledge bundle (`knowledge/cells/typescript/merged/model.yaml`) shows `repo_sha: fc186507e5b7124f4664aa6035f25cfd3112367d` and `promoted_at: '2026-08-24T06:11:30…'` — the knowledge base was re-promoted against the post-refresh commit, after the real push, consistent with a later re-verification/audit pass.

## Factual Accuracy

- All spot-checked factual claims in the candidate check out against real source (see API Accuracy / Dependency Accuracy / Example Verification below).
- **Defect (confirmed, MAJOR):** Candidate line 323, `## Scope and Limitations`: `[Aspose.Cells — Enterprise Edition](https://products.aspose.com/cells/)` (no platform qualifier). This is **correct** — but it is *not* what's actually live. The published/live README (verified identical between clone cache and `gh api .../contents/README.md`) reads `[Aspose.Cells for .NET — Enterprise Edition](https://products.aspose.com/cells/), which adds…` at the same line — mislabeling the generic Aspose.Cells commercial line as ".NET-specific" on the *TypeScript* product's own README. Cross-check against sibling candidates confirms the generic form is the house convention when no platform-specific commercial SKU exists: `reports/repo-presenter-regen-full/cells/rust/readme.md:678` uses the identical unqualified `[Aspose.Cells — Enterprise Edition](https://products.aspose.com/cells/)` wording for the same reason (no Aspose.Cells-for-Rust commercial product), while `cells/net`, `cells/java`, `cells/python`, `cells/cpp`, `cells/go` all correctly use their own platform name and platform-specific URL (confirmed via `grep -rn "Enterprise Edition" reports/repo-presenter-regen-full/cells/`). So: **the currently-live, real-world README has a real factual/branding inaccuracy that the audited candidate has already fixed**, but that fix has not been re-published.
- **Gap (confirmed, MAJOR):** `upstream-issues.md:5-24` discloses a real, confirmed functional defect — `Workbook.save()` silently writes XLSX binary data for `.csv`/`.json`/`.md`/`.markdown` target paths. Independently verified against source: `runs/.clone_cache/aspose_cells_typescript/aspose_cells/workbook.ts:394-421` — `save()` special-cases only `SaveFormat.HTML` (line 396); every other detected format (lines 427-429 in `detectFormat()`, confirmed to correctly identify `csv`/`json`/`md`/`markdown`) falls through to the generic ZIP-write path (lines 417-421), producing an XLSX-format file under the requested extension with no error. The candidate's `## Scope and Limitations` (readme.md:316-320) documents the *correct workaround* (call `toCsv()`/`toJson()`/`toMarkdown()` directly) but nowhere states the actual hazard — that calling `save()` with those extensions **silently corrupts output**. A reader who generalizes from the README's own HTML example (`await workbook.save("output.html", …)`, line 165, which *does* auto-dispatch correctly) has no textual warning against doing the same for `.csv`.

## Content-Preservation Ledger

Original README (`git show cabbb9d:README.md`, 116 lines) units, per `content-dispositions.json` (31 units, `u0001`-`u0031`) and `structure-dispositions.json` (2 units, `s0001`-`s0002`), each disposition verified by me directly against the candidate/source rather than trusted from the JSON:

**Headings** (not covered by any disposition file — verified by direct diff of headings between the two READMEs):
| Original heading | Candidate heading | Disposition |
|---|---|---|
| `# Aspose.Cells FOSS for TypeScript` | same | PRESERVED |
| `## Highlights` | `## Key Capabilities` | TRANSFORMED (retitled + expanded) |
| `## Installation` | `## Installation` | PRESERVED (content expanded) |
| `## Quick Start` → `### Create, style, and save a workbook` / `### Load and update a workbook` | `## Quick Start` (H3s dropped, replaced by inline lead-in prose) | TRANSFORMED |
| `## Supported Areas` | dissolved into `## Key Capabilities` + example list moved to new `## Additional Examples` | TRANSFORMED/MERGED |
| `## Build from Source` | `## Development and Testing` | TRANSFORMED (renamed + AGENTS.md pointer added) |
| `## Compatibility` | absorbed into new `## Dependencies` → `### Native and System Requirements` | MERGED |
| `## License` | `## License` | PRESERVED |
| `## Support` | `## Documentation & Resources` | TRANSFORMED (Issues link kept, 3 new links added) |

None of this heading-level restructuring is recorded in `structure-dispositions.json` (which holds only the two code-example entries). Cross-checked `reports/repo-presenter-regen-full/3d/net/structure-dispositions.json` (2 bare entries, no heading fields at all) — this appears to be the system's general behavior, not specific to this product (see Verdict V-4).

**Prose/capability facts** (`content-dispositions.json`, all independently re-checked):
| unit | excerpt | disposition | my verification |
|---|---|---|---|
| u0001, u0002 | intro paragraph / API-surface claim | merged_reframed → Intro | PRESERVED, matches candidate lines 7-11 |
| u0003-u0006, u0009-u0013, u0016 | load/save, cell/formula, style, worksheet settings, hyperlinks, validation/conditional-format, pictures | merged_reframed → Key Capabilities | PRESERVED, matches candidate lines 64-80; spot-verified `Worksheet.shapes`/`Workbook.images` real (`worksheet.ts:214-215`, `workbook.ts:85-86`), `Cell.putValue/setFormula/setStyle` real (`cell.ts:50,63,76`), `Style.setBold/setFontColor/setForegroundColor` real (`style.ts:79,115,124`) |
| u0007 | "Clone the repository and install dependencies" | merged_reframed → Installation | PRESERVED, candidate lines 84-90 |
| u0008 | "Workbook and worksheet management" | excluded (redundant) | Correct — genuinely redundant with u0001/u0002/u0003 |
| u0014 | "Page setup and print-related settings" | excluded (false claim) | INDEPENDENTLY CONFIRMED false: `grep -rni "pagesetup\|printarea\|print.setup\|printsettings"` across `aspose_cells/` and `examples/` → zero hits |
| u0015 | "Tables (`ListObjects`)" | excluded (false claim) | INDEPENDENTLY CONFIRMED false: `grep -rni "listobject"` → zero hits; only unrelated `HtmlTable` class exists |
| u0017 | "Document properties" + examples pointer | excluded (false claim + redundant) | INDEPENDENTLY CONFIRMED false: `grep -rni "documentproperties\|customdocumentproperties\|builtindocumentproperties"` → zero hits |
| u0018-u0026 | 9 example filenames | merged_reframed → Additional Examples | PRESERVED and CONFIRMED present: `ls runs/.clone_cache/aspose_cells_typescript/examples/` lists all 9 files exactly |
| u0027 | "Run commands from the repository root" | merged_reframed → Development and Testing | PRESERVED (prose only — see gap below for the adjoining code block) |
| u0028 | "Node.js 18+" | merged_reframed → Dependencies | PRESERVED in candidate line 102, **but mislabeled**: `verification.status: "verified_against_manifest"` while its own `evidence_note` admits "No explicit engines field in package.json" (`content-dispositions.json:466-477`). Independently confirmed `package.json` has no `engines` field. This is a carried-forward, unverified legacy claim mislabeled as manifest-verified (Verdict V-5). |
| u0029 | "TypeScript 5+" | merged_reframed → Dependencies | PRESERVED and genuinely verified: `package.json` devDependencies pins `typescript ^5.9.3` |
| u0030 | MIT license + path | merged_reframed → License | PRESERVED, path `License/LICENSE.txt` confirmed real (1108 bytes MIT text per `upstream-issues.md:44-46`) |
| u0031 | Issues link | merged_reframed → Documentation & Resources | PRESERVED, candidate line 314 |

**Code examples** (`structure-dispositions.json`):
| unit | disposition | verification |
|---|---|---|
| s0001 (create/style/save) | merged_verbatim → Quick Start | PRESERVED; independently confirmed `Workbook()` ctor, `worksheets.get()`, `putValue`, `getCell2`, `setFormula`, `Style`/`setBold`/`setFontColor`/`setForegroundColor`, `setStyle`, `save` all real |
| s0002 (load/update) | merged_verbatim → Quick Start | PRESERVED; `Workbook.load()` confirmed `static async load(filePath, password?)` (`workbook.ts:52`) |
| **(untracked, gap)** | the original's third code block — `npm install` / `npx tsc --noEmit` under "Build from Source" | **PRESERVED but with NO disposition record anywhere.** It survives, transformed, into candidate lines 331-334, but neither `content-dispositions.json` (u0027 covers only the adjoining prose sentence) nor `structure-dispositions.json` (only 2 entries, both Quick Start) accounts for it. See Verdict V-4. |

**Badges/images**: `badge-dispositions.json` = `[]` (3-byte file). This is **correct, not a gap** — the original README (`/tmp/original_readme.md`, verified) has zero badges and zero images of any kind. The candidate's License badge, Contributors badge, and banner image (lines 3-5) are net-new additions, out of scope for a "disposition of original units" ledger. Independently confirmed the banner asset is real and non-trivial: `static/media/cells/typescript/banner-readme.png`, 312,018 bytes.

**Net-new sections** (API Reference, Documentation & Resources' three new links, At a Glance diagram, Scope and Limitations) are new content, not original-README units, so their absence from `content-dispositions.json` is expected under that file's own scope — not counted as a ledger gap.

## Usability

- Navigation TOC (lines 13-25) matches actual headings 1:1 — verified by reading the full candidate.
- Quick Start is runnable-looking and self-contained; both snippets verified against real API (see above).
- The undisclosed `save()`-corruption hazard (Factual Accuracy) is a real usability trap: a reader who tries `workbook.save("out.csv")` by analogy with the documented `save("output.html", …)` pattern gets silent data corruption with no warning in the text.
- `<details>` collapsible blocks (Additional Examples table, full API surface table) are appropriately used to keep the top-level scannable while still surfacing full detail.

## Presentation/SEO

- Title, intro, and Documentation & Resources block give docs.aspose.org / kb.aspose.org / reference.aspose.org backlinks — all three target pages independently confirmed to exist and be live: `content/docs.aspose.org/en/cells/typescript/_index.md`, `content/kb.aspose.org/en/cells/typescript/_index.md`, `content/reference.aspose.org/en/cells/typescript/_index.md`.
- Banner image and badges give the page a branded look consistent with other launched FOSS products' READMEs (a look the original entirely lacked).
- Mermaid "At a Glance" diagram is new synthesized content; its capability nodes trace to already-verified Key Capabilities claims (u0003-u0006, u0009-u0013, u0016), so it isn't introducing unverified claims, just visualizing verified ones.

## Dependency Accuracy

All dependency claims cross-checked directly against `package.json` (read in full):
| Claimed (candidate lines 96-107) | package.json | Match |
|---|---|---|
| `@zip.js/zip.js` ^2.8.21 | `"@zip.js/zip.js": "^2.8.21"` | Exact |
| `@xmldom/xmldom` ^0.8.10 | `"@xmldom/xmldom": "^0.8.10"` | Exact |
| `adm-zip` ^0.5.16 | `"adm-zip": "^0.5.16"` | Exact |
| `@types/node` ^25.3.3 | `"@types/node": "^25.3.3"` | Exact |
| `typescript` ^5.9.3 | `"typescript": "^5.9.3"` | Exact |
| `ts-node` ^10.9.2 | `"ts-node": "^10.9.2"` | Exact |
| `tsx` ^4.21.0 | `"tsx": "^4.21.0"` | Exact |
| Node.js 18+ | no `engines` field | Carried-forward, unverifiable against manifest (mislabeled — see V-5) |

`upstream-issues.md:26-39` also correctly and separately discloses that `package.json`'s own `"name"` field (`"excel-cells"`) is not Aspose-branded — an accurate, well-scoped informational note, correctly kept out of the public README (a package-name choice isn't README-fixable).

## Example Verification

- Quick Start snippet 1 (create/style/save): every call verified real (see Content-Preservation Ledger, s0001).
- Quick Start snippet 2 (load/update): every call verified real (s0002).
- "Export a Workbook to HTML" snippet (candidate lines 161-166): `await workbook.save("output.html", { saveFormat: undefined })` — functionally correct (falls through `options?.saveFormat || this.detectFormat(filePath)` to `detectFormat("output.html")` → `SaveFormat.HTML`, `workbook.ts:394,426`), but passing an explicit `{ saveFormat: undefined }` is an unusual, slightly confusing way to write this for a "first example" (NIT — see V-6).
- All 9 example files referenced in the Additional Examples table are confirmed to exist: `ls runs/.clone_cache/aspose_cells_typescript/examples/` → `auto_filter.ts, cell_values.ts, data_validation.ts, export.ts, html_export.ts, hyperlinks.ts, index.ts, protection.ts, styles.ts, worksheet_management.ts`.

## API Accuracy

Spot-checked API Reference table entries against real source, all correct:
- `SaveFormat` "Enum with 5 members" — confirmed: `types.ts:177-183` (`XLSX, CSV, JSON, MARKDOWN, HTML` = 5).
- `EncryptionType` "Enum with 1 member" — confirmed: `types.ts:185-187` (`AES` = 1).
- `Worksheet.shapes: ShapeInfo[]`, `Workbook.images: ImageInfo[]` — confirmed real getters (`worksheet.ts:214-215`, `workbook.ts:85-86`).
- `Workbook.load()`/`save()`, `Cell.putValue/setFormula/setStyle`, `Style.setBold/setFontColor/setForegroundColor`, `Worksheet.putValue(key, value): Cell`, `WorksheetCollection.get(index)` — all confirmed real with matching signatures.
- No contradictions found between the API Reference table's class list and the real, current source during spot-checking.

## Link/Rendering

- `License/LICENSE.txt` — real path, confirmed 1108-byte MIT text (`upstream-issues.md:44-46`).
- `examples/` directory link and all 9 named example files — confirmed present.
- `agents.md` (candidate: `[AGENTS.md](agents.md)`) — real file exists at that exact lowercase path in the clone cache (`ls` output lists `agents.md`); link target case matches the real filename (only the *display text* is uppercase, which is cosmetic, not a broken link).
- `https://products.aspose.org/media/cells/typescript/banner-readme.png` — backing file confirmed present and non-trivial (312,018 bytes) at `static/media/cells/typescript/banner-readme.png`.
- `https://products.aspose.org/cells/typescript/`, `https://docs.aspose.org/cells/typescript/`, `https://kb.aspose.org/cells/typescript/`, `https://reference.aspose.org/cells/typescript/`, GitHub issues URL — all confirmed to have live corresponding content in this repo or point at the real, existing upstream repo.
- Mermaid block syntax (```mermaid fence, `flowchart TD`) is well-formed on inspection; no unmatched brackets or subgraph tags found on manual read.

## Verdict

Ten findings, most-severe first. No BLOCKER found.

1. **[MAJOR, likely product-specific in manifestation but systemic in mechanism]** The currently **live, published** upstream README (`runs/.clone_cache/aspose_cells_typescript/README.md:323`, byte-identical to `gh api repos/aspose-cells-foss/Aspose.Cells-FOSS-for-TypeScript/contents/README.md`) reads `[Aspose.Cells for .NET — Enterprise Edition](https://products.aspose.com/cells/)`, incorrectly branding the generic Aspose.Cells commercial upsell as ".NET-specific" on the TypeScript product's own page. The audited candidate (`reports/repo-presenter-regen-full/cells/typescript/readme.md:323`) already has the correct, unqualified wording, matching the house convention used for `cells/rust` (`reports/repo-presenter-regen-full/cells/rust/readme.md:678`) — the only other cells platform without its own commercial SKU. The fix exists locally but has not been re-published; the real defect is still live today.

2. **[MAJOR, systemic]** A confirmed, disclosed functional defect (`upstream-issues.md:5-24`, independently verified at `runs/.clone_cache/aspose_cells_typescript/aspose_cells/workbook.ts:390-429`: `save()` silently writes XLSX bytes for `.csv`/`.json`/`.md`/`.markdown` paths) is never surfaced as an explicit warning in the candidate's `## Scope and Limitations` (readme.md:316-325) or anywhere else in the README — only the safe workaround is shown, with no caution against the naive `save("x.csv")` call a reader might reasonably try by analogy with the documented `save("output.html", …)` pattern. Systemic because nothing in the disposition pipeline appears to force a discovered `FUNCTIONAL-DEFECT` from `upstream-issues.md` into a visible reader-facing warning.

3. **[MAJOR, product-specific with plausible systemic cause]** `reports/repo-presenter-regen-full/cells/typescript/` is missing `last-verified.json` and `code-example-dispositions.json`, both of which exist for sibling products in the same family (`ls reports/repo-presenter-regen-full/cells/net/` and `.../cells/rust/` both list both files). This is plausibly connected to this product's unusual generation path (registry-excluded per `data/registry_exclusions.json` but refreshed under explicit override, per the task's own context note) — a registry-excluded-but-overridden product may take a shortened code path that skips whatever step writes these two files. No `cells/typescript` entry exists in `data/readme_published_state.json` or `reports/repo_presenter_actions.jsonl` either, despite a real push having landed (`fc186507e5b7124f4664aa6035f25cfd3112367d`, confirmed on the real GitHub remote) — the publication is real but has zero record in either publication-tracking file, meaning the same override path also loses ordinary publication logging.

4. **[MINOR, systemic]** `structure-dispositions.json` for this product records only the 2 Quick-Start code snippets and captures none of the substantial original→candidate heading reorganization (`Highlights`→`Key Capabilities`, `Supported Areas` dissolved, `Build from Source`→`Development and Testing`, `Compatibility`→`Dependencies`, `Support`→`Documentation & Resources`, two H3 subheadings dropped) nor the original's third code block (`npm install`/`npx tsc --noEmit` under "Build from Source", preserved into candidate lines 331-334 with zero disposition record anywhere). Cross-checked `reports/repo-presenter-regen-full/3d/net/structure-dispositions.json` (2 bare entries, no heading tracking at all) — the same shallow coverage appears there too, suggesting this is how the system behaves generally, not a one-off for this product.

5. **[MINOR, systemic]** `content-dispositions.json` unit `u0028` ("Node.js 18+") self-labels `verification.status: "verified_against_manifest"` while its own `evidence_note` states "No explicit engines field in package.json" — independently confirmed `package.json` has no `engines` field. The claim is a carried-forward, unverified assertion from the pre-refresh README, mislabeled as manifest-verified. Any dependency claim carried forward without a live manifest field risks the same mislabeling elsewhere.

6. **[INFORMATIONAL, context per task's own request]** `data/registry_exclusions.json`'s `cells/typescript` exclusion (`excluded_at: 2026-07-28`) cites "no LICENSE file" and "a GitLab-boilerplate README (recruitize.ai origin text)" as blocking reasons. Both were already false at the time the exclusion was recorded: `gh api .../commits` shows commit `e68775b64bfc7eb0021dd5d45ed5cc45dd4f94b5` (2026-05-25) replaced the GitLab-boilerplate README (confirmed present as of the immediately preceding commit `391d48024264757add58fa7355a73b5d46b48962` via `gh api .../contents/README.md?ref=391d4802...`) with a real product README, and added `License/LICENSE.txt` in the same commit — over two months before the exclusion was written. Only the third stated reason (non-Aspose package name `"excel-cells"`) still holds today. This doesn't impugn the candidate's quality — if anything it supports that a refresh was reasonable here — but the exclusion record itself is stale and unreconciled.

7. **[NIT]** Candidate line 165, `await workbook.save("output.html", { saveFormat: undefined })`, is functionally correct but a confusing way to introduce the HTML-export path in an illustrative example — passing no options object at all would show the same real behavior more clearly.

8. **[NIT]** Candidate line 336, `[AGENTS.md](agents.md)`, uses uppercase display text against a real lowercase target file; not a broken link, purely cosmetic.

No BLOCKER-severity defects were found: every content-exclusion decision I independently re-verified (page-setup/print, Tables/ListObjects, Document properties) was correct, every dependency and API claim I spot-checked was accurate, and all referenced files/links resolve to real, existing targets.

## Stage B: Source Cross-Check

### Factual Accuracy

- **`Workbook.save()` XLSX-for-non-XLSX defect** — CONFIRMED, independently re-read. `runs/.clone_cache/aspose_cells_typescript/aspose_cells/workbook.ts:390-421`: `save()` computes `format = options?.saveFormat || this.detectFormat(filePath)` (line 394), special-cases only `format === SaveFormat.HTML` (line 396, HTML export branch returns at line 414); every other value — including `CSV`/`JSON`/`MARKDOWN` — falls through to lines 417-421 (`createZipWriter()` → `writeToZip()` → `finalizeZip()` → raw `writeFile`), i.e. the XLSX ZIP path, with no format-specific branch and no error. `detectFormat()` (lines 424-431) does correctly map `.csv`→`CSV`, `.json`→`JSON`, `.md`/`.markdown`→`MARKDOWN`. Candidate's Scope-and-Limitations text (`reports/repo-presenter-regen-full/cells/typescript/readme.md:318-320`) documents only the safe workaround, never states the hazard. Matches Stage A exactly.

- **Live vs. candidate "Enterprise Edition" wording** — CONFIRMED via my own hashing and content read, not trusted from Stage A's table:
  - `gh api repos/aspose-cells-foss/Aspose.Cells-FOSS-for-TypeScript/contents/README.md --jq .content | base64 -d` → line 323 reads `[Aspose.Cells for .NET — Enterprise Edition](https://products.aspose.com/cells/)`.
  - `sha256sum` on that decoded file = `6e92da3a04ae70dadbe600431c38b19f7b16b50af338417fb2e7f2baadd0826c`.
  - `tr -d '\r' < runs/.clone_cache/aspose_cells_typescript/README.md | sha256sum` = same hash `6e92da3a04ae70dadbe600431c38b19f7b16b50af338417fb2e7f2baadd0826c` — clone cache is byte-identical (LF-normalized) to the live published file. Both independently reproduce Stage A's reported value.
  - Candidate (`reports/repo-presenter-regen-full/cells/typescript/readme.md:323`) reads the unqualified `[Aspose.Cells — Enterprise Edition](https://products.aspose.com/cells/), which adds`.
  - `git -C runs/.clone_cache/aspose_cells_typescript show cabbb9d8ba2067854f7cb3dcdc4acfeec849747b:README.md | sha256sum` = `1a2a4cf34bf48db85412a5b25ccc196c38b6fc735cbc308a4941a4219b881aa8` — original-at-generation-time hash, also reproduces Stage A's value.
  - `git -C runs/.clone_cache/aspose_cells_typescript log --oneline -- README.md` → `fc18650 docs: refresh README...` on top of `cabbb9d add agents.md`; `git log -1` on HEAD shows `fc186507e5b7124f4664aa6035f25cfd3112367d`, author `babar.raza@aspose.com`, `Fri Aug 14 19:57:33 2026 +0500`. All CONFIRMED.
  - `grep -rn "Enterprise Edition" reports/repo-presenter-regen-full/cells/` shows `cells/net`, `cells/java`, `cells/python`, `cells/cpp`, `cells/go` all use their own platform name + platform URL, and `cells/rust/readme.md:678` uses the identical unqualified form `[Aspose.Cells — Enterprise Edition](https://products.aspose.com/cells/), which adds`. CONFIRMED — house convention as described.

### Content/Knowledge-Layer Cross-Check (feeds Factual/API/Dependency accuracy)

- **u0014 (page setup/print)** — CONFIRMED false: `grep -rni "pagesetup|printarea|print.setup|printsettings" aspose_cells/ examples/` → exit 1 (zero hits), re-run myself.
- **u0015 (Tables/ListObjects)** — CONFIRMED false: `grep -rni "listobject" aspose_cells/ examples/` → zero hits.
- **u0017 (Document properties)** — CONFIRMED false: `grep -rni "documentproperties|customdocumentproperties|builtindocumentproperties" aspose_cells/ examples/` → zero hits.
- **The "108 real classes/interfaces/enums" figure cited in u0015/u0017's evidence_note** — CONFIRMED by independent count, but via a route Stage A didn't cite: `grep -o '"kind": "[a-z_]*"' knowledge/cells/typescript/merged/api_surface.json | sort | uniq -c` → `class_declaration: 28, enum_declaration: 2, interface_declaration: 53, type_alias_declaration: 25`. Sum = 108, exact match. Note this total only works if "interfaces/enums" is read to include `type_alias_declaration` entries (not stated explicitly in the evidence_note). Separately, the live published reference pages at `content/reference.aspose.org/en/cells/typescript/*.md` number 101 (102 including `_index.md`) — 6-7 fewer than the knowledge-layer figure. Immaterial to the ListObjects/DocumentProperties conclusion (still zero matches either way) but worth flagging as a minor unreconciled inventory discrepancy between `api_surface.json` and the published reference set.
- **u0028 (Node.js 18+) mislabel** — CONFIRMED: `reports/repo-presenter-regen-full/cells/typescript/content-dispositions.json:468-472` — `verification.status: "verified_against_manifest"` while `evidence_note` itself states "No explicit engines field in package.json". My own `grep -n "engines" package.json` → exit 1, no `engines` field. Self-contradictory status label, exactly as Stage A found.
- **u0029 (TypeScript 5+)** — CONFIRMED genuinely verified: `package.json:17` → `"typescript": "^5.9.3"`.
- **Worksheet.shapes / Workbook.images getters** — CONFIRMED: `aspose_cells/worksheet.ts:214-215` (`get shapes(): ShapeInfo[] { return this._shapes; }`); `aspose_cells/workbook.ts:85-86` (`get images(): ImageInfo[] { return this._images; }`).
- **Cell.putValue/setFormula/setStyle** — CONFIRMED at `aspose_cells/cell.ts:50,63,76` exactly (`putValue(value: CellValue)`, `setFormula(formula: string)`, `setStyle(style: Style)`).
- **Style.setBold/setFontColor/setForegroundColor** — CONFIRMED at `aspose_cells/style.ts:79,115,124` exactly.
- **Workbook.load() signature** — CONFIRMED: `aspose_cells/workbook.ts:52` → `static async load(filePath: string, password?: string): Promise<Workbook>`.
- **WorksheetCollection.get(index)** — CONFIRMED: `aspose_cells/worksheetCollection.ts:40` → `get(index: number): Worksheet | undefined`.
- **Worksheet.putValue(key, value): Cell** — CONFIRMED: `aspose_cells/worksheet.ts:82` → `putValue(key: string, value: CellValue): Cell`.
- **`getCell2`** used in both Quick Start snippets (s0001/s0002) but not explicitly flagged by Stage A — CONFIRMED real: `aspose_cells/worksheet.ts:74` → `getCell2(key: string): Cell`, with regex validation and a thrown error for invalid refs (lines 75-79).
- **badge-dispositions.json = `[]`** — CONFIRMED, `wc -c` = 3 bytes, content `[]`.
- **Banner asset** — CONFIRMED: `static/media/cells/typescript/banner-readme.png`, 312,018 bytes.
- **structure-dispositions.json scope (2 entries only, both Quick Start)** and **3d/net's parallel file having no heading field** — CONFIRMED by direct read of both files: typescript's file has exactly `s0001`/`s0002` with `heading`/`kind` fields; `3d/net/structure-dispositions.json` has exactly 2 entries with only `unit_id`/`disposition`/`target_section`/`verification`, no `heading` key anywhere.
- **Untracked third code block** (`npm install` / `npx tsc --noEmit`) — CONFIRMED preserved at candidate lines 331-334 exactly, sourced from original `README.md:100-103` under `## Build from Source`; no disposition unit covers it (content-dispositions.json's u0027 covers only the adjoining prose sentence at original line 98).
- **Heading reorganization table** — CONFIRMED by my own `grep -n "^#"` on both the original (`cabbb9d` blob) and candidate: original has `Highlights, Installation, Quick Start (+2 H3s), Supported Areas, Build from Source, Compatibility, License, Support`; candidate has `Navigation, At a Glance, Key Capabilities, Installation, Dependencies (+3 H3s), Quick Start, Additional Examples (+H3), API Reference (+H3), Documentation & Resources, Scope and Limitations, Development and Testing, License` — matches Stage A's mapping.
- **Publication-tracking gap** — CONFIRMED: `grep -n '"cells' data/readme_published_state.json` shows entries for `cells/go`, `cells/java`, `cells/net` only — no `cells/typescript` row. `grep -n '"cells' reports/repo_presenter_actions.jsonl` shows one `cells/rust` dry-run event, no `cells/typescript` entry at all, despite the real push `fc186507e5b7124f4664aa6035f25cfd3112367d`.
- **Registry exclusion record** — CONFIRMED verbatim at `data/registry_exclusions.json:10-17` (family `cells`, platform `typescript`, `excluded_at: "2026-07-28"`, citing no-LICENSE + GitLab-boilerplate + non-Aspose package name).

### Dependency Accuracy

All read directly from `runs/.clone_cache/aspose_cells_typescript/package.json` (full file, 20 lines):
- `@zip.js/zip.js: ^2.8.21`, `@xmldom/xmldom: ^0.8.10`, `adm-zip: ^0.5.16` (dependencies, lines 9-11) — CONFIRMED exact match to candidate lines 96-98.
- `@types/node: ^25.3.3`, `ts-node: ^10.9.2`, `tsx: ^4.21.0`, `typescript: ^5.9.3` (devDependencies, lines 14-17) — CONFIRMED exact match to candidate lines 106-107.
- No `engines` field anywhere in the file — CONFIRMED (`grep -n "engines" package.json` → no output, exit 1).
- `"name": "excel-cells"` (line 2) — CONFIRMED, matches `upstream-issues.md`'s informational note.
- **New cross-check not in Stage A's Dependency Accuracy section**: `data/package_registry.json` (family `cells` → platform `typescript`, lines 127-146) records `registry_type: "npm"`, `candidate.name: "excel-cells"`, `verification.published: false`, `verified_owner: null`, `evidence_note: "Backfilled 2026-08-01: no live match found for any tried candidate (excel-cells, @asposefoss/cells); recorded as not-yet-published..."`. This directly and accurately backs the candidate's own Installation-section line (`readme.md:84`): *"A npm package has not been published yet. Install from source:"* — CONFIRMED accurate, and consistent with `upstream-issues.md`'s own citation of this same registry file.

### API Accuracy

- **`SaveFormat` enum, 5 members** — CONFIRMED: `aspose_cells/types.ts:177-183` → `XLSX, CSV, JSON, MARKDOWN, HTML` (5 exactly).
- **`EncryptionType` enum, 1 member** — CONFIRMED: `aspose_cells/types.ts:185-187` → `AES` only.
- All other API-signature claims cross-checked above (Cell/Style/Worksheet/Workbook methods) are CONFIRMED with my own line citations, matching Stage A's conclusions.

### Unflagged finding: knowledge-layer internal contradiction on CSV/JSON/MARKDOWN export (strengthens Verdict #2)

Independently discovered, not raised by Stage A. `knowledge/cells/typescript/merged/claims.json` (raw scout output, confidence 1.0) contains claims `CLM-cells-ac97eb` / `CLM-cells-63dbab` / `CLM-cells-18fbe2` (~lines 10642-10683): *"export support for CSV via SaveFormat"*, *"...JSON via SaveFormat"*, *"...MARKDOWN via SaveFormat"*, each sourced only from the enum declaration at `types.ts:177` — i.e. inferred purely from the enum member existing, never from checking `save()`'s dispatch logic. Given the confirmed defect above, these three claims are literally false as worded (SaveFormat.CSV/JSON/MARKDOWN exist but produce XLSX bytes when passed to `save()`).

However, the later-stage promoted artifact `knowledge/cells/typescript/merged/formats.json` gets this right: `XLSX`/`CSV`/`JSON`/`MARKDOWN` entries are all tagged `"direction": "enum_only", "functional": false`, and only `HTML` is tagged `"direction": "export", "functional": true` — and `formats.md`'s rendered table shows `CSV | - | -`, `JSON | - | -`, `MARKDOWN | - | -`, `HTML | Yes | Yes`. So the pipeline's own knowledge layer already computed the correct, defect-aware answer in `formats.json`/`formats.md`, but a stale, overclaiming, contradictory claim survives uncorrected in `claims.json`. Neither artifact's signal made it into an explicit README warning — this gives Stage A's systemic finding #2 a concrete root-cause locus (a formats.json↔claims.json reconciliation gap) rather than just "nothing forces it into a warning."

### Bonus verification (Verdict #6, outside the three required sections but fast to check with `gh api`)

CONFIRMED independently: `gh api .../contents/README.md?ref=391d48024264757add58fa7355a73b5d46b48962` decodes to GitLab's literal boilerplate template ("## Getting started / To make it easy for you to get started with GitLab..."). `gh api .../commits/e68775b64bfc7eb0021dd5d45ed5cc45dd4f94b5` → message `"update readme, licensse"`, date `2026-05-25T03:34:47Z`, `.files[].filename` → exactly `License/LICENSE.txt` and `README.md`. Matches Stage A's finding #6 exactly — the exclusion record's cited blocking reasons (no LICENSE, GitLab boilerplate) were already false as of 2026-05-25, over two months before the 2026-07-28 exclusion was recorded.

### Net assessment

Every claim in Stage A's Factual Accuracy, Dependency Accuracy, and API Accuracy sections is CONFIRMED against my own independent reads/commands/hashes — no REFUTED or UNVERIFIABLE findings among them. No new BLOCKER or MAJOR-severity defects surfaced. One new MINOR/INFORMATIONAL nuance found: a `claims.json` vs `formats.json` internal contradiction on CSV/JSON/MARKDOWN export support that sharpens (but does not change the severity of) Stage A's Verdict finding #2, plus a minor unreconciled count (108 in `api_surface.json` vs. 101 published reference pages) that doesn't change any exclusion conclusion.

## Stage C: Adversarial Verification

1. **[MAJOR] Live README ".NET" mislabel, candidate already fixed but unpublished** — CONFIRMED (facts), severity **DOWNGRADED to MINOR**. I independently reproduced every cited artifact: `gh api .../contents/README.md` → decoded file hashes to `6e92da3a04ae70dadbe600431c38b19f7b16b50af338417fb2e7f2baadd0826c` exactly, matches CRLF-stripped clone-cache hash exactly; candidate `readme.md` hashes to `a8af6b3ecf...` (as-read) and `d9ad00aac3...` (LF-normalized) exactly as claimed; `git log --oneline -- README.md` reproduces `fc18650`/`cabbb9d` exactly; `gh api commits/fc186507...` confirms author `babar.raza@aspose.com`, date `2026-08-14T14:57:33Z` (=19:57:33+0500, consistent with local git log), and the exact commit message including `Co-Authored-By: Claude Sonnet 5`; `cells/rust/readme.md:678` uses the identical unqualified wording; the family-wide grep result is reproduced verbatim. Every underlying fact checks out. However, tagging this at the same MAJOR tier as an actual silent-data-corruption bug (#2) is a stretch — this is a cosmetic commercial-upsell-link label mismatch (URL still resolves to a legitimate, related product page), not a functional or safety defect. Internally the review itself reserves MAJOR for genuine functional risk (#2) and MINOR/INFORMATIONAL for internal-artifact issues (#4–#6); a live-but-cosmetic public string is more consistent with MINOR under that same scheme.

2. **[MAJOR] Undisclosed `save()` XLSX-for-non-XLSX corruption hazard** — CONFIRMED, severity appropriate. Re-read `workbook.ts:390-431` directly: `save()` branches only on `format === SaveFormat.HTML` (line 396); every other value, including the correctly-detected `CSV`/`JSON`/`MARKDOWN` from `detectFormat()` (lines 424-431), falls through to the ZIP-write path (lines 417-421) with no error. Confirmed the candidate's entire README (`grep -n "csv|CSV"`) contains exactly the two cited CSV mentions, neither of which warns against `save("x.csv")`; the API Reference table (`line 305`) states "`SaveFormat` | Enum with 5 members" with zero caveat about which are functional in `save()`. This makes the trap slightly worse than Stage A/B stated, not weaker — MAJOR is correctly calibrated, not overstated.

3. **[MAJOR] Missing `last-verified.json`/`code-example-dispositions.json` + zero publish-tracking entries despite real push** — CONFIRMED. Directly listed `cells/typescript/` (5 files, missing both) vs. `cells/net/` and `cells/rust/` (both present in each). Grepped `data/readme_published_state.json` for "typescript" → only a `3d`/`typescript` row exists, zero `cells`/`typescript` row. Grepped `reports/repo_presenter_actions.jsonl` for "typescript" → zero matches at all (not even the cited `cells/rust` dry-run row mentions typescript, confirming no cross-contamination). A real, verified push (`fc186507`, confirmed live on GitHub) with zero entries in either tracking file is a genuine governance/audit-trail gap in a repo whose own CLAUDE.md is built around mandatory skill-run/publish records — MAJOR is justified, and the "plausible systemic cause" framing is appropriately hedged rather than asserted as proven.

4. **[MINOR, systemic] Structure-dispositions.json shallow coverage (heading reorg + 3rd code block untracked)** — CONFIRMED core facts, **"systemic" tag DOWNGRADED**. Verified `structure-dispositions.json` has exactly `s0001`/`s0002` (both Quick Start); verified original headings via `git show cabbb9d:README.md | grep "^#"` and candidate headings via direct grep — the full reorg table (Highlights→Key Capabilities, Supported Areas dissolved, Build from Source→Development and Testing, Compatibility→Dependencies, Support→Documentation & Resources, 2 H3s dropped) reproduces exactly. Verified the original's third code block (`npm install`/`npx tsc --noEmit` under `## Build from Source`) survives verbatim into candidate lines 331-334, and `content-dispositions.json` u0027 covers only the adjoining prose sentence, not the code block. But expanding the cross-check beyond the single cited comparator (`3d/net`): `cells/net/structure-dispositions.json` (4/4 entries), `cells/rust/structure-dispositions.json` (6/6 entries), and `pdf/java/structure-dispositions.json` (7/7 entries) **all carry a `heading` field on every entry** — directly contradicting "no heading tracking at all... appears to be the system's general behavior." Schema richness actually varies significantly per product (3d/net: fully bare; cells/net: heading+classification; cells/typescript: heading+excerpt+kind) — this is product/run-variable, not a uniform systemic gap, so the "systemic" generalization drawn from n=1 doesn't hold once sampled further. (Note: even cells/net's heading fields only label individual code-example headings, not a document-level H2 reorg map, so the underlying substantive complaint — nothing tracks the H2-level restructuring — plausibly still holds; it's specifically the inductive leap to "general behavior" from one comparator that's unsupported.)

5. **[MINOR, systemic] u0028 self-contradictory `verified_against_manifest` label** — CONFIRMED core defect; "systemic" framing **UNCONFIRMED** as a real second occurrence. Read `content-dispositions.json:462-477` directly: `verification.status: "verified_against_manifest"` while `evidence_note` states verbatim "No explicit engines field in package.json" — exact match to the citation. Confirmed `package.json` has no `engines` field (`grep -n "engines"` → exit 1). This is a genuine self-contradiction, MINOR severity is fair (it's an internal-artifact mislabel, doesn't corrupt the README's own text). However, I spot-checked two other products carrying the same status (`cells/go`, `pdf/go` `content-dispositions.json`) and found their `verified_against_manifest` entries have no `evidence_note` field at all — i.e., no matching self-contradiction pattern found elsewhere in this quick sample. The "systemic" tag is really a forward-looking risk statement ("any claim carried forward... risks the same mislabeling elsewhere"), not a demonstrated recurrence — reasonable as phrased, but should not be read as already-observed-elsewhere.

6. **[INFORMATIONAL] Stale registry-exclusion reasons** — CONFIRMED exactly. `gh api commits/e68775b64bfc...` reproduces the exact date (`2026-05-25T03:34:47Z`), exact message (`"update readme, licensse"`), and exact file list (`License/LICENSE.txt`, `README.md`). `gh api contents/README.md?ref=391d4802...` decodes to the literal GitLab boilerplate ("gitlab.recruitize.ai/gulou-cells/shijiewang/..."), confirming the pre-fix state. `data/registry_exclusions.json:13-17` reproduces verbatim (`excluded_at: "2026-07-28"`, same three cited reasons). Two of three reasons are confirmably false as of over two months before the exclusion date; only the package-name reason still holds. INFORMATIONAL is the right tier — doesn't affect candidate quality, purely a stale governance record.

7. **[NIT] `save("output.html", { saveFormat: undefined })` confusing example** — CONFIRMED. Verified candidate line 165 verbatim, and traced the logic in `workbook.ts:394` (`options?.saveFormat || this.detectFormat(filePath)`) — `undefined || detectFormat("output.html")` correctly resolves to `SaveFormat.HTML`. Functionally correct, genuinely just an odd way to write a first example. NIT is correctly calibrated, not a real bug.

8. **[NIT] `agents.md` link case mismatch** — CONFIRMED. `ls -la` on the clone cache shows the real file is lowercase `agents.md`; candidate line 336 link target `(agents.md)` matches exactly (only the display text `[AGENTS.md]` is uppercase). Purely cosmetic, correctly tagged NIT, not a broken link on any filesystem since the target string matches the real path exactly.

**Summary**: 6 of 8 findings CONFIRMED outright with severity/tag as given (2, 3, 6, 7, 8, plus 5's core defect). Finding 1's facts are fully reproduced but its MAJOR severity is arguably inflated relative to a genuinely functional MAJOR (#2) — DOWNGRADED to MINOR on calibration grounds. Finding 4's specific facts hold but its "systemic" generalization is contradicted by a 3-product expanded sample (cells/net, cells/rust, pdf/java all track per-entry headings unlike the sole cited comparator 3d/net) — DOWNGRADED on the systemic tag specifically. Finding 5's "systemic" framing is an unverified forward-looking risk rather than an observed second occurrence in my own 2-product spot check — flagged but not downgraded, since the finding's own wording already hedges as risk rather than fact. No finding was UNCONFIRMED outright or UPGRADED in severity.