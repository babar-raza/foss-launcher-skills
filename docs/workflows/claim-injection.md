<!-- Adapted from aspose.org docs/workflows/ for standalone use -->

# Claim Injection Runbook

> **Governance**: Verified claim injection lifecycle.
> All facts derived from source code.

---

## 1. Claim ID Types

| Prefix | Source | Generator | Confidence |
|--------|--------|-----------|------------|
| `CLM-` | `scout.py` (tree-sitter) | `scout/claims.json` via `promote.py` | 1.0 syntactic |
| `ERC-` | `enrich.py` (LLM)  | `scout/enriched_claims.json` via `promote.py` | LLM-assigned |

Source of truth: `knowledge/{family}/{platform}/merged/claims.json`

---

## 2. Injection Entry Points

### Path 1: `attach_evidence.py` -- all content subdomains

```
scripts/pipeline/commands/healing/attach_evidence.py
  -> evidence/runner.py:main()
  -> evidence/runner.py:attach_product(family, platform)
  -> lib/content_discovery.py:discover_content()
  -> evidence/runner.py:attach_evidence(filepath, knowledge)
  -> evidence/mapper.py:_map_tokens_to_evidence()
  -> evidence/writer.py:_write_evidence_to_frontmatter()
```

### Path 2: `batch_reference.py` -- reference content only

```
scripts/pipeline/commands/content/batch_reference.py
  -> hard-coded to reference content path
  -> pre-seeds claims: [] then calls attach_evidence(..., force=True)
```

---

## 3. Subdomain Scope

`--subdomain SUBDOMAIN` restricts writes to one site:

```bash
# Scoped write (recommended for all write operations)
attach_evidence.py cells java --subdomain reference

# Report-only -- no writes; scope defaults to ALL
attach_evidence.py cells java --dry-run
attach_evidence.py cells java --dry-run-json plan.json

# Explicit all-subdomains (suppresses Phase 1 WARN)
attach_evidence.py cells java --all-subdomains --confirm-all-subdomains
```

Phase 1 (current): unscoped write emits `WARN: running across all subdomains`.
Phase 2: unscoped writes are errors.

---

## 4. writer.py Union-Merge Behavior

```
merged_claims = sorted(set(existing_claims + new_claims))
```

Never removes claims. Once a claim ID lands in `evidence.claims` it persists
until removed via git. No automated removal exists.

---

## 5. Idempotency and Skip Conditions

Skip key: `existing.get("model_sha") == knowledge.repo_sha`

**Blind spot**: skip key is upstream FOSS repo SHA, not `claims.json` hash.
ERC enrichment without new upstream commit -> previously-stamped files skipped permanently.

Skip conditions (in order):
1. `draft: true` -> `SKIP (draft)`
2. `model_sha == repo_sha` -> `SKIP (current)`
3. audit FAIL findings -> `SKIP (audit FAILs)`
4. `knowledge.available == False` -> `SKIP`; batch_reference exits code 1

---

## 6. Reference-Specific ERC Boost

On reference content with no code-block tokens, the class name from the page title is the
authoritative api_ref. Intentional design. Always ALLOW in ClaimPolicy. Not subject to
page_role routing.

---

## 7. ClaimPolicy (Phase 1 -- Report-Only)

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

## 8. ClaimPlan (`--dry-run-json`)

Generate machine-readable per-file plan without writing:

```bash
attach_evidence.py cells java \
  --subdomain reference \
  --dry-run-json runs/claim-plan.json
```

Record format: `filepath`, `subdomain`, `action`, `existing_claims`,
`proposed_claims` (with `policy_status`/`policy_reason` per claim),
`added_claims`, `stale_claims`, `skip_reason`, `token_matches`.

---

## 9. Backfill Policy -- Authoritative Gate

> **THIS SECTION SUPERSEDES ANY WEAKER STATEMENT ELSEWHERE.**
> Broad `.md` backfill is **FORBIDDEN by default**.

All of the following required before any broad inject:
1. Clean working tree
2. `--subdomain` implemented
3. `--dry-run-json` implemented
4. Stale detection implemented
5. ClaimPolicy layer exists
6. ClaimPlan apply gate exists
7. Fixture integration tests pass
8. `--dry-run-json` plan generated and reviewed; <= 10 files for pilot
9. `--subdomain` scoped to exactly one subdomain per run
10. `--apply-claim-plan` used (not raw `--force`)
11. `--max-files 10` for pilot; `--max-files 50` subsequent
12. `--confirm-apply` explicit flag
13. Post-run `truth_audit.py` passes
14. `git diff content/` shows only frontmatter changes
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
| GAP-1 | RESOLVED Phase 1 | No subdomain filter -- fixed by `--subdomain` |
| GAP-5 | Detection only | Stale claims never pruned; ClaimValidator detection deferred |
| GAP-7 | CLOSED | Truth audit passes |
| GAP-14 | Phase 1 | `model_sha` blind spot; `claims_hash` exposed in ClaimPlan |
| GAP-15 | Detection only | Union-merge accumulates stale claims |
| GAP-16 | Test added | `knowledge.available` gate test |
| GAP-18 | RESOLVED | No apply gate -- ClaimPlan apply gate added |

---

## 12. Related Files

| File | Purpose |
|------|---------|
| `scripts/pipeline/commands/healing/attach_evidence.py` | CLI entry point |
| `scripts/pipeline/evidence/runner.py` | Orchestration |
| `scripts/pipeline/evidence/claim_policy.py` | Report-only policy layer |
| `scripts/pipeline/evidence/claim_validator.py` | Stale claim detection |
| `scripts/pipeline/lib/content_discovery.py` | Site paths, `_infer_subdomain()` |
