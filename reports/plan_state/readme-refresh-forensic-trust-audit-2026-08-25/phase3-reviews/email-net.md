## Identity

Four artifacts requested; all four obtained.

- **Candidate**: `reports/repo-presenter-regen-full/email/net/readme.md` — SHA-256 `3e9bc7ea033ec50db9575949952894b9ca9f09005a64aa2ff26970f3ae987bac` (matches `last-verified.json:2` `readme_sha256` exactly, via `certutil -hashfile`).
- **Original-at-generation-time**: obtained via `git -C runs/.clone_cache/aspose_email_net show a8999e2:README.md` (commit `a8999e259143a9ffc660086b34a7f39516da29f5`, "Initial public release", 2026-03-27) — this is the "pinned repo_sha" cited by `upstream-issues.md:3-4` and `knowledge/email/net/merged/model.yaml:7`.
- **Current-upstream**: `runs/.clone_cache/aspose_email_net/README.md` — path exists. Clone-cache HEAD is now commit `59125b4732df0eedbc4d4c2ab978698ed4348eb7` ("docs: refresh README with verified content, structure, and examples", author Babar Raza, 2026-08-15T12:29:40+05:00, trailer `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`), per `git -C runs/.clone_cache/aspose_email_net log -1`. File is byte-identical to the candidate once CRLF is normalized (`diff --strip-trailing-cr candidate upstream` → 0 lines of output).
- **Published**: obtained via `gh api repos/aspose-email-foss/Aspose.Email-FOSS-for-.Net/contents/README.md --jq .content | base64 -d`. SHA-256 of the fetched content = `3e9bc7ea033ec50db9575949952894b9ca9f09005a64aa2ff26970f3ae987bac` — identical to the candidate's hash. `diff --strip-trailing-cr candidate published` → 0 lines. `gh api repos/aspose-email-foss/Aspose.Email-FOSS-for-.Net/commits` confirms `59125b4732df0eedbc4d4c2ab978698ed4348eb7` (2026-08-15T07:29:40Z) is the current tip of the real repo's default branch, two commits after `a8999e2`.

**Net result**: candidate == current-upstream == published (three-way byte-identical after line-ending normalization); all three differ from original-at-generation-time.

## Factual Accuracy

All checkable factual claims in the candidate were independently verified against the real cloned source and, where applicable, the live NuGet registry:

