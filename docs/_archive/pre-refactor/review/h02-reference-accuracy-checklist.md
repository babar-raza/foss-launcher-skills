# Archived Document

Archived: 2026-05-30

Reason: Superseded by the docs architecture refactor. This file is retained for history only; do not use it as current operating guidance.

Successor: See docs/README.md for the current documentation map and canonical references.

Original path: docs/_archive/pre-refactor/review/h02-reference-accuracy-checklist.md

---

# H-02: Reference Accuracy Checklist

**Gate**: H-02 — Stratified sample of 10 reference pages spot-checked against source
**Pass criteria**: API names match api_surface.json; member names verified; no hallucinations

## Before You Start

1. Generate your sample:
   ```bash
   .venv/Scripts/python scripts/pipeline/commands/diagnostics/human_review_sampler.py --family {family} --platform {platform} --gate h02
   ```
2. Open the generated file at `reports/human-review/{family}-{platform}-h02-sample.md`
3. Have the clone cache available at `runs/.clone_cache/` for cross-referencing

## Per-Page Checklist

For each of the 10 sampled reference pages:

### API Name Accuracy
- [ ] Class name matches the actual class in the source repository
- [ ] Namespace/package is correct
- [ ] The class actually exists in the version being documented

### Member Verification
- [ ] Listed methods exist in the source class
- [ ] Method signatures match (parameter names, types, return type)
- [ ] No hallucinated methods that don't exist in source
- [ ] No important public methods are missing (compare against `api_surface.json`)

### Access Modifiers
- [ ] Public/protected/internal/private annotations match source
- [ ] Static vs instance is correct
- [ ] Abstract/virtual/override is correct (where applicable)

### Inheritance
- [ ] Base class is correct
- [ ] Implemented interfaces are accurate
- [ ] No fabricated inheritance relationships

### Property/Field Accuracy
- [ ] Property types match source
- [ ] Read-only vs read-write matches source
- [ ] Default values mentioned are correct

### Cross-Reference Integrity
- [ ] Links to related classes resolve correctly
- [ ] Evidence block `apis` field matches actual class members
- [ ] `claim_ids` in evidence correspond to valid claims

## Completing the Review

1. Fill in the Verdict column in the sample file for each page
2. Fill in the Sign-Off block at the bottom of the sample file
3. Re-run `readiness_scorecard.py` to verify H-02 is recorded as PASS
