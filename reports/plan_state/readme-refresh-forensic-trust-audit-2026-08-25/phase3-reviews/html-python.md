## Identity

Four distinct artifacts were sought; all four were obtained.

| Artifact | Obtained? | Path / Source | SHA-256 (raw bytes) |
|---|---|---|---|
| Original-at-generation-time README | Yes | `git -C runs/.clone_cache/aspose_html_python show c2356ec:README.md` (repo_sha `c2356ec872fd7d64c14a0ae8cc043eea1a03847e`, cited by `upstream-issues.md` and `model.yaml`) | not separately hashed; 86 lines, content quoted in full below |
| Current live upstream (clone cache HEAD) | Yes | `runs/.clone_cache/aspose_html_python/README.md`, HEAD = `912f0ae078b5418226a51de08539bc591547682e` (2026-08-16 18:12:43 +0500) | `212725feb27b0169b3669b6cd5e020f4d172f01d6f6b76bb4e18c768ac2e197f` (raw, CRLF); `56b1ca26647b602d903c9a4510ef9b1cb828eecbcbbd6ccdb90cb985c1d9529c` after CRLF→LF normalization |
| Candidate | Yes | `reports/repo-presenter-regen-full/html/python/readme.md` | `2130ce2e4a26c4f1328153427e309ca2c695fd3a755b0deeb55f91710a81ce08` — matches `last-verified.json`'s `readme_sha256` field exactly |
| Actually-published (real GitHub) | Yes | `gh api repos/aspose-html-foss/Aspose.HTML-FOSS-for-Python/contents/README.md --jq .content` → base64-decoded to raw bytes | `56b1ca26647b602d903c9a4510ef9b1cb828eecbcbbd6ccdb90cb985c1d9529c` (raw, LF) — **identical** to clone-cache HEAD after line-ending normalization |

Note on method: my first `gh api` fetch piped the base64 output through Python's `print()` on Windows, which silently re-encoded em-dash characters (UTF-8 `E2 80 94`) into CP1252 byte `0x97`, producing a false "mojibake" signal. Re-fetched by decoding base64 straight to a binary file (no text-mode step) and confirmed the real published content uses correct UTF-8 em-dashes (40 occurrences, 0 corrupted). This is flagged in the Verdict as a note about my own tooling, not a product defect — but it is exactly the kind of self-inflicted false positive this audit format is meant to catch before it's reported as a finding.

## Factual Accuracy

Spot-checked every load-bearing factual claim in the candidate against `runs/.clone_cache/aspose_html_python/pyproject.toml` and source:

- `requires-python = ">=3.10"` — matches candidate's "requires Python 3.10 or later" (Installation, Dependencies).
- `dependencies = ["skia-python>=87.0,<145"]` — matches candidate exactly (Installation, Dependencies).
- `[project.optional-dependencies] js = ["quickjs>=1.19,<2"]` — matches candidate exactly.
- `[project.optional-dependencies] test = ["pytest>=8"]` — matches candidate's "`pytest` >=8" (Dependencies, Development and Testing).
- `[tool.pytest.ini_options] pythonpath = ["src"]` — matches candidate's Installation/Development-and-Testing narrative about the test suite already pointing at `src/`.
- `[build-system] build-backend = "setuptools.backends.legacy:build"` — confirmed still broken (no such module in any setuptools release); candidate correctly never tells the user to `pip install aspose-html-foss` and instead documents the real working source-checkout + `PYTHONPATH` path. This is a genuine, disclosed fix versus the pre-refresh original, whose `## Installation` section was `pip install aspose-html-foss` — a command that would fail today given the broken build backend (original: `git -C runs/.clone_cache/aspose_html_python show c2356ec:README.md`, `## Installation` block).
- "The library exposes 243 public types in total" (readme.md:213) — **factually false**. See Content-Preservation Ledger / Verdict Finding 2: source has 244 public class definitions; the candidate's own table lists 243.
- `examples/` directory referenced by the (unpublished) new "Runnable examples" line and by the pre-existing "Runnable scripts are available in the `examples` directory" sentence — confirmed to exist and contain `parse_and_update.py`, `url_search_params.py` (`ls runs/.clone_cache/aspose_html_python/examples/`).
- `PUBLIC_API.md`, `CONTRIBUTING.md`, `SECURITY.md`, `CHANGELOG.md`, `LICENSE` — all confirmed to exist in the clone cache.

## Content-Preservation Ledger

Original README (86 lines, `git show c2356ec:README.md`) mapped against the candidate:

