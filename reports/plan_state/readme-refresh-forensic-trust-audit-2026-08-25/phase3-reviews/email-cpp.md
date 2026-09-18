## Identity

Four artifacts sought; all four obtained.

1. **Original-at-generation-time** — obtained via `git -C runs/.clone_cache/aspose_email_cpp show c7252b3e4f6bbec4bbe5e2f50f51eb2a7384eaf2:README.md` (pinned SHA per `knowledge/email/cpp/merged/model.yaml:7` and `reports/repo-presenter-regen-full/email/cpp/upstream-issues.md:5`). 77 lines, 2137 bytes, sha256 `40a0d44e62344a1a40fd0908091ff033a8faadc70b1ebff1dddf11e21973366d`.
2. **Current-upstream** — `runs/.clone_cache/aspose_email_cpp/README.md`. Exists. Clone-cache HEAD = `fef9c934c3ad7a207c97cc24546176e678f577af` (`git -C runs/.clone_cache/aspose_email_cpp log --oneline -5`), tracking `origin/master` with zero ahead/behind (`git branch -a -vv`). 476 lines, 24624 bytes (CRLF line endings — `od -c` shows `\r\n`), raw sha256 `24cadf31716b7d3471dbb83f0bd63f408a8432074e38059088ac0acf45a58329`; after CRLF→LF normalization, sha256 `a092d3c0a0bb75796a9064f9abb4194362b6562ca9e0acb2affe921c8adf4f05`.
3. **Candidate** — `reports/repo-presenter-regen-full/email/cpp/readme.md`. 476 lines, 24148 bytes, sha256 `a092d3c0a0bb75796a9064f9abb4194362b6562ca9e0acb2affe921c8adf4f05` — matches `last-verified.json:2`'s recorded `readme_sha256` exactly.
4. **Published** — fetched live via `gh api repos/aspose-email-foss/Aspose.Email-FOSS-for-Cpp/contents/README.md --jq .content | base64 -d`. 24148 bytes, sha256 `a092d3c0a0bb75796a9064f9abb4194362b6562ca9e0acb2affe921c8adf4f05`.

Result: candidate, current-upstream (content-normalized), and published are all **byte-identical**. The only divergence between candidate and current-upstream is CRLF-vs-LF line endings on the local Windows clone-cache checkout (a `core.autocrlf` artifact, not a content difference — confirmed by hash match after normalization).

## Factual Accuracy

