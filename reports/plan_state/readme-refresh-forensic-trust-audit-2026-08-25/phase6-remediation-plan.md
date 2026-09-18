# Phase 6 — Prioritized Remediation Plan (readme-refresh forensic trust audit)

## How to read this plan

Every item lists: affected products, root cause (Phase 5 cluster), owning layer, exact
files/components, proposed implementation, migration/invalidation scope, tests needed, a
real-product canary, regression protection, evidence required, completion gate, estimated
risk, dependencies, and whether existing accepted/published content remains valid or needs
re-review. **This audit mission fixes nothing.** Every item here is a candidate for a
separate, future remediation mission — see the canary + rollout plan and the RC-* JSON
file for how that mission should sequence its work.

## Tier 1 — Immediate publication corrections

These are defects **already live** on a real, published GitHub README today (verified via
`gh api`/direct diff in the underlying phase3 reviews), or, in tex/python's case, the
identical mechanism on a **not-yet-published** sibling — flagged with that distinction made
explicit rather than glossed over.

### 1. words/net — fabricated/broken flagship example (`Shapes[0].Chart`)
- **Affected products**: words/net (BLOCKER, live).
- **Root cause**: Cluster C (citation-exists ≠ claim-true) + Cluster G (no C# example
  compilation exists at any stage).
- **Owning layer**: content correction now; systemic fix owned by readme-refresh checks +
  verify-examples runner expansion (Tier 2 items 7, 13).
- **Files**: the product's own published `README.md` (external repo,
  `aspose-words-foss/Aspose.Words-FOSS-for-Python`... confirm exact org/repo name via
  `data/products.json` before touching); local candidate mirror
  `reports/repo-presenter-regen-full/words/net/readme.md`.
- **Proposed fix**: replace the example with a real, compiling alternative (e.g. iterate
  `Body.ChildNodes` for a `Shape` with `HasChart`, or drop the chart-access line entirely
  if no public equivalent exists) — a human/agent content edit, not a template change.
- **Migration/invalidation scope**: this one file, this one code block. No other product
  touched.
- **Tests needed**: `code-smoke` (S-63) syntax/type-check on the corrected block; ideally
  a real `dotnet build` against the actual package once Tier 2 item 13 exists.
- **Canary**: N/A — this is a direct, single-product fix, not a systemic-fix rollout.
- **Regression protection**: re-run `ingest-candidate`/`recheck` before any future push;
  add a `code-smoke` gate specifically covering this block if not already covered.
- **Evidence required**: a real compile/run transcript against the current source tree
  before republishing (see Tier 2 item 13's canary sequence for the general capability).
- **Completion gate**: republished README's corrected block independently re-verified by a
  second reviewer against real source, not just re-authored.
- **Estimated risk**: Low (isolated single-block fix) but **do not push without human
  review** — this repo's `approve` step is human-gated by convention only, not
  code-enforced (Phase 2 §9).
- **Dependencies**: none blocking; benefits from Tier 2 item 13 existing first.
- **Existing content disposition**: the rest of words/net's published README is not shown
  to be affected — no broader re-review required.

### 2. font/python — entire refresh publication silently wiped (full regression)
- **Affected products**: font/python (BLOCKER, systemic architecture risk).
- **Root cause**: Cluster E, sub-tier E2 (publication-target authority — GitHub mirror of a
  GitLab-canonical source) + E1 (ledger has zero record of the real merge that got wiped).
- **Owning layer**: orchestration/publication-target-verification (new capability, does not
  exist today) + ledger reconciliation (Tier 2 item 9).
- **Files**: `data/readme_published_state.json`, `reports/repo_presenter_actions.jsonl`
  (both need a font/python row backfilled regardless of what else happens); the external
  repo's own `.gitlab-ci.yml`/`CODEOWNERS` (read-only reference, confirms mirror
  architecture, do not touch).
- **Proposed fix**: **before any re-push**, determine whether GitHub is a *safe* publish
  target for this product at all — if the GitLab-canonical repo is what actually ships,
  either (a) publish there instead, (b) coordinate with whatever owns the mirror sync so it
  preserves README-only pipeline commits, or (c) explicitly flag font/python
  publish-unsafe in `data/products.json`/`data/registry_exclusions.json` until resolved,
  rather than re-pushing into a channel proven to discard the content within days.
- **Migration/invalidation scope**: font/python only for the immediate decision; the
  publish-safety check itself, once built, applies portfolio-wide (see Tier 2 item 10).
- **Tests needed**: a scripted post-push drift check (Tier 2 item 10) exercised specifically
  against font/python's repo history shape (a zero-parent history replacement) as its
  first real test case.
