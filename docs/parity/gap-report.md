# Gap Report

**Program:** Skill Parity Migration — aspose.org → foss-launcher-skills-gitlab
**Date:** 2026-04-20
**Total classified gaps:** 59 (42 missing skills + 13 infrastructure + 4 governance)

---

## Gap Classification Legend

| Code | Meaning |
|------|---------|
| `missing_skill` | No equivalent skill in foss-launcher |
| `missing_script` | Skill exists but backing script absent |
| `missing_registration` | Skill file exists but not in registry |
| `missing_governance` | No internal_flag, no guard, no chain reference |
| `missing_docs` | No RUNBOOK/OPERATOR_GUIDE equivalent |
| `missing_ci` | No GitHub workflow enforcement |
| `missing_hooks` | No git hooks |
| `missing_sync` | Sync script doesn't cover .agents/.kilocode |
| `missing_infra` | Translator/gap-eval/SEO systems absent |
| `naming_mismatch` | Same behavior, different slug/ID |
| `id_reassignment` | Same ID, completely different skill |
| `behavioral_mismatch` | Present but behaves differently |
| `verification_gap` | Present but behavior unconfirmed |

---

## Section 1: Missing Skills (42 gaps)

### 1a: Internal/Guard Skills (P1 — Critical)

| Gap # | Slug | Gap Type | Evidence | Action |
|-------|------|---------|---------|--------|
| G-001 | no-downgrade-guard | `missing_skill` + `missing_script` | aspose S-55 is INTERNAL; `scripts/pipeline/no_downgrade_guard.py` exists in aspose but not foss | Port script + create skill file + register as internal S-56 |
| G-002 | gap-plan | `missing_skill` | aspose S-44 INTERNAL; planning sub-tool for gap remediation pipeline | Port skill; assign foss S-59; mark internal |

### 1b: Knowledge Pipeline Skills (P1)

| Gap # | Slug | Gap Type | Evidence | Action |
|-------|------|---------|---------|--------|
| G-003 | knowledge-enrich | `missing_skill` | aspose S-37; LLM semantic enrichment of scout artifacts; `scripts/pipeline/enrich.py` in aspose; no equivalent in foss | Port skill + enrich.py; assign foss S-57 |
| G-004 | gap-eval | `missing_skill` | aspose S-43; content verification against clone cache; backed by `scripts/gap-eval/run.py`; foss has evidence pipeline instead (both should coexist per decision) | Port skill (prompt-only); assign foss S-58; note evidence pipeline alternative |
| G-005 | gap-report | `missing_skill` | aspose S-45; cross-product gap synthesis; backed by gap-eval system | Port skill; assign foss S-60 |
| G-006 | gap-apply | `missing_skill` | aspose S-46; execute wave-ordered fix specs; backed by gap-eval system | Port skill; assign foss S-61 |

### 1c: Site Planning & Orchestration Skills (P1)

| Gap # | Slug | Gap Type | Evidence | Action |
|-------|------|---------|---------|--------|
| G-007 | site-plan | `missing_skill` | aspose S-47; pre-generation site manifest; critical for batch launch planning | Port skill; assign foss S-62 |
| G-008 | delta-site-plan | `missing_skill` | aspose S-82; incremental planning after knowledge update | Port skill; assign foss S-87 |
| G-009 | family-sync | `missing_skill` | aspose S-48; updates family page across all platforms | Port skill; assign foss S-63 |
| G-010 | refresh-product | `missing_skill` | aspose S-84; 14-step full post-launch refresh chain | Port skill; assign foss S-89 |
| G-011 | refresh-product-page | `missing_skill` | aspose S-86; re-generates product landing page | Port skill; assign foss S-91 |
| G-012 | launch-rollback | `missing_skill` | aspose S-79; reverts generated content for one product | Port skill; assign foss S-84 |

### 1d: Generation Skills (P2)

| Gap # | Slug | Gap Type | Evidence | Action |
|-------|------|---------|---------|--------|
| G-013 | new-products-page | `missing_skill` | aspose S-61; products.aspose.org landing page generation | Port skill; assign foss S-66 |
| G-014 | batch-reference | `missing_skill` | aspose S-62; bulk reference page generation | Port skill; assign foss S-67 |
| G-015 | new-kb-index | `missing_skill` | aspose S-69; KB platform section landing page scaffolding | Port skill; assign foss S-74 |
| G-016 | new-docs-index | `missing_skill` | aspose S-70; docs platform section landing page scaffolding | Port skill; assign foss S-75 |
| G-017 | new-reference-index | `missing_skill` | aspose S-71; reference platform section landing page scaffolding | Port skill; assign foss S-76 |
| G-018 | register-human-content | `missing_skill` | aspose S-66; onboards human-authored pages into registry | Port skill; assign foss S-71 |
| G-019 | page-retire | `missing_skill` | aspose S-83; retires obsolete content pages | Port skill; assign foss S-88 |

### 1e: Validation & Audit Skills (P1)

