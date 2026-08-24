<!-- CONTRACT: registered-cli-wrapper
     purpose: operate one run-bound post-launch product refresh state machine
     preconditions: product launched; explicit session identity; knowledge and clone reachable
     postcondition: run is blocked, ready-to-commit, committed-and-bound, or abandoned
     idempotent: yes — immutable receipts, OCC hashes, and state checkpoints
     verified: 2026-07-26
-->

> Cross-skill references like `/knowledge-bootstrap` refer to sibling skills in this directory.

# S-84: Refresh Product

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform}`

## Official execution contract

Use only the registered control plane:

```bash
.venv/Scripts/python scripts/pipeline/commands/ops/refresh_run.py start FAMILY PLATFORM \
  --mode upstream|remediation|combined [--scope-manifest PATH] [--session-id ID]
.venv/Scripts/python scripts/pipeline/commands/ops/refresh_run.py run --run-id ID [--session-id ID]
.venv/Scripts/python scripts/pipeline/commands/ops/refresh_run.py resume --run-id ID [--session-id ID]
.venv/Scripts/python scripts/pipeline/commands/ops/refresh_run.py status --run-id ID
.venv/Scripts/python scripts/pipeline/commands/ops/refresh_run.py verify --run-id ID [--session-id ID]
.venv/Scripts/python scripts/pipeline/commands/ops/refresh_run.py recover --run-id ID \
  --reason TEXT [--session-id ID]
.venv/Scripts/python scripts/pipeline/commands/ops/refresh_run.py bind-commit --run-id ID \
  --commit SHA [--session-id ID]
.venv/Scripts/python scripts/pipeline/commands/ops/refresh_run.py abandon --run-id ID \
  --reason TEXT [--session-id ID]
