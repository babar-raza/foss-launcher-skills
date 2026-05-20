# Evidence and Provenance — foss-launcher Governance

**Source**: Adapted from aspose.org `docs/governance/evidence-and-provenance.md`
**Adapted**: 2026-05-15 (PAR-013 GV-001)

---

## Evidence Requirements (non-negotiable)

- Every content page write must pass S-23 (ground-check) before committing.
  **S-23 implementation**: `python scripts/pipeline/commands/content/audit.py --files {path}` (deterministic, scriptable).
- Every code block in content must come from a snippet in `knowledge/{family}/{platform}/snippets/`
- Every factual claim must be traceable to a `claim_id` in `knowledge/{family}/{platform}/claims.json`
- Claims with `confidence < 0.5` require human review before use
- An `evidence:` YAML frontmatter block must be present in every content page. Generate it
  deterministically with `python scripts/pipeline/commands/content/attach_evidence.py --files {path}`
  (for pages with code blocks) or manually via S-24 (evidence-cite, for prose-only pages). Format:
  ```yaml
  evidence:
    model_sha: "<repo_sha from merged/model.yaml>"   # anchors to knowledge version
    model_version: "<version>"
    claims: [CLM-xxx, ...]      # claim_ids from merged/claims.json ([] is valid)
    apis: [ClassName.method, …] # verified against merged/api_surface.json ([] is valid)
    formats: [{ext: glb, support: both}, …]  # omit if no format content
  ```
  Do **not** include `ground_check:` — it is self-reported and unverifiable.
  Do **not** use inline HTML comments (`<!-- evidence: ... -->`).
  After any knowledge model update, rerun `attach_evidence.py {family} {platform}` to refresh stale blocks.

## Knowledge Bootstrap Prerequisite

**Knowledge bootstrap is a hard prerequisite for content generation and healing.**

- All generation skills must exit with error code 1 when `knowledge.available == False`.
  Silent degradation that generates ungrounded content is prohibited.
- All evaluators must return WARN with "UNVERIFIED" text when knowledge is unavailable.
  Returning `[]` (silent skip) is prohibited.
- Pages generated without local knowledge must have `provenance.knowledge_status: ungrounded`.
- Ungrounded pages must not receive grade A (ceiling is B).

## Evidence Proof in Commits

Every commit touching content must include in the commit message:

- Knowledge model SHA: `knowledge/{family}/{platform}/merged/model.yaml` `repo_sha` value
- Ground-check result: `PASS` (with report path)
- Skills invoked: `[S-xx, S-yy, ...]`

The `evidence:` frontmatter block in each page is the persistent inline evidence record.
`model_sha` anchors it to the knowledge version; `audit.py` detects staleness automatically.

## Verification Standards for Fixes

Every fix — whether to a script, evaluator, content page, or knowledge artifact — must meet
these verification standards before being declared complete.

| Fix type | Before evidence | After evidence | Tool |
|----------|----------------|----------------|------|
| Content page fix | `audit.py` FAIL count before fix | `audit.py` FAIL count after fix (must be ≤ before) | `python scripts/pipeline/commands/content/audit.py --files {path}` |
| Evaluator logic fix | Evaluation output before change | Evaluation output after change | `python -m scripts.pipeline.content_eval.cli evaluate ...` |
| Knowledge artifact fix | Artifact state before fix (git diff) | Artifact state after fix | `git diff knowledge/` |
| Script/pipeline fix | Script invocation output before fix | Script invocation output after fix | Per script |

After any fix, verify no previously passing content now FAILs.

## Output-Location Discipline

All agent-generated artifact files must be written to their designated location.

| Artifact type | Correct location | Never write to |
|---------------|-----------------|----------------|
| Content pages | `$CONTENT_REPO_PATH/content/{site}/en/{family}/{platform}/` | `reports/`, `knowledge/`, repo root |
| Knowledge artifacts | `knowledge/{family}/{platform}/` | `content/`, `reports/`, repo root |
| Audit and evaluation reports | `reports/` (local-only) | `content/`, `knowledge/`, repo root |
| Launch gate results | `reports/launch-gate/` | `content/`, `knowledge/` |
| Skill gap escalation reports | `reports/skill-gaps/` | Any git-tracked path |
| Evidence repair logs | `reports/evidence-repair/` | Any git-tracked path |
| Design documents | `reports/design/` | `knowledge/`, `content/`, `skills/` |

**`reports/` is a strict local artifact boundary.** Nothing under `reports/` may ever be staged or committed.
If you need a design document to persist across sessions, it must live in `reports/design/` (local-only).
