# readme-refresh pdf/typescript scale hardening — findings and design (living spec)

Mission `readme-refresh-pdf-typescript-scale-hardening-2026-09-03`. Trigger: user asked to
generate a pdf/typescript candidate through the real `/readme-refresh` (S-120) skill, manually
compare it against the live destination repo (described as "quite comprehensive"), find gaps,
harden the skill, and iterate to a verified candidate.

## 0. The source, measured

Live `README.md` on `aspose-pdf-foss/Aspose.PDF-FOSS-for-TypeScript` main (commit `197de270`,
re-fetched and clone cache updated 2026-09-03): **274,584 bytes, 2,642 lines, 6 H2 sections, 42
H3/H4 subsections** — by a wide margin the largest and most technically dense source this skill
has ever composed a candidate from (the next-largest prior products run 15–55KB). Its own
extraction produced **324 content units, 114 code units, 3 structural units, 0 badges**.

**A genuine, live upstream defect, confirmed independently before relying on it**: the raw
file's byte 0 is a stray, near-duplicate API-table row glued directly onto the `# Aspose.PDF FOSS
for TypeScript` title with no line break. Verified via GitHub's own markdown render API
(`POST /markdown`, `mode: gfm`) that the entire first line renders as **one plain `<p>`** — the
H1 title does not render as a heading at all on the live GitHub page. This is real and current,
not a fetch artifact (confirmed on a clean re-fetch, blob sha `b454dac7`).

## 1. What the candidate composition looked like

Given the scale, verbatim-preserving fidelity was prioritized over hand-retyping: the 32 worked
examples under the old `## Quick start` and the entire `## Limitations` section were extracted
programmatically (byte-exact slices) rather than manually retyped, then reorganized into the
template's structure — `## Key Capabilities` condensed the old `## Features`' 71 bullets (some
individually 1,500–2,000 words) into 18 bullets; `## API Reference` combines a real
module-grouped class table (360 classes / 9 modules, mechanically built from
`content/reference.aspose.org/en/pdf/typescript/_index.md`'s own real body) with the old
`## API overview`'s full member-level table preserved verbatim under `#### Detailed Member
Reference`. Final candidate: 47,715 → several rounds → final size below.

## 2. Real, confirmed skill/check defects found and fixed (not worked around)

Every fix below is a genuine bug in the checking machinery, confirmed against real content
before touching code — none are "gate says X, so change the gate to accept X" without cause.

### 2.1 `_is_title_case` never implemented its own documented internal-capitals clause
Fixed earlier the same day during the 3d/python mission (`46e9535e28`) — the docstring always
said a word with internal capitals (`glTF`, `macOS`, `DocumentBuilder`) counts as correctly
cased; the code only checked the first letter. Re-confirmed load-bearing here too
(`### Encrypt With Certificate-Based (Public-Key) Encryption`-style headings).

### 2.2 `check_format_name_casing`: two real prose-extraction gaps at this document's scale
- **Fenced code blocks were never stripped**, only inline `` `code` `` spans — the inline
  regex `` `[^`]*` `` only consumes from one backtick to the next, so for a triple-backtick
  fence it eats two of the three opening backticks and leaves the entire fenced body as
  "prose". With 32 real TypeScript examples, a source variable name (`const doc = ...`)
  false-positived against the real format registry's `DOC` entry.
- **A literal HTML tag name in prose** (`<svg>`, `<img>`, from the verbatim Limitations
  section's HTML-rendering discussion) was scanned as a bare word for the same reason.
- Fixed: a dedicated fenced-block strip runs before the inline-backtick strip; HTML tags are
  stripped the same way link targets and inline code already are. Both changes only ever
  *remove* text from consideration, so they cannot introduce a new finding on any of the other
  30 products — confirmed via `audit-portfolio` (see §4).

### 2.3 `check_format_name_casing`: a single incidental ALL-CAPS emphasis word
Real, verbatim-preserved sentences used bare ALL-CAPS for emphasis the way most candidates use
`**bold**` ("a Type 1 program **IS** embedded" written as literal `IS`, "records **WHICH
PIXELS**" as literal `WHICH PIXELS`) — each exactly once, colliding with hundreds of ordinary
lowercase uses of the same common English word elsewhere. This is the *same* false-positive
mechanism TC-HARDEN-28 (2026-08-12) already named and fixed for the API Reference section's
table/heading collisions — recurring in ordinary prose purely because of document length, a
scale this skill had never been tested against. Fixed: the "appears all-caps at least once"
acronym-candidacy signal now requires **≥2** independent all-caps occurrences (a genuine
acronym like `SVG`/`PDF` recurs many times; a one-off emphasis word does not). Verified: `IS`,
`WHICH`, `PIXELS` each occur all-caps exactly once in the whole 3,100-line candidate; `SVG`
17×, `PDF` 95×.

### 2.4 `_parse_readme_api_tables`'s stop-marker is a fixed, undocumented-elsewhere string
The API Reference section's own additional member-detail content must be introduced with the
*exact* heading `#### Detailed Member Reference` (case-insensitive) for the completeness/
public-type-count checks to stop scanning there — this is real, established, working portfolio
convention (confirmed present in 3d/java, cells/cpp, cells/net, cells/rust, email/cpp and
others) but was **not documented anywhere in `skills/readme-refresh.md`**, so a
first-time composing agent (this session) invented its own label
(`#### Member Quick Reference`) and produced 121 `api_reference_table_completeness` findings +
1 `api_reference_public_type_count_matches_table` finding purely from the parser not
recognizing the stop marker and folding an entire 35KB supplementary table (plus its own
internal `### HTML`/`### Markdown` sub-headers) into spurious extra "modules". **This is a
documentation gap, not a code bug** — the mechanism already works correctly once the exact
heading is used; TC-04 below adds the missing skill-doc sentence so the next agent doesn't
rediscover this by trial and error.

