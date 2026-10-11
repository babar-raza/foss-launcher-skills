# Evaluator Changes

Status: Current
Audience: Contributor
Canonical reference: `docs/development/testing.md`
Last code-backed audit: 2026-09-17

Evaluator changes affect content quality gates and must be tested carefully.

## Checklist

1. Identify the evaluator and affected findings.
2. Add or update focused tests under `scripts/pipeline/tests/content_eval/`.
3. Run focused evaluator tests.
4. Run broader content eval tests if behavior affects shared grading or strict mode.
5. **Bump the evaluator's version.** Any change to
   `scripts/pipeline/content_eval/evaluators/{name}.py` must also bump either
   `EVALUATOR_VERSIONS["{name}"]` or the cross-cutting `EVALUATOR_LOGIC_VERSION`
   (for a change affecting multiple evaluators) in
   `scripts/pipeline/content_eval/__init__.py`, in the **same commit**. This is
   enforced by `scripts/ci/checks/check_evaluator_version_bump.py`, which runs
   as a real pre-commit gate (`scripts/pre-commit-audit.sh` Step 44 — added
   2026-09-17 after a real, repeated incident where this was missed, silently
   defeating `--skip-graded`'s staleness detection for the affected evaluator).
   A genuinely cosmetic change (docstring/comment only) may instead add a line
   `EVALUATOR-VERSION-BUMP-EXEMPT: <reason>` to the same diff.
6. Update references only if CLI/config/contracts changed.

This guidance was missing from this document between 2026-05-30 (when the prior
version of this page, `docs/workflows/evaluator-changes.md`, was deleted and
this page took over without carrying the rule forward) and 2026-09-17, during
which the omission contributed to a real, recurring CI failure pattern
(content-governance-checks.yml, 49% failure rate in September 2026 — see
mission MT069's `TC-05`/`TC-15` findings). `AGENTS.md` §9a still links to the
deleted path; that fix is a separate, human-maintainer action (`AGENTS.md` is
human-authored only) and has not yet landed as of this note.

References:

- [Content audit and evaluation](../guides/content-audit-and-evaluation.md)
- [Testing and CI](testing.md)
- [Governance gates](../reference/governance-gates.md)