| Gap # | Slug | Gap Type | Evidence | Action |
|-------|------|---------|---------|--------|
| G-020 | code-smoke | `missing_skill` | aspose S-63; syntax/type-check Python code blocks | Port skill; assign foss S-68 |
| G-021 | link-validate | `missing_skill` | aspose S-65; cross-subdomain link validation | Port skill; assign foss S-70 |
| G-022 | coverage-reconcile | `missing_skill` | aspose S-80; knowledge unit disposition report | Port skill; assign foss S-85 |
| G-023 | knowledge-coverage-audit | `missing_skill` | aspose S-81; per-claim disposition table | Port skill; assign foss S-86 |
| G-024 | truth-audit-content | `missing_skill` | aspose S-85; line-level content truth audit | Port skill; assign foss S-90 |
| G-025 | publish-readiness-review | `missing_skill` | aspose S-90; agent-executed governed inspection | Port skill; assign foss S-95 |
| G-026 | plan-normalize | `missing_skill` | aspose S-91; execution-safe plan quality gate | Port skill; assign foss S-96 |
| G-027 | triage-confirm | `missing_skill` | aspose S-92; layer 2 body-prose staleness scanner | Port skill; assign foss S-97 |

### 1f: Repair & Remediation Skills (P1)

| Gap # | Slug | Gap Type | Evidence | Action |
|-------|------|---------|---------|--------|
| G-028 | evidence-repair | `missing_skill` | aspose S-72; repairs evidence frontmatter for blocked pages | Port skill; assign foss S-77 |
| G-029 | evidence-enhance | `missing_skill` | aspose S-78; improves evidence coverage on passing pages | Port skill; assign foss S-83 |
| G-030 | manual-edit | `missing_skill` | aspose S-73; operator-directed targeted content edit | Port skill; assign foss S-78 |
| G-031 | causal-backtrack | `missing_skill` | aspose S-74; resolves upstream dependency failures | Port skill; assign foss S-79 |
| G-032 | system-heal | `missing_skill` | aspose S-87; audit-driven content healing | Port skill; assign foss S-92 |
| G-033 | heal-batch | `missing_skill` | aspose S-89; batch healing from eval report | Port skill; assign foss S-94 |

### 1g: Session & Operations Skills (P1)

| Gap # | Slug | Gap Type | Evidence | Action |
|-------|------|---------|---------|--------|
| G-034 | session-start | `missing_skill` | aspose S-77; mandatory session initialization gate | Port skill; assign foss S-82 |
| G-035 | getting-started | `missing_skill` | aspose S-64; bootstraps repo environment from fresh clone | Port skill; assign foss S-69 |
| G-036 | commit | `missing_skill` | aspose S-76; stages and commits working tree | Port skill; adapt for foss (remove Hugo-specific steps); assign foss S-81 |
| G-037 | diagnose-skill-failure | `missing_skill` | aspose S-67; governed diagnostic procedure | Port skill; assign foss S-72 |
| G-038 | update-registry | `missing_skill` | aspose S-68; discovers and registers FOSS repos (different from foss discover-products) | Port skill; assign foss S-73 |
| G-039 | backlog | `missing_skill` | aspose S-88; unified planning & backlog management (22 subcommands) | Port skill; assign foss S-93 |

### 1h: Translation Skills (P3 — Heavy Infrastructure)

| Gap # | Slug | Gap Type | Evidence | Action |
|-------|------|---------|---------|--------|
| G-040 | translate-page | `missing_skill` + `missing_infra` | aspose S-52; backed by `scripts/translator/cli.py`; translator system absent in foss | Port translator scripts system + skill; assign foss S-64 |
| G-041 | translate-batch | `missing_skill` + `missing_infra` | aspose S-53; backed by translator system | Port skill; assign foss S-65 |

### 1i: Locale Skills (P3)

| Gap # | Slug | Gap Type | Evidence | Action |
|-------|------|---------|---------|--------|
| G-042 | locale-patch | `missing_skill` | aspose S-75; propagates text fixes to locale files | Port skill; assign foss S-80 |

---

## Section 2: Infrastructure Gaps (13 gaps)

