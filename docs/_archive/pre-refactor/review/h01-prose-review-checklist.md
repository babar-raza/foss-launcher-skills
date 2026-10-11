# Archived Document

Archived: 2026-05-30

Reason: Superseded by the docs architecture refactor. This file is retained for history only; do not use it as current operating guidance.

Successor: See docs/README.md for the current documentation map and canonical references.

Original path: docs/_archive/pre-refactor/review/h01-prose-review-checklist.md

---

# H-01: Human Prose Review Checklist

**Gate**: H-01 — Random sample of 5 non-reference pages reviewed by human
**Pass criteria**: Pages match system grades (within 1 grade level); no hallucinations; prose correct

## Before You Start

1. Generate your sample:
   ```bash
   .venv/Scripts/python scripts/pipeline/commands/diagnostics/human_review_sampler.py --family {family} --platform {platform} --gate h01
   ```
2. Open the generated file at `reports/human-review/{family}-{platform}-h01-sample.md`
3. Review each sampled page against the checklist below

## Per-Page Checklist

For each of the 5 sampled pages:

### Factual Accuracy
- [ ] All capability claims are supported by the library (cross-check against `knowledge/{family}/{platform}/merged/claims.json`)
- [ ] No hallucinated features or methods mentioned in prose
- [ ] Version numbers and compatibility claims are accurate

### Grade Calibration
- [ ] Your assessment matches the system grade within 1 level (e.g., system says B, you agree B or C is fair)
- [ ] If grade mismatch > 1 level, note the specific deficiency

### Language Quality
- [ ] No marketing superlatives (seamless, robust, best-in-class)
- [ ] No unsupported performance claims (fastest, lightweight)
- [ ] Technical tone appropriate for developer documentation

### Platform Correctness
- [ ] Code examples use the correct language for the platform
- [ ] Install instructions reference the correct package manager (NuGet for .NET, pip for Python, Maven for Java)
- [ ] Import statements use correct namespaces

### Structure
- [ ] Page has clear heading hierarchy
- [ ] Content matches the page role (getting-started, how-to, reference, etc.)
- [ ] No placeholder text (TODO, TBD, Lorem ipsum)

### Code Quality (if test code present)
- [ ] No T1/T2 monkeypatch violations per AGENTS.md §16

## Completing the Review

1. Fill in the Verdict column in the sample file for each page
2. Fill in the Sign-Off block at the bottom of the sample file
3. Re-run `readiness_scorecard.py` to verify H-01 is recorded as PASS
