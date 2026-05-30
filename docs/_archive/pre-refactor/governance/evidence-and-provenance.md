# Archived Document

Archived: 2026-05-30

Reason: Superseded by the docs architecture refactor. This file is retained for history only; do not use it as current operating guidance.

Successor: See docs/README.md for the current documentation map and canonical references.

Original path: docs/_archive/pre-refactor/governance/evidence-and-provenance.md

---

---
# Governance child document — extracted from AGENTS.md
# Source: AGENTS.md §5, §10, §10a, §10c
# Plan: delightful-wondering-hartmanis (TC-03)
# Extracted: 2026-04-28
---

## 5. Evidence Requirements (non-negotiable)

- Every content page write must pass S-23 (content-check) before committing.
  **S-23 implementation**: `python scripts/pipeline/commands/content/audit.py --files {path}` (deterministic, scriptable).
  Pre-commit hook enforces this automatically; CI workflow blocks PRs with FAILs.
- Every code block in `content/` must come from a snippet in `knowledge/{family}/{platform}/snippets/`
- Every factual claim must be traceable to a `claim_id` in `knowledge/{family}/{platform}/claims.json`
- Claims with `confidence < 0.5` require human review before use
- An `evidence:` YAML frontmatter block must be present in every content page. Generate it
  deterministically with `python scripts/pipeline/commands/healing/attach_evidence.py --files {path}` (for pages
  with code blocks) or manually via S-24 (evidence-cite, for prose-only pages). Format:
  ```yaml
  evidence:
    model_sha: "<repo_sha from merged/model.yaml>"   # anchors to knowledge version
    model_version: "<version>"
    claims: [CLM-xxx, ...]      # claim_ids from merged/claims.json ([] is valid)
    apis: [ClassName.method, …] # verified against merged/api_surface.json ([] is valid)
    formats: [{ext: glb, support: both}, …]  # omit if no format content
  ```
  Do **not** include `ground_check:` — it is self-reported and unverifiable.
  Do **not** use inline HTML comments (`<!-- evidence: ... -->`).
  Frontmatter is the canonical citation store, machine-validated by `audit.py`. The
  `evidence-panel` Hugo partial renders this data **only in non-production builds**
  (see Section 13 — Internal Metadata Rendering Policy). After any knowledge model update,
  rerun `attach_evidence.py {family} {platform}` to refresh stale blocks.


## 5a. Knowledge Bootstrap Prerequisite (LH-02, added 2026-04-30)

**Knowledge bootstrap is a hard prerequisite for content generation and healing.**
See AGENTS.md §5a for the complete policy. Summary of key rules:

- `batch_reference.py` and all generation skills must exit with error code 1 when
  `knowledge.available == False` -- graceful degradation that generates ungrounded content
  is prohibited.
- All evaluators must return WARN with "UNVERIFIED" text when knowledge is unavailable.
  Returning `[]` (silent skip) is prohibited.
- Pages generated without local knowledge must have `provenance.knowledge_status: ungrounded`.
- Ungrounded pages must not receive grade A (ceiling is B).
- Publication readiness review must WARN or FAIL when ungrounded pages exist in mandatory sections.

### Evidence chain integrity

The forensic-audit-healing sprint (2026-04-30) found that 15 of 16 products had corrupted
clone caches pointing to the monorepo instead of the actual FOSS source repos. This caused:
1. Scout extraction (S-34) to extract from the wrong source
2. Knowledge artifacts to be missing or empty for 15 products
3. Evaluators to silently skip all truth checks for those products
4. Grade A pages with no actual knowledge backing

The policy above closes this gap and ensures future generation is always knowledge-grounded.

## 10. Evidence Proof in Commits

Every commit touching `content/` MUST include in the commit message:

- Knowledge model SHA: `knowledge/{family}/{platform}/merged/model.yaml` `repo_sha` value
- Ground-check result: `PASS` (with report path)
- Skills invoked: `[S-xx, S-yy, ...]`

The `evidence:` frontmatter block in each page is the persistent inline evidence record. `model_sha` anchors it to the knowledge version; `audit.py` detects staleness automatically.

### Skill invocation accuracy (T-04 requirement)

For content commits, the "Skills invoked:" field MUST accurately reflect which skills were invoked as **full SKILL.md procedures**. Do not declare a skill that was applied as inline reasoning (equivalent work but not through the registered skill procedure).

Use a skill run record to ensure accuracy:
```bash
# Before execution: create a run record
python scripts/pipeline/commands/ops/skill_run_manager.py create --skills S-48 S-23 --plan '<plan>'

# If any skill was applied as inline reasoning, record it explicitly:
python scripts/pipeline/commands/ops/skill_run_manager.py record-step \
  --run-id <id> --skill S-01 --type inline_reasoning \
  --note "Path checked inline: under content/, not forbidden" --deviation

# Get the correct "Skills invoked:" list (excludes inline_reasoning):
python scripts/pipeline/commands/ops/skill_run_manager.py get-declared-skills --run-id <id>
```

