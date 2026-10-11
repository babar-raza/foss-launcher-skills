# Phase 6b — Production Hardening Redesign (post-closure deep pass)

Produced after mission `readme-refresh-forensic-trust-audit-2026-08-25` closed, on explicit
request to go deeper than the closed audit's Tier-1/Tier-2 remediation list and treat this
as a production-engineering problem: separate symptoms from root causes from structural
weaknesses, identify what's already correct, and propose a durable architecture rather than
a longer checklist. This document does not reopen the closed mission or change any RC-*
status; it is the design input for a future, separately-bound remediation mission, per that
mission's own stated boundary ("every item here is a candidate for a separate, future
remediation mission").

**Sequencing mandate, stated up front because it governs everything below**: fix the
system/skill first; only then reuse the hardened system to fix outcomes. The one deliberate
exception is the small set of already-live, already-misleading Tier-1 items from the closed
audit (`words/net`, `font/python`, `cells/java`, `html/python`, `page/python`) — those get
the narrow, human-reviewed, single-file interim corrections already scoped in
`phase6-remediation-plan.md`, because leaving a non-compiling published example live for
months while the machinery is rebuilt is worse than a small, contained patch. That is
triage, not a contradiction of "system first."

**Revision note**: this document was adversarially reviewed after its first draft (a
dedicated critique pass re-verified every load-bearing code citation directly and stress-
tested the proposal for overreach, missed simpler alternatives, and internal
contradictions). Several corrections came out of that pass and are folded in below rather
than listed separately — most importantly: §1 SW-3's original wiring claim was wrong in a
way that changes what §3.I actually needs to build; the original design omitted proposals
for the single largest defect class in the whole audit (the publication ledger) and two of
the cheapest, highest-leverage fixes found; §3.I's migration strategy and §3.VII's
enforcement mechanism were both replaced with materially better designs the first draft
didn't consider; and the effort estimate was corrected upward. Where the critique found a
real gap I could not close cleanly, that is stated as an open limitation (§6), not papered
over.

## 1. Three layers, not two

The closed audit separated symptoms (172 findings) from root causes (8 clusters). This pass
adds a third, deeper layer: **structural weaknesses** — properties of the architecture
itself that guarantee root-cause clusters keep regenerating even after any single cluster is
patched. Six are load-bearing; §3 traces back to them, with one honest exception flagged
where it occurs (SW-1, below) rather than forced to fit.

### SW-1 — Verification happens after free-form generation, never during it
The pipeline generates prose first (a fully agentic composition step with no template and no
output contract beyond "10 sections exist"), then tries to catch problems with a fixed
battery of 103 deterministic checks written after specific defect shapes were discovered.
This is a whack-a-mole architecture by construction: a check battery, however large, is only
complete for defect shapes someone has already thought to write a check for. This is not
speculation — it is this project's own recorded history repeating: [[project_readme_refresh_repo_presenter_plan]]'s
memory already names the exact lesson four separate times ("a different failure mode needs a
different check, not wider coverage" — `check_dropped_content` vs. `check_named_member_accuracy`,
then again for diagram connectivity vs. capability-dependency matching, then again for MT030's
disposition-coverage vs. named-member-accuracy). This audit's own Phase 4 matrix added
**~40 more** defect-class rows on top of the existing 103 checks, and found **53% of all
confirmed findings had no targeting check at all**. The ceiling is structural, not a matter
of writing more checks.

**Honest tension, flagged rather than smoothed over**: the actual structural fix for SW-1 is
constraining generation itself (real templating, or a much narrower agentic surface) so
there are fewer defect shapes to catch in the first place. §3.VI explicitly declines to
propose that — full templating risks losing the "plan never writes prose, composition does"
boundary this document itself lists as worth preserving (§2), and the evidence in hand
(172 findings, however serious) does not clearly justify a rewrite of that scale over the
narrower fixes below. §3.IV (claim-taxonomy metadata required *at generation time*) is the
one proposal that genuinely moves toward SW-1's fix — it changes what composition must
produce, not just what gets checked afterward. Every other item in §3 is, honestly, a deeper
or better-targeted check on the same generate-then-verify sequence SW-1 critiques. That is
a real, acknowledged limitation of this plan: it substantially narrows SW-1's damage without
resolving its root architecture. A future pass, once §3's items have run in production long
enough to show whether the narrower fixes hold, should revisit full constrained generation
on its own merits rather than by default.

