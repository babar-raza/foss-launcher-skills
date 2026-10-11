## Identity

Four artifact classes examined, all four obtained:

- **Original-at-generation-time README**: recovered via `git -C runs/.clone_cache/aspose_words_net show 572fc74:README.md` (commit `572fc748b45fe5efce5d93d0684c5ac78fc8affe`, "Import Aspose.Words FOSS build"). This is the pre-refresh README the disposition ledgers describe transforming. Saved locally at `/tmp/orig_readme.txt` for citation purposes (110 lines).
- **Current live upstream README**: `runs/.clone_cache/aspose_words_net/README.md` exists (71,760 bytes, CRLF on disk). Clone-cache HEAD is `68d56fdaf7fcd2d95935a0c180b6e69e99a9b4b8` ("docs: refresh README with verified content, dependencies, and diagram fixes", authored by Babar Raza, 2026-08-17T10:11:33+05:00). `git -C runs/.clone_cache/aspose_words_net log --oneline -- README.md` → `68d56fd` then `572fc74` (exactly two commits touch README.md ever).
- **Candidate**: `reports/repo-presenter-regen-full/words/net/readme.md` (931 lines, 71,760 bytes).
- **Published**: confirmed real (non-dry-run) via `gh api repos/aspose-words-foss/Aspose.Words-FOSS-for-.NET/commits/master` → sha `68d56fdaf7fcd2d95935a0c180b6e69e99a9b4b8`, matching clone-cache HEAD exactly, `pushed_at: 2026-08-17T05:11:36Z`. Fetched the live blob via `gh api repos/aspose-words-foss/Aspose.Words-FOSS-for-.NET/contents/README.md --jq .content | base64 -d`.

**Hash reconciliation** (all four are the same content):
- `sha256sum reports/repo-presenter-regen-full/words/net/readme.md runs/.clone_cache/aspose_words_net/README.md` → both `0d2348a5b4d711182c5c6b678ea0e26e1091dc0b0ee738f80102e0b8829c3d4b` (raw bytes, CRLF-checkout form). `diff` of the two files → empty (identical).
- Live GitHub blob, LF-normalized (`tr -d '\r'`) → sha256 `013cd7ccd77e3204060686a0453fc35e6a9e34f950443d1aa1c442b7373bf735`, which is **exactly** the `readme_sha256` recorded in `last-verified.json` line 2. `diff` of LF-normalized live vs. LF-normalized clone-cache vs. LF-normalized candidate → all three empty (identical). This confirms `last-verified.json`'s hash is computed over LF-normalized content (consistent with the documented CRLF-normalization fix referenced in repo history), not a discrepancy.
- **Conclusion**: candidate = current live upstream README = actually-published GitHub content, byte-for-byte. This run is a re-verification pass over content already shipped, not a pending change.
- `data/readme_published_state.json` line 15 corroborates: `{"family":"words","platform":"net","last_known_publication":"2026-08-18", "evidence":"MT056 reconciliation: canonical candidate byte-identical (stripped) to clone-cache upstream README..."}`. `reports/repo_presenter_actions.jsonl` has **no** `words/net` entry at all (only `note/python` and `cells/rust`) — the publication record for this product rests entirely on content-match reconciliation, not on a logged push event, because the actual push (`68d56fd`) was made as a direct git commit rather than through the pipeline's `_do_push` action.

## Factual Accuracy