```

Do not invoke the stages below as a production orchestration sequence. The CLI pins
the session owner, Git base, clone/model SHAs, scope, receipts, decisions, state
transitions, and validation results under
`reports/refresh_runs/{family}/{platform}/{run_id}/`. Mutating S-62 and S-105 calls
without a run ID fail. Commit readiness requires `post_refresh_verify --run-id`;
`--base` is forensic-only and never infers the newest local manifest.
The validation state also requires scoped S-23 content audit and link validation,
the refresh oracle, triage confirmation, and SEO stability to return PASS.
Writers stage the final candidate and emit a validated receipt plus page decision
before mutating the real content path. Scope identity and its manifest digest are
rechecked inside each writer. A resumed run accepts only the pinned input hash or
the receipt-bound output hash, so interruption cannot create an unowned write.
Required page validators are exactly `receipt`, `forbidden_claims`, and
`regrounding`; all three must be `PASS`.

Use `--mode remediation --scope-manifest PATH` to revalidate an explicit historical
candidate set against current truth without fabricating an upstream delta. Missing
baseline, model/clone mismatch, mixed-run evidence, incomplete scope reconciliation,
in-scope HEAD movement, or an altered scoped file blocks the run.

**Reference pages always regenerate from the full, current knowledge model — not just
this cycle's delta** (deep-reassessment pass, 2026-08-24, closes G17). `knowledge_delta.json`
is cycle-scoped: it only diffs the immediately preceding `merged/` snapshot against the
current one, so a real knowledge advance whose content generation is skipped for one
cycle (a different lane's own workflow, an interrupted run, human error) becomes
permanently invisible to every later cycle's own narrower delta — confirmed live for
pdf/java, where a real ~121-class Structured Document Model addition was correctly
scouted but never got a single reference page. For `upstream`/`combined` mode,
`prepare_run()` pins the *entire*, delta-independent reference-page candidate set
(`batch_reference.py`'s own `--rebuild-all` dry-run — both missing and existing-eligible
classes) into the run's scope, and `apply_run()` always invokes `batch_reference.py`
with `--rebuild-all --confirm-rebuild` for the reference surface, for every mode — never
the old delta-scoped `--update`. This is safe: the reference surface is entirely
mechanically generated (no hand-authored-content risk), and the existing meaningful-change
guard plus `auto_updatable:false`/manually-curated protections mean pinning the full
candidate set into scope does not mean every existing page gets rewritten — only
genuinely different ones do, at apply time. `remediation` mode's explicit,
operator-pinned scope is never broadened by this union.

**Before/after content-coverage verification is automatic, not a separate step.**
`prepare_run()` captures a coverage baseline (`manifest["content_coverage_before"]` —
which classes in `api_surface.json` currently have no reference page) before this run's
own `apply_run()` writes anything. `verify_run()` re-scans after applying
(`manifest["content_coverage_summary"]`) and diffs the two into
`manifest["content_coverage_comparison"]`: `newly_covered` (previously missing, now has a
page — confirms new API references were actually generated), `newly_missing` (had a page
before this run, has none now — a real regression signal), and `still_missing` (missing
both before and after — a pre-existing gap this run's generation did not close). This is
advisory, recorded in the manifest for every run, not a new blocking gate (per this
mission's own non-goal of not changing repo-wide validator strictness) —
`post_refresh_verify.py`'s existing Check 3b (incorrectly-retired pages) remains the
blocking defense for the closely related "still-valid class marked draft:true" case.

Use `recover` only for an uncommitted failed or rejected run. It restores each
run-owned path from the pinned base only when the current bytes still match the
validated receipt output (or were already restored by an interrupted recovery),
then marks the run `ABANDONED`. It refuses paths absent from the base rather than
deleting them. Post-commit rollback remains `git revert`, never recovery.

One run owns one family/platform and one content commit. Keep pipeline-code changes
separate. Include `Refresh-Run`, `Refresh-Base`, and `Refresh-Source-SHA` trailers in
the content commit exactly once each in the final Git trailer block, then bind it
explicitly; matching subject/body prose is not accepted. Binding compares
checkout-filtered committed bytes to each receipt's raw `new_hash` in addition to
normalized body/frontmatter hashes. Never push as part of S-84.

<details>
<summary>Legacy pre-orchestrator sequence (forensic context only; do not execute)</summary>

## Purpose

Re-generate content for a single product after a knowledge update. Detects upstream
changes, refreshes the knowledge model, plans what content needs to change, updates stale
pages, generates new pages, retires obsolete pages, validates quality, and commits the
result.

**Translation is not part of this chain** — it was decoupled in AREA9-TRANS-001 and runs
via a separate cadence. After refresh, run `translation_coverage.py` to detect locale
staleness and trigger translation independently.

This skill is the entry point for the maintenance chain (AGENTS.md §6; full detail: [docs/workflows/skill-chains.md](../docs/workflows/skill-chains.md)). Running it ensures
the full cycle executes in the correct order with progress tracking and a verification gate
before any commit.

## Pre-conditions

- Knowledge model must be accessible: `knowledge/{family}/{platform}/merged/model.yaml` must exist.
- Clone cache must be reachable or previously populated at `runs/.clone_cache/` (or `ASPOSE_CLONE_CACHE`).
- **S-12 (knowledge-diff) is auto-invoked as Step 1** — no separate pre-activation required.
  If S-12 reports no SHA change, the skill exits cleanly without further steps.

## Early Exit (No Change)

If Step 1 finds no SHA change (upstream repo unchanged), exit cleanly:
```
No upstream change detected for {family}/{platform}.
SHA: {sha} (unchanged)
No content update needed.
```
Do not run any subsequent steps. Exit 0.

## Steps

> **Skill context gate** — run before step 1:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py begin --skill S-84 --scope "*"
> ```


1. **Detect change** (S-12: knowledge-diff):
   - **First, capture this refresh's pre-refresh baseline (RPR-J-17/ST-034)**, before any
     knowledge or content change is made:
     ```bash
     PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/ops/refresh_run_manifest.py {family} {platform} --capture-base
     ```
     Writes the current `HEAD` sha as `base_commit_sha` into a new
     `reports/refresh_runs/{family}/{platform}/*.manifest.json`. `post_refresh_verify.py
     --verify`'s git-founded checks (7, 8, 10, 11) read this automatically — without it they
     silently default to comparing against `HEAD`, which is vacuous the moment this refresh's
     own commits land (`HEAD` then *is* the post-refresh state; confirmed against real
     pdf/net/3d/net/cells/java data, not merely theoretical — see RPR-J-10's independent
     review). This step is a best-effort capture: if it fails (not a git repo, git
     unavailable), proceed anyway — `--verify` falls back to `HEAD`, the pre-existing
     behavior, not a new failure.
   ```
   /knowledge-diff {family} {platform} {repo-path}
   ```
   - Calls `update_clone()` to fetch upstream before SHA comparison
   - If SHAs match: exit cleanly with "no upstream change" message
   - If HIGH/MEDIUM: `stale_since` auto-set; proceed to Step 2
   - Record progress: `python scripts/pipeline/commands/ops/post_refresh_verify.py {family} {platform} --step knowledge_diff`

