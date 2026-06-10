---
name: content-enrich
id: S-108
description: >
  Post-launch cross-subdomain enrichment audit and planning workflow. Produces
  coverage, candidate, and handoff manifests without writing content directly.
args: "{family} {platform} [--mode audit|dry-run|execute] [--output-root PATH]"
---

# S-108: Content Enrich — Post-Launch Enrichment Planning

Audit cross-subdomain content coverage for a launched product, identify enrichment candidates, and produce governed handoff manifests for downstream skills.

**Arguments:** `$ARGUMENTS`

## Status

This standalone skill restores the `content-enrich` command surface from the embedded aspose.org skill set. The full aspose.org enrichment backend is not yet ported into this standalone repo, so this skill is currently a governed orchestration contract and migration target.

Use it to plan and verify the enrichment workflow. Do not treat it as a direct content writer.

## Expected Format

```text
{family} {platform} [--mode audit|dry-run|execute] [--output-root PATH]
```

Default mode is `audit`.

## Preconditions

- Knowledge artifacts exist for `{family}/{platform}`.
- A site plan or equivalent content inventory exists.
- The content root is resolved through the external content repo adapter contract, not by assuming the skills repo contains Hugo content.
- Any write-like output uses `--output-root` or a local reports directory.

## Modes

### audit

Read-only coverage analysis. Produces coverage outputs only.

Expected outputs:

- `coverage-matrix.json`
- `coverage-matrix.md`

### dry-run

Read-only candidate generation and disposition planning. Produces candidates, decisions, handoff manifest, and denominator check with `dry_run: true`.

Expected outputs:

- `candidate-list.json`
- `enrichment-decisions.json`
- `handoff-manifest.json`
- `denominator-check.json`

### execute

Manifest-based handoff mode. It must not write content pages directly. It may only create a local execution manifest that instructs operators or later orchestrators to invoke downstream skills such as `new-docs-page`, `new-blog-post`, `new-kb-howto`, or `page-update`.

## Denominator Invariant

Every candidate must be assigned exactly one disposition:

```text
total_candidates = generate_now + update_existing + deferred_to_backlog + rejected_with_reason + blocked_with_reason
```

If the invariant fails, stop and report the mismatch.

## Safety

- Never write to `aspose.org/content`.
- Never write content pages directly.
- Never publish, deploy, push, or open a PR.
- Prefer `--output-root` for all generated reports and manifests.
- Blog candidates require a stricter quality gate; medium-confidence blog candidates should be deferred rather than generated.

## Migration Note

The aspose.org reference implementation uses `scripts/pipeline/commands/enrichment/content_enrich.py` plus `scripts/pipeline/lib/enrichment/`. Porting that backend belongs to the dependency-port taskcards. Until then, this skill preserves discoverability, governance, and user-facing workflow shape.

## Verification

- Run `python scripts/validate_skills.py`.
- Confirm provider mirrors are synced.
- Verify any future backend supports `audit` and `dry-run` without content writes.
