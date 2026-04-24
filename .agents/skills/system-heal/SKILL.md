<!-- CONTRACT: agent-executed
     purpose: audit-driven content healing via gap-eval baseline + classified finding repair
     preconditions: knowledge model current; clone cache exists; gap-eval profile exists
     postcondition: CONTENT findings fixed and grades improved; PIPELINE findings documented + HOLD items routed to S-90 for governed inspection
     idempotent: no — LLM-generated fixes vary; Tier 3 findings may differ between runs
     verified: 2026-04-11
-->
# S-87: System Heal — Audit-Driven Content Healing

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform} [--scope all|docs|products|kb|blog|reference] [--no-tier3-cache] [--dry-run] [--max-findings N]`

## Purpose
Audit-driven, issue-by-issue healing for a family/platform. Runs when `refresh-product` (S-84)
exits early (no upstream SHA change) but content is known or suspected to be wrong. Produces a
deterministic BEFORE baseline, classifies each finding by pipeline origin, heals CONTENT-class
issues automatically, and generates a structured pipeline evidence report for PIPELINE-class
issues requiring human action.

**Not a replacement for S-84 (change-driven refresh).** These skills are complementary:
S-84 handles change-driven refresh; S-87 handles audit-driven repair when S-84 exits early.

## Pre-conditions

1. Clone cache must exist at `runs/.clone_cache/aspose_{family}_{platform}/`
   — if missing, run S-34 (repo-scout) first.
2. Knowledge must not be stale: run `/knowledge-bootstrap` (S-54) first if `stale_since` is not null.
   Healing wrong content on a stale knowledge model produces wrong repairs.
3. Profile must exist at `scripts/gap-eval/profiles/{family}/{platform}.yaml`
4. `LLM_API_KEY` env var set (for Phase 2 Tier 3 calls); falls back to Ollama if unset.

## Hard Limits

- **Max findings**: Default 50. If Phase 1 (deterministic baseline) exceeds `--max-findings`,
  halt immediately. At that scale use S-44 (gap-plan) + S-46 (gap-apply) wave-ordered
  remediation instead.
- **Max S-26 passes per file**: 2. If grade does not improve after 2 passes, escalate;
  do not loop further.
- **AMBIGUOUS findings are never auto-repaired**: always routed to pipeline evidence report.
- **Tier 3 non-determinism flag**: findings with `tier3_non_determinism_flag: true` are
  never routed to automated repair regardless of `origin_class`.

---

## Phase 1: Deterministic Baseline

Run gap-eval with `--no-llm`. Reproducible BEFORE snapshot — no LLM variance.

```bash
.venv/Scripts/python scripts/gap-eval/run.py {family} {platform} \
    --scope {scope} --no-llm \
    --out reports/system-heal/{family}-{platform}/baseline \
    --state-dir reports/system-heal/{family}-{platform}/state
```

Record profile SHA (`sha256(profile.yaml bytes)[:8]`) and clone SHA in:
`reports/system-heal/{family}-{platform}/run_manifest.json`

**Hard stop**: if finding count > `--max-findings` (default 50), halt with:
> "Finding count {N} exceeds --max-findings {M}. Use S-44 + S-46 wave-ordered remediation."

Do not proceed to Phase 2.

---

## Phase 2: Extended Baseline (LLM + Tier 3 Cache)

Run gap-eval with LLM and tier3_cache active. On first run, populates the Tier 3 cache;
on reruns, uses cached results (idempotent for unchanged files).

```bash
.venv/Scripts/python scripts/gap-eval/run.py {family} {platform} \
    --scope {scope} \
    --out reports/system-heal/{family}-{platform}/extended-baseline \
    --state-dir reports/system-heal/{family}-{platform}/state
```

Pass `--no-tier3-cache` only if the operator explicitly requested it via the skill argument.

Annotate all findings with `tier_resolved_by: 3` and no `tier3_cache_hit` field as
non-determinism flagged. Record count in `run_manifest.json`.

If LLM unavailable: Tier 3 findings go to HOLD bucket with `origin_class: NEEDS_REVIEW`.

---

## Phase 3: Origin Classification

```bash
.venv/Scripts/python scripts/gap-eval/origin_map.py \
    reports/system-heal/{family}-{platform}/extended-baseline.json \
    {family} {platform} \
    --out reports/system-heal/{family}-{platform}/annotated-findings.json
