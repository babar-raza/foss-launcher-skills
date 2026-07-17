# Refresh Unification 001 — Merge the Three Parallel Refresh Systems Into One Pipeline

**Status**: IMPLEMENTED (2026-07-17)
**Decided by**: `aspose-org-foss-refresh-tidy-lightning` (RPR-A-04 step 3, RPR-G-01)
**Implemented in**: `skills/refresh-product.md` (canonical) + all 3 provider mirrors; `skills/{baseline-ledger-writer,triage-verdict-gate,plan-health-watchdog,regression-classification}.md`; `scripts/pipeline/lib/{baseline_ledger,baseline_resolver,forbidden_claims_check,regrounding_check,schema_validators}.py`; `scripts/pipeline/commands/ops/{post_refresh_verify,page_impact_assess,refresh_review,triage_confirm}.py`; `scripts/pipeline/commands/content/{body_refresh,seo_stability_check,audit_content_hash}.py`
**Supersedes/absorbs**: Amendment 009 (`amendment-009-refresh-decision-engine.md`) as a *silo*; its blocking-gate logic is retained inside the unified path
**Backlog**: ST-027 (evidence-restamp incident), ST-028 (silent revert of S-104–S-108)

---

## Context — three uncoordinated systems, not one broken pipeline

A forensic audit (plan §2.1) found the repository was running **three parallel refresh systems that
did not reference each other**:

| System | What it was | Real state before this decision |
|---|---|---|
| **(A)** S-84 `refresh-product` | The documented 13-step orchestration chain | Structurally sound shell, but body prose was edited by S-20 — pure agent prose instruction with **no deterministic backing script**, and every downstream gate weaker than the skill doc implied |
| **(B)** Amendment-009 decision engine | `decision_engine.py`, `semantic_refresh_guard.py`, … | Had a genuinely blocking gate, but was **scoped to reference-page writes only**, and its own design record states: *"No deterministic body updater exists… route existing content page updates to a post-Phase-5 agent workflow rather than building an untested deterministic updater."* Zero cross-references to (C). |
| **(C)** S-104–S-108 body-refresh engine | `semantic_diff`, `body_refresh`, `refresh_oracle`, `locale_refresh_handoff`, `frontmatter_body_consistency` | Built precisely to close the gap (B) admitted it punted. Validated (14/14 pilots, 4-product backfill). **Wired into `.claude/commands/` mirrors only — never the canonical `.agents/skills/` files — then silently reverted 5 days later with no rationale and no backlog entry.** Orphaned. Zero cross-references to (B). |

A refresh therefore executed purely via (A), with (B) silently gating only the reference path and (C)
doing nothing at all. The recurring symptom — refreshes that touch `evidence:` frontmatter without
touching the prose readers actually see — was the predictable result.

## Decision

**Merge all three into a single pipeline. No system survives as a separate silo.**

1. **(A) is kept as the orchestration shell** and becomes the single canonical entry point,
   re-sequenced per plan §4 in the **canonical** `skills/refresh-product.md` — not a command mirror.
2. **(C) is re-integrated as the primary body-editing path** (S-105 `body-refresh`), consuming S-104's
   typed `semantic_changes.json`. **S-20 `page-update` is demoted to an explicit, logged fallback**
   used only when body-refresh reports `UNRESOLVED`.
3. **(B) is retired as a silo; its blocking-gate logic is absorbed.** Its
   `GENERATED_ONLY_BODY_CHANGE_INSUFFICIENT` verdict is merged with S-108
   `frontmatter-body-consistency` into one enforcement path. (B) no longer punts docs/kb/blog to an
   unenforced manual fallback, because S-105 now covers it.
4. **Gates block instead of WARN.** `post_refresh_verify --verify --assert-no-skipped` Checks 7/8
   (RPR-F-01), 9 (RPR-F-03), 10 (RPR-F-04), 11 (RPR-F-05) are blocking. A WARN nobody reads is not a
   control.
5. **Baseline becomes durable history, not a mutable scalar.** S-111 `baseline-ledger-writer` provides
   an append-only `baseline_ledger.jsonl` plus a real orphaned-SHA walkback, replacing the
   `model.yaml.repo_sha` scalar that `promote.py` overwrote every run.
6. **Impact is citation-based, not token-guessed.** The PIA reads each page's own
   `evidence.claims`/`evidence.apis` frontmatter; per-page `NOT_AFFECTED` is now assignable.

## Why the wiring lives in the canonical skill files

The 2026-07-02 revert (ST-028) was possible *because* the original integration touched only
`.claude/commands/` mirrors — nothing reading the canonical `.agents/skills/` source would ever
notice it was missing, and nothing reading the mirror would notice it was reverted. This decision
therefore requires:

- the wiring to live in the **canonical** source, and
- `scripts/ci/checks/check_skill_command_parity.py` (RPR-G-02) to enforce 3-mirror parity with
  co-change checking, so a future mirror-only wiring **or** mirror-only revert is flagged.

Both the 2026-06-27 wiring commit and the 2026-07-02 revert commit would have been blocked by that
check without an explicit `SKILL-COMMAND-DIVERGENCE-ACK:` trailer.

## Consequences

**Accepted:**
- One entry point, one decision enum (`VALID_DECISIONS`), one baseline source of truth.
- Refreshes that update zero prose now **fail** rather than pass with warnings. Verified empirically:
  re-verifying the 4 already-backfilled products (RPR-H-01) shows **all 4 now FAIL** — including
  pdf/net's 36 recorded body diffs against an empty `pages_updated` (the literal §2.4 defect). This
  pre-existing debt was always there; the old gates hid it.
- Consequently, new pilots are **halted** (plan §9 Stage 3) until that debt is remediated through the
  unified chain. This is the intended behavior, not a setback.

**Costs / honest limits:**
- One generation step (`PARAGRAPH_REWRITE`) is genuinely stochastic (LLM, temperature 0.1), so
  idempotency is tiered: structural + content idempotency are byte-checkable; **semantic idempotency
  (oracle-pass + identical `grounding_source`) is a deliberately weaker guarantee** — a check asserting
  byte-identical LLM output would be a bug in the test, not a control.
- The remaining 5 deterministic strategies never touch an LLM, which is what keeps the stochastic
  blast radius to one identifiable code path.

## Alternatives rejected

- **Keep three systems, document the boundaries.** Rejected: the boundaries were already documented
  and still produced a silently-orphaned engine and an unenforced manual fallback.
- **Build a fourth pipeline.** Rejected explicitly (plan §16): this decision merges, it does not add.
- **Regenerate/rewrite all pages.** Rejected: violates surgical-first (§3.6). Demonstrated in practice
  — RPR-A-02 found all 5 flagged pages carry **0 FAIL** and were therefore left untouched rather than
  rewritten.