Spot-checked prose claims directly against clone-cache source (not the disposition JSON's own self-report):
- "617 public types" (readme.md lines 893, 901) — matches `knowledge/words/net/merged/model.yaml` `stats.class_count: 617` exactly, and matches manual visual scan of the Core API/Interfaces/Enumerations tables.
- Target frameworks "net462;netstandard2.0;net8.0" (readme.md line 103, 91) — confirmed verbatim in `Aspose.Words/Aspose.Words.csproj`: `<TargetFrameworks>net462;netstandard2.0;net8.0</TargetFrameworks>`.
- Format support table (readme.md lines 908–910) cross-checked against `knowledge/words/net/merged/formats.md`: DOCX/DOCM/DOTX/DOTM Yes/Yes, FLATOPC* Yes/Yes, MARKDOWN Yes/Yes, TEXT/TXT Yes/Yes; DOC/RTF/HTML/EPUB/ODT all `-`/`-`. Matches the README's positive and negative format claims exactly.
- NuGet package publication claim (`dotnet add package Aspose.Words.FOSS`, readme.md line 80) — live-verified via `api.nuget.org` catalog: package `Aspose.Words.FOSS` v26.2.0, published, MIT license, author Aspose. Matches, and correctly sidesteps the stale "coming very soon" text still present in the upstream repo's own root README/AGENTS.md at the time of the pre-refresh original (this is already disclosed in `upstream-issues.md` lines 13–17).
- See **Example Verification** and **API Accuracy** below for two factual defects found by direct source inspection that the disposition ledger's own verification claims missed.

## Content-Preservation Ledger

Original units taken from `/tmp/orig_readme.txt` (git blob `572fc74:README.md`); disposition verified by reading the candidate myself, not by trusting `content-dispositions.json`'s self-report.

| Original unit | Line(s) in original | Disposition | Notes |
|---|---|---|---|
| Title `# Aspose.Words FOSS for .NET` | 1 | PRESERVED | Unchanged |
| Intro one-liner | 3 | TRANSFORMED | Expanded into candidate u0002 (readme.md line 11); format list DOCX→DOCX/DOCM/DOTX/DOTM, accurate per formats.md |
| License-only badge | 5 | PRESERVED (merged into badge row) | Now one of four badges, readme.md line 3 |
| `## What it can do` heading | 7 | TRANSFORMED (renamed) | → `## Key Capabilities`; **not tracked** in structure-dispositions.json |
| Bullet: create-from-scratch | 8 | TRANSFORMED | readme.md line 65, same substance |
| Bullet: read/edit DOCX (incl. **shapes**) | 9–10 | **PARTIALLY DROPPED-SILENTLY** | readme.md line 66 keeps text/styles/tables/lists/sections/headers/footers/bookmarks/comments/footnotes but drops "shapes" from the enumeration with no disposition entry disclosing the removal; `Shape` remains listed in the API table (line 531) so the class isn't erased, only the narrative claim is |
| Bullet: convert formats | 11 | TRANSFORMED (expanded) | readme.md line 67 adds Flat OPC, verified accurate |
| Bullet: combine/reorganize | 12 | PRESERVED/TRANSFORMED | readme.md line 68 |
| Bullet: find/replace | 13 | PRESERVED/TRANSFORMED | readme.md line 69 |
| Bullet: tracked changes | 14 | MERGED | Combined with next bullet into readme.md line 70 |
| Bullet: update fields | 15 | MERGED | Merged into readme.md line 70 (same bullet as tracked changes) — content correctly preserved |
| Bullet: protect/round-trip DOCM/DOTM | 16 | PRESERVED | readme.md line 71 |
| Bullet: digital signatures incl. **"or remove signatures"** | 17 | **DROPPED-SILENTLY (real capability)** | readme.md line 72 keeps verify/inspect + "creating new signatures is not included" but drops "or remove signatures." `DigitalSignatureUtil.RemoveAllSignatures(...)` is a real, functional public API (`Aspose.Words/Model/DigitalSignatures/DigitalSignatureUtil.cs:197,223`) supporting Docx/Dotx/Docm/Dotm (the exact formats this edition ships) — see Verdict |
| Three-target paragraph (GDI+/SkiaSharp) | 19 | TRANSFORMED/MERGED | Expanded into full `## Dependencies` section (readme.md lines 93–111) — good enhancement |
| `## Supported formats` table | 21–29 | TRANSFORMED (table→prose) | Info preserved via Intro + Key Capabilities bullets; no distinct disposition unit ever existed for this table (structure-dispositions.json doesn't track it) |
| `## Getting started` heading + NuGet/build-from-source | 32–50 | TRANSFORMED/MERGED | → `## Installation` (readme.md lines 75–91), content preserved and expanded |
| `### A quick example` | 52–74 | TRANSFORMED | → `## Quick Start` + `## Additional Examples`, split into two examples plus 3 more (Merge, Convert MD, Chart) |
| `## What's not included...` | 76–86 | TRANSFORMED (renamed) | → `## Scope and Limitations` (readme.md lines 906–913), content preserved faithfully |
| `## The story behind this code` (incl. Full2Foss/Claude-tooling detail) | 88–96 | TRANSFORMED (compressed) | → `### Project History` (readme.md lines 7–9); the "Full2Foss agent built with Claude" implementation-tooling anecdote is dropped — editorially defensible (not a factual/capability claim), but undisclosed in any ledger |
| **`## Enjoying it? Star it ⭐`** (Star/Watch/Tell-someone CTA) | 98–104 | **DROPPED-SILENTLY (whole section)** | No trace anywhere in candidate (`grep -i "star it\|watch.*releases\|tell someone"` on readme.md → no matches). No disposition entry of any kind exists for this heading in `structure-dispositions.json` (only 3 entries total, all *new* headings, none mapping this original section's fate) |
| `## Contributing` | 106–108 | MERGED | Folded into `## Documentation & Resources` bullet (readme.md line 904, "Found a bug...open an issue...pull requests are welcome") |
| `## License` | 110 | PRESERVED | readme.md lines 928–931 |

**Systemic ledger-completeness gap**: `structure-dispositions.json` contains only 3 entries (`s0001` At a Glance, `s0002` Merge Two Documents, `s0003` Convert Markdown to DOCX) — all describe *new* headings added in the candidate. It contains **zero** entries for any of the original's 8 top-level headings, so it cannot answer "what happened to `## Enjoying it? Star it`" or any other original heading by itself — that required independently diffing git history. This is a structural gap in the disposition machinery's own scope, not specific to this product.

**Ledger-content gap**: every `content-dispositions.json` excerpt (all 97 units, verified via `grep -c '"unit_id"'` = 97) contains the **candidate's** final text, not the **original's** text, despite the audit brief's expectation that these files "may embed excerpts of the ORIGINAL README content used at generation time." No unit anywhere quotes original wording being replaced. This makes the ledger unusable on its own for verifying preservation — the only way to do so is external git diffing, which this audit performed.

`content-dispositions.json`/`code-example-dispositions.json`/`badge-dispositions.json` show **zero** `dropped_*` or `incorrectly_excluded` dispositions (all 97 content units are `merged_verbatim`/`merged_reframed`; all 10 code units and 4 badge units `merged_verbatim`/`preserved`) — this 100%-preserved self-report is contradicted by the two silent drops documented above, which the ledger simply never surfaces because it never encodes original text to diff against.

## Usability

Structure is a clear improvement over the original: Navigation TOC, At-a-Glance mermaid diagram, progressive disclosure (`<details>` for the full API table and extra examples) make the README substantially easier to scan than the original's flat list. Installation, Dependencies, Quick Start, Scope and Limitations are all well-separated and logically ordered. No usability defects found.

## Presentation/SEO

Badges row (readme.md line 3) and banner image (line 5) render at the top per standard GitHub README convention. `badge-dispositions.json`'s `b0002` unit is recorded with `"category": "unknown"` (line 17) — cosmetic ledger-metadata gap only (the ".NET Standard" badge simply wasn't classified into a known category bucket); no user-facing effect. No other presentation issues found.

## Dependency Accuracy

Cross-checked every dependency claim in readme.md lines 97–111 against the actual `.csproj` files:
- SkiaSharp 3.119.0, BitMiracle.LibTiff.NET 2.4.649, Microsoft.Win32.Registry 5.0.0 — all confirmed exactly via `grep -n PackageReference Aspose.Foundation/Aspose.Foundation/Aspose.Foundation.csproj` (lines 80, 82, 86).
- Test-only deps (Microsoft.NET.Test.Sdk 17.13.0, NUnit 4.2.2, NUnit3TestAdapter 5.0.0, Newtonsoft.Json 13.0.3) — all confirmed exactly via `Aspose.Words.Tests/Aspose.Words.Tests.csproj` lines 72–75.
- **Gap found**: `Aspose.Foundation/Aspose.Foundation/Aspose.Foundation.csproj` line 81 also has an unconditional `<PackageReference Include="System.Text.Encoding.CodePages" Version="7.0.0" />` under the identical `Condition="'$(TargetFramework)' != 'net462'"` block as SkiaSharp and BitMiracle.LibTiff.NET (lines 79–83). readme.md's Dependencies section (line 91: "see Dependencies below for the full required-package and native-requirement breakdown") omits this package entirely. However, live-checking the actually-published NuGet package (`curl https://api.nuget.org/v3/catalog0/data/2026.07.29.18.11.09/aspose.words.foss.26.2.0.json`, `grep -o '"id": "[^"]*"'`) shows the real v26.2.0 dependency graph across all three target-framework groups lists only `SkiaSharp`, `BitMiracle.LibTiff.NET`, `Microsoft.Win32.Registry` — `System.Text.Encoding.CodePages` is genuinely absent from the shipped package's own dependency metadata, so end users of the current published package are unaffected. This affects only someone reading the `.csproj` directly (a contributor), and is the same class of "source vs. what's actually shipped" gap already disclosed for other findings in `upstream-issues.md`.
- The already-disclosed items in `upstream-issues.md` (unbuildable-from-clean-clone via `Aspose.EnumExtensionsGenerator`, stale "coming very soon" text elsewhere in the repo, stale `data/package_registry.json.published:false`, "no native dependencies" framing vs. SkiaSharp's native assets) were independently re-verified and hold up: `Aspose.Words/Aspose.Words.csproj` line 100 and `Aspose.Foundation.csproj` line 92 both do carry the `Aspose.EnumExtensionsGenerator 1.0.2` reference; `api.nuget.org` flatcontainer for `aspose.enumextensionsgenerator` was not re-fetched in this pass but the `.csproj` evidence is self-sufficient.

## Example Verification

Code-example-dispositions.json claims all 10 code units `verified_against_source`. Independently re-verified against actual source, and found one **broken example**:

- readme.md lines 183–198, "Additional Examples → Read and Adjust an Embedded Chart's Data Labels": line 187, `Chart chart = doc.FirstSection.Body.Shapes[0].Chart;` — **`Body` has no `Shapes` member of any kind.** Confirmed via `knowledge/words/net/merged/api_surface.md` lines 273–327 (the complete extracted public surface of `Body`: methods include `DeleteShapes()` but no `Shapes` getter; properties list `Paragraphs`, `Tables`, `FirstChild`/`LastChild`/etc., no `Shapes`) and via `grep -rn "public.*Shapes\b" Aspose.Words/Model/` returning only unrelated members (`IgnoreShapes`, `DeleteHeaderFooterShapes`, `DeleteShapes`). A real scouted test snippet for the same feature (`knowledge/words/net/merged/snippets/snippet_010.cs`, lines 5–7) obtains the chart-bearing shape correctly as `Shape shape = builder.InsertChart(...); Chart chart = shape.Chart;` — i.e. the real access pattern never goes through `Body.Shapes`. Since indexer syntax (`Shapes[0]`) cannot be an extension member in C# under any language version, there is no way this line compiles. Any user copying this example verbatim gets a compile error (`CS1061`).
  - This directly contradicts `upstream-issues.md` line 34's claim: "every class, method, and property referenced in the Quick Start, Additional Examples, and Detailed Member Reference sections was cross-checked against `knowledge/words/net/merged/api_surface.md`... and confirmed to exist with matching signatures" — that cross-check did not actually catch this member.
- All other code snippets checked (Quick Start `Document`/`DocumentBuilder`/`Save`/`GetText`; `AcceptAllRevisions`; `AppendDocument`; loading Markdown via `Document(fileName)`; `chart.Series[0]`, `series.HasDataLabels`, `series.DataLabels.ShowValue`, `series.DataLabels[1]`, `label.ShowCategoryName`, `label.Position = ChartDataLabelPosition.Below`) verified present with matching signatures in `Chart.cs:32`, `ChartSeries.cs:514,531`, `ChartDataLabel.cs:534,592`, `ChartDataLabelCollection.cs:69`.

## API Accuracy

- `617 public types` claim (readme.md lines 893, 901) matches `model.yaml`'s `stats.class_count: 617` exactly.
- Spot-checked ~15 class/interface/enum one-line descriptions in the Core API / Interfaces / Enumerations tables (readme.md lines 213–839) against actual XML-doc summaries in source (e.g. `DigitalSignatureUtil` → "Provides methods for signing document." verified verbatim in `DigitalSignatureUtil.cs:18`); all matched verbatim — these are lifted directly from source doc comments, not paraphrased.
- `Shape.Chart` property (`Shape.cs:1551`), `ChartSeriesCollection this[int]` pattern consistent with confirmed `ChartDataLabelCollection.this[int]` (`ChartDataLabelCollection.cs:69`) — real.
- The one API-accuracy defect is the fabricated `Body.Shapes` member documented under Example Verification above — filed there rather than duplicated.

## Link/Rendering

- Internal cross-site links: `content/docs.aspose.org/en/words/net/` exists (`_index.md`, `developer-guide/`, `getting-started/`); `content/kb.aspose.org/en/words/net/` exists (`_index.md`, `faq.md`, several how-to pages); `content/reference.aspose.org/en/words/net/` exists (`_index.md` plus per-class pages, e.g. `AbsolutePositionTab.md`). All three URLs referenced in readme.md's "Documentation & Resources" section (lines 899–901) resolve to real local content.
- Banner image `https://products.aspose.org/media/words/net/banner-readme.png` (readme.md line 5) — confirmed present at `static/media/words/net/banner-readme.png`.
- `AGENTS.md` link (readme.md lines 144, 902) — confirmed present in the clone cache root (`ls runs/.clone_cache/aspose_words_net/` → `AGENTS.md`).
- GitHub issues links use absolute `https://github.com/aspose-words-foss/Aspose.Words-FOSS-for-.NET/issues` (readme.md lines 904, 911) — repo confirmed to exist and be reachable via `gh api repos/aspose-words-foss/Aspose.Words-FOSS-for-.NET`.
- No broken or malformed links found in this pass.

## Verdict

**BLOCKER — product-specific, but the verification-methodology gap that let it through is potentially systemic.**
Broken code example already live on GitHub: `doc.FirstSection.Body.Shapes[0].Chart` (candidate/live readme.md line 187) references a `Shapes` member that does not exist on `Body`.
Evidence: `knowledge/words/net/merged/api_surface.md` lines 273–327 (complete `Body` surface, no `Shapes`); `grep -rn "public.*Shapes\b" runs/.clone_cache/aspose_words_net/Aspose.Words/Model/` → only `IgnoreShapes`/`DeleteHeaderFooterShapes`/`DeleteShapes` match, no `Shapes` getter anywhere in the codebase; real equivalent snippet `knowledge/words/net/merged/snippets/snippet_010.cs` lines 5–7 obtains the chart via `Shape shape = builder.InsertChart(...); Chart chart = shape.Chart;` instead. Contradicts `upstream-issues.md` line 34's claim that every referenced member was "cross-checked against `knowledge/words/net/merged/api_surface.md`... and confirmed to exist." Because this content is already published (confirmed live via `gh api .../contents/README.md`), any user who copies this example today gets a `CS1061` compile error.

**MAJOR — product-specific.**
Silent drop of a real, verified capability from the Key Capabilities digital-signatures bullet: the original README's "...or remove signatures" (git-blob `572fc74:README.md` line 17) is absent from the candidate/live bullet (readme.md line 72), with no disposition record acknowledging the removal. `DigitalSignatureUtil.RemoveAllSignatures(string,string)` is a real, non-stub public API (`Aspose.Words/Model/DigitalSignatures/DigitalSignatureUtil.cs` lines 197–206) supporting Docx/Dotx/Docm/Dotm — exactly the formats this FOSS edition ships. `content-dispositions.json` unit `u0021` (line 243) reports this bullet as `merged_verbatim`/`verified_against_source` with no mention of the dropped capability.

**MAJOR — systemic (affects every product's disposition ledgers, not just this one).**
`structure-dispositions.json`'s schema only records *new* headings introduced in the candidate (3 entries here, all new). It contains no record at all of what happened to any of the original README's 8 top-level headings — including one, `## Enjoying it? Star it ⭐` (original lines 98–104), that is dropped from the candidate in its entirety with zero disposition trail. Confirmed absent via `grep -i "star it\|watch.*releases\|tell someone" reports/repo-presenter-regen-full/words/net/readme.md` → no matches. This means the "structure-dispositions" ledger cannot, by itself, answer "was any heading dropped and why" for any product — an auditor must independently diff git history to find out, as this audit did.

**MINOR — systemic (affects every product's disposition ledgers).**
`content-dispositions.json`'s `excerpt` field is populated with the *candidate's* resulting text, not the *original's* pre-refresh text, for all 97 units (`grep -c '"unit_id"' content-dispositions.json` = 97, all confirmed candidate-verbatim by cross-reading readme.md). This contradicts the reasonable expectation (and this audit brief's own framing) that the ledger preserves original-content excerpts for traceability, and combined with the 100%-`merged_verbatim` self-report, makes the ledger self-certify perfect preservation in a way that cannot be checked without external git diffing.

**MINOR — product-specific.**
Silent drop of "shapes" from the structural-content Key Capabilities bullet: original (`572fc74:README.md` line 10) lists "...bookmarks, comments, footnotes, shapes"; candidate (readme.md line 66) lists "...bookmarks, comments, and footnotes" only. The `Shape` class itself remains listed in the full API table (line 531), so this is a narrative omission rather than a capability erasure.

**MINOR — product-specific, methodology gap possibly systemic.**
`System.Text.Encoding.CodePages` 7.0.0 (`Aspose.Foundation/Aspose.Foundation/Aspose.Foundation.csproj` line 81, same unconditional scope as the two dependencies that *are* listed) is omitted from the README's Dependencies section, which explicitly claims to be "the full required-package and native-requirement breakdown" (readme.md line 91). Live NuGet catalog check (`api.nuget.org` catalog entry for `aspose.words.foss` 26.2.0) confirms the actually-published package's dependency graph does not include this package for any target framework, so no real consumer impact — but it means the disposition ledger's `verified_against_source` claim against this exact `.csproj` file (units u0026–u0028) missed a real line in the file it cites as evidence.

**NIT — product-specific, cosmetic.**
`badge-dispositions.json` unit `b0002` (line 17) is recorded with `"category": "unknown"` — the ".NET Standard" badge was never classified. No functional effect.

No BLOCKER-level factual fabrications were found beyond the one code example above; dependency version numbers, format-support claims, class counts, and the great majority of API descriptions are all verbatim-accurate against source. The candidate is materially an improvement in structure and completeness over the original README, and is already live in production identically to what was reviewed here.

## Stage B: Source Cross-Check

### Factual Accuracy claims

**"617 public types" (readme.md lines 893, 901)** — CONFIRMED, via two independent methods.
- `knowledge/words/net/merged/model.yaml` line 26: `class_count: 617`.
- Independently recomputed from raw entity records rather than trusting the pre-aggregated stat: `grep -o '"kind": "[a-z_]*"' knowledge/words/net/merged/api_surface.json | sort | uniq -c` → `379 class_declaration`, `27 interface_declaration`, `211 enum_declaration` (plus 16 constant, 13 static_field, not part of the "Core API/Interfaces/Enumerations" count). 379+27+211 = **617**, matching exactly.

**Target frameworks `net462;netstandard2.0;net8.0` (readme.md lines 91, 103)** — CONFIRMED. `runs/.clone_cache/aspose_words_net/Aspose.Words/Aspose.Words.csproj` line 5: `<TargetFrameworks>net462;netstandard2.0;net8.0</TargetFrameworks>`.

**Format support table (readme.md lines 908–910)** — CONFIRMED against `knowledge/words/net/merged/formats.md`, read in full: DOCX line 17, DOCM line 15, DOTX line 20, DOTM line 19 all `Yes|Yes`; FLATOPC/FLATOPCMACROENABLED/FLATOPCTEMPLATE/FLATOPCTEMPLATEMACROENABLED lines 26–29 all `Yes|Yes`; MARKDOWN line 41 `Yes|Yes`; TEXT/TXT lines 59/62 `Yes|Yes`; DOC line 13, RTF line 54, HTML line 33, EPUB line 25, ODT line 47 all `-|-`. Exact match to the README's positive/negative claims.

**NuGet package `Aspose.Words.FOSS` genuinely published (readme.md line 80)** — CONFIRMED via my own fresh live calls (not reused from Stage A):
```
curl -s https://api.nuget.org/v3-flatcontainer/aspose.words.foss/index.json
→ {"versions": ["26.2.0"]}
```
Registration endpoint (`.../registration5-semver1/aspose.words.foss/26.2.0.json`) shows `"listed":true`, `"published":"2026-07-29T18:04:48.54+00:00"`. The catalog entry (`.../catalog0/data/2026.07.29.18.11.09/aspose.words.foss.26.2.0.json`) shows `"authors":"Aspose"`, `"licenseExpression":"MIT"`, `"id":"Aspose.Words.FOSS"` — matches the README's install instructions exactly.

### Dependency Accuracy claims

**SkiaSharp 3.119.0 / BitMiracle.LibTiff.NET 2.4.649 / Microsoft.Win32.Registry 5.0.0 (readme.md lines 97–99)** — CONFIRMED, both in source and in the live shipped artifact:
- `Aspose.Foundation/Aspose.Foundation/Aspose.Foundation.csproj` lines 80/82 (`Condition="'$(TargetFramework)' != 'net462'"`): `SkiaSharp` 3.119.0, `BitMiracle.LibTiff.NET` 2.4.649; line 86 (`Condition="'$(TargetFramework)' == 'netstandard2.0'"`): `Microsoft.Win32.Registry` 5.0.0.
- Live NuGet catalog `dependencyGroups`: `.NETStandard2.0` group lists all three (SkiaSharp, BitMiracle.LibTiff.NET, Microsoft.Win32.Registry); `net8.0` group lists only SkiaSharp + BitMiracle.LibTiff.NET (no Registry) — this independently confirms the README's precise claim that Registry is "not referenced by ... the .NET 8 builds," using the actually-shipped package graph rather than just source.

**Test-only dependencies (readme.md lines 108–109)** — CONFIRMED. `Aspose.Words.Tests/Aspose.Words.Tests.csproj` lines 72–75: `Microsoft.NET.Test.Sdk` 17.13.0, `Newtonsoft.Json` 13.0.3, `NUnit` 4.2.2, `NUnit3TestAdapter` 5.0.0 — exact version match.

**`System.Text.Encoding.CodePages` 7.0.0 omitted from Dependencies section** — CONFIRMED both ways.
- Source: `Aspose.Foundation.csproj` line 81, inside the identical `ItemGroup Condition="'$(TargetFramework)' != 'net462'"` block (lines 79–83) as the two listed packages.
- Live: the same NuGet catalog fetch above shows **no** `System.Text.Encoding.CodePages` entry in either the `.NETStandard2.0` or `net8.0` dependency groups — independently reproduces Stage A's "genuinely absent from the shipped package" conclusion with a fresh pull, not a reused citation.

**`Aspose.EnumExtensionsGenerator` 1.0.2 unbuildable-from-clean-clone claim** — CONFIRMED, and I went one step further than Stage A here (their report explicitly said this NuGet endpoint "was not re-fetched in this pass"):
- Source: `Aspose.Words.csproj` line 100, `Aspose.Foundation.csproj` line 92, both `PackageReference Include="Aspose.EnumExtensionsGenerator" Version="1.0.2"`.
- Live: `curl https://api.nuget.org/v3-flatcontainer/aspose.enumextensionsgenerator/index.json` → `BlobNotFound` (404). The package genuinely does not exist on nuget.org, confirming a from-clean-clone `dotnet build` fails at restore. (This is already disclosed in the candidate's own `upstream-issues.md` line 9, which I independently corroborate here.)

### API Accuracy claims

**Fabricated `doc.FirstSection.Body.Shapes[0].Chart` (readme.md line 187)** — CONFIRMED as broken, with a refinement Stage A missed. I read `Body.cs` in full (`Aspose.Words/Model/Sections/Body.cs`): no `Shapes` member anywhere in the class (only constructor, `NodeType`, `ParentSection`, `Accept`/`AcceptStart`/`AcceptEnd`, `CanInsert`, `EnsureMinimum`). `knowledge/words/net/merged/api_surface.json`'s own `Body` record (starts line 65877) lists the identical member set — no `Shapes`. **However**, unlike Stage A's characterization ("does not exist ... anywhere in the codebase"), a `Shapes` member does exist, one level up: `Aspose.Words/Model/Sections/Story.cs` line 68: `internal ShapeCollection Shapes { get { return mShapes ?? (mShapes = new ShapeCollection(this)); } }` — and `Body : Story`. But it is declared `internal`, and its return type is *also* internal (`Aspose.Words/Model/Drawing/ShapeCollection.cs` line 12: `internal class ShapeCollection : NodeCollection`). Since the shipped package is a compiled `Aspose.Words.FOSS.dll` referenced from a separate consumer assembly, this member and type are inaccessible to any real user — the actual compiler diagnostic for `doc.FirstSection.Body.Shapes[0].Chart` in consumer code is `CS0122` (inaccessible due to protection level), not `CS1061` as Stage A's Verdict states, and even if it were accessible the return type itself couldn't be named outside the assembly. Verdict/severity is unchanged (still a genuine BLOCKER — the line cannot compile for any consumer), but "does not exist ... anywhere" overstates it; it exists as unreachable internal plumbing.
- Independently re-read `knowledge/words/net/merged/snippets/snippet_010.cs` in full: confirms Stage A's citation exactly — `Shape shape = builder.InsertChart(ChartType.Column, 432, 252); Chart chart = shape.Chart;` (lines 6–7) is the real, scouted, compiling access pattern; it never goes through `Body.Shapes`.

**`DigitalSignatureUtil.RemoveAllSignatures` real/public (Verdict, MAJOR finding)** — CONFIRMED. `Aspose.Words/Model/DigitalSignatures/DigitalSignatureUtil.cs` line 33: `public static class DigitalSignatureUtil`; line 197: `public static void RemoveAllSignatures(string srcFileName, string dstFileName)`; line 223: overload `RemoveAllSignatures(Stream, Stream)`. Doc comment (lines 187–195) lists compatible formats as `Doc, Dot, Docx, Dotx, Docm, Dotm, Odt, Ott` — Docx/Dotx/Docm/Dotm (this FOSS edition's shipped formats) are included, confirming Stage A's claim precisely.

**Chart object model members (readme.md lines 187–198, 887–891)** — all CONFIRMED by direct read:
- `Chart.cs` line 22: `public class Chart : IChartFormatSource`.
- `Shape.cs` line 1551: `public Chart Chart` (property) — and line 23's XML-doc summary, `"Represents an object in the drawing layer, such as an AutoShape, textbox, freeform, OLE object, ActiveX control, or picture."`, matches the Core API table entry for `Shape` (readme.md line 531) **verbatim**.
- `ChartSeries.cs` line 514: `public bool HasDataLabels`; line 531: `public ChartDataLabelCollection DataLabels`.
- `ChartDataLabel.cs` line 534: `public bool ShowCategoryName`; line 592: `public bool ShowValue`; line 869: `public ChartDataLabelPosition Position`.
- `ChartDataLabelCollection.cs` line 69: `public ChartDataLabel this[int index]`.
- `DigitalSignatureUtil.cs` line 17 XML-doc: `"Provides methods for signing document."` — verbatim match to the Core API table entry (readme.md line 296).

**Other Detailed-Member-Reference / example members** — all CONFIRMED via direct read of `Aspose.Words/Model/Document/Document.cs`: constructors at lines 249/262/275/362/378 (`Document()`, `Document(fileName)`, `Document(fileName, loadOptions)`, `Document(stream)`, `Document(stream, loadOptions)`); `AppendDocument(Document, ImportFormatMode)` line 1239 and 3-arg overload line 1250; `AcceptAllRevisions()` line 1540; `DigitalSignatures` property line 1017; `Protect(ProtectionType)`/`Protect(ProtectionType, string)` lines 1562/1582. `ImportFormatMode.KeepSourceFormatting` confirmed as a real enum member in `Aspose.Words/Model/.../ImportFormatMode.cs`.

### Ledger-completeness / preservation claims

Independently re-derived, not just re-read Stage A's numbers:
- `structure-dispositions.json`: read in full — exactly 3 entries (`s0001`/`s0002`/`s0003`), headings "At a Glance", "Merge Two Documents", "Convert Markdown to DOCX" — all candidate-new sections, none mapping any of the original's 8 top-level headings. CONFIRMED.
- `grep -c '"unit_id"' content-dispositions.json` → 97; `grep -c "dropped\|incorrectly_excluded"` across all four disposition JSON files (`content-`, `code-example-`, `badge-`, `structure-dispositions.json`) → 0 in every file. CONFIRMED.
- Re-fetched the original commit myself rather than trusting Stage A's `/tmp/orig_readme.txt`: `git -C runs/.clone_cache/aspose_words_net show 572fc74:README.md`. Confirms all three cited silent drops verbatim:
  - "...bookmarks, comments, footnotes, shapes." (the word "shapes" is present).
  - "...check whether a DOCX is signed and untampered, inspect the certificates, **or remove signatures**. (Creating new signatures is not included in this edition.)"
  - The full `## Enjoying it? Star it ⭐` section (Star/Watch/Tell-someone bullets) exists verbatim in the original's tail. `grep -ic "star it\|watch.*releases\|tell someone" reports/repo-presenter-regen-full/words/net/readme.md` → `0` in the candidate.

### Additional unflagged finding (not raised in Stage A's Factual/Dependency/API sections)

**`data/package_registry.json`'s `words.net` entry is stale, but this is already self-disclosed by the product's own ledger.** I read `data/package_registry.json` lines 419–438 directly: `"published": false`, `"verified_owner": null`, `scouted_at: "2026-08-01T06:02:00Z"`, with an `evidence_note` explicitly calling it "a naming-convention guess... not a live-verified identity." My own live checks above (package listed, published 2026-07-29, version 26.2.0) show this registry entry is genuinely wrong/stale — a real discrepancy. However, re-reading `upstream-issues.md` (which Stage A did cite for its lines 13–17 and line 34) in full, I found it **already contains a dedicated section, lines 19–23**, titled `"data/package_registry.json's published: false flag is stale for this product"`, disclosing this exact fact with the same live-verification detail, and correctly scoping it as INFORMATIONAL / out-of-write-scope. So this is not an undisclosed gap — it's a case where Stage A's review, despite quoting other parts of the same `upstream-issues.md` file, did not surface this already-existing disclosure. Net effect: CONFIRMED as a real (but already-disclosed and non-blocking) data-file staleness issue, not a new finding requiring escalation.

### Scope-and-limitations scan (unflagged, checked for completeness)

Read `knowledge/words/net/merged/limitations.md` in full: 22 `NotImplementedException` stubs exist beyond what the README's Scope and Limitations section enumerates by category (e.g., several `ChartFormat` theme-color setters, `ShadowFormat.Visible`, `DocumentBuilder.InsertStructuredDocumentTag` for certain SDT types, `CompatibilityOptions.OptimizeFor`, multiple `NrxXmlBuilder` revision-writer methods, `Ecma376AgileEncryption.Encrypt`). Cross-checked against every member actually named in the README's Quick Start / Additional Examples / Detailed Member Reference / Core API table — none of these stub members are referenced anywhere in the candidate. Result: UNVERIFIABLE-as-a-defect — scanned clean, no second broken example found among these landmines.

## Stage C: Adversarial Verification

**1. BLOCKER — `doc.FirstSection.Body.Shapes[0].Chart` fabricated/broken example.**
CONFIRMED (severity correct). Independently re-read `Body.cs` in full (16 lines of members, no `Shapes`) and `structure`d `readme.md` line 187 — the line is live exactly as quoted. However, the Verdict's own supporting text is not fully accurate and is self-contradicted by the review's own Stage B: `Story.cs:68` (`Body : Story`) does declare `internal ShapeCollection Shapes`, so "no `Shapes` getter anywhere in the codebase" overstates it, and the real compiler diagnostic for external consumer code is CS0122 (inaccessible), not the CS1061 the Verdict states. Net effect unchanged — the line still cannot compile for any consumer, live in production (re-confirmed: `gh api .../contents/README.md` LF-normalized sha256 `013cd7cc…` matches the candidate exactly) — but the Verdict quotes a wrong error code that its own document later corrects and never reconciles.

**2. MAJOR — silent drop of "...or remove signatures" (Key Capabilities).**
CONFIRMED. Re-fetched `572fc74:README.md` myself — line 17 reads "...or remove signatures. (Creating new signatures is not included...)"; candidate `readme.md` line 72 reads "...check whether a document is signed and untampered, and inspect certificates...creating new signatures is not included" — "or remove signatures" is genuinely gone. `DigitalSignatureUtil.cs:33` (`public static class`), `:197` (`RemoveAllSignatures(string,string)`), `:223` (stream overload), doc-comment formats list at `:187-195` (Doc/Dot/Docx/Dotx/Docm/Dotm/Odt/Ott) all verified verbatim. `content-dispositions.json` unit `u0021` (line 243) re-read directly: excerpt is the candidate's final bullet, `disposition: merged_verbatim`, no drop disclosed. Severity (MAJOR) is reasonably calibrated — a real, non-trivial, non-stub capability erased from the primary discovery surface with a ledger that affirmatively (falsely) claims full preservation.

**3. MAJOR (systemic) — structure-dispositions.json only tracks new headings.**
CONFIRMED for words/net, DOWNGRADED on the "systemic" tag. Re-read `structure-dispositions.json` in full: exactly 3 entries (s0001-s0003), all new headings, zero mapping to any of the original's 8 headings — matches the Verdict exactly. But checked 4 other products' ledgers in the same `reports/repo-presenter-regen-full/` tree: **`note/python`'s `structure-dispositions.json` directly falsifies the "schema can never record this" framing** — it has 13 entries, most mapping *original* headings, including `s0007`: `"disposition": "excluded"` with an `"excluded_reason"` field explaining why "🧭 Traverse MS OneNote document structure (DOM)..." was dropped — and I confirmed that exact heading exists verbatim in the original `note/python` README (`git show 6d97a52:README.md` line 303). The schema demonstrably supports exactly the "was a heading dropped and why" disclosure the Verdict says it structurally cannot provide. (`cells/net` and `pdf/net` do show the same new-headings-only pattern as words/net, so the *practice* is inconsistent/recurring across some runs — but "systemic" as "the schema's own design gap, affecting every product" is contradicted by counter-evidence sitting in the same directory tree the reviewer already had open.)

**4. MINOR (systemic) — content-dispositions.json excerpts are candidate text, not original text.**
CONFIRMED for words/net, DOWNGRADED on the "systemic" tag. Re-verified `u0021`'s excerpt is candidate-final text (matches readme.md line 72 verbatim), and `grep -c '"unit_id"'` = 97 confirmed exactly. But `note/python`'s `content-dispositions.json` again falsifies the blanket claim: `u0003`'s excerpt — "This repository provides a Python library with a **subset-compatible Aspose.Note for .NET-shaped public API**..." — is verbatim original text (`git show 6d97a52:README.md` line 12) and does **not** appear anywhere in `note/python`'s candidate `readme.md` (grep, no match); it's tagged `merged_reframed`, i.e., original wording quoted precisely because it was reframed away. Same for `u0001`/`u0002` (`excluded` units quoting the dropped original bullets with `excluded_reason`). The ledger mechanism plainly can and does embed original excerpts elsewhere in this same run set — this is a words/net-specific (and apparently not universal) gap, not a property of the ledger format itself.

**5. MINOR — silent drop of "shapes" from the structural-content bullet.**
CONFIRMED exactly. Re-fetched original line 10 ("...bookmarks, comments, footnotes, shapes.") and candidate line 66 ("...bookmarks, comments, and footnotes...") — "shapes" is absent, word for word as claimed. Severity (MINOR, not MAJOR) is correctly calibrated since `Shape` remains in the API table — verified present at readme.md line 531's table context — so this is narrative-only, not a capability erasure.

**6. MINOR — `System.Text.Encoding.CodePages` 7.0.0 omitted from Dependencies.**
CONFIRMED, both source and live. `Aspose.Foundation.csproj:81` — verified independently, sitting in the identical `ItemGroup Condition="'$(TargetFramework)' != 'net462'"` block as the two listed packages (lines 79-82). Fresh live NuGet catalog fetch (`api.nuget.org/v3/catalog0/...aspose.words.foss.26.2.0.json`) reproduced independently: `.NETStandard2.0` dependencyGroup lists SkiaSharp/BitMiracle.LibTiff.NET/Microsoft.Win32.Registry only, `net8.0` lists SkiaSharp/BitMiracle.LibTiff.NET only — no CodePages in either, confirming the "no real consumer impact" mitigation. readme.md line 91's "full required-package and native-requirement breakdown" claim and the absence of any "CodePages" string in readme.md were both re-confirmed directly. Tag ("possibly systemic," hedged rather than asserted) is appropriately cautious and not contradicted by anything found.

**7. NIT — `badge-dispositions.json` unit `b0002` category "unknown".**
CONFIRMED exactly. Read the file in full: `b0002` at line 17 is `"category": "unknown"`, 4 total badge units, all `"action": "preserved"`. No functional effect, correctly scoped as NIT.

**Closing "no other BLOCKER-level fabrications" claim**: spot-checked independently (not just re-read) — `Chart.cs:22`, `Document.cs:1017/1239/1250/1540/1562/1582` (DigitalSignatures, AppendDocument×2, AcceptAllRevisions, Protect×2) all match the cited signatures exactly. Holds up under a second independent pass; no additional blocker found.

**Overall**: 5 of 7 Verdict findings CONFIRMED as stated (severities well-calibrated); 1 (BLOCKER) CONFIRMED in substance but with an inaccurate technical citation the review's own later section already exposes and never reconciled; 2 (both "systemic" tags, findings 3 and 4) CONFIRMED as real word/net-specific defects but DOWNGRADED on their systemic characterization — direct counter-evidence in `note/python`'s ledgers (same repo, same tree, one directory over) shows the disposition schema itself is capable of exactly what the Verdict says it structurally cannot do, meaning this is an inconsistent-execution gap in some runs, not a design-level defect "affecting every product's disposition ledgers."