| Original unit | Disposition | Notes / evidence |
|---|---|---|
| `# Aspose.HTML FOSS for Python` (title) | PRESERVED | candidate line 1, verbatim |
| Intro (2 sentences: "open-source Python toolkit for working with HTML documents..." / "focused on practical HTML parsing...") | TRANSFORMED | Candidate line 7 is a materially more precise, source-grounded rewrite (mentions `HTMLDocument`/`Document`/`Element`, CSSOM, `URL`/`URLSearchParams`, QuickJS bridge). `content-dispositions.json` u0001 claims this, target "Intro" — target holds (readme.md:7) |
| `## Features` (7 bullets) | TRANSFORMED/MERGED → `## Key Capabilities` (7 bullets) | Substance preserved and sharpened with real method/class names; verified target section holds (readme.md:56-64) against `content-dispositions.json` u0013-u0019 |
| `## Installation` (`pip install aspose-html-foss`) | TRANSFORMED (correctly) | Replaced with real working source-checkout method; disclosed in `upstream-issues.md` as fixing a BLOCKING upstream defect (broken `pip install` for every install path) |
| `## Quick Start` code example | TRANSFORMED | Original's inline multi-line HTML string replaced with a leaner document; the parse/create_element/append_child/serialise flow preserved. A brand-new second example (CSSStyleSheet/computed style) is MERGED in as net-new content, not from original |
| `## Package Entry Points` (8 bullets) | MERGED/EXPANDED → `## API Reference` | Original's flat 8-item list is superseded by the full 243-row typed table + Detailed Member Reference; strictly a superset in substance |
| `## Compatibility` → "Main supported scenarios" (7 bullets) | MERGED | Distributed across Key Capabilities / API Reference; no distinct loss found |
| `## Compatibility` → "API layers" (5 bullets) | MERGED | Same as above |
| `## Compatibility` → "For the stable API summary, see PUBLIC_API.md" | PRESERVED | Candidate: "**[Public API surface](PUBLIC_API.md)**" (readme.md:567) |
| `## Compatibility` → "For runnable scenarios, see examples" | PRESERVED | Candidate: "Runnable scripts are available in the `examples` directory." (readme.md:146) |
| `### Parse And Read HTML` (example) | MERGED/RENAMED → `### Query Elements By Tag Name` | Nearly identical code (`get_elements_by_tag_name("h1").item(0)`); `structure-dispositions.json` s0002 records this as new content rather than a rename-from-original — see Verdict Finding 4 |
| `### Create DOM Nodes` (example) | DROPPED-SILENTLY (as a distinct heading) | Its substance (create_element/append_child/serialise) is folded into the new Quick Start second half, but no disposition file records this heading's fate at all — not in `structure-dispositions.json`'s 4 entries |
| `### Work With URLs` (example) | PRESERVED/RENAMED → `### Work With URLs and Search Parameters` | Content essentially identical; **not tracked** in `structure-dispositions.json` (only 4 entries exist, this isn't one) — see Verdict Finding 4 |
| `## Links` → Repository link | DROPPED-SILENTLY (as standalone list item) | Substance survives implicitly via badges/banner links at top of candidate, but the explicit "Repository:" bullet has no disposition record |
| `## Links` → Issues link | PRESERVED | Candidate: "Found a bug or have a feature request? [Open an issue](...)" (readme.md:572) |
| `## Links` → PyPI link | DROPPED-WITH-REASON | Correctly dropped since no PyPI package exists yet (`upstream-issues.md`); consistent with candidate's Installation section |
| `## Development` (See CONTRIBUTING.md) | PRESERVED | readme.md:569 |
| `## Security` (See SECURITY.md) | PRESERVED | readme.md:570 |
| `## Changelog` (See CHANGELOG.md) | PRESERVED | readme.md:571 |
| *(no original counterpart)* | net-new: `## Dependencies`, `## Scope and Limitations`, `## License`, `## At a Glance` diagram, 3 new Additional-Examples subsections | All independently `verified_against_source` per disposition JSONs; spot-checks (below) confirm accuracy |

**Disposition-file self-report vs. reality**: I independently re-derived the original README (`git show c2356ec:README.md`) to check the task's claim that disposition JSON "excerpt" fields embed original-README content. They do not — every excerpt I compared (e.g. `content-dispositions.json` u0013) is verbatim candidate (destination) text, not original (source) text. See Verdict Finding 3.

## Usability

- Navigation TOC (readme.md:9-21) lists 11 anchors; all 11 corresponding `##` headings exist in the candidate with matching slugs — confirmed by direct read of readme.md.
- Installation → Quick Start → Additional Examples → API Reference → Documentation & Resources → Scope and Limitations → Development and Testing → License is a coherent, logical order; no orphaned or out-of-order sections found.
- The `<details>` collapsible blocks (Additional Examples, API Reference) are both correctly opened and closed (`<details>`/`</details>` pairs at readme.md:159/209 and 215/560 — verified balanced by direct read).
- One usability gap: the "Runnable examples" documentation link (readme.md:568) is present in the local candidate but **absent from what a user actually sees on GitHub today** (see Identity / Verdict Finding 1) — this is a currency gap, not an authoring defect in the candidate itself.

## Presentation/SEO

- Single H1, proper heading hierarchy (H1 → H2 → H3), no skipped levels — confirmed by direct read of readme.md.
- Badges (License, Contributors) and banner image render at the top before any prose, standard GitHub README convention — readme.md:3-5.
- Intro paragraph (readme.md:7) is a dense, keyword-rich one-paragraph summary suitable for GitHub's social-preview/description scraping — reasonable.
- Mermaid diagram (readme.md:25-54) is well-formed (`flowchart TD`, balanced `subgraph`/`end` pairs — 5 subgraphs, 5 `end`s, verified by direct read) and renders on GitHub natively.

## Dependency Accuracy

All dependency claims independently verified against `runs/.clone_cache/aspose_html_python/pyproject.toml` (read in full above):

- `skia-python>=87.0,<145` required — exact match (candidate readme.md:75,93; pyproject.toml:28).
- `quickjs>=1.19,<2` optional, `js` extra — exact match (candidate readme.md:86,97; pyproject.toml:32).
- `pytest>=8` dev/test dependency — exact match (candidate readme.md:105,591; pyproject.toml:33).
- Python `>=3.10` — exact match (candidate readme.md:82,101; pyproject.toml:10).
- No undisclosed dependencies found in `pyproject.toml` that are missing from the candidate's Dependencies section.

## Example Verification

Every code example's API surface was checked against real source signatures (not merely against the disposition JSON's self-report):