2. **Refresh knowledge** (S-14: knowledge-update):
   ```
   /knowledge-update {family} {platform}
   ```
   - Runs full scout → enrich → promote → index pipeline
   - Writes `knowledge_delta.json` with semantic diff
   - Clears `stale_since` on success
   - `promote.py` appends the accepted baseline to the append-only ledger (S-111:
     baseline-ledger-writer) — the durable history that replaces the mutable
     `model.yaml.repo_sha` scalar (RPR-C-01/02). Step 1's baseline was resolved via
     `resolve_baseline_sha` (real orphaned-SHA walkback), not a raw scalar read (RPR-C-03).
   - Record progress: `python scripts/pipeline/commands/ops/post_refresh_verify.py {family} {platform} --step knowledge_update`

2.5. **Semantic diff** (S-104: semantic-diff):
   ```
   /semantic-diff {family} {platform}
   ```
   - Converts `knowledge_delta.json`'s string arrays into typed semantic change objects
     (API_ADDED / FEATURE_CHANGED / BEHAVIOR_CHANGED / …), each routed to an update strategy
     and tagged with a grounding source; writes `semantic_changes.json` (schema 5b).
   - This typed output is the single change-typing input consumed by body-refresh (Step 4) and
     the PIA (Step 3.5) — not a filename or version-string heuristic.
   - Record progress: `python scripts/pipeline/commands/ops/post_refresh_verify.py {family} {platform} --step semantic_diff`

3. **Delta site planning** (S-82: delta-site-plan):
   ```
   /delta-site-plan {family} {platform}
   ```
   - Runs `site_planner.py --mode update`
   - Produces `delta.pages_to_add`, `pages_to_update`, `pages_to_remove`, `pages_renamed`
   - Record progress: `python scripts/pipeline/commands/ops/post_refresh_verify.py {family} {platform} --step delta_site_plan`

3.5. **Page Impact Assessment**:
   ```bash
   .venv/Scripts/python scripts/pipeline/commands/ops/page_impact_assess.py {family} {platform}
   ```
   - Scores every English page HIGH_IMPACT / MEDIUM_IMPACT / LOW_IMPACT / NOT_AFFECTED using
     **citation-based scoring** (RPR-D-01): reads each page's own `evidence.claims`/`evidence.apis`
     frontmatter and matches it against the changed claim/API IDs. HIGH on a cited-API change,
     MEDIUM on a cited-claim change, NOT_AFFECTED ("cite-clean") when evidence is present but nothing
     cited changed. The old token-intersection heuristic is a logged fallback for evidence-less
     pages only ("fallback-no-evidence"), never primary. A page can now score NOT_AFFECTED even
     when its product's delta is non-empty (RPR-D-02).
   - Writes `reports/refresh_review/{family}/{platform}/page_impact.json`
   - **If `knowledge_delta.json` absent**: step is skipped with WARNING; chain continues
   - Record progress: `python scripts/pipeline/commands/ops/post_refresh_verify.py {family} {platform} --step page_impact_assess`

