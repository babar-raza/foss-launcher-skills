# Claim Injection Runbook

> **Governance**: Verified claim injection lifecycle.
> All facts derived from source code.

---

## 1. Claim ID Types

| Prefix | Source | Generator | Confidence |
|--------|--------|-----------|------------|
| `CLM-` | `scout.py` (tree-sitter) | `scout/claims.json` via `promote.py` | 1.0 syntactic |
| `ERC-` | `enrich.py` (LLM, S-61)  | `scout/enriched_claims.json` via `promote.py` | LLM-assigned |

Source of truth: `knowledge/{family}/{platform}/merged/claims.json`

---

## 2. Injection Entry Points

### Path 1: `attach_evidence.py` (S-77/S-78) — all content subdomains

```
scripts/pipeline/commands/healing/attach_evidence.py
  → evidence/runner.py:main()
  → evidence/runner.py:attach_product(family, platform)
  → lib/content_discovery.py:discover_content()   ← covers all content subdomains
  → evidence/runner.py:attach_evidence(filepath, knowledge)
  → evidence/mapper.py:_map_tokens_to_evidence()
  → evidence/writer.py:_write_evidence_to_frontmatter()
```

### Path 2: `batch_reference.py` — reference pages only

```
scripts/pipeline/commands/content/batch_reference.py
  → writes to $CONTENT_REPO_PATH/reference/
  → pre-seeds claims: [] then calls attach_evidence(..., force=True)
```

---

## 3. Subdomain Scope (TC-CLAIM-02)

`--subdomain SUBDOMAIN` restricts writes to one site:

```bash
# Scoped write (recommended for all write operations)
.venv/Scripts/python attach_evidence.py cells java --subdomain reference

# Report-only — no writes; scope defaults to ALL
.venv/Scripts/python attach_evidence.py cells java --dry-run
.venv/Scripts/python attach_evidence.py cells java --dry-run-json plan.json

# Explicit all-subdomains (suppresses Phase 1 WARN)
.venv/Scripts/python attach_evidence.py cells java --all-subdomains --confirm-all-subdomains
```

Phase 1 (current): unscoped write emits `WARN: running across all subdomains`.
Phase 2 (after TC-CLAIM-09): unscoped writes are errors.

Canonical subdomain values:
`products`, `reference`, `docs`, `blog`, `kb`

---

## 4. writer.py Union-Merge Behavior (GAP-15)

`writer.py:128-131`:
```python
merged_claims = sorted(set(existing_claims + new_claims))
```

Never removes claims. Once a claim ID lands in `evidence.claims` it persists
until removed via git. LH-01 (commit `60dbf67`) removed ERC IDs from 2112 files
via a one-time git op. No automated removal exists.

---

## 5. Idempotency and Skip Conditions

`runner.py:57` skips when: `existing.get("model_sha") == knowledge.repo_sha`

**Blind spot (GAP-14)**: skip key is upstream FOSS repo SHA, not `claims.json` hash.
ERC enrichment without new upstream commit → previously-stamped files skipped permanently.

Skip conditions (in order):
1. `draft: true` → `SKIP (draft)`
2. `model_sha == repo_sha` → `SKIP (current)`
3. audit FAIL findings → `SKIP (audit FAILs)`
4. `knowledge.available == False` → `SKIP`; batch_reference exits code 1 (LH-02)

---

## 6. Reference-Specific ERC Boost

`runner.py:73-90`: On reference pages with no code-block tokens, the class
name from the page title is the authoritative api_ref. Intentional design per AGENTS.md §6.
Always ALLOW in ClaimPolicy. Not subject to page_role routing.

---

## 7. ClaimPolicy (Phase 1 — Report-Only, TC-CLAIM-08)

`evidence/claim_policy.py` does **not** change injection output in Phase 1.
Adds `policy_status` and `policy_reason` to `--dry-run-json` ClaimPlan records.