### 2.5 A checked-in skill-doc illustration itself violates `check_heading_title_case`
`skills/readme-refresh.md`'s own Additional-Example heading-contract illustration shows
`<summary><strong>View Additional Examples</strong></summary>` — copying it literally (as this
session initially did) fails the gate, because the summary-text regex extracts `<strong>` as
part of the heading text and its first "word" (`strong`, from the tag) is lowercase. The real,
established portfolio convention (3d/python, cells/typescript, and every other shipped
candidate) uses plain text, no `<strong>` wrapper. TC-04 fixes the illustration to match.

## 3. Real candidate content defects found and fixed (not skill bugs)

- **Key Capabilities under-coverage at scale**: condensing 71 Features bullets (many
  individually larger than most products' *entire* Features section) into ~18 overview bullets
  genuinely dropped specific facts `check_content_unit_merged_into_target_section`'s per-sentence
  bundling logic correctly detected (245 findings on the first pass). Root-caused per unit: 228
  of 245 were legitimately retargetable to `## API Reference` (their full detail already lives
  verbatim in the Detailed Member Reference table) — verified programmatically by re-running the
  real check function against each candidate target, not guessed. The remaining ~17 needed
  genuine content additions to Key Capabilities (new bullets for Page decoration/Bates
  numbering, image extraction, digital-signature detail, tagged-PDF authoring); the final ~8
  were deep, per-parameter PDF-object-name tokens (`/BBox`, `/DW2`, `opts.timestamp`) genuinely
  below the level any Key Capabilities bullet states for any capability in this portfolio —
  disposed honestly as `excluded` with a precise reason naming what's covered vs. what isn't.
- **`evidence_ref` set to the bare README itself** for 316 of 324 content units (a real
  ledger-authoring mistake this session made, not a skill defect) — `check_content_unit_
  evidence_resolves` correctly rejects a claim about the README citing the README as its own
  evidence. Fixed by mechanically deriving the real source file per unit from
  `knowledge/pdf/typescript/merged/api_surface.json`'s own name→file index (434 of 441 resolved
  automatically; 7 fixed by hand after checking the real source tree).
- **`c0001` (a self-contained `ToSvg`/`ToImage`/`ToHtml`/`ToMarkdown`/`ToDocx` rendering demo)
  was embedded inside the old `## Features` section itself**, not under any Quick-Start `###`
  heading — invisible to the extraction pass that only walked the 32 `### `-headed examples.
  `check_code_example_api_coverage_survives` caught the drop; restored as a new, real, verbatim
  Additional Example ("Render and Export a Page or Document to Other Formats").