4. **Update stale existing pages** (S-105: body-refresh — PRIMARY; S-20: page-update — FALLBACK):
   ```
   /body-refresh {family} {platform}
   ```
   - **body-refresh (S-105) is the primary, deterministic-first body-editing path.** It consumes the
     typed `semantic_changes.json` (Step 2.5), selects a surgical strategy per change (5 of 6
     strategies never touch an LLM), and applies the smallest sufficient edit — grounded in cited
     evidence, with generation-time forbidden-claims (RPR-E-02), template-propagation/re-grounding
     (RPR-E-03), surface-policy (RPR-E-04), and LLM-circuit/`fallback_reason` (RPR-E-05) gates. It
     emits a per-page patch receipt (schema 5d) with `llm_invoked`/`fallback_reason`/`oracle_verdict`.
   - **S-20 page-update is the explicit, logged fallback** — used only when body-refresh reports
     `UNRESOLVED` for a page (`/page-update {family} {platform}`), never as the default.
   - Record progress: `python scripts/pipeline/commands/ops/post_refresh_verify.py {family} {platform} --step page_update`

5. **Delta dispatch — generate new pages**:
   For each page in `delta.pages_to_add` from the site_plan.yaml delta section:
   - `docs/` prefix → `/new-docs-page {family} {platform} {slug}`
   - `blog/` prefix → `/new-blog-post {family} {platform} {slug}`
   - `kb/faq` → `/new-kb-faq {family} {platform}`
   - `kb/howto` → `/new-kb-howto {family} {platform} {slug}`
   - `reference/` → `python scripts/pipeline/commands/content/batch_reference.py {family} {platform} --update`
   - Record progress: `python scripts/pipeline/commands/ops/post_refresh_verify.py {family} {platform} --step delta_dispatch`

6. **Retire obsolete pages** (S-83: page-retire):
   ```
   /page-retire --from-plan reports/plans/{family}/{platform}/site_plan.yaml
   ```
   - Always run `--dry-run` first; confirm before executing
   - Retires pages from `delta.pages_to_remove` (dual-signal rule applies)
   - Record progress: `python scripts/pipeline/commands/ops/post_refresh_verify.py {family} {platform} --step page_retire`

7. **Update reference pages for modified APIs** (S-62: batch-reference --update):
   ```
   .venv/Scripts/python scripts/pipeline/commands/content/batch_reference.py {family} {platform} --update
   ```
   - Regenerates only reference pages for classes in `knowledge_delta.json modified_apis`
   - **Two-step regeneration rule** (MANDATORY when `removed_apis > 0`):
     If `knowledge_delta.json` has `removed_apis` count > 0, run a second pass:
     ```
     .venv/Scripts/python scripts/pipeline/commands/content/batch_reference.py {family} {platform} --rebuild-all
     ```
     Without this second pass, reference pages for classes NOT in `modified_apis` may retain
     phantom methods that were removed as side-effects of the deleted classes. Proven by
     `pdf/java` sprint (2026-06-12): `Rectangle.md` had phantom `fromCOSArray`/`toCOSArray`
     that survived `--update`; only resolved by `--rebuild-all`.
   - Record progress: `python scripts/pipeline/commands/ops/post_refresh_verify.py {family} {platform} --step reference_update`
   - **Write execution reconciliation** (after all content steps complete):
     ```bash
     .venv/Scripts/python scripts/pipeline/commands/ops/post_refresh_verify.py {family} {platform} --reconcile
     ```

8. **Family page sync** (S-48: family-sync):
   ```
   /family-sync {family}
   ```
   Updates `products.aspose.org` family landing page with any version/status changes.
   - Record progress: `python scripts/pipeline/commands/ops/post_refresh_verify.py {family} {platform} --step family_sync`

9. **Content check** on all changed files (S-23: content-check):
   ```
   /content-check {family} {platform}
   ```
   Run on all pages updated, generated, or modified in Steps 4-7.

9.5. **Re-grade changed pages** (TC-P3-03: post-refresh re-grading):
    ```bash
    .venv/Scripts/python -m content_eval evaluate {family} {platform} --write-grade
    ```
    Recalculates grades against the updated knowledge model and persists them to frontmatter.
    Compare before/after grades: any page regressing to D or F should be flagged for healing
    before commit. Pass `--skip-regrade` to bypass for fast refresh runs.

10. **Link validation** (S-65: link-validate):
    ```
    /link-validate {family} {platform}
    ```
    Verify no broken cross-subdomain links were introduced.

11. **Record step completions**: After each step above, call:
    ```bash
    .venv/Scripts/python scripts/pipeline/commands/ops/post_refresh_verify.py {family} {platform} --step {step_name}
    ```
    Progress is tracked at `reports/refresh_state/{family}/{platform}/progress.json` (local-only, not committed).