| Condition | Action |
|-----------|--------|
| `claim_source="UNKNOWN"` | `BLOCK` |
| `token_match_context` set | `ALLOW` |
| reference subdomain + no token | `ALLOW` (title-based ERC) |
| `claim_page_role` matches subdomain | `ALLOW` |
| `claim_page_role` mismatches subdomain | `WARN` |
| `claim_page_role` is None | `UNKNOWN` |

---

## 8. ClaimPlan (`--dry-run-json`, TC-CLAIM-03)

Generate machine-readable per-file plan without writing:

```bash
.venv/Scripts/python attach_evidence.py cells java \
  --subdomain reference \
  --dry-run-json runs/claim-plan.json
```

Record format: `filepath`, `subdomain`, `action`, `existing_claims`,
`proposed_claims` (with `policy_status`/`policy_reason` per claim),
`added_claims`, `stale_claims`, `skip_reason`, `token_matches`.

---

## 9. Backfill Policy — Authoritative Gate (TC-CLAIM-07)

> **THIS SECTION SUPERSEDES ANY WEAKER STATEMENT ELSEWHERE.**
> Broad `.md` backfill is **FORBIDDEN by default**.

All of the following required before any broad inject:
1. TC-CLAIM-00 complete (clean working tree)
2. TC-CLAIM-02 complete (`--subdomain` implemented)
3. TC-CLAIM-03 complete (`--dry-run-json` implemented)
4. TC-CLAIM-05 complete (stale detection implemented)
5. TC-CLAIM-08 complete (ClaimPolicy layer exists)
6. TC-CLAIM-09 complete (ClaimPlan apply gate exists)
7. TC-CLAIM-06 complete (fixture integration tests pass)
8. `--dry-run-json` plan generated and reviewed; <= 10 files for pilot
9. `--subdomain` scoped to exactly one subdomain per run
10. `--apply-claim-plan` used (not raw `--force`)
11. `--max-files 10` for pilot; `--max-files 50` subsequent
12. `--confirm-apply` explicit flag
13. Post-run `truth_audit.py` passes
14. `git diff` shows only frontmatter changes in content files
15. Rollback command documented before execution

Any broad inject missing any gate = governance violation.

---

## 10. Content Change Legitimacy Policy

**Legitimate** (fixes a real correctness issue):
- Unknown/stale/orphaned/duplicate/malformed claim ID
- Wrong subdomain evidence; missing required evidence
- Contradiction with current knowledge; audited reference gap

**Not legitimate** (SHA noise):
- Adds `claims_hash`; sorts/reformats evidence; updates line numbers
- Adds ERC IDs without validation benefit; updates `model_sha` without reason
- Normalizes evidence because a tool happened to touch it

---

## 11. Known Gap Status

| ID | Status | Description |
|----|--------|-------------|
| GAP-1 | RESOLVED Phase 1 | No subdomain filter — fixed by `--subdomain` (TC-CLAIM-02) |
| GAP-5 | Detection only | Stale claims never pruned; ClaimValidator detection deferred |
| GAP-7 | CLOSED | cells/java truth_audit: 183 files, 0 FAIL |
| GAP-14 | Phase 1 | `model_sha` blind spot; `claims_hash` exposed in ClaimPlan |
| GAP-15 | Detection only | Union-merge accumulates stale claims (TC-CLAIM-05) |
| GAP-16 | Test added | LH-02 `knowledge.available` gate test in TC-CLAIM-06 |
| GAP-18 | RESOLVED | No apply gate — ClaimPlan apply gate (TC-CLAIM-09) |

---

## 12. Related Files

| File | Purpose |
|------|---------|
| `scripts/pipeline/commands/healing/attach_evidence.py` | CLI entry point |
| `scripts/pipeline/evidence/runner.py` | Orchestration |
| `scripts/pipeline/evidence/claim_policy.py` | Report-only policy layer |
| `scripts/pipeline/evidence/claim_validator.py` | Stale claim detection |
| `scripts/pipeline/lib/content_discovery.py` | Site paths, `_infer_subdomain()` |
