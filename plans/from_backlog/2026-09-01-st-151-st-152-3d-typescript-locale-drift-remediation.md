# ST-151/ST-152: 3d/typescript locale template drift — investigation + fix plan
> Created: 2026-09-01
> Source: /backlog plan — ST-151, ST-152 (backlog/inbox.md), promoted to Active
> Status: active
> Predecessor: C:\Users\prora\.claude\plans\scalable-mixing-stonebraker.md (ephemeral,
> per-user Claude Code plan file — this file is the durable, git-tracked copy; keep
> both in sync going forward, but treat this one as authoritative for continuity)

## Context

Backlog rows ST-151 and ST-152 (`backlog/inbox.md`) both describe the same underlying
defect, filed 2026-08-31 during MT040 Phase I, re-scoped the same day (commit
`df51cfef565e`) once the investigator realized it was bigger than first thought:

**What actually happened, in plain English:** on 2026-04-03 (commit `9b3bfa469c`),
the English API-reference pages for `3d/typescript`'s `mesh.md` and `scene.md` were
regenerated onto a new, simpler page template — a short "Overview / Properties /
Methods (one summary table) / See Also" shape. Before that date, the template was a
much longer one: a per-method breakdown, each method getting its own `### ` heading
with prose, parameters, and worked examples. When English switched templates, nobody
went back and re-translated the locale (non-English) copies of these two pages — they
were left frozen on the old, now-retired template. Translators had patched small
wording fixes into those old-template locale pages since then (as recently as July),
but never rebuilt their *structure* to match. The result: today, a Spanish or Russian
reader of `mesh.md` sees 8 method-detail subsections (`createPolygon`, `triangulate`,
`static union`, …) that don't exist anywhere on the English page anymore, some of them
containing details that are now factually wrong (e.g. an enum value written as
`TextureMapping.Diffuse`, when the real member is `TextureMapping.DIFFUSE`).

**Confirmed scope (I re-ran the actual checker live rather than trusting the
backlog's hand-counted figure):** the repo already has a purpose-built structural
checker for exactly this — `scripts/pipeline/commands/ops/check_locale_topology.py`
(RG-004), which compares the count/order of `## ` headings between an English page and
each locale copy. Running it fresh against both files:

```
mesh.md:  36 locales checked, 36 mismatches  (100%)
scene.md: 36 locales checked, 36 mismatches  (100%)
```

So it's **72 files across all 36 non-English locales**, not the 53-55 the backlog
recorded — the backlog's count only caught one of four distinct drift shapes (the
"old full per-method template" shape, ~27 locales/file); it missed three more shapes
that trip the same checker: 7 locales missing just the "See Also" section, 2-3 locales
with an extra "Description" section, and 2-3 locales (hr, sr) that have lost their `##`
headings entirely. All are pre-existing (confirmed unrelated to any recent session —
the same drift pattern reproduces on pages nobody has touched recently) and none are
fixable by this repo's normal locale-patch tooling.

**Why the normal tooling can't fix this (the actual root cause):** the mechanism that's
supposed to keep locale pages in sync, S-107 (`locale_refresh_handoff.py`), only knows
how to route *literal text edits* — "this English sentence changed, patch the matching
sentence in the locale file." It has no way to represent "this whole section was
removed" (there's no new text to patch *to*), and it never checks whether a locale
file's heading structure still matches English at all — RG-004 exists as a standalone
script but isn't wired into S-107's decision-making. So when English fully restructured
these pages in April, S-107 had nothing to say about it, and the drift just sat there
for 5 months.

**Two additional real bugs found while reading the actual code** (not previously in the
backlog), both in `locale_refresh_handoff.py`, both worth fixing in the same pass since
we're already touching this function:
- `KNOWN_LOCALES` (line 52-57) is missing `"hi"` (Hindi), even though
  `content/reference.aspose.org/hi/...` exists and is populated — S-107 silently never
  discovers Hindi locale files for *any* product today.
- `SKILL_LARGE = "S-56"` (line 47) is stale: per `docs/registries/skills.md:69`, skill
  ID **S-56 has been reassigned** to `new-docs-page` ("Generate documentation pages")
  — a completely unrelated skill. So today, any "large change" locale-handoff routes to
  the wrong skill entirely. The correct current skill for page-level re-translation is
  `S-HT-01` (`ht-translate`, single-page translation via hugo-translator).

## Plan verification (second pass, live-checked 2026-09-01)

Before treating this plan as execution-ready, every governance/tooling claim it
depends on was re-verified against the live repo rather than reused from the first
drafting pass. Five corrections and one hard constraint came out of that pass:

1. **`override_manager.py` lives at `scripts/pipeline/commands/governance/
   override_manager.py`**, not `.../ops/...` as earlier drafted.