- **Canary**: font/python itself is the canary for Tier 2 item 10, since it is the only
  confirmed live instance of this mechanism.
- **Regression protection**: do not consider this "fixed" by a second push alone — verify
  the target repo's mirror-sync cadence and confirm a subsequent sync does not repeat the
  wipe before declaring success.
- **Evidence required**: `gh api repos/{org}/{repo}/commits` history showing a real,
  non-force-pushed lineage from the corrected content forward through at least one
  mirror-sync cycle.
- **Completion gate**: either the corrected README survives a full mirror-sync cycle, or
  the product is explicitly marked publish-unsafe with a documented reason.
- **Estimated risk**: **High** — re-pushing without resolving the mirror-authority question
  reproduces the exact same silent loss again.
- **Dependencies**: Tier 2 item 10 (publication-target-authority verification) should exist
  before this is retried, not after.
- **Existing content disposition**: the live README today is the **pre-refresh original**
  — there is currently zero pipeline-authored benefit live for this product. Nothing to
  "keep" from the wiped commit; it must be regenerated/re-verified fresh once the target
  question is resolved, not blindly re-pushed as-is.

### 3. cells/java — carried-forward 44.3%-wrong "single module" narrative
- **Affected products**: cells/java (BLOCKER, confirmed live — `phase3-reviews/cells-java.md:88`:
  "this exact defect is already present, identically, in the currently-published README...
  predates this regeneration cycle").
- **Root cause**: Cluster C (evidence-resolution proves existence, not claim-truth).
- **Owning layer**: content correction now; systemic fix is Tier 2 item 7.
- **Files**: published `README.md` on the external cells/java repo; local candidate
  `reports/repo-presenter-regen-full/cells/java/readme.md`.
- **Proposed fix**: correct the framing sentence to reflect the true count (81/183, 44.3%,
  are not organized into the single `org.aspose.cells_foss` module as claimed) — a targeted
  prose edit.
- **Migration/invalidation scope**: this sentence and any adjacent claims that assume the
  false single-module framing.
- **Tests needed**: re-run `check_content_unit_evidence_resolves` plus a manual recount
  against `knowledge/cells/java/merged/api_surface.json` before republishing.
- **Canary**: N/A — direct fix. Also serves retroactively as the canary proving Tier 2 item
  7's semantic-verification check would have caught this, once built.
- **Regression protection**: re-verify the corrected count against source at push time, not
  just at authoring time.
- **Evidence required**: a fresh module-membership count against current
  `api_surface.json`, cited inline or in the evidence ledger.
- **Completion gate**: independent second-reviewer recount matches the corrected claim.
- **Estimated risk**: Low.
- **Dependencies**: none blocking.
- **Existing content disposition**: note separately (not a Tier-1 blocker, but log it) —
  the candidate's `26.7.0` version claim is *ahead* of the last live-confirmed Maven
  Central publish (`26.5.0`, confirmed 2026-07-24); do not treat the candidate's version
  bump as "safe to also push live" without Tier 2 item 6 (live-registry re-verification)
  or a fresh manual Maven Central check first.

### 4. html/python — `IDSelector` missing from published API Reference table
- **Affected products**: html/python (MAJOR, confirmed live per `phase3-reviews/html-python.md:126-127,176`).
- **Root cause**: Cluster D-i (shared-omission ground truth) — also affects the
  reference.aspose.org index this table likely mirrors.
- **Owning layer**: content correction now (README table) + reference.aspose.org page
  (check whether it shares the same omission); systemic fix is Tier 2 item 8.
- **Files**: published `README.md`; possibly `content/reference.aspose.org/en/html/python/_index.md`
  or its generated API pages — **verify independently before editing**, do not assume.
- **Proposed fix**: add the missing `IDSelector` row to the API Reference table (and
  reference.aspose.org's index, if it independently omits it too), correcting the
  self-reported "243 public types" count to 244 if that number appears elsewhere.
- **Migration/invalidation scope**: this table only, both surfaces if both are affected.
- **Tests needed**: re-run `check_api_reference_table_completeness` after the edit; a
  fresh set-diff of `api_surface.json` class names against the rendered table (the exact
  method the phase3 review used) to confirm zero remaining gaps.
- **Canary**: N/A — direct fix.
- **Regression protection**: same set-diff re-run at next refresh cycle.
- **Evidence required**: the set-diff transcript, before and after.
- **Completion gate**: zero-length set-diff in both directions.
- **Estimated risk**: Low.
- **Dependencies**: none blocking.
- **Existing content disposition**: rest of the table not shown to be affected.

### 5. page/python — Enterprise Edition link/anchor mismatch (live) + 2 other live diffs
- **Affected products**: page/python (published; diff vs. live-published README shows
  exactly 2 content hunks + the EE link, per `phase3-reviews/page-python.md:14,42,56,77`).
- **Root cause**: Cluster E, sub-tier E3 (correctly-detected drift, no requeue mechanism).
- **Owning layer**: content correction now (this is a monetization/cross-sell link — wrong
  target has direct revenue relevance, not just a content nit); systemic fix is Tier 2
  item 11.
- **Files**: published `README.md`; `data/aspose_com_targets.json` (read to find the
  correct current target, do not edit blindly).
- **Proposed fix**: point the EE link/anchor at the correct verified target
  (`.../page/python-net/` per the review's own citation) matching the real
  `target_mismatch`/anchor-relationship the hard gate already correctly computes; also
  correct the At-a-Glance diagram `c3` node text and the Scope-and-Limitations
  circular-import bullet (the other 2 diffed hunks).
- **Migration/invalidation scope**: this product only for the immediate fix.
- **Tests needed**: re-run `ingest-candidate`/`recheck` — `check_enterprise_edition_link_resolves`
  and `check_enterprise_edition_anchor_matches_relationship` should both go clean.
- **Canary**: N/A — direct fix; also doubles as proof-of-life for Tier 2 item 11 once that
  requeue mechanism exists (page/python + tex/python should both go clean automatically on
  the next override change once built).
- **Regression protection**: none needed beyond the standard hard-gate re-run.
- **Evidence required**: `audit-portfolio --family page --platform python` reporting
  `clean: true` on both checks post-fix.
- **Completion gate**: the above.
- **Estimated risk**: Low.
- **Dependencies**: none blocking for the immediate fix; Tier 2 item 11 prevents recurrence.
- **Existing content disposition**: rest of page/python's published README unaffected.

### tex/python — same EE-link mechanism, **not yet published** (companion item, not Tier-1-urgent)
Confirmed via `data/readme_published_state.json` (no `tex` entry) and
`reports/repo_presenter_actions.jsonl` (no tex/python row) —
`phase3-reviews/tex-python.md:10`. This is the **same root cause and same fix** as item 5
above, but it lives only in the not-yet-approved candidate
(`reports/repo-presenter-regen-full/tex/python/readme.md`). Being honest about the
distinction: this is a **block-approval** item, not an "already misleading a real user"
item — do not approve/push tex/python until the same link/anchor correction is applied.
Tracked as its own RC card (`RC-ee-link-batch-fix`) alongside item 5 since one fix session
naturally covers both.

### 6. pdf/net — stale version (26.7.0 vs live 26.8.0), largest break in the portfolio (173 findings)
- **Affected products**: pdf/net.
- **Root cause**: Cluster B (rows 1, 4, 5 — install-command staleness, clone-cache
  staleness, missing new-content absorption, all compounding on one product).
- **Owning layer**: **verify push status first** — phase1/phase3 evidence does not
  unambiguously establish whether pdf/net's *candidate* (still sitting DIRTY in
  `reports/repo-presenter-regen-full/pdf/net/`) has ever actually been pushed live by this
  pipeline, or whether "current live upstream README" in the review refers to the target
  repo's own pre-existing content that this candidate is trying to replace. `pdf/net` is
  **not** named in row 20's list of 17 confirmed untracked-but-real pushes, and is **not**
  marked `skipped_published` in the Phase 1 baseline table (unlike words/net, note/python,
  email/cpp, email/net, cells/rust) — the honest read is that this is most likely a
  not-yet-approved dirty candidate, not a live-production regression, but this must be
  confirmed with a live `gh api repos/.../commits` check against
  `data/readme_published_state.json` before deciding whether this is a "republish now" or
  a "block-approval, do not push" action.
- **Files**: `reports/repo-presenter-regen-full/pdf/net/{readme.md,*-dispositions.json,upstream-issues.md}`.
- **Proposed fix**: regenerate the candidate against current knowledge
  (`knowledge/pdf/net/merged/model.yaml`, `repo_sha: 663783d…`, v26.8.0) rather than
  patching the stale v26.7.0 candidate in place — the drift is large (167
  `content_unit_excerpt_matches_extraction` findings alone) and patching piecemeal risks
  missing the same class of new-content-absorption gap Cluster B describes.
  **Do not approve/push until Tier 2 items 4 and 5 exist**, or at minimum until a manual
  fresh regeneration against v26.8.0 is confirmed clean.
- **Migration/invalidation scope**: this product's candidate only, for the immediate
  action; Tier 2 items 4/5/6 are the systemic fix.
- **Tests needed**: full `ingest-candidate` re-run against the regenerated candidate;
  `audit-portfolio --family pdf --platform net` reporting materially fewer than 173
  findings.
- **Canary**: pdf/net **is** the designated canary for Tier 2's version-check hard gate
  (item 6) — see canary/rollout plan below.
- **Regression protection**: confirm the regenerated candidate's Dependency-Accuracy
  section (unaffected by the v26.7.0→v26.8.0 gap, per the review's own finding) does not
  regress.
- **Evidence required**: a fresh `diff` against `runs/.clone_cache/aspose_pdf_net/README.md`
  at its current HEAD, not the v26.7.0 snapshot.
- **Completion gate**: `audit-portfolio` clean or near-clean on the regenerated candidate,
  plus the live-push-status question above explicitly answered and recorded.
- **Estimated risk**: Medium (largest single-product finding count in the portfolio; do not
  rush a partial patch).
- **Dependencies**: benefits heavily from Tier 2 items 4, 5, 6 existing first, since this
  is the single clearest instance of all three.
- **Existing content disposition**: if pdf/net turns out to already be live, its Dependency
  Accuracy section remains valid; everything else needs re-review against v26.8.0.

## Tier 2 — Shared machinery blockers (Phase 5 clusters, systemic causes)

Each item below maps 1:1 or 1:many to a Phase 5 cluster. All are "will keep producing
defects" items — fixing Tier 1 without these means the same defect classes recur on the
next refresh cycle for any product.

1. **RC-disposition-bidirectional-coverage** (Cluster A, rows 6/18/28) — walk the
   candidate's real headings/badges/bullets and flag anything with no disposition trace,
   alongside the existing old-unit-driven pass. Owning layer: `readme_refresh_checks.py`
   (`check_content_unit_disposition_coverage` ~5892,
   `check_structural_unit_disposition_coverage` ~7276,
   `check_badge_disposition_coverage` ~8194). Canary: slides/java (portfolio-sweep
   baseline already exists: 1-13 entries vs 20-30+ real headings across 6 products).
2. **RC-disposition-text-diff-verification** (Cluster A, rows 8/9/10/15/16/27/29) — require
   a literal text/identity diff for any `merged_verbatim`/`preserved` disposition, not just
   enum-membership/field-presence; add a dedicated zero-old-badges branch. Canary: tex/python
   (row 10, from-source install command mislabeled verbatim) + email/cpp (row 27, zero-badge
   original).
3. **RC-disposition-baseline-integrity-assert** (Cluster A, row 26 + font/python's
   root-caused instance) — assert at generation time that the "original" input to
   disposition-writing is git-verified pre-refresh, not stale/already-advanced. Canary:
   font/python (the exact mechanism was root-caused there).
4. **RC-clone-cache-freshness-gate** (Cluster B, row 4) — an out-of-band, pre-`ingest_candidate`
   live-HEAD freshness gate comparing `clone_cache_root`'s HEAD against a live
   `git ls-remote`/`gh api` fetch. Canary: pdf/python (proven BLOCKER-severity instance,
   live HEAD 6 minutes ahead of this run's own `verified_at`).
5. **RC-new-upstream-content-absorption** (Cluster B, row 5) — extend `check_dropped_content`
   (~2249) to also flag new upstream content not yet absorbed, once item 4 exists. Canary:
   pdf/python (6+ new public API surfaces missing) or pdf/net (once regenerated per Tier 1
   item 6).
6. **RC-package-version-currency-hard-gate** (Cluster B, rows 1/30) — extend
   `check_installation_matches_package_registry`/`check_dependency_version_pin_freshness`
   to compare the Installation section's own cited version(s) against the product's current
   manifest/registry AND against a live-registry liveness check (both directions: stale and
   ahead-of-live). Canary: pdf/net (clearest stale instance, per the task's own framing) +
   cells/java (clearest ahead-of-live instance).
7. **RC-upstream-issues-freshness-reverify** (Cluster B, row 3 — 11/31, 35%, the single most
   consequential zero-coverage gap) — re-diff `upstream-issues.md`'s own cited SHA/claims
   against current clone-cache HEAD before trusting it as generation input; block or warn
   loudly on drift. Canary: email/python (small, isolated, off-by-one-commit case — cleanest
   first proof before tackling noisier products).
8. **RC-verification-timestamp-currency-gate** (Cluster B, row 2) — compare
   `last-verified.json`'s own timestamp/repo_sha against the knowledge bundle's freshness.
   Canary: pdf/net.
9. **RC-claim-level-semantic-evidence-verification** (Cluster C, rows 7/33) — genuine
   semantic verification (LLM-graded second pass, or at minimum deterministic
   keyword-presence/negation check) reading cited evidence alongside the exact claim text;
   extend to cross-reference accessibility modifiers for code-example member references.
   Canary: cells/java (retroactive proof against the already-known 44.3%-wrong claim) +
   words/net (retroactive proof against the Shapes[0].Chart BLOCKER).
10. **RC-knowledge-layer-runtime-dispatch-verification** (Cluster D-i, rows 11/12/13/14/31/34)
    — owned by S-34/repo-scout + knowledge-enrich, not readme-refresh's own checks: verify
    real reader/writer/dispatch wiring, not mere class/file/enum existence;
    `promote.py` must propagate a `caveat`/`functional:false` field into Yes/No rendering;
    fix the Javadoc `{@code <tag>}`→Markdown conversion to escape rather than drop angle
    brackets. Canary: 3d/java (formats.md fabrication already fully root-caused there,
    including the nonsensical "EXCEPTION" format row) for the format-verification half;
    slides/java for the Javadoc-conversion half (8 confirmed empty-tag rows, exact names
    known).
11. **RC-cpp-scout-visibility-signal** (Cluster D-ii, row 32) — populate a real
    `is_public`/`visibility` field keyed off `canonical_namespace`/file path (any
    `::Internal::`/`_internal/` segment); wire `check_api_reference_table_completeness` (or
    a new check) to exclude/flag internal-namespaced entries. Canary: pdf/cpp (worse leak
    ratio, 92/340 ≈27%, more decisive proof than slides/cpp's 29 entries) — but confirm
    against email/cpp too (zero internal-marked entries there) as a negative control before
    declaring the fix portfolio-safe for all C++ products.
12. **RC-publication-ledger-reconciliation-job** (Cluster E1, row 20 — 17/31, 55%, the #1
    priority by product count) — a periodic **live** reconciliation job diffing
    `gh api .../commits`/`.../pulls` against both `data/readme_published_state.json` and
    `reports/repo_presenter_actions.jsonl` for every registered product; the plan's
    taskcard register becomes a secondary cross-check, not the primary source of truth
    (barcode/python's out-of-band manual commit can never be "seeded" from this repo's own
    PR history at all). Canary: slides/java (clean, straightforward real PR-merge case)
    then barcode/python (the harder out-of-band-commit edge case).
13. **RC-publication-target-authority-verification** (Cluster E2, font/python) — before
    trusting any push as durable, verify the target repo's own git-history shape/mirror
    architecture (does `CODEOWNERS`/CI config reference an external canonical source?); add
    a post-push drift-detection re-check some interval after push to catch a mirror-sync
    wipe before it goes unnoticed for days. Canary: font/python (the only confirmed live
    instance; also the hardest case, since the wipe already happened).
14. **RC-registry-drift-requeue-trigger** (Cluster E3, row 25) — when
    `platform_canonical_overrides.yaml`/`aspose_com_targets.json` changes a
    `validated_via` target for an already-generated product, automatically queue that
    product for regeneration, or at minimum surface it in the next `session-start`/backlog
    sweep. Canary: page/python + tex/python (both should clear their EE-link dirty flag
    automatically on the next relevant override change once this exists).
15. **RC-candidate-self-consistency-checks** (Cluster F, rows 19/21/22) — extract
    Navigation's own linked section names and diff against every real `##` heading in both
    directions; detect embedded numeric claims in disposition rationale/candidate prose and
    cross-check against the candidate's own actual table/row counts; extend
    `check_heading_title_case` to verify word-split correctness, not just per-word
    capitalization. Canary: note/python (row 22's original, cleanest instance — a single
    omitted "Dependencies" heading).
16. **RC-example-verification-coverage-expansion** (Cluster G, row 17 +
    `AUD-P1-VERIFY-EXAMPLES-STUB`) — broaden `check_code_example_imports_match_source`
    beyond Java to every scripted language; add a lightweight "does this fenced block's
    module/package path exist in the real source tree" check regardless of fence language
    (bash, python, etc.); begin extending `verify_examples`'s real runner beyond the
    Python-only opt-in toward at least a real-compile check for statically-typed languages
    (this sub-item is the expensive part — see Tier 5 for the full multi-language
    execution version). Canary: words/python (isolated single-line `ModuleNotFoundError`
    fix, not yet published — safe first target) then words/net (retroactively proves this
    would have caught the live BLOCKER).
17. **RC-verification-marker-write-path-fix** (Cluster H, rows 35/36) — two fixes in the
    same function, `_write_candidate_verification_marker`
    (`readme_refresh_run.py:584-594`): (a) hash the file's actual on-disk bytes
    (`open(path, "rb").read()`), not a `read_text()`-normalized re-encoding; (b) stop the
    `audit_portfolio` call site (line 2951, `run_id=None`) from unconditionally clobbering a
    real run_id written by a prior `ingest_candidate`/`recheck` call — either skip writing
    `verified_by_run_id` at all on a read-only audit sweep (preserve whatever was already
    there), or split into two distinct fields (`verified_by_run_id` for real bound runs,
    `last_audited_at`/`last_audit_run` for read-only sweeps) so the two write paths stop
    fighting over one field. Canary: 3d/java (CRLF bug already root-caused there to this
    exact line) for fix (a); any product with a recent real `ingest_candidate` run
    immediately followed by an `audit-portfolio` sweep, to prove fix (b) preserves the real
    run_id across the sweep.

## Tier 3 — Required hardening (reliability/coverage, not tied to one Phase-5 cluster)

- **RC-unscoped-audit-portfolio-hang-fix** — `audit_portfolio` with no `--family`/`--platform`
  hangs indefinitely (reproduced: killed after >15 min, zero output). Needs root-causing
  (likely the same O(n×m)-or-worse matching algorithm implicated in the runtime-variance
  finding below, multiplied across all 31 products with no incremental output).
- **RC-audit-portfolio-runtime-variance-fix** — `AUD-P1-RUNTIME-VARIANCE`: >1000x spread
  (0.3s to 382.2s) correlated with original-README content volume (pdf/net alone produces
  167 individual findings under one check). Likely an O(n×m)-or-worse algorithm inside
  `content_unit_excerpt_matches_extraction` or a sibling check — profile before assuming.
- **RC-check-count-doc-drift-fix** — `AUD-P1-CHECK-COUNT-DRIFT`: registry.yaml says "21",
  skill-doc mirrors say "91", real count (verified live via `grep -c "^def check_"`) is 103.
- **RC-skill-description-placeholder-fix** — `skills/registry.json:811-818`'s S-120
  description is the literal stale placeholder "Skill description pending."
- **RC-dead-code-depmatrix-resolution** — the reviewer-facing dependency verification
  matrix function exists, is tested, is never called, and is referenced in docs as if live
  (`AUD-P1-DEAD-CODE-DEPMATRIX`) — wire it in or remove the stale documentation claim.
- **RC-acceptance-registry-exercise-or-retire** — the surgical-scope
  `declare-scope`/`accept-blocks`/`converge-verify` workflow has never been exercised on
  any real product (`AUD-P1-ACCEPTANCE-REGISTRY-UNUSED`) — either prove it works on one
  real product or stop documenting it as available.
- **RC-approve-gate-code-enforcement** — nothing in code prevents an agent from calling
  `approve` itself; the human-in-the-loop gate is a documented convention only (Phase 2 §9).
  Given this audit's own findings (Tier 1 items live in production), this is no longer a
  theoretical gap.
- **RC-republication-tripwire-hard-gate** — `readme_refresh_run.py:2303`'s
  `hard_gate: False` on the republication-debt tripwire is the direct root cause of the
  still-open `TC-REPUB-01` (3d/net's published README stale relative to a flat-topology
  diagram fix) — consider promoting to hard-gate status once Tier 2 item 12's
  reconciliation job exists (promoting it before that would likely just produce a wall of
  new hard failures across the 17/31 products in row 20).
- **RC-registry-excluded-empty-result-messaging** — a scoped `audit-portfolio` call against
  a registry-excluded product (`cells/typescript`) returns `total: 0` with no explanation;
  should return an explicit "excluded, reason: X" message instead of silent emptiness.

## Tier 4 — Product-specific corrections (valid exceptions, don't touch global templates)

- **RC-words-python-shapenode-disclosure-review** — `ShapeNode | 25 properties` names a
  class that doesn't exist (real class is `Shape`, 24 properties); already disclosed via
  `content-dispositions.json`'s own `excluded_reason` as a deliberate scoping choice to
  match an equally-wrong reference.aspose.org page. Action: fix the underlying
  reference.aspose.org page (shared with Cluster D-i's item 10 remit) rather than the
  README alone, since fixing only the README would create a new cross-page inconsistency.
- **RC-3d-typescript-ci-claim-and-example-caveat** — remove or substantiate the fabricated
  "development is verified on Node.js 18/20/22" claim (zero CI/config backing anywhere in
  the repo); add an inline caveat to the flagship worked example demonstrating the
  confirmed-broken `enableMaterials` option (note: Stage C found the pre-refresh original
  had the *same* undisclosed pattern with *less* disclosure — this is an improvement
  opportunity, not a new regression).
- **RC-slides-java-javadoc-tag-stopgap** — manually restore the 8 known-good tag names
  (`AdjustValue`, `AdjustValueCollection`, `Glow`, `InnerShadow`, `OuterShadow`,
  `PresetShadow`, `Reflection`, `SoftEdge`) into the affected table cells as an immediate,
  product-specific patch, independent of and prior to Tier 2 item 10's general
  Javadoc-conversion fix.
- **RC-pdf-java-namespace-suffix-formatting-fix** — a namespace-disambiguation suffix is
  fused into the API-table Class column as a non-identifier string; strip/reformat for this
  product's table pending the general fix (none proposed portfolio-wide since only 1
  product is confirmed hit).
- **RC-slides-net-diagram-caveat-restoration** — the At-a-Glance mermaid diagram's `s0001`
  unit dropped an "existing groups recognized" caveat; the caveat survives in adjacent
  prose (Stage C downgraded MAJOR→MINOR on this basis), so this is a low-priority polish
  item, not a blocker.

## Tier 5 — Deferred improvements (useful, non-blocking)

- **RC-full-multilanguage-example-execution** — the expensive completion of Tier 2 item 16:
  real compilation/execution runners for every target language (C#, Java, C++, Go, Rust,
  TypeScript), not just import/path-resolution checks. Large scope, high value, not a
  blocker for the Tier 1/2 items above.
- **RC-diagram-structural-unit-literal-diff** — extend structural-unit verification for
  `mermaid`-kind units to a literal text diff against the corresponding upstream diagram
  block, not just the current coarse plausibility check (row 18's specific refinement,
  beyond Tier 2 item 1's bidirectional-coverage fix).
- **RC-skill-template-bring-into-repo** — `AUD-P1-TEMPLATE-OUTSIDE-GIT`: the actual
  design-rationale source (~22,036 lines) lives outside git entirely
  (`<local-plan-cache>/...`); bring a copy or durable summary into the repo.
- **RC-stale-push-docstring-fix** — `AUD-P1-STALE-PUSH-DOCSTRING`: the code's own docstring
  claims push mechanics are unproven against a real external org; they are proven (this
  audit independently confirmed real pushes/PR-merges across 17+ products) — fix the stale
  self-description.
- **RC-mission-number-collision-cleanup** — `AUD-P1-MISSION-NUMBER-COLLISION` (housekeeping,
  no functional impact identified).

## Canary + rollout plan for a SEPARATE future remediation mission

This audit fixes nothing. Any future mission executing the Tier 2/3 items above must
follow this sequence per systemic correction — **explicitly not** a blind portfolio-wide
regeneration:

1. Reproduce the defect exactly as cited above (same file/line, same product).
2. Add a failing regression test asserting the fix's absence today (e.g. a test that feeds
   the check the true original and confirms it currently produces a false pass/negative).
3. Fix the responsible layer only — `readme_refresh_checks.py`,
   `readme_refresh_run.py`, `dependency_extract.py`, or the S-34/knowledge-enrich
   extraction layer, as identified per item above. Never patch a symptom in a downstream
   consumer when Phase 5 traced the cause upstream.
4. Regenerate **one** canary product in scratch (`reports/repo-presenter-regen-full/{f}/{p}/`
   is the canonical tree — do not overwrite it in place; use a scratch copy until proven).
5. Full manual compare of the regenerated candidate against both the pre-fix candidate and
   the true original — every section, not a sample.
6. Run the full validator battery (`ingest-candidate`) plus any executable examples now
   reachable for that product's language.
7. Run a second, completely unchanged generation pass (same inputs, same fix, no manual
   intervention).
8. **Require byte-identical output** between runs 4 and 7 — any difference means the fix
   introduced nondeterminism and is not ready.
9. Confirm every unrelated section of the canary's README is byte-identical to the pre-fix
   candidate — the fix must be surgical, not a full-document regeneration side effect.
10. Only then expand to the other affected products named in that item's "Affected
    products" list above — one at a time, each re-run through steps 4-9, never a batch
    regeneration across the whole 31-product portfolio in one pass.

Canary selections by systemic fix (repeated from Tier 2 for a single reference table):

| Systemic fix | Primary canary | Why |
|---|---|---|
| Package-version currency hard gate | pdf/net | Clearest, largest instance; task's own example |
| Upstream-issues.md freshness re-verify | email/python | Smallest, cleanest, single off-by-one-commit case |
| Clone-cache freshness gate | pdf/python | Proven BLOCKER-severity, precise 6-minute-stale evidence |
| Disposition bidirectional coverage | slides/java | Portfolio-sweep baseline already exists (1-13 vs 20-30+) |
| Disposition text-diff verification | tex/python | Single, well-isolated `merged_verbatim` mislabel |
| Semantic evidence verification | cells/java, words/net | Both already-known BLOCKER live defects — retroactive proof |
| C++ scout visibility signal | pdf/cpp (positive), email/cpp (negative control) | Worst leak ratio + a confirmed-clean control |
| Knowledge-layer runtime-dispatch verification | 3d/java | Fabrication fully root-caused, including nonsensical "EXCEPTION" row |
| Publication-ledger reconciliation job | slides/java, then barcode/python | Clean case first, then the hard out-of-band-commit edge case |
| Publication-target authority verification | font/python | Only confirmed live instance |
| Registry-drift requeue trigger | page/python, tex/python | Both share the identical EE-link mechanism |
| Candidate self-consistency checks | note/python | Original, cleanest single-heading-omission instance |
| Example verification coverage expansion | words/python, then words/net | Safe unpublished case first, then retroactive BLOCKER proof |
| Verification marker write-path fix | 3d/java | CRLF bug already root-caused to this exact line |

## Go/no-go verdicts

### 1. Continued local candidate generation
**Conditional yes, with immediate caveats.** Generation (`plan`/candidate-composition) is
deterministic-fact-first by design and that part holds up (Phase 2 §9: "never writes
prose" confirmed live). But Cluster B proves generation routinely runs against
stale/pinned knowledge with zero freshness gate (pdf/python: BLOCKER, 6-minutes-stale
clone cache silently producing a regressive candidate), and Cluster A proves the
disposition ledgers it produces cannot currently be trusted as preservation evidence on
roughly 20+/31 products. Recommendation: keep generating candidates (there is no cheaper
way to get a first draft), but treat every candidate as **unverified until Tier 2 items
4-9 exist**, and do not treat a "clean" `audit-portfolio` result as sufficient on its own
given Cluster A's proven false-pass instances.

### 2. Human review of existing candidates
**No, not as currently structured — reviewers are being handed self-reports that are
sometimes provably false.** Row 19's disposition/prose numeric self-reports
("139 public types," "153... 0 fabrications") and Cluster A's disposition ledgers are
exactly the artifacts a human reviewer would lean on to scope their own review effort, and
both are shown, by direct mechanical re-execution, to be unreliable on multiple products.
A reviewer trusting `content-dispositions.json`'s "nothing was dropped" claim at face
value would miss real, confirmed content loss (font/python: ~250 of 486 original lines
with zero disposition record at all). Recommendation: human review must independently
re-derive the true original and diff against it directly — exactly what this audit's own
Stage B/C methodology did — not review the ledgers as ground truth. Until Tier 2 items 1-3
exist, budget review time accordingly (assume the ledgers under-report, not over-report,
risk).

### 3. Republishing existing candidates to target repos
**No.** Two of this audit's own confirmed findings are already live and materially
misleading (words/net's non-compiling flagship example, cells/java's 44%-wrong core
narrative), one product's entire prior publication was silently erased with zero detection
for 5+ days (font/python), and the publication-ledger itself is blind on 55% of the
portfolio (row 20). Pushing any further candidate before Tier 1's items are corrected and
at least Tier 2 items 12-13 (reconciliation + target-authority verification) exist would
add to, not resolve, exactly this class of problem. The one narrow exception: Tier 1's
own itemized single-file corrections (words/net, cells/java, html/python, page/python) are
themselves republication actions — but each requires the specific manual verification
steps listed in its own item, not a blanket "republish is fine now" reading of this
verdict.

### 4. Autonomous scheduled execution of this whole system
**No.** The `approve` step is human-gated by convention only, not code-enforced (Phase 2
§9) — nothing in code stops an autonomous scheduler from calling `approve` and `push`
back-to-back on a candidate carrying any of Cluster A/B/C/D's proven blind spots. Running
this system on a schedule today would mean: stale-knowledge candidates get generated
undetected (Cluster B), disposition ledgers self-certify preservation that isn't real
(Cluster A), evidence-resolution passes claims that are false (Cluster C, 10+/9+ products
already), and even a genuinely correct push can be silently erased by a mirror-sync with
zero automatic alerting (Cluster E2). This is not a "tighten one gate" fix — it requires
Tier 2 items 1-3, 6-9, and 12-13 at minimum before autonomous scheduling is revisited, plus
code-level (not conventional) enforcement of the human-approval gate.

---
