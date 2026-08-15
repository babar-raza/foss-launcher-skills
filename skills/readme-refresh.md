---
name: readme-refresh
id: S-120
description: >
  Generate, verify, and (on explicit approval) push a production-grade README.md refresh for
  one FOSS product repository, through the registered run-bound readme_refresh_run.py state
  machine.
args: "{family} {platform}"
---

<!-- CONTRACT: registered-cli-wrapper
     purpose: operate one run-bound README refresh for one FOSS product repository
     preconditions: product active in data/products.json, not excluded, real push/admin access
     postcondition: run is AWAITING_REVIEW, APPROVED, PUSHED, BLOCKED, or ABANDONED
     idempotent: yes — immutable receipts, state checkpoints, single-owner-per-product locking
     verified: 2026-08-15
-->

> Cross-skill references like `/knowledge-bootstrap` refer to sibling skills in this directory.

# S-120: README Refresh

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform}`

## Official execution contract

Use only the registered control plane:

```bash
.venv/Scripts/python scripts/pipeline/commands/foss/readme_refresh_run.py start FAMILY PLATFORM \
  [--run-id ID] [--session-id ID] [--skip-preflight]
.venv/Scripts/python scripts/pipeline/commands/foss/readme_refresh_run.py plan --run-id ID [--session-id ID]
.venv/Scripts/python scripts/pipeline/commands/foss/readme_refresh_run.py ingest-candidate --run-id ID [--session-id ID]
.venv/Scripts/python scripts/pipeline/commands/foss/readme_refresh_run.py verify-examples --run-id ID [--session-id ID]
.venv/Scripts/python scripts/pipeline/commands/foss/readme_refresh_run.py recheck --run-id ID [--session-id ID]
.venv/Scripts/python scripts/pipeline/commands/foss/readme_refresh_run.py status --run-id ID
.venv/Scripts/python scripts/pipeline/commands/foss/readme_refresh_run.py approve --run-id ID \
  --note TEXT [--session-id ID]
.venv/Scripts/python scripts/pipeline/commands/foss/readme_refresh_run.py push --run-id ID \
  [--session-id ID] [--dry-run]
.venv/Scripts/python scripts/pipeline/commands/foss/readme_refresh_run.py verify --run-id ID [--session-id ID]
.venv/Scripts/python scripts/pipeline/commands/foss/readme_refresh_run.py abandon --run-id ID \
  --reason TEXT [--session-id ID]
.venv/Scripts/python scripts/pipeline/commands/foss/readme_refresh_run.py recover --run-id ID \
  --reason TEXT [--session-id ID]
.venv/Scripts/python scripts/pipeline/commands/foss/readme_refresh_run.py audit-portfolio \
  [--family FAMILY --platform PLATFORM] [--json]
```

`audit-portfolio` (TC-HARDEN-05, MT035, 2026-08-12) is the one subcommand with no `--run-id` —
it's read-only and portfolio-wide, not run-scoped: it re-runs every deterministic check
(`_run_deterministic_checks`, the same function `ingest-candidate`/`recheck` use) against every
already-composed candidate in `reports/repo-presenter/{family}/{platform}/readme.md`, for every
`active: true`, non-excluded product in `data/products.json` (optionally narrowed to one
`family`/`platform` pair via the two flags). A product with no candidate composed yet is
skipped, never an error. This is the real, registered, tested replacement for the ad hoc,
gitignored scratch script (`reports/repo-presenter/_scratch/phase2_scan.py`) this skill's own
maintenance had to hand-write and re-derive from memory every time a "is the whole portfolio
still clean" question came up — closing the gap named in TC-HARDEN-14 (real verification work
happening outside any registered, reproducible path). `--json` prints the full structured
result (`{"products", "clean_count", "dirty_count", "total", "skipped"}`); without it, prints a
one-line summary plus one line per dirty product. **This does not run on a schedule** — it's an
on-demand capability, not a recurring job; nothing currently triggers it automatically, so
drift between two products' candidates and their real upstream reference data (e.g. a
`reference.aspose.org` regeneration) can still accumulate silently until someone runs it by
hand — a real, disclosed, still-open gap (see the skill's own governance taskcard register in
the plan file for the deferred "should this run on a schedule" decision).

State machine: `CREATED → INPUTS_PINNED → PLANNED → VERIFYING_EXAMPLES → AWAITING_REVIEW →
APPROVED → PUSHING → PUSHED`. `BLOCKED` is re-enterable from `INPUTS_PINNED`/`PLANNED`/
`VERIFYING_EXAMPLES`/`PUSHING`. `ABANDONED` is terminal from any non-terminal state. `PUSHED`
and `ABANDONED` are the only terminal states. Every mutating call requires a stable session
identity (`--session-id` or `AGENT_SESSION_ID`/`CODEX_THREAD_ID`/`CLAUDE_CODE_SESSION_ID`) and
is checked against the run's `session_owner` — a different session cannot touch someone else's
run. One `ACTIVE.json` per `(family, platform)` plus a `FileLock` prevents two runs owning the
same product concurrently.

## Steps

> **Skill context gate** — run before `start`:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py begin --skill S-120 --scope "reports/repo-presenter/{family}/{platform}/*,reports/readme_refresh_runs/{family}/{platform}/*"
> ```

1. **`start`** — resolves the product against `data/products.json` (must be `active: true`,
   not in `data/registry_exclusions.json`), runs a real `gh api repos/{org}/{repo} --jq
   .permissions` pre-flight check (refuses without real push/admin access — this is the literal
   fix for `foss-java-publish`/S-110's documented gap, which only assumed access as prose and
   never checked it), pins the clone-cache `HEAD` SHA. Transitions `CREATED → INPUTS_PINNED`.

2. **`plan`** — emits `facts/factpack.json`: real archetype classification (`data/
   diagram_archetypes.json`, defaulting to `transform` when no override entry exists), real
   capability-dependency edges (`data/diagram_capability_dependencies.json` — `None` when the
   product has never been traced, which must never be read as "confirmed independent"), real
   install/package data (`data/package_registry.json`), real case-sensitive license-file
   detection against the clone cache (widened 2026-08-12, TC-HARDEN-20, to a 200-char
   case-insensitive substring match — the old exact-20-char-prefix match missed real files
   phrased "The MIT License (MIT)..."), a real, live-verified Enterprise Edition link
   (`enterprise_link` — TC-HARDEN-19, 2026-08-12, via `scripts/pipeline/lib/backlink_targets.py`
   against `data/aspose_com_targets.json`; `url` is `None` on a genuine unresolved target, which
   the candidate must never paper over with a guessed slug — see the hard gate below), a real,
   locally-verified homepage link (`homepage` — TC-HARDEN-27, 2026-08-12, `{"url", "verified"}`;
   `verified` is True only when `content/products.aspose.org/en/{family}/{platform}/_index.md`
   genuinely exists in this repo, a first-party same-repo-deploy guarantee, deliberately not a
   live HTTP check — see that field's own docstring for the tradeoff), and the
   old upstream README's real link/heading/prose inventory (`old_readme_inventory`, including
   `content_units` — MT030, see below). Transitions `INPUTS_PINNED → PLANNED`.

   **Enterprise Edition anchor-text contract (MT043/TC-HARDEN-61-62, 2026-08-14 — CORRECTED
   same day, MT044/Thirty-Fourth incident).** `enterprise_link` also carries `relationship`
   (`"family"` | `"platform"` | `"unresolved"` | `None`) and `public_platform` (a normalized,
   implementation-neutral display name, e.g. `"Python"`, `"Go"`, `"Node.js"` — never a compound
   like `"Python via Java"`), computed by `_classify_enterprise_relationship`. Compose the anchor
   from these two fields, never freehand:
   - `relationship == "family"` → `[Aspose.{Family} — Enterprise Edition]({url})` — the anchor
     names NO platform at all, ever, even when the source product's own platform is obvious from
     context.
   - `relationship == "platform"` → `[Aspose.{Family} for {public_platform} — Enterprise
     Edition]({url})` — name the one real `public_platform`, nothing else. This applies
     identically whether the underlying resolved URL is a bare platform slug (`.../cells/java/`)
     or a compound bridge slug (`.../cells/python-java/`, `.../cells/go-cpp/`) — **the anchor
     never distinguishes the two, and must never mention the compound's own second component**
     (Java, .NET, C++ as an *implementation* detail) anywhere in the anchor or the surrounding
     prose. `resolve_backlink` may internally have chosen this URL because of implementation
     compatibility; that reasoning stays internal and is never surfaced publicly.
   - `relationship in ("unresolved", None)` → omit the Enterprise Edition link entirely. Never
     guess a platform name or fall back to a family link merely because the exact source-platform
     slug differs, the URL has a compound suffix, or a family URL is easier to write — family is
     the FINAL fallback (used only when `_detect_enterprise_link` itself could resolve no
     platform-specific target at all), never a default for an inconvenient platform match.
   - **Permanently forbidden, anywhere in the document** (anchors, prose, tables, notes,
     comparison sections, badges, installation text, architecture descriptions, related-product
     descriptions, footnotes, generated metadata) — any wording that discloses how one platform is
     implemented through another: "via Java", "via C++", "via .NET", "Python via Java",
     "implemented through X", "backed by X", "a wrapper around X", "a binding to X", "rather than
     as a native X", or any equivalent phrasing. `check_no_implementation_bridge_disclosure` (hard
     gate, portfolio-wide, not scoped to the Enterprise-link paragraph) is the mechanical backstop
     for this rule — it is not a substitute for composing correctly the first time.
   - **History, so this is never reintroduced**: MT043 originally required exactly this kind of
     "via {language}" wording plus a disclosure sentence for a compound-slug destination — a real
     policy defect discovered and reversed the same day (MT044), not a hypothetical. Do not revive
     any "bridge disclosure" requirement under a different name.

