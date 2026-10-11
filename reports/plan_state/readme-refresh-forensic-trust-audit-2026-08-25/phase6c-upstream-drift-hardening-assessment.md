# Phase 6c — Upstream Drift & README-Overwrite Hardening Assessment

Independent, first-principles deep assessment, produced fresh (not a reassessment of prior
phase6/phase6b conclusions) at the user's request, triggered by two real, live-verified
cases: `font/python`'s repo history was replaced by an external mirror-sync, and
`page/python`'s upstream repo advanced under a human maintainer's own hand — and the
pipeline's local candidate then regressed relative to what was already correctly live. The
user's framing is adopted as the governing premise: **an upstream repo changing, and a
README being overwritten (by an external force, or by the maintainer's own hand, or by the
pipeline's own later regeneration), is normal, expected, recurring behavior — not an edge
case — and the system must be structurally prepared for it every time it happens.**

This document extends SW-2 and related items in `phase6b-production-hardening-design.md`
with two newly-verified, precisely-timed real-world instances and a materially sharper
mechanism than was previously available. **Nothing in phase6b or phase6-remediation-plan.md
is overwritten or retracted here** — this is an addendum with corrections stated explicitly
where this pass's evidence sharpens or partially revises the earlier framing.

## Assessment scope

- **System/component**: `readme-refresh` (S-120)'s handling of upstream-repository state
  relative to its own pinned knowledge, generated candidates, and already-published content
  — specifically, everything between "the upstream repo is the actual source of truth" and
  "the pipeline's belief about that repo's current state."
- **Intended outcome**: a generated/published README should always reflect (a) the real,
  current state of the upstream repo, and (b) never regress content that was already
  correctly published, regardless of what changed upstream or when.
- **Current sources of truth** (five, independently updated, no reconciliation authority —
  restating SW-2 from phase6b with two new concrete instances below): the local clone cache
  (`runs/.clone_cache/aspose_{family}_{platform}/`), the knowledge bundle
  (`knowledge/{family}/{platform}/merged/`), the generated candidate
  (`reports/repo-presenter-regen-full/{family}/{platform}/`), the publication ledgers
  (`data/readme_published_state.json`, `reports/repo_presenter_actions.jsonl`), and the real
  upstream GitHub repo itself.
- **Inputs and consumers**: inputs are the clone cache and knowledge bundle (read at `plan`
  time); consumers are the candidate composer (agentic), the 103-check battery, and,
  eventually, a human reviewer approving a push.
- **Evidence inspected** (this pass, live, 2026-08-26): `gh api` calls against
  `aspose-font-foss/Aspose.Font-FOSS-for-Python` and `aspose-page-foss/Aspose.Page-FOSS-for-Python`
  (repo metadata, commit history, branch list, live README content, both fetched fresh, not
  from cache); `git log`/`git show` against both local clone caches; a byte-level diff of
  page/python's live README against its local candidate; `knowledge/page/python/merged/model.yaml`'s
  pinned `repo_sha`/`bundle_generated_at`; file mtimes of every file in
  `reports/repo-presenter-regen-full/page/python/`; `upstream-issues.md`'s own pinned-SHA
  header; a repo-wide grep for every call site of `clone_cache.update_clone()`; a targeted
  grep of `readme_refresh_run.py` for any clone-cache-refresh call (none found). Also reused,
  with re-verification rather than blind trust: the closed audit's `phase3-reviews/font-python.md`
  and `phase3-reviews/page-python.md`, and `phase6-root-cause-clusters.md`'s Cluster E.
- **Missing evidence, stated honestly**: I did not trace the exact tool/session/skill
  invocation that produced page/python's 2026-08-18 candidate regeneration (the mission
  history I have access to does not name a page/python-touching event on that date — the
  `readme-refresh-seo-deps-headings-hardening-2026-08-19` mission's own 9-product list does
  not include page/python). I infer *that* a regeneration happened (precise mtime evidence,
  below) and *what conditions* it ran under (stale knowledge, no live-README awareness), but
  not *who/what* triggered it. I also did not exhaustively check all 29 other products for a
  third instance of either pattern — the font/python and page/python cases are the two the
  user identified and I independently verified; I did not go hunting for more before writing
  this assessment, and say so rather than implying full-portfolio coverage.