- **`BigTIFF`/`Pdf` (16×, boilerplate reference.aspose.org descriptions) mis-cased** against the
  registry's canonical `BIGTIFF`/`PDF` — fixed.
- **Installation dropped two real facts** from the old README's own Installation section (the
  `node:zlib`/`node:crypto`/`node:fs` built-in dependency and the "local file or npm workspace
  dependency" clone-install framing) — restored.
- **Three genuinely duplicate-fingerprinted code units** (`AddTextBlock` called 3 different ways
  in one Text Stamping example; `npm run` in both Development and the Feature Showcase) were
  given real, topically-accurate, distinct, resolvable `evidence_ref`s (a real test file per
  variant, e.g. `test/decorate-watermark.test.ts` for the rotate/opacity stamp) rather than
  fabricated ones — using `check_code_example_no_exact_duplicate_merge`'s own documented,
  already-established exemption mechanism.
- **A dependency-absence claim phrased "third-party-dependency-free"** didn't match the Claims
  Policy's accepted qualifier-noun list (`crate`/`package`/`library`, not bare `dependency`) —
  reworded to "no third-party library" rather than widening the check's accepted-phrase list
  (a narrower, lower-risk fix given the remaining time budget; see §5 deferred items).
- **Diagram Outputs nodes carried non-format connector words** ("new or modified", "renders",
  "export") — `check_diagram_container_format_purity` correctly flagged them; simplified to
  bare format lists matching established portfolio convention.

### 2.6 `_acquire_typescript_environment` never made an unpublished package resolvable by its own declared name
The Python runner's acquire step (ST-171, fixed earlier the same day for font/python) already
knew "unpublished → editable-install the clone". The TypeScript runner's own acquire step had
never been exercised against a product whose real Quick Start imports **by its own declared
package name** (`import { Document } from '@asposefoss/pdf'` — the correct, realistic form,
distinct from the relative-import convention `_run_single_typescript_block`'s docstring
documents for other products, e.g. cells/typescript's own `./aspose_cells`). Confirmed live:
plain `npm install` only resolves the manifest's own listed dependencies — it never makes a
package resolvable by its own name from inside its own source tree — so `Document.New` on the
FIRST real end-to-end `verify-examples --typescript-runner` run against pdf/typescript raised
Node's real `ERR_MODULE_NOT_FOUND` on **86 of 91 real blocks**. Root-caused and fixed with two
real, additional, disposable-copy-only steps, each verified live end-to-end before landing (a
real `Document.New` call, via both plain `node` and `tsx`):
1. `npm run build` (only when the manifest declares that script) — `main`/`types` point at
   `dist/...`, which does not exist without building.
2. A real, standard package self-link: `node_modules/{scope}/{name}` created as a directory
   symlink pointing at the project directory itself. `npm install .` was tried first and found
   to be a silent no-op (npm detects installing a package into itself and skips it, confirmed
   live); a real filesystem symlink is what `npm link`/a monorepo workspace does under the hood
   and needed no admin privilege on this platform (confirmed live, both attempts). Harmless and
   never attempted for a product whose examples never self-import.
Rechecked after the fix: see evidence/verify-examples.after-fix.result.json.

### 2.7 A checked-in badge template mislabels the npm/TypeScript language-version badge
`_BADGE_LANGUAGE_VERSION_TEMPLATES["typescript"]` labeled its suggested badge "TypeScript
Version" while the underlying data (`dependency_snapshot.native_system`'s
`version_constraint`) is the npm `engines.node` constraint — a Node.js **runtime** requirement,
never the TypeScript **language/compiler** version (that's a separate `development`-bucket
devDependency, its own semver range, e.g. `^5.5.0`). Confirmed inert until this mission (zero
shipped candidates on any `typescript` platform currently render this badge, so nothing already
live needs correction) — relabeled "Node.js" with the real npm-ecosystem `node.js` shields.io
logo. Real, generalizable: would have mislabeled the badge for every future `typescript`-
platform product the moment anyone acted on the advisory suggestion, not just this one.