11.6. **Body-update planner routing**:
    After Step 11, classify each updated page by what type of change was made:
    - `BODY_UPDATED` — prose body content was modified
    - `EVIDENCE_ONLY` — only `evidence.model_sha` or claim IDs were updated (no body change)
    - `NOT_AFFECTED` — page was scanned but required no update
    Route pages with `EVIDENCE_ONLY` status to `/grade-remediate` for grade recalculation
    rather than full re-evaluation. Do not commit `EVIDENCE_ONLY` changes without
    verifying the grade is still accurate for the current content.

    **SOURCE_EVIDENCE_UNAVAILABLE** — if the clone cache is absent or the source
    baseline for a page cannot be fetched, the planner must fail-closed: do not
    update the page and emit `SOURCE_EVIDENCE_UNAVAILABLE` in the decision record.
    Proceeding without source evidence risks silent quality regression.

11.7. **Oracle + frontmatter-body consistency** (S-106: refresh-oracle, S-108:
    frontmatter-body-consistency — BLOCKING):
    ```
    /refresh-oracle {family} {platform}
    /frontmatter-body-consistency {family} {platform}
    ```
    - **refresh-oracle (S-106)** validates every `BODY_UPDATED` page's refreshed prose against
      source truth (claim/API-symbol validation) — required PASS for each such page, not a
      pilot-only side effect. Queues any missed cross-page propagation.
    - **frontmatter-body-consistency (S-108)** checks paired-claim consistency between frontmatter
      evidence and body prose, merged with Amendment-009's `GENERATED_ONLY_BODY_CHANGE_INSUFFICIENT`
      verdict into one enforcement path.
    - Both are BLOCKING: an oracle FAIL or a consistency violation halts the chain before Step 12.

11.8. **Regression classification** (S-114: regression-classification — on any grade delta):
    If Step 9.5's re-grade shows any page's grade moved, classify each delta JUSTIFIED/UNJUSTIFIED
    with a cited `grade_reason`, writing the COMPLETE list to
    `reports/regression_classification/`. UNJUSTIFIED items must be remediated (re-run Step 4) or
    explicitly accepted before commit — a grade regression may never pass silently.