### SW-2 — Five independent "truth" stores, no reconciliation authority
Clone cache, knowledge bundle, package registry, publication ledger, and the target repo's
own live state are updated independently, on different cadences, by different mechanisms,
with no scheduled process that reconciles them against each other or against live upstream.
Every staleness-shaped defect in Clusters B, D, and E (pdf/net's version drift, pdf/python's
18-commits-stale knowledge, the 55%-of-portfolio publication-ledger gap, font/python's wiped
publication) is a symptom of this one gap: there is no single "as-of" freshness contract
that generation, verification, and publication all consult. Patching each staleness check
individually (as Phase 6's Tier 2 partly does) treats five symptoms of one structural absence
as five unrelated problems.

### SW-3 — Positional, non-content-addressed identity for disposition tracking — the enforcement hook exists, but the identity scheme and the data it enforces don't
The sharpest finding of this pass, corrected after adversarial re-verification of exactly
how it's wired. `extract_old_readme_content_units` (`readme_refresh_checks.py:5769-5817`)
assigns `unit_id` as `f"u{len(units) + 1:04d}"` — a stable, *order-based* id, explicitly
documented in its own docstring as "not a content hash." The identical pattern recurs
independently in three more extractors — structural units (`s%04d`, ~7217), code-example
units (`c%04d`, ~7654), and badges (`b%04d`, ~8015) — four separate positional-ID ledgers,
not one. The code's own MT056 comment block (`readme_refresh_checks.py:5350-5366`) states
outright: *"the positional unit_id scheme is the confirmed root cause of the R-07
disposition-drift regression class."*

**What's actually already built, precisely**: `split_into_scope_blocks`/
`compute_block_fingerprints` implement content-addressed identity (sha256 over normalized
block text + a stable heading slug) at `##`-section granularity, and — corrected from the
first draft of this document — the enforcement hook (`_apply_scope_enforcement`) *is*
called unconditionally from both `ingest_candidate` and `recheck`, i.e. from the default
path every product refresh actually goes through, not only from the opt-in workflow. What
is genuinely missing is two things, not one: (a) the fingerprint comparison only fires when
a `blocks` entry exists in `acceptance-registry.json`, and that registry is populated only
by the opt-in `accept_blocks` call — confirmed zero instances anywhere in the portfolio
(`AUD-P1-ACCEPTANCE-REGISTRY-UNUSED`); and (b) even if populated, block-level hashing
operates at `##`-section granularity, one level coarser than the four *unit*-level ledgers
(content/structural/code-example/badge) that actually carry the positional-ID defect this
audit found. So the fix is not "wire an unused mechanism into the default path" (it's
already there) — it is "start populating the registry as a matter of course, and extend the
same hashing idea down to unit granularity for the four ledgers that need it." Cluster A —
11 of 36 defect-class rows, the largest cluster in the audit — is downstream of exactly this
gap: a positional-ID ledger cannot survive any edit that shifts unit order, which is exactly
the "false preserved," "orphaned disposition," "wrong target_section" family of defects this
audit found repeatedly.

### SW-4 — The single largest defect class by hit-rate has no reconciliation mechanism at all, live or offline
Distinct from SW-2 (which is about *generation-input* freshness — clone cache, knowledge,
package registry). This is about *publication-output* tracking: whether a real, confirmed
push/merge to a product's live GitHub repo is reflected anywhere the system can see it.
Phase 4 row 20 found this is wrong on **17 of 31 products (55%)** — by a wide margin the
most-recurring confirmed defect in the entire audit — through at least three independently
confirmed causal mechanisms (a missed backfill sweep, a genuinely out-of-band manual commit
no seeding pass could ever learn about, and the disclosed "published then locally re-edited"
case). `_published_readme_current_findings` exists and is wired, but is advisory-only and
has no mechanism to detect an *unrecorded* real publication at all — it only re-checks
publications the ledger already claims to know about. This is structural, not a missing
check: there is no process, scheduled or triggered, that ever asks GitHub directly "did
anything land on this repo that we don't have a record of."

### SW-5 — No contract for "consistent across reruns," and free-form prose cannot meet the strictest reading of one
The surgical-scope workflow enforces a real, hard idempotency guarantee: frozen blocks stay
byte-identical. But the *initial* composition of a candidate is a single, unconstrained LLM
step with no temperature/seed pinning, no template skeleton, and — confirmed by direct
search — no test anywhere that reruns composition against unchanged inputs and checks the
output for equivalence. This matters concretely: the closed audit's own canary/rollout
template (`phase6-remediation-plan.md`, step 8) asks for "a second unchanged generation,
byte-identical output" as a regression gate. That is achievable for mechanical
transformations (a check fix, a template field) but **not realistic for anything the
free-form composer touches** — an LLM asked to write prose from the same facts twice is not
guaranteed to produce the same wording, and nothing in the system today can tell the
difference between "the candidate changed because upstream changed" and "the candidate
changed because the model phrased it differently this run." I am revising my own prior
guidance here: §5 below restates what "consistent across reruns" should actually mean for
this system.

### SW-6 — The system's own design contract is not a versioned, machine-checked artifact
Already flagged in the closed audit (`AUD-P1-TEMPLATE-OUTSIDE-GIT`) as a documentation gap;
restated here as structural. The actual specification of what a compliant README must
contain and why exists as 1,301 lines of skill-doc prose plus a 22,000+ line, un-versioned,
single-machine narrative file. Nothing forces the skill doc, the 103-function check battery,
and this "template" to move together — which is a direct, mechanical explanation for why
this audit found the check count wrong in three independent places, and why "spec'd but not
implemented" gaps (the dependency-verification-matrix, the acceptance registry) can persist
for months without anyone noticing the drift between what's documented and what runs.

## 2. What must be preserved

Explicitly, so the redesign doesn't discard what's proven:

- **The run-bound state machine, locking, and session-ownership model.** No defect in this
  audit traces to a state-transition bug. `FileLock`-guarded single-owner-per-product
  locking, `ACTIVE.json`, and receipt-based resume are sound and should not be touched.
- **The deterministic, offline, fail-closed `plan` step.** "Never writes prose" is a real,
  valuable architectural boundary — keep the fact-extraction/composition split exactly where
  it is.
- **The MT056 content-addressed block-identity primitive itself.** The mechanism is correct;
  it is simply mis-scoped (opt-in instead of default). §3.I promotes it — it does not
  replace it with something new.
- **The disposition-JSON concept.** Tracking every original unit's fate (preserved /
  transformed / dropped-with-reason) is the right idea and should not be abandoned because
  its identity scheme is broken.