### 2.8 TypeScript verify-examples runner never had fixture staging or example chaining
The Python runner earned both in ST-171 (2026-09-02); the TypeScript runner (added
TC-25/2026-09-01, then given the self-import fix in §2.6 above) never did. Confirmed live,
end to end, against the real pdf/typescript candidate after §2.6 landed: 83 of 91 blocks still
failed, but now with `ReferenceError: doc/page/bytes/source is not defined` (77) and generic
`ENOENT` on `in.pdf`/`secret.pdf`/etc. (5) instead of `ERR_MODULE_NOT_FOUND` — a completely
different, previously-invisible failure class. Root cause, confirmed by reading the live
upstream `README.md` directly: pdf/typescript's own `## Additional Examples` writes several
long runs of `###` sections (`Encrypted PDFs` / `Encrypted output` / `Certificate-based
encryption` / `Split and merge` / `Content streams` / `Text stamping` and others) as one
continuous narrative sharing an ambient `doc`, not as independently-runnable snippets per
heading — real, upstream authoring style, faithfully preserved verbatim by this candidate's
own byte-exact extraction (not a composition defect). Fixed by giving the TypeScript runner the
same two capabilities, reusing the Python runner's own `_stage_readme_fixtures`/
`_readme_fixture_names` unchanged (already language-agnostic) and adding
`_typescript_block_starts_chain` (same "first real statement is an import" convention as
`_python_block_starts_chain`, adjusted for `//` line comments). Measured effect on the real
candidate: 83 undifferentiated RUNTIME-ERROR collapsed to 72 honest `DEPENDS-ON-FAILED-BLOCK`
(correctly downstream of a named root cause) + 11 real, individually-understood root causes (5
`FIXTURE-UNAVAILABLE` — `in.pdf`/`secret.pdf`/etc. genuinely do not exist anywhere in the
clone cache, confirmed by direct search, so honestly disclosed rather than fabricated; 5
`RUNTIME-ERROR`; 1 `UPSTREAM-BROKEN`, see §2.9). The heuristic does not bridge every case — see
§5's ST-179 for the disclosed, narrow residual.