2. **Only `skills/` (plus a short `FORBIDDEN_EXACT` list and `docs/governance|
   workflows|registries/`) is actually protected**, per the live `path_guard.py`'s
   `FORBIDDEN_PREFIXES`/`ALLOWED_PREFIXES`. `scripts/pipeline/` and `scripts/ci/` are
   explicitly *allowed* — `skills/commit.md` §D's "scripts/ (all subdirectories)" text
   is itself stale (drifted since 2026-04-03) and should not be trusted. Consequence:
   TC-LOCALE-01's override token only needs to cover the `skills/locale-refresh-
   handoff.md` + 3 mirror paths, not `locale_refresh_handoff.py` or its test file.
3. **`check_skill_mirror_parity.py` takes `--staged-files <paths>`, not `--check`** —
   only `sync_skills.py` has a `--check` flag. Corrected below.
4. **`/commit` (S-76) does not push, and does not run fully unattended by default.**
   Pushing to `origin/main` is a separate step (`GH_TOKEN`, non-interactive, per
   `CLAUDE.md`'s "Git Push" section) that must be added explicitly after each commit.
   More importantly: S-76 Step B.5 requires **live confirmation of the staged commit
   plan** before it proceeds, and its only documented bypass (`--auto`) is reserved for
   orchestrating skills (e.g. S-84) calling `/commit` internally — not something a
   standalone invocation can legitimately claim. This is a real, intentional
   governance checkpoint, not agent over-caution: a review-and-approve gate is exactly
   the kind of thing that isn't an agent's to route around. **This plan cannot run as
   a fully unattended single pass** — it has two built-in pause points, both at
   `/commit` invocations (TC-LOCALE-01-04, TC-LOCALE-02-06), where the run legitimately
   stops and hands back to whoever is supervising it, rather than inventing a way past
   the checkpoint.
5. No "swarm"/"lane ownership" concept exists anywhere in this repo. The closest real
   mechanisms — `session_ledger.py adopt` (refuses paths another live session already
   claims), `skill_context.py begin/end` (an execution lease over a real, non-wildcard
   path scope), and `git_plumb_commit.py` (the sanctioned ST-021 git-index-contention
   mitigation) — are wired into TC-LOCALE-00 below instead of inventing new vocabulary.
6. Backlog status vocabulary: `fix_planned` does not exist in this repo. Use
   `in-progress` while the taskcards below are executing; on close, append
   `resolved:{date} — {summary}` to the ST-151/ST-152 rows in place, matching how every
   other closed row in that table is annotated (there's no separate "done" table).

## What the fix is, in plain English

Two pieces, in this order:

1. **Close the tooling gap first.** Teach S-107 to run the same structural check
   (RG-004) it already has sitting unused in the repo, on every locale file it
   considers, and give it a new routing category — `STRUCTURAL_DRIFT` — that always
   points at real re-translation (`S-HT-01`), never at the text-patch skill (`S-75`),
   which is safe by its own documented rules only for small literal edits. Fix this
   *before* the content fix so the content fix can be verified and file-scoped by
   running the corrected tool, and so this class of defect can't silently reaccumulate
   the next time an English template changes.

2. **Regenerate the drifted files** by re-translating the current English
   `mesh.md`/`scene.md` into all supported locales via `S-HT-01` (`ht-translate`) — the
   currently-supported, non-retired translation tool — rather than hand-patching. This
   naturally produces pages with the current 4-section structure and no orphaned
   content, because it's a full regeneration from the current source, not a text diff.
   Verify success by re-running RG-004 (expect zero mismatches) plus a content-eval
   spot-check, then commit through the normal `/commit` (S-76) path.

## Execution log (real findings from the live run, 2026-09-01)

TC-LOCALE-00 and TC-LOCALE-01 are CLOSED — see per-taskcard status below for evidence.
While starting TC-LOCALE-02, three things were learned that change its plan versus what
was drafted before execution began, recorded here rather than silently overwritten:

1. **Real concurrent-session git-index contention hit live**, exactly the ST-021 class
   CLAUDE.md warns about: mid-staging, `scripts/pipeline/tests/test_mission_id_ledger.py`
   appeared in `git diff --staged` without ever being added by this session — another
   live session was mutating the shared index at the same time. Recovered by
   `git restore --staged` on the stray path, then switched to `git_plumb_commit.py`
   (isolated temp index, never touches the real `.git/index`) for the actual commit
   instead of a plain staged `git commit` — exactly the tool's documented purpose.
2. **`ht-translate`'s own skill doc is more restrictive than the underlying CLI needs.**
   `hugo-translator`'s `--input` flag directly accepts a single file, not just a
   directory (confirmed via a live dry-run: `Input: .../mesh.md`, `would_translate`
   listed exactly 1 job, 0 skips). This is strictly better than the plan's original
   "staged 2-file temp directory" idea — no staging step needed at all, and it can
   never bleed into the other 154 sibling files under `en/3d/typescript/`.
3. **Real bug found in `hugo-translator` itself** (external repo, out of scope to fix
   here): `src/cli.py` line ~1942, the per-language subprocess dispatcher copies
   `--force-accept` into each child invocation but never copies `--i-understand-data-loss`
   alongside it — confirmed by reading the source, not just observing the failure. Any
   invocation with 2+ `--target-langs` fails immediately (`ERROR: --force-accept requires
   --i-understand-data-loss`) for every language. Single-language invocations don't hit
   this (no subprocess dispatch in that path) and work cleanly. **Workaround: always
   invoke with exactly one target language at a time.**
4. **Pivoted off local GPU inference per explicit instruction.** The default model
   (`m2m100_418m`, local NMT, GPU-loaded) took several minutes per single-file/
   single-locale invocation just for model load + inference — for 72 files × 36 locales
   that's an impractical multi-hour GPU-bound run, and two other live sessions
   (`hugo-translator-89`, `hugo-translator-82`) are concurrently using the same local
   GPU tool right now. Switched to the `professionalize_llm` model
   (`config/model_registry.yaml`: `base_url: https://llm.professionalize.com/v1`,
   OpenAI-compatible, already the configured escalation model for several
   MT-failure-prone locales in `config/global.yaml`) via `--model professionalize_llm`.
   Carries the LLM Metrics Obligation per AGENTS.md §15 (ht-translate.md's own note) —
   record this in TC-LOCALE-02-05's evidence.

**Revised TC-LOCALE-02-02 decision** (supersedes the original staged-subset-vs-directory
framing): use single-file `--input` (no staging), one locale at a time (works around the
dispatch bug), `--model professionalize_llm` (per pivot above).

## Batch-1 pilot results + open decisions (2026-09-01, post-approval — READ BEFORE
## RESUMING TC-LOCALE-02-03/02-04)

TC-LOCALE-02-01 confirmed live, unchanged: 36/36 mismatches both files. Saved to
`reports/plan_execution/st-151-st-152-locale-drift/rg004-{mesh,scene}-before.json`.

TC-LOCALE-02-02's pilot (es/mesh.md) succeeded: RG-004 0 mismatches, evidence block
content matches English exactly (cosmetic YAML re-indentation only), no transliteration,
`translation_fidelity: score 1.0, verdict: pass`. Real cost measured: **5m39s wall-clock
for one file/one locale** (mostly LLM round-trip + the tool's own fidelity-check pass).

A follow-up 8-locale batch (both files = 16 invocations) was run to spot-check quality
diversity across all four drift shapes (old-template, missing-See-Also, extra-Description,
headings-stripped) and across scripts (Cyrillic/CJK/RTL). Results — **two new, real,
scope-changing findings, not yet acted on**:

### Finding A — 11 of 36 locale directories are NOT translatable via ht-translate at all

`hr` and `sr` failed immediately: `ERROR: Locale(s) ['hr'/'sr'] are not in the allowed
locale set for site 'reference.aspose.org'`. Root cause: `hugo-translator`'s
`config/site_profiles/reference.aspose.org.yaml` has `strict_locale_allowlist: true`
with only **25 approved locales** (same 25 used fleet-wide, e.g. identical list in
`docs.aspose.org.yaml` — confirmed via `git log`, this is a deliberate policy
("`feat(locale-policy): generalize Aspose.org locale allowlist to any site`"), not a
bug to route around.

Exact set (computed via script against real directory listing, not estimated):
- **25 approved, translatable**: ar, cs, de, el, es, fa, fr, he, hi, hu, id, it, ja, ko,
  nl, pl, pt, ro, ru, sv, th, tr, uk, vi, zh
- **11 NOT approved, cannot be translated via ht-translate right now**: bg, ca, da, fi,
  hr, lt, lv, ms, no, sk, sr

This means the achievable deliverable via ht-translate is **50 files (25 locales × 2)**,
not all 72. The other **22 files (11 locales × 2)** remain structurally drifted and need
a separate, explicitly-scoped follow-up (extend the hugo-translator allowlist — external
repo, real scope/risk of its own — or another mechanism not yet identified). Do not force
past `strict_locale_allowlist` — it is a deliberate gate, same class as this plan's own
"never force past a genuine new problem" rule for `--force-accept`.

### Finding B — `--force-accept` is masking real translation-fidelity defects

The tool's own `translation_fidelity` self-check (written into each output file's
frontmatter) flagged real problems on 2 of the 8 batch-1 locales, force-accepted into
the output anyway because `--force-accept` (required by the documented `ht-translate`
command) skips validation entirely rather than retrying:
- **de-mesh: score 0.6, verdict `warn`** — "public members" mistranslated as "public
  users", a boolean-return meaning lost on `isManifold`, `referenceMode` garbled to
  "referenceMade"
- **fr-mesh: score 0.6, verdict `warn`** — "mesh" mistranslated as "grille" (grid),
  encoding-garbled text, "mixed language" in 3 method descriptions
- **fr-scene: score 0.8** — the product name itself came out wrong in the See Also link:
  **"Objectif 3D" instead of "Aspose.3D"** — a real product-name defect, the exact class
  of thing `ht-translate.md` Step 6's review checklist exists to catch, that a
  transliteration-pattern grep does NOT catch (it's a full mistranslation, not a
  phonetic transliteration)
- The other 8/12 files (ru, zh, ar, ja — both files; de-scene) scored 0.9–1.0,
  `verdict: pass`

`--force-accept` is documented (`ht-translate.md`) as being for known CJK/RTL false
positives (`FrontmatterLanguageCheck` flagging English product names) — it's not clear
it should also apply to Latin-script locales like `de`/`fr`, where it may be suppressing
genuine defects the tool's own (non-forced) validation+retry logic would otherwise catch.

### Two decisions were pending user input when this file was written (interrupted before
### an answer was given — resolve before resuming TC-LOCALE-02-03/02-04)

1. **Locale-coverage gap (Finding A)**: scope TC-LOCALE-02 down to the 25 approved
   locales now (50 files) and file the 11-locale gap as a new, explicitly-scoped
   follow-up backlog item — same pattern as how ST-151/152 themselves were filed — OR
   investigate extending hugo-translator's allowlist first (adds scope/risk, touches an
   external repo's config).
2. **Quality-gate policy (Finding B)**: re-run without `--force-accept` for Latin-script
   locales (keep it only for the documented CJK/RTL locales: zh, ar, he, fa, hi, ko, ja,
   th, vi) so the tool's own retry logic catches fidelity problems instead of silently
   writing them — OR keep force-accept for all locales (matches the skill doc exactly)
   but gate on `translation_fidelity` score/verdict after the fact, rerouting anything
   below a threshold for manual re-translation/review.

**Recommended default if resuming without further input**: Finding A → scope down to 25
locales, file the gap as a follow-up (lowest-risk, matches this plan's own established
"don't force past a deliberate gate" precedent). Finding B → re-run de/fr without
`--force-accept` first (cheap to test — 2 locales, not a full-strategy commitment) and
decide the full-batch policy based on whether that actually improves the fidelity score,
rather than guessing.

## Execution control layer (scoped taskcards)

This plan is small enough (one ~30-line code change + tests, one content-regeneration
pass) that it doesn't warrant a full mission-scale taskcard apparatus (dependency DAGs,
per-dimension numeric quality scoring, standalone CSV/YAML traceability files). What
follows is a right-sized version: every actionable item below is a taskcard with an ID,
explicit scope, dependencies, micro-steps, acceptance checks, evidence, and a rollback/
stop condition — kept as sections of this one plan file rather than spun out into
separate artifacts.

**Requirement IDs** (source: this plan's Context section):
- `REQ-LOCALE-01` — S-107 must detect and route structural (H2-topology) locale drift,
  not just literal text edits, so this class of defect can't silently reaccumulate.
- `REQ-LOCALE-02` — The structurally-drifted `3d/typescript` `mesh.md`/`scene.md` locale
  files must be regenerated to match the current English template (scope: the 25
  hugo-translator-approved locales — see Finding A above for the 11-locale exclusion).

**Status legend** (applies to every taskcard/micro-step below):
`TODO → IN_PROGRESS → IMPLEMENTED → VERIFIED → CLOSED`, with `BLOCKED` and `REROUTED`
(send back to `IN_PROGRESS` with a recorded reason) reachable from any non-`CLOSED`
state. A parent taskcard may move to `CLOSED` only when every child below it is
`CLOSED` and its own acceptance checks pass — not merely because children exist.

**Dependency note:** TC-LOCALE-02 (content regeneration) does **not** hard-block on
TC-LOCALE-01 (tooling fix) — B1's discovery step can run the standalone
`check_locale_topology.py` CLI directly, which already exists and needs no code change.
Doing A before B is still the recommended order: it fixes the stale `SKILL_LARGE`
routing and gives B a corrected, tool-verified file list instead of a hand-derived one.
Treat this as a soft/recommended ordering, not a gate.

---

### TC-LOCALE-00 — Backlog state + coordination setup [PARENT]
Status: **CLOSED** (2026-09-01) · Runs first, before TC-LOCALE-01/02 make any edits.

- **TC-LOCALE-00-01 — Claim scope and mark backlog in-progress** [CHILD, **CLOSED**]
  - MS-01: `session_ledger.py adopt` the real file scope this plan will touch (the
    exact paths named in TC-LOCALE-01/02's Scope lines — not a wildcard). This is the
    repo's actual concurrency-safety mechanism — it refuses to proceed if another live
    session already claims any of these paths; there is no separate "swarm"/"lane"
    concept to invent on top of it.
  - MS-02: `skill_context.py begin --skill S-107 --scope "<real paths>"` before
    starting edits for each parent taskcard, `... end --status completed` after it
    closes — never scope `"*"` (per `skills/commit.md`'s own warning that a wildcard
    scope defeats the overlap-conflict design).
  - MS-03: Edit `backlog/inbox.md`: set ST-151 and ST-152's `status` column from
    `queued` to `in-progress`.
  Acceptance: ledger claim succeeds (or reports a genuine conflicting live session, in
  which case stop and report rather than forcing it); both rows show `in-progress`.
  Evidence: `session_ledger.py` claim output; diff of the two backlog rows.
  **Result:** `skill_context.py begin --skill S-107` succeeded, no conflicting live
  session. ST-151/ST-152 both edited to `in-progress` in `backlog/inbox.md`.

---

### TC-LOCALE-01 — Wire RG-004 into S-107 routing [PARENT]
Status: **CLOSED** (2026-09-01) · Satisfies: `REQ-LOCALE-01` · Depended on TC-LOCALE-00 CLOSED
**Result:** commit `6186b9768188c170b1cff51f75883402bfe996b7`, pushed to `origin/main`
(verified: `git log -1 origin/main` matches). All 4 children CLOSED. 12/12 scoped tests
passed. `sync_skills.py --check` PASS, `check_skill_mirror_parity.py` PASS. Committed via
`git_plumb_commit.py` (isolated index) after live ST-021-class contention was observed on
the real index — see Execution log above. 39/39 pre-commit gates passed (2 skipped, N/A).
Scope — allowed: `scripts/pipeline/commands/content/locale_refresh_handoff.py`,
`scripts/pipeline/tests/content/test_locale_refresh_handoff.py`,
`skills/locale-refresh-handoff.md` + its 3 mirrors. Forbidden: any other pipeline
module, any content/ file (that's TC-LOCALE-02's scope).
Acceptance (parent-level): all 4 children `CLOSED`; scoped pytest run green;
skill-mirror parity check green; commit landed AND pushed to `origin/main`.
Rollback: single self-contained commit — `git revert` it (never `reset --hard`) if
`pytest scripts/pipeline/tests/content/test_locale_refresh_handoff.py -q` or any
downstream S-107 consumer breaks after push.

- **TC-LOCALE-01-01 — Code change in `locale_refresh_handoff.py`** [CHILD, **CLOSED**]
  Scope: that one file only.
  - MS-01: Add `from commands.ops.check_locale_topology import check_locale as
    _check_h2_topology` near the existing imports. *Done when:* import line present,
    `python -c "import commands.content.locale_refresh_handoff"` doesn't error.
  - MS-02: Add `"hi"` to `KNOWN_LOCALES` (keep the list alphabetically ordered).
    *Done when:* `"hi" in KNOWN_LOCALES`. **Do not also remove `"sl"`** — it's stale
    for `reference.aspose.org` (no populated `sl/` dir there) but real, if thin, for
    `docs.aspose.org`; that's a separate, unscoped decision (see "What this
    deliberately does NOT do").
  - MS-03: Change `SKILL_LARGE = "S-56"` → `SKILL_LARGE = "S-HT-01"`. Confirmed live:
    `S-56` is now `new-docs-page` (`docs/registries/skills.md:69`) — a page-generation
    skill, unrelated to translation; the stale code comment `# translate batch (>= 3
    sentences changed)` (line 47) is itself evidence the ID drifted after S-56 was
    reassigned. **Use `S-HT-01`, not `S-HT-02` (`ht-translate-batch`, the literal
    "batch" skill)**: `_build_handoff_entry` always routes one locale's copy of one
    page, never a whole directory, and S-HT-02's own skill doc copies results back
    with a recursive `cp -r` that can overwrite unrelated sibling files in the target
    locale directory — the wrong shape for this per-page routing. Rewrite the comment
    to `# ht-translate, single-page retranslation (>= 3 sentences changed) — NOT
    S-HT-02/batch: directory-scoped with a recursive copy-back that risks overwriting
    unrelated locale files`. Add `SKILL_STRUCTURAL = "S-HT-01"` with a one-line
    comment: "S-75 is documented unsafe for section-level drift; always route
    structural drift to re-translation." *Done when:* both constants present, no
    other reference to `"S-56"` remains in the file, comment text no longer says
    "batch".
  - MS-04: In `_build_handoff_entry` (current lines 151-176), for each
    `(locale, locale_path)` call `_check_h2_topology(Path(receipt["page_path"]),
    Path(locale_path))`. If it returns a mismatch dict: set `handoff_status:
    "STRUCTURAL_DRIFT"`, `translate_skill: SKILL_STRUCTURAL`, add `topology_detail`
    (the checker's `detail` string) to the entry. This overrides small/large routing
    regardless of text-diff size. Unchanged locales keep today's `QUEUED`/small-large
    path. *Done when:* function returns the new fields on a synthetic mismatched input
    and the old fields on a matched one (covered by TC-LOCALE-01-02's tests, not by
    manual inspection alone).
  - MS-05: Update the module docstring's output schema (top-of-file comment) to
    document `handoff_status: STRUCTURAL_DRIFT` and `topology_detail`. *Done when:*
    docstring lists the new field alongside the existing schema example.
  Evidence: diff of the file; `git diff --stat`.

- **TC-LOCALE-01-02 — Tests** [CHILD, **CLOSED**, depended on 01-01]
  Scope: `scripts/pipeline/tests/content/test_locale_refresh_handoff.py` only.
  - MS-01: `test_structural_drift_flagged_when_h2_mismatch` — locale fixture with a
    different H2 count than source → asserts `handoff_status == "STRUCTURAL_DRIFT"`
    and `translate_skill == lrh.SKILL_STRUCTURAL`.
  - MS-02: `test_structural_drift_overrides_small_large_classification` — a receipt
    that would classify "small" but has H2 mismatch → still routes to `S-HT-01`.
  - MS-03: `test_matching_topology_keeps_existing_queued_path` — H2 counts match →
    unchanged `QUEUED`/small-large behavior (regression guard for existing callers).
  - MS-04: `test_known_locales_includes_hi` — `assert "hi" in lrh.KNOWN_LOCALES`.
  - MS-05: Rename the existing `test_large_change_queued_for_s56` →
    `test_large_change_queued_for_s_ht_01`. Its assertion (`translate_skill ==
    lrh.SKILL_LARGE`) is symbolic, so behavior is unaffected by the MS-03 constant
    change — but the name would otherwise keep claiming "s56" after this fix, which is
    exactly the kind of stale label this plan exists to clean up.
  Acceptance: `pytest scripts/pipeline/tests/content/test_locale_refresh_handoff.py -q`
  passes, 4 new tests present + 1 renamed, no existing test broken.
  Evidence: pytest output captured in the commit's `Verification:` line.

- **TC-LOCALE-01-03 — Skill docs** [CHILD, **CLOSED**, depended on 01-01]
  (executed via `sync_providers.py` rather than hand-editing the 3 mirrors — same
  outcome, safer: it only touched the 4 locale-refresh-handoff paths, confirmed by
  dry-run first.)
  Scope: `skills/locale-refresh-handoff.md` + its mirrors in `.claude/commands/`,
  `.agents/skills/`, `.kilocode/skills/`.
  - MS-01: Rewrite the "Quality Gate (RG-004)" section from "run this manually after
    propagation" to "this now runs automatically per-locale inside every S-107 run;
    the standalone CLI remains available as an independent spot-check/CI gate."
    Document `STRUCTURAL_DRIFT` / `S-HT-01` routing.
  - MS-02: Apply the same edit to the 3 mirror copies.
  Acceptance: `sync_skills.py --check` exits 0; `scripts/ci/checks/
  check_skill_mirror_parity.py --staged-files <the touched skills/ paths>` exits 0
  (its real flag is `--staged-files`, not `--check`).
  Evidence: both command outputs.

- **TC-LOCALE-01-04 — Commit + push Part A** [CHILD, **CLOSED**, depended on 01-01, 01-02, 01-03]
  (committed via `git_plumb_commit.py`, not a plain staged `/commit`, after live
  ST-021-class index contention was observed — see Execution log above; same override
  token, same push destination, same net effect, safer mechanism for the moment.)
  Scope: git staging/commit/push only, no further content edits.
  - MS-01: `scripts/pipeline/commands/governance/override_manager.py create --paths
    skills/locale-refresh-handoff.md .claude/commands/locale-refresh-handoff.md
    .agents/skills/locale-refresh-handoff/SKILL.md
    .kilocode/skills/locale-refresh-handoff/SKILL.md --reason "wire RG-004
    structural-drift detection into S-107 routing" --plan "fix(pipeline): ..."` — only
    the `skills/` paths need a token; `scripts/pipeline/` is an allowed path under the
    live `path_guard.py`, so do not token the `.py` files.
  - MS-02: Run the full scoped test file once more against staged content.
  - MS-03: `/commit` (S-76) — never raw `git commit`. Message includes `Skills
    invoked:` and cites the pytest pass as verification. **Pause here**: S-76 Step
    B.5 presents the staged commit plan and requires confirmation before it proceeds
    — a real governance gate, not something to script around. If running unattended,
    this is where the run legitimately stops and hands back to its supervisor.
  - MS-04: Once committed locally, push: `git push
    "https://x-access-token:${GH_TOKEN}@github.com/Aspose/aspose.org.git" main` per
    `CLAUDE.md`'s non-interactive push section (S-76 itself never pushes).
  Acceptance: commit lands; pushed SHA visible on `origin/main`; `git log -1 --stat`
  shows only the expected files.
  Stop condition: if the override token or pre-commit gate rejects the commit for a
  reason unrelated to this change (e.g. an unrelated protected-path collision), stop
  and report rather than forcing it through.

---

### TC-LOCALE-02 — Regenerate the drifted locale files [PARENT]
Status: **IN PROGRESS** (2026-09-01, batch-1 pilot done, paused for the two decisions
above) · Satisfies: `REQ-LOCALE-02` · Soft-depends on TC-LOCALE-01 (see Dependency note
above — not a hard gate)
Scope — allowed: `content/reference.aspose.org/*/3d/typescript/mesh.md`,
`content/reference.aspose.org/*/3d/typescript/scene.md`, scoped to the 25
hugo-translator-approved locales per Finding A above (English untouched — it's the
source, not a target). Forbidden: any other file under `en/3d/typescript/` (156 total
files live there; only these 2 are in scope — a recursive directory copy-back is
explicitly forbidden, see TC-LOCALE-02-03 MS).
Acceptance (parent-level): all children `CLOSED`; RG-004 reports zero mismatches for
both files across the 25 in-scope locales; commit landed. (11-locale gap tracked
separately, not part of this taskcard's acceptance — see Finding A.)
Rollback: revert the content commit; English source file is never modified by this
taskcard so rollback has no cross-file blast radius beyond the locale files touched.

- **TC-LOCALE-02-01 — Authoritative file list** [CHILD, **CLOSED**]
  **Result:** confirmed live, unchanged from planning: 36/36 mismatches both files.
  Saved to `reports/plan_execution/st-151-st-152-locale-drift/rg004-{mesh,scene}-before.json`.

- **TC-LOCALE-02-02 — Pilot: translation input/backend approach** [CHILD, **CLOSED**]
  **Result:** single-file `--input` (no staging needed), one target language per
  invocation (works around the confirmed `hugo-translator` dispatch bug),
  `--model professionalize_llm` (pivoted off local GPU per explicit instruction).
  Pilot (es/mesh.md) succeeded with high quality — see Batch-1 section above.

- **TC-LOCALE-02-02b — Batch-1 spot-check (8 locales × 2 files)** [CHILD, **CLOSED**,
  added during execution, not in the original plan] — see "Batch-1 pilot results" above
  for full findings. 12/16 files succeeded with good-to-excellent quality (RG-004 clean,
  no transliteration/placeholder leakage, fidelity 0.8-1.0 on 10/12); 2/12 (de-mesh,
  fr-mesh) scored 0.6/warn — real mistranslations force-accepted through; 4/16 (hr, sr
  × 2 files) failed outright — locale-coverage gap (Finding A). **Both findings require
  a decision before TC-LOCALE-02-03/02-04 resume at full scale** — see "open decisions"
  above.

- **TC-LOCALE-02-03 — Translate `mesh.md` (25 approved locales)** [CHILD, TODO,
  depends on 02-02b decision]
  - MS-01: For each of the 25 approved locales (7 already done: es [pilot], ru, zh, de,
    ar, fr, ja [batch-1]; de/fr pending the Finding-B decision on whether to redo
    without `--force-accept`), run single-language, single-file (do not combine
    multiple `--target-langs` in one call — Execution log point 3):
    ```
    cd hugo-translator && .venv/Scripts/python -m src.cli \
      --site reference.aspose.org \
      --input "d:/onedrive/Documents/GitHub/aspose.org/content/reference.aspose.org/en/3d/typescript/mesh.md" \
      --output "<per-locale temp output dir>" \
      --target-langs {locale} \
      --model professionalize_llm \
      --validation-mode normal --force-accept --i-understand-data-loss --no-commit \
      --force-retranslate
    ```
    (`--force-retranslate` is required — without it the tool skips retranslation via a
    source-mtime cache check that assumes the existing, structurally-broken locale file
    is already current. Confirmed live: the first pilot attempt silently no-op'd until
    this flag was added.) 18 locales remain untranslated for mesh.md after batch-1: cs,
    el, fa, he, hi, hu, id, it, ko, nl, pl, pt, ro, sv, th, tr, uk, vi.
  - MS-02: Review output per Step 6's checklist (evidence block byte-identical,
    shortcodes preserved, no placeholder leakage, no product-name transliteration/
    mistranslation — check the `translation_fidelity` block in each output's frontmatter,
    not just a manual read) plus: no repeated-identical-heading corruption (see
    TC-LOCALE-02-05 MS-03).
  - MS-03: Copy back **only** `mesh.md` per locale (per-file `cp`, never a
    directory-recursive copy).
  Acceptance: all in-scope locale `mesh.md` files updated in the working tree, nothing
  else touched under `en/3d/typescript/`.
  Evidence: per-locale `translation_fidelity` score/verdict; flag anything below the
  Finding-B threshold for reroute rather than silently accepting it.
  Note: record the `professionalize_llm` LLM Metrics Obligation (AGENTS.md §15) in
  TC-LOCALE-02-05's evidence, not per-locale.

- **TC-LOCALE-02-04 — Translate `scene.md` (25 approved locales)** [CHILD, TODO,
  depends on 02-02b decision, parallel-safe with 02-03 — different files, no shared
  state] Same MS-01/02/03 pattern as TC-LOCALE-02-03, for `scene.md`. 6 locales already
  done in batch-1 (ru, zh, de, ar, fr, ja); 19 remain (es plus the 18 listed above).

- **TC-LOCALE-02-05 — Verify** [CHILD, TODO, depends on 02-03, 02-04]
  - MS-01: Re-run RG-004 for both files across the 25 in-scope locales → expect
    `"mismatches": []` for both.
  - MS-02: `content-eval` (S-51) spot-check on at least one locale from each of the
    four drift shapes identified in this plan's Context section (old-template,
    missing-See-Also, extra-Description, headings-stripped) → no grade regression.
  - MS-03: Confirm the repeated-identical-heading corruption (e.g. `es/mesh.md`'s
    triple `## Examples`) does not reappear anywhere in the new output — grep for any
    H2 heading text that repeats 2+ times within one file.
  - MS-04: Confirm at least one previously-legacy-frontmatter locale (no
    `evidence:`/`grade:` block before this pass, e.g. `hr` or `ru`) now has the modern
    evidence schema after regeneration. (Note: `hr` itself is out of scope per Finding
    A — use `ru` or another in-scope legacy-frontmatter locale instead.)
  Acceptance: all 4 checks pass. Any failure reroutes to the relevant translate child
  (02-03 or 02-04), not to a silent manual patch.
  Evidence: RG-004 JSON (zero mismatches), content-eval scores, grep output, and the
  `professionalize_llm` LLM Metrics Obligation record (AGENTS.md §15) for this run.

- **TC-LOCALE-02-06 — Commit + push Part B** [CHILD, TODO, depends on 02-05]
  - MS-01: Stage exactly the changed locale files (confirmed no override token needed
    — content/ isn't a protected path under the live `path_guard.py`).
  - MS-02: `/commit` (S-76) with `Skills invoked: [S-HT-01]` (+ `[S-107]` if
    TC-LOCALE-01 landed and was used for file discovery) and a `Verification:` line
    citing the TC-LOCALE-02-05 RG-004 zero-mismatch result. **Pause here** for the
    same Step B.5 commit-plan confirmation as TC-LOCALE-01-04 — a second, separate
    legitimate stop point.
  - MS-03: Push: `git push
    "https://x-access-token:${GH_TOKEN}@github.com/Aspose/aspose.org.git" main`.
  - MS-04: Append `resolved:{today} — {one-line summary, must mention the 11-locale
    exclusion and point to its follow-up item}` to the ST-151 and ST-152 rows in
    `backlog/inbox.md` in place — this repo's live convention for closed Standalone
    Task rows (there's no separate "done" table to move them to).
  Acceptance: commit lands and is pushed; `git show --stat` lists exactly the expected
  changed paths.
  Stop condition: if the pre-commit content-API/evidence audit fails for a reason
  unrelated to this change, stop and report rather than bypassing the gate.

- **TC-LOCALE-02-07 — File the 11-locale coverage gap as a follow-up** [CHILD, TODO,
  new, added during execution per Finding A] File a new backlog item (Standalone Task,
  `backlog/inbox.md`) documenting: the exact 11 locales (bg, ca, da, fi, hr, lt, lv, ms,
  no, sk, sr), that they remain structurally drifted (fail RG-004) after this plan
  closes, that `hugo-translator`'s `strict_locale_allowlist` is the blocker (not a repo
  bug), and the two options from Finding A (extend the allowlist vs. another mechanism)
  as fix candidates — same evidence-first pattern this repo already uses for ST-151/152
  themselves.

---

### TC-LOCALE-03 — Evidence bundle & closeout [PARENT]
Status: TODO · Depends on TC-LOCALE-01 CLOSED and TC-LOCALE-02 CLOSED.

- **TC-LOCALE-03-01 — Assemble evidence bundle** [CHILD, TODO]
  - MS-01: Create `reports/plan_execution/st-151-st-152-locale-drift/` — matches this
    repo's existing `reports/refresh_review/`, `reports/plan_state/` family, not an
    invented location. (Already created and partially populated — batch-1 outputs and
    both RG-004 before-JSONs are already there.)
  - MS-02: Save into it: both RG-004 JSON outputs from TC-LOCALE-02-01 (before) and
    TC-LOCALE-02-05 (after); the TC-LOCALE-01-02 pytest output; the
    `check_skill_mirror_parity.py`/`sync_skills.py --check` outputs; the
    TC-LOCALE-02-05 content-eval spot-check results; the heading-corruption grep
    output; both commit SHAs and push confirmations; a diff of the two backlog rows;
    the Finding A/B writeups from this plan (11-locale gap, fidelity-score variance).
  - MS-03: Write `summary.md` in that directory: what changed, both commit SHAs, the
    RG-004 zero-mismatch confirmation (scoped to the 25 in-scope locales), the
    11-locale exclusion and its follow-up item ID, and a pointer to every other file
    in the bundle.
  Acceptance: directory exists with all listed files non-empty; `summary.md` links to
  each one.
  Evidence: this taskcard's own output *is* the evidence bundle — report its absolute
  path (`d:\onedrive\Documents\GitHub\aspose.org\reports\plan_execution\
  st-151-st-152-locale-drift\`) in the final response to whoever invoked this plan.

## What this deliberately does NOT do

- Does not remove the stale `"sl"` entry from `KNOWN_LOCALES` — real for
  docs.aspose.org, dead for every other subdomain; a separate, unscoped decision.
- Does not touch the other ~180 fleet-wide pages RG-004 flagged as mismatched
  (confirmed 97/98 sampled pages fail it, including pages untouched by any recent
  session, e.g. `Axis.md`) — this plan is scoped to exactly `3d/typescript`'s
  `mesh.md`/`scene.md`. ST-152's own fix candidate (c) — survey whether this is
  fleet-wide — becomes cheap to answer once Part A ships, and is a natural follow-up,
  not part of this plan.
- Does not attempt to "correct" the old-template locale prose in place (e.g. fixing
  the wrong enum casing) — the current English template has no per-method worked-example
  section at all anymore, so the fix is deletion-via-regeneration, not correction.
- The `KNOWN_LOCALES` "hi" fix has repo-wide effect beyond this one product (S-107 will
  start discovering Hindi locale files for every product on its next run) — flagged
  here, not hidden, since it may surface a new backlog of previously-invisible drift.
- **Does not translate the 11 hugo-translator-unsupported locales** (Finding A) — filed
  as a separate follow-up (TC-LOCALE-02-07), not silently dropped or force-attempted.
- **Does not silently accept low-fidelity translations** (Finding B) — any locale
  scoring below the agreed threshold is rerouted, not committed as-is.

## Verification

- `pytest scripts/pipeline/tests/content/test_locale_refresh_handoff.py -q` after Part A.
- `check_locale_topology.py --source .../en/3d/typescript/mesh.md --locales .../*/3d/typescript/mesh.md --json` (and same for `scene.md`) → expect `"mismatches": []` after Part B (scoped to the 25 in-scope locales).
- `sync_skills.py --check` and `check_skill_mirror_parity.py --staged-files <paths>`
  after the skill-doc edits.
- Manual review of a handful of translated locale files (across scripts, e.g. ar/he,
  and across the four drift shapes) for evidence-block byte-identity and no
  placeholder/transliteration leakage, per `ht-translate.md` Step 6's own checklist —
  plus, per Finding B, an explicit check of each file's `translation_fidelity` block,
  not just a manual skim.

## Backlog Cross-Reference

| Backlog ID | Plan TC | Phase |
|------------|---------|-------|
| ST-151 | TC-LOCALE-01, TC-LOCALE-02 | Both — same underlying defect, see Context |
| ST-152 | TC-LOCALE-01, TC-LOCALE-02 | Both — same underlying defect, see Context |
