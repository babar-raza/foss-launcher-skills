# GRADE_CONTRACT.md — Content Quality Grade System Contract

Version: 1.3
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
| EG | WARN | B | evidence_depth (EG_GROUNDING) |

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

### v1.3 (2026-09-10)
- New §10 "Safety-Override Findings" (FREEZE-06): a lighter-than-full-graduation
  process for a small, explicit `(evaluator, category)` allowlist
  (`content_eval/config.py`'s `SAFETY_OVERRIDE_FINDINGS`) letting specific
  FAIL-only, deterministic, already-tested findings from an EXPERIMENTAL
  evaluator affect grade computation. First (and currently only) use:
  `install_recipe`'s `IR_PUBLISH_CLAIM`/`IR_UNPUBLISHED_DISCLOSURE` (split out
  of its previously-shared `"IR"` category), closing a real gap where 89 live
  `PUBLISH-CLAIM-CONTRADICTION-001` findings were invisible to grade despite
  the evaluator running in every eval pass. `content_eval/models.py` gained a
  shared `_is_grade_eligible(f)` helper (replacing 2 independent inline
  `CANONICAL_EVALUATORS` filters). Both new categories added to
  `grade_config.yaml`'s `critical_categories`. ELV bumped 18->19,
  `EVALUATOR_FREEZE_VERSION` updated to `"19"`. Current frozen baseline:
  EVALUATOR_FREEZE_VERSION = 19. See §10 for the full mechanism, eligibility
  bar for future additions, and an explicit honesty note that this section's
  own process is this change's proposal, not a pre-existing maintainer-
  approved pattern.
- Fixed a stale "Current version: 1.1" note under old §9's own Contract
  Versioning subsection (had not been updated since the v1.2 entry below
  landed on 2026-08-07 — found while editing this file for the above).

### v1.2 (2026-08-07)
- Evaluator graduation: `evidence_depth` moved from `EXPERIMENTAL_EVALUATORS` to
  `CANONICAL_EVALUATORS` (TC-SFH-003, 2026-07-14) per the §6 Graduation Policy and §9
  Evaluator Graduation Protocol. Added the `EG` (`EG_GROUNDING`) category ceiling row to §3
  (WARN → B, per `grade_config.yaml`). This graduation happened in code on 2026-07-14 but was
  never logged here until now — the gap was found by `root_docs_checks.py`'s
  `check_grade_contract_sync` (S-121), which compares this document's stated frozen baseline
  against the live `content_eval/__init__.py` constant on every `/root-docs-refresh` run.
- ELV bumped 17->18 to reflect the `evidence_depth` graduation. `EVALUATOR_FREEZE_VERSION`
  updated to `"18"` (superseded by the v1.3 entry above — kept here only as historical
  record, not a current baseline claim).

### v1.1 (2026-04-24)
- Removed `graded_at` from canonical frontmatter schema (§4). `graded_at` is operational
  state; it belongs in the external grade manifest only. Aligns with the D-1 code fix
  (2026-04-23) which removed `graded_at` from `CANONICAL_FRONTMATTER_FIELDS` in
  `grade_writer.py`. Non-breaking: the runtime was already not writing `graded_at`.
- Hard-freeze governance declared (Part 21). `EVALUATOR_FREEZE_VERSION = "16"` activated
  in `content_eval/__init__.py`.

### v1.1 amendment (2026-04-24, same day - post-freeze ELV bump)
- ELV bumped 16->17 for encoding_check addition. EVALUATOR_FREEZE_VERSION updated to "17"
  (superseded by the v1.2 entry above — kept here only as historical record, not a current
  baseline claim).

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
- **Current version:** 1.3 (was stale at "1.1" here despite the top-of-file header
  and Changelog already showing 1.2 as of the 2026-08-07 evaluator-graduation entry --
  fixed in the same pass that added §10, PKGINSTALL-GRADE-SAFETY-OVERRIDE, 2026-09-10)
- **Minor version (1.x):** non-breaking changes (new experimental evaluator, threshold tweak)
- **Major version (2.0+):** breaking changes (grade semantics, canonical evaluator set, frontmatter schema)

---

## 10. Safety-Override Findings (FREEZE-06)

### Purpose

A narrow, explicit mechanism for a small number of FAIL-only, deterministic,
already-tested findings from an EXPERIMENTAL evaluator to affect grade
computation, without that evaluator undergoing full graduation to
CANONICAL_EVALUATORS. Exists because full graduation and "affects nothing until
graduated" are not the only two positions on the spectrum -- an evaluator can be
EXPERIMENTAL overall (its other checks still unvetted, still noisy, still
correctly excluded from grade) while carrying one or two specific checks that
are already safety-critical, already tested, and already known not to be noisy.

### Origin