```

Sort findings into three buckets:

| Bucket | Criteria |
|--------|----------|
| **CONTENT** | `origin_class` is CONTENT or UPSTREAM **AND** `origin_certainty` is HIGH or MEDIUM **AND** `tier3_non_determinism_flag: false` |
| **PIPELINE** | `origin_class` is PIPELINE (any certainty) |
| **HOLD** | Everything else: AMBIGUOUS, LOW certainty, `tier3_non_determinism_flag: true`, NEEDS_REVIEW |

HOLD findings go to the pipeline evidence report only. Never to automated repair.

---

## Phase 4: Content Healing (CONTENT bucket only)

Skip entirely if `--dry-run` is set.

Route by `repair_route` field from origin classification:

### S-74 route (broken-link findings)

Invoke S-74 (causal-backtrack) with the annotated findings report as input.
S-74 handles this completely; record result in `reports/system-heal/{family}-{platform}/heal_log.json`.
S-74 escalates automatically at depth ≥ 3; continue with non-link findings.

### S-46 route (wrong-package, wrong-api-name/hallucination)

Run S-46 (gap-apply) waves 1 and 2 only. Do not run wave 3+ in system-heal context.

S-55 (no-downgrade-guard) and revert-on-fail are enforced internally by S-46. Do not add a
second layer — double-revert behavior would result.

If S-46 reports "old_text not found in file" for a finding: log SKIP; continue.

### S-26 route (wrong-claim/hallucination, unimplemented-as-working, missing-section, structural-reference-page)

For each unique file in the CONTENT bucket with these finding types, invoke S-26 (heal-page).
Hard limit: 2 passes per file. If grade does not improve after 2 passes, add to escalation list
(not PIPELINE report — this is a content-level failure, not a pipeline failure).

Track all operations in `reports/system-heal/{family}-{platform}/heal_log.json`.

---

## Phase 5: Pipeline Evidence Report

For PIPELINE bucket + HOLD bucket, write:
`reports/system-heal/{family}-{platform}/pipeline-evidence.md`

Structure:
1. **Extraction problems** (`phantom-api`, `knowledge-model-wrong`): evidence + required action (re-run S-34)
2. **Profile configuration problems** (`wrong-package` PIPELINE subclass): evidence + required action (update profile YAML, re-run gap-eval)
3. **Enrichment problems** (`wrong-claim` PIPELINE subclass): evidence + required action (re-run S-37 for affected claim IDs)
4. **Planner gaps** (`missing-section` PIPELINE subclass): evidence + required action (re-run S-47/S-82 or add page to site plan manually)
5. **Ambiguous and HOLD findings**: list with evidence; classify via S-90 (§7c)
6. **Tier 3 non-determinism flags**: list of findings needing a second run to confirm (real escalation per §7c condition 3)

Also write `reports/system-heal/{family}-{platform}/pipeline-evidence.json` (machine-readable).

After writing this report, **invoke S-90 on the HOLD bucket items**:
```
/publish-readiness-review {family} {platform} --grade-filter C,D,F
```

S-90 will classify each HOLD item as either:
- **Actionable** (CONTENT defect misrouted to HOLD) → S-90 routes to S-21/S-26
- **Pipeline-class only** (genuine extraction/profile/planner gap) → documented in
  pipeline-evidence.md as requiring the specific pipeline action listed above
- **Real escalation** (tier3_non_determinism_flag, skill breakage) → S-90 emits
  escalation record per §7c conditions 2 and 3

Do not halt at this report. S-90 is the governed continuation path for all HOLD items
that S-87 cannot automatically repair. Real human action is required only for items
that S-90 classifies as ESCALATED per §7c.

---

## Phase 6: Re-Verify

Skip entirely if `--dry-run` is set.

Run gap-eval on healed content (scoped to files in `heal_log.json` if possible; full scope otherwise):

```bash
.venv/Scripts/python scripts/gap-eval/run.py {family} {platform} \
    --scope {scope} \
    --out reports/system-heal/{family}-{platform}/post-heal \
    --state-dir reports/system-heal/{family}-{platform}/state
