# Phase 6d — Freshness/Staleness Reuse-First Deep Assessment

Independent, first-principles pass (not a reassessment of phase6c's conclusions — a fresh
investigation of shared infrastructure), triggered by the user's explicit caution: before
proposing that readme-refresh should trigger clone/knowledge refresh itself, investigate
who else already depends on that machinery, and whether equivalent capability already
exists. **It does — extensively.** This materially revises phase6c's RC-3
(`RC-upstream-divergence-classifier`), which proposed building a new ancestry classifier;
that classifier already exists, tested, in production, at
`scripts/pipeline/lib/baseline_resolver.py`. This document supersedes that one proposal
explicitly (via a `SUPERSEDED` taskcard status, not a silent edit) and leaves every other
phase6/phase6b/phase6c item untouched.

## Assessment scope

- **System/component**: the freshness/staleness detection-and-enforcement chain shared
  across all knowledge-consuming generation skills, and specifically whether/how
  `readme-refresh` should participate in it.
- **Intended outcome**: no generation skill (readme-refresh included) should produce output
  from knowledge it cannot establish is current, and the mechanism for establishing
  currency should be one shared, tested implementation — not N independent reinventions.
- **Current sources of truth**: `knowledge/{family}/{platform}/merged/model.yaml`'s
  `stale_since`/`repo_sha`/`bundle_generated_at` fields (the durable staleness record);
  `scripts/pipeline/lib/freshness_guard.py` (the enforcement gate); `scripts/pipeline/lib/baseline_resolver.py`
  + `scripts/pipeline/lib/baseline_ledger.py` (the ancestry/reachability record and walker);
  `.github/workflows/upstream-monitor.yml` (the only automatic trigger in this chain).
- **Inputs and consumers of `freshness_guard.is_generation_allowed()`**: `batch_reference.py`,
  `refresh_run.py`, `launch_gate.py`, `readiness_gate.py` — confirmed by direct code read.
  `readme_refresh_run.py` is not among them (confirmed by exhaustive grep, zero matches for
  `freshness_guard`, `is_generation_allowed`, `check_freshness`, or `stale_since` anywhere
  in that file).
- **Evidence inspected**: full reads of `freshness_guard.py` (all functions), `baseline_resolver.py`
  (all functions), the exact call site in `batch_reference.py:1852-1882`; `skills/knowledge-diff.md`,
  `skills/change-sweep.md`, `skills/mechanism-sweep.md`, `skills/repo-patrol.md` in full;
  `.github/workflows/upstream-monitor.yml`'s schedule; live state of `knowledge/font/python/merged/model.yaml`
  (`stale_since: null`, `repo_sha: 136b6e2...`, `bundle_generated_at: 2026-08-14`, no
  `orphaned_sha` key) checked today, 6 days after the confirmed live history-replacement;
  a repo-wide grep for every `update_clone()` call site and every consumer's locking
  behavior.
- **Missing evidence, stated honestly**: I could not find a repo-local artifact confirming
  whether the scheduled Monday 2026-08-24 run of `upstream-monitor.yml` actually executed,
  what it found for `font/python` specifically, or why its result (if any) never propagated
  into `stale_since`. GitHub Actions run logs are not mirrored into this repo's own
  `reports/` tree in any location I found (`reports/mechanism_sweep/` has one unrelated
  entry; no `reports/change_sweep/` directory exists locally). This is itself a finding
  (see Structural weaknesses) rather than a gap I can currently close from this
  environment.

## Current-state reconstruction

### The freshness/staleness chain that already exists (three tiers, confirmed by direct code read)