Skill run records are stored in `reports/skill-runs/`. The CI step "Validate skill run records" checks that declared skills match the record (advisory). The commit-msg hook warns on mismatch.

### Proof bundles for compliance observations

Any governance run that produces a compliance observation in `reports/compliance/` MUST generate a corresponding proof bundle in `reports/proofs/`. Use:
```bash
bash scripts/ci/hooks/capture_proof_bundle.sh <slug> <command1> <command2> ...
```

The bundle captures verbatim command outputs with exit codes, git diff, and structured metadata. The CI step "Check compliance observation proof bundles" verifies this linkage.

## 10a. Verification Standards for Fixes

Every fix — whether to a script, evaluator, content page, or knowledge artifact — must meet these verification standards before being declared complete.

### Required evidence per fix

| Fix type | Before evidence | After evidence | Tool |
|----------|----------------|----------------|------|
| Content page fix | `audit.py` FAIL count before fix | `audit.py` FAIL count after fix (must be <= before) | `python scripts/pipeline/commands/content/audit.py --files {path}` |
| Evaluator logic fix | Evaluation output before change | Evaluation output after change (same test page) | `python -m scripts.pipeline.content_eval.cli evaluate ...` |
| Knowledge artifact fix | Artifact state before fix (git diff) | Artifact state after fix (git diff) | `git diff knowledge/` |
| Script/pipeline fix | Script invocation output before fix | Script invocation output after fix | Per script |

### Regression check requirement

After any fix, verify that the fix does not break previously passing content. Minimum check:
```bash
# Re-run evaluators on the same product that was passing before
python -m scripts.pipeline.content_eval.cli evaluate {family} {platform} --write-grade
```

If any previously-passing page now FAILs, the fix introduced a regression. Investigate before committing.

### Before/after evidence trail

Every fix commit message MUST include:
- What was broken (symptom)
- Root cause (one sentence)
- What changed (file + function/line)
- Before: [tool output or count before fix]
- After: [tool output or count after fix]
- Regression check: PASS / FAIL (if FAIL, explain)

### Verification scope selection

| Fix scope | Verification scope |
|-----------|-------------------|
| Single file | Verify that file only |
| Single evaluator | Verify all test pages that the evaluator touches |
| Knowledge bootstrap chain (scout/enrich/promote) | Re-run full launch gate (§7a) on the affected product |
| Grade ceiling or model.py change | Re-grade all products; verify overall A/B/C/D/F distribution is within expected range |


## 10c. Output-Location Discipline

All agent-generated artifact files must be written to their designated location. Using the wrong output location causes git leakage, CI failures, and audit trail gaps.

| Artifact type | Correct location | Never write to |
|---------------|-----------------|----------------|
| Content pages (docs, blog, kb, reference, products) | `content/{site}/en/{family}/{platform}/` | `reports/`, `knowledge/`, repo root |
| Knowledge artifacts (api_surface, claims, formats, etc.) | `knowledge/{family}/{platform}/` | `content/`, `reports/`, repo root |
| Audit and evaluation reports | `reports/` (gitignored, local-only) | `content/`, `knowledge/`, repo root |
| Launch gate results | `reports/launch-gate/` | `content/`, `knowledge/`, git-tracked paths |
| Skill gap escalation reports | `reports/skill-gaps/` | Any git-tracked path |
| Skill breakage reports | `reports/skill-breakage/` | Any git-tracked path |
| Evidence repair logs | `reports/evidence-repair/` | Any git-tracked path |
| Compliance observations + proof bundles | `reports/compliance/`, `reports/proofs/` | Any git-tracked path |
| Design documents (schema, evaluator specs) | `reports/design/` | `knowledge/`, `content/`, skills/ |
| Override tokens | `reports/overrides/pending/` | Any git-tracked path |
| Discovery patrol/sweep reports + history | `reports/discovery/`, `reports/discovery/history/` | Any git-tracked path |

**`reports/` is a strict local artifact boundary.** Nothing under `reports/` may ever be staged or committed. The pre-commit hook enforces this. If you need a design document to persist across sessions, it must live in `reports/design/` (local-only) — not in `knowledge/` or `content/`.

**Do not write reports to the repo root.** Files like `reconciliation-report.md`, `gate-results.txt`, or `debug.log` written to `/` will be flagged by `git status` as untracked files and may confuse future audit runs. Use `reports/` exclusively.

---

## Metrics Evidence

Metrics sprints must produce local evidence in `reports/metrics/`:
- Per-call event JSONL files (`events/{run_id}.jsonl`) — captured by `MetricsEventLedger`
- Per-run payload JSON (`dry/{run_id}.dry.json`, `tests/`, `failed/`)
- Secret-scan proof (output of `check_metrics_no_secrets.py`)
- Evidence bundle (`slice{N}-evidence-bundle.tar.gz`)

`reports/metrics/` is git-ignored. Evidence is local-only by design.
Metrics captures must use `AGENT_METRICS_ENDPOINT` and `AGENT_METRICS_TOKEN` from environment only.
See `AGENTS.md §15` for the full metrics obligation.