- "No required third-party package dependencies" (readme.md:87-89) — confirmed: `src/Aspose.Email.Foss/Aspose.Email.Foss.csproj` has zero `<PackageReference>` entries.
- NuGet package ID `Aspose.Email.Foss` (readme.md:66-71) — matches `<PackageId>Aspose.Email.Foss</PackageId>` in the csproj.
- NuGet version `26.7.0` (readme.md:76) — confirmed live via `WebFetch https://api.nuget.org/v3-flatcontainer/aspose.email.foss/index.json` → the only version listed is `26.7.0`; cross-confirmed in `data/package_registry.json` (email→net entry, `"published": true`, same evidence_url).
- Target framework `.NET 8.0` (readme.md:79, 93) — matches `<TargetFramework>net8.0</TargetFramework>` in both csproj files.
- Dev-dependency versions (readme.md:97-98: `Microsoft.NET.Test.Sdk 17.8.0`, `xunit 2.5.3`, `xunit.runner.visualstudio 2.5.3`, `coverlet.collector 6.0.0`) — exact match against `tests/Aspose.Email.Foss.Tests/Aspose.Email.Foss.Tests.csproj`.
- "29 classes and enumerations" (readme.md:180) — independently recounted via `grep -rhoE "^\s*(public|internal)\s+..." src/Aspose.Email.Foss/`: 23 public classes/records + 6 public enums = 29 (MapiMessage's 3 `partial` declarations counted once). Exact match.
- Namespaces `Aspose.Email.Foss.Cfb` / `Aspose.Email.Foss.Msg` (readme.md:178-179) — a third namespace, `Aspose.Email.Foss.Msg.Mime`, exists but all 14 of its types are `internal` (confirmed via grep of access modifiers across `Msg/Mime/*.cs`), so its omission from the public-facing namespace list is correct, not an error.
- License MIT (readme.md:318-320) — confirmed against `LICENSE` file text.
- Test class names and example project files (readme.md:307, 313) — `CfbRoundTripTests.cs`, `MsgReaderTests.cs`, `MapiMessageTests.cs`, `MapiMessageEmlTests.cs`, `MetadataSmokeTests.cs` and `examples/create_msg_and_eml/create_msg_and_eml.csproj`, `examples/msg_reader/msg_reader.csproj`, `examples/msg_summary/msg_summary.csproj` all confirmed to exist with those exact names.

No factual errors found in the rendered README text.

## Content-Preservation Ledger

Enumerated by diffing the true original (`git show a8999e2:README.md`) against the candidate by hand (the disposition JSON's own excerpts could not be used for this — see Verdict #1):

| Original unit | Disposition | Evidence |
|---|---|---|
| Title `# Aspose.Email FOSS for .NET` | PRESERVED verbatim | readme.md:1 |
| Intro bullet list (CFB/MSG/mutable objects/EML) | TRANSFORMED → prose paragraph | readme.md:7-12; disposition u0001 correctly labels this `merged_reframed` |
| `## Main Namespaces` + 2 bullets | MERGED → API Reference intro sentence | readme.md:177-181 (u0034) names both namespaces; no disposition unit explicitly tracks the original section as its own item (see Verdict #1) |
| `## Features` (6 bullets) | TRANSFORMED/expanded → `## Key Capabilities` (8 bullets) | readme.md:53-62; 1:1 correspondence hand-verified for 6 of 8 bullets, 2 are net-new grounded additions (SetProperty/GetPropertyValue, ValidationIssues) verified against `MapiMessage.cs`/`MsgReader.cs` |
| `## Install` (1 command) | TRANSFORMED/expanded → `## Installation` | readme.md:69-77, adds XML PackageReference form + platform prose |
| Quick Start example 1 ("Read a subject") | PRESERVED verbatim | readme.md:108-115 |
| Quick Start example 2 ("Create and save a message") | PRESERVED (near-verbatim) → "Create and Save an MSG Message" | readme.md:121-135 |
| Quick Start example 3 ("Bridge between EML and MSG") | PRESERVED (near-verbatim) → "Convert EML to MSG" | readme.md:140-152, inside `<details>` |
| `## Build And Test` (2 commands, stale `csharp/` prefix) | TRANSFORMED, defect corrected | readme.md:295-314 — real paths verified via `ls runs/.clone_cache/aspose_email_net/src/Aspose.Email.Foss/Aspose.Email.Foss.csproj` |
| `## Examples` (3 filenames, stale `csharp/examples/` prefix) | MERGED into Development and Testing paragraph, stale prefix dropped | readme.md:308-314; real paths verified via `ls runs/.clone_cache/aspose_email_net/examples/` |

No unit was DROPPED-SILENTLY, DROPPED-WITH-REASON, or INCORRECTLY-EXCLUDED — every original unit's substance survives, generally enhanced. New sections with no original ancestor (badges, banner, Navigation TOC, At-a-Glance diagram, Dependencies, API Reference table, Documentation & Resources, Scope and Limitations, License) are all independently grounded per Factual Accuracy / API Accuracy above.

## Usability

- All 11 Navigation TOC anchors (readme.md:16-26) verified against GitHub's heading-slug algorithm; spot-checked "Documentation & Resources" → `#documentation--resources`, correct.
- `<details>` progressive disclosure used deliberately (1 of 3 "Additional Examples" and only the summary table of "API Reference" show by default) — matches the intent stated in the upstream commit message.
- Quick Start reaches working output in 4 lines of code.
- NIT: "Additional Examples" intro sentence (readme.md:119) is immediately followed by one example outside the `<details>` block and two inside it — intentional per the commit message, but a reader skimming headings only might not notice the collapsed continuation.

## Presentation/SEO

- Badge row + banner render before prose (readme.md:3-5), standard for this pipeline's template.
- Banner path `https://products.aspose.org/media/email/net/banner-readme.png` resolves to a real local asset: confirmed present at `static/media/email/net/banner-readme.png`.
- Single `#` H1, no heading-level duplication.

## Dependency Accuracy

- "No required third-party package dependencies" — confirmed (zero `<PackageReference>` in `Aspose.Email.Foss.csproj`).
- Dev dependencies — exact name+version match against `tests/Aspose.Email.Foss.Tests/Aspose.Email.Foss.Tests.csproj` (4 packages).
- Runtime requirement ".NET 8.0 SDK/runtime or later" matches `<TargetFramework>net8.0</TargetFramework>`.
- No inaccurate dependency claims found.

## Example Verification

- All 4 C# examples (Quick Start, Create-and-Save, Convert-EML-to-MSG, Inspect-CFB) reference real, currently-existing APIs with matching signatures, verified directly against `src/Aspose.Email.Foss/Msg/MapiMessage.cs` and `src/Aspose.Email.Foss/Cfb/CfbReader.cs`. Not compiled/executed (read-only audit) — signature-level verification only.
- Install/build/test/run commands (readme.md:70, 300-302, 313) all use real, existing paths — confirmed via `ls`/`find` against the clone cache.
- By contrast, the upstream repo's own `examples/README.md` still carries the stale `csharp/examples/...` prefix in 3 places (confirmed live: `grep -rn "csharp/" runs/.clone_cache/aspose_email_net/` → 3 hits, all in `examples/README.md`, lines 30/45/61) — this is exactly the defect `upstream-issues.md` documents and correctly declines to fix (out of scope for a README-only refresh).

## API Accuracy

- Class/enum count (readme.md:180, "29 classes and enumerations") independently recounted from source: 23 public classes/records + 6 public enums = 29. Exact match.
- The API Reference table (readme.md:188-223) lists all 23 public classes and all 6 public enums found in source — full coverage, nothing invented, nothing omitted from the summary table.
- Detailed Member Reference (readme.md:229-269) cross-checked for `CfbReader` and `MapiMessage`: every listed method/property exists with a matching name and parameter list. Some real public members are omitted (e.g., `CfbReader.MiniStream`, `.MaterializedStreamCount`, `MapiMessage.SenderAddressType`, `.UnicodeStrings`, `.MajorVersion`/`.MinorVersion`, `.Properties`) — this is deliberate curation, consistent with the README's own "beyond the strongly-typed properties..." framing, not a fabrication.
- `Aspose.Email.Foss.Msg.Mime` (14 internal-only types) correctly excluded from the public API description.

## Link/Rendering

- `PUBLIC_API.md` link (readme.md:278) — resolves to a real, populated file in the upstream repo (65 lines: 2 stable namespaces + primary types), confirmed via `cat runs/.clone_cache/aspose_email_net/PUBLIC_API.md`. However, the **local mirror** at `reports/repo-presenter-regen-full/email/net/PUBLIC_API.md` is only a 2-line stub (`# PUBLIC_API` + blank line) — see Verdict #5.
- `CHANGELOG.md`, `LICENSE` links — both resolve to real files in the clone cache root.
- `docs.aspose.org/email/net/`, `kb.aspose.org/email/net/`, `reference.aspose.org/email/net/` — all three have real, populated local content directories (confirmed via `ls content/{docs,kb,reference}.aspose.org/en/email/net/`).
- GitHub issues link and repo URL (readme.md:280) match the real, live repo, confirmed via `gh api`.
- Mermaid diagram (readme.md:30-51) is syntactically well-formed (`flowchart TD`, 3 subgraphs); not independently rendered (read-only audit), no obvious syntax errors.

## Verdict

1. **MAJOR / SYSTEMIC** — `content-dispositions.json`, `structure-dispositions.json`, and `code-example-dispositions.json`'s `excerpt` fields do not contain the actual pre-refresh original README text; they contain the CANDIDATE's own rewritten text, self-labeled `verified_against_source`. Evidence: `grep -n "dependency-free C# library\|Main Namespaces\|Read and write CFB containers through\|Bridge between EML and MSG\|Build And Test\|dotnet pack csharp\|Examples are available under\|csharp/examples" reports/repo-presenter-regen-full/email/net/{content-dispositions.json,structure-dispositions.json,code-example-dispositions.json,badge-dispositions.json}` → zero matches, even though these are exact, distinctive phrases from the true original (`git -C runs/.clone_cache/aspose_email_net show a8999e2:README.md`). Meanwhile every excerpt (spot-checked u0013, u0016, u0034, u0078) verbatim-matches a line in `readme.md`. Consequence: the ledger cannot answer its own stated purpose ("map original-README units to what happened to them") by inspection alone — an auditor must independently diff against git history, as this report did, to detect a silent drop. Systemic because the mechanism populating `excerpt` appears to run post-generation against the candidate rather than pre-generation against the source, which would reproduce on any product refreshed by the same code path.

2. **MAJOR / SYSTEMIC (same root cause as #1)** — `badge-dispositions.json` labels all 3 badges (`b0001`-`b0003`) `"action": "preserved"`, but the true original README (`a8999e2`) contains zero badge markup of any kind — badges are net-new additions, not preserved units. Evidence: `git -C runs/.clone_cache/aspose_email_net show a8999e2:README.md` has no `![...]` badge syntax anywhere.

3. **MAJOR / leaning SYSTEMIC** — a real, non-dry-run publication of this exact candidate to the live public repo (commit `59125b4732df0eedbc4d4c2ab978698ed4348eb7`, 2026-08-15T07:29:40Z, `Co-Authored-By: Claude Sonnet 5`) has zero entry in either canonical tracking artifact this audit was scoped to check. Evidence: `grep -in "email" data/readme_published_state.json` → no output; `grep -n "email/net" reports/repo_presenter_actions.jsonl` → no output (the file has only 2 total lines, covering `note/python` and `cells/rust`). The publication's reality was cross-confirmed via `gh api repos/aspose-email-foss/Aspose.Email-FOSS-for-.Net/contents/README.md --jq .content | base64 -d`, byte-identical to the candidate (both hash `3e9bc7ea033ec50db9575949952894b9ca9f09005a64aa2ff26970f3ae987bac`, matching `last-verified.json:2`). `data/readme_published_state.json`'s header comment states entries are "seeded ... from the authoritative plan's own recorded PR/merge history"; email/net's publish was a direct push to `main` with no PR (only `a8999e2` and `d37af27` precede it, no merge commit) — a structurally different path that PR-history-based seeding would miss. Likely systemic to any product published via direct-push rather than PR-merge.

4. **MINOR / product-specific (self-inflicted staleness)** — `upstream-issues.md:3-4` and `knowledge/email/net/merged/model.yaml:7` both cite pinned `repo_sha` `a8999e259143a9ffc660086b34a7f39516da29f5`, but the clone cache's actual current HEAD is `59125b4732df0eedbc4d4c2ab978698ed4348eb7` (confirmed via `git -C runs/.clone_cache/aspose_email_net log -1 --format="%H"`) — the same session's own publish action (finding #3) moved the very clone cache the citation claims to be pinned against, and neither file was updated afterward. Low practical impact: the finding's substance (stale `csharp/` prefix in `examples/README.md`) is unchanged at the new HEAD (`grep -rn "csharp/" runs/.clone_cache/aspose_email_net/` still finds all 3 references) — only the cited pin is now inaccurate.

5. **NIT / product-specific** — `reports/repo-presenter-regen-full/email/net/PUBLIC_API.md` is a 2-line stub (`# PUBLIC_API` + blank line), while the real upstream `PUBLIC_API.md` the candidate links to (readme.md:278) has 65 lines of real content. Not a defect in the published README (the link resolves correctly against the real repo), but a stale/empty artifact sitting alongside the audited files.

No BLOCKER findings. No factual, dependency, API, or example errors were found in the rendered README/candidate itself — every content, code, and API claim checked independently matched the real cloned source and the live NuGet registry. All defects identified are in the surrounding governance/tracking layer (disposition-ledger self-report fidelity and publish-event logging), not in the public-facing artifact.

## Stage B: Source Cross-Check

Independent re-verification performed directly against `runs/.clone_cache/aspose_email_net/` source and build files, `knowledge/email/net/merged/*`, and `data/package_registry.json`. All commands run fresh by me; none of Stage A's citations were taken on faith.

### Factual Accuracy

- **"No required third-party package dependencies"** — CONFIRMED. Read the full contents of `runs/.clone_cache/aspose_email_net/src/Aspose.Email.Foss/Aspose.Email.Foss.csproj` myself: the only `<ItemGroup>` is a `<None Include="..\..\README.md" .../>` for pack metadata; zero `<PackageReference>` elements.

- **NuGet package ID `Aspose.Email.Foss`** — CONFIRMED verbatim. `<PackageId>Aspose.Email.Foss</PackageId>` at line 4 of the same csproj, exact case match to readme.md:66-71.

- **NuGet version `26.7.0` (readme.md:76)** — **UNVERIFIABLE from any of the three local sources I was scoped to check, and contradicted by all of them in isolation.** The csproj I read directly declares `<Version>0.1.0</Version>` (line 5). `runs/.clone_cache/aspose_email_net/CHANGELOG.md` has exactly one entry, `## [0.1.0] - 2026-03-18`, and nothing newer. `knowledge/email/net/merged/model.yaml:4` has `version: ''` (empty). `data/package_registry.json`'s email→net block (verified by direct read) has no version field at all — only `"published": true` and an `evidence_url` pointing at the live NuGet flatcontainer index, which is an external source outside my prescribed evidence set. Stage A's confirmation of `26.7.0` rests entirely on that same live external NuGet fetch, not on anything checked into this repo or the clone cache. This is plausibly explained by a publish-time version override (`dotnet pack /p:Version=...`) that never gets back-written to the checked-in csproj/CHANGELOG, but no artifact in my scope proves that mechanism exists — I found no CI/publish workflow in the clone cache (`find ... -iname "*.yml"` → empty) and no NuGet-publish workflow in `.github/workflows` matching this product. Flagging as a real, previously-unflagged gap: the version number baked into the README's install example cannot be corroborated by any local repo artifact.

- **Target framework `.NET 8.0`** — CONFIRMED independently, three times over: `<TargetFramework>net8.0</TargetFramework>` in `src/Aspose.Email.Foss/Aspose.Email.Foss.csproj:3`, in `tests/Aspose.Email.Foss.Tests/Aspose.Email.Foss.Tests.csproj:3`, and in all three `examples/*/*.csproj` files.

- **"29 classes and enumerations" (readme.md:180)** — CONFIRMED by three independent methods that all agree:
  1. My own `grep -rn -E "^\s*(public|internal)\s+..."` over `src/Aspose.Email.Foss/` and manual tally of `public` (non-`internal`) types: 23 classes/records (`CfbConstants, CfbDocument, CfbException, CfbNode, CfbReader, CfbStorage, CfbStream, CfbWriter, DirectoryEntry, DirectoryEntryNameComparer, Header, MapiAttachment, MapiMessage, MapiProperty, MapiPropertyCollection, MapiRecipient, MsgConstants, MsgDocument, MsgException, MsgReader, MsgStorage, MsgStream, MsgWriter`) + 6 enums (`CommonMessagePropertyId, DirectoryColorFlag, DirectoryObjectType, MsgStorageRole, PropertyTypeCode, SectorMarker`) = 29, with `MapiMessage`'s 3 `partial` files counted once.
  2. `grep -c '"kind": "class_declaration"'` (21) + `'"kind": "record_declaration"'` (2) + `'"kind": "enum_declaration"'` (6) in `knowledge/email/net/merged/api_surface.json` = 29.
  3. `knowledge/email/net/merged/model.yaml:19` states `class_count: 29` directly.
  All 29 names extracted from `api_surface.json` match the readme's API Reference table 1:1 with no additions or omissions.

- **Namespaces `Aspose.Email.Foss.Cfb` / `Aspose.Email.Foss.Msg` (readme.md:177-179)** — CONFIRMED via `grep -n "^namespace"` across every file in `Cfb/` and `Msg/` (non-Mime): all 23 public types plus the 6 enums resolve to exactly these two namespaces, none other.

- **`Aspose.Email.Foss.Msg.Mime` all-internal claim** — CONFIRMED in substance but Stage A's count is off by one. My `grep -n "^namespace" .../Msg/Mime/*.cs` finds **15** files in that namespace (`AddressParser, CharsetDecoder, EmlMessageMapper, HeaderParser, MimeBoundaryFactory, MimeEntity, MimeHeader, MimeMessageModel, MimeMultipart, MimePart, MimeReader, MimeWriter, MultipartParser, TransferEncodingDecoder, TransferEncodingEncoder`), not 14 as Stage A stated — and every one of them is declared `internal`. So the README's omission of this namespace from the public API section is still correct (REFUTES nothing material), but Stage A's own count ("all 14 of its types") is itself off by one against the real source.

- **License MIT** — CONFIRMED. Read `runs/.clone_cache/aspose_email_net/LICENSE` directly: first line `MIT License`, `Copyright (c) 2026 Aspose.Email FOSS Family`.

- **Test class names / example project files** — CONFIRMED by direct `find`: `tests/Aspose.Email.Foss.Tests/{CfbRoundTripTests,MapiMessageEmlTests,MapiMessageTests,MetadataSmokeTests,MsgReaderTests}.cs` all exist exactly as named; `examples/{create_msg_and_eml,msg_reader,msg_summary}/*.csproj` all exist exactly as named.

- **Scope and Limitations bullets (readme.md:283-292)** — CONFIRMED absent from source: `grep -rniE "imap|smtp|pop3|tnef|winmail|calendar|appointment" src/` finds only `"SMTP"` used as a MAPI address-type *string literal/property value* (`MapiRecipient.AddressType = "SMTP"`, etc.) — never a protocol implementation — and zero hits for IMAP, POP3, TNEF, winmail.dat, calendar, or appointment anywhere in source. The README's claims of *no* support for these are accurate. Also confirmed no `NotImplementedException`/`NotSupportedException`/`TODO` anywhere in `src/` (`grep` → zero hits), consistent with `knowledge/email/net/merged/limitations.md` ("No NotImplementedError patterns detected").

- **`PUBLIC_API.md` 65 lines vs. 2-line local mirror stub** — CONFIRMED independently: `wc -l runs/.clone_cache/aspose_email_net/PUBLIC_API.md` → 65; `wc -l reports/repo-presenter-regen-full/email/net/PUBLIC_API.md` → 2 (`# PUBLIC_API` + blank line).

- **Banner asset path** — CONFIRMED present: `static/media/email/net/banner-readme.png` exists (along with `banner.png`, `banner.webp`, `icon.png`, `icon.webp`).

- **Stale `csharp/` prefix in upstream `examples/README.md`** — CONFIRMED independently: my own `grep -n "csharp/" .../examples/README.md` → 3 hits, lines 30/45/61, all `dotnet run --project csharp/examples/...`. The real directory (`ls examples/`) has no `csharp/` subdirectory — projects sit directly under `examples/`. Matches Stage A exactly.

### Dependency Accuracy

- **Zero required package dependencies** — CONFIRMED (see csproj read above).
- **Dev dependencies exact name+version** — CONFIRMED by direct read of `tests/Aspose.Email.Foss.Tests/Aspose.Email.Foss.Tests.csproj`: `Microsoft.NET.Test.Sdk 17.8.0`, `xunit 2.5.3`, `xunit.runner.visualstudio 2.5.3`, `coverlet.collector 6.0.0` — all four match readme.md:97-98 exactly, including version strings.
- **`.NET 8.0 SDK/runtime` requirement** — CONFIRMED against `<TargetFramework>net8.0</TargetFramework>` in the main csproj.
- No inaccurate dependency claims found — agrees with Stage A.

### API Accuracy

- **Class/enum count "29"** — CONFIRMED (see three-way independent count above; strictly stronger than Stage A's single-method count since I cross-checked against `api_surface.json` as a third, independent source).
- **API Reference summary table (readme.md:188-223)** — CONFIRMED complete and accurate: all 23 public class/record names and all 6 enum names extracted independently from `api_surface.json` match the table's rows 1:1, no fabricated or missing entries.
- **Detailed Member Reference, `CfbReader`** — CONFIRMED member-for-member against `grep -n -E "public\s" .../Cfb/CfbReader.cs`: constructor, `FromFile`, `FromStream`, `IterStorages`, `IterStreams`, `IterChildren(uint)`, `IterTree(uint startStreamId=0)`, `FindChildByName`, `ResolvePath`, `GetEntry`, `GetStreamData`, and properties `Header, Difat, Fat, MiniFat, DirectoryEntries, RootEntry, MajorVersion, SectorSize, MiniSectorSize, DirectoryEntryCount, FileSize` — every signature and default value matches the README text exactly. Confirmed omitted-but-real members `MiniStream` and `MaterializedStreamCount` exist in source but are absent from the README (deliberate curation, as Stage A said).
- **Detailed Member Reference, `MapiMessage`** — CONFIRMED member-for-member against `grep -n -E "public\s"` across all three partial files: `Create`, `FromFile`, `FromStream`, `FromMsgDocument`, all three `LoadFromEml` overloads, `Save()`/`Save(path)`/`Save(stream)`, `SaveToEml()`/`(path)`/`(stream)`, `AddRecipient(emailAddress, displayName, recipientType)`, both `AddAttachment` overloads, `AddEmbeddedMessageAttachment(message, filename, mimeType)`, `SetProperty(propertyId, propertyType, value, flags)`, `GetPropertyValue(propertyId, propertyType, decode)`, `IterProperties()`, `IterPropertyKeys()` — every parameter name, order, and default matches. Listed properties `Subject, Body, HtmlBody, SenderName, SenderEmailAddress, MessageClass, InternetMessageId, MessageDeliveryTime, Recipients, Attachments, ValidationIssues` all exist exactly as named. Confirmed real-but-omitted members: `SenderAddressType, UnicodeStrings, MajorVersion, MinorVersion, TransactionSignatureNumber, Properties, IterAttachmentsInfo(), ToMsgDocument()`, and the `DefaultPropertyFlags`/`RecipientType*`/`AttachMethod*` constants — all deliberately curated out, not fabricated gaps.
- **`MsgReader`, `MsgWriter`, `MsgDocument`, `MsgStorage`, `MapiAttachment`, `MapiPropertyCollection`, `CfbWriter`** — all spot-checked directly against source (`grep -n -E "public\s"` per file); every method/property the README lists for these types exists with matching name, parameter order, and defaults. No fabricated members found anywhere in the Detailed Member Reference section.
- **`Aspose.Email.Foss.Msg.Mime` correctly excluded** — CONFIRMED (see Factual Accuracy above; 15 internal types, not 14, but 100% internal either way).

### Unflagged findings from my own pass

1. **NuGet version `26.7.0` is not corroborated by any local/repo artifact** (detailed above) — the strongest re-verification finding I turned up that Stage A did not surface as a gap in its own evidence chain (it treated a live external NuGet fetch as sufficient without noting that every local version-bearing file disagrees or is silent).
2. **Stage A undercounted the internal `Msg.Mime` types by one** (14 claimed vs. 15 actual) — does not change the underlying verdict (all internal, correctly excluded), but is a factual slip in Stage A's own audit trail worth correcting for the record.
3. No other unflagged high-risk factual/API/dependency claims found. Format support (`formats.md`: CFB/MIME/MSG import+export both "Yes") is consistent with the README's claims; `claims.json` and `model.yaml` (`class_count: 29`, `repo_sha` pin) are internally consistent with the rest of the audit; example-project target frameworks (`net8.0` in all three `examples/*.csproj`) are consistent with the README's stated runtime requirement.

## Stage C: Adversarial Verification

1. **CONFIRMED** — Independently reproduced the mechanism rather than just re-running the grep: calling `extract_old_readme_content_units()` against the true original (`git show a8999e2:README.md`) yields exactly 21 units (`u0001`="- Compound File Binary (CFB) containers", `u0016`="Create and save a message:", etc.), while calling it against the candidate `readme.md` yields exactly 85 units whose text is an *exact* match to every excerpt stored in `content-dispositions.json` (u0001, u0013, u0016, u0034, u0078 all verified verbatim). The ledger's excerpts are provably extracted from the candidate, not the original — stronger proof than Stage A/B's absence-of-phrase grep. Severity/tag correctly calibrated; refine the causal story: all four disposition JSONs share one identical mtime (Aug 19 23:50), four days *after* `readme.md`/the Aug 15 push — i.e. authored once the clone cache's "old" README had already been overwritten to match the candidate, not "the mechanism runs post-generation by design."

2. **CONFIRMED** — `badge-dispositions.json`'s 3 entries (`b0001`-`b0003`, all `"action": "preserved"`) verified directly; `grep -c '!\['` on the true original a8999e2 README returns 0, confirming zero original badges. Additionally found the exact code-level admission this is a known, still-live gap: `check_badge_disposition_coverage` (readme_refresh_checks.py:8207-8209) explicitly "Vacuous pass `[]` when `old_badges` is empty," and a nearby comment names this precise defect class as having previously shipped undetected on `cells/typescript`. This directly substantiates "SYSTEMIC (same root cause as #1)" — same Aug-19-batch timing as finding #1's files.

3. **DOWNGRADED** — The observational claim (no `email` row in `data/readme_published_state.json`, no `email/net` line in `reports/repo_presenter_actions.jsonl`) reconfirmed via fresh grep, both zero hits. But the causal explanation is falsified: `gh api repos/aspose-email-foss/Aspose.Email-FOSS-for-.Net/pulls/1` shows a real PR #1 ("docs: refresh README with verified content...", author babar-raza) with `"merged": true`, `"merged_at": "2026-08-15T07:29:40Z"`, `"merge_commit_sha": "59125b4732df..."` — i.e. this WAS a normal PR-merge, not a direct push. Stage A/B's "no merge commit" inference from a single-parent `git log` is invalid: a GitHub squash-merge also produces a single-parent commit, visually indistinguishable from a direct push — they didn't check `gh api .../commits/{sha}/pulls` before concluding "direct push, no PR." Since a real, ordinary PR/merge did exist, the "PR-history-based seeding would structurally miss a direct-push path" theory — and the "leaning SYSTEMIC to direct-push products" tag built on it — does not hold; the real explanation is more likely an incomplete Aug-18 backfill sweep that missed a real, discoverable PR, a different (and not yet demonstrated to be systemic) failure mode.

4. **CONFIRMED** — Directly verified both citations (`upstream-issues.md:3-4` and `knowledge/email/net/merged/model.yaml:7`) read `a8999e259143a9ffc660086b34a7f39516da29f5`, while `git -C runs/.clone_cache/aspose_email_net log -1 --format="%H"` returns `59125b4732df...`; also confirmed the finding's substance is unchanged at new HEAD (`grep -rn "csharp/"` still returns the same 3 hits in `examples/README.md`, lines 30/45/61). Severity (MINOR/product-specific) is fair. Minor imprecision only: `model.yaml`'s `promoted_at` is `2026-07-12`, over a month before the Aug-15 push, so "the same session" moved the pin's target is loosely worded (it's the same body of work across time, not one continuous session) — doesn't change the finding's validity.

5. **CONFIRMED** — `wc -l` on both files reproduced exactly: local mirror `reports/repo-presenter-regen-full/email/net/PUBLIC_API.md` = 2 lines (`# PUBLIC_API` + blank), upstream `runs/.clone_cache/aspose_email_net/PUBLIC_API.md` = 65 lines; `readme.md:278` links `PUBLIC_API.md` as a bare relative link, which resolves correctly on the real published GitHub repo (root-relative), not against the local stub. NIT/product-specific severity is correctly scoped — confirmed this reports/ tree is not wired into any Hugo site config, so the stub is never publicly served.