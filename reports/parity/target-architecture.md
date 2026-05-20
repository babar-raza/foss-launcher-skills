# Target Architecture — foss-launcher Parity Migration

**Generated**: 2026-05-15  **Agent**: A (Discovery)  **Plan**: PAR-012

## Design Principles

1. **Preserve behavior, redesign organization** — port semantics, not file structure
2. **Rationalize CI checks** — group by domain rather than copying 63 individual scripts
3. **Complement AGENTS.md** — new governance docs extend, not duplicate
4. **Follow foss conventions** — new libraries follow existing scripts/pipeline/ patterns
5. **Incremental + reversible** — every TC is one PR-equivalent unit, rollback defined

## Gap Category Design Decisions

### GC1: Missing CI Checks (59 checks → ~20 rationalized modules)

| Domain | Count | Approach |
|--------|-------|----------|
| skill_governance | 14 | Extend scripts/validate_skills.py with new checks |
| pipeline_integrity | 7 | New scripts/ci/check_pipeline_integrity.py |
| content_quality | 6 | New scripts/ci/check_content_quality.py |
| metrics | 6 | New scripts/ci/check_metrics.py |
| provenance | 5 | New scripts/ci/check_provenance.py |
| other | 19 | Group into scripts/ci/check_misc.py or individual files |
| knowledge | 3 | New scripts/ci/check_knowledge.py |
| locale | 1 | Add to existing scripts/ci/ |
| link_integrity | 1 | New scripts/ci/check_links.py |
| blog | 1 | Skip (blog-specific, aspose.org-only concern) |

**Priority order**: skill_governance > content_quality > pipeline_integrity > provenance > knowledge > metrics

### GC2: Missing Governance Docs (22 docs → docs/governance/ + docs/workflows/)

Create external governance directory structure mirroring aspose.org.
Adapt content for standalone repo (remove Hugo/website-specific references).

Priority docs to port first:
1. evidence governance (precondition for content work)
2. write boundaries (safety)
3. launch gates (product launch safety)
4. skill chains (workflow understanding)
5. heal policy (remediation guidance)

### GC3: Missing Backing Scripts (58 governance_only + 2 documented_not_implemented)

60 foss-launcher skills have no backing script.
Design approach: Add scripts incrementally, highest-value skills first.

Priority scripts (by skill usage frequency and impact):
- knowledge-diff, stale-detect, page-plan, page-draft, page-update, page-enhance
- cross-platform, content-audit improvements
- gap-eval family (gap-plan, gap-apply, gap-report)

### GC4: Size Divergence (52 skills where foss file < 70% aspose size)

For each diverged skill: compare content section by section.
Add missing sections, examples, and edge case documentation.
Do NOT bloat — only add content present in aspose.org that is genuinely useful.

### GC5: Missing Test Coverage (59 skills with no test file)

Add test files for the 22 skills that have scripts (implemented_not_verified).
For governance_only skills, add smoke tests that verify skill files parse correctly.

### GC6: Missing Shared Libraries (scripts/pipeline/lib/)

aspose.org has 19 shared modules. Create scripts/pipeline/lib/ directory.
Port the 8-10 most-needed modules based on what skills reference them.

### GC7: Missing Skill Files (2 skills)

- `blog-migrate`: Evaluate relevance to standalone repo. If relevant, port content.
- `pipeline-harden`: Highly relevant to standalone repo maintenance. Port with adaptation.

## Implementation Wave Order

| Wave | Domain | Taskcards | Rationale |
|------|---------|-----------|-----------|
| W1 | Safety + config | CF-*, VF-SAFETY | Foundation; no skill deps |
| W2 | Registry + ID mapping | RG-* | Foundation for all other work |
| W3 | Governance docs | GV-* | Conceptual foundation |
| W4 | Library stubs | LB-* | Required by script work |
| W5 | CI checks (skill_governance) | CI-001..CI-014 | Highest value, validates everything |
| W6 | Backing scripts | SC-* | Core implementation |
| W7 | Skill content updates | SK-* | Content improvements |
| W8 | CI checks (other domains) | CI-015..CI-063 | Remaining validation |
| W9 | Test coverage | TS-* | Verification layer |
| W10 | Verification + closure | VF-*, DC-* | Final sign-off |