No factual inaccuracies found in the candidate's prose claims. Spot-verified against real repo files:
- "No third-party package dependencies" / CMake 3.26+ / C++17 / Ninja — verified against `runs/.clone_cache/aspose_email_cpp/CMakeLists.txt` (`cmake_minimum_required(VERSION 3.26)`, `CMAKE_CXX_STANDARD 17`) and `CMakePresets.json` (Ninja generator, `RelWithDebInfo`, tests ON/examples OFF in the `default` preset) — exact match to readme.md:116-121.
- "Three test executables ... `aspose_email_foss_cfb_tests`, `aspose_email_foss_msg_tests`, `aspose_email_foss_public_tests`" (readme.md:461-465) — verified against `tests/CMakeLists.txt` (three `add_executable`/`add_test` pairs with exactly those names).
- "26 public types" (readme.md:430) — verified by counting `##` headings in `knowledge/email/cpp/merged/api_surface.md` = 26, matching `model.yaml:19` `class_count: 26`, and matching the candidate's own table (18 classes + 2 structs + 6 enumerations = 26).
- CFB/MSG/EML import+export support claims — consistent with `knowledge/email/cpp/merged/formats.md` and `formats.json`.
- `upstream-issues.md:7-24` documents one pre-existing, correctly-identified, and correctly-NOT-repeated upstream inconsistency (old README's stale `cpp/`-prefixed examples path); independently confirmed via `original_at_pin.md:73` ("Examples are available under `cpp/examples/`") vs. the real repo root having `examples/` directly (`ls runs/.clone_cache/aspose_email_cpp/`). The candidate correctly uses the un-prefixed path throughout (readme.md:172, 428-433). No other factual issues found in old README or build files — consistent with `upstream-issues.md:25-29`'s own claim, which this audit independently corroborates.

## Content-Preservation Ledger

Original headings (from `original_at_pin.md`, i.e. `git show c7252b3e...:README.md`): `# Aspose.Email FOSS for C++` (L1), `## Features` (L5), `## Build` (L16), `## Install` (L24), `## Quick Start` (L30), `## Examples` (L71).

| Original unit | Disposition (verified by re-reading candidate myself) | Ledger's own claim |
|---|---|---|
| Title (L1) | PRESERVED — readme.md:1, identical text | not tracked in structure-dispositions.json |
| Intro sentence (L3) | TRANSFORMED — reframed into readme.md:7-12 (longer, names CFB/MSG/EML explicitly, class names) | content-dispositions.json u0001, "merged_reframed" — label is directionally correct, but see Verdict finding re: excerpt field |
| `## Features` 8 bullets (L5-14) | MERGED — all 8 facts consolidated into 5 richer bullets, readme.md:58-73 (Key Capabilities); no fact dropped (verified each original bullet maps to one of the 5 new ones) | content-dispositions.json u0013-u0017 label this "merged_verbatim" — **wording is not verbatim**, see Verdict |
| `## Build` heading + code (L16-22) | PRESERVED — code block identical to readme.md:88-92 under new `### Build` subheading | code (c0003) correctly "merged_verbatim"; the heading-rename itself untracked in structure-dispositions.json |
| `## Install` heading + code (L24-28) | PRESERVED — code identical to readme.md:100-102 under new `### Install (Optional)` subheading | code (c0004) correctly "merged_verbatim"; heading-rename untracked |
| Quick Start snippet 1 (L34-46) | PRESERVED verbatim — byte-identical to readme.md:127-139 | code-example-dispositions.json c0005, correctly "merged_verbatim" |
| Quick Start snippet 2 (L50-69) | PRESERVED verbatim — byte-identical to readme.md:143-162 | c0006, correctly "merged_verbatim" |
| `## Examples` heading + 3 filenames + stale `cpp/` path (L71-77) | TRANSFORMED — renamed "Additional Examples", stale path corrected, filenames expanded into full runnable code excerpts verified against `examples/create_msg_and_eml.cpp`, `msg_reader.cpp`, `msg_summary.cpp` (all byte-identical main() bodies, confirmed directly) | Path fix explained only in upstream-issues.md; heading rename untracked in structure-dispositions.json; code correctly sourced per code-example-dispositions.json c0007a-g/c0008a-e |
| Badges | **INCORRECTLY-EXCLUDED CLAIM OF PRESERVATION** — original has **zero** badges/images anywhere in its 77 lines (confirmed: no `![` or `[!` substring exists in `original_at_pin.md`); candidate adds two shields.io badges + a banner image (readme.md:3-5), which is net-new | badge-dispositions.json:4,15 both say `"action": "preserved"` — **factually false**, see Verdict |
| No License section, no Dependencies section, no API Reference, no Documentation & Resources, no Scope and Limitations, no Development and Testing, no Navigation, no At a Glance | All net-new (7 wholly new top-level sections), each individually verified against real source (CMakeLists.txt, header files, LICENSE) | structure-dispositions.json contains exactly **one** entry (s0001, "At a Glance") for what is at least 10 heading-level structural changes (5 renames/merges + 7 net-new sections, minus overlap) |

No content was DROPPED-WITH-REASON or DROPPED-SILENTLY — every original fact has a traceable, accurate destination in the candidate. The defect is entirely in the **ledger's own bookkeeping**, not in the candidate's actual content fidelity (see Verdict).

## Usability

Strong improvement over the original. TOC (readme.md:14-27) with verified working anchors; collapsible `<details>` blocks keep the long API Reference and secondary examples scannable without bloating the primary read; Quick Start is immediately actionable with copy-paste-verified code; Build/Install/Test commands are copy-paste-ready and verified against the repo's actual CMake presets. The original had no navigation, no API reference, and no scope/limitations disclosure at all — the candidate closes all three real usability gaps. No usability defects found.

## Presentation/SEO

Single H1, clean H2/H3/H4 hierarchy (27 headings, verified via `grep -n "^#"`). Badges and banner render real, existing assets: `static/media/email/cpp/banner-readme.png`, `banner.png`, `icon.png` all found on disk. Mermaid "At a Glance" diagram is syntactically well-formed. Documentation & Resources section cross-links to `docs.aspose.org/email/cpp/`, `kb.aspose.org/email/cpp/`, `reference.aspose.org/email/cpp/`, and `products.aspose.org/email/cpp/` — all four confirmed to exist as real content directories in this monorepo (`content/docs.aspose.org/en/email/cpp`, `content/kb.aspose.org/en/email/cpp`, `content/reference.aspose.org/en/email/cpp`, `content/products.aspose.org/en/email/cpp`). GitHub issues link (readme.md:433) matches the real upstream repo path exactly. No presentation/SEO defects found; the badge-ledger inaccuracy (see Verdict) is a governance defect, not a rendering/SEO one — the badges themselves display correctly.

## Dependency Accuracy

Fully accurate, no defects. "No required third-party package dependencies" (readme.md:112) verified — no `find_package`/`FetchContent` calls for external libraries anywhere in `CMakeLists.txt` (full 101-line file read). CMake 3.26 floor, C++17 standard, Ninja generator via `CMakePresets.json`'s `default` preset — all verified verbatim against source, matching readme.md:116-121 exactly.

## Example Verification

All code examples verified byte-for-byte against real source:
- Quick Start snippet 1 (readme.md:127-139) == `examples` region of original README, both identical to the pattern used throughout the actual `mapi_message.hpp` API.
- `examples/create_msg_and_eml.cpp` lines 36-89 (its full `main()`) == readme.md:180-233 **character-for-character** (verified by direct side-by-side read).
- `examples/msg_reader.cpp` lines 186-212 (its full `main()`) == readme.md:247-273 **character-for-character**.
- `examples/msg_summary.cpp` — candidate's claim that it supports `--property-id`/`--property-type` CLI flags (readme.md:282-283) confirmed via `grep -n "property-id\|property-type" examples/msg_summary.cpp` (lines 174, 180-181 of that file).

No fabricated, stale, or non-compiling-looking example content found.

## API Accuracy

All 26 public types (18 classes, 2 structs, 6 enumerations — readme.md:300-337) verified present and correctly described against `knowledge/email/cpp/merged/api_surface.md` and the real header list under `runs/.clone_cache/aspose_email_cpp/include/aspose/email/foss/`. Spot-checked member signatures for `mapi_message`, `cfb_reader`, `msg_reader`, `msg_storage` (readme.md:345-421) against `api_surface.md:192-245, 42-63, 291-297, 299-316` — all match exactly, including method names, parameter names, and return types. The candidate does not overclaim completeness (explicitly says the curated member list "covers the essentials" and points to the full reference site for the rest). No API accuracy defects found.

## Link/Rendering

- TOC anchors verified against actual heading slugs, including the tricky ampersand case: `## Documentation & Resources` → GitHub slug `#documentation--resources` (double-hyphen, since `&` is stripped leaving two spaces) — candidate's TOC entry (readme.md:23) matches exactly.
- Relative file links — `examples/create_msg_and_eml.cpp`, `examples/msg_reader.cpp`, `examples/msg_summary.cpp`, `examples/README.md`, `PUBLIC_API.md`, `CHANGELOG.md`, `LICENSE` — all confirmed to exist in `runs/.clone_cache/aspose_email_cpp/`.
- External links (GitHub issues path, docs/kb/reference/products subdomain links, banner image path) all confirmed to resolve to real targets (see Presentation/SEO).
- No broken links found.

## Verdict

No BLOCKER-level defects. No reader-facing factual error, broken link, broken build/test command, or fabricated code example was found anywhere in the candidate or the actually-published README — the customer-facing content is accurate and a substantial improvement over the original. Every defect below is in the surrounding **evidence/governance machinery**, not in the published text itself.

1. **[MAJOR, likely systemic]** `badge-dispositions.json` fabricates provenance: both badges are labeled `"action": "preserved"` when the original README contained **zero** badges or images of any kind.
   - Evidence: `reports/repo-presenter-regen-full/email/cpp/badge-dispositions.json:4` and `:15` (`"action": "preserved"` for b0001/b0002); `git -C runs/.clone_cache/aspose_email_cpp show c7252b3e4f6bbec4bbe5e2f50f51eb2a7384eaf2:README.md` (77 lines, read in full) contains no `![` or `[!` markdown-image/badge syntax anywhere.
   - Likely systemic: this looks like a classifier defaulting all badges to "preserved" rather than distinguishing added-vs-carried-over state, a bug that would recur on any product where badges are newly introduced during refresh.

2. **[MAJOR, likely systemic]** `structure-dispositions.json` tracks only 1 of at least ~10 real heading-level structural changes.
   - Evidence: file contains exactly one array element (s0001, "At a Glance") — full file read, 14 lines. Original headings (`grep -n "^#" original_at_pin.md`): title, `## Features` (L5), `## Build` (L16), `## Install` (L24), `## Quick Start` (L30), `## Examples` (L71). Candidate headings (`grep -n "^#" readme.md`): 27 headings including renames (Features→Key Capabilities, Examples→Additional Examples), merges (Build/Install folded under new `## Installation`), and 7 wholly new top-level sections (Navigation, Dependencies, API Reference, Documentation & Resources, Scope and Limitations, Development and Testing, License) — none of these renames/merges/additions appear in structure-dispositions.json.

3. **[MAJOR, systemic]** `content-dispositions.json` and `code-example-dispositions.json` label substantially reworded/consolidated or wholly-new content as `"merged_verbatim"`, making the PRESERVED/TRANSFORMED/MERGED axis unreliable without independently reconstructing the original README (which this audit had to do).
   - Evidence: `content-dispositions.json:149,161,173,185,197` (units u0013-u0017, "merged_verbatim", target "Key Capabilities") map to the original's `## Features` 8 bullets (`original_at_pin.md:7-14`), but the candidate text (readme.md:58-73) is a reworded 5-bullet consolidation, not verbatim text, e.g. original "Read CFB containers from file paths, streams, and in-memory byte buffers" vs. candidate "Low-level CFB access — read, build, and write generic Compound File Binary containers directly through `cfb_reader`, `cfb_storage`/`cfb_stream`, and `cfb_writer`..." (readme.md:58-60). Similarly `code-example-dispositions.json:14` (c0002, target "Installation") is labeled "merged_verbatim" for a CMake integration snippet (readme.md:81-84) that has **no counterpart at all** in the original's Install section.

4. **[MAJOR, systemic]** For "merged_reframed" content units, the ledger's `excerpt` field stores the candidate's **post-transformation** text, not the original's pre-transformation text — defeating the stated purpose of preserving original-content evidence.
   - Evidence: `content-dispositions.json:4` (u0001 excerpt) is character-for-character identical to `readme.md:7-12`; the actual original text at the pinned SHA (`original_at_pin.md:3`) reads "Aspose.Email FOSS for C++ is a dependency-free C++17 library for deterministic binary email container and message processing without external runtime dependencies." — a completely different, much shorter sentence that appears nowhere in the disposition file.

5. **[MAJOR, product-specific but plausibly systemic for any pre-tracking-era push]** A real, non-dry-run publication to the actual upstream GitHub repo occurred but is absent from both canonical publication-tracking files.
   - Evidence: `gh api repos/aspose-email-foss/Aspose.Email-FOSS-for-Cpp/commits --jq '...'` shows commit `fef9c934c3` (2026-08-15T07:27:23Z, "docs: refresh README with verified content, structure, and examples", author Babar Raza, co-authored by Claude Sonnet 5) live on `origin/master`. `data/readme_published_state.json` (17 lines, read in full) and `reports/repo_presenter_actions.jsonl` (2 lines, read in full) contain no "email" entry. Consequence: per `readme_published_state.json:2`'s own stated purpose, the audit-portfolio's advisory `published_readme_current` drift check will never fire for this already-live product if it diverges from the candidate in the future, since the check depends on this file listing it.

6. **[NIT, not a content defect]** A naive byte-level `diff` between the clone-cache README and the candidate falsely reports 100% of lines as changed (954-line diff for a 476-line file) due to CRLF-vs-LF line endings on the local Windows checkout — not an actual content discrepancy. Confirmed by hash match after CRLF normalization (`sha256sum` of both = `a092d3c0a0bb75796a9064f9abb4194362b6562ca9e0acb2affe921c8adf4f05`). Worth flagging only as a methodology gotcha for future auditors comparing clone-cache files on Windows.

All independent verification is complete. Here is the Stage B section.

## Stage B: Source Cross-Check

All claims below were independently re-derived by reading the cited source myself — not by re-citing Stage A's evidence pointers.

### Identity (spot-check of the foundational hashes everything else depends on)

1. **Clone-cache HEAD / README state** — CONFIRMED. `git -C runs/.clone_cache/aspose_email_cpp log --oneline -3` → `fef9c934c3ad7a207c97cc24546176e678f577af docs: refresh README...` / `c7252b3e4f6bbec4bbe5e2f50f51eb2a7384eaf2 Add license` / `82c496d Initial public release`. `wc -l` + `sha256sum runs/.clone_cache/aspose_email_cpp/README.md` → `476` lines, `24cadf31716b7d3471dbb83f0bd63f408a8432074e38059088ac0acf45a58329`.
2. **Candidate hash** — CONFIRMED. `wc -c reports/repo-presenter-regen-full/email/cpp/readme.md` → `24148`; `sha256sum` → `a092d3c0a0bb75796a9064f9abb4194362b6562ca9e0acb2affe921c8adf4f05`.
3. **Published (live GitHub)** — CONFIRMED. `gh api repos/aspose-email-foss/Aspose.Email-FOSS-for-Cpp/contents/README.md --jq '.sha, .size'` → `1207c6779c05e9caace33ab0181c4425476295c5`, `24148`; piping `.content` through `base64 -d | sha256sum` → `a092d3c0a0bb75796a9064f9abb4194362b6562ca9e0acb2affe921c8adf4f05`. Matches the candidate exactly.
4. **`last-verified.json` cross-check** — CONFIRMED. `reports/repo-presenter-regen-full/email/cpp/last-verified.json:2` records `"readme_sha256": "a092d3c0a0bb75796a9064f9abb4194362b6562ca9e0acb2affe921c8adf4f05"`, matching my own `sha256sum` of `readme.md` byte-for-byte.

### Factual Accuracy / Dependency Accuracy

5. **CMake 3.26+, C++17, no third-party deps** — CONFIRMED, and pushed further than Stage A's check. `runs/.clone_cache/aspose_email_cpp/CMakeLists.txt:1` = `cmake_minimum_required(VERSION 3.26)`; `:9-11` = `CMAKE_CXX_STANDARD 17` / `CMAKE_CXX_STANDARD_REQUIRED ON`. `grep -c "find_package\|FetchContent" CMakeLists.txt` → `0`. I additionally grepped every `#include <...>` across `src/` (12 files) for anything besides standard-library headers: the only non-trivial ones are `<unordered_set>`, `<deque>`, `<codecvt>`, `<iterator>`, `<locale>`, `<istream>`, `<regex>` — all standard library, zero vendored or third-party headers found anywhere in the implementation.
6. **Ninja / RelWithDebInfo / tests ON, examples OFF in `default` preset** — CONFIRMED. `CMakePresets.json:12,15-17`: `"generator": "Ninja"`, `"CMAKE_BUILD_TYPE": "RelWithDebInfo"`, `"ASPOSE_EMAIL_FOSS_BUILD_TESTS": "ON"`, `"ASPOSE_EMAIL_FOSS_BUILD_EXAMPLES": "OFF"`.
7. **Three named test executables** — CONFIRMED. `runs/.clone_cache/aspose_email_cpp/tests/CMakeLists.txt` lines 1,12,23: `add_executable(aspose_email_foss_cfb_tests ...)`, `add_executable(aspose_email_foss_public_tests ...)`, `add_executable(aspose_email_foss_msg_tests ...)`, each with a matching `add_test`.
8. **MIT license** — CONFIRMED. `runs/.clone_cache/aspose_email_cpp/LICENSE:1` = `MIT License`.
9. **CFB/MSG/EML import+export** — CONFIRMED via `knowledge/email/cpp/merged/formats.md` (table: CFB/EML/MSG all `Yes`/`Yes`) and independently via `knowledge/email/cpp/merged/formats.json` (7 entries: cfb import + cfb export, msg import + msg export, eml import + eml export ×2, all in real header paths under `include/aspose/email/foss/`).
10. **NuGet not-yet-published claim (readme.md:77)** — CONFIRMED, an unflagged cross-check Stage A didn't cite. `data/package_registry.json`'s `cpp` entry: `"registry_type": "nuget"`, `"published": false`, evidence note "no live match found for any tried candidate ... recorded as not-yet-published" — directly consistent with the candidate's own Installation-section text, "No NuGet package has been published for this library yet."

### API Accuracy

11. **26 public types (18 classes + 2 structs + 6 enumerations)** — CONFIRMED by direct count of `##` headings in `knowledge/email/cpp/merged/api_surface.md` (26 total: 18 classes, `directory_entry`+`header` structs, 6 enums), and `model.yaml:19` → `class_count: 26`.
12. **`mapi_message` member list (readme.md:345-362)** — CONFIRMED line-for-line against `api_surface.md:194-237` (`create`, `from_file`/`from_stream`, `load_from_eml`×2, accessor pairs, `recipients()`/`attachments()`, `add_recipient`, `add_attachment` (byte/stream overloads), `add_embedded_message_attachment`, `set_property`/`get_property_value`, `validation_issues`, `save`×3, `save_to_eml`×3, `to_msg_document`) — every signature matches exactly, no omissions or additions.
13. **`cfb_reader` member list (readme.md:384-394)** — CONFIRMED against `api_surface.md:44-63`: `from_file`/`from_stream`/`from_bytes`/`from_buffer`, `header()`, `directory_entries()`, `root_entry()`, `get_entry`, `get_stream_data`, `storage_ids`/`stream_ids`, `child_ids`, `find_child_by_name`, `resolve_path` — exact match.
14. **`msg_reader` member list (readme.md:366-368)** — CONFIRMED against `api_surface.md:293-297`: `from_file(path, strict)`/`from_stream(stream, strict)`, `cfb() -> cfb::cfb_reader`, `validation_issues()`.
15. **`msg_storage` member list (readme.md:376-380)** — CONFIRMED against `api_surface.md:301-315`: `add_stream`/`add_storage`/`find_stream`/`find_storage` and properties `streams`, `storages`, `role`.

### Example Verification

16. **`examples/create_msg_and_eml.cpp` `main()` (lines 36-89)** — Read the full file myself; its `main()` body is character-for-character identical to `readme.md:180-233`. CONFIRMED.
17. **`examples/msg_reader.cpp` `main()` (lines 186-212)** — Read directly; identical to `readme.md:246-274` (`msg_reader::from_file`, `msg_document::from_reader`, `build_dump`, `--out` handling). CONFIRMED.
18. **`examples/msg_summary.cpp` `--property-id`/`--property-type` flags** — CONFIRMED. `grep -n "property-id\|property-type" examples/msg_summary.cpp` → line 174 (usage string) and lines 180-181 (`read_option(argc, argv, "--property-id")` / `"--property-type"`).

### Original-README re-derivation (independent fetch, not reused from Stage A)

19. Ran `git -C runs/.clone_cache/aspose_email_cpp show c7252b3e4f6bbec4bbe5e2f50f51eb2a7384eaf2:README.md` myself and read all 77 lines. Confirms, independently: **zero** `![`/`[!` badge or image syntax anywhere (supports MAJOR finding #1 on `badge-dispositions.json`); the intro sentence at line 3 reads exactly "Aspose.Email FOSS for C++ is a dependency-free C++17 library for deterministic binary email container and message processing without external runtime dependencies." — verbatim match to the text `content-dispositions.json:4` claims as an "excerpt" of the original, when it is actually the candidate's post-rewrite text (supports MAJOR finding #4); the `## Features` section has exactly 8 bullets (lines 7-14) which the candidate compresses into 5 "Key Capabilities" bullets with substantially reworded prose (supports MAJOR finding #3); and the stale `cpp/examples/` path claim at line 73, versus the real repo root's `examples/` directory confirmed directly via my own `ls runs/.clone_cache/aspose_email_cpp/` (no `cpp/` subdirectory present).
20. **Build/Install/Quick-Start code blocks preserved verbatim** — CONFIRMED by direct byte-level comparison of my own read of the original (lines 18-21, 26-27, 34-46, 50-69) against the candidate (readme.md:88-91, 100-101, 127-139, 143-162): all four blocks are character-for-character identical.

### Ledger cross-check (independent read of the JSON files themselves)

21. **`badge-dispositions.json`** — CONFIRMED both `b0001` and `b0002` carry `"action": "preserved"` (lines 4 and 15), against an original with zero badges (see #19). This is a direct read, not a re-citation.
22. **`structure-dispositions.json`** — CONFIRMED the file contains exactly one array element (`s0001`, "At a Glance"), while the candidate has 27 real headings (independently counted via `grep -n "^#"` on readme.md, filtering out `#include` lines) against the original's 6.
23. **`content-dispositions.json` u0013-u0017** — CONFIRMED all five are labeled `"merged_verbatim"` for target "Key Capabilities" (lines 149,161,173,185,197), yet their `excerpt` text is a 5-bullet rewrite, not the original's 8 verbatim bullets.
24. **`code-example-dispositions.json` c0002** — CONFIRMED labeled `"merged_verbatim"` for the "Installation" section's CMake-integration snippet (`add_subdirectory`/`target_link_libraries`, readme.md:81-84), which — per my own read of the original's `## Install` section (lines 24-28) — has no counterpart at all in the original.

### Publication-tracking gap (independently re-pulled, not reused)

25. **Live upstream commit** — CONFIRMED via my own `gh api repos/aspose-email-foss/Aspose.Email-FOSS-for-Cpp/commits --jq ...` call: commit `fef9c934c3ad7a207c97cc24546176e678f577af`, dated `2026-08-15T07:27:23Z`, message "docs: refresh README with verified content, structure, and examples", author Babar Raza, co-authored by Claude Sonnet 5 — live on `origin/master`.
26. **Absence from tracking files** — CONFIRMED. Read `data/readme_published_state.json` in full (11 product entries: 3d×4, note/python, pdf/cpp, cells×3, slides/cpp, words/net) — no `email` entry. Read `reports/repo_presenter_actions.jsonl` in full (2 lines: `note/python` and `cells/rust`) — no `email` entry either.

### Overall

Every claim in Stage A's Factual Accuracy, Dependency Accuracy, and API Accuracy sections is **CONFIRMED** by my own independent reads and commands — no REFUTED or UNVERIFIABLE findings. My own scan for unflagged high-risk claims (NuGet-publication status against `package_registry.json`, third-party-dependency check widened to all `#include` statements in `src/`, independent original-README fetch, direct reads of all four disposition-ledger JSON files rather than trusting Stage A's line citations) turned up nothing Stage A missed or mischaracterized — it corroborates all six numbered VERDICT findings from Stage A with independently-obtained evidence.

## Stage C: Adversarial Verification

1. **Badge fabrication (badge-dispositions.json)** — **CONFIRMED** (and the "likely systemic" hedge is now provably an understatement). Independently re-fetched the pinned original via `git show c7252b3e...:README.md` (77 lines, sha256 `40a0d44e...` — exact match) and confirmed zero `![`/`[!` occurrences. Read `badge-dispositions.json` directly: b0001/b0002 both `"action": "preserved"`. Went further than the review by reading the actual enforcement code (`readme_refresh_checks.py:8190-8255`, `check_badge_disposition_coverage`): its own docstring states it **"vacuously pass[es] `[]` when `old_badges` is empty"** — i.e., the hard gate that exists specifically to police this is documented to skip validation entirely in the exact zero-old-badges scenario this product hit. That's not "likely" a classifier default, it's a proven, named blind spot in the gate itself.

2. **structure-dispositions.json undercount (only 1 of ~10 structural changes)** — **CONFIRMED**, severity understated. Independently counted 27 candidate headings vs. 6 original (matches review). Went further: ran the repo's own `extract_old_readme_structural_units` against the true original (via stdin, not a shared temp file) — it finds exactly 2 real structural units (`s0001`="Build", `s0002`="Install"). Running the actual hard gate `check_structural_unit_disposition_coverage(sunits, sdisp)` produces a live failure: `s0002` has no disposition entry at all. Worse, the file's one entry, `s0001`, doesn't even describe the real `s0001` ("Build") — its `heading` field says `"At a Glance"`, a section invented for the candidate that never existed in the original. This is a live hard-gate failure plus a fabricated old-heading, not merely an incomplete ledger.

3. **"merged_verbatim" mislabeling of reworded/new content** — **CONFIRMED**, severity understated. Independently re-read u0013-u0017 and c0002 verbatim — matches the review's quotes exactly. Went further: ran the actual hard gates. `check_content_unit_disposition_coverage` returns **89 of 104** entries as referencing unit_ids absent from a live re-extraction of the true original (only u0001-u0015 exist for real). `check_content_unit_excerpt_matches_extraction` flags **15 of 15** entries that do resolve as excerpt mismatches. Root cause found: the file's id order (u0002-u0012 = the candidate's 11 Navigation bullets, u0013-u0017 = its 5 Key Capabilities bullets, etc.) tracks the **candidate's own section order**, not the old README's — so "merged_verbatim" isn't scattered mislabeling, it's a uniformly wrong schema applied file-wide. Same pattern independently confirmed in `code-example-dispositions.json` (real old code units are c0001=Build/c0002=Install/c0003-4=Quick Start; the file instead routes c0001→"At a Glance", c0002-4→"Installation", none matching their real content).

4. **Excerpt field stores post-transformation text** — **CONFIRMED**, scope understated. Review demonstrated this only for u0001; my mechanical re-run of `check_content_unit_excerpt_matches_extraction` shows **all 15** resolvable content units fail this exact way (100%, not one cherry-picked instance), consistent with finding 3's root cause — the whole file was built from the candidate's content, never the original's.

5. **Publication-tracking gap** — **CONFIRMED** exactly as stated. Independently re-ran `gh api .../commits/fef9c934c3...` — got identical date (`2026-08-15T07:27:23Z`), author (Babar Raza), message, and Claude Sonnet 5 co-author line. Independently `grep -n "email"` on both `data/readme_published_state.json` and `reports/repo_presenter_actions.jsonl` — zero matches (exit 1) in both, confirming the omission. Read the tracking file's own header comment, which confirms the causal mechanism claimed (the `published_readme_current` advisory check depends on this file listing the product). Tag ("product-specific but plausibly systemic") is fair, not overstated.

6. **CRLF naive-diff nit** — **CONFIRMED** exactly. Independently reproduced every number: clone-cache file 476 lines/24624 bytes/CRLF present (`od -c` shows `\r\n`)/raw sha256 `24cadf31...`; normalized sha256 and candidate sha256 both `a092d3c0...`; naive `diff` line count = exactly 954. Correctly scoped as NIT/methodology note, not a real content defect.

**Caveat on method**: two of my own verification runs were transiently corrupted by a concurrent sibling session overwriting a same-named file in the shared OS `/tmp` and in this task's (apparently shared, not session-isolated in practice) scratchpad directory with a different product's (email/net) README content — caught via a sha256 mismatch, discarded, and redone by piping `git show` directly into the check functions via stdin with no intermediate file. All findings above reflect only the clean, sha256-verified stdin runs.