1. **Automated detection (weekly, no human trigger needed)**: `.github/workflows/upstream-monitor.yml`
   (cron `0 8 * * 1`, Monday 08:00 UTC) runs `repo_patrol.py sweep` (S-94 `change-sweep`).
   This calls `update_clone()` for every active product, compares stored vs. new SHA, and
   classifies impact HIGH/MEDIUM/LOW via a **naive `git diff --name-only` file-extension
   heuristic** (`_classify_impact`, `repo_patrol.py:881-926` — not an ancestry check; it
   returns `MEDIUM` on any non-zero diff exit without distinguishing an ordinary diff from
   an unreachable/orphaned SHA). **By its own skill file's explicit statement
   (`skills/change-sweep.md:50`): "Sweep is read-only. It does NOT set `stale_since` — that
   is S-12 responsibility."**
2. **Precise, ancestry-aware classification (agent-executed, not automatically triggered)**:
   `/knowledge-diff` (S-12), "recommended after S-94 flags MEDIUM/HIGH" — a human or agent
   decision, not an automatic handoff. Its real logic lives in `baseline_resolver.py`:
   `git_reachable(repo_path)` (lines 85-102, `git cat-file -e {sha}^{commit}`) and
   `resolve_baseline_sha()` (lines 129-196), which walks the baseline ledger for a reachable
   ancestor and **raises `OrphanedBaselineError`** (line 196) when nothing is reachable —
   this is the exact, already-built, already-tested mechanism that would correctly classify
   `font/python`'s history-replacement as fundamentally different from `page/python`'s
   ordinary advance. Step 6 of the skill (`knowledge-diff.md:157-166`) writes both
   `stale_since` and `orphaned_sha: true` to `model.yaml` for this case, unconditionally.
3. **Enforcement (the actual hard-stop gate, already shared by 4 consumers)**:
   `freshness_guard.is_generation_allowed(family, platform, mode="degraded")`. In `degraded`
   mode — the mode every generation-time consumer uses to avoid a network round-trip per
   run — the check (`check_freshness`, lines 258-355) reads `model.yaml["stale_since"]`
   (line 321-332) and a cross-source agreement check; it makes **no live git call** and
   **never invokes `baseline_resolver`'s ancestry logic**. Only `mode="strict"` does a live
   `git ls-remote` + plain SHA-equality comparison (lines 334-355) — sufficient to detect
   *that* something changed, but not to classify *how*.

### The gap, precisely located

`readme_refresh_run.py` calls **none of the three tiers**. It has its own, narrower,
fourth mechanism — pinning `clone_cache_head` at `start` (raw `git rev-parse HEAD`, no
fetch) and comparing it at `converge-verify` to mark blocks `INVALIDATED_BY_SOURCE_CHANGE`
(lines 3354-3374) — but this only detects drift if *something else* already advanced the
local clone; it never fetches, and is gated behind `--apply-invalidation`, opt-in. This
machinery is sound and does not need to be rebuilt; it is simply never fed a live signal.

**Live, dated proof that the existing three-tier chain has a real handoff gap, independent
of readme-refresh entirely**: `font/python`'s `model.yaml` today (2026-08-26) still shows
`stale_since: null`, `repo_sha: 136b6e2...` (predating even the 2026-08-15 PR merge), and no
`orphaned_sha` key — six days after the live, confirmed history-replacement, and past at
least one scheduled Monday sweep window. Whether the automated sweep ran and flagged this
correctly but nobody ran `/knowledge-diff` next, or the sweep itself failed to flag it, or
did not run at all, I cannot determine from this environment (Missing evidence, above) —
but the observable fact is unambiguous: **the existing automated tier did not result in
`stale_since` being set**, for a case unambiguous enough that it should have.

## Symptoms

- `readme_refresh_run.py` generates content without ever checking `stale_since`,
  `freshness_guard`, or any live signal — confirmed by exhaustive grep.
- `font/python`'s `stale_since` is still `null` 6 days after a confirmed real-world upstream
  history replacement, despite a weekly automated sweep mechanism that exists specifically
  to catch this class of event.
- `page/python`'s knowledge is pinned to a SHA predating the maintainer's own subsequent
  real push by 12+ days as of today, with the same `stale_since: null` non-signal (this was
  already established in phase6c; restated here as a second instance of the same
  handoff gap, not a new finding).

