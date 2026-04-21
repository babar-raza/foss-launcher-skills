# Closure Report — Skill Parity Program

**Program:** foss-launcher-skills-gitlab ↔ aspose.org capability parity
**Closed:** 2026-04-20
**Status:** COMPLETE

---

## 1. What Was the Goal

Bring `foss-launcher-skills-gitlab` to full capability parity with the embedded skills system
in `aspose.org`, without modifying aspose.org and without regressing foss-launcher's unique
advantages. The scope covered skills, infrastructure, governance, and documentation.

---

## 2. What Matched (Group A — Present in Both)

35 skills existed in both repositories by name. Most had different S-XX IDs due to independent
ID assignment after approximately S-42. All Group A skills are present in foss-launcher and
the ID cross-reference is documented in `docs/id-mapping.md`.

Key overlaps verified:
- Core knowledge pipeline: knowledge-diff (S-12), knowledge-update (S-14), embed-knowledge (S-15)
- Content generation: page-draft (S-19), page-update (S-20), page-enhance (S-21), faq-generate (S-22)
- Quality gates: eval-page (S-25), heal-page (S-26), content-audit (S-32)
- Orchestration: batch-remediate (S-40), batch-eval-fix (S-41), launch-product (S-38)
- All new-* page generators: new-docs-page, new-blog-post, new-kb-howto, new-kb-faq, new-reference-page

---

## 3. What Was Missing (Group B — Ported in This Program)

42 skills were absent from foss-launcher at program start. All 42 have been migrated.

### By category:

**Content Generation (5 skills):**
new-products-page (S-66), batch-reference (S-67), new-kb-index (S-74), new-docs-index (S-75), new-reference-index (S-76)

**Operational/Workflow (6 skills):**
code-smoke (S-68), getting-started (S-69), diagnose-skill-failure (S-72), update-registry (S-73), commit (S-81), session-start (S-82)

**Repair/Remediation (7 skills):**
evidence-repair (S-77), manual-edit (S-78), causal-backtrack (S-79), evidence-enhance (S-83), page-retire (S-88), heal-batch (S-94), triage-confirm (S-97)

**Quality/Audit (6 skills):**
link-validate (S-70), coverage-reconcile (S-85), knowledge-coverage-audit (S-86), truth-audit-content (S-90), publish-readiness-review (S-95), plan-normalize (S-96)

**Orchestration/Pipeline (9 skills):**
site-plan (S-57), family-sync (S-58), refresh-product-page (S-59), launch-rollback (S-60), register-human-content (S-71), refresh-product (S-84), delta-site-plan (S-87), system-heal (S-93), backlog (S-98)

**Knowledge/Gap-Eval (5 skills):**
knowledge-enrich (S-61), gap-eval (S-62), gap-plan (S-63), gap-report (S-64), gap-apply (S-65)

**Translation (2 skills — prompt-only, backend absent):**
translate-page (S-99), translate-batch (S-100)
> Note: Skill prompt files are present and registered. The `scripts/translator/` backend package was not ported. Skills display a backend-requirement notice. Full translation functionality requires a separate backend integration step.

**Locale (1 skill):**
locale-patch (S-101)

**Internal guard (1 skill):**
no-downgrade-guard (S-56, internal: true)

---

## 4. What Was Improved (Group D — foss-launcher Advantages Preserved)

These foss-launcher capabilities were NOT in aspose.org and were preserved without regression:

| Capability | foss advantage |
|-----------|---------------|
| Evidence pipeline | S-43→S-44→S-45→S-46 chain (no equivalent in aspose) |
| Content evaluation | 16 evaluators + 8 auto-fixers vs aspose's simpler eval |
| Artifact schema validation | 6 JSON schemas in `configs/schemas/` |
| Test organization | 28→30 dedicated test files, 442→487 passing tests |
| YAML registry | More readable than aspose's JSON registry |
| Installation scripts | `install.sh` + `install.ps1` |
| corpus-scan (S-37) | Different from aspose's knowledge-enrich; golden corpus approach preserved |
| truth-sync (S-30), discover-products (S-39) | foss-unique; retained as-is |

---

## 5. Infrastructure Additions

| Component | Before | After |
|-----------|--------|-------|
| Skill mirrors synced | `.claude/commands/` only | All 3 mirrors (`.claude/`, `.agents/`, `.kilocode/`) |
| Internal skill enforcement | No flag; all skills in commands/ | `internal:` field in registry; 7 internals excluded from commands/ |
| Pre-write guard | No script | `scripts/pipeline/no_downgrade_guard.py` (26 unit tests) |
| Git hooks | None | `pre-commit-audit.sh`, `commit-msg-skills.sh`, `install-hooks.sh` |
| CI workflow | None | `.github/workflows/skill-governance.yml` |
| INTERNAL_SKILLS constant | Not defined | `scripts/_skill_constants.py` |
| Operator docs | None | `docs/RUNBOOK.md` |
| ID cross-reference | None | `docs/id-mapping.md` |
| Parity artifacts | None | `docs/parity/` (6 documents) |

---

## 6. What Remains Unresolved

| Item | Reason not addressed | Risk |
|------|---------------------|------|
| Translator backends (`scripts/translator/`) | Large external-dependency system (Ollama, M2M100); skills S-99/S-100 are ported as prompt skills; backend scripts require separate integration effort | LOW — skills are usable with any LLM backend |
| SEO scripts (`scripts/seo/`) | No skill in either repo directly depends on them; purely operational tooling | LOW |
| Gap-eval CI workflow | aspose's `gap-eval-consistency.yml` is Hugo-specific; foss equivalent would need different content path assumptions | LOW |
| Group A behavioral diffs | 35 same-name skills are UNVERIFIED — deeper comparison not done | MEDIUM — future program item |
| RUNBOOK.md operator guide | Written in `docs/RUNBOOK.md`; not yet reviewed by operator | LOW |

---

## 7. Verification Proof

Full verification log: [`docs/parity/verification-log.md`](verification-log.md)

Summary of results:
- Registry: **PASS** (84 skills, 7 internal, no violations)
- Mirror sync: **PASS** (all 3 mirrors in sync)
- Test suite: **487 passed, 0 failed**
- Internal skills governance: **PASS** (7 skills excluded from commands/)
- Safety check: **PASS** (aspose.org working tree clean throughout)

---

## 8. Metrics

| Metric | Before | After | Delta |
|--------|--------|-------|-------|
| User-callable skills | 42 | 77 | +35 |
| Internal skills | 0 (no flag) | 7 | +7 |
| Total registered skills | 42 | 84 | +42 |
| Mirror directories synced | 1 | 3 | +2 |
| Test files | 28 | 30 | +2 |
| Tests passing | 442 | 487 | +45 |
| Infrastructure scripts added | 0 | 6 | +6 |
| Documentation files added | 0 | 8 | +8 |

---

## 9. Decisions Made During Program

| Decision | Rationale |
|----------|-----------|
| New foss IDs start at S-56, not copying aspose IDs | Prevents collisions; foss has its own ID space after divergence |
| Gap-eval pipeline ported alongside evidence pipeline | Both pipelines serve different workflows; they coexist |
| Translator skills ported as prompt skills | Backend scripts are a separate integration; core skill behavior is captured |
| Internal skills excluded from `.claude/commands/` | Matches aspose governance intent; prevents operator confusion |
| SEO scripts deferred | No skill dependency; low priority |
| aspose.org never touched | Read-only constraint met throughout |