| Gap # | Component | Gap Type | Evidence | Action |
|-------|-----------|---------|---------|--------|
| G-043 | GitHub CI workflows | `missing_ci` | `.github/` absent in foss; aspose has 4 workflows enforcing skill governance | Create `.github/workflows/skill-governance.yml` adapted for standalone use |
| G-044 | Git pre-commit hook | `missing_hooks` | `pre-commit-audit.sh` absent in foss; aspose runs validate_skills.py on every commit | Create `scripts/pre-commit-audit.sh` |
| G-045 | Git commit-msg hook | `missing_hooks` | `commit-msg-skills.sh` absent; aspose enforces skill provenance in commit messages | Create `scripts/commit-msg-skills.sh` |
| G-046 | Hook installer | `missing_hooks` | `install-hooks.sh` absent; no way for users to install hooks | Create `scripts/install-hooks.sh` |
| G-047 | Translator scripts | `missing_infra` | `scripts/translator/` absent; blocks translate-page + translate-batch | Port all translator modules from aspose |
| G-048 | no-downgrade-guard script | `missing_script` | `scripts/pipeline/no_downgrade_guard.py` in aspose; skill prompt exists in aspose but no foss equivalent | Port script; add to foss pipeline |
| G-049 | .agents/.kilocode sync | `missing_sync` | `sync_commands.py` only covers `.claude/commands/`; `.agents/` and `.kilocode/` drift silently | Create `scripts/sync_agents.py` |
| G-050 | knowledge-enrich script | `missing_script` | `scripts/pipeline/enrich.py` in aspose; needed for G-003 | Port enrich.py to foss |
| G-051 | gap-eval scripts | `missing_infra` | `scripts/gap-eval/run.py` (73KB) + 12 other files; needed for G-004 through G-006 | Port gap-eval system to `scripts/gap_eval/` |
| G-052 | RUNBOOK.md | `missing_docs` | `RUNBOOK.md` (303 lines) in aspose; foss has only QUICKSTART.md | Create `docs/RUNBOOK.md` adapted for standalone |
| G-053 | OPERATOR_GUIDE.md | `missing_docs` | `OPERATOR_GUIDE.md` (271 lines) in aspose; no equivalent in foss | Create `docs/OPERATOR_GUIDE.md` adapted for standalone |
| G-054 | Data directory | `missing_infra` | `data/families.json`, `products.json`, `platforms.json` in aspose; foss has `configs/families.yaml` only | Evaluate if foss skills need product/platform truth tables; add if required by ported skills |
| G-055 | SEO scripts | `missing_infra` | `scripts/seo/` in aspose; no skills depend on it directly | Low priority; add as optional module |

---

## Section 3: Governance Gaps (4 gaps)

| Gap # | Component | Gap Type | Evidence | Action |
|-------|-----------|---------|---------|--------|
| G-056 | Internal skill flag in registry | `missing_governance` | Registry YAML has no `internal:` field; aspose uses INTERNAL_SKILLS constant enforced by sync | Add `internal: true/false` to all 42 registry entries (TC-006) |
| G-057 | `_skill_constants.py` | `missing_governance` | No `INTERNAL_SKILLS` frozenset in foss; needed by validate_skills and CI checks | Create `scripts/_skill_constants.py` mirroring aspose pattern |
| G-058 | Internal skills excluded from .claude/commands | `missing_governance` | foss syncs ALL skills to .claude/commands including internal ones; aspose excludes internal | Update `sync_commands.py` to exclude skills with `internal: true` |
| G-059 | Commit skill provenance check | `missing_governance` | aspose CI enforces skill IDs in commit messages; foss has no such check | Add provenance check to GitHub workflow (G-043) |

---

## Section 4: ID Reassignment Issues (informational, not actionable gaps)

These are documentation issues, not gaps requiring code changes. They are resolved by `docs/id-mapping.md`.

| Issue | aspose | foss | Resolution |
|-------|--------|------|-----------|
| truth-audit ID differs | S-38 | S-47 | Accepted divergence; document in id-mapping.md |
| launch-product ID differs | S-49 | S-38 | Accepted divergence; document in id-mapping.md |
| content-eval ID differs | S-51 | S-48 | Accepted divergence; document in id-mapping.md |
| new-docs-page ID differs | S-56 | S-51 | Accepted divergence; document in id-mapping.md |
| new-blog-post ID differs | S-57 | S-52 | Accepted divergence; document in id-mapping.md |
| new-kb-howto ID differs | S-58 | S-53 | Accepted divergence; document in id-mapping.md |
| new-kb-faq ID differs | S-59 | S-54 | Accepted divergence; document in id-mapping.md |
| new-reference-page ID differs | S-60 | S-55 | Accepted divergence; document in id-mapping.md |
| knowledge-bootstrap ID differs | S-54 | S-49 | Accepted divergence; document in id-mapping.md |
| content-check ID differs | S-23 | S-50 | Accepted divergence; document in id-mapping.md |

---

## Priority Summary

| Priority | Count | Skills/Items |
|----------|-------|-------------|
| P1 — Critical (blocks workflows) | 25 gaps | G-001 to G-027, G-034 to G-039, G-043 to G-049, G-056 to G-059 |
| P2 — Generation (new page types) | 7 gaps | G-013 to G-019 |
| P3 — Heavy (infrastructure) | 3 gaps | G-040, G-041, G-042 |
| Low priority | 2 gaps | G-053 (OPERATOR_GUIDE), G-055 (SEO) |

---

## Execution Order Recommendation

Based on dependency analysis:

```
1. Governance first:  G-056, G-057, G-058 (TC-006) — enables all subsequent validation
2. Sync fix:          G-049 (TC-007) — closes silent drift
3. CI workflows:      G-043, G-059 (TC-010) — gates all future changes
4. Git hooks:         G-044, G-045, G-046 (TC-009)
5. Missing internal:  G-001, G-002 (TC-008, TC-011)
6. P1 skills:         G-003 to G-039 in batches (TC-012b, c, d, e, f, h)
7. Infrastructure:    G-047, G-050, G-051 (translator, enrich, gap-eval)
8. P2 skills:         G-013 to G-019 (TC-012a)
9. P3 skills:         G-040, G-041, G-042 (TC-012g, h)
10. Docs:             G-052, G-053 (TC-013)
```