## Root causes

### RC-1 (revised from phase6c): readme-refresh omits an established, shared compliance gate — a governance gap, not an architecture gap
- **Evidence**: `freshness_guard.is_generation_allowed()` has exactly 4 real consumers
  (`batch_reference.py:1871-1878` read directly), each an exact-pattern reuse of the same
  function; `readme_refresh_run.py` has zero references to it or to `stale_since` anywhere.
- **First failing boundary**: `plan_run()` in `readme_refresh_run.py` (line ~1856) — the
  exact point where the file's own docstring already admits *"an absent claims.json/model.yaml
  degrades to `{claims: [], repo_sha: None}`... never fatal"* — the opposite of AGENTS.md
  §5a's "HARD STOP" requirement.
- **Affected scope**: readme-refresh specifically; the other 4 generation-skill consumers
  already comply.
- **Why existing controls missed it**: AGENTS.md §5a's "and all generation skills" is
  enforced by convention/manual migration (four scripts were updated to call the shared
  function when it was introduced), not by any mechanical registry check that every
  qualifying skill actually does — so a fifth generation skill (readme-refresh, built
  separately) simply fell outside the update without anyone's decision to exclude it.
- **Confidence**: High — directly read every relevant file; §5a's text has no exclusion
  clause and the rule has been actively maintained (2026-08-14/19 change-notes) well after
  readme-refresh existed, ruling out "predates the rule."

### RC-2 (unchanged from phase6c, reconfirmed not covered by anything found in this pass): regeneration has no live-published-content awareness
No existing mechanism inspected in this pass (freshness_guard, baseline_resolver,
change-sweep, repo-patrol) compares a new candidate against what is currently, correctly
live before allowing generation to proceed. This remains a genuinely new gap, not something
this deeper investigation found already solved elsewhere.

### RC-3 (revised from phase6c — superseding `RC-upstream-divergence-classifier`): the real ancestry classifier exists, but is decoupled from the cheap gate every generation-time consumer actually calls
- **Evidence**: `baseline_resolver.py::resolve_baseline_sha()`/`git_reachable()` is real,
  tested, and already used by S-12 — but `freshness_guard.check_freshness(mode="degraded")`,
  the mode every existing generation-time consumer uses, never calls it; only
  `mode="strict"` does a live check at all, and even `strict` mode does plain SHA-equality,
  not ancestry-walking.
- **First failing boundary**: the boundary between `freshness_guard.py` (the gate every
  generation skill actually calls) and `baseline_resolver.py` (the module that could answer
  the ancestry question) — they do not call each other.
- **Affected scope**: **portfolio-wide and pre-existing** — this affects the 4 already-
  compliant consumers exactly as much as it would affect readme-refresh if readme-refresh
  adopted the identical pattern. This is not a readme-refresh-specific gap.