- **The 103-check battery, reframed as a necessary but not sufficient outer ring.** Cluster
  row 23 (a hard gate correctly defending a candidate against a bad `formats.md` signal) is
  live proof the battery does real work when fed trustworthy input. The fix is adding depth
  above and below it, not discarding it.
- **Human-gated `approve`/`push` as a concept** — move it from convention to code
  enforcement (§3.VII); don't remove the gate itself.

## 3. What must be redesigned — concrete proposals

### I. Promote content-addressed identity to the default disposition backbone
Extend the hash-plus-stable-slug scheme `compute_block_fingerprints` already implements at
`##`-section granularity down to the four *unit*-level ledgers that actually carry the
positional-ID defect (content, structural, code-example, badge). This is reuse-and-extend,
not invention — but it is a materially larger surface than a single extractor: honestly
counted, roughly 20+ functions across four independent ledger families
(`extract_old_readme_content_units` ~5769 plus ~10 consumers; the structural/`s%04d` family
~7217 plus ~4 consumers; the code-example/`c%04d` family ~7654 plus ~3-4 consumers; the
badge/`b%04d` family ~8015 plus ~3-4 consumers), not the ~7 this document's first draft
estimated.
- **Rollout strategy, revised from a one-shot batch migration to additive dual-key**: add a
  `content_hash` field alongside the existing positional `unit_id` on every new disposition
  entry going forward; consuming checks read `content_hash` when present and fall back to
  positional `unit_id` when absent. Re-key each product's *existing* ledgers lazily, the
  next time that product is genuinely touched (a real refresh, not a special migration run),
  rather than a single portfolio-wide batch pass. This avoids the biggest risk a one-shot
  migration creates — silently mis-mapping a unit whose wording changed enough to break a
  text match, across all 31 products at once — by never forcing a decision on a ledger
  nobody is actively working on.