12. **Verification gate** (post_refresh_verify.py --verify --assert-no-skipped):
    ```bash
    # RPR-F-02: --assert-no-skipped (exit 2) is now part of the documented gate — it
    # was a real hard-blocking flag that the chain previously never invoked.
    .venv/Scripts/python scripts/pipeline/commands/ops/post_refresh_verify.py {family} {platform} --assert-no-skipped
    .venv/Scripts/python scripts/pipeline/commands/ops/post_refresh_verify.py {family} {platform} --verify
    ```
    Runs post-refresh checklist:
    - `stale_since` is null in `merged/model.yaml`
    - No content pages cite claim IDs absent from `merged/claims.json`
    - No reference pages exist for classes absent from `merged/api_surface.json`
    - `stale_detect.py` reports 0 stale pages (end-state proxy for page freshness)
    - **Check 7/8 (RPR-F-01, now BLOCKING)**: a refresh that removed >50 claims but updated
      0 pages, or shows real body diffs with no tracked `pages_updated`, or has stale prose
      referencing removed APIs, now FAILS the gate (was WARN-only). `--allow-warn` demotes
      these back to WARN, opt-out only, after manual confirmation.
    - **Check 9 (RPR-F-03)**: S-92 triage-confirm Layer 2 body-prose scan (blocks on stale prose).
    - **Check 10 (RPR-F-04)**: frontmatter-only grade regression — a page whose body is
      byte-identical but whose evidence bumped AND grade regressed (the PDF-NET-REFRESH-001
      v26.7.0 defect) now FAILS the gate.
    - **Check 11 (RPR-F-05)**: SEO stability — any undeclared title/H1/slug/canonical change on a
      refreshed page FAILS the gate unless declared in the run manifest's `intentional_renames`.

    **Tri-state verdicts (RPR-J-00, broadened by RPR-J-06)**: every check in `--verify`
    (Checks 1, 4, 5, 7, 8 Case B, 9, 10, 11) returns one of three states, not a binary
    PASS/FAIL — a tool crashing, timing out, or an artifact failing to parse proves the
    check couldn't run, never that the content is defective, so it routes to UNKNOWN, not
    a fabricated FAIL. `--verify`'s exit codes: `0` = PASS, `1` = real FAIL (a
    content/tracking defect), `3` = INCONCLUSIVE (one or more checks returned UNKNOWN —
    commit is still blocked, but this is NOT a content defect and reports no fabricated
    count).

    **Tier-aware claim gating (RPR-J-07)**: Check 2 and `evidence_verifier.py` no longer
    treat every unknown `evidence.claims` citation identically. A missing `CLM-*`
    (deterministic scout/api_surface/formats) claim_id is a real, blocking signal — the
    underlying API/format genuinely changed. A missing `ERC-*` (LLM-enriched) claim_id is
    expected knowledge-rebuild churn (capability-mode enriched claims are still
    content-hash-keyed even after RPR-J-16) and is reported, not blocked. See
    `lib/knowledge_tiers.py`.

    **Git-founded, not bookkeeping (RPR-J-05)**: Checks 7 and 8 Case A no longer read
    `progress.json` / `execution_reconciliation.json` for their verdict — both are ephemeral,
    gitignored, and were proven to disagree with each other on a genuinely healthy refresh
    (comparing two independently-stale files manufactured false blocks). They now diff the
    working tree against a git ref using the same primitive `audit_content_hash.py` already
    uses for Checks 10/11 (`git show {ref}:{path}` vs. a normalized body hash). Check 7 asks
    "did ANY discovered page's body really change" (aggregate); Check 8 Case A cross-checks
    each page `page_decisions.json` records as `BODY_UPDATED` against that same git diff — a
    decision claiming a body update whose body is git-identical to the base ref is the literal
    PDF-NET-REFRESH-001 tracking-gap shape, caught directly. UNKNOWN when git-founded
    verification is unavailable (no comparable pages, or not a git repo) — never a fabricated
    count from an absent/old-schema bookkeeping file.

    **`--base <ref>` (RPR-J-17)**: the ref Checks 7/8/10/11 diff against. Default: the newest
    `reports/refresh_runs/{family}/{platform}/*.manifest.json`'s `base_commit_sha` if one
    exists, else `HEAD`. **`HEAD` is only meaningful for an in-progress, not-yet-committed
    refresh** — once a refresh has already landed, `HEAD` *is* the post-refresh state, so a
    plain `HEAD` diff is vacuous (confirmed against real pdf/net data: every `BODY_UPDATED`
    page showed 0 diff from `HEAD` purely because the refresh had already been committed, not
    because nothing happened). Pass `--base <pre-refresh-sha>` explicitly to verify an
    already-committed historical refresh against its true starting point.

    Note: `audit.py` is NOT re-run per-page during `--verify`; it is already enforced
    by S-20 and S-23 during the chain. `stale_detect.py` is the correct end-state proxy:
    pages with audit failures leave their `model_sha` stale (Check 4) or produce orphaned
    claim citations (Check 2), both of which are caught above.

    **If verification fails**: do NOT proceed to Step 13. Fix the reported issues and re-run
    the failing sub-steps, then re-run `--verify`. Commit only after verification passes.

12.5. **Hugo build check** (VVR-TC09-001):
    ```bash
    bash scripts/ci/hooks/check_hugo_build.sh
    ```
    Builds all 5 sites (`products.aspose.org docs.aspose.org kb.aspose.org reference.aspose.org blog.aspose.org`).
    - If any site FAIL: abort; do not proceed to Step 13.5 or Step 13 (commit).
    - Invoke S-67 (diagnose-skill-failure) if build fails before retrying.
    - A passing build does NOT prove rendering completeness (Hugo silently skips missing frontmatter
      sections via `{{ with }}` guards); use the verification gate (Step 12) for semantic checks.
    - Record progress: `python scripts/pipeline/commands/ops/post_refresh_verify.py {family} {platform} --step hugo_build`