`install_recipe` has been in `EXPERIMENTAL_EVALUATORS` since 2026-04-24. Its
`_verify_publish_channel_claims` check (RC-W1-003) was added 2026-08-14 --
four months later -- to catch pages that falsely claim a package is published
when `data/package_registry.json` records `verification.published: false`.
Because `content_eval/models.py`'s `grade_reasons()` and
`compute_grade_with_criticality()` both filtered to
`f.evaluator in CANONICAL_EVALUATORS` before any category/criticality logic
ran, every FAIL from this check was discarded before grade computation ever
saw it -- confirmed live, 2026-09-10: 89 real findings (backlog/BACKLOG.md
row `PUBLISH-CLAIM-CONTRADICTION-001`, 9 products) existed on pages carrying a
stored `grade: A`. No process step existed that asked "does a new FAIL-level
check added to an experimental evaluator need to bypass this filter" -- this
section exists so that question now has a documented answer with a real
process behind it, not just a one-off code change.

### Mechanism

- `content_eval/config.py` defines `SAFETY_OVERRIDE_FINDINGS: frozenset[tuple[str, str]]`,
  an explicit `(evaluator_name, category)` allowlist.
- `content_eval/models.py`'s `_is_grade_eligible(f)` is the single shared
  choke point both `grade_reasons()` and `compute_grade_with_criticality()`
  call: a finding is grade-eligible if its evaluator is canonical, **or** if
  `f.level == "FAIL"` and `(f.evaluator, f.category)` is in
  `SAFETY_OVERRIDE_FINDINGS`.
- `install_recipe.py`'s single, shared `"IR"` category was split so the two
  safety checks get their own codes (`IR_PUBLISH_CLAIM`,
  `IR_UNPUBLISHED_DISCLOSURE`), leaving `_verify_install_accuracy`'s own,
  noisier `"IR"` findings untouched and still excluded from grade (this
  evaluator's other checks remain fully experimental).
- Both new categories are added to `grade_config.yaml`'s `critical_categories`
  (any FAIL forces grade F), matching `FC`/`PC`/`TA`'s existing treatment.

### Eligibility bar for adding a NEW entry to SAFETY_OVERRIDE_FINDINGS

All of the following must hold -- this is deliberately a **lighter** process
than full evaluator graduation (§6/§9's Evaluator Graduation Protocol), not an
equivalent one, because it governs 1-2 already-scoped checks, not an
evaluator's entire noise profile:

1. **FAIL-only.** WARN-level findings from the same evaluator are never
   included -- this mechanism cannot be used to let a noisy WARN check
   silently start capping grades.
2. **Deterministic.** No LLM involvement in producing the finding.
3. **Already tested.** The specific check has its own real, existing test
   coverage (not merely "the evaluator has some tests").
4. **Documented safety justification.** A written explanation (in this
   section, updated) of what real defect class the check catches and why
   leaving it grade-invisible is itself a safety risk.
5. **Maintainer sign-off** on this specific addition.
6. **Contract version bump**, same as any other §9 "Changes Requiring
   Contract Version Bump" item.

**Explicitly NOT required**, unlike full graduation: the 14-day
stability-in-EXPERIMENTAL waiting period, or a corpus-wide false-positive-rate
validation run. Those bars exist to vet an evaluator's *overall* noise
profile before every one of its findings starts affecting grade -- irrelevant
here, since only 1-2 specific, already-individually-verified FAIL categories
are being added, not the evaluator's full output.

### Honesty note on this process itself

This section's own process (points 1-6 above) is this taskcard's proposal,
written and applied to its own originating case (`install_recipe`'s 2 safety
checks) in the same change that introduces it. It is not a process a
maintainer had separately reviewed and pre-approved as a general pattern
before this section was written -- **maintainer sign-off on this section
itself is part of what closes this taskcard**, not a formality after the
fact. A future addition to `SAFETY_OVERRIDE_FINDINGS` should cite this
section and satisfy points 1-6 above; it does not need to re-argue whether
the *category* of mechanism is acceptable, since that question is what this
section itself is meant to settle.

### Current entries

| Evaluator | Category | Added | Justification |
|---|---|---|---|
| `install_recipe` | `IR_PUBLISH_CLAIM` | 2026-09-10 | Catches a page falsely claiming a package is published when the registry records it isn't (RC-W1-003) -- confirmed 89 real, live findings across 9 products, all previously invisible to grade. |
| `install_recipe` | `IR_UNPUBLISHED_DISCLOSURE` | 2026-09-10 | Catches a page disclosing internal non-publication status to a public reader, against explicit 2026-09-03/2026-09-10 operator policy (ST-054 TC-14) -- 0 findings at the time of addition (already remediated by TC-16), added for regression protection, not an active defect. |

### Verification requirement (this taskcard's own closing gate)

Before this section's addition may be considered closed: a full
`--skip-graded` corpus re-evaluation must be run and its grade-distribution
shift (before/after counts per grade letter, portfolio-wide) recorded in the
originating taskcard's `evidence_refs` -- a change to grade computation
itself gets a global before/after, not a spot check on the 9 known-affected
products, per this contract's own existing discipline for any change of
this kind.
