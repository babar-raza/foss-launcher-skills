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
     verified: 2026-08-12
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
```

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

4. **`ingest-candidate`** — runs the real deterministic checks module
   (`scripts/pipeline/commands/foss/readme_refresh_checks.py`, 49 `check_*` functions as of
   2026-08-12 — re-verify against `grep -c "^def check_" readme_refresh_checks.py` before
   trusting this number again; TC-HARDEN-16 tracks this doc's own self-consistency as real,
   deferred work, not solved here). **2026-08-08 diagram simplification (Tenth incident, MT024)**: the At-a-Glance
   diagram is now exactly `Product → Core Capabilities → Outputs`, with an optional 2-line
   `Starting Points` container ahead of `Product` for `hybrid`-archetype products only (up to 5
   capabilities in one column, 6+ split into 2 balanced columns) — no individual per-capability
   edges. **Hard gates** (any finding blocks the transition): required sections present in title
   case, no `forum.aspose.com`/`*.aspose.app` links, license link target resolves
   case-sensitively on disk, the diagram matches the fixed container-chain shape and column-
   balance rule, the diagram's column order matches the recorded `data/
   diagram_capability_dependencies.json` entry (no-op when none exists — edges there are now
   keyed to the *current* diagram's own node IDs, re-recorded whenever a diagram is redrawn), a
   `Starting Points` container may only appear when the product's `hybrid` archetype has been
   freshly re-confirmed *this run* (`data/diagram_archetypes.json`'s `decided_at` must match
   today), every format named in the diagram is genuinely supported (cross-checked against
   `knowledge/{family}/{platform}/merged/formats.md`), format-name casing is internally
   consistent and matches `data/format_descriptions.json` where known, no sibling product family
   is cited inside a section that's supposed to describe only this product, the `## Additional
   Examples` exhaustive table is collapsed alongside the remaining worked examples (not always
   visible), every heading (including `<summary>` text) is title case, no undisclosed BLOCKING
   command from `upstream-issues.md` is repeated as a normal install/build step, no real
   old-README link/heading/meaning was silently dropped or hidden behind an internal
   process-label like "Preserved repository details", (**TC-HARDEN-19**, MT034/Twentieth
   incident, 2026-08-12) every `products.aspose.com` Enterprise Edition link in the candidate
   matches the factpack's own real, live-verified `enterprise_link["url"]` exactly — never a
   guessed slug (this closes a confirmed-live regression: a clean-room regeneration produced a
   real, curl-confirmed 404 that every prior gate, including the anchor-text/context check
   below, passed cleanly), (**TC-HARDEN-21**, MT034, 2026-08-12) no class name appears more than
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
   unconfirmed homepage URL, and (**MT030**, Fifteenth incident)
   every real old-README content unit has a complete, well-formed disposition record whose
   cited evidence actually resolves against real product-repo/registry/docs data and whose
   claimed section-merge is traceable to real text in the candidate (never two disposition
   entries merging the identical excerpt into the identical section). **Heuristic checks** (surfaced for
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
   contains a real request/contact phrase worth re-examining. `check_diagram_
   suspicious_direct_product_edge`/`check_diagram_capability_unreachable_from_product` are
   retired — both were tripwires for a per-node-edge defect class the simplified model can no
   longer produce.
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
   currently just `README.md`) + push + `gh pr create --draft`. `--dry-run` rehearses every step
   up to (not including) the live network write, then returns the run to `APPROVED` — it never
   reaches `PUSHED` without a real push. Draft PRs always — a human explicitly marks "Ready for
   review"; this skill never merges.

9. **`verify`** — post-push, safely re-runnable any time: confirms the PR still exists and its
   head matches the approved candidate.

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