3. **Agent composes the candidate.** The script does not write README prose — the agent reads
   `facts/factpack.json` and writes `reports/repo-presenter/{family}/{platform}/readme.md`
   directly, following the Template section's standard structure (plan:
   `C:\Users\prora\.claude\plans\d-users-prora-onedrive-documents-github-humble-tome.md`). Every
   item in the factpack's `old_readme_inventory` (links, headings) must either land somewhere
   real in the candidate or be a deliberate, verified drop — `ingest-candidate`'s
   `check_dropped_content` hard gate below enforces this, it is not optional diligence.
   **MT030 (Fifteenth incident, 2026-08-09)**: the agent must ALSO write
   `reports/repo-presenter/{family}/{platform}/content-dispositions.json` — one entry per real
   prose content unit `old_readme_inventory.content_units` extracted from the old README
   (mechanism-level explanations and branding/positioning claims, verified against the real
   product repo and merged/reframed into the appropriate section; pure narrative/origin-story/
   CTA prose is explicitly out of scope, per the user's own decision, and gets an `excluded`
   disposition citing that). This is the real, working artifact `dropped_claims.json` was only
   ever a docstring aspiration for (2026-08-04 through 2026-08-09, never implemented by any
   code) — see `check_content_unit_disposition_coverage`'s own docstring for the full schema.
   **MT031 (Sixteenth incident, 2026-08-10)**: a 4th classification, `4_verifiable_history`,
   covers genuine, checkable project/format history (a past event, not a live source-checkable
   mechanism) — its `verification.status` must be `verified_by_corroboration` (internally
   consistent with, not contradicted by, real repo artifacts — never claimed "proven" the way a
   mechanism claim is). A `4_verifiable_history` unit may target a new, permanently OPTIONAL H3
   section, `### Project History`, placed after the banner and before the unheaded Intro
   paragraph (never a `##` heading — that would break `_split_into_sections`'s `"__preamble__"`
   boundary; H3 keeps it inside the same preamble region as Intro, so `check_required_sections`/
   `check_only_sections_changed` need no change and the section stays vacuously satisfied like
   `## Additional Examples` when a product has nothing real for it). A mixed unit — real,
   independently-actionable fact bundled with pure hedge/CTA tone (e.g. "...not the final
   shape... [open an issue](../../issues) and tell us about your use case...") — is reclassified
   to whichever real category the checkable fact belongs to and reframed to drop the hedge,
   never excluded wholesale; `check_content_unit_embedded_actionable_fact` (heuristic) is a
   standing, portfolio-wide tripwire for this exact pattern recurring on a future product.

   **Prose quality (TC-HARDEN-22, MT034/Twentieth incident, 2026-08-12).** Every existing
   tone-adjacent check (`check_process_narration_smells`, `check_key_capabilities_quality`,
   `check_section_job_distinctness`) is deliberately a heuristic, never a hard gate — "does this
   read naturally" is a judgment call no regex can make. What *is* made durable is the process
   that produces natural-reading prose, not left to whichever agent happens to be composing that
   day:
   - **Mandatory tone-exemplar reading, before composing any product's prose.** Read 2–3 real,
     already-shipped sibling candidates **in full** (not skimmed) — chosen for register
     diversity: one small/simple product, one large/complex product, and, when this product's
     own archetype has a shipped sibling, one from the same archetype. This extends the existing
     "read a sibling candidate for structural reference only, never copy its content" discipline
     to explicitly cover *voice*, not just structure — a real, required step, not left to
     individual agent judgment.
   - **A positive rubric to self-check against before finalizing** (never a hard gate): state a
     fact plainly, active voice, no hedging (real, shipped example — `cells/cpp`'s *"The primary
     entry point is `Workbook`, which owns a `WorksheetCollection` of `Worksheet` objects."*); a
     backtick-quoted identifier is woven naturally into a sentence describing what it does, never
     presented as a bare, undifferentiated list; each Key Capabilities bullet reads like
     something a developer would tell a colleague, not template filler with the identifier
     swapped in; sentence length and rhythm vary across a section.
   - **Regeneration Comparison Protocol** — whenever this product already has an existing
     candidate, do not stop at `ALL HARD GATES CLEAN`. Read both files in full and classify every
     real difference into: **structural** (sections/diagram/tables — the gates below already
     force these to match; a real difference here is itself a bug worth investigating, not
     accepting), **factual** (a claim present/absent/changed — verify EVERY factual disagreement
     against real source before trusting either side; never assume the older file is right just
     because it shipped first, never assume the newer file is right just because it's freshly
     source-derived), and **wording/tone variation** (expected, not a defect — this is the rubric
     above at work). Write the comparison down per-product, alongside `content-dispositions.json`
     — not just held in the composing agent's own context. **A regenerated candidate never
     silently replaces an existing one** — replacement requires the same explicit, per-product
     human go-ahead as every other consequential action this skill takes (matching the approve/
     push/merge gates above).
   - **Honest limit, stated plainly, never smoothed over**: the skill can produce the comparison
     and apply the rubric; it cannot certify "reads naturally" on its own authority. A
     mechanically-checkable property (does a link resolve, does a member exist) is not the same
     thing as prose quality — the gates below catch factual and structural defects; final
     certification that prose reads naturally stays a human judgment call, every time.
   - **Tone-exemplar contamination guard (TC-HARDEN-44, MT039/Twenty-Ninth incident,
     2026-08-14).** Before treating a shipped sibling candidate as a genuine tone/voice
     exemplar (the mandatory reading step above), confirm it is free of live
     `check_process_narration_smells` findings first — run the check, don't assume. A
     mechanism built to spread *good* patterns is exactly as capable of spreading *bad* ones:
     the "table/index below mirrors reference.aspose.org's own structure" leak (below) shipped
     in at least 9 products with closely related wording, strong evidence it propagated via
     this exact exemplar-reading step, not 9 unrelated composition mistakes. If a chosen
     exemplar has active findings, either pick a different sibling or explicitly note the
     specific passage *not* to imitate — never read a flagged file as if it were clean.

   **No generation-mechanism / design-rationale narration in the API Reference intro sentence
   (TC-HARDEN-43/44/45, MT039/Twenty-Ninth incident, 2026-08-14).** The API Reference intro
   sentence (Rule "API reference intro sentence must name real hub classes", above) must state
   *product* facts only — real hub classes, real type/module counts. It must never describe
   *this document's own table or section* as "mirroring," "organized as," or "grouped exactly
   as" another site, document, or internal artifact's structure — named or paraphrased. This is
   a fifth, previously-unnamed narration category, distinct from the other four
   (receipts/execution-notes/provenance/confidence-language): it narrates a *composition design
   choice*, not verification activity. Confirmed live across 9 products, several without naming
   `reference.aspose.org` literally (paraphrased as "the library's reference index," "the full,
   module-grouped reference," "the same data") — a regex keyed to the literal domain name alone
   would have missed 4 of the 10 confirmed instances.
   - **BAD** (real, confirmed, since fixed): *"The library ships 96 public types, summarized in
     the module-grouped table below (mirrors [reference.aspose.org's own class index](...))."*
   - **GOOD** (real, already-shipped, the reusable template): `3d/typescript`'s Documentation &
     Resources bullet — *"the API reference section above covers the essentials."* State what
     the section covers, never why or how it was built to look the way it does.
   - The word "mirror(s)/mirroring" itself is fine — real, legitimate product facts use it
     constantly (`MirroredProfile`, "mirrors the WHATWG `window.customElements` API," "mirrors
     PDF 32000 §12.3.2.2 names," "the API shape mirrors Aspose.PDF for .NET"). The defect is
     specifically when the *subject* doing the mirroring is this document's own table, tables,
     index, or section.
   - `check_process_narration_smells` (hard gate, below) mechanically catches the structural
     shape (`table|tables|index|section ... below|above ... mirror(s|ing)?`, plus `grouped
     exactly as`) — but the written rule above is the durable defense; a regex can only ever
     chase phrasings already seen (proof: this exact defect class evaded the module's other 27+
     narration patterns for 10 real instances before being named).

   **No generation-mechanism / design-rationale narration in ANY section's own intro sentence
   (TC-HARDEN-71/72/73, MT046/Thirty-Sixth incident, 2026-08-15) — the general principle,
   generalized past API Reference alone.** `font/python`'s real Key Capabilities intro sentence
   independently reproduced the identical narration category one incident after MT039 first
   named it — different vocabulary, same underlying defect: describing this document's own
   editorial choices instead of the product. The general rule: **any section's own framing/intro
   sentence — before Key Capabilities' bullets, before Additional Examples' flagship snippet,
   before API Reference's detail, or anywhere else a short prose lead-in precedes real content —
   must describe real, verifiable PRODUCT facts: real architecture, real processing layers, real
   feature groupings that would be true independent of how this specific README document happens
   to be organized.** It must NEVER describe (a) this document's own editorial/organizational
   choices, or compare how content COULD be organized against how it happens to be organized in
   this file; (b) internal source-code structure facts with no product relevance (file names,
   file sizes, "the largest module," line counts, which functions live "below"/"above" in this
   document). **The test**: would this sentence be true of the product even if this README were
   rewritten from scratch with a completely different structure? If the sentence would become
   false or meaningless under a different document structure, it is describing the document, not
   the product, and does not belong.
   - **BAD** (real, confirmed, `font/python`): *"Here's what you get — a Capability Snapshot of
     why teams use it, grouped by real module rather than by workflow label. Python API
     Highlights and CLI Highlights are both covered inline via backtick-quoted class/command
     names below, and variable-font-first workflows remain the deepest, most actively developed
     surface area (`instancing.py` alone is the largest module in the library)."*
   - **GOOD** (real, already-shipped, `email/cpp`): *"Features are grouped below by processing
     layer, from low-level CFB container access up through the high-level `mapi_message` API."*
     Note this ALSO says "grouped below" — the distinguishing fact is "processing layer...
     low-level...high-level" is real product architecture, true regardless of this document's own
     structure, while "real module rather than by workflow label" is a claim about the DOCUMENT's
     presentation choice. A bare "grouped by" is never itself the defect.
   - **Extension to the tone-exemplar guidance (TC-HARDEN-44, above)**: when imitating a
     sibling's intro-sentence convention (per the mandatory tone-exemplar-reading step) and no
     equivalently clean, real architectural narrative exists for the current product, the safe
     fallback is to **omit the framing sentence entirely** and start directly with the first
     bullet — matching the many real, already-correct portfolio products with no intro sentence
     at all (e.g. `barcode/python`, `cells/python`). Never invent a document-structure-comparison
     sentence to fill the gap. Imitating a *clean* exemplar's *form* while silently dropping its
     *substantive constraint* is exactly as capable of shipping a defect as imitating an
     already-flagged one.
   - `check_section_intro_no_meta_narration` (hard gate, below) mechanically scans the leading
     intro prose of `## Key Capabilities` and `## Additional Examples` for three narrow,
     precision-first patterns (a rejected-alternative organizing-scheme comparison, a
     self-reference to "covered inline...below," a source-filename-plus-size-superlative leak) —
     `## API Reference`'s own intro sentence is deliberately excluded, already separately covered
     by the rule above. Same honest limit as every other fixed-pattern narration check: it cannot
     prove no instance of this class exists anywhere, only that these specific patterns don't
     match — the written rule above is the durable defense.

   **SEO keyword integration and structural variety in Key Capabilities (TC-HARDEN-39/40/41,
   MT037, Twenty-Seventh incident, 2026-08-13).** `cells/java`'s real Key Capabilities section
   was found genuinely "dry" — 8 of 10 bullets opened with a backtick-quoted identifier as their
   grammatical subject, a monotonous, API-reference-style shape distinct from the fragmentation/
   thin-bullet defects `check_key_capabilities_quality` already caught (different first words
   every time, so that check's own literal-first-word-repetition signal never fired).
   - **Real, per-page SEO keyword data exists — `keywords/{family}.json`** — read via
     `_detect_seo_keywords(family, platform)` (matches the entry whose `sourcePath` is
     `content/products.aspose.org/en/{family}/{platform}/_index.md`, falling back to the
     family-root entry) and populated into `factpack["seo_keywords"]`/`["seo_keywords_
     filtered"]`. **The raw data is confirmed unreliable — do not trust it directly.** Every
     non-`.NET` platform checked for the `cells` family (java/python/rust, across products/docs/
     kb.aspose.org's own per-page entries) carries keyword phrases naming `.NET`/`C#` instead of
     its own real platform (`cells/java`'s own real entry: 10 of 10 phrases mention `.NET`/`C#`,
     zero mention Java) — the same "even structured, checked-in data isn't infallible" lesson
     `formats.md`/`data/package_registry.json` already taught this skill, recurring here.
     `checks.filter_relevant_seo_keywords(keywords, family, platform, known_format_names)` is the
     real, mechanical defense — already applied at factpack-build time, not left to the composing
     agent's own restraint: drops any phrase naming a platform other than this product's own
     (`_SEO_KEYWORD_PLATFORM_TOKENS`), keeps only phrases grounded in the family name, a known
     real format, or this portfolio's own established capability-verb vocabulary, and caps the
     result to 6 phrases. **`seo_keywords_filtered` can legitimately be empty** (confirmed live
     for `cells/java` — all 10 raw phrases were contaminated and none survived) — when it is, do
     not invent a substitute phrase; rely on this portfolio's own already-established natural
     framing (the Intro paragraph's own "free, open-source, pure-Java spreadsheet library"
     wording is itself real, verified SEO framing) instead of forcing something ungrounded in.
   - **"Highlight properly" means placement, never typographic markup.** Weave real, filtered
     keyword language into 2–4 spots across the whole file — weighted toward the Intro paragraph
     and the first 1–2 Key Capabilities bullets, where a reader or crawler looks first — as
     natural prose using verbs/framing already native to this portfolio's own voice (`"free"`,
     `"open source"`, `"alternative"`). Never wrap a keyword phrase in backticks (reserved for
     real code identifiers) and never bold it (this portfolio's Key Capabilities/Intro prose has
     no existing bold-emphasis convention, and introducing one for keywords reads as marketing-
     copy stuffing — the same unprofessional-tone class this skill has fought since the
     2026-08-04 process-narration incident). Never force a phrase into every bullet.
   - **Vary bullet opening structure — identifier-first, action-first, benefit-first, and
     task-first, mixed across the section, not any single shape uniformly.** Swapping "every
     bullet opens with a backtick identifier" for "every bullet opens with an action verb" is the
     same monotony in a different shape — `check_key_capabilities_structural_variety` (heuristic,
     below) only flags when ≥70% of bullets share the identifier-first shape specifically; a
     genuinely mixed section (roughly a quarter to a third identifier-first, the rest varied) is
     the target, not zero.
   - **Preserve every fact and identifier exactly** when rewriting for structure/SEO — this is a
     phrasing pass, never a content pass; if a rewrite drops a word a `content-dispositions.json`
     entry's evidence trail depends on for its own `check_content_unit_merged_into_target_
     section` word-overlap proof (real incident: rewriting "applies data validation rules" to
     "Validate input..." silently dropped the literal word "data" a real disposition's own
     word-overlap check depended on), restore the dropped word naturally rather than leaving the
     gate to fail — verify with `recheck` after any Key Capabilities rewrite on a product that
     already has real dispositions on file, not just the two new heuristics.
   - **Cheap, mechanical formatting hygiene** (`check_key_capabilities_formatting`, heuristic,
     below): every bullet ends with terminal punctuation, has no unmatched backtick (an odd
     backtick count in one bullet — the same parity-count idiom already proven for
     `check_no_stripped_example_in_description`), and never opens with a lowercase letter unless
     that word is itself a backtick-quoted identifier.

   **Dependency terminology and the Claims Policy — a mandatory `## Dependencies` section
   (TC-HARDEN-49 through -56, MT041/Thirty-First incident, 2026-08-14).** The real, confirmed
   defect this mission exists to fix: `cells/rust`'s Installation section stated *"Requires a
   recent stable Rust toolchain (2021 edition) — no external runtime or Microsoft Office
   installation is needed"* while its own `Cargo.toml` declares 7 real runtime crates (`chrono`,
   `zip`, `sha2`, `base64`, `serde_json`, `roxmltree`, `getrandom`) — a same-document
   contradiction against that file's own, correct Intro paragraph, which already named all 7.
   Real, already-verified dependency data now exists in every factpack (`factpack["dependencies"]`
   — a real `DependencySnapshot` from `dependency_extract.py`'s per-ecosystem manifest parsing,
   never a guess) and must be used, never invented.

   Use these terms precisely, never interchangeably — the sub-heading nouns below match them
   verbatim:
   - **Package dependency** — a real, named entry in the product's own manifest.
   - **Direct dependency** — declared directly in that manifest's own dependency table (this
     skill's own extractors never read a lockfile, so every `DependencySnapshot` entry is, by
     construction, direct — never present a name absent from the snapshot as if it were one).
   - **Optional dependency** — gated behind a feature flag/extra; the library builds and runs
     without it.
   - **Development dependency** — used only by the test/benchmark/lint suite, never shipped or
     required by a consumer.
   - **Native/system dependency** — an OS-level library, compiler, or toolchain version floor,
     not a package-manager entry.
   - **Proprietary-runtime dependency** — a commercial/proprietary runtime this product does NOT
     need (e.g. Microsoft Office, a proprietary Aspose engine). Proving this is absent proves
     *nothing* about package/native dependencies — never conflate the two, the exact mistake the
     real `cells/rust` sentence made.

   **`## Dependencies`** is a new, mandatory `_REQUIRED_SECTIONS` entry, placed immediately after
   `## Installation`, before `## Quick Start` — the direct sequel to "how do I install this,"
   strictly before "how do I use it." Four `###` sub-headings (title case, matching Rule 6 —
   "and" stays lowercase): **Required Package Dependencies**, **Optional Dependencies**,
   **Native and System Requirements**, **Development Dependencies**. Required omits only when
   the snapshot's `required` list is genuinely empty, and even then renders the fixed sentence
   **"No required third-party package dependencies."** rather than vanishing silently (a reader
   must never confuse "verified zero" with "generation forgot this"); Optional/Development omit
   silently when empty; Native and System is present for nearly every product (a real language/
   runtime version floor almost always exists). `pdf/cpp`'s existing inline `**Requirements**:
   ...` Installation sub-line is **superseded**, not duplicated, by this section — coexistence
   would recreate the exact same-document-contradiction risk `cells/rust` already proved real.

   **Claims Policy: never write an unqualified absolute** ("No external dependencies",
   "Dependency-free", "No dependencies required", "Completely standalone", "no external
   runtime/installation/software") **unless the claim names the exact dependency class it
   excludes in the *same coordinated clause* AND that is actually proven** by the
   `DependencySnapshot` data. "No third-party runtime crate dependencies," "no native system
   libraries," and "no proprietary Aspose runtime" are each fine, independently, only when true.
   A generic mention of the words "library"/"crate"/"package" elsewhere in the sentence (e.g. "a
   pure-Rust *library* for...") never counts as scoping — the qualifier must be an actual
   dependency-class phrase (`third-party crate`, `native system library`, `proprietary Aspose
   runtime`, etc.), checked within the *same clause* as the claim, never borrowed from a
   different coordinated clause joined by "or"/"and" in a compound sentence (the real
   `cells/rust` shape: "no external runtime *or* Microsoft Office installation" — "Microsoft
   Office" legitimately scopes only the second clause, never the first).
   - **BAD** (real, confirmed, since fixed): *"Requires a recent stable Rust toolchain (2021
     edition) — no external runtime or Microsoft Office installation is needed."*
   - **GOOD** (the reusable replacement): *"Requires a recent stable Rust toolchain (2021
     edition or later). No proprietary Aspose runtime and no Microsoft Office installation is
     required."* — paired with a real `## Dependencies` section naming all 7 crates. The
     corrected sentence keeps the true, scoped part of the original claim and drops only the
     false, unscoped part.

   When `factpack["dependencies"]` is missing or carries `applicable=False` with no real
   `not_applicable_reason` (should be structurally impossible — checked anyway), **never
   substitute a dependency-free claim** — `check_dependency_snapshot_completeness` (hard gate,
   below) fails the run with a named, actionable error instead. `dependency_extract.py`'s own
   extraction failures already convert into a real `BLOCKED` run at `plan` time via the same
   `_block()`/`ReadmeRefreshRunError` mechanism already proven at `push()`'s own call site — fix
   the named manifest (or add a verified entry to `data/dependency_overrides.json`), then
   `recover` and re-run `plan`.

   **Public-source allowlist for limitations content (2026-08-13, found live on `cells/cpp`).**
   A real Development and Testing sentence cited `upstream-issues.md` by name ("...see
   `upstream-issues.md` for the corrected commands used above") and, even once that citation is
   stripped, still narrated the underlying comparison finding in generalized prose ("...reference
   a `workspace/`-prefixed path layout that does not match a plain clone of this repository").
   Both are the same defect: a finding this pipeline's own investigation produced — by reading
   an internal, never-published artifact, or by comparing two real artifacts against each other —
   disclosed in the public README merely because the machinery discovered it. **Any public
   Scope-and-Limitations or Development-and-Testing claim must trace to one of**: the target
   repo's real, current, public source code (directly, statically observable by any external
   reader who opens the same public files — this is the established, already-hardened "verify
   against real source" discipline this whole skill relies on, and stays fully allowed), the
   target repo's existing root README, another public tracked doc in the target repo, or
   authoritative public product/package documentation. **Never allowed as the basis for a public
   claim**: `upstream-issues.md`, `content-dispositions.json`, `knowledge/{family}/{platform}/
   merged/*`, the read-only clone cache path itself, this project's own `reports/` evidence tree,
   or any other artifact that will not ship with or be reachable from the published repo — citing
   one by name, or restating its finding as unattributed prose, are the identical violation.
   Concretely: when composing Installation/Development-and-Testing instructions, give the real,
   working commands directly; never narrate *why* they differ from what a sibling doc in the repo
   says, or how this pipeline discovered the discrepancy — that narration is exactly the leak,
   independent of whether the internal filename is named. **If no limitation traces to an allowed
   source, omit the bulleted list entirely** — never invent filler such as "no known limitations"
   to satisfy the section's format contract; `check_scope_limitations_format`'s zero-bullet
   carve-out (below) makes this the valid, checked shape, not a workaround.

   **At-a-Glance diagram composition — Starting Points, Outputs, and Project Structure
   (2026-08-13, `cells/java` healing pass).** The container-chain shape is fixed
   (`Product → Core Capabilities → Outputs`, with an optional `Starting Points` container ahead
   of `Product`) but two real, live defects — a wrong Starting Points node and a wrong Outputs
   node, both on `cells/java`, both already correctly caught by the hard gates below before this
   guidance existed — showed the *composition* rules that should have prevented them were never
   written down anywhere a composing agent actually reads. Corrected here, not just fixed on that
   one product.
   - **Starting Points presence, corrected** (this paragraph replaces an earlier, stale
     hybrid-only description): required and populated with the product's real, distinct input
     formats for `transform`/`compile` archetypes; forbidden entirely for `generative`; exactly
     2 lines for `hybrid` (its own established "An existing X document" / "Nothing — authored
     from scratch" shape). Never assume "hybrid-only" — that was true before 2026-08-06 and is
     no longer the real rule.
   - **A format belongs in Starting Points only if it is a genuine PRIMARY document the product
     loads/creates/saves on its own terms — not merely auxiliary material a capability happens to
     also consume.** Exclusion tests (verify against real source before drawing *or* omitting,
     same discipline as every other diagram claim):
     - *(a) Capability-path selector* — chooses which of several already-modeled Capability nodes
       runs; redundant with their own existence.
     - *(b) Access/invocation-mechanism selector* — how the caller invokes the library, not data
       it operates on.
     - *(c) Bundled/internal resource* — ships inside the package, never supplied by the caller.
     - *(d) "Build from scratch"* — absence of input data is not itself input data; model as a
       Capability, not an Input.
     - *(e) Embedded/attached auxiliary material* — real, external, caller-supplied data that
       materially shapes a capability's output, EXCLUDED anyway when BOTH hold: (i) the product
       never exposes a top-level load/parse call whose primary subject is this format — it is
       only ever accepted as a parameter while building/editing a *different* primary document;
       and (ii) the product does not decode/interpret the format's own structure, only identifies
       (sniffs) and stores it as an opaque blob. Confirmed live: `cells/java`'s
       `PictureCollection` only magic-byte-sniffs JPEG/PNG/GIF/BMP (`PictureCollection.java:
       72-75`) and never independently loads one — the format belongs in Key Capabilities prose
       ("embeds images... detecting JPEG, PNG, GIF, and BMP formats"), never Starting Points.
       Cross-checked against every sibling product with a picture-embedding capability
       (`slides/java`, `slides/net`, `cells/net`, `cells/python`, `cells/rust`, `pdf/cpp`,
       `pdf/go`) — all nine already fold this into a Capabilities node or a genuine rendering
       Output, none show it as a Starting Point; this rule makes that existing, unwritten
       convention explicit rather than inventing a new one. Contrast: if the product's own
       top-level API *does* let a caller independently load a document of format X (not merely
       embed it), X still belongs in Starting Points for that real capability — (e) excludes only
       formats with no independent top-level load path anywhere in the product.
   - **When `check_diagram_verified_format_claims` or `check_diagram_container_format_purity`
     fires, check first whether the flagged node's concept is already — or belongs — represented
     as a Capability node.** If so, delete the Starting-Points/Outputs node; that is usually the
     correct resolution, not "strengthen the evidence until the claim passes." Reserve evidence-
     strengthening for a format that genuinely is a primary document and is simply under-recorded
     in `formats.md`/source. Confirmed live: `cells/java`'s `"Load diagnostics and repair report"`
     Outputs node was pure duplication of its own `"Load diagnostics and repair reporting"`
     Capability node and Key Capabilities' own `Workbook.getLoadDiagnostics()` sentence — deleting
     it lost zero information. `check_diagram_container_duplicates_capability` (heuristic, below)
     is the standing, mechanical tripwire for this exact shape recurring on a future product.
   - **Project Structure tree format is canonical, not whatever the old README happened to use.**
     When a `## Project Structure` section is restored (structure-dispositions.json, MT030-
     sibling mechanism), its fenced tree must use box-drawing characters (`├──`/`└──`/`│`),
     matching the one real, shipped, approved precedent (`cells/go`) — never the old upstream
     README's own native style (plain indented text, YAML-like nesting, etc.) reproduced
     verbatim. `check_project_structure_canonical_tree_format` (hard gate, below) enforces this
     mechanically so the next product can't silently pick a third visual convention.

   **API Reference detail must always collapse; the Enterprise Edition paragraph must always be
   genuinely separate from the Limitations bullets (MT045, Thirty-Fifth incident, 2026-08-15,
   TC-HARDEN-67/68/70).** A real `barcode/python` regeneration independently reproduced BOTH
   defects at once, and a portfolio scan found the first defect ALSO on `3d/net`/`3d/typescript`
   (2 separate regeneration batches) — proof neither convention was ever durable, only imitated.
   - **`<details>`-collapse the API Reference detail content, unconditionally, regardless of
     row/class count.** Every real module table row and every curated `` - `ClassName` ``
     member bullet goes inside `<details><summary>View the Full API Surface</summary>...
     </details>`, the same shape `## Additional Examples`'s own exhaustive table already uses —
     size is never a threshold (`tex/python`'s real 11-class table, the smallest real API surface
     in the whole portfolio, still collapses). `check_api_reference_detail_collapsed` (hard gate,
     below) mirrors `check_examples_table_collapsed`'s design exactly.
     - **BAD** (real, confirmed on `barcode/python`): a `### Core API` table, an `#### Enumerations`
       table, and no `<details>` tag anywhere in the section — every row fully expanded above the
       fold.
     - **GOOD**: intro sentence naming real hub classes, visible → `<details><summary>View the
       Full API Surface</summary>` → every module table + curated bullet → `</details>`.
   - **Never continue a Limitations bullet's own sentence directly into the Enterprise Edition
     mention — always insert a blank line and start a genuinely separate paragraph.**
     `check_scope_limitations_format` (hard gate, unchanged design intent, bug-fixed below) had a
     real, reproducible bug that silently missed this exact shape.
     - **BAD** (real, confirmed on `barcode/python`): *"...PDF rendering is not implemented...
       For PDF rendering and additional symbologies, see the\n[Aspose.BarCode for Python —
       Enterprise Edition](...), which adds\nthe full commercial rendering pipeline..."* — no
       blank line before the Enterprise sentence; it is the same bulleted list item's own wrapped
       continuation.
     - **GOOD** (real, already-shipped — `email/python`, `3d/python`, `cells/cpp`): the bulleted
       Limitations list, a blank line, then a standalone paragraph: *"These limitations apply only
       to {Product} FOSS — they don't carry over to [{Product} — Enterprise Edition](...), which
       adds..."*

4. **`ingest-candidate`** — runs the real deterministic checks module
   (`scripts/pipeline/commands/foss/readme_refresh_checks.py`, 83 `check_*` functions as of
   2026-08-15 (MT046) — re-verify against `grep -c "^def check_" readme_refresh_checks.py` before
   trusting this number again). **2026-08-08 diagram simplification (Tenth incident, MT024)**: the At-a-Glance
   diagram is now exactly `Product → Core Capabilities → Outputs` (up to 5 capabilities in one
   column, 6+ split into 2 balanced columns) — no individual per-capability edges. **Starting
   Points presence is archetype-general, not hybrid-only** (corrected 2026-08-08, Eleventh
   incident / MT025, itself corrected in this doc 2026-08-13 after a live composition mistake
   traced the error back to this exact paragraph never having been updated): required, populated
   with real input formats, for `transform`/`compile` archetypes; forbidden for `generative`;
   exactly 2 lines (unchanged shape) for `hybrid`. See the diagram-composition guidance above for
   which formats belong there. **Hard gates** (any finding blocks the transition): required
   sections present in title case, no `forum.aspose.com`/`*.aspose.app` links, license link
   target resolves case-sensitively on disk, the diagram matches the fixed container-chain shape
   and column-balance rule, the diagram's column order matches the recorded `data/
   diagram_capability_dependencies.json` entry (no-op when none exists — edges there are now
   keyed to the *current* diagram's own node IDs, re-recorded whenever a diagram is redrawn),
   `check_diagram_starting_points_presence` enforces the archetype-general presence/count rule
   above (not hybrid-only), a `Starting Points` container on a `hybrid`-archetype product must
   ADDITIONALLY have its classification freshly re-confirmed *this run*
   (`check_diagram_hybrid_reverification`; `data/diagram_archetypes.json`'s `decided_at` must
   match today — a no-op for every other archetype, since presence-appropriateness is
   `check_diagram_starting_points_presence`'s job, not this one's), a Starting-Points/Outputs
   node whose label significantly word-overlaps an existing Capabilities node's label is flagged
   for likely duplication (`check_diagram_container_duplicates_capability`, heuristic — usually
   means the node should be deleted, not evidence-strengthened; see the composition guidance
   above), a `## Project Structure` section's tree uses canonical box-drawing characters, not the
   old README's own native style (`check_project_structure_canonical_tree_format`, hard gate),
   every format named in the diagram is genuinely supported (cross-checked against
   `knowledge/{family}/{platform}/merged/formats.md`), format-name casing is internally
   consistent and matches `data/format_descriptions.json` where known, no sibling product family
   is cited inside a section that's supposed to describe only this product, the `## Additional
   Examples` exhaustive table is collapsed alongside the remaining worked examples (not always
   visible), (**TC-HARDEN-67**, MT045/Thirty-Fifth incident, 2026-08-15) the `## API Reference`
   section's own detail content — every module table row and curated `` - `ClassName` `` bullet
   — is likewise inside a `<details>` block, unconditionally, never a row-count threshold
   (`check_api_reference_detail_collapsed`; a real, confirmed regeneration-batch defect on
   `barcode/python`, `3d/net`, and `3d/typescript`, not a one-off), every heading (including
   `<summary>` text) is title case, no undisclosed BLOCKING
   command from `upstream-issues.md` is repeated as a normal install/build step, no real
   old-README link/heading/meaning was silently dropped or hidden behind an internal
   process-label like "Preserved repository details", (**2026-08-13, `cells/cpp` healing pass**)
   no internal-only artifact — `upstream-issues.md`, `content-dispositions.json`, the
   `.clone_cache` path, the `knowledge/*/merged` layer, this project's own `reports/repo-
   presenter`/`reports/readme_refresh_runs` trees — is named, linked, or cited anywhere in the
   candidate (`_INTERNAL_LABEL_PATTERNS`, folded into the same `check_dropped_content` hard gate
   as the process-label check above — it is a NEW-candidate-quality check, unconditional, not
   gated on whether an old README exists), the Scope and Limitations section never asserts "no
   known limitations" or any equivalent invented-filler phrasing (`check_scope_limitations_
   format`'s `invented_filler` finding — the section's bulleted list is simply omitted, never
   filled with a sentence about its own absence, when no limitation traces to an allowed public
   source), the closing Enterprise Edition mention is a genuinely separate paragraph, never a
   bulleted Limitation's own wrapped continuation (**TC-HARDEN-68**, MT045/Thirty-Fifth incident,
   2026-08-15 — `check_scope_limitations_format`'s own bullet/continuation classification was
   bug-fixed to route through `_iter_leak_scan_units`; the prior raw-physical-line
   classification silently missed `barcode/python`'s real defect, where the Enterprise sentence
   was the "PDF rendering is not implemented" bullet's own unbroken continuation), (**TC-HARDEN-19**, MT034/Twentieth
   incident, 2026-08-12) every `products.aspose.com` Enterprise Edition link in the candidate
   matches the factpack's own real, live-verified `enterprise_link["url"]` exactly — never a
   guessed slug (this closes a confirmed-live regression: a clean-room regeneration produced a
   real, curl-confirmed 404 that every prior gate, including the anchor-text/context check
   below, passed cleanly), (**TC-HARDEN-62**, MT043/Thirty-Third incident, 2026-08-14 —
   CORRECTED same day, MT044/Thirty-Fourth incident) the anchor's own platform claim matches
   `enterprise_link`'s real, computed `relationship`/`public_platform` — a family relationship's
   anchor names no platform at all, a platform relationship's anchor names the one real
   `public_platform` and no other (see the anchor-text contract under `plan`, above) —
   (**MT044**, Thirty-Fourth incident, 2026-08-14) and, portfolio-wide and document-wide, not
   scoped to the Enterprise-link paragraph, no implementation-bridge disclosure phrase ("via
   Java", "implemented through .NET", "backed by C++", "a wrapper around X", "a binding to X",
   "rather than as a native X") appears anywhere in the candidate at all
   (`check_no_implementation_bridge_disclosure`) — this REPLACES TC-HARDEN-62's own original
   "missing_bridge_disclosure" requirement, which had mandated exactly this wording for a
   compound-slug destination; that requirement was the actual policy defect this later gate
   reverses, not a residual bug, (**TC-HARDEN-21**, MT034, 2026-08-12) no class name appears more than
   once within the same API Reference module table (an exact duplicate row is not the same
   defect as a missing/unrecognized class, and `check_api_reference_table_completeness` has no
   concept of it), (**TC-HARDEN-26**, MT034/Twenty-First incident, 2026-08-12) the `## License`
   section's text starts with the fixed template sentence (linked or unlinked form, per whether
   a real license file was detected) rather than free-form narration — the only prior check for
   this section (`check_license_link_target`) verified the link target alone, never the prose,
   and a blind clean-room regeneration of `3d/typescript` independently reproduced the exact
   2026-08-04 narration-leak defect this rule already named, proving it had never actually been
   enforced, (**TC-HARDEN-27**, MT034/Twenty-First incident, 2026-08-12) the At-a-Glance banner
   is linked to the product's real `products.aspose.org/{family}/{platform}/` homepage whenever
   `content/products.aspose.org/en/{family}/{platform}/_index.md` genuinely exists in this repo
   (a first-party, same-repo-deploy guarantee), and stays unlinked otherwise — never a guessed or
   unconfirmed homepage URL, (**TC-HARDEN-71**, MT046/Thirty-Sixth incident, 2026-08-15) neither
   `## Key Capabilities`'s nor `## Additional Examples`'s own leading intro sentence (the text
   before the first bullet/fenced block/sub-heading) narrates this document's own editorial
   organization or leaks an internal source-filename-plus-size-superlative fact
   (`check_section_intro_no_meta_narration` — see the generalized composition rule above;
   `## API Reference`'s own intro sentence is deliberately excluded, already separately covered),
   and (**MT030**, Fifteenth incident)
   every real old-README content unit has a complete, well-formed disposition record whose
   cited evidence actually resolves against real product-repo/registry/docs data and whose
   claimed section-merge is traceable to real text in the candidate (never two disposition
   entries merging the identical excerpt into the identical section). **(Twenty-Fourth mission,
   2026-08-13, `cells/go`'s missing `Project Structure` section) — two more agent-authored
   sibling files, same tier as `content-dispositions.json`, closing what that file structurally
   can never see:**
   - `structure-dispositions.json` covers STRUCTURAL (non-prose) old-README sections — a section
     whose real content lives entirely or mostly inside a fenced code block (a directory tree, a
     pure command list) produces ZERO content units under `extract_old_readme_content_units` (it
     strips fenced code before segmenting, by design), so it was previously invisible to the
     whole verify-and-merge pipeline. `extract_old_readme_structural_units` gates on content
     SHAPE, not heading text — "Repository Layout"/"Source Layout"/"Project Structure" all
     recognize identically. Every extracted unit needs a disposition
     (`check_structural_unit_disposition_coverage`, hard gate) whose claimed merge is genuinely
     traceable into its `target_section` (`check_structural_unit_merged_into_target_section`,
     hard gate — a `target_section` may be an existing template section OR the unit's own real
     heading, e.g. a genuinely new `## Project Structure` section) with no exact-duplicate merges
     (`check_structural_unit_no_exact_duplicate_merge`, hard gate) and (heuristic)
     `check_structural_unit_tree_paths_plausible` flags a directory-tree unit whose claimed paths
     mostly don't resolve against the real clone cache anymore.
   - `badge-dispositions.json` covers badge semantic reconciliation — previously nonexistent (no
     parsing/classification/dedup mechanism anywhere in this module). `extract_badges` +
     `classify_badge` (an open-string category, never a closed enum) + `verify_badge_target`
     (tiered, network-cautious: a `#` link is a structural placeholder; a shields.io *static*
     `/badge/` URL claiming an inherently-dynamic fact like CI/coverage/downloads/contributors is
     a real, mechanically-decidable red flag, not a guess) + `reconcile_badges` (pairs by
     category + real link target, never by label similarity — the real `cells/go` case: old
     "License" and new "License: MIT" pair correctly despite different wording). Every old badge
     needs a disposition (`check_badge_disposition_coverage`, hard gate) whose
     `preserved`/`superseded_by_duplicate` claim genuinely credits a same-category badge that's
     really in the candidate (`check_badge_preserved_or_credited_in_candidate`, hard gate), plus
     two heuristics (`check_badge_probable_duplicate_disposition`,
     `check_badge_static_claims_dynamic_fact` — the latter runs against the candidate
     unconditionally, catching a freshly-composed static/fake badge, not just a carried-forward
     old one), and one more hard gate, `check_no_duplicate_badges_in_candidate`, checking the
     RENDERED candidate directly (independent of disposition-bookkeeping correctness) for two
     badges sharing a real category and real-world target — the mechanical enforcement of "must
     not display duplicate badges," since a well-formed disposition file doesn't itself guarantee
     the suppressed badge was actually removed from the text. Both files reuse `check_content_
     unit_evidence_resolves` UNCHANGED for evidence resolution — both key entries on `unit_id`,
     which is all that function ever reads.
   **(MT042, Thirty-Second incident, 2026-08-14) — the badge row has a verified FLOOR, not just
   reconciliation:** everything above stops a real OLD badge from being silently lost — it
   vacuously passes when the old README has zero badges, exactly the gap that let a real
   clean-room candidate ship with a single License badge while every other currently-shipped
   candidate in the portfolio has 2-5 (zero exceptions, full 30-product survey).
   `_detect_available_badges` (`readme_refresh_run.py`) computes the real, per-category
   availability from data this pipeline already has — `_detect_license_file`, `_detect_install_
   info`/`data/package_registry.json`, the real `DependencySnapshot`'s `native_system` bucket,
   `_detect_dev_test_artifacts`'s CI-workflow list, and a resolvable `repo_full_name` — into
   `factpack["available_badges"]`. `check_badge_row_meets_verified_floor` (hard gate) requires a
   License badge whenever one is genuinely available, plus at least one more badge from ANY of
   `{package_version, language_version, ci_build_status, contributor_count}` whenever at least
   one of those is genuinely available — it never mandates a SPECIFIC second category (6 of 30
   real products show CI/build in that slot instead of Contributors, a legitimate editorial
   choice). Safe as a hard gate, unlike `check_installation_matches_package_registry` below:
   `contributor_count` needs nothing but a resolvable `repo_full_name`, so the floor can always
   be satisfied by License + Contributors even when every other category is unavailable or the
   registry data is wrong. `check_badge_available_fact_not_shown` (heuristic) separately prompts
   — never mandates — adding a badge for any OTHER genuinely available category not yet shown.
   **Composition-time discipline this incident names explicitly, generalized beyond badges**:
   before adding a new visible template element sourced from external/structured data (a badge,
   a link, a claim), confirm it has BOTH (a) a `_detect_*` factpack function drawing from real,
   already-available data, and (b) a verifying check confirming the candidate reflects it
   correctly — never rely purely on reconciliation-from-old-content or unaided agent judgment
   for a fact this pipeline can verify. This is the fourth independent instance of the same gap
   found in this plan's history (the Enterprise Edition link, the banner-homepage link, the
   Installation-vs-registry match, now badges) — each time, a real, verifiable fact was left to
   unaided judgment with no `_detect_*`+check pairing until a specific product's content exposed
   it.
   **(MT041, Thirty-First incident, 2026-08-14) — dependency accuracy, hard gates:** the
   `## Dependencies` section's data must exist and be internally consistent
   (`check_dependency_snapshot_completeness`), no unqualified absolute dependency-absence claim
   anywhere in the candidate (`check_unqualified_dependency_claims` — the Claims Policy, see the
   composition guidance above), a Required-section bullet's name must be a real, direct entry in
   the manifest (`check_dependency_direct_transitive_confusion`), an optional/dev-only dependency
   must never be listed under Required (`check_dependency_optional_presented_as_required`/
   `check_dependency_dev_only_presented_as_runtime`), the Intro paragraph's own real dependency
   names must never be contradicted by an unqualified claim elsewhere in the file
   (`check_dependencies_intro_contradiction` — the exact same-document-contradiction shape the
   real `cells/rust` defect had), a Native and System Requirements bullet must never be
   duplicated verbatim in Scope and Limitations
   (`check_dependency_native_system_scope_limitations_placement`), and every `5_dependency_claim`
   disposition entry's evidence must cite the real manifest path or a real dependency name, never
   narrative-only evidence (`check_dependency_disposition_reconciliation`).
   **Heuristic checks** (surfaced for
   judgment, never auto-fail): mechanism-duplicate output nodes, process-narration smells (now
   covering internal receipts/execution notes/provenance/confidence language, not just the
   original 22 incident-specific phrases), Enterprise Edition anchor-text naming *and* context
   (must explain the broader/full functionality gained, not be a naked CTA — standard anchor text
   is `"Enterprise Edition"`, decided 2026-08-08), section-job distinctness (intro vs. Key
   Capabilities overlap), a weak API-reference intro sentence, and named-member accuracy (a
   grep-based heuristic — see that function's own docstring for its honest, stated scope limits,
   most importantly that it does not trace inheritance), and (**MT030**) content-unit
   classification plausibility (a mechanical narrative/CTA tone prefilter cross-checked against
   the agent's own stated classification), probable-duplicate content-unit merges (2+ shared
   salient tokens into the same section with a non-identical excerpt), and (**MT031**) an
   embedded-actionable-fact tripwire flagging an excluded narrative/CTA unit whose excerpt
   contains a real request/contact phrase worth re-examining, and (**TC-HARDEN-32**, MT035,
   2026-08-12) whether the `## Installation` section's real content agrees with `data/
   package_registry.json`'s own `published`/`candidate` fields for this product — deliberately
   a heuristic, not a hard gate, per direct live evidence found the moment this check first ran
   against real content: that registry file was independently wrong, in both directions, for
   real products already in this portfolio (`words/net`'s real, live NuGet package contradicts
   its own `published: false`; `email/net`'s real nuspec casing contradicts its own
   `candidate.name` casing) — the same "even structured, checked-in data isn't infallible"
   lesson `formats.md` already taught this plan. `check_diagram_
   suspicious_direct_product_edge`/`check_diagram_capability_unreachable_from_product` are
   retired — both were tripwires for a per-node-edge defect class the simplified model can no
   longer produce. (**MT041**, 2026-08-14) `check_dependency_section_manifest_corroboration` —
   cross-checks the Required-section bullets against `knowledge/{family}/{platform}/merged/
   claims.json`'s own "kind": "dependency" claims; deliberately heuristic, since those claims
   are confirmed to be a lossy, name-only re-parse of the SAME manifest at a possibly different
   revision (`scout.py` → `package_manifest.py` → `claims.py`), never independent corroborating
   data — `check_dependency_version_pin_freshness`, flagging a prose-cited version that
   doesn't match the manifest's real constraint (routinely a legitimate range-vs-point
   difference, so a prompt, never a block) — and `check_dependency_scope_claim_matches_evidence`
   (a scoped "no proprietary runtime"-shaped claim's category has real corroborating snapshot
   data), **downgraded from an originally-planned hard gate the moment it ran against real
   content**: no extractor today populates the `proprietary_runtime` category at all, so this
   check's only possible outcome is "always flag" — including against this skill's own
   sanctioned GOOD-example phrasing (composition guidance above) — the same "don't hard-gate on
   a claim category with no real verifier behind it" lesson `check_installation_matches_
   package_registry` already taught this skill (TC-HARDEN-32).
   Transitions `PLANNED → VERIFYING_EXAMPLES` only once every hard gate passes.

5. **`verify-examples`** — runs the (pluggable) per-language compile/run verification pass and
   writes `verification/result.json` plus `upstream-issues.md` (written for every run, including
   the clean case — an absent file is itself a bug). **Honest scope note**: the default runner
   reports every code block `BLOCKED-WITH-REASON: TOOLCHAIN-UNAVAILABLE` rather than claiming a
   compile that never happened — real per-language toolchain wiring (`javac`/`javap`, `dotnet`,
   `go build`, `cargo`, `cmake`/`ninja`, a disposable Python venv, `tsc`) is separate, follow-on
   work, injectable via `configure(verification_runner=...)`. Only transitions
   `VERIFYING_EXAMPLES → AWAITING_REVIEW` once every block has a real, named status.

6. **`recheck`** — re-runs the deterministic checks in place after manual edits during
   `AWAITING_REVIEW`, without a state transition. Use this after applying reviewer feedback
   instead of re-planning from scratch.

7. **`approve`** — **the skill must never call this on its own initiative; only on an
   unambiguous, fresh instruction from the user in that turn.** Re-verifies the pinned clone-cache
   `HEAD` hasn't drifted since `start`; if it has, forces the run back to `PLANNED` for re-review
   rather than approving stale content — `approve` itself will raise in that case, it never
   silently substitutes a replan for an approval.

8. **`push`** — disposable-clone + branch + git-plumbing commit (`write-tree`/`commit-tree`/
   `update-ref`, never the shared clone cache) + surgical-diff check (declared file set only,
   currently just `README.md`) + push + `gh pr create` (**no `--draft`**, MT032, 2026-08-10/11 —
   none of these repos have branch protection or a second reviewer, so draft mode was pure
   friction with no offsetting safety benefit; the human review step still happens, just at
   "review the PR before merging" rather than "review, unmark draft, review again"). `--dry-run`
   rehearses every step up to (not including) the live network write, then returns the run to
   `APPROVED` — it never reaches `PUSHED` without a real push. The plumbed commit's message
   carries the real `Co-Authored-By: {real acting session's model} <noreply@anthropic.com>`
   trailer, read fresh each time, never hardcoded.

   **Merging (only on the user's explicit, this-PR-specific go-ahead after their own manual
   review — never on this skill's own initiative)**: `gh pr merge {number} --squash
   --delete-branch`, but **always with explicit `--subject`/`--body` (or `--body-file`), never
   accepting `gh`'s own default squash-message construction** (2026-08-13, cells/cpp healing
   pass — a real, confirmed defect). GitHub's default squash-commit-message builder auto-appends
   a `Co-authored-by:` trailer for the underlying plumbed commit's own git-level Author identity
   (the human operator, e.g. `babar-raza <babar-raza@users.noreply.github.com>`) **in addition
   to** correctly setting that same person as the merge commit's real Author — a redundant,
   incorrect self-citation: the primary author is already attributed via git's own Author/
   Committer metadata (which GitHub displays natively, no trailer needed); `Co-authored-by` is
   for genuinely *additional* contributors only. **The merged commit's trailer section must
   contain exactly one line**: `Co-authored-by: {real acting session's model} <noreply@
   anthropic.com>` — never the human operator's identity, in any email form, as a co-author.
   Build the `--body` text by hand from the plumbed commit's own real message plus that one
   trailer; do not let `gh pr merge` construct it.

9. **`verify`** — post-push, safely re-runnable any time: confirms the PR still exists and its
   head matches the approved candidate.

## Onboarding a new product, platform, or family (TC-HARDEN-35, MT035, 2026-08-12)

No such section existed anywhere in this repo before this one — confirmed by an exhaustive
search of this file, `AGENTS.md`, and `skills/registry.json`'s S-120 entry (no `dependencies`
field). This section describes the **real, current** behavior of the checked-in code as of
2026-08-12, not an aspirational future state — it will be extended as `TC-HARDEN-33` closes
(see the plan's Twenty-Second incident / MT035 section for the full evidence trail behind every
claim below: `C:\Users\prora\.claude\plans\d-users-prora-onedrive-documents-github-humble-tome.md`).

**1. The real prerequisite chain — mechanically load-bearing, not just recommended.** Run
`/repo-scout` → `/knowledge-enrich` → `/truth-merge` for the new product **before** attempting
`plan`/`ingest-candidate`. This is not a soft suggestion: `check_diagram_verified_format_claims`
(a hard gate) requires 2 of 3 independent signals (`formats.md` row / prose mention / real source
evidence) to accept any format claim in the diagram's `Starting Points`/`Outputs` containers —
with no `knowledge/{family}/{platform}/merged/formats.md` and no `api_surface.json`, only the
prose signal can ever be true (1 of 3), so **every real format claim in the diagram will
mechanically fail to verify** until the knowledge pipeline has run at least once.

**2. Which data files need a new row, and which correctly default:**

| File | New product needs an entry? |
|---|---|
| `data/products.json` | **Yes, required.** `family`, `platform`, `repo_url`, `clone_url`, `active: true` at minimum — `_resolve_product` (TC-HARDEN-30, fixed 2026-08-12) now validates `repo_url`/`clone_url` are present and raises a clean `README-REFRESH-RUN BLOCKED: ... missing required field(s): ...` message if either is missing or the file has a JSON syntax error, rather than a raw traceback. |
| `data/registry_exclusions.json` | Only if the product should be excluded from this skill's coverage. |
| `data/diagram_archetypes.json` | No entry needed by default — absence correctly defaults to `transform`. Add an entry only if the product is genuinely `hybrid`/`generative`/`compile` (Template section's 3-condition hybrid test, or the equivalent generative/compile tests). |
| `data/families.json` | **Yes, required for a genuinely new FAMILY** (not a new platform of an existing family) — see the disclosed gap in item 4 below; this is not yet mechanically enforced if forgotten. |
| `data/aspose_com_targets.json`, `content/products.aspose.org/en/{family}/{platform}/`, `content/reference.aspose.org/en/{family}/{platform}/` | No entry required before a first run — each degrades gracefully (see item 3), but the resulting candidate will carry real, visible gaps (no Enterprise link, no homepage-linked banner, no API Reference table) until the real content exists. |

**3. What to expect on a first real run, before knowledge/content exist yet:**
- The diagram's `Starting Points`/`Outputs` containers cannot carry any real format claim yet
  (item 1) — compose the rest of the candidate, but expect `diagram_verified_format_claims` to
  block until `/repo-scout` has run at least once.
- `check_api_reference_classes_exist_in_reference_site` (TC-HARDEN-31, fixed 2026-08-12) now
  **correctly blocks**, with a real named finding per cited class, rather than silently passing
  — the exact opposite of its pre-2026-08-12 behavior, which produced zero findings
  (indistinguishable from "verified clean") when neither `content/reference.aspose.org/.../
  _index.md` nor the clone cache existed yet. Do not compose the curated API Reference bullet
  detail (the `` - `ClassName` `` convention) until at least one of those two sources is real —
  the MT028 mechanically-generated table has the same real dependency anyway.
- `check_dev_test_artifacts_linked`, `check_no_undisclosed_blocking_commands`, and similar
  clone-cache-scanning checks degrade gracefully with an empty clone cache (nothing found means
  nothing is required) — safe to run before `/repo-scout`, unlike the two checks above.

**4. Fixed since this section was first written (2026-08-12):**
- **New-language source discovery (TC-HARDEN-34, fixed 2026-08-12)**: `_find_class_source_files`'s
  extension allowlist now also recognizes PHP (`.php`), Kotlin (`.kt`/`.kts`), Ruby (`.rb`), and
  Swift (`.swift`), alongside the original 10 extensions — a deliberate, bounded widening (see
  `_CLASS_SOURCE_EXTENSIONS`'s own docstring), not an open-ended "any extension" policy. A new
  language outside this set is still invisible to `check_named_member_accuracy` and to
  `check_api_reference_classes_exist_in_reference_site`'s clone-cache fallback until the
  allowlist is widened again — a real, bounded, but no longer *permanent* blind spot.
- **Installation-section verification (TC-HARDEN-32, fixed 2026-08-12)**: `check_installation_
  matches_package_registry` now cross-checks the composed `## Installation` section against
  `data/package_registry.json`'s `published`/`candidate` fields — deliberately a **heuristic**,
  not a hard gate, per direct live evidence found the moment this check first ran against real
  content: that registry file was independently confirmed wrong, in both directions, for real
  products already in this portfolio. A finding here is a prompt to check which side (the
  content or the registry) is actually stale, never an automatic "the content is wrong."

**5. Known, disclosed gaps not yet fixed — do not assume these are handled:**
- **`data/families.json` consistency (TC-HARDEN-33)**: this is a separate, hand-maintained
  registry from `data/products.json`, not derived from it. If you add a genuinely new family to
  `products.json` without also adding it to `families.json`, `check_no_cross_product_citation`'s
  family allowlist silently stops catching *any other product's* citation of the new family — no
  warning is raised. Add the new family to `data/families.json` manually; nothing currently
  reminds you if you forget.

## Post-conditions

- `AWAITING_REVIEW`: candidate has passed every hard-gate deterministic check and every code
  block has a named verification status.
- `PUSHED`: a draft PR is open against the product's real default branch, with `README.md` as
  the only changed file, evidence recorded at `reports/readme_refresh_runs/{family}/{platform}/
  {run_id}/` and `reports/repo_presenter_actions.jsonl` (once that shared ledger is built —
  not yet wired into this pass).

## Error handling

- `start`: pre-flight access failure, product not found/excluded, or an already-active run for
  the same product all raise before any state is created.
- `ingest-candidate`: any hard-gate finding raises with `checks/result.json` written first, so
  the specific failing check is always inspectable, not just a bare failure message.
- `verify-examples`: raises if any code block has no named status; never silently advances.
- `push`: any failure (clone, plumbing, surgical-diff mismatch, network push, `gh pr create`)
  transitions the run to `BLOCKED` with the failure reason recorded, rather than leaving it in
  an ambiguous `PUSHING` state — `recover` resumes from `resume_state` afterward.

> **Skill context close** — run after the last step:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py end --skill S-120 --status completed
> ```
