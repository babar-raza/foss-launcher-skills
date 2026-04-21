# Normalized Skill Inventory — foss-launcher-skills-gitlab

**Repository:** `C:\Users\prora\OneDrive\Documents\GitHub\foss-launcher-skills-gitlab`
**Registry:** `skills/registry.yaml` (YAML, schema v1)
**Total skills:** 42 (no internal/external designation in registry)
**ID range:** S-01 to S-55 with gaps (S-02–09, S-11, S-16, S-28–29, S-32-gap, S-50 unassigned)
**Evidence date:** 2026-04-20

---

## De-facto Internal Skills (should be marked)

These skills behave as internal auto-invoked routines but lack `internal: true` in the registry.
This is a governance gap relative to aspose.org.

| foss ID | Slug | Reason for internal flag |
|---------|------|--------------------------|
| S-01 | path-guard | Enforced automatically on every write |
| S-10 | project-phase-store | Checkpoint infrastructure |
| S-17 | rubric-align | Sub-evaluator called by eval-page |
| S-24 | evidence-cite | Auto-invoked by generation skills |
| S-33 | change-guard | Auto-invoked before writes |
| S-49 | knowledge-bootstrap | Auto-invoked pre-condition gate |

Missing from foss-launcher entirely: `no-downgrade-guard` (aspose S-55 internal).

---

## Full Skill Registry (42 skills)

All scripts confirmed to exist on disk as of evidence date.

| foss ID | Slug | Description | Script |
|---------|------|-------------|--------|
| S-01 | path-guard | Enforce allowed write paths | `scripts/path_guard.py` ✓ |
| S-10 | project-phase-store | Record page creation intent as a YAML plan file | — |
| S-12 | knowledge-diff | Detect upstream repo changes since last knowledge extraction | — |
| S-13 | stale-detect | Identify content pages affected by upstream changes | — |
| S-14 | knowledge-update | Refresh knowledge model from source repo | `scripts/pipeline/refresh_knowledge.py` ✓ |
| S-15 | embed-knowledge | Generate vector embeddings for knowledge retrieval | `scripts/embed.py` ✓ |
| S-17 | rubric-align | Align content to quality rubric and identify gaps | — |
| S-18 | page-plan | Plan page structure before drafting | — |
| S-19 | page-draft | Draft initial page content from knowledge model | — |
| S-20 | page-update | Update page after knowledge model change | — |
| S-21 | page-enhance | Enhance page quality to meet rubric bar | — |
| S-22 | faq-generate | Generate FAQ section from knowledge model | — |
| S-23 | ground-check | Pre-write evidence verification gate | `scripts/pipeline/audit.py` ✓ |
| S-24 | evidence-cite | Attach evidence citations to content frontmatter | `scripts/pipeline/attach_evidence.py` ✓ |
| S-25 | eval-page | Evaluate page quality and assign A-F grade | `scripts/pipeline/content_eval/__main__.py` ✓ |
| S-26 | heal-page | Fix low-quality page to reach passing grade | — |
| S-30 | truth-sync | Import external FOSS-Launcher knowledge into fl/ | — |
| S-31 | truth-index | Generate knowledge index from merged artifacts | `scripts/index.py` ✓ |
| S-32 | content-audit | Semantic knowledge verification of content pages | `scripts/pipeline/content_audit.py` ✓ |
| S-33 | change-guard | Pre-write knowledge gate for single text blocks | `scripts/pipeline/change_guard.py` ✓ |
| S-34 | repo-scout | Extract API truth from FOSS repository | `scripts/scout.py` ✓ |
| S-35 | truth-merge | Merge scout and external knowledge sources | `scripts/merge.py` ✓ |
| S-36 | cross-platform | Family-wide consistency check across platforms | — |
| S-37 | corpus-scan | Build golden corpus profile for a site type | `scripts/corpus_scan.py` ✓ |
| S-38 | launch-product | Orchestrate full FOSS product launch end-to-end | — |
| S-39 | discover-products | Scan GitHub org to discover FOSS product repos | `scripts/discover.py` ✓ |
| S-40 | batch-remediate | Full eval-to-fix-to-LLM-to-re-eval remediation pipeline | `scripts/pipeline/remediate.py` ✓ |
| S-41 | batch-eval-fix | Quick eval plus deterministic auto-fix only (no LLM) | `scripts/pipeline/remediate.py` ✓ |
| S-42 | category-fix | Run specific fixer on targeted files by category | `scripts/pipeline/remediate.py` ✓ |
| S-43 | evidence-decide | Determine per-page content action from evidence | `scripts/decide.py` ✓ |
| S-44 | evidence-materialize | Build canonical Product Evidence File from merged knowledge | `scripts/materialize.py` ✓ |
| S-45 | mental-model | Build product mental model and capability tiers from PEF | `scripts/mental_model.py` ✓ |
| S-46 | evidence-verify | Deterministic content verification against PEF | `scripts/verify.py` ✓ |
| S-47 | truth-audit | Member-level API verification against knowledge surface | — |
| S-48 | content-eval | Multi-dimensional content evaluation against repo truth | `scripts/pipeline/content_eval/__main__.py` ✓ |
| S-49 | knowledge-bootstrap | Shared pre-condition gate for knowledge state detection | — |
| S-50 | content-check | Structural and quality check on a content file pre-commit | — |
| S-51 | new-docs-page | Generate a new documentation page for docs.aspose.org | — |
| S-52 | new-blog-post | Generate a new blog post for blog.aspose.org | — |
| S-53 | new-kb-howto | Generate a new KB how-to article for kb.aspose.org | — |
| S-54 | new-kb-faq | Generate or update the FAQ page for a product platform | — |
| S-55 | new-reference-page | Generate a new API reference page for reference.aspose.org | — |