| Example (readme.md section) | API called | Verified against | Result |
|---|---|---|---|
| Quick Start #1 | `HTMLDocument.parse()`, `Document.get_element_by_id()`, `Document.create_element()`, `Node.append_child()`, `serialise()` | `html_document.py:39` (`parse`), `_document.py:2374` (`get_element_by_id`), `_document.py:1661` (`create_element`), `_node.py:708` (`append_child`) | Signatures match |
| Quick Start #2 | `Document()`, `Element.set_attribute()`, `CSSStyleSheet()`, `replace_sync()`, `Document.attach_style_sheet()`, `Element.get_computed_style()`, `get_property_value()` | `_stylesheet.py:10,295` (`CSSStyleSheet`/`replace_sync`), `_document.py:1056` (`attach_style_sheet`), `_element.py:209` (`get_computed_style`), `_declarations.py:176`/`_cascade.py:399` (`get_property_value`) | Signatures match |
| Work With URLs and Search Parameters | `URL()`, `url.search_params.set()` | `url/_url.py` (class exists, referenced consistently across disposition + candidate) | Consistent, not independently re-verified line-by-line given scope |
| Query Elements By Tag Name | `HTMLDocument.parse()`, `get_elements_by_tag_name().item(0)` | `_document.py:2395` (`get_elements_by_tag_name`) | Signature matches |
| Detect Character Encoding From Bytes | `detect_encoding()` | `encoding/detection.py:47` | Signature matches |
| Execute JavaScript Against The DOM | `JSContext(document)`, context manager (`__enter__`/`__exit__`), `evaluate()` | `_quickjs_bridge.py:205,465,516,530` | Signature and context-manager protocol match |
| Drive The Tokenizer Directly | `Tokenizer(text)`, `.tokenize()` | `tokenizer/_tokenizer.py:44,153` | Signature matches |

No broken or hallucinated API call found in any of the 7 code examples.

## API Accuracy

- The candidate's API Reference tables list 243 unique class names (mechanically extracted and de-duplicated from `readme.md`'s `## API Reference` section — 243 rows, 0 duplicates).
- `knowledge/html/python/merged/api_surface.json` records 244 `class_definition` entries total (234 `visibility: "public"` + 4 `"exported"` + 6 `"conventional"` = 244), plus 48 top-level functions.
- Set-difference: exactly one class — **`IDSelector`** (`src/aspose_html/css/_ast.py:53`, `visibility: "public"`, a frozen dataclass identical in shape to `ClassSelector`/`TypeSelector`/`AttributeSelector`, which *are* listed) — exists in the source/knowledge extraction but is **absent from every table in the candidate's API Reference section**. No disposition file (`content-dispositions.json`, `structure-dispositions.json`, `badge-dispositions.json`, `code-example-dispositions.json`) records any drop, exclusion, or reason for `IDSelector`.
- This directly falsifies the candidate's own claim (readme.md:213, `content-dispositions.json` u0032, marked `"verified_against_source"`) that "The library exposes 243 public types in total, listed below by module."
- All other spot-checked class descriptions (HTMLDocument, CSS selector classes, CSSOM rule classes, DOM abort/event classes, Tokenizer classes) match real docstrings in source, confirming the extraction pipeline itself is generally sound — the gap is a single-row omission downstream of extraction.

## Link/Rendering

- All 10 anchor links in the Navigation TOC resolve to real headings in the same document (verified by direct text match of slug ↔ heading).
- `LICENSE`, `PUBLIC_API.md`, `CONTRIBUTING.md`, `SECURITY.md`, `CHANGELOG.md`, `examples/` — all confirmed to exist in `runs/.clone_cache/aspose_html_python/` (directory listing above).
- External links (`docs.aspose.org/html/python/`, `kb.aspose.org/html/python/`, `reference.aspose.org/html/python/`, GitHub issues URL, `products.aspose.com/html/python-net/`) were not live-fetched (out of scope / no explicit instruction to do so) — noted as unverified rather than assumed good.
- Mermaid diagram: balanced `subgraph`/`end` blocks, valid `flowchart TD` syntax by direct inspection — no rendering-breaking syntax found.
- No literal `\r\n` vs `\n` corruption exists in either the candidate or the actually-published GitHub content once correctly decoded (my own first-pass fetch artifact is documented in Identity, not a real defect — see Verdict).