13.5. **Coverage report**:
    ```bash
    .venv/Scripts/python scripts/pipeline/commands/ops/refresh_review.py {family} {platform} --report
    ```
    Writes `reports/refresh_review/{family}/{platform}/coverage_report.md` with per-subdomain
    counts (total, body_updated, evidence_only, not_affected, retired).
    - **Generated reference pages are never counted** toward coverage percentage —
      only human-authored and LLM-authored non-reference pages contribute to the coverage
      numerator. Auto-generated reference pages have their own quality gate (audit.py).
    - If coverage < 100%: emits WARNING and includes gap in commit message; does NOT abort commit
    - Record progress: `python scripts/pipeline/commands/ops/post_refresh_verify.py {family} {platform} --step coverage_report`


13a. **Two-layer triage gate** (S-92: triage-confirm):

    Before committing, confirm that all updated and generated pages pass the
    Layer 2 body-prose scanner. This catches residual staleness signals not
    caught by the SHA-based Layer 1 check.

    For each page in the updated/generated set, run:
    ```python
    from triage_confirm import triage_confirm
    result = triage_confirm(page_path, knowledge)
    # knowledge must include: api_surface, claims, delta
    ```
    Or invoke the skill:
    ```
    /triage-confirm {family} {platform}
    ```
    - If `result['stale']` is True for any page: log the reasons and re-run
      the relevant content update step before continuing.
    - If all pages return `stale: False`: proceed to Step 13.
    - **Deterministic enforcement (S-112: triage-verdict-gate)**: the verdict is now a real
      exit-coded gate, not advisory prose. Run
      `.venv/Scripts/python scripts/pipeline/lib/triage_confirm.py {family} {platform}` — exit 1
      (stale prose) is a hard BLOCK on commit; a CONFIRMED verdict (or explicit logged human
      override) is required before Step 13. This is also enforced as Check 9 in `--verify`.
    - Record step: `.venv/Scripts/python scripts/pipeline/commands/ops/post_refresh_verify.py {family} {platform} --step triage_gate`

13. **Commit** (S-76: commit):
    ```
    /commit
    ```
    Include in the commit message:
    - Knowledge delta summary (new/removed claims and APIs)
    - Step list from `progress.json`
    - `Skills invoked: [refresh-product, S-12, S-14, S-104, S-82, S-105, S-83, S-62, S-48, S-106, S-108, S-92/S-112, S-76]`
    - **Commit precondition**: the S-112 triage verdict must be CONFIRMED (or explicitly overridden)
      and every Step 12 check PASS — the pre-commit hook (Step 22, HARDEN-A8, check_stale_refresh_gate.py) BLOCKS the S-76 commit if triage_verdict.yaml records unresolved stale pages; there is no separate "manifest schema 5e" validation inside S-76 itself (that phrasing was aspirational, corrected 2026-07-22).

14. **Locale handoff** (S-107: locale-refresh-handoff — post-commit):
    ```
    /locale-refresh-handoff {family} {platform}
    ```
    After the English commit lands, queue the locale equivalents of every `BODY_UPDATED` page for
    re-translation (routes <3 changed sentences to S-75 locale-patch, ≥3 to the batch translator).
    This runs post-commit so locale work never blocks the English refresh.

> **Skill context close** — run after the last step:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py end --skill S-84 --status completed
> ```

## Progress Tracking

Progress is stored at `reports/refresh_state/{family}/{platform}/progress.json` (local-only, gitignored).
Check current progress at any time:
```bash
.venv/Scripts/python scripts/pipeline/commands/ops/post_refresh_verify.py {family} {platform} --status
```

If the refresh cycle is interrupted, re-run this skill — completed steps are idempotent and
will be skipped or produce no-ops on re-run.

## Post-conditions

- All stale content pages have been updated or retired
- All new pages required by knowledge additions have been generated
- No orphaned claim citations remain
- Verification gate (`--verify`) exited 0
- All changes committed with structured commit message

## Error handling

- Step 1 (detect): if `update_clone()` fails, log warning and compare against cached local SHA; continue
- Step 2 (knowledge-update): if scout fails, abort entire cycle; do not write partial delta
- Step 12 (verify): if fails, list specific issues; do not commit; fix and re-verify
- Any step failure: check `--status` to see which steps completed; resume from the failing step

</details>