## Current-state reconstruction

### Actual execution flow (verified, not assumed)

1. **Clone-cache population/refresh is entirely decoupled from readme-refresh.** A
   repo-wide grep for `update_clone(` — the only function in `scripts/pipeline/core/clone_cache.py`
   that advances a local clone toward live upstream (`git fetch --depth=2 origin` then
   `git reset --hard origin/HEAD`) — found exactly 5 call sites:
   `refresh_knowledge.py` (S-54), `mechanism_sweep.py`, `repo_patrol.py` (S-93),
   `clone_cache.py` itself (its own CLI), and one test file. **`readme_refresh_run.py`
   contains zero references to `update_clone` anywhere** (confirmed by direct grep of that
   file) — every one of its own references to `clone_cache` (9 call sites) only checks
   `.is_dir()` or globs an *already-existing* local directory. `readme-refresh` does not
   check whether its clone cache is current, does not trigger a refresh, and has no
   mechanism to even ask the question before using whatever is on disk. Freshness is
   entirely the responsibility of some other, separately-invoked skill running at some
   unrelated time, for some unrelated reason, with no coupling to when a README is next
   generated or re-verified.
2. **`plan` reads the clone cache and knowledge bundle once, pins nothing durably against
   live upstream, and composition proceeds from there.** No step in the documented
   execution contract (`.claude/commands/readme-refresh.md`) or the code
   (`readme_refresh_run.py`) compares the clone cache's HEAD against a live fetch before
   trusting it.
3. **Regeneration of an existing candidate has no awareness of what is already live and
   published.** Nothing in `plan_run`/composition reads `data/readme_published_state.json`
   or fetches the current live README before writing a new candidate. A regeneration cycle
   is a fresh composition from (possibly stale) knowledge, full stop — it does not diff
   against, defer to, or protect content that a prior, successful cycle already published.
4. **Publication tracking is a self-reported ledger with no reconciliation loop against
   live GitHub** (already established in phase6b SW-4/§III-b) — restated here because both
   font/python and page/python's real pushes are absent from both ledgers, which is why
   neither the mirror-wipe nor the stale-regeneration-regression triggered any alert.

### State and artifact flow for the two verified cases

**`font/python`** — external force replaces the target repo entirely:
- 2026-08-15T15:22:31Z: PR #1 genuinely merged (`7971880`), a real, correct fix.
- 2026-08-20T21:48:16Z: live repo HEAD becomes `55409553`, a **zero-parent** commit
  ("Release 26.8.3", author `AI-Agent-AsposeFontFOSS`), whose README is byte-identical to
  the **pre-refresh original** — the entire git history, including the merged fix, is gone
  from the default branch.
- **Re-verified today (2026-08-26)**: live HEAD is still `55409553`. The local clone cache
  still shows `7971880` as HEAD — it has never been refreshed since before the wipe, so the
  pipeline's own local state doesn't even know the wipe happened.
- `CHANGELOG.md`/`CODEOWNERS`/`.gitlab-ci.yml` at live HEAD describe a GitLab-canonical,
  GitHub-mirror architecture (already identified in the closed audit) — the mirror sync is
  the plausible mechanism, though this pass did not independently re-derive that beyond
  citing the prior finding.

**`page/python`** — the maintainer's own real commit advances the repo; the pipeline's
*own later regeneration* then regresses relative to it:
- 2026-07-24T11:49:18Z: upstream release `dac5d70e` (26.7) — this is the commit
  `knowledge/page/python/merged/model.yaml` is pinned to (`bundle_generated_at:
  2026-08-14T11:49:43Z`) and remains pinned to today, 2026-08-26 — **12 days stale relative
  to this pass's own live check**, and the knowledge bundle itself is 43 days behind the
  release it describes having been rebuilt "for."