- **Collision handling, addressed explicitly** (a real gap in the first draft): unit-level
  text is short enough (a paragraph or bullet) that near-duplicate units genuinely occur in
  this corpus — this codebase already has dedicated near-duplicate detection
  (`check_content_unit_probable_duplicate`, `check_content_unit_no_exact_duplicate_merge`)
  because of it. A bare content hash is not sufficient identity at this granularity; salt
  the hash with the unit's position *within its owning section* (stable unless the section
  itself is restructured, which is a real and appropriate case for a fresh id) rather than
  its position in the whole document (unstable under any earlier edit). The existing
  duplicate-detection checks stay in place — this fixes stability, not duplication, and the
  two problems remain independent.
- **Canary selection, split by purpose rather than treated as one list**: two products with
  a *clean* known baseline prove the mechanism works (`pdf/net` — largest, most structurally
  representative; `slides/java` — the sparse-structure-ledger pattern). `email/cpp` is
  deliberately **not** a general-purpose canary here — Phase 4 row 26 already found its
  `content-dispositions.json` was built against a wrong/stale "old readme" baseline, so
  re-keying it would either bake that corruption into new hash ids (a false-clean result) or
  dump everything into `UNRESOLVED` for a reason unrelated to the migration logic. Use
  `email/cpp` instead as the dedicated negative-path test: prove the migration correctly
  routes known-bad input to `UNRESOLVED` rather than silently accepting it, as its own
  separate, explicit test case.
- **Regression control**: a new test that inserts a unit before an existing one and asserts
  every *other* unit's `content_hash` is unchanged (positional `unit_id` is expected to
  shift; that's exactly the property being replaced) — the one test that would have caught
  this defect class at design time.
- **Revised risk/effort**: Medium-to-High, larger than first estimated. Four independent
  ledger families, ~20+ consuming functions, and a lazy per-product rollout (rather than one
  batch) means this item alone likely spans several work sessions, not one.

### II. Bidirectional disposition coverage, as a structural pattern not a per-section patch
Every "does every OLD unit have a disposition" check gets a paired check asking "does every
element of the CANDIDATE's own real structure (headings, badges, sections) trace to either
an old-unit disposition or an explicit new-content declaration." This generalizes
`phase6-remediation-plan.md`'s `RC-disposition-bidirectional-coverage` item into the actual
structural fix — closing the one-directional blind spot (13/31 products missing Dependencies-
section coverage) as a *class*, not by special-casing one section name.

### II-b. Two cheap, high-leverage fixes this document's first draft omitted entirely
Flagged directly by the critique pass: two of the audit's own findings — one the "cheapest
fix-to-impact ratio in the entire matrix," the other affecting 100% of the portfolio and
already fully root-caused — had no proposal anywhere in the first draft. Both are small
enough to schedule early, ahead of the heavier items above, precisely because they're cheap:
- **Navigation TOC parity** (Phase 4 row 22, 9/31 products, 29%): no check today parses the
  Navigation section's own linked heading list and diffs it against the document's real
  `##` headings. A single new check doing exactly that — flagging both a missing Navigation
  entry for a real heading and an invented entry with no matching heading — closes this
  class outright. No architectural change needed; this is genuinely just a missing check,
  not a symptom of any deeper structural weakness above.