---

## Capabilities Unique to foss-launcher (not in aspose.org)

These capabilities should be preserved and not regressed during migration:

| Slug/Component | Description | Why Better |
|----------------|-------------|------------|
| truth-sync (S-30) | Import external knowledge into fl/ subdirectory | No aspose equivalent |
| discover-products (S-39) | GitHub org scanner for FOSS repo discovery | aspose has update-registry (S-68) but different approach |
| evidence-decide (S-43) | Per-page content action engine from PEF | Systematic evidence-driven workflow not in aspose |
| evidence-materialize (S-44) | Canonical Product Evidence File builder | aspose has no PEF concept |
| mental-model (S-45) | Capability tier + gap analysis from PEF | aspose has no mental-model skill |
| evidence-verify (S-46) | Deterministic PEF-grounded verification | More systematic than aspose's gap-eval |
| corpus-scan (S-37) | Golden corpus profile for style anchoring | Different purpose from aspose's knowledge-enrich |
| ground-check (S-23) | Evidence verification gate (vs aspose's structural check) | Foss split content-check into evidence + structure |
| content-check (S-50) | Structural pre-commit check | Same purpose as aspose S-23 but foss distinguishes better |
| content_eval module | 16 evaluators + 8 auto-fixers | Richer than aspose's evaluation |
| configs/schemas/ | 6 JSON schemas for artifact validation | aspose has no schema validation |
| install.sh + install.ps1 | Cross-platform installers | aspose has no installer |
| CODEX.md | Codex CLI agent instructions | aspose has no CODEX.md |
| QUICKSTART.md | Standalone operator onboarding | aspose has no QUICKSTART |
| .pylibs/ | Bundled Python deps (tree-sitter, etc.) | aspose relies on venv convention only |
| pytest.ini + tests/ | Well-organized standalone test suite | 28 files vs aspose's scattered tests |

---

## Infrastructure Summary

| Component | Present | Path / Notes |
|-----------|---------|------|
| Skill registry | YES | `skills/registry.yaml` (YAML — better than JSON) |
| Sync scripts | PARTIAL | `scripts/sync_commands.py` syncs only `.claude/commands/`; `.agents/` and `.kilocode/` NOT synced |
| .claude/commands mirror | YES | 42 files |
| .agents/skills mirror | YES | 42 directories (manually maintained — no auto-sync) |
| .kilocode/skills mirror | YES | 42 directories (manually maintained — no auto-sync) |
| Internal skill constant | NO | No `_skill_constants.py`; registry lacks `internal:` field |
| GitHub CI workflows | NO | `.github/` directory absent |
| Git hooks | NO | No hook scripts |
| Hook installer | NO | Absent |
| Translator system | NO | Absent; translate-page/translate-batch skills absent |
| Gap-eval system | NO | Replaced by evidence pipeline (different approach) |
| SEO scripts | NO | Absent |
| CI validation scripts | PARTIAL | 4 scripts only (validate_skills, sync_commands, readme_sync, check_setup) |
| Data directory | NO | Only `configs/families.yaml`; no products.json, platforms.json |
| RUNBOOK.md | NO | Absent |
| OPERATOR_GUIDE.md | NO | Absent |
| Tests | YES | 28 test files in `tests/` + fixtures (better organized than aspose.org) |
| Schema validation | YES | `configs/schemas/*.json` (6 schemas — unique to foss) |
| Evidence pipeline | YES | `scripts/decide.py`, `materialize.py`, `verify.py`, `mental_model.py` |
| Install scripts | YES | `install.sh`, `install.ps1` |

---

## Key Structural Notes

1. **ID collisions resolved in registry header:**
   - S-38 collision: `launch-product` keeps S-38; `truth-audit` renumbered to S-47
   - S-42 collision: `category-fix` keeps S-42; `evidence-verify` renumbered to S-46

2. **Stale frontmatter IDs:** `truth-audit.md` has `id: S-38` in frontmatter (stale); registry YAML is authoritative

3. **evidence-verify.md** has `id: S-42` in frontmatter (stale); registry correctly assigns S-46

4. **All 18 script paths** in registry confirmed to exist on disk

---

## Confidence Notes

- Registry data: HIGH (read directly from `skills/registry.yaml`)
- Script existence: HIGH (all 18 confirmed present)
- Internal skill inference: MEDIUM (inferred from aspose pattern; not formally declared in foss)
- Skill content quality: MEDIUM (first 40 lines read for 18 skills; others confirmed by file list)