## Verdict

**Finding 1 — MAJOR — likely SYSTEMIC (tracking-ledger gap, not this product's content).**
The candidate's lineage was already pushed to the real upstream repo (commit `912f0ae`, "fix(readme): production-grade README refresh (#2)", authored by Babar Raza <babar.raza@aspose.com>, 2026-08-16 18:12:43 +0500), and the local candidate has since drifted one line ahead of what's actually live — yet this entire publication history is invisible to `data/readme_published_state.json`, whose own header comment says it exists specifically so "republication pending" can be "mechanically re-derived instead of remembered," and to `reports/repo_presenter_actions.jsonl`.
- Evidence: `cd runs/.clone_cache/aspose_html_python && git log --oneline -- README.md` → `912f0ae fix(readme): production-grade README refresh (#2)` / `c2356ec Add sanitized public Aspose.HTML FOSS snapshot`.
- Evidence: `gh api repos/aspose-html-foss/Aspose.HTML-FOSS-for-Python/contents/README.md --jq .content` decoded to raw bytes → sha256 `56b1ca26647b602d903c9a4510ef9b1cb828eecbcbbd6ccdb90cb985c1d9529c`, byte-identical (after CRLF→LF normalization) to `runs/.clone_cache/aspose_html_python/README.md` at HEAD `912f0ae` (same sha256 after normalization) — proves the local clone-cache commit really is what's live on GitHub today.
- Evidence: `data/readme_published_state.json` lines 4-16 — 11 `products` entries, none for `family: "html"`/`platform: "python"`.
- Evidence: `reports/repo_presenter_actions.jsonl` — 2 total lines, neither for html/python.
- Evidence: `diff` of the correctly-decoded live README against `reports/repo-presenter-regen-full/html/python/readme.md` → single hunk: `567a568 > - **[Runnable examples](examples/)** — real, scenario-focused scripts beyond Quick Start.`
- Systemic because: the ledger is explicitly "seeded... from the authoritative plan's own recorded PR/merge history" (a manual/plan-driven process) rather than derived from git/GitHub state, so any publication that happens outside that tracked process — as this one apparently did — will silently fail to register, on any product.

**Finding 2 — MAJOR — product-specific (this candidate's table-curation step), but the underlying failure mode (a table-population/dedup step silently dropping one otherwise-qualifying row) is plausible on any product whose API surface goes through the same curation.**
`IDSelector` (`src/aspose_html/css/_ast.py:53`, `visibility: "public"` in `knowledge/html/python/merged/api_surface.json`) is a real, public, dataclass CSS selector class of the same shape as `ClassSelector`/`TypeSelector`/`AttributeSelector` — which *are* included — yet it does not appear anywhere in the candidate's API Reference tables, and no disposition file records excluding it. This makes the candidate's own claim "The library exposes 243 public types in total" (readme.md:213) false: the real public-class count is 244.
- Evidence: `.venv/Scripts/python` set-difference of `knowledge/html/python/merged/api_surface.json` class names (244 `class_definition` entries) against the 243 unique backtick-quoted class rows mechanically extracted from `reports/repo-presenter-regen-full/html/python/readme.md`'s `## API Reference` section → `in api_surface but NOT in readme table: ['IDSelector']`; reverse direction empty.
- Evidence: `IDSelector` source at `runs/.clone_cache/aspose_html_python/src/aspose_html/css/_ast.py:53` (`class IDSelector:` … `"""Matches elements whose id attribute equals id_value: \`\`#main\`\`."""`).

**Finding 3 — MINOR — SYSTEMIC (disposition-ledger design, not html/python-specific).**
`content-dispositions.json`'s "excerpt" fields do not contain original-README text as the audit task's own framing assumes ("may embed excerpts of the ORIGINAL README content used at generation time") — every excerpt sampled is verbatim candidate (destination) text.
- Evidence: `content-dispositions.json` u0013 excerpt = "Parse HTML strings, bytes, fragments, and files into a DOM document with `HTMLDocument.parse()`, `HTMLDocument.parse_fragment()`, and `HTMLDocument.load()`; the lower-level `Tokenizer` and `TreeBuilder` classes..." — this string appears verbatim at `readme.md:58`.
- Evidence: the actual original text for the same conceptual bullet, from `git -C runs/.clone_cache/aspose_html_python show c2356ec:README.md`, `## Features` section: "- Parse HTML strings, bytes, fragments, and files into a DOM document" (no backticked method names, no Tokenizer/TreeBuilder mention) — materially different text.
- Because this is a structural property of how the ledger is written (destination-text capture, not source-text capture), it will recur identically on every other product audited under S-120.

**Finding 4 — MINOR — likely SYSTEMIC (same ledger-completeness issue as Finding 3).**
`structure-dispositions.json` records only 4 heading-level units total, but the candidate contains at least 2 additional heading transitions with no tracking entry at all: `### Work With URLs and Search Parameters` (renamed/preserved from original's `### Work With Urls`) and the original's `### Create DOM Nodes` example (dropped as a standalone heading, its substance folded into the new Quick Start second example) have zero disposition-file representation.
- Evidence: `structure-dispositions.json` full contents — 4 entries (`s0001`-`s0004`): "At a Glance", "Query Elements By Tag Name", "Detect Character Encoding From Bytes", "Execute JavaScript Against The DOM".
- Evidence: original headings from `git show c2356ec:README.md`: `### Parse And Read HTML`, `### Create DOM Nodes`, `### Work With URLs` — none of the latter two's fates are recorded anywhere in any of the 4 disposition JSON files.

**Finding 5 — INFORMATIONAL — confirmed correct, not a defect.**
Re-verified `upstream-issues.md`'s BLOCKING finding (broken `pip install` due to `build-backend = "setuptools.backends.legacy:build"` in `pyproject.toml`, not a real setuptools module) directly against the live `pyproject.toml` — still true today. The candidate correctly never recommends `pip install aspose-html-foss` and instead documents the real working source-checkout + `PYTHONPATH` path, a genuine improvement over the pre-refresh original's `## Installation` (`pip install aspose-html-foss`, which would fail).
- Evidence: `runs/.clone_cache/aspose_html_python/pyproject.toml:1-3`.

**Finding 6 — NIT — my own tooling artifact, disclosed for transparency, not a product or system defect.**
My first `gh api ... | python -c "print(...)"` pipeline silently corrupted em-dash characters (UTF-8 → CP1252 byte `0x97`) via Python's console-encoding default on Windows text-mode stdout. Re-fetching by decoding base64 directly to binary confirmed the real published content is clean UTF-8. Recorded here only because it would have been a false BLOCKER finding ("mojibake in production README") had I not independently re-verified before reporting it — consistent with this repo's own standing practice of re-verifying consequential claims before acting on them.

No BLOCKER-severity defect was found in the candidate's actual content (all code examples, dependency claims, and the large majority of API descriptions check out against source). The two MAJOR findings are both about **completeness/self-consistency of the exhaustiveness claim and the tracking ledgers**, not about the candidate being actively wrong in what it does say.

Confirmed. I now have complete independent verification of every claim in scope, plus one new discrepancy in Stage A's own report. Compiling the findings section.

## Stage B: Source Cross-Check

### Factual Accuracy claims

| # | Claim | Verdict | My own evidence |
|---|---|---|---|
| 1 | `requires-python = ">=3.10"` matches candidate | CONFIRMED | `Read` on `runs/.clone_cache/aspose_html_python/pyproject.toml` line 10: `requires-python = ">=3.10"`; candidate lines 82/101 read directly. |
| 2 | `dependencies = ["skia-python>=87.0,<145"]` matches | CONFIRMED | `pyproject.toml:28` (my own `grep -n`); candidate lines 75/93 read directly. |
| 3 | `js = ["quickjs>=1.19,<2"]` matches | CONFIRMED | `pyproject.toml:32`; candidate lines 86/97. |
| 4 | `test = ["pytest>=8"]` matches | CONFIRMED | `pyproject.toml:33`; candidate lines 105/591. |
| 5 | `[tool.pytest.ini_options] pythonpath = ["src"]` matches candidate's testing narrative | CONFIRMED | `pyproject.toml:43-44` (`grep -n "pythonpath"` → `44:pythonpath = ["src"]`), directly under `[tool.pytest.ini_options]` at line 43. |
| 6 | `build-backend = "setuptools.backends.legacy:build"` references a non-existent module (broken `pip install`) | CONFIRMED — independently, at the module level, not just asserted | `pyproject.toml:3` reads `build-backend = "setuptools.backends.legacy:build"`. This repo's own `.venv` has no `setuptools` installed at all (`ModuleNotFoundError: No module named 'setuptools'`), so I went further than Stage A: I ran `.venv/Scripts/python -m pip download setuptools --no-deps -d <scratchpad>/pipdl`, which pulled the current real PyPI release (`setuptools-84.0.0-py3-none-any.whl`, fetched live 2026-08-26), and unzipped its file listing in-memory (`zipfile.ZipFile(...).namelist()`, no install). Result: 343 files total, exactly one backend-related file — `setuptools/build_meta.py`. No `setuptools/backends/` package exists anywhere in the real, current setuptools distribution. `setuptools.backends.legacy:build` is unimportable in any installable version — the candidate's decision to never recommend `pip install aspose-html-foss` is correct. |
| 7 | "The library exposes 243 public types in total" (readme.md:213) is factually false; real count is 244 | CONFIRMED — and independently re-derived, not just cross-checked | `.venv/Scripts/python` loading `knowledge/html/python/merged/api_surface.json` directly: 292 total entries, `{'class_definition': 244, 'function': 48}`; visibility breakdown of the 244 classes = `{'exported': 4, 'public': 234, 'conventional': 6}` (234+4+6=244). Independently regex-extracting every backtick-quoted class name from the candidate's own `## API Reference` section (`reports/repo-presenter-regen-full/html/python/readme.md`, between the `## API Reference` and `## Documentation & Resources` headings) yields exactly 243 unique names, breaking down as `{'public': 233, 'conventional': 6, 'exported': 4}` — i.e. every non-public-visibility class is present and exactly one `public`-visibility class is missing. Set-difference confirms it is `IDSelector` and nothing else. The false count is stated **twice**, not once as Stage A's citation implied — readme.md:213 ("The library exposes 243 public types in total") and readme.md:566 ("the complete, browsable reference for all 243 public types") both assert the wrong number. |
| 8 | `examples/` directory contains `parse_and_update.py`, `url_search_params.py` | CONFIRMED | `ls -la runs/.clone_cache/aspose_html_python/examples/` → exactly those two files, no others. |
| 9 | `PUBLIC_API.md`, `CONTRIBUTING.md`, `SECURITY.md`, `CHANGELOG.md`, `LICENSE` exist | CONFIRMED | Direct `ls` on all five paths under `runs/.clone_cache/aspose_html_python/` — all resolve, no error. |

### Dependency Accuracy claims

All four dependency/version claims (`skia-python>=87.0,<145`, `quickjs>=1.19,<2` under `js` extra, `pytest>=8` dev dependency, Python `>=3.10`) — CONFIRMED via my own `grep -n` on `pyproject.toml` (exact line numbers 10, 28, 32, 33, matching Stage A's citations independently) cross-referenced against my own direct `Read` of the candidate at lines 75/93 (skia), 86/97 (quickjs), 82/101 (python), 105/591 (pytest). I additionally re-read the complete `[project]` and `[project.optional-dependencies]` blocks of `pyproject.toml` myself and confirm there is no third dependency, extra, or version constraint anywhere in the file that the candidate omits or misstates.

Additional unflagged check: candidate's Installation claim "A PyPI package has not been published yet" — CONFIRMED against `data/package_registry.json` → `html.python.verification.published: false`, `evidence_note: "Backfilled 2026-08-01: no live match found for any tried candidate (aspose-html-foss)..."`.

### API Accuracy claims

- 244 total `class_definition` entries in `api_surface.json`, 48 functions — CONFIRMED (my own `Counter` over `kind` field, independent of Stage A's numbers).
- `IDSelector` (`src/aspose_html/css/_ast.py:53`, `visibility: "public"`) is real and absent from the candidate — CONFIRMED. I independently grepped the source (`class IDSelector:` at line 53, docstring `"""Matches elements whose id attribute equals id_value: \`\`#main\`\`."""`, exactly matching the `api_surface.json` entry's `doc` field verbatim) and independently confirmed `grep -n "IDSelector" reports/repo-presenter-regen-full/html/python/readme.md` returns **zero matches** (exit code 1).
- No disposition file records `IDSelector`'s exclusion — CONFIRMED: `grep -rl "IDSelector" reports/repo-presenter-regen-full/html/python/*.json` returns nothing (checked all four disposition files that exist for this product: `badge-`, `code-example-`, `content-`, `structure-dispositions.json`).
- New finding beyond Stage A: `content-dispositions.json` unit `u0032` — the disposition entry for the "243 public types" sentence itself — is independently confirmed to read `"verification": {"status": "verified_against_source", "evidence_type": "clone_cache_path", "evidence_ref": "src/aspose_html/html_document.py"}`. I read this JSON object directly (field name is `unit_id`, not `id` as one might assume). A single source file (`html_document.py`, which only defines the `HTMLDocument` entry point) cannot substantiate a cross-module total-class-count claim; the "verified_against_source" tag on this specific unit is itself unsubstantiated by its own cited evidence, independent of the count being wrong.
- All 7 code-example API signatures — CONFIRMED via my own `grep -n`, exactly matching every line number Stage A cited: `html_document.py:39` (`def parse(`), `_document.py:2374` (`def get_element_by_id`), `_document.py:1661` (`def create_element`), `_document.py:1056` (`def attach_style_sheet`), `_document.py:2395` (`def get_elements_by_tag_name`), `_node.py:708` (`def append_child`), `_stylesheet.py:10` (`class CSSStyleSheet`) / `:295` (`def replace_sync`), `_element.py:209` (`def get_computed_style`), `_declarations.py:176` and `_cascade.py:399` (both define `def get_property_value`), `encoding/detection.py:47` (`def detect_encoding`), `_quickjs_bridge.py:205/465/516/530` (`class JSContext` / `def evaluate` / `def __enter__` / `def __exit__`), `tokenizer/_tokenizer.py:44/153` (`class Tokenizer` / `def tokenize`).
- "Work With URLs and Search Parameters" example — Stage A explicitly flagged this as **not independently re-verified line-by-line given scope**. I closed that gap myself: `class URL` at `url/_url.py:24`, `URL.search_params` property at `url/_url.py:278` returning a `URLSearchParams`, and `URLSearchParams.set(name, value)` at `url/_search_params.py:129` — CONFIRMED, full call chain checks out.
- `EncodingDetectionResult.encoding/.confidence/.text` attributes used in the candidate's example — CONFIRMED against the live `@dataclass(frozen=True)` definition in `encoding/detection.py:12-42`; the source's own doctest (`detect_encoding(b"<p>Hello</p>")` → `.encoding`/`.confidence`) uses the identical attribute names the candidate's example relies on.
- `JSContext(document)` context-manager example — CONFIRMED; `_quickjs_bridge.py:237` `__init__(self, document: "Document")`, and the source module's own docstring at lines ~225-233 contains a doctest nearly identical to the candidate's example (`with JSContext(doc) as ctx: ctx.evaluate("1 + 1")` → `2`).
- Scope-and-Limitations `NotImplementedError` citations — I independently re-checked 5 of the 5 distinct source locations against live code (not just against `limitations.md`): `css/_rules.py` `CSSRule.type`/`css_text` (lines 59-65), `dom/html/_embedded_elements.py` `HTMLImageElement.decode()` (~line 427), `js/_quickjs_bridge.py` `import_stub` (~line 460), `css/_matcher.py` pseudo-class/combinator `NotImplementedError`s (lines ~196, ~349), `dom/_validation.py` `_compute_validity_state` (line 186) — all CONFIRMED present verbatim in current source, so `limitations.md` is not stale relative to the live clone cache.
- Development-and-Testing section's test-directory listing and skip mechanics — CONFIRMED: `ls runs/.clone_cache/aspose_html_python/tests/` returns exactly `test_html, test_dom, tokenizer, test_tree, test_css, test_cssom, test_layout, test_url, encoding, test_js, test_serialiser, test_render, test_file_io.py` (13 items, exact match, same order-independent set as candidate readme.md:606); `tests/test_js/*.py` use `pytest.importorskip("quickjs")` (3 files checked); `tests/test_render/test_skia_smoke.py` uses `pytest.importorskip("skia", reason="skia-python not installed")`; `conftest.py` conditionally excludes `src/aspose_html/js/` from doctest collection when `quickjs` is absent.
- Spot-checked two additional class descriptions Stage A didn't cite (`HTMLUnknownElement`, `ProcessingInstruction`) against live docstrings — both CONFIRMED as accurate paraphrases of the real source doc comments.

### One discrepancy found in Stage A's own report (not in the candidate)

**Stage A's Identity table states the original README (`c2356ec`) is "86 lines."** I independently ran `git -C runs/.clone_cache/aspose_html_python show c2356ec:README.md` myself (piped to a scratchpad file and also read via the `Read` tool, which numbers every line): the file is **136 lines**, ending at `136\tSee [CHANGELOG.md](CHANGELOG.md).` with a trailing blank line 137. `wc -l` on the same git-show output independently confirms `136`. This is a factual error in Stage A's own Identity section, not a defect in the candidate — the substantive line-by-line content Stage A quotes from and maps against the original (Features bullets, Installation, Quick Start, Package Entry Points, Compatibility, three `###` examples, Links, Development/Security/Changelog) is all verbatim-correct against my own full read of the same `git show` output, so the Content-Preservation Ledger's conclusions are unaffected — only the reported line count itself is wrong.

### Unflagged high-risk claims checked and found sound

- `model.yaml` (`knowledge/html/python/merged/model.yaml`) independently read: `class_count: 244`, `total_claims: 2144`, `repo_sha: c2356ec872fd7d64c14a0ae8cc043eea1a03847e` — all self-consistent with `api_surface.json` (244 classes) and `claims.json` (2144 entries, `len(json.load(...))` == 2144 exactly).
- `data/package_registry.json`'s `html.python` entry confirms `published: false`, consistent with and supporting the candidate's Installation-section claim.
- No contradicting claim about total public-type count exists anywhere in `claims.json` (grepped for "243"/"244 public"/"public types" — no such claim recorded there, so the false count originates only in the disposition/generation step, not from a bad upstream claim record).

## Stage C: Adversarial Verification

**Finding 1 (MAJOR, systemic — publication-ledger gap)** — **CONFIRMED.** Independently re-ran every cited command: `git -C runs/.clone_cache/aspose_html_python log --oneline -- README.md` → `912f0ae .../ c2356ec ...` (exact match, including author `Babar Raza <babar.raza@aspose.com>`, timestamp `Sun Aug 16 18:12:43 2026 +0500`); `gh api repos/aspose-html-foss/Aspose.HTML-FOSS-for-Python/contents/README.md --jq .content` freshly fetched and decoded via `.venv/Scripts/python` (not piped through `print()`) → raw sha256 `56b1ca26...9529c`, identical to clone-cache HEAD's CRLF→LF-normalized sha256, and the repo is confirmed public (`private: false`) with `pushed_at` matching the commit second-for-second. `diff` of the freshly-decoded live file against the candidate reproduces the exact single-hunk delta cited (`567a568 > - **[Runnable examples]...`). Parsed `data/readme_published_state.json` programmatically: 11 entries, none for `family:"html"`; `reports/repo_presenter_actions.jsonl` has exactly 2 lines, neither for html/python. Severity/tag are calibrated, not overstated — this is a real, reproducible blind spot in a ledger whose own header comment says it exists to prevent exactly this kind of silent drift.

**Finding 2 (MAJOR, product-specific w/ plausible-systemic hedge — false "243 public types" count)** — **CONFIRMED**, and independently reproduced with a stricter method than either prior stage used. Loaded `api_surface.json` directly: 292 entries = 244 `class_definition` + 48 `function`; visibility breakdown 234 public + 4 exported + 6 conventional = 244; `IDSelector` present, `visibility:"public"`, `file: src/aspose_html/css/_ast.py`, `line: 53` — matches source exactly (`class IDSelector:` at that line, docstring verbatim). Rather than a loose backtick regex, I extracted only `| \`Name\` |` table rows from the candidate's `## API Reference` section: exactly 243 unique rows, and `set(api_surface classes) - set(table rows) == {'IDSelector'}` with the reverse difference empty — this is airtight, not merely plausible. Also confirmed the false count appears **twice** in the candidate (lines 213, 566) and confirmed `u0032`'s `verification.status: "verified_against_source"` citing only `src/aspose_html/html_document.py` — a file that cannot substantiate a portfolio-wide count. Additional fact the write-up under-leverages: the same "243" text is already present verbatim in the **live, published GitHub README** (lines 213/566 of the freshly-fetched file), meaning this isn't just a pending-candidate defect — it's already shipped to real users. That strengthens rather than undermines MAJOR; not a reason to downgrade.

**Finding 3 (MINOR, systemic-hedged — disposition excerpts capture destination text, not source text)** — **CONFIRMED** for this product. `content-dispositions.json` unit `u0013` excerpt reproduced exactly and found verbatim at candidate `readme.md:58`; the true original (`git show c2356ec:README.md`, line 9) reads only "- Parse HTML strings, bytes, fragments, and files into a DOM document" — materially shorter, no backticked API names. The "systemic" tag is explicitly hedged by the reviewer ("SYSTEMIC (disposition-ledger design...)") and I could not independently corroborate it across products in the time available — a spot check on `cells/net` u0001 was inconclusive because that unit happens to be a verbatim-preserved passage where source and destination text coincide, so it can't distinguish "captures source" from "captures destination." The core in-scope claim is solid; the cross-product generalization remains an untested (but reasonably-hedged) hypothesis, not overclaimed.

**Finding 4 (MINOR, likely-systemic — structure-dispositions.json missing 2 heading transitions)** — **CONFIRMED.** `structure-dispositions.json` contains exactly the 4 entries claimed (`s0001`–`s0004`: "At a Glance," "Query Elements By Tag Name," "Detect Character Encoding From Bytes," "Execute JavaScript Against The DOM"). Original headings (`grep '^### '` on the c2356ec text) are exactly `Parse And Read HTML`, `Create DOM Nodes`, `Work With URLs` — the latter two untracked. Verified `### Work With URLs and Search Parameters` exists in the candidate (line 148, untracked) and `### Create DOM Nodes` has no surviving heading, with its substance (`create_element`, `append_child`, `serialise`) independently confirmed present in the Quick Start code block (lines ~112–134). Evidence fully supports the claim as stated; severity (MINOR, a ledger-completeness gap rather than a reader-facing defect) is appropriately calibrated.

**Finding 5 (INFORMATIONAL — broken build-backend correctly not recommended)** — **CONFIRMED**, and I went one step further than either prior stage: live-downloaded the real current PyPI `setuptools-84.0.0-py3-none-any.whl` (fresh network fetch this session, not reused from Stage B) and inspected its 343-file listing directly — `setuptools/build_meta.py` exists; no `setuptools/backends/` package exists anywhere. `pyproject.toml:3` confirmed to read `build-backend = "setuptools.backends.legacy:build"` verbatim. `setuptools` is absent from this repo's own `.venv`, corroborating the environment-level observation. The candidate's Installation section (verified lines 66–80) indeed never suggests `pip install aspose-html-foss`. Correctly scored as informational, not a defect.

**Finding 6 (NIT — reviewer's own Windows console mojibake, disclosed and self-corrected)** — **CONFIRMED.** Re-fetched the live README fresh (independent `gh api` call, decoded straight to binary, never touching a text-mode `print()`) and counted UTF-8 em-dash bytes vs. raw `0x97`: 40 UTF-8 em-dashes, 0 raw `0x97` bytes, clean UTF-8 decode — matches the "40 occurrences, 0 corrupted" claim exactly. Correctly classified as a self-inflicted tooling artifact rather than a product defect.

**Overall:** All six Verdict findings survive independent re-derivation from their own cited evidence (recomputed hashes, live network re-fetches, direct JSON/source reads, a fresh setuptools wheel download) with no discrepancies found. None warrant downgrade or upgrade; severities and product-specific/systemic tags are all defensibly calibrated, with appropriate hedging language already in place where cross-product generalization wasn't independently tested.