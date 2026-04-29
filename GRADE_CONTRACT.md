# GRADE_CONTRACT.md — Content Quality Grade System Contract

Version: 1.1
Effective: 2026-04-24
Status: FROZEN (schema and canonical model)

This document defines the frozen, stable elements of the content grading system.
Changes to any frozen item require a contract version bump, a documented migration
plan, and explicit maintainer approval.

---

## 1. Grade Letter Semantics

| Grade | Definition |
|-------|-----------|
| **A** | 0 FAIL findings, 0-2 WARN findings across canonical dimensions |
| **B** | 0 FAIL findings, 3-5 WARN findings |
| **C** | 1-2 FAIL findings; OR 0 FAIL + 6+ WARN findings |
| **D** | 3-5 FAIL findings |
| **F** | 6+ FAIL findings; OR any Safety FAIL (critical category override) |

Finding levels: FAIL (blocking quality issue), WARN (notable concern),
INFO (informational, no grade impact).

**This scale is frozen.** The thresholds (FAIL/WARN counts per letter) do not
change without a contract version bump.

---

## 2. Critical Category Rules

Any FAIL finding in a critical category forces grade F immediately,
regardless of other findings.

| Category code | Evaluator | Description |
|---------------|-----------|-------------|
| **FC** | forbidden_claims | Text matching known false or forbidden claims |
| **PC** | platform_purity | Wrong-language code or prose contamination |
| **TA** | type_accuracy | Type annotation mismatches in reference pages |

**This rule is frozen.** Adding or removing a critical category requires a
contract version bump.

---

## 3. Category Ceiling Structure

Category ceilings cap the final grade when specific evaluators produce findings
at specified levels. The ceiling pattern is frozen; individual ceiling values
may be adjusted within the evaluator change protocol (AGENTS.md section 9a).

| Category | Levels | Ceiling | Evaluator |
|----------|--------|---------|-----------|
| TA | WARN, FAIL | C | type_accuracy |
| FT | FAIL | C | format_truth |
| CP | FAIL | B | code_plausibility |
| NC | FAIL | C | namespace_correctness |
| SX | FAIL | C | code_syntax_check |
| AC | FAIL | B | api_completeness |
| FM | FAIL | C | format_completeness |
| MV | FAIL | C | member_validity |
| DC | FAIL | C | description_completeness |
| CB | FAIL | C | code_block_api |
| DL | FAIL | C | dead_internal_link |
| VC | WARN, FAIL | C | version_claim_check |
| CF | WARN, FAIL | C | capability_claim_check |
| SG | WARN | C | api_accuracy (signature) |
| US | WARN | B | consumer_usefulness |

---

## 4. Canonical Frontmatter Schema

Only these fields belong in .md file frontmatter for grading:

| Field | Type | Purpose |
|-------|------|---------|
| `grade` | A-F letter | Publication readiness tier |
| `grade_reasons` | YAML list of strings | Human-readable failure descriptions with evaluator attribution |
| `graded_content_hash` | 32-char hex string | SHA-256 prefix of normalized body content for skip-graded gate |

All other grade-related fields (graded_model_sha, graded_evaluators,
graded_logic_version, graded_evaluator_versions, graded_enrichment_status,
grade_final, grade_stale_reason, grade_stale_targets) are operational
pipeline state. They will move to the external grade manifest (Phase 2)
and must not be added to new frontmatter writes after ARCH-04 lands.

The `CANONICAL_FRONTMATTER_FIELDS` constant in `grade_writer.py` enforces
this schema programmatically.

**This schema is frozen** (3 fields). Adding a new field requires:
(a) documented human-value justification, (b) contract version bump,
(c) maintainer approval.

---

## 5. Frontmatter Write Policy

Frontmatter grade fields are updated ONLY when:
1. Page has no grade (first grading)
2. Page body content changed AND the new canonical grade letter differs
   from the stored grade
3. The grade crossed a letter boundary (any direction) under approved conditions

Frontmatter MUST NOT be updated when:
- Only ELV or evaluator versions changed (operational state only)
- Grade letter is unchanged even if body changed
- A diagnostic/experimental evaluator finding changed
- Grading was run for reporting purposes without healing

Enforced by `_should_write_canonical_grade()` in grade_writer.py (WP-01).
CLI flag: `--write-grade-if-policy-met` (default) vs `--write-grade-force`.

---

## 6. Evaluator Governance

### Canonical vs Experimental

Evaluators are classified as **canonical** (affect the frontmatter grade)
or **experimental** (run for diagnostics only, appear in manifest/reports
but do not change the canonical grade letter).

The EXPERIMENTAL_EVALUATORS set is defined in `content_eval/config.py` (FREEZE-02 evaluator stability audit completed 2026-04-24).

### Graduation Policy

Moving an evaluator from experimental to canonical requires:
1. Stability period: evaluator unchanged for 14+ days
2. Corpus-wide validation run with documented results
3. Explicit maintainer sign-off

### ELV Bump Rules

EVALUATOR_LOGIC_VERSION bumps are suspended except for:
- Confirmed false results (wrong FAIL or wrong PASS) on real pages
- Safety defects in a canonical evaluator
- One-time canonical migration when Grade Contract items are formally updated

See AGENTS.md section 9a for the full evaluator change checklist.

---

## 7. Backward Compatibility Policy

### What requires a contract version bump
- Changing the A-F grade letter thresholds (section 1)
- Adding or removing a critical category (section 2)
- Adding a new field to canonical frontmatter (section 4)
- Moving an evaluator between canonical and experimental tiers
- Changing the write policy rules (section 5)

### What does NOT require a contract version bump
- Adjusting individual evaluator thresholds within existing FAIL/WARN levels
- Adding a new evaluator to the experimental set
- Modifying category ceiling values (section 3)
- Manifest schema changes (operational, not canonical)
- Changes to the grade_reasons format (as long as evaluator attribution is preserved)

---

## 8. Change Protocol

To modify a frozen item:
1. Document the proposed change and its justification
2. Assess impact on existing grades across the corpus
3. Create a migration plan if grade distribution will shift
4. Obtain maintainer approval
5. Bump contract version (this file's version number)
6. Update AGENTS.md section 9a if governance rules change
7. Execute migration per the bulk migration annotation protocol (DEC-06)

---

## Changelog

### v1.1 (2026-04-24)
- Removed `graded_at` from canonical frontmatter schema (§4). `graded_at` is operational
  state; it belongs in the external grade manifest only. Aligns with the D-1 code fix
  (2026-04-23) which removed `graded_at` from `CANONICAL_FRONTMATTER_FIELDS` in
  `grade_writer.py`. Non-breaking: the runtime was already not writing `graded_at`.
- Hard-freeze governance declared (Part 21). `EVALUATOR_FREEZE_VERSION = "16"` activated
  in `content_eval/__init__.py`.

### v1.1 amendment (2026-04-24, same day - post-freeze ELV bump)
- ELV bumped 16->17 for encoding_check addition. EVALUATOR_FREEZE_VERSION updated to "17". Current frozen baseline: EVALUATOR_FREEZE_VERSION = "17".

### v1.0 (2026-04-21)
- Initial frozen version.

---

## References

- Governing plan: curried-pondering-music.md (FINAL ARCHITECTURE Sections 6, 7, 8.6, 9)
- Implementation: scripts/pipeline/lib/grade_writer.py (CANONICAL_FRONTMATTER_FIELDS, WP-01)
- Grade computation: scripts/pipeline/content_eval/models.py
- Configuration: scripts/pipeline/content_eval/grade_config.yaml
- Evaluator change checklist: AGENTS.md section 9a

---

## 9. Post-Freeze Change Protocol (FREEZE-05)

### Allowed Changes (No Contract Version Bump)
- Threshold adjustments within experimental evaluators
- Adding new evaluators to EXPERIMENTAL_EVALUATORS
- Bug fixes in experimental evaluators
- Documentation clarifications

### Changes Requiring Contract Version Bump
- Moving an evaluator from experimental to canonical (graduation)
- Changing grade letter semantics (A-F definitions)
- Changing critical category rules (FC/PC/TA → F)
- Adding or removing canonical frontmatter fields
- Modifying the canonical grade formula

### Emergency Fix Protocol
- **When:** A canonical evaluator produces confirmed false results (wrong FAIL/PASS) on real pages
- **Process:**
  1. File documented issue citing affected pages
  2. Fix evaluator
  3. Bump ELV with EVALUATOR_FREEZE_VERSION update
  4. Document in MIGRATION_LOG.md
  5. Re-evaluate affected pages only
- **Timeline:** Same-day for safety defects; 48h for accuracy defects

### Evaluator Graduation Protocol
- **Prerequisite:** ≥14 days in EXPERIMENTAL_EVALUATORS with stable results
- **Evidence:** Corpus-wide validation run showing FP rate <10%
- **Approval:** Explicit maintainer sign-off
- **Execution:** Add to CANONICAL_EVALUATORS in config.py, update GRADE_CONTRACT.md version, bump ELV

### Contract Versioning
- **Current version:** 1.1
- **Minor version (1.x):** non-breaking changes (new experimental evaluator, threshold tweak)
- **Major version (2.0+):** breaking changes (grade semantics, canonical evaluator set, frontmatter schema)