### 2.9 A real upstream defect the new UPSTREAM-BROKEN classifier caught: `htmlFileToPdf` is undocumented-unreachable
One of the 11 root causes from §2.8 was not an ambient-scope issue: `### Use file-based helper
methods` imports `htmlFileToPdf` from `@asposefoss/pdf` and calls it exactly as the upstream
README shows. `htmlFileToPdf` is a real, fully-implemented, exported function in the package's
own `src/node.ts`, but `src/index.ts` — the package's only real entry point
(`"main": "dist/index.js"`, no `exports` subpath map) — never re-exports it; confirmed by
reading both files directly. A real `npm run build` + Node's real ESM loader raises `SyntaxError:
The requested module '@asposefoss/pdf' does not provide an export named 'htmlFileToPdf'` — a
genuine upstream defect (the README documents a real capability the built package cannot
actually deliver), not a candidate mistake (verbatim-transcribed from the source). Added
`_classify_typescript_failure`, mirroring the Python runner's own TC-26 `UPSTREAM-BROKEN`
distinction, so this reports honestly instead of as generic `RUNTIME-ERROR`. Recorded in
`reports/repo-presenter-regen-full/pdf/typescript/upstream-issues.md` with full evidence.

### 2.10 Publication-status disclosure reversed (explicit user direction, post-close addendum)
After this mission's first close, the user reviewed the pushed candidate live and objected to
the Installation section's own publication-status narration — "`@asposefoss/pdf` has not yet
been published to npm… Once published this will become `npm install @asposefoss/pdf`." —
naming it internal-only information that must not appear in a public README. This is a real
policy reversal of the 2026-09-02 mission's own deliberate precedent ("disclosure + preview is
fine"), not a bug fix: `check_installation_matches_live_publication`'s NOT-published branch
previously *required* the disclosure sentence when a registry command was shown, and now
*forbids* both the disclosure sentence and any registry-command preview outright (new finding
`unpublished_with_disclosure_sentence`, alongside the renamed-scope
`unpublished_with_registry_install_command`, which now fires on the preview too since it
literally contains the registry command text). `skills/readme-refresh.md`'s "Installation by
publication state" composition guidance rewritten to match. pdf/typescript's own candidate
edited (the two sentences removed, from-checkout instructions kept verbatim) and its
`code-example-dispositions.json` unit `c0002` (the source's own bare, not-really-working
`npm install @asposefoss/pdf` fence) changed from `merged_verbatim` to `excluded` with a real
reason, since that exact text no longer appears anywhere in the candidate. Re-verified clean:
`recheck` → 0/72 hard-gate findings, unchanged.

**Portfolio-wide consequence, measured, not fixed here**: `audit-portfolio` before/after this
change (isolated via dirty-set diff) shows exactly **9** already-shipped candidates newly dirty
on `installation_matches_live_publication` alone — their Installation sections still carry the
now-forbidden disclosure text: barcode/python, cells/rust, cells/typescript, email/cpp,
font/python, html/python, slides/cpp, slides/net, tex/python. Several are already pushed live
(their real GitHub READMEs carry the same old disclosure). Filed as **ST-180** (backlog, P2) —
each needs its own Installation-section regeneration + review + re-push, out of this mission's
scope (which was pdf/typescript only).

### 2.11 ST-180 closed same day (user: "regenerate and confirm") — plus a real, distinct discovery
All 9 candidates' Installation sections fixed directly (disclosure/preview text removed, real
working instructions kept) — `barcode/python`/`cells/typescript`/`html/python` (one-line
disclosure removed), `email/cpp`/`slides/cpp`/`slides/net`/`tex/python` (disclosure prefix
removed), `font/python` (disclosure + a separate "once published this will become `pip install
aspose-font`" preview both removed), `cells/rust` (Installation prose fixed AND a duplicate
Scope-and-Limitations disclosure bullet deleted entirely, plus a now-stale "once the repository
is live at its real GitHub location" clause removed — confirmed live via `gh api` that the repo
is now public). 4 dependent `content-dispositions.json` entries whose `merged_verbatim` claim
was exactly the removed text (barcode/python `u0020`, cells/rust `u0105`, slides/cpp `u0022`,
slides/net `u0022`) flipped to `excluded` with a real reason, matching the same-mission `c0002`
precedent (§2.10). `audit-portfolio` confirms `installation_matches_live_publication` clean on
all 9 (0 findings); **7 of 9 are fully clean overall** (barcode/python, cells/rust,
cells/typescript, email/cpp, html/python, slides/cpp, slides/net).

**A real, separate, pre-existing problem surfaced while confirming, not caused by this fix**:
font/python and tex/python's `audit-portfolio` runs showed a large, genuine
`content_unit_disposition_coverage`/`content_unit_excerpt_matches_extraction`/
`code_example_disposition_coverage`/`badge_disposition_coverage` finding set (91+50+49+3 on
font/python) that never surfaced before — because `audit-portfolio` silently SKIPS those checks
whenever a product's live-probed `published` flag reads `true`, and both products' probe read
`true` (stale/ambiguous) in two calls earlier the same session before flipping to the correct
`false` (independently confirmed via direct `curl` against PyPI: both packages 404). The `false`
reading un-masked real drift: both candidates' disposition ledgers were built against an
old-README extraction pinned to a clone-cache HEAD that has since moved (font: `c6d82093` →
`dcf9549a`; tex: `2f4bfab3` → `181015d2`, tex/python's own prior mission's real merge SHA — its
live GitHub README was independently confirmed, via `gh api`, to still carry the same disclosure
text this fix targets, so the local candidate copy is not out of sync with what's live, only
with the ledger's own ability to verify it). Neither product's ledger was regenerated here — a
full, separate S-120 re-composition per product, well outside "remove the disclosure sentence."
Filed as **ST-181** (backlog, P2): the specific disclosure fix is confirmed correct and complete
for all 9 products; the newly-found masking behavior and the two products' stale ledgers are a
distinct, real problem for a dedicated future mission.

### 2.12 CORRECTION (2026-09-04): the §4 retention claim was true but not a reliable answer
The user reviewed the candidate against the live upstream README directly and pushed back:
"much of the existing content was not retained." Re-verified independently rather than
re-asserting §4's own prior claim (a real, systematic, token-level re-check of all 69 original
`## Features` bullets, not a sample) — the user was right. `## Features` (69 bullets, 82,393
bytes, 11,343 words) collapsed into `## Key Capabilities` (17 bullets, 5,950 bytes, 745 words)
— a **93% word-count cut**. A byte-weighted token-coverage measurement (every backtick/bold
term from each original bullet, checked for presence anywhere in the candidate — a deliberately
generous bar) found only **68% average coverage**, dragged down hardest on the document's
*biggest* bullets: SVG embedding (11.5 KB, the largest bullet, 48% coverage), digital
signatures (44%), and the entire PDF/A + PDF/X validation/conversion cluster (26–53% across all
four). 7 of 69 topics scored under 50%.

**Root cause of why §4's "0 hard-gate findings" didn't catch this**:
`check_content_unit_merged_into_target_section` only requires ONE matching token per
sentence-group to appear in the claimed target section — a single compressed API-table row
containing "gradients, patterns, filters, masks" satisfies that bar for an entire 1,700-word
bullet describing exact stop/opacity semantics, mask region defaults, marker geometry, the full
CSS cascade, and named SVG filter primitives, none of which the table row actually carries. The
check verifies "the topic is mentioned," not "the explanation survived." This is a real,
confirmed methodological gap, not a difference of editorial opinion — §4's "243 verbatim / 72
reframed, all honest, all traced" framing is accurate to what the ledger recorded and was an
incomplete answer to "was the content retained."

Qualitative pattern (checked via 3 full-bullet-vs-candidate manual comparisons, not just the
token count): **API-surface-shaped** topics (named types/options/enums — e.g. digital
signatures) redistribute reasonably into the API-table format even at a lower raw token score,
because tables have a natural home for named things. **Behavior-shaped** topics (exact
semantics, defaults, edge-case rules, algorithms explained in flowing prose — e.g. SVG
embedding's gradient-stop/mask/filter behavior) do not have a table-row-shaped home and are the
ones genuinely being lost.

Delivered to the user: a full audit artifact (`evidence/retention-audit.html`, published) with
the complete 69-row sorted table, methodology, and two full before/after excerpts (SVG=worst
case, digital signatures=better case for contrast). Three options were laid out; the user chose
a fourth, stronger one directly: harden the skill so it retains every VERIFIED piece of the
original, dropping only genuinely unverifiable content (never disclosed publicly why), then
regenerate and re-loop until real retention is proven — see §2.13.

### 2.13 Full resolution: skill hardened, candidate regenerated, retention now 100% (measured)
**Skill hardening** (both real, tested, portfolio-safety-checked):
- `check_content_unit_reframe_fidelity` — new HARD GATE (checks_module_version 6→7, 118th
  `check_*` function). Promotes `_retention_fidelity` (word-overlap score, target-section-scoped
  with a whole-document fallback) from `build_retention_report`'s reviewer-only advisory to a
  real blocking failure at the SAME 0.5 threshold the report already used to label
  `reframed_low_fidelity` — closing the exact gap §2.12 found. Portfolio-wide impact measured
  via `audit-portfolio` before/after: 2 newly-dirty products (3d/net, note/python — 1 finding
  each, genuine, disclosed, not fixed here, out of scope). `skills/readme-refresh.md`'s
  composition guidance rewritten: verified content must be retained with real fidelity;
  "too granular for a bullet" is no longer a legitimate `excluded` reason — only genuinely
  unverifiable content may be dropped, and the public candidate never explains why (the
  `excluded_reason` lives only in the internal, gitignored disposition ledger).
- Two real, narrow `check_format_name_casing` false positives found live composing the fix
  (could not be worked around by rewording, since the offending text is now verbatim-preserved
  original content, not this skill's own prose): a `\bdot[\s-]+leaders?\b` idiom strip (the
  Table-of-Contents feature's real "dot leaders" typesetting term colliding with the registry's
  real `DOT` format), and `"ONE"` added to `_GENERIC_ACRONYM_STOPLIST` (a common number-word
  that hit the ≥3-distinct-casing-variants signal via two unrelated, unreworded occurrences —
  verbatim prose + a pre-existing code comment). Both are narrow, named, verified-safe
  exceptions, not the general ST-176 fix (still deferred).

**Candidate regeneration**: rather than hand-summarizing 69 bullets losslessly (judged too
error-prone to verify at this density), the full original `## Features` body — verified,
byte-for-byte, against the pinned clone-cache baseline — was inserted essentially verbatim as a
new `#### Detailed Capability Reference` block, `<details><summary>`-collapsed under `##
Key Capabilities`, mirroring the API Reference's own already-established `#### Detailed Member
Reference` two-tier pattern exactly (short overview list, then full detail). All 71 real
content units the extractor traces back to `## Features` were re-disposed `merged_verbatim`
targeting `Key Capabilities` (62 previously `merged_reframed` + 8 previously `excluded` for
granularity, now correctly retained; 1 already `merged_verbatim`) — verification blocks (real
`evidence_ref`s to source files) were kept, only `disposition`/`target_section` changed.

**A real, live, additional finding along the way**: composing this exposed genuine upstream
drift — a real commit (`7b994de4`, "incremental save" + "preserve encryption on save",
2026-09-03 16:38 +0500) landed on the live GitHub repo after the clone cache was pinned
(`197de270`). Its own README diff (verified via `git diff` against the fetched-but-not-checked-
out new commit, plus a source spot-check confirming `Document.Revisions`/`hasIncrementalUpdates`
are real) is small but real: an extended `Saving` paragraph (`{ incremental: true }`), a new API
table row, and a new Limitations bullet (encrypted-save preserves its own `/Encrypt` by default).
Incorporated directly (sourced from a fresh live fetch, not the stale pin) since the mandate is
retaining what the CURRENT target repo says — added as extra verbatim content with no
corresponding ledger entry required (the pinned baseline's own extraction doesn't know about it,
so no coverage obligation is triggered; harmless, purely additive). The clone-cache **working
tree** was deliberately left checked out at the original pin (`197de270`, only `git fetch`, no
checkout/reset) to avoid triggering a full re-extraction cascade over content this specific fix
didn't touch — a future regeneration will naturally pick up the moved HEAD via a fresh `plan`.

**Final, independently re-verified result**: `recheck` → 0/73 hard-gate findings (up from 72
applicable gates, since the new fidelity gate is now counted). The SAME independent token-
coverage methodology §2.12 used to find the 68% average — re-run against the fixed candidate —
now measures **100.0% coverage across all 69 original bullets** (byte-weighted, against the
LIVE current upstream text including the newly-incorporated drift). `audit-portfolio` re-run
portfolio-wide: pdf/typescript clean (`{}`), zero real regression elsewhere (one transient
`cells/rust` finding traced to live-probe network flakiness during the scan, confirmed gone on
an isolated re-check — matches the already-disclosed ST-181 pattern, not a new defect).

## 4. Validation
- Scoped test additions: `test_readme_refresh_checks.py` (format-name-casing fenced-block/
  HTML-tag/all-caps-floor cases, 3 new + 1 rebalanced), `test_readme_refresh_run.py`
  (`_self_link_typescript_package` × 3, TypeScript-badge-label × 1,
  `_typescript_block_starts_chain` × 4, `_classify_typescript_failure` × 2). Full scoped suite —
  `test_readme_refresh_checks.py` + `test_readme_refresh_run.py` +
  `test_check_readme_template_contract_parity.py` — **1012 passed**;
  `check_readme_template_contract_parity` OK (117 `check_*` functions, unchanged — every fix
  this mission made was to an EXISTING check's internals, not a new check); `sync_providers
  --dry-run` confirms only the 3 readme-refresh mirrors need updating.
- `audit-portfolio --json` captured before and after the `check_format_name_casing` fix: 25
  clean / 7 dirty both times, identical dirty set — confirms zero regression across the other 30
  products (removing false-positive-generating text can only ever reduce findings, never add
  one — verified, not just argued).
- Live proof, first real run (no shortcuts, no pre-tuning): `ingest-candidate` → 0/117 hard-gate
  findings on the composed candidate (down from 10 hard-gate categories / ~700+ individual
  findings on the true first pass — evidence/ingest.negative-control.result.json). Final:
  `ingest-candidate` → **0 hard-gate findings across all 72 applicable hard gates**
  (evidence/ingest.final.result.json), candidate 235,111 bytes.
- `verify-examples --typescript-runner` against the real compiled/executed TypeScript, through
  three real end-to-end runs as the runner itself was hardened (§2.6, §2.8, §2.9):
  v1 (self-import only) → 86/91 `ERR_MODULE_NOT_FOUND`; v2-pre-classifier (+ fixture staging
  + chaining) → 83 undifferentiated RUNTIME-ERROR collapsed to 72 `DEPENDS-ON-FAILED-BLOCK` +
  11 named root causes; **final** (+ `UPSTREAM-BROKEN` classifier) →
  **3 `COMPILED+RAN CLEAN`, 72 `DEPENDS-ON-FAILED-BLOCK`, 5 `TOOLCHAIN-UNAVAILABLE` (non-TS
  blocks), 5 `FIXTURE-UNAVAILABLE` (confirmed: no such file anywhere in the clone cache), 5
  `RUNTIME-ERROR` (ST-179, disclosed), 1 `UPSTREAM-BROKEN` (§2.9, disclosed)** — every one of
  the 91 real blocks now has a specific, individually-understood, honestly-classified status;
  see evidence/verify-examples.final.result.json.
- Retention: `retention-report pdf typescript` — 324 content units (243 verbatim / 72 reframed /
  9 excluded, all honest, all traced — see §3's 8-unit `excluded` list for exactly what's not
  independently restated and why), 3 structural units (verbatim), 114 code units (verbatim).
  41 headings: 8 present verbatim, 24 absorbed into a real target under different prose, **9
  reported "absent" that are each a deliberate, task-descriptive retitling of a real, verbatim-
  preserved worked example** (`### Text stamping` → `### Stamp Text on a Page`,
  `### Flow layout (`` `doc.NewFlow` ``)` → `### Build Multi-Column Flow Layouts`, and 6 more;
  `## API overview` → `## API Reference`, the required section name) — the report's own
  heading-match is literal-text-based and has no way to know a heading was intentionally
  renamed, not dropped; the content itself is independently confirmed verbatim via the code-unit
  ledger (114/114 verbatim). None of the 9 is a real loss.

## 5. Deferred, disclosed, NOT fixed this pass
- **`_canonical_format_casing()` is sourced from the FULL cross-portfolio format registry**,
  unscoped to the current product — a format whose canonical spelling collides with a common
  English word (`DOC`, `DOT`) can still false-positive on ordinary prose use of that word ("dot
  leaders", not a real DOT-format reference) regardless of document length. Confirmed real
  (7 occurrences, all false), worked around in the candidate by rewording rather than fixing the
  check — an under-tested, portfolio-wide behavior change (scoping `canonical_casing` to a
  product's own verified format list) was judged too risky to attempt and verify within this
  session's remaining time. **ST-176** (backlog).
- **Claims Policy's `_DEPENDENCY_SCOPE_QUALIFIER_RE` has no "third-party dependency/
  dependencies" alternative** — only `crate(s)`/`package(s)`/`librar(y|ies)` are accepted nouns
  after "third-party". A TypeScript/npm product describing a hand-written decoder has no natural
  reason to say "crate" (Rust) or "library" always fits awkwardly for an *algorithm*, not a
  dependency. Worked around by rewording in the candidate; a small, well-scoped regex addition
  (same shape as the existing alternatives) is a real, low-risk future fix. **ST-177**.
- **`readme_refresh_run.py recheck`'s own CLI stdout print crashes on Windows cp1252** the
  moment a finding's JSON contains a non-Latin-1 character (confirmed: `→`) — cosmetic (the
  underlying `checks/result.json` write succeeds either way, confirmed by reading it back), but
  a real annoyance on this platform. **ST-178**.
- **`_typescript_block_starts_chain` (§2.8) resets on ANY leading `import`**, same convention as
  the Python runner's own heuristic, which cannot bridge a later `###` section that imports one
  new symbol while still depending on an unrelated earlier section's local variable — 5 of 91
  real blocks (disclosed in `upstream-issues.md`, reflects the upstream README's own
  multi-heading narrative style). A real fix needs a stronger signal (e.g. only reset on a
  fresh `Document.OpenFile`/`Document.Open` binding) — judged out of scope to design and verify
  portfolio-wide within this session's remaining time. **ST-179**.