- 2026-08-15: `upstream-issues.md` generated, pinned to the same `dac5d70e`.
- **2026-08-16T15:25:24Z**: a real, live, non-dry-run push — `ca4fb3d7`, authored by
  `Babar Raza` (the repository maintainer, i.e. the user) — "restore Example Results
  screenshots and reclassify as hybrid archetype." This commit's README contains detailed,
  specific, correct wording (e.g., "Author PS, EPS, and XPS documents from scratch," and a
  precise circular-import paragraph naming the exact modules and methods involved).
- **2026-08-18T21:53:22+05:00** (candidate file's own mtime): the local candidate
  (`reports/repo-presenter-regen-full/page/python/readme.md`) was rewritten — **two days
  after** the maintainer's own live push — while the knowledge bundle was still pinned to
  the same pre-push `dac5d70e` SHA it had been pinned to all along (no refresh happened
  between the 16th and the 18th). The regenerated text for the same two passages is now
  **generically vaguer** than what the maintainer had already published: "Author new
  documents" (drops PS/EPS/XPS/method names) and a circular-import paragraph that drops the
  specific module/method names entirely.
- **Re-verified today (2026-08-26)**: live README is still `ca4fb3d7`'s content, unchanged,
  and remains byte-identical to the local clone cache. The regression is confined to the
  *local candidate*, not yet republished — but it is sitting there, generated, ready to be
  approved and pushed, which would silently downgrade already-correct live content.
- 2026-08-20T17:49: the four disposition JSON files were rewritten again, in a separate
  pass 2 days after the readme.md regeneration — source unidentified (see Missing evidence
  above).

### Gates and validators that should have caught this, and did not

- No check compares the knowledge bundle's `repo_sha`/`bundle_generated_at` against a live
  fetch of the upstream repo (this is exactly phase6b §3.III's proposed freshness manifest
  — restated here with a precisely-dated, quantified instance: **12 days and counting**,
  confirmed live today, not merely "possible").
- No check fetches the currently-live published README and diffs a new candidate against
  it before allowing generation to proceed — this is a genuinely new gap this pass surfaces
  that phase6b's §3.III/§3.III-b did not explicitly name: those items cover *whether a push
  happened* (publication-ledger completeness) and *whether inputs are stale* (freshness
  manifest), but neither one compares **candidate content against live content for
  regression** before a regeneration is trusted.
- No check distinguishes "upstream advanced in the ordinary way" (fast-forward, like
  page/python's `dac5d70e` → `ca4fb3d7`) from "upstream history was replaced" (non-fast-
  forward / zero-parent, like font/python's wipe) — both currently look the same to every
  existing mechanism: "the clone cache doesn't match live," full stop, with no
  classification of *how* it doesn't match.

### Observed inconsistencies

The same broad symptom — "the pipeline's belief about upstream diverges from upstream
reality" — manifests as two *structurally different* problems that would need *different*
handling: font/python needs **loss detection and a publish-target-authority decision**
(already scoped in phase6-remediation-plan.md Tier 1 item 2 and RC-font-python-republish-regression,
RC-publication-target-authority-verification); page/python needs **regression prevention
during ordinary regeneration** (not yet scoped anywhere as its own item — see new proposal
below).

## Symptoms

(Listed without treating them as causes, per the required method.)

- font/python: live README reverted to the pre-refresh original; the real merged fix is
  invisible in production.
- font/python: neither publication ledger has any record of the original merge or the
  subsequent wipe.
- page/python: local candidate contains measurably vaguer, less specific wording than the
  README already live in production, for two distinct passages.
- page/python: knowledge bundle is 12+ days stale relative to the live repo as of this
  check, and was already stale (predating the maintainer's own push) at the moment the
  regressive candidate was generated.
- page/python: `upstream-issues.md` has not been touched since 2026-08-15, predating the
  maintainer's own subsequent push by a day.
- Both cases: no alert, warning, or hard-gate finding fired for either condition at any
  point between when they occurred and when a human (the user) noticed and raised them.

## Root causes

### RC-1: No coupling between clone-cache/knowledge freshness and readme-refresh execution
- **Evidence**: zero `update_clone` call sites in `readme_refresh_run.py` (repo-wide grep);
  page/python's knowledge bundle 12 days stale as of a live check performed today.
- **First failing boundary**: the very first read at `plan` time — the pipeline trusts
  whatever is in `runs/.clone_cache/`/`knowledge/.../merged/` unconditionally, with no
  liveness check anywhere upstream of that read.
- **Affected scope**: portfolio-wide, architectural (not product-specific) — any product
  whose clone-cache-refreshing skill (S-54/S-93/mechanism-sweep) isn't run in close temporal
  proximity to a readme-refresh cycle is exposed identically.
- **Why existing controls missed it**: the 103-check battery is explicitly, deliberately
  offline-only (a real, valuable property, per phase6b §2) — but nothing *outside* that
  battery fills the live-freshness role either, so the gap is total, not partial.
- **Confidence**: High — directly verified by grep and by a live, dated staleness
  measurement, not inferred.

### RC-2: Regeneration has no concept of "already live," so it cannot avoid regressing it
- **Evidence**: page/python's candidate mtime (2026-08-18) postdates the live push
  (2026-08-16) by two days, using the same pre-push knowledge pin throughout, and produces
  measurably worse wording for the same content than what was already correctly live.
- **First failing boundary**: candidate composition itself — the agentic step that writes
  `readme.md` has access to the factpack and the skill doc, but nothing in its inputs
  includes "here is what is currently live; do not regress it."
- **Affected scope**: portfolio-wide by mechanism (any product can be regenerated a second
  time against stale knowledge after a real push has already landed); confirmed on one
  product (page/python) by direct evidence.
- **Why existing controls missed it**: `check_dropped_content` and the disposition-ledger
  family (Cluster A) compare the candidate against the **old, pre-refresh README**, never
  against **the currently-live, already-published one** — a regeneration cycle that starts
  from stale knowledge has no live reference point to regress *against* in any check's
  design, because none of them are wired to fetch or compare live state.
- **Confidence**: High on the observed fact pattern (precise, dated, directly diffed);
  Medium on the *specific causal mechanism* ("a regeneration cycle ran using stale
  knowledge") — this is the best-supported reconstruction of the evidence, but the exact
  triggering tool/session is not identified (see Missing evidence).

### RC-3: No structural distinction between "upstream advanced" and "upstream history was replaced"
- **Evidence**: both font/python (zero-parent replacement) and page/python (ordinary
  fast-forward advance) currently present identically to every existing mechanism as "clone
  cache doesn't match live" — confirmed by inspecting what each mechanism actually checks
  (none perform an ancestry check).
- **First failing boundary**: there is no code anywhere in the readme-refresh execution
  contract that runs the equivalent of `git merge-base --is-ancestor <last-known-sha>
  <live-HEAD>` to classify a divergence before acting on it.
- **Affected scope**: portfolio-wide, architectural.
- **Why existing controls missed it**: this distinction was never in scope for any existing
  check — it requires a live git operation, which the offline check battery structurally
  excludes by design (correctly, per phase6b §2), and nothing else fills the role.
- **Confidence**: High that the distinction is not made anywhere (directly verified by
  reading every relevant check and finding none perform ancestry classification); High that
  this is the correct fix shape (a standard, well-understood git operation), Medium on
  exactly where it should live operationally (see Implementation direction).

## Structural weaknesses

These recur across both cases and would keep producing the same class of incident
regardless of how many individual findings are patched:

1. **Freshness is advisory-or-absent everywhere it exists, never a precondition.** Even
   where a staleness signal exists elsewhere in the system (phase6b's proposed freshness
   manifest, or `_checks_currency_findings`'s module-version tripwire), it is designed to be
   *reported*, not to *block* generation from proceeding on stale ground. RC-1 and RC-2 both
   trace to the same shape: nothing stops the pipeline from acting on data it has no live
   confirmation is current.
2. **The pipeline has exactly one directional relationship with "live state": it produces
   candidates and (occasionally) pushes them. It never consumes live state as an input to
   protect against regression.** This is the structural reason RC-2 is possible at all — a
   regeneration is a write operation with no corresponding read of "what does the target
   already correctly contain."
3. **"Different from what I expected" is not classified before being acted on.** RC-3:
   until upstream divergence is classified (ordinary advance vs. history replacement), any
   single response to "clone cache doesn't match live" is guaranteed to be wrong for one of
   the two cases — treating every divergence as "just refresh and regenerate" would silently
   regenerate page/python fine but blindly republish over font/python's wiped history
   without ever surfacing that a wipe occurred; treating every divergence as "halt and
   escalate to a human" would correctly protect font/python but create unnecessary friction
   for the overwhelmingly more common page/python-style ordinary case.

## What should be preserved

- The offline, deterministic 103-check battery's purity (per phase6b §2) — none of the
  fixes below should be folded into it; they belong to a separate, explicitly-live
  reconciliation layer, exactly as phase6b's §III already proposed for a different reason.
- The clone-cache module's own refresh primitive (`update_clone`, `git fetch --depth=2` +
  `git reset --hard origin/HEAD`) — it is correct and already used successfully by three
  other skills; it does not need to be reimplemented, only *invoked from the right place*
  for readme-refresh's purposes.
- The disposition-ledger concept and the old-README-comparison checks (Cluster A) — they
  answer a real, different, still-necessary question ("was old content preserved") and
  should not be modified to also answer the live-regression question; that needs its own,
  additional comparison, not a repurposing of an existing one.
- page/python's and font/python's *already-correct* published content itself — the fix
  target here is preventing future regressions/losses, not touching what is currently,
  correctly live.

## What must be redesigned

1. **A live-freshness precondition, not just a report.** Extending phase6b §3.III/RC-clone-cache-freshness-gate:
   the freshness check must be capable of **blocking** `plan`/composition (with an explicit,
   loggable override path), not only recording DRIFTED in a manifest for someone to notice
   later.
2. **A live-published-content regression gate**, genuinely new relative to phase6b: before
   a regenerated candidate can pass `ingest-candidate`, fetch the currently-live published
   README (if `data/readme_published_state.json` or a live `gh api` check shows one exists)
   and require an explicit disposition for every passage that changed relative to it —
   using the *same* disposition-ledger machinery Cluster A already established (PRESERVED /
   TRANSFORMED / DROPPED-WITH-REASON), just against a second baseline (live-published) in
   addition to the existing one (old-README-at-generation-time).
3. **A divergence classifier**, genuinely new: before treating any clone-cache-vs-live
   mismatch as routine, run an ancestry check
   (`git merge-base --is-ancestor <last-known-verified-sha> <live-HEAD>`) and branch:
   fast-forward → ordinary refresh-and-continue path (extends RC-2's fix); not an ancestor →
   halt, flag `publication_target_integrity: SUSPECT_HISTORY_REPLACEMENT`, and require the
   same human-decision gate already scoped for font/python
   (RC-publication-target-authority-verification, RC-font-python-republish-regression) —
   this generalizes that font/python-specific item into the portfolio-wide mechanism it was
   always implicitly describing.

## Production-grade target design

**Architecture**: one new, explicit, out-of-band **reconciliation step** (call it
`reconcile-upstream`, alongside `plan`/`ingest-candidate`/`approve`/`push` in the existing
state machine's vocabulary, not inside the offline check battery), run automatically as a
mandatory precondition of `start`/`plan`, and independently invocable on its own schedule
(daily, or before any remediation mission touches a product) — the same operational shape
phase6b's §III/§III-b already proposed, now with the two dedicated mechanisms above folded
in as its actual content, not left as a future TODO.

**Responsibilities**:
- Fetch live HEAD (`gh api`/`git ls-remote`, following `_preflight_access_check`'s already-
  proven pattern) and compare against the clone cache's current HEAD and against
  `data/readme_published_state.json`'s last-known-published SHA (three-way, not two-way).
- Classify: `CURRENT` (clone cache already matches live) / `BEHIND_FAST_FORWARD` (ordinary
  advance — refresh clone cache via the existing `update_clone`, mark knowledge for
  re-scout) / `HISTORY_DIVERGED` (not an ancestor — halt, do not auto-refresh, flag for
  human review of what happened upstream).
- On `BEHIND_FAST_FORWARD` specifically: if a live-published README exists, fetch it and
  hand it to the composer as a required second input alongside the factpack, with an
  explicit instruction (and a corresponding new disposition-tracking requirement) that no
  passage may regress relative to it without a recorded, verified reason.

**State model**: a `reconciliation_state.json` per product (sibling to the freshness
manifest phase6b already specified — this can be the same artifact, extended, not a
separate file), recording `last_known_verified_sha`, `live_head_sha_at_last_check`,
`classification`, `checked_at`. This becomes the durable "what did we last know to be true"
record RC-1/RC-3 currently lack entirely.

**Failure handling**: a failed live fetch (rate limit, network) records `UNKNOWN`, never
silently treated as `CURRENT` (same principle phase6b already established for the freshness
manifest — restated because RC-3's classifier introduces a second live-call surface with the
same failure-handling need).

**Observability**: `HISTORY_DIVERGED` and `BEHIND_FAST_FORWARD`-with-live-regression-risk
are exactly the two states that should page/notify a human, not silently log — this is the
concrete trigger condition RC-publication-target-authority-verification and the new
regression gate need to actually fire on, rather than existing only as a described intent.

**Compatibility**: additive — every existing check, the disposition-ledger machinery, and
the state machine's transitions are unchanged; `reconcile-upstream` is a new precondition
gate inserted before `start`, not a replacement for anything.

## Implementation direction

1. **Sequence** (fits inside phase6b's existing Stage 2b — freshness/reconciliation — do
   not create a new stage; this is the concrete content that stage was always going to
   need):
   a. Build the three-way freshness/ancestry check as a standalone function first
      (`_classify_upstream_divergence(family, platform)` in a new or existing lib module),
      unit-tested against synthetic git histories (a fast-forward fixture, a diverged/
      zero-parent fixture) before touching any live product.
   b. Wire it as a hard precondition of `start` (refuse to `CREATED → INPUTS_PINNED` on
      `HISTORY_DIVERGED` without an explicit override, matching the existing pattern for
      other hard preconditions in that function).
   c. Build the live-published-content regression gate as a new check function
      (`check_no_regression_vs_live_published`), reusing the disposition-ledger's existing
      three-way classification vocabulary, wired as a hard gate in `ingest_candidate` only
      when a live-published README is confirmed to exist (never fabricate a comparison
      baseline when none exists).
2. **Dependencies**: (b) depends on (a) existing; (c) depends on phase6b §3.I's disposition-
   identity work being far enough along that a second baseline comparison doesn't compound
   the existing positional-ID fragility — sequence (c) after phase6b Stage 1b, not before.
3. **Canaries, using the two real cases as positive controls, not synthetic examples**:
   `page/python` for (c) — regenerating against current knowledge should now correctly
   preserve or improve on the live wording, not regress it, and the tool should flag the
   *already-generated* regressive candidate sitting on disk today as the first real
   detection this mechanism should catch, retroactively; `font/python` for (a)/(b) — running
   the classifier against it today should correctly report `HISTORY_DIVERGED`, not
   `BEHIND_FAST_FORWARD`, as its very first real-world proof.
4. **Safeguards**: never auto-refresh on `HISTORY_DIVERGED`; never auto-republish anything
   on any classification without the existing human-approval gate; the regression gate
   never silently drops a live-only passage it can't reconcile — it fails the check and asks
   for a disposition, matching Cluster A's existing "never assume, always require a
   disposition" discipline.

## Verification strategy

Following the required proof chain:

```
REAL INPUT (live upstream repo state for font/python, page/python)
→ OFFICIAL ENTRY POINT (reconcile-upstream, invoked before start)
→ SYSTEM PROCESSING (three-way fetch + ancestry classification)
→ STATE OR ARTIFACT (reconciliation_state.json)
→ VALIDATOR OR GATE (start's hard precondition; ingest_candidate's regression gate)
→ DOWNSTREAM CONSUMER (approve/push, and any future remediation mission)
→ OBSERVED RESULT (font/python correctly blocked with HISTORY_DIVERGED;
   page/python's existing regressive candidate correctly flagged)
```

- **Focused tests**: the ancestry classifier against fixture git repos (fast-forward,
  diverged, identical, network-failure-simulated).
- **Integration test**: run `reconcile-upstream` against the real, current `font/python`
  clone cache and live repo (read-only — fetch + classify only) and assert it returns
  `HISTORY_DIVERGED`; run it against `page/python` and assert `BEHIND_FAST_FORWARD`. These
  are real, already-available positive controls — no synthetic fixture substitutes for
  proving the classifier works against the actual cases that motivated it.
- **Negative control**: run the classifier against a product confirmed `CURRENT` (e.g.
  `note/python`, per this mission's own baseline) and assert no finding fires — proves the
  gate isn't just always-block.
- **End-to-end proof**: run the full `start → reconcile-upstream → plan → composition →
  ingest-candidate` chain against page/python's *current, real* stale state and confirm the
  regression gate fires against the already-known-bad passages (the two diffed above) before
  any fix to the underlying candidate is made — proving detection works on the real defect,
  not a contrived one.
- **Rerun/idempotency check**: running `reconcile-upstream` twice in immediate succession
  against unchanged live state must return the identical classification both times.
- **Regression gate**: once this lands, no future candidate for any product may be approved
  while `check_no_regression_vs_live_published` has open findings, enforced the same way
  existing hard gates already block `ingest_candidate`.

## Tradeoffs and risks

- **Benefit**: closes a class of defect (silent regression of already-correct live content)
  that the closed audit's Phase 4 matrix did not have a dedicated row for — this is a real
  gap in the prior analysis, not merely a deeper explanation of an already-known one.
- **Cost**: a new live-network-dependent precondition on every `start` call is a real
  latency and reliability cost (network calls, rate limits) added to the critical path of
  every future readme-refresh invocation — mitigated by, but not eliminated by, treating a
  failed check as `UNKNOWN`-and-warn rather than hard-block by default (a policy choice the
  user should confirm, since it trades strictness for availability).
- **Migration risk**: retroactively running the regression gate against all 31 existing
  candidates will likely surface more than just page/python's case — this pass did not
  check the other 29 for the same pattern (Missing evidence, above), so the true blast
  radius of RC-2 is currently unknown and should be swept before assuming it's a one-off.
- **Compatibility risk**: low — additive precondition, no existing interface changes.
- **Operational risk**: `HISTORY_DIVERGED` handling for font/python-class incidents still
  terminates in a human decision this design cannot make (GitLab-vs-GitHub publish-target
  authority) — the classifier correctly detects and routes the problem, it does not resolve
  it.
- **Likely limits**: this design detects and blocks regression *at generation/ingest time*;
  it does nothing to recover font/python's already-lost merged fix, which remains a manual
  remediation (Tier 1 item 2, unchanged).
- **Rejected alternative**: folding the live-fetch classifier into the existing 103-check
  battery was considered and rejected — it would compromise the battery's proven, valuable
  offline-purity property (phase6b §2) for a capability that belongs structurally
  upstream of it.

## Final assessment

**STRUCTURAL_REDESIGN_REQUIRED** — narrowly scoped, not portfolio-wide. The specific gap
(no live-freshness precondition, no live-regression gate, no divergence classification) is
structural, not a missing check inside the existing battery, and both real-world cases
independently confirm it is already causing production-visible harm (one confirmed content
loss, one confirmed quality regression sitting ready to ship). This does not upgrade the
overall system verdict beyond what phase6-remediation-plan.md/phase6b already concluded
("not currently trustworthy for autonomous use") — it sharpens *why*, with two dated, live,
independently-reproducible instances, and adds one dedicated new mechanism
(live-published-content regression gate) that the prior passes had not separately named.