- **The shared write-path bug behind `verified_by_run_id`-always-null and the CRLF hash
  mismatch** (Phase 5 Cluster H, both traced to `_write_candidate_verification_marker`,
  `readme_refresh_run.py:584-594`): already root-caused precisely in the closed audit — the
  hash is computed over `read_text()`'s universal-newline-translated content rather than the
  file's real on-disk bytes (fix: hash the raw bytes), and `audit_portfolio`'s own
  `run_id=None` write unconditionally clobbers whatever a prior bound run legitimately
  recorded (fix: preserve or namespace the field so a read-only audit sweep cannot erase a
  real run's provenance). Both are small, well-understood, single-function fixes with a
  clear regression test (assert the recorded hash matches raw on-disk bytes; assert an
  `audit_portfolio` sweep does not overwrite a `run_id` written by a prior `ingest_candidate`/
  `recheck` call).

### III. One authoritative freshness manifest for generation inputs, not five ad hoc staleness checks
A `freshness_manifest.json` per product, written by a new, explicit, out-of-band `reconcile`
step (not embedded in the offline 103-check battery — that purity is worth preserving, see
§2): clone-cache HEAD + live-fetch comparison, knowledge-bundle `bundle_generated_at`/
`repo_sha`, package-registry last-checked timestamp, upstream-issues.md's pinned SHA — each
with an explicit status (FRESH / DRIFTED / UNKNOWN; never silently absent, and a failed live
check must record UNKNOWN, never be conflated with FRESH).
- `plan` refuses to proceed past a DRIFTED clone-cache without an explicit override (closes
  Cluster B row 4 at its source instead of downstream); `last-verified.json` must cite this
  manifest's timestamp (closes row 2); `upstream-issues.md` generation must re-diff against
  the manifest's HEAD before being trusted as input (closes row 3).
- **Why this is structural, not "one more check"**: it centralizes four independently-wrong
  input-staleness questions into one artifact every stage reads and writes, so a future fix
  to "how do we know an input is stale" happens once, not four times.
- **Precedent, corrected from the first draft**: this is not entirely novel scope. A working
  `gh api` call with an established timeout/error-handling pattern already exists in
  production (`_preflight_access_check`, `readme_refresh_run.py:904`) — the freshness
  manifest's live-fetch step follows that same pattern, it does not introduce live network
  access to this codebase for the first time. What genuinely is new is doing this on a
  schedule/reconciliation basis rather than as a one-shot preflight gate, and the failure
  handling below still needs to be built and tested for that different usage pattern.
- **Failure handling, stated honestly**: rate limits and transient network errors are real
  and need explicit handling for the *reconciliation* usage pattern specifically (repeated,
  scheduled calls, not the preflight's single check-and-proceed) — a failed reconciliation
  attempt must produce UNKNOWN, never be silently skipped or treated as FRESH.

### III-b. Publication-ledger reconciliation, as its own explicit mechanism — the largest defect class in the audit, addressed directly
This was under-specified in the first draft of this document, which gestured at it inside
§III's generation-input framing without a concrete design; it deserves one, since Phase 4
row 20 (17/31 products, 55%) is the single most-recurring confirmed defect in the whole
audit — larger than any other class by a wide margin. This is not an input-freshness problem
(§III) — it is an output-tracking problem, and `_published_readme_current_findings`'s
structural limitation is that it can only ever re-check a publication the ledger already
claims to know about; it has no way to detect one it doesn't.
- **Proposed mechanism**: a separate, scheduled reconciliation job — not part of the
  freshness manifest, not part of the 103-check battery — that periodically calls
  `gh api repos/{org}/{repo}/commits`/`.../pulls` for every registered product and diffs the
  result against `data/readme_published_state.json`/`reports/repo_presenter_actions.jsonl`,
  flagging any real commit/merge touching `README.md` with no corresponding ledger entry.
- **Explicit limit, stated rather than implied**: this closes the "missed backfill sweep"
  and "published then locally re-edited" causal mechanisms Phase 5 identified, but *not*
  barcode/python's mechanism — a genuinely out-of-band manual commit made entirely outside
  any PR history this repo can query is, by construction, invisible to any reconciliation
  job built on `gh api` history. No design proposed here closes that specific gap; it is a
  process/discipline question (route all publication actions through the pipeline, never a
  manual out-of-band commit), not a technical one.

### IV. A tiered, honest claim-verification system — not "add an LLM grader"
Cluster C (evidence-exists ≠ claim-true) is the single largest defect class (10+ findings,
9+ products). Full semantic verification of arbitrary prose against arbitrary source is an
open problem — I am not proposing it as solved. Instead: require the composing step to tag
every capability/count/support/accessibility claim with a structured claim TYPE and its
exact evidence pointer, as metadata alongside the prose, not inferred after the fact. Route
each type to the cheapest verification method that can actually validate it:
- **COUNT claims** ("854 public types") → deterministic recount against `api_surface.json`,
  exact match, hard gate. Fully mechanical; would have caught cells/java's 44%-wrong claim
  and several type-count findings outright.
- **EXISTENCE/SUPPORT claims** ("supports DOCX") → deterministic keyword-presence/negation
  grep against the cited evidence file as a first-pass hard gate (would have caught
  pdf/java's DOCX case directly). Escalate to an LLM semantic pass only when the deterministic
  pass is ambiguous, and treat that pass's verdict as **advisory, flagged for human
  confirmation — never a silent pass.** This tiering is the honest design: cheap-and-strict
  first, expensive-and-fallible second, never trusted silently.
- **ACCESSIBILITY claims** (a code example referencing a class member) → cross-reference the
  scout's own visibility field once §3.V lands. Deterministic, no LLM needed.
- **Explicit limit**: this does not solve cases requiring real domain tracing — 3d/python's
  FBX shadow-duplicate-bug misattribution needed runtime-behavior tracing a human reviewer
  did by hand; no tier proposed here catches that class today. Say so, don't imply otherwise.

### V. Fix scout-layer defects at their source, not with downstream workarounds
The C++ scout's hardcoded `visibility: "public"` (Cluster D-ii) and the shared `formats.py`
extractor's shallow pattern-matching (Cluster D-i, an estimated 14+ consumers) are upstream
of `readme-refresh` — they belong to S-34 (repo-scout)/knowledge-enrich. The durable fix is
correcting the field at the source and having `readme_refresh_checks.py` consume it, not
adding compensating logic inside readme-refresh for a bad upstream field — that would be
exactly the "isolated workaround" this pass was asked to avoid.

### VI. Make prose non-determinism observable and bounded, without claiming to eliminate it
Full templating is not proposed — it would be a larger, riskier rewrite than the evidence
justifies, and it would discard the "plan never writes prose, composition does" split, which
is a good architectural boundary (§2). Instead:
1. The composing step emits the §3.IV claim-taxonomy metadata as a required, checkable
   structured side-channel — a real output-schema requirement, not a template.
2. **Redefine the rerun-consistency regression control**: rerun composition twice against
   identical pinned inputs and assert the 103-check-plus-new-tiers **pass/fail profile is
   unchanged** between runs — not that the prose is byte-identical. This is the achievable,
   honest target: wording may legitimately vary; whether it passes the same gates must not.
   This directly revises the closed audit's own canary/rollout template (step 8) — that
   guidance was correct for mechanical fixes and should be read as inapplicable to anything
   the free-form composer touches.
3. Log and diff the `--acting-model` value across reruns as a recorded signal (the flag
   already exists; today nothing consumes it for this purpose).

**Feasibility gap, corrected from the first draft, which called this "a permanent CI
addition" without checking whether that's actually possible**: composition today is an
interactive, agentic step with no scriptable, non-interactive entry point anywhere in the
test suite (confirmed directly — none of the three `test_readme_refresh_*.py` files invoke
it; the closest thing, `test_extract_*_is_deterministic`, only tests pure extraction
functions, not composition). Running item 2 "in the normal CI suite" as stated would require
building batch-composition infrastructure that doesn't exist today, plus a real per-run
token/compute cost this document did not budget. **Revised proposal**: run item 2 as an
explicit, manually-triggered gate before any future portfolio-wide remediation pass (Stage 4
below), and as a periodic (e.g. monthly) scheduled check outside the normal per-commit CI
path — not folded into the standard test suite until real batch-composition tooling exists
to make that affordable and reliable.

### VII. Structurally prevent an unreviewed agent-driven push, not just label who approved it
The first draft proposed requiring `approve` to carry "a human-actor identity distinct from
any automated session-id pattern." The critique correctly found this doesn't close the real
hole: `session_identity.py` resolves identity from exactly three automation-thread sources
(`AGENT_SESSION_ID`/`CODEX_THREAD_ID`/`CLAUDE_CODE_SESSION_ID`) with no OS-user/SSO/git-
identity concept anywhere in the system, and this pipeline's entire calling convention is
"an agent acts on a human's behalf" — an under-instructed agent can produce a string in
"human-actor shape" as easily as it calls `approve()` directly today. A naming convention
cannot fix an authority problem.

**Revised mechanism**: move the actual point of human control from a string an agent can
supply to an action only a human, using their own real GitHub credentials, can perform —
require every push to open a real PR (already how the system works, `gh pr create`) and
gate `data/readme_published_state.json`'s "published" status *exclusively* on a real,
externally-observed **PR merge event** (via `gh api`, checking the merging actor's GitHub
identity is not the pipeline's own bot/token identity), never on the pipeline's own
`approve`/`push` call succeeding. This doesn't require inventing a new identity primitive —
it relocates the actual gate to something that already requires a human with real repository
permissions to click, and it composes directly with §III-b's reconciliation job (which
already needs to read PR/merge history). It is not perfect either — a human could still
merge without real scrutiny — but it removes the specific failure mode named in this
document (an agent completing its own approval loop end-to-end), which a naming-convention
fix does not.

## 4. Sequencing (system first, then outcomes — the user's explicit priority)

- **Stage 0 — Freeze.** No further candidate regeneration or portfolio-wide content fixes
  until Stage 1-3 are canary-proven. Exception: the closed audit's own Tier-1 already-live
  items proceed as narrow, human-reviewed single-file patches, unchanged from
  `phase6-remediation-plan.md`.
- **Stage 1a — Cheap wins first** (§3.II-b: Navigation TOC parity, the write-path-marker
  fix). No canary needed beyond the standard single-fix regression test — these are small,
  independently well-understood, and there's no reason to gate them behind the larger items.
- **Stage 1b — Identity and coverage** (§3.I, §3.II). Canary per §3.I's own split selection
  (`pdf/net`/`slides/java` for the positive path, `email/cpp` for the negative/`UNRESOLVED`
  path), using this repo's own established Repair Loop (build → prove fails closed → run
  against real content → fix → regression-test → portfolio rollup — see
  [[project_readme_refresh_repo_presenter_plan]] for why this pattern is trusted here).
- **Stage 2a — Scout-layer fixes** (§3.V, in S-34/knowledge-enrich, not readme-refresh
  itself) — sequenced explicitly ahead of Stage 2b since §3.IV's accessibility-claim tier
  depends on the corrected visibility field existing first; the first draft named this
  dependency in prose but never gave it its own stage.
- **Stage 2b — Freshness, publication reconciliation, and claim verification** (§3.III,
  §3.III-b, §3.IV). Canary on the products that most exercised Cluster C (`cells/java`,
  `words/net`, `3d/python`) and Cluster B (`pdf/net`, `pdf/python`); §3.III-b's
  reconciliation job can be smoke-tested against the already-known 17-product gap as its own
  correctness proof (it should rediscover all 17, not a subset).
- **Stage 3 — Generation instrumentation and gate enforcement** (§3.VI as a manually-
  triggered/periodic gate, not folded into per-commit CI yet; §3.VII's PR-merge-based gate).
- **Stage 4 — Only now: re-run generation/verification across the full portfolio** using the
  hardened system, as its own separately-scoped mission, under the same canary-first,
  no-blind-regeneration discipline already established — this is "reuse the healed system to
  fix the outcomes."
- **Stage 5 — Close the loop on Stage-0's interim patches**: re-verify the 6 Tier-1 items
  through the now-hardened pipeline rather than leaving hand-patches as the permanent state.

## 5. Validation and regression controls

- Every Stage 1-3 item ships with: a failing-first regression test reproducing the exact
  confirmed defect (this audit already has 31 fully-documented real cases with exact
  citations to draw fixtures from), a canary regeneration, and the redefined
  rerun-consistency check from §3.VI (verification-outcome-identical, not byte-identical
  prose).
- **Portfolio gate before Stage 4 begins**: re-run this audit's own manual four-way
  methodology (not just the automated checks) on the same 7 canaries, and require the
  hardened system to independently *rediscover* the specific known defects it was built to
  catch (cells/java's 44% narrative, pdf/net's version drift, words/net's Shapes[0].Chart)
  before trusting it to find *unknown* defects in the real Stage 4 remediation pass — prove
  it against known answers first.
- **§3.III-b's own correctness proof**: run the publication-reconciliation job against the
  current portfolio and require it to surface all 17 already-known ungapped products (not a
  subset) before trusting it to find new gaps going forward.
- The §3.VI rerun-consistency check, run as the manually-triggered/periodic gate described in
  §3.VI (not folded into per-commit CI without real batch-composition infrastructure first)
  — the durable control against silently reintroducing the exact non-determinism this pass
  diagnosed, scoped to what's actually achievable today.

## 6. Tradeoffs, risks, and honest limits

- **Migration risk (§3.I)**, reduced but not eliminated by moving to additive/lazy rollout:
  re-keying still risks mis-mapping a unit whose wording changed enough to break a text
  match, but only one product at a time, on its own next real refresh, not all 31 at once —
  and an explicit unresolved-bucket means a bad match is surfaced, not silently accepted.
  The residual risk is scope creep: because re-keying happens lazily, a portfolio-wide,
  consistently-identified ledger takes longer to reach than a one-shot migration would (a
  real tradeoff of the safer approach, not a free win).
- **Freshness manifest and publication reconciliation (§3.III, §3.III-b) are a genuine scope
  expansion of usage pattern, even though the underlying `gh api` mechanism has production
  precedent** (`_preflight_access_check`) — a single preflight check and a recurring,
  scheduled reconciliation job have different failure-mode profiles (repeated exposure to
  rate limits and transient errors), and the latter's handling needs its own testing, not an
  assumption that the existing pattern covers it. §3.III-b also has a named, un-closeable
  gap: it cannot detect a genuinely out-of-band manual commit (barcode/python's confirmed
  mechanism) — that remains a process discipline question, not a technical one this design
  solves.
- **Claim verification (§3.IV) does not solve semantic accuracy** — it narrows the problem to
  what's mechanically checkable and makes the remaining, genuinely hard cases explicit and
  human-escalated rather than silently trusted. That is a real improvement, not a fix.
- **Rerun consistency is redefined, not achieved in the strict sense** — §3.VI is an explicit
  correction of this same author's own earlier guidance (the closed audit's canary/rollout
  template asked for byte-identical regeneration, which is not realistic for free-form prose).
  Anyone executing this plan should read that earlier guidance as superseded by §3.VI, not as
  a second, conflicting requirement.
- **This redesign does not resolve business/authority decisions** — font/python's GitLab-
  canonical-vs-GitHub-mirror publish-target question remains a human decision no amount of
  system hardening can make for us.
- **Cost, revised upward after the critique pass corrected the scope**: Stage 1-3 is a large
  engineering investment, larger than this document's first draft estimated. Content-
  addressed identity alone touches ~20+ functions across four independent ledger families,
  not ~7 in one; the freshness manifest and publication reconciliation are new shared
  infrastructure touching `plan`/`start`/`approve` plus a new scheduled job; claim-taxonomy
  touches the composition contract and at least 2 major checks; and §3.VI's rerun-consistency
  check cannot be a normal CI item until batch-composition tooling is built, which is its own
  real, unscoped piece of work. This reads as **months of focused engineering across several
  work sessions, not weeks** — plan and stage it accordingly rather than as a short patch
  series. The cheap wins in §3.II-b are the one place a "days, not weeks" estimate genuinely
  holds.
- **Confidence calibration**: SW-1, SW-3, and SW-4 are backed by direct evidence (code reads,
  the system's own comments, this audit's own findings, independently re-verified in the
  adversarial pass) and held with high confidence. SW-5's characterization of prose
  non-determinism is inferred from the absence of any determinism test or control, not from
  directly observing two divergent reruns — a reasonably confident inference, not a proven
  fact, and worth a small, cheap confirming experiment (rerun composition twice on one
  pinned-input product and diff the output) before treating it as settled. §3.I's revised
  effort estimate and §3.VII's PR-merge mechanism are this document's own second-pass
  corrections, not independently re-verified by a third pass — reasonably confident, not
  certain.