- **Why existing controls missed it**: `baseline_resolver`'s ancestry logic was built for,
  and wired only into, the agent-executed S-12 workflow's own narrower use case (resolving
  which SHA to diff against) — nobody has yet connected it to the cheap, no-network gate
  every generation-time caller actually uses for the different, related question ("is it
  safe to generate right now").
- **Confidence**: High on the code-level disconnection (directly read both modules, found
  no cross-reference); Medium on whether this is the *sole* explanation for font/python's
  undetected state, given the unresolved Missing Evidence above about whether S-94 itself
  even ran/flagged this case.

### RC-4 (new): the only automatic trigger in the chain does not automatically produce the durable signal enforcement depends on
- **Evidence**: `skills/change-sweep.md:50`'s own explicit statement that sweep "does NOT
  set `stale_since`"; `/knowledge-diff` is described in its own skill file as "recommended,"
  not triggered; live, dated proof (`font/python`'s `stale_since: null`, 6 days post-wipe,
  past a scheduled sweep window).
- **First failing boundary**: between S-94's automated detection output and S-12's
  stale_since-writing step — a human/agent judgment call sits in between with no forcing
  function.
- **Affected scope**: portfolio-wide, affects every product, independent of readme-refresh.
- **Why existing controls missed it**: this was a deliberate design choice (ordinary drift
  genuinely benefits from a human/agent's semantic judgment before committing to a
  regeneration cycle) that does not distinguish the ordinary case from the unambiguous,
  high-severity orphaned-SHA case, where no judgment call is actually needed to know
  something is wrong.
- **Confidence**: High on the structural gap itself (documented in the skill's own text);
  Medium-low on the specific causal explanation for font/python's exact 6-day silence
  (could be this gap, could be a sweep execution failure — Missing Evidence).

### RC-5 (new, minor): `update_clone()`'s `git reset --hard` has no lock scoped to the clone directory
- **Evidence**: `clone_cache.py:181-189` (the reset call) has only a best-effort toplevel
  safety check (lines 152-168), no acquire/release around the mutation itself.
- **First failing boundary**: any two of the 5 existing callers (`refresh_knowledge.py`,
  `mechanism_sweep.py`-adjacent via `repo_patrol.py`, `repo_patrol.py`) invoked concurrently
  today already race on this.
- **Affected scope**: shared infrastructure, pre-existing, independent of any new caller.
- **Confidence**: High (directly read the function, confirmed no lock acquisition).

## Structural weaknesses

1. **§5a's "all generation skills" has no mechanical enforcement of its own scope** — it is
   a prose rule enforced by whoever happened to migrate their script when
   `freshness_guard.py` was introduced. A future 6th generation skill could omit it exactly
   as readme-refresh did, invisibly, until someone happens to audit it the way this pass
   did.
2. **Detection and enforcement are split across three independently-evolving mechanisms
   with a human-judgment gap at the only automatic trigger.** S-94 (automatic, imprecise),
   S-12 (precise, manual), freshness_guard (enforcement, degraded-mode-blind to what S-12
   could tell it) do not compose into one closed loop even for the 4 skills that already
   use freshness_guard correctly.
3. **No audit trail connects "the sweep ran" to "here is what it found" in a place anyone
   (including this investigation) can inspect after the fact.** Even if the chain worked
   perfectly, there is no way to *prove* it did without re-deriving the evidence by hand,
   exactly as this pass had to.

## What should be preserved

- **`freshness_guard.is_generation_allowed()` as the single shared gate.** Extend it; do
  not have readme-refresh bypass it with a parallel check.
- **`baseline_resolver.py`'s ancestry-walk logic**, exactly as built and already proven for
  S-12 — reuse its output, do not reimplement `git cat-file -e` elsewhere.
- **The degraded/strict mode cost-conscious design** — any fix must not force a network
  call into every generation run by default; that tradeoff was made deliberately and
  correctly for the ordinary case.
- **S-94's weekly cadence and read-only detect-and-classify design** — sound; the gap is
  downstream of it, not in its own detection logic.
- Everything already established as sound in phase6b §2 and phase6c (state machine,
  disposition concept, offline check-battery purity, `update_clone`'s fetch+reset mechanics
  themselves).

## What must be redesigned

1. **readme-refresh must call `freshness_guard.is_generation_allowed()`** at the same point
   `batch_reference.py` does (top of the generation-planning step) — pure reuse, closes
   RC-1. This is correct and should ship regardless of anything else below, since it closes
   an unambiguous compliance gap even before the deeper chain is fixed.
2. **`freshness_guard.check_freshness()`'s degraded-mode path should additionally consult
   `baseline_resolver`'s local (no-network) reachability check** against the last-known
   ledger SHA — closes RC-3 for the 4 existing consumers *and* readme-refresh at once,
   without paying strict mode's network cost, since `git cat-file -e` against an
   already-local clone is a local operation.
3. **`repo_patrol.py`'s sweep should distinguish "ordinary diff" from "SHA unreachable"** at
   detection time (it already fetches; it already could call `git_reachable`), and for the
   unreachable case specifically — an unambiguous, no-judgment-required signal — write
   `stale_since`/`orphaned_sha` directly, without waiting for a separate, manually-triggered
   S-12 run. The ordinary HIGH/MEDIUM drift case keeps its current "recommended, human/agent-
   mediated" path unchanged — this preserves the deliberate design choice for the case where
   judgment adds value, and only removes the gap for the case where it doesn't.
4. **`update_clone()` should acquire a clone-path-scoped lock** before `git reset --hard` —
   shared-infrastructure fix, benefits all 5 existing callers, contained and low-risk.
5. **A new live-published-content regression gate** (RC-2, carried forward unchanged from
   phase6c's `RC-live-published-regression-gate`).
6. **A portfolio-level test or registry check** asserting every skill classified as a §5a
   "generation skill" actually calls `is_generation_allowed()` — prevents a future silent
   6th omission.

## Production-grade target design

```
.github/workflows/upstream-monitor.yml (weekly, unchanged cadence)
  → repo_patrol.py sweep (existing fetch + diff)
      → [NEW] git_reachable() check on the stored baseline SHA
          → unreachable  → [NEW] write stale_since + orphaned_sha directly (no human wait)
          → reachable, diff nonzero → existing HIGH/MEDIUM/LOW path, "recommended" S-12 (unchanged)
knowledge/{family}/{platform}/merged/model.yaml (stale_since / orphaned_sha, existing schema)
  → freshness_guard.check_freshness(mode="degraded")
      → [NEW] also consults baseline_resolver's local reachability signal directly
          (closes the case where stale_since somehow still wasn't set, at zero network cost)
  → freshness_guard.is_generation_allowed()  (existing, unchanged interface)
      → batch_reference.py / refresh_run.py / launch_gate.py / readiness_gate.py (existing, unaffected)
      → [NEW] readme_refresh_run.py::plan_run() (new 5th consumer, same call pattern)
readme_refresh_run.py::ingest_candidate()
  → [NEW] check_no_regression_vs_live_published (RC-2, independent of the above chain)
```

**Responsibilities**: unchanged ownership — S-94 still owns detection, S-12 still owns
nuanced human/agent-mediated classification for the ordinary case, `freshness_guard` still
owns enforcement, `readme-refresh` becomes a consumer like the other 4, not a new authority.
**State model**: `model.yaml`'s existing `stale_since`/`orphaned_sha` fields, unchanged
schema — this design adds writers and readers, not new state. **Compatibility**: additive
throughout; every change point wraps or extends an existing function's behavior for a case
it previously didn't handle, never altering behavior for the cases it already handled
correctly (this must be the explicit acceptance criterion for item 2's regression tests).

## Implementation direction

1. **readme-refresh compliance call** (item 1) — smallest, safest, zero shared-infra risk,
   ship immediately, independent of everything else.
2. **`update_clone()` locking fix** (item 4) — small, contained, shared but low-risk, ship
   early.
3. **`freshness_guard` degraded-mode extension** (item 2) — touches shared infrastructure
   used by 4 existing consumers; requires their full test suites to pass unchanged before
   and after, plus new tests for the newly-added reachability branch. Higher risk, sequence
   after 1 and 4.
4. **`repo_patrol.py` sweep auto-write for the unreachable-SHA case** (item 3) — depends on
   (3)'s reachability check existing as a clean, reusable function first; do not duplicate
   the `git_reachable` call.
5. **Live-published-content regression gate** (item 5) — independent track, can proceed in
   parallel with 1-4.
6. **Portfolio compliance test** (item 6) — cheap, do last, once the true target consumer
   list (5, not 4) is settled.

**Safeguards**: every shared-infrastructure change (2, 3, 4) must be proven against the 4
existing consumers' own test suites with zero regressions before being considered complete
— this is a harder bar than "the new behavior works," and should be treated as the primary
acceptance criterion given the blast radius.

## Verification strategy

```
REAL INPUT: font/python (live, orphaned/unreachable SHA, confirmed today)
          + page/python (live, ordinary fast-forward advance, confirmed today)
→ OFFICIAL ENTRY POINT: repo_patrol.py sweep / readme_refresh_run.py plan_run()
→ SYSTEM PROCESSING: git_reachable() classification / freshness_guard gate
→ STATE OR ARTIFACT: model.yaml stale_since + orphaned_sha
→ VALIDATOR OR GATE: is_generation_allowed()
→ DOWNSTREAM CONSUMER: readme-refresh plan/ingest-candidate, plus the 4 existing consumers
→ OBSERVED RESULT: font/python correctly blocked/flagged; page/python correctly unaffected
```

- **Focused**: `git_reachable()` against fixture repos (unchanged, verified against real
  `baseline_resolver.py` test patterns already in the suite).
- **Integration**: run the extended sweep against real `font/python` (should now write
  `stale_since`/`orphaned_sha` without a manual S-12 invocation) and real `page/python`
  (should NOT trigger the unreachable path — ordinary fast-forward, existing behavior
  unchanged).
- **Negative control**: a product confirmed current (e.g. `note/python`) must show zero
  change in behavior through the whole chain.
- **Regression**: full existing test suites for `batch_reference.py`, `refresh_run.py`,
  `launch_gate.py`, `readiness_gate.py` must pass unchanged after the `freshness_guard`
  extension — this is the primary gate for item 2, not a nice-to-have.
- **Rerun/idempotency**: running the extended sweep twice against unchanged live state must
  produce identical `stale_since`/`orphaned_sha` writes both times (no double-write drift).

## Tradeoffs and risks

- **Benefit**: closes an unambiguous compliance gap (item 1) almost risk-free, and closes
  the deeper, portfolio-wide handoff gap (items 2-4) that independently affects the 4
  already-compliant consumers too — this is a materially higher-value fix than a
  readme-refresh-local patch would have been.
- **Cost/risk**: items 2-4 touch shared infrastructure with real blast radius across 4
  other consumers; this requires more careful, conservative rollout (a canary or feature
  flag, not a blanket change) than a purely additive readme-refresh-local change would.
- **Item 1 alone is not sufficient** to catch font/python's case — shipping it in isolation
  gives governance parity, not actual detection, since `degraded` mode's blind spot is
  identical for readme-refresh and the 4 existing consumers alike. This must be communicated
  plainly, not left implied.
- **Genuine unresolved uncertainty**: whether the automated sweep is even running/succeeding
  as scheduled is not confirmed from this environment — implementing items 2-4 without also
  checking the sweep's own operational health risks fixing the wrong link in the chain.
  Recommend a direct operational check (does `upstream-monitor.yml` show successful recent
  runs in GitHub Actions) before or alongside implementation.
- **Rejected alternative**: phase6c's original `RC-upstream-divergence-classifier` (build a
  new ancestry classifier for readme-refresh specifically) — rejected because it would
  duplicate `baseline_resolver.py`'s already-proven logic and create the exact "duplicated
  authority" weakness the assessment methodology explicitly warns against; superseded by
  this document's item 2/3, which extend the existing module's reach instead.

## Final assessment

**STRUCTURAL_REDESIGN_REQUIRED.** The readme-refresh-specific piece (item 1) is a small,
low-risk hardening fix — reuse, not redesign. But the deeper, motivating finding is that
the shared freshness/staleness chain itself has a structural, portfolio-wide gap (RC-3,
RC-4) that already affects the 4 currently-compliant consumers, independent of
readme-refresh entirely. Making readme-refresh comply with the existing (incomplete) pattern
closes one gap while leaving the larger one — the one that actually explains why
font/python's state went undetected for 6+ days — unaddressed. Both must be done; neither
alone matches what the evidence shows is actually broken.