```

Compare `post-heal.json` against `extended-baseline.json` by finding ID:

| Outcome | Definition |
|---------|------------|
| Fixed | Finding ID in baseline but not in post-heal |
| Unchanged | Finding ID in both |
| **Regression** | Finding ID in post-heal but not in baseline |

**If regressions detected**: immediately revert all Phase 4 changes:

```bash
git checkout -- {each healed file from heal_log.json}
```

Do not commit. Report exactly which files were reverted and what new findings appeared.

---

## Phase 7: Commit or Escalate

- **fixed > 0 AND regressions == 0**: invoke `/commit` with message referencing S-87 and finding counts.
- **fixed == 0**: do not commit; report; proceed to Phase 8.
- **regressions detected**: do not commit (already reverted in Phase 6); report escalation with finding IDs.

---

## Phase 8: Final Report

Write `reports/system-heal/{family}-{platform}/final-report.md`:

1. Run manifest summary (profile SHA, clone SHA, tier3_cache coverage %)
2. Finding counts before/after by origin class
3. Files healed, findings resolved (by ID)
4. Files escalated (S-26 failed after 2 passes)
5. Pipeline evidence summary (N findings requiring human action, by category)
6. Tier 3 non-determinism summary (N findings not yet cache-covered; recommend second run)
7. Verdict change (if any: PASS/CONDITIONAL/FAIL before → after)
8. Commit SHA or reason for no commit
9. Required human actions (extracted from `pipeline-evidence.md`)

---

## Error Handling

| Failure | Action |
|---------|--------|
| Clone cache missing | HALT; run S-34 first |
| Knowledge stale (`stale_since` not null) | HALT; run S-12 → S-14 first |
| Phase 1 finding count > `--max-findings` | HALT; use S-44 + S-46 instead |
| S-26 fails to improve after 2 passes | Move file to escalation list; continue |
| S-46 old_text not found in file | Skip finding (S-46 existing behavior); log SKIP |
| S-74 depth ≥ 3 | S-74 escalates automatically; continue with non-link findings |
| Phase 6 regression detected | Revert all Phase 4 changes; do not commit; report |
| `origin_map.py` raises exception for a finding | Classify as AMBIGUOUS; route to pipeline evidence |
| LLM unavailable in Phase 2 | Tier 3 findings → NEEDS_REVIEW; add to HOLD bucket |

---

## Output Files

| File | Phase | Description |
|------|-------|-------------|
| `reports/system-heal/{family}-{platform}/run_manifest.json` | 1 | Profile SHA, clone SHA, timestamp |
| `reports/system-heal/{family}-{platform}/baseline.json` | 1 | Deterministic (no-LLM) findings |
| `reports/system-heal/{family}-{platform}/extended-baseline.json` | 2 | Full findings with Tier 3 + cache |
| `reports/system-heal/{family}-{platform}/annotated-findings.json` | 3 | Findings with origin classification |
| `reports/system-heal/{family}-{platform}/heal_log.json` | 4 | Operations performed, per file |
| `reports/system-heal/{family}-{platform}/pipeline-evidence.md` | 5 | Human-readable pipeline issues |
| `reports/system-heal/{family}-{platform}/pipeline-evidence.json` | 5 | Machine-readable pipeline issues |
| `reports/system-heal/{family}-{platform}/post-heal.json` | 6 | Post-heal verification findings |
| `reports/system-heal/{family}-{platform}/final-report.md` | 8 | Complete run summary |

---

## Related Skills

- **S-43 gap-eval**: The evaluation engine this skill orchestrates.
- **S-44 gap-plan**: Wave-ordered remediation planning (use instead of S-87 when > 50 findings).
- **S-46 gap-apply**: Wave-ordered fix application (Phase 4 S-46 route).
- **S-26 heal-page**: Page-level content healing (Phase 4 S-26 route).
- **S-74 causal-backtrack**: Broken-link upstream tracing (Phase 4 S-74 route).
- **S-84 refresh-product**: Change-driven refresh (complementary; S-87 handles when S-84 exits